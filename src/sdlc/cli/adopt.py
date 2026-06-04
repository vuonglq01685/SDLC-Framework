"""`sdlc init --adopt` (brownfield) CLI entry (Story 3.1 + 3.3, FR2, AC1/AC2).

Reuses the greenfield init scaffolding (`scaffold_canonical_layout`, `baseline_hook_trust`)
on a fresh adopt, then delegates to the `adopt/` three-pass driver. Fresh vs resume is
distinguished by the presence of canonical state (AC2): a re-run on an already-initialized
repo does NOT hard-refuse — it resumes from `adopt-report.json` per D3(a) pass-level resume.

Story 3.3 (Pass 2): this layer holds the TTY + config grants, so it resolves the interactivity
mode + the auto-accept threshold and builds the `[Y/n/edit]` confirm-callback + the warning
sink, injecting all three into the boundary-respecting `adopt/` core (which must not import
`cli/` or `print`). `--json` ⇒ non-interactive (prompts would corrupt the machine channel).

Per Architecture §488, cross-module imports are deferred into the command body to keep the
cold-start budget under 200 ms.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json

if TYPE_CHECKING:
    from sdlc.adopt.passes.symlink_offer import ConfirmCallback, SymlinkDecision
    from sdlc.config.project import ProjectConfig
    from sdlc.contracts.adopt_report import DetectedArtifact

_JOURNAL_PATH_REL = ".claude/state/journal.log"
# AC5 (epics.md:1809, verbatim): greenfield-disguised brownfield → no candidates message.
_GREENFIELD_MESSAGE = "no candidate artifacts detected; will treat as greenfield"


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


def _load_project_config(root: Path, *, ctx: typer.Context) -> ProjectConfig:
    """Read `project.yaml` once for both the D4 `legacy_code_globs` and the D1 threshold (3.3).

    Mirrors Story 3.8's read (`cli/break_.py:224`). A brownfield repo being adopted usually has
    no `project.yaml` → `load_project_config` returns defaults. A malformed / unreadable file
    surfaces a typed envelope rather than silently dropping the config (closes CR3.2-W3: the
    prior reader caught only `ConfigError`, so a permission-denied / non-UTF8 `project.yaml`
    escaped uncaught — now `OSError`/`UnicodeDecodeError` are surfaced too).
    """
    from collections.abc import Mapping  # deferred per §488

    from sdlc.config.project import DEFAULT_PROJECT_YAML, load_project_config
    from sdlc.errors import ConfigError

    try:
        return load_project_config(root / DEFAULT_PROJECT_YAML)
    except ConfigError as exc:
        # emit_error raises typer.Exit (NoReturn) — surfaces a typed envelope, never falls through.
        emit_error(
            "ERR_USER_INPUT",
            f"project.yaml could not be read: {exc}",
            ctx=ctx,
            details=dict(exc.details) if isinstance(exc.details, Mapping) else {"cause": str(exc)},
        )
    except (OSError, UnicodeDecodeError) as exc:
        emit_error(
            "ERR_USER_INPUT",
            f"project.yaml could not be read: {exc}",
            ctx=ctx,
            details={"path": str(root / DEFAULT_PROJECT_YAML), "cause": str(exc)},
        )


def _is_safe_relative_target(root: Path, target: str) -> bool:
    """True if ``target`` is a relative path that stays under ``root`` (D3 edit validation).

    Delegates to the single shared `adopt/` predicate so this cli edit guard and the core
    re-validation in `offer_symlinks` cannot drift (code-review P2).
    """
    from sdlc.adopt.passes._symlink import is_target_under_root  # deferred per §488

    return is_target_under_root(root, target)


def _build_confirm_callback(root: Path, *, ctx: typer.Context) -> ConfirmCallback:
    """Build the interactive `[Y/n/edit]` prompt callback injected into Pass 2 (AC1, D3).

    Renders `confidence` as an INTEGER (never a float — the frozen contract is int-percent).
    `edit` re-prompts for a relative target validated under the project root, then re-offers
    `[Y/n]`; an invalid edit is reported and treated as a skip.
    """
    from sdlc.adopt.passes.symlink_offer import SymlinkDecision

    def confirm(artifact: DetectedArtifact, suggested_target: str) -> SymlinkDecision:
        prompt = (
            f"Found {artifact.path} ({artifact.kind}, confidence {artifact.confidence}). "
            f"Symlink to {suggested_target}? [Y/n/edit]"
        )
        answer = typer.prompt(prompt, default="Y", show_default=False).strip().lower()
        if answer in ("", "y", "yes"):
            return SymlinkDecision(accept=True, target=suggested_target)
        if answer in ("e", "edit"):
            new_target = typer.prompt("  New target path (relative to project root)").strip()
            if not _is_safe_relative_target(root, new_target):
                echo(
                    f"  invalid target {new_target!r}; skipping {artifact.path}", err=True, ctx=ctx
                )
                return SymlinkDecision(accept=False, target=suggested_target)
            if typer.confirm(f"  Symlink to {new_target}?", default=True):
                return SymlinkDecision(accept=True, target=new_target)
            return SymlinkDecision(accept=False, target=new_target)
        # `n`/`no` or anything unrecognized → skip (safe default).
        return SymlinkDecision(accept=False, target=suggested_target)

    return confirm


def run_adopt(*, ctx: typer.Context, non_interactive: bool = False) -> None:
    """Adopt an existing repository (FR2): scaffold-if-fresh, then run the three passes.

    Story 3.3: `non_interactive` (the `--non-interactive` flag), `--json`, or a non-TTY stdin
    force auto-accept mode (no prompts); otherwise the `[Y/n/edit]` confirm-callback is built
    and injected. The auto-accept threshold + legacy globs come from a single `project.yaml` read.
    """
    from sdlc.errors import AdoptError, JournalError  # deferred

    root = _get_repo_root_or_cwd()
    journal_path = root / _JOURNAL_PATH_REL

    _scaffold_if_fresh(root, ctx=ctx)

    # Story 3.2 D2/D4 + 3.3 D1: compute the recency signal + read project config (legacy globs +
    # auto-accept threshold) in the cli layer (which holds the git + config grants).
    from sdlc.cli._git_recency import git_last_touched_days  # deferred per boundary + §488

    git_signal = git_last_touched_days(root)
    config = _load_project_config(root, ctx=ctx)

    # Story 3.3 AC1/AC3/AC7: resolve interactivity in the cli layer and inject the confirm + warn
    # callbacks. --json ⇒ non-interactive (prompts would corrupt the machine-readable channel).
    json_mode = bool(ctx.obj is not None and ctx.obj.get("json", False))
    interactive = sys.stdin.isatty() and not json_mode and not non_interactive
    confirm = _build_confirm_callback(root, ctx=ctx) if interactive else None

    def _warn(message: str) -> None:
        echo(f"  {message}", err=True, ctx=ctx)

    from sdlc.adopt import run_adopt as _run_adopt_driver  # deferred per boundary + §488

    try:
        report = _run_adopt_driver(
            root=root,
            journal_path=journal_path,
            git_signal=git_signal,
            legacy_code_globs=config.legacy_code_globs,
            confirm=confirm,
            auto_accept_threshold=config.auto_accept_threshold,
            warn=_warn,
        )
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
    # AC5: greenfield-disguised repo → emit the verbatim no-candidates message.
    if not report.detected:
        echo(f"  {_GREENFIELD_MESSAGE}", ctx=ctx)
    else:
        echo(
            f"  detected artifacts: {len(report.detected)} (see .claude/state/adopt-report.json)",
            ctx=ctx,
        )
    echo("Next: sdlc status", ctx=ctx)
