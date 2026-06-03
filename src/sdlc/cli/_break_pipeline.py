"""`sdlc break` async dispatch pipeline (Story 2A.16, extracted per AC8 LOC budget).

Contains: task-batch validation helpers, dep-DAG cycle detection,
mock body, and the async write loop for /sdlc-break.
Callers: cli/break_.py:run_break.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml
from pydantic import ValidationError

from sdlc.cli._brownfield import classify_tdd_strategy
from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry
from sdlc.cli._runtime_selection import merge_observer_mock_audit
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
from sdlc.errors import WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.ids.parsers import parse_task_id
from sdlc.journal import append as journal_append
from sdlc.runtime.abc import AIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

_SLASH_CMD: Final[str] = "/sdlc-break"
_PRIMARY_SPECIALIST: Final[str] = "task-breaker"
_TASKS_ROOT_REL: Final[str] = "03-Implementation/tasks"


def _validate_task_batch(  # noqa: C901
    records: list[_TaskEntry],
    *,
    request_story_id: str,
) -> None:
    """Validate batch invariants for AC4: story_id, uniqueness, deps, DAG, seq contiguity."""
    if not records:
        raise WorkflowError(
            "task-breaker returned an empty task batch",
            details={"sdlc_break": "empty_batch"},
        )

    seen_ids: set[str] = set()
    task_nums: list[int] = []

    for rec in records:
        # story_id cross-validation
        if rec.story_id != request_story_id:
            raise WorkflowError(
                f"task {rec.id!r} declares wrong story_id {rec.story_id!r} != {request_story_id!r}",
                details={"sdlc_break": "wrong_story_id", "task_id": rec.id},
            )
        # uniqueness
        if rec.id in seen_ids:
            raise WorkflowError(
                f"duplicate task id: {rec.id!r}",
                details={"sdlc_break": "duplicate_task_id", "task_id": rec.id},
            )
        seen_ids.add(rec.id)
        # the story-id encoded in the task id must match the request story
        parsed = parse_task_id(rec.id)
        id_story_prefix = f"EPIC-{parsed.epic_slug}-S{parsed.story_num:02d}-{parsed.story_slug}"
        if id_story_prefix != request_story_id:
            raise WorkflowError(
                f"task {rec.id!r} id encodes story {id_story_prefix!r} "
                f"!= request {request_story_id!r}",
                details={"sdlc_break": "wrong_story_id_in_id", "task_id": rec.id},
            )
        task_nums.append(parsed.task_num)

    # dependency references: all deps must be in the current batch
    for rec in records:
        for dep in rec.dependencies:
            if dep not in seen_ids:
                raise WorkflowError(
                    f"task {rec.id!r} declares dependency {dep!r} not in this batch",
                    details={"sdlc_break": "orphan_dependency", "task_id": rec.id, "dep": dep},
                )

    # DAG cycle detection (Kahn's algorithm, O(V+E))
    _check_dep_dag(records)

    # seq contiguity: must be [1, 2, ..., N] in order
    expected = list(range(1, len(records) + 1))
    if task_nums != expected:
        raise WorkflowError(
            f"task seq gap detected: expected T01..T{len(records):02d}, "
            f"found {[f'T{n:02d}' for n in task_nums]}",
            details={"sdlc_break": "seq_gap", "found": task_nums, "expected": expected},
        )


def _check_dep_dag(records: list[_TaskEntry]) -> None:
    """Reject if dep graph has cycles. O(V+E) Kahn's algorithm."""
    indegree: dict[str, int] = {r.id: 0 for r in records}
    edges: dict[str, list[str]] = {r.id: [] for r in records}
    for r in records:
        for dep in r.dependencies:
            edges[dep].append(r.id)
            indegree[r.id] += 1
    queue = [tid for tid, d in indegree.items() if d == 0]
    visited = 0
    while queue:
        tid = queue.pop()
        visited += 1
        for nxt in edges[tid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if visited != len(records):
        cycle_ids = sorted(tid for tid, d in indegree.items() if d > 0)
        raise WorkflowError(
            f"task dependency cycle detected involving: {cycle_ids!r}",
            details={"sdlc_break": "dep_cycle", "cycle_ids": cycle_ids},
        )


def parse_task_array(output_text: str, *, request_story_id: str) -> list[_TaskEntry]:
    """Parse + validate specialist JSON array of task records (AC4)."""
    raw = output_text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowError(
            "task-breaker output is not valid JSON",
            details={"sdlc_break": "schema_invalid", "cause": str(exc)},
        ) from exc
    if not isinstance(data, list):
        raise WorkflowError(
            "task-breaker output must be a JSON array of task objects",
            details={"sdlc_break": "schema_invalid", "type": type(data).__name__},
        )
    out: list[_TaskEntry] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise WorkflowError(
                f"task array entry {i} is not an object",
                details={"sdlc_break": "schema_invalid", "index": i},
            )
        # Story 3.8 review (F3): the CLI stamps tdd_strategy deterministically (D2), so drop any
        # value the model supplied — an out-of-enum value would otherwise raise ValidationError
        # and abort the whole batch, contradicting task-breaker.md's "it is dropped" contract.
        item_clean = {k: v for k, v in item.items() if k != "tdd_strategy"}
        try:
            out.append(_TaskEntry.model_validate_json(json.dumps(item_clean, ensure_ascii=False)))
        except ValidationError as exc:
            raise WorkflowError(
                f"task array entry {i} failed schema validation: {exc}",
                details={"sdlc_break": "schema_invalid", "index": i, "cause": str(exc)},
            ) from exc
    return out


def mock_task_batch_body(story_id: str) -> str:
    """AC8/D1: mock body for SDLC_USE_MOCK_RUNTIME=1 (default)."""
    return json.dumps(
        [
            {
                "id": f"{story_id}-T01-design-data-model",
                "story_id": story_id,
                "label": "Design the canonical data model.",
                "stage": "pending",
                "dependencies": [],
            },
            {
                "id": f"{story_id}-T02-implement-write-path",
                "story_id": story_id,
                "label": "Implement the write path with validation.",
                "stage": "pending",
                "dependencies": [f"{story_id}-T01-design-data-model"],
            },
            {
                "id": f"{story_id}-T03-implement-read-path",
                "story_id": story_id,
                "label": "Implement the read path with caching.",
                "stage": "pending",
                "dependencies": [f"{story_id}-T01-design-data-model"],
            },
        ],
        ensure_ascii=False,
    )


def write_mock_fixture(dest_dir: Path, name: str, h: str, body: str) -> None:
    records = {h: {"output_text": body, "tokens_in": 1, "tokens_out": 1, "tool_calls": []}}
    atomic_write(
        dest_dir / f"{name}.yaml",
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
    )


async def break_dispatch_write(
    *,
    spec: WorkflowSpec,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    story_id: str,
    story_text: str,
    product_text: str,
    tasks_dir: Path,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
    legacy_code_globs: tuple[str, ...] = (),
    allow_mock_invoked: bool = False,
) -> list[str]:
    """Dispatch task-breaker, validate, write task files, journal entries. Returns task ids.

    Story 3.8 AC1/D2(a): each parsed task is stamped with a deterministic ``tdd_strategy``
    by matching its ``touches`` against ``legacy_code_globs`` (empty globs → all
    ``write-tests-first``, the greenfield regression guard).
    """
    seq_ad = await allocate_seq(journal_path)
    await journal_append(
        make_journal_entry(
            seq=seq_ad,
            ts=now_ts(),
            kind="agent_dispatched",
            target_id=_SLASH_CMD,
            payload={"slash_command": _SLASH_CMD, "phase": 3, "specialist": _PRIMARY_SPECIALIST},
            actor="cli",
        ),
        journal_path,
    )

    observer_ctx: dict[str, object] = {}
    merge_observer_mock_audit(observer_ctx, allow_mock_invoked=allow_mock_invoked)
    observer = PanelObserver(
        slash_command=_SLASH_CMD,
        extra_context=MappingProxyType(observer_ctx),
        emit_agent_dispatched=False,
    )
    result = await dispatch(
        spec,
        runtime=runtime,
        registry=registry,
        repo_root=root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=_make_prompt_builder(story_text=story_text, product_text=product_text),
        hooks=hooks,
        observer=observer,
        persist_artifact=False,
        target_path_override=tasks_dir / ".break-dispatch-anchor",
    )

    if result.outcome != "success":
        raise WorkflowError(
            f"break dispatch finished with outcome={result.outcome!r}",
            details={"sdlc_break": "dispatch_failed", "outcome": result.outcome},
        )

    raw_entries = parse_task_array(result.agent_result.output_text, request_story_id=story_id)
    _validate_task_batch(raw_entries, request_story_id=story_id)

    # Story 3.8 AC1/D2(a): deterministic CLI-side TDD-strategy stamping. The classifier (not
    # the LLM) matches each task's touches against legacy_code_globs so the mock-vs-claude
    # byte identity (2B.3) holds. touches itself is excluded from the serialized task JSON.
    entries = [
        entry.model_copy(
            update={"tdd_strategy": classify_tdd_strategy(entry.touches, legacy_code_globs)}
        )
        for entry in raw_entries
    ]

    tasks_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    task_ids: list[str] = []
    run_id = str(uuid.uuid4())

    try:
        for entry in entries:
            parsed = parse_task_id(entry.id)
            fname = f"T{parsed.task_num:02d}-{parsed.task_slug}.json"
            rel = f"{_TASKS_ROOT_REL}/{story_id}/{fname}"
            path = root / rel

            payload = build_write_intent_payload(
                hook_name="break-cli",
                target_path=rel,
                write_intent="create",
                content_hash_before=None,
            )
            decision = await run_hook_chain(payload, hooks=hooks, journal_path=journal_path)
            if decision.decision != "allow":
                raise WorkflowError(
                    "pre-write hook rejected task write",
                    details={
                        "sdlc_break": "hook_rejected",
                        "hook": decision.hook_name,
                        "reason": decision.reason,
                        "path": rel,
                    },
                )

            text = serialize_task_entry(entry)
            atomic_write(path, text)
            written.append(path)

            seq_aw = await allocate_seq(journal_path)
            await journal_append(
                make_journal_entry(
                    seq=seq_aw,
                    ts=now_ts(),
                    kind="artifact_written",
                    target_id=rel,
                    payload={
                        "slash_command": _SLASH_CMD,
                        "phase": 3,
                        "specialist": _PRIMARY_SPECIALIST,
                        "target": rel,
                        "writer": "cli",
                        "run_id": run_id,
                        "task_id": entry.id,
                    },
                    after_hash=content_hash(text),
                    actor="cli",
                ),
                journal_path,
            )
            task_ids.append(entry.id)

    except (WorkflowError, OSError):
        for p in written:
            with contextlib.suppress(OSError):
                p.unlink(missing_ok=True)
        raise

    seq_done = await allocate_seq(journal_path)
    await journal_append(
        make_journal_entry(
            seq=seq_done,
            ts=now_ts(),
            kind="story_broken_into_tasks",
            target_id=story_id,
            payload={
                "slash_command": _SLASH_CMD,
                "phase": 3,
                "specialist": _PRIMARY_SPECIALIST,
                "story_id": story_id,
                "task_ids": task_ids,
                "task_count": len(task_ids),
            },
            actor="cli",
        ),
        journal_path,
    )

    return task_ids


def _make_prompt_builder(
    *,
    story_text: str,
    product_text: str,
) -> Callable[[Specialist, WorkflowSpec], str]:
    def _builder(sp: Specialist, wf: WorkflowSpec) -> str:
        return phase1_compound_prompt_builder(
            sp,
            wf,
            primary_input=product_text,
            secondary_input=story_text,
            primary_label="PRODUCT_BRIEF",
            secondary_label="STORY_TO_BREAK",
            role="primary",
        )

    return _builder
