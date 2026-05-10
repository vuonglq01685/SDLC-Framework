"""Static disjoint-writes checker for WorkflowSpec (Story 2A.1, AC4).

Glob comparison uses segment-aware matching: each path-segment is matched with
``fnmatch`` (which never has the ``*``-crosses-``/`` hazard at the segment
level), and ``**`` is handled as a recursive zero-or-more-segments wildcard.
This is sound for the disjoint-writes invariant: false-positive overlap
findings are preferred to false-negatives, and the algorithm provably terminates
for any pair of glob patterns containing only ``*``, ``?``, ``**``, and
literal segments.

Alternatives considered (ADR-027 §"Alternatives Considered" pattern):
- raw ``fnmatch.fnmatch`` over the full path: rejected — ``fnmatch``'s ``*``
  matches across ``/`` (e.g. ``fnmatch.fnmatch("a/b/c.json", "*.json") == True``),
  which causes false-positive overlap findings.
- finite probe set: rejected — adversarial pairs can miss every probe.
- ``wcmatch`` / ``pathspec``: rejected to avoid new runtime dependencies.

Reachability and termination checks are out of scope for 2A.1 — deferred as
follow-up debt items (Architecture §193 siblings of disjoint-writes).
"""

from __future__ import annotations

import fnmatch
import itertools
import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import WorkflowError

# Symbolic placeholder used when constructing witnesses for pure-wildcard
# segments (no literal characters to draw from).
_WILDCARD_FILLER: str = "x"


def _segments(glob: str) -> tuple[str, ...]:
    """Split a glob pattern into its path segments using POSIX semantics."""
    return tuple(PurePosixPath(glob).parts)


def _segment_witness(s1: str, s2: str) -> str | None:
    """Return a single-segment string matched by both patterns, or None.

    Conservative: false-positive (returning a non-None witness when patterns
    barely overlap) is preferred to false-negative (returning None when they do).
    """
    if s1 == s2:
        # Resolve any wildcards in the shared pattern to a concrete substring.
        return _resolve_wildcards(s1)
    has_wild_1 = "*" in s1 or "?" in s1
    has_wild_2 = "*" in s2 or "?" in s2
    if not has_wild_1 and not has_wild_2:
        return None  # both literal but unequal
    if not has_wild_1:
        return s1 if fnmatch.fnmatchcase(s1, s2) else None
    if not has_wild_2:
        return s2 if fnmatch.fnmatchcase(s2, s1) else None
    # Both contain wildcards. Try candidates derived from literal islands.
    literals_1 = [c for c in re.split(r"[*?]+", s1) if c]
    literals_2 = [c for c in re.split(r"[*?]+", s2) if c]
    candidates: list[str] = [_WILDCARD_FILLER]
    candidates.extend(literals_1)
    candidates.extend(literals_2)
    candidates.extend(a + b for a in literals_1 for b in literals_2)
    candidates.append("".join(literals_1) or _WILDCARD_FILLER)
    candidates.append("".join(literals_2) or _WILDCARD_FILLER)
    for c in candidates:
        if fnmatch.fnmatchcase(c, s1) and fnmatch.fnmatchcase(c, s2):
            return c
    return None


def _resolve_wildcards(seg: str) -> str:
    """Concretize a single-segment pattern by replacing wildcards with filler."""
    return (
        seg.replace("**", _WILDCARD_FILLER)
        .replace("*", _WILDCARD_FILLER)
        .replace("?", _WILDCARD_FILLER)
    )


def _witness_both_doublestar(p1: Sequence[str], p2: Sequence[str]) -> tuple[str, ...] | None:
    """Both heads are ``**``; either can consume zero or more path segments."""
    t1, t2 = p1[1:], p2[1:]
    for cand in (
        _overlap_witness(t1, t2),
        _overlap_witness(t1, p2),
        _overlap_witness(p1, t2),
    ):
        if cand is not None:
            return cand
    return None


def _witness_one_doublestar(
    star_pattern: Sequence[str],
    other_pattern: Sequence[str],
    star_first: bool,
) -> tuple[str, ...] | None:
    """One head is ``**``; the other is a concrete-or-wildcard segment.

    ``star_pattern[0]`` is ``**``; ``other_pattern[0]`` is not.
    ``star_first`` controls witness ordering only; it does not affect the
    set of accepted paths.
    """
    star_tail = star_pattern[1:]
    other_head, other_tail = other_pattern[0], other_pattern[1:]
    # ``**`` consumes zero path segments — drop it and re-try.
    sub = (
        _overlap_witness(star_tail, other_pattern)
        if star_first
        else _overlap_witness(other_pattern, star_tail)
    )
    if sub is not None:
        return sub
    # ``**`` consumes one path segment, which must satisfy the other head too.
    seg = _resolve_wildcards(other_head)
    sub = (
        _overlap_witness(star_pattern, other_tail)
        if star_first
        else _overlap_witness(other_tail, star_pattern)
    )
    if sub is None:
        return None
    return (seg, *sub)


def _empty_pattern_witness(other: Sequence[str]) -> tuple[str, ...] | None:
    """Witness for one empty pattern: matches the empty path iff the other is all ``**``."""
    return () if all(s == "**" for s in other) else None


def _witness_neither_doublestar(p1: Sequence[str], p2: Sequence[str]) -> tuple[str, ...] | None:
    """Both heads are concrete-or-wildcard single segments; match them pairwise."""
    seg = _segment_witness(p1[0], p2[0])
    if seg is None:
        return None
    sub = _overlap_witness(p1[1:], p2[1:])
    if sub is None:
        return None
    return (seg, *sub)


def _overlap_witness(p1: Sequence[str], p2: Sequence[str]) -> tuple[str, ...] | None:
    """Return a concrete path (as segment tuple) matched by both segment sequences,
    or None if they are disjoint.

    Both patterns must match the SAME concrete path:
    - ``**`` consumes zero or more PATH segments (greedy: try zero first for the
      shortest witness).
    - When ``**`` consumes one path segment, the OTHER pattern's next segment
      must also match that same path segment.
    """
    if not p1:
        return _empty_pattern_witness(p2)
    if not p2:
        return _empty_pattern_witness(p1)
    if p1[0] == "**" and p2[0] == "**":
        return _witness_both_doublestar(p1, p2)
    if p1[0] == "**":
        return _witness_one_doublestar(p1, p2, star_first=True)
    if p2[0] == "**":
        return _witness_one_doublestar(p2, p1, star_first=False)
    return _witness_neither_doublestar(p1, p2)


def _patterns_can_overlap(p1: Sequence[str], p2: Sequence[str]) -> bool:
    """Return True iff two segment sequences share at least one matching path."""
    return _overlap_witness(p1, p2) is not None


def _canonical_glob(g1: str, g2: str) -> str:
    """Pick a deterministic canonical glob between an overlapping pair.

    Rule (deterministic, no length-tiebreak ambiguity):
    1. If exactly one contains ``**``, the other (more specific) is canonical.
    2. Otherwise the lexicographically smaller glob is canonical.
    """
    g1_has_doublestar = "**" in g1
    g2_has_doublestar = "**" in g2
    if g1_has_doublestar and not g2_has_doublestar:
        return g2
    if g2_has_doublestar and not g1_has_doublestar:
        return g1
    return min(g1, g2)


def _intra_agent_overlap(agent: str, globs: Sequence[str]) -> tuple[str, str] | None:
    """Find any pairwise overlap within a single agent's glob list."""
    for ga, gb in itertools.combinations(sorted(set(globs)), 2):
        if _patterns_can_overlap(_segments(ga), _segments(gb)):
            return (ga, gb)
    return None


def _resolve_known_agents(spec: WorkflowSpec) -> frozenset[str]:
    """Return the set of agent names declared in the workflow's role fields."""
    known: set[str] = {spec.primary_agent, *spec.parallel_agents}
    if spec.synthesizer_agent is not None:
        known.add(spec.synthesizer_agent)
    return frozenset(known)


def _check_phantom_agents(
    sorted_globs: Sequence[tuple[str, tuple[str, ...]]],
    known_agents: frozenset[str],
) -> None:
    for agent, _ in sorted_globs:
        if agent not in known_agents:
            raise WorkflowError(
                f"phantom-agent write_globs entry: agent {agent!r} is not declared "
                f"as primary_agent, parallel_agents, or synthesizer_agent",
                details={"agent": agent, "known_agents": sorted(known_agents)},
            )


def _check_intra_agent_overlaps(
    sorted_globs: Sequence[tuple[str, tuple[str, ...]]],
) -> None:
    for agent, globs in sorted_globs:
        intra = _intra_agent_overlap(agent, globs)
        if intra is not None:
            ga, gb = intra
            raise WorkflowError(
                f"intra-agent write_globs overlap: agent {agent!r} declares "
                f"overlapping globs {ga!r} and {gb!r}",
                details={"agent": agent, "globs": [ga, gb]},
            )


def _check_inter_agent_disjoint(
    sorted_globs: Sequence[tuple[str, tuple[str, ...]]],
) -> None:
    for (agent_a, globs_a), (agent_b, globs_b) in itertools.combinations(sorted_globs, 2):
        for ga in globs_a:
            for gb in globs_b:
                witness_segs = _overlap_witness(_segments(ga), _segments(gb))
                if witness_segs is None:
                    continue
                canonical = _canonical_glob(ga, gb)
                witness = "/".join(witness_segs) if witness_segs else _WILDCARD_FILLER
                sorted_names = sorted([agent_a, agent_b])
                raise WorkflowError(
                    f"disjoint-writes violation: specialists {sorted_names} "
                    f"both write to glob {canonical!r}",
                    details={
                        "specialists": sorted_names,
                        "glob": canonical,
                        "witness": witness,
                    },
                )


def validate_workflow(spec: WorkflowSpec) -> None:
    """Validate the static invariants of a WorkflowSpec at load time.

    Checks (in order):
    1. Every key of ``write_globs`` is a declared agent (primary, parallel, or
       synthesizer). Phantom-agent globs raise ``WorkflowError``.
    2. No agent's own glob list contains pairwise-overlapping patterns
       (intra-agent overlap).
    3. No two agents' glob lists share a matching path (disjoint-writes per AC4).

    Iteration is sorted by agent name so the first-violation message is
    byte-stable across YAML re-orderings (eliminates iteration-order flicker).

    Raises:
        WorkflowError: with message shape
            ``"disjoint-writes violation: specialists [<sorted>] both write to glob '<glob>'"``
        for the inter-agent case, and analogous shapes for phantom-agent and
        intra-agent violations.
    """
    sorted_globs: list[tuple[str, tuple[str, ...]]] = sorted(
        (agent, tuple(globs)) for agent, globs in spec.write_globs.items()
    )
    _check_phantom_agents(sorted_globs, _resolve_known_agents(spec))
    _check_intra_agent_overlaps(sorted_globs)
    _check_inter_agent_disjoint(sorted_globs)
