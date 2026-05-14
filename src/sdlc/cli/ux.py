"""`sdlc ux` — Phase 2 UX track (FR13, Story 2A.13)."""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import emit_error, emit_json
from sdlc.cli.verify import _artifact_contains_boundary
from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import (
    PanelObserver,
    allocate_seq,
    build_pre_write_hook_chain,
    content_hash,
    dispatch,
    make_journal_entry,
    now_ts,
    phase1_prompt_builder,
)
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import SignoffError, WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.journal import append as journal_append
from sdlc.runtime.mock import MockAIRuntime
from sdlc.signoff import SignoffState, compute_state
from sdlc.specialists import SpecialistRegistry, load_registry
from sdlc.workflows.registry import WorkflowRegistry

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_PRODUCT_REL: Final[str] = "01-Requirement/01-PRODUCT.md"
_UX_DIR_REL: Final[str] = "02-Architecture/01-UX"
_SPECIALIST: Final[str] = "ux-designer"
_SLASH_CMD: Final[str] = "/sdlc-ux"

# Safe filename: NN-name.md (digit prefix, alnum/hyphens, .md suffix)
_SAFE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"^\d{2}-[a-zA-Z0-9][a-zA-Z0-9\-]*\.md$")


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg  # deferred

    return Path(pkg.__file__).resolve().parent


def _validate_ux_filename(filename: str, *, ctx: typer.Context) -> None:
    """Validate specialist-returned filename for safety (AC5)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        emit_error(
            "ERR_UNSAFE_FILENAME",
            f"specialist returned unsafe filename (path traversal): {filename!r}",
            ctx=ctx,
            details={"filename": filename},
        )
    if not _SAFE_FILENAME_RE.match(filename):
        emit_error(
            "ERR_UNSAFE_FILENAME",
            f"specialist returned filename not matching NN-name.md pattern: {filename!r}",
            ctx=ctx,
            details={"filename": filename},
        )


async def _ux_dispatch_and_write_async(
    *,
    spec: WorkflowSpec,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    product_text: str,
    ux_dir: Path,
    runtime: MockAIRuntime,
    registry: SpecialistRegistry,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
    ctx: typer.Context,
) -> list[dict[str, str]]:
    """Dispatch ux-designer, parse JSON array, write files. Returns [{path, hash}, ...]."""
    from sdlc.specialists.frontmatter import Specialist

    anchor = ux_dir / "00-ux-dispatch-anchor.md"
    anchor_rel = anchor.resolve().relative_to(root.resolve()).as_posix()

    def _prompt_builder(sp: object, wf: WorkflowSpec) -> str:
        assert isinstance(sp, Specialist)
        return phase1_prompt_builder(
            sp,
            wf,
            idea_text=product_text,
            role="primary",
            upstream_outputs=(),
        )

    # AC6: write agent_dispatched at CLI layer so the entry exists even when
    # dispatch is mocked in unit tests (emit_agent_dispatched=False below).
    seq_ad = await allocate_seq(journal_path)
    await journal_append(
        make_journal_entry(
            seq=seq_ad,
            ts=now_ts(),
            kind="agent_dispatched",
            target_id=anchor_rel,
            payload={
                "slash_command": _SLASH_CMD,
                "phase": 2,
                "specialist": _SPECIALIST,
            },
            actor="cli",
        ),
        journal_path,
    )

    observer = PanelObserver(
        slash_command=_SLASH_CMD,
        idea_text=product_text,
        emit_agent_dispatched=False,  # written explicitly above
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
            f"ux dispatch finished with outcome={result.outcome!r}",
            details={"outcome": result.outcome},
        )

    try:
        files: object = json.loads(result.agent_result.output_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise WorkflowError(
            "specialist response is not valid JSON",
            details={"cause": str(exc)},
        ) from exc

    if not isinstance(files, list):
        raise WorkflowError(
            "specialist response must be a JSON array",
            details={"type": type(files).__name__},
        )

    artifacts: list[dict[str, str]] = []
    for entry in files:
        if not isinstance(entry, dict) or "filename" not in entry or "content" not in entry:
            raise WorkflowError(
                "each specialist response entry must have filename + content fields",
                details={"entry": str(entry)[:200]},
            )
        filename = str(entry["filename"])
        file_content = str(entry["content"])

        _validate_ux_filename(filename, ctx=ctx)

        target = ux_dir / filename
        rel = target.resolve().relative_to(root.resolve()).as_posix()

        payload = build_write_intent_payload(
            hook_name="ux-cli",
            target_path=rel,
            write_intent="create",
            content_hash_before=None,
        )
        decision = await run_hook_chain(payload, hooks=hooks, journal_path=journal_path)
        if decision.decision != "allow":
            raise WorkflowError(
                "pre-write hook rejected UX artifact write",
                details={
                    "hook": decision.hook_name,
                    "reason": decision.reason,
                    "path": rel,
                },
            )

        target.write_text(file_content, encoding="utf-8")
        after = content_hash(file_content)

        seq_aw = await allocate_seq(journal_path)
        await journal_append(
            make_journal_entry(
                seq=seq_aw,
                ts=now_ts(),
                kind="artifact_written",
                target_id=rel,
                payload={
                    "slash_command": _SLASH_CMD,
                    "phase": 2,
                    "specialist": _SPECIALIST,
                },
                after_hash=after,
                actor="cli",
            ),
            journal_path,
        )
        artifacts.append({"path": rel, "hash": after})

    return artifacts


def run_ux(*, ctx: typer.Context) -> None:  # noqa: C901, PLR0915
    """Initiate Phase 2 UX track (FR13, AC5)."""
    root = _get_repo_root_or_cwd()
    state_path = root / _STATE_REL
    journal_path = root / _JOURNAL_REL
    agent_runs_path = root / _RUNS_REL

    if not state_path.exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )
    try:
        phase1_state = compute_state(1, repo_root=root)
    except SignoffError as exc:
        emit_error(
            "ERR_PHASE1_NOT_APPROVED",
            f"phase 1 signoff state could not be read: {exc}",
            ctx=ctx,
            details={"phase": 1},
        )
    if phase1_state != SignoffState.APPROVED:
        emit_error(
            "ERR_PHASE1_NOT_APPROVED",
            "phase 1 signoff must be APPROVED before starting Phase 2 UX work; "
            f"current state: {phase1_state.value}. "
            "Run '/sdlc-signoff 1' to generate the draft, approve it, then 'sdlc scan'.",
            ctx=ctx,
            details={"phase1_state": str(phase1_state)},
        )
    product_path = root / _PRODUCT_REL
    if not product_path.is_file():
        emit_error(
            "ERR_USER_INPUT",
            f"missing {_PRODUCT_REL}; run 'sdlc start' first",
            ctx=ctx,
            details={"path": str(product_path)},
        )
    try:
        product_text = product_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"{_PRODUCT_REL} is not valid UTF-8: {exc}",
            ctx=ctx,
            details={"path": str(product_path), "cause": str(exc)},
        )
    if _artifact_contains_boundary(product_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"{_PRODUCT_REL} contains the data-vs-instruction boundary marker",
            ctx=ctx,
            details={"path": str(product_path)},
        )
    ux_dir = root / _UX_DIR_REL
    ux_dir.mkdir(parents=True, exist_ok=True)
    workflows_dir = _workflows_package_dir()
    try:
        spec = WorkflowRegistry.load(workflows_dir).get(_SLASH_CMD)
    except WorkflowError as exc:
        wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_INFRASTRUCTURE", f"workflow load failed: {exc}", ctx=ctx, details=wf_details
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

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            _materialize_ux_mock_fixture(
                tmp_path, spec=spec, registry=registry, product_text=product_text
            )
            runtime = MockAIRuntime(tmp_path)
            artifacts = asyncio.run(
                _ux_dispatch_and_write_async(
                    spec=spec,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    product_text=product_text,
                    ux_dir=ux_dir,
                    runtime=runtime,
                    registry=registry,
                    hooks=hooks,
                    ctx=ctx,
                )
            )
        except WorkflowError as exc:
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error("ERR_UX_DISPATCH_FAILED", str(exc), ctx=ctx, details=wf_details)
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except Exception as exc:
            emit_error(
                "ERR_UX_DISPATCH_FAILED",
                f"UX pipeline failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    try:
        evaluate_postconditions(
            spec,
            repo_root=root,
            agent_runs_path=agent_runs_path.resolve(),
            ux_dir_abs=ux_dir.resolve(),
        )
    except WorkflowError as exc:
        post_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition failed: {exc}",
            ctx=ctx,
            details=post_details,
        )

    emit_json(
        "ux",
        {
            "phase": 2,
            "track": "ux",
            "specialist": _SPECIALIST,
            "artifacts": artifacts,
            "outcome": "success",
        },
        ctx=ctx,
    )


def _materialize_ux_mock_fixture(
    dest_dir: Path,
    *,
    spec: WorkflowSpec,
    registry: SpecialistRegistry,
    product_text: str,
) -> None:
    """Write a MockAIRuntime fixture for the ux-designer specialist."""
    import yaml

    from sdlc.runtime.mock import compute_prompt_hash
    from sdlc.specialists.frontmatter import Specialist

    try:
        sp = registry.get(_SPECIALIST)
    except Exception:
        return  # mock runtime will miss; let MockAIRuntime raise MockMissError
    assert isinstance(sp, Specialist)
    prompt = phase1_prompt_builder(
        sp, spec, idea_text=product_text, role="primary", upstream_outputs=()
    )
    h = compute_prompt_hash(prompt)
    _ph = "**PLACEHOLDER** — MockAIRuntime v1. Real content lands in Story 2B.9.\n"
    placeholder_body = json.dumps(
        [
            {"filename": "01-tokens.md", "content": f"# Design Tokens\n\n{_ph}"},
            {"filename": "02-flows.md", "content": f"# User Flows\n\n{_ph}"},
            {"filename": "03-screens.md", "content": f"# Screen Specs\n\n{_ph}"},
        ]
    )
    records = {
        h: {"output_text": placeholder_body, "tokens_in": 1, "tokens_out": 1, "tool_calls": []}
    }
    (dest_dir / f"{spec.name}.yaml").write_text(
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True), encoding="utf-8"
    )
