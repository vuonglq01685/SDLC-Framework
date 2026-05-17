"""Unit tests for architecture_md_written postcondition (Story 2A.14, AC8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import WorkflowError

pytestmark = pytest.mark.unit


def _make_spec(postconditions: tuple[str, ...]) -> WorkflowSpec:
    return WorkflowSpec(
        schema_version=1,
        name="phase2-architect-track",
        slash_command="/sdlc-architect",
        primary_agent="system-architect",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=postconditions,
        write_globs={"system-architect": ("02-Architecture/02-System/ARCHITECTURE.md",)},
        stop_on_postcondition_failure=True,
    )


def _make_runs(tmp_path: Path) -> Path:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("", encoding="utf-8")
    return runs


def _make_arch_file(
    tmp_path: Path, content: str = "# Architecture\n\n## Overview\n\nTest.\n"
) -> Path:
    arch_dir = tmp_path / "02-Architecture" / "02-System"
    arch_dir.mkdir(parents=True)
    arch = arch_dir / "ARCHITECTURE.md"
    arch.write_text(content, encoding="utf-8")
    return arch


# ---------------------------------------------------------------------------
# architecture_md_written — passes when file exists and is non-empty
# ---------------------------------------------------------------------------


def test_architecture_md_written_passes_with_content(tmp_path: Path) -> None:
    """architecture_md_written passes when ARCHITECTURE.md exists and has content (AC8)."""
    _make_arch_file(tmp_path)
    runs = _make_runs(tmp_path)
    spec = _make_spec(("architecture_md_written",))

    # Should not raise
    evaluate_postconditions(
        spec,
        repo_root=tmp_path,
        agent_runs_path=runs,
        architecture_path_abs=(tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"),
    )


def test_architecture_md_written_passes_with_frontmatter(tmp_path: Path) -> None:
    """architecture_md_written passes when file has YAML frontmatter (AC8)."""
    content = "---\nrequires:\n  - database\n---\n\n## Overview\n\nTest.\n"
    _make_arch_file(tmp_path, content=content)
    runs = _make_runs(tmp_path)
    spec = _make_spec(("architecture_md_written",))

    evaluate_postconditions(
        spec,
        repo_root=tmp_path,
        agent_runs_path=runs,
        architecture_path_abs=(tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"),
    )


def test_architecture_md_written_fails_when_missing(tmp_path: Path) -> None:
    """architecture_md_written raises WorkflowError when ARCHITECTURE.md is absent (AC8)."""
    runs = _make_runs(tmp_path)
    spec = _make_spec(("architecture_md_written",))
    missing = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    # Do NOT create the file

    with pytest.raises(WorkflowError, match="architecture_md_written"):
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=runs,
            architecture_path_abs=missing,
        )


def test_architecture_md_written_fails_when_empty(tmp_path: Path) -> None:
    """architecture_md_written raises WorkflowError when ARCHITECTURE.md is empty (AC8)."""
    _make_arch_file(tmp_path, content="")
    runs = _make_runs(tmp_path)
    spec = _make_spec(("architecture_md_written",))

    with pytest.raises(WorkflowError, match="architecture_md_written"):
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=runs,
            architecture_path_abs=(tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"),
        )


def test_architecture_md_written_fails_when_whitespace_only(tmp_path: Path) -> None:
    """architecture_md_written raises WorkflowError on a whitespace-only ARCHITECTURE.md (AC8)."""
    _make_arch_file(tmp_path, content="   \n\n  \t\n")
    runs = _make_runs(tmp_path)
    spec = _make_spec(("architecture_md_written",))

    with pytest.raises(WorkflowError, match="architecture_md_written"):
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=runs,
            architecture_path_abs=(tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"),
        )


def test_architecture_md_written_requires_architecture_path_abs(tmp_path: Path) -> None:
    """evaluate_postconditions raises RuntimeError when architecture_path_abs not provided (AC8)."""
    _make_arch_file(tmp_path)
    runs = _make_runs(tmp_path)
    spec = _make_spec(("architecture_md_written",))

    with pytest.raises(RuntimeError, match="architecture_path_abs"):
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=runs,
            # architecture_path_abs NOT provided — programmer error
        )
