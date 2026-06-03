"""Three-pass adopt orchestrator (Story 3.1, FR2, AC1/AC3/AC4/AC6).

`run_adopt` runs Pass 1 → Pass 2 → Pass 3 in strict order, journals each pass start/complete
(event-only zero-sentinel `after_hash` per ADR-028 §2), writes `.claude/state/adopt-report.json`
after Pass 1 (AC4), and resumes from `passes_completed` on re-run (D3(a) pass-level resume).

Boundary (scripts/module_boundary_table.py): `adopt/` builds `JournalEntry` directly and uses
the SYNC journal API (`allocate_next_seq_for_append_sync` + `append_sync`) — the CLI command body
is synchronous, so the async `append` (a coroutine that no-ops if un-awaited) must NOT be used.
`adopt/` MUST NOT import `engine/`, `dispatcher/`, or `runtime/`.
"""

from __future__ import annotations

import contextlib
import json
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from sdlc.adopt.invariant import assert_path_under_claude
from sdlc.adopt.passes import detection, stamp, symlink_offer
from sdlc.concurrency.io_primitives import atomic_write_bytes
from sdlc.contracts.adopt_report import AdoptReport, DetectedArtifact
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import AdoptError
from sdlc.ids.clock import now_rfc3339_utc_ms
from sdlc.journal import allocate_next_seq_for_append_sync, append_sync

# Named pass numbers (avoid magic literals; the ordering 1->2->3 is the FR2 contract).
_PASS_DETECT: Final[int] = 1
_PASS_SYMLINK_OFFER: Final[int] = 2
_PASS_STAMP: Final[int] = 3
_PASSES: Final[tuple[int, ...]] = (_PASS_DETECT, _PASS_SYMLINK_OFFER, _PASS_STAMP)
_ACTOR: Final[str] = "cli"
_TARGET_ID: Final[str] = "adopt"
# Event-only entries record no content write → all-zero sha256 sentinel (ADR-028 §2).
_ZERO_HASH: Final[str] = "sha256:" + "0" * 64
_REPORT_REL: Final[str] = ".claude/state/adopt-report.json"

_KIND_STARTED: Final[str] = "adopt_pass_started"
_KIND_COMPLETED: Final[str] = "adopt_pass_completed"
_KIND_FAILED: Final[str] = "adopt_pass_failed"


def _append_event(journal_path: Path, *, kind: str, payload: dict[str, object]) -> None:
    """Append an event-only journal entry (zero-sentinel `after_hash`, `before_hash=None`)."""
    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=now_rfc3339_utc_ms(),
        actor=_ACTOR,
        kind=kind,
        target_id=_TARGET_ID,
        before_hash=None,
        after_hash=_ZERO_HASH,
        payload=payload,
    )
    append_sync(entry, journal_path=journal_path)


def _report_bytes(report: AdoptReport) -> bytes:
    """Canonical bytes: sorted keys, UTF-8, NFC-normalized, no floats (architecture.md:496-515)."""
    text = json.dumps(
        report.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (unicodedata.normalize("NFC", text) + "\n").encode("utf-8")


def _write_report(root: Path, report: AdoptReport) -> None:
    """Atomically write `adopt-report.json`, pre-guarded to stay under `.claude/` (AC7)."""
    report_path = (root / _REPORT_REL).resolve()
    assert_path_under_claude(root, report_path)
    try:
        atomic_write_bytes(report_path, _report_bytes(report))
    except OSError as exc:  # missing parent / disk full → typed envelope, not a raw traceback
        raise AdoptError(
            "adopt could not write adopt-report.json",
            details={"path": str(report_path), "cause": str(exc)},
        ) from exc


def _read_existing_report(root: Path) -> AdoptReport | None:
    """Return the prior `adopt-report.json` (resume cursor) or None on a fresh adopt."""
    report_path = root / _REPORT_REL
    if not report_path.exists():
        return None
    try:
        return AdoptReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise AdoptError(
            "adopt-report.json is malformed; cannot resume",
            details={"path": str(report_path), "cause": str(exc)},
        ) from exc


def _validate_resume_cursor(completed: Sequence[int], report_path: Path) -> None:
    """Reject a corrupt resume cursor — `passes_completed` MUST be a contiguous prefix of 1->2->3.

    A hand-edited or future-tool-written report with out-of-order, duplicate, or out-of-range
    passes (e.g. ``(2,)``, ``(1, 3)``, ``(99,)``, ``(1, 1)``) would otherwise silently skip passes
    against a stale `detected` set (FR2 ordering). Only ``()``/``(1,)``/``(1, 2)``/``(1, 2, 3)``
    are valid resume cursors.
    """
    if list(completed) != list(_PASSES[: len(completed)]):
        raise AdoptError(
            "adopt-report.json resume cursor is corrupt; cannot resume",
            details={"path": str(report_path), "passes_completed": list(completed)},
        )


def _run_pass(
    n: int,
    root: Path,
    detected: list[DetectedArtifact],
    *,
    git_signal: dict[str, int] | None,
    legacy_code_globs: tuple[str, ...],
) -> list[DetectedArtifact]:
    """Dispatch pass ``n`` to its typed seam. Pass 1 returns the detected list (3.2 fills it).

    ``git_signal`` (recency, D2) and ``legacy_code_globs`` (exclusion, D4) are injected by
    the ``cli`` layer and consumed only by Pass 1 detection (``adopt/`` has no git grant).
    """
    if n == _PASS_DETECT:
        return list(
            detection.detect_existing(
                root, git_signal=git_signal, legacy_code_globs=legacy_code_globs
            )
        )
    if n == _PASS_SYMLINK_OFFER:
        symlink_offer.offer_symlinks(root, detected)
        return detected
    stamp.mark_imported(root, detected)
    return detected


def _build_report(
    root: Path,
    scanned_at: str,
    detected: Sequence[DetectedArtifact],
    completed: Sequence[int],
) -> AdoptReport:
    return AdoptReport(
        schema_version=1,
        repo_root=str(root),
        scanned_at=scanned_at,
        detected=tuple(detected),
        passes_completed=tuple(completed),
    )


def run_adopt(
    *,
    root: Path,
    journal_path: Path,
    git_signal: dict[str, int] | None = None,
    legacy_code_globs: tuple[str, ...] = (),
) -> AdoptReport:
    """Run the three adopt passes in order, journaling + persisting the report (FR2).

    Resumes from any prior `adopt-report.json` (D3(a) pass-level): passes in
    `passes_completed` are skipped. On a pass failure the last-good `passes_completed` is
    persisted, the failure is journaled with the pass + reason, and `AdoptError` is raised.

    ``git_signal`` (Story 3.2 D2 recency map) and ``legacy_code_globs`` (D4 exclusion) are
    injected by the ``cli`` layer and forwarded to Pass 1 detection; both default to the
    no-op value so non-adopt callers and resume runs are unaffected.
    """
    existing = _read_existing_report(root)
    completed: list[int] = list(existing.passes_completed) if existing else []
    if existing is not None:
        _validate_resume_cursor(completed, root / _REPORT_REL)
    scanned_at: str = existing.scanned_at if existing else now_rfc3339_utc_ms()
    detected: list[DetectedArtifact] = list(existing.detected) if existing else []

    for n in _PASSES:
        if n in completed:
            continue
        _append_event(journal_path, kind=_KIND_STARTED, payload={"pass": n})
        try:
            detected = _run_pass(
                n, root, detected, git_signal=git_signal, legacy_code_globs=legacy_code_globs
            )
        except Exception as exc:
            # Orchestrator must journal + persist ANY pass failure, then re-raise as AdoptError.
            # Both side effects are best-effort: a secondary failure (journal/disk) must NOT mask
            # the real pass error — the AdoptError below always surfaces with `exc` as its cause.
            with contextlib.suppress(Exception):
                _append_event(
                    journal_path, kind=_KIND_FAILED, payload={"pass": n, "reason": str(exc)}
                )
            with contextlib.suppress(Exception):
                _write_report(root, _build_report(root, scanned_at, detected, completed))
            raise AdoptError(
                f"adopt pass {n} failed: {exc}",
                details={"pass": n, "reason": str(exc)},
            ) from exc
        completed.append(n)
        _append_event(journal_path, kind=_KIND_COMPLETED, payload={"pass": n})
        if n == 1:
            # AC4: the report is written as soon as Pass 1 completes.
            _write_report(root, _build_report(root, scanned_at, detected, completed))

    report = _build_report(root, scanned_at, detected, completed)
    _write_report(root, report)
    return report
