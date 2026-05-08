from __future__ import annotations

import pytest

from sdlc.errors import IdsError
from sdlc.ids import (
    EpicId,
    StoryId,
    TaskId,
    build_epic_id,
    build_story_id,
    build_task_id,
    parse_epic_id,
    parse_story_id,
    parse_task_id,
)


@pytest.mark.unit
def test_build_epic_id_happy_path() -> None:
    result = build_epic_id("stripe-webhook")
    assert isinstance(result, EpicId)
    assert result.raw == "EPIC-stripe-webhook"
    assert result.epic_slug == "stripe-webhook"


@pytest.mark.unit
def test_build_story_id_happy_path() -> None:
    result = build_story_id("stripe-webhook", 3, "capture-payment")
    assert isinstance(result, StoryId)
    assert result.raw == "EPIC-stripe-webhook-S03-capture-payment"
    assert result.story_num == 3


@pytest.mark.unit
def test_build_task_id_happy_path() -> None:
    result = build_task_id("stripe-webhook", 3, "capture-payment", 1, "validate-payload")
    assert isinstance(result, TaskId)
    assert result.raw == "EPIC-stripe-webhook-S03-capture-payment-T01-validate-payload"
    assert result.task_num == 1


@pytest.mark.unit
def test_build_story_id_zero_padding() -> None:
    result = build_story_id("foo", 5, "bar")
    assert result.raw == "EPIC-foo-S05-bar"


@pytest.mark.unit
def test_build_task_id_zero_padding() -> None:
    result = build_task_id("foo", 0, "bar", 9, "baz")
    assert result.raw == "EPIC-foo-S00-bar-T09-baz"


# Round-trip: parse → build → parse
@pytest.mark.unit
def test_epic_id_round_trip_build_then_parse() -> None:
    built = build_epic_id("my-epic")
    parsed = parse_epic_id(built.raw)
    assert parsed == built


@pytest.mark.unit
def test_story_id_round_trip_build_then_parse() -> None:
    built = build_story_id("my-epic", 7, "my-story")
    parsed = parse_story_id(built.raw)
    assert parsed == built


@pytest.mark.unit
def test_task_id_round_trip_build_then_parse() -> None:
    built = build_task_id("my-epic", 7, "my-story", 3, "my-task")
    parsed = parse_task_id(built.raw)
    assert parsed == built


# Round-trip: parse → unpack → build
@pytest.mark.unit
def test_epic_id_round_trip_parse_then_build() -> None:
    raw = "EPIC-stripe-webhook"
    parsed = parse_epic_id(raw)
    rebuilt = build_epic_id(parsed.epic_slug)
    assert rebuilt.raw == raw


@pytest.mark.unit
def test_story_id_round_trip_parse_then_build() -> None:
    raw = "EPIC-stripe-webhook-S03-capture-payment"
    parsed = parse_story_id(raw)
    rebuilt = build_story_id(parsed.epic_slug, parsed.story_num, parsed.story_slug)
    assert rebuilt.raw == raw


@pytest.mark.unit
def test_task_id_round_trip_parse_then_build() -> None:
    raw = "EPIC-stripe-webhook-S03-capture-payment-T01-validate-payload"
    parsed = parse_task_id(raw)
    rebuilt = build_task_id(
        parsed.epic_slug,
        parsed.story_num,
        parsed.story_slug,
        parsed.task_num,
        parsed.task_slug,
    )
    assert rebuilt.raw == raw


# Builder invalid_component validation
@pytest.mark.unit
@pytest.mark.parametrize(
    "epic_slug",
    ["Stripe", "stripe_webhook", "stripe-", "stripe--webhook"],
)
def test_build_epic_id_invalid_slug_raises(epic_slug: str) -> None:
    with pytest.raises(IdsError) as exc_info:
        build_epic_id(epic_slug)
    assert exc_info.value.details["rule"] == "invalid_component"


@pytest.mark.unit
@pytest.mark.parametrize("story_num", [-1, 100, 999])
def test_build_story_id_invalid_story_num_raises(story_num: int) -> None:
    with pytest.raises(IdsError) as exc_info:
        build_story_id("foo", story_num, "bar")
    assert exc_info.value.details["rule"] == "invalid_component"


@pytest.mark.unit
def test_build_story_id_boundary_valid() -> None:
    assert build_story_id("foo", 0, "bar").raw == "EPIC-foo-S00-bar"
    assert build_story_id("foo", 99, "bar").raw == "EPIC-foo-S99-bar"


@pytest.mark.unit
@pytest.mark.parametrize("task_num", [-1, 100])
def test_build_task_id_invalid_task_num_raises(task_num: int) -> None:
    with pytest.raises(IdsError) as exc_info:
        build_task_id("foo", 1, "bar", task_num, "baz")
    assert exc_info.value.details["rule"] == "invalid_component"


@pytest.mark.unit
def test_build_story_id_invalid_story_slug_raises() -> None:
    with pytest.raises(IdsError) as exc_info:
        build_story_id("foo", 1, "INVALID_SLUG")
    assert exc_info.value.details["rule"] == "invalid_component"


@pytest.mark.unit
def test_build_task_id_invalid_task_slug_raises() -> None:
    with pytest.raises(IdsError) as exc_info:
        build_task_id("foo", 1, "bar", 2, "INVALID")
    assert exc_info.value.details["rule"] == "invalid_component"


@pytest.mark.unit
def test_build_story_id_non_int_story_num_raises_type_error() -> None:
    with pytest.raises(TypeError, match=r"story_num must be int"):
        build_story_id("foo", "3", "bar")  # type: ignore[arg-type]


@pytest.mark.unit
def test_build_task_id_non_int_task_num_raises_type_error() -> None:
    with pytest.raises(TypeError, match=r"task_num must be int"):
        build_task_id("foo", 1, "bar", "2", "baz")  # type: ignore[arg-type]


@pytest.mark.unit
def test_build_story_id_float_story_num_raises_type_error() -> None:
    with pytest.raises(TypeError, match=r"story_num must be int"):
        build_story_id("foo", 3.5, "bar")  # type: ignore[arg-type]


@pytest.mark.unit
def test_build_task_id_float_task_num_raises_type_error() -> None:
    with pytest.raises(TypeError, match=r"task_num must be int"):
        build_task_id("foo", 1, "bar", 2.5, "baz")  # type: ignore[arg-type]


@pytest.mark.unit
def test_build_story_id_bool_story_num_raises_type_error() -> None:
    with pytest.raises(TypeError, match=r"story_num must be int"):
        build_story_id("foo", True, "bar")  # type: ignore[arg-type]


@pytest.mark.unit
def test_build_task_id_bool_task_num_raises_type_error() -> None:
    with pytest.raises(TypeError, match=r"task_num must be int"):
        build_task_id("foo", 1, "bar", False, "baz")  # type: ignore[arg-type]


@pytest.mark.unit
def test_build_story_id_invalid_epic_slug_raises() -> None:
    with pytest.raises(IdsError) as exc_info:
        build_story_id("INVALID_SLUG", 1, "bar")
    assert exc_info.value.details["rule"] == "invalid_component"


@pytest.mark.unit
def test_build_task_id_invalid_epic_slug_raises() -> None:
    with pytest.raises(IdsError) as exc_info:
        build_task_id("INVALID_SLUG", 1, "bar", 2, "baz")
    assert exc_info.value.details["rule"] == "invalid_component"


@pytest.mark.unit
def test_build_task_id_invalid_story_num_raises() -> None:
    with pytest.raises(IdsError) as exc_info:
        build_task_id("foo", -1, "bar", 2, "baz")
    assert exc_info.value.details["rule"] == "invalid_component"


@pytest.mark.unit
def test_build_task_id_invalid_story_slug_raises() -> None:
    with pytest.raises(IdsError) as exc_info:
        build_task_id("foo", 1, "INVALID_SLUG", 2, "baz")
    assert exc_info.value.details["rule"] == "invalid_component"
