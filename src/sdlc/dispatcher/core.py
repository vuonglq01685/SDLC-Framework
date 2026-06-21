"""Dispatcher core: primary dispatch + panel orchestration (FR25, FR26, FR27, NFR-OBS-2).

Architecture §821-§824, §1067; ADR-013, ADR-016, ADR-024, ADR-025, ADR-026.
Boundary rules (§1106, §1109): imports ``runtime/`` ONLY via ``AIRuntime`` ABC; forbidden
from importing ``engine/`` or ``cli/``; ``repo_root`` is a ``Path`` parameter.

# TODO(epic-4): STOP-trigger placeholder — ``kind="stop_trigger_raised"`` entries
# are written by ``_emit_stop_trigger()`` on terminal dispatch failure (AC5).
# Epic 4 Story 4.6 reads these to surface the STOP banner. See deferred-work.md.

DR2 — ``_run_member``, ``_emit_stop_trigger``, ``_make_journal_entry``, ``_now_ts``,
``_legacy_default_prompt_builder`` extracted to ``dispatcher/_panel_helpers.py``.
Public API (``dispatch``, ``dispatch_panel``, ``DispatchResult``, ``PanelResult``,
``DispatchOutcome``) lives here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias

from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher._panel_helpers import (
    DispatchMemberResult,
    _emit_stop_trigger,
    _globstar_match,
    _is_phase1_prompt_builder,
    _legacy_default_prompt_builder,
    _run_member,
    _unified_write_target_panel,
    _validate_target_path,
)
from sdlc.errors import DispatchError, WorkflowError
from sdlc.hooks.runner import BypassRequest, HookDecision
from sdlc.runtime import AgentResult, AIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

if TYPE_CHECKING:
    from sdlc.dispatcher import PanelObserver


class PromptBuilder(Protocol):
    """Prompt-assembly Protocol — Phase 1 form takes role/idea_text/upstream_outputs/extra_context.

    Legacy 2-arg ``_legacy_default_prompt_builder`` is also accepted via
    ``LegacyPromptBuilder`` for non-Phase-1 sites. The dispatcher introspects
    the call shape at the invocation site (``_run_member``).
    """

    def __call__(
        self,
        specialist: Specialist,
        spec: WorkflowSpec,
        *,
        idea_text: str,
        role: Literal["primary", "parallel", "synthesizer"],
        upstream_outputs: Sequence[str] = (),
        extra_context: Mapping[str, object] = ...,
    ) -> str: ...


LegacyPromptBuilder: TypeAlias = Callable[[Specialist, WorkflowSpec], str]

DispatchOutcome: TypeAlias = Literal["success", "failed", "hook_rejected"]


@dataclass(frozen=True)
class DispatchResult:
    """Immutable result of a single-specialist dispatch (AC1, FR25)."""

    specialist_name: str
    target_path: Path
    agent_result: AgentResult
    attempts: int
    outcome: DispatchOutcome  # "success" | "failed" | "hook_rejected"


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


def _should_emit_stop_trigger_raised(exc: DispatchError) -> bool:
    """Story 4.7: high-risk halts use ``stop_triggered``, not ``stop_trigger_raised``."""
    details = exc.details or {}
    return not details.get("high_risk_path_halt")


def _validate_target_path_override(
    target: Path,
    *,
    repo_root: Path,
    spec: WorkflowSpec,
    specialist: str,
) -> None:
    """P13 (code review): reject overrides that escape the repo or workflow contract.

    Three guards:
      1. ``target`` must resolve to a path under ``repo_root`` — no traversal.
      2. ``target`` must not be a symlink — would defeat phase_gate semantics.
      3. ``target`` (relative form) must match at least one ``write_globs`` entry
         for the primary specialist — overrides cannot widen the workflow surface.
    """
    try:
        rel = target.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"target_path_override {target!s} is not under repo_root {repo_root!s}"
        ) from exc
    if target.is_symlink():
        raise ValueError(
            f"target_path_override {target!s} is a symlink; dispatcher refuses to follow it"
        )
    globs = spec.write_globs.get(specialist, ())
    if not globs:
        return  # no constraint declared — caller accepted broad surface
    rel_posix = rel.as_posix()
    if not any(_globstar_match(rel_posix, pat) for pat in globs):
        raise ValueError(
            f"target_path_override {rel_posix!r} matches none of the write_globs "
            f"for specialist {specialist!r}: {list(globs)}"
        )


async def dispatch(
    step: WorkflowSpec,
    *,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    repo_root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    prompt_builder: PromptBuilder | LegacyPromptBuilder = _legacy_default_prompt_builder,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...] = (),
    bypass: BypassRequest | None = None,
    observer: PanelObserver | None = None,
    persist_artifact: bool = True,
    target_path_override: Path | None = None,
    auto_loop_mode: bool = False,
    confirm_tool_call_id: str | None = None,
    _max_attempts: int = 3,
) -> DispatchResult:
    """Dispatch the primary specialist for a workflow step (AC1, FR25).

    Per-attempt journal entries are written via the ``on_attempt`` hook in
    ``with_retries``; ``artifact_written`` is written on success only.
    On hook deny: ``hook_rejected`` is written by runner; ``dispatch_attempt``
    (outcome="hook_rejected") is written here; file is NOT written.

    P18: emits STOP-trigger placeholder on terminal failure (parity with dispatch_panel).

    P13 (code review): ``target_path_override`` is validated here — it MUST live
    under ``repo_root`` (no path traversal), MUST NOT be a symlink (the
    dispatcher writes through the path; following a symlink to outside the
    repo would defeat phase_gate's relative-path enforcement), and MUST match
    at least one ``write_globs`` entry for the primary specialist (the override
    cannot route writes to a path the workflow YAML disallows). Callers passing
    user-derived slug paths (e.g., ``cli/research.py``) must keep both guards
    intact.

    Story 2A.10 extends the single-specialist surface with three kwargs that
    panel dispatch already exposed via :func:`_run_member`:

    * ``observer`` — typed CLI passthrough; when set with
      ``emit_agent_dispatched=True`` the dispatcher emits
      ``kind="agent_dispatched"`` once per dispatch (mirrors panel behaviour).
    * ``persist_artifact`` — set to False to suppress the dispatcher's
      ``Path.write_text`` + ``artifact_written`` journal append. The caller
      is then responsible for any persistent write (used by ``sdlc verify``
      so the verification ceremony is non-destructive — AC5/D2).
    * ``target_path_override`` — bypass ``write_globs[0]`` resolution and
      use the supplied concrete path. Required when the workflow YAML
      declares a glob pattern (e.g. ``01-Requirement/**/*.md``) but the
      CLI knows the artifact path explicitly (Story 2A.10 AC2/AC5).
    """
    if target_path_override is not None:
        _validate_target_path_override(
            target_path_override,
            repo_root=repo_root,
            spec=step,
            specialist=step.primary_agent,
        )
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
            hooks=hooks,
            bypass=bypass,
            observer=observer,
            persist_artifact=persist_artifact,
            target_path_override=target_path_override,
            auto_loop_mode=auto_loop_mode,
            confirm_tool_call_id=confirm_tool_call_id,
        )
    except DispatchError as exc:
        if _should_emit_stop_trigger_raised(exc):
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


async def dispatch_panel(  # noqa: C901, PLR0912, PLR0915 — panel orchestration intrinsic to AC2
    step: WorkflowSpec,
    *,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    repo_root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    prompt_builder: PromptBuilder | LegacyPromptBuilder = _legacy_default_prompt_builder,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...] = (),
    observer: PanelObserver | None = None,
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

    Story 2A.8 D1-C+D2-B: CLI-specific concerns (slash_command tagging, idea_text,
    journal-emit gating, synthesizer frontmatter context) are passed via the typed
    ``observer`` argument instead of free-standing kwargs. The synthesizer is always
    the canonical writer for unified-target panels (D2-B); the CLI no longer
    post-processes the synthesizer's output.
    """
    if max_parallel_agents < 1:
        raise DispatchError(
            f"max_parallel_agents must be >= 1, got {max_parallel_agents}",
            details={"max_parallel_agents": max_parallel_agents},
        )

    # P21: Phase-1 prompt_builder REQUIRES observer.idea_text to be non-empty —
    # the synthesizer's prompt embeds the idea verbatim. Fail at the entry, not
    # deep in _run_member, so the error surfaces with the exact caller invariant.
    if _is_phase1_prompt_builder(prompt_builder):
        idea_text = observer.idea_text if observer is not None else None
        if not idea_text:
            raise WorkflowError(
                "phase1 prompt_builder requires non-empty observer.idea_text",
                details={
                    "step": step.name,
                    "prompt_builder": getattr(prompt_builder, "__name__", repr(prompt_builder)),
                },
            )
    # P28: emit_agent_dispatched=True without a slash_command produces journal
    # entries with no provenance — block this misconfiguration at the entry.
    if observer is not None and observer.emit_agent_dispatched and not observer.slash_command:
        raise WorkflowError(
            "observer.emit_agent_dispatched=True requires non-empty observer.slash_command",
            details={"step": step.name},
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

    unified = _unified_write_target_panel(step)
    # D2-B: for unified-target panels the synthesizer is the canonical writer;
    # non-synth members run for their candidate output but do NOT persist to disk.
    # The synthesizer ALWAYS persists (no more cli_finalize_product_md shortcut).
    persist_non_synth = not unified

    # Phase 1 — primary (sequential)
    try:
        primary_member = await _run_member(
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
            hooks=hooks,
            observer=observer,
            persist_artifact=persist_non_synth,
            upstream_outputs=(),
        )
    except DispatchError as exc:
        if _should_emit_stop_trigger_raised(exc):
            await _emit_stop_trigger(
                step.primary_agent,
                step.name,
                journal_path,
                last_error=str(exc),
            )
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
            _run_member(
                step,
                name,
                "parallel",
                runtime=runtime,
                registry=registry,
                repo_root=repo_root,
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                prompt_builder=prompt_builder,
                sleep=sleep,
                max_attempts=_max_attempts,
                hooks=hooks,
                observer=observer,
                persist_artifact=persist_non_synth,
                upstream_outputs=(),
            )
            for name in step.parallel_agents
        ]
        outcomes = await _gather_with_semaphore(coros, max_parallel_agents=max_parallel_agents)
        successes: list[DispatchMemberResult] = []
        first_exc: BaseException | None = None
        for outcome in outcomes:
            # P14: never swallow cancellation/interrupt — surface them so the
            # caller can shut down cleanly instead of being silently degraded
            # to a "failed" panel result.
            if isinstance(outcome, (KeyboardInterrupt, asyncio.CancelledError)):
                raise outcome
            if isinstance(outcome, BaseException):
                if first_exc is None:
                    first_exc = outcome
            else:
                successes.append(outcome)
        parallel_pub = tuple(_to_public(m) for m in successes)
        if first_exc is not None:
            err_msg = str(first_exc)
            if not isinstance(first_exc, DispatchError) or _should_emit_stop_trigger_raised(
                first_exc
            ):
                await _emit_stop_trigger(
                    "parallel_agents", step.name, journal_path, last_error=err_msg
                )
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
        upstream_tuple = tuple(r.agent_result.output_text for r in (primary_pub, *parallel_pub))
        try:
            synth_member = await _run_member(
                step,
                synth_name,
                "synthesizer",
                runtime=runtime,
                registry=registry,
                repo_root=repo_root,
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                prompt_builder=prompt_builder,
                sleep=sleep,
                max_attempts=_max_attempts,
                hooks=hooks,
                observer=observer,
                extra_context={"panel_outputs": panel_outputs},
                extra_journal_payload={"panel_size": panel_size},
                target_path_override=primary_target,
                # D2-B: synthesizer is always the canonical writer.
                persist_artifact=True,
                upstream_outputs=upstream_tuple,
            )
        except DispatchError as exc:
            synth_attempts_raw = exc.details.get("attempts", 1) if exc.details else 1
            synth_attempts = synth_attempts_raw if isinstance(synth_attempts_raw, int) else 1
            err_msg = str(exc)
            if _should_emit_stop_trigger_raised(exc):
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
