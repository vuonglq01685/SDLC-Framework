"""Phase-aware resolver for `/sdlc-next` (Story 2A.18, AC2/D1).

Delegates to ``engine.next_selector.resolve_next_action`` (Story 4.1, D1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sdlc.engine.next_selector import NextDecision as _EngineNextDecision
from sdlc.engine.next_selector import resolve_next_action


@dataclass(frozen=True)
class _NextDecision:
    """Output of ``resolve_next``.

    kind:
      "dispatch_task"  — Phase 3 task ready; caller invokes ``run_task(task_id=...)``
      "run_command"    — Phase 1/2 advance; caller prints ``suggested_command``
      "none"           — no ready items; caller prints ``reason``
    """

    kind: Literal["dispatch_task", "run_command", "none"]
    task_id: str | None = None
    command: str | None = None
    phase: int | None = None
    reason: str = ""
    blockers: dict[str, int] = field(default_factory=dict)


def _to_cli_decision(decision: _EngineNextDecision) -> _NextDecision:
    return _NextDecision(
        kind=decision.kind,
        task_id=decision.task_id,
        command=decision.command,
        phase=decision.phase,
        reason=decision.reason,
        blockers=dict(decision.blockers),
    )


def resolve_next(repo_root: Path) -> _NextDecision:
    """Phase-aware next-item resolver (AC2/D1). Pure function — reads disk only."""
    return _to_cli_decision(resolve_next_action(repo_root))
