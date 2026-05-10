"""phase_gate builtin hook — phase boundary enforcement (FR37, AC5, Story 2A.4).

Reads the minimal signoff record (file exists + approved==True) to gate writes
to Phase 2 and Phase 3 paths. Hash drift validation and full signoff CRUD belong
to Story 2A.7 — this hook is intentionally minimal (necessary-but-not-sufficient).

DEBT: EPIC-2A-DEBT-PHASE-GATE-READ — when Story 2A.7 ships
  ``signoff.records.read_record(phase: int) -> SignoffRecord | None``, replace the
  direct yaml.safe_load here with that canonical reader. The hook will receive
  the reader via a callback DI parameter to preserve the boundary rule:
  hooks/ MUST NOT import signoff/ (signoff/ sits ABOVE hooks/ in the layer
  hierarchy per Architecture §1061).

Architecture §1109: hooks/ does NOT import engine/ or dispatcher/.
Boundary (AC9): this module imports only stdlib + yaml + sdlc.errors + sdlc.hooks.runner.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Final

import yaml

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.runner import HookDecision

_HOOK_NAME: Final[str] = "phase_gate"

# Signoff file paths relative to repo_root
_SIGNOFF_DIR: Final[str] = ".claude/state/signoffs"
_PHASE_1_SIGNOFF: Final[str] = "phase-1.yaml"
_PHASE_2_SIGNOFF: Final[str] = "phase-2.yaml"


def _deny_gate(reason: str) -> HookDecision:
    return HookDecision.deny(
        hook_name=_HOOK_NAME,
        reason=reason,
        error_code="phase_gate_violation",
    )


def _get_leading_dir(target_path: str) -> str | None:
    """Extract leading directory from a POSIX path string (defense against Windows sep)."""
    parts = PurePosixPath(target_path).parts
    if not parts:
        return None
    return parts[0]


def _read_signoff(signoff_path: Path) -> bool | None:
    """Read signoff YAML and return approved status, or None if absent/corrupted."""
    if not signoff_path.exists():
        return None
    try:
        data = yaml.safe_load(signoff_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return bool(data.get("approved", False))
    except yaml.YAMLError:
        # Signal corruption via a sentinel — caller checks for this
        raise


def _check_signoff(signoff_path: Path, phase_num: int) -> HookDecision | None:
    """Return deny if signoff is absent/rejected; None (= allow) if approved."""
    try:
        approved = _read_signoff(signoff_path)
    except yaml.YAMLError:
        return _deny_gate(
            f"phase-gate violation: Phase {phase_num} signoff at "
            f"{signoff_path.name} is corrupted (YAML parse error)"
        )

    if approved is None:
        return _deny_gate(
            f"phase-gate violation: Phase {phase_num} path requires valid "
            f"Phase {phase_num - 1} signoff at {signoff_path}; not found"
        )
    if not approved:
        return _deny_gate(
            f"phase-gate violation: Phase {phase_num} path requires valid "
            f"Phase {phase_num - 1} signoff at {signoff_path}; signoff exists "
            f"but approved=false"
        )
    return None


def phase_gate(
    payload: HookPayload,
    *,
    repo_root: Path,
    bypass_phase_gate: bool = False,
) -> HookDecision:
    """Gate writes to Phase 2/3 paths on the existence of the prior phase's signoff.

    Phase 1 paths (01-Requirement/) → always allow.
    Phase 2 paths (02-Architecture/) → require phase-1.yaml with approved=true.
    Phase 3 paths (03-Implementation/) → require phase-2.yaml with approved=true.
    All other paths (.claude/, tests/, _bmad-output/, etc.) → allow.
    """
    if bypass_phase_gate:
        return HookDecision.allow()

    leading = _get_leading_dir(payload.target_path)

    if leading is None or leading.startswith("01-"):
        return HookDecision.allow()

    if leading.startswith("02-"):
        signoff_path = repo_root / _SIGNOFF_DIR / _PHASE_1_SIGNOFF
        deny = _check_signoff(signoff_path, phase_num=2)
        return deny if deny is not None else HookDecision.allow()

    if leading.startswith("03-"):
        signoff_path = repo_root / _SIGNOFF_DIR / _PHASE_2_SIGNOFF
        deny = _check_signoff(signoff_path, phase_num=3)
        return deny if deny is not None else HookDecision.allow()

    # Non-phase paths (.claude/, tests/, _bmad-output/, config files, etc.)
    return HookDecision.allow()
