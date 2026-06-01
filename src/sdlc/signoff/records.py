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

import contextlib
import datetime
import logging
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

import yaml
from pydantic import Field, StringConstraints, model_validator

from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import SignoffError

_log = logging.getLogger(__name__)


# EPIC-2A-D7A — per-phase exclusive write lock. A POSIX flock serialises
# concurrent write_record / invalidate_record against one phase file so two
# writers cannot both pass the exists-check and clobber the shared .tmp path.
if sys.platform != "win32":
    from sdlc.concurrency.locks import file_lock

    def _signoff_write_lock(target: Path) -> contextlib.AbstractContextManager[object]:
        """Per-target exclusive flock at ``<target>.lock`` (POSIX)."""
        return file_lock(str(target) + ".lock")

else:  # pragma: no cover — POSIX-only CI matrix (ci.yml: ubuntu + macos)

    def _signoff_write_lock(target: Path) -> contextlib.AbstractContextManager[object]:
        """Windows: no flock — EPIC-2A-D7B-WIN32-RUNS-LOCK (deferred; the
        framework is POSIX-only in v1, journal/writer.py raises on Windows)."""
        return contextlib.nullcontext()


_SIGNOFF_DIR = ".claude/state/signoffs"
_PHASE_DIR_MAP = {1: "01-Requirement", 2: "02-Architecture"}
_PHASE_NO_SIGNOFF: int = 3
_VALID_RECORD_PHASES = frozenset({1, 2})  # write_record/list_records scope
_SHA256_PAT: re.Pattern[str] = re.compile(r"^sha256:[0-9a-f]{64}$")
_RFC3339_UTC_MS = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
_RFC3339_UTC_MS_RE: re.Pattern[str] = re.compile(_RFC3339_UTC_MS)
_RFC3339_UTC_MS_OR_NULL = re.compile(rf"(?:{_RFC3339_UTC_MS}|^$)")

PhaseLiteral = Literal[1, 2]


def _is_safe_repo_relative_posix(p: str) -> bool:  # noqa: PLR0911
    """Return True if `p` is a safe repo-relative POSIX path.

    Rejects: absolute paths, any backslash (Windows separator), leading or
    interior `..` traversal segments. Branchy by design — each early return
    surfaces a distinct rejection reason that callers may map to error UX.
    """
    if not p:
        return False
    if "\\" in p:
        return False
    if p.startswith("/"):
        return False
    try:
        parsed = PurePosixPath(p)
    except Exception:
        return False
    if parsed.is_absolute():
        return False
    if p.startswith("../") or p == "..":
        return False
    if "/../" in p:
        return False
    return not p.endswith("/..")


def _normalize_yaml_data(obj: Any) -> Any:
    """Recursively normalize YAML-loaded data for Pydantic model_validate.

    PyYAML safe_load auto-converts ISO timestamps to datetime objects and
    sequences to lists. This function converts datetime/date → ISO string
    in canonical RFC 3339 UTC ms form, converting non-UTC tz to UTC first
    (preserves audit invariant: persisted timestamps are always UTC).
    """
    if isinstance(obj, dict):
        return {k: _normalize_yaml_data(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_yaml_data(v) for v in obj]
    if isinstance(obj, datetime.datetime):
        if obj.tzinfo is None:
            # Naive datetime: refuse to guess UTC (audit invariant: every
            # canonical timestamp must declare UTC explicitly via Z suffix).
            raise SignoffError(
                f"datetime field is missing timezone information: {obj.isoformat()!r}; "
                "canonical records require UTC (Z suffix)",
                details={"step": "normalize_yaml", "value": obj.isoformat()},
            )
        utc = obj.astimezone(datetime.timezone.utc)
        millis = utc.microsecond // 1000
        return f"{utc.strftime('%Y-%m-%dT%H:%M:%S')}.{millis:03d}Z"
    if isinstance(obj, datetime.date):
        # Plain date → midnight UTC ms (defensive; should not appear in records).
        return f"{obj.isoformat()}T00:00:00.000Z"
    return obj


class ArtifactRef(StrictModel):
    """Canonical artifact reference in a SignoffRecord (immutable, frozen)."""

    schema_version: Literal[1] = 1
    path: str  # repo-relative POSIX path
    hash: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _validate_path(self) -> ArtifactRef:
        if not _is_safe_repo_relative_posix(self.path):
            raise SignoffError(
                f"artifact path must be repo-relative POSIX: {self.path}",
                details={"path": self.path},
            )
        return self


class SignoffRecord(StrictModel):
    """Canonical signoff record for a phase (.claude/state/signoffs/phase-N.yaml).

    Not a wire-format contract (AC9/AC11-D2). See module docstring for promotion criteria.
    """

    schema_version: Literal[1] = 1
    phase: PhaseLiteral
    artifacts: Annotated[tuple[ArtifactRef, ...], Field(min_length=1)]
    approved_by: Annotated[str, StringConstraints(min_length=1)]
    approved_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC_MS)]
    drafted_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC_MS)]
    validated_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC_MS)]
    invalidated_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC_MS)] | None = None
    invalidated_reason: str | None = None


class _SignoffMdDraftArtifact(StrictModel):
    """Artifact entry in a SIGNOFF.md draft (private model)."""

    path: str
    hash: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _validate_path(self) -> _SignoffMdDraftArtifact:
        if not _is_safe_repo_relative_posix(self.path):
            raise SignoffError(
                f"artifact path must be repo-relative POSIX: {self.path}",
                details={"path": self.path},
            )
        return self


class _SignoffMdDraft(StrictModel):
    """Private model for reading SIGNOFF.md draft payloads (AC2).

    Mirrors Story 2A.5's _HookHashStore privacy posture EXACTLY.
    Never exported from sdlc.signoff or sdlc.contracts.

    Operator-written drafts MAY be in any artifact order; the canonical record
    written by ``validate_signoff`` is always emitted in path-sorted order
    (AC2 fifth-And) by the validator's sort + ``_canonicalize_record`` flow,
    which guarantees byte-stable round-trip on the audit-grade artifact.
    """

    schema_version: Literal[1] = 1
    phase: PhaseLiteral
    artifacts: Annotated[tuple[_SignoffMdDraftArtifact, ...], Field(min_length=1)]
    approved: bool
    approved_by: Annotated[str, StringConstraints(min_length=1)] | None = None
    approved_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC_MS)] | None = None
    drafted_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC_MS)]


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
    if not body.endswith("\n"):  # pragma: no cover — yaml.safe_dump always terminates with \n
        body += "\n"
    return body.encode("utf-8")


def _write_bytes_to_disk(target: Path, data: bytes) -> None:
    """Write bytes to target via tmp+fsync+replace (atomic on POSIX via os.rename).

    On Windows, Path.replace is a two-step move (non-atomic); cross-platform
    flock-based concurrency hardening is tracked under
    EPIC-2A-DEBT-SIGNOFF-FLOCK-CONCURRENCY in deferred-work.md (Story 2A.7 D3).
    fsync ensures the bytes are durable before the rename so a power-loss
    cannot leave an empty/stale tmp visible after the rename succeeds.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    fd = -1
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(str(tmp), str(target))
    except OSError:
        if fd != -1:
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(OSError):
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
    except SignoffError:
        raise
    except Exception as exc:
        raise SignoffError(
            f"canonical record at {target} is malformed: {exc}",
            details={"step": "read_record", "path": str(target)},
        ) from exc


def write_record(record: SignoffRecord, *, repo_root: Path) -> None:
    """Atomically write the canonical record to .claude/state/signoffs/phase-N.yaml.

    AC10: phase=3 records are unconditionally refused.
    AC5: refuses to overwrite a non-invalidated APPROVED record (D4: an
    invalidated record may be overwritten by the post-replan re-approval flow).
    The caller (Story 2A.12) is responsible for appending the journal entry.
    """
    if record.phase == _PHASE_NO_SIGNOFF:
        raise SignoffError(
            "phase 3 has no canonical record in v1",
            details={"step": "write_record", "phase": record.phase},
        )
    target = _signoff_path(record.phase, repo_root)
    canonical = _canonicalize_record(record)
    # The lock file lives beside the target — its directory must exist first.
    target.parent.mkdir(parents=True, exist_ok=True)
    # Hold the per-target write lock across the exists-check + write so two
    # concurrent writers cannot both pass the guard (EPIC-2A-D7A).
    with _signoff_write_lock(target):
        if target.exists():
            try:
                existing = read_record(record.phase, repo_root=repo_root)
            except SignoffError:
                # Existing file is malformed — refuse silently to overwrite to
                # avoid masking corruption with a fresh write.
                raise SignoffError(
                    f"cannot overwrite phase-{record.phase} record: existing file is "
                    "malformed; inspect manually before overwriting",
                    details={"step": "write_record", "phase": record.phase, "path": str(target)},
                ) from None
            if existing is not None and existing.invalidated_at is None:
                raise SignoffError(
                    f"cannot overwrite phase-{record.phase} approved record; "
                    "use invalidate_record first",
                    details={"step": "write_record", "phase": record.phase, "path": str(target)},
                )
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
    Returns the post-invalidation record (re-read from disk to guarantee
    byte-stability with future read_record calls).
    Raises SignoffError if no canonical record exists at phase or if `now_utc`
    is not RFC 3339 UTC ms format.
    """
    if not _RFC3339_UTC_MS_RE.match(now_utc):
        raise SignoffError(
            f"now_utc must be RFC 3339 UTC ms (e.g. 2026-05-10T12:00:00.000Z); got {now_utc!r}",
            details={"step": "invalidate_record", "now_utc": now_utc},
        )
    target = _signoff_path(phase, repo_root)
    # The lock file lives beside the target — its directory must exist first.
    target.parent.mkdir(parents=True, exist_ok=True)
    # Hold the per-target write lock across the TOCTOU read + rewrite + re-read
    # (EPIC-2A-D7A).
    with _signoff_write_lock(target):
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
        # Re-read from disk so the returned record matches future read_record
        # output byte-for-byte (catches any normalization round-trip drift).
        refreshed = read_record(phase, repo_root=repo_root)
        if refreshed is None:  # pragma: no cover — write succeeded means file exists
            raise SignoffError(
                f"phase-{phase} record vanished immediately after write",
                details={"step": "invalidate_record", "path": str(target)},
            )
        return refreshed


def list_records(repo_root: Path) -> tuple[SignoffRecord, ...]:
    """Return all canonical records sorted by phase number (1 then 2).

    Skips phase-3.yaml (phase 3 has no signoff per AC10) and any other
    out-of-range phase files (e.g. phase-99.yaml is silently ignored after a WARN).
    Empty tuple if directory missing.
    """
    signoff_dir = repo_root / _SIGNOFF_DIR
    if not signoff_dir.exists():
        return ()

    candidates: list[tuple[int, Path]] = []
    for phase_file in signoff_dir.glob("phase-*.yaml"):
        stem = phase_file.stem  # e.g. "phase-1"
        try:
            phase_num = int(stem.split("-", 1)[1])
        except (IndexError, ValueError):
            continue
        if phase_num == _PHASE_NO_SIGNOFF:
            _log.warning(
                "phase-3.yaml found and ignored: %s; phase 3 has no signoff in v1",
                phase_file,
            )
            continue
        if phase_num not in _VALID_RECORD_PHASES:
            _log.warning(
                "out-of-range signoff file ignored: %s (phase %d not in {1, 2})",
                phase_file,
                phase_num,
            )
            continue
        candidates.append((phase_num, phase_file))

    records: list[SignoffRecord] = []
    for phase_num, _ in sorted(candidates, key=lambda pair: pair[0]):
        rec = read_record(phase_num, repo_root=repo_root)
        if rec is not None:
            records.append(rec)
    return tuple(records)


# ---------------------------------------------------------------------------
# SIGNOFF.md draft reader (AC2)
# ---------------------------------------------------------------------------


def _extract_yaml_payload(text: str, path: Path) -> dict[str, Any]:  # noqa: C901
    """Extract YAML payload from SIGNOFF.md — supports frontmatter OR fenced block.

    Distinct, operator-actionable errors for each malformation mode (P24):
      - both shapes present → ambiguous
      - frontmatter delimiters present but unterminated → unterminated
      - frontmatter parses to non-dict (list/scalar/null/empty) → wrong shape
      - neither shape present → missing
    """
    stripped = text.lstrip()
    fm_data: Any = None
    fm_present = False
    fm_unterminated = False

    if stripped.startswith("---"):
        end = stripped.find("\n---", 3)
        if end == -1:
            fm_unterminated = True
        else:
            fm_present = True
            fm_text = stripped[3:end].strip()
            try:
                fm_data = yaml.safe_load(fm_text)
            except yaml.YAMLError as exc:
                raise SignoffError(
                    f"SIGNOFF.md at {path} is malformed: {exc}",
                    details={"step": "read_signoff_md_draft", "path": str(path)},
                ) from exc

    fence_pattern = re.compile(r"```signoff\s*\n(.*?)```", re.DOTALL)
    m = fence_pattern.search(text)
    fenced_data: Any = None
    fenced_present = m is not None
    if m is not None:
        try:
            fenced_data = yaml.safe_load(m.group(1))
        except yaml.YAMLError as exc:
            raise SignoffError(
                f"SIGNOFF.md at {path} is malformed: {exc}",
                details={"step": "read_signoff_md_draft", "path": str(path)},
            ) from exc

    if fm_unterminated:
        raise SignoffError(
            f"SIGNOFF.md at {path} is malformed: frontmatter has opening '---' but no "
            "closing '---' delimiter",
            details={"step": "read_signoff_md_draft", "path": str(path)},
        )

    if fm_present and fenced_present:
        raise SignoffError(
            f"SIGNOFF.md at {path} is malformed: BOTH frontmatter and fenced "
            "```signoff block are present; only one is permitted",
            details={"step": "read_signoff_md_draft", "path": str(path)},
        )

    if fm_present:
        if not isinstance(fm_data, dict):
            kind = type(fm_data).__name__ if fm_data is not None else "empty/null"
            raise SignoffError(
                f"SIGNOFF.md at {path} is malformed: frontmatter must be a YAML mapping; "
                f"got {kind}",
                details={"step": "read_signoff_md_draft", "path": str(path)},
            )
        return fm_data

    if fenced_present:
        if not isinstance(fenced_data, dict):
            kind = type(fenced_data).__name__ if fenced_data is not None else "empty/null"
            raise SignoffError(
                f"SIGNOFF.md at {path} is malformed: fenced ```signoff block must be a "
                f"YAML mapping; got {kind}",
                details={"step": "read_signoff_md_draft", "path": str(path)},
            )
        return fenced_data

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
            if not isinstance(p, str) or not _is_safe_repo_relative_posix(p):
                raise SignoffError(
                    f"artifact path must be repo-relative POSIX: {p}",
                    details={"step": "read_signoff_md_draft", "path": str(path)},
                )

    # Reject coerced bools (P29): `approved` MUST be a true Python bool, not 0/1/string.
    approved_raw = data.get("approved")
    if approved_raw is not None and not isinstance(approved_raw, bool):
        raise SignoffError(
            f"SIGNOFF.md at {path} is malformed: 'approved' must be a YAML boolean "
            f"(true/false); got {type(approved_raw).__name__}: {approved_raw!r}",
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
