"""signoff package public API (Story 2A.7, AC11).

Exports populated incrementally across TDD commits:
  Commit 1: compute_artifact_hash, compute_signoff_record_hash (hasher.py)
  Commit 2: SignoffRecord, ArtifactRef, read_record, write_record,
             invalidate_record, list_records (records.py)
  Commit 3: SignoffState, compute_state (states.py)
  Commit 4: ValidatedSignoff, ArtifactDrift, validate_signoff (validator.py)
"""

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

__all__ = [
    "compute_artifact_hash",
    "compute_signoff_record_hash",
    "ArtifactRef",
    "SignoffRecord",
    "invalidate_record",
    "list_records",
    "read_record",
    "write_record",
    "SignoffState",
    "compute_state",
    "ArtifactDrift",
    "ValidatedSignoff",
    "validate_signoff",
]
