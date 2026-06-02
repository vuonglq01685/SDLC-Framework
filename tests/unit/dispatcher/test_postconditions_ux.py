"""Unit tests for ux_dir_non_empty postcondition (Story 2A.13, AC8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.dispatcher.prompts import BOUNDARY_LINE
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


# ---------------------------------------------------------------------------
# boundary_line_present_in_prompts — SECURITY-INVARIANT restored (EPIC-2A-D4)
# Mirrors the architect Phase-2 path; reactivated once Story 2B.1 records
# dispatch_prompt rows. Each recorded prompt must wrap BOUNDARY_LINE in exactly
# one <BOUNDARY>...</BOUNDARY> block (NFR-SEC-3 / P60).
# ---------------------------------------------------------------------------


def _write_runs(tmp_path: Path, prompts: list[str]) -> Path:
    runs = tmp_path / "agent_runs.jsonl"
    rows = [json.dumps({"dispatch_prompt": p, "specialist_name": "ux-designer"}) for p in prompts]
    runs.write_text(("\n".join(rows) + "\n") if rows else "", encoding="utf-8")
    return runs


def _boundary_spec() -> object:
    from sdlc.contracts.workflow_spec import WorkflowSpec

    return WorkflowSpec(
        schema_version=1,
        name="test-ux",
        slash_command="/sdlc-ux",
        primary_agent="ux-designer",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=("boundary_line_present_in_prompts",),
        write_globs={},
        stop_on_postcondition_failure=True,
    )


def test_ux_boundary_line_present_passes_with_valid_block(tmp_path: Path) -> None:
    """Passes when each dispatch_prompt wraps BOUNDARY_LINE in one <BOUNDARY> block."""
    prompt = (
        f"Persona preamble.\n<BOUNDARY>\n{BOUNDARY_LINE}\nuser-supplied text\n</BOUNDARY>\nClosing."
    )
    runs = _write_runs(tmp_path, [prompt])

    # Should not raise — the UX Phase-2 path now enforces the boundary invariant.
    evaluate_postconditions(_boundary_spec(), repo_root=tmp_path, agent_runs_path=runs)


def test_ux_boundary_line_present_fails_when_block_absent(tmp_path: Path) -> None:
    """Raises WorkflowError when a recorded prompt omits the <BOUNDARY> block."""
    runs = _write_runs(tmp_path, ["No boundary tags anywhere in this prompt."])

    with pytest.raises(WorkflowError, match="boundary_line_present_in_prompts"):
        evaluate_postconditions(_boundary_spec(), repo_root=tmp_path, agent_runs_path=runs)


def test_ux_boundary_line_present_fails_when_no_dispatch_prompt_rows(tmp_path: Path) -> None:
    """Raises (invariant) when no dispatch_prompt rows were recorded."""
    runs = _write_runs(tmp_path, [])

    with pytest.raises(WorkflowError, match="boundary_line_present_in_prompts"):
        evaluate_postconditions(_boundary_spec(), repo_root=tmp_path, agent_runs_path=runs)
