# ADR-017: Abstraction-Adequacy CI Contract

**Status:** Accepted (2026-05-09, Story 1.14)

## Context

Decision C2 (Architecture §316, §356) requires a CI gate that exercises the AIRuntime abstraction against MockAIRuntime so the abstraction's behavioral surface is auditable BEFORE ClaudeAIRuntime lands (Architecture §191 paradigm: "Agent suggestion text is non-deterministic and quarantined behind the AIRuntime interface"). Without this gate the abstraction is aspirational — Claude-specific assumptions can leak into the engine without anyone noticing until production.

NFR-COMPAT-3 (PRD §855) makes this a hard CI requirement: "Mock AIRuntime adequacy test as CI gate." Architecture §1185 names the specific boundary: "AIRuntime abstraction → runtime/abc.py (boundary) + CI test in tests/integration/." Architecture §1424 names the forward extension point: "Behavioral conformance contract (Story 1.14) extended to cover full orchestration pipeline against MockAIRuntime" when Story 2B.3 ships ClaudeAIRuntime.

## Decision

1. The abstraction-adequacy contract is enforced as a single integration test at `tests/integration/test_abstraction_adequacy.py`, marked `@pytest.mark.integration` and skipped on Windows (POSIX-only substrate per Architecture §573).
2. The test runs a fixed deterministic pipeline (init → scan-stub → mock dispatch ×2 → hook-synth → journal append → state projection → atomic state write) against `MockAIRuntime` and asserts byte-equality of the synthesized HookPayload sequence + final state.json against checked-in golden files at `tests/fixtures/abstraction_adequacy/`.
3. The test is parameterized via `_RUNTIME_FACTORIES = [_mock_factory]`. Adding `ClaudeAIRuntime` (Story 2B.3) is a one-line change — extending the list to `[_mock_factory, _claude_factory]`. Both factories MUST produce IDENTICAL golden bytes — divergence fails CI.
4. Determinism is achieved via frozen timestamps (`_FROZEN_TS = "2026-05-08T00:00:00Z"`), frozen monotonic_seq seeds, frozen actor/target_id, and the canonical hash protocol (Architecture §513): `json.dumps(state.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")` without trailing `\n`.
5. Substrate that does not exist in Epic 1 (`engine.scanner.scan` → Story 1.15; `hooks.runner.run_hook_chain` → Story 2A.4) is replaced by inline stubs documented as "deferred to Story 1.15 / 2A.4." When those stories land, the stubs are deleted and goldens are regenerated.
6. Goldens live at `tests/fixtures/abstraction_adequacy/` and are regenerated via the `_REGENERATE_GOLDENS = True` toggle in the test file. Regeneration MUST be a deliberate, justified change committed with a message naming the trigger. The toggle MUST be `False` in all committed code.

## Alternatives Considered

- **Parametrize via `pytest.mark.parametrize` instead of a fixture-with-params**: rejected — a fixture cleanly returns the constructed runtime instance, hiding factory plumbing from the test body. Story 2B.3's one-line extension targets the factory list, not the test body.
- **Use snapshot-testing libraries (`syrupy`, `pytest-snapshot`)**: rejected — adds a dev dependency for a pattern expressible in 5 lines (`Path.read_bytes` + `assert ==`). YAGNI.
- **Compute goldens at test time from the input fixture (round-trip determinism check)**: rejected — that is a tautology test; goldens MUST be checked-in artifacts so a refactor that breaks the abstraction surface fails CI rather than silently auto-correcting.
- **Skip the test entirely until Story 1.15 + 2A.4 land**: rejected — the abstraction-adequacy gap is Winston's named concern (Architecture §1185, §1424). Closing it at the substrate layer, even with stubs, is the discipline. Story 2B.3 extends; it does not replace.
- **Run on Windows via `tempfile`-based pure-Python writes**: rejected — would fork the implementation into a Windows path that does not match the production POSIX protocol. POSIX-only substrate is a deliberate v1 boundary (Architecture §573); the integration test honors it.

## Consequences

- Goldens are coupled to: the seed prompt, the seed fixture, the synthesizer's HookPayload field choices, the JournalEntry payload shape, the State model's field order, and pydantic v2's `model_dump(mode="json")` semantics. Any of these changing is a deliberate goldens regeneration; a subtle drift (e.g., pydantic minor version field re-ordering) trips the CI gate first.
- When Story 1.15 ships `engine.scanner.scan`, the scan-stub is replaced and goldens regen. When Story 2A.4 ships `hooks.runner.run_hook_chain`, the synthesizer stub is replaced and goldens regen. When Story 2B.3 ships `ClaudeAIRuntime`, `_RUNTIME_FACTORIES` extends and the goldens MUST hold for both factories — this is the moment the abstraction-adequacy contract is fully realized.
- The test runs on every PR. Total runtime budget: ≤ 5s (`asyncio.run` × 2 dispatches + a handful of file writes — well under the existing test suite's expectations).
- The `_REGENERATE_GOLDENS` toggle is a documented escape hatch. Code review for any commit changing the goldens MUST include a short "why these bytes drifted" justification — drift without justification is a likely abstraction-adequacy violation.
- **Goldens MUST be regenerated by the integration test itself, not by a sibling script.** Story 1.14 was implemented on a Windows dev host; the integration test is POSIX-only (skipif-win32). The initial goldens were authored manually because `_REGENERATE_GOLDENS=True` cannot run on Windows. This is a one-time exception; any future regeneration MUST go through the canonical path: flip the flag, run `uv run pytest tests/integration/test_abstraction_adequacy.py -m integration` on Linux/macOS (WSL, devbox, or a CI ad-hoc run is acceptable), commit the new bytes, flip the flag back. A Story 1.14 follow-up regenerates the initial goldens via this path to prove the round-trip.

## Code Review Action Items (2026-05-09)

Review of the Story 1.14 commit `c8c6b77` surfaced 22 unified findings; 14 patches + 2 decision-needed items have been applied in a follow-up commit. Notable contract clarifications recorded here:

- **`_TARGET_ID` is now `"epic-1"`** (was `"epic-abstraction-adequacy"`). The previous value did NOT match `state.projection._EPIC_ID_PATTERN = r"\Aepic-[0-9]+\Z"`, so `project_from_journal` silently dropped the epic-mutation branch and the goldens validated only `next_monotonic_seq` advancement. The integration test now exercises the full epic-projection branch. A unit-level pin (`test_target_id_matches_projection_epic_pattern`) catches future drift.
- **`_canonicalize_state_for_hash` now NFC-normalizes** (mirror of `state/atomic._normalize_strings`). Without this, the hash variant and the disk variant of the canonicalizer diverged the moment any non-ASCII state field landed.
- **Per-test fixture isolation**: the `runtime` fixture now copies `abstraction-adequacy.yaml` into `tmp_path/fixtures/`. `MockAIRuntime` eager-loads every `*.yaml` in the canonical `tests/fixtures/mock_responses/` directory, so a malformed sibling fixture added by a future story would have broken Story 1.14's CI gate via cross-test coupling.
- **Hash-chain coupling assert** (`je_1.before_hash == hp_2.content_hash_before`): pins the v1 invariant that the seed fixture's `content_hash` and the placeholder `after_hash` of the previous journal entry are the same value. A future regen that decouples them now fails fast.
- **`_REGENERATE_GOLDENS` regen guard**: a unit test (`test_regenerate_goldens_flag_is_false`) asserts the flag is `False`. Runs on Windows AND POSIX; the integration test is skipif-Windows so a leaked `True` flag is undetectable on the dev host without this guard.
- **Subprocess determinism test → in-process**: the original `subprocess.run(["uv", "run", ...])` test had no timeout, used a relative `sys.path`, and was marked `unit` despite shelling out. Replaced with an in-process check that compares two `_state_hash` computations on equivalent `State` objects.
- **`.gitattributes`** added with `tests/fixtures/abstraction_adequacy/*.json text eol=lf` so a future Windows CI cell does not break golden byte-equality on CRLF checkout.

## Revisit-by

2027-05-09 — or when Story 2B.3 ships `ClaudeAIRuntime` and the test is upgraded to run two runtime variants, at which point the deferred-substrate stubs are evaluated for deletion and the goldens are validated against both factories.

## References

Architecture §191 (paradigm), §220 (sentinel), §316 (Decision C2), §327 (no streaming), §348 (event-sourced read-side), §355–§356 (AIRuntime + Mock), §513 (canonical hash protocol), §1185 (abstraction-adequacy gate), §1424 (Story 2B.3 extension contract). PRD §FR29, §NFR-COMPAT-3, §855. ADR-013 (atomic state write), ADR-014 (journal append-only), ADR-015 (state projection — Story 1.12), ADR-016 (AIRuntime ABC + Mock — Story 1.13).
