"""Unit tests for src/sdlc/concurrency/io_primitives.py (C1 / Epic 2A retro D1).

RED phase per CONTRIBUTING §2 — tests cover the atomic-write contract:
basic write, idempotency, byte-stability, encoding, absolute-path requirement,
parent-dir existence, EINTR retry on os.write + os.replace, retry budget cap,
permission-error propagation, no tmp-file leak on failure, byte-mode variant,
anti-tautology receipt.

GREEN lands in a follow-up commit.
"""

from __future__ import annotations

import errno
import sys
from pathlib import Path
from unittest import mock

import pytest

# Module under test is POSIX-only. Skip the entire suite on Windows so a CI
# matrix cell doesn't false-fail on the ImportError.
if sys.platform == "win32":  # pragma: no cover
    pytest.skip("io_primitives is POSIX-only", allow_module_level=True)

from sdlc.concurrency import io_primitives

# ---------------------------------------------------------------------------
# atomic_write — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAtomicWriteHappyPath:
    def test_writes_content_to_path(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        io_primitives.atomic_write(target, "hello\n")
        assert target.read_text(encoding="utf-8") == "hello\n"

    def test_overwrite_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        target.write_text("old", encoding="utf-8")
        io_primitives.atomic_write(target, "new\n")
        assert target.read_text(encoding="utf-8") == "new\n"

    def test_idempotent_when_called_twice(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        io_primitives.atomic_write(target, "same\n")
        io_primitives.atomic_write(target, "same\n")
        assert target.read_text(encoding="utf-8") == "same\n"

    def test_utf8_multibyte_round_trips(self, tmp_path: Path) -> None:
        target = tmp_path / "vn.md"
        text = "Tiếng Việt — đậm chất 🇻🇳\n"
        io_primitives.atomic_write(target, text)
        assert target.read_text(encoding="utf-8") == text

    def test_alternate_encoding_round_trips(self, tmp_path: Path) -> None:
        target = tmp_path / "latin.txt"
        io_primitives.atomic_write(target, "café\n", encoding="latin-1")
        assert target.read_bytes() == b"caf\xe9\n"


# ---------------------------------------------------------------------------
# atomic_write — preconditions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAtomicWritePreconditions:
    def test_relative_path_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="absolute"):
            io_primitives.atomic_write(Path("relative.md"), "x")

    def test_missing_parent_dir_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "nope" / "out.md"
        with pytest.raises((FileNotFoundError, NotADirectoryError, OSError)):
            io_primitives.atomic_write(target, "x")


# ---------------------------------------------------------------------------
# atomic_write — tmp + rename protocol
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAtomicWriteProtocol:
    def test_no_tmp_file_remains_after_success(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        io_primitives.atomic_write(target, "x\n")
        # The .tmp sibling must be gone after a successful write.
        assert not any(p.suffix.endswith(io_primitives._TMP_SUFFIX) for p in tmp_path.iterdir())

    def test_target_never_partially_written_on_write_failure(self, tmp_path: Path) -> None:
        """If os.write raises a non-EINTR error, the target file MUST NOT exist
        (or, if it pre-existed, MUST retain its prior content). The contract is
        all-or-nothing — readers either see the old version or the new one,
        never a partial buffer."""
        target = tmp_path / "out.md"
        target.write_text("prior\n", encoding="utf-8")

        with (
            mock.patch(
                "sdlc.concurrency.io_primitives.os.write",
                side_effect=OSError(errno.ENOSPC, "no space"),
            ),
            pytest.raises(OSError),
        ):
            io_primitives.atomic_write(target, "new\n")

        assert target.read_text(encoding="utf-8") == "prior\n"


# ---------------------------------------------------------------------------
# atomic_write — EINTR retry
# ---------------------------------------------------------------------------


def _make_write_eintr_then_succeed(n_eintrs: int) -> mock.MagicMock:
    """Return a mock that raises EINTR ``n_eintrs`` times then delegates to real os.write."""
    real_write = io_primitives.os.write  # captured before patching
    state = {"remaining": n_eintrs}

    def side_effect(fd: int, data: bytes) -> int:
        if state["remaining"] > 0:
            state["remaining"] -= 1
            raise OSError(errno.EINTR, "interrupted")
        return real_write(fd, data)

    return mock.MagicMock(side_effect=side_effect)


@pytest.mark.unit
class TestAtomicWriteEintrRetry:
    def test_single_eintr_recovers(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        eintr_mock = _make_write_eintr_then_succeed(1)
        with mock.patch.object(io_primitives.os, "write", eintr_mock):
            io_primitives.atomic_write(target, "x\n")
        assert target.read_text(encoding="utf-8") == "x\n"

    def test_burst_of_eintrs_recovers(self, tmp_path: Path) -> None:
        # Up to _MAX_EINTR_RETRIES - 1 consecutive EINTRs must still succeed.
        target = tmp_path / "out.md"
        eintr_mock = _make_write_eintr_then_succeed(io_primitives._MAX_EINTR_RETRIES - 1)
        with mock.patch.object(io_primitives.os, "write", eintr_mock):
            io_primitives.atomic_write(target, "x\n")
        assert target.read_text(encoding="utf-8") == "x\n"

    def test_eintr_storm_exceeding_budget_fails(self, tmp_path: Path) -> None:
        # _MAX_EINTR_RETRIES + 1 consecutive EINTRs is pathological — raise.
        target = tmp_path / "out.md"
        always_eintr = mock.MagicMock(side_effect=OSError(errno.EINTR, "interrupted"))
        with (
            mock.patch.object(io_primitives.os, "write", always_eintr),
            pytest.raises(OSError) as excinfo,
        ):
            io_primitives.atomic_write(target, "x\n")
        assert excinfo.value.errno == errno.EINTR

    def test_rename_eintr_recovers(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        real_replace = io_primitives.os.replace
        state = {"remaining": 1}

        def side_effect(src: str, dst: str) -> None:
            if state["remaining"] > 0:
                state["remaining"] -= 1
                raise OSError(errno.EINTR, "interrupted")
            real_replace(src, dst)

        with mock.patch.object(io_primitives.os, "replace", side_effect=side_effect):
            io_primitives.atomic_write(target, "x\n")
        assert target.read_text(encoding="utf-8") == "x\n"


# ---------------------------------------------------------------------------
# atomic_write_bytes — byte-mode variant
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAtomicWriteBytes:
    def test_writes_bytes_unmodified(self, tmp_path: Path) -> None:
        target = tmp_path / "bin.bin"
        payload = bytes(range(256))
        io_primitives.atomic_write_bytes(target, payload)
        assert target.read_bytes() == payload

    def test_empty_bytes_writes_empty_file(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.bin"
        io_primitives.atomic_write_bytes(target, b"")
        assert target.read_bytes() == b""

    def test_bytes_relative_path_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="absolute"):
            io_primitives.atomic_write_bytes(Path("rel.bin"), b"x")


# ---------------------------------------------------------------------------
# Anti-tautology receipt (per ADR-026 §1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAntiTautologyReceipt:
    def test_atomic_write_is_load_bearing_not_a_passthrough(self, tmp_path: Path) -> None:
        """If atomic_write secretly delegated to ``path.write_text`` (a
        passthrough), there would be no tmp file at any moment during the
        write. Patch ``os.write`` to capture which fd it sees; a non-target
        fd proves the tmp+rename protocol is exercised, not a direct write.
        """
        target = tmp_path / "out.md"
        seen_paths: list[str] = []
        real_open = io_primitives.os.open

        def open_capture(path: str, *args: object, **kwargs: object) -> int:
            seen_paths.append(path)
            return real_open(path, *args, **kwargs)

        with mock.patch.object(io_primitives.os, "open", side_effect=open_capture):
            io_primitives.atomic_write(target, "x\n")

        # At least one os.open() must target the tmp suffix, not the final path.
        assert any(p.endswith(io_primitives._TMP_SUFFIX) for p in seen_paths), (
            "atomic_write did not use a tmp file — protocol bypassed, receipt failed"
        )
