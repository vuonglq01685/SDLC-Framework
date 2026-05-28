#!/usr/bin/env python3
"""AST static check for subprocess allow-list (Story 2B.6 AC2)."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

from sdlc.errors import SecurityError

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXEMPT_DIRS = frozenset({"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"})
_SELF = Path(__file__).resolve()
_DYNAMIC_BIN = "<dynamic>"
_MAX_BINARY_RESOLVE_DEPTH: int = 3
_SUBPROCESS_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("src/sdlc/runtime/claude.py", "claude"),
        ("src/sdlc/cli/_compat_check.py", "claude"),
        ("src/sdlc/cli/_paths.py", "git"),
        ("src/sdlc/hooks/runner.py", _DYNAMIC_BIN),
        ("src/sdlc/hooks/runner.py", "git"),
        ("src/sdlc/claude_hooks/pre_tool_use.py", "sdlc"),
    }
)
_ALLOWED_SUBPROCESS_CALLS = frozenset({"run", "Popen", "call", "check_call", "check_output"})
_FORBIDDEN_OS_CALLS = frozenset(
    {
        "system",
        "popen",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
    }
)


@dataclass(frozen=True, slots=True)
class SubprocessViolation:
    path: Path
    line: int
    col: int
    binary: str
    reason: str

    def to_security_error(self) -> SecurityError:
        return SecurityError(
            f"module {self.path}:{self.line} subprocess not in allow-list",
            details={
                "path": str(self.path),
                "line": self.line,
                "col": self.col,
                "binary": self.binary,
                "reason": self.reason,
            },
        )


def _is_exempt(path: Path) -> bool:
    resolved = path.resolve()
    if resolved == _SELF:
        return True
    try:
        rel = resolved.relative_to(_REPO_ROOT)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] in _EXEMPT_DIRS


def _expand_targets(argv: list[str]) -> list[Path]:
    if not argv:
        return list((_REPO_ROOT / "src" / "sdlc").rglob("*.py"))
    out: list[Path] = []
    for raw in argv:
        p = Path(raw)
        if p.is_dir():
            out.extend(p.rglob("*.py"))
        else:
            out.append(p)
    return out


def _rel_key(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT).as_posix()


def _const_bindings(tree: ast.Module) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            out[node.target.id] = node.value
    return out


def _called_symbol(node: ast.Call) -> tuple[str | None, str | None]:
    fn = node.func
    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
        return fn.value.id, fn.attr
    return None, None


def _extract_binary(arg: ast.expr, bindings: dict[str, ast.expr], depth: int = 0) -> str | None:
    if depth > _MAX_BINARY_RESOLVE_DEPTH:
        return None
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value.strip().split()[0] if arg.value.strip() else None
    if isinstance(arg, (ast.List, ast.Tuple)) and arg.elts:
        first = arg.elts[0]
        return _extract_binary(first, bindings, depth + 1)
    if isinstance(arg, ast.Name) and arg.id in bindings:
        return _extract_binary(bindings[arg.id], bindings, depth + 1)
    return None


def _check_subprocess_call(
    node: ast.Call,
    path: Path,
    allowed: set[str],
    bindings: dict[str, ast.expr],
) -> SubprocessViolation | None:
    """Return a violation if this subprocess call is not in the allow-list."""
    if not node.args:
        return SubprocessViolation(
            path=path,
            line=node.lineno,
            col=node.col_offset + 1,
            binary="<missing>",
            reason="missing first positional arg",
        )
    binary = _extract_binary(node.args[0], bindings)
    if binary is None:
        if _DYNAMIC_BIN in allowed or len(allowed) == 1:
            return None
        return SubprocessViolation(
            path=path,
            line=node.lineno,
            col=node.col_offset + 1,
            binary="<dynamic>",
            reason="dynamic binary not approved",
        )
    if binary not in allowed:
        return SubprocessViolation(
            path=path,
            line=node.lineno,
            col=node.col_offset + 1,
            binary=binary,
            reason="binary not allow-listed for module",
        )
    return None


def _scan_file(path: Path) -> list[SubprocessViolation]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    bindings = _const_bindings(tree)
    rel = _rel_key(path)
    allowed = {binary for file_path, binary in _SUBPROCESS_ALLOWLIST if file_path == rel}
    violations: list[SubprocessViolation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        base, attr = _called_symbol(node)
        if base == "subprocess" and attr in _ALLOWED_SUBPROCESS_CALLS:
            v = _check_subprocess_call(node, path, allowed, bindings)
            if v is not None:
                violations.append(v)
        elif base == "os" and attr in _FORBIDDEN_OS_CALLS:
            violations.append(
                SubprocessViolation(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset + 1,
                    binary=f"os.{attr}",
                    reason="os shell/process APIs are forbidden",
                )
            )
    return violations


def scan_file(path: Path) -> list[SubprocessViolation]:
    try:
        return _scan_file(path)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise SecurityError(
            "subprocess allow-list scan target is unreadable or invalid",
            details={"path": str(path), "error": type(exc).__name__},
        ) from exc


def main(argv: list[str]) -> int:
    has_any = False
    for target in sorted(_expand_targets(argv)):
        if _is_exempt(target):
            continue
        for violation in scan_file(target):
            err = violation.to_security_error()
            print(f"{target}:{violation.line}:{violation.col}: {err.message}")
            has_any = True
    return 2 if has_any else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
