"""Pass 3 imported-metadata sidecar helpers (Story 3.4, D2(a)).

Not a frozen wire-format contract (ADR-024). Journal ``imported_from_existing`` events are
the audit source of truth; ``.claude/state/imported-metadata/<artifact-id>.yaml`` is a
derived cache rebuildable from the journal (mirrors ``adopted-symlinks.json`` stance in 3.3).
"""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import StringConstraints

from sdlc.contracts._strict_model import StrictModel
from sdlc.contracts.adopt_report import _RFC3339_UTC, ArtifactKind

_log = logging.getLogger(__name__)

_MARKER: Literal["imported-from-existing"] = "imported-from-existing"
_METADATA_DIR_REL = ".claude/state/imported-metadata"
_MAX_ARTIFACT_ID_LEN = 200


def artifact_id_for_target(target: str) -> str:
    """Deterministic filesystem-safe slug of a repo-relative POSIX target (D3(a))."""
    slug = target.replace("/", "__")
    for ch in (":", " ", "\0", "<", ">", "|", '"', "*", "?"):
        slug = slug.replace(ch, "_")
    if len(slug) > _MAX_ARTIFACT_ID_LEN:
        slug = slug[:_MAX_ARTIFACT_ID_LEN]
    return slug


class ImportedMetadataRecord(StrictModel):
    """External metadata for one adopted symlink (source bytes never modified)."""

    source: str
    target: str
    kind: ArtifactKind
    marker: Literal["imported-from-existing"] = _MARKER
    imported_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC)]
    frontmatter: dict[str, object] | None = None


def metadata_record_path(root: Path, target: str) -> Path:
    """Absolute path for the sidecar YAML belonging to canonical ``target``."""
    return root / _METADATA_DIR_REL / f"{artifact_id_for_target(target)}.yaml"


def record_to_yaml_bytes(record: ImportedMetadataRecord) -> bytes:
    """Canonical YAML bytes (Pattern §3 — mirrors ``signoff/records.py``)."""
    text = yaml.safe_dump(
        record.model_dump(mode="json"),
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )
    return (unicodedata.normalize("NFC", text) + "\n").encode("utf-8")


def read_metadata_record(path: Path) -> ImportedMetadataRecord | None:
    """Return a parsed sidecar, or None when missing or unreadable/corrupt.

    A genuinely-absent sidecar returns None silently; a present-but-corrupt one logs a
    warning before returning None (never silently swallow) so a tampered/corrupt record
    that would otherwise downgrade verification to "native" leaves an audit trace.
    """
    if not path.exists():
        return None
    try:
        return ImportedMetadataRecord.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        _log.warning(
            "imported-metadata sidecar at %s is unreadable/corrupt (%s); treating as absent",
            path,
            exc,
        )
        return None
