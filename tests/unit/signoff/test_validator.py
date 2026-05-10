"""Unit tests for signoff/validator.py — validate_signoff + hash-drift (AC3, Story 2A.7)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_VALID_HASH = "sha256:" + "a" * 64
_ZERO_HASH = "sha256:" + "0" * 64
_TS1 = "2026-05-10T11:00:00.000Z"
_TS2 = "2026-05-10T12:00:00.000Z"
_TS_NOW = "2026-05-10T13:00:00.000Z"

_PHASE_DIR = {1: "01-Requirement", 2: "02-Architecture"}


def _setup_phase(
    repo_root: Path,
    phase: int,
    *,
    artifact_content: bytes = b"hello world",
    approved: bool = True,
    approved_by: str = "alice",
    approved_at: str | None = None,
    hash_override: str | None = None,
    extra_artifact_path: str | None = None,
    extra_artifact_hash: str | None = None,
) -> tuple[Path, Path]:
    """Create artifact + SIGNOFF.md draft; return (artifact_path, draft_path)."""
    from sdlc.signoff.hasher import compute_artifact_hash

    phase_dir = repo_root / _PHASE_DIR[phase]
    phase_dir.mkdir(parents=True, exist_ok=True)

    artifact = phase_dir / "PRODUCT.md"
    artifact.write_bytes(artifact_content)

    actual_hash = hash_override or compute_artifact_hash(artifact, repo_root=repo_root)
    approved_at_val = f'"{approved_at}"' if approved_at else "null"
    approved_by_val = f'"{approved_by}"' if approved_by else "null"

    art_lines = f'  - path: "{_PHASE_DIR[phase]}/PRODUCT.md"\n    hash: "{actual_hash}"'
    if extra_artifact_path and extra_artifact_hash:
        art_lines += f'\n  - path: "{extra_artifact_path}"\n    hash: "{extra_artifact_hash}"'

    draft = phase_dir / "SIGNOFF.md"
    # Do NOT use textwrap.dedent here — multi-line {art_lines} breaks dedent's
    # common-prefix calculation and produces malformed YAML frontmatter.
    draft.write_text(
        f"---\n"
        f"schema_version: 1\n"
        f"phase: {phase}\n"
        f"artifacts:\n"
        f"{art_lines}\n"
        f"approved: {str(approved).lower()}\n"
        f"approved_by: {approved_by_val}\n"
        f"approved_at: {approved_at_val}\n"
        f'drafted_at: "{_TS1}"\n'
        f"---\n",
        encoding="utf-8",
    )
    return artifact, draft


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_validate_signoff_happy_path(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState
    from sdlc.signoff.validator import validate_signoff

    _setup_phase(tmp_path, phase=1)
    result = validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)

    assert result.state == SignoffState.APPROVED
    assert result.drift == ()
    assert result.record.phase == 1
    assert result.record.approved_by == "alice"
    assert result.record.validated_at == _TS_NOW
    assert result.record.drafted_at == _TS1


def test_validate_signoff_sets_validated_at_to_now(tmp_path: Path) -> None:
    from sdlc.signoff.validator import validate_signoff

    _setup_phase(tmp_path, phase=1)
    result = validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)
    assert result.record.validated_at == _TS_NOW


def test_validate_signoff_uses_draft_approved_at_if_present(tmp_path: Path) -> None:
    from sdlc.signoff.validator import validate_signoff

    _setup_phase(tmp_path, phase=1, approved_at=_TS2)
    result = validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)
    assert result.record.approved_at == _TS2


def test_validate_signoff_falls_back_approved_at_to_now_utc(tmp_path: Path) -> None:
    """If draft approved_at is null, validate_signoff fills it with now_utc."""
    from sdlc.signoff.validator import validate_signoff

    _setup_phase(tmp_path, phase=1, approved_at=None)
    result = validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)
    assert result.record.approved_at == _TS_NOW


def test_validate_signoff_phase2_happy_path(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState
    from sdlc.signoff.validator import validate_signoff

    _setup_phase(tmp_path, phase=2)
    result = validate_signoff(phase=2, repo_root=tmp_path, now_utc=_TS_NOW)
    assert result.state == SignoffState.APPROVED


# ---------------------------------------------------------------------------
# Draft not approved
# ---------------------------------------------------------------------------


def test_validate_signoff_draft_not_approved_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    _setup_phase(tmp_path, phase=1, approved=False)
    with pytest.raises(SignoffError, match="not yet approved"):
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)


# ---------------------------------------------------------------------------
# Hash drift
# ---------------------------------------------------------------------------


def test_validate_signoff_artifact_drifted_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    artifact, _ = _setup_phase(tmp_path, phase=1)
    # Mutate artifact after draft was written
    artifact.write_bytes(b"tampered content")

    with pytest.raises(SignoffError, match="hash drift on artifact"):
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)


def test_validate_signoff_drift_error_has_kind_drifted(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    artifact, _ = _setup_phase(tmp_path, phase=1)
    artifact.write_bytes(b"tampered")

    with pytest.raises(SignoffError) as exc_info:
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)
    assert exc_info.value.details["kind"] == "drifted"


def test_validate_signoff_missing_artifact_raises(tmp_path: Path) -> None:
    """Artifact deleted between draft and approval → kind=missing."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    artifact, _ = _setup_phase(tmp_path, phase=1)
    artifact.unlink()

    with pytest.raises(SignoffError, match="hash drift on artifact"):
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)


def test_validate_signoff_missing_artifact_kind_is_missing(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    artifact, _ = _setup_phase(tmp_path, phase=1)
    artifact.unlink()

    with pytest.raises(SignoffError) as exc_info:
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)
    assert exc_info.value.details["kind"] == "missing"


def test_validate_signoff_tampered_hash_in_draft_raises(tmp_path: Path) -> None:
    """Hash in SIGNOFF.md is tampered (not matching disk) → drifted."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    # Write draft with wrong hash (zero hash) but real file has different content
    _setup_phase(tmp_path, phase=1, hash_override=_ZERO_HASH)

    with pytest.raises(SignoffError, match="hash drift on artifact"):
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)


def test_validate_signoff_tampered_hash_kind_is_drifted(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    _setup_phase(tmp_path, phase=1, hash_override=_ZERO_HASH)

    with pytest.raises(SignoffError) as exc_info:
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)
    assert exc_info.value.details["kind"] == "drifted"


# ---------------------------------------------------------------------------
# Deterministic first-drift (path-sorted)
# ---------------------------------------------------------------------------


def test_validate_signoff_first_drift_in_path_sorted_order(tmp_path: Path) -> None:
    """When multiple artifacts drift, the path-sorted first is raised."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.hasher import compute_artifact_hash
    from sdlc.signoff.validator import validate_signoff

    phase_dir = tmp_path / "01-Requirement"
    phase_dir.mkdir(parents=True)

    a_file = phase_dir / "AAA.md"
    b_file = phase_dir / "ZZZ.md"
    a_file.write_bytes(b"aaa content")
    b_file.write_bytes(b"zzz content")

    a_hash = compute_artifact_hash(a_file, repo_root=tmp_path)
    b_hash = compute_artifact_hash(b_file, repo_root=tmp_path)

    draft = phase_dir / "SIGNOFF.md"
    draft.write_text(
        f"---\n"
        f"schema_version: 1\n"
        f"phase: 1\n"
        f"artifacts:\n"
        f'  - path: "01-Requirement/ZZZ.md"\n'
        f'    hash: "{b_hash}"\n'
        f'  - path: "01-Requirement/AAA.md"\n'
        f'    hash: "{a_hash}"\n'
        f"approved: true\n"
        f'approved_by: "alice"\n'
        f"approved_at: null\n"
        f'drafted_at: "{_TS1}"\n'
        f"---\n",
        encoding="utf-8",
    )

    # Tamper both files
    a_file.write_bytes(b"aaa tampered")
    b_file.write_bytes(b"zzz tampered")

    with pytest.raises(SignoffError) as exc_info:
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)

    # Path-sorted first: AAA.md < ZZZ.md
    assert "AAA.md" in exc_info.value.details["artifact"]


# ---------------------------------------------------------------------------
# Cross-phase artifact rejection
# ---------------------------------------------------------------------------


def test_validate_signoff_cross_phase_artifact_raises(tmp_path: Path) -> None:
    """Phase-1 draft references 02-Architecture/... → raises."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    _setup_phase(
        tmp_path,
        phase=1,
        extra_artifact_path="02-Architecture/DESIGN.md",
        extra_artifact_hash=_VALID_HASH,
    )

    with pytest.raises(SignoffError, match="outside phase-1 tree"):
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)


# ---------------------------------------------------------------------------
# Phase 3 rejects unconditionally
# ---------------------------------------------------------------------------


def test_validate_signoff_phase3_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    with pytest.raises(SignoffError, match="phase 3 has no signoff"):
        validate_signoff(phase=3, repo_root=tmp_path, now_utc=_TS_NOW)


# ---------------------------------------------------------------------------
# No SIGNOFF.md draft → raises
# ---------------------------------------------------------------------------


def test_validate_signoff_missing_draft_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    with pytest.raises(SignoffError):
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)


# ---------------------------------------------------------------------------
# ValidatedSignoff + ArtifactDrift types
# ---------------------------------------------------------------------------


def test_validated_signoff_is_frozen() -> None:
    from sdlc.signoff.records import ArtifactRef, SignoffRecord
    from sdlc.signoff.states import SignoffState
    from sdlc.signoff.validator import ValidatedSignoff

    record = SignoffRecord(
        phase=1,
        artifacts=(ArtifactRef(path="01-Requirement/f.md", hash=_VALID_HASH),),
        approved_by="bob",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS_NOW,
    )
    vs = ValidatedSignoff(state=SignoffState.APPROVED, record=record, drift=())
    with pytest.raises((AttributeError, TypeError)):
        vs.state = SignoffState.AWAITING_SIGNOFF  # type: ignore[misc]


def test_artifact_drift_fields() -> None:
    from sdlc.signoff.validator import ArtifactDrift

    d = ArtifactDrift(
        path="01-Requirement/f.md",
        expected=_VALID_HASH,
        actual=_ZERO_HASH,
        kind="drifted",
    )
    assert d.path == "01-Requirement/f.md"
    assert d.kind == "drifted"
