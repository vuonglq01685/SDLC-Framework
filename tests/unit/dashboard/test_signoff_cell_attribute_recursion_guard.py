"""Regression guard for a pre-existing infinite-recursion defect (Story 5.14).

``signoff-cell.js`` / ``phase-cell.js`` are frozen Story 5.9 substrate. Story
5.9 only ever asserted them via static-text contracts
(``test_signoff_states_fixture.py``) — no test actually rendered them in a
browser, so a real defect went undetected: both components call
``element.setAttribute(name, value)`` on an *observed* attribute
(``state`` / ``aria-label``) from inside the render triggered by that very
attribute's own change. The DOM does not dedupe ``setAttribute`` by value —
``attributeChangedCallback`` fires again even when the new value is IDENTICAL
to the current one — so an unguarded write recurses synchronously until the
call stack overflows (``RangeError: Maximum call stack size exceeded``),
discovered when Story 5.14's Playwright suite first loaded these components
in a real browser (``tests/integration/test_dashboard_phase_tracker_live.py``).

These tests pin the fix at the source: any write to an observed attribute
from within a render path must be diff-guarded via ``setAttributeIfChanged``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPONENTS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "components"
_SIGNOFF_JS = _COMPONENTS / "signoff-cell" / "signoff-cell.js"
_PHASE_CELL_JS = _COMPONENTS / "phase-cell" / "phase-cell.js"

_UNGUARDED_STATE_WRITE = re.compile(r"""this\.setAttribute\(\s*["']state["']\s*,\s*stateKey\s*\)""")
_UNGUARDED_ARIA_WRITE = re.compile(r"""root\.setAttribute\(\s*["']aria-label["']\s*,""")


def test_signoff_cell_defines_the_set_attribute_if_changed_guard() -> None:
    js = _SIGNOFF_JS.read_text(encoding="utf-8")
    assert "function setAttributeIfChanged(" in js, (
        "signoff-cell.js must define a diff-guarded attribute-write helper"
    )
    assert (
        "setAttributeIfChanged" in _SIGNOFF_JS.read_text(encoding="utf-8").split("export {")[-1]
    ), "setAttributeIfChanged must be exported so phase-cell.js can reuse it"


def test_signoff_cell_render_does_not_unconditionally_rewrite_state() -> None:
    js = _SIGNOFF_JS.read_text(encoding="utf-8")
    assert not _UNGUARDED_STATE_WRITE.search(js), (
        "SignoffCell._render() must not call this.setAttribute('state', stateKey) "
        "unconditionally — setAttribute re-fires attributeChangedCallback even when "
        "the value is unchanged, causing unbounded recursion"
    )
    assert re.search(r"""setAttributeIfChanged\(\s*this\s*,\s*["']state["']""", js), (
        "SignoffCell._render() must write 'state' through the guarded helper"
    )


def test_signoff_cell_aria_label_write_is_guarded() -> None:
    js = _SIGNOFF_JS.read_text(encoding="utf-8")
    assert not _UNGUARDED_ARIA_WRITE.search(js), (
        "renderSignoffCell() must not call root.setAttribute('aria-label', ...) "
        "unconditionally — 'aria-label' is an observed attribute"
    )
    assert re.search(r"""setAttributeIfChanged\(\s*root\s*,\s*["']aria-label["']""", js)


def test_phase_cell_imports_and_uses_the_shared_guard() -> None:
    js = _PHASE_CELL_JS.read_text(encoding="utf-8")
    assert "setAttributeIfChanged" in js, (
        "phase-cell.js must import setAttributeIfChanged from signoff-cell.js "
        "(mirrors its existing createGlyph re-use) to guard its observed "
        "'aria-label' write in renderPhaseCell()"
    )
    assert not _UNGUARDED_ARIA_WRITE.search(js), (
        "renderPhaseCell() must not call root.setAttribute('aria-label', ...) "
        "unconditionally — 'aria-label' is an observed attribute on <phase-cell>"
    )
