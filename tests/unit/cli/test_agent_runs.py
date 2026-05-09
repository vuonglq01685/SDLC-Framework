"""Unit tests for sdlc.cli._agent_runs (Story 1.18.1, AC2).

B-P16: monkeypatch Path.open → FileNotFoundError yields empty iterator.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_iter_agent_runs_missing_file_returns_empty(tmp_path: Path) -> None:
    """Missing file → empty iterator (no exception)."""
    from sdlc.cli._agent_runs import iter_agent_runs

    result = list(iter_agent_runs(tmp_path / "nonexistent.jsonl"))
    assert result == []


def test_iter_agent_runs_file_not_found_via_monkeypatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-P16: when Path.open raises FileNotFoundError, iter_agent_runs returns empty iterator.

    Exercises the TOCTOU path where the file vanishes between exists-check and open.
    """
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("")  # create so Path exists but open is mocked

    from sdlc.cli._agent_runs import iter_agent_runs

    original_open = Path.open

    def _raise_fnf(self: Path, *args: object, **kwargs: object) -> object:
        if self == runs:
            raise FileNotFoundError(f"vanished: {self}")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _raise_fnf)

    result = list(iter_agent_runs(runs))
    assert result == []


def test_iter_agent_runs_yields_valid_records(tmp_path: Path) -> None:
    """Valid JSONL records are yielded as dicts."""
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "impl"})
        + "\n"
        + json.dumps({"ts": "2026-01-01T00:00:01Z", "agent": "reviewer"})
        + "\n"
    )
    from sdlc.cli._agent_runs import iter_agent_runs

    records = list(iter_agent_runs(runs))
    assert len(records) == 2
    assert records[0]["agent"] == "impl"
    assert records[1]["agent"] == "reviewer"


def test_iter_agent_runs_skips_blank_lines(tmp_path: Path) -> None:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("\n" + json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x"}) + "\n\n")
    from sdlc.cli._agent_runs import iter_agent_runs

    records = list(iter_agent_runs(runs))
    assert len(records) == 1


def test_iter_agent_runs_warns_on_malformed_json(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("NOT JSON\n" + json.dumps({"ts": "2026-01-01T00:00:00Z"}) + "\n")
    from sdlc.cli._agent_runs import iter_agent_runs

    with caplog.at_level(logging.WARNING):
        records = list(iter_agent_runs(runs))

    assert len(records) == 1
    assert "malformed agent_runs line" in caplog.text


def test_iter_agent_runs_warns_on_non_dict_json(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("[1, 2, 3]\n" + json.dumps({"ts": "2026-01-01T00:00:00Z"}) + "\n")
    from sdlc.cli._agent_runs import iter_agent_runs

    with caplog.at_level(logging.WARNING):
        records = list(iter_agent_runs(runs))

    assert len(records) == 1
    assert "non-object agent_runs line" in caplog.text


def test_iter_agent_runs_oserror_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-FileNotFoundError OSError is re-raised."""
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text("")

    original_open = Path.open

    def _raise_oserr(self: Path, *args: object, **kwargs: object) -> object:
        if self == runs:
            raise PermissionError(f"permission denied: {self}")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _raise_oserr)

    from sdlc.cli._agent_runs import iter_agent_runs

    with pytest.raises(OSError, match="agent_runs read failed"):
        list(iter_agent_runs(runs))
