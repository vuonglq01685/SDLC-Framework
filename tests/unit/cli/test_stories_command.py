"""Unit-style CLI tests for ``sdlc stories`` (Story 2A.11, Task 5.1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()


def _product_body() -> str:
    return (
        "---\nschema_version: 1\nkind: product_brief\ntitle: Test\n---\n# Product Brief\n\nBody.\n"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_stories_happy_after_epics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    (req / "01-PRODUCT.md").write_text(_product_body(), encoding="utf-8")

    with patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path):
        r1 = _runner.invoke(app, ["epics"])
    assert r1.exit_code == 0, r1.stderr + r1.stdout

    with patch("sdlc.cli.stories._get_repo_root_or_cwd", return_value=tmp_path):
        r2 = _runner.invoke(app, ["stories", "EPIC-sdlc-mock-a"])
    assert r2.exit_code == 0, r2.stderr + r2.stdout

    sdir = req / "05-Stories" / "EPIC-sdlc-mock-a"
    files = sorted(p.name for p in sdir.glob("EPIC-*-S*.json"))
    assert len(files) == 2

    journal = tmp_path / ".claude" / "state" / "journal.log"
    entries = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
    ]
    kinds = [e["kind"] for e in entries]
    assert kinds.count("agent_dispatched") >= 2
    assert kinds.count("artifact_written") >= 5


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_stories_epic_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    (req / "01-PRODUCT.md").write_text(_product_body(), encoding="utf-8")

    with patch("sdlc.cli.stories._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["stories", "EPIC-missing-epic"])
    assert r.exit_code == 1
