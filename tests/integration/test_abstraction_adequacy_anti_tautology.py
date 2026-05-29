"""Anti-tautology receipt for abstraction-adequacy cross-runtime check (Story 2B.3 AC5).

Receipt #1 (stub-divergence): a deliberately-mutated ``claude`` stub MUST make the REAL wired
cross-run surface go RED. We invoke ``test_abstraction_adequacy.test_cross_runtime_byte_identity``
directly (review P36 / D7) — NOT a reimplemented copy of its assertion — after populating the
capture registry with one normal mock run and one byte-divergent claude run. This proves the
production gate surface is load-bearing, not just that an in-line ``==`` can fail.

The capture registry (``_abstraction_adequacy_capture._CAPTURED``) is a process-global shared
with the main conformance flow, whose ``test_cross_runtime_byte_identity`` is ordered LAST across
the whole integration suite (conftest.py). So this receipt SAVES and RESTORES whatever the main
flow has already captured (review P27) — a naive clear would wipe the main captures and make the
real gate fail with "missing captures".

The real surface is reached via the module object (``_aa_module``), NOT a ``from ... import
test_cross_runtime_byte_identity`` — importing the name would make pytest collect a second,
capture-less copy in THIS module that would fail.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Final

import pytest

from integration import test_abstraction_adequacy as _aa_module
from integration._abstraction_adequacy_capture import pop_captured, record_runtime_bytes
from integration._abstraction_adequacy_helpers import (
    _ZERO_HASH,
    _build_journal_entry,
    dispatch_twice,
    install_claude_stub_on_path,
    run_pre_write_hooks_for_dispatches,
)
from sdlc.journal import append_sync
from sdlc.runtime import ClaudeAIRuntime, MockAIRuntime
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


def _run_pipeline_capture(
    repo_root: Path,
    runtime: MockAIRuntime | ClaudeAIRuntime,
    factory_id: str,
) -> None:
    """Run the conformance pipeline once and register its bytes under ``factory_id``."""
    state_dir = repo_root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal_path = state_dir / "journal.log"
    state_path = state_dir / "state.json"

    result_1, result_2 = asyncio.run(dispatch_twice(runtime))
    hook_payloads = asyncio.run(
        run_pre_write_hooks_for_dispatches(
            repo_root=repo_root,
            journal_path=journal_path,
            results=(result_1, result_2),
        )
    )
    append_sync(
        _build_journal_entry(seq=0, before_hash=None, after_hash=_ZERO_HASH, agent_result=result_1),
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


def test_divergent_claude_stub_makes_real_cross_run_surface_red(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """AC5 receipt #1: a one-byte-mutated claude stub makes the REAL gate RED with a diff.

    Invokes ``test_abstraction_adequacy.test_cross_runtime_byte_identity`` (the production
    cross-run surface) and asserts it raises ``AssertionError`` whose message both names
    ``state.json`` and SHOWS the mutated byte on a ``+`` diff line — proving the diff is the
    actual differing content, not a bare "<bytes differ>" summary (review P8).
    """
    # SAVE any captures the main conformance flow has already registered, then clear, so this
    # receipt's divergent pair cannot collide (P26 dup-guard) or leak into the main gate (P27).
    preserved = pop_captured()
    try:
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

        # The real surface pops the registry and asserts cross-runtime byte identity. The
        # mutated output_text diverges state.json (hook payloads stay identical), so the
        # state assertion fires.
        with pytest.raises(AssertionError) as exc_info:
            _aa_module.test_cross_runtime_byte_identity(request)

        message = str(exc_info.value)
        assert "state.json" in message, message
        # The mutated byte must appear on an added ('+') unified-diff line — proves the diff is
        # the actual differing content, not a bare "<bytes differ>" summary (review P8). lstrip
        # because pytest indents assertion-message continuation lines.
        assert any(
            line.lstrip().startswith("+") and "X" in line for line in message.splitlines()
        ), f"diff did not surface the mutated byte on a '+' line:\n{message}"
    finally:
        # The real surface already popped our divergent pair; clear any residue defensively
        # then restore the main flow's captures so its last-ordered gate still sees them.
        pop_captured()
        for factory_id, (hook_payload_bytes, state_bytes) in preserved.items():
            record_runtime_bytes(factory_id, hook_payload_bytes, state_bytes)
