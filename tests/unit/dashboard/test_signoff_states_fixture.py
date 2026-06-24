"""Static-analysis contract for the signoff 4-state components (Story 5.9 AC1, AC2, AC3).

These tests measure the COMPONENT source-of-truth — the per-state ``label``/``glyph``
maps that drive runtime rendering — NOT hand-placed fixture markup. (Review DEC-1/PAT-3:
the prior version asserted ``sprite.svg#check`` / "APPROVED" against ``<svg hidden>`` +
``<span hidden>`` decoys the fixture author had typed next to each *empty* ``<signoff-cell>``;
the cell renders its glyph/label via JS that a static-text test never executes, so a real
component regression could not turn the test red.) The fixture tests below assert only
structure that is real in static HTML (the ``<signoff-cell state=...>`` elements and the
phase-tracker landmark) and guard against the decoys returning.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"
_FIXTURE = _STATIC / "test-fixtures" / "signoff-states.html"
_SIGNOFF_JS = _STATIC / "components" / "signoff-cell" / "signoff-cell.js"
_ITEM_ROW_JS = _STATIC / "components" / "phase-item-row" / "phase-item-row.js"
_SPRITE = _STATIC / "icons" / "sprite.svg"

_ALL_STATES = (
    "awaiting-signoff",
    "drafted-not-approved",
    "approved",
    "invalidated-by-replan",
)

# AC1 mandated treatment per state: (text label, cell glyph id or None).
# Color is never the only signal — every state carries a text label; the two
# resolved states also carry a sprite glyph top-right.
_CELL_CONTRACT: dict[str, tuple[str, str | None]] = {
    "awaiting-signoff": ("AWAITING", None),
    "drafted-not-approved": ("DRAFTED", None),
    "approved": ("APPROVED", "check"),
    "invalidated-by-replan": ("INVALIDATED", "slash-circle"),
}

# §7.2 item-row glyph mapping (phase-item-row.js ROW_GLYPHS).
_ROW_CONTRACT: dict[str, str] = {
    "awaiting-signoff": "circle",
    "drafted-not-approved": "circle-filled",
    "approved": "check",
    "invalidated-by-replan": "slash-circle",
}

_GLYPH_VALUE = re.compile(r"""glyph\s*:\s*(null|"[-\w]+"|'[-\w]+')""")
_LABEL_VALUE = re.compile(r"""label\s*:\s*["']([^"']+)["']""")


def _entry_body(js: str, key: str) -> str | None:
    """Return the ``{...}`` body of a line-anchored object entry ``key: { ... }``.

    Anchored at line start (``re.MULTILINE``) so ``approved:`` does not match inside
    ``"drafted-not-approved":``. The SIGNOFF_STATES entry bodies contain no nested braces,
    so the non-greedy capture stops at the entry's own closing brace.
    """
    match = re.search(
        rf"""^[ \t]*["']?{re.escape(key)}["']?\s*:\s*\{{(.*?)\}}""",
        js,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else None


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file(), f"missing committed fixture: {_FIXTURE.relative_to(_REPO_ROOT)}"


def test_signoff_source_defines_all_four_states() -> None:
    js = _SIGNOFF_JS.read_text(encoding="utf-8")
    missing = [s for s in _ALL_STATES if _entry_body(js, s) is None]
    assert not missing, f"signoff-cell.js SIGNOFF_STATES missing entries: {missing}"


def test_signoff_source_label_and_glyph_per_state() -> None:
    """AC1: each state's text label + cell glyph match the mandated treatment."""
    js = _SIGNOFF_JS.read_text(encoding="utf-8")
    for state, (label, glyph) in _CELL_CONTRACT.items():
        body = _entry_body(js, state)
        assert body is not None, f"missing SIGNOFF_STATES entry for {state}"

        label_match = _LABEL_VALUE.search(body)
        assert label_match, f"{state}: no parseable label"
        assert label_match.group(1) == label, (
            f"{state}: label {label_match.group(1)!r} != mandated {label!r}"
        )

        glyph_match = _GLYPH_VALUE.search(body)
        assert glyph_match, f"{state}: no parseable glyph key"
        got = None if glyph_match.group(1) == "null" else glyph_match.group(1).strip("\"'")
        assert got == glyph, f"{state}: glyph {got!r} != mandated {glyph!r}"


def test_no_signoff_state_is_color_only() -> None:
    """5.5 color-only contract, verified at the source: every state carries a non-empty
    text label, so color is never the only signal (the two resolved states add a glyph)."""
    js = _SIGNOFF_JS.read_text(encoding="utf-8")
    for state in _ALL_STATES:
        body = _entry_body(js, state)
        assert body is not None, f"missing SIGNOFF_STATES entry for {state}"
        label_match = _LABEL_VALUE.search(body)
        assert label_match and label_match.group(1).strip(), (
            f"{state}: empty/missing text label — color-only signaling risk"
        )


def test_item_row_source_glyph_per_state() -> None:
    """§7.2 item-row glyph mapping (phase-item-row.js ROW_GLYPHS)."""
    js = _ITEM_ROW_JS.read_text(encoding="utf-8")
    for state, glyph in _ROW_CONTRACT.items():
        match = re.search(
            rf"""^[ \t]*["']?{re.escape(state)}["']?\s*:\s*["']([-\w]+)["']""",
            js,
            re.MULTILINE,
        )
        assert match, f"phase-item-row.js ROW_GLYPHS missing {state}"
        assert match.group(1) == glyph, (
            f"{state}: row glyph {match.group(1)!r} != mandated {glyph!r}"
        )


def test_referenced_glyphs_exist_in_sprite() -> None:
    """Every glyph the components reference resolves to a real symbol in the 5.3 sprite."""
    sprite = _SPRITE.read_text(encoding="utf-8")
    referenced = {g for _, g in _CELL_CONTRACT.values() if g} | set(_ROW_CONTRACT.values())
    for glyph in sorted(referenced):
        assert f'id="{glyph}"' in sprite, f"sprite.svg missing <symbol id={glyph!r}>"


def test_fixture_renders_all_four_signoff_cells() -> None:
    """Structural (real elements, not decoys): a <signoff-cell> exists for each state."""
    html = _FIXTURE.read_text(encoding="utf-8")
    for state in _ALL_STATES:
        assert re.search(
            rf'<signoff-cell\b[^>]*\bstate="{re.escape(state)}"', html, re.IGNORECASE
        ), f"fixture missing <signoff-cell state={state!r}>"


def test_fixture_has_no_hidden_label_decoys() -> None:
    """Regression guard (PAT-3): the fixture must NOT smuggle the contract via hidden
    decoy markup. The uppercase state labels are JS-rendered at runtime; their literal
    presence between tags in static HTML signals a returned decoy."""
    html = _FIXTURE.read_text(encoding="utf-8")
    for label in ("DRAFTED", "APPROVED", "INVALIDATED"):
        assert f">{label}<" not in html, (
            f"fixture statically contains label {label!r} (likely a hidden decoy); "
            "the component must render labels at runtime"
        )


def test_fixture_has_phase_tracker_region() -> None:
    html = _FIXTURE.read_text(encoding="utf-8")
    assert 'role="region"' in html
    assert 'aria-label="Phase tracker"' in html


def test_fixture_phase_tracker_has_five_cells() -> None:
    html = _FIXTURE.read_text(encoding="utf-8")
    tracker_match = re.search(
        r"<phase-tracker[^>]*>(.*?)</phase-tracker>",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert tracker_match, "fixture must include <phase-tracker>"
    inner = tracker_match.group(1)
    phase_cells = len(re.findall(r"<phase-cell\b", inner, re.IGNORECASE))
    signoff_cells = len(re.findall(r"<signoff-cell\b", inner, re.IGNORECASE))
    assert phase_cells == 3, f"expected 3 phase cells, got {phase_cells}"
    assert signoff_cells == 2, f"expected 2 signoff cells, got {signoff_cells}"


def test_fixture_has_item_rows_in_declared_order() -> None:
    html = _FIXTURE.read_text(encoding="utf-8")
    rows = re.findall(r"<phase-item-row\b[^>]*>", html, re.IGNORECASE)
    assert len(rows) >= 3, "fixture must include item rows for focus-order review"
