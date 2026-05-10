"""Unit tests for telemetry.runs.record_agent_run (Story 2A.3, AC9, Task 3.1).

TDD-first: tests committed before implementation (ADR-026 §1).
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SKIP_WIN32 = pytest.mark.skipif(
    sys.platform == "win32",
    reason="file_lock is POSIX-only — concurrent-write test requires fcntl",
)

_BASE_KWARGS: dict = {
    "run_id": "11111111-1111-1111-1111-111111111111",
    "ts": "2026-05-10T12:00:00.000Z",
    "workflow_step": "requirements",
    "specialist_name": "product-strategist",
    "target_kind": "primary",
    "outcome": "success",
    "attempts": 1,
    "tokens_in": 100,
    "tokens_out": 200,
    "target_path": "01-Requirement/01-PRODUCT.md",
    "duration_ms": 1234,
}


class TestRecordAgentRunWritesOneLine:
    def test_creates_file_with_one_jsonl_line(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        runs_path = tmp_path / "agent_runs.jsonl"
        record_agent_run(runs_path, **_BASE_KWARGS)

        lines = runs_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1

    def test_appends_second_line_on_second_call(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        runs_path = tmp_path / "agent_runs.jsonl"
        record_agent_run(runs_path, **_BASE_KWARGS)
        kwargs2 = {**_BASE_KWARGS, "run_id": "22222222-2222-2222-2222-222222222222"}
        record_agent_run(runs_path, **kwargs2)

        lines = runs_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_line_is_valid_json(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        runs_path = tmp_path / "agent_runs.jsonl"
        record_agent_run(runs_path, **_BASE_KWARGS)

        line = runs_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert isinstance(parsed, dict)


class TestRecordAgentRunRoundTrip:
    def test_all_fields_present(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        runs_path = tmp_path / "agent_runs.jsonl"
        record_agent_run(runs_path, **_BASE_KWARGS)

        record = json.loads(runs_path.read_text(encoding="utf-8").strip())
        assert record["schema_version"] == 1
        assert record["run_id"] == _BASE_KWARGS["run_id"]
        assert record["ts"] == _BASE_KWARGS["ts"]
        assert record["workflow_step"] == _BASE_KWARGS["workflow_step"]
        assert record["specialist_name"] == _BASE_KWARGS["specialist_name"]
        assert record["target_kind"] == _BASE_KWARGS["target_kind"]
        assert record["outcome"] == _BASE_KWARGS["outcome"]
        assert record["attempts"] == _BASE_KWARGS["attempts"]
        assert record["tokens_in"] == _BASE_KWARGS["tokens_in"]
        assert record["tokens_out"] == _BASE_KWARGS["tokens_out"]
        assert record["target_path"] == _BASE_KWARGS["target_path"]
        assert record["duration_ms"] == _BASE_KWARGS["duration_ms"]

    def test_schema_version_is_1(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        runs_path = tmp_path / "agent_runs.jsonl"
        record_agent_run(runs_path, **_BASE_KWARGS)
        record = json.loads(runs_path.read_text(encoding="utf-8").strip())
        assert record["schema_version"] == 1


class TestRecordAgentRunValidation:
    def test_bad_outcome_raises_value_error(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        bad = {**_BASE_KWARGS, "outcome": "partial"}
        with pytest.raises(ValueError, match="outcome"):
            record_agent_run(tmp_path / "agent_runs.jsonl", **bad)

    def test_bad_target_kind_raises_value_error(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        bad = {**_BASE_KWARGS, "target_kind": "supervisor"}
        with pytest.raises(ValueError, match="target_kind"):
            record_agent_run(tmp_path / "agent_runs.jsonl", **bad)

    def test_valid_outcome_failed_accepted(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        kwargs = {**_BASE_KWARGS, "outcome": "failed"}
        record_agent_run(tmp_path / "agent_runs.jsonl", **kwargs)
        record = json.loads((tmp_path / "agent_runs.jsonl").read_text().strip())
        assert record["outcome"] == "failed"

    def test_valid_target_kind_parallel_accepted(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        kwargs = {**_BASE_KWARGS, "target_kind": "parallel"}
        record_agent_run(tmp_path / "agent_runs.jsonl", **kwargs)
        record = json.loads((tmp_path / "agent_runs.jsonl").read_text().strip())
        assert record["target_kind"] == "parallel"

    def test_valid_target_kind_synthesizer_accepted(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        kwargs = {**_BASE_KWARGS, "target_kind": "synthesizer"}
        record_agent_run(tmp_path / "agent_runs.jsonl", **kwargs)
        record = json.loads((tmp_path / "agent_runs.jsonl").read_text().strip())
        assert record["target_kind"] == "synthesizer"


class TestRecordAgentRunSortedKeys:
    def test_json_keys_are_sorted(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        runs_path = tmp_path / "agent_runs.jsonl"
        record_agent_run(runs_path, **_BASE_KWARGS)

        line = runs_path.read_text(encoding="utf-8").strip()
        keys = list(json.loads(line).keys())
        assert keys == sorted(keys), f"keys not sorted: {keys}"

    def test_line_ends_with_newline(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        runs_path = tmp_path / "agent_runs.jsonl"
        record_agent_run(runs_path, **_BASE_KWARGS)
        assert runs_path.read_text(encoding="utf-8").endswith("\n")


@_SKIP_WIN32
class TestRecordAgentRunConcurrentWrites:
    def test_two_threads_write_two_complete_lines(self, tmp_path: Path) -> None:
        from sdlc.telemetry.runs import record_agent_run

        runs_path = tmp_path / "agent_runs.jsonl"
        errors: list[BaseException] = []

        def _write(run_id: str) -> None:
            try:
                record_agent_run(runs_path, **{**_BASE_KWARGS, "run_id": run_id})
            except BaseException as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_write, args=("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",))
        t2 = threading.Thread(target=_write, args=("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"thread errors: {errors}"
        lines = runs_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        # both lines must be valid JSON
        for line in lines:
            assert json.loads(line)["schema_version"] == 1
