"""Unit tests for the adopt git-recency signal helper (Story 3.2, D2).

`parse_git_log` is pure (given `now`), so the recency math is tested without invoking git.
`git_last_touched_days` degrades gracefully to `{}` on a non-git repo (AC3).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sdlc.cli._git_recency import _COMMIT_PREFIX, git_last_touched_days, parse_git_log

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 6, 3, tzinfo=timezone.utc)


def _commit_line(iso: str) -> str:
    return f"{_COMMIT_PREFIX}{iso}"


def test_parse_records_days_since_per_path() -> None:
    stdout = "\n".join(
        [
            _commit_line("2026-06-01T00:00:00+00:00"),  # exactly 2 days before _NOW
            "docs/arch.md",
            "README.md",
        ]
    )
    result = parse_git_log(stdout, _NOW)
    assert result == {"docs/arch.md": 2, "README.md": 2}


def test_parse_newest_commit_wins_per_path() -> None:
    """A path touched in multiple commits keeps the newest (smallest days_since)."""
    stdout = "\n".join(
        [
            _commit_line("2026-06-02T00:00:00+00:00"),  # 1 day ago (newest)
            "docs/arch.md",
            _commit_line("2026-01-01T00:00:00+00:00"),  # ~153 days ago (older)
            "docs/arch.md",
            "old-only.md",
        ]
    )
    result = parse_git_log(stdout, _NOW)
    assert result["docs/arch.md"] == 1  # newest wins
    assert result["old-only.md"] > 90  # only in the old commit


def test_parse_ignores_blank_lines() -> None:
    stdout = "\n".join(
        [
            _commit_line("2026-06-01T00:00:00+00:00"),
            "",
            "pom.xml",
            "",
        ]
    )
    assert parse_git_log(stdout, _NOW) == {"pom.xml": 2}


def test_parse_empty_output_is_empty_map() -> None:
    assert parse_git_log("", _NOW) == {}


def test_parse_handles_naive_commit_date() -> None:
    """A `%cI` with no tz (defensive) is treated as UTC, not crashed on."""
    stdout = "\n".join([_commit_line("2026-06-01T00:00:00"), "README.md"])
    result = parse_git_log(stdout, _NOW)
    assert result == {"README.md": 2}


def test_git_last_touched_days_on_non_git_dir_returns_empty(tmp_path: Path) -> None:
    """A directory that is not a git repo → graceful empty map (AC3)."""
    # tmp_path has no .git → `git log` exits non-zero → {}.
    assert git_last_touched_days(tmp_path) == {}
