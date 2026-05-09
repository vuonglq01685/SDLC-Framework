"""Private helper module for abstraction-adequacy CI test (Story 1.14).

Factored out of test_abstraction_adequacy.py so tests/unit/integration/ can import
helpers without cross-module test import ambiguity. Single-underscore prefix marks
this as private but keeps it importable for unit-test seams.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.runtime import AgentResult
from sdlc.state.model import State

_SEED_PROMPT: Final[str] = "abstraction-adequacy seed prompt"
_SEED_CONTEXT: Final[Mapping[str, object]] = MappingProxyType(
    {"workflow_step": "abstraction-adequacy"}
)
_FROZEN_TS: Final[str] = "2026-05-08T00:00:00Z"
_ACTOR: Final[str] = "agent:abstraction-adequacy"
_TARGET_ID: Final[str] = "epic-abstraction-adequacy"


def _canonicalize_state_for_hash(state: State) -> bytes:
    """Hash-canonical form: no trailing newline (Architecture §513).

    Differs from _canonicalize_state in atomic.py (which appends b'\\n' for disk writes).
    """
    return json.dumps(
        state.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _state_hash(state: State) -> str:
    """Return sha256:<hex> of the hash-canonical state bytes."""
    return "sha256:" + hashlib.sha256(_canonicalize_state_for_hash(state)).hexdigest()


def _synthesize_hook_payload(result: AgentResult, seq: int) -> HookPayload:
    """Deferred-substrate stub for hook synthesis (Story 1.14 test-only).

    Hook synthesis is a Story-1.14-test-only stub; the real chain lands in Story 2A.4.
    Story 2B.3 will switch this to the real hooks/runner.py invocation — at that point
    the synthesizer code is deleted and the test asserts the chain's actual emission order.

    content_hash_before chain is intentionally simplified for the substrate test;
    Story 2A.4 owns the real chain.
    """
    if not result.tool_calls:
        raise ValueError(
            "synthesizer expects exactly one tool_call in v1 fixtures; got empty tool_calls"
        )
    tool_call = result.tool_calls[0]
    target = tool_call["args"]["target"]
    content_hash = str(tool_call["args"]["content_hash"])
    return HookPayload(
        schema_version=1,
        hook_name="abstraction-adequacy-synth",
        target_path=str(target),
        target_kind="epic",
        content_hash_before=None if seq == 0 else content_hash,
        write_intent="create",
    )


def _build_journal_entry(
    seq: int,
    before_hash: str | None,
    after_hash: str,
    agent_result: AgentResult,
) -> JournalEntry:
    """Build a JournalEntry for one pipeline step.

    tool_calls are intentionally NOT in the payload — they are captured by HookPayload
    synthesis. Duplicating them here would make the journal a secondary source of truth
    for the hook surface, violating the substrate's separation of concerns.
    """
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=_FROZEN_TS,
        actor=_ACTOR,
        kind="state_mutation",
        target_id=_TARGET_ID,
        before_hash=before_hash,
        after_hash=after_hash,
        payload={
            "output_text": agent_result.output_text,
            "tokens_in": agent_result.tokens_in,
            "tokens_out": agent_result.tokens_out,
        },
    )
