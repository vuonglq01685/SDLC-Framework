"""Integration tests for AC3: disjoint-writes static check at dispatch time (Story 2A.3).

AC3 contract:
- WorkflowRegistry.load() gates dispatch via validate_workflow — a spec that
  violates the disjoint-writes invariant never reaches dispatch_panel().
- dispatch_panel() does NOT re-run validate_workflow (Decision D3 v1 trust posture;
  ADR-013, Architecture §1067). It trusts the loaded WorkflowSpec as validated input.
- The AC2.4 synthesizer-overwrites-primary behaviour is only achievable today by
  constructing WorkflowSpec directly (bypassing static check); a YAML workflow where
  synthesizer and primary share the same glob IS rejected by validate_workflow.
  This is a known design tension documented in the dispatcher Change Log.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import WorkflowError
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.workflows.registry import WorkflowRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _make_specialist(name: str, write_glob: str) -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=name,
        title=name.replace("-", " ").title(),
        icon="📄",
        model="claude-opus-4-5",
        description=f"{name} specialist.",
        write_globs=(write_glob,),
    )
    return Specialist(frontmatter=fm, body=f"You are {name}.", source_path=Path(f"{name}.md"))


def _make_registry(*specs: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specs}))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDisjointWritesGating:
    """AC3: WorkflowRegistry gates dispatch; dispatcher trusts loaded spec."""

    def test_registry_rejects_parallel_agents_with_shared_glob(self, tmp_path: Path) -> None:
        """A YAML spec where two parallel agents share a write glob never loads.

        validate_workflow raises WorkflowError so the spec never reaches dispatch.
        """
        yaml_dir = tmp_path / "workflows"
        yaml_dir.mkdir()
        _write_yaml(
            yaml_dir / "collision.yaml",
            """
schema_version: 1
name: requirements
slash_command: /sdlc-start
primary_agent: primary-agent
parallel_agents:
  - researcher
  - critic
write_globs:
  primary-agent:
    - docs/primary.md
  researcher:
    - docs/shared.md
  critic:
    - docs/shared.md
""",
        )

        with pytest.raises(WorkflowError, match="disjoint-writes violation"):
            WorkflowRegistry.load(yaml_dir)

    def test_valid_spec_loads_and_reaches_dispatch_panel(self, tmp_path: Path) -> None:
        """A spec with non-overlapping write_globs loads and dispatch_panel succeeds."""
        yaml_dir = tmp_path / "workflows"
        yaml_dir.mkdir()
        _write_yaml(
            yaml_dir / "valid.yaml",
            """
schema_version: 1
name: requirements
slash_command: /sdlc-start
primary_agent: primary-agent
parallel_agents:
  - researcher
write_globs:
  primary-agent:
    - docs/primary.md
  researcher:
    - docs/research.md
""",
        )
        registry = WorkflowRegistry.load(yaml_dir)
        spec = registry.get("/sdlc-start")

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="done", tokens_in=5, tokens_out=10)
        specialist_registry = _make_registry(
            _make_specialist("primary-agent", "docs/primary.md"),
            _make_specialist("researcher", "docs/research.md"),
        )

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            from sdlc.dispatcher.core import dispatch_panel

            result = asyncio.run(
                dispatch_panel(
                    spec,
                    runtime=runtime,
                    registry=specialist_registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        assert result.outcome == "success"

    def test_dispatcher_trusts_spec_no_static_check(self, tmp_path: Path) -> None:
        """dispatch_panel trusts the WorkflowSpec as pre-validated (D3 trust posture).

        A WorkflowSpec constructed directly (bypassing validate_workflow) with
        a write-target "collision" reaches dispatch_panel without WorkflowError.
        WorkflowError is only raised by validate_workflow (in static_check/registry),
        never by dispatch_panel itself — so its absence proves the dispatcher
        does not re-run the static check (AC3, ADR-013).
        """
        from sdlc.dispatcher.core import dispatch_panel
        from sdlc.workflows.static_check import validate_workflow

        # Build a spec with synth + primary sharing the same glob — this
        # is rejected by validate_workflow but accepted by dispatch_panel directly.
        spec = WorkflowSpec(
            schema_version=1,
            name="requirements",
            slash_command="/sdlc-start",
            primary_agent="primary-agent",
            parallel_agents=(),
            synthesizer_agent="synthesizer",
            write_globs={
                "primary-agent": ("docs/primary.md",),
                "synthesizer": ("docs/primary.md",),  # same target = static_check violation
            },
        )
        # Confirm static_check would reject this spec.
        with pytest.raises(WorkflowError, match="disjoint-writes violation"):
            validate_workflow(spec)

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(
            output_text="artifact", tokens_in=5, tokens_out=10
        )
        specialist_registry = _make_registry(
            _make_specialist("primary-agent", "docs/primary.md"),
            _make_specialist("synthesizer", "docs/primary.md"),
        )

        # P20: assert via mock that ``validate_workflow`` is NEVER invoked from the
        # dispatcher path (Blind Hunter caught the original test as tautological:
        # absence-of-raise does not prove absence-of-call). dispatch_panel must trust
        # the loaded spec per AC3 / ADR-013 D3 trust posture.
        with (
            patch(
                "sdlc.workflows.static_check.validate_workflow",
                wraps=validate_workflow,
            ) as validate_spy,
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    spec,
                    runtime=runtime,
                    registry=specialist_registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        validate_spy.assert_not_called()
