"""Source-untouched invariant for adopt mode (Story 3.1, AC7; NFR-REL-6).

3.1 scope: the orchestrator writes ONLY under `.claude/`. `assert_path_under_claude`
pre-guards every write target and raises `AdoptError` (ERR_ADOPT, exit 2) on any path
outside `root/.claude/`.

`assert_source_untouched` is the typed public seam (architecture.md:1069). Story 3.7
hardens the `.claude/` sandbox (CR3.1-W2) here; exhaustive `git status --porcelain`
empty + tree-hash equality over the brownfield corpus lives in
``tests/property/test_source_untouched_invariant.py`` (D1=b — no adopt→git grant).
"""

from __future__ import annotations

from pathlib import Path

from sdlc.errors import AdoptError

_CLAUDE_DIR = ".claude"


def _assert_claude_sandbox_intact(root: Path) -> None:
    """Ensure ``root/.claude`` is a real directory confined under ``root`` (CR3.1-W2)."""
    root_resolved = root.resolve()
    claude_entry = root / _CLAUDE_DIR
    if claude_entry.is_symlink():
        raise AdoptError(
            "adopt refuses a symlinked .claude/ sandbox",
            details={"path": str(claude_entry)},
        )
    if not claude_entry.is_dir():
        raise AdoptError(
            "adopt requires .claude/ to be a directory under the repository root",
            details={"path": str(claude_entry)},
        )
    claude_root = claude_entry.resolve()
    expected = root_resolved / _CLAUDE_DIR
    if claude_root != expected:
        raise AdoptError(
            "adopt refuses .claude/ that resolves outside the repository root",
            details={"claude_root": str(claude_root), "root": str(root_resolved)},
        )


def assert_path_under_claude(root: Path, path: Path) -> None:
    """Raise ``AdoptError`` if ``path`` does not resolve under ``root/.claude/`` (AC7).

    Uses resolved absolute paths so a traversal component (``.claude/../src``) cannot
    escape the sandbox. When ``.claude/`` already exists, rejects a symlinked or
    root-escaping sandbox (Story 3.7 / CR3.1-W2). Before init, only the logical
    ``root/.claude/`` prefix is enforced so pre-write guards stay usable.
    """
    root_resolved = root.resolve()
    claude_entry = root / _CLAUDE_DIR
    if claude_entry.exists():
        _assert_claude_sandbox_intact(root)
        claude_root = claude_entry.resolve()
    else:
        claude_root = root_resolved / _CLAUDE_DIR
    candidate = path.resolve()
    if candidate != claude_root and claude_root not in candidate.parents:
        raise AdoptError(
            "adopt refuses to write outside .claude/ (source tree is read-only)",
            details={"path": str(path), "claude_root": str(claude_root)},
        )


def assert_source_untouched(root: Path) -> None:
    """Runtime sandbox integrity check (Story 3.7, D1=b).

    Per-write confinement via ``assert_path_under_claude`` plus a structural guarantee
    that ``.claude/`` is a real directory under ``root``. Porcelain + tree-hash
    verification is enforced by property tests, not production git subprocesses.
    """
    _assert_claude_sandbox_intact(root)
