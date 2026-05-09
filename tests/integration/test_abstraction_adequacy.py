"""Abstraction-adequacy CI gate (Story 1.14 / Epic 1).

Runs the deterministic pipeline (init → scan-stub → mock dispatch x2 →
hook-synth → journal append → state projection → atomic state write)
against MockAIRuntime and asserts a golden HookPayload sequence and
golden final state.json. Closes Winston's mock-vs-claude drift gap
(Architecture §191, §316, §356, §1185, §1424).

Story 2B.3 extends _RUNTIME_FACTORIES with ClaudeAIRuntime — the
contract there is: "Mock and Claude produce IDENTICAL HookPayload
sequences and IDENTICAL final state.json bytes for the same input."

Deferred substrate (replaced by later stories):
    - scan step      → Story 1.15 (engine.scanner.scan)
    - hook synth     → Story 2A.4 (hooks.runner.run_hook_chain)
    - claude variant → Story 2B.3 (extends _RUNTIME_FACTORIES)

POSIX-only: journal.append_sync + state.write_state_atomic_sync
require fcntl + O_APPEND. Windows skipped at module level.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

from integration._abstraction_adequacy_helpers import (
    _SEED_CONTEXT,
    _SEED_PROMPT,
    _build_journal_entry,
    _synthesize_hook_payload,
)
from sdlc.journal import append_sync
from sdlc.runtime import AIRuntime, MockAIRuntime
from sdlc.state import State, write_state_atomic_sync
from sdlc.state.projection import project_from_journal

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "POSIX-only: journal.append_sync + state.write_state_atomic_sync"
            " require fcntl + O_APPEND"
        ),
    ),
]

_REGENERATE_GOLDENS: Final[bool] = False

_GOLDEN_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "fixtures" / "abstraction_adequacy"
_MOCK_FIXTURES_DIR: Final[Path] = (
    Path(__file__).resolve().parents[1] / "fixtures" / "mock_responses"
)


def _mock_factory(fixtures_dir: Path) -> AIRuntime:
    return MockAIRuntime(fixtures_dir=fixtures_dir)


# EPIC 2B GATE — Story 2B.3 extends this list to [_mock_factory, _claude_factory].
# Both factories MUST produce identical HookPayload sequences and identical final state.json
# bytes (Decision C2, Architecture §1424, FR29). DO NOT add a third factory in v1.
_RUNTIME_FACTORIES: list[Callable[[Path], AIRuntime]] = [_mock_factory]


@pytest.fixture(
    params=_RUNTIME_FACTORIES,
    ids=lambda factory: factory.__name__.lstrip("_"),
)
def runtime(request: pytest.FixtureRequest) -> AIRuntime:
    factory: Callable[[Path], AIRuntime] = request.param
    return factory(_MOCK_FIXTURES_DIR)


def test_abstraction_adequacy_pipeline(tmp_path: Path, runtime: AIRuntime) -> None:
    # Step 1: init — create .claude/state/ directory under tmp_path.
    # Mirrors Story 1.16's future `sdlc init` shape but stays inside the test;
    # cli/init is Story 1.16. Do NOT pre-write state.json or journal.log.
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=False)
    journal_path = state_dir / "journal.log"
    state_path = state_dir / "state.json"

    # Step 2: scan stub — Story 1.15 will replace with engine.scanner.scan when the
    # scanner ships. Story 2B.3 will run the FULL pipeline (with real scan) — at that
    # point this stub disappears and the test is upgraded in lockstep.
    _initial_state = State(schema_version=1, next_monotonic_seq=0, epics={})

    # Step 3: dispatch x2 (same prompt+context — exercise determinism).
    # Two dispatches give a non-trivial event sequence; one dispatch is too small to
    # detect ordering bugs.
    result_1 = asyncio.run(runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT))
    result_2 = asyncio.run(runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT))
    # AC1.8 sanity: dispatches must be byte-deterministic (Story 1.13 AC3)
    assert result_1.model_dump(mode="json") == result_2.model_dump(mode="json"), (
        "non-deterministic dispatch — Story 1.13 AC3 violated"
    )

    # Step 4: hook synthesis (deferred-substrate stub).
    # Hook synthesis is a Story-1.14-test-only stub; the real chain lands in Story 2A.4.
    # Story 2B.3 will switch this to the real hooks/runner.py invocation — at that point
    # the synthesizer code is deleted and the test asserts the chain's actual emission order.
    hp_1 = _synthesize_hook_payload(result_1, seq=0)
    hp_2 = _synthesize_hook_payload(result_2, seq=1)
    synthesized_hook_payloads = [hp_1, hp_2]

    # Step 5: journal append x2 with chained before/after hashes.
    je_0 = _build_journal_entry(
        seq=0,
        before_hash=None,
        after_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        agent_result=result_1,
    )
    # Note: after_hash values are placeholders; the real hash chain is enforced by
    # journal/state coupling in Story 2A.4. The test asserts JOURNAL byte-stability
    # (golden), not hash semantics.
    append_sync(je_0, journal_path=journal_path)
    je_1 = _build_journal_entry(
        seq=1,
        before_hash=je_0.after_hash,
        after_hash="sha256:1111111111111111111111111111111111111111111111111111111111111111",
        agent_result=result_2,
    )
    append_sync(je_1, journal_path=journal_path)

    # Step 6: project final state from the journal (pure function — no I/O writes)
    final_state = project_from_journal(journal_path)

    # Step 7: atomic state.json write
    write_state_atomic_sync(final_state, target=state_path)

    # Step 8: golden assertions (the CI gate)
    actual_hp_bytes = (
        json.dumps(
            [hp.model_dump(mode="json") for hp in synthesized_hook_payloads],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    actual_state_bytes = state_path.read_bytes()

    if _REGENERATE_GOLDENS:
        _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        (_GOLDEN_DIR / "expected_hook_payloads.json").write_bytes(actual_hp_bytes)
        (_GOLDEN_DIR / "expected_state.json").write_bytes(actual_state_bytes)
        pytest.fail(
            "_REGENERATE_GOLDENS=True wrote new goldens; flip back to False"
            " and verify diff before committing.",
            pytrace=False,
        )

    expected_hp_bytes = (_GOLDEN_DIR / "expected_hook_payloads.json").read_bytes()
    expected_state_bytes = (_GOLDEN_DIR / "expected_state.json").read_bytes()
    assert actual_hp_bytes == expected_hp_bytes, (
        "HookPayload sequence drift — see _REGENERATE_GOLDENS docs at end of file"
    )
    assert actual_state_bytes == expected_state_bytes, (
        "Final state.json drift — see _REGENERATE_GOLDENS docs at end of file"
    )


# To regenerate goldens (e.g., after a deliberate fixture change):
#   1. Set _REGENERATE_GOLDENS = True at the top of this file.
#   2. uv run pytest tests/integration/test_abstraction_adequacy.py -m integration
#   3. The test will WRITE the goldens instead of asserting; visually diff the result.
#   4. Set _REGENERATE_GOLDENS = False; commit the new goldens with a justifying message.
# DO NOT regenerate goldens to make a failing test pass without first auditing
# WHY the bytes drifted — drift is the symptom this test exists to catch.
