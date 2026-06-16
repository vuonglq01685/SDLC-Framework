# Story 4.2: STOP Trigger 1 — Open Clarification

**Status:** done

**Epic:** 4 — Auto-Mode & Autonomous Execution (`/sdlc-auto`)
**Layer:** 2 (`docs/sprints/epic-4-dag.md` §3 — first of the 8-story STOP-trigger fan-out; **the FOUNDATIONAL STOP**)
**Worktree:** `epic-4/4-2-stop-clarification` (owner: Dana, DAG §5)
**Critical Path:** **ON** the critical path — `4.1 → 4.2 → 4.10 → 4.11 → 4.12` (DAG §4). 4.2 is the only Layer-2 story on the critical path; Stories **4.10** (auto-brainstorm, which *writes* `open_clarification.md`) and **4.11** (mad-mode, which *resolves* it) both bind to 4.2's existence/resolution contract.
**Depends on (all on `main`):** **4.1** — the frozen `engine/stop_triggers.py` STOP-check interface + `engine/auto_loop.py` loop + the `State.auto_loop_status`/`stop_reason` fields (done, merged `2cc8ce4`); Epic 1 substrate — `append_with_seq_alloc` (ADR-032), `state.projection.project_from_journal` (1.12), `ids.clock` (1.6), `MockAIRuntime` (1.13). **Does NOT depend on Epic 3 (adopt).**
**Consumed by (downstream):** **4.10** produces the `open_clarification.md` 4.2 detects (epics.md:2272, 2281); **4.11** resolves it to satisfy 4.2's resume cell (epics.md:2300, 2340); **5.19** renders 4.2's STOP as a dashboard banner (severity `info`, epics.md:2819).

> **Layer-2 precondition — VERIFIED.** 4.2 is **not** Story N.1, so the CONTRIBUTING §7.4 epic-entry gate does **not** re-apply (epic-4 is `in-progress`; the gate cleared at 4.1). The Layer-2 precondition is **"4.1's loop + STOP-check interface frozen on `main`"** — satisfied: 4.1 is `done` (merged-before-done R1/R2 passed, flip `2cc8ce4`); `engine/auto_loop.py`, `engine/stop_triggers.py`, `engine/next_selector.py` are on `main` (via `4dac45c`); `freeze_wireformat_snapshots --check` is 7/7. **As the foundational STOP that lands the shared registry seam (see C2/D1), 4.2 should merge before the 4.3–4.9 batch branches** — mirrors the 4.1→4.2 freeze discipline.

---

## Story

As a **user trusting the auto-loop to halt when human input is needed**,
I want **the loop to halt when an "open clarification" file exists (indicating an agent flagged ambiguity), preserving the loop's resume contract**,
so that **automated work doesn't proceed past genuine human decisions** (PRD **FR21** trigger 1 [prd.md:764]; the loop's resume/perf contracts **NFR-REL-5** [prd.md:840] + **NFR-PERF-6** [prd.md:830] are inherited from 4.1 and must be preserved).

---

## Acceptance Criteria

> **READ FIRST — binding ground-truth corrections + scope boundaries (verified against the codebase 2026-06-15). These prevent the most likely implementation disasters. Do not skip.**
>
> **(C1) SCOPE — 4.2 DETECTS + HALTS + RECORDS only; it never writes or resolves the clarification.** 4.2 is the FIRST concrete STOP trigger plugged into 4.1's frozen `engine/stop_triggers.py` interface. It detects the **existence** of `.claude/state/clarifications/<id>/open_clarification.md` and halts the auto-loop. It does **NOT** write that file — **Story 4.10** (auto-brainstorm) produces it (epics.md:2272, 2281) — and does **NOT** resolve it — **Story 4.11** / the human does (epics.md:2300, 2063). The contract is **existence-based, not content-based**: do not parse the file's body (see C5).
>
> **(C2) THE REGISTRY IS A STUB — 4.2 builds the real mechanism for all 8 siblings.** Story 4.1 deliberately shipped `register_stop_trigger` raising `NotImplementedError` and `_EmptyRegistry.check_all` always returning not-fired (`stop_triggers.py:35–50`; deferred in 4.1 Review Findings: *"Layer 2 (4.2) must build the real registration mechanism"*). 4.2 lands that mechanism. **Keep the PUBLIC symbols byte-stable** — the `StopDecision` field set (`stop_triggers.py:16–23`), the `StopTrigger` Protocol shape (`:26–32`), and the `check_stop(*, repo_root: Path, state: State) -> StopDecision` signature (`:53–55`) — they are frozen for Layer 2 (DAG §3/§4) and pinned by `tests/unit/engine/test_stop_triggers.py:22–30`. Only the **private** `_REGISTRY`/`_EmptyRegistry` internals and the `register_stop_trigger` body may change. See **D1**.
>
> **(C3) JOURNAL KIND `stop_triggered` IS NET-NEW + AC-MANDATED.** AC-1 requires the journal record `kind=stop_triggered, trigger=open_clarification, target=<path>` (epics.md:2055). `grep -rn stop_triggered src/ tests/` → **zero hits** today; 4.2 introduces it. Add it via the **ADR-028 forward rule** (`docs/decisions/ADR-028-journal-kind-taxonomy.md` §3 taxonomy-table row + §4 Revision-Log line) — `JournalEntry.kind` is a bare `str`, so **no contract/snapshot change** (freeze stays 7/7). Write with **`append_with_seq_alloc`** (ADR-032; the only multi-process-safe allocator) + the event sentinel `before_hash=None`, `after_hash="sha256:"+"0"*64` (bound as `auto_loop.py:_EVENT_SENTINEL`). **`stop_triggered` (4.2) is DISTINCT from `stop_trigger_raised`** — the latter is the 2A.3 agent-failure seam written by `dispatcher/_panel_helpers.py:235,249` and consumed by **Story 4.6** (`EPIC-4-STOP-TRIGGER-WIRE`). **Do NOT touch `_emit_stop_trigger`.** **Payload keys are `trigger`, `target`, optional `reason`, `correlation_id` — use the key `trigger`** (matching the real emitter convention + the fold at `projection.py:84`), **NOT `trigger_kind`**: the adjacent ADR-028 `stop_trigger_raised` row documents a stale `trigger_kind` key the emitter never actually writes (a known doc↔emitter mismatch patched in 4.1) — **do not copy it into the new row or the journal payload**, or the C4 fold will silently fail to match.
>
> **(C4) PROJECTION FOLD must learn `stop_triggered`, or `state.json` will read `idle` not `halted`.** Verified in `state/projection.py`: `_fold_auto_loop_status` (`:68–90`) folds `auto_loop_iteration` + `action="stopped"` → **`idle`** (`:76–78`) and only `stop_trigger_raised` → `halted` (`:81–89`); `_KNOWN_KINDS` (`:40–51`) and the fold dispatch set (`:136`) **do not list `stop_triggered`**. So a fired trigger that merely writes `action="stopped"` produces `auto_loop_status: idle` — failing AC-1's `halted`. 4.2 must (i) emit a `stop_triggered` entry on halt and (ii) extend `_KNOWN_KINDS`, the dispatch set, and `_fold_auto_loop_status` to map `stop_triggered` → `("halted", trigger)`. `_KNOWN_KINDS` is forward-compat **documentation only** (`projection.py:38–39`); the `:136` dispatch guard is what actually routes an entry into the fold — so `stop_triggered` needs **all three** edits (add to the set, add to the `:136` dispatch, add the `_fold_auto_loop_status` branch), not one. The `State.auto_loop_status`/`stop_reason` fields **ALREADY EXIST** (`state/model.py:34–35`, from 4.1) — reuse, do not re-add. This finalizes the halt representation 4.1 explicitly deferred (4.1 Review Findings: *"a fired trigger journals action='stopped' (→ 'idle') … finalize halt representation in Layer 2"*). See **D2** (incl. the fold-order gotcha).
>
> **(C5) ZERO new wire-format contracts (Decision D1 ratified, DAG §248/§269).** `open_clarification.md` is an **opaque presence signal** — detect by path/filename presence, never parse a frozen schema. It is internal operational state, **NOT** a `StrictModel`, **NOT** in `tests/contract_snapshots/v1/`. No `src/sdlc/contracts/` edits; `freeze_wireformat_snapshots --check` stays **7/7**. (This is the deliberate inverse of Epic 3, which froze `AdoptReport`/`AdoptedSymlinks` because they are read back across invocations.)
>
> **(C6) MODULE BOUNDARY + LOC + mock-runtime posture.** New code lives in `engine/` — `engine` MAY import `state`, `journal`, `ids`, `errors` but MUST NOT import `cli`/`dashboard` (`scripts/module_boundary_table.py`; gate `scripts/check_module_boundaries.py`). Every new `src/` file is **≤ 400 LOC** (the NFR-MAINT-3 gate — 4.1's `cli/main.py` tripped it at 413). Tests run under `SDLC_USE_MOCK_RUNTIME=1` (autouse, `tests/conftest.py`); the clarification trigger is pure-disk so the runtime is immaterial to it, but the loop-integration test inherits the posture.
>
> **(C7) STOP-check semantics — ordering + the unused `state` param.** `check_stop` returns the **FIRST fired** decision (`stop_triggers.py:54`). With 4.2 the sole registered trigger, ordering is moot; but 4.3–4.8 each add one, so 4.2 **establishes the priority-ordering convention** the siblings inherit (D1). The loop passes `check_stop` the **PRE-dispatch** `state` snapshot (`auto_loop.py:157–160, 210`); the clarification check reads the filesystem **directly** under `repo_root` at `check()` time, so `OpenClarificationTrigger.check` **accepts but does not consult** the `state: State` Protocol param (`_ = state`). This is by design — do not fight it. **Do not conflate** the state-marker with the `clarification-triager` **support specialist** (`src/sdlc/agents/support/clarification-triager.md`), which is a downstream router writing `04-Support/clarification-report.md` — a different surface 4.2 does not touch.

---

**AC1 — Positive trigger: an open clarification halts the loop (FR21 trigger 1).** *(epics.md:2052–2056)*
**Given** the auto-loop running,
**When** an agent writes an `open_clarification.md` file under `.claude/state/clarifications/<id>/`,
**Then** the next STOP-check detects it and halts the loop,
**And** the journal records `kind=stop_triggered, trigger=open_clarification, target=<path>` (C3 — net-new kind, `append_with_seq_alloc` + event sentinel),
**And** `state.json` reflects `auto_loop_status: halted, stop_reason: open_clarification` (C4 — via the extended projection fold, **not** a stale write-through).

**AC2 — Negative case: no file → continue.** *(epics.md:2058–2061)*
**Given** no open clarification files exist (including a **missing** `.claude/state/clarifications/` directory on a greenfield project — treat as "no file", never an error),
**When** the loop iterates,
**Then** STOP-check for trigger 1 returns `StopDecision(fired=False)`,
**And** the loop continues to the next ready item (no `stop_triggered` entry, no halt).

**AC3 — Resume: resolved → loop continues (preserves NFR-REL-5).** *(epics.md:2063–2066)*
**Given** the loop halted on this trigger and the user resolves the clarification (deletes the file or marks it resolved — see **D3** for the canonical resolution semantics),
**When** I re-run `/sdlc-auto`,
**Then** the loop resumes; STOP-check for trigger 1 now returns `fired=False`,
**And** processing continues from the disk state at halt time (pure-function-of-disk — the resume reads the resolved filesystem, no in-memory continuation).

**AC4 — 4-cell test matrix gate (the merge gate).** *(epics.md:2068–2070)*
**Given** the 4-cell test matrix,
**When** `tests/integration/stop_triggers/test_stop_clarification.py` runs (new directory — 4.2 creates it),
**Then** all 4 cells pass: **(1) positive** (file present → halt), **(2) negative** (no file → continue), **(3) termination state** (`state.json` reflects halt with reason via the projection fold), **(4) resume** (file resolved → loop continues).

**AC5 — Quality gate green + TDD-first (CONTRIBUTING §1/§2/§5).**
Quality gate green per §1 (ruff format/check, `mypy --strict src/`, pytest, coverage ≥ 87 operational floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` **7/7 unchanged**, module-boundary + LOC ≤ 400). TDD-first (§2): the trigger + 4-cell matrix + registry-integration + projection-fold tests are the failing-first commit, **RED before** the `engine/stop_clarification.py` + registry + projection edits land, visible in `git log --reverse` (`test(4.2)` → `feat(4.2)`). Material decisions surfaced as **D1/D2/D3/D4** (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the behavior suite — trigger existence-detection + `StopDecision` shape + the 4-cell loop-halt matrix + `register_stop_trigger` actually registering + the `stop_triggered`→`halted` projection fold. All RED before `engine/stop_clarification.py`, the registry edit, the loop fired-branch halt-emit (D2), and the `state/projection.py` fold land.

- [x] **(§5) T0 — Resolve D1/D2/D3/D4** (registry mechanism · halt representation · resolution semantics · multiple-clarification ordering) and record the choices in the Change Log **before writing code**. Recommended answers are pre-filled in §Decisions; confirm or override.
- [x] **(AC1–AC4, §2) Write failing trigger + matrix tests FIRST.**
  - `tests/unit/engine/test_stop_clarification.py` — instantiate `OpenClarificationTrigger()`; assert `isinstance(trigger, StopTrigger)` (mirror `test_stop_triggers.py:22–30`); on a `tmp_path` repo, `check(repo_root=tmp_path, state=State())` returns `fired=True, trigger="open_clarification", target=<path>` when `.claude/state/clarifications/<id>/open_clarification.md` exists, and `fired=False` when absent / when the dir is missing entirely. RED.
  - `tests/integration/stop_triggers/test_stop_clarification.py` (new dir + `__init__.py`/conftest per the existing `tests/integration/` layout) — the **4-cell matrix** driving `run_auto_loop` (or `check_stop` post-registration): **(1)** file present → `AutoLoopResult(halted=True, stop_reason="open_clarification")` + a `stop_triggered` journal entry (read via `iter_entries`); **(2)** no file → loop continues / does not halt on this trigger; **(3)** termination → `project_from_journal(journal)` yields `auto_loop_status="halted"`, `stop_reason="open_clarification"`; **(4)** resume → resolve the file, re-run, `check()` now `fired=False`. RED.
  - A registry-integration assertion: registering `OpenClarificationTrigger` makes `check_stop(...)` fire (proves `register_stop_trigger` is no longer `NotImplementedError`). RED.
  - A projection unit test: a journal containing a `stop_triggered` entry folds to `auto_loop_status="halted"` (extend the existing `tests/.../test_projection*`-style assertions). RED.
- [x] **(AC1, AC2, C1, C7) Implement the trigger** — `src/sdlc/engine/stop_clarification.py`: class `OpenClarificationTrigger` with `trigger_id = "open_clarification"` and `def check(self, *, repo_root: Path, state: State) -> StopDecision`. Detect any `open_clarification.md` under `<repo_root>/.claude/state/clarifications/*/` (module-level `_CLARIFICATIONS_DIR_REL = ".claude/state/clarifications"`, mirroring the existing `.claude/state/<thing>` constants). Missing dir → `fired=False`. `_ = state` (C7). ≤ 400 LOC.
- [x] **(AC1, C2, D1) Build the real registry** — flip `register_stop_trigger` from `NotImplementedError` to a real append into an ordered registry, and land the composition seam per **D1** (recommended: new `src/sdlc/engine/stop_registry.py` assembling the ordered `tuple[StopTrigger, ...]`; `check_stop` consults it). Register `OpenClarificationTrigger` as the first/known-priority trigger and **document the priority-ordering convention** for 4.3–4.9. Keep the public symbols byte-stable (C2). ≤ 400 LOC each.
- [x] **(AC1, C3, C4, D2) Land the halt representation** — on a fired STOP, emit `kind=stop_triggered` (`trigger`, `target`, optional `reason`, `correlation_id`) via `append_with_seq_alloc` + event sentinel, on the loop's **fired-branch** (`auto_loop.py:210–222`, the 4.1-deferred finalization — see D2), ensuring it is the **terminal** auto-loop fold entry so it is not overwritten back to `idle` (D2 gotcha).
- [x] **(C4) Extend the projection fold** — add `stop_triggered` to `_KNOWN_KINDS` (`projection.py:40–51`), to the fold dispatch set (`:136`), and add a `_fold_auto_loop_status` branch (`:68–90`) mapping `stop_triggered` → `("halted", payload["trigger"])`. Internal-state only — no wire-format/snapshot impact (C5).
- [x] **(C3) Register the journal kind** — add a new `stop_triggered` row (source-story **4.2**, alphabetised by kind within that grouping) to `ADR-028 §3` taxonomy table + one §4 Revision-Log line citing Story 4.2. **Document payload keys `trigger, target, reason, correlation_id` — use `trigger`, NOT `trigger_kind` (do not copy the adjacent `stop_trigger_raised` row's stale key).** No `JournalEntry` change.
- [x] **(AC3, D3, D4) Resolution + multiplicity** — implement resume-recognition per **D3** (deletion canonical) and deterministic multi-clarification handling per **D4** (first-by-lexical-id, deterministic for NFR-REL-5). Cover both in the resume cell + an N>1 test.
- [x] **(AC5, §1) Full quality gate to green** — ruff, `mypy --strict src/`, pytest (full suite, not just the new files — the 4.1 lesson: a partial run hid 7 pre-existing failures), coverage ≥ 87, pre-commit, `mkdocs build --strict`, freeze **7/7**, module-boundary + LOC ≤ 400. Run `scripts/check_module_boundaries.py src/sdlc/engine/stop_clarification.py` explicitly.
- [x] **(§3) Worktree** — branch `epic-4/4-2-stop-clarification` off up-to-date `main`; rebase before merge. **Freeze the registry seam + halt representation in this story's review before the 4.3–4.9 batch branches** (C2).
- [ ] **(§4) Chunked review** — review-A/B/C via the `code-review` workflow once status is `review` (use a different LLM context). Route the registry design (D1) + the loop fired-branch halt-emit (D2) through review-B. **Run the full suite during review** (CONTRIBUTING §4.4 / the 4.1 post-patch lesson — layer reviews only diff the change).

---

## Dev Notes

### Substrate map (verified 2026-06-15 — exact symbols; wrong names break the build)

| Concern | Symbol / path | Notes |
|---|---|---|
| **frozen STOP result** | `engine.stop_triggers.StopDecision` (`stop_triggers.py:16–23`) | `@dataclass(frozen=True)`; `fired: bool`, `trigger/target/reason: str \| None`. **Byte-stable** (C2). 4.2's trigger returns `StopDecision(fired=True, trigger="open_clarification", target=<path>)`. |
| **frozen STOP Protocol** | `engine.stop_triggers.StopTrigger` (`:26–32`) | `@runtime_checkable`; `trigger_id: str` + `check(self, *, repo_root: Path, state: State) -> StopDecision`. 4.2's class must satisfy `isinstance(...)` (pinned `test_stop_triggers.py:22–30`). |
| **registry / register** | `engine.stop_triggers._EmptyRegistry`, `register_stop_trigger`, `check_stop` (`:35–55`) | `register_stop_trigger` **raises `NotImplementedError`** today; `_EmptyRegistry.check_all` always `fired=False`. **4.2 builds the real one** (C2/D1). `check_stop` signature frozen; returns first-fired (C7). |
| **loop call site (fired-branch)** | `engine.auto_loop.run_auto_loop` → `check_stop(...)` (`auto_loop.py:210`) → `_finish_stopped(action="stopped")` on fire (`:213–222`, `:105–131`) | The fired-branch is where 4.2 lands the `stop_triggered` halt-emit (D2). The iteration contract + `check_stop` signature stay frozen. |
| **pre-dispatch snapshot** | `auto_loop.py:157–160` comment | STOP gets the pre-dispatch `state`; "a Layer-2 trigger that needs the post-dispatch snapshot must re-scan inside its own `check()`." A FS-presence check reads disk directly → `state` unused (C7). |
| **journal append** | `journal.append_with_seq_alloc(journal_path, entry_factory) -> int` (ADR-032) | The only multi-process-safe allocator. `entry_factory(seq)` returns a `JournalEntry` with `monotonic_seq == seq`. Event entry: `before_hash=None`, `after_hash="sha256:"+"0"*64`. |
| **state fields (exist)** | `state.model.State.auto_loop_status: str = "idle"`, `stop_reason: str \| None = None` (`model.py:34–35`) | Added by 4.1. Plain `BaseModel` (`frozen=True, extra="forbid"`). **Reuse — do not re-add.** |
| **projection fold** | `state.projection._fold_auto_loop_status` (`projection.py:68–90`), `_KNOWN_KINDS` (`:40–51`), dispatch (`:136`) | Extend to fold `stop_triggered`→`("halted", trigger)` (C4). `auto_loop_iteration`+`action="stopped"`→`idle` (`:76–78`); `stop_trigger_raised`→`halted` (`:81–89`) is the template. |
| **timestamp** | `ids.clock.now_rfc3339_utc_ms() -> str` | Matches `JournalEntry` RFC-3339 pattern. NOT a private `_now_ts()`. |
| **NOT 4.2's** | `dispatcher._panel_helpers._emit_stop_trigger` → `kind=stop_trigger_raised` (`_panel_helpers.py:235,249`); `core.py:291` | The 2A.3 agent-failure seam — **Story 4.6** consumes it. Different kind, different owner. Do not touch. |
| **NOT 4.2's (lookalike)** | `agents/support/clarification-triager.md` → `04-Support/clarification-report.md` | A downstream routing specialist, **not** the `.claude/state/clarifications/<id>/` STOP marker. Different surface (C7). |
| **clarification surface (new)** | `.claude/state/clarifications/<id>/open_clarification.md` | **No src/ reader/writer today** (grep-confirmed). Follows the established `.claude/state/<thing>` convention (cf. `signoff/records.py:54` `.claude/state/signoffs`). 4.2 is the first to reference it. |

### The clarification surface — what exists vs what 4.2 does

- **Nothing in `src/` reads or writes `open_clarification.md` today** (verified). 4.2 is net-new ground. The `.claude/state/clarifications/<id>/` path is established only in the planning docs (epics.md:2053, DAG §5:190, :254) and follows the same `.claude/state/<thing>` layout as `signoffs/`, `adopt-report.json`, `imported-metadata/`.
- **Producer is Story 4.10** (auto-brainstorm): it writes `options.md` (≥2 options + tradeoffs, FR26) and "opens (or creates) the corresponding `open_clarification.md`" (epics.md:2271–2272); even with `auto_brainstorm: false` it "still creates the open_clarification.md (so the loop still halts)" (epics.md:2287). So `open_clarification.md` may exist **with or without** an `options.md` — 4.2's detection must be **independent of `options.md`**.
- **Resolver is Story 4.11 / the human**: mad-mode resolves (epics.md:2300) and the reversal `sdlc unsign --mad-only --include-clarifications` **recreates** `open_clarification.md` (epics.md:2340) — which must re-trigger 4.2. This is why the canonical resolution is **deletion/recreation** (informs D3).
- Detection = **path/filename presence under `.claude/state/clarifications/*/`**; the journal `target` is the path (epics.md:2055). No body parsing (C1/C5).

### Halt representation — the fold-order gotcha (read before implementing D2)

`project_from_journal` folds entries **in order**; the last auto-loop fold wins. The loop's fired-branch currently writes `auto_loop_iteration(action="stopped")` → folds to **`idle`** (`projection.py:76–78`). If 4.2 writes `stop_triggered` **and then** the loop also writes `action="stopped"` afterward, the final fold is `idle` (the stopped entry overwrites halted). **Therefore:** on the fired-branch, emit the `stop_triggered` entry as the **terminal** auto-loop entry (do not also write a later `action="stopped"`), or make `halted` sticky in the fold. The recommended D2(a) replaces the fired-branch's generic stopped-finalizer with a halt-finalizer that writes `stop_triggered`. Prove it with the termination cell (cell 3): `project_from_journal(journal).auto_loop_status == "halted"`.

### Test idioms (reuse from 4.1 — do not invent)

- **Mock-runtime autouse:** `tests/conftest.py` sets `SDLC_USE_MOCK_RUNTIME=1` suite-wide. The clarification trigger is pure-disk (no runtime), but the loop-integration cells inherit this.
- **STOP-interface unit shape:** `tests/unit/engine/test_stop_triggers.py:22–30` is the Protocol-conformance template (`isinstance(stub, StopTrigger)`); `test_check_stop_returns_not_fired_by_default` (`:15–19`) is the negative baseline.
- **Loop unit driving:** `tests/unit/engine/test_auto_loop.py` shows building a `tmp_path` project, running one iteration, and reading entries via `iter_entries` + `project_from_journal`.
- **Resume cell:** follow the pure-fn-of-disk pattern — resolve the file on disk, re-run, assert `fired=False`. Guard with `skipif(win32)` if it exercises `_rebuild_state` (the inherited win32 `ImportError` limitation; CI matrix is POSIX).
- **New integration subdir:** `tests/integration/stop_triggers/` does not exist — create it with the same `__init__.py`/conftest wiring the rest of `tests/integration/` uses.

### Project Structure Notes

- **New files:** `src/sdlc/engine/stop_clarification.py` (the trigger), `src/sdlc/engine/stop_registry.py` (the composition seam, per D1); `tests/unit/engine/test_stop_clarification.py`, `tests/integration/stop_triggers/test_stop_clarification.py` (+ `__init__.py`).
- **Modified:** `src/sdlc/engine/stop_triggers.py` (real `register_stop_trigger` + registry wiring — public symbols byte-stable), `src/sdlc/engine/auto_loop.py` (fired-branch halt-emit, D2 — additive, scoped to the halt path), `src/sdlc/state/projection.py` (fold `stop_triggered`), `docs/decisions/ADR-028-journal-kind-taxonomy.md` (+1 kind), possibly `src/sdlc/engine/__init__.py` (export the new symbols).
- **Conventions:** every `src/` file ≤ 400 LOC; absolute `from sdlc.X import Y` imports only (relative imports inside `src/sdlc/<module>/` are gate-forbidden, Architecture §1075); `engine` never imports `cli` (C6).

### References

- Epic + ACs: `_bmad-output/planning-artifacts/epics.md:2044–2070` (Story 4.2 + the 4 BDD ACs); 4-cell convention `:2012`, `:2350–2355`.
- Producer/resolver context: `epics.md:2271–2272, 2287` (4.10 writes the file), `:2300, 2340` (4.11 resolves/recreates it), `:2819` (dashboard severity `info`).
- Requirements: `_bmad-output/planning-artifacts/prd.md:764` (FR21), `:840` (NFR-REL-5), `:830` (NFR-PERF-6).
- Frozen interface: `src/sdlc/engine/stop_triggers.py` (consume; build the registry); call site `src/sdlc/engine/auto_loop.py:210` (fired-branch); 4.1 story `_bmad-output/implementation-artifacts/4-1-sdlc-auto-orchestrator-auto-loop.md` (AC5 freeze + the deferred halt-representation in Review Findings).
- Projection: `src/sdlc/state/projection.py:40–51, 68–90, 136`; State fields `src/sdlc/state/model.py:34–35`.
- Journal taxonomy + forward rule: `docs/decisions/ADR-028-journal-kind-taxonomy.md` §3/§4; seq-alloc ADR-032.
- DAG / decisions: `docs/sprints/epic-4-dag.md` §3 (layers `:129`), §4 (critical path `:177–178`), §5 (worktree `:190`), D1 (zero new contracts `:248–271`).
- NOT 4.2's: `src/sdlc/dispatcher/_panel_helpers.py:235,249` (`stop_trigger_raised` → 4.6); `src/sdlc/agents/support/clarification-triager.md` (downstream router).

---

## Decisions Needed

- **D1 — Registry mechanism (how the 8 Layer-2 triggers register into the frozen `check_stop`).** `register_stop_trigger` is a `NotImplementedError` stub; 4.2 builds the real path for all siblings. Hard constraint: 8 parallel Layer-2 worktrees each add one trigger → the mechanism is itself a shared-file surface.
  - **(a) Explicit composition registry (DI-style) — `engine/stop_registry.py` assembles an ordered `tuple[StopTrigger, ...]`; flip `register_stop_trigger` to a real append; `check_stop` consults it.** Each trigger is a pure class in its own file (zero body contention); the only shared edit is one reviewed line in the ordered tuple — and the priority order (which the "first-fired" contract C7 makes load-bearing) becomes an **explicit, reviewable artifact** rather than an import-order accident. Pure classes are trivially unit-testable (no global reset fixture). Keeps the frozen `stop_triggers.py` public file untouched. **(Recommended.)**
  - **(b) Per-trigger self-registration on import** — each trigger module calls `register_stop_trigger(...)` at import time; a bootstrap imports each module. Matches the `specialists/registry.py` idiom; trigger bodies fully isolated. But import-order-dependent priority (fragile for first-fired), import-time side effects, and global mutable registry (needs reset fixtures).
  - **(c) Central explicit list inside `stop_triggers.py`** — all 8 worktrees edit the same literal in the frozen public file → **HIGH** merge contention + reopens the frozen file 8×. Rejected.

- **D2 — Halt representation (how AC-1's `kind=stop_triggered` + `auto_loop_status: halted` land on disk).** Today the fired-branch writes `auto_loop_iteration(action="stopped")` → folds to **`idle`**, and `stop_triggered` is not folded at all (C4). The halt is invisible on disk.
  - **(a) Loop fired-branch emits `stop_triggered` + projection learns it.** Replace the fired-branch's generic stopped-finalizer with a halt-finalizer that writes `kind=stop_triggered` (trigger/target/reason) via `append_with_seq_alloc`, and extend the projection fold (C4). This is the 4.1-review-deferred *"finalize halt representation in Layer 2 where the registry actually fires."* It touches **only the fired-branch** — not the iteration contract, not the `StopTrigger`/`check_stop` signatures. Mind the fold-order gotcha (emit `stop_triggered` as the terminal auto-loop entry). **(Recommended.)**
  - **(b) Trigger-side journaling** — `OpenClarificationTrigger.check()` derives `journal_path` from `repo_root` and writes `stop_triggered` itself, keeping `auto_loop.py` byte-stable. But it makes `check()` side-effecting (breaks the pure-read Protocol + risks a double-write with the loop), and `check()` does not receive `journal_path` (Protocol frozen) — and the journal write is async while `check_stop` is sync. Awkward.
  - **(c) Projection-only** — fold `auto_loop_iteration(action="stopped")` whose `reason ∈ trigger-set` → `halted`. No new kind, but **violates AC-1**, which explicitly requires `kind=stop_triggered` in the journal. Rejected.

- **D3 — Resolution semantics for resume (AC-3 "deletes the file OR marks it resolved").** The "marked resolved" marker is undefined anywhere in the artifacts.
  - **(a) Deletion is canonical; "marked resolved" ≡ the file no longer present at `open_clarification.md`.** 4.2 detects presence; resolution = absence. This matches Story 4.11's reversal contract, which **recreates** `open_clarification.md` (epics.md:2340) — i.e., presence/absence is the canonical lifecycle. Simplest, fewest moving parts, and the resume cell is a clean delete-then-rerun. **(Recommended.)**
  - **(b) Define an in-file `status: resolved` frontmatter marker** that 4.2 reads to treat the file as resolved-but-present. Adds content-parsing (against C5's existence-only posture) and a second resolution path to test.
  - **(c) `resolved/` rename convention** (move the file into a sibling resolved dir). More filesystem choreography; still reducible to "no `open_clarification.md` at the active path."

- **D4 — Multiple open clarifications + the singular `target`.** AC-1 journals `target=<path>` (singular) but N>1 clarifications are possible (dashboard supports up to 7; AC-2 says "files", plural). NFR-REL-5 (pure-fn-of-disk) requires a **deterministic** choice.
  - **(a) Halt on the first by lexical `<id>` ordering; `target` = that path.** Deterministic across runs (stable resume), matches the singular `target` AC, smallest surface. The remaining open clarifications re-trigger on subsequent runs after the first resolves. **(Recommended.)**
  - **(b) Enumerate all** — `target` = first, plus an `all_targets: [...]` payload list for the dashboard. Richer for 5.19's "one banner per active trigger", but exceeds the singular AC and adds payload surface; defer to the dashboard story unless a panel reviewer wants it now.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

composer

### Debug Log References

### Completion Notes List

- Implemented STOP trigger 1 (open clarification): `OpenClarificationTrigger` detects `open_clarification.md` under `.claude/state/clarifications/*/`, real registry via `stop_registry.py` + `register_stop_trigger` (D1a), loop fired-branch emits `stop_triggered` journal entries (D2a), projection fold maps to `halted`/`stop_reason` (D3a deletion-only resume, D4a first lexical id). Unit + integration 4-cell matrix tests. ADR-028 `stop_triggered` kind registered.

### File List

- `_bmad-output/implementation-artifacts/4-2-stop-trigger-1-open-clarification.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/decisions/ADR-028-journal-kind-taxonomy.md`
- `src/sdlc/engine/auto_loop.py`
- `src/sdlc/engine/stop_clarification.py`
- `src/sdlc/engine/stop_registry.py`
- `src/sdlc/engine/stop_triggers.py`
- `src/sdlc/state/projection.py`
- `tests/integration/stop_triggers/__init__.py`
- `tests/integration/stop_triggers/test_stop_clarification.py`
- `tests/unit/engine/test_stop_clarification.py`

---

## Change Log

- 2026-06-15: dev-story implementation — STOP trigger 1 (open clarification), registry seam, `stop_triggered` journal + projection fold, 4-cell tests; decisions D1(a) D2(a) D3(a) D4(a). Status: review.

- 2026-06-15: Story drafted (create-story) — first Layer-2 STOP trigger of Epic 4 and the **foundational STOP** (4.10 produces the file it detects, 4.11 resolves it). Authored after the Layer-2 precondition was verified: **4.1 `done` + merged to `main`** (flip `2cc8ce4`, merged-before-done R1/R2 satisfied), the `engine/stop_triggers.py` STOP-check interface frozen on `main`, freeze 7/7. Two parallel research subagents (requirements vs architecture/seams) + first-hand verification of every load-bearing seam (`stop_triggers.py` frozen symbols, `auto_loop.py` fired-branch, `projection.py:40–51/68–90/136` fold gap, `state/model.py:34–35` existing fields, `stop_triggered` net-new, `clarification-triager` lookalike). Surfaced 7 binding ground-truth corrections (C1 detect-only scope; C2 the `NotImplementedError` registry stub 4.2 must build; C3 net-new `stop_triggered` kind distinct from `stop_trigger_raised`; C4 the projection fold gap that otherwise yields `idle` not `halted`; C5 zero new wire-format contracts / opaque presence signal; C6 module-boundary + LOC + mock-runtime; C7 first-fired ordering + the unused `state` param + the `clarification-triager` lookalike) and 4 decisions (D1 registry mechanism, D2 halt representation, D3 resolution semantics, D4 multiplicity/ordering). Status: ready-for-dev.

---

### Review Findings (code-review 2026-06-16)

> bmad-code-review — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) + full quality gate. **Verdict:** AC1–AC4 MET, AC5 PARTIAL (work uncommitted), constraints C2–C7 / D2 / D4 MET. **Gate GREEN on every 4.2 file:** ruff format/check, `mypy --strict` (172 files), pytest **3600 passed / 4 skipped**, coverage **88.36% ≥ 87**, freeze **7/7**, LOC ≤ 400 (41/34/45/314/183), module-boundary, `mkdocs --strict`. Triage: **1 decision-needed → resolved to defer (option c), 2 patch (both applied 2026-06-16), 3 defer, 4 dismissed.**

**Decision-needed**

- [x] [Review][Defer] **Halt-stickiness across runs (finalize the 4.1-carried halt representation).** **[Resolved 2026-06-16 → DEFER, option (c); see `deferred-work.md` → CR4.2-W3]** The clarification STOP is consulted **only post-dispatch** (`auto_loop.py:286`, after `dispatch_fn` at `:276`); the no-ready-work path (`auto_loop.py:239-248`) writes `auto_loop_iteration(action="stopped")` → the fold returns `idle` (`projection.py:92-94`), which **clobbers** an earlier `stop_triggered`→`halted` (`projection.py:97-100`) because the fold is last-write-wins, not sticky. Net: if a clarification stays open but the work queue drains on a later run, `state.json` reads `auto_loop_status="idle"` while `open_clarification.md` is still on disk (the 5.19 dashboard would lose the halt banner). Verified at the projection level (`[dispatch, stop_triggered, auto_loop_iteration(stopped)]` → `idle`); in-memory `AutoLoopResult.halted` is correct, only the persisted projection drifts. This is the residual of the 4.1-deferred "Loop-side halt marker" item — 4.2 closed the in-run case (cell 3 proves `halted`); this is the cross-run case. Since 4.2 **freezes the halt representation for siblings 4.3–4.9**, pick the contract: **(a)** make `halted` sticky in the fold (cleared only by an explicit resume/resolve entry — 4.11's surface; also changes `stop_trigger_raised`); **(b)** run `check_stop` on the no-work path too (halt on a still-open clarification with an empty queue — expands *when* every sibling trigger fires, changing the 4.1 post-dispatch contract); **(c) [Recommended]** accept as-is and record as a known consideration for 4.10/4.11 (the lifecycle owners) — no AC covers the unresolved-rerun case (AC3 only covers resolved-rerun), the producer 4.10 isn't built, the in-run halt is correct, and in the real flow the clarified task is blocked (not `done`) so the queue likely does not drain. **Deferred (option c):** owned by the 4.10 (producer) / 4.11 (resolver) lifecycle; siblings 4.3–4.9 inherit 4.2's current non-sticky halt representation.

**Patch**

- [x] [Review][Patch] **Registry test-isolation leak** **[Applied 2026-06-16 — autouse `_reset_stop_trigger_registry` fixture in `tests/conftest.py` snapshots/restores `_extra_triggers`; canary test `test_registry_isolated_after_registration`]** [`src/sdlc/engine/stop_registry.py:15,23-25` + `tests/unit/engine/test_stop_clarification.py:65-66`] — module-global `_extra_triggers` + `register()` has no reset/dedup; `test_register_stop_trigger_no_longer_raises` appends an `OpenClarificationTrigger` that leaks for the rest of the process (no conftest reset — verified). Benign today (leaked trigger idempotent, lower-priority than the tuple default, first-fired short-circuits) but contradicts the ratified D1(a) rationale ("no global reset fixture") and is a latent flake for siblings 4.3–4.9 that register non-idempotent triggers. Fix: autouse fixture snapshotting/restoring `_extra_triggers`. (blind+edge+auditor)
- [x] [Review][Patch] **`register_stop_trigger` accepts non-conforming triggers silently** **[Applied 2026-06-16 — `isinstance(trigger, StopTrigger)` guard in `stop_registry.register()` → fail-loud `TypeError`; test `test_register_stop_trigger_rejects_non_conforming`]** [`src/sdlc/engine/stop_registry.py:23` / `src/sdlc/engine/stop_triggers.py:38-40`] — `StopTrigger` is `@runtime_checkable` but `register()` never checks; a malformed sibling trigger registers fine and crashes later as an opaque `AttributeError` inside `check_all`. Fix: `isinstance(trigger, StopTrigger)` guard → fail-loud `TypeError` at the registration call site. Hardens the seam for 4.3–4.9. (edge)

**Defer**

- [x] [Review][Defer] **`pre-commit run --all-files` red — pre-existing Epic-3 LOC-cap debt** [`tests/unit/adopt/test_{accept,stamp_rollback,driver,symlink_offer,conflict}_mutations.py`] — 5 Epic-3 adopt mutation-test files exceed the 400-LOC cap (1255/829/638/589/573). All pre-existing on HEAD; 4.2 touches none and didn't touch `scripts/` or `.pre-commit-config.yaml`. `boundary-validator` is `pass_filenames: true`, so a real 4.2 commit only checks staged 4.2 files (all pass) → does **not** block 4.2; but CONTRIBUTING §1 `pre-commit run --all-files` is currently red on `main` → relevant to the §7.4 "gate green on main" precondition for the next story. — deferred, pre-existing Epic-3 debt
- [x] [Review][Defer] **AC5 TDD-first ordering not yet provable — work uncommitted** [working-tree only, no commits] — `git log --reverse` can't show `test(4.2)` RED before `feat(4.2)` GREEN; decisions D1(a)/D2(a)/D3(a)/D4(a) ARE recorded in the Change Log. Action: commit TDD-first before merge; the commit-msg gates (Epic-3 retro A1 merged-before-done + fresh-context-review) enforce it. Recurs the 4.1 [LOW] note. — deferred, commit-ceremony action item

**Dismissed (4)** — (B1) TOCTOU on `target`: payload stores the string only, nothing reopens it, pure-fn-of-disk re-checks each iteration; (B2) `target_id=trigger` event-label: defensible, task linkage preserved via `correlation_id`, projection only special-cases `target_id` for `state_mutation`+epic; (B4) `reason` key absent: optional by ADR/design, siblings may set it (`auto_loop.py:119` is the dormant branch); (B5/A4) dispatch-then-halt test ordering: accurately reflects the real post-dispatch STOP contract (not tautological) — the architectural concern is folded into the decision above.
