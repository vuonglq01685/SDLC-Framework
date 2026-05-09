from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from sdlc.contracts.hook_payload import HookPayload

# Imports kept in semantic order matching __all__ per Architecture §1238 enumeration:
# JournalEntry (prototype) first, then the other 4 in architecture-canonical order.
# isort sorting is suppressed by the noqa pragmas; ruff/I001 enforced via __all__-only convention.
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.contracts.resume_token import ResumeToken
from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec

__all__ = (  # noqa: RUF022
    "JournalEntry",
    "ResumeToken",
    "HookPayload",
    "SpecialistFrontmatter",
    "WorkflowSpec",
)

# Wire-format lock registry (Story 1.21, Decision F3, ADR-024).
# Single source of truth for the canonical (slug, ContractCls) iteration order shared by
# `scripts/freeze_wireformat_snapshots.py` and `tests/contracts/test_wireformat_immutability.py`.
# Private (NOT in __all__): adding a 6th contract requires an ADR amendment + new snapshot,
# so callers should not import this transitively.
_WIRE_FORMAT_REGISTRY: Final[tuple[tuple[str, type[BaseModel]], ...]] = (
    ("journal_entry", JournalEntry),
    ("resume_token", ResumeToken),
    ("hook_payload", HookPayload),
    ("specialist_frontmatter", SpecialistFrontmatter),
    ("workflow_spec", WorkflowSpec),
)
