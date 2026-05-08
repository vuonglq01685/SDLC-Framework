#!/usr/bin/env python3
"""Scan src/sdlc/ for hardcoded secret literals (NFR-SEC-1).

Usage: uv run python scripts/check_no_hardcoded_secrets.py [path ...]
No args: scans src/sdlc/ recursively. Directory args are expanded recursively.
Exit 0 = clean; exit 1 = violations.

Escape hatch: ``# noqa: secret -- <reason ≥ 10 chars>`` (or em-dash variant
``# noqa: secret — <reason>``). Plain ``# noqa: secret`` without a reason is
itself flagged as a violation — every suppression must carry an audit trail.

Exempt top-level dirs (relative to repo root): tests/, scripts/, _bmad/,
_bmad-output/, .claude/, _site/, docs/. Exemption is anchored to the first
path segment so e.g. src/sdlc/scripts/foo.py is NOT exempt.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
# Append (not insert) so an installed `sdlc` package wins; only fall back to
# the repo's local src/ when the package is not on the path.
sys.path.append(str(_REPO_ROOT / "src"))

from sdlc.config.secrets import SECRET_PATTERNS  # noqa: E402

_EXEMPT_DIRS = frozenset({"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"})
_SELF = Path(__file__).resolve()

# Match `# noqa: secret` optionally followed by a justification of >=10 chars
# preceded by `--` or em-dash. Group 1 is the reason if present, else None.
_NOQA_PATTERN = re.compile(r"#\s*noqa:\s*secret(?:\s*(?:—|--)\s*(.{10,}))?")


def _is_exempt(path: Path) -> bool:
    resolved = path.resolve()
    if resolved == _SELF:
        return True
    try:
        rel = resolved.relative_to(_REPO_ROOT.resolve())
    except ValueError:
        return False
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


def _scan_file(path: Path) -> list[tuple[int, int, str]]:
    violations: list[tuple[int, int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return violations
    for lineno, line in enumerate(lines, start=1):
        noqa_match = _NOQA_PATTERN.search(line)
        if noqa_match:
            if noqa_match.group(1) is None:
                violations.append((
                    lineno,
                    noqa_match.start() + 1,
                    "# noqa: secret missing justification "
                    "(required: '# noqa: secret -- <reason ≥ 10 chars>')",
                ))
            continue
        for pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                violations.append((lineno, match.start() + 1, pattern.pattern))
                break
    return violations


def main(argv: list[str]) -> int:
    targets = _expand_targets(argv) if argv else list((_REPO_ROOT / "src" / "sdlc").rglob("*.py"))
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
