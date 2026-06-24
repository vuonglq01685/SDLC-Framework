#!/usr/bin/env python3
"""Forbidden-pattern gate: dashboard CSS motion budget (Story 5.4 AC2 / DD-14).

Scans ``src/sdlc/dashboard/static/**`` CSS for prototype transitions/animations.
Only ``@keyframes pulse`` and ``animation`` declarations referencing
``var(--motion-pulse-live)`` / ``var(--motion-pulse-stop)`` (or ``animation: none``)
are permitted.

Usage: ``uv run python scripts/check_dashboard_motion.py [path ...]``
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

_SCAN_GLOBS = ("*.css",)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_TRANSITION = re.compile(r"\btransition\s*:", re.IGNORECASE)
_KEYFRAMES = re.compile(r"@keyframes\s+([-\w]+)", re.IGNORECASE)
_ANIMATION = re.compile(r"\banimation\s*:", re.IGNORECASE)
_PULSE_VARS = ("var(--motion-pulse-live)", "var(--motion-pulse-stop)")
_ALLOWED_KEYFRAME = "pulse"


def _blank_comment(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


@dataclass(frozen=True, slots=True)
class MotionViolation:
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


def _animation_allowed(line: str) -> bool:
    lowered = line.lower()
    if "animation: none" in lowered or "animation:none" in lowered:
        return True
    return any(token in line for token in _PULSE_VARS)


def _scan_css(path: Path, text: str) -> list[MotionViolation]:
    violations: list[MotionViolation] = []
    stripped = _CSS_COMMENT.sub(_blank_comment, text)
    for lineno, line in enumerate(stripped.splitlines(), start=1):
        transition_match = _TRANSITION.search(line)
        if transition_match is not None:
            violations.append(
                MotionViolation(
                    path=path,
                    line=lineno,
                    pattern="transition:",
                    col=transition_match.start() + 1,
                )
            )
            continue
        for keyframes_match in _KEYFRAMES.finditer(line):
            name = keyframes_match.group(1)
            if name != _ALLOWED_KEYFRAME:
                violations.append(
                    MotionViolation(
                        path=path,
                        line=lineno,
                        pattern=f"@keyframes {name}",
                        col=keyframes_match.start() + 1,
                    )
                )
        animation_match = _ANIMATION.search(line)
        if animation_match is not None and not _animation_allowed(line):
            violations.append(
                MotionViolation(
                    path=path,
                    line=lineno,
                    pattern="animation:",
                    col=animation_match.start() + 1,
                )
            )
    return violations


def scan_paths(paths: list[Path]) -> list[MotionViolation]:
    violations: list[MotionViolation] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".css":
            violations.extend(_scan_css(path, text))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    targets, unknown = _expand_targets(args)
    for raw in unknown:
        print(
            f"dashboard DD-14 gate: path not found, nothing scanned: {raw}",
            file=sys.stderr,
        )
    violations = scan_paths(targets)
    if violations:
        for v in violations:
            rel = v.path
            with suppress(ValueError):
                rel = v.path.resolve().relative_to(_REPO_ROOT.resolve())
            print(f"{rel}:{v.line}:{v.col}: forbidden {v.pattern} (DD-14)", file=sys.stderr)
        return 1
    if unknown:
        return 2
    print("dashboard DD-14 gate OK (pulse-only motion budget)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
