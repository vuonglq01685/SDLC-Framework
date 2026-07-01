"""Real-compute wiring + schema conformance for ``GET /api/dora`` (Story 5.13).

Generic route/cache-contract tests (frozen by Story 5.1) live in
``test_dashboard_routes.py``; this file covers the 5.13-specific concerns:
DI wiring end-to-end (git-log provider + agent_runs.jsonl -> real numbers),
conformance against ``docs/api/dora-schema.json``, and malformed-input
resilience (review-B / security-reviewer focus, Task 9).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread
from sdlc.telemetry.dora import GitCommitTuple

from ._http import http_get

pytestmark = pytest.mark.unit

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "api" / "dora-schema.json"


def _recent_iso(*, hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "null": (type(None),),
    "array": (list,),
}


def _validate(instance: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    """Minimal recursive JSON-Schema-subset validator (type/enum/required/properties).

    Deliberately hand-rolled (no third-party ``jsonschema`` dependency — not
    declared in pyproject.toml, and this story must not introduce a new
    dependency without approval) — covers only the keywords this schema uses.
    """
    if "type" in schema:
        expected = schema["type"]
        allowed_names = expected if isinstance(expected, list) else [expected]
        allowed_types = tuple(t for name in allowed_names for t in _TYPE_MAP[name])
        # bool is a subclass of int in Python; DORA integers are never bools.
        is_bool = isinstance(instance, bool)
        assert isinstance(instance, allowed_types) and not (
            is_bool and "integer" not in allowed_names and "number" not in allowed_names
        ), f"{path}: expected type {allowed_names}, got {type(instance).__name__} ({instance!r})"
    if "enum" in schema:
        assert instance in schema["enum"], f"{path}: {instance!r} not in enum {schema['enum']}"
    if isinstance(instance, dict):
        for key in schema.get("required", ()):
            assert key in instance, f"{path}: missing required key {key!r}"
        for key, subschema in schema.get("properties", {}).items():
            if key in instance:
                _validate(instance[key], subschema, path=f"{path}.{key}")


def _write_agent_runs(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def _base_run(*, ts: str, outcome: str, target_path: str = "a.md") -> dict[str, Any]:
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


def _start_dashboard(
    repo_root: Path, *, git_commits: list[GitCommitTuple] | None = None
) -> tuple[str, int, object, object]:
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(
        repo_root=repo_root,
        port=port,
        git_log_provider=(lambda: git_commits or []),
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            status, _, _ = http_get(base_url, "/api/dora", port=port)
            if status == 200:
                break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("dashboard server did not become ready")
    return base_url, port, server, thread


def _stop_dashboard(server: Any, thread: Any) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


class TestRealComputeWiring:
    def test_injected_git_and_agent_runs_produce_ok_metrics(self, tmp_path: Path) -> None:
        _write_agent_runs(
            tmp_path / "03-Implementation" / "agent_runs.jsonl",
            [
                _base_run(ts="2026-01-01T00:00:00+00:00", outcome="success"),  # old anchor
                _base_run(ts=_recent_iso(hours_ago=2), outcome="failed"),
                _base_run(ts=_recent_iso(hours_ago=1), outcome="success"),
            ],
        )
        commits: list[GitCommitTuple] = [
            (_recent_iso(hours_ago=10), _recent_iso(hours_ago=9), False)
        ]
        base_url, port, server, thread = _start_dashboard(tmp_path, git_commits=commits)
        try:
            status, _, body = http_get(base_url, "/api/dora", port=port)
            assert status == 200
            payload = json.loads(body.decode("utf-8"))
            window7 = payload["windows"]["7d"]
            assert window7["deployment_frequency"]["data_status"] == "ok"
            assert window7["change_failure_rate"]["data_status"] == "ok"
            assert window7["change_failure_rate"]["value"] == pytest.approx(0.5)
        finally:
            _stop_dashboard(server, thread)

    def test_agent_runs_path_is_derived_from_repo_root(self, tmp_path: Path) -> None:
        """No agent_runs.jsonl on disk at all -> insufficient_data, not a crash."""
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            status, _, body = http_get(base_url, "/api/dora", port=port)
            assert status == 200
            payload = json.loads(body.decode("utf-8"))
            assert payload["windows"]["7d"]["mttr"]["data_status"] == "insufficient_data"
        finally:
            _stop_dashboard(server, thread)


class TestMalformedInputResilience:
    def test_malformed_agent_runs_jsonl_does_not_500(self, tmp_path: Path) -> None:
        runs_path = tmp_path / "03-Implementation" / "agent_runs.jsonl"
        runs_path.parent.mkdir(parents=True)
        runs_path.write_text(
            "not json at all\n"
            + json.dumps(["not", "an", "object"])
            + "\n"
            + json.dumps({"ts": "also missing fields"})
            + "\n",
            encoding="utf-8",
        )
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            status, _, body = http_get(base_url, "/api/dora", port=port)
            assert status == 200
            json.loads(body.decode("utf-8"))  # does not raise
        finally:
            _stop_dashboard(server, thread)


class TestSchemaConformance:
    def test_insufficient_data_response_conforms_to_schema(self, tmp_path: Path) -> None:
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/dora", port=port)
            _validate(json.loads(body.decode("utf-8")), _load_schema())
        finally:
            _stop_dashboard(server, thread)

    def test_ok_response_conforms_to_schema(self, tmp_path: Path) -> None:
        _write_agent_runs(
            tmp_path / "03-Implementation" / "agent_runs.jsonl",
            [
                _base_run(ts="2026-01-01T00:00:00+00:00", outcome="success"),
                _base_run(ts=_recent_iso(hours_ago=2), outcome="success"),
            ],
        )
        commits: list[GitCommitTuple] = [
            (_recent_iso(hours_ago=10), _recent_iso(hours_ago=9), False)
        ]
        base_url, port, server, thread = _start_dashboard(tmp_path, git_commits=commits)
        try:
            _, _, body = http_get(base_url, "/api/dora", port=port)
            _validate(json.loads(body.decode("utf-8")), _load_schema())
        finally:
            _stop_dashboard(server, thread)
