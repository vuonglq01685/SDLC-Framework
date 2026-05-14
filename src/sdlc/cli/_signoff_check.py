"""Per-scan signoff validation pass (AC5, AC6, Story 2A.12).

Private helper extracted from ``cli/scan.py`` to keep that module under the
400-LOC cap (Architecture §765 + NFR-MAINT-3). Public entry point:
``check_signoffs(repo_root, journal_path, *, ctx) -> list[dict]``.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import emit_warning
from sdlc.contracts.journal_entry import JournalEntry

_logger = logging.getLogger(__name__)
_ACTOR: Final[str] = "cli"
_PHASE_2_GATE: Final[int] = 2


def _state_to_wire(state: object) -> str:
    """Convert SignoffState enum → kebab-case wire string for emit_json payloads."""
    s = str(state)
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.lower().replace("_", "-")


def check_signoffs(  # noqa: C901, PLR0912, PLR0915
    repo_root: Path,
    journal_path: Path,
    *,
    ctx: typer.Context | None = None,
) -> list[dict[str, object]]:
    """Run signoff validation pass for phases 1 and 2 (AC6/D1: dedicated helper).

    For each phase in (1, 2):
      - AWAITING_SIGNOFF / APPROVED / INVALIDATED_BY_REPLAN → skip
      - DRAFTED_NOT_APPROVED + approved=false → skip
      - DRAFTED_NOT_APPROVED + approved=true → validate hashes
        - clean → write canonical record + journal signoff_recorded
        - drift → emit ERR_SIGNOFF_HASH_DRIFT envelope + journal signoff_hash_drift_detected
        - non-drift validation failure (e.g. missing approved_by) → ERR_SIGNOFF_VALIDATION
        - malformed draft (parse error) → ERR_SIGNOFF_MALFORMED_DRAFT
    Scan exits 0 regardless of outcome (non-blocking per AC6 third-And).

    Returns a list of per-phase status dicts ``[{"phase": N, "state": "<enum>"}]``
    that ``run_scan`` includes under the ``signoffs`` key of its emit_json envelope
    (P2 from Story 2A.12 review: AC6 third-And requires this section).
    """
    from sdlc.errors import SignoffError
    from sdlc.journal import append_sync
    from sdlc.journal.writer import allocate_next_seq_for_append_sync
    from sdlc.signoff import (
        PHASE_DIR_MAP,
        SignoffMdDraft,
        SignoffState,
        compute_state,
        read_signoff_md_draft,
        validate_signoff,
        write_record,
    )

    def _try_read_draft(phase: int) -> SignoffMdDraft | None:
        phase_dir_name = PHASE_DIR_MAP.get(phase)
        if not phase_dir_name:
            return None
        draft_path = repo_root / phase_dir_name / "SIGNOFF.md"
        if not draft_path.exists():
            return None
        try:
            return read_signoff_md_draft(draft_path)
        except SignoffError as exc:
            # P9: surface malformed-draft to stderr (was: silent logger.warning
            # contradicting AC2 final-And + states.compute_state docstring).
            if ctx is not None:
                emit_warning(
                    "ERR_SIGNOFF_MALFORMED_DRAFT",
                    f"phase {phase} SIGNOFF.md is malformed at {draft_path}: {exc}; "
                    "fix or delete to proceed",
                    ctx=ctx,
                    details={"phase": phase, "path": str(draft_path)},
                )
            else:
                _logger.warning("signoff check: malformed SIGNOFF.md for phase %d: %s", phase, exc)
            return None

    def _allocate_seq() -> int:
        """P5: canonical seq allocator (flock + max-seq; was: last-line read + return 0)."""
        return allocate_next_seq_for_append_sync(journal_path)

    now = now_rfc3339_utc_ms()
    phase1_approved = False
    signoffs_report: list[dict[str, object]] = []

    for phase in (1, 2):
        # P18: phase 2 requires phase 1 APPROVED (sequential gate — AC2 prerequisite).
        # Use `continue` so future phase additions don't silently break; log when a
        # phase-2 draft is present but skipped so operator sees the blocker.
        if phase == _PHASE_2_GATE and not phase1_approved:
            if (repo_root / PHASE_DIR_MAP[phase] / "SIGNOFF.md").exists() and ctx is not None:
                emit_warning(
                    "ERR_SIGNOFF_VALIDATION",
                    "phase 2 SIGNOFF.md draft present but phase 1 not APPROVED — "
                    "approve phase 1 first via 'sdlc signoff 1' then 'sdlc scan'",
                    ctx=ctx,
                    details={"phase": 2, "phase1_state": "not_approved"},
                )
            signoffs_report.append({"phase": phase, "state": "skipped-phase1-not-approved"})
            continue

        try:
            state = compute_state(phase, repo_root=repo_root)
        except SignoffError as exc:
            # P9: surface compute_state malformed-draft via emit_warning envelope.
            if ctx is not None:
                emit_warning(
                    "ERR_SIGNOFF_MALFORMED_DRAFT",
                    f"signoff check: compute_state phase {phase} failed: {exc}",
                    ctx=ctx,
                    details={"phase": phase},
                )
            else:
                _logger.warning("signoff check: compute_state phase %d failed: %s", phase, exc)
            signoffs_report.append({"phase": phase, "state": "malformed-draft"})
            continue

        if state == SignoffState.APPROVED:
            if phase == 1:
                phase1_approved = True
            signoffs_report.append({"phase": phase, "state": "approved"})
            continue

        if state != SignoffState.DRAFTED_NOT_APPROVED:
            signoffs_report.append({"phase": phase, "state": _state_to_wire(state)})
            continue

        draft = _try_read_draft(phase)
        if draft is None or not draft.approved:
            signoffs_report.append({"phase": phase, "state": "drafted-not-approved"})
            continue

        # approved=true → attempt validation.
        try:
            result = validate_signoff(phase, repo_root=repo_root, now_utc=now)
        except SignoffError as exc:
            # P4: only "drifted" / "missing" map to ERR_SIGNOFF_HASH_DRIFT; other
            # non-drift validator failures (missing approved_by, phase mismatch,
            # cross-phase artifact, …) map to ERR_SIGNOFF_VALIDATION so the audit
            # log doesn't record fictitious drift events.
            details_kind = exc.details.get("kind") if isinstance(exc.details, dict) else None
            is_drift = details_kind in ("drifted", "missing")
            drifted_paths: list[str] = []
            if is_drift and isinstance(exc.details, dict):
                artifact = exc.details.get("artifact")
                if artifact:
                    drifted_paths = [str(artifact)]

            if is_drift:
                code = "ERR_SIGNOFF_HASH_DRIFT"
                msg = (
                    f"{exc.message}; cannot approve. Either restore the artifact to "
                    f"its state at draft time, or regenerate the signoff draft "
                    f"with '/sdlc-signoff {phase}'"
                )
                journal_kind = "signoff_hash_drift_detected"
                journal_payload: dict[str, object] = {
                    "phase": phase,
                    "drifted_paths": drifted_paths,
                }
            else:
                code = "ERR_SIGNOFF_VALIDATION"
                msg = str(exc.message)
                journal_kind = "signoff_validation_failed"
                journal_payload = {
                    "phase": phase,
                    "validation_kind": str(details_kind) if details_kind else "unknown",
                }

            # P13: route via emit_warning so --json mode sees the envelope (was: raw
            # _sys.stderr.write bypassing JSON-mode + exit-code map).
            if ctx is not None:
                emit_warning(code, msg, ctx=ctx, details=journal_payload)
            else:
                # Test path / non-CLI caller: keep stderr line for back-compat.
                import sys as _sys

                _sys.stderr.write(f"{code}: {msg}\n")

            # Journal entry. P7: after_hash now represents the SIGNOFF.md content
            # hash at the moment validation failed (was: sha256 of comma-joined paths
            # — meaningless content for `after_hash`). The draft content hash is the
            # meaningful state-snapshot for a drift/validation-failure event.
            # JournalEntry contract requires after_hash: str (frozen v1) — we cannot
            # use None without bumping schema_version per ADR-024.
            # P6: journal failures logged loudly (was: only WARN; still non-blocking
            # for scan itself, but the audit-gap is now visible).
            draft_path = repo_root / PHASE_DIR_MAP[phase] / "SIGNOFF.md"
            try:
                draft_bytes = draft_path.read_bytes()
                event_hash = f"sha256:{hashlib.sha256(draft_bytes).hexdigest()}"
            except OSError:
                # Defensive: if the draft itself is unreadable, hash the payload.
                import json as _json

                event_hash = (
                    "sha256:"
                    + hashlib.sha256(
                        _json.dumps(journal_payload, sort_keys=True).encode("utf-8")
                    ).hexdigest()
                )
            try:
                entry = JournalEntry(
                    schema_version=1,
                    monotonic_seq=_allocate_seq(),
                    ts=now,
                    actor=_ACTOR,
                    kind=journal_kind,
                    target_id=f"signoff-phase-{phase}",
                    before_hash=None,
                    after_hash=event_hash,
                    payload=journal_payload,
                )
                append_sync(entry, journal_path=journal_path)
            except OSError as jerr:
                _logger.error(
                    "AUDIT-GAP signoff journal append FAILED (%s phase %d): %s; "
                    "audit chain has a hole — operator must investigate",
                    journal_kind,
                    phase,
                    jerr,
                )
            signoffs_report.append(
                {"phase": phase, "state": "drift" if is_drift else "validation-failed"}
            )
            continue

        # Validation succeeded → write canonical record.
        try:
            write_record(result.record, repo_root=repo_root)
        except SignoffError as exc:
            if ctx is not None:
                emit_warning(
                    "ERR_SIGNOFF_VALIDATION",
                    f"signoff check: write_record phase {phase} failed: {exc}",
                    ctx=ctx,
                    details={"phase": phase},
                )
            else:
                _logger.warning("signoff check: write_record phase %d failed: %s", phase, exc)
            signoffs_report.append({"phase": phase, "state": "write-failed"})
            continue

        if phase == 1:
            phase1_approved = True

        # Journal signoff_recorded.
        try:
            from sdlc.signoff.hasher import compute_signoff_record_hash

            record_hash = compute_signoff_record_hash(result.record)
            entry = JournalEntry(
                schema_version=1,
                monotonic_seq=_allocate_seq(),
                ts=now,
                actor=_ACTOR,
                kind="signoff_recorded",
                target_id=f"signoff-phase-{phase}",
                before_hash=None,
                after_hash=record_hash,
                payload={
                    "phase": phase,
                    "approved_by": result.record.approved_by,
                    "artifact_count": len(result.record.artifacts),
                    "all_hashes_clean": True,
                },
            )
            append_sync(entry, journal_path=journal_path)
        except OSError as jerr:
            _logger.error(
                "AUDIT-GAP signoff journal append FAILED (signoff_recorded phase %d): %s",
                phase,
                jerr,
            )
        signoffs_report.append({"phase": phase, "state": "approved"})

    return signoffs_report
