"""Integration tests for destructive-op dispatcher pause (Story 2B.6 AC3 + AC4 Receipt #3).

Proves:
- Destructive tool_calls trigger the reconfirmation pause
- Wrong nonce → DispatchError("destructive operation rejected by user at <stage>")
- Correct nonce → proceeds + emits destructive_op_reconfirmed journal entry
- Non-destructive result → passes through without pause
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher._panel_helpers import _reset_seq_cache_for_test, _run_member
from sdlc.errors import DispatchError
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

_SPECIALIST_NAME = "code-author"
_TARGET = "src/app/main.py"
_FIXED_NONCE = "FIXED_NONCE_FOR_TESTS"


def _make_specialist(write_globs: tuple[str, ...] = (_TARGET,)) -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=_SPECIALIST_NAME,
        title="Code Author",
        icon="🛠",
        model="claude-opus-4-5",
        description="Writes source code.",
        write_globs=write_globs,
    )
    return Specialist(
        frontmatter=fm,
        body="Write the implementation.",
        source_path=Path(f"specialists/{_SPECIALIST_NAME}.md"),
    )


def _make_step() -> WorkflowSpec:
    return WorkflowSpec(
        schema_version=1,
        name="code-writing",
        slash_command="sdlc-task",
        primary_agent=_SPECIALIST_NAME,
        parallel_agents=(),
        synthesizer_agent=None,
        write_globs={_SPECIALIST_NAME: (_TARGET,)},
    )


def _make_registry(specialist: Specialist | None = None) -> SpecialistRegistry:
    s = specialist or _make_specialist()
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s}))


def _agent_result_with_destructive_toolcall(cmd: str = "rm -rf /data") -> AgentResult:
    return AgentResult(
        output_text="done",
        tokens_in=10,
        tokens_out=5,
        tool_calls=({"name": "Bash", "command": cmd},),
    )


def _safe_agent_result() -> AgentResult:
    return AgentResult(output_text="safe output", tokens_in=5, tokens_out=3, tool_calls=())


async def _instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)


class TestDestructiveOpDispatcherPause:
    """AC3 Receipt #3 — proves detect-pause-record path all fire."""

    def test_wrong_nonce_raises_dispatch_error(self, tmp_path: Path) -> None:
        """Wrong nonce at re-confirmation → DispatchError with 'rejected by user' message."""
        journal_path = tmp_path / "journal.log"
        agent_runs_path = tmp_path / "agent_runs.jsonl"

        runtime = AsyncMock()
        runtime.dispatch.return_value = _agent_result_with_destructive_toolcall("rm -rf /important")

        _reset_seq_cache_for_test()

        with (
            patch("secrets.token_urlsafe", return_value=_FIXED_NONCE),
            patch("builtins.input", return_value="wrong-nonce"),
            pytest.raises(DispatchError) as exc_info,
        ):
            asyncio.run(
                _run_member(
                    _make_step(),
                    _SPECIALIST_NAME,
                    "primary",
                    runtime=runtime,
                    registry=_make_registry(),
                    repo_root=tmp_path,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    prompt_builder=lambda s, step: "prompt",
                    sleep=_instant_sleep,
                    max_attempts=1,
                    persist_artifact=False,
                )
            )

        assert "rejected by user" in str(exc_info.value)

    def test_correct_nonce_emits_reconfirmed_journal_entry(self, tmp_path: Path) -> None:
        """Correct nonce → destructive_op_reconfirmed journal entry recorded."""
        journal_path = tmp_path / "journal.log"
        agent_runs_path = tmp_path / "agent_runs.jsonl"

        runtime = AsyncMock()
        runtime.dispatch.return_value = _agent_result_with_destructive_toolcall("rm -rf /data")

        _reset_seq_cache_for_test()

        with (
            patch("secrets.token_urlsafe", return_value=_FIXED_NONCE),
            patch("builtins.input", return_value=_FIXED_NONCE),
        ):
            asyncio.run(
                _run_member(
                    _make_step(),
                    _SPECIALIST_NAME,
                    "primary",
                    runtime=runtime,
                    registry=_make_registry(),
                    repo_root=tmp_path,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    prompt_builder=lambda s, step: "prompt",
                    sleep=_instant_sleep,
                    max_attempts=1,
                    persist_artifact=False,
                )
            )

        assert journal_path.exists(), "journal.log must exist after dispatch"
        entries = [
            json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()
        ]
        kinds = [e.get("kind") for e in entries]
        assert "destructive_op_reconfirmed" in kinds, (
            f"Expected 'destructive_op_reconfirmed' in {kinds}"
        )

        reconfirmed = next(e for e in entries if e.get("kind") == "destructive_op_reconfirmed")
        payload = reconfirmed["payload"]
        assert payload["category"] == "file_delete"
        assert payload["outcome"] == "accepted"
        assert payload["nonce"] == _FIXED_NONCE

    def test_rejected_nonce_emits_rejected_journal_entry(self, tmp_path: Path) -> None:
        """Wrong nonce → destructive_op_rejected journal entry recorded before DispatchError."""
        journal_path = tmp_path / "journal.log"
        agent_runs_path = tmp_path / "agent_runs.jsonl"

        runtime = AsyncMock()
        runtime.dispatch.return_value = _agent_result_with_destructive_toolcall("rm -rf /data")

        _reset_seq_cache_for_test()

        with (
            patch("secrets.token_urlsafe", return_value=_FIXED_NONCE),
            patch("builtins.input", return_value="bad-nonce"),
            pytest.raises(DispatchError),
        ):
            asyncio.run(
                _run_member(
                    _make_step(),
                    _SPECIALIST_NAME,
                    "primary",
                    runtime=runtime,
                    registry=_make_registry(),
                    repo_root=tmp_path,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    prompt_builder=lambda s, step: "prompt",
                    sleep=_instant_sleep,
                    max_attempts=1,
                    persist_artifact=False,
                )
            )

        assert journal_path.exists()
        entries = [
            json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()
        ]
        kinds = [e.get("kind") for e in entries]
        assert "destructive_op_rejected" in kinds, f"Expected 'destructive_op_rejected' in {kinds}"

        rejected = next(e for e in entries if e.get("kind") == "destructive_op_rejected")
        assert rejected["payload"]["outcome"] == "rejected"

    def test_safe_tool_calls_pass_through_without_pause(self, tmp_path: Path) -> None:
        """Non-destructive AgentResult does NOT trigger input() prompt."""
        journal_path = tmp_path / "journal.log"
        agent_runs_path = tmp_path / "agent_runs.jsonl"

        runtime = AsyncMock()
        runtime.dispatch.return_value = _safe_agent_result()

        _reset_seq_cache_for_test()
        input_called: list[bool] = []

        def spy_input(prompt: str) -> str:
            input_called.append(True)
            return "nonce"

        with (
            patch("secrets.token_urlsafe", return_value=_FIXED_NONCE),
            patch("builtins.input", side_effect=spy_input),
        ):
            asyncio.run(
                _run_member(
                    _make_step(),
                    _SPECIALIST_NAME,
                    "primary",
                    runtime=runtime,
                    registry=_make_registry(),
                    repo_root=tmp_path,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    prompt_builder=lambda s, step: "prompt",
                    sleep=_instant_sleep,
                    max_attempts=1,
                    persist_artifact=False,
                )
            )

        assert not input_called, "input() must NOT be called for non-destructive tool_calls"

    def test_empty_tool_calls_passes_through_without_pause(self, tmp_path: Path) -> None:
        """Empty tool_calls tuple on AgentResult does NOT trigger pause."""
        journal_path = tmp_path / "journal.log"
        agent_runs_path = tmp_path / "agent_runs.jsonl"

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="ok", tokens_in=1, tokens_out=1)

        _reset_seq_cache_for_test()
        input_called: list[bool] = []

        def spy_input(prompt: str) -> str:
            input_called.append(True)
            return ""

        with (
            patch("secrets.token_urlsafe", return_value=_FIXED_NONCE),
            patch("builtins.input", side_effect=spy_input),
        ):
            asyncio.run(
                _run_member(
                    _make_step(),
                    _SPECIALIST_NAME,
                    "primary",
                    runtime=runtime,
                    registry=_make_registry(),
                    repo_root=tmp_path,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    prompt_builder=lambda s, step: "prompt",
                    sleep=_instant_sleep,
                    max_attempts=1,
                    persist_artifact=False,
                )
            )

        assert not input_called, "input() must NOT be called when tool_calls is empty"
