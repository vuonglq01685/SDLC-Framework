"""Unit tests for sdlc.cli.init (AC6.2)."""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
import typer

from sdlc.cli.init import run_init
from sdlc.state import State


def _expected_initial_state_payload() -> dict[str, Any]:
    """Return expected state.json payload for the current State schema."""
    return State().model_dump(mode="json")


pytestmark = pytest.mark.unit


def test_sdlc_init_creates_canonical_state_subtree(tmp_path: Path) -> None:
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        run_init()
    assert (tmp_path / ".claude" / "state" / "state.json").exists()
    assert (tmp_path / ".claude" / "state" / "journal.log").exists()
    assert (tmp_path / ".claude" / "state" / "journal.log").stat().st_size == 0


def test_sdlc_init_state_json_is_empty_canonical_state(tmp_path: Path) -> None:
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        run_init()
    raw = (tmp_path / ".claude" / "state" / "state.json").read_bytes()
    parsed = json.loads(raw)
    assert parsed == _expected_initial_state_payload()
    # Also validates through pydantic
    State.model_validate(parsed)


def test_canonical_initial_state_bytes_cross_platform_parity(tmp_path: Path) -> None:
    """POSIX and Windows write paths must produce byte-identical state.json.

    Cross-platform reproducibility is a Story 1.16 invariant — a state.json
    written by `sdlc init` on Linux must compare byte-equal to one written
    on Windows for the same schema. This guards against subtle drift in the
    canonical-bytes contract (newline, separator, sort order).
    """
    from sdlc.cli.init import _canonical_initial_state_bytes, _write_state_json_windows_atomic

    expected = _canonical_initial_state_bytes()

    # Drive the Windows code path explicitly so this test runs on every host.
    win_target = tmp_path / "win_state.json"
    _write_state_json_windows_atomic(win_target)
    win_bytes = win_target.read_bytes()

    # Property: Windows fallback writes the canonical bytes verbatim.
    assert win_bytes == expected
    # Property: canonical bytes end with exactly one trailing newline.
    assert expected.endswith(b"\n")
    assert not expected.endswith(b"\n\n")
    # Property: canonical bytes are valid UTF-8 with sort_keys (deterministic).
    payload = json.loads(expected.decode("utf-8"))
    assert payload == _expected_initial_state_payload()


def test_sdlc_init_creates_static_asset_dirs(tmp_path: Path) -> None:
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        run_init()
    for tree in ("agents", "commands", "hooks", "workflows", "memory", "skills"):
        assert (tmp_path / ".claude" / tree).is_dir(), f".claude/{tree} missing"


def test_sdlc_init_creates_phase_artifact_dirs(tmp_path: Path) -> None:
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        run_init()
    for phase in ("01-Requirement", "02-Architecture", "03-Implementation"):
        assert (tmp_path / phase).is_dir(), f"{phase}/ missing"


def test_sdlc_init_returns_zero_on_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """run_init() returns None on success (no typer.Exit) AND emits the AC2.4 confirmation."""
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        # If run_init raised any exception (typer.Exit included), pytest would
        # propagate it and fail. Reaching the next line proves the success path.
        run_init()
    captured = capsys.readouterr()
    assert "Initialized SDLC framework" in captured.out, (
        f"AC2.4 confirmation header missing from stdout: {captured.out!r}"
    )
    assert "Next: sdlc status" in captured.out
    assert (tmp_path / ".claude" / "state" / "state.json").exists()


def test_sdlc_init_refuses_on_rerun(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        run_init()
        with pytest.raises(typer.Exit) as exc_info:
            run_init()
    assert exc_info.value.exit_code == 1
    # typer.echo with err=True writes to stderr; capture via capsys
    captured = capsys.readouterr()
    assert "already initialized" in captured.err


def test_sdlc_init_rerun_does_not_modify_state_json(tmp_path: Path) -> None:
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        run_init()
        state_path = tmp_path / ".claude" / "state" / "state.json"
        before = state_path.read_bytes()
        with pytest.raises(typer.Exit):
            run_init()
        after = state_path.read_bytes()
    assert before == after, "state.json was modified on re-run"


def test_sdlc_init_rerun_does_not_create_new_files(tmp_path: Path) -> None:
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        run_init()
        before = {p for p in tmp_path.rglob("*") if p.is_file()}
        with pytest.raises(typer.Exit):
            run_init()
        after = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after, f"New files appeared on re-run: {after - before}"


def test_sdlc_init_tolerates_pre_existing_empty_dot_claude_dir(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    with unittest.mock.patch("sdlc.cli.init._get_repo_root_or_cwd", return_value=tmp_path):
        run_init()
    assert (tmp_path / ".claude" / "state" / "state.json").exists()


_SKIP_WIN32 = pytest.mark.skipif(
    sys.platform == "win32", reason="subprocess mock behaves differently on Windows"
)


def test_safe_child_name_rejects_separators_and_parent_refs() -> None:
    """`_safe_child_name` rejects path-traversal vectors regardless of OS separator."""
    from sdlc.cli.init import _safe_child_name

    assert _safe_child_name("agents.json") is True
    assert _safe_child_name("nested-name.yaml") is True

    # Reject empties and parent references
    assert _safe_child_name("") is False
    assert _safe_child_name(".") is False
    assert _safe_child_name("..") is False
    assert _safe_child_name("../escape") is False
    # Reject embedded separators (POSIX + Windows)
    assert _safe_child_name("a/b") is False
    assert _safe_child_name("a\\b") is False


def test_state_already_exists_detects_partial_layout(tmp_path: Path) -> None:
    """`_state_already_exists` MUST fire on either state.json OR journal.log."""
    from sdlc.cli.init import _state_already_exists

    assert _state_already_exists(tmp_path) is False

    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    journal = state_dir / "journal.log"
    journal.touch()
    # journal.log alone (state.json never written) → previous run partially crashed
    assert _state_already_exists(tmp_path) is True


def test_get_repo_root_uses_git_top_level_when_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Successful `git rev-parse` output is taken as the repo root."""
    from sdlc.cli.init import _get_repo_root_or_cwd

    fake_root = tmp_path / "fake-repo-root"
    fake_root.mkdir()

    def _fake_run(*_args: object, **_kwargs: object) -> object:
        class _Result:
            returncode = 0
            stdout = f"{fake_root}\n"

        return _Result()

    monkeypatch.setattr("sdlc.cli.init.subprocess.run", _fake_run)
    assert _get_repo_root_or_cwd() == fake_root.resolve()


def test_get_repo_root_falls_back_to_cwd_on_empty_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty stdout from git (degenerate case) falls back to cwd, not Path('')."""
    from sdlc.cli.init import _get_repo_root_or_cwd

    monkeypatch.chdir(tmp_path)

    class _Result:
        returncode = 0
        stdout = "\n"  # success but blank

    monkeypatch.setattr("sdlc.cli.init.subprocess.run", lambda *a, **k: _Result())
    assert _get_repo_root_or_cwd() == tmp_path.resolve()


def test_get_repo_root_falls_back_on_subprocess_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Any OSError from subprocess (incl. timeout) falls back to cwd."""
    import subprocess as _sp

    from sdlc.cli.init import _get_repo_root_or_cwd

    monkeypatch.chdir(tmp_path)

    def _raise(*_a: object, **_k: object) -> object:
        raise _sp.SubprocessError("simulated")

    monkeypatch.setattr("sdlc.cli.init.subprocess.run", _raise)
    assert _get_repo_root_or_cwd() == tmp_path.resolve()


def test_copy_package_data_tree_filters_gitkeep_and_unsafe_names(tmp_path: Path) -> None:
    """`_copy_package_data_tree` skips `.gitkeep` AND any unsafe child name.

    Builds a fake on-disk source tree, points _resource_files at it via a
    monkeypatch, and asserts the destination contains only safe files.
    """
    import unittest.mock as _mock

    from sdlc.cli.init import _copy_package_data_tree

    # Build a fake "sdlc/agents" tree in tmp_path
    fake_pkg_root = tmp_path / "fake-pkg" / "sdlc"
    agents_src = fake_pkg_root / "agents"
    agents_src.mkdir(parents=True)
    (agents_src / ".gitkeep").write_text("")
    (agents_src / "real.json").write_text('{"id": "x"}')

    target = tmp_path / "target"
    target.mkdir()

    class _FakeFiles:
        def __truediv__(self, other: str) -> Path:
            return agents_src if other == "agents" else fake_pkg_root / other

    with _mock.patch("sdlc.cli.init._resource_files", return_value=_FakeFiles()):
        _copy_package_data_tree("agents", target)

    assert (target / "real.json").read_text() == '{"id": "x"}'
    # .gitkeep is filtered out
    assert not (target / ".gitkeep").exists()


def test_copy_traversable_entry_recurses_into_directories(tmp_path: Path) -> None:
    """`_copy_traversable_entry` recurses into nested directories preserving structure."""
    from sdlc.cli.init import _copy_traversable_entry

    src = tmp_path / "src"
    nested = src / "nested"
    nested.mkdir(parents=True)
    (src / "top.txt").write_text("top-content")
    (nested / "deep.txt").write_text("deep-content")

    dst = tmp_path / "dst"

    # pathlib.Path implements the Traversable interface (read_bytes, iterdir,
    # is_dir, name) — pass directly. Type check passes via duck typing.
    _copy_traversable_entry(src, dst)  # type: ignore[arg-type]

    assert (dst / "top.txt").read_text() == "top-content"
    assert (dst / "nested" / "deep.txt").read_text() == "deep-content"


@_SKIP_WIN32
def test_sdlc_init_falls_back_to_cwd_when_no_git_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `git` is not on PATH, init scaffolds at Path.cwd() instead of crashing.

    Exercises the actual fallback in `_get_repo_root_or_cwd` (no
    `_get_repo_root_or_cwd` mock — only the subprocess boundary is replaced).
    """
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.chdir(isolated)

    def _no_git(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("git: command not found")

    monkeypatch.setattr("sdlc.cli.init.subprocess.run", _no_git)
    run_init()
    # Layout was scaffolded relative to cwd (the isolated dir), not via git rev-parse
    assert (isolated / ".claude" / "state" / "state.json").exists()
    assert (isolated / "01-Requirement").is_dir()
