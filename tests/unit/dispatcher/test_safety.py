"""Unit tests for dispatcher.safety — Story 2B.6 AC3 (RED → GREEN via TDD)."""

from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import patch

import pytest

from sdlc.dispatcher.safety import (
    _DESTRUCTIVE_TOOL_PATTERNS,
    is_destructive,
    prompt_for_reconfirmation,
    tool_call_excerpt,
)

# ---------------------------------------------------------------------------
# is_destructive — pattern detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_is_destructive_file_delete_rm_rf() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "rm -rf /some/path"}
    flagged, category = is_destructive(tc)
    assert flagged is True
    assert category == "file_delete"


@pytest.mark.unit
def test_is_destructive_file_delete_rm_fr() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "rm -fr /tmp/dir"}
    flagged, category = is_destructive(tc)
    assert flagged is True
    assert category == "file_delete"


@pytest.mark.unit
def test_is_destructive_force_push_short_flag() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "git push -f origin main"}
    flagged, category = is_destructive(tc)
    assert flagged is True
    assert category == "force_push"


@pytest.mark.unit
def test_is_destructive_force_push_long_flag() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "git push --force origin HEAD"}
    flagged, category = is_destructive(tc)
    assert flagged is True
    assert category == "force_push"


@pytest.mark.unit
def test_is_destructive_force_push_with_lease() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "git push --force-with-lease"}
    flagged, category = is_destructive(tc)
    assert flagged is True
    assert category == "force_push"


@pytest.mark.unit
def test_is_destructive_drop_database_uppercase() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "DROP DATABASE mydb;"}
    flagged, category = is_destructive(tc)
    assert flagged is True
    assert category == "drop_database"


@pytest.mark.unit
def test_is_destructive_drop_table_lowercase() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "drop table users"}
    flagged, category = is_destructive(tc)
    assert flagged is True
    assert category == "drop_database"


@pytest.mark.unit
def test_is_destructive_drop_schema() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "DROP SCHEMA public CASCADE;"}
    flagged, category = is_destructive(tc)
    assert flagged is True
    assert category == "drop_database"


@pytest.mark.unit
def test_is_destructive_safe_command_returns_false() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": "echo hello world"}
    flagged, category = is_destructive(tc)
    assert flagged is False
    assert category is None


@pytest.mark.unit
def test_is_destructive_empty_tool_call_returns_false() -> None:
    flagged, category = is_destructive({})
    assert flagged is False
    assert category is None


@pytest.mark.unit
def test_is_destructive_non_bash_tool_returns_false() -> None:
    tc: Mapping[str, object] = {"name": "Write", "command": "rm -rf /"}
    flagged, category = is_destructive(tc)
    assert flagged is False
    assert category is None


@pytest.mark.unit
def test_is_destructive_non_string_command_returns_false() -> None:
    tc: Mapping[str, object] = {"name": "Bash", "command": 42}
    flagged, category = is_destructive(tc)
    assert flagged is False
    assert category is None


@pytest.mark.unit
def test_patterns_registry_has_expected_categories() -> None:
    assert "file_delete" in _DESTRUCTIVE_TOOL_PATTERNS
    assert "force_push" in _DESTRUCTIVE_TOOL_PATTERNS
    assert "drop_database" in _DESTRUCTIVE_TOOL_PATTERNS


# ---------------------------------------------------------------------------
# tool_call_excerpt
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tool_call_excerpt_returns_command_truncated_at_200() -> None:
    long_cmd = "x" * 300
    tc: Mapping[str, object] = {"name": "Bash", "command": long_cmd}
    excerpt = tool_call_excerpt(tc)
    assert len(excerpt) == 200
    assert excerpt == long_cmd[:200]


@pytest.mark.unit
def test_tool_call_excerpt_falls_back_to_str_repr_for_non_string_command() -> None:
    tc: Mapping[str, object] = {"name": "Bash"}
    excerpt = tool_call_excerpt(tc)
    assert isinstance(excerpt, str)


# ---------------------------------------------------------------------------
# prompt_for_reconfirmation — nonce echo check
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_prompt_for_reconfirmation_correct_nonce_returns_true() -> None:
    nonce = "abc123xyz"
    with patch("builtins.input", return_value=nonce):
        result = prompt_for_reconfirmation(
            nonce=nonce, category="file_delete", tool_call_excerpt="rm -rf /"
        )
    assert result is True


@pytest.mark.unit
def test_prompt_for_reconfirmation_wrong_nonce_returns_false() -> None:
    nonce = "abc123xyz"
    with patch("builtins.input", return_value="wrong-answer"):
        result = prompt_for_reconfirmation(
            nonce=nonce, category="file_delete", tool_call_excerpt="rm -rf /"
        )
    assert result is False


@pytest.mark.unit
def test_prompt_for_reconfirmation_partial_nonce_returns_false() -> None:
    nonce = "abc123xyz"
    with patch("builtins.input", return_value="abc123"):
        result = prompt_for_reconfirmation(
            nonce=nonce, category="file_delete", tool_call_excerpt="rm -rf /"
        )
    assert result is False


@pytest.mark.unit
def test_prompt_for_reconfirmation_yes_literal_returns_false() -> None:
    nonce = "secret-nonce-99"
    with patch("builtins.input", return_value="yes"):
        result = prompt_for_reconfirmation(
            nonce=nonce, category="force_push", tool_call_excerpt="git push -f"
        )
    assert result is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "category",
    ["file_delete", "force_push", "drop_database"],
)
def test_prompt_for_reconfirmation_includes_category_in_prompt(category: str) -> None:
    nonce = "test-nonce"
    captured: list[str] = []

    def fake_input(prompt: str) -> str:
        captured.append(prompt)
        return nonce

    with patch("builtins.input", side_effect=fake_input):
        prompt_for_reconfirmation(nonce=nonce, category=category, tool_call_excerpt="cmd")

    assert captured, "input() was not called"
    assert category in captured[0]


@pytest.mark.unit
def test_prompt_for_reconfirmation_includes_nonce_in_prompt() -> None:
    nonce = "unique-nonce-xyz"
    captured: list[str] = []

    def fake_input(prompt: str) -> str:
        captured.append(prompt)
        return nonce

    with patch("builtins.input", side_effect=fake_input):
        prompt_for_reconfirmation(nonce=nonce, category="file_delete", tool_call_excerpt="rm -rf /")

    assert nonce in captured[0]
