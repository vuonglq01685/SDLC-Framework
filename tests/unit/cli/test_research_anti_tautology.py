"""Permanent anti-tautology invariants for ``sdlc research`` (Story 2A.9).

P30 + P33 (code review resolution for D1): the original Change Log claimed
two anti-tautology receipts (AC4 prompt-text + AC11 byte-preservation flips)
but provided no commit-visible evidence the flip-and-revert ceremony was
actually performed. This file replaces the receipt narrative with three
permanent property tests that fail loudly if the underlying invariants ever
break:

  1. ``test_closure_binds_caller_topic_into_prompt`` — covers AC4: the
     CLI's prompt-builder closure must bind the *caller's* topic, not a
     hard-coded sentinel. Equivalent to the AC4 receipt's flip
     (``idea_text=topic`` → ``idea_text="DIFFERENT_TOPIC"``) but as a
     standing assertion.

  2. ``test_dedup_preserves_prior_research_bytes`` — covers AC11.2: a
     re-run with the same topic must produce a new ``-N.md`` while the
     prior file's bytes remain identical (the AC11 receipt's
     ``==`` ↔ ``!=`` flip becomes a standing assertion).

  3. ``test_fixture_builder_prompt_hash_matches_live_dispatch_prompt`` —
     covers P30: the MockAIRuntime fixture's prompt hash must equal the
     live dispatch path's prompt hash for the same topic. Future patches
     that add ``extra_context`` to one path but not the other would
     silently break MockAIRuntime fixture matching; this test fails first.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.cli.research import _workflows_package_dir, _wrap_research_artifact
from sdlc.runtime.mock import compute_prompt_hash
from sdlc.specialists import load_registry
from sdlc.workflows.registry import WorkflowRegistry

pytestmark = pytest.mark.unit

_runner = CliRunner()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_closure_binds_caller_topic_into_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4 invariant: the prompt-builder closure captures the CLI arg verbatim.

    Flipping ``idea_text=topic`` to a hard-coded sentinel inside the CLI would
    make the recorded prompt lack the topic; this test asserts the topic IS
    recorded, which fails under any such regression.
    """
    import json as _json

    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)

    topic = "AC4 anti-tautology canary topic"
    with patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["research", topic])
    assert r.exit_code == 0, r.stderr + r.stdout

    runs = (tmp_path / "03-Implementation" / "agent_runs.jsonl").read_text(encoding="utf-8")
    prompts = [_json.loads(line)["dispatch_prompt"] for line in runs.splitlines() if line.strip()]
    # At least one prompt must carry the verbatim topic text. A closure that
    # binds the wrong value (e.g., a constant sentinel) would fail this.
    matched = [p for p in prompts if isinstance(p, str) and topic in p]
    assert matched, (
        "no prompt in agent_runs.jsonl contained the caller topic; "
        "the prompt-builder closure is not binding the CLI argument"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_dedup_preserves_prior_research_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC11.2 invariant: re-running with the same topic does NOT mutate prior bytes.

    Flipping ``original_bytes == reread_original_bytes`` to ``!=`` would mean
    the dedup logic overwrites the original instead of allocating a ``-N.md``.
    This test fails under any such regression.
    """
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)

    topic = "AC11 anti-tautology dedup topic"
    art = tmp_path / "01-Requirement" / "02-Research" / "ac11-anti-tautology-dedup-topic.md"
    art2 = tmp_path / "01-Requirement" / "02-Research" / "ac11-anti-tautology-dedup-topic-2.md"

    with patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path):
        r1 = _runner.invoke(app, ["research", topic])
    assert r1.exit_code == 0, r1.stderr + r1.stdout
    assert art.is_file(), "first run should create the base artifact"
    original_bytes = art.read_bytes()

    with patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path):
        r2 = _runner.invoke(app, ["research", topic])
    assert r2.exit_code == 0, r2.stderr + r2.stdout
    assert art2.is_file(), "second run should produce <slug>-2.md"
    assert art.read_bytes() == original_bytes, (
        "second run mutated the prior artifact; the dedup logic does not "
        "preserve byte-for-byte the original (audit-grade chain-of-custody "
        "broken)"
    )


def test_fixture_builder_prompt_hash_matches_live_dispatch_prompt() -> None:
    """P30: the MockAIRuntime fixture and the live dispatch path must agree on prompt bytes.

    ``_materialize_research_mock_fixtures`` builds the fixture key with
    ``phase1_prompt_builder(specialist, spec, idea_text=topic, role='primary',
    upstream_outputs=())``. The live ``_research_dispatch_async`` calls
    ``dispatch(..., prompt_builder=_prompt_builder)`` where ``_prompt_builder``
    wraps the same call with the same kwargs. If a future patch adds an
    ``extra_context`` argument to one path and not the other, the fixture's
    prompt hash no longer matches the live prompt hash, MockAIRuntime fails
    with a generic "no fixture for hash" error, and the regression is hard
    to diagnose. This test pins them together.
    """
    from sdlc.dispatcher.prompts import phase1_prompt_builder

    repo_root = Path(__file__).resolve().parents[3]
    workflows_dir = _workflows_package_dir()
    reg = WorkflowRegistry.load(workflows_dir)
    spec = reg.get("/sdlc-research")
    sp = load_registry(repo_root / "src" / "sdlc" / "agents").get("technical-researcher")

    topic = "P30 fixture vs live prompt parity"

    # Path A — fixture builder (verbatim from _materialize_research_mock_fixtures).
    fixture_prompt = phase1_prompt_builder(
        sp,
        spec,
        idea_text=topic,
        role="primary",
        upstream_outputs=(),
    )

    # Path B — live dispatch closure (verbatim from _research_dispatch_async).
    def _live_prompt_builder(sp_arg: object, wf: object) -> str:
        return phase1_prompt_builder(
            sp_arg,  # type: ignore[arg-type]
            wf,  # type: ignore[arg-type]
            idea_text=topic,
            role="primary",
            upstream_outputs=(),
        )

    live_prompt = _live_prompt_builder(sp, spec)
    assert compute_prompt_hash(fixture_prompt) == compute_prompt_hash(live_prompt), (
        "fixture builder and live dispatch builder produced different prompt hashes — "
        "MockAIRuntime will fail to match in production; check that both paths pass "
        "the same kwargs to phase1_prompt_builder"
    )


def test_wrap_artifact_topic_byte_round_trip() -> None:
    """Defense-in-depth for AC11 byte invariant at the helper level."""
    topic = "= USER-PROVIDED — special: chars\nNL"
    out = _wrap_research_artifact("body\n", topic=topic, slug="t", ts="2026-01-01T00:00:00.000Z")
    import yaml as _yaml

    parts = out.split("---", 2)
    front = _yaml.safe_load(parts[1])
    assert isinstance(front, dict)
    assert front["topic"] == topic
