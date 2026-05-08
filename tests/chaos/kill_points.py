"""KillPoint enum — 10 declared kill points for atomic write chaos tests (AC2, Story 1.10)."""

from __future__ import annotations

from enum import Enum

_KP_DESCRIPTIONS: dict[str, str] = {
    "AFTER_TMP_OPEN": "empty <target>.tmp; previous <target> intact",
    "MID_TMP_WRITE": "partial <target>.tmp; previous <target> intact",
    "AFTER_TMP_WRITE": "full <target>.tmp but not fsynced; previous <target> intact",
    "AFTER_TMP_FSYNC": ("full + durable <target>.tmp; lock not yet held; previous <target> intact"),
    "AFTER_FLOCK_ACQUIRE": (
        "lock held by killed process — kernel releases on PID death; previous <target> intact"
    ),
    "AFTER_RENAME": (
        "new <target> visible BUT directory entry not fsynced;"
        " rename may be reverted under OS-crash"
    ),
    "AFTER_PARENT_DIR_FSYNC": "new <target> durable; lock still held; next start sees new state",
    "BEFORE_FLOCK_RELEASE": "new <target> durable; lock fd may be closed by kernel cleanup",
    "OS_CRASH_PRE_FSYNC": (
        "rename may be lost; tmp may be lost; previous <target> is the only durable artifact"
    ),
    "RECOVERY_OF_RECOVERY": (
        "second invocation must complete cleanly; orphan tmp from prior run must not block"
    ),
}


class KillPoint(Enum):
    """10 declared kill points for atomic-write chaos testing (Architecture §219, NFR-REL-1)."""

    AFTER_TMP_OPEN = "AFTER_TMP_OPEN"
    MID_TMP_WRITE = "MID_TMP_WRITE"
    AFTER_TMP_WRITE = "AFTER_TMP_WRITE"
    AFTER_TMP_FSYNC = "AFTER_TMP_FSYNC"
    AFTER_FLOCK_ACQUIRE = "AFTER_FLOCK_ACQUIRE"
    AFTER_RENAME = "AFTER_RENAME"
    AFTER_PARENT_DIR_FSYNC = "AFTER_PARENT_DIR_FSYNC"
    BEFORE_FLOCK_RELEASE = "BEFORE_FLOCK_RELEASE"
    OS_CRASH_PRE_FSYNC = "OS_CRASH_PRE_FSYNC"
    RECOVERY_OF_RECOVERY = "RECOVERY_OF_RECOVERY"

    @property
    def description(self) -> str:
        """Return 'what is on disk at kill' string for failure messages."""
        return _KP_DESCRIPTIONS[self.value]
