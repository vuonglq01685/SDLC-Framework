#!/usr/bin/env python3
"""Scan src/sdlc/ for direct state.json writes bypassing write_state_atomic (AC3, Story 1.10).

Usage: uv run python scripts/check_no_direct_state_writes.py [path ...]
No args: scans src/sdlc/ recursively. Directory args are expanded recursively.
Exit 0 = clean; exit 1 = violations.

Escape hatch: ``# noqa: state-write -- <reason ≥ 10 chars>`` (or em-dash variant).
Plain ``# noqa: state-write`` without a reason is itself flagged as a violation.

Exempt top-level dirs (relative to repo root): tests/, scripts/, _bmad/, _bmad-output/,
.claude/, _site/, docs/. Also self-exempt: src/sdlc/state/atomic.py (canonical writer).

Fix suggestion: "<file>:<line>: direct state write detected.
  Use sdlc.state.atomic.write_state_atomic instead. (Architecture §493 + Pattern §6)"
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_EXEMPT_DIRS = frozenset({"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"})
_SELF = Path(__file__).resolve()

# Canonical write API names — intentional drift detector (mirrors atomic.py constant).
_CANONICAL_WRITE_API = frozenset(
    {"sdlc.state.atomic.write_state_atomic", "sdlc.state.atomic.write_state_atomic_sync"}
)

# state-write noqa pattern — group 1 is the reason if present
_NOQA_PATTERN = re.compile(r"#\s*noqa:\s*state-write(?:\s*(?:—|--)\s*(.{10,}))?")

# Patterns that indicate a state path argument
_STATE_PATH_NAMES = re.compile(
    r"(state\.json|state_path|STATE_PATH|STATE_FILE|STATE_JSON)", re.IGNORECASE
)

# Write modes that create/overwrite files
_WRITE_MODES = frozenset({"w", "wb", "a", "ab", "w+", "wb+"})
_MIN_ARGS = 2


def _is_exempt(path: Path) -> bool:
    resolved = path.resolve()
    # Self-exempt: the linter itself
    if resolved == _SELF:
        return True
    # Self-exempt: the canonical state writer
    try:
        rel = resolved.relative_to(_REPO_ROOT.resolve())
    except ValueError:
        return False
    # state/atomic.py is the canonical writer — exempt
    if str(rel) in {"src/sdlc/state/atomic.py", "src\\sdlc\\state\\atomic.py"}:
        return True
    return bool(rel.parts) and rel.parts[0] in _EXEMPT_DIRS


def _expand_targets(paths: list[str]) -> list[Path]:
    expanded: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            expanded.extend(path.rglob("*.py"))
        else:
            expanded.append(path)
    return expanded


def _is_state_path_expr(node: ast.expr) -> bool:
    """Return True if the AST expression looks like a state.json path reference."""
    src = ast.unparse(node)
    return bool(_STATE_PATH_NAMES.search(src))


def _check_open_call(node: ast.Call) -> bool:
    """Return True if this is a banned open(..., "w"/"wb"/...) on a state path."""
    func = node.func
    is_open = (isinstance(func, ast.Name) and func.id == "open") or (
        isinstance(func, ast.Attribute) and func.attr == "open"
    )
    if not is_open:
        return False
    if len(node.args) < _MIN_ARGS:
        return False
    mode_arg = node.args[1]
    if not isinstance(mode_arg, ast.Constant) or mode_arg.value not in _WRITE_MODES:
        return False
    path_arg = node.args[0]
    return _is_state_path_expr(path_arg)


def _check_path_write(node: ast.Call) -> bool:
    """Return True if this is Path(...).write_text/write_bytes on a state.json path."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in {"write_text", "write_bytes"}:
        return False
    return _is_state_path_expr(func.value)


def _check_os_rename_replace(node: ast.Call) -> bool:
    """Return True if this is os.replace/os.rename with a state.json destination."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in {"replace", "rename"}:
        return False
    if not isinstance(func.value, ast.Name) or func.value.id != "os":
        return False
    if len(node.args) < _MIN_ARGS:
        return False
    dst_arg = node.args[1]
    return _is_state_path_expr(dst_arg)


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if _check_open_call(node):
            self.violations.append((node.lineno, "open() with write mode on state path"))
        elif _check_path_write(node):
            self.violations.append((node.lineno, "Path.write_text/write_bytes on state path"))
        elif _check_os_rename_replace(node):
            self.violations.append(
                (node.lineno, "os.replace/os.rename with state.json destination")
            )
        self.generic_visit(node)


_NOQA_MISSING_REASON = (
    "noqa: state-write requires a reason ≥ 10 chars (use: '# noqa: state-write -- <reason>')"
)


def _filter_violations_by_noqa(
    violations: list[tuple[int, str]], lines: list[str]
) -> list[tuple[int, str]]:
    """Apply noqa filtering: suppress valid suppressions, flag missing reasons."""
    results: list[tuple[int, str]] = []
    for lineno, msg in violations:
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        noqa_match = _NOQA_PATTERN.search(line)
        if noqa_match:
            if noqa_match.group(1) is None:
                results.append((lineno, _NOQA_MISSING_REASON))
            # else: valid noqa — suppress violation
        else:
            results.append((lineno, msg))
    return results


def _find_bare_noqa(lines: list[str], existing: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Find bare noqa directives not associated with any AST violation."""
    existing_linenos = {ln for ln, _ in existing}
    results: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        noqa_match = _NOQA_PATTERN.search(line)
        if noqa_match and noqa_match.group(1) is None and lineno not in existing_linenos:
            results.append((lineno, _NOQA_MISSING_REASON))
    return results


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (lineno, message) violations in file."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(
            f"warning: could not read {path}: {e} — skipping (file not scanned)",
            file=sys.stderr,
        )
        return []

    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    visitor = _Visitor()
    visitor.visit(tree)

    results = _filter_violations_by_noqa(visitor.violations, lines)
    results.extend(_find_bare_noqa(lines, results))
    return results


FIX_SUGGESTION = (
    "Use sdlc.state.atomic.write_state_atomic instead. (Architecture §493 + Pattern §6)"
)


def main(argv: list[str]) -> int:
    targets = _expand_targets(argv) if argv else list((_REPO_ROOT / "src" / "sdlc").rglob("*.py"))
    found_any = False
    for path in sorted(targets):
        if _is_exempt(path):
            continue
        for lineno, msg in _scan_file(path):
            print(
                f"{path}:{lineno}: direct state write detected — {msg}. {FIX_SUGGESTION}",
                file=sys.stderr,
            )
            found_any = True
    return 1 if found_any else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
