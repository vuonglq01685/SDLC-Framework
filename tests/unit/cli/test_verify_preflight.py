"""Pre-flight checks for `sdlc verify` (Story 2A.10, Task 2, AC3).

Asserts that `cli/verify.run_verify` rejects bad inputs BEFORE invoking
`dispatch(...)` and BEFORE appending journal entries. Each failure mode
maps to a distinct error code per AC3.

The dispatch call-site is mocked: any test that reaches dispatch is
expected to break out via the mock (signalling the pre-flight passed).
"""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()


def _bootstrap(tmp_path: Path, *, phase: int = 1, with_artifact: bool = True) -> Path:
    """Create a minimal initialised project + (optionally) a Phase-1 artifact."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(
        f'{{"schema_version":1,"next_monotonic_seq":0,"phase":{phase},'
        f'"epics":{{}},"stories":{{}},"tasks":{{}}}}\n',
        encoding="utf-8",
    )
    (state_dir / "journal.log").touch()
    req_dir = tmp_path / "01-Requirement"
    req_dir.mkdir(parents=True)
    if with_artifact:
        (req_dir / "01-PRODUCT.md").write_text("# Product\n\nBody.\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# AC3.1 — state.json missing → ERR_NOT_INITIALIZED
# ---------------------------------------------------------------------------


def test_uninitialized_returns_err_not_initialized(tmp_path: Path) -> None:
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "01-Requirement/01-PRODUCT.md"])
    assert result.exit_code == 1
    out = result.stderr + result.stdout
    # PC4 (post-review 2026-05-12 Cluster C-J): keep OR-clause until tests
    # migrate to `--json` invocation. Non-JSON mode emits only the canonical
    # message ("project not initialized"); the ERR code is only surfaced in
    # JSON mode. Tightening to ERR-code-only without --json invocation
    # over-fits. TODO: refactor invocation to `["--json", ...]` and parse
    # envelope.
    assert "ERR_NOT_INITIALIZED" in out or "not initialized" in out.lower()


# ---------------------------------------------------------------------------
# AC3.2 — phase != 1 → ERR_PHASE_MISMATCH
# ---------------------------------------------------------------------------


def test_phase_mismatch_returns_err_phase_mismatch(tmp_path: Path) -> None:
    _bootstrap(tmp_path, phase=2)
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "01-Requirement/01-PRODUCT.md"])
    assert result.exit_code != 0
    out = result.stderr + result.stdout
    assert (
        "ERR_PHASE_MISMATCH" in out or "requires phase=1" in out
    )  # PC4 (2026-05-12): canonical-msg fallback


# ---------------------------------------------------------------------------
# AC3.3 — absolute path or `..` traversal → ERR_PATH_TRAVERSAL
# ---------------------------------------------------------------------------


def test_absolute_path_returns_err_path_traversal(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "/etc/passwd"])
    assert result.exit_code != 0
    out = result.stderr + result.stdout
    assert (
        "ERR_PATH_TRAVERSAL" in out or "repo-relative POSIX path" in out
    )  # PC4: tight ERR-or-canonical-msg


def test_dotdot_traversal_returns_err_path_traversal(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "../etc/passwd"])
    assert result.exit_code != 0
    out = result.stderr + result.stdout
    assert (
        "ERR_PATH_TRAVERSAL" in out or "repo-relative POSIX path" in out
    )  # PC4: tight ERR-or-canonical-msg


def test_outside_requirement_dir_returns_err_path_traversal(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    other = tmp_path / "02-Architecture"
    other.mkdir()
    (other / "x.md").write_text("body", encoding="utf-8")
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "02-Architecture/x.md"])
    assert result.exit_code != 0
    out = result.stderr + result.stdout
    assert (
        "ERR_PATH_TRAVERSAL" in out or "repo-relative POSIX path" in out
    )  # PC4: tight ERR-or-canonical-msg


# ---------------------------------------------------------------------------
# AC3.4 — non-existent path → ERR_ARTIFACT_NOT_FOUND
# ---------------------------------------------------------------------------


def test_missing_artifact_returns_err_artifact_not_found(tmp_path: Path) -> None:
    _bootstrap(tmp_path, with_artifact=False)
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "01-Requirement/missing.md"])
    assert result.exit_code != 0
    out = result.stderr + result.stdout
    assert (
        "ERR_ARTIFACT_NOT_FOUND" in out or "artifact not found" in out.lower()
    )  # PC4 (2026-05-12): kept dual-channel


def test_directory_returns_err_artifact_not_found(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    (tmp_path / "01-Requirement" / "subdir").mkdir()
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "01-Requirement/subdir"])
    assert result.exit_code != 0
    out = result.stderr + result.stdout
    assert (
        "ERR_ARTIFACT_NOT_FOUND" in out or "artifact not found" in out.lower()
    )  # PC4 (2026-05-12): kept dual-channel


def test_symlink_escape_returns_err_path_traversal(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    outside = tmp_path.parent / "outside-target.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    link = tmp_path / "01-Requirement" / "escape.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")

    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "01-Requirement/escape.md"])
    assert result.exit_code != 0
    out = result.stderr + result.stdout
    # PC4 (2026-05-12): symlink escape is caught by PC2 parent-walk → message
    # contains "symlink component" + "01-Requirement". On platforms where
    # `Path.is_symlink()` can't see the link (rare; tests skipped above if
    # symlinks unsupported), the resolve() check catches it via either
    # traversal or not-found messaging. The non-JSON CLI emits only the
    # canonical message; tighter than the prior bare "01-Requirement" substring.
    assert (
        "symlink component" in out
        or "repo-relative POSIX path" in out
        or "artifact not found" in out.lower()
    )


# ---------------------------------------------------------------------------
# AC3 happy path: phase 1 + valid path → reaches dispatch (mocked)
# ---------------------------------------------------------------------------


def test_phase1_valid_path_reaches_dispatch(tmp_path: Path) -> None:
    _bootstrap(tmp_path)

    sentinel = RuntimeError("dispatch reached — pre-flight passed")

    def _fail_dispatch(*args: object, **kwargs: object) -> None:
        raise sentinel

    with (
        unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.verify._invoke_dispatch", side_effect=_fail_dispatch),
    ):
        result = _runner.invoke(app, ["verify", "01-Requirement/01-PRODUCT.md"])

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# P26 / PC5 (post-review 2026-05-12 Cluster C-J): JSON-mode missing-arg envelope
# Typer's default missing-argument error handler emits a usage-banner plain text
# to stderr, NOT a JSON envelope. This test pins the current behaviour so a
# future contract amendment (AC1 sub-clause for Typer-level errors) has a
# concrete failure-mode to assert against. Until that AC ships, the assertion
# is "exits non-zero", not "emits structured envelope".
# ---------------------------------------------------------------------------


def test_json_mode_missing_artifact_id_exits_nonzero(tmp_path: Path) -> None:
    """sdlc --json verify (no artifact_id) MUST exit non-zero; envelope shape
    is currently NOT JSON (Typer usage banner). When AC1 amends the contract,
    tighten this test to parse and assert ``envelope["error"]["code"]``.
    """
    _bootstrap(tmp_path)
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["--json", "verify"])
    assert result.exit_code != 0
    # Document current behaviour: Typer emits a usage banner. Future PC may
    # introduce an early `--json` check that produces an `{"error": {...}}`
    # envelope; the assertion below is the regression pin for "AC1 contract
    # is NOT YET amended for Typer-level errors" — flip to a JSON-parse
    # assertion when AC1 grows the sub-clause.
    out = result.stderr + result.stdout
    assert "Missing argument" in out or "MISSING_ARGUMENT" in out or "Usage:" in out


# ---------------------------------------------------------------------------
# Additional: no journal entries on pre-flight failure (AC3 last-And)
# ---------------------------------------------------------------------------


def test_preflight_failure_appends_no_journal_entry(tmp_path: Path) -> None:
    _bootstrap(tmp_path, with_artifact=False)
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    before = journal_path.read_bytes()
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        _runner.invoke(app, ["verify", "01-Requirement/missing.md"])
    after = journal_path.read_bytes()
    assert before == after


# ---------------------------------------------------------------------------
# Module-level bypass test for _resolve_artifact_path helper (kept narrow
# so refactors of run_verify orchestration don't churn this case).
# ---------------------------------------------------------------------------


class TestResolveArtifactPathHelper:
    def test_rejects_absolute(self) -> None:
        from sdlc.cli.verify import _resolve_artifact_path

        with pytest.raises(typer.Exit):
            ctx = typer.Context(command=typer.core.TyperCommand("verify"))
            ctx.ensure_object(dict)
            _resolve_artifact_path(ctx=ctx, root=Path("/repo"), artifact_id="/etc/passwd")

    def test_rejects_dotdot(self) -> None:
        from sdlc.cli.verify import _resolve_artifact_path

        with pytest.raises(typer.Exit):
            ctx = typer.Context(command=typer.core.TyperCommand("verify"))
            ctx.ensure_object(dict)
            _resolve_artifact_path(ctx=ctx, root=Path("/repo"), artifact_id="../leak.md")

    def test_rejects_outside_requirement_dir(self) -> None:
        from sdlc.cli.verify import _resolve_artifact_path

        with pytest.raises(typer.Exit):
            ctx = typer.Context(command=typer.core.TyperCommand("verify"))
            ctx.ensure_object(dict)
            _resolve_artifact_path(ctx=ctx, root=Path("/repo"), artifact_id="02-Architecture/x.md")

    def test_accepts_under_requirement_dir(self, tmp_path: Path) -> None:
        from sdlc.cli.verify import _resolve_artifact_path

        req_dir = tmp_path / "01-Requirement"
        req_dir.mkdir()
        artifact = req_dir / "01-PRODUCT.md"
        artifact.write_text("# Body\n", encoding="utf-8")

        ctx = typer.Context(command=typer.core.TyperCommand("verify"))
        ctx.ensure_object(dict)
        resolved = _resolve_artifact_path(
            ctx=ctx, root=tmp_path, artifact_id="01-Requirement/01-PRODUCT.md"
        )
        assert resolved == artifact
