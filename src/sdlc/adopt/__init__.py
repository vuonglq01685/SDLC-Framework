"""`adopt/` — brownfield `sdlc init --adopt` subsystem (Epic 3, FR2).

Net-new top-level subsystem (architecture.md:1084) sitting below `cli/`. Only `cli/` imports
`adopt/`. Public seam (architecture.md:1069): `run_adopt`, `detect_existing`, `offer_symlinks`,
`mark_imported`, `assert_source_untouched`. The internal layout is the D1(a) `passes/` package
(epic-3-dag.md §5), frozen by Story 3.1's review for Stories 3.2-3.7.

Boundary (Rule 6, architecture.md:1110): `adopt/` MUST NOT import `engine/`, `dispatcher/`, or
`runtime/`. Adopt initializes empty state; the engine handles flow afterward.
"""

from __future__ import annotations

from sdlc.adopt.driver import run_adopt
from sdlc.adopt.invariant import assert_source_untouched
from sdlc.adopt.passes.detection import detect_existing
from sdlc.adopt.passes.stamp import mark_imported
from sdlc.adopt.passes.symlink_offer import offer_symlinks

__all__ = [
    "assert_source_untouched",
    "detect_existing",
    "mark_imported",
    "offer_symlinks",
    "run_adopt",
]
