# Story 2A.19: `sdlc replan --scope=<scope>` (Mark Stale + Invalidate Downstream)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a tech lead handling upstream changes that invalidate prior decisions,
I want `sdlc replan --scope=<scope>` marking items stale and invalidating downstream phase signoffs,
so that the audit chain reflects reality after a major direction change (FR4).

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1415-1437`. Per ADR-026 §1, the public API surface (`cli/replan_cmd.py:run_replan`) requires TDD-first commit ordering visible in `git log --reverse`. This story **depends on Story 2A.12** (the signoff sign flow whose round-trip AC7 verifies) per the Epic 2A DAG (`A12 → A19`). It consumes the `invalidate_record` API shipped by **Story 2A.7** and **closes `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE`** (opened by Story 2A.7 Task 11.5 — `deferred-work.md:359`). This story introduces NO new wire-format contracts (ADR-024 snapshot count remains 5; `SignoffRecord` already carries `invalidated_at` + `invalidated_reason`). It introduces TWO new open-string `JournalEntry.kind` values: `replan_invalidated` (the replan event) and `signoff_invalidated` (per invalidated phase).

### AC1 — `sdlc replan --scope=<scope>` CLI surface + init guard + scope validation

**Given** the user invokes `sdlc replan --scope=<scope>`
**When** the CLI parses arguments
**Then** `src/sdlc/cli/replan_cmd.py:run_replan(*, ctx: typer.Context, scope: str)` is invoked
**And** `--scope` is a REQUIRED option carrying a repo-relative POSIX path to an artifact (e.g. `02-Architecture/02-System/ARCHITECTURE.md`)
**And** the project must be initialized (`.claude/state/state.json` present), else `ERR_NOT_INITIALIZED` with non-zero exit
**And** the scope value is validated as a safe repo-relative POSIX path — reject absolute paths, backslashes, and `..` traversal with `WorkflowError("invalid --scope: <raw>; expected a repo-relative POSIX path")` (`ERR_USER_INPUT`); reuse the `_is_safe_repo_relative_posix` helper pattern from `src/sdlc/signoff/records.py`
**And** the scoped artifact MUST exist on disk → if missing, `WorkflowError("replan scope not found: <scope>; expected at <abs-path>")` with non-zero exit
**And** the scoped path's leading directory MUST map to a known phase (`01-Requirement/` → 1, `02-Architecture/` → 2, `03-Implementation/` → 3) → otherwise `WorkflowError("replan scope is not under a recognized phase directory: <scope>")`

### AC2 — Mark the scoped artifact + downstream artifacts stale

**Given** a valid `--scope` artifact at phase `P_scope`
**When** the replan runs
**Then** the named artifact is recorded as dirty AND every downstream artifact is recorded as dirty
**And** "downstream" is computed per **AC2/D1** below
**And** the dirty set is RECORDED per **AC2/D2** below (where the dirty marker lives)
**And** the count of downstream artifacts (`downstream_count`) is computed for the journal payload + the `--json` envelope

**And** **AC2/D1 (downstream-computation D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** **phase-based downstream** — downstream = every artifact file under a phase directory numerically greater than `P_scope` (`P_scope=1` → everything under `02-Architecture/` + `03-Implementation/`; `P_scope=2` → everything under `03-Implementation/`; `P_scope=3` → none). `downstream_count` = the count of files under those directories. **Pros**: a Phase-2 architecture change genuinely invalidates ALL Phase-3 work — phase-based is *correct*, not merely coarse; deterministic; needs no artifact dependency graph (which does not yet exist as a queryable structure). **Cons**: cannot express "only stories under epic X are stale".
  - **D2:** **fine-grained dependency-DAG traversal** — walk epic→story→task `dependencies` edges from the scope artifact. **Cons**: the scope is often a *document* (`ARCHITECTURE.md`), not an epic/story/task with a `dependencies` field — there is no edge to walk; building an artifact-level provenance graph is architecture concern #16 (provenance/lineage), a separate track.
  - **D3:** hybrid (phase-based for documents, dep-DAG for epic/story/task scopes). **Cons**: two code paths for v1; premature.

**And** **Recommended: D1** — phase-based downstream. Document as FIRST line item in PR Change Log. Open `EPIC-2A-DEBT-REPLAN-FINE-GRAINED-DAG` for the artifact-level provenance traversal (ties to architecture concern #16).

**And** **AC2/D2 (dirty-marker location D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** the dirty set is recorded in the `replan_invalidated` journal entry payload (`{"scope": "<scope>", "scope_phase": P, "downstream_artifacts": ["<rel>", ...], "downstream_count": N}`). The journal is the source of truth (Decision B5); a future `sdlc scan` projection folds `replan_invalidated` entries into a `state.json` dirty-flags field. **Pros**: no `state.json` schema change in a Layer-7 story; consistent with the journal-is-truth + projection pattern. **Cons**: `state.json` does not show dirty flags until the projection is extended.
  - **D2:** write a `.claude/state/replan-dirty.json` sidecar listing dirty paths. **Cons**: a new on-disk file outside the journal/state pair; new recovery surface.
  - **D3:** extend the `State` model with a `dirty_artifacts` field and write `state.json` directly. **Cons**: a `State` schema change — touches the Story 1.19 migration surface; `extra="forbid"` on `State` means every reader must update in lockstep.

**And** **Recommended: D2 → D1** — the `replan_invalidated` journal entry is the dirty record of truth. Document as SECOND line item in PR Change Log. Open `EPIC-2A-DEBT-REPLAN-DIRTY-PROJECTION` to fold `replan_invalidated` entries into a `state.json` dirty-flags projection (consumed by `/sdlc-next` Story 2A.18 + the Epic 5 dashboard).

### AC3 — Invalidate signoff records for affected phases

**Given** the replan scope at phase `P_scope` and downstream phases
**When** the replan proceeds
**Then** for every phase `P` in `{1, 2}` where `P >= P_scope` AND `compute_state(P, repo_root=root) == SignoffState.APPROVED`:
  - the command calls `signoff.invalidate_record(phase=P, repo_root=root, reason=<replan reason>, now_utc=<RFC3339-ms>)`
  - the affected phase's signoff state transitions to `INVALIDATED_BY_REPLAN` (verified via `compute_state` post-call)
**And** Phase 3 is never invalidated as a *signoff* — Phase 3 has no signoff (`signoff/states.py:_PHASE_NO_SIGNOFF`); a `P_scope=3` replan invalidates no signoff record (it still marks Phase-3 artifacts dirty per AC2 and journals the replan event per AC4)
**And** the example from `epics.md:1424` holds: `sdlc replan --scope=02-Architecture/02-System/ARCHITECTURE.md` → `P_scope=2` → Phase 2 signoff (only) transitions to `invalidated-by-replan`
**And** a `P_scope=1` replan invalidates BOTH the Phase 1 and Phase 2 signoff records (both `P >= 1`)
**And** if an affected phase is NOT currently `APPROVED` (e.g. already `INVALIDATED_BY_REPLAN`, or `AWAITING_SIGNOFF`), `invalidate_record` is SKIPPED for that phase — replan-then-replan does not double-invalidate (this also dodges `deferred-work.md:42` W20 "re-invalidating overwrites silently")

### AC4 — Journal entries: `replan_invalidated` + `signoff_invalidated`

**Given** the full `sdlc replan --scope=<scope>` run
**When** all invalidations + dirty-recording complete
**Then** the journal contains, in monotonic order:
  1. ONE `kind="replan_invalidated"` entry — `target_id=<scope>`, `payload={"scope": "<scope>", "scope_phase": P_scope, "downstream_artifacts": [...], "downstream_count": N, "reason": "<reason>"}`
  2. ZERO or more `kind="signoff_invalidated"` entries — one per phase invalidated in AC3 — each `target_id="phase-<P>"`, `payload={"phase": P, "reason": "<reason>", "invalidated_at": "<RFC3339-ms>"}`
**And** the journal write sequence is covered by the journal flock (inherited `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ`)
**And** the `replan_invalidated` entry is appended even when zero signoffs are invalidated (a `P_scope=3` replan, or a replan on a project with no approved signoffs, still records the event)
**And** `emit_json` at the end: `{"command": "replan", "scope": "<scope>", "scope_phase": P_scope, "downstream_count": N, "invalidated_phases": [<P>, ...], "outcome": "success"}`

> This AC + the `invalidate_record` call in AC3 together discharge the cross-story contract of `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE` (`deferred-work.md:359`): (1) call `invalidate_record` for every impacted phase; (2) append a `signoff_invalidated` journal entry carrying `{phase, reason, invalidated_at}`; (3) record downstream dirty flags (AC2/D2 — recorded in the `replan_invalidated` payload; the `sdlc scan` projection fold is the remaining `EPIC-2A-DEBT-REPLAN-DIRTY-PROJECTION` slice).

### AC5 — Phase-gate blocks new Phase-3 writes after invalidation (verify; no code change)

**Given** a replan that invalidated the Phase 2 signoff
**When** any Phase-3 write is subsequently attempted (e.g. `/sdlc-task`, `/sdlc-break`)
**Then** the pre-write phase-gate hook blocks the write because `compute_state(phase=2) == INVALIDATED_BY_REPLAN != APPROVED`
**And** this requires NO change to `src/sdlc/hooks/builtin/phase_gate.py` — the phase-gate already gates `03-Implementation/` writes on `compute_state(2) == APPROVED`, and `invalidate_record` flips that state. The dev VERIFIES this by inspection + an e2e scenario (AC10 scenario 3); the story must not silently regress it.
**And** the CLI pre-flight gates in `/sdlc-task` (Story 2A.17 AC1) and `/sdlc-break` (Story 2A.16 AC1) likewise refuse with `ERR_PHASE2_NOT_APPROVED` after a replan — defense-in-depth alongside the hook

### AC6 — `sdlc trace` surfaces the replan event

**Given** a replan has invalidated a phase
**When** the user runs `sdlc trace <task-id>` on any task affected by the replan
**Then** the trace output shows the replan event with `kind=replan_invalidated, scope=<scope>, downstream_count=N`

**And** **AC6/D1 (trace-integration D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** `replan_invalidated` is a *global* journal event (`target_id=<scope>`, not a task id). `cli/trace.py` is extended so any `trace` invocation always surfaces `kind="replan_invalidated"` entries that postdate the traced task's first journal entry (a global-event passthrough rule). This is a small, well-scoped patch to the trace filter. **Pros**: spec-faithful — `epics.md:1431` literally says `sdlc trace` on an affected task shows the event. **Cons**: touches `cli/trace.py` (the dev must read its current entry-filter structure first).
  - **D2:** v1 does NOT extend `trace`; the replan event is verifiable via `sdlc replay` / `sdlc logs` (which render all journal entries). **Cons**: deviates from the `epics.md:1431` `trace` wording.
  - **D3:** fan out — append a per-task `replan_invalidated` entry for every downstream task so each task's task-scoped trace shows it. **Cons**: journal bloat; O(downstream tasks) writes per replan.

**And** **Recommended: D1** — extend `cli/trace.py` with the global-event passthrough for `replan_invalidated`. The dev reads `cli/trace.py`'s current entry-selection logic during Task 4 and adds the rule with a unit test. If the trace filter structure makes D1 disproportionately large, fall back to D2 and amend this AC — raise it as a D-decision in `review-A`. Document the chosen path as THIRD line item in PR Change Log.

### AC7 — Re-sign round-trip restores `APPROVED` (verify; satisfied by existing `/sdlc-signoff`)

**Given** a replan invalidated the Phase 2 signoff, then the user reverts the offending change and re-runs `/sdlc-signoff 2` (Story 2A.12)
**When** signoff validation runs
**Then** the signoff hashes are recomputed against the current artifacts; if all match, `write_record` writes a fresh record and `compute_state(2)` returns `APPROVED` again; Phase 3 may proceed
**And** this round-trip is satisfied by EXISTING machinery — `signoff.write_record` already permits overwriting an `invalidated_at`-non-null record (`records.py:287` — the guard refuses overwrite only when `existing.invalidated_at is None`, the Story 2A.7 D4 "invalidated overwrite allowed" decision). 2A.19 implements NO re-sign code; it VERIFIES the round-trip in an e2e scenario (AC10 scenario 4) and must not regress it.

### AC8 — `engine/replan.py` pure logic + `cli/replan_cmd.py` shell + `commands/sdlc-replan.md`

**Given** the architecture canonical tree maps FR4 to `cli/replan_cmd.py` + `engine/replan.py` (`architecture.md:800,816,1134`) and lists `commands/sdlc-replan.md` (`architecture.md:953`)
**When** the dev authors the surfaces
**Then** `src/sdlc/engine/replan.py` is authored as the pure replan logic:
  - `resolve_scope_phase(scope: str) -> int` — leading-dir → phase number
  - `compute_downstream(repo_root: Path, scope_phase: int) -> tuple[list[str], int]` — phase-based downstream artifact list + count (AC2/D1)
  - `plan_invalidations(repo_root: Path, scope_phase: int) -> list[int]` — the phases in `{1,2}` with `P >= scope_phase` currently `APPROVED`
  - these are pure / read-only functions; the actual `invalidate_record` calls + journal appends are orchestrated by the CLI (`engine` may depend on `signoff`/`state`/`journal` per the module table, so a thin `engine`-side orchestrator is also acceptable — keep the journal-writing in whichever layer the dev finds cleaner, but the CLI owns `ctx`/`emit_*`)
**And** `src/sdlc/cli/replan_cmd.py:run_replan` is the CLI shell (init guard, scope validation, `emit_json`/`emit_error`, journal orchestration)
**And** `src/sdlc/commands/sdlc-replan.md` is authored (slash-command shell with `--scope` syntax; ≤ 80 LOC). NO workflow YAML and NO specialist — `sdlc replan` dispatches no agent; it is a state-machinery command (like `sdlc rebuild-state`, `sdlc scan`). `architecture.md:957-963`'s `workflows_yaml/` list correctly omits `sdlc-replan.yaml`.
**And** `engine/__init__.py` is updated to export the new `replan` surface alongside `scan`
**And** module-boundary compliance: `engine` may import `signoff`, `state`, `journal`, `config`, `errors` per `scripts/module_boundary_table.py`; `engine` must NOT import `cli`. Verify with `check_module_boundaries.py`.

### AC9 — CLI surface: `sdlc replan --scope=<scope>` + `run_replan` ordering

**Given** the Typer subcommand pattern from Stories 2A.9–2A.17
**When** the dev registers the command
**Then** `@app.command(name="replan")` is registered in `cli/main.py` with a deferred import of `run_replan`:
  ```python
  @app.command(name="replan")
  def replan_command(
      ctx: typer.Context,
      scope: str = typer.Option(..., "--scope", help="Repo-relative POSIX path of the artifact to replan (FR4)."),
  ) -> None:
      """Mark an artifact + its downstream stale and invalidate downstream signoffs (FR4)."""
      from sdlc.cli.replan_cmd import run_replan  # deferred per Architecture §488
      run_replan(ctx=ctx, scope=scope)
  ```
**And** `run_replan(*, ctx, scope)` ordering:
  1. Resolve `repo_root`; init guard → `ERR_NOT_INITIALIZED` (AC1)
  2. Validate `scope` is a safe repo-relative POSIX path; resolve `scope_phase`; verify the artifact exists (AC1)
  3. `compute_downstream(...)` → `(downstream_artifacts, downstream_count)` (AC2)
  4. `plan_invalidations(...)` → the list of `APPROVED` phases `>= scope_phase` (AC3)
  5. Append the `kind="replan_invalidated"` journal entry (AC4 #1) — appended FIRST so the event is recorded even if a later `invalidate_record` raises
  6. For each phase to invalidate: `invalidate_record(...)` then append `kind="signoff_invalidated"` (AC3 + AC4 #2)
  7. `emit_json` success envelope (AC4)
**And** the module LOC budget is ≤ 320; extraction of pure logic into `engine/replan.py` (AC8) keeps `cli/replan_cmd.py` thin.

### AC10 — Tier-2 e2e + anti-tautology receipt

**Given** the Tier-2 e2e harness from Story 2A.0 + the `phase2_approved_repo` fixture (Story 2A.15/2A.16/2A.17)
**When** the dev authors the replan e2e
**Then** `tests/e2e/pipeline/test_sdlc_replan.py` (NEW) covers at minimum:

  1. **Phase 2 scope invalidation**: tmp repo with Phase 1 + Phase 2 `APPROVED`; invoke `sdlc replan --scope=02-Architecture/02-System/ARCHITECTURE.md`; assert exit 0; assert `compute_state(2) == INVALIDATED_BY_REPLAN`; assert `compute_state(1)` UNCHANGED (`APPROVED`); assert ONE `replan_invalidated` + ONE `signoff_invalidated` journal entry; assert `--json` `invalidated_phases == [2]`
  2. **Phase 1 scope cascades to Phase 2**: invoke `sdlc replan --scope=01-Requirement/01-PRODUCT.md`; assert BOTH Phase 1 and Phase 2 signoffs → `INVALIDATED_BY_REPLAN`; assert TWO `signoff_invalidated` entries; `invalidated_phases == [1, 2]`
  3. **Phase-gate blocks Phase-3 writes post-replan**: after scenario 1, attempt a `/sdlc-task` (or `/sdlc-break`) run; assert it refuses with `ERR_PHASE2_NOT_APPROVED` (AC5)
  4. **Re-sign round-trip**: after scenario 1, re-run `/sdlc-signoff 2`; assert `compute_state(2)` returns to `APPROVED`; assert a subsequent Phase-3 write is no longer blocked (AC7)

**And** **Anti-tautology receipt (AC10 mandatory)**: in an auxiliary executable test, temporarily neutralise the `invalidate_record` call in `run_replan` (skip it); re-run scenario 1; observe the inversion — the assertion `compute_state(2) == INVALIDATED_BY_REPLAN` now FAILS (the state stays `APPROVED`); revert. Document as `test_e2e_replan_invalidation_is_load_bearing` in the PR Change Log. The receipt proves the `invalidate_record` call, and only it, drives the state transition.

### AC11 — Module boundary + quality gate compliance (CONTRIBUTING.md §1)

**Given** the Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests`
  - `pytest -q -m "not e2e and not property"` — new unit + integration tests green
  - `pytest -q -m e2e` — new `test_sdlc_replan.py` + all existing e2e green
  - `python scripts/freeze_wireformat_snapshots.py --check` — `5 contracts match snapshots` (unchanged — no contract edits; `SignoffRecord` already has `invalidated_at`/`invalidated_reason` and is not snapshotted)
  - `python scripts/check_module_boundaries.py` — 0 new violations; `engine` depends on `signoff`/`state`/`journal`/`config`/`errors` (already in the table); `cli` depends on `engine`/`signoff`/`journal` (already in the table)
  - `mkdocs build --strict` — clean
  - `tests/integration/test_wheel_build.py` — `sdlc-replan.md` added to `_ALLOWED_CONTENT_FILES`

## Tasks / Subtasks

> Tasks ordered for TDD-first commits per ADR-026 §1. AC1/AC9 (CLI), AC2/AC3/AC8 (engine logic), AC10 (e2e) are public-API surfaces requiring tests-first commit ordering.

- [ ] **Task 1 — Slash-command shell + CLI registration skeleton (AC1, AC8, AC9)** — **TDD-first commit 1**
  - [ ] 1.1 Author `src/sdlc/commands/sdlc-replan.md` (≤ 80 LOC; `--scope` syntax; no YAML, no specialist).
  - [ ] 1.2 Author the `run_replan` skeleton in `src/sdlc/cli/replan_cmd.py` (init guard + scope validation only).
  - [ ] 1.3 Register `replan_command` in `cli/main.py` (deferred import; `--scope` required option).
  - [ ] 1.4 Author `tests/unit/cli/test_replan_command.py` — command registered; init guard → `ERR_NOT_INITIALIZED`; bad `--scope` (absolute / `..` / backslash) → `WorkflowError`; missing scope artifact → `WorkflowError "not found"`; scope outside a phase dir → `WorkflowError`. Tests fail (red) → implement → pass (green).
  - [ ] 1.5 Document AC2/D1, AC2/D2, AC6/D1 as FIRST/SECOND/THIRD line items in the PR Change Log.

- [ ] **Task 2 — `engine/replan.py` pure logic (AC2, AC3, AC8)** — **TDD-first commit 2**
  - [ ] 2.1 Author `tests/unit/engine/test_replan.py`:
    - `resolve_scope_phase` — `01-/02-/03-` prefixes → 1/2/3; unknown → raises
    - `compute_downstream` — `scope_phase=1` → files under `02-` + `03-`; `=2` → under `03-`; `=3` → empty; count correct
    - `plan_invalidations` — only `APPROVED` phases `>= scope_phase` in `{1,2}`; an already-invalidated phase is excluded (AC3 replan-then-replan)
    Tests fail (red).
  - [ ] 2.2 Implement `src/sdlc/engine/replan.py` (`resolve_scope_phase`, `compute_downstream`, `plan_invalidations` — pure / read-only).
  - [ ] 2.3 Update `src/sdlc/engine/__init__.py` to export the replan surface. Tests pass (green).
  - [ ] 2.4 Run `python scripts/check_module_boundaries.py` — confirm `engine` → `signoff` edge is already permitted.

- [ ] **Task 3 — `run_replan` orchestration: invalidate + journal (AC3, AC4, AC9)** — **TDD-first commit 3**
  - [ ] 3.1 Author `tests/unit/cli/test_replan_command.py` additions:
    - Phase 2 scope, both phases approved → only Phase 2 `invalidate_record` called; one `signoff_invalidated` entry
    - Phase 1 scope → Phase 1 + Phase 2 invalidated; two `signoff_invalidated` entries
    - Phase 3 scope → no `invalidate_record` call; still one `replan_invalidated` entry
    - replan-then-replan → second run does not re-invalidate (AC3 skip)
    - `replan_invalidated` payload carries `scope`, `scope_phase`, `downstream_count`, `downstream_artifacts`
    - `emit_json` envelope shape (AC4)
    Tests fail (red).
  - [ ] 3.2 Implement the `run_replan` body per the AC9 ordering: append `replan_invalidated` FIRST, then per-phase `invalidate_record` + `signoff_invalidated`, then `emit_json`. Tests pass (green).
  - [ ] 3.3 Integration test `tests/integration/test_sdlc_replan.py`: tmp repo with approved Phase 1 + 2 signoff records; invoke `run_replan`; assert signoff YAML files gain `invalidated_at`; assert the journal sequence.

- [ ] **Task 4 — `sdlc trace` global-event passthrough (AC6)** — **TDD-first commit 4**
  - [ ] 4.1 Read `src/sdlc/cli/trace.py` — understand its current journal-entry selection/filtering.
  - [ ] 4.2 Author a unit test asserting `sdlc trace <task>` output includes a `kind="replan_invalidated"` entry that postdates the task (AC6/D1). Test fails (red).
  - [ ] 4.3 Implement the global-event passthrough rule in `cli/trace.py` (AC6/D1). If the change is disproportionately large, fall back to AC6/D2 and raise the deviation as a D-decision in `review-A`. Test passes (green).

- [ ] **Task 5 — Tier-2 e2e + anti-tautology receipt (AC5, AC7, AC10)** — **TDD-first commit 5**
  - [ ] 5.1 Reuse `phase2_approved_repo` from `tests/e2e/pipeline/conftest.py` (must yield a repo with REAL approved Phase 1 + Phase 2 signoff records — extend the fixture if it only seeds Phase 2).
  - [ ] 5.2 Author `tests/e2e/pipeline/fixtures/replan/` as needed.
  - [ ] 5.3 Author `tests/e2e/pipeline/test_sdlc_replan.py` (4 scenarios per AC10).
  - [ ] 5.4 Run targeted Tier-2 e2e: all scenarios green.
  - [ ] 5.5 **Anti-tautology receipt (AC10 mandatory)**: neutralise the `invalidate_record` call; confirm `test_e2e_replan_invalidation_is_load_bearing` fails; revert; document in the PR Change Log.

- [ ] **Task 6 — Module boundary + quality gate + Change Log + close debt (AC11)**
  - [ ] 6.1 Run `python scripts/check_module_boundaries.py` — confirm no new edges required.
  - [ ] 6.2 Add `sdlc-replan.md` to `tests/integration/test_wheel_build.py:_ALLOWED_CONTENT_FILES`.
  - [ ] 6.3 Run the full quality gate; record the baseline.
  - [ ] 6.4 Mark `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE` CLOSED in `deferred-work.md` (cite AC3 + AC4); author the PR Change Log with D-decisions, the anti-tautology receipt, debt citations.

## Dev Notes

### The replan flow

```
run_replan(ctx, scope)
  ├── 1. init guard
  ├── 2. _is_safe_repo_relative_posix(scope); scope_phase = resolve_scope_phase(scope)
  │      (root/scope).exists()  else ERR
  ├── 3. downstream, count = compute_downstream(root, scope_phase)        ← AC2/D1
  ├── 4. phases = plan_invalidations(root, scope_phase)  # APPROVED, >=scope_phase, ⊆{1,2}
  ├── 5. journal append  kind="replan_invalidated"  target=scope          ← AC4 #1
  │        payload={scope, scope_phase, downstream_artifacts, downstream_count, reason}
  ├── 6. for P in phases:
  │        invalidate_record(phase=P, repo_root=root, reason=..., now_utc=...)  ← AC3
  │        journal append  kind="signoff_invalidated"  target=f"phase-{P}"      ← AC4 #2
  └── 7. emit_json {scope, scope_phase, downstream_count, invalidated_phases, outcome}
```

`replan_invalidated` is journaled BEFORE any `invalidate_record` so the audit chain records the *intent* even if a downstream `invalidate_record` raises (fail-loud: the exception propagates to `emit_error`, but the event is already on the chain).

### Phase-based downstream (AC2/D1)

`scope_phase` is the leading directory: `01-Requirement/` → 1, `02-Architecture/` → 2, `03-Implementation/` → 3. Downstream = all files under phase directories numerically greater than `scope_phase`. `compute_downstream` globs `root / "<NN>-*" ` for the higher phases (or globs the three known phase dirs). Return the sorted repo-relative POSIX paths + their count.

`EPIC-2A-DEBT-REPLAN-FINE-GRAINED-DAG`: a true artifact-provenance graph (architecture concern #16) would let a replan invalidate only the stories under one epic. Out of scope for v1.

### Signoff invalidation (AC3) — the `invalidate_record` API

Story 2A.7 ships `invalidate_record(phase, *, repo_root, reason, now_utc) -> SignoffRecord` (`signoff/records.py:303`). It rewrites `.claude/state/signoffs/phase-<N>.yaml` atomically, setting `invalidated_at` + `invalidated_reason`. After the call, `compute_state(phase, repo_root)` returns `INVALIDATED_BY_REPLAN` (`signoff/states.py` — "canonical record exists + `invalidated_at` non-null"). Phase 3 has no signoff record — never call `invalidate_record(phase=3)` (it would raise; `_VALID_RECORD_PHASES = {1, 2}`).

Guard against double-invalidation (AC3): only call `invalidate_record` for a phase whose `compute_state` is currently `APPROVED`. A phase already `INVALIDATED_BY_REPLAN` is skipped — this also sidesteps `deferred-work.md` W20 ("re-invalidating overwrites silently": a second `invalidate_record` loses the original timestamp/reason).

### Phase-gate already blocks post-replan writes (AC5 — no code change)

`hooks/builtin/phase_gate.py` gates `03-Implementation/` writes on `compute_state(2) == APPROVED`. After `invalidate_record(2, ...)`, that state is `INVALIDATED_BY_REPLAN` → the phase-gate denies. `/sdlc-task` (2A.17 AC1) and `/sdlc-break` (2A.16 AC1) ALSO pre-flight on `compute_state(2) == APPROVED` → they refuse with `ERR_PHASE2_NOT_APPROVED`. 2A.19 changes neither — it verifies the behavior via AC10 scenario 3.

### Re-sign round-trip (AC7 — no code change)

`/sdlc-signoff 2` (Story 2A.12) runs `validate_signoff` (hash recompute) then `write_record`. `write_record` (`records.py:262`) refuses overwrite ONLY when `existing.invalidated_at is None` — an invalidated record CAN be overwritten (Story 2A.7 D4). So re-signing after a replan writes a fresh record → `compute_state(2)` → `APPROVED`. 2A.19 verifies this in AC10 scenario 4.

### `engine/replan.py` and module boundaries

`engine` may import `signoff`, `state`, `journal`, `config`, `errors` (`scripts/module_boundary_table.py:95-102`). `engine` must NOT import `cli` (`forbidden_from={"cli", "dashboard"}`). Keep `ctx`/`emit_*`/journal-orchestration in `cli/replan_cmd.py`; keep the pure `resolve_scope_phase`/`compute_downstream`/`plan_invalidations` in `engine/replan.py`. `architecture.md:1134` maps FR4 to exactly this split (`cli/replan_cmd.py` + `engine/replan.py`).

### `sdlc replan` is a top-level CLI command, not a slash-workflow

`sdlc replan` dispatches no specialist — it is pure state machinery (like `sdlc scan`, `sdlc rebuild-state`). It has a `commands/sdlc-replan.md` Claude-Code shell (`architecture.md:953`) but NO `workflows_yaml/sdlc-replan.yaml` and NO specialist. Do not add a workflow YAML.

### Cross-Story Coordination

- Story 2A.7 (DEPENDENCY) — `invalidate_record`, `compute_state`, `SignoffState.INVALIDATED_BY_REPLAN`, the 4-state signoff machine. **Closes `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE`** opened by 2A.7 Task 11.5.
- Story 2A.12 (DEPENDENCY, per DAG `A12 → A19`) — the `/sdlc-signoff` sign flow whose re-sign round-trip AC7 verifies; `write_record`'s "invalidated overwrite allowed" posture
- Story 2A.16 / 2A.17 (downstream) — `/sdlc-break` + `/sdlc-task` Phase-3 writes are blocked post-replan (AC5); no direct code coupling
- Story 2A.18 (Layer-7 sibling) — `/sdlc-next` will eventually read replan dirty flags once `EPIC-2A-DEBT-REPLAN-DIRTY-PROJECTION` lands a `state.json` projection
- **Layer-7 sibling coordination**: Stories 2A.17, 2A.18, 2A.19 may branch from the same `main`. 2A.19 registers no specialist and does not touch `agents/index.yaml`. Worktree branch: `epic-2a/2a-19-replan`.
- Story 4.12 (`sdlc unsign`, mad-only) — depends on the 2A.7 signoff state machine; `sdlc replan` and `sdlc unsign` are sibling state-mutators — keep `invalidate_record` the single invalidation surface.
- `deferred-work.md` W10 (Story 2A.3) — "fail-mid-dispatch journal orphans … coordinate with Story 2A.19" — out of 2A.19 scope; `replan` does not dispatch, so it generates no panel orphans. Leave W10 with the retry/panel owner.

### Inherited Debt

- `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` — journal flock covers the `replan_invalidated` + `signoff_invalidated` append sequence
- `EPIC-2A-DEBT-SIGNOFF-FLOCK-CONCURRENCY` (`deferred-work.md:361`) — `invalidate_record`'s `tmp+replace` is not flock-guarded; re-cited, not fixed here

### New Debt (this story)

- `EPIC-2A-DEBT-REPLAN-FINE-GRAINED-DAG` — v1 downstream is phase-based; an artifact-level provenance graph (architecture concern #16) would scope invalidation to the affected epic/story subtree
- `EPIC-2A-DEBT-REPLAN-DIRTY-PROJECTION` — the dirty set lives in the `replan_invalidated` journal payload; a `sdlc scan` projection folding it into a `state.json` dirty-flags field is deferred (consumed by `/sdlc-next` + Epic 5 dashboard)
- (conditional) `EPIC-2A-DEBT-REPLAN-TRACE-PASSTHROUGH` — open ONLY if AC6 falls back to D2 (trace not extended); otherwise AC6/D1 closes the trace requirement inline

### Closed Debt (this story)

- `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE` — CLOSED by AC3 (`invalidate_record` per impacted phase) + AC4 (`signoff_invalidated` journal entry with `{phase, reason, invalidated_at}`) + AC2/D2 (downstream dirty recorded in `replan_invalidated`). Mark closed in `deferred-work.md` during Task 6.4.

### File Layout

```
src/sdlc/commands/sdlc-replan.md              # NEW — slash-command shell (no YAML, no specialist)
src/sdlc/cli/replan_cmd.py                    # NEW — run_replan CLI shell (≤ 320 LOC)
src/sdlc/cli/main.py                          # UPDATE — register replan_command
src/sdlc/engine/replan.py                     # NEW — pure replan logic (FR4)
src/sdlc/engine/__init__.py                   # UPDATE — export replan surface
src/sdlc/cli/trace.py                         # UPDATE — replan_invalidated global-event passthrough (AC6/D1)

tests/unit/cli/test_replan_command.py         # NEW
tests/unit/engine/test_replan.py              # NEW
tests/unit/cli/test_trace_replan.py           # NEW (or extend an existing trace test)
tests/integration/test_sdlc_replan.py         # NEW
tests/integration/test_wheel_build.py         # UPDATE — _ALLOWED_CONTENT_FILES
tests/e2e/pipeline/fixtures/replan/           # NEW (as needed)
tests/e2e/pipeline/test_sdlc_replan.py        # NEW — Tier-2 e2e (4 scenarios)
tests/e2e/pipeline/conftest.py                # UPDATE if phase2_approved_repo lacks Phase 1 signoff
```

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1415-1437`] — Story 2A.19 BDD ACs
- [Source: `_bmad-output/planning-artifacts/epics.md:39`] — FR4 definition (`sdlc replan`)
- [Source: `_bmad-output/planning-artifacts/architecture.md:117`] — replan engine in the FR1–FR5 lifecycle group
- [Source: `_bmad-output/planning-artifacts/architecture.md:800,816`] — `cli/replan_cmd.py` + `engine/replan.py` in the canonical tree
- [Source: `_bmad-output/planning-artifacts/architecture.md:953`] — `commands/sdlc-replan.md`
- [Source: `_bmad-output/planning-artifacts/architecture.md:1134`] — FR4 → `cli/replan_cmd.py` + `engine/replan.py`
- [Source: `_bmad-output/planning-artifacts/architecture.md` concern #16] — provenance/artifact lineage (rationale for AC2/D1 deferral)
- [Source: `src/sdlc/signoff/records.py:303`] — `invalidate_record(phase, *, repo_root, reason, now_utc)`
- [Source: `src/sdlc/signoff/records.py:262,287`] — `write_record` permits overwriting an invalidated record (AC7)
- [Source: `src/sdlc/signoff/states.py`] — `compute_state`, `SignoffState.INVALIDATED_BY_REPLAN`, `_PHASE_NO_SIGNOFF`
- [Source: `src/sdlc/signoff/records.py` `_is_safe_repo_relative_posix`] — scope-path safety validator pattern
- [Source: `src/sdlc/hooks/builtin/phase_gate.py`] — phase-boundary enforcement (AC5 — verify, no change)
- [Source: `scripts/module_boundary_table.py:95-102,126`] — `engine` / `cli` `depends_on` sets
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md:359`] — `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE` (closed by this story)
- [Source: `docs/sprints/epic-2a-dag.md`] — Layer 7: A12 → A19
- [Source: CONTRIBUTING.md §1-§5]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

## Change Log
