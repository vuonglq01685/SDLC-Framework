"""`sdlc start` — Phase 1 entry via panel dispatch (FR6, Story 2A.8).

Holds journal monotonic_seq coordination in-process with the dispatcher allocator
(EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ). Story 2A.8 refactor (D1-C/D2-B/D3-A):
CLI builds a typed ``PanelObserver``; synthesizer is the canonical writer;
frontmatter values flow via ``observer.extra_context``.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

import typer
import yaml

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import (
    PanelObserver,
    build_pre_write_hook_chain,
    dispatch_panel,
    phase1_prompt_builder,
)
from sdlc.dispatcher.core import PanelResult
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import StateError, WorkflowError
from sdlc.runtime.mock import MockAIRuntime, compute_prompt_hash
from sdlc.specialists import SpecialistRegistry, load_registry
from sdlc.workflows.registry import WorkflowRegistry

_PRODUCT_REL: Final[str] = "01-Requirement/01-PRODUCT.md"
_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"

# v1 mock bodies — non-synthesizer agents emit candidate drafts (each contains `## `
# for product_md_exists when promoted). Synthesizer mock output is computed at runtime
# (frontmatter is timestamp-dependent) inside ``_synth_mock_output``.
# P36: MappingProxyType wrap = process-wide read-only sentinel; prevents accidental
# mutation by test fixtures that import this module.
_V1_MOCK_BODIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "product-strategist": "## Strategist\n\nPrimary draft.\n",
        "technical-researcher": "## Research\n\nParallel notes.\n",
        "devil-advocate": "## Risks\n\nParallel concerns.\n",
    }
)
_SYNTH_BODY: Final[str] = "## Product Brief\n\nSynthesized PRD body for v1.\n"


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg  # deferred

    return Path(pkg.__file__).resolve().parent


def _build_frontmatter_context(idea: str, spec: WorkflowSpec) -> dict[str, object]:
    """Assemble the canonical frontmatter fields the synthesizer prompt expects (D3-A)."""
    assert spec.synthesizer_agent  # workflow loader rejects unsynthesized phase-1
    return {
        "schema_version": 1,
        "kind": "product_brief",
        "idea": idea,
        "drafted_at": now_rfc3339_utc_ms(),
        "drafted_by_specialists": [
            spec.primary_agent,
            *spec.parallel_agents,
            spec.synthesizer_agent,
        ],
    }


def _synth_mock_output(extra_context: Mapping[str, object]) -> str:
    """Compose the mock synthesizer output bytes: frontmatter (rendered) + body.

    Mirrors :func:`sdlc.dispatcher.prompts._render_frontmatter_block` so the
    fixture and the live prompt agree on a byte-equal payload.
    """
    fm: dict[str, object] = {
        "schema_version": extra_context["schema_version"],
        "kind": extra_context["kind"],
        "idea": extra_context["idea"],
        "drafted_at": extra_context["drafted_at"],
        "drafted_by_specialists": extra_context["drafted_by_specialists"],
    }
    fm_yaml = yaml.safe_dump(fm, sort_keys=True, allow_unicode=True).strip()
    return f"---\n{fm_yaml}\n---\n\n{_SYNTH_BODY}"


def _materialize_phase1_mock_fixtures(
    dest_dir: Path,
    *,
    spec: WorkflowSpec,
    registry: SpecialistRegistry,
    idea_text: str,
    extra_context: Mapping[str, object],
) -> None:
    """Write ``{spec.name}.yaml`` for MockAIRuntime (one entry per panel prompt hash)."""
    records: dict[str, dict[str, object]] = {}

    def _add(name: str, role: str, output_text: str, upstream: tuple[str, ...] = ()) -> None:
        sp = registry.get(name)
        builder_kwargs: dict[str, object] = {
            "idea_text": idea_text,
            "role": role,
            "upstream_outputs": upstream,
        }
        if role == "synthesizer":
            builder_kwargs["extra_context"] = extra_context
        prompt = phase1_prompt_builder(sp, spec, **builder_kwargs)  # type: ignore[arg-type]
        h = compute_prompt_hash(prompt)
        records[h] = {
            "output_text": output_text,
            "tokens_in": 1,
            "tokens_out": 1,
            "tool_calls": [],
        }

    _add(spec.primary_agent, "primary", _V1_MOCK_BODIES[spec.primary_agent])
    for n in spec.parallel_agents:
        _add(n, "parallel", _V1_MOCK_BODIES[n])
    upstream = (
        _V1_MOCK_BODIES[spec.primary_agent],
        *(_V1_MOCK_BODIES[n] for n in spec.parallel_agents),
    )
    assert spec.synthesizer_agent
    _add(spec.synthesizer_agent, "synthesizer", _synth_mock_output(extra_context), upstream)

    (dest_dir / f"{spec.name}.yaml").write_text(
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


async def _dispatch_phase1_panel(
    *,
    spec: WorkflowSpec,
    registry: SpecialistRegistry,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    runtime: MockAIRuntime,
    observer: PanelObserver,
) -> PanelResult:
    return await dispatch_panel(
        spec,
        runtime=runtime,
        registry=registry,
        repo_root=root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=phase1_prompt_builder,
        hooks=build_pre_write_hook_chain(repo_root=root),
        observer=observer,
        max_parallel_agents=4,
    )


def run_start(  # noqa: C901, PLR0912, PLR0915 — CLI orchestration; Story 2A.8 caps LOC not branch count
    *, ctx: typer.Context, idea: str, quiet: bool = False
) -> None:
    """Run Phase 1 product-discovery panel; write ``01-Requirement/01-PRODUCT.md``."""
    # P16: validate ctx.obj shape once; downstream reads use the local Mapping.
    ctx_obj: Mapping[str, object] = ctx.obj if isinstance(ctx.obj, Mapping) else {}
    if not idea.strip():
        emit_error(
            "ERR_USER_INPUT",
            "idea text must be non-empty",
            ctx=ctx,
        )

    root = _get_repo_root_or_cwd()
    state_path = root / _STATE_REL
    journal_path = root / _JOURNAL_REL
    product_path = root / _PRODUCT_REL

    if not state_path.is_file():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    if product_path.is_file():
        emit_error(
            "ERR_PHASE1_PRODUCT_EXISTS",
            f"01-PRODUCT.md already exists at {product_path}; "
            "run `sdlc replan --scope=01-Requirement/01-PRODUCT.md` or remove the file first",
            ctx=ctx,
            details={"path": str(product_path), "workflow": "phase1-product-discovery"},
        )

    workflows_dir = _workflows_package_dir()
    try:
        wf_registry = WorkflowRegistry.load(workflows_dir)
        spec = wf_registry.get("/sdlc-start")
    except WorkflowError as exc:
        # P18: guard exc.details type before dict(...) — defensive against future
        # WorkflowError subclasses that may carry non-Mapping details.
        wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"workflow load failed: {exc}",
            ctx=ctx,
            details=wf_details,
        )

    agents_dir = root / _AGENTS_REL
    try:
        registry = load_registry(agents_dir)
    except Exception as exc:  # SpecialistError or manifest I/O
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"specialist registry load failed: {exc}",
            ctx=ctx,
            details={"agents_dir": str(agents_dir)},
        )

    agent_runs_path = root / _RUNS_REL

    # P16: use the pre-validated ctx_obj Mapping.
    json_mode = bool(ctx_obj.get("json", False))
    if not quiet and not json_mode:
        echo(
            "[WARN] sdlc start runs against MockAIRuntime in v1; "
            "real Claude dispatch ships in Story 2B.1",
            err=True,
            ctx=ctx,
        )

    # D3-A: assemble frontmatter values once; pass to BOTH the mock fixture
    # materializer (so the synth prompt hash matches) AND the observer (so the
    # live synth prompt embeds the same canonical bytes).
    frontmatter_context = _build_frontmatter_context(idea, spec)
    observer = PanelObserver(
        slash_command="/sdlc-start",
        idea_text=idea,
        extra_context=MappingProxyType(dict(frontmatter_context)),
        emit_agent_dispatched=True,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            _materialize_phase1_mock_fixtures(
                tmp_path,
                spec=spec,
                registry=registry,
                idea_text=idea,
                extra_context=frontmatter_context,
            )
            runtime = MockAIRuntime(tmp_path)
            panel = asyncio.run(
                _dispatch_phase1_panel(
                    spec=spec,
                    registry=registry,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    runtime=runtime,
                    observer=observer,
                )
            )
        except WorkflowError as exc:
            # P18: guard exc.details Mapping shape before dict(...).
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error(
                "ERR_USER_INPUT",
                str(exc),
                ctx=ctx,
                details=wf_details,
            )
        # P14: never swallow cancellation/interrupt — re-raise BEFORE broad except.
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except Exception as exc:
            emit_error(
                "ERR_PANEL_DISPATCH_FAILED",
                f"panel dispatch failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    if panel.outcome != "success":
        emit_error(
            "ERR_PANEL_DISPATCH_FAILED",
            f"panel finished with outcome={panel.outcome!r}",
            ctx=ctx,
            details={"outcome": panel.outcome},
        )

    if panel.synthesizer_result is None:
        emit_error(
            "ERR_PANEL_DISPATCH_FAILED",
            "panel missing synthesizer result",
            ctx=ctx,
        )

    # D2-B verification: the synthesizer's pre-write hook chain wrote the canonical
    # file; CLI only verifies presence + non-empty body and updates state.json.
    if not product_path.is_file():
        emit_error(
            "ERR_PANEL_DISPATCH_FAILED",
            f"synthesizer did not produce {_PRODUCT_REL}",
            ctx=ctx,
            details={"path": str(product_path)},
        )
    written = product_path.read_text(encoding="utf-8")
    if not written.strip():
        emit_error(
            "ERR_PANEL_DISPATCH_FAILED",
            f"synthesizer wrote empty {_PRODUCT_REL}",
            ctx=ctx,
            details={"path": str(product_path)},
        )

    from sdlc.journal._seq import _read_highest_seq  # deferred
    from sdlc.state import read_state_or_recover, write_state_atomic_sync  # deferred

    # D4-B: trust the dispatcher's allocator + per-CLI bookkeeping. Re-scan journal
    # to find the highest seq the dispatcher allocated, then advance state by +1.
    highest_seq = _read_highest_seq(journal_path.resolve())

    try:
        pre = read_state_or_recover(state_path.resolve(), journal_path.resolve())
    except StateError as exc:
        # P18: guard exc.details Mapping shape before dict(...).
        state_err_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_STATE_MALFORMED",
            exc.message,
            ctx=ctx,
            details=state_err_details,
        )
    # P17: state.json must still be readable mid-run; surface a clear error if
    # it disappeared between `state_path.is_file()` and the post-dispatch read.
    if pre is None:
        emit_error(
            "ERR_NOT_INITIALIZED",
            "state.json disappeared mid-run",
            ctx=ctx,
            details={"path": str(state_path)},
        )
    try:
        # P15: monotonically advance `next_monotonic_seq` — never regress.
        # The dispatcher's allocator advanced the journal; CLI takes max() of the
        # state's current value and the journal-derived seq+1 so a parallel writer
        # cannot rewind the state under us.
        next_seq = max(pre.next_monotonic_seq, highest_seq + 1)
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

    try:
        evaluate_postconditions(
            spec,
            repo_root=root,
            agent_runs_path=agent_runs_path.resolve(),
            product_rel=_PRODUCT_REL,
        )
    except WorkflowError as exc:
        # P18: guard exc.details Mapping shape before dict(...).
        post_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_USER_INPUT",
            f"postcondition failed: {exc}",
            ctx=ctx,
            details=post_details,
        )

    if json_mode:
        emit_json(
            "start",
            {
                "artifact": _PRODUCT_REL,
                "outcome": "success",
                "phase": 1,
                "specialists": [
                    spec.primary_agent,
                    *spec.parallel_agents,
                    spec.synthesizer_agent,
                ],
            },
            ctx=ctx,
        )
    else:
        echo(f"sdlc start: wrote {product_path.relative_to(root)}", ctx=ctx)
