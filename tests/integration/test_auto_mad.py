"""Integration tests — mad-mode auto-resolution (Story 4.11).

Shared project-seed + dispatch fixtures live in ``tests/_auto_mad_helpers.py``
(400-LOC cap split; CR4.11-W2 dedup).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from _auto_mad_helpers import (
    _CLAR_ID,
    _bootstrap_journal,
    _force_dispatch_decision,
    _make_retry_dispatch_fn,
    _mock_runtime,
    _seed_open_clarification,
    _write_phase1_approved_phase2_unsigned_project,
    _write_phase3_ready_project,
)
from sdlc.engine.auto_loop import run_auto_loop
from sdlc.errors import DispatchError
from sdlc.journal import iter_entries
from sdlc.signoff import read_record
from sdlc.specialists.registry import SpecialistRegistry

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_mad_mode_auto_signs_unsigned_phase_and_continues(tmp_path: Path) -> None:
    _write_phase1_approved_phase2_unsigned_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=_force_dispatch_decision(),
    ):
        result = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=dispatch,
            state_path=state_path,
            max_iterations=1,
            mad_mode=True,
        )
    assert result.halted is False
    record = read_record(phase=2, repo_root=tmp_path)
    assert record.approved_by == "ai-mad-mode"
    kinds = [e.kind for e in iter_entries(journal)]
    assert "signoff_recorded" in kinds
    assert "auto_mad_resolve" in kinds
    assert "stop_triggered" not in kinds


@pytest.mark.asyncio
async def test_mad_mode_auto_resolves_clarification_and_continues(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    open_path = _seed_open_clarification(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=_force_dispatch_decision(),
    ):
        result = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=dispatch,
            state_path=state_path,
            max_iterations=1,
            auto_brainstorm=False,
            mad_mode=True,
        )
    assert result.halted is False
    clar_dir = open_path.parent
    assert not open_path.exists()
    assert (clar_dir / "resolution.md").is_file()
    mad_entries = [e for e in iter_entries(journal) if e.kind == "auto_mad_resolve"]
    assert len(mad_entries) == 1
    assert _CLAR_ID in str(mad_entries[0].payload["target"])
    assert "stop_triggered" not in [e.kind for e in iter_entries(journal)]


@pytest.mark.asyncio
async def test_mad_mode_synth_pick_when_options_missing(tmp_path: Path) -> None:
    from sdlc.engine.auto_mad import _SYNTH_PICK_SENTINEL

    _write_phase3_ready_project(tmp_path)
    _seed_open_clarification(tmp_path, with_options=False)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=_force_dispatch_decision(),
    ):
        await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=AsyncMock(return_value=None),
            state_path=state_path,
            max_iterations=1,
            auto_brainstorm=False,
            mad_mode=True,
        )
    mad = next(e for e in iter_entries(journal) if e.kind == "auto_mad_resolve")
    assert mad.payload["decision"] == _SYNTH_PICK_SENTINEL


@pytest.mark.asyncio
async def test_mad_mode_still_halts_on_agent_failed(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_make_retry_dispatch_fn(DispatchError("runtime unavailable")),
        state_path=state_path,
        max_iterations=1,
        mad_mode=True,
    )
    assert result.halted is True
    assert result.stop_reason == "agent_failed"
    assert "auto_mad_resolve" not in [e.kind for e in iter_entries(journal)]


@pytest.mark.asyncio
async def test_mad_mode_watchdog_reason_carries_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    times = iter([0.0, 200.0])
    monkeypatch.setattr("sdlc.engine.auto_loop.time.monotonic", lambda: next(times, 200.0))
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=AsyncMock(return_value=None),
        state_path=state_path,
        max_iterations=1,
        watchdog_timeout_minutes=1.0,
        mad_mode=True,
    )
    assert result.halted is True
    assert result.stop_reason == "watchdog_timeout"
    stop = next(e for e in iter_entries(journal) if e.kind == "stop_triggered")
    assert "(mad-mode)" in str(stop.payload.get("reason", ""))


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only signoff path in v1")
async def test_mad_mode_resume_does_not_re_sign_or_re_resolve(tmp_path: Path) -> None:
    _write_phase1_approved_phase2_unsigned_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=_force_dispatch_decision(),
    ):
        first = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=dispatch,
            state_path=state_path,
            max_iterations=1,
            mad_mode=True,
        )
    assert first.halted is False
    mad_count_after_first = sum(1 for e in iter_entries(journal) if e.kind == "auto_mad_resolve")
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=_force_dispatch_decision(),
    ):
        second = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=dispatch,
            state_path=state_path,
            max_iterations=1,
            mad_mode=True,
        )
    assert second.halted is False
    mad_count_after_second = sum(1 for e in iter_entries(journal) if e.kind == "auto_mad_resolve")
    assert mad_count_after_second == mad_count_after_first
    record = read_record(phase=2, repo_root=tmp_path)
    assert record.approved_by == "ai-mad-mode"
