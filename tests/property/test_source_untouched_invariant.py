"""Property gate: NFR-REL-6 source-untouched across brownfield corpus (Story 3.7, AC1)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

if sys.platform == "win32":  # pragma: no cover - adopt is POSIX-only (ADR-034)
    pytest.skip("adopt is POSIX-only in v1 (ADR-034)", allow_module_level=True)

from adopt._source_untouched_helpers import (
    CORPUS_FIXTURES,
    AdoptInvocationMode,
    assert_source_tree_unchanged,
    copy_fixture,
    init_git_repo,
    run_adopt_for_mode,
    seed_preexisting_symlinks,
    snapshot_source_bytes,
)
from sdlc.adopt.source_tree import DEFAULT_SOURCE_TREE_GLOBS, effective_source_globs, is_source_path
from sdlc.adopt.tree_hash import compute_source_tree_hash

pytestmark = pytest.mark.property

_MODES = list(AdoptInvocationMode)
_MIN_FIXTURE_MODE_PAIRS = [(name, mode) for name in CORPUS_FIXTURES for mode in _MODES]


@pytest.mark.parametrize(("fixture_name", "mode"), _MIN_FIXTURE_MODE_PAIRS)
def test_source_untouched_per_fixture_and_mode(
    fixture_name: str,
    mode: AdoptInvocationMode,
    tmp_path: Path,
) -> None:
    root = copy_fixture(fixture_name, tmp_path)
    if fixture_name == "preexisting-symlinks":
        seed_preexisting_symlinks(root)
    init_git_repo(root)
    legacy: tuple[str, ...] = ()
    before_hash = compute_source_tree_hash(root, legacy_code_globs=legacy)
    before_bytes = snapshot_source_bytes(root, legacy_code_globs=legacy)
    run_adopt_for_mode(root, mode)
    assert_source_tree_unchanged(
        root,
        before_hash=before_hash,
        before_bytes=before_bytes,
        legacy_code_globs=legacy,
    )


@given(extra_byte=st.binary(min_size=1, max_size=64))
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
    ],
)
def test_source_bytes_stable_under_content_fuzz(
    extra_byte: bytes,
    tmp_path: Path,
) -> None:
    """Fuzz one source file in python-pyproject; tree hash + bytes must stay stable after adopt."""
    root = copy_fixture("python-pyproject", tmp_path)
    init_git_repo(root)
    target = root / "docs" / "requirements.md"
    assert target.exists(), (
        "fuzz target docs/requirements.md missing from the python-pyproject fixture — "
        "without it this property would pass vacuously, fuzzing nothing"
    )
    target.write_bytes(target.read_bytes() + extra_byte)
    git = shutil.which("git")
    if git:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "fuzz"],
            cwd=root,
            check=True,
            capture_output=True,
        )
    legacy: tuple[str, ...] = ()
    before_hash = compute_source_tree_hash(root, legacy_code_globs=legacy)
    before_bytes = snapshot_source_bytes(root, legacy_code_globs=legacy)
    run_adopt_for_mode(root, AdoptInvocationMode.NON_INTERACTIVE_AUTO)
    assert_source_tree_unchanged(
        root,
        before_hash=before_hash,
        before_bytes=before_bytes,
        legacy_code_globs=legacy,
    )


def test_default_source_tree_globs_exclude_claude() -> None:
    assert not is_source_path(".claude/state/adopt-report.json")
    assert not is_source_path(".claude/journal/agent_runs.jsonl")
    assert is_source_path("src/main.py")
    assert is_source_path("README.md")
    union = effective_source_globs(("vendor/**",))
    assert "vendor/**" in union
    assert DEFAULT_SOURCE_TREE_GLOBS[0] == "src/**"
