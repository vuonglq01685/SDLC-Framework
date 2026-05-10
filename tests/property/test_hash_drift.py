"""Hypothesis property test: hash-drift permutation matrix (AC8, Story 2A.7).

NFR-REL-3 zero false negatives: validate_signoff MUST detect ANY of:
  artifact_edit    — artifact bytes mutated after SIGNOFF.md was drafted
  hash_record_edit — hash in SIGNOFF.md draft tampered to a wrong value
  no_mutation      — happy path; approve MUST succeed (no false positives)
  signoff_edit     — only approved: false → true; no content mutation; must SUCCEED

Budget: @settings(max_examples=200, deadline=5000) per @given.
Four @given suites x 200 examples = 800 total test cases.

NOTE: Tests manage their own tempfile.TemporaryDirectory() to avoid hypothesis
function_scoped_fixture health check (hypothesis does not reset pytest fixtures
between examples).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = pytest.mark.property

_TS_NOW = "2026-05-10T13:00:00.000Z"
_TS1 = "2026-05-10T11:00:00.000Z"
_TS2 = "2026-05-10T12:00:00.000Z"
_PHASE = 1
_PHASE_DIR = "01-Requirement"
_ZERO_HASH = "sha256:" + "0" * 64

# ---------------------------------------------------------------------------
# Helpers (NOT exported — property-test-only, per story Task 5.2)
# ---------------------------------------------------------------------------


def _write_artifact(repo_root: Path, name: str, content: bytes) -> Path:
    phase_dir = repo_root / _PHASE_DIR
    phase_dir.mkdir(parents=True, exist_ok=True)
    p = phase_dir / name
    p.write_bytes(content)
    return p


def _write_signoff_draft(
    repo_root: Path,
    artifacts: list[tuple[str, str]],  # [(repo_rel_path, hash), ...]
    *,
    approved: bool = False,
) -> Path:
    lines = [
        "---",
        "schema_version: 1",
        f"phase: {_PHASE}",
        "artifacts:",
    ]
    for path, h in artifacts:
        lines.append(f'  - path: "{path}"')
        lines.append(f'    hash: "{h}"')
    lines += [
        f"approved: {str(approved).lower()}",
        'approved_by: "alice"' if approved else "approved_by: null",
        f'approved_at: "{_TS2}"' if approved else "approved_at: null",
        f'drafted_at: "{_TS1}"',
        "---",
        "",
    ]
    draft_path = repo_root / _PHASE_DIR / "SIGNOFF.md"
    draft_path.write_text("\n".join(lines), encoding="utf-8")
    return draft_path


def _setup_repo(
    repo_root: Path,
    artifact_bytes: bytes,
    *,
    approved: bool = False,
) -> tuple[Path, str]:
    """Create one artifact + draft; return (artifact_path, recorded_hash)."""
    from sdlc.signoff.hasher import compute_artifact_hash

    artifact = _write_artifact(repo_root, "PRODUCT.md", artifact_bytes)
    recorded_hash = compute_artifact_hash(artifact, repo_root=repo_root)
    _write_signoff_draft(
        repo_root,
        [(f"{_PHASE_DIR}/PRODUCT.md", recorded_hash)],
        approved=approved,
    )
    return artifact, recorded_hash


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_non_empty_bytes = st.binary(min_size=1, max_size=4096)


# ---------------------------------------------------------------------------
# Property 1 — artifact_edit: mutating artifact bytes MUST raise drift error
# ---------------------------------------------------------------------------


@given(original=_non_empty_bytes, tampered=_non_empty_bytes)
@settings(max_examples=200, deadline=5000, suppress_health_check=[HealthCheck.too_slow])
def test_artifact_edit_always_detected(original: bytes, tampered: bytes) -> None:
    """Any byte mutation of the artifact (when hash differs) triggers drift detection."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.hasher import compute_artifact_hash
    from sdlc.signoff.validator import validate_signoff

    with tempfile.TemporaryDirectory() as _tmpdir:
        repo_root = Path(_tmpdir)
        artifact, recorded_hash = _setup_repo(repo_root, original, approved=True)

        # Compute hash of tampered bytes
        tmp_check = repo_root / "_tmp_check.md"
        tmp_check.write_bytes(tampered)
        tampered_hash = compute_artifact_hash(tmp_check, repo_root=repo_root)
        tmp_check.unlink()

        if tampered_hash == recorded_hash:
            # Same content (or collision) — no drift; skip
            return

        # Overwrite artifact with tampered content
        artifact.write_bytes(tampered)

        with pytest.raises(SignoffError) as exc_info:
            validate_signoff(phase=_PHASE, repo_root=repo_root, now_utc=_TS_NOW)

        assert exc_info.value.details["kind"] in ("drifted", "missing")


# ---------------------------------------------------------------------------
# Property 2 — signoff_edit: only approved flag change MUST succeed
# ---------------------------------------------------------------------------


@given(content=_non_empty_bytes)
@settings(max_examples=200, deadline=5000, suppress_health_check=[HealthCheck.too_slow])
def test_signoff_edit_no_drift_succeeds(content: bytes) -> None:
    """Approving a draft without touching artifacts must always succeed."""
    from sdlc.signoff.states import SignoffState
    from sdlc.signoff.validator import validate_signoff

    with tempfile.TemporaryDirectory() as _tmpdir:
        repo_root = Path(_tmpdir)
        _setup_repo(repo_root, content, approved=True)
        result = validate_signoff(phase=_PHASE, repo_root=repo_root, now_utc=_TS_NOW)
        assert result.state == SignoffState.APPROVED
        assert result.drift == ()


# ---------------------------------------------------------------------------
# Property 3 — hash_record_edit: tampered hash in draft MUST raise drift error
# ---------------------------------------------------------------------------


@given(content=_non_empty_bytes)
@settings(max_examples=200, deadline=5000, suppress_health_check=[HealthCheck.too_slow])
def test_hash_record_edit_always_detected(content: bytes) -> None:
    """Tampered hash value in SIGNOFF.md draft always triggers drift detection."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.hasher import compute_artifact_hash
    from sdlc.signoff.validator import validate_signoff

    with tempfile.TemporaryDirectory() as _tmpdir:
        repo_root = Path(_tmpdir)
        artifact = _write_artifact(repo_root, "PRODUCT.md", content)
        real_hash = compute_artifact_hash(artifact, repo_root=repo_root)

        if real_hash == _ZERO_HASH:
            return  # pathological case — skip

        # Draft with zero hash but real artifact on disk
        _write_signoff_draft(
            repo_root,
            [(f"{_PHASE_DIR}/PRODUCT.md", _ZERO_HASH)],
            approved=True,
        )

        with pytest.raises(SignoffError) as exc_info:
            validate_signoff(phase=_PHASE, repo_root=repo_root, now_utc=_TS_NOW)

        assert exc_info.value.details["kind"] == "drifted"
        assert exc_info.value.details["expected"] == _ZERO_HASH


# ---------------------------------------------------------------------------
# Property 4 — no_mutation: unchanged artifact + approved draft MUST succeed
# ---------------------------------------------------------------------------


@given(content=_non_empty_bytes)
@settings(max_examples=200, deadline=5000, suppress_health_check=[HealthCheck.too_slow])
def test_no_mutation_always_approves(content: bytes) -> None:
    """No mutation + approved draft always returns ValidatedSignoff(APPROVED)."""
    from sdlc.signoff.states import SignoffState
    from sdlc.signoff.validator import validate_signoff

    with tempfile.TemporaryDirectory() as _tmpdir:
        repo_root = Path(_tmpdir)
        _setup_repo(repo_root, content, approved=True)
        result = validate_signoff(phase=_PHASE, repo_root=repo_root, now_utc=_TS_NOW)
        assert result.state == SignoffState.APPROVED
        assert result.drift == ()
        assert result.record.phase == _PHASE
