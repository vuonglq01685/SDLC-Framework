"""Shared factories for ``test_dispatcher_hook_integration.py`` (LOC cap §765)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType

from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import build_pre_write_hook_chain
from sdlc.hooks.runner import HookDecision
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

PRIMARY = "product-strategist"
OUTPUT = "# Product Requirements\n\nContent here.\n"


def make_specialist(name: str, target: str) -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=name,
        title="Product Strategist",
        icon="📋",
        model="claude-opus-4-5",
        description="Writes product requirements.",
        write_globs=(target,),
    )
    return Specialist(
        frontmatter=fm,
        body="You are the product strategist.",
        source_path=Path(f"specialists/{name}.md"),
    )


def make_step(name: str, specialist: str, target: str) -> WorkflowSpec:
    return WorkflowSpec(
        schema_version=1,
        name=name,
        slash_command="sdlc-start",
        primary_agent=specialist,
        parallel_agents=(),
        synthesizer_agent=None,
        write_globs={specialist: (target,)},
    )


def make_registry(*specialists: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specialists}))


def phase_gate_hook(repo_root: Path) -> Callable[[HookPayload], HookDecision]:
    """Production phase_gate binding (Story 2A.7 AC7 — signoff_reader injected).

    P42 (Story 2A.8): locate the phase-gate hook in the chain by its
    ``__is_phase_gate__`` attribute marker, not by index ``[1]``. This is
    forward-compatible with the Phase-3 C1 refactor that converts the closure to
    a ``_PhaseGateHook`` callable class while still carrying the marker.
    """
    chain = build_pre_write_hook_chain(repo_root)
    return next(h for h in chain if getattr(h, "__is_phase_gate__", False))


async def instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)
