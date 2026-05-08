"""Hypothesis property test: replay invariant for state projection (Story 1.12, AC2 + AC4).

Decision B4 (Architecture §348) — full replay from journal[0] for v1.
Decision B5 (Architecture §349) — state is a projection of journal.
Architecture §220 — Murat's added invariant: replay(journal[0:k]) == state_at_step_k for every k.
Epic AC block 2: ≥1000 hypothesis examples per CI run.

The oracle reducer (_oracle_reduce) is an independent implementation of the same contract —
co-located here so the differential test is self-contained and reviewable in one file.
Do NOT refactor the oracle to call _project_entries; the two-implementation differential is the
whole point (Murat's pattern at Architecture §220).

Strategy helpers duplicated from tests/property/test_journal_append_only.py (not imported).
Rationale: property tests are contract assertions; keeping strategies local makes the contract
self-contained; cross-test imports are fragile under pytest's discovery ordering.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError
from sdlc.state import project_from_journal
from sdlc.state.model import State
from sdlc.state.projection import _project_entries

# ---------------------------------------------------------------------------
# Independent oracle reducer — must NOT import from sdlc.state.projection
# ---------------------------------------------------------------------------
_ORACLE_EPIC_PATTERN = re.compile(r"^epic-\d+$")


def _oracle_reduce(entries: list[JournalEntry]) -> State:
    """Independent oracle reducer for the replay invariant.

    Must NOT import from sdlc.state.projection. Mirrors the same contract via a different
    implementation path so the property test provably exercises the contract end-to-end
    (differential-test pattern — Architecture §220).
    """
    epics: dict[str, Any] = {}
    next_seq = 0
    for e in entries:
        if e.schema_version != 1:
            raise JournalError(
                f"unknown schema_version={e.schema_version} for kind={e.kind};"
                f" run sdlc migrate-v{e.schema_version}",
                details={
                    "step": "project_unknown_schema",
                    "schema_version": e.schema_version,
                    "kind": e.kind,
                    "monotonic_seq": e.monotonic_seq,
                    "lineno": None,
                },
            )
        next_seq = max(next_seq, e.monotonic_seq + 1)
        if e.kind == "state_mutation" and _ORACLE_EPIC_PATTERN.match(e.target_id):
            epics[e.target_id] = dict(e.payload)
    return State(next_monotonic_seq=next_seq, epics=epics)


# ---------------------------------------------------------------------------
# Strategy helpers (duplicated from test_journal_append_only.py — see module docstring)
# ---------------------------------------------------------------------------


def _iso_z_strategy() -> st.SearchStrategy[str]:
    from datetime import timezone

    return st.datetimes(timezones=st.just(timezone.utc)).map(
        lambda dt: dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _sha256_strategy() -> st.SearchStrategy[str]:
    return st.text(alphabet="0123456789abcdef", min_size=64, max_size=64).map(
        lambda h: f"sha256:{h}"
    )


# Kind strategy: all known kinds + low-probability unknown kind to exercise permissive path
_KNOWN_KINDS_LIST = [
    "state_mutation",
    "agent_dispatch",
    "signoff",
    "bypass_signoff",
    "auto_mad_resolve",
    "hook_bypass",
]

_journal_entry_base = st.fixed_dictionaries(
    {
        "schema_version": st.just(1),
        "ts": _iso_z_strategy(),
        "actor": st.text(min_size=1, max_size=20).filter(str.isprintable),
        "kind": st.one_of(
            st.sampled_from(_KNOWN_KINDS_LIST),
            st.just("unknown_kind_for_drift_test"),
        ),
        "target_id": st.one_of(
            st.sampled_from(["epic-1", "epic-2", "epic-10", "task-1.2.3", "story-1.2"]),
            st.text(min_size=1, max_size=40).filter(str.isprintable),
        ),
        "before_hash": st.one_of(st.none(), _sha256_strategy()),
        "after_hash": _sha256_strategy(),
        "payload": st.dictionaries(
            st.text(min_size=1, max_size=10).filter(str.isprintable),
            st.text(min_size=0, max_size=20),
            max_size=5,
        ),
    }
)

_journal_entry_strategy = _journal_entry_base


def _make_monotonic_sequence_strategy(max_size: int = 30) -> st.SearchStrategy[list[JournalEntry]]:
    """Produce a list of JournalEntry with strictly increasing monotonic_seq values."""

    def build_sequence(
        base_entries: list[dict[str, object]], offsets: list[int]
    ) -> list[JournalEntry]:
        seq = 0
        result = []
        for entry_dict, gap in zip(base_entries, offsets, strict=True):
            seq += gap
            result.append(JournalEntry.model_validate({**entry_dict, "monotonic_seq": seq}))
        return result

    n = st.integers(min_value=1, max_value=max_size)
    return n.flatmap(
        lambda size: st.builds(
            build_sequence,
            base_entries=st.lists(_journal_entry_base, min_size=size, max_size=size),
            offsets=st.lists(st.integers(min_value=1, max_value=10), min_size=size, max_size=size),
        )
    )


# ---------------------------------------------------------------------------
# Property 1 — replay invariant (POSIX-only — needs append_sync for file construction)
# ---------------------------------------------------------------------------
@given(entries=_make_monotonic_sequence_strategy(max_size=30))
@settings(
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@pytest.mark.property
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only — depends on append_sync which requires fcntl + O_APPEND",
)
def test_replay_invariant_holds_for_arbitrary_journal(
    tmp_path: Path, entries: list[JournalEntry]
) -> None:
    """For every k in [0,N]: project_from_journal(journal[:k]) == _oracle_reduce(entries[:k])."""
    from sdlc.journal import append_sync

    journal_path = tmp_path / "journal.log"
    for k in range(0, len(entries) + 1):
        # Reset journal file for each k — clean file per k to keep state isolated;
        # tmp_path resets per hypothesis example so cross-example state is impossible.
        if journal_path.exists():
            journal_path.unlink()
        for e in entries[:k]:
            append_sync(e, journal_path)
        actual = project_from_journal(journal_path)
        expected = _oracle_reduce(entries[:k])
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json"), (
            f"replay invariant broken at k={k}: "
            f"actual={actual.model_dump()} expected={expected.model_dump()}"
        )


# ---------------------------------------------------------------------------
# Smoke test — fast feedback in normal pytest runs (unit tier, no property gate)
# ---------------------------------------------------------------------------
@given(entries=_make_monotonic_sequence_strategy(max_size=15))
@settings(
    max_examples=20, deadline=2000, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@pytest.mark.unit
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only — depends on append_sync which requires fcntl + O_APPEND",
)
def test_replay_invariant_smoke(tmp_path: Path, entries: list[JournalEntry]) -> None:
    """Fast smoke variant of the replay invariant (20 examples, unit tier)."""
    from sdlc.journal import append_sync

    journal_path = tmp_path / "journal.log"
    for k in range(0, len(entries) + 1):
        if journal_path.exists():
            journal_path.unlink()
        for e in entries[:k]:
            append_sync(e, journal_path)
        actual = project_from_journal(journal_path)
        expected = _oracle_reduce(entries[:k])
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Property 2 — schema-version drift fails-loud (cross-platform)
# ---------------------------------------------------------------------------
@given(
    entry=_journal_entry_strategy,
    bad_version=st.integers().filter(lambda v: v != 1),
)
@settings(max_examples=200, deadline=None)
@pytest.mark.property
def test_unknown_schema_version_raises_journal_error(
    entry: dict[str, object], bad_version: int
) -> None:
    """schema_version != 1 must raise JournalError with the exact message contract."""
    valid = JournalEntry.model_validate({**entry, "monotonic_seq": 0})
    # model_construct bypasses Literal[1] — pydantic v2 way to build "invalid" models for tests.
    bad_entry = JournalEntry.model_construct(
        **{**valid.model_dump(), "schema_version": bad_version}
    )
    with pytest.raises(JournalError) as exc_info:
        _project_entries([bad_entry])
    assert exc_info.value.details["step"] == "project_unknown_schema"
    assert exc_info.value.details["schema_version"] == bad_version
    assert str(exc_info.value).startswith(
        f"unknown schema_version={bad_version} for kind={bad_entry.kind}"
    )


# ---------------------------------------------------------------------------
# Property 3 — projection idempotent under no-op replay (cross-platform)
# ---------------------------------------------------------------------------
@given(entries=_make_monotonic_sequence_strategy(max_size=20))
@settings(max_examples=200, deadline=None)
@pytest.mark.property
def test_projection_idempotent(entries: list[JournalEntry]) -> None:
    """Calling _project_entries twice on the same list yields equal states — no hidden state."""
    s1 = _project_entries(entries)
    s2 = _project_entries(entries)
    assert s1.model_dump(mode="json") == s2.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Property 4 — module boundary invariant (unit tier, static assertion)
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_state_module_depends_on_journal() -> None:
    """Invariant: MODULE_DEPS['state'] must include 'journal' (Story 1.12 — see ADR-015)."""
    import sys as _sys

    _sys.path.insert(0, "scripts")
    try:
        from check_module_boundaries import MODULE_DEPS
    finally:
        _sys.path.pop(0)

    assert "journal" in MODULE_DEPS["state"].depends_on, (
        "MODULE_DEPS['state'] must include 'journal' (added by Story 1.12 — see ADR-015)"
    )
