"""Tests for runner bypass wiring (AC6 runner integration, Story 2A.4 Task 5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.builtin.naming_validator import naming_validator
from sdlc.hooks.builtin.phase_gate import phase_gate
from sdlc.hooks.runner import HookDecision, run_hook_chain


def _p(path: str) -> HookPayload:
    return HookPayload(
        hook_name="test",
        target_path=path,
        target_kind="write_intent",
        content_hash_before=None,
        write_intent="test write",
    )


def _make_phase_gate(repo_root: Path):
    def _hook(p: HookPayload) -> HookDecision:
        return phase_gate(p, repo_root=repo_root)

    return _hook


@pytest.mark.unit
class TestBypassInRunner:
    async def test_naming_still_runs_on_bypass(self, tmp_path) -> None:
        """naming_validator is NEVER bypassed — even when bypass_phase_gate=True."""
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock):
            result = await run_hook_chain(
                _p("01-Requirement/04-Epics/EPC_typo.json"),
                hooks=(naming_validator, _make_phase_gate(tmp_path)),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=None,
            )
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"

    async def test_phase_gate_bypassed_on_phase2(self, tmp_path) -> None:
        """phase_gate bypassed for phase-2 path with no signoff when bypass=True."""
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock):
            result = await run_hook_chain(
                _p("02-Architecture/01-UX/01-tokens.md"),
                hooks=(naming_validator, _make_phase_gate(tmp_path)),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=None,
            )
        assert result.decision == "allow"

    async def test_bypass_appends_journal_entry(self, tmp_path) -> None:
        """Bypass appends kind=bypass_signoff journal entry."""
        journal_path = tmp_path / "journal.log"
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                _p("02-Architecture/01-UX/01-tokens.md"),
                hooks=(_make_phase_gate(tmp_path),),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=journal_path,
            )
        assert result.decision == "allow"
        # Should have called journal append for bypass_signoff
        mock_j.assert_called()
        entry = mock_j.call_args.args[0]
        assert entry.kind == "bypass_signoff"
        assert "justification" in entry.payload
        assert entry.payload["justification"] == "real reason here"

    async def test_bypass_justification_too_short_raises(self, tmp_path) -> None:
        """Justification shorter than 10 chars raises ValueError."""
        with pytest.raises(ValueError, match="10 characters"):
            await run_hook_chain(
                _p("02-Architecture/01-UX/01-tokens.md"),
                hooks=(_make_phase_gate(tmp_path),),
                bypass_phase_gate=True,
                justification="short",
                journal_path=None,
            )

    async def test_bypass_on_phase1_no_journal_entry(self, tmp_path) -> None:
        """Bypass on a non-gated path (Phase 1) does NOT append bypass_signoff journal entry."""
        journal_path = tmp_path / "journal.log"
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                _p("01-Requirement/04-Epics/EPIC-foo.json"),
                hooks=(_make_phase_gate(tmp_path),),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=journal_path,
            )
        assert result.decision == "allow"
        # No bypass_signoff entry — the gate wasn't triggered
        bypass_calls = [c for c in mock_j.call_args_list if c.args[0].kind == "bypass_signoff"]
        assert len(bypass_calls) == 0

    async def test_phase_gate_bypassed_on_phase3(self, tmp_path) -> None:
        """phase_gate bypassed for phase-3 path; journal entry records phase_attempted=3."""
        journal_path = tmp_path / "journal.log"
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                _p("03-Implementation/01-API/server.py"),
                hooks=(_make_phase_gate(tmp_path),),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=journal_path,
            )
        assert result.decision == "allow"
        entry = mock_j.call_args.args[0]
        assert entry.kind == "bypass_signoff"
        assert entry.payload["phase_attempted"] == 3

    async def test_bypass_on_non_phase_path_no_bypass_journal(self, tmp_path) -> None:
        """Bypass on a non-phase path (.claude/) has no gated phase → no bypass_signoff entry."""
        journal_path = tmp_path / "journal.log"
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                _p(".claude/hooks/naming_validator.py"),
                hooks=(_make_phase_gate(tmp_path),),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=journal_path,
            )
        assert result.decision == "allow"
        bypass_calls = [c for c in mock_j.call_args_list if c.args[0].kind == "bypass_signoff"]
        assert len(bypass_calls) == 0

    async def test_is_phase_gate_marker_attribute_bypassed(self, tmp_path) -> None:
        """Hook with __is_phase_gate__ = True is detected via marker and bypassed."""
        call_log: list[bool] = []

        def fake_gate(p: HookPayload) -> HookDecision:
            call_log.append(True)
            return HookDecision.deny(
                hook_name="fake_gate", reason="gated", error_code="phase_gate_violation"
            )

        fake_gate.__is_phase_gate__ = True  # type: ignore[attr-defined]

        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock):
            result = await run_hook_chain(
                _p("02-Architecture/01-UX/01-tokens.md"),
                hooks=(fake_gate,),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=None,
            )
        # Marker detected → hook bypassed → allow without calling fake_gate
        assert result.decision == "allow"
        assert call_log == []

    async def test_callable_object_not_phase_gate_still_runs(self, tmp_path) -> None:
        """Callable object (no __code__) is not detected as phase_gate → still called."""

        class NonFunctionHook:
            def __call__(self, p: HookPayload) -> HookDecision:
                return HookDecision.allow()

        hook = NonFunctionHook()
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock):
            result = await run_hook_chain(
                _p("02-Architecture/01-UX/01-tokens.md"),
                hooks=(hook,),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=None,
            )
        # NonFunctionHook has no __code__ → not detected as phase_gate → called → allow
        assert result.decision == "allow"

    async def test_resolve_user_falls_back_on_subprocess_error(self, tmp_path) -> None:
        """_resolve_user falls back to USERNAME env when subprocess raises OSError."""
        journal_path = tmp_path / "journal.log"
        with (
            patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j,
            patch("sdlc.hooks.runner.subprocess.run", side_effect=OSError("no git")),
            patch("sdlc.hooks.runner.os.environ", {"USERNAME": "fallback-user"}),
        ):
            result = await run_hook_chain(
                _p("02-Architecture/01-UX/01-tokens.md"),
                hooks=(_make_phase_gate(tmp_path),),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=journal_path,
            )
        assert result.decision == "allow"
        entry = mock_j.call_args.args[0]
        assert entry.payload["user"] == "fallback-user"

    async def test_resolve_user_falls_back_when_git_returns_nonzero(self, tmp_path) -> None:
        """_resolve_user falls back to USERNAME when git exits non-zero (no email configured)."""
        from unittest.mock import MagicMock

        journal_path = tmp_path / "journal.log"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with (
            patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j,
            patch("sdlc.hooks.runner.subprocess.run", return_value=mock_result),
            patch("sdlc.hooks.runner.os.environ", {"USERNAME": "env-user"}),
        ):
            result = await run_hook_chain(
                _p("02-Architecture/01-UX/01-tokens.md"),
                hooks=(_make_phase_gate(tmp_path),),
                bypass_phase_gate=True,
                justification="real reason here",
                journal_path=journal_path,
            )
        assert result.decision == "allow"
        entry = mock_j.call_args.args[0]
        assert entry.payload["user"] == "env-user"
