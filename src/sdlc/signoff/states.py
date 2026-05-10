"""Signoff state machine (AC1, AC10, Story 2A.7).

4-state machine:
  awaiting-signoff        → no draft and no canonical record
  drafted-not-approved    → SIGNOFF.md exists; approved: false (or true before record written)
  approved                → canonical record exists; invalidated_at is null
  invalidated-by-replan   → canonical record exists; invalidated_at is non-null

structlog not installed; uses stdlib logging per AC1 doc note.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from sdlc.errors import SignoffError
from sdlc.signoff.records import _PHASE_DIR_MAP, read_record, read_signoff_md_draft

_log = logging.getLogger(__name__)

_VALID_PHASES = frozenset({1, 2, 3})
_PHASE_NO_SIGNOFF: int = 3

# Once-per-process warning flag for phase 3 (AC10)
_phase3_warned: bool = False


class SignoffState(str, Enum):
    """Canonical 4-state signoff state machine (AC1)."""

    AWAITING_SIGNOFF = "awaiting-signoff"
    DRAFTED_NOT_APPROVED = "drafted-not-approved"
    APPROVED = "approved"
    INVALIDATED_BY_REPLAN = "invalidated-by-replan"


def compute_state(  # noqa: C901
    phase: int,
    *,
    repo_root: Path,
    strict: bool = False,
) -> SignoffState:
    """Return the current SignoffState for phase.

    Priority order (AC1):
      1. Canonical record exists + invalidated_at non-null → INVALIDATED_BY_REPLAN
      2. Canonical record exists + invalidated_at null     → APPROVED
      3. SIGNOFF.md draft exists (any approved value)      → DRAFTED_NOT_APPROVED
      4. Neither                                           → AWAITING_SIGNOFF

    Phase 3 (AC10):
      strict=False (default): returns AWAITING_SIGNOFF + logs WARN once per process
      strict=True: raises SignoffError

    Per AC2 final-And: a malformed SIGNOFF.md draft is operator-actionable —
    the SignoffError raised by ``read_signoff_md_draft`` is propagated, NOT
    swallowed-and-demoted. Only a missing draft maps to AWAITING_SIGNOFF.

    Raises SignoffError for phase outside {1, 2, 3} or malformed canonical record.
    """
    global _phase3_warned  # noqa: PLW0603

    if phase not in _VALID_PHASES:
        raise SignoffError(
            f"phase out of range: must be 1, 2, or 3; got {phase}",
            details={"phase": phase},
        )

    if phase == _PHASE_NO_SIGNOFF:
        if strict:
            raise SignoffError(
                "phase 3 has no signoff in v1; use per-task TDD evidence + PR merge",
                details={"phase": 3},
            )
        if not _phase3_warned:
            _log.warning("phase 3 has no signoff in v1; treating as awaiting-signoff")
            _phase3_warned = True
        return SignoffState.AWAITING_SIGNOFF

    # Step 1 + 2: canonical record check
    record = read_record(phase, repo_root=repo_root)
    if record is not None:
        if record.invalidated_at is not None:
            return SignoffState.INVALIDATED_BY_REPLAN
        return SignoffState.APPROVED

    # Step 3: SIGNOFF.md draft check.
    # Per AC2 final-And, a malformed draft is operator-actionable: the SignoffError
    # propagates so the operator can fix the file rather than seeing the phase
    # silently demoted to AWAITING_SIGNOFF.
    phase_dir_name = _PHASE_DIR_MAP.get(phase)
    if phase_dir_name:
        draft_path = repo_root / phase_dir_name / "SIGNOFF.md"
        if draft_path.exists():
            read_signoff_md_draft(draft_path)
            return SignoffState.DRAFTED_NOT_APPROVED

    return SignoffState.AWAITING_SIGNOFF
