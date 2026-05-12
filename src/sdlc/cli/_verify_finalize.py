"""Verify-ceremony final stages (Story 2A.10, post-review Cluster C-J).

Two helpers, called from :func:`sdlc.cli._verify_dispatch.invoke_dispatch`
after the frontmatter rewrite lands:

  * :func:`emit_verified_and_advance` — malformed-verdict flag + warning,
    journal ``artifact_verified`` with all four hashes, state-seq advance
    via :func:`sdlc.cli._verify_post.advance_state_seq_or_emit`.
  * :func:`emit_user_output_and_exit` — JSON envelope or human line; non-
    zero exit when verdict is failed/advisory per P30/DC10.

Extracted from ``_verify_dispatch.py`` (LOC-cap split) so each verify
module stays under Architecture §1052-§1112 / NFR-MAINT-3 400-LOC cap.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from sdlc.cli._verify_post import (
    advance_state_seq_or_emit,
    emit_artifact_verified,
    is_verdict_malformed,
)
from sdlc.cli.output import echo, emit_json

__all__ = ("emit_user_output_and_exit", "emit_verified_and_advance")


def emit_verified_and_advance(
    ctx: typer.Context,
    *,
    json_mode: bool,
    output_text: str,
    journal_path: Path,
    state_path: Path,
    artifact_id: str,
    entry: object,  # _Verification
    verification_index: int,
    before_hash: str,
    after_hash: str,
) -> None:
    """P36/DC9 + P13/DC4: malformed-verdict flag + stderr warning, emit
    `artifact_verified` w/ all four hashes, advance state seq with distinct
    ``ERR_STATE_CORRUPT`` / ``ERR_STATE_SYNC_FAILED`` envelopes.
    """
    payload_malformed = is_verdict_malformed(output_text)
    if payload_malformed and not json_mode:
        echo(
            "[WARN] verifier payload malformed; row recorded as advisory + "
            "flagged via `payload.verifier_payload_malformed=true`",
            err=True,
            ctx=ctx,
        )
    asyncio.run(
        emit_artifact_verified(
            journal_path=journal_path,
            rel_path=artifact_id,
            entry=entry,  # type: ignore[arg-type]
            verification_index=verification_index,
            verifier_payload_malformed=payload_malformed,
            before_hash=before_hash,
            after_hash=after_hash,
        )
    )
    advance_state_seq_or_emit(ctx, state_path=state_path, journal_path=journal_path)


def emit_user_output_and_exit(
    ctx: typer.Context,
    *,
    json_mode: bool,
    artifact_id: str,
    entry: object,  # _Verification
    verification_index: int,
    total_verifications: int,
) -> None:
    """Print JSON envelope or human line; raise ``typer.Exit(1)`` per P30/DC10
    when verdict is failed/advisory.
    """
    status = entry.status  # type: ignore[attr-defined]
    if json_mode:
        emit_json(
            "verify",
            {
                "artifact_id": artifact_id,
                "verifier": entry.verifier,  # type: ignore[attr-defined]
                "status": status,
                "verification_index": verification_index,
                "content_hash_at_verify": entry.content_hash_at_verify,  # type: ignore[attr-defined]
                "total_verifications": total_verifications,
            },
            ctx=ctx,
        )
    else:
        echo(
            f"sdlc verify: appended verification[{verification_index}] ({status}) to {artifact_id}",
            ctx=ctx,
        )
    if status in ("failed", "advisory"):
        raise typer.Exit(code=1)
