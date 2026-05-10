"""Hook payload re-export + builder helpers (AC1, AC8, Story 2A.4).

Re-exports HookPayload from sdlc.contracts.hook_payload (Decision D2) so
engine-side and Claude-Code-side both import from hooks.payload, not from
contracts/ directly. This enforces the boundary ``claude_hooks/ → hooks.payload``
(NOT ``claude_hooks/ → contracts/``) per Story 2A.6's planned wiring.

Builder helpers construct valid HookPayload instances for the three canonical
target_kind values documented in hooks/__init__.py module docstring.
"""

from __future__ import annotations

from sdlc.contracts.hook_payload import HookPayload

__all__ = [
    "HookPayload",
    "build_phase_advance_payload",
    "build_signoff_record_payload",
    "build_write_intent_payload",
]


def build_write_intent_payload(
    *,
    hook_name: str,
    target_path: str,
    write_intent: str,
    content_hash_before: str | None = None,
) -> HookPayload:
    """Build a payload for the engine pre-write site (target_kind="write_intent")."""
    return HookPayload(
        hook_name=hook_name,
        target_path=target_path,
        target_kind="write_intent",
        content_hash_before=content_hash_before,
        write_intent=write_intent,
    )


def build_phase_advance_payload(
    *,
    hook_name: str,
    target_path: str,
    write_intent: str,
    content_hash_before: str | None = None,
) -> HookPayload:
    """Build a payload for Phase 1→2 / 2→3 transition writes (target_kind="phase_advance")."""
    return HookPayload(
        hook_name=hook_name,
        target_path=target_path,
        target_kind="phase_advance",
        content_hash_before=content_hash_before,
        write_intent=write_intent,
    )


def build_signoff_record_payload(
    *,
    hook_name: str,
    target_path: str,
    write_intent: str,
    content_hash_before: str | None = None,
) -> HookPayload:
    """Build a payload for signoff CRUD operations (target_kind="signoff_record")."""
    return HookPayload(
        hook_name=hook_name,
        target_path=target_path,
        target_kind="signoff_record",
        content_hash_before=content_hash_before,
        write_intent=write_intent,
    )
