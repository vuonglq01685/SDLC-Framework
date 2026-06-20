# Story 4.4: STOP Trigger 3 — PR-Ready Story

**Status:** done

**Epic:** 4 — Auto-Mode & Autonomous Execution (`/sdlc-auto`)
**Layer:** 2 (`docs/sprints/epic-4-dag.md` §3 — one of the 8-story STOP-trigger fan-out; a *sibling* trigger that plugs into the frozen seam 4.2 landed)
**Worktree:** `epic-4/4-4-stop-pr-ready` (owner: Elena, DAG §5:192)
**Critical Path:** **NOT** on the critical path — the critical path is `4.1 → 4.2 → 4.10 → 4.11 → 4.12` (DAG §4); 4.4 is one of the parallel Layer-2 siblings. It *is* one of "the other 5" STOP triggers that **4.11** (mad-mode) must HALT on (epics.md §4.11 "respects the other 5 STOP triggers → the loop still halts", DAG §3:118).
**Depends on (all on `main`):** **4.1** — the frozen `engine/auto_loop.py` loop + `engine/stop_triggers.py` STOP-check interface + `State.auto_loop_status`/`stop_reason` fields (done, merged `2cc8ce4`). **4.2** — the **real registry seam** (`engine/stop_registry.py` `_ORDERED_TRIGGERS` + `register_stop_trigger`), the **generic halt-emit** (`auto_loop.py:_finish_halted_on_stop_trigger`), the **`stop_triggered` journal kind** (ADR-028:79), and the **projection fold** (`projection.py:97-100`) — all done/merged, close-out `e539d5f`. Epic 1 substrate — `scan` (1.17), `state.projection.project_from_journal` (1.12), `ids.clock` (1.6), `MockAIRuntime` (1.13). **`pr-ready` derivation depends on 2A.16/2A.17 task `stage` machinery (see C1 — a hard correction + dependency).**
**Consumed by (downstream):** **4.11** mad-mode must HALT on this STOP (one of "the other 5"); **5.19** dashboard renders it as a banner (per the 5.x dashboard surface). **4.3–4.8** each append one sibling trigger to the same `_ORDERED_TRIGGERS` tuple (shared merge point — see C2).

> **Layer-2 precondition — VERIFIED.** 4.4 is **not** Story N.1, so the CONTRIBUTING §7.4 epic-entry gate does **not** re-apply (epic-4 is `in-progress`; the gate cleared at 4.1). The Layer-2 precondition is **"4.1's loop + 4.2's registry seam frozen on `main`"** — satisfied: 4.1 and 4.2 are both `done` (merged-before-done R1/R2 satisfied; 4.1 flip `2cc8ce4`, 4.2 close-out `e539d5f`); `engine/auto_loop.py`, `engine/stop_triggers.py`, `engine/stop_registry.py`, `engine/stop_clarification.py`, `state/projection.py` are on `main`; `freeze_wireformat_snapshots --check` is 7/7. **This story is PURELY ADDITIVE** — it plugs a new trigger class into the already-built seam (see C-correction below); it does **not** rebuild any machinery.

---

## Story

As a **user wanting human review before publishing a PR**,
I want **the loop to halt when a story reaches PR-ready state (all its tasks `done`, ready for `pr-author` to publish), preserving the loop's resume contract**,
so that **PR creation is always a deliberate, human-acknowledged step in auto-mode** (PRD **FR21** trigger 3; the loop's resume/perf contracts **NFR-REL-5** + **NFR-PERF-6** are inherited from 4.1 and must be preserved).

---

## Acceptance Criteria

> **READ FIRST — binding ground-truth corrections + scope boundaries (verified against the codebase 2026-06-18 by reading real source). These prevent the most likely implementation disasters. Do not skip.**
>
> **(C-correction — THE BIG ONE: this story is PURELY ADDITIVE; do NOT rebuild the seam.)** 4.2 already built the shared mechanism: `engine/stop_registry.py` (`_ORDERED_TRIGGERS` tuple + `register()` with the `isinstance(StopTrigger)` guard + autouse reset fixture `tests/conftest.py:64`), the generic loop halt-emit `auto_loop._finish_halted_on_stop_trigger` (`auto_loop.py:153-178`, runs post-dispatch at `:286-295` off the StopDecision), the `stop_triggered` journal kind (ADR-028:79, payload `trigger, target, reason, correlation_id`), and the projection fold (`projection.py:97-100` folds `stop_triggered` → `auto_loop_status="halted", stop_reason=payload["trigger"]`). **A vanilla trigger needs ZERO edits to `auto_loop.py`, `projection.py`, `stop_triggers.py`, or ADR-028.** 4.4's entire surface is: **(1)** new `src/sdlc/engine/stop_pr_ready.py` (one `StopTrigger` class), **(2)** ONE appended line in `_ORDERED_TRIGGERS` (story-number order, after `OpenClarificationTrigger()`), **(3)** a unit test + a 4-cell integration test. No new journal kind, no new wire-format, no machinery build. **If you find yourself editing `auto_loop.py` or `projection.py`, STOP — you've misread the seam.**
>
> **(C1) `pr-ready` IS NET-NEW — IT DOES NOT EXIST ON DISK OR IN CODE; 4.4 must DERIVE it. (Hard correction + dependency.)** `grep -rni 'pr.ready|pr_ready|published' src/ tests/` → **zero hits** (verified). There is **no** `pr-ready` story state value anywhere. The only durable per-item state on disk is the **task `stage`** field: `pending | write-tests | write-code | review | done` (`_TaskEntry.stage`, `cli/_epic_story_models.py:87`; the stage machine `pending→write-tests→write-code→review→done` lives in `cli/_task_pipeline.py:64`). The `_StoryEntry.status` field (`pending|in-progress|done`, `_epic_story_models.py:60`) is declared **`exclude=True`** — it is **never serialized to the story JSON** — and its canonical writer (Story **2A.18** `/sdlc-next`) is explicitly noted as **not yet built** (`_epic_story_models.py:56-60`: *"Story 2A.18 (/sdlc-next) will be the canonical writer; until then, manual edit"*). **Therefore there is NO durable `status: pr-ready` marker to read.** The DAG itself encodes the intended derivation: *"story `pr-ready` state from 2A.16/2A.17 task completion"* (DAG §5:192). **4.4 must DERIVE pr-ready = every task belonging to a story is at `stage == "done"`** (see **D1** for the exact predicate and the story-grouping mechanics). This is the same "all tasks of a story done" predicate `next_selector._select_phase3_task` already uses internally (`next_selector.py:116,135` — `stage == "done"`); reuse that logic shape, do not reinvent a `status` field that does not exist. **Flag the 2A.16/2A.17 dependency explicitly in review** (D1): if those stories' task-stage semantics are not as assumed, the derivation predicate must adjust.
>
> **(C2) THE REGISTRY SEAM IS A SHARED FILE — append exactly one line; do NOT touch the public frozen symbols.** `engine/stop_registry.py:13` `_ORDERED_TRIGGERS` is the composition tuple. 4.4 appends `PrReadyStoryTrigger()` **after** `OpenClarificationTrigger()` in **story-number order** (4.2 first, then 4.3, then 4.4 …). This same tuple is the merge point for **4.3–4.8** — each sibling adds one line. **Rebase-before-merge** (CONTRIBUTING §3) keeps the merge trivial (one-line additions in a stable, reviewed order — the same discipline 4.2's C2 established). Keep the PUBLIC symbols byte-stable: the `StopDecision` field set (`stop_triggers.py:16-23`), the `StopTrigger` Protocol shape (`:26-32`), and `check_stop`/`register_stop_trigger` signatures (`:38-45`) are **frozen** for Layer 2 (DAG §3) — your trigger class only needs to satisfy `isinstance(..., StopTrigger)` (i.e. expose `trigger_id: str` + `check(self, *, repo_root: Path, state: State) -> StopDecision`). Do **not** edit `stop_triggers.py`.
>
> **(C3) REUSE the `stop_triggered` journal kind with `trigger="pr_ready_story"` — add NO new kind, NO new ADR-028 row.** AC1 requires the halt to journal `trigger=pr_ready_story, story=<id>`. The generic `auto_loop._finish_halted_on_stop_trigger` already writes `kind=stop_triggered {trigger, target, reason?, correlation_id}` from your returned `StopDecision` (via `append_with_seq_alloc` + the `_EVENT_SENTINEL` `before_hash=None`/`after_hash="sha256:"+"0"*64`). ADR-028:79 already registers `stop_triggered` (added by 4.2). **Do not add a `pr_ready_story` kind, do not add an ADR-028 taxonomy row, do not add a Revision-Log line** — `stop_triggered` is the umbrella kind and `payload["trigger"]` discriminates. (Contrast 4.2, which *introduced* `stop_triggered`; 4.4 merely *reuses* it.)
>
> **(C4) `StopDecision` HAS ONLY 4 FIELDS — map the epics' `story=<id>` onto `target`, the suggested action onto `reason`.** `StopDecision(fired, trigger, target, reason)` (`stop_triggers.py:16-23`) — frozen, no `story` field (C2). The epics phrase the AC as `trigger=pr_ready_story, story=<id>` (epics.md:2108) and "show the suggested next action `/sdlc-publish-pr <story-id>`" (epics.md:2109). Map them: **`trigger="pr_ready_story"`**, **`target=<story-id>`** (the story id string — NOT a path; this is the legitimate divergence from 4.2, whose `target` was a file path), **`reason="/sdlc-publish-pr <story-id>"`** (the suggested next action — `pr-author` is the resolver, `src/sdlc/agents/phase3/pr-author.md` exists). The journal then records `trigger=pr_ready_story`, `target=<story-id>`, `reason=/sdlc-publish-pr <story-id>` generically. Do **not** add a `story` field to `StopDecision`. **Surface the target/reason mapping as a Decision** (D2) — it's the one shaping call.
>
> **(C5) THE PRE-DISPATCH SNAPSHOT CAVEAT IS LOAD-BEARING — re-scan disk inside `check()`, do NOT trust the passed `state`.** `auto_loop.py:236` computes `state = scan(repo_root)` **before** `dispatch_fn` (`:276`), and `check_stop(repo_root=..., state=state)` at `:286` receives that **PRE-dispatch** snapshot. A story becomes pr-ready precisely when the **last** task transitions to `stage="done"` — and that transition happens **inside** `dispatch_fn` (the `review→done` advance, `_task_pipeline.py:64,280-319`). So the pre-dispatch `state.tasks` will **still show the just-completed task as not-`done`** → trusting `state` would make the trigger fire one iteration late or never. **`PrReadyStoryTrigger.check` MUST re-derive pr-ready by re-reading disk** (call `engine.scanner.scan(repo_root)` itself, or read the task JSONs under `03-Implementation/tasks/<story-id>/` directly) and **must NOT consult the passed `state` param** (`_ = state`, mirroring 4.2's `stop_clarification.py:20`). This is the *exact* scenario the loop's own comment warns about (`auto_loop.py:234-235`: *"a Layer-2 trigger that needs the post-dispatch snapshot must re-scan inside its own `check()`"*). This also preserves NFR-REL-5 (pure-function-of-disk): the decision is a function of the on-disk task stages at `check()` time, not of carried Python state.
>
> **(C6) ZERO new wire-format contracts (Epic-4 D1, DAG §248).** pr-ready is **derived operational state**, not a persisted schema — no `StrictModel`, no `tests/contract_snapshots/v1/` entry, no `src/sdlc/contracts/` edit. `freeze_wireformat_snapshots --check` stays **7/7**. The task JSONs 4.4 reads are the *existing* 2A.16/2A.17 task files (read-only); 4.4 writes nothing to them.
>
> **(C7) MODULE BOUNDARY + LOC + mock-runtime posture.** New code lives in `engine/`. The `engine` allow-set (`scripts/module_boundary_table.py:97-114`) is `depends_on = {errors, ids, state, journal, signoff, dispatcher, hooks, telemetry, workflows, specialists, runtime, config}` and **`forbidden_from = {cli, dashboard}`**. **CRITICAL: `_epic_story_models.py` lives in `cli/` — 4.4 MUST NOT import it** (would break the boundary gate `scripts/check_module_boundaries.py`). Read task JSONs via `engine.scanner.scan` (returns `State.tasks` as raw dicts carrying `stage`) or plain `json.loads` on the disk paths — never via the `cli` models. Every new `src/` file is **≤ 400 LOC** (NFR-MAINT-3 gate). Tests run under `SDLC_USE_MOCK_RUNTIME=1` (autouse, `tests/conftest.py`); the trigger is pure-disk so the runtime is immaterial to it, but the loop-integration cells inherit the posture.
>
> **(C8) FIRST-FIRED ORDERING + INHERITED non-sticky halt (cite, don't fix).** `check_all` returns the **FIRST fired** decision in `_ORDERED_TRIGGERS` order (`stop_registry.py:33-39`). 4.4 sits *after* `OpenClarificationTrigger`, so an open clarification out-prioritizes a pr-ready halt — acceptable (clarification is the foundational STOP). **Inherited from 4.2 (do NOT fix here):** `CR4.2-W3` — the cross-run halt-stickiness gap (a drained queue on a later run can fold `auto_loop_status` back to `idle` while the halt condition persists); owners are **4.10/4.11** (the lifecycle owners), and siblings 4.3–4.8 inherit the current non-sticky halt representation. Do not attempt a fix; note it as inherited.

---

**AC1 — Positive trigger: a story reaching pr-ready halts the loop (FR21 trigger 3).** *(epics.md:2104–2109)*
**Given** the auto-loop running through Phase-3 tasks,
**When** all tasks for a story transition to `done` and the story thereby becomes **pr-ready** (derived — every task of `<story-id>` at `stage="done"`, see C1/D1),
**Then** the next STOP-check detects it and halts the loop with `trigger=pr_ready_story`, `target=<story-id>` (the `story=<id>` of the AC, mapped onto `target` per C4),
**And** the journal records `kind=stop_triggered, trigger=pr_ready_story, target=<story-id>, reason=/sdlc-publish-pr <story-id>` (C3 — REUSED kind via the generic `_finish_halted_on_stop_trigger`; no new kind),
**And** `state.json` reflects `auto_loop_status: halted, stop_reason: pr_ready_story` (C-correction — via the existing projection fold `projection.py:97-100`, **not** any new fold),
**And** the user is shown the suggested next action `/sdlc-publish-pr <story-id>` (surfaced via `StopDecision.reason`, C4).

**AC2 — Negative case: not yet pr-ready → continue.** *(epics.md:2111–2114)*
**Given** stories not yet at pr-ready (at least one task of every story is **not** `done` — including a greenfield project with **no** `03-Implementation/tasks/` directory at all — treat as "no pr-ready story", never an error),
**When** the loop iterates,
**Then** STOP-check for trigger 3 returns `StopDecision(fired=False)`,
**And** the loop continues processing tasks (no `stop_triggered` entry for `pr_ready_story`, no halt on this trigger).

**AC3 — Resume: published/advanced → loop continues (preserves NFR-REL-5).** *(epics.md:2116–2119)*
**Given** the loop halted on this trigger and the user reviews + runs the publish action (or otherwise advances the story past pr-ready — see **D3** for the canonical resume semantics),
**When** I re-run `/sdlc-auto`,
**Then** the loop resumes; STOP-check for trigger 3 now returns `fired=False` for that story,
**And** the loop continues to the next story (pure-function-of-disk — the resume re-derives pr-ready from the resolved on-disk task/story state, no in-memory continuation).

**AC4 — 4-cell test matrix gate (the merge gate).** *(epics.md:2121–2123)*
**Given** the 4-cell test matrix,
**When** `tests/integration/stop_triggers/test_stop_pr_ready.py` runs (the dir already exists from 4.2),
**Then** all 4 cells pass: **(1) positive** (all tasks `done` → halt with `stop_reason="pr_ready_story"`), **(2) negative** (a task not `done` → continue), **(3) termination state** (`project_from_journal(journal)` yields `auto_loop_status="halted", stop_reason="pr_ready_story"` via the existing fold), **(4) resume** (story advanced past pr-ready → loop continues, `fired=False`).

**AC5 — Quality gate green + TDD-first (CONTRIBUTING §1/§2/§5).**
Quality gate green per §1 (ruff format/check, `mypy --strict src/`, **FULL** pytest suite, coverage ≥ 87 operational floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` **7/7 unchanged**, module-boundary + LOC ≤ 400). Run the **full** pytest suite, not just the new files (the 4.1/4.2 lesson: a partial run hides pre-existing/golden regressions). TDD-first (§2): the trigger unit suite (`isinstance` Protocol conformance + positive/negative `check()`) + the 4-cell integration matrix are the failing-first commit, **RED before** `engine/stop_pr_ready.py` + the `_ORDERED_TRIGGERS` append land, visible in `git log --reverse` (`test(4.4)` → `feat(4.4)`). Material decisions surfaced as **D1/D2/D3** (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the behavior suite — `PrReadyStoryTrigger` Protocol conformance + the pr-ready derivation (`check()` positive/negative, re-reading disk per C5) + the 4-cell loop-halt matrix. All RED **before** `engine/stop_pr_ready.py` and the one-line `_ORDERED_TRIGGERS` append land. `test(4.4)` → `feat(4.4)` in `git log --reverse`.

- [x] **(§5) T0 — Resolve D1/D2/D3** (pr-ready derivation predicate + story-grouping · `target`/`reason` mapping · resume semantics) and record the choices in the Change Log **before writing code**. Recommended answers are pre-filled in §Decisions; confirm or override. **Explicitly flag the 2A.16/2A.17 task-stage dependency** (D1) in T0.
- [x] **(AC1–AC4, §2) Write failing trigger + matrix tests FIRST.**
  - `tests/unit/engine/test_stop_pr_ready.py` — instantiate `PrReadyStoryTrigger()`; assert `isinstance(trigger, StopTrigger)` (mirror `tests/unit/engine/test_stop_clarification.py:26-27`). On a `tmp_path` repo, build a story dir with task JSONs (mirror the `_TaskEntry` on-disk shape — `{id, story_id, label, stage, dependencies, ...}`, see `tests/integration/stop_triggers/test_stop_clarification.py:73-86`): `check(repo_root=tmp_path, state=State())` returns `fired=True, trigger="pr_ready_story", target="<story-id>", reason="/sdlc-publish-pr <story-id>"` when **all** tasks of the story are `stage="done"`; `fired=False` when **any** task is not `done`, and `fired=False` when the tasks dir is missing entirely. Add an N>1-story case (D1 ordering: first pr-ready story by lexical id). Assert the trigger does **not** consult `state` (pass a deliberately-stale `State()` and confirm disk drives the result, C5). RED.
  - `tests/integration/stop_triggers/test_stop_pr_ready.py` (dir already exists from 4.2; add this file) — the **4-cell matrix** driving `run_auto_loop`: **(1)** all tasks `done` → `AutoLoopResult(halted=True, stop_reason="pr_ready_story")` + a `stop_triggered` journal entry with `payload["trigger"]=="pr_ready_story"` and `payload["target"]==<story-id>` (read via `iter_entries`); **(2)** a task not `done` → loop continues, no `pr_ready_story` halt; **(3)** termination → `project_from_journal(journal)` yields `auto_loop_status="halted", stop_reason="pr_ready_story"`; **(4)** resume → advance the story past pr-ready (D3), re-run, `fired=False` / loop continues. Reuse the `_write_phase3_ready_project` / `_bootstrap_journal` idioms from `test_stop_clarification.py`. RED. **Mind C5:** to make cell 1 fire deterministically with a stubbed `dispatch_fn` (AsyncMock that does not actually advance the task), seed the task JSON as already `stage="done"` on disk so the post-dispatch re-scan inside `check()` sees pr-ready — the integration test asserts the **trigger→halt→journal→projection** wiring, not the dispatcher's stage-advance (which 2A.17 owns and tests).
- [x] **(AC1, AC2, C1, C4, C5, C7) Implement the trigger** — `src/sdlc/engine/stop_pr_ready.py`: class `PrReadyStoryTrigger` with `trigger_id = "pr_ready_story"` and `def check(self, *, repo_root: Path, state: State) -> StopDecision`. **Re-scan disk** (C5): derive pr-ready = a story all of whose tasks are at `stage="done"` (D1). Group tasks by `story_id` (the task JSON `story_id` field, or the `03-Implementation/tasks/<story-id>/` subdir name — D1). On the first pr-ready story by lexical id, return `StopDecision(fired=True, trigger="pr_ready_story", target=<story-id>, reason=f"/sdlc-publish-pr {story_id}")`. Missing tasks dir / no fully-done story → `fired=False`. `_ = state` (C5). Module-level rel-path constant mirroring `next_selector._TASKS_ROOT_REL = "03-Implementation/tasks"`. **Do NOT import `cli`** (C7). ≤ 400 LOC.
- [x] **(AC1, C2) Register the trigger** — append `PrReadyStoryTrigger()` as **one line** to `_ORDERED_TRIGGERS` in `engine/stop_registry.py:13`, **after** `OpenClarificationTrigger()` (story-number order). Add the import. Keep the public frozen symbols untouched (C2). **No other src edit.**
- [x] **(C-correction — confirm, don't build) Verify the seam needs nothing else.** Confirm by running the integration matrix: NO edit to `auto_loop.py`, `projection.py`, `stop_triggers.py`, or `ADR-028` is required (C3/C-correction). If a test seems to demand one, re-read the seam — you've likely mis-shaped the `StopDecision`.
- [x] **(AC3, D3) Resolution + multiplicity** — implement resume-recognition per **D3** (story advanced past pr-ready ⇒ no longer fires) and deterministic multi-story handling per **D1** (first pr-ready story by lexical id; remaining pr-ready stories re-fire on subsequent runs after the first resolves — deterministic for NFR-REL-5). Cover both in the resume cell + an N>1 unit test.
- [x] **(AC5, §1) Full quality gate to green** — ruff, `mypy --strict src/`, pytest (**full** suite), coverage ≥ 87, pre-commit, `mkdocs build --strict`, freeze **7/7**, module-boundary + LOC ≤ 400. Run `scripts/check_module_boundaries.py src/sdlc/engine/stop_pr_ready.py` explicitly (proves no `cli` import, C7).
- [x] **(§3) Worktree** — branch `epic-4/4-4-stop-pr-ready` off up-to-date `main`; **rebase before merge** (the `_ORDERED_TRIGGERS` one-line append is the only shared-file surface — C2). No registry-seam freeze needed (4.2 already froze it).
- [x] **(§4) Chunked review** — review-A/B/C via the `code-review` workflow once status is `review` (use a different LLM context). Route the **pr-ready derivation predicate (D1)** + the **2A.16/2A.17 task-stage dependency** + the **`target`/`reason` mapping (D2)** + the **C5 re-scan** through review-B. **Run the full suite during review** (CONTRIBUTING §4.4 / the 4.1–4.2 lesson — layer reviews only diff the change).

---

## Dev Notes

### Substrate map (verified 2026-06-18 — exact symbols; wrong names break the build)

| Concern | Symbol / path | Notes |
|---|---|---|
| **frozen STOP result** | `engine.stop_triggers.StopDecision` (`stop_triggers.py:16-23`) | `@dataclass(frozen=True)`; `fired: bool`, `trigger/target/reason: str \| None`. **Byte-stable** (C2). 4.4 returns `StopDecision(fired=True, trigger="pr_ready_story", target=<story-id>, reason="/sdlc-publish-pr <story-id>")` (C4). Only 4 fields — `story` maps onto `target`. |
| **frozen STOP Protocol** | `engine.stop_triggers.StopTrigger` (`:26-32`) | `@runtime_checkable`; `trigger_id: str` + `check(self, *, repo_root: Path, state: State) -> StopDecision`. 4.4's class must satisfy `isinstance(...)` (mirror `test_stop_clarification.py:26-27`). |
| **registry seam (BUILT by 4.2)** | `engine.stop_registry._ORDERED_TRIGGERS` (`stop_registry.py:13`), `ordered_triggers()`, `register()`, `check_all()` | **Append one line** here (C2). `register()` has the `isinstance(StopTrigger)` guard (`:25-29`); `check_all` returns first-fired (`:33-39`). Autouse reset fixture `tests/conftest.py:64-76`. Do NOT rebuild. |
| **generic halt-emit (BUILT by 4.2)** | `engine.auto_loop._finish_halted_on_stop_trigger` (`auto_loop.py:153-178`) → `_append_stop_triggered` (`:133-150`) → `_make_stop_triggered_entry` (`:105-130`) | Journals `kind=stop_triggered {trigger, target, reason?, correlation_id}` from the StopDecision, via `append_with_seq_alloc` + `_EVENT_SENTINEL`. **4.4 writes ZERO auto_loop code** (C-correction). |
| **loop call site (post-dispatch)** | `engine.auto_loop.run_auto_loop` → `check_stop(repo_root, state=state)` (`auto_loop.py:286`) on fire → `_finish_halted_on_stop_trigger` (`:288-295`) | `check_stop` runs **after** `dispatch_fn` (`:276`) with the **PRE-dispatch** `state` snapshot from `scan(repo_root)` (`:236`). **Re-scan inside `check()`** (C5). |
| **pre-dispatch snapshot caveat** | `auto_loop.py:234-235` comment | *"a Layer-2 trigger that needs the post-dispatch snapshot must re-scan inside its own `check()`."* The last-task→`done` advance happens **inside** `dispatch_fn` → the passed `state` is stale for pr-ready. Trigger re-scans disk (C5). |
| **projection fold (BUILT by 4.2)** | `state.projection._fold_auto_loop_status` (`projection.py:84-101`), dispatch (`:147`), `_KNOWN_KINDS` (`:40-52`) | `stop_triggered` already folds → `("halted", payload["trigger"])` **generically** (`:97-100` via `_halt_reason_from_stop_payload :70-72`). `stop_triggered` already in `_KNOWN_KINDS` (`:50`). **No projection edit** (C-correction). |
| **task on-disk shape (the pr-ready source)** | `cli._epic_story_models._TaskEntry.stage` = `Literal["pending","write-tests","write-code","review","done"]` (`_epic_story_models.py:87`); stage machine `cli/_task_pipeline.py:64` (`"review": "done"`) | The durable per-task state. **Read the JSON, NOT the cli model** (C7 — `cli` is forbidden from `engine`). Task files live at `03-Implementation/tasks/<story-id>/T*-*.json`. |
| **`status` field is a TRAP** | `cli._epic_story_models._StoryEntry.status` (`_epic_story_models.py:60`) | `Literal["pending","in-progress","done"]`, **`exclude=True`** → never serialized; writer 2A.18 not built (`:56-60`). **NOT a pr-ready source.** Derive from task stages (C1/D1). |
| **derivation precedent** | `engine.next_selector._select_phase3_task` (`next_selector.py:120-137`), `_deps_satisfied` (`:114-117`) | Already computes "all tasks of a story done" via `task.stage == "done"`. **Reuse this predicate shape** (C1) — same engine module, same `scan`-free disk read pattern (`_load_task` `:62-78`, `_collect_task_index` `:93-111`). |
| **disk reader** | `engine.scanner.scan(repo_root) -> State` (`scanner.py:228`) | Returns `State.tasks` as a `dict[str, dict]` of raw task JSON (carrying `stage`), keyed by canonical task id; `State.stories` similarly. A clean engine-internal disk read — or read the `tasks/<story-id>/` JSONs directly like `next_selector._load_task`. Pick one in D1. |
| **state fields (exist)** | `state.model.State.auto_loop_status: str = "idle"`, `stop_reason: str \| None = None` (`model.py:34-35`); `State.tasks`/`State.stories: dict` (`:30-32`) | From 4.1/1.x. **Reuse — do not re-add.** |
| **journal kind (REGISTERED by 4.2)** | ADR-028:79 `stop_triggered` row (payload `trigger, target, reason, correlation_id`) | **Reuse with `trigger="pr_ready_story"`** — no new row, no Revision-Log line (C3). |
| **resolver (downstream)** | `src/sdlc/agents/phase3/pr-author.md` (exists); `/sdlc-publish-pr` | The suggested next action goes in `StopDecision.reason` (C4). `pr-author` publishes the PR; the publish/advance is the resume signal (D3). 4.4 does NOT implement publish. |
| **NOT 4.4's** | `dispatcher._panel_helpers._emit_stop_trigger` → `kind=stop_trigger_raised` | The 2A.3 agent-failure seam — **Story 4.6** consumes it. Different kind, different owner. Do not touch. |

### The pr-ready signal — what exists vs what 4.4 does (READ before D1)

- **`pr-ready` does not exist on disk or in code** (grep-confirmed: zero hits for `pr.ready|pr_ready|published`). 4.4 is net-new derivation ground. The DAG's own description is the spec: *"story `pr-ready` state from 2A.16/2A.17 task completion"* (DAG §5:192).
- **The only durable signal is the task `stage`.** A task advances `pending → write-tests → write-code → review → done` (`_task_pipeline.py:64`). When the **last** task of a story hits `done`, the story is pr-ready by derivation. The `review→done` advance is what happens inside `dispatch_fn` on the final iteration — hence the C5 re-scan requirement.
- **`_StoryEntry.status` is NOT usable** — `exclude=True` (never written), writer (2A.18) not shipped. Anyone reaching for `story["status"] == "pr-ready"` will read nothing and the trigger will never fire. Derive from task stages.
- **2A.16/2A.17 dependency (flag in review, D1):** the derivation assumes 2A.16 (story/task models) + 2A.17 (task stage machine: `review→done`) define `stage` as the canonical completion marker. Both are upstream of Epic 4; verify the assumption holds. If a story can have **zero** tasks on disk (not yet broken down via `/sdlc-break`), that is **NOT** pr-ready (D1: require ≥1 task AND all `done`) — guard against the empty-set vacuous-truth bug (`all([]) == True`).
- 4.4 reads task JSONs **read-only**; it writes nothing to them (C6). Publishing/advancing is `pr-author`'s job (resume, D3).

### Why the seam needs no machinery (the C-correction, restated for the dev)

4.2 paid the machinery cost. The loop's fired-branch (`auto_loop.py:286-295`) already: consults `check_stop`, and on any `fired` decision calls `_finish_halted_on_stop_trigger` which journals `stop_triggered` from the StopDecision and returns `AutoLoopResult(halted=True, stop_reason=trigger)`. The projection already folds `stop_triggered → halted` reading `payload["trigger"]`. So a new trigger that returns the right `StopDecision` gets halt + journal + projection **for free**. 4.4's only novel logic is *the derivation of pr-ready from disk* — everything downstream of `fired=True` is solved. Prove the wiring end-to-end with the 4-cell matrix (cell 3 = `project_from_journal(...).auto_loop_status == "halted"`).

### Test idioms (reuse from 4.2 — do not invent)

- **Mock-runtime autouse:** `tests/conftest.py` sets `SDLC_USE_MOCK_RUNTIME=1` suite-wide; the registry reset fixture (`:64-76`) isolates `_extra_triggers` per-test (you register nothing at runtime, but the static-tuple append is covered by the integration tests).
- **STOP-interface unit shape:** `tests/unit/engine/test_stop_clarification.py:26-27` is the Protocol-conformance template (`isinstance(PrReadyStoryTrigger(), StopTrigger)`). The disk-fixture + positive/negative `check()` shape is `:30-62`.
- **Phase-3-ready project + journal bootstrap:** `tests/integration/stop_triggers/test_stop_clarification.py:60-100` (`_write_phase3_ready_project(tmp_path, stage=...)`, `_bootstrap_journal`, `_write_approved_signoffs`). The `stage=` param already lets you seed tasks at any stage — set `stage="done"` for the positive cell (C5 note in Tasks).
- **4-cell driving:** `test_stop_clarification.py:115-213` is the cell-1/2/3/4 template (`run_auto_loop(..., max_iterations=1)`, `iter_entries`, `project_from_journal`). Swap the clarification-file setup for task-stage setup; assert `stop_reason="pr_ready_story"` and `payload["trigger"]=="pr_ready_story"`.
- **Resume cell:** pure-fn-of-disk — advance the story past pr-ready on disk (D3), re-run, assert `fired=False`. Guard with `skipif(win32)` if it exercises `_rebuild_state` (inherited win32 `ImportError`; CI matrix is POSIX).
- **New integration FILE (not dir):** `tests/integration/stop_triggers/` already exists (from 4.2) with `__init__.py`; just add `test_stop_pr_ready.py`.

### Project Structure Notes

- **New files:** `src/sdlc/engine/stop_pr_ready.py` (the trigger); `tests/unit/engine/test_stop_pr_ready.py`, `tests/integration/stop_triggers/test_stop_pr_ready.py`.
- **Modified:** `src/sdlc/engine/stop_registry.py` (one-line `_ORDERED_TRIGGERS` append + import — C2). **That is the ONLY production file modified** (C-correction).
- **NOT modified (and must not be):** `auto_loop.py`, `projection.py`, `stop_triggers.py`, `ADR-028`, any `src/sdlc/contracts/` or `tests/contract_snapshots/` file.
- **Conventions:** every `src/` file ≤ 400 LOC; absolute `from sdlc.X import Y` imports only (relative imports inside `src/sdlc/<module>/` are gate-forbidden, Architecture §1075); `engine` never imports `cli`/`dashboard` (C7).

### References

- Epic + ACs: `_bmad-output/planning-artifacts/epics.md:2098-2123` (Story 4.4 + the 4 BDD ACs); `:2108` (`trigger=pr_ready_story, story=<id>`), `:2109` (`/sdlc-publish-pr`).
- Requirements: `_bmad-output/planning-artifacts/prd.md` FR21 (STOP triggers), NFR-REL-5 (resume), NFR-PERF-6 (loop perf).
- Frozen seam (consume, do not rebuild): `src/sdlc/engine/stop_triggers.py:16-45`; `src/sdlc/engine/stop_registry.py` (append point `:13`); `src/sdlc/engine/auto_loop.py:153-178` (generic halt-emit), `:234-236, :286-295` (post-dispatch check + pre-dispatch snapshot caveat); `src/sdlc/state/projection.py:70-101, :147` (existing `stop_triggered` fold).
- pr-ready derivation source: `src/sdlc/cli/_epic_story_models.py:60` (`status` trap, `exclude=True`), `:87` (`_TaskEntry.stage`); `src/sdlc/cli/_task_pipeline.py:64` (`review→done`); `src/sdlc/engine/next_selector.py:114-137` (the "all tasks done" predicate shape to reuse); `src/sdlc/engine/scanner.py:228` (`scan` → `State.tasks`).
- 4.2 precedent (mirror structure): `_bmad-output/implementation-artifacts/4-2-stop-trigger-1-open-clarification.md` (the gold-standard sibling); `src/sdlc/engine/stop_clarification.py` (trigger shape), `tests/unit/engine/test_stop_clarification.py`, `tests/integration/stop_triggers/test_stop_clarification.py`.
- Journal taxonomy (reuse, no new row): `docs/decisions/ADR-028-journal-kind-taxonomy.md:79` (`stop_triggered`); seq-alloc ADR-032.
- Module boundary: `scripts/module_boundary_table.py:97-114` (engine allow-set; `forbidden_from={cli,dashboard}`); gate `scripts/check_module_boundaries.py`.
- DAG / decisions: `docs/sprints/epic-4-dag.md` §3 (layers `:129`), §4 (critical path), §5 (worktree `:192` — *"pr-ready state from 2A.16/2A.17 task completion"*), D1 (zero new contracts).
- Inherited debt (cite, don't fix): `CR4.2-W3` halt-stickiness (`deferred-work.md`) — owners 4.10/4.11.
- Resolver (downstream): `src/sdlc/agents/phase3/pr-author.md` (`/sdlc-publish-pr`).

---

## Decisions Needed

- **D1 — pr-ready derivation predicate + story-grouping + multiplicity (the core of this story).** `pr-ready` is net-new (C1); 4.4 must derive it from task `stage`. Choices: how to group tasks by story, how to define "all done", and how to pick when N stories are pr-ready.
  - **(a) Derive from task `stage` on disk: a story is pr-ready iff it has ≥1 task and every one of its tasks is `stage="done"`; group tasks by the `tasks/<story-id>/` subdir (or the JSON `story_id` field); halt on the first pr-ready story by lexical `<story-id>` order; `target = <story-id>`. Re-read disk inside `check()` (C5); reuse the `next_selector` predicate shape (`stage == "done"`).** Deterministic across runs (stable resume, NFR-REL-5), matches the singular `story=<id>` AC, smallest surface, guards the `all([]) == True` empty-task vacuous-truth bug (require ≥1 task). Remaining pr-ready stories re-fire on subsequent runs after the first resolves. **(Recommended.)**
  - **(b) Read `_StoryEntry.status == "pr-ready"`** — rejected: `status` is `exclude=True` (never serialized), the value `"pr-ready"` is not even in its `Literal`, and the writer (2A.18) does not exist. Would silently never fire (C1).
  - **(c) Enumerate all pr-ready stories** — `target=<first>` plus an `all_stories: [...]` payload for the dashboard. Richer for 5.19, but exceeds the singular `story=<id>` AC and adds payload surface; defer to the dashboard story unless a panel reviewer wants it now.
  - **Dependency to flag (T0 + review-B):** the derivation rests on 2A.16/2A.17 defining `stage="done"` as the canonical task-completion marker (DAG §5:192). If those stories' semantics differ (e.g. a separate story-level "ready" flag ships), the predicate adjusts. Verify before merge.

- **D2 — Mapping the 4-field `StopDecision` onto the epics' `story=<id>` + suggested action.** `StopDecision` has no `story` field (C4, frozen C2).
  - **(a) `trigger="pr_ready_story"`, `target=<story-id>`, `reason="/sdlc-publish-pr <story-id>"`.** The story id is the natural `target` (the thing the halt is "about"); `reason` carries the human-facing next action verbatim, which is exactly what AC1 asks to "show". The journal then records all three generically (C3). Clean, no new fields, satisfies both AC clauses. **(Recommended.)**
  - **(b) `target="/sdlc-publish-pr <story-id>"`, `reason=<story-id>`** — inverts the semantics; `target` should identify the subject (the story), not the command. Rejected.
  - **(c) Add a `story` field to `StopDecision`** — reopens the frozen public dataclass for all 8 siblings (C2 violation); high blast radius. Rejected.

- **D3 — Resume semantics (AC3 "runs the publish action OR marks story as `published`").** The "published" marker is not defined anywhere (mirrors 4.2's D3 ambiguity).
  - **(a) Resume = the story is no longer pr-ready by the same derivation (D1): once `pr-author`/`/sdlc-publish-pr` advances the story past "all-tasks-done" — e.g. the story is archived/removed from the active `tasks/` tree, or a follow-on task is added that is not yet `done`, or the next story's tasks become the ready frontier — `check()` re-derives `fired=False` and the loop continues to the next story.** Presence/absence of the pr-ready condition is the canonical lifecycle (same posture as 4.2's deletion-canonical D3). Simplest; the resume cell is "advance-then-rerun". No content-parsing, no `published` field invented. **(Recommended.)**
  - **(b) Define an on-disk `published: true` marker** that 4.4 reads to suppress the halt while the tasks stay `done`. Adds a net-new persisted marker (against C6's zero-new-wire-format posture) and a second resolution path; defer to the `pr-author`/publish story that would own such a marker.
  - **(c) Journal-based resume** — read a `pr_published` journal entry to suppress re-firing. Couples the trigger to a not-yet-existing journal kind; over-engineered for a pure-fn-of-disk trigger.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

Composer (dev-story workflow)

### Debug Log References

### Completion Notes List

- Implemented `PrReadyStoryTrigger` (D1a/D2a/D3a): derives pr-ready from task `stage=="done"` grouped by `03-Implementation/tasks/<story-id>/`; re-scans disk inside `check()` (C5); `_ = state`.
- Registered in `_ORDERED_TRIGGERS` after `SignoffRequiredTrigger` (story-number order, one-line append + import).
- Unit suite: Protocol conformance, positive/negative/stale-state/multi-story/empty-task guard (8 tests).
- Integration 4-cell matrix: positive halt + journal + projection; negative continue; termination fold; resume after tasks tree removed (D3a). Cells 1/3/4 patch `resolve_next_action` to force dispatch when all tasks done (loop otherwise exits before STOP-check).
- Quality gate green: ruff, mypy --strict, full pytest 3626 passed, freeze 7/7, mkdocs --strict, module-boundary check on `stop_pr_ready.py`. No edits to `auto_loop.py`, `projection.py`, `stop_triggers.py`, or ADR-028 (C-correction confirmed).

### File List

- `src/sdlc/engine/stop_pr_ready.py` (new)
- `src/sdlc/engine/stop_registry.py` (modified — append `PrReadyStoryTrigger`)
- `tests/unit/engine/test_stop_pr_ready.py` (new)
- `tests/integration/stop_triggers/test_stop_pr_ready.py` (new)

---

### Review Findings

_Code review (`bmad-code-review`, 3 adversarial layers: Blind Hunter / Edge Case Hunter / Acceptance Auditor; all at Opus-4.8 capability) — 2026-06-20. **Acceptance Auditor: 16 MET · 2 PARTIAL · 0 NOT MET · 0 VIOLATED** (C-correction + C1–C8 + D1a/D2a/D3a all MET; AC1–AC4 MET with a real, non-tautological 4-cell matrix). Triage: **1 decision-needed · 3 patch · 1 defer · 12 dismissed**. Dismissed = verified false-positives / by-design / sibling-parity: re-halt-on-resume (by-design STOP semantics + inherited CR4.2-W3, D3a MET), `_ = state` discard (sibling idiom `stop_clarification.py:20`/`stop_signoff.py:29`), `target`=dir-name (= canonical story-id, D2a MET), `reason` "injection" (inert journal text, not executed), TOCTOU (atomic writes + safe-direction), symlink story/task dir (read-only, sibling parity, OSError-safe), cross-trigger ordering untested (first-wins structural, tested in 4.2), cell2 selector-coupling (`assert_awaited_once` makes it fail-loud), stale-state/`'Done'`-typo tests (safe-direction, Literal-controlled)._

**Decision-needed:**

- [x] [Review][Decision] Multi-pr-ready tiebreak — lexical (ratified **D1a**) vs `next_selector` seq order — When ≥2 stories are simultaneously pr-ready, `_first_pr_ready_story` returns the first by `sorted(tasks_root.iterdir())` (lexical dir-name), exactly matching ratified **D1a**. But `next_selector` (the engine's own task-ordering authority) orders by parsed `-S(\d{2})-` seq (`next_selector.py:81-83`). They agree for zero-padded seqs within one epic but can diverge across epics. Verified by Edge Case Hunter against real source (rated High in isolation; the implementation nonetheless matches the ratified decision). **RESOLVED 2026-06-20 → option (a) keep lexical** (user call): matches ratified D1a; divergence is narrow (only the rare multi-epic simultaneous-pr-ready state, and the loop halts on the first pr-ready story anyway); the reported target is always a genuinely pr-ready story. No code change. [src/sdlc/engine/stop_pr_ready.py:36-43]

**Patch:**

- [x] [Review][Patch] **APPLIED** — `_read_task_stage` let `UnicodeDecodeError` escape → crashed the STOP check / auto-loop on a corrupt-encoding task file (empirically reproduced: `UnicodeDecodeError` is a `ValueError` subclass, not in the caught `(OSError, json.JSONDecodeError, TypeError)` tuple; the caught `TypeError` was itself unreachable). Fixed → `except (OSError, UnicodeDecodeError, json.JSONDecodeError)`; added `test_check_not_fired_when_task_file_has_invalid_encoding` (RED-before-fix: it crashed; now fail-safe `fired=False`). [src/sdlc/engine/stop_pr_ready.py:60]
- [x] [Review][Patch] **APPLIED** — Glob `T*.json` was broader than the canonical `T*-*.json` used by `next_selector.py:23` (real task files are always `T{nn}-{slug}.json` — `_break_pipeline.py:295`). Tightened to `T*-*.json` for exact parity (spec **C1** "reuse the `next_selector` predicate shape"); added `test_non_task_json_in_story_dir_is_not_counted_as_a_task` (a `TODO.json` stage=done no longer counts). [src/sdlc/engine/stop_pr_ready.py:13]
- [x] [Review][Patch] **APPLIED** — Removed dead `_journal_kinds` helper (defined, never called). [tests/integration/stop_triggers/test_stop_pr_ready.py]

**Defer:**

- [x] [Review][Defer] AC5 TDD-first commit ordering unverifiable while the work is uncommitted [working-tree only] — **RESOLVED 2026-06-20**: `test(4.4)` 97f6282 RED → `feat(4.4)` 336c5ee GREEN verified in `git log --reverse` on main; merged-before-done R1/R2 satisfied; closes CR4.4-W1.

---

## Change Log

- 2026-06-20: **close-out — review → done** — TDD-first commits `test(4.4)` 97f6282 → `feat(4.4)` 336c5ee on main; `docs(4.4)` [fresh-context-review] records bmad-code-review outcome; merged-before-done R1/R2 satisfied (Epic-3 retro A1); CR4.4-W1 closed. Acceptance Auditor 16 MET / 2 PARTIAL / 0 NOT MET / 0 VIOLATED; 1 decision resolved (keep lexical D1a tiebreak), 3 patches applied, 12 dismissed. Gate green: ruff, mypy --strict, full pytest, freeze 7/7, module-boundary. epic-4 stays in-progress; 4.5–4.9 ready-for-dev.
- 2026-06-20: **code-review (`bmad-code-review`, 3 adversarial layers) — STAYS `review`** (gate green locally; flips to `done` only after TDD-first commit + merge per the merged-before-done gate, Epic-3 retro A1). Acceptance Auditor 16 MET / 2 PARTIAL / 0 NOT MET / 0 VIOLATED. Triage 1 decision-needed (→ option a, keep lexical, no code change) / 3 patch APPLIED / 1 defer (CR4.4-W1) / 12 dismissed. Patches: P1 `_read_task_stage` widened `except` to catch `UnicodeDecodeError` (was uncaught → crashed the STOP check on a corrupt-encoding task file; dropped the unreachable `TypeError`) + corrupt-file regression test; P2 tightened the task glob `T*.json` → `T*-*.json` for parity with `next_selector` (spec C1) + non-task-file regression test; P3 removed the dead `_journal_kinds` test helper. Re-verified: ruff format/check clean, mypy --strict clean, 85 passed across `tests/unit/engine/` + `tests/integration/stop_triggers/` (was 12 stop_pr_ready tests → 14 with the +2 new). NOT committed — working-tree only. NEXT: commit TDD-first (`test(4.4)` RED → `feat(4.4)` GREEN → `docs(4.4)` [fresh-context-review]) + merge to main, then flip `done` (closes CR4.4-W1).
- 2026-06-20: dev-story implementation complete — STOP trigger 3 (`pr_ready_story`) purely additive on 4.2 seam; status → review.
- 2026-06-20: T0 decisions resolved (dev-story) — **D1a**: pr-ready = story has ≥1 task and every task `stage=="done"`; group by `03-Implementation/tasks/<story-id>/` subdir; halt on first pr-ready story by lexical `<story-id>`; re-scan disk inside `check()` (C5). **2A.16/2A.17 dependency flagged**: derivation assumes `stage="done"` is canonical task completion from the task pipeline. **D2a**: `target=<story-id>`, `reason="/sdlc-publish-pr <story-id>"`. **D3a**: resume = story no longer pr-ready (e.g. tasks tree removed/archived after publish); presence/absence of pr-ready condition is canonical lifecycle.
- 2026-06-18: Story drafted (create-story) — STOP trigger 3 (pr-ready story), a Layer-2 **sibling** trigger plugging into the registry seam 4.2 already froze on `main`. Authored after the Layer-2 precondition was verified first-hand: **4.1 + 4.2 both `done` + merged** (4.1 flip `2cc8ce4`, 4.2 close-out `e539d5f`), the `engine/stop_registry.py` seam + generic `auto_loop._finish_halted_on_stop_trigger` halt-emit + `stop_triggered` kind (ADR-028:79) + projection fold (`projection.py:97-100`) all on `main`, freeze 7/7. Every load-bearing seam verified by reading real source (`stop_triggers.py`/`stop_registry.py`/`auto_loop.py` frozen symbols, `projection.py` generic fold, `scanner.py`/`next_selector.py` task-stage read pattern, `_epic_story_models.py` task `stage` vs the `status` `exclude=True` trap, module-boundary engine allow-set). **Central verified finding: `pr-ready` is NET-NEW — zero hits for `pr.ready|pr_ready|published` across src/ + tests/; the only durable signal is per-task `stage`, so pr-ready must be DERIVED (all tasks of a story `done`), and the trigger must RE-SCAN disk inside `check()` because the loop passes a PRE-dispatch snapshot while the last-task→`done` advance happens during dispatch.** Surfaced 8 binding corrections (C-correction purely-additive scope; C1 pr-ready net-new + derive-from-task-stage + 2A.16/2A.17 dependency; C2 one-line registry append, public symbols frozen; C3 reuse `stop_triggered` kind, no new ADR row; C4 4-field `StopDecision` → `story` onto `target`; C5 the pre-dispatch snapshot re-scan; C6 zero new wire-format; C7 module-boundary `cli` ban + LOC + mock-runtime; C8 first-fired ordering + inherited non-sticky halt) and 3 decisions (D1 derivation predicate/grouping/multiplicity, D2 target/reason mapping, D3 resume semantics). Status: ready-for-dev.
