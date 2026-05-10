"""Cross-reference validators for specialists (AC5, AC6, Story 2A.2).

Scope (AC6): agents/<name>.md links and [[<name>]] wikilinks only.
Broader cross-refs (skills/, commands/, workflows_yaml/) are out of scope —
tracked as a debt entry alongside Story 2B.8.
"""

from __future__ import annotations

import re
from typing import Final

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import SpecialistError
from sdlc.specialists._registry import SpecialistRegistry

# Exported constants (AC6): tested directly by tests importing via _LINK_RE / _WIKILINK_RE.
_LINK_RE: Final[re.Pattern[str]] = re.compile(
    r"\[.*?\]\(agents/(?P<name>[a-z0-9-]+)\.md(?:#.*?)?\)"
)
_WIKILINK_RE: Final[re.Pattern[str]] = re.compile(r"\[\[(?P<name>[a-z0-9-]+)\]\]")


def validate_workflow_refs(spec: WorkflowSpec, registry: SpecialistRegistry) -> None:
    """Validate all specialist cross-references in a WorkflowSpec (AC5).

    Collects ALL violations and raises a single SpecialistError with the full list
    (fail-once-with-full-list pattern, mirrors Story 1.21 review-finding shape).
    """
    names = registry.names()
    violations: list[str] = []

    if spec.primary_agent not in names:
        violations.append(
            f"workflow {spec.name!r} references unknown specialist "
            f"{spec.primary_agent!r} (primary_agent)"
        )

    for agent in spec.parallel_agents:
        if agent not in names:
            violations.append(
                f"workflow {spec.name!r} references unknown specialist {agent!r} (parallel_agents)"
            )

    if spec.synthesizer_agent is not None and spec.synthesizer_agent not in names:
        violations.append(
            f"workflow {spec.name!r} references unknown specialist "
            f"{spec.synthesizer_agent!r} (synthesizer_agent)"
        )

    for key in spec.write_globs:
        if key not in names:
            violations.append(
                f"workflow {spec.name!r} write_globs declares unknown specialist {key!r}"
            )

    if violations:
        raise SpecialistError(
            f"workflow {spec.name!r} has {len(violations)} unresolved specialist reference(s)",
            details={"violations": violations, "workflow": spec.name},
        )


def validate_internal_links(registry: SpecialistRegistry) -> None:
    """Validate agents/<name>.md and [[<name>]] cross-references across all specialist bodies (AC6).

    Raises SpecialistError listing all dangling references (fail-loud).
    """
    names = registry.names()
    all_dangling: list[str] = []

    for specialist in registry.list():
        body = specialist.body
        dangling: list[str] = []

        for m in _LINK_RE.finditer(body):
            ref = m.group("name")
            if ref not in names:
                dangling.append(ref)

        for m in _WIKILINK_RE.finditer(body):
            ref = m.group("name")
            if ref not in names:
                dangling.append(ref)

        if dangling:
            all_dangling.append(
                f"specialist {specialist.frontmatter.name!r} has dangling references: "
                + ", ".join(repr(r) for r in dangling)
            )

    if all_dangling:
        raise SpecialistError(
            f"dangling internal links found in {len(all_dangling)} specialist(s)",
            details={"dangling": all_dangling},
        )
