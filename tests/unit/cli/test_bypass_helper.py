"""Tests for cli/_bypass.py bypass validation helper (AC6, Story 2A.4 Task 7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sdlc.cli._bypass import truncate_justification, validate_bypass_request
from sdlc.errors import HookError


def _make_report(status: str):
    report = MagicMock()
    report.status = status
    return report


@pytest.mark.unit
class TestValidateBypassRequest:
    def test_valid_request_returns_none(self, tmp_path) -> None:
        with patch("sdlc.cli._bypass.detect_tampering") as mock_dt:
            mock_dt.return_value = _make_report("clean")
            result = validate_bypass_request("a valid justification", repo_root=tmp_path)
            assert result is None

    def test_short_justification_raises_hook_error(self, tmp_path) -> None:
        with patch("sdlc.cli._bypass.detect_tampering") as mock_dt:
            mock_dt.return_value = _make_report("clean")
            with pytest.raises(HookError, match="10 characters"):
                validate_bypass_request("short", repo_root=tmp_path)

    def test_exactly_9_chars_raises(self, tmp_path) -> None:
        with patch("sdlc.cli._bypass.detect_tampering") as mock_dt:
            mock_dt.return_value = _make_report("clean")
            with pytest.raises(HookError):
                validate_bypass_request("123456789", repo_root=tmp_path)

    def test_exactly_10_chars_passes(self, tmp_path) -> None:
        with patch("sdlc.cli._bypass.detect_tampering") as mock_dt:
            mock_dt.return_value = _make_report("clean")
            result = validate_bypass_request("1234567890", repo_root=tmp_path)
            assert result is None

    def test_uninitialized_trust_raises(self, tmp_path) -> None:
        with patch("sdlc.cli._bypass.detect_tampering") as mock_dt:
            mock_dt.return_value = _make_report("uninitialized")
            with pytest.raises(HookError, match="trust"):
                validate_bypass_request("valid justification text", repo_root=tmp_path)

    def test_corrupted_trust_raises(self, tmp_path) -> None:
        with patch("sdlc.cli._bypass.detect_tampering") as mock_dt:
            mock_dt.return_value = _make_report("corrupted")
            with pytest.raises(HookError, match="trust"):
                validate_bypass_request("valid justification text", repo_root=tmp_path)

    def test_tampered_trust_passes(self, tmp_path) -> None:
        """Tampered is advisory-only in v1; bypass is still allowed."""
        with patch("sdlc.cli._bypass.detect_tampering") as mock_dt:
            mock_dt.return_value = _make_report("tampered")
            result = validate_bypass_request("valid justification text", repo_root=tmp_path)
            assert result is None

    def test_error_message_contains_trust_hooks(self, tmp_path) -> None:
        with patch("sdlc.cli._bypass.detect_tampering") as mock_dt:
            mock_dt.return_value = _make_report("uninitialized")
            with pytest.raises(HookError, match="trust-hooks"):
                validate_bypass_request("valid justification text", repo_root=tmp_path)


@pytest.mark.unit
class TestTruncateJustification:
    def test_short_text_unchanged(self) -> None:
        text, truncated = truncate_justification("hello", max_len=500)
        assert text == "hello"
        assert truncated is False

    def test_exact_max_unchanged(self) -> None:
        text = "a" * 500
        result, truncated = truncate_justification(text, max_len=500)
        assert result == text
        assert truncated is False

    def test_over_max_truncated(self) -> None:
        text = "a" * 501
        result, truncated = truncate_justification(text, max_len=500)
        assert len(result) == 500
        assert truncated is True

    def test_default_max_500(self) -> None:
        text = "b" * 600
        result, truncated = truncate_justification(text)
        assert len(result) == 500
        assert truncated is True
