"""Unit tests for sdlc.state.projection (Story 1.12, AC1 + AC3).

Tests drive _project_entries directly with Python lists to stay cross-platform,
plus a handful that need a real journal file (POSIX-only for the write-path tests).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType

import pydantic
import pytest

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError
from sdlc.journal import append_sync
from sdlc.state import project_from_journal
from sdlc.state.model import State
from sdlc.state.projection import _project_entries

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = "2026-05-08T00:00:00.000Z"
_AFTER = "sha256:" + "a" * 64


def _entry(
    *,
    kind: str = "state_mutation",
    target_id: str = "epic-1",
    seq: int = 0,
    payload: dict[str, object] | None = None,
    schema_version: int = 1,
) -> JournalEntry:
    """Build a valid JournalEntry for testing."""
    return JournalEntry.model_validate(
        {
            "schema_version": schema_version,
            "monotonic_seq": seq,
            "ts": _TS,
            "actor": "test",
            "kind": kind,
            "target_id": target_id,
            "before_hash": None,
            "after_hash": _AFTER,
            "payload": payload if payload is not None else {},
        }
    )


def _bad_schema_entry(
    *, kind: str = "state_mutation", seq: int = 0, bad_version: int = 2
) -> JournalEntry:
    """Build a JournalEntry with an invalid schema_version via model_construct."""
    valid = _entry(kind=kind, seq=seq)
    return JournalEntry.model_construct(**{**valid.model_dump(), "schema_version": bad_version})


# ---------------------------------------------------------------------------
# Cross-platform tests — drive _project_entries directly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_project_empty_iterable_returns_default_state() -> None:
    state = _project_entries([])
    assert state.next_monotonic_seq == 0
    assert state.epics == {}
    assert state.schema_version == 1


@pytest.mark.unit
def test_project_single_state_mutation_on_epic_updates_epics() -> None:
    entry = _entry(
        kind="state_mutation",
        target_id="epic-1",
        seq=0,
        payload={"phase": "1", "status": "in-progress"},
    )
    state = _project_entries([entry])
    assert state.epics["epic-1"] == {"phase": "1", "status": "in-progress"}
    assert state.next_monotonic_seq == 1


@pytest.mark.unit
def test_project_state_mutation_on_non_epic_target_does_not_touch_epics() -> None:
    # Forward-compat: task-/story- projections will be added in later stories.
    # This test is the canary that catches an inadvertent regression if that happens early.
    entry = _entry(kind="state_mutation", target_id="task-1.2.3", seq=0, payload={"x": "y"})
    state = _project_entries([entry])
    assert state.epics == {}
    assert state.next_monotonic_seq == 1


@pytest.mark.unit
def test_project_rejects_target_id_with_trailing_newline() -> None:
    # Regex must use \A...\Z anchors (not ^...$) — the default $ matches before a final \n,
    # which would silently corrupt epic keys with literal newlines in state.json.
    entry = _entry(kind="state_mutation", target_id="epic-1\n", seq=0, payload={"x": "y"})
    state = _project_entries([entry])
    assert state.epics == {}, "target_id with trailing newline must NOT match epic-N pattern"
    assert state.next_monotonic_seq == 1


@pytest.mark.unit
def test_project_rejects_unicode_digit_target_id() -> None:
    # Regex must use [0-9]+ (not \d+) — Python's \d is Unicode-aware and matches Arabic-Indic
    # digits (U+0660 series), Devanagari, etc. Epic IDs are ASCII per the Story 1.6 IdsError
    # contract; non-ASCII digits would never round-trip equal to "epic-1".
    # Use \u escape for the Arabic-Indic digit one (U+0661) to avoid RUF001 ambiguous-char lint.
    entry = _entry(kind="state_mutation", target_id="epic-\u0661", seq=0, payload={"x": "y"})
    state = _project_entries([entry])
    assert state.epics == {}, "target_id with Arabic-Indic digit must NOT match epic-N pattern"
    assert state.next_monotonic_seq == 1


@pytest.mark.unit
def test_project_advances_seq_for_all_known_kinds() -> None:
    kinds = [
        "state_mutation",
        "agent_dispatch",
        "signoff",
        "bypass_signoff",
        "auto_mad_resolve",
        "hook_bypass",
    ]
    entries = [
        _entry(kind=k, target_id="epic-1" if k == "state_mutation" else "other", seq=i)
        for i, k in enumerate(kinds)
    ]
    state = _project_entries(entries)
    assert state.next_monotonic_seq == len(kinds)
    # Only the state_mutation on epic-1 touches epics
    assert list(state.epics.keys()) == ["epic-1"]


@pytest.mark.unit
def test_project_unknown_kind_advances_seq_only() -> None:
    # Unknown kinds are permissive by design (forward-compat: future kinds must not break replay).
    entry = _entry(kind="totally_made_up_v2_kind", target_id="epic-1", seq=0)
    state = _project_entries([entry])
    assert state.next_monotonic_seq == 1
    assert state.epics == {}


@pytest.mark.unit
def test_project_same_target_id_mutated_twice_last_writer_wins() -> None:
    # Production behavior: deterministic last-writer-wins. The reducer overwrites
    # epics[target_id] = dict(payload) on each state_mutation entry. This pins the contract
    # so a future story changing it (e.g., to merge or append) breaks this test loud.
    entries = [
        _entry(target_id="epic-1", seq=0, payload={"phase": "1", "owner": "alice"}),
        _entry(target_id="epic-1", seq=1, payload={"phase": "2", "stage": "review"}),
    ]
    state = _project_entries(entries)
    # Second payload fully replaces the first — no merge.
    assert state.epics["epic-1"] == {"phase": "2", "stage": "review"}
    assert "owner" not in state.epics["epic-1"]
    assert state.next_monotonic_seq == 2


@pytest.mark.unit
def test_project_unknown_schema_version_raises_journal_error() -> None:
    # AC3 dual-defence: pydantic's Literal[1] is the first defence (rejects schema_version=2 at
    # parse time via model_validate_json from the reader). _project_entries' check is the second
    # defence — exercised here by bypassing the parser via model_construct.
    bad = _bad_schema_entry(kind="state_mutation", seq=5, bad_version=2)
    with pytest.raises(JournalError) as exc_info:
        _project_entries([bad])
    err = exc_info.value
    assert err.details["step"] == "project_unknown_schema"
    assert err.details["schema_version"] == 2
    assert err.details["kind"] == "state_mutation"
    assert err.details["monotonic_seq"] == 5
    # _project_entries does not have access to the journal path; project_from_journal injects it.
    # When called via _project_entries directly (no path layer), `path` is absent.
    assert "path" not in err.details
    assert str(err) == "unknown schema_version=2 for kind=state_mutation; run sdlc migrate-v2"


@pytest.mark.unit
def test_project_halts_on_unknown_schema_version() -> None:
    valid_entries = [_entry(seq=i) for i in range(3)]
    bad = _bad_schema_entry(seq=3, bad_version=99)
    more_valid = [_entry(seq=4)]
    with pytest.raises(JournalError) as exc_info:
        _project_entries([*valid_entries, bad, *more_valid])
    assert exc_info.value.details["schema_version"] == 99
    assert exc_info.value.details["monotonic_seq"] == 3


@pytest.mark.unit
def test_project_max_seq_handles_out_of_order_defensively() -> None:
    # In production iter_entries rejects out-of-order seqs, but _project_entries
    # is a pure reducer that accepts any iterable — max() is belt-and-suspenders.
    # Per-step semantics: next_seq = max(next_seq, entry.monotonic_seq + 1) on each entry.
    # For seqs [0,5,2]: step1→max(0,1)=1; step2→max(1,6)=6; step3→max(6,3)=6.
    entries = [_entry(seq=s) for s in [0, 5, 2]]
    state = _project_entries(entries)
    assert state.next_monotonic_seq == 6


@pytest.mark.unit
def test_project_returns_frozen_state() -> None:
    result = _project_entries([])
    assert result.model_config.get("frozen") is True
    with pytest.raises((pydantic.ValidationError, TypeError, AttributeError)):
        # frozen=True model raises on attribute assignment
        result.next_monotonic_seq = 99  # type: ignore[misc]


@pytest.mark.unit
def test_project_pure_no_module_state() -> None:
    entry_a = _entry(target_id="epic-1", seq=0, payload={"a": "1"})
    entry_b = _entry(target_id="epic-2", seq=0, payload={"b": "2"})
    _project_entries([entry_a])
    result_b = _project_entries([entry_b])
    # Second call must not contain state from first call
    assert "epic-1" not in result_b.epics
    assert result_b.epics == {"epic-2": {"b": "2"}}


@pytest.mark.unit
def test_project_payload_is_dict_not_mappingproxy() -> None:
    # Story 1.7 _freeze_payload wraps payload as MappingProxyType; projection must unwrap
    # to plain dict so json serialization works.
    entry = _entry(target_id="epic-1", seq=0, payload={"k": "v"})
    assert isinstance(entry.payload, MappingProxyType), (
        "Test precondition: entry.payload is MappingProxyType (Story 1.7 contract). If this "
        "fails, the upstream JournalEntry._freeze_payload validator order changed — the actual "
        "behavior under test (dict-unwrap) is still verified by the type(state.epics[...]) check "
        "below; this precondition is a tripwire for an expected upstream contract change."
    )
    state = _project_entries([entry])
    assert type(state.epics["epic-1"]) is dict


# ---------------------------------------------------------------------------
# Tests needing a real journal file — some are cross-platform, some POSIX-only
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_project_from_journal_missing_file_returns_default_state(tmp_path: Path) -> None:
    state = project_from_journal(tmp_path / "nonexistent.log")
    assert state == State()


@pytest.mark.unit
def test_project_from_journal_empty_file_returns_default_state(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.log"
    journal_path.touch()
    state = project_from_journal(journal_path)
    assert state == State()


@pytest.mark.unit
def test_project_from_journal_injects_path_on_schema_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3 envelope contract: project_from_journal MUST inject details["path"] on schema-drift.

    Today's reader skips entries whose schema_version != 1 (pydantic Literal[1] raises
    ValidationError, the reader catches ValueError and skips with a warning), so the
    second-line-of-defence in _project_entries is unreachable through real files in v1.
    This test simulates the future-build case (Literal[1] broadened to int) by patching
    _project_entries to raise the schema-drift JournalError directly — verifies the wrapper's
    path-injection clause functions.
    """
    journal_path = tmp_path / "journal.log"
    journal_path.touch()

    def _raise_schema_drift(_entries: object) -> State:
        raise JournalError(
            "unknown schema_version=99 for kind=state_mutation; run sdlc migrate-v99",
            details={
                "step": "project_unknown_schema",
                "schema_version": 99,
                "kind": "state_mutation",
                "monotonic_seq": 0,
                "lineno": None,
            },
        )

    monkeypatch.setattr("sdlc.state.projection._project_entries", _raise_schema_drift)

    with pytest.raises(JournalError) as exc_info:
        project_from_journal(journal_path)
    assert exc_info.value.details["step"] == "project_unknown_schema"
    assert exc_info.value.details["schema_version"] == 99
    assert exc_info.value.details["path"] == str(journal_path)


@pytest.mark.unit
def test_project_from_journal_does_not_overwrite_existing_path_in_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Path injection is conditional: never overwrites an existing details["path"].

    iter_entries' reader_invariant errors already carry path; the wrapper only injects when
    absent. This test simulates the upstream-path case to pin the no-overwrite contract.
    """
    journal_path = tmp_path / "journal.log"
    journal_path.touch()
    upstream_path = "/upstream/different/journal.log"

    def _raise_with_path(_entries: object) -> State:
        raise JournalError(
            "upstream error",
            details={"step": "reader_invariant", "path": upstream_path},
        )

    monkeypatch.setattr("sdlc.state.projection._project_entries", _raise_with_path)

    with pytest.raises(JournalError) as exc_info:
        project_from_journal(journal_path)
    assert exc_info.value.details["path"] == upstream_path


@pytest.mark.unit
@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only — append_sync requires fcntl + O_APPEND"
)
def test_project_from_journal_round_trip_via_append_sync(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.log"
    entries = [
        _entry(kind="state_mutation", target_id="epic-1", seq=0, payload={"phase": "1"}),
        _entry(kind="agent_dispatch", target_id="agent-x", seq=1),
        _entry(kind="state_mutation", target_id="epic-2", seq=2, payload={"phase": "2"}),
    ]
    for e in entries:
        append_sync(e, journal_path)

    state = project_from_journal(journal_path)
    # Oracle: manually fold the entries
    assert state.next_monotonic_seq == 3
    assert state.epics["epic-1"] == {"phase": "1"}
    assert state.epics["epic-2"] == {"phase": "2"}
    assert "agent-x" not in state.epics


@pytest.mark.unit
def test_project_from_journal_propagates_reader_invariant_error(tmp_path: Path) -> None:
    """Hand-crafted journal with out-of-order seqs (bypasses append_sync validation).

    Cross-platform: writes JSONL via JournalEntry.model_dump_json (public pydantic API)
    rather than the private writer canonicalization helper — avoids coupling to internal
    journal/writer details and runs on Windows.
    """
    journal_path = tmp_path / "journal.log"
    e0 = _entry(seq=0)
    e1 = _entry(seq=1)
    e_bad = _entry(seq=0)  # regresses to seq 0 — will trigger reader_invariant

    lines = b"".join(e.model_dump_json().encode("utf-8") + b"\n" for e in (e0, e1, e_bad))
    journal_path.write_bytes(lines)

    with pytest.raises(JournalError) as exc_info:
        project_from_journal(journal_path)
    assert exc_info.value.details.get("step") == "reader_invariant"
