"""Route behaviour tests for ``GET /api/resume`` (Story 5.18 Task 1).

D1(b): a dedicated dashboard route computes the ``ResumeToken`` shape
server-side from real sources -- ``state.json`` (phase, via the cross-platform
``read_state_or_refuse`` reader) + the real Epic/Story/Task artifact tree
(cursor, via ``find_current_cursor`` -- state.json does not project the
hierarchy, D1 gap shared with Story 5.15) + the D2 single-source
``compute_suggested_next`` helper. The response is never constructed by
importing ``sdlc.contracts`` (module boundary: ``dashboard`` does not declare
``contracts`` as a dependency) -- these tests instead validate the served JSON
against the real ``ResumeToken`` model directly (freeze 7/7: contract class
untouched).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdlc.cli._epic_story_models import (
    _EpicEntry,
    _StoryEntry,
    _TaskEntry,
    serialize_entry,
    serialize_task_entry,
)
from sdlc.contracts.resume_token import ResumeToken

from ._http import http_get

pytestmark = pytest.mark.unit

_DRAFTED_AT = "2026-07-01T00:00:00.000Z"
_EPICS_DIR = "01-Requirement/04-Epics"
_STORIES_DIR = "01-Requirement/05-Stories"
_TASKS_DIR = "03-Implementation/tasks"


def _write_epic(root: Path, *, id_: str, label: str, ordering: int = 0) -> None:
    entry = _EpicEntry(
        id=id_,
        label=label,
        priority="P1",
        ordering=ordering,
        acceptance_criteria=("Criterion 1",),
        drafted_at=_DRAFTED_AT,
        drafted_by_specialist="epic-generator",
    )
    path = root / _EPICS_DIR / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entry(entry), encoding="utf-8")


def _write_story(root: Path, *, id_: str, epic_id: str, seq: int, label: str) -> None:
    entry = _StoryEntry(
        id=id_,
        epic_id=epic_id,
        seq=seq,
        label=label,
        as_a="a user",
        i_want="a thing",
        so_that="value",
        given_when_then=("Given/When/Then 1",),
        drafted_at=_DRAFTED_AT,
        drafted_by_specialist="story-writer",
    )
    path = root / _STORIES_DIR / epic_id / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entry(entry), encoding="utf-8")


def _write_task(root: Path, *, id_: str, story_id: str, label: str, stage: str = "pending") -> None:
    entry = _TaskEntry(id=id_, story_id=story_id, label=label, stage=stage)
    path = root / _TASKS_DIR / story_id / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_task_entry(entry), encoding="utf-8")


def _write_state(root: Path, *, phase: int = 1, epics: dict | None = None) -> None:
    state_dir = root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "next_monotonic_seq": 0,
        "phase": phase,
        "epics": epics or {},
        "stories": {},
        "tasks": {},
        "auto_loop_status": "idle",
        "stop_reason": None,
    }
    (state_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")


class TestResumeRouteHappyPath:
    def test_missing_state_json_returns_404(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        (dashboard_project / ".claude" / "state" / "state.json").unlink()
        base_url, port, _ = running_dashboard
        status, _, _ = http_get(base_url, "/api/resume", port=port)
        assert status == 404

    def test_fresh_project_no_epics_suggests_sdlc_start(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        _write_state(dashboard_project, phase=1, epics={})
        base_url, port, _ = running_dashboard
        status, headers, body = http_get(base_url, "/api/resume", port=port)
        assert status == 200
        assert headers.get("content-type", "").startswith("application/json")
        payload = json.loads(body.decode("utf-8"))
        assert payload["phase"] == 1
        assert payload["suggested_next_command"] == '/sdlc-start "<idea>"'
        assert payload["cursor"]["breadcrumb"] == ["Phase 1"]

    def test_response_validates_as_resume_token_shape(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        """Freeze 7/7: the served JSON round-trips through the real (untouched)
        ``ResumeToken`` model -- the extra ``breadcrumb`` key lives INSIDE
        ``cursor`` (schema-permitted: cursor's JSON-Schema declares
        ``additionalProperties: true``), so the top-level shape stays exactly
        the 5 frozen keys."""
        _write_state(dashboard_project, phase=1, epics={})
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/resume", port=port)
        payload = json.loads(body.decode("utf-8"))
        token = ResumeToken.model_validate(payload)
        assert token.phase == 1
        assert token.state_hash.startswith("sha256:")

    def test_current_task_populates_full_cursor_and_breadcrumb(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        _write_state(dashboard_project, phase=3, epics={"epic-1": {}})
        _write_epic(dashboard_project, id_="EPIC-stripe-webhook", label="Stripe webhook")
        _write_story(
            dashboard_project,
            id_="EPIC-stripe-webhook-S01-setup",
            epic_id="EPIC-stripe-webhook",
            seq=1,
            label="Setup",
        )
        _write_task(
            dashboard_project,
            id_="EPIC-stripe-webhook-S01-setup-T01-init",
            story_id="EPIC-stripe-webhook-S01-setup",
            label="Init",
            stage="write-tests",
        )
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/resume", port=port)
        payload = json.loads(body.decode("utf-8"))
        assert payload["cursor"]["epic_id"] == "EPIC-stripe-webhook"
        assert payload["cursor"]["story_id"] == "EPIC-stripe-webhook-S01-setup"
        assert payload["cursor"]["task_id"] == "EPIC-stripe-webhook-S01-setup-T01-init"
        assert payload["cursor"]["stage"] == "write-tests"
        assert payload["cursor"]["breadcrumb"] == [
            "Phase 3",
            "EPIC-stripe-webhook",
            "EPIC-stripe-webhook-S01-setup",
            "write-tests",
        ]

    def test_suggested_next_matches_cli_status_single_source(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        """D2 parity: the route's suggested_next_command is produced by the SAME
        compute_suggested_next function sdlc status delegates to -- not a
        parallel re-derivation."""
        from sdlc.state.model import State
        from sdlc.state.suggested_next import compute_suggested_next

        _write_state(dashboard_project, phase=2, epics={"epic-1": {}})
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/resume", port=port)
        payload = json.loads(body.decode("utf-8"))
        expected = compute_suggested_next(State(phase=2, epics={"epic-1": {}}))
        assert payload["suggested_next_command"] == expected


class TestResumeRouteUntrustedInputResilience:
    def test_malformed_state_json_returns_404_not_500(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        state_path = dashboard_project / ".claude" / "state" / "state.json"
        state_path.write_text("NOT JSON", encoding="utf-8")
        base_url, port, _ = running_dashboard
        status, _, _ = http_get(base_url, "/api/resume", port=port)
        assert status == 404

    def test_schema_version_mismatch_returns_404_not_500(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        state_path = dashboard_project / ".claude" / "state" / "state.json"
        state_path.write_text(json.dumps({"schema_version": 2, "phase": 1}), encoding="utf-8")
        base_url, port, _ = running_dashboard
        status, _, _ = http_get(base_url, "/api/resume", port=port)
        assert status == 404

    def test_partial_cursor_missing_story_renders_epic_and_phase_only(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        """D3: a missing part is skipped (never the literal 'undefined')."""
        _write_state(dashboard_project, phase=1, epics={"epic-1": {}})
        _write_epic(dashboard_project, id_="EPIC-x", label="X")
        # no story/task written under EPIC-x -> find_current_cursor returns None
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/resume", port=port)
        payload = json.loads(body.decode("utf-8"))
        assert payload["cursor"]["breadcrumb"] == ["Phase 1"]
        assert "undefined" not in json.dumps(payload)

    def test_negative_phase_clamped_to_zero_and_stays_contract_valid(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        """DEF-2 fold (masthead range-validation, adapted to server-side breadcrumb
        assembly): ``State.phase`` carries no ``ge=0`` constraint (unlike the frozen
        ``ResumeToken.phase = Field(ge=0)``), so a corrupted state.json could smuggle
        a negative phase through. The route clamps once so both the emitted ``phase``
        field and the breadcrumb text stay mutually consistent and contract-valid."""
        state_dir = dashboard_project / ".claude" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "next_monotonic_seq": 0,
            "phase": -5,
            "epics": {},
            "stories": {},
            "tasks": {},
            "auto_loop_status": "idle",
            "stop_reason": None,
        }
        (state_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")
        base_url, port, _ = running_dashboard
        _, _, body = http_get(base_url, "/api/resume", port=port)
        result = json.loads(body.decode("utf-8"))
        assert result["phase"] == 0
        assert result["cursor"]["breadcrumb"] == ["Phase 0"]
        token = ResumeToken.model_validate(result)
        assert token.phase == 0
