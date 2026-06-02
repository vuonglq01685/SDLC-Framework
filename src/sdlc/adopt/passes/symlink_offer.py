"""Pass 2 — offer to symlink detected artifacts into the canonical layout (Story 3.1 seam).

The public name `offer_symlinks` is the stable seam (architecture.md:1069) that Story 3.3
implements (interactive symlink offer + `adopted-symlinks.json` tracking, POSIX-only per
ADR-034). In Story 3.1 it is a no-op so the orchestrator ordering can be exercised.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sdlc.contracts.adopt_report import DetectedArtifact


def offer_symlinks(root: Path, detected: Sequence[DetectedArtifact]) -> None:
    """Offer symlinks for ``detected`` artifacts (Story 3.3 implements; 3.1 no-op)."""
    return None
