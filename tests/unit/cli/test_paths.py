"""Unit tests for sdlc.cli._paths.get_repo_root_or_cwd (Story 1.17 review)."""

from __future__ import annotations

import subprocess as _sp
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_get_repo_root_uses_git_top_level(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Successful `git rev-parse` output is taken as the repo root."""
    from sdlc.cli._paths import get_repo_root_or_cwd

    fake_root = tmp_path / "fake-repo"
    fake_root.mkdir()

    class _Result:
        returncode = 0
        stdout = f"{fake_root}\n"

    monkeypatch.setattr("sdlc.cli._paths.subprocess.run", lambda *a, **k: _Result())
    assert get_repo_root_or_cwd() == fake_root.resolve()


def test_get_repo_root_falls_back_on_subprocess_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SubprocessError (incl. timeout) falls back to cwd."""
    from sdlc.cli._paths import get_repo_root_or_cwd

    monkeypatch.chdir(tmp_path)

    def _raise(*_a: object, **_k: object) -> object:
        raise _sp.SubprocessError("simulated")

    monkeypatch.setattr("sdlc.cli._paths.subprocess.run", _raise)
    assert get_repo_root_or_cwd() == tmp_path.resolve()


def test_get_repo_root_falls_back_on_empty_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty stdout from git (degenerate case) falls back to cwd, not Path('')."""
    from sdlc.cli._paths import get_repo_root_or_cwd

    monkeypatch.chdir(tmp_path)

    class _Result:
        returncode = 0
        stdout = "\n"  # success but blank

    monkeypatch.setattr("sdlc.cli._paths.subprocess.run", lambda *a, **k: _Result())
    assert get_repo_root_or_cwd() == tmp_path.resolve()


def test_get_repo_root_falls_back_on_nonzero_returncode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Non-zero git returncode (cwd outside any repo) falls back to cwd."""
    from sdlc.cli._paths import get_repo_root_or_cwd

    monkeypatch.chdir(tmp_path)

    class _Result:
        returncode = 128
        stdout = ""

    monkeypatch.setattr("sdlc.cli._paths.subprocess.run", lambda *a, **k: _Result())
    assert get_repo_root_or_cwd() == tmp_path.resolve()


def test_get_repo_root_falls_back_on_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Generic OSError (e.g. ENOENT for git binary) falls back to cwd."""
    from sdlc.cli._paths import get_repo_root_or_cwd

    monkeypatch.chdir(tmp_path)

    def _raise(*_a: object, **_k: object) -> object:
        raise OSError("git not found")

    monkeypatch.setattr("sdlc.cli._paths.subprocess.run", _raise)
    assert get_repo_root_or_cwd() == tmp_path.resolve()
