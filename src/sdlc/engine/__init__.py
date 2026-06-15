from __future__ import annotations

from sdlc.engine.auto_loop import AutoLoopResult, run_auto_loop
from sdlc.engine.next_selector import NextDecision, resolve_next_action
from sdlc.engine.replan import compute_downstream, plan_invalidations, resolve_scope_phase
from sdlc.engine.scanner import scan
from sdlc.engine.stop_triggers import StopDecision, StopTrigger, check_stop

__all__ = (
    "AutoLoopResult",
    "NextDecision",
    "StopDecision",
    "StopTrigger",
    "check_stop",
    "compute_downstream",
    "plan_invalidations",
    "resolve_next_action",
    "resolve_scope_phase",
    "run_auto_loop",
    "scan",
)
