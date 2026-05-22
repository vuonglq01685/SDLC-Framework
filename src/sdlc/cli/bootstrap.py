"""`sdlc bootstrap` — Phase 3 greenfield codebase scaffolding (FR15, Story 2A.15).

AC2/D1: "source exists" = any regular file under src/ not in _BOOTSTRAP_PLACEHOLDER_ALLOWLIST.
AC2/D2: source root hardcoded as "src" relative to repo_root
  (EPIC-2A-DEBT-BOOTSTRAP-SOURCE-ROOT-CONFIG).
AC3/D1: specialist named "code-bootstrapper" per architecture.md:1696 + epics.md:1329.
AC8/D1: mock writes src/__init__.py so re-run auto-skips.
AC1/D3: CLI pre-flight is Phase-2 gate; phase_gate hook is permissive on src/
  (EPIC-2A-DEBT-PHASE-GATE-SRC-TESTS-COVERAGE).
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._bootstrap_pipeline import (
    _PRIMARY_SPECIALIST,
    _SLASH_CMD,
    _bootstrap_dispatch_write,
    _mock_bootstrap_body,
    _write_mock_fixture,
)
from sdlc.cli._boundary import artifact_contains_boundary
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._runtime_selection import (
    build_runtime,
    enforce_allow_mock_gate,
    use_mock_runtime,
)
from sdlc.cli.output import emit_error, emit_json
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import (
    build_pre_write_hook_chain,
    phase1_compound_prompt_builder,
)
from sdlc.dispatcher.postconditions import evaluate_postconditions
from sdlc.errors import SignoffError, SpecialistError, WorkflowError
from sdlc.runtime.mock import compute_prompt_hash
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
# AC2/D1: explicit placeholder allowlist — files that do NOT count as "real source".
_BOOTSTRAP_PLACEHOLDER_ALLOWLIST: Final[frozenset[str]] = frozenset({".gitkeep", "README.md"})


def _source_exists(src_root: Path) -> bool:
    """True if src_root has at least one regular file outside the placeholder allowlist."""
    if not src_root.exists() or not src_root.is_dir():
        return False
    for path in src_root.rglob("*"):
        if path.is_file() and path.name not in _BOOTSTRAP_PLACEHOLDER_ALLOWLIST:
            return True
    return False


def _workflows_package_dir() -> Path:
    import sdlc.workflows_yaml as pkg

    return Path(pkg.__file__).resolve().parent


def run_bootstrap(*, ctx: typer.Context, allow_mock: bool = False) -> None:  # noqa: C901, PLR0912, PLR0915
    """Initiate Phase 3 codebase scaffolding (FR15, AC5)."""
    allow_mock_invoked = enforce_allow_mock_gate(allow_mock=allow_mock, ctx=ctx)
    root = _get_repo_root_or_cwd()
    source_root = root / "src"
    journal_path = root / _JOURNAL_REL
    agent_runs_path = root / _RUNS_REL

    # Step 2 — AUTO-SKIP FIRST (AC2/FR15 critical invariant: skip beats gate).
    if _source_exists(source_root):
        emit_json(
            "bootstrap",
            {
                "phase": 3,
                "track": "bootstrap",
                "outcome": "skipped",
                "reason": "source-exists",
                "source_root": str(source_root.resolve()),
            },
            ctx=ctx,
        )
        raise typer.Exit(0)

    # Step 3 — init guard.
    if not (root / _STATE_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    # Step 4 — Phase 2 gate (AC1).
    try:
        phase2_state = compute_state(phase=2, repo_root=root)
    except (SignoffError, Exception) as exc:
        cause = " | ".join(str(exc).splitlines())[:500]
        emit_error(
            "ERR_SIGNOFF_READ_FAILED",
            f"phase 2 signoff state could not be read: {cause}",
            ctx=ctx,
            details={"phase": 2, "cause": cause},
        )
    if phase2_state != SignoffState.APPROVED:
        emit_error(
            "ERR_PHASE2_NOT_APPROVED",
            f"phase 2 signoff must be APPROVED before Phase 3 bootstrap; "
            f"current state: {phase2_state.value}.",
            ctx=ctx,
            details={"phase2_state": str(phase2_state)},
        )

    # Step 5 — create directories (AC5).
    try:
        source_root.mkdir(parents=True, exist_ok=True)
        (root / "tests").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"failed to create project directories: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )

    # Step 6 — read and validate inputs (AC5).
    product_path = root / _PRODUCT_REL
    arch_path = root / _ARCH_REL
    if not product_path.is_file():
        emit_error("ERR_USER_INPUT", f"missing {_PRODUCT_REL}; run 'sdlc start' first", ctx=ctx)
    if not arch_path.is_file():
        emit_error(
            "ERR_USER_INPUT",
            f"missing {_ARCH_REL}; run 'sdlc architect' first",
            ctx=ctx,
        )
    try:
        product_text = product_path.read_text(encoding="utf-8-sig")
        arch_text = arch_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        emit_error("ERR_ARTIFACT_UNREADABLE", str(exc), ctx=ctx, details={"cause": str(exc)})
    if artifact_contains_boundary(product_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"{_PRODUCT_REL} contains the data-vs-instruction boundary marker",
            ctx=ctx,
        )
    if artifact_contains_boundary(arch_text):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"{_ARCH_REL} contains the data-vs-instruction boundary marker",
            ctx=ctx,
        )

    # Step 7 — load workflow spec + specialist registry + hook chain.
    workflows_dir = _workflows_package_dir()
    try:
        spec = WorkflowRegistry.load(workflows_dir).get(_SLASH_CMD)
    except (WorkflowError, Exception) as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"workflow load failed: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )

    agents_dir = root / _AGENTS_REL
    try:
        registry = load_registry(agents_dir)
    except (SpecialistError, OSError) as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"specialist registry load failed: {exc}",
            ctx=ctx,
            details={"agents_dir": str(agents_dir)},
        )

    hooks = build_pre_write_hook_chain(repo_root=root)

    def _prompt_builder(sp: Specialist, wf: WorkflowSpec) -> str:
        return phase1_compound_prompt_builder(
            sp,
            wf,
            primary_input=product_text,
            secondary_input=arch_text,
            primary_label="PRODUCT_BRIEF",
            secondary_label="SYSTEM_ARCHITECTURE",
            role="primary",
        )

    # Step 8 — dispatch + write (async core).
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            if use_mock_runtime():
                sp_obj = registry.get(_PRIMARY_SPECIALIST)
                if not isinstance(sp_obj, Specialist):
                    raise WorkflowError(
                        f"specialist {_PRIMARY_SPECIALIST!r} not found in registry",
                        details={"specialist": _PRIMARY_SPECIALIST},
                    )
                mock_prompt = _prompt_builder(sp_obj, spec)
                _write_mock_fixture(
                    tmp_path, spec.name, compute_prompt_hash(mock_prompt), _mock_bootstrap_body()
                )
            runtime = build_runtime(fixtures_dir=tmp_path)
        except (WorkflowError, SpecialistError, OSError) as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"mock materialization failed: {exc}",
                ctx=ctx,
                details={"cause": str(exc)},
            )

        try:
            files_written = asyncio.run(
                _bootstrap_dispatch_write(
                    spec=spec,
                    root=root,
                    journal_path=journal_path,
                    agent_runs_path=agent_runs_path,
                    source_root=source_root,
                    registry=registry,
                    hooks=hooks,
                    runtime=runtime,
                    prompt_builder=_prompt_builder,
                    allow_mock_invoked=allow_mock_invoked,
                )
            )
        except WorkflowError as exc:
            wf_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
            emit_error("ERR_BOOTSTRAP_DISPATCH_FAILED", str(exc), ctx=ctx, details=wf_details)
        except (KeyboardInterrupt, asyncio.CancelledError, typer.Exit):
            raise
        except OSError as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"bootstrap I/O failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )
        except Exception as exc:
            emit_error(
                "ERR_BOOTSTRAP_DISPATCH_FAILED",
                f"bootstrap pipeline failed: {exc}",
                ctx=ctx,
                details={"error": str(exc)},
            )

    # Step 12 — postconditions.
    try:
        evaluate_postconditions(
            spec,
            repo_root=root,
            agent_runs_path=agent_runs_path.resolve(),
            source_root_abs=source_root.resolve(),
        )
    except WorkflowError as exc:
        post_details = dict(exc.details) if isinstance(exc.details, Mapping) else {}
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition failed: {exc}",
            ctx=ctx,
            details=post_details,
        )
    except (RuntimeError, OSError) as exc:
        emit_error(
            "ERR_POSTCONDITION_FAILED",
            f"postcondition wiring incomplete: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )

    # Step 13 — emit success (AC1).
    source_root_rel = str(source_root.relative_to(root))
    emit_json(
        "bootstrap",
        {
            "phase": 3,
            "track": "bootstrap",
            "specialist": _PRIMARY_SPECIALIST,
            "files_written": files_written,
            "source_root": source_root_rel,
            "outcome": "success",
        },
        ctx=ctx,
    )
