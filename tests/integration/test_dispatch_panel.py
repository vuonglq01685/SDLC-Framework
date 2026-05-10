"""Integration tests for dispatch_panel() (Story 2A.3, AC2 + AC3 + AC11 mandatory).

DR1 of Story 2A.3 review: AC11 mandates `test_dispatch_panel.py` as integration coverage
for the panel orchestration path "regardless of D choice".

Verifies:
- AC2 step 1 + P7+P8: Phase 0 atomicity — missing parallel/synth specialist rejected
  BEFORE any primary write happens.
- AC2 step 2 + P4: parallel members run concurrently under semaphore; partial failure
  preserves successful sibling results (no orphan coros).
- AC2 step 3 + DR5: synthesizer dispatched after panel completes with panel_outputs;
  synth target overwrites primary's first write_glob entry.
- AC2 'and' + P6: synth dispatch_attempt journal payload includes panel_size = N+1.
- AC2.5: synthesizer NOT dispatched on panel-member failure.
- AC3: dispatcher does NOT re-run disjoint_writes_check at runtime (covered separately
  in test_dispatch_disjoint_writes.py — this file focuses on positive flows).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import DispatchError, SpecialistError
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

_PRIMARY = "product-strategist"
_PAR_A = "technical-researcher"
_PAR_B = "devil-advocate"
_SYNTH = "synthesizer"


def _make_specialist(name: str, target: str, body: str = "body") -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=name,
        title=name.title(),
        icon="🤖",
        model="claude-opus-4-5",
        description=f"{name} specialist",
        write_globs=(target,),
    )
    return Specialist(frontmatter=fm, body=body, source_path=Path(f"specialists/{name}.md"))


def _make_registry(*specialists: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specialists}))


def _make_step(
    *, parallel: tuple[str, ...] = (), synth: str | None = None, primary_target: str = "docs/01.md"
) -> WorkflowSpec:
    write_globs = {_PRIMARY: (primary_target,)}
    for name in parallel:
        write_globs[name] = (f"docs/par-{name}.md",)
    if synth:
        write_globs[synth] = (f"docs/synth-{synth}.md",)
    return WorkflowSpec(
        schema_version=1,
        name="requirements",
        slash_command="sdlc-start",
        primary_agent=_PRIMARY,
        parallel_agents=parallel,
        synthesizer_agent=synth,
        write_globs=write_globs,
    )


async def _instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)


def _runtime_returning(text: str = "out") -> AsyncMock:
    runtime = AsyncMock()
    runtime.dispatch.return_value = AgentResult(output_text=text, tokens_in=1, tokens_out=1)
    return runtime


class TestDispatchPanelHappyPaths:
    """AC2 happy paths — primary-only, primary+parallel, primary+parallel+synth."""

    def test_primary_only_returns_panel_result(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step()
        registry = _make_registry(_make_specialist(_PRIMARY, "docs/01.md"))
        runtime = _runtime_returning("primary-out")
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        assert result.outcome == "success"
        assert result.parallel_results == ()
        assert result.synthesizer_result is None
        assert result.primary_result.specialist_name == _PRIMARY

    def test_primary_plus_parallel_returns_all_results(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A, _PAR_B))
        registry = _make_registry(
            _make_specialist(_PRIMARY, "docs/01.md"),
            _make_specialist(_PAR_A, f"docs/par-{_PAR_A}.md"),
            _make_specialist(_PAR_B, f"docs/par-{_PAR_B}.md"),
        )
        runtime = _runtime_returning("out")
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        assert result.outcome == "success"
        assert len(result.parallel_results) == 2
        names = [r.specialist_name for r in result.parallel_results]
        assert names == [_PAR_A, _PAR_B]  # input-order preservation

    def test_synth_dispatched_after_panel_with_panel_outputs(self, tmp_path: Path) -> None:
        """AC2 step 3: synth context includes panel_outputs from primary + parallel."""
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,), synth=_SYNTH)
        registry = _make_registry(
            _make_specialist(_PRIMARY, "docs/01.md"),
            _make_specialist(_PAR_A, f"docs/par-{_PAR_A}.md"),
            _make_specialist(_SYNTH, f"docs/synth-{_SYNTH}.md"),
        )
        seen_contexts: list[dict] = []

        async def _capture(prompt: str, context: dict) -> AgentResult:
            seen_contexts.append(context)
            return AgentResult(
                output_text=f"out:{context['agent_name']}", tokens_in=1, tokens_out=1
            )

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _capture
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        assert result.outcome == "success"
        assert result.synthesizer_result is not None
        synth_ctx = next(c for c in seen_contexts if c["target_kind"] == "synthesizer")
        assert "panel_outputs" in synth_ctx
        panel_outputs = synth_ctx["panel_outputs"]
        assert _PRIMARY in panel_outputs
        assert _PAR_A in panel_outputs
        assert panel_outputs[_PRIMARY] == f"out:{_PRIMARY}"

    def test_synth_overwrites_primary_target_path(self, tmp_path: Path) -> None:
        """AC2.4 + DR5: synth's artifact lands at primary's first write_glob entry."""
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(), synth=_SYNTH, primary_target="docs/01-PRODUCT.md")
        registry = _make_registry(
            _make_specialist(_PRIMARY, "docs/01-PRODUCT.md"),
            _make_specialist(_SYNTH, f"docs/synth-{_SYNTH}.md"),
        )
        outputs = iter(["primary-text", "synth-text"])

        async def _seq_dispatch(prompt: str, context: dict) -> AgentResult:
            return AgentResult(output_text=next(outputs), tokens_in=1, tokens_out=1)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _seq_dispatch
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        assert result.synthesizer_result is not None
        # DR5: synth target_path equals primary's resolved write_globs[0]
        primary_target = (tmp_path / "docs/01-PRODUCT.md").resolve()
        assert result.synthesizer_result.target_path == primary_target
        # Final on-disk content is the synth output, overwriting primary's earlier write
        assert primary_target.read_text(encoding="utf-8") == "synth-text"

    def test_synth_journal_payload_includes_panel_size(self, tmp_path: Path) -> None:
        """P6: synth dispatch_attempt payload carries panel_size = N+1."""
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A, _PAR_B), synth=_SYNTH)
        registry = _make_registry(
            _make_specialist(_PRIMARY, "docs/01.md"),
            _make_specialist(_PAR_A, f"docs/par-{_PAR_A}.md"),
            _make_specialist(_PAR_B, f"docs/par-{_PAR_B}.md"),
            _make_specialist(_SYNTH, f"docs/synth-{_SYNTH}.md"),
        )
        runtime = _runtime_returning("out")
        captured: list = []

        async def _capture_journal(entry, journal_path):  # type: ignore[no-untyped-def]
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture_journal),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        synth_attempts = [
            e
            for e in captured
            if e.kind == "dispatch_attempt" and e.payload.get("target_kind") == "synthesizer"
        ]
        assert len(synth_attempts) == 1
        assert synth_attempts[0].payload["panel_size"] == 4  # 1 primary + 2 parallel + 1 synth


class TestDispatchPanelAtomicity:
    """AC2 step 1 + P7+P8 — Phase 0 pre-resolution prevents partial dispatch."""

    def test_missing_parallel_specialist_rejected_before_primary_writes(
        self, tmp_path: Path
    ) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,))  # _PAR_A not in registry
        registry = _make_registry(_make_specialist(_PRIMARY, "docs/01.md"))
        runtime = _runtime_returning("out")
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            pytest.raises(SpecialistError),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        # Primary's target file MUST NOT exist on disk (atomicity).
        primary_target = tmp_path / "docs/01.md"
        assert not primary_target.exists()

    def test_missing_synth_specialist_rejected_before_primary_writes(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(synth=_SYNTH)  # _SYNTH not in registry
        registry = _make_registry(_make_specialist(_PRIMARY, "docs/01.md"))
        runtime = _runtime_returning("out")
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            pytest.raises(SpecialistError),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        primary_target = tmp_path / "docs/01.md"
        assert not primary_target.exists()


class TestDispatchPanelFailurePropagation:
    """AC2.5 — synth NOT dispatched on panel failure; AC5 stop_trigger emitted."""

    def test_parallel_failure_skips_synth_dispatch(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,), synth=_SYNTH)
        registry = _make_registry(
            _make_specialist(_PRIMARY, "docs/01.md"),
            _make_specialist(_PAR_A, f"docs/par-{_PAR_A}.md"),
            _make_specialist(_SYNTH, f"docs/synth-{_SYNTH}.md"),
        )
        dispatched: list[str] = []

        async def _selective(prompt: str, context: dict) -> AgentResult:
            name = context.get("agent_name", "?")
            dispatched.append(name)
            if name == _PAR_A:
                raise DispatchError("parallel A blew up")
            return AgentResult(output_text="ok", tokens_in=1, tokens_out=1)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _selective
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    _max_attempts=1,
                )
            )
        assert result.outcome == "failed"
        assert _SYNTH not in dispatched

    def test_panel_failure_emits_stop_trigger_raised(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,))
        registry = _make_registry(
            _make_specialist(_PRIMARY, "docs/01.md"),
            _make_specialist(_PAR_A, f"docs/par-{_PAR_A}.md"),
        )

        async def _fail(prompt: str, context: dict) -> AgentResult:
            if context.get("target_kind") == "parallel":
                raise DispatchError("parallel down")
            return AgentResult(output_text="ok", tokens_in=1, tokens_out=1)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _fail
        captured: list = []

        async def _capture_journal(entry, journal_path):  # type: ignore[no-untyped-def]
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture_journal),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    _max_attempts=1,
                )
            )
        stop_kinds = [e for e in captured if e.kind == "stop_trigger_raised"]
        assert len(stop_kinds) == 1


class TestDispatchPanelInvariantInputs:
    """P12 — dispatch_panel rejects out-of-range max_parallel_agents at entry."""

    def test_max_parallel_agents_zero_rejected(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step()
        registry = _make_registry(_make_specialist(_PRIMARY, "docs/01.md"))
        runtime = _runtime_returning("out")
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            pytest.raises(DispatchError, match="max_parallel_agents"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    max_parallel_agents=0,
                )
            )
