"""``GET /api/resume`` — server-computed ``ResumeToken`` (Story 5.18 D1(b)/D2/D3).

D1(b): a dedicated route (architecture.md:1170 names it) computes the
resume-token shape server-side rather than extending the projected
``state.json`` -- mirrors the batch-1 precedent set by
``routes/backlog.py`` (Story 5.15) and ``routes/activity.py`` (Story 5.16):
``state.json`` does not project the real Epic/Story/Task hierarchy (D1 gap,
verified independently by both stories), so the cursor is derived from the
SAME real artifact tree ``backlog.py`` reads, through :func:`find_current_cursor`.

This module MUST NOT import ``sdlc.contracts`` -- ``dashboard`` does not
declare ``contracts`` as a boundary dependency (module_boundary_table.py). The
response is therefore a hand-built dict matching the frozen ``ResumeToken``
shape (schema_version/phase/cursor/suggested_next_command/state_hash), never
a constructed ``ResumeToken`` instance -- freeze stays 7/7 (contract class
untouched; verified by tests validating the served JSON against the real
model from the test side, where importing ``contracts`` is unrestricted).

D2: ``suggested_next_command`` is produced by the SAME
``sdlc.state.suggested_next.compute_suggested_next`` function ``cli/status.py``
delegates to -- "same command as `sdlc status`" holds by construction.

D3: the breadcrumb is assembled SERVER-side into a validated ordered list
(present parts coerced/trimmed, missing parts skipped -- never the literal
"undefined") and carried as an EXTRA ``breadcrumb`` key inside ``cursor``
(schema-legal: ``ResumeToken.cursor`` declares ``additionalProperties: true``,
so this does not touch the frozen top-level shape). The client renders it
directly via the existing array-aware ``parseBreadcrumb``.

Untrusted-content posture (data-validation review focus): a missing/malformed
``state.json`` degrades to 404 (mirrors ``routes/state.py``'s own handling of
an unreadable/escaped artifact) rather than 500ing the dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from sdlc.dashboard.etag import compute_etag
from sdlc.dashboard.router import RequestContext, Response, Router
from sdlc.dashboard.routes.backlog import find_current_cursor
from sdlc.errors import SchemaError, SignoffError, StateError
from sdlc.state.reader import read_state_or_refuse
from sdlc.state.suggested_next import compute_suggested_next

_STATE_REL: Final[str] = ".claude/state/state.json"


def _build_breadcrumb(*, phase: int, cursor: dict[str, str] | None) -> list[str]:
    """D3: server-side validated ordered list. Each present cursor part is
    coerced to a trimmed string; missing or blank parts are SKIPPED (never
    rendered as the literal "undefined"), so a partial/malformed cursor degrades
    cleanly instead of raising -- the route must 404 on bad input, never 500."""
    parts = [f"Phase {phase}"]
    if cursor is not None:
        for key in ("epic_id", "story_id", "stage"):
            value = cursor.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                parts.append(text)
    return parts


def build_resume_token(repo_root: Path) -> dict[str, Any] | None:
    """Pure(ish) read-only derivation of the resume-token JSON shape.

    Returns ``None`` when ``state.json`` is missing, malformed, or schema-
    mismatched (D1) -- the route maps that to 404, never a 500.
    """
    state_path = repo_root / _STATE_REL
    try:
        state = read_state_or_refuse(state_path)
    except (StateError, SchemaError):
        return None
    if state is None:
        return None

    try:
        state_hash = compute_etag(state_path, repo_root=repo_root)
    except SignoffError:
        return None
    if not state_hash:
        return None

    # DEF-2 fold (masthead range-validation, adapted to server-side breadcrumb
    # assembly): `State.phase` carries no `ge=0` constraint (unlike the frozen
    # `ResumeToken.phase = Field(ge=0)`), so a corrupted state.json could smuggle
    # a negative phase through. Clamp ONCE here so the emitted "phase" field and
    # the breadcrumb's "Phase {N}" text stay mutually consistent and contract-valid.
    phase = state.phase if state.phase >= 0 else 0

    cursor_info = find_current_cursor(repo_root)
    cursor: dict[str, Any] = dict(cursor_info) if cursor_info is not None else {}
    cursor["breadcrumb"] = _build_breadcrumb(phase=phase, cursor=cursor_info)

    return {
        "schema_version": 1,
        "phase": phase,
        "cursor": cursor,
        "suggested_next_command": compute_suggested_next(state),
        "state_hash": state_hash,
    }


def register_resume_route(router: Router, *, repo_root: Path) -> None:
    @router.get("/api/resume")
    def handle_resume(_ctx: RequestContext) -> Response:
        token = build_resume_token(repo_root)
        if token is None:
            return Response(status=404, body=b"Not Found")
        body = json.dumps(token, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return Response(
            status=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
        )
