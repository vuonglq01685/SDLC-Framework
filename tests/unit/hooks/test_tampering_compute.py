"""Task 1.1 — unit tests for compute_hook_hashes (TDD-first, RED phase)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from sdlc.errors import HookError
from sdlc.hooks.tampering import compute_hook_hashes

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "hooks" / "trees"

_SKIP_WIN32 = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only symlink test")


@pytest.mark.unit
class TestComputeHookHashesMissingRoot:
    def test_missing_hooks_root_raises_hook_error(self, tmp_path: Path) -> None:
        absent = tmp_path / "no_such_dir"
        with pytest.raises(HookError, match="hooks_root not found"):
            compute_hook_hashes(absent)

    def test_error_details_contain_path(self, tmp_path: Path) -> None:
        absent = tmp_path / "no_such_dir"
        with pytest.raises(HookError) as exc_info:
            compute_hook_hashes(absent)
        assert "path" in exc_info.value.details


@pytest.mark.unit
class TestComputeHookHashesEmpty:
    def test_empty_tree_returns_empty_dict(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "empty")
        assert result == {}


@pytest.mark.unit
class TestComputeHookHashesSingle:
    def test_single_file_key_is_posix_relpath(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "single")
        assert list(result.keys()) == ["hook_a.py"]

    def test_single_file_value_matches_sha256(self) -> None:
        hooks_root = _FIXTURES / "single"
        result = compute_hook_hashes(hooks_root)
        raw = (hooks_root / "hook_a.py").read_bytes()
        expected = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        assert result["hook_a.py"] == expected

    def test_value_format_sha256_prefix(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "single")
        for v in result.values():
            assert v.startswith("sha256:")
            assert len(v) == len("sha256:") + 64


@pytest.mark.unit
class TestComputeHookHashesMulti:
    def test_multi_file_keys_sorted_lexicographically(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "multi")
        keys = list(result.keys())
        assert keys == sorted(keys)

    def test_multi_file_subdirectory_key_uses_posix_separator(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "multi")
        assert "subdir/cc.py" in result

    def test_multi_file_count(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "multi")
        assert len(result) == 3

    def test_multi_file_values_are_unique_sha256(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "multi")
        values = list(result.values())
        assert len(values) == len(set(values))


@pytest.mark.unit
class TestComputeHookHashesNonPy:
    def test_non_py_files_are_silently_ignored(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "with_non_py")
        assert "README.md" not in result

    def test_py_file_is_included(self) -> None:
        result = compute_hook_hashes(_FIXTURES / "with_non_py")
        assert "hook_a.py" in result


@pytest.mark.unit
@_SKIP_WIN32
class TestComputeHookHashesSymlinks:
    def test_symlink_inside_tree_is_followed(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        real = hooks / "real.py"
        real.write_bytes(b"# real\n")
        link = hooks / "link.py"
        link.symlink_to(real)
        result = compute_hook_hashes(hooks)
        assert "link.py" in result
        assert "real.py" in result
        assert result["link.py"] == result["real.py"]

    def test_symlink_escape_raises_hook_error(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        outside = tmp_path / "outside.py"
        outside.write_bytes(b"# outside\n")
        link = hooks / "escape.py"
        link.symlink_to(outside)
        with pytest.raises(HookError, match="hook escapes hooks_root"):
            compute_hook_hashes(hooks)

    def test_symlink_escape_error_contains_relpath(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        outside = tmp_path / "outside.py"
        outside.write_bytes(b"# outside\n")
        link = hooks / "escape.py"
        link.symlink_to(outside)
        with pytest.raises(HookError) as exc_info:
            compute_hook_hashes(hooks)
        assert "escape.py" in str(exc_info.value)

    def test_posix_relpath_semantics_on_subdirs(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        (hooks / "sub").mkdir(parents=True)
        (hooks / "sub" / "a.py").write_bytes(b"# a\n")
        result = compute_hook_hashes(hooks)
        assert "sub/a.py" in result
        for key in result:
            assert "\\" not in key
