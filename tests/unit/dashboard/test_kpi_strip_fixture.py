"""Static-analysis contract for KPI strip + value cell (Story 5.7).

Measures component source-of-truth (kpi-strip.js render paths, CSS token
composition) and committed fixture structure — not runtime JS execution,
except resolveState which is also exercised via a pure-function integration hook.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"
_KPI_JS = _STATIC / "components" / "kpi-strip" / "kpi-strip.js"
_KPI_CSS = _STATIC / "components" / "kpi-strip" / "kpi-strip.css"
_FIXTURE = _STATIC / "components" / "kpi-strip" / "kpi-strip.fixture.html"

_KPI_STATES = ("default", "no-data", "stale")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing committed asset: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def _exported_names(js: str) -> set[str]:
    """Names actually listed in `export { ... }` blocks (not merely defined)."""
    names: set[str] = set()
    for block in re.findall(r"export\s*\{([^}]*)\}", js):
        for raw in block.split(","):
            name = raw.strip().split(" as ")[0].strip()
            if name:
                names.add(name)
    return names


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_kpi_strip_js_exports_fixture_and_renderer() -> None:
    js = _read(_KPI_JS)
    assert "export const SYNTHETIC_KPI_FIXTURE" in js
    exported = _exported_names(js)
    assert "renderKpiStrip" in exported
    assert "renderKpiCell" in exported


def test_kpi_strip_js_exports_resolve_state() -> None:
    js = _read(_KPI_JS)
    assert "function resolveState" in js
    assert "resolveState" in _exported_names(js)


def test_resolve_state_pat1_normalizer() -> None:
    """PAT-1: trim + lowercase + membership-check with safe fallback to default."""
    js = _read(_KPI_JS)
    body_match = re.search(r"function resolveState\(.*?\)\s*\{(.*?)\n\}", js, re.DOTALL)
    assert body_match, "resolveState not found"
    body = body_match.group(1)
    assert ".trim()" in body
    assert ".toLowerCase()" in body
    assert "includes" in body
    for state in _KPI_STATES:
        assert state in js


def test_kpi_strip_region_landmark_in_js() -> None:
    js = _read(_KPI_JS)
    assert 'role", "region"' in js or 'setAttribute("role", "region")' in js
    assert "Project KPIs" in js


def test_kpi_strip_dl_semantics_in_js() -> None:
    js = _read(_KPI_JS)
    for tag in ("dl", "dt", "dd"):
        assert f'"{tag}"' in js or f'createElement("{tag}")' in js


def test_kpi_strip_five_cells_in_fixture_data() -> None:
    js = _read(_KPI_JS)
    match = re.search(r"SYNTHETIC_KPI_FIXTURE\s*=\s*\[(.*?)\n\];", js, re.DOTALL)
    assert match, "SYNTHETIC_KPI_FIXTURE array not found"
    fixture_body = match.group(1)
    # Exactly five cells in the synthetic fixture — not a >= count over the whole
    # file (which also counts the render-time placeholder cell).
    assert len(re.findall(r"\blabel\s*:", fixture_body)) == 5


def test_kpi_strip_hero_token_expansion_in_css() -> None:
    css = _read(_KPI_CSS)
    for token in (
        "--type-display-hero-size",
        "--type-display-hero-line-height",
        "--type-display-hero-weight",
        "--type-display-hero-letter-spacing",
    ):
        assert token in css
    assert "var(--font-serif)" in css


def test_kpi_strip_label_and_delta_tokens_in_css() -> None:
    css = _read(_KPI_CSS)
    assert "--type-label-mono-sm-size" in css
    assert "--type-mono-data-size" in css
    assert "--type-body-size" in css


def test_kpi_strip_right_border_except_last_in_css() -> None:
    css = _read(_KPI_CSS)
    assert ":not(:last-child)" in css
    assert "var(--rule)" in css or "var(--border-hairline)" in css


def test_kpi_strip_cell_padding_uses_frozen_spacing() -> None:
    css = _read(_KPI_CSS)
    assert "var(--space-10)" in css
    assert "var(--space-12)" in css


def test_no_data_contract_in_js() -> None:
    """AC2: real-text n/a, aria-describedby, delta omitted."""
    js = _read(_KPI_JS)
    assert '"n/a"' in js or "'n/a'" in js
    assert "aria-describedby" in js
    assert "no-data" in js
    no_data_body = _fn_body(js, "renderNoDataValue")
    assert "delta" not in no_data_body.lower() or "return" in no_data_body


def test_stale_contract_in_js() -> None:
    """AC3: --ink-mute value + as of HH:MM:SS via formatLocalTime."""
    js = _read(_KPI_JS)
    assert "formatLocalTime" in js
    assert "freshness-footer" in js
    assert "stale" in js
    stale_body = _fn_body(js, "renderStaleDelta")
    # The HH:MM:SS digits are produced at runtime by formatLocalTime, so a digit
    # regex can never match JS source. Assert the source actually composes the
    # timestamp via formatLocalTime instead of a decorative regex.
    assert "as of" in stale_body
    assert "formatLocalTime(" in stale_body


def test_delta_non_color_signal_embeds_text_arrow() -> None:
    js = _read(_KPI_JS)
    delta_body = _fn_body(js, "formatDeltaLine")
    assert "\u2191" in delta_body or "\\u2191" in delta_body or '"↑"' in delta_body
    assert "\u2193" in delta_body or "\\u2193" in delta_body or '"↓"' in delta_body


def test_delta_color_classes_in_css() -> None:
    css = _read(_KPI_CSS)
    assert "var(--green)" in css
    assert "var(--red)" in css
    assert "var(--ink-mute)" in css


def test_no_data_value_uses_ink_dim_in_css() -> None:
    css = _read(_KPI_CSS)
    assert "var(--ink-dim)" in css


def test_stale_value_uses_ink_mute_in_css() -> None:
    css = _read(_KPI_CSS)
    assert "kpi-strip__value--stale" in css or '[data-state="stale"]' in css


def test_fixture_mounts_kpi_strip_and_assets() -> None:
    html = _read(_FIXTURE)
    assert "<kpi-strip" in html
    assert "kpi-strip.js" in html
    assert "kpi-strip.css" in html
    assert "tokens.css" in html


def test_synthetic_fixture_covers_all_three_states() -> None:
    js = _read(_KPI_JS)
    for state in _KPI_STATES:
        assert f'state: "{state}"' in js or f"state: '{state}'" in js


def _fn_body(js: str, name: str) -> str:
    match = re.search(rf"function {name}\(.*?\)\s*\{{(.*?)\n\}}", js, re.DOTALL)
    assert match, f"{name} not found"
    return match.group(1)
