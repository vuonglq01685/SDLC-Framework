"""Source-untouched invariant for adopt mode (Story 3.1, AC7; NFR-REL-6).

3.1 scope: the orchestrator writes ONLY under `.claude/`. `assert_path_under_claude`
pre-guards every write target and raises `AdoptError` (ERR_ADOPT, exit 2) on any path
outside `root/.claude/`.

`assert_source_untouched` is the typed public seam (architecture.md:1069). Story 3.7
hardens it into the exhaustive `git status --porcelain` empty + tree-hash equality property
(architecture.md:194,223 — "diff misses mtime, mode, xattr, symlink target") over a 5+
fixture corpus with mutation testing. Running git porcelain here would require a
module-boundary-table grant for git that does not exist yet (Story 3.7), so 3.1 keeps the
confinement guarantee enforced per-write via `assert_path_under_claude` instead.
"""

from __future__ import annotations

from pathlib import Path

from sdlc.errors import AdoptError

_CLAUDE_DIR = ".claude"


def assert_path_under_claude(root: Path, path: Path) -> None:
    """Raise ``AdoptError`` if ``path`` does not resolve under ``root/.claude/`` (AC7).

    Uses resolved absolute paths so a traversal component (``.claude/../src``) cannot
    escape the sandbox.
    """
    claude_root = (root / _CLAUDE_DIR).resolve()
    candidate = path.resolve()
    if candidate != claude_root and claude_root not in candidate.parents:
        raise AdoptError(
            "adopt refuses to write outside .claude/ (source tree is read-only)",
            details={"path": str(path), "claude_root": str(claude_root)},
        )


def assert_source_untouched(root: Path) -> None:
    """Story 3.7 seam — porcelain + tree-hash source-untouched property (architecture.md:1069).

    3.1: the orchestrator confines every write to ``.claude/`` (each pre-guarded by
    `assert_path_under_claude`), so the source tree is untouched by construction. Story 3.7
    replaces this with the exhaustive `git status --porcelain` + tree-hash invariant; here it
    is the typed entry point that freezes the public name for 3.2-3.7.
    """
    return None
