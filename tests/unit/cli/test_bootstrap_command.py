"""Unit tests for cli/bootstrap.py:run_bootstrap (Story 2A.15, AC1-AC2, AC5-AC6, AC8)."""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from sdlc.cli._bootstrap_pipeline import _validate_bootstrap_record
from sdlc.cli.main import app
from sdlc.errors import WorkflowError

pytestmark = pytest.mark.unit

_runner = CliRunner()

_PRODUCT_CONTENT = "# Product Brief\n\n## Overview\n\nA product for testing.\n"
_ARCH_CONTENT = "# System Architecture\n\n## Overview\n\nSystem architecture stub.\n"

_MOCK_RECORDS_2 = json.dumps(
    [
        {"path": "src/__init__.py", "content": "# placeholder\n"},
        {"path": "tests/.gitkeep", "content": ""},
    ]
)
_MOCK_RECORDS_3 = json.dumps(
    [
        {"path": "src/__init__.py", "content": "# placeholder\n"},
        {"path": "tests/.gitkeep", "content": ""},
        {"path": "tests/conftest.py", "content": "# conftest\n"},
    ]
)


def _init_repo(tmp_path: Path) -> None:
    import typer

    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _write_product_md(tmp_path: Path, content: str | None = None) -> Path:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if content is not None else _PRODUCT_CONTENT, encoding="utf-8")
    return p


def _write_arch_md(tmp_path: Path, content: str | None = None) -> Path:
    p = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if content is not None else _ARCH_CONTENT, encoding="utf-8")
    return p


def _write_approved_signoff(tmp_path: Path, phase: int) -> None:
    signoffs_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoffs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "phase": phase,
        "artifacts": [
            {
                "schema_version": 1,
                "path": f"0{phase}-artifact/artifact.md",
                "hash": "sha256:" + "a" * 64,
            }
        ],
        "approved_by": "test-approver",
        "approved_at": "2026-05-17T10:00:00.000Z",
        "drafted_at": "2026-05-17T09:00:00.000Z",
        "validated_at": "2026-05-17T10:00:00.000Z",
    }
    (signoffs_dir / f"phase-{phase}.yaml").write_text(
        yaml.safe_dump(record, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def _make_dispatch_result(output_text: str) -> unittest.mock.MagicMock:
    result = unittest.mock.MagicMock()
    result.outcome = "success"
    result.agent_result.output_text = output_text
    return result


def _invoke_bootstrap(tmp_path: Path, *, json_mode: bool = True) -> object:
    args = ["--json", "bootstrap"] if json_mode else ["bootstrap"]
    with unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


# ---------------------------------------------------------------------------
# AC2 — Auto-skip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_auto_skip_when_real_source_exists(tmp_path: Path) -> None:
    """AC2: src/main.py present → exit 0, skip message, no dispatch, journal unchanged."""
    _init_repo(tmp_path)
    journal = tmp_path / ".claude" / "state" / "journal.log"
    initial_size = journal.stat().st_size if journal.exists() else 0

    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("# user code\n", encoding="utf-8")

    with (
        unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._bootstrap_pipeline.dispatch") as mock_dispatch,
    ):
        r = _runner.invoke(app, ["--json", "bootstrap"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    mock_dispatch.assert_not_called()
    out = json.loads(r.stdout)
    assert out["outcome"] == "skipped"
    assert out["reason"] == "source-exists"
    assert out["phase"] == 3
    assert out["track"] == "bootstrap"
    assert "source_root" in out
    final_size = journal.stat().st_size if journal.exists() else 0
    assert final_size == initial_size


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
@pytest.mark.parametrize("filename", [".gitkeep", "README.md"])
def test_proceeds_when_only_placeholder_in_src(tmp_path: Path, filename: str) -> None:
    """AC2/D1 edge: only placeholder in src/ → not a real source file → proceeds to gate check."""
    _init_repo(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / filename).write_text("", encoding="utf-8")
    r = _invoke_bootstrap(tmp_path)
    assert r.exit_code != 0
    assert "ERR_PHASE2_NOT_APPROVED" in (r.stdout + (r.stderr or ""))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_proceeds_when_src_is_file_not_dir(tmp_path: Path) -> None:
    """AC2: src exists as a regular file (not dir) → _source_exists False → proceeds to gate."""
    _init_repo(tmp_path)
    (tmp_path / "src").write_text("not a directory\n", encoding="utf-8")
    r = _invoke_bootstrap(tmp_path)
    assert r.exit_code != 0
    assert "ERR_PHASE2_NOT_APPROVED" in (r.stdout + (r.stderr or ""))


# ---------------------------------------------------------------------------
# AC1 — Phase 2 gate
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_phase2_not_approved_empty_source(tmp_path: Path) -> None:
    """AC1: empty src/ + no phase-2 signoff → ERR_PHASE2_NOT_APPROVED, no dispatch."""
    _init_repo(tmp_path)
    with (
        unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._bootstrap_pipeline.dispatch") as mock_dispatch,
    ):
        r = _runner.invoke(app, ["--json", "bootstrap"])

    assert r.exit_code == 1
    assert "ERR_PHASE2_NOT_APPROVED" in (r.stdout + (r.stderr or ""))
    mock_dispatch.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_phase2_gate_no_files_written(tmp_path: Path) -> None:
    """AC1: gate fires → no files written anywhere."""
    _init_repo(tmp_path)
    r = _invoke_bootstrap(tmp_path)
    assert r.exit_code == 1
    src = tmp_path / "src"
    assert not src.exists() or not any(
        p for p in src.rglob("*") if p.is_file() and p.name not in {".gitkeep", "README.md"}
    )


# ---------------------------------------------------------------------------
# AC5 — Happy path
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_files_and_journal(tmp_path: Path) -> None:
    """AC1/AC5: phase 2 APPROVED + empty src/ → files written, journal correct, exit 0."""
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _write_product_md(tmp_path)
    _write_arch_md(tmp_path)

    dispatch_result = _make_dispatch_result(_MOCK_RECORDS_2)
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    initial_lines = (
        len(journal_path.read_text(encoding="utf-8").splitlines()) if journal_path.exists() else 0
    )

    with (
        unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._bootstrap_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.bootstrap.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "bootstrap"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    assert (tmp_path / "src" / "__init__.py").is_file()
    out = json.loads(r.stdout)
    assert out["outcome"] == "success"
    assert out["phase"] == 3
    assert out["track"] == "bootstrap"
    assert out["specialist"] == "code-bootstrapper"
    assert out["files_written"] == 2

    entries = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    new_entries = entries[initial_lines:]
    kinds = [e.get("kind") for e in new_entries]
    assert "agent_dispatched" in kinds
    assert kinds.count("artifact_written") == 2
    assert kinds[-1] == "bootstrap_completed"
    bc = next(e for e in new_entries if e.get("kind") == "bootstrap_completed")
    assert bc["payload"]["files_written"] == 2


# ---------------------------------------------------------------------------
# AC5 — BOUNDARY_LINE pollution
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_boundary_in_product_md_raises_error(tmp_path: Path) -> None:
    """AC5: PRODUCT.md with BOUNDARY_LINE → ERR_ARTIFACT_CONTAINS_BOUNDARY."""
    from sdlc.dispatcher.prompts import BOUNDARY_LINE

    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _write_product_md(tmp_path, content=f"# Product\n\n{BOUNDARY_LINE}\n\nContent\n")
    _write_arch_md(tmp_path)

    r = _invoke_bootstrap(tmp_path)
    assert r.exit_code == 1
    assert "ERR_ARTIFACT_CONTAINS_BOUNDARY" in (r.stdout + (r.stderr or ""))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_boundary_in_arch_md_raises_error(tmp_path: Path) -> None:
    """AC5: ARCHITECTURE.md with BOUNDARY_LINE → ERR_ARTIFACT_CONTAINS_BOUNDARY."""
    from sdlc.dispatcher.prompts import BOUNDARY_LINE

    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _write_product_md(tmp_path)
    _write_arch_md(tmp_path, content=f"# Architecture\n\n{BOUNDARY_LINE}\n\nContent\n")

    r = _invoke_bootstrap(tmp_path)
    assert r.exit_code == 1
    assert "ERR_ARTIFACT_CONTAINS_BOUNDARY" in (r.stdout + (r.stderr or ""))


# ---------------------------------------------------------------------------
# AC6 — Record validation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_record_path_traversal_rejected(tmp_path: Path) -> None:
    """AC6: path with .. segment → WorkflowError."""
    with pytest.raises(WorkflowError, match=r"'\.\.'"):
        _validate_bootstrap_record({"path": "src/../etc/passwd", "content": "x"})


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_record_absolute_path_rejected(tmp_path: Path) -> None:
    """AC6: absolute path → WorkflowError."""
    with pytest.raises(WorkflowError, match="relative"):
        _validate_bootstrap_record({"path": "/etc/passwd", "content": "x"})


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_record_outside_allowed_roots_rejected(tmp_path: Path) -> None:
    """AC6: path outside src/ or tests/ → WorkflowError."""
    with pytest.raises(WorkflowError, match="allowed roots"):
        _validate_bootstrap_record({"path": "config/settings.py", "content": "x"})


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_record_missing_content_rejected(tmp_path: Path) -> None:
    """AC6: missing content key → WorkflowError."""
    with pytest.raises(WorkflowError, match="content"):
        _validate_bootstrap_record({"path": "src/foo.py"})


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_record_missing_path_rejected(tmp_path: Path) -> None:
    """AC6: missing path key → WorkflowError."""
    with pytest.raises(WorkflowError, match="path"):
        _validate_bootstrap_record({"content": "x"})


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_duplicate_paths_rejected_in_dispatch(tmp_path: Path) -> None:
    """AC6: duplicate path values across records → WorkflowError, non-zero exit."""
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _write_product_md(tmp_path)
    _write_arch_md(tmp_path)

    dup_records = json.dumps(
        [
            {"path": "src/__init__.py", "content": "# v1\n"},
            {"path": "src/__init__.py", "content": "# v2\n"},
        ]
    )
    dispatch_result = _make_dispatch_result(dup_records)

    with (
        unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._bootstrap_pipeline.dispatch", return_value=dispatch_result),
    ):
        r = _runner.invoke(app, ["--json", "bootstrap"])

    assert r.exit_code == 1
    assert "duplicate" in (r.stdout + (r.stderr or "")).lower()


# ---------------------------------------------------------------------------
# AC8 — Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_idempotency_second_run_skips(tmp_path: Path) -> None:
    """AC8: second run after success skips invisibly (auto-skip fires)."""
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _write_product_md(tmp_path)
    _write_arch_md(tmp_path)

    dispatch_result = _make_dispatch_result(_MOCK_RECORDS_2)

    # First run
    with (
        unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._bootstrap_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.bootstrap.evaluate_postconditions"),
    ):
        r1 = _runner.invoke(app, ["--json", "bootstrap"])
    assert r1.exit_code == 0

    # Second run — auto-skip must fire, dispatch must NOT be called
    with (
        unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._bootstrap_pipeline.dispatch") as mock_dispatch2,
    ):
        r2 = _runner.invoke(app, ["--json", "bootstrap"])

    assert r2.exit_code == 0
    mock_dispatch2.assert_not_called()
    out2 = json.loads(r2.stdout)
    assert out2["outcome"] == "skipped"
