from __future__ import annotations

from sdlc.engine.auto_brainstorm import (
    AmbiguityContext,
    clarification_id_for,
    detect_ambiguity_signal,
    run_auto_brainstorm,
)
from sdlc.engine.auto_loop import AutoLoopResult, run_auto_loop
from sdlc.engine.auto_mad import maybe_mad_resolve_stop, try_mad_resolve_stop_and_continue
from sdlc.engine.next_selector import NextDecision, resolve_next_action
from sdlc.engine.replan import compute_downstream, plan_invalidations, resolve_scope_phase
from sdlc.engine.scanner import scan
from sdlc.engine.stop_triggers import StopDecision, StopTrigger, check_stop

__all__ = (
    "AmbiguityContext",
    "AutoLoopResult",
    "NextDecision",
    "StopDecision",
    "StopTrigger",
    "check_stop",
    "clarification_id_for",
    "compute_downstream",
    "detect_ambiguity_signal",
    "maybe_mad_resolve_stop",
    "plan_invalidations",
    "resolve_next_action",
    "resolve_scope_phase",
    "run_auto_brainstorm",
    "run_auto_loop",
    "scan",
    "try_mad_resolve_stop_and_continue",
)
