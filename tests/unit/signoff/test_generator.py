"""Unit tests for signoff/generator.py — generate_signoff_md (AC1, AC3, AC9, Story 2A.12)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_PHASE1_DIR = "01-Requirement"
_PHASE2_DIR = "02-Architecture"


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_artifact(repo_root: Path, rel_path: str, content: bytes = b"test content") -> Path:
    p = repo_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_generate_signoff_md_happy_path(tmp_path: Path) -> None:
    """AC1/AC3: generate SIGNOFF.md with 2 artifacts; assert fenced block + correct hashes."""
    from sdlc.signoff.generator import generate_signoff_md

    art1_content = b"product brief content"
    art2_content = b"epic content"
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md", art1_content)
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/04-Epics/EPIC-foo.json", art2_content)

    result_path, artifact_count = generate_signoff_md(1, repo_root=tmp_path)

    assert result_path == tmp_path / _PHASE1_DIR / "SIGNOFF.md"
    assert result_path.exists()
    assert artifact_count == 2  # P10: tuple return — count matches the two artifacts

    text = result_path.read_text(encoding="utf-8")

    # Fenced block present
    assert "```signoff" in text
    assert "```" in text

    # Parse the fenced block
    import re

    fence_pattern = re.compile(r"```signoff\s*\n(.*?)```", re.DOTALL)
    m = fence_pattern.search(text)
    assert m is not None, "No fenced signoff block found"
    data = yaml.safe_load(m.group(1))

    assert data["phase"] == 1
    assert data["approved"] is False
    assert data["approved_by"] is None
    assert data["approved_at"] is None
    assert "drafted_at" in data

    # Artifacts in block with correct hashes
    paths_in_block = {a["path"] for a in data["artifacts"]}
    assert f"{_PHASE1_DIR}/01-PRODUCT.md" in paths_in_block
    assert f"{_PHASE1_DIR}/04-Epics/EPIC-foo.json" in paths_in_block

    hash_map = {a["path"]: a["hash"] for a in data["artifacts"]}
    assert hash_map[f"{_PHASE1_DIR}/01-PRODUCT.md"] == _sha256(art1_content)
    assert hash_map[f"{_PHASE1_DIR}/04-Epics/EPIC-foo.json"] == _sha256(art2_content)

    # Markdown table also present
    assert "| Path | Origin | SHA-256 |" in text


def test_generate_signoff_md_returns_path(tmp_path: Path) -> None:
    """AC9: generate_signoff_md returns the SIGNOFF.md path."""
    from sdlc.signoff.generator import generate_signoff_md

    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md")

    result_path, artifact_count = generate_signoff_md(1, repo_root=tmp_path)
    assert isinstance(result_path, Path)
    assert result_path.name == "SIGNOFF.md"
    assert result_path.parent == tmp_path / _PHASE1_DIR
    assert artifact_count == 1


# ---------------------------------------------------------------------------
# SIGNOFF.md excluded from artifact list
# ---------------------------------------------------------------------------


def test_signoff_md_excluded_from_artifacts(tmp_path: Path) -> None:
    """AC3: SIGNOFF.md itself must NOT appear in the artifact listing."""
    from sdlc.signoff.generator import generate_signoff_md

    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md")

    # First call writes SIGNOFF.md; second call must exclude it
    generate_signoff_md(1, repo_root=tmp_path)
    result_path, _ = generate_signoff_md(1, repo_root=tmp_path)

    text = result_path.read_text(encoding="utf-8")
    assert "SIGNOFF.md" not in text.split("```signoff")[1].split("```")[0]


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


def test_deterministic_ordering(tmp_path: Path) -> None:
    """AC3: artifacts sorted lexicographically by POSIX path (byte-stable output)."""
    from sdlc.signoff.generator import generate_signoff_md

    _write_artifact(tmp_path, f"{_PHASE1_DIR}/z-last.md", b"zzz")
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/a-first.md", b"aaa")
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/m-middle.md", b"mmm")

    result, _ = generate_signoff_md(1, repo_root=tmp_path)
    text = result.read_text(encoding="utf-8")

    import re

    fence_pattern = re.compile(r"```signoff\s*\n(.*?)```", re.DOTALL)
    m = fence_pattern.search(text)
    assert m is not None
    data = yaml.safe_load(m.group(1))

    paths = [a["path"] for a in data["artifacts"]]
    assert paths == sorted(paths), f"Artifacts not sorted: {paths}"


def test_two_calls_same_content_identical_output(tmp_path: Path) -> None:
    """AC3: two calls with same content produce byte-identical output (excluding timestamps)."""
    from sdlc.signoff.generator import generate_signoff_md

    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md", b"stable content")

    path1, count1 = generate_signoff_md(1, repo_root=tmp_path)
    text1 = path1.read_text(encoding="utf-8")

    path2, count2 = generate_signoff_md(1, repo_root=tmp_path)
    text2 = path2.read_text(encoding="utf-8")
    assert count1 == count2 == 1

    import re

    # Artifact paths and hashes must be identical between calls
    fence_pattern = re.compile(r"```signoff\s*\n(.*?)```", re.DOTALL)
    data1 = yaml.safe_load(fence_pattern.search(text1).group(1))  # type: ignore[union-attr]
    data2 = yaml.safe_load(fence_pattern.search(text2).group(1))  # type: ignore[union-attr]

    assert data1["phase"] == data2["phase"]
    assert data1["approved"] == data2["approved"]
    assert [a["path"] for a in data1["artifacts"]] == [a["path"] for a in data2["artifacts"]]
    assert [a["hash"] for a in data1["artifacts"]] == [a["hash"] for a in data2["artifacts"]]


# ---------------------------------------------------------------------------
# Empty directory → ERR_NO_ARTIFACTS
# ---------------------------------------------------------------------------


def test_empty_directory_raises_no_artifacts(tmp_path: Path) -> None:
    """AC3: empty phase dir → SignoffError with ERR_NO_ARTIFACTS message."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.generator import generate_signoff_md

    phase_dir = tmp_path / _PHASE1_DIR
    phase_dir.mkdir(parents=True)

    with pytest.raises(SignoffError) as exc_info:
        generate_signoff_md(1, repo_root=tmp_path)

    assert (
        "ERR_NO_ARTIFACTS" in str(exc_info.value)
        or "no artifacts found" in str(exc_info.value).lower()
    )


def test_missing_phase_dir_raises_no_artifacts(tmp_path: Path) -> None:
    """AC3: missing phase directory → SignoffError (no artifacts)."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.generator import generate_signoff_md

    with pytest.raises(SignoffError):
        generate_signoff_md(1, repo_root=tmp_path)


# ---------------------------------------------------------------------------
# Phase 2 coverage
# ---------------------------------------------------------------------------


def test_generate_phase2(tmp_path: Path) -> None:
    """AC2: phase=2 generates SIGNOFF.md under 02-Architecture/."""
    from sdlc.signoff.generator import generate_signoff_md

    _write_artifact(tmp_path, f"{_PHASE2_DIR}/arch.md", b"arch content")

    result, artifact_count = generate_signoff_md(2, repo_root=tmp_path)

    assert result == tmp_path / _PHASE2_DIR / "SIGNOFF.md"
    assert result.exists()
    assert artifact_count == 1

    import re

    text = result.read_text(encoding="utf-8")
    fence_pattern = re.compile(r"```signoff\s*\n(.*?)```", re.DOTALL)
    m = fence_pattern.search(text)
    assert m is not None
    data = yaml.safe_load(m.group(1))
    assert data["phase"] == 2
    assert any(a["path"].startswith(_PHASE2_DIR) for a in data["artifacts"])


# ---------------------------------------------------------------------------
# Readable by read_signoff_md_draft
# ---------------------------------------------------------------------------


def test_output_parseable_by_reader(tmp_path: Path) -> None:
    """AC3/AC9: generated SIGNOFF.md is parseable by records.read_signoff_md_draft."""
    from sdlc.signoff.generator import generate_signoff_md
    from sdlc.signoff.records import read_signoff_md_draft

    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md", b"product")
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/04-Epics/EPIC-x.json", b"epic")

    result, _ = generate_signoff_md(1, repo_root=tmp_path)
    draft = read_signoff_md_draft(result)

    assert draft.phase == 1
    assert draft.approved is False
    assert draft.approved_by is None
    assert len(draft.artifacts) == 2
    assert draft.drafted_at is not None


def test_adopted_symlink_included_with_imported_origin(tmp_path: Path) -> None:
    """AC5: known-adopted leaf symlinks are hashed and marked imported."""
    import os

    from sdlc.signoff.generator import generate_signoff_md

    src = tmp_path / "legacy" / "arch.md"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"imported body")
    target_rel = f"{_PHASE2_DIR}/02-System/ARCHITECTURE.md"
    target = tmp_path / target_rel
    target.parent.mkdir(parents=True)
    os.symlink(os.path.relpath(src, target.parent), target)

    adopted = {target_rel: "legacy/arch.md"}
    result_path, count = generate_signoff_md(2, repo_root=tmp_path, adopted_sources=adopted)
    assert count == 1
    text = result_path.read_text(encoding="utf-8")
    assert "imported" in text
    assert _sha256(b"imported body") in text


def test_non_adopted_symlink_still_skipped(tmp_path: Path) -> None:
    """Security: an UNRELATED symlink stays excluded even when OTHER targets ARE adopted.

    P10: the dangerous case is a populated allowlist with one legit adopted entry while an
    unrelated `EVIL.md` symlink is present — the membership check must not leak it through.
    """
    import os

    from sdlc.signoff.generator import generate_signoff_md

    # A legitimately-adopted symlink (recorded in the manifest map).
    legit_src = tmp_path / "legacy" / "arch.md"
    legit_src.parent.mkdir(parents=True)
    legit_src.write_bytes(b"legit body")
    legit_rel = f"{_PHASE2_DIR}/02-System/ARCHITECTURE.md"
    legit_target = tmp_path / legit_rel
    legit_target.parent.mkdir(parents=True)
    os.symlink(os.path.relpath(legit_src, legit_target.parent), legit_target)

    # An UNRELATED symlink NOT in the adopted map → must stay skipped.
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"x")
    evil_rel = f"{_PHASE2_DIR}/02-System/EVIL.md"
    evil_target = tmp_path / evil_rel
    os.symlink(os.path.relpath(outside, evil_target.parent), evil_target)

    # A plain native file.
    (tmp_path / _PHASE2_DIR / "01-NATIVE.md").write_bytes(b"native")

    result_path, count = generate_signoff_md(
        2, repo_root=tmp_path, adopted_sources={legit_rel: "legacy/arch.md"}
    )
    text = result_path.read_text(encoding="utf-8")
    assert count == 2  # native + adopted; EVIL excluded
    assert "01-NATIVE.md" in text
    assert "ARCHITECTURE.md" in text
    assert "EVIL.md" not in text
