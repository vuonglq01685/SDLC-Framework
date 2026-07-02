"""``GET /api/signoff`` — real 4-state signoff read seam (Story 5.14 Task 1).

D1(a): a new internal/documentary read route mirroring ``register_dora_route``
[routes/dora.py]. Reads the REAL Story 2A.7 4-state machine through the
sanctioned ``signoff`` reader seam — ``compute_state`` / ``read_record`` —
never re-parsing ``.claude/state/signoffs/*.yaml`` directly and never folding
computed data into ``/state.json`` (that route streams the file byte-for-byte
with ETag-over-content [routes/state.py]). No ``StrictModel``, no
``tests/contract_snapshots/v1/`` snapshot -> freeze stays 7/7 (DAG Decision
D1 precedent for ``/api/dora``).

The wire ``state`` value is the ``SignoffState`` enum value verbatim (zero
translation table — the 5.9 ``signoff-cell.js SIGNOFF_STATES`` keys already
match 1:1). A malformed canonical record (``SignoffError`` from
``compute_state``) is NOT caught here: it propagates out of the handler
(fail-loud per AC1 RED spec), matching the "never silently demote" contract —
unlike ``/api/dora``'s graceful-on-malformed-input posture, a corrupted
signoff record is operator-actionable and must not read as a false
``awaiting-signoff``.

D2: the invalidated-by-replan click-through scope is read via the ``journal``
seam (``replan_invalidated`` payload), correlated to the phase's invalidation
by matching ``JournalEntry.ts`` to ``SignoffRecord.invalidated_at`` — both are
written from the same ``now_utc`` value in one ``sdlc replan`` invocation
[cli/replan_cmd.py]. Scope is never recomputed via ``engine.replan`` (module
boundary forbids ``dashboard -> engine``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from sdlc.dashboard.router import RequestContext, Response, Router
from sdlc.journal.reader import iter_entries
from sdlc.signoff.records import read_record
from sdlc.signoff.states import compute_state

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_PHASES: Final[tuple[int, ...]] = (1, 2, 3)
_RECORD_PHASES: Final[frozenset[int]] = frozenset({1, 2})
_REPLAN_INVALIDATED_KIND: Final[str] = "replan_invalidated"
_INVALIDATED_STATE: Final[str] = "invalidated-by-replan"


def _find_replan_scope(journal_path: Path, *, invalidated_at: str) -> dict[str, Any] | None:
    """Return the persisted ``replan_invalidated`` payload matching ``invalidated_at``.

    Correlates by exact ``ts`` match (RFC 3339 UTC ms) rather than recomputing
    scope: ``cli/replan_cmd.py`` writes ``replan_invalidated`` then the
    per-phase ``signoff_invalidated`` entries within one call, sharing the
    same ``now`` timestamp. Returns the last (most recent) match in journal
    order in the rare case more than one replan run shares a millisecond.
    """
    match: dict[str, Any] | None = None
    for entry in iter_entries(journal_path):
        if entry.kind == _REPLAN_INVALIDATED_KIND and entry.ts == invalidated_at:
            match = dict(entry.payload)
    return match


def _phase_snapshot(phase: int, *, repo_root: Path, journal_path: Path) -> dict[str, Any]:
    state = compute_state(phase, repo_root=repo_root)
    snapshot: dict[str, Any] = {
        "state": state.value,
        "invalidated_at": None,
        "invalidated_reason": None,
    }
    if phase not in _RECORD_PHASES or state.value != _INVALIDATED_STATE:
        return snapshot

    record = read_record(phase, repo_root=repo_root)
    if record is None:  # pragma: no cover — compute_state already confirmed a record exists
        return snapshot
    snapshot["invalidated_at"] = record.invalidated_at
    snapshot["invalidated_reason"] = record.invalidated_reason
    if record.invalidated_at is not None:
        scope = _find_replan_scope(journal_path, invalidated_at=record.invalidated_at)
        if scope is not None:
            snapshot["replan"] = scope
    return snapshot


def register_signoff_route(router: Router, *, repo_root: Path) -> None:
    journal_path = repo_root / _JOURNAL_REL

    def _compute_body() -> bytes:
        phases = {
            str(phase): _phase_snapshot(phase, repo_root=repo_root, journal_path=journal_path)
            for phase in _PHASES
        }
        return json.dumps({"phases": phases}, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @router.get("/api/signoff")
    def handle_signoff(_ctx: RequestContext) -> Response:
        body = _compute_body()
        return Response(
            status=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
        )
