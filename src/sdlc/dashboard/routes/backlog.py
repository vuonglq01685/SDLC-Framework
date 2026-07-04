"""``GET /api/backlog`` — real Epic->Story->Task hierarchy read seam (Story 5.15 Task 1/2).

D1(a): the real hierarchy lives in the ``01-Requirement/04-Epics`` +
``01-Requirement/05-Stories/<epic-id>/`` + ``03-Implementation/tasks/<story-id>/``
artifact tree (Story 2A.11 writer: ``cli/epics.py`` / ``cli/stories.py`` /
``cli/break_.py``), NOT the projected ``state.json`` -- ``state/projection.py``
reserves ``story-``/``task-`` folding "for later stories", so
``state.json["stories"]``/``["tasks"]`` stay empty today. This route is a
read-only dashboard-side view: it never imports ``engine``/``cli`` (module
boundary forbids it) and never re-parses the wire ``/state.json`` file (that
route streams it byte-for-byte with ETag-over-content [routes/state.py]).

D2(a): :func:`build_backlog_tree` is a PURE nesting adapter. It groups each
STORY under its EPIC and each TASK under its STORY by **parsing the
canonical id** (Story 1.6 ``parse_story_id``/``parse_task_id`` -- never by
trusting directory names), emitting the exact
``{currentTaskId, epics:[{id,kind,name,flow,meta,pct,expanded,
stories:[{id,kind,name,status,meta,pct,expanded,tasks:[{id,kind,name,status,meta}]}]}]}``
shape the FROZEN 5.10 ``renderBacklogTree`` already consumes
[backlog-tree.js:15-73] -- the render/keyboard/a11y seam is untouched.

A malformed real id (unparsable epic/story/task id, an orphaned task whose
story was never written) is skipped rather than raised or rendered as
``undefined`` (D5 tolerance) -- this route is best-effort real-data display,
not a validating gate. Real epic/story JSON (``cli/_epic_story_models.py``)
carries no persisted "status"/"flow" field today: story/epic ``status`` is
derived from child task ``stage`` (never invented out of thin air), and
``flow`` is simply omitted (the frozen ``if (epic.flow)`` guard in
``backlog-tree.js`` already skips rendering it when absent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from sdlc.dashboard.router import RequestContext, Response, Router
from sdlc.ids.parsers import (
    EPIC_ID_REGEX,
    parse_epic_id,
    parse_story_id,
    parse_task_id,
)

_EPICS_DIR_REL: Final[str] = "01-Requirement/04-Epics"
_STORIES_ROOT_REL: Final[str] = "01-Requirement/05-Stories"
_TASKS_ROOT_REL: Final[str] = "03-Implementation/tasks"
_EPIC_JSON_GLOB: Final[str] = "EPIC-*.json"
_JSON_GLOB: Final[str] = "*.json"

# Task stage (5-state /sdlc-task machine) -> the 3-value pill-status vocabulary
# the FROZEN 5.10 renderer understands (PILL_STATUS_VARIANTS: done/in-progress/pending).
_TASK_STAGE_TO_STATUS: Final[dict[str, str]] = {
    "pending": "pending",
    "write-tests": "in-progress",
    "write-code": "in-progress",
    "review": "in-progress",
    "done": "done",
}


def _load_json_object(path: Path) -> dict[str, Any] | None:
    """Best-effort read; malformed/unreadable artifacts are skipped, never raised (D5)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _ordering_key(value: object) -> int:
    """Coerce a possibly-malformed ``ordering`` to a sortable int (Review P-1).

    The epic sort compares ``ordering`` across every file; a non-int value
    (``null`` -> ``None``, or a string) previously raised ``TypeError`` and
    500'd the ENTIRE ``/api/backlog`` tree -- defeating the module's
    best-effort "malformed skipped, never raised (D5)" contract. Non-int
    values sort as ``0`` rather than crashing the whole endpoint.
    """
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _read_epics(epics_root: Path) -> list[dict[str, Any]]:
    if not epics_root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(epics_root.glob(_EPIC_JSON_GLOB)):
        data = _load_json_object(path)
        if data is None:
            continue
        raw_id = data.get("id")
        if not isinstance(raw_id, str) or EPIC_ID_REGEX.match(raw_id) is None:
            continue  # D5: malformed/non-canonical id -> skip, never render "undefined"
        out.append(data)
    out.sort(key=lambda e: (_ordering_key(e.get("ordering")), e["id"]))
    return out


def _read_stories(stories_root: Path, *, epic_id: str, epic_slug: str) -> list[dict[str, Any]]:
    story_dir = stories_root / epic_id
    if not story_dir.is_dir():
        return []
    parsed_pairs = []
    for path in sorted(story_dir.glob(_JSON_GLOB)):
        data = _load_json_object(path)
        if data is None:
            continue
        raw_id = data.get("id")
        if not isinstance(raw_id, str):
            continue
        try:
            parsed = parse_story_id(raw_id)
        except Exception:
            continue
        if parsed.epic_slug != epic_slug:
            continue  # id claims a different epic than the directory it lives in
        parsed_pairs.append((parsed, data))
    parsed_pairs.sort(key=lambda pair: pair[0].story_num)
    return [data for _parsed, data in parsed_pairs]


def _parse_task_file(path: Path) -> tuple[Any, dict[str, Any]] | None:
    data = _load_json_object(path)
    if data is None:
        return None
    raw_id = data.get("id")
    if not isinstance(raw_id, str):
        return None
    try:
        parsed = parse_task_id(raw_id)
    except Exception:  # D5: any parse failure is a safe skip
        return None
    return parsed, data


def _index_tasks_by_story(tasks_root: Path) -> dict[str, list[tuple[Any, dict[str, Any]]]]:
    """Return ``{story_id: [(TaskId, raw_json), ...]}`` sorted by task_num.

    Grouped by the task's OWN canonical id (never by directory name) so an
    orphaned task (a story id that no real story file matches) safely lands
    under a key nothing looks up -- dropped, not mis-nested, not raised (D5).
    """
    by_story: dict[str, list[tuple[Any, dict[str, Any]]]] = {}
    if not tasks_root.is_dir():
        return by_story
    for story_dir in sorted(tasks_root.iterdir()):
        if not story_dir.is_dir():
            continue
        for path in sorted(story_dir.glob(_JSON_GLOB)):
            pair = _parse_task_file(path)
            if pair is None:
                continue
            parsed, _data = pair
            story_id = f"EPIC-{parsed.epic_slug}-S{parsed.story_num:02d}-{parsed.story_slug}"
            by_story.setdefault(story_id, []).append(pair)
    for tasks in by_story.values():
        tasks.sort(key=lambda pair: pair[0].task_num)
    return by_story


def _task_status(stage: object) -> str:
    key = stage if isinstance(stage, str) else "pending"
    return _TASK_STAGE_TO_STATUS.get(key, "pending")


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular}" if count == 1 else f"{count} {plural}"


def _pct(done: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round(done * 100 / total)}%"


def _build_task_node(parsed_task: Any, data: dict[str, Any]) -> dict[str, Any]:
    status = _task_status(data.get("stage"))
    label = data.get("label")
    name = label if isinstance(label, str) and label else parsed_task.task_slug
    return {
        "id": parsed_task.raw,
        "kind": "TASK",
        "name": name,
        "status": status,
        "meta": f"T{parsed_task.task_num:02d}",
    }


def _story_status(done_count: int, in_progress_count: int, total: int) -> str:
    if total == 0:
        return "pending"
    if done_count == total:
        return "done"
    # Review P-2: a story with started (in-progress) tasks but 0 done is
    # in-progress, not pending -- otherwise a mid-flight story's header pill
    # contradicts its own in-progress child task pills.
    if done_count > 0 or in_progress_count > 0:
        return "in-progress"
    return "pending"


def _build_story_node(
    story_data: dict[str, Any], story_tasks: list[tuple[Any, dict[str, Any]]]
) -> tuple[dict[str, Any], str]:
    """Return (story_node, first_non_done_task_id_or_empty)."""
    tasks_out: list[dict[str, Any]] = []
    done_count = 0
    in_progress_count = 0
    first_pending = ""
    for parsed_task, task_data in story_tasks:
        node = _build_task_node(parsed_task, task_data)
        if node["status"] == "done":
            done_count += 1
        else:
            if first_pending == "":
                first_pending = node["id"]
            if node["status"] == "in-progress":
                in_progress_count += 1
        tasks_out.append(node)

    story_id = story_data["id"]
    label = story_data.get("label")
    name = label if isinstance(label, str) and label else story_id
    story_node = {
        "id": story_id,
        "kind": "STORY",
        "name": name,
        "status": _story_status(done_count, in_progress_count, len(story_tasks)),
        "meta": _plural(len(tasks_out), "task", "tasks"),
        "pct": _pct(done_count, len(story_tasks)),
        "expanded": False,
        "tasks": tasks_out,
    }
    return story_node, first_pending


def _build_epic_node(
    epic_data: dict[str, Any],
    *,
    stories_root: Path,
    tasks_by_story: dict[str, list[tuple[Any, dict[str, Any]]]],
) -> tuple[dict[str, Any], str] | None:
    """Return (epic_node, first_non_done_task_id_or_empty), or None on a malformed id."""
    epic_id = epic_data["id"]
    try:
        epic_slug = parse_epic_id(epic_id).epic_slug
    except Exception:  # D5: safe skip on malformed epic id
        return None

    stories_out: list[dict[str, Any]] = []
    epic_done_tasks = 0
    epic_total_tasks = 0
    first_pending = ""

    for story_data in _read_stories(stories_root, epic_id=epic_id, epic_slug=epic_slug):
        story_tasks = tasks_by_story.get(story_data["id"], [])
        story_node, pending = _build_story_node(story_data, story_tasks)
        if first_pending == "" and pending:
            first_pending = pending
        epic_done_tasks += sum(1 for t in story_node["tasks"] if t["status"] == "done")
        epic_total_tasks += len(story_tasks)
        stories_out.append(story_node)

    label = epic_data.get("label")
    name = label if isinstance(label, str) and label else epic_id
    epic_node = {
        "id": epic_id,
        "kind": "EPIC",
        "name": name,
        "meta": _plural(len(stories_out), "story", "stories"),
        "pct": _pct(epic_done_tasks, epic_total_tasks),
        "expanded": False,
        "stories": stories_out,
    }
    return epic_node, first_pending


def build_backlog_tree(repo_root: Path) -> dict[str, Any]:
    """Pure read-only derivation of the real Epic->Story->Task nest (D1(a)/D2(a))."""
    epics_root = repo_root / _EPICS_DIR_REL
    stories_root = repo_root / _STORIES_ROOT_REL
    tasks_root = repo_root / _TASKS_ROOT_REL

    tasks_by_story = _index_tasks_by_story(tasks_root)

    current_task_id = ""
    epics_out: list[dict[str, Any]] = []

    for epic_data in _read_epics(epics_root):
        built = _build_epic_node(
            epic_data, stories_root=stories_root, tasks_by_story=tasks_by_story
        )
        if built is None:
            continue
        epic_node, pending = built
        if current_task_id == "" and pending:
            current_task_id = pending
        epics_out.append(epic_node)

    return {"currentTaskId": current_task_id, "epics": epics_out}


def find_current_cursor(repo_root: Path) -> dict[str, str] | None:
    """Return ``{epic_id, story_id, task_id, stage}`` for the first non-done task
    in canonical epic/story/task order (Story 5.18 D1/D3), or ``None`` when no
    epics/stories/tasks exist or every task is done.

    Mirrors :func:`build_backlog_tree`'s first-pending-task precedence (same
    read helpers, same ordering) but returns the task's RAW workflow ``stage``
    (5-value: pending/write-tests/write-code/review/done) instead of the
    3-value display pill ``build_backlog_tree`` derives for the tree UI.
    """
    epics_root = repo_root / _EPICS_DIR_REL
    stories_root = repo_root / _STORIES_ROOT_REL
    tasks_root = repo_root / _TASKS_ROOT_REL
    tasks_by_story = _index_tasks_by_story(tasks_root)

    for epic_data in _read_epics(epics_root):
        epic_id = epic_data["id"]
        try:
            epic_slug = parse_epic_id(epic_id).epic_slug
        except Exception:  # D5: safe skip on malformed epic id
            continue
        for story_data in _read_stories(stories_root, epic_id=epic_id, epic_slug=epic_slug):
            story_id = story_data["id"]
            for parsed_task, task_data in tasks_by_story.get(story_id, []):
                stage = task_data.get("stage")
                stage_str = stage if isinstance(stage, str) and stage else "pending"
                if stage_str != "done":
                    return {
                        "epic_id": epic_id,
                        "story_id": story_id,
                        "task_id": parsed_task.raw,
                        "stage": stage_str,
                    }
    return None


def register_backlog_route(router: Router, *, repo_root: Path) -> None:
    @router.get("/api/backlog")
    def handle_backlog(_ctx: RequestContext) -> Response:
        body = json.dumps(
            build_backlog_tree(repo_root), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return Response(
            status=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
        )
