"""Integration test: `sdlc init --adopt` never modifies the source tree (Story 3.1, AC7).

3.1-scoped guarantee: after a full `sdlc init --adopt` on a minimal brownfield repo,
`git status --porcelain` reports changes ONLY under `.claude/`. The exhaustive
multi-fixture porcelain + tree-hash property + mutation gate is Story 3.7; this is the
single-fixture smoke proof for the orchestrator skeleton.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

if sys.platform == "win32":  # pragma: no cover - adopt journals via POSIX-only writer
    pytest.skip("adopt mode is POSIX-only in v1 (ADR-034)", allow_module_level=True)

pytestmark = pytest.mark.integration

_runner = CliRunner()


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.fixture
def brownfield_repo(tmp_path: Path) -> Path:
    """A committed git repo with a minimal pre-existing source tree."""
    if shutil.which("git") is None:  # pragma: no cover - git always present in CI
        pytest.skip("git not on PATH")
    root = tmp_path / "proj"
    root.mkdir()
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "README.md").write_text("# Existing project\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "initial"], root)
    return root


def test_adopt_does_not_touch_source_tree(
    brownfield_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli.main import app

    monkeypatch.chdir(brownfield_repo)
    result = _runner.invoke(app, ["init", "--adopt"])
    assert result.exit_code == 0, result.output

    porcelain = _git(["status", "--porcelain"], brownfield_repo).stdout
    changed_paths = [line[3:] for line in porcelain.splitlines() if line.strip()]
    assert changed_paths, "expected adopt to create .claude/ artifacts"
    offenders = [p for p in changed_paths if not p.startswith(".claude/")]
    assert offenders == [], f"adopt modified paths outside .claude/: {offenders}"


def test_adopt_writes_adopt_report(brownfield_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.cli.main import app

    monkeypatch.chdir(brownfield_repo)
    result = _runner.invoke(app, ["init", "--adopt"])
    assert result.exit_code == 0, result.output
    report_path = brownfield_repo / ".claude" / "state" / "adopt-report.json"
    assert report_path.exists()


def test_adopt_no_longer_reports_unimplemented(
    brownfield_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli.main import app

    monkeypatch.chdir(brownfield_repo)
    result = _runner.invoke(app, ["init", "--adopt"])
    assert "not implemented" not in result.output.lower()
