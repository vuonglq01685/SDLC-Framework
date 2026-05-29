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
# Anchored with \A...\Z (not ^...$) to reject trailing-newline target_ids — the default $ matches
# before a final \n, which would corrupt epic keys (e.g., "epic-1\n" would silently match).
# Uses [0-9]+ instead of \d+ to reject Unicode digits (Arabic-Indic U+0660-U+0669, Devanagari,
# etc.) — epic IDs are ASCII per the Story 1.6 IdsError contract; \d is Unicode-aware by default.
# Other patterns (story-, task-) are reserved for later stories.
_EPIC_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"\Aepic-[0-9]+\Z")

# Journal payload keys that are audit-trail-only and MUST NOT appear in the state.json
# projection (ADR-029 §1). ``mock`` records whether an AgentResult came from MockAIRuntime
# vs ClaudeAIRuntime — a runtime-provenance fact for the journal/telemetry, never a piece
# of projected state (a downstream consumer of state.json MUST NOT branch on mock-vs-real).
# This frozenset is the authoritative registry; ADR-029 §1 references it by name. Story
# 2B.3 AC4 pins the strip via test_projection_strips_mock_from_state_mutation_payload.
_AUDIT_ONLY_KEYS: Final[frozenset[str]] = frozenset({"mock"})

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
#
# Dual-defence model (AC3): JournalEntry.schema_version is declared `Literal[1]` in the pydantic
# contract (src/sdlc/contracts/journal_entry.py:29), so a journal line with schema_version=2 fails
# pydantic validation in JournalEntry.model_validate_json BEFORE reaching the check in
# _project_entries — Literal[1] rejects 2 at parse time, surfacing as a SchemaError from the
# reader. The check below is the SECOND line of defence: it catches the case where a future build
# broadens the contract (e.g., to `schema_version: int = Field(...)`) and the parser admits 2,
# but the projection still recognizes only v1. Removing either layer breaks the
# fail-loud-on-schema-drift contract (Decision F3 — per-contract versioning with explicit
# migration). The migration command name `sdlc migrate-vN` is reserved by the error message
# (forward-contract; cli/migrate.py is not yet implemented but the wording locks the command).
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
            # Second line of defence — see _SCHEMA_VERSION docstring above for the dual-defence
            # rationale. `path` is intentionally absent here; project_from_journal's wrapping
            # try/except injects it (AC3 envelope contract).
            raise JournalError(
                f"unknown schema_version={entry.schema_version} for kind={entry.kind};"
                f" run sdlc migrate-v{entry.schema_version}",
                details={
                    "step": "project_unknown_schema",
                    "schema_version": entry.schema_version,
                    "kind": entry.kind,
                    "monotonic_seq": entry.monotonic_seq,
                    # iter_entries doesn't surface line numbers; populated by a future
                    # reader-instrumentation story.
                    "lineno": None,
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
            # ADR-029 §1: keys in _AUDIT_ONLY_KEYS (e.g. ``mock``) are journal audit-trail
            # only — never project into state.json. sorted() pins canonical key order
            # independent of journal-writer insertion order (belt-and-braces vs golden drift).
            filtered = {k: v for k, v in entry.payload.items() if k not in _AUDIT_ONLY_KEYS}
            epics[entry.target_id] = dict(sorted(filtered.items(), key=lambda kv: kv[0]))
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

    Path injection: any JournalError raised by _project_entries (schema-drift) gets
    `details["path"]` populated here so callers see the originating journal path. Reader-
    invariant errors from iter_entries already include `path`, so the conditional add avoids
    overwriting (AC3 — error envelope contract).
    """
    try:
        return _project_entries(iter_entries(journal_path))
    except JournalError as err:
        if "path" not in err.details:
            err.details["path"] = str(journal_path)
        raise
