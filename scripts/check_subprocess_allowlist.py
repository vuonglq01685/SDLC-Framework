#!/usr/bin/env python3
"""AST static check for subprocess allow-list (Story 2B.6 AC2, post-review).

Post-review patches (2026-05-28 bmad-code-review):
- P9: tracks aliased imports — ``import subprocess as sp`` and
  ``from subprocess import run [as r]`` resolve back to canonical.
- P10: any ``shell=True`` kwarg is a violation regardless of binary.
- P11: inspects ``args=`` and ``executable=`` kwargs — not just the first
  positional. ``executable=`` overrides ``args[0]`` for the binary check.
- P12: ``len(allowed) == 1`` silent-permit shortcut REMOVED — dynamic binaries
  now require an explicit ``"<dynamic>"`` allow-list entry per AC2/D3.
- P13: binary names like ``/usr/bin/git`` are stripped to ``git`` via
  ``Path(value).name`` so the allow-list match works regardless of full path.
- P14: ``asyncio.create_subprocess_exec`` / ``create_subprocess_shell`` are
  detected as subprocess calls (shell variant also forbidden).
- P15: ``pty.spawn`` and ``os.exec*`` / ``os.posix_spawn*`` are forbidden.
- P16: f-string binary names yield ``"<dynamic>"`` (rather than ``None``)
  so they DO fail-closed unless ``"<dynamic>"`` is allow-listed.
- P20: source opened via ``tokenize.open`` to honour PEP-263 + BOM.
"""

from __future__ import annotations

import ast
import sys
import tokenize
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
        # P12 (post-review): explicit ``<dynamic>`` declaration for the
        # ``Popen(cmd, ...)`` callsite where ``cmd[0] = claude_bin`` (function
        # parameter — not a module-level constant). The pre-review scanner
        # silently permitted this via the ``len(allowed) == 1`` shortcut; that
        # shortcut is removed, so dynamic binaries MUST now be explicit per AC2/D3.
        ("src/sdlc/runtime/claude.py", _DYNAMIC_BIN),
        ("src/sdlc/cli/_compat_check.py", "claude"),
        ("src/sdlc/cli/_paths.py", "git"),
        ("src/sdlc/hooks/runner.py", _DYNAMIC_BIN),
        ("src/sdlc/hooks/runner.py", "git"),
        ("src/sdlc/claude_hooks/pre_tool_use.py", "sdlc"),
    }
)
_ALLOWED_SUBPROCESS_CALLS = frozenset({"run", "Popen", "call", "check_call", "check_output"})
# P14: async subprocess APIs — _shell variant is treated as a shell call.
_ALLOWED_ASYNCIO_SUBPROCESS_CALLS = frozenset({"create_subprocess_exec", "create_subprocess_shell"})
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
        # P15: exec family
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "posix_spawn",
        "posix_spawnp",
        "fork",
        "forkpty",
    }
)
# P15: pty.spawn — directly forks + execs a shell command.
_FORBIDDEN_PTY_CALLS = frozenset({"spawn"})


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
    """Return repo-relative POSIX path; for paths outside the repo (e.g.
    transient tmp files in scanner tests), return the absolute POSIX path so
    the lookup falls through to fail-closed rather than crashing."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


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


@dataclass(frozen=True, slots=True)
class _ImportTable:
    """P9: maps local aliases back to ``(module, attr)`` for subprocess /
    asyncio / pty / os call resolution."""

    # ``alias -> canonical module name`` for ``import X [as Y]``.
    module_aliases: dict[str, str]
    # ``alias -> (canonical_module, attr)`` for ``from X import Y [as Z]``.
    bound_names: dict[str, tuple[str, str]]


def _collect_imports(tree: ast.Module) -> _ImportTable:
    mods: dict[str, str] = {}
    names: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                mods[local] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            for alias in node.names:
                local = alias.asname or alias.name
                names[local] = (node.module, alias.name)
    return _ImportTable(module_aliases=mods, bound_names=names)


def _called_symbol(node: ast.Call, imports: _ImportTable) -> tuple[str | None, str | None]:
    """P9: resolve ``node.func`` to canonical ``(module, attr)``.

    Examples:
      - ``subprocess.run(...)`` → ``("subprocess", "run")``
      - ``import subprocess as sp; sp.run(...)`` → ``("subprocess", "run")``
      - ``from subprocess import run; run(...)`` → ``("subprocess", "run")``
      - ``from subprocess import run as r; r(...)`` → ``("subprocess", "run")``
      - ``asyncio.create_subprocess_exec(...)`` → ``("asyncio", "create_subprocess_exec")``
    """
    fn = node.func
    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
        local = fn.value.id
        canonical_module = imports.module_aliases.get(local, local)
        return canonical_module, fn.attr
    if isinstance(fn, ast.Name):
        if fn.id in imports.bound_names:
            return imports.bound_names[fn.id]
        return None, None
    return None, None


def _strip_binary(value: str) -> str | None:
    """P13: strip path prefix so allow-list match works on the bare name."""
    head = value.strip().split() if value.strip() else []
    if not head:
        return None
    return Path(head[0]).name


def _extract_binary(arg: ast.expr, bindings: dict[str, ast.expr], depth: int = 0) -> str | None:
    if depth > _MAX_BINARY_RESOLVE_DEPTH:
        return None
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return _strip_binary(arg.value)
    if isinstance(arg, ast.JoinedStr):
        # P16: f-strings yield <dynamic> so the gate fails-closed unless
        # <dynamic> is allow-listed.
        return _DYNAMIC_BIN
    if isinstance(arg, (ast.List, ast.Tuple)) and arg.elts:
        first = arg.elts[0]
        return _extract_binary(first, bindings, depth + 1)
    if isinstance(arg, ast.Name) and arg.id in bindings:
        return _extract_binary(bindings[arg.id], bindings, depth + 1)
    return None


def _has_shell_true_kwarg(node: ast.Call) -> bool:
    """P10: ``shell=True`` is a violation regardless of binary."""
    for kw in node.keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _first_positional_or_args_kwarg(
    node: ast.Call, bindings: dict[str, ast.expr]
) -> ast.expr | None:
    """P11: return the call's effective ``args`` value — first positional OR
    the ``args=`` kwarg when no positional is supplied."""
    if node.args:
        return node.args[0]
    for kw in node.keywords:
        if kw.arg == "args":
            return kw.value
    return None


def _executable_kwarg(node: ast.Call) -> ast.expr | None:
    for kw in node.keywords:
        if kw.arg == "executable":
            return kw.value
    return None


def _violation(node: ast.Call, path: Path, binary: str, reason: str) -> SubprocessViolation:
    return SubprocessViolation(
        path=path,
        line=node.lineno,
        col=node.col_offset + 1,
        binary=binary,
        reason=reason,
    )


def _check_subprocess_call(
    node: ast.Call,
    path: Path,
    allowed: set[str],
    bindings: dict[str, ast.expr],
    *,
    is_async_shell_variant: bool = False,
) -> SubprocessViolation | None:
    """Return a violation if this subprocess call is not in the allow-list."""
    if _has_shell_true_kwarg(node) or is_async_shell_variant:
        return _violation(
            node,
            path,
            "<shell=True>" if not is_async_shell_variant else "<asyncio.create_subprocess_shell>",
            "shell-injectable invocation forbidden",
        )

    # P11: prefer ``executable=`` kwarg as the effective binary if present.
    exec_kw = _executable_kwarg(node)
    if exec_kw is not None:
        binary = _extract_binary(exec_kw, bindings)
    else:
        target = _first_positional_or_args_kwarg(node, bindings)
        if target is None:
            return _violation(node, path, "<missing>", "missing first positional arg")
        binary = _extract_binary(target, bindings)

    if binary is None:
        # P12: removed the ``len(allowed) == 1`` silent permit. Dynamic
        # binaries now require an explicit ``<dynamic>`` entry.
        if _DYNAMIC_BIN in allowed:
            return None
        return _violation(node, path, "<dynamic>", "dynamic binary not approved")
    if binary not in allowed:
        return _violation(node, path, binary, "binary not allow-listed for module")
    return None


def _check_os_call(node: ast.Call, path: Path, attr: str) -> SubprocessViolation:
    return _violation(node, path, f"os.{attr}", "os shell/process APIs are forbidden")


def _check_pty_call(node: ast.Call, path: Path, attr: str) -> SubprocessViolation:
    return _violation(node, path, f"pty.{attr}", "pty spawn is forbidden")


def _scan_file(path: Path) -> list[SubprocessViolation]:  # noqa: C901 — orchestrator dispatch table
    # P20: tokenize.open honours PEP-263 + BOM.
    with tokenize.open(str(path)) as fh:
        source = fh.read()
    tree = ast.parse(source, filename=str(path))
    bindings = _const_bindings(tree)
    imports = _collect_imports(tree)
    rel = _rel_key(path)
    allowed = {binary for file_path, binary in _SUBPROCESS_ALLOWLIST if file_path == rel}
    violations: list[SubprocessViolation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        base, attr = _called_symbol(node, imports)
        if base == "subprocess" and attr in _ALLOWED_SUBPROCESS_CALLS:
            v = _check_subprocess_call(node, path, allowed, bindings)
            if v is not None:
                violations.append(v)
        elif base == "asyncio" and attr in _ALLOWED_ASYNCIO_SUBPROCESS_CALLS:
            is_shell = attr == "create_subprocess_shell"
            v = _check_subprocess_call(
                node, path, allowed, bindings, is_async_shell_variant=is_shell
            )
            if v is not None:
                violations.append(v)
        elif base == "os" and attr in _FORBIDDEN_OS_CALLS:
            violations.append(_check_os_call(node, path, attr or ""))
        elif base == "pty" and attr in _FORBIDDEN_PTY_CALLS:
            violations.append(_check_pty_call(node, path, attr or ""))
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
