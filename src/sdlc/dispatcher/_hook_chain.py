"""Pre-write hook-chain builder (Story 2A.7 D1, AC7 wiring shim).

The dispatcher boundary is allowed to import both ``hooks/`` and ``signoff/``
(boundary rule §1067/§1109 forbids ``hooks/`` from importing ``signoff/``,
but ``dispatcher/`` is the composition root). This builder produces the
production-ready ``(naming_validator, phase_gate-with-signoff_reader)`` tuple
that ``run_hook_chain`` consumes.

Story 2A.6 (`claude-code-pretooluse-hook-hook-check`) is the canonical caller:
it invokes ``build_pre_write_hook_chain(repo_root)`` at chain-construction
time and passes the result to ``run_hook_chain``. Until 2A.6 lands, this
builder is exercised by the integration test suite to guarantee the wiring
is correct end-to-end.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.builtin import naming_validator, phase_gate
from sdlc.hooks.runner import HookDecision
from sdlc.signoff import compute_state


def _signoff_reader(phase: int, repo_root: Path) -> str:
    """Adapter: ``compute_state`` accepts ``repo_root`` as kwarg-only.

    Returns the canonical state value as a ``str`` (SignoffState is a str-Enum,
    so its members compare equal to their string values like "approved").
    """
    return compute_state(phase, repo_root=repo_root).value


def build_pre_write_hook_chain(
    repo_root: Path,
) -> tuple[Callable[[HookPayload], HookDecision], ...]:
    """Return the production pre-write hook chain (AC7 D1 wiring).

    Order: naming_validator → phase_gate (first deny short-circuits per AC3).

    The phase_gate closure is bound to ``repo_root`` and ``signoff_reader``
    at construction time so call sites can pass it directly to
    ``run_hook_chain(hooks=..., ...)``.
    """
    bound_phase_gate = partial(
        phase_gate,
        repo_root=repo_root,
        signoff_reader=_signoff_reader,
    )
    # Mark wrapper so run_hook_chain's bypass-detection heuristic recognizes it
    # without falling back to the co_names probe (see runner._is_phase_gate_closure).
    bound_phase_gate.__is_phase_gate__ = True  # type: ignore[attr-defined]
    return (naming_validator, bound_phase_gate)
