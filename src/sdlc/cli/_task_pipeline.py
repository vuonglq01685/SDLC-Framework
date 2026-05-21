"""`sdlc task` async dispatch pipeline (Story 2A.17).

Contains: stage→specialist maps and the async write loop for /sdlc-task.
Callers: cli/task.py:run_task.

AC9/D1: CLI owns the stage→specialist map; workflow YAML primary_agent is nominal only.
AC4/D1: RED→GREEN gate trusts specialist self-report (EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION).
AC6/D1: task JSON stage field is state-of-record; state.json not written
  (EPIC-2A-DEBT-TASK-STATE-PROJECTION).
AC8/D1: review_verdict/review_notes are real serialized fields on _TaskEntry.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Final

from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry
from sdlc.cli._task_pipeline_parsers import (
    parse_files_result,
    parse_review_result,
    validate_file_prefix,
)
from sdlc.concurrency.io_primitives import atomic_write
from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import (
    PanelObserver,
    allocate_seq,
    content_hash,
    dispatch,
    make_journal_entry,
    now_ts,
    phase1_compound_prompt_builder,
)
from sdlc.errors import SpecialistError, WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.journal import append as journal_append
from sdlc.runtime.mock import MockAIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

_SLASH_CMD: Final[str] = "/sdlc-task"
_TASKS_ROOT_REL: Final[str] = "03-Implementation/tasks"

# AC9/D1: CLI owns stage→specialist dispatch map; workflow YAML primary_agent is nominal.
_STAGE_SPECIALIST: Final[dict[str, str | None]] = {
    "pending": "test-author",
    "write-tests": "code-author",
    "write-code": "code-reviewer",
    "review": None,  # pure state advance, no dispatch
}

_NEXT_STAGE: Final[dict[str, str]] = {
    "pending": "write-tests",
    "write-tests": "write-code",
    "write-code": "review",
    "review": "done",
}


async def task_stage_dispatch_write(  # noqa: C901, PLR0912, PLR0915
    *,
    spec: WorkflowSpec,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    task_id: str,
    task: _TaskEntry,
    task_path: Path,
    task_text: str,
    story_text: str,
    runtime: MockAIRuntime | None,
    registry: SpecialistRegistry,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
) -> str | None:
    """Execute one stage advance: dispatch specialist (if any), write files, update task JSON,
    and journal.

    Returns the captured review verdict when the stage produced one (write-code →
    review), else None.
    """
    current_stage = task.stage
    # Independent terminal/unknown-stage guard: run_task already refuses `done`,
    # but this coroutine is public — a direct call with a non-advanceable stage
    # must raise a structured error, not a bare KeyError on the maps below.
    if current_stage not in _NEXT_STAGE:
        raise WorkflowError(
            f"task {task_id} is at terminal or unknown stage {current_stage!r}; "
            "no stage transition is possible",
            details={"task_id": task_id, "stage": current_stage},
        )
    next_stage = _NEXT_STAGE[current_stage]
    specialist_name = _STAGE_SPECIALIST[current_stage]

    written: list[Path] = []
    # Tracks whether the task JSON has been rewritten, so a failure after the rewrite
    # can restore the original on-disk content (AC7: stage left UNCHANGED on failure).
    task_rewritten = False
    # Accumulate field updates; applied via model_copy at write time (StrictModel is frozen).
    update_fields: dict[str, object] = {}
    # One run_id per invocation — correlates artifact_written with the stage outcome.
    run_id = str(uuid.uuid4())
    # Review verdict captured this stage (write-code → review), surfaced to the caller.
    captured_verdict: str | None = None

    try:
        if specialist_name is not None:
            # Dispatch stage — run_task supplies a runtime for every dispatch stage;
            # guard explicitly so a misuse fails loud rather than at dispatch().
            if runtime is None:
                raise WorkflowError(
                    f"no runtime provided for dispatch stage {current_stage!r}",
                    details={"task_id": task_id, "stage": current_stage},
                )
            observer = PanelObserver(slash_command=_SLASH_CMD, emit_agent_dispatched=False)
            result = await dispatch(
                spec,
                runtime=runtime,
                registry=registry,
                repo_root=root,
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                prompt_builder=_make_prompt_builder(
                    task_text=task_text,
                    story_text=story_text,
                ),
                hooks=hooks,
                observer=observer,
                persist_artifact=False,
                # target must be within primary_agent's (test-author) write_globs ("tests/**").
                # AC9/D1: primary_agent is nominal-only; all stages route through test-author.
                target_path_override=root / "tests" / f".sdlc-task-dispatch-{current_stage}",
            )

            if result.outcome != "success":
                raise WorkflowError(
                    f"task dispatch finished with outcome={result.outcome!r} "
                    f"at stage {current_stage!r}",
                    details={"task_id": task_id, "stage": current_stage, "outcome": result.outcome},
                )

            output_text = result.agent_result.output_text

            if current_stage in ("pending", "write-tests"):
                # test-author or code-author: files + tests_status
                expected_prefix = "tests/" if current_stage == "pending" else "src/"
                files_result = parse_files_result(output_text, specialist=specialist_name)

                # Validate per-stage path prefix + reject duplicate paths
                # (a repeated path would silently overwrite and double-journal).
                seen_paths: set[str] = set()
                for fspec in files_result.files:
                    if fspec.path in seen_paths:
                        raise WorkflowError(
                            f"{specialist_name} returned a duplicate file path: {fspec.path!r}",
                            details={"specialist": specialist_name, "path": fspec.path},
                        )
                    seen_paths.add(fspec.path)
                    validate_file_prefix(
                        fspec.path, expected_prefix=expected_prefix, specialist=specialist_name
                    )

                # RED→GREEN gate enforcement (AC4/D1)
                if current_stage == "pending":
                    if files_result.tests_status != "red":
                        raise WorkflowError(
                            f"test-author reported tests_status={files_result.tests_status!r}"
                            " (expected 'red'); "
                            "TDD discipline violated — tests must fail before implementation",
                            details={"task_id": task_id, "tests_status": files_result.tests_status},
                        )
                # write-tests stage: code-author must report green
                elif files_result.tests_status != "green":
                    raise WorkflowError(
                        f"code-author reported tests_status={files_result.tests_status!r}"
                        " (expected 'green'); "
                        "implementation did not turn the test suite GREEN; "
                        f"rerun '/sdlc-task {task_id}'",
                        details={
                            "task_id": task_id,
                            "stage": current_stage,
                            "tests_status": files_result.tests_status,
                            "debt": "EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION",
                        },
                    )

                # Write stage files through hook chain
                for fspec in files_result.files:
                    path = root / fspec.path
                    path.parent.mkdir(parents=True, exist_ok=True)

                    hook_payload = build_write_intent_payload(
                        hook_name="task-cli",
                        target_path=fspec.path,
                        write_intent="create",
                        content_hash_before=None,
                    )
                    decision = await run_hook_chain(
                        hook_payload, hooks=hooks, journal_path=journal_path
                    )
                    if decision.decision != "allow":
                        raise WorkflowError(
                            "pre-write hook rejected task stage file write",
                            details={
                                "task_id": task_id,
                                "hook": decision.hook_name,
                                "reason": decision.reason,
                                "path": fspec.path,
                            },
                        )

                    atomic_write(path, fspec.content)
                    written.append(path)

                    seq_aw = await allocate_seq(journal_path)
                    await journal_append(
                        make_journal_entry(
                            seq=seq_aw,
                            ts=now_ts(),
                            kind="artifact_written",
                            target_id=fspec.path,
                            payload={
                                "slash_command": _SLASH_CMD,
                                "phase": 3,
                                "specialist": specialist_name,
                                "target": fspec.path,
                                "writer": "cli",
                                "run_id": run_id,
                                "task_id": task_id,
                            },
                            after_hash=content_hash(fspec.content),
                            actor="cli",
                        ),
                        journal_path,
                    )

                update_fields["stage"] = next_stage

            elif current_stage == "write-code":
                # code-reviewer: verdict + notes
                review_result = parse_review_result(output_text)
                update_fields["stage"] = next_stage
                update_fields["review_verdict"] = review_result.verdict
                update_fields["review_notes"] = review_result.notes
                captured_verdict = review_result.verdict

        else:
            # review → done: pure state advance, gate on review_verdict
            if current_stage != "review":
                raise WorkflowError(
                    f"unexpected no-dispatch stage {current_stage!r}; expected 'review'",
                    details={"task_id": task_id, "stage": current_stage},
                )
            task_json_path_str = str(task_path)
            if task.review_verdict is None:
                raise WorkflowError(
                    f"no review verdict recorded for {task_id}: the write-code → review "
                    f"stage has not completed; rerun '/sdlc-task {task_id}' from the "
                    "write-code stage first",
                    details={
                        "task_id": task_id,
                        "review_verdict": None,
                        "task_json_path": task_json_path_str,
                    },
                )
            if task.review_verdict != "approved":
                raise WorkflowError(
                    f"review rejected for {task_id}: see notes in {task_json_path_str}; "
                    f"address the feedback and rerun '/sdlc-task {task_id}'",
                    details={
                        "task_id": task_id,
                        "review_verdict": task.review_verdict,
                        "task_json_path": task_json_path_str,
                    },
                )
            update_fields["stage"] = next_stage

        # Rewrite task JSON via model_copy (StrictModel is frozen — no direct mutation, AC7)
        updated_task = task.model_copy(update=update_fields)
        task_text_new = serialize_task_entry(updated_task)
        atomic_write(task_path, task_text_new)
        task_rewritten = True

        # Journal task_stage_advanced
        payload: dict[str, object] = {
            "task": task_id,
            "from": current_stage,
            "to": next_stage,
            "specialist": specialist_name,
            "run_id": run_id,
        }
        if current_stage == "write-code":
            payload["verdict"] = update_fields.get("review_verdict")
        seq_done = await allocate_seq(journal_path)
        await journal_append(
            make_journal_entry(
                seq=seq_done,
                ts=now_ts(),
                kind="task_stage_advanced",
                target_id=task_id,
                payload=payload,
                actor="cli",
            ),
            journal_path,
        )

    except (WorkflowError, SpecialistError, ValueError, OSError) as exc:
        # Rollback written files (AC7)
        for p in written:
            with contextlib.suppress(OSError):
                p.unlink(missing_ok=True)
        # Restore the original task JSON if it was already rewritten before the failure
        # (AC7: the stage field must be left UNCHANGED on any stage-transition failure).
        if task_rewritten:
            with contextlib.suppress(OSError):
                atomic_write(task_path, task_text)
        # Journal task_stage_failed (AC7) — best-effort; ignore journal I/O errors
        with contextlib.suppress(Exception):
            seq_fail = await allocate_seq(journal_path)
            await journal_append(
                make_journal_entry(
                    seq=seq_fail,
                    ts=now_ts(),
                    kind="task_stage_failed",
                    target_id=task_id,
                    payload={
                        "task": task_id,
                        "stage": current_stage,
                        "reason": str(exc),
                        "run_id": run_id,
                    },
                    actor="cli",
                ),
                journal_path,
            )
        raise

    return captured_verdict


def _make_prompt_builder(
    *,
    task_text: str,
    story_text: str,
) -> Callable[[Specialist, WorkflowSpec], str]:
    def _builder(sp: Specialist, wf: WorkflowSpec) -> str:
        return phase1_compound_prompt_builder(
            sp,
            wf,
            primary_input=task_text,
            secondary_input=story_text,
            primary_label="TASK_TO_IMPLEMENT",
            secondary_label="STORY_CONTEXT",
            role="primary",
        )

    return _builder
