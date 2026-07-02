"""Static-analysis contract for the Backlog Tree real-hierarchy poller (Story 5.15).

Mirrors ``test_phase_tracker_live_source.py`` (PAT-3): measures the poller's
JS/HTML source-of-truth rather than executing it (Playwright covers rendered
DOM behavior in ``tests/integration/test_dashboard_backlog_tree_live.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sdlc.ids.parsers import EPIC_ID_PATTERN, STORY_ID_PATTERN, TASK_ID_PATTERN

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPONENTS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "components"
_LIVE_JS = _COMPONENTS / "backlog-tree" / "backlog-tree-live.js"
_FIXTURE = _COMPONENTS / "backlog-tree" / "backlog-tree-live.fixture.html"
_BACKLOG_TREE_JS = _COMPONENTS / "backlog-tree" / "backlog-tree.js"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_NAMED_GROUP = re.compile(r"\(\?P<\w+>")


def _code_only(js: str) -> str:
    return _BLOCK_COMMENT.sub("", js)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_live_module_exists() -> None:
    assert _LIVE_JS.is_file()


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_poll_cadence_is_3000ms() -> None:
    js = _read(_LIVE_JS)
    assert re.search(r"POLL_INTERVAL_MS\s*=\s*3_?000\b", js)
    assert "setInterval" in js


def test_reads_the_api_backlog_seam_not_state_json() -> None:
    """D1: real hierarchy comes from the pure adapter route, never /state.json."""
    js = _read(_LIVE_JS)
    assert "/api/backlog" in js
    assert "/state.json" not in _code_only(js), (
        "must NOT fold the real hierarchy read into /state.json (D1)"
    )


def test_never_reimplements_click_or_keydown_handling() -> None:
    """D3: the frozen 5.10 click/keydown seam must not be rewired."""
    js = _code_only(_read(_LIVE_JS))
    assert 'addEventListener("click"' not in js
    assert 'addEventListener("keydown"' not in js
    assert "addEventListener('click'" not in js
    assert "addEventListener('keydown'" not in js


def test_uses_mutation_observer_not_attribute_rewrite() -> None:
    js = _read(_LIVE_JS)
    assert "MutationObserver" in js
    assert "childList" in js


def test_hash_grammar_is_backlog_key() -> None:
    js = _read(_LIVE_JS)
    assert 'HASH_KEY = "backlog"' in js


def test_hash_reads_and_writes_via_history_replace_state() -> None:
    js = _read(_LIVE_JS)
    assert "location.hash" in js or "locationRef.hash" in js
    assert "replaceState" in js
    assert "hashchange" in js
    # Injection-safety: never innerHTML the hash-derived value.
    assert not re.search(r"\.innerHTML\s*=", js)


def _extract_js_regex_body(js: str, const_name: str) -> str:
    match = re.search(rf"const {const_name}\s*=\s*\n?\s*/\^(.*?)\$/", js, re.DOTALL)
    assert match, f"{const_name} not found in backlog-tree-live.js"
    return match.group(1).replace("\n", "").replace(" ", "")


def _strip_named_groups(pattern: str) -> str:
    stripped = _NAMED_GROUP.sub("(", pattern)
    return stripped.removeprefix("^").removesuffix("$")


def test_hash_id_regexes_mirror_story_1_6_canonical_shape() -> None:
    """Injection-safety validation must match the SHARED Story 1.6 regex shape."""
    js = _read(_LIVE_JS)
    assert _extract_js_regex_body(js, "EPIC_ID_REGEX") == _strip_named_groups(EPIC_ID_PATTERN)
    assert _extract_js_regex_body(js, "STORY_ID_REGEX") == _strip_named_groups(STORY_ID_PATTERN)
    assert _extract_js_regex_body(js, "TASK_ID_REGEX") == _strip_named_groups(TASK_ID_PATTERN)


def test_fixture_mounts_backlog_tree_and_imports_poller() -> None:
    html = _read(_FIXTURE)
    assert '<backlog-tree id="backlog-tree-live-target">' in html
    assert "backlog-tree-live.js" in html
    assert "startBacklogTreeLivePoller" in html


def test_empty_state_row_is_tab_reachable() -> None:
    """D4/DEF-3: an empty real backlog must still expose a Tab entry point."""
    js = _code_only(_read(_BACKLOG_TREE_JS))
    assert 'setAttribute("tabindex", "0")' in js
    assert "epics.length === 0" in js


def test_flow_pill_group_no_longer_silently_drops_unknown_steps() -> None:
    """D5/DEF-5: unknown flow steps get a fallback pill, not a silent drop."""
    pills_js = _read(_COMPONENTS / "pills" / "pills.js")
    assert "fallbackFlowVariant" in pills_js
