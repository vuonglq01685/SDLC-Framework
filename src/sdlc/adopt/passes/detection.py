"""Pass 1 — detect pre-existing artifacts in a brownfield repo (Story 3.2, FR2).

`detect_existing` walks `root`, collects candidate artifacts by name/path pattern,
classifies each via content heuristics into the frozen `ArtifactKind` taxonomy with an
integer-percent `confidence` and a canonical `suggested_target`, and returns the
in-memory `list[DetectedArtifact]` that the driver (`adopt/driver.py`) writes into
`adopt-report.json` under `.claude/`.

Detection is READ-ONLY (NFR-REL-6): it performs zero writes — it only reads file names
and (for docs markdown) file content. The scan skips `.claude/` and `.git/`, and (D4)
any path matching `legacy_code_globs` (source code, not an SDLC artifact).

Boundary (scripts/module_boundary_table.py): `adopt/` has NO git grant and MUST NOT
import `cli/`. The 90-day recency signal (AC3) is therefore dependency-injected by the
`cli` layer as `git_signal` (a `{rel_posix_path: days_since_last_touch}` map), mirroring
Story 3.8's `legacy_code_globs` DI (`cli/break_.py` → `cli/_brownfield.classify_tdd_strategy`).
When the signal is absent, detection degrades gracefully (no recency boost, AC3).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from sdlc.adopt.passes import _classify
from sdlc.contracts.adopt_report import DetectedArtifact

# Directories never scanned: SDLC's own state + the git database (architecture.md, AC1/AC7).
_SKIP_DIRS: Final[frozenset[str]] = frozenset({".claude", ".git"})


def _safe_read_text(path: Path) -> str:
    """Read a candidate's text for content classification; empty string on any read error.

    Detection must never crash on an unreadable/binary candidate — a failed read just means
    "no content signal" → the file falls back to name-pattern / `unknown` classification.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _classify_candidate(
    abs_path: Path,
    rel_posix: str,
    git_signal: dict[str, int] | None,
) -> DetectedArtifact | None:
    """Classify one filesystem entry into a `DetectedArtifact`, or `None` if not a candidate."""
    name_match = _classify.classify_by_name(rel_posix)
    if name_match is not None:
        kind, confidence = name_match
    elif _classify.is_doc_markdown(rel_posix):
        kind, confidence = _classify.classify_markdown(_safe_read_text(abs_path))
    else:
        return None  # not an SDLC-shaped artifact

    confidence = _classify.apply_recency_boost(confidence, rel_posix, git_signal)
    return DetectedArtifact(
        path=rel_posix,
        kind=kind,
        confidence=confidence,
        suggested_target=_classify.suggested_target_for(kind),
    )


def detect_existing(
    root: Path,
    *,
    git_signal: dict[str, int] | None = None,
    legacy_code_globs: tuple[str, ...] = (),
) -> list[DetectedArtifact]:
    """Return pre-existing SDLC artifacts detected under ``root`` (Story 3.2 heuristics).

    Args:
        root: repository root to scan (read-only).
        git_signal: optional `{rel_posix_path: days_since_last_touch}` map injected by the
            `cli` layer (D2); recently-touched artifacts get a small confidence boost (AC3).
            Absent ⇒ no recency boost (graceful degradation).
        legacy_code_globs: optional source-code globs to exclude from detection (D4); a path
            matching any glob is source, not an SDLC artifact, so it is skipped.

    Returns an empty list on a greenfield-disguised repo (no SDLC-shaped artifacts, AC5);
    the `cli` layer emits the user-facing greenfield message when this is empty.
    """
    results: list[DetectedArtifact] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in place so os.walk never descends into them (AC1/AC7).
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in filenames:
            abs_path = Path(dirpath) / filename
            rel_posix = abs_path.relative_to(root).as_posix()
            if _classify.matches_legacy_glob(rel_posix, legacy_code_globs):
                continue
            artifact = _classify_candidate(abs_path, rel_posix, git_signal)
            if artifact is not None:
                results.append(artifact)
    # Deterministic order (sorted by path): os.walk yields entries in arbitrary OS-dependent
    # order, so sort here to make the written adopt-report.json reproducible across filesystems.
    return sorted(results, key=lambda a: a.path)
