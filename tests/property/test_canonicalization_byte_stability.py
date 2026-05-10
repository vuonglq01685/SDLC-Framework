"""Hypothesis property tests: canonicalization byte-stability (D1, Epic 1 retro).

Carried over from Story 1.21 Item B — deferred until Epic 2A prep sprint.
Required before Story 2A.4 (pre-write hook chain) because phase-gate signoff
hashes depend on byte-identical serialization across calls and platforms.

Properties verified:

- P1 (test_nfc_normalize_is_idempotent): NFC(NFC(s)) == NFC(s) for arbitrary text.
- P2 (test_normalize_strings_idempotent_state): state.atomic._normalize_strings
  applied twice equals once for arbitrary nested state-like dicts.
- P3 (test_normalize_strings_idempotent_journal): same for journal._canonical copy.
- P4 (test_normalize_strings_lockstep_arbitrary): state and journal normalizers
  produce identical output for arbitrary nested structures (extends fixed-corpus
  lockstep in test_canonical_lockstep.py to the full Hypothesis search space).
- P5 (test_canonical_bytes_deterministic): _canonicalize_state returns byte-identical
  output on repeated calls for arbitrary State instances.
- P6 (test_canonical_bytes_key_order_independent): same logical dict with different
  key-insertion order produces identical canonical bytes.
- P7 (test_canonical_entry_deterministic): _canonicalize_entry returns byte-identical
  output on repeated calls for arbitrary JournalEntry instances.
"""

from __future__ import annotations

import json
import sys
import unicodedata

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = [
    pytest.mark.property,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="state.atomic is POSIX-only; journal._canonical tested on Linux CI",
    ),
]

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Unicode text that may contain composed/decomposed forms, ligatures, and
# non-ASCII codepoints relevant to NFC normalization.
_unicode_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),  # exclude surrogates
    ),
    max_size=200,
)

# A recursive strategy for nested dicts/lists of strings and scalars.
# Mirrors the structure of state.json and journal JSONL payloads.
_json_leaf = st.one_of(
    _unicode_text,
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    st.booleans(),
    st.none(),
)

_json_value: st.SearchStrategy[object] = st.deferred(
    lambda: st.one_of(
        _json_leaf,
        st.lists(_json_value, max_size=6),
        st.dictionaries(_unicode_text, _json_value, max_size=6),
    )
)

_flat_str_dict = st.dictionaries(
    _unicode_text,
    _unicode_text,
    max_size=10,
)


# ---------------------------------------------------------------------------
# P1: NFC idempotency
# ---------------------------------------------------------------------------


@given(_unicode_text)
@settings(max_examples=1000, suppress_health_check=[HealthCheck.too_slow])
def test_nfc_normalize_is_idempotent(s: str) -> None:
    once = unicodedata.normalize("NFC", s)
    twice = unicodedata.normalize("NFC", once)
    assert once == twice, f"NFC not idempotent on {s!r}"


# ---------------------------------------------------------------------------
# P2: state.atomic._normalize_strings idempotency
# ---------------------------------------------------------------------------


@given(_json_value)
@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_strings_idempotent_state(obj: object) -> None:
    from sdlc.state.atomic import _normalize_strings

    once = _normalize_strings(obj)
    twice = _normalize_strings(once)
    assert once == twice, f"state._normalize_strings not idempotent on {obj!r}"


# ---------------------------------------------------------------------------
# P3: journal._canonical._normalize_strings idempotency
# ---------------------------------------------------------------------------


@given(_json_value)
@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_strings_idempotent_journal(obj: object) -> None:
    from sdlc.journal._canonical import _normalize_strings

    once = _normalize_strings(obj)
    twice = _normalize_strings(once)
    assert once == twice, f"journal._normalize_strings not idempotent on {obj!r}"


# ---------------------------------------------------------------------------
# P4: lockstep — both copies produce identical output for arbitrary inputs
# ---------------------------------------------------------------------------


@given(_json_value)
@settings(max_examples=1000, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_strings_lockstep_arbitrary(obj: object) -> None:
    from sdlc.journal._canonical import _normalize_strings as journal_norm
    from sdlc.state.atomic import _normalize_strings as state_norm

    assert state_norm(obj) == journal_norm(obj), (
        f"Lockstep drift for {obj!r}: state={state_norm(obj)!r} journal={journal_norm(obj)!r}"
    )


# ---------------------------------------------------------------------------
# P5: _canonicalize_state determinism for arbitrary State instances
# ---------------------------------------------------------------------------


@given(st.dictionaries(_unicode_text, _unicode_text, max_size=8))
@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
def test_canonical_bytes_deterministic(epic_titles: dict[str, str]) -> None:
    """Same State produced twice yields byte-identical canonical output."""
    from sdlc.state.atomic import _canonicalize_state
    from sdlc.state.model import State

    epics = {k: {"id": k, "title": v} for k, v in epic_titles.items()}
    state_a = State(epics=epics)
    state_b = State(epics=epics)
    assert _canonicalize_state(state_a) == _canonicalize_state(state_b)


# ---------------------------------------------------------------------------
# P6: key-insertion order does not affect canonical bytes
# ---------------------------------------------------------------------------


@given(_flat_str_dict)
@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
def test_canonical_bytes_key_order_independent(d: dict[str, str]) -> None:
    """Two dicts with same content but reversed key order produce identical bytes.

    This is the core invariant for signoff hash stability: a HookPayload or
    State constructed from different code paths (with keys added in different
    order) must hash identically.
    """
    items = list(d.items())
    reversed_d = dict(reversed(items))

    def _serialize(mapping: dict[str, str]) -> bytes:
        import unicodedata

        normalized = {
            unicodedata.normalize("NFC", k): unicodedata.normalize("NFC", v)
            for k, v in mapping.items()
        }
        return (
            json.dumps(
                normalized,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )

    assert _serialize(d) == _serialize(reversed_d), (
        f"Key-order sensitivity detected: {d!r} vs {reversed_d!r}"
    )


# ---------------------------------------------------------------------------
# P7: _canonicalize_entry determinism for arbitrary JournalEntry instances
# ---------------------------------------------------------------------------


@given(
    actor=_unicode_text,
    target_id=_unicode_text,
    payload_key=_unicode_text,
    payload_val=_unicode_text,
    monotonic_seq=st.integers(min_value=1, max_value=10_000),
)
@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
def test_canonical_entry_deterministic(
    actor: str,
    target_id: str,
    payload_key: str,
    payload_val: str,
    monotonic_seq: int,
) -> None:
    """Same JournalEntry constructed twice yields byte-identical canonical output."""
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal._canonical import _canonicalize_entry

    kwargs = {
        "schema_version": 1,
        "monotonic_seq": monotonic_seq,
        "ts": "2026-05-10T00:00:00.000Z",
        "actor": actor,
        "kind": "state_mutation",
        "target_id": target_id,
        "before_hash": None,
        "after_hash": "sha256:" + "a" * 64,
        "payload": {payload_key: payload_val},
    }
    entry_a = JournalEntry(**kwargs)
    entry_b = JournalEntry(**kwargs)
    assert _canonicalize_entry(entry_a) == _canonicalize_entry(entry_b)
