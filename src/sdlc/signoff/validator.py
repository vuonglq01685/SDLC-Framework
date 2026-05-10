"""Signoff hash-drift validator (AC3, Story 2A.7).

validate_signoff is the v1 audit-gate: it proves zero false negatives
on hash drift (NFR-REL-3, PRD §344). The caller (Story 2A.12) is
responsible for calling records.write_record after a clean ValidatedSignoff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sdlc.errors import SignoffError
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.signoff.records import _PHASE_DIR_MAP, ArtifactRef, SignoffRecord, read_signoff_md_draft
from sdlc.signoff.states import SignoffState

_VALID_PHASES = frozenset({1, 2})  # phase 3 has no signoff (AC10)
_PHASE_NO_SIGNOFF: int = 3


@dataclass(frozen=True)
class ArtifactDrift:
    """Single artifact hash-drift entry (AC3)."""

    path: str
    expected: str  # hash recorded in SIGNOFF.md draft
    actual: str  # hash computed from disk ('' sentinel if file missing)
    kind: Literal["drifted", "missing"]


@dataclass(frozen=True)
class ValidatedSignoff:
    """Result of a successful validate_signoff call (AC3).

    state is always APPROVED on success.
    drift is always () — reserved for future "report-all-drifts" mode.
    """

    state: SignoffState
    record: SignoffRecord
    drift: tuple[ArtifactDrift, ...] = field(default_factory=tuple)


def validate_signoff(  # noqa: C901
    phase: int,
    *,
    repo_root: Path,
    now_utc: str,
) -> ValidatedSignoff:
    """Validate a SIGNOFF.md draft and return a ValidatedSignoff on success.

    Steps (AC3):
      1. Phase 3 is unconditionally rejected (AC10).
      2. Reads SIGNOFF.md draft; raises if approved=false.
      3. Checks each artifact for cross-phase violation.
      4. Recomputes hashes; raises on first path-sorted drift.
      5. Returns ValidatedSignoff(state=APPROVED, record=<populated>).

    The caller (Story 2A.12) calls records.write_record(result.record).
    """
    if phase == _PHASE_NO_SIGNOFF:
        raise SignoffError(
            "phase 3 has no signoff in v1; cannot validate",
            details={"phase": 3},
        )
    if phase not in {1, 2}:
        raise SignoffError(
            f"phase out of range: must be 1 or 2 for validate_signoff; got {phase}",
            details={"phase": phase},
        )

    phase_dir_name = _PHASE_DIR_MAP[phase]
    draft_path = repo_root / phase_dir_name / "SIGNOFF.md"

    if not draft_path.exists():
        raise SignoffError(
            f"SIGNOFF.md draft not found for phase {phase} at {draft_path}",
            details={"step": "validate_signoff", "phase": phase, "draft_path": str(draft_path)},
        )

    draft = read_signoff_md_draft(draft_path)

    if not draft.approved:
        raise SignoffError(
            f"phase {phase} draft is not yet approved (approved: false); cannot validate",
            details={
                "step": "validate_signoff",
                "phase": phase,
                "draft_path": str(draft_path),
            },
        )

    # Cross-phase artifact check (AC3 last-And)
    for art in draft.artifacts:
        if not art.path.startswith(phase_dir_name + "/") and not art.path.startswith(
            phase_dir_name + "\\"
        ):
            raise SignoffError(
                f"artifact {art.path!r} is outside phase-{phase} tree ({phase_dir_name}); "
                "cross-phase signoffs are not supported in v1",
                details={
                    "step": "validate_signoff",
                    "phase": phase,
                    "artifact_path": art.path,
                },
            )

    # Hash-drift check — process in path-sorted order for determinism (AC3 + AC8)
    sorted_artifacts = sorted(draft.artifacts, key=lambda a: a.path)
    for art in sorted_artifacts:
        artifact_abs = repo_root / art.path
        actual_hash = compute_artifact_hash(artifact_abs, repo_root=repo_root)

        if actual_hash == "":
            # Sentinel: file missing
            raise SignoffError(
                f"hash drift on artifact {art.path!r}: file is missing (deleted since draft)",
                details={
                    "step": "validate_signoff",
                    "phase": phase,
                    "artifact_path": art.path,
                    "expected": art.hash,
                    "actual": "",
                    "kind": "missing",
                },
            )

        if actual_hash != art.hash:
            raise SignoffError(
                f"hash drift on artifact {art.path!r}: expected {art.hash!r}, got {actual_hash!r}",
                details={
                    "step": "validate_signoff",
                    "phase": phase,
                    "artifact_path": art.path,
                    "expected": art.hash,
                    "actual": actual_hash,
                    "kind": "drifted",
                },
            )

    # Build the canonical SignoffRecord (caller writes it via write_record)
    artifact_refs = tuple(ArtifactRef(path=art.path, hash=art.hash) for art in draft.artifacts)
    record = SignoffRecord(
        phase=phase,
        artifacts=artifact_refs,
        approved_by=draft.approved_by or "",
        approved_at=draft.approved_at or now_utc,
        drafted_at=draft.drafted_at,
        validated_at=now_utc,
    )
    return ValidatedSignoff(state=SignoffState.APPROVED, record=record, drift=())
