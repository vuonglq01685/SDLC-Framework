"""Claude Code minimum-version pre-flight stub (Story 2B.2 — RED state).

This module is intentionally a stub at this commit. The behavioural functions
(``probe_claude_version``, ``parse_claude_version_line``, ``_version_tuple``,
``ensure_claude_code_compatible``) raise ``NotImplementedError`` so the
test suite is RED. The next commit replaces this stub with the real impl
(GREEN). The pytest auto-bypass + non-dispatch carve-out are real so the
rest of the test suite isn't broken by the stub.

Symbols + signatures are pinned here to satisfy ``mypy --strict`` on the
test files in this commit (CONTRIBUTING §1 quality gate).
"""

from __future__ import annotations

import os
import re
import string
import subprocess  # noqa: F401  — pinned for stub symbol parity with the GREEN impl
import sys
from functools import lru_cache
from typing import TYPE_CHECKING, Final

from sdlc.errors import CompatibilityError

if TYPE_CHECKING:
    import typer

CLAUDE_CODE_MIN_VERSION: Final[str] = "2.0.0"
_CLAUDE_VERSION_TIMEOUT_SECONDS: Final[float] = 5.0
_CLAUDE_DOCS_URL: Final[str] = "https://docs.anthropic.com/en/docs/claude-code"
_VERSION_SEMVER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9_])claude[\s/_-]+(\d+\.\d+\.\d+)"
)
_EXCERPT_MAX_LEN: Final[int] = 120
_PRINTABLE: Final[frozenset[str]] = frozenset(string.printable)
_SEMVER_FIELD_COUNT: Final[int] = 3
_TEST_FORCE_ENV: Final[str] = "SDLC_TEST_FORCE_COMPAT_CHECK"
DISPATCH_SUBCOMMANDS: Final[frozenset[str]] = frozenset(
    {"research", "start", "epics", "stories", "ux", "architect", "bootstrap", "break", "task"}
)
HELP_FLAGS: Final[frozenset[str]] = frozenset({"--help", "-h"})


def parse_claude_version_line(stdout: str) -> str:
    del stdout  # stub — real impl in next commit
    raise NotImplementedError("Story 2B.2 stub — real impl in next commit")


def _version_tuple(version: str) -> tuple[int, int, int]:
    del version  # stub — real impl in next commit
    raise NotImplementedError("Story 2B.2 stub — real impl in next commit")


def probe_claude_version() -> str:
    raise NotImplementedError("Story 2B.2 stub — real impl in next commit")


@lru_cache(maxsize=1)
def _cached_probe() -> str:
    return probe_claude_version()


def _under_pytest() -> bool:
    """Real impl in the stub: production-safe pytest bypass with test-force override."""
    if os.environ.get(_TEST_FORCE_ENV) == "1":
        return False
    return "PYTEST_CURRENT_TEST" in os.environ


def ensure_claude_code_compatible() -> None:
    """Stub: raise NotImplementedError unless pytest auto-bypass is in effect."""
    if _under_pytest():
        return
    raise NotImplementedError("Story 2B.2 stub — real impl in next commit")


def gate_should_run(ctx: typer.Context) -> bool:
    """Real impl in the stub so the non-dispatch carve-out doesn't break other tests."""
    invoked = ctx.invoked_subcommand
    if invoked not in DISPATCH_SUBCOMMANDS:
        return False
    if any(arg in HELP_FLAGS for arg in (ctx.args or [])):
        return False
    return not any(arg in HELP_FLAGS for arg in sys.argv)


def run_pre_flight(ctx: typer.Context) -> None:
    """Real impl in the stub: caller populates ctx.obj first, then gate fires."""
    if not gate_should_run(ctx):
        return
    from sdlc.cli.output import emit_error  # deferred per Architecture §488

    try:
        ensure_claude_code_compatible()
    except CompatibilityError as exc:
        emit_error(exc.code, exc.message, ctx=ctx, details=exc.details)
