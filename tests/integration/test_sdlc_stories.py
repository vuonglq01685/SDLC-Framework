"""Integration tests for ``sdlc stories`` (Story 2A.11 Task 7.2)."""

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
def test_sdlc_stories_writes_epic_scoped_story_files(
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
        epics_run = _runner.invoke(app, ["epics"])
    assert epics_run.exit_code == 0, epics_run.stderr + epics_run.stdout

    with patch("sdlc.cli.stories._get_repo_root_or_cwd", return_value=tmp_path):
        stories_run = _runner.invoke(app, ["stories", "EPIC-sdlc-mock-a"])
    assert stories_run.exit_code == 0, stories_run.stderr + stories_run.stdout

    stories_dir = req / "05-Stories" / "EPIC-sdlc-mock-a"
    story_files = sorted(p.name for p in stories_dir.glob("EPIC-sdlc-mock-a-S*.json"))
    assert story_files == [
        "EPIC-sdlc-mock-a-S01-mock-story-one.json",
        "EPIC-sdlc-mock-a-S02-mock-story-two.json",
    ]

    entries = [
        json.loads(line)
        for line in (tmp_path / ".claude" / "state" / "journal.log")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    artifact_written = [e for e in entries if e.get("kind") == "artifact_written"]
    assert len(artifact_written) >= 5
