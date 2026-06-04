"""Integration tests for ``sdlc hook-check`` real subprocess invocation (AC2, Story 2A.6 Task 1.2).

Exercises the command end-to-end via stdin piping — the canonical form mandated by AC1
(stdout/stdin over argv avoids Windows shell-escaping and argv length limits).

Tests are RED until Task 1.3 ships ``src/sdlc/cli/hook_check.py``.

Windows-safe: all subprocess calls use ``input=``, ``text=True``, ``encoding="utf-8"``
— no shell-level piping via ``echo`` (not portable across Windows shells).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from _clihelper import sdlc_uv_argv

_UV_RUN = sdlc_uv_argv()

# ---------------------------------------------------------------------------
# Canonical test payloads
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


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path: Path, *, hooks: list[str] | None = None) -> Path:
    """Write a minimal pyproject.toml in tmp_path.

    When hooks is non-empty, adds [tool.sdlc.hooks] pre_write so hook_check
    exercises real hook dispatch rather than the empty-chain fast-path.

    No git init needed: ``_get_repo_root_or_cwd`` falls back to cwd when git
    is absent, and pytest's tmp_path sits outside the SDLC-Framework repo tree.
    """
    hook_section = ""
    if hooks:
        pre_write_toml = json.dumps(hooks)  # ["naming_validator"] → JSON list
        hook_section = f"\n[tool.sdlc.hooks]\npre_write = {pre_write_toml}\n"

    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "test"\nversion = "0.1.0"\n{hook_section}',
        encoding="utf-8",
    )
    return tmp_path


def _run_hook_check(payload_json: str, workspace: Path) -> subprocess.CompletedProcess[str]:
    """Run ``sdlc hook-check`` with payload piped to stdin; Windows-safe."""
    return subprocess.run(
        [*_UV_RUN, "hook-check"],
        input=payload_json,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=workspace,
    )


# ---------------------------------------------------------------------------
# Allow path
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestHookCheckAllowSubprocess:
    def test_allow_exits_0(self, tmp_path: Path) -> None:
        """Valid payload with naming_validator → allow → exit 0."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_ALLOW_PAYLOAD, ws)
        assert result.returncode == 0, f"stderr={result.stderr!r}"

    def test_allow_envelope_decision(self, tmp_path: Path) -> None:
        """Allow envelope carries decision=allow."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_ALLOW_PAYLOAD, ws)
        envelope = json.loads(result.stdout.strip())
        assert envelope["decision"] == "allow"

    def test_allow_envelope_error_code_null(self, tmp_path: Path) -> None:
        """Allow envelope: error_code=null."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_ALLOW_PAYLOAD, ws)
        envelope = json.loads(result.stdout.strip())
        assert envelope["error_code"] is None

    def test_allow_envelope_has_four_keys(self, tmp_path: Path) -> None:
        """Envelope must have exactly {decision, error_code, hook_name, reason}."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_ALLOW_PAYLOAD, ws)
        envelope = json.loads(result.stdout.strip())
        assert set(envelope.keys()) == {"decision", "error_code", "hook_name", "reason"}

    def test_empty_registry_allow_exits_0(self, tmp_path: Path) -> None:
        """Empty hook registry (no [tool.sdlc.hooks]) → chain empty → allow."""
        ws = _make_workspace(tmp_path)
        result = _run_hook_check(_ALLOW_PAYLOAD, ws)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Deny path
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestHookCheckDenySubprocess:
    def test_deny_exits_1(self, tmp_path: Path) -> None:
        """Malformed epic id → naming_validator deny → exit 1."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_DENY_PAYLOAD, ws)
        assert result.returncode == 1, f"stderr={result.stderr!r}"

    def test_deny_envelope_decision(self, tmp_path: Path) -> None:
        """Deny envelope carries decision=deny."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_DENY_PAYLOAD, ws)
        envelope = json.loads(result.stdout.strip())
        assert envelope["decision"] == "deny"

    def test_deny_envelope_error_code(self, tmp_path: Path) -> None:
        """Deny envelope carries error_code=naming_violation."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_DENY_PAYLOAD, ws)
        envelope = json.loads(result.stdout.strip())
        assert envelope["error_code"] == "naming_violation"

    def test_deny_envelope_reason_nonempty(self, tmp_path: Path) -> None:
        """Deny envelope has a non-empty reason string."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_DENY_PAYLOAD, ws)
        envelope = json.loads(result.stdout.strip())
        assert envelope["reason"]


# ---------------------------------------------------------------------------
# Invalid payload
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestHookCheckInvalidPayloadSubprocess:
    def test_bad_json_exits_2(self, tmp_path: Path) -> None:
        """Non-JSON stdin → invalid_payload → exit 2."""
        ws = _make_workspace(tmp_path)
        result = _run_hook_check("not-valid-json", ws)
        assert result.returncode == 2

    def test_bad_json_envelope_error_code(self, tmp_path: Path) -> None:
        """Non-JSON stdin → envelope error_code=invalid_payload."""
        ws = _make_workspace(tmp_path)
        result = _run_hook_check("not-valid-json", ws)
        envelope = json.loads(result.stdout.strip())
        assert envelope["error_code"] == "invalid_payload"

    def test_schema_mismatch_exits_2(self, tmp_path: Path) -> None:
        """Valid JSON but wrong pydantic schema → exit 2."""
        ws = _make_workspace(tmp_path)
        bad = json.dumps({"schema_version": 99, "hook_name": "x"})
        result = _run_hook_check(bad, ws)
        assert result.returncode == 2

    def test_empty_stdin_exits_2(self, tmp_path: Path) -> None:
        """Empty stdin (no payload at all) → exit 2."""
        ws = _make_workspace(tmp_path)
        result = _run_hook_check("", ws)
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# Exit code propagation + machine-parseability
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestHookCheckExitCodePropagation:
    def test_exit_0_for_allow(self, tmp_path: Path) -> None:
        """Pipe + exit code propagation: allow → 0."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        assert _run_hook_check(_ALLOW_PAYLOAD, ws).returncode == 0

    def test_exit_1_for_deny(self, tmp_path: Path) -> None:
        """Pipe + exit code propagation: deny → 1."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        assert _run_hook_check(_DENY_PAYLOAD, ws).returncode == 1

    def test_exit_2_for_invalid(self, tmp_path: Path) -> None:
        """Pipe + exit code propagation: invalid payload → 2."""
        ws = _make_workspace(tmp_path)
        assert _run_hook_check("not-json", ws).returncode == 2

    def test_stdout_is_valid_json(self, tmp_path: Path) -> None:
        """Stdout MUST be valid JSON — it is parsed by Claude Code's hook machinery."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_ALLOW_PAYLOAD, ws)
        # Must not raise
        parsed = json.loads(result.stdout.strip())
        assert isinstance(parsed, dict)

    def test_envelope_keys_sorted_allow(self, tmp_path: Path) -> None:
        """Envelope JSON must have sorted keys for byte-stable round-trip (AC1)."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_ALLOW_PAYLOAD, ws)
        keys = list(json.loads(result.stdout.strip()).keys())
        assert keys == sorted(keys)

    def test_envelope_keys_sorted_deny(self, tmp_path: Path) -> None:
        """Envelope JSON sorted keys hold on deny path too (AC1)."""
        ws = _make_workspace(tmp_path, hooks=["naming_validator"])
        result = _run_hook_check(_DENY_PAYLOAD, ws)
        keys = list(json.loads(result.stdout.strip()).keys())
        assert keys == sorted(keys)
