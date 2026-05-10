"""Cross-reference validators for specialists (AC5, AC6, Story 2A.2).

Scope (AC6) is intentionally narrow: only `agents/<name>.md` markdown links
and `[[<name>]]` wikilinks are validated. The following forms are
**intentionally not validated** (out of AC6 scope; track-able for 2B.8):

  - Relative-prefixed links: `[text](./agents/x.md)`, `[text](../agents/x.md)`
  - Markdown links with title attributes: `[text](agents/x.md "title")`
  - Whitespace-padded wikilinks: `[[ name ]]` or `[[\nname\n]]`
  - Unicode names (the `[a-z0-9-]+` regex restricts to ASCII kebab-case)
  - References inside fenced code blocks, HTML comments, or inline code
    spans (treated as documentation, not real cross-refs)
  - Broader cross-refs to skills/, commands/, workflows_yaml/ (deferred to 2B.8)

Self-references — a specialist linking to itself — are intentionally allowed.
"""

from __future__ import annotations

import re
from typing import Final

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import SpecialistError
from sdlc.specialists.registry import SpecialistRegistry

# Exported constants (AC6): tested directly by tests importing via _LINK_RE / _WIKILINK_RE.
_LINK_RE: Final[re.Pattern[str]] = re.compile(
    r"\[.*?\]\(agents/(?P<name>[a-z0-9-]+)\.md(?:#.*?)?\)"
)
_WIKILINK_RE: Final[re.Pattern[str]] = re.compile(r"\[\[(?P<name>[a-z0-9-]+)\]\]")

# P-R4: pre-mask fenced code blocks, HTML comments, and inline code spans before
# regex matching so documentation snippets do not trigger false-positive
# dangling-link errors when specialists author docs that reference unbuilt names.
_FENCED_BLOCK_RE: Final[re.Pattern[str]] = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE: Final[re.Pattern[str]] = re.compile(r"`[^`\n]*`")
_HTML_COMMENT_RE: Final[re.Pattern[str]] = re.compile(r"<!--.*?-->", re.DOTALL)


def _replace_with_spaces(match: re.Match[str]) -> str:
    """Substitute the matched span with whitespace of equal length.

    Preserves byte offsets so future patches that surface offsets in
    diagnostics see consistent positions.
    """
    return " " * len(match.group(0))


def _strip_non_link_contexts(body: str) -> str:
    """Remove markdown contexts where references are not real links."""
    for pattern in (_FENCED_BLOCK_RE, _HTML_COMMENT_RE, _INLINE_CODE_RE):
        body = pattern.sub(_replace_with_spaces, body)
    return body


def validate_workflow_refs(spec: WorkflowSpec, registry: SpecialistRegistry) -> None:
    """Validate all specialist cross-references in a WorkflowSpec (AC5).

    Collects ALL violations and raises a single SpecialistError with the full
    list (fail-once-with-full-list pattern, mirrors Story 1.21).
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
        # P-R6: dedupe while preserving insertion order so len(unique) reflects
        # unique offending refs, not call counts (e.g. parallel_agents=["x","x"]
        # for unknown 'x' should report once, not twice).
        unique = list(dict.fromkeys(violations))
        raise SpecialistError(
            f"workflow {spec.name!r} has {len(unique)} unresolved specialist reference(s)",
            details={"violations": unique, "workflow": spec.name},
        )


def validate_internal_links(registry: SpecialistRegistry) -> None:
    """Validate `agents/<name>.md` and `[[<name>]]` cross-refs across all bodies (AC6).

    Strips fenced code blocks, HTML comments, and inline code spans before
    matching so documentation does not surface false-positive dangling errors.
    Self-references are allowed. See module docstring for the full scope.
    """
    names = registry.names()
    all_dangling: list[str] = []

    for specialist in registry.list():
        body = _strip_non_link_contexts(specialist.body)
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
            unique = list(dict.fromkeys(dangling))
            all_dangling.append(
                f"specialist {specialist.frontmatter.name!r} has dangling references: "
                + ", ".join(repr(r) for r in unique)
            )

    if all_dangling:
        raise SpecialistError(
            f"dangling internal links found in {len(all_dangling)} specialist(s)",
            details={"dangling": all_dangling},
        )
