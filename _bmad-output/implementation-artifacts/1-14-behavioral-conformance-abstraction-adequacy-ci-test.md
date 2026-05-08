# Story 1.14: Behavioral Conformance / Abstraction-Adequacy CI Test

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Winston (architect) closing the mock-vs-claude drift gap,
I want a CI integration test running a fixed deterministic pipeline against `MockAIRuntime` and asserting both an exact sequence of `HookPayload` events AND an exact final `state.json` (golden-file comparison),
so that when `ClaudeAIRuntime` arrives in Epic 2B (Story 2B.3) the abstraction-adequacy contract is already wired in CI to detect mock-vs-claude drift before it reaches production (FR29, NFR-COMPAT-3, Decision C2, Architecture §191, §220, §316, §356, §1185, §1424).

## Acceptance Criteria

**AC1 — A single integration test file at the canonical location runs the abstraction-adequacy pipeline end-to-end (epic AC block 1)**

**Given** Stories 1.10–1.13 complete on disk:

- `src/sdlc/state/atomic.py` exports `write_state_atomic_sync` (Story 1.10)
- `src/sdlc/journal/writer.py` exports `append_sync` (Story 1.11)
- `src/sdlc/journal/reader.py` exports `iter_entries` (Story 1.11)
- `src/sdlc/state/projection.py` exports `project_from_journal` (Story 1.12)
- `src/sdlc/runtime/__init__.py` exports `AIRuntime, AgentResult, MockAIRuntime, MockMissError` (Story 1.13)
- `src/sdlc/contracts/hook_payload.py` exports `HookPayload` (Story 1.7)
- `src/sdlc/contracts/journal_entry.py` exports `JournalEntry` (Story 1.7)

**When** the file `tests/integration/test_abstraction_adequacy.py` runs under `uv run pytest -m integration`,

**Then** a single test function `test_abstraction_adequacy_against_mock_runtime` executes the canonical fixed pipeline against `MockAIRuntime` once and exits 0 with all assertions green. The pipeline is exactly these ordered steps (mirrors Architecture §1185 + Story 1.14 Acceptance Criteria block 1):

1. **init** — create a temporary project root via `tmp_path` fixture; create the `.claude/state/` directory; do NOT pre-write `state.json` or `journal.log` (the pipeline creates them on first append). The init step is purely directory scaffolding; mirrors Story 1.16's future `sdlc init` shape but stays inside the test (cli/init is Story 1.16).
2. **scan (deferred-substrate stub)** — Story 1.15's `engine.scanner.scan(project_root)` does NOT exist yet. The test substitutes a deterministic stub that returns the canonical empty initial `State(schema_version=1, next_monotonic_seq=0, epics={})` (Story 1.12's `state.model.State`). Document inline: "scan step is a no-op stub for Epic 1; Story 1.15 will replace this with `engine.scanner.scan` when the scanner ships. Story 2B.3 will run the FULL pipeline (with real scan) — at that point this stub disappears and the test is upgraded in lockstep."
3. **mock dispatch** — instantiate `MockAIRuntime(fixtures_dir=tests/fixtures/mock_responses/)`. Call `await mock.dispatch(prompt=_SEED_PROMPT, context={"workflow_step": "abstraction-adequacy"})` exactly twice in sequence (two dispatches give us a non-trivial 2-event sequence to assert; one dispatch is too small to detect ordering bugs). Both dispatches use IDENTICAL `(prompt, context)` so the same fixture record is returned both times — this is intentional: AC3 (Story 1.13) asserts byte-identical AgentResult under repeated dispatch; this story asserts the dispatcher-level pipeline preserves that determinism end-to-end.
4. **HookPayload synthesis (deferred-substrate stub)** — Story 2A.4's full `hooks/runner.py` chain does NOT exist yet. The test synthesizes one `HookPayload` per dispatch from each `AgentResult.tool_calls[0]` (the seed fixture has exactly one tool_call: a `write_artifact` call producing `01-Requirement/04-Epics/EPIC-abstraction-adequacy.json`). The synthesizer is a small inline helper (≤ 20 LOC) that takes `(AgentResult, monotonic_seq) -> HookPayload`. Document inline: "Hook synthesis is a Story-1.14-test-only stub; the real chain lands in Story 2A.4. Story 2B.3 will switch this to the real `hooks/runner.py` invocation — at that point the synthesizer code is deleted and the test asserts the chain's actual emission order."
5. **journal append** — for each `(AgentResult, HookPayload)` pair, build a `JournalEntry(schema_version=1, monotonic_seq=N, ts=<frozen>, actor="agent:abstraction-adequacy", kind="state_mutation", target_id="epic-abstraction-adequacy", before_hash=<prev>, after_hash=<curr>, payload=<dispatch-result>)` and call `journal.append_sync(entry, journal_path=<tmp>/.claude/state/journal.log)`. Use the `monotonic_seq` returned by the previous append to chain `before_hash`/`after_hash` correctly.
6. **state projection** — call `state = state.projection.project_from_journal(<tmp>/.claude/state/journal.log)`. The projection MUST be deterministic (Story 1.12's pure-function contract).
7. **state.json atomic write** — `state.write_state_atomic_sync(state, target=<tmp>/.claude/state/state.json)`.
8. **golden assertions (the CI gate)** —
   - **HookPayload sequence**: collect the synthesized `HookPayload` list as a JSON array (`[hp.model_dump(mode="json") for hp in synthesized_payloads]`); canonicalize via `json.dumps(payloads, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"`; assert byte-equality to `tests/fixtures/abstraction_adequacy/expected_hook_payloads.json` (read as bytes).
   - **Final state.json**: read `<tmp>/.claude/state/state.json` as raw bytes; assert byte-equality to `tests/fixtures/abstraction_adequacy/expected_state.json` (read as bytes).
   - **AgentResult determinism**: the two dispatches' `AgentResult` objects MUST be `model_dump(mode="json")`-equal (sanity check that 1.13's determinism holds when called from this pipeline harness).

**And** the test MUST pass on `ubuntu-latest` AND `macos-latest` python 3.10 / 3.11 / 3.12 / 3.13 (the existing `quality-gates` matrix in `.github/workflows/ci.yml:25-28`). It MUST be skipped on Windows because `journal.writer.append_sync` and `state.atomic.write_state_atomic_sync` are POSIX-only (Architecture §573, §493). Skip pattern is the canonical project pattern: top-of-file `pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only: journal append + atomic state write require fcntl + O_APPEND")`. Mirrors `tests/chaos/test_atomic_write_kill_points.py` and `tests/property/test_journal_append_only.py` skip patterns from Stories 1.10/1.11.

**And** the test is marked `@pytest.mark.integration` (NOT `unit`, NOT `chaos`). Existing markers cover this; no new pytest marker is added.

**AC2 — The test is parameterized for runtime, so adding ClaudeAIRuntime in Epic 2B (Story 2B.3) is a one-line change (epic AC block 2)**

**Given** the integration test infrastructure of AC1,

**When** Epic 2B's Story 2B.3 ships `ClaudeAIRuntime` and extends this test,

**Then** the only edit required to enable the Claude variant is changing ONE line: extending the `params=` list of the `runtime_factory` pytest fixture from `params=[_mock_factory]` to `params=[_mock_factory, _claude_factory]`. The pipeline body, the assertions, and the golden files MUST remain unchanged — Mock and Claude must produce IDENTICAL `HookPayload` event sequences and IDENTICAL final state.json bytes for the same input (Decision C2 + Architecture §1424 contract).

To deliver this:

1. Define a module-level constant `_RUNTIME_FACTORIES: list[Callable[[Path], AIRuntime]] = [_mock_factory]` at the top of `test_abstraction_adequacy.py`. The factory takes a `fixtures_dir` Path and returns a constructed `AIRuntime` instance.
2. Define `_mock_factory(fixtures_dir: Path) -> AIRuntime` at module level: `return MockAIRuntime(fixtures_dir=fixtures_dir)`. This factory is the EXACT shape Story 2B.3 will mirror for `_claude_factory(fixtures_dir: Path) -> AIRuntime` — the Claude factory will ignore `fixtures_dir` and connect to the real `claude` subprocess (per Story 2B.1's `runtime/claude.py`).
3. Use a parameterized fixture: `@pytest.fixture(params=_RUNTIME_FACTORIES, ids=lambda f: f.__name__.lstrip("_"))`. The fixture yields a constructed `AIRuntime` instance. The `ids=` callable produces stable test-id strings (`mock_factory`, future `claude_factory`) for pytest's `-k` filtering.
4. The test function signature is `def test_abstraction_adequacy_pipeline(tmp_path: Path, runtime: AIRuntime) -> None:` — `runtime` comes from the parameterized fixture. Inside the test the runtime is used directly: `result = asyncio.run(runtime.dispatch(prompt=_SEED_PROMPT, context=_SEED_CONTEXT))`.
5. Document inline at the top of `_RUNTIME_FACTORIES`: "EPIC 2B GATE — Story 2B.3 extends this list to `[_mock_factory, _claude_factory]`. Both factories MUST produce identical HookPayload sequences and identical final state.json bytes (Decision C2, Architecture §1424, FR29). DO NOT add a third factory in v1."

**And** the test name in pytest output reads as `test_abstraction_adequacy_pipeline[mock_factory]` (one variant in v1; two variants when 2B.3 lands).

**AC3 — In Epic 1, only the Mock variant runs; the contract surface for adding ClaudeAIRuntime is documented (epic AC block 3)**

**Given** the parameterized fixture from AC2 with `_RUNTIME_FACTORIES = [_mock_factory]`,

**When** the test runs in CI as part of the existing `quality-gates` job,

**Then**:

1. The test runs ONCE (only the Mock variant) and passes. No `xfail`, no `skip` on the Mock variant.
2. A module-level docstring at the top of `test_abstraction_adequacy.py` documents the contract:
   ```python
   """Abstraction-adequacy CI gate (Story 1.14 / Epic 1).

   Runs the deterministic pipeline (init → scan-stub → mock dispatch ×2 →
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
   ```
3. ADR-017 (Task 5) records the contract: "Abstraction-adequacy is enforced as a CI gate via golden-file comparison of HookPayload sequence + final state.json. Adding a runtime variant (Claude in 2B.3, hypothetical Cursor/Copilot in v2) MUST produce identical golden bytes for the same seed input — divergence fails CI."
4. Architecture §1424 ("Behavioral conformance contract (Story 1.14) extended to cover full orchestration pipeline against MockAIRuntime") is satisfied for v1 minimal substrate. Story 2B.3 will extend the test in lockstep with the dispatcher landing in Epic 2A.

**AC4 — Golden files are byte-stable across machines, OS targets, and python minor versions (epic AC block 4)**

**Given** the goldens at `tests/fixtures/abstraction_adequacy/expected_hook_payloads.json` and `tests/fixtures/abstraction_adequacy/expected_state.json`,

**When** the test runs on `ubuntu-latest` python 3.10, `ubuntu-latest` python 3.13, `macos-latest` python 3.10, AND `macos-latest` python 3.13,

**Then** the same goldens pass on every matrix cell. Determinism is achieved by:

1. **Fixed timestamps**: every `JournalEntry.ts` in the pipeline uses the constant `_FROZEN_TS: Final[str] = "2026-05-08T00:00:00Z"` (RFC 3339 UTC, matches `_RFC3339_UTC` regex in `journal_entry.py:16`). Do NOT call `datetime.now()` — non-determinism would break goldens. Document inline: "Frozen timestamp; the pipeline is a determinism contract, not a wall-clock test."
2. **Fixed monotonic_seq seeds**: `monotonic_seq=0` for the first append, `monotonic_seq=1` for the second. Computed from a counter local to the test, not from `time.time_ns()`.
3. **Fixed before_hash/after_hash chain**: the `before_hash` of entry 0 is `None` (initial state, no predecessor). The `after_hash` of entry N is computed via the canonical hash protocol (Architecture §513): `"sha256:" + hashlib.sha256(canonical_json_bytes_of_state).hexdigest()` where `canonical_json_bytes_of_state` is `json.dumps(state.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")` (NOT terminated with `\n` — Architecture §513 distinguishes hash-canonicalization from disk-canonicalization). The `before_hash` of entry 1 is the `after_hash` of entry 0.
4. **Fixed actor**: `"agent:abstraction-adequacy"` (constant string).
5. **Fixed seed prompt + workflow_step**: `_SEED_PROMPT: Final[str] = "abstraction-adequacy seed prompt"` and `_SEED_CONTEXT: Final[Mapping[str, object]] = MappingProxyType({"workflow_step": "abstraction-adequacy"})`. Both are constants at module scope.
6. **Canonical JSON for goldens**: BOTH golden files are written using the SAME canonicalization rules as the pipeline (`json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"` for state.json — matches `state/atomic.py:_canonicalize_state` exactly). For `expected_hook_payloads.json`, write the canonicalized JSON array. The trailing `\n` on `expected_state.json` is mandatory (matches `_canonicalize_state`'s `+ b"\n"` line at `state/atomic.py:65`); the trailing `\n` on `expected_hook_payloads.json` is also mandatory (consistency).

**And** unit tests in `tests/unit/integration/test_abstraction_adequacy_helpers.py` (a unit-level companion file — different directory than the integration test, mirrors how `tests/unit/scripts/` mirrors `scripts/`) verify the determinism primitives in isolation:

1. `test_seed_prompt_hash_is_byte_stable`: hash `_SEED_PROMPT` via `hashlib.sha256` directly; assert the hex matches a hard-coded expected (catches accidental edit to `_SEED_PROMPT`).
2. `test_synthesize_hook_payload_is_pure`: call the synthesizer twice with the same `AgentResult` and same `monotonic_seq`; assert the two results are `model_dump(mode="json")`-equal (catches non-determinism in synthesis).
3. `test_canonical_state_hash_is_stable`: build `State(schema_version=1, next_monotonic_seq=0, epics={"epic-1": {"k": "v"}})`; canonicalize via the helper; assert the sha256 hex matches a hard-coded expected (catches `_canonicalize_state_for_hash` drift).

**And** golden-file regeneration is documented at the bottom of `test_abstraction_adequacy.py` as a comment block:
```python
# To regenerate goldens (e.g., after a deliberate fixture change):
#   1. Set _REGENERATE_GOLDENS = True at the top of this file.
#   2. uv run pytest tests/integration/test_abstraction_adequacy.py -m integration
#   3. The test will WRITE the goldens instead of asserting; visually diff the result.
#   4. Set _REGENERATE_GOLDENS = False; commit the new goldens with a justifying message.
# DO NOT regenerate goldens to make a failing test pass without first auditing
# WHY the bytes drifted — drift is the symptom this test exists to catch.
```
The `_REGENERATE_GOLDENS: Final[bool] = False` constant is at module scope. When `True`, the assertions are replaced with `Path.write_bytes(...)` calls. This pattern mirrors hash-corpus regeneration scripts in similar codebases; document the discipline in ADR-017.

**AC5 — The seed YAML fixture lives under the canonical mock_responses directory (epic AC block 5)**

**Given** the canonical mock fixtures directory at `tests/fixtures/mock_responses/` (Story 1.13 Task 5),

**When** the test runs,

**Then** the seed fixture file is at `tests/fixtures/mock_responses/abstraction-adequacy.yaml`. The filename `abstraction-adequacy.yaml` derives from `workflow_step="abstraction-adequacy"` per Story 1.13's loader convention (`workflow_step = path.stem`).

The fixture content is exactly:

```yaml
# tests/fixtures/mock_responses/abstraction-adequacy.yaml
# Seed fixture for Story 1.14 abstraction-adequacy CI test.
# workflow_step="abstraction-adequacy"; prompt="abstraction-adequacy seed prompt".
# prompt_hash for that prompt = sha256("abstraction-adequacy seed prompt".encode("utf-8")).hexdigest()
# Generate via:
#   python -c 'import hashlib; print("sha256:" + hashlib.sha256(b"abstraction-adequacy seed prompt").hexdigest())'
"sha256:<COMPUTED-HEX>":
  output_text: "Generated abstraction-adequacy seed artifact for Story 1.14 / 2B.3 conformance contract."
  tool_calls:
    - name: "write_artifact"
      args:
        target: "01-Requirement/04-Epics/EPIC-abstraction-adequacy.json"
        content_hash: "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  tokens_in: 42
  tokens_out: 84
```

Compute `<COMPUTED-HEX>` at story-author / story-implement time:

```bash
uv run python -c 'import hashlib; print("sha256:" + hashlib.sha256(b"abstraction-adequacy seed prompt").hexdigest())'
```

This hex MUST match what `MockAIRuntime._hash_prompt(_SEED_PROMPT)` produces — Task 1 includes a pre-flight verification of this match (a mismatch is a Story-1.13 / Story-1.14 sync bug).

**And** `tests/fixtures/mock_responses/_smoke.yaml` (Story 1.13's smoke fixture) is left untouched — Story 1.14 is additive, not replacing.

**And** `tests/fixtures/mock_responses/README.md` is updated to mention `abstraction-adequacy.yaml` as the canonical "live" fixture used by the abstraction-adequacy CI gate (Story 1.14): one short paragraph after the existing format docs.

## Tasks / Subtasks

- [ ] **Task 1: Pre-flight verification of dependencies and existing state (AC: all)**
  - [ ] Verify Story 1.10 deliverables on disk: `src/sdlc/state/atomic.py` exports `write_state_atomic_sync`; smoke `uv run python -c "from sdlc.state import write_state_atomic_sync; print('ok')"`.
  - [ ] Verify Story 1.11 deliverables on disk: `src/sdlc/journal/writer.py` exports `append_sync`; `src/sdlc/journal/reader.py` exports `iter_entries`; smoke `uv run python -c "from sdlc.journal import append_sync, iter_entries; print('ok')"`.
  - [ ] Verify Story 1.12 deliverables on disk: `src/sdlc/state/projection.py` exports `project_from_journal`; smoke `uv run python -c "from sdlc.state.projection import project_from_journal; print('ok')"`. **If 1.12 has not landed yet, this story is BLOCKED — stop and escalate.** This story has a hard dependency on `project_from_journal`.
  - [ ] Verify Story 1.13 deliverables on disk: `src/sdlc/runtime/__init__.py` exports `AIRuntime, AgentResult, MockAIRuntime, MockMissError`; smoke `uv run python -c "from sdlc.runtime import AIRuntime, AgentResult, MockAIRuntime, MockMissError; print('ok')"`. **If 1.13 has not landed yet, this story is BLOCKED — stop and escalate.**
  - [ ] Verify Story 1.13's `tests/fixtures/mock_responses/` directory exists with `_smoke.yaml`; if missing, escalate (Story 1.13 owns directory creation).
  - [ ] Verify `MockAIRuntime._hash_prompt(_SEED_PROMPT)` and stand-alone `hashlib.sha256(_SEED_PROMPT.encode()).hexdigest()` agree. Run:
    ```bash
    uv run python -c 'from sdlc.runtime.mock import _hash_prompt; print(_hash_prompt("abstraction-adequacy seed prompt"))'
    uv run python -c 'import hashlib; print("sha256:" + hashlib.sha256(b"abstraction-adequacy seed prompt").hexdigest())'
    ```
    Both MUST print the same `sha256:...` hex. The fixture file's top-level key MUST exactly match this hex.
  - [ ] Verify ADR numbering: existing ADRs are 001-014 per `docs/decisions/index.md`. Stories 1.12 and 1.13 add ADR-015 and ADR-016 respectively (in flight). Story 1.14 (this story) authors **ADR-017**. If 1.12/1.13 ADRs are not yet on disk at story-implement time, this story's ADR-017 is still the next available number — proceed.
  - [ ] Verify `pyproject.toml [tool.pytest.ini_options].markers` includes `integration` (line ~178). Confirmed already from Story 1.4. No new marker.
  - [ ] Verify CI matrix in `.github/workflows/ci.yml:25-28`: `os: [ubuntu-latest, macos-latest]` × `python-version: ["3.10", "3.11", "3.12", "3.13"]`. The integration test will run on all 8 cells (POSIX skip applies to Windows only — Windows is NOT in the matrix anyway). No CI workflow edit required by this story.
  - [ ] Verify the existing chaos-tests job in `.github/workflows/ci.yml:67-89` uses `-m chaos --no-cov`; the abstraction-adequacy test does NOT run there (different marker, runs in the main `quality-gates` job which already uses `uv run pytest` without marker filtering, picking up `integration`-marked tests).

- [ ] **Task 2: Create the integration test directory + helpers, including determinism constants (AC: #1, #4)**
  - [ ] Verify `tests/integration/__init__.py` already exists (Story 1.10 created it). If missing, create it as an empty file (pytest collection sentinel).
  - [ ] Create `tests/integration/test_abstraction_adequacy.py` with:
    - Module docstring per AC3.2.
    - `from __future__ import annotations`.
    - Imports (in canonical order: stdlib, third-party, sdlc): `asyncio, hashlib, json, sys`; `from collections.abc import Callable, Mapping`; `from pathlib import Path`; `from types import MappingProxyType`; `from typing import Final`; `import pytest`; `from sdlc.contracts.hook_payload import HookPayload`; `from sdlc.contracts.journal_entry import JournalEntry`; `from sdlc.journal import append_sync, iter_entries`; `from sdlc.runtime import AIRuntime, AgentResult, MockAIRuntime`; `from sdlc.state import State, write_state_atomic_sync`; `from sdlc.state.projection import project_from_journal`.
    - POSIX skip pattern at module level: `pytestmark = [pytest.mark.integration, pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only: journal.append_sync + state.write_state_atomic_sync require fcntl + O_APPEND")]`.
    - Module-level constants:
      ```python
      _REGENERATE_GOLDENS: Final[bool] = False
      _SEED_PROMPT: Final[str] = "abstraction-adequacy seed prompt"
      _SEED_CONTEXT: Final[Mapping[str, object]] = MappingProxyType(
          {"workflow_step": "abstraction-adequacy"}
      )
      _FROZEN_TS: Final[str] = "2026-05-08T00:00:00Z"
      _ACTOR: Final[str] = "agent:abstraction-adequacy"
      _TARGET_ID: Final[str] = "epic-abstraction-adequacy"
      _GOLDEN_DIR: Final[Path] = (
          Path(__file__).resolve().parents[1]
          / "fixtures"
          / "abstraction_adequacy"
      )
      _MOCK_FIXTURES_DIR: Final[Path] = (
          Path(__file__).resolve().parents[1] / "fixtures" / "mock_responses"
      )
      ```
    - Helper `_canonicalize_state_for_hash(state: State) -> bytes`: returns `json.dumps(state.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")` (no trailing `\n` — hash variant per Architecture §513).
    - Helper `_state_hash(state: State) -> str`: returns `"sha256:" + hashlib.sha256(_canonicalize_state_for_hash(state)).hexdigest()`.
    - Helper `_synthesize_hook_payload(result: AgentResult, seq: int) -> HookPayload`: extracts the first tool_call from `result.tool_calls`; reads `target` and `content_hash` keys; builds `HookPayload(schema_version=1, hook_name="abstraction-adequacy-synth", target_path=str(target), target_kind="epic", content_hash_before=None if seq == 0 else <prev>, write_intent="create")`. Document inline that `content_hash_before` chain is intentionally simplified for the substrate test; Story 2A.4 owns the real chain.
    - Helper `_build_journal_entry(seq: int, before_hash: str | None, after_hash: str, agent_result: AgentResult) -> JournalEntry`: returns `JournalEntry(schema_version=1, monotonic_seq=seq, ts=_FROZEN_TS, actor=_ACTOR, kind="state_mutation", target_id=_TARGET_ID, before_hash=before_hash, after_hash=after_hash, payload={"output_text": agent_result.output_text, "tokens_in": agent_result.tokens_in, "tokens_out": agent_result.tokens_out})`. Note: `tool_calls` are intentionally NOT in the payload — they'd duplicate the HookPayload synthesis. Document inline.
    - `_RUNTIME_FACTORIES: list[Callable[[Path], AIRuntime]] = [_mock_factory]` and `def _mock_factory(fixtures_dir: Path) -> AIRuntime: return MockAIRuntime(fixtures_dir=fixtures_dir)`. Add the EPIC-2B-GATE comment per AC2.5.
  - [ ] LOC budget for `test_abstraction_adequacy.py`: ≤ 350 LOC (test file; not subject to the 400-LOC src cap, but stay disciplined). The file is the contract; verbosity is OK if it serves clarity, but trim ceremony.

- [ ] **Task 3: Implement the parameterized test function (AC: #1, #2, #3, #4)**
  - [ ] Define the parameterized fixture:
    ```python
    @pytest.fixture(
        params=_RUNTIME_FACTORIES,
        ids=lambda factory: factory.__name__.lstrip("_"),
    )
    def runtime(request: pytest.FixtureRequest) -> AIRuntime:
        factory: Callable[[Path], AIRuntime] = request.param
        return factory(_MOCK_FIXTURES_DIR)
    ```
    Note: even when `_claude_factory` lands in 2B.3, the `fixtures_dir` argument is harmless (the Claude factory ignores it). Keeping the same factory signature is the simplest forward-compat shape.
  - [ ] Define the test function:
    ```python
    def test_abstraction_adequacy_pipeline(
        tmp_path: Path, runtime: AIRuntime
    ) -> None:
        # Step 1: init — create .claude/state/ directory under tmp_path
        state_dir = tmp_path / ".claude" / "state"
        state_dir.mkdir(parents=True, exist_ok=False)
        journal_path = state_dir / "journal.log"
        state_path = state_dir / "state.json"

        # Step 2: scan stub — Story 1.15 will replace with engine.scanner.scan
        initial_state = State(schema_version=1, next_monotonic_seq=0, epics={})

        # Step 3: dispatch ×2 (same prompt+context — exercise determinism)
        result_1 = asyncio.run(runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT))
        result_2 = asyncio.run(runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT))
        # AC1.8 sanity: dispatches are deterministic
        assert result_1.model_dump(mode="json") == result_2.model_dump(mode="json"), (
            "non-deterministic dispatch — Story 1.13 AC3 violated"
        )

        # Step 4: hook synthesis (deferred-substrate stub)
        hp_1 = _synthesize_hook_payload(result_1, seq=0)
        hp_2 = _synthesize_hook_payload(result_2, seq=1)
        synthesized_hook_payloads = [hp_1, hp_2]

        # Step 5: journal append ×2 with chained before/after hashes
        # Build the projected states first to compute hashes deterministically.
        je_0 = _build_journal_entry(
            seq=0,
            before_hash=None,
            after_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
            agent_result=result_1,
        )
        # Note: after_hash is a placeholder; the real hash chain is enforced by
        # journal/state coupling in Story 2A.4. The test asserts the JOURNAL
        # contents are byte-stable (golden), not the hash semantics.
        append_sync(je_0, journal_path=journal_path)
        je_1 = _build_journal_entry(
            seq=1,
            before_hash=je_0.after_hash,
            after_hash="sha256:1111111111111111111111111111111111111111111111111111111111111111",
            agent_result=result_2,
        )
        append_sync(je_1, journal_path=journal_path)

        # Step 6: project final state from the journal
        final_state = project_from_journal(journal_path)

        # Step 7: atomic state.json write
        write_state_atomic_sync(final_state, target=state_path)

        # Step 8: golden assertions
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

        if _REGENERATE_GOLDENS:  # noqa: SIM108
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
    ```
  - [ ] **Forbidden patterns at code-review time** (mirror Stories 1.10–1.13):
    - `datetime.now()` / `time.time()` / `time.time_ns()` — non-determinism. Use `_FROZEN_TS`.
    - `asyncio.get_event_loop()` — deprecated in 3.10+. Use `asyncio.run(coro)` per Story 1.13's pattern.
    - Hard-coded absolute paths — use `tmp_path` and `_GOLDEN_DIR` (computed from `__file__`).
    - `print()` in test code — Architecture §489 forbids `print` in src/; pytest captures stdout, but the project convention extends to tests. Use `pytest.fail(...)` for diagnostic exits.
    - Bare `except:` / `except Exception:` — narrow catches. The pipeline propagates errors; the test does not catch them.
    - `pytest-asyncio` — NOT in dev deps; do NOT add. Use `asyncio.run(coro)` directly (Story 1.13 precedent).
    - Re-creating the `MockAIRuntime` inside the test body — the fixture constructs it once. The fixture is per-test (not session-scoped) so each test run gets a fresh instance, BUT the construction happens in the fixture, not in the test body.

- [ ] **Task 4: Create the seed YAML fixture + golden files (AC: #4, #5)**
  - [ ] Compute `_SEED_PROMPT_HASH = sha256("abstraction-adequacy seed prompt".encode("utf-8")).hexdigest()` once via `uv run python -c 'import hashlib; print("sha256:" + hashlib.sha256(b"abstraction-adequacy seed prompt").hexdigest())'`. Capture the output as a 64-char hex string. (Story-author note: the canonical hex for `b"abstraction-adequacy seed prompt"` is reproducible; Task 1 verifies the runtime path agrees.)
  - [ ] Create `tests/fixtures/mock_responses/abstraction-adequacy.yaml` per AC5 with the computed hex as the top-level key.
  - [ ] Update `tests/fixtures/mock_responses/README.md` (created by Story 1.13) — append a paragraph: "`abstraction-adequacy.yaml` is the live fixture used by `tests/integration/test_abstraction_adequacy.py` (Story 1.14). Do NOT edit without re-generating goldens at `tests/fixtures/abstraction_adequacy/`."
  - [ ] Create `tests/fixtures/abstraction_adequacy/` directory.
  - [ ] Generate the goldens by running the test once with `_REGENERATE_GOLDENS = True`:
    ```bash
    # 1. Edit test_abstraction_adequacy.py: _REGENERATE_GOLDENS = True
    uv run pytest tests/integration/test_abstraction_adequacy.py -m integration -v
    # The test will WRITE the goldens and pytest.fail(...). The golden files
    # are now on disk under tests/fixtures/abstraction_adequacy/.
    # 2. Edit test_abstraction_adequacy.py: _REGENERATE_GOLDENS = False
    uv run pytest tests/integration/test_abstraction_adequacy.py -m integration -v
    # The test now passes against the freshly-written goldens.
    ```
  - [ ] Inspect the generated goldens visually:
    - `expected_hook_payloads.json` should be a JSON array of two HookPayload objects, both with `target_path="01-Requirement/04-Epics/EPIC-abstraction-adequacy.json"`, `target_kind="epic"`, `write_intent="create"`, and DIFFERENT `content_hash_before` values (None for seq 0, a sha256:... value for seq 1).
    - `expected_state.json` should reflect a State with `next_monotonic_seq=2` and `epics["epic-abstraction-adequacy"]` populated by the projection. Confirm canonical JSON layout: keys sorted, no whitespace except inside strings, terminating `\n`.
  - [ ] Add a brief regen-history line to `tests/fixtures/abstraction_adequacy/README.md`:
    ```markdown
    # Abstraction-Adequacy Goldens (Story 1.14)

    Generated by `tests/integration/test_abstraction_adequacy.py` with
    `_REGENERATE_GOLDENS = True`. DO NOT hand-edit. Drift is a CI gate
    failure (Decision C2, Architecture §1424).

    Regen history:
      - 2026-05-09: initial generation (Story 1.14, ADR-017).
    ```
  - [ ] Confirm the goldens are NOT excluded from coverage / CI artifacts (`pyproject.toml [tool.coverage.run].omit` does NOT list `tests/fixtures/...` — fixtures are data, not code).

- [ ] **Task 5: Author ADR-017 + update documentation (AC: all)**
  - [ ] Create `docs/decisions/ADR-017-abstraction-adequacy-ci-contract.md` using the structure of `docs/decisions/adr-template.md`. Sections:
    - **Status:** Accepted
    - **Date:** 2026-05-09 (or system date when story is dev'd)
    - **Story:** 1.14
    - **Context:** Decision C2 (Architecture §316, §356) requires a CI gate that exercises the AIRuntime abstraction against the Mock so the abstraction's behavioral surface is auditable BEFORE Claude lands (Architecture §191 paradigm: "Agent suggestion text is non-deterministic and quarantined behind the AIRuntime interface"). Without this gate, the abstraction is aspirational — Claude-specific assumptions can leak into the engine without anyone noticing until production. NFR-COMPAT-3 (PRD §855) makes this a hard CI requirement.
    - **Decision:**
      1. The abstraction-adequacy contract is enforced as a single integration test at `tests/integration/test_abstraction_adequacy.py`, marked `@pytest.mark.integration` and skipped on Windows (POSIX-only substrate).
      2. The test runs a fixed deterministic pipeline (init → scan-stub → mock dispatch ×2 → hook-synth → journal append → state projection → atomic state write) against `MockAIRuntime` and asserts byte-equality of the synthesized HookPayload sequence + final state.json against checked-in golden files.
      3. The test is parameterized via `_RUNTIME_FACTORIES`. Adding `ClaudeAIRuntime` (Story 2B.3) is a one-line change. Both factories MUST produce IDENTICAL goldens — drift fails CI.
      4. Determinism is achieved via frozen timestamps, frozen monotonic_seq seeds, frozen actor/target_id, and the canonical hash protocol (Architecture §513).
      5. Substrate that doesn't exist in Epic 1 (engine.scanner.scan, hooks.runner.run_hook_chain) is replaced by inline stubs documented as "deferred to Story 1.15 / 2A.4". When those stories land, the stubs are deleted and the goldens are regenerated.
      6. Goldens live at `tests/fixtures/abstraction_adequacy/` and are regenerated via the `_REGENERATE_GOLDENS=True` toggle. Regeneration MUST be a deliberate, justified change (committed with a message naming the trigger).
    - **Alternatives considered:**
      - Parametrize via `pytest.mark.parametrize` instead of a fixture-with-params — rejected: a fixture cleanly returns the constructed runtime instance, hiding factory plumbing from the test body. Story 2B.3's one-line extension is to the factory list, not the test body.
      - Use snapshot-testing libraries (`syrupy`, `pytest-snapshot`) — rejected: adds a dev dependency for a pattern we can express in 5 lines (`Path.read_bytes` + `assert ==`). YAGNI.
      - Compute goldens at test time from the input fixture (round-trip determinism check) — rejected: that's a tautology test; goldens MUST be checked-in artifacts so a refactor that breaks the abstraction surface gets caught at CI, not silently auto-corrected.
      - Skip the test entirely until 1.15 + 2A.4 land — rejected: the abstraction-adequacy gap is Winston's NAMED concern (Architecture §1185, §1424). Closing it AT THE SUBSTRATE LAYER, even with stubs, is the discipline. 2B.3 extends; it does not replace.
      - Run on Windows via `tempfile`-based pure-Python writes — rejected: would fork the implementation into a Windows path that doesn't match the production protocol. POSIX-only substrate is a deliberate v1 boundary (Architecture §573); the integration test honors it.
    - **Consequences:**
      - Goldens are coupled to: the seed prompt, the seed fixture, the synthesizer's HookPayload field choices, the JournalEntry payload shape, the State model's field order, and pydantic v2's `model_dump(mode="json")` semantics. Any of these changing is a deliberate goldens regeneration; a subtle drift (e.g., pydantic minor version field re-ordering) trips the CI gate first.
      - When Story 1.15 ships `engine.scanner.scan`, the scan-stub is replaced and goldens regen. When Story 2A.4 ships `hooks.runner.run_hook_chain`, the synthesizer stub is replaced and goldens regen. When Story 2B.3 ships `ClaudeAIRuntime`, `_RUNTIME_FACTORIES` extends and the goldens MUST hold for both factories — this is the moment the abstraction-adequacy contract is fully realized.
      - The test runs on every PR. Total runtime budget: ≤ 5s (asyncio.run × 2 dispatches + a handful of file writes — well under the existing test suite's expectations).
      - The `_REGENERATE_GOLDENS` toggle is a documented escape hatch. Code review for any commit changing the goldens MUST include a short "why these bytes drifted" justification — drift without justification is a likely abstraction-adequacy violation.
    - **Revisit by:** Story 2B.3 (when ClaudeAIRuntime lands and the test is upgraded to run two variants).
    - **References:** Architecture §191 (paradigm), §220 (sentinel), §316 (Decision C2), §327 (no streaming), §348 (event-sourced read-side), §355-§356 (AIRuntime + Mock), §513 (canonical hash protocol), §1185 (abstraction-adequacy gate), §1424 (Story 2B.3 extension contract). PRD §FR29, §NFR-COMPAT-3, §855. ADR-013 (atomic state write), ADR-014 (journal append-only), ADR-015 (state projection — Story 1.12), ADR-016 (AIRuntime ABC + Mock — Story 1.13).
  - [ ] Update `docs/decisions/index.md`: add row `| [017](ADR-017-abstraction-adequacy-ci-contract.md) | Abstraction-adequacy CI contract | 1.14 | Accepted |` after the existing ADR-014 row. If Stories 1.12 / 1.13 have not yet landed their ADR-015 / ADR-016 rows, place this row in numeric position 017 (preserving gaps; the missing rows fill in when those stories commit).
  - [ ] Create `docs/CODEMAPS/integration-tests.md` (or update if exists) listing the abstraction-adequacy test, its fixture, its goldens, and its forward-compat link to Story 2B.3.

- [ ] **Task 6: Unit tests for the determinism helpers (AC: #4)**
  - [ ] Create `tests/unit/integration/__init__.py` (empty file — pytest collection sentinel).
  - [ ] Create `tests/unit/integration/test_abstraction_adequacy_helpers.py` with these tests (mark `@pytest.mark.unit`):
    - `test_seed_prompt_hash_is_byte_stable`:
      ```python
      def test_seed_prompt_hash_is_byte_stable() -> None:
          import hashlib
          actual = "sha256:" + hashlib.sha256(b"abstraction-adequacy seed prompt").hexdigest()
          # If you change _SEED_PROMPT, regenerate goldens — see ADR-017.
          expected = "sha256:<paste-the-actual-hex-here-from-Task-1-pre-flight>"
          assert actual == expected
      ```
      The test imports the constants from the integration module:
      ```python
      from tests.integration.test_abstraction_adequacy import _SEED_PROMPT, _state_hash, _synthesize_hook_payload
      ```
      Note: importing across test directories requires `tests/__init__.py` (already in place per Story 1.10) AND a careful path. If the import path doesn't resolve, fall back to importing via the package's `tests` module (`from tests.integration.test_abstraction_adequacy import ...`) — pytest's rootdir handling per `pyproject.toml [tool.pytest.ini_options].testpaths = ["tests"]` makes this work. If still failing, factor the helpers out into `tests/integration/_abstraction_adequacy_helpers.py` (a non-test helper module) and import from there. **Choose this path proactively if the cross-import looks fragile** — factoring into `_abstraction_adequacy_helpers.py` is the cleaner shape.
    - `test_synthesize_hook_payload_is_pure`: build a known `AgentResult`; call the synthesizer twice with the same seq; assert `model_dump(mode="json")`-equal.
    - `test_canonical_state_hash_is_stable`: build `State(schema_version=1, next_monotonic_seq=0, epics={"epic-1": {"k": "v"}})`; canonicalize via `_canonicalize_state_for_hash`; compute sha256; assert hex matches a hard-coded expected.
    - `test_synthesize_hook_payload_handles_missing_tool_calls`: build an `AgentResult` with `tool_calls=()` (empty); call synthesizer; assert it raises a clear error (or returns a sentinel — pick one and document). The deferred-substrate intent is "the synthesizer expects exactly one tool_call in v1 fixtures"; if a fixture changes that, fail loud.
    - `test_state_hash_is_deterministic_across_runs`: subprocess-test pattern (mirror Story 1.13 hash stability test). Run a small script in two separate `uv run python` subprocesses; assert the same hex. Mark `@pytest.mark.integration` (subprocess test). SKIP on Windows if `uv` is not on PATH (`shutil.which("uv")`).
  - [ ] Per-package coverage: `tests/integration/test_abstraction_adequacy.py` itself is NOT under `src/`; coverage scope is `src/sdlc/` and `scripts/`. The unit tests for helpers cover the synthesizer + hash logic; the integration test exercises them in pipeline shape. Do NOT add the test file to `[tool.coverage.run].source` — tests are tests, not sources.

- [ ] **Task 7: Run the full quality gate stack and verify CI green (AC: all)**
  - [ ] `uv run ruff check src/ tests/ scripts/` → 0 errors. The new test file's imports must satisfy `from __future__ import annotations` (auto-required by `tool.ruff.lint.isort`).
  - [ ] `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [ ] `uv run mypy --strict src/` → 0 errors. Note: `tests/` are NOT under mypy strict (`[[tool.mypy.overrides]] module = "tests.*" disallow_untyped_defs = false`), but the helpers in the test file SHOULD still type-annotate cleanly — ruff's checks catch the obvious cases.
  - [ ] `uv run pre-commit run --all-files` → all hooks pass:
    - `ruff-check`, `ruff-format` (existing)
    - `mypy-strict` (existing)
    - `boundary-validator` (existing — runs on `tests/`; the new test file imports `from sdlc.{state,journal,runtime,contracts}` which is allowed because `tests/` is not subject to MODULE_DEPS forbidden_from rules; verify by reading boundary script).
    - `state-write-protocol-validator` (Story 1.10 — runs on `src/sdlc/`; should not flag `tests/` files because the validator is scoped to `^src/sdlc/.*\.py$`).
    - `journal-append-only-validator` (Story 1.11 — same scoping).
    - `runtime-import-via-abc-validator` (Story 1.13 — same scoping).
    - `secret-hardcode-validator` (Story 1.8 — scoped to `^src/sdlc/.*\.py$`).
    - `specialist-validator` (placeholder — runs on every commit).
  - [ ] `uv run pytest tests/integration/test_abstraction_adequacy.py -m integration -v` → green; 1 test (`test_abstraction_adequacy_pipeline[mock_factory]`) passes.
  - [ ] `uv run pytest tests/unit/integration/ -m unit -v` → green; helper unit tests pass.
  - [ ] Global `uv run pytest --cov=src --cov-fail-under=90` → coverage gate passes (the new test exercises Story 1.10/1.11/1.12/1.13 substrate further; should NOT drop coverage; if it does, investigate before merging).
  - [ ] Confirm goldens are committed: `git status` → `tests/fixtures/abstraction_adequacy/expected_hook_payloads.json`, `tests/fixtures/abstraction_adequacy/expected_state.json`, `tests/fixtures/abstraction_adequacy/README.md`, `tests/fixtures/mock_responses/abstraction-adequacy.yaml` are all tracked. The goldens directory does NOT need a `.gitkeep` since it has README + 2 JSON files.
  - [ ] Confirm `_REGENERATE_GOLDENS = False` in the final committed file (a `True` value would fail every subsequent CI run). Add a CI-side belt-and-braces check if desired (`grep -E "_REGENERATE_GOLDENS:?\\s*Final\\[bool\\]\\s*=\\s*True" tests/integration/test_abstraction_adequacy.py && exit 1 || exit 0` as a custom pre-commit hook) — OR leave as a code-review discipline (preferred for v1; mirrors how `xfail_strict = true` in `pyproject.toml:174` enforces the discipline at runtime).
  - [ ] Run the test on a fresh clone (or via `git clean -fdx; uv sync --frozen --group dev; uv run pytest tests/integration/test_abstraction_adequacy.py`) to confirm the goldens are loaded from disk (not from a stale `_REGENERATE_GOLDENS=True` run); the test must be fresh-clone reproducible.

## Dev Notes

### Why this story exists (FR + NFR + Decision mapping)

- **FR29 — Multi-Agent Specialist Dispatch via runtime-neutral interface (PRD §758-§760)**: Story 1.13 ships the runtime abstraction; Story 1.14 ships the CI gate that PROVES the abstraction is adequate (i.e., a Mock implementation produces the same dispatcher-side observable behavior the future Claude implementation will). Without 1.14, the abstraction is aspirational.
- **NFR-COMPAT-3 — Mock-runtime abstraction-adequacy test as CI gate (PRD §855)**: this story is the literal materialization of NFR-COMPAT-3. The test runs in `quality-gates` on every PR and is a hard merge-blocking gate.
- **Decision C2 — deterministic Mock + abstraction-adequacy CI gate (Architecture §316, §356)**: "abstraction-adequacy CI gate runs full pipeline against mock." This story is the gate. The "full pipeline" is approximated for v1 substrate; Story 2B.3 extends to the literal full pipeline.
- **Architecture §191 — paradigm framing**: "Naming this paradigm explicitly is itself a load-bearing decision. Every downstream concern — audit, atomic writes, AIRuntime, STOP triggers — is a consequence of where the determinism boundary is drawn." The abstraction-adequacy test is the boundary's CI sentinel.
- **Architecture §1185 — module-level abstraction-adequacy boundary**: "AIRuntime abstraction → `runtime/abc.py` (boundary) + CI test in `tests/integration/`." This story creates the CI test side of that named boundary.
- **Architecture §1424 — Epic 2A → 2B gate**: "Behavioral conformance contract (Story 1.14) extended to cover full orchestration pipeline against MockAIRuntime." Story 1.14 ships the v1 substrate gate; Story 2B.3 extends to the full pipeline + Claude variant.

### File set this story creates / modifies

**New files (created):**

- `tests/integration/test_abstraction_adequacy.py` — the abstraction-adequacy CI gate (~250-350 LOC including helpers + docstrings)
- `tests/unit/integration/__init__.py` — pytest collection sentinel
- `tests/unit/integration/test_abstraction_adequacy_helpers.py` — unit tests for the determinism helpers (~5 cases)
- `tests/fixtures/mock_responses/abstraction-adequacy.yaml` — seed fixture for the test (workflow_step="abstraction-adequacy")
- `tests/fixtures/abstraction_adequacy/README.md` — goldens directory readme + regen history
- `tests/fixtures/abstraction_adequacy/expected_hook_payloads.json` — golden HookPayload sequence (regenerated, not hand-written)
- `tests/fixtures/abstraction_adequacy/expected_state.json` — golden final state.json (regenerated, not hand-written)
- `docs/decisions/ADR-017-abstraction-adequacy-ci-contract.md` — new ADR
- `docs/CODEMAPS/integration-tests.md` (or update) — codemap for tests/integration/ (cross-link to Stories 2A.4 + 2B.3)

**Optional new file** (factor out if cross-test imports are fragile per Task 6):

- `tests/integration/_abstraction_adequacy_helpers.py` — `_synthesize_hook_payload`, `_canonicalize_state_for_hash`, `_state_hash`, constants (single-underscore prefix marks it as private). Keeps the test file lean and makes unit tests' import path unambiguous.

**Modified files:**

- `tests/fixtures/mock_responses/README.md` — add a paragraph naming `abstraction-adequacy.yaml` as the live abstraction-adequacy fixture
- `docs/decisions/index.md` — add ADR-017 row (preserve ADR-015 / ADR-016 rows owned by Stories 1.12 / 1.13)

**Files NOT modified (invariant — break-glass if any of these change):**

- `src/sdlc/runtime/*.py` — Story 1.13 closed; Story 1.14 is consumer-only.
- `src/sdlc/state/*.py`, `src/sdlc/journal/*.py` — Stories 1.10/1.11/1.12 closed; Story 1.14 consumes them via `__init__.py` re-exports.
- `pyproject.toml` — no new dep, no new marker, no new ruff/mypy/coverage config. Existing `integration` marker covers this.
- `.pre-commit-config.yaml` — no new hook. The integration test runs in pytest, not pre-commit (per the existing model).
- `.github/workflows/ci.yml` — no edit. The new test runs as part of `uv run pytest` in `quality-gates`. The chaos-tests job filters by `-m chaos` and won't pick up this `integration`-marked test (correct).
- `scripts/check_module_boundaries.py` — `tests/` is not subject to MODULE_DEPS forbidden_from rules (the boundary script is scoped to `src/sdlc/`, see `boundary-validator` files filter at `.pre-commit-config.yaml:54`).

### Why deferred-substrate stubs are honest, not hacks

The acceptance criteria from epics.md mention a "fixed pipeline (init → scan → mock dispatch → state projection → journal append) end-to-end." Several of those steps depend on substrate that does not exist when Story 1.14 implements:

| Step | Substrate | Story | Status at 1.14 dev time |
|---|---|---|---|
| init | tmp_path scaffolding | n/a | available (pytest builtin) |
| scan | `engine.scanner.scan` | 1.15 | NOT available |
| mock dispatch | `MockAIRuntime` | 1.13 | available (hard dep) |
| hook chain | `hooks.runner.run_hook_chain` | 2A.4 | NOT available |
| journal append | `journal.append_sync` | 1.11 | available |
| state projection | `state.project_from_journal` | 1.12 | available (hard dep) |
| state.json write | `state.write_state_atomic_sync` | 1.10 | available |

The honest path is to STUB the missing substrate inline (scan stub returns a known-empty State; hook synth manually constructs a HookPayload from each AgentResult) and document the stub as "Story X.Y will replace this and regen goldens." The dishonest paths are:

- **Skip the test until all substrate is built** — fails Architecture §1424's gate, leaves the abstraction unverified through Epic 1.
- **Build `engine/scanner.py` and `hooks/runner.py` here** — scope creep; those are owned by their respective stories; their test surface differs.
- **Run with a pretend "always-pass" assertion** — defeats the gate; goldens that don't actually verify behavior are worse than no test.

The stub approach is the BMad-method-canonical "ship the substrate, build forward incrementally" pattern (Stories 1.10–1.13 follow it). Story 2B.3 is the explicit checkpoint where the full real pipeline replaces the stubs.

### Why golden-file byte-equality (not structural-equality)

Golden files are checked-in BYTES. The assertion `actual_bytes == expected_bytes` catches:

- Pydantic minor version field re-ordering (silent in `model_dump(mode="json")`-equality, loud in byte-equality).
- Pydantic field-default changes (a new optional field with a default value would change the canonical JSON shape).
- Hash protocol drift (e.g., someone replacing `sort_keys=True` with `sort_keys=False`).
- Encoding drift (e.g., `ensure_ascii=False` vs `True` produces different bytes for non-ASCII strings).
- Line-ending drift (LF vs CRLF — caught by `.gitattributes` + `mixed-line-ending` pre-commit hook + the explicit `+ b"\n"` in `_canonicalize_state`).

Structural equality (`actual_dict == expected_dict`) silently swallows all of these. The byte-equality discipline is identical to Story 1.10's `_canonicalize_state` byte-equality and Story 1.13's `model_dump(mode="json")`-byte-equality; consistent across the project.

### Why two dispatches (not one, not three)

- **One dispatch** is too small to detect ordering bugs. A single-element sequence is order-trivial; the test would still pass even if the synthesizer accidentally returned `[hp_2, hp_1]` instead of `[hp_1, hp_2]`.
- **Three dispatches** is over-budget; the second dispatch is enough to assert determinism (Story 1.13 AC3 already proves N-dispatch determinism) and the synthesizer's seq-chained behavior. A third adds golden bytes without new signal.
- **Two dispatches** with identical `(prompt, context)` exercises:
  - Determinism of the AgentResult chain (sanity check on Story 1.13's AC3).
  - Sequence-ordering integrity in the HookPayload synthesizer (`seq=0` then `seq=1`).
  - Multi-entry journal append + projection chain (one-entry projection is a degenerate case).
  - `before_hash` chaining (entry 0's `before_hash=None`, entry 1's `before_hash=entry_0.after_hash`).

### Why `_REGENERATE_GOLDENS` (not a separate regeneration script)

Two options were considered:

1. **A standalone script `scripts/regen_abstraction_adequacy_goldens.py`** — pros: clean separation of "test" and "regen." Cons: duplicates the pipeline body; drift between script and test undermines the goldens' value.
2. **An in-test toggle `_REGENERATE_GOLDENS: bool`** — pros: pipeline body lives in one place; goldens are guaranteed-by-construction to match what the test asserts. Cons: requires the toggle to be `False` in committed code; misuse risk.

Option 2 wins because the pipeline IS the goldens' source of truth. A separate script would be a second source of truth, and source-of-truth divergence is the abstraction-adequacy gap the gate exists to catch — meta-irony aside, two paths is a footgun. The `True`/`False` discipline is enforced by code review (and optionally by a one-line grep in pre-commit).

### Forward-compat: What Story 2B.3 changes (and what it MUST NOT change)

When Story 2B.3 lands `ClaudeAIRuntime` and extends this test:

**MUST change (one-line each):**

- `_RUNTIME_FACTORIES` extends from `[_mock_factory]` to `[_mock_factory, _claude_factory]`.
- A new `_claude_factory(fixtures_dir: Path) -> AIRuntime: return ClaudeAIRuntime(...)` factory function (signature MUST match `_mock_factory`'s).
- The test parameterization now produces `test_abstraction_adequacy_pipeline[mock_factory]` AND `test_abstraction_adequacy_pipeline[claude_factory]`.

**MUST NOT change:**

- Goldens (`expected_hook_payloads.json`, `expected_state.json`) — Mock and Claude MUST produce the same bytes. If they don't, the abstraction has leaked Claude-specific assumptions and the gate fires.
- The seed prompt, seed context, frozen timestamp, frozen monotonic_seq, frozen actor — all are determinism anchors.
- The pipeline body — the abstraction's contract is "given the same input, both runtimes produce the same observable output." Changing the pipeline mid-extension would muddy the test.

If 2B.3 needs to add a setup step (e.g., the Claude factory needs a config fixture), it goes inside `_claude_factory(...)`, not in the test body. The test body MUST remain runtime-agnostic.

### Substrate dependencies — concrete API surface this story consumes

From the contracts:

```python
# from sdlc.contracts.hook_payload import HookPayload
HookPayload(
    schema_version=1,                          # Literal[1] = 1
    hook_name="abstraction-adequacy-synth",
    target_path="01-Requirement/04-Epics/EPIC-abstraction-adequacy.json",
    target_kind="epic",
    content_hash_before=None,                  # or "sha256:<64-hex>"
    write_intent="create",
)

# from sdlc.contracts.journal_entry import JournalEntry
JournalEntry(
    schema_version=1,                          # Literal[1] = 1
    monotonic_seq=0,                           # int >= 0
    ts="2026-05-08T00:00:00Z",                 # RFC 3339 UTC, regex-validated
    actor="agent:abstraction-adequacy",
    kind="state_mutation",
    target_id="epic-abstraction-adequacy",
    before_hash=None,                          # or "sha256:<64-hex>"
    after_hash="sha256:<64-hex>",
    payload={"output_text": ..., "tokens_in": ..., "tokens_out": ...},
)
```

From the substrate APIs:

```python
# from sdlc.state import State, write_state_atomic_sync
State(schema_version=1, next_monotonic_seq=0, epics={})
write_state_atomic_sync(state: State, target: Path) -> None       # POSIX-only

# from sdlc.journal import append_sync, iter_entries
append_sync(entry: JournalEntry, journal_path: Path) -> int       # returns monotonic_seq; POSIX-only
iter_entries(journal_path: Path) -> Iterator[JournalEntry]         # cross-platform

# from sdlc.state.projection import project_from_journal
project_from_journal(journal_path: Path) -> State                  # pure function; cross-platform

# from sdlc.runtime import AIRuntime, AgentResult, MockAIRuntime
MockAIRuntime(fixtures_dir: Path) -> AIRuntime                     # constructor
await runtime.dispatch(prompt: str, context: Mapping[str, object]) -> AgentResult
```

If any of these signatures shift between Stories 1.10–1.13 dev and Story 1.14 dev, this story's pre-flight (Task 1) catches it; abort and reconcile.

### Previous story intelligence — Stories 1.10 + 1.11 + 1.12 + 1.13

Patterns to mirror exactly (validated through 1.10's 9 patches and 1.11/1.12/1.13's review cycles):

- **`from __future__ import annotations`** at top of every new `.py` file.
- **Module-level `pytestmark` for skip + marker stacking**: `pytestmark = [pytest.mark.integration, pytest.mark.skipif(sys.platform == "win32", ...)]`. Mirrors `tests/chaos/test_atomic_write_kill_points.py` and `tests/property/test_journal_append_only.py`.
- **Cross-platform vs POSIX-only**: this test is **POSIX-only** because `journal.append_sync` and `state.write_state_atomic_sync` raise `NotImplementedError` on Windows. Skip at module level.
- **`Final[...]` constants** for module-level immutables: `_SEED_PROMPT`, `_SEED_CONTEXT`, `_FROZEN_TS`, `_ACTOR`, `_TARGET_ID`, `_GOLDEN_DIR`, `_MOCK_FIXTURES_DIR`, `_REGENERATE_GOLDENS`. Mirror Story 1.13's `_SHA256_PREFIX`.
- **Narrow exception catches**: this test does not catch errors. The pipeline propagates them; pytest reports them. Do NOT add `try`/`except` for "robustness" — failures ARE the signal.
- **Pure helper functions**: `_canonicalize_state_for_hash`, `_state_hash`, `_synthesize_hook_payload`, `_build_journal_entry`, `_mock_factory` — module-level, pure, single-underscore-prefixed (private but importable for unit tests). Mirror Stories 1.10/1.12/1.13's helper-function pattern.
- **Test-seam private functions**: helpers are single-underscore-prefixed, importable from `tests/unit/integration/`. Mirror Story 1.10's `_canonicalize_state` and Story 1.13's `_load_fixtures`.
- **Pydantic v2 patterns**: `model.model_dump(mode="json")` for JSON-shape serialization; pydantic frozen-ness for `_SEED_CONTEXT` (use `MappingProxyType`).
- **Asyncio without pytest-asyncio**: `asyncio.run(coro)` directly inside sync test functions. Project does NOT depend on `pytest-asyncio` (Story 1.13 precedent).
- **Subprocess tests for cross-process determinism**: marked `@pytest.mark.integration`; check `shutil.which("uv")` to skip on machines without uv. Mirror Story 1.13's `test_prompt_hash_is_stable_across_python_runs`.

Code-review feedback from Stories 1.10 + 1.11 + 1.12 + 1.13 to pre-empt:

- Be explicit about exception chaining (`raise X(...) from exc`) where appropriate (n/a here — no exception construction in test code).
- Avoid `Any` in type hints — use `Mapping[str, object]`, `tuple[...]`, `Path`.
- Verify `mypy --strict` passes BEFORE committing. The strict config in `pyproject.toml:108` will reject untyped functions, missing returns, and Any leaks. Tests are NOT under strict (`tests.*` override at `pyproject.toml:118-121`), but the helpers should still type-annotate cleanly.
- Use access-mode check pattern where relevant (n/a here — no fd manipulation).
- Narrow exception catches; do NOT swallow programmer errors.
- For coverage: tests are NOT in coverage scope (`source = ["src/sdlc", "scripts"]` per `pyproject.toml:186`). The integration test should not change coverage numbers up or down — if it does, something's miswired.
- For golden files: byte-equality assertions are stricter than dict-equality; do not weaken to "structural equality" under reviewer pressure — that defeats the gate.

### Git intelligence — last 5 commits (as of story authoring)

```
26f619a feat: implement append-only journal with property tests and linter (Story 1.11)
2f4322d feat: implement atomic state write protocol with chaos tests (Story 1.10)
ce351c5 chore: ignore graphify output and config files
99c8f78 chore: update skills, add Story 1.9, graphify output, and project config
b378b5a fix: apply code-review patches for Story 1.8 config module
```

**Notable**: Stories 1.12 (state projection) and 1.13 (AIRuntime + Mock) are `ready-for-dev` per sprint-status.yaml — both authored but not yet implemented at story-author time. Story 1.14 has hard dependencies on both. **Pre-flight (Task 1) gates this**: if 1.12 OR 1.13 has not landed when 1.14 is dev'd, halt and escalate. Do NOT attempt to implement 1.14 without 1.12+1.13 substrate on disk.

If 1.11 (currently `review`) regresses or its patches change `journal.append_sync`'s return type, this story's `append_sync(je_0, journal_path=...)` lines must be reconciled — append_sync returns `int` (the assigned `monotonic_seq`); we don't currently use the return value (we pre-compute seqs from local counters), but be aware.

**Commit pattern to follow** (Stories 1.10/1.11/1.12/1.13 precedent):

- One `feat: implement abstraction-adequacy CI test (Story 1.14)` commit covering: `tests/integration/test_abstraction_adequacy.py`, `tests/unit/integration/__init__.py`, `tests/unit/integration/test_abstraction_adequacy_helpers.py`, `tests/fixtures/mock_responses/abstraction-adequacy.yaml`, `tests/fixtures/mock_responses/README.md` edit, `tests/fixtures/abstraction_adequacy/`, `docs/decisions/ADR-017-*.md`, `docs/decisions/index.md` edit, `docs/CODEMAPS/integration-tests.md`.
- Optional: one `fix: apply code-review patches for Story 1.14` follow-up if reviewers flag golden-file or determinism issues (Stories 1.8/1.10/1.11 precedent).

### Latest tech information

- **Python 3.10+** target (`pyproject.toml:10`). Used: `Final[...]`, `Mapping[str, object]`, `MappingProxyType`, `asyncio.run`, `Callable[[Path], AIRuntime]`. All stable in 3.10+.
- **pytest 8.x** (`pyproject.toml:24`). `@pytest.fixture(params=..., ids=lambda: ...)` is stable. `pytestmark = [...]` for module-level multi-marker stacking is the canonical pytest pattern.
- **pydantic v2** (Stories 1.7+). `model.model_dump(mode="json")` produces a JSON-coercible dict (e.g., `tuple` → `list`); `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))` over that dict is the canonical hash/disk byte form (Architecture §501-§508, §513). The trailing `\n` distinguishes "disk canonical" (with `\n`) from "hash canonical" (without `\n`) per `state/atomic.py:_canonicalize_state` vs Architecture §513.
- **PyYAML 6.x** (`pyproject.toml:13`). The seed fixture YAML is loaded by `MockAIRuntime` (Story 1.13's `_load_fixtures`). This story does NOT call `yaml.safe_load` directly — the fixture flows through the runtime.
- **`hashlib.sha256`** (stdlib). Stable hex digests across Python versions and across runs. Used for `_state_hash` and (transitively) `MockAIRuntime._hash_prompt`.
- **`asyncio.run(coro)`** (stdlib, Python 3.10+). No `pytest-asyncio` dep; mirrors Story 1.13.
- **`pytest.fixture` parameterization with `ids=lambda`**: pytest's `ids=` callable runs once per param value at collection time; the resulting strings appear in the test's pytest output (`test_X[mock_factory]`). Stable since pytest 6.x.

### Project Structure Notes

- **Alignment with unified project structure**: this story creates `tests/integration/test_abstraction_adequacy.py` (canonical name from Architecture §1185 + epic AC). It reuses `tests/fixtures/mock_responses/` (Story 1.13) and creates `tests/fixtures/abstraction_adequacy/` for goldens. Both fixture paths are under `tests/fixtures/` per Architecture §692, §1011.
- **No conflict with architecture**: every file path lives under directories the architecture has declared. The new `tests/fixtures/abstraction_adequacy/` directory is a sibling of `mock_responses/` and `golden_corpus/` (Architecture §1012-§1013). Pattern matches.
- **Pyproject markers**: `unit`, `integration` already exist. No new marks. The integration test runs in the existing `quality-gates` job; no chaos / property / benchmark / e2e marker needed.
- **CI workflow**: NO new CI job. The new test runs as part of the existing `quality-gates` job's `uv run pytest` step. The existing `chaos-tests` job filters by `-m chaos --no-cov` and won't pick this up.
- **Coverage**: `tests/` files are not in coverage `source` (`pyproject.toml:186`). Tests exercise `src/sdlc/` code; coverage is measured on src, not tests.
- **MODULE_DEPS**: tests are not subject to `MODULE_DEPS["X"].forbidden_from` rules. The boundary script's `ALLOWED_TESTS_IMPORTS` (or equivalent) covers this — verify in Task 1 by reading `scripts/check_module_boundaries.py`'s `tests/` handling.

### Why deferred from this story

These are explicitly NOT in scope for Story 1.14 — flag if they creep in during implementation:

- **`engine/scanner.py` (`engine.scanner.scan`)** — Story 1.15. The "scan" pipeline step is a no-op stub here. When 1.15 lands, the stub is replaced and goldens regen.
- **`hooks/runner.py` (`hooks.run_hook_chain`)** — Story 2A.4. The "hook synth" pipeline step is an inline helper here. When 2A.4 lands, the synth is replaced with the real chain and goldens regen.
- **`runtime/claude.py` (`ClaudeAIRuntime`)** — Story 2B.1. The `_RUNTIME_FACTORIES` list is `[_mock_factory]` only. When 2B.1 + 2B.3 land, the list extends and goldens MUST hold for both factories.
- **Real prompt-injection corpus** — Story 2B.4. The seed prompt for the abstraction-adequacy test is a benign deterministic string; injection-corpus tests are a separate gate.
- **Tool-safety contract tests** — Story 2B.6. Out of scope.
- **Workflow YAML loading** — Story 2A.1. The seed dispatch uses a literal `workflow_step="abstraction-adequacy"` string; no workflow YAML is loaded.
- **Specialist registry / frontmatter validation** — Stories 2A.2, 2B.8-11. The seed dispatch's mock fixture is hand-written, not produced by a specialist.
- **Streaming dispatch** — Decision C1 + Architecture §327 explicitly defer; the abstraction is non-streaming. Out of scope.
- **Token-budget enforcement** — Story 2A.3. The mock returns `tokens_in=42, tokens_out=84` per the fixture; nothing enforces a cap.
- **Multi-fixture / multi-prompt scenarios** — out of scope. v1 abstraction-adequacy uses ONE seed (two dispatches of the same seed). Story 2B.3 may add a second scenario; not required for v1.
- **Performance budgets** — `tests/benchmark/` is for `pytest-benchmark` regression gates (Architecture §996-§999). The abstraction-adequacy test should run in < 5s; if it grows past that, factor out hot-path. Not a separate benchmark.
- **Network-isolated CI test (NFR-PRIV-1)** — Story 2B.7 / docs threat-model. The mock is an in-process pure function; no network calls happen even without isolation.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.14] (lines 752-775) — story spec, AC blocks
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.15] (line 785-786) — adjacent story; "Given Story 1.14 complete" gates engine.scanner.scan, confirms 1.14 is the substrate-completion sentinel
- [Source: _bmad-output/planning-artifacts/epics.md#Story-2B.3] (lines 1485-1496) — extension story; the contract this v1 substrate ships in service of
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-1-Summary] (line 960) — "abstraction-adequacy behavioral conformance test" listed as a v1 test gate
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-2A-Gate-to-Epic-2B] (line 1424) — "Behavioral conformance contract (Story 1.14) extended to cover full orchestration pipeline against MockAIRuntime"
- [Source: _bmad-output/planning-artifacts/architecture.md#Paradigm] (line 191) — "AIRuntime abstraction. Load-bearing only if exercised by ≥ 1 non-Claude implementation in v1."
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-C1] (lines 315, 355) — async dispatch returning AgentResult, no streaming
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-C2] (lines 316, 356) — deterministic mock + abstraction-adequacy CI gate
- [Source: _bmad-output/planning-artifacts/architecture.md#Hash-Canonicalization] (line 513) — canonical hash protocol (no trailing newline) vs disk canonicalization (with newline)
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Boundary-Concern] (line 1185) — "AIRuntime abstraction → runtime/abc.py + CI test in tests/integration/"
- [Source: _bmad-output/planning-artifacts/architecture.md#Test-Layout] (lines 685-695) — tests/integration/ canonical location, naming convention
- [Source: _bmad-output/planning-artifacts/architecture.md#Mock-Fixtures-Location] (lines 692, 1012) — `tests/fixtures/mock_responses/`
- [Source: _bmad-output/planning-artifacts/architecture.md#POSIX-Gating] (lines 573, 493) — POSIX-only substrate (justifies module-level Windows skip)
- [Source: _bmad-output/planning-artifacts/architecture.md#Pydantic-Schemas] (lines 595-621) — JournalEntry + HookPayload contract shapes
- [Source: _bmad-output/planning-artifacts/prd.md#FR29] — runtime-neutral AIRuntime interface (NFR-COMPAT-3 makes this a CI gate)
- [Source: _bmad-output/planning-artifacts/prd.md#NFR-COMPAT-3] (line 855) — "Mock AIRuntime adequacy test as CI gate"
- [Source: _bmad-output/implementation-artifacts/1-13-airuntime-abc-mock-airuntime.md] — Story 1.13 (immediate predecessor) — runtime substrate this story consumes
- [Source: _bmad-output/implementation-artifacts/1-12-state-projection-from-journal-replay-property-test.md] — Story 1.12 — `project_from_journal` substrate
- [Source: _bmad-output/implementation-artifacts/1-11-append-only-journal-property-test.md] — Story 1.11 — `journal.append_sync` substrate
- [Source: _bmad-output/implementation-artifacts/1-10-atomic-write-protocol-chaos-tests.md] — Story 1.10 — `state.write_state_atomic_sync` substrate
- [Source: src/sdlc/contracts/hook_payload.py:1-32] — HookPayload pydantic model
- [Source: src/sdlc/contracts/journal_entry.py:1-54] — JournalEntry pydantic model
- [Source: src/sdlc/state/atomic.py:54-66] — `_canonicalize_state` byte-form pattern (mirror for golden generation)
- [Source: .github/workflows/ci.yml:25-28] — CI matrix that this test runs across
- [Source: .pre-commit-config.yaml] — pre-commit chain order (no edit by this story)
- [Source: pyproject.toml:118-121] — `tests.*` mypy override (relaxed strictness)
- [Source: pyproject.toml:176-183] — pytest markers (`integration` already declared)
- [Source: pyproject.toml:186-203] — coverage source / omit (tests are not in scope)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
