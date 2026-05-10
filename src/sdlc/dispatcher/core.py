"""Dispatcher core: primary dispatch + panel orchestration (FR25, FR26, FR27, NFR-OBS-2).

Architecture §821-§824, §1067; ADR-013, ADR-016, ADR-024, ADR-025, ADR-026.

Boundary rules (Architecture §1106, §1109):
- Imports ``runtime/`` ONLY via ``sdlc.runtime.abc.AIRuntime`` ABC.
- Forbidden from importing ``engine/`` or ``cli/``.
- ``repo_root`` is accepted as a ``Path`` parameter; ``cli._paths`` stays in CLI.

# TODO(epic-4): STOP-trigger placeholder (kind="stop_trigger_raised") is emitted
# on terminal failure; Epic 4 Story 4.6 reads these journal entries to surface
# the actual STOP banner. See ``deferred-work.md`` EPIC-4-STOP-TRIGGER-WIRE.
"""

from __future__ import annotations

import asyncio
import datetime
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sdlc.concurrency.subprocess_pool import BoundedDispatcher
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import DispatchError
from sdlc.journal import append as journal_append
from sdlc.runtime.abc import AgentResult, AIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.telemetry.runs import record_agent_run

from sdlc.dispatcher.retry import with_retries

_ACTOR = "dispatcher"
_NULL_HASH = "sha256:" + "0" * 64

# EPIC-2A-DEBT-SHARED-TIME: cli/_time.py is the canonical ts source but dispatcher
# cannot import from cli (boundary §1106). Inline here until a shared util is created.
def _now_ts() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


@dataclass(frozen=True)
class DispatchResult:
    """Immutable result of a single-specialist dispatch (AC1, FR25)."""

    specialist_name: str
    target_path: Path
    agent_result: AgentResult
    attempts: int
    outcome: Literal["success", "failed"]


@dataclass(frozen=True)
class PanelResult:
    """Immutable result of a panel dispatch (AC2, FR25+FR26)."""

    primary_result: DispatchResult
    parallel_results: tuple[DispatchResult, ...]
    synthesizer_result: DispatchResult | None
    write_targets: tuple[Path, ...]
    total_attempts: int
    outcome: Literal["success", "failed"]


def _default_prompt_builder(specialist: Specialist, step: WorkflowSpec) -> str:
    """Minimal prompt scaffold — Story 2A.8 will replace with full context (FR25)."""
    return specialist.body


def _make_journal_entry(
    *,
    seq: int,
    ts: str,
    kind: str,
    target_id: str,
    payload: dict[str, object],
) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=_ACTOR,
        kind=kind,
        target_id=target_id,
        before_hash=None,
        after_hash=_NULL_HASH,
        payload=payload,
    )


async def _run_member(
    step: WorkflowSpec,
    specialist_name: str,
    target_kind: Literal["primary", "parallel", "synthesizer"],
    *,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    repo_root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    prompt_builder: Callable[[Specialist, WorkflowSpec], str],
    sleep: Callable[[float], Awaitable[None]],
    max_attempts: int,
    extra_context: dict[str, object] | None = None,
) -> DispatchResult:
    """Dispatch a single specialist as a panel member (primary/parallel/synthesizer).

    # EPIC-2A-DEBT-WRITE-PRIMITIVE: output write uses Path.write_text() (plain).
    # write_state_raw_atomic_sync is JSON-only and POSIX-only; a raw-text atomic
    # primitive is needed for arbitrary specialist artifacts. Deferred to Epic 2B.
    """
    specialist = registry.get(specialist_name)

    write_globs = step.write_globs.get(specialist_name)
    if not write_globs:
        raise DispatchError(
            f"workflow step {step.name!r} has no write_globs entry for specialist"
            f" {specialist_name!r}",
            details={"step": step.name, "specialist": specialist_name},
        )
    target_path = (repo_root / write_globs[0]).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = prompt_builder(specialist, step)
    context: dict[str, object] = {
        "workflow_step": step.name,
        "agent_name": specialist_name,
        "target_kind": target_kind,
    }
    if extra_context:
        context.update(extra_context)

    actual_attempts = 0

    async def _on_attempt(attempt_num: int, outcome: str) -> None:
        nonlocal actual_attempts
        actual_attempts = attempt_num
        await journal_append(
            _make_journal_entry(
                seq=attempt_num - 1,
                ts=_now_ts(),
                kind="dispatch_attempt",
                target_id=f"{step.name}/{specialist_name}",
                payload={
                    "specialist": specialist_name,
                    "outcome": outcome,
                    "attempt": attempt_num,
                    "target_kind": target_kind,
                },
            ),
            journal_path,
        )

    t_start = time.monotonic()
    agent_result = await with_retries(
        lambda: runtime.dispatch(prompt, context),
        max_attempts=max_attempts,
        sleep=sleep,
        on_attempt=_on_attempt,
    )
    duration_ms = int((time.monotonic() - t_start) * 1000)
    ts = _now_ts()
    run_id = str(uuid.uuid4())

    target_path.write_text(agent_result.output_text, encoding="utf-8")

    await journal_append(
        _make_journal_entry(
            seq=actual_attempts,
            ts=ts,
            kind="artifact_written",
            target_id=str(target_path.relative_to(repo_root)),
            payload={
                "target": str(target_path.relative_to(repo_root)),
                "writer": "dispatcher",
                "specialist": specialist_name,
            },
        ),
        journal_path,
    )

    record_agent_run(
        agent_runs_path,
        run_id=run_id,
        ts=ts,
        workflow_step=step.name,
        specialist_name=specialist_name,
        target_kind=target_kind,
        outcome="success",
        attempts=actual_attempts,
        tokens_in=agent_result.tokens_in,
        tokens_out=agent_result.tokens_out,
        target_path=str(target_path.relative_to(repo_root)),
        duration_ms=duration_ms,
    )

    return DispatchResult(
        specialist_name=specialist_name,
        target_path=target_path,
        agent_result=agent_result,
        attempts=actual_attempts,
        outcome="success",
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

    Delegates to ``_run_member`` with target_kind="primary".
    Per-attempt journal entries are written via the ``on_attempt`` hook in
    ``with_retries``; ``artifact_written`` is written on success only.
    """
    return await _run_member(
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


async def dispatch_panel(
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

    Parallel agents run through a BoundedDispatcher capped at ``max_parallel_agents``.
    Synthesizer runs only if all panel members succeed; it receives ``panel_outputs``
    containing the text output of every panel member.

    On any DispatchError the panel short-circuits and returns outcome="failed";
    the synthesizer is never dispatched on failure (AC2.5).

    # EPIC-4-STOP-TRIGGER-WIRE: on terminal failure, a kind="stop_trigger_raised"
    # journal entry should be emitted here. Deferred — see deferred-work.md.
    """
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

    def _failed_primary() -> PanelResult:
        wg = step.write_globs.get(step.primary_agent, ())
        tp = (repo_root / wg[0]).resolve() if wg else repo_root / "unknown.md"
        return PanelResult(
            primary_result=DispatchResult(
                specialist_name=step.primary_agent,
                target_path=tp,
                agent_result=AgentResult(output_text="", tokens_in=0, tokens_out=0),
                attempts=1,
                outcome="failed",
            ),
            parallel_results=(),
            synthesizer_result=None,
            write_targets=(),
            total_attempts=1,
            outcome="failed",
        )

    # Phase 1 — primary (sequential)
    try:
        primary_result = await _run_member(step, step.primary_agent, "primary", **_kw)  # type: ignore[arg-type]
    except DispatchError:
        return _failed_primary()

    # Phase 2 — parallel agents (concurrent, semaphore-bounded)
    parallel_results: tuple[DispatchResult, ...] = ()
    if step.parallel_agents:
        bd = BoundedDispatcher(max_parallel_agents)
        coros = [
            _run_member(step, name, "parallel", **_kw)  # type: ignore[arg-type]
            for name in step.parallel_agents
        ]
        try:
            raw = await bd.dispatch_many(coros)
            parallel_results = tuple(raw)
        except DispatchError:
            return PanelResult(
                primary_result=primary_result,
                parallel_results=(),
                synthesizer_result=None,
                write_targets=(primary_result.target_path,),
                total_attempts=primary_result.attempts + 1,
                outcome="failed",
            )

    # Phase 3 — synthesizer (sequential, after all panel members succeed)
    synth_result: DispatchResult | None = None
    if step.synthesizer_agent:
        panel_outputs: dict[str, object] = {
            r.specialist_name: r.agent_result.output_text
            for r in (primary_result, *parallel_results)
        }
        try:
            synth_result = await _run_member(
                step,
                step.synthesizer_agent,
                "synthesizer",
                extra_context={"panel_outputs": panel_outputs},
                **_kw,  # type: ignore[arg-type]
            )
        except DispatchError:
            return PanelResult(
                primary_result=primary_result,
                parallel_results=parallel_results,
                synthesizer_result=None,
                write_targets=tuple(
                    r.target_path for r in (primary_result, *parallel_results)
                ),
                total_attempts=sum(
                    r.attempts for r in (primary_result, *parallel_results)
                ) + 1,
                outcome="failed",
            )

    all_results = [primary_result, *parallel_results, *([synth_result] if synth_result else [])]
    return PanelResult(
        primary_result=primary_result,
        parallel_results=parallel_results,
        synthesizer_result=synth_result,
        write_targets=tuple(r.target_path for r in all_results),
        total_attempts=sum(r.attempts for r in all_results),
        outcome="success",
    )


__all__: tuple[str, ...] = (
    "dispatch",
    "dispatch_panel",
    "DispatchResult",
    "PanelResult",
    "_default_prompt_builder",
)
