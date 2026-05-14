"""Tier-2 e2e for ``sdlc epics`` + ``sdlc stories`` (Story 2A.11 AC10)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.signoff.states import SignoffState

pytestmark = pytest.mark.e2e

_runner = CliRunner()


def _product_body() -> str:
    return (
        "---\nschema_version: 1\nkind: product_brief\ntitle: Test\n---\n# Product Brief\n\nBody.\n"
    )


def _init_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    (req / "01-PRODUCT.md").write_text(_product_body(), encoding="utf-8")
    return req


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_epics_then_stories_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _init_repo(tmp_path, monkeypatch)

    with patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path):
        r_epics = _runner.invoke(app, ["epics"])
    assert r_epics.exit_code == 0, r_epics.stderr + r_epics.stdout

    with patch("sdlc.cli.stories._get_repo_root_or_cwd", return_value=tmp_path):
        r_stories = _runner.invoke(app, ["stories", "EPIC-sdlc-mock-a"])
    assert r_stories.exit_code == 0, r_stories.stderr + r_stories.stdout

    stories = sorted(
        p.name for p in (req / "05-Stories" / "EPIC-sdlc-mock-a").glob("EPIC-sdlc-mock-a-S*.json")
    )
    assert len(stories) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_epics_schema_invalid_refused_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patch #14: schema-invalid path is now exercised end-to-end by overriding
    the v1 mock body with malformed JSON. The real parser fires and surfaces
    ``ERR_EPIC_SCHEMA_INVALID``; the SUT is not stubbed."""
    req = _init_repo(tmp_path, monkeypatch)
    epics_dir = req / "04-Epics"

    from sdlc.cli import _epics_pipeline as _pipeline

    monkeypatch.setattr(_pipeline, "mock_epics_body", lambda: '{"id": "not-an-array"}')

    with patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["epics"])
    assert r.exit_code == 1
    assert "must be a JSON array" in (r.stderr + r.stdout)
    assert not epics_dir.exists() or not list(epics_dir.glob("EPIC-*.json"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_epics_refused_when_signoff_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path, monkeypatch)

    with (
        patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.cli.epics.compute_state", return_value=SignoffState.APPROVED),
    ):
        r = _runner.invoke(app, ["epics"])
    assert r.exit_code == 1
    assert "phase 1 signoff" in (r.stderr + r.stdout).lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_stories_unknown_epic_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path, monkeypatch)

    with patch("sdlc.cli.stories._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["stories", "EPIC-does-not-exist"])
    assert r.exit_code == 1
    assert "not found at 01-Requirement/04-Epics/" in (r.stderr + r.stdout)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_stories_append_only_seq_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli._epic_story_models import _StoryEntry, serialize_entry

    req = _init_repo(tmp_path, monkeypatch)

    with patch("sdlc.cli.epics._get_repo_root_or_cwd", return_value=tmp_path):
        r_epics = _runner.invoke(app, ["epics"])
    assert r_epics.exit_code == 0, r_epics.stderr + r_epics.stdout

    story_dir = req / "05-Stories" / "EPIC-sdlc-mock-a"
    story_dir.mkdir(parents=True, exist_ok=True)
    existing_1 = story_dir / "EPIC-sdlc-mock-a-S01-existing.json"
    existing_2 = story_dir / "EPIC-sdlc-mock-a-S02-existing.json"
    story1 = _StoryEntry(
        id="EPIC-sdlc-mock-a-S01-existing",
        epic_id="EPIC-sdlc-mock-a",
        seq=1,
        label="Existing story one",
        as_a="user",
        i_want="existing behavior",
        so_that="keep history",
        given_when_then=("Given old\nWhen keep\nThen unchanged",),
        dependencies=(),
        drafted_at="2026-01-01T00:00:00.000Z",
        drafted_by_specialist="story-writer",
    )
    story2 = _StoryEntry(
        id="EPIC-sdlc-mock-a-S02-existing",
        epic_id="EPIC-sdlc-mock-a",
        seq=2,
        label="Existing story two",
        as_a="user",
        i_want="existing behavior",
        so_that="keep history",
        given_when_then=("Given old\nWhen keep\nThen unchanged",),
        dependencies=(),
        drafted_at="2026-01-01T00:00:00.000Z",
        drafted_by_specialist="story-writer",
    )
    existing_1.write_text(serialize_entry(story1), encoding="utf-8")
    existing_2.write_text(serialize_entry(story2), encoding="utf-8")
    before_1 = existing_1.read_bytes()
    before_2 = existing_2.read_bytes()

    with patch("sdlc.cli.stories._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["stories", "EPIC-sdlc-mock-a"])
    assert r.exit_code == 0, r.stderr + r.stdout

    assert existing_1.read_bytes() == before_1
    assert existing_2.read_bytes() == before_2
    assert (story_dir / "EPIC-sdlc-mock-a-S03-mock-story-one.json").is_file()
    assert (story_dir / "EPIC-sdlc-mock-a-S04-mock-story-two.json").is_file()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_stories_refused_when_signoff_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path, monkeypatch)
    req = tmp_path / "01-Requirement" / "04-Epics"
    req.mkdir(parents=True, exist_ok=True)
    (req / "EPIC-x.json").write_text('{"schema_version":1}\n', encoding="utf-8")

    with (
        patch("sdlc.cli.stories._get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.cli.stories.compute_state", return_value=SignoffState.APPROVED),
    ):
        r = _runner.invoke(app, ["stories", "EPIC-x"])
    assert r.exit_code == 1
    assert "phase 1 signoff" in (r.stderr + r.stdout).lower()
