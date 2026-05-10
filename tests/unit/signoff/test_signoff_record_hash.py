"""Unit tests for compute_signoff_record_hash (AC4, Story 2A.7)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_record() -> object:
    """Build a minimal valid SignoffRecord for tests."""
    from sdlc.signoff.records import ArtifactRef, SignoffRecord

    return SignoffRecord(
        phase=1,
        artifacts=(
            ArtifactRef(
                path="01-Requirement/PRODUCT.md",
                hash="sha256:" + "a" * 64,
            ),
        ),
        approved_by="alice",
        approved_at="2026-05-10T12:00:00.000Z",
        drafted_at="2026-05-10T11:00:00.000Z",
        validated_at="2026-05-10T12:01:00.000Z",
    )


def test_record_hash_is_stable(tmp_path: object) -> None:
    """Same record → same hash on two calls."""
    from sdlc.signoff.hasher import compute_signoff_record_hash

    record = _make_record()
    h1 = compute_signoff_record_hash(record)  # type: ignore[arg-type]
    h2 = compute_signoff_record_hash(record)  # type: ignore[arg-type]
    assert h1 == h2


def test_record_hash_changes_on_mutation() -> None:
    """Changing any field changes the hash."""
    from sdlc.signoff.hasher import compute_signoff_record_hash
    from sdlc.signoff.records import ArtifactRef, SignoffRecord

    record1 = _make_record()

    record2 = SignoffRecord(
        phase=2,  # changed
        artifacts=(
            ArtifactRef(
                path="01-Requirement/PRODUCT.md",
                hash="sha256:" + "a" * 64,
            ),
        ),
        approved_by="alice",
        approved_at="2026-05-10T12:00:00.000Z",
        drafted_at="2026-05-10T11:00:00.000Z",
        validated_at="2026-05-10T12:01:00.000Z",
    )

    assert compute_signoff_record_hash(record1) != compute_signoff_record_hash(record2)  # type: ignore[arg-type]


def test_record_hash_yaml_canonicalization() -> None:
    """Hash is derived from sorted-keys YAML — two identical records produce byte-equal YAML.

    Strengthened per P27 — explicitly assert that top-level keys appear in
    alphabetical order in the canonical bytes (removing ``sort_keys=True``
    would silently break this).
    """
    import yaml

    from sdlc.signoff.hasher import _canonicalize_record_bytes

    record = _make_record()
    canon1 = _canonicalize_record_bytes(record)  # type: ignore[arg-type]
    canon2 = _canonicalize_record_bytes(record)  # type: ignore[arg-type]
    assert canon1 == canon2

    # Verify it's valid YAML with sorted keys
    parsed = yaml.safe_load(canon1)
    assert isinstance(parsed, dict)

    # Anti-tautology: extract the top-level scalar keys from the raw bytes and
    # verify they are alphabetically ordered. Two consecutive non-indented lines
    # of form ``<key>:`` are the top-level keys of a single mapping.
    text = canon1.decode("utf-8")
    top_level_keys = [
        line.split(":", 1)[0]
        for line in text.splitlines()
        if line and not line.startswith(" ") and not line.startswith("-") and ":" in line
    ]
    assert top_level_keys == sorted(top_level_keys), (
        f"canonical YAML keys must be alphabetically sorted; got {top_level_keys!r}"
    )


def test_record_hash_format_matches_regex() -> None:
    """Hash output matches ^sha256:[0-9a-f]{64}$."""
    import re

    from sdlc.signoff.hasher import compute_signoff_record_hash

    record = _make_record()
    result = compute_signoff_record_hash(record)  # type: ignore[arg-type]
    assert re.fullmatch(r"^sha256:[0-9a-f]{64}$", result)
