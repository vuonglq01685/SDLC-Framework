"""Integration tests for sdlc rebuild-state end-to-end (Story 1.20, FR35).

Tests run `sdlc` via subprocess (uv run sdlc ...) to exercise the full CLI path
including deferred imports, error dispatch, and journal/state interaction.

Test names follow AC7.7 spec:
  - test_full_rebuild_lifecycle (AC7.7.1)
  - test_no_recovery_source_e2e (AC7.7.4)
  - test_refusal_message_on_malformed_state_for_status_command (AC7.7.2)
  - test_refusal_message_on_schema_mismatch_for_status_command (AC7.7.3)
  - test_rebuild_state_does_not_mutate_journal (AC7.7.5)
  - test_rebuild_twice_produces_byte_identical_state (AC7.7 + Task 14 — idempotency)
  - test_rebuild_state_json_mode_success_envelope (AC7.7 — JSON success)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_SKIP_NO_UV = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv not on PATH — skipping subprocess e2e test",
)

_VALID_V1_STATE: dict[str, object] = {
    "schema_version": 1,
    "next_monotonic_seq": 1,
    "epics": {},
    "stories": {},
    "tasks": {},
    "phase": 1,
}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_sdlc(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--project", str(_PROJECT_ROOT), "sdlc", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _bootstrap_initialized(project_root: Path) -> Path:
    """Create .claude/state/ with a valid state.json and a journal.log."""
    state_dir = project_root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"
    state_path.write_text(json.dumps(_VALID_V1_STATE), encoding="utf-8")
    (state_dir / "journal.log").touch()
    return state_path


def _write_journal_entries(project_root: Path, n: int) -> None:
    """Append N synthetic journal entries so rebuild has something to replay."""
    import datetime

    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync

    journal_path = project_root / ".claude" / "state" / "journal.log"

    def _ts() -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    for i in range(n):
        entry = JournalEntry(
            schema_version=1,
            monotonic_seq=i,
            ts=_ts(),
            actor="integration-test",
            kind="state_mutation",
            target_id="state",
            before_hash=None,
            after_hash=f"sha256:{'a' * 64}",
            payload={"seq": i},
        )
        append_sync(entry, journal_path=journal_path)


# ---------------------------------------------------------------------------
# AC7.7.1 — rebuild-state reconstructs state.json from journal after deletion
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_full_rebuild_lifecycle(tmp_path: Path) -> None:
    """After deleting state.json, sdlc rebuild-state recreates it from the journal.

    Also asserts the atomic-protocol kill-safety invariant: state.json.tmp is gone
    after a successful rebuild (no leftover write buffer).
    """
    state_path = _bootstrap_initialized(tmp_path)
    _write_journal_entries(tmp_path, 3)
    state_path.unlink()

    result = _run_sdlc(["rebuild-state"], tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert state_path.exists(), "state.json was not recreated"
    assert "state rebuilt from 3 journal entries" in result.stdout
    # Atomic-protocol invariant: no leftover write buffer.
    assert not (tmp_path / ".claude" / "state" / "state.json.tmp").exists(), (
        "state.json.tmp leaked after successful rebuild"
    )


# ---------------------------------------------------------------------------
# AC7.7.4 — rebuild-state refuses when no journal exists (ERR_NO_RECOVERY_SOURCE)
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_no_recovery_source_e2e(tmp_path: Path) -> None:
    """When no journal.log exists, sdlc rebuild-state must exit non-zero and mention recovery."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    # state.json present but no journal.log

    result = _run_sdlc(["rebuild-state"], tmp_path)

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "journal" in combined.lower() or "recovery" in combined.lower(), (
        f"Expected recovery hint in output.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC7.7.2 — recovery prompt is the unified message on `sdlc status` over malformed state
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_refusal_message_on_malformed_state_for_status_command(tmp_path: Path) -> None:
    """Bootstrap; overwrite state.json with not-json; sdlc status surfaces the recovery prompt."""
    state_path = _bootstrap_initialized(tmp_path)
    _write_journal_entries(tmp_path, 2)
    state_path.write_text("this is not valid json {{{", encoding="utf-8")

    result = _run_sdlc(["status"], tmp_path)

    assert result.returncode == 2, (
        f"expected exit 2 (ERR_STATE_MALFORMED); got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    stderr = result.stderr
    assert "state.json is malformed at" in stderr, (
        f"missing recovery-prompt prefix; stderr:\n{stderr}"
    )
    assert "sdlc rebuild-state" in stderr
    assert "sdlc migrate-vN" in stderr
    assert "is untouched" in stderr


# ---------------------------------------------------------------------------
# AC7.7.3 — recovery prompt + inner schema-mismatch wording on `sdlc status`
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_refusal_message_on_schema_mismatch_for_status_command(tmp_path: Path) -> None:
    """Bootstrap; overwrite state.json with schema_version=2; sdlc status surfaces both
    the unified recovery prompt AND the Story 1.19 inner schema-mismatch message."""
    state_path = _bootstrap_initialized(tmp_path)
    _write_journal_entries(tmp_path, 1)
    state_path.write_text(
        json.dumps({"schema_version": 2, "next_monotonic_seq": 0, "epics": {}}),
        encoding="utf-8",
    )

    result = _run_sdlc(["status"], tmp_path)

    assert result.returncode == 2, (
        f"expected exit 2; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    stderr = result.stderr
    # Outer recovery prompt
    assert "state.json is malformed at" in stderr
    assert "sdlc rebuild-state" in stderr
    assert "is untouched" in stderr
    # Inner Story 1.19 schema-mismatch wording — surfaced via details["inner_message"]
    # in JSON mode, or appended to the human-mode envelope. We accept either by
    # asserting the JSON envelope explicitly with --json.
    json_result = _run_sdlc(["--json", "status"], tmp_path)
    assert json_result.returncode == 2
    payload = json.loads(json_result.stderr)
    inner = payload["error"]["details"].get("inner_message", "")
    assert "schema_version mismatch" in inner, (
        f"inner_message missing schema-mismatch wording; got: {inner!r}"
    )
    assert "state is v2" in inner
    assert "framework expects v1" in inner


# ---------------------------------------------------------------------------
# AC7.7 — sdlc rebuild-state --json emits well-formed JSON success envelope
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_rebuild_state_json_mode_success_envelope(tmp_path: Path) -> None:
    """sdlc --json rebuild-state must emit a JSON success envelope on stdout."""
    _bootstrap_initialized(tmp_path)
    _write_journal_entries(tmp_path, 2)
    (tmp_path / ".claude" / "state" / "state.json").unlink()

    result = _run_sdlc(["--json", "rebuild-state"], tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    payload = json.loads(result.stdout)
    assert payload.get("result") == "success"
    assert isinstance(payload.get("entries_replayed"), int)
    assert payload.get("entries_replayed") == 2


# ---------------------------------------------------------------------------
# AC7.7.5 — journal is untouched after rebuild
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_rebuild_state_does_not_mutate_journal(tmp_path: Path) -> None:
    """sdlc rebuild-state must not write to or truncate journal.log."""
    _bootstrap_initialized(tmp_path)
    _write_journal_entries(tmp_path, 4)
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_bytes_before = journal_path.read_bytes()
    (tmp_path / ".claude" / "state" / "state.json").unlink()

    result = _run_sdlc(["rebuild-state"], tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert journal_path.read_bytes() == journal_bytes_before, "journal.log was mutated"


# ---------------------------------------------------------------------------
# Task 14 — manual-verify checklist: rebuild twice and compare bytes (idempotency at e2e)
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_rebuild_twice_produces_byte_identical_state(tmp_path: Path) -> None:
    """Subprocess-level idempotency: two consecutive rebuild-state runs yield byte-equal state.json.

    Catches subprocess-environment regressions (e.g., a logger that timestamps state)
    that the in-process unit test cannot detect.
    """
    state_path = _bootstrap_initialized(tmp_path)
    _write_journal_entries(tmp_path, 3)
    state_path.unlink()

    result1 = _run_sdlc(["rebuild-state"], tmp_path)
    assert result1.returncode == 0, f"first rebuild failed; stderr: {result1.stderr}"
    bytes_first = state_path.read_bytes()

    result2 = _run_sdlc(["rebuild-state"], tmp_path)
    assert result2.returncode == 0, f"second rebuild failed; stderr: {result2.stderr}"
    bytes_second = state_path.read_bytes()

    assert bytes_first == bytes_second, "rebuild-state is not idempotent across subprocess runs"
    # Atomic-protocol invariant after second run too.
    assert not (tmp_path / ".claude" / "state" / "state.json.tmp").exists()
