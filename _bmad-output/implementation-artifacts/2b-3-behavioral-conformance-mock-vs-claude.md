# Story 2B.3: Behavioral Conformance Mock-vs-Claude (Extension of Story 1.14)

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Winston's drift-gap closer,
I want the abstraction-adequacy CI test (Story 1.14) extended to run the full pipeline against both `MockAIRuntime` and `ClaudeAIRuntime` and assert identical `HookPayload` event sequences plus byte-identical final `state.json`,
so that Mock-vs-Claude drift is caught in CI, not in production (Decision C2 + Concern #2, FR29).

## Acceptance Criteria

> **Source ACs:** `_bmad-output/planning-artifacts/epics.md:1507-1529` (3 AC groups → AC1–AC3 below).
> **DAG position:** **Layer 2**, Epic 2B. Depends on **2B.1** (`ClaudeAIRuntime` + `AgentResult.mock` per ADR-029). **ON THE CRITICAL PATH** `2B.1 → 2B.3 → 2B.10 → 2B.11` (DAG §4). Layer-3 stories **2B.8 / 2B.9 / 2B.10** each carry an AC requiring this conformance harness to exercise the new specialist Mock-vs-Claude — a slip here starves the entire specialist-authoring layer (DAG §3 Risk note).
> **No new wire-format contract.** Modifies `tests/integration/test_abstraction_adequacy.py` (the existing CI gate from Story 1.14) and its golden fixtures. `_RUNTIME_FACTORIES` is the deliberate parametrisation hook documented inline (`test_abstraction_adequacy.py:75-78`).
> **No new `JournalEntry.kind` values.** Reuses existing `agent_dispatched` / `artifact_written` kinds emitted by the real dispatch path.
>
> **Scope boundary — do NOT reinvent:**
> - The harness already exists (`tests/integration/test_abstraction_adequacy.py` from Story 1.14). The work is **extension**, not new authorship: add `_claude_factory`, supply a stub `claude` binary, replace deferred-substrate stubs (scan / hook-synth) per AC1/D2, and tighten the unified-diff failure path per AC2.
> - **`AgentResult.mock` is already present** (Story 2B.1 / ADR-029 §1). Do **not** redesign it; AC4 enforces that `mock` must NOT pollute the byte-identical golden `state.json` — see AC4/D1 for the projection-vs-payload separation.
> - The stub `claude` script convention is established (`tests/fixtures/claude_stubs/` from Story 2B.1, see `2b-1-claudeairuntime-implementation-subprocess-management.md#File List`). **Re-use it**; do not create a sibling fixtures directory.

### AC1 — Parameterized conformance: pipeline runs once per runtime factory

**Given** Stories 1.14 (Mock-only conformance) + 2B.1 (`ClaudeAIRuntime` impl) `done`
**When** the parameterized CI test runs (`tests/integration/test_abstraction_adequacy.py`)
**Then** `_RUNTIME_FACTORIES` is extended from `[_mock_factory]` to `[_mock_factory, _claude_factory]` (exactly two — the inline comment at `test_abstraction_adequacy.py:77` ("DO NOT add a third factory in v1") is the contract surface)
**And** the parametrised `runtime` fixture (`test_abstraction_adequacy.py:96-102`) runs the existing `test_abstraction_adequacy_pipeline` once with `runtime_factory=_mock_factory` and once with `runtime_factory=_claude_factory`
**And** the same fixed pipeline shape is used for both runs (init → scan → dispatch ×2 → hook synth/chain → journal append → projection → atomic state.json write)
**And** the asserted contracts are: identical sequence of `HookPayload` events (the existing `expected_hook_payloads.json` golden) + **byte-identical** final `state.json` (the existing `expected_state.json` golden) — both goldens are runtime-agnostic and must NOT need per-runtime variants (see AC4)

**And** **AC1/D1 — stub `claude` binary contract:** `_claude_factory` constructs a `ClaudeAIRuntime` whose `claude` binary is a deterministic stub on `PATH` (the **2B.1 pattern**: `tests/fixtures/claude_stubs/`, set via `monkeypatch.setenv("PATH", ...)`). The stub's stdout MUST produce a Claude-CLI `--output-format json` envelope whose `result` field deserialises to the **same `AgentResult.output_text` + `tool_calls` + `tokens_in` + `tokens_out`** values as `MockAIRuntime`'s seed fixture (`tests/fixtures/mock_responses/abstraction-adequacy.yaml`). The only field that may differ is `mock` (`True` for Mock, `False` for Claude — see AC4). **Pick one — pin in the Change Log:**
  - **D1 (Recommended):** generate the stub script at test-setup time from the seed YAML — a tiny Python script that re-reads the fixture and prints the JSON envelope for that exact `(workflow_step, prompt_hash)`. **Pros:** single source of truth (the YAML); fixture-edit drift cannot desynchronise the two runtimes. **Cons:** one helper function in `_abstraction_adequacy_helpers.py`.
  - **D2:** check in a static `tests/fixtures/claude_stubs/abstraction_adequacy.py` next to the YAML. **Cons:** two sources of truth; a fixture edit that forgets to regenerate the stub silently passes Mock but fails Claude (or worse, both pass against drifted goldens).
  - **Recommended: D1.** Helper name: `_build_claude_stub_for_fixture(fixture_path: Path, target_dir: Path) -> Path` (returns the on-`PATH` stub path).

**And** **AC1/D2 — scope of "the same fixed pipeline":** Story 1.14's test currently uses deferred-substrate stubs at Step 2 (no-op `scan`) and Step 4 (`_synthesize_hook_payload`) — the inline comments at `test_abstraction_adequacy.py:9-16, 128-129, 144-146` flag both as "Story 2B.3 will switch this to the real ...". Pick ONE:
  - **D1 (Recommended):** **replace the hook-synth stub with the real `hooks.runner.run_hook_chain` invocation** (Story 2A.4 substrate is `done`); keep the no-op `scan` as-is because `tmp_path` has no SDLC artefact dirs and the scan-vs-pipeline equivalence is exercised by Story 1.15's own tests. The deferred-substrate comment on the scan step is amended; the hook-synth stub `_synthesize_hook_payload` and the inline regen-warning block are deleted. **Pros:** narrowest scope that satisfies the AC1 "full pipeline" wording — hooks are the part Mock-vs-Claude can diverge on (because dispatcher emits the chain); `scan` is identical regardless of runtime. **Cons:** the test now depends on `hooks.runner` shape — a hook-chain refactor breaks this gate.
  - **D2:** replace both stubs at once. **Cons:** widens scope; couples 2B.3 to `engine.scanner` shape; no measurable additional drift coverage because `scan(tmp_path)` returns the canonical empty projection for both runtimes.
  - **Recommended: D1.** Record in the PR Change Log. If D2 is chosen, open `EPIC-2B-DEBT-CONFORMANCE-SCAN-SUBSTRATE` in `deferred-work.md` per ADR-026 §1.

### AC2 — Divergence failure surfaces a unified diff (both event sequence + final state)

**Given** the conformance test detects a divergence (either runtime produces a different `HookPayload` sequence or a different `state.json` byte stream)
**When** CI runs
**Then** the failure message includes **two unified diffs**:
  - a unified diff of the two event sequences (`HookPayload` round-tripped via canonical JSON — sorted keys, no insignificant whitespace), and
  - a unified diff of the two final `state.json` byte streams (decoded as UTF-8 for the diff; the **byte equality** is the assertion, the diff is for the human)
**And** the diff output is the **actual `bytes` content**, not just a "<bytes differ at offset N>" summary
**And** the PR is blocked (a failing assertion in a `pytest.mark.integration` gate already blocks via the standard CI job)

**And** **AC2/D1 — diff helper placement:** add `_format_diff(label: str, expected: bytes, actual: bytes) -> str` to `tests/integration/_abstraction_adequacy_helpers.py` (the existing private helper module). Use `difflib.unified_diff` over UTF-8-decoded `.splitlines(keepends=True)`. Surface as the `assert ..., msg` second argument on the two AC1 byte-equality asserts. Reuse the same helper for both diffs — one definition, two callers.

**And** **AC2/D2 — failure-output is the per-runtime delta (mock vs claude), not goldens-vs-actual:** the existing test asserts `actual == expected_golden` per runtime. **For 2B.3 this is insufficient** — a *common* drift (both runtimes produce different bytes from the golden in the same way) would surface as two identical "drift" messages, not as "mock vs claude diverge". Add a **third assertion**: after the per-runtime golden assertions inside the parametrised body, accumulate the actual bytes across both runs (a module-scoped or session-scoped `dict[str, bytes]` keyed by factory name); a **session-finalize hook** (`pytest_sessionfinish` in a local `conftest.py`, or a final test ordered after both parametrised runs) asserts the two captured byte streams are equal and surfaces the per-runtime delta via the same `_format_diff` helper. Document the parametrisation-vs-cross-run-assertion split in the test docstring; do not silently couple the two assertions in a single body.

### AC3 — Extensibility: adding a specialist fixture extends coverage with zero test code changes

**Given** the conformance test infrastructure
**When** a new specialist is added in Story 2B.8 / 2B.9 / 2B.10 / 2B.11
**Then** adding a **fixture row** for the new specialist (a `(workflow_step, prompt_hash) → response` entry in `tests/fixtures/mock_responses/<seed>.yaml` plus, per AC1/D1, the stub `claude` auto-derives the same response) is sufficient to extend conformance coverage to that specialist
**And** no edits to `tests/integration/test_abstraction_adequacy.py` are required for typical specialist additions
**And** the seed-fixture format is documented inline at the top of `tests/fixtures/mock_responses/abstraction-adequacy.yaml` (or sibling README) so a Story 2B.8 author can extend it without reading this story's PR

**And** **AC3/D1 — extension surface — pick one:**
  - **D1 (Recommended):** extend the existing single seed fixture `abstraction-adequacy.yaml` with additional `(workflow_step, prompt_hash)` rows for each new specialist; the test runs `dispatch` once per specialist within the same parametrised pipeline. Stub `claude` auto-derives per AC1/D1. **Pros:** zero test code edit per addition; goldens regenerated by the documented `_REGENERATE_GOLDENS=True` ceremony at the bottom of `test_abstraction_adequacy.py:221-228`. **Cons:** the seed fixture grows; one regen per specialist add.
  - **D2:** introduce one seed fixture per specialist + glob discovery in the test. **Cons:** more moving parts; no measurable benefit over D1 for v1's specialist count (~25).
  - **Recommended: D1.** Document the extension procedure (add a YAML row, regen goldens, no code change) as a 3-step checklist in the seed fixture's leading comment.

### AC4 — `mock` envelope MUST NOT pollute the byte-identical golden `state.json`

**Given** ADR-029 §1 (`AgentResult.mock: bool`) added by Story 2B.1 / verified in `src/sdlc/runtime/abc.py:33`
**When** the conformance pipeline runs against the two factories
**Then** the projected `state.json` byte stream MUST be **byte-identical** across `_mock_factory` and `_claude_factory` — the `mock` field MUST be invisible in the projection
**And** `state.json`'s shape is determined by `src/sdlc/state/projection.py:project_from_journal`; if the journal-replay projection includes any field derived from `AgentResult.mock` (whether directly or via dispatcher journal `payload.mock`), that field MUST be filtered out before serialisation, OR (preferred) the projection MUST NOT depend on `mock` in the first place — document which is the case
**And** a **unit test** in `tests/unit/state/test_projection.py` (or sibling) asserts: a journal-pair `(payload.mock=True, payload.mock=False)` with otherwise-identical entries projects to **byte-equal** `state.json` bytes — this is the **invariant** that makes the conformance harness's `state.json` golden runtime-agnostic in the first place

**And** **AC4/D1 — projection-vs-payload separation:** ADR-029 §1 + §4 specify `mock` lives in the **journal payload** (audit-trail) and `agent_runs.jsonl` (telemetry). It is **deliberately absent from `state.json`** because state is the runtime-neutral projection — a downstream consumer (dashboard, `sdlc next`) MUST NOT branch on mock-vs-real. **If the dev finds `state.json` already differs between the two runtimes**, that is the divergence this story exists to surface — root-cause it (likely `payload.mock` leaked into projection), close it in `state/projection.py`, and the AC4 unit test is the receipt. Do NOT add a per-runtime golden as a workaround.

### AC5 — Anti-tautology receipt

**Given** ADR-026 §1 (anti-tautology requirement)
**When** the test suite runs
**Then** the conformance test is proven load-bearing by **at least two** behavioural receipts:
  1. **Stub-divergence receipt:** a deliberately-divergent stub `claude` (e.g. a one-byte mutation of `output_text`) fed into `_claude_factory` is asserted to make the cross-run assertion (AC2/D2) RED — proves the byte-equality check **can** fail, not just pass vacuously
  2. **Projection-neutrality receipt (AC4):** the AC4 unit test asserts byte-equality on a `payload.mock=True` vs `payload.mock=False` journal pair — proves the projection **does** strip `mock`, not just happens to coincide on the seed fixture
**And** the RED-before-GREEN ordering is visible in `git log --reverse` for the public test surface (the parametrised `runtime` fixture extension + the AC2/D2 cross-run assertion are the public-surface logic; the stub-derivation helper is implementation detail)

## Tasks / Subtasks

- [x] **Task 1 — `_claude_factory` + stub `claude` binary** (AC: 1)
  - [x] Failing test (RED): `_RUNTIME_FACTORIES` contains `_claude_factory`; parametrised `runtime` fixture runs the pipeline body with a `ClaudeAIRuntime` whose stub is on `PATH`
  - [x] Implement `_build_claude_stub_for_fixture(...)` in `tests/integration/_abstraction_adequacy_helpers.py` (AC1/D1); the stub re-reads the seed YAML and prints the matching `result` payload as a Claude `--output-format json` envelope
  - [x] `_claude_factory(fixtures_dir: Path) -> AIRuntime`: builds the stub on `tmp_path`, `monkeypatch.setenv("PATH", ...)`, returns `ClaudeAIRuntime(...)` — fixture-scoped `monkeypatch` lifetime is the per-parametrisation tear-down boundary
  - [x] Update `_RUNTIME_FACTORIES = [_mock_factory, _claude_factory]`; verify the `# DO NOT add a third factory in v1` invariant comment is preserved
- [x] **Task 2 — Replace hook-synth stub with real `hooks.runner.run_hook_chain`** (AC: 1, 2)
  - [x] Failing test (RED): assert `synthesized_hook_payloads` are emitted by the real chain — delete `_synthesize_hook_payload` and the test imports/calls fail
  - [x] Replace `tests/integration/test_abstraction_adequacy.py:147-149` (the `hp_1 = _synthesize_hook_payload(...)` block) with the real `await hooks.runner.run_hook_chain(payload, ...)` invocation; the dispatched chain emits `HookPayload`s — capture the emission order
  - [x] Regenerate `tests/fixtures/abstraction_adequacy/expected_hook_payloads.json` via the documented `_REGENERATE_GOLDENS=True` ceremony (run on Linux/macOS — POSIX-only); audit the diff before commit
  - [x] Per AC1/D2 deviation rule: if the scan stub is ALSO replaced (D2 path), open `EPIC-2B-DEBT-CONFORMANCE-SCAN-SUBSTRATE` and amend this task
- [x] **Task 3 — Unified-diff failure path + cross-run assertion** (AC: 2)
  - [x] Failing test (RED): a fixture pair with deliberately-divergent bytes produces a failure message containing `--- mock` / `+++ claude` unified-diff lines, not bare "bytes differ"
  - [x] Implement `_format_diff(label, expected, actual)` in `_abstraction_adequacy_helpers.py` (AC2/D1) using `difflib.unified_diff`
  - [x] Wire `_format_diff` into the existing two per-runtime golden asserts as the `assert ..., msg` second arg
  - [x] Implement the AC2/D2 cross-run assertion: capture per-factory actual bytes in a module-scoped dict during the parametrised body; add a final session-finalise assertion (local `conftest.py` `pytest_sessionfinish` or an ordered final test) asserting `mock_bytes == claude_bytes` with the `_format_diff` message
- [x] **Task 4 — Extensibility procedure documented in seed fixture** (AC: 3)
  - [x] Add a leading comment block to `tests/fixtures/mock_responses/abstraction-adequacy.yaml` documenting the 3-step add-a-specialist checklist: (1) append `(workflow_step, prompt_hash) → response` row, (2) run `_REGENERATE_GOLDENS=True` once, (3) commit goldens + this YAML in a single specialist-add PR
  - [x] Unit test: load the seed YAML, assert the documentation block is present (so a future YAML rewrite that strips it fails CI) — guards the AC3 "zero test code edit" contract
- [x] **Task 5 — `state.json` projection neutrality wrt `mock`** (AC: 4)
  - [x] Failing test (RED) in `tests/unit/state/test_projection.py` (or sibling): two-entry journal — entry A with `payload.mock=True`, entry B with `payload.mock=False`, otherwise identical — projects to byte-equal `state.json` bytes
  - [x] Inspect `src/sdlc/state/projection.py:project_from_journal` against the failure; if the projection includes a `mock`-derived field, strip it (per AC4/D1); if not, document in the unit test docstring why the projection is already neutral (a discovery this story makes explicit)
  - [x] If the strip lands in `state/projection.py`, open a single-line ADR note (does NOT require a full ADR — `state.json` already excludes `mock` by design per ADR-029 §1; this is a guard, not a contract edit)
- [x] **Task 6 — Anti-tautology receipt + quality gate** (AC: 5)
  - [x] **Receipt #1:** behavioural stub-divergence test — `tests/integration/test_abstraction_adequacy_anti_tautology.py` (or inline in `test_abstraction_adequacy.py`): a copy of the conformance run with a deliberately-mutated stub `claude` is asserted to FAIL with the AC2/D2 cross-run diff message
  - [x] **Receipt #2:** the AC4 projection-neutrality unit test is the second receipt (AC5 lists both)
  - [x] Run full quality gate (CONTRIBUTING §1): `ruff format` + `ruff check` + `mypy --strict` + `pytest` + coverage ≥87 (`pyproject.toml --cov-fail-under`) + `pre-commit run --all-files` + `mkdocs --strict` + wire-format snapshots (`scripts/freeze_wireformat_snapshots.py --check`)

## Dev Notes

### Relevant architecture patterns and constraints

- **`AIRuntime` ABC + `AgentResult` contract** — `src/sdlc/runtime/abc.py:15-53`. `dispatch` is `async`, takes `(prompt: str, context: Mapping[str, object])`, returns `AgentResult(output_text, tool_calls, tokens_in, tokens_out, mock)`. `extra="forbid", frozen=True` — both runtimes return the same shape; `mock` is the only field whose value legitimately differs.
- **The existing conformance harness** — `tests/integration/test_abstraction_adequacy.py:1-228`. **READ THIS FILE END-TO-END before writing anything** — every "Story 2B.3 will ..." inline comment (`:9-16, :75-78, :128-129, :144-146, :221-228`) is a contract this story honours. The `_REGENERATE_GOLDENS` ceremony at lines 221-228 is the canonical golden-regen procedure — do not invent a second.
- **Stub `claude` binary pattern** — `tests/fixtures/claude_stubs/` (created by Story 2B.1; see 2B.1 File List). Pattern: a tiny shell or Python script placed on a tmp `PATH` via `monkeypatch.setenv("PATH", tmp_dir + os.pathsep + os.environ["PATH"])`. The 2B.1 stubs model edge cases (kill / slow / malformed-JSON / well-formed). 2B.3 needs **one more stub shape**: a "well-formed echo of the seed YAML's `result` payload" stub — generate it per AC1/D1.
- **`ClaudeAIRuntime` invocation contract** — `src/sdlc/runtime/claude.py:183-187` spawns `subprocess.Popen([..., "claude", ...], stdin/stdout/stderr=PIPE, text=True, encoding="utf-8", errors="strict")`. The stub MUST honour this: read prompt from stdin, write Claude-CLI `--output-format json` envelope to stdout, exit 0. The envelope shape parsed by `_parse_claude_stdout` (`runtime/claude.py:49-50` per 2B.1 review patch P5) is `{"type": "result", "is_error": false, "result": "<output_text>", "usage": {"input_tokens": N, "output_tokens": M}}` — verify exact field names against `runtime/claude.py:_parse_claude_stdout` before generating stubs.
- **Real hook chain (per AC1/D2 D1)** — `src/sdlc/hooks/runner.py:run_hook_chain`. Story 2A.4 substrate; pre-write hook registry in `pyproject.toml [tool.sdlc.hooks] pre_write`. The chain emits one `HookPayload` per registered hook per dispatch; the test currently fakes two `HookPayload`s with `_synthesize_hook_payload` (`tests/integration/_abstraction_adequacy_helpers.py`). Replacing this is the AC1/D2 D1 path.
- **Hook payload + journal coupling** — `src/sdlc/contracts/hook_payload.py` (`HookPayload`, frozen Pydantic, schema_version=1, ADR-024 snapshotted). The conformance harness asserts `HookPayload` sequence byte-stability via the existing `expected_hook_payloads.json` golden. The hook chain's emission order is the testable invariant.
- **State projection** — `src/sdlc/state/projection.py:project_from_journal` (pure function — no I/O). Journal entries → `State` (pydantic) → `model_dump(mode="json")` → atomic-write JSON bytes. ADR-029 §1 explicitly leaves `mock` in journal **payload** but not in projected state — AC4 is the verification that this design intent is actually realised.
- **`agent_runs.jsonl` telemetry** — `src/sdlc/telemetry/runs.py` (`_AgentRunLine.mock` per ADR-029 §4 #4). This file is NOT part of the conformance harness's golden assertions (state.json + hook_payloads only). The dispatcher writes it via `record_agent_run(...)`; both runtimes route through the same dispatcher path so `agent_runs.jsonl` will differ only in the `mock` boolean — out of scope for this story's assertions but a useful debug artefact when a divergence surfaces.
- **Async-strategy invariant** — both `MockAIRuntime.dispatch` and `ClaudeAIRuntime.dispatch` are `async def`. The harness uses one `asyncio.run(_dispatch_twice(rt))` per parametrised run (`test_abstraction_adequacy.py:105-114`) to avoid loop-teardown DeprecationWarning churn under `pyproject filterwarnings=["error"]`. Do NOT break this — the wrapper exists for a measured reason.

### Module boundary guardrail (READ — primary cause of RED-checkpoint failures)

`scripts/module_boundary_table.py`: `tests/integration/` imports the public API (`sdlc.runtime`, `sdlc.hooks`, `sdlc.state.projection`, `sdlc.journal`). Do not reach into private modules from the integration test — if a private helper is needed, expose it from `tests/integration/_abstraction_adequacy_helpers.py` (the existing private-test-helpers module — already-in-package; not subject to src/ module boundary rules).

**Do not import `sdlc.dispatcher.*` or `sdlc.cli.*` into the conformance test** — the harness exercises the runtime + projection layer, not the dispatcher. The dispatcher is exercised end-to-end elsewhere (Tier-2 e2e in `tests/e2e/pipeline/`). Mixing layers here couples conformance to dispatcher refactors.

### Project Structure Notes

- **Modified (the bulk of the work):**
  - `tests/integration/test_abstraction_adequacy.py` — `_RUNTIME_FACTORIES` extension, hook-synth replacement, cross-run assertion wiring, inline-comment cleanup of the resolved deferred-substrate notes
  - `tests/integration/_abstraction_adequacy_helpers.py` — `_build_claude_stub_for_fixture(...)`, `_format_diff(...)`, possibly a `_capture_actual_bytes` registration helper
  - `tests/fixtures/mock_responses/abstraction-adequacy.yaml` — leading comment block (AC3 extensibility procedure)
  - `tests/fixtures/abstraction_adequacy/expected_hook_payloads.json` — regenerated via `_REGENERATE_GOLDENS=True` after the hook-chain replacement (AC1/D2 D1)
  - `tests/fixtures/abstraction_adequacy/expected_state.json` — regenerated alongside the hook-payload golden ONLY if the projection neutralisation lands in `state/projection.py` (AC4/D1); otherwise byte-stable
- **New (small):**
  - `tests/integration/test_abstraction_adequacy_anti_tautology.py` — AC5 stub-divergence receipt (or inline in the conformance test; pick one and stay)
  - `tests/unit/state/test_projection.py` — AC4 projection-neutrality unit test (or extend the existing projection test file if one is closer in scope; verify before creating)
- **Possibly modified (AC4/D1 outcome):**
  - `src/sdlc/state/projection.py` — only if the AC4 unit test goes RED. If the projection already strips `mock`, do not touch it; document the discovery in the unit test docstring.
- **Layer 2 sibling coordination:** **2B.6 (`tests/security/test_subprocess_allowlist.py`)** is the other Layer 2 story and is the **subprocess allow-list gate**. 2B.6 whitelists `runtime/claude.py` (claude) for `subprocess.Popen`; 2B.3 does NOT add new `subprocess.*` callsites in `src/` (the stub generation happens in `tests/`, not `src/`). **No file conflict with 2B.6**; both stories merge independently.
- **Worktree:** `epic-2b/2b-3-conformance` (owners: Charlie + Dana, DAG §5). Per CONTRIBUTING §3 — one branch, linear FF-merge to `main`; rebase if 2B.6 merges first (no expected conflict).
- **Snapshot count:** no contract touched. `scripts/freeze_wireformat_snapshots.py --check` MUST stay green; ADR-024 snapshot count unchanged.

### Testing standards summary

- TDD-first (CONTRIBUTING §2): tests-first commit ordering visible in `git log --reverse` for the parametrised `runtime` fixture extension and the AC2/D2 cross-run assertion (both are the public test-surface logic). The stub-derivation helper is implementation detail and may be co-committed with its tests.
- Anti-tautology (ADR-026 §1): AC5 mandates **two** receipts — stub-divergence and projection-neutrality. Without these, the test is a guaranteed pass (both runtimes echoing the same fixture would pass even if the byte-equality check were a no-op).
- Test org (`architecture.md:682-701`): `tests/integration/test_abstraction_adequacy.py` exists; `tests/unit/state/test_projection.py` mirrors `src/sdlc/state/projection.py`; `tests/integration/_abstraction_adequacy_helpers.py` is the private helper module convention.
- POSIX-only invariant: the existing test carries `pytest.mark.skipif(sys.platform == "win32", ...)` at the module level — preserve it. `ClaudeAIRuntime` itself is POSIX-only-ish (subprocess + signals), and `journal.append_sync` + `state.write_state_atomic_sync` are POSIX-only.
- Determinism: the existing `_REGENERATE_GOLDENS` ceremony is the canonical golden-regen workflow — extend it (not replace it) for the new hook-chain emission order if AC1/D2 D1 lands.
- Quality gate (CONTRIBUTING §1): `ruff format` + `ruff check` + `mypy --strict` + `pytest` + coverage ≥87 + `pre-commit run --all-files` + `mkdocs --strict` + wire-format snapshots.
- `mypy --strict` on stub-generation code: subprocess + Path types must be clean; no bare `type: ignore`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-2B.3] — AC source (lines 1507-1529)
- [Source: docs/sprints/epic-2b-dag.md] — §3 Layer 2, §4 critical path (`2B.1→2B.3→2B.10→2B.11`), §5 worktree (owners Charlie + Dana), §7 Risk row 3 (golden-file flakiness must not stall 2B.8/9/10)
- [Source: tests/integration/test_abstraction_adequacy.py] — the existing harness; `_RUNTIME_FACTORIES` at lines 75-78, deferred-substrate notes at lines 9-16/128-129/144-146, regen ceremony at lines 221-228
- [Source: tests/integration/_abstraction_adequacy_helpers.py] — private helper module; `_synthesize_hook_payload` lives here today
- [Source: tests/fixtures/mock_responses/abstraction-adequacy.yaml] — the seed fixture; both runtimes derive their dispatch result from this (per AC1/D1)
- [Source: tests/fixtures/abstraction_adequacy/expected_hook_payloads.json + expected_state.json] — the existing goldens
- [Source: src/sdlc/runtime/abc.py] — `AIRuntime` ABC + `AgentResult.mock` (lines 33, 36-53)
- [Source: src/sdlc/runtime/claude.py] — `ClaudeAIRuntime`, `_parse_claude_stdout` envelope shape (lines 49-50, 183-201)
- [Source: src/sdlc/runtime/mock.py] — `MockAIRuntime` fixture lookup contract (lines 231-278)
- [Source: src/sdlc/hooks/runner.py] — `run_hook_chain` (Story 2A.4; AC1/D2 D1 target)
- [Source: src/sdlc/state/projection.py] — `project_from_journal` (AC4 target if projection includes `mock`)
- [Source: src/sdlc/contracts/hook_payload.py] — `HookPayload` schema (ADR-024 snapshotted, schema_version=1)
- [Source: _bmad-output/implementation-artifacts/2b-1-claudeairuntime-implementation-subprocess-management.md] — `done`; stub-claude pattern, `AgentResult.mock` rationale, ADR-029 fixes
- [Source: docs/decisions/ADR-029-mock-runtime-envelope-semantics.md] — `mock` field, default-flip, 4 collateral fixes; AC4 enforces §1 projection-vs-payload separation
- [Source: docs/decisions/ADR-024.md] — frozen-contract mutation taxonomy; this story makes NO contract edits (no snapshot regen)
- [Source: docs/decisions/ADR-026.md §1] — anti-tautology receipt requirement (AC5)
- [Source: CONTRIBUTING.md] — §1 quality gate, §2 TDD-first, §3 worktree workflow
- [Source: _bmad-output/implementation-artifacts/2b-5-automated-boundary-line-presence-test.md] — sibling Layer-1 (`done`); pattern reference for ADR-026 §1 anti-tautology receipt structure (its AC4 fixture-driven RED-coverage approach is the model for AC5 Receipt #1 here)

## Dev Agent Record

### Agent Model Used

Composer (Cursor)

### Debug Log References

- ClaudeAIRuntime v1 returns empty tool_calls; hook payloads use seed-stable targets when tool_calls absent.
- Golden hook payloads regenerated: hook_name pre_write + target_kind write_intent (real chain path).

### Completion Notes List

- Extended `_RUNTIME_FACTORIES` with `_claude_factory` and YAML-derived stub on PATH (AC1/D1).
- Replaced `_synthesize_hook_payload` with `run_pre_write_hooks_for_dispatches` + `build_conformance_hook_chain` (AC1/D2 D1).
- Added `_format_diff`, per-runtime golden diffs, and `pytest_sessionfinish` cross-runtime assert (AC2).
- Documented specialist extension checklist in seed YAML + unit guard (AC3).
- Stripped `mock` from state projection; unit test in `test_state_projection.py` (AC4).
- Anti-tautology: `test_abstraction_adequacy_anti_tautology.py` + projection test (AC5).

### File List

- tests/integration/test_abstraction_adequacy.py
- tests/integration/_abstraction_adequacy_helpers.py
- tests/integration/_abstraction_adequacy_capture.py
- tests/integration/conftest.py
- tests/integration/test_abstraction_adequacy_anti_tautology.py
- tests/unit/integration/test_abstraction_adequacy_helpers.py
- tests/unit/state/test_state_projection.py
- tests/fixtures/mock_responses/abstraction-adequacy.yaml
- tests/fixtures/abstraction_adequacy/expected_hook_payloads.json
- src/sdlc/state/projection.py

### Change Log

- 2026-05-28: Story 2B.3 — Mock+Claude conformance harness; AC1/D1 stub from YAML; AC1/D2 D1 real pre-write hook chain; AC2 unified diffs + session cross-runtime assert; AC4 projection strips `mock`.

## Review Findings

> **2026-05-28 bmad-code-review** — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor); 102 raw findings → 47 unique after dedupe → 7 decision-needed + 29 patch + 11 defer + 14 dismissed. AC coverage: AC1 partial / AC2 partial / AC3 met / AC4 partial / AC5 partial.

### Decisions (resolved 2026-05-28)

- [x] [Review][Decision] **D1 — Cross-runtime gate hook surface** → **resolved (b) Final ordered test** — refactor cross-run check to a regular test ordered after both parametrised runs via `pytest_collection_modifyitems`; eliminates INTERNALERROR fragility; spec AC2/D2 explicitly allows. Becomes patch P30.
- [x] [Review][Decision] **D2 — pytest-xdist incompatibility** → **resolved (b) Runtime guard fail-loud** — detect xdist worker context (`request.config.workerinput is not None`) and `pytest.fail(...)` if conformance runs under parallel mode. Becomes patch P31.
- [x] [Review][Decision] **D3 — Empty `tool_calls` fallback tautology** → **resolved (b) v1 fallback + debt** — keep fallback for v1; open EPIC-2B-DEBT-CLAUDE-TOOL-CALLS in deferred-work.md (becomes CR2B3-W12); add explicit `# COINCIDENCE-COUPLING: ... see CR2B3-W12` comment at fallback site. Becomes patch P32 + defer W12.
- [x] [Review][Decision] **D4 — Hook chain emission vs synthesised payload** → **resolved (c) Accept + open debt** — document v1 deviation; rename `_hook_payload_from_agent_result` → `_build_pre_chain_input_payload` to clarify the helper synthesises the INPUT to `run_hook_chain`, not its emission; assert chain's `decision == "allow"` is the load-bearing invariant; open EPIC-2B-DEBT-CHAIN-EMISSION-CAPTURE (CR2B3-W13). Becomes patch P33 + defer W13.
- [x] [Review][Decision] **D5 — `_build_journal_entry` doesn't emit `mock`** → **resolved (b) Verify production + mirror** — verify dispatcher's REAL journal-write path emits `payload.mock`; if so, mirror in `_build_journal_entry` so integration exercises the strip; if not, escalate (AC4 contract is theatrical) and open debt. Becomes patch P34 (conditional on verification result).
- [x] [Review][Decision] **D6 — Projection strip key strategy** → **resolved (a) `_AUDIT_ONLY_KEYS` constant** — introduce `_AUDIT_ONLY_KEYS: Final[frozenset[str]] = frozenset({"mock"})` in `src/sdlc/state/projection.py`; filter via membership; update ADR-029 to document the registry as the authoritative key list. Becomes patch P35.
- [x] [Review][Decision] **D7 — AC5 Receipt #1 decoupled from gate surface** → **resolved (a) pytester sub-session** — refactor `test_divergent_claude_stub_fails_cross_runtime_identity` to use pytest `pytester` fixture; run a sub-pytest session with the divergent stub; assert sub-session exit-code != 0 ⇒ proves the wired final-ordered-test surface (D1=b) is load-bearing. Becomes patch P36.

### Patches — `pytest_sessionfinish` raises `AssertionError` ⇒ pytest reports INTERNALERROR (fragile / version-dependent), not a regular test failure. Spec AC2/D2 explicitly allows EITHER `pytest_sessionfinish` OR a final test ordered after both parametrised runs. **Options:** (a) keep sessionfinish + document CI exit-code dependency; (b) refactor to final ordered test via `pytest_collection_modifyitems`; (c) synthetic test item via `pytest_collection_finish`. **Recommended: (b).** Sources: Blind#41, Acc#2.
- [ ] [Review][Decision] **D2 — pytest-xdist incompatibility of `_CAPTURED` module global** — Each xdist worker has its own module copy ⇒ `mock_factory` (worker A) and `claude_factory` (worker B) never meet in the same dict; gate silently no-ops. **Options:** (a) document single-worker constraint via pytest marker + CONTRIBUTING note; (b) runtime guard that fails on detected xdist parallel context; (c) persist captures to a temp file shared across workers. **Recommended: (b).** Sources: Edge#1, Blind#13.
- [ ] [Review][Decision] **D3 — Empty `tool_calls` fallback is tautological** — `ClaudeAIRuntime._parse_claude_stdout` always returns `tool_calls=()`; `_hook_payload_from_agent_result` routes around with `_SEED_TARGET_PATH` + `_ZERO_HASH` hard-coded. Mock-vs-Claude HookPayload identity becomes a coincidence on the current seed, not a measurement. **Options:** (a) extend `runtime/claude.py:_parse_claude_stdout` to surface `tool_calls` from JSON envelope, drop fallback; (b) v1 accept fallback + open EPIC-2B-DEBT-CLAUDE-TOOL-CALLS + add explicit "coincidence-coupling" comment; (c) mark hook-payload divergence detection as `xfail` until 2B.10. **Recommended: (b)** if `runtime/claude.py` is out-of-scope; else (a). Sources: Edge#20, Acc#9, Blind#29, Edge#31.
- [ ] [Review][Decision] **D4 — Hook-chain emission vs synthesised payload** — `_synthesize_hook_payload` was renamed `_hook_payload_from_agent_result` but synth logic kept. `run_hook_chain` is invoked for `decision == "allow"` side-effect only; asserted goldens are NOT what the chain emits, contradicting AC1/D2 D1 ("the dispatched chain emits HookPayloads — capture the emission order"). **Options:** (a) extend `hooks.runner` to expose emissions, capture them in the test; (b) document v1 deviation, assert decision invariant only, rename helper to clarify intent; (c) open EPIC-2B-DEBT-CHAIN-EMISSION-CAPTURE for 2B.10 audit. **Recommended: (c).** Sources: Acc#6, Acc#7.
- [ ] [Review][Decision] **D5 — `_build_journal_entry` doesn't carry `mock` → AC4 strip is dead in integration** — Production journal payload (per current `_build_journal_entry`) is `{output_text, tokens_in, tokens_out}` only. AC4 unit test injects `mock` directly into a synthetic payload, proving the strip works *in isolation*. Integration test exercises projection-output-equivalence but never the strip. **Options:** (a) update `_build_journal_entry` to emit `mock=result.mock` so integration exercises the strip; (b) verify dispatcher's REAL journal-write path emits `payload.mock` and mirror in the helper; (c) document that AC4 enforcement lives at projection-layer only. **Recommended: (b)** — verify production first, then mirror. Sources: Edge#25.
- [ ] [Review][Decision] **D6 — Projection strip key strategy** — Spec AC4/D1 says "preferred: never depend on mock in the first place". Implementation chose deny-list of literal `"mock"`. **Options:** (a) introduce `_AUDIT_ONLY_KEYS = frozenset({"mock"})` constant in `projection.py`; (b) switch to allow-list via typed `EpicPayloadProjection(BaseModel)` (larger contract change); (c) keep literal + open EPIC-2B-DEBT-AUDIT-KEY-REGISTRY. **Recommended: (a).** Sources: Blind#14, Edge#22, Acc#19.
- [ ] [Review][Decision] **D7 — AC5 Receipt #1 is decoupled from the surface it claims to prove** — `test_divergent_claude_stub_fails_cross_runtime_identity` reimplements `assert mock_state == claude_state` in-process; never invokes `pytest_sessionfinish` hook → cannot prove the actual session-finalize wiring is load-bearing. **Options:** (a) use `pytester` fixture to run a sub-pytest session with divergent stub, assert non-zero exit-code; (b) accept current shape — in-process AssertionError captures the *logic*; (c) defer via EPIC-2B-DEBT-PYTESTER-RECEIPTS. **Recommended: (a)** — spec AC5 Receipt #1 explicitly says "make the cross-run assertion (AC2/D2) RED". Sources: Acc#3.

### Patches

- [ ] [Review][Patch] **P1 — `pytest_sessionfinish` silent-return when only one factory captured** [tests/integration/conftest.py:17-18] — replace `return` with `pytest.fail(...)` when partial captures present (only allow clean return on fully empty captures + `exitstatus == 0`).
- [ ] [Review][Patch] **P2 — `pytest_sessionfinish` swallows exitstatus** [tests/integration/conftest.py:12-13] — early-return only when `exitstatus == 0`; on non-zero, skip cross-runtime check to avoid layered confusion on top of primary failure.
- [ ] [Review][Patch] **P3 — Hardcoded `"mock_factory"`/`"claude_factory"` keys** [tests/integration/conftest.py:18-25, tests/integration/test_abstraction_adequacy.py:119] — derive expected key set from `_RUNTIME_FACTORIES` (e.g., `{f.__name__.lstrip("_") for f in _RUNTIME_FACTORIES}`); rename-resistant.
- [ ] [Review][Patch] **P4 — `record_runtime_bytes` happens after golden assertions** [tests/integration/test_abstraction_adequacy.py:189-196] — wrap goldens in `try/finally` so capture always fires before any assertion (covers golden drift + `_REGENERATE_GOLDENS` mode bypass).
- [ ] [Review][Patch] **P5 — `request.node.callspec` fallback to `"runtime"`** [tests/integration/test_abstraction_adequacy.py:119] — `assert request.node.callspec is not None`; drop the fallback that masks misconfiguration.
- [ ] [Review][Patch] **P6 — AC4 unit test asserts byte-equality only** [tests/unit/state/test_state_projection.py:367-384] — add positive assertion `assert "mock" not in canonical_true.decode()` to prove the strip, not coincidence.
- [ ] [Review][Patch] **P7 — `_format_diff` produces duplicate `--- expected` headers** [tests/integration/_abstraction_adequacy_helpers.py:93-103] — drop manual header OR pass `fromfile=""`/`tofile=""` to `difflib.unified_diff`.
- [ ] [Review][Patch] **P8 — Anti-tautology assertion always passes due to P7** [tests/integration/test_abstraction_adequacy_anti_tautology.py:144] — tighten from `"--- expected" in msg_state or "+++ actual" in msg_state` to `any(line.startswith("+") and "X" in line for line in msg_state.splitlines())`.
- [ ] [Review][Patch] **P9 — `_build_claude_stub_with_mutated_output` mutates ALL rows** [tests/integration/_abstraction_adequacy_helpers.py:252-256] — parameterize on `target_key` or limit mutation to a single `(workflow_step, prompt_hash)` row; AC3 extensibility broken otherwise.
- [ ] [Review][Patch] **P10 — `mock_hp == claude_hp` has no diagnostic** [tests/integration/test_abstraction_adequacy_anti_tautology.py:135-136] — add `_format_diff(...)` message for failure debugging.
- [ ] [Review][Patch] **P11 — Stub `#!/usr/bin/env python3` may pick system python lacking yaml** [tests/integration/_abstraction_adequacy_helpers.py:240-243] — emit `f"#!{sys.executable}"` shebang at stub-generation time using the test-runner's interpreter.
- [ ] [Review][Patch] **P12 — Stub `sys.stdin.read()` locale-dependent** [tests/integration/_abstraction_adequacy_helpers.py:209-210] — emit `sys.stdin.buffer.read().decode("utf-8")` so non-ASCII seed prompts don't silently break the hash.
- [ ] [Review][Patch] **P13 — Stub crashes opaquely on missing token keys** [tests/integration/_abstraction_adequacy_helpers.py:222-223] — wrap stub body in try/except; emit `is_error=True` JSON envelope with descriptive message; CI diagnostic actionable.
- [ ] [Review][Patch] **P14 — Stub `print(json.dumps(envelope))` adds trailing newline** [tests/integration/_abstraction_adequacy_helpers.py:226] — use `sys.stdout.write(json.dumps(envelope))` for byte-stable stdout.
- [ ] [Review][Patch] **P15 — `_state_hash` not pinned mock-invariant** [tests/unit/state/test_state_projection.py] — add a one-line unit test asserting `_state_hash` on a `State` constructed with `{"mock": True}` in an epic raises or strips; cheap regression guard for the projection-vs-hash coupling.
- [ ] [Review][Patch] **P16 — Projection `dict()` comprehension preserves journal-write key order** [src/sdlc/state/projection.py:95] — wrap in `dict(sorted({...}.items()))` for canonical key order; belt-and-braces vs unspecified writer order.
- [ ] [Review][Patch] **P17 — `sprint-status.yaml` pre-flipped 2B.3 to "review → done" before review concluded** [_bmad-output/implementation-artifacts/sprint-status.yaml] — revert the development_status entry to `review`; flip only after code-review concludes (per CONTRIBUTING §4 chunked review ordering).
- [ ] [Review][Patch] **P18 — ADR-029 §1 v1 strip mechanism not separately noted** [docs/decisions/ADR-029-*.md] — append a one-line note documenting v1 chose filter-on-projection over structural independence; opens migration path for D6.
- [ ] [Review][Patch] **P19 — AC1 invariant comment in future tense** [tests/integration/test_abstraction_adequacy.py:69-72] — past tense ("Story 2B.3 extended ...") + standalone "DO NOT add a third factory in v1" line.
- [ ] [Review][Patch] **P20 — Spec line 77 file-path mismatch** [_bmad-output/implementation-artifacts/2b-3-behavioral-conformance-mock-vs-claude.md:77] — fix `tests/unit/state/test_projection.py` → `tests/unit/state/test_state_projection.py`.
- [ ] [Review][Patch] **P21 — AC3 extensibility marker is a magic-string tautology** [tests/integration/_abstraction_adequacy_helpers.py:309-313, tests/unit/integration/test_abstraction_adequacy_helpers.py:127-134] — strengthen to assert presence of `"1."`, `"2."`, `"3."` numbered prefixes AND a reference to `_REGENERATE_GOLDENS`.
- [ ] [Review][Patch] **P22 — Em-dash in marker string vulnerable to editor normalization** [tests/fixtures/mock_responses/abstraction-adequacy.yaml:61, _abstraction_adequacy_helpers.py:309-313] — use ASCII `--` instead of `—`.
- [ ] [Review][Patch] **P23 — `_SEED_TARGET_PATH` duplicated as string literal in unit test** [tests/unit/integration/test_abstraction_adequacy_helpers.py:661] — import the constant from helpers; eliminate drift opportunity.
- [ ] [Review][Patch] **P24 — `_dispatch_twice` duplicated locally in anti-tautology test** [tests/integration/test_abstraction_adequacy_anti_tautology.py:42-46] — import shared helper from `test_abstraction_adequacy.py` or extract to `_abstraction_adequacy_helpers.py`.
- [ ] [Review][Patch] **P25 — `_dispatch_twice` rationale comment deleted** [tests/integration/test_abstraction_adequacy.py:104] — restore the "two sequential `asyncio.run` ... loop teardown DeprecationWarning" rationale; load-bearing context per spec line 132.
- [ ] [Review][Patch] **P26 — `record_runtime_bytes` silently overwrites duplicate factory_id** [tests/integration/_abstraction_adequacy_capture.py:9-10] — `assert factory_id not in _CAPTURED`; fail-loud on retry/double-write.
- [ ] [Review][Patch] **P27 — Anti-tautology test should defensively clear `_CAPTURED` in teardown** [tests/integration/test_abstraction_adequacy_anti_tautology.py] — add `addfinalizer(_CAPTURED.clear)` so divergent captures cannot leak to `pytest_sessionfinish` and falsely fail the suite.
- [ ] [Review][Patch] **P28 — Redundant `target_dir.mkdir` calls** [tests/integration/_abstraction_adequacy_helpers.py:237 and ~285] — drop the duplicate.
- [ ] [Review][Patch] **P30 — Refactor cross-run check to final ordered test (from D1=b)** [tests/integration/conftest.py, tests/integration/test_abstraction_adequacy.py] — replace `pytest_sessionfinish` hook with a regular test `test_cross_runtime_byte_identity` ordered after `test_abstraction_adequacy_pipeline[*]` via `pytest_collection_modifyitems`; failures surface as test failures, not INTERNALERROR.
- [ ] [Review][Patch] **P31 — xdist worker fail-loud guard (from D2=b)** [tests/integration/conftest.py] — detect `request.config.workerinput is not None` in a session-scoped autouse fixture (or via `pytest_configure`); `pytest.fail("conformance harness incompatible with pytest-xdist; run on single worker")` when running parallel.
- [ ] [Review][Patch] **P32 — COINCIDENCE-COUPLING comment + open CR2B3-W12 (from D3=b)** [tests/integration/_abstraction_adequacy_helpers.py:152-156, tests/fixtures/mock_responses/abstraction-adequacy.yaml] — at the `_ZERO_HASH`/`_SEED_TARGET_PATH` fallback site, add explicit comment block: `# COINCIDENCE-COUPLING (CR2B3-W12): Mock-vs-Claude hook-payload identity holds only because the seed YAML's tool_call.target == _SEED_TARGET_PATH AND tool_call.content_hash == _ZERO_HASH. Any seed edit changing these decouples the runtimes silently. To-be-resolved via Claude parser surfacing tool_calls — see EPIC-2B-DEBT-CLAUDE-TOOL-CALLS.` Also add invariant unit test asserting the seed YAML's `tool_calls[0].args.target == _SEED_TARGET_PATH` and `content_hash == _ZERO_HASH` — turns silent decoupling into a RED test on any future seed edit.
- [ ] [Review][Patch] **P33 — Rename `_hook_payload_from_agent_result` → `_build_pre_chain_input_payload` (from D4=c)** [tests/integration/_abstraction_adequacy_helpers.py] — clarify helper synthesises the INPUT to `run_hook_chain`, not its emission; add docstring noting AC1/D2 D1 wording is honoured via the `decision == "allow"` invariant, not via chain emission capture; open CR2B3-W13.
- [ ] [Review][Patch] **P34 — Verify dispatcher emits `payload.mock` + mirror in test helper (from D5=b)** [src/sdlc/dispatcher/*, tests/integration/_abstraction_adequacy_helpers.py:283-297] — read dispatcher journal-write path; if production already emits `payload.mock`, update `_build_journal_entry` to mirror (add `"mock": result.mock` to payload dict); the strip then exercises in integration. If production does NOT emit `payload.mock`, open EPIC-2B-DEBT-DISPATCHER-MOCK-EMIT and treat AC4 as projection-layer-only (escalate to user before merge).
- [ ] [Review][Patch] **P35 — `_AUDIT_ONLY_KEYS` constant (from D6=a)** [src/sdlc/state/projection.py] — introduce `_AUDIT_ONLY_KEYS: Final[frozenset[str]] = frozenset({"mock"})`; filter via `if k not in _AUDIT_ONLY_KEYS`; export from module for ADR-029 registry reference; update inline comment to point at the constant + ADR-029 §1.
- [ ] [Review][Patch] **P36 — pytester sub-session receipt for AC5 #1 (from D7=a)** [tests/integration/test_abstraction_adequacy_anti_tautology.py] — refactor receipt to use `pytester` fixture; write a tiny `test_xxx.py` into the sub-session that uses the divergent-output stub; run via `pytester.runpytest()`; assert non-zero exit-code AND the final-ordered-test name appears in failure list ⇒ proves the wired surface (D1=b) is load-bearing.
- [ ] [Review][Patch] **P29 — `pytest_sessionfinish` swallow no-capture as success** [tests/integration/conftest.py:14-15] — when `not captured` AND any conformance test ran (per session items list), fail loud; only allow silent return when the entire integration suite was skipped (e.g., win32 platform skip).

### Deferred

- [x] [Review][Defer] **W1 — EPIC-2B-DEBT-PHASE-GATE-DISCOVERY-COUPLING** [tests/integration/_abstraction_adequacy_helpers.py:165-171] — deferred, pre-existing: `bound_phase_gate.__is_phase_gate__ = True` magic attribute coupling to production hook discovery is undocumented; add unit test pinning the attribute contract.
- [x] [Review][Defer] **W2 — EPIC-2B-DEBT-PRODUCTION-HOOK-CHAIN-PINNING** [tests/integration/_abstraction_adequacy_helpers.py:161-171] — deferred, pre-existing: conformance chain `(naming_validator, bound_phase_gate)` mirrors dispatcher wiring without importing it; production wiring not pinned by any test.
- [x] [Review][Defer] **W3 — EPIC-2B-DEBT-STUB-NOEXEC-FALLBACK** [tests/integration/_abstraction_adequacy_helpers.py:230, 313] — deferred, pre-existing: `chmod 0o755` + `Popen` fails on noexec `/tmp`; fallback to `subprocess.Popen([sys.executable, str(stub_path), ...])`.
- [x] [Review][Defer] **W4 — EPIC-2B-DEBT-STUB-ENV-SCRUB** [tests/integration/_abstraction_adequacy_helpers.py:300-313] — deferred, pre-existing: `install_claude_stub_on_path` doesn't scrub `ANTHROPIC_API_KEY`/`CLAUDE_BIN`; if stub yaml-import fails, dispatch may hit real network.
- [x] [Review][Defer] **W5 — EPIC-2B-DEBT-STUB-EXTRACT-TO-FILE** [tests/integration/_abstraction_adequacy_helpers.py:240-285] — deferred, pre-existing: `textwrap.dedent` + f-string + `{{`/`}}` escapes for stub-generation is double-escape-bait; refactor to standalone `tests/integration/_stubs/claude_stub_template.py` and copy via `shutil.copy2`.
- [x] [Review][Defer] **W6 — EPIC-2B-DEBT-STUB-PROMPT-CONTRACT** [tests/integration/_abstraction_adequacy_helpers.py:209-210] — deferred, pre-existing: stub assumes `ClaudeAIRuntime.dispatch` writes `_SEED_PROMPT` to stdin verbatim with no decoration; document the stdin protocol contract as an invariant of `runtime/claude.py`.
- [x] [Review][Defer] **W7 — EPIC-2B-DEBT-HOOK-NAME-RENAME-AUDIT** [tests/fixtures/abstraction_adequacy/expected_hook_payloads.json:55] — deferred, pre-existing: golden changed `target_kind: "epic" → "write_intent"` and `hook_name: "abstraction-adequacy-synth" → "pre_write"`; verify no downstream taxonomy (ADR-028 §3) references the old strings as orphans.
- [x] [Review][Defer] **W8 — EPIC-2B-DEBT-PRETTY-PRINT-DIFF** [tests/integration/_abstraction_adequacy_helpers.py:93-103] — deferred, pre-existing: `_format_diff` for single-line JSON state shows unreadable mega-line diffs; pretty-print via `json.dumps(..., indent=2)` round-trip before diffing for human readability.
- [x] [Review][Defer] **W9 — EPIC-2B-DEBT-RECURSIVE-CANONICAL-JSON** [tests/integration/test_abstraction_adequacy.py:166-174] — deferred, pre-existing: `json.dumps(..., sort_keys=True)` sorts only top-level; nested dicts retain insertion order; HookPayload v1 has no nested dicts but future fields could break byte-identity.
- [x] [Review][Defer] **W10 — TDD-first commit ordering enforcement at merge time** [git history] — deferred, audit-only: uncommitted state cannot be audited; reviewer must require split commits — (1) RED with parametrised fixture + AC2/D2 cross-run assertion only, (2) GREEN with stub-derivation and helper — before merge per CONTRIBUTING §2 + ADR-026 §2 squash-flow.
- [x] [Review][Defer] **W11 — EPIC-2B-DEBT-PROJECTION-MOCK-STRIP-NARROW** [src/sdlc/state/projection.py:91-96] — deferred, pre-existing: strip applies to every `state_mutation` entry regardless of source; if a future story emits `mock` as legitimate domain field, it gets silently dropped; document discriminator via comment.

### Dismissed (14, with rationale)

- **E8/E9** — Stub `Path(repr())` and Windows backslash concerns: POSIX-only via `skipif(win32)`; `repr()` of `Path.__str__` is safe Python literal.
- **H7** — `_signoff_reader` defensive error wrapping: not impacting; current behavior is acceptable.
- **H8/Edge#32** — `compute_state` once-per-process WARN log: cross-cutting; not in 2B.3 scope.
- **H9/Edge#29** — Cygwin not covered by `skipif`: Cygwin is not a supported platform.
- **H10/Edge#18/Edge#33** — bindir leak / PATH evaluation timing: tmp_path is GC'd per pytest; no concurrent monkeypatch hazard.
- **H12/Edge#8** — Resolve-equality dead branch / TOCTOU on fixture mutation: defensive snapshot semantics are correct.
- **H19/Edge#12** — Mutate-while-iterate landmine: current code iterates `raw`, mutates `mutated` — correct; refactor risk is a separate concern.
- **Edge#27** — `_claude_factory` ignores `fixtures_dir` argument: explicit decoupling; `install_claude_stub_on_path` has its own path discovery.
- **Edge#22 broader-mock-keys risk**: covered by **D6** (decision-needed), so not separately dismissed; D6 addresses the registry vs literal question.
