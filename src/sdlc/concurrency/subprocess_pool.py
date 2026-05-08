from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from typing import TypeVar

from sdlc.errors import DispatchError

T = TypeVar("T")


class BoundedDispatcher:
    """Asyncio-Semaphore-backed dispatcher capping parallel coroutine execution.

    Exposes `current_in_flight()` for telemetry (Architecture §1195 — 8th
    STOP-trigger placeholder).  Results are returned in input order, mirroring
    `asyncio.gather` ordering semantics (Architecture §337, Decision A2).
    """

    def __init__(self, semaphore_size: int) -> None:
        if semaphore_size < 1:
            raise DispatchError(
                "semaphore_size must be >= 1",
                details={"semaphore_size": semaphore_size},
            )
        self._sem = asyncio.Semaphore(semaphore_size)
        self._in_flight: int = 0

    def current_in_flight(self) -> int:
        """Return the number of coroutines currently executing under the semaphore."""
        return self._in_flight

    async def dispatch_many(self, coros: Iterable[Awaitable[T]]) -> list[T]:
        """Run *coros* with at most `semaphore_size` executing concurrently.

        Returns results in input order (asyncio.gather guarantee).
        Raises on the first coroutine failure (`return_exceptions=False`).
        """

        async def _acquire_then_run(coro: Awaitable[T]) -> T:
            async with self._sem:
                self._in_flight += 1
                try:
                    return await coro
                finally:
                    self._in_flight -= 1

        wrapped = [_acquire_then_run(c) for c in coros]
        return list(await asyncio.gather(*wrapped, return_exceptions=False))
