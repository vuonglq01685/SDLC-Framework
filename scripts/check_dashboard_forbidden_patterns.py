#!/usr/bin/env python3
"""Forbidden-pattern gate: UX §7.12 v1 absences (Story 5.12 AC1).

Scans dashboard static HTML/CSS/JS for deliberately-absent UX patterns:
modals/dialogs, in-app forms, toasts, client-side routing (``history.pushState``),
and skeleton-loader class hints.

The scan is document-level and quote/comment-aware (Story 5.12 review 2026-07-01,
D1→(a)/P4), mirroring the sibling ``check_dashboard_color_only.py`` idiom:

* JS is scanned after blanking ``//`` / ``/* */`` comments AND ``'..'``/``".."``
  string literals, so a forbidden token merely *mentioned* in a string or a
  trailing comment (exactly what §7.12 invites contributors to write) does not
  false-trip the release-blocking gate. Template/regex literals are intentionally
  left as code so a real ``history.pushState(`` inside a ``${...}`` interpolation
  is still caught (a HARD gate prefers a false positive over a missed router call).
  ``history . pushState`` / ``history\n.pushState`` (whitespace/newline around the
  dot) are caught too.
* HTML element/attribute tokens are matched only inside ``<...>`` tags (text between
  tags is blanked), so ``<td>data-toast</td>`` visible copy is not flagged.
* Inline ``<script>`` / ``<style>`` blocks inside ``.html`` are extracted and run
  through the JS / CSS rules, so a literal ``history.pushState(`` in an inline
  script or a ``.skeleton`` selector in an inline style cannot sneak through.

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
    # `data-toast` attribute (boolean form has no `=`). `(?<![\w-])…(?![\w-])`
    # bounds it to a whole attribute token, so `data-toast-card` / `x-data-toast`
    # class names or hyphenated attrs are NOT false-flagged (P3).
    (re.compile(r"(?<![\w-])data-toast(?![\w-])", re.IGNORECASE), "data-toast attribute"),
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

_JS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Whitespace/newline tolerant around the dot so `history .pushState(` and a
    # method-chain-split `history\n.pushState(` are caught on the blanked document.
    (re.compile(r"history\s*\.\s*pushState\s*\("), "history.pushState (client router)"),
    (re.compile(r"history\s*\.\s*replaceState\s*\("), "history.replaceState (client router)"),
)

_HTML_CLASS_ATTR = re.compile(
    r"""class\s*=\s*(['"])(?P<classes>.*?)\1""",
    re.IGNORECASE | re.DOTALL,
)

# Inline `<script>…</script>` / `<style>…</style>` blocks inside an HTML document.
_INLINE_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script\s*>", re.DOTALL | re.IGNORECASE)
_INLINE_STYLE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.DOTALL | re.IGNORECASE)
_INLINE_BLOCK = re.compile(r"<(script|style)\b.*?</\1\s*>", re.DOTALL | re.IGNORECASE)

# JS comments + `'..'`/`".."` string literals — blanked before matching so a token
# merely mentioned in a string or trailing comment does not false-trip the gate.
# Template and regex literals are deliberately NOT matched (see `_blank_js_noncode`).
_JS_NONCODE = re.compile(
    r"""//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'""",
    re.DOTALL,
)


def _blank_comment(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def _blank_run(text: str) -> str:
    """Blank every non-newline char in ``text`` (preserving line structure)."""
    return re.sub(r"[^\n]", " ", text)


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


def _blank_js_noncode(text: str) -> str:
    """Blank JS ``//``/``/* */`` comments and ``'..'``/``".."`` string literals.

    Length and newlines are preserved (``_blank_comment`` blanks only non-newlines)
    so ``_line_col`` stays accurate. The alternation is scanned left-to-right, so a
    ``//`` inside a string (``"http://x"``) is consumed by the string branch, not
    read as a comment. Template and regex literals are deliberately left as code so a
    real ``history.pushState(`` inside a ``${...}`` interpolation is still flagged —
    a HARD gate prefers a false positive over a missed router call.
    """
    return _JS_NONCODE.sub(_blank_comment, text)


def _mask_to_span(text: str, start: int, end: int) -> str:
    """Return ``text`` with everything outside ``[start, end)`` blanked to spaces.

    Positions inside the window are preserved, so ``_line_col`` on a match within
    the window still yields the correct line/column in the original document.
    """
    return _blank_run(text[:start]) + text[start:end] + _blank_run(text[end:])


def _blank_inline_blocks(text: str) -> str:
    """Blank whole ``<script>``/``<style>`` blocks (their JS/CSS is scanned apart)."""
    return _INLINE_BLOCK.sub(_blank_comment, text)


def _advance_html_scan(ch: str, in_tag: bool, quote: str | None) -> tuple[bool, str | None, bool]:
    """One-char transition for the tag-only scan: ``(in_tag, quote, keep_char)``."""
    if quote is not None:
        return in_tag, (None if ch == quote else quote), True
    if in_tag:
        if ch in ("'", '"'):
            return True, ch, True
        if ch == ">":
            return False, None, True
        return True, None, True
    if ch == "<":
        return True, None, True
    return False, None, False


def _tags_only_view(text: str) -> str:
    """Blank HTML text nodes and whole ``<script>``/``<style>`` blocks.

    What remains are the ``<...>`` tag interiors, so element/attribute patterns
    match only real markup — a forbidden token in visible text (``<td>data-toast``)
    or inside inline JS/CSS (scanned separately) does not false-trip the gate.
    """
    stripped = _blank_inline_blocks(text)
    result = list(stripped)
    in_tag = False
    quote: str | None = None
    for i, ch in enumerate(stripped):
        in_tag, quote, keep = _advance_html_scan(ch, in_tag, quote)
        if not keep and ch != "\n":
            result[i] = " "
    return "".join(result)


def _match_patterns(
    path: Path,
    text: str,
    patterns: tuple[tuple[re.Pattern[str], str], ...],
) -> list[ForbiddenViolation]:
    violations: list[ForbiddenViolation] = []
    for pattern, label in patterns:
        for match in pattern.finditer(text):
            line, col = _line_col(text, match.start())
            violations.append(ForbiddenViolation(path=path, line=line, pattern=label, col=col))
    return violations


def _scan_html_class_skeleton(path: Path, text: str) -> list[ForbiddenViolation]:
    violations: list[ForbiddenViolation] = []
    for match in _HTML_CLASS_ATTR.finditer(text):
        classes = match.group("classes")
        skeleton = _SKELETON_CLASS_RE.search(classes)
        if skeleton is not None:
            # Anchor on the class VALUE start (`match.start("classes")`), not the
            # start of the whole `class="…"` match, so the column names the actual
            # skeleton token (P2 — previously undercounted by len('class="')).
            line, col = _line_col(text, match.start("classes") + skeleton.start())
            violations.append(
                ForbiddenViolation(
                    path=path,
                    line=line,
                    pattern="skeleton-loader CSS class",
                    col=col,
                )
            )
    return violations


def _scan_js_text(path: Path, text: str) -> list[ForbiddenViolation]:
    return _match_patterns(path, _blank_js_noncode(text), _JS_PATTERNS)


def _scan_css_text(path: Path, text: str) -> list[ForbiddenViolation]:
    stripped = _CSS_COMMENT.sub(_blank_comment, text)
    return _match_patterns(path, stripped, _CSS_PATTERNS)


def _scan_html(path: Path, text: str) -> list[ForbiddenViolation]:
    no_comments = _HTML_COMMENT.sub(_blank_comment, text)
    violations: list[ForbiddenViolation] = []
    # Inline <script>/<style> blocks -> JS/CSS rules (positions kept via masking).
    for match in _INLINE_SCRIPT.finditer(no_comments):
        start, end = match.span(1)
        violations.extend(_scan_js_text(path, _mask_to_span(no_comments, start, end)))
    for match in _INLINE_STYLE.finditer(no_comments):
        start, end = match.span(1)
        violations.extend(_scan_css_text(path, _mask_to_span(no_comments, start, end)))
    # Element / attribute tokens + skeleton class on the tag-only view.
    tags_only = _tags_only_view(no_comments)
    violations.extend(_match_patterns(path, tags_only, _HTML_PATTERNS))
    violations.extend(_scan_html_class_skeleton(path, tags_only))
    violations.sort(key=lambda v: (v.line, v.col))
    return violations


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
            violations.extend(_scan_css_text(path, text))
        elif suffix in _JS_SUFFIXES:
            violations.extend(_scan_js_text(path, text))
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
