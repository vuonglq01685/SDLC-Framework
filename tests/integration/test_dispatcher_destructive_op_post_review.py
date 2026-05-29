"""Post-review hardening tests for the destructive-op dispatcher pause.

Covers patches and decisions added in the 2026-05-28 ``bmad-code-review``
session: D3 (read-only specialist integrity violation), D4 (nonce hashed in
journal payload), D5 (asyncio.Lock around stdin reads), D6 (all-or-nothing
multi-tool_call ceremony), and v1 architectural pivot for the
prompt-side nonce (deferred to ``EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE``).

Split from ``test_dispatcher_destructive_op.py`` to keep both files under the
400-LOC cap (Architecture §765 / NFR-MAINT-3).
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


def _readonly_specialist() -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=_SPECIALIST_NAME,
        title="Read-only researcher",
        icon="🔎",
        model="claude-opus-4-5",
        description="Reads only.",
        write_globs=("_bmad-output/research/notes.md",),
    )
    return Specialist(
        frontmatter=fm,
        body="Research only.",
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


def _agent_result_with_multi_destructive() -> AgentResult:
    return AgentResult(
        output_text="done",
        tokens_in=10,
        tokens_out=5,
        tool_calls=(
            {"name": "Bash", "command": "rm -rf /a"},
            {"name": "Bash", "command": "git push --force"},
            {"name": "Bash", "command": "DROP TABLE users"},
        ),
    )


async def _instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)


def _run_member_sync(
    tmp_path: Path,
    runtime: AsyncMock,
    *,
    specialist: Specialist | None = None,
    prompt_builder: object = None,
) -> None:
    journal_path = tmp_path / "journal.log"
    agent_runs_path = tmp_path / "agent_runs.jsonl"
    asyncio.run(
        _run_member(
            _make_step(),
            _SPECIALIST_NAME,
            "primary",
            runtime=runtime,
            registry=_make_registry(specialist),
            repo_root=tmp_path,
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
            prompt_builder=prompt_builder or (lambda s, step: "prompt"),
            sleep=_instant_sleep,
            max_attempts=1,
            persist_artifact=False,
        )
    )


class TestPostReviewHardening:
    """D3/D4/D5/D6 + v1 pivot + P27/P28 (post-review 2026-05-28)."""

    def test_readonly_specialist_emitting_destructive_raises_without_prompt_d3(
        self, tmp_path: Path
    ) -> None:
        """D3: read-only specialist + destructive op = integrity violation.
        Dispatcher raises WITHOUT prompting and emits the new journal kind."""
        runtime = AsyncMock()
        runtime.dispatch.return_value = _agent_result_with_destructive_toolcall("rm -rf /etc")
        _reset_seq_cache_for_test()
        input_called: list[bool] = []

        def spy_input(prompt: str) -> str:
            input_called.append(True)
            return _FIXED_NONCE  # never reached if D3 holds

        with (
            patch(
                "sdlc.dispatcher._panel_helpers.secrets.token_urlsafe", return_value=_FIXED_NONCE
            ),
            patch("builtins.input", side_effect=spy_input),
            pytest.raises(DispatchError) as exc_info,
        ):
            _run_member_sync(tmp_path, runtime, specialist=_readonly_specialist())

        assert "read-only specialist" in str(exc_info.value)
        assert not input_called, "user prompt must NOT fire for integrity violation"

        entries = [
            json.loads(line)
            for line in (tmp_path / "journal.log").read_text().splitlines()
            if line.strip()
        ]
        kinds = [e.get("kind") for e in entries]
        assert "destructive_op_from_readonly_specialist" in kinds, kinds

    def test_multi_destructive_all_accepted_emits_reconfirmed_for_each_d6(
        self, tmp_path: Path
    ) -> None:
        """D6: when every nonce echoes correctly, every destructive tool_call
        gets its own ``destructive_op_reconfirmed`` journal entry."""
        runtime = AsyncMock()
        runtime.dispatch.return_value = _agent_result_with_multi_destructive()
        _reset_seq_cache_for_test()

        with (
            patch(
                "sdlc.dispatcher._panel_helpers.secrets.token_urlsafe", return_value=_FIXED_NONCE
            ),
            patch("builtins.input", return_value=_FIXED_NONCE),
        ):
            _run_member_sync(tmp_path, runtime)

        entries = [
            json.loads(line)
            for line in (tmp_path / "journal.log").read_text().splitlines()
            if line.strip()
        ]
        reconfirmed = [e for e in entries if e.get("kind") == "destructive_op_reconfirmed"]
        assert len(reconfirmed) == 3, [e.get("kind") for e in entries]
        categories = sorted(e["payload"]["category"] for e in reconfirmed)
        assert categories == sorted(["file_delete", "force_push", "drop_database"])

    def test_multi_destructive_one_rejected_emits_rejected_for_all_d6(self, tmp_path: Path) -> None:
        """D6: if any nonce echo is wrong, EVERY destructive tool_call gets a
        ``destructive_op_rejected`` entry and the dispatcher raises BEFORE any
        artifact write — no accepted-prefix-runs partial semantics."""
        runtime = AsyncMock()
        runtime.dispatch.return_value = _agent_result_with_multi_destructive()
        _reset_seq_cache_for_test()
        responses = iter([_FIXED_NONCE, "wrong", _FIXED_NONCE])

        with (
            patch(
                "sdlc.dispatcher._panel_helpers.secrets.token_urlsafe", return_value=_FIXED_NONCE
            ),
            patch("builtins.input", side_effect=lambda _prompt: next(responses)),
            pytest.raises(DispatchError),
        ):
            _run_member_sync(tmp_path, runtime)

        entries = [
            json.loads(line)
            for line in (tmp_path / "journal.log").read_text().splitlines()
            if line.strip()
        ]
        rejected = [e for e in entries if e.get("kind") == "destructive_op_rejected"]
        reconfirmed = [e for e in entries if e.get("kind") == "destructive_op_reconfirmed"]
        assert len(rejected) == 3, [e.get("kind") for e in entries]
        assert reconfirmed == [], reconfirmed

    def test_dispatcher_does_not_thread_nonce_into_phase1_builder_v1(self, tmp_path: Path) -> None:
        """V1 architectural pivot: the per-dispatch nonce is the HUMAN-TTY-side
        gate only. Threading it into the agent prompt would shift every prompt
        hash per dispatch (invalidating MockAIRuntime fixtures) without buying
        any v1 security, because v1 has no agent-side verification that the
        agent echoed the nonce back. That verification is opened as
        ``EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE`` per spec AC3/D3 (already
        deferred). When it lands, this test inverts: the builder MUST receive
        ``nonce=<session-token>``. For v1, the builder MUST NOT receive a
        nonce kwarg.
        """
        from sdlc.dispatcher import prompts as prompts_mod

        runtime = AsyncMock()
        runtime.dispatch.return_value = _safe_agent_result()
        _reset_seq_cache_for_test()
        captured_kwargs: list[dict[str, object]] = []

        def spy_builder(
            specialist: Specialist,
            step: WorkflowSpec,
            *,
            idea_text: str,
            role: str,
            **kwargs: object,
        ) -> str:
            kwargs["idea_text"] = idea_text
            kwargs["role"] = role
            captured_kwargs.append(dict(kwargs))
            return "prompt"

        spy_builder.__module__ = prompts_mod.__name__
        spy_builder.__qualname__ = "phase1_prompt_builder"

        with patch(
            "sdlc.dispatcher._panel_helpers.secrets.token_urlsafe", return_value=_FIXED_NONCE
        ):
            _run_member_sync(tmp_path, runtime, prompt_builder=spy_builder)

        assert captured_kwargs, "spy builder was never invoked"
        assert captured_kwargs[0].get("nonce") is None, captured_kwargs[0]

    def test_nonce_is_unique_across_dispatches_p27(self, tmp_path: Path) -> None:
        """P27: two consecutive ``_run_member`` invocations must produce two
        DISTINCT nonces (regression guard against future module-level caching)."""
        from sdlc.dispatcher import _panel_helpers as ph

        runtime = AsyncMock()
        runtime.dispatch.return_value = _safe_agent_result()
        _reset_seq_cache_for_test()

        async def _twice() -> tuple[str, str]:
            generated: list[str] = []
            real = ph.secrets.token_urlsafe

            def capturing_token_urlsafe(n: int = 16) -> str:
                v = real(n)
                generated.append(v)
                return v

            with patch.object(ph.secrets, "token_urlsafe", side_effect=capturing_token_urlsafe):
                for _ in range(2):
                    await _run_member(
                        _make_step(),
                        _SPECIALIST_NAME,
                        "primary",
                        runtime=runtime,
                        registry=_make_registry(),
                        repo_root=tmp_path,
                        journal_path=tmp_path / "journal.log",
                        agent_runs_path=tmp_path / "agent_runs.jsonl",
                        prompt_builder=lambda s, step: "prompt",
                        sleep=_instant_sleep,
                        max_attempts=1,
                        persist_artifact=False,
                    )
            assert len(generated) >= 2, generated
            return generated[0], generated[1]

        n1, n2 = asyncio.run(_twice())
        assert n1 != n2, f"nonce reused across dispatches: {n1}"
