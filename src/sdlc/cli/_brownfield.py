"""Brownfield TDD-strategy classification for `/sdlc-break` (Story 3.8, AC1/D2(a)).

A task whose ``touches`` paths intersect ``legacy_code_globs`` gets ``characterization-test``
(capture current behaviour, then refactor under that net); all others keep ``write-tests-first``
(the strict greenfield RED→GREEN pipeline). The match is **deterministic and CLI-side** — the LLM
never performs glob-matching — so the 2B.3 mock-vs-claude byte identity holds: the mock body and
the real model produce the same ``tdd_strategy`` for the same ``touches``.

The segment-aware ``**`` matcher mirrors ``dispatcher._panel_helpers._globstar_match`` and
``workflows.static_check`` (the codebase keeps a local matcher per layer rather than coupling
``cli`` to a dispatcher-private helper).
"""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Sequence
from typing import Final, Literal

TddStrategy = Literal["write-tests-first", "characterization-test"]

WRITE_TESTS_FIRST: Final[TddStrategy] = "write-tests-first"
CHARACTERIZATION_TEST: Final[TddStrategy] = "characterization-test"


def classify_tdd_strategy(
    touches: Sequence[str],
    legacy_code_globs: Sequence[str],
) -> TddStrategy:
    """Return ``characterization-test`` if any touched path matches any legacy glob.

    Greenfield (``legacy_code_globs`` empty) always returns ``write-tests-first`` — the
    regression guard that keeps existing projects byte-identical to today.
    """
    if not legacy_code_globs:
        return WRITE_TESTS_FIRST
    for path in touches:
        for glob in legacy_code_globs:
            if _match_path_glob(path, glob):
                return CHARACTERIZATION_TEST
    return WRITE_TESTS_FIRST


def _match_path_glob(path: str, pattern: str) -> bool:
    """Match a POSIX path against a glob with ``**`` support (segment-aware).

    ``**`` matches zero or more path segments; ``*``/``?``/char-classes match within a
    single segment (delegated to :mod:`fnmatch`) so ``*`` does NOT cross ``/`` boundaries.
    """
    return _match_segments(path.split("/"), pattern.split("/"))


def _match_segments(path_parts: list[str], pat_parts: list[str]) -> bool:
    if not pat_parts:
        return not path_parts
    head = pat_parts[0]
    if head == "**":
        return any(
            _match_segments(path_parts[i:], pat_parts[1:]) for i in range(len(path_parts) + 1)
        )
    if not path_parts:
        return False
    if fnmatch.fnmatchcase(path_parts[0], head):
        return _match_segments(path_parts[1:], pat_parts[1:])
    return False


def mock_task_batch_body_brownfield(story_id: str) -> str:
    """Brownfield variant of the mock task-breaker output (Story 3.8 AC7).

    Mirrors ``_break_pipeline.mock_task_batch_body`` but each task carries a ``touches``
    array: T01 touches a legacy path, T02/T03 touch fresh paths. With a project.yaml whose
    ``legacy_code_globs`` covers ``src/legacy/**`` the CLI classifier stamps T01
    ``characterization-test`` and the rest ``write-tests-first`` — exercising both branches
    on the deterministic mock-vs-claude byte-identity path.
    """
    return json.dumps(
        [
            {
                "id": f"{story_id}-T01-characterize-legacy-core",
                "story_id": story_id,
                "label": "Characterize and refactor the legacy core module.",
                "stage": "pending",
                "dependencies": [],
                "touches": ["src/legacy/core.py"],
            },
            {
                "id": f"{story_id}-T02-implement-write-path",
                "story_id": story_id,
                "label": "Implement the write path with validation.",
                "stage": "pending",
                "dependencies": [],
                "touches": ["src/app/write_path.py"],
            },
            {
                "id": f"{story_id}-T03-implement-read-path",
                "story_id": story_id,
                "label": "Implement the read path with caching.",
                "stage": "pending",
                "dependencies": [f"{story_id}-T01-characterize-legacy-core"],
                "touches": ["src/app/read_path.py"],
            },
        ],
        ensure_ascii=False,
    )
