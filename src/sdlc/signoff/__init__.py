"""signoff package public API (Story 2A.7, AC11)."""

from __future__ import annotations

from sdlc.signoff.hasher import compute_artifact_hash, compute_signoff_record_hash
from sdlc.signoff.records import (
    ArtifactRef,
    SignoffRecord,
    invalidate_record,
    list_records,
    read_record,
    write_record,
)
from sdlc.signoff.states import SignoffState, compute_state
from sdlc.signoff.validator import ArtifactDrift, ValidatedSignoff, validate_signoff

__all__ = (
    "ArtifactDrift",
    "ArtifactRef",
    "SignoffRecord",
    "SignoffState",
    "ValidatedSignoff",
    "compute_artifact_hash",
    "compute_signoff_record_hash",
    "compute_state",
    "invalidate_record",
    "list_records",
    "read_record",
    "validate_signoff",
    "write_record",
)
