"""Integration tests — auto-brainstorm panel on ambiguity (Story 4.10)."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
import yaml

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.engine.auto_loop import run_auto_loop
from sdlc.journal import iter_entries
from sdlc.runtime.mock import MockAIRuntime, compute_prompt_hash
from sdlc.specialists import load_registry
from sdlc.state.projection import project_from_journal

pytestmark = pytest.mark.integration

_REPO_AGENTS = Path(__file__).resolve().parents[2] / "src" / "sdlc" / "agents"
_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"
_SUMMARY = "Should we support webhooks or polling for integrations?"


def _options_md_body() -> str:
    return """# Clarification Options

## Option 1: Webhooks
### Pros
- Real-time updates
### Cons
- Requires public endpoint
### Risks
- Delivery retries complexity
### Concerns preserved
- product-strategist: faster user feedback loops
- technical-researcher: standard for SaaS integrations
- devil-advocate: infra exposure surface

## Option 2: Polling
### Pros
- Simpler deployment
### Cons
- Higher latency
### Risks
- Rate-limit pressure
### Concerns preserved
- product-strategist: lower operational burden initially
- technical-researcher: easier behind corporate firewalls
- devil-advocate: stale data during outages
"""


def _write_approved_signoffs(tmp_path: Path) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    for phase, rel in (
        (1, "01-Requirement/01-PRODUCT.md"),
        (2, "02-Architecture/ARCHITECTURE.md"),
    ):
        artifact_path = tmp_path / rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
        artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
        write_record(
            SignoffRecord(
                phase=phase,
                artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
                approved_by="test",
                approved_at="2026-06-10T10:00:00.000Z",
                drafted_at="2026-06-10T09:00:00.000Z",
                validated_at="2026-06-10T10:00:00.000Z",
            ),
            repo_root=tmp_path,
        )


def _write_phase3_ready_project(tmp_path: Path, *, stage: str = "pending") -> None:
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").write_text("# Product\n", encoding="utf-8")
    epics = tmp_path / "01-Requirement" / "04-Epics"
    epics.mkdir(parents=True, exist_ok=True)
    (epics / f"{_EPIC_ID}.json").write_text(json.dumps({"id": _EPIC_ID}), encoding="utf-8")
    stories = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID
    stories.mkdir(parents=True, exist_ok=True)
    (stories / f"{_STORY_ID}.json").write_text(json.dumps({"id": _STORY_ID}), encoding="utf-8")
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").write_text("# Arch\n", encoding="utf-8")
    tasks = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "T01-first-task.json").write_text(
        json.dumps(
            {
                "id": _TASK_ID,
                "story_id": _STORY_ID,
                "label": "t",
                "stage": stage,
                "dependencies": [],
                "review_verdict": None,
                "review_notes": None,
            }
        ),
        encoding="utf-8",
    )
    _write_approved_signoffs(tmp_path)


def _bootstrap_journal(tmp_path: Path) -> tuple[Path, Path, Path]:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal = (state_dir / "journal.log").resolve()
    journal.touch()
    state = (state_dir / "state.json").resolve()
    state.write_text("{}", encoding="utf-8")
    runs = (tmp_path / "03-Implementation" / "agent_runs.jsonl").resolve()
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.touch()
    return journal, runs, state


def _write_ambiguity_signal(repo_root: Path, *, task_id: str, summary: str) -> None:
    signals = repo_root / ".claude" / "state" / "ambiguity_signals"
    signals.mkdir(parents=True, exist_ok=True)
    (signals / f"{task_id}.json").write_text(
        json.dumps({"summary": summary}),
        encoding="utf-8",
    )


def _brainstorm_spec(clar_rel: str) -> WorkflowSpec:
    options_rel = clar_rel
    return WorkflowSpec(
        schema_version=1,
        name="auto-brainstorm",
        slash_command="sdlc-auto",
        primary_agent="product-strategist",
        parallel_agents=("technical-researcher", "devil-advocate"),
        synthesizer_agent="requirement-synthesizer",
        write_globs=MappingProxyType(
            {
                "product-strategist": (options_rel,),
                "technical-researcher": (options_rel,),
                "devil-advocate": (options_rel,),
                "requirement-synthesizer": (options_rel,),
            }
        ),
    )


def _materialize_brainstorm_fixtures(
    fixtures_dir: Path,
    *,
    summary: str,
    options_body: str,
) -> None:
    from sdlc.engine.auto_brainstorm import clarification_prompt_builder

    registry = load_registry(_REPO_AGENTS)
    spec = _brainstorm_spec(".claude/state/clarifications/placeholder/options.md")
    records: dict[str, dict[str, object]] = {}

    def _add(name: str, role: str, output_text: str, upstream: tuple[str, ...] = ()) -> None:
        specialist = registry.get(name)
        prompt = clarification_prompt_builder(
            specialist,
            spec,
            idea_text=summary,
            role=role,  # type: ignore[arg-type]
            upstream_outputs=upstream,
        )
        h = compute_prompt_hash(prompt)
        records[h] = {
            "output_text": output_text,
            "tokens_in": 1,
            "tokens_out": 1,
            "tool_calls": [],
        }

    _add("product-strategist", "primary", "## Strategist\n\nPrimary draft.\n")
    _add("technical-researcher", "parallel", "## Research\n\nParallel notes.\n")
    _add("devil-advocate", "parallel", "## Risks\n\nParallel concerns.\n")
    upstream = (
        "## Strategist\n\nPrimary draft.\n",
        "## Research\n\nParallel notes.\n",
        "## Risks\n\nParallel concerns.\n",
    )
    _add("requirement-synthesizer", "synthesizer", options_body, upstream)
    (fixtures_dir / f"{spec.name}.yaml").write_text(
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def _mock_runtime(tmp_path: Path, *, summary: str, options_body: str) -> MockAIRuntime:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    _materialize_brainstorm_fixtures(fixtures, summary=summary, options_body=options_body)
    return MockAIRuntime(fixtures_dir=fixtures)


async def _dispatch_with_ambiguity_signal(**kwargs) -> None:
    repo_root = kwargs["repo_root"]
    task_id = kwargs["task_id"]
    _write_ambiguity_signal(repo_root, task_id=task_id, summary=_SUMMARY)


@pytest.mark.asyncio
async def test_positive_ambiguity_dispatches_panel_and_halts(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    registry = load_registry(_REPO_AGENTS)
    options_body = _options_md_body()
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path, summary=_SUMMARY, options_body=options_body),
        registry=registry,
        dispatch_fn=_dispatch_with_ambiguity_signal,
        state_path=state_path,
        max_iterations=1,
        auto_brainstorm=True,
    )
    assert result.halted is True
    assert result.stop_reason == "open_clarification"
    clar_root = tmp_path / ".claude" / "state" / "clarifications"
    clar_dirs = [p for p in clar_root.iterdir() if p.is_dir()]
    assert len(clar_dirs) == 1
    clar_dir = clar_dirs[0]
    assert (clar_dir / "open_clarification.md").is_file()
    options_text = (clar_dir / "options.md").read_text(encoding="utf-8")
    from sdlc.engine.auto_brainstorm import parse_options_contract

    contract = parse_options_contract(options_text)
    assert contract.option_count >= 2
    assert contract.has_tradeoffs
    assert contract.preserves_member_concerns
    assert not contract.has_auto_pick
    entries = list(iter_entries(journal))
    assert sum(1 for e in entries if e.kind == "agent_dispatched") == 4
    assert any(e.kind == "auto_brainstorm_dispatched" for e in entries)
    stop_entries = [e for e in entries if e.kind == "stop_triggered"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["trigger"] == "open_clarification"
    projected = project_from_journal(journal)
    assert projected.auto_loop_status == "halted"
    assert projected.stop_reason == "open_clarification"


@pytest.mark.asyncio
async def test_bypass_skips_panel_but_still_halts(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    registry = load_registry(_REPO_AGENTS)
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path, summary=_SUMMARY, options_body=_options_md_body()),
        registry=registry,
        dispatch_fn=_dispatch_with_ambiguity_signal,
        state_path=state_path,
        max_iterations=1,
        auto_brainstorm=False,
    )
    assert result.halted is True
    assert result.stop_reason == "open_clarification"
    clar_root = tmp_path / ".claude" / "state" / "clarifications"
    clar_dir = next(p for p in clar_root.iterdir() if p.is_dir())
    assert (clar_dir / "open_clarification.md").is_file()
    assert not (clar_dir / "options.md").exists()
    assert not any(e.kind == "agent_dispatched" for e in iter_entries(journal))


@pytest.mark.asyncio
async def test_no_ambiguity_never_brainstorms(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path, summary=_SUMMARY, options_body=_options_md_body()),
        registry=load_registry(_REPO_AGENTS),
        dispatch_fn=dispatch,
        state_path=state_path,
        max_iterations=1,
        auto_brainstorm=True,
    )
    assert result.halted is False
    assert not (tmp_path / ".claude" / "state" / "clarifications").exists()
    assert not any(e.kind == "auto_brainstorm_dispatched" for e in iter_entries(journal))
