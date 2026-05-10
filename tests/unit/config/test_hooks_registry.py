"""Tests for config/hooks.py hook registry loader (AC2, AC11 D1, Story 2A.4 Task 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.config.hooks import load_hook_registry
from sdlc.errors import ConfigError


def _write_pyproject(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(content)
    return p


@pytest.mark.unit
class TestLoadHookRegistry:
    def test_valid_registry(self, tmp_path) -> None:
        p = _write_pyproject(
            tmp_path,
            '[tool.sdlc.hooks]\npre_write = ["naming_validator", "phase_gate"]\n',
        )
        result = load_hook_registry(p)
        assert result == ("naming_validator", "phase_gate")

    def test_missing_tool_sdlc_hooks_returns_empty(self, tmp_path) -> None:
        p = _write_pyproject(tmp_path, "[project]\nname = 'test'\n")
        result = load_hook_registry(p)
        assert result == ()

    def test_empty_pre_write_list_returns_empty(self, tmp_path) -> None:
        p = _write_pyproject(tmp_path, "[tool.sdlc.hooks]\npre_write = []\n")
        result = load_hook_registry(p)
        assert result == ()

    def test_unknown_hook_raises_config_error(self, tmp_path) -> None:
        p = _write_pyproject(
            tmp_path,
            '[tool.sdlc.hooks]\npre_write = ["unknown_hook"]\n',
        )
        with pytest.raises(ConfigError, match="unknown hook"):
            load_hook_registry(p)

    def test_unknown_hook_error_includes_available(self, tmp_path) -> None:
        p = _write_pyproject(
            tmp_path,
            '[tool.sdlc.hooks]\npre_write = ["bad_hook"]\n',
        )
        with pytest.raises(ConfigError, match="available"):
            load_hook_registry(p)

    def test_duplicate_hook_raises_config_error(self, tmp_path) -> None:
        p = _write_pyproject(
            tmp_path,
            '[tool.sdlc.hooks]\npre_write = ["naming_validator", "naming_validator"]\n',
        )
        with pytest.raises(ConfigError, match="duplicate hook"):
            load_hook_registry(p)

    def test_pyproject_not_found_raises(self, tmp_path) -> None:
        missing = tmp_path / "missing" / "pyproject.toml"
        with pytest.raises(ConfigError, match="not found"):
            load_hook_registry(missing)

    def test_returns_tuple_not_list(self, tmp_path) -> None:
        p = _write_pyproject(
            tmp_path,
            '[tool.sdlc.hooks]\npre_write = ["naming_validator"]\n',
        )
        result = load_hook_registry(p)
        assert isinstance(result, tuple)
