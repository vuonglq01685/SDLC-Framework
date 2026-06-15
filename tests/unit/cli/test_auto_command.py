"""Unit tests for `sdlc auto` command (Story 4.1, AC7/C6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.engine.auto_loop import AutoLoopResult
from sdlc.specialists.registry import SpecialistRegistry

pytestmark = pytest.mark.unit

runner = CliRunner()


def _bootstrap(tmp_path: Path) -> None:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{}", encoding="utf-8")
    (state_dir / "journal.log").touch()


def test_auto_command_registered() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "auto" in result.output


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_auto_real_runtime_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SDLC_USE_MOCK_RUNTIME", raising=False)
    monkeypatch.delenv("SDLC_MOCK_GATE_BYPASS", raising=False)

    result = runner.invoke(app, ["auto"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "cannot dispatch on the real runtime yet" in result.output
    assert "EPIC-4-DEBT-AUTO-REAL-DISPATCH" in result.output
    journal = tmp_path / ".claude" / "state" / "journal.log"
    assert journal.read_text(encoding="utf-8") == ""


def test_auto_command_max_iterations_plumbed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The --max-iterations flag (code-review D3) reaches run_auto_loop unchanged."""
    _bootstrap(tmp_path)
    (tmp_path / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SDLC_USE_MOCK_RUNTIME", "1")
    monkeypatch.delenv("SDLC_MOCK_GATE_BYPASS", raising=False)

    captured: dict[str, object] = {}

    async def _fake_loop(repo_root: Path, **kwargs: object) -> AutoLoopResult:
        captured.update(kwargs)
        return AutoLoopResult(iterations=0, last_action="stopped", halted=False)

    monkeypatch.setattr("sdlc.cli.auto.run_auto_loop", _fake_loop)
    monkeypatch.setattr("sdlc.cli.auto.load_registry", lambda _p: SpecialistRegistry({}))
    result = runner.invoke(app, ["auto", "--max-iterations", "3"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert captured.get("max_iterations") == 3
