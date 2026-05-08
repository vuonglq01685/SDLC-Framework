#!/usr/bin/env python3
"""Scan src/sdlc/ for journal mutation patterns bypassing sdlc.journal.append (AC3, Story 1.11).

Usage: uv run python scripts/check_no_journal_mutation.py [path ...]
No args: scans src/sdlc/ recursively. Directory args are expanded recursively.
Exit 0 = clean; exit 1 = violations.

Escape hatch: ``# noqa: journal-mutation -- <reason ≥ 10 chars>`` (em-dash or ``:`` separator
also accepted). Plain ``# noqa: journal-mutation`` without a reason is itself flagged.

Exempt top-level dirs (relative to repo root): tests/, scripts/, _bmad/, _bmad-output/,
.claude/, _site/, docs/. Also self-exempt: src/sdlc/journal/writer.py (canonical writer).

Heuristic limitation: ``_JOURNAL_PATH_NAMES`` (in ``_journal_mutation_detectors``) is a
regex over the unparsed AST source of the path argument; computed paths via
``os.path.join("/var/log", chosen_name)``, indirect alias renames
(``alt = JOURNAL_PATH; open(alt, "w")``), and dynamic dispatch escape detection. The
drift detector (``_CANONICAL_WRITE_API``) plus the property test file-grows-only
invariant catch the residual cases.

Detectors are split into ``scripts/_journal_mutation_detectors.py`` (NFR-MAINT-3 cap).

Fix suggestion: "<file>:<line>: journal mutation detected.
  Use sdlc.journal.append (or append_sync) instead. (FR31 + Architecture §493 + Pattern §6)"
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Local detector helpers — split out per NFR-MAINT-3 LOC cap.
sys.path.insert(0, str(Path(__file__).parent))
from _journal_mutation_detectors import (  # type: ignore[import-not-found]
    _check_link_call,
    _check_open_call,
    _check_os_open_call,
    _check_path_method_open,
    _check_path_write_call,
    _check_replace_call,
    _check_truncate_call,
    _check_unlink_call,
    _collect_os_aliases,
    _find_lseek_then_write_violations,
    _find_seek_then_write_violations,
)

_REPO_ROOT = Path(__file__).parent.parent
_EXEMPT_DIRS = frozenset({"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"})
_SELF = Path(__file__).resolve()

# Canonical write API names — runtime-asserted in main() against the writer module.
_CANONICAL_WRITE_API = frozenset({"sdlc.journal.writer.append", "sdlc.journal.writer.append_sync"})

# Reason guard: requires at least one ``\w{4,}`` token (rejects "########"-style noise)
# and >= 10 chars; accepts ``--``/em-dash/``:`` separators.
_NOQA_PATTERN = re.compile(r"#\s*noqa:\s*journal-mutation(?:\s*(?:—|--|:)\s*((?=.*\w{4,}).{10,}))?")

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
    if rel.as_posix() == "src/sdlc/journal/writer.py":
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


class _Visitor(ast.NodeVisitor):
    def __init__(self, os_aliases: frozenset[str]) -> None:
        self.violations: list[tuple[int, str]] = []
        self._os_aliases = os_aliases

    def visit_Call(self, node: ast.Call) -> None:
        msg = (
            _check_open_call(node)
            or _check_os_open_call(node)
            or _check_path_method_open(node)
            or _check_path_write_call(node)
            or _check_replace_call(node)
            or _check_truncate_call(node, self._os_aliases)
            or _check_unlink_call(node, self._os_aliases)
            or _check_link_call(node, self._os_aliases)
        )
        if msg:
            self.violations.append((node.lineno, msg))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.violations.extend(_find_seek_then_write_violations(node))
        self.violations.extend(_find_lseek_then_write_violations(node, self._os_aliases))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.violations.extend(_find_seek_then_write_violations(node))
        self.violations.extend(_find_lseek_then_write_violations(node, self._os_aliases))
        self.generic_visit(node)


_NOQA_MISSING_REASON_VIOLATION = (
    "noqa: journal-mutation requires a reason ≥ 10 chars on a real violation"
    " (use: '# noqa: journal-mutation -- <reason>')"
)
_NOQA_MISSING_REASON_BARE = (
    "stray '# noqa: journal-mutation' without reason or violation"
    " (use: '# noqa: journal-mutation -- <reason>')"
)


def _string_literal_linenos(tree: ast.Module) -> set[int]:
    """Line numbers covered by string-literal ast.Constant nodes (docstrings, etc.)."""
    result: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            for ln in range(start, end + 1):
                result.add(ln)
    return result


def _logical_line_for(lineno: int, lines: list[str]) -> str:
    """Return the joined logical line for ``lineno``, walking back across ``\\``-continuations."""
    if not lines:
        return ""
    end_idx = max(0, min(lineno - 1, len(lines) - 1))
    start_idx = end_idx
    while start_idx > 0 and lines[start_idx - 1].rstrip().endswith("\\"):
        start_idx -= 1
    return "\n".join(lines[start_idx : end_idx + 1])


def _filter_violations_by_noqa(
    violations: list[tuple[int, str]], lines: list[str], string_lines: set[int] | None = None
) -> list[tuple[int, str]]:
    string_lines = string_lines or set()
    results: list[tuple[int, str]] = []
    for lineno, msg in violations:
        line = _logical_line_for(lineno, lines)
        noqa_match = _NOQA_PATTERN.search(line)
        # Discard hits that come purely from string-literal interiors.
        if noqa_match and lineno in string_lines:
            noqa_match = None
        if noqa_match:
            if noqa_match.group(1) is None:
                results.append((lineno, _NOQA_MISSING_REASON_VIOLATION))
            # else: valid noqa with reason — suppress
        else:
            results.append((lineno, msg))
    return results


def _find_bare_noqa(
    lines: list[str], existing: list[tuple[int, str]], string_lines: set[int] | None = None
) -> list[tuple[int, str]]:
    string_lines = string_lines or set()
    existing_linenos = {ln for ln, _ in existing}
    results: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        if lineno in string_lines:
            continue
        noqa_match = _NOQA_PATTERN.search(line)
        if noqa_match and noqa_match.group(1) is None and lineno not in existing_linenos:
            results.append((lineno, _NOQA_MISSING_REASON_BARE))
    return results


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"warning: could not read {path}: {e} -- skipping", file=sys.stderr)
        return []

    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    os_aliases = _collect_os_aliases(tree)
    visitor = _Visitor(os_aliases)
    visitor.visit(tree)
    # Module-level seek+write detection (review patch Edge B4) — wrap top-level statements
    # in a synthetic Module so the walker sees them as a single contiguous scope.
    module_top = ast.Module(
        body=[
            n
            for n in tree.body
            if not isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        ],
        type_ignores=[],
    )
    visitor.violations.extend(_find_seek_then_write_violations(module_top))
    visitor.violations.extend(_find_lseek_then_write_violations(module_top, os_aliases))

    string_lines = _string_literal_linenos(tree)
    results = _filter_violations_by_noqa(visitor.violations, lines, string_lines)
    results.extend(_find_bare_noqa(lines, results, string_lines))
    return results


def _assert_canonical_api() -> None:
    """Runtime drift check: writer.py must still expose append + append_sync."""
    try:
        import sdlc.journal.writer as w  # noqa: PLC0415
    except ImportError:
        # Writer is POSIX-only; on Windows the ImportError raise is the documented path.
        return
    assert hasattr(w, "append") and hasattr(w, "append_sync"), (
        "_CANONICAL_WRITE_API drift: sdlc.journal.writer must expose append + append_sync"
    )


def main(argv: list[str]) -> int:
    _assert_canonical_api()
    targets = _expand_targets(argv) if argv else list((_REPO_ROOT / "src" / "sdlc").rglob("*.py"))
    found_any = False
    for path in sorted(targets):
        if _is_exempt(path):
            continue
        for lineno, msg in _scan_file(path):
            print(
                f"{path}:{lineno}: journal mutation detected -- {msg}. {FIX_SUGGESTION}",
                file=sys.stderr,
            )
            found_any = True
    return 1 if found_any else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
