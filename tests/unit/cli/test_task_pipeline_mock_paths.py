"""Story 3.8 review (F5): the characterization-author mock body must derive a task-specific
test filename, so two characterization tasks (e.g. sharing a ``T01`` number across stories)
do not collide on the same ``tests/unit/...`` path and clobber each other in mock-mode runs.
"""

from __future__ import annotations

import json

import pytest

from sdlc.cli._task_pipeline_mocks import mock_characterization_author_body

pytestmark = pytest.mark.unit


def _path(task_id: str) -> str:
    return json.loads(mock_characterization_author_body(task_id))["files"][0]["path"]


def test_characterization_mock_path_is_unique_per_task() -> None:
    a = _path("EPIC-x-S01-alpha-T01-characterize-core")
    b = _path("EPIC-y-S02-beta-T01-characterize-other")

    # Same T-number, different stories/tasks → distinct files (no clobber).
    assert a != b
    assert a.startswith("tests/") and a.endswith("_characterization.py")
    assert b.startswith("tests/") and b.endswith("_characterization.py")
