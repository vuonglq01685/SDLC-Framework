"""Retry policy: 1 attempt + 2 retries, exponential backoff 1s/4s (FR27, NFR-REL-4).

Architecture §821-§824, §1067; ADR-026 §1 (TDD-first commit 1).

Only ``DispatchError`` (and subclasses) trigger retry. All other ``SdlcError``
subclasses (``WorkflowError``, ``SpecialistError``, ``HookError``, etc.) and
non-``SdlcError`` exceptions propagate immediately without retry.

P9: catches ``Exception`` (not ``BaseException``) and explicitly re-raises
``KeyboardInterrupt`` / ``SystemExit`` / ``CancelledError`` for AC4 last bullet.
P10: preserves inner ``details`` from the wrapped exception in the final raise.
P11: replaces production ``assert`` with ``raise`` (python -O safe).
P12: validates ``max_attempts >= 1`` and ``len(backoff_schedule) >= 1`` at entry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sdlc.errors import DispatchError

T = TypeVar("T")

_DEFAULT_MAX_ATTEMPTS: int = 3
_DEFAULT_BACKOFF: tuple[float, ...] = (1.0, 4.0)


def _is_retryable(exc: BaseException) -> bool:
    """Return True only for DispatchError and its subclasses (FR27 narrow-retry posture)."""
    return isinstance(exc, DispatchError)


async def with_retries(  # noqa: C901 — retry control flow is intrinsically branchy
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    backoff_schedule: tuple[float, ...] = _DEFAULT_BACKOFF,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    retryable: Callable[[BaseException], bool] = _is_retryable,
    on_attempt: Callable[[int, str], Awaitable[None]] | None = None,
) -> T:
    """Await ``coro_factory()`` up to ``max_attempts`` times with exponential backoff.

    ``coro_factory`` is called fresh on each attempt (coroutines are single-shot).
    ``sleep`` is dependency-injected for test reproducibility.
    ``on_attempt(attempt_num, outcome)`` is called after each attempt if provided;
    outcome is ``"success"``, ``"retry"`` (not the last failure), or ``"failed"`` (last failure).

    Retry contract:
    - Attempt 1: call coro_factory(); on success: call on_attempt(1, "success"), return.
    - On ``retryable`` exception: call on_attempt(attempt, "retry"|"failed"), then sleep
      ``backoff_schedule[attempt-1]`` and retry.
    - After ``max_attempts`` failures: raise ``DispatchError("dispatch failed after N
      attempts: <last_message>", details={"attempts": N, "last_error": ..., "inner_details": ...})``
      with ``__cause__`` set to the final exception.
    - Non-retryable exceptions (including ``asyncio.CancelledError``,
      ``KeyboardInterrupt``, ``SystemExit``) propagate immediately without retry (P9).
    """
    if max_attempts < 1:
        raise DispatchError(
            f"with_retries: max_attempts must be >= 1, got {max_attempts}",
            details={"max_attempts": max_attempts},
        )
    if not backoff_schedule:
        raise DispatchError(
            "with_retries: backoff_schedule must be non-empty",
            details={"backoff_schedule": backoff_schedule},
        )

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await coro_factory()
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            # Honour cancellation/shutdown signals immediately (AC4 last bullet, P9).
            raise
        except Exception as exc:
            if not retryable(exc):
                raise
            last_exc = exc
            is_last = attempt >= max_attempts
            if on_attempt is not None:
                await on_attempt(attempt, "failed" if is_last else "retry")
            if not is_last:
                backoff_idx = attempt - 1
                delay = backoff_schedule[min(backoff_idx, len(backoff_schedule) - 1)]
                await sleep(delay)
            continue
        if on_attempt is not None:
            await on_attempt(attempt, "success")
        return result

    if last_exc is None:
        raise DispatchError(
            f"with_retries: exhausted {max_attempts} attempts but captured no exception",
            details={"attempts": max_attempts},
        )

    inner_details = getattr(last_exc, "details", None)
    error_details: dict[str, object] = {
        "attempts": max_attempts,
        "last_error": str(last_exc),
    }
    if inner_details:
        error_details["inner_details"] = dict(inner_details)
    raise DispatchError(
        f"dispatch failed after {max_attempts} attempts: {last_exc}",
        details=error_details,
    ) from last_exc


__all__ = ["with_retries"]
