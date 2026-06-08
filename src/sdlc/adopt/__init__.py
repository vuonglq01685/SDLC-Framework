"""`adopt/` — brownfield `sdlc init --adopt` subsystem (Epic 3, FR2).

Net-new top-level subsystem (architecture.md:1084) sitting below `cli/`. Only `cli/` imports
`adopt/`. Public seam (architecture.md:1069): `run_adopt`, `detect_existing`, `offer_symlinks`,
`mark_imported`, `assert_source_untouched`. The internal layout is the D1(a) `passes/` package
(epic-3-dag.md §5), frozen by Story 3.1's review for Stories 3.2-3.7.

Boundary (Rule 6, architecture.md:1110): `adopt/` MUST NOT import `engine/`, `dispatcher/`, or
`runtime/`. Adopt initializes empty state; the engine handles flow afterward.

Lazy exports avoid pulling POSIX-only ``driver`` / ``symlink_offer`` dependencies when tests
import lightweight submodules (``invariant``, ``source_tree``, ``tree_hash``) on any platform.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "assert_source_untouched",
    "detect_existing",
    "mark_imported",
    "offer_symlinks",
    "run_adopt",
]


def __getattr__(name: str) -> Any:
    # Lazy re-exports: importing these eagerly pulls the POSIX-only writer
    # (sdlc.concurrency.io_primitives), which raises ImportError on win32 and would break
    # `import sdlc.adopt.{source_tree,tree_hash,invariant}` collection on every platform.
    # Deferring the import to attribute-access time is the whole point of this seam, so the
    # function-level imports below are intentional (PLC0415 waived per ADR-034 POSIX-only).
    if name == "run_adopt":
        from sdlc.adopt.driver import run_adopt  # noqa: PLC0415

        return run_adopt
    if name == "assert_source_untouched":
        from sdlc.adopt.invariant import assert_source_untouched  # noqa: PLC0415

        return assert_source_untouched
    if name == "detect_existing":
        from sdlc.adopt.passes.detection import detect_existing  # noqa: PLC0415

        return detect_existing
    if name == "mark_imported":
        from sdlc.adopt.passes.stamp import mark_imported  # noqa: PLC0415

        return mark_imported
    if name == "offer_symlinks":
        from sdlc.adopt.passes.symlink_offer import offer_symlinks  # noqa: PLC0415

        return offer_symlinks
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
