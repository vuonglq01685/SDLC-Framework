"""Unit tests for signoff/hasher.py — compute_artifact_hash (AC4, Story 2A.7)."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# compute_artifact_hash
# ---------------------------------------------------------------------------


def test_hash_small_file(tmp_path: Path) -> None:
    """Happy path: small file returns sha256:<hex> string."""
    from sdlc.signoff.hasher import compute_artifact_hash

    f = tmp_path / "artifact.md"
    f.write_bytes(b"hello world")
    result = compute_artifact_hash(f, repo_root=tmp_path)
    expected_hex = hashlib.sha256(b"hello world").hexdigest()
    assert result == f"sha256:{expected_hex}"


def test_hash_empty_file(tmp_path: Path) -> None:
    """Empty file hashes to sha256 of empty input (e3b0c44...)."""
    from sdlc.signoff.hasher import compute_artifact_hash

    f = tmp_path / "empty.md"
    f.write_bytes(b"")
    result = compute_artifact_hash(f, repo_root=tmp_path)
    empty_hex = hashlib.sha256(b"").hexdigest()
    assert result == f"sha256:{empty_hex}"
    assert result == "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_hash_large_file_streams_correctly(tmp_path: Path) -> None:
    """Large file (>1MB) is streamed; result matches direct hash."""
    from sdlc.signoff.hasher import compute_artifact_hash

    data = os.urandom(2 * 1024 * 1024)  # 2MB
    f = tmp_path / "large.bin"
    f.write_bytes(data)
    result = compute_artifact_hash(f, repo_root=tmp_path)
    expected_hex = hashlib.sha256(data).hexdigest()
    assert result == f"sha256:{expected_hex}"


def test_hash_missing_file_returns_sentinel(tmp_path: Path) -> None:
    """Missing file returns sentinel '' (callers MUST handle)."""
    from sdlc.signoff.hasher import compute_artifact_hash

    result = compute_artifact_hash(tmp_path / "nonexistent.md", repo_root=tmp_path)
    assert result == ""


def test_hash_permission_denied_raises(tmp_path: Path) -> None:
    """Permission denied on readable raises SignoffError."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.hasher import compute_artifact_hash

    if sys.platform == "win32":
        pytest.skip("chmod-based permission test is POSIX-only")

    f = tmp_path / "locked.md"
    f.write_bytes(b"data")
    f.chmod(0o000)
    try:
        with pytest.raises(SignoffError):
            compute_artifact_hash(f, repo_root=tmp_path)
    finally:
        f.chmod(0o644)


def test_hash_symlink_inside_repo_follows(tmp_path: Path) -> None:
    """Symlink whose target is inside repo root is followed."""
    from sdlc.signoff.hasher import compute_artifact_hash

    if sys.platform == "win32":
        pytest.skip("symlink test is POSIX-only")

    target = tmp_path / "real.md"
    target.write_bytes(b"real content")
    link = tmp_path / "link.md"
    link.symlink_to(target)

    result = compute_artifact_hash(link, repo_root=tmp_path)
    expected_hex = hashlib.sha256(b"real content").hexdigest()
    assert result == f"sha256:{expected_hex}"


def test_hash_symlink_escape_raises(tmp_path: Path) -> None:
    """Symlink pointing outside repo_root raises SignoffError."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.hasher import compute_artifact_hash

    if sys.platform == "win32":
        pytest.skip("symlink test is POSIX-only")

    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"escaped")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    link = repo_root / "escape.md"
    link.symlink_to(outside)

    with pytest.raises(SignoffError, match="artifact symlink escapes repo"):
        compute_artifact_hash(link, repo_root=repo_root)


def test_hash_format_matches_contract_regex(tmp_path: Path) -> None:
    """Output matches ^sha256:[0-9a-f]{64}$ contract regex."""
    import re

    from sdlc.signoff.hasher import compute_artifact_hash

    f = tmp_path / "f.md"
    f.write_bytes(b"test")
    result = compute_artifact_hash(f, repo_root=tmp_path)
    assert re.fullmatch(r"^sha256:[0-9a-f]{64}$", result)


def test_hash_raw_bytes_no_normalization(tmp_path: Path) -> None:
    """Hashing is byte-exact — CRLF and LF produce different hashes."""
    from sdlc.signoff.hasher import compute_artifact_hash

    lf = tmp_path / "lf.md"
    lf.write_bytes(b"line\n")
    crlf = tmp_path / "crlf.md"
    crlf.write_bytes(b"line\r\n")

    assert compute_artifact_hash(lf, repo_root=tmp_path) != compute_artifact_hash(
        crlf, repo_root=tmp_path
    )
