"""CLI exit code constants (Architecture §540-§548)."""

from __future__ import annotations

from typing import Final

EXIT_OK: Final[int] = 0
EXIT_USER_ERROR: Final[int] = 1
EXIT_FRAMEWORK_FAILURE: Final[int] = 2
EXIT_INFRASTRUCTURE: Final[int] = 3

__all__ = (
    "EXIT_FRAMEWORK_FAILURE",
    "EXIT_INFRASTRUCTURE",
    "EXIT_OK",
    "EXIT_USER_ERROR",
)
