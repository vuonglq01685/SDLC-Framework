"""Integration tests for ``sdlc epics`` (Story 2A.11 Task 7.1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.integration

_runner = CliRunner()


def _product_body() -> str:
    return (
        "---\nschema_version: 1\nkind: product_brief\ntitle: Test\n---\n# Product Brief\n\nBody.\n"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_epics_writes_three_files_and_per_file_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    (req / "01-PRODUCT.md").write_text(_product_body(), encoding="utf-8")

    with patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["epics"])
    assert result.exit_code == 0, result.stderr + result.stdout

    epics_dir = req / "04-Epics"
    files = sorted(p.name for p in epics_dir.glob("EPIC-*.json"))
    assert files == [
        "EPIC-sdlc-mock-a.json",
        "EPIC-sdlc-mock-b.json",
        "EPIC-sdlc-mock-c.json",
    ]

    entries = [
        json.loads(line)
        for line in (tmp_path / ".claude" / "state" / "journal.log")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    agent_dispatched = [e for e in entries if e.get("kind") == "agent_dispatched"]
    artifact_written = [e for e in entries if e.get("kind") == "artifact_written"]
    assert len(agent_dispatched) == 1
    assert len(artifact_written) == 3
