from __future__ import annotations

import pytest

from sdlc.config import sanitize_mapping
from sdlc.errors import SdlcError


@pytest.mark.integration
class TestSecretHygiene:
    def test_envelope_details_redacted(self) -> None:
        error = SdlcError(
            "test",
            details={"api_key": "sk-abc123def456ghi789jkl012mno345pq"},
        )
        envelope = error.to_envelope()
        details = envelope["error"]["details"]
        assert isinstance(details, dict)
        sanitized = sanitize_mapping(details)
        assert sanitized["api_key"] == "<REDACTED:secret>"

    def test_multi_pattern_envelope(self) -> None:
        error = SdlcError(
            "multi",
            details={
                "openai_key": "sk-abc123def456ghi789jkl012mno345pq",
                "github_pat": "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
                "aws_access": "AKIAIOSFODNN7EXAMPLE",
                "jwt": (
                    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
                    ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
                    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
                ),
                "stripe": "pk_live_abc123def456ghi789jkl0",
            },
        )
        details = error.to_envelope()["error"]["details"]
        assert isinstance(details, dict)
        sanitized = sanitize_mapping(details)
        assert all(v == "<REDACTED:secret>" for v in sanitized.values())

    def test_nested_envelope(self) -> None:
        error = SdlcError(
            "nested",
            details={
                "caller": {
                    "name": "agent",
                    "credentials": {"api_key": "sk-abc123def456ghi789jkl012mno345pq"},
                },
            },
        )
        details = error.to_envelope()["error"]["details"]
        assert isinstance(details, dict)
        sanitized = sanitize_mapping(details)
        caller = sanitized["caller"]
        assert isinstance(caller, dict)
        credentials = caller["credentials"]
        assert isinstance(credentials, dict)
        assert credentials["api_key"] == "<REDACTED:secret>"
