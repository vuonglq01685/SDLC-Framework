"""Single-source suggested-next command (Story 5.18 D2).

Lifted verbatim from the Story 1.17 `cli/status.py::_compute_suggested_next`
stub into this boundary-legal shared module: both `cli` and `dashboard` declare
`state` as a dependency (`scripts/module_boundary_table.py`), so `cli/status.py`
(`sdlc status`) and `dashboard/routes/resume.py` (`GET /api/resume`) can both
import this SAME function. "Same command" then holds by construction, not by
parallel re-derivation across the CLI/dashboard boundary.
"""

from __future__ import annotations

from sdlc.state.model import State


def compute_suggested_next(state: State) -> str:
    """Minimal v1.17 stub. Story 4.x's auto_loop owns the rich engine.
    Fresh-project case is the only AC-tested branch.
    """
    if state.phase == 1 and not state.epics:
        return '/sdlc-start "<idea>"'
    return "sdlc scan"
