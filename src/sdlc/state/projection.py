"""State projection from journal — pure function (Decision B5, Architecture §348, §845, FR35).

Replay invariant: project_from_journal(journal[0:k]) == state_at_step_k for every k.
Uses sdlc.journal.iter_entries; respects MODULE_DEPS["state"].depends_on (post-Story-1.12 includes
"journal").

Cross-platform: no fcntl, no O_APPEND. Only reads the journal via iter_entries.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError
from sdlc.journal import iter_entries
from sdlc.state.model import State

# Only state_mutation entries with target_id matching this pattern affect state.epics in v1.
# Other patterns (story-, task-) are reserved for later stories.
_EPIC_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^epic-\d+$")

# Documents the v1 kind surface; NOT used to reject unknown kinds (forward-compat — kind drift
# within a schema version is permissive by design; schema_version drift is the strict detector).
_KNOWN_KINDS: Final[frozenset[str]] = frozenset(
    {
        "state_mutation",
        "agent_dispatch",
        "signoff",
        "bypass_signoff",
        "auto_mad_resolve",
        "hook_bypass",
    }
)

# The only schema_version this v1 projection recognizes.
_SCHEMA_VERSION: Final[int] = 1


def _project_entries(entries: Iterable[JournalEntry]) -> State:
    """Fold an iterable of JournalEntry into a State. Pure function — no I/O.

    Test seam: importable as sdlc.state.projection._project_entries for property tests
    that drive the reducer with a Python iterable directly (skipping the file-read step).
    Not part of the stable public API; do NOT call from production code paths.
    """
    next_seq: int = 0
    epics: dict[str, Any] = {}
    for entry in entries:
        if entry.schema_version != _SCHEMA_VERSION:
            raise JournalError(
                f"unknown schema_version={entry.schema_version} for kind={entry.kind};"
                f" run sdlc migrate-v{entry.schema_version}",
                details={
                    "step": "project_unknown_schema",
                    "schema_version": entry.schema_version,
                    "kind": entry.kind,
                    "monotonic_seq": entry.monotonic_seq,
                    # lineno is not available here; iter_entries doesn't surface it.
                    "lineno": None,
                    # path not available at this layer; project_from_journal adds it.
                },
            )
        # All known + unknown kinds advance the counter (forward-compat).
        # Using max() is belt-and-suspenders against an out-of-order journal (which iter_entries
        # already rejects via reader_invariant, but this is cheap extra safety).
        next_seq = max(next_seq, entry.monotonic_seq + 1)
        # Only state_mutation on epic-N target_id touches epics in v1.
        # Unknown kinds produce no state effect beyond advancing next_monotonic_seq.
        if entry.kind == "state_mutation" and _EPIC_ID_PATTERN.match(entry.target_id):
            # dict() unwraps MappingProxyType from Story 1.7's _freeze_payload so that
            # state.json serialization works (json.dumps doesn't handle MappingProxyType).
            epics[entry.target_id] = dict(entry.payload)
    return State(next_monotonic_seq=next_seq, epics=epics)


def project_from_journal(journal_path: Path) -> State:
    """Pure-function state projection from journal (Decision B5).

    Returns State() defaults for missing/empty journal. Raises JournalError with
    message "unknown schema_version=N for kind=X; run sdlc migrate-vN" on schema drift.
    No I/O writes; no global mutation.

    Path validation: not performed here. iter_entries handles missing files gracefully
    (yields nothing → returns State() defaults). The writer's path validation already
    covers production paths; adding it here would be redundant and asymmetric with the
    read-only nature of projection.
    """
    return _project_entries(iter_entries(journal_path))
