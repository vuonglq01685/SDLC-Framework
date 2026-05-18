"""Unit tests for source_root_populated postcondition (Story 2A.15, AC7)."""

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
        name="phase3-bootstrap-track",
        slash_command="/sdlc-bootstrap",
        primary_agent="code-bootstrapper",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=postconditions,
        write_globs={"code-bootstrapper": ("src/**", "tests/**")},
        stop_on_postcondition_failure=True,
    )


def _make_runs(tmp_path: Path) -> Path:
    """Create a dummy agent_runs file (not used by source_root_populated)."""
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("", encoding="utf-8")
    return runs


class TestSourceRootPopulated:
    def test_passes_when_src_has_real_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("# placeholder\n", encoding="utf-8")
        spec = _make_spec(("source_root_populated",))
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=_make_runs(tmp_path),
            source_root_abs=src,
        )

    def test_fails_when_src_missing(self, tmp_path: Path) -> None:
        spec = _make_spec(("source_root_populated",))
        with pytest.raises(WorkflowError, match="source_root_populated"):
            evaluate_postconditions(
                spec,
                repo_root=tmp_path,
                agent_runs_path=_make_runs(tmp_path),
                source_root_abs=tmp_path / "src",
            )

    def test_fails_when_src_is_empty(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        spec = _make_spec(("source_root_populated",))
        with pytest.raises(WorkflowError, match="source_root_populated"):
            evaluate_postconditions(
                spec,
                repo_root=tmp_path,
                agent_runs_path=_make_runs(tmp_path),
                source_root_abs=src,
            )

    def test_fails_when_only_gitkeep_present(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / ".gitkeep").write_text("", encoding="utf-8")
        spec = _make_spec(("source_root_populated",))
        with pytest.raises(WorkflowError, match="source_root_populated"):
            evaluate_postconditions(
                spec,
                repo_root=tmp_path,
                agent_runs_path=_make_runs(tmp_path),
                source_root_abs=src,
            )

    def test_fails_when_only_readme_present(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "README.md").write_text("# placeholder\n", encoding="utf-8")
        spec = _make_spec(("source_root_populated",))
        with pytest.raises(WorkflowError, match="source_root_populated"):
            evaluate_postconditions(
                spec,
                repo_root=tmp_path,
                agent_runs_path=_make_runs(tmp_path),
                source_root_abs=src,
            )

    def test_passes_when_nested_real_file_exists(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        pkg = src / "myapp"
        pkg.mkdir(parents=True)
        (pkg / "models.py").write_text("# model\n", encoding="utf-8")
        spec = _make_spec(("source_root_populated",))
        evaluate_postconditions(
            spec,
            repo_root=tmp_path,
            agent_runs_path=_make_runs(tmp_path),
            source_root_abs=src,
        )

    def test_raises_runtime_error_when_source_root_abs_not_provided(self, tmp_path: Path) -> None:
        spec = _make_spec(("source_root_populated",))
        with pytest.raises(RuntimeError, match="source_root_abs"):
            evaluate_postconditions(
                spec,
                repo_root=tmp_path,
                agent_runs_path=_make_runs(tmp_path),
            )
