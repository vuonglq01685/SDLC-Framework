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
