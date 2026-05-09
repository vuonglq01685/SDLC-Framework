"""Hypothesis property tests: rebuild_state_from_journal invariants (Story 1.20, AC7.2).

Three independent properties over arbitrary valid journals:
  1. byte_equivalent — rebuild produces the SAME state.json bytes as a direct
     ``project_from_journal`` + ``write_state_atomic_sync`` call (the load-bearing
     proof of AC1's "byte-equivalent to a clean run from the same journal" invariant).
  2. idempotent — running rebuild twice on the same journal yields byte-identical state.
  3. entry_count — returned integer equals the number of entries appended.

The strategy for generating valid monotonic sequences is imported from Story 1.12's
``test_replay_invariant.monotonic_sequence_strategy`` (AC7.2 spec mandate: "import it
rather than duplicate") — see ``tests/property/test_replay_invariant.py:135``.

Each test creates its own TemporaryDirectory inside the test body to avoid the
Hypothesis function_scoped_fixture health-check warning.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings

# Cross-test import (pytest --import-mode=prepend puts tests/<pkg>/__init__.py on sys.path).
from property.test_replay_invariant import monotonic_sequence_strategy

pytestmark = [
    pytest.mark.property,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — atomic state write"),
]


# ---------------------------------------------------------------------------
# Journal materialisation helper (writer-validated; entries arrive via append_sync)
# ---------------------------------------------------------------------------


def _materialise_journal(tmp: Path, entries: list[object]) -> Path:
    """Write entries to ``tmp/journal.log`` via the production append_sync API.

    Always creates the file (even when entries is empty) — rebuild requires the
    journal file to exist.
    """
    from sdlc.journal import append_sync

    journal_path = tmp / "journal.log"
    journal_path.touch()
    for entry in entries:
        append_sync(entry, journal_path=journal_path)  # type: ignore[arg-type]
    return journal_path.resolve()


# ---------------------------------------------------------------------------
# Property 1: byte-equivalence to direct project + atomic-write
# ---------------------------------------------------------------------------


@given(entries=monotonic_sequence_strategy(max_size=15))
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.property
def test_rebuild_byte_equivalent_to_full_replay_for_arbitrary_journal(
    entries: list[object],
) -> None:
    """AC1 + AC7.2: rebuild_state_from_journal produces byte-identical state.json
    to a direct project_from_journal + write_state_atomic_sync invocation."""
    from sdlc.state import project_from_journal, write_state_atomic_sync
    from sdlc.state.rebuild import rebuild_state_from_journal

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        journal_path = _materialise_journal(tmp, entries)
        path_a = (tmp / "state_a.json").resolve()
        path_b = (tmp / "state_b.json").resolve()

        rebuild_state_from_journal(journal_path=journal_path, state_path=path_a)
        write_state_atomic_sync(project_from_journal(journal_path), path_b)

        assert path_a.read_bytes() == path_b.read_bytes()


# ---------------------------------------------------------------------------
# Property 2: idempotent — two successive rebuilds produce byte-identical state.json
# ---------------------------------------------------------------------------


@given(entries=monotonic_sequence_strategy(max_size=15))
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.property
def test_rebuild_idempotent_for_arbitrary_journal(entries: list[object]) -> None:
    from sdlc.state.rebuild import rebuild_state_from_journal

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        journal_path = _materialise_journal(tmp, entries)
        state_path = (tmp / "state.json").resolve()

        rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)
        first_bytes = state_path.read_bytes()

        rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)
        second_bytes = state_path.read_bytes()

    assert first_bytes == second_bytes


# ---------------------------------------------------------------------------
# Property 3: returned count equals journal length
# ---------------------------------------------------------------------------


@given(entries=monotonic_sequence_strategy(max_size=15))
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.property
def test_rebuild_returns_correct_entry_count(entries: list[object]) -> None:
    from sdlc.state.rebuild import rebuild_state_from_journal

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        journal_path = _materialise_journal(tmp, entries)
        state_path = (tmp / "state.json").resolve()

        count = rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)

    assert count == len(entries)
