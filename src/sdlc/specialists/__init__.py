"""Specialist registry + manifest validation (Story 2A.2, Architecture §836-§839).

Public surface:
  load_registry(agents_dir) -> SpecialistRegistry
  load_specialist(path)     -> Specialist
  validate_workflow_refs(spec, registry) -> None
  validate_internal_links(registry)      -> None
  SpecialistRegistry
  Specialist

NOTE: SpecialistRegistry is the ONLY public way to enumerate specialists.
Direct calls to load_specialist outside specialists/ and tests are a
code-review-blocking pattern (Architecture §1064, mirroring Story 2A.1 precedent).

scripts/validate_specialists.py wiring is DEFERRED to Story 2A.3+ (AC7 chose D3).
See _bmad-output/implementation-artifacts/deferred-work.md for the debt entry.
"""

from __future__ import annotations

from sdlc.specialists._frontmatter import Specialist, load_specialist
from sdlc.specialists._registry import SpecialistRegistry, load_registry
from sdlc.specialists._validator import validate_internal_links, validate_workflow_refs

__all__ = [
    "Specialist",
    "SpecialistRegistry",
    "load_registry",
    "load_specialist",
    "validate_internal_links",
    "validate_workflow_refs",
]
