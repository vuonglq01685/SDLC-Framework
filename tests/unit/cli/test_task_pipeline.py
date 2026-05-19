"""Unit tests for _task_pipeline.py — stage maps and per-stage response parsers
(Story 2A.17, AC3-AC5, Task 3.1).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Stage → specialist + next-stage maps
# ---------------------------------------------------------------------------


def test_stage_specialist_map_all_keys_present() -> None:
    """_STAGE_SPECIALIST covers all dispatch stages + review (None)."""
    from sdlc.cli._task_pipeline import _STAGE_SPECIALIST

    assert set(_STAGE_SPECIALIST.keys()) == {"pending", "write-tests", "write-code", "review"}
    assert _STAGE_SPECIALIST["pending"] == "test-author"
    assert _STAGE_SPECIALIST["write-tests"] == "code-author"
    assert _STAGE_SPECIALIST["write-code"] == "code-reviewer"
    assert _STAGE_SPECIALIST["review"] is None


def test_next_stage_map_all_keys_present() -> None:
    """_NEXT_STAGE covers all advanceable stages."""
    from sdlc.cli._task_pipeline import _NEXT_STAGE

    assert set(_NEXT_STAGE.keys()) == {"pending", "write-tests", "write-code", "review"}
    assert _NEXT_STAGE["pending"] == "write-tests"
    assert _NEXT_STAGE["write-tests"] == "write-code"
    assert _NEXT_STAGE["write-code"] == "review"
    assert _NEXT_STAGE["review"] == "done"


# ---------------------------------------------------------------------------
# _StageFilesResult parser — happy path
# ---------------------------------------------------------------------------


def test_stage_files_result_valid_parses_cleanly() -> None:
    from sdlc.cli._task_pipeline_parsers import _StageFilesResult

    result = _StageFilesResult.model_validate(
        {
            "files": [{"path": "tests/unit/test_foo.py", "content": "# test"}],
            "tests_status": "red",
        }
    )
    assert len(result.files) == 1
    assert result.files[0].path == "tests/unit/test_foo.py"
    assert result.tests_status == "red"


def test_stage_files_result_green_status() -> None:
    from sdlc.cli._task_pipeline_parsers import _StageFilesResult

    result = _StageFilesResult.model_validate(
        {
            "files": [{"path": "src/sdlc/foo.py", "content": "x = 1"}],
            "tests_status": "green",
        }
    )
    assert result.tests_status == "green"


def test_stage_files_result_multiple_files() -> None:
    from sdlc.cli._task_pipeline_parsers import _StageFilesResult

    result = _StageFilesResult.model_validate(
        {
            "files": [
                {"path": "tests/unit/test_a.py", "content": "# a"},
                {"path": "tests/unit/test_b.py", "content": "# b"},
            ],
            "tests_status": "red",
        }
    )
    assert len(result.files) == 2


# ---------------------------------------------------------------------------
# _StageFilesResult parser — error paths
# ---------------------------------------------------------------------------


def test_stage_files_result_empty_files_raises_error() -> None:
    """files must be non-empty (min_length=1)."""
    from pydantic import ValidationError

    from sdlc.cli._task_pipeline_parsers import _StageFilesResult

    with pytest.raises(ValidationError):
        _StageFilesResult.model_validate({"files": [], "tests_status": "red"})


def test_stage_files_result_missing_tests_status_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._task_pipeline_parsers import _StageFilesResult

    with pytest.raises(ValidationError):
        _StageFilesResult.model_validate({"files": [{"path": "tests/foo.py", "content": "x"}]})


def test_stage_files_result_invalid_tests_status_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._task_pipeline_parsers import _StageFilesResult

    with pytest.raises(ValidationError):
        _StageFilesResult.model_validate(
            {"files": [{"path": "tests/foo.py", "content": "x"}], "tests_status": "yellow"}
        )


def test_stage_files_result_non_list_files_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._task_pipeline_parsers import _StageFilesResult

    with pytest.raises(ValidationError):
        _StageFilesResult.model_validate({"files": "not-a-list", "tests_status": "red"})


# ---------------------------------------------------------------------------
# Per-stage path-prefix validator
# ---------------------------------------------------------------------------


def test_validate_file_prefix_tests_passes_for_tests_path() -> None:
    from sdlc.cli._task_pipeline_parsers import validate_file_prefix

    validate_file_prefix(
        "tests/unit/test_foo.py", expected_prefix="tests/", specialist="test-author"
    )


def test_validate_file_prefix_tests_rejects_src_path() -> None:
    from sdlc.cli._task_pipeline_parsers import validate_file_prefix
    from sdlc.errors import WorkflowError

    with pytest.raises(WorkflowError, match="test-author wrote outside tests/"):
        validate_file_prefix("src/sdlc/foo.py", expected_prefix="tests/", specialist="test-author")


def test_validate_file_prefix_src_passes_for_src_path() -> None:
    from sdlc.cli._task_pipeline_parsers import validate_file_prefix

    validate_file_prefix("src/sdlc/foo.py", expected_prefix="src/", specialist="code-author")


def test_validate_file_prefix_src_rejects_tests_path() -> None:
    from sdlc.cli._task_pipeline_parsers import validate_file_prefix
    from sdlc.errors import WorkflowError

    with pytest.raises(WorkflowError, match="code-author wrote outside src/"):
        validate_file_prefix(
            "tests/unit/test_foo.py", expected_prefix="src/", specialist="code-author"
        )


def test_validate_file_prefix_rejects_absolute_path() -> None:
    from sdlc.cli._task_pipeline_parsers import validate_file_prefix
    from sdlc.errors import WorkflowError

    with pytest.raises(WorkflowError):
        validate_file_prefix(
            "/abs/tests/foo.py", expected_prefix="tests/", specialist="test-author"
        )


def test_validate_file_prefix_rejects_parent_traversal() -> None:
    """A path with a '..' segment escapes the prefix even though it startswith it."""
    from sdlc.cli._task_pipeline_parsers import validate_file_prefix
    from sdlc.errors import WorkflowError

    with pytest.raises(WorkflowError, match="traversal"):
        validate_file_prefix(
            "tests/../src/evil.py", expected_prefix="tests/", specialist="test-author"
        )


# ---------------------------------------------------------------------------
# _StageReviewResult parser — happy path
# ---------------------------------------------------------------------------


def test_stage_review_result_approved_parses_cleanly() -> None:
    from sdlc.cli._task_pipeline_parsers import _StageReviewResult

    result = _StageReviewResult.model_validate({"verdict": "approved", "notes": "looks good"})
    assert result.verdict == "approved"
    assert result.notes == "looks good"


def test_stage_review_result_rejected_parses_cleanly() -> None:
    from sdlc.cli._task_pipeline_parsers import _StageReviewResult

    result = _StageReviewResult.model_validate(
        {"verdict": "rejected", "notes": "missing error handling"}
    )
    assert result.verdict == "rejected"
    assert result.notes == "missing error handling"


# ---------------------------------------------------------------------------
# _StageReviewResult parser — error paths
# ---------------------------------------------------------------------------


def test_stage_review_result_bad_verdict_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._task_pipeline_parsers import _StageReviewResult

    with pytest.raises(ValidationError):
        _StageReviewResult.model_validate({"verdict": "maybe", "notes": "hmm"})


def test_stage_review_result_missing_notes_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._task_pipeline_parsers import _StageReviewResult

    with pytest.raises(ValidationError):
        _StageReviewResult.model_validate({"verdict": "approved"})


def test_stage_review_result_empty_notes_raises_error() -> None:
    """notes must be non-empty (StringConstraints min_length=1)."""
    from pydantic import ValidationError

    from sdlc.cli._task_pipeline_parsers import _StageReviewResult

    with pytest.raises(ValidationError):
        _StageReviewResult.model_validate({"verdict": "approved", "notes": ""})


# The RED→GREEN gate (AC4/D1) is enforced inline in task_stage_dispatch_write as
# two independent per-stage self-report checks (pending requires "red", write-tests
# requires "green"). Coverage lives in the integration/e2e suites (test_sdlc_task.py).
