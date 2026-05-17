"""`sdlc architect` — Phase 2 system architecture track (FR14, Story 2A.14).

Pre-flight + primary dispatch + dynamic sub-track dispatch.

AC2/D1: sub-tracks dispatched sequentially (not parallel). Safe, simple, correct for v1.
         Parallel dispatch deferred to Story 2B (EPIC-2A-DEBT-ARCHITECT-PARALLEL-SUBTRACKS).
AC3/D1: sub-track allowlist is a hardcoded ``_SUBTRACK_SPECIALISTS`` mapping. YAGNI.
         Dynamic discovery deferred to Story 2B.9 (EPIC-2A-DEBT-ARCHITECT-SUBTRACK-REGISTRY).
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

import typer
from pydantic import ValidationError

from sdlc.cli._architect_pipeline import (
    build_sub_track_prompt,
    dispatch_and_write,
    materialize_primary_mock,
    materialize_sub_track_mock,
    parse_requires_block,
)
from sdlc.cli._boundary import artifact_contains_boundary
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import emit_error, emit_json
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import (
    build_pre_write_hook_chain,
    phase1_prompt_builder,
)
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import SignoffError, SpecialistError, WorkflowError
from sdlc.runtime.mock import MockAIRuntime
from sdlc.signoff import SignoffState, compute_state
from sdlc.specialists import load_registry
from sdlc.specialists.frontmatter import Specialist
from sdlc.workflows.registry import WorkflowRegistry

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_PRODUCT_REL: Final[str] = "01-Requirement/01-PRODUCT.md"
_ARCH_REL: Final[str] = "02-Architecture/02-System/ARCHITECTURE.md"
_SLASH_CMD: Final[str] = "/sdlc-architect"
_PRIMARY_SPECIALIST: Final[str] = "system-architect"

# AC3/D1: hardcoded allowlist mapping sub-track → specialist name.
_SUBTRACK_SPECIALISTS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "database": "database-architect",
        "observability": "observability-architect",
        "security": "security-architect",
    }
)


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg  # deferred

    return Path(pkg.__file__).resolve().parent


def run_architect(*, ctx: typer.Context) -> None:  # noqa: C901, PLR0912, PLR0915
    """Initiate Phase 2 system architecture track (FR14, AC5)."""
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
        phase1_state = compute_state(phase=1, repo_root=root)
    except (SignoffError, ValidationError, OSError) as exc:
        cause = " | ".join(str(exc).splitlines())[:500]
        emit_error(
            "ERR_SIGNOFF_READ_FAILED",
            f"phase 1 signoff state could not be read: {cause}",
            ctx=ctx,
            details={"phase": 1, "cause": cause},
        )
    if phase1_state != SignoffState.APPROVED:
        emit_error(
            "ERR_PHASE1_NOT_APPROVED",
            "phase 1 signoff must be APPROVED before starting Phase 2 architecture work; "
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
        product_text = product_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"{_PRODUCT_REL} is not valid UTF-8: {exc}",
            ctx=ctx,
            details={"path": str(product_path), "cause": str(exc)},
        )
    if not product_text.strip():
        emit_error(
            "ERR_USER_INPUT",
            f"{_PRODUCT_REL} is empty; run 'sdlc start' or add content first",
            ctx=ctx,
            details={"path": str(product_path)},
        )
    if artifact_contains_boundary(product_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"{_PRODUCT_REL} contains the data-vs-instruction boundary marker",
            ctx=ctx,
            details={"path": str(product_path)},
        )

    # AC5: create output directories before dispatch
    arch_dir = root / "02-Architecture" / "02-System"
    sub_tracks_dir = arch_dir / "sub-tracks"
    arch_dir.mkdir(parents=True, exist_ok=True)
    sub_tracks_dir.mkdir(parents=True, exist_ok=True)

    arch_path = arch_dir / "ARCHITECTURE.md"
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"

    workflows_dir = _workflows_package_dir()
    try:
        spec = WorkflowRegistry.load(workflows_dir).get(_SLASH_CMD)
    except (WorkflowError, ValidationError, OSError) as exc:
        wf_details = (
            dict(exc.details)
            if isinstance(exc, WorkflowError) and isinstance(exc.details, Mapping)
            else {"cause": str(exc)}
        )
        emit_error(
            "ERR_INFRASTRUCTURE", f"workflow load failed: {exc}", ctx=ctx, details=wf_details
        )

    agents_dir = root / _AGENTS_REL
    try:
        registry = load_registry(agents_dir)
    except (SpecialistError, OSError) as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"specialist registry load failed: {exc}",
            ctx=ctx,
            details={"agents_dir": str(agents_dir), "cause": str(exc)},
        )

    hooks = build_pre_write_hook_chain(repo_root=root)

    # AC5 step 3-6: primary dispatch + write ARCHITECTURE.md
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            materialize_primary_mock(
                tmp_path, spec=spec, registry=registry, product_text=product_text
            )
            runtime = MockAIRuntime(tmp_path)

            def _primary_prompt(sp: Specialist, wf: WorkflowSpec) -> str:
                return phase1_prompt_builder(
                    sp, wf, idea_text=product_text, role="primary", upstream_outputs=()
                )

            # Primary output is re-read from disk below; the return value of
            # dispatch_and_write is intentionally not bound here.
            asyncio.run(
                dispatch_and_write(
                    spec=spec,
                    target_path=arch_path,
                    rel_path=arch_rel,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    prompt_builder=_primary_prompt,
                    runtime=runtime,
                    registry=registry,
                    hooks=hooks,
                    specialist_name=_PRIMARY_SPECIALIST,
                    slash_cmd=_SLASH_CMD,
                )
            )
        except WorkflowError as exc:
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error("ERR_ARCHITECT_DISPATCH_FAILED", str(exc), ctx=ctx, details=wf_details)
        except (KeyboardInterrupt, asyncio.CancelledError, typer.Exit):
            raise
        except OSError as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"architect primary dispatch I/O failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )
        except Exception as exc:
            emit_error(
                "ERR_ARCHITECT_DISPATCH_FAILED",
                f"architect pipeline failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    # AC5 step 7: parse frontmatter from written ARCHITECTURE.md (not raw output_text)
    try:
        requires = parse_requires_block(arch_path)
    except (OSError, UnicodeDecodeError) as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"could not re-read {arch_rel} to parse sub-tracks: {exc}",
            ctx=ctx,
            details={"path": str(arch_path), "cause": str(exc)},
        )

    # AC5 step 8: validate all requires items against _SUBTRACK_SPECIALISTS
    if requires:
        unknown = [r for r in requires if r not in _SUBTRACK_SPECIALISTS]
        if unknown:
            sorted_available = sorted(_SUBTRACK_SPECIALISTS.keys())
            unknown_display = ", ".join(repr(u) for u in unknown)
            emit_error(
                "ERR_UNKNOWN_SUB_TRACK",
                f"unknown sub-track(s): {unknown_display}; available: {sorted_available}",
                ctx=ctx,
                details={"unknown": unknown, "available": sorted_available},
            )

    # CR14-D2: drop orphan sub-track files from a prior run with a different
    # (or larger) requires: set, so postconditions never see stale artifacts.
    expected_sub_files = {f"{r}.md" for r in requires}
    if sub_tracks_dir.is_dir():
        for stale in sorted(sub_tracks_dir.glob("*.md")):
            if stale.name not in expected_sub_files:
                stale.unlink()

    # AC5 step 9: dispatch sub-tracks sequentially (D1)
    sub_track_artifacts: list[dict[str, str]] = []
    for sub_track in requires:
        specialist_name = _SUBTRACK_SPECIALISTS[sub_track]
        sub_path = sub_tracks_dir / f"{sub_track}.md"
        sub_rel = f"02-Architecture/02-System/sub-tracks/{sub_track}.md"

        sub_spec = WorkflowSpec(
            schema_version=1,
            name=f"phase2-{sub_track}-sub-track",
            slash_command=f"{_SLASH_CMD}/{sub_track}",
            primary_agent=specialist_name,
            parallel_agents=(),
            synthesizer_agent=None,
            postconditions=(),
            write_globs={specialist_name: (sub_rel,)},
            stop_on_postcondition_failure=False,
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            try:
                arch_text = arch_path.read_text(encoding="utf-8")
                materialize_sub_track_mock(
                    tmp_path,
                    sub_track=sub_track,
                    specialist_name=specialist_name,
                    sub_spec=sub_spec,
                    registry=registry,
                    product_text=product_text,
                    arch_text=arch_text,
                )
                runtime = MockAIRuntime(tmp_path)

                # ``_at`` is default-bound to dodge loop late-binding; the
                # shared builder keeps this prompt byte-identical to the
                # fixture key produced by materialize_sub_track_mock.
                def _sub_prompt(
                    sp: Specialist,
                    wf: WorkflowSpec,
                    _at: str = arch_text,
                ) -> str:
                    return build_sub_track_prompt(sp, wf, product_text=product_text, arch_text=_at)

                asyncio.run(
                    dispatch_and_write(
                        spec=sub_spec,
                        target_path=sub_path,
                        rel_path=sub_rel,
                        root=root,
                        journal_path=journal_path,
                        agent_runs_path=agent_runs_path,
                        prompt_builder=_sub_prompt,
                        runtime=runtime,
                        registry=registry,
                        hooks=hooks,
                        specialist_name=specialist_name,
                        slash_cmd=f"{_SLASH_CMD}/{sub_track}",
                    )
                )
                sub_track_artifacts.append({"track": sub_track, "path": sub_rel})
            except WorkflowError as exc:
                wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
                emit_error(
                    "ERR_ARCHITECT_DISPATCH_FAILED",
                    f"sub-track {sub_track!r} failed: {exc}",
                    ctx=ctx,
                    details=wf_details,
                )
            except (KeyboardInterrupt, asyncio.CancelledError, typer.Exit):
                raise
            except OSError as exc:
                emit_error(
                    "ERR_INFRASTRUCTURE",
                    f"sub-track {sub_track!r} I/O failed: {exc}",
                    ctx=ctx,
                    details={"sub_track": sub_track, "error": str(exc)},
                )
            except Exception as exc:
                emit_error(
                    "ERR_ARCHITECT_DISPATCH_FAILED",
                    f"sub-track {sub_track!r} pipeline failed: {exc}",
                    ctx=ctx,
                    details={"sub_track": sub_track, "error": str(exc)},
                )

    # AC8 + AC11: evaluate postconditions
    try:
        evaluate_postconditions(
            spec,
            repo_root=root,
            agent_runs_path=agent_runs_path.resolve(),
            architecture_path_abs=arch_path.resolve(),
        )
    except WorkflowError as exc:
        post_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition failed: {exc}",
            ctx=ctx,
            details=post_details,
        )
    except RuntimeError as exc:
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition wiring incomplete: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )
    except OSError as exc:
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition I/O failed: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )

    # AC1: emit_json summary
    emit_json(
        "architect",
        {
            "phase": 2,
            "track": "architect",
            "specialist": _PRIMARY_SPECIALIST,
            "architecture_path": arch_rel,
            "sub_tracks_dispatched": requires,
            "sub_track_artifacts": sub_track_artifacts,
            "outcome": "success",
        },
        ctx=ctx,
    )
