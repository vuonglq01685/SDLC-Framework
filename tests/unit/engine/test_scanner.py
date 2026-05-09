"""Unit tests for engine.scanner.scan — cross-platform (Story 1.15)."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

from sdlc.engine.scanner import scan
from sdlc.errors import StateError
from sdlc.state.model import State

pytestmark = pytest.mark.unit


def _state_bytes(s: State) -> bytes:
    return json.dumps(
        s.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _epic_dir(root: Path) -> Path:
    d = root / "01-Requirement" / "04-Epics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stories_dir(root: Path, epic: str) -> Path:
    d = root / "01-Requirement" / "05-Stories" / epic
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tasks_dir(root: Path, story: str) -> Path:
    d = root / "03-Implementation" / "tasks" / story
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_json(path: Path, data: dict) -> None:  # type: ignore[type-arg]
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Empty / missing project
# ---------------------------------------------------------------------------


def test_scan_returns_empty_state_on_empty_project(tmp_path: Path) -> None:
    result = scan(tmp_path)
    assert result.model_dump(mode="json") == State(
        schema_version=1, next_monotonic_seq=0, phase=1, epics={}, stories={}, tasks={}
    ).model_dump(mode="json")


def test_scan_returns_empty_state_when_artifact_dirs_missing(tmp_path: Path) -> None:
    result = scan(tmp_path)
    assert result.epics == {}
    assert result.stories == {}
    assert result.tasks == {}


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_scan_raises_on_relative_project_root() -> None:
    with pytest.raises(StateError) as exc_info:
        scan(Path("relative/path"))
    assert exc_info.value.details["reason"] == "not_absolute"


def test_scan_raises_when_project_root_is_a_file(tmp_path: Path) -> None:
    tmp_file = tmp_path / "x"
    tmp_file.write_text("data", encoding="utf-8")
    with pytest.raises(StateError) as exc_info:
        scan(tmp_file)
    assert exc_info.value.details["reason"] == "not_a_directory"


def test_scan_raises_when_project_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(StateError) as exc_info:
        scan(missing)
    assert exc_info.value.details["reason"] == "not_found"
    assert exc_info.value.details["path"] == str(missing)


def test_scan_raises_on_malformed_json(tmp_path: Path) -> None:
    _epic_dir(tmp_path).joinpath("EPIC-bad.json").write_text("not valid json{", encoding="utf-8")
    with pytest.raises(StateError) as exc_info:
        scan(tmp_path)
    assert exc_info.value.details["reason"] == "malformed_artifact"
    # AC1 contract: file is a relative path under project_root, not absolute.
    assert exc_info.value.details["file"] == str(
        Path("01-Requirement") / "04-Epics" / "EPIC-bad.json"
    )


def test_scan_raises_on_non_object_json(tmp_path: Path) -> None:
    _epic_dir(tmp_path).joinpath("EPIC-list.json").write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(StateError) as exc_info:
        scan(tmp_path)
    assert exc_info.value.details["reason"] == "non_object_artifact"


def test_scan_raises_on_non_utf8_artifact(tmp_path: Path) -> None:
    """Latin-1 byte 0xf1 (ñ) without UTF-8 wrapping must surface as StateError."""
    epic_d = _epic_dir(tmp_path)
    (epic_d / "EPIC-bad.json").write_bytes(b'{"id":"EPIC-bad","x":"\xf1ame"}')
    with pytest.raises(StateError) as exc_info:
        scan(tmp_path)
    assert exc_info.value.details["reason"] == "non_utf8_artifact"
    assert exc_info.value.details["file"] == str(
        Path("01-Requirement") / "04-Epics" / "EPIC-bad.json"
    )


def test_scan_accepts_utf8_bom_artifact(tmp_path: Path) -> None:
    """Notepad/Windows-saved JSON with UTF-8 BOM must parse cleanly."""
    epic_d = _epic_dir(tmp_path)
    payload = json.dumps({"id": "EPIC-bom", "title": "héllo"}, ensure_ascii=False)
    (epic_d / "EPIC-bom.json").write_bytes(b"\xef\xbb\xbf" + payload.encode("utf-8"))
    result = scan(tmp_path)
    assert "EPIC-bom" in result.epics
    assert result.epics["EPIC-bom"]["title"] == "héllo"


# ---------------------------------------------------------------------------
# Canonical sort order
# ---------------------------------------------------------------------------


def test_scan_loads_epics_in_canonical_sort_order(tmp_path: Path) -> None:
    epic_d = _epic_dir(tmp_path)
    for slug in ("charlie", "alpha", "bravo"):
        _write_json(epic_d / f"EPIC-{slug}.json", {"id": f"EPIC-{slug}", "title": slug})
    result = scan(tmp_path)
    assert list(result.epics.keys()) == ["EPIC-alpha", "EPIC-bravo", "EPIC-charlie"]


def test_scan_loads_stories_under_epic_subdirs(tmp_path: Path) -> None:
    _write_json(_epic_dir(tmp_path) / "EPIC-alpha.json", {"id": "EPIC-alpha"})
    sdir = _stories_dir(tmp_path, "EPIC-alpha")
    # Write S02 first, then S01, so the canonical-sort order assertion
    # genuinely exercises sort behaviour rather than insertion order.
    _write_json(sdir / "EPIC-alpha-S02-y.json", {"id": "EPIC-alpha-S02-y"})
    _write_json(sdir / "EPIC-alpha-S01-x.json", {"id": "EPIC-alpha-S01-x"})
    result = scan(tmp_path)
    assert set(result.stories.keys()) == {"EPIC-alpha-S01-x", "EPIC-alpha-S02-y"}
    assert list(result.stories.keys()) == ["EPIC-alpha-S01-x", "EPIC-alpha-S02-y"]


def test_scan_loads_tasks_under_story_subdirs(tmp_path: Path) -> None:
    _write_json(_epic_dir(tmp_path) / "EPIC-alpha.json", {"id": "EPIC-alpha"})
    _write_json(
        _stories_dir(tmp_path, "EPIC-alpha") / "EPIC-alpha-S01-x.json",
        {"id": "EPIC-alpha-S01-x"},
    )
    tdir = _tasks_dir(tmp_path, "EPIC-alpha-S01-x")
    _write_json(tdir / "EPIC-alpha-S01-x-T01-init.json", {"id": "EPIC-alpha-S01-x-T01-init"})
    _write_json(tdir / "EPIC-alpha-S01-x-T02-run.json", {"id": "EPIC-alpha-S01-x-T02-run"})
    result = scan(tmp_path)
    assert set(result.tasks.keys()) == {
        "EPIC-alpha-S01-x-T01-init",
        "EPIC-alpha-S01-x-T02-run",
    }


# ---------------------------------------------------------------------------
# Skipping behaviour
# ---------------------------------------------------------------------------


def test_scan_skips_foreign_filenames_with_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_json(_epic_dir(tmp_path) / "EPIC-good.json", {"id": "EPIC-good"})
    (_epic_dir(tmp_path) / "random.json").write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="sdlc.engine.scanner"):
        result = scan(tmp_path)
    assert list(result.epics.keys()) == ["EPIC-good"]
    assert any("random.json" in r.message for r in caplog.records)


def test_scan_skips_hidden_files(tmp_path: Path) -> None:
    _write_json(_epic_dir(tmp_path) / "EPIC-real.json", {"id": "EPIC-real"})
    (_epic_dir(tmp_path) / ".DS_Store").write_text("{}", encoding="utf-8")
    result = scan(tmp_path)
    assert list(result.epics.keys()) == ["EPIC-real"]


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink creation requires admin / developer-mode on Windows",
)
def test_scan_logs_broken_symlinks_at_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC2: broken symlinks are skipped silently and logged at INFO."""
    epic_d = _epic_dir(tmp_path)
    _write_json(epic_d / "EPIC-real.json", {"id": "EPIC-real"})
    broken = epic_d / "EPIC-broken.json"
    broken.symlink_to(epic_d / "does-not-exist.json")
    with caplog.at_level(logging.INFO, logger="sdlc.engine.scanner"):
        result = scan(tmp_path)
    assert list(result.epics.keys()) == ["EPIC-real"]
    assert any(
        "broken symlink" in r.message and "EPIC-broken.json" in r.message for r in caplog.records
    )


def test_scan_skips_non_json_files(tmp_path: Path) -> None:
    _write_json(_epic_dir(tmp_path) / "EPIC-real.json", {"id": "EPIC-real"})
    (_epic_dir(tmp_path) / "EPIC-text.txt").write_text("{}", encoding="utf-8")
    result = scan(tmp_path)
    assert list(result.epics.keys()) == ["EPIC-real"]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_scan_is_idempotent_byte_equal(tmp_path: Path) -> None:
    epic_d = _epic_dir(tmp_path)
    for slug in ("alpha", "bravo"):
        _write_json(epic_d / f"EPIC-{slug}.json", {"id": f"EPIC-{slug}", "title": slug})
    sdir = _stories_dir(tmp_path, "EPIC-alpha")
    _write_json(sdir / "EPIC-alpha-S01-boot.json", {"id": "EPIC-alpha-S01-boot"})
    tdir = _tasks_dir(tmp_path, "EPIC-alpha-S01-boot")
    _write_json(tdir / "EPIC-alpha-S01-boot-T01-go.json", {"id": "EPIC-alpha-S01-boot-T01-go"})

    s1 = scan(tmp_path)
    s2 = scan(tmp_path)
    assert _state_bytes(s1) == _state_bytes(s2)


# ---------------------------------------------------------------------------
# Defensive: PermissionError + symlink sandbox (Story 1.16 review patches P6, P15)
# ---------------------------------------------------------------------------


def test_walk_dir_returns_empty_on_iterdir_permission_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_walk_dir_sorted` returns [] and logs WARNING when iterdir raises PermissionError."""
    import re as _re

    from sdlc.engine.scanner import _walk_dir_sorted

    epic_d = _epic_dir(tmp_path)
    _write_json(epic_d / "EPIC-x.json", {"id": "EPIC-x"})

    real_iterdir = Path.iterdir

    def _denied(self: Path) -> object:
        if self == epic_d:
            raise PermissionError("simulated denial")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", _denied)
    with caplog.at_level(logging.WARNING, logger="sdlc.engine.scanner"):
        result = _walk_dir_sorted(epic_d, _re.compile(r".*"), tmp_path)
    assert result == []
    assert any("cannot enumerate" in r.message for r in caplog.records)


def test_load_nested_artifacts_returns_empty_on_iterdir_permission_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_load_nested_artifacts` survives a PermissionError on the parent directory."""
    sdir = _stories_dir(tmp_path, "EPIC-alpha")
    _write_json(sdir / "EPIC-alpha-S01-boot.json", {"id": "EPIC-alpha-S01-boot"})

    parent = tmp_path / "01-Requirement" / "05-Stories"
    real_iterdir = Path.iterdir

    def _denied(self: Path) -> object:
        if self == parent:
            raise PermissionError("simulated denial")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", _denied)
    with caplog.at_level(logging.WARNING, logger="sdlc.engine.scanner"):
        result = scan(tmp_path)
    # Stories sub-tree is unreadable → empty stories dict, but scan completes.
    assert result.stories == {}
    assert any("cannot enumerate" in r.message for r in caplog.records)


def test_is_inside_returns_false_on_resolve_oserror(tmp_path: Path) -> None:
    """`_is_inside` returns False (not raise) when path.resolve() raises OSError."""
    from unittest import mock

    from sdlc.engine.scanner import _is_inside

    p = tmp_path / "victim.json"
    p.touch()
    with mock.patch.object(Path, "resolve", side_effect=OSError("simulated")):
        assert _is_inside(p, tmp_path) is False


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink creation requires admin / developer-mode on Windows",
)
def test_scan_rejects_symlink_artifact_resolving_outside_project_root(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """P15: artifact symlink that resolves outside project_root is skipped + logged."""
    epic_d = _epic_dir(tmp_path)
    _write_json(epic_d / "EPIC-real.json", {"id": "EPIC-real"})

    # Create a target outside project_root and symlink it inside the epics dir
    outside = tmp_path.parent / "outside-secrets.json"
    outside.write_text(json.dumps({"id": "EPIC-leak", "secret": "leaked"}))
    leak = epic_d / "EPIC-leak.json"
    leak.symlink_to(outside)

    with caplog.at_level(logging.WARNING, logger="sdlc.engine.scanner"):
        result = scan(tmp_path)
    assert list(result.epics.keys()) == ["EPIC-real"]
    assert any(
        "resolves outside project_root" in r.message and "EPIC-leak.json" in r.message
        for r in caplog.records
    )
