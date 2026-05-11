"""Unit coverage for `sdlc.cli._verify_post` defensive branches (Story 2A.10).

The post-dispatch module is exercised end-to-end through the integration +
e2e suites; this file pins the *defensive* fallbacks directly so the gate
holds ≥90% line+branch coverage on the module even when the dispatcher
returns malformed payloads or the on-disk state is unreadable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from sdlc.cli._verify_post import (
    advance_state_seq,
    build_verification_entry,
    parse_verdict_envelope,
)
from sdlc.errors import StateError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# parse_verdict_envelope: defensive fallbacks
# ---------------------------------------------------------------------------


def test_parse_verdict_envelope_empty_string_returns_verified_none() -> None:
    """Empty `output_text` (mock runtime, no payload) — fall back."""
    assert parse_verdict_envelope("") == ("verified", None)
    assert parse_verdict_envelope("   \n\t ") == ("verified", None)


def test_parse_verdict_envelope_invalid_json_returns_verified_none() -> None:
    """Garbage that fails `json.loads` — fall back to verified/None."""
    assert parse_verdict_envelope("not-json-at-all") == ("verified", None)
    assert parse_verdict_envelope("{ unterminated") == ("verified", None)


def test_parse_verdict_envelope_non_dict_json_returns_verified_none() -> None:
    """Valid JSON that isn't an object — fall back."""
    assert parse_verdict_envelope('["list", "not", "dict"]') == ("verified", None)
    assert parse_verdict_envelope('"bare string"') == ("verified", None)
    assert parse_verdict_envelope("42") == ("verified", None)


def test_parse_verdict_envelope_unknown_status_defaults_to_verified() -> None:
    """Verdict outside `ALLOWED_STATUSES` is coerced to ``verified``."""
    status, note = parse_verdict_envelope('{"verdict": "bogus-status", "note": "x"}')
    assert status == "verified"
    assert note == "x"


def test_parse_verdict_envelope_advisory_with_note_round_trips() -> None:
    """Known status + note survives — anti-tautology for the happy branch."""
    status, note = parse_verdict_envelope('{"verdict": "advisory", "note": "watch SLI"}')
    assert status == "advisory"
    assert note == "watch SLI"


def test_parse_verdict_envelope_empty_note_returns_none() -> None:
    """Falsy note string is normalised to `None`."""
    status, note = parse_verdict_envelope('{"verdict": "verified", "note": ""}')
    assert status == "verified"
    assert note is None


# ---------------------------------------------------------------------------
# build_verification_entry: status fallback
# ---------------------------------------------------------------------------


def test_build_verification_entry_unknown_status_coerced_to_verified() -> None:
    """A caller passing an out-of-band status is normalised, never raised."""
    entry = build_verification_entry(
        verifier="artifact-verifier",
        status="not-a-real-status",
        note=None,
        body_hash="sha256:" + ("a" * 64),
    )
    assert entry.status == "verified"


# ---------------------------------------------------------------------------
# advance_state_seq: defensive return paths
# ---------------------------------------------------------------------------


def test_advance_state_seq_swallows_state_error(tmp_path: Path) -> None:
    """`StateError` from the reader is swallowed (best-effort sync)."""
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("", encoding="utf-8")

    with (
        mock.patch("sdlc.journal._seq._read_highest_seq", return_value=0),
        mock.patch(
            "sdlc.state.read_state_or_recover", side_effect=StateError("simulated corruption")
        ),
    ):
        advance_state_seq(state_path, journal_path)  # MUST NOT raise


def test_advance_state_seq_returns_when_pre_is_none(tmp_path: Path) -> None:
    """If the reader returns `None`, the function bails without writing."""
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("", encoding="utf-8")

    with (
        mock.patch("sdlc.journal._seq._read_highest_seq", return_value=0),
        mock.patch("sdlc.state.read_state_or_recover", return_value=None),
        mock.patch("sdlc.state.write_state_atomic_sync") as writer,
    ):
        advance_state_seq(state_path, journal_path)
        writer.assert_not_called()


def test_advance_state_seq_no_op_when_already_caught_up(tmp_path: Path) -> None:
    """If `next_monotonic_seq` already covers the journal, no write happens."""
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("", encoding="utf-8")

    fake_state = mock.MagicMock()
    fake_state.next_monotonic_seq = 42  # already ahead of highest_seq+1 = 11

    with (
        mock.patch("sdlc.journal._seq._read_highest_seq", return_value=10),
        mock.patch("sdlc.state.read_state_or_recover", return_value=fake_state),
        mock.patch("sdlc.state.write_state_atomic_sync") as writer,
    ):
        advance_state_seq(state_path, journal_path)
        writer.assert_not_called()


def test_advance_state_seq_swallows_oserror_on_write(tmp_path: Path) -> None:
    """A disk-write `OSError` is swallowed — the journal stays authoritative."""
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("", encoding="utf-8")

    fake_state = mock.MagicMock()
    fake_state.next_monotonic_seq = 1

    def _copy_update(*, update: dict[str, Any]) -> mock.MagicMock:
        m = mock.MagicMock()
        m.next_monotonic_seq = update["next_monotonic_seq"]
        return m

    fake_state.model_copy.side_effect = _copy_update

    with (
        mock.patch("sdlc.journal._seq._read_highest_seq", return_value=10),
        mock.patch("sdlc.state.read_state_or_recover", return_value=fake_state),
        mock.patch(
            "sdlc.state.write_state_atomic_sync", side_effect=OSError("disk full simulated")
        ),
    ):
        advance_state_seq(state_path, journal_path)  # MUST NOT raise
