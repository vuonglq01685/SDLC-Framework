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

    Writes output to ``step.write_globs[primary_agent][0]`` relative to ``repo_root``.
    Appends ``dispatch_attempt`` + ``artifact_written`` journal entries and one
    ``agent_runs.jsonl`` line.

    # EPIC-2A-DEBT-WRITE-PRIMITIVE: output write uses Path.write_text() (plain).
    # write_state_raw_atomic_sync is JSON-only and POSIX-only; a raw-text atomic
    # primitive is needed for arbitrary specialist artifacts. Deferred to Epic 2B.
    """
    specialist = registry.get(step.primary_agent)

    write_globs = step.write_globs.get(step.primary_agent)
    if not write_globs:
        raise DispatchError(
            f"workflow step {step.name!r} has no write_globs entry for specialist"
            f" {step.primary_agent!r}",
            details={"step": step.name, "specialist": step.primary_agent},
        )
    target_path = (repo_root / write_globs[0]).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = prompt_builder(specialist, step)
    context: dict[str, object] = {
        "workflow_step": step.name,
        "agent_name": step.primary_agent,
        "target_kind": "primary",
    }

    t_start = time.monotonic()
    agent_result = await with_retries(
        lambda: runtime.dispatch(prompt, context),
        max_attempts=_max_attempts,
        sleep=sleep,
    )
    duration_ms = int((time.monotonic() - t_start) * 1000)
    ts = _now_ts()
    run_id = str(uuid.uuid4())

    # Write artifact — plain write (see EPIC-2A-DEBT-WRITE-PRIMITIVE above).
    target_path.write_text(agent_result.output_text, encoding="utf-8")

    # Journal: dispatch_attempt
    await journal_append(
        _make_journal_entry(
            seq=0,
            ts=ts,
            kind="dispatch_attempt",
            target_id=f"{step.name}/{step.primary_agent}",
            payload={
                "specialist": step.primary_agent,
                "outcome": "success",
                "attempt": 1,
                "target_kind": "primary",
            },
        ),
        journal_path,
    )

    # Journal: artifact_written
    await journal_append(
        _make_journal_entry(
            seq=1,
            ts=ts,
            kind="artifact_written",
            target_id=str(target_path.relative_to(repo_root)),
            payload={
                "target": str(target_path.relative_to(repo_root)),
                "writer": "dispatcher",
                "specialist": step.primary_agent,
            },
        ),
        journal_path,
    )

    # Telemetry
    record_agent_run(
        agent_runs_path,
        run_id=run_id,
        ts=ts,
        workflow_step=step.name,
        specialist_name=step.primary_agent,
        target_kind="primary",
        outcome="success",
        attempts=1,
        tokens_in=agent_result.tokens_in,
        tokens_out=agent_result.tokens_out,
        target_path=str(target_path.relative_to(repo_root)),
        duration_ms=duration_ms,
    )

    return DispatchResult(
        specialist_name=step.primary_agent,
        target_path=target_path,
        agent_result=agent_result,
        attempts=1,
        outcome="success",
    )


__all__: tuple[str, ...] = (
    "dispatch",
    "DispatchResult",
    "PanelResult",
    "_default_prompt_builder",
)
