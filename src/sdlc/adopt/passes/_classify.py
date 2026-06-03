"""Classification heuristics for Pass 1 detection (Story 3.2, D1/D3).

Pure, side-effect-free helpers that map a candidate path + content to an
``(ArtifactKind, confidence)`` pair and a canonical ``suggested_target``. The
signature table (D3) and the target mapping (D1) are ratified in the Story 3.2
PR Change Log and frozen by the golden corpus (AC6).

Boundary note: ``adopt/`` MUST NOT import ``cli/`` (architecture.md:1084), so the
``**``-aware glob matcher is a LOCAL copy of the segment-aware matcher that also
lives in ``cli/_brownfield`` / ``dispatcher/_panel_helpers`` — the house pattern
keeps one matcher per layer rather than coupling layers (``cli/_brownfield.py:8-12``).
"""

from __future__ import annotations

import fnmatch
from typing import Final

from sdlc.contracts.adopt_report import ArtifactKind

# ---------------------------------------------------------------------------
# Name-pattern tables (AC1)
# ---------------------------------------------------------------------------

_README_NAMES: Final[frozenset[str]] = frozenset({"readme.md", "readme.rst", "readme.markdown"})
_BUILD_FILE_NAMES: Final[frozenset[str]] = frozenset(
    {"pom.xml", "pyproject.toml", "package.json", "go.mod", "build.gradle", "build.gradle.kts"}
)
_DOC_MD_SUFFIXES: Final[tuple[str, ...]] = (".md", ".rst", ".markdown")
_WORKFLOW_DIR_SEGMENTS: Final[tuple[str, str]] = (".github", "workflows")
_WORKFLOW_SUFFIXES: Final[tuple[str, ...]] = (".yml", ".yaml")

# ---------------------------------------------------------------------------
# Content-signature table (D3) — lowercased substrings, checked in priority order
# ---------------------------------------------------------------------------

_ARCH_SIGS: Final[tuple[str, ...]] = (
    "c4 context",
    "c4 model",
    "c4 diagram",
    "adr-",
    "adr ",
    "architecture decision",
    "component diagram",
    "system design",
)
_PRD_SIGS: Final[tuple[str, ...]] = (
    "product requirements",
    "user stories",
    "user story",
    "epics",
)
_RUNBOOK_SIGS: Final[tuple[str, ...]] = (
    "runbook",
    "on-call",
    "oncall",
    "incident",
    "escalation",
    "sla",
)
_RESEARCH_SIGS: Final[tuple[str, ...]] = (
    "research",
    "investigation",
    "findings",
    "analysis",
)

# ---------------------------------------------------------------------------
# Confidence scores (int percent, AC4 binding correction — never float)
# ---------------------------------------------------------------------------

_CONF_README: Final[int] = 90
_CONF_CI: Final[int] = 95
_CONF_DOCKERFILE: Final[int] = 95
_CONF_BUILD: Final[int] = 95
_CONF_ARCH: Final[int] = 85
_CONF_PRD: Final[int] = 80
_CONF_RESEARCH: Final[int] = 75
_CONF_RUNBOOK: Final[int] = 75
_CONF_UNKNOWN: Final[int] = 40

_RECENCY_BOOST: Final[int] = 5
_RECENCY_DAYS: Final[int] = 90
_MAX_CONF: Final[int] = 100

# ---------------------------------------------------------------------------
# D1 — suggested_target mapping (only 3 kinds are doc-blessed; rest detect-only)
# ---------------------------------------------------------------------------

_SUGGESTED_TARGET: Final[dict[str, str]] = {
    "prd": "01-Requirement/01-PRODUCT.md",
    "architecture": "02-Architecture/02-System/ARCHITECTURE.md",
    "research": "01-Requirement/02-Research/",
}


def suggested_target_for(kind: ArtifactKind) -> str:
    """Return the canonical SDLC slot for ``kind``, or ``""`` for detect-only kinds (D1)."""
    return _SUGGESTED_TARGET.get(kind, "")


# ---------------------------------------------------------------------------
# Name-pattern classification
# ---------------------------------------------------------------------------


def _basename(rel_posix: str) -> str:
    return rel_posix.rsplit("/", 1)[-1]


def _is_ci_workflow(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    name = parts[-1].lower()
    if not name.endswith(_WORKFLOW_SUFFIXES):
        return False
    # Must live under a `.github/workflows/` directory (contiguous segments).
    dir_parts = parts[:-1]
    for i in range(len(dir_parts) - 1):
        if (dir_parts[i], dir_parts[i + 1]) == _WORKFLOW_DIR_SEGMENTS:
            return True
    return False


def _is_dockerfile(name_lower: str) -> bool:
    return (
        name_lower == "dockerfile"
        or name_lower.startswith("dockerfile.")
        or name_lower.endswith(".dockerfile")
    )


def classify_by_name(rel_posix: str) -> tuple[ArtifactKind, int] | None:
    """Classify a candidate by name/path pattern alone, or ``None`` if not a name match."""
    name_lower = _basename(rel_posix).lower()
    if name_lower in _README_NAMES:
        return "readme", _CONF_README
    if _is_ci_workflow(rel_posix):
        return "ci-workflow", _CONF_CI
    if _is_dockerfile(name_lower):
        return "dockerfile", _CONF_DOCKERFILE
    if name_lower in _BUILD_FILE_NAMES:
        return "build-file", _CONF_BUILD
    return None


# ---------------------------------------------------------------------------
# Markdown content classification (AC2)
# ---------------------------------------------------------------------------


def is_doc_markdown(rel_posix: str) -> bool:
    """True if ``rel_posix`` is a markdown file under a ``docs/`` directory (AC1)."""
    parts = rel_posix.split("/")
    if "docs" not in parts[:-1]:
        return False
    return rel_posix.lower().endswith(_DOC_MD_SUFFIXES)


def _matches_any(content_lower: str, signatures: tuple[str, ...]) -> bool:
    return any(sig in content_lower for sig in signatures)


def classify_markdown(content: str) -> tuple[ArtifactKind, int]:
    """Classify a docs markdown file by content signature (D3 table, priority order)."""
    low = content.lower()
    if _matches_any(low, _ARCH_SIGS):
        return "architecture", _CONF_ARCH
    if _matches_any(low, _PRD_SIGS):
        return "prd", _CONF_PRD
    if _matches_any(low, _RUNBOOK_SIGS):
        return "runbook", _CONF_RUNBOOK
    if _matches_any(low, _RESEARCH_SIGS):
        return "research", _CONF_RESEARCH
    return "unknown", _CONF_UNKNOWN


def apply_recency_boost(confidence: int, rel_posix: str, git_signal: dict[str, int] | None) -> int:
    """Add a recency boost (capped at 100) if the path was touched within 90 days (D2/AC3).

    Graceful degradation (AC3): when ``git_signal`` is ``None`` (no signal — non-git repo,
    git error, or not threaded) OR the path is absent from the map OR the file was last
    touched > 90 days ago, no boost is applied ("and/or no recency boost" license).
    """
    if git_signal is None:
        return confidence
    days = git_signal.get(rel_posix)
    if days is not None and days <= _RECENCY_DAYS:
        return min(_MAX_CONF, confidence + _RECENCY_BOOST)
    return confidence


# ---------------------------------------------------------------------------
# legacy_code_globs exclusion (D4) — LOCAL segment-aware `**` matcher
# ---------------------------------------------------------------------------


def _canonical_glob(pattern: str) -> str:
    p = pattern.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    if p.endswith("/"):
        return p.rstrip("/") + "/**"
    return p


def _match_segments(path_parts: list[str], pat_parts: list[str]) -> bool:
    if not pat_parts:
        return not path_parts
    head = pat_parts[0]
    if head == "**":
        return any(
            _match_segments(path_parts[i:], pat_parts[1:]) for i in range(len(path_parts) + 1)
        )
    if not path_parts:
        return False
    if fnmatch.fnmatchcase(path_parts[0], head):
        return _match_segments(path_parts[1:], pat_parts[1:])
    return False


def matches_legacy_glob(rel_posix: str, legacy_code_globs: tuple[str, ...]) -> bool:
    """True if ``rel_posix`` matches any ``legacy_code_globs`` entry (segment-aware ``**``)."""
    if not legacy_code_globs:
        return False
    path_parts = rel_posix.split("/")
    return any(
        _match_segments(path_parts, _canonical_glob(g).split("/")) for g in legacy_code_globs
    )
