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


def make_watchdog_stop_decision(
    repo_root_str: str,
    *,
    elapsed_minutes: float,
    mad_mode: bool = False,
) -> StopDecision:
    """Synthesize the loop-level watchdog halt decision (C3/C4)."""
    suffix = " (mad-mode)" if mad_mode else ""
    return StopDecision(
        fired=True,
        trigger="watchdog_timeout",
        target=repo_root_str,
        reason=f"elapsed {_format_elapsed(elapsed_minutes)}{suffix}",
    )


def watchdog_stop_decision_if_exceeded(
    start_monotonic: float,
    *,
    now_monotonic: float,
    timeout_minutes: float,
    repo_root_str: str,
    mad_mode: bool = False,
) -> StopDecision | None:
    """Return the watchdog halt decision when the deadline is exceeded."""
    if not watchdog_deadline_exceeded(
        start_monotonic,
        now_monotonic=now_monotonic,
        timeout_minutes=timeout_minutes,
    ):
        return None
    elapsed_minutes = (now_monotonic - start_monotonic) / 60.0
    return make_watchdog_stop_decision(
        repo_root_str,
        elapsed_minutes=elapsed_minutes,
        mad_mode=mad_mode,
    )
