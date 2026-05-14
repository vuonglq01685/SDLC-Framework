"""Signoff gate for ``sdlc epics`` / ``sdlc stories`` (Story 2A.11, Task 4.2 / 5)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.signoff.states import SignoffState

pytestmark = pytest.mark.unit

_runner = CliRunner()


def _product_body() -> str:
    return (
        "---\nschema_version: 1\nkind: product_brief\ntitle: Test\n---\n# Product Brief\n\nBody.\n"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_epics_refuses_when_signoff_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    (req / "01-PRODUCT.md").write_text(_product_body(), encoding="utf-8")

    with (
        patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.cli.epics.compute_state", return_value=SignoffState.APPROVED),
    ):
        r = _runner.invoke(app, ["epics"])
    assert r.exit_code == 1
    assert "phase 1 signoff" in r.stderr.lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_stories_refuses_when_signoff_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    (req / "01-PRODUCT.md").write_text(_product_body(), encoding="utf-8")
    epics = req / "04-Epics"
    epics.mkdir(parents=True, exist_ok=True)
    (epics / "EPIC-x.json").write_text('{"schema_version":1}', encoding="utf-8")

    with (
        patch("sdlc.cli.stories._get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.cli.stories.compute_state", return_value=SignoffState.APPROVED),
    ):
        r = _runner.invoke(app, ["stories", "EPIC-x"])
    assert r.exit_code == 1
