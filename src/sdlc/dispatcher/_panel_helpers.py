"""Private panel-orchestration helpers for dispatcher.core (AC6 LOC discipline, DR2).

Houses ``_run_member`` (single-specialist dispatch), ``_emit_stop_trigger`` (AC5 placeholder),
``_make_journal_entry``, ``_now_ts``, ``_default_prompt_builder``, and the process-local
monotonic_seq allocator that fixes panel-dispatch journal regression (P1).

Architecture §821-§824, §1067; ADR-013, ADR-014, ADR-016, ADR-024, ADR-026.

# EPIC-2A-DEBT-WRITE-PRIMITIVE: ``Path.write_text()`` used directly in ``_run_member``.
# ``state.atomic.write_state_raw_atomic_sync`` is JSON-only + POSIX-only; a raw-text
# atomic primitive is needed for arbitrary specialist artifacts. Deferred to Epic 2B.

# EPIC-2A-DEBT-SHARED-TIME: ``_now_ts`` duplicates ``cli/_time.py:now_rfc3339_utc_ms``.
# Boundary §1106 forbids ``cli/`` import here. Deferred to shared-util follow-up.

# v1 monotonic_seq allocator is process-local: dispatcher is single-process per AC1.
# Cross-process journal coordination (Epic 2B + ClaudeAIRuntime) requires a journal
# API like ``append_with_seq_alloc`` — out of 2A.3 scope.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.retry import with_retries
from sdlc.errors import DispatchError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import BypassRequest, HookDecision, run_hook_chain
from sdlc.journal import append as journal_append
from sdlc.journal._seq import _read_highest_seq
from sdlc.runtime import AgentResult, AIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.telemetry.runs import record_agent_run

_ACTOR = "dispatcher"
# Sentinel hash for non-state-mutation journal entries (dispatch_attempt, stop_trigger_raised).
# JournalEntry.after_hash is sha256-pattern non-null (Story 1.7); a real hash is meaningless
# for "attempted dispatch" events. EPIC-2A-DEBT-JOURNAL-NULL-AFTER-HASH tracks lifting this
# constraint for non-mutation kinds (Epic 2B).
_NULL_HASH = "sha256:" + "0" * 64


def _content_hash(text: str) -> str:
    """SHA-256 of an artifact's text payload (used by artifact_written entries)."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DispatchMemberResult:
    """Result of a single panel-member dispatch (mirrors public DispatchResult shape)."""

    specialist_name: str
    target_path: Path
    agent_result: AgentResult
    attempts: int
    outcome: Literal["success", "failed", "hook_rejected"]


def _now_ts() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


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
    after_hash: str = _NULL_HASH,
) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=_ACTOR,
        kind=kind,
        target_id=target_id,
        before_hash=None,
        after_hash=after_hash,
        payload=payload,
    )


# Process-local seq allocator (P1 fix). Per-journal-path async lock + cached "next seq".
# Cache primed from disk on first use; advanced atomically per journal_append call.
# Cross-process correctness requires journal-side allocator (Epic 2B).
_SEQ_LOCKS: dict[Path, asyncio.Lock] = {}
_SEQ_CACHE: dict[Path, int] = {}
_SEQ_REGISTRY_LOCK = asyncio.Lock()


async def _allocate_seq(journal_path: Path) -> int:
    """Allocate next monotonic_seq for ``journal_path`` (process-local)."""
    async with _SEQ_REGISTRY_LOCK:
        lock = _SEQ_LOCKS.setdefault(journal_path, asyncio.Lock())
    async with lock:
        if journal_path not in _SEQ_CACHE:
            _SEQ_CACHE[journal_path] = await asyncio.to_thread(_read_highest_seq, journal_path)
        _SEQ_CACHE[journal_path] += 1
        return _SEQ_CACHE[journal_path]


def _reset_seq_cache_for_test(journal_path: Path | None = None) -> None:
    """Test-only hook: reset the process-local seq cache for a path (or all paths)."""
    if journal_path is None:
        _SEQ_CACHE.clear()
        _SEQ_LOCKS.clear()
    else:
        _SEQ_CACHE.pop(journal_path, None)
        _SEQ_LOCKS.pop(journal_path, None)


def _validate_target_path(repo_root: Path, raw_glob: str) -> Path:
    """Validate write target stays under ``repo_root`` and is concrete (no glob chars). P2 + P3."""
    if any(ch in raw_glob for ch in "*?["):
        raise DispatchError(
            f"write target {raw_glob!r} contains glob characters; expected concrete path (AC8)",
            details={"write_glob": raw_glob},
        )
    target_path = (repo_root / raw_glob).resolve()
    try:
        target_path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise DispatchError(
            f"write target {raw_glob!r} resolves outside repo_root {repo_root!s}",
            details={"write_glob": raw_glob, "resolved": str(target_path)},
        ) from exc
    return target_path


async def _emit_stop_trigger(
    specialist_name: str,
    step_name: str,
    journal_path: Path,
    *,
    last_error: str | None = None,
) -> None:
    """Append a stop_trigger_raised placeholder entry (AC5, TODO(epic-4))."""
    seq = await _allocate_seq(journal_path)
    payload: dict[str, object] = {
        "trigger": "agent_failure_after_retries",
        "specialist": specialist_name,
        "step": step_name,
        "epic_4_placeholder": True,
    }
    if last_error is not None:
        payload["last_error"] = last_error
    await journal_append(
        _make_journal_entry(
            seq=seq,
            ts=_now_ts(),
            kind="stop_trigger_raised",
            target_id=f"{step_name}/{specialist_name}",
            payload=payload,
        ),
        journal_path,
    )


async def _emit_hook_rejected(
    *,
    step: WorkflowSpec,
    specialist_name: str,
    target_kind: Literal["primary", "parallel", "synthesizer"],
    target_path: Path,
    journal_path: Path,
    decision: HookDecision,
) -> DispatchMemberResult:
    """Append dispatch_attempt(outcome=hook_rejected) and return without writing the file."""
    seq = await _allocate_seq(journal_path)
    await journal_append(
        _make_journal_entry(
            seq=seq,
            ts=_now_ts(),
            kind="dispatch_attempt",
            target_id=f"{step.name}/{specialist_name}",
            payload={
                "specialist": specialist_name,
                "outcome": "hook_rejected",
                "attempt": 0,
                "target_kind": target_kind,
                "hook_name": decision.hook_name,
                "error_code": decision.error_code,
            },
        ),
        journal_path,
    )
    return DispatchMemberResult(
        specialist_name=specialist_name,
        target_path=target_path,
        agent_result=AgentResult(output_text="", tokens_in=0, tokens_out=0),
        attempts=0,
        outcome="hook_rejected",
    )


async def _run_pre_write_hooks(
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
    target_path: Path,
    repo_root: Path,
    journal_path: Path,
    bypass: BypassRequest | None,
) -> HookDecision | None:
    """Run hook chain before write; return deny decision or None if allowed."""
    if not hooks:
        return None
    hook_payload = build_write_intent_payload(
        hook_name="pre_write",
        target_path=target_path.relative_to(repo_root.resolve()).as_posix(),
        write_intent="dispatcher_artifact_write",
    )
    decision = await run_hook_chain(
        hook_payload,
        hooks=hooks,
        journal_path=journal_path,
        bypass_phase_gate=bypass.bypass_phase_gate if bypass else False,
        justification=bypass.justification if bypass else None,
    )
    return decision if decision.decision == "deny" else None


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
    extra_journal_payload: dict[str, object] | None = None,
    target_path_override: Path | None = None,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...] = (),
    bypass: BypassRequest | None = None,
) -> DispatchMemberResult:
    """Dispatch a single specialist as a panel member (primary/parallel/synthesizer)."""
    specialist = registry.get(specialist_name)

    if target_path_override is not None:
        target_path = target_path_override
    else:
        write_globs = step.write_globs.get(specialist_name)
        if not write_globs:
            raise DispatchError(
                f"workflow step {step.name!r} has no write_globs entry for specialist"
                f" {specialist_name!r}",
                details={"step": step.name, "specialist": specialist_name},
            )
        target_path = _validate_target_path(repo_root, write_globs[0])
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
        seq = await _allocate_seq(journal_path)
        attempt_payload: dict[str, object] = {
            "specialist": specialist_name,
            "outcome": outcome,
            "attempt": attempt_num,
            "target_kind": target_kind,
        }
        if extra_journal_payload:
            attempt_payload.update(extra_journal_payload)
        await journal_append(
            _make_journal_entry(
                seq=seq,
                ts=_now_ts(),
                kind="dispatch_attempt",
                target_id=f"{step.name}/{specialist_name}",
                payload=attempt_payload,
            ),
            journal_path,
        )

    deny = await _run_pre_write_hooks(hooks, target_path, repo_root, journal_path, bypass)
    if deny is not None:
        return await _emit_hook_rejected(
            step=step,
            specialist_name=specialist_name,
            target_kind=target_kind,
            target_path=target_path,
            journal_path=journal_path,
            decision=deny,
        )

    t_start = time.monotonic()
    try:
        agent_result: AgentResult = await with_retries(
            lambda: runtime.dispatch(prompt, context),
            max_attempts=max_attempts,
            sleep=sleep,
            on_attempt=_on_attempt,
        )
    except DispatchError as exc:
        # P7: augment AC4 step 6 details with specialist (and step) at the dispatcher seam.
        details = dict(exc.details) if exc.details else {}
        details["specialist"] = specialist_name
        details["step"] = step.name
        raise DispatchError(str(exc), details=details) from exc

    duration_ms = int((time.monotonic() - t_start) * 1000)
    ts = _now_ts()
    run_id = str(uuid.uuid4())

    target_path.write_text(agent_result.output_text, encoding="utf-8")

    artifact_seq = await _allocate_seq(journal_path)
    rel_target = target_path.relative_to(repo_root.resolve()).as_posix()
    await journal_append(
        _make_journal_entry(
            seq=artifact_seq,
            ts=ts,
            kind="artifact_written",
            target_id=rel_target,
            payload={
                "target": rel_target,
                "writer": "dispatcher",
                "specialist": specialist_name,
                "run_id": run_id,
            },
            after_hash=_content_hash(agent_result.output_text),
        ),
        journal_path,
    )

    await asyncio.to_thread(
        record_agent_run,
        agent_runs_path,
        run_id=run_id,
        ts=ts,
        workflow_step=step.name,
        specialist_name=specialist_name,
        target_kind=target_kind,
        outcome="success",
        attempts=actual_attempts or 1,
        tokens_in=agent_result.tokens_in,
        tokens_out=agent_result.tokens_out,
        target_path=rel_target,
        duration_ms=duration_ms,
    )

    return DispatchMemberResult(
        specialist_name=specialist_name,
        target_path=target_path,
        agent_result=agent_result,
        attempts=actual_attempts or 1,
        outcome="success",
    )


__all__: tuple[str, ...] = (
    "DispatchMemberResult",
    "_allocate_seq",
    "_default_prompt_builder",
    "_emit_hook_rejected",
    "_emit_stop_trigger",
    "_make_journal_entry",
    "_now_ts",
    "_reset_seq_cache_for_test",
    "_run_member",
    "_validate_target_path",
)
