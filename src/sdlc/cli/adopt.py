"""`sdlc init --adopt` (brownfield) CLI entry (Story 3.1, FR2, AC1/AC2).

Reuses the greenfield init scaffolding (`scaffold_canonical_layout`, `baseline_hook_trust`)
on a fresh adopt, then delegates to the `adopt/` three-pass driver. Fresh vs resume is
distinguished by the presence of canonical state (AC2): a re-run on an already-initialized
repo does NOT hard-refuse — it resumes from `adopt-report.json` per D3(a) pass-level resume.

Per Architecture §488, cross-module imports are deferred into the command body to keep the
cold-start budget under 200 ms.
"""

from __future__ import annotations

from pathlib import Path

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json

_JOURNAL_PATH_REL = ".claude/state/journal.log"


def _state_already_initialized(root: Path) -> bool:
    """Mirror init's re-init signal: state.json OR journal.log present (init.py:61-69)."""
    state_dir = root / ".claude" / "state"
    return (state_dir / "state.json").exists() or (state_dir / "journal.log").exists()


def _scaffold_if_fresh(root: Path, *, ctx: typer.Context) -> None:
    """Scaffold canonical state on a fresh adopt; no-op on resume (AC2 + D3(a))."""
    if _state_already_initialized(root):
        return
    from sdlc.cli.init import scaffold_canonical_layout  # deferred per Architecture §488

    scaffold_canonical_layout(root)

    from sdlc.cli._init_hook_baseline import baseline_hook_trust  # deferred

    try:
        baseline_hook_trust(root)
    except Exception as exc:
        # Surface a typed envelope for any baseline failure (mirrors init's DR4 posture).
        emit_error(
            "ERR_ADOPT",
            f"sdlc init --adopt: hook-trust baseline failed: {exc}",
            ctx=ctx,
            details={"project_root": str(root)},
        )


def run_adopt(*, ctx: typer.Context) -> None:
    """Adopt an existing repository (FR2): scaffold-if-fresh, then run the three passes."""
    from sdlc.errors import AdoptError, JournalError  # deferred

    root = _get_repo_root_or_cwd()
    journal_path = root / _JOURNAL_PATH_REL

    _scaffold_if_fresh(root, ctx=ctx)

    from sdlc.adopt import run_adopt as _run_adopt_driver  # deferred per boundary + §488

    try:
        report = _run_adopt_driver(root=root, journal_path=journal_path)
    except JournalError as exc:
        emit_error(
            "ERR_ADOPT",
            f"adopt journal append failed: {exc}",
            ctx=ctx,
            details={"path": str(journal_path)},
        )
    except AdoptError as exc:
        emit_error("ERR_ADOPT", exc.message, ctx=ctx, details=dict(exc.details))

    if ctx.obj is not None and ctx.obj.get("json", False):
        emit_json(
            "adopt",
            {
                "project_root": str(root),
                "passes_completed": list(report.passes_completed),
                "detected_count": len(report.detected),
            },
            ctx=ctx,
        )
        return
    echo(f"Adopted SDLC framework in {root}", ctx=ctx)
    echo(f"  passes completed: {list(report.passes_completed)}", ctx=ctx)
    echo(
        f"  detected artifacts: {len(report.detected)} (see .claude/state/adopt-report.json)",
        ctx=ctx,
    )
    echo("Next: sdlc status", ctx=ctx)
