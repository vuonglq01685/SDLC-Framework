# Story 4.1: `/sdlc-auto` Orchestrator (Auto-Loop, Pure Function of Disk State)

**Status:** done

**Epic:** 4 — Auto-Mode & Autonomous Execution (`/sdlc-auto`)
**Layer:** 1 (`docs/sprints/epic-4-dag.md` §3 — **the fan-out root**; gates all of Layer 2)
**Worktree:** `epic-4/4-1-auto-loop-orchestrator` (owner: Charlie, DAG §5)
**Critical Path:** **ON** the critical path and **its root** — `4.1 → 4.2 → 4.10 → 4.11 → 4.12` (DAG §4). One of the **two highest-risk stories in Epic 4** (novel pure-fn-of-disk loop + crash-resume at 5 kill points, NFR-REL-5).
**Depends on (all on `main`):** Epic 1 substrate — `engine.scanner.scan` (1.15), append-only journal (1.11) + `append_with_seq_alloc` (ADR-032), state projection/rebuild (1.12), `atomic_write` (1.10 / ADR-031), `ids.clock` (1.6), `MockAIRuntime` (1.13); Epic 2A — `dispatcher.dispatch` + the pre-wired `_emit_stop_trigger` seam (2A.3). **Reuses:** the chaos kill-point idiom (1.10) and the `benchmarks` CI gate (1.15). **Does NOT depend on Epic 3 (adopt).**

> **§7.4 Pre-Story 4.1 gate — VERIFIED GREEN 2026-06-10 (all 8 items).** DAG exists + §8 4/4 approved; Epic 3 retro A1/A2 gate scripts on `main`; HIGH D-items closed; ADRs Accepted; wire-format **7/7**; **matrix-green `main` confirmed on `13ba5ca`** (all 8 cells incl. both ex-flake macOS cells + all 10 required checks); debt-decay strict `--target-epic 4` Gate A/B/C **PASS**. (The DAG §1/§7 "sole remaining: A2 toggle" note predates the CI-never-green discovery + today's resolution and is stale.)

---

## Story

As a **tech lead initiating continuous autonomous execution**,
I want **`/sdlc-auto` running an iteration loop `scan → dispatch_next → STOP_check` where each iteration is a pure function of disk state (no in-memory continuation)**,
so that **the loop is recoverable from any crash by simply re-running `/sdlc-auto`, and per-iteration framework overhead stays under 1 second excluding agent execution** (PRD FR19 [prd.md:762], NFR-REL-5 [prd.md:840], NFR-PERF-6 [prd.md:830]).

---

## Acceptance Criteria

> **READ FIRST — binding ground-truth corrections + scope boundaries (verified against the codebase 2026-06-10). These prevent the most likely implementation disasters. Do not skip.**
>
> **(C1) SCOPE: this story builds the loop + the STOP-check *interface*, NOT the 7 concrete STOP triggers.** The 7 triggers are Stories 4.2–4.8 and the watchdog is 4.9; they plug into `engine/stop_triggers.py`. Per DAG §3, 4.1 must **freeze the `engine/auto_loop.py` iteration contract + the `engine/stop_triggers.py` STOP-check interface before Layer 2 branches** (8 stories consume it). 4.1 ships the interface with a registry that currently returns "no trigger fired" (an empty/placeholder trigger set), plus the `agent_failure_after_retries` reader is **out of scope** (that is 4.6, which consumes the `epic_4_placeholder=True` seam). **Build the interface to be byte-stable; if Layer 2 churns it, the whole epic slips.**
>
> **(C2) `correlation_id` DOES NOT EXIST in the codebase today** (`grep -r correlation_id src/ tests/` → zero hits). It is net-new in this story. Generate it as `str(uuid.uuid4())` (match the existing `run_id` convention at `dispatcher/_panel_helpers.py:692`). `sdlc trace` reconstruction is a **reader-side filter** over journal entries carrying the id in their `payload` — it is **NOT** a new field on the frozen `JournalEntry` contract (do not touch `contracts/journal_entry.py`).
>
> **(C3) ZERO new wire-format contracts (ratified Decision D1, DAG §248).** `auto_loop_status` + `stop_reason` are **internal state** added as fields on `State` (`src/sdlc/state/model.py`, a plain `pydantic.BaseModel` — NOT a `StrictModel`, NOT in `tests/contract_snapshots/v1/`). Add them with defaults; `extra="forbid"` + defaults keeps pre-existing `state.json` blobs valid. **Do NOT place any auto-loop model in `src/sdlc/contracts/`** — the AST gate `scripts/check_no_direct_basemodel.py` + the snapshot ceremony only apply there, and D1 forbids new ADR-024 contracts (stays 7/7).
>
> **(C4) The new journal kind `auto_loop_iteration` needs NO contract change** — `JournalEntry.kind` is a bare `str`. Add the kind via the **ADR-028 forward rule** (`docs/decisions/ADR-028-journal-kind-taxonomy.md` §3 table row + §4 Revision-Log line). Write entries with **`append_with_seq_alloc`** (the only multi-process-safe seq allocator, ADR-032) — **NOT** bare `append`, and **NOT** the process-local `_allocate_seq` in `_panel_helpers.py` (documented-racy outside the dispatcher). Event entries set `before_hash=None` and `after_hash="sha256:" + "0"*64` (the ADR-028 §2 sentinel). Timestamps: `ids.clock.now_rfc3339_utc_ms()` (NOT the private `_now_ts()` duplicate).
>
> **(C5) MODULE BOUNDARY — load-bearing (enforced by `scripts/check_module_boundaries.py` + `scripts/module_boundary_table.py`).** `engine` **MAY** import `dispatcher` (it is in engine's `depends_on`) → the async loop lives in `engine/auto_loop.py` and calls `dispatcher.dispatch` directly. `engine` **MUST NOT** import `cli` (engine is `forbidden_from={cli, dashboard}`). Therefore: `cli/_next_resolver.resolve_next`, `cli/output.emit_error`, and `cli/_runtime_selection.use_mock_runtime` **CANNOT** be called from `engine/` — see Tasks for where each goes. Every new `src/` file is **≤ 400 LOC** (the gate asserts it).
>
> **(C6) Real dispatch is mock-only (ratified Decision D3, DAG §289).** 4.1's `dispatch_next` is tested exclusively against `SDLC_USE_MOCK_RUNTIME=1`. A **pre-emptive actionable guard** (the Story 3.8 pattern, `cli/task.py:260–274`) blocks the real-runtime path with `emit_error(...)` **before any journal write or `build_runtime()`**, naming the debt. The load-bearing debt is `EPIC-3-DEBT-CHARACTERIZATION-REAL-DISPATCH` (debt-budget.yaml:129, registered 2026-06-09, marked "LOAD-BEARING FOR EPIC 4"). See Decision **D3** for whether to register a distinct `EPIC-4-DEBT-AUTO-REAL-DISPATCH`.

**AC1 — Iteration loop executes `scan → dispatch_next → STOP_check` (FR19).**
**Given** a project in any phase with at least one ready item,
**When** I run `/sdlc-auto` (the `sdlc auto` CLI command),
**Then** the loop executes iterations: `scan` the disk → `dispatch` the highest-priority ready item → run the STOP-check → continue or halt,
**And** each iteration's state is **fully derived from disk** (no in-memory continuation per ratified Decision A4 — the next iteration re-reads disk, never trusts a Python variable carried across iterations),
**And** the loop logs each iteration to the journal with `kind=auto_loop_iteration`, `payload={"iteration_seq": N, "action": "dispatch"|"stopped"|"continued", "correlation_id": <uuid>}`.

**AC2 — Crash-resume at 5 distinct mid-iteration kill points (NFR-REL-5).**
**Given** the loop running and a process kill (SIGKILL) mid-iteration,
**When** I re-run `/sdlc-auto`,
**Then** the loop resumes from the current disk state without state loss,
**And** `tests/integration/test_auto_loop_resume.py` kills mid-iteration at **5 distinct points** and asserts post-resume correctness,
**And** journal entries written before the kill are intact; entries that had not started are simply absent (the journal's two-state invariant — never a partial entry).

**AC3 — Per-iteration overhead < 1 second, CI-gated (NFR-PERF-6).**
**Given** the iteration-overhead benchmark,
**When** the framework's own per-iteration work is timed (**excluding** agent execution — use the mock runtime so agent time is ~0),
**Then** mean per-iteration overhead is **< 1.0 s**,
**And** a `@pytest.mark.benchmark` test enforces it as a CI regression gate, picked up by the existing `benchmarks` job (`.github/workflows/ci.yml`, "Performance Benchmarks (Story 1.15)").

**AC4 — Per-iteration `correlation_id` reconstructable by `sdlc trace`.**
**Given** the loop's correlation discipline,
**When** an iteration runs,
**Then** that iteration is tagged with a unique `correlation_id` propagated into every journal entry it produces (the `auto_loop_iteration` entry and any `dispatch`-side entries it can stamp),
**And** `sdlc trace` can reconstruct the entire iteration by filtering on the `correlation_id` (reader-side; see C2).

**AC5 — STOP-check interface frozen for Layer 2 (DAG §3, the cross-story contract).**
**Given** Stories 4.2–4.9 will each plug one concrete check into the STOP-check interface,
**When** 4.1 lands,
**Then** `engine/stop_triggers.py` exposes a stable, documented interface — a `StopTrigger` Protocol (or equivalent) + a registry the loop consults each iteration — that returns a typed "no trigger" result today and accepts the 7 triggers + watchdog without changing the loop,
**And** the `auto_loop_status` ∈ {`idle`, `running`, `halted`} and `stop_reason` (`str | None`) internal-state fields exist on `State` so a halt is observable on disk (C3).

**AC6 — `auto_loop_status` is derived from the journal (pure-fn-of-disk; load-bearing for AC2).**
**Given** the loop is "a pure function of disk state",
**When** the loop resumes after a crash,
**Then** `auto_loop_status`/`stop_reason` are re-derived by **journal replay** (extend `state.projection.project_from_journal` to fold `auto_loop_iteration` + any `stop_triggered` entries), so resume reads the same status the crash left — it is **not** trusted from a separately-written `state.json` field that a crash could leave stale (see Decision **D2** if you choose write-through instead).

**AC7 — Greenfield/regression safety + quality gate (CONTRIBUTING §1/§2/§5).**
**Given** a project with no ready item,
**When** `/sdlc-auto` runs,
**Then** the loop performs one scan, finds nothing to dispatch, logs a terminal `auto_loop_iteration` with `action="stopped"` (or returns cleanly), and exits 0 — **never** dispatches against the real runtime (C6).
Quality gate green per §1 (ruff format/check, `mypy --strict src/`, pytest, coverage ≥ 87 operational floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` **7/7 unchanged** since no contract is touched). TDD-first (§2): the loop/resume/benchmark/STOP-interface tests are the failing-first commit, RED before the `engine/` + `cli/` code lands, visible in `git log --reverse`. Material decisions surfaced as D1/D2/D3 (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the behavior suite — loop iteration shape + `auto_loop_iteration` journal entry + correlation_id propagation + 5-kill-point resume + <1s benchmark + STOP-check interface contract + real-dispatch guard. All RED before the `engine/auto_loop.py`, `engine/stop_triggers.py`, `cli/auto.py`, and `State`-field edits land.

- [x] **(§5) T0 — Resolve D1/D2/D3** (loop locus + boundary, status-derivation, debt registration) and record the choices in the Change Log before writing code. Recommended answers are pre-filled below; confirm or override.
- [x] **(AC1, AC5, §2) Write failing loop + STOP-interface tests FIRST** — `tests/unit/engine/test_auto_loop.py` (one iteration: scan→dispatch→stop-check→`auto_loop_iteration` entry with correct `action`/`iteration_seq`/`correlation_id`; pure-fn-of-disk: second iteration re-reads disk, no carried state; no-ready-item terminal case) + `tests/unit/engine/test_stop_triggers.py` (registry returns typed "no trigger"; Protocol shape is stable). RED.
- [x] **(AC2, §2) Write failing resume test** — `tests/integration/test_auto_loop_resume.py` reusing the chaos idiom (see Dev Notes §"Kill-point idiom"): `multiprocessing.get_context("fork")` + child self-`SIGSTOP` at the kill point + parent `WIFSTOPPED`→`SIGKILL` + `@given(seed=...)` `@settings(max_examples=..., deadline=None)`; **5 distinct kill points** (recommended: after-scan, after-next-resolved, after-dispatch-returns, after-journal-append, after-state-write); post-kill assert the journal two-state invariant + correct resume. RED.
- [x] **(AC3, §2) Write failing benchmark** — `tests/benchmark/test_auto_loop_perf.py`, `@pytest.mark.benchmark`, `benchmark.pedantic(run_one_iteration, ...)`, `assert mean < 1.0` (NFR-PERF-6); mirror `tests/benchmark/test_scan_perf.py`. RED (will pass once impl lands; assert the gate exists).
- [x] **(AC4, §2) Write failing trace test** — assert `sdlc trace` (or the journal reader) reconstructs an iteration by `correlation_id`. RED.
- [x] **(C6, AC7, §2) Write failing guard test** — `tests/unit/cli/test_auto_command.py`: on a **real** runtime (`monkeypatch.delenv("SDLC_USE_MOCK_RUNTIME")`) `sdlc auto` fails fast with the actionable `emit_error` naming the debt, **before** any journal write. RED.
- [x] **(AC5, C3) Add internal-state fields** — `State.auto_loop_status: str = "idle"` + `State.stop_reason: str | None = None` in `src/sdlc/state/model.py`. Confirm `freeze_wireformat_snapshots --check` stays **7/7** (State is not a snapshot). No `contracts/` edits.
- [x] **(C4) Register the journal kind** — add `auto_loop_iteration` to `ADR-028 §3` taxonomy table (alphabetised in the story column) + one Revision-Log line. No `JournalEntry` change.
- [x] **(AC5, C1, C5) Implement `engine/stop_triggers.py`** — `StopTrigger` Protocol + a registry/`check_stop(...)` that returns a typed `StopDecision(fired: bool, trigger: str | None, target: str | None)`; today the registry is empty (returns not-fired). Document the interface as **frozen for Layer 2**. ≤ 400 LOC.
- [x] **(AC1, AC2, AC6, C5) Implement `engine/auto_loop.py`** — async `run_auto_loop(repo_root, *, runtime, registry, journal_path, ...)`: `scan` (engine) → resolve next ready item (see D1) → `dispatcher.dispatch(...)` → `check_stop(...)` → `append_with_seq_alloc(auto_loop_iteration)` → loop, each iteration re-reading disk. Generate one `correlation_id=str(uuid.uuid4())` per iteration. ≤ 400 LOC. **Imports allowed:** `dispatcher`, `engine.scanner`, `journal`, `state`, `ids`, `errors`. **Forbidden:** anything from `cli`.
- [x] **(AC6, D2) Extend journal projection** — fold `auto_loop_iteration`/`stop_triggered` into `state.projection.project_from_journal` so `auto_loop_status` is replay-derived (recommended). Add a property/unit test that replay reproduces the on-disk status.
- [x] **(C5, C6, AC1) Implement `cli/auto.py` + register `sdlc auto`** — `run_auto(ctx, ...)`: (1) **pre-emptive real-dispatch guard** (`if not use_mock_runtime(): emit_error("ERR_AUTO_LOOP_REAL_DISPATCH_DEFERRED", ...)`) **before** anything else; (2) `build_runtime(fixtures_dir=...)`; (3) `asyncio.run(run_auto_loop(...))`. Register in `cli/main.py` with a **deferred** `from sdlc.cli.auto import run_auto` body (cold-start <200ms, Architecture §488). The guard + `emit_error` + `use_mock_runtime` live HERE (cli/), never in engine/.
- [x] **(D1) Resolve next-ready-item without an engine→cli import** — the selection currently lives in `cli/_next_resolver.resolve_next` (cli/), which engine cannot import. Recommended: **lift the pure "pick highest-priority ready item from `State`" selector into `engine/`** and have `cli/_next_resolver` delegate to it (cli→engine is allowed) — single source of truth. Alternative: inject a `resolve_next` callable from `cli/auto.py` into `run_auto_loop`. Pick one in T0.
- [x] **(D3) Register/confirm debt** — ensure the guard's `details.debt` id exists in `debt-budget.yaml`; per D3 reuse `EPIC-3-DEBT-CHARACTERIZATION-REAL-DISPATCH` and/or register `EPIC-4-DEBT-AUTO-REAL-DISPATCH` paired with `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION`. Confirm `check_debt_decay_budget --target-epic 4 --mode strict` stays PASS.
- [x] **(AC7, §1) Full quality gate to green** — ruff, `mypy --strict src/`, pytest, coverage ≥ 87, pre-commit, `mkdocs build --strict`, wire-format **7/7**, module-boundary + LOC≤400 gate.
- [x] **(§3) Worktree** — branch `epic-4/4-1-auto-loop-orchestrator` off up-to-date `main`. Layer-1 solo (no sibling collision); **freeze the loop + STOP interface in this story's review before Layer 2 branches.**
- [x] **(§4) Chunked review** — review-A/B/C via the `code-review` workflow once status is `review`. Route the real-dispatch guard + module-boundary design through review-B.

---

## Dev Notes

### Substrate map (verified 2026-06-10 — exact symbols; wrong names break the build)

| Concern | Symbol / path | Notes |
|---|---|---|
| **scan** | `engine.scanner.scan(project_root: Path) -> State` (`src/sdlc/engine/scanner.py:228`) | Pure read; zero writes. Exported via `engine/__init__.py`. |
| **next ready item** | `cli/_next_resolver.resolve_next(repo_root) -> _NextDecision` | **In cli/ — engine cannot import it (C5).** Lift the pure selector to engine or inject (D1). |
| **dispatch** | `dispatcher.core.dispatch(step, *, runtime, registry, repo_root, journal_path, agent_runs_path, ...) -> DispatchResult` (`src/sdlc/dispatcher/core.py:155`); async | **engine MAY import dispatcher (C5).** On failure it already emits the `stop_trigger_raised`/`epic_4_placeholder` seam (4.6 consumes). |
| **stop-trigger seam** | `dispatcher._panel_helpers._emit_stop_trigger(...)` (`_panel_helpers.py:228`) writes `kind=stop_trigger_raised`, `payload.epic_4_placeholder=True` | Pre-wired by 2A.3; **4.6** reads it, not 4.1. |
| **journal append** | `journal.writer.append_with_seq_alloc(journal_path, entry_factory) -> int` (`src/sdlc/journal/writer.py:250`) | **Use this** (single flock read+alloc+write, ADR-032). `entry_factory(seq)` must return a `JournalEntry` whose `monotonic_seq == seq`. |
| **journal entry** | `contracts.journal_entry.JournalEntry(StrictModel)` | `kind` is bare `str`. Event entry: `before_hash=None`, `after_hash="sha256:"+"0"*64`. **Do not edit this contract.** |
| **state model** | `state.model.State(BaseModel)` (`src/sdlc/state/model.py`) | Plain BaseModel, `frozen=True, extra="forbid"`. Add `auto_loop_status`/`stop_reason` here (C3). |
| **state projection** | `state.projection.project_from_journal(journal_path) -> State` (`projection.py:110`) | Extend to fold `auto_loop_iteration` (AC6). |
| **state rebuild** | `state.rebuild.rebuild_state_from_journal(journal_path, state_path) -> int` | The crash-recovery composition (project + atomic write). |
| **atomic write** | `concurrency.io_primitives.atomic_write(path, content, *, encoding="utf-8")` | 7-step POSIX protocol; absolute path; parent must exist. |
| **timestamp** | `ids.clock.now_rfc3339_utc_ms() -> str` | Matches `JournalEntry` RFC-3339 pattern. NOT `_panel_helpers._now_ts()`. |
| **correlation_id** | net-new; `str(uuid.uuid4())` (`import uuid`) | Mirror `run_id` (`_panel_helpers.py:692`). |
| **mock runtime** | `cli/_runtime_selection.use_mock_runtime()` + `build_runtime(fixtures_dir=...)`; `runtime.mock.MockAIRuntime` (1.13) | `tests/conftest.py:36-45` autouse sets `SDLC_USE_MOCK_RUNTIME=1` for the whole suite. `use_mock_runtime` is cli/ → guard lives in cli/auto.py. |
| **CLI registration** | `cli/main.py` Typer `app` (`main.py:39`); `@app.command(name="auto")` with deferred import body | No `sdlc auto` today. No `.claude/commands/` dir — `/sdlc-auto` is the `slash_command` label string, not a file. |
| **repo root** | `cli/_paths.get_repo_root_or_cwd() -> Path` | Use in cli/auto.py. |
| **module boundary** | `scripts/module_boundary_table.py` MODULE_DEPS | `engine.depends_on ⊇ {dispatcher, scanner→engine, state, journal, ids, errors, runtime, ...}`; `engine.forbidden_from={cli, dashboard}`. |

### Kill-point idiom (reuse verbatim from `tests/chaos/`)

`tests/chaos/test_atomic_write_kill_points.py::_spawn_and_kill` is the template: fork a child running the operation, the child self-sends `SIGSTOP` at the instrumented point (`tests/chaos/_kill_protocol.py::_pause_at`), the parent loops on `os.waitpid(pid, os.WNOHANG | os.WUNTRACED)` until `os.WIFSTOPPED`, then sends `SIGKILL`; post-kill assert the two-state invariant via a `read_state`-style check. Decorator stack: `@given(seed=st.integers(...))` + `@settings(max_examples=..., deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])`. Instrument each of the 5 iteration boundaries with `unittest.mock.patch.object` on the low-level call at that step. **This is the proven NFR-REL-5 harness — do not invent a new one.**

### Benchmark gate (reuse from `tests/benchmark/test_scan_perf.py`)

`benchmark.pedantic(fn, args=(...), iterations=N, rounds=M, warmup_rounds=K)` then `assert benchmark.stats.stats.mean < 1.0`. CI job `benchmarks` runs `uv run pytest -m benchmark --benchmark-only --no-cov`. Time **one iteration against the mock runtime** so agent execution ≈ 0 and you are measuring framework overhead only (NFR-PERF-6 is explicit: "excluding agent execution").

### Pre-emptive real-dispatch guard (reuse the Story 3.8 pattern)

`cli/task.py:260–274` is the template: before `build_runtime()`, `if <real-runtime condition>: emit_error("ERR_...", "<actionable message naming the gap + the debt id>", ctx=ctx, details={"debt": "<id>"})`. `emit_error` (`cli/output.py`) is `NoReturn` (exits non-zero). For 4.1 the condition is `not use_mock_runtime()`; place it first in `run_auto(...)` so **no journal write happens** on the real path. Debt context: `debt-budget.yaml:129` `EPIC-3-DEBT-CHARACTERIZATION-REAL-DISPATCH` is registered and flagged "LOAD-BEARING FOR EPIC 4"; its partner `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION` is still unregistered (root cause).

### Why AC6 derives status from the journal

NFR-REL-5 says iterations are "pure functions of disk state with no in-memory continuation." `state.json` is itself journal-derived (`project_from_journal`). If `auto_loop_status` were only written to `state.json` at loop time, a crash between the journal append and the state write would leave `state.json` stale — resume would read a wrong status. Folding the status from `auto_loop_iteration`/`stop_triggered` entries makes the journal the single source of truth and the resume genuinely pure-fn-of-disk. Decision **D2** records the alternative (write-through to `state.json` with a reconciliation step) if you have reason to avoid the projection change.

### Project Structure Notes

- **New files:** `src/sdlc/engine/auto_loop.py`, `src/sdlc/engine/stop_triggers.py`, `src/sdlc/cli/auto.py`; tests under `tests/unit/engine/`, `tests/integration/`, `tests/benchmark/`, `tests/unit/cli/`.
- **Modified:** `src/sdlc/state/model.py` (+2 fields), `src/sdlc/state/projection.py` (fold new kind), `src/sdlc/cli/main.py` (register `auto`), `docs/decisions/ADR-028-journal-kind-taxonomy.md` (+1 kind), possibly `src/sdlc/engine/__init__.py` (export `run_auto_loop`) and `cli/_next_resolver.py` (delegate to lifted selector, per D1).
- **Conventions:** every `src/` file ≤ 400 LOC; deferred imports in CLI command bodies; absolute `from sdlc.X import Y` imports only (relative imports inside `src/sdlc/<module>/` are gate-forbidden, Architecture §1075); engine never imports cli (C5).

### References

- Epic + ACs: `_bmad-output/planning-artifacts/epics.md:2010-2042` (Epic 4 goal + Story 4.1)
- DAG / decisions / risks: `docs/sprints/epic-4-dag.md` §3 (layers), §4 (critical path), §5 (worktree/owner), §7 (risks), D1/D3 (§248, §289)
- Requirements: `_bmad-output/planning-artifacts/prd.md:762` (FR19), `:830` (NFR-PERF-6), `:840` (NFR-REL-5)
- Journal taxonomy + forward rule: `docs/decisions/ADR-028-journal-kind-taxonomy.md`
- Seq-alloc race fix: ADR-032 (`journal/writer.py:250` `append_with_seq_alloc`)
- Atomic write: ADR-031 (`concurrency/io_primitives.py`)
- Real-dispatch debt: `_bmad-output/implementation-artifacts/debt-budget.yaml:129`
- Boundary rules: `scripts/module_boundary_table.py`, `scripts/check_module_boundaries.py` (Architecture §1075/§1103/§488)
- Prior-art patterns: kill-points `tests/chaos/test_atomic_write_kill_points.py`; benchmark `tests/benchmark/test_scan_perf.py`; pre-emptive guard `src/sdlc/cli/task.py:260-274`; mock-runtime test setup `tests/conftest.py:36-45`

---

## Decisions Needed

- **D1 — Loop locus + how `engine/auto_loop.py` resolves the next ready item without importing `cli`.**
  - **(a) Lift the pure selector into `engine/`** — extract "pick highest-priority ready item from `State`" into an engine-level function; `cli/_next_resolver.resolve_next` delegates to it (cli→engine allowed). Single source of truth; keeps `auto_loop.py` boundary-clean. **(Recommended.)**
  - **(b) Dependency-inject a `resolve_next` callable** from `cli/auto.py` into `run_auto_loop(...)`. Lighter (no refactor of `_next_resolver`), keeps cli-specific concerns in cli, but the loop's selection truth is now passed in (slightly weaker contract for Layer 2). Acceptable if `resolve_next` is too entangled with cli output/state to lift cleanly.

- **D2 — `auto_loop_status` derivation: journal-replay vs write-through to `state.json`.**
  - **(a) Journal-replay** — fold `auto_loop_iteration`/`stop_triggered` into `project_from_journal`; status is always re-derived from disk. Truest to NFR-REL-5; the AC2 resume test is the natural proof. **(Recommended — see Dev Notes "Why AC6…".)**
  - **(b) Write-through** — write `auto_loop_status` into `state.json` at loop time with a reconciliation pass on resume. Avoids touching the projection but reintroduces a crash window the resume must reconcile; needs an explicit "journal wins over stale state.json" test.

- **D3 — Real-dispatch debt id for the guard.**
  - **(a) Register a new `EPIC-4-DEBT-AUTO-REAL-DISPATCH`** paired with `EPIC-3-DEBT-CHARACTERIZATION-REAL-DISPATCH` + `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION`. Mirrors the 3.8 per-story-debt pattern; makes the auto-loop's specific deferral first-class in `debt-budget.yaml`. **(Recommended.)**
  - **(b) Reuse `EPIC-3-DEBT-CHARACTERIZATION-REAL-DISPATCH`** (already "LOAD-BEARING FOR EPIC 4") as the guard's `details.debt`. No new debt row; relies on that item's description already covering 4.1/4.6. Lighter, but conflates two distinct deferrals.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

---

## Change Log

- 2026-06-10: Story drafted (create-story) — Layer-1 fan-out root of Epic 4, created only after the §7.4 Pre-Story 4.1 gate was verified **green on all 8 items** (matrix-green `main` on `13ba5ca`, all 10 required checks, after PR #6 hardened the two macOS flakes). Surfaced 6 binding ground-truth corrections (STOP-interface scope vs the 7 triggers; `correlation_id` is net-new; zero new wire-format contracts; ADR-028 forward-rule for `auto_loop_iteration` + `append_with_seq_alloc`; the `engine`↛`cli` boundary + `engine`→`dispatcher` allowance; mock-only dispatch + pre-emptive guard) and 3 decisions (loop locus/selector, status derivation, debt id). Status: ready-for-dev.
- 2026-06-15: Code review (bmad-code-review) — 3 adversarial layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor) + ground-truth verification (boundary gate, mypy --strict, freeze 7/7, 12 tests). Result: **§1 quality gate RED** (module-boundary `engine`→`contracts` + `cli/main.py` 413 LOC > 400) → AC7 "gate green" unmet. 4 decision-needed, 6 patch, 7 deferred, 5 dismissed. See Review Findings. Status: review (pending triage resolution).
- 2026-06-15: Review patches applied + verified (bmad-code-review §5/§6). 4 decisions resolved → patches; 9 patches applied (P6 dismissed: `emit_error` is `NoReturn`); **plus a post-patch discovery — the original story had shipped a RED full suite (7 pre-existing failures: 6 state-golden/hash from the `State` field additions, 1 from the `next_selector` refactor) which no review layer caught (none ran the full suite)**. All 7 fixed (walking-skeleton + abstraction-adequacy goldens regenerated via the sanctioned mechanisms — audited: diff is *only* `auto_loop_status`/`stop_reason`; `test_sdlc_next` repointed to `engine.next_selector`; inline state-hash + rebuild dict updated). **Complete §1 gate now GREEN: ruff/format, mypy --strict (170 files), pytest 3588 passed / coverage 88.31%, boundary gate, freeze 7/7, mkdocs --strict, benchmark 2.5ms ≪ 1s.** Deferred (W1–W7) + deep-D4 dispatcher-entry stamping tracked for follow-up stories. Status stays **review** (NOT done) — the merged-before-done gate (Epic 3 retro A1) requires merge to main before `done`. **Landed on `epic-4/4-1-auto-loop-orchestrator` as TDD-first commits `test(4.1)` → `feat(4.1)` → `chore(4.1)`; remaining: worktree merge to main (flips to done there).**

---

## Review Findings

> bmad-code-review 2026-06-15. Severity in brackets. Verified against the working tree (not committed). `engine`→`contracts` import + `main.py` LOC both confirmed RED by running `scripts/check_module_boundaries.py`; mypy --strict / ruff / freeze-7/7 / 12 new tests all green.

### Decision-needed (RESOLVED 2026-06-15 → now patches)

- [x] [Review][Patch] **[CRITICAL] Module-boundary gate RED: `engine/auto_loop.py:12` imports `sdlc.contracts.journal_entry`** **→ RESOLVED: option B — re-export `JournalEntry` from the `sdlc.journal` package and import it from there (keep `engine` off `contracts`).** — `contracts` declares `forbidden_from={engine,dispatcher,cli}` and is absent from `engine.depends_on`; `scripts/check_module_boundaries.py src/sdlc/engine/auto_loop.py` → EXIT 1. Neither `sdlc.journal` nor `sdlc.state` re-exports `JournalEntry`, so the fix is not mechanical. Options: **(A)** amend `module_boundary_table.py` to grant `engine`→`contracts` (Architecture §1052 table change); **(B, recommended)** re-export `JournalEntry` from the `sdlc.journal` package (engine-allowed) and import it from there; **(C)** construct the entry via a builder in an allowed module. Blocks §1 gate + violates C5. (sources: auditor — gate-confirmed)
- [x] [Review][Patch] **[HIGH] AC2 crash-resume correctness is unproven** **→ RESOLVED: option A — journal an intent marker BEFORE dispatch (intent-anchor pattern) AND strengthen the resume test with real post-resume assertions (entry count / no duplicate iteration / idempotent re-run).** — per-iteration order is `dispatch_fn` (disk side-effect, `auto_loop.py:161`) **before** the `auto_loop_iteration` append (`:184`), and the resume test's `_journal_valid` (`tests/integration/test_auto_loop_resume.py:126-128`) only does `list(iter_entries(journal))` — it asserts **nothing** about entry count, duplicate iterations, idempotency, or post-resume correctness, and the resume dispatch is a no-op `AsyncMock()` that never mutates disk. So NFR-REL-5 (the story's #2-highest risk) is not actually verified. Decision: **(A)** journal an intent marker before dispatch (intent-anchor pattern) or **(B)** add an idempotency guard + document reliance on `run_task`'s own journaling — **in both cases strengthen the resume test with real post-resume assertions**. (sources: edge+blind)
- [x] [Review][Patch] **[MEDIUM] Unbounded-loop risk: `max_iterations=None` default + empty STOP registry + no progress guard** **→ RESOLVED: option A — ship a safety backstop now (`--max-iterations` CLI flag and/or a same-task-twice-in-a-row guard).** — `run_auto` (`cli/auto.py:77-87`) calls the loop with no `max_iterations`; `_EmptyRegistry.check_all` always returns not-fired, so termination depends entirely on `resolve_next_action` eventually returning non-dispatch. A dispatch that fails to advance the task stage re-selects the same `task_id` forever; there is no `--max-iterations` flag and no same-task-twice guard. Decision: ship a safety ceiling/guard in 4.1, or rely on Layer-2 STOP triggers + the 4.9 watchdog? (sources: blind+edge)
- [x] [Review][Patch] **[MEDIUM] AC4 incomplete: `correlation_id` not propagated to dispatch-side entries; `sdlc trace` not wired to it** **→ RESOLVED: option A — thread `correlation_id` through `run_task`/dispatcher entries and add `sdlc trace --correlation-id`.** — `_task_dispatch_fn` discards `correlation_id` (`cli/auto.py:41`) and `run_task` has no such param, so only the `auto_loop_iteration` entry carries the id, not the dispatcher's own entries; `sdlc trace` still filters by `task_id` only (`collect_entries_by_correlation_id` is referenced solely by its own unit test). AC4's "reconstruct the entire iteration by filtering on `correlation_id`" is not reachable from the command. Decision: thread `correlation_id` through `run_task`/dispatcher + add `sdlc trace --correlation-id` now, or accept the reader-side helper as the 4.1 deliverable and defer wiring? (sources: blind+auditor)

### Patch (unambiguous)

- [x] [Review][Patch] **[HIGH] `cli/main.py` is 413 LOC, over the 400 cap → boundary gate RED** — the +15 lines wiring `sdlc auto`/`trace` pushed the file over the NFR-MAINT-3 cap; extract command registration into a submodule to get under 400. Missed by all three review layers. [src/sdlc/cli/main.py]
- [x] [Review][Patch] **[MEDIUM] `iteration_seq` resets to 0 on every resume → duplicate `target_id="auto-loop-iter-N"` across runs** — it is a fresh local never seeded from the journal; after a crash/resume the second run re-emits iter-1, iter-2… and `AutoLoopResult.iterations` undercounts. Seed it from the max existing `auto_loop_iteration` in the journal at startup (more pure-fn-of-disk, not less). [src/sdlc/engine/auto_loop.py:129]
- [x] [Review][Patch] **[MEDIUM] Clean `max_iterations` exit writes no terminal entry → projected `auto_loop_status` stuck at "running"** — the bounded-exit return path emits no `stopped` marker, so projection leaves status "running" after a normal bounded run. Emit a terminal `auto_loop_iteration(action="stopped")` on this path. [src/sdlc/engine/auto_loop.py:195]
- [x] [Review][Patch] **[MEDIUM] Projection fold reads `trigger_kind`, but the only real emitter writes `trigger` → real `stop_trigger_raised` never folds to "halted"** — `_fold_auto_loop_status` reads `payload.get("trigger_kind")` while `dispatcher/_panel_helpers.py:238` writes `payload["trigger"]`; the passing unit test fabricates a `trigger_kind` payload the real seam never produces. Align the fold key to `trigger`. (Latent in 4.1 — empty registry — but the derivation is frozen for Layer 2.) [src/sdlc/state/projection.py:_fold_auto_loop_status]
- [x] [Review][Patch] **[LOW] `scan(repo_root)` runs twice per iteration; the line-136 result is discarded** — `resolve_next_action` re-reads disk itself, then `check_stop` scans again at `:171`; two scans per NFR-PERF-6 iteration observing different snapshots. Scan once and reuse for `check_stop`. [src/sdlc/engine/auto_loop.py:136,171]
- [x] [Review][Dismissed] **[LOW] Real-dispatch guard relies on `emit_error`** — **DISMISSED: `emit_error` is typed `-> NoReturn`, so `mypy --strict` statically guarantees control flow cannot continue past the guard; any future change weakening that contract fails the type gate at every call site. An explicit `raise` would be unreachable dead code.** [src/sdlc/cli/auto.py]

### Deferred (real, but pre-existing or Layer-2 scope)

- [x] [Review][Defer] **[HIGH] `_rebuild_state` raises `ImportError` on win32** [src/sdlc/engine/auto_loop.py:198 → sdlc.state.rebuild] — deferred, pre-existing limitation of `sdlc.state.rebuild`; resume tests `skipif(win32)`, CI matrix is POSIX.
- [x] [Review][Defer] **[MEDIUM] Loop-side halt marker: a fired trigger journals `action="stopped"` (→ "idle"), so `auto_loop_status="halted"` is never written to disk** [src/sdlc/engine/auto_loop.py:171-182] — deferred; pairs with the fold-key patch. Finalize halt representation (distinct `action="halted"` or loop-emitted `stop_trigger_raised`) in Layer 2, where the registry actually fires (C1 scopes 4.1 to interface-only).
- [x] [Review][Defer] **[MEDIUM] Dispatch failure (`run_task` raising `typer.Exit`) aborts the whole loop with no failure journal, leaving status "running"** [src/sdlc/engine/auto_loop.py:161] — deferred; loop-level dispatch error handling pairs with the 4.6 `agent_failure` / 4.9 watchdog stories.
- [x] [Review][Defer] **[MEDIUM] `_finish_stopped` journal-append failure → uncaught `JournalError`; the terminal stop is not crash-safe** [src/sdlc/engine/auto_loop.py:99-108] — deferred; broader loop-robustness/watchdog concern.
- [x] [Review][Defer] **[MEDIUM] No single-instance lock — two concurrent `/sdlc-auto` can dispatch the same task** [src/sdlc/cli/auto.py] — deferred; "v1 single-process by design" is documented in the debt note but unenforced (a lockfile is unscoped for 4.1).
- [x] [Review][Defer] **[MEDIUM] `register_stop_trigger` is a `NotImplementedError` stub and `_EmptyRegistry` has no add path** [src/sdlc/engine/stop_triggers.py:46] — deferred; the AC5-required surface (`StopTrigger` Protocol + `check_stop`) IS frozen/stable, but Layer 2 (4.2) must build the real registration mechanism.
- [x] [Review][Defer] **[LOW] TDD-first RED→GREEN ordering not yet visible in git history** [no commits — working-tree only] — deferred; ensure tests-first commit ordering (§2) at the commit ceremony.

### ‼️ Post-patch discovery (CRITICAL — the original story shipped a RED full test suite)

Running the **full** `pytest` suite (which no review layer did — the "12 tests pass" claim only ran the 4 new test files) surfaced **7 pre-existing failures**, all caused by the original Story 4.1 work (NOT the review patches), so AC7 "quality gate green" was false on counts the review never checked:

- [x] [Review][Patch] **[CRITICAL] 6 state-golden/hash tests fail because the new `State` fields (`auto_loop_status`/`stop_reason`) changed canonical `state.json` bytes without golden regeneration** — `tests/e2e/cli/test_walking_skeleton_goldens.py` (×2), `tests/integration/test_abstraction_adequacy.py` (×2, `mock_factory`+`claude_factory`), `tests/unit/integration/test_abstraction_adequacy_helpers.py::test_canonical_state_hash_is_stable`, `tests/unit/cli/test_rebuild_state.py::test_rebuild_state_succeeds_with_empty_journal`. Fix: regenerate goldens (`pytest --update-goldens`) + update the inline hash/dict in the latter two. C3 ("defaults keep old blobs valid") is true for *validation* but not for *canonical hashes* — adding serialized fields necessarily changes them.
- [x] [Review][Patch] **[HIGH] `tests/e2e/pipeline/test_sdlc_next.py` patches `_select_phase3_task`/`_parse_story_seq`/`_parse_task_seq` at `sdlc.cli._next_resolver`, but the story's D1 refactor moved them to `sdlc.engine.next_selector`** — the test was never repointed. Fix: update the imports/patch targets (lines 286, 327, 346) to `sdlc.engine.next_selector`.

> Note: the 10 review patches are complete and verified green in isolation (ruff/mypy/boundary/freeze 7-7 + the 4 new test files + all affected unit/integration tests, coverage 88.31%). These 7 are a separate, pre-existing gate-RED condition requiring a golden-regeneration ceremony (changes recorded canonical `state.json` bytes) — surfaced to the user before touching recorded output.

### Dismissed (false positive / by-design)

- `check_stop(state=scan(...))` "type mismatch" — `scan()` returns `State`; `mypy --strict` passes. (FP)
- Unparseable-id sentinel `999` "sort `TypeError`" — `next_selector.py:110` sorts by `key=lambda item: (item[0], item[1])` (two ints only); `_TaskSnapshot` is never compared. (FP)
- `auto_loop_iteration` entries "lack hash-chain linkage" — `before_hash=None` + sentinel `after_hash` are mandated by C4 / ADR-028 §2 for event entries. (by design)
- Wall-clock `ts` "non-monotonic ordering" — timestamp source mandated by C4 (`now_rfc3339_utc_ms`); `trace` resolves same-ms ties via the secondary `monotonic_seq` key. (mandated)
- "Already-done task re-selected after resume crashes loop" — `next_selector.py:129` skips `stage=="done"`; `resolve_next_action` never returns a done task. (guarded)
