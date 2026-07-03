"""Route behaviour tests for ``GET /api/activity`` (Story 5.16 Task 2/6).

``agent_runs.jsonl`` is untrusted file content — these tests assert the route
never 500s on malformed/partial data and never leaks private fields.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ._http import http_get

pytestmark = pytest.mark.unit


def _write_runs(dashboard_project: Path, lines: list[str]) -> Path:
    runs_dir = dashboard_project / "03-Implementation"
    runs_dir.mkdir(parents=True, exist_ok=True)
    runs_path = runs_dir / "agent_runs.jsonl"
    runs_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return runs_path


def _record(
    *,
    run_id: str = "11111111-1111-1111-1111-111111111111",
    ts: str = "2026-06-26T10:00:00.000Z",
    specialist_name: str = "dev-story",
    target_path: str = "5-16",
    workflow_step: str = "implementation",
    outcome: str = "success",
    duration_ms: int = 70_000,
    **overrides: object,
) -> dict[str, object]:
    base = {
        "schema_version": 1,
        "run_id": run_id,
        "ts": ts,
        "specialist_name": specialist_name,
        "target_path": target_path,
        "target_kind": "primary",
        "workflow_step": workflow_step,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "attempts": 1,
        "tokens_in": 100,
        "tokens_out": 200,
        "mock": False,
    }
    base.update(overrides)
    return base


class TestActivityRouteHappyPath:
    def test_missing_file_returns_empty_list_200(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        base_url, port, _ = running_dashboard
        status, headers, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        assert headers.get("content-type", "").startswith("application/json")
        assert json.loads(body.decode("utf-8")) == {"entries": []}

    def test_maps_real_fields_to_display_shape(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        _write_runs(dashboard_project, [json.dumps(_record())])
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert entries == [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "ts": "2026-06-26T10:00:00.000Z",
                "agentName": "dev-story",
                "targetId": "5-16",
                "stage": "implementation",
                "outcome": "success",
                "durationMs": 70_000,
            }
        ]

    def test_does_not_leak_private_fields(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        _write_runs(dashboard_project, [json.dumps(_record())])
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/activity", port=port)
        entry = json.loads(body.decode("utf-8"))["entries"][0]
        for leaked in ("tokens_in", "tokens_out", "dispatch_prompt", "attempts", "mock"):
            assert leaked not in entry

    def test_sorted_reverse_chronological(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        lines = [
            json.dumps(_record(run_id="a", ts="2026-06-26T10:00:00.000Z")),
            json.dumps(_record(run_id="b", ts="2026-06-26T12:00:00.000Z")),
            json.dumps(_record(run_id="c", ts="2026-06-26T11:00:00.000Z")),
        ]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/activity", port=port)
        ids = [e["id"] for e in json.loads(body.decode("utf-8"))["entries"]]
        assert ids == ["b", "c", "a"]

    def test_truncates_to_last_50(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        lines = [
            json.dumps(_record(run_id=f"run-{i:03d}", ts=f"2026-06-26T10:{i:02d}:00.000Z"))
            for i in range(60)
        ]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/activity", port=port)
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert len(entries) == 50
        # newest 50 (highest minute values) kept, reverse-chron
        assert entries[0]["id"] == "run-059"
        assert entries[-1]["id"] == "run-010"

    def test_sorts_by_true_instant_not_lexicographically(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        """AC1 under the untrusted-content mandate (DN-1): reverse-chron must sort by
        the parsed instant, not by a lexicographic string compare. ``11:00:00+07:00``
        (= 04:00Z) is a *lexically larger* string than ``10:00:00Z`` yet an *earlier*
        instant, so a raw-string sort would wrongly place it first."""
        lines = [
            json.dumps(_record(run_id="utc10", ts="2026-06-26T10:00:00Z")),
            json.dumps(_record(run_id="off11", ts="2026-06-26T11:00:00+07:00")),
        ]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/activity", port=port)
        ids = [e["id"] for e in json.loads(body.decode("utf-8"))["entries"]]
        # utc10 (10:00Z) is the LATER instant than off11 (11:00+07:00 = 04:00Z).
        assert ids == ["utc10", "off11"]


class TestActivityRouteUntrustedInputResilience:
    def test_malformed_json_line_skipped_good_rows_returned(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        lines = ["NOT JSON", json.dumps(_record(run_id="good"))]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert [e["id"] for e in entries] == ["good"]

    def test_non_object_line_skipped(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        lines = ["[1, 2, 3]", json.dumps(_record(run_id="good"))]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert [e["id"] for e in entries] == ["good"]

    def test_truncated_trailing_line_skipped(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        lines = [json.dumps(_record(run_id="good")), '{"run_id": "trun'.rstrip()]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert [e["id"] for e in entries] == ["good"]

    @pytest.mark.parametrize(
        "missing_field",
        ["run_id", "ts", "specialist_name", "target_path", "workflow_step", "outcome"],
    )
    def test_record_missing_required_field_dropped(
        self,
        missing_field: str,
        dashboard_project: Path,
        running_dashboard: tuple[str, int, object],
    ) -> None:
        bad_record = _record(run_id="bad")
        del bad_record[missing_field]
        lines = [json.dumps(bad_record), json.dumps(_record(run_id="good"))]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert [e["id"] for e in entries] == ["good"]

    def test_record_with_non_string_duration_dropped(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        bad_record = _record(run_id="bad", duration_ms="not-a-number")
        lines = [json.dumps(bad_record), json.dumps(_record(run_id="good"))]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert [e["id"] for e in entries] == ["good"]

    def test_record_with_unparseable_ts_dropped(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        """DN-1: a non-empty but unparseable ``ts`` (untrusted content) is DROPPED,
        not kept-and-mis-sorted — mirrors the malformed->drop contract and
        telemetry/dora.py::_parse_iso. A garbage ts must never poison the ordering
        that the last-50 truncation depends on."""
        bad_record = _record(run_id="bad", ts="not-a-timestamp")
        lines = [json.dumps(bad_record), json.dumps(_record(run_id="good"))]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert [e["id"] for e in entries] == ["good"]

    def test_unknown_outcome_value_still_passes_through(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        """Future-schema tolerance (D3): an unknown outcome is NOT dropped by the
        route — the client-side renderer is responsible for a neutral fallback."""
        lines = [json.dumps(_record(run_id="a", outcome="timeout"))]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert entries[0]["outcome"] == "timeout"

    def test_xss_payload_passed_through_verbatim_as_data(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        """The route does not sanitize/escape (JSON, not HTML) — XSS-safety is the
        renderer's job (textContent-only, Task 6). This just proves the raw string
        round-trips intact rather than being mangled or dropped."""
        payload = "<img src=x onerror=alert(1)>"
        lines = [json.dumps(_record(run_id="a", specialist_name=payload))]
        _write_runs(dashboard_project, lines)
        base_url, port, _ = running_dashboard
        status, _, body = http_get(base_url, "/api/activity", port=port)
        assert status == 200
        entries = json.loads(body.decode("utf-8"))["entries"]
        assert entries[0]["agentName"] == payload
