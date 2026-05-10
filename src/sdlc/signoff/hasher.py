"""Signoff artifact hashing helpers (AC4, Story 2A.7).

Boundary: pure sync I/O — no asyncio, no imports from engine/dispatcher/cli.
Pattern §3 equivalence: yaml.safe_dump(sort_keys=True, default_flow_style=False,
allow_unicode=True) is the YAML analogue of JSON canonicalization (sorted keys,
deterministic serialization, UTF-8). Used for compute_signoff_record_hash.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from sdlc.errors import SignoffError

_CHUNK_SIZE = 64 * 1024  # 64 KiB streaming chunks (cold-start friendliness per §488-§494)


def compute_artifact_hash(path: Path, *, repo_root: Path | None = None) -> str:
    """Return ``sha256:<hex>`` of the file's on-disk bytes (raw; no canonicalization).

    Returns the missing-file-sentinel string ``''`` if the file does not exist.
    Callers MUST handle the sentinel; validate_signoff treats it as drift.

    Raises ``SignoffError`` on permission denied or unreadable file, and on
    symlink escaping the repo root.
    """
    if not path.exists():
        return ""

    # Symlink-escape check (defense-in-depth, mirrors Story 2A.5's compute_hook_hashes)
    if repo_root is not None and path.is_symlink():
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise SignoffError(
                f"artifact path cannot be resolved: {path}: {exc}",
                details={"step": "compute_artifact_hash", "path": str(path)},
            ) from exc
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            raise SignoffError(
                f"artifact symlink escapes repo: {path.name} → {resolved}",
                details={"step": "compute_artifact_hash", "path": str(path)},
            ) from None

    try:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            while chunk := fh.read(_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as exc:
        raise SignoffError(
            f"failed to read artifact {path}: {exc}",
            details={"step": "compute_artifact_hash", "path": str(path)},
        ) from exc

    return f"sha256:{digest.hexdigest()}"


def _canonicalize_record_bytes(record: object) -> bytes:
    """Return canonical YAML bytes for a SignoffRecord (Pattern §3 YAML equivalent)."""
    # Use model_dump(mode="json") to get JSON-compatible scalars (strings, not datetimes)
    data = record.model_dump(mode="json")  # type: ignore[attr-defined]
    return yaml.safe_dump(
        data,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    ).encode("utf-8")


def compute_signoff_record_hash(record: object) -> str:
    """Return ``sha256:<hex>`` of the canonical YAML serialisation of the record.

    Used by Story 2A.19 sdlc replan to detect external tampering with the
    canonical record itself. Canonicalization: yaml.safe_dump(sort_keys=True,
    default_flow_style=False, allow_unicode=True) — YAML analogue of Pattern §3.
    """
    canonical = _canonicalize_record_bytes(record)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
