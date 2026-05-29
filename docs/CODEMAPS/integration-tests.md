# Codemap: Integration Tests

## Overview

The `tests/integration/` directory contains end-to-end pipeline tests that exercise multiple substrate modules together. These tests are marked `@pytest.mark.integration` and run in the `quality-gates` CI job.

## Key Files

### `tests/integration/test_abstraction_adequacy.py`

The abstraction-adequacy CI gate (Story 1.14 / ADR-017). Runs a deterministic 8-step pipeline against `MockAIRuntime` and asserts byte-equality of the produced HookPayload sequence and final state.json against checked-in golden files.

**Pipeline steps:**
1. init — create `.claude/state/` via `tmp_path`
2. scan stub — returns `State(schema_version=1, next_monotonic_seq=0, epics={})` (Story 1.15 replaces this)
3. dispatch ×2 — `dispatch_twice(runtime)` runs `runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT)` twice in one event loop (same input; exercises determinism). `runtime` is parametrized over `_mock_factory` and `_claude_factory`.
4. pre-write hook chain — `run_pre_write_hooks_for_dispatches(...)` runs the real `run_hook_chain` per dispatch (Story 2B.3 replaced the synth stub)
5. journal append ×2 — `journal.append_sync(entry, journal_path)` with chained before/after hashes
6. state projection — `project_from_journal(journal_path)` (pure function)
7. atomic state write — `write_state_atomic_sync(final_state, target=state_path)`
8. golden assertions — byte-equality to `tests/fixtures/abstraction_adequacy/expected_*.json`; bytes recorded per runtime, then `test_cross_runtime_byte_identity` (ordered last by `conftest.py`) asserts mock-vs-claude byte identity (AC2/D2)

**Parameterization:** `_RUNTIME_FACTORIES = [_mock_factory, _claude_factory]` (Story 2B.3 — both runtimes asserted to produce byte-identical hook payloads + state.json; ADR-017, Decision 3). `# DO NOT add a third factory in v1`.

**POSIX-only:** skipped on Windows (`journal.append_sync` + `write_state_atomic_sync` require `fcntl`/`O_APPEND`).

### `tests/integration/_abstraction_adequacy_helpers.py`

Private helper module (non-test, importable by unit tests). Contains:

- `_SEED_PROMPT`, `_SEED_CONTEXT`, `_FROZEN_TS`, `_ACTOR`, `_TARGET_ID` — determinism constants
- `_canonicalize_state_for_hash(state)` — canonical bytes without trailing `\n` (Architecture §513 hash variant)
- `_state_hash(state)` — `"sha256:" + hexdigest`
- `_build_pre_chain_input_payload(result, seq)` — builds the `HookPayload` fed into `run_hook_chain`; falls back to seed-stable target/hash when `tool_calls` is empty (Claude v1)
- `dispatch_twice(runtime)` / `run_pre_write_hooks_for_dispatches(...)` — one-loop double dispatch + real pre-write hook chain
- `fail_if_xdist_parallel(config)` — fail-loud guard: the capture registry is a module global incompatible with pytest-xdist
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

## Story 1.17 Integration Tests

### `tests/integration/test_walking_skeleton_e2e.py`

End-to-end subprocess tests for the v0.2 walking skeleton: `sdlc init → sdlc scan → sdlc status`.

- Skips on Windows for scan-related tests (`journal.append_sync` is POSIX-only).
- Verifies exit codes, JSON envelopes, `phase_name`, and `last_updated_ts` after scan.
- `_SKIP_NO_UV` guard skips all tests when `uv` is not on PATH.

### `tests/integration/test_no_color_every_command.py`

Parametrized subprocess tests: every subcommand × every no-color signal → zero ANSI in stdout/stderr.

- Covers `--no-color` flag and `NO_COLOR=1` env var.
- Commands tested: `sdlc init`, `sdlc status`.

### `tests/integration/test_scan_journal_seq_continuity.py`

Journal seq chain invariants: each `sdlc scan` appends one entry with `monotonic_seq` incrementing
from 0 (POSIX only). Verifies schema fields, RFC3339 UTC timestamp, and `state.json` seq increment.

## Related ADRs

[ADR-017](../decisions/ADR-017-abstraction-adequacy-ci-contract.md) — abstraction-adequacy CI contract.

[ADR-020](../decisions/ADR-020-cli-scan-status-accessibility-flags.md) — `sdlc scan`, `sdlc status`, and accessibility flags design.
