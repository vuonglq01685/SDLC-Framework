"""`sdlc trust-hooks` implementation (FR39, NFR-SEC-5, Architecture §806).

Records current hook file hashes into ``.claude/state/hook-hashes.json`` atomically,
journals a ``hooks_trusted`` entry, and advances state.json's ``next_monotonic_seq``.
The whole read-modify-write sequence is serialized under a flock on state.json
to prevent the parallel-invocation race (P9, code review 2026-05-10).

Advisory-only in v1 (PRD §374 + ADR-013); hard-block is v1.x scope.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._fs import sha256_file_or_none
from sdlc.cli._hook_trust_writer import write_hook_hashes_atomic
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import echo, emit_error, emit_json

_logger = logging.getLogger(__name__)

_ACTOR: Final[str] = "cli"
_HOOKS_ROOT_REL: Final[str] = ".claude/hooks"
_STATE_ROOT_REL: Final[str] = ".claude/state"
_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_TRUST_LOCK_REL: Final[str] = ".claude/state/.trust-hooks.lock"


def _journal_and_advance_seq(
    *,
    hashes: dict[str, str],
    before_hash: str,
    after_hash: str,
    now: str,
    state_path: Path,
    journal_path: Path,
    ctx: typer.Context,
) -> None:
    """Append ``hooks_trusted`` journal entry and advance ``next_monotonic_seq`` (AC3).

    Caller MUST hold the trust-hooks flock; this function does NOT acquire it.
    """
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.errors import JournalError, StateError
    from sdlc.journal import append_sync
    from sdlc.state import read_state_or_recover, write_state_atomic_sync

    try:
        state = read_state_or_recover(state_path.resolve(), journal_path.resolve())
    except StateError as exc:
        emit_error("ERR_STATE_MALFORMED", str(exc), ctx=ctx)

    if state is None:
        # workspace must be initialized for trust-hooks to journal — caller
        # already validated `.claude/` exists, so a missing state.json here
        # means partial init. Refuse rather than silently start a chain
        # at seq=0 that diverges from any future state.json restore.
        emit_error(
            "ERR_NOT_INITIALIZED",
            "state.json missing; workspace partially initialized. "
            "Run 'sdlc rebuild-state' or re-run 'sdlc init'.",
            ctx=ctx,
        )

    seq = state.next_monotonic_seq
    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=now,
        actor=_ACTOR,
        kind="hooks_trusted",
        target_id="hook-hashes",
        before_hash=before_hash,
        after_hash=after_hash,
        payload={"files": sorted(hashes.keys())},
    )
    try:
        append_sync(entry, journal_path=journal_path.resolve())
    except JournalError as exc:
        emit_error("ERR_JOURNAL_APPEND_FAILED", str(exc), ctx=ctx)

    new_state = state.model_copy(update={"next_monotonic_seq": seq + 1})
    try:
        write_state_atomic_sync(new_state, state_path.resolve())
    except (OSError, StateError) as exc:
        emit_error("ERR_STATE_WRITE_FAILED", str(exc), ctx=ctx)


def run_trust_hooks(*, ctx: typer.Context) -> None:
    """Record current hook hashes and journal a ``hooks_trusted`` entry (FR39).

    P9: serialized under a flock on ``.claude/state/.trust-hooks.lock`` so
    two parallel invocations cannot race-write the same ``monotonic_seq``.
    """
    from sdlc.concurrency import file_lock
    from sdlc.errors import HookError
    from sdlc.hooks import compute_hook_hashes
    from sdlc.journal._genesis import GENESIS_HASH

    root = _get_repo_root_or_cwd()
    claude_dir = root / ".claude"

    if not claude_dir.exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            "not an sdlc workspace; run 'sdlc init' first",
            ctx=ctx,
        )

    hooks_root = root / _HOOKS_ROOT_REL
    state_root = root / _STATE_ROOT_REL
    state_path = root / _STATE_PATH_REL
    journal_path = root / _JOURNAL_PATH_REL
    store_path = state_root / "hook-hashes.json"
    lock_path = root / _TRUST_LOCK_REL

    now = now_rfc3339_utc_ms()

    try:
        hashes = compute_hook_hashes(hooks_root)
    except HookError as exc:
        emit_error("ERR_NOT_INITIALIZED", str(exc), ctx=ctx)

    # Acquire RMW lock — serializes journal-seq advance against parallel
    # `sdlc trust-hooks` and `sdlc scan` invocations writing to state.json.
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(lock_path):
        # P28/DR5: GENESIS_HASH for the first trust event in this target_id chain.
        before_hash = sha256_file_or_none(store_path) or GENESIS_HASH

        try:
            write_hook_hashes_atomic(state_root, hashes, now_utc=now)
        except HookError as exc:
            emit_error("ERR_INFRASTRUCTURE", str(exc), ctx=ctx)

        after_hash = sha256_file_or_none(store_path)
        if after_hash is None:  # pragma: no cover — should not happen post-write
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"hook-hashes.json missing after atomic write at {store_path}",
                ctx=ctx,
            )

        _journal_and_advance_seq(
            hashes=hashes,
            before_hash=before_hash,
            after_hash=after_hash,
            now=now,
            state_path=state_path,
            journal_path=journal_path,
            ctx=ctx,
        )

    n = len(hashes)
    json_mode = ctx.obj is not None and ctx.obj.get("json", False)
    if json_mode:
        emit_json(
            "trust-hooks",
            {
                "project_root": str(root),
                "files": sorted(hashes.keys()),
                "file_count": n,
                "trusted_at": now,
            },
            ctx=ctx,
        )
    else:
        echo(f"[OK] hook hashes recorded: {n} file(s) at {now}", ctx=ctx)
