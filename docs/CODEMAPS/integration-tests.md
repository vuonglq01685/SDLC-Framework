# Codemap: Integration Tests

## Overview

The `tests/integration/` directory contains end-to-end pipeline tests that exercise multiple substrate modules together. These tests are marked `@pytest.mark.integration` and run in the `quality-gates` CI job.

## Key Files

### `tests/integration/test_abstraction_adequacy.py`

The abstraction-adequacy CI gate (Story 1.14 / ADR-017). Runs a deterministic 8-step pipeline against `MockAIRuntime` and asserts byte-equality of the produced HookPayload sequence and final state.json against checked-in golden files.

**Pipeline steps:**
1. init — create `.claude/state/` via `tmp_path`
2. scan stub — returns `State(schema_version=1, next_monotonic_seq=0, epics={})` (Story 1.15 replaces this)
3. mock dispatch ×2 — `MockAIRuntime.dispatch(_SEED_PROMPT, _SEED_CONTEXT)` twice (same input; exercises determinism)
4. hook synthesis stub — `_synthesize_hook_payload(result, seq)` per dispatch (Story 2A.4 replaces this)
5. journal append ×2 — `journal.append_sync(entry, journal_path)` with chained before/after hashes
6. state projection — `project_from_journal(journal_path)` (pure function)
7. atomic state write — `write_state_atomic_sync(final_state, target=state_path)`
8. golden assertions — byte-equality to `tests/fixtures/abstraction_adequacy/expected_*.json`

**Parameterization:** `_RUNTIME_FACTORIES = [_mock_factory]`. Story 2B.3 extends to `[_mock_factory, _claude_factory]` — one-line change (ADR-017, Decision 3).

**POSIX-only:** skipped on Windows (`journal.append_sync` + `write_state_atomic_sync` require `fcntl`/`O_APPEND`).

### `tests/integration/_abstraction_adequacy_helpers.py`

Private helper module (non-test, importable by unit tests). Contains:

- `_SEED_PROMPT`, `_SEED_CONTEXT`, `_FROZEN_TS`, `_ACTOR`, `_TARGET_ID` — determinism constants
- `_canonicalize_state_for_hash(state)` — canonical bytes without trailing `\n` (Architecture §513 hash variant)
- `_state_hash(state)` — `"sha256:" + hexdigest`
- `_synthesize_hook_payload(result, seq)` — builds `HookPayload` from `AgentResult.tool_calls[0]`
- `_build_journal_entry(seq, before_hash, after_hash, agent_result)` — builds `JournalEntry`

## Fixtures

### `tests/fixtures/mock_responses/abstraction-adequacy.yaml`

Seed fixture for `workflow_step="abstraction-adequacy"`. Key: `sha256:1944573a27dc9cc1fb5fc366b4e6df342aa013515e5e686ecfc70c27d2b9b62d` (sha256 of `"abstraction-adequacy seed prompt"`). Contains one `write_artifact` tool_call producing `EPIC-abstraction-adequacy.json`.

### `tests/fixtures/abstraction_adequacy/`

Golden files (byte-stable across OS/Python-version matrix):

- `expected_hook_payloads.json` — JSON array of 2 `HookPayload` objects (seq 0 and seq 1)
- `expected_state.json` — final `State` after projecting the 2-entry journal: `{"epics":{},"next_monotonic_seq":2,"schema_version":1}`
- `README.md` — regen history and instructions

**Regeneration:** set `_REGENERATE_GOLDENS = True` in `test_abstraction_adequacy.py`, run the test (POSIX only), inspect the diff, flip back to `False`.

## Unit-Test Companion

`tests/unit/integration/test_abstraction_adequacy_helpers.py` — unit tests for the determinism helpers (marked `@pytest.mark.unit`). Imports helpers from `integration._abstraction_adequacy_helpers` via pytest's `sys.path` prepend (`tests/` is added to path by pytest's `prepend` importmode).

## Forward-Compat Notes

| Story | Change | Impact on this test |
|-------|--------|---------------------|
| 1.15 | `engine.scanner.scan` ships | Replace scan stub; regen goldens |
| 2A.4 | `hooks.runner.run_hook_chain` ships | Replace synthesizer stub; regen goldens |
| 2B.3 | `ClaudeAIRuntime` ships | Extend `_RUNTIME_FACTORIES`; goldens MUST hold for both factories |

## Related ADR

[ADR-017](../decisions/ADR-017-abstraction-adequacy-ci-contract.md) — records the CI contract design, parameterization strategy, golden-file discipline, and revisit-by trigger.
