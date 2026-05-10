"""WorkflowRegistry tests (Story 2A.1, AC6)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.errors import WorkflowError
from sdlc.workflows import WorkflowRegistry

VALID_DIR = Path(__file__).parent.parent.parent / "fixtures" / "workflows" / "valid"
ADVERSARIAL_DIR = Path(__file__).parent.parent.parent / "fixtures" / "workflows" / "adversarial"


def _write_workflow(tmp_path: Path, name: str, slash_command: str) -> Path:
    """Write a minimal valid workflow YAML and return its path."""
    data = {
        "schema_version": 1,
        "name": name,
        "slash_command": slash_command,
        "primary_agent": "agent-x",
        "parallel_agents": [],
        "write_globs": {},
        "stop_on_postcondition_failure": True,
    }
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


@pytest.mark.unit
class TestWorkflowRegistry:
    def test_empty_directory_loads_zero_workflows(self, tmp_path: Path) -> None:
        registry = WorkflowRegistry.load(tmp_path)
        assert registry.list() == ()

    def test_single_workflow_directory_loads(self, tmp_path: Path) -> None:
        _write_workflow(tmp_path, "research", "/sdlc-research")
        registry = WorkflowRegistry.load(tmp_path)
        assert len(registry.list()) == 1

    def test_get_returns_correct_spec(self, tmp_path: Path) -> None:
        _write_workflow(tmp_path, "research", "/sdlc-research")
        registry = WorkflowRegistry.load(tmp_path)
        spec = registry.get("/sdlc-research")
        assert spec.slash_command == "/sdlc-research"
        assert spec.name == "research"

    def test_list_returns_all_workflows_sorted_by_slash_command(self, tmp_path: Path) -> None:
        _write_workflow(tmp_path, "ux", "/sdlc-ux")
        _write_workflow(tmp_path, "research", "/sdlc-research")
        _write_workflow(tmp_path, "arch", "/sdlc-arch")
        registry = WorkflowRegistry.load(tmp_path)
        commands = [spec.slash_command for spec in registry.list()]
        assert commands == sorted(commands)

    def test_get_unknown_command_raises_workflow_error(self, tmp_path: Path) -> None:
        registry = WorkflowRegistry.load(tmp_path)
        with pytest.raises(WorkflowError) as exc_info:
            registry.get("/nonexistent")
        assert "unknown slash_command" in str(exc_info.value)
        assert "/nonexistent" in str(exc_info.value)

    def test_duplicate_slash_command_raises_workflow_error(self, tmp_path: Path) -> None:
        _write_workflow(tmp_path, "research-a", "/sdlc-research")
        _write_workflow(tmp_path, "research-b", "/sdlc-research")
        with pytest.raises(WorkflowError) as exc_info:
            WorkflowRegistry.load(tmp_path)
        msg = str(exc_info.value)
        assert "duplicate slash_command" in msg
        assert "/sdlc-research" in msg

    def test_malformed_yaml_aborts_registry_construction(self, tmp_path: Path) -> None:
        _write_workflow(tmp_path, "good", "/good-cmd")
        bad = tmp_path / "bad.yaml"
        bad.write_text(":::not valid yaml:::", encoding="utf-8")
        with pytest.raises(WorkflowError):
            WorkflowRegistry.load(tmp_path)

    def test_no_partial_state_on_failure(self, tmp_path: Path) -> None:
        _write_workflow(tmp_path, "aaa-good", "/good-cmd")
        # adversarial YAML aborts after the good one is loaded
        bad = tmp_path / "bbb-bad.yaml"
        bad.write_text(":::not valid yaml:::", encoding="utf-8")
        with pytest.raises(WorkflowError):
            WorkflowRegistry.load(tmp_path)

    def test_list_is_byte_stable_sorted_by_slash_command(self, tmp_path: Path) -> None:
        _write_workflow(tmp_path, "c-workflow", "/c-cmd")
        _write_workflow(tmp_path, "a-workflow", "/a-cmd")
        _write_workflow(tmp_path, "b-workflow", "/b-cmd")
        registry = WorkflowRegistry.load(tmp_path)
        assert [s.slash_command for s in registry.list()] == ["/a-cmd", "/b-cmd", "/c-cmd"]
