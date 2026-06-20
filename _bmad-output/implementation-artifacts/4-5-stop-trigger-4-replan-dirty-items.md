# Story 4.5: STOP Trigger 4 — Replan-Dirty Items

**Status:** ready-for-dev

**Epic:** 4 — Auto-Mode & Autonomous Execution (`/sdlc-auto`)
**Layer:** 2 (`docs/sprints/epic-4-dag.md` §3 — one of the 8-story STOP-trigger fan-out; a **vanilla sibling** plugging into the registry seam 4.2 froze)
**Worktree:** `epic-4/4-5-stop-replan-dirty` (owner: Alice, DAG §5:193)
**Critical Path:** **OFF** the critical path — the Epic-4 critical path is `4.1 → 4.2 → 4.10 → 4.11 → 4.12` (DAG §4); 4.5 is a Layer-2 leaf that 4.11 (mad-mode) and 5.19 (dashboard) consume but do not gate on.
**Depends on (all on `main`):** **4.2** — the frozen STOP-trigger registry seam (`engine/stop_registry.py` `_ORDERED_TRIGGERS`, `engine/stop_triggers.py` `StopTrigger`/`StopDecision`/`check_stop`, the `auto_loop.py` `_finish_halted_on_stop_trigger` halt-emit, the `state/projection.py` `stop_triggered`→`halted` fold, the ADR-028 `stop_triggered` kind) — done, merged-before-done R1/R2 on `main` (close-out `e539d5f`). **The dirty seam — Story 2A.19**: `sdlc replan` (`cli/replan_cmd.py`) + `signoff.invalidate_record` + `signoff.compute_state`/`SignoffState.INVALIDATED_BY_REPLAN` + the `replan_invalidated`/`signoff_invalidated` journal kinds (all on `main`).
**Consumed by (downstream):** **4.11** mad-mode must HALT on this STOP (one of "the other 5" non-foundational triggers); **5.19** renders this STOP as a dashboard banner at severity **`warn`** (`epics.md:2819` — `replan_dirty = warn`).

> **Layer-2 precondition — VERIFIED.** 4.5 is **not** Story N.1, so the CONTRIBUTING §7.4 epic-entry gate does **not** re-apply (epic-4 is `in-progress`; the gate cleared at 4.1). The Layer-2 precondition is **"4.1's loop + 4.2's registry seam frozen on `main`"** — **SATISFIED:** 4.1 + 4.2 are both `done` and merged (`2cc8ce4`, then the 4.2 close-out `e539d5f`); `engine/stop_registry.py`, `engine/stop_triggers.py`, `engine/stop_clarification.py`, the `auto_loop.py` generic halt-emit, and the `projection.py` `stop_triggered` fold are all on `main`; `freeze_wireformat_snapshots --check` is 7/7. **Unlike 4.2, this story builds NO machinery** — it is a purely additive sibling (one trigger class + one appended `_ORDERED_TRIGGERS` line + tests). See C1.

---

## Story

As a **user enforcing replan discipline in auto-mode**,
I want **the loop to halt when any item was marked dirty by a `sdlc replan` invocation (Story 2A.19) and has not yet been re-validated**,
so that **auto-mode never proceeds against stale upstream decisions** (PRD **FR21** trigger 4 [prd.md:764]; the loop's resume/perf contracts **NFR-REL-5** [prd.md:840] + **NFR-PERF-6** [prd.md:830] are inherited from 4.1/4.2 and must be preserved).

---

## Acceptance Criteria

> **READ FIRST — binding ground-truth corrections + scope boundaries (verified against the codebase 2026-06-18). These prevent the most likely implementation disasters. Do not skip.**
>
> **(C1) SCOPE — PURELY ADDITIVE; plug into the frozen 4.2 seam, build NOTHING new.** 4.5 is a vanilla Layer-2 sibling. The entire deliverable is: **(i)** a new `src/sdlc/engine/stop_replan_dirty.py` holding **one** `StopTrigger` class; **(ii)** **one** appended line in `engine/stop_registry.py`'s `_ORDERED_TRIGGERS` tuple; **(iii)** a unit test + a 4-cell integration test. **DO NOT** edit `auto_loop.py`, `projection.py`, `stop_triggers.py`, `stop_registry.py` (beyond the one tuple line), `state/model.py`, ADR-028, or any wire-format contract. The halt-emit, the `stop_triggered`→`halted` projection fold, and the ADR-028 `stop_triggered` row were all landed by 4.2 and are **already on `main`** — a fired `StopDecision` flows through them generically (see C3/C4). If you find yourself touching machinery, stop: you have left scope.
>
> **(C2) "DIRTY" IS NOT A `state=dirty` FIELD — it is the signoff `INVALIDATED_BY_REPLAN` state. THIS IS THE #1 DISASTER.** The epics ACs (`epics.md:2128, 2134, 2143`), the DAG worktree row (§5:193), and the PRD all use the shorthand **`state=dirty` / `dirty_items`** — **there is no such field anywhere on disk.** Verified: `grep -rn "dirty" src/` returns **only doc strings in `commands/sdlc-replan.md`**; there is no `dirty` field on `State`, no marker file, no `dirty` journal kind. The **real** representation (Story 2A.19 / 3.5-mapped seam): a "dirty item" is a **signoff phase whose canonical record `.claude/state/signoffs/phase-<N>.yaml` has a non-null `invalidated_at`** — i.e. `signoff.compute_state(phase, repo_root=...)` returns **`SignoffState.INVALIDATED_BY_REPLAN`** (`signoff/states.py:36, 85-86`). `sdlc replan` produces this by calling `invalidate_record` (which sets `invalidated_at` + `invalidated_reason` on the YAML, `records.py:331-390`) and journaling `replan_invalidated` + one `signoff_invalidated` per phase (`cli/replan_cmd.py:111-192`). **The trigger MUST detect dirtiness via `signoff.compute_state`, not a hallucinated field.** "Re-validated"/"clean" (AC3) = the phase is re-signed so `compute_state` returns `APPROVED` again (a fresh canonical record with null `invalidated_at`; `write_record` permits overwriting an invalidated record per `records.py:289-290`).
>
> **(C3) THE HALT IS GENERIC — `auto_loop.py` needs ZERO edits.** Verified: when `check_stop` returns `fired=True`, `run_auto_loop` calls `_finish_halted_on_stop_trigger` (`auto_loop.py:153-178, 287-295`), which generically journals `kind=stop_triggered` with `payload={trigger, target, correlation_id, reason?}` straight from `stop.trigger`/`stop.target`/`stop.reason` via `append_with_seq_alloc` + the event sentinel. It is **trigger-agnostic** — it does not name `open_clarification`. So your trigger only has to **return a well-formed `StopDecision`**; the journal entry and `halted` result fall out for free. **Do not add a replan-specific branch to the loop.**
>
> **(C4) THE PROJECTION FOLD IS GENERIC — `projection.py` needs ZERO edits.** Verified: `_fold_auto_loop_status` (`projection.py:84-101`) and `_halt_reason_from_stop_payload` (`:69-81`) fold **any** `stop_triggered` entry to `("halted", payload["trigger"])` by reading `payload["trigger"]` — not by matching a literal. `stop_triggered` is already in `_KNOWN_KINDS` (`:40-52`) and in the dispatch guard (`:147`). A `stop_triggered` entry with `trigger="replan_dirty"` therefore folds to `auto_loop_status="halted"`, `stop_reason="replan_dirty"` automatically. **Do not extend the fold.** (This is the deliberate inverse of 4.2, which had to *build* the fold; 4.5 *inherits* it.)
>
> **(C5) ADR-028 `stop_triggered` ROW ALREADY EXISTS — NO ADR EDIT, NO NEW JOURNAL KIND.** Verified at `docs/decisions/ADR-028-journal-kind-taxonomy.md:79` — the `stop_triggered` row (source-story **4.2**, payload `trigger, target, reason, correlation_id`) is on `main` (§4 Revision-Log line dated 2026-06-15). Per **ADR-028: REUSE `kind=stop_triggered` with `trigger="replan_dirty"`** — do **NOT** add a new journal kind, do **NOT** add an ADR row. The `stop_triggered` row already covers every Layer-2 trigger generically. `JournalEntry.kind` is a bare `str`, so even if it did need a row there would be no contract/snapshot change — but here there is **no ADR work at all**. **Use the payload key `trigger` (NOT `trigger_kind`)** — the loop's emitter writes `trigger` and the projection fold reads `trigger`; `trigger_kind` is a stale doc-only key on the *adjacent* `stop_trigger_raised` row (4.6's seam) that the emitter never writes — do not copy it.
>
> **(C6) `StopDecision` HAS ONLY 4 FIELDS — pack the dirty set into `target` + `reason`; do NOT add fields.** `StopDecision` is `@dataclass(frozen=True)` with exactly `{fired, trigger, target, reason}` (`stop_triggers.py:16-23`) — **frozen, byte-stable** (C8). It **cannot** hold the `dirty_items=[<list>]` the epics AC names. Per **D1 (recommended)**: set `target` = the **first dirty item id by lexical order** (deterministic for NFR-REL-5, mirroring 4.2's D4 first-by-lexical-id) and `reason` = a human summary listing the dirty items (or their count + ids). The remaining dirty phases re-trigger on subsequent runs after the first is re-signed. Do **not** widen `StopDecision`, and do **not** invent an `all_targets` payload key (that is a 5.19 dashboard concern; defer unless a panel reviewer asks — see D1(b)).
>
> **(C7) DIRTY PHASES ARE ONLY {1, 2}; ENUMERATE THOSE — phase 3 has NO signoff.** Verified: signoff records exist only for phases 1 and 2 (`records.py:55` `_PHASE_DIR_MAP = {1: "01-Requirement", 2: "02-Architecture"}`; `_VALID_RECORD_PHASES = {1, 2}`); `compute_state(3, ...)` returns `AWAITING_SIGNOFF` and logs a warn, never `INVALIDATED_BY_REPLAN` (`states.py:71-80`). So the trigger enumerates phases **`(1, 2)`** (a module constant `_DIRTY_PHASES: tuple[int, ...] = (1, 2)`), calls `compute_state(p, repo_root=repo_root)` for each, and collects those equal to `SignoffState.INVALIDATED_BY_REPLAN`. **Use the phase id (e.g. `"phase-1"`) as the dirty-item id; lexical order puts `phase-1` before `phase-2`** → `target="phase-1"` when phase 1 is dirty. **`compute_state` may raise `SignoffError`** on a malformed record — `plan_invalidations` (`engine/replan.py:76-81`) lets it propagate (fail-loud); the trigger's `check()` is a read on the post-dispatch disk and SHOULD let `SignoffError` propagate the same way (do not swallow it into `fired=False` — a corrupt record must surface, mirroring the 2A.19 posture). Confirm the exact propagation contract in **D2**.
>
> **(C8) MODULE BOUNDARY + LOC + mock-runtime + first-fired ordering.** New code lives in `engine/` — `engine` MAY import `signoff` (proven: `engine/replan.py:15` imports `from sdlc.signoff.states import SignoffState, compute_state`; `signoff` is in `engine.depends_on`, `scripts/module_boundary_table.py`), `state`, `journal`, `ids`, `errors`, `config` — but MUST NOT import `cli`/`dashboard` (gate `scripts/check_module_boundaries.py`). **Import `compute_state`/`SignoffState` from `sdlc.signoff` (the public `__init__` re-exports both, `signoff/__init__.py:18,27,31`) — do NOT reach into `cli/replan_cmd.py`** (that is a forbidden `engine→cli` edge and would re-run the whole replan side-effect). Every new `src/` file is **≤ 400 LOC** (NFR-MAINT-3 gate). Tests run under `SDLC_USE_MOCK_RUNTIME=1` (autouse, `tests/conftest.py`); the trigger is pure-disk so the runtime is immaterial to it, but the loop-integration cells inherit the posture. `check_stop` returns the **FIRST fired** decision across `_ORDERED_TRIGGERS` (`stop_registry.py:33-39`); the priority slot 4.5 occupies is the appended tuple position — establish it explicitly in the registry edit (D3). **ZERO new wire-format (freeze 7/7, Epic-4 D1).**
>
> **(C9) SHARED-FILE MERGE POINT — `_ORDERED_TRIGGERS` (rebase-before-merge).** Stories 4.3–4.8 each append exactly one line to `_ORDERED_TRIGGERS` (`stop_registry.py:13`). This is a small but real merge point across the 8 parallel Layer-2 worktrees — your branch adds one `ReplanDirtyTrigger()` entry; **rebase on up-to-date `main` before merge** so the tuple composes cleanly (CONTRIBUTING §3 linear-merge; mirrors 4.2's C2 freeze discipline). Keep the registry's public symbols byte-stable; the only edit to `stop_registry.py` is the one tuple line + its import.

---

**AC1 — Positive trigger: a replan-dirtied item halts the loop (FR21 trigger 4).** *(epics.md:2128–2135)*
**Given** the auto-loop running and a `sdlc replan --scope=...` was previously invoked (so ≥1 signoff phase is in `INVALIDATED_BY_REPLAN` — see C2),
**When** the next STOP-check runs with one or more items dirty,
**Then** the loop halts with `trigger=replan_dirty` and a `target` = the first dirty item id by lexical order (e.g. `"phase-1"`), and a `reason` summarising the full dirty set (C6 — `StopDecision` is 4-field; `dirty_items=[<list>]` from the AC is surfaced via `target` + `reason`, D1),
**And** the journal records `kind=stop_triggered, trigger=replan_dirty, target=phase-<N>` via the **generic** loop halt-emit (C3 — reusing the existing `stop_triggered` kind, NOT a new kind),
**And** `state.json` reflects `auto_loop_status: halted, stop_reason: replan_dirty` via the **generic** projection fold (C4 — `payload["trigger"]`-driven, zero projection edits),
**And** the user is shown the dirty items and told to re-validate (typically by re-signing the affected phase) — carried by `target`/`reason` for 5.19 to render at severity `warn`.

**AC2 — Negative case: nothing dirty → continue.** *(epics.md:2137–2140)*
**Given** no signoff phase is `INVALIDATED_BY_REPLAN` (including a **missing** `.claude/state/signoffs/` directory or absent canonical records on a greenfield/Phase-3-only project — `compute_state` returns `AWAITING_SIGNOFF`/`APPROVED`, never dirty; treat as "no dirty item", never an error),
**When** the loop iterates,
**Then** STOP-check for trigger 4 returns `StopDecision(fired=False)`,
**And** the loop continues to the next ready item (no `stop_triggered` entry, no halt).

**AC3 — Resume: re-signed → dirty transitions to clean → loop continues (preserves NFR-REL-5).** *(epics.md:2142–2144)*
**Given** the loop halted on this trigger and the user re-signs the affected phase restoring `APPROVED` (a fresh canonical record with null `invalidated_at` — see C2; or the phase stays dirty if signoff fails),
**When** I re-run `/sdlc-auto`,
**Then** the dirty item transitions to `clean` (`compute_state` now returns `APPROVED`), STOP-check for trigger 4 returns `fired=False` for that phase, and the loop continues; if other phases remain dirty, the loop re-halts on the next dirty phase by lexical order (D1),
**And** processing continues from the disk state at resume time (pure-function-of-disk — the resume reads the re-signed filesystem via `compute_state`, no in-memory continuation).

**AC4 — 4-cell test matrix gate (the merge gate).** *(epics.md:2146–2148)*
**Given** the 4-cell test matrix,
**When** `tests/integration/stop_triggers/test_stop_replan_dirty.py` runs (the `tests/integration/stop_triggers/` dir already exists from 4.2 — add the file, reuse `__init__.py`),
**Then** all 4 cells pass: **(1) positive** (a phase dirtied via `invalidate_record` → halt with `stop_reason="replan_dirty"` + a `stop_triggered` journal entry), **(2) negative** (no dirty phase → continue, no `stop_triggered`), **(3) termination state** (`project_from_journal(journal).auto_loop_status == "halted"`, `stop_reason == "replan_dirty"`), **(4) resume** (re-sign the phase → `compute_state` `APPROVED` → `check_stop` `fired=False` → loop continues).

**AC5 — Quality gate green + TDD-first (CONTRIBUTING §1/§2/§5).**
Quality gate green per §1 (ruff format/check, `mypy --strict src/`, pytest **full suite** — not just the new files; the 4.1/4.2 lesson is a partial run hides pre-existing failures — coverage ≥ 87 operational floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` **7/7 unchanged**, module-boundary + LOC ≤ 400). TDD-first (§2): the trigger unit suite + the 4-cell matrix are the failing-first commit, **RED before** `engine/stop_replan_dirty.py` + the `_ORDERED_TRIGGERS` append land, visible in `git log --reverse` (`test(4.5)` → `feat(4.5)`). Material decisions surfaced as **D1/D2/D3** (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the behavior suite — `ReplanDirtyTrigger` Protocol-conformance + dirty-detection via `compute_state` + the 4-cell loop-halt matrix + a registry-integration assertion that `check_stop` fires once the trigger is in `_ORDERED_TRIGGERS`. All RED before `engine/stop_replan_dirty.py` and the registry append land. `test(4.5)` → `feat(4.5)`.

- [ ] **(§5) T0 — Resolve D1/D2/D3** (dirty-set → `target`+`reason` packing · `SignoffError` propagation in `check()` · registry priority slot) and record the choices in the Change Log **before writing code**. Recommended answers are pre-filled in §Decisions; confirm or override.
- [ ] **(AC1–AC4, §2) Write failing trigger + matrix tests FIRST.**
  - `tests/unit/engine/test_stop_replan_dirty.py` — instantiate `ReplanDirtyTrigger()`; assert `isinstance(trigger, StopTrigger)` (mirror `tests/unit/engine/test_stop_clarification.py:26-27`). On a `tmp_path` repo: write an APPROVED phase-1 + phase-2 signoff (reuse the 4.2 idiom `tests/integration/.../test_stop_clarification.py:35-57`), then `invalidate_record(1, repo_root=tmp_path, reason="r", now_utc=...)` → `check(repo_root=tmp_path, state=State())` returns `fired=True, trigger="replan_dirty", target="phase-1"`; with **no** invalidated phase → `fired=False`; with a **missing** signoffs dir → `fired=False`; with **both** phases dirty → `target="phase-1"` (lexical-first, D1); a malformed record → `SignoffError` propagates (D2). RED.
  - `tests/integration/stop_triggers/test_stop_replan_dirty.py` — the **4-cell matrix** driving `run_auto_loop` (clone the structure of `tests/integration/stop_triggers/test_stop_clarification.py`): **(1)** dirty phase → `AutoLoopResult(halted=True, stop_reason="replan_dirty")` + a `stop_triggered` journal entry whose `payload["trigger"]=="replan_dirty"` and `payload["target"]` starts `phase-`; **(2)** no dirty phase → loop continues, no `stop_triggered`; **(3)** termination → `project_from_journal(journal)` yields `auto_loop_status="halted"`, `stop_reason="replan_dirty"`; **(4)** resume → re-sign the phase (overwrite with a fresh APPROVED record / `write_record`), re-run, `check_stop(...).fired is False`. RED.
  - A registry-integration assertion: after the `_ORDERED_TRIGGERS` append, `check_stop(repo_root=<dirty repo>, state=State())` fires with `trigger="replan_dirty"` (proves the slot is wired). RED.
- [ ] **(AC1, AC2, C2, C6, C7) Implement the trigger** — `src/sdlc/engine/stop_replan_dirty.py`: class `ReplanDirtyTrigger` with `trigger_id = "replan_dirty"` and `def check(self, *, repo_root: Path, state: State) -> StopDecision`. Enumerate `_DIRTY_PHASES = (1, 2)`; for each, `compute_state(p, repo_root=repo_root)`; collect phases where the result `== SignoffState.INVALIDATED_BY_REPLAN`; if none → `StopDecision(fired=False)`; else `target=f"phase-{dirty[0]}"` (lexical-first via sorted phase ints → `phase-1` < `phase-2`), `reason` = a summary listing the dirty phase ids (D1). `_ = state` (the trigger reads disk via `compute_state`, not the pre-dispatch snapshot — mirrors 4.2's C7). ≤ 400 LOC (this file is ~40-60 LOC).
- [ ] **(AC1, C8, C9, D3) Append to the registry** — add `ReplanDirtyTrigger()` to `engine/stop_registry.py` `_ORDERED_TRIGGERS` (`:13`) at the agreed priority slot (D3) + the `from sdlc.engine.stop_replan_dirty import ReplanDirtyTrigger` import. **This is the ONLY edit to `stop_registry.py`.** Keep public symbols byte-stable. Rebase on up-to-date `main` before merge (C9).
- [ ] **(C3, C4, C5) VERIFY no machinery edits are needed** — confirm by running the integration cells that the **unmodified** `auto_loop.py` halt-emit (C3), `projection.py` fold (C4), and existing ADR-028 `stop_triggered` row (C5) carry a `replan_dirty` decision end-to-end. If any cell forces an edit to those files, re-read C1 — the decision is almost certainly malformed (wrong payload key, widened `StopDecision`), not a machinery gap.
- [ ] **(AC3, D1) Resume + multiplicity** — cover the resume cell (re-sign → `APPROVED` → `fired=False`) and an N>1 test: two dirty phases → halt on `phase-1`; re-sign phase 1 → re-run halts on `phase-2`; re-sign phase 2 → `fired=False`, loop continues (deterministic re-trigger for NFR-REL-5).
- [ ] **(AC5, §1) Full quality gate to green** — ruff, `mypy --strict src/`, pytest (full suite, not just the new files), coverage ≥ 87, pre-commit, `mkdocs build --strict`, freeze **7/7** (assert unchanged — you touched no contract), module-boundary + LOC ≤ 400. Run `scripts/check_module_boundaries.py src/sdlc/engine/stop_replan_dirty.py` explicitly (proves the `engine→signoff` import is allowed and no `engine→cli` edge crept in).
- [ ] **(§3) Worktree** — branch `epic-4/4-5-stop-replan-dirty` off up-to-date `main`; rebase before merge (the `_ORDERED_TRIGGERS` shared line, C9).
- [ ] **(§4) Chunked review** — review-A/B/C via the `code-review` workflow once status is `review` (use a different LLM context). Route the dirty-detection contract (D2 `SignoffError` propagation) + the `target`/`reason` packing (D1) through review-B. **Run the full suite during review** (CONTRIBUTING §4.4 / the 4.1–4.2 lesson — layer reviews only diff the change).

---

## Dev Notes

### Substrate map (verified 2026-06-18 — exact symbols; wrong names break the build)

| Concern | Symbol / path | Notes |
|---|---|---|
| **frozen STOP result** | `engine.stop_triggers.StopDecision` (`stop_triggers.py:16–23`) | `@dataclass(frozen=True)`; `fired: bool`, `trigger/target/reason: str \| None`. **Byte-stable** (C8). 4.5 returns `StopDecision(fired=True, trigger="replan_dirty", target="phase-1", reason=<summary>)`. **Only 4 fields — pack the dirty set into `target`+`reason`** (C6/D1). |
| **frozen STOP Protocol** | `engine.stop_triggers.StopTrigger` (`:26–32`) | `@runtime_checkable`; `trigger_id: str` + `check(self, *, repo_root: Path, state: State) -> StopDecision`. 4.5's class must satisfy `isinstance(...)` (mirror `tests/unit/engine/test_stop_clarification.py:26-27`). |
| **registry append point** | `engine.stop_registry._ORDERED_TRIGGERS` (`stop_registry.py:13`) | `tuple[StopTrigger, ...]` — **APPEND one `ReplanDirtyTrigger()` line + its import (`:7` neighbour)**. `check_all` returns first-fired (`:33-39`). The ONLY `stop_registry.py` edit. Shared with 4.3–4.8 → rebase-before-merge (C9). Autouse reset fixture `_reset_stop_trigger_registry` already in `tests/conftest.py` (4.2 review P1). |
| **the dirty seam (DETECT via this)** | `signoff.compute_state(phase, *, repo_root) -> SignoffState` (`signoff/states.py:39-100`); `SignoffState.INVALIDATED_BY_REPLAN` (`:36`) | **THE dirty signal** (C2). A phase is "dirty" iff `compute_state` returns `INVALIDATED_BY_REPLAN` (canonical record with non-null `invalidated_at`, `:85-86`). Public re-export: `from sdlc.signoff import compute_state, SignoffState` (`signoff/__init__.py:18,27,31`). May raise `SignoffError` on a malformed record (D2). |
| **dirty phases** | `signoff/records.py:55` `_PHASE_DIR_MAP = {1, 2}`; `_VALID_RECORD_PHASES = {1, 2}`; phase 3 has no signoff (`states.py:71-80`) | Enumerate **`(1, 2)`** only (C7). `compute_state(3,...)` → `AWAITING_SIGNOFF`, never dirty. Dirty-item id = `f"phase-{n}"`; lexical `phase-1` < `phase-2`. |
| **how items GET dirty (do NOT call)** | `cli/replan_cmd.run_replan` → `invalidate_record` + `replan_invalidated`/`signoff_invalidated` journal (`replan_cmd.py:111-192`) | The PRODUCER (Story 2A.19). 4.5 only DETECTS the resulting `INVALIDATED_BY_REPLAN` state. **`engine` MUST NOT import `cli`** (C8) — never call `run_replan` from the trigger. In tests, dirty a phase directly via `signoff.invalidate_record(phase, repo_root=..., reason=..., now_utc=...)`. |
| **generic loop halt-emit** | `engine.auto_loop._finish_halted_on_stop_trigger` (`auto_loop.py:153–178`); call site `:287-295`; `check_stop` post-dispatch `:286` | Journals `kind=stop_triggered {trigger, target, correlation_id, reason?}` from the `StopDecision` generically (C3). **ZERO edits.** `check_stop` gets the pre-dispatch `state` (`:236`) but the trigger reads disk → `state` unused. |
| **generic projection fold** | `state.projection._fold_auto_loop_status` (`:84-101`) + `_halt_reason_from_stop_payload` (`:69-81`); `_KNOWN_KINDS` (`:40-52`); dispatch (`:147`) | Folds any `stop_triggered`→`("halted", payload["trigger"])` (C4). `stop_triggered` already in `_KNOWN_KINDS` + dispatch set. **ZERO edits.** |
| **journal kind (REUSE)** | ADR-028 `stop_triggered` row (`ADR-028:79`, source 4.2) | REUSE with `trigger="replan_dirty"` (C5). **No new kind, no ADR edit.** Payload key is `trigger` NOT `trigger_kind` (the latter is `stop_trigger_raised`'s stale doc key). |
| **state fields (exist)** | `state.model.State.auto_loop_status: str = "idle"`, `stop_reason: str \| None = None` (`model.py:34–35`) | From 4.1; folded to `halted`/`replan_dirty` generically. **Reuse — do not re-add, do not add a `dirty` field** (C2). |
| **NOT 4.5's (lookalike)** | `stop_trigger_raised` (`dispatcher/_panel_helpers.py`; ADR-028:78) → **Story 4.6** | The 2A.3 agent-failure seam, payload `trigger_kind`. Distinct kind, distinct owner. Do not touch, do not copy its `trigger_kind` key. |

### The dirty signal — what "dirty" really is (read before implementing the trigger)

- **There is no `state=dirty` field.** `grep -rn "dirty" src/` → only doc strings in `commands/sdlc-replan.md`. The epics ACs / DAG §5:193 use `state=dirty` / `dirty_items` as **conceptual shorthand**. The realised seam (Story 2A.19, mapped by 3.5) is the **`replan` invalidation pattern**: `invalidate_record` + `signoff_invalidated` (+ `replan_invalidated`).
- **Canonical disk representation:** `.claude/state/signoffs/phase-<N>.yaml` (phases 1, 2) with a non-null `invalidated_at` field → `signoff.compute_state(phase)` returns `SignoffState.INVALIDATED_BY_REPLAN`. This is the **pure-disk signal** the trigger reads (mirrors 4.2's pure-disk clarification check; no in-memory state).
- **Journal trail (informational, not the detection path):** `sdlc replan` writes one `replan_invalidated` (scope/downstream) then one `signoff_invalidated` per phase (`replan_cmd.py:118, 173`). 4.5's detection does **not** need to replay the journal — `compute_state` reads the YAML directly, which is simpler and matches `plan_invalidations` (`engine/replan.py:65-83`). (The journal-derived path would also work but is more code; `compute_state` is the established read.)
- **"Clean" / re-validated (AC3):** the phase is re-signed → a fresh APPROVED canonical record (null `invalidated_at`) → `compute_state` returns `APPROVED`. `write_record` explicitly permits overwriting an invalidated record (`records.py:289-290`), so the resume cell can re-sign via `write_record(SignoffRecord(...APPROVED...), repo_root=...)`.

### Why no machinery edits (the 4.2-vs-4.5 contrast)

4.2 was the foundational STOP: it had to **build** the registry, the loop halt-emit, the projection fold, and register the `stop_triggered` kind. 4.5 is a **plug-in**: every one of those is already on `main` and **trigger-agnostic** (C3/C4/C5 verified the genericity by reading the symbols). The single architectural risk is mis-modelling "dirty" (C2) and over-packing `StopDecision` (C6). If an integration cell pushes you to edit `auto_loop.py`/`projection.py`/ADR-028, that is a signal your `StopDecision` payload is malformed — not that the machinery is missing.

### Test idioms (reuse from 4.2 — do not invent)

- **Approved-signoff setup:** `tests/integration/stop_triggers/test_stop_clarification.py:35-57` (`_write_approved_signoffs`) writes phase-1 + phase-2 APPROVED records via `SignoffRecord` + `write_record` + `compute_artifact_hash`. Reuse it, then dirty a phase with `signoff.invalidate_record(phase, repo_root=tmp_path, reason="r", now_utc="2026-06-18T10:00:00.000Z")`.
- **Ready-to-dispatch project:** `_write_phase3_ready_project` (same file, `:60-87`) builds an epic/story/task tree so `resolve_next_action` returns `dispatch_task` and the loop reaches the **post-dispatch** `check_stop` (the STOP fires after dispatch — `auto_loop.py:286`; a project with no ready task halts as `no ready item` before the STOP, so cell 1 needs a dispatchable task). Reuse it — but note it calls `_write_approved_signoffs`, so dirty the phase **after** bootstrapping the project.
- **Journal bootstrap:** `_bootstrap_journal` (`:90-100`) creates `.claude/state/journal.log` + `state.json` + `agent_runs.jsonl`.
- **Loop driving:** `run_auto_loop(tmp_path, journal_path=…, runtime=MockAIRuntime(…), registry=SpecialistRegistry({}), dispatch_fn=AsyncMock(return_value=None), state_path=…, max_iterations=1)`; read entries via `iter_entries`; project via `project_from_journal`.
- **Unit shape:** `tests/unit/engine/test_stop_clarification.py:26-89` is the Protocol-conformance + fire/not-fire + registry-fires template.
- **Mock-runtime autouse + registry-reset autouse:** `tests/conftest.py` sets `SDLC_USE_MOCK_RUNTIME=1` and `_reset_stop_trigger_registry` suite-wide; the trigger is pure-disk but the loop cells inherit both.
- **Resume cell:** pure-fn-of-disk — re-sign the phase on disk (`write_record` a fresh APPROVED record), re-run, assert `fired=False`. Guard with `skipif(win32)` if a cell exercises `_rebuild_state` (inherited win32 `ImportError`; CI matrix is POSIX).

### Project Structure Notes

- **New files:** `src/sdlc/engine/stop_replan_dirty.py` (the trigger, ~40-60 LOC); `tests/unit/engine/test_stop_replan_dirty.py`; `tests/integration/stop_triggers/test_stop_replan_dirty.py`.
- **Modified (ONE line):** `src/sdlc/engine/stop_registry.py` — append `ReplanDirtyTrigger()` to `_ORDERED_TRIGGERS` + its import. **No other src/ or docs/ edits.** (Contrast 4.2, which touched `auto_loop.py`, `projection.py`, `stop_triggers.py`, ADR-028.)
- **Conventions:** every `src/` file ≤ 400 LOC; absolute `from sdlc.X import Y` imports only (relative imports inside `src/sdlc/<module>/` are gate-forbidden, Architecture §1075); `engine` MAY import `signoff` (verified `engine/replan.py:15`) but never `cli` (C8).

### References

- Epic + ACs: `_bmad-output/planning-artifacts/epics.md:2124–2148` (Story 4.5 + the 4 BDD ACs); dashboard severity `replan_dirty = warn` `:2819`.
- Dirty seam (Story 2A.19): `src/sdlc/cli/replan_cmd.py:111–192` (producer — invalidate + journal); `src/sdlc/signoff/states.py:36,39–100` (`SignoffState.INVALIDATED_BY_REPLAN`, `compute_state`); `src/sdlc/signoff/records.py:154–155,289–290,331–390` (`invalidated_at`/`invalidated_reason`, `invalidate_record`, overwrite-on-invalidated); `src/sdlc/engine/replan.py:65–83` (`plan_invalidations` — the established `compute_state`-reads-dirty pattern); `src/sdlc/signoff/__init__.py:18,31` (public re-exports).
- Frozen 4.2 seam (consume, don't rebuild): `src/sdlc/engine/stop_triggers.py:16–46`; `src/sdlc/engine/stop_registry.py:13,33–39` (append point); `src/sdlc/engine/auto_loop.py:153–178,286–295` (generic halt-emit); `src/sdlc/state/projection.py:69–101,147` (generic fold); `docs/decisions/ADR-028-journal-kind-taxonomy.md:79` (`stop_triggered` row — reuse).
- 4.2 story (the gold standard + test idioms): `_bmad-output/implementation-artifacts/4-2-stop-trigger-1-open-clarification.md`; `tests/integration/stop_triggers/test_stop_clarification.py`; `tests/unit/engine/test_stop_clarification.py`.
- Requirements: `_bmad-output/planning-artifacts/prd.md:764` (FR21), `:840` (NFR-REL-5), `:830` (NFR-PERF-6).
- State fields: `src/sdlc/state/model.py:34–35`. Module boundary: `scripts/module_boundary_table.py` (`engine.depends_on` includes `signoff`).
- DAG / decisions: `docs/sprints/epic-4-dag.md` §3 (layers `:129`), §4 (critical path), §5:193 (worktree `epic-4/4-5-stop-replan-dirty`, owner Alice — note its `state=dirty` shorthand is the conceptual label, not a literal field; see C2), D1 (zero new wire-format contracts).
- Inherited (cite, do not fix): **CR4.2-W3** halt-stickiness-across-runs — `_bmad-output/implementation-artifacts/deferred-work.md:761`. Siblings 4.3–4.9 inherit 4.2's non-sticky halt representation; owners are 4.10 (producer) / 4.11 (resolver). 4.5 does **not** address it.
- NOT 4.5's: `src/sdlc/dispatcher/_panel_helpers.py` (`stop_trigger_raised` → Story 4.6); ADR-028:78 (the `trigger_kind` lookalike key).

---

## Decisions Needed

- **D1 — Dirty-set → 4-field `StopDecision` packing (the epics AC names `dirty_items=[<list>]`, but `StopDecision` has only `{fired, trigger, target, reason}`).** N>1 dirty phases are possible (both phase 1 and 2 can be invalidated); NFR-REL-5 (pure-fn-of-disk) requires a **deterministic** choice.
  - **(a) `target` = the first dirty phase by lexical id (`phase-1` before `phase-2`); `reason` = a human summary listing all dirty phase ids (e.g. `"replan-dirty: phase-1, phase-2 awaiting re-signoff"`).** Deterministic across runs (stable resume), matches the singular `target`, smallest surface, mirrors 4.2's D4 first-by-lexical-id determinism. Remaining dirty phases re-trigger on subsequent runs after the first is re-signed (AC3 N>1 path). No new `StopDecision` field, no new payload key. **(Recommended.)**
  - **(b) Add an `all_targets: [...]` payload key** on the `stop_triggered` entry for 5.19's "one banner per active trigger." Richer for the dashboard, but exceeds the singular AC, adds payload surface beyond the ADR-028 `stop_triggered` row's documented keys, and 5.19 isn't built. Defer unless a panel reviewer asks for it now.
  - **(c) Widen `StopDecision` with a `targets: tuple[str, ...]` field.** **Rejected** — `StopDecision` is frozen/byte-stable for all of Layer 2 (C8); widening it reopens the 4.2-frozen public shape across 8 siblings.

- **D2 — `SignoffError` propagation in `check()` (a malformed canonical record under `.claude/state/signoffs/`).** `compute_state` raises `SignoffError` on a corrupt/schema-invalid record (`states.py:61`, `records.py:278–282`).
  - **(a) Let `SignoffError` propagate out of `check()` (fail-loud), mirroring `plan_invalidations` (`engine/replan.py:76–81`).** A corrupt signoff record is operator-actionable data corruption — it must NOT be silently demoted to `fired=False` (which would let auto-mode proceed against an unreadable signoff). Consistent with the 2A.19 posture and the framework's fail-loud convention. The loop already surfaces exceptions from `check_stop`. **(Recommended.)**
  - **(b) Catch `SignoffError` → `fired=False`.** Treats a corrupt record as "not dirty" so the loop continues. **Rejected** — masks data corruption, violates fail-loud, and could let stale work proceed; contradicts the established `compute_state` callers.

- **D3 — Registry priority slot (where `ReplanDirtyTrigger` sits in `_ORDERED_TRIGGERS`).** `check_stop` returns first-fired (C8); the slot is the appended tuple position. 4.5 is "STOP Trigger 4" per the epics numbering.
  - **(a) Append after the existing trigger(s) in `_ORDERED_TRIGGERS`, in story order (4.5 after 4.2's `OpenClarificationTrigger`, and after 4.3/4.4 if their lines merge first).** Matches the epics trigger numbering (clarification=1 … replan_dirty=4), keeps priority an explicit reviewable artifact (D1(a) rationale from 4.2), and the rebase-before-merge discipline (C9) composes the 4.3–4.8 batch cleanly. Triggers are mutually exclusive in practice (a dirty phase and an open clarification rarely co-fire in one iteration), so the relative slot is low-stakes, but explicit order beats import-order accident. **(Recommended.)**
  - **(b) Insert at a specific priority ahead of other triggers.** No evidence any trigger must pre-empt `replan_dirty`; adds coordination across worktrees for no benefit. Defer to a panel reviewer if cross-trigger priority becomes load-bearing.

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

- 2026-06-18: Story drafted (create-story) — STOP trigger 4 (replan-dirty items), a **purely additive** Layer-2 sibling plugging into the frozen 4.2 registry seam (no machinery build: zero `auto_loop.py`/`projection.py`/`stop_triggers.py`/ADR-028 edits — reuses the generic halt-emit + `payload["trigger"]` fold + the existing `stop_triggered` kind). Authored after first-hand verification of every load-bearing seam. **Headline ground-truth correction (C2):** there is NO `state=dirty` field on disk — the epics ACs' `dirty_items`/`state=dirty` is conceptual shorthand for the **signoff `INVALIDATED_BY_REPLAN`** state (canonical `.claude/state/signoffs/phase-<N>.yaml` with non-null `invalidated_at`); the trigger detects it via `signoff.compute_state(phase) == SignoffState.INVALIDATED_BY_REPLAN` over phases (1, 2). Surfaced 9 binding corrections (C1 additive scope; C2 the dirty=INVALIDATED_BY_REPLAN finding; C3 generic loop halt-emit / zero auto_loop edits; C4 generic projection fold / zero projection edits; C5 ADR-028 `stop_triggered` row already exists / no ADR edit / use `trigger` not `trigger_kind`; C6 4-field `StopDecision` → pack dirty set into `target`+`reason`; C7 dirty phases only {1,2}, phase-3 has no signoff; C8 module-boundary `engine→signoff` allowed / `engine→cli` forbidden + LOC + first-fired; C9 `_ORDERED_TRIGGERS` shared-line merge point) and 3 decisions (D1 dirty-set packing, D2 `SignoffError` propagation, D3 registry slot). Layer-2 precondition verified: 4.1 + 4.2 done/merged on `main` (close-out `e539d5f`), registry seam frozen, freeze 7/7. Status: ready-for-dev.
