"""Unit tests for ``telemetry.runs.iter_agent_run_records`` (Story 5.16 Task 1).

Mirrors ``tests/unit/cli/test_agent_runs.py`` (the reader this seam was lifted
alongside — see Dev Notes D4): missing file -> empty iterator; malformed JSON
line -> WARNING + skip; non-object line -> WARNING + skip; other OSError
propagates. Added coverage here is direct (Story 5.13 introduced
``iter_agent_run_records`` for ``telemetry/dora.py`` but exercised it only
indirectly through ``compute_dora_window``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_iter_agent_run_records_missing_file_returns_empty(tmp_path: Path) -> None:
    from sdlc.telemetry.runs import iter_agent_run_records

    result = list(iter_agent_run_records(tmp_path / "nonexistent.jsonl"))
    assert result == []


def test_iter_agent_run_records_yields_valid_records(tmp_path: Path) -> None:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "run_id": "a"})
        + "\n"
        + json.dumps({"ts": "2026-01-01T00:00:01Z", "run_id": "b"})
        + "\n"
    )
    from sdlc.telemetry.runs import iter_agent_run_records

    records = list(iter_agent_run_records(runs))
    assert len(records) == 2
    assert records[0]["run_id"] == "a"
    assert records[1]["run_id"] == "b"


def test_iter_agent_run_records_skips_blank_lines(tmp_path: Path) -> None:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("\n" + json.dumps({"ts": "2026-01-01T00:00:00Z", "run_id": "a"}) + "\n\n")
    from sdlc.telemetry.runs import iter_agent_run_records

    records = list(iter_agent_run_records(runs))
    assert len(records) == 1


def test_iter_agent_run_records_warns_and_skips_malformed_json(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("NOT JSON\n" + json.dumps({"ts": "2026-01-01T00:00:00Z", "run_id": "a"}) + "\n")
    from sdlc.telemetry.runs import iter_agent_run_records

    with caplog.at_level(logging.WARNING):
        records = list(iter_agent_run_records(runs))

    assert len(records) == 1
    assert "malformed agent_runs line" in caplog.text


def test_iter_agent_run_records_warns_and_skips_non_dict_json(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text(
        "[1, 2, 3]\n" + json.dumps({"ts": "2026-01-01T00:00:00Z", "run_id": "a"}) + "\n"
    )
    from sdlc.telemetry.runs import iter_agent_run_records

    with caplog.at_level(logging.WARNING):
        records = list(iter_agent_run_records(runs))

    assert len(records) == 1
    assert "non-object agent_runs line" in caplog.text


def test_iter_agent_run_records_truncated_last_line_skipped_not_crashed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A partial/truncated trailing line (process killed mid-write) is skipped, not raised."""
    runs = tmp_path / "agent_runs.jsonl"
    good = json.dumps({"ts": "2026-01-01T00:00:00Z", "run_id": "a"})
    runs.write_text(good + "\n" + '{"ts": "2026-01-01T00:00:01Z", "run_id": "trun')
    from sdlc.telemetry.runs import iter_agent_run_records

    with caplog.at_level(logging.WARNING):
        records = list(iter_agent_run_records(runs))

    assert len(records) == 1
    assert records[0]["run_id"] == "a"


def test_iter_agent_run_records_undecodable_byte_replaced_not_raised(tmp_path: Path) -> None:
    """Hardening beyond cli/_agent_runs.py: opened with errors='replace' (code-review P1)."""
    runs = tmp_path / "agent_runs.jsonl"
    good = json.dumps({"ts": "2026-01-01T00:00:00Z", "run_id": "a"}).encode("utf-8")
    runs.write_bytes(good + b"\n\xff\xfe not valid utf-8\n")
    from sdlc.telemetry.runs import iter_agent_run_records

    records = list(iter_agent_run_records(runs))
    assert len(records) == 1
    assert records[0]["run_id"] == "a"


def test_iter_agent_run_records_oserror_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("")

    original_open = Path.open

    def _raise_oserr(self: Path, *args: object, **kwargs: object) -> object:
        if self == runs:
            raise PermissionError(f"permission denied: {self}")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _raise_oserr)

    from sdlc.telemetry.runs import iter_agent_run_records

    with pytest.raises(OSError, match="agent_runs read failed"):
        list(iter_agent_run_records(runs))
