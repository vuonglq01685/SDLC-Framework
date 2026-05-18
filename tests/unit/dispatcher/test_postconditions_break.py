"""Unit tests for ``tasks_dir_populated`` no-op postcondition (Story 2A.16, AC9/D2, Task 3.1)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _make_spec(postconditions: list[str]) -> object:
    """Return a minimal WorkflowSpec-like object with the given postconditions."""
    from sdlc.contracts.workflow_spec import WorkflowSpec

    return WorkflowSpec(
        schema_version=1,
        name="phase3-break-track",
        slash_command="/sdlc-break",
        primary_agent="task-breaker",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=tuple(postconditions),
        write_globs={"task-breaker": ("03-Implementation/tasks/**",)},
        stop_on_postcondition_failure=True,
    )


def test_tasks_dir_populated_no_op_returns_without_raising(tmp_path: Path) -> None:
    """AC9/D2: tasks_dir_populated is a no-op — must not raise WorkflowError (Task 3.1)."""
    from sdlc.dispatcher.postconditions import evaluate_postconditions

    spec = _make_spec(["tasks_dir_populated"])
    agent_runs_path = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    agent_runs_path.parent.mkdir(parents=True, exist_ok=True)
    agent_runs_path.write_text("", encoding="utf-8")

    # Must not raise for any repo state
    evaluate_postconditions(spec, repo_root=tmp_path, agent_runs_path=agent_runs_path)


def test_tasks_dir_populated_emits_warn_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """tasks_dir_populated no-op must emit at least one WARN log (AC9/D2 contract)."""
    from sdlc.dispatcher.postconditions import evaluate_postconditions

    spec = _make_spec(["tasks_dir_populated"])
    agent_runs_path = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    agent_runs_path.parent.mkdir(parents=True, exist_ok=True)
    agent_runs_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        evaluate_postconditions(spec, repo_root=tmp_path, agent_runs_path=agent_runs_path)

    warn_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("tasks_dir_populated" in m for m in warn_msgs), (
        f"expected a WARN containing 'tasks_dir_populated'; got: {warn_msgs}"
    )


def test_tasks_dir_populated_emits_exactly_one_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """tasks_dir_populated no-op must emit exactly one WARN per call (AC9/D2)."""
    from sdlc.dispatcher.postconditions import evaluate_postconditions

    spec = _make_spec(["tasks_dir_populated"])
    agent_runs_path = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    agent_runs_path.parent.mkdir(parents=True, exist_ok=True)
    agent_runs_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        evaluate_postconditions(spec, repo_root=tmp_path, agent_runs_path=agent_runs_path)

    warn_msgs = [
        r.message
        for r in caplog.records
        if r.levelno >= logging.WARNING and "tasks_dir_populated" in r.message
    ]
    assert len(warn_msgs) == 1, (
        f"expected exactly 1 WARN for tasks_dir_populated; got {len(warn_msgs)}: {warn_msgs}"
    )
