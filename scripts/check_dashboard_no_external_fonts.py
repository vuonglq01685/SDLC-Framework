"""Forbidden-pattern gate: no external font CDNs in dashboard static assets (Story 5.3 AC1 / DD-10).

Scans ``src/sdlc/dashboard/static/**`` HTML and CSS for Google Fonts / external font CDN
references. Mirrors the DD-09 gate shape (comment-stripping, exit 0/1/2, ``file:line:col``).

Usage: ``uv run python scripts/check_dashboard_no_external_fonts.py [path ...]``
No args: scans ``src/sdlc/dashboard/static`` recursively.
Exit 0 = clean; exit 1 = violations; exit 2 = explicit path not found.
"""

from __future__ import annotations

import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ROOT = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"

_SCAN_GLOBS = ("*.css", "*.html")
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"fonts\.googleapis\.com", re.IGNORECASE), "fonts.googleapis.com"),
    (re.compile(r"fonts\.gstatic\.com", re.IGNORECASE), "fonts.gstatic.com"),
    (
        re.compile(r"""@import\s+url\s*\(\s*['"]?https?://""", re.IGNORECASE),
        "@import url(http",
    ),
    (
        re.compile(
            r"""<link[^>]+href\s*=\s*["']https?://[^"']*(?:font|typekit|use\.typekit)""",
            re.IGNORECASE,
        ),
        "external font CDN <link>",
    ),
)


def _blank_comment(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


@dataclass(frozen=True, slots=True)
class FontViolation:
    path: Path
    line: int
    pattern: str
    col: int = 1


def _expand_targets(argv: list[str]) -> tuple[list[Path], list[str]]:
    if not argv:
        root = _DEFAULT_ROOT
        if not root.is_dir():
            return [], []
        files: list[Path] = []
        for ext in _SCAN_GLOBS:
            files.extend(root.rglob(ext))
        return sorted(files), []
    out: list[Path] = []
    unknown: list[str] = []
    for raw in argv:
        p = Path(raw)
        if p.is_dir():
            for ext in _SCAN_GLOBS:
                out.extend(p.rglob(ext))
        elif p.is_file():
            out.append(p)
        else:
            unknown.append(raw)
    return sorted(out), unknown


def _scan_text(path: Path, text: str) -> list[FontViolation]:
    violations: list[FontViolation] = []
    stripped = _CSS_COMMENT.sub(_blank_comment, text) if path.suffix.lower() == ".css" else text
    for lineno, line in enumerate(stripped.splitlines(), start=1):
        for pattern, label in _PATTERNS:
            match = pattern.search(line)
            if match is not None:
                violations.append(
                    FontViolation(
                        path=path,
                        line=lineno,
                        pattern=label,
                        col=match.start() + 1,
                    )
                )
                break
    return violations


def scan_paths(paths: list[Path]) -> list[FontViolation]:
    violations: list[FontViolation] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        violations.extend(_scan_text(path, text))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    targets, unknown = _expand_targets(args)
    for raw in unknown:
        print(
            f"dashboard DD-10 gate: path not found, nothing scanned: {raw}",
            file=sys.stderr,
        )
    violations = scan_paths(targets)
    if violations:
        for v in violations:
            rel = v.path
            with suppress(ValueError):
                rel = v.path.resolve().relative_to(_REPO_ROOT.resolve())
            print(f"{rel}:{v.line}:{v.col}: forbidden {v.pattern} (DD-10)", file=sys.stderr)
        return 1
    if unknown:
        return 2
    print("dashboard DD-10 gate OK (no external font CDN references)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
