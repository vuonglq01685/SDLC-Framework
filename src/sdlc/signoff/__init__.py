"""signoff package public API (Story 2A.7, AC11)."""

from __future__ import annotations

from sdlc.signoff.generator import generate_signoff_md
from sdlc.signoff.hasher import compute_artifact_hash, compute_signoff_record_hash
from sdlc.signoff.records import _PHASE_DIR_MAP as PHASE_DIR_MAP  # P15: public re-export
from sdlc.signoff.records import (
    ArtifactRef,
    SignoffRecord,
    invalidate_record,
    list_records,
    read_record,
    read_signoff_md_draft,
    write_record,
)
from sdlc.signoff.records import _SignoffMdDraft as SignoffMdDraft  # P15: public re-export
from sdlc.signoff.states import SignoffState, compute_state
from sdlc.signoff.validator import ArtifactDrift, ValidatedSignoff, validate_signoff

__all__ = (
    "PHASE_DIR_MAP",
    "ArtifactDrift",
    "ArtifactRef",
    "SignoffMdDraft",
    "SignoffRecord",
    "SignoffState",
    "ValidatedSignoff",
    "compute_artifact_hash",
    "compute_signoff_record_hash",
    "compute_state",
    "generate_signoff_md",
    "invalidate_record",
    "list_records",
    "read_record",
    "read_signoff_md_draft",
    "validate_signoff",
    "write_record",
)
