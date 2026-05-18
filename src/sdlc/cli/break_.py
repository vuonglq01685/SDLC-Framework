"""`sdlc break <STORY-id>` — Phase 3 just-in-time task generation (FR16, Story 2A.16).

AC2/D1: story must have status=="in-progress"; missing/pending/done → refuse.
AC3/D1: idempotency guard — refuse if tasks dir already has T*-*.json files.
AC8/D1: mock runtime default (SDLC_USE_MOCK_RUNTIME=1).
DEBT: EPIC-2A-DEBT-BREAK-MANUAL-STATUS-FLIP — user must manually set status to
  "in-progress" until Story 2A.18 (/sdlc-next) implements the automatic flip.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._boundary import artifact_contains_boundary
from sdlc.cli._break_pipeline import (
    _PRIMARY_SPECIALIST,
    _SLASH_CMD,
    _TASKS_ROOT_REL,
    break_dispatch_write,
    mock_task_batch_body,
    write_mock_fixture,
)
from sdlc.cli._epic_story_models import _StoryEntry
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import emit_error, emit_json
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import (
    build_pre_write_hook_chain,
    phase1_compound_prompt_builder,
)
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import SignoffError, SpecialistError, WorkflowError
from sdlc.ids.parsers import STORY_ID_PATTERN, STORY_ID_REGEX, parse_story_id
from sdlc.runtime.mock import MockAIRuntime, compute_prompt_hash
from sdlc.signoff import SignoffState, compute_state
from sdlc.specialists import load_registry
from sdlc.specialists.frontmatter import Specialist
from sdlc.workflows.registry import WorkflowRegistry

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_PRODUCT_REL: Final[str] = "01-Requirement/01-PRODUCT.md"
_STORIES_ROOT_REL: Final[str] = "01-Requirement/05-Stories"
_USE_MOCK_ENV: Final[str] = "SDLC_USE_MOCK_RUNTIME"


def _use_mock_runtime() -> bool:
    return os.environ.get(_USE_MOCK_ENV, "1") == "1"


def _story_is_active(story: _StoryEntry) -> bool:
    """Return True iff story status is 'in-progress' (AC2/D1 gate)."""
    return story.status == "in-progress"


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg

    return Path(pkg.__file__).resolve().parent


def _story_path(root: Path, story_id: str) -> Path:
    parsed = parse_story_id(story_id)
    epic_id = f"EPIC-{parsed.epic_slug}"
    fname = f"{story_id}.json"
    return root / _STORIES_ROOT_REL / epic_id / fname


def run_break(*, ctx: typer.Context, story_id: str) -> None:  # noqa: C901, PLR0912, PLR0915
    """Phase 3 just-in-time story→tasks breakdown (FR16)."""
    root = _get_repo_root_or_cwd()
    journal_path = root / _JOURNAL_REL
    agent_runs_path = root / _RUNS_REL

    # Step 1 — Validate STORY-id format (AC1).
    if STORY_ID_REGEX.match(story_id) is None:
        emit_error(
            "ERR_USER_INPUT",
            f"invalid STORY-id: {story_id}; expected pattern {STORY_ID_PATTERN}",
            ctx=ctx,
            details={"story_id": story_id, "expected_pattern": STORY_ID_PATTERN},
        )

    # Step 2 — Init guard.
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
            f"phase 2 signoff must be APPROVED before breaking a story into tasks; "
            f"current state: {phase2_state.value}.",
            ctx=ctx,
            details={"phase2_state": str(phase2_state)},
        )

    # Step 4 — Load PRODUCT.md (AC8).
    product_path = root / _PRODUCT_REL
    if not product_path.is_file():
        emit_error("ERR_USER_INPUT", f"missing {_PRODUCT_REL}; run 'sdlc start' first", ctx=ctx)
    try:
        product_text = product_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        emit_error("ERR_ARTIFACT_UNREADABLE", str(exc), ctx=ctx, details={"cause": str(exc)})
    if artifact_contains_boundary(product_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"{_PRODUCT_REL} contains the data-vs-instruction boundary marker",
            ctx=ctx,
        )

    # Step 5 — Load and validate story (AC2).
    story_path = _story_path(root, story_id)
    if not story_path.is_file():
        emit_error(
            "ERR_USER_INPUT",
            f"story not found: {story_id}; expected at {story_path}",
            ctx=ctx,
            details={"story_id": story_id, "path": str(story_path)},
        )
    try:
        story_text = story_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        emit_error("ERR_ARTIFACT_UNREADABLE", str(exc), ctx=ctx, details={"cause": str(exc)})
    if artifact_contains_boundary(story_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"story JSON {story_path.name} contains the data-vs-instruction boundary marker",
            ctx=ctx,
        )
    try:
        story = _StoryEntry.model_validate_json(story_text)
    except Exception as exc:
        emit_error(
            "ERR_USER_INPUT",
            f"story JSON parse failed: {exc}",
            ctx=ctx,
            details={"story_id": story_id, "cause": str(exc)},
        )
    if not _story_is_active(story):
        emit_error(
            "ERR_USER_INPUT",
            "story not active; use '/sdlc-next' to advance",
            ctx=ctx,
            details={
                "story_id": story_id,
                "status": story.status,
                "debt": "EPIC-2A-DEBT-BREAK-MANUAL-STATUS-FLIP",
            },
        )

    # Step 6 — Idempotency guard (AC3).
    tasks_dir = root / _TASKS_ROOT_REL / story_id
    existing_tasks = sorted(tasks_dir.glob("T*-*.json")) if tasks_dir.is_dir() else []
    if existing_tasks:
        emit_error(
            "ERR_USER_INPUT",
            f"story already broken into {len(existing_tasks)} tasks; "
            "use '/sdlc-next' to advance through tasks",
            ctx=ctx,
            details={
                "story_id": story_id,
                "tasks_dir": str(tasks_dir),
                "task_count": len(existing_tasks),
            },
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

    # Step 8 — Mock runtime materialization (AC8/D1).
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            if _use_mock_runtime():
                sp_obj = registry.get(_PRIMARY_SPECIALIST)
                if not isinstance(sp_obj, Specialist):
                    raise WorkflowError(
                        f"specialist {_PRIMARY_SPECIALIST!r} not found in registry",
                        details={"specialist": _PRIMARY_SPECIALIST},
                    )

                def _prompt_builder(sp: Specialist, wf: WorkflowSpec) -> str:
                    return phase1_compound_prompt_builder(
                        sp,
                        wf,
                        primary_input=product_text,
                        secondary_input=story_text,
                        primary_label="PRODUCT_BRIEF",
                        secondary_label="STORY_TO_BREAK",
                        role="primary",
                    )

                mock_prompt = _prompt_builder(sp_obj, spec)
                write_mock_fixture(
                    tmp_path,
                    spec.name,
                    compute_prompt_hash(mock_prompt),
                    mock_task_batch_body(story_id),
                )
                runtime: MockAIRuntime = MockAIRuntime(tmp_path)
            else:
                emit_error("ERR_INFRASTRUCTURE", "real runtime not available in v1", ctx=ctx)
        except (WorkflowError, SpecialistError, OSError) as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"mock materialization failed: {exc}",
                ctx=ctx,
                details={"cause": str(exc)},
            )

        # Step 9 — Dispatch + validate + write (async core).
        try:
            task_ids = asyncio.run(
                break_dispatch_write(
                    spec=spec,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    story_id=story_id,
                    story_text=story_text,
                    product_text=product_text,
                    tasks_dir=tasks_dir,
                    runtime=runtime,
                    registry=registry,
                    hooks=hooks,
                )
            )
        except WorkflowError as exc:
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error("ERR_BREAK_DISPATCH_FAILED", str(exc), ctx=ctx, details=wf_details)
        except (KeyboardInterrupt, asyncio.CancelledError, typer.Exit):
            raise
        except OSError as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"break I/O failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )
        except Exception as exc:
            emit_error(
                "ERR_BREAK_DISPATCH_FAILED",
                f"break pipeline failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    # Step 10 — Postconditions.
    try:
        evaluate_postconditions(
            spec,
            repo_root=root,
            agent_runs_path=agent_runs_path.resolve(),
        )
    except WorkflowError as exc:
        post_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition failed: {exc}",
            ctx=ctx,
            details=post_details,
        )
    except (RuntimeError, OSError) as exc:
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition wiring incomplete: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )

    # Step 11 — Emit success (AC6). Journal entry story_broken_into_tasks is written
    # inside break_dispatch_write to mirror bootstrap_completed placement pattern.
    emit_json(
        "break",
        {
            "phase": 3,
            "track": "break",
            "specialist": _PRIMARY_SPECIALIST,
            "story_id": story_id,
            "task_ids": task_ids,
            "task_count": len(task_ids),
            "outcome": "success",
        },
        ctx=ctx,
    )
