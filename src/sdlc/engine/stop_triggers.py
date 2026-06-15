"""STOP-check interface for the auto-loop (Story 4.1, AC5).

Layer 2 (Stories 4.2-4.9) plugs concrete triggers into the registry. Story 4.1 ships
the interface with an empty registry that always returns not-fired.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from sdlc.state.model import State


@dataclass(frozen=True)
class StopDecision:
    """Typed result of a STOP-check consultation."""

    fired: bool
    trigger: str | None = None
    target: str | None = None
    reason: str | None = None


@runtime_checkable
class StopTrigger(Protocol):
    """Frozen interface for Layer-2 STOP trigger implementations."""

    trigger_id: str

    def check(self, *, repo_root: Path, state: State) -> StopDecision: ...


class _EmptyRegistry:
    """Placeholder registry — no triggers registered in Story 4.1."""

    def check_all(self, *, repo_root: Path, state: State) -> StopDecision:
        _ = repo_root, state
        return StopDecision(fired=False)


_REGISTRY = _EmptyRegistry()


def register_stop_trigger(trigger: StopTrigger) -> None:
    """Register a STOP trigger for Layer-2 stories (interface frozen at 4.1)."""
    raise NotImplementedError(
        "register_stop_trigger is reserved for Layer-2; Story 4.1 uses an empty registry"
    )


def check_stop(*, repo_root: Path, state: State) -> StopDecision:
    """Consult all registered STOP triggers; return the first fired decision or not-fired."""
    return _REGISTRY.check_all(repo_root=repo_root, state=state)
