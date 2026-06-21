"""STOP trigger 6 — high-risk path detected (Story 4.7)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sdlc.dispatcher.safety import (
    build_high_risk_reason,
    extract_destructive_target,
    is_destructive,
)
from sdlc.engine.stop_triggers import StopDecision
from sdlc.errors import JournalError
from sdlc.journal import JournalEntry, iter_entries
from sdlc.state.model import State

_JOURNAL_REL = ".claude/state/journal.log"
_REJECTED_KIND = "destructive_op_rejected"
_CONFIRMED_KIND = "high_risk_confirmed"
_AUTO_LOOP_HALT_KEY = "auto_loop_halt"
_TOOL_CALL_ID_KEY = "tool_call_id"


def evaluate_queued_tool_call(tool_call: Mapping[str, object]) -> StopDecision | None:
    """Classify a queued tool call — mirrors the dispatcher pre-execution gate."""
    flagged, category = is_destructive(tool_call)
    if not flagged or category is None:
        return None
    tool_name = tool_call.get("name")
    tool = tool_name if isinstance(tool_name, str) else "unknown"
    excerpt = str(tool_call.get("command", ""))
    target = extract_destructive_target(tool_call, category)
    return StopDecision(
        fired=True,
        trigger="high_risk_path",
        target=target,
        reason=build_high_risk_reason(tool=tool, category=category, excerpt=excerpt),
    )


def _confirmed_tool_call_ids(entries: list[JournalEntry]) -> set[str]:
    confirmed: set[str] = set()
    for entry in entries:
        if entry.kind != _CONFIRMED_KIND:
            continue
        tool_call_id = entry.payload.get(_TOOL_CALL_ID_KEY)
        if isinstance(tool_call_id, str):
            confirmed.add(tool_call_id)
    return confirmed


def _select_active_block(
    entries: list[JournalEntry], *, confirmed: set[str]
) -> JournalEntry | None:
    best: JournalEntry | None = None
    for entry in entries:
        if entry.kind != _REJECTED_KIND:
            continue
        payload = entry.payload
        if payload.get(_AUTO_LOOP_HALT_KEY) is not True:
            continue
        tool_call_id = payload.get(_TOOL_CALL_ID_KEY)
        if not isinstance(tool_call_id, str) or tool_call_id in confirmed:
            continue
        if best is None or entry.monotonic_seq > best.monotonic_seq:
            best = entry
    return best


class HighRiskPathTrigger:
    """Detect auto-loop high-risk tool calls blocked by the dispatcher pre-execution gate."""

    trigger_id = "high_risk_path"

    def check(self, *, repo_root: Path, state: State) -> StopDecision:
        _ = state
        journal_path = repo_root / _JOURNAL_REL
        if not journal_path.is_file():
            return StopDecision(fired=False)

        try:
            entries = list(iter_entries(journal_path))
        except JournalError:
            return StopDecision(fired=False)

        confirmed = _confirmed_tool_call_ids(entries)
        blocked = _select_active_block(entries, confirmed=confirmed)
        if blocked is None:
            return StopDecision(fired=False)

        payload = blocked.payload
        target_val = payload.get("target")
        target = target_val if isinstance(target_val, str) else blocked.target_id
        tool_val = payload.get("tool")
        category_val = payload.get("category")
        excerpt_val = payload.get("tool_call_excerpt")
        tool = tool_val if isinstance(tool_val, str) else "unknown"
        category = category_val if isinstance(category_val, str) else "unknown"
        excerpt = excerpt_val if isinstance(excerpt_val, str) else ""
        return StopDecision(
            fired=True,
            trigger=self.trigger_id,
            target=target,
            reason=build_high_risk_reason(tool=tool, category=category, excerpt=excerpt),
        )
