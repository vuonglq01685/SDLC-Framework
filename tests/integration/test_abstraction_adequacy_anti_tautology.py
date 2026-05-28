"""Anti-tautology receipt for abstraction-adequacy cross-runtime check (Story 2B.3 AC5)."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Final

import pytest

from integration._abstraction_adequacy_capture import pop_captured, record_runtime_bytes
from integration._abstraction_adequacy_helpers import (
    _SEED_CONTEXT,
    _SEED_PROMPT,
    _ZERO_HASH,
    _build_journal_entry,
    _format_diff,
    install_claude_stub_on_path,
    run_pre_write_hooks_for_dispatches,
)
from sdlc.journal import append_sync
from sdlc.runtime import AgentResult, ClaudeAIRuntime, MockAIRuntime
from sdlc.state import write_state_atomic_sync
from sdlc.state.projection import project_from_journal

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX-only: journal.append_sync + state.write_state_atomic_sync",
    ),
]

_TESTS_DIR: Final[Path] = Path(__file__).resolve().parent.parent
_SOURCE_FIXTURE: Final[Path] = (
    _TESTS_DIR / "fixtures" / "mock_responses" / "abstraction-adequacy.yaml"
)


async def _dispatch_twice(
    runtime: MockAIRuntime | ClaudeAIRuntime,
) -> tuple[AgentResult, AgentResult]:
    first = await runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT)
    second = await runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT)
    return first, second


def _run_pipeline_capture(
    tmp_path: Path,
    runtime: MockAIRuntime | ClaudeAIRuntime,
    factory_id: str,
) -> None:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal_path = state_dir / "journal.log"
    state_path = state_dir / "state.json"

    result_1, result_2 = asyncio.run(_dispatch_twice(runtime))
    hook_payloads = asyncio.run(
        run_pre_write_hooks_for_dispatches(
            repo_root=tmp_path,
            journal_path=journal_path,
            results=(result_1, result_2),
        )
    )
    append_sync(
        _build_journal_entry(
            seq=0,
            before_hash=None,
            after_hash=_ZERO_HASH,
            agent_result=result_1,
        ),
        journal_path=journal_path,
    )
    append_sync(
        _build_journal_entry(
            seq=1,
            before_hash=_ZERO_HASH,
            after_hash="sha256:1111111111111111111111111111111111111111111111111111111111111111",
            agent_result=result_2,
        ),
        journal_path=journal_path,
    )
    final_state = project_from_journal(journal_path)
    write_state_atomic_sync(final_state, target=state_path)

    actual_hp_bytes = (
        json.dumps(
            [hp.model_dump(mode="json") for hp in hook_payloads],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    record_runtime_bytes(factory_id, actual_hp_bytes, state_path.read_bytes())


def test_divergent_claude_stub_fails_cross_runtime_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5 receipt #1: mutated stub breaks mock-vs-claude byte identity with unified diff."""
    pop_captured()

    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    shutil.copy2(_SOURCE_FIXTURE, fixtures_dir / "abstraction-adequacy.yaml")

    mock_root = tmp_path / "mock-run"
    mock_root.mkdir()
    shutil.copytree(fixtures_dir, mock_root / "fixtures")
    _run_pipeline_capture(
        mock_root, MockAIRuntime(fixtures_dir=mock_root / "fixtures"), "mock_factory"
    )

    claude_root = tmp_path / "claude-run"
    claude_root.mkdir()
    shutil.copytree(fixtures_dir, claude_root / "fixtures")
    install_claude_stub_on_path(
        monkeypatch,
        claude_root / "fixtures" / "abstraction-adequacy.yaml",
        claude_root,
        mutate_output=True,
    )
    _run_pipeline_capture(claude_root, ClaudeAIRuntime(), "claude_factory")

    captured = pop_captured()
    mock_hp, mock_state = captured["mock_factory"]
    claude_hp, claude_state = captured["claude_factory"]

    # Hook payloads are built from fixture-stable targets — identical across runtimes.
    assert mock_hp == claude_hp

    with pytest.raises(AssertionError) as exc_info_state:
        assert mock_state == claude_state, _format_diff(
            "state.json (mock vs claude)", mock_state, claude_state
        )
    msg_state = str(exc_info_state.value)
    assert "state.json" in msg_state
    assert "--- expected" in msg_state or "+++ actual" in msg_state
