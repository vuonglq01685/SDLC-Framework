# Story 2A.18: `/sdlc-next`

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer wanting the framework to pick the next ready item,
I want `/sdlc-next` selecting the highest-priority ready item across phases and either dispatching directly (for Phase 3 tasks) or printing the next slash command,
so that I never have to guess which artifact to advance (FR18).

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1397-1413`. Per ADR-026 §1, the public API surface (`cli/next_.py:run_next`) requires TDD-first commit ordering visible in `git log --reverse`. This story **depends on Story 2A.12** (`compute_state` for signoff-driven phase resolution) per the Epic 2A DAG (`A12 → A18`). It has a documented **soft dependency on Story 2A.17** — `/sdlc-next` auto-dispatches `/sdlc-task` for Phase 3 tasks (AC1, AC3); 2A.17 is a Layer-7 sibling that merges first (see AC3/D2 + Cross-Story Coordination). This story introduces NO new wire-format contracts (ADR-024 snapshot count remains 5) and NO new `JournalEntry.kind` values — `/sdlc-next` is a read-and-route command; it dispatches `/sdlc-task` (whose own journaling applies) or prints, and writes nothing itself.

### AC1 — `/sdlc-next` CLI surface + init guard

**Given** the user invokes `sdlc next`
**When** the CLI runs
**Then** `src/sdlc/cli/next_.py:run_next(*, ctx: typer.Context)` is invoked (no positional arguments)
**And** the project must be initialized (`.claude/state/state.json` present), else `ERR_NOT_INITIALIZED` ("project not initialized at <root>; run `sdlc init` first") with non-zero exit

**And** **AC1/D1 (CLI module name D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** the module is `src/sdlc/cli/next_.py` (trailing-underscore). **Pros**: `next` is a Python builtin; a module named `next.py` shadows it within its own namespace and reads ambiguously; the trailing-underscore convention is already established in this codebase by Story 2A.16's `break_.py`. Consistency. **Cons**: minor — `next` is not a *keyword*, so `next.py` would technically import.
  - **D2:** the module is `src/sdlc/cli/next.py`. **Pros**: matches the slash command `/sdlc-next` more literally. **Cons**: shadows the builtin; diverges from the `break_.py` precedent.

**And** **Recommended: D1** — `cli/next_.py`. The Typer command name is `"next"` (user-facing CLI is `sdlc next`). Document as FIRST line item in PR Change Log.

### AC2 — Phase resolution + ready-item selection

**Given** the project state
**When** `/sdlc-next` runs
**Then** the command resolves the current phase and selects the next ready item per **AC2/D1** below
**And** the resolution consults: Phase 1 + Phase 2 signoff states (`compute_state`), the presence of phase artifacts on disk (`01-Requirement/01-PRODUCT.md`, `02-Architecture/.../ARCHITECTURE.md`, epic/story JSON files), and — for Phase 3 — the task JSON files under `03-Implementation/tasks/`
**And** a selected Phase 3 task is "ready" only when ALL its `dependencies` (other task IDs in the same story batch) are at `stage: done` AND the task itself is at `stage != done`

**And** **AC2/D1 (readiness-source D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** a **phase-aware resolver** computes the next item directly from signoff states + the artifact tree, NOT from a rich `state.json` projection. The resolution ladder (first match wins):
    1. `01-Requirement/01-PRODUCT.md` absent → next item is "start Phase 1", command `/sdlc-start "<idea>"`
    2. Phase 1 signoff `compute_state(1) != APPROVED` → next item is a Phase 1 advance: `/sdlc-research`, `/sdlc-verify`, `/sdlc-epics`, `/sdlc-stories`, or `/sdlc-signoff 1` (pick by which Phase-1 artifacts are missing — see Dev Notes ladder)
    3. Phase 2 signoff `compute_state(2) != APPROVED` → next item is a Phase 2 advance: `/sdlc-ux`, `/sdlc-architect`, or `/sdlc-signoff 2`
    4. Phase 2 `APPROVED` → Phase 3: enumerate task JSON files; select the first task (story `seq` order, then task `seq` order) with all deps `done` and `stage != done`
    **Pros**: works today — `state/projection.py` v1 folds only `epic-<N>` keys, so a `state.json`-driven selector would read an empty `tasks` map; the phase-aware resolver reads the artifacts that actually exist. Matches the FR18 intent ("never guess which artifact to advance"). **Cons**: re-derives phase logic that a future full `state.json` projection would centralize.
  - **D2:** drive selection from `state.json` via `engine.scan`. **Cons**: the v1 projection does not fold story/task state — `state.json["tasks"]`/`["stories"]` are empty; the selector would always report "no ready items".
  - **D3:** build a full task/story/epic projection in this story. **Cons**: scope explosion — that is `EPIC-2A-DEBT-TASK-STATE-PROJECTION` (opened by Story 2A.17), not a `/sdlc-next` deliverable.

**And** **Recommended: D1** — the phase-aware resolver. Document as SECOND line item in PR Change Log. When the full `state.json` projection lands (`EPIC-2A-DEBT-TASK-STATE-PROJECTION`), `/sdlc-next` SHOULD be refactored to consume it — note the refactor target as `EPIC-2A-DEBT-NEXT-CONSUME-PROJECTION`.

### AC3 — Phase 3 task selected → auto-dispatch `/sdlc-task`

**Given** the resolver selects a Phase 3 task (`stage != done`, deps satisfied)
**When** `/sdlc-next` proceeds
**Then** the command auto-dispatches the task by invoking `/sdlc-task <TASK-id>` directly
**And** `/sdlc-next`'s exit code + emitted output reflect the underlying `/sdlc-task` run

**And** **AC3/D1 (auto-dispatch wiring D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** `run_next` imports `sdlc.cli.task.run_task` (deferred import, per Architecture §488) and calls `run_task(ctx=ctx, task_id=<selected>)` in-process. **Pros**: spec-faithful ("dispatches `/sdlc-task <id>` automatically"); preserves the Typer `ctx` (so `--json`/`--no-color` flow through); one process. **Cons**: a Layer-7 intra-batch import — `cli/next_.py` imports `cli/task.py` (both Layer 7). The DAG edge `A12 → A18` does not list 2A.17, so this is a *soft* dependency satisfied by merge ordering (2A.17 < 2A.18).
  - **D2:** `/sdlc-next` does NOT auto-dispatch; it always PRINTS `/sdlc-task <TASK-id>` for the user to run. **Pros**: zero cross-story import; strictly satisfies the DAG. **Cons**: deviates from the AC1/AC3 spec wording "dispatches automatically".
  - **D3:** `subprocess.run(["sdlc", "task", <id>])`. **Cons**: loses `ctx`, slow cold-start, brittle.

**And** **Recommended: D1** — in-process `run_task` call. The soft dependency on Story 2A.17 is documented; the `epic-2a/2a-18-next` worktree rebases onto `main` after `epic-2a/2a-17-task-tdd-pipeline` merges (natural Layer-7 order). Document as THIRD line item in PR Change Log.

> **Dev-order note**: Story 2A.17 (`/sdlc-task`) MUST be `done` and merged to `main` before the `/sdlc-next` worktree implements AC3. If 2A.18 development starts before 2A.17 merges, stub `run_task` behind the import and complete AC3 after the rebase — do NOT ship a `try/except ImportError` fallback (no backwards-compat shims).

### AC4 — Non-Phase-3 item selected → print next slash command

**Given** the resolver selects an item at Phase 1 or Phase 2 (not a Phase 3 task)
**When** `/sdlc-next` proceeds
**Then** the command prints the next slash command to run (e.g. `/sdlc-architect` for the Phase 2 entry, `/sdlc-signoff 1` when all Phase 1 artifacts exist but the phase is unsigned)
**And** the printed line is human-readable on stdout; under `--json` the envelope is `{"command": "next", "next_action": "command", "phase": <N>, "suggested_command": "/sdlc-...", "reason": "<short>"}`
**And** `/sdlc-next` exits 0 (printing a suggestion is a success, not an error)
**And** NO dispatch occurs and NO files are written for the print path

### AC5 — No ready items → print the reason

**Given** no ready item exists (all Phase 3 tasks `done`, or all candidates blocked by unsatisfied dependencies, or a phase is awaiting signoff with no remaining artifact to produce)
**When** `/sdlc-next` runs
**Then** the command prints a reason string enumerating the blockers, e.g. `no ready items: 2 tasks blocked by dependencies, phase 2 awaiting signoff` (this is the placeholder for the Epic 4 STOP system — epics.md AC2 wording)
**And** under `--json` the envelope is `{"command": "next", "next_action": "none", "reason": "<text>", "blockers": {"blocked_by_deps": <N>, "awaiting_signoff": <N>, ...}}`
**And** `/sdlc-next` exits 0 (a fully-advanced project is not an error state)

> The Epic 4 STOP taxonomy (`stop_triggers.py`, 7 triggers) will replace this free-text reason with structured STOP-trigger records. `/sdlc-next`'s `next_action: "none"` envelope is the forward-compatible shape; the `blockers` map is the v1 placeholder.

### AC6 — Slash-command shell + CLI registration + `run_next` ordering

**Given** the architecture canonical tree lists `commands/sdlc-next.md` (`architecture.md:950`)
**When** the dev authors the command surface
**Then** `src/sdlc/commands/sdlc-next.md` is authored (slash-command shell, no positional argument; ≤ 70 LOC; documents the auto-dispatch-vs-print behavior)
**And** NO workflow YAML is authored — `/sdlc-next` dispatches no specialist of its own; it routes to `/sdlc-task` or prints. (`architecture.md:957-963`'s `workflows_yaml/` list correctly omits `sdlc-next.yaml`; `sdlc next` joins `scan`/`trace`/`status` as a non-workflow CLI command.)
**And** NO specialist is authored and `agents/index.yaml` is NOT touched
**And** `@app.command(name="next")` is registered in `cli/main.py` with a deferred import of `run_next` (per Architecture §488)
**And** `run_next(*, ctx)` ordering:
  1. Resolve `repo_root`
  2. Init guard → `ERR_NOT_INITIALIZED` (AC1)
  3. Run the phase-aware resolver (AC2/D1)
  4. If a Phase 3 task is selected → call `run_task(ctx=ctx, task_id=...)` (AC3)
  5. Else if a phase advance is selected → `emit_json`/print the suggested command (AC4)
  6. Else → `emit_json`/print the no-ready-items reason (AC5)
**And** the module LOC budget is ≤ 320; extraction of the resolver into `cli/_next_resolver.py` is permitted if `next_.py` exceeds 220 LOC.

### AC7 — Tier-2 e2e + anti-tautology receipt

**Given** the Tier-2 e2e harness from Story 2A.0 + the `phase2_approved_repo` fixture (Story 2A.15/2A.16/2A.17)
**When** the dev authors the next e2e
**Then** `tests/e2e/pipeline/test_sdlc_next.py` (NEW) covers at minimum:

  1. **Phase 3 auto-dispatch**: tmp repo with Phase 2 `APPROVED` + a `pending` task JSON whose deps are satisfied; invoke `sdlc next`; assert `/sdlc-task` ran (the task stage advanced; a `task_stage_advanced` journal entry exists); exit 0
  2. **Phase 2 print**: tmp repo with Phase 1 `APPROVED`, Phase 2 unsigned, no architecture artifact; invoke `sdlc next`; assert exit 0, stdout/`--json` suggests `/sdlc-architect` (or the correct Phase-2 entry), no dispatch occurs
  3. **No ready items**: tmp repo with all Phase 3 tasks at `stage: done`; invoke `sdlc next`; assert exit 0, `next_action: "none"`, reason text names the fully-advanced state
  4. **Dependency-blocked**: tmp repo with task `T02` depending on `T01` where `T01` is at `stage != done`; invoke `sdlc next`; assert the resolver selects `T01` (not `T02`) — deps gate selection order

**And** **Anti-tautology receipt (AC7 mandatory)**: in an auxiliary executable test, temporarily neutralise the dependency gate in the resolver (make it treat every task as dep-satisfied); re-run scenario 4; observe the inversion — the assertion "`T01` is selected before `T02`" still holds by `seq` order, so instead assert on a fixture where `T02` has lower `seq` than `T01`: with the gate neutralised the resolver wrongly picks `T02`; with the gate active it picks `T01`. Confirm the test fails under neutralisation; revert. Document as `test_e2e_next_dependency_gate_is_load_bearing` in the PR Change Log.

### AC8 — Module boundary + quality gate compliance (CONTRIBUTING.md §1)

**Given** the Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests`
  - `pytest -q -m "not e2e and not property"` — new unit + integration tests green
  - `pytest -q -m e2e` — new `test_sdlc_next.py` + all existing e2e green
  - `python scripts/freeze_wireformat_snapshots.py --check` — `5 contracts match snapshots` (unchanged — no contract edits)
  - `python scripts/check_module_boundaries.py` — 0 new violations (`cli` already depends on `signoff`, `journal`, `state`, `ids`, `errors`; `cli/next_.py` importing `cli/task.py` is an intra-`cli` import, allowed)
  - `mkdocs build --strict` — clean
  - `tests/integration/test_wheel_build.py` — `sdlc-next.md` added to `_ALLOWED_CONTENT_FILES`

## Tasks / Subtasks

> Tasks ordered for TDD-first commits per ADR-026 §1. AC1/AC6 (CLI), AC2 (resolver), AC7 (e2e) are public-API surfaces requiring tests-first commit ordering.

- [ ] **Task 1 — Slash-command shell + CLI registration (AC1, AC6)** — **TDD-first commit 1**
  - [ ] 1.1 Author `src/sdlc/commands/sdlc-next.md` (≤ 70 LOC; document auto-dispatch vs print).
  - [ ] 1.2 Author the `run_next` skeleton in `src/sdlc/cli/next_.py` (init guard only; resolver call stubbed).
  - [ ] 1.3 Register `next_command` in `cli/main.py` (deferred import).
  - [ ] 1.4 Author `tests/unit/cli/test_next_command.py` — assert the command is registered, init guard fires `ERR_NOT_INITIALIZED`. Tests fail (red) → implement → pass (green).
  - [ ] 1.5 Document AC1/D1, AC2/D1, AC3/D1 as FIRST/SECOND/THIRD line items in the PR Change Log.

- [ ] **Task 2 — Phase-aware resolver (AC2, AC4, AC5)** — **TDD-first commit 2**
  - [ ] 2.1 Author `tests/unit/cli/test_next_resolver.py`:
    - PRODUCT.md absent → suggests `/sdlc-start`
    - Phase 1 unsigned, artifacts present → suggests `/sdlc-signoff 1`
    - Phase 2 unsigned, no architecture artifact → suggests `/sdlc-architect`
    - Phase 2 `APPROVED`, a `pending` dep-satisfied task → selects that task
    - Phase 2 `APPROVED`, `T02` deps on non-`done` `T01` → selects `T01`
    - all tasks `done` → no-ready-items reason
    Tests fail (red).
  - [ ] 2.2 Implement the resolver in `cli/_next_resolver.py` (pure function: `resolve_next(repo_root) -> _NextDecision`). `_NextDecision` is a private dataclass/model: `{kind: Literal["dispatch_task","run_command","none"], task_id, command, phase, reason, blockers}`.
  - [ ] 2.3 Tests pass (green).

- [ ] **Task 3 — `run_next` wiring: dispatch / print / reason (AC3, AC4, AC5, AC6)** — **TDD-first commit 3**
  - [ ] 3.1 Author `tests/unit/cli/test_next_command.py` additions:
    - resolver returns `dispatch_task` → `run_task` is called with the selected id (assert via patch/spy)
    - resolver returns `run_command` → suggested command printed; exit 0; no dispatch
    - resolver returns `none` → reason printed; exit 0
    - `--json` envelopes for all three branches per AC4/AC5
    Tests fail (red).
  - [ ] 3.2 Implement the `run_next` body wiring `resolve_next` → `run_task` / `emit_json` / print. Use a deferred `from sdlc.cli.task import run_task` import inside the dispatch branch (AC3/D1). Tests pass (green).
  - [ ] 3.3 Integration test `tests/integration/test_sdlc_next.py`: tmp repo at each phase boundary; assert `run_next` routes correctly end-to-end.

- [ ] **Task 4 — Tier-2 e2e + anti-tautology receipt (AC7)** — **TDD-first commit 4**
  - [ ] 4.1 Reuse `phase2_approved_repo` from `tests/e2e/pipeline/conftest.py`.
  - [ ] 4.2 Author `tests/e2e/pipeline/fixtures/next/` (phase-boundary fixtures + a dep-ordered task set).
  - [ ] 4.3 Author `tests/e2e/pipeline/test_sdlc_next.py` (4 scenarios per AC7).
  - [ ] 4.4 Run targeted Tier-2 e2e: all scenarios green.
  - [ ] 4.5 **Anti-tautology receipt (AC7 mandatory)**: neutralise the dependency gate; confirm `test_e2e_next_dependency_gate_is_load_bearing` fails; revert; document in the PR Change Log.

- [ ] **Task 5 — Module boundary + quality gate + Change Log (AC8)**
  - [ ] 5.1 Run `python scripts/check_module_boundaries.py` — confirm no new edges required.
  - [ ] 5.2 Add `sdlc-next.md` to `tests/integration/test_wheel_build.py:_ALLOWED_CONTENT_FILES`.
  - [ ] 5.3 Run the full quality gate; record the baseline.
  - [ ] 5.4 Author the PR Change Log with D-decisions FIRST/SECOND/THIRD, the anti-tautology receipt, debt citations.

## Dev Notes

### The phase-aware resolution ladder (AC2/D1)

```
resolve_next(repo_root) -> _NextDecision
  ├── 1. if not (01-Requirement/01-PRODUCT.md).exists():
  │        → run_command  /sdlc-start "<idea>"     reason="phase 1 not started"
  ├── 2. if compute_state(1) != APPROVED:
  │        Phase-1 artifact ladder (first missing wins):
  │        ├── no epic JSONs under 01-Requirement/04-Epics/        → /sdlc-epics
  │        ├── an epic with no story JSONs under 05-Stories/<id>/  → /sdlc-stories <EPIC-id>
  │        └── all Phase-1 artifacts present, phase unsigned       → /sdlc-signoff 1
  ├── 3. if compute_state(2) != APPROVED:
  │        ├── no 02-Architecture/.../ARCHITECTURE.md              → /sdlc-architect
  │        └── architecture present, phase unsigned                → /sdlc-signoff 2
  └── 4. compute_state(2) == APPROVED  → Phase 3:
           enumerate 03-Implementation/tasks/<STORY-id>/T*-*.json
           order by (story seq, task seq)
           pick first task where stage != "done" AND every dep task stage == "done"
           ├── found      → dispatch_task <TASK-id>
           ├── none (all done) → none, reason="all tasks complete"
           └── none (all blocked) → none, reason="N tasks blocked by dependencies"
```

The resolver is a **pure function of disk state** — no writes, no journal. It reads signoff state via `compute_state` and globs the artifact tree. Mirror the read-only posture of `cli/scan.py` / `cli/status.py`.

### Why the phase-aware resolver, not `state.json`

`state/projection.py` v1 folds only `state_mutation` entries with `epic-<N>` target IDs into `state.json["epics"]`; `["stories"]` and `["tasks"]` stay empty (see the module docstring — "Other patterns (story-, task-) are reserved for later stories"). A `state.json`-driven `/sdlc-next` would therefore always see an empty task map and report "no ready items". The phase-aware resolver reads the artifacts that exist on disk *today*. When `EPIC-2A-DEBT-TASK-STATE-PROJECTION` (Story 2A.17) lands the task projection, `/sdlc-next` should be refactored to consume `state.json` — tracked as `EPIC-2A-DEBT-NEXT-CONSUME-PROJECTION`.

### Task readiness + dependency gate (AC2, AC7)

A Phase 3 task is "ready" when `task.stage != "done"` AND every id in `task.dependencies` resolves to a task whose JSON file has `stage == "done"`. Load each task JSON as `_TaskEntry` (Story 2A.16/2A.17 widened model — `stage` is the 5-state Literal). Selection order: sort candidate tasks by `(story_seq, task_seq)` from `parse_task_id`, pick the first ready one. The dependency gate is what the AC7 anti-tautology receipt proves load-bearing.

### Auto-dispatch (AC3/D1)

```python
def run_next(*, ctx: typer.Context) -> None:
    root = _get_repo_root_or_cwd()
    # ... init guard ...
    decision = resolve_next(root)
    if decision.kind == "dispatch_task":
        from sdlc.cli.task import run_task   # deferred; soft dep on Story 2A.17
        run_task(ctx=ctx, task_id=decision.task_id)
        return
    if decision.kind == "run_command":
        emit_json("next", {"next_action": "command", "phase": decision.phase,
                           "suggested_command": decision.command, "reason": decision.reason}, ctx=ctx)
        return
    # decision.kind == "none"
    emit_json("next", {"next_action": "none", "reason": decision.reason,
                       "blockers": decision.blockers}, ctx=ctx)
```

`run_task` raises `typer.Exit` on failure (via `emit_error`); `/sdlc-next` does not catch it — the underlying exit code surfaces. This is intentional: `/sdlc-next` is a transparent router.

### Why `cli/next_.py` (AC1/D1)

`next` is a Python builtin, not a keyword — `import sdlc.cli.next` would work but shadows the builtin inside that module and reads ambiguously. Story 2A.16 set the trailing-underscore precedent with `break_.py` (there, `break` IS a keyword). For consistency and clarity, `next_.py`. The Typer command name stays `"next"` → user-facing CLI `sdlc next`.

### Cross-Story Coordination

- Story 2A.12 (DEPENDENCY, per DAG `A12 → A18`) — `compute_state` drives Phase 1/2 resolution
- Story 2A.17 (SOFT DEPENDENCY — Layer-7 sibling) — `/sdlc-next` imports `run_task`; 2A.17 merges to `main` before the `epic-2a/2a-18-next` worktree implements AC3. The DAG omits this edge because 2A.17 + 2A.18 are the same layer; merge ordering (2A.17 < 2A.18) resolves it.
- Story 2A.16 (DEPENDENCY) — task JSON file layout `03-Implementation/tasks/<STORY-id>/T<NN>-<slug>.json`; `_TaskEntry` model; `parse_task_id`
- Story 2A.8–2A.15 — the slash commands `/sdlc-next` suggests (`/sdlc-start`, `/sdlc-epics`, `/sdlc-stories`, `/sdlc-architect`, `/sdlc-signoff`)
- **Layer-7 sibling coordination**: Stories 2A.17, 2A.18, 2A.19 may branch from the same `main`. 2A.18 registers no specialist and does not touch `agents/index.yaml`. Worktree branch: `epic-2a/2a-18-next`.
- Epic 4 — the STOP taxonomy (`engine/stop_triggers.py`, 7 triggers) replaces the AC5 free-text reason with structured STOP records; `/sdlc-next`'s `next_action: "none"` + `blockers` map is the forward-compatible shape.

### Inherited Debt

- `EPIC-2A-DEBT-WRITE-PRIMITIVE` — N/A here (`/sdlc-next` writes nothing directly)
- `EPIC-2A-DEBT-CLAUDE-HOOK-FAIL-CLOSED-V1.X` — inherited transitively via `/sdlc-task`

### New Debt (this story)

- `EPIC-2A-DEBT-NEXT-CONSUME-PROJECTION` — once `EPIC-2A-DEBT-TASK-STATE-PROJECTION` (Story 2A.17) lands a task projection into `state.json`, refactor `/sdlc-next` to consume `state.json` instead of re-globbing the artifact tree
- `EPIC-2A-DEBT-NEXT-PRIORITY-RANKING` — AC1's "highest-priority" is approximated by `(story seq, task seq)` order in v1; true cross-phase priority ranking (epic `priority` field P0–P3, story priority) is deferred to the Epic 4 auto-loop / Epic 5 dashboard

### File Layout

```
src/sdlc/commands/sdlc-next.md                # NEW — slash-command shell (no YAML, no specialist)
src/sdlc/cli/next_.py                         # NEW — run_next (≤ 320 LOC)
src/sdlc/cli/_next_resolver.py                # NEW (optional) — phase-aware resolver
src/sdlc/cli/main.py                          # UPDATE — register next_command

tests/unit/cli/test_next_command.py           # NEW
tests/unit/cli/test_next_resolver.py          # NEW
tests/integration/test_sdlc_next.py           # NEW
tests/integration/test_wheel_build.py         # UPDATE — _ALLOWED_CONTENT_FILES
tests/e2e/pipeline/fixtures/next/             # NEW
tests/e2e/pipeline/test_sdlc_next.py          # NEW — Tier-2 e2e (4 scenarios)
```

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1397-1413`] — Story 2A.18 BDD ACs
- [Source: `_bmad-output/planning-artifacts/epics.md:41`] — FR18 definition
- [Source: `_bmad-output/planning-artifacts/architecture.md:950`] — `commands/sdlc-next.md` in the canonical tree
- [Source: `_bmad-output/planning-artifacts/architecture.md:957-963`] — `workflows_yaml/` list omits `sdlc-next.yaml` (correct — no workflow)
- [Source: `_bmad-output/planning-artifacts/architecture.md:1148`] — FR18 → `commands/sdlc-next.md`
- [Source: `src/sdlc/signoff/states.py`] — `compute_state` + `SignoffState`
- [Source: `src/sdlc/state/projection.py`] — v1 projection folds only `epic-<N>` keys (rationale for AC2/D1)
- [Source: `src/sdlc/cli/scan.py`, `src/sdlc/cli/status.py`] — read-only CLI command pattern
- [Source: `src/sdlc/cli/main.py`] — Typer registration + deferred-import pattern
- [Source: `src/sdlc/ids/parsers.py`] — `parse_task_id`, `parse_story_id`
- [Source: `docs/sprints/epic-2a-dag.md`] — Layer 7: A12 → A18
- [Source: CONTRIBUTING.md §1-§5]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

## Change Log
