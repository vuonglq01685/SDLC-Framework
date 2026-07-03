"""Static-analysis contracts for tabs, activity feed, empty state, section heading (Story 5.11)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"
_TABS_JS = _STATIC / "components" / "tabs" / "tabs.js"
_FEED_JS = _STATIC / "components" / "activity-feed" / "activity-feed.js"
_EMPTY_JS = _STATIC / "components" / "empty-state" / "empty-state.js"
_HEADING_JS = _STATIC / "components" / "section-heading" / "section-heading.js"
_TABS_FIXTURE = _STATIC / "components" / "tabs" / "tabs.fixture.html"
_FEED_FIXTURE = _STATIC / "components" / "activity-feed" / "activity-feed.fixture.html"
_EMPTY_FIXTURE = _STATIC / "components" / "empty-state" / "empty-state.fixture.html"
_RHYTHM_FIXTURE = _STATIC / "test-fixtures" / "editorial-scanning-rhythm.html"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing committed asset: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_tabs_fixture_exists() -> None:
    assert _TABS_FIXTURE.is_file()


def test_activity_feed_fixture_exists() -> None:
    assert _FEED_FIXTURE.is_file()


def test_empty_state_fixture_exists() -> None:
    assert _EMPTY_FIXTURE.is_file()


def test_rhythm_fixture_exists() -> None:
    assert _RHYTHM_FIXTURE.is_file()


def test_tabs_js_exports_fixture_and_renderer() -> None:
    js = _read(_TABS_JS)
    assert "export const SYNTHETIC_TABS_FIXTURE" in js
    assert "export function renderTabs" in js
    assert 'role="tablist"' in js or "tablist" in js


def test_tabs_fixture_has_tablist_tab_tabpanel_contract() -> None:
    js = _read(_TABS_JS)
    assert 'role="tablist"' in js or "tablist" in js
    assert 'role="tab"' in js
    assert "tabpanel" in js
    assert "aria-controls" in js
    assert "aria-selected" in js


def test_activity_feed_js_exports_fixture_and_renderer() -> None:
    js = _read(_FEED_JS)
    assert "export const SYNTHETIC_ACTIVITY_FEED_FIXTURE" in js
    assert "export function renderActivityFeed" in js
    assert "prependActivityFeedEntry" in js


def test_activity_feed_fixture_has_exactly_50_entries() -> None:
    js = _read(_FEED_JS)
    assert "buildSyntheticEntries(50)" in js


def test_activity_feed_entry_has_six_fields() -> None:
    """Story 5.16 D2: the AC's 6 fields, real field names (drop the 5.11 synthetic
    ``timestamp``/``duration`` grep -- the real record uses ``ts``/``durationMs``,
    reconciled client-side onto the unchanged renderer contract)."""
    js = _read(_FEED_JS)
    for field in ("agentName", "targetId", "stage", "outcome", "durationMs"):
        assert field in js, f"activity feed must render {field}"


def test_activity_feed_incremental_prepend_preserves_existing_nodes() -> None:
    js = _read(_FEED_JS)
    assert "insertBefore" in js
    assert "prependActivityFeedEntry" in js
    render_body = js.split("export function renderActivityFeed")[1]
    render_body = render_body.split("export function prependActivityFeedEntry")[0]
    assert "replaceChildren" not in render_body


def test_activity_feed_outcome_glyph_uses_frozen_sprite() -> None:
    js = _read(_FEED_JS)
    for glyph in ("check", "slash-circle", "error"):
        assert glyph in js


def test_activity_feed_unknown_outcome_maps_to_neutral_glyph_not_error() -> None:
    """D3/DEF-3: an unknown outcome must route to the neutral `warning` glyph,
    never the red `error` glyph (real writer emits only {success, failed})."""
    js = _read(_FEED_JS)
    assert "warning" in js
    assert "NEUTRAL_OUTCOME_GLYPH" in js


def test_activity_feed_exports_live_poller_and_never_uses_innerhtml() -> None:
    js = _read(_FEED_JS)
    assert "export function startActivityFeedLivePoller" in js
    assert "innerHTML" not in js, "renderer must stay textContent-only (Task 6 XSS-safety)"


def test_activity_feed_live_source_skips_synthetic_default_render() -> None:
    """A `data-source="live"` host must not flash synthetic rows before the
    real poller's first fetch resolves."""
    js = _read(_FEED_JS)
    assert 'dataset.source === "live"' in js


def test_empty_state_message_constant_is_non_blank_anti_cynicism_copy() -> None:
    # Behavioral "never silently blank" coverage lives in the Playwright suite
    # (tests/integration/test_dashboard_activity_feed_empty_state.py); this static
    # contract pins the message constant itself so a blank/banned copy fails fast.
    js = _read(_EMPTY_JS)
    assert "freshness-footer" in js
    match = re.search(r'EMPTY_STATE_MESSAGE\s*=\s*"([^"]*)"', js)
    assert match is not None, "EMPTY_STATE_MESSAGE constant must be defined"
    message = match.group(1).strip()
    assert message, "empty-state message must be non-blank (UX-DR15: silent blank forbidden)"
    assert "All clear!" not in message, "D2 bans the exclamatory 'All clear!' form"
    assert "messageEl.textContent = message" in js, (
        "the message constant must be rendered, not just declared"
    )
    html = _read(_EMPTY_FIXTURE)
    assert "<empty-state" in html


def test_empty_state_js_exports_renderer() -> None:
    js = _read(_EMPTY_JS)
    assert "export function renderEmptyState" in js
    assert "freshness-footer" in js


def test_section_heading_js_exports_renderer() -> None:
    js = _read(_HEADING_JS)
    assert "renderSectionBlockHeading" in js
    assert "type-display-3" in js or "display-3" in js


def test_rhythm_fixture_section_order() -> None:
    """§7.10: Masthead → KPI → Tabs → Phase tracker → main content."""
    html = _read(_RHYTHM_FIXTURE)
    markers = [
        'data-rhythm-section="masthead"',
        'data-rhythm-section="kpi-strip"',
        'data-rhythm-section="tabs"',
        'data-rhythm-section="phase-tracker"',
        'data-rhythm-section="main-content"',
    ]
    positions = [html.find(m) for m in markers]
    assert all(p >= 0 for p in positions), "every rhythm section marker must be present"
    assert positions == sorted(positions), "sections must appear in editorial scanning order"


def test_rhythm_fixture_main_column_order() -> None:
    """Side col: resume → alerts (STOP/empty) → activity feed."""
    html = _read(_RHYTHM_FIXTURE)
    resume = html.find('data-rhythm-section="resume-card"')
    alerts = html.find('data-rhythm-section="alerts-column"')
    feed = html.find('data-rhythm-section="activity-feed"')
    assert resume >= 0 and alerts >= 0 and feed >= 0
    assert resume < alerts < feed


def test_rhythm_fixture_named_sections_have_section_block_heading() -> None:
    html = _read(_RHYTHM_FIXTURE)
    for section in ("Phase tracker", "Backlog", "Activity", "Alerts"):
        assert section in html
    assert html.count("section-block-heading") >= 4
