"""Hypothesis property test: replay invariant for state projection (Story 1.12, AC2 + AC4).

Decision B4 (Architecture §348) — full replay from journal[0] for v1.
Decision B5 (Architecture §349) — state is a projection of journal.
Architecture §220 — Murat's added invariant: replay(journal[0:k]) == state_at_step_k for every k.
Epic AC block 2: ≥1000 hypothesis examples per CI run.

The oracle reducer (_oracle_reduce) is an INDEPENDENT implementation of the same contract,
co-located here so the differential test is self-contained and reviewable in one file.
The oracle uses a recursive/functional fold (functools.reduce + immutable returns) while
production uses an iterative mutable accumulator — the structural divergence is the whole point
of the differential pattern (Architecture §220). Do NOT refactor the oracle to call
_project_entries; the two-implementation independence is the contract.

Strategy helpers duplicated from tests/property/test_journal_append_only.py (not imported).
Rationale: property tests are contract assertions; keeping strategies local makes the contract
self-contained; cross-test imports are fragile under pytest's discovery ordering.
"""

from __future__ import annotations

import re
import sys
from contextlib import suppress
from datetime import timezone
from functools import reduce
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError
from sdlc.journal import append_sync
from sdlc.state import project_from_journal
from sdlc.state.model import State
from sdlc.state.projection import _KNOWN_KINDS, _project_entries

# ---------------------------------------------------------------------------
# Independent oracle reducer — must NOT import from sdlc.state.projection (other than
# _KNOWN_KINDS, which is a CONSTANT shared with production for drift safety, not the reducer).
#
# Implementation strategy intentionally diverges from production:
#  - Production: iterative for-loop with mutable next_seq + dict accumulators.
#  - Oracle:     functools.reduce with immutable State returns at every step.
# This structural independence is what makes the differential test meaningful (Architecture §220).
# ---------------------------------------------------------------------------

# Use re.fullmatch in the oracle (production uses anchored \A...\Z); both reject trailing newlines
# and Unicode digits. Two different anchoring approaches → independent verification of the contract.
_ORACLE_EPIC_PATTERN = re.compile(r"epic-[0-9]+")


def _oracle_step(state: State, entry: JournalEntry) -> State:
    """One reducer step — returns a NEW State (no mutation)."""
    if entry.schema_version != 1:
        raise JournalError(
            f"unknown schema_version={entry.schema_version} for kind={entry.kind};"
            f" run sdlc migrate-v{entry.schema_version}",
            details={
                "step": "project_unknown_schema",
                "schema_version": entry.schema_version,
                "kind": entry.kind,
                "monotonic_seq": entry.monotonic_seq,
                "lineno": None,
            },
        )
    new_seq = max(state.next_monotonic_seq, entry.monotonic_seq + 1)
    if entry.kind == "state_mutation" and _ORACLE_EPIC_PATTERN.fullmatch(entry.target_id):
        new_epics = {**state.epics, entry.target_id: dict(entry.payload)}
    else:
        new_epics = state.epics
    return State(next_monotonic_seq=new_seq, epics=new_epics)


def _oracle_reduce(entries: list[JournalEntry]) -> State:
    """Independent oracle reducer — recursive functional fold via functools.reduce.

    Diverges structurally from production's iterative mutable-accumulator style; this is
    the differential-test pattern (Architecture §220). Must NOT import the production reducer.
    """
    return reduce(_oracle_step, entries, State())


# ---------------------------------------------------------------------------
# Strategy helpers (duplicated from test_journal_append_only.py — see module docstring)
# ---------------------------------------------------------------------------


def _iso_z_strategy() -> st.SearchStrategy[str]:
    return st.datetimes(timezones=st.just(timezone.utc)).map(
        lambda dt: dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _sha256_strategy() -> st.SearchStrategy[str]:
    return st.text(alphabet="0123456789abcdef", min_size=64, max_size=64).map(
        lambda h: f"sha256:{h}"
    )


# Kind strategy: all known kinds (sorted for determinism) plus a sentinel unknown kind to
# exercise the permissive forward-compat path.
_KIND_STRATEGY = st.one_of(
    st.sampled_from(sorted(_KNOWN_KINDS)),
    st.just("unknown_kind_for_drift_test"),
)


# Build JournalEntry instances directly via st.builds (AC2 Task 6 spec wording: st.builds(
# JournalEntry, ...)). Yields validated JournalEntry instances; consumers do not need to
# re-validate via model_validate.
journal_entry_strategy = st.builds(
    JournalEntry,
    schema_version=st.just(1),
    monotonic_seq=st.integers(min_value=0, max_value=10_000),
    ts=_iso_z_strategy(),
    actor=st.text(min_size=1, max_size=20).filter(str.isprintable),
    kind=_KIND_STRATEGY,
    target_id=st.one_of(
        st.sampled_from(["epic-1", "epic-2", "epic-10", "task-1.2.3", "story-1.2"]),
        st.text(min_size=1, max_size=40).filter(str.isprintable),
    ),
    before_hash=st.one_of(st.none(), _sha256_strategy()),
    after_hash=_sha256_strategy(),
    payload=st.dictionaries(
        st.text(min_size=1, max_size=10).filter(str.isprintable),
        st.text(min_size=0, max_size=20),
        max_size=5,
    ),
)


def monotonic_sequence_strategy(max_size: int = 30) -> st.SearchStrategy[list[JournalEntry]]:
    """Produce a list of JournalEntry with strictly increasing monotonic_seq values.

    Rebuilds entries via model_copy(update=...) to set per-position seq while preserving
    the rest of the hypothesis-generated payload — preferred over re-validating dicts.
    """

    def build_sequence(base_entries: list[JournalEntry], offsets: list[int]) -> list[JournalEntry]:
        seq = 0
        result: list[JournalEntry] = []
        for entry, gap in zip(base_entries, offsets, strict=True):
            seq += gap
            result.append(entry.model_copy(update={"monotonic_seq": seq}))
        return result

    n = st.integers(min_value=1, max_value=max_size)
    return n.flatmap(
        lambda size: st.builds(
            build_sequence,
            base_entries=st.lists(journal_entry_strategy, min_size=size, max_size=size),
            offsets=st.lists(st.integers(min_value=1, max_value=10), min_size=size, max_size=size),
        )
    )


# ---------------------------------------------------------------------------
# Property 1 — replay invariant (cross-platform; no IO, drives _project_entries directly)
#
# Tier-split rationale (D2): contract under test is replay(entries[:k]) == oracle(entries[:k]).
# Driving _project_entries directly with the iterable is faster (no file IO), runs on Windows,
# and lets us spend the 1000-example budget on the reducer surface rather than fsync. The
# IO smoke test below (Property 1-IO) preserves coverage of the project_from_journal path.
# ---------------------------------------------------------------------------
@given(entries=monotonic_sequence_strategy(max_size=30))
@settings(
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow],
)
@pytest.mark.property
def test_replay_invariant_holds_for_arbitrary_journal(entries: list[JournalEntry]) -> None:
    """For every k in [0,N]: _project_entries(entries[:k]) == _oracle_reduce(entries[:k])."""
    for k in range(0, len(entries) + 1):
        actual = _project_entries(entries[:k])
        expected = _oracle_reduce(entries[:k])
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json"), (
            f"replay invariant broken at k={k}: "
            f"actual={actual.model_dump()} expected={expected.model_dump()}"
        )


# ---------------------------------------------------------------------------
# Property 1-IO — IO smoke variant (POSIX-only; preserves project_from_journal path coverage)
#
# Smaller surface (max_size=8, max_examples=20) keeps fsync cost bounded while still exercising
# the file-read → iter_entries → _project_entries pipeline. function_scoped_fixture suppression
# is required because tmp_path is function-scoped per AC2.
# ---------------------------------------------------------------------------
@given(entries=monotonic_sequence_strategy(max_size=8))
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
    ],
)
@pytest.mark.property
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only — depends on append_sync which requires fcntl + O_APPEND",
)
def test_replay_invariant_via_real_journal_file(
    tmp_path: Path, entries: list[JournalEntry]
) -> None:
    """Same replay invariant, but routed through project_from_journal (file IO path)."""
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
# Smoke test — fast feedback in normal pytest runs (unit tier, no property gate)
# ---------------------------------------------------------------------------
@given(entries=monotonic_sequence_strategy(max_size=15))
@settings(
    max_examples=20,
    deadline=2000,
    suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow],
)
@pytest.mark.unit
def test_replay_invariant_smoke(entries: list[JournalEntry]) -> None:
    """Fast smoke variant of the replay invariant (20 examples, unit tier, in-memory)."""
    for k in range(0, len(entries) + 1):
        actual = _project_entries(entries[:k])
        expected = _oracle_reduce(entries[:k])
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Property 2 — schema-version drift fails-loud (cross-platform)
# ---------------------------------------------------------------------------
@given(
    entry=journal_entry_strategy,
    bad_version=st.integers().filter(lambda v: v != 1),
)
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much],
)
@pytest.mark.property
def test_unknown_schema_version_raises_journal_error(entry: JournalEntry, bad_version: int) -> None:
    """schema_version != 1 must raise JournalError with the exact message contract."""
    # model_construct bypasses Literal[1] — pydantic v2 way to build "invalid" models for tests.
    bad_entry = JournalEntry.model_construct(
        **{**entry.model_dump(), "schema_version": bad_version}
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
@given(entries=monotonic_sequence_strategy(max_size=20))
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much],
)
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

    # Use absolute path to scripts/ — cwd-independent, avoids picking up a stale module from
    # any other location on sys.path. Repo layout: tests/property/test_replay_invariant.py →
    # repo_root = parents[2]; scripts/ sits at repo_root/scripts.
    scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    _sys.path.insert(0, scripts_dir)
    try:
        from check_module_boundaries import MODULE_DEPS
    finally:
        # remove(value) is safer than pop(0): another plugin may have inserted ahead of us
        # between insert and remove.
        with suppress(ValueError):
            _sys.path.remove(scripts_dir)

    assert "journal" in MODULE_DEPS["state"].depends_on, (
        "MODULE_DEPS['state'] must include 'journal' (added by Story 1.12 — see ADR-015)"
    )
