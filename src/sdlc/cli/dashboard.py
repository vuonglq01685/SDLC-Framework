"""`sdlc dashboard` — local read-only dashboard server (Story 5.1, FR41)."""

from __future__ import annotations

import typer

_DEFAULT_PORT: int = 8765


def run_dashboard(*, ctx: typer.Context, port: int = _DEFAULT_PORT) -> None:
    """Start the localhost-only dashboard HTTP server."""
    del ctx  # reserved for future --json / --no-color parity
    from sdlc.cli._git_dora import git_dora_log
    from sdlc.cli._paths import get_repo_root_or_cwd
    from sdlc.dashboard.server import serve_dashboard

    repo_root = get_repo_root_or_cwd()
    typer.echo(f"serving on http://127.0.0.1:{port}")
    try:
        # D1: the git-log subprocess lives in `cli/` (this module) and is injected
        # into the dashboard server at construction — `dashboard/`/`telemetry/`
        # stay subprocess-free and `cli`-free (Story 5.13).
        serve_dashboard(
            repo_root=repo_root,
            port=port,
            git_log_provider=lambda: git_dora_log(repo_root),
        )
    except KeyboardInterrupt:
        typer.echo("dashboard stopped")
