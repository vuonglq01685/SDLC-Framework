"""Unit tests for cli/signoff.py:run_signoff (AC8, Story 2A.12)."""

from __future__ import annotations

import hashlib
import sys
import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()
_TS_NOW = "2026-05-14T10:00:00.000Z"


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch | None = None) -> None:
    """Create minimal project state (init).

    The ``_get_repo_root_or_cwd`` override is only needed for the single
    ``run_init`` call below, so it is ALWAYS restored afterwards. A bare,
    unrestored assignment (the former P21 "legacy" fallback) leaked the tmp-path
    lambda into ``sdlc.cli.init`` for the rest of the session and made every
    later real ``sdlc init`` resolve to a prior test's tmp dir — turning the
    trace/replay/logs E2E suite red in the full run (CI-recovery 2026-07-03).
    Pass ``monkeypatch`` when available (auto-restored); otherwise this
    save/restore keeps the no-fixture call sites leak-free too.
    """
    from sdlc.cli import init as init_mod

    if monkeypatch is not None:
        monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
        init_mod.run_init(ctx=None)
        return

    original = init_mod._get_repo_root_or_cwd
    init_mod._get_repo_root_or_cwd = lambda: tmp_path  # type: ignore[method-assign]
    try:
        init_mod.run_init(ctx=None)
    finally:
        init_mod._get_repo_root_or_cwd = original  # type: ignore[method-assign]


def _make_ctx(*, json_mode: bool = False) -> typer.Context:
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = False
    ctx.obj["json"] = json_mode
    return ctx


# ---------------------------------------------------------------------------
# Pre-flight: uninitialized project
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_not_initialized(tmp_path: Path) -> None:
    """AC8: ERR_NOT_INITIALIZED if state.json missing."""
    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "signoff", "1"])
    assert r.exit_code == 1
    assert "ERR_NOT_INITIALIZED" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Pre-flight: invalid phase
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_invalid_phase_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC8: phase=0 → ERR_USER_INPUT."""
    _bootstrap(tmp_path)
    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "signoff", "0"])
    assert r.exit_code == 1
    assert "ERR_USER_INPUT" in (r.stdout + r.stderr)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_invalid_phase_3(tmp_path: Path) -> None:
    """AC8: phase=3 → ERR_USER_INPUT."""
    _bootstrap(tmp_path)
    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "signoff", "3"])
    assert r.exit_code == 1
    assert "ERR_USER_INPUT" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Pre-flight: missing phase directory
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_missing_phase_directory(tmp_path: Path) -> None:
    """AC8: phase=1 but 01-Requirement/ missing → error."""
    _bootstrap(tmp_path)
    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["signoff", "1"])
    assert r.exit_code == 1


# ---------------------------------------------------------------------------
# Pre-flight: phase 2 requires phase 1 APPROVED
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_phase2_refused_when_phase1_not_approved(tmp_path: Path) -> None:
    """AC2/AC8: phase=2 without phase 1 APPROVED → ERR_PHASE1_NOT_APPROVED."""
    _bootstrap(tmp_path)
    arch_dir = tmp_path / "02-Architecture"
    arch_dir.mkdir(parents=True, exist_ok=True)
    (arch_dir / "arch.md").write_bytes(b"arch")

    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "signoff", "2"])
    assert r.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Pre-flight: already APPROVED → refuse re-generation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_phase1_already_approved_refused(tmp_path: Path) -> None:
    """AC4/AC8: if phase 1 is APPROVED, refuse re-generation with ERR_PHASE1_ALREADY_APPROVED."""
    from sdlc.signoff.states import SignoffState

    _bootstrap(tmp_path)
    req_dir = tmp_path / "01-Requirement"
    req_dir.mkdir(parents=True, exist_ok=True)
    (req_dir / "01-PRODUCT.md").write_bytes(b"product")

    with (
        unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.signoff.compute_state", return_value=SignoffState.APPROVED),
    ):
        r = _runner.invoke(app, ["--json", "signoff", "1"])
    assert r.exit_code == 1
    assert "ALREADY_APPROVED" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Happy path: phase 1 AWAITING_SIGNOFF → generates SIGNOFF.md
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_phase1_happy_path_generates_signoff_md(tmp_path: Path) -> None:
    """AC1/AC8: phase=1, AWAITING_SIGNOFF → SIGNOFF.md written + journal + emit_json next_step."""
    _bootstrap(tmp_path)
    req_dir = tmp_path / "01-Requirement"
    req_dir.mkdir(parents=True, exist_ok=True)
    (req_dir / "01-PRODUCT.md").write_bytes(b"product content")

    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "signoff", "1"])
    assert r.exit_code == 0, r.stderr + r.stdout

    # SIGNOFF.md written
    signoff_path = req_dir / "SIGNOFF.md"
    assert signoff_path.exists()

    # Journal has signoff_draft_generated
    import json

    journal = tmp_path / ".claude" / "state" / "journal.log"
    entries = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
    ]
    kinds = [e["kind"] for e in entries]
    assert "signoff_draft_generated" in kinds

    # emit_json has next_step
    output = r.stdout + r.stderr
    assert "next_step" in output or "signoff" in output


# ---------------------------------------------------------------------------
# Re-generation: DRAFTED_NOT_APPROVED → overwrite
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_re_generate_overwrites_draft(tmp_path: Path) -> None:
    """AC4/AC8: DRAFTED_NOT_APPROVED → overwrite SIGNOFF.md with fresh hashes."""
    _bootstrap(tmp_path)
    req_dir = tmp_path / "01-Requirement"
    req_dir.mkdir(parents=True, exist_ok=True)
    (req_dir / "01-PRODUCT.md").write_bytes(b"product v1")

    # First generation
    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r1 = _runner.invoke(app, ["signoff", "1"])
    assert r1.exit_code == 0

    # Modify artifact
    (req_dir / "01-PRODUCT.md").write_bytes(b"product v2")

    # Second generation
    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r2 = _runner.invoke(app, ["signoff", "1"])
    assert r2.exit_code == 0

    # SIGNOFF.md has new hash (v2)
    text = (req_dir / "SIGNOFF.md").read_text(encoding="utf-8")
    assert _sha256(b"product v2") in text
    assert _sha256(b"product v1") not in text


# ---------------------------------------------------------------------------
# DR2 (Story 2A.12 code-review) — per-module coverage for error paths
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_compute_state_error_for_phase1_raises_phase1_not_approved(tmp_path: Path) -> None:
    """DR2: compute_state raising during phase-2 pre-flight → ERR_PHASE1_NOT_APPROVED."""
    _bootstrap(tmp_path)

    from sdlc.errors import SignoffError

    def _raise(phase: int, **kw: object) -> object:
        raise SignoffError("simulated phase-1 read failure", details={"phase": phase})

    with (
        unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.signoff.compute_state", side_effect=_raise),
    ):
        result = _runner.invoke(app, ["signoff", "2"])

    assert result.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in result.output or "phase 1" in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_compute_state_error_for_current_phase_raises_user_input(tmp_path: Path) -> None:
    """DR2: compute_state raising during current-phase pre-flight → ERR_USER_INPUT.

    Patches compute_state to raise ONLY for the target phase so the phase-2-gates-phase-1
    branch passes (phase 1 reads as APPROVED via the unpatched code path is not reachable
    here — we exercise phase 1 directly where compute_state raises for the target phase).
    """
    _bootstrap(tmp_path)

    from sdlc.errors import SignoffError

    def _raise(*a: object, **kw: object) -> object:
        raise SignoffError("simulated state read failure", details={})

    with (
        unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.signoff.compute_state", side_effect=_raise),
    ):
        result = _runner.invoke(app, ["signoff", "1"])

    assert result.exit_code == 1
    assert "ERR_USER_INPUT" in result.output or "could not read signoff state" in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_generate_error_propagates_code_from_details(tmp_path: Path) -> None:
    """DR2 + P3: generator's SignoffError emits with code from exc.details["code"].

    Empty phase directory (no artifacts) → ERR_NO_ARTIFACTS with message NOT
    double-prefixed (P3). Verifies the cleaned-up message text.
    """
    _bootstrap(tmp_path)
    # Create an empty phase directory so generate_signoff_md raises ERR_NO_ARTIFACTS.
    (tmp_path / "01-Requirement").mkdir(parents=True, exist_ok=True)

    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["signoff", "1"])

    assert result.exit_code == 1
    # P3: message body must NOT start with "ERR_NO_ARTIFACTS: ERR_NO_ARTIFACTS: …"
    assert "ERR_NO_ARTIFACTS: ERR_NO_ARTIFACTS" not in result.output
    # The error code is still surfaced via the envelope (default-mode prints "sdlc: <message>").
    assert "no artifacts found" in result.output.lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_journal_append_oserror_emits_journal_append_failed(tmp_path: Path) -> None:
    """DR2 + P6: journal append OSError → ERR_JOURNAL_APPEND_FAILED (was: silent swallow)."""
    _bootstrap(tmp_path)
    (tmp_path / "01-Requirement").mkdir(parents=True, exist_ok=True)
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").write_bytes(b"product")

    def _raise(*a: object, **kw: object) -> object:
        raise OSError("simulated journal write failure")

    with (
        unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.journal.append_sync", side_effect=_raise),
    ):
        result = _runner.invoke(app, ["signoff", "1"])

    assert result.exit_code == 2  # ERR_JOURNAL_APPEND_FAILED → 2
    assert "ERR_JOURNAL_APPEND_FAILED" in result.output or "journal append failed" in result.output


def test_bootstrap_does_not_leak_repo_root_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test-isolation regression (CI-recovery 2026-07-03): ``_bootstrap`` must
    restore ``sdlc.cli.init._get_repo_root_or_cwd`` after ``run_init`` — a leaked
    tmp-path override poisoned that module global for the rest of the session and
    made every later real ``sdlc init`` resolve to a prior test's tmp dir
    ("already initialized at .../test_journal_append_oserror_em0"), turning the
    whole ``tests/integration/test_trace_replay_logs_e2e.py`` suite red in the
    full run while it passed in isolation.
    """
    from sdlc.cli import init as init_mod
    from sdlc.cli._paths import get_repo_root_or_cwd

    # Pin a known-clean baseline (auto-restored by monkeypatch) so this guard is
    # order-independent — it must not depend on no earlier test having leaked.
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", get_repo_root_or_cwd)

    _bootstrap(tmp_path)

    assert init_mod._get_repo_root_or_cwd is get_repo_root_or_cwd, (
        "_bootstrap leaked its tmp-path repo-root override into "
        "sdlc.cli.init._get_repo_root_or_cwd (poisons later tests' `sdlc init`)"
    )
