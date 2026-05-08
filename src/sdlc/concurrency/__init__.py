from __future__ import annotations

import sys

from sdlc.concurrency.subprocess_pool import BoundedDispatcher

# file_lock and lock_registry are POSIX-only; import is skipped on Windows
# (the entire concurrency/locks.py module is POSIX-only by design — see Dev Notes).
if sys.platform != "win32":
    from sdlc.concurrency.locks import file_lock, lock_registry

# Semantic order: locks → registry-introspection → dispatcher (Architecture §1058)
if sys.platform != "win32":
    __all__ = (  # noqa: RUF022
        "file_lock",
        "lock_registry",
        "BoundedDispatcher",
    )
else:
    __all__ = ("BoundedDispatcher",)
