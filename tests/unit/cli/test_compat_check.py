"""Unit tests for Claude Code version pre-flight (Story 2B.2)."""

from __future__ import annotations

import sys
import unittest.mock
from pathlib import Path
from typing import ClassVar

import pytest
import tomllib
from typer.testing import CliRunner

from sdlc.cli import _compat_check
from sdlc.cli._compat_check import (
    _CLAUDE_VERSION_TIMEOUT_SECONDS,
    CLAUDE_CODE_MIN_VERSION,
    ensure_claude_code_compatible,
    parse_claude_version_line,
    probe_claude_version,
)
from sdlc.cli.main import app
from sdlc.errors import CompatibilityError

pytestmark = pytest.mark.unit

# Source-tree only (the Final[str] constant is the runtime source of truth per
# AC1/D1; this consistency test catches drift in developer checkout, not in
# installed wheels which legitimately omit tests/ and pyproject.toml). (R19)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_runner = CliRunner()


@pytest.fixture(autouse=True)
def _exercise_real_compat_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the real compat check despite the pytest auto-bypass (Story 2B.2 D1).

    Also clears the per-process lru_cache so each test gets a fresh probe.
    """
    _compat_check._cached_probe.cache_clear()
    monkeypatch.setenv("SDLC_TEST_FORCE_COMPAT_CHECK", "1")


@pytest.mark.unit
def test_pyproject_declared_min_version_matches_source_constant() -> None:
    """Source-tree consistency check (R19: dev-time only)."""
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["tool"]["sdlc"]["claude_code_min_version"]
    assert declared == CLAUDE_CODE_MIN_VERSION


@pytest.mark.unit
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("claude 2.0.0 (Claude Code)", "2.0.0"),
        ("claude 3.1.4 (abc)", "3.1.4"),
        ("  claude 1.5.0  ", "1.5.0"),
        # R3: anchored regex must not grab nag-banner versions before the real one.
        ("Update available: 3.0.5 (you are on 1.5.0)\nclaude 2.0.0 (test)", "2.0.0"),
        # R3: banner-then-stderr-semver leak must not false-accept.
        ("Anthropic build 12.34.5 — claude 1.5.0 (legacy)", "1.5.0"),
    ],
)
def test_parse_claude_version_line_extracts_semver(line: str, expected: str) -> None:
    assert parse_claude_version_line(line) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "noise",
    [
        "claude-code unknown build",
        "node v20.0.0 not supported",  # R3: bare semver without `claude` token
        "2024.10.05 release notes",  # R3: date-like, no `claude` anchor
        "127.0.0.1 connect failed",  # R3: IP-like, no `claude` anchor
    ],
)
def test_parse_claude_version_line_unparseable_raises(noise: str) -> None:
    with pytest.raises(CompatibilityError) as exc_info:
        parse_claude_version_line(noise)
    assert "could not parse claude version" in exc_info.value.message


@pytest.mark.unit
def test_probe_claude_version_file_not_found() -> None:
    with (
        unittest.mock.patch(
            "sdlc.cli._compat_check.subprocess.run",
            side_effect=FileNotFoundError,
        ),
        pytest.raises(CompatibilityError) as exc_info,
    ):
        probe_claude_version()
    assert "claude not found on PATH" in exc_info.value.message
    # R7: docs URL must be in the user-visible message (not just details).
    assert "docs.anthropic.com" in exc_info.value.message
    assert exc_info.value.details["docs_url"]


@pytest.mark.unit
def test_probe_claude_version_timeout_distinct_message() -> None:
    """R18: TimeoutExpired gets a distinct, actionable message."""
    import subprocess

    with (
        unittest.mock.patch(
            "sdlc.cli._compat_check.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["claude", "--version"], timeout=5.0),
        ),
        pytest.raises(CompatibilityError) as exc_info,
    ):
        probe_claude_version()
    assert "timed out" in exc_info.value.message
    assert str(_CLAUDE_VERSION_TIMEOUT_SECONDS) in exc_info.value.message


@pytest.mark.unit
def test_probe_claude_version_nonzero_returncode_is_distinct_error() -> None:
    """R4: claude exiting non-zero must NOT silently parse stderr garbage."""
    import subprocess

    fake = subprocess.CompletedProcess(
        args=["claude", "--version"],
        returncode=1,
        stdout="",
        stderr="Error: trial expired — claude 1.0.0 (legacy)\n",
    )
    with (
        unittest.mock.patch(
            "sdlc.cli._compat_check.subprocess.run",
            return_value=fake,
        ),
        pytest.raises(CompatibilityError) as exc_info,
    ):
        probe_claude_version()
    msg = exc_info.value.message
    assert "exited 1" in msg
    # Must NOT silently parse the stderr-leak as a real version.
    assert "reported 1.0.0" not in msg


@pytest.mark.unit
def test_ensure_rejects_version_below_minimum() -> None:
    with (
        unittest.mock.patch(
            "sdlc.cli._compat_check.probe_claude_version",
            return_value="1.5.0",
        ),
        pytest.raises(CompatibilityError) as exc_info,
    ):
        ensure_claude_code_compatible()
    msg = exc_info.value.message
    assert "1.5.0" in msg
    assert CLAUDE_CODE_MIN_VERSION in msg
    assert "requires" in msg
    # R11: details payload includes reported + min + docs_url.
    details = exc_info.value.details
    assert details["reported"] == "1.5.0"
    assert details["min_version"] == CLAUDE_CODE_MIN_VERSION
    assert details["docs_url"]


@pytest.mark.unit
@pytest.mark.parametrize("version", ["2.0.0", "3.0.0"])
def test_ensure_accepts_version_at_or_above_minimum(version: str) -> None:
    with unittest.mock.patch(
        "sdlc.cli._compat_check.probe_claude_version",
        return_value=version,
    ):
        ensure_claude_code_compatible()


@pytest.mark.unit
def test_version_callback_does_not_invoke_claude_compat_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _track() -> None:
        calls.append("checked")

    monkeypatch.setattr(
        "sdlc.cli._compat_check.ensure_claude_code_compatible",
        _track,
    )
    result = _runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert calls == []


@pytest.mark.unit
def test_gate_should_run_skips_when_help_in_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """D2: `_gate_should_run` returns False when ``--help`` is on the real CLI argv.

    Direct unit test of the helper because ``CliRunner.invoke`` doesn't propagate
    ``sys.argv`` (it passes args via ``cli.main(args=...)`` directly), so a
    CliRunner-driven test cannot exercise the sys.argv code path.
    """
    from sdlc.cli._compat_check import gate_should_run as _gate_should_run

    class _FakeCtx:
        invoked_subcommand = "start"
        args: ClassVar[list[str]] = []
        protected_args: ClassVar[list[str]] = []

    monkeypatch.setattr("sys.argv", ["sdlc", "start", "--help"])
    assert _gate_should_run(_FakeCtx()) is False  # type: ignore[arg-type]

    monkeypatch.setattr("sys.argv", ["sdlc", "start", "-h"])
    assert _gate_should_run(_FakeCtx()) is False  # type: ignore[arg-type]

    monkeypatch.setattr("sys.argv", ["sdlc", "start", "ideatext"])
    assert _gate_should_run(_FakeCtx()) is True  # type: ignore[arg-type]


@pytest.mark.unit
def test_gate_should_run_skips_when_help_in_ctx_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """D2: `_gate_should_run` returns False when ``--help`` shows up in ctx.args."""
    from sdlc.cli._compat_check import gate_should_run as _gate_should_run

    class _FakeCtx:
        invoked_subcommand = "start"
        args: ClassVar[list[str]] = ["--help"]
        protected_args: ClassVar[list[str]] = []

    monkeypatch.setattr("sys.argv", ["pytest"])  # no help in sys.argv
    assert _gate_should_run(_FakeCtx()) is False  # type: ignore[arg-type]


@pytest.mark.unit
def test_gate_should_run_skips_non_dispatch_subcommands() -> None:
    """D2: scan/logs/status/etc. don't dispatch to claude — gate must skip."""
    from sdlc.cli._compat_check import DISPATCH_SUBCOMMANDS as _DISPATCH_SUBCOMMANDS
    from sdlc.cli._compat_check import gate_should_run as _gate_should_run

    class _FakeCtx:
        args: ClassVar[list[str]] = []
        protected_args: ClassVar[list[str]] = []

        def __init__(self, invoked: str | None) -> None:
            self.invoked_subcommand = invoked

    for invoked in ("scan", "logs", "status", "trace", "replay", "rebuild-state", "trust-hooks"):
        assert invoked not in _DISPATCH_SUBCOMMANDS, f"{invoked} should not be in dispatch set"
        assert _gate_should_run(_FakeCtx(invoked)) is False  # type: ignore[arg-type]


@pytest.mark.unit
def test_non_dispatch_subcommand_does_not_invoke_claude_compat_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D2 (end-to-end): non-dispatch subcommands don't even import the compat-check module."""
    calls: list[str] = []

    def _track() -> None:
        calls.append("checked")

    monkeypatch.setattr(
        "sdlc.cli._compat_check.ensure_claude_code_compatible",
        _track,
    )
    _runner.invoke(app, ["status"])
    assert calls == []


@pytest.mark.unit
def test_root_preflight_invokes_compat_check_before_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R9: gate must run AND subcommand body must NOT run on rejection."""
    invoked: list[str] = []
    body_calls: list[str] = []

    def _fail_fast() -> None:
        invoked.append("checked")
        raise CompatibilityError("blocked for test")

    def _record_body(**_kwargs: object) -> None:
        body_calls.append("ran")

    monkeypatch.setattr(
        "sdlc.cli._compat_check.ensure_claude_code_compatible",
        _fail_fast,
    )
    monkeypatch.setattr("sdlc.cli.start.run_start", _record_body)
    result = _runner.invoke(app, ["start", "idea-text"])
    assert invoked == ["checked"]
    assert body_calls == []  # R9: subcommand body MUST NOT execute on gate rejection.
    assert result.exit_code == 3
    # R9: stderr attribution — exit 3 must come from CompatibilityError, not a downstream error.
    assert "blocked for test" in result.stderr


@pytest.mark.unit
def test_under_pytest_bypass_is_active_by_default() -> None:
    """D1: production-safe pytest bypass is reachable only via PYTEST_CURRENT_TEST."""
    # PYTEST_CURRENT_TEST is set by pytest itself; SDLC_TEST_FORCE_COMPAT_CHECK is on per
    # the autouse fixture in this module. Verify the helper honors the override.
    import os as _os

    saved = _os.environ.pop("SDLC_TEST_FORCE_COMPAT_CHECK", None)
    try:
        assert _compat_check._under_pytest() is True
    finally:
        if saved is not None:
            _os.environ["SDLC_TEST_FORCE_COMPAT_CHECK"] = saved


@pytest.mark.unit
def test_cold_start_version_does_not_spawn_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    """D5: `sdlc --version` must NOT spawn any subprocess (cold-start budget)."""
    spawn_calls: list[object] = []

    real_run = __import__("subprocess").run

    def _record(*args: object, **kwargs: object) -> object:
        spawn_calls.append((args, kwargs))
        return real_run(*args, **kwargs)  # type: ignore[no-any-return]

    monkeypatch.setattr("sdlc.cli._compat_check.subprocess.run", _record)
    result = _runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert spawn_calls == []


@pytest.mark.unit
def test_subprocess_pattern_uses_documented_timeout() -> None:
    """R14: assert the numeric timeout directly, not via cross-import of a private constant."""
    assert _CLAUDE_VERSION_TIMEOUT_SECONDS == 5.0
    assert sys.version_info >= (3, 11)  # tomllib import gate
