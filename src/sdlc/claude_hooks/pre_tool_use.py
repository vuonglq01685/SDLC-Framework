"""Claude Code PreToolUse hook — stdlib-only entry point (Story 2A.6, AC3/AC4).

Implements:
  - FR40 (Claude PreToolUse hook), Decision D2 (one HookPayload contract, two callers).
  - ADR-013 (advisory v1 trust posture), ADR-024 (HookPayload v1 wire-format lock),
    ADR-026 (TDD-first commit ordering).
  - Architecture §971-§974 (claude_hooks/ content tree), §488-§494 (cold-start budget).

Exit 0 = decision approve (allow or fail-open).
Exit 1 = decision block (deny or path_outside_repo).

Stdlib-only at runtime; pydantic only behind ``if TYPE_CHECKING:`` (AC9).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # type-only import per AC3 fifth-And + AC9 line 189
    from sdlc.contracts.hook_payload import HookPayload as _HookPayload  # noqa: F401

_WRITE_TOOLS: frozenset[str] = frozenset({"Write", "Edit", "MultiEdit"})

# AC2 canonical 4-key envelope shape (DR3 → D1 standardisation).
_APPROVE: dict[str, object] = {
    "decision": "approve",
    "hook_name": None,
    "reason": None,
    "error_code": None,
}


def _to_claude_envelope(engine: dict[str, object]) -> dict[str, object]:
    """Translate engine HookDecision envelope to Claude Code's approve/block vocabulary.

    Always emits the 4-key canonical shape (DR3 → D1): decision/hook_name/reason/error_code.
    Unknown engine decisions fall back to fail-open (per AC9 advisory posture).
    """
    decision = engine.get("decision")
    if decision == "allow":
        return dict(_APPROVE)
    if decision == "deny":
        return {
            "decision": "block",
            "hook_name": engine.get("hook_name"),
            "reason": engine.get("reason"),
            "error_code": engine.get("error_code"),
        }
    # Unknown decision value (schema drift) — fail-open per AC9 advisory posture.
    sys.stderr.write(f"[pre_tool_use WARN] unknown engine decision {decision!r}; fail-open\n")
    return dict(_APPROVE)


def _emit(envelope: dict[str, object]) -> None:
    print(json.dumps(envelope, sort_keys=True, separators=(",", ":")))


def _fail_open(msg: str) -> None:
    sys.stderr.write(f"[pre_tool_use WARN] {msg}\n")
    _emit(_APPROVE)


def _resolve_path(file_path_str: str, cwd: Path) -> str | None:
    """Return cwd-relative POSIX path string, or None if the path escapes cwd.

    Happy path uses pure path arithmetic (no filesystem lookup, no ``os.getcwd``).
    Fallback to ``.resolve()`` only when the lexical relative_to fails — handles
    symlinked roots (macOS ``/private/var/...`` vs ``/var/...``) and Windows
    case-insensitive FS edge cases (F2 fix). Pure-path happy path also keeps the
    test that mocks ``os.getcwd`` honest (the original code never called it).
    """
    fp = Path(file_path_str)
    raw = fp if fp.is_absolute() else cwd / fp
    try:
        return raw.relative_to(cwd).as_posix()
    except ValueError:
        pass
    # Fallback 1: .resolve() to handle symlinks (macOS /private/var case).
    try:
        return raw.resolve().relative_to(cwd.resolve()).as_posix()
    except (OSError, ValueError):
        pass
    # Fallback 2: Windows case-insensitive normcase comparison.
    try:
        cwd_str = os.path.normcase(str(cwd))
        raw_str = os.path.normcase(str(raw))
        if raw_str.startswith(cwd_str):
            tail = raw_str[len(cwd_str) :].lstrip("\\/")
            return Path(tail).as_posix() if tail else "."
    except OSError:
        pass
    return None


def _content_hash_before(rel_path: str, cwd: Path) -> str | None:
    """Return ``sha256:<hex>`` of an existing file's bytes, or None (AC3.3).

    Uses plain join (no .resolve()) so unit tests that mock os.getcwd stay honest.
    """
    try:
        absolute = cwd / rel_path
        if not absolute.exists() or not absolute.is_file():
            return None
        digest = hashlib.sha256(absolute.read_bytes()).hexdigest()
        return f"sha256:{digest}"
    except OSError:
        return None


def _call_engine(rel_path: str, tool_name: str, cwd: Path) -> dict[str, object] | None:
    """Invoke ``sdlc hook-check``; return engine response dict or None on fail-open.

    AC3.3 wire-format (F1 fix):
      - target_kind = "write_intent" (matches Story 2A.4 AC1 vocabulary)
      - write_intent = "claude_pretooluse_{tool}" (AC10 discriminator)
      - content_hash_before = sha256 of file bytes IF file exists else None
    """
    payload = {
        "schema_version": 1,
        "hook_name": "pre_write",
        "target_path": rel_path,
        "target_kind": "write_intent",
        "content_hash_before": _content_hash_before(rel_path, cwd),
        "write_intent": f"claude_pretooluse_{tool_name.lower()}",
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        result = subprocess.run(
            ["sdlc", "hook-check"],
            input=payload_bytes,
            capture_output=True,
            timeout=10.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _fail_open("sdlc hook-check timed out — fail-open")
        return None
    except FileNotFoundError:
        _fail_open("sdlc executable not found on PATH — fail-open")
        return None
    except OSError as exc:
        _fail_open(f"sdlc hook-check OSError: {exc} — fail-open")
        return None

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        _fail_open(f"sdlc hook-check returned non-JSON stdout: {exc} — fail-open")
        return None
    if not isinstance(parsed, dict):
        _fail_open(
            f"sdlc hook-check returned non-object JSON ({type(parsed).__name__}) — fail-open"
        )
        return None
    return parsed


def _parse_envelope(raw: str) -> tuple[dict[str, object], str] | None:
    """Parse stdin envelope; return (envelope, tool_name) or None on schema error (fail-open)."""
    try:
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise TypeError(f"envelope is not a JSON object: {type(envelope).__name__}")
        tool_name_raw = envelope["tool_name"]
        if not isinstance(tool_name_raw, str):
            raise TypeError(f"tool_name is not a string: {type(tool_name_raw).__name__}")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        _fail_open(f"unrecognised envelope schema ({type(exc).__name__}: {exc}) — fail-open")
        return None
    return envelope, tool_name_raw


def _extract_file_path(envelope: dict[str, object]) -> str | None:
    """Extract tool_input.file_path; return None on missing/invalid (fail-open already emitted)."""
    try:
        file_path_str = envelope["tool_input"]["file_path"]  # type: ignore[index]
        if not isinstance(file_path_str, str) or not file_path_str:
            raise TypeError("tool_input.file_path missing or non-string")
    except (KeyError, TypeError) as exc:
        _fail_open(f"missing/invalid tool_input.file_path ({exc}) — fail-open")
        return None
    return file_path_str


def main() -> None:
    """PreToolUse hook entry point — reads Claude envelope from stdin, exits 0/1."""
    parsed = _parse_envelope(sys.stdin.read())
    if parsed is None:
        sys.exit(0)
    envelope, tool_name = parsed

    if tool_name not in _WRITE_TOOLS:
        _emit(_APPROVE)
        sys.exit(0)

    cwd_raw = envelope.get("cwd")
    cwd = Path(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw else Path(os.getcwd())

    file_path_str = _extract_file_path(envelope)
    if file_path_str is None:
        sys.exit(0)

    rel = _resolve_path(file_path_str, cwd)
    if rel is None:
        _emit(
            {
                "decision": "block",
                "hook_name": None,
                "reason": f"path {file_path_str!r} is outside the repo root",
                "error_code": "path_outside_repo",
            }
        )
        sys.exit(1)

    engine_resp = _call_engine(rel, tool_name, cwd)
    if engine_resp is None:
        # _fail_open() already emitted approve to stdout
        sys.exit(0)

    claude_env = _to_claude_envelope(engine_resp)
    _emit(claude_env)
    sys.exit(1 if claude_env.get("decision") == "block" else 0)


if __name__ == "__main__":
    main()
