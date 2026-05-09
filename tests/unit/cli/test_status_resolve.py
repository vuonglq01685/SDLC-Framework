"""Unit tests for status._resolve_project_name helpers (Story 1.17 AC2.1).

Split from test_status.py to keep both files under the 400-LOC cap (Architecture
§765 + NFR-MAINT-3). The split is by helper, not by test type — every assertion
here exercises one of `_extract_project_section`, `_resolve_via_regex`, or
`_resolve_via_tomllib`.
"""

from __future__ import annotations

import unittest.mock
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


def test_resolve_via_regex_returns_name_from_project_section(tmp_path: Path) -> None:
    """The 3.10 regex fallback resolves `[project] name`."""
    from sdlc.cli.status import _resolve_via_regex

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.poetry]\nname = "wrong"\n[project]\nname = "right"\n', encoding="utf-8"
    )
    assert _resolve_via_regex(pyproject, fallback_name="fallback") == "right"


def test_resolve_via_regex_returns_fallback_on_oserror(tmp_path: Path) -> None:
    """OSError reading pyproject.toml in 3.10 fallback returns the fallback name."""
    from sdlc.cli.status import _resolve_via_regex

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\n", encoding="utf-8")
    with unittest.mock.patch.object(
        type(pyproject), "read_text", side_effect=OSError("permission denied")
    ):
        assert _resolve_via_regex(pyproject, fallback_name="fallback") == "fallback"


def test_resolve_via_regex_returns_fallback_when_no_project_table(tmp_path: Path) -> None:
    from sdlc.cli.status import _resolve_via_regex

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[build-system]\nrequires = []\n", encoding="utf-8")
    assert _resolve_via_regex(pyproject, fallback_name="fallback") == "fallback"


def test_resolve_via_regex_returns_fallback_when_project_lacks_name(tmp_path: Path) -> None:
    from sdlc.cli.status import _resolve_via_regex

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "0.1"\n', encoding="utf-8")
    assert _resolve_via_regex(pyproject, fallback_name="fallback") == "fallback"


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
