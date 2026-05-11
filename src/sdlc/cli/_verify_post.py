"""Post-dispatch ceremony for `sdlc verify` (Story 2A.10).

Private CLI-internal helpers invoked AFTER the dispatcher returns:

  * verdict envelope parsing,
  * `_Verification` row construction + frontmatter append,
  * `kind=artifact_verified` journal emit,
  * defensive `state.next_monotonic_seq` re-anchor.

Lives alongside `_verify_dispatch.py` so each file stays under the
§1052-§1112 LOC cap; D1 still mandates a single PUBLIC surface
(`cli/verify.py` re-exports the relevant symbols).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli._verify_frontmatter import (
    ALLOWED_STATUSES,
    VERIFIER_NOTE_MAX_LEN,
    _append_verification,
    _parse_frontmatter,
    _serialize_artifact,
    _Verification,
)
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import StateError

__all__ = (  # noqa: RUF022 — pipeline order, not alphabetical
    "parse_verdict_envelope",
    "build_verification_entry",
    "append_and_persist_frontmatter",
    "emit_artifact_verified",
    "advance_state_seq",
    "SLASH_COMMAND",
    "REQUIRED_PHASE",
)

SLASH_COMMAND: Final[str] = "/sdlc-verify"
REQUIRED_PHASE: Final[int] = 1


def parse_verdict_envelope(output_text: str) -> tuple[str, str | None]:
    """Parse the verifier's ``output_text`` into ``(status, note)``.

    Defensive: any malformed payload falls back to
    ``(status="verified", note=None)`` rather than failing the verify
    ceremony — the stored ``content_hash_at_verify`` already pins the
    body bytes presented to the verifier, so an unparseable verdict
    still produces a defensible audit trail.
    """
    txt = output_text.strip()
    if not txt:
        return "verified", None
    try:
        parsed: object = json.loads(txt)
    except json.JSONDecodeError:
        return "verified", None
    if not isinstance(parsed, dict):
        return "verified", None
    raw_verdict = parsed.get("verdict")
    status: str = raw_verdict if raw_verdict in ALLOWED_STATUSES else "verified"
    raw_note = parsed.get("note")
    note: str | None = (
        raw_note[:VERIFIER_NOTE_MAX_LEN] if isinstance(raw_note, str) and raw_note else None
    )
    return status, note


def build_verification_entry(
    *,
    verifier: str,
    status: str,
    note: str | None,
    body_hash: str,
) -> _Verification:
    """Construct a single ``_Verification`` row from the parsed verdict."""
    if status not in ALLOWED_STATUSES:
        status = "verified"
    return _Verification(
        verifier=verifier,
        ts=now_rfc3339_utc_ms(),
        status=status,  # type: ignore[arg-type]  # narrowed above
        content_hash_at_verify=body_hash,
        verifier_note=note,
    )


def append_and_persist_frontmatter(
    artifact_path: Path,
    entry: _Verification,
) -> tuple[dict[str, Any], int]:
    """Re-read the artifact, append `entry`, persist atomically.

    Returns ``(new_frontmatter, verification_index)`` so the caller can
    embed both into the ``artifact_verified`` journal payload. Body
    bytes are preserved verbatim (canonical round-trip proof lives in
    `_verify_frontmatter._canonical_body`).
    """
    fresh_content = artifact_path.read_text(encoding="utf-8")
    fresh_fm, fresh_body = _parse_frontmatter(fresh_content)
    new_fm = _append_verification(fresh_fm, entry)
    new_content = _serialize_artifact(new_fm, fresh_body)
    artifact_path.write_text(new_content, encoding="utf-8")
    verifications_list = new_fm["verifications"]
    assert isinstance(verifications_list, list)
    return new_fm, len(verifications_list) - 1


async def emit_artifact_verified(
    *,
    journal_path: Path,
    rel_path: str,
    entry: _Verification,
    verification_index: int,
) -> int:
    """Append the ``kind=artifact_verified`` journal entry; return seq used."""
    from sdlc.dispatcher._panel_helpers import _allocate_seq  # deferred (private)
    from sdlc.journal import append as journal_append  # deferred

    payload: dict[str, object] = {
        "slash_command": SLASH_COMMAND,
        "phase": REQUIRED_PHASE,
        "verifier": entry.verifier,
        "status": entry.status,
        "content_hash_at_verify": entry.content_hash_at_verify,
        "verification_index": verification_index,
    }
    if entry.verifier_note:
        payload["verifier_note"] = entry.verifier_note
    seq = await _allocate_seq(journal_path)
    je = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=now_rfc3339_utc_ms(),
        actor="cli",
        kind="artifact_verified",
        target_id=rel_path,
        before_hash=None,
        after_hash=entry.content_hash_at_verify,
        payload=payload,
    )
    await journal_append(je, journal_path)
    return seq


def advance_state_seq(state_path: Path, journal_path: Path) -> None:
    """Re-anchor ``state.next_monotonic_seq`` to ``highest_seq + 1``.

    Mirrors `cli/start.py`'s post-panel advance. Verify never mutates
    ``state.phase``; only the seq pointer advances so subsequent CLI
    ceremonies read a fresh horizon. Defensive: never regress the pointer.
    Any read or write error is swallowed (best-effort sync — the journal
    is already authoritative).
    """
    from sdlc.journal._seq import _read_highest_seq  # deferred (private)
    from sdlc.state import read_state_or_recover, write_state_atomic_sync  # deferred

    highest_seq = _read_highest_seq(journal_path.resolve())
    try:
        pre = read_state_or_recover(state_path.resolve(), journal_path.resolve())
    except StateError:
        return
    if pre is None:
        return
    next_seq = max(pre.next_monotonic_seq, highest_seq + 1)
    if next_seq <= pre.next_monotonic_seq:
        return
    try:
        write_state_atomic_sync(
            pre.model_copy(update={"next_monotonic_seq": next_seq}),
            target=state_path,
        )
    except OSError:
        return


# Re-export used by the orchestrator so `_verify_dispatch.py` only needs to
# import one symbol per ceremony stage (parse → build → append → emit → sync).
# Mapping kept here so updates to the post-dispatch surface localise to one
# module.
_POST_DISPATCH_SURFACE: Final[Mapping[str, object]] = {
    "parse_verdict_envelope": parse_verdict_envelope,
    "build_verification_entry": build_verification_entry,
    "append_and_persist_frontmatter": append_and_persist_frontmatter,
    "emit_artifact_verified": emit_artifact_verified,
    "advance_state_seq": advance_state_seq,
}
