"""Tests for hooks/builtin/naming_validator.py (AC4, Story 2A.4 Task 3)."""

from __future__ import annotations

import pytest

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.builtin.naming_validator import naming_validator
from sdlc.ids.parsers import _EPIC_ID_PATTERN, _STORY_ID_PATTERN


def _p(path: str) -> HookPayload:
    return HookPayload(
        hook_name="naming_validator",
        target_path=path,
        target_kind="write_intent",
        content_hash_before=None,
        write_intent="test write",
    )


@pytest.mark.unit
class TestNamingValidatorEpicDir:
    def test_valid_epic_id_allows(self) -> None:
        result = naming_validator(_p("01-Requirement/04-Epics/EPIC-stripe-webhook.json"))
        assert result.decision == "allow"

    def test_invalid_epic_id_denies(self) -> None:
        result = naming_validator(_p("01-Requirement/04-Epics/EPC_typo.json"))
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"
        assert _EPIC_ID_PATTERN in (result.reason or "")

    def test_story_id_in_epic_dir_denies(self) -> None:
        """A story-shaped id in epic dir should deny (wrong shape)."""
        result = naming_validator(_p("01-Requirement/04-Epics/EPIC-foo-S01-bar.json"))
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"


@pytest.mark.unit
class TestNamingValidatorStoryDir:
    def test_valid_story_id_allows(self) -> None:
        result = naming_validator(
            _p("01-Requirement/05-Stories/EPIC-stripe-webhook/EPIC-stripe-webhook-S01-design.json")
        )
        assert result.decision == "allow"

    def test_story_dir_epic_id_shape_denies(self) -> None:
        result = naming_validator(_p("01-Requirement/05-Stories/EPIC-foo/EPIC-foo.json"))
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"

    def test_story_dir_malformed_parent_epic_denies(self) -> None:
        """Malformed parent epic directory → deny."""
        result = naming_validator(_p("01-Requirement/05-Stories/BAD_PARENT/EPIC-foo-S01-bar.json"))
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"
        assert "parent directory" in (result.reason or "")


@pytest.mark.unit
class TestNamingValidatorTaskDir:
    def test_valid_task_id_allows(self) -> None:
        result = naming_validator(
            _p(
                "01-Requirement/06-Tasks/EPIC-foo/EPIC-foo-S01-story/"
                "EPIC-foo-S01-story-T01-task.json"
            )
        )
        assert result.decision == "allow"

    def test_task_dir_malformed_grandparent_epic_denies(self) -> None:
        result = naming_validator(
            _p(
                "01-Requirement/06-Tasks/BAD_EPIC/EPIC-foo-S01-story/"
                "EPIC-foo-S01-story-T01-task.json"
            )
        )
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"

    def test_task_dir_malformed_parent_story_denies(self) -> None:
        result = naming_validator(
            _p("01-Requirement/06-Tasks/EPIC-foo/BAD_STORY/EPIC-foo-S01-story-T01-task.json")
        )
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"

    def test_task_dir_invalid_task_stem_denies(self) -> None:
        """Valid epic + story ancestors but invalid task stem → deny (lines 94-95 coverage)."""
        result = naming_validator(
            _p(
                "01-Requirement/06-Tasks/EPIC-foo/EPIC-foo-S01-story/BAD_TASK.json"
            )
        )
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"


@pytest.mark.unit
class TestNamingValidatorNonIdPaths:
    def test_architecture_path_allows(self) -> None:
        result = naming_validator(_p("02-Architecture/01-UX/01-tokens.md"))
        assert result.decision == "allow"

    def test_product_doc_allows(self) -> None:
        result = naming_validator(_p("01-Requirement/01-PRODUCT.md"))
        assert result.decision == "allow"

    def test_claude_state_path_allows(self) -> None:
        result = naming_validator(_p(".claude/state/signoffs/phase-1.yaml"))
        assert result.decision == "allow"

    def test_top_level_config_allows(self) -> None:
        result = naming_validator(_p("pyproject.toml"))
        assert result.decision == "allow"

    def test_dot_slash_prefix_stripped(self) -> None:
        """Path starting with './' has the leading dot stripped (line 107 coverage)."""
        result = naming_validator(_p("./01-Requirement/04-Epics/EPIC-stripe-webhook.json"))
        assert result.decision == "allow"

    def test_stories_dir_too_shallow_fallthrough_allows(self) -> None:
        """01-Requirement/05-Stories/<file> (only 3 parts) falls through to allow (line 125)."""
        result = naming_validator(_p("01-Requirement/05-Stories/README.md"))
        assert result.decision == "allow"

    def test_tasks_dir_too_shallow_fallthrough_allows(self) -> None:
        """01-Requirement/06-Tasks/<file> (only 3 parts) falls through to allow (line 125)."""
        result = naming_validator(_p("01-Requirement/06-Tasks/README.md"))
        assert result.decision == "allow"


@pytest.mark.unit
class TestNamingValidatorReason:
    def test_deny_reason_includes_full_regex(self) -> None:
        """Task 3.3 anti-tautology: deny reason must include full regex pattern."""
        result = naming_validator(_p("01-Requirement/04-Epics/EPC_typo.json"))
        assert result.decision == "deny"
        assert _EPIC_ID_PATTERN in (result.reason or "")

    def test_deny_story_reason_includes_story_regex(self) -> None:
        result = naming_validator(_p("01-Requirement/05-Stories/EPIC-foo/EPIC-foo.json"))
        assert result.decision == "deny"
        assert _STORY_ID_PATTERN in (result.reason or "")
