"""Integration tests for Claude Code minimum-version gate (Story 2B.2, AC3).

These tests opt OUT of the pytest auto-bypass (Story 2B.2 D1) by setting
``SDLC_TEST_FORCE_COMPAT_CHECK=1`` so the real ``ensure_claude_code_compatible``
fires against stub ``claude`` scripts on a controlled PATH.

POSIX-only: stub scripts use ``#!/bin/sh`` shebangs which Windows cannot
execute (R8). Windows coverage of the gate is deferred to the unit-test layer
(``tests/unit/cli/test_compat_check.py``) which uses Python-level mocks.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdlc.cli import _compat_check
from sdlc.cli._compat_check import CLAUDE_CODE_MIN_VERSION
from sdlc.cli.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.claude_version_gate,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="R8: stub scripts use POSIX shebangs; Windows coverage via unit tests.",
    ),
]

_runner = CliRunner()


def _write_claude_stub(bin_dir: Path, *, body: str) -> Path:
    script = bin_dir / "claude"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _prepend_path(monkeypatch: pytest.MonkeyPatch, bin_dir: Path) -> None:
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")


@pytest.fixture(autouse=True)
def _enable_claude_version_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt into the real compat-check despite the pytest auto-bypass (Story 2B.2 D1).

    Also clears the per-process lru_cache so each test gets a fresh probe against
    its own stub-PATH (D5: gate is memoized for the CLI invocation lifetime).
    """
    _compat_check._cached_probe.cache_clear()
    monkeypatch.setenv("SDLC_TEST_FORCE_COMPAT_CHECK", "1")


@pytest.mark.claude_version_gate
def test_rejects_claude_below_minimum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_claude_stub(
        bin_dir,
        body='#!/bin/sh\nprintf "%s\\n" "claude 1.5.0 (test-stub)"\n',
    )
    _prepend_path(monkeypatch, bin_dir)

    # Use a dispatch subcommand so the gate runs per D2 carve-out.
    result = _runner.invoke(app, ["start", "test-idea"])
    assert result.exit_code == 3
    assert "1.5.0" in result.stderr
    assert CLAUDE_CODE_MIN_VERSION in result.stderr


@pytest.mark.claude_version_gate
@pytest.mark.parametrize("version", ["2.0.0", "3.0.0"])
def test_accepts_claude_at_or_above_minimum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: str,
) -> None:
    """R5: positive assertion that the gate ran AND passed (not just `!= 3`)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_claude_stub(
        bin_dir,
        body=f'#!/bin/sh\nprintf "%s\\n" "claude {version} (test-stub)"\n',
    )
    _prepend_path(monkeypatch, bin_dir)

    # Spy on the compat-check call to prove the gate ran without raising.
    call_results: list[str | BaseException] = []
    original = _compat_check.ensure_claude_code_compatible

    def _spy() -> None:
        try:
            original()
            call_results.append("passed")
        except BaseException as exc:
            call_results.append(exc)
            raise

    monkeypatch.setattr(
        "sdlc.cli._compat_check.ensure_claude_code_compatible",
        _spy,
    )

    result = _runner.invoke(app, ["start", "test-idea"])
    # R5: positive assertion — the gate ran AND returned cleanly.
    assert call_results == ["passed"]
    # R5: subcommand body subsequently ran (its error is what surfaces, not the gate's).
    assert result.exit_code != 3
    assert "requires" not in result.stderr


@pytest.mark.claude_version_gate
def test_claude_absent_from_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    # Use a dispatch subcommand so the gate runs per D2 carve-out.
    result = _runner.invoke(app, ["start", "test-idea"])
    assert result.exit_code == 3
    assert "claude not found on PATH" in result.stderr
    # R7: docs URL must be visible in the plain-text stderr (not just JSON details).
    assert "docs.anthropic.com" in result.stderr


@pytest.mark.claude_version_gate
def test_unparseable_claude_version_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_claude_stub(
        bin_dir,
        body='#!/bin/sh\nprintf "%s\\n" "claude-code unknown build"\n',
    )
    _prepend_path(monkeypatch, bin_dir)

    # Use a dispatch subcommand so the gate runs per D2 carve-out.
    result = _runner.invoke(app, ["start", "test-idea"])
    assert result.exit_code == 3
    assert "could not parse claude version" in result.stderr
