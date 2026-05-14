"""Shared CLI helper: check if an artifact contains the canonical BOUNDARY_LINE.

Promoted from ``sdlc.cli.verify._artifact_contains_boundary`` during code review
of Story 2A.13 (P13) — was a private helper inside ``verify.py`` but reused by
``cli/ux.py`` (Phase 2 UX track) to enforce NFR-SEC-3 prompt-injection-boundary
invariants on user-authored Phase 1 artifacts. Centralizing here so future Phase 2
specialists do not import a private symbol from a sibling CLI module.

The function is *content-only* — no I/O. Path-handling caller decides what to do
on a positive match (typically: ``emit_error("ERR_ARTIFACT_CONTAINS_BOUNDARY", ...)``).
"""

from __future__ import annotations

from sdlc.dispatcher.prompts import BOUNDARY_LINE, normalize_for_boundary_check


def artifact_contains_boundary(content: str) -> bool:
    """Return True iff ``content`` contains the canonical BOUNDARY_LINE.

    Normalizes whitespace and line endings before comparison so an artifact that
    embeds the boundary across mixed CRLF/LF or with leading/trailing spaces
    cannot evade the check.
    """
    return normalize_for_boundary_check(BOUNDARY_LINE) in normalize_for_boundary_check(content)
