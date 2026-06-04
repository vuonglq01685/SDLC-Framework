"""Dispatch wiring for `sdlc verify` (Story 2A.10, FR8, AC5/AC7).

Private CLI-internal. Owns workflow+spec load, MockAIRuntime fixture
materialisation (v1), single-specialist ``dispatch(persist_artifact=False)``
per AC5, and the top-level orchestrator. Post-dispatch ceremony lives in
the sibling :mod:`sdlc.cli._verify_post`. PUBLIC surface stays in
:mod:`sdlc.cli.verify` (D1). Real Claude dispatch ships in Story 2B.x;
the on-disk frontmatter contract is stable across that swap because
verdict parsing is defensive (see
:func:`sdlc.cli._verify_post.parse_verdict_envelope`).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

import typer
import yaml
from pydantic import ValidationError

from sdlc.cli._verify_finalize import emit_user_output_and_exit, emit_verified_and_advance
from sdlc.cli._verify_frontmatter import _compute_body_hash
from sdlc.cli._verify_mock import resolve_mock_verdict
from sdlc.cli._verify_post import (
    REQUIRED_PHASE,
    SLASH_COMMAND,
    append_and_persist_frontmatter,
    assert_artifact_not_raced,
    build_verification_entry,
    parse_verdict_with_overflow_check,
)
from sdlc.cli.output import echo, emit_error
from sdlc.errors import WorkflowError

__all__ = ("invoke_dispatch", "SLASH_COMMAND")  # noqa: RUF022 — public entry first, constant second

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"

_ = REQUIRED_PHASE  # imported for re-export visibility; payload built in _verify_post


def _workflows_package_dir() -> Path:
    # P18 (post-review 2026-05-12): use importlib.resources so we don't depend
    # on `pkg.__file__` being a real filesystem path (frozen wheels / zip-imports).
    from importlib.resources import files  # deferred per Architecture §488

    # files() returns a Traversable; str(...) coerces non-Path shims.
    return Path(str(files("sdlc.workflows_yaml"))).resolve()


def _materialize_verifier_fixture(
    dest_dir: Path,
    *,
    spec: object,
    registry: object,
    idea_text: str,
) -> None:
    """Write a single-record MockAIRuntime fixture for the verifier prompt."""
    from sdlc.dispatcher import phase1_prompt_builder  # deferred
    from sdlc.runtime.mock import compute_prompt_hash  # deferred

    sp = registry.get(spec.primary_agent)  # type: ignore[attr-defined]
    prompt = phase1_prompt_builder(
        sp,
        spec,  # type: ignore[arg-type]
        idea_text=idea_text,
        role="primary",
        upstream_outputs=(),
    )
    prompt_hash = compute_prompt_hash(prompt)
    records = {
        prompt_hash: {
            "output_text": json.dumps(dict(resolve_mock_verdict()), sort_keys=True),
            "tokens_in": 1,
            "tokens_out": 1,
            "tool_calls": [],
        },
    }
    (dest_dir / f"{spec.name}.yaml").write_text(  # type: ignore[attr-defined]
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


async def _dispatch_verifier(
    *,
    spec: object,
    registry: object,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    runtime: object,
    observer: object,
    artifact_path: Path,
) -> object:
    """Await a single-specialist `dispatch(...)` with non-destructive kwargs."""
    from sdlc.dispatcher import (  # deferred
        build_pre_write_hook_chain,
        dispatch,
        phase1_prompt_builder,
    )

    return await dispatch(
        spec,  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
        registry=registry,  # type: ignore[arg-type]
        repo_root=root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=phase1_prompt_builder,
        hooks=build_pre_write_hook_chain(repo_root=root),
        observer=observer,  # type: ignore[arg-type]
        persist_artifact=False,
        target_path_override=artifact_path,
    )


def _load_workflow_and_registry(ctx: typer.Context, root: Path) -> tuple[object, object]:
    """Return (WorkflowSpec for /sdlc-verify, SpecialistRegistry)."""
    from sdlc.specialists import load_registry  # deferred
    from sdlc.workflows.registry import WorkflowRegistry  # deferred

    try:
        wf_registry = WorkflowRegistry.load(_workflows_package_dir())
        spec = wf_registry.get(SLASH_COMMAND)
    except WorkflowError as exc:
        wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"workflow load failed: {exc}",
            ctx=ctx,
            details=wf_details,
        )
    # P2: broaden to surface OSError / yaml.YAMLError / TypeError as
    # ERR_INFRASTRUCTURE instead of raw tracebacks.
    except Exception as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"workflow registry load failed: {exc}",
            ctx=ctx,
            details={"error": str(exc), "error_type": type(exc).__name__},
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
    return spec, registry


def _run_dispatch_under_mock(
    ctx: typer.Context,
    *,
    spec: object,
    registry: object,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    observer: object,
    artifact_path: Path,
    artifact_content: str,
    idea_text: str,
) -> object:
    """Materialize MockAIRuntime fixture and run dispatch under it."""
    from sdlc.runtime.mock import MockAIRuntime  # deferred

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            _materialize_verifier_fixture(
                tmp_path, spec=spec, registry=registry, idea_text=idea_text
            )
            runtime = MockAIRuntime(tmp_path)
            return asyncio.run(
                _dispatch_verifier(
                    spec=spec,
                    registry=registry,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    runtime=runtime,
                    observer=observer,
                    artifact_path=artifact_path,
                )
            )
        except WorkflowError as exc:
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error(
                "ERR_USER_INPUT",
                str(exc),
                ctx=ctx,
                details=wf_details,
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except Exception as exc:
            emit_error(
                "ERR_PANEL_DISPATCH_FAILED",
                f"verify dispatch failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )


def _build_idea_with_origin(root: Path, artifact_id: str, artifact_content: str) -> str:
    """Prepend an ``<IMPORTED_ORIGIN>`` block when an imported-metadata sidecar exists (AC4).

    Returns ``artifact_content`` unchanged when the artifact was not adopted (no sidecar).
    Extracted from :func:`invoke_dispatch` so the origin-injection behaviour is unit-testable
    without standing up a full dispatch.
    """
    from sdlc.adopt.imported_metadata import metadata_record_path, read_metadata_record

    imported_meta = read_metadata_record(metadata_record_path(root, artifact_id))
    if imported_meta is None:
        return artifact_content
    return (
        "<IMPORTED_ORIGIN>\n"
        "This artifact was imported from existing project content during "
        "`sdlc init --adopt`.\n"
        f"Source path: {imported_meta.source}\n"
        f"Canonical target: {imported_meta.target}\n"
        "Your verification MUST explicitly address whether this imported "
        "content is still accurate.\n"
        "</IMPORTED_ORIGIN>\n\n"
        f"{artifact_content}"
    )


def invoke_dispatch(  # CLI orchestration; LOC budget split across 3 modules
    *,
    ctx: typer.Context,
    root: Path,
    artifact_path: Path,
    artifact_id: str,
    artifact_content: str,
) -> None:
    """Dispatch the artifact-verifier specialist + append verification entry.

    Re-exported via :mod:`sdlc.cli.verify` as ``_invoke_dispatch``. Post-
    dispatch ceremony (parse/append/emit/advance) lives in
    :mod:`sdlc.cli._verify_post` for LOC-cap discipline.
    """
    from sdlc.dispatcher import PanelObserver  # deferred

    ctx_obj: Mapping[str, object] = ctx.obj if isinstance(ctx.obj, Mapping) else {}
    json_mode = bool(ctx_obj.get("json", False))

    spec, registry = _load_workflow_and_registry(ctx, root)
    journal_path = root / _JOURNAL_REL
    state_path = root / _STATE_REL
    agent_runs_path = root / _RUNS_REL

    # P20 / DC7=(c): lazy mkdir `03-Implementation/` (test fixtures create
    # it manually; real Phase-1 init may not).
    try:
        agent_runs_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"could not create agent_runs directory: {exc}",
            ctx=ctx,
            details={"path": str(agent_runs_path.parent)},
        )

    if not json_mode:
        echo(
            "[WARN] sdlc verify runs against MockAIRuntime in v1; "
            "real Claude dispatch ships in Story 2B.x",
            err=True,
            ctx=ctx,
        )

    # P29/DC8=(2): whole-file hash pre-dispatch → stamps both
    # `agent_dispatched.payload.artifact_hash_at_dispatch` (alongside legacy
    # `idea_hash`) AND `artifact_verified.before_hash`.
    from sdlc.signoff.hasher import compute_artifact_hash  # deferred

    pre_dispatch_full_hash = compute_artifact_hash(artifact_path, repo_root=root)

    idea_for_dispatch = _build_idea_with_origin(root, artifact_id, artifact_content)

    observer = PanelObserver(
        slash_command=SLASH_COMMAND,
        idea_text=idea_for_dispatch,
        extra_context=MappingProxyType(
            {
                "agent_dispatched_extras": MappingProxyType(
                    {"artifact_hash_at_dispatch": pre_dispatch_full_hash}
                ),
            }
        ),
        emit_agent_dispatched=True,
    )

    result = _run_dispatch_under_mock(
        ctx,
        spec=spec,
        registry=registry,
        root=root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        observer=observer,
        artifact_path=artifact_path,
        artifact_content=artifact_content,
        idea_text=idea_for_dispatch,
    )

    outcome = getattr(result, "outcome", None)
    if outcome != "success":
        emit_error(
            "ERR_PANEL_DISPATCH_FAILED",
            f"verifier outcome={outcome!r}",
            ctx=ctx,
            details={"outcome": str(outcome)},
        )

    agent_result = getattr(result, "agent_result", None)
    output_text: str = getattr(agent_result, "output_text", "") if agent_result else ""

    status, note = parse_verdict_with_overflow_check(ctx, output_text)
    body_hash = _compute_body_hash(artifact_content)
    assert_artifact_not_raced(
        ctx=ctx,
        artifact_path=artifact_path,
        artifact_id=artifact_id,
        preflight_body_hash=body_hash,
    )
    try:
        entry = build_verification_entry(
            verifier=getattr(spec, "primary_agent", "artifact-verifier"),
            status=status,
            note=note,
            body_hash=body_hash,
        )
    except ValidationError as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"verification entry construction failed: {exc}",
            ctx=ctx,
            details={"errors": exc.errors()},
        )

    # P29/DC8=(2): reuse pre-dispatch hash; TOCTOU above guarantees bytes
    # unchanged since dispatch.
    before_hash_full = pre_dispatch_full_hash

    try:
        new_fm, verification_index = append_and_persist_frontmatter(artifact_path, entry)
    except WorkflowError as exc:
        wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"frontmatter append failed: {exc}",
            ctx=ctx,
            details=wf_details,
        )

    # P29 / DC8=(2): post-rewrite whole-file hash pins the after-state.
    after_hash_full = compute_artifact_hash(artifact_path, repo_root=root)

    emit_verified_and_advance(
        ctx,
        json_mode=json_mode,
        output_text=output_text,
        journal_path=journal_path,
        state_path=state_path,
        artifact_id=artifact_id,
        entry=entry,
        verification_index=verification_index,
        before_hash=before_hash_full,
        after_hash=after_hash_full,
    )

    emit_user_output_and_exit(
        ctx,
        json_mode=json_mode,
        artifact_id=artifact_id,
        entry=entry,
        verification_index=verification_index,
        total_verifications=len(new_fm["verifications"]),
    )
