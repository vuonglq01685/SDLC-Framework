"""Rebuild state.json from journal — full replay.

FR35, Decision B4 + B5, Architecture §348, §846, §1059.

This is the materialisation of the replay invariant from Story 1.12:
  ``project_from_journal(journal[0:k]) == state_at_step_k`` for every k.
rebuild_state_from_journal() is the user-facing recovery surface; it is
idempotent and produces byte-equivalent state.json output to a clean run
from the same journal.

Not a primitive — composes ``state.projection.project_from_journal``
(read) and ``state.atomic.write_state_atomic_sync`` (write). Both are
covered by their own kill-point + property tests; this module is the
minimal seam between them.

Never mutates the journal. Reads are pure; writes go through the atomic
protocol so a kill mid-rebuild leaves the prior state.json intact.

On ``JournalError(step="reader_invariant")``, the caller MUST treat the
rebuild as failed; partial consumption of the iterator is NOT a recovery
state. ADR-023 records this contract.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    raise ImportError(
        "sdlc.state.rebuild is POSIX-only — depends on state.atomic (Architecture §573)"
    )

from pathlib import Path

from sdlc.errors import (  # noqa: F401  -- JournalError propagates from project_from_journal; explicit import documents the contract
    JournalError,
    StateError,
)
from sdlc.journal import iter_entries
from sdlc.state.atomic import write_state_atomic_sync
from sdlc.state.projection import project_from_journal

__all__ = ("rebuild_state_from_journal",)


def rebuild_state_from_journal(journal_path: Path, state_path: Path) -> int:
    """Rebuild state.json from a full journal replay (FR35, Decision B4 + B5).

    Returns the number of journal entries replayed.
    Raises StateError on validation failures or write errors.
    Propagates JournalError unchanged on journal corruption or schema drift.
    """
    if not journal_path.is_absolute():
        raise StateError(
            "rebuild_state_from_journal requires absolute journal_path",
            details={"path": str(journal_path), "step": "validate_journal_path"},
        )
    if not state_path.is_absolute():
        raise StateError(
            "rebuild_state_from_journal requires absolute state_path",
            details={"path": str(state_path), "step": "validate_state_path"},
        )
    if not journal_path.exists():
        raise StateError(
            f"no journal at {journal_path}; recovery requires either journal or backup",
            details={
                "path": str(journal_path),
                "reason": "missing_journal",
                "step": "validate_journal_exists",
            },
        )

    # JournalError propagates unchanged to the caller (journal corruption → unrecoverable)
    state = project_from_journal(journal_path)

    # Second pass: count entries for the success message.
    # WHY a second iteration: project_from_journal consumes the iterator without returning
    # a count, and the count is needed for human-readable output. Acceptable O(N) extra scan
    # on the recovery path (recovery is not a hot loop). Documented in ADR-023.
    entries_replayed = sum(1 for _ in iter_entries(journal_path))

    write_state_atomic_sync(state, state_path)

    return entries_replayed
