"""Unit tests for ux_dir_non_empty postcondition (Story 2A.13, AC8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import WorkflowError

pytestmark = pytest.mark.unit

# Minimal WorkflowSpec stub via the real class
_REPO = Path(__file__).resolve().parents[3]
_WORKFLOWS_DIR = _REPO / "src" / "sdlc" / "workflows_yaml"


def _load_ux_spec() -> object:
    from sdlc.workflows.registry import WorkflowRegistry

    return WorkflowRegistry.load(_WORKFLOWS_DIR).get("/sdlc-ux")


# ---------------------------------------------------------------------------
# ux_dir_non_empty — unit-level
# ---------------------------------------------------------------------------


def test_ux_dir_non_empty_passes_with_md_file(tmp_path: Path) -> None:
    """ux_dir_non_empty passes when at least one .md file exists in the dir."""
    from sdlc.contracts.workflow_spec import WorkflowSpec

    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    ux_dir.mkdir(parents=True)
    (ux_dir / "01-tokens.md").write_text("# tokens", encoding="utf-8")

    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("", encoding="utf-8")

    # Build a minimal spec with only ux_dir_non_empty postcondition
    spec = WorkflowSpec(
        schema_version=1,
        name="test-ux",
        slash_command="/sdlc-ux",
        primary_agent="ux-designer",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=("ux_dir_non_empty",),
        write_globs={},
        stop_on_postcondition_failure=True,
    )
    # Should not raise
    evaluate_postconditions(
        spec,
        repo_root=tmp_path,
        agent_runs_path=runs,
        ux_dir_abs=ux_dir,
    )


def test_ux_dir_non_empty_passes_with_multiple_md_files(tmp_path: Path) -> None:
    """ux_dir_non_empty passes with multiple .md files."""
    from sdlc.contracts.workflow_spec import WorkflowSpec

    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    ux_dir.mkdir(parents=True)
    (ux_dir / "01-tokens.md").write_text("# tokens", encoding="utf-8")
    (ux_dir / "02-flows.md").write_text("# flows", encoding="utf-8")
    (ux_dir / "03-screens.md").write_text("# screens", encoding="utf-8")

    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("", encoding="utf-8")

    spec = WorkflowSpec(
        schema_version=1,
        name="test-ux",
        slash_command="/sdlc-ux",
        primary_agent="ux-designer",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=("ux_dir_non_empty",),
        write_globs={},
        stop_on_postcondition_failure=True,
    )
    evaluate_postconditions(
        spec,
        repo_root=tmp_path,
        agent_runs_path=runs,
        ux_dir_abs=ux_dir,
    )


def test_ux_dir_non_empty_fails_when_dir_is_empty(tmp_path: Path) -> None:
    """ux_dir_non_empty raises WorkflowError when directory has no .md files."""
    from sdlc.contracts.workflow_spec import WorkflowSpec

    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    ux_dir.mkdir(parents=True)
    # No .md files — only a non-md file
    (ux_dir / "README.txt").write_text("ignored", encoding="utf-8")

    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("", encoding="utf-8")

    spec = WorkflowSpec(
        schema_version=1,
        name="test-ux",
        slash_command="/sdlc-ux",
        primary_agent="ux-designer",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=("ux_dir_non_empty",),
        write_globs={},
        stop_on_postcondition_failure=True,
    )
    with pytest.raises(WorkflowError, match="ux_dir_non_empty"):
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=runs,
            ux_dir_abs=ux_dir,
        )


def test_ux_dir_non_empty_fails_when_dir_missing(tmp_path: Path) -> None:
    """ux_dir_non_empty raises WorkflowError when the directory does not exist."""
    from sdlc.contracts.workflow_spec import WorkflowSpec

    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    # Do NOT create the directory

    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("", encoding="utf-8")

    spec = WorkflowSpec(
        schema_version=1,
        name="test-ux",
        slash_command="/sdlc-ux",
        primary_agent="ux-designer",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=("ux_dir_non_empty",),
        write_globs={},
        stop_on_postcondition_failure=True,
    )
    with pytest.raises(WorkflowError, match="ux_dir_non_empty"):
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=runs,
            ux_dir_abs=ux_dir,
        )


def test_ux_dir_non_empty_requires_ux_dir_abs_caller_plumbing(tmp_path: Path) -> None:
    """evaluate_postconditions raises RuntimeError when ux_dir_abs is not provided."""
    from sdlc.contracts.workflow_spec import WorkflowSpec

    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("", encoding="utf-8")

    spec = WorkflowSpec(
        schema_version=1,
        name="test-ux",
        slash_command="/sdlc-ux",
        primary_agent="ux-designer",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=("ux_dir_non_empty",),
        write_globs={},
        stop_on_postcondition_failure=True,
    )
    with pytest.raises(RuntimeError, match="ux_dir_abs"):
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=runs,
            # ux_dir_abs NOT provided — programmer error
        )
