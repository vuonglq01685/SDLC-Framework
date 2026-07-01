"""Performance benchmark for `compute_dora_window` — NFR-PERF-5 CI gate (Story 5.13).

Budget: cold compute < 30 s on a synthetic fixture project (200 "stories" ~
git commits, 1000 "tasks" ~ agent_runs, 90 days of history) — the 30 s
server-side cache (Story 5.1 `_DoraCache`) bounds *repeat* cost, but the
*cold* compute itself must stay under the NFR-PERF-5 budget (DAG §7 risk
row). Mirrors the `<100ms` `/state.json` gate pattern (Story 5.1 Task 10).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from sdlc.telemetry.dora import GitCommitTuple, compute_dora_window

pytestmark = [pytest.mark.benchmark]

_NUM_COMMITS = 200  # "200 stories"
_NUM_AGENT_RUNS = 1000  # "1000 tasks"
_HISTORY_DAYS = 90
_BUDGET_SECONDS = 30.0


def _build_dora_fixture(root: Path, *, now: datetime) -> tuple[Path, list[GitCommitTuple]]:
    """Write a synthetic agent_runs.jsonl (1000 records) + build 200 commit tuples
    spread evenly across 90 days, mirroring a real long-lived project (Task 8)."""
    runs_path = root / "agent_runs.jsonl"
    outcomes = ("success", "success", "success", "failed")  # 25% failure rate
    with runs_path.open("w", encoding="utf-8") as fh:
        for i in range(_NUM_AGENT_RUNS):
            days_ago = _HISTORY_DAYS * i / _NUM_AGENT_RUNS
            ts = (now - timedelta(days=days_ago)).isoformat()
            record: dict[str, Any] = {
                "schema_version": 1,
                "ts": ts,
                "outcome": outcomes[i % len(outcomes)],
                "target_path": f"03-Implementation/tasks/T{i % 200:04d}.md",
                "run_id": f"{i:08x}-0000-0000-0000-000000000000",
                "workflow_step": "task-tdd",
                "specialist_name": "backend-swe",
                "target_kind": "primary",
                "attempts": 1,
                "tokens_in": 100,
                "tokens_out": 200,
                "duration_ms": 1000,
            }
            fh.write(json.dumps(record) + "\n")

    commits: list[GitCommitTuple] = []
    for i in range(_NUM_COMMITS):
        days_ago = _HISTORY_DAYS * i / _NUM_COMMITS
        commit_dt = now - timedelta(days=days_ago)
        author_dt = commit_dt - timedelta(hours=3)
        is_merge = i % 5 == 0  # a mix of merge + non-merge commits
        commits.append((author_dt.isoformat(), commit_dt.isoformat(), is_merge))

    return runs_path, commits


def test_compute_dora_window_perf_cold(benchmark: BenchmarkFixture, tmp_path: Path) -> None:
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)
    runs_path, commits = _build_dora_fixture(tmp_path, now=now)

    # One true cold sample per CI run: rounds=1, iterations=1, no warmup — mirrors
    # test_scan_perf_cold's rationale (Story 1.15).
    benchmark.pedantic(  # type: ignore[no-untyped-call]
        compute_dora_window,
        kwargs={"agent_runs_path": runs_path, "git_commits": commits, "now": now},
        iterations=1,
        rounds=1,
        warmup_rounds=0,
    )
    mean = benchmark.stats.stats.mean  # type: ignore[union-attr]
    assert mean < _BUDGET_SECONDS, (
        f"compute_dora_window() ran in {mean:.3f}s on a {_NUM_COMMITS}-commit/"
        f"{_NUM_AGENT_RUNS}-run/{_HISTORY_DAYS}-day fixture; budget is "
        f"{_BUDGET_SECONDS}s (NFR-PERF-5)"
    )
