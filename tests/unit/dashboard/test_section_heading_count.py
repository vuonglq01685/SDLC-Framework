"""DEF-6 regression: ``renderSectionBlockHeading({count:0})`` must render "0", not blank.

Story 5.14 Task 5 folds deferred-work.md DEF-6 (5.11 review): the prior
``count || ""`` falsy-coercion blanks a legitimate numeric zero (e.g. "0
approved" from a real signoff count). Static-analysis contract (mirrors
test_signoff_states_fixture.py) — measures the component source-of-truth
since these vanilla-JS custom elements have no unit-level JS execution
harness in this repo (Playwright covers rendered-DOM behavior separately).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SECTION_HEADING_JS = (
    _REPO_ROOT
    / "src"
    / "sdlc"
    / "dashboard"
    / "static"
    / "components"
    / "section-heading"
    / "section-heading.js"
)

# The falsy-coercion bug this test guards against: `count || ""` blanks 0.
_FALSY_COERCION = re.compile(r"""countEl\.textContent\s*=\s*count\s*\|\|\s*["']["']""")

# The mandated fix: an explicit null/undefined check, not a falsy check, so a
# numeric 0 still renders "0" while null/undefined/"" still render blank.
_NULLISH_GUARD = re.compile(
    r"""countEl\.textContent\s*=\s*"""
    r"""count\s*==\s*null\s*\?\s*["']["']\s*:\s*String\(count\)"""
)


def test_source_no_longer_uses_falsy_coercion_for_count() -> None:
    js = _SECTION_HEADING_JS.read_text(encoding="utf-8")
    assert not _FALSY_COERCION.search(js), (
        'section-heading.js still uses falsy `count || ""` — this blanks a '
        "legitimate numeric 0 (DEF-6)"
    )


def test_source_uses_nullish_guard_for_count() -> None:
    js = _SECTION_HEADING_JS.read_text(encoding="utf-8")
    assert _NULLISH_GUARD.search(js), (
        "section-heading.js must render count via a null-check "
        '(`count == null ? "" : String(count)`) so numeric 0 renders "0" (DEF-6)'
    )
