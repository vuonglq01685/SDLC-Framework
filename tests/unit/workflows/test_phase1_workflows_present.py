"""Story 2A.8 AC1 — sdlc-start workflow YAML is loadable and shape-stable."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.workflows.registry import WorkflowRegistry

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOWS = _REPO / "src" / "sdlc" / "workflows_yaml"
_YAML_PATH = _WORKFLOWS / "sdlc-start.yaml"

pytestmark = pytest.mark.unit


def test_registry_loads_sdlc_start() -> None:
    reg = WorkflowRegistry.load(_WORKFLOWS)
    spec = reg.get("/sdlc-start")
    assert spec.primary_agent == "product-strategist"
    assert spec.parallel_agents == ("technical-researcher", "devil-advocate")
    assert spec.synthesizer_agent == "requirement-synthesizer"
    assert spec.slash_command == "/sdlc-start"


def test_sdlc_start_yaml_round_trip_byte_stable() -> None:
    raw = _YAML_PATH.read_bytes()
    data = yaml.safe_load(raw)
    dumped = yaml.safe_dump(data, sort_keys=True, allow_unicode=False, default_flow_style=False)
    round_raw = yaml.safe_dump(
        yaml.safe_load(dumped),
        sort_keys=True,
        allow_unicode=False,
        default_flow_style=False,
    )
    assert dumped == round_raw
