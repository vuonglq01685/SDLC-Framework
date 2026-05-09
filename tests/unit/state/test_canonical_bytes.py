"""Tests for state_to_canonical_bytes helper (Story 1.17, Task 3)."""

from __future__ import annotations

import json

import pytest

from sdlc.state import State, state_to_canonical_bytes

pytestmark = pytest.mark.unit


def test_canonical_bytes_round_trip() -> None:
    s = State()
    b = state_to_canonical_bytes(s)
    parsed = json.loads(b.decode("utf-8"))
    s2 = State.model_validate(parsed)
    assert s == s2


def test_canonical_bytes_byte_equal_across_calls() -> None:
    b1 = state_to_canonical_bytes(State())
    b2 = state_to_canonical_bytes(State())
    assert b1 == b2


def test_canonical_bytes_sorted_keys() -> None:
    b = state_to_canonical_bytes(State())
    parsed = json.loads(b.decode("utf-8"))
    keys = list(parsed.keys())
    assert keys == sorted(keys)


def test_canonical_bytes_trailing_newline() -> None:
    assert state_to_canonical_bytes(State()).endswith(b"\n")


def test_canonical_bytes_compact_separators() -> None:
    b = state_to_canonical_bytes(State())
    text = b.decode("utf-8")
    assert ": " not in text and ",\n" not in text


def test_canonical_bytes_no_ascii_escaping_for_unicode() -> None:
    """Story 1.17 review: ensure_ascii=False is verified with a real Unicode payload.

    Without this test, a regression to `ensure_ascii=True` would flip non-ASCII
    characters to `\\uNNNN` escapes silently, breaking byte-equality with the
    POSIX atomic-write protocol's canonical-bytes contract on cross-platform
    state.json snapshots.
    """
    state = State(epics={"EPIC-é-中-🦀": {"id": "EPIC-é-中-🦀", "title": "café 中文 🦀"}})
    b = state_to_canonical_bytes(state)
    text = b.decode("utf-8")
    # Literal Unicode codepoints must be present, NOT \uNNNN escapes.
    assert "é" in text
    assert "中" in text
    assert "🦀" in text
    assert "\\u" not in text
    # Round-trip preserves the Unicode content.
    parsed = json.loads(text)
    assert "EPIC-é-中-🦀" in parsed["epics"]
