"""Pass 3 — stamp adopted artifacts as imported-from-existing (Story 3.1 seam).

The public name `mark_imported` is the stable seam (architecture.md:1069) that Story 3.4
implements (writes the `imported_from_existing` marker + journal kind). In Story 3.1 it is
a no-op so the three-pass orchestration can be exercised end-to-end.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sdlc.contracts.adopt_report import DetectedArtifact


def mark_imported(root: Path, detected: Sequence[DetectedArtifact]) -> None:
    """Stamp ``detected`` artifacts as imported (Story 3.4 implements; 3.1 no-op)."""
    return None
