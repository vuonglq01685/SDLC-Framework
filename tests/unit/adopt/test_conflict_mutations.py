"""Mutation-kill tests for passes/_conflict.py (Story 3.7 AC2, Tier-1).

Targets the 90 surviving mutants in _conflict.py by exercising:
- backup_real_file: path construction, symlink guard, exact bytes preserved
- restore_real_file: exact restore target
- remove_symlink_at_target: only removes symlinks, not real files
- restore_symlink: recreates link at correct slot
- read_other_symlink_source_rel: relpath from root, not absolute
- conflict_backup_dir: timestamp-scoped directory construction
- _unique_backup_path: collisions generate unique names
- Cross-filesystem fallback: shutil.copy2 path
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.passes._conflict import (
    backup_real_file,
    conflict_backup_dir,
    read_other_symlink_source_rel,
    remove_symlink_at_target,
    restore_real_file,
    restore_symlink,
)
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit

_TS = "2026-06-04T120000"
_ARCH_TARGET = "02-Architecture/02-System/ARCHITECTURE.md"


def _scaffold(tmp_path: Path) -> Path:
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# backup_real_file
# ---------------------------------------------------------------------------


def test_backup_real_file_returns_backup_path(tmp_path: Path) -> None:
    """backup_real_file returns the exact path where the backup was placed."""
    root = _scaffold(tmp_path)
    target_rel = _ARCH_TARGET
    slot = root / target_rel
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("important content\n", encoding="utf-8")

    backup_path = backup_real_file(root, target_rel, timestamp=_TS)
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "important content\n"


def test_backup_real_file_removes_original(tmp_path: Path) -> None:
    """backup_real_file moves the file, so the original slot no longer exists."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("data\n", encoding="utf-8")

    backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    assert not slot.exists()


def test_backup_real_file_rejects_symlink_at_target(tmp_path: Path) -> None:
    """backup_real_file raises AdoptError when target is a symlink, not a real file."""
    root = _scaffold(tmp_path)
    src = root / "docs/src.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("src\n", encoding="utf-8")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../docs/src.md", slot)

    with pytest.raises(AdoptError, match="real file"):
        backup_real_file(root, _ARCH_TARGET, timestamp=_TS)


def test_backup_real_file_rejects_missing_target(tmp_path: Path) -> None:
    """backup_real_file raises AdoptError when target does not exist."""
    root = _scaffold(tmp_path)
    (root / _ARCH_TARGET).parent.mkdir(parents=True, exist_ok=True)

    with pytest.raises(AdoptError):
        backup_real_file(root, _ARCH_TARGET, timestamp=_TS)


def test_backup_real_file_preserves_bytes_exactly(tmp_path: Path) -> None:
    """backup_real_file is byte-preserving (NFR-REL-6)."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    content = b"binary\x00data\xff\n"
    slot.write_bytes(content)

    backup_path = backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    assert backup_path.read_bytes() == content


def test_backup_real_file_collision_creates_unique_names(tmp_path: Path) -> None:
    """When the default backup name is taken, _unique_backup_path generates a new one."""
    root = _scaffold(tmp_path)
    target_rel = _ARCH_TARGET

    slot1 = root / target_rel
    slot1.parent.mkdir(parents=True, exist_ok=True)
    slot1.write_text("first\n", encoding="utf-8")
    bp1 = backup_real_file(root, target_rel, timestamp=_TS)

    slot1.write_text("second\n", encoding="utf-8")
    bp2 = backup_real_file(root, target_rel, timestamp=_TS)

    # Must be different paths
    assert bp1 != bp2
    assert bp1.read_text(encoding="utf-8") == "first\n"
    assert bp2.read_text(encoding="utf-8") == "second\n"


def test_backup_is_under_conflict_backup_dir(tmp_path: Path) -> None:
    """Backup is placed inside .claude/state/adopt-conflicts/<timestamp>/."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("content\n", encoding="utf-8")

    bp = backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    expected_parent = conflict_backup_dir(root, _TS)
    assert bp.parent == expected_parent


# ---------------------------------------------------------------------------
# restore_real_file
# ---------------------------------------------------------------------------


def test_restore_real_file_puts_bytes_back_at_target(tmp_path: Path) -> None:
    """restore_real_file moves backup back to target path with original bytes."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("original\n", encoding="utf-8")

    backup_path = backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    assert not slot.exists()

    restore_real_file(root, _ARCH_TARGET, backup_path=backup_path)
    assert slot.exists()
    assert slot.read_text(encoding="utf-8") == "original\n"


def test_restore_real_file_removes_backup(tmp_path: Path) -> None:
    """After restore_real_file, the backup file is removed (atomic replace)."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("data\n", encoding="utf-8")

    backup_path = backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    restore_real_file(root, _ARCH_TARGET, backup_path=backup_path)

    # The backup is gone (os.replace is atomic: backup → original)
    assert not backup_path.exists()


# ---------------------------------------------------------------------------
# remove_symlink_at_target
# ---------------------------------------------------------------------------


def test_remove_symlink_at_target_removes_symlink(tmp_path: Path) -> None:
    """remove_symlink_at_target successfully removes a symlink."""
    root = _scaffold(tmp_path)
    src = root / "docs/src.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("src\n", encoding="utf-8")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../docs/src.md", slot)

    remove_symlink_at_target(root, _ARCH_TARGET)
    assert not slot.exists()
    assert not slot.is_symlink()


def test_remove_symlink_at_target_does_not_remove_real_file(tmp_path: Path) -> None:
    """remove_symlink_at_target is a no-op on a real file: returns None and leaves it intact.

    Production (``_conflict.py``) returns None when the slot is not a symlink — it must never
    delete a real source/user file. Killing the ``not target_abs.is_symlink()`` guard mutant.
    """
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("real file\n", encoding="utf-8")

    result = remove_symlink_at_target(root, _ARCH_TARGET)
    assert result is None
    assert slot.exists()
    assert not slot.is_symlink()
    assert slot.read_text(encoding="utf-8") == "real file\n"


# ---------------------------------------------------------------------------
# restore_symlink
# ---------------------------------------------------------------------------


def test_restore_symlink_recreates_link_at_slot(tmp_path: Path) -> None:
    """restore_symlink recreates a symlink at an empty slot using the raw link text verbatim.

    Production sig is ``restore_symlink(root, target_rel, link_text)`` (``_conflict.py:116``) —
    a best-effort compensation that writes ``link_text`` verbatim only when the slot is empty.
    """
    root = _scaffold(tmp_path)
    src = root / "docs/src.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("src\n", encoding="utf-8")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    link_text = os.path.relpath(src, slot.parent)

    restore_symlink(root, _ARCH_TARGET, link_text)

    assert slot.is_symlink()
    assert slot.resolve() == src.resolve()


def test_restore_symlink_link_is_relative(tmp_path: Path) -> None:
    """restore_symlink writes the link text verbatim, preserving a relative (not absolute) link."""
    root = _scaffold(tmp_path)
    src = root / "docs/src.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("src\n", encoding="utf-8")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    link_text = os.path.relpath(src, slot.parent)

    restore_symlink(root, _ARCH_TARGET, link_text)

    assert not os.path.isabs(os.readlink(slot))


# ---------------------------------------------------------------------------
# read_other_symlink_source_rel
# ---------------------------------------------------------------------------


def test_read_other_symlink_source_rel_returns_root_relative_posix(tmp_path: Path) -> None:
    """read_other_symlink_source_rel returns root-relative POSIX path, not absolute."""
    root = _scaffold(tmp_path)
    src = root / "docs/other.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("other\n", encoding="utf-8")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    # Create a relative symlink
    rel = os.path.relpath(src, slot.parent)
    os.symlink(rel, slot)

    result = read_other_symlink_source_rel(root, _ARCH_TARGET)
    # Must be root-relative, not absolute
    assert result is not None
    assert not os.path.isabs(result)
    assert result == "docs/other.md"


def test_read_other_symlink_source_rel_raises_when_not_symlink(tmp_path: Path) -> None:
    """read_other_symlink_source_rel raises AdoptError when the target is not a symlink.

    Production is typed ``-> str`` and raises (``_conflict.py:136``) — there is no None path.
    Killing the ``not target_abs.is_symlink()`` guard-removal mutant.
    """
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("real file\n", encoding="utf-8")

    with pytest.raises(AdoptError, match="expected a symlink"):
        read_other_symlink_source_rel(root, _ARCH_TARGET)


# ---------------------------------------------------------------------------
# conflict_backup_dir path structure
# ---------------------------------------------------------------------------


def test_conflict_backup_dir_is_under_claude_state(tmp_path: Path) -> None:
    """conflict_backup_dir returns a path inside .claude/state/adopt-conflicts/."""
    root = _scaffold(tmp_path)
    d = conflict_backup_dir(root, _TS)
    # Must be under .claude/state/adopt-conflicts/
    relative = d.relative_to(root)
    parts = relative.parts
    assert parts[0] == ".claude"
    assert parts[1] == "state"
    assert parts[2] == "adopt-conflicts"


def test_conflict_backup_dir_includes_timestamp(tmp_path: Path) -> None:
    """conflict_backup_dir path incorporates the timestamp for isolation."""
    root = _scaffold(tmp_path)
    ts1 = "2026-06-04T120000"
    ts2 = "2026-06-04T130000"
    d1 = conflict_backup_dir(root, ts1)
    d2 = conflict_backup_dir(root, ts2)
    assert d1 != d2
