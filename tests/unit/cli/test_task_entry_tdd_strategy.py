"""Unit tests for the Story 3.8 ``_TaskEntry`` additions: ``tdd_strategy`` + ``touches`` (AC2).

``tdd_strategy`` is a real serialized field (default ``write-tests-first``) so ``/sdlc-task`` can
read it back off disk. ``touches`` is input-only (``exclude=True``, mirroring ``status``): the
task-breaker emits it so the CLI classifier can stamp ``tdd_strategy``, but it MUST NOT serialize.
``_TaskEntry`` is NOT a wire-format snapshot contract → no ADR-024 regen.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.unit

_VALID_STORY_ID = "EPIC-foo-S01-bar"
_VALID_TASK_ID = "EPIC-foo-S01-bar-T01-design-data-model"


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": _VALID_TASK_ID,
        "story_id": _VALID_STORY_ID,
        "label": "Design the data model.",
        "stage": "pending",
        "dependencies": [],
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# tdd_strategy — default + Literal constraint + serialization round-trip.
# ---------------------------------------------------------------------------


def test_tdd_strategy_defaults_to_write_tests_first() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_record())  # type: ignore[arg-type]
    assert entry.tdd_strategy == "write-tests-first"


def test_tdd_strategy_accepts_characterization_test() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_record(tdd_strategy="characterization-test"))  # type: ignore[arg-type]
    assert entry.tdd_strategy == "characterization-test"


def test_tdd_strategy_rejects_unknown_value() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    with pytest.raises(ValidationError):
        _TaskEntry(**_record(tdd_strategy="characterization"))  # type: ignore[arg-type]


def test_tdd_strategy_serializes_by_default() -> None:
    """AC2: tdd_strategy MUST serialize (unlike status) so /sdlc-task reads it back."""
    from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry

    entry = _TaskEntry(**_record())  # type: ignore[arg-type]
    parsed = json.loads(serialize_task_entry(entry))
    assert parsed["tdd_strategy"] == "write-tests-first"


def test_tdd_strategy_round_trips_through_serialize_and_reparse() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry

    original = _TaskEntry(**_record(tdd_strategy="characterization-test"))  # type: ignore[arg-type]
    restored = _TaskEntry(**json.loads(serialize_task_entry(original)))  # type: ignore[arg-type]
    assert restored.tdd_strategy == "characterization-test"


# ---------------------------------------------------------------------------
# touches — parsed from task-breaker output but NEVER serialized (exclude=True).
# ---------------------------------------------------------------------------


def test_touches_defaults_to_empty() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_record())  # type: ignore[arg-type]
    assert tuple(entry.touches) == ()


def test_touches_parses_from_input() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_record(touches=["src/legacy/foo.py", "src/legacy/bar.py"]))  # type: ignore[arg-type]
    assert tuple(entry.touches) == ("src/legacy/foo.py", "src/legacy/bar.py")


def test_touches_is_excluded_from_serialization() -> None:
    """touches is input-only — it must not leak into the on-disk task JSON (mirrors status)."""
    from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry

    entry = _TaskEntry(**_record(touches=["src/legacy/foo.py"]))  # type: ignore[arg-type]
    parsed = json.loads(serialize_task_entry(entry))
    assert "touches" not in parsed
