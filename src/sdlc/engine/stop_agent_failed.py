"""STOP trigger 5 — agent failure after retries (Story 4.6)."""

from __future__ import annotations

from pathlib import Path

from sdlc.engine.stop_triggers import StopDecision
from sdlc.errors import JournalError
from sdlc.journal import JournalEntry, iter_entries
from sdlc.state.model import State

_JOURNAL_REL = ".claude/state/journal.log"
_STOP_RAISED_KIND = "stop_trigger_raised"
_DISPATCH_ATTEMPT_KIND = "dispatch_attempt"
_RUNS_REL = "03-Implementation/agent_runs.jsonl"
_MAX_REASON_ERROR_LEN = 200
_DEFAULT_ATTEMPTS = 3
_PLACEHOLDER_TRIGGER = "agent_failure_after_retries"


def _truncate_error(msg: str, *, max_len: int = _MAX_REASON_ERROR_LEN) -> str:
    if len(msg) <= max_len:
        return msg
    return msg[: max_len - 3] + "..."


def _build_reason(*, specialist: str, attempts: int, last_error: str | None) -> str:
    parts = [f"agent={specialist}", f"attempts={attempts}"]
    if last_error is not None:
        parts.append(f"last_error={_truncate_error(last_error)}")
    parts.append(f"debug={_RUNS_REL}")
    return " ".join(parts)


def _attempt_count(entries: list[JournalEntry], *, target_id: str, raised_seq: int) -> int:
    attempts: list[int] = []
    for entry in entries:
        if entry.kind != _DISPATCH_ATTEMPT_KIND:
            continue
        if entry.target_id != target_id or entry.monotonic_seq > raised_seq:
            continue
        attempt_val = entry.payload.get("attempt")
        if isinstance(attempt_val, int):
            attempts.append(attempt_val)
    if not attempts:
        return _DEFAULT_ATTEMPTS
    return max(attempts)


def _collect_supersession_state(
    entries: list[JournalEntry],
) -> tuple[dict[str, int], dict[str, tuple[int, dict[str, object]]]]:
    last_success_seq: dict[str, int] = {}
    last_raised: dict[str, tuple[int, dict[str, object]]] = {}
    for entry in entries:
        target = entry.target_id
        if entry.kind == _DISPATCH_ATTEMPT_KIND:
            if entry.payload.get("outcome") == "success":
                last_success_seq[target] = entry.monotonic_seq
        elif (
            entry.kind == _STOP_RAISED_KIND and entry.payload.get("trigger") == _PLACEHOLDER_TRIGGER
        ):
            last_raised[target] = (entry.monotonic_seq, dict(entry.payload))
    return last_success_seq, last_raised


def _select_active_failure(
    last_success_seq: dict[str, int],
    last_raised: dict[str, tuple[int, dict[str, object]]],
) -> tuple[str | None, int, dict[str, object] | None]:
    best_target: str | None = None
    best_seq = -1
    best_payload: dict[str, object] | None = None
    for target, (raised_seq, payload) in last_raised.items():
        if raised_seq > last_success_seq.get(target, -1) and raised_seq > best_seq:
            best_seq = raised_seq
            best_target = target
            best_payload = payload
    return best_target, best_seq, best_payload


class AgentFailedTrigger:
    """Detect terminal agent failure from dispatcher ``stop_trigger_raised`` journal seam."""

    trigger_id = "agent_failed"

    def check(self, *, repo_root: Path, state: State) -> StopDecision:
        _ = state
        journal_path = repo_root / _JOURNAL_REL
        if not journal_path.is_file():
            return StopDecision(fired=False)

        try:
            entries = list(iter_entries(journal_path))
        except JournalError:
            # D-R2/P3: a corrupt (seq-regressed) or unreadable journal must never
            # crash the post-dispatch STOP check — fail open so the auto-loop keeps
            # running rather than aborting the iteration (NFR-REL). The reader still
            # surfaces the corruption loudly to other consumers (projection).
            return StopDecision(fired=False)
        last_success_seq, last_raised = _collect_supersession_state(entries)
        best_target, best_seq, best_payload = _select_active_failure(last_success_seq, last_raised)
        if best_target is None or best_payload is None:
            return StopDecision(fired=False)

        specialist_val = best_payload.get("specialist")
        specialist = (
            specialist_val
            if isinstance(specialist_val, str)
            else best_target.rsplit("/", maxsplit=1)[-1]
        )
        last_error_val = best_payload.get("last_error")
        last_error = last_error_val if isinstance(last_error_val, str) else None
        attempts = _attempt_count(entries, target_id=best_target, raised_seq=best_seq)

        return StopDecision(
            fired=True,
            trigger=self.trigger_id,
            target=best_target,
            reason=_build_reason(specialist=specialist, attempts=attempts, last_error=last_error),
        )
