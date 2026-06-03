"""Git-history recency signal for adopt Pass 1 (Story 3.2, D2 dependency-injection).

`adopt/` has no git grant and must not import `cli/` (architecture.md:1084), so the
90-day recency signal (AC3) is computed HERE — in the `cli` layer, which already holds
the git subprocess grant (`cli/_paths.py`) — and dependency-injected into
`detect_existing(root, *, git_signal=...)`. This mirrors Story 3.8's pattern of reading
config in `cli` and injecting it into a pure boundary-respecting core
(`cli/break_.py` → `cli/_brownfield.classify_tdd_strategy`).

The signal is a `{repo_relative_posix_path: days_since_last_commit_touch}` map built from
a single `git log` traversal (newest commit wins per path). It degrades gracefully
(AC3): a non-git repo, missing git binary, timeout, non-zero exit, or parse error yields
an empty map, and detection proceeds with no recency boost.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

# A unit-separator-delimited prefix so a commit-date line can never be confused with a
# file path (git paths cannot contain \x1f). `--name-only` lists touched paths per commit.
_COMMIT_PREFIX: Final[str] = "\x1fCOMMIT\x1f"
_GIT_TIMEOUT_SECONDS: Final[float] = 5.0


def _now_utc() -> datetime:
    """Current UTC time (isolated for test injection via `parse_git_log`)."""
    return datetime.now(timezone.utc)


def _try_parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 commit date (`%cI`); return None if it is not a valid date."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_git_log(stdout: str, now: datetime) -> dict[str, int]:
    """Parse `git log --pretty=format:<prefix>%cI --name-only` output into a recency map.

    Newest commit wins (git log is newest-first), so the first time a path is seen its
    `days_since` is recorded and later (older) occurrences are ignored. Pure + deterministic
    given `now`, so it is unit-testable without invoking git.
    """
    out: dict[str, int] = {}
    current_days: int | None = None
    for raw in stdout.splitlines():
        if raw.startswith(_COMMIT_PREFIX):
            parsed = _try_parse_iso(raw[len(_COMMIT_PREFIX) :])
            if parsed is not None:
                current_days = max(0, (now - parsed).days)
            continue
        path = raw.strip()
        if path and current_days is not None and path not in out:
            out[path] = current_days
    return out


def git_last_touched_days(root: Path) -> dict[str, int]:
    """Return `{repo_relative_posix_path: days_since_last_touch}` for tracked files.

    Degrades gracefully to `{}` on any git failure (AC3) — detection then applies no
    recency boost.
    """
    try:
        result = subprocess.run(
            ["git", "log", f"--pretty=format:{_COMMIT_PREFIX}%cI", "--name-only", "--no-renames"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            cwd=root,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    return parse_git_log(result.stdout, _now_utc())
