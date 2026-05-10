"""Unknown-key rejection tests for load_workflow (Story 2A.1, AC2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.errors import WorkflowError
from sdlc.workflows import load_workflow

ADVERSARIAL_DIR = Path(__file__).parent.parent.parent / "fixtures" / "workflows" / "adversarial"

UNKNOWN_KEY_FIXTURES = [
    "unknown_key_metadata.yaml",
]


@pytest.mark.unit
@pytest.mark.parametrize("fixture_name", UNKNOWN_KEY_FIXTURES)
def test_unknown_key_raises_workflow_error(fixture_name: str) -> None:
    path = ADVERSARIAL_DIR / fixture_name
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "regenerate from schema or remove the field" in message


@pytest.mark.unit
def test_unknown_key_names_the_offending_key() -> None:
    path = ADVERSARIAL_DIR / "unknown_key_metadata.yaml"
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(path)
    message = str(exc_info.value)
    assert "metadata" in message


@pytest.mark.unit
def test_unknown_key_details_contains_field() -> None:
    path = ADVERSARIAL_DIR / "unknown_key_metadata.yaml"
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(path)
    assert exc_info.value.details["field"] == "metadata"
    assert exc_info.value.details["path"] == str(path)
