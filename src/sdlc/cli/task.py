"""`sdlc task <TASK-id>` — Phase 3 TDD pipeline one-stage-per-invocation (FR17, Story 2A.17).

AC9/D1: single sdlc-task.yaml; CLI owns the stage→specialist map in _task_pipeline.py.
AC4/D1: RED→GREEN gate trusts specialist self-report (EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION).
AC6/D1: task JSON stage field is state-of-record; state.json not written
  (EPIC-2A-DEBT-TASK-STATE-PROJECTION).
AC8/D1: review_verdict/review_notes are real serialized fields on _TaskEntry
  (key set grows on first advance).
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import typer
from pydantic import ValidationError

from sdlc.cli._boundary import artifact_contains_boundary
from sdlc.cli._epic_story_models import _TaskEntry
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._runtime_selection import (
    build_runtime,
    enforce_allow_mock_gate,
    use_mock_runtime,
)
from sdlc.cli._task_pipeline import (
    _NEXT_STAGE,
    _SLASH_CMD,
    _TASKS_ROOT_REL,
    select_stage_specialist,
    task_stage_dispatch_write,
)
from sdlc.cli._task_pipeline_mocks import (
    mock_characterization_author_body,
    mock_code_author_body,
    mock_code_reviewer_body,
    mock_test_author_body,
    write_mock_fixture,
)
from sdlc.cli.output import emit_error, emit_json, emit_warning
from sdlc.dispatcher import build_pre_write_hook_chain
from sdlc.errors import SignoffError, SpecialistError, WorkflowError
from sdlc.ids.parsers import TASK_ID_PATTERN, TASK_ID_REGEX, parse_task_id
from sdlc.runtime.mock import compute_prompt_hash
from sdlc.signoff import SignoffState, compute_state
from sdlc.specialists import load_registry
from sdlc.specialists.frontmatter import Specialist
from sdlc.workflows.registry import WorkflowRegistry

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_STORIES_ROOT_REL: Final[str] = "01-Requirement/05-Stories"


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg

    return Path(pkg.__file__).resolve().parent


def _story_path(root: Path, task_id: str) -> Path:
    parsed = parse_task_id(task_id)
    story_id = f"EPIC-{parsed.epic_slug}-S{parsed.story_num:02d}-{parsed.story_slug}"
    epic_id = f"EPIC-{parsed.epic_slug}"
    return root / _STORIES_ROOT_REL / epic_id / f"{story_id}.json"


def _task_file_path(root: Path, task_id: str) -> Path:
    parsed = parse_task_id(task_id)
    story_id = f"EPIC-{parsed.epic_slug}-S{parsed.story_num:02d}-{parsed.story_slug}"
    fname = f"T{parsed.task_num:02d}-{parsed.task_slug}.json"
    return root / _TASKS_ROOT_REL / story_id / fname


def run_task(*, ctx: typer.Context, task_id: str, allow_mock: bool = False) -> None:  # noqa: C901, PLR0912, PLR0915
    """Phase 3 TDD pipeline — one stage per invocation (FR17)."""
    allow_mock_invoked = enforce_allow_mock_gate(allow_mock=allow_mock, ctx=ctx)
    root = _get_repo_root_or_cwd()
    journal_path = root / _JOURNAL_REL
    agent_runs_path = root / _RUNS_REL

    # Step 1 — Validate TASK-id format (AC1).
    if TASK_ID_REGEX.match(task_id) is None:
        emit_error(
            "ERR_USER_INPUT",
            f"invalid TASK-id: {task_id}; expected pattern {TASK_ID_PATTERN}",
            ctx=ctx,
            details={"task_id": task_id, "expected_pattern": TASK_ID_PATTERN},
        )

    # Step 2 — Init guard (AC1).
    if not (root / _STATE_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    # Step 3 — Phase 2 gate (AC1).
    try:
        phase2_state = compute_state(phase=2, repo_root=root)
    except (SignoffError, OSError) as exc:
        cause = " | ".join(str(exc).splitlines())[:500]
        emit_error(
            "ERR_SIGNOFF_READ_FAILED",
            f"phase 2 signoff state could not be read: {cause}",
            ctx=ctx,
            details={"phase": 2, "cause": cause},
        )
    if phase2_state != SignoffState.APPROVED:
        emit_error(
            "ERR_PHASE2_NOT_APPROVED",
            f"phase 2 signoff must be APPROVED before running tasks; "
            f"current state: {phase2_state.value}.",
            ctx=ctx,
            details={"phase2_state": str(phase2_state)},
        )

    # Step 4 — Resolve task file path + load task (AC2).
    task_path = _task_file_path(root, task_id)
    parsed = parse_task_id(task_id)
    story_id = f"EPIC-{parsed.epic_slug}-S{parsed.story_num:02d}-{parsed.story_slug}"

    if not task_path.is_file():
        emit_error(
            "ERR_USER_INPUT",
            f"task not found: {task_id}; expected at {task_path}; "
            f"run '/sdlc-break {story_id}' first",
            ctx=ctx,
            details={"task_id": task_id, "path": str(task_path)},
        )

    try:
        task_text = task_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        emit_error("ERR_ARTIFACT_UNREADABLE", str(exc), ctx=ctx, details={"cause": str(exc)})

    # BOUNDARY_LINE guard (AC2).
    if artifact_contains_boundary(task_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"task JSON {task_path.name} contains the data-vs-instruction boundary marker",
            ctx=ctx,
        )

    try:
        task = _TaskEntry.model_validate_json(task_text)
    except ValidationError as exc:
        emit_error(
            "ERR_USER_INPUT",
            f"task JSON parse failed: {exc}",
            ctx=ctx,
            details={"task_id": task_id, "cause": str(exc)},
        )

    # Step 4b — Identity + lineage cross-check: the path is derived from the
    # TASK-id argument, so a renamed/copied task file whose internal id or
    # story_id disagrees with the request must be refused (mirrors the
    # /sdlc-break output-side cross-check, Story 2A.16).
    if task.id != task_id:
        emit_error(
            "ERR_USER_INPUT",
            f"task file identity mismatch: {task_path.name} declares id {task.id!r} "
            f"but {task_id!r} was requested",
            ctx=ctx,
            details={"requested": task_id, "file_id": task.id, "path": str(task_path)},
        )
    if task.story_id != story_id:
        emit_error(
            "ERR_USER_INPUT",
            f"task lineage mismatch: {task_path.name} declares story_id {task.story_id!r} "
            f"but {task_id!r} belongs to story {story_id!r}",
            ctx=ctx,
            details={
                "requested": task_id,
                "file_story_id": task.story_id,
                "expected_story_id": story_id,
            },
        )

    # Step 5 — Idempotency guard: refuse if already done (AC2).
    if task.stage == "done":
        emit_error(
            "ERR_USER_INPUT",
            f"task already complete: {task_id} is at stage 'done'",
            ctx=ctx,
            details={"task_id": task_id, "stage": "done"},
        )

    current_stage = task.stage

    # Step 6 — Load story for compound prompt context. A missing or undecodable
    # story file degrades the prompt rather than aborting, but the degradation
    # must be visible — emit a non-blocking advisory rather than failing silent.
    story_path = _story_path(root, task_id)
    story_text = ""
    if story_path.is_file():
        try:
            story_text = story_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            emit_warning(
                "ERR_STORY_CONTEXT_UNREADABLE",
                f"story file {story_path.name} is not valid UTF-8; the specialist "
                "will be dispatched with empty STORY_CONTEXT",
                ctx=ctx,
                details={"story_path": str(story_path)},
            )
    else:
        emit_warning(
            "ERR_STORY_CONTEXT_MISSING",
            f"story file not found at {story_path}; the specialist will be "
            "dispatched with empty STORY_CONTEXT",
            ctx=ctx,
            details={"story_path": str(story_path)},
        )

    # Step 7 — Load workflow spec + specialist registry + hook chain.
    workflows_dir = _workflows_package_dir()
    try:
        spec = WorkflowRegistry.load(workflows_dir).get(_SLASH_CMD)
    except (WorkflowError, OSError) as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"workflow load failed: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )

    agents_dir = root / _AGENTS_REL
    try:
        registry = load_registry(agents_dir)
    except (SpecialistError, OSError) as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"specialist registry load failed: {exc}",
            ctx=ctx,
            details={"agents_dir": str(agents_dir)},
        )

    hooks = build_pre_write_hook_chain(repo_root=root)

    # Step 8 — Mock runtime materialization per stage specialist (AC8/D1 dispatch stages only).
    # Story 3.8 AC3: pending-stage selection consults task.tdd_strategy (characterization swap).
    specialist_name = select_stage_specialist(current_stage, task)

    # Story 3.8 review (F1): on the real runtime the pending stage dispatches the nominal-only
    # primary_agent ("test-author", AC9/D1), which authors fail-first RED tests — but the
    # characterization gate requires GREEN, so a real characterization-test task would fail
    # confusingly at the gate after dispatch. Fail fast with an actionable message until real
    # characterization-author dispatch is wired (EPIC-3-DEBT-CHARACTERIZATION-REAL-DISPATCH,
    # tracked alongside EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION). Mock mode dispatches the
    # characterization body (GREEN) and is unaffected.
    if specialist_name == "characterization-author" and not use_mock_runtime():
        emit_error(
            "ERR_TASK_STAGE_FAILED",
            "characterization-test tasks cannot be dispatched on the real runtime yet: "
            "/sdlc-task routes the pending stage through 'test-author' (nominal-only, AC9/D1), "
            "which authors fail-first (RED) tests, but the characterization gate requires GREEN. "
            "Use the mock runtime (SDLC_USE_MOCK_RUNTIME=1) for now; real characterization-author "
            "dispatch is tracked as EPIC-3-DEBT-CHARACTERIZATION-REAL-DISPATCH.",
            ctx=ctx,
            details={
                "task_id": task_id,
                "tdd_strategy": "characterization-test",
                "debt": "EPIC-3-DEBT-CHARACTERIZATION-REAL-DISPATCH",
            },
        )

    review_verdict: str | None = None

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runtime = None

        if specialist_name is not None:
            try:
                if use_mock_runtime():
                    # Hash must match what dispatch computes internally: dispatch always
                    # calls spec.primary_agent ("test-author") — AC9/D1 nominal-only.
                    sp_obj = registry.get(spec.primary_agent)
                    if not isinstance(sp_obj, Specialist):
                        raise WorkflowError(
                            f"specialist {spec.primary_agent!r} not found in registry",
                            details={"specialist": spec.primary_agent},
                        )

                    from sdlc.cli._task_pipeline import _make_prompt_builder

                    prompt = _make_prompt_builder(
                        task_text=task_text,
                        story_text=story_text,
                    )(sp_obj, spec)
                    h = compute_prompt_hash(prompt)

                    # Select appropriate mock body based on specialist role
                    if specialist_name == "test-author":
                        body = mock_test_author_body(task_id)
                    elif specialist_name == "characterization-author":
                        body = mock_characterization_author_body(task_id)
                    elif specialist_name == "code-author":
                        body = mock_code_author_body(task_id)
                    else:
                        body = mock_code_reviewer_body()

                    write_mock_fixture(tmp_path, spec.name, h, body)
                # build_runtime runs unconditionally — it selects MockAIRuntime or
                # ClaudeAIRuntime per the env gate. After the ADR-029 default-flip
                # the real runtime is the default; gating this on use_mock_runtime()
                # would abort `sdlc task` in normal operation.
                runtime = build_runtime(fixtures_dir=tmp_path)
            except (WorkflowError, SpecialistError, OSError) as exc:
                emit_error(
                    "ERR_INFRASTRUCTURE",
                    f"mock materialization failed: {exc}",
                    ctx=ctx,
                    details={"cause": str(exc)},
                )

        # Step 9 — Dispatch + write + journal (async core).
        try:
            review_verdict = asyncio.run(
                task_stage_dispatch_write(
                    spec=spec,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    task_id=task_id,
                    task=task,
                    task_path=task_path,
                    task_text=task_text,
                    story_text=story_text,
                    runtime=runtime,
                    registry=registry,
                    hooks=hooks,
                    allow_mock_invoked=allow_mock_invoked,
                )
            )
        except WorkflowError as exc:
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error("ERR_TASK_STAGE_FAILED", str(exc), ctx=ctx, details=wf_details)
        except (KeyboardInterrupt, asyncio.CancelledError, typer.Exit):
            raise
        except OSError as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"task I/O failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )
        except Exception as exc:
            emit_error(
                "ERR_TASK_STAGE_FAILED",
                f"task pipeline failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    # Step 10 — Emit success envelope (AC10).
    next_stage = _NEXT_STAGE[current_stage]
    envelope: dict[str, object] = {
        "phase": 3,
        "track": "task",
        "task_id": task_id,
        "from": current_stage,
        "to": next_stage,
        "specialist": specialist_name,
        "outcome": "success",
    }
    # Surface the review verdict so a programmatic caller (e.g. /sdlc-next) can
    # see a rejected review — the task advances to `review` but is not clean.
    if review_verdict is not None:
        envelope["review_verdict"] = review_verdict
    emit_json("task", envelope, ctx=ctx)
