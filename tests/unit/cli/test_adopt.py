"""Unit tests for `sdlc init --adopt` CLI entry (Story 3.1, AC1/AC2/AC6).

The CLI layer (cli/adopt.run_adopt) reuses the init scaffolding, runs the three-pass
driver, and writes `adopt-report.json`. Fresh vs resume is distinguished by the presence
of canonical state (AC2 + D3(a) pass-level resume).
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover - POSIX-only journal writer
    pytest.skip("adopt mode is POSIX-only in v1", allow_module_level=True)

from typer.testing import CliRunner

from sdlc.contracts.adopt_report import AdoptReport
from sdlc.errors import AdoptError, JournalError

pytestmark = pytest.mark.unit

_runner = CliRunner()


def _invoke_adopt(root: Path, *, global_flags: tuple[str, ...] = ()) -> object:
    from sdlc.cli.main import app

    # Root-callback eager options (e.g. --json) precede the subcommand.
    args = [*global_flags, "init", "--adopt"]
    with unittest.mock.patch("sdlc.cli.adopt._get_repo_root_or_cwd", return_value=root):
        return _runner.invoke(app, args)


def test_adopt_scaffolds_canonical_state(tmp_path: Path) -> None:
    result = _invoke_adopt(tmp_path)
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "state" / "state.json").exists()
    assert (tmp_path / ".claude" / "state" / "journal.log").exists()
    # init scaffolding includes the hook-trust baseline
    assert (tmp_path / ".claude" / "state" / "hook-hashes.json").exists()


def test_adopt_writes_conforming_report(tmp_path: Path) -> None:
    result = _invoke_adopt(tmp_path)
    assert result.exit_code == 0, result.output
    report_path = tmp_path / ".claude" / "state" / "adopt-report.json"
    report = AdoptReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert list(report.passes_completed) == [1, 2, 3]
    assert report.detected == ()


def test_adopt_json_envelope(tmp_path: Path) -> None:
    result = _invoke_adopt(tmp_path, global_flags=("--json",))
    assert result.exit_code == 0, result.output
    # --json mode must emit ONLY the machine-readable envelope — no human `echo` lines may
    # contaminate the JSON channel (parsing splitlines()[-1] would silently mask such a leak).
    lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
    assert len(lines) == 1, f"--json mode leaked non-envelope output: {lines}"
    envelope = json.loads(lines[0])
    assert envelope["command"] == "adopt"
    assert envelope["passes_completed"] == [1, 2, 3]


def test_adopt_resume_is_idempotent(tmp_path: Path) -> None:
    first = _invoke_adopt(tmp_path)
    assert first.exit_code == 0, first.output
    # second invocation on an already-initialized repo must not hard-refuse (AC2)
    second = _invoke_adopt(tmp_path)
    assert second.exit_code == 0, second.output
    report_path = tmp_path / ".claude" / "state" / "adopt-report.json"
    report = AdoptReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert list(report.passes_completed) == [1, 2, 3]


def test_adopt_does_not_emit_not_implemented(tmp_path: Path) -> None:
    result = _invoke_adopt(tmp_path)
    assert "not implemented" not in result.output.lower()


# --- AC5: greenfield-disguised message + detected-artifact count (Story 3.2) ---------------


def test_adopt_emits_greenfield_message_on_empty_detection(tmp_path: Path) -> None:
    """An artifact-free repo → the verbatim greenfield message (AC5, epics.md:1809)."""
    result = _invoke_adopt(tmp_path)
    assert result.exit_code == 0, result.output
    assert "no candidate artifacts detected; will treat as greenfield" in result.output


def test_adopt_emits_detected_count_when_artifacts_found(tmp_path: Path) -> None:
    """A repo with SDLC-shaped artifacts → the detected-count line, not the greenfield message."""
    (tmp_path / "README.md").write_text("# My Project", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    result = _invoke_adopt(tmp_path)
    assert result.exit_code == 0, result.output
    assert "detected artifacts:" in result.output
    assert "will treat as greenfield" not in result.output


def test_adopt_report_populates_detected_for_brownfield(tmp_path: Path) -> None:
    """Pass 1 detection populates `detected[]` in the report for a brownfield repo (AC1/AC4)."""
    (tmp_path / "README.md").write_text("# My Project", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "arch.md").write_text(
        "# Architecture\n\nADR-001: decision\n", encoding="utf-8"
    )
    result = _invoke_adopt(tmp_path)
    assert result.exit_code == 0, result.output
    report_path = tmp_path / ".claude" / "state" / "adopt-report.json"
    report = AdoptReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    kinds = {a.kind for a in report.detected}
    assert "readme" in kinds
    assert "architecture" in kinds
    arch = next(a for a in report.detected if a.kind == "architecture")
    assert arch.suggested_target == "02-Architecture/02-System/ARCHITECTURE.md"
    assert isinstance(arch.confidence, int)


# --- failure surfacing (AC6: failures are journaled at the driver AND surfaced at the CLI) ----


def test_adopt_surfaces_driver_adopt_error_as_exit_2(tmp_path: Path) -> None:
    """A driver-raised AdoptError becomes an ERR_ADOPT envelope (exit 2), not a raw traceback."""

    def _boom(*, root: Path, journal_path: Path, **_kw: object) -> object:
        raise AdoptError("adopt pass 2 failed: boom", details={"pass": 2})

    with unittest.mock.patch("sdlc.adopt.run_adopt", _boom):
        result = _invoke_adopt(tmp_path)
    assert result.exit_code == 2, result.output
    assert "adopt pass 2 failed" in result.output


def test_adopt_surfaces_journal_error_as_exit_2(tmp_path: Path) -> None:
    """A driver-raised JournalError becomes an ERR_ADOPT envelope (exit 2)."""

    def _boom(*, root: Path, journal_path: Path, **_kw: object) -> object:
        raise JournalError("monotonic_seq regression")

    with unittest.mock.patch("sdlc.adopt.run_adopt", _boom):
        result = _invoke_adopt(tmp_path)
    assert result.exit_code == 2, result.output
    assert "journal append failed" in result.output


def test_adopt_hook_baseline_failure_surfaces_as_exit_2(tmp_path: Path) -> None:
    """A hook-trust baseline failure on a fresh adopt is a typed ERR_ADOPT envelope (exit 2)."""

    def _boom(root: Path) -> None:
        raise RuntimeError("hash mismatch")

    with unittest.mock.patch("sdlc.cli._init_hook_baseline.baseline_hook_trust", _boom):
        result = _invoke_adopt(tmp_path)
    assert result.exit_code == 2, result.output
    assert "hook-trust baseline failed" in result.output
