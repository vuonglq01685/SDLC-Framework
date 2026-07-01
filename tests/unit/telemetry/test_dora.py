"""Unit tests for the DORA compute engine (Story 5.13, Tasks 1/5).

``compute_dora_window`` is pure given an injectable ``now`` clock and
pre-read ``git_commits``; it reads ``agent_runs_path`` itself via the
telemetry-owned reader seam (D2), so tests write a real JSONL fixture file
under ``tmp_path`` rather than mocking the reader.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from sdlc.telemetry.dora import GitCommitTuple, compute_dora_window

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _write_runs(tmp_path: Path, records: Sequence[Mapping[str, Any]]) -> Path:
    path = tmp_path / "agent_runs.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")
    return path


def _run(
    *, ts: str, outcome: str, target_path: str = "01-Requirement/01-PRODUCT.md"
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ts": ts,
        "outcome": outcome,
        "target_path": target_path,
        "run_id": "11111111-1111-1111-1111-111111111111",
        "workflow_step": "requirements",
        "specialist_name": "product-strategist",
        "target_kind": "primary",
        "attempts": 1,
        "tokens_in": 1,
        "tokens_out": 1,
        "duration_ms": 1,
    }


def _commit(author_iso: str, commit_iso: str, *, is_merge: bool = False) -> GitCommitTuple:
    return (author_iso, commit_iso, is_merge)


# An anchor run far outside every window (>30d before _NOW) so span-threshold tests
# (TestSpanThreshold) don't accidentally make these metric-math-focused fixtures
# globally insufficient; it never enters any window's filtered subset itself.
_ANCHOR_RUN = _run(ts="2026-05-01T00:00:00+00:00", outcome="success")


class TestGloballyInsufficient:
    def test_missing_agent_runs_file_and_no_commits_is_insufficient_everywhere(
        self, tmp_path: Path
    ) -> None:
        missing_path = tmp_path / "agent_runs.jsonl"  # never created
        result = compute_dora_window(agent_runs_path=missing_path, git_commits=[], now=_NOW)
        for window in ("7d", "30d"):
            for metric in ("deployment_frequency", "lead_time", "change_failure_rate", "mttr"):
                assert result["windows"][window][metric]["data_status"] == "insufficient_data"
                assert result["windows"][window][metric]["value"] is None

    def test_agent_runs_present_but_empty_git_log_is_insufficient_everywhere(
        self, tmp_path: Path
    ) -> None:
        path = _write_runs(tmp_path, [_run(ts="2026-06-30T00:00:00+00:00", outcome="success")])
        result = compute_dora_window(agent_runs_path=path, git_commits=[], now=_NOW)
        for window in ("7d", "30d"):
            for metric in result["windows"][window].values():
                assert metric["data_status"] == "insufficient_data"

    def test_commits_present_but_no_agent_runs_is_insufficient_everywhere(
        self, tmp_path: Path
    ) -> None:
        missing_path = tmp_path / "agent_runs.jsonl"
        commits = [_commit("2026-06-30T10:00:00+00:00", "2026-06-30T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=missing_path, git_commits=commits, now=_NOW)
        for window in ("7d", "30d"):
            for metric in result["windows"][window].values():
                assert metric["data_status"] == "insufficient_data"


class TestSpanThreshold:
    def test_span_shorter_than_7_days_is_insufficient_for_both_windows(
        self, tmp_path: Path
    ) -> None:
        # earliest event 2 days ago -> span=2 < 7 < 30 -> both windows insufficient.
        path = _write_runs(tmp_path, [_run(ts="2026-06-29T00:00:00+00:00", outcome="success")])
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        for window in ("7d", "30d"):
            for metric in result["windows"][window].values():
                assert metric["data_status"] == "insufficient_data"

    def test_span_between_7_and_30_days_is_sufficient_for_7d_only(self, tmp_path: Path) -> None:
        # earliest event 10 days ago -> span=10: 7d sufficient (10>=7), 30d insufficient (10<30).
        earliest = "2026-06-21T00:00:00+00:00"
        path = _write_runs(
            tmp_path,
            [
                _run(ts=earliest, outcome="success"),
                _run(ts="2026-06-30T00:00:00+00:00", outcome="success"),
            ],
        )
        commits = [_commit("2026-06-30T10:00:00+00:00", "2026-06-30T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        assert result["windows"]["7d"]["change_failure_rate"]["data_status"] == "ok"
        for metric in result["windows"]["30d"].values():
            assert metric["data_status"] == "insufficient_data"


class TestPerMetricInsufficiency:
    def test_metric_specific_insufficiency_within_a_sufficient_window(self, tmp_path: Path) -> None:
        """Span is sufficient (old agent run sets earliest), but no agent_runs fall
        inside the window itself -> change_failure_rate/mttr insufficient while
        deployment_frequency/lead_time (fed by recent commits) stay ok."""
        old_run = "2026-05-22T00:00:00+00:00"  # 40 days before _NOW
        path = _write_runs(tmp_path, [_run(ts=old_run, outcome="success")])
        commits = [
            _commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00"),
            _commit("2026-06-30T08:00:00+00:00", "2026-06-30T09:00:00+00:00"),
        ]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        window7 = result["windows"]["7d"]
        assert window7["deployment_frequency"]["data_status"] == "ok"
        assert window7["deployment_frequency"]["value"] == 2
        assert window7["lead_time"]["data_status"] == "ok"
        assert window7["change_failure_rate"]["data_status"] == "insufficient_data"
        assert window7["mttr"]["data_status"] == "insufficient_data"


class TestDeploymentFrequency:
    def test_falls_back_to_all_commits_when_no_merges_exist(self, tmp_path: Path) -> None:
        path = _write_runs(tmp_path, [_ANCHOR_RUN])
        commits = [
            _commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00", is_merge=False),
            _commit("2026-06-30T08:00:00+00:00", "2026-06-30T09:00:00+00:00", is_merge=False),
        ]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        metric = result["windows"]["7d"]["deployment_frequency"]
        assert metric["data_status"] == "ok"
        assert metric["value"] == 2
        assert metric["per_day"] == pytest.approx(2 / 7)

    def test_counts_merges_only_when_any_merge_exists(self, tmp_path: Path) -> None:
        path = _write_runs(tmp_path, [_ANCHOR_RUN])
        commits = [
            _commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00", is_merge=False),
            _commit("2026-06-30T08:00:00+00:00", "2026-06-30T09:00:00+00:00", is_merge=True),
        ]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        metric = result["windows"]["7d"]["deployment_frequency"]
        assert metric["value"] == 1  # only the merge commit counted


class TestLeadTime:
    def test_median_of_commit_minus_author_hours(self, tmp_path: Path) -> None:
        path = _write_runs(tmp_path, [_ANCHOR_RUN])
        commits = [
            _commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00"),  # 2h
            _commit("2026-06-30T08:00:00+00:00", "2026-06-30T09:00:00+00:00"),  # 1h
        ]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        metric = result["windows"]["7d"]["lead_time"]
        assert metric["data_status"] == "ok"
        assert metric["value"] == pytest.approx(1.5)
        assert metric["unit"] == "hours"


class TestChangeFailureRate:
    def test_ratio_of_failed_to_total(self, tmp_path: Path) -> None:
        path = _write_runs(
            tmp_path,
            [
                _ANCHOR_RUN,
                _run(ts="2026-06-29T00:00:00+00:00", outcome="failed"),
                _run(ts="2026-06-29T01:00:00+00:00", outcome="success"),
                _run(ts="2026-06-29T02:00:00+00:00", outcome="success"),
                _run(ts="2026-06-29T03:00:00+00:00", outcome="success"),
            ],
        )
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        metric = result["windows"]["7d"]["change_failure_rate"]
        assert metric["data_status"] == "ok"
        assert metric["value"] == pytest.approx(0.25)
        assert metric["failed_count"] == 1
        assert metric["total_count"] == 4


class TestMttr:
    def test_pairs_failed_with_next_success_same_target(self, tmp_path: Path) -> None:
        path = _write_runs(
            tmp_path,
            [
                _ANCHOR_RUN,
                _run(ts="2026-06-29T00:00:00+00:00", outcome="failed", target_path="a.md"),
                _run(ts="2026-06-29T02:00:00+00:00", outcome="success", target_path="a.md"),
            ],
        )
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        metric = result["windows"]["7d"]["mttr"]
        assert metric["data_status"] == "ok"
        assert metric["value"] == pytest.approx(2.0)
        assert metric["recovery_count"] == 1

    def test_unmatched_failure_with_no_later_success_is_insufficient(self, tmp_path: Path) -> None:
        path = _write_runs(
            tmp_path,
            [
                _ANCHOR_RUN,
                _run(ts="2026-06-29T00:00:00+00:00", outcome="failed", target_path="a.md"),
            ],
        )
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        assert result["windows"]["7d"]["mttr"]["data_status"] == "insufficient_data"

    def test_pairs_are_independent_per_target_path(self, tmp_path: Path) -> None:
        path = _write_runs(
            tmp_path,
            [
                _ANCHOR_RUN,
                _run(ts="2026-06-29T00:00:00+00:00", outcome="failed", target_path="a.md"),
                _run(ts="2026-06-29T01:00:00+00:00", outcome="success", target_path="b.md"),
                _run(ts="2026-06-29T04:00:00+00:00", outcome="success", target_path="a.md"),
            ],
        )
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        metric = result["windows"]["7d"]["mttr"]
        # b.md's success has no preceding failure -> not paired; only a.md's 4h gap counts.
        assert metric["value"] == pytest.approx(4.0)
        assert metric["recovery_count"] == 1


class TestMalformedInputResilience:
    def test_agent_run_missing_required_fields_is_skipped_not_crashed(self, tmp_path: Path) -> None:
        path = tmp_path / "agent_runs.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(_ANCHOR_RUN) + "\n")
            fh.write(json.dumps({"ts": "2026-06-29T00:00:00+00:00"}) + "\n")  # missing outcome
            fh.write("not even json\n")
            fh.write(json.dumps(["not", "an", "object"]) + "\n")
            fh.write(json.dumps(_run(ts="2026-06-29T00:00:00+00:00", outcome="success")) + "\n")
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        # the one well-formed record still contributes; malformed ones are skipped, not crashed
        assert result["windows"]["7d"]["change_failure_rate"]["total_count"] == 1

    def test_unreadable_agent_runs_path_degrades_to_insufficient_not_crash(
        self, tmp_path: Path
    ) -> None:
        """`iter_agent_run_records` re-raises non-`FileNotFoundError` `OSError`s

        (e.g. a permission error, or — as simulated here portably — pointing
        the path at a directory instead of a file). The HTTP-facing DORA
        engine must degrade gracefully (all metrics `insufficient_data`)
        rather than let the `OSError` propagate and crash the `/api/dora`
        request handler (Task 4 review-B focus: "never crash the endpoint or
        500 the request"; security-reviewer touch, Task 9).
        """
        unreadable_path = tmp_path / "agent_runs.jsonl"
        unreadable_path.mkdir()  # a directory, not a file -> IsADirectoryError (an OSError)
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=unreadable_path, git_commits=commits, now=_NOW)
        for window in ("7d", "30d"):
            for metric in result["windows"][window].values():
                assert metric["data_status"] == "insufficient_data"

    def test_git_commit_with_unparsable_timestamp_is_skipped(self, tmp_path: Path) -> None:
        path = _write_runs(tmp_path, [_run(ts="2026-06-29T00:00:00+00:00", outcome="success")])
        commits: list[GitCommitTuple] = [("not-a-date", "also-not-a-date", False)]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        # no valid commits -> `not commits` after filtering is empty -> insufficient everywhere
        for metric in result["windows"]["7d"].values():
            assert metric["data_status"] == "insufficient_data"


def test_schema_version_is_1(tmp_path: Path) -> None:
    result = compute_dora_window(
        agent_runs_path=tmp_path / "agent_runs.jsonl", git_commits=[], now=_NOW
    )
    assert result["schema_version"] == 1


class TestReviewPatches:
    """RED→GREEN witnesses for the 2026-07-01 bmad-code-review patches (P1/P2/P3)."""

    def test_non_utf8_byte_in_agent_runs_does_not_crash(self, tmp_path: Path) -> None:
        """P1: an invalid UTF-8 byte must NOT raise ``UnicodeDecodeError`` out of
        ``compute_dora_window``. ``UnicodeDecodeError`` subclasses ``ValueError``
        (not ``OSError``), so pre-fix it escaped the ``except OSError`` guard and
        dropped the ``/api/dora`` connection — and because ``_DoraCache`` stores no
        body on a failed compute, every subsequent request re-crashed. The reader now
        opens ``errors="replace"`` so one bad byte is replaced, not fatal, and the
        still-valid lines contribute."""
        path = tmp_path / "agent_runs.jsonl"
        good_failed = json.dumps(_run(ts="2026-06-29T00:00:00+00:00", outcome="failed"))
        good_success = json.dumps(_run(ts="2026-06-29T02:00:00+00:00", outcome="success"))
        with path.open("wb") as fh:
            fh.write((json.dumps(_ANCHOR_RUN) + "\n").encode("utf-8"))
            fh.write((good_failed + "\n").encode("utf-8"))
            fh.write(b'{"ts":"2026-06-29T01:00:00+00:00","outcome":"x\xff","target_path":"x.md"}\n')
            fh.write((good_success + "\n").encode("utf-8"))
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        # pre-fix this raised UnicodeDecodeError; post-fix it must return a body
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        cfr = result["windows"]["7d"]["change_failure_rate"]
        assert cfr["data_status"] == "ok"
        # the two clean runs count; the replaced-byte line's outcome ("x�") is not
        # success/failed, so P3 excludes it from the denominator.
        assert cfr["failed_count"] == 1
        assert cfr["total_count"] == 2

    def test_future_dated_commit_and_run_excluded_from_windows(self, tmp_path: Path) -> None:
        """P2: events dated after ``now`` (clock skew / crafted GIT_COMMITTER_DATE) must
        not be counted in any trailing window."""
        future = "2026-07-05T00:00:00+00:00"  # 4 days after _NOW
        path = _write_runs(
            tmp_path,
            [
                _ANCHOR_RUN,  # old success -> span sufficient for both windows
                _run(ts="2026-06-29T00:00:00+00:00", outcome="failed"),
                _run(ts=future, outcome="failed"),  # future -> must be excluded
            ],
        )
        commits = [
            _commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00"),
            _commit("2026-07-05T09:00:00+00:00", future),  # future commit_ts -> excluded
        ]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        window7 = result["windows"]["7d"]
        assert window7["deployment_frequency"]["value"] == 1  # future commit not counted
        assert window7["change_failure_rate"]["total_count"] == 1  # future run not counted
        assert window7["change_failure_rate"]["failed_count"] == 1

    def test_change_failure_rate_excludes_out_of_enum_outcomes(self, tmp_path: Path) -> None:
        """P3: a run whose outcome is neither success nor failed must not inflate the
        denominator (which would silently deflate the reported failure rate)."""
        path = _write_runs(
            tmp_path,
            [
                _ANCHOR_RUN,
                _run(ts="2026-06-29T00:00:00+00:00", outcome="failed"),
                _run(ts="2026-06-29T01:00:00+00:00", outcome="success"),
                _run(ts="2026-06-29T02:00:00+00:00", outcome="timeout"),  # out-of-enum
            ],
        )
        commits = [_commit("2026-06-29T10:00:00+00:00", "2026-06-29T12:00:00+00:00")]
        result = compute_dora_window(agent_runs_path=path, git_commits=commits, now=_NOW)
        cfr = result["windows"]["7d"]["change_failure_rate"]
        assert cfr["total_count"] == 2  # the "timeout" run is excluded
        assert cfr["failed_count"] == 1
        assert cfr["value"] == pytest.approx(0.5)
