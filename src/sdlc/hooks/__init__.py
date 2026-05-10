"""Hook package public API (FR36, FR37, FR39, NFR-SEC-5).

Detection-only surface (2A.5) — write orchestration lives in
``sdlc.cli._hook_trust_writer`` per Story 2A.5 DR1 (AC10 boundary).

Pre-write hook chain (2A.4):
- HookPayload / HookDecision — wire-format contract + runtime decision
- run_hook_chain — async orchestrator (naming_validator → phase_gate)
- naming_validator, phase_gate — builtin hooks
- payload builders — build_write_intent_payload, build_phase_advance_payload,
  build_signoff_record_payload
"""

from __future__ import annotations

from sdlc.hooks.builtin import naming_validator, phase_gate
from sdlc.hooks.payload import (
    build_phase_advance_payload,
    build_signoff_record_payload,
    build_write_intent_payload,
)
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.hooks.tampering import (
    HookDrift,
    TamperReport,
    build_hook_hash_store_payload,
    compute_hook_hashes,
    detect_tampering,
    render_warning,
)

__all__ = [
    "HookDecision",
    "HookDrift",
    "TamperReport",
    "build_hook_hash_store_payload",
    "build_phase_advance_payload",
    "build_signoff_record_payload",
    "build_write_intent_payload",
    "compute_hook_hashes",
    "detect_tampering",
    "naming_validator",
    "phase_gate",
    "render_warning",
    "run_hook_chain",
]
