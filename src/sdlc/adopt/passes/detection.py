"""Pass 1 — detect pre-existing artifacts in a brownfield repo (Story 3.1 seam).

The public name `detect_existing` is the stable seam (architecture.md:1069) that Story 3.2
implements with real filesystem-scan + content heuristics. In Story 3.1 it returns an empty
list — the `detected` shape is frozen here (`DetectedArtifact`), Pass 1's heuristics arrive
in 3.2.
"""

from __future__ import annotations

from pathlib import Path

from sdlc.contracts.adopt_report import DetectedArtifact


def detect_existing(root: Path) -> list[DetectedArtifact]:
    """Return artifacts detected under ``root`` (Story 3.2 heuristics; 3.1 returns ``[]``)."""
    return []
