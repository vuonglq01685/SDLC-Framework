"""Hypothesis property test: append-only invariant for journal (AC2, Story 1.11).

FR31 + NFR-REL-2 + epic AC block 2 (lines 688-692):
- File grows monotonically; line bytes are byte-identical to what was appended.
- No mutation API exists on sdlc.journal.
- iter_after returns entries with monotonic_seq strictly > threshold.
- Duplicate/regressing monotonic_seq is rejected; file size unchanged on failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = [
    pytest.mark.property,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX-only — fcntl + O_APPEND atomicity required",
    ),
]

# ---------------------------------------------------------------------------
# Structural assertion (module-level, runs once per session)
# ---------------------------------------------------------------------------
import sdlc.journal  # noqa: E402 (after pytestmark)

_JOURNAL_PUBLIC_API = set(sdlc.journal.__all__)
_EXPECTED_API = {"append", "append_sync", "iter_entries", "iter_after"}
assert _JOURNAL_PUBLIC_API == _EXPECTED_API, f"Unexpected public API: {_JOURNAL_PUBLIC_API}"

_FORBIDDEN_MUTATION_NAMES = (
    "write_at_offset",
    "truncate",
    "replace_line",
    "edit_line",
    "delete_line",
    "overwrite",
    "seek_and_write",
)
for _fname in _FORBIDDEN_MUTATION_NAMES:
    assert not hasattr(sdlc.journal, _fname), f"Mutation API exists: {_fname}"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
_RFC3339_UTC_RE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"


def _iso_z_strategy() -> st.SearchStrategy[str]:
    from datetime import timezone

    import hypothesis.strategies as _st

    return _st.datetimes(timezones=_st.just(timezone.utc)).map(
        lambda dt: dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _sha256_strategy() -> st.SearchStrategy[str]:
    return st.text(alphabet="0123456789abcdef", min_size=64, max_size=64).map(
        lambda h: f"sha256:{h}"
    )


_journal_entry_strategy = st.fixed_dictionaries(
    {
        "schema_version": st.just(1),
        "ts": _iso_z_strategy(),
        "actor": st.text(min_size=1, max_size=20).filter(str.isprintable),
        "kind": st.sampled_from(["state_mutation", "agent_dispatch", "signoff", "bypass_signoff"]),
        "target_id": st.text(min_size=1, max_size=40).filter(str.isprintable),
        "before_hash": st.one_of(st.none(), _sha256_strategy()),
        "after_hash": _sha256_strategy(),
        "payload": st.dictionaries(
            st.text(min_size=1, max_size=10).filter(str.isprintable),
            st.text(min_size=0, max_size=20),
            max_size=5,
        ),
    }
)


def _make_entry_sequence_strategy() -> st.SearchStrategy[list[object]]:
    """Produce a list of JournalEntry with strictly increasing monotonic_seq values."""
    from sdlc.contracts.journal_entry import JournalEntry

    def build_sequence(
        base_entries: list[dict[str, object]], offsets: list[int]
    ) -> list[JournalEntry]:
        seq = 0
        result = []
        for entry_dict, gap in zip(base_entries, offsets, strict=True):
            seq += gap
            result.append(JournalEntry.model_validate({**entry_dict, "monotonic_seq": seq}))
        return result

    n = st.integers(min_value=1, max_value=50)
    return n.flatmap(
        lambda size: st.builds(
            build_sequence,
            base_entries=st.lists(_journal_entry_strategy, min_size=size, max_size=size),
            offsets=st.lists(st.integers(min_value=1, max_value=10), min_size=size, max_size=size),
        )
    )


_sequence_strategy = _make_entry_sequence_strategy()


# ---------------------------------------------------------------------------
# Property 1: File grows-only + line bytes immutable
# ---------------------------------------------------------------------------
@given(entries=_sequence_strategy)
@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_file_grows_only_and_line_bytes_immutable(entries: list[object], tmp_path: Path) -> None:
    """For every prefix, appended bytes are byte-identical to what was written; file only grows."""
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync, iter_after, iter_entries
    from sdlc.journal.writer import _canonicalize_entry

    journal_path = tmp_path / "test.journal.log"
    prev_size = 0

    for i, entry in enumerate(entries):
        assert isinstance(entry, JournalEntry)
        append_sync(entry, journal_path)

        current_size = os.path.getsize(str(journal_path))
        assert current_size > prev_size, (
            f"File size did not grow after append {i}: {prev_size} → {current_size}"
        )
        prev_size = current_size

        # Read all lines and verify byte-identity for every prefix entry
        raw_lines = journal_path.read_bytes().decode("utf-8").splitlines()
        assert len(raw_lines) == i + 1, f"Expected {i + 1} lines, got {len(raw_lines)}"
        for j in range(i + 1):
            expected_bytes = _canonicalize_entry(entries[j])  # type: ignore[arg-type]
            actual_bytes = (raw_lines[j] + "\n").encode("utf-8")
            assert actual_bytes == expected_bytes, f"Line {j} byte mismatch at prefix {i + 1}"

        # iter_entries must yield in monotonic_seq order
        yielded = list(iter_entries(journal_path))
        assert len(yielded) == i + 1
        for k in range(len(yielded) - 1):
            assert yielded[k].monotonic_seq < yielded[k + 1].monotonic_seq

    # Final full read still equals the complete sequence
    final_entries = list(iter_entries(journal_path))
    assert len(final_entries) == len(entries)
    for entry, read_entry in zip(entries, final_entries, strict=True):
        assert isinstance(entry, JournalEntry)
        assert read_entry.monotonic_seq == entry.monotonic_seq

    # iter_after correctness (Property 3 inline)
    if len(entries) >= 2:
        k = len(entries) // 2
        threshold = entries[k].monotonic_seq  # type: ignore[union-attr]
        after = list(iter_after(journal_path, threshold))
        expected_after = [e for e in entries if e.monotonic_seq > threshold]  # type: ignore[union-attr]
        assert len(after) == len(expected_after)
        for a, b in zip(after, expected_after, strict=True):
            assert isinstance(b, JournalEntry)
            assert a.monotonic_seq == b.monotonic_seq


# ---------------------------------------------------------------------------
# Property 4: Monotonic_seq regression rejected; file size unchanged on failure
# ---------------------------------------------------------------------------
@given(entry=_journal_entry_strategy)
@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_seq_regression_rejected_and_file_unchanged(
    entry: dict[str, object], tmp_path: Path
) -> None:
    """Duplicate/regressing seq raises JournalError; file size is unchanged after failure."""
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync

    journal_path = tmp_path / "test.regression.log"
    first = JournalEntry.model_validate({**entry, "monotonic_seq": 5})
    append_sync(first, journal_path)
    size_after_first = os.path.getsize(str(journal_path))

    # Attempt same seq → must reject
    duplicate = JournalEntry.model_validate({**entry, "monotonic_seq": 5})
    with pytest.raises(JournalError) as exc_info:
        append_sync(duplicate, journal_path)

    assert exc_info.value.details.get("step") == "validate_seq", (
        f"Expected step='validate_seq', got: {exc_info.value.details}"
    )
    # File must not have grown or shrunk
    assert os.path.getsize(str(journal_path)) == size_after_first, (
        "File size changed after failed append"
    )
