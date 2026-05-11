"""Pre-flight tests for ``sdlc research`` (Story 2A.9, AC8).

P17 (code review): preflight tests now mock ``_research_dispatch_async`` to
assert *behavior* — dispatch is called exactly once on the happy path and
zero times on every refusal path. Previously the happy-path test ran the full
mock-runtime flow and only verified ``exit_code == 0``, making it functionally
equivalent to the integration test (and mis-classified as a unit test).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.state.model import State

pytestmark = pytest.mark.unit

_runner = CliRunner()

_DISPATCH_TARGET = "sdlc.cli.research._research_dispatch_async"


def test_uninitialized_emits_err_not_initialized_and_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch(_DISPATCH_TARGET, new_callable=AsyncMock) as mock_dispatch:
        result = _runner.invoke(app, ["--json", "research", "topic"])
    assert result.exit_code == 1
    assert "ERR_NOT_INITIALIZED" in result.stderr
    mock_dispatch.assert_not_called()


def test_phase_zero_emits_phase_mismatch_and_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    st = State(phase=0, next_monotonic_seq=0)
    state_path = tmp_path / ".claude" / "state" / "state.json"
    state_path.write_text(json.dumps(st.model_dump(mode="json")), encoding="utf-8")

    with (
        patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path),
        patch(_DISPATCH_TARGET, new_callable=AsyncMock) as mock_dispatch,
    ):
        result = _runner.invoke(app, ["--json", "research", "topic"])
    assert result.exit_code == 1
    assert "ERR_PHASE_MISMATCH" in result.stderr
    mock_dispatch.assert_not_called()


def test_phase_two_emits_phase_mismatch_and_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    st = State(phase=2, next_monotonic_seq=0)
    state_path = tmp_path / ".claude" / "state" / "state.json"
    state_path.write_text(json.dumps(st.model_dump(mode="json")), encoding="utf-8")

    with (
        patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path),
        patch(_DISPATCH_TARGET, new_callable=AsyncMock) as mock_dispatch,
    ):
        result = _runner.invoke(app, ["--json", "research", "topic"])
    assert result.exit_code == 1
    assert "ERR_PHASE_MISMATCH" in result.stderr
    mock_dispatch.assert_not_called()


def test_phase_three_emits_phase_mismatch_and_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    st = State(phase=3, next_monotonic_seq=0)
    state_path = tmp_path / ".claude" / "state" / "state.json"
    state_path.write_text(json.dumps(st.model_dump(mode="json")), encoding="utf-8")

    with (
        patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path),
        patch(_DISPATCH_TARGET, new_callable=AsyncMock) as mock_dispatch,
    ):
        result = _runner.invoke(app, ["--json", "research", "topic"])
    assert result.exit_code == 1
    assert "ERR_PHASE_MISMATCH" in result.stderr
    mock_dispatch.assert_not_called()


@pytest.mark.skipif(
    __import__("sys").platform == "win32",
    reason="POSIX journal append required for research dispatch",
)
def test_phase_one_dispatch_called_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P17: happy path calls dispatch exactly once; integration test covers e2e."""
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)

    # Stub _research_dispatch_async to write the artifact + a minimal
    # agent_runs row (postcondition `boundary_line_present_in_prompts` reads
    # this file), then return the rel_art string.
    def _make_stub_write(slug: str, topic: str) -> AsyncMock:
        async def _stub(**kwargs: object) -> str:
            import json as _json

            from sdlc.cli.research import _wrap_research_artifact
            from sdlc.dispatcher.prompts import BOUNDARY_LINE

            target = kwargs["target_path"]
            assert isinstance(target, Path)
            root = kwargs["root"]
            assert isinstance(root, Path)
            text = _wrap_research_artifact(
                "## Research Findings\n\nstub body\n",
                topic=topic,
                slug=slug,
                ts="2026-01-01T00:00:00.000Z",
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            runs_path = root / "03-Implementation" / "agent_runs.jsonl"
            runs_path.parent.mkdir(parents=True, exist_ok=True)
            # Embed BOUNDARY_LINE inside <BOUNDARY>...</BOUNDARY> tags to satisfy
            # the boundary_line_present_in_prompts invariant.
            runs_row = {
                "dispatch_prompt": (
                    f"prompt for {topic}\n<BOUNDARY>\n{BOUNDARY_LINE}\n</BOUNDARY>\n"
                ),
                "specialist_name": "technical-researcher",
            }
            runs_path.write_text(_json.dumps(runs_row, sort_keys=True) + "\n", encoding="utf-8")
            return target.resolve().relative_to(root.resolve()).as_posix()

        wrapper = AsyncMock(side_effect=_stub)
        return wrapper

    stub = _make_stub_write("hello-research-topic", "hello research topic")
    with (
        patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path),
        patch(_DISPATCH_TARGET, new=stub),
    ):
        result = _runner.invoke(app, ["research", "hello research topic"])
    assert result.exit_code == 0, result.stderr + result.stdout
    stub.assert_called_once()
    art = tmp_path / "01-Requirement" / "02-Research" / "hello-research-topic.md"
    assert art.is_file()
