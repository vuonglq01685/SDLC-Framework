from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from sdlc.contracts import (
    HookPayload,
    JournalEntry,
    ResumeToken,
    SpecialistFrontmatter,
    WorkflowSpec,
)

# All 5 contracts with minimal valid kwargs for each.
_ALL_CONTRACTS: list[tuple[type[Any], dict[str, Any]]] = [
    (
        JournalEntry,
        dict(
            monotonic_seq=1,
            ts="2026-05-08T09:42:13.487Z",
            actor="cli",
            kind="state_mutation",
            target_id="EPIC-x",
            before_hash=None,
            after_hash="sha256:" + "a" * 64,
        ),
    ),
    (
        ResumeToken,
        dict(
            phase=1,
            suggested_next_command="/sdlc-start",
            state_hash="sha256:" + "d" * 64,
        ),
    ),
    (
        HookPayload,
        dict(
            hook_name="phase_gate",
            target_path="04-Epics/EPIC-x.json",
            target_kind="epic",
            content_hash_before=None,
            write_intent="create",
        ),
    ),
    (
        SpecialistFrontmatter,
        dict(
            name="req-analyst",
            title="Requirement Analyst",
            icon="\U0001f4dd",
            model="opus",
            description="Drafts PRDs",
        ),
    ),
    (
        WorkflowSpec,
        dict(
            name="sdlc-start",
            slash_command="/sdlc-start",
            primary_agent="orchestrator",
            write_globs={"orchestrator": ["**/*"]},
        ),
    ),
]

_CONTRACT_IDS = [cls.__name__ for cls, _ in _ALL_CONTRACTS]


@pytest.mark.unit
@pytest.mark.parametrize("cls,valid_kwargs", _ALL_CONTRACTS, ids=_CONTRACT_IDS)
def test_schema_version_is_independent_per_contract(
    cls: type[Any], valid_kwargs: dict[str, Any]
) -> None:
    # Step 1: schema_version=1 succeeds for the class under test.
    instance_v1 = cls(schema_version=1, **valid_kwargs)
    assert instance_v1.schema_version == 1

    # Step 2: schema_version=2 fails for the class under test (Decision F3).
    with pytest.raises(ValidationError) as exc_info:
        cls(schema_version=2, **valid_kwargs)
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("schema_version",) for e in errors)

    # Step 3: the OTHER FOUR contracts still construct successfully with schema_version=1
    # — bumping one contract's schema_version must not require lockstep changes.
    for other_cls, other_kwargs in _ALL_CONTRACTS:
        if other_cls is cls:
            continue
        other_instance = other_cls(**other_kwargs)
        assert other_instance.schema_version == 1
