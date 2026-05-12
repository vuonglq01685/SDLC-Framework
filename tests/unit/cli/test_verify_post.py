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
    is_verdict_malformed,
    parse_verdict_envelope,
)
from sdlc.errors import StateError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# parse_verdict_envelope: defensive fallbacks
# ---------------------------------------------------------------------------


def test_parse_verdict_envelope_empty_string_returns_advisory_none() -> None:
    """P36 / DC9 (post-review 2026-05-12 Cluster C-J): empty `output_text`
    is a non-decision; coerced to ``advisory`` (NOT ``verified`` — the
    DR7 silent-verified fallback was the most severe correctness failure
    mode). "advisory" routes through DC10 non-zero exit.
    """
    assert parse_verdict_envelope("") == ("advisory", None)
    assert parse_verdict_envelope("   \n\t ") == ("advisory", None)


def test_parse_verdict_envelope_invalid_json_returns_advisory_none() -> None:
    """P36 / DC9: garbage that fails `json.loads` → ``advisory``."""
    assert parse_verdict_envelope("not-json-at-all") == ("advisory", None)
    assert parse_verdict_envelope("{ unterminated") == ("advisory", None)


def test_parse_verdict_envelope_non_dict_json_returns_advisory_none() -> None:
    """P36 / DC9: valid JSON that isn't a mapping → ``advisory``."""
    assert parse_verdict_envelope('["list", "not", "dict"]') == ("advisory", None)
    assert parse_verdict_envelope('"bare string"') == ("advisory", None)
    assert parse_verdict_envelope("42") == ("advisory", None)


def test_parse_verdict_envelope_unknown_status_defaults_to_advisory() -> None:
    """P36 / DC9: verdict outside `ALLOWED_STATUSES` → ``advisory`` (note preserved)."""
    status, note = parse_verdict_envelope('{"verdict": "bogus-status", "note": "x"}')
    assert status == "advisory"
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


# ---------------------------------------------------------------------------
# is_verdict_malformed: P36 / DC9 detector for journal payload flag
# ---------------------------------------------------------------------------


def test_is_verdict_malformed_well_formed_returns_false() -> None:
    """A clean ``{"verdict": "verified", ...}`` payload is NOT malformed."""
    assert is_verdict_malformed('{"verdict": "verified", "note": "ok"}') is False
    assert is_verdict_malformed('{"verdict": "failed"}') is False
    assert is_verdict_malformed('{"verdict": "advisory", "note": "watch"}') is False


def test_is_verdict_malformed_empty_returns_true() -> None:
    """Empty / whitespace payload is a non-decision → malformed."""
    assert is_verdict_malformed("") is True
    assert is_verdict_malformed("   \n\t ") is True


def test_is_verdict_malformed_invalid_json_returns_true() -> None:
    """Unparseable JSON → malformed."""
    assert is_verdict_malformed("not-json") is True
    assert is_verdict_malformed("{ unterminated") is True


def test_is_verdict_malformed_non_dict_returns_true() -> None:
    """Valid JSON that isn't a mapping → malformed."""
    assert is_verdict_malformed("[1, 2, 3]") is True
    assert is_verdict_malformed('"bare string"') is True


def test_is_verdict_malformed_unknown_verdict_returns_true() -> None:
    """Verdict outside ALLOWED_STATUSES (incl. missing / non-string) → malformed."""
    assert is_verdict_malformed('{"verdict": "bogus"}') is True
    assert is_verdict_malformed('{"note": "no verdict key"}') is True
    assert is_verdict_malformed('{"verdict": ["verified"]}') is True  # unhashable (P28)
    assert is_verdict_malformed('{"verdict": null}') is True


def test_build_verification_entry_unknown_status_coerced_to_advisory() -> None:
    """P36 / DC9 (post-review 2026-05-12 Cluster C-J): out-of-band status
    coerces to ``advisory`` (not ``verified``) so silent misbehaviour
    surfaces as a flagged advisory + non-zero exit per DC10.
    """
    entry = build_verification_entry(
        verifier="artifact-verifier",
        status="not-a-real-status",
        note=None,
        body_hash="sha256:" + ("a" * 64),
    )
    assert entry.status == "advisory"


def test_build_verification_entry_status_failed_round_trips() -> None:
    """P31(a) / PC6 (post-review 2026-05-12 Cluster C-J): a verifier returning
    `{"verdict": "failed"}` MUST produce a `_Verification` row with
    ``status == "failed"`` (not silently coerced to "verified"). This pins
    the DC10-scoped P30 behaviour at the unit-test layer: verifier-decided
    failed verdicts survive the `build_verification_entry` step and flow to
    the frontmatter row + journal payload unchanged.
    """
    entry = build_verification_entry(
        verifier="artifact-verifier",
        status="failed",
        note="hand-rolled failure reason",
        body_hash="sha256:" + ("b" * 64),
    )
    assert entry.status == "failed"
    assert entry.verifier_note == "hand-rolled failure reason"
    assert entry.content_hash_at_verify == "sha256:" + ("b" * 64)


def test_build_verification_entry_status_advisory_round_trips() -> None:
    """`status="advisory"` is currently legal per AC6's `ALLOWED_STATUSES`
    enum (it's the DC9-deferred destination for unknown verdicts under P36).
    This pins it as a contract-supported value today.
    """
    entry = build_verification_entry(
        verifier="artifact-verifier",
        status="advisory",
        note=None,
        body_hash="sha256:" + ("c" * 64),
    )
    assert entry.status == "advisory"


# ---------------------------------------------------------------------------
# advance_state_seq: defensive return paths
# ---------------------------------------------------------------------------


def test_advance_state_seq_propagates_state_error(tmp_path: Path) -> None:
    """P13 / DC4=(1) (post-review 2026-05-12 Cluster C-J): `StateError` from
    the reader is NO LONGER silently swallowed. The function bubbles it up
    so the orchestrator can emit `ERR_STATE_CORRUPT` and surface terminal
    state corruption to the operator (vs the prior silent no-op which let
    the verify ceremony exit 0 even when state.json was unreadable).
    """
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("", encoding="utf-8")

    with (
        mock.patch("sdlc.journal._seq._read_highest_seq", return_value=0),
        mock.patch(
            "sdlc.state.read_state_or_recover", side_effect=StateError("simulated corruption")
        ),
        pytest.raises(StateError, match="simulated corruption"),
    ):
        advance_state_seq(state_path, journal_path)


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


def test_advance_state_seq_propagates_oserror_on_write(tmp_path: Path) -> None:
    """P13 / DC4=(1) (post-review 2026-05-12 Cluster C-J): a disk-write
    `OSError` is NO LONGER silently swallowed. The orchestrator wraps this
    into `ERR_STATE_SYNC_FAILED` so operators see that the state pointer
    drifted (retryable I/O failure, distinct from `ERR_STATE_CORRUPT`).
    """
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
        pytest.raises(OSError, match="disk full simulated"),
    ):
        advance_state_seq(state_path, journal_path)
