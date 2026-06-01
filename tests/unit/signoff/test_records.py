"""Unit tests for signoff/records.py — SignoffRecord, ArtifactRef, read/write/invalidate."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_VALID_HASH = "sha256:" + "a" * 64
_VALID_HASH2 = "sha256:" + "b" * 64
_TS1 = "2026-05-10T11:00:00.000Z"
_TS2 = "2026-05-10T12:00:00.000Z"
_TS3 = "2026-05-10T12:01:00.000Z"


def _make_record(phase: int = 1) -> object:
    from sdlc.signoff.records import ArtifactRef, SignoffRecord

    return SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=f"0{phase}-Dir/FILE.md", hash=_VALID_HASH),),
        approved_by="alice",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS3,
    )


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


def test_signoff_record_model_validate_happy() -> None:
    from sdlc.signoff.records import ArtifactRef, SignoffRecord

    r = SignoffRecord(
        phase=1,
        artifacts=(ArtifactRef(path="01-Dir/f.md", hash=_VALID_HASH),),
        approved_by="bob",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS3,
    )
    assert r.phase == 1
    assert r.schema_version == 1


def test_signoff_record_rejects_extra_fields() -> None:
    from pydantic import ValidationError

    from sdlc.signoff.records import ArtifactRef, SignoffRecord

    # P28: anchor on the actual error (extra field) rather than any ValidationError —
    # the test was previously vacuous: any unrelated validation regression would
    # still pass `pytest.raises(ValidationError)`.
    with pytest.raises(ValidationError, match=r"extra_field|Extra inputs are not permitted"):
        SignoffRecord(
            phase=1,
            artifacts=(ArtifactRef(path="01-Dir/f.md", hash=_VALID_HASH),),
            approved_by="bob",
            approved_at=_TS2,
            drafted_at=_TS1,
            validated_at=_TS3,
            extra_field="bad",  # type: ignore[call-arg]
        )


def test_artifact_ref_rejects_bad_hash() -> None:
    from pydantic import ValidationError

    from sdlc.signoff.records import ArtifactRef

    with pytest.raises(ValidationError):
        ArtifactRef(path="01-Dir/f.md", hash="md5:notvalid")


def test_artifact_ref_rejects_absolute_path() -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import ArtifactRef

    with pytest.raises((SignoffError, Exception)):
        ArtifactRef(path="/absolute/path.md", hash=_VALID_HASH)


# ---------------------------------------------------------------------------
# read_record
# ---------------------------------------------------------------------------


def test_read_record_returns_none_when_absent(tmp_path: Path) -> None:
    from sdlc.signoff.records import read_record

    result = read_record(phase=1, repo_root=tmp_path)
    assert result is None


def test_read_record_returns_record_when_present(tmp_path: Path) -> None:
    from sdlc.signoff.records import read_record, write_record

    record = _make_record(phase=1)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]
    result = read_record(phase=1, repo_root=tmp_path)
    assert result is not None
    assert result.phase == 1


def test_read_record_raises_on_malformed_yaml(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import read_record

    signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoff_dir.mkdir(parents=True)
    (signoff_dir / "phase-1.yaml").write_text("}{invalid yaml}{", encoding="utf-8")

    with pytest.raises(SignoffError, match="malformed"):
        read_record(phase=1, repo_root=tmp_path)


def test_read_record_raises_on_schema_invalid(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import read_record

    signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoff_dir.mkdir(parents=True)
    # Valid YAML but wrong schema (missing required fields)
    (signoff_dir / "phase-1.yaml").write_text("schema_version: 1\nphase: 1\n", encoding="utf-8")

    with pytest.raises(SignoffError, match="malformed"):
        read_record(phase=1, repo_root=tmp_path)


# ---------------------------------------------------------------------------
# write_record
# ---------------------------------------------------------------------------


def test_write_record_creates_file(tmp_path: Path) -> None:
    from sdlc.signoff.records import write_record

    record = _make_record(phase=1)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]

    target = tmp_path / ".claude" / "state" / "signoffs" / "phase-1.yaml"
    assert target.exists()


def test_write_record_creates_parent_dirs(tmp_path: Path) -> None:
    from sdlc.signoff.records import write_record

    record = _make_record(phase=2)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]

    target = tmp_path / ".claude" / "state" / "signoffs" / "phase-2.yaml"
    assert target.exists()


def test_write_record_round_trip(tmp_path: Path) -> None:
    from sdlc.signoff.records import read_record, write_record

    record = _make_record(phase=1)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]
    loaded = read_record(phase=1, repo_root=tmp_path)
    assert loaded is not None
    assert loaded.phase == record.phase  # type: ignore[union-attr]
    assert loaded.approved_by == record.approved_by  # type: ignore[union-attr]


def test_write_record_refuses_overwrite(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import write_record

    record = _make_record(phase=1)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(SignoffError, match="cannot overwrite"):
        write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]


def test_write_record_trailing_newline(tmp_path: Path) -> None:
    from sdlc.signoff.records import write_record

    record = _make_record(phase=1)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]
    target = tmp_path / ".claude" / "state" / "signoffs" / "phase-1.yaml"
    content = target.read_bytes()
    assert content.endswith(b"\n")


# ---------------------------------------------------------------------------
# invalidate_record
# ---------------------------------------------------------------------------


def test_invalidate_record_sets_fields(tmp_path: Path) -> None:
    from sdlc.signoff.records import invalidate_record, write_record

    record = _make_record(phase=1)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]
    invalidated = invalidate_record(phase=1, repo_root=tmp_path, reason="replan", now_utc=_TS3)
    assert invalidated.invalidated_at == _TS3
    assert invalidated.invalidated_reason == "replan"


def test_invalidate_record_preserves_other_fields(tmp_path: Path) -> None:
    from sdlc.signoff.records import invalidate_record, write_record

    record = _make_record(phase=1)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]
    invalidated = invalidate_record(phase=1, repo_root=tmp_path, reason="replan", now_utc=_TS3)
    assert invalidated.approved_by == record.approved_by  # type: ignore[union-attr]
    assert invalidated.approved_at == record.approved_at  # type: ignore[union-attr]
    assert invalidated.drafted_at == record.drafted_at  # type: ignore[union-attr]


def test_invalidate_record_round_trip(tmp_path: Path) -> None:
    from sdlc.signoff.records import invalidate_record, read_record, write_record

    record = _make_record(phase=1)
    write_record(record, repo_root=tmp_path)  # type: ignore[arg-type]
    invalidate_record(phase=1, repo_root=tmp_path, reason="r", now_utc=_TS3)
    loaded = read_record(phase=1, repo_root=tmp_path)
    assert loaded is not None
    assert loaded.invalidated_at == _TS3


def test_invalidate_record_nonexistent_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import invalidate_record

    with pytest.raises(SignoffError):
        invalidate_record(phase=1, repo_root=tmp_path, reason="r", now_utc=_TS3)


# ---------------------------------------------------------------------------
# list_records
# ---------------------------------------------------------------------------


def test_list_records_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    from sdlc.signoff.records import list_records

    result = list_records(tmp_path)
    assert result == ()


def test_list_records_returns_sorted_by_phase(tmp_path: Path) -> None:
    from sdlc.signoff.records import list_records, write_record

    r2 = _make_record(phase=2)
    r1 = _make_record(phase=1)
    write_record(r2, repo_root=tmp_path)  # type: ignore[arg-type]
    write_record(r1, repo_root=tmp_path)  # type: ignore[arg-type]
    records = list_records(tmp_path)
    assert len(records) == 2
    assert records[0].phase == 1
    assert records[1].phase == 2


def test_list_records_ignores_phase3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from sdlc.signoff.records import list_records

    signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoff_dir.mkdir(parents=True)
    (signoff_dir / "phase-3.yaml").write_text("dummy: true\n", encoding="utf-8")

    records = list_records(tmp_path)
    assert records == ()


# ---------------------------------------------------------------------------
# EPIC-2A-D7A — SIGNOFF-FLOCK-CONCURRENCY: per-target exclusive write lock
#
# write_record / invalidate_record must hold a per-phase flock across the
# exists-check + tmp+replace so two concurrent writers cannot both pass the
# guard and clobber the shared .tmp path. POSIX-only (ci.yml matrix has no
# Windows runner — Windows lock-free path is deferred as EPIC-2A-D7B).
# The RED-without-fix behaviour of these tests IS the anti-tautology receipt.
# ---------------------------------------------------------------------------

_WIN32 = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX flock; Windows path deferred to EPIC-2A-D7B"
)


@_WIN32
def test_write_record_waits_for_per_target_lock(tmp_path: Path) -> None:
    from sdlc.concurrency.locks import file_lock
    from sdlc.signoff.records import _signoff_path, write_record

    target = _signoff_path(1, tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)  # lock file needs the dir
    lock_path = str(target) + ".lock"
    done = threading.Event()

    def _writer() -> None:
        write_record(_make_record(1), repo_root=tmp_path)  # type: ignore[arg-type]
        done.set()

    with file_lock(lock_path):
        thread = threading.Thread(target=_writer, daemon=True)
        thread.start()
        time.sleep(0.3)
        # While the lock is held externally the writer must be blocked.
        assert not done.is_set(), "write_record did not wait for the per-target lock"
        assert not target.exists(), "write_record wrote while the lock was held"
    thread.join(timeout=5.0)
    assert done.is_set(), "write_record never completed after the lock released"
    assert target.exists()


@_WIN32
def test_invalidate_record_waits_for_per_target_lock(tmp_path: Path) -> None:
    from sdlc.concurrency.locks import file_lock
    from sdlc.signoff.records import _signoff_path, invalidate_record, write_record

    write_record(_make_record(1), repo_root=tmp_path)  # type: ignore[arg-type]
    target = _signoff_path(1, tmp_path)
    lock_path = str(target) + ".lock"
    done = threading.Event()

    def _invalidator() -> None:
        invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_TS3)
        done.set()

    with file_lock(lock_path):
        thread = threading.Thread(target=_invalidator, daemon=True)
        thread.start()
        time.sleep(0.3)
        assert not done.is_set(), "invalidate_record did not wait for the per-target lock"
    thread.join(timeout=5.0)
    assert done.is_set(), "invalidate_record never completed after the lock released"


# ---------------------------------------------------------------------------
# _is_safe_repo_relative_posix + _normalize_yaml_data (Story 2B.10 patch)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "",  # line 74: empty
        "foo\\bar.md",  # line 76: backslash
        "..",  # line 86: bare dotdot
        "../etc/passwd",  # line 86: dotdot prefix
        "foo/../bar.md",  # line 88: interior dotdot
        "foo/..",  # line 89: trailing dotdot
    ],
)
def test_is_safe_rejected_paths(path: str) -> None:
    """_is_safe_repo_relative_posix rejects unsafe path patterns."""
    from sdlc.signoff.records import _is_safe_repo_relative_posix

    assert _is_safe_repo_relative_posix(path) is False


def test_normalize_yaml_naive_datetime_raises() -> None:
    """Line 108: naive datetime (no tzinfo) raises SignoffError."""
    import datetime

    from sdlc.errors import SignoffError
    from sdlc.signoff.records import _normalize_yaml_data

    naive = datetime.datetime(2026, 1, 1, 12, 0, 0)  # no tzinfo
    with pytest.raises(SignoffError, match="timezone"):
        _normalize_yaml_data(naive)


def test_normalize_yaml_plain_date_to_midnight_utc() -> None:
    """Line 118: plain datetime.date -> midnight UTC string."""
    import datetime

    from sdlc.signoff.records import _normalize_yaml_data

    assert _normalize_yaml_data(datetime.date(2026, 6, 1)) == "2026-06-01T00:00:00.000Z"


@pytest.mark.parametrize(
    "patch_fn,err", [("os.write", "disk full"), ("os.replace", "cross-device link")]
)
def test_write_bytes_to_disk_error_arms_clean_up(tmp_path: Path, patch_fn: str, err: str) -> None:
    """fd != -1 (write-fail) and fd == -1 (replace-fail) arms both unlink the tmp."""
    from unittest.mock import patch

    from sdlc.signoff.records import _write_bytes_to_disk

    target = tmp_path / "out.yaml"
    tmp = target.with_suffix(target.suffix + ".tmp")
    with patch(patch_fn, side_effect=OSError(err)), pytest.raises(OSError, match=err):
        _write_bytes_to_disk(target, b"data")
    assert not tmp.exists(), "tmp file leaked on error"
    assert not target.exists()
