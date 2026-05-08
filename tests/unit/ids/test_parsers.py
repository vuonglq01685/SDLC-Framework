from __future__ import annotations

from collections.abc import Callable

import pytest

from sdlc.errors import IdsError
from sdlc.ids import EpicId, StoryId, TaskId, parse_epic_id, parse_story_id, parse_task_id


@pytest.mark.unit
def test_parse_epic_id_happy_path() -> None:
    result = parse_epic_id("EPIC-stripe-webhook")
    assert isinstance(result, EpicId)
    assert result.raw == "EPIC-stripe-webhook"
    assert result.epic_slug == "stripe-webhook"


@pytest.mark.unit
def test_parse_story_id_happy_path() -> None:
    result = parse_story_id("EPIC-stripe-webhook-S03-capture-payment")
    assert isinstance(result, StoryId)
    assert result.raw == "EPIC-stripe-webhook-S03-capture-payment"
    assert result.epic_slug == "stripe-webhook"
    assert result.story_num == 3
    assert result.story_slug == "capture-payment"


@pytest.mark.unit
def test_parse_task_id_happy_path() -> None:
    result = parse_task_id("EPIC-stripe-webhook-S03-capture-payment-T01-validate-payload")
    assert isinstance(result, TaskId)
    assert result.raw == "EPIC-stripe-webhook-S03-capture-payment-T01-validate-payload"
    assert result.epic_slug == "stripe-webhook"
    assert result.story_num == 3
    assert result.story_slug == "capture-payment"
    assert result.task_num == 1
    assert result.task_slug == "validate-payload"


# 6-row failure-mode table from AC2 (parse_task_id of "EPIC-foo-S04-bar"
# is now caught by symmetric wrong_id_shape detection — see dedicated tests below)
@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,parse_fn,expected_rule",
    [
        ("", parse_epic_id, "empty_or_non_string"),
        ("stripe-webhook", parse_epic_id, "missing_epic_prefix"),
        ("EPIC-Stripe_Webhook", parse_epic_id, "invalid_slug"),
        ("EPIC-foo-S4-bar", parse_story_id, "invalid_story_shape"),
        ("EPIC-foo-S04-bar-T1-baz", parse_task_id, "invalid_task_shape"),
        ("EPIC-foo-S04-bar", parse_epic_id, "wrong_id_shape"),
    ],
    ids=[
        "empty_or_non_string",
        "missing_epic_prefix",
        "invalid_slug",
        "invalid_story_shape",
        "invalid_task_shape",
        "wrong_id_shape",
    ],
)
def test_parse_failure_raises_ids_error_with_rule(
    raw: str,
    parse_fn: Callable[[str], EpicId | StoryId | TaskId],
    expected_rule: str,
) -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_fn(raw)
    assert exc_info.value.details["rule"] == expected_rule


@pytest.mark.unit
def test_epic_id_prefix_lowercase_rejected() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_epic_id("epic-stripe-webhook")
    assert exc_info.value.details["rule"] == "missing_epic_prefix"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "EPIC-a",  # single character slug: valid
        "EPIC-1abc",  # leading digit: valid per regex
        "EPIC-checkout-v2",  # digit inside slug: valid
    ],
)
def test_epic_id_slug_valid_edge_cases(raw: str) -> None:
    result = parse_epic_id(raw)
    assert result.raw == raw


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "EPIC-stripe-",  # trailing dash: invalid
        "EPIC-stripe--webhook",  # double dash: invalid
        "EPIC-Stripe",  # uppercase: invalid
        "EPIC-stripe_webhook",  # underscore: invalid
    ],
)
def test_epic_id_slug_invalid_edge_cases(raw: str) -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_epic_id(raw)
    assert exc_info.value.details["rule"] == "invalid_slug"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "EPIC-foo-S00-bar",  # S00: valid
        "EPIC-foo-S99-bar",  # S99: valid
    ],
)
def test_story_num_edge_cases_valid(raw: str) -> None:
    result = parse_story_id(raw)
    assert result.raw == raw


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "EPIC-foo-S100-bar",  # 3 digits with uppercase S: invalid (not a valid epic slug either)
        "EPIC-foo-S0-bar",  # 1 digit with uppercase S: invalid (not a valid epic slug either)
    ],
)
def test_story_num_edge_cases_invalid_shape(raw: str) -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_story_id(raw)
    assert exc_info.value.details["rule"] == "invalid_story_shape"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "EPIC-foo-s04-bar",  # lowercase s — parses as a valid epic id
        "EPIC-foo-bar",  # no story-num portion — parses as a valid epic id
    ],
)
def test_story_id_parser_detects_epic_shaped_input(raw: str) -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_story_id(raw)
    assert exc_info.value.details["rule"] == "wrong_id_shape"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "EPIC-foo-S04-bar-T00-baz",  # T00: valid
        "EPIC-foo-S04-bar-T99-baz",  # T99: valid
    ],
)
def test_task_num_edge_cases_valid(raw: str) -> None:
    result = parse_task_id(raw)
    assert result.raw == raw


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "EPIC-foo-S04-bar-T100-baz",  # 3 digits with uppercase T: invalid
        "EPIC-foo-S04-bar-T1-baz",  # 1 digit with uppercase T: invalid
    ],
)
def test_task_num_edge_cases_invalid_shape(raw: str) -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_task_id(raw)
    assert exc_info.value.details["rule"] == "invalid_task_shape"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "EPIC-foo-S04-bar-t01-baz",  # lowercase t — full string parses as a valid story id
        "EPIC-foo-S04-bar",  # bare story id passed to parse_task_id
    ],
)
def test_task_id_parser_detects_story_shaped_input(raw: str) -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_task_id(raw)
    assert exc_info.value.details["rule"] == "wrong_id_shape"


@pytest.mark.unit
def test_task_id_parser_detects_epic_shaped_input() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_task_id("EPIC-foo")
    assert exc_info.value.details["rule"] == "wrong_id_shape"


@pytest.mark.unit
def test_story_id_parser_detects_task_shaped_input() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_story_id("EPIC-foo-S04-bar-T01-baz")
    assert exc_info.value.details["rule"] == "wrong_id_shape"


@pytest.mark.unit
def test_ids_error_details_contain_input_field() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_epic_id("")
    assert "input" in exc_info.value.details


@pytest.mark.unit
def test_epic_id_is_frozen_dataclass() -> None:
    result = parse_epic_id("EPIC-foo")
    with pytest.raises(AttributeError, match=r"cannot assign"):
        result.raw = "mutated"  # type: ignore[misc]


@pytest.mark.unit
def test_story_id_frozen_dataclass() -> None:
    result = parse_story_id("EPIC-foo-S01-bar")
    with pytest.raises(AttributeError, match=r"cannot assign"):
        result.story_num = 99  # type: ignore[misc]


@pytest.mark.unit
def test_parse_epic_id_task_shaped_input_raises_wrong_id_shape() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_epic_id("EPIC-foo-S04-bar-T01-baz")
    assert exc_info.value.details["rule"] == "wrong_id_shape"


@pytest.mark.unit
def test_parse_story_id_empty_raises_empty_or_non_string() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_story_id("")
    assert exc_info.value.details["rule"] == "empty_or_non_string"


@pytest.mark.unit
def test_parse_story_id_missing_prefix_raises() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_story_id("no-prefix-here")
    assert exc_info.value.details["rule"] == "missing_epic_prefix"


@pytest.mark.unit
def test_parse_story_id_missing_prefix_message_says_story() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_story_id("no-prefix-here")
    assert "story identifier" in exc_info.value.message


@pytest.mark.unit
def test_parse_task_id_empty_raises_empty_or_non_string() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_task_id("")
    assert exc_info.value.details["rule"] == "empty_or_non_string"


@pytest.mark.unit
def test_parse_task_id_missing_prefix_raises() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_task_id("no-prefix-here")
    assert exc_info.value.details["rule"] == "missing_epic_prefix"


@pytest.mark.unit
def test_parse_task_id_missing_prefix_message_says_task() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_task_id("no-prefix-here")
    assert "task identifier" in exc_info.value.message
