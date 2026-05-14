"""Story 2A.13 AC4 — sdlc-ux workflow YAML is loadable and shape-stable."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.workflows.registry import WorkflowRegistry

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOWS = _REPO / "src" / "sdlc" / "workflows_yaml"
_UX_YAML = _WORKFLOWS / "sdlc-ux.yaml"

pytestmark = pytest.mark.unit


def test_registry_loads_sdlc_ux() -> None:
    """sdlc-ux.yaml is discoverable + shape-stable (AC4, AC3/D1)."""
    reg = WorkflowRegistry.load(_WORKFLOWS)
    spec = reg.get("/sdlc-ux")
    assert spec.primary_agent == "ux-designer"
    assert spec.parallel_agents == ()
    assert spec.synthesizer_agent is None
    assert spec.slash_command == "/sdlc-ux"
    assert spec.name == "phase2-ux-track"


def test_sdlc_ux_yaml_round_trip_byte_stable() -> None:
    """sdlc-ux.yaml round-trips through yaml.safe_dump/safe_load byte-stable + shape pinned."""
    raw = _UX_YAML.read_bytes()
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
    assert data["slash_command"] == "/sdlc-ux"
    assert data["primary_agent"] == "ux-designer"
    assert data["parallel_agents"] == []
    assert data["synthesizer_agent"] is None
    assert "ux_dir_non_empty" in data["postconditions"]
    assert "boundary_line_present_in_prompts" not in data["postconditions"]


def test_sdlc_ux_write_globs_registered() -> None:
    """ux-designer write_globs must be registered in sdlc-ux.yaml (AC4)."""
    data = yaml.safe_load(_UX_YAML.read_bytes())
    assert "ux-designer" in data["write_globs"]
    globs = data["write_globs"]["ux-designer"]
    assert isinstance(globs, list)
    assert len(globs) >= 1
    assert any("02-Architecture/01-UX" in g for g in globs)
