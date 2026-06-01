"""`sdlc research` — Phase 1 topical research (FR7, Story 2A.9).

The dispatcher's ``dispatch`` runs with ``persist_artifact=False`` so the specialist
body is captured without emitting ``artifact_written``; the CLI prepends deterministic
YAML frontmatter (AC6/D2) then writes the final bytes and appends a single
``artifact_written`` with ``actor="cli"`` and ``after_hash`` over the full file.

NOTE: dispatcher writes nothing to disk for the research body in this mode; the
CLI performs the sole artifact write. Non-atomic double-write posture from the
general ``Path.write_text`` primitive is inherited (``EPIC-2A-DEBT-WRITE-PRIMITIVE``).

Concurrency caveat: two simultaneous ``/sdlc-research`` invocations with the same
topic may collide on the deduplicating suffix in v1. The journal flock covers the
dispatch window but not the path resolution. v1.x: tighten via flock-on-research-dir.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

import typer
import yaml

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._runtime_selection import merge_observer_mock_audit
from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.concurrency.io_primitives import atomic_write
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
from sdlc.dispatcher.postconditions import (
    evaluate_postconditions,
    validate_research_md_text,
)
from sdlc.errors import StateError, WorkflowError
from sdlc.journal import append as journal_append
from sdlc.runtime.abc import AIRuntime
from sdlc.runtime.mock import compute_prompt_hash
from sdlc.specialists import SpecialistRegistry, load_registry
from sdlc.state.reader import read_state_or_refuse
from sdlc.workflows.registry import WorkflowRegistry

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_RESEARCH_DIR_REL: Final[str] = "01-Requirement/02-Research"
_MAX_SLUG_LEN: Final[int] = 80
_RESEARCH_SEQ_MIN: Final[int] = 2
_RESEARCH_SEQ_CAP: Final[int] = 999


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg  # deferred

    return Path(pkg.__file__).resolve().parent


def _slugify_topic(topic: str) -> str:
    """Convert topic to a filesystem-safe slug (ASCII alnum runs only)."""
    parts = re.findall(r"[a-z0-9]+", topic.lower())
    if not parts:
        raise WorkflowError(
            "topic produces empty slug; provide a topic with at least one alphanumeric character",
            details={"topic": topic},
        )
    slug = "-".join(parts)
    if len(slug) <= _MAX_SLUG_LEN:
        return slug
    prefix = slug[:_MAX_SLUG_LEN]
    if prefix.endswith("-"):
        return prefix[:-1] if len(prefix) > 1 else prefix[: _MAX_SLUG_LEN - 1]
    last_hy = prefix.rfind("-")
    if last_hy > 0:
        return prefix[:last_hy]
    return prefix[:_MAX_SLUG_LEN]


def _occupied_research_suffixes(slug: str, research_dir: Path) -> set[int]:
    occupied: set[int] = {1}
    if not research_dir.exists():
        return occupied
    prefix = f"{slug}-"
    for p in research_dir.glob(f"{slug}-*.md"):
        stem = p.stem
        if not stem.startswith(prefix):  # pragma: no cover - glob guarantees prefix
            continue
        suffix = stem[len(prefix) :]
        try:
            n = int(suffix)
        except ValueError:
            continue
        if _RESEARCH_SEQ_MIN <= n <= _RESEARCH_SEQ_CAP:
            occupied.add(n)
    return occupied


def _next_research_path(slug: str, *, research_dir: Path) -> Path:
    base = research_dir / f"{slug}.md"
    if not base.exists():
        return base
    occupied = _occupied_research_suffixes(slug, research_dir)
    for n in range(_RESEARCH_SEQ_MIN, _RESEARCH_SEQ_CAP + 1):
        if n not in occupied:
            return research_dir / f"{slug}-{n}.md"
    cap = _RESEARCH_SEQ_CAP
    raise WorkflowError(
        f"research slug exhausted: {slug}-{cap}.md exists; choose a more specific topic",
        details={"slug": slug},
    )


def _slug_title_heading(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def _wrap_research_artifact(raw_body: str, *, topic: str, slug: str, ts: str) -> str:
    fm: dict[str, object] = {
        "schema_version": 1,
        "kind": "research",
        "topic": topic,
        "slug": slug,
        "researched_at": ts,
        "researched_by_specialist": "technical-researcher",
    }
    fm_yaml = yaml.safe_dump(
        fm, sort_keys=True, default_flow_style=False, allow_unicode=True
    ).strip()
    title = _slug_title_heading(slug)
    body = raw_body if raw_body.endswith("\n") else raw_body + "\n"
    return f"---\n{fm_yaml}\n---\n\n# {title}\n\n{body}"


def _materialize_research_mock_fixtures(
    dest_dir: Path,
    *,
    spec: WorkflowSpec,
    registry: SpecialistRegistry,
    topic: str,
    output_text: str,
) -> None:
    sp = registry.get("technical-researcher")
    prompt = phase1_prompt_builder(
        sp,
        spec,
        idea_text=topic,
        role="primary",
        upstream_outputs=(),
    )
    h = compute_prompt_hash(prompt)
    records = {
        h: {
            "output_text": output_text,
            "tokens_in": 1,
            "tokens_out": 1,
            "tool_calls": [],
        }
    }
    atomic_write(
        dest_dir / f"{spec.name}.yaml",
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
    )


def _research_seq_for_path(path: Path, slug: str) -> int:
    """Map a research artifact path back to its dedup seq integer.

    P27 (code review): raise loudly on malformed inputs instead of silently
    returning 1. The path is always produced by ``_next_research_path`` in v1, so
    a parse failure means an invariant break (e.g., a future caller passing a
    manually-named file). Silent fallback to 1 makes such bugs hard to spot in
    audit logs (two distinct files would both record ``research_seq=1``).
    """
    name = path.name
    if name == f"{slug}.md":
        return 1
    if name.startswith(f"{slug}-") and name.endswith(".md"):
        suf = name[len(slug) + 1 : -3]
        try:
            return int(suf)
        except ValueError as exc:
            raise WorkflowError(
                f"research path {name!r} has non-integer dedup suffix {suf!r}",
                details={"path": str(path), "slug": slug, "suffix": suf},
            ) from exc
    raise WorkflowError(
        f"research path {name!r} does not match slug {slug!r}",
        details={"path": str(path), "slug": slug},
    )


async def _research_dispatch_async(
    *,
    spec: WorkflowSpec,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    topic: str,
    slug: str,
    target_path: Path,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    topic_hash: str,
    allow_mock_invoked: bool = False,
) -> str:
    """Run the dispatch + frontmatter wrap + journal emit.

    P20 (code review): return the cached ``rel_art`` POSIX string so the outer
    CLI tail does not recompute ``target_path.resolve().relative_to(...)``. The
    recompute window was open to symlink TOCTOU and would crash AFTER the
    artifact + journal were already committed.
    """

    def _prompt_builder(sp: object, wf: WorkflowSpec) -> str:
        from sdlc.specialists.frontmatter import Specialist

        assert isinstance(sp, Specialist)
        return phase1_prompt_builder(
            sp,
            wf,
            idea_text=topic,
            role="primary",
            upstream_outputs=(),
        )

    observer_ctx: dict[str, object] = {
        "agent_dispatched_extras": {
            "topic_hash": topic_hash,
            "slug": slug,
        },
    }
    merge_observer_mock_audit(observer_ctx, allow_mock_invoked=allow_mock_invoked)
    observer = PanelObserver(
        slash_command="/sdlc-research",
        idea_text=topic,
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
        hooks=build_pre_write_hook_chain(repo_root=root),
        observer=observer,
        persist_artifact=False,
        target_path_override=target_path,
    )
    if result.outcome != "success":
        raise WorkflowError(
            f"research dispatch finished with outcome={result.outcome!r}",
            details={"outcome": result.outcome},
        )
    ts = now_rfc3339_utc_ms()
    final_text = _wrap_research_artifact(
        result.agent_result.output_text,
        topic=topic,
        slug=slug,
        ts=ts,
    )
    # P4 (code review): validate the artifact SHAPE in memory BEFORE writing +
    # journaling. A malformed specialist body (e.g., missing H2) used to leave
    # an orphan ``artifact_written`` journal entry pointing at an unshippable
    # file because the postcondition ran in the outer scope.
    validate_research_md_text(final_text, source_label=str(target_path))
    atomic_write(target_path, final_text)
    rel = target_path.resolve().relative_to(root.resolve()).as_posix()
    seq_aw = await allocate_seq(journal_path)
    run_id = str(uuid.uuid4())
    await journal_append(
        make_journal_entry(
            seq=seq_aw,
            ts=now_ts(),
            kind="artifact_written",
            target_id=rel,
            payload={
                "slash_command": "/sdlc-research",
                "phase": 1,
                "specialist": "technical-researcher",
                "topic_hash": topic_hash,
                "research_seq": _research_seq_for_path(target_path, slug),
                "target": rel,
                "writer": "cli",
                "run_id": run_id,
                "mock": result.agent_result.mock,
            },
            after_hash=content_hash(final_text),
            actor="cli",
        ),
        journal_path,
    )
    return rel  # P20: caller uses this verbatim; no resolve() in outer scope.


def run_research(  # noqa: C901, PLR0912, PLR0915 — CLI orchestration; Story 2A.9 (mirrors start.py posture).
    *, ctx: typer.Context, topic: str, allow_mock: bool = False
) -> None:
    """Run Phase 1 topical research; write under ``01-Requirement/02-Research/``."""
    from sdlc.cli._runtime_selection import build_runtime, enforce_allow_mock_gate, use_mock_runtime
    from sdlc.journal._seq import _read_highest_seq

    allow_mock_invoked = enforce_allow_mock_gate(allow_mock=allow_mock, ctx=ctx)
    from sdlc.state import read_state_or_recover, write_state_atomic_sync

    ctx_obj: Mapping[str, object] = ctx.obj if isinstance(ctx.obj, Mapping) else {}
    json_mode = bool(ctx_obj.get("json", False))
    if not topic.strip():
        emit_error("ERR_USER_INPUT", "topic must be non-empty", ctx=ctx)

    root = _get_repo_root_or_cwd()
    state_path = root / _STATE_REL
    journal_path = root / _JOURNAL_REL
    agent_runs_path = root / _RUNS_REL

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
            f"phase 1 required for /sdlc-research; current phase: {state.phase}",
            ctx=ctx,
            details={"current_phase": state.phase},
        )

    try:
        slug = _slugify_topic(topic)
    except WorkflowError as exc:
        wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error("ERR_USER_INPUT", str(exc), ctx=ctx, details=wf_details)

    research_dir = root / _RESEARCH_DIR_REL
    research_dir.mkdir(parents=True, exist_ok=True)
    target_path = _next_research_path(slug, research_dir=research_dir)

    workflows_dir = _workflows_package_dir()
    try:
        wf_registry = WorkflowRegistry.load(workflows_dir)
        spec = wf_registry.get("/sdlc-research")
    except WorkflowError as exc:
        wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_INFRASTRUCTURE", f"workflow load failed: {exc}", ctx=ctx, details=wf_details
        )

    # P31 (code review): the postcondition ``research_md_exists`` is the validator
    # that protects the FR7 contract (frontmatter shape + body H2). If the YAML is
    # edited to drop the postcondition, the CLI silently proceeds with no
    # validation. Refuse loudly instead.
    if "research_md_exists" not in spec.postconditions:
        emit_error(
            "ERR_INFRASTRUCTURE",
            "workflow sdlc-research.yaml is missing required postcondition "
            "'research_md_exists'; the validator that protects FR7 frontmatter shape",
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

    topic_hash = "sha256:" + hashlib.sha256(topic.encode("utf-8")).hexdigest()
    mock_body = (
        "## Research Findings\n\n"
        "**PLACEHOLDER** — this body was written by `sdlc research` running against "
        "MockAIRuntime. It is not a research deliverable when mock mode is enabled.\n"
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            if use_mock_runtime():
                _materialize_research_mock_fixtures(
                    tmp_path,
                    spec=spec,
                    registry=registry,
                    topic=topic,
                    output_text=mock_body,
                )
            runtime = build_runtime(fixtures_dir=tmp_path)
            # P20 (code review): capture the rel_art string at write time inside
            # _research_dispatch_async; do NOT recompute resolve()/relative_to()
            # in the outer scope where a symlink TOCTOU would crash AFTER the
            # journal entry is already committed.
            rel_art = asyncio.run(
                _research_dispatch_async(
                    spec=spec,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    topic=topic,
                    slug=slug,
                    target_path=target_path,
                    runtime=runtime,
                    registry=registry,
                    topic_hash=topic_hash,
                    allow_mock_invoked=allow_mock_invoked,
                )
            )
        except WorkflowError as exc:
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error("ERR_USER_INPUT", str(exc), ctx=ctx, details=wf_details)
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except Exception as exc:
            emit_error(
                "ERR_RESEARCH_DISPATCH_FAILED",
                f"research dispatch failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    try:
        evaluate_postconditions(
            spec,
            repo_root=root,
            agent_runs_path=agent_runs_path.resolve(),
            research_artifact_abs=target_path.resolve(),
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
        state_err_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error("ERR_STATE_MALFORMED", exc.message, ctx=ctx, details=state_err_details)
    if pre is None:
        emit_error(
            "ERR_NOT_INITIALIZED",
            "state.json disappeared mid-run",
            ctx=ctx,
            details={"path": str(state_path)},
        )
    next_seq = max(pre.next_monotonic_seq, highest_seq + 1)
    try:
        write_state_atomic_sync(
            pre.model_copy(update={"next_monotonic_seq": next_seq}), target=state_path
        )
    except OSError as exc:
        emit_error(
            "ERR_STATE_WRITE_FAILED",
            f"state update failed: {exc}",
            ctx=ctx,
            details={"path": str(state_path)},
        )

    # rel_art was captured at write time inside _research_dispatch_async (P20).
    if json_mode:
        emit_json(
            "research",
            {
                "phase": 1,
                "artifact": rel_art,
                "specialist": "technical-researcher",
                "slug": slug,
                "outcome": "success",
            },
            ctx=ctx,
        )
    else:
        echo(f"sdlc research: wrote {rel_art}", ctx=ctx)
