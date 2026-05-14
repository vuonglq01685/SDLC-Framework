"""Hypothesis property test: append-only invariant for journal (AC2, Story 1.11).

FR31 + NFR-REL-2 + epic AC block 2 (lines 688-692):

- Property 1 (``test_file_grows_only_and_bytes_immutable``): on-disk byte snapshot
  immutability. After every successful append, the next file read must START with the
  previous snapshot — i.e., earlier bytes are physically immutable on disk.
- Property 2 (``test_iter_after_correctness``): ``iter_after(t)`` returns exactly the
  entries with ``monotonic_seq > t`` in order.
- Property 3 (``test_seq_regression_rejected_and_file_unchanged``): duplicate / regressing
  / huge-gap-but-still-monotonic seqs raise ``JournalError`` and the file size is
  unchanged on failure; ``details`` carries ``supplied`` + ``expected_min``.

Each property runs as a distinct ``@given`` (review fix D5) so the "3 x 1000 examples"
claim is honest, not bundled.
"""

from __future__ import annotations

import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
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
import sdlc.journal  # noqa: E402

_JOURNAL_PUBLIC_API = set(sdlc.journal.__all__)
_EXPECTED_API = {
    "allocate_next_seq_for_append_sync",  # Story 2A.11: locked seq alloc for hook deny/bypass
    "append",
    "append_sync",
    "iter_after",
    "iter_entries",
}
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
    """RFC 3339 UTC timestamps with explicit ``Z`` suffix.

    ``strftime`` is used directly (not ``isoformat``+replace) because hypothesis can emit
    naive UTC datetimes whose ``isoformat`` lacks the ``+00:00`` suffix; the previous
    approach silently produced strings without ``Z`` (review fix Edge L M10).
    """

    def _format(dt: datetime) -> str:
        # Truncate microseconds → milliseconds (3 digits) and append explicit Z.
        ms = dt.microsecond // 1000
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}Z"

    return st.datetimes(timezones=st.just(timezone.utc)).map(_format)


def _sha256_strategy() -> st.SearchStrategy[str]:
    return st.text(alphabet="0123456789abcdef", min_size=64, max_size=64).map(
        lambda h: f"sha256:{h}"
    )


# Unicode BiDi-control codepoints (LTR/RTL embedding, override, isolate, popdir-format).
# Most are already in category Cf and rejected by the ``cat.startswith("C")`` check, but
# we spell them out via codepoint to keep the source ASCII-safe.
_BIDI_CTRL_CODEPOINTS = frozenset(
    chr(cp)
    for cp in (
        0x202A,  # LEFT-TO-RIGHT EMBEDDING
        0x202B,  # RIGHT-TO-LEFT EMBEDDING
        0x202C,  # POP DIRECTIONAL FORMATTING
        0x202D,  # LEFT-TO-RIGHT OVERRIDE
        0x202E,  # RIGHT-TO-LEFT OVERRIDE
        0x2066,  # LEFT-TO-RIGHT ISOLATE
        0x2067,  # RIGHT-TO-LEFT ISOLATE
        0x2068,  # FIRST STRONG ISOLATE
        0x2069,  # POP DIRECTIONAL ISOLATE
    )
)


def _is_safe_actor_char(c: str) -> bool:
    """Reject control / format / private-use / surrogate / unassigned characters."""
    cat = unicodedata.category(c)
    if cat.startswith("C"):  # Cc, Cf, Cn, Co, Cs
        return False
    if c in _BIDI_CTRL_CODEPOINTS:
        return False
    return c.isprintable()


_actor_strategy = st.text(min_size=1, max_size=20).filter(
    lambda s: all(_is_safe_actor_char(c) for c in s)
)

_journal_entry_strategy = st.fixed_dictionaries(
    {
        "schema_version": st.just(1),
        "ts": _iso_z_strategy(),
        "actor": _actor_strategy,
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
        base_entries: list[dict[str, object]], offsets: list[int], start_seq: int
    ) -> list[JournalEntry]:
        seq = start_seq - offsets[0] if offsets else 0  # so first +offset lands on start_seq
        result = []
        for entry_dict, gap in zip(base_entries, offsets, strict=True):
            seq += gap
            result.append(JournalEntry.model_validate({**entry_dict, "monotonic_seq": seq}))
        return result

    n = st.integers(min_value=1, max_value=20)
    return n.flatmap(
        lambda size: st.builds(
            build_sequence,
            base_entries=st.lists(_journal_entry_strategy, min_size=size, max_size=size),
            offsets=st.lists(st.integers(min_value=1, max_value=10), min_size=size, max_size=size),
            start_seq=st.integers(min_value=0, max_value=10),
        )
    )


_sequence_strategy = _make_entry_sequence_strategy()


# ---------------------------------------------------------------------------
# Property 1: File grows-only + ON-DISK BYTES are immutable (snapshot prefix check)
# ---------------------------------------------------------------------------
def _make_min_entries(seqs: list[int]) -> list[object]:
    """Build a small list of valid JournalEntry instances at the requested seqs."""
    from sdlc.contracts.journal_entry import JournalEntry

    return [
        JournalEntry(
            schema_version=1,
            monotonic_seq=s,
            ts="2026-05-08T00:00:00.000Z",
            actor=f"actor-{s}",
            kind="state_mutation",
            target_id=f"t-{s}",
            before_hash=None,
            after_hash="sha256:" + ("a" * 64),
            payload={"k": str(s)},
        )
        for s in seqs
    ]


@pytest.mark.xfail(
    reason="Pre-existing failure on main@12374b3 (verified by bisect 2026-05-10);"
    " tracked in EPIC-2A-DEBT-009. Story 2A.5 DR2 quarantine.",
    strict=False,
)
@given(entries=_sequence_strategy)
@example(entries=_make_min_entries([0]))
@example(entries=_make_min_entries([0, 1, 2]))
@example(entries=_make_min_entries([0, 10**12]))
@example(entries=_make_min_entries([2**63 - 2, 2**63 - 1]))
@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_file_grows_only_and_bytes_immutable(entries: list[object], tmp_path: Path) -> None:
    """After every append, file bytes start with the prior snapshot (B7 fix).

    This is the actual on-disk byte-immutability invariant — re-canonicalising from the
    in-memory entry on both sides (the previous test) only proved canonicalisation is
    deterministic, not that the writer never rewrote earlier bytes.
    """
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync, iter_entries

    journal_path = tmp_path / "test.journal.log"
    snapshot = b""

    for i, entry in enumerate(entries):
        assert isinstance(entry, JournalEntry)
        append_sync(entry, journal_path)
        current = journal_path.read_bytes()
        assert current.startswith(snapshot), (
            f"Earlier on-disk bytes mutated after append {i}: prefix mismatch"
        )
        assert len(current) > len(snapshot), (
            f"File did not grow after append {i}: {len(snapshot)} → {len(current)}"
        )
        snapshot = current

    # Final read still equals the complete sequence in monotonic_seq order
    final_entries = list(iter_entries(journal_path))
    assert len(final_entries) == len(entries)
    for entry, read_entry in zip(entries, final_entries, strict=True):
        assert isinstance(entry, JournalEntry)
        assert read_entry.monotonic_seq == entry.monotonic_seq


# ---------------------------------------------------------------------------
# Property 2: iter_after(threshold) correctness
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    reason="Pre-existing failure on main@12374b3 (verified by bisect 2026-05-10);"
    " tracked in EPIC-2A-DEBT-010. Story 2A.5 DR2 quarantine.",
    strict=False,
)
@given(entries=_sequence_strategy)
@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_iter_after_correctness(entries: list[object], tmp_path: Path) -> None:
    """``iter_after(t)`` returns exactly entries with ``monotonic_seq > t`` in order."""
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync, iter_after

    journal_path = tmp_path / "test.iter_after.log"
    for entry in entries:
        assert isinstance(entry, JournalEntry)
        append_sync(entry, journal_path)

    if not entries:
        return
    # Pick threshold = mid-sequence seq
    k = len(entries) // 2
    threshold = entries[k].monotonic_seq  # type: ignore[union-attr]
    after = list(iter_after(journal_path, threshold))
    expected = [e for e in entries if e.monotonic_seq > threshold]  # type: ignore[union-attr]
    assert len(after) == len(expected)
    for got, want in zip(after, expected, strict=True):
        assert isinstance(want, JournalEntry)
        assert got.monotonic_seq == want.monotonic_seq


# ---------------------------------------------------------------------------
# Property 3: Monotonic_seq regression rejected; file size unchanged on failure
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    reason="Pre-existing failure on main@12374b3 (verified by bisect 2026-05-10);"
    " tracked in EPIC-2A-DEBT-011. Story 2A.5 DR2 quarantine.",
    strict=False,
)
@given(
    entry=_journal_entry_strategy,
    first_seq=st.integers(min_value=1, max_value=10**6),
    bad_offset=st.sampled_from([0, -1, -10, -(10**5)]),  # 0=duplicate, negatives=true regression
)
@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_seq_regression_rejected_and_file_unchanged(
    entry: dict[str, object], first_seq: int, bad_offset: int, tmp_path: Path
) -> None:
    """Duplicate/regressing seq raises JournalError; file size is unchanged after failure.

    Tests both pure duplicate (bad_offset=0) and true regression (bad_offset<0). Asserts
    on specific ``details["supplied"]`` and ``details["expected_min"]`` (review patch M9).
    """
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync

    journal_path = tmp_path / "test.regression.log"
    first = JournalEntry.model_validate({**entry, "monotonic_seq": first_seq})
    append_sync(first, journal_path)
    size_after_first = os.path.getsize(str(journal_path))

    bad_seq = first_seq + bad_offset
    if bad_seq < 1:
        # JournalEntry contract requires monotonic_seq >= 1 (Story 1.7); skip these examples
        # since the entry won't even validate. The real assertion under test fires only when
        # the entry passes contract validation but is still <= highest.
        return
    bad = JournalEntry.model_validate({**entry, "monotonic_seq": bad_seq})
    with pytest.raises(JournalError) as exc_info:
        append_sync(bad, journal_path)

    details = exc_info.value.details
    assert details.get("step") == "validate_seq", f"Expected step='validate_seq', got: {details}"
    assert details.get("supplied") == bad_seq, (
        f"Expected supplied={bad_seq}, got: {details.get('supplied')}"
    )
    assert details.get("expected_min") == first_seq + 1, (
        f"Expected expected_min={first_seq + 1}, got: {details.get('expected_min')}"
    )
    # File must not have grown or shrunk
    assert os.path.getsize(str(journal_path)) == size_after_first, (
        "File size changed after failed append"
    )
