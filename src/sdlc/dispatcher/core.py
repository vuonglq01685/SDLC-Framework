"""Dispatcher core: primary dispatch + panel orchestration (FR25, FR26, FR27, NFR-OBS-2).

Architecture §821-§824, §1067; ADR-013, ADR-016, ADR-024, ADR-025, ADR-026.

Boundary rules (Architecture §1106, §1109):
- Imports ``runtime/`` ONLY via ``sdlc.runtime.abc.AIRuntime`` ABC.
- Forbidden from importing ``engine/`` or ``cli/``.
- ``repo_root`` is accepted as a ``Path`` parameter; ``cli._paths`` stays in CLI.

# TODO(epic-4): STOP-trigger placeholder — ``kind="stop_trigger_raised"`` entries
# are written by ``_emit_stop_trigger()`` on terminal dispatch failure (AC5).
# Epic 4 Story 4.6 reads these journal entries to surface the actual STOP banner.
# See ``deferred-work.md`` EPIC-4-STOP-TRIGGER-WIRE.

DR2 — ``_run_member``, ``_emit_stop_trigger``, ``_make_journal_entry``, ``_now_ts``,
``_default_prompt_builder`` extracted to ``dispatcher/_panel_helpers.py`` to keep
this file under the AC6 350-LOC cap. Public API (``dispatch``, ``dispatch_panel``,
``DispatchResult``, ``PanelResult``, ``DispatchOutcome``) lives here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher._panel_helpers import (
    DispatchMemberResult,
    _default_prompt_builder,
    _emit_stop_trigger,
    _run_member,
    _validate_target_path,
)
from sdlc.errors import DispatchError
from sdlc.runtime import AgentResult, AIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

DispatchOutcome: TypeAlias = Literal["success", "failed"]


@dataclass(frozen=True)
class DispatchResult:
    """Immutable result of a single-specialist dispatch (AC1, FR25)."""

    specialist_name: str
    target_path: Path
    agent_result: AgentResult
    attempts: int
    outcome: DispatchOutcome


@dataclass(frozen=True)
class PanelResult:
    """Immutable result of a panel dispatch (AC2, FR25+FR26)."""

    primary_result: DispatchResult
    parallel_results: tuple[DispatchResult, ...]
    synthesizer_result: DispatchResult | None
    write_targets: tuple[Path, ...]
    total_attempts: int
    outcome: DispatchOutcome


def _to_public(member: DispatchMemberResult) -> DispatchResult:
    return DispatchResult(
        specialist_name=member.specialist_name,
        target_path=member.target_path,
        agent_result=member.agent_result,
        attempts=member.attempts,
        outcome=member.outcome,
    )


def _failed_result(
    specialist_name: str,
    target_path: Path,
    attempts: int = 1,
) -> DispatchResult:
    return DispatchResult(
        specialist_name=specialist_name,
        target_path=target_path,
        agent_result=AgentResult(output_text="", tokens_in=0, tokens_out=0),
        attempts=attempts,
        outcome="failed",
    )


async def dispatch(
    step: WorkflowSpec,
    *,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    repo_root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    prompt_builder: Callable[[Specialist, WorkflowSpec], str] = _default_prompt_builder,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    _max_attempts: int = 3,
) -> DispatchResult:
    """Dispatch the primary specialist for a workflow step (AC1, FR25).

    Per-attempt journal entries are written via the ``on_attempt`` hook in
    ``with_retries``; ``artifact_written`` is written on success only.

    P18: emits STOP-trigger placeholder on terminal failure (parity with dispatch_panel).
    """
    try:
        member = await _run_member(
            step,
            step.primary_agent,
            "primary",
            runtime=runtime,
            registry=registry,
            repo_root=repo_root,
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
            prompt_builder=prompt_builder,
            sleep=sleep,
            max_attempts=_max_attempts,
        )
    except DispatchError as exc:
        await _emit_stop_trigger(
            step.primary_agent,
            step.name,
            journal_path,
            last_error=str(exc),
        )
        raise
    return _to_public(member)


async def _gather_with_semaphore(
    coros: list[Awaitable[DispatchMemberResult]],
    *,
    max_parallel_agents: int,
) -> list[DispatchMemberResult | BaseException]:
    """Run ``coros`` under a Semaphore(max_parallel_agents); collect every outcome.

    P4: uses ``gather(return_exceptions=True)`` so that a single member's failure
    does NOT leave its siblings as orphan coroutines (the ``BoundedDispatcher.dispatch_many``
    contract uses ``return_exceptions=False`` which leaves siblings running per the
    Python asyncio gather docs — discovered by Edge Case Hunter). Throttling pattern
    preserves the BoundedDispatcher mandate; the API call is replaced for safety.
    """
    sem = asyncio.Semaphore(max_parallel_agents)

    async def _acquire(coro: Awaitable[DispatchMemberResult]) -> DispatchMemberResult:
        async with sem:
            return await coro

    return list(await asyncio.gather(*(_acquire(c) for c in coros), return_exceptions=True))


async def dispatch_panel(  # noqa: C901, PLR0912 — phase-by-phase orchestration; complexity is intrinsic to AC2
    step: WorkflowSpec,
    *,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    repo_root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    prompt_builder: Callable[[Specialist, WorkflowSpec], str] = _default_prompt_builder,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_parallel_agents: int = 4,
    _max_attempts: int = 3,
) -> PanelResult:
    """Orchestrate a panel dispatch: primary → parallel (bounded) → synthesizer (AC2, FR26).

    Phase 0 — Pre-resolve every member via ``registry.get(...)`` so a missing parallel
    or synthesizer specialist does NOT leave the primary already written (AC2 step 1
    atomicity, P7+P8).

    Parallel agents run under a semaphore; ``gather(return_exceptions=True)`` collects
    every outcome to prevent orphan coroutines on first failure (P4).

    Synthesizer overwrites the primary's first write_globs entry per AC2.4 wording (DR5);
    the synthesizer's ``dispatch_attempt`` journal payload includes ``panel_size`` (P6).

    On any DispatchError the panel short-circuits, emits a ``stop_trigger_raised``
    journal placeholder (AC5, TODO(epic-4)), and returns ``outcome="failed"``;
    the synthesizer is never dispatched on failure (AC2.5).
    """
    if max_parallel_agents < 1:
        raise DispatchError(
            f"max_parallel_agents must be >= 1, got {max_parallel_agents}",
            details={"max_parallel_agents": max_parallel_agents},
        )

    # Phase 0 — atomicity pre-resolution (P7+P8) and primary target derivation (DR5).
    members_to_resolve: list[str] = [step.primary_agent, *step.parallel_agents]
    if step.synthesizer_agent:
        members_to_resolve.append(step.synthesizer_agent)
    for name in members_to_resolve:
        registry.get(name)  # propagates SpecialistError on miss

    primary_globs = step.write_globs.get(step.primary_agent)
    if not primary_globs:
        raise DispatchError(
            f"workflow step {step.name!r} has no write_globs entry for primary"
            f" specialist {step.primary_agent!r}",
            details={"step": step.name, "specialist": step.primary_agent},
        )
    primary_target = _validate_target_path(repo_root, primary_globs[0])

    _kw: dict[str, object] = dict(
        runtime=runtime,
        registry=registry,
        repo_root=repo_root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=prompt_builder,
        sleep=sleep,
        max_attempts=_max_attempts,
    )

    # Phase 1 — primary (sequential)
    try:
        primary_member = await _run_member(step, step.primary_agent, "primary", **_kw)  # type: ignore[arg-type]
    except DispatchError as exc:
        await _emit_stop_trigger(step.primary_agent, step.name, journal_path, last_error=str(exc))
        return PanelResult(
            primary_result=_failed_result(step.primary_agent, primary_target),
            parallel_results=(),
            synthesizer_result=None,
            write_targets=(),
            total_attempts=1,
            outcome="failed",
        )

    primary_pub = _to_public(primary_member)

    # Phase 2 — parallel agents (concurrent under semaphore; P4 collect-all)
    parallel_pub: tuple[DispatchResult, ...] = ()
    if step.parallel_agents:
        coros: list[Awaitable[DispatchMemberResult]] = [
            _run_member(step, name, "parallel", **_kw)  # type: ignore[arg-type]
            for name in step.parallel_agents
        ]
        outcomes = await _gather_with_semaphore(coros, max_parallel_agents=max_parallel_agents)
        successes: list[DispatchMemberResult] = []
        first_exc: BaseException | None = None
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                if first_exc is None:
                    first_exc = outcome
            else:
                successes.append(outcome)
        parallel_pub = tuple(_to_public(m) for m in successes)
        if first_exc is not None:
            err_msg = str(first_exc)
            await _emit_stop_trigger("parallel_agents", step.name, journal_path, last_error=err_msg)
            return PanelResult(
                primary_result=primary_pub,
                parallel_results=parallel_pub,
                synthesizer_result=None,
                write_targets=tuple(
                    [primary_pub.target_path] + [p.target_path for p in parallel_pub]
                ),
                total_attempts=primary_pub.attempts + sum(p.attempts for p in parallel_pub),
                outcome="failed",
            )

    # Phase 3 — synthesizer (sequential, target overrides primary's per AC2.4 / DR5)
    synth_pub: DispatchResult | None = None
    synth_name = step.synthesizer_agent
    if synth_name:
        panel_size = 1 + len(parallel_pub) + 1  # primary + parallel + synth
        panel_outputs: dict[str, object] = {
            r.specialist_name: r.agent_result.output_text for r in (primary_pub, *parallel_pub)
        }
        try:
            synth_member = await _run_member(
                step,
                synth_name,
                "synthesizer",
                extra_context={"panel_outputs": panel_outputs},
                extra_journal_payload={"panel_size": panel_size},
                target_path_override=primary_target,
                **_kw,  # type: ignore[arg-type]
            )
        except DispatchError as exc:
            synth_attempts_raw = exc.details.get("attempts", 1) if exc.details else 1
            synth_attempts = synth_attempts_raw if isinstance(synth_attempts_raw, int) else 1
            err_msg = str(exc)
            await _emit_stop_trigger(synth_name, step.name, journal_path, last_error=err_msg)
            return PanelResult(
                primary_result=primary_pub,
                parallel_results=parallel_pub,
                synthesizer_result=None,
                write_targets=tuple([r.target_path for r in (primary_pub, *parallel_pub)]),
                total_attempts=sum(r.attempts for r in (primary_pub, *parallel_pub))
                + synth_attempts,
                outcome="failed",
            )
        synth_pub = _to_public(synth_member)

    all_results = [primary_pub, *parallel_pub, *([synth_pub] if synth_pub else [])]
    return PanelResult(
        primary_result=primary_pub,
        parallel_results=parallel_pub,
        synthesizer_result=synth_pub,
        write_targets=tuple(r.target_path for r in all_results),
        total_attempts=sum(r.attempts for r in all_results),
        outcome="success",
    )


__all__: tuple[str, ...] = (
    "DispatchOutcome",
    "DispatchResult",
    "PanelResult",
    "dispatch",
    "dispatch_panel",
)
