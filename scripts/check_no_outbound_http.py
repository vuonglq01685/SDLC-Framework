#!/usr/bin/env python3
"""AST static check for outbound-network imports under ``src/sdlc/`` (Story 2B.6 AC1, post-review).

Post-review patches (2026-05-28 bmad-code-review):
- D7: ``scripts/`` removed from ``_EXEMPT_DIRS`` so supply-chain risk in build /
  install helpers is also scanned.
- P17: detects dynamic-import escape hatches ``importlib.import_module("requests")``
  and ``__import__("requests")``.
- P18: relative imports ``from . import foo`` are NOT matched against the
  forbidden absolute module set (``node.level > 0`` short-circuits).
- P19: ``# noqa: net`` lookup walks the physical line range of the import
  (``node.lineno..node.end_lineno``) so continuation-line and decorated forms
  honour the marker.
- P20: source opened via ``tokenize.open`` so PEP-263 encoding cookies and BOM
  are respected (UTF-16/UTF-8-BOM no longer aborts the whole scan).

Usage: ``uv run python scripts/check_no_outbound_http.py [path ...]``
No args: scan ``src/sdlc`` recursively.
Exit codes:
  - 0: clean
  - 2: violations (ERR_SECURITY semantics)

Escape hatch:
  ``# noqa: net -- <reason >= 10 chars>`` (or em-dash ``—`` form)
"""

from __future__ import annotations

import ast
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

from sdlc.errors import SecurityError

_REPO_ROOT = Path(__file__).resolve().parent.parent
# D7: ``scripts/`` removed — supply-chain risk lives here.
_EXEMPT_DIRS = frozenset({"tests", "_bmad", "_bmad-output", ".claude", "_site", "docs"})
_SELF = Path(__file__).resolve()
_FORBIDDEN_NETWORK_MODULES: frozenset[str] = frozenset(
    {
        "http.client",
        "http.server",
        "urllib",
        "urllib.request",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "telnetlib",
        "socket",
    }
)
_NOQA_PATTERN = re.compile(r"#\s*noqa:\s*net(?:\s*(?:—|--)\s*(.{10,}))?")
# P17: dynamic-import call names whose first positional ``Constant(str)`` arg
# we treat as a module-name probe.
_DYNAMIC_IMPORT_CALL_NAMES: frozenset[str] = frozenset({"import_module", "__import__"})


@dataclass(frozen=True, slots=True)
class NetImportViolation:
    path: Path
    line: int
    col: int
    module: str

    def to_security_error(self) -> SecurityError:
        return SecurityError(
            f"module {self.path} imports forbidden network module {self.module}",
            details={
                "path": str(self.path),
                "line": self.line,
                "col": self.col,
                "module": self.module,
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


def _is_forbidden(module: str) -> bool:
    return any(
        module == base or module.startswith(f"{base}.") for base in _FORBIDDEN_NETWORK_MODULES
    )


def _dynamic_import_module_arg(node: ast.Call) -> str | None:
    """P17: return the module-name string literal for ``importlib.import_module``
    or ``__import__`` calls, else ``None`` (and for non-literal args)."""
    func = node.func
    name: str | None = None
    if isinstance(func, ast.Attribute) and func.attr in _DYNAMIC_IMPORT_CALL_NAMES:
        name = func.attr
    elif isinstance(func, ast.Name) and func.id in _DYNAMIC_IMPORT_CALL_NAMES:
        name = func.id
    if name is None or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _check_node(node: ast.AST, path: Path) -> list[NetImportViolation]:
    """Extract violations from a single AST node."""
    out: list[NetImportViolation] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if _is_forbidden(alias.name):
                out.append(
                    NetImportViolation(
                        path=path, line=node.lineno, col=node.col_offset + 1, module=alias.name
                    )
                )
    elif isinstance(node, ast.ImportFrom):
        # P18: relative imports do not resolve to the absolute forbidden set.
        if node.level == 0 and node.module and _is_forbidden(node.module):
            out.append(
                NetImportViolation(
                    path=path, line=node.lineno, col=node.col_offset + 1, module=node.module
                )
            )
    elif isinstance(node, ast.Call):
        mod = _dynamic_import_module_arg(node)
        if mod is not None and _is_forbidden(mod):
            out.append(
                NetImportViolation(path=path, line=node.lineno, col=node.col_offset + 1, module=mod)
            )
    return out


def _noqa_in_range(lines: list[str], start: int, end: int | None) -> bool:
    """P19: search ``# noqa: net -- <reason>`` across the physical line range
    of the statement; honour the marker if it appears on any of those lines."""
    last = end if end is not None else start
    for ln in range(start, last + 1):
        idx = ln - 1
        if 0 <= idx < len(lines):
            marker = _NOQA_PATTERN.search(lines[idx])
            if marker and marker.group(1) is not None:
                return True
    return False


def _read_source(path: Path) -> str:
    """P20: ``tokenize.open`` honours PEP-263 encoding cookie + BOM."""
    with tokenize.open(str(path)) as fh:
        return fh.read()


def _scan_file(path: Path) -> list[NetImportViolation]:
    source = _read_source(path)
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))

    # Collect (violation, statement-end-line) pairs so the noqa lookup can
    # walk the physical range (P19).
    raw: list[tuple[NetImportViolation, int | None]] = []
    for node in ast.walk(tree):
        for v in _check_node(node, path):
            end_lineno: int | None = getattr(node, "end_lineno", None)
            raw.append((v, end_lineno))

    filtered: list[NetImportViolation] = []
    for item, end in raw:
        if _noqa_in_range(lines, item.line, end):
            continue
        filtered.append(item)
    return filtered


def scan_file(path: Path) -> list[NetImportViolation]:
    try:
        return _scan_file(path)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise SecurityError(
            "network-import scan target is unreadable or invalid",
            details={"path": str(path), "error": type(exc).__name__},
        ) from exc


def main(argv: list[str]) -> int:
    found = False
    for target in sorted(_expand_targets(argv)):
        if _is_exempt(target):
            continue
        for violation in scan_file(target):
            err = violation.to_security_error()
            print(f"{target}:{violation.line}:{violation.col}: {err.message}")
            found = True
    return 2 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
