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
import shutil
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.passes._conflict import (
    _unique_backup_path,
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


# ---------------------------------------------------------------------------
# _unique_backup_path — collision counter
# ---------------------------------------------------------------------------


def test_unique_backup_path_first_collision_uses_dot1(tmp_path: Path) -> None:
    """First collision yields `<name>.1.bak` (kills counter-start 1->2)."""
    backup_dir = tmp_path
    (backup_dir / "report.md.bak").write_text("x", encoding="utf-8")
    result = _unique_backup_path(backup_dir, "report.md")
    assert result.name == "report.md.1.bak"


def test_unique_backup_path_second_collision_uses_dot2(tmp_path: Path) -> None:
    """Two collisions yield `<name>.2.bak` (kills counter no-increment / -=1 / +=2;
    the no-increment mutant infinite-loops and dies by timeout)."""
    backup_dir = tmp_path
    (backup_dir / "report.md.bak").write_text("x", encoding="utf-8")
    (backup_dir / "report.md.1.bak").write_text("y", encoding="utf-8")
    result = _unique_backup_path(backup_dir, "report.md")
    assert result.name == "report.md.2.bak"


# ---------------------------------------------------------------------------
# backup_real_file — guards, naming, cross-fs fallback, error envelopes
# ---------------------------------------------------------------------------


def test_backup_real_file_rejects_symlink_target_exact(tmp_path: Path) -> None:
    """A symlink (not a real file) at the target raises with exact message + details."""
    root = _scaffold(tmp_path)
    src = root / "docs/src.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("s\n", encoding="utf-8")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../docs/src.md", slot)
    with pytest.raises(AdoptError) as ei:
        backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    assert ei.value.message == "adopt conflict backup requires a real file at the target"
    assert ei.value.details == {"target": _ARCH_TARGET}


def test_backup_real_file_backup_name_uses_target_basename(tmp_path: Path) -> None:
    """The backup file is named `<target-basename>.bak` (kills name-arg -> None)."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("data\n", encoding="utf-8")
    backup_path = backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    assert backup_path.name == "ARCHITECTURE.md.bak"


def test_backup_real_file_cross_fs_fallback_preserves_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When os.replace fails (cross-fs), backup falls back to copy2 + unlink, preserving bytes."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("precious\n", encoding="utf-8")

    def _raise_replace(*_a: object, **_k: object) -> None:
        raise OSError("cross-device link")

    monkeypatch.setattr(os, "replace", _raise_replace)
    backup_path = backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    assert backup_path.read_text(encoding="utf-8") == "precious\n"
    assert not slot.exists()


def test_backup_real_file_oserror_wrapped_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When both replace and copy2 fail, the OSError is wrapped with exact message + cause."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("data\n", encoding="utf-8")

    def _raise(*_a: object, **_k: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(os, "replace", _raise)
    monkeypatch.setattr(shutil, "copy2", _raise)
    with pytest.raises(AdoptError) as ei:
        backup_real_file(root, _ARCH_TARGET, timestamp=_TS)
    assert ei.value.message == "adopt could not back up the conflicting real file"
    assert ei.value.details["target"] == _ARCH_TARGET
    assert ei.value.details["cause"] == "boom"


# ---------------------------------------------------------------------------
# restore_real_file — occupied-slot guard, cross-fs fallback, both-fail
# ---------------------------------------------------------------------------


def test_restore_real_file_does_not_clobber_occupied_slot(tmp_path: Path) -> None:
    """A slot already holding a real file is NOT clobbered (kills `or`->`and` + return True)."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("LIVE\n", encoding="utf-8")
    backup = tmp_path / "old.bak"
    backup.write_text("STALE\n", encoding="utf-8")
    result = restore_real_file(root, _ARCH_TARGET, backup)
    assert result is False
    assert slot.read_text(encoding="utf-8") == "LIVE\n"


def test_restore_real_file_cross_fs_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When os.replace fails, restore falls back to copy2 + unlink and returns True."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)  # parent exists, slot empty
    backup = tmp_path / "old.bak"
    backup.write_text("RESTORED\n", encoding="utf-8")

    def _raise_replace(*_a: object, **_k: object) -> None:
        raise OSError("cross-device link")

    monkeypatch.setattr(os, "replace", _raise_replace)
    result = restore_real_file(root, _ARCH_TARGET, backup)
    assert result is True
    assert slot.read_text(encoding="utf-8") == "RESTORED\n"


def test_restore_real_file_returns_false_when_both_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When replace and copy2 both fail, restore returns False (bytes survive in backup)."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    backup = tmp_path / "old.bak"
    backup.write_text("x\n", encoding="utf-8")

    def _raise(*_a: object, **_k: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(os, "replace", _raise)
    monkeypatch.setattr(shutil, "copy2", _raise)
    assert restore_real_file(root, _ARCH_TARGET, backup) is False


# ---------------------------------------------------------------------------
# remove_symlink_at_target — OSError envelope
# ---------------------------------------------------------------------------


def test_remove_symlink_oserror_wrapped_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OSError while removing the symlink is wrapped with exact message + cause."""
    root = _scaffold(tmp_path)
    src = root / "docs/src.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("s\n", encoding="utf-8")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../docs/src.md", slot)

    def _raise_unlink(*_a: object, **_k: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(os, "unlink", _raise_unlink)
    with pytest.raises(AdoptError) as ei:
        remove_symlink_at_target(root, _ARCH_TARGET)
    assert ei.value.message == "adopt could not remove the conflicting symlink at the target"
    assert ei.value.details["target"] == _ARCH_TARGET
    assert ei.value.details["cause"] == "boom"


# ---------------------------------------------------------------------------
# restore_symlink — creates missing parent dirs
# ---------------------------------------------------------------------------


def test_restore_symlink_creates_missing_parent_dirs(tmp_path: Path) -> None:
    """restore_symlink mkdir(parents=True) creates the slot's missing parent chain
    (kills parents=True -> None/False and the dropped-kwarg mutant)."""
    root = _scaffold(tmp_path)
    target_rel = "deep/newly/made/dirs/file.md"
    # parent chain deep/newly/made/dirs does NOT exist yet
    restore_symlink(root, target_rel, "../../../../some/source.md")
    slot = root / target_rel
    assert slot.is_symlink()
    assert os.readlink(slot) == "../../../../some/source.md"


# ---------------------------------------------------------------------------
# read_other_symlink_source_rel — error envelopes + in-root predicate
# ---------------------------------------------------------------------------


def test_read_other_non_symlink_raises_exact(tmp_path: Path) -> None:
    """A non-symlink target raises with exact message + details."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("real\n", encoding="utf-8")
    with pytest.raises(AdoptError) as ei:
        read_other_symlink_source_rel(root, _ARCH_TARGET)
    assert ei.value.message == "adopt expected a symlink at the target for conflict resolution"
    assert ei.value.details == {"target": _ARCH_TARGET}


def test_read_other_readlink_oserror_wrapped_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OSError while reading the existing symlink is wrapped with exact message + cause.

    `is_target_under_root` resolves the slot first (one readlink of the symlink); the function's
    OWN `os.readlink` is the second. The patch lets the guard's resolve succeed, then raises.
    """
    root = _scaffold(tmp_path)
    src = root / "docs/other.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("o\n", encoding="utf-8")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../docs/other.md", slot)

    real_readlink = os.readlink
    state = {"seen_slot": False}

    def _maybe_raise(path: object, *a: object, **k: object) -> str:
        if str(path).endswith("ARCHITECTURE.md"):
            if state["seen_slot"]:
                raise OSError("boom")
            state["seen_slot"] = True
        return real_readlink(path, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "readlink", _maybe_raise)
    with pytest.raises(AdoptError) as ei:
        read_other_symlink_source_rel(root, _ARCH_TARGET)
    assert ei.value.message == "adopt could not read an existing symlink at the target"
    assert ei.value.details["target"] == _ARCH_TARGET
    assert ei.value.details["cause"] == "boom"


def test_read_other_symlink_pointing_at_root_returns_dot(tmp_path: Path) -> None:
    """A symlink resolving to the root itself returns relpath '.' (kills the `==`->`!=`
    flip on the in-root predicate, which would instead leak the raw '../..' link text)."""
    root = _scaffold(tmp_path)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    rel_to_root = os.path.relpath(root, slot.parent)  # e.g. "../.."
    os.symlink(rel_to_root, slot)
    assert read_other_symlink_source_rel(root, _ARCH_TARGET) == "."
