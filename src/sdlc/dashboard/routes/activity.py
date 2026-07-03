"""``GET /api/activity`` — last-50 reverse-chron Activity Feed (Story 5.16 D1/D2/D4).

Reads the real ``agent_runs.jsonl`` through the ``telemetry``-owned reader
seam (``iter_agent_run_records`` — the same reader ``telemetry/dora.py`` uses,
lifted for Story 5.13; ``dashboard`` MUST NOT re-parse the wire file itself
nor import ``cli`` — module_boundary_table.py:142-147). ``agent_runs.jsonl``
is untrusted file content (DAG §5:294): a malformed/partial/truncated line,
a non-object line, or a record missing/mistyping a required field is DROPPED
(never raised, never rendered as ``undefined``) — the route always returns
200 with whatever valid subset remains, even against a missing file (empty
list).

D1 server-side projection: each real ``_AgentRunLine`` dict
[src/sdlc/telemetry/runs.py:36-50] is mapped to the feed's display shape and
ONLY those fields are emitted — ``tokens_in``/``tokens_out``/
``dispatch_prompt``/``attempts``/``mock`` never leak to the browser.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from sdlc.dashboard.router import RequestContext, Response, Router
from sdlc.telemetry.runs import iter_agent_run_records

_logger = logging.getLogger(__name__)

_RUNS_PATH_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_LAST_N: Final[int] = 50

# D1 field map: display_key -> real persisted key on `_AgentRunLine`.
_REQUIRED_STR_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("id", "run_id"),
    ("ts", "ts"),
    ("agentName", "specialist_name"),
    ("targetId", "target_path"),
    ("stage", "workflow_step"),
    ("outcome", "outcome"),
)


def _project_entry(record: dict[str, Any]) -> dict[str, Any] | None:
    """Map one raw ``agent_runs.jsonl`` record to the feed's display shape.

    Returns ``None`` (dropped, D5-style best-effort tolerance) when a
    required field is missing or the wrong type — untrusted input must
    degrade gracefully, never crash the route or leak a partial shape.
    """
    projected: dict[str, Any] = {}
    for display_key, real_key in _REQUIRED_STR_FIELDS:
        value = record.get(real_key)
        if not isinstance(value, str) or not value:
            return None
        projected[display_key] = value

    duration_ms = record.get("duration_ms")
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0:
        return None
    projected["durationMs"] = duration_ms
    return projected


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp; tz-naive values are treated as UTC.

    Mirrors ``telemetry/dora.py::_parse_iso`` (proven across the py3.10-3.13
    support matrix): the ``.replace("Z", "+00:00")`` normalization lets
    ``datetime.fromisoformat`` accept the RFC-3339 ``Z`` suffix on 3.10, and a
    naive value is pinned to UTC so it compares against offset-aware records.
    Returns ``None`` for anything unparseable.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _load_entries(runs_path: Path) -> list[dict[str, Any]]:
    try:
        raw_records = list(iter_agent_run_records(runs_path))
    except OSError as exc:
        # iter_agent_run_records already treats "missing file" as empty; any
        # other OSError (permission denied, I/O error, ...) must not crash
        # this request — degrade to empty entries (mirrors routes/dora.py).
        _logger.warning("agent_runs.jsonl unreadable at %s: %s", runs_path, exc)
        raw_records = []

    projected = [entry for raw in raw_records if (entry := _project_entry(raw)) is not None]
    # Reverse-chronological by the PARSED instant, not a lexicographic string
    # compare (DN-1): agent_runs.jsonl is untrusted and runs.py imposes NO
    # ts-format check, so a mixed-offset / differing-precision / garbage ts
    # would otherwise misorder the feed AND — because `[:_LAST_N]` truncates
    # after the sort — drop genuinely-recent entries. An unparseable ts is
    # dropped (mirrors the route's malformed->drop contract + dora's _parse_iso).
    dated = [(dt, entry) for entry in projected if (dt := _parse_iso(entry["ts"])) is not None]
    dated.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _dt, entry in dated][:_LAST_N]


def register_activity_route(router: Router, *, repo_root: Path) -> None:
    runs_path = repo_root / _RUNS_PATH_REL

    @router.get("/api/activity")
    def handle_activity(_ctx: RequestContext) -> Response:
        body = json.dumps({"entries": _load_entries(runs_path)}, sort_keys=True).encode("utf-8")
        return Response(
            status=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
        )
