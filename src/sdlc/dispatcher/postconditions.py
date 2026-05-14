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
from typing import cast

import yaml

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.prompts import BOUNDARY_LINE
from sdlc.errors import WorkflowError
from sdlc.ids.parsers import EPIC_ID_REGEX, STORY_ID_REGEX

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

_DRAFTED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_EPIC_JSON_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "id",
        "label",
        "priority",
        "dependencies",
        "ordering",
        "acceptance_criteria",
        "drafted_at",
        "drafted_by_specialist",
    }
)
_STORY_JSON_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "id",
        "epic_id",
        "seq",
        "label",
        "as_a",
        "i_want",
        "so_that",
        "given_when_then",
        "dependencies",
        "drafted_at",
        "drafted_by_specialist",
    }
)
_PRIORITY_VALUES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3"})
_EPIC_LABEL_MAX = 200
_EPIC_AC_MAX = 1000
_STORY_LABEL_MAX = 200
_STORY_AS_A_MAX = 200
_STORY_I_WANT_MAX = 500
_STORY_SO_THAT_MAX = 500
_STORY_SCENARIO_MAX = 8000


def _json_load_mapping(path: Path, *, label: str) -> dict[str, object]:
    text = _read_text_utf8(path, context=label)
    try:
        obj: object = json.loads(text)
    except json.JSONDecodeError as e:
        raise WorkflowError(
            f"postcondition {label}: invalid json",
            details={"path": str(path), "cause": str(e)},
        ) from e
    if not isinstance(obj, dict):
        raise WorkflowError(
            f"postcondition {label}: root must be a JSON object",
            details={"path": str(path), "type": type(obj).__name__},
        )
    return cast(dict[str, object], obj)


def _validate_epic_json_file(path: Path) -> None:  # noqa: C901, PLR0912
    """Shape-check one epic JSON file (Story 2A.11; mirrors ``_EpicEntry`` invariants)."""
    d = _json_load_mapping(path, label="all_epic_jsons_valid")
    if set(d.keys()) != _EPIC_JSON_KEYS:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: unexpected epic key set",
            details={"path": str(path), "keys": sorted(d.keys())},
        )
    if d.get("schema_version") != 1:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: schema_version must be 1",
            details={"path": str(path)},
        )
    eid = d.get("id")
    if not isinstance(eid, str) or EPIC_ID_REGEX.fullmatch(eid) is None:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: invalid epic id",
            details={"path": str(path), "id": eid},
        )
    label = d.get("label")
    if not isinstance(label, str) or not label or len(label) > _EPIC_LABEL_MAX:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: label invalid",
            details={"path": str(path)},
        )
    pri = d.get("priority")
    if not isinstance(pri, str) or pri not in _PRIORITY_VALUES:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: priority invalid",
            details={"path": str(path), "priority": pri},
        )
    deps = d.get("dependencies")
    if not isinstance(deps, list):
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: dependencies must be a list",
            details={"path": str(path)},
        )
    for dep in deps:
        if not isinstance(dep, str) or EPIC_ID_REGEX.fullmatch(dep) is None:
            raise WorkflowError(
                "postcondition all_epic_jsons_valid: invalid dependency id",
                details={"path": str(path), "dep": dep},
            )
    ordering = d.get("ordering")
    if not isinstance(ordering, int) or isinstance(ordering, bool) or ordering < 0:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: ordering must be non-negative int",
            details={"path": str(path), "ordering": ordering},
        )
    ac = d.get("acceptance_criteria")
    if not isinstance(ac, list) or len(ac) < 1:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: acceptance_criteria must be non-empty list",
            details={"path": str(path)},
        )
    for row in ac:
        if not isinstance(row, str) or len(row) < 1 or len(row) > _EPIC_AC_MAX:
            raise WorkflowError(
                "postcondition all_epic_jsons_valid: acceptance_criteria entry invalid",
                details={"path": str(path)},
            )
    drafted = d.get("drafted_at")
    if not isinstance(drafted, str) or _DRAFTED_AT_RE.fullmatch(drafted) is None:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: drafted_at invalid",
            details={"path": str(path)},
        )
    dbs = d.get("drafted_by_specialist")
    if not isinstance(dbs, str) or not dbs:
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: drafted_by_specialist invalid",
            details={"path": str(path)},
        )


def _validate_story_json_file(path: Path) -> None:  # noqa: C901, PLR0912
    """Shape-check one story JSON file (Story 2A.11; mirrors ``_StoryEntry`` invariants)."""
    d = _json_load_mapping(path, label="all_story_jsons_valid")
    if set(d.keys()) != _STORY_JSON_KEYS:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: unexpected story key set",
            details={"path": str(path), "keys": sorted(d.keys())},
        )
    if d.get("schema_version") != 1:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: schema_version must be 1",
            details={"path": str(path)},
        )
    eid = d.get("id")
    if not isinstance(eid, str) or STORY_ID_REGEX.fullmatch(eid) is None:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: invalid story id",
            details={"path": str(path), "id": eid},
        )
    epic_id = d.get("epic_id")
    if not isinstance(epic_id, str) or EPIC_ID_REGEX.fullmatch(epic_id) is None:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: invalid epic_id",
            details={"path": str(path), "epic_id": epic_id},
        )
    if not eid.startswith(f"{epic_id}-S"):
        raise WorkflowError(
            "postcondition all_story_jsons_valid: story id / epic_id mismatch",
            details={"path": str(path)},
        )
    seq = d.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: seq invalid",
            details={"path": str(path), "seq": seq},
        )
    m = re.match(rf"^{re.escape(epic_id)}-S(\d{{2}})-", eid)
    if m is None or int(m.group(1)) != seq:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: seq does not match id",
            details={"path": str(path), "id": eid, "seq": seq},
        )
    for text_key, maxlen in (
        ("label", _STORY_LABEL_MAX),
        ("as_a", _STORY_AS_A_MAX),
        ("i_want", _STORY_I_WANT_MAX),
        ("so_that", _STORY_SO_THAT_MAX),
    ):
        val = d.get(text_key)
        if not isinstance(val, str) or len(val) < 1 or len(val) > maxlen:
            raise WorkflowError(
                f"postcondition all_story_jsons_valid: {text_key} invalid",
                details={"path": str(path)},
            )
    gwt = d.get("given_when_then")
    if not isinstance(gwt, list) or len(gwt) < 1:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: given_when_then invalid",
            details={"path": str(path)},
        )
    for scen in gwt:
        if not isinstance(scen, str) or len(scen) < 1 or len(scen) > _STORY_SCENARIO_MAX:
            raise WorkflowError(
                "postcondition all_story_jsons_valid: scenario invalid",
                details={"path": str(path)},
            )
    deps = d.get("dependencies")
    if not isinstance(deps, list):
        raise WorkflowError(
            "postcondition all_story_jsons_valid: dependencies must be a list",
            details={"path": str(path)},
        )
    for dep in deps:
        if not isinstance(dep, str) or STORY_ID_REGEX.fullmatch(dep) is None:
            raise WorkflowError(
                "postcondition all_story_jsons_valid: invalid story dependency id",
                details={"path": str(path), "dep": dep},
            )
    drafted = d.get("drafted_at")
    if not isinstance(drafted, str) or _DRAFTED_AT_RE.fullmatch(drafted) is None:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: drafted_at invalid",
            details={"path": str(path)},
        )
    dbs = d.get("drafted_by_specialist")
    if not isinstance(dbs, str) or not dbs:
        raise WorkflowError(
            "postcondition all_story_jsons_valid: drafted_by_specialist invalid",
            details={"path": str(path)},
        )


def _epic_files(epics_dir: Path) -> list[Path]:
    """Glob *.json filtered to filenames whose stem matches ``EPIC_ID_REGEX``.

    Patch #15: stray ``notes.json`` etc. no longer trip the postcondition.
    """
    return sorted(
        p for p in epics_dir.glob("*.json") if EPIC_ID_REGEX.fullmatch(p.stem) is not None
    )


def _story_files(stories_dir: Path) -> list[Path]:
    """Glob *.json filtered to filenames whose stem matches ``STORY_ID_REGEX``."""
    return sorted(
        p for p in stories_dir.glob("*.json") if STORY_ID_REGEX.fullmatch(p.stem) is not None
    )


def _check_epics_dir_non_empty(epics_dir: Path) -> None:
    if not epics_dir.is_dir():
        raise WorkflowError(
            "postcondition epics_dir_non_empty: directory missing",
            details={"path": str(epics_dir)},
        )
    if not _epic_files(epics_dir):
        raise WorkflowError(
            "postcondition epics_dir_non_empty: no epic json files",
            details={"path": str(epics_dir)},
        )


def _check_all_epic_jsons_valid(epics_dir: Path) -> None:
    if not epics_dir.is_dir():
        raise WorkflowError(
            "postcondition all_epic_jsons_valid: directory missing",
            details={"path": str(epics_dir)},
        )
    for path in _epic_files(epics_dir):
        _validate_epic_json_file(path)


def _check_stories_dir_non_empty(stories_dir: Path) -> None:
    if not stories_dir.is_dir():
        raise WorkflowError(
            "postcondition stories_dir_non_empty: directory missing",
            details={"path": str(stories_dir)},
        )
    if not _story_files(stories_dir):
        raise WorkflowError(
            "postcondition stories_dir_non_empty: no story json files",
            details={"path": str(stories_dir)},
        )


def _check_all_story_jsons_valid(stories_dir: Path) -> None:
    if not stories_dir.is_dir():
        raise WorkflowError(
            "postcondition all_story_jsons_valid: directory missing",
            details={"path": str(stories_dir)},
        )
    for path in _story_files(stories_dir):
        _validate_story_json_file(path)


def _check_ux_dir_non_empty(ux_dir: Path) -> None:
    if not ux_dir.is_dir():
        raise WorkflowError(
            "postcondition ux_dir_non_empty: directory missing",
            details={"path": str(ux_dir)},
        )
    if not any(ux_dir.glob("*.md")):
        raise WorkflowError(
            "postcondition ux_dir_non_empty: no .md files in UX directory",
            details={"path": str(ux_dir)},
        )


def evaluate_postconditions(  # noqa: C901, PLR0912
    spec: WorkflowSpec,
    *,
    repo_root: Path,
    agent_runs_path: Path,
    product_rel: str = "01-Requirement/01-PRODUCT.md",
    research_artifact_abs: Path | None = None,
    epics_dir_abs: Path | None = None,
    stories_subdir_abs: Path | None = None,
    ux_dir_abs: Path | None = None,
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
        elif name == "epics_dir_non_empty":
            if epics_dir_abs is None:
                raise RuntimeError(
                    f"postcondition epics_dir_non_empty requires epics_dir_abs "
                    f"(workflow={spec.name!r})"
                )
            _check_epics_dir_non_empty(epics_dir_abs)
        elif name == "all_epic_jsons_valid":
            if epics_dir_abs is None:
                raise RuntimeError(
                    f"postcondition all_epic_jsons_valid requires epics_dir_abs "
                    f"(workflow={spec.name!r})"
                )
            _check_all_epic_jsons_valid(epics_dir_abs)
        elif name == "stories_dir_non_empty":
            if stories_subdir_abs is None:
                raise RuntimeError(
                    f"postcondition stories_dir_non_empty requires stories_subdir_abs "
                    f"(workflow={spec.name!r})"
                )
            _check_stories_dir_non_empty(stories_subdir_abs)
        elif name == "all_story_jsons_valid":
            if stories_subdir_abs is None:
                raise RuntimeError(
                    f"postcondition all_story_jsons_valid requires stories_subdir_abs "
                    f"(workflow={spec.name!r})"
                )
            _check_all_story_jsons_valid(stories_subdir_abs)
        elif name == "ux_dir_non_empty":
            if ux_dir_abs is None:
                raise RuntimeError(
                    f"postcondition ux_dir_non_empty requires ux_dir_abs (workflow={spec.name!r})"
                )
            _check_ux_dir_non_empty(ux_dir_abs)
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
