"""Shared fixtures for Pass 2 symlink-offer unit tests (Story 3.3)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt mode is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.passes.symlink_offer import SymlinkDecision
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks
from sdlc.contracts.journal_entry import JournalEntry

pytestmark = pytest.mark.unit

MANIFEST_REL = ".claude/state/adopted-symlinks.json"
JOURNAL_REL = ".claude/state/journal.log"
ARCH_TARGET = "02-Architecture/02-System/ARCHITECTURE.md"


def scaffold(tmp_path: Path) -> Path:
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "journal.log").touch()
    return tmp_path


def artifact(
    path: str = "docs/architecture-2024.md",
    kind: str = "architecture",
    confidence: int = 85,
    suggested_target: str = ARCH_TARGET,
) -> DetectedArtifact:
    return DetectedArtifact(
        path=path, kind=kind, confidence=confidence, suggested_target=suggested_target
    )


def write_source(root: Path, rel: str, body: str = "# Architecture\n") -> Path:
    src = root / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(body, encoding="utf-8")
    return src


def accept_all(_art: DetectedArtifact, target: str) -> SymlinkDecision:
    return SymlinkDecision(accept=True, target=target)


def reject_all(_art: DetectedArtifact, target: str) -> SymlinkDecision:
    return SymlinkDecision(accept=False, target=target)


def read_manifest(root: Path) -> AdoptedSymlinks:
    return AdoptedSymlinks.model_validate_json((root / MANIFEST_REL).read_text(encoding="utf-8"))


def journal_entries(root: Path) -> list[JournalEntry]:
    text = (root / JOURNAL_REL).read_text(encoding="utf-8")
    return [JournalEntry.model_validate_json(ln) for ln in text.splitlines() if ln.strip()]


def file_sha256(path: Path) -> str:
    """Content digest of a regular file (NFR-REL-6 source-byte-identity assertions)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
