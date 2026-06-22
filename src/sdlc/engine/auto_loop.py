"""Auto-loop orchestrator — pure function of disk state (Story 4.1)."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sdlc.dispatcher import DispatchResult
from sdlc.engine.auto_brainstorm import detect_ambiguity_signal, run_auto_brainstorm
from sdlc.engine.next_selector import resolve_next_action
from sdlc.engine.scanner import scan
from sdlc.engine.stop_triggers import StopDecision, check_stop
from sdlc.engine.watchdog import make_watchdog_stop_decision, watchdog_deadline_exceeded
from sdlc.ids.clock import now_rfc3339_utc_ms
from sdlc.journal import JournalEntry, append_with_seq_alloc, iter_entries
from sdlc.runtime import AIRuntime
from sdlc.specialists.registry import SpecialistRegistry

_ACTOR: Final[str] = "auto_loop"
_EVENT_SENTINEL: Final[str] = "sha256:" + "0" * 64

DispatchFn = Callable[..., Awaitable[DispatchResult | None]]


@dataclass(frozen=True)
class AutoLoopResult:
    iterations: int
    last_action: str
    halted: bool
    stop_reason: str | None = None


def _make_iteration_entry(
    seq: int,
    *,
    iteration_seq: int,
    action: str,
    correlation_id: str,
    task_id: str | None = None,
    reason: str | None = None,
) -> JournalEntry:
    payload: dict[str, object] = {
        "iteration_seq": iteration_seq,
        "action": action,
        "correlation_id": correlation_id,
    }
    if task_id is not None:
        payload["task_id"] = task_id
    if reason is not None:
        payload["reason"] = reason
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=now_rfc3339_utc_ms(),
        actor=_ACTOR,
        kind="auto_loop_iteration",
        target_id=f"auto-loop-iter-{iteration_seq}",
        before_hash=None,
        after_hash=_EVENT_SENTINEL,
        payload=payload,
    )


async def _append_iteration(
    journal_path: Path,
    *,
    iteration_seq: int,
    action: str,
    correlation_id: str,
    task_id: str | None = None,
    reason: str | None = None,
) -> int:
    return await append_with_seq_alloc(
        journal_path,
        lambda seq: _make_iteration_entry(
            seq,
            iteration_seq=iteration_seq,
            action=action,
            correlation_id=correlation_id,
            task_id=task_id,
            reason=reason,
        ),
    )


def _last_iteration_seq(journal_path: Path) -> int:
    """Highest ``iteration_seq`` already on disk (0 if none).

    Resume anchor (code-review P2): the loop's iteration counter is re-derived from the
    journal on every start, so a crash-resume continues the numbering instead of restarting
    at 1 and colliding `target_id="auto-loop-iter-N"` with a prior run. This is a *disk read*,
    not carried Python state, so it preserves the pure-function-of-disk invariant (A4).
    """
    last = 0
    for entry in iter_entries(journal_path):
        if entry.kind == "auto_loop_iteration":
            seq = entry.payload.get("iteration_seq")
            if isinstance(seq, int) and seq > last:
                last = seq
    return last


def _make_stop_triggered_entry(
    seq: int,
    *,
    trigger: str,
    target: str,
    correlation_id: str,
    reason: str | None = None,
) -> JournalEntry:
    payload: dict[str, object] = {
        "trigger": trigger,
        "target": target,
        "correlation_id": correlation_id,
    }
    if reason is not None:
        payload["reason"] = reason
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=now_rfc3339_utc_ms(),
        actor=_ACTOR,
        kind="stop_triggered",
        target_id=trigger,
        before_hash=None,
        after_hash=_EVENT_SENTINEL,
        payload=payload,
    )


async def _append_stop_triggered(
    journal_path: Path,
    *,
    trigger: str,
    target: str,
    correlation_id: str,
    reason: str | None = None,
) -> int:
    return await append_with_seq_alloc(
        journal_path,
        lambda seq: _make_stop_triggered_entry(
            seq,
            trigger=trigger,
            target=target,
            correlation_id=correlation_id,
            reason=reason,
        ),
    )


async def _finish_halted_on_stop_trigger(
    *,
    journal_path: Path,
    state_path: Path | None,
    iteration_seq: int,
    correlation_id: str,
    stop: StopDecision,
    last_action: str = "dispatch",
) -> AutoLoopResult:
    trigger = stop.trigger or "unknown"
    target = stop.target or ""
    await _append_stop_triggered(
        journal_path,
        trigger=trigger,
        target=target,
        correlation_id=correlation_id,
        reason=stop.reason,
    )
    if state_path is not None:
        await _rebuild_state(journal_path, state_path)
    return AutoLoopResult(
        iterations=iteration_seq,
        last_action=last_action,
        halted=True,
        stop_reason=trigger,
    )


async def _finish_stopped(
    *,
    journal_path: Path,
    state_path: Path | None,
    iteration_seq: int,
    correlation_id: str,
    reason: str,
    halted: bool,
    last_action: str = "stopped",
    task_id: str | None = None,
) -> AutoLoopResult:
    await _append_iteration(
        journal_path,
        iteration_seq=iteration_seq,
        action="stopped",
        correlation_id=correlation_id,
        task_id=task_id,
        reason=reason,
    )
    if state_path is not None:
        await _rebuild_state(journal_path, state_path)
    return AutoLoopResult(
        iterations=iteration_seq,
        last_action=last_action,
        halted=halted,
        stop_reason=reason,
    )


async def _maybe_run_auto_brainstorm_on_ambiguity(
    *,
    repo_root: Path,
    task_id: str,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    journal_path: Path,
    agent_runs_path: Path,
    correlation_id: str,
    auto_brainstorm: bool,
) -> None:
    ambiguity = detect_ambiguity_signal(repo_root, task_id=task_id)
    if ambiguity is None:
        return
    await run_auto_brainstorm(
        repo_root,
        context=ambiguity,
        runtime=runtime,
        registry=registry,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        correlation_id=correlation_id,
        auto_brainstorm=auto_brainstorm,
    )


async def run_auto_loop(
    repo_root: Path,
    *,
    journal_path: Path,
    agent_runs_path: Path,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    dispatch_fn: DispatchFn,
    state_path: Path | None = None,
    max_iterations: int | None = None,
    watchdog_timeout_minutes: float | None = None,
    auto_brainstorm: bool = True,
) -> AutoLoopResult:
    """Run scan → dispatch → STOP-check iterations until halt or max_iterations."""
    # Resume anchor: seed the iteration counter from disk (P2), not from 0.
    iteration_seq = _last_iteration_seq(journal_path)
    last_action = "stopped"
    iterations_this_run = 0
    start_monotonic = time.monotonic()
    repo_root_str = str(repo_root)

    while max_iterations is None or iterations_this_run < max_iterations:
        iteration_seq += 1
        iterations_this_run += 1
        correlation_id = str(uuid.uuid4())

        # Single disk scan per iteration (AC1 "scan" step + the AFTER_SCAN crash kill anchor).
        # Reused for the post-dispatch STOP check below (P5): 4.1's STOP registry is empty so
        # the pre/post-dispatch snapshot timing is immaterial; a Layer-2 trigger that needs the
        # post-dispatch snapshot must re-scan inside its own ``check()``.
        state = scan(repo_root)
        decision = resolve_next_action(repo_root)

        if decision.kind != "dispatch_task":
            reason = decision.reason or decision.command or "no ready item"
            return await _finish_stopped(
                journal_path=journal_path,
                state_path=state_path,
                iteration_seq=iteration_seq,
                correlation_id=correlation_id,
                reason=reason,
                halted=False,
            )

        task_id = decision.task_id
        if task_id is None:
            return await _finish_stopped(
                journal_path=journal_path,
                state_path=state_path,
                iteration_seq=iteration_seq,
                correlation_id=correlation_id,
                reason="internal: dispatch_task missing task_id",
                halted=False,
            )

        # Intent-anchor (code-review D2): record the iteration BEFORE the dispatch side-effect
        # so a crash mid-dispatch still leaves a durable, replayable iteration record (NFR-REL-5).
        # On resume the loop re-reads disk and either re-dispatches an unadvanced task idempotently
        # or skips one the dispatch already advanced — never silently losing the iteration record.
        await _append_iteration(
            journal_path,
            iteration_seq=iteration_seq,
            action="dispatch",
            correlation_id=correlation_id,
            task_id=task_id,
        )
        last_action = "dispatch"
        if state_path is not None:
            await _rebuild_state(journal_path, state_path)

        await dispatch_fn(
            task_id=task_id,
            repo_root=repo_root,
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
            runtime=runtime,
            registry=registry,
            correlation_id=correlation_id,
        )

        if watchdog_timeout_minutes is not None:
            now_monotonic = time.monotonic()
            if watchdog_deadline_exceeded(
                start_monotonic,
                now_monotonic=now_monotonic,
                timeout_minutes=watchdog_timeout_minutes,
            ):
                elapsed_minutes = (now_monotonic - start_monotonic) / 60.0
                return await _finish_halted_on_stop_trigger(
                    journal_path=journal_path,
                    state_path=state_path,
                    iteration_seq=iteration_seq,
                    correlation_id=correlation_id,
                    stop=make_watchdog_stop_decision(
                        repo_root_str, elapsed_minutes=elapsed_minutes
                    ),
                    last_action="dispatch",
                )

        await _maybe_run_auto_brainstorm_on_ambiguity(
            repo_root=repo_root,
            task_id=task_id,
            runtime=runtime,
            registry=registry,
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
            correlation_id=correlation_id,
            auto_brainstorm=auto_brainstorm,
        )

        stop = check_stop(repo_root=repo_root, state=state)
        if stop.fired:
            return await _finish_halted_on_stop_trigger(
                journal_path=journal_path,
                state_path=state_path,
                iteration_seq=iteration_seq,
                correlation_id=correlation_id,
                stop=stop,
                last_action="dispatch",
            )

    # Bounded exit (max_iterations reached): write a terminal "stopped" marker (P3) so the
    # journal-derived auto_loop_status settles to "idle" instead of latching "running". The
    # returned last_action still reflects the real final action (e.g. "dispatch").
    return await _finish_stopped(
        journal_path=journal_path,
        state_path=state_path,
        iteration_seq=iteration_seq,
        correlation_id=str(uuid.uuid4()),
        reason="max_iterations reached",
        halted=False,
        last_action=last_action,
    )


async def _rebuild_state(journal_path: Path, state_path: Path) -> None:
    from sdlc.state.rebuild import rebuild_state_from_journal  # noqa: PLC0415

    await asyncio.to_thread(rebuild_state_from_journal, journal_path, state_path)
