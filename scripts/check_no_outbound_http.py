#!/usr/bin/env python3
"""AST static check for outbound-network imports under ``src/sdlc/`` (Story 2B.6 AC1).

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
from dataclasses import dataclass
from pathlib import Path

from sdlc.errors import SecurityError

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXEMPT_DIRS = frozenset({"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"})
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


def _check_node(node: ast.AST, path: Path) -> list[NetImportViolation]:
    """Extract violations from a single AST node (import statement only)."""
    out: list[NetImportViolation] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if _is_forbidden(alias.name):
                out.append(
                    NetImportViolation(
                        path=path, line=node.lineno, col=node.col_offset + 1, module=alias.name
                    )
                )
    elif isinstance(node, ast.ImportFrom) and node.module and _is_forbidden(node.module):
        out.append(
            NetImportViolation(
                path=path, line=node.lineno, col=node.col_offset + 1, module=node.module
            )
        )
    return out


def _scan_file(path: Path) -> list[NetImportViolation]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    violations: list[NetImportViolation] = [
        v for node in ast.walk(tree) for v in _check_node(node, path)
    ]

    filtered: list[NetImportViolation] = []
    for item in violations:
        line = lines[item.line - 1] if item.line - 1 < len(lines) else ""
        marker = _NOQA_PATTERN.search(line)
        if marker and marker.group(1) is not None:
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
