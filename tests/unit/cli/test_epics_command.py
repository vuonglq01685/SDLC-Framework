"""Unit-style CLI tests for ``sdlc epics`` (Story 2A.11, Task 4.1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
def test_epics_happy_writes_three_json_and_journals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    (req / "01-PRODUCT.md").write_text(_product_body(), encoding="utf-8")

    from unittest.mock import patch

    with patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["epics"])
    assert r.exit_code == 0, r.stderr + r.stdout

    epics_dir = req / "04-Epics"
    names = sorted(p.name for p in epics_dir.glob("*.json"))
    assert "EPIC-sdlc-mock-a.json" in names
    assert "EPIC-sdlc-mock-b.json" in names
    assert "EPIC-sdlc-mock-c.json" in names

    journal = tmp_path / ".claude" / "state" / "journal.log"
    entries = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
    ]
    kinds = [e["kind"] for e in entries]
    assert kinds.count("agent_dispatched") == 1
    assert kinds.count("artifact_written") == 3


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_epics_missing_product_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)

    from unittest.mock import patch

    with patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["epics"])
    assert r.exit_code == 1
