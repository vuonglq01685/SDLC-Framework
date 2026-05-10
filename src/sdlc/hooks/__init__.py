"""Hook package public API (FR39, NFR-SEC-5).

Exports tampering-detection surface; runner/payload/builtin hooks arrive in Story 2A.4.
"""

from __future__ import annotations

from sdlc.hooks.tampering import (
    HookDrift,
    TamperReport,
    compute_hook_hashes,
    detect_tampering,
    record_trust,
    render_warning,
)

__all__ = [
    "HookDrift",
    "TamperReport",
    "compute_hook_hashes",
    "detect_tampering",
    "record_trust",
    "render_warning",
]
