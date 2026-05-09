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
