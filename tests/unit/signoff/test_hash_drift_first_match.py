"""Unit test: first path-sorted drift is deterministically surfaced (AC8, Story 2A.7).

Running validate_signoff twice in a row on the same drifted repo returns the same
error — the operator always sees the same first artifact to fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_VALID_HASH = "sha256:" + "a" * 64
_TS1 = "2026-05-10T11:00:00.000Z"
_TS2 = "2026-05-10T12:00:00.000Z"
_TS_NOW = "2026-05-10T13:00:00.000Z"
_PHASE_DIR = "01-Requirement"


def _write_multi_artifact_draft(
    repo_root: Path,
    artifact_names: list[str],
    hashes: list[str],
    *,
    approved: bool = True,
) -> None:
    phase_dir = repo_root / _PHASE_DIR
    phase_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "schema_version: 1",
        "phase: 1",
        "artifacts:",
    ]
    for name, h in zip(artifact_names, hashes, strict=False):
        lines.append(f'  - path: "{_PHASE_DIR}/{name}"')
        lines.append(f'    hash: "{h}"')
    lines += [
        f"approved: {str(approved).lower()}",
        'approved_by: "alice"' if approved else "approved_by: null",
        f'approved_at: "{_TS2}"' if approved else "approved_at: null",
        f'drafted_at: "{_TS1}"',
        "---",
        "",
    ]
    (phase_dir / "SIGNOFF.md").write_text("\n".join(lines), encoding="utf-8")


def test_first_drift_is_path_sorted(tmp_path: Path) -> None:
    """When multiple artifacts drift, the path-sorted first is always surfaced."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.hasher import compute_artifact_hash
    from sdlc.signoff.validator import validate_signoff

    phase_dir = tmp_path / _PHASE_DIR
    phase_dir.mkdir(parents=True, exist_ok=True)

    # Create three files; list them in reverse alpha order in the draft
    for name, content in [("AAA.md", b"aaa"), ("MMM.md", b"mmm"), ("ZZZ.md", b"zzz")]:
        (phase_dir / name).write_bytes(content)

    hashes = {
        name: compute_artifact_hash(phase_dir / name, repo_root=tmp_path)
        for name in ["AAA.md", "MMM.md", "ZZZ.md"]
    }

    # Draft lists in reverse order to confirm sorting is not insertion-order
    _write_multi_artifact_draft(
        tmp_path,
        artifact_names=["ZZZ.md", "MMM.md", "AAA.md"],
        hashes=[hashes["ZZZ.md"], hashes["MMM.md"], hashes["AAA.md"]],
    )

    # Tamper all three
    for name in ["AAA.md", "MMM.md", "ZZZ.md"]:
        (phase_dir / name).write_bytes(b"tampered")

    # Both calls raise the same error
    with pytest.raises(SignoffError) as exc1:
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)
    with pytest.raises(SignoffError) as exc2:
        validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)

    # Path-sorted first: AAA.md
    assert "AAA.md" in exc1.value.details["artifact_path"]
    assert exc1.value.details["artifact_path"] == exc2.value.details["artifact_path"]


def test_first_drift_stable_across_calls(tmp_path: Path) -> None:
    """Two consecutive calls on the same drifted repo return the identical error path."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.hasher import compute_artifact_hash
    from sdlc.signoff.validator import validate_signoff

    phase_dir = tmp_path / _PHASE_DIR
    phase_dir.mkdir(parents=True, exist_ok=True)

    (phase_dir / "B_file.md").write_bytes(b"b content")
    (phase_dir / "A_file.md").write_bytes(b"a content")

    hashes = {
        n: compute_artifact_hash(phase_dir / n, repo_root=tmp_path)
        for n in ["A_file.md", "B_file.md"]
    }

    _write_multi_artifact_draft(
        tmp_path,
        artifact_names=["B_file.md", "A_file.md"],
        hashes=[hashes["B_file.md"], hashes["A_file.md"]],
    )

    # Tamper both
    (phase_dir / "A_file.md").write_bytes(b"tampered")
    (phase_dir / "B_file.md").write_bytes(b"tampered")

    errors = []
    for _ in range(3):
        with pytest.raises(SignoffError) as exc_info:
            validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS_NOW)
        errors.append(exc_info.value.details["artifact_path"])

    # All calls surface the same (path-sorted first) artifact
    assert len(set(errors)) == 1
    assert "A_file.md" in errors[0]
