"""Dispatch wiring for `sdlc verify` (Story 2A.10, FR8, AC5/AC7).

Private CLI-internal module. Owns the dispatch-side of the verify ceremony:
workflow + spec load, MockAIRuntime fixture materialisation, single-specialist
``dispatch(...)`` invocation with ``persist_artifact=False`` (AC5), and the
top-level orchestrator (`invoke_dispatch`).

Post-dispatch ceremony — verdict parsing, frontmatter append, journal emit,
state advance — lives in the sibling `_verify_post.py` so each module stays
under the Architecture §1052-§1112 LOC cap. D1 still mandates a single PUBLIC
surface; both privates are re-exported only via `cli/verify.py`.

Mock posture (v1, Story 2A.10):

  * The verifier specialist is dispatched against a deterministic
    `MockAIRuntime` whose fixture is materialised at request time
    (parity with `cli/start.py`). The mock returns a canned
    ``{"verdict": "verified", "note": "..."}`` envelope. Real Claude
    dispatch ships in Story 2B.x; the on-disk frontmatter contract is
    stable across that swap because the verdict envelope is parsed
    defensively in `_verify_post.parse_verdict_envelope`.
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

from sdlc.cli._verify_frontmatter import _compute_body_hash
from sdlc.cli._verify_post import (
    REQUIRED_PHASE,
    SLASH_COMMAND,
    advance_state_seq,
    append_and_persist_frontmatter,
    build_verification_entry,
    emit_artifact_verified,
    parse_verdict_envelope,
)
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.errors import WorkflowError

__all__ = ("invoke_dispatch", "SLASH_COMMAND")  # noqa: RUF022 — public entry first, constant second

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"

# v1 mock verifier output (deterministic; see Story 2A.10 D2). Private: the
# on-disk frontmatter row is the public surface, NOT the verdict envelope.
_MOCK_VERIFIER_VERDICT: Final[Mapping[str, str]] = MappingProxyType(
    {"verdict": "verified", "note": "v1 mock verifier — replaced by Story 2B.x"},
)

_ = REQUIRED_PHASE  # imported for re-export visibility; payload built in _verify_post


def _workflows_package_dir() -> Path:
    # P18 (post-review 2026-05-12): use importlib.resources so we don't depend
    # on `pkg.__file__` being a real filesystem path (e.g. frozen wheels /
    # zip-imports). The package is a normal MultiplexedPath under Hatchling.
    from importlib.resources import files  # deferred per Architecture §488

    pkg_path = files("sdlc.workflows_yaml")
    # `files()` returns a Traversable; for a regular package this is a real
    # `Path`. Coerce via str(...) so non-Path Traversable shims still work.
    return Path(str(pkg_path)).resolve()


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
            "output_text": json.dumps(dict(_MOCK_VERIFIER_VERDICT), sort_keys=True),
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
    # P2 (post-review 2026-05-12): broaden so OSError / yaml.YAMLError /
    # TypeError from the importlib.resources path coercion surface as
    # ERR_INFRASTRUCTURE envelopes instead of raw tracebacks.
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
) -> object:
    """Materialize MockAIRuntime fixture and run dispatch under it."""
    from sdlc.runtime.mock import MockAIRuntime  # deferred

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            _materialize_verifier_fixture(
                tmp_path, spec=spec, registry=registry, idea_text=artifact_content
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


def invoke_dispatch(  # CLI orchestration; LOC budget split across 3 modules
    *,
    ctx: typer.Context,
    root: Path,
    artifact_path: Path,
    artifact_id: str,
    artifact_content: str,
) -> None:
    """Dispatch the artifact-verifier specialist + append verification entry.

    Public to `cli/verify.py` (re-exported there as `_invoke_dispatch`
    for test compatibility). The post-dispatch ceremony — verdict parsing,
    frontmatter append, journal emit, state advance — is delegated to
    `_verify_post` so each private module stays under the §1052-§1112
    LOC cap.
    """
    from sdlc.dispatcher import PanelObserver  # deferred

    ctx_obj: Mapping[str, object] = ctx.obj if isinstance(ctx.obj, Mapping) else {}
    json_mode = bool(ctx_obj.get("json", False))

    spec, registry = _load_workflow_and_registry(ctx, root)
    journal_path = root / _JOURNAL_REL
    state_path = root / _STATE_REL
    agent_runs_path = root / _RUNS_REL

    if not json_mode:
        echo(
            "[WARN] sdlc verify runs against MockAIRuntime in v1; "
            "real Claude dispatch ships in Story 2B.x",
            err=True,
            ctx=ctx,
        )

    observer = PanelObserver(
        slash_command=SLASH_COMMAND,
        idea_text=artifact_content,
        extra_context=MappingProxyType({}),
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
    status, note = parse_verdict_envelope(output_text)
    body_hash = _compute_body_hash(artifact_content)
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

    asyncio.run(
        emit_artifact_verified(
            journal_path=journal_path,
            rel_path=artifact_id,
            entry=entry,
            verification_index=verification_index,
        )
    )
    advance_state_seq(state_path, journal_path)

    if json_mode:
        emit_json(
            "verify",
            {
                "artifact_id": artifact_id,
                "verifier": entry.verifier,
                "status": entry.status,
                "verification_index": verification_index,
                "content_hash_at_verify": entry.content_hash_at_verify,
                "total_verifications": len(new_fm["verifications"]),
            },
            ctx=ctx,
        )
    else:
        echo(
            f"sdlc verify: appended verification[{verification_index}] "
            f"({entry.status}) to {artifact_id}",
            ctx=ctx,
        )
