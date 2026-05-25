"""Claude Code minimum-version pre-flight for the global CLI callback (Story 2B.2).

Contract: ``ensure_claude_code_compatible`` raises ONLY ``CompatibilityError``.
Every other subprocess/OS condition is converted at this boundary so callers
in ``cli/main.py`` can rely on a single exception class.

Pytest bypass (Story 2B.2 review D1): under pytest the gate is a no-op so
unit/integration tests don't require a real Claude Code binary. Tests that
exercise the gate (``tests/integration/test_claude_version_gate.py``) opt in
via ``SDLC_TEST_FORCE_COMPAT_CHECK=1`` and provide a stub ``claude`` on PATH.
The bypass is reachable ONLY when ``PYTEST_CURRENT_TEST`` is set (a real
pytest-only invariant) — production users cannot disable this gate.
"""

from __future__ import annotations

import os
import re
import string
import subprocess
import sys
from functools import lru_cache
from typing import TYPE_CHECKING, Final

from sdlc.errors import CompatibilityError

if TYPE_CHECKING:
    import typer

# Mirror of pyproject.toml [tool.sdlc] claude_code_min_version (AC1/D1).
CLAUDE_CODE_MIN_VERSION: Final[str] = "2.0.0"

# Subcommands that dispatch to Claude Code (the compat gate guards only these).
# Identified by their ``allow_mock`` parameter — every AI-dispatching command
# carries it per ADR-029. Non-dispatch surfaces (scan/logs/status/trace/replay/
# rebuild-state/trust-hooks/hook-check/verify/next/replan/init/signoff/migrate-v*)
# remain reachable without a real ``claude`` binary so users can read help screens,
# inspect state, and recover broken installs (Story 2B.2 review D2).
DISPATCH_SUBCOMMANDS: Final[frozenset[str]] = frozenset(
    {"research", "start", "epics", "stories", "ux", "architect", "bootstrap", "break", "task"}
)
HELP_FLAGS: Final[frozenset[str]] = frozenset({"--help", "-h"})


def gate_should_run(ctx: typer.Context) -> bool:
    """True only when the invoked subcommand dispatches AND --help is not being parsed.

    Checks Click's parsed subcommand args (``ctx.args`` — populated under
    ``CliRunner.invoke`` and the real-CLI path) AND ``sys.argv`` as a fallback so
    the carve-out works under both invocation modes without relying on
    deprecated Click internals.
    """
    invoked = ctx.invoked_subcommand
    if invoked not in DISPATCH_SUBCOMMANDS:
        return False
    if any(arg in HELP_FLAGS for arg in (ctx.args or [])):
        return False
    return not any(arg in HELP_FLAGS for arg in sys.argv)


def run_pre_flight(ctx: typer.Context) -> None:
    """Run the Claude Code compat gate from the global Typer callback.

    Caller must populate ``ctx.obj`` BEFORE invoking this so the error
    envelope honors ``--json`` / ``--no-color`` (Story 2B.2 review R1).
    Raises ``typer.Exit(3)`` via ``emit_error`` on rejection; no-ops otherwise.
    """
    if not gate_should_run(ctx):
        return
    from sdlc.cli.output import emit_error  # deferred per Architecture §488

    try:
        ensure_claude_code_compatible()
    except CompatibilityError as exc:
        emit_error(exc.code, exc.message, ctx=ctx, details=exc.details)


_CLAUDE_VERSION_TIMEOUT_SECONDS: Final[float] = 5.0
_CLAUDE_DOCS_URL: Final[str] = "https://docs.anthropic.com/en/docs/claude-code"
# Anchored on the literal token ``claude`` so banner numbers / build dates /
# IP-shaped digits / stray semver in stderr cannot false-match (Story 2B.2
# review R3 — was the bare regex ``(\d+\.\d+\.\d+)``).
_VERSION_SEMVER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9_])claude[\s/_-]+(\d+\.\d+\.\d+)"
)
_EXCERPT_MAX_LEN: Final[int] = 120
_PRINTABLE: Final[frozenset[str]] = frozenset(string.printable)
_SEMVER_FIELD_COUNT: Final[int] = 3
_TEST_FORCE_ENV: Final[str] = "SDLC_TEST_FORCE_COMPAT_CHECK"


def _build_compat_details(*, reported: str | None = None) -> dict[str, object]:
    """Common details payload — docs URL, declared minimum, optionally reported.

    Ensures every CompatibilityError this module raises carries a consistent
    machine-readable payload for ``--json`` consumers (Story 2B.2 review R11).
    """
    details: dict[str, object] = {
        "docs_url": _CLAUDE_DOCS_URL,
        "min_version": CLAUDE_CODE_MIN_VERSION,
    }
    if reported is not None:
        details["reported"] = reported
    return details


def _sanitize_excerpt(raw: str) -> str:
    """Strip non-printable characters and truncate for safe inclusion in error messages."""
    flattened = raw.replace("\n", " ").strip()
    sanitized = "".join(ch if ch in _PRINTABLE else "?" for ch in flattened)
    return sanitized[:_EXCERPT_MAX_LEN]


def parse_claude_version_line(stdout: str) -> str:
    """Extract a ``X.Y.Z`` semver anchored to the literal token ``claude`` (AC3/D1)."""
    match = _VERSION_SEMVER_RE.search(stdout)
    if match is None:
        excerpt = _sanitize_excerpt(stdout)
        raise CompatibilityError(
            f"could not parse claude version from: {excerpt!r}",
            details=_build_compat_details(),
        )
    return match.group(1)


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != _SEMVER_FIELD_COUNT:
        raise CompatibilityError(
            f"could not parse claude version from: {version!r}",
            details=_build_compat_details(),
        )
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError as exc:
        raise CompatibilityError(
            f"could not parse claude version from: {version!r}",
            details=_build_compat_details(),
        ) from exc


# Validate the framework-declared minimum at import time so a malformed
# constant cannot masquerade as a "your claude is unparseable" error at
# runtime (Story 2B.2 review R16).
_MIN_VERSION_TUPLE: Final[tuple[int, int, int]] = _version_tuple(CLAUDE_CODE_MIN_VERSION)


def probe_claude_version() -> str:
    """Run ``claude --version`` and return the parsed semver string.

    Contract: raises ONLY ``CompatibilityError``. Subprocess/OS errors are
    converted at this boundary. Memoized per-process via ``_cached_probe``.
    """
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_CLAUDE_VERSION_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise CompatibilityError(
            f"claude not found on PATH; install Claude Code ({_CLAUDE_DOCS_URL})",
            details=_build_compat_details(),
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CompatibilityError(
            f"claude --version timed out after {_CLAUDE_VERSION_TIMEOUT_SECONDS}s; "
            "check for a hung or unresponsive Claude Code install.",
            details=_build_compat_details(),
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise CompatibilityError(
            f"claude --version failed: {exc}",
            details=_build_compat_details(),
        ) from exc

    if result.returncode != 0:
        excerpt = _sanitize_excerpt((result.stderr or "") + (result.stdout or ""))
        raise CompatibilityError(
            f"claude --version exited {result.returncode}: {excerpt!r}",
            details=_build_compat_details(),
        )

    combined = (result.stdout or "") + (result.stderr or "")
    return parse_claude_version_line(combined)


@lru_cache(maxsize=1)
def _cached_probe() -> str:
    """Memoize the version probe for the lifetime of a single CLI invocation (D5)."""
    return probe_claude_version()


def _under_pytest() -> bool:
    """True when running inside a pytest process (D1 — production-safe bypass).

    Tests that need to exercise the real gate set ``SDLC_TEST_FORCE_COMPAT_CHECK=1``
    to opt in. Production users cannot reach this bypass because
    ``PYTEST_CURRENT_TEST`` is never set outside pytest.
    """
    if os.environ.get(_TEST_FORCE_ENV) == "1":
        return False
    return "PYTEST_CURRENT_TEST" in os.environ


def ensure_claude_code_compatible() -> None:
    """Refuse startup when Claude Code is missing or below the documented minimum.

    Raises only ``CompatibilityError``. No-ops under pytest unless
    ``SDLC_TEST_FORCE_COMPAT_CHECK=1`` is set (D1).
    """
    if _under_pytest():
        return
    reported = _cached_probe()
    if _version_tuple(reported) < _MIN_VERSION_TUPLE:
        raise CompatibilityError(
            f"claude --version reported {reported}; framework requires "
            f"≥ {CLAUDE_CODE_MIN_VERSION}. Upgrade Claude Code.",
            details=_build_compat_details(reported=reported),
        )
