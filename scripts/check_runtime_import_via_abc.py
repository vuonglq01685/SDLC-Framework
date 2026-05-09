#!/usr/bin/env python3
"""Runtime ABC-only import validator (AC4 / Architecture §1106 / Story 1.13).

Engine and dispatcher MUST import runtime via the ABC re-export only:
    from sdlc.runtime import AIRuntime, AgentResult        # OK
    import sdlc.runtime                                    # OK (re-export namespace)
    from sdlc.runtime.mock import MockAIRuntime             # FORBIDDEN in engine/dispatcher
    from sdlc.runtime.claude import ClaudeAIRuntime         # FORBIDDEN in engine/dispatcher
    from sdlc.runtime.abc import AIRuntime          # FORBIDDEN (use re-export from sdlc.runtime)
    import sdlc.runtime.mock                                # FORBIDDEN (sub-module path)

cli/ has a permissive exception (Architecture §1071 — "runtime (only mock for tests)").
Other modules' runtime usage is governed by MODULE_DEPS["runtime"].forbidden_from already.

Usage: uv run python scripts/check_runtime_import_via_abc.py [path ...]
No args: scans src/sdlc/engine/ and src/sdlc/dispatcher/ recursively.
Exit 0 = clean; exit 1 = violations.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_GUARDED_PARENTS = (
    _REPO_ROOT / "src" / "sdlc" / "engine",
    _REPO_ROOT / "src" / "sdlc" / "dispatcher",
)
_PERMISSIVE_PARENTS = (_REPO_ROOT / "src" / "sdlc" / "cli",)

# Only the top-level re-export namespace is allowed in engine/dispatcher.
_ALLOWED_RUNTIME_MODULE = "sdlc.runtime"

# Any sub-module path is forbidden in guarded dirs (forward-compat: covers claude.py if absent).
_FORBIDDEN_PREFIX = "sdlc.runtime."


def _is_guarded(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(parent.resolve()) for parent in _GUARDED_PARENTS)


def _is_permissive(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(parent.resolve()) for parent in _PERMISSIVE_PARENTS)


def _check_import_from(node: ast.ImportFrom) -> list[tuple[int, str]]:
    """Flag `from sdlc.runtime.<sub> import ...`; allow `from sdlc.runtime import ...`."""
    module = node.module or ""
    if module == _ALLOWED_RUNTIME_MODULE:
        return []
    if module.startswith(_FORBIDDEN_PREFIX):
        sub = module[len(_FORBIDDEN_PREFIX) :]
        return [
            (
                node.lineno,
                f"forbidden direct import from sdlc.runtime.{sub}; "
                f"use `from sdlc.runtime import ...` (Architecture §1106)",
            )
        ]
    return []


def _check_import(node: ast.Import) -> list[tuple[int, str]]:
    """Flag `import sdlc.runtime.<sub>` (forbidden); allow `import sdlc.runtime`.

    Handles aliased imports (`import sdlc.runtime.mock as m`) — the alias does not
    change the imported module path, so the same rule applies.
    """
    violations: list[tuple[int, str]] = []
    for alias in node.names:
        name = alias.name
        if name == _ALLOWED_RUNTIME_MODULE:
            continue
        if name.startswith(_FORBIDDEN_PREFIX):
            sub = name[len(_FORBIDDEN_PREFIX) :]
            violations.append(
                (
                    node.lineno,
                    f"forbidden direct import of sdlc.runtime.{sub}; "
                    f"use `from sdlc.runtime import ...` (Architecture §1106)",
                )
            )
    return violations


def _check_file(path: Path) -> list[tuple[int, str]]:
    """Return (line, message) pairs for forbidden runtime imports in path.

    Handles both `from X import Y` (ast.ImportFrom) and `import X[.Y]` (ast.Import) syntaxes.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"warning: could not read {path}: {exc} -- skipping", file=sys.stderr)
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        print(f"warning: could not parse {path}: {exc} -- skipping", file=sys.stderr)
        return []

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            violations.extend(_check_import_from(node))
        elif isinstance(node, ast.Import):
            violations.extend(_check_import(node))
    return violations


def _expand_targets(paths: list[str]) -> list[Path]:
    """Expand argv paths into a list of Python files to check.

    Directories are recursively globbed for `*.py`. Files with `.py` suffix or
    `.py.txt` (lint negative-test fixtures) are accepted; other suffixes are
    rejected with a warning rather than silently AST-parsed.
    """
    expanded: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            expanded.extend(sorted(path.rglob("*.py")))
        elif path.suffix == ".py" or path.name.endswith(".py.txt"):
            expanded.append(path)
        else:
            print(
                f"warning: skipping non-Python path {path} (unsupported suffix)",
                file=sys.stderr,
            )
    return expanded


def _default_targets() -> list[Path]:
    targets: list[Path] = []
    for parent in _GUARDED_PARENTS:
        if parent.exists():
            targets.extend(sorted(parent.rglob("*.py")))
    return targets


def main(argv: list[str]) -> int:
    targets = _expand_targets(argv) if argv else _default_targets()

    found_any = False
    for path in targets:
        # cli/ has an explicit permissive exception per Architecture §1071 — the rule
        # relaxes there to allow `from sdlc.runtime.mock import MockAIRuntime` for
        # test-only DI. Skip permissive parents before guard check so the relaxation
        # is documented at the call site, not implicit.
        if _is_permissive(path):
            continue
        if not _is_guarded(path):
            continue

        for lineno, msg in _check_file(path):
            print(f"{path}:{lineno}: {msg}", file=sys.stderr)
            found_any = True

    return 1 if found_any else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
