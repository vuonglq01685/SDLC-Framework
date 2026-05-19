"""Per-stage response models, path validator, and output parsers for _task_pipeline (2A.17)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationError

from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import WorkflowError


class _StageFileSpec(StrictModel):
    path: str
    content: str


class _StageFilesResult(StrictModel):
    files: list[_StageFileSpec] = Field(min_length=1)
    tests_status: Literal["red", "green"]


class _StageReviewResult(StrictModel):
    verdict: Literal["approved", "rejected"]
    notes: Annotated[str, StringConstraints(min_length=1)]


def validate_file_prefix(path: str, *, expected_prefix: str, specialist: str) -> None:
    """Raise WorkflowError if path does not start with expected_prefix or is absolute."""
    if Path(path).is_absolute():
        raise WorkflowError(
            f"{specialist} wrote an absolute path: {path!r}; all paths must be repo-relative",
            details={"specialist": specialist, "path": path},
        )
    if ".." in Path(path).parts:
        raise WorkflowError(
            f"{specialist} wrote a path with '..' traversal: {path!r}; "
            f"all paths must stay under {expected_prefix}",
            details={"specialist": specialist, "path": path, "expected_prefix": expected_prefix},
        )
    if not path.startswith(expected_prefix):
        raise WorkflowError(
            f"{specialist} wrote outside {expected_prefix}: {path!r}",
            details={"specialist": specialist, "path": path, "expected_prefix": expected_prefix},
        )


def parse_files_result(output_text: str, *, specialist: str) -> _StageFilesResult:
    """Parse and validate a test-author or code-author JSON response."""
    try:
        data = json.loads(output_text.strip())
    except json.JSONDecodeError as exc:
        raise WorkflowError(
            f"{specialist} output is not valid JSON: {exc}",
            details={"specialist": specialist, "cause": str(exc)},
        ) from exc
    try:
        return _StageFilesResult.model_validate(data)
    except ValidationError as exc:
        raise WorkflowError(
            f"{specialist} response failed schema validation: {exc}",
            details={"specialist": specialist, "cause": str(exc)},
        ) from exc


def parse_review_result(output_text: str) -> _StageReviewResult:
    """Parse and validate a code-reviewer JSON response."""
    try:
        data = json.loads(output_text.strip())
    except json.JSONDecodeError as exc:
        raise WorkflowError(
            f"code-reviewer output is not valid JSON: {exc}",
            details={"cause": str(exc)},
        ) from exc
    try:
        return _StageReviewResult.model_validate(data)
    except ValidationError as exc:
        raise WorkflowError(
            f"code-reviewer response failed schema validation: {exc}",
            details={"cause": str(exc)},
        ) from exc
