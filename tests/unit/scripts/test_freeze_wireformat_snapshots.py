"""Unit tests for scripts/freeze_wireformat_snapshots.py (Story 1.21, AC7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import freeze_wireformat_snapshots as fws
from sdlc.contracts import JournalEntry

pytestmark = pytest.mark.unit


def test_canonical_schema_bytes_deterministic() -> None:
    b1 = fws._canonical_schema_bytes(JournalEntry)
    b2 = fws._canonical_schema_bytes(JournalEntry)
    assert b1 == b2


def test_canonical_schema_bytes_is_utf8_ending_newline() -> None:
    b = fws._canonical_schema_bytes(JournalEntry)
    assert isinstance(b, bytes)
    assert b.endswith(b"\n")
    b.decode("utf-8")  # raises if not valid UTF-8


def test_canonical_schema_bytes_contains_schema_version() -> None:
    b = fws._canonical_schema_bytes(JournalEntry)
    assert b"schema_version" in b


def test_verify_one_returns_true_none_on_match(tmp_path: Path) -> None:
    path = tmp_path / "journal_entry.json"
    path.write_bytes(fws._canonical_schema_bytes(JournalEntry))
    ok, msg = fws._verify_one("journal_entry", JournalEntry, path)
    assert ok is True
    assert msg is None


def test_verify_one_returns_false_with_diff_on_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "journal_entry.json"
    path.write_bytes(b'{"stale":"old_schema"}\n')
    ok, msg = fws._verify_one("journal_entry", JournalEntry, path)
    assert ok is False
    assert msg is not None
    assert "journal_entry" in msg


def test_write_one_creates_file_with_parents(tmp_path: Path) -> None:
    path = tmp_path / "v1" / "journal_entry.json"
    fws._write_one("journal_entry", JournalEntry, path)
    assert path.exists()
    content = json.loads(path.read_bytes())
    assert "schema_version" in str(content)


def test_main_check_exits_0_when_all_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # P14: seed tmp_path with valid snapshots and monkeypatch _REPO_ROOT — don't rely
    # on the real repo tree (which couples this unit test to repo state and breaks in
    # ephemeral sandboxes / cache evictions).
    for slug, model_cls in fws._CONTRACTS:
        path = tmp_path / "tests" / "contract_snapshots" / "v1" / f"{slug}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fws._canonical_schema_bytes(model_cls))
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    result = fws.main(["--check"])
    assert result == 0


def test_main_write_refuses_non_tty_without_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # P11 verification: non-tty without --yes returns _EXIT_FRAMEWORK (2) and
    # writes nothing — silent overwrite would be a foot-gun.
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    result = fws.main(["--write"])
    assert result == 2
    assert not (tmp_path / "tests" / "contract_snapshots").exists()


def test_main_write_user_aborts_returns_distinct_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # P1 verification: bare 'n' at the prompt returns _EXIT_USER_ABORT (3),
    # not 1 (which is reserved for drift detection).
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    result = fws.main(["--write"])
    assert result == 3


def test_main_write_eof_returns_user_abort_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # P1 verification: EOF on stdin during prompt returns 3, not a traceback.
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def _eof(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    result = fws.main(["--write"])
    assert result == 3


def test_main_yes_without_write_is_rejected() -> None:
    # P13 verification: --yes alone is meaningless and should fail the parser.
    with pytest.raises(SystemExit):
        fws.main(["--yes"])


def test_main_check_exits_2_on_empty_snapshot_treated_as_drift_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # P10 verification: empty snapshot file returns False from _verify_one with a
    # corruption message (rather than producing a giant unhelpful diff).
    for slug, model_cls in fws._CONTRACTS:
        path = tmp_path / "tests" / "contract_snapshots" / "v1" / f"{slug}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if slug == "journal_entry":
            path.write_bytes(b"")  # empty
        else:
            path.write_bytes(fws._canonical_schema_bytes(model_cls))
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    result = fws.main(["--check"])
    # Empty file is treated as drift (semantic: "doesn't match"); the message names
    # corruption explicitly so the dev knows to regenerate, not bump schema_version.
    assert result == 1


def test_run_check_accumulates_missing_snapshots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # P7 verification: when N snapshots are missing, _run_check reports ALL of them
    # before returning, not just the first.
    result = fws._run_check(tmp_path)
    assert result == 2
    captured = capsys.readouterr()
    # Every contract should be named in the stderr output.
    for slug, _ in fws._CONTRACTS:
        assert slug in captured.err


def test_run_check_flags_unexpected_snapshot_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # P9 verification: a stale / orphan JSON file in the snapshot dir is detected
    # (otherwise a renamed contract leaves a ghost snapshot that nothing pins).
    snapshot_dir = tmp_path / "tests" / "contract_snapshots" / "v1"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for slug, model_cls in fws._CONTRACTS:
        (snapshot_dir / f"{slug}.json").write_bytes(fws._canonical_schema_bytes(model_cls))
    # Orphan: no contract called "ghost".
    (snapshot_dir / "ghost.json").write_bytes(b'{"orphan":true}\n')

    result = fws._run_check(tmp_path)
    assert result == 1
    captured = capsys.readouterr()
    assert "unexpected snapshot file" in captured.err
    assert "ghost.json" in captured.err


def test_main_check_exits_1_when_snapshot_mutated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for slug, model_cls in fws._CONTRACTS:
        path = tmp_path / "tests" / "contract_snapshots" / "v1" / f"{slug}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if slug == "journal_entry":
            path.write_bytes(b'{"stale":"drift"}\n')
        else:
            path.write_bytes(fws._canonical_schema_bytes(model_cls))
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    result = fws.main(["--check"])
    assert result == 1


def test_main_check_exits_2_when_snapshot_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No snapshot files in tmp_path — bootstrap failure expected.
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    result = fws.main(["--check"])
    assert result == 2


def test_main_write_regenerates_all_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    result = fws.main(["--write", "--yes"])
    assert result == 0
    for slug, model_cls in fws._CONTRACTS:
        path = tmp_path / "tests" / "contract_snapshots" / "v1" / f"{slug}.json"
        assert path.exists()
        assert path.read_bytes() == fws._canonical_schema_bytes(model_cls)


def test_main_write_yes_skips_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fws, "_REPO_ROOT", tmp_path)
    prompt_called = [False]

    def _no_input(prompt: str) -> str:
        prompt_called[0] = True
        return "n"  # would abort if reached

    monkeypatch.setattr("builtins.input", _no_input)
    result = fws.main(["--write", "--yes"])
    assert result == 0
    assert prompt_called[0] is False
