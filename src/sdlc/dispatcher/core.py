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
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.concurrency import BoundedDispatcher
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import DispatchError
from sdlc.journal import append as _journal_append
from sdlc.runtime.abc import AgentResult, AIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

DispatchOutcome = Literal["success", "failed"]


@dataclass(frozen=True)
class DispatchResult:
    """Result of a single specialist dispatch (AC1)."""

    specialist_name: str
    target_path: str
    agent_result: AgentResult
    attempts: int
    outcome: DispatchOutcome


@dataclass(frozen=True)
class PanelResult:
    """Result of a panel dispatch (primary + parallel + optional synthesizer) (AC2)."""

    primary_result: DispatchResult
    parallel_results: tuple[DispatchResult, ...]
    synthesizer_result: DispatchResult | None
    write_targets: tuple[str, ...]
    total_attempts: int
    outcome: DispatchOutcome


def _default_prompt_builder(specialist: Specialist, step: WorkflowSpec) -> str:
    """Scaffold prompt builder: returns specialist body (Story 2A.8 will replace)."""
    return specialist.body


def _build_journal_entry(
    kind: str,
    payload: dict[str, object],
    seq: int,
    actor: str,
    target_id: str,
) -> JournalEntry:
    return JournalEntry(
        monotonic_seq=seq,
        ts=now_rfc3339_utc_ms(),
        actor=actor,
        kind=kind,
        target_id=target_id,
        before_hash=None,
        after_hash="sha256:" + "0" * 64,
        payload=payload,
    )


async def _write_artifact(
    content: str,
    target_path: Path,
    repo_root: Path,
) -> None:
    """Write a text artifact to disk.

    Uses a simple async write (via asyncio.to_thread) since state.atomic
    is JSON-canonicalized and unsuitable for raw markdown text (AC8 escape hatch).
    Debt ticket: EPIC-2A-DEBT-WRITE-PRIMITIVE — replace with a proper raw-text
    atomic write primitive when one is available.
    """
    abs_path = repo_root / target_path if not Path(target_path).is_absolute() else Path(target_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(abs_path.write_text, content, "utf-8")


async def _dispatch_single(
    specialist: Specialist,
    step: WorkflowSpec,
    target_kind: Literal["primary", "parallel", "synthesizer"],
    runtime: AIRuntime,
    repo_root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    seq_counter: list[int],
    prompt_builder: Callable[[Specialist, WorkflowSpec], str],
    sleep: Callable[[float], "asyncio.coroutines.CoroType[None]"] | None = None,
    panel_outputs: dict[str, str] | None = None,
) -> DispatchResult:
    """Dispatch one specialist; write artifact; record telemetry + journal.

    ``seq_counter`` is a shared mutable list[int] so callers can hand a
    reference without Python's lack of pass-by-reference for ints.
    """
    from sdlc.dispatcher.retry import with_retries
    from sdlc.telemetry.runs import record_agent_run

    import time

    specialist_name = specialist.frontmatter.name
    target_glob_list = step.write_globs.get(specialist_name)
    if not target_glob_list:
        raise DispatchError(
            f"workflow step {step.name!r} has no write_globs entry for specialist"
            f" {specialist_name!r}",
            details={"specialist": specialist_name, "step": step.name},
        )
    target_path_str = target_glob_list[0]

    # Build context dict for dispatch.
    context: dict[str, object] = {
        "workflow_step": step.name,
        "agent_name": specialist_name,
        "target_kind": target_kind,
    }
    if panel_outputs is not None:
        context["panel_outputs"] = dict(panel_outputs)

    prompt = prompt_builder(specialist, step)
    attempts = 0
    start_ms = int(time.monotonic() * 1000)

    async def _attempt() -> AgentResult:
        nonlocal attempts
        attempts += 1
        seq = seq_counter[0]
        seq_counter[0] += 1
        await _journal_append(
            _build_journal_entry(
                kind="dispatch_attempt",
                payload={
                    "specialist": specialist_name,
                    "outcome": "retry" if attempts > 1 else "pending",
                    "attempt": attempts,
                    "target_kind": target_kind,
                },
                seq=seq,
                actor="dispatcher",
                target_id=step.name,
            ),
            journal_path,
        )
        return await runtime.dispatch(prompt, context)

    import asyncio as _asyncio

    _sleep = sleep if sleep is not None else _asyncio.sleep

    try:
        agent_result = await with_retries(
            _attempt,
            sleep=_sleep,
        )
    except DispatchError as exc:
        # Terminal failure — record STOP-trigger placeholder (AC5).
        seq = seq_counter[0]
        seq_counter[0] += 1
        await _journal_append(
            _build_journal_entry(
                kind="dispatch_attempt",
                payload={
                    "specialist": specialist_name,
                    "outcome": "failed",
                    "attempt": attempts,
                    "target_kind": target_kind,
                },
                seq=seq,
                actor="dispatcher",
                target_id=step.name,
            ),
            journal_path,
        )
        seq = seq_counter[0]
        seq_counter[0] += 1
        await _journal_append(
            _build_journal_entry(
                kind="stop_trigger_raised",
                payload={
                    "trigger": "agent_failure_after_retries",
                    "specialist": specialist_name,
                    "step": step.name,
                    "epic_4_placeholder": True,  # TODO(epic-4)
                },
                seq=seq,
                actor="dispatcher",
                target_id=step.name,
            ),
            journal_path,
        )
        raise

    duration_ms = int(time.monotonic() * 1000) - start_ms

    # Write artifact (AC8).
    await _write_artifact(agent_result.output_text, Path(target_path_str), repo_root)

    # Record success journal entry (artifact_written).
    seq = seq_counter[0]
    seq_counter[0] += 1
    await _journal_append(
        _build_journal_entry(
            kind="artifact_written",
            payload={
                "target": target_path_str,
                "writer": "dispatcher",
                "specialist": specialist_name,
            },
            seq=seq,
            actor="dispatcher",
            target_id=step.name,
        ),
        journal_path,
    )

    # Overwrite the dispatch_attempt entry outcome to "success" in telemetry.
    await record_agent_run(
        agent_runs_path,
        run_id=str(uuid.uuid4()),
        ts=now_rfc3339_utc_ms(),
        workflow_step=step.name,
        specialist_name=specialist_name,
        target_kind=target_kind,
        outcome="success",
        attempts=attempts,
        tokens_in=agent_result.tokens_in,
        tokens_out=agent_result.tokens_out,
        target_path=target_path_str,
        duration_ms=duration_ms,
    )

    return DispatchResult(
        specialist_name=specialist_name,
        target_path=target_path_str,
        agent_result=agent_result,
        attempts=attempts,
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
    sleep: Callable[[float], "asyncio.coroutines.CoroType[None]"] | None = None,
    _seq_start: int = 1,
) -> DispatchResult:
    """Dispatch the primary specialist for ``step`` (AC1, FR25, NFR-OBS-2).

    Resolves the primary specialist via registry, awaits runtime dispatch,
    writes the output artifact, records telemetry and journal entries.

    Raises:
        SpecialistError: if the primary specialist is not in the registry.
        DispatchError: after retry exhaustion or write target missing.
    """
    specialist = registry.get(step.primary_agent)
    seq_counter = [_seq_start]
    return await _dispatch_single(
        specialist=specialist,
        step=step,
        target_kind="primary",
        runtime=runtime,
        repo_root=repo_root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        seq_counter=seq_counter,
        prompt_builder=prompt_builder,
        sleep=sleep,
    )


async def dispatch_panel(
    step: WorkflowSpec,
    *,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    repo_root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    max_parallel_agents: int = 4,
    prompt_builder: Callable[[Specialist, WorkflowSpec], str] = _default_prompt_builder,
    sleep: Callable[[float], "asyncio.coroutines.CoroType[None]"] | None = None,
    _seq_start: int = 1,
) -> PanelResult:
    """Dispatch primary + parallel specialists, then optional synthesizer (AC2, FR25-FR26).

    All specialists are resolved upfront (atomic fail-fast on first miss).
    Panel members run concurrently up to ``max_parallel_agents``.
    Synthesizer is dispatched AFTER the panel completes (FR26).
    If any panel member fails, the entire panel outcome is "failed" and the
    synthesizer is NOT dispatched.

    Raises:
        SpecialistError: if any specialist is not in the registry (propagated as-is).
        DispatchError: after retry exhaustion for a panel member.
    """
    seq_counter = [_seq_start]

    # Resolve all specialists upfront (atomic fail-fast on first miss).
    primary_spec = registry.get(step.primary_agent)
    parallel_specs = [registry.get(name) for name in step.parallel_agents]
    synth_spec = registry.get(step.synthesizer_agent) if step.synthesizer_agent else None

    # Build panel member coroutines.
    all_panel_specs: list[tuple[Specialist, Literal["primary", "parallel"]]] = [
        (primary_spec, "primary"),
        *[(s, "parallel") for s in parallel_specs],
    ]

    import asyncio as _asyncio

    bounded = BoundedDispatcher(semaphore_size=max_parallel_agents)

    async def _dispatch_member(
        spec: Specialist,
        kind: Literal["primary", "parallel"],
    ) -> DispatchResult:
        return await _dispatch_single(
            specialist=spec,
            step=step,
            target_kind=kind,
            runtime=runtime,
            repo_root=repo_root,
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
            seq_counter=seq_counter,
            prompt_builder=prompt_builder,
            sleep=sleep,
        )

    coros = [_dispatch_member(spec, kind) for spec, kind in all_panel_specs]

    try:
        panel_results: list[DispatchResult] = await bounded.dispatch_many(coros)
    except DispatchError:
        # Panel member failed — return failed PanelResult; synthesizer NOT dispatched.
        return PanelResult(
            primary_result=DispatchResult(
                specialist_name=primary_spec.frontmatter.name,
                target_path="",
                agent_result=AgentResult(output_text="", tokens_in=0, tokens_out=0),
                attempts=0,
                outcome="failed",
            ),
            parallel_results=(),
            synthesizer_result=None,
            write_targets=(),
            total_attempts=0,
            outcome="failed",
        )

    primary_result = panel_results[0]
    parallel_results = tuple(panel_results[1:])

    # Collect per-member outputs for synthesizer context.
    panel_outputs: dict[str, str] = {}
    for result in panel_results:
        panel_outputs[result.specialist_name] = result.agent_result.output_text

    # Dispatch synthesizer if present (FR26).
    synth_result: DispatchResult | None = None
    if synth_spec is not None:
        synth_result = await _dispatch_single(
            specialist=synth_spec,
            step=step,
            target_kind="synthesizer",
            runtime=runtime,
            repo_root=repo_root,
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
            seq_counter=seq_counter,
            prompt_builder=prompt_builder,
            sleep=sleep,
            panel_outputs=panel_outputs,
        )

    all_results = panel_results + ([synth_result] if synth_result else [])
    total_attempts = sum(r.attempts for r in all_results)
    write_targets = tuple(r.target_path for r in all_results)

    return PanelResult(
        primary_result=primary_result,
        parallel_results=parallel_results,
        synthesizer_result=synth_result,
        write_targets=write_targets,
        total_attempts=total_attempts,
        outcome="success",
    )


__all__ = [
    "dispatch",
    "dispatch_panel",
    "DispatchResult",
    "PanelResult",
    "DispatchOutcome",
    "_default_prompt_builder",
]
