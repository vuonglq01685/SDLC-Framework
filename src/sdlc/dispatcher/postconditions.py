"""Runtime postcondition validators for workflow dispatch (Story 2A.8, AC1).

``product_md_exists`` and ``boundary_line_present_in_prompts`` are evaluated from
``sdlc.cli.start.run_start`` after the final ``01-PRODUCT.md`` artifact is composed
(frontmatter + synthesizer body), so YAML shape checks see the on-disk file the
CLI commits.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.prompts import BOUNDARY_LINE
from sdlc.errors import WorkflowError

# Frontmatter split("---", 2) yields [preamble, yaml, body] when well-formed.
_FRONT_MATTER_MIN_SEGMENTS = 3
_H2_HEADING_RE = re.compile(r"^## ", re.MULTILINE)
_BOUNDARY_OPEN_RE = re.compile(r"^<BOUNDARY>$", re.MULTILINE)
_BOUNDARY_CLOSE_RE = re.compile(r"^</BOUNDARY>$", re.MULTILINE)
_BOUNDARY_BLOCK_RE = re.compile(r"<BOUNDARY>\n(.*?)\n</BOUNDARY>", re.DOTALL)


_REQUIRED_PRODUCT_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {"schema_version", "kind", "idea", "drafted_at", "drafted_by_specialists"}
)

_REQUIRED_RESEARCH_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "kind",
        "topic",
        "slug",
        "researched_at",
        "researched_by_specialist",
    }
)


def evaluate_postconditions(
    spec: WorkflowSpec,
    *,
    repo_root: Path,
    agent_runs_path: Path,
    product_rel: str = "01-Requirement/01-PRODUCT.md",
    research_artifact_abs: Path | None = None,
) -> None:
    """Raise WorkflowError on first failed postcondition when the workflow lists any."""
    if not spec.postconditions:
        return
    for name in spec.postconditions:
        if name == "product_md_exists":
            _check_product_md_exists(repo_root / product_rel)
        elif name == "boundary_line_present_in_prompts":
            _check_boundary_line_in_runs(agent_runs_path)
        elif name == "product_md_frontmatter_keys":
            _check_product_md_frontmatter_keys(repo_root / product_rel)
        elif name == "research_md_exists":
            if research_artifact_abs is None:
                # Programmer error (caller forgot to plumb the path), not a workflow
                # contract failure — use RuntimeError so observers/journal'ers do not
                # record this as a workflow problem (Story 2A.9 code review P19).
                raise RuntimeError(
                    f"postcondition research_md_exists requires research_artifact_abs "
                    f"(workflow={spec.name!r})"
                )
            _check_research_md_exists(research_artifact_abs)
        else:
            raise WorkflowError(
                f"unknown postcondition {name!r}",
                details={"name": name, "workflow": spec.name},
            )


def _read_text_utf8(path: Path, *, context: str) -> str:
    """Read file as UTF-8 or raise WorkflowError with cause attached (P7/P49)."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise WorkflowError(
            f"postcondition {context} non-utf-8",
            details={"path": str(path), "cause": str(e)},
        ) from e


def _check_product_md_exists(path: Path) -> None:
    if not path.is_file():
        raise WorkflowError(
            f"postcondition product_md_exists: missing file {path}",
            details={"path": str(path)},
        )
    text = _read_text_utf8(path, context="product_md")
    if not text.startswith("---"):
        raise WorkflowError(
            "postcondition product_md_exists: expected YAML frontmatter",
            details={"path": str(path)},
        )
    segments = text.split("---", 2)
    if len(segments) < _FRONT_MATTER_MIN_SEGMENTS:
        raise WorkflowError(
            "postcondition product_md_exists: malformed frontmatter",
            details={"path": str(path)},
        )
    try:
        front = yaml.safe_load(segments[1])
    except yaml.YAMLError as e:
        raise WorkflowError(
            "postcondition product_md frontmatter malformed",
            details={"path": str(path), "cause": str(e)},
        ) from e
    if not isinstance(front, dict) or front.get("kind") != "product_brief":
        raise WorkflowError(
            "postcondition product_md_exists: frontmatter kind must be product_brief",
            details={"path": str(path)},
        )
    body = segments[2].lstrip("\n")
    if not _H2_HEADING_RE.search(body):
        raise WorkflowError(
            "postcondition product_md_exists: markdown body must contain an H2 heading",
            details={"path": str(path)},
        )


def validate_research_md_text(text: str, *, source_label: str = "<in-memory>") -> None:
    """P4 (code review): validate the research artifact SHAPE without requiring disk I/O.

    Use this BEFORE the CLI writes + journals, so a malformed specialist body
    fails fast in memory instead of leaving an orphan ``artifact_written``
    journal entry pointing at an unshippable file.

    ``_REQUIRED_RESEARCH_FRONTMATTER_KEYS`` is enforced as a *subset* of the
    actual key set (D5 from the Story 2A.9 code review): /sdlc-verify
    (Story 2A.10) APPENDS ``verifications: [...]`` to this frontmatter and the
    postcondition must keep accepting verified artifacts.
    """
    if not text.startswith("---"):
        raise WorkflowError(
            "postcondition research_md_exists: expected YAML frontmatter",
            details={"path": source_label},
        )
    segments = text.split("---", 2)
    if len(segments) < _FRONT_MATTER_MIN_SEGMENTS:
        raise WorkflowError(
            "postcondition research_md_exists: malformed frontmatter",
            details={"path": source_label},
        )
    try:
        front = yaml.safe_load(segments[1])
    except yaml.YAMLError as e:
        raise WorkflowError(
            "postcondition research_md_exists: frontmatter malformed",
            details={"path": source_label, "cause": str(e)},
        ) from e
    if not isinstance(front, dict) or front.get("kind") != "research":
        raise WorkflowError(
            "postcondition research_md_exists: frontmatter kind must be research",
            details={"path": source_label},
        )
    actual = frozenset(front.keys())
    if not _REQUIRED_RESEARCH_FRONTMATTER_KEYS.issubset(actual):
        raise WorkflowError(
            "postcondition research_md_exists: missing required frontmatter keys",
            details={
                "path": source_label,
                "expected": sorted(_REQUIRED_RESEARCH_FRONTMATTER_KEYS),
                "actual": sorted(actual),
            },
        )
    body = segments[2].lstrip("\n")
    if not _H2_HEADING_RE.search(body):
        raise WorkflowError(
            "postcondition research_md_exists: markdown body must contain an H2 heading",
            details={"path": source_label},
        )


def _check_research_md_exists(path: Path) -> None:
    """Story 2A.9 — research artifact exists with YAML frontmatter + H2 body."""
    if not path.is_file():
        raise WorkflowError(
            f"postcondition research_md_exists: missing file {path}",
            details={"path": str(path)},
        )
    text = _read_text_utf8(path, context="research_md")
    validate_research_md_text(text, source_label=str(path))


def _check_product_md_frontmatter_keys(path: Path) -> None:
    """Enforce that PRODUCT.md frontmatter top-level keys match D3-A canonical set.

    Postcondition for Story 2A.8 (P55). Runs after the synthesizer-canonical write
    so the file under audit is the on-disk artifact the CLI committed.
    """
    if not path.is_file():
        raise WorkflowError(
            f"postcondition product_md_frontmatter_keys: missing file {path}",
            details={"path": str(path)},
        )
    text = _read_text_utf8(path, context="product_md_frontmatter_keys")
    if not text.startswith("---"):
        raise WorkflowError(
            "invariant violated: product_md_frontmatter_keys",
            details={
                "path": str(path),
                "reason": "expected YAML frontmatter",
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )
    segments = text.split("---", 2)
    if len(segments) < _FRONT_MATTER_MIN_SEGMENTS:
        raise WorkflowError(
            "invariant violated: product_md_frontmatter_keys",
            details={
                "path": str(path),
                "reason": "malformed frontmatter",
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )
    try:
        front = yaml.safe_load(segments[1])
    except yaml.YAMLError as e:
        raise WorkflowError(
            "invariant violated: product_md_frontmatter_keys",
            details={
                "path": str(path),
                "cause": str(e),
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        ) from e
    if not isinstance(front, dict):
        raise WorkflowError(
            "invariant violated: product_md_frontmatter_keys",
            details={
                "path": str(path),
                "reason": "frontmatter is not a mapping",
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )
    actual = frozenset(front.keys())
    if actual != _REQUIRED_PRODUCT_FRONTMATTER_KEYS:
        raise WorkflowError(
            "invariant violated: product_md_frontmatter_keys",
            details={
                "path": str(path),
                "expected": sorted(_REQUIRED_PRODUCT_FRONTMATTER_KEYS),
                "actual": sorted(actual),
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )


def _check_boundary_line_in_runs(runs_path: Path) -> None:
    if not runs_path.is_file():
        raise WorkflowError(
            "postcondition boundary_line_present_in_prompts: agent_runs file missing",
            details={"path": str(runs_path)},
        )
    text = _read_text_utf8(runs_path, context="agent_runs")
    rows_with_prompt = 0
    for i, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise WorkflowError(
                "postcondition agent_runs malformed",
                details={"line_index": i, "cause": str(e)},
            ) from e
        if not isinstance(row, dict):
            raise WorkflowError(
                "postcondition agent_runs row not a dict",
                details={"line_index": i, "type": type(row).__name__},
            )
        prompt = row.get("dispatch_prompt")
        if prompt is None:
            continue
        rows_with_prompt += 1
        _validate_boundary_block(
            prompt,
            line_index=i,
            specialist_name=row.get("specialist_name"),
        )
    if rows_with_prompt == 0:
        # Pure invariant violation (P6): no dispatch_prompt rows were recorded,
        # so the boundary-line invariant cannot be evaluated. This is a system
        # bug, not a user-fixable postcondition failure.
        raise WorkflowError(
            "invariant violated: boundary_line_present_in_prompts",
            details={
                "path": str(runs_path),
                "reason": "no dispatch_prompt rows recorded",
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )


def _validate_boundary_block(
    prompt: object,
    *,
    line_index: int,
    specialist_name: object,
) -> None:
    """Enforce <BOUNDARY>...</BOUNDARY> tag-block invariant (P59 / D6-B).

    Each recorded dispatch_prompt must contain exactly one ``<BOUNDARY>`` line and
    exactly one ``</BOUNDARY>`` line. The text between those tags must contain the
    canonical ``BOUNDARY_LINE`` constant, and ``BOUNDARY_LINE`` must not appear
    outside the tag block. Pure invariant — failure carries ERR_INVARIANT_VIOLATED.
    """
    if not isinstance(prompt, str):
        raise WorkflowError(
            "invariant violated: boundary_line_present_in_prompts",
            details={
                "line_index": line_index,
                "specialist_name": specialist_name,
                "reason": "dispatch_prompt is not a string",
                "type": type(prompt).__name__,
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )
    open_count = len(_BOUNDARY_OPEN_RE.findall(prompt))
    close_count = len(_BOUNDARY_CLOSE_RE.findall(prompt))
    if open_count != 1 or close_count != 1:
        raise WorkflowError(
            "invariant violated: boundary_line_present_in_prompts",
            details={
                "line_index": line_index,
                "specialist_name": specialist_name,
                "reason": "expected exactly one <BOUNDARY> and one </BOUNDARY> tag",
                "open_count": open_count,
                "close_count": close_count,
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )
    match = _BOUNDARY_BLOCK_RE.search(prompt)
    if match is None:
        raise WorkflowError(
            "invariant violated: boundary_line_present_in_prompts",
            details={
                "line_index": line_index,
                "specialist_name": specialist_name,
                "reason": "no <BOUNDARY>...</BOUNDARY> block found",
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )
    inside = match.group(1)
    if BOUNDARY_LINE not in inside:
        raise WorkflowError(
            "invariant violated: boundary_line_present_in_prompts",
            details={
                "line_index": line_index,
                "specialist_name": specialist_name,
                "reason": "BOUNDARY_LINE missing inside <BOUNDARY> block",
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )
    outside = prompt[: match.start()] + prompt[match.end() :]
    if BOUNDARY_LINE in outside:
        raise WorkflowError(
            "invariant violated: boundary_line_present_in_prompts",
            details={
                "line_index": line_index,
                "specialist_name": specialist_name,
                "reason": "BOUNDARY_LINE appears outside <BOUNDARY> block",
                "error_code": "ERR_INVARIANT_VIOLATED",
            },
        )


__all__: tuple[str, ...] = ("evaluate_postconditions",)
