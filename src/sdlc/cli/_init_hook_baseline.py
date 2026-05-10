"""Three-phase fail-loud + transactional hook-trust baseline (DR4 + AC7).

Extracted from ``sdlc.cli.init`` to keep ``init.py`` under the 400-LOC cap
(NFR-MAINT-3 / Architecture §765). The orchestration logic itself is
intentionally explicit — a single linear ceremony with rollback — so the
audit trail (security-relevant Phase 1, idempotency Phase 2, atomicity Phase 3)
remains visible to reviewers.
"""

from __future__ import annotations

import contextlib
from pathlib import Path


def baseline_hook_trust(root: Path) -> None:  # noqa: PLR0915, C901  # DR4: explicit 3-phase ceremony
    """Compute hook hashes, write hook-hashes.json, and journal a hooks_trusted entry.

    Phase 1 — pre-validate (no side effects):
        compute hook hashes (escape attempts hard-fail; missing root → empty);
        read state (StateError → hard fail with rebuild-state hint).

    Phase 2 — refuse partial-init resume:
        if hook-hashes.json already exists, init must not silently overwrite —
        the user should run ``sdlc trust-hooks`` instead.

    Phase 3 — atomic commit with rollback:
        write store via the CLI helper; if journal append fails, delete the
        store and propagate. Final step advances ``next_monotonic_seq``.

    On Windows, ``write_hook_hashes_atomic`` raises ``HookError`` and init
    fails loudly — cross-platform support is deferred per Story 2A.5 DR1.
    """
    from sdlc.cli._fs import sha256_file_or_none
    from sdlc.cli._hook_trust_writer import write_hook_hashes_atomic
    from sdlc.cli._time import now_rfc3339_utc_ms
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.errors import HookError, JournalError, StateError
    from sdlc.hooks.tampering import compute_hook_hashes
    from sdlc.journal import append_sync
    from sdlc.journal._genesis import GENESIS_HASH
    from sdlc.state import read_state_or_recover, write_state_atomic_sync

    hooks_root = root / ".claude" / "hooks"
    state_root = root / ".claude" / "state"
    state_path = state_root / "state.json"
    journal_path = state_root / "journal.log"
    store_path = state_root / "hook-hashes.json"

    # ----- Phase 1: pre-validate hash collection -----
    try:
        hashes = compute_hook_hashes(hooks_root)
    except HookError as exc:
        if "escapes hooks_root" in str(exc):
            # SECURITY: never silently bless a symlink-escape attempt as "trusted."
            raise HookError(
                f"sdlc init refusing to baseline hook trust: {exc}. "
                f"Inspect .claude/hooks/ contents and remove any escaping symlinks.",
                details={"step": "init_baseline", "phase": "pre_validate"},
            ) from exc
        step_path = exc.details.get("path", "")
        if step_path == str(hooks_root) and "not found" in str(exc):
            hashes = {}  # benign: hooks tree absent on first init
        else:
            raise

    # ----- Phase 1b: pre-validate state read -----
    try:
        state = read_state_or_recover(state_path.resolve(), journal_path.resolve())
    except StateError as exc:
        raise StateError(
            f"sdlc init: cannot baseline hook trust — state.json corrupted: {exc}. "
            f"Run 'sdlc rebuild-state' first.",
            details={"step": "init_baseline", "phase": "read_state"},
        ) from exc

    if state is None:
        from sdlc.state import State  # deferred

        state = State()

    # ----- Phase 2: refuse partial-init resume -----
    if store_path.exists():
        raise HookError(
            f"sdlc init: hook-hashes.json already exists at {store_path}. "
            f"This indicates a prior init crashed mid-baseline. "
            f"Run 'sdlc trust-hooks' to re-baseline an existing workspace.",
            details={"step": "init_baseline", "phase": "refuse_partial"},
        )

    # ----- Phase 3: atomic commit with rollback -----
    now = now_rfc3339_utc_ms()
    before_hash = GENESIS_HASH  # DR5: genesis entry for hook-hashes target

    write_hook_hashes_atomic(state_root, hashes, now_utc=now)

    after_hash = sha256_file_or_none(store_path)
    if after_hash is None:  # pragma: no cover — should not happen post-write
        raise HookError(
            f"sdlc init: hook-hashes.json missing after atomic write at {store_path}",
            details={"step": "init_baseline", "phase": "post_write_check"},
        )

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=state.next_monotonic_seq,
        ts=now,
        actor="cli",
        kind="hooks_trusted",
        target_id="hook-hashes",
        before_hash=before_hash,
        after_hash=after_hash,
        payload={"files": sorted(hashes.keys()), "via": "sdlc init"},
    )

    try:
        append_sync(entry, journal_path=journal_path.resolve())
    except (JournalError, OSError) as exc:
        with contextlib.suppress(OSError):
            store_path.unlink(missing_ok=True)
        raise HookError(
            f"sdlc init: journal append failed during hook-trust baseline: {exc}."
            f" Partial hook-hashes.json removed; safe to retry 'sdlc init'.",
            details={"step": "init_baseline", "phase": "journal_append"},
        ) from exc

    new_state = state.model_copy(update={"next_monotonic_seq": state.next_monotonic_seq + 1})
    try:
        write_state_atomic_sync(new_state, state_path.resolve())
    except (OSError, StateError) as exc:
        with contextlib.suppress(OSError):
            store_path.unlink(missing_ok=True)
        raise StateError(
            f"sdlc init: state.json advance failed after hook-trust baseline: {exc}."
            f" Hook-hashes.json removed; run 'sdlc rebuild-state' to recover.",
            details={"step": "init_baseline", "phase": "advance_seq"},
        ) from exc


__all__ = ["baseline_hook_trust"]
