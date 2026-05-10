"""Unit tests for ``sdlc hook-check`` subcommand (AC2, Story 2A.6 Task 1.1).

Tests are written RED-FIRST per ADR-026 §1 (TDD-first commit ordering).
They import from ``sdlc.cli.hook_check`` which does not exist yet → all fail
until Task 1.3 ships the implementation.

Coverage targets (AC12): 100% on ``cli/hook_check.py``.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer

from sdlc.errors import ConfigError
from sdlc.hooks.runner import HookDecision

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ALLOW_PAYLOAD: str = json.dumps(
    {
        "schema_version": 1,
        "hook_name": "naming_validator",
        "target_path": "01-Requirement/04-Epics/EPIC-foo-bar.json",
        "target_kind": "write_intent",
        "content_hash_before": None,
        "write_intent": "create epic",
    }
)

_DENY_PAYLOAD: str = json.dumps(
    {
        "schema_version": 1,
        "hook_name": "naming_validator",
        "target_path": "01-Requirement/04-Epics/EPC_typo.json",
        "target_kind": "write_intent",
        "content_hash_before": None,
        "write_intent": "create epic",
    }
)

_DECISION_ALLOW = HookDecision.allow()
_DECISION_DENY = HookDecision.deny(
    hook_name="naming_validator",
    reason="naming violation: 'EPC_typo' does not match epic id regex",
    error_code="naming_violation",
)


def _make_ctx() -> typer.Context:
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"json": False, "no_color": False}
    return ctx


def _run_hook_check_with_stdin(
    payload_json: str,
    tmp_path: Path,
    decision: HookDecision = _DECISION_ALLOW,
    hook_names: tuple[str, ...] = ("naming_validator",),
    registry_error: ConfigError | None = None,
) -> tuple[str, int]:
    """Call run_hook_check with mocked stdin and collect (stdout_text, exit_code).

    Returns (stdout_text, exit_code) where exit_code is 0 (no Exit raised), 1, or 2.
    """
    from sdlc.cli.hook_check import run_hook_check  # import under test

    mock_stdin = io.StringIO(payload_json)
    ctx = _make_ctx()
    captured_output: list[str] = []

    def _fake_emit(envelope: dict[str, object]) -> None:  # type: ignore[type-arg]
        captured_output.append(json.dumps(envelope, sort_keys=True, separators=(",", ":")))

    with (
        patch("sys.stdin", mock_stdin),
        patch("sdlc.cli.hook_check._get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.cli.hook_check._emit", side_effect=_fake_emit),
        patch("sdlc.config.hooks.load_hook_registry", return_value=hook_names)
        if registry_error is None
        else patch(
            "sdlc.config.hooks.load_hook_registry",
            side_effect=registry_error,
        ),
        patch("sdlc.hooks.runner.run_hook_chain", new_callable=AsyncMock, return_value=decision),
    ):
        try:
            run_hook_check(ctx=ctx)
            exit_code = 0
        except typer.Exit as exc:
            exit_code = exc.exit_code

    return "\n".join(captured_output), exit_code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHookCheckAllowPath:
    def test_stdin_allow_emits_envelope_exit_0(self, tmp_path: Path) -> None:
        """Stdin canonical form: valid payload → allow → emit envelope + exit 0."""
        stdout, code = _run_hook_check_with_stdin(_ALLOW_PAYLOAD, tmp_path, _DECISION_ALLOW)
        assert code == 0
        envelope = json.loads(stdout)
        assert envelope["decision"] == "allow"
        assert envelope["error_code"] is None
        assert envelope["hook_name"] is None
        assert envelope["reason"] is None

    def test_allow_envelope_keys_are_sorted(self, tmp_path: Path) -> None:
        """Envelope JSON must have sorted keys (byte-stable round-trip per AC1)."""
        stdout, _ = _run_hook_check_with_stdin(_ALLOW_PAYLOAD, tmp_path, _DECISION_ALLOW)
        keys = list(json.loads(stdout).keys())
        assert keys == sorted(keys)


@pytest.mark.unit
class TestHookCheckDenyPath:
    def test_stdin_deny_emits_envelope_exit_1(self, tmp_path: Path) -> None:
        """Deny decision emits deny envelope and exits 1."""
        stdout, code = _run_hook_check_with_stdin(_DENY_PAYLOAD, tmp_path, _DECISION_DENY)
        assert code == 1
        envelope = json.loads(stdout)
        assert envelope["decision"] == "deny"
        assert envelope["error_code"] == "naming_violation"
        assert envelope["hook_name"] == "naming_validator"
        assert "naming violation" in (envelope["reason"] or "")

    def test_deny_preserves_error_code(self, tmp_path: Path) -> None:
        """error_code propagated from HookDecision.deny to the stdout envelope."""
        custom_deny = HookDecision.deny(
            hook_name="phase_gate",
            reason="phase-gate violation",
            error_code="phase_gate_violation",
        )
        stdout, code = _run_hook_check_with_stdin(_ALLOW_PAYLOAD, tmp_path, custom_deny)
        assert code == 1
        assert json.loads(stdout)["error_code"] == "phase_gate_violation"


@pytest.mark.unit
class TestHookCheckArgvFallback:
    def test_argv_used_when_stdin_is_tty(self, tmp_path: Path) -> None:
        """When stdin.isatty() is True, argv[1] is used as the payload."""
        from sdlc.cli.hook_check import run_hook_check

        tty_stdin = io.StringIO("")
        tty_stdin.isatty = lambda: True  # type: ignore[method-assign]
        ctx = _make_ctx()
        captured: list[str] = []

        def _fake_emit(envelope: dict[str, object]) -> None:  # type: ignore[type-arg]
            captured.append(json.dumps(envelope, sort_keys=True, separators=(",", ":")))

        with (
            patch("sys.stdin", tty_stdin),
            patch("sys.argv", ["sdlc", _ALLOW_PAYLOAD]),
            patch("sdlc.cli.hook_check._get_repo_root_or_cwd", return_value=tmp_path),
            patch("sdlc.cli.hook_check._emit", side_effect=_fake_emit),
            patch("sdlc.config.hooks.load_hook_registry", return_value=("naming_validator",)),
            patch(
                "sdlc.hooks.runner.run_hook_chain",
                new_callable=AsyncMock,
                return_value=_DECISION_ALLOW,
            ),
            contextlib.suppress(typer.Exit),
        ):
            run_hook_check(ctx=ctx)

        assert captured, "expected at least one emitted envelope"
        assert json.loads(captured[0])["decision"] == "allow"


@pytest.mark.unit
class TestHookCheckInvalidPayload:
    def test_bad_json_exits_2_invalid_payload(self, tmp_path: Path) -> None:
        """Non-JSON input → error_code=invalid_payload, exit 2."""
        stdout, code = _run_hook_check_with_stdin("not-valid-json", tmp_path)
        assert code == 2
        envelope = json.loads(stdout)
        assert envelope["decision"] == "deny"
        assert envelope["error_code"] == "invalid_payload"

    def test_validation_error_exits_2_with_reason(self, tmp_path: Path) -> None:
        """Valid JSON but wrong pydantic schema → error_code=invalid_payload + reason string."""
        bad_payload = json.dumps({"schema_version": 99, "hook_name": "x"})
        stdout, code = _run_hook_check_with_stdin(bad_payload, tmp_path)
        assert code == 2
        envelope = json.loads(stdout)
        assert envelope["error_code"] == "invalid_payload"
        assert envelope["reason"]  # non-empty reason string from pydantic ValidationError

    def test_empty_stdin_exits_2(self, tmp_path: Path) -> None:
        """Empty stdin (no payload) → invalid_payload exit 2."""
        stdout, code = _run_hook_check_with_stdin("", tmp_path)
        assert code == 2
        assert json.loads(stdout)["error_code"] == "invalid_payload"


@pytest.mark.unit
class TestHookCheckRegistryEdgeCases:
    def test_empty_hooks_registry_allows(self, tmp_path: Path) -> None:
        """[tool.sdlc.hooks] absent (empty tuple) → empty chain → allow path."""
        stdout, code = _run_hook_check_with_stdin(
            _ALLOW_PAYLOAD,
            tmp_path,
            _DECISION_ALLOW,
            hook_names=(),
        )
        assert code == 0
        assert json.loads(stdout)["decision"] == "allow"

    def test_registry_error_exits_2(self, tmp_path: Path) -> None:
        """ConfigError from load_hook_registry → error_code=registry_error, exit 2."""
        err = ConfigError("unknown hook: 'bad_hook'", details={"step": "test"})
        stdout, code = _run_hook_check_with_stdin(
            _ALLOW_PAYLOAD,
            tmp_path,
            registry_error=err,
        )
        assert code == 2
        envelope = json.loads(stdout)
        assert envelope["decision"] == "deny"
        assert envelope["error_code"] == "registry_error"
        assert "bad_hook" in (envelope["reason"] or "")


@pytest.mark.unit
class TestHookCheckJsonFlagNoOp:
    def test_json_flag_does_not_change_output_shape(self, tmp_path: Path) -> None:
        """--json global flag is a no-op; output envelope shape is unchanged."""
        from sdlc.cli.hook_check import run_hook_check

        mock_stdin = io.StringIO(_ALLOW_PAYLOAD)
        ctx = _make_ctx()
        ctx.obj["json"] = True  # simulate --json flag set
        captured: list[str] = []

        def _fake_emit(envelope: dict[str, object]) -> None:  # type: ignore[type-arg]
            captured.append(json.dumps(envelope, sort_keys=True, separators=(",", ":")))

        with (
            patch("sys.stdin", mock_stdin),
            patch("sdlc.cli.hook_check._get_repo_root_or_cwd", return_value=tmp_path),
            patch("sdlc.cli.hook_check._emit", side_effect=_fake_emit),
            patch("sdlc.config.hooks.load_hook_registry", return_value=("naming_validator",)),
            patch(
                "sdlc.hooks.runner.run_hook_chain",
                new_callable=AsyncMock,
                return_value=_DECISION_ALLOW,
            ),
            contextlib.suppress(typer.Exit),
        ):
            run_hook_check(ctx=ctx)

        assert captured
        envelope = json.loads(captured[0])
        # Same 4 keys as without --json; no extra "command" wrapper
        assert set(envelope.keys()) == {"decision", "error_code", "hook_name", "reason"}
