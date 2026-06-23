#!/usr/bin/env python3
"""Forbidden-pattern gate: no ``data-theme`` in dashboard static assets (Story 5.2 AC3 / DD-09).

Scans ``src/sdlc/dashboard/static/**`` CSS for ``[data-theme`` selectors, JS for
reads/writes of ``data-theme`` (``getAttribute`` / ``setAttribute`` / ``dataset.theme`` /
``dataset['theme']``), and HTML for a ``data-theme`` attribute or inline
``<script>`` / ``<style>`` theme references.

Usage: ``uv run python scripts/check_dashboard_no_data_theme.py [path ...]``
No args: scans ``src/sdlc/dashboard/static`` recursively.
Exit 0 = clean; exit 1 = violations (reports ``file:line``); exit 2 = explicit path not found.
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

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# Allow whitespace after ``[`` so the CSS-valid spaced form ``[ data-theme ]`` is caught.
_CSS_PATTERN = re.compile(r"\[\s*data-theme", re.IGNORECASE)
# Specific patterns FIRST so the bare ``data-theme`` catch-all (last) never shadows
# them — keeps violation labels accurate and the specific patterns reachable.
_JS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"""getAttribute\s*\(\s*['"]data-theme['"]\s*\)"""), "getAttribute(data-theme)"),
    (re.compile(r"""setAttribute\s*\(\s*['"]data-theme['"]"""), "setAttribute(data-theme)"),
    (re.compile(r"""dataset\s*\[\s*['"]theme['"]\s*\]"""), "dataset[theme]"),
    (re.compile(r"dataset\.theme\b"), "dataset.theme"),
    (re.compile(r"data-theme", re.IGNORECASE), "data-theme"),
)


def _blank_comment(match: re.Match[str]) -> str:
    """Replace a CSS comment with same-shape blanks, preserving newlines.

    Keeps line numbers and column offsets accurate for violations that follow a
    multi-line comment (a plain ``sub("")`` would collapse the embedded newlines).
    """
    return re.sub(r"[^\n]", " ", match.group(0))


@dataclass(frozen=True, slots=True)
class ThemeViolation:
    path: Path
    line: int
    pattern: str
    col: int = 1


def _expand_targets(argv: list[str]) -> tuple[list[Path], list[str]]:
    """Expand args to scannable files. Returns ``(targets, unknown_paths)``.

    ``unknown_paths`` holds explicit args that are neither a dir nor a file — a
    misconfigured invocation must not be reported as a clean pass (see ``main``).
    """
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


def _scan_css(path: Path, text: str) -> list[ThemeViolation]:
    violations: list[ThemeViolation] = []
    stripped = _CSS_COMMENT.sub(_blank_comment, text)
    for lineno, line in enumerate(stripped.splitlines(), start=1):
        match = _CSS_PATTERN.search(line)
        if match is not None:
            violations.append(
                ThemeViolation(path=path, line=lineno, pattern="[data-theme", col=match.start() + 1)
            )
    return violations


def _scan_js(path: Path, text: str) -> list[ThemeViolation]:
    violations: list[ThemeViolation] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, label in _JS_PATTERNS:
            match = pattern.search(line)
            if match is not None:
                violations.append(
                    ThemeViolation(
                        path=path,
                        line=lineno,
                        pattern=label,
                        col=match.start() + 1,
                    )
                )
                break
    return violations


def scan_paths(paths: list[Path]) -> list[ThemeViolation]:
    violations: list[ThemeViolation] = []
    for path in paths:
        if not path.is_file():
            continue
        # ``errors="replace"`` keeps the gate producing a verdict (never a
        # UnicodeDecodeError crash) on a non-UTF-8 asset; an ASCII ``data-theme``
        # still decodes and flags, so this introduces no false negative.
        text = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix.lower()
        if suffix == ".css":
            violations.extend(_scan_css(path, text))
        elif suffix in _JS_SUFFIXES:
            violations.extend(_scan_js(path, text))
        elif suffix == ".html":
            # Inline ``<script>`` (dataset/getAttribute/setAttribute), inline
            # ``<style>`` ``[data-theme]``, and a ``data-theme=`` attribute all
            # surface through the JS pattern set (the bare ``data-theme`` catch-all
            # covers the attribute and the inline-style selector).
            violations.extend(_scan_js(path, text))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    targets, unknown = _expand_targets(args)
    for raw in unknown:
        print(
            f"dashboard DD-09 gate: path not found, nothing scanned: {raw}",
            file=sys.stderr,
        )
    violations = scan_paths(targets)
    if violations:
        for v in violations:
            rel = v.path
            with suppress(ValueError):
                rel = v.path.resolve().relative_to(_REPO_ROOT.resolve())
            print(f"{rel}:{v.line}:{v.col}: forbidden {v.pattern} (DD-09)", file=sys.stderr)
        return 1
    if unknown:
        # An explicit path that does not exist is a misconfiguration, not a clean
        # pass — fail loud (exit 2) rather than silently reporting OK.
        return 2
    print("dashboard DD-09 gate OK (no data-theme references)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
