"""Unit tests for engine/auto_brainstorm.py (Story 4.10)."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.dispatcher.core import DispatchResult, PanelResult
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

pytestmark = pytest.mark.unit

_PRIMARY = "product-strategist"
_PAR_A = "technical-researcher"
_PAR_B = "devil-advocate"
_SYNTH = "requirement-synthesizer"
_TASK_ID = "EPIC-e-S01-s-T01-task"
_SUMMARY = "ambiguous requirement scope"


def _options_md_body() -> str:
    return """# Clarification Options

## Option 1: Narrow MVP
### Pros
- Faster delivery
### Cons
- Limited scope
### Risks
- May miss edge cases
### Concerns preserved
- product-strategist: prioritize time-to-market
- technical-researcher: integration complexity is manageable
- devil-advocate: scope creep risk if too narrow

## Option 2: Full platform
### Pros
- Complete solution
### Cons
- Longer timeline
### Risks
- Over-engineering
### Concerns preserved
- product-strategist: long-term vision alignment
- technical-researcher: needs more research
- devil-advocate: budget overrun risk
"""


def _make_specialist(name: str) -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=name,
        title=name.replace("-", " ").title(),
        icon="🤖",
        model="claude-opus-4-5",
        description=f"{name} specialist",
        write_globs=(f"docs/{name}.md",),
    )
    return Specialist(frontmatter=fm, body=f"You are {name}.", source_path=Path(f"{name}.md"))


def _registry() -> SpecialistRegistry:
    specs = [_make_specialist(n) for n in (_PRIMARY, _PAR_A, _PAR_B, _SYNTH)]
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specs}))


def _panel_result(options_text: str) -> PanelResult:
    def _dr(name: str, text: str) -> DispatchResult:
        return DispatchResult(
            specialist_name=name,
            target_path=Path("docs/out.md"),
            agent_result=AgentResult(output_text=text, tokens_in=1, tokens_out=1),
            attempts=1,
            outcome="success",
        )

    return PanelResult(
        primary_result=_dr(_PRIMARY, "## Strategist\n"),
        parallel_results=(_dr(_PAR_A, "## Research\n"), _dr(_PAR_B, "## Risks\n")),
        synthesizer_result=_dr(_SYNTH, options_text),
        write_targets=(Path("docs/out.md"),),
        total_attempts=4,
        outcome="success",
    )


@pytest.mark.asyncio
async def test_bypass_writes_open_clarification_only(tmp_path: Path) -> None:
    from sdlc.engine.auto_brainstorm import AmbiguityContext, run_auto_brainstorm

    journal = tmp_path / ".claude" / "state" / "journal.log"
    journal.parent.mkdir(parents=True)
    journal.touch()
    runs = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    runs.parent.mkdir(parents=True)
    runs.touch()
    ctx = AmbiguityContext(task_id=_TASK_ID, summary=_SUMMARY)

    with patch("sdlc.engine.auto_brainstorm.dispatch_panel", new_callable=AsyncMock) as panel:
        clar_id = await run_auto_brainstorm(
            tmp_path,
            context=ctx,
            runtime=AsyncMock(),
            registry=_registry(),
            journal_path=journal,
            agent_runs_path=runs,
            correlation_id="cid-1",
            auto_brainstorm=False,
        )

    panel.assert_not_awaited()
    clar_dir = tmp_path / ".claude" / "state" / "clarifications" / clar_id
    assert (clar_dir / "open_clarification.md").is_file()
    assert not (clar_dir / "options.md").exists()


@pytest.mark.asyncio
async def test_idempotent_skips_second_panel_dispatch(tmp_path: Path) -> None:
    from sdlc.engine.auto_brainstorm import AmbiguityContext, run_auto_brainstorm

    journal = tmp_path / ".claude" / "state" / "journal.log"
    journal.parent.mkdir(parents=True)
    journal.touch()
    runs = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    runs.parent.mkdir(parents=True)
    runs.touch()
    ctx = AmbiguityContext(task_id=_TASK_ID, summary=_SUMMARY)
    panel = AsyncMock(return_value=_panel_result(_options_md_body()))

    with patch("sdlc.engine.auto_brainstorm.dispatch_panel", panel):
        first_id = await run_auto_brainstorm(
            tmp_path,
            context=ctx,
            runtime=AsyncMock(),
            registry=_registry(),
            journal_path=journal,
            agent_runs_path=runs,
            correlation_id="cid-1",
            auto_brainstorm=True,
        )
        second_id = await run_auto_brainstorm(
            tmp_path,
            context=ctx,
            runtime=AsyncMock(),
            registry=_registry(),
            journal_path=journal,
            agent_runs_path=runs,
            correlation_id="cid-2",
            auto_brainstorm=True,
        )

    assert first_id == second_id
    assert panel.await_count == 1


@pytest.mark.asyncio
async def test_options_md_from_panel_result_satisfies_fr26_shape(tmp_path: Path) -> None:
    from sdlc.engine.auto_brainstorm import (
        AmbiguityContext,
        parse_options_contract,
        run_auto_brainstorm,
    )

    journal = tmp_path / ".claude" / "state" / "journal.log"
    journal.parent.mkdir(parents=True)
    journal.touch()
    runs = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    runs.parent.mkdir(parents=True)
    runs.touch()
    body = _options_md_body()
    ctx = AmbiguityContext(task_id=_TASK_ID, summary=_SUMMARY)

    with patch(
        "sdlc.engine.auto_brainstorm.dispatch_panel",
        new_callable=AsyncMock,
        return_value=_panel_result(body),
    ):
        clar_id = await run_auto_brainstorm(
            tmp_path,
            context=ctx,
            runtime=AsyncMock(),
            registry=_registry(),
            journal_path=journal,
            agent_runs_path=runs,
            correlation_id="cid-1",
            auto_brainstorm=True,
        )

    options_path = tmp_path / ".claude" / "state" / "clarifications" / clar_id / "options.md"
    assert options_path.is_file()
    contract = parse_options_contract(options_path.read_text(encoding="utf-8"))
    assert contract.option_count >= 2
    assert contract.has_tradeoffs
    assert contract.preserves_member_concerns
    assert not contract.has_auto_pick


def test_detect_ambiguity_signal_reads_task_marker(tmp_path: Path) -> None:
    from sdlc.engine.auto_brainstorm import AmbiguityContext, detect_ambiguity_signal

    signals = tmp_path / ".claude" / "state" / "ambiguity_signals"
    signals.mkdir(parents=True)
    (signals / f"{_TASK_ID}.json").write_text(
        json.dumps({"summary": _SUMMARY}),
        encoding="utf-8",
    )
    ctx = detect_ambiguity_signal(tmp_path, task_id=_TASK_ID)
    assert ctx == AmbiguityContext(task_id=_TASK_ID, summary=_SUMMARY)


# --- CR4.10-D1: panel failure halts gracefully (no crash) -------------------


def _failed_panel_result() -> PanelResult:
    """A panel whose synthesizer never produced output (real ``dispatch_panel`` failure)."""
    return PanelResult(
        primary_result=DispatchResult(
            specialist_name=_PRIMARY,
            target_path=Path("docs/out.md"),
            agent_result=AgentResult(output_text="## Strategist\n", tokens_in=1, tokens_out=1),
            attempts=1,
            outcome="success",
        ),
        parallel_results=(),
        synthesizer_result=None,
        write_targets=(),
        total_attempts=3,
        outcome="failed",
    )


def _run_kwargs(tmp_path: Path) -> dict[str, object]:
    journal = tmp_path / ".claude" / "state" / "journal.log"
    journal.parent.mkdir(parents=True)
    journal.touch()
    runs = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    runs.parent.mkdir(parents=True)
    runs.touch()
    return {"journal": journal, "runs": runs}


def _panel_succeeded_flags(journal: Path) -> list[object]:
    from sdlc.journal import iter_entries

    return [
        e.payload.get("panel_succeeded")
        for e in iter_entries(journal)
        if e.kind == "auto_brainstorm_dispatched"
    ]


@pytest.mark.asyncio
async def test_panel_failure_halts_gracefully_without_crash(tmp_path: Path) -> None:
    """A non-success panel must NOT raise — it writes open_clarification.md and journals failure."""
    from sdlc.engine.auto_brainstorm import AmbiguityContext, run_auto_brainstorm

    k = _run_kwargs(tmp_path)
    ctx = AmbiguityContext(task_id=_TASK_ID, summary=_SUMMARY)
    panel = AsyncMock(return_value=_failed_panel_result())

    with patch("sdlc.engine.auto_brainstorm.dispatch_panel", panel):
        clar_id = await run_auto_brainstorm(
            tmp_path,
            context=ctx,
            runtime=AsyncMock(),
            registry=_registry(),
            journal_path=k["journal"],
            agent_runs_path=k["runs"],
            correlation_id="cid-1",
            auto_brainstorm=True,
        )

    clar_dir = tmp_path / ".claude" / "state" / "clarifications" / clar_id
    # Graceful halt: open_clarification.md exists so STOP fires + resume is idempotent...
    assert (clar_dir / "open_clarification.md").is_file()
    # ...but no options.md is written for a failed panel.
    assert not (clar_dir / "options.md").exists()
    # Failure is recorded in the journal, not raised.
    assert _panel_succeeded_flags(k["journal"]) == [False]


@pytest.mark.asyncio
async def test_panel_failure_is_idempotent_on_resume(tmp_path: Path) -> None:
    """After a failed panel halts, a resume must NOT re-dispatch the panel."""
    from sdlc.engine.auto_brainstorm import AmbiguityContext, run_auto_brainstorm

    k = _run_kwargs(tmp_path)
    ctx = AmbiguityContext(task_id=_TASK_ID, summary=_SUMMARY)
    panel = AsyncMock(return_value=_failed_panel_result())

    with patch("sdlc.engine.auto_brainstorm.dispatch_panel", panel):
        first = await run_auto_brainstorm(
            tmp_path,
            context=ctx,
            runtime=AsyncMock(),
            registry=_registry(),
            journal_path=k["journal"],
            agent_runs_path=k["runs"],
            correlation_id="cid-1",
            auto_brainstorm=True,
        )
        second = await run_auto_brainstorm(
            tmp_path,
            context=ctx,
            runtime=AsyncMock(),
            registry=_registry(),
            journal_path=k["journal"],
            agent_runs_path=k["runs"],
            correlation_id="cid-2",
            auto_brainstorm=True,
        )

    assert first == second
    assert panel.await_count == 1


# --- CR4.10-D2: options-contract enforced at the write path -----------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_body",
    [
        pytest.param("   \n\t\n  ", id="empty"),
        pytest.param(
            "# Clarification Options\n\n## Option 1: Only one\n"
            "### Pros\n- a\n### Cons\n- b\n### Risks\n- c\n",
            id="single-option",
        ),
        pytest.param(
            _options_md_body() + "\n## Recommendation\nWe recommend Option 1.\n",
            id="auto-pick",
        ),
    ],
)
async def test_contract_violating_output_is_rejected_no_options_written(
    tmp_path: Path, bad_body: str
) -> None:
    """Empty / <2-option / auto-pick synthesizer output must not be written to options.md."""
    from sdlc.engine.auto_brainstorm import AmbiguityContext, run_auto_brainstorm

    k = _run_kwargs(tmp_path)
    ctx = AmbiguityContext(task_id=_TASK_ID, summary=_SUMMARY)

    with patch(
        "sdlc.engine.auto_brainstorm.dispatch_panel",
        new_callable=AsyncMock,
        return_value=_panel_result(bad_body),
    ):
        clar_id = await run_auto_brainstorm(
            tmp_path,
            context=ctx,
            runtime=AsyncMock(),
            registry=_registry(),
            journal_path=k["journal"],
            agent_runs_path=k["runs"],
            correlation_id="cid-1",
            auto_brainstorm=True,
        )

    clar_dir = tmp_path / ".claude" / "state" / "clarifications" / clar_id
    assert (clar_dir / "open_clarification.md").is_file()
    assert not (clar_dir / "options.md").exists()
    assert _panel_succeeded_flags(k["journal"]) == [False]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("## Recommendation\nWe recommend Option 1.", True),
        ("We choose option 2 as the path forward.", True),
        ("Option 2 is the best choice for the team.", True),
        ("The selected option is the webhook design.", True),
        ("## Decision\nGo with option 1.", True),
        # benign: discusses tradeoffs, defers the choice to the human — NOT a pick
        ("Both options preserve member concerns; the human decides.", False),
        ("Pros include faster delivery; risks include scope creep.", False),
    ],
)
def test_parse_options_contract_pick_detection(text: str, expected: bool) -> None:
    from sdlc.engine.auto_brainstorm import parse_options_contract

    assert parse_options_contract(text).has_auto_pick is expected
