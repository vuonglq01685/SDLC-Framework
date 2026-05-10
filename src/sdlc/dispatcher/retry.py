"""Retry policy: 1 attempt + 2 retries, exponential backoff 1s/4s (FR27, NFR-REL-4).

Architecture §821-§824, §1067; ADR-026 §1 (TDD-first commit 1).

Only ``DispatchError`` (and subclasses) trigger retry. All other ``SdlcError``
subclasses (``WorkflowError``, ``SpecialistError``, ``HookError``, etc.) and
non-``SdlcError`` exceptions propagate immediately without retry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sdlc.errors import DispatchError, SdlcError

T = TypeVar("T")

_DEFAULT_MAX_ATTEMPTS: int = 3
_DEFAULT_BACKOFF: tuple[float, ...] = (1.0, 4.0)


def _is_retryable(exc: BaseException) -> bool:
    """Return True only for DispatchError and its subclasses (FR27 narrow-retry posture)."""
    return isinstance(exc, DispatchError)


async def with_retries(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    backoff_schedule: tuple[float, ...] = _DEFAULT_BACKOFF,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    retryable: Callable[[BaseException], bool] = _is_retryable,
) -> T:
    """Await ``coro_factory()`` up to ``max_attempts`` times with exponential backoff.

    ``coro_factory`` is called fresh on each attempt (coroutines are single-shot).
    ``sleep`` is dependency-injected for test reproducibility.

    Retry contract:
    - Attempt 1: call coro_factory(); on success return immediately.
    - On ``retryable`` exception: sleep ``backoff_schedule[attempt-1]`` seconds, retry.
    - After ``max_attempts`` failures: raise ``DispatchError("dispatch failed after N
      attempts: <last_message>")`` with ``__cause__`` set to the final exception.
    - Non-retryable exceptions (including ``asyncio.CancelledError``,
      ``KeyboardInterrupt``) propagate immediately without retry.
    - ``SdlcError`` subclasses other than ``DispatchError`` are NOT retryable —
      they indicate operator-fixable misconfiguration.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except BaseException as exc:
            if not retryable(exc):
                raise
            last_exc = exc
            if attempt < max_attempts:
                backoff_idx = attempt - 1
                delay = backoff_schedule[backoff_idx] if backoff_idx < len(backoff_schedule) else backoff_schedule[-1]
                await sleep(delay)

    # All attempts exhausted.
    assert last_exc is not None
    raise DispatchError(
        f"dispatch failed after {max_attempts} attempts: {last_exc}",
        details={
            "attempts": max_attempts,
            "last_error": str(last_exc),
        },
    ) from last_exc


__all__ = ["with_retries"]
