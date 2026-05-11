"""``sdlc hook-check`` — engine-side parity oracle for the Claude Code PreToolUse hook.

Implements:
  - FR40 (Claude PreToolUse hook), Decision D2 (one HookPayload contract, two callers).
  - ADR-013 (advisory v1 trust posture; engine-side is authoritative).
  - ADR-024 (HookPayload v1 wire-format lock — REUSED unchanged here).
  - ADR-025 (Pydantic strict-mode for HookPayload — inherited).
  - ADR-026 §1 (TDD-first commit ordering for the public ``run_hook_check`` entry).
  - Architecture §796 (file location), §488-§494 (cold-start budget).

Machine-only subcommand (AC2, Story 2A.6): reads a HookPayload JSON from stdin
(canonical form) or ``argv[1]`` (TTY fallback for interactive testing), runs the
engine's ``naming_validator + phase_gate`` chain via ``run_hook_chain``, emits a
response envelope to stdout, and exits 0/1/2.

Exit codes:
  0 — allow  (write permitted)
  1 — deny   (hook chain blocked the write; Claude Code maps exit != 0 → block)
  2 — error  (invalid payload, registry corrupt, or other internal failure)

Wire direction: Claude-side serialises HookPayload → ``sdlc hook-check`` reads from
stdin → CLI writes the response envelope to stdout. Stdin-first avoids Windows
argv-length limits and shell-escaping fragility (Story 2A.0 P26 lessons).

Bypass policy: ``sdlc hook-check`` does NOT accept ``--force-bypass-signoff`` in v1.
Bypass is always user-initiated from a human-driven CLI command; Claude Code's
PreToolUse hook never has bypass authority. A future v1.x bypass path goes via a
separate flag — out of scope here.
"""

from __future__ import annotations

import asyncio
import json
import sys
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.hooks.builtin.phase_gate import phase_gate
from sdlc.signoff import compute_state

if TYPE_CHECKING:
    from sdlc.contracts.hook_payload import HookPayload
    from sdlc.hooks.runner import HookDecision

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state"


def _emit(envelope: dict[str, object]) -> None:
    """Write the canonical JSON response envelope to stdout (machine-readable)."""
    typer.echo(json.dumps(envelope, sort_keys=True, separators=(",", ":")))


class _PhaseGateHook:
    """Phase-gate hook callable with an explicit ``__is_phase_gate__`` marker (P26).

    Replaces the previous ``functools.partial`` + attribute-assignment idiom —
    setting attributes on ``functools.partial`` instances is undocumented CPython
    behavior. The class-based shape keeps the marker discoverable by
    ``sdlc.hooks.runner`` while binding ``repo_root`` and ``signoff_reader``
    via composition.

    Mirrors :func:`sdlc.dispatcher._hook_chain.build_pre_write_hook_chain` so
    ``sdlc hook-check`` and dispatch exercise the same gate semantics.
    """

    __is_phase_gate__: bool = True

    def __init__(self, repo_root: Path) -> None:
        self._fn = partial(
            phase_gate,
            repo_root=repo_root,
            signoff_reader=_signoff_reader_for_repo,
        )

    def __call__(self, payload: HookPayload) -> HookDecision:
        return self._fn(payload)


def _signoff_reader_for_repo(phase: int, root: Path) -> str:
    """Adapter: ``compute_state`` accepts ``repo_root`` as kwarg-only.

    P25: fail OPEN (advisory v1 trust posture, ADR-013) when compute_state
    blows up — engine-side gate is authoritative; hook-check should not crash
    the agent on a transient signoff-store read error.
    """
    try:
        return compute_state(phase, repo_root=root).value
    except Exception:
        # P25: fail-open advisory per ADR-013 — hook-check is parity oracle,
        # engine-side gate is authoritative.
        return "indeterminate"


def _make_phase_gate_hook(
    repo_root: Path,
) -> object:  # Callable[[HookPayload], HookDecision] at runtime
    """Return phase_gate bound to repo_root and signoff_reader (Story 2A.7 AC7).

    Mirrors ``dispatcher._hook_chain.build_pre_write_hook_chain`` so hook-check
    exercises the same gate semantics as dispatch (no missing DI).
    """
    return _PhaseGateHook(repo_root)


def run_hook_check(*, ctx: typer.Context) -> None:
    """Run the engine hook chain; emit a machine-readable decision envelope.

    Reads HookPayload JSON from stdin (canonical) or ``argv[1]`` (TTY fallback).
    The ``--json`` global flag is accepted for consistency and is a no-op — this
    subcommand always emits the JSON envelope regardless.
    """
    from pydantic import ValidationError

    from sdlc.config.hooks import load_hook_registry
    from sdlc.contracts.hook_payload import HookPayload
    from sdlc.errors import ConfigError
    from sdlc.hooks.runner import run_hook_chain

    # ── 1. Read raw payload ───────────────────────────────────────────────────
    # TTY fallback: interactive invocation or direct argv call (testing only)
    raw = (sys.argv[1] if len(sys.argv) > 1 else "") if sys.stdin.isatty() else sys.stdin.read()

    if not raw or not raw.strip():
        _emit(
            {
                "decision": "deny",
                "error_code": "invalid_payload",
                "hook_name": None,
                "reason": "empty payload",
            }
        )
        raise typer.Exit(code=2)

    # ── 2. Validate HookPayload ───────────────────────────────────────────────
    try:
        payload = HookPayload.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        _emit(
            {
                "decision": "deny",
                "error_code": "invalid_payload",
                "hook_name": None,
                "reason": str(exc),
            }
        )
        raise typer.Exit(code=2) from exc

    # ── 3. Resolve repo root + load hook registry ─────────────────────────────
    repo_root = _get_repo_root_or_cwd()
    try:
        hook_names = load_hook_registry(repo_root / "pyproject.toml")
    except ConfigError as exc:
        _emit(
            {
                "decision": "deny",
                "error_code": "registry_error",
                "hook_name": None,
                "reason": str(exc),
            }
        )
        raise typer.Exit(code=2) from exc

    # ── 4. Build hook callables from the registry ─────────────────────────────
    from sdlc.hooks.builtin.naming_validator import naming_validator

    _builtins: dict[str, object] = {
        "naming_validator": naming_validator,
        "phase_gate": _make_phase_gate_hook(repo_root),
    }
    # F16: unknown hook names → registry_error (was silently filtered → all-allow).
    unknown = [n for n in hook_names if n not in _builtins]
    if unknown:
        _emit(
            {
                "decision": "deny",
                "error_code": "registry_error",
                "hook_name": None,
                "reason": f"unknown hook(s) in registry: {sorted(unknown)!r}",
            }
        )
        raise typer.Exit(code=2)
    hooks = tuple(_builtins[n] for n in hook_names)

    # ── 5. Resolve journal path ───────────────────────────────────────────────
    # AC2.5: journal IS appended when reachable. The `sdlc.journal.append`
    # primitive is POSIX-only (Architecture §573 — fcntl/O_APPEND atomicity);
    # on Windows or pre-init workspaces the file may not exist. Gate on the
    # journal file existing so we never crash on an unreachable journal —
    # document this as F4-defer (see deferred-work.md W9).
    _journal_file = repo_root / _JOURNAL_REL
    journal_path: Path | None = _journal_file if _journal_file.exists() else None

    # ── 6. Run the hook chain ─────────────────────────────────────────────────
    decision: HookDecision = asyncio.run(
        run_hook_chain(payload, hooks=hooks, journal_path=journal_path)  # type: ignore[arg-type]
    )

    # ── 7. Emit canonical response envelope ───────────────────────────────────
    _emit(
        {
            "decision": decision.decision,
            "error_code": decision.error_code,
            "hook_name": decision.hook_name,
            "reason": decision.reason,
        }
    )

    if decision.decision == "deny":
        raise typer.Exit(code=1)
