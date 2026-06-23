"""ETag helpers for dashboard read routes (wraps signoff hashing — Decision D2)."""

from __future__ import annotations

from pathlib import Path

from sdlc.signoff.hasher import compute_artifact_hash


def compute_etag(path: Path, *, repo_root: Path) -> str:
    """Return ``sha256:<hex>`` ETag for ``path``, or ``''`` when the file is missing."""
    return compute_artifact_hash(path, repo_root=repo_root)
