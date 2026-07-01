"""Git-log reader for DORA `deployment_frequency` + `lead_time` (Story 5.13, D1).

`telemetry/` and `dashboard/` have no git grant and must not import `cli/`
(architecture.md:492, :1105 restrict `subprocess.run` to `runtime/` +
`cli/git.py` + `cli/gh.py`), so the git read for DORA is computed HERE — in
the `cli` layer — and dependency-injected into the dashboard server at
construction (`cli/dashboard.py::run_dashboard`). This mirrors Story 3.2's
`cli/_git_recency.py` DI precedent exactly.

The reader emits `(author_ts_iso, commit_ts_iso, is_merge)` tuples (plain
`tuple[str, str, bool]`, not a shared dataclass) so `telemetry/dora.py` can
consume them without either module importing the other's types. It degrades
gracefully (mirrors architecture.md:1121): a non-git repo, missing git
binary, timeout, non-zero exit, or parse error yields an empty list, and
`compute_dora_window` treats that the same as "no git history" →
`insufficient_data`.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeAlias

_GIT_TIMEOUT_SECONDS: Final[float] = 5.0
_FIELD_SEP: Final[str] = "\x1f"

# (author_ts_iso, commit_ts_iso, is_merge). Duplicated (not imported) from
# telemetry/dora.py's identical alias — both sides are plain tuples, so no
# cross-module import is needed to keep the shapes compatible under mypy.
GitCommitTuple: TypeAlias = tuple[str, str, bool]


def _try_parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 git date (`%aI`/`%cI`); return None if invalid.

    Mirrors `cli/_git_recency.py::_try_parse_iso` — git emits a trailing 'Z'
    for UTC committers on some hosts; normalize to `+00:00` (3.10 compat).
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_dora_git_log(stdout: str) -> list[GitCommitTuple]:
    """Parse `git log --pretty=format:%P<sep>%aI<sep>%cI` output into commit tuples.

    Pure function fed a canned stdout fixture — unit-testable without invoking
    git (mirrors `parse_git_log` / Story 3.2 precedent). A commit is a merge
    iff it has more than one parent hash (`%P` is space-separated).
    """
    records: list[GitCommitTuple] = []
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        parts = raw.split(_FIELD_SEP)
        if len(parts) != 3:  # noqa: PLR2004 - (parents, author_iso, commit_iso)
            continue
        parent_hashes, author_iso, commit_iso = parts
        author_dt = _try_parse_iso(author_iso)
        commit_dt = _try_parse_iso(commit_iso)
        if author_dt is None or commit_dt is None:
            continue
        is_merge = len(parent_hashes.split()) > 1
        records.append((author_dt.isoformat(), commit_dt.isoformat(), is_merge))
    return records


def git_dora_log(root: Path) -> list[GitCommitTuple]:
    """Return `(author_ts, commit_ts, is_merge)` tuples for `root`'s git history.

    Degrades gracefully to `[]` on any git failure (non-git repo, missing
    binary, timeout, non-zero exit) — DORA computation then reports
    `insufficient_data` for the git-derived metrics (architecture.md:1121).
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "log",
                f"--pretty=format:%P{_FIELD_SEP}%aI{_FIELD_SEP}%cI",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            cwd=root,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return parse_dora_git_log(result.stdout)


__all__: tuple[str, ...] = ("GitCommitTuple", "git_dora_log", "parse_dora_git_log")
