"""Hook package public API (FR39, NFR-SEC-5).

Detection-only surface — write orchestration lives in
``sdlc.cli._hook_trust_writer`` per Story 2A.5 DR1 (AC10 boundary).
Runner/payload/builtin hooks arrive in Story 2A.4.
"""

from __future__ import annotations

from sdlc.hooks.tampering import (
    HookDrift,
    TamperReport,
    build_hook_hash_store_payload,
    compute_hook_hashes,
    detect_tampering,
    render_warning,
)

__all__ = [
    "HookDrift",
    "TamperReport",
    "build_hook_hash_store_payload",
    "compute_hook_hashes",
    "detect_tampering",
    "render_warning",
]
