"""`sdlc dashboard` — local read-only dashboard server (Story 5.1, FR41)."""

from __future__ import annotations

import typer

_DEFAULT_PORT: int = 8765


def run_dashboard(*, ctx: typer.Context, port: int = _DEFAULT_PORT) -> None:
    """Start the localhost-only dashboard HTTP server."""
    del ctx  # reserved for future --json / --no-color parity
    from sdlc.cli._paths import get_repo_root_or_cwd
    from sdlc.dashboard.server import serve_dashboard

    repo_root = get_repo_root_or_cwd()
    typer.echo(f"serving on http://127.0.0.1:{port}")
    try:
        serve_dashboard(repo_root=repo_root, port=port)
    except KeyboardInterrupt:
        typer.echo("dashboard stopped")
