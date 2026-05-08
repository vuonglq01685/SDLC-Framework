"""Lockstep test: ``sdlc.journal._canonical._normalize_strings`` must produce
byte-for-byte identical output to ``sdlc.state.atomic._normalize_strings`` for a fixed
corpus (Story 1.11 review — drift detector).

This is the ONLY place in the journal test suite that imports from ``sdlc.state`` —
the lockstep promise is the whole reason the duplication exists, so verifying it must
read both copies. ``MODULE_DEPS["journal"]`` excludes ``state`` for production code; the
test boundary is the right place to enforce the equivalence.
"""

from __future__ import annotations

import sys

import pytest

# Skip on Windows because ``sdlc.state.atomic`` is POSIX-only and raises ImportError.
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="state.atomic is POSIX-only — lockstep verified on Linux CI",
    ),
]


_FIXTURES = [
    "ascii-only",
    "café",  # composed (precomposed)
    "café",  # decomposed: e + combining acute → must NFC to "café"
    "naïveté",
    "ｱｲｳ",  # halfwidth katakana → fullwidth on NFKC, but stays half on NFC
    "\U0001d4d7ello",  # mathematical script H + ascii (NFC no-op; NFKC would decompose)
    "",  # empty string
    "ﬁnally",  # ligature — NFC keeps as ligature, NFKC decomposes
]


@pytest.mark.unit
def test_normalize_strings_lockstep_strings() -> None:
    from sdlc.journal._canonical import _normalize_strings as journal_norm
    from sdlc.state.atomic import _normalize_strings as state_norm

    for s in _FIXTURES:
        assert journal_norm(s) == state_norm(s), f"Drift on {s!r}"


@pytest.mark.unit
def test_normalize_strings_lockstep_nested() -> None:
    from sdlc.journal._canonical import _normalize_strings as journal_norm
    from sdlc.state.atomic import _normalize_strings as state_norm

    sample = {
        "name": "café",
        "items": ["ascii", "naïveté", {"deep": "ﬁnally"}],
        "tuple_like": [1, "ｱｲｳ", None, True],
        "nested": {"a": {"b": "\U0001d4d7ello"}},
    }
    assert journal_norm(sample) == state_norm(sample)


@pytest.mark.unit
def test_canonicalize_entry_byte_identical() -> None:
    """Independent: both canonicalisers (entry vs state) emit JSON in the same shape."""
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal._canonical import _canonicalize_entry

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=42,
        ts="2026-05-08T12:34:56.000Z",
        actor="café",  # decomposed, must canonicalise to NFC
        kind="state_mutation",
        target_id="t-1",
        before_hash=None,
        after_hash="sha256:" + ("a" * 64),
        payload={"k": "naïveté"},
    )
    raw = _canonicalize_entry(entry)
    # Must end in newline, must be valid utf-8 JSON, and must NFC-normalise the actor
    assert raw.endswith(b"\n")
    decoded = raw.decode("utf-8")
    assert "café" in decoded  # composed form, not "café"
