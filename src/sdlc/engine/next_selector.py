"""Phase-aware next-item selector for auto-loop and CLI (Story 4.1, D1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from sdlc.errors import SignoffError
from sdlc.ids.parsers import parse_task_id
from sdlc.signoff import SignoffState, compute_state

_PRODUCT_REL: Final[str] = "01-Requirement/01-PRODUCT.md"
_EPICS_ROOT_REL: Final[str] = "01-Requirement/04-Epics"
_STORIES_ROOT_REL: Final[str] = "01-Requirement/05-Stories"
_ARCH_ROOT_REL: Final[str] = "02-Architecture"
_TASKS_ROOT_REL: Final[str] = "03-Implementation/tasks"
_ARCH_FILE_GLOB: Final[str] = "**/ARCHITECTURE.md"
_EPIC_JSON_GLOB: Final[str] = "EPIC-*.json"
_STORY_JSON_GLOB: Final[str] = "*.json"
_TASK_JSON_GLOB: Final[str] = "T*-*.json"


@dataclass(frozen=True)
class NextDecision:
    kind: Literal["dispatch_task", "run_command", "none"]
    task_id: str | None = None
    command: str | None = None
    phase: int | None = None
    reason: str = ""
    blockers: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _TaskSnapshot:
    id: str
    stage: str
    dependencies: tuple[str, ...]


def _epic_ids_on_disk(epics_root: Path) -> list[str]:
    if not epics_root.is_dir():
        return []
    return [p.stem for p in sorted(epics_root.glob(_EPIC_JSON_GLOB))]


def _stories_exist_for_epic(stories_root: Path, epic_id: str) -> bool:
    story_dir = stories_root / epic_id
    if not story_dir.is_dir():
        return False
    return any(story_dir.glob(_STORY_JSON_GLOB))


def _architecture_exists(arch_root: Path) -> bool:
    if not arch_root.is_dir():
        return False
    return any(arch_root.rglob(_ARCH_FILE_GLOB))


def _load_task(task_path: Path) -> _TaskSnapshot | None:
    try:
        data = json.loads(task_path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return None
        task_id = data.get("id")
        stage = data.get("stage")
        if not isinstance(task_id, str) or not isinstance(stage, str):
            return None
        deps_raw = data.get("dependencies", [])
        if isinstance(deps_raw, list):
            deps = tuple(d for d in deps_raw if isinstance(d, str))
        else:
            deps = ()
        return _TaskSnapshot(id=task_id, stage=stage, dependencies=deps)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _parse_story_seq(story_dir_name: str) -> int:
    m = re.search(r"-S(\d{2})-", story_dir_name)
    return int(m.group(1)) if m else 999


def _parse_task_seq(task_id: str) -> int:
    try:
        return parse_task_id(task_id).task_num
    except Exception:
        return 999


def _collect_task_index(
    tasks_root: Path,
) -> tuple[dict[str, _TaskSnapshot], list[tuple[int, int, _TaskSnapshot]]]:
    all_tasks: dict[str, _TaskSnapshot] = {}
    indexed: list[tuple[int, int, _TaskSnapshot]] = []
    if not tasks_root.is_dir():
        return all_tasks, indexed
    for story_dir in sorted(tasks_root.iterdir()):
        if not story_dir.is_dir():
            continue
        s_seq = _parse_story_seq(story_dir.name)
        for task_path in sorted(story_dir.glob(_TASK_JSON_GLOB)):
            task = _load_task(task_path)
            if task is None:
                continue
            all_tasks[task.id] = task
            indexed.append((s_seq, _parse_task_seq(task.id), task))
    indexed.sort(key=lambda item: (item[0], item[1]))
    return all_tasks, indexed


def _deps_satisfied(task: _TaskSnapshot, all_tasks: dict[str, _TaskSnapshot]) -> bool:
    return all(
        dep_id in all_tasks and all_tasks[dep_id].stage == "done" for dep_id in task.dependencies
    )


def _select_phase3_task(tasks_root: Path) -> tuple[_TaskSnapshot | None, dict[str, int]]:
    if not tasks_root.is_dir():
        return None, {}
    all_tasks, indexed = _collect_task_index(tasks_root)
    if not indexed:
        return None, {}
    blocked_count = 0
    done_count = 0
    for _, _, task in indexed:
        if task.stage == "done":
            done_count += 1
            continue
        if _deps_satisfied(task, all_tasks):
            return task, {}
        blocked_count += 1
    if done_count == len(indexed):
        return None, {"blocked_by_deps": 0, "awaiting_signoff": 0}
    return None, {"blocked_by_deps": blocked_count, "awaiting_signoff": 0}


def resolve_next_action(repo_root: Path) -> NextDecision:
    """Phase-aware next-item resolver — engine-owned, pure read."""
    if not (repo_root / _PRODUCT_REL).is_file():
        return NextDecision(
            kind="run_command",
            command='/sdlc-start "<idea>"',
            phase=1,
            reason="phase 1 not started",
        )
    try:
        phase1_state = compute_state(phase=1, repo_root=repo_root)
    except (SignoffError, OSError) as exc:
        return NextDecision(
            kind="run_command",
            command="/sdlc-signoff 1",
            phase=1,
            reason=f"phase 1 signoff unreadable: {exc}",
        )
    if phase1_state != SignoffState.APPROVED:
        return _resolve_phase1_ladder(repo_root)
    try:
        phase2_state = compute_state(phase=2, repo_root=repo_root)
    except (SignoffError, OSError) as exc:
        return NextDecision(
            kind="run_command",
            command="/sdlc-signoff 2",
            phase=2,
            reason=f"phase 2 signoff unreadable: {exc}",
        )
    if phase2_state != SignoffState.APPROVED:
        return _resolve_phase2_ladder(repo_root)
    return _resolve_phase3(repo_root)


def _resolve_phase1_ladder(repo_root: Path) -> NextDecision:
    epics_root = repo_root / _EPICS_ROOT_REL
    stories_root = repo_root / _STORIES_ROOT_REL
    epic_ids = _epic_ids_on_disk(epics_root)
    if not epic_ids:
        return NextDecision(
            kind="run_command", command="/sdlc-epics", phase=1, reason="no epic JSONs found"
        )
    for epic_id in epic_ids:
        if not _stories_exist_for_epic(stories_root, epic_id):
            return NextDecision(
                kind="run_command",
                command=f"/sdlc-stories {epic_id}",
                phase=1,
                reason=f"no stories for {epic_id}",
            )
    return NextDecision(
        kind="run_command", command="/sdlc-signoff 1", phase=1, reason="phase 1 unsigned"
    )


def _resolve_phase2_ladder(repo_root: Path) -> NextDecision:
    arch_root = repo_root / _ARCH_ROOT_REL
    if not _architecture_exists(arch_root):
        return NextDecision(
            kind="run_command",
            command="/sdlc-architect",
            phase=2,
            reason="no architecture artifact found",
        )
    return NextDecision(
        kind="run_command", command="/sdlc-signoff 2", phase=2, reason="phase 2 unsigned"
    )


def _resolve_phase3(repo_root: Path) -> NextDecision:
    tasks_root = repo_root / _TASKS_ROOT_REL
    task, blockers = _select_phase3_task(tasks_root)

    if task is not None:
        return NextDecision(
            kind="dispatch_task",
            task_id=task.id,
            reason=f"phase 3 task ready: {task.id}",
        )

    if not blockers:
        return NextDecision(
            kind="none",
            reason="phase 3: no tasks generated yet (run /sdlc-break for the active story)",
        )

    if blockers.get("blocked_by_deps", 0) > 0:
        n = blockers["blocked_by_deps"]
        return NextDecision(
            kind="none",
            reason=f"no ready items: {n} task{'s' if n != 1 else ''} blocked by dependencies",
            blockers=blockers,
        )

    return NextDecision(
        kind="none",
        reason="all tasks complete",
        blockers={"blocked_by_deps": 0, "awaiting_signoff": 0},
    )
