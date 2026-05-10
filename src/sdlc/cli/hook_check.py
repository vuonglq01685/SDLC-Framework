"""``sdlc hook-check`` — engine-side parity oracle for the Claude Code PreToolUse hook.

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
from pathlib import Path
from typing import TYPE_CHECKING, Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd

if TYPE_CHECKING:
    from sdlc.hooks.runner import HookDecision

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state"


def _emit(envelope: dict[str, object]) -> None:
    """Write the canonical JSON response envelope to stdout (machine-readable)."""
    typer.echo(json.dumps(envelope, sort_keys=True, separators=(",", ":")))


def _make_phase_gate_hook(
    repo_root: Path,
) -> object:  # Callable[[HookPayload], HookDecision] at runtime
    """Return a single-arg closure wrapping phase_gate with __is_phase_gate__ marker."""
    from sdlc.hooks.builtin.phase_gate import phase_gate

    def _hook(payload: object) -> object:
        return phase_gate(payload, repo_root=repo_root)  # type: ignore[arg-type]

    _hook.__is_phase_gate__ = True  # type: ignore[attr-defined]
    return _hook


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
    hooks = tuple(_builtins[n] for n in hook_names if n in _builtins)

    # ── 5. Resolve journal path ───────────────────────────────────────────────
    # Gate on the journal file existing, not just the state dir — avoids
    # POSIX-only journal write in parity tests (tmp_path has signoffs but no
    # journal.log) and on Windows dev hosts without a full sdlc init.
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
