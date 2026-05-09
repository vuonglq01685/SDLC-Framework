from __future__ import annotations

import sys

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — depends on state.atomic"),
]


def _write_journal_entries(journal_path, n: int) -> None:
    """Write n valid journal entries via append_sync."""
    import datetime

    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync

    def _ts() -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    for i in range(n):
        entry = JournalEntry(
            schema_version=1,
            monotonic_seq=i,
            ts=_ts(),
            actor="test",
            kind="state_mutation",
            target_id="state",
            before_hash=None,
            after_hash=f"sha256:{'a' * 64}",
            payload={"seq": i},
        )
        append_sync(entry, journal_path=journal_path)


def test_rebuild_state_from_journal_rejects_relative_journal_path(tmp_path):
    """AC1.3 sub-bullet 1: relative journal_path raises StateError(step=validate_journal_path)
    BEFORE any I/O. Use a true relative Path — `tmp_path / "relative"` would still be
    absolute (since `tmp_path` is absolute), which would trigger the missing-journal
    branch instead of the path-validation branch.
    """
    from pathlib import Path

    from sdlc.errors import StateError
    from sdlc.state.rebuild import rebuild_state_from_journal

    with pytest.raises(StateError) as exc_info:
        rebuild_state_from_journal(
            journal_path=Path("journal.log"),  # truly relative
            state_path=tmp_path / "state.json",
        )
    assert exc_info.value.details["step"] == "validate_journal_path"
    assert "absolute" in exc_info.value.message


def test_rebuild_state_from_journal_rejects_relative_state_path(tmp_path):
    from pathlib import Path

    from sdlc.errors import StateError
    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    journal_path.touch()

    with pytest.raises(StateError) as exc_info:
        rebuild_state_from_journal(
            journal_path=journal_path,
            state_path=Path("state.json"),
        )
    assert exc_info.value.details["step"] == "validate_state_path"
    assert "absolute" in exc_info.value.message


def test_rebuild_state_from_journal_refuses_when_journal_missing(tmp_path):
    from sdlc.errors import StateError
    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    state_path = tmp_path / "state.json"

    with pytest.raises(StateError) as exc_info:
        rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)

    err = exc_info.value
    assert err.details["reason"] == "missing_journal"
    assert "no journal at" in err.message
    assert str(journal_path) in err.message
    assert "recovery requires either journal or backup" in err.message


def test_rebuild_state_from_empty_journal_writes_default_state(tmp_path):
    import json

    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    journal_path.touch()
    state_path = tmp_path / "state.json"

    result = rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)

    assert result == 0
    assert state_path.exists()
    data = json.loads(state_path.read_bytes())
    assert data["schema_version"] == 1
    assert data["next_monotonic_seq"] == 0
    assert data["epics"] == {}


def test_rebuild_state_from_journal_with_3_entries_writes_correct_state(tmp_path):
    import json

    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    state_path = tmp_path / "state.json"
    _write_journal_entries(journal_path, 3)

    result = rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)

    assert result == 3
    assert state_path.exists()
    data = json.loads(state_path.read_bytes())
    assert data["schema_version"] == 1


def test_rebuild_state_byte_equivalent_to_full_replay(tmp_path):
    from sdlc.state import project_from_journal, write_state_atomic_sync
    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    _write_journal_entries(journal_path, 5)

    alt_path_a = tmp_path / "state_a.json"
    alt_path_b = tmp_path / "state_b.json"

    # Direct projection + write
    state_a = project_from_journal(journal_path)
    write_state_atomic_sync(state_a, alt_path_a)

    # Via rebuild
    rebuild_state_from_journal(journal_path=journal_path, state_path=alt_path_b)

    assert alt_path_a.read_bytes() == alt_path_b.read_bytes()


def test_rebuild_state_idempotent(tmp_path):
    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    state_path = tmp_path / "state.json"
    _write_journal_entries(journal_path, 4)

    rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)
    bytes_first = state_path.read_bytes()

    rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)
    bytes_second = state_path.read_bytes()

    assert bytes_first == bytes_second


def test_rebuild_state_propagates_journal_error_on_seq_regression(tmp_path):
    """JournalError(step="reader_invariant") propagates unchanged from project_from_journal.

    Avoids the writer's flock seq-monotonicity check by writing two entries with the same
    monotonic_seq directly through JournalEntry's public ``model_dump_json``. The reader's
    second-line-of-defence invariant must fire before any state is written.
    """
    import datetime
    import json

    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.errors import JournalError
    from sdlc.state.rebuild import rebuild_state_from_journal

    def _ts() -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    journal_path = tmp_path / "journal.log"
    state_path = tmp_path / "state.json"

    # Two entries with the SAME monotonic_seq (regression) — written via the entry's own
    # public JSON serializer rather than importing the journal package's `_canonical`
    # private helper. The reader accepts any well-formed JournalEntry JSON object per line.
    e0 = JournalEntry(
        schema_version=1,
        monotonic_seq=0,
        ts=_ts(),
        actor="test",
        kind="state_mutation",
        target_id="state",
        before_hash=None,
        after_hash=f"sha256:{'a' * 64}",
        payload={},
    )
    e1 = JournalEntry(
        schema_version=1,
        monotonic_seq=0,
        ts=_ts(),
        actor="test",
        kind="state_mutation",
        target_id="state",
        before_hash=None,
        after_hash=f"sha256:{'b' * 64}",
        payload={},
    )
    line0 = json.dumps(e0.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    line1 = json.dumps(e1.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    journal_path.write_text(line0 + "\n" + line1 + "\n", encoding="utf-8")

    with pytest.raises(JournalError) as exc_info:
        rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)
    assert exc_info.value.details["step"] == "reader_invariant"
    # The reader emits "lineno" (line number of the regression) — the dispatcher contract
    # depends on this exact key (see cli/rebuild_state.py::_dispatch_rebuild_error).
    assert "lineno" in exc_info.value.details


def test_rebuild_state_propagates_journal_error_on_schema_drift(tmp_path):
    """Verify JournalError(step='project_unknown_schema') propagates through rebuild.

    The reader's pydantic Literal[1] guard silently skips schema_version=2 lines
    (dual-defence model per projection.py §45-50). This test patches
    project_from_journal directly to simulate the error — testing the propagation
    contract without relying on the currently-unreachable reader path.
    """
    from unittest.mock import patch

    from sdlc.errors import JournalError
    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    journal_path.touch()
    state_path = tmp_path / "state.json"

    schema_drift_err = JournalError(
        "unknown schema_version=2 for kind=state_mutation; run sdlc migrate-v2",
        details={"step": "project_unknown_schema", "schema_version": 2},
    )

    with (
        patch("sdlc.state.rebuild.project_from_journal", side_effect=schema_drift_err),
        pytest.raises(JournalError) as exc_info,
    ):
        rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)

    assert exc_info.value.details["step"] == "project_unknown_schema"


def test_rebuild_state_overwrites_existing_state_json(tmp_path):
    import json

    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    state_path = tmp_path / "state.json"

    # Write a stale state.json
    stale = {"schema_version": 1, "next_monotonic_seq": 99, "epics": {}}
    state_path.write_text(
        json.dumps(stale, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    _write_journal_entries(journal_path, 1)
    rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)

    data = json.loads(state_path.read_bytes())
    assert data["next_monotonic_seq"] == 1  # rebuilt from journal (1 entry = seq becomes 1)


def test_rebuild_state_kill_safety_via_atomic_write(tmp_path):
    """AC7.1: tmp file is cleaned up; lock sentinel persists by design (Decision B2).

    The spec text says "assert state.json.lock is RELEASED (no leftover file)" but the
    atomic protocol's Decision B2 keeps the ``.lock`` file as a reusable flock sentinel
    after the rebuild releases the kernel lock. This test asserts both contracts:

      - the in-progress write buffer (``state.json.tmp``) is gone (kill-safety);
      - the flock is *released* (not held) — verified by acquiring it from a second
        process / file handle without blocking.

    The ``.lock`` file itself persists by design; that is recorded in ADR-023.
    """
    import fcntl

    from sdlc.state.rebuild import rebuild_state_from_journal

    journal_path = tmp_path / "journal.log"
    state_path = tmp_path / "state.json"
    journal_path.touch()

    rebuild_state_from_journal(journal_path=journal_path, state_path=state_path)

    # Kill-safety: the in-progress write buffer must be gone.
    assert not (tmp_path / "state.json.tmp").exists()
    assert state_path.exists()

    # Flock-released invariant: re-acquiring the lock must succeed without blocking.
    # If the rebuild forgot to release the flock, LOCK_NB would raise BlockingIOError.
    lock_path = tmp_path / "state.json.lock"
    if lock_path.exists():
        with lock_path.open("r+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
