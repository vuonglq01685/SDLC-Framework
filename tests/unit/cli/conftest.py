"""Shared fixtures and helpers for tests/unit/cli/ (Story 1.18.1 B-P19).

Centralises _make_ctx, _make_entry, _bootstrap_project, _append_entry so that
a future JournalEntry schema change only requires updating one file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer

from sdlc.contracts.journal_entry import JournalEntry

# ---------------------------------------------------------------------------
# Exit-code constants (B-P11) — import these instead of bare literals
# ---------------------------------------------------------------------------
EXIT_USER_ERROR: int = 1
EXIT_SYSTEM_ERROR: int = 2


# ---------------------------------------------------------------------------
# Context factory
# ---------------------------------------------------------------------------


def make_ctx(*, no_color: bool = False, json_mode: bool = False) -> typer.Context:
    """Build a minimal Typer context for unit tests."""
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json"] = json_mode
    return ctx


# ---------------------------------------------------------------------------
# JournalEntry factory
# ---------------------------------------------------------------------------


def make_entry(
    seq: int,
    ts: str,
    *,
    target_id: str = "state",
    actor: str = "cli",
    kind: str = "scan_completed",
    payload: dict[str, Any] | None = None,
) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=actor,
        kind=kind,
        target_id=target_id,
        before_hash=None if seq == 0 else "sha256:" + "0" * 64,
        after_hash="sha256:" + "1" * 64,
        payload=payload or {},
    )


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def bootstrap_project(tmp_path: Path) -> Path:
    """Create the minimal initialised project structure; return journal path."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{}")
    journal = state_dir / "journal.log"
    journal.touch()
    return journal


def append_entry(journal: Path, entry: JournalEntry) -> None:
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


# ---------------------------------------------------------------------------
# pytest fixtures — tests may import helpers directly OR use fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_ctx() -> typer.Context:
    return make_ctx()


@pytest.fixture()
def cli_ctx_json() -> typer.Context:
    return make_ctx(json_mode=True)
