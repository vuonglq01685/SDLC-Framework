"""Wall-clock watchdog deadline helpers for auto-loop (Story 4.9)."""

from __future__ import annotations

from sdlc.engine.stop_triggers import StopDecision


def watchdog_deadline_exceeded(
    start_monotonic: float,
    *,
    now_monotonic: float,
    timeout_minutes: float,
) -> bool:
    """Return True when elapsed monotonic time meets or exceeds the deadline."""
    elapsed_seconds = now_monotonic - start_monotonic
    return elapsed_seconds >= timeout_minutes * 60.0


def _format_elapsed(elapsed_minutes: float) -> str:
    """Human-readable elapsed for the halt reason (C4).

    Render whole minutes for >= 1 min, but fall back to seconds below a minute so a
    sub-minute timeout (e.g. the 0.05-min test value) reads "~3 s" rather than the
    misleading "~0 min" that bare ``int()`` truncation produces.
    """
    if elapsed_minutes >= 1:
        return f"~{int(elapsed_minutes)} min"
    return f"~{round(elapsed_minutes * 60.0)} s"


def make_watchdog_stop_decision(repo_root_str: str, *, elapsed_minutes: float) -> StopDecision:
    """Synthesize the loop-level watchdog halt decision (C3/C4)."""
    return StopDecision(
        fired=True,
        trigger="watchdog_timeout",
        target=repo_root_str,
        reason=f"elapsed {_format_elapsed(elapsed_minutes)}",
    )
