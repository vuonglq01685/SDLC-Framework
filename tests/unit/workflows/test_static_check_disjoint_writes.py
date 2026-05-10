"""Disjoint-writes static checker tests (Story 2A.1, AC4)."""

from __future__ import annotations

import pytest

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import WorkflowError
from sdlc.workflows.static_check import validate_workflow


def _make_spec(write_globs: dict[str, list[str]]) -> WorkflowSpec:
    """Build a minimal WorkflowSpec with the given write_globs.

    All agents named in write_globs are auto-declared as parallel_agents (with
    the lexicographically smallest one promoted to primary_agent) so the new
    phantom-agent check (added by P1/E3) does not pre-empt the disjoint-writes
    assertion under test.
    """
    agents = sorted(write_globs.keys())
    primary = agents[0] if agents else "agent-a"
    parallel = agents[1:]
    return WorkflowSpec.model_validate(
        {
            "schema_version": 1,
            "name": "test-workflow",
            "slash_command": "/test",
            "primary_agent": primary,
            "parallel_agents": parallel,
            "write_globs": write_globs,
            "stop_on_postcondition_failure": True,
        }
    )


@pytest.mark.unit
class TestValidateWorkflowDisjointWrites:
    def test_empty_write_globs_passes(self) -> None:
        spec = _make_spec({})
        validate_workflow(spec)  # must not raise

    def test_single_agent_passes(self) -> None:
        spec = _make_spec({"agent-a": ["01-Requirement/*.json"]})
        validate_workflow(spec)  # must not raise

    def test_non_overlapping_passes(self) -> None:
        spec = _make_spec(
            {
                "agent-a": ["01-Requirement/04-Epics/*.json"],
                "agent-b": ["02-Architecture/*.md"],
            }
        )
        validate_workflow(spec)  # must not raise

    def test_exact_match_overlap_raises(self) -> None:
        spec = _make_spec(
            {
                "agent-a": ["01-Requirement/04-Epics/*.json"],
                "agent-b": ["01-Requirement/04-Epics/*.json"],
            }
        )
        with pytest.raises(WorkflowError) as exc_info:
            validate_workflow(spec)
        msg = str(exc_info.value)
        assert "disjoint-writes violation" in msg
        # specialist list is sorted lexicographically
        assert "agent-a" in msg
        assert "agent-b" in msg

    def test_exact_match_overlap_sorted_specialist_list(self) -> None:
        spec = _make_spec(
            {
                "zebra": ["data/*.json"],
                "alpha": ["data/*.json"],
            }
        )
        with pytest.raises(WorkflowError) as exc_info:
            validate_workflow(spec)
        details = exc_info.value.details
        assert details["specialists"] == ["alpha", "zebra"]

    def test_prefix_overlap_wildcard_vs_literal_raises(self) -> None:
        # agent-a writes to 01-Requirement/** which covers everything under 01-Requirement/
        # agent-b writes to 01-Requirement/04-Epics/*.json which is under that prefix
        spec = _make_spec(
            {
                "agent-a": ["01-Requirement/**"],
                "agent-b": ["01-Requirement/04-Epics/*.json"],
            }
        )
        with pytest.raises(WorkflowError) as exc_info:
            validate_workflow(spec)
        msg = str(exc_info.value)
        assert "disjoint-writes violation" in msg

    def test_prefix_overlap_canonical_witness_is_literal_subdir(self) -> None:
        # When ** overlaps a literal subdir, the literal subdir is the canonical witness
        spec = _make_spec(
            {
                "agent-a": ["01-Requirement/**"],
                "agent-b": ["01-Requirement/04-Epics/*.json"],
            }
        )
        with pytest.raises(WorkflowError) as exc_info:
            validate_workflow(spec)
        details = exc_info.value.details
        # The canonical glob is the literal (more specific) one
        assert details["glob"] == "01-Requirement/04-Epics/*.json"

    def test_deeply_nested_overlap_raises(self) -> None:
        spec = _make_spec(
            {
                "agent-a": ["**/*.json"],
                "agent-b": ["01/02/03/*.json"],
            }
        )
        with pytest.raises(WorkflowError) as exc_info:
            validate_workflow(spec)
        assert "disjoint-writes violation" in str(exc_info.value)

    def test_error_message_shape(self) -> None:
        spec = _make_spec(
            {
                "agent-a": ["data/*.json"],
                "agent-b": ["data/*.json"],
            }
        )
        with pytest.raises(WorkflowError) as exc_info:
            validate_workflow(spec)
        msg = str(exc_info.value)
        assert msg.startswith("disjoint-writes violation: specialists")
        assert "both write to glob" in msg

    def test_literal_only_glob_no_wildcards_passes(self) -> None:
        # Covers the "loop exhausted without break" branch in _literal_prefix
        # when a glob has no wildcard characters at all.
        spec = _make_spec(
            {
                "agent-a": ["01/Requirement/exact-file.json"],
                "agent-b": ["02/Architecture/other-file.json"],
            }
        )
        validate_workflow(spec)  # non-overlapping literal globs — must not raise
