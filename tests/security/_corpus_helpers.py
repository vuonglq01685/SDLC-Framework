"""Shared helpers for the Story 2B.4 prompt-injection corpus harness.

Extracted from ``test_prompt_injection_corpus.py`` so the harness file stays
within the Architecture §765 / NFR-MAINT-3 LOC cap (400 LOC raw). All public
names here are imported by the test module.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.prompts import BOUNDARY_LINE, phase1_prompt_builder
from sdlc.errors import WorkflowError
from sdlc.specialists.frontmatter import Specialist
from sdlc.workflows import load_workflow
from sdlc.workflows.static_check import validate_workflow

# --- corpus layout -----------------------------------------------------------

CORPUS_ROOT: Final[Path] = Path(__file__).parent / "corpus"
USER_TEXT_DIR: Final[Path] = CORPUS_ROOT / "user_text"
WORKFLOW_DIR: Final[Path] = CORPUS_ROOT / "workflow_yaml"

# --- disposition values (single source — README must mirror; P25) -----------

DISPOSITION_BOUNDARY: Final[str] = "boundary-wrapped"
DISPOSITION_REJECTED: Final[str] = "rejected-at-validation"
ALL_DISPOSITIONS: Final[frozenset[str]] = frozenset({DISPOSITION_BOUNDARY, DISPOSITION_REJECTED})

# --- category taxonomy (AC1; epic _bmad-output/.../epics.md:1531-1557) ------

# 10 attack categories named in the epic AC + 1 benign negative-control = 11
# REQUIRED. ``boundary_smuggling`` is a meta-category that exercises
# ``_validate_idea_text`` rejection paths — allowed but not in the AC1 list.
REQUIRED_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "instruction_override",
        "role_flip",
        "system_prompt_leak",
        "tool_invocation",
        "json_smuggling",
        "base64_directive",
        "rot13_obfuscation",
        "multilingual",
        "url_exfiltration",
        "command_substitution",
        "benign",
    }
)
OPTIONAL_CATEGORIES: Final[frozenset[str]] = frozenset({"boundary_smuggling"})
ALL_CATEGORIES: Final[frozenset[str]] = REQUIRED_CATEGORIES | OPTIONAL_CATEGORIES

# --- rejection-reason taxonomy (D1-P; src/sdlc/dispatcher/prompts.py) -------

# Mapping from declared ``# expected_reason:`` metadata to a substring asserted
# on the resulting WorkflowError message. Sources: rejection sites inside
# ``_validate_idea_text`` and its helpers.
REJECTION_REASON_PATTERNS: Final[dict[str, str]] = {
    "boundary_marker": "boundary marker",
    "envelope_fragment": "envelope-breaking tag fragment",
    "control_char": "control characters",
    "non_empty": "non-empty",
    "too_long": "too long",
}

# --- workflow vector taxonomy (D2-P; PRD §354-355 / AC2) --------------------

VECTOR_INSTRUCTION_SHAPE: Final[str] = "instruction_shape"
VECTOR_PHANTOM_AGENT: Final[str] = "phantom_agent"
VECTOR_GLOB_OVERLAP: Final[str] = "glob_overlap"
VECTOR_SPECIALIST_REDIRECTION: Final[str] = "specialist_redirection"
REQUIRED_VECTORS: Final[frozenset[str]] = frozenset(
    {
        VECTOR_INSTRUCTION_SHAPE,
        VECTOR_PHANTOM_AGENT,
        VECTOR_GLOB_OVERLAP,
        VECTOR_SPECIALIST_REDIRECTION,
    }
)

REJECTOR_LOADER: Final[str] = "loader"
REJECTOR_STATIC: Final[str] = "static_check"
ALL_REJECTORS: Final[frozenset[str]] = frozenset({REJECTOR_LOADER, REJECTOR_STATIC})

# --- parser ------------------------------------------------------------------

# Lowercase ASCII metadata keys only (P18). Value captured non-greedy so
# trailing whitespace is excluded.
META_LINE_RE: Final[re.Pattern[str]] = re.compile(r"^#\s*([a-z][a-z0-9_]*):\s*(\S.*?)\s*$")

# Bare tags appear inside the boundary-block descriptive text AND in the
# user envelope itself; the newline-anchored envelope is unique to the envelope.
USER_IDEA_OPEN_TAG: Final[str] = "<USER_IDEA>"
USER_IDEA_CLOSE_TAG: Final[str] = "</USER_IDEA>"
USER_IDEA_ENVELOPE_OPEN: Final[str] = USER_IDEA_OPEN_TAG + "\n"
USER_IDEA_ENVELOPE_CLOSE: Final[str] = "\n" + USER_IDEA_CLOSE_TAG


# --- discovery (P11/P12/P13: filter dotfiles, symlinks, non-files) ----------


def discover_user_text_paths() -> list[Path]:
    """Discover user-text corpus files — filter dotfiles, symlinks, non-files."""
    return sorted(
        p
        for p in USER_TEXT_DIR.glob("*.txt")
        if p.is_file() and not p.is_symlink() and not p.name.startswith(".")
    )


def discover_workflow_paths() -> list[Path]:
    """Discover workflow-YAML corpus files — same filters as user-text discovery."""
    return sorted(
        p
        for p in WORKFLOW_DIR.glob("*.yaml")
        if p.is_file() and not p.is_symlink() and not p.name.startswith(".")
    )


# --- parsers + loaders -------------------------------------------------------


def parse_corpus_metadata(raw: str) -> tuple[dict[str, str], str]:  # noqa: C901
    """Parse ``# key: value`` header lines, optional pre-body ``#`` comments, ``---`` separator.

    P17/P18/P19:
      - once ``in_body=True``, never re-parse metadata or separator;
      - reject duplicate metadata keys;
      - skip pre-separator ``#`` lines that don't match the regex (treat as comments)
        instead of silently absorbing them into the payload.
    """
    meta: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False
    for line in raw.splitlines():
        if not in_body:
            match = META_LINE_RE.match(line)
            if match:
                key, value = match.group(1), match.group(2).strip()
                if key in meta:
                    raise ValueError(f"duplicate metadata key {key!r}")
                if not value:
                    raise ValueError(f"empty metadata value for key {key!r}")
                meta[key] = value
                continue
            if line.strip() == "---":
                in_body = True
                continue
            if line.strip() == "":
                continue
            if line.startswith("#"):
                # Pre-body comment line that did not match key:value shape.
                continue
            in_body = True
            body_lines.append(line)
            continue
        body_lines.append(line)
    return meta, "\n".join(body_lines).strip("\n")


def load_user_text_case(path: Path) -> tuple[dict[str, str], str]:  # noqa: C901
    """Load + validate metadata and payload for a user-text corpus file.

    P14: convert UnicodeDecodeError to ValueError with file context.
    P20: require non-empty payload for ALL dispositions.
    P21: validate category against the all-categories allow-list.
    D1-P: rejected-at-validation must declare ``# expected_reason:``.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: corpus file must be UTF-8 ({exc})") from exc
    meta, payload = parse_corpus_metadata(raw)
    if "category" not in meta:
        raise ValueError(f"{path}: missing # category: metadata")
    if "expected_disposition" not in meta:
        raise ValueError(f"{path}: missing # expected_disposition: metadata")
    category = meta["category"]
    if category not in ALL_CATEGORIES:
        raise ValueError(f"{path}: unknown category {category!r}; allowed={sorted(ALL_CATEGORIES)}")
    disposition = meta["expected_disposition"]
    if disposition not in ALL_DISPOSITIONS:
        raise ValueError(f"{path}: unknown expected_disposition {disposition!r}")
    if not payload:
        raise ValueError(f"{path}: empty payload not allowed")
    if disposition == DISPOSITION_REJECTED:
        reason = meta.get("expected_reason")
        if reason is None or reason not in REJECTION_REASON_PATTERNS:
            raise ValueError(
                f"{path}: rejected-at-validation must declare "
                f"# expected_reason: <key> in {sorted(REJECTION_REASON_PATTERNS)}"
            )
    return meta, payload


def load_workflow_case(path: Path) -> dict[str, str]:
    """Parse leading ``# key: value`` comment block from a workflow YAML (D2-P)."""
    meta: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if not line.lstrip().startswith("#"):
            break
        match = META_LINE_RE.match(line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            if key in meta:
                raise ValueError(f"{path}: duplicate metadata key {key!r}")
            meta[key] = value
    rejector = meta.get("expected_rejector")
    if rejector not in ALL_REJECTORS:
        raise ValueError(
            f"{path}: workflow YAML must declare "
            f"# expected_rejector: loader|static_check (got {rejector!r})"
        )
    vector = meta.get("expected_vector")
    if vector not in REQUIRED_VECTORS:
        raise ValueError(
            f"{path}: workflow YAML must declare "
            f"# expected_vector: <key> in {sorted(REQUIRED_VECTORS)} (got {vector!r})"
        )
    return meta


# --- workflow spec / specialist fixtures (CR2B4-W5 tracks refactor debt) ----


def sdlc_start_spec() -> WorkflowSpec:
    """Construct a minimal valid Phase-1 WorkflowSpec for prompt construction."""
    return WorkflowSpec(
        schema_version=1,
        name="phase1-product-discovery",
        slash_command="/sdlc-start",
        primary_agent="product-strategist",
        parallel_agents=("technical-researcher", "devil-advocate"),
        synthesizer_agent="requirement-synthesizer",
        postconditions=(),
        write_globs={"product-strategist": ("01-Requirement/01-PRODUCT.md",)},
    )


def product_strategist() -> Specialist:
    """Construct the Phase-1 primary specialist used by the corpus harness."""
    fm = SpecialistFrontmatter(
        schema_version=1,
        name="product-strategist",
        title="Product Strategist",
        icon="🎯",
        model="sonnet",
        description="Strategy.",
        write_globs=("01-Requirement/01-PRODUCT.md",),
    )
    return Specialist(
        frontmatter=fm,
        body="Synthesize a product brief.",
        source_path=Path(__file__),
    )


def build_start_prompt(idea_text: str) -> str:
    """Render the ``/sdlc-start`` Phase-1 prompt for ``idea_text`` (primary role)."""
    return phase1_prompt_builder(
        product_strategist(),
        sdlc_start_spec(),
        idea_text=idea_text,
        role="primary",
    )


# --- boundary assertion (P9 tightened) --------------------------------------


def assert_boundary_before_user_idea(prompt: str, idea_text: str) -> None:
    """BOUNDARY_LINE must appear EXACTLY ONCE in the prefix before a SINGLE envelope.

    P9 tightening:
      - exactly one ``<USER_IDEA>\\n`` open AND one ``\\n</USER_IDEA>`` close;
      - payload appears INSIDE the envelope, not just somewhere in the prompt;
      - BOUNDARY_LINE occurs exactly once in the prefix (smuggling a second
        BOUNDARY_LINE through user text must not pass).
    """
    open_count = prompt.count(USER_IDEA_ENVELOPE_OPEN)
    close_count = prompt.count(USER_IDEA_ENVELOPE_CLOSE)
    assert open_count == 1, (
        f"expected exactly one <USER_IDEA> envelope (newline-anchored), got {open_count}"
    )
    assert close_count == 1, (
        f"expected exactly one </USER_IDEA> envelope (newline-anchored), got {close_count}"
    )
    open_idx = prompt.find(USER_IDEA_ENVELOPE_OPEN)
    close_idx = prompt.find(USER_IDEA_ENVELOPE_CLOSE)
    assert open_idx < close_idx, "envelope close must follow open"
    envelope_body = prompt[open_idx + len(USER_IDEA_ENVELOPE_OPEN) : close_idx]
    assert idea_text in envelope_body, (
        "user idea must appear INSIDE <USER_IDEA>...</USER_IDEA> envelope"
    )
    prefix = prompt[:open_idx]
    boundary_count = prefix.count(BOUNDARY_LINE)
    assert boundary_count == 1, (
        f"BOUNDARY_LINE must appear EXACTLY ONCE in the prompt prefix before "
        f"<USER_IDEA>; got {boundary_count} occurrences"
    )


# --- workflow rejection helpers (D2-P split) --------------------------------


def assert_workflow_loader_rejects(path: Path, *, vector: str) -> WorkflowError:
    """Loader-side rejection: ``load_workflow`` itself raises ``WorkflowError``."""
    with pytest.raises(WorkflowError) as exc_info:
        load_workflow(path)
    assert isinstance(exc_info.value, WorkflowError), (
        f"{path.name}: vector={vector} must raise WorkflowError at loader"
    )
    return exc_info.value


def assert_workflow_static_check_rejects(path: Path, *, vector: str) -> WorkflowError:
    """Static-check rejection: loader succeeds, ``validate_workflow`` raises.

    Also asserts that ``load_workflow`` itself does NOT raise — the layer split
    is part of the contract so a future loader-side rule shadowing static_check
    is caught as a regression.
    """
    try:
        spec = load_workflow(path)
    except WorkflowError as exc:
        pytest.fail(
            f"{path.name}: vector={vector} expected static_check rejection but "
            f"loader rejected first: {exc!s}"
        )
    with pytest.raises(WorkflowError) as exc_info:
        validate_workflow(spec)
    return exc_info.value


def assert_workflow_rejected_per_metadata(path: Path) -> WorkflowError:
    """Dispatch to the layer declared in ``# expected_rejector:`` metadata."""
    meta = load_workflow_case(path)
    if meta["expected_rejector"] == REJECTOR_LOADER:
        return assert_workflow_loader_rejects(path, vector=meta["expected_vector"])
    return assert_workflow_static_check_rejects(path, vector=meta["expected_vector"])
