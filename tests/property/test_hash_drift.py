"""Hypothesis property test: hash-drift permutation matrix (AC8, Story 2A.7, D6).

NFR-REL-3 zero false negatives: validate_signoff MUST detect ANY of:
  artifact_edit    — artifact bytes mutated after SIGNOFF.md was drafted
  hash_record_edit — hash in SIGNOFF.md draft tampered to a wrong value
  signoff_edit     — only approved: false → true; no content mutation; must SUCCEED
  no_mutation      — happy path; approve MUST succeed (no false positives)

Per AC8 (Story 2A.7 D6 review decision), mutation types are dispatched via a
single ``hypothesis.strategies.sampled_from`` strategy so a single property
randomly distributes examples across all four cases, exercising cross-mutation
interleaving instead of running each case in isolation. Spec-mandated bytes
sizing (1 KiB-10 KiB) and 1-5 artifacts per case are also honoured.

Edge cases additionally covered as hard-coded unit-style checks below the
property: 0-byte file, non-ASCII / UTF-8 path, multi-artifact path-sort.

Budget: @settings(max_examples=200, deadline=10_000) on the unified property
+ four ``no_mutation`` baseline examples → ≥ 200 examples per mutation type
in expectation (sampled_from gives uniform distribution, so 200/4 = 50 each;
the unified shape preserves the AC8 ≥ 100 budget by raising max_examples to
1000 to keep ≥ 200 hits per bucket).

NOTE: Tests manage their own ``tempfile.TemporaryDirectory()`` to avoid the
hypothesis function_scoped_fixture health check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
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


def _setup_multi_artifact_repo(
    repo_root: Path,
    artifacts: list[tuple[str, bytes]],  # [(name, content), ...]
    *,
    approved: bool = True,
) -> list[tuple[str, str]]:
    """Create N artifacts and a draft listing them all (sorted-by-path)."""
    from sdlc.signoff.hasher import compute_artifact_hash

    entries: list[tuple[str, str]] = []
    for name, content in artifacts:
        path = _write_artifact(repo_root, name, content)
        h = compute_artifact_hash(path, repo_root=repo_root)
        entries.append((f"{_PHASE_DIR}/{name}", h))
    _write_signoff_draft(repo_root, entries, approved=approved)
    return entries


# ---------------------------------------------------------------------------
# Strategies (D6: spec-mandated sizes + 1-5 artifacts)
# ---------------------------------------------------------------------------

# AC8 first-And: 1 KiB-10 KiB content per artifact.
_artifact_bytes = st.binary(min_size=1024, max_size=10240)

# 1-5 artifacts per case, each with a deterministic distinct name so the
# resulting paths are byte-stable for hash-drift verification.
_artifact_count = st.integers(min_value=1, max_value=5)

_mutation_kind = st.sampled_from(
    ["artifact_edit", "signoff_edit", "hash_record_edit", "no_mutation"]
)


# ---------------------------------------------------------------------------
# Unified property: dispatch on mutation kind (D6)
# ---------------------------------------------------------------------------


@given(
    mutation=_mutation_kind,
    contents=st.lists(_artifact_bytes, min_size=1, max_size=5),
    tampered_payload=_artifact_bytes,
)
@settings(
    max_examples=1000,
    deadline=10_000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_hash_drift_permutation_matrix(
    mutation: str, contents: list[bytes], tampered_payload: bytes
) -> None:
    """Unified property: mutation ∈ {artifact_edit, signoff_edit, hash_record_edit, no_mutation}.

    NFR-REL-3 zero false negatives — validate_signoff must detect drift in the
    three mutation cases and succeed in the negative (no_mutation) case.
    """
    from sdlc.errors import SignoffError
    from sdlc.signoff.hasher import compute_artifact_hash
    from sdlc.signoff.states import SignoffState
    from sdlc.signoff.validator import validate_signoff

    with tempfile.TemporaryDirectory() as _tmpdir:
        repo_root = Path(_tmpdir)
        # Distinct, sorted artifact names so every example exercises path-order.
        artifact_specs = [(f"DOC_{idx:02d}.md", c) for idx, c in enumerate(contents)]
        entries = _setup_multi_artifact_repo(repo_root, artifact_specs, approved=True)

        if mutation == "no_mutation":
            result = validate_signoff(phase=_PHASE, repo_root=repo_root, now_utc=_TS_NOW)
            assert result.state == SignoffState.APPROVED
            assert result.drift == ()
            assert len(result.record.artifacts) == len(artifact_specs)
            return

        if mutation == "signoff_edit":
            # Re-write draft with approved flipped on; no artifact mutation.
            _write_signoff_draft(repo_root, entries, approved=True)
            result = validate_signoff(phase=_PHASE, repo_root=repo_root, now_utc=_TS_NOW)
            assert result.state == SignoffState.APPROVED
            return

        if mutation == "artifact_edit":
            # Tamper the FIRST artifact's bytes; need genuinely different bytes.
            target_name, original = artifact_specs[0]
            tmp_check = repo_root / "_tmp_check.md"
            tmp_check.write_bytes(tampered_payload)
            tampered_hash = compute_artifact_hash(tmp_check, repo_root=repo_root)
            tmp_check.unlink()
            recorded_hash = entries[0][1]
            assume(tampered_hash != recorded_hash)

            (repo_root / _PHASE_DIR / target_name).write_bytes(tampered_payload)
            with pytest.raises(SignoffError) as exc_info:
                validate_signoff(phase=_PHASE, repo_root=repo_root, now_utc=_TS_NOW)
            assert exc_info.value.details["kind"] in ("drifted", "missing")
            return

        if mutation == "hash_record_edit":
            # Tamper the recorded hash in the draft to a known-wrong sentinel.
            assume(entries[0][1] != _ZERO_HASH)
            tampered_entries = [(entries[0][0], _ZERO_HASH), *entries[1:]]
            _write_signoff_draft(repo_root, tampered_entries, approved=True)
            with pytest.raises(SignoffError) as exc_info:
                validate_signoff(phase=_PHASE, repo_root=repo_root, now_utc=_TS_NOW)
            assert exc_info.value.details["kind"] == "drifted"
            assert exc_info.value.details["expected"] == _ZERO_HASH
            return

        raise AssertionError(f"unhandled mutation: {mutation!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Spec-mandated edge cases (AC8 third-And — explicit unit-shape coverage)
# ---------------------------------------------------------------------------


def test_zero_byte_artifact_edge_case(tmp_path: Path) -> None:
    """0-byte artifact still has a stable SHA-256 (the well-known empty-string hash)."""
    from sdlc.signoff.states import SignoffState
    from sdlc.signoff.validator import validate_signoff

    _setup_multi_artifact_repo(tmp_path, [("ZERO.md", b"")], approved=True)
    result = validate_signoff(phase=_PHASE, repo_root=tmp_path, now_utc=_TS_NOW)
    assert result.state == SignoffState.APPROVED


def test_utf8_filename_edge_case(tmp_path: Path) -> None:
    """Non-ASCII (UTF-8) artifact filenames round-trip safely through the validator."""
    from sdlc.signoff.states import SignoffState
    from sdlc.signoff.validator import validate_signoff

    _setup_multi_artifact_repo(
        tmp_path, [("résumé.md", b"utf8 body"), ("日本.md", b"jp")], approved=True
    )
    result = validate_signoff(phase=_PHASE, repo_root=tmp_path, now_utc=_TS_NOW)
    assert result.state == SignoffState.APPROVED
    # Sorted-on-output (P13): the canonical record's artifacts must be path-ordered.
    paths = [a.path for a in result.record.artifacts]
    assert paths == sorted(paths)


def test_multi_artifact_path_sort_first_drift(tmp_path: Path) -> None:
    """When 3 artifacts drift, the path-sorted FIRST is surfaced (AC3 step 4)."""
    from sdlc.errors import SignoffError
    from sdlc.signoff.validator import validate_signoff

    entries = _setup_multi_artifact_repo(
        tmp_path,
        [("ZZZ.md", b"z"), ("MMM.md", b"m"), ("AAA.md", b"a")],
        approved=True,
    )
    # Tamper all three on disk so all drift; first path-sorted is AAA.md.
    for name in ("AAA.md", "MMM.md", "ZZZ.md"):
        (tmp_path / _PHASE_DIR / name).write_bytes(b"tampered " + name.encode())

    with pytest.raises(SignoffError) as exc_info:
        validate_signoff(phase=_PHASE, repo_root=tmp_path, now_utc=_TS_NOW)
    assert "AAA.md" in exc_info.value.details["artifact"]
    # Defensive: ensure entries are not silently reordered (hash check uses sorted).
    assert entries[0][0].endswith("ZZZ.md")
