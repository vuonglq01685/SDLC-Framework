"""Unit tests for dispatcher.retry.with_retries (Story 2A.3, AC4, Task 2.1).

TDD-first: tests committed before implementation (ADR-026 §1).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from sdlc.errors import (
    ConfigError,
    DispatchError,
    HookError,
    SpecialistError,
    WorkflowError,
)

pytestmark = pytest.mark.unit


def _make_mock_sleep() -> tuple[list[float], Callable[[float], "asyncio.coroutine"]]:
    """Return (recorded_delays, mock_sleep) — mock_sleep records calls without sleeping."""
    delays: list[float] = []

    async def _mock_sleep(seconds: float) -> None:
        delays.append(seconds)

    return delays, _mock_sleep


def _succeeds(result: object) -> Callable[[], "asyncio.coroutine"]:
    """Return a coro_factory that always succeeds."""

    async def _coro() -> object:
        return result

    return _coro


def _fails_n_then_succeeds(
    n: int, exc: BaseException, result: object = "ok"
) -> Callable[[], "asyncio.coroutine"]:
    """Return a coro_factory that raises exc for the first n attempts, then returns result."""
    state = {"count": 0}

    def _factory() -> "asyncio.coroutine":
        async def _coro() -> object:
            if state["count"] < n:
                state["count"] += 1
                raise exc
            return result

        return _coro()

    return _factory


def _always_fails(exc: BaseException) -> Callable[[], "asyncio.coroutine"]:
    """Return a coro_factory that always raises exc."""

    def _factory() -> "asyncio.coroutine":
        async def _coro() -> object:
            raise exc

        return _coro()

    return _factory


class TestWithRetriesFirstAttemptSuccess:
    def test_returns_result_on_first_success(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        result = asyncio.run(
            with_retries(_succeeds("value"), sleep=mock_sleep)
        )
        assert result == "value"

    def test_no_sleep_on_first_success(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        asyncio.run(with_retries(_succeeds("x"), sleep=mock_sleep))
        assert delays == []

    def test_coro_factory_called_exactly_once_on_success(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        calls: list[int] = []

        def _factory() -> "asyncio.coroutine":
            async def _coro() -> str:
                calls.append(1)
                return "ok"

            return _coro()

        asyncio.run(with_retries(_factory))
        assert len(calls) == 1


class TestWithRetriesOneFailThenSuccess:
    def test_returns_result_after_one_retry(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        result = asyncio.run(
            with_retries(
                _fails_n_then_succeeds(1, DispatchError("transient")),
                sleep=mock_sleep,
            )
        )
        assert result == "ok"

    def test_sleeps_1_second_before_second_attempt(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        asyncio.run(
            with_retries(
                _fails_n_then_succeeds(1, DispatchError("transient")),
                sleep=mock_sleep,
            )
        )
        assert delays == [1.0]

    def test_coro_factory_called_twice(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        calls: list[int] = []
        exc = DispatchError("transient")

        def _factory() -> "asyncio.coroutine":
            async def _coro() -> str:
                calls.append(1)
                if len(calls) == 1:
                    raise exc
                return "ok"

            return _coro()

        asyncio.run(with_retries(_factory))
        assert len(calls) == 2


class TestWithRetriesTwoFailsThenSuccess:
    def test_returns_result_after_two_retries(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        result = asyncio.run(
            with_retries(
                _fails_n_then_succeeds(2, DispatchError("transient")),
                sleep=mock_sleep,
            )
        )
        assert result == "ok"

    def test_sleeps_1s_then_4s(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        asyncio.run(
            with_retries(
                _fails_n_then_succeeds(2, DispatchError("transient")),
                sleep=mock_sleep,
            )
        )
        assert delays == [1.0, 4.0]

    def test_coro_factory_called_three_times(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        calls: list[int] = []

        def _factory() -> "asyncio.coroutine":
            async def _coro() -> str:
                calls.append(1)
                if len(calls) <= 2:
                    raise DispatchError("transient")
                return "ok"

            return _coro()

        asyncio.run(with_retries(_factory))
        assert len(calls) == 3


class TestWithRetriesAllFail:
    def test_raises_dispatch_error_after_3_attempts(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        original = DispatchError("original failure")
        with pytest.raises(DispatchError) as exc_info:
            asyncio.run(
                with_retries(_always_fails(original), sleep=mock_sleep)
            )
        assert "3 attempts" in str(exc_info.value)

    def test_raises_with_cause_set_to_last_exception(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        original = DispatchError("original failure")
        with pytest.raises(DispatchError) as exc_info:
            asyncio.run(
                with_retries(_always_fails(original), sleep=mock_sleep)
            )
        assert exc_info.value.__cause__ is original

    def test_sleeps_twice_on_3_failures(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        with pytest.raises(DispatchError):
            asyncio.run(
                with_retries(_always_fails(DispatchError("fail")), sleep=mock_sleep)
            )
        assert delays == [1.0, 4.0]

    def test_coro_factory_called_exactly_three_times(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        calls: list[int] = []

        def _factory() -> "asyncio.coroutine":
            async def _coro() -> str:
                calls.append(1)
                raise DispatchError("fail")

            return _coro()

        with pytest.raises(DispatchError):
            asyncio.run(with_retries(_factory))
        assert len(calls) == 3


class TestWithRetriesNonRetryableErrors:
    @pytest.mark.parametrize(
        "exc",
        [
            WorkflowError("workflow misconfiguration"),
            SpecialistError("specialist not found"),
            HookError("hook failed"),
            ConfigError("bad config"),
        ],
    )
    def test_sdlc_error_non_dispatch_propagates_immediately(
        self, exc: BaseException
    ) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        with pytest.raises(type(exc)):
            asyncio.run(with_retries(_always_fails(exc), sleep=mock_sleep))
        assert delays == [], "should not sleep for non-retryable SdlcErrors"

    def test_cancelled_error_propagates_immediately(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(
                with_retries(
                    _always_fails(asyncio.CancelledError()),
                    sleep=mock_sleep,
                )
            )
        assert delays == []

    def test_generic_runtime_error_propagates_immediately(self) -> None:
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        with pytest.raises(RuntimeError):
            asyncio.run(
                with_retries(_always_fails(RuntimeError("bug")), sleep=mock_sleep)
            )
        assert delays == []


class TestWithRetriesCoroFactoryCalledFresh:
    def test_each_attempt_gets_a_fresh_coroutine(self) -> None:
        """Verify coro_factory is called fresh each attempt (coroutines are single-shot)."""
        from sdlc.dispatcher.retry import with_retries

        created: list[object] = []

        def _factory() -> "asyncio.coroutine":
            async def _coro() -> str:
                if len(created) < 2:
                    raise DispatchError("transient")
                return "ok"

            obj = _coro()
            created.append(obj)
            return obj

        _, mock_sleep = _make_mock_sleep()
        asyncio.run(with_retries(_factory, sleep=mock_sleep))
        # Each attempt must have received a distinct coroutine object.
        assert len(created) == 3
        assert len({id(c) for c in created}) == 3, "all coro objects must be distinct"


class TestWithRetriesSubclassOfDispatchError:
    def test_subclass_of_dispatch_error_is_retryable(self) -> None:
        """MockMissError is a subclass of DispatchError and MUST trigger retry."""
        from sdlc.errors import MockMissError
        from sdlc.dispatcher.retry import with_retries

        delays, mock_sleep = _make_mock_sleep()
        with pytest.raises(DispatchError) as exc_info:
            asyncio.run(
                with_retries(
                    _always_fails(MockMissError("fixture missing")),
                    sleep=mock_sleep,
                )
            )
        assert delays == [1.0, 4.0], "MockMissError must trigger retry backoff"
