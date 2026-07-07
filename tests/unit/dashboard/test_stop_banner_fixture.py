"""Static-analysis contract for STOP banner component (Story 5.19)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"
_JS = _STATIC / "components" / "stop-banner" / "stop-banner.js"
_CSS = _STATIC / "components" / "stop-banner" / "stop-banner.css"
_LIVE_JS = _STATIC / "components" / "stop-banner" / "stop-banner-live.js"
_FIXTURE = _STATIC / "components" / "stop-banner" / "stop-banner.fixture.html"
_LIVE_FIXTURE = _STATIC / "components" / "stop-banner" / "stop-banner-live.fixture.html"

# Authoritative code trigger_ids (engine/stop_registry.py) — NOT the stale AC labels.
_REGISTRY_TRIGGER_IDS = (
    "high_risk_path",
    "agent_failed",
    "open_clarification",
    "signoff_required",
    "replan_dirty",
    "bug_awaiting_decide",
    "pr_ready_story",
)

_DOCUMENTED_SEVERITY = {
    "high_risk_path": "crit",
    "agent_failed": "crit",
    "open_clarification": "info",
    "signoff_required": "warn",
    "replan_dirty": "warn",
    "bug_awaiting_decide": "warn",
    "pr_ready_story": "info",
    "watchdog_timeout": "crit",
    "agent_failure_after_retries": "crit",
}


def _read(path: Path) -> str:
    assert path.is_file(), f"missing committed asset: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_stop_banner_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_stop_banner_live_fixture_exists() -> None:
    assert _LIVE_FIXTURE.is_file()


def test_stop_banner_js_exports_render_seam_and_trigger_meta() -> None:
    js = _read(_JS)
    assert "export const TRIGGER_META" in js
    assert "export function renderStopBanners" in js
    assert "buildSyntheticAll7Triggers" in js


def test_trigger_meta_maps_all_seven_registry_ids_with_documented_severity() -> None:
    js = _read(_JS)
    for trigger_id, severity in _DOCUMENTED_SEVERITY.items():
        if trigger_id not in _REGISTRY_TRIGGER_IDS and trigger_id not in (
            "watchdog_timeout",
            "agent_failure_after_retries",
        ):
            continue
        pattern = rf'{re.escape(trigger_id)}:\s*\{{[^}}]*severity:\s*"{severity}"'
        assert re.search(pattern, js), f"TRIGGER_META missing {trigger_id!r} -> {severity!r}"


def test_trigger_meta_includes_out_of_registry_strings_and_neutral_fallback() -> None:
    js = _read(_JS)
    assert "watchdog_timeout" in js
    assert "agent_failure_after_retries" in js
    assert "NEUTRAL_META" in js or "neutral" in js


def test_trigger_meta_covers_live_engine_registry_no_drift() -> None:
    """AC2 / Task 1: cross-check against the LIVE engine registry, not a copy.

    A renamed/added/reordered trigger in engine/stop_registry.py fails HERE
    instead of silently drifting from the dashboard TRIGGER_META map (review
    2026-07-07 P7 — the mapping test previously only checked the JS against a
    hardcoded dict that could co-drift with it).
    """
    from sdlc.engine.stop_registry import ordered_triggers

    registry_ids = [trigger.trigger_id for trigger in ordered_triggers()]
    assert registry_ids == list(_REGISTRY_TRIGGER_IDS), (
        "engine registry drifted from the documented dashboard order/ids: "
        f"engine={registry_ids} documented={list(_REGISTRY_TRIGGER_IDS)}"
    )
    js = _read(_JS)
    for trigger_id in registry_ids:
        severity = _DOCUMENTED_SEVERITY[trigger_id]
        pattern = rf'{re.escape(trigger_id)}:\s*\{{[^}}]*severity:\s*"{severity}"'
        assert re.search(pattern, js), f"TRIGGER_META missing {trigger_id!r} -> {severity!r}"


def test_neutral_severity_tag_is_notice() -> None:
    """Review 2026-07-07 (Decision a): unknown/neutral banners carry a NOTICE: text tag."""
    js = _read(_JS)
    assert 'neutral: "NOTICE:"' in js


def test_severity_uses_alert_treatment_not_live_dot() -> None:
    js = _read(_JS)
    css = _read(_CSS)
    assert "<live-dot" not in js
    assert "live-dot.js" not in js
    assert ".alert" in css or "stop-banner" in css
    assert "CRITICAL:" in js
    assert "WARNING:" in js
    assert "INFO:" in js


def test_untrusted_content_hardening_in_js() -> None:
    js = _read(_JS)
    assert "textContent" in js
    assert "MAX_REASON_LEN" in js or "_MAX_REASON" in js or "200" in js
    # The render sink is textContent, never innerHTML. (review 2026-07-07 P11:
    # dropped a confused `.replace("//", "")` that stripped comment markers but
    # left comment bodies — it did not do what it claimed.)
    assert "innerHTML" not in js


def test_read_only_action_surface_no_write_buttons() -> None:
    js = _read(_JS)
    fixture = _read(_FIXTURE)
    for forbidden in ("<form", "<dialog", "showModal", 'type="submit"'):
        assert forbidden not in js
        assert forbidden not in fixture


def test_stop_banner_a11y_roles_in_js() -> None:
    js = _read(_JS)
    assert 'role="alert"' in js or "alert" in js
    assert "aria-labelledby" in js


def test_synthetic_fixture_declares_all_seven_code_trigger_ids() -> None:
    js = _read(_JS)
    for trigger_id in _REGISTRY_TRIGGER_IDS:
        assert trigger_id in js, f"stop-banner.js missing trigger_id {trigger_id!r}"


def test_synthetic_fixture_has_text_severity_labels_in_js() -> None:
    js = _read(_JS)
    for tag in ("CRITICAL:", "WARNING:", "INFO:"):
        assert tag in js


def test_stop_banner_css_uses_semantic_tokens_only() -> None:
    css = _read(_CSS)
    assert "var(--paper)" in css
    assert "var(--blue)" in css or "var(--amber)" in css or "var(--red)" in css
    hex_colors = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
    assert hex_colors == []


def test_empty_state_falsy_message_coercion_def5() -> None:
    """Fold 5.5 DEF-5: empty string message must fall back to default copy."""
    empty_js = _read(_STATIC / "components" / "empty-state" / "empty-state.js")
    assert "EMPTY_STATE_MESSAGE" in empty_js
    assert 'rawMessage === ""' in empty_js or "rawMessage == null" in empty_js


def test_copy_btn_relocated_to_inverted_command_def6() -> None:
    inverted_css = _read(_STATIC / "components" / "inverted-command" / "inverted-command.css")
    resume_css = _read(_STATIC / "components" / "resume-card" / "resume-card.css")
    assert ".copy-btn" in inverted_css
    assert "36px" in inverted_css
    assert ".copy-btn" not in resume_css
