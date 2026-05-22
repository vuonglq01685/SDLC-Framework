"""Story-writer dispatch pipeline — extracted from cli/stories.py for LOC cap (Story 2A.11 D1).

:mod:`sdlc.cli.stories` retains pre-flight + error-code mapping only.

Patches applied during code review (2026-05-14):
- #2 / D2: ``SDLC_USE_MOCK_RUNTIME`` env gate around v1 mock body
- #5: remap inter-batch ``dependencies`` refs when ``_renumber_for_append`` shifts seq
- #10: elif structure in :func:`apply_signoff_gate`
- #13: strict JSON-array contract (drop silent object→list coercion)
- #16: single ``run_id`` per dispatch batch
- #3 (partial): roll back files written before mid-batch hook denial
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml

from sdlc.cli._epic_story_models import _StoryEntry, serialize_entry
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
from sdlc.errors import IdsError, WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.ids.parsers import parse_epic_id, parse_story_id
from sdlc.journal import append as journal_append
from sdlc.runtime.abc import AIRuntime
from sdlc.runtime.mock import compute_prompt_hash
from sdlc.specialists import SpecialistRegistry

_STORIES_ROOT_REL: Final[str] = "01-Requirement/05-Stories"
_USE_MOCK_ENV: Final[str] = "SDLC_USE_MOCK_RUNTIME"


def use_mock_runtime() -> bool:
    return os.environ.get(_USE_MOCK_ENV, "0") == "1"


def mock_stories_body(epic_id: str) -> str:
    rows = [
        {
            "schema_version": 1,
            "id": f"{epic_id}-S0{seq}-mock-story-{name}",
            "epic_id": epic_id,
            "seq": seq,
            "label": f"Mock story {name}",
            "as_a": "user",
            "i_want": f"feature {chr(ord('A') + seq - 1)}",
            "so_that": "I succeed",
            "given_when_then": [f"Given {ord('x') + seq - 1}\nWhen y\nThen z"],
            "dependencies": [],
            "drafted_at": "2026-01-01T00:00:00.000Z",
            "drafted_by_specialist": "story-writer",
        }
        for seq, name in ((1, "one"), (2, "two"))
    ]
    return json.dumps(rows, ensure_ascii=False)


def story_slug_tail(story_id: str, epic_id: str) -> str:
    m = re.match(rf"^{re.escape(epic_id)}-S\d{{2,3}}-(.+)$", story_id)
    if m is None:
        raise WorkflowError(
            f"story id {story_id!r} does not match epic {epic_id!r}",
            details={"sdlc_stories": "schema_invalid", "story_id": story_id},
        )
    return m.group(1)


def max_existing_story_seq(story_dir: Path, epic_id: str) -> int:
    best = 0
    if not story_dir.is_dir():
        return best
    expected_slug = parse_epic_id(epic_id).epic_slug
    for p in story_dir.glob("*.json"):
        try:
            sid = parse_story_id(p.stem)
        except IdsError:
            continue
        if sid.epic_slug != expected_slug:
            continue
        best = max(best, sid.story_num)
    return best


def parse_story_array(output_text: str) -> list[_StoryEntry]:
    raw = output_text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowError(
            "story-writer output is not valid JSON",
            details={"sdlc_stories": "schema_invalid", "cause": str(exc)},
        ) from exc
    if not isinstance(data, list):  # patch #13: strict array contract
        raise WorkflowError(
            "story-writer output must be a JSON array of story objects",
            details={"sdlc_stories": "schema_invalid", "type": type(data).__name__},
        )
    out: list[_StoryEntry] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise WorkflowError(
                f"story array entry {i} is not an object",
                details={
                    "sdlc_stories": "schema_invalid",
                    "index": i,
                    "type": type(item).__name__,
                },
            )
        try:
            out.append(_StoryEntry.model_validate_json(json.dumps(item, ensure_ascii=False)))
        except Exception as exc:
            raise WorkflowError(
                f"story array entry {i} failed schema validation: {exc}",
                details={"sdlc_stories": "schema_invalid", "index": i, "cause": str(exc)},
            ) from exc
    if not out:
        raise WorkflowError(
            "story-writer returned an empty array",
            details={"sdlc_stories": "schema_invalid"},
        )
    return out


def renumber_for_append(
    raw_entries: list[_StoryEntry],
    *,
    epic_id: str,
    start_seq: int,
) -> list[_StoryEntry]:
    """Assign sequential seq and ids starting at ``start_seq + 1`` (append-only).

    Patch #5: remap inter-batch ``dependencies`` refs so an entry that depended
    on a sibling (by its pre-renumber id) ends up pointing at the renumbered
    sibling instead of an unrelated existing story with the same pre-renumber
    id. References to existing on-disk stories are left untouched.
    """
    id_map: dict[str, str] = {}
    new_ids: list[str] = []
    for offset, raw in enumerate(raw_entries):
        new_seq = start_seq + 1 + offset
        slug = story_slug_tail(raw.id, epic_id)
        new_id = f"{epic_id}-S{new_seq:02d}-{slug}"
        id_map[raw.id] = new_id
        new_ids.append(new_id)

    out: list[_StoryEntry] = []
    for offset, raw in enumerate(raw_entries):
        # mode="json" emits tuples as lists; we round-trip through JSON for
        # validation because StrictModel rejects list-for-tuple coercion in
        # python mode. The JSON serializer's list→tuple coercion is allowed
        # via model_validate_json.
        dumped = raw.model_dump(mode="json")
        dumped["id"] = new_ids[offset]
        dumped["seq"] = start_seq + 1 + offset
        dumped["epic_id"] = epic_id
        deps = dumped.get("dependencies") or []
        if isinstance(deps, list):
            dumped["dependencies"] = [id_map.get(d, d) for d in deps]
        out.append(_StoryEntry.model_validate_json(json.dumps(dumped, ensure_ascii=False)))
    return out


def materialize_mock(
    dest_dir: Path,
    *,
    spec: WorkflowSpec,
    registry: SpecialistRegistry,
    epic_text: str,
    product_text: str,
    epic_id: str,
) -> None:
    sp = registry.get("story-writer")
    prompt = phase1_compound_prompt_builder(
        sp,
        spec,
        primary_input=epic_text,
        secondary_input=product_text,
        role="primary",
    )
    records = {
        compute_prompt_hash(prompt): {
            "output_text": mock_stories_body(epic_id),
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
    epic_text: str,
    product_text: str,
    epic_id: str,
    story_dir: Path,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
    allow_mock_invoked: bool = False,
) -> list[tuple[str, str]]:
    story_dir.mkdir(parents=True, exist_ok=True)
    anchor = story_dir / f"{epic_id}-S01-sdlc-dispatch-anchor.json"

    def _prompt_builder(sp: object, wf: WorkflowSpec) -> str:
        from sdlc.specialists.frontmatter import Specialist

        assert isinstance(sp, Specialist)
        return phase1_compound_prompt_builder(
            sp,
            wf,
            primary_input=epic_text,
            secondary_input=product_text,
            role="primary",
        )

    observer_ctx: dict[str, object] = {}
    merge_observer_mock_audit(observer_ctx, allow_mock_invoked=allow_mock_invoked)
    observer = PanelObserver(
        slash_command="/sdlc-stories",
        idea_text=epic_id,
        extra_context=MappingProxyType(observer_ctx),
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
            f"stories dispatch finished with outcome={result.outcome!r}",
            details={"sdlc_stories": "dispatch_failed", "outcome": result.outcome},
        )

    raw_entries = parse_story_array(result.agent_result.output_text)
    for raw in raw_entries:
        if raw.epic_id != epic_id:
            raise WorkflowError(
                f"story epic_id {raw.epic_id!r} does not match CLI epic {epic_id!r}",
                details={"sdlc_stories": "epic_mismatch", "story_id": raw.id},
            )
        if not raw.id.startswith(f"{epic_id}-S"):
            raise WorkflowError(
                f"story id {raw.id!r} must start with {epic_id}-S",
                details={"sdlc_stories": "epic_mismatch"},
            )

    start = max_existing_story_seq(story_dir, epic_id)
    entries = renumber_for_append(raw_entries, epic_id=epic_id, start_seq=start)

    for e in entries:
        fname = f"{epic_id}-S{e.seq:02d}-{story_slug_tail(e.id, epic_id)}.json"
        if (story_dir / fname).is_file():
            raise WorkflowError(
                f"story file already exists: {fname}",
                details={"sdlc_stories": "collision", "path": str(story_dir / fname)},
            )

    created: list[tuple[str, str]] = []
    written: list[Path] = []
    run_id = str(uuid.uuid4())  # patch #16: one run_id per batch
    try:
        for entry in entries:
            fname = f"{epic_id}-S{entry.seq:02d}-{story_slug_tail(entry.id, epic_id)}.json"
            rel = f"{_STORIES_ROOT_REL}/{epic_id}/{fname}"
            path = root / rel
            payload = build_write_intent_payload(
                hook_name="stories-cli",
                target_path=rel,
                write_intent="create",
                content_hash_before=None,
            )
            decision = await run_hook_chain(payload, hooks=hooks, journal_path=journal_path)
            if decision.decision != "allow":
                raise WorkflowError(
                    "pre-write hook rejected story write",
                    details={
                        "sdlc_stories": "hook_rejected",
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
                        "slash_command": "/sdlc-stories",
                        "phase": 1,
                        "specialist": "story-writer",
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
        for p in written:
            with contextlib.suppress(OSError):
                p.unlink(missing_ok=True)
        raise
    return created
