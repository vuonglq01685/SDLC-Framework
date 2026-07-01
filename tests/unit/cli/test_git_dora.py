"""Unit tests for the DORA git-log reader (Story 5.13, D1).

`parse_dora_git_log` is pure, so commit classification (merge vs. non-merge)
and timestamp extraction are tested without invoking git. `git_dora_log`
degrades gracefully to `[]` on a non-git repo (mirrors Story 3.2's
`_git_recency.py::git_last_touched_days`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.cli._git_dora import _FIELD_SEP, git_dora_log, parse_dora_git_log

pytestmark = pytest.mark.unit


def _line(parents: str, author_iso: str, commit_iso: str) -> str:
    return f"{parents}{_FIELD_SEP}{author_iso}{_FIELD_SEP}{commit_iso}"


def test_parse_single_non_merge_commit() -> None:
    stdout = _line("aaaaaaa", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00")
    result = parse_dora_git_log(stdout)
    assert result == [("2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00", False)]


def test_parse_merge_commit_has_two_parents() -> None:
    stdout = _line("aaaaaaa bbbbbbb", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00")
    result = parse_dora_git_log(stdout)
    assert result[0][2] is True


def test_parse_root_commit_has_no_parents() -> None:
    """A commit with zero parents (%P empty) is not a merge."""
    stdout = _line("", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00")
    result = parse_dora_git_log(stdout)
    assert result[0][2] is False


def test_parse_multiple_commits_in_order() -> None:
    stdout = "\n".join(
        [
            _line("aaaaaaa", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00"),
            _line("bbbbbbb ccccccc", "2026-06-02T10:00:00+00:00", "2026-06-02T12:00:00+00:00"),
        ]
    )
    result = parse_dora_git_log(stdout)
    assert len(result) == 2
    assert result[0][2] is False
    assert result[1][2] is True


def test_parse_ignores_blank_lines() -> None:
    stdout = "\n".join(
        [
            "",
            _line("aaaaaaa", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00"),
            "",
        ]
    )
    assert len(parse_dora_git_log(stdout)) == 1


def test_parse_empty_output_is_empty_list() -> None:
    assert parse_dora_git_log("") == []


def test_parse_skips_line_with_wrong_field_count() -> None:
    stdout = "only-one-field"
    assert parse_dora_git_log(stdout) == []


def test_parse_skips_unparsable_timestamps() -> None:
    stdout = _line("aaaaaaa", "not-a-date", "also-not-a-date")
    assert parse_dora_git_log(stdout) == []


def test_parse_handles_naive_commit_date() -> None:
    """A timestamp with no tz (defensive) is treated as UTC, not crashed on."""
    stdout = _line("aaaaaaa", "2026-06-01T10:00:00", "2026-06-01T12:00:00")
    result = parse_dora_git_log(stdout)
    assert result[0][0] == "2026-06-01T10:00:00+00:00"
    assert result[0][1] == "2026-06-01T12:00:00+00:00"


def test_git_dora_log_on_non_git_dir_returns_empty(tmp_path: Path) -> None:
    """A directory that is not a git repo → graceful empty list (D1)."""
    assert git_dora_log(tmp_path) == []
