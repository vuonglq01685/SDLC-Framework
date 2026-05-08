#!/usr/bin/env python3
"""Scan src/sdlc/ for hardcoded secret literals (NFR-SEC-1).

Usage: uv run python scripts/check_no_hardcoded_secrets.py [file ...]
No args: scans src/sdlc/ recursively. Exit 0 = clean; exit 1 = violations.
Escape hatch: add `# noqa: secret` on a line to suppress it.
Exempt dirs (never scanned): tests/, scripts/, _bmad/, _bmad-output/, .claude/, _site/, docs/
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from sdlc.config.secrets import SECRET_PATTERNS  # noqa: E402

_EXEMPT_DIRS = frozenset({"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"})
_SELF = Path(__file__).resolve()


def _is_exempt(path: Path) -> bool:
    if path.resolve() == _SELF:
        return True
    return any(exempt in path.parts for exempt in _EXEMPT_DIRS)


def _scan_file(path: Path) -> list[tuple[int, int, str]]:
    violations: list[tuple[int, int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return violations
    for lineno, line in enumerate(lines, start=1):
        if "# noqa: secret" in line:
            continue
        for pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                violations.append((lineno, match.start() + 1, pattern.pattern))
                break
    return violations


def main(argv: list[str]) -> int:
    targets = [Path(p) for p in argv] if argv else list((_REPO_ROOT / "src" / "sdlc").rglob("*.py"))
    found_any = False
    for path in sorted(targets):
        if _is_exempt(path):
            continue
        for lineno, col, pat in _scan_file(path):
            print(f"{path}:{lineno}:{col}: hardcoded secret literal matches pattern {pat!r}")
            found_any = True
    return 1 if found_any else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
