"""CLI bypass validation helper for --force-bypass-signoff (AC6, Story 2A.4).

Integration contract for future commands (Stories 2A.13/14/15):
Any CLI command that drives dispatcher writes to Phase 2/3 paths MUST:
  (a) Accept --force-bypass-signoff <justification> flag.
  (b) Call validate_bypass_request(justification, repo_root=root) BEFORE invoking
      the dispatcher — this enforces trust-store check + min-length guard.
  (c) Pass bypass_phase_gate=True, justification=<text> through to
      run_hook_chain via the dispatcher's hook-chain parameter (Story 2A.6 wires
      this end-to-end).

DEBT: EPIC-2A-DEBT-BYPASS-FLAG-WIRING — Stories 2A.13/14/15 (sdlc-ux,
  sdlc-architect, sdlc-bootstrap) are the consumer commands that add the
  --force-bypass-signoff flag and call validate_bypass_request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from sdlc.errors import HookError
from sdlc.hooks.tampering import detect_tampering

_MIN_JUSTIFICATION_LEN: Final[int] = 10
_MAX_JUSTIFICATION_LEN: Final[int] = 500


def validate_bypass_request(justification: str, *, repo_root: Path) -> None:
    """Validate a --force-bypass-signoff request.

    Checks:
    1. Justification must be at least 10 characters.
    2. Hook trust store must NOT be uninitialized or corrupted.
       (Tampered is advisory-only in v1 — bypass is still allowed.)

    Raises:
        HookError: if justification is too short or trust store is unestablished.
    """
    if len(justification) < _MIN_JUSTIFICATION_LEN:
        raise HookError(
            f"--force-bypass-signoff requires a justification of at least "
            f"{_MIN_JUSTIFICATION_LEN} characters",
            details={"step": "validate_bypass_request", "justification_len": len(justification)},
        )

    state_root = repo_root / ".claude" / "state"
    hooks_root = repo_root / ".claude" / "hooks"
    try:
        report = detect_tampering(state_root, hooks_root)
    except Exception as exc:
        # If detect_tampering itself fails (e.g., corrupted store can't be parsed),
        # treat as uninitialized/corrupted per the advisory-only v1 contract.
        raise HookError(
            "[ERROR] cannot bypass while hook trust is unestablished; run 'sdlc trust-hooks' first",
            details={"step": "validate_bypass_request", "cause": str(exc)},
        ) from exc

    if report.status in ("uninitialized", "corrupted"):
        raise HookError(
            "[ERROR] cannot bypass while hook trust is unestablished; run 'sdlc trust-hooks' first",
            details={"step": "validate_bypass_request", "trust_status": report.status},
        )


def truncate_justification(text: str, max_len: int = _MAX_JUSTIFICATION_LEN) -> tuple[str, bool]:
    """Truncate justification to max_len characters (DoS guard on journal payload size).

    Returns:
        (truncated_text, was_truncated)
    """
    if len(text) <= max_len:
        return text, False
    return text[:max_len], True
