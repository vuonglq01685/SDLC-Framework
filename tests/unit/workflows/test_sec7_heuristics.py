"""NFR-SEC-7 instruction-shape heuristic tests (Story 2A.1, AC3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.errors import WorkflowError
from sdlc.workflows import load_workflow

SEC7_DIR = Path(__file__).parent.parent.parent / "fixtures" / "workflows" / "adversarial" / "sec7"

SEC7_FIXTURES = [
    ("instruction_prefix.yaml", "instruction_prefix"),
    ("fenced_code_block.yaml", "fenced_code_block"),
    ("xml_tag.yaml", "xml_instruction_tag"),
    ("length_overflow.yaml", "length_overflow"),
]


@pytest.mark.unit
@pytest.mark.parametrize("fixture_name,expected_heuristic", SEC7_FIXTURES)
def test_sec7_fixture_raises_workflow_error(fixture_name: str, expected_heuristic: str) -> None:
    path = SEC7_DIR / fixture_name
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(path)
    message = str(exc_info.value)
    assert expected_heuristic in message, (
        f"Expected heuristic name {expected_heuristic!r} in message: {message!r}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("fixture_name,expected_heuristic", SEC7_FIXTURES)
def test_sec7_error_names_file_path(fixture_name: str, expected_heuristic: str) -> None:
    path = SEC7_DIR / fixture_name
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(path)
    assert str(path) in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.parametrize("fixture_name,expected_heuristic", SEC7_FIXTURES)
def test_sec7_error_details_contain_heuristic(fixture_name: str, expected_heuristic: str) -> None:
    path = SEC7_DIR / fixture_name
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(path)
    assert exc_info.value.details["heuristic"] == expected_heuristic
