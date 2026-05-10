# Story 2A.3: Dispatcher — Primary + Parallel + Synthesizer + Retry Policy

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an orchestrator dispatching agents per workflow step,
I want `dispatcher.dispatch(step)` executing one primary specialist plus optional parallel specialists, optionally consolidated by a `synthesizer`, with retry-on-failure (1 attempt + 2 retries, exponential backoff 1s/4s),
So that the dispatch contract is uniform and reliable across every workflow (FR25, FR26, FR27, FR29, NFR-REL-4, Decision A2).

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1039-1063`. Per ADR-026 §1, the dispatcher's public surface (`dispatch`, `dispatch_panel`, retry policy) requires TDD-first commit ordering. The `agent_runs.jsonl` placeholder is a **NEW internal artifact in 2A** (NOT a wire-format contract — Epic 2B finalizes the schema; see AC9 below for explicit non-snapshot policy).

### AC1 — `dispatch(step, *, runtime, registry, journal_path, agent_runs_path) -> DispatchResult` (primary-only path, FR25 + NFR-OBS-2)

**Given** a `WorkflowSpec` step where `parallel_agents == ()` and `synthesizer_agent is None`
**When** the dev calls `dispatcher.core.dispatch(step, runtime=..., registry=..., journal_path=..., agent_runs_path=...)`
**Then** the function:
  1. Resolves the primary specialist via `registry.get(step.primary_agent)` — propagates `SpecialistError` on miss (do NOT wrap)
  2. Constructs the dispatch context dict with `{workflow_step: step.name, agent_name: <primary>, target_kind: "primary"}` — schema is intentionally open per `runtime.abc.AIRuntime.dispatch` v1 surface
  3. Awaits `runtime.dispatch(prompt, context) -> AgentResult` (single attempt path before retry wrapping in AC4)
  4. Writes the result's `output_text` to the specialist's declared output path (resolved per AC8 — write-target derivation)
  5. Appends an `agent_runs.jsonl` line via `telemetry.runs.record_agent_run(...)` containing `{schema_version: 1, run_id: <uuid4>, ts: <RFC 3339 UTC ms>, workflow_step, specialist_name, target_kind: "primary", outcome: "success", attempts: 1, tokens_in, tokens_out, target_path, duration_ms}` (NFR-OBS-2 — full schema lock arrives in Epic 2B; see AC9)
  6. Returns `DispatchResult(specialist_name, target_path, agent_result, attempts=1, outcome="success")`
**And** every step transition that mutates state appends a `JournalEntry` with `kind="dispatch_attempt"` and `payload={"specialist": ..., "outcome": "success", "attempt": 1, "target_kind": "primary"}` via `sdlc.journal.writer.append` (do NOT roll a separate writer)
**And** the prompt construction shape is dependency-injected via the function parameter `prompt_builder: Callable[[Specialist, WorkflowSpec], str]` with a default of `dispatcher.core._default_prompt_builder` — keeps the prompt-engineering concern out of dispatch core (Story 2A.8 owns the real prompt shape)

### AC2 — `dispatch_panel(step, *, runtime, registry, journal_path, agent_runs_path) -> PanelResult` (primary + parallel + synthesizer, FR25 + FR26)

**Given** a `WorkflowSpec` step with `parallel_agents = ("technical-researcher", "devil-advocate")` and `synthesizer_agent = "synthesizer"`
**When** the dev calls `dispatcher.core.dispatch_panel(step, ...)`
**Then** the function:
  1. Resolves primary + every parallel specialist via `registry.get(...)` — propagates `SpecialistError` on first miss; the entire panel fails atomically (no partial dispatch)
  2. Constructs one coroutine per panel member (1 primary + N parallel) and awaits them via `concurrency.subprocess_pool.BoundedDispatcher.dispatch_many(coros)` initialized with `Semaphore(max_parallel_agents)` from `config.project` (default `max_parallel_agents=4` per project.yaml — load via `config.load_project_config(...).max_parallel_agents`)
  3. After the panel completes, IF `synthesizer_agent is not None`, dispatches the synthesizer with `context = {workflow_step, agent_name: <synth>, target_kind: "synthesizer", panel_outputs: {<member>: <output_text>, ...}}` — the synthesizer's `AgentResult.output_text` is the consolidated artifact (FR26)
  4. The synthesizer's output is written to `step.write_globs[step.primary_agent][0]` (the primary specialist's first declared write target — Decision: synthesizer overwrites primary's write target so downstream consumers see ONE artifact, not N+1; document in Change Log per D-decision protocol if dev disagrees)
  5. Each panel member's individual output is ALSO written to its own declared write target (preserves per-member auditability for `sdlc trace`)
  6. Returns `PanelResult(primary_result, parallel_results, synthesizer_result, write_targets, total_attempts, outcome)`
**And** if any panel member's dispatch raises (after retry exhaustion per AC4), the entire panel's outcome is `"failed"`; the synthesizer is NOT dispatched (no consolidation of incomplete input)
**And** every panel-member dispatch produces its own `agent_runs.jsonl` line (per AC1.5 schema; `target_kind` ∈ `{"primary", "parallel", "synthesizer"}`)
**And** the panel emits ONE journal entry per dispatch_attempt (`kind="dispatch_attempt"`); the synthesizer emits a SEPARATE journal entry with `payload={"target_kind": "synthesizer", "panel_size": N+1}`

### AC3 — Disjoint-writes static check enforcement at dispatch time (FR25, ties to Story 2A.1 AC7)

**Given** Story 2A.1 AC7's `static_check.disjoint_writes_check(spec) -> CheckResult` already validates that primary + parallel + synthesizer write_globs do not collide at workflow load time
**When** the dispatcher consumes a `WorkflowSpec` at runtime
**Then** the dispatcher does **NOT** re-run the static check (Story 2A.1's `WorkflowRegistry.load_workflow` already gates this — re-running is wasteful and creates a TOCTOU race window)
**And** the dispatcher trusts the loaded `WorkflowSpec` as a validated input (matches Decision D3 trust posture for v1)
**And** if a runtime collision IS detected during write (e.g., synthesizer overwrites primary in AC2.4 — that's intentional per the AC2.4 D-decision; non-intentional collisions would have been caught by 2A.1), the dispatcher raises `DispatchError("write target collision detected at dispatch time: <path>")` and the panel's outcome is `"failed"`
**And** the integration test `tests/integration/test_dispatch_disjoint_writes.py` asserts that a 2A.1-rejected spec NEVER reaches `dispatch()` (the registry refuses to load it)

### AC4 — Retry policy: 1 attempt + 2 retries, exponential backoff 1s/4s (FR27, NFR-REL-4)

**Given** a specialist dispatch where `runtime.dispatch(...)` raises `DispatchError` (or any subclass: `MockMissError`, future `ClaudeDispatchError`)
**When** the retry policy at `dispatcher.retry.with_retries(coro_factory, *, max_attempts=3, backoff_schedule=(1.0, 4.0))` wraps the dispatch
**Then** the function:
  1. Awaits `coro_factory()` once (attempt 1)
  2. On `DispatchError`, sleeps `backoff_schedule[0] = 1.0` second via `asyncio.sleep` (NOT `time.sleep` — must yield to the event loop so concurrent panel members continue)
  3. Awaits `coro_factory()` again (attempt 2)
  4. On `DispatchError`, sleeps `backoff_schedule[1] = 4.0` seconds via `asyncio.sleep`
  5. Awaits `coro_factory()` a final time (attempt 3 = the 2nd retry per FR27 wording "1 attempt + 2 retries" = 3 total invocations)
  6. On `DispatchError`, the function raises `DispatchError("dispatch failed after 3 attempts: <last_message>", details={"attempts": 3, "specialist": ..., "last_error": ...})` with `__cause__` set to the final exception (`raise … from`)
**And** `coro_factory` is called fresh on each attempt (NOT awaited multiple times — coroutines are single-shot in Python; reuse raises `RuntimeError`)
**And** the backoff schedule is dependency-injected (test reproducibility): `with_retries(coro_factory, sleep=asyncio.sleep, ...)` — production passes `asyncio.sleep`; tests pass a mock that records but does NOT sleep
**And** **only** `DispatchError` (and subclasses) trigger retry — `WorkflowError`, `SpecialistError`, `HookError`, `JournalError`, `StateError`, `SignoffError`, `ConfigError` are NOT retryable (they indicate operator-fixable misconfiguration; retrying just delays the obvious failure)
**And** non-`SdlcError` exceptions (`asyncio.CancelledError`, `KeyboardInterrupt`, generic `Exception`) propagate immediately WITHOUT retry — cancellation must be honored; surprise exceptions surface a real bug, not a transient failure
**And** every attempt (success or failure) appends ONE `JournalEntry` with `kind="dispatch_attempt"` and `payload={"specialist": ..., "outcome": "success"|"retry"|"failed", "attempt": <1|2|3>}` — three rows for a 3-fail run, one row for a 1st-attempt-success run

### AC5 — STOP-trigger placeholder on terminal failure (ties to FR21, full implementation Epic 4)

**Given** a panel member's dispatch exhausts all retries
**When** the dispatcher catches the final `DispatchError`
**Then** the dispatcher records a STOP-trigger placeholder by appending a `JournalEntry` with `kind="stop_trigger_raised"` and `payload={"trigger": "agent_failure_after_retries", "specialist": ..., "step": ..., "epic_4_placeholder": true}` — Epic 4 Story 4.6 will read these journal entries to compute the actual STOP banner state
**And** the dispatcher does NOT halt the calling code (engine/CLI) — it returns a `DispatchResult/PanelResult` with `outcome="failed"`; the caller decides whether to surface a STOP banner (Epic 4 concern)
**And** the placeholder is documented as "Epic 4 stub" in the dispatcher module docstring with a `# TODO(epic-4)` marker — debt-tracking lives at `_bmad-output/implementation-artifacts/deferred-work.md` under a NEW `EPIC-4-STOP-TRIGGER-WIRE` ticket created by this story

### AC6 — Module structure + LOC caps (Architecture §821-§824, §1067)

**Given** the architecture mandates `dispatcher/{core.py, retry.py, postconditions.py}` (Architecture §821-§824)
**When** the dev creates the dispatcher package
**Then** the file layout is:

```
src/sdlc/dispatcher/
├── __init__.py            # public re-exports: dispatch, dispatch_panel, with_retries,
│                          #   DispatchResult, PanelResult, DispatchOutcome
├── core.py                # dispatch + dispatch_panel + DispatchResult/PanelResult dataclasses
│                          # (≤ 350 LOC — primary + parallel + synth orchestration)
├── retry.py               # with_retries + backoff schedule + retryable predicate
│                          # (≤ 150 LOC — pure async control flow)
└── postconditions.py      # placeholder for postcondition validators (Story 2A.10/2A.12 owns;
                           #   2A.3 ships an empty stub + module docstring noting future scope)
```

**And** every file has a module docstring citing the FR/NFR + ADR + architecture sections it implements
**And** `dispatcher/__init__.py` re-exports the public API; nothing else
**And** the LOC caps are enforced by `scripts/check_module_loc.py` (or the existing pre-commit equivalent — verify the script name in `scripts/`)
**And** `postconditions.py` may be empty (just a docstring + `__all__: tuple[str, ...] = ()`); a non-empty implementation is OUT of scope for 2A.3 (2A.10's `/sdlc-verify` and 2A.12's `/sdlc-signoff` will populate it)

### AC7 — Module boundaries (Architecture §1067, §1106-§1111)

**Given** the architectural boundaries: `dispatcher/` may import `errors/`, `runtime/` (via ABC only — boundary §1106), `workflows/`, `specialists/`, `state/`, `journal/`, `hooks/`, `telemetry/`, `concurrency/`, `config/`, `contracts/`, `ids/`. **Forbidden from**: `engine/`, `cli/`, `dashboard/`, `adopt/`.
**When** the dev runs the boundary linter (`scripts/check_module_boundaries.py`)
**Then** every file under `src/sdlc/dispatcher/` imports only from the allowed list above + stdlib
**And** the import of `runtime/` is via `sdlc.runtime.abc.AIRuntime` (the ABC) — direct import of `sdlc.runtime.mock` or `sdlc.runtime.claude` is FORBIDDEN outside `runtime/` (boundary §1106). The `runtime` parameter on `dispatch(...)` is typed as `AIRuntime` so DI is the substitution mechanism
**And** the linter emits zero new violations after this story's diff
**And** the linter's `dispatcher.depends_on` frozenset is updated to include any newly-required module (most likely already complete per Architecture §1067; verify before adding)

### AC8 — Write-target derivation from `WorkflowSpec.write_globs` + specialist frontmatter

**Given** a `WorkflowSpec` step where `write_globs = {"product-strategist": ("01-Requirement/01-PRODUCT.md",), "synthesizer": ("01-Requirement/01-PRODUCT.md",)}` and the matched specialist's `SpecialistFrontmatter.write_globs = ("01-Requirement/**/*.md",)`
**When** the dispatcher derives the write target for a member
**Then** the rule is:
  1. Look up `step.write_globs[<specialist_name>]` — this MUST be present, non-empty, and a `tuple[str, ...]` of length ≥ 1; if absent, raise `DispatchError("workflow step <name> has no write_globs entry for specialist <specialist_name>")`
  2. The first entry (`step.write_globs[name][0]`) is the canonical write target (single-file-per-dispatch in v1; multi-file dispatch is Epic 2B scope)
  3. The path is interpreted relative to `repo_root` (resolved via `cli._paths.get_repo_root_or_cwd` — but the dispatcher receives `repo_root` as a parameter to keep `cli/` out of the import path; see AC7)
  4. The dispatcher does NOT validate that the path matches the specialist's frontmatter `write_globs` — Story 2A.4's pre-write hook chain (sibling Layer 2 story) is the runtime enforcer; dispatcher trusts the workflow loader's static check
**And** the write itself goes through the `state.atomic.write_state_raw_atomic_sync` (or `write_state_atomic` async sibling — verify which is the right primitive for non-state-model files) — do NOT roll a separate writer; if the existing primitive is unsuitable for arbitrary text files (it canonicalizes JSON), DEFER via D-decision: raise `DispatchError` with a TODO and add a `EPIC-2A-DEBT-WRITE-PRIMITIVE` debt ticket
**And** the write site appends a `JournalEntry` with `kind="artifact_written"` and `payload={"target": <relpath>, "writer": "dispatcher", "specialist": ...}` — distinct from `kind="dispatch_attempt"` (one captures the dispatch outcome; this captures the filesystem effect)

### AC9 — `agent_runs.jsonl` placeholder schema (E3, NFR-OBS-2 — NOT a wire-format contract in 2A)

**Given** the wire-format v1 lock (ADR-024) freezes 5 contracts at `tests/contract_snapshots/v1/`
**When** the dispatcher writes to `agent_runs.jsonl` via `telemetry.runs.record_agent_run(...)`
**Then** the line schema is:

```json
{
  "schema_version": 1,
  "run_id": "<uuid4>",
  "ts": "<RFC 3339 UTC, ms precision, Z suffix>",
  "workflow_step": "<step.name>",
  "specialist_name": "<specialist>",
  "target_kind": "primary|parallel|synthesizer",
  "outcome": "success|failed",
  "attempts": <int 1..3>,
  "tokens_in": <int>,
  "tokens_out": <int>,
  "target_path": "<relpath>",
  "duration_ms": <int>
}
```

**And** the canonical writer lives at `src/sdlc/telemetry/runs.py` (NEW — Architecture §888-§892); the dispatcher orchestrates the call but does NOT roll the writer
**And** the line is appended via `O_APPEND + flock` semantics (mirror `journal/writer.py`); use `concurrency.file_lock(<runs_path>.lock)` for serialization across concurrent dispatches
**And** **`agent_runs.jsonl` is NOT a wire-format contract in Epic 2A.** AC9 makes this explicit: the placeholder schema may evolve in Epic 2B without an ADR-024 ceremony. Do NOT add `tests/contract_snapshots/v1/agent_run.json`. The module docstring of `telemetry/runs.py` MUST state: `"AgentRun is a 2A placeholder; full wire-format lock arrives in Epic 2B Story 2B.1. Format may evolve in 2A without ADR-024 ceremony."`
**And** `python scripts/freeze_wireformat_snapshots.py --check` reports `5 contracts match snapshots` (unchanged)
**And** the model is a private `@dataclass(frozen=True)` `_AgentRunLine` in `telemetry/runs.py` — NOT a pydantic `StrictModel` (the strict-model gate per ADR-025 applies to wire-format contracts; placeholder telemetry uses a frozen dataclass with explicit json serialization)

### AC10 — `JournalEntry.kind` discriminators added in 2A.3 (verify openness first)

**Given** the existing `JournalEntry` contract at `src/sdlc/contracts/journal_entry.py` defines `kind: str` (open string per Story 2A.5 AC6 verification — NOT a closed Literal)
**When** the dispatcher introduces NEW kind values: `"dispatch_attempt"`, `"artifact_written"`, `"stop_trigger_raised"`
**Then** no contract edit is required (open `str`); no ADR-024 ceremony needed
**And** the kind values are documented in a NEW table in `docs/architecture-overview.md` (or whichever doc owns the journal kind catalog — verify; if no catalog exists, create one as part of this story under a new H2 "Journal Kind Catalog")
**And** the catalog entry shape is: `| kind | written by | meaning | added in story |` — populate the 3 new rows + retroactively add `hooks_trusted` (2A.5) if not yet cataloged
**And** if any reviewer disagrees with adding 3 new kinds in one story, the D-decision protocol applies: **D1** = ship all 3 in 2A.3; **D2** = ship `dispatch_attempt` only in 2A.3, defer `artifact_written` + `stop_trigger_raised` to follow-up; **D3** = defer all 3 to Epic 2B and use a generic `kind="dispatcher_event"` with discriminator in payload. **Recommended**: D1 — the three kinds are tightly coupled to dispatch outcomes and discoverable via `sdlc trace`

### AC11 — Tier-2 e2e scenario for dispatch (NEW or extend existing — D-decision required)

**Given** the Tier-2 pipeline harness from Story 2A.0 (`tests/e2e/pipeline/`)
**When** the dev considers adding a Tier-2 scenario covering primary + parallel + synthesizer dispatch with MockAIRuntime
**Then** ONE of the following is delivered (D1/D2/D3 per ADR-026 §3):
  - **D1:** Add a NEW Tier-2 scenario `tests/e2e/pipeline/fixtures/dispatch_panel/` exercising `WorkflowSpec(primary, parallel=[a,b], synth=z)` with a 4-fixture MockAIRuntime; assert journal entries, `agent_runs.jsonl` rows, and the consolidated artifact contents are byte-stable across runs.
  - **D2:** Extend the existing `walking_skeleton` Tier-1 scenario to invoke `dispatch_panel(...)` with a single-member spec (smoke test only); defer multi-member panel coverage to integration tests.
  - **D3:** Defer all new e2e coverage to Story 2A.8 (`/sdlc-start`) which is the first real consumer of `dispatch_panel`; rely on integration tests under `tests/integration/test_dispatch_panel.py` for 2A.3.
**And** whichever option is chosen, the choice MUST be the FIRST line of the PR's Change Log: `D-decision: AC11 chose D<n> because <one-line reason>`
**And** **Recommended**: D3 — 2A.3 is the dispatcher infrastructure; 2A.8 is the first user. Coupling e2e fixtures to 2A.3 creates premature golden churn risk per Epic-1 retro Pattern 5 ("review-patch volume crescendo")
**And** integration coverage MUST exist regardless of D choice: `tests/integration/test_dispatch_primary.py`, `tests/integration/test_dispatch_panel.py`, `tests/integration/test_dispatch_retry.py` are MANDATORY

### AC12 — Quality gate compliance (CONTRIBUTING.md §1)

**Given** the full Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests` (note: the CI command is `mypy --strict src` only; the `tests` portion may surface pre-existing failures — quarantine via Story 2A.5's xfail pattern with EPIC-2A-DEBT-NNN ticket if needed)
  - `pytest -q -m "not e2e"` (unit + integration + property green; pre-existing 18 xfails from EPIC-2A-DEBT-001..012 + 2A.1's xfailed legacy may persist — DO NOT fix in 2A.3, document the pre-existing count in the PR Change Log baseline)
  - `pytest -q -m e2e` (Tier-1 + Tier-2 still green; 2A.0 walking_skeleton MUST pass; per AC11.D3 recommendation no NEW e2e fixtures expected — if you choose D1/D2 update the goldens accordingly)
  - `pytest --cov=src --cov-report=term-missing --cov-fail-under=90` (≥ 90% repo-wide; module-level expectation: 100% on `dispatcher/retry.py` — pure async control flow; ≥ 95% on `dispatcher/core.py`; ≥ 95% on `telemetry/runs.py`)
  - `pre-commit run --all-files`
  - `mkdocs build --strict`
  - `python scripts/freeze_wireformat_snapshots.py --check` — MUST still report `5 contracts match snapshots` per AC9

## Tasks / Subtasks

> Tasks ordered to enable TDD-first commits per ADR-026 §1. AC1 + AC4 + AC9 are CLI/contract surfaces requiring tests-first commit ordering visible in `git log --reverse`.

- [ ] **Task 1 — `dispatcher/__init__.py` + module skeleton + LOC caps (AC6, AC7)** — foundational scaffold, no behavior
  - [ ] 1.1 Create `src/sdlc/dispatcher/{__init__.py, core.py, retry.py, postconditions.py}` with module docstrings only (cite FR25/26/27, NFR-REL-4, ADR-024/025/026, Architecture §821-§824 + §1067).
  - [ ] 1.2 Add `"dispatcher"` entry to `scripts/check_module_boundaries.py` if not already present; verify `dispatcher.depends_on = frozenset({"errors", "runtime", "workflows", "specialists", "state", "journal", "hooks", "telemetry", "concurrency", "config", "contracts", "ids"})` matches Architecture §1067.
  - [ ] 1.3 Add per-file LOC caps to `scripts/check_module_loc.py` (or its equivalent — verify) for `dispatcher/core.py` (≤ 350), `dispatcher/retry.py` (≤ 150), `dispatcher/postconditions.py` (≤ 50). If no LOC linter exists, document the caps as PR Change Log discipline.
  - [ ] 1.4 Boundary linter passes: `python scripts/check_module_boundaries.py` reports 0 new violations.

- [ ] **Task 2 — Retry policy `with_retries` (AC4)** — **TDD-first commit 1**
  - [ ] 2.1 Author `tests/unit/dispatcher/test_retry.py` covering: 1st-attempt success (no sleep, 1 invocation); 1st-fail-2nd-success (1 sleep of 1.0s, 2 invocations, recorded via mock_sleep); 2-fail-3rd-success (2 sleeps: 1.0s then 4.0s, 3 invocations); all-fail (3 invocations, 2 sleeps, raises `DispatchError("...after 3 attempts...")` with `__cause__` set to last exception); non-`DispatchError` propagates immediately (no retry) — test with `WorkflowError`, `SpecialistError`, `HookError`, `ConfigError`, `asyncio.CancelledError`, generic `RuntimeError`; `coro_factory` is invoked fresh each attempt (NOT awaited multiple times). Tests fail (red).
  - [ ] 2.2 Implement `dispatcher/retry.py` with `async def with_retries(coro_factory: Callable[[], Awaitable[T]], *, max_attempts: int = 3, backoff_schedule: tuple[float, ...] = (1.0, 4.0), sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, retryable: Callable[[BaseException], bool] = _is_retryable) -> T`. Tests pass (green).
  - [ ] 2.3 LOC cap: `retry.py` ≤ 150 LOC.

- [ ] **Task 3 — `telemetry/runs.py` placeholder writer (AC9)** — **TDD-first commit 2** (NEW package — `src/sdlc/telemetry/` does NOT exist yet)
  - [ ] 3.1 Author `tests/unit/telemetry/test_runs.py` covering: writes one line; round-trips JSON; rejects bad `outcome` value; rejects bad `target_kind` value; sorted-keys canonical output; concurrent writes serialize via `file_lock` (use `tmp_path` + 2 threads). Tests fail (red).
  - [ ] 3.2 Create `src/sdlc/telemetry/{__init__.py, runs.py}`. Implement `_AgentRunLine` `@dataclass(frozen=True)` + `record_agent_run(runs_path: Path, *, run_id: str, ts: str, workflow_step: str, specialist_name: str, target_kind: Literal["primary","parallel","synthesizer"], outcome: Literal["success","failed"], attempts: int, tokens_in: int, tokens_out: int, target_path: str, duration_ms: int) -> None`. Tests pass (green).
  - [ ] 3.3 Module docstring states the v1.x evolution disclaimer (AC9 last bullet).
  - [ ] 3.4 Boundary linter: add `"telemetry"` to module list with `telemetry.depends_on = frozenset({"errors", "contracts", "journal", "concurrency"})` per Architecture §1066.

- [ ] **Task 4 — `dispatch(step, ...)` primary-only path (AC1, AC8)** — **TDD-first commit 3**
  - [ ] 4.1 Author `tests/unit/dispatcher/test_dispatch_primary.py` covering: happy path (primary specialist exists, runtime returns success, write happens, `agent_runs` line emitted, journal `dispatch_attempt` + `artifact_written` rows appended); missing specialist raises `SpecialistError` (NOT wrapped); missing `step.write_globs[name]` raises `DispatchError`; runtime raises `MockMissError` → propagates after AC4 retry exhaustion in Task 6. For Task 4 use the `with_retries` shim from Task 2 with `max_attempts=1` for isolation. Tests fail (red).
  - [ ] 4.2 Author `tests/unit/dispatcher/test_dispatch_result.py` covering: `DispatchResult` dataclass shape (frozen, all fields populated, `outcome` Literal, `attempts` int); construction immutability; equality semantics. Tests fail (red).
  - [ ] 4.3 Implement `DispatchResult` `@dataclass(frozen=True)` + `_default_prompt_builder(specialist, step) -> str` (single-line scaffold returning the specialist's `body` field — Story 2A.8 will replace) + `dispatch(step, *, runtime, registry, repo_root, journal_path, agent_runs_path, prompt_builder=_default_prompt_builder, sleep=asyncio.sleep) -> DispatchResult` in `dispatcher/core.py`. Tests pass (green).
  - [ ] 4.4 LOC: `core.py` after Task 4 should be ≤ 200 LOC (room for Task 5 panel + Task 6 retry wiring).

- [ ] **Task 5 — `dispatch_panel(step, ...)` primary + parallel + synthesizer (AC2)** — **TDD-first commit 4**
  - [ ] 5.1 Author `tests/unit/dispatcher/test_dispatch_panel.py` covering: primary-only (no parallel, no synth) returns identical shape to `dispatch()` wrapped in `PanelResult`; primary + 2 parallel (no synth) — 3 dispatches happen in parallel (assert via `current_in_flight` peak ≥ 2 with `Semaphore(4)`); primary + 2 parallel + synth — synth dispatched AFTER panel completes with `panel_outputs` populated; synth's output overwrites primary's write target (intentional per AC2.4); panel member failure aborts synth (synth NOT dispatched); per-member `agent_runs` lines written (4 lines for primary+2par+synth); per-member writes preserved (each goes to its own write target). Tests fail (red).
  - [ ] 5.2 Author `tests/unit/dispatcher/test_panel_concurrency.py` covering: `BoundedDispatcher` semaphore size = `max_parallel_agents` from project.yaml; 5-member panel with `max_parallel_agents=2` shows peak in-flight ≤ 2; ordering: results returned in input order (primary first, then parallel in spec order, then synth). Tests fail (red).
  - [ ] 5.3 Implement `PanelResult` `@dataclass(frozen=True)` + `dispatch_panel(step, *, runtime, registry, repo_root, journal_path, agent_runs_path, max_parallel_agents, ...) -> PanelResult` in `dispatcher/core.py`. Use `concurrency.subprocess_pool.BoundedDispatcher.dispatch_many(coros)` for parallel execution. Tests pass (green).
  - [ ] 5.4 LOC: `core.py` after Task 5 should be ≤ 350 LOC (cap per AC6).

- [ ] **Task 6 — Wire AC4 retry into AC1 + AC2 (FR27, NFR-REL-4)** — **TDD-first commit 5**
  - [ ] 6.1 Author `tests/integration/test_dispatch_retry.py` covering: 2A.0 MockAIRuntime fixture series (`step1.yaml` returns success, `step2.yaml` raises twice then succeeds, `step3.yaml` raises 3 times); end-to-end `dispatch()` with `step2` produces 3 journal `dispatch_attempt` rows (outcomes: retry, retry, success), 2 `agent_runs` lines? No — `agent_runs` is written ONCE per dispatch with `attempts=N` final; the per-attempt journal trace covers granularity. Adjust per AC1.5 + AC4 last bullet. Tests fail (red).
  - [ ] 6.2 Wrap the runtime dispatch call in `dispatch()` and `dispatch_panel()` with `with_retries(...)`. Pass real `asyncio.sleep` in production; tests inject a recording mock. Tests pass (green).
  - [ ] 6.3 STOP-trigger placeholder per AC5: on terminal failure, append `JournalEntry(kind="stop_trigger_raised", payload={"trigger": "agent_failure_after_retries", ...})`. Add `# TODO(epic-4)` marker. Add `EPIC-4-STOP-TRIGGER-WIRE` to `_bmad-output/implementation-artifacts/deferred-work.md`.

- [ ] **Task 7 — Disjoint-writes integration test (AC3)**
  - [ ] 7.1 Author `tests/integration/test_dispatch_disjoint_writes.py` covering: a `WorkflowSpec` rejected by 2A.1's `disjoint_writes_check` is NEVER constructible via `WorkflowRegistry.load_workflow` (assert via expected `WorkflowError`); a valid spec reaches `dispatch_panel` cleanly; the AC2.4 intentional collision (synth overwriting primary) is NOT raised by static check (it's the same key, NOT a collision per the static check semantics). Tests pass (green).
  - [ ] 7.2 No new dispatcher code expected — this task verifies the architectural contract holds.

- [ ] **Task 8 — `JournalEntry.kind` catalog doc (AC10)**
  - [ ] 8.1 Open `docs/architecture-overview.md` (or the canonical doc — verify; create if missing). Add H2 "Journal Kind Catalog" with table: `| kind | written by | meaning | added in story |`. Populate rows: `dispatch_attempt` (dispatcher.core, Story 2A.3), `artifact_written` (dispatcher.core, Story 2A.3), `stop_trigger_raised` (dispatcher.core, Story 2A.3, Epic-4 placeholder). Retroactively add `hooks_trusted` (cli.trust_hooks, Story 2A.5) if not present.
  - [ ] 8.2 D-decision: AC10 chose D1 (ship all 3 kinds) — first line of PR Change Log MUST cite this.

- [ ] **Task 9 — Tier-2 e2e D-decision (AC11)**
  - [ ] 9.1 Choose D1, D2, or D3 per AC11. **Recommendation**: D3 (defer e2e to 2A.8).
  - [ ] 9.2 If D1 or D2: build the fixture per `tests/e2e/pipeline/fixtures/walking_skeleton/` shape; if D3: add a debt entry to `_bmad-output/implementation-artifacts/deferred-work.md` under `EPIC-2A-DEBT-DISPATCH-E2E` referencing 2A.8 as the natural home.

- [ ] **Task 10 — Quality gate full sweep (AC12)**
  - [ ] 10.1 `ruff format --check && ruff check src tests` — clean
  - [ ] 10.2 `mypy --strict src` — 0 issues
  - [ ] 10.3 `pytest -q -m "not e2e"` — green (baseline xfails preserved per CONTRIBUTING.md QG1/QG2)
  - [ ] 10.4 `pytest --cov=src --cov-fail-under=90` — ≥ 90% repo-wide; ≥ 95% on `dispatcher/core.py` + `telemetry/runs.py`; 100% on `dispatcher/retry.py`
  - [ ] 10.5 `pre-commit run --all-files` — clean
  - [ ] 10.6 `mkdocs build --strict` — clean (catalog doc from Task 8 must build)
  - [ ] 10.7 `python scripts/freeze_wireformat_snapshots.py --check` — 5 contracts ✓
  - [ ] 10.8 Run `graphify update .` after merging to refresh the knowledge graph (AST-only, no API cost).

- [ ] **Task 11 — Docs + change log**
  - [ ] 11.1 Add a runbook entry `docs/runbooks/diagnose-dispatch-failure.md` covering: how to read `agent_runs.jsonl` for a failed dispatch; how to replay via `sdlc trace --kind=dispatch_attempt`; how to identify retry-vs-config failures.
  - [ ] 11.2 Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: `2a-3-dispatcher-primary-parallel-synthesizer-retry: ready-for-dev → review` after dev finishes.
  - [ ] 11.3 PR Change Log MUST cite the AC10 + AC11 D-decisions on its first two lines.

## Dev Notes

### Critical context — DO NOT skip

Story 2A.3 is the **first user-visible orchestration primitive** at Layer 2 of Epic 2A's DAG (`docs/sprints/epic-2a-dag.md:107-122`). It depends on **2A.1 (WorkflowSpec loader)** and **2A.2 (SpecialistRegistry)** — both done as of `main` at `acd1d3f` — and it is consumed by every Phase-1/2/3 slash command (Stories 2A.8 through 2A.19). Three rules govern the implementation:

1. **The dispatcher is `cli`/`engine`-free.** Architecture §1067 + §1109 mandate dispatcher imports only `errors/`, `runtime/` (via ABC), `workflows/`, `specialists/`, `state/`, `journal/`, `hooks/`, `telemetry/`, `concurrency/`, `config/`, `contracts/`, `ids/`. **No CLI helpers, no engine imports.** When AC1 says "the dispatcher receives `repo_root` as a parameter", that is the boundary discipline — `cli/_paths.get_repo_root_or_cwd` lives in CLI; the dispatcher accepts a resolved `Path` and trusts it.
2. **Retry only on `DispatchError`, not on every exception.** AC4 is explicit: `WorkflowError`, `SpecialistError`, `HookError`, `JournalError`, `StateError`, `SignoffError`, `ConfigError` indicate operator-fixable misconfiguration. Retrying just delays the obvious failure. `asyncio.CancelledError` and `KeyboardInterrupt` MUST propagate immediately. This narrow-retry posture is what makes the FR27 "1 attempt + 2 retries" SLO honest.
3. **`agent_runs.jsonl` is NOT a wire-format contract in 2A.** AC9 makes this explicit. The full schema lock arrives in Epic 2B Story 2B.1 alongside `ClaudeAIRuntime`. If you find yourself writing `tests/contract_snapshots/v1/agent_run.json`, **stop**.

### What this story IS NOT

- It is NOT the pre-write hook chain (Story 2A.4 — sibling Layer 2). The dispatcher writes; 2A.4 will validate writes via `hooks.run_hook_chain(payload)`. 2A.3 does NOT call hooks (that wiring is Story 2A.6 / Epic 2B).
- It is NOT the Claude AIRuntime (Story 2B.1). 2A.3 ships ONLY against `MockAIRuntime` from Story 1.13. The runtime parameter is `AIRuntime` (the ABC), so swapping in `ClaudeAIRuntime` later is a no-op.
- It is NOT the postcondition system (Story 2A.10's `/sdlc-verify` and 2A.12's `/sdlc-signoff`). `dispatcher/postconditions.py` is an empty placeholder file (AC6).
- It does NOT compute STOP triggers. AC5 emits a `kind="stop_trigger_raised"` journal placeholder; Epic 4 Story 4.6 reads these journal entries to surface the actual STOP banner.
- It does NOT enforce `--force-bypass-signoff` (Story 2A.4 owns the bypass flag). 2A.3 has no concept of bypass; every write is direct.
- It does NOT load the workflow YAML (Story 2A.1 owns that). The dispatcher receives a validated `WorkflowSpec` — it trusts it (Decision D3 v1 trust posture).

### Architecture compliance

- **Module specifications (Architecture §1067).** `dispatcher/` exposes `dispatch`, `dispatch_panel`, retry policy. Imports: `errors`, `runtime`, `workflows`, `specialists`, `state`, `journal`, `hooks`, `telemetry`, `concurrency`. **Forbidden from**: `engine`, `cli`. AC7 is the linter enforcement.
- **Boundary rule §1106.** *"`engine/` and `dispatcher/` import `runtime/` only via the `AIRuntime` ABC."* The dispatcher's `runtime` parameter is typed `AIRuntime`; direct import of `runtime.mock` or `runtime.claude` outside `runtime/` raises a pre-commit error.
- **Decision A2 + Concurrency §1058.** `BoundedDispatcher` from `concurrency.subprocess_pool` is the canonical parallel primitive. `Semaphore(max_parallel_agents)` from `config.project.max_parallel_agents` (default 4 per project.yaml).
- **Decision C1 + AIRuntime §355.** `AgentResult(output_text, tool_calls, tokens_in, tokens_out)` is the runtime-neutral dispatch result; immutable, `extra="forbid"`. Never construct `AgentResult` outside `runtime/` — receive it from `runtime.dispatch(...)` and pass through.
- **Decision E3 + Telemetry §1066.** `telemetry/runs.py` writes `agent_runs.jsonl`; dispatcher orchestrates the call. Three streams: `journal.log` (audit, state mutations), `agent_runs.jsonl` (dispatch records), `debug_events.jsonl` (correlation-tagged debug — Story 2B+). 2A.3 does NOT write to `debug_events.jsonl`.
- **Atomic write protocol (Architecture §569-§589).** All writes go through `state.atomic.*` primitives (Story 1.10). For arbitrary text artifacts (markdown specialist outputs), the existing `write_state_atomic` is JSON-canonicalized; if it does NOT support raw text, AC8's escape hatch applies: raise + add a debt ticket.
- **JournalEntry contract (Architecture §1056, ADR-024).** `kind` is open `str` per Story 2A.5 verification. The 3 new kinds (`dispatch_attempt`, `artifact_written`, `stop_trigger_raised`) need NO contract edit. Catalog them in `docs/architecture-overview.md` per AC10.
- **Pydantic strict-mode (ADR-025).** `WorkflowSpec`, `SpecialistFrontmatter`, `JournalEntry`, `HookPayload` all inherit `StrictModel`. The dispatcher consumes them; do NOT bypass strict validation.
- **Wire-format v1 lock (ADR-024).** AC9 verifies `agent_runs.jsonl` is private/non-snapshot. Snapshot count stays at 5.
- **Cold-start budget (Architecture §488-§494).** `dispatch()` adds: 1× registry lookup + 1× runtime dispatch + 1× write + 1× journal append + 1× telemetry append. Should be < 50ms excluding the runtime call (which is dominated by Mock fixture loading + sleep). Negligible vs the existing 200ms cold-start floor.

### Library / framework requirements

- **`asyncio` (stdlib)** for parallel dispatch + retry sleeps. Python 3.10+ floor (see Architecture §337); `TaskGroup` (3.11+) is NOT available — use `asyncio.gather` per Decision A2.
- **`uuid` (stdlib)** for `run_id` generation in `agent_runs.jsonl` lines (`uuid.uuid4()` — sufficient for local-only telemetry, no cryptographic requirement).
- **`hashlib` (stdlib)** if needed for content-hash fields (likely NOT in 2A.3 — that's hook-chain territory in 2A.4).
- **No new runtime dependencies introduced.** Specifically: do NOT add `tenacity`, `backoff`, or any retry library — `with_retries` is ~30 LOC of pure asyncio control flow per AC4. Adding a third-party retry lib would multiply the dependency surface for negligible benefit.
- **pydantic** ≥ 2.x for `WorkflowSpec`, `AgentResult` (already pinned).
- **Python ≥ 3.10** per `.python-version`; `from __future__ import annotations` consistently.

### File structure requirements

```
src/sdlc/dispatcher/                         # NEW (does not exist)
  ├── __init__.py                            # public re-exports: dispatch, dispatch_panel,
  │                                          #   with_retries, DispatchResult, PanelResult
  ├── core.py                                # dispatch + dispatch_panel + result dataclasses (≤ 350 LOC)
  ├── retry.py                               # with_retries + _is_retryable (≤ 150 LOC)
  └── postconditions.py                      # empty stub for Story 2A.10/2A.12 (≤ 50 LOC)

src/sdlc/telemetry/                          # NEW (does not exist)
  ├── __init__.py                            # public re-exports: record_agent_run
  └── runs.py                                # _AgentRunLine + record_agent_run (≤ 200 LOC)

tests/unit/dispatcher/                       # NEW
  ├── __init__.py
  ├── test_retry.py                          # AC4 coverage; pure async tests
  ├── test_dispatch_primary.py               # AC1 + AC8 happy path + error paths
  ├── test_dispatch_result.py                # DispatchResult dataclass shape
  ├── test_dispatch_panel.py                 # AC2 panel orchestration
  └── test_panel_concurrency.py              # AC2 BoundedDispatcher integration

tests/unit/telemetry/                        # NEW
  ├── __init__.py
  └── test_runs.py                           # AC9 placeholder writer

tests/integration/                           # UPDATE
  ├── test_dispatch_retry.py                 # NEW — AC4 e2e via MockAIRuntime
  ├── test_dispatch_panel.py                 # NEW — AC2 multi-fixture scenario
  └── test_dispatch_disjoint_writes.py       # NEW — AC3 cross-story contract

tests/e2e/pipeline/fixtures/dispatch_panel/  # CONDITIONAL — only if AC11 D1 chosen
  ├── workflow.yaml                          # WorkflowSpec(primary, parallel=[a,b], synth=z)
  ├── mock_responses/{primary,a,b,synth}.yaml
  ├── README.md
  └── goldens/                               # journal.log, agent_runs.jsonl, output artifact

docs/architecture-overview.md                # UPDATE — add Journal Kind Catalog (AC10)
docs/runbooks/diagnose-dispatch-failure.md   # NEW — operator runbook for retry/failure diagnosis

scripts/check_module_boundaries.py           # UPDATE if dispatcher/telemetry not yet listed
```

Mirrors:
- `src/sdlc/specialists/registry.py` — defensive copy + `MappingProxyType` pattern for `DispatchResult`/`PanelResult` immutable container fields.
- `src/sdlc/runtime/mock.py` — `_NoDuplicateKeysLoader`, `_compute_prompt_hash`, fail-loud philosophy. Reuse the `MockAIRuntime` class verbatim for tests.
- `src/sdlc/journal/writer.py` — `O_APPEND + flock` semantics for `agent_runs.jsonl` (AC9). Mirror the `_lock_path_for`, `_fsync_journal` patterns; do NOT roll a separate writer if a generic-append public function exists in `journal/`.
- `src/sdlc/concurrency/subprocess_pool.py:BoundedDispatcher` — the canonical parallel primitive; reuse `dispatch_many(coros) -> list[T]`.
- `src/sdlc/cli/_time.py:now_rfc3339_utc_ms` — single source of truth for the `ts` field in `agent_runs.jsonl` and journal entries.

### Testing requirements

- Coverage: ≥ 90% repo-wide MUST hold; ≥ 95% on `dispatcher/core.py`; 100% on `dispatcher/retry.py` (pure logic); ≥ 95% on `telemetry/runs.py`.
- Test marks: `@pytest.mark.unit` for unit tests; integration tests under `tests/integration/` use the project default mark.
- **Anti-tautology receipt** (Task 6.1): manually break the retry-counter increment in `with_retries` — confirm `test_3rd_attempt_succeeds_after_2_failures` fires (verifies the counter is real, not tautological). Document in PR Change Log.
- Async test fixtures: use `pytest-asyncio` (already pinned via Story 1.13's MockAIRuntime tests). Use `asyncio_mode = "auto"` if not already set in `pyproject.toml`.
- `BoundedDispatcher` peak in-flight assertions: poll `current_in_flight()` from the test thread via `asyncio.sleep(0)` interleavings — see Story 1.13's `tests/unit/runtime/test_mock.py` for the pattern.
- Integration tests use real `asyncio.sleep` (production code path) but with backoff schedule overridden to `(0.001, 0.001)` for test speed. The retry-policy unit tests use a recording mock that does NOT sleep at all.

### Previous-story intelligence — what to copy + what to avoid

**Copy from Story 2A.1 (`workflows/loader.py`):**
- The "wire-format frozen reminder" discipline — `WorkflowSpec` is at `schema_version=1` and `_strict_schema_version` rejects float coercion. Trust the loaded spec; do NOT re-validate.
- The TDD-first commit ceremony shape (6 commits visible in `git log --reverse`).
- The `_safe_repr` pattern for embedding user-controlled strings in error messages — apply if any error message includes specialist names or step names from the workflow.

**Copy from Story 2A.2 (`specialists/registry.py`):**
- The `SpecialistRegistry.get(name) -> Specialist` interface — call directly; let `SpecialistError` propagate.
- The `MappingProxyType` defensive-copy pattern for immutable container fields in `DispatchResult` / `PanelResult`.
- The "private vs public manifest" discipline (`_SpecialistManifest` is internal; `Specialist` is public). Apply: `_AgentRunLine` is internal to `telemetry/runs.py`; `record_agent_run` is the public API.

**Copy from Story 2A.5 (`hooks/tampering.py`):**
- The "report-state-not-exception" pattern — but for dispatch, errors are exceptional (we ARE the exception path), so this pattern does NOT apply to dispatcher itself. It DOES apply to `agent_runs.jsonl` reads in future stories (Epic 5 dashboard) — flag for those consumers.
- The advisory-only-in-v1 disclaimer pattern for `_AgentRunLine` (AC9 module docstring).
- The D-decision pattern (D1/D2/D3 explicit options in PR Change Log first line).

**Copy from Story 1.13 (`runtime/mock.py`):**
- `MockAIRuntime` for tests — instantiate with a fixtures dir; dispatch via `await runtime.dispatch(prompt, context)`.
- The `MockMissError(message, details={"step": ..., "path": ...})` shape — propagates through the dispatcher's retry policy unchanged (subclass of `DispatchError`, so it IS retryable per AC4).
- The `_compute_prompt_hash` SHA-256 prefix convention (`sha256:<hex>`).

**Copy from Story 1.10 (atomic write):**
- `state.atomic.write_state_*` for the artifact-write step in AC8. Verify which primitive accepts arbitrary bytes vs. canonicalized JSON-of-State; raise + debt-ticket if no suitable primitive exists.
- Parent-dir fsync discipline.

**Copy from Story 1.20 (`recovery/sdlc-rebuild-state`):**
- The "every state mutation produces a journal entry" invariant. AC1 + AC2 enforce this for `dispatch_attempt` + `artifact_written` kinds.

**AVOID (failure modes from Epic 1 retro):**
- **Pattern 1 — Tautological tests.** Task 6.1 anti-tautology receipt prevents this for the retry counter.
- **Pattern 2 — POSIX-only sprawl.** The dispatcher is async-only and POSIX-clean (uses `asyncio.sleep`, no fcntl directly). All file I/O goes through `state.atomic` + `journal.writer` which already handle POSIX/Win32 boundaries.
- **Pattern 3 — Half-done multi-file refactors.** Keep `dispatcher/core.py` ≤ 350 LOC (AC6). If it grows, extract `_panel_orchestration.py` rather than letting it sprawl.
- **Pattern 4 — Pydantic lax coercion.** `WorkflowSpec` already enforces strict; do NOT downgrade.
- **Pattern 5 — Review-patch volume crescendo.** D-decision protocol on AC10 + AC11 prevents this; choose UP-FRONT in PR Change Log.
- **Pattern 6 — Linter AST blind spots.** This story does NOT extend any AST linter. The boundary linter update in Task 1.2 is a frozenset edit, not new AST logic.

### Git intelligence — recent commits

- `acd1d3f docs(qa-gate): align CONTRIBUTING.md mypy command with CI` — current `main` baseline; the `mypy --strict src` (no `tests`) command is the CI gate. AC12 mirrors this.
- `61b34cd Merge branch 'epic-2a/2a-5-hook-trust' into main` — 2A.5 done; `kind="hooks_trusted"` is a precedent for the 3 new kinds AC10 introduces.
- `dd10fc6 fix(2a-2): preserve original 2-loop ordering in _validate_manifest_entries` — `SpecialistRegistry` interface stable; trust `registry.get(name)` to raise `SpecialistError` on miss.
- Pre-existing 18 xfailed tests (EPIC-2A-DEBT-001..012) per 2A.5 quarantine — DO NOT fix in 2A.3; record the same baseline count in the 2A.3 PR Change Log.

### Project structure notes

- `src/sdlc/dispatcher/` does NOT exist yet. This story creates it (`__init__.py`, `core.py`, `retry.py`, `postconditions.py`).
- `src/sdlc/telemetry/` does NOT exist yet. This story creates it (`__init__.py`, `runs.py`). Story 2B+ will add `debug.py`, `dora.py`, `correlation.py`.
- Shared file edits with **Story 2A.4** (sibling Layer 2): `src/sdlc/contracts/journal_entry.py` is read-only for both (open `str` `kind`); no edit needed. `_bmad-output/implementation-artifacts/deferred-work.md` may be edited by both — coordinate via linear-merge per CONTRIBUTING.md §3.3.
- Shared file edits with **Story 2A.0**: `tests/e2e/pipeline/` may grow if AC11 D1 chosen. Coordinate goldens via the 2A.0 walking-skeleton golden regen discipline.
- No edits expected to `src/sdlc/errors/base.py` — `DispatchError` already exists (since Story 1.6); reuse.

### References

- [Epic 2A overview](_bmad-output/planning-artifacts/epics.md) — story scope at L1039-L1063.
- [Story 2A.3 in epics](_bmad-output/planning-artifacts/epics.md#L1039-L1063) — source ACs.
- [PRD FR25–FR29](_bmad-output/planning-artifacts/prd.md#L756-L762) — orchestrator dispatch contract.
- [PRD FR27 + NFR-REL-4](_bmad-output/planning-artifacts/prd.md#L758) — retry SLO; 1 attempt + 2 retries with 1s/4s backoff.
- [Architecture §337 (Decision A2)](_bmad-output/planning-artifacts/architecture.md) — `asyncio.gather` + `Semaphore(max_parallel_agents)`.
- [Architecture §355 (Decision C1)](_bmad-output/planning-artifacts/architecture.md) — `AIRuntime.dispatch(prompt, context) -> AgentResult` ABC.
- [Architecture §821-§824](_bmad-output/planning-artifacts/architecture.md) — dispatcher/ module file structure.
- [Architecture §1067 (dispatcher/ module spec row)](_bmad-output/planning-artifacts/architecture.md) — public API + import boundaries.
- [Architecture §888-§892 (telemetry/)](_bmad-output/planning-artifacts/architecture.md) — telemetry/runs.py mandate.
- [Architecture §1106 (boundary rule)](_bmad-output/planning-artifacts/architecture.md) — engine/dispatcher import runtime via ABC only.
- [Architecture §1109 (boundary rule §5)](_bmad-output/planning-artifacts/architecture.md) — hooks/ does not import engine/dispatcher.
- [Epic 2A DAG](docs/sprints/epic-2a-dag.md) — Layer 2 placement; Charlie owns 2A.3.
- [ADR-013 — Workflow trust model v1](docs/decisions/ADR-013-workflow-trust-model-v1.md) — v1 trust posture; dispatcher trusts loaded `WorkflowSpec`.
- [ADR-016 — AIRuntime ABC + Mock implementation](docs/decisions/ADR-016-airuntime-abc-and-mock-implementation.md) — runtime substitution mechanism.
- [ADR-024 — Wire-format v1 lock](docs/decisions/ADR-024-wire-format-v1-lock.md) — `_AgentRunLine` private; AC9 keeps snapshot count at 5.
- [ADR-025 — Pydantic strict-mode default](docs/decisions/ADR-025-pydantic-strict-mode-default.md) — `WorkflowSpec` strict; do NOT bypass.
- [ADR-026 — TDD-first + Chunked-review](docs/decisions/ADR-026-tdd-first-chunked-review-workflow.md) — 5+ TDD-first commits expected; D-decision protocol for AC10 + AC11.
- [ADR-027 — E2E test framework strategy](docs/decisions/ADR-027-e2e-test-framework-strategy.md) — Tier-2 fixture shape if AC11 D1 chosen.
- [CONTRIBUTING.md §1-§6](CONTRIBUTING.md) — quality gate, TDD-first, worktree, chunked review, decision protocol.
- [Story 2A.0](_bmad-output/implementation-artifacts/2a-0-e2e-test-harness-tier-1-cli-tier-2-pipeline.md) — Tier-1/Tier-2 harness; dispatch_panel fixture pattern if D1.
- [Story 2A.1](_bmad-output/implementation-artifacts/2a-1-workflow-yaml-loader-schema-validation.md) — `WorkflowRegistry.load_workflow` consumer; trust the validated spec.
- [Story 2A.2](_bmad-output/implementation-artifacts/2a-2-specialist-registry-manifest-validation.md) — `SpecialistRegistry.get(name)` consumer; let `SpecialistError` propagate.
- [Story 2A.5](_bmad-output/implementation-artifacts/2a-5-recovery-hook-tampering-detection-trust-hooks.md) — sibling Layer 1; precedent for the "private contract is NOT snapshotted" pattern (AC9 mirrors it).
- [Story 1.10](_bmad-output/implementation-artifacts/1-10-atomic-write-protocol-chaos-tests.md) — atomic write protocol for AC8.
- [Story 1.13](_bmad-output/implementation-artifacts/1-13-airuntime-abc-mock-airuntime.md) — `MockAIRuntime` for tests.
- [`src/sdlc/runtime/abc.py`](src/sdlc/runtime/abc.py) — `AIRuntime` + `AgentResult`.
- [`src/sdlc/specialists/registry.py`](src/sdlc/specialists/registry.py) — `SpecialistRegistry.get/list_phase/list/names`.
- [`src/sdlc/workflows/loader.py`](src/sdlc/workflows/loader.py) — `load_workflow` + `MAX_FIELD_LEN`.
- [`src/sdlc/contracts/workflow_spec.py`](src/sdlc/contracts/workflow_spec.py) — `WorkflowSpec` (frozen v1; do NOT edit).
- [`src/sdlc/contracts/journal_entry.py`](src/sdlc/contracts/journal_entry.py) — `JournalEntry`; verify `kind` is open `str`.
- [`src/sdlc/concurrency/subprocess_pool.py`](src/sdlc/concurrency/subprocess_pool.py) — `BoundedDispatcher`.
- [`src/sdlc/journal/writer.py`](src/sdlc/journal/writer.py) — `append`, `append_sync`; mirror the `O_APPEND + flock` shape for `agent_runs.jsonl`.
- [`src/sdlc/cli/_time.py`](src/sdlc/cli/_time.py) — `now_rfc3339_utc_ms`; single source of truth for `ts` fields.
- [`src/sdlc/state/atomic.py`](src/sdlc/state/atomic.py) — atomic write public functions; AC8 escape hatch documents what to do if no suitable raw-text primitive exists.
- [`src/sdlc/errors/base.py`](src/sdlc/errors/base.py) — `DispatchError`, `MockMissError`, `WorkflowError`, `SpecialistError` hierarchy.

## Dev Agent Record

### Agent Model Used

_TBD by dev — record the model name + version that implemented this story._

### Debug Log References

_TBD — record red-test failures, anti-tautology receipts, boundary-linter findings, and any decision-needed escalations encountered during dev._

### Completion Notes List

_TBD — populate after implementation is complete with: D-decisions chosen for AC10/AC11; anti-tautology receipt summary; baseline xfail count; coverage delta on dispatcher/ + telemetry/._

### File List

_TBD — populate before requesting `review-A` per ADR-026 §1._

## Change Log

| Date | Author | Change |
|---|---|---|
| 2026-05-10 | bmad-create-story (Claude) | Story file created via `/bmad-create-story` (Layer 2 batch). Layer 1 dependencies (2A.1, 2A.2, 2A.5) all `done` on `main` at `acd1d3f`. §7.4 hard gate does NOT apply (this is not Story N.1). Status: backlog → ready-for-dev. AC10 D-decision DEFERRED to dev-author with **D1 recommended** (ship all 3 new journal kinds in 2A.3); AC11 D-decision DEFERRED with **D3 recommended** (defer Tier-2 e2e to 2A.8). First two lines of PR Change Log MUST cite the chosen options. |
