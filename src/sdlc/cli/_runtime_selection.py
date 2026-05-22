"""Shared mock-vs-real runtime selection and ``--allow-mock`` gate (ADR-029, Story 2B.1)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import typer

from sdlc.cli.output import echo, emit_error
from sdlc.runtime.abc import AIRuntime
from sdlc.runtime.claude import ClaudeAIRuntime
from sdlc.runtime.mock import MockAIRuntime

_USE_MOCK_ENV: Final[str] = "SDLC_USE_MOCK_RUNTIME"
_MOCK_GATE_BYPASS_ENV: Final[str] = "SDLC_MOCK_GATE_BYPASS"
_ALLOW_MOCK_WARN: Final[str] = (
    "WARN: --allow-mock is set; this run uses MockAIRuntime, "
    "outputs are fixture-derived, not real model outputs"
)


def use_mock_runtime() -> bool:
    """Return True when mock dispatch is enabled (default off post-2B.1)."""
    return os.environ.get(_USE_MOCK_ENV, "0") == "1"


def _mock_gate_bypass_enabled() -> bool:
    """True when an explicit opt-in waives the ``--allow-mock`` gate.

    Set ``SDLC_MOCK_GATE_BYPASS=1`` only in automated harnesses (the test suite
    sets it via ``conftest.py``) that already run on MockAIRuntime by
    construction. Production code never sets it — the gate must not branch on
    test-framework detection such as ``PYTEST_CURRENT_TEST`` (Story 2B.1 P16).
    """
    return os.environ.get(_MOCK_GATE_BYPASS_ENV, "") == "1"


def enforce_allow_mock_gate(*, allow_mock: bool, ctx: typer.Context) -> bool:
    """Exit on missing ``--allow-mock`` when mock env is on; emit WARN when permitted.

    Returns ``allow_mock_invoked`` for journal audit payloads.
    """
    if not use_mock_runtime():
        return False
    if not allow_mock:
        if _mock_gate_bypass_enabled():
            return False
        emit_error(
            "ERR_USER_INPUT",
            "mock runtime is enabled via SDLC_USE_MOCK_RUNTIME=1 but --allow-mock was not "
            "provided; pass --allow-mock to acknowledge mock dispatch in this run",
            ctx=ctx,
            details={"env": _USE_MOCK_ENV},
        )
    ctx_obj = ctx.obj if isinstance(ctx.obj, dict) else {}
    if not bool(ctx_obj.get("json", False)):
        echo(_ALLOW_MOCK_WARN, err=True, ctx=ctx)
    return True


def merge_observer_mock_audit(
    ctx: dict[str, object],
    *,
    allow_mock_invoked: bool,
) -> None:
    """Attach ``dispatch_attempt_extras.allow_mock_invoked`` for ADR-029 audit (AC6)."""
    if not allow_mock_invoked:
        return
    existing = ctx.get("dispatch_attempt_extras")
    merged: dict[str, object] = dict(existing) if isinstance(existing, Mapping) else {}
    merged["allow_mock_invoked"] = True
    ctx["dispatch_attempt_extras"] = merged


def build_runtime(*, fixtures_dir: Path) -> AIRuntime:
    """Construct MockAIRuntime or ClaudeAIRuntime per env gate."""
    if use_mock_runtime():
        return MockAIRuntime(fixtures_dir)
    return ClaudeAIRuntime()


__all__ = (
    "_USE_MOCK_ENV",
    "ClaudeAIRuntime",
    "MockAIRuntime",
    "build_runtime",
    "enforce_allow_mock_gate",
    "merge_observer_mock_audit",
    "use_mock_runtime",
)
