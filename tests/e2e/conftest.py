"""Shared pytest configuration for the tests/e2e/ tier (AC4 — shared plumbing).

Defines: update_goldens fixture (--update-goldens flag registered in tests/conftest.py),
e2e_repo_root fixture, cli_runner fixture (available to all e2e sub-tiers),
CliRunner Protocol, _strip_uv_preamble helper, and _normalize_timestamps helper.

2A.0 time-freeze policy: no SDLC_FAKE_NOW hook is introduced here. Journal golden
comparisons in cli/conftest.py exclude the `ts` field via ts-excluded
re-canonicalization (AC5.1 — applies to journals only). Stdout/stderr timestamp
normalization is sanctioned by the 2026-05-10 spec amendment (P24/D1) — see
`_normalize_timestamps` below for the anchored regex contract.
See tests/e2e/README.md for the full rationale.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Protocol

import pytest

# Default subprocess hang guard (P6/PR13). Callers may override per-invocation if needed.
_DEFAULT_SUBPROCESS_TIMEOUT_SECONDS: float = 60.0


# ---------------------------------------------------------------------------
# Pytest option + session fixtures
# ---------------------------------------------------------------------------
# NOTE: --update-goldens is registered in the top-level tests/conftest.py
# (moved by Story 3.2 so both e2e and unit-tier corpus tests share the flag).


@pytest.fixture(scope="session")
def update_goldens(request: pytest.FixtureRequest) -> bool:
    """Return True when --update-goldens flag is set."""
    return bool(request.config.getoption("--update-goldens"))


@pytest.fixture(scope="session")
def e2e_repo_root() -> Path:
    """Return the repository root (directory containing pyproject.toml).

    Resolved via parents[2] from this file:
    tests/e2e/conftest.py → tests/e2e/ → tests/ → <repo-root>

    Used by ``cli_runner`` to pin ``uv run --project=<repo_root>`` so subprocess
    project-discovery is independent of the caller's ``cwd`` (P10).
    """
    return Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# CLI runner fixture (available to Tier-1 tests AND test_harness_anti_tautology)
# ---------------------------------------------------------------------------

# Sanitized env allow-list (AC5.2): strips developer-local env leakage into goldens.
# Per-platform additions ensure subprocess + uv work on every supported OS without
# baking system-specific env into goldens. (P23: Windows + macOS-locale coverage.)
_ENV_ALLOWLIST_BASE: frozenset[str] = frozenset(
    {"PATH", "HOME", "USER", "TMPDIR", "LANG", "LC_ALL", "NO_COLOR", "PYTHONHASHSEED"}
)
# Windows-only essentials — without these, subprocess + uv emit cryptic errors.
_ENV_ALLOWLIST_WIN32: frozenset[str] = frozenset(
    {
        "SYSTEMROOT",
        "PATHEXT",
        "COMSPEC",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "USERPROFILE",
    }
)
_ENV_ALLOWLIST: frozenset[str] = (
    _ENV_ALLOWLIST_BASE | _ENV_ALLOWLIST_WIN32 if sys.platform == "win32" else _ENV_ALLOWLIST_BASE
)


def _resolve_locale() -> str:
    """Return a UTF-8 locale supported by the current platform.

    macOS commonly lacks ``C.UTF-8`` and falls back to ``en_US.UTF-8``;
    Linux/Windows ship ``C.UTF-8``. Implemented as a runtime branch on
    ``sys.platform`` so the function works under cross-platform CI without
    needing per-platform conditional imports. (PR23: removed the
    ``# type: ignore[unreachable]`` mypy escape hatch.)
    """
    return "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"


def _build_sanitized_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build env dict containing only allowed keys + UV_* vars (AC5.2)."""
    env: dict[str, str] = {}
    for key in _ENV_ALLOWLIST:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    locale = _resolve_locale()
    env["LANG"] = locale
    env["LC_ALL"] = locale
    env["NO_COLOR"] = "1"
    env["PYTHONHASHSEED"] = "0"
    # Align with tests/conftest.py autouse — Tier-1 subprocess goldens must not
    # require a real ``claude`` binary on PATH (Story 2B.2).
    env["SDLC_USE_MOCK_RUNTIME"] = "1"
    env["SDLC_MOCK_GATE_BYPASS"] = "1"
    # Story 2B.2 D1: pass PYTEST_CURRENT_TEST through to the e2e subprocess so the
    # Claude compat gate auto-bypasses under pytest (production-safe — the env
    # var is never set outside pytest, so users can't disable the gate by
    # exporting it themselves).
    if "PYTEST_CURRENT_TEST" in os.environ:
        env["PYTEST_CURRENT_TEST"] = os.environ["PYTEST_CURRENT_TEST"]
    for key, val in os.environ.items():
        if key.startswith("UV_"):
            env[key] = val
    if extra:
        env.update(extra)
    return env


# ---------------------------------------------------------------------------
# CliRunner Protocol (PR9/PR21 — typed cli_runner signature)
# ---------------------------------------------------------------------------


class CliRunner(Protocol):
    """Type contract for the ``cli_runner`` fixture.

    Promotes a typed callable for callers so mypy --strict catches misuse without
    requiring ``# type: ignore[operator]`` at every callsite (PR9).
    """

    def __call__(
        self,
        args: list[str],
        cwd: Path,
        env: dict[str, str] | None = ...,
        timeout: float = ...,
    ) -> subprocess.CompletedProcess[str]: ...


@pytest.fixture
def cli_runner(e2e_repo_root: Path) -> CliRunner:
    """Return a callable that invokes ``uv run --project=<repo_root> sdlc --no-color <args>``.

    - ``--no-color`` is unconditional so ANSI escapes never enter goldens.
    - ``--project=<repo_root>`` pins uv project discovery to the actual repo
      regardless of subprocess cwd, so tests can run sdlc inside an arbitrary
      tmp_path without uv walking parent dirs (P10).
    - Env is sanitized to the AC5.2 allow-list + UV_* vars.
    - Subprocess uses a 60s default timeout (P6/PR13); on timeout, wraps the
      bare ``TimeoutExpired`` with an actionable message naming command + cwd.
    - ``errors="replace"`` defends against undecodable bytes in CLI output (P7).

    Available to all tests under tests/e2e/ (Tier-1 and anti-tautology). Sanctioned
    in parent conftest by AC4 (PR-DR2): cross-tier shared fixture so parent-level
    anti-tautology tests don't need to import via the cli package.
    """

    def _run(
        args: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float = _DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            "uv",
            "run",
            "--project",
            str(e2e_repo_root),
            "sdlc",
            "--no-color",
            *args,
        ]
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                env=_build_sanitized_env(env),
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            # PR13: wrap bare TimeoutExpired with an actionable message naming
            # the command and cwd so test failures don't dump opaque tracebacks.
            raise AssertionError(
                f"cli_runner subprocess timed out after {timeout}s.\n"
                f"  command: {' '.join(cmd)}\n"
                f"  cwd:     {cwd}\n"
                f"  stdout (partial): {exc.stdout!r}\n"
                f"  stderr (partial): {exc.stderr!r}\n"
                f"action: investigate hung sdlc command, OR raise the per-test "
                f"timeout via cli_runner(..., timeout=N)."
            ) from exc

    return _run


# ---------------------------------------------------------------------------
# Module-level helpers (NOT fixtures)
# ---------------------------------------------------------------------------


# Anchored uv preamble patterns (P8/PR15). Each regex requires a uv-specific
# shape so sdlc-emitted lines starting with the same word (``Built …``,
# ``Resolved …``) are never silently dropped. Update only when uv changes its
# preamble format.
_UV_RESOLVED_RE = re.compile(r"^Resolved \d+ packages? in \S+\s*$")
# PR15: tighten ``Built`` regex from ``\S+ @ \S+`` to ``\S+ @ <url-shaped>``.
# Accepts uv 0.5+ source variants: file://, https://, git+<scheme>://,
# direct_url, and registry-cached package builds (e.g. ``Built X==1.0 @ X (cached)``).
_UV_BUILT_URL_RE = re.compile(
    r"^Built \S+ @ "
    r"(?:https?|file|git\+\S+?|ssh|svn|bzr|hg)://\S+\s*$"
)
_UV_AUDIT_RE = re.compile(r"^Audited \d+ packages? in \S+\s*$")  # uv 0.5+


def _strip_uv_preamble(stderr: str) -> str:
    """Remove uv toolchain preamble lines from stderr before golden comparison.

    Strips:
      ``Resolved N packages in Xms``
      ``Built <pkg> @ <url-shaped>``  — URL-anchored so sdlc output is safe (PR15)
      ``Audited N packages in Xms``

    These are uv-emitted, not sdlc-emitted, and vary across environments and
    uv versions.
    """
    lines = stderr.splitlines(keepends=True)
    return "".join(
        line
        for line in lines
        if not _UV_RESOLVED_RE.match(line)
        and not _UV_BUILT_URL_RE.match(line)
        and not _UV_AUDIT_RE.match(line)
    )


# Anchored timestamp regex — sanctioned by the 2026-05-10 spec amendment (P24/D1).
# Requires both a date and a time component, so isolated dates in epic titles or
# isolated times don't match. PR19: negative-lookbehind anchored — the date must
# NOT be preceded by a word character (letter/digit/underscore) or a hyphen, so
# embedded substrings like ``epic-2026-05-10T00:00:00-launch`` are left alone
# while ``Last updated: 2026-05-10 14:23:45`` is normalized.
# Covers:
#   2026-05-10 14:23:45                  (space-separated, AC2.3 original)
#   2026-05-10T14:23:45                  (ISO-T)
#   2026-05-10 14:23:45.123456           (fractional seconds)
#   2026-05-10T14:23:45.123Z             (UTC marker)
#   2026-05-10 14:23:45 +0700            (offset, ±HHMM or ±HH:MM)
_TIMESTAMP_RE = re.compile(
    r"(?<![\w-])"  # PR19: not preceded by word-char or hyphen — keeps identifiers intact
    r"\d{4}-\d{2}-\d{2}"  # YYYY-MM-DD
    r"[T ]"  # 'T' or space separator (required)
    r"\d{2}:\d{2}:\d{2}"  # HH:MM:SS
    r"(?:\.\d+)?"  # optional fractional seconds
    # Optional UTC marker (Z) or offset; offset accepts ±HH, ±HHMM, or ±HH:MM
    # so all common timezone notations are normalized (e.g. +07, +0700, +07:00).
    r"(?:Z|\s*[+-]\d{2}(?::?\d{2})?)?"
)


def _normalize_timestamps(text: str) -> str:
    """Replace wall-clock timestamps with ``<TIMESTAMP>`` sentinel.

    Handles ISO-8601-like timestamps emitted by ``sdlc status`` and similar
    commands. Sanctioned by the 2026-05-10 P24/D1 spec amendment to AC2.3/AC5.1.
    PR19: anchored via negative lookbehind so a timestamp embedded in an
    identifier like ``epic-2026-05-10T00:00:00-launch`` is left alone.
    """
    return _TIMESTAMP_RE.sub("<TIMESTAMP>", text)
