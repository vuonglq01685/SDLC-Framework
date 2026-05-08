"""Session-scoped fixtures for chaos tests (Story 1.10)."""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

if sys.platform != "win32":
    import os

_NODE_NAME_FS_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _is_tmpfs(path: Path) -> bool:
    """Best-effort check if path is on a tmpfs (Linux only)."""
    if sys.platform != "linux":
        return False
    try:
        result = subprocess.run(
            ["df", "-T", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return "tmpfs" in result.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def _cleanup_artifacts(directory: Path) -> None:
    """Remove orphan .tmp and .lock files between tests."""
    if not directory.exists():
        return
    for artifact in list(directory.glob("*.tmp")) + list(directory.glob("*.lock")):
        with contextlib.suppress(OSError):
            artifact.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def chaos_target_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped tmp directory for chaos tests.

    Asserts directory is writable and fsyncable. Skips if on tmpfs-only filesystem.
    """
    directory = tmp_path_factory.mktemp("chaos-state")

    if _is_tmpfs(directory):
        pytest.skip(
            f"chaos tests require a non-tmpfs filesystem for meaningful fsync semantics; "
            f"{directory} appears to be on tmpfs"
        )

    # Verify directory is writable and fsyncable
    if sys.platform != "win32":
        probe = directory / "fsync_probe"
        try:
            fd = os.open(str(probe), os.O_CREAT | os.O_WRONLY, 0o644)
            os.write(fd, b"probe")
            os.fsync(fd)
            os.close(fd)
            dir_fd = os.open(str(directory), os.O_RDONLY)
            os.fsync(dir_fd)
            os.close(dir_fd)
            probe.unlink(missing_ok=True)
        except OSError as e:
            pytest.skip(f"chaos target directory is not fsyncable: {e}")

    return directory


@pytest.fixture()
def chaos_target(chaos_target_dir: Path, request: pytest.FixtureRequest) -> Iterator[Path]:
    """Per-test target path under chaos_target_dir with artifact cleanup."""
    safe_name = _NODE_NAME_FS_UNSAFE.sub("_", request.node.name)[:32]
    target = chaos_target_dir / f"state_{safe_name}.json"
    _cleanup_artifacts(chaos_target_dir)
    yield target
    _cleanup_artifacts(chaos_target_dir)
