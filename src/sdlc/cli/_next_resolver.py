"""Phase-aware resolver for `/sdlc-next` (Story 2A.18, AC2/D1).

``resolve_next(repo_root)`` is a **pure function of disk state** — no writes,
no journal. It reads signoff state via ``compute_state`` and globs the artifact
tree, mirroring the read-only posture of ``cli/scan.py`` / ``cli/status.py``.

Resolution ladder (first match wins):
  1. PRODUCT.md absent         → run_command  /sdlc-start "<idea>"
  2. Phase 1 not APPROVED      → run_command  first missing Phase-1 artifact command
  3. Phase 2 not APPROVED      → run_command  first missing Phase-2 artifact command
  4. Phase 2 APPROVED          → dispatch_task / none

Debt: EPIC-2A-DEBT-NEXT-CONSUME-PROJECTION — once the task projection lands in
state.json, refactor to consume that instead of re-globbing the artifact tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from sdlc.cli._epic_story_models import _TaskEntry
from sdlc.errors import SignoffError
from sdlc.ids.parsers import parse_task_id
from sdlc.signoff import SignoffState, compute_state

# ---------------------------------------------------------------------------
# Artifact path constants (mirroring cli/break_.py)
# ---------------------------------------------------------------------------

_PRODUCT_REL: Final[str] = "01-Requirement/01-PRODUCT.md"
_EPICS_ROOT_REL: Final[str] = "01-Requirement/04-Epics"
_STORIES_ROOT_REL: Final[str] = "01-Requirement/05-Stories"
_ARCH_ROOT_REL: Final[str] = "02-Architecture"
_TASKS_ROOT_REL: Final[str] = "03-Implementation/tasks"

_ARCH_FILE_GLOB: Final[str] = "**/ARCHITECTURE.md"
_EPIC_JSON_GLOB: Final[str] = "EPIC-*.json"
_STORY_JSON_GLOB: Final[str] = "*.json"
_TASK_JSON_GLOB: Final[str] = "T*-*.json"

# ---------------------------------------------------------------------------
# _NextDecision dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _NextDecision:
    """Output of ``resolve_next``.

    kind:
      "dispatch_task"  — Phase 3 task ready; caller invokes ``run_task(task_id=...)``
      "run_command"    — Phase 1/2 advance; caller prints ``suggested_command``
      "none"           — no ready items; caller prints ``reason``
    """

    kind: Literal["dispatch_task", "run_command", "none"]
    task_id: str | None = None
    command: str | None = None
    phase: int | None = None
    reason: str = ""
    blockers: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _epic_ids_on_disk(epics_root: Path) -> list[str]:
    """Return EPIC-*.json IDs found under 04-Epics/, sorted by filename."""
    if not epics_root.is_dir():
        return []
    ids: list[str] = []
    for p in sorted(epics_root.glob(_EPIC_JSON_GLOB)):
        ids.append(p.stem)
    return ids


def _stories_exist_for_epic(stories_root: Path, epic_id: str) -> bool:
    """Return True if at least one story JSON exists under 05-Stories/<epic_id>/."""
    story_dir = stories_root / epic_id
    if not story_dir.is_dir():
        return False
    return any(story_dir.glob(_STORY_JSON_GLOB))


def _architecture_exists(arch_root: Path) -> bool:
    """Return True if any ARCHITECTURE.md exists anywhere under 02-Architecture/."""
    if not arch_root.is_dir():
        return False
    return any(arch_root.rglob(_ARCH_FILE_GLOB))


def _load_task(task_path: Path) -> _TaskEntry | None:
    """Parse a task JSON; return None on failure (soft — resolver skips malformed tasks)."""
    try:
        text = task_path.read_text(encoding="utf-8-sig")
        return _TaskEntry.model_validate_json(text)
    except Exception:
        return None


def _parse_story_seq(story_dir_name: str) -> int:
    """Extract story seq from directory name (EPIC-...-S<NN>-...); fallback=999."""
    m = re.search(r"-S(\d{2})-", story_dir_name)
    return int(m.group(1)) if m else 999


def _parse_task_seq(task_id: str) -> int:
    """Extract task seq from task id; fallback=999."""
    try:
        return parse_task_id(task_id).task_num
    except Exception:
        return 999


def _collect_task_index(
    tasks_root: Path,
) -> tuple[dict[str, _TaskEntry], list[tuple[int, int, _TaskEntry]]]:
    """Return (all_tasks_by_id, sorted [(story_seq, task_seq, task), ...]).

    Each task JSON is parsed exactly once — the parsed ``_TaskEntry`` is carried
    through the index so callers never re-read the file.
    """
    all_tasks: dict[str, _TaskEntry] = {}
    indexed: list[tuple[int, int, _TaskEntry]] = []
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


def _deps_satisfied(task: _TaskEntry, all_tasks: dict[str, _TaskEntry]) -> bool:
    """Return True when every dependency is present and at stage 'done'."""
    return all(
        dep_id in all_tasks and all_tasks[dep_id].stage == "done" for dep_id in task.dependencies
    )


def _select_phase3_task(tasks_root: Path) -> tuple[_TaskEntry | None, dict[str, int]]:
    """Enumerate task JSONs; return (first_ready_task, blocker_counts).

    Selection order: (story_seq, task_seq). A task is ready when:
      - stage != "done"
      - every dependency task_id has stage == "done"

    The blocker dict is empty (``{}``) ONLY when no task JSON exists at all —
    callers use that to distinguish "no tasks generated yet" from "all done".
    """
    if not tasks_root.is_dir():
        return None, {}

    all_tasks, indexed = _collect_task_index(tasks_root)
    if not indexed:  # tasks_root exists but holds no parseable task JSON
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_next(repo_root: Path) -> _NextDecision:
    """Phase-aware next-item resolver (AC2/D1).

    Pure function — reads disk + signoff state; writes nothing.
    """
    # --- Step 1: PRODUCT.md absent ---
    if not (repo_root / _PRODUCT_REL).is_file():
        return _NextDecision(
            kind="run_command",
            command='/sdlc-start "<idea>"',
            phase=1,
            reason="phase 1 not started",
        )

    # --- Step 2: Phase 1 not APPROVED ---
    try:
        phase1_state = compute_state(phase=1, repo_root=repo_root)
    except (SignoffError, OSError) as exc:
        return _NextDecision(
            kind="run_command",
            command="/sdlc-signoff 1",
            phase=1,
            reason=f"phase 1 signoff unreadable: {exc}",
        )

    if phase1_state != SignoffState.APPROVED:
        return _resolve_phase1_ladder(repo_root)

    # --- Step 3: Phase 2 not APPROVED ---
    try:
        phase2_state = compute_state(phase=2, repo_root=repo_root)
    except (SignoffError, OSError) as exc:
        return _NextDecision(
            kind="run_command",
            command="/sdlc-signoff 2",
            phase=2,
            reason=f"phase 2 signoff unreadable: {exc}",
        )

    if phase2_state != SignoffState.APPROVED:
        return _resolve_phase2_ladder(repo_root)

    # --- Step 4: Phase 2 APPROVED → Phase 3 ---
    return _resolve_phase3(repo_root)


def _resolve_phase1_ladder(repo_root: Path) -> _NextDecision:
    """Phase-1 artifact ladder (first missing wins)."""
    epics_root = repo_root / _EPICS_ROOT_REL
    stories_root = repo_root / _STORIES_ROOT_REL

    epic_ids = _epic_ids_on_disk(epics_root)
    if not epic_ids:
        return _NextDecision(
            kind="run_command",
            command="/sdlc-epics",
            phase=1,
            reason="no epic JSONs found",
        )

    # Check if any epic lacks stories
    for epic_id in epic_ids:
        if not _stories_exist_for_epic(stories_root, epic_id):
            return _NextDecision(
                kind="run_command",
                command=f"/sdlc-stories {epic_id}",
                phase=1,
                reason=f"no stories for {epic_id}",
            )

    # All artifacts present but phase unsigned
    return _NextDecision(
        kind="run_command",
        command="/sdlc-signoff 1",
        phase=1,
        reason="phase 1 unsigned",
    )


def _resolve_phase2_ladder(repo_root: Path) -> _NextDecision:
    """Phase-2 artifact ladder (first missing wins)."""
    arch_root = repo_root / _ARCH_ROOT_REL

    if not _architecture_exists(arch_root):
        return _NextDecision(
            kind="run_command",
            command="/sdlc-architect",
            phase=2,
            reason="no architecture artifact found",
        )

    return _NextDecision(
        kind="run_command",
        command="/sdlc-signoff 2",
        phase=2,
        reason="phase 2 unsigned",
    )


def _resolve_phase3(repo_root: Path) -> _NextDecision:
    """Phase 3: enumerate task JSONs and select the first ready task."""
    tasks_root = repo_root / _TASKS_ROOT_REL
    task, blockers = _select_phase3_task(tasks_root)

    if task is not None:
        return _NextDecision(
            kind="dispatch_task",
            task_id=task.id,
            reason=f"phase 3 task ready: {task.id}",
        )

    if not blockers:  # no task JSON exists yet — phase 3 not broken into tasks
        return _NextDecision(
            kind="none",
            reason="phase 3: no tasks generated yet (run /sdlc-break for the active story)",
        )

    if blockers.get("blocked_by_deps", 0) > 0:
        n = blockers["blocked_by_deps"]
        return _NextDecision(
            kind="none",
            reason=f"no ready items: {n} task{'s' if n != 1 else ''} blocked by dependencies",
            blockers=blockers,
        )

    return _NextDecision(
        kind="none",
        reason="all tasks complete",
        blockers={"blocked_by_deps": 0, "awaiting_signoff": 0},
    )
