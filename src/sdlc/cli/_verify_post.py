"""Post-dispatch ceremony for `sdlc verify` (Story 2A.10).

Private CLI-internal helpers run AFTER dispatch returns: verdict parsing,
``_Verification`` row construction + frontmatter append, ``artifact_verified``
journal emit, defensive ``state.next_monotonic_seq`` re-anchor. PUBLIC
surface stays in :mod:`sdlc.cli.verify` (D1).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli._verify_frontmatter import (
    ALLOWED_STATUSES,
    VERIFIER_NOTE_MAX_LEN,
    _append_verification,
    _parse_frontmatter,
    _serialize_artifact,
    _Verification,
)
from sdlc.cli._verify_io import atomic_write_text
from sdlc.cli.output import emit_error
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import StateError

if TYPE_CHECKING:
    import typer

__all__ = (  # noqa: RUF022 — pipeline order, not alphabetical
    "parse_verdict_envelope",
    "is_verdict_malformed",
    "check_verifier_note_overflow",
    "parse_verdict_with_overflow_check",
    "build_verification_entry",
    "append_and_persist_frontmatter",
    "assert_artifact_not_raced",
    "emit_artifact_verified",
    "advance_state_seq",
    "advance_state_seq_or_emit",
    "SLASH_COMMAND",
    "REQUIRED_PHASE",
)

SLASH_COMMAND: Final[str] = "/sdlc-verify"
REQUIRED_PHASE: Final[int] = 1


def parse_verdict_envelope(output_text: str) -> tuple[str, str | None]:
    """Parse the verifier's ``output_text`` into ``(status, note)``.

    P36 / DC9 / DR7 (post-review 2026-05-12 Cluster C-J): malformed payloads
    fall back to ``status="advisory"`` (NOT silently "verified"). The DR7
    rationale: a verifier that returns an unparseable verdict is exhibiting
    behaviour the operator MUST see — "verified" silently approves the
    artifact based on a non-decision, which is the most severe correctness
    failure mode. "advisory" routes through DC10's non-zero exit path so
    the verify ceremony surfaces the malformed payload to CI/operators
    while still appending a defensible audit row.

    Use :func:`is_verdict_malformed` alongside this function when the
    caller needs to know whether coercion happened (for journal payload
    flagging per P36 / `verifier_payload_malformed`).
    """
    txt = output_text.strip()
    if not txt:
        return "advisory", None  # P36: empty payload is a non-decision -> advisory
    try:
        parsed: object = json.loads(txt)
    except json.JSONDecodeError:
        return "advisory", None  # P36: malformed JSON -> advisory
    if not isinstance(parsed, dict):
        return "advisory", None  # P36: non-dict JSON -> advisory
    # P28 (post-review 2026-05-12): isinstance guard before `in ALLOWED_STATUSES`.
    # Previously a non-hashable verdict (e.g. `{"verdict": ["verified"]}`) raised
    # TypeError on `in frozenset` and propagated as an unenveloped traceback.
    raw_verdict = parsed.get("verdict")
    status: str = (
        raw_verdict
        if isinstance(raw_verdict, str) and raw_verdict in ALLOWED_STATUSES
        else "advisory"  # P36: unknown / non-string / missing verdict -> advisory
    )
    raw_note = parsed.get("note")
    # P14 / DC1=(a): notes >MAX_LEN MUST be rejected upstream (see
    # :func:`check_verifier_note_overflow`); by the time we reach here the
    # contract is already enforced. We still slice defensively in case a
    # future call-site forgets the precheck — keeps this helper safe to
    # call standalone.
    note: str | None = (
        raw_note[:VERIFIER_NOTE_MAX_LEN] if isinstance(raw_note, str) and raw_note else None
    )
    return status, note


def is_verdict_malformed(output_text: str) -> bool:
    """P36 / DC9 / DR7: True iff :func:`parse_verdict_envelope` would coerce
    the payload to ``advisory`` (verifier did NOT return well-formed
    ``{"verdict": <ALLOWED_STATUS>, ...}``). Drives the
    ``verifier_payload_malformed`` journal flag.
    """
    txt = output_text.strip()
    if not txt:
        return True
    try:
        parsed: object = json.loads(txt)
    except json.JSONDecodeError:
        return True
    if not isinstance(parsed, dict):
        return True
    raw_verdict = parsed.get("verdict")
    return not (isinstance(raw_verdict, str) and raw_verdict in ALLOWED_STATUSES)


def check_verifier_note_overflow(output_text: str) -> int | None:
    """P14 / DC1=(a): return ``len(raw_note)`` if the verifier's note exceeds
    ``VERIFIER_NOTE_MAX_LEN``, else ``None``. Surfaced upstream as
    ``ERR_VERIFIER_NOTE_OVERFLOW`` to preserve audit-trail integrity (a
    5000-char note is a behaviour signal, not noise to truncate).
    Malformed-payload cases short-circuit to ``None`` — covered by the
    existing :func:`parse_verdict_envelope` defensive fallbacks.
    """
    txt = output_text.strip()
    if not txt:
        return None
    try:
        parsed: object = json.loads(txt)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    raw_note = parsed.get("note")
    if isinstance(raw_note, str) and len(raw_note) > VERIFIER_NOTE_MAX_LEN:
        return len(raw_note)
    return None


def build_verification_entry(
    *,
    verifier: str,
    status: str,
    note: str | None,
    body_hash: str,
) -> _Verification:
    """Construct a single ``_Verification`` row from the parsed verdict.

    P36 / DC9 (post-review 2026-05-12 Cluster C-J): out-of-band status
    coerces to ``advisory`` (NOT ``verified``) so silent verifier
    misbehaviour surfaces as a flagged advisory row + non-zero exit per
    DC10. Aligns with :func:`parse_verdict_envelope` post-DR7 default.
    """
    if status not in ALLOWED_STATUSES:
        status = "advisory"
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

    The write uses :func:`sdlc.cli._verify_io.atomic_write_text` (PC3
    post-review patch) so a crash mid-write leaves either the pre-state
    or the new state on disk — never a truncated artifact.
    """
    fresh_content = artifact_path.read_text(encoding="utf-8")
    fresh_fm, fresh_body = _parse_frontmatter(fresh_content)
    new_fm = _append_verification(fresh_fm, entry)
    new_content = _serialize_artifact(new_fm, fresh_body)
    atomic_write_text(artifact_path, new_content)
    verifications_list = new_fm["verifications"]
    assert isinstance(verifications_list, list)
    return new_fm, len(verifications_list) - 1


async def emit_artifact_verified(
    *,
    journal_path: Path,
    rel_path: str,
    entry: _Verification,
    verification_index: int,
    verifier_payload_malformed: bool = False,
    before_hash: str | None = None,
    after_hash: str | None = None,
) -> int:
    """Append the ``kind=artifact_verified`` journal entry; return seq used.

    P36/DC9 ``verifier_payload_malformed`` flag distinguishes coerced-from-
    malformed advisories from verifier-decided advisories (stable payload
    shape; always emitted).

    P29/DC8=(2) ``before_hash`` / ``after_hash`` are **whole-file** SHA-256
    of artifact bytes immediately before/after the frontmatter rewrite.
    ``payload.content_hash_at_verify`` continues to pin the **body-only**
    hash (2A.12 drift detection semantics — unchanged). When
    ``before_hash is None`` the legacy ``after_hash=content_hash_at_verify``
    convention is preserved for backward-compat.
    """
    from sdlc.dispatcher._panel_helpers import _allocate_seq  # deferred (private)
    from sdlc.journal import append as journal_append  # deferred

    # P15 (post-review 2026-05-12): always emit `verifier_note` key (None when
    # absent) so downstream consumers — dashboards, Story 2A.12 sdlc-signoff —
    # can expect a stable payload shape without per-key existence guards.
    payload: dict[str, object] = {
        "slash_command": SLASH_COMMAND,
        "phase": REQUIRED_PHASE,
        "verifier": entry.verifier,
        "status": entry.status,
        "content_hash_at_verify": entry.content_hash_at_verify,
        "verification_index": verification_index,
        "verifier_note": entry.verifier_note,
        # P36 / DC9: always emit so payload shape is stable.
        "verifier_payload_malformed": verifier_payload_malformed,
    }
    seq = await _allocate_seq(journal_path)
    je = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=now_rfc3339_utc_ms(),
        actor="cli",
        kind="artifact_verified",
        target_id=rel_path,
        # P29 / DC8=(2): pre/post whole-file hashes if computed; else
        # legacy semantics (before=None, after=body-only hash).
        before_hash=before_hash,
        after_hash=after_hash if after_hash is not None else entry.content_hash_at_verify,
        payload=payload,
    )
    await journal_append(je, journal_path)
    return seq


def advance_state_seq(state_path: Path, journal_path: Path) -> None:
    """Re-anchor ``state.next_monotonic_seq`` to ``highest_seq + 1``.

    Mirrors `cli/start.py`'s post-panel advance. Verify never mutates
    ``state.phase``; only the seq pointer advances so subsequent CLI
    ceremonies read a fresh horizon. The pointer never regresses (the
    `max(...)` guard ensures monotonic-only updates).

    P13 / DC4=(1) (post-review 2026-05-12 Cluster C-J): errors are NOT
    silently swallowed. The function bubbles two distinct error types so
    the caller (``_verify_dispatch.invoke_dispatch``) can distinguish:

      * :class:`sdlc.errors.StateError` — logical corruption of
        ``state.json`` (terminal; caller emits ``ERR_STATE_CORRUPT`` +
        suggests ``sdlc rebuild-state``).
      * :class:`OSError` — transient I/O failure on write (retryable;
        caller emits ``ERR_STATE_SYNC_FAILED``).

    The function still no-ops gracefully on two designed-in cases:
    ``read_state_or_recover`` returning ``None`` (state file missing),
    and ``next_seq <= pre.next_monotonic_seq`` (already caught up).
    """
    from sdlc.journal._seq import _read_highest_seq  # deferred (private)
    from sdlc.state import read_state_or_recover, write_state_atomic_sync  # deferred

    highest_seq = _read_highest_seq(journal_path.resolve())
    # P13: re-raise StateError so the orchestrator surfaces ERR_STATE_CORRUPT.
    pre = read_state_or_recover(state_path.resolve(), journal_path.resolve())
    if pre is None:
        return
    next_seq = max(pre.next_monotonic_seq, highest_seq + 1)
    if next_seq <= pre.next_monotonic_seq:
        return
    # P13: re-raise OSError so the orchestrator surfaces ERR_STATE_SYNC_FAILED.
    write_state_atomic_sync(
        pre.model_copy(update={"next_monotonic_seq": next_seq}),
        target=state_path,
    )


# ---------------------------------------------------------------------------
# Orchestrator wrappers (PC + DC bundle, post-review 2026-05-12 Cluster C-J)
#
# The three helpers below translate the pure post-dispatch primitives into
# `emit_error`-bearing forms that the CLI orchestrator invokes directly.
# Extracted here (from _verify_dispatch.py) under the §1052-§1112 / NFR-MAINT-3
# 400-LOC cap. Each wraps exactly one P-cluster patch:
#
#   * parse_verdict_with_overflow_check  →  P14 / DC1=(a)
#   * assert_artifact_not_raced          →  P10 / DC2
#   * advance_state_seq_or_emit          →  P13 / DC4=(1)
# ---------------------------------------------------------------------------


def parse_verdict_with_overflow_check(
    ctx: typer.Context, output_text: str
) -> tuple[str, str | None]:
    """P14 / DC1=(a): reject verifier notes >VERIFIER_NOTE_MAX_LEN BEFORE
    :func:`parse_verdict_envelope`'s silent truncation; preserves audit-trail
    integrity. Returns the parsed ``(status, note)`` on success.
    """
    overflow_len = check_verifier_note_overflow(output_text)
    if overflow_len is not None:
        emit_error(
            "ERR_VERIFIER_NOTE_OVERFLOW",
            f"verifier note exceeded {VERIFIER_NOTE_MAX_LEN} chars (got {overflow_len}); "
            "refusing silent truncation",
            ctx=ctx,
            details={"max_len": VERIFIER_NOTE_MAX_LEN, "actual_len": overflow_len},
        )
    return parse_verdict_envelope(output_text)


def assert_artifact_not_raced(
    *,
    ctx: typer.Context,
    artifact_path: Path,
    artifact_id: str,
    preflight_body_hash: str,
) -> None:
    """P10 / DC2: close TOCTOU between pre-flight content read and post-
    dispatch frontmatter rewrite. Fail-loud (`ERR_ARTIFACT_RACED`) if the
    body hash changed between pre-flight and now.
    """
    from sdlc.cli._verify_frontmatter import _compute_body_hash  # deferred

    try:
        fresh_content = artifact_path.read_text(encoding="utf-8")
    except OSError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"artifact unreadable after dispatch: {exc}",
            ctx=ctx,
            details={"artifact_id": artifact_id, "path": str(artifact_path)},
        )
    fresh_body_hash = _compute_body_hash(fresh_content)
    if fresh_body_hash != preflight_body_hash:
        emit_error(
            "ERR_ARTIFACT_RACED",
            "artifact body changed between pre-flight and post-dispatch "
            "(content_hash_at_verify mismatch); refusing to append a "
            "verification row pinned to stale bytes",
            ctx=ctx,
            details={
                "artifact_id": artifact_id,
                "preflight_hash": preflight_body_hash,
                "post_dispatch_hash": fresh_body_hash,
            },
        )


def advance_state_seq_or_emit(ctx: typer.Context, *, state_path: Path, journal_path: Path) -> None:
    """P13 / DC4=(1): surface state-sync failures via distinct envelopes —
    terminal corruption (``ERR_STATE_CORRUPT``) vs retryable I/O
    (``ERR_STATE_SYNC_FAILED``). Wrapping the call here keeps
    ``invoke_dispatch`` under the mccabe complexity cap.
    """
    try:
        advance_state_seq(state_path, journal_path)
    except StateError as exc:
        emit_error(
            "ERR_STATE_CORRUPT",
            f"state corrupted during seq advance: {exc}; run `sdlc rebuild-state`",
            ctx=ctx,
            details={"state_path": str(state_path)},
        )
    except OSError as exc:
        emit_error(
            "ERR_STATE_SYNC_FAILED",
            f"state.next_monotonic_seq write failed: {exc}; retry is safe",
            ctx=ctx,
            details={"state_path": str(state_path), "error": str(exc)},
        )


# Re-export used by the orchestrator so `_verify_dispatch.py` only needs to
# import one symbol per ceremony stage (parse → build → append → emit → sync).
# Mapping kept here so updates to the post-dispatch surface localise to one
# module.
_POST_DISPATCH_SURFACE: Final[Mapping[str, object]] = {
    "parse_verdict_envelope": parse_verdict_envelope,
    "parse_verdict_with_overflow_check": parse_verdict_with_overflow_check,
    "build_verification_entry": build_verification_entry,
    "append_and_persist_frontmatter": append_and_persist_frontmatter,
    "assert_artifact_not_raced": assert_artifact_not_raced,
    "emit_artifact_verified": emit_artifact_verified,
    "advance_state_seq": advance_state_seq,
    "advance_state_seq_or_emit": advance_state_seq_or_emit,
}
