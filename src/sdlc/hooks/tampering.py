"""Hook tampering detection and trust management (FR39, NFR-SEC-5, Architecture §863).

_HookHashStore is internal policy state, not a wire-format contract. Format may evolve
in v1.x without ADR-024 ceremony.

Boundary note: record_trust uses a deferred import from sdlc.state.atomic; hooks/ is
permitted to import state/ per MODULE_DEPS (check_module_boundaries.py).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Final, Literal

from pydantic import StringConstraints, field_validator

from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import HookError

_RFC3339_UTC: Final[str] = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
_SHA256_PAT: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_VERSION: Final[int] = 1
_HOOKS_ROOT_LABEL: Final[str] = ".claude/hooks"


# ---------------------------------------------------------------------------
# Private pydantic model — NOT a wire-format contract (AC8)
# ---------------------------------------------------------------------------


class _HookHashStore(StrictModel):
    schema_version: Literal[1] = 1
    trusted_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC)]
    hooks_root: str
    hashes: dict[str, str]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

    @field_validator("hashes", mode="after")
    @classmethod
    def _validate_and_sort_hashes(cls, v: dict[str, str]) -> dict[str, str]:
        for key, val in v.items():
            if not _SHA256_PAT.match(val):
                raise ValueError(f"hash value for {key!r} must match sha256:<64hex>, got {val!r}")
        return dict(sorted(v.items()))


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def compute_hook_hashes(hooks_root: Path) -> dict[str, str]:
    """Return sorted dict of POSIX-relpath → 'sha256:<hex>' for .py files in hooks_root."""
    if not hooks_root.exists():
        raise HookError(
            f"hooks_root not found: {hooks_root}; run 'sdlc init' first",
            details={"step": "compute_hook_hashes", "path": str(hooks_root)},
        )
    resolved_root = hooks_root.resolve()
    result: dict[str, str] = {}
    for py_path in sorted(hooks_root.rglob("*.py")):
        if py_path.is_symlink():
            target = py_path.resolve()
            try:
                target.relative_to(resolved_root)
            except ValueError:
                relpath = str(PurePosixPath(py_path.relative_to(hooks_root)))
                raise HookError(
                    f"hook symlink escapes hooks_root: {relpath} → {target}",
                    details={"step": "compute_hook_hashes", "path": str(py_path)},
                ) from None
        relpath = str(PurePosixPath(py_path.relative_to(hooks_root)))
        result[relpath] = f"sha256:{hashlib.sha256(py_path.read_bytes()).hexdigest()}"
    return result


def record_trust(state_root: Path, hashes: dict[str, str], *, now_utc: str) -> None:
    """Write hook-hashes.json atomically to <state_root>/hook-hashes.json (AC3)."""
    target = state_root / "hook-hashes.json"
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "trusted_at": now_utc,
        "hooks_root": _HOOKS_ROOT_LABEL,
        "hashes": dict(sorted(hashes.items())),
    }
    try:
        if sys.platform == "win32":
            _record_trust_windows(target, payload)
        else:
            from sdlc.state.atomic import (  # noqa: PLC0415
                write_state_raw_atomic_sync,  # deferred POSIX-only
            )

            write_state_raw_atomic_sync(payload, target.resolve())
    except HookError:
        raise
    except Exception as exc:
        raise HookError(
            f"record_trust write failed: {exc}",
            details={"step": "record_trust", "path": str(target)},
        ) from exc


def _record_trust_windows(target: Path, payload: dict[str, object]) -> None:
    """Windows atomic write shim for hook-hashes.json (mirrors init.py pattern)."""
    import contextlib  # noqa: PLC0415
    import os  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    canonical = _canonicalize(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".hook-hashes.", suffix=".tmp", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(canonical)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


def _canonicalize(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )


def detect_tampering(state_root: Path, hooks_root: Path) -> TamperReport:
    """Compare current hook hashes against stored hash store; never raises on store issues."""
    store_path = state_root / "hook-hashes.json"

    # --- compute actual hashes (may raise HookError for permission denied etc.) ---
    actual = compute_hook_hashes(hooks_root)

    # --- load expected from store ---
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
        )

    expected: dict[str, str] = dict(store.hashes)

    # --- compute drift ---
    all_keys = sorted(set(expected) | set(actual))
    drift_items: list[HookDrift] = []
    for key in all_keys:
        exp_val = expected.get(key)
        act_val = actual.get(key)
        if exp_val == act_val:
            continue
        if exp_val is None:
            kind: Literal["added", "removed", "modified"] = "added"
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
    """Return human-readable warning string for non-clean TamperReport (AC5)."""
    if report.status == "uninitialized":
        return "[WARN] hook hashes unavailable; run 'sdlc trust-hooks' to initialize."

    if report.status == "corrupted":
        return (
            f"[WARN] hook hash store is corrupted: {report.message.split(': ', 1)[-1]}; "
            "run 'sdlc trust-hooks' to re-initialize."
        )

    if report.status == "tampered":
        lines = [
            f"[WARN] hook tampering detected: {len(report.drift)} file(s) changed since trust."
        ]
        for drift in report.drift:
            prefix = f"  .claude/hooks/{drift.relpath}"
            if drift.kind == "modified":
                exp_short = (drift.expected or "")[:15]
                act_short = (drift.actual or "")[:15]
                lines += [
                    f"  modified: .claude/hooks/{drift.relpath}",
                    f"    expected: {exp_short}...",
                    f"    actual:   {act_short}...",
                ]
            elif drift.kind == "added":
                lines.append(f"  added:    {prefix}")
            else:
                lines.append(f"  removed:  {prefix}")
        lines.append("Run 'sdlc trust-hooks' to acknowledge or restore the file(s).")
        return "\n".join(lines)

    return ""  # clean — caller should not call render_warning for clean status
