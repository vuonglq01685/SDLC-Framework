"""Benchmark corpus builder for Story 1.15 performance gate."""

from __future__ import annotations

import json
from pathlib import Path


def _build_perf_corpus(root: Path) -> None:
    """Scaffold 4 epics + 200 stories + 1000 tasks under root for the perf gate.

    Distributing 200 stories across 4 epics (50 each) keeps every story
    number in the regex-valid S01..S50 range. Single-epic 200-story
    layouts would emit S100..S200 filenames that STORY_ID_REGEX silently
    skips, undercounting the corpus.
    """
    epics_dir = root / "01-Requirement" / "04-Epics"
    stories_root = root / "01-Requirement" / "05-Stories"
    tasks_root = root / "03-Implementation" / "tasks"
    epics_dir.mkdir(parents=True)
    stories_root.mkdir(parents=True)
    tasks_root.mkdir(parents=True)
    for letter in ("a", "b", "c", "d"):
        eid = f"EPIC-perf-{letter}"
        (epics_dir / f"{eid}.json").write_text(
            json.dumps({"id": eid, "title": "perf"}),
            encoding="utf-8",
        )
        sdir = stories_root / eid
        sdir.mkdir()
        for n in range(1, 51):  # 50 stories per epic, S01..S50
            sid = f"{eid}-S{n:02d}-perf"
            (sdir / f"{sid}.json").write_text(
                json.dumps({"id": sid, "title": "perf"}),
                encoding="utf-8",
            )
            tdir = tasks_root / sid
            tdir.mkdir()
            for m in range(1, 6):  # 5 tasks per story, T01..T05 = 1000 tasks total
                tid = f"{sid}-T{m:02d}-perf"
                (tdir / f"{tid}.json").write_text(
                    json.dumps({"id": tid, "title": "perf"}),
                    encoding="utf-8",
                )
