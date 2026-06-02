"""Adopt three-pass package (Story 3.1, D1(a) `passes/` layout).

The driver (`sdlc.adopt.driver`) calls these in strict order:

  Pass 1 — `detection.detect_existing`   (Story 3.2 fills the heuristics)
  Pass 2 — `symlink_offer.offer_symlinks` (Story 3.3 fills the interactive offer)
  Pass 3 — `stamp.mark_imported`          (Story 3.4 fills the stamping)

In Story 3.1 each pass is a minimal, typed seam so the orchestration ordering, journaling,
and report-writing contract can be implemented and tested against a stable boundary.
"""

from __future__ import annotations

__all__ = ["detection", "stamp", "symlink_offer"]
