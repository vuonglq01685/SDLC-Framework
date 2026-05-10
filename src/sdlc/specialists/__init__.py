"""Specialist registry + manifest validation (Story 2A.2, Architecture §836-§839).

Public surface (built up across Tasks 2-5; current commit lands Task 3 — frontmatter):
  load_registry(agents_dir) -> SpecialistRegistry        [Task 4]
  load_specialist(path)     -> Specialist                [Task 3, this commit]
  validate_workflow_refs(spec, registry) -> None         [Task 5]
  validate_internal_links(registry)      -> None         [Task 5]
  SpecialistRegistry                                     [Task 4]
  Specialist                                             [Task 3, this commit]

NOTE: SpecialistRegistry is the ONLY public way to enumerate specialists.
Direct calls to load_specialist outside specialists/ and tests are a
code-review-blocking pattern (Architecture §1064, mirroring Story 2A.1 precedent).

scripts/validate_specialists.py wiring is DEFERRED to Story 2A.3+ (AC7 chose D3).
See _bmad-output/implementation-artifacts/deferred-work.md for the debt entry.
"""

from __future__ import annotations

from sdlc.specialists._frontmatter import Specialist, load_specialist

__all__ = [
    "Specialist",
    "load_specialist",
]
