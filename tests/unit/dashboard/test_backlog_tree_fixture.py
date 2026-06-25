"""Static-analysis contract for backlog tree + pill registry (Story 5.10).

Measures component source-of-truth (pills.js registry maps, backlog-tree.js
render order) and committed fixture/registry structure — not runtime JS execution.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"
_PILLS_JS = _STATIC / "components" / "pills" / "pills.js"
_BACKLOG_JS = _STATIC / "components" / "backlog-tree" / "backlog-tree.js"
_FIXTURE = _STATIC / "components" / "backlog-tree" / "backlog-tree.fixture.html"
_REGISTRY = _STATIC / "components" / "pills" / "pills.registry.html"

_PILL_GROUPS = ("kind", "status", "stage", "flow", "priority")

_LABEL_IN_JS = re.compile(r"""label\s*:\s*["']([^"']+)["']""")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing committed asset: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_registry_exists() -> None:
    assert _REGISTRY.is_file()


def test_pills_js_exports_all_registry_groups() -> None:
    js = _read(_PILLS_JS)
    assert "PILL_REGISTRY_GROUPS" in js
    for group in _PILL_GROUPS:
        assert f"PILL_{group.upper()}_VARIANTS" in js


def test_pills_js_registry_lists_every_group_key() -> None:
    js = _read(_PILLS_JS)
    for group in _PILL_GROUPS:
        assert re.search(
            rf"PILL_REGISTRY_GROUPS[\s\S]*?\b{group}\s*:\s*PILL_",
            js,
        ), f"pills.js PILL_REGISTRY_GROUPS missing {group}"


def test_backlog_tree_exports_fixture_and_renderer() -> None:
    js = _read(_BACKLOG_JS)
    assert "export const SYNTHETIC_TREE_FIXTURE" in js
    assert "export function renderBacklogTree" in js


def _fn_body(js: str, name: str) -> str:
    match = re.search(rf"function {name}\(.*?\)\s*\{{(.*?)\n\}}", js, re.DOTALL)
    assert match, f"{name} not found"
    return match.group(1)


def test_backlog_tree_kind_badge_immediately_left_of_name_all_render_paths() -> None:
    """§7.3: kind pill is appended BEFORE the name in every render path.

    Covers both the shared epic/story helper AND the separate inline task-row
    path — a reversal in `renderTaskRow` must fail this contract (PAT-3),
    not slip through because only the helper is checked.
    """
    js = _read(_BACKLOG_JS)

    # Epic + story rows go through the shared helper.
    assert "appendKindBadgeLeftOfName" in js
    helper = _fn_body(js, "appendKindBadgeLeftOfName")
    h_pill = helper.find("createPillElement")
    h_name = helper.find('className = "name"')
    assert 0 <= h_pill < h_name, "helper: kind badge must precede the name span"

    # Task rows render the kind pill + name inline (a DIFFERENT code path).
    task_body = _fn_body(js, "renderTaskRow")
    t_pill = task_body.find("createPillElement(kindVariant")
    t_name = task_body.find('"tree-task__name"')
    assert t_pill >= 0 and t_name >= 0, "task row kind pill or name missing"
    assert t_pill < t_name, "renderTaskRow: kind badge must precede the task name"


def test_backlog_tree_fixture_mounts_keyboard_target() -> None:
    html = _read(_FIXTURE)
    assert '<backlog-tree id="backlog-tree-keyboard-target">' in html
    assert "backlog-tree.js" in html
    assert "pills.js" in html
    assert "backlog-tree.css" in html
    assert "pills.css" in html
    assert "inline-code.css" in html


def test_registry_page_references_pills_js() -> None:
    html = _read(_REGISTRY)
    assert "pills.js" in html
    assert "PILL_REGISTRY_GROUPS" in html


def test_registry_mounts_every_pill_group() -> None:
    """Registry page must mount all five pill families (labels are JS-rendered)."""
    html = _read(_REGISTRY)
    for group in _PILL_GROUPS:
        assert f"pill-{group}-mount" in html
        assert f"PILL_REGISTRY_GROUPS.{group}" in html or (
            group == "flow" and "PILL_FLOW_VARIANTS" in html
        )


# The AC2 / §7.9 required vocabulary, per family. A weak `len >= 10` count
# would pass even if an entire named variant were renamed — pin the labels.
_REQUIRED_LABELS: dict[str, set[str]] = {
    "kind": {"EPIC", "STORY", "TASK"},
    "status": {"done", "in-progress", "pending"},
    "stage": {"research", "epics", "stories"},
    "flow": {"research", "epics", "stories"},
    "priority": {"high", "medium", "low"},
}


def test_pills_js_declares_required_ac2_variant_labels() -> None:
    """AC2: every named pill variant must be present verbatim (PAT-4)."""
    js = _read(_PILLS_JS)
    for group in _PILL_GROUPS:
        block_match = re.search(
            rf"export const PILL_{group.upper()}_VARIANTS\s*=\s*\{{(.*?)\n\}};",
            js,
            re.DOTALL,
        )
        assert block_match, f"missing PILL_{group.upper()}_VARIANTS export"
        labels = set(_LABEL_IN_JS.findall(block_match.group(1)))
        required = _REQUIRED_LABELS[group]
        assert required <= labels, (
            f"PILL_{group.upper()}_VARIANTS missing required labels: {sorted(required - labels)}"
        )
    # Kind badges must be EXACTLY the three AC2 variants (no silent rename).
    kind_block = re.search(r"export const PILL_KIND_VARIANTS\s*=\s*\{(.*?)\n\};", js, re.DOTALL)
    assert kind_block
    assert set(_LABEL_IN_JS.findall(kind_block.group(1))) == {"EPIC", "STORY", "TASK"}
