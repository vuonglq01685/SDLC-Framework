"""Mock fixture body builders and fixture writers for _task_pipeline (Story 2A.17, AC8/D1)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def mock_test_author_body(task_id: str) -> str:
    """Happy-path mock: test-author returns one test file under tests/ with tests_status red."""
    return json.dumps(
        {
            "files": [
                {
                    "path": (
                        "tests/unit/test_"
                        f"{task_id.rsplit('-T', maxsplit=1)[-1].split('-', maxsplit=1)[0]}.py"
                    ),
                    "content": (
                        f"# Test stub for {task_id}\n"
                        "def test_placeholder() -> None:\n    assert False\n"
                    ),
                }
            ],
            "tests_status": "red",
        },
        ensure_ascii=False,
    )


def mock_characterization_author_body(task_id: str) -> str:
    """Story 3.8: characterization-author returns one passing test under tests/ (status green).

    Characterization tests capture the CURRENT behavior of legacy code, so they are expected
    to PASS — the pending-stage gate accepts ``green`` for ``characterization-test`` tasks.
    """
    return json.dumps(
        {
            "files": [
                {
                    "path": (
                        "tests/unit/test_"
                        f"{task_id.rsplit('-T', maxsplit=1)[-1].split('-', maxsplit=1)[0]}"
                        "_characterization.py"
                    ),
                    "content": (
                        f"# Characterization test for {task_id}\n"
                        "def test_current_behavior_captured() -> None:\n    assert True\n"
                    ),
                }
            ],
            "tests_status": "green",
        },
        ensure_ascii=False,
    )


def mock_code_author_body(task_id: str) -> str:
    """Happy-path mock: code-author returns one source file under src/ with tests_status green."""
    return json.dumps(
        {
            "files": [
                {
                    "path": (
                        "src/sdlc/impl_"
                        f"{task_id.rsplit('-T', maxsplit=1)[-1].split('-', maxsplit=1)[0]}.py"
                    ),
                    "content": f"# Implementation stub for {task_id}\n",
                }
            ],
            "tests_status": "green",
        },
        ensure_ascii=False,
    )


def mock_code_reviewer_body() -> str:
    """Happy-path mock: code-reviewer returns approved verdict."""
    return json.dumps(
        {"verdict": "approved", "notes": "MockAIRuntime v1 — auto-approved placeholder."},
        ensure_ascii=False,
    )


def write_mock_fixture(dest_dir: Path, name: str, h: str, body: str) -> None:
    records = {h: {"output_text": body, "tokens_in": 1, "tokens_out": 1, "tool_calls": []}}
    (dest_dir / f"{name}.yaml").write_text(
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True), encoding="utf-8"
    )
