"""Unit tests for status._resolve_project_name helpers (Story 1.17 AC2.1).

Split from test_status.py to keep both files under the 400-LOC cap (Architecture
§765 + NFR-MAINT-3). The split is by helper — every assertion here exercises one
of `_extract_project_section` or `_resolve_via_tomllib`. The legacy
`_resolve_via_regex` helper was removed in Story 2A.8 (P34) since runtime is
Python 3.12 and the fallback path is unreachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_extract_project_section_handles_tool_poetry_before_project() -> None:
    """`[tool.poetry] name = "x"` followed by `[project] name = "y"` → return 'y'.

    Naive regex without table awareness would match `x` first. Verifies the
    section-extracted body contains only `[project]` body lines.
    """
    from sdlc.cli.status import _extract_project_section

    text = '[tool.poetry]\nname = "wrong"\n\n[project]\nname = "right"\n'
    body = _extract_project_section(text)
    assert body is not None
    assert "wrong" not in body
    assert "right" in body


def test_extract_project_section_returns_none_when_no_project_table() -> None:
    from sdlc.cli.status import _extract_project_section

    assert _extract_project_section("[build-system]\nrequires = []\n") is None


def test_resolve_via_tomllib_returns_fallback_on_invalid_toml(tmp_path: Path) -> None:
    from sdlc.cli.status import _resolve_via_tomllib

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("not = valid = toml = at all", encoding="utf-8")
    assert _resolve_via_tomllib(pyproject, fallback_name="fallback") == "fallback"


def test_resolve_via_tomllib_returns_fallback_when_no_project_name(tmp_path: Path) -> None:
    """tomllib parses but [project] table has no `name` field."""
    from sdlc.cli.status import _resolve_via_tomllib

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    assert _resolve_via_tomllib(pyproject, fallback_name="fallback") == "fallback"
