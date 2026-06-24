#!/usr/bin/env python3
"""Forbidden-pattern gate: no third-party UI framework in dashboard (Story 5.4 AC4 / DD-08).

Fails when a dashboard ``package.json`` declares runtime UI framework dependencies, or when
the dashboard tree contains a vendored UI-framework bundle. Bundle detection is filename-based:
any ``.js``/``.css`` whose name carries a framework token (``react``, ``vue``, ``tailwind`` …)
is flagged, not only ``*.min.js`` (a renamed ``react.min.js`` → ``react.js`` must not slip past).
Chart.js is the only permitted vendored runtime (``chart.js`` / ``chart*.min.js``).

Usage: ``uv run python scripts/check_dashboard_no_framework.py [path ...]``
No args: scans ``src/sdlc/dashboard`` recursively (static tree + any ``package.json`` under the
dashboard, including a dashboard-root ``package.json`` outside ``static/``).
Exit 0 = clean; exit 1 = violations (names the import); exit 2 = explicit path not found.
"""

from __future__ import annotations

import json
import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
# Scan the whole dashboard dir — a dashboard-root package.json (the natural location,
# outside static/) must be covered, not just the shipped static tree (DEC-2).
_DEFAULT_ROOT = _REPO_ROOT / "src" / "sdlc" / "dashboard"

_FORBIDDEN_DEPS = frozenset(
    {
        "react",
        "react-dom",
        "vue",
        "svelte",
        "@sveltejs/kit",
        "angular",
        "@angular/core",
        "lit",
        "lit-element",
        "lit-html",
        "preact",
        "solid-js",
        "@solidjs/router",
        "tailwindcss",
        "@tailwindcss/cli",
        "bootstrap",
        "@mui/material",
        "antd",
    }
)
_BUNDLE_EXTS = frozenset({".js", ".css"})
_FORBIDDEN_BUNDLE_MARKERS = (
    "react",
    "vue",
    "svelte",
    "angular",
    "preact",
    "lit",
    "tailwind",
    "bootstrap",
    "mui",
)
# Match a framework token only at a filename-segment boundary (preceded by start or a
# `.`/`-`/`_` separator, followed by one or end). This catches `react.js`, `vue.global.js`,
# `app-react.min.js`, `tailwind.css` but NOT substrings like `split.js` (`lit`) or
# `reactivity.js` (`react` without a trailing boundary).
_MARKER_RE = re.compile(
    r"(?:^|[._-])(?:" + "|".join(_FORBIDDEN_BUNDLE_MARKERS) + r")(?=[._-]|$)",
    re.IGNORECASE,
)
_PERMITTED_BUNDLE = re.compile(r"chart(?:\.bundle)?(?:\.min)?\.js$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class FrameworkViolation:
    path: Path
    line: int
    pattern: str
    col: int = 1


def _expand_targets(argv: list[str]) -> tuple[list[Path], list[str]]:
    if not argv:
        root = _DEFAULT_ROOT
        if not root.is_dir():
            return [], []
        files = sorted(root.rglob("*"))
        return [p for p in files if p.is_file()], []
    out: list[Path] = []
    unknown: list[str] = []
    for raw in argv:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(p.rglob("*")))
        elif p.is_file():
            out.append(p)
        else:
            unknown.append(raw)
    return sorted({f for f in out if f.is_file()}), unknown


def _dep_line(lines: list[str], name: str) -> int:
    needle = f'"{name}"'
    return next((i for i, ln in enumerate(lines, start=1) if needle in ln), 1)


def scan_package_json(path: Path) -> list[FrameworkViolation]:
    violations: list[FrameworkViolation] = []
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return violations
    deps = data.get("dependencies")
    if not isinstance(deps, dict):
        return violations
    lines = raw.splitlines()
    for name, _version in sorted(deps.items()):
        base = name.split("/")[-1] if name.startswith("@") else name
        if name in _FORBIDDEN_DEPS or base in _FORBIDDEN_DEPS:
            violations.append(
                FrameworkViolation(
                    path=path,
                    line=_dep_line(lines, name),
                    pattern=name,
                )
            )
    return violations


def _bundle_violation_name(path: Path) -> str | None:
    name = path.name
    if path.suffix.lower() not in _BUNDLE_EXTS:
        return None
    if _PERMITTED_BUNDLE.match(name):
        return None
    if _MARKER_RE.search(name):
        return name
    return None


def scan_static_tree(root: Path) -> list[FrameworkViolation]:
    violations: list[FrameworkViolation] = []
    if not root.is_dir():
        return violations
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "package.json":
            violations.extend(scan_package_json(path))
            continue
        label = _bundle_violation_name(path)
        if label is not None:
            violations.append(
                FrameworkViolation(
                    path=path,
                    line=1,
                    pattern=label,
                )
            )
    return violations


def scan_paths(paths: list[Path]) -> list[FrameworkViolation]:
    # Scan each given file once. Directory args are pre-expanded to files by
    # _expand_targets, so we never re-walk a parent tree here (which previously
    # double-counted every violation and re-scanned siblings — PAT-1).
    violations: list[FrameworkViolation] = []
    for path in paths:
        if not path.is_file():
            continue
        if path.name == "package.json":
            violations.extend(scan_package_json(path))
            continue
        label = _bundle_violation_name(path)
        if label is not None:
            violations.append(FrameworkViolation(path=path, line=1, pattern=label))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    targets, unknown = _expand_targets(args)
    for raw in unknown:
        print(
            f"dashboard DD-08 gate: path not found, nothing scanned: {raw}",
            file=sys.stderr,
        )
    violations = scan_paths(targets)
    if violations:
        for v in violations:
            rel = v.path
            with suppress(ValueError):
                rel = v.path.resolve().relative_to(_REPO_ROOT.resolve())
            print(
                f"{rel}:{v.line}:{v.col}: forbidden UI framework dependency {v.pattern} (DD-08)",
                file=sys.stderr,
            )
        return 1
    if unknown:
        return 2
    print("dashboard DD-08 gate OK (no third-party UI framework)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
