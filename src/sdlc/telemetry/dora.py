"""DORA metrics computation engine — pure, subprocess-free (Story 5.13, E4).

Computes the four DORA metrics (`deployment_frequency`, `lead_time`,
`change_failure_rate`, `mttr`) for two windows (`7d`, `30d`) from
already-injected inputs: an `agent_runs.jsonl` path (read here via the
telemetry-owned reader seam, D2) and pre-read git commit tuples (injected by
the caller, D1 — git's subprocess grant lives in `cli/`, which neither
`telemetry` nor `dashboard` may import). This module invokes no subprocess
and imports no `cli.*`/`runtime.*`/`engine.*`/`dispatcher.*`.

Metric proxies (D3 — ratified per the story Dev Notes recommendation, over
`agent_runs.jsonl` + `git log`, documented in `docs/api/dora-schema.json`):
  deployment_frequency — count of merge commits per window (first-parent
    merge-to-main model). When the repo has ZERO merge commits anywhere in
    its history (solo-dev, no merge model), falls back to counting ALL
    commits per window.
  lead_time — median(commit_ts - author_ts) in hours, over commits (merge or
    not) in the window whose commit_ts >= author_ts - the per-commit
    author-to-land latency (author->land, NOT idea->production DORA lead time;
    near-zero outside rebase workflows). Commits with commit_ts < author_ts
    (clock skew / rebase / --date override) are excluded so a negative latency
    never skews the median (code-review P4, 2026-07-01).
  change_failure_rate — `failed` agent_runs divided by total agent_runs in window.
  mttr — mean(next `success`.ts - `failed`.ts) in hours, paired per
    `target_path`, over agent_runs in window.

`insufficient_data` threshold (D4): a window is insufficient iff
`span(earliest_event .. now) < window_days`, where `earliest_event` is the
oldest timestamp across the union of `agent_runs.ts` and git commit_ts. Additionally, if
`agent_runs` is entirely empty OR the git history is entirely empty, ALL
four metrics in ALL windows are `insufficient_data` (nothing to compute
from). Otherwise a metric is `insufficient_data` individually when its own
numerator/denominator subset is empty within an otherwise-sufficient window.

Boundary: `telemetry/` depends on `errors`, `contracts`, `journal`,
`concurrency`; forbidden from `engine`, `dispatcher`, `runtime`, `cli`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Final, TypeAlias

from sdlc.telemetry.runs import iter_agent_run_records

_logger = logging.getLogger(__name__)

_WINDOW_DAYS: Final[tuple[int, ...]] = (7, 30)
_SECONDS_PER_HOUR: Final[float] = 3600.0
# change_failure_rate denominator counts only genuine change outcomes; a run whose
# outcome is outside this set (corruption / future schema) must not dilute the rate
# (code-review P3, 2026-07-01).
_CHANGE_OUTCOMES: Final[frozenset[str]] = frozenset({"success", "failed"})

# (author_ts_iso, commit_ts_iso, is_merge) — injected by the cli-layer git
# reader (D1, `cli/_git_dora.py::git_dora_log`). Kept as a plain tuple (not a
# shared dataclass) so `cli/_git_dora.py` needs zero import from `telemetry/`
# — both sides declare an identical, independent type alias.
GitCommitTuple: TypeAlias = tuple[str, str, bool]


@dataclass(frozen=True, slots=True)
class _ParsedCommit:
    author_ts: datetime
    commit_ts: datetime
    is_merge: bool


@dataclass(frozen=True, slots=True)
class _ParsedRun:
    ts: datetime
    outcome: str
    target_path: str


def _window_key(days: int) -> str:
    return f"{days}d"


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp; tz-naive values are treated as UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_commits(git_commits: Sequence[GitCommitTuple]) -> list[_ParsedCommit]:
    parsed: list[_ParsedCommit] = []
    for author_iso, commit_iso, is_merge in git_commits:
        author_dt = _parse_iso(author_iso)
        commit_dt = _parse_iso(commit_iso)
        if author_dt is None or commit_dt is None:
            _logger.warning(
                "skipping git commit with unparsable timestamp: author=%r commit=%r",
                author_iso,
                commit_iso,
            )
            continue
        parsed.append(_ParsedCommit(author_ts=author_dt, commit_ts=commit_dt, is_merge=is_merge))
    return parsed


def _parse_runs(agent_runs: Sequence[Mapping[str, Any]]) -> list[_ParsedRun]:
    parsed: list[_ParsedRun] = []
    for record in agent_runs:
        ts_raw = record.get("ts")
        outcome = record.get("outcome")
        target_path = record.get("target_path")
        if (
            not isinstance(ts_raw, str)
            or not isinstance(outcome, str)
            or not isinstance(target_path, str)
        ):
            _logger.warning("skipping agent_run record missing ts/outcome/target_path: %r", record)
            continue
        ts = _parse_iso(ts_raw)
        if ts is None:
            _logger.warning("skipping agent_run record with unparsable ts: %r", ts_raw)
            continue
        parsed.append(_ParsedRun(ts=ts, outcome=outcome, target_path=target_path))
    return parsed


def _metric_ok(value: float | int, unit: str, **extra: Any) -> dict[str, Any]:
    return {"data_status": "ok", "value": value, "unit": unit, **extra}


def _metric_insufficient(unit: str, extra_keys: Sequence[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"data_status": "insufficient_data", "value": None, "unit": unit}
    for key in extra_keys:
        payload[key] = None
    return payload


def _deployment_frequency(
    commits: list[_ParsedCommit], *, now: datetime, window_days: int, use_merges_only: bool
) -> dict[str, Any]:
    since = now - timedelta(days=window_days)
    in_window = [
        c for c in commits if since <= c.commit_ts <= now and (not use_merges_only or c.is_merge)
    ]
    if not in_window:
        return _metric_insufficient("deploys_per_window", ("per_day",))
    count = len(in_window)
    return _metric_ok(count, "deploys_per_window", per_day=count / window_days)


def _lead_time(commits: list[_ParsedCommit], *, now: datetime, window_days: int) -> dict[str, Any]:
    since = now - timedelta(days=window_days)
    deltas = [
        (c.commit_ts - c.author_ts).total_seconds() / _SECONDS_PER_HOUR
        for c in commits
        if since <= c.commit_ts <= now and c.commit_ts >= c.author_ts
    ]
    if not deltas:
        return _metric_insufficient("hours", ())
    return _metric_ok(median(deltas), "hours")


def _change_failure_rate(
    runs: list[_ParsedRun], *, now: datetime, window_days: int
) -> dict[str, Any]:
    since = now - timedelta(days=window_days)
    in_window = [r for r in runs if since <= r.ts <= now and r.outcome in _CHANGE_OUTCOMES]
    total = len(in_window)
    if total == 0:
        return _metric_insufficient("ratio", ("failed_count", "total_count"))
    failed = sum(1 for r in in_window if r.outcome == "failed")
    return _metric_ok(failed / total, "ratio", failed_count=failed, total_count=total)


def _mttr(runs: list[_ParsedRun], *, now: datetime, window_days: int) -> dict[str, Any]:
    since = now - timedelta(days=window_days)
    in_window = sorted((r for r in runs if since <= r.ts <= now), key=lambda r: r.ts)
    by_target: dict[str, list[_ParsedRun]] = {}
    for r in in_window:
        by_target.setdefault(r.target_path, []).append(r)
    gaps: list[float] = []
    for target_runs in by_target.values():
        pending_failure: datetime | None = None
        for r in target_runs:
            if r.outcome == "failed":
                pending_failure = r.ts
            elif r.outcome == "success" and pending_failure is not None:
                gaps.append((r.ts - pending_failure).total_seconds() / _SECONDS_PER_HOUR)
                pending_failure = None
    if not gaps:
        return _metric_insufficient("hours", ("recovery_count",))
    return _metric_ok(sum(gaps) / len(gaps), "hours", recovery_count=len(gaps))


def _all_insufficient_window() -> dict[str, Any]:
    return {
        "deployment_frequency": _metric_insufficient("deploys_per_window", ("per_day",)),
        "lead_time": _metric_insufficient("hours", ()),
        "change_failure_rate": _metric_insufficient("ratio", ("failed_count", "total_count")),
        "mttr": _metric_insufficient("hours", ("recovery_count",)),
    }


def compute_dora_window(
    *,
    agent_runs_path: Path,
    git_commits: Sequence[GitCommitTuple],
    now: datetime,
) -> dict[str, Any]:
    """Compute the 4-metric x {7d, 30d} DORA envelope (AC1, AC4).

    ``agent_runs_path`` is read here via the telemetry-owned reader seam
    (D2); ``git_commits`` are pre-read/injected by the caller (D1 — the git
    subprocess lives in ``cli/``). ``now`` is injectable for deterministic
    tests (mirrors ``parse_git_log(stdout, now)``).
    """
    try:
        raw_runs = list(iter_agent_run_records(agent_runs_path))
    except OSError as exc:
        # `iter_agent_run_records` already treats "missing file" as empty;
        # any other OSError (permission denied, I/O error, ...) must not
        # crash the `/api/dora` request handler — degrade to empty runs
        # (review-B focus, security-reviewer touch: never 500 on unreadable
        # untrusted input).
        _logger.warning("agent_runs.jsonl unreadable at %s: %s", agent_runs_path, exc)
        raw_runs = []
    runs = _parse_runs(raw_runs)
    commits = _parse_commits(git_commits)

    if not runs or not commits:
        return {
            "schema_version": 1,
            "windows": {_window_key(d): _all_insufficient_window() for d in _WINDOW_DAYS},
        }

    earliest = min([c.commit_ts for c in commits] + [r.ts for r in runs])
    use_merges_only = any(c.is_merge for c in commits)

    windows: dict[str, Any] = {}
    for window_days in _WINDOW_DAYS:
        if now - earliest < timedelta(days=window_days):
            windows[_window_key(window_days)] = _all_insufficient_window()
            continue
        windows[_window_key(window_days)] = {
            "deployment_frequency": _deployment_frequency(
                commits, now=now, window_days=window_days, use_merges_only=use_merges_only
            ),
            "lead_time": _lead_time(commits, now=now, window_days=window_days),
            "change_failure_rate": _change_failure_rate(runs, now=now, window_days=window_days),
            "mttr": _mttr(runs, now=now, window_days=window_days),
        }

    return {"schema_version": 1, "windows": windows}


__all__: tuple[str, ...] = ("GitCommitTuple", "compute_dora_window")
