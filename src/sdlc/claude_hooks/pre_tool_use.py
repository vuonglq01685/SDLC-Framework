"""Claude Code PreToolUse hook — stdlib-only entry point (Story 2A.6, AC3/AC4).

Exit 0 = decision approve (allow or fail-open).
Exit 1 = decision block (deny or path_outside_repo).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_WRITE_TOOLS: frozenset[str] = frozenset({"Write", "Edit", "MultiEdit"})
_APPROVE: dict[str, object] = {"decision": "approve"}


def _to_claude_envelope(engine: dict[str, object]) -> dict[str, object]:
    if engine.get("decision") == "allow":
        return {"decision": "approve", "reason": None}
    return {
        "decision": "block",
        "reason": engine.get("reason"),
        "error_code": engine.get("error_code"),
    }


def _emit(envelope: dict[str, object]) -> None:
    print(json.dumps(envelope))


def _fail_open(msg: str) -> None:
    sys.stderr.write(f"[pre_tool_use WARN] {msg}\n")
    _emit(_APPROVE)


def _resolve_path(file_path_str: str, cwd: Path) -> str | None:
    """Return cwd-relative path string, or None if the resolved path escapes cwd."""
    fp = Path(file_path_str)
    resolved = fp if fp.is_absolute() else cwd / fp
    try:
        return resolved.relative_to(cwd).as_posix()
    except ValueError:
        return None


def _call_engine(rel_path: str, tool_name: str) -> dict[str, object] | None:
    """Invoke sdlc hook-check; return engine response dict or None on fail-open."""
    payload = {
        "schema_version": 1,
        "hook_name": "pre_write",
        "target_path": rel_path,
        "target_kind": "file",
        "content_hash_before": None,
        "write_intent": tool_name.lower(),
    }
    try:
        result = subprocess.run(
            ["sdlc", "hook-check"],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=10.0,
            check=False,
        )
        return json.loads(result.stdout)  # type: ignore[no-any-return]
    except subprocess.TimeoutExpired:
        _fail_open("sdlc hook-check timed out — fail-open")
        return None
    except Exception:
        _fail_open("sdlc hook-check error — fail-open")
        return None


def main() -> None:
    """PreToolUse hook entry point — reads Claude envelope from stdin, exits 0/1."""
    try:
        envelope = json.loads(sys.stdin.read())
        tool_name: str = envelope["tool_name"]
    except Exception:
        _fail_open("unrecognised envelope schema — fail-open")
        sys.exit(0)

    if tool_name not in _WRITE_TOOLS:
        _emit(_APPROVE)
        sys.exit(0)

    cwd_raw: str | None = envelope.get("cwd")
    cwd = Path(cwd_raw) if cwd_raw is not None else Path(os.getcwd())

    try:
        file_path_str: str = envelope["tool_input"]["file_path"]
    except (KeyError, TypeError):
        _fail_open("missing tool_input.file_path — fail-open")
        sys.exit(0)

    rel = _resolve_path(file_path_str, cwd)
    if rel is None:
        _emit(
            {
                "decision": "block",
                "reason": f"path {file_path_str!r} is outside the repo root",
                "error_code": "path_outside_repo",
            }
        )
        sys.exit(1)

    engine_resp = _call_engine(rel, tool_name)
    if engine_resp is None:
        sys.exit(0)

    claude_env = _to_claude_envelope(engine_resp)
    _emit(claude_env)
    sys.exit(1 if claude_env.get("decision") == "block" else 0)


if __name__ == "__main__":
    main()
