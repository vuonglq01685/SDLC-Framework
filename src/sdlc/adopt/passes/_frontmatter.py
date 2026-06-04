"""Lenient YAML frontmatter reader for adopt Pass 3 (Story 3.4, D5(a), E).

``specialists/frontmatter`` raises on missing delimiters and lives outside ``adopt``'s
``depends_on`` grant — this tiny helper is inlined here for optional read-only frontmatter
extraction without widening the adopt boundary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_MIN_FRONTMATTER_DELIMS = 2


def read_lenient_frontmatter(path: Path) -> dict[str, object] | None:
    """Return the YAML mapping between the first two ``---`` lines, or None.

    Missing delimiters, empty blocks, and non-dict YAML all yield None (never raise).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.splitlines()
    delim_indices = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(delim_indices) < _MIN_FRONTMATTER_DELIMS:
        return None
    start, end = delim_indices[0] + 1, delim_indices[1]
    block = "\n".join(lines[start:end]).strip()
    if not block:
        return None
    try:
        loaded: Any = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict):
        return None
    return {str(k): v for k, v in loaded.items()}
