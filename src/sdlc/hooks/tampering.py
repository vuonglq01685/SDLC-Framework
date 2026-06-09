"""Hook tampering detection (FR39, NFR-SEC-5, Architecture §863).

Boundary: this module is pure logic — no atomic-write side effects. Callers
(``sdlc.cli._hook_trust_writer``) orchestrate atomic writes via
``sdlc.state.atomic``. The only filesystem reads here are ``compute_hook_hashes``
(walks hooks tree) and ``detect_tampering`` (reads hook-hashes.json). See
Story 2A.5 DR1 (code review 2026-05-10): record_trust orchestration moved to
the CLI layer to satisfy AC10's file-level boundary rule.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from sdlc.errors import HookError
from sdlc.hooks._hash_store import (
    HOOKS_ROOT_LABEL,
    SCHEMA_VERSION,
    _HookHashStore,
)


@dataclass(frozen=True)
class HookDrift:
    relpath: str
    expected: str | None
    actual: str | None
    kind: Literal["added", "removed", "modified"]


@dataclass(frozen=True)
class TamperReport:
    status: Literal["clean", "tampered", "uninitialized", "corrupted"]
    expected: Mapping[str, str]
    actual: Mapping[str, str]
    drift: tuple[HookDrift, ...]
    message: str
    # P7: structured fields so render_warning composes the corrupted message
    # without fragile `: ` splitting on the prose.
    detail: str | None = None
    store_path: str | None = None


def _stream_file_sha256(path: Path) -> str:
    """Hex sha256 of a file's content, streamed for bounded memory.

    Uses ``hashlib.file_digest`` on Python 3.11+; falls back to a chunked loop on
    Python 3.10 (file_digest was added in 3.11; requires-python floor is 3.10).
    """
    with path.open("rb") as fh:
        if hasattr(hashlib, "file_digest"):
            # hasattr-narrowed to Any (typeshed has file_digest only at 3.11+); the
            # annotation keeps warn_return_any happy without a version-fragile ignore.
            digest: str = hashlib.file_digest(fh, "sha256").hexdigest()
            return digest
        h = hashlib.sha256()
        while chunk := fh.read(1 << 16):
            h.update(chunk)
        return h.hexdigest()


def compute_hook_hashes(hooks_root: Path) -> dict[str, str]:
    """Return sorted dict of POSIX-relpath → ``sha256:<hex>`` for .py files in tree.

    Defensive guards (P3+P4+P5+P19):
    - missing root → ``HookError(step="compute_hook_hashes")``
    - rglob OSError (symlink loop, permission) → ``HookError``
    - non-files (directories named ``*.py``) → silently skipped
    - any path that resolves outside ``hooks_root`` → ``HookError``
    - broken symlink (``resolve(strict=True)`` fails) → ``HookError``
    - file content streamed via ``hashlib.file_digest`` (Python 3.11+) — bounded memory
    """
    if not hooks_root.exists():
        raise HookError(
            f"hooks_root not found: {hooks_root}; run 'sdlc init' first",
            details={"step": "compute_hook_hashes", "path": str(hooks_root)},
        )
    resolved_root = hooks_root.resolve()
    result: dict[str, str] = {}

    try:
        candidates = sorted(hooks_root.rglob("*.py"))
    except OSError as exc:
        raise HookError(
            f"failed to walk hooks_root: {exc}",
            details={"step": "compute_hook_hashes", "path": str(hooks_root)},
        ) from exc

    for py_path in candidates:
        if not py_path.is_file():  # P19: skip dirs named *.py
            continue

        try:
            resolved = py_path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise HookError(
                f"hook path cannot be resolved: {py_path}: {exc}",
                details={"step": "compute_hook_hashes", "path": str(py_path)},
            ) from exc

        relpath = str(PurePosixPath(py_path.relative_to(hooks_root)))
        try:
            resolved.relative_to(resolved_root)
        except ValueError:
            raise HookError(
                f"hook escapes hooks_root: {relpath} → {resolved}",
                details={"step": "compute_hook_hashes", "path": str(py_path)},
            ) from None

        try:
            digest = _stream_file_sha256(resolved)  # P5 streaming
        except OSError as exc:
            raise HookError(
                f"failed to read hook file {relpath}: {exc}",
                details={"step": "compute_hook_hashes", "path": str(py_path)},
            ) from exc

        result[relpath] = f"sha256:{digest}"
    return result


def build_hook_hash_store_payload(hashes: Mapping[str, str], *, now_utc: str) -> dict[str, Any]:
    """Return the hook-hashes.json payload dict (sorted keys, ms-precision UTC).

    Pure logic — the CLI orchestration layer (``sdlc.cli._hook_trust_writer``)
    passes this payload to ``sdlc.state.atomic.write_state_raw_atomic_sync``,
    which handles canonical-bytes serialization + atomic write.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "trusted_at": now_utc,
        "hooks_root": HOOKS_ROOT_LABEL,
        "hashes": dict(sorted(hashes.items())),
    }


def detect_tampering(state_root: Path, hooks_root: Path) -> TamperReport:  # noqa: C901  # 4 status branches and 3 drift kinds; collapsing harms readability
    """Compare current hook hashes against stored hash store (AC4).

    Per AC4 third-Given: NEVER raises on store-not-found or store-corrupt;
    those are *report states*. Per P1, missing ``hooks_root`` is also classified
    as ``uninitialized`` instead of raising. ``HookError`` still propagates for
    genuinely-unrecoverable conditions like a symlink-escape attempt — that's
    a security signal callers (init, scan) MUST surface, not swallow.
    """
    store_path = state_root / "hook-hashes.json"

    try:
        actual = compute_hook_hashes(hooks_root)
    except HookError as exc:
        step_path = exc.details.get("path", "")
        if step_path == str(hooks_root) and "not found" in str(exc):
            return TamperReport(
                status="uninitialized",
                expected={},
                actual={},
                drift=(),
                message="hook hashes unavailable; run 'sdlc trust-hooks' to initialize.",
            )
        raise

    if not store_path.exists():
        return TamperReport(
            status="uninitialized",
            expected={},
            actual=actual,
            drift=(),
            message="hook hashes unavailable; run 'sdlc trust-hooks' to initialize.",
        )

    try:
        raw = store_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        store = _HookHashStore.model_validate(data)
    except Exception as exc:
        return TamperReport(
            status="corrupted",
            expected={},
            actual=actual,
            drift=(),
            message=f"hook hash store at {store_path} is corrupted: {exc}",
            detail=str(exc),
            store_path=str(store_path),
        )

    expected: dict[str, str] = dict(store.hashes)
    drift_items: list[HookDrift] = []
    for key in sorted(set(expected) | set(actual)):
        exp_val = expected.get(key)
        act_val = actual.get(key)
        if exp_val == act_val:
            continue
        kind: Literal["added", "removed", "modified"]
        if exp_val is None:
            kind = "added"
        elif act_val is None:
            kind = "removed"
        else:
            kind = "modified"
        drift_items.append(HookDrift(relpath=key, expected=exp_val, actual=act_val, kind=kind))
    drift = tuple(sorted(drift_items, key=lambda d: d.relpath))

    if drift:
        return TamperReport(
            status="tampered",
            expected=expected,
            actual=actual,
            drift=drift,
            message=f"hook tampering detected: {len(drift)} file(s) changed since trust.",
        )

    return TamperReport(
        status="clean",
        expected=expected,
        actual=actual,
        drift=(),
        message="hook hashes match stored trust record.",
    )


def render_warning(report: TamperReport) -> str:
    """Return human-readable advisory string for a non-clean TamperReport (AC5)."""
    if report.status == "uninitialized":
        return "[WARN] hook hashes unavailable; run 'sdlc trust-hooks' to initialize."

    if report.status == "corrupted":
        # P7: use structured fields rather than splitting `report.message`.
        path = report.store_path or "<unknown path>"
        detail = report.detail or "unknown reason"
        return (
            f"[WARN] hook hash store at {path} is corrupted: {detail}; "
            "run 'sdlc trust-hooks' to re-initialize."
        )

    if report.status == "tampered":
        lines = [
            f"[WARN] hook tampering detected: {len(report.drift)} file(s) changed since trust."
        ]
        for drift in report.drift:
            prefix = f"  .claude/hooks/{drift.relpath}"
            if drift.kind == "modified":
                # P18: strip sha256: prefix so the visible chars are hex,
                # not the constant 7-char envelope.
                exp_short = (drift.expected or "").removeprefix("sha256:")[:16]
                act_short = (drift.actual or "").removeprefix("sha256:")[:16]
                lines += [
                    f"  modified: .claude/hooks/{drift.relpath}",
                    f"    expected: sha256:{exp_short}...",
                    f"    actual:   sha256:{act_short}...",
                ]
            elif drift.kind == "added":
                lines.append(f"  added:    {prefix}")
            else:
                lines.append(f"  removed:  {prefix}")
        lines.append("Run 'sdlc trust-hooks' to acknowledge or restore the file(s).")
        return "\n".join(lines)

    return ""  # clean — caller should not call render_warning
