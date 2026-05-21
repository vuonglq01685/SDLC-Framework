"""Error-path coverage for ``sdlc.cli._init_hook_baseline.baseline_hook_trust``.

The three-phase ceremony at the heart of ``sdlc init`` has tightly-scoped
failure modes (symlink-escape, state corruption, partial-init resume, journal
append failure, state advance failure). The happy path is exercised by
``test_init.py``; this file targets the rollback and re-raise branches so
prep-sprint C3 can restore the 90% coverage gate (EPIC-2A-D3).
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest

from sdlc.cli._init_hook_baseline import baseline_hook_trust
from sdlc.errors import HookError, JournalError, StateError

pytestmark = pytest.mark.unit

_POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only — symlink and atomic-write semantics require Linux/macOS",
)


def _prepare_root(tmp_path: Path) -> Path:
    """Lay down ``.claude/{hooks,state}`` so baseline_hook_trust can run."""
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Phase 1: pre-validate hash collection
# ---------------------------------------------------------------------------


@_POSIX_ONLY
def test_baseline_refuses_symlink_escape(tmp_path: Path) -> None:
    """Symlink whose target escapes ``hooks_root`` must hard-fail with a
    descriptive HookError — never silently bless an escaping symlink as trusted."""
    root = _prepare_root(tmp_path)
    hooks_root = root / ".claude" / "hooks"
    # compute_hook_hashes only scans *.py files; the symlink target also needs
    # to be a real file (resolve(strict=True) at line 81 of tampering.py).
    outside_target = tmp_path / "evil.py"
    outside_target.write_text("print('pwned')\n")
    (hooks_root / "escape.py").symlink_to(outside_target)

    with pytest.raises(HookError) as exc:
        baseline_hook_trust(root)
    assert "refusing to baseline" in str(exc.value)
    assert exc.value.details.get("phase") == "pre_validate"
    assert exc.value.details.get("step") == "init_baseline"


def test_baseline_treats_missing_hooks_tree_as_empty(tmp_path: Path) -> None:
    """A workspace with no ``.claude/hooks/`` directory must produce an empty
    hash set, not a hard failure — first-init has no hooks tree yet."""
    state_root = tmp_path / ".claude" / "state"
    state_root.mkdir(parents=True)
    # Intentionally do not create .claude/hooks/

    baseline_hook_trust(tmp_path)

    # Empty hash store is still committed + journaled.
    store = state_root / "hook-hashes.json"
    assert store.exists()
    payload = json.loads(store.read_text())
    assert payload["hashes"] == {}


def test_baseline_propagates_unrelated_hook_error(tmp_path: Path) -> None:
    """HookError that is neither an escape nor a missing-tree must propagate
    as-is rather than be reshaped into the init-specific wrapper."""
    root = _prepare_root(tmp_path)
    boom = HookError("disk failure", details={"path": "/somewhere/else", "step": "compute"})

    with (
        unittest.mock.patch("sdlc.hooks.tampering.compute_hook_hashes", side_effect=boom),
        pytest.raises(HookError) as exc,
    ):
        baseline_hook_trust(root)
    assert exc.value is boom  # exact same object — no rewrap


# ---------------------------------------------------------------------------
# Phase 1b: pre-validate state read
# ---------------------------------------------------------------------------


def test_baseline_wraps_state_corruption_with_rebuild_hint(tmp_path: Path) -> None:
    """StateError from ``read_state_or_recover`` must be re-raised with an
    actionable rebuild-state hint, preserving the original cause via ``from``."""
    root = _prepare_root(tmp_path)
    cause = StateError("state.json is malformed JSON", details={"step": "read_state"})

    with (
        unittest.mock.patch("sdlc.state.read_state_or_recover", side_effect=cause),
        pytest.raises(StateError) as exc,
    ):
        baseline_hook_trust(root)
    assert "rebuild-state" in str(exc.value)
    assert exc.value.details.get("phase") == "read_state"
    assert exc.value.__cause__ is cause


def test_baseline_handles_state_none_as_fresh_state(tmp_path: Path) -> None:
    """When ``read_state_or_recover`` returns ``None`` (no prior state, no
    recoverable journal) the function must synthesise a fresh ``State()`` and
    proceed — first-init has no state.json yet."""
    root = _prepare_root(tmp_path)

    with unittest.mock.patch("sdlc.state.read_state_or_recover", return_value=None):
        baseline_hook_trust(root)

    state_payload = json.loads((root / ".claude" / "state" / "state.json").read_text())
    # baseline advances next_monotonic_seq exactly once (genesis → 1).
    assert state_payload["next_monotonic_seq"] == 1


# ---------------------------------------------------------------------------
# Phase 2: refuse partial-init resume
# ---------------------------------------------------------------------------


def test_baseline_refuses_when_hook_hashes_already_exists(tmp_path: Path) -> None:
    """If hook-hashes.json is already on disk, init must refuse to overwrite
    and direct the user to ``sdlc trust-hooks`` instead."""
    root = _prepare_root(tmp_path)
    store = root / ".claude" / "state" / "hook-hashes.json"
    store.write_text('{"hashes": {}, "computed_at": "2026-05-21T00:00:00.000Z"}')

    with pytest.raises(HookError) as exc:
        baseline_hook_trust(root)
    assert "hook-hashes.json already exists" in str(exc.value)
    assert "sdlc trust-hooks" in str(exc.value)
    assert exc.value.details.get("phase") == "refuse_partial"


# ---------------------------------------------------------------------------
# Phase 3: atomic commit with rollback
# ---------------------------------------------------------------------------


def test_baseline_rolls_back_store_on_journal_append_failure(tmp_path: Path) -> None:
    """A JournalError at append time must delete the just-written
    hook-hashes.json so the workspace is safe to retry ``sdlc init`` against."""
    root = _prepare_root(tmp_path)
    store_path = root / ".claude" / "state" / "hook-hashes.json"
    boom = JournalError("EIO during append", details={"errno": 5, "step": "write_journal"})

    with (
        unittest.mock.patch("sdlc.journal.append_sync", side_effect=boom),
        pytest.raises(HookError) as exc,
    ):
        baseline_hook_trust(root)

    assert not store_path.exists(), "rollback must delete the just-written store"
    assert "journal append failed" in str(exc.value)
    assert exc.value.details.get("phase") == "journal_append"
    assert exc.value.__cause__ is boom


def test_baseline_rolls_back_store_on_state_advance_failure(tmp_path: Path) -> None:
    """A StateError at state-advance time must also delete the store so the
    user can recover with ``sdlc rebuild-state``."""
    root = _prepare_root(tmp_path)
    store_path = root / ".claude" / "state" / "hook-hashes.json"
    boom = StateError("EIO during atomic rename", details={"errno": 5})

    with (
        unittest.mock.patch("sdlc.state.write_state_atomic_sync", side_effect=boom),
        pytest.raises(StateError) as exc,
    ):
        baseline_hook_trust(root)

    assert not store_path.exists(), "rollback must delete the store on state advance failure"
    assert "rebuild-state" in str(exc.value)
    assert exc.value.details.get("phase") == "advance_seq"
    assert exc.value.__cause__ is boom
