#!/usr/bin/env python3
"""Strict-model inheritance validator (ADR-025, Epic 2A prep — D2).

Any class inside src/sdlc/contracts/ that directly inherits from
pydantic.BaseModel MUST carry a ``# strict-opt-out: <reason>`` comment
on its class definition line. Classes that inherit from StrictModel
(or any non-BaseModel base) are allowed without annotation.

Rule: default-deny on direct BaseModel inheritance; annotated opt-out allowed.

Usage: uv run python scripts/check_strict_model_inheritance.py [path ...]
No args: scans src/sdlc/contracts/ recursively.
Exit 0 = clean; exit 1 = violations.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_CONTRACTS_DIR = _REPO_ROOT / "src" / "sdlc" / "contracts"

_OPT_OUT_MARKER = "# strict-opt-out:"

# Names that count as direct BaseModel inheritance (not via StrictModel).
_BASE_MODEL_NAMES = frozenset({"BaseModel"})
_BASE_MODEL_ATTRS = frozenset({"pydantic.BaseModel"})


def _is_direct_base_model(node: ast.expr) -> bool:
    """Return True if the base expression is pydantic.BaseModel (direct)."""
    if isinstance(node, ast.Name):
        return node.id in _BASE_MODEL_NAMES
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}" in _BASE_MODEL_ATTRS
    return False


def _check_file(path: Path) -> list[tuple[int, str]]:
    """Return (line, message) pairs for direct BaseModel subclasses without opt-out."""
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

    source_lines = source.splitlines()
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(_is_direct_base_model(base) for base in node.bases):
            continue

        # Class directly inherits from BaseModel — require opt-out annotation.
        # Search all header lines (from `class` to just before the body)
        # to handle multi-line class definitions produced by formatters.
        lineno = node.lineno
        header_end = node.body[0].lineno if node.body else lineno
        header_text = " ".join(source_lines[lineno - 1 : header_end])
        if _OPT_OUT_MARKER not in header_text:
            violations.append(
                (
                    lineno,
                    f"class '{node.name}' inherits directly from BaseModel "
                    f"(ADR-025: use StrictModel or add '# strict-opt-out: <reason>' "
                    f"to the class line)",
                )
            )

    return violations


def _scan(paths: list[Path]) -> dict[Path, list[tuple[int, str]]]:
    results: dict[Path, list[tuple[int, str]]] = {}
    for path in paths:
        violations = _check_file(path)
        if violations:
            results[path] = violations
    return results


def _collect_targets(args: list[str]) -> list[Path]:
    if args:
        return [Path(a) for a in args]
    return sorted(_CONTRACTS_DIR.rglob("*.py"))


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    targets = _collect_targets(args)
    results = _scan(targets)

    if not results:
        print(
            f"strict-model-inheritance check: "
            f"{len(targets)} file(s) clean (no direct BaseModel subclasses without opt-out)"
        )
        return 0

    for path, violations in sorted(results.items()):
        for lineno, msg in violations:
            print(f"{path}:{lineno}: {msg}", file=sys.stderr)
    print(
        f"\nstrict-model-inheritance FAILED: "
        f"{sum(len(v) for v in results.values())} violation(s) in {len(results)} file(s)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
