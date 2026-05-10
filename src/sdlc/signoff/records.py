"""Signoff record persistence layer (AC5, AC9, Story 2A.7).

SignoffRecord and ArtifactRef are internal policy models, not wire-format contracts.
Format may evolve in v1.x without ADR-024 ceremony. The on-disk YAML at
.claude/state/signoffs/phase-<N>.yaml is canonical for human-audit purposes;
the Python model is a v1 implementation detail.

AC11/D2 decision: SignoffRecord kept private to sdlc.signoff (NOT exported from
sdlc.contracts); no snapshot under tests/contract_snapshots/v1/.
Promotion criteria documented in module docstring per AC9:
  - Promotion criterion 1: any --json CLI envelope serialises SignoffRecord
  - Promotion criterion 2: any HTTP route returns SignoffRecord in its body
  - Promotion criterion 3: any external tool (dashboard, third-party) reads the YAML
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

import yaml
from pydantic import StringConstraints, model_validator

from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import SignoffError

_SIGNOFF_DIR = ".claude/state/signoffs"
_PHASE_DIR_MAP = {1: "01-Requirement", 2: "02-Architecture"}
_PHASE_NO_SIGNOFF: int = 3
_SHA256_PAT: re.Pattern[str] = re.compile(r"^sha256:[0-9a-f]{64}$")
_RFC3339_UTC_MS = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"


def _normalize_yaml_data(obj: Any) -> Any:
    """Recursively normalize YAML-loaded data for Pydantic model_validate.

    PyYAML safe_load auto-converts ISO timestamps to datetime objects and
    sequences to lists. This function converts datetime/date → ISO string
    and leaves all other scalars unchanged. The strict=False call in
    model_validate handles list→tuple coercion.
    """
    if isinstance(obj, dict):
        return {k: _normalize_yaml_data(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_yaml_data(v) for v in obj]
    if isinstance(obj, datetime.datetime):
        # Preserve the original UTC suffix if timezone-aware
        if obj.tzinfo is not None:
            return obj.strftime("%Y-%m-%dT%H:%M:%S.") + f"{obj.microsecond // 1000:03d}Z"
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


class ArtifactRef(StrictModel):
    """Canonical artifact reference in a SignoffRecord (immutable, frozen)."""

    schema_version: Literal[1] = 1
    path: str  # repo-relative POSIX path
    hash: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _validate_path(self) -> ArtifactRef:
        p = self.path
        if p.startswith("/") or p.startswith("..") or "/../" in p or p.endswith("/.."):
            raise SignoffError(
                f"artifact path must be repo-relative POSIX: {p}",
                details={"path": p},
            )
        # Reject absolute paths on all platforms
        try:
            parsed = PurePosixPath(p)
        except Exception as _exc:
            raise SignoffError(f"artifact path must be repo-relative POSIX: {p}") from _exc
        if parsed.is_absolute():
            raise SignoffError(
                f"artifact path must be repo-relative POSIX: {p}",
                details={"path": p},
            )
        return self


class SignoffRecord(StrictModel):
    """Canonical signoff record for a phase (.claude/state/signoffs/phase-N.yaml).

    Not a wire-format contract (AC9/AC11-D2). See module docstring for promotion criteria.
    """

    schema_version: Literal[1] = 1
    phase: int
    artifacts: tuple[ArtifactRef, ...]
    approved_by: str
    approved_at: str
    drafted_at: str
    validated_at: str
    invalidated_at: str | None = None
    invalidated_reason: str | None = None


class _SignoffMdDraftArtifact(StrictModel):
    """Artifact entry in a SIGNOFF.md draft (private model)."""

    path: str
    hash: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _validate_path(self) -> _SignoffMdDraftArtifact:
        p = self.path
        parsed = PurePosixPath(p)
        if parsed.is_absolute() or p.startswith("..") or "/../" in p or p.endswith("/.."):
            raise SignoffError(
                f"artifact path must be repo-relative POSIX: {p}",
                details={"path": p},
            )
        return self


class _SignoffMdDraft(StrictModel):
    """Private model for reading SIGNOFF.md draft payloads (AC2).

    Mirrors Story 2A.5's _HookHashStore privacy posture EXACTLY.
    Never exported from sdlc.signoff or sdlc.contracts.
    """

    schema_version: Literal[1] = 1
    phase: int
    artifacts: tuple[_SignoffMdDraftArtifact, ...]
    approved: bool
    approved_by: str | None = None
    approved_at: str | None = None
    drafted_at: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _signoff_path(phase: int, repo_root: Path) -> Path:
    return repo_root / _SIGNOFF_DIR / f"phase-{phase}.yaml"


def _canonicalize_record(record: SignoffRecord) -> bytes:
    """Produce sorted-key YAML bytes + trailing newline (Pattern §3 YAML analogue)."""
    data = record.model_dump(mode="json")
    body = yaml.safe_dump(
        data,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )
    if not body.endswith("\n"):
        body += "\n"
    return body.encode("utf-8")


def _write_bytes_to_disk(target: Path, data: bytes) -> None:
    """Write bytes to target using tmp+replace (atomic on POSIX via os.rename).

    On Windows, Path.replace is a two-step move (non-atomic); mirrors scan.py pattern.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_record(phase: int, *, repo_root: Path) -> SignoffRecord | None:
    """Return the canonical SignoffRecord for phase, or None if absent.

    Raises SignoffError if the file exists but is malformed or schema-invalid.
    """
    target = _signoff_path(phase, repo_root)
    if not target.exists():
        return None
    try:
        raw = target.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SignoffError(
            f"canonical record at {target} is malformed: {exc}",
            details={"step": "read_record", "path": str(target)},
        ) from exc
    except OSError as exc:
        raise SignoffError(
            f"failed to read canonical record at {target}: {exc}",
            details={"step": "read_record", "path": str(target)},
        ) from exc

    try:
        return SignoffRecord.model_validate(_normalize_yaml_data(data), strict=False)
    except Exception as exc:
        raise SignoffError(
            f"canonical record at {target} is malformed: {exc}",
            details={"step": "read_record", "path": str(target)},
        ) from exc


def write_record(record: SignoffRecord, *, repo_root: Path) -> None:
    """Atomically write the canonical record to .claude/state/signoffs/phase-N.yaml.

    Refuses to overwrite an existing APPROVED record (raises SignoffError).
    The caller (Story 2A.12) is responsible for appending the journal entry.
    """
    target = _signoff_path(record.phase, repo_root)
    if target.exists():
        raise SignoffError(
            f"cannot overwrite phase-{record.phase} approved record; use invalidate_record first",
            details={"step": "write_record", "phase": record.phase, "path": str(target)},
        )
    canonical = _canonicalize_record(record)
    try:
        _write_bytes_to_disk(target, canonical)
    except OSError as exc:
        raise SignoffError(
            f"failed to write canonical record: {exc}",
            details={"step": "write_record", "path": str(target)},
        ) from exc


def invalidate_record(
    phase: int,
    *,
    repo_root: Path,
    reason: str,
    now_utc: str,
) -> SignoffRecord:
    """Mark the canonical record as invalidated-by-replan.

    Mutates the file via atomic rewrite: sets invalidated_at + invalidated_reason
    while preserving all other fields (the audit trail).
    Returns the post-invalidation record.
    Raises SignoffError if no canonical record exists at phase.
    """
    target = _signoff_path(phase, repo_root)
    existing = read_record(phase, repo_root=repo_root)
    if existing is None:
        raise SignoffError(
            f"no canonical record found for phase-{phase}; cannot invalidate",
            details={"step": "invalidate_record", "phase": phase},
        )
    # Rebuild record with invalidated_at + reason; preserve all other fields
    updated = SignoffRecord(
        schema_version=existing.schema_version,
        phase=existing.phase,
        artifacts=existing.artifacts,
        approved_by=existing.approved_by,
        approved_at=existing.approved_at,
        drafted_at=existing.drafted_at,
        validated_at=existing.validated_at,
        invalidated_at=now_utc,
        invalidated_reason=reason,
    )
    canonical = _canonicalize_record(updated)
    try:
        _write_bytes_to_disk(target, canonical)
    except OSError as exc:
        raise SignoffError(
            f"failed to write invalidated record: {exc}",
            details={"step": "invalidate_record", "path": str(target)},
        ) from exc
    return updated


def list_records(repo_root: Path) -> tuple[SignoffRecord, ...]:
    """Return all canonical records sorted by phase (1 then 2).

    Skips phase-3.yaml (phase 3 has no signoff per AC10).
    Empty tuple if directory missing.
    """
    signoff_dir = repo_root / _SIGNOFF_DIR
    if not signoff_dir.exists():
        return ()

    records: list[SignoffRecord] = []
    for phase_file in sorted(signoff_dir.glob("phase-*.yaml")):
        stem = phase_file.stem  # e.g. "phase-1"
        try:
            phase_num = int(stem.split("-")[1])
        except (IndexError, ValueError):
            continue
        if phase_num == _PHASE_NO_SIGNOFF:
            print(
                f"[WARN] phase-3.yaml found and ignored: {phase_file}; "
                "phase 3 has no signoff in v1",
                file=sys.stderr,
            )
            continue
        rec = read_record(phase_num, repo_root=repo_root)
        if rec is not None:
            records.append(rec)

    return tuple(records)


# ---------------------------------------------------------------------------
# SIGNOFF.md draft reader (AC2)
# ---------------------------------------------------------------------------


def _extract_yaml_payload(text: str, path: Path) -> dict:  # type: ignore[type-arg]
    """Extract YAML payload from SIGNOFF.md — supports frontmatter OR fenced block."""
    # Try YAML frontmatter first (--- ... ---)
    stripped = text.lstrip()
    if stripped.startswith("---"):
        end = stripped.find("\n---", 3)
        if end != -1:
            fm_text = stripped[3:end].strip()
            try:
                data = yaml.safe_load(fm_text)
                if isinstance(data, dict):
                    return data
            except yaml.YAMLError as exc:
                raise SignoffError(
                    f"SIGNOFF.md at {path} is malformed: {exc}",
                    details={"step": "read_signoff_md_draft", "path": str(path)},
                ) from exc

    # Try fenced YAML code block (```signoff ... ```)
    fence_pattern = re.compile(r"```signoff\s*\n(.*?)```", re.DOTALL)
    m = fence_pattern.search(text)
    if m:
        block_text = m.group(1)
        try:
            data = yaml.safe_load(block_text)
            if isinstance(data, dict):
                return data
        except yaml.YAMLError as exc:
            raise SignoffError(
                f"SIGNOFF.md at {path} is malformed: {exc}",
                details={"step": "read_signoff_md_draft", "path": str(path)},
            ) from exc

    raise SignoffError(
        f"SIGNOFF.md at {path} is malformed: no frontmatter or fenced signoff block found",
        details={"step": "read_signoff_md_draft", "path": str(path)},
    )


def read_signoff_md_draft(path: Path) -> _SignoffMdDraft:
    """Read a SIGNOFF.md draft and return a _SignoffMdDraft (private model).

    Accepts both YAML frontmatter and fenced ```signoff block forms.
    Raises SignoffError if the file is missing, malformed, or schema-invalid.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SignoffError(
            f"SIGNOFF.md at {path} cannot be read: {exc}",
            details={"step": "read_signoff_md_draft", "path": str(path)},
        ) from exc

    data = _normalize_yaml_data(_extract_yaml_payload(text, path))

    # Validate artifact paths before model_validate (better error messages)
    for art in data.get("artifacts", []):
        if isinstance(art, dict):
            p = art.get("path", "")
            parsed = PurePosixPath(str(p))
            if parsed.is_absolute() or str(p).startswith("..") or "/../" in str(p):
                raise SignoffError(
                    f"artifact path must be repo-relative POSIX: {p}",
                    details={"step": "read_signoff_md_draft", "path": str(path)},
                )

    try:
        return _SignoffMdDraft.model_validate(data, strict=False)
    except SignoffError:
        raise
    except Exception as exc:
        raise SignoffError(
            f"SIGNOFF.md at {path} is malformed: {exc}",
            details={"step": "read_signoff_md_draft", "path": str(path)},
        ) from exc
