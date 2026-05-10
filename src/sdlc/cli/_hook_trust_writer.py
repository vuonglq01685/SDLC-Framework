"""CLI orchestration for writing the hook-hashes.json trust store (Story 2A.5 DR1).

Boundary discipline (AC10): ``sdlc.hooks.tampering`` is pure logic; this module
owns the atomic-write side effect. ``sdlc.hooks.tampering.build_hook_hash_store_payload``
constructs the payload dict; this module routes it through
``sdlc.state.atomic.write_state_raw_atomic_sync`` (POSIX) or raises ``HookError``
(Windows) until cross-platform support arrives in a follow-up story.

This split eliminates three hand-rolled JSON-dump sites that previously existed
in ``cli/init.py``, ``cli/trust_hooks.py``, and ``hooks/tampering.py``.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from sdlc.errors import HookError
from sdlc.hooks.tampering import build_hook_hash_store_payload


def write_hook_hashes_atomic(state_root: Path, hashes: Mapping[str, str], *, now_utc: str) -> Path:
    """Write ``hook-hashes.json`` atomically under ``state_root``.

    Returns the absolute store path on success.

    On POSIX: routes through ``sdlc.state.atomic.write_state_raw_atomic_sync``
    (tmp + flock + rename + fsync). On Windows: raises ``HookError`` —
    cross-platform atomic-write support is deferred to a follow-up story
    (DR1-Windows). The caller should not silently fall back to a hand-rolled
    writer; the spec (AC3) forbids that and Story 2A.5 DR1 records the
    decision.
    """
    if sys.platform == "win32":
        raise HookError(
            "sdlc trust-hooks write is POSIX-only in v1; Windows support is"
            " tracked in DR1-Windows follow-up. See docs/runbooks/handle-hash-drift.md.",
            details={
                "step": "write_hook_hashes_atomic",
                "path": str(state_root / "hook-hashes.json"),
            },
        )

    target = (state_root / "hook-hashes.json").resolve()
    payload = build_hook_hash_store_payload(hashes, now_utc=now_utc)

    # Deferred POSIX-only import — sdlc.state.atomic raises ImportError on Windows.
    from sdlc.state.atomic import write_state_raw_atomic_sync

    try:
        write_state_raw_atomic_sync(payload, target)
    except HookError:
        raise
    except Exception as exc:
        raise HookError(
            f"hook-hashes.json atomic write failed: {exc}",
            details={"step": "write_hook_hashes_atomic", "path": str(target)},
        ) from exc

    return target


__all__ = ["write_hook_hashes_atomic"]
