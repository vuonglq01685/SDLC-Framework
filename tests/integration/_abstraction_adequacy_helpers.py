"""Private helper module for abstraction-adequacy CI test (Story 1.14).

Factored out of test_abstraction_adequacy.py so tests/unit/integration/ can import
helpers without cross-module test import ambiguity. Single-underscore prefix marks
this as private but keeps it importable for unit-test seams.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

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
# Must match state.projection._EPIC_ID_PATTERN = r"\Aepic-[0-9]+\Z" — otherwise
# project_from_journal silently drops the epic-mutation branch and the goldens validate
# only next_monotonic_seq advancement (the abstraction-adequacy gate's main coverage
# surface). Pinned to the matching shape "epic-1" by review of Story 1.14; coverage
# of the pin lives in tests/unit/integration/test_abstraction_adequacy_helpers.py.
_TARGET_ID: Final[str] = "epic-1"


def _normalize_strings(obj: Any) -> Any:
    """Recursively NFC-normalize string values.

    Mirror of sdlc.state.atomic._normalize_strings (Architecture §513). Duplicated
    locally so the helper module stays Windows-importable (state.atomic is POSIX-only,
    raises ImportError at module top on Windows).
    """
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _normalize_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_strings(item) for item in obj]
    return obj


def _canonicalize_state_for_hash(state: State) -> bytes:
    """Hash-canonical form: NFC-normalized, no trailing newline (Architecture §513).

    Differs from atomic._canonicalize_state in ONE place: no terminating b'\\n'
    (hash variant per §513). MUST otherwise match byte-for-byte, including the NFC
    normalization pass — divergence here masks unicode-edge bugs that the on-disk
    canonicalizer would catch.
    """
    payload = _normalize_strings(state.model_dump(mode="json"))
    return json.dumps(
        payload,
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
    try:
        args = tool_call["args"]
        if not isinstance(args, Mapping):
            raise TypeError(f"tool_call['args'] must be a Mapping; got {type(args).__name__}")
        target = args["target"]
        content_hash = args["content_hash"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "tool_call shape mismatch — expected {name, args:{target, content_hash}};"
            f" missing/wrong key: {exc}"
        ) from exc
    if not isinstance(target, str):
        raise ValueError(f"tool_call['args']['target'] must be str; got {type(target).__name__}")
    if not isinstance(content_hash, str):
        raise ValueError(
            f"tool_call['args']['content_hash'] must be str; got {type(content_hash).__name__}"
        )
    return HookPayload(
        schema_version=1,
        hook_name="abstraction-adequacy-synth",
        target_path=target,
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
