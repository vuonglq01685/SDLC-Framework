"""Mutation-kill tests for passes/_symlink.py (Story 3.7 AC2, Tier-1).

Targets the 38 surviving mutants in _symlink.py by exercising:
- create_relative_symlink: exact SymlinkOutcome return values
  * SOURCE_MISSING when source absent
  * ALREADY_CORRECT when symlink already resolves to right source
  * CONFLICT_REAL_FILE when a real file occupies the slot
  * CONFLICT_OTHER_SYMLINK when a different symlink occupies the slot
  * CREATED when symlink is newly created
- is_target_under_root: boundary cases (root itself, escape, nested)
- assert_target_under_root: raises AdoptError for escaping paths
- resolve_target: trailing-slash → file-relative name appended
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.passes._symlink import (
    SymlinkOutcome,
    assert_target_under_root,
    create_relative_symlink,
    is_target_under_root,
    resolve_target,
)
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit

_SOURCE_REL = "docs/architecture-2024.md"
_TARGET_REL = "02-Architecture/02-System/ARCHITECTURE.md"


def _scaffold(tmp_path: Path) -> Path:
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    return tmp_path


def _write_source(root: Path, rel: str = _SOURCE_REL) -> Path:
    src = root / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(f"# {rel}\n", encoding="utf-8")
    return src


# ---------------------------------------------------------------------------
# create_relative_symlink → CREATED
# ---------------------------------------------------------------------------


def test_create_relative_symlink_returns_created(tmp_path: Path) -> None:
    """Returns CREATED when symlink is newly made."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    (root / _TARGET_REL).parent.mkdir(parents=True, exist_ok=True)

    outcome = create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)
    assert outcome is SymlinkOutcome.CREATED


def test_create_relative_symlink_creates_file(tmp_path: Path) -> None:
    """After CREATED, the target slot is a symlink resolving to the source."""
    root = _scaffold(tmp_path)
    src = _write_source(root, _SOURCE_REL)
    (root / _TARGET_REL).parent.mkdir(parents=True, exist_ok=True)

    create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)

    slot = root / _TARGET_REL
    assert slot.is_symlink()
    assert slot.resolve() == src.resolve()


def test_create_relative_symlink_link_is_relative(tmp_path: Path) -> None:
    """Symlink created by create_relative_symlink is relative, not absolute."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    (root / _TARGET_REL).parent.mkdir(parents=True, exist_ok=True)

    create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)

    link = os.readlink(root / _TARGET_REL)
    assert not os.path.isabs(link)


# ---------------------------------------------------------------------------
# create_relative_symlink → SOURCE_MISSING
# ---------------------------------------------------------------------------


def test_create_returns_source_missing_when_no_source(tmp_path: Path) -> None:
    """Returns SOURCE_MISSING when the source file does not exist."""
    root = _scaffold(tmp_path)
    (root / _TARGET_REL).parent.mkdir(parents=True, exist_ok=True)

    outcome = create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)
    assert outcome is SymlinkOutcome.SOURCE_MISSING


# ---------------------------------------------------------------------------
# create_relative_symlink → ALREADY_CORRECT
# ---------------------------------------------------------------------------


def test_create_returns_already_correct_when_symlink_matches(tmp_path: Path) -> None:
    """Returns ALREADY_CORRECT when the slot already has a correct adopt symlink."""
    root = _scaffold(tmp_path)
    src = _write_source(root, _SOURCE_REL)
    slot = root / _TARGET_REL
    slot.parent.mkdir(parents=True, exist_ok=True)
    rel = os.path.relpath(src, slot.parent)
    os.symlink(rel, slot)

    outcome = create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)
    assert outcome is SymlinkOutcome.ALREADY_CORRECT


def test_create_does_not_modify_existing_correct_symlink(tmp_path: Path) -> None:
    """ALREADY_CORRECT: no filesystem change, symlink still points to same source."""
    root = _scaffold(tmp_path)
    src = _write_source(root, _SOURCE_REL)
    slot = root / _TARGET_REL
    slot.parent.mkdir(parents=True, exist_ok=True)
    rel = os.path.relpath(src, slot.parent)
    os.symlink(rel, slot)
    original_link = os.readlink(slot)

    create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)

    assert os.readlink(slot) == original_link


# ---------------------------------------------------------------------------
# create_relative_symlink → CONFLICT_REAL_FILE
# ---------------------------------------------------------------------------


def test_create_returns_conflict_real_file(tmp_path: Path) -> None:
    """Returns CONFLICT_REAL_FILE when a real file occupies the target slot."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    slot = root / _TARGET_REL
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("existing real file\n", encoding="utf-8")

    outcome = create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)
    assert outcome is SymlinkOutcome.CONFLICT_REAL_FILE


def test_create_does_not_overwrite_real_file(tmp_path: Path) -> None:
    """CONFLICT_REAL_FILE: the existing real file is left untouched."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    slot = root / _TARGET_REL
    slot.parent.mkdir(parents=True, exist_ok=True)
    content = "must not be modified\n"
    slot.write_text(content, encoding="utf-8")

    create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)

    assert slot.read_text(encoding="utf-8") == content
    assert not slot.is_symlink()


# ---------------------------------------------------------------------------
# create_relative_symlink → CONFLICT_OTHER_SYMLINK
# ---------------------------------------------------------------------------


def test_create_returns_conflict_other_symlink(tmp_path: Path) -> None:
    """Returns CONFLICT_OTHER_SYMLINK when a different symlink occupies the slot."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    other_src = root / "other/file.md"
    other_src.parent.mkdir(parents=True, exist_ok=True)
    other_src.write_text("# other\n", encoding="utf-8")
    slot = root / _TARGET_REL
    slot.parent.mkdir(parents=True, exist_ok=True)
    rel = os.path.relpath(other_src, slot.parent)
    os.symlink(rel, slot)

    outcome = create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)
    assert outcome is SymlinkOutcome.CONFLICT_OTHER_SYMLINK


def test_create_does_not_overwrite_other_symlink(tmp_path: Path) -> None:
    """CONFLICT_OTHER_SYMLINK: the existing symlink target is preserved."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    other_src = root / "other/file.md"
    other_src.parent.mkdir(parents=True, exist_ok=True)
    other_src.write_text("# other\n", encoding="utf-8")
    slot = root / _TARGET_REL
    slot.parent.mkdir(parents=True, exist_ok=True)
    rel = os.path.relpath(other_src, slot.parent)
    os.symlink(rel, slot)
    original_link = os.readlink(slot)

    create_relative_symlink(root, _SOURCE_REL, _TARGET_REL)

    assert os.readlink(slot) == original_link


# ---------------------------------------------------------------------------
# All SymlinkOutcome variants are distinct
# ---------------------------------------------------------------------------


def test_symlink_outcomes_are_distinct(  ) -> None:
    """Each SymlinkOutcome enum value is different from the others."""
    outcomes = [
        SymlinkOutcome.CREATED,
        SymlinkOutcome.ALREADY_CORRECT,
        SymlinkOutcome.CONFLICT_REAL_FILE,
        SymlinkOutcome.CONFLICT_OTHER_SYMLINK,
        SymlinkOutcome.SOURCE_MISSING,
    ]
    assert len(set(outcomes)) == len(outcomes)


# ---------------------------------------------------------------------------
# is_target_under_root
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target, expected", [
    ("02-Architecture/ARCHITECTURE.md", True),
    ("docs/arch.md", True),
    (".claude/state/file.json", True),
    ("../escape.md", False),
    ("../../deeply/escape.md", False),
    ("/absolute/path.md", False),
])
def test_is_target_under_root(tmp_path: Path, target: str, expected: bool) -> None:
    root = _scaffold(tmp_path)
    assert is_target_under_root(root, target) is expected


def test_is_target_under_root_empty_string(tmp_path: Path) -> None:
    """Empty string target resolves to root itself — which IS under root."""
    root = _scaffold(tmp_path)
    # root / "" resolves to root; root is a prefix of itself → True
    assert is_target_under_root(root, "") is True


# ---------------------------------------------------------------------------
# assert_target_under_root
# ---------------------------------------------------------------------------


def test_assert_target_under_root_ok_for_nested(tmp_path: Path) -> None:
    """assert_target_under_root does not raise for a valid nested path."""
    root = _scaffold(tmp_path)
    assert_target_under_root(root, "docs/nested/file.md")  # must not raise


def test_assert_target_under_root_raises_for_escape(tmp_path: Path) -> None:
    """assert_target_under_root raises AdoptError for a path escaping the root."""
    root = _scaffold(tmp_path)
    with pytest.raises(AdoptError):
        assert_target_under_root(root, "../escape.md")


# ---------------------------------------------------------------------------
# resolve_target
# ---------------------------------------------------------------------------


def test_resolve_target_no_trailing_slash_returns_as_is(  ) -> None:
    """resolve_target with no trailing slash returns the target unchanged."""
    result = resolve_target("02-Architecture/ARCHITECTURE.md", "docs/arch.md")
    assert result == "02-Architecture/ARCHITECTURE.md"


def test_resolve_target_trailing_slash_appends_filename(  ) -> None:
    """resolve_target with trailing slash appends the source filename."""
    result = resolve_target("01-Requirement/02-Research/", "docs/research-2024.md")
    assert result == "01-Requirement/02-Research/research-2024.md"


def test_resolve_target_trailing_slash_uses_basename_only(  ) -> None:
    """Trailing-slash target appends only the basename, not the full source path."""
    result = resolve_target("docs/dest/", "some/deep/path/filename.md")
    assert result == "docs/dest/filename.md"
    assert "/" not in result.replace("docs/dest/", "")
