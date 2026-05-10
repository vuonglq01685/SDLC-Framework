"""Unit tests for ``sdlc.claude_hooks.pre_tool_use`` (AC3, AC4, Story 2A.6 Task 2.2).

Tests are RED until Task 2.4 ships ``src/sdlc/claude_hooks/pre_tool_use.py``.

The module is stdlib-only at runtime; tests mock subprocess.run to avoid
real ``sdlc hook-check`` subprocess calls.

Coverage targets (AC12): ≥ 95% on pre_tool_use.py.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ALLOW_ENGINE_RESP = json.dumps(
    {"decision": "allow", "hook_name": None, "reason": None, "error_code": None}
).encode()

_DENY_ENGINE_RESP = json.dumps(
    {
        "decision": "deny",
        "hook_name": "naming_validator",
        "reason": "naming violation: 'EPC_typo' does not match epic id regex",
        "error_code": "naming_violation",
    }
).encode()

_WRITE_ENVELOPE = json.dumps(
    {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "01-Requirement/04-Epics/EPIC-foo-bar.json",
            "content": "{}",
        },
        "cwd": "/repo",
    }
)

_EDIT_ENVELOPE = json.dumps(
    {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "01-Requirement/04-Epics/EPIC-foo-bar.json",
            "old_string": "old",
            "new_string": "new",
        },
        "cwd": "/repo",
    }
)

_READ_ENVELOPE = json.dumps(
    {
        "tool_name": "Read",
        "tool_input": {"file_path": "01-Requirement/04-Epics/EPIC-foo-bar.json"},
        "cwd": "/repo",
    }
)


def _make_subprocess_result(
    stdout: bytes = _ALLOW_ENGINE_RESP, returncode: int = 0
) -> CompletedProcess[bytes]:
    result: CompletedProcess[bytes] = MagicMock(spec=CompletedProcess)
    result.stdout = stdout
    result.returncode = returncode
    return result


def _run_main(stdin_json: str, *, subprocess_stdout: bytes = _ALLOW_ENGINE_RESP) -> tuple[str, int]:
    """Run pre_tool_use.main() with mocked stdin; return (stdout_text, exit_code)."""
    from sdlc.claude_hooks.pre_tool_use import main

    captured_out: list[str] = []
    mock_stdin = io.StringIO(stdin_json)
    mock_print = MagicMock(side_effect=lambda *a, **kw: captured_out.append(str(a[0])))

    exit_code = 0
    with (
        patch("sys.stdin", mock_stdin),
        patch("builtins.print", mock_print),
        patch(
            "subprocess.run",
            return_value=_make_subprocess_result(stdout=subprocess_stdout),
        ),
    ):
        try:
            main()
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 0

    return "\n".join(captured_out), exit_code


# ---------------------------------------------------------------------------
# Fast-path allow (non-write tools)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFastPathAllow:
    def test_read_tool_fast_path_exits_0(self) -> None:
        """Read → fast-path allow, no subprocess."""
        _, code = _run_main(_READ_ENVELOPE)
        assert code == 0

    def test_read_tool_no_subprocess_call(self) -> None:
        """Read → subprocess.run must NOT be called (performance budget)."""
        from sdlc.claude_hooks.pre_tool_use import main

        mock_stdin = io.StringIO(_READ_ENVELOPE)
        with (
            patch("sys.stdin", mock_stdin),
            patch("subprocess.run") as mock_sub,
            contextlib.suppress(SystemExit),
        ):
            main()
        mock_sub.assert_not_called()

    def test_bash_tool_fast_path_exits_0(self) -> None:
        """Bash → fast-path allow, no subprocess."""
        env = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/repo"})
        _, code = _run_main(env)
        assert code == 0

    def test_grep_tool_fast_path_exits_0(self) -> None:
        """Grep → fast-path allow."""
        env = json.dumps({"tool_name": "Grep", "tool_input": {}, "cwd": "/repo"})
        _, code = _run_main(env)
        assert code == 0

    def test_fast_path_envelope_decision_approve(self) -> None:
        """Fast-path allow emits decision=approve."""
        stdout, _ = _run_main(_READ_ENVELOPE)
        assert json.loads(stdout)["decision"] == "approve"


# ---------------------------------------------------------------------------
# Write-tool triggers chain
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWriteToolTriggersChain:
    def test_write_tool_calls_subprocess(self) -> None:
        """Write → subprocess.run IS called (hook chain round-trip)."""
        from sdlc.claude_hooks.pre_tool_use import main

        mock_stdin = io.StringIO(_WRITE_ENVELOPE)
        with (
            patch("sys.stdin", mock_stdin),
            patch("builtins.print"),
            patch("subprocess.run", return_value=_make_subprocess_result()) as mock_sub,
            contextlib.suppress(SystemExit),
        ):
            main()
        mock_sub.assert_called_once()

    def test_edit_tool_calls_subprocess(self) -> None:
        """Edit → subprocess.run called."""
        from sdlc.claude_hooks.pre_tool_use import main

        mock_stdin = io.StringIO(_EDIT_ENVELOPE)
        with (
            patch("sys.stdin", mock_stdin),
            patch("builtins.print"),
            patch("subprocess.run", return_value=_make_subprocess_result()) as mock_sub,
            contextlib.suppress(SystemExit),
        ):
            main()
        mock_sub.assert_called_once()

    def test_multiedit_tool_calls_subprocess(self) -> None:
        """MultiEdit → subprocess.run called."""
        env = json.dumps(
            {
                "tool_name": "MultiEdit",
                "tool_input": {"file_path": "foo.md", "edits": []},
                "cwd": "/repo",
            }
        )
        from sdlc.claude_hooks.pre_tool_use import main

        mock_stdin = io.StringIO(env)
        with (
            patch("sys.stdin", mock_stdin),
            patch("builtins.print"),
            patch("subprocess.run", return_value=_make_subprocess_result()) as mock_sub,
            contextlib.suppress(SystemExit),
        ):
            main()
        mock_sub.assert_called_once()

    def test_write_allow_exits_0(self) -> None:
        """Write + engine allow → exit 0."""
        _, code = _run_main(_WRITE_ENVELOPE, subprocess_stdout=_ALLOW_ENGINE_RESP)
        assert code == 0

    def test_write_deny_exits_1(self) -> None:
        """Write + engine deny → exit 1."""
        _, code = _run_main(_WRITE_ENVELOPE, subprocess_stdout=_DENY_ENGINE_RESP)
        assert code == 1

    def test_write_deny_envelope_decision_block(self) -> None:
        """Write + engine deny → Claude envelope decision=block."""
        stdout, _ = _run_main(_WRITE_ENVELOPE, subprocess_stdout=_DENY_ENGINE_RESP)
        assert json.loads(stdout)["decision"] == "block"


# ---------------------------------------------------------------------------
# Path resolution (AC4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPathResolution:
    def test_relative_path_accepted(self, tmp_path: Path) -> None:
        """Relative path → accepted and passed to subprocess."""
        env = json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "src/foo.py", "content": "x"},
                "cwd": str(tmp_path),
            }
        )
        _, code = _run_main(env)
        assert code == 0  # allow path with mocked subprocess

    def test_absolute_path_under_cwd_relativized(self, tmp_path: Path) -> None:
        """Absolute path under cwd → relativized, no denial."""
        abs_path = str(tmp_path / "src" / "foo.py")
        env = json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": abs_path, "content": "x"},
                "cwd": str(tmp_path),
            }
        )
        _, code = _run_main(env)
        assert code == 0

    def test_absolute_path_outside_cwd_denied(self, tmp_path: Path) -> None:
        """Absolute path outside cwd → path_outside_repo deny, exit 1."""
        outside_path = "/completely/outside/repo/file.txt"
        env = json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": outside_path, "content": "x"},
                "cwd": str(tmp_path),
            }
        )
        stdout, code = _run_main(env)
        assert code == 1
        envelope = json.loads(stdout)
        assert envelope.get("error_code") == "path_outside_repo"

    def test_cwd_absent_falls_back_to_os_getcwd(self) -> None:
        """cwd field absent → falls back to os.getcwd() as anchor."""
        from sdlc.claude_hooks.pre_tool_use import main

        env = json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "src/foo.py", "content": "x"},
                # no "cwd" key
            }
        )
        mock_stdin = io.StringIO(env)
        with (
            patch("sys.stdin", mock_stdin),
            patch("builtins.print"),
            patch("subprocess.run", return_value=_make_subprocess_result()) as mock_sub,
            patch("os.getcwd", return_value="/repo"),
            contextlib.suppress(SystemExit),
        ):
            main()
        mock_sub.assert_called_once()

    def test_cwd_field_used_as_anchor(self, tmp_path: Path) -> None:
        """When cwd is present in envelope, it's used (not os.getcwd())."""
        from sdlc.claude_hooks.pre_tool_use import main

        env = json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "src/foo.py", "content": "x"},
                "cwd": str(tmp_path),
            }
        )
        mock_stdin = io.StringIO(env)
        getcwd_mock = MagicMock(return_value="/should-not-be-called")
        with (
            patch("sys.stdin", mock_stdin),
            patch("builtins.print"),
            patch("subprocess.run", return_value=_make_subprocess_result()),
            patch("os.getcwd", getcwd_mock),
            contextlib.suppress(SystemExit),
        ):
            main()
        getcwd_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Fail-open error handling (AC4 last-And, AC9)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFailOpenErrorHandling:
    def test_subprocess_timeout_fail_open(self) -> None:
        """Subprocess timeout → fail-open (approve) with WARN to stderr."""
        import subprocess

        from sdlc.claude_hooks.pre_tool_use import main

        mock_stdin = io.StringIO(_WRITE_ENVELOPE)
        captured_out: list[str] = []
        captured_err: list[str] = []

        with (
            patch("sys.stdin", mock_stdin),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: (
                    captured_err.append(str(a[0]))
                    if kw.get("file") is sys.stderr
                    else captured_out.append(str(a[0]))
                ),
            ),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=10.0)),
            contextlib.suppress(SystemExit),
        ):
            main()

        # fail-open: at least one print with "approve"
        approve_lines = [line for line in captured_out if "approve" in line]
        assert approve_lines, "expected fail-open approve envelope in stdout"

    def test_subprocess_invalid_json_fail_open(self) -> None:
        """Subprocess returns non-JSON stdout → fail-open approve."""
        stdout, _ = _run_main(_WRITE_ENVELOPE, subprocess_stdout=b"not-valid-json")
        assert json.loads(stdout)["decision"] == "approve"

    def test_missing_tool_input_field_fail_open(self) -> None:
        """Missing tool_input.file_path → fail-open approve."""
        env = json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {},  # no file_path
                "cwd": "/repo",
            }
        )
        stdout, _ = _run_main(env)
        assert json.loads(stdout)["decision"] == "approve"

    def test_invalid_stdin_json_fail_open(self) -> None:
        """Non-JSON stdin envelope → fail-open approve (AC4 unrecognised schema)."""
        stdout, _ = _run_main("not-json-at-all")
        assert json.loads(stdout)["decision"] == "approve"
