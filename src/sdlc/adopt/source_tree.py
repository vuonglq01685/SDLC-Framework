"""Source-tree glob definitions for NFR-REL-6 (Story 3.7, AC3).

Default globs cover common application source layouts; users extend via
``legacy_code_globs`` in ``project.yaml``. Matching reuses the segment-aware
``**`` engine from ``adopt.passes._classify`` (D3).
"""

from __future__ import annotations

from typing import Final

from sdlc.adopt.passes import _classify

# Union of epics AC3 defaults — not source: ``.claude/**`` (filtered explicitly).
DEFAULT_SOURCE_TREE_GLOBS: Final[tuple[str, ...]] = (
    "src/**",
    "lib/**",
    "app/**",
    "packages/**",
    "*.java",
    "*.py",
    "*.go",
    "*.rs",
    "*.ts",
    "*.js",
    "pom.xml",
    "pyproject.toml",
    "go.mod",
    "package.json",
    "README.md",
    "docs/**",
)

_CLAUDE_PREFIX = ".claude/"


def is_source_path(rel_posix: str, legacy_code_globs: tuple[str, ...] = ()) -> bool:
    """True when ``rel_posix`` is a configured source-tree path (AC3)."""
    if rel_posix == ".claude" or rel_posix.startswith(_CLAUDE_PREFIX):
        return False
    globs = DEFAULT_SOURCE_TREE_GLOBS + legacy_code_globs
    return _classify.matches_legacy_glob(rel_posix, globs)


def effective_source_globs(legacy_code_globs: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Default source-tree globs unioned with user ``legacy_code_globs``."""
    return DEFAULT_SOURCE_TREE_GLOBS + legacy_code_globs
