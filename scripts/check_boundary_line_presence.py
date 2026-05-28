#!/usr/bin/env python3
"""Static NFR-SEC-3 gate for prompt builders.

A function is scanned when its name ends with ``_prompt_builder`` and it
accepts one of: ``idea_text``, ``primary_input``, ``secondary_input``.
It must reference ``BOUNDARY_LINE`` and assign ``boundary_block`` before any
user-text block (``user_block``, ``primary_block``, ``secondary_block``).
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sdlc.errors import SecurityError  # noqa: E402

_DEFAULT_SCAN_PATH = _SRC / "sdlc" / "dispatcher" / "prompts.py"
_PROMPT_SUFFIX = "_prompt_builder"
_USER_TEXT_PARAMS = frozenset({"idea_text", "primary_input", "secondary_input"})
_USER_BLOCK_NAMES = frozenset({"user_block", "primary_block", "secondary_block"})


@dataclass(frozen=True, slots=True)
class BoundaryLineViolation:
    path: Path
    line: int
    reason: str

    def format_location(self) -> str:
        try:
            rel = self.path.resolve().relative_to(_REPO_ROOT)
        except ValueError:
            rel = self.path.resolve()
        return f"{rel}:{self.line}"

    def to_security_error(self) -> SecurityError:
        loc = self.format_location()
        return SecurityError(
            f"prompt template {loc} interpolates user text without boundary line",
            details={"path": str(self.path), "line": self.line, "reason": self.reason},
        )


def _iter_function_defs(tree: ast.AST) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]


def _is_user_text_prompt_builder(node: ast.FunctionDef) -> bool:
    if not node.name.endswith(_PROMPT_SUFFIX):
        return False
    names = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
    return bool(names & _USER_TEXT_PARAMS)


def _assignment_line(node: ast.FunctionDef, name: str) -> int | None:
    for child in ast.walk(node):
        if not isinstance(child, ast.Assign):
            continue
        for target in child.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return child.lineno
    return None


def _references_boundary_line(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "BOUNDARY_LINE":
            return True
    return False


def _boundary_precedes_user_blocks(node: ast.FunctionDef) -> bool:
    boundary_line = _assignment_line(node, "boundary_block")
    user_lines = [ln for nm in _USER_BLOCK_NAMES if (ln := _assignment_line(node, nm)) is not None]
    if boundary_line is None or not user_lines:
        return False
    return boundary_line < min(user_lines)


def _violation_line(node: ast.FunctionDef, source: str) -> int:
    segment = ast.get_source_segment(source, node) or ""
    for off, line in enumerate(segment.splitlines()):
        if "<USER_IDEA>" in line:
            return node.lineno + off
    return node.lineno


def scan_file(path: Path) -> list[BoundaryLineViolation]:
    if not path.exists():
        raise SecurityError(
            "prompt template scan target does not exist", details={"path": str(path)}
        )
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecurityError(
            "prompt template scan target is unreadable", details={"path": str(path)}
        ) from exc
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise SecurityError(
            "prompt template scan target contains syntax errors", details={"path": str(path)}
        ) from exc

    violations: list[BoundaryLineViolation] = []
    for node in _iter_function_defs(tree):
        if not _is_user_text_prompt_builder(node):
            continue
        line = _violation_line(node, source)
        if not _references_boundary_line(node):
            violations.append(BoundaryLineViolation(path, line, "missing BOUNDARY_LINE reference"))
            continue
        if not _boundary_precedes_user_blocks(node):
            violations.append(
                BoundaryLineViolation(path, line, "<BOUNDARY> block must precede <USER_IDEA>")
            )
    return violations


def main(argv: list[str]) -> int:
    targets = [Path(raw) for raw in argv] if argv else [_DEFAULT_SCAN_PATH]
    violations: list[BoundaryLineViolation] = []
    for target in targets:
        violations.extend(scan_file(target))
    for v in violations:
        err = v.to_security_error()
        print(f"{v.format_location()}: {err.message} ({v.reason})")
    return 2 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
