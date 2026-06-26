#!/usr/bin/env python3
"""Forbidden-pattern gate: UX §7.12 v1 absences (Story 5.12 AC1).

Scans dashboard static HTML/CSS/JS for deliberately-absent UX patterns:
modals/dialogs, in-app forms, toasts, client-side routing (``history.pushState``),
and skeleton-loader class hints.

Usage: ``uv run python scripts/check_dashboard_forbidden_patterns.py [path ...]``
No args: scans ``src/sdlc/dashboard/static`` recursively.
Exit 0 = clean; exit 1 = violations (``file:line:col``); exit 2 = explicit path not found.
"""

from __future__ import annotations

import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ROOT = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"

_SCAN_GLOBS = ("*.css", "*.js", "*.mjs", "*.html")
_JS_SUFFIXES = frozenset({".js", ".mjs"})

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# Epic-AC token set (D6). Skeleton-loader class hints, matched token-aware so BEM
# (`skeleton__row`) and compound (`loading-skeleton`, `card-skeleton`) class names
# are caught, not only the bare word.
_SKELETON_CLASS_NAMES = ("skeleton", "shimmer", "placeholder-loading")
_SKELETON_HINT = "(?:" + "|".join(_SKELETON_CLASS_NAMES) + ")"
_SKELETON_CLASS_RE = re.compile(_SKELETON_HINT, re.IGNORECASE)

_HTML_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # `(?![\w-])` (not `\b`) so hyphenated custom elements (`<dialog-box>`,
    # `<form-row>`) are NOT false-flagged as the forbidden element.
    (re.compile(r"<\s*dialog(?![\w-])", re.IGNORECASE), "<dialog>"),
    (re.compile(r"<\s*modal(?![\w-])", re.IGNORECASE), "<modal>"),
    # Bare/boolean `data-toast` (no `=` required) also forbidden.
    (re.compile(r"\bdata-toast\b", re.IGNORECASE), "data-toast attribute"),
    (re.compile(r"<\s*form(?![\w-])", re.IGNORECASE), "<form> (in-app)"),
)

_CSS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        # `.<…hint…>` class selector — token-aware (`.skeleton__row`,
        # `.loading-skeleton`, `.card-skeleton` all match).
        re.compile(r"\.[\w-]*" + _SKELETON_HINT + r"[\w-]*", re.IGNORECASE),
        "skeleton-loader CSS class",
    ),
)

# JS comments are blanked (mirrors HTML/CSS) so a §7.12 doc comment (e.g.
# "// we never call history.pushState") does not false-trip the gate. Only block
# comments and whole-line `//` comments are stripped — never inline trailing
# comments, to avoid blanking past a real call on the same line.
_JS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_JS_LINE_COMMENT = re.compile(r"(?m)^[ \t]*//[^\n]*")

_JS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"history\.pushState\s*\("), "history.pushState (client router)"),
    (re.compile(r"history\.replaceState\s*\("), "history.replaceState (client router)"),
)

_HTML_CLASS_ATTR = re.compile(
    r"""class\s*=\s*(['"])(?P<classes>.*?)\1""",
    re.IGNORECASE | re.DOTALL,
)


def _blank_comment(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


@dataclass(frozen=True, slots=True)
class ForbiddenViolation:
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


def _line_col(text: str, idx: int) -> tuple[int, int]:
    line = text.count("\n", 0, idx) + 1
    col = idx - text.rfind("\n", 0, idx)
    return line, col


def _scan_line_patterns(
    path: Path,
    text: str,
    patterns: tuple[tuple[re.Pattern[str], str], ...],
) -> list[ForbiddenViolation]:
    violations: list[ForbiddenViolation] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, label in patterns:
            match = pattern.search(line)
            if match is not None:
                violations.append(
                    ForbiddenViolation(
                        path=path,
                        line=lineno,
                        pattern=label,
                        col=match.start() + 1,
                    )
                )
                break
    return violations


def _scan_html_class_skeleton(path: Path, text: str) -> list[ForbiddenViolation]:
    violations: list[ForbiddenViolation] = []
    for match in _HTML_CLASS_ATTR.finditer(text):
        classes = match.group("classes")
        skeleton = _SKELETON_CLASS_RE.search(classes)
        if skeleton is not None:
            line, col = _line_col(text, match.start() + skeleton.start())
            violations.append(
                ForbiddenViolation(
                    path=path,
                    line=line,
                    pattern="skeleton-loader CSS class",
                    col=col,
                )
            )
    return violations


def _scan_html(path: Path, text: str) -> list[ForbiddenViolation]:
    stripped = _HTML_COMMENT.sub(_blank_comment, text)
    violations = _scan_line_patterns(path, stripped, _HTML_PATTERNS)
    violations.extend(_scan_html_class_skeleton(path, stripped))
    return violations


def _scan_css(path: Path, text: str) -> list[ForbiddenViolation]:
    stripped = _CSS_COMMENT.sub(_blank_comment, text)
    return _scan_line_patterns(path, stripped, _CSS_PATTERNS)


def _scan_js(path: Path, text: str) -> list[ForbiddenViolation]:
    stripped = _JS_BLOCK_COMMENT.sub(_blank_comment, text)
    stripped = _JS_LINE_COMMENT.sub(_blank_comment, stripped)
    return _scan_line_patterns(path, stripped, _JS_PATTERNS)


def scan_paths(paths: list[Path]) -> list[ForbiddenViolation]:
    violations: list[ForbiddenViolation] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix.lower()
        if suffix == ".html":
            violations.extend(_scan_html(path, text))
        elif suffix == ".css":
            violations.extend(_scan_css(path, text))
        elif suffix in _JS_SUFFIXES:
            violations.extend(_scan_js(path, text))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    targets, unknown = _expand_targets(args)
    for raw in unknown:
        print(
            f"dashboard forbidden-patterns gate: path not found, nothing scanned: {raw}",
            file=sys.stderr,
        )
    violations = scan_paths(targets)
    if violations:
        for v in violations:
            rel = v.path
            with suppress(ValueError):
                rel = v.path.resolve().relative_to(_REPO_ROOT.resolve())
            print(
                f"{rel}:{v.line}:{v.col}: {v.pattern} (UX §7.12)",
                file=sys.stderr,
            )
        return 1
    if unknown:
        return 2
    print("dashboard forbidden-patterns gate OK (no §7.12 violations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
