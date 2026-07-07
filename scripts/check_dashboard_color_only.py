#!/usr/bin/env python3
"""Forbidden-pattern gate: color-only live-dot signaling (Story 5.5 AC2 / UX §7.4).

Scans committed dashboard HTML for ``<live-dot>`` elements without an adjacent
text-label sibling (color-only signaling is forbidden — a live dot must always be
paired with text such as "LIVE" / "WARN" / "DISCONNECTED").

The scanner is document-level and quote-aware (Story 5.5 review PATCH-3): it finds
the real end of each ``<live-dot>`` opening tag even when the tag spans multiple
lines or carries a ``>`` inside an attribute value, and it looks for the adjacent
label across line boundaries (so a label on the next line is NOT a false positive).

Usage: ``uv run python scripts/check_dashboard_color_only.py [path ...]``
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

_SCAN_GLOBS = ("*.html",)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_LIVE_DOT_TAG = re.compile(r"<live-dot\b", re.IGNORECASE)
_LIVE_DOT_CLOSE = "</live-dot>"
_STOP_BANNER_TAG = re.compile(r"\bstop-banner\s+alert\b", re.IGNORECASE)
_SEVERITY_TAG = re.compile(r"\b(?:CRITICAL|WARNING|INFO):")
# How far past a <live-dot> tag to look for its adjacent label sibling/child.
_LOOKAHEAD = 400
_LABEL_CLASS = re.compile(
    r"""class\s*=\s*['"][^'"]*\b(?:live-dot-label|live-dot__label)\b[^'"]*['"]""",
    re.IGNORECASE,
)
_TEXT_LABEL_TAGS = frozenset(
    {"span", "abbr", "label", "small", "strong", "em", "b", "i", "p", "div"}
)


def _blank_comment(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


@dataclass(frozen=True, slots=True)
class ColorOnlyViolation:
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


def _find_tag_end(text: str, start: int) -> int:
    """Return the index just past the opening tag's ``>``.

    Skips any ``>`` that appears inside a single- or double-quoted attribute value
    (so ``<live-dot data-x="a>b">`` resolves to the final ``>``). Returns ``-1`` if
    the tag is never closed.
    """
    quote: str | None = None
    for i in range(start, len(text)):
        char = text[i]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == ">":
            return i + 1
    return -1


def _line_col(text: str, idx: int) -> tuple[int, int]:
    """1-based (line, column) of ``idx`` within ``text``."""
    line = text.count("\n", 0, idx) + 1
    col = idx - text.rfind("\n", 0, idx)
    return line, col


def _tag_name_after_lt(fragment: str) -> str | None:
    match = re.match(r"<\s*([a-zA-Z][\w-]*)", fragment)
    return match.group(1).lower() if match else None


def _element_has_text(fragment: str) -> bool:
    """A leading element is a label only if it is a text tag with non-empty content."""
    tag = _tag_name_after_lt(fragment)
    if tag not in _TEXT_LABEL_TAGS:
        return False
    open_end = fragment.find(">")
    if open_end == -1:
        return False
    close = fragment.find("</", open_end)
    inner = fragment[open_end + 1 : close] if close != -1 else ""
    return bool(inner.strip())


def _label_present(after: str) -> bool:
    """Whether an adjacent text label follows a ``<live-dot>`` opening tag.

    ``after`` is the document text immediately after the tag's closing ``>`` (HTML
    comments are already blanked to spaces, so they read as whitespace). The search
    crosses line boundaries within a bounded window and skips the element's own
    empty ``</live-dot>`` close so a sibling label is seen.
    """
    window = after[:_LOOKAHEAD]
    if _LABEL_CLASS.search(window):
        return True
    rest = window.lstrip()
    if rest[: len(_LIVE_DOT_CLOSE)].lower() == _LIVE_DOT_CLOSE:
        rest = rest[len(_LIVE_DOT_CLOSE) :].lstrip()
    if not rest:
        return False
    if not rest.startswith("<"):
        return bool(rest.strip())
    return _element_has_text(rest)


def _scan_stop_banners(path: Path, text: str) -> list[ColorOnlyViolation]:
    """STOP banners must carry a text severity tag — never color-only (Story 5.19).

    The severity tag lives in the banner's own title (a child of the
    ``.stop-banner.alert`` element), so the search is scoped FORWARD from each
    banner's class match up to the NEXT banner (or end of document). A flat
    ±character window would let a neighbouring banner's tag mask a genuinely
    color-only one (review 2026-07-07 P2).
    """
    violations: list[ColorOnlyViolation] = []
    stripped = _HTML_COMMENT.sub(_blank_comment, text)
    matches = list(_STOP_BANNER_TAG.finditer(stripped))
    for i, match in enumerate(matches):
        start = match.start()
        line, col = _line_col(stripped, start)
        window_end = matches[i + 1].start() if i + 1 < len(matches) else len(stripped)
        window = stripped[start:window_end]
        if not _SEVERITY_TAG.search(window):
            violations.append(
                ColorOnlyViolation(
                    path=path,
                    line=line,
                    pattern=".stop-banner without text severity tag (CRITICAL:/WARNING:/INFO:)",
                    col=col,
                )
            )
    return violations


def _scan_html(path: Path, text: str) -> list[ColorOnlyViolation]:
    violations: list[ColorOnlyViolation] = []
    stripped = _HTML_COMMENT.sub(_blank_comment, text)
    for match in _LIVE_DOT_TAG.finditer(stripped):
        start = match.start()
        line, col = _line_col(stripped, start)
        tag_end = _find_tag_end(stripped, start)
        if tag_end == -1:
            # Unterminated opening tag -> cannot pair a label -> fail closed.
            violations.append(
                ColorOnlyViolation(
                    path=path,
                    line=line,
                    pattern="<live-dot> opening tag not terminated",
                    col=col,
                )
            )
            continue
        if _LABEL_CLASS.search(stripped[start:tag_end]):
            # Label class carried on the element itself.
            continue
        if _label_present(stripped[tag_end:]):
            continue
        violations.append(
            ColorOnlyViolation(
                path=path,
                line=line,
                pattern="<live-dot> without adjacent text label",
                col=col,
            )
        )
    violations.extend(_scan_stop_banners(path, text))
    return violations


def scan_paths(paths: list[Path]) -> list[ColorOnlyViolation]:
    violations: list[ColorOnlyViolation] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".html":
            violations.extend(_scan_html(path, text))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    targets, unknown = _expand_targets(args)
    for raw in unknown:
        print(
            f"dashboard color-only gate: path not found, nothing scanned: {raw}",
            file=sys.stderr,
        )
    violations = scan_paths(targets)
    if violations:
        for v in violations:
            rel = v.path
            with suppress(ValueError):
                rel = v.path.resolve().relative_to(_REPO_ROOT.resolve())
            print(
                f"{rel}:{v.line}:{v.col}: {v.pattern} (UX §7.4 color-only)",
                file=sys.stderr,
            )
        return 1
    if unknown:
        return 2
    print("dashboard color-only gate OK (live-dot paired with text label)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
