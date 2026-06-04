"""Read-only helpers for ``adopted-symlinks.json`` (Story 3.4 consuming side)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from sdlc.contracts.adopted_symlinks import AdoptedSymlinks

_MANIFEST_REL: Final[str] = ".claude/state/adopted-symlinks.json"


def load_adopted_target_sources(root: Path) -> dict[str, str]:
    """Return ``{canonical target: original source}`` for accepted adopt symlinks, or empty.

    The source is needed by the verify/signoff consuming side to bind a known-adopted
    symlink to the EXACT path the manifest recorded (defense-in-depth: membership alone
    authorizes the slot *name*, the source binding authorizes the *destination*).
    """
    manifest_path = root / _MANIFEST_REL
    if not manifest_path.exists():
        return {}
    try:
        manifest = AdoptedSymlinks.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {m.target: m.source for m in manifest.mappings}


def load_adopted_targets(root: Path) -> frozenset[str]:
    """Return repo-relative POSIX targets of accepted adopt symlinks, or empty."""
    return frozenset(load_adopted_target_sources(root))
