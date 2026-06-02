"""Contract tests for `AdoptReport` + `DetectedArtifact` wire-format models (Story 3.1).

`AdoptReport` is the 6th frozen wire-format contract (ADR-024 amendment; epic-3-dag.md
Decision D1 RATIFIED = wire-format). These tests pin the strict-mode behaviour the
StrictModel base guarantees:

  * round-trip JSON serialization is stable;
  * `extra="forbid"` rejects unknown keys;
  * `strict=True` rejects float→int coercion on `confidence` (D2(a) = int percent);
  * `kind` is constrained to the epics.md:1803 enum;
  * `schema_version` rejects non-strict-int inputs (mirrors journal_entry.py:28-33).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from sdlc.contracts.adopt_report import AdoptReport, DetectedArtifact

pytestmark = pytest.mark.unit


def _valid_artifact_payload() -> dict[str, object]:
    return {
        "path": "docs/prd.md",
        "kind": "prd",
        "confidence": 92,
        "suggested_target": ".claude/01-Requirement/prd.md",
    }


def _valid_report_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "repo_root": "/home/user/project",
        "scanned_at": "2026-06-02T12:00:00.000Z",
        "detected": [_valid_artifact_payload()],
        "passes_completed": [1],
    }


# --- DetectedArtifact -------------------------------------------------------


def test_detected_artifact_round_trips() -> None:
    payload = _valid_artifact_payload()
    artifact = DetectedArtifact.model_validate(payload)
    dumped = artifact.model_dump(mode="json")
    assert dumped == payload


def test_detected_artifact_rejects_extra_key() -> None:
    payload = {**_valid_artifact_payload(), "unexpected": "x"}
    with pytest.raises(ValidationError):
        DetectedArtifact.model_validate(payload)


def test_detected_artifact_rejects_float_confidence() -> None:
    """D2(a): confidence is a strict int percent [0,100]; a 0.92 float must be rejected."""
    payload = {**_valid_artifact_payload(), "confidence": 0.92}
    with pytest.raises(ValidationError):
        DetectedArtifact.model_validate(payload)


def test_detected_artifact_rejects_confidence_above_100() -> None:
    payload = {**_valid_artifact_payload(), "confidence": 101}
    with pytest.raises(ValidationError):
        DetectedArtifact.model_validate(payload)


def test_detected_artifact_rejects_negative_confidence() -> None:
    payload = {**_valid_artifact_payload(), "confidence": -1}
    with pytest.raises(ValidationError):
        DetectedArtifact.model_validate(payload)


def test_detected_artifact_rejects_unknown_kind() -> None:
    payload = {**_valid_artifact_payload(), "kind": "spreadsheet"}
    with pytest.raises(ValidationError):
        DetectedArtifact.model_validate(payload)


@pytest.mark.parametrize(
    "kind",
    [
        "prd",
        "architecture",
        "research",
        "runbook",
        "ci-workflow",
        "build-file",
        "dockerfile",
        "readme",
        "unknown",
    ],
)
def test_detected_artifact_accepts_every_canonical_kind(kind: str) -> None:
    payload = {**_valid_artifact_payload(), "kind": kind}
    artifact = DetectedArtifact.model_validate(payload)
    assert artifact.kind == kind


# --- AdoptReport ------------------------------------------------------------


def test_adopt_report_round_trips() -> None:
    payload = _valid_report_payload()
    report = AdoptReport.model_validate(payload)
    assert json.loads(report.model_dump_json()) == payload


def test_adopt_report_rejects_extra_key() -> None:
    payload = {**_valid_report_payload(), "rogue": 1}
    with pytest.raises(ValidationError):
        AdoptReport.model_validate(payload)


def test_adopt_report_rejects_non_strict_schema_version() -> None:
    """schema_version must be a strict int (not bool/str) — matches journal_entry.py."""
    payload = {**_valid_report_payload(), "schema_version": True}
    with pytest.raises(ValidationError):
        AdoptReport.model_validate(payload)


def test_adopt_report_rejects_wrong_schema_version() -> None:
    payload = {**_valid_report_payload(), "schema_version": 2}
    with pytest.raises(ValidationError):
        AdoptReport.model_validate(payload)


def test_adopt_report_rejects_bad_scanned_at() -> None:
    """scanned_at must be RFC-3339 UTC ms with a Z suffix (constraint captured in snapshot)."""
    payload = {**_valid_report_payload(), "scanned_at": "2026-06-02 12:00:00"}
    with pytest.raises(ValidationError):
        AdoptReport.model_validate(payload)


def test_adopt_report_defaults_detected_empty() -> None:
    """3.1 driver writes detected: [] — the shape is frozen, Pass 1 (3.2) populates it."""
    payload = {**_valid_report_payload(), "detected": []}
    report = AdoptReport.model_validate(payload)
    assert report.detected == ()


def test_adopt_report_is_frozen() -> None:
    report = AdoptReport.model_validate(_valid_report_payload())
    with pytest.raises(ValidationError):
        report.repo_root = "/elsewhere"  # type: ignore[misc]


def test_adopt_report_registered_in_wire_format_registry() -> None:
    """AC5: AdoptReport is the 6th locked wire-format contract."""
    from sdlc.contracts import _WIRE_FORMAT_REGISTRY

    slugs = {slug for slug, _ in _WIRE_FORMAT_REGISTRY}
    classes = {cls.__name__ for _, cls in _WIRE_FORMAT_REGISTRY}
    assert "adopt_report" in slugs
    assert "AdoptReport" in classes
