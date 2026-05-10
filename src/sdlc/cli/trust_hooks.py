"""`sdlc trust-hooks` implementation (FR39, NFR-SEC-5, Architecture §806).

Records current hook file hashes into .claude/state/hook-hashes.json atomically,
journals a hooks_trusted entry, and updates state.json's next_monotonic_seq.
Advisory-only in v1 (PRD §374 + ADR-013); hard-block is v1.x scope.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import sys
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json

_logger = logging.getLogger(__name__)

_ACTOR: Final[str] = "cli"
_HOOKS_ROOT_REL: Final[str] = ".claude/hooks"
_STATE_ROOT_REL: Final[str] = ".claude/state"
_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"


def _now_rfc3339_utc() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write_state_to_disk(state: object, state_path: Path) -> None:
    if sys.platform == "win32":
        _logger.warning("trust-hooks on Windows uses non-atomic state write fallback")
        from sdlc.state import state_to_canonical_bytes  # type: ignore[attr-defined]

        state_path.write_bytes(state_to_canonical_bytes(state))  # type: ignore[arg-type]  # noqa: state-write -- Windows non-atomic fallback in trust_hooks
        return
    from sdlc.state import write_state_atomic_sync  # deferred POSIX-only

    write_state_atomic_sync(state, state_path)  # type: ignore[arg-type]


def _journal_and_advance_seq(
    *,
    hashes: dict[str, str],
    before_hash: str | None,
    after_hash: str,
    now: str,
    state_path: Path,
    journal_path: Path,
    ctx: typer.Context,
) -> None:
    """Append hooks_trusted journal entry and advance next_monotonic_seq (AC3)."""
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.errors import JournalError, StateError
    from sdlc.journal import append_sync
    from sdlc.state import read_state_or_recover

    try:
        state = read_state_or_recover(state_path.resolve(), journal_path.resolve())
    except StateError as exc:
        emit_error("ERR_STATE_MALFORMED", str(exc), ctx=ctx)

    seq = 0 if state is None else state.next_monotonic_seq
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

    if state is not None:
        new_state = state.model_copy(update={"next_monotonic_seq": seq + 1})
        try:
            _write_state_to_disk(new_state, state_path)
        except (OSError, StateError) as exc:
            emit_error("ERR_STATE_WRITE_FAILED", str(exc), ctx=ctx)


def run_trust_hooks(*, ctx: typer.Context) -> None:
    """Record current hook hashes and journal a hooks_trusted entry (FR39)."""
    from sdlc.errors import HookError
    from sdlc.hooks.tampering import compute_hook_hashes, record_trust

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

    now = _now_rfc3339_utc()

    try:
        hashes = compute_hook_hashes(hooks_root)
    except HookError as exc:
        emit_error("ERR_NOT_INITIALIZED", str(exc), ctx=ctx)

    before_hash = _sha256_file(store_path)

    try:
        record_trust(state_root.resolve(), hashes, now_utc=now)
    except HookError as exc:
        emit_error("ERR_INFRASTRUCTURE", str(exc), ctx=ctx)

    after_hash = _sha256_file(store_path)
    assert after_hash is not None, "hook-hashes.json must exist after record_trust"

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
