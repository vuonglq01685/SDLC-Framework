"""Static-analysis contract for masthead disconnection wiring (Story 5.20)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MASTHEAD_JS = (
    _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "components" / "masthead" / "masthead.js"
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_masthead_wires_broker_driven_disconnected_variant() -> None:
    js = _read(_MASTHEAD_JS)
    assert "connection-state" in js
    assert "getState" in js or "disconnected" in js
    assert "reportPollResult" in js


def test_masthead_preserves_existing_sub_line_and_rate_limiter() -> None:
    js = _read(_MASTHEAD_JS)
    assert "formatMastheadSubLine" in js
    assert "createAriaLiveRateLimiter" in js
    assert "variantAnnouncementText" in js
    assert "Disconnected" in js
    assert "Connected" in js


def test_masthead_keeps_last_known_good_on_transient_failure() -> None:
    js = _read(_MASTHEAD_JS)
    assert "lastGoodState" in js or "lastKnown" in js.lower()


def test_masthead_poll_catch_reports_failure_to_broker() -> None:
    js = _read(_MASTHEAD_JS)
    assert re.search(r"reportPollResult\s*\(\s*\{\s*ok:\s*false", js)
