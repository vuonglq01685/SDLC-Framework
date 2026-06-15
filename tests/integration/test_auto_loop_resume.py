"""Crash-resume integration tests for auto-loop (Story 4.1, AC2)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import multiprocessing
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only"),
]

_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"


def _write_project(root: Path) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    (root / "01-Requirement" / "01-PRODUCT.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "01-Requirement" / "01-PRODUCT.md").write_text("# Product\n", encoding="utf-8")
    epics = root / "01-Requirement" / "04-Epics"
    epics.mkdir(parents=True, exist_ok=True)
    (epics / f"{_EPIC_ID}.json").write_text(json.dumps({"id": _EPIC_ID}), encoding="utf-8")
    stories = root / "01-Requirement" / "05-Stories" / _EPIC_ID
    stories.mkdir(parents=True, exist_ok=True)
    (stories / f"{_STORY_ID}.json").write_text(json.dumps({"id": _STORY_ID}), encoding="utf-8")
    (root / "02-Architecture" / "ARCHITECTURE.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "02-Architecture" / "ARCHITECTURE.md").write_text("# Arch\n", encoding="utf-8")
    tasks = root / "03-Implementation" / "tasks" / _STORY_ID
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "T01-first-task.json").write_text(
        json.dumps(
            {
                "id": _TASK_ID,
                "story_id": _STORY_ID,
                "label": "t",
                "stage": "pending",
                "dependencies": [],
                "review_verdict": None,
                "review_notes": None,
            }
        ),
        encoding="utf-8",
    )
    for phase, rel in ((1, "01-Requirement/01-PRODUCT.md"), (2, "02-Architecture/ARCHITECTURE.md")):
        artifact_path = root / rel
        artifact_hash = compute_artifact_hash(artifact_path, repo_root=root)
        write_record(
            SignoffRecord(
                phase=phase,
                artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
                approved_by="test",
                approved_at="2026-06-10T10:00:00.000Z",
                drafted_at="2026-06-10T09:00:00.000Z",
                validated_at="2026-06-10T10:00:00.000Z",
            ),
            repo_root=root,
        )
    state_dir = root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text("{}", encoding="utf-8")
    (state_dir / "journal.log").touch()
    runs = root / "03-Implementation" / "agent_runs.jsonl"
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.touch()
    (root / "fixtures").mkdir(exist_ok=True)


def _run_loop_child(root_str: str, kill_point: str) -> None:  # noqa: C901 - 5 kill-point branches
    import sys

    _project_root = str(Path(__file__).resolve().parents[2])
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from tests.chaos._kill_protocol import _pause_at

    root = Path(root_str)
    journal = (root / ".claude" / "state" / "journal.log").resolve()
    runs = (root / "03-Implementation" / "agent_runs.jsonl").resolve()
    state = (root / ".claude" / "state" / "state.json").resolve()
    from sdlc.engine.auto_loop import run_auto_loop
    from sdlc.engine.next_selector import resolve_next_action as rna
    from sdlc.engine.scanner import scan as do_scan
    from sdlc.runtime.mock import MockAIRuntime
    from sdlc.specialists.registry import SpecialistRegistry

    async def _dispatch(**_kwargs):
        if kill_point == "AFTER_DISPATCH_RETURNS":
            _pause_at(kill_point)

    patches = []
    if kill_point == "AFTER_SCAN":
        patches.append(
            patch(
                "sdlc.engine.auto_loop.scan",
                side_effect=lambda r: (_pause_at(kill_point), do_scan(r))[1],
            )
        )
    elif kill_point == "AFTER_NEXT_RESOLVED":
        patches.append(
            patch(
                "sdlc.engine.auto_loop.resolve_next_action",
                side_effect=lambda r: (_pause_at(kill_point), rna(r))[1],
            )
        )
    elif kill_point == "AFTER_JOURNAL_APPEND":
        from sdlc.engine import auto_loop as al

        orig = al._append_iteration

        async def _kill_append(*a, **k):
            await orig(*a, **k)
            _pause_at(kill_point)

        patches.append(patch.object(al, "_append_iteration", side_effect=_kill_append))
    elif kill_point == "AFTER_STATE_WRITE":
        from sdlc.engine import auto_loop as al

        orig = al._rebuild_state

        async def _kill_rebuild(jp, sp):
            await orig(jp, sp)
            _pause_at(kill_point)

        patches.append(patch.object(al, "_rebuild_state", side_effect=_kill_rebuild))

    for ptc in patches:
        ptc.start()
    try:
        asyncio.run(
            run_auto_loop(
                root,
                journal_path=journal,
                agent_runs_path=runs,
                runtime=MockAIRuntime(fixtures_dir=(root / "fixtures")),
                registry=SpecialistRegistry({}),
                dispatch_fn=_dispatch,
                state_path=state,
                max_iterations=1,
            )
        )
    finally:
        for ptc in reversed(patches):
            ptc.stop()


def _spawn_and_kill(kill_point: str, root: Path) -> None:
    ctx = multiprocessing.get_context("fork")
    proc = ctx.Process(target=_run_loop_child, args=(str(root), kill_point))
    proc.start()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            result = os.waitpid(proc.pid, os.WNOHANG | os.WUNTRACED)
            if result[0] != 0 and os.WIFSTOPPED(result[1]):
                break
        except ChildProcessError:
            break
        time.sleep(0.005)
    with contextlib.suppress(ProcessLookupError):
        os.kill(proc.pid, signal.SIGKILL)
    proc.join(timeout=5.0)


def _parse_and_assert_invariants(journal: Path) -> list:
    """Two-state invariant: every line parses fully (no partial entry) and monotonic_seq is
    strictly increasing with no duplicates. Returns the parsed entries in journal order."""
    from sdlc.journal import iter_entries

    entries = list(iter_entries(journal))  # raises JournalError on any partial/garbled line
    seqs = [e.monotonic_seq for e in entries]
    assert seqs == sorted(seqs), f"monotonic_seq not non-decreasing: {seqs}"
    assert len(seqs) == len(set(seqs)), f"duplicate monotonic_seq: {seqs}"
    return entries


def _iteration_seqs(entries: list) -> list[int]:
    return [
        e.payload["iteration_seq"]
        for e in entries
        if e.kind == "auto_loop_iteration" and isinstance(e.payload.get("iteration_seq"), int)
    ]


_KILL_POINTS = (
    "AFTER_SCAN",
    "AFTER_NEXT_RESOLVED",
    "AFTER_DISPATCH_RETURNS",
    "AFTER_JOURNAL_APPEND",
    "AFTER_STATE_WRITE",
)


@pytest.mark.asyncio
async def test_auto_loop_resume_kill_points(tmp_path: Path) -> None:
    from sdlc.engine.auto_loop import run_auto_loop
    from sdlc.runtime.mock import MockAIRuntime
    from sdlc.specialists.registry import SpecialistRegistry
    from sdlc.state.projection import project_from_journal

    for kill_point in _KILL_POINTS:
        root = tmp_path / kill_point
        root.mkdir(exist_ok=True)
        _write_project(root)
        journal = (root / ".claude" / "state" / "journal.log").resolve()
        _spawn_and_kill(kill_point, root)

        # Post-kill: the journal is never left with a partial entry (two-state invariant).
        killed = _parse_and_assert_invariants(journal)
        pre_count = len(killed)
        pre_max_iter = max(_iteration_seqs(killed), default=0)

        # Resume: re-running the loop continues from disk state.
        await run_auto_loop(
            root,
            journal_path=journal,
            agent_runs_path=(root / "03-Implementation" / "agent_runs.jsonl").resolve(),
            runtime=MockAIRuntime(fixtures_dir=(root / "fixtures")),
            registry=SpecialistRegistry({}),
            dispatch_fn=AsyncMock(),
            state_path=(root / ".claude" / "state" / "state.json").resolve(),
            max_iterations=1,
        )

        after = _parse_and_assert_invariants(journal)
        resumed_iters = _iteration_seqs(after[pre_count:])
        # Resume recorded at least one iteration and never reused a pre-crash iteration_seq —
        # the counter is re-seeded from disk, so "auto-loop-iter-N" cannot collide (P2 / AC2).
        assert resumed_iters, f"{kill_point}: resume recorded no auto_loop_iteration"
        assert all(s > pre_max_iter for s in resumed_iters), (
            f"{kill_point}: resumed iteration_seq {resumed_iters} did not advance "
            f"past pre-crash max {pre_max_iter} (resume-seed regression)"
        )
        # Replayed status settles to a valid value (never a stale/partial state).
        assert project_from_journal(journal).auto_loop_status in {"idle", "running", "halted"}
