"""Cross-runtime byte capture for Story 2B.3 AC2/D2 (mock vs claude identity)."""

from __future__ import annotations

_CAPTURED: dict[str, tuple[bytes, bytes]] = {}


def record_runtime_bytes(factory_id: str, hook_payload_bytes: bytes, state_bytes: bytes) -> None:
    """Register golden actuals from one parametrized conformance run."""
    _CAPTURED[factory_id] = (hook_payload_bytes, state_bytes)


def pop_captured() -> dict[str, tuple[bytes, bytes]]:
    """Return and clear captures (session-finalize hook)."""
    snapshot = dict(_CAPTURED)
    _CAPTURED.clear()
    return snapshot
