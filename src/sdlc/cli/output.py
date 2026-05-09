"""CLI output helpers (Story 1.16 minimal stub; Story 1.17 expands with
--no-color / --json envelope handling)."""

from __future__ import annotations

import typer

__all__ = ("echo",)


def echo(message: str, *, err: bool = False) -> None:
    """Emit ``message`` on stdout (or stderr if ``err=True``).

    Wraps ``typer.echo`` so Story 1.17 can centralize ``--no-color`` /
    ``--json`` plumbing in one place. v1.16 forwards verbatim.
    """
    typer.echo(message, err=err)
