"""Doc-contract tests for docs/a11y/ (Story 5.22 Task 3 / D3).

Static assertions over the per-release signoff template + the a11y-minimum
README so the manual-smoke checklist can't silently lose a named surface (or
the §8.4 per-component checklist, or the NVDA/VoiceOver/keyboard sections) in
a future edit. Mirrors the other dashboard static-contract gates (e.g. the
dashboard DD gate scripts) in spirit: a plain-text scan, no rendering needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_A11Y_DOCS_DIR = _REPO_ROOT / "docs" / "a11y"
_TEMPLATE_PATH = _A11Y_DOCS_DIR / "release-template.md"
_README_PATH = _A11Y_DOCS_DIR / "README.md"
_CONTRIBUTING_PATH = _REPO_ROOT / "CONTRIBUTING.md"

# UX §8.4/§8.5 — the 7 named smoke surfaces (AC2's verbatim list).
_NAMED_SURFACES = (
    "masthead",
    "KPI",
    "resume card",
    "phase tracker",
    "backlog tree",
    "STOP banner",
    "activity feed",
)

# UX §8.4 — one component heading per checklist section (the Level-A sign-off form).
_COMPONENT_CHECKLIST_HEADINGS = (
    "Masthead",
    "KPI Strip",
    "Resume Card",
    "Phase Tracker",
    "Backlog Tree",
    "STOP Banner",
    "Tabs",
    "Activity Feed",
    "Copy Button",
    "Disconnected State",
)


def test_release_template_exists() -> None:
    assert _TEMPLATE_PATH.is_file(), f"missing {_TEMPLATE_PATH}"


def test_release_template_names_all_7_smoke_surfaces() -> None:
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    for surface in _NAMED_SURFACES:
        assert surface.lower() in text.lower(), f"template missing named surface: {surface}"


def test_release_template_has_axe_report_section() -> None:
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "generate_a11y_report.py" in text
    assert "A11Y-REPORT-STATUS" in text


def test_release_template_has_screen_reader_smoke_sections() -> None:
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "NVDA" in text
    assert "VoiceOver" in text
    # UX §8.5:1825 verbatim smoke steps.
    for step_fragment in ("masthead", "resume card", "tree node", "STOP banner"):
        assert step_fragment.lower() in text.lower()


def test_release_template_has_keyboard_only_smoke_section() -> None:
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "keyboard-only" in text.lower()
    # UX §8.5:1831-1834 verbatim smoke steps. Anchor to the bold-wrapped key
    # tokens + specific step phrases (review P5) — a bare substring like "tab"
    # is satisfied by "table"/"Tabs" and "focus" by "focused", so the old check
    # could not detect the drift it exists to catch.
    for key_token in (
        "**Tab**",
        "**Enter**",
        "**Right-arrow**",
        "**Left-arrow**",
        "**Arrow-Right**",
    ):
        assert key_token in text, f"missing keyboard smoke key: {key_token}"
    for step_phrase in ("Reach the resume card via", "to switch tabs", "visibly indicated"):
        assert step_phrase in text, f"missing keyboard smoke step: {step_phrase}"


def test_release_template_embeds_full_component_checklist() -> None:
    """AC3 'consult §8.4 to identify the failing component' needs a concrete home."""
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "8.4" in text
    for heading in _COMPONENT_CHECKLIST_HEADINGS:
        assert heading in text, f"§8.4 checklist missing component section: {heading}"


def test_release_template_has_designated_reviewer_signoff_block() -> None:
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "Signoff" in text or "signoff" in text
    assert "Reviewer" in text
    assert "Date" in text


def test_release_template_does_not_fabricate_a_shipped_version() -> None:
    """D3: ship the template now; do NOT fabricate release-0.x.0.md for the unshipped 0.0.0."""
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "0.0.0" not in text


def test_a11y_readme_exists_and_cites_process() -> None:
    assert _README_PATH.is_file(), f"missing {_README_PATH}"
    text = _README_PATH.read_text(encoding="utf-8")
    assert "kind:bug" in text
    assert "quality-gates" in text
    assert "8.4" in text


def test_contributing_cross_links_a11y_readme() -> None:
    """Task 4 (D4): a one-line §1/§8 pointer, not a duplicated process (anti-bloat)."""
    text = _CONTRIBUTING_PATH.read_text(encoding="utf-8")
    assert "docs/a11y/README.md" in text
