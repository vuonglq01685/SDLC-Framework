"""`sdlc bootstrap` async dispatch pipeline (Story 2A.15, extracted per AC10 LOC budget).

Contains: constants, record validator, mock helpers, and the async write loop.
Callers: cli/bootstrap.py:run_bootstrap.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Final

import yaml

from sdlc.concurrency.io_primitives import atomic_write
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import (
    PanelObserver,
    allocate_seq,
    content_hash,
    dispatch,
    make_journal_entry,
    now_ts,
)
from sdlc.errors import WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.journal import append as journal_append
from sdlc.runtime.mock import MockAIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

_SLASH_CMD: Final[str] = "/sdlc-bootstrap"
_PRIMARY_SPECIALIST: Final[str] = "code-bootstrapper"

# AC6: allowed path prefixes for bootstrapped files.
_ALLOWED_PREFIXES: Final[tuple[str, ...]] = ("src/", "tests/")

# Minimum path depth: must be at least <root>/<filename> (e.g. src/foo.py)
_MIN_PATH_PARTS: Final[int] = 2


def _validate_bootstrap_record(record: object) -> tuple[Path, str]:  # noqa: C901
    """Validate a single write-record from the specialist (AC6)."""
    if not isinstance(record, dict):
        raise WorkflowError(f"bootstrap record not a dict: {record!r}")
    path_raw = record.get("path")
    content = record.get("content")
    if not isinstance(path_raw, str) or not path_raw:
        raise WorkflowError(f"bootstrap record missing 'path': {record!r}")
    if not isinstance(content, str):
        raise WorkflowError(f"bootstrap record missing 'content' for path={path_raw!r}")
    normalized = path_raw.replace("\\", "/")
    if "\x00" in normalized:
        raise WorkflowError(f"bootstrap path contains null byte: {path_raw!r}")
    if normalized.startswith("/"):
        raise WorkflowError(f"bootstrap path must be relative: {path_raw!r}")
    parts = PurePosixPath(normalized).parts
    if any(p == ".." for p in parts):
        raise WorkflowError(f"bootstrap path contains '..' traversal: {path_raw!r}")
    if len(parts) < _MIN_PATH_PARTS:
        raise WorkflowError(
            f"bootstrap path must include a filename under src/ or tests/: {path_raw!r}"
        )
    if not any(normalized.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        raise WorkflowError(
            f"bootstrap path outside allowed roots {_ALLOWED_PREFIXES}: {path_raw!r}"
        )
    return Path(normalized), content


def _mock_bootstrap_body() -> str:
    """AC8/D1: writes src/__init__.py (non-placeholder) so re-run auto-skips."""
    return json.dumps(
        [
            {"path": "src/__init__.py", "content": "# placeholder\n"},
            {"path": "tests/.gitkeep", "content": ""},
            {"path": "tests/conftest.py", "content": "# bootstrap placeholder\n"},
        ]
    )


def _write_mock_fixture(dest_dir: Path, name: str, h: str, body: str) -> None:
    records = {h: {"output_text": body, "tokens_in": 1, "tokens_out": 1, "tool_calls": []}}
    atomic_write(
        dest_dir / f"{name}.yaml",
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
    )


async def _bootstrap_dispatch_write(
    *,
    spec: WorkflowSpec,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    source_root: Path,
    registry: SpecialistRegistry,
    hooks: tuple[Callable[..., HookDecision], ...],
    runtime: MockAIRuntime,
    prompt_builder: Callable[[Specialist, WorkflowSpec], str],
) -> int:
    """Dispatch code-bootstrapper, write each record, journal entries. Returns files_written."""
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

    observer = PanelObserver(slash_command=_SLASH_CMD, emit_agent_dispatched=False)
    result = await dispatch(
        spec,
        runtime=runtime,
        registry=registry,
        repo_root=root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=prompt_builder,
        hooks=hooks,
        observer=observer,
        persist_artifact=False,
        target_path_override=root / "src" / ".bootstrap-dispatch-anchor",
    )

    if result.outcome != "success":
        raise WorkflowError(
            f"bootstrap dispatch finished with outcome={result.outcome!r}",
            details={"outcome": result.outcome},
        )

    try:
        raw = json.loads(result.agent_result.output_text)
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise WorkflowError(f"bootstrap specialist returned invalid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise WorkflowError("bootstrap specialist must return a JSON array of write-records")

    validated: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for rec in raw:
        rel_path, file_content = _validate_bootstrap_record(rec)
        key = str(rel_path)
        if key in seen:
            raise WorkflowError(f"duplicate bootstrap path: {key!r}")
        seen.add(key)
        validated.append((rel_path, file_content))

    run_id = str(uuid.uuid4())
    for rel_path, file_content in validated:
        abs_path = root / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        rel_str = str(rel_path)
        payload = build_write_intent_payload(
            hook_name="bootstrap-cli",
            target_path=rel_str,
            write_intent="create",
            content_hash_before=None,
        )
        decision = await run_hook_chain(payload, hooks=hooks, journal_path=journal_path)
        if decision.decision != "allow":
            raise WorkflowError(
                "pre-write hook rejected bootstrap write",
                details={"hook": decision.hook_name, "reason": decision.reason, "path": rel_str},
            )
        atomic_write(abs_path, file_content)
        seq_aw = await allocate_seq(journal_path)
        await journal_append(
            make_journal_entry(
                seq=seq_aw,
                ts=now_ts(),
                kind="artifact_written",
                target_id=rel_str,
                payload={
                    "slash_command": _SLASH_CMD,
                    "phase": 3,
                    "specialist": _PRIMARY_SPECIALIST,
                    "target": rel_str,
                    "writer": "cli",
                    "run_id": run_id,
                },
                after_hash=content_hash(file_content),
                actor="cli",
            ),
            journal_path,
        )

    source_root_rel = str(source_root.relative_to(root))
    seq_bc = await allocate_seq(journal_path)
    await journal_append(
        make_journal_entry(
            seq=seq_bc,
            ts=now_ts(),
            kind="bootstrap_completed",
            target_id="bootstrap",
            payload={
                "slash_command": _SLASH_CMD,
                "phase": 3,
                "specialist": _PRIMARY_SPECIALIST,
                "files_written": len(validated),
                "source_root": source_root_rel,
            },
            actor="cli",
        ),
        journal_path,
    )

    return len(validated)
