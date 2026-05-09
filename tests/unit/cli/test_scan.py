"""Unit tests for sdlc.cli.scan (Story 1.17, AC7.1)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.cli.scan import run_scan
from sdlc.state import State, state_to_canonical_bytes

pytestmark = pytest.mark.unit

runner = CliRunner()


def _make_ctx(*, no_color: bool = False, json_mode: bool = False) -> typer.Context:
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json"] = json_mode
    return ctx


def _bootstrap_project(root: Path) -> None:
    """Create the minimal state subtree that sdlc init would create."""
    state_dir = root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    initial_bytes = state_to_canonical_bytes(State())
    (state_dir / "state.json").write_bytes(initial_bytes)
    (state_dir / "journal.log").touch()


@pytest.fixture()
def bootstrapped(tmp_path: Path) -> Path:
    _bootstrap_project(tmp_path)
    return tmp_path


def test_scan_refuses_when_state_not_initialized(tmp_path: Path) -> None:
    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=tmp_path),
        pytest.raises(typer.Exit) as exc_info,
    ):
        run_scan(ctx=ctx)
    assert exc_info.value.exit_code == 1


def test_scan_writes_fresh_state_json(bootstrapped: Path) -> None:
    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch("sdlc.cli.scan._append_scan_journal_entry"),
        unittest.mock.patch("sdlc.engine.scanner.scan", return_value=State()),
    ):
        run_scan(ctx=ctx)
    state_path = bootstrapped / ".claude" / "state" / "state.json"
    assert state_path.exists()
    parsed = json.loads(state_path.read_bytes())
    state = State.model_validate(parsed)
    assert state.next_monotonic_seq == 1


def test_scan_idempotent_state_byte_equal(bootstrapped: Path) -> None:
    """Running scan twice on the same artifact tree produces state.json whose
    content is byte-identical except for the `next_monotonic_seq` field, which
    advances by one per scan (Story 1.17 review: previous form only asserted
    empty dicts, which is a tautology when scanner is mocked to return State())."""
    ctx = _make_ctx()
    state_path = bootstrapped / ".claude" / "state" / "state.json"
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch("sdlc.cli.scan._append_scan_journal_entry"),
        unittest.mock.patch("sdlc.engine.scanner.scan", return_value=State()),
    ):
        run_scan(ctx=ctx)
        snapshot_a = json.loads(state_path.read_bytes())
        run_scan(ctx=_make_ctx())
        snapshot_b = json.loads(state_path.read_bytes())

    # next_monotonic_seq advances; everything else is byte-identical.
    assert snapshot_a["next_monotonic_seq"] == 1
    assert snapshot_b["next_monotonic_seq"] == 2
    a_minus_seq = {k: v for k, v in snapshot_a.items() if k != "next_monotonic_seq"}
    b_minus_seq = {k: v for k, v in snapshot_b.items() if k != "next_monotonic_seq"}
    assert a_minus_seq == b_minus_seq


def test_scan_canonical_bytes_match_state_canonical_bytes(bootstrapped: Path) -> None:
    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch("sdlc.cli.scan._append_scan_journal_entry"),
        unittest.mock.patch("sdlc.engine.scanner.scan", return_value=State()),
    ):
        run_scan(ctx=ctx)
    state_path = bootstrapped / ".claude" / "state" / "state.json"
    raw = state_path.read_bytes()
    # Must end with newline (canonical bytes contract)
    assert raw.endswith(b"\n")
    # Must be valid JSON with sorted keys
    parsed = json.loads(raw)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


def test_scan_json_mode_emits_canonical_envelope(bootstrapped: Path) -> None:
    expected_keys = {
        "command",
        "project_root",
        "phase",
        "epic_count",
        "story_count",
        "task_count",
        "next_monotonic_seq",
        "journal_entry_seq",
    }
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch("sdlc.cli.scan._append_scan_journal_entry"),
        unittest.mock.patch("sdlc.engine.scanner.scan", return_value=State()),
    ):
        result = runner.invoke(app, ["--json", "scan"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == expected_keys
    assert payload["command"] == "scan"
    assert payload["epic_count"] == 0


def test_scan_appends_journal_scan_completed_entry(bootstrapped: Path) -> None:
    """Asserts the journal entry kwargs AND the before/after sha256 contract (AC1.5).

    Strengthened in Story 1.17 review: previous form captured kwargs but never
    verified that `before_hash` matches the pre-scan state.json bytes and
    `after_hash` matches the post-scan canonical bytes.
    """
    import hashlib

    captured_entries: list[object] = []

    def _capture_append(**kwargs: object) -> None:
        captured_entries.append(kwargs)

    state_path = bootstrapped / ".claude" / "state" / "state.json"
    pre_scan_bytes = state_path.read_bytes()
    expected_before_hash = f"sha256:{hashlib.sha256(pre_scan_bytes).hexdigest()}"

    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch(
            "sdlc.cli.scan._append_scan_journal_entry", side_effect=_capture_append
        ),
        unittest.mock.patch("sdlc.engine.scanner.scan", return_value=State()),
    ):
        run_scan(ctx=ctx)

    assert len(captured_entries) == 1
    entry_kwargs = captured_entries[0]
    assert isinstance(entry_kwargs, dict)
    assert entry_kwargs["seq"] == 0
    assert entry_kwargs["epic_count"] == 0
    assert entry_kwargs["story_count"] == 0
    assert entry_kwargs["task_count"] == 0
    # Hash content contract (AC1.5):
    assert entry_kwargs["before_hash"] == expected_before_hash
    after_hash = entry_kwargs["after_hash"]
    assert isinstance(after_hash, str)
    assert after_hash.startswith("sha256:")
    assert len(after_hash) == len("sha256:") + 64
    # after_hash must equal sha256 of the post-scan canonical bytes.
    post_scan_bytes = state_path.read_bytes()
    assert after_hash == f"sha256:{hashlib.sha256(post_scan_bytes).hexdigest()}"


def test_scan_scans_artifacts_when_present(bootstrapped: Path) -> None:
    """AC7.1 — scan picks up an EPIC artifact in 01-Requirement/04-Epics/ and
    propagates it into state.epics with the right counts."""
    epics_dir = bootstrapped / "01-Requirement" / "04-Epics"
    epics_dir.mkdir(parents=True, exist_ok=True)
    (epics_dir / "EPIC-test.json").write_text(
        json.dumps({"id": "EPIC-test", "title": "test"}), encoding="utf-8"
    )

    captured_entries: list[object] = []

    def _capture_append(**kwargs: object) -> None:
        captured_entries.append(kwargs)

    state_path = bootstrapped / ".claude" / "state" / "state.json"
    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch(
            "sdlc.cli.scan._append_scan_journal_entry", side_effect=_capture_append
        ),
    ):
        run_scan(ctx=ctx)

    parsed = json.loads(state_path.read_bytes())
    assert "EPIC-test" in parsed["epics"]
    assert len(captured_entries) == 1
    entry_kwargs = captured_entries[0]
    assert isinstance(entry_kwargs, dict)
    assert entry_kwargs["epic_count"] == 1


def test_scan_appends_one_journal_entry_per_call(bootstrapped: Path) -> None:
    captured_entries: list[object] = []

    def _capture_append(**kwargs: object) -> None:
        captured_entries.append(kwargs)

    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch(
            "sdlc.cli.scan._append_scan_journal_entry", side_effect=_capture_append
        ),
        unittest.mock.patch("sdlc.engine.scanner.scan", return_value=State()),
    ):
        run_scan(ctx=ctx)
        run_scan(ctx=_make_ctx())

    assert len(captured_entries) == 2
    seqs = [e["seq"] for e in captured_entries if isinstance(e, dict)]  # type: ignore[index]
    assert seqs == [0, 1]


# Note: _get_repo_root_or_cwd helper tests live in test_paths.py (Story 1.17
# review: factored from scan.py + status.py + init.py into cli/_paths.py).
#
# _read_state_portable was removed in Story 1.17 review — see
# tests/unit/state/test_state_read.py for canonical read_state coverage.


# ---------------------------------------------------------------------------
# _compute_sha256_of_file returns None for missing file (line 83)
# ---------------------------------------------------------------------------


def test_compute_sha256_returns_none_for_missing_file(tmp_path: Path) -> None:
    from sdlc.cli.scan import _compute_sha256_of_file

    result = _compute_sha256_of_file(tmp_path / "nonexistent.json")
    assert result is None


# ---------------------------------------------------------------------------
# _append_scan_journal_entry basic call (lines 121-138)
# ---------------------------------------------------------------------------


def test_append_scan_journal_entry_calls_append_sync(tmp_path: Path) -> None:
    from sdlc.cli.scan import _append_scan_journal_entry

    captured: list[object] = []

    def _fake_append(entry: object, *, journal_path: object) -> None:
        captured.append(entry)

    with unittest.mock.patch("sdlc.journal.append_sync", side_effect=_fake_append):
        _append_scan_journal_entry(
            journal_path=tmp_path / "journal.log",
            seq=7,
            ts="2024-01-01T00:00:00.000Z",
            before_hash=None,
            after_hash="sha256:" + "a" * 64,
            epic_count=2,
            story_count=3,
            task_count=5,
        )

    assert len(captured) == 1
    entry = captured[0]
    assert hasattr(entry, "monotonic_seq")
    assert entry.monotonic_seq == 7  # type: ignore[union-attr]
    assert entry.payload["epic_count"] == 2  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# run_scan error paths (lines 162-163, 176-177, 191-192, 211-212)
# ---------------------------------------------------------------------------


def test_scan_emits_error_when_state_read_raises_state_error(bootstrapped: Path) -> None:
    """A StateError from sdlc.state.read_state surfaces as ERR_INFRASTRUCTURE (exit 3)."""
    from sdlc.errors import StateError

    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch("sdlc.state.read_state", side_effect=StateError("disk failure")),
        pytest.raises(typer.Exit) as exc_info,
    ):
        run_scan(ctx=ctx)
    assert exc_info.value.exit_code == 3


def test_scan_emits_error_when_engine_scan_raises_state_error(bootstrapped: Path) -> None:
    from sdlc.errors import StateError

    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        # `from sdlc.engine import scan as engine_scan` binds the package-level
        # attribute, so patch `sdlc.engine.scan` (not `sdlc.engine.scanner.scan`).
        unittest.mock.patch("sdlc.engine.scan", side_effect=StateError("scan exploded")),
        pytest.raises(typer.Exit) as exc_info,
    ):
        run_scan(ctx=ctx)
    assert exc_info.value.exit_code == 2


def test_scan_emits_error_when_state_write_raises(bootstrapped: Path) -> None:
    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch("sdlc.engine.scanner.scan", return_value=State()),
        unittest.mock.patch(
            "sdlc.cli.scan._write_state_to_disk", side_effect=OSError("write fail")
        ),
        pytest.raises(typer.Exit) as exc_info,
    ):
        run_scan(ctx=ctx)
    assert exc_info.value.exit_code == 2


def test_scan_emits_error_when_journal_append_raises(bootstrapped: Path) -> None:
    from sdlc.errors import JournalError

    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch("sdlc.engine.scanner.scan", return_value=State()),
        unittest.mock.patch("sdlc.cli.scan._write_state_to_disk"),
        unittest.mock.patch(
            "sdlc.cli.scan._append_scan_journal_entry",
            side_effect=JournalError("append exploded"),
        ),
        pytest.raises(typer.Exit) as exc_info,
    ):
        run_scan(ctx=ctx)
    assert exc_info.value.exit_code == 2
