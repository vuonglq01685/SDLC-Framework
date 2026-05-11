"""Story 2A.8 AC1 — sdlc-start workflow YAML is loadable and shape-stable."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.workflows.registry import WorkflowRegistry

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOWS = _REPO / "src" / "sdlc" / "workflows_yaml"
_YAML_PATH = _WORKFLOWS / "sdlc-start.yaml"
_RESEARCH_YAML = _WORKFLOWS / "sdlc-research.yaml"
_VERIFY_YAML_PATH = _WORKFLOWS / "sdlc-verify.yaml"

pytestmark = pytest.mark.unit


def test_registry_loads_sdlc_start() -> None:
    reg = WorkflowRegistry.load(_WORKFLOWS)
    spec = reg.get("/sdlc-start")
    assert spec.primary_agent == "product-strategist"
    assert spec.parallel_agents == ("technical-researcher", "devil-advocate")
    assert spec.synthesizer_agent == "requirement-synthesizer"
    assert spec.slash_command == "/sdlc-start"


def test_registry_loads_sdlc_research() -> None:
    reg = WorkflowRegistry.load(_WORKFLOWS)
    spec = reg.get("/sdlc-research")
    assert spec.primary_agent == "technical-researcher"
    assert spec.parallel_agents == ()
    assert spec.synthesizer_agent is None
    assert spec.slash_command == "/sdlc-research"


def test_sdlc_research_yaml_round_trip_byte_stable() -> None:
    """P8 (code review): assert dump idempotency AND the parsed shape.

    The original ``dumped == round_raw`` test was idempotency-only and could
    silently pass even when the disk YAML's keys reordered. Strengthen the
    assertion to also pin the parsed shape (schema_version, slash_command,
    primary_agent, parallel_agents=[], synthesizer_agent=None) so that any
    accidental edit to the YAML — reorder, add a key, drop a key — fails
    here in addition to the dump-stability check.
    """
    raw = _RESEARCH_YAML.read_bytes()
    data = yaml.safe_load(raw)
    dumped = yaml.safe_dump(data, sort_keys=True, allow_unicode=False, default_flow_style=False)
    round_raw = yaml.safe_dump(
        yaml.safe_load(dumped),
        sort_keys=True,
        allow_unicode=False,
        default_flow_style=False,
    )
    assert dumped == round_raw
    # P8 strengthening: pin the parsed shape, not just dump idempotency.
    assert data["schema_version"] == 1
    assert data["slash_command"] == "/sdlc-research"
    assert data["primary_agent"] == "technical-researcher"
    assert data["parallel_agents"] == []
    assert data["synthesizer_agent"] is None
    assert "research_md_exists" in data["postconditions"]


def test_sdlc_start_yaml_round_trip_byte_stable() -> None:
    """P8 (code review): dump idempotency + parsed-shape pin for sdlc-start."""
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
    assert data["schema_version"] == 1
    assert data["slash_command"] == "/sdlc-start"
    assert data["primary_agent"] == "product-strategist"


def test_registry_loads_sdlc_verify() -> None:
    """Story 2A.10 AC1/D1: sdlc-verify.yaml is discoverable + shape-stable."""
    reg = WorkflowRegistry.load(_WORKFLOWS)
    spec = reg.get("/sdlc-verify")
    assert spec.primary_agent == "artifact-verifier"
    assert spec.parallel_agents == ()
    assert spec.synthesizer_agent is None
    assert spec.slash_command == "/sdlc-verify"
    assert spec.name == "phase1-artifact-verification"


def test_sdlc_verify_yaml_round_trip_byte_stable() -> None:
    raw = _VERIFY_YAML_PATH.read_bytes()
    data = yaml.safe_load(raw)
    dumped = yaml.safe_dump(data, sort_keys=True, allow_unicode=False, default_flow_style=False)
    round_raw = yaml.safe_dump(
        yaml.safe_load(dumped),
        sort_keys=True,
        allow_unicode=False,
        default_flow_style=False,
    )
    assert dumped == round_raw
