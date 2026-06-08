"""Mutation-kill tests for the small adopt modules (Story 3.7 AC2, Tier-1).

Consolidated coverage for the residual survivors in:
- adopt/__init__.py        — the lazy ``__getattr__`` re-export shim
- adopt/invariant.py       — the dangling-``.claude``-symlink guard branch
- adopt/source_tree.py     — the ``.claude`` source-tree exclusion
- adopt/tree_hash.py       — fingerprint fields, glob forwarding, join separator
- adopt/passes/_frontmatter.py — the multi-line frontmatter block join
- adopt/passes/detection.py    — skip-then-continue loop control

Equivalent mutants intentionally NOT targeted: encoding "utf-8"/"UTF-8" aliases,
``followlinks=None`` (falsy ≡ False), ``_safe_read_text`` ""→"XXXX" (both classify
as "unknown"), and the unreachable ``_assert_claude_sandbox_intact`` root-escape
envelope (``claude_root != expected`` cannot hold for a real non-symlink ``.claude``,
since ``resolve()`` normalizes both sides identically).
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt is POSIX-only in v1", allow_module_level=True)

import sdlc.adopt as adopt_pkg
from sdlc.adopt.invariant import assert_path_under_claude
from sdlc.adopt.passes import detection
from sdlc.adopt.passes._frontmatter import read_lenient_frontmatter
from sdlc.adopt.source_tree import is_source_path
from sdlc.adopt.tree_hash import (
    _entry_fingerprint,
    compute_source_tree_hash,
    iter_source_relpaths,
)
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# adopt/__init__.py __getattr__ lazy re-exports
# ---------------------------------------------------------------------------


def test_getattr_lazy_exports_are_the_real_functions() -> None:
    """Each lazy export resolves to the exact underlying function (kills == → != / XX / UPPER)."""
    from sdlc.adopt.driver import run_adopt
    from sdlc.adopt.invariant import assert_source_untouched
    from sdlc.adopt.passes.detection import detect_existing
    from sdlc.adopt.passes.stamp import mark_imported
    from sdlc.adopt.passes.symlink_offer import offer_symlinks

    assert adopt_pkg.assert_source_untouched is assert_source_untouched
    assert adopt_pkg.detect_existing is detect_existing
    assert adopt_pkg.mark_imported is mark_imported
    assert adopt_pkg.offer_symlinks is offer_symlinks
    assert adopt_pkg.run_adopt is run_adopt


def test_getattr_unknown_attribute_raises_descriptive() -> None:
    """An unknown attribute raises AttributeError naming the attr (kills AttributeError(None))."""
    with pytest.raises(AttributeError) as ei:
        _ = adopt_pkg.totally_bogus_name
    message = str(ei.value)
    assert "has no attribute" in message
    assert "totally_bogus_name" in message


# ---------------------------------------------------------------------------
# adopt/invariant.py — dangling .claude symlink guard
# ---------------------------------------------------------------------------


def test_assert_path_under_claude_rejects_dangling_claude_symlink(tmp_path: Path) -> None:
    """A dangling ``.claude`` symlink is rejected as a symlinked sandbox (kills `or` → `and`)."""
    root = tmp_path
    os.symlink(
        root / "nonexistent-target", root / ".claude"
    )  # dangling: is_symlink True, exists False
    with pytest.raises(AdoptError) as ei:
        assert_path_under_claude(root, root / ".claude" / "state" / "x.json")
    # `exists()` alone would miss the dangling link; the `or is_symlink()` reaches the sandbox
    # integrity check, which rejects with this exact message (not the generic write-outside one).
    assert ei.value.message == "adopt refuses a symlinked .claude/ sandbox"


# ---------------------------------------------------------------------------
# adopt/source_tree.py — .claude exclusion
# ---------------------------------------------------------------------------


def test_is_source_path_claude_exclusion() -> None:
    """`.claude` (exact + prefix) is excluded even against catch-all globs."""
    assert is_source_path("src/main.py", ()) is True
    assert is_source_path(".claude", ("**",)) is False  # kills "XX.claudeXX" / ".CLAUDE"
    assert is_source_path(".claude/x.py", ("**/*.py",)) is False  # kills `or` → `and`


# ---------------------------------------------------------------------------
# adopt/tree_hash.py — fingerprint fields, glob forwarding, join separator
# ---------------------------------------------------------------------------


def test_entry_fingerprint_file_includes_mode_and_digest(tmp_path: Path) -> None:
    """A file fingerprint is exactly ``rel|file|<mode>|<sha256>`` (kills mode mutations)."""
    root = tmp_path
    (root / "f.py").write_text("hello\n", encoding="utf-8")
    mode = oct((root / "f.py").lstat().st_mode & 0o777777)
    digest = hashlib.sha256(b"hello\n").hexdigest()
    assert _entry_fingerprint(root, "f.py") == f"f.py|file|{mode}|{digest}"


def test_entry_fingerprint_symlink_includes_target(tmp_path: Path) -> None:
    """A symlink fingerprint is exactly ``rel|symlink|<mode>|<target>`` (kills target → None)."""
    root = tmp_path
    (root / "real.py").write_text("x\n", encoding="utf-8")
    os.symlink("real.py", root / "lnk")
    mode = oct((root / "lnk").lstat().st_mode & 0o777777)
    assert _entry_fingerprint(root, "lnk") == f"lnk|symlink|{mode}|real.py"


def test_iter_source_relpaths_forwards_legacy_globs(tmp_path: Path) -> None:
    """legacy_code_globs widen the source set (kills the dropped-arg mutant)."""
    root = tmp_path
    (root / "weird.xyz").write_text("x\n", encoding="utf-8")
    assert iter_source_relpaths(root, legacy_code_globs=("*.xyz",)) == ["weird.xyz"]
    assert iter_source_relpaths(root) == []  # not a default source path


def test_compute_hash_forwards_legacy_globs(tmp_path: Path) -> None:
    """compute_source_tree_hash threads legacy_code_globs into iteration (kills dropped-arg)."""
    root = tmp_path
    (root / "weird.xyz").write_text("x\n", encoding="utf-8")
    assert compute_source_tree_hash(root, legacy_code_globs=("*.xyz",)) != compute_source_tree_hash(
        root
    )


def test_compute_hash_does_not_follow_dir_symlinks(tmp_path: Path) -> None:
    """os.walk(followlinks=False): a symlinked dir's contents are not traversed (kills =True)."""
    root = tmp_path
    (root / "src" / "real").mkdir(parents=True)
    (root / "src" / "real" / "x.py").write_text("x=1\n", encoding="utf-8")
    os.symlink(root / "src" / "real", root / "src" / "link")
    relpaths = iter_source_relpaths(root)
    assert "src/real/x.py" in relpaths
    assert "src/link/x.py" not in relpaths


def test_compute_hash_joins_fingerprints_with_newline(tmp_path: Path) -> None:
    """The tree-hash payload joins fingerprints with '\\n' (kills the XX-wrapped separator)."""
    root = tmp_path
    (root / "a.py").write_text("aaa\n", encoding="utf-8")
    (root / "b.py").write_text("bbb\n", encoding="utf-8")
    relpaths = iter_source_relpaths(root)  # sorted: a.py, b.py
    payload = "\n".join(_entry_fingerprint(root, r) for r in relpaths).encode("utf-8")
    assert compute_source_tree_hash(root) == hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# adopt/passes/_frontmatter.py — multi-line block join
# ---------------------------------------------------------------------------


def test_read_lenient_frontmatter_multiline_block(tmp_path: Path) -> None:
    """A multi-line frontmatter block is joined with '\\n' so it parses as YAML (kills XX-join)."""
    path = tmp_path / "f.md"
    path.write_text("---\ntitle: T\ntags:\n  - a\n  - b\n---\nbody\n", encoding="utf-8")
    assert read_lenient_frontmatter(path) == {"title": "T", "tags": ["a", "b"]}


# ---------------------------------------------------------------------------
# adopt/passes/detection.py — skip-then-continue loop control
# ---------------------------------------------------------------------------


def _walk_with_first(name: str) -> object:
    """An os.walk wrapper that yields ``name`` before the other filenames (deterministic order)."""
    real_walk = os.walk

    def _walk(*args: object, **kwargs: object) -> object:
        for dirpath, dirnames, filenames in real_walk(*args, **kwargs):  # type: ignore[arg-type]
            yield dirpath, dirnames, sorted(filenames, key=lambda n: (n != name, n))

    return _walk


def test_detect_existing_symlink_skip_uses_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skipping a symlink candidate continues the loop (a later real artifact is still detected)."""
    root = tmp_path
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    os.symlink(root / "Dockerfile", root / "link.md")  # a symlink, skipped at the loop head
    monkeypatch.setattr(os, "walk", _walk_with_first("link.md"))  # symlink iterated first
    results = detection.detect_existing(root)
    assert any(r.path == "Dockerfile" for r in results)


def test_detect_existing_legacy_glob_skip_uses_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skipping a legacy-glob match continues the loop (a later real artifact is still detected)."""
    root = tmp_path
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (root / "excluded.py").write_text("x = 1\n", encoding="utf-8")  # matches the *.py legacy glob
    monkeypatch.setattr(os, "walk", _walk_with_first("excluded.py"))  # excluded file iterated first
    results = detection.detect_existing(root, legacy_code_globs=("*.py",))
    assert any(r.path == "Dockerfile" for r in results)
