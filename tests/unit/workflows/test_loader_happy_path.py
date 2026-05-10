"""Happy-path tests for workflows.load_workflow (Story 2A.1, AC1)."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.workflows import load_workflow

FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "workflows" / "valid"


@pytest.mark.unit
class TestLoadWorkflowHappyPath:
    def test_returns_workflow_spec_instance(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert isinstance(result, WorkflowSpec)

    def test_schema_version_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.schema_version == 1

    def test_name_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.name == "research-phase"

    def test_slash_command_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.slash_command == "/sdlc-research"

    def test_primary_agent_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.primary_agent == "research-specialist"

    def test_parallel_agents_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.parallel_agents == ("lit-review-agent", "market-scan-agent")

    def test_synthesizer_agent_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.synthesizer_agent == "synthesis-specialist"

    def test_postconditions_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.postconditions == ("research_report_exists", "sources_validated")

    def test_write_globs_is_mapping_proxy_type(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert isinstance(result.write_globs, MappingProxyType)

    def test_write_globs_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.write_globs["research-specialist"] == ("01-Research/*.md",)

    def test_stop_on_postcondition_failure_field(self) -> None:
        result = load_workflow(FIXTURE_DIR / "minimal.yaml")
        assert result.stop_on_postcondition_failure is True

    def test_accepts_absolute_path(self) -> None:
        path = (FIXTURE_DIR / "minimal.yaml").resolve()
        result = load_workflow(path)
        assert isinstance(result, WorkflowSpec)

    def test_accepts_relative_path(self, tmp_path: Path) -> None:
        import shutil

        dest = tmp_path / "minimal.yaml"
        shutil.copy(FIXTURE_DIR / "minimal.yaml", dest)
        result = load_workflow(dest)
        assert isinstance(result, WorkflowSpec)
