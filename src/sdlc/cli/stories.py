"""`sdlc stories` — Phase 1 story JSON generation (Story 2A.11, FR10, AC5).

Dispatch / parse / per-file write logic lives in :mod:`sdlc.cli._stories_pipeline`
so this module stays under the AC8 LOC cap.

Append-only seq policy: gaps in existing seq are preserved (e.g. dir has S01,
S03 → next run starts at S04). Code review 2026-05-14 accepted this as the v1
contract — see ADR notes and review-findings section in the story file.

Patches applied during code review (2026-05-14):
- #6  validate existing epic JSON via :class:`_EpicEntry` before prompt injection
- #7  empty PRODUCT.md / epic JSON → ``ERR_USER_INPUT``
- #8  ``UnicodeDecodeError`` → ``ERR_ARTIFACT_UNREADABLE``
- #9  guard ``pre is None`` before reading ``pre.next_monotonic_seq``
- #11 unknown ``WorkflowError`` sub-category defaults to ``ERR_INFRASTRUCTURE``
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from typer import Context

from sdlc.cli import _stories_pipeline as _pipeline
from sdlc.cli._boundary import artifact_contains_boundary as _artifact_contains_boundary
from sdlc.cli._epic_story_models import _EpicEntry
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.dispatcher import build_pre_write_hook_chain
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import IdsError, SignoffError, StateError, WorkflowError
from sdlc.ids.parsers import parse_epic_id
from sdlc.signoff import SignoffState, compute_state  # re-export for test patching
from sdlc.specialists import load_registry
from sdlc.state.reader import read_state_or_refuse
from sdlc.workflows.registry import WorkflowRegistry

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_PRODUCT_REL: Final[str] = "01-Requirement/01-PRODUCT.md"
_EPICS_DIR_REL: Final[str] = "01-Requirement/04-Epics"
_STORIES_ROOT_REL: Final[str] = "01-Requirement/05-Stories"

__all__ = ("SignoffState", "compute_state", "run_stories")


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg  # deferred

    return Path(pkg.__file__).resolve().parent


def _read_utf8(path: Path, rel: str, ctx: Context) -> str:
    """Patch #8: explicit error mapping for non-UTF-8 / empty artifacts."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"{rel} is not valid UTF-8: {exc}",
            ctx=ctx,
            details={"path": str(path), "cause": str(exc)},
        )
        return ""  # type: ignore[unreachable]  # emit_error raises typer.Exit
    if not text.strip():
        emit_error(
            "ERR_USER_INPUT",
            f"{rel} is empty; populate it before /sdlc-stories",
            ctx=ctx,
            details={"path": str(path)},
        )
        return ""  # type: ignore[unreachable]  # emit_error raises typer.Exit
    return text


def _validate_epic_payload(epic_text: str, epic_path: Path, ctx: Context) -> None:
    """Patch #6: refuse to forward a malformed epic into the story-writer prompt."""
    try:
        _EpicEntry.model_validate_json(epic_text)
    except Exception as exc:
        emit_error(
            "ERR_EPIC_SCHEMA_INVALID",
            f"epic JSON at {epic_path} failed schema validation: {exc}",
            ctx=ctx,
            details={"path": str(epic_path), "cause": str(exc)},
        )


def _apply_signoff_gate(*, root: Path, ctx: Context) -> None:
    """Inlined so tests can patch ``sdlc.cli.stories.compute_state`` directly."""
    try:
        st = compute_state(1, repo_root=root)
    except SignoffError as exc:
        details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_SIGNOFF_STATE",
            f"cannot read phase-1 signoff state: {exc}",
            ctx=ctx,
            details=details,
        )
        return  # type: ignore[unreachable]
    if st == SignoffState.APPROVED:
        emit_error(
            "ERR_PHASE1_ALREADY_APPROVED",
            "phase 1 signoff is APPROVED; adding stories is a hash-drift event. "
            "Run 'sdlc replan' to invalidate signoff for the stories scope first, "
            "then re-run /sdlc-stories.",
            ctx=ctx,
        )
        return  # type: ignore[unreachable]
    if st == SignoffState.DRAFTED_NOT_APPROVED:
        echo(
            "[WARN] phase 1 signoff is drafted but not approved; adding stories "
            "will require signoff re-draft.",
            err=True,
            ctx=ctx,
        )


def _map_workflow_error(exc: WorkflowError, ctx: Context) -> None:
    details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
    sub = details.get("sdlc_stories")
    if sub == "schema_invalid":
        emit_error("ERR_STORY_SCHEMA_INVALID", str(exc), ctx=ctx, details=details)
    elif sub == "hook_rejected":
        emit_error("ERR_HOOK_REJECTED", str(exc), ctx=ctx, details=details)
    elif sub == "dispatch_failed":
        emit_error("ERR_STORIES_DISPATCH_FAILED", str(exc), ctx=ctx, details=details)
    elif sub == "collision":
        emit_error("ERR_USER_INPUT", str(exc), ctx=ctx, details=details)
    elif sub == "epic_mismatch":
        emit_error("ERR_STORY_EPIC_MISMATCH", str(exc), ctx=ctx, details=details)
    else:
        emit_error("ERR_INFRASTRUCTURE", str(exc), ctx=ctx, details=details)


def run_stories(*, ctx: Context, epic_id: str, allow_mock: bool = False) -> None:  # noqa: C901, PLR0912, PLR0915
    """Generate story JSON files for one epic under ``01-Requirement/05-Stories/<id>/``."""
    from sdlc.cli._runtime_selection import build_runtime, enforce_allow_mock_gate
    from sdlc.journal._seq import _read_highest_seq

    allow_mock_invoked = enforce_allow_mock_gate(allow_mock=allow_mock, ctx=ctx)
    from sdlc.state import read_state_or_recover, write_state_atomic_sync

    ctx_obj: Mapping[str, object] = ctx.obj if isinstance(ctx.obj, Mapping) else {}
    json_mode = bool(ctx_obj.get("json", False))
    root = _get_repo_root_or_cwd()
    state_path = root / _STATE_REL
    journal_path = (root / _JOURNAL_REL).resolve()
    agent_runs_path = (root / _RUNS_REL).resolve()

    if not state_path.is_file():
        emit_error(
            "ERR_NOT_INITIALIZED",
            "no .claude/state/state.json found; run 'sdlc init' first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    state = read_state_or_refuse(state_path)
    if state is None:
        emit_error(
            "ERR_NOT_INITIALIZED",
            "no .claude/state/state.json found; run 'sdlc init' first",
            ctx=ctx,
            details={"project_root": str(root)},
        )
    if state.phase != 1:
        emit_error(
            "ERR_PHASE_MISMATCH",
            f"phase 1 required for /sdlc-stories; current phase: {state.phase}",
            ctx=ctx,
            details={"current_phase": state.phase},
        )

    eid = epic_id.strip()
    try:
        parse_epic_id(eid)
    except IdsError:
        emit_error(
            "ERR_USER_INPUT",
            f"invalid epic id {eid!r}",
            ctx=ctx,
            details={"epic_id": eid},
        )

    epic_path = root / _EPICS_DIR_REL / f"{eid}.json"
    story_dir = root / _STORIES_ROOT_REL / eid
    if not epic_path.is_file():
        emit_error(
            "ERR_EPIC_NOT_FOUND",
            f"epic {eid} not found at {epic_path.relative_to(root).as_posix()}; "
            "run 'sdlc epics' first to generate epics, or check the EPIC-id",
            ctx=ctx,
            details={"epic_id": eid, "path": str(epic_path)},
        )

    product_path = root / _PRODUCT_REL
    if not product_path.is_file():
        emit_error(
            "ERR_USER_INPUT",
            f"missing product brief at {_PRODUCT_REL}; run 'sdlc start' first",
            ctx=ctx,
            details={"path": str(product_path)},
        )
    product_text = _read_utf8(product_path, _PRODUCT_REL, ctx)
    if _artifact_contains_boundary(product_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"{_PRODUCT_REL} contains the data-vs-instruction boundary marker",
            ctx=ctx,
            details={"path": str(product_path)},
        )

    _apply_signoff_gate(root=root, ctx=ctx)

    epic_text = _read_utf8(epic_path, f"{_EPICS_DIR_REL}/{eid}.json", ctx)
    if _artifact_contains_boundary(epic_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            "epic JSON contains the data-vs-instruction boundary marker",
            ctx=ctx,
            details={"path": str(epic_path)},
        )
    _validate_epic_payload(epic_text, epic_path, ctx)

    workflows_dir = _workflows_package_dir()
    try:
        wf_registry = WorkflowRegistry.load(workflows_dir)
        spec = wf_registry.get("/sdlc-stories")
    except WorkflowError as exc:
        details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error("ERR_INFRASTRUCTURE", f"workflow load failed: {exc}", ctx=ctx, details=details)

    required_pc = (
        "stories_dir_non_empty",
        "all_story_jsons_valid",
        "boundary_line_present_in_prompts",
    )
    for name in required_pc:
        if name not in spec.postconditions:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"workflow sdlc-stories.yaml is missing required postcondition {name!r}",
                ctx=ctx,
                details={"workflow": spec.name, "postconditions": list(spec.postconditions)},
            )

    agents_dir = root / _AGENTS_REL
    try:
        registry = load_registry(agents_dir)
    except Exception as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"specialist registry load failed: {exc}",
            ctx=ctx,
            details={"agents_dir": str(agents_dir)},
        )

    hooks = build_pre_write_hook_chain(repo_root=root)

    created: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            if _pipeline.use_mock_runtime():
                _pipeline.materialize_mock(
                    tmp_path,
                    spec=spec,
                    registry=registry,
                    epic_text=epic_text,
                    product_text=product_text,
                    epic_id=eid,
                )
            runtime = build_runtime(fixtures_dir=tmp_path)
            created = asyncio.run(
                _pipeline.dispatch_and_write(
                    spec=spec,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    epic_text=epic_text,
                    product_text=product_text,
                    epic_id=eid,
                    story_dir=story_dir,
                    runtime=runtime,
                    registry=registry,
                    hooks=hooks,
                    allow_mock_invoked=allow_mock_invoked,
                ),
            )
        except WorkflowError as exc:
            _map_workflow_error(exc, ctx)
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except Exception as exc:
            emit_error(
                "ERR_STORIES_DISPATCH_FAILED",
                f"stories pipeline failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    try:
        evaluate_postconditions(
            spec,
            repo_root=root,
            agent_runs_path=agent_runs_path.resolve(),
            stories_subdir_abs=story_dir.resolve(),
        )
    except WorkflowError as exc:
        post_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_USER_INPUT",
            f"postcondition failed: {exc}",
            ctx=ctx,
            details=post_details,
        )

    highest_seq = _read_highest_seq(journal_path.resolve())
    try:
        pre = read_state_or_recover(state_path.resolve(), journal_path.resolve())
    except StateError as exc:
        st_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error("ERR_STATE_MALFORMED", exc.message, ctx=ctx, details=st_details)
    if pre is None:  # patch #9: guard for mypy + defense-in-depth
        emit_error(
            "ERR_NOT_INITIALIZED",
            "state.json disappeared mid-run",
            ctx=ctx,
            details={"path": str(state_path)},
        )
    if pre is not None:
        next_seq = max(pre.next_monotonic_seq, highest_seq + 1)
        try:
            write_state_atomic_sync(
                pre.model_copy(update={"next_monotonic_seq": next_seq}),
                target=state_path,
            )
        except OSError as exc:
            emit_error(
                "ERR_STATE_WRITE_FAILED",
                f"state update failed: {exc}",
                ctx=ctx,
                details={"path": str(state_path)},
            )

    if json_mode:
        emit_json(
            "stories",
            {
                "phase": 1,
                "specialist": "story-writer",
                "epic_id": eid,
                "stories_created": [{"id": i, "path": p} for i, p in created],
                "outcome": "success",
            },
            ctx=ctx,
        )
    else:
        echo(
            f"sdlc stories: wrote {len(created)} story file(s) under {_STORIES_ROOT_REL}/{eid}/",
            ctx=ctx,
        )


_ = (SignoffError, json)  # keep names live for tests; ``json`` reserved for future hooks
