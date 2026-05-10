"""Tests for hooks/payload.py builder helpers (AC1, Story 2A.4 Task 1)."""

from __future__ import annotations

import pydantic
import pytest

from sdlc.hooks.payload import (
    build_phase_advance_payload,
    build_signoff_record_payload,
    build_write_intent_payload,
)


@pytest.mark.unit
class TestBuildWriteIntentPayload:
    def test_valid_no_hash(self) -> None:
        p = build_write_intent_payload(
            hook_name="naming_validator",
            target_path="01-Requirement/04-Epics/EPIC-stripe-webhook.json",
            write_intent="create epic JSON",
        )
        assert p.target_kind == "write_intent"
        assert p.content_hash_before is None
        assert p.hook_name == "naming_validator"
        assert p.schema_version == 1

    def test_valid_with_hash(self) -> None:
        sha = "sha256:" + "a" * 64
        p = build_write_intent_payload(
            hook_name="phase_gate",
            target_path="02-Architecture/01-UX/01-tokens.md",
            write_intent="update tokens",
            content_hash_before=sha,
        )
        assert p.content_hash_before == sha

    def test_invalid_hash_raises(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            build_write_intent_payload(
                hook_name="phase_gate",
                target_path="02-Architecture/01-UX/01-tokens.md",
                write_intent="update tokens",
                content_hash_before="notahash",
            )


@pytest.mark.unit
class TestBuildPhaseAdvancePayload:
    def test_target_kind(self) -> None:
        p = build_phase_advance_payload(
            hook_name="phase_gate",
            target_path="02-Architecture/01-UX/01-tokens.md",
            write_intent="signoff phase 1",
        )
        assert p.target_kind == "phase_advance"

    def test_no_hash(self) -> None:
        p = build_phase_advance_payload(
            hook_name="phase_gate",
            target_path="02-Architecture/01-UX/01-tokens.md",
            write_intent="signoff phase 1",
        )
        assert p.content_hash_before is None


@pytest.mark.unit
class TestBuildSignoffRecordPayload:
    def test_target_kind(self) -> None:
        p = build_signoff_record_payload(
            hook_name="phase_gate",
            target_path=".claude/state/signoffs/phase-1.yaml",
            write_intent="signoff phase 1",
        )
        assert p.target_kind == "signoff_record"

    def test_schema_version_one(self) -> None:
        p = build_signoff_record_payload(
            hook_name="phase_gate",
            target_path=".claude/state/signoffs/phase-2.yaml",
            write_intent="signoff phase 2",
        )
        assert p.schema_version == 1
