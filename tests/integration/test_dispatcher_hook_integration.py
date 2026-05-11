"""Integration tests for dispatcher hook chain wiring (AC6, Story 2A.6, Task 3.1+3.3).

Replaces tests/integration/test_hook_chain_smoke.py (Story 2A.4 Task 8.1).  Covers:
- Sections 1-4: dispatch() end-to-end with hook chain executing inside _run_member.
- Section 5 (TestRunHookChainDirect): run_hook_chain standalone — migrated from the
  smoke test for scenarios not exercised through the dispatcher path (journal_path=None
  and payload construction roundtrip).

Architecture §1067 (dispatcher → hooks allowed), §1109 (hooks → dispatcher forbidden).
Decision D2: one HookPayload contract, two callers — engine-side dispatcher + Claude-side
pre_tool_use.py (verified here via the engine path).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher._hook_chain import build_pre_write_hook_chain
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import BypassRequest, run_hook_chain
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_PRIMARY = "product-strategist"
_OUTPUT = "# Product Requirements\n\nContent here.\n"


def _make_specialist(name: str, target: str) -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=name,
        title="Product Strategist",
        icon="📋",
        model="claude-opus-4-5",
        description="Writes product requirements.",
        write_globs=(target,),
    )
    return Specialist(
        frontmatter=fm,
        body="You are the product strategist.",
        source_path=Path(f"specialists/{name}.md"),
    )


def _make_step(name: str, specialist: str, target: str) -> WorkflowSpec:
    return WorkflowSpec(
        schema_version=1,
        name=name,
        slash_command="sdlc-start",
        primary_agent=specialist,
        parallel_agents=(),
        synthesizer_agent=None,
        write_globs={specialist: (target,)},
    )


def _make_registry(*specialists: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specialists}))


async def _instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 1. Allow path — plain path passes both hooks → file written + journal OK
# ---------------------------------------------------------------------------

_PLAIN_TARGET = "docs/01-PRODUCT.md"


@pytest.mark.integration
class TestDispatcherAllowPath:
    """AC6 allow path: naming_validator + phase_gate both allow → file written."""

    def test_allow_file_written(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        specialist = _make_specialist(_PRIMARY, _PLAIN_TARGET)
        step = _make_step("requirements", _PRIMARY, _PLAIN_TARGET)
        registry = _make_registry(specialist)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=_OUTPUT, tokens_in=1, tokens_out=1)
        hooks = build_pre_write_hook_chain(tmp_path)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    hooks=hooks,
                )
            )

        assert (tmp_path / _PLAIN_TARGET).exists()

    def test_allow_journal_has_dispatch_attempt_and_artifact_written(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        specialist = _make_specialist(_PRIMARY, _PLAIN_TARGET)
        step = _make_step("requirements", _PRIMARY, _PLAIN_TARGET)
        registry = _make_registry(specialist)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=_OUTPUT, tokens_in=1, tokens_out=1)
        hooks = build_pre_write_hook_chain(tmp_path)
        captured: list = []

        async def _capture(entry, journal_path):  # type: ignore[no-untyped-def]
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    hooks=hooks,
                )
            )

        kinds = [e.kind for e in captured]
        assert "dispatch_attempt" in kinds
        assert "artifact_written" in kinds
        attempt = next(e for e in captured if e.kind == "dispatch_attempt")
        assert attempt.payload["outcome"] == "success"


# ---------------------------------------------------------------------------
# 2. Deny path — naming_violation (EPC_typo.json)
# ---------------------------------------------------------------------------

_NAMING_DENY_TARGET = "01-Requirement/04-Epics/EPC_typo.json"


@pytest.mark.integration
class TestDispatcherDenyNamingViolation:
    """AC6 deny path: naming_validator blocks EPC_typo.json → file NOT written."""

    def test_deny_file_not_written(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        specialist = _make_specialist(_PRIMARY, _NAMING_DENY_TARGET)
        step = _make_step("epic-create", _PRIMARY, _NAMING_DENY_TARGET)
        registry = _make_registry(specialist)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=_OUTPUT, tokens_in=1, tokens_out=1)
        hooks = build_pre_write_hook_chain(tmp_path)
        target_file = tmp_path / _NAMING_DENY_TARGET

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    hooks=hooks,
                )
            )

        # Deny path: dispatcher must NOT write the file when hook chain denies.
        assert not target_file.exists()

    def test_deny_journal_hook_rejected_and_dispatch_attempt_hook_rejected(
        self, tmp_path: Path
    ) -> None:
        from sdlc.dispatcher.core import dispatch

        specialist = _make_specialist(_PRIMARY, _NAMING_DENY_TARGET)
        step = _make_step("epic-create", _PRIMARY, _NAMING_DENY_TARGET)
        registry = _make_registry(specialist)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=_OUTPUT, tokens_in=1, tokens_out=1)
        hooks = build_pre_write_hook_chain(tmp_path)
        dispatcher_captured: list = []
        hooks_captured: list = []

        async def _cap_dispatcher(entry, journal_path):  # type: ignore[no-untyped-def]
            dispatcher_captured.append(entry)

        async def _cap_hooks(entry, journal_path):  # type: ignore[no-untyped-def]
            hooks_captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_cap_dispatcher),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            patch("sdlc.hooks.runner._do_journal_append", side_effect=_cap_hooks),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    hooks=hooks,
                )
            )

        # hook_rejected written by hooks.runner
        assert any(e.kind == "hook_rejected" for e in hooks_captured), (
            "expected hook_rejected journal entry from hooks.runner"
        )
        hook_rej = next(e for e in hooks_captured if e.kind == "hook_rejected")
        assert hook_rej.payload["error_code"] == "naming_violation"

        # dispatch_attempt with outcome=hook_rejected written by dispatcher
        assert any(e.kind == "dispatch_attempt" for e in dispatcher_captured), (
            "expected dispatch_attempt journal entry from dispatcher"
        )
        attempt = next(e for e in dispatcher_captured if e.kind == "dispatch_attempt")
        assert attempt.payload["outcome"] == "hook_rejected"


# ---------------------------------------------------------------------------
# 3. Deny path — phase_gate violation (Phase-2 path, no signoff in tmp_path)
# ---------------------------------------------------------------------------

_PHASE2_TARGET = "02-Architecture/01-UX/01-tokens.md"


@pytest.mark.integration
class TestDispatcherDenyPhaseGate:
    """AC6 deny path: phase_gate blocks Phase-2 write when phase-1.yaml absent."""

    def test_deny_phase2_no_signoff_file_not_written(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        specialist = _make_specialist(_PRIMARY, _PHASE2_TARGET)
        step = _make_step("architecture", _PRIMARY, _PHASE2_TARGET)
        registry = _make_registry(specialist)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=_OUTPUT, tokens_in=1, tokens_out=1)
        hooks = build_pre_write_hook_chain(tmp_path)
        target_file = tmp_path / _PHASE2_TARGET

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    hooks=hooks,
                )
            )

        # Deny path: dispatcher must NOT write the file when hook chain denies.
        assert not target_file.exists()

    def test_deny_phase2_journal_has_hook_rejected_phase_gate(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        specialist = _make_specialist(_PRIMARY, _PHASE2_TARGET)
        step = _make_step("architecture", _PRIMARY, _PHASE2_TARGET)
        registry = _make_registry(specialist)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=_OUTPUT, tokens_in=1, tokens_out=1)
        hooks = build_pre_write_hook_chain(tmp_path)
        hooks_captured: list = []

        async def _cap_hooks(entry, journal_path):  # type: ignore[no-untyped-def]
            hooks_captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            patch("sdlc.hooks.runner._do_journal_append", side_effect=_cap_hooks),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    hooks=hooks,
                )
            )

        assert any(e.kind == "hook_rejected" for e in hooks_captured)
        rej = next(e for e in hooks_captured if e.kind == "hook_rejected")
        assert rej.payload["error_code"] == "phase_gate_violation"


# ---------------------------------------------------------------------------
# 4. Bypass path — bypass_phase_gate=True lets Phase-2 write through
# ---------------------------------------------------------------------------

_BYPASS_JUSTIFICATION = "emergency hotfix to unblock team build"


@pytest.mark.integration
class TestDispatcherBypassPhaseGate:
    """AC6 bypass path: BypassRequest with valid justification skips phase_gate."""

    def test_bypass_file_written(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        specialist = _make_specialist(_PRIMARY, _PHASE2_TARGET)
        step = _make_step("architecture", _PRIMARY, _PHASE2_TARGET)
        registry = _make_registry(specialist)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=_OUTPUT, tokens_in=1, tokens_out=1)
        hooks = build_pre_write_hook_chain(tmp_path)
        bypass = BypassRequest(bypass_phase_gate=True, justification=_BYPASS_JUSTIFICATION)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    hooks=hooks,
                    bypass=bypass,
                )
            )

        assert (tmp_path / _PHASE2_TARGET).exists()

    def test_bypass_journal_has_bypass_signoff(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        specialist = _make_specialist(_PRIMARY, _PHASE2_TARGET)
        step = _make_step("architecture", _PRIMARY, _PHASE2_TARGET)
        registry = _make_registry(specialist)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=_OUTPUT, tokens_in=1, tokens_out=1)
        hooks = build_pre_write_hook_chain(tmp_path)
        bypass = BypassRequest(bypass_phase_gate=True, justification=_BYPASS_JUSTIFICATION)
        hooks_captured: list = []

        async def _cap_hooks(entry, journal_path):  # type: ignore[no-untyped-def]
            hooks_captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            patch("sdlc.hooks.runner._do_journal_append", side_effect=_cap_hooks),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    hooks=hooks,
                    bypass=bypass,
                )
            )

        assert any(e.kind == "bypass_signoff" for e in hooks_captured), (
            "expected bypass_signoff journal entry from hooks.runner"
        )
        signoff = next(e for e in hooks_captured if e.kind == "bypass_signoff")
        assert signoff.payload["justification"] == _BYPASS_JUSTIFICATION


# ---------------------------------------------------------------------------
# 5. run_hook_chain direct tests — migrated from test_hook_chain_smoke.py
#    (Task 3.3). Covers scenarios NOT exercised through the dispatcher path:
#    journal_path=None (no entry emitted) and payload construction roundtrip.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRunHookChainDirect:
    """Direct run_hook_chain tests migrated from test_hook_chain_smoke.py (AC7, 2A.4 Task 8.1)."""

    async def test_allow_path_no_journal(self, tmp_path: Path) -> None:
        """Valid epic path, journal_path=None → chain allows, _do_journal_append NOT called."""
        payload = build_write_intent_payload(
            hook_name="naming_validator",
            target_path="01-Requirement/04-Epics/EPIC-stripe-webhook.json",
            write_intent="create epic JSON",
        )
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                payload,
                hooks=build_pre_write_hook_chain(tmp_path),
                journal_path=None,
            )
        assert result.decision == "allow"
        mock_j.assert_not_called()

    async def test_payload_construction_roundtrip(self, tmp_path: Path) -> None:
        """build_write_intent_payload → run_hook_chain → allow for a valid phase-1 epic path."""
        payload = build_write_intent_payload(
            hook_name="naming_validator",
            target_path="01-Requirement/04-Epics/EPIC-foo-bar.json",
            write_intent="create epic",
        )
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock):
            result = await run_hook_chain(
                payload,
                hooks=build_pre_write_hook_chain(tmp_path),
                journal_path=None,
            )
        assert result.decision == "allow"
