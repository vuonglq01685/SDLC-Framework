#!/usr/bin/env python3
"""Scan src/sdlc/ for journal mutation patterns bypassing sdlc.journal.append (AC3, Story 1.11).

Usage: uv run python scripts/check_no_journal_mutation.py [path ...]
No args: scans src/sdlc/ recursively. Directory args are expanded recursively.
Exit 0 = clean; exit 1 = violations.

Escape hatch: ``# noqa: journal-mutation -- <reason ≥ 10 chars>`` (or em-dash variant).
Plain ``# noqa: journal-mutation`` without a reason is itself flagged as a violation.

Exempt top-level dirs (relative to repo root): tests/, scripts/, _bmad/, _bmad-output/,
.claude/, _site/, docs/. Also self-exempt: src/sdlc/journal/writer.py (canonical writer).

Fix suggestion: "<file>:<line>: journal mutation detected.
  Use sdlc.journal.append (or append_sync) instead. (FR31 + Architecture §493 + Pattern §6)"
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_EXEMPT_DIRS = frozenset({"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"})
_SELF = Path(__file__).resolve()

# Canonical write API names — intentional drift detector: if writer.py renames either,
# this constant breaks this linter (mirrors state/atomic.py + check_no_direct_state_writes.py).
_CANONICAL_WRITE_API = frozenset({"sdlc.journal.writer.append", "sdlc.journal.writer.append_sync"})

# journal-mutation noqa pattern — group 1 is the reason if present
_NOQA_PATTERN = re.compile(r"#\s*noqa:\s*journal-mutation(?:\s*(?:—|--)\s*(.{10,}))?")

# Patterns that indicate a journal path argument
_JOURNAL_PATH_NAMES = re.compile(
    r"(journal\.log|journal\.jsonl|journal_path|JOURNAL_(PATH|FILE|LOG|JSONL))",
    re.IGNORECASE,
)

# Write modes that create/overwrite/append files (all banned outside writer.py)
# Includes r+/rb+ because they enable seek+write mutation.
_WRITE_MODES = frozenset({"w", "wb", "a", "ab", "r+", "rb+", "w+", "wb+"})

_MIN_ARGS = 2

FIX_SUGGESTION = (
    "Use sdlc.journal.append (or append_sync) instead. (FR31 + Architecture §493 + Pattern §6)"
)


def _is_exempt(path: Path) -> bool:
    resolved = path.resolve()
    if resolved == _SELF:
        return True
    try:
        rel = resolved.relative_to(_REPO_ROOT.resolve())
    except ValueError:
        return False
    # journal/writer.py is the only module permitted to open the journal for writing
    if str(rel) in {
        "src/sdlc/journal/writer.py",
        "src\\sdlc\\journal\\writer.py",
    }:
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


def _is_journal_path_expr(node: ast.expr) -> bool:
    src = ast.unparse(node)
    return bool(_JOURNAL_PATH_NAMES.search(src))


def _check_open_call(node: ast.Call) -> str | None:
    """Detect open(journal_path, write_mode) — all write modes banned outside writer.py."""
    func = node.func
    is_open = (isinstance(func, ast.Name) and func.id == "open") or (
        isinstance(func, ast.Attribute) and func.attr == "open"
    )
    if not is_open:
        return None
    if len(node.args) < _MIN_ARGS:
        return None
    mode_arg = node.args[1]
    if not isinstance(mode_arg, ast.Constant) or mode_arg.value not in _WRITE_MODES:
        return None
    path_arg = node.args[0]
    if not _is_journal_path_expr(path_arg):
        return None
    return f"open() with mode '{mode_arg.value}' on journal path"


def _check_path_write_call(node: ast.Call) -> str | None:
    """Detect Path(journal_path).write_text/write_bytes(...)."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in {"write_text", "write_bytes"}:
        return None
    if not _is_journal_path_expr(func.value):
        return None
    return f"Path.{func.attr}() on journal path"


def _check_replace_call(node: ast.Call) -> str | None:
    """Detect os.replace/os.rename(<src>, journal_path) — replaces file in-place."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in {"replace", "rename"}:
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "os":
        return None
    if len(node.args) < _MIN_ARGS:
        return None
    dst_arg = node.args[1]
    if not _is_journal_path_expr(dst_arg):
        return None
    return f"os.{func.attr}() with journal path as destination"


def _collect_calls(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    """Collect all Call nodes in document order within a function body."""
    all_calls: list[ast.Call] = []

    class _FlatCallCollector(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            all_calls.append(node)
            self.generic_visit(node)

    _FlatCallCollector().visit(func_node)
    return all_calls


def _find_seek_then_write_violations(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[int, str]]:
    """Detect f.seek(...) followed by f.write(...) on the same handle in a function body.

    Uses ast.unparse equality of the receiver expression as a heuristic (best-effort literal
    match — no full dataflow). A noqa escape hatch handles false positives.
    """
    violations: list[tuple[int, str]] = []
    seen_seeks: list[tuple[int, str]] = []  # (lineno, receiver_src)
    for call in _collect_calls(func_node):
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        receiver_src = ast.unparse(func.value)
        if func.attr == "seek":
            seen_seeks.append((call.lineno, receiver_src))
        elif func.attr == "write":
            for _, seek_receiver in seen_seeks:
                if seek_receiver == receiver_src:
                    violations.append(
                        (call.lineno, f"seek()+write() anti-pattern on '{receiver_src}'")
                    )
                    break
    return violations


def _find_lseek_then_write_violations(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[int, str]]:
    """Detect os.lseek(fd, ...) followed by os.write(fd, ...) on the same fd-name."""
    violations: list[tuple[int, str]] = []
    seen_lseeks: list[tuple[int, str]] = []  # (lineno, fd_src)
    for call in _collect_calls(func_node):
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "os":
            continue
        if func.attr == "lseek" and call.args:
            seen_lseeks.append((call.lineno, ast.unparse(call.args[0])))
        elif func.attr == "write" and call.args:
            fd_src = ast.unparse(call.args[0])
            for _, lseek_fd in seen_lseeks:
                if lseek_fd == fd_src:
                    violations.append(
                        (call.lineno, f"os.lseek()+os.write() anti-pattern on fd '{fd_src}'")
                    )
                    break
    return violations


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        msg = _check_open_call(node) or _check_path_write_call(node) or _check_replace_call(node)
        if msg:
            self.violations.append((node.lineno, msg))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.violations.extend(_find_seek_then_write_violations(node))
        self.violations.extend(_find_lseek_then_write_violations(node))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.violations.extend(_find_seek_then_write_violations(node))
        self.violations.extend(_find_lseek_then_write_violations(node))
        self.generic_visit(node)


_NOQA_MISSING_REASON = (
    "noqa: journal-mutation requires a reason ≥ 10 chars"
    " (use: '# noqa: journal-mutation -- <reason>')"
)


def _filter_violations_by_noqa(
    violations: list[tuple[int, str]], lines: list[str]
) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    for lineno, msg in violations:
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        noqa_match = _NOQA_PATTERN.search(line)
        if noqa_match:
            if noqa_match.group(1) is None:
                results.append((lineno, _NOQA_MISSING_REASON))
            # else: valid noqa with reason — suppress
        else:
            results.append((lineno, msg))
    return results


def _find_bare_noqa(lines: list[str], existing: list[tuple[int, str]]) -> list[tuple[int, str]]:
    existing_linenos = {ln for ln, _ in existing}
    results: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        noqa_match = _NOQA_PATTERN.search(line)
        if noqa_match and noqa_match.group(1) is None and lineno not in existing_linenos:
            results.append((lineno, _NOQA_MISSING_REASON))
    return results


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(
            f"warning: could not read {path}: {e} — skipping",
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


def main(argv: list[str]) -> int:
    targets = _expand_targets(argv) if argv else list((_REPO_ROOT / "src" / "sdlc").rglob("*.py"))
    found_any = False
    for path in sorted(targets):
        if _is_exempt(path):
            continue
        for lineno, msg in _scan_file(path):
            print(
                f"{path}:{lineno}: journal mutation detected — {msg}. {FIX_SUGGESTION}",
                file=sys.stderr,
            )
            found_any = True
    return 1 if found_any else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
