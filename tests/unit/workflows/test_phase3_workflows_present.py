"""Phase 3 workflow YAML shape tests — sdlc-bootstrap (Story 2A.15) + sdlc-break (Story 2A.16)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.workflows.registry import WorkflowRegistry

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOWS = _REPO / "src" / "sdlc" / "workflows_yaml"
_BOOTSTRAP_YAML = _WORKFLOWS / "sdlc-bootstrap.yaml"
_BREAK_YAML = _WORKFLOWS / "sdlc-break.yaml"

pytestmark = pytest.mark.unit


def test_registry_loads_sdlc_bootstrap() -> None:
    """sdlc-bootstrap.yaml is discoverable and shape-stable (AC4, AC3/D1)."""
    reg = WorkflowRegistry.load(_WORKFLOWS)
    spec = reg.get("/sdlc-bootstrap")
    assert spec.primary_agent == "code-bootstrapper"
    assert spec.parallel_agents == ()
    assert spec.synthesizer_agent is None
    assert spec.slash_command == "/sdlc-bootstrap"
    assert spec.name == "phase3-bootstrap-track"


def test_sdlc_bootstrap_yaml_round_trip_byte_stable() -> None:
    """sdlc-bootstrap.yaml round-trips through yaml.safe_dump/safe_load byte-stable."""
    raw = _BOOTSTRAP_YAML.read_bytes()
    data = yaml.safe_load(raw)
    dumped = yaml.safe_dump(data, sort_keys=True, allow_unicode=False, default_flow_style=False)
    round_raw = yaml.safe_dump(
        yaml.safe_load(dumped),
        sort_keys=True,
        allow_unicode=False,
        default_flow_style=False,
    )
    assert dumped == round_raw
    assert data["schema_version"] == 1
    assert data["slash_command"] == "/sdlc-bootstrap"
    assert data["primary_agent"] == "code-bootstrapper"
    assert data["parallel_agents"] == []
    assert data["synthesizer_agent"] is None
    assert "source_root_populated" in data["postconditions"]
    assert "boundary_line_present_in_prompts" in data["postconditions"]
    assert data["stop_on_postcondition_failure"] is True


def test_sdlc_bootstrap_write_globs_registered() -> None:
    """code-bootstrapper write_globs must cover src/** and tests/** (AC3)."""
    data = yaml.safe_load(_BOOTSTRAP_YAML.read_bytes())
    assert "code-bootstrapper" in data["write_globs"]
    globs = data["write_globs"]["code-bootstrapper"]
    assert isinstance(globs, list)
    assert any(g == "src/**" for g in globs)
    assert any(g == "tests/**" for g in globs)


# ---------------------------------------------------------------------------
# Story 2A.16 — sdlc-break.yaml (AC7)
# ---------------------------------------------------------------------------


def test_registry_loads_sdlc_break() -> None:
    """sdlc-break.yaml is discoverable and shape-stable (Story 2A.16, AC7)."""
    reg = WorkflowRegistry.load(_WORKFLOWS)
    spec = reg.get("/sdlc-break")
    assert spec.primary_agent == "task-breaker"
    assert spec.parallel_agents == ()
    assert spec.synthesizer_agent is None
    assert spec.slash_command == "/sdlc-break"
    assert spec.name == "phase3-break-track"


def test_sdlc_break_yaml_round_trip_byte_stable() -> None:
    """sdlc-break.yaml round-trips through yaml.safe_dump/safe_load byte-stable (AC7)."""
    raw = _BREAK_YAML.read_bytes()
    data = yaml.safe_load(raw)
    dumped = yaml.safe_dump(data, sort_keys=True, allow_unicode=False, default_flow_style=False)
    round_raw = yaml.safe_dump(
        yaml.safe_load(dumped),
        sort_keys=True,
        allow_unicode=False,
        default_flow_style=False,
    )
    assert dumped == round_raw
    assert data["schema_version"] == 1
    assert data["slash_command"] == "/sdlc-break"
    assert data["primary_agent"] == "task-breaker"
    assert data["parallel_agents"] == []
    assert data["synthesizer_agent"] is None
    assert "tasks_dir_populated" in data["postconditions"]
    assert "boundary_line_present_in_prompts" in data["postconditions"]
    assert data["stop_on_postcondition_failure"] is True


def test_sdlc_break_write_globs_registered() -> None:
    """task-breaker write_globs must cover 03-Implementation/tasks/** (AC7)."""
    data = yaml.safe_load(_BREAK_YAML.read_bytes())
    assert "task-breaker" in data["write_globs"]
    globs = data["write_globs"]["task-breaker"]
    assert isinstance(globs, list)
    assert any(g == "03-Implementation/tasks/**" for g in globs)
