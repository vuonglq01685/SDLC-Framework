"""`sdlc ux` — Phase 2 UX track (FR13, Story 2A.13).

Pre-flight + error-code mapping only. Dispatch / write logic lives in
:mod:`sdlc.cli._ux_pipeline` to keep this module under the AC5 LOC cap
(sibling pattern from :mod:`sdlc.cli.epics` + :mod:`sdlc.cli.stories`).

Patches applied during code review (2026-05-14):
- P2: distinct ``ERR_SIGNOFF_READ_FAILED`` for corrupt-signoff vs not-approved
- P8: reject empty / whitespace-only ``01-PRODUCT.md`` before prompt-build
- P10: use keyword ``compute_state(phase=1, repo_root=root)`` per 2A.7 style
- P12: widen ``WorkflowRegistry.load`` catch to ``yaml.YAMLError`` / ``OSError``
- P13: import ``artifact_contains_boundary`` from public :mod:`sdlc.cli._boundary`
- P14: dispatch logic extracted to :mod:`sdlc.cli._ux_pipeline`
- P15: wrap ``RuntimeError`` from ``evaluate_postconditions`` into ``WorkflowError``
- P18: re-raise ``typer.Exit`` in the dispatch ``try`` block (it inherits from
       ``RuntimeError``, NOT ``SystemExit``, so the bare ``except Exception``
       would otherwise swallow inner ``emit_error`` calls from the pipeline and
       re-wrap them as ``ERR_UX_DISPATCH_FAILED``)
- P19: narrow ``load_registry`` ``except`` with cause-bearing ``details``
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import typer
import yaml
from pydantic import ValidationError

from sdlc.cli._boundary import artifact_contains_boundary
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._ux_pipeline import (
    materialize_ux_mock_fixture,
    ux_dispatch_and_write_async,
)
from sdlc.cli.output import emit_error, emit_json
from sdlc.dispatcher import build_pre_write_hook_chain
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import SignoffError, SpecialistError, WorkflowError
from sdlc.signoff import SignoffState, compute_state
from sdlc.specialists import load_registry
from sdlc.workflows.registry import WorkflowRegistry

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_PRODUCT_REL: Final[str] = "01-Requirement/01-PRODUCT.md"
_UX_DIR_REL: Final[str] = "02-Architecture/01-UX"
_SLASH_CMD: Final[str] = "/sdlc-ux"
_SPECIALIST: Final[str] = "ux-designer"


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg  # deferred

    return Path(pkg.__file__).resolve().parent


def run_ux(*, ctx: typer.Context, allow_mock: bool = False) -> None:  # noqa: C901, PLR0912, PLR0915
    """Initiate Phase 2 UX track (FR13, AC5).

    Note on exception flow: ``emit_error`` always raises ``typer.Exit``, which
    inherits from ``RuntimeError`` (NOT ``SystemExit``). The dispatch ``try``
    therefore explicitly re-raises ``typer.Exit`` (P18) so the bare
    ``except Exception`` cannot swallow inner ``emit_error`` calls from the
    pipeline and re-wrap them as ``ERR_UX_DISPATCH_FAILED``.
    """
    from sdlc.cli._runtime_selection import build_runtime, enforce_allow_mock_gate, use_mock_runtime

    allow_mock_invoked = enforce_allow_mock_gate(allow_mock=allow_mock, ctx=ctx)
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

    # P2 (review-A) + PB4 (review-B): distinct error code for corrupt-signoff vs
    # not-approved. Catch widened to also include ``pydantic.ValidationError``
    # (schema-valid YAML that violates ``SignoffRecord``) and ``OSError``
    # (permission denied / missing dir / stale NFS) so neither leaks as a raw
    # traceback.  Note this code is INTENTIONALLY distinct from sibling
    # ``signoff.py`` (uses ``ERR_PHASE1_NOT_APPROVED``) and ``epics.py``
    # (uses ``ERR_SIGNOFF_STATE``) — DB1=c (review-B): the three codes carry
    # different semantics; the convention table is documented in the spec
    # Change Log.
    try:
        phase1_state = compute_state(phase=1, repo_root=root)  # P10 — kwarg
    except (SignoffError, ValidationError, OSError) as exc:
        # PC6 (review-C): sanitize the exception representation before
        # embedding in the envelope. ``pydantic.ValidationError.__str__``
        # emits multi-line text including ANSI escapes and raw user-controlled
        # ``input`` values from the offending YAML — those would corrupt
        # line-delimited JSON consumers and could leak terminal-control
        # sequences. Strip newlines and truncate.
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
    # PB10 (review-B): ``encoding="utf-8-sig"`` strips a leading UTF-8 BOM
    # (``﻿``) so a BOM-only file does NOT bypass the P8 empty-check
    # below — ``str.strip()`` does not strip BOM by default.
    try:
        product_text = product_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"{_PRODUCT_REL} is not valid UTF-8: {exc}",
            ctx=ctx,
            details={"path": str(product_path), "cause": str(exc)},
        )
    # P8: reject empty / whitespace-only PRODUCT.md so empty idea_text doesn't
    # silently propagate into the specialist prompt.
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

    ux_dir = root / _UX_DIR_REL
    ux_dir.mkdir(parents=True, exist_ok=True)
    workflows_dir = _workflows_package_dir()
    # P12 (review-A) + PB5 (review-B): widen catch to YAML / OSError /
    # pydantic.ValidationError so a malformed workflow yaml, unreadable file,
    # or a yaml whose value types violate ``WorkflowSpec`` becomes a structured
    # ERR_INFRASTRUCTURE envelope instead of a raw Python traceback.
    try:
        spec = WorkflowRegistry.load(workflows_dir).get(_SLASH_CMD)
    except (WorkflowError, yaml.YAMLError, OSError, ValidationError) as exc:
        wf_details = (
            dict(exc.details)
            if isinstance(exc, WorkflowError) and isinstance(exc.details, Mapping)
            else {"cause": str(exc)}
        )
        emit_error(
            "ERR_INFRASTRUCTURE", f"workflow load failed: {exc}", ctx=ctx, details=wf_details
        )
    agents_dir = root / _AGENTS_REL
    # P19: narrow except — SpecialistError is the registry's typed failure, plus
    # OSError for missing/unreadable agents_dir. Other exceptions propagate.
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

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            if use_mock_runtime():
                materialize_ux_mock_fixture(
                    tmp_path, spec=spec, registry=registry, product_text=product_text
                )
            runtime = build_runtime(fixtures_dir=tmp_path)
            artifacts = asyncio.run(
                ux_dispatch_and_write_async(
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
                    allow_mock_invoked=allow_mock_invoked,
                )
            )
        except WorkflowError as exc:
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error("ERR_UX_DISPATCH_FAILED", str(exc), ctx=ctx, details=wf_details)
        except (KeyboardInterrupt, asyncio.CancelledError, typer.Exit):
            # P18: ``typer.Exit`` is ``click.exceptions.Exit`` inheriting from
            # ``RuntimeError`` (NOT ``SystemExit``) — without this clause, the
            # bare ``except Exception`` below would swallow inner ``emit_error``
            # calls from the pipeline (e.g. ``ERR_UNSAFE_FILENAME``) and
            # re-wrap them as ``ERR_UX_DISPATCH_FAILED``. Re-raise so the inner
            # exit code and error envelope survive intact.
            raise
        except Exception as exc:
            emit_error(
                "ERR_UX_DISPATCH_FAILED",
                f"UX pipeline failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    # P15: evaluate_postconditions raises bare RuntimeError when plumbing is
    # missing (programmer error). Wrap it as WorkflowError so the structured
    # ERR_POSTCONDITION_FAILED envelope still applies — never leak a raw
    # Python traceback to the operator.
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
    except RuntimeError as exc:
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition wiring incomplete: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )
    except OSError as exc:
        # PB6 (review-B): ``_check_ux_dir_non_empty`` calls ``is_dir()`` /
        # ``glob`` which may raise OSError on non-traversable parents or stale
        # NFS mounts. Surface as a structured envelope rather than a raw
        # traceback.
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition I/O failed: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
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
