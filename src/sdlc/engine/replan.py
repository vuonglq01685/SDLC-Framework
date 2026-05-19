"""Pure replan logic: resolve_scope_phase, compute_downstream, plan_invalidations (FR4, 2A.19).

These functions are read-only / deterministic; all I/O side-effects (invalidate_record,
journal appends) live in cli/replan_cmd.py per Architecture §1134 (FR4 split).

Module boundary: engine may import signoff, state, journal, config, errors.
engine must NOT import cli.
"""

from __future__ import annotations

from pathlib import Path

from sdlc.errors.base import WorkflowError
from sdlc.signoff.states import SignoffState, compute_state

# Leading directory → phase number mapping (AC1 + AC2/D1).
_DIR_TO_PHASE: dict[str, int] = {
    "01-Requirement": 1,
    "02-Architecture": 2,
    "03-Implementation": 3,
}

# Phase number → leading directory for downstream glob.
_PHASE_TO_DIR: dict[int, str] = {v: k for k, v in _DIR_TO_PHASE.items()}


def resolve_scope_phase(scope: str) -> int:
    """Return phase number for a repo-relative scope path based on its leading directory.

    Raises WorkflowError with ERR_USER_INPUT wording if the scope is not under
    a recognized phase directory.
    """
    for dir_name, phase in _DIR_TO_PHASE.items():
        if scope.startswith(dir_name + "/") or scope == dir_name:
            return phase
    raise WorkflowError(
        f"replan scope is not under a recognized phase directory: {scope}",
        details={"scope": scope},
    )


def compute_downstream(repo_root: Path, scope_phase: int) -> tuple[list[str], int]:
    """Return (sorted repo-relative POSIX paths, count) of all files in phases > scope_phase.

    Uses phase-based downstream per AC2/D1: downstream = every artifact file under a
    phase directory numerically greater than scope_phase.

    EPIC-2A-DEBT-REPLAN-FINE-GRAINED-DAG: a true artifact-provenance graph (architecture
    concern #16) would let a replan scope to a single epic/story subtree.
    """
    downstream: list[str] = []
    for phase_num in sorted(_PHASE_TO_DIR):
        if phase_num <= scope_phase:
            continue
        phase_dir = repo_root / _PHASE_TO_DIR[phase_num]
        if not phase_dir.exists():
            continue
        for f in sorted(phase_dir.rglob("*")):
            if f.is_file():
                downstream.append(f.relative_to(repo_root).as_posix())
    return downstream, len(downstream)


def plan_invalidations(repo_root: Path, scope_phase: int) -> list[int]:
    """Return phases in {1, 2} that are currently APPROVED and >= scope_phase.

    An already-INVALIDATED_BY_REPLAN phase is excluded — replan-then-replan
    must not double-invalidate (AC3; also sidesteps deferred-work.md W20).
    Phase 3 is never in {1,2}, so it is never returned.
    """
    phases: list[int] = []
    for p in [1, 2]:
        if p < scope_phase:
            continue
        try:
            state = compute_state(p, repo_root=repo_root)
        except Exception:
            continue
        if state == SignoffState.APPROVED:
            phases.append(p)
    return phases
