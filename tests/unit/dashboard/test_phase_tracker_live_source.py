"""Static-analysis contract for the Phase Tracker real-signoff poller (Story 5.14).

Mirrors ``test_signoff_states_fixture.py`` (PAT-3): measures the poller's
JS/HTML source-of-truth rather than executing it (Playwright covers rendered
DOM behavior in ``tests/integration/test_dashboard_phase_tracker_live.py``).
Guards the structural contracts that a Python-side test CAN verify cheaply:
the 3 s poll cadence, reuse of the frozen `/api/signoff` seam, content-delta
(no grid resynthesis), and the click-through's forbidden-patterns posture
(no `<dialog>`/modal/toast for the replan-scope disclosure).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPONENTS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "components"
_LIVE_JS = _COMPONENTS / "phase-tracker" / "phase-tracker-live.js"
_FIXTURE = _COMPONENTS / "phase-tracker" / "phase-tracker-live.fixture.html"
_PHASE_TRACKER_JS = _COMPONENTS / "phase-tracker" / "phase-tracker.js"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _code_only(js: str) -> str:
    """Blank JS block comments so doc-comment prose can't fake a source match."""
    return _BLOCK_COMMENT.sub("", js)


def test_live_module_exists() -> None:
    assert _LIVE_JS.is_file(), f"missing {_LIVE_JS.relative_to(_REPO_ROOT)}"


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file(), f"missing committed fixture: {_FIXTURE.relative_to(_REPO_ROOT)}"


def test_poll_cadence_is_3000ms() -> None:
    js = _LIVE_JS.read_text(encoding="utf-8")
    assert re.search(r"POLL_INTERVAL_MS\s*=\s*3_?000\b", js), (
        "phase-tracker-live.js must poll on the 3 s cadence (AC1 final-And, D4)"
    )
    assert "setInterval" in js, "poller must use setInterval (mirrors masthead.js)"


def test_reads_the_api_signoff_seam_not_state_json() -> None:
    js = _LIVE_JS.read_text(encoding="utf-8")
    assert "/api/signoff" in js, "poller must consume the Task-1 /api/signoff read seam"
    assert "/state.json" not in js, (
        "must NOT fold the real signoff read into /state.json (D1: breaks the 5.1 "
        "ETag-over-content contract)"
    )


def test_never_replaces_the_phase_tracker_grid_wholesale() -> None:
    """Only-changed re-render (NFR-PERF-4/DD-06): no full-grid resynthesis."""
    js = _LIVE_JS.read_text(encoding="utf-8")
    assert "phase-tracker__grid" not in js, (
        "poller must not touch/replace .phase-tracker__grid directly — it swaps "
        "attributes on the existing per-phase cells only"
    )
    assert not re.search(r"\.innerHTML\s*=", js), "no innerHTML wholesale replacement"


def test_state_attribute_write_is_change_guarded() -> None:
    """Content-delta only: setAttribute("state", …) must be gated by a diff check."""
    js = _LIVE_JS.read_text(encoding="utf-8")
    assert re.search(r"""getAttribute\(\s*["']state["']\s*\)\s*===\s*stateKey""", js), (
        "state writes must be guarded by a getAttribute(...) === stateKey diff check"
    )


def test_phase_tracker_js_untouched_no_default_strip_resurrection() -> None:
    """5.14 must not resurrect a DEFAULT_STRIP render path in the frozen decorator."""
    js = _code_only(_PHASE_TRACKER_JS.read_text(encoding="utf-8"))
    assert "DEFAULT_STRIP" not in js
    assert "role" in js and "aria-label" in js  # thin ARIA-decorator contract intact


def test_click_through_creates_no_dialog_modal_or_toast() -> None:
    """D2 / §7.12 forbidden-patterns: inline disclosure only, never a dialog/modal/toast."""
    js = _code_only(_LIVE_JS.read_text(encoding="utf-8"))
    fixture = _FIXTURE.read_text(encoding="utf-8")
    for forbidden in ("<dialog", "showModal", 'role="dialog"', "role='dialog'"):
        assert forbidden not in js, f"poller JS must not use {forbidden!r} (forbidden-patterns)"
        assert forbidden not in fixture, (
            f"fixture must not contain {forbidden!r} (forbidden-patterns)"
        )
    assert "toast" not in js.lower()
    assert "toast" not in fixture.lower()


def test_click_through_never_recomputes_via_engine_import() -> None:
    """D2: the click-through reads persisted scope; it must never import the replan engine."""
    js = _code_only(_LIVE_JS.read_text(encoding="utf-8"))
    assert "engine" not in js.lower(), "dashboard JS must never import/reference the replan engine"


def test_fixture_declares_data_phase_hooks_for_every_gate_phase() -> None:
    fixture = _FIXTURE.read_text(encoding="utf-8")
    for phase in ("1", "2"):
        assert re.search(rf'<signoff-cell\b[^>]*\bdata-phase="{phase}"', fixture), (
            f"fixture missing a data-phase={phase!r} signoff-cell hook"
        )
    for phase in ("1", "2", "3"):
        assert re.search(rf'<phase-item-row\b[^>]*\bdata-phase="{phase}"', fixture), (
            f"fixture missing a data-phase={phase!r} phase-item-row hook"
        )


def test_fixture_imports_the_poller_module() -> None:
    fixture = _FIXTURE.read_text(encoding="utf-8")
    assert "startPhaseTrackerPoller" in fixture
    assert "phase-tracker-live.js" in fixture


def test_replan_detail_render_is_content_guarded() -> None:
    """Review patch P1: an open disclosure is not torn down/rebuilt on every 3 s poll."""
    js = _code_only(_LIVE_JS.read_text(encoding="utf-8"))
    assert "data-content-key" in js, (
        "renderReplanDetail must skip the DOM rebuild when reason/downstream are "
        "unchanged (P1: an open disclosure must survive a poll — content-delta, DD-06)"
    )


def test_poll_guards_overlap_and_teardown_removes_listener() -> None:
    """Review patches P2/P3: no stale-over-fresh overlap, and dispose fully tears down."""
    js = _code_only(_LIVE_JS.read_text(encoding="utf-8"))
    # P2: an in-flight guard stops a slow poll from applying AFTER a newer one.
    assert re.search(r"if\s*\(\s*inFlight", js), (
        "poller must skip a tick while a previous poll is still in flight (P2)"
    )
    # P3: the click listener is bound to an AbortController so dispose() removes it
    # (no leaked listener; a re-init cannot stack a duplicate that cancels a click).
    assert "AbortController" in js and re.search(r"\.abort\(\s*\)", js), (
        "dispose() must abort the click listener (P3)"
    )
