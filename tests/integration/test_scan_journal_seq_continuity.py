"""Integration tests: sdlc scan journal seq chain invariants (Story 1.17 AC3.3)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_SKIP_NO_UV = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv not on PATH",
)
_SKIP_WIN32 = pytest.mark.skipif(
    sys.platform == "win32",
    reason="journal.append_sync is POSIX-only; journal continuity tests skipped on Windows",
)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _parse_journal_entries(journal_path: Path) -> list[dict]:
    entries = []
    for raw in journal_path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped:
            entries.append(json.loads(stripped))
    return entries


@_SKIP_NO_UV
@_SKIP_WIN32
def test_first_scan_appends_seq_zero(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    _run(["sdlc", "scan"], tmp_path)
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entries = _parse_journal_entries(journal_path)
    assert len(entries) == 1
    assert entries[0]["monotonic_seq"] == 0


@_SKIP_NO_UV
@_SKIP_WIN32
def test_second_scan_appends_seq_one(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    _run(["sdlc", "scan"], tmp_path)
    _run(["sdlc", "scan"], tmp_path)
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entries = _parse_journal_entries(journal_path)
    assert len(entries) == 2
    seqs = [e["monotonic_seq"] for e in entries]
    assert seqs == [0, 1]


@_SKIP_NO_UV
@_SKIP_WIN32
def test_scan_journal_entries_have_required_fields(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    _run(["sdlc", "scan"], tmp_path)
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entries = _parse_journal_entries(journal_path)
    entry = entries[0]
    required = {"schema_version", "monotonic_seq", "ts", "actor", "kind", "target_id", "payload"}
    assert required.issubset(entry.keys()), f"Missing fields: {required - entry.keys()}"
    assert entry["actor"] == "cli"
    assert entry["kind"] == "scan_completed"
    assert entry["target_id"] == "state"


@_SKIP_NO_UV
@_SKIP_WIN32
def test_scan_journal_ts_is_rfc3339_utc(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    _run(["sdlc", "scan"], tmp_path)
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entries = _parse_journal_entries(journal_path)
    ts = entries[0]["ts"]
    # RFC 3339 UTC: ends with Z or +00:00
    assert ts.endswith("Z") or ts.endswith("+00:00"), f"ts not RFC3339 UTC: {ts!r}"


@_SKIP_NO_UV
@_SKIP_WIN32
def test_scan_state_json_next_monotonic_seq_increments(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    state_path = tmp_path / ".claude" / "state" / "state.json"

    seq_before = json.loads(state_path.read_bytes())["next_monotonic_seq"]
    _run(["sdlc", "scan"], tmp_path)
    seq_after = json.loads(state_path.read_bytes())["next_monotonic_seq"]

    assert seq_after == seq_before + 1


@_SKIP_NO_UV
@_SKIP_WIN32
def test_journal_entry_referential_integrity(tmp_path: Path) -> None:
    """AC7.7 — chain-of-hashes invariant: each entry's `before_hash` equals the
    `after_hash` of the entry whose seq is one less. Entry seq=0's before_hash
    matches sha256 of the post-init state.json bytes.
    """
    import hashlib

    _run(["sdlc", "init"], tmp_path)
    state_path = tmp_path / ".claude" / "state" / "state.json"
    post_init_bytes = state_path.read_bytes()
    expected_seq0_before = f"sha256:{hashlib.sha256(post_init_bytes).hexdigest()}"

    _run(["sdlc", "scan"], tmp_path)
    _run(["sdlc", "scan"], tmp_path)

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entries = _parse_journal_entries(journal_path)
    assert len(entries) == 2
    by_seq = {e["monotonic_seq"]: e for e in entries}

    # Entry 0's before_hash points at the post-init state bytes.
    assert by_seq[0]["before_hash"] == expected_seq0_before
    # Entry 1's before_hash equals entry 0's after_hash (chain).
    assert by_seq[1]["before_hash"] == by_seq[0]["after_hash"]
    # Both after_hash values follow the canonical sha256 envelope.
    for entry in entries:
        ah = entry["after_hash"]
        assert isinstance(ah, str) and ah.startswith("sha256:") and len(ah) == 71
