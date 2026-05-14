"""`sdlc epics` — Phase 1 epic JSON generation (Story 2A.11, FR9, AC4).

Reads ``01-Requirement/01-PRODUCT.md``, dispatches ``epic-generator`` once,
validates JSON-array output via :class:`_EpicEntry`, and writes one canonical
JSON file per epic under ``01-Requirement/04-Epics/`` with per-file hooks +
journal entries. Dispatch / parse / per-file write logic lives in
:mod:`sdlc.cli._epics_pipeline` so this module stays under the AC8 LOC cap.

Patches applied during code review (2026-05-14):
- #7  empty PRODUCT.md → ``ERR_USER_INPUT`` (not infra error)
- #8  ``UnicodeDecodeError`` on PRODUCT.md → ``ERR_ARTIFACT_UNREADABLE``
- #11 unknown ``WorkflowError`` sub-category defaults to ``ERR_INFRASTRUCTURE``
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from typer import Context

from sdlc.cli import _epics_pipeline as _pipeline
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.cli.verify import _artifact_contains_boundary
from sdlc.dispatcher import build_pre_write_hook_chain
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import SignoffError, StateError, WorkflowError
from sdlc.runtime.mock import MockAIRuntime
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

# Keep references that production code + tests patch via ``sdlc.cli.epics.<name>``.
__all__ = ("SignoffState", "compute_state", "run_epics")


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg  # deferred

    return Path(pkg.__file__).resolve().parent


def _read_product_text(product_path: Path, ctx: Context) -> str:
    """Read PRODUCT.md with explicit error mapping (patches #7 + #8)."""
    try:
        text = product_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"{_PRODUCT_REL} is not valid UTF-8: {exc}",
            ctx=ctx,
            details={"path": str(product_path), "cause": str(exc)},
        )
        return ""  # type: ignore[unreachable]  # emit_error raises typer.Exit
    if not text.strip():
        emit_error(
            "ERR_USER_INPUT",
            f"{_PRODUCT_REL} is empty; populate the product brief before /sdlc-epics",
            ctx=ctx,
            details={"path": str(product_path)},
        )
        return ""  # type: ignore[unreachable]  # emit_error raises typer.Exit
    return text


def _apply_signoff_gate(*, root: Path, ctx: Context) -> None:
    """Inlined so tests can patch ``sdlc.cli.epics.compute_state`` directly.

    Patch #10: elif chain so flow control survives mocked emit_error.
    """
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
            "phase 1 signoff is APPROVED; adding epics is a hash-drift event. "
            "Run 'sdlc replan --scope=01-Requirement/04-Epics/' first to invalidate "
            "signoff, then re-run /sdlc-epics.",
            ctx=ctx,
        )
        return  # type: ignore[unreachable]
    if st == SignoffState.DRAFTED_NOT_APPROVED:
        echo(
            "[WARN] phase 1 signoff is drafted but not approved; adding epics "
            "will require signoff re-draft.",
            err=True,
            ctx=ctx,
        )


def _map_workflow_error(exc: WorkflowError, ctx: Context) -> None:
    """Patch #11: default to ERR_INFRASTRUCTURE for unknown sub-categories."""
    details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
    sub = details.get("sdlc_epics")
    if sub == "schema_invalid":
        emit_error("ERR_EPIC_SCHEMA_INVALID", str(exc), ctx=ctx, details=details)
    elif sub == "hook_rejected":
        emit_error("ERR_HOOK_REJECTED", str(exc), ctx=ctx, details=details)
    elif sub == "dispatch_failed":
        emit_error("ERR_EPICS_DISPATCH_FAILED", str(exc), ctx=ctx, details=details)
    elif sub == "collision":
        emit_error("ERR_USER_INPUT", str(exc), ctx=ctx, details=details)
    else:
        emit_error("ERR_INFRASTRUCTURE", str(exc), ctx=ctx, details=details)


def run_epics(*, ctx: Context) -> None:  # noqa: C901, PLR0912, PLR0915
    """Generate epic JSON files from the Phase 1 product brief."""
    from sdlc.journal._seq import _read_highest_seq
    from sdlc.state import read_state_or_recover, write_state_atomic_sync

    ctx_obj: Mapping[str, object] = ctx.obj if isinstance(ctx.obj, Mapping) else {}
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
            f"phase 1 required for /sdlc-epics; current phase: {state.phase}",
            ctx=ctx,
            details={"current_phase": state.phase},
        )

    product_path = root / _PRODUCT_REL
    if not product_path.is_file():
        emit_error(
            "ERR_USER_INPUT",
            f"missing product brief at {_PRODUCT_REL}; run 'sdlc start' first",
            ctx=ctx,
            details={"path": str(product_path)},
        )
    product_text = _read_product_text(product_path, ctx)
    if _artifact_contains_boundary(product_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"{_PRODUCT_REL} contains the data-vs-instruction boundary marker",
            ctx=ctx,
            details={"path": str(product_path)},
        )

    _apply_signoff_gate(root=root, ctx=ctx)

    workflows_dir = _workflows_package_dir()
    try:
        wf_registry = WorkflowRegistry.load(workflows_dir)
        spec = wf_registry.get("/sdlc-epics")
    except WorkflowError as exc:
        details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error("ERR_INFRASTRUCTURE", f"workflow load failed: {exc}", ctx=ctx, details=details)

    required_pc = (
        "epics_dir_non_empty",
        "all_epic_jsons_valid",
        "boundary_line_present_in_prompts",
    )
    for name in required_pc:
        if name not in spec.postconditions:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"workflow sdlc-epics.yaml is missing required postcondition {name!r}",
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

    if not _pipeline.use_mock_runtime():
        emit_error(
            "ERR_INFRASTRUCTURE",
            "SDLC_USE_MOCK_RUNTIME=0 but no real specialist runtime is wired in v1; "
            "set SDLC_USE_MOCK_RUNTIME=1 or wait for Story 2B.1 ClaudeAIRuntime",
            ctx=ctx,
            details={"env": "SDLC_USE_MOCK_RUNTIME"},
        )

    json_mode = bool(ctx_obj.get("json", False))
    if not json_mode:
        echo(
            "[WARN] sdlc epics v1 uses MockAIRuntime; output is a structural placeholder.",
            err=True,
            ctx=ctx,
        )

    epics_dir = root / _EPICS_DIR_REL
    hooks = build_pre_write_hook_chain(repo_root=root)

    created: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            _pipeline.materialize_mock(
                tmp_path,
                spec=spec,
                registry=registry,
                product_text=product_text,
            )
            runtime = MockAIRuntime(tmp_path)
            created = asyncio.run(
                _pipeline.dispatch_and_write(
                    spec=spec,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    product_text=product_text,
                    epics_dir=epics_dir,
                    runtime=runtime,
                    registry=registry,
                    hooks=hooks,
                ),
            )
        except WorkflowError as exc:
            _map_workflow_error(exc, ctx)
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except Exception as exc:
            emit_error(
                "ERR_EPICS_DISPATCH_FAILED",
                f"epics pipeline failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    try:
        evaluate_postconditions(
            spec,
            repo_root=root,
            agent_runs_path=agent_runs_path.resolve(),
            epics_dir_abs=epics_dir.resolve(),
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
    if pre is None:
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
            "epics",
            {
                "phase": 1,
                "specialist": "epic-generator",
                "epics_created": [{"id": i, "path": p} for i, p in created],
                "epics_dir": f"{_EPICS_DIR_REL}/",
                "outcome": "success",
            },
            ctx=ctx,
        )
    else:
        echo(f"sdlc epics: wrote {len(created)} epic file(s) under {_EPICS_DIR_REL}/", ctx=ctx)


# SignoffError is reachable through the pipeline; suppress F401 for re-export.
_ = SignoffError
