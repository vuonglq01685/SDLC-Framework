# Story 4.9: Watchdog Timeout (Configurable)

**Status:** ready-for-dev

**Epic:** 4 — Auto-Mode & Autonomous Execution (`/sdlc-auto`)
**Layer:** 2 (`docs/sprints/epic-4-dag.md` §3 — one of the 8 Layer-2 stories, but the **inverse** of the 7 STOP-trigger fan-out: a wall-clock watchdog, **not** a registered `StopTrigger`)
**Worktree:** `epic-4/4-9-watchdog-timeout` (owner: Elena, DAG §5)
**Critical Path:** **OFF** the critical path. The spine is `4.1 → 4.2 → 4.10 → 4.11 → 4.12` (DAG §4); 4.9 is independent of the STOP triggers (a pure wall-clock timer + 2B.1 subprocess termination) and is **front-loaded into the first Layer-2 batch to consume otherwise-idle agent cap** (DAG §5:150, §6:224). It is **not** on any sibling's dependency edge.
**Depends on (all on `main`):** **4.1** — the frozen `engine/auto_loop.py` `run_auto_loop` loop (the iteration contract + `_finish_halted_on_stop_trigger` fired-branch + `StopDecision`); done, merged `2cc8ce4`. **4.2** — landed the real registry seam + the `stop_triggered` journal kind + the projection fold `stop_triggered → ("halted", trigger)`; done, merged `e539d5f`. **Story 2B.1** — the subprocess termination logic (`runtime/claude.py` `_terminate`: SIGTERM → grace → SIGKILL); done. **`src/sdlc/config/project.py`** — the `ProjectConfig` model + `load_project_config` loader (the `watchdog_timeout_minutes` field already exists — see C2).
**Consumed by (downstream):** **4.11** mad-mode must **respect** the watchdog (epics.md:2308–2311 — "When the watchdog timeout fires / Then mad-mode respects the timeout (Story 4.9)"); **5.19** dashboard may surface the watchdog timeout as a banner. 4.9 establishes the loop-level deadline mechanism both consume.

> **Layer-2 precondition — VERIFIED.** 4.9 is **not** Story N.1, so the CONTRIBUTING §7.4 epic-entry gate does **not** re-apply (epic-4 is `in-progress`; the gate cleared at 4.1). The Layer-2 precondition is **"4.1's loop frozen on `main` + 4.2's registry seam + `stop_triggered` halt representation frozen on `main`"** — **satisfied**: 4.1 is `done` (flip `2cc8ce4`) and 4.2 is `done` (close-out `e539d5f`); `engine/auto_loop.py`, `engine/stop_triggers.py`, `engine/stop_registry.py`, `state/projection.py` are on `main` with the `stop_triggered` fold landed; `freeze_wireformat_snapshots --check` is **7/7**. 4.9 **edits `auto_loop.py`** (additive watchdog check inside `run_auto_loop`) but keeps the iteration contract + the `check_stop` signature + the `StopTrigger`/`StopDecision`/registry public symbols byte-stable. **Inherited debt (cite, do not fix):** CR4.2-W3 (4.2's non-sticky halt representation — `auto_loop_iteration(action="stopped")` on the no-work path clobbers an earlier `halted` back to `idle` cross-run); 4.9 inherits this as-is (its watchdog halt uses the **same** `_finish_halted_on_stop_trigger` path, so it inherits the identical fold behaviour — see C5).

---

## Story

As a **user preventing runaway costs from an auto-loop running unbounded**,
I want **a configurable watchdog timeout (default 30 minutes per `project.yaml`) that halts the loop after the elapsed wall-clock time, allowing any in-flight dispatch to complete or be terminated per Story 2B.1**,
so that **misconfigured loops or stuck dispatches do not burn unbounded LLM tokens** (PRD **FR24** [prd.md:767], **FR19** [prd.md:762], **FR51** override [prd.md:812]; the loop's resume contract **NFR-REL-5** [prd.md:840] is inherited from 4.1 and must be preserved).

---

## Acceptance Criteria

> **READ FIRST — binding ground-truth corrections + scope boundaries (verified against the codebase 2026-06-18). These prevent the most likely implementation disasters. Do not skip.**
>
> **(C1) THE HEADLINE CORRECTION — 4.9 is a LOOP-LEVEL concern, NOT a registered `StopTrigger`.** Every sibling 4.2–4.8 implements the frozen `StopTrigger.check(self, *, repo_root: Path, state: State) -> StopDecision` Protocol (`stop_triggers.py:26–32`) and appends to `_ORDERED_TRIGGERS` (`stop_registry.py:13`). **4.9 must NOT.** The Protocol has **no time input** — `check()` receives only `repo_root` + a `State` snapshot, never a clock or an elapsed-time value — so a wall-clock watchdog **cannot** fit the pure-disk trigger registry. The watchdog instead lives **inside `run_auto_loop`** (`auto_loop.py:210–308`): capture a run-start timestamp at loop entry, and on each iteration compare `now − start` against the configured deadline. **Do NOT register a trigger, do NOT touch `stop_registry.py` / `_ORDERED_TRIGGERS`, do NOT add a `watchdog` entry to the trigger tuple.** This is the inverse architecture of 4.3–4.8. See **D1**.
>
> **(C2) THE CONFIG FIELD ALREADY EXISTS — and its current `int` type BLOCKS the integration test.** `grep` confirms `watchdog_timeout_minutes: int = Field(default=30, ge=1)` is **already** on `ProjectConfig` (`project.py:38`), with passing tests pinning default `30`, override `60`, and `ge=1` rejection of `0` (`test_project.py:23, 119, 125–127`). **Do NOT re-add the field.** BUT the integration test (AC4) sets `watchdog_timeout_minutes: 0.05` (3 seconds, for testability — epics.md:2256) and `0.05` is a **non-integer**; pydantic's `int` field rejects it (no fractional-int coercion). So 4.9 must **widen the type to accept a positive number** (`float`, with `0.05` valid) while **still rejecting ≤ 0 and non-numeric garbage** at config-load time (AC2). Reconcile AC2's "non-integer rejected" prose against the test's `0.05`: AC2 is satisfied by rejecting **non-NUMERIC** input (strings like `"foo"`, lists, negatives, zero) — `0.05` is a valid positive number for testability. The existing `ge=1` constraint must change (it would reject `0.05`); use `gt=0` instead. **Mind the 3 existing tests** at `test_project.py:23, 119, 125–127` — they must still pass (default stays `30`, override `60` still works, and `0`/negative still rejected); update `test_watchdog_timeout_ge1_constraint` (`:125`) to reflect `gt=0` semantics, and the `test_defaults_values`/`test_happy_path` int-equality assertions stay valid since `30 == 30.0` and `60 == 60.0` in Python. See **D2**.
>
> **(C3) NO new journal kind, NO ADR-028 edit — REUSE `stop_triggered`.** 4.2 already shipped `kind=stop_triggered` (ADR-028 §3 row at line 79: payload `trigger, target, reason, correlation_id`; Revision-Log at line 157) and the loop's `_finish_halted_on_stop_trigger` fired-branch that journals it (`auto_loop.py:153–178`). The watchdog **synthesizes** `StopDecision(fired=True, trigger="watchdog_timeout", target=<repo-root-or-"">, reason=f"elapsed ~{N} min")` at the loop level and **routes it through the existing `_finish_halted_on_stop_trigger`** — which journals `kind=stop_triggered {trigger:"watchdog_timeout", target, reason, correlation_id}` and rebuilds state. **Do NOT add a journal kind, do NOT edit ADR-028, do NOT edit `state/projection.py`.** The fold already maps `stop_triggered → ("halted", payload["trigger"])` (`projection.py:97–100`), so `state.json` reads `auto_loop_status="halted", stop_reason="watchdog_timeout"` for free. `freeze_wireformat_snapshots --check` stays **7/7** (Epic-4 Decision D1, zero new wire-format).
>
> **(C4) `elapsed_minutes` GOES IN `reason`, NOT a new field.** Epics says the loop halts with `trigger=watchdog_timeout, elapsed_minutes=<N>` (epics.md:2241). `StopDecision` is `@dataclass(frozen=True)` with **exactly 4 fields** — `fired, trigger, target, reason` (`stop_triggers.py:16–23`, byte-stable / frozen for Layer 2). **Do NOT add an `elapsed_minutes` field** to `StopDecision` or the journal payload. Encode the elapsed value inside `reason` (e.g. `reason="elapsed ~30 min"`) — `reason` flows into the `stop_triggered` payload's optional `reason` key (`auto_loop.py:118–119, 164–170`). The dashboard (5.19) reads `stop_reason="watchdog_timeout"` from `state.json`; the human-readable elapsed minutes live in the journal `reason` for audit.
>
> **(C5) RESUME + the per-run RESET — read this before designing the anchor (the core tension).** The loop is pure-function-of-disk (4.1 Decision A4 — no in-memory continuation; resume re-derives from disk). AC3 says "re-run `/sdlc-auto` → the watchdog timer **RESETS**". These pull in opposite directions: a *strictly* disk-derived elapsed (anchored to the first `auto_loop_iteration` ts ever written) would **accumulate across runs** and NOT reset. AC3 explicitly wants a reset, which means anchoring to **THIS run's start** (an in-loop timestamp captured at `run_auto_loop` entry). The watchdog bounds **a single process's wall-clock cost** (FR24 "runaway costs"), not a persistent project-lifetime budget — so a per-run, in-memory start anchor is the correct semantics and it naturally resets on re-run. This does **not** violate NFR-REL-5: NFR-REL-5 requires that loop *iterations* (scan → dispatch → STOP) are pure functions of disk and resume correctly — it does **not** require the wall-clock deadline itself to be disk-persisted (the deadline is a within-process safety bound, not projected state). On resume the loop still re-reads disk, re-derives `iteration_seq` from the journal (`_last_iteration_seq`, `auto_loop.py:88–102`), and continues; only the fresh deadline is per-process. See **D1**. **Inherited (CR4.2-W3, cite-don't-fix):** the watchdog halt uses the **same** `_finish_halted_on_stop_trigger`, so a later no-work run that drains the queue can still clobber the persisted `halted` back to `idle` — identical to 4.2's non-sticky representation; owned by the 4.10/4.11 lifecycle, not 4.9.
>
> **(C6) 2B.1 GRACE — the loop already awaits dispatch FULLY before any stop-check; the watchdog is a POST-dispatch deadline check.** "the in-flight agent dispatch (if any) is allowed to complete or is terminated per Story 2B.1's subprocess termination logic" (epics.md:2243). The 2B.1 termination seam is `runtime/claude.py` `_terminate` (`:39–53` — SIGTERM, `_TERM_GRACE_SECONDS=5.0`, then SIGKILL) invoked from `_invoke_claude_blocking` on its own per-dispatch `_DEFAULT_TIMEOUT_SECONDS=300` timeout (`:201–204`). **4.9 does NOT call `_terminate` directly** and does NOT add a second subprocess kill path — that is 2B.1's owned mechanism, already wired into every dispatch. The loop `await dispatch_fn(...)` (`auto_loop.py:276–284`) runs the dispatch **to completion** (or to 2B.1's own internal timeout/termination) **before** control returns; the watchdog then checks the deadline at the **post-dispatch** point (alongside the existing `check_stop` at `:286`). This is the **recommended grace model**: let the current dispatch finish under 2B.1's own bounds, then the watchdog halts before the **next** dispatch — so "allowed to complete OR terminated per 2B.1" is satisfied with **zero** new termination code (the per-dispatch 2B.1 timeout is the "terminated" branch; a fast dispatch is the "allowed to complete" branch). **Do NOT wrap `dispatch_fn` in `asyncio.wait_for`** to force a mid-dispatch kill — that would duplicate 2B.1's termination and break the frozen `DispatchFn` contract. See **D3**.
>
> **(C7) MODULE BOUNDARY + LOC + mock-runtime + config threading.** The watchdog edit lives in `engine/` (`auto_loop.py`); `engine` MAY import `config`, `state`, `journal`, `ids`, `errors` (`scripts/module_boundary_table.py:97–115` — `config` IS in `engine.depends_on`), MUST NOT import `cli`/`dashboard`. **`auto_loop.py` is currently 314 LOC** (verified) — the watchdog edit must stay small/additive; if it risks the ≤ 400-LOC cap, extract a tiny pure helper (e.g. `def watchdog_deadline_exceeded(start_ts, now_ts, timeout_minutes) -> bool` or a `WatchdogDeadline` dataclass) into a **new** `src/sdlc/engine/watchdog.py` (≤ 400 LOC) and import it. **`run_auto_loop` does NOT receive config today** (`cli/auto.py:80–89` calls it with no timeout arg) — 4.9 must thread the timeout in: add a `watchdog_timeout_minutes: float | None = None` kwarg to `run_auto_loop` (default `None` = no watchdog, preserving every existing caller/test), and in `cli/auto.py` load `load_project_config(root / DEFAULT_PROJECT_YAML).watchdog_timeout_minutes` and pass it through (mirror the `cli/break_.py:224` / `cli/adopt.py:88` config-load idiom). Tests run under `SDLC_USE_MOCK_RUNTIME=1` (autouse, `tests/conftest.py`); the integration test inherits this posture.

---

**AC1 — Positive trigger: the loop halts after the configured wall-clock timeout (FR24).** *(epics.md:2239–2243)*
**Given** `project.yaml` declares `watchdog_timeout_minutes: 30` (default),
**When** the auto-loop has been running for ≥ 30 minutes wall-clock,
**Then** the loop halts with `trigger=watchdog_timeout` (and `elapsed_minutes=<N>` encoded in `reason` — C4),
**And** the journal records the timeout as `kind=stop_triggered {trigger:"watchdog_timeout", target, reason, correlation_id}` (C3 — REUSE 4.2's kind + `_finish_halted_on_stop_trigger`, `append_with_seq_alloc` + event sentinel),
**And** `state.json` reflects `auto_loop_status: halted, stop_reason: watchdog_timeout` (C3 — via the EXISTING projection fold, no new fold code),
**And** the in-flight agent dispatch (if any) completes under 2B.1's own bounds or is terminated by 2B.1's `_terminate` — 4.9 adds NO new kill path (C6).

**AC2 — Override + validation at config-load.** *(epics.md:2245–2248)*
**Given** a `project.yaml` overriding to `watchdog_timeout_minutes: 60`,
**When** the loop runs,
**Then** the watchdog fires at 60 minutes, not 30,
**And** invalid values are rejected at config-load time: **negative** and **zero** (`gt=0`) and **non-numeric** (e.g. `"foo"`, a list, `true`) raise `ConfigError` via the existing `load_project_config` `ValidationError` wrapper (`project.py:77–78`) — while `0.05` (a valid positive number) is **accepted** for testability (C2 reconciliation: "non-integer rejected" ≡ "non-NUMERIC rejected").

**AC3 — Resume: re-run resets the watchdog timer (preserves NFR-REL-5).** *(epics.md:2250–2253)*
**Given** the loop halted by watchdog timeout,
**When** I re-run `/sdlc-auto`,
**Then** the watchdog timer **resets** (a fresh per-run start anchor — D1), and the loop resumes from disk state (re-derives `iteration_seq` from the journal, continues — pure-function-of-disk),
**And** the user can address the underlying slowness (e.g. investigate a stuck agent) before re-running.

**AC4 — Integration test gate (the merge gate).** *(epics.md:2255–2258)*
**Given** `tests/integration/test_watchdog_timeout.py` (new file at the **top level** of `tests/integration/` — NOT under `stop_triggers/`, per epics.md:2255),
**When** the test sets `watchdog_timeout_minutes: 0.05` (3 seconds) and runs the loop under `SDLC_USE_MOCK_RUNTIME=1`,
**Then** the loop halts within **3–5 seconds** (grace for in-flight dispatch),
**And** the termination is journaled correctly: a `stop_triggered` entry with `trigger="watchdog_timeout"` (read via `iter_entries`), and `project_from_journal(journal)` yields `auto_loop_status="halted", stop_reason="watchdog_timeout"`.

**AC5 — Quality gate green + TDD-first (CONTRIBUTING §1/§2/§5).**
Quality gate green per §1 (ruff format/check, `mypy --strict src/`, **full** pytest — not just the new files (the 4.1/4.2 lesson: a partial run hides pre-existing failures), coverage ≥ 87 operational floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` **7/7 unchanged**, module-boundary + LOC ≤ 400). TDD-first (§2): the failing watchdog integration test + the config-validation unit tests are the failing-first commit, **RED before** the `auto_loop.py` watchdog edit + the `project.py` type-widening land, visible in `git log --reverse` (`test(4.9)` → `feat(4.9)`). Material decisions surfaced as **D1/D2/D3** (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the behavior suite — the watchdog integration cell (`0.05` min → halt within 3–5 s + `stop_triggered{trigger:"watchdog_timeout"}` journaled + projection `halted`) plus the config-validation unit tests (`gt=0` rejects ≤ 0; non-numeric rejected; `0.05` accepted; default `30`, override `60` still pass). All RED before the `run_auto_loop` watchdog check, the `watchdog_timeout_minutes` type-widening, and the `cli/auto.py` config-threading land.

- [ ] **(§5) T0 — Resolve D1/D2/D3** (anchor-the-deadline-per-run vs disk-derive · config-type widening · dispatch-grace model) and record the choices in the Change Log **before writing code**. Recommended answers are pre-filled in §Decisions; confirm or override.
- [ ] **(AC1–AC4, §2) Write failing tests FIRST.**
  - `tests/unit/config/test_project.py` (EXTEND the existing file — do NOT create a new one) — add: `0.05` accepted (`ProjectConfig(watchdog_timeout_minutes=0.05).watchdog_timeout_minutes == 0.05`); negative rejected (`pytest.raises(ValidationError)` on `-1`); non-numeric rejected via the loader (`watchdog_timeout_minutes: foo\n` → `ConfigError`); and a YAML-load cell for `watchdog_timeout_minutes: 0.05\n` → loads `0.05`. Keep the existing `:23/:119/:125–127` cells green (default `30`, override `60`, reject `0`). RED.
  - `tests/integration/test_watchdog_timeout.py` (NEW top-level file; reuse the existing `tests/integration/conftest.py` + `__init__.py` wiring) — build a `tmp_path` project with `watchdog_timeout_minutes: 0.05`, a slow-enough `dispatch_fn` (or enough ready work) that wall-clock crosses 3 s; assert: `AutoLoopResult(halted=True, stop_reason="watchdog_timeout")`, halt **within 3–5 s** (bound with a wall-clock assertion), a `stop_triggered` journal entry with `payload["trigger"] == "watchdog_timeout"` (via `iter_entries`), and `project_from_journal(journal).auto_loop_status == "halted"` / `.stop_reason == "watchdog_timeout"`. RED.
  - A `run_auto_loop` unit cell (in `tests/unit/engine/test_auto_loop.py` or a new sibling): with `watchdog_timeout_minutes` set and a monkeypatched/clock-forced elapsed past the deadline, the loop returns `halted=True, stop_reason="watchdog_timeout"` and emits exactly one `stop_triggered` entry; with `watchdog_timeout_minutes=None` the loop never watchdog-halts (back-compat). RED.
- [ ] **(C2, D2) Widen the config field** — change `watchdog_timeout_minutes` on `ProjectConfig` (`project.py:38`) from `int = Field(default=30, ge=1)` to a positive-number type that accepts `0.05` and rejects ≤ 0 / non-numeric (recommended: `float = Field(default=30, gt=0)` — pydantic coerces YAML `30`/`60` ints to `30.0`/`60.0`, accepts `0.05`, rejects `0`/negatives via `gt=0`, rejects strings/lists via type validation; the loader's existing `ValidationError`→`ConfigError` wrap (`:77–78`) gives the AC2 load-time rejection). Confirm the 3 existing tests still pass (int-equality holds: `30 == 30.0`). ≤ 400 LOC.
- [ ] **(C1, C5, C6, D1, D3) Land the watchdog in `run_auto_loop`** — additive edit to `auto_loop.py:210–308`: add kwarg `watchdog_timeout_minutes: float | None = None`; capture `start_ts = now_rfc3339_utc_ms()` (or `time.monotonic()` — D1) at loop entry; on each iteration (post-dispatch, alongside the existing `check_stop` at `:286`) compute elapsed and, if `watchdog_timeout_minutes is not None and elapsed >= deadline`, synthesize `StopDecision(fired=True, trigger="watchdog_timeout", target=str(repo_root) or "", reason=f"elapsed ~{int(elapsed_min)} min")` and route through the EXISTING `_finish_halted_on_stop_trigger(...)` (C3). If the edit pushes `auto_loop.py` near the 400-LOC cap, extract a pure helper into `src/sdlc/engine/watchdog.py` (C7). Keep the iteration contract + `check_stop` signature + `StopDecision`/`StopTrigger`/registry symbols byte-stable. ≤ 400 LOC each.
- [ ] **(C7) Thread config through the CLI** — in `cli/auto.py:79–90`, load `load_project_config(root / DEFAULT_PROJECT_YAML).watchdog_timeout_minutes` (import per `cli/break_.py:224` idiom) and pass it as `watchdog_timeout_minutes=...` into `run_auto_loop`. Handle a missing/malformed `project.yaml` the same way other CLI config-loads do (defaults / `ConfigError` surfaced as a CLI error). `cli` MAY import `config` + `engine` (boundary OK).
- [ ] **(AC5, §1) Full quality gate to green** — ruff, `mypy --strict src/`, pytest (FULL suite, not just new files), coverage ≥ 87, pre-commit, `mkdocs build --strict`, freeze **7/7**, module-boundary + LOC ≤ 400. Run `scripts/check_module_boundaries.py src/sdlc/engine/auto_loop.py` (and `engine/watchdog.py` if created) explicitly. Confirm `freeze` stays 7/7 (no contract touched — C3).
- [ ] **(§3) Worktree** — branch `epic-4/4-9-watchdog-timeout` off up-to-date `main`; rebase before merge. Front-loaded into the first Layer-2 batch (DAG §5/§6) — independent of 4.2–4.8, so no shared-file contention with the STOP-trigger siblings (it does NOT touch `stop_registry.py` — C1).
- [ ] **(§4) Chunked review** — review-A/B/C via the `code-review` workflow once status is `review` (use a different LLM context). Route the per-run-vs-disk anchor decision (D1) + the dispatch-grace model (D3) through review-B. **Run the FULL suite during review** (CONTRIBUTING §4.4 / the 4.1+4.2 lesson — layer reviews only diff the change).

---

## Dev Notes

### Substrate map (verified 2026-06-18 — exact symbols; wrong names break the build)

| Concern | Symbol / path | Notes |
|---|---|---|
| **loop entry (edit here)** | `engine.auto_loop.run_auto_loop` (`auto_loop.py:210–308`) | Add `watchdog_timeout_minutes: float \| None = None` kwarg; capture `start_ts` at entry (`:222–225` region); check deadline post-dispatch (alongside `check_stop` at `:286`). Iteration contract + `check_stop` signature stay **frozen** (C1). **Currently 314 LOC** — keep edit small (C7). |
| **reuse: fired-branch halt-emit** | `engine.auto_loop._finish_halted_on_stop_trigger` (`auto_loop.py:153–178`) | Generic: takes `stop: StopDecision`, journals `kind=stop_triggered {trigger, target, reason?, correlation_id}` via `_append_stop_triggered` (`:133–150`) + `append_with_seq_alloc` + `_EVENT_SENTINEL`, rebuilds state, returns `AutoLoopResult(halted=True, stop_reason=trigger)`. **4.9 routes its synthesized `StopDecision` through this — no new emit code** (C3). |
| **frozen STOP result (reuse, don't extend)** | `engine.stop_triggers.StopDecision` (`stop_triggers.py:16–23`) | `@dataclass(frozen=True)`; **exactly** `fired, trigger, target, reason`. 4.9 synthesizes `StopDecision(fired=True, trigger="watchdog_timeout", target=…, reason="elapsed ~N min")`. **Do NOT add `elapsed_minutes`** (C4). Byte-stable / frozen for Layer 2. |
| **DO NOT TOUCH — the trigger registry** | `engine.stop_registry._ORDERED_TRIGGERS` (`stop_registry.py:13`), `register`/`check_all` | 4.2's seam for the 7 STOP triggers. **4.9 does NOT register a trigger** (C1) — no edit to this file, no `watchdog` tuple entry. |
| **config field (exists — widen type)** | `config.project.ProjectConfig.watchdog_timeout_minutes` (`project.py:38`) | **Already** `int = Field(default=30, ge=1)`. Widen to `float = Field(default=30, gt=0)` to accept `0.05` + reject ≤ 0 / non-numeric (C2/D2). `model_config` is `extra="forbid", frozen=True`. |
| **config loader** | `config.project.load_project_config` (`project.py:45–78`) + `_wrap_validation_error` (`:81–103`) | Missing/empty file → defaults; `ValidationError` → `ConfigError` (the AC2 load-time rejection path). Loader is unchanged by 4.9 — only the field type changes. |
| **config threading (NEW)** | `cli.auto.run_auto` (`cli/auto.py:48–103`); call site `:79–90` | `run_auto_loop` is called with **no timeout arg today**. Add the load + pass-through (mirror `cli/break_.py:224`, `cli/adopt.py:88`). |
| **projection fold (already learns it)** | `state.projection._fold_auto_loop_status` (`projection.py:84–101`) | `stop_triggered → ("halted", payload["trigger"])` (`:97–100`) ALREADY landed by 4.2. `_KNOWN_KINDS` (`:40–52`) + dispatch (`:147`) already list `stop_triggered`. **No projection edit** (C3). |
| **2B.1 termination (reuse, don't re-call)** | `runtime.claude._terminate` (`claude.py:39–53`), `_TERM_GRACE_SECONDS=5.0` (`:17`), `_DEFAULT_TIMEOUT_SECONDS=300` (`:16`); invoked at `:201–204, 220–221` | The per-dispatch SIGTERM→grace→SIGKILL path. 4.9's grace = let the awaited `dispatch_fn` (`auto_loop.py:276`) finish under 2B.1's own bounds, then watchdog-halt before the next dispatch. **No new kill path** (C6/D3). |
| **clock** | `ids.clock.now_rfc3339_utc_ms() -> str` (`clock.py:13`) | RFC-3339 ms-precision UTC string; matches `JournalEntry.ts`. For elapsed math, parse two timestamps **or** use `time.monotonic()` for a per-run monotonic anchor (D1 discusses the tradeoff). |
| **resume anchor (iteration_seq, not deadline)** | `engine.auto_loop._last_iteration_seq` (`auto_loop.py:88–102`) | Re-derives the iteration counter from the journal on every start (pure-fn-of-disk). The **deadline** anchor is separate + per-run (C5/D1) — do NOT conflate the two. |
| **journal append** | `journal.append_with_seq_alloc(journal_path, entry_factory) -> int` | Multi-process-safe allocator; already used by `_append_stop_triggered`. 4.9 uses it transitively via `_finish_halted_on_stop_trigger`. |
| **ADR-028 (no edit)** | `docs/decisions/ADR-028-journal-kind-taxonomy.md:79, 157` | `stop_triggered` row already documents `trigger, target, reason, correlation_id`. 4.9 reuses it — **no ADR edit** (C3). |

### The wall-clock-vs-pure-disk tension (read before implementing D1)

4.1's Decision A4 makes the loop pure-function-of-disk: every iteration re-derives state from the journal, and resume re-reads disk with **no in-memory continuation**. A naive reading says "the elapsed wall-clock must also come from disk" (e.g. anchor to the first `auto_loop_iteration` ts via `iter_entries`). **But that conflicts with AC3's explicit "the watchdog timer RESETS on re-run"** — a disk-anchored elapsed would accumulate across runs and never reset. Resolution: the watchdog is a **within-process safety bound** on a single `/sdlc-auto` invocation's wall-clock cost (FR24 "runaway costs from an auto-loop running unbounded"), **not** a persistent project-lifetime budget. So anchor the deadline to **THIS run's start** (captured in-loop at `run_auto_loop` entry); a fresh run = a fresh anchor = a natural reset (AC3 satisfied). NFR-REL-5 is **not** violated: it constrains *iteration* recoverability (scan → dispatch → STOP re-derived from disk), which 4.9 preserves untouched; it does **not** require the wall-clock deadline to be disk-persisted. The deadline is a process-local guard, not projected state. (If a reviewer insists on a disk-derived "this-run start", journal a `loop_started` ts at entry and read it back — but that is a new journal surface and still must reset per run, so it buys nothing over the in-memory anchor. Recommended: in-memory.)

### Test idioms (reuse from 4.1/4.2 — do not invent)

- **Mock-runtime autouse:** `tests/conftest.py` sets `SDLC_USE_MOCK_RUNTIME=1` suite-wide. The integration test inherits it; the watchdog is runtime-agnostic (it bounds wall-clock, not dispatch internals).
- **Loop driving + journal reading:** `tests/unit/engine/test_auto_loop.py` shows building a `tmp_path` project, running iterations, and reading entries via `iter_entries` + `project_from_journal`. Reuse for the watchdog cell.
- **Config tests:** `tests/unit/config/test_project.py` — `ProjectConfig(...)` direct construction for `ValidationError`, and `load_project_config(yaml_file)` for `ConfigError`. **Extend this file** (do not add a new test module) — the existing watchdog cells (`:23, 119, 125–127`) are your regression guard.
- **Wall-clock bound:** the 3–5 s window (AC4) needs a real-time assertion. Use `time.monotonic()` around the `run_auto_loop` call and assert the elapsed is in `[3, 5]` (plus a small grace ceiling); avoid flaky sub-second timing — `0.05 min = 3 s` gives comfortable headroom. Keep the dispatch fast (mock) so the only wall-clock spend is the watchdog deadline.
- **Resume cell (AC3):** halt by watchdog, then re-run `run_auto_loop` (fresh process semantics in-test = a fresh `start_ts`); assert it does NOT immediately watchdog-halt (timer reset) and resumes from disk.

### Project Structure Notes

- **New files:** `tests/integration/test_watchdog_timeout.py` (top-level, per epics.md:2255); optionally `src/sdlc/engine/watchdog.py` (a pure deadline helper, **only if** the inline edit pressures `auto_loop.py`'s 400-LOC cap — C7).
- **Modified:** `src/sdlc/config/project.py` (widen `watchdog_timeout_minutes` type — C2/D2), `src/sdlc/engine/auto_loop.py` (additive watchdog check in `run_auto_loop` — C1/C6), `src/sdlc/cli/auto.py` (load + thread the timeout — C7), `tests/unit/config/test_project.py` (extend with the `0.05`/non-numeric/negative cells + adjust the `ge=1`→`gt=0` cell — C2), `tests/unit/engine/test_auto_loop.py` (watchdog unit cell).
- **NOT modified (despite the sibling pattern):** `src/sdlc/engine/stop_registry.py`, `src/sdlc/engine/stop_triggers.py`, `src/sdlc/state/projection.py`, `docs/decisions/ADR-028-*.md`, any `src/sdlc/contracts/` file, `tests/contract_snapshots/v1/` (C1/C3 — 4.9 is the inverse of 4.3–4.8 and adds zero wire-format).
- **Conventions:** every `src/` file ≤ 400 LOC (`auto_loop.py` is at 314 — watch the headroom); absolute `from sdlc.X import Y` imports only; `engine` MAY import `config` (boundary-verified `module_boundary_table.py:111`) but never `cli`/`dashboard`.

### References

- Epic + ACs: `_bmad-output/planning-artifacts/epics.md:2231–2258` (Story 4.9 + the 4 BDD ACs); `:2308–2311` (4.11 must respect the watchdog).
- Requirements: `prd.md:767` (FR24 watchdog), `:762` (FR19 auto-loop), `:812` (FR51 project.yaml override), `:840` (NFR-REL-5 resume).
- Loop substrate (consume, edit additively): `src/sdlc/engine/auto_loop.py:153–178` (`_finish_halted_on_stop_trigger`), `:210–308` (`run_auto_loop`), `:88–102` (`_last_iteration_seq`); call site `src/sdlc/cli/auto.py:79–90`.
- Frozen result / registry (do NOT touch): `src/sdlc/engine/stop_triggers.py:16–32`; `src/sdlc/engine/stop_registry.py:13`.
- Config: `src/sdlc/config/project.py:38` (the existing field), `:45–103` (loader + wrap); tests `tests/unit/config/test_project.py:23, 119, 125–127`. Config-load idiom: `src/sdlc/cli/break_.py:224`, `src/sdlc/cli/adopt.py:88`.
- Projection (already folds it — no edit): `src/sdlc/state/projection.py:84–101, 40–52, 147`.
- 2B.1 termination seam: `src/sdlc/runtime/claude.py:39–53` (`_terminate`), `:16–17` (`_DEFAULT_TIMEOUT_SECONDS`, `_TERM_GRACE_SECONDS`), `:201–204, 220–221`.
- Journal kind (reuse — no edit): `docs/decisions/ADR-028-journal-kind-taxonomy.md:79, 157`.
- DAG / decisions: `docs/sprints/epic-4-dag.md` §3 (layers `:129`), §4 (critical path `:131`), §5 (4.9 independent + idle-cap `:150, :197`), §6 (front-load `:224`).
- Module boundary: `scripts/module_boundary_table.py:97–115` (engine deps incl. `config`).
- Inherited debt (cite, don't fix): `docs/sprints/deferred-work.md` → CR4.2-W3 (4.2's non-sticky halt representation).

---

## Decisions Needed

- **D1 — The watchdog start anchor (the headline decision: per-run in-memory vs disk-derived).** The loop is pure-fn-of-disk (4.1 A4), but AC3 wants the timer to **reset** on re-run. These conflict for a disk-anchored elapsed.
  - **(a) Anchor the deadline to THIS run's start — an in-memory `start_ts` (`now_rfc3339_utc_ms()` or `time.monotonic()`) captured at `run_auto_loop` entry, checked each iteration.** Simplest; naturally "resets" on re-run (fresh run = fresh anchor) — directly satisfies AC3. The start ts is in-memory, not on disk, but that is correct: the watchdog bounds a **single process's** wall-clock cost (FR24), not a persistent budget. NFR-REL-5 (iteration recoverability) is preserved — the deadline is a within-process guard, not projected state. Prefer `time.monotonic()` for the elapsed math (immune to wall-clock jumps/NTP) while keeping `now_rfc3339_utc_ms()` for the journal `reason`. **(Recommended.)**
  - **(b) Journal a `loop_started` ts at entry and derive elapsed from disk.** More literally "pure-fn-of-disk", but: (i) it is a **new journal surface** (a new kind or a payload convention) → more wire-format risk against Epic-4 D1's zero-new-contract posture; (ii) it must STILL reset per run (read only THIS run's start), so it gains nothing over (a) for AC3; (iii) it conflates the deadline (a process guard) with projected state. Rejected as over-engineering.
  - **(c) Disk-anchor to the FIRST `auto_loop_iteration` ts ever written.** Strictly disk-derived, but **accumulates across runs** → the timer never resets → **violates AC3**. Rejected.

- **D2 — Config field type-widening (reconcile AC2 "non-integer rejected" with the test's `0.05`).** The field is `int = Field(default=30, ge=1)` today; `0.05` fails int-coercion.
  - **(a) `float = Field(default=30, gt=0)`.** Accepts `0.05`, accepts YAML ints `30`/`60` (coerced to float; existing int-equality tests still pass), rejects `0`/negatives via `gt=0`, rejects non-numeric (`"foo"`, lists, `true`) via type validation → `ConfigError` at load (AC2). "Non-integer rejected" (AC2 prose) is satisfied as "non-NUMERIC rejected"; `0.05` is a valid positive number for testability. Minimal, idiomatic. **(Recommended.)**
  - **(b) `int | float` union with a custom `gt=0` validator.** Equivalent behaviour but more surface and a non-obvious union; `float` already accepts ints transparently. Unnecessary.
  - **(c) Keep `int`, make the integration test use a whole-minute timeout with a faked/scaled clock.** Avoids the type change but contradicts epics.md:2256 (which literally specifies `0.05`) and forces clock-mocking machinery into an integration test. Rejected.

- **D3 — Dispatch-grace model (how "allowed to complete OR terminated per 2B.1" lands).** The loop awaits `dispatch_fn` fully before any stop-check.
  - **(a) Post-dispatch deadline check — let the in-flight dispatch finish under 2B.1's own per-dispatch timeout/termination, then watchdog-halt before the NEXT dispatch.** Zero new termination code: 2B.1's `_terminate` (`runtime/claude.py:39–53`) already bounds each dispatch (its 300 s `_DEFAULT_TIMEOUT_SECONDS` → SIGTERM→grace→SIGKILL). "Allowed to complete" = a fast dispatch; "terminated per 2B.1" = a dispatch that hits 2B.1's own timeout. The watchdog adds a loop-level deadline checked at the existing post-dispatch point (`auto_loop.py:286`). The 3–5 s AC4 window is the grace = at most one in-flight dispatch's remaining time. **(Recommended.)**
  - **(b) Wrap `dispatch_fn` in `asyncio.wait_for(deadline)` to force a mid-dispatch kill.** Forces a hard halt mid-dispatch, but: duplicates 2B.1's termination, breaks the frozen `DispatchFn` await contract, risks orphaning the subprocess outside 2B.1's reaping, and an `asyncio` cancel does NOT actually kill the OS subprocess (2B.1 owns that). Rejected — fights C6.
  - **(c) Pre-dispatch deadline check only.** Halt before each dispatch if over deadline; never interrupts an in-flight dispatch. Simpler but a single very-long dispatch could overshoot the deadline by its full duration with no grace semantics — and it ignores the "in-flight dispatch allowed to complete" clause's intent. (a) subsumes it (check both pre- and post-dispatch is fine; post-dispatch is the load-bearing one for the grace window).

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

- 2026-06-18: Story drafted (create-story) — the **watchdog** Layer-2 story, structurally the **inverse** of the 4.3–4.8 STOP-trigger fan-out: a wall-clock deadline inside `run_auto_loop`, **not** a registered `StopTrigger` (the frozen `StopTrigger.check` Protocol has no time input). Authored after verifying the Layer-2 precondition (**4.1 + 4.2 `done` + merged to `main`**, close-out `e539d5f`; loop + registry seam + `stop_triggered` halt representation frozen; freeze 7/7) and every load-bearing seam first-hand: `run_auto_loop`/`_finish_halted_on_stop_trigger` (reuse the fired-branch), `StopDecision` 4-field frozen shape (C4), the **already-existing** `watchdog_timeout_minutes: int` field whose `int` type blocks the `0.05` test (C2 — the central config correction), the projection fold that **already** maps `stop_triggered → halted` (C3 — no projection/ADR edit), the 2B.1 `_terminate` seam (C6), and the fact that `run_auto_loop` receives no config today (C7 — must thread it via `cli/auto.py`). Surfaced 7 binding ground-truth corrections (C1 loop-level-not-a-trigger; C2 widen the existing field's type + reconcile `0.05` vs "non-integer rejected"; C3 reuse `stop_triggered`, zero ADR/projection/wire-format edits; C4 `elapsed_minutes` in `reason`, not a new `StopDecision` field; C5 per-run reset vs pure-fn-of-disk resume; C6 post-dispatch grace via 2B.1, no new kill path; C7 module-boundary + LOC + config-threading) and 3 decisions (D1 per-run in-memory start anchor; D2 `float gt=0` field type; D3 post-dispatch deadline check). Status: ready-for-dev.
