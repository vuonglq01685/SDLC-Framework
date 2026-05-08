from __future__ import annotations

import asyncio

import pytest

from sdlc.concurrency.subprocess_pool import BoundedDispatcher
from sdlc.errors import DispatchError


@pytest.mark.unit
def test_dispatch_many_caps_concurrency() -> None:
    dispatcher = BoundedDispatcher(semaphore_size=4)
    max_observed: list[int] = [0]

    async def _probe_coro() -> None:
        max_observed[0] = max(max_observed[0], dispatcher.current_in_flight())
        await asyncio.sleep(0.01)
        max_observed[0] = max(max_observed[0], dispatcher.current_in_flight())

    async def _run() -> None:
        coros = [_probe_coro() for _ in range(20)]
        await dispatcher.dispatch_many(coros)

    asyncio.run(_run())
    assert 2 <= max_observed[0] <= 4


@pytest.mark.unit
def test_dispatch_many_returns_in_input_order() -> None:
    dispatcher = BoundedDispatcher(semaphore_size=3)

    async def _return_after(n: int) -> int:
        await asyncio.sleep(0.01 * (5 - n % 5))  # varying sleep
        return n

    async def _run() -> list[int]:
        coros = [_return_after(i) for i in range(10)]
        return await dispatcher.dispatch_many(coros)

    results = asyncio.run(_run())
    assert results == list(range(10))


@pytest.mark.unit
def test_dispatch_many_empty_iterable_returns_empty_list() -> None:
    dispatcher = BoundedDispatcher(semaphore_size=2)

    async def _run() -> list[int]:
        return await dispatcher.dispatch_many([])

    results = asyncio.run(_run())
    assert results == []


@pytest.mark.unit
def test_current_in_flight_zero_at_rest() -> None:
    dispatcher = BoundedDispatcher(semaphore_size=2)
    assert dispatcher.current_in_flight() == 0

    async def _simple() -> int:
        return 42

    async def _run() -> None:
        await dispatcher.dispatch_many([_simple()])

    asyncio.run(_run())
    assert dispatcher.current_in_flight() == 0


@pytest.mark.unit
def test_construction_rejects_zero_or_negative_size() -> None:
    for bad_size in (0, -1):
        with pytest.raises(DispatchError) as exc_info:
            BoundedDispatcher(semaphore_size=bad_size)
        assert exc_info.value.details.get("semaphore_size") == bad_size


@pytest.mark.unit
def test_dispatch_many_propagates_exception() -> None:
    dispatcher = BoundedDispatcher(semaphore_size=2)

    async def _fail() -> int:
        raise ValueError("dispatch failed")

    async def _run() -> None:
        await dispatcher.dispatch_many([_fail()])

    with pytest.raises(ValueError, match="dispatch failed"):
        asyncio.run(_run())

    assert dispatcher.current_in_flight() == 0
