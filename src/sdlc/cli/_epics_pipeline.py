"""Epic-generator dispatch pipeline — extracted from cli/epics.py for LOC cap (Story 2A.11 D1).

Holds parsing, materialization, signoff-gate, dispatch + per-file write logic.
:mod:`sdlc.cli.epics` retains pre-flight + error-code mapping only.

Patches applied during code review (2026-05-14):
- #2 / D2: ``SDLC_USE_MOCK_RUNTIME`` env gate around v1 mock body
- #4: reject duplicate epic ids in single specialist response
- #10: elif structure in :func:`apply_signoff_gate`
- #13: strict JSON-array contract (drop silent object→list coercion)
- #16: single ``run_id`` per dispatch batch
- #3 (partial): roll back files written before mid-batch hook denial
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml

from sdlc.cli._epic_story_models import _EpicEntry, serialize_entry
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
    phase1_prompt_builder,
)
from sdlc.errors import WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.journal import append as journal_append
from sdlc.runtime.mock import MockAIRuntime, compute_prompt_hash
from sdlc.specialists import SpecialistRegistry

_EPICS_DIR_REL: Final[str] = "01-Requirement/04-Epics"
_USE_MOCK_ENV: Final[str] = "SDLC_USE_MOCK_RUNTIME"


def use_mock_runtime() -> bool:
    """v1 default-on gate; flip to ``0`` to require a real runtime (2B.1+)."""
    return os.environ.get(_USE_MOCK_ENV, "1") == "1"


def mock_epics_body() -> str:
    return json.dumps(
        [
            {
                "schema_version": 1,
                "id": f"EPIC-sdlc-mock-{letter}",
                "label": f"Mock epic {letter.upper()}",
                "priority": prio,
                "dependencies": [],
                "ordering": idx,
                "acceptance_criteria": [f"Criterion {idx + 1}"],
                "drafted_at": "2026-01-01T00:00:00.000Z",
                "drafted_by_specialist": "epic-generator",
            }
            for idx, (letter, prio) in enumerate([("a", "P1"), ("b", "P2"), ("c", "P3")])
        ],
        ensure_ascii=False,
    )


def parse_epic_array(output_text: str) -> list[_EpicEntry]:
    raw = output_text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowError(
            "epic-generator output is not valid JSON",
            details={"sdlc_epics": "schema_invalid", "cause": str(exc)},
        ) from exc
    if not isinstance(data, list):  # patch #13: strict array contract
        raise WorkflowError(
            "epic-generator output must be a JSON array of epic objects",
            details={"sdlc_epics": "schema_invalid", "type": type(data).__name__},
        )
    out: list[_EpicEntry] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise WorkflowError(
                f"epic array entry {i} is not an object",
                details={"sdlc_epics": "schema_invalid", "index": i, "type": type(item).__name__},
            )
        try:
            out.append(_EpicEntry.model_validate_json(json.dumps(item, ensure_ascii=False)))
        except Exception as exc:
            raise WorkflowError(
                f"epic array entry {i} failed schema validation: {exc}",
                details={"sdlc_epics": "schema_invalid", "index": i, "cause": str(exc)},
            ) from exc
    if not out:
        raise WorkflowError(
            "epic-generator returned an empty array",
            details={"sdlc_epics": "schema_invalid"},
        )
    ids = [e.id for e in out]  # patch #4: dedup gate before write loop
    if len(set(ids)) != len(ids):
        dups = sorted({i for i in ids if ids.count(i) > 1})
        raise WorkflowError(
            f"epic array has duplicate ids: {dups!r}",
            details={"sdlc_epics": "schema_invalid", "duplicate_ids": dups},
        )
    return out


def materialize_mock(
    dest_dir: Path,
    *,
    spec: WorkflowSpec,
    registry: SpecialistRegistry,
    product_text: str,
) -> None:
    sp = registry.get("epic-generator")
    prompt = phase1_prompt_builder(
        sp,
        spec,
        idea_text=product_text,
        role="primary",
        upstream_outputs=(),
    )
    records = {
        compute_prompt_hash(prompt): {
            "output_text": mock_epics_body(),
            "tokens_in": 1,
            "tokens_out": 1,
            "tool_calls": [],
        }
    }
    atomic_write(
        dest_dir / f"{spec.name}.yaml",
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
    )


async def dispatch_and_write(  # noqa: C901
    *,
    spec: WorkflowSpec,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    product_text: str,
    epics_dir: Path,
    runtime: MockAIRuntime,
    registry: SpecialistRegistry,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
) -> list[tuple[str, str]]:
    epics_dir.mkdir(parents=True, exist_ok=True)
    anchor = epics_dir / "EPIC-sdlc-dispatch-anchor.json"

    def _prompt_builder(sp: object, wf: WorkflowSpec) -> str:
        from sdlc.specialists.frontmatter import Specialist

        assert isinstance(sp, Specialist)
        return phase1_prompt_builder(
            sp,
            wf,
            idea_text=product_text,
            role="primary",
            upstream_outputs=(),
        )

    observer = PanelObserver(
        slash_command="/sdlc-epics",
        idea_text=product_text,
        extra_context=MappingProxyType({}),
        emit_agent_dispatched=True,
    )
    result = await dispatch(
        spec,
        runtime=runtime,
        registry=registry,
        repo_root=root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=_prompt_builder,
        hooks=hooks,
        observer=observer,
        persist_artifact=False,
        target_path_override=anchor,
    )
    if result.outcome != "success":
        raise WorkflowError(
            f"epics dispatch finished with outcome={result.outcome!r}",
            details={"sdlc_epics": "dispatch_failed", "outcome": result.outcome},
        )

    entries = parse_epic_array(result.agent_result.output_text)
    for e in entries:
        p = epics_dir / f"{e.id}.json"
        if p.is_file():
            raise WorkflowError(
                f"epic file already exists: {p.name}",
                details={"sdlc_epics": "collision", "path": str(p), "id": e.id},
            )

    created: list[tuple[str, str]] = []
    written: list[Path] = []
    run_id = str(uuid.uuid4())  # patch #16: one run_id per batch
    try:
        for entry in entries:
            rel = f"{_EPICS_DIR_REL}/{entry.id}.json"
            path = root / rel
            payload = build_write_intent_payload(
                hook_name="epics-cli",
                target_path=rel,
                write_intent="create",
                content_hash_before=None,
            )
            decision = await run_hook_chain(payload, hooks=hooks, journal_path=journal_path)
            if decision.decision != "allow":
                raise WorkflowError(
                    "pre-write hook rejected epic write",
                    details={
                        "sdlc_epics": "hook_rejected",
                        "hook": decision.hook_name,
                        "reason": decision.reason,
                        "path": rel,
                    },
                )
            text = serialize_entry(entry)
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
                        "slash_command": "/sdlc-epics",
                        "phase": 1,
                        "specialist": "epic-generator",
                        "entry_id": entry.id,
                        "schema_version": 1,
                        "target": rel,
                        "writer": "cli",
                        "run_id": run_id,
                    },
                    after_hash=content_hash(text),
                    actor="cli",
                ),
                journal_path,
            )
            created.append((entry.id, rel))
    except WorkflowError:
        # patch #3 (partial): roll back files written before mid-batch denial.
        # Journal entries already appended remain (append-only log); the
        # restored directory lets postcondition `epics_dir_non_empty` surface
        # the failure cleanly instead of masking it with half-written state.
        for p in written:
            with contextlib.suppress(OSError):
                p.unlink(missing_ok=True)
        raise
    return created
