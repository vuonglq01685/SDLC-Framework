"""Unit tests for cli/architect.py:run_architect (Story 2A.14, AC1-AC7, AC9)."""

from __future__ import annotations

import contextlib
import sys
import unittest.mock
from pathlib import Path

import pytest
import typer
import yaml
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()

_ARCH_CONTENT_NO_REQUIRES = "## Overview\n\nSystem architecture stub.\n"
_ARCH_CONTENT_WITH_DATABASE = (
    "---\nrequires:\n  - database\n---\n\n## Overview\n\nSystem architecture stub.\n"
)
_ARCH_CONTENT_WITH_TWO_TRACKS = (
    "---\nrequires:\n  - database\n  - security\n---\n\n## Overview\n\nSystem architecture stub.\n"
)
_ARCH_CONTENT_UNKNOWN_TRACK = (
    "---\nrequires:\n  - quantum-computing\n---\n\n## Overview\n\nSystem architecture stub.\n"
)
_SUB_TRACK_CONTENT = "## Database Architecture\n\nDatabase stub.\n"


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _write_product_md(tmp_path: Path, content: str | None = None) -> Path:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = "# Product Brief\n\nA product for testing.\n"
    p.write_text(content, encoding="utf-8")
    return p


def _write_approved_phase1_signoff(tmp_path: Path) -> None:
    """Write a canonical phase-1 signoff record so compute_state returns APPROVED."""
    signoffs_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoffs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "phase": 1,
        "artifacts": [
            {
                "schema_version": 1,
                "path": "01-Requirement/01-PRODUCT.md",
                "hash": "sha256:" + "a" * 64,
            }
        ],
        "approved_by": "test-approver",
        "approved_at": "2026-05-14T10:00:00.000Z",
        "drafted_at": "2026-05-14T09:00:00.000Z",
        "validated_at": "2026-05-14T10:00:00.000Z",
    }
    (signoffs_dir / "phase-1.yaml").write_text(
        yaml.safe_dump(record, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def _make_dispatch_result(output_text: str) -> unittest.mock.MagicMock:
    result = unittest.mock.MagicMock()
    result.outcome = "success"
    result.agent_result.output_text = output_text
    return result


def _invoke_architect(
    tmp_path: Path, *, json_mode: bool = True, mock_postconditions: bool = False
) -> object:
    args = ["--json", "architect"] if json_mode else ["architect"]
    patches: list[object] = [
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
    ]
    if mock_postconditions:
        patches.append(unittest.mock.patch("sdlc.cli.architect.evaluate_postconditions"))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)  # type: ignore[arg-type]
        return _runner.invoke(app, args)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_not_initialized(tmp_path: Path) -> None:
    """AC1: ERR_NOT_INITIALIZED if state.json missing."""
    with unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "architect"])
    assert r.exit_code == 1
    assert "ERR_NOT_INITIALIZED" in (r.stdout + (r.stderr or ""))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_phase1_not_approved(tmp_path: Path) -> None:
    """AC1: ERR_PHASE1_NOT_APPROVED when phase 1 is AWAITING_SIGNOFF."""
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    # No signoff record → AWAITING_SIGNOFF
    r = _invoke_architect(tmp_path)
    assert r.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (r.stdout + (r.stderr or ""))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_phase1_not_approved_no_dispatch_called(tmp_path: Path) -> None:
    """AC1: no dispatch call when phase-1 gate fires."""
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._architect_pipeline.dispatch") as mock_dispatch,
    ):
        r = _runner.invoke(app, ["--json", "architect"])
    assert r.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (r.stdout + (r.stderr or ""))
    mock_dispatch.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_product_md_contains_boundary(tmp_path: Path) -> None:
    """AC5/AC7: ERR_ARTIFACT_CONTAINS_BOUNDARY if 01-PRODUCT.md has boundary marker."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    from sdlc.dispatcher.prompts import BOUNDARY_LINE

    _write_product_md(tmp_path, content=f"# Product\n\n{BOUNDARY_LINE}\n\nContent\n")
    r = _invoke_architect(tmp_path)
    assert r.exit_code == 1
    assert "ERR_ARTIFACT_CONTAINS_BOUNDARY" in (r.stdout + (r.stderr or ""))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_no_sub_tracks(tmp_path: Path) -> None:
    """AC2: no requires → ARCHITECTURE.md written, sub_tracks_dispatched: [], exit 0."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_NO_REQUIRES)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._architect_pipeline.dispatch", return_value=primary_result),
        unittest.mock.patch("sdlc.cli.architect.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    arch = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    assert arch.is_file()
    assert _ARCH_CONTENT_NO_REQUIRES in arch.read_text(encoding="utf-8")

    import json

    out = json.loads(r.stdout)
    assert out["sub_tracks_dispatched"] == []
    assert out["outcome"] == "success"
    assert out["phase"] == 2
    assert out["track"] == "architect"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_no_sub_tracks_dispatch_called_once(tmp_path: Path) -> None:
    """AC9: no sub-tracks → dispatch called exactly once (primary only)."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_NO_REQUIRES)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch(
            "sdlc.cli._architect_pipeline.dispatch", return_value=primary_result
        ) as mock_d,
        unittest.mock.patch("sdlc.cli.architect.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 0
    assert mock_d.call_count == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_one_sub_track(tmp_path: Path) -> None:
    """AC2/AC3: requires: [database] → 2 dispatches, ARCHITECTURE.md + sub-tracks/database.md."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_WITH_DATABASE)
    sub_result = _make_dispatch_result(_SUB_TRACK_CONTENT)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch(
            "sdlc.cli._architect_pipeline.dispatch",
            side_effect=[primary_result, sub_result],
        ) as mock_d,
        unittest.mock.patch("sdlc.cli.architect.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    assert mock_d.call_count == 2

    arch = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    db_track = tmp_path / "02-Architecture" / "02-System" / "sub-tracks" / "database.md"
    assert arch.is_file()
    assert db_track.is_file()
    assert _SUB_TRACK_CONTENT in db_track.read_text(encoding="utf-8")

    import json

    out = json.loads(r.stdout)
    assert out["sub_tracks_dispatched"] == ["database"]
    assert len(out["sub_track_artifacts"]) == 1
    assert out["sub_track_artifacts"][0]["track"] == "database"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_two_sub_tracks(tmp_path: Path) -> None:
    """AC2/AC3: requires: [database, security] → 3 dispatches, 3 files written."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_WITH_TWO_TRACKS)
    sub_db = _make_dispatch_result("## DB\n\nStub.\n")
    sub_sec = _make_dispatch_result("## Security\n\nStub.\n")

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch(
            "sdlc.cli._architect_pipeline.dispatch",
            side_effect=[primary_result, sub_db, sub_sec],
        ) as mock_d,
        unittest.mock.patch("sdlc.cli.architect.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    assert mock_d.call_count == 3

    arch_dir = tmp_path / "02-Architecture" / "02-System"
    assert (arch_dir / "ARCHITECTURE.md").is_file()
    assert (arch_dir / "sub-tracks" / "database.md").is_file()
    assert (arch_dir / "sub-tracks" / "security.md").is_file()

    import json

    out = json.loads(r.stdout)
    assert sorted(out["sub_tracks_dispatched"]) == ["database", "security"]
    assert len(out["sub_track_artifacts"]) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_unknown_sub_track_raises_error(tmp_path: Path) -> None:
    """AC3: requires: [quantum-computing] → error; ARCHITECTURE.md written; no sub-track files."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_UNKNOWN_TRACK)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._architect_pipeline.dispatch", return_value=primary_result),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 1
    output = r.stdout + (r.stderr or "")
    assert "quantum-computing" in output
    # ARCHITECTURE.md IS written (primary dispatch succeeded before validation)
    arch = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    assert arch.is_file()
    # No sub-track files
    sub_dir = tmp_path / "02-Architecture" / "02-System" / "sub-tracks"
    assert not sub_dir.is_dir() or not list(sub_dir.glob("*.md"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_unknown_sub_track_error_contains_sorted_list(tmp_path: Path) -> None:
    """AC3: error message must include sorted available sub-track names."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_UNKNOWN_TRACK)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._architect_pipeline.dispatch", return_value=primary_result),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 1
    output = r.stdout + (r.stderr or "")
    # Must contain the sorted available list
    assert "database" in output
    assert "observability" in output
    assert "security" in output


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_unknown_sub_track_no_sub_track_dispatch_called(tmp_path: Path) -> None:
    """AC3: fail-fast before dispatching any sub-track (no partial output)."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_UNKNOWN_TRACK)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch(
            "sdlc.cli._architect_pipeline.dispatch",
            return_value=primary_result,
        ) as mock_d,
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 1
    # Only primary dispatch was called, no sub-track calls
    assert mock_d.call_count == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sub_track_prompt_uses_compound_builder(tmp_path: Path) -> None:
    """AC7: sub-track prompt builder called with secondary_input=ARCHITECTURE.md content."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_WITH_DATABASE)
    sub_result = _make_dispatch_result(_SUB_TRACK_CONTENT)

    compound_calls: list[dict[str, object]] = []

    def _capture_compound(sp: object, wf: object, **kwargs: object) -> str:
        compound_calls.append(dict(kwargs))
        # Return a minimal valid prompt
        from sdlc.dispatcher.prompts import BOUNDARY_LINE

        return f"<SYSTEM>x</SYSTEM><BOUNDARY>\n{BOUNDARY_LINE}\n</BOUNDARY><USER_IDEA>y</USER_IDEA>"

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch(
            "sdlc.cli._architect_pipeline.dispatch",
            side_effect=[primary_result, sub_result],
        ),
        unittest.mock.patch(
            "sdlc.cli._architect_pipeline.phase1_compound_prompt_builder",
            side_effect=_capture_compound,
        ),
        unittest.mock.patch("sdlc.cli.architect.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    # compound_builder must have been called for the sub-track
    assert len(compound_calls) >= 1
    call = compound_calls[0]
    # AC7: secondary_input must be the FULL ARCHITECTURE.md re-read from disk —
    # frontmatter included — not a substring and not the raw output_text.
    assert call["secondary_input"] == _ARCH_CONTENT_WITH_DATABASE
    # AC7: primary_input is the product brief; labels pin the compound shape.
    assert "primary_input" in call
    assert call["primary_label"] == "PRODUCT_BRIEF"
    assert call["secondary_label"] == "SYSTEM_ARCHITECTURE"
    assert call["role"] == "primary"
