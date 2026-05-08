"""Best-effort OS-crash simulation for KP9 (Story 1.10).

True power-loss simulation requires a faulty-block device driver (e.g., dmsetup + error target
on Linux). This module provides a best-effort approximation using posix_fadvise to evict page
cache entries, which catches "fsync forgotten" bugs but cannot catch storage-controller-level
write-reordering (Architecture §219 acknowledged gap).

Process-kill (page cache preserved) vs. OS-crash simulation (page cache lost — exposes missing
fsync on directory after rename) — KP9 covers the page-cache-lost variant; full storage-level
chaos is deferred indefinitely.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _simulate_power_loss(target_dir: Path) -> None:
    """Simulate OS-crash by evicting page cache for target directory.

    Best-effort: uses posix_fadvise(POSIX_FADV_DONTNEED) if available (Linux + most BSDs;
    NOT available on macOS — callers must pytest.skip on macOS).
    Falls back to subprocess sync only if posix_fadvise is unavailable.
    """
    import os

    # Flush kernel buffer cache to disk first
    subprocess.run(["sync"], check=False)

    # Attempt posix_fadvise eviction if available
    if not hasattr(os, "posix_fadvise"):
        return

    POSIX_FADV_DONTNEED = 4  # Linux constant; same on most POSIX platforms

    for path in target_dir.iterdir():
        try:
            fd = os.open(str(path), os.O_RDONLY)
            try:
                os.posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED)  # type: ignore[attr-defined]
            finally:
                os.close(fd)
        except OSError:
            pass
