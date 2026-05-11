"""Shared factories for ``test_dispatch_panel.py`` (LOC cap — Architecture §765)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

PRIMARY = "product-strategist"
PAR_A = "technical-researcher"
PAR_B = "devil-advocate"
SYNTH = "synthesizer"


def make_specialist(name: str, target: str, body: str = "body") -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=name,
        title=name.title(),
        icon="🤖",
        model="claude-opus-4-5",
        description=f"{name} specialist",
        write_globs=(target,),
    )
    return Specialist(frontmatter=fm, body=body, source_path=Path(f"specialists/{name}.md"))


def make_registry(*specialists: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specialists}))


def make_step(
    *, parallel: tuple[str, ...] = (), synth: str | None = None, primary_target: str = "docs/01.md"
) -> WorkflowSpec:
    write_globs = {PRIMARY: (primary_target,)}
    for name in parallel:
        write_globs[name] = (f"docs/par-{name}.md",)
    if synth:
        write_globs[synth] = (f"docs/synth-{synth}.md",)
    return WorkflowSpec(
        schema_version=1,
        name="requirements",
        slash_command="sdlc-start",
        primary_agent=PRIMARY,
        parallel_agents=parallel,
        synthesizer_agent=synth,
        write_globs=write_globs,
    )


async def instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)


def runtime_returning(text: str = "out") -> AsyncMock:
    runtime = AsyncMock()
    runtime.dispatch.return_value = AgentResult(output_text=text, tokens_in=1, tokens_out=1)
    return runtime
