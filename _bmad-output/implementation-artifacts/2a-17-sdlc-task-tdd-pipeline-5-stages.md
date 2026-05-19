# Story 2A.17: `/sdlc-task <TASK-id>` (TDD Pipeline — 5 Stages)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer executing a task through the full TDD pipeline,
I want `/sdlc-task <TASK-id>` advancing one stage per invocation through `pending → write-tests → write-code → review → done` with the appropriate specialist dispatched per stage,
so that every task is produced via TDD discipline with explicit review (FR17).

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1361-1395`. Per ADR-026 §1, the public API surface (`cli/task.py:run_task`) requires TDD-first commit ordering visible in `git log --reverse`. This story **depends on Story 2A.15** (`agents/phase3/` directory + `phase2_approved_repo` fixture) and **depends on Story 2A.16** (task JSON files under `03-Implementation/tasks/<STORY-id>/`, the `_TaskEntry` private model, `phase1_compound_prompt_builder`). It is the **first story of Layer 7** of the Epic 2A DAG, the longest critical-path tail (`2A.0 → 2A.1 → 2A.3 → 2A.6 → 2A.8 → 2A.12 → 2A.15 → 2A.17`). This story introduces NO new wire-format contracts (ADR-024 snapshot count remains 5). It introduces TWO new open-string `JournalEntry.kind` values (`task_stage_advanced`, `task_stage_failed`).

### AC1 — TASK-id positional argument + init guard + Phase 2 signoff gate

**Given** the user invokes `sdlc task <TASK-id>` with a positional argument
**When** the CLI parses the argument
**Then** the argument is validated against `TASK_ID_REGEX` (Story 1.6, exported from `sdlc.ids`)
**And** a malformed TASK-id raises `WorkflowError("invalid TASK-id: <raw>; expected pattern <pattern>")` with non-zero exit (`ERR_USER_INPUT`)
**And** the empty or missing argument yields the Typer usage error (no custom handling required)

**Given** the project is not initialized (`.claude/state/state.json` absent)
**When** I run `/sdlc-task TASK-id`
**Then** the CLI refuses with `ERR_NOT_INITIALIZED` ("project not initialized at <root>; run `sdlc init` first")

**Given** Phase 2 signoff is NOT in state `APPROVED`
**When** I run `/sdlc-task TASK-id`
**Then** the CLI pre-flight refuses with `ERR_PHASE2_NOT_APPROVED` (same message family as Story 2A.15/2A.16 AC1; defense-in-depth alongside the phase-gate hook — task work writes under `03-Implementation/` and `src/` and `tests/`, all Phase-3-gated paths)
**And** no dispatch is attempted; no files are written; the task stage is unchanged

### AC2 — Task file lookup + current-stage read + idempotency (`done` refuse)

**Given** Phase 2 `APPROVED` and TASK-id valid
**When** the command locates the task
**Then** it reads `03-Implementation/tasks/<STORY-id>/T<NN>-<slug>.json` where the path is derived from `parse_task_id(<TASK-id>)` — `STORY-id = EPIC-<epic_slug>-S<story_num:02d>-<story_slug>`, filename `T<task_num:02d>-<task_slug>.json`
**And** if the task JSON file is missing → `WorkflowError("task not found: <TASK-id>; expected at <abs-path>; run '/sdlc-break <STORY-id>' first")` with non-zero exit
**And** if found, the file is parsed as `_TaskEntry` (private model from `cli/_epic_story_models.py`, extended per AC8)
**And** the BOUNDARY_LINE pollution guard applies to the task JSON text (`ERR_ARTIFACT_CONTAINS_BOUNDARY` if present)

**Given** the parsed task is already at `stage: done`
**When** I run `/sdlc-task TASK-id`
**Then** the command refuses with `WorkflowError("task already complete: <TASK-id> is at stage 'done'")` with non-zero exit
**And** NO dispatch is attempted; NO files are written

> **Single-stage-advance invariant (binding for AC3–AC6):** ONE invocation of `/sdlc-task` advances the task by EXACTLY ONE stage and dispatches EXACTLY ONE specialist (zero for the `review → done` transition). The pipeline is re-entrant: the user (or `/sdlc-next`, Story 2A.18) re-invokes `/sdlc-task` to drive the next stage. The CLI never loops the stages internally.

### AC3 — Stage transition `pending → write-tests` (test-author)

**Given** the task at `stage: pending`
**When** I run `/sdlc-task TASK-id`
**Then** the `test-author` specialist is dispatched with a compound prompt (`phase1_compound_prompt_builder`, `primary_input` = task record canonical text, `secondary_input` = story JSON; labels `TASK_TO_IMPLEMENT` / `STORY_CONTEXT`; `BOUNDARY_LINE` enforcement applies)
**And** the specialist returns a JSON object `{"files": [{"path": "<repo-relative POSIX>", "content": "<text>"}, ...], "tests_status": "red"}`
**And** every declared file `path` MUST be under `tests/` (reject otherwise with `WorkflowError("test-author wrote outside tests/: <path>")`)
**And** each file write goes through the pre-write hook chain (`build_pre_write_hook_chain`, Story 2A.4 + 2A.6)
**And** the task JSON `stage` field is updated `pending → write-tests` and the file is rewritten (canonical serialization)
**And** a journal entry is appended with `kind="task_stage_advanced"`, `target_id=<TASK-id>`, `payload={"task": "<TASK-id>", "from": "pending", "to": "write-tests", "specialist": "test-author"}`

### AC4 — Stage transition `write-tests → write-code` (code-author, RED→GREEN gate)

**Given** the task at `stage: write-tests`
**When** I run `/sdlc-task TASK-id`
**Then** the `code-author` specialist is dispatched (compound prompt as AC3)
**And** the specialist returns `{"files": [{"path": "<repo-relative POSIX>", "content": "..."}, ...], "tests_status": "green"}`
**And** every declared file `path` MUST be under `src/` (reject otherwise with `WorkflowError("code-author wrote outside src/: <path>")`)
**And** the RED→GREEN gate is enforced per **AC4/D1** below: the stage advances ONLY when the task's tests transition from RED (at `write-tests`) to GREEN (after `write-code`)
**And** each file write goes through the pre-write hook chain
**And** the task JSON `stage` advances `write-tests → write-code`
**And** a journal entry `kind="task_stage_advanced"` is appended with `from="write-tests", to="write-code", specialist="code-author"`

**And** **AC4/D1 (RED→GREEN verification D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** v1 trusts the specialist's self-reported `tests_status`. The gate is: the `test-author` response at AC3 MUST report `tests_status="red"` and the `code-author` response at AC4 MUST report `tests_status="green"`; a mismatch (`code-author` reports `red`) is a stage-transition failure per AC7. **Pros**: deterministic, fast, correct for the v1 posture — Epic 2A runs against `MockAIRuntime` only (epics.md ship-signal: "orchestration without real LLM = incomplete"); no real source is generated, so a real `pytest` subprocess has nothing meaningful to execute. **Cons**: does not actually run tests; trusts agent output. Tracked as `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION`.
  - **D2:** v1 runs a real `pytest` subprocess scoped to the task's test files between AC3 and AC4 and gates on the exit code. **Cons**: mock-generated test files are not executable real code; the subprocess fails for reasons unrelated to TDD discipline; slow; fragile in CI.
  - **D3:** v1 runs `pytest` advisory-only (logs the result, does not gate). **Cons**: a non-gating "gate" is misleading.

**And** **Recommended: D1** — self-reported `tests_status` is the v1 contract. Document as FIRST line item in PR Change Log; open `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION` (owner: Epic 2B, when `ClaudeAIRuntime` produces real source) for the real `pytest`-subprocess RED→GREEN gate.

### AC5 — Stage transition `write-code → review` (code-reviewer, verdict captured)

**Given** the task at `stage: write-code`
**When** I run `/sdlc-task TASK-id`
**Then** the `code-reviewer` specialist is dispatched (compound prompt as AC3)
**And** the specialist returns `{"verdict": "approved" | "rejected", "notes": "<text>"}`
**And** the reviewer's verdict is captured in the task JSON record per AC8 (`review_verdict` + `review_notes` fields)
**And** the task JSON `stage` advances `write-code → review` REGARDLESS of the verdict value (the `review` stage means "a review has been performed"; whether the verdict was clean is evaluated at the `review → done` transition, AC6)
**And** a journal entry `kind="task_stage_advanced"` is appended with `from="write-code", to="review", specialist="code-reviewer"` and `payload` carries `"verdict": "<approved|rejected>"`

### AC6 — Stage transition `review → done` (clean-verdict gate, no dispatch)

**Given** the task at `stage: review` with `review_verdict == "approved"`
**When** I run `/sdlc-task TASK-id`
**Then** NO specialist is dispatched (this transition is a pure state advance)
**And** the task JSON `stage` advances `review → done`
**And** a journal entry `kind="task_stage_advanced"` is appended with `from="review", to="done", specialist=null`
**And** the task JSON `stage: done` field is the **state-of-record** for task completion per **AC6/D1** below

**Given** the task at `stage: review` with `review_verdict == "rejected"`
**When** I run `/sdlc-task TASK-id`
**Then** the transition is a stage-transition failure per AC7: the task remains at `stage: review`, `kind="task_stage_failed"` is journaled, and the user is told to address the review and re-run

**And** **AC6/D1 (state.json reflection D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** the task JSON file's `stage` field IS the canonical per-task state of record for v1. `/sdlc-task` writes the journal `task_stage_advanced` entries + the task JSON file; it does NOT write `state.json` directly. `sdlc scan`'s state projection does not yet fold task records (the v1 projection in `state/projection.py` covers only `epic-<N>` keys). **Pros**: matches the established journal-is-source-of-truth + projection pattern (Decision B5); no `state/projection.py` change in a Layer-7 story. **Cons**: `state.json["tasks"]` stays empty until the projection is extended.
  - **D2:** `/sdlc-task` writes `state.json["tasks"][<TASK-id>] = {"stage": ...}` directly. **Cons**: bypasses the journal-projection contract; two writers of `state.json`.

**And** **Recommended: D1** — the task JSON `stage` field is the v1 state of record. Document as SECOND line item in PR Change Log; open `EPIC-2A-DEBT-TASK-STATE-PROJECTION` to extend `state/projection.py` to fold `task_stage_advanced` entries into `state.json["tasks"]` (consumed later by Story 2A.18 `/sdlc-next` and Epic 5 dashboard).

### AC7 — Stage-transition failure handling

**Given** ANY stage transition fails — specifically:
  - `code-author` reports `tests_status="red"` at AC4 (RED→GREEN gate failed)
  - `code-reviewer` returns `verdict="rejected"` and the task is being advanced `review → done` at AC6
  - the dispatched specialist returns a malformed / schema-invalid response
  - a pre-write hook denies a file write
  - the dispatch itself fails (`DispatchResult.outcome != "success"` after the retry policy)
**When** the failure surfaces
**Then** the task JSON `stage` field is left UNCHANGED (no advance; no partial write of the task record)
**And** any source/test files written before the failure point are rolled back (unlinked) — mirror the Story 2A.16 mid-batch rollback pattern
**And** a journal entry `kind="task_stage_failed"` is appended with `target_id=<TASK-id>` and `payload={"task": "<TASK-id>", "stage": "<current-stage>", "reason": "<specific reason>"}`
**And** the CLI exits non-zero with an actionable message naming the next user action, e.g.:
  - rejected review → `"review rejected for <TASK-id>: see notes in <task-json-path>; address the feedback and rerun '/sdlc-task <TASK-id>'"`
  - RED→GREEN gate → `"code-author did not turn the test suite green for <TASK-id>; tests still RED; rerun '/sdlc-task <TASK-id>'"`

### AC8 — `_TaskEntry` stage + review-field extension; task-file write contract

**Given** the `_TaskEntry` private model from Story 2A.16 (`stage: Literal["pending"]`, no review fields)
**When** the dev extends the model
**Then** `cli/_epic_story_models.py` is UPDATED:
  ```python
  class _TaskEntry(StrictModel):
      id: str                                  # TASK_ID_REGEX
      story_id: str                            # STORY_ID_REGEX
      label: Annotated[str, StringConstraints(min_length=1)]
      stage: Literal["pending", "write-tests", "write-code", "review", "done"] = "pending"
      dependencies: list[str] = Field(default_factory=list)
      review_verdict: Literal["approved", "rejected"] | None = Field(default=None, exclude=True)
      review_notes: str | None = Field(default=None, exclude=True)
  ```
**And** the `stage` Literal is widened to the 5-state machine (Story 2A.16 wrote `stage="pending"`; this story is the only writer that advances it)
**And** `review_verdict` + `review_notes` are NEW optional fields recording the AC5 reviewer output
**And** **AC8/D1 (review-field serialization D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** `review_verdict` + `review_notes` carry `exclude=True` so `serialize_task_entry` output stays byte-stable with Story 2A.16's serialization (no new keys when null). When a review IS recorded, the CLI writes the verdict via a dedicated `serialize_task_entry_full(entry)` helper that includes the review fields, OR the review fields drop `exclude=True` and the postcondition/snapshot posture is re-checked. **Decision:** drop `exclude=True` ONLY on `review_verdict`/`review_notes` is NOT viable because Story 2A.16 task files (written before a review) would then gain keys on rewrite. **Recommended:** keep `review_verdict`/`review_notes` as `exclude=True`-free fields BUT serialize via `model_dump(mode="json")` so a null verdict serializes as `"review_verdict": null` — the task JSON file written by `/sdlc-break` (Story 2A.16) is rewritten by `/sdlc-task` on the FIRST stage advance anyway (stage changes `pending → write-tests`), so the key set legitimately grows at that point. `_TaskEntry` is private and NOT snapshotted (ADR-024 count unchanged), so a key-set change is not a contract edit.
  - **D2:** keep `exclude=True` and store review output in a separate sidecar file `03-Implementation/tasks/<STORY-id>/T<NN>-<slug>.review.json`. **Cons**: a second file per task; extra glob surface.

**And** **Recommended: D1** — `review_verdict`/`review_notes` are real serialized fields on `_TaskEntry`; the task JSON key set grows on the first `/sdlc-task` invocation; `_TaskEntry` is private so this is not an ADR-024 edit. Document as THIRD line item in PR Change Log. Add `serialize_task_entry` coverage for the extended shape (the existing Story 2A.16 helper already uses `model_dump(mode="json")` + `sort_keys=True` — verify it round-trips the new fields).

> **Coordination note**: `dispatcher/postconditions.py:_validate_story_json_file` and any task-JSON shape check do NOT validate task files against a frozen key set, so widening `_TaskEntry` does not break a postcondition. Verify during Task 2.

### AC9 — Workflow YAML + 3 specialist stubs + slash-command shell + index.yaml

**Given** the architecture canonical tree lists `workflows_yaml/sdlc-task.yaml` (`architecture.md:962`) and `commands/sdlc-task.md` (`architecture.md:949`)
**When** the dev authors the workflow surface
**Then** `src/sdlc/workflows_yaml/sdlc-task.yaml` is authored:
  ```yaml
  schema_version: 1
  name: phase3-task-tdd-pipeline
  slash_command: /sdlc-task
  primary_agent: test-author
  parallel_agents:
    - code-author
    - code-reviewer
  synthesizer_agent: null
  postconditions: []
  write_globs:
    test-author:
      - "tests/**"
    code-author:
      - "src/**"
    code-reviewer:
      - "03-Implementation/tasks/**"
  stop_on_postcondition_failure: true
  ```
  > **AC9 amendment (code review 2026-05-18):** `parallel_agents` MUST list `code-author`
  > and `code-reviewer` — NOT `[]`. The `workflows/static_check.py:_check_phantom_agents`
  > guard rejects any `write_globs` key that is not a declared agent (`primary_agent` ∪
  > `parallel_agents` ∪ `synthesizer_agent`). Since the three-specialist `write_globs`
  > block is mandated above, `parallel_agents: []` would make `code-author`/`code-reviewer`
  > phantom agents and the workflow would fail to load. `parallel_agents` here is registry
  > metadata satisfying the static check only; the single-primary `dispatch()` path used by
  > `run_task` dispatches `primary_agent` exclusively per stage — there is no panel fan-out.
**And** **AC9/D1 (single-workflow / per-stage-specialist D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** ONE `sdlc-task.yaml` whose `primary_agent` is `test-author` (nominal — the first stage's specialist, satisfying the `WorkflowSpec` 1:1 slash-command discovery contract). The CLI (`run_task`) owns the stage→specialist map (`{"pending": "test-author", "write-tests": "code-author", "write-code": "code-reviewer"}`) and selects the specialist directly from the registry per stage. The workflow YAML's `write_globs` carries all three specialists' globs for the static disjoint-writes check. **Pros**: no `WorkflowSpec` contract edit (frozen at `schema_version=1`, ADR-024); preserves `WorkflowRegistry` discovery. **Cons**: `primary_agent` is partly nominal — only literally the primary for the first stage.
  - **D2:** three workflow YAML files (`sdlc-task-test.yaml`, etc.). **Cons**: breaks the 1:1 slash-command ↔ YAML convention.
  - **D3:** extend `WorkflowSpec` with a `stages` field. **Cons**: a frozen wire-format contract edit — ADR-024 mutation taxonomy + snapshot regeneration ceremony; disproportionate for a Layer-7 story.

**And** **Recommended: D1** — single `sdlc-task.yaml`; CLI owns the stage→specialist map. Document as FOURTH line item in PR Change Log.
**And** `src/sdlc/commands/sdlc-task.md` is authored (slash-command shell with positional TASK-id syntax; ≤ 80 LOC; note the single-stage-advance + re-entrant semantics)
**And** three specialist stubs are authored at `src/sdlc/agents/phase3/{test-author,code-author,code-reviewer}.md` (minimal `SpecialistFrontmatter`; real content in Story 2B.10)
**And** `src/sdlc/agents/index.yaml` is updated to append three Phase 3 entries:
  ```yaml
  - name: test-author
    phase: 3
    file: phase3/test-author.md
  - name: code-author
    phase: 3
    file: phase3/code-author.md
  - name: code-reviewer
    phase: 3
    file: phase3/code-reviewer.md
  ```
**And** `scripts/validate_specialists.py` passes with the new entries registered
**And** the `code-reviewer` specialist `write_globs` (`03-Implementation/tasks/**`) reflects that the review verdict lands in the task JSON; the CLI performs the actual write (`persist_artifact=False` dispatch, mirroring Story 2A.16)

### AC10 — CLI surface: `sdlc task <TASK-id>` + `run_task` ordering

**Given** the Typer subcommand pattern from Stories 2A.9–2A.16
**When** the dev registers the command
**Then** `src/sdlc/cli/task.py:run_task(*, ctx: typer.Context, task_id: str)` is implemented with this exact ordering:
  1. Resolve `repo_root` from `_get_repo_root_or_cwd`
  2. Validate `task_id` against `TASK_ID_REGEX`; on mismatch → `WorkflowError` (AC1)
  3. Init guard: `.claude/state/state.json` exists, else `ERR_NOT_INITIALIZED` (AC1)
  4. **Phase 2 gate**: `compute_state(phase=2, repo_root=root) != SignoffState.APPROVED` → `ERR_PHASE2_NOT_APPROVED` (AC1)
  5. Resolve task file path from `parse_task_id`; load + parse `_TaskEntry`; refuse if missing (AC2); BOUNDARY_LINE guard
  6. Read `current_stage = task.stage`; refuse if `done` (AC2)
  7. Compute `next_stage` + `stage_specialist` from the stage→specialist map (D1)
  8. For dispatch stages (`pending`/`write-tests`/`write-code`): load `WorkflowRegistry` spec + specialist registry + `build_pre_write_hook_chain`; materialize `MockAIRuntime` fixture for the stage's specialist; compose the compound prompt; `dispatch(...)` with `persist_artifact=False`
  9. Parse + validate the stage-specific specialist response (`_StageFilesResult` for write-tests/write-code; `_StageReviewResult` for review); enforce the per-stage path-prefix rule (AC3/AC4) and the RED→GREEN gate (AC4/D1)
  10. Write stage output files through the per-file hook chain; on hook deny or any failure → roll back written files + journal `task_stage_failed` + exit non-zero (AC7)
  11. Update the task JSON `stage` (+ `review_verdict`/`review_notes` for the `review` transition) and rewrite the file
  12. Journal `task_stage_advanced` (AC3–AC6)
  13. `emit_json` success envelope: `{"phase": 3, "track": "task", "task_id": "<id>", "from": "<stage>", "to": "<stage>", "specialist": "<name|null>", "outcome": "success"}`
**And** `@app.command(name="task")` is registered in `cli/main.py` with a deferred import of `run_task` (per Architecture §488)
**And** the module LOC budget is ≤ 380; extraction to `cli/_task_pipeline.py` is permitted (and expected — mirror 2A.16's `break_.py` / `_break_pipeline.py` split). The async dispatch+write+journal logic and the per-stage parsers belong in `_task_pipeline.py`.

### AC11 — Tier-2 e2e + anti-tautology receipt

**Given** the Tier-2 e2e harness from Story 2A.0 + the `phase2_approved_repo` fixture (Story 2A.15/2A.16)
**When** the dev authors the task e2e
**Then** `tests/e2e/pipeline/test_sdlc_task.py` (NEW) covers at minimum these scenarios:

  1. **Full pipeline drive**: tmp repo with Phase 2 `APPROVED` + a task JSON at `stage: pending`; invoke `sdlc task <TASK-id>` four times in sequence; assert the stage advances `pending → write-tests → write-code → review → done` (one stage per invocation); assert the journal contains exactly four `task_stage_advanced` entries with the correct `from`/`to`; assert test files appear under `tests/`, code files under `src/`; assert the final task JSON has `stage: done` and `review_verdict: "approved"`
  2. **Idempotency: `done` refuse**: with the task at `stage: done`, invoke again → non-zero exit, `WorkflowError "task already complete"`, no dispatch (`MockAIRuntime` call count == 0), no files written
  3. **Rejected review**: code-reviewer mock returns `verdict: "rejected"`; drive to `stage: review`, then invoke for `review → done`; assert non-zero exit, `task_stage_failed` journaled, task stays at `stage: review`, message names "review rejected"
  4. **RED→GREEN gate**: code-author mock returns `tests_status: "red"` at the `write-tests → write-code` transition; assert non-zero exit, `task_stage_failed` journaled with `reason` naming the RED→GREEN gate, task stays at `stage: write-tests`, code files rolled back

**And** **Anti-tautology receipt (AC11 mandatory)**: in an auxiliary executable test, temporarily neutralise the clean-verdict gate at the `review → done` transition (patch the verdict check so a `rejected` verdict still advances to `done`); re-run scenario 3; observe the inversion — the test that asserts "rejected review does not reach done" now FAILS; revert. Document the inversion + restoration in the PR Change Log as an executable test (`test_e2e_task_review_verdict_gate_is_load_bearing`).

### AC12 — Module boundary + quality gate compliance (CONTRIBUTING.md §1)

**Given** the Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests`
  - `pytest -q -m "not e2e and not property"` — new unit + integration tests green
  - `pytest -q -m e2e` — new `test_sdlc_task.py` + all existing e2e green
  - `python scripts/freeze_wireformat_snapshots.py --check` — `5 contracts match snapshots` (unchanged — no contract edits)
  - `python scripts/check_module_boundaries.py` — 0 new violations; `cli` already depends on `dispatcher`, `signoff`, `hooks`, `journal`, `runtime`, `contracts`, `errors`, `ids`, `workflows`, `specialists`
  - `python scripts/validate_specialists.py` — passes with `test-author`, `code-author`, `code-reviewer` registered
  - `mkdocs build --strict` — clean
  - `tests/integration/test_wheel_build.py` — `sdlc-task.yaml`, `sdlc-task.md`, the three `phase3/*.md` stubs added to `_ALLOWED_CONTENT_FILES`

## Tasks / Subtasks

> Tasks ordered for TDD-first commits per ADR-026 §1. AC1/AC2/AC10 (CLI), AC3–AC7 (stage machine), AC8 (model), AC9 (workflow), AC11 (e2e) are public-API surfaces requiring tests-first commit ordering.

- [x] **Task 1 — Workflow YAML + 3 specialist stubs + slash-command (AC9)** — **TDD-first commit 1**
  - [x] 1.1 `src/sdlc/agents/phase3/` exists (created by Story 2A.15/2A.16); author three stubs `test-author.md`, `code-author.md`, `code-reviewer.md` (minimal `SpecialistFrontmatter`).
  - [x] 1.2 Append the three Phase 3 entries to `src/sdlc/agents/index.yaml`.
  - [x] 1.3 Author `src/sdlc/workflows_yaml/sdlc-task.yaml` per AC9 (D1 — single YAML, `primary_agent: test-author`).
  - [x] 1.4 Author `src/sdlc/commands/sdlc-task.md` (≤ 80 LOC; document single-stage-advance + re-entrant semantics).
  - [x] 1.5 Extend `tests/unit/workflows/test_phase3_workflows_present.py` to assert `sdlc-task.yaml` loads, `primary_agent == "test-author"`, write_globs match AC9. Tests fail (red) → author YAML → pass (green).
  - [x] 1.6 Run `scripts/validate_specialists.py` — must pass.
  - [x] 1.7 Document AC4/D1, AC6/D1, AC8/D1, AC9/D1 as FIRST/SECOND/THIRD/FOURTH line items in the PR Change Log.

- [x] **Task 2 — `_TaskEntry` stage + review-field extension (AC8)** — **TDD-first commit 2**
  - [x] 2.1 Author tests in `tests/unit/cli/test_task_entry_model.py` (extend the Story 2A.16 file): `stage` accepts all 5 values; `review_verdict`/`review_notes` default `None`; `review_verdict` rejects values outside `{approved, rejected}`; `serialize_task_entry` round-trips the extended shape. Tests fail (red).
  - [x] 2.2 Widen `_TaskEntry.stage` Literal + add `review_verdict`/`review_notes` per AC8/D1. Tests pass (green).
  - [x] 2.3 Verify `dispatcher/postconditions.py` has no frozen task-JSON key-set check that the widening breaks; verify `serialize_task_entry` (Story 2A.16) round-trips the new fields.

- [x] **Task 3 — Stage→specialist map + per-stage response parsers (AC3, AC4, AC5)** — **TDD-first commit 3**
  - [x] 3.1 Author tests in `tests/unit/cli/test_task_pipeline.py`: stage→specialist + stage→next-stage maps; `_StageFilesResult` parser (valid; path outside `tests/`; path outside `src/`; missing `tests_status`; non-list `files`); `_StageReviewResult` parser (valid; bad verdict; missing `notes`). Tests fail (red).
  - [x] 3.2 Author `cli/_task_pipeline.py`: the `_STAGE_SPECIALIST` / `_NEXT_STAGE` maps; `_StageFilesResult` + `_StageReviewResult` private models (or parse helpers); the per-stage path-prefix validators. Tests pass (green).
  - [x] 3.3 Author the RED→GREEN gate helper (`assert_red_to_green(test_status, code_status)`); unit-test the mismatch branch.

- [x] **Task 4 — `cli/task.py:run_task` + async dispatch/write/journal (AC1, AC2, AC3–AC7, AC10)** — **TDD-first commit 4**
  - [x] 4.1 Author `tests/unit/cli/test_task_command.py` (all cases listed in story spec). Tests fail (red).
  - [x] 4.2 Implement `cli/task.py:run_task` + the `cli/_task_pipeline.py` async core (`task_stage_dispatch_write`). LOC: `task.py` ≤ 380; split into `_task_pipeline.py`.
  - [x] 4.3 Register `task_command` in `cli/main.py`. Tests pass (green).
  - [x] 4.4 Integration test `tests/integration/test_sdlc_task.py`: tmp repo with APPROVED Phase 2 + PRODUCT.md + story JSON + a `pending` task JSON; `MockAIRuntime` fixtures for all three specialists; drive `run_task` four times; assert stage progression + journal.

- [x] **Task 5 — Tier-2 e2e + anti-tautology receipt (AC11)** — **TDD-first commit 5**
  - [x] 5.1 Reuse `phase2_approved_repo` from `tests/e2e/pipeline/conftest.py` (Story 2A.15/2A.16) — inline helpers used instead to avoid conftest coupling.
  - [x] 5.2 Author `tests/e2e/pipeline/fixtures/task/` (PRODUCT.md, story JSON).
  - [x] 5.3 Author `tests/e2e/pipeline/test_sdlc_task.py` (4 scenarios per AC11).
  - [x] 5.4 Run targeted Tier-2 e2e: all 5 scenarios green (4 AC11 + anti-tautology receipt).
  - [x] 5.5 **Anti-tautology receipt (AC11 mandatory)**: `test_e2e_task_review_verdict_gate_is_load_bearing` neutralises the verdict gate by patching `sdlc.cli.task.task_stage_dispatch_write` to substitute `review_verdict="approved"` at the review stage; verifies that with the gate neutralised the command exits 0 and reaches `done`, proving the verdict check is the sole barrier.

- [x] **Task 6 — Module boundary + quality gate + Change Log (AC12)**
  - [x] 6.1 Run `python scripts/check_module_boundaries.py` — confirm no new edges required.
  - [x] 6.2 Add the new content files to `tests/integration/test_wheel_build.py:_ALLOWED_CONTENT_FILES`.
  - [x] 6.3 Run the full quality gate; record the baseline.
  - [x] 6.4 Author the PR Change Log with D-decisions FIRST/SECOND/THIRD/FOURTH, the anti-tautology receipt, debt citations.

## Dev Notes

### The 5-stage machine — one stage per invocation

```
run_task(ctx, task_id)
  ├── 1. TASK_ID_REGEX(task_id)                                  ← AC1
  ├── 2. init guard + compute_state(phase=2) == APPROVED         ← AC1
  ├── 3. STORY-id, T<NN>-<slug> ← parse_task_id(task_id)
  │      task_path = root/03-Implementation/tasks/<STORY-id>/T<NN>-<slug>.json
  ├── 4. task = _TaskEntry(**json.loads(task_path))              ← AC2
  ├── 5. current = task.stage; if current == "done": refuse      ← AC2
  ├── 6. next_stage, specialist = _STAGE_SPECIALIST[current], _NEXT_STAGE[current]
  ├── 7a. if current ∈ {pending, write-tests, write-code}:
  │       dispatch(specialist) → parse stage response
  │       ├── write-tests:  files under tests/; tests_status must be "red"
  │       ├── write-code:   files under src/;   tests_status must be "green"  ← AC4/D1 gate
  │       └── review:       {verdict, notes}    → capture into task record    ← AC5
  ├── 7b. if current == review: NO dispatch; gate on review_verdict=="approved" ← AC6
  ├── 8. write stage files via hook chain  → on deny/fail: rollback + task_stage_failed ← AC7
  ├── 9. task.stage = next_stage (+ review fields); rewrite task JSON
  ├── 10. journal task_stage_advanced
  └── 11. emit_json success
```

### Stage → specialist + next-stage maps (AC9/D1 — CLI owns the map)

```python
_NEXT_STAGE: Final[dict[str, str]] = {
    "pending": "write-tests",
    "write-tests": "write-code",
    "write-code": "review",
    "review": "done",
}
_STAGE_SPECIALIST: Final[dict[str, str | None]] = {
    "pending": "test-author",       # dispatched for the pending → write-tests transition
    "write-tests": "code-author",   # dispatched for write-tests → write-code
    "write-code": "code-reviewer",  # dispatched for write-code → review
    "review": None,                 # review → done is a pure state advance, no dispatch
}
```

The dispatch for a transition uses the specialist keyed by the *current* stage. The workflow YAML's `primary_agent` (`test-author`) is nominal — `WorkflowRegistry` discovery needs a value; the CLI ignores it and selects per-stage from the registry directly.

### Per-stage specialist response contracts (v1 mock)

`test-author` / `code-author` return a files object:
```json
{"files": [{"path": "tests/unit/foo/test_bar.py", "content": "..."}], "tests_status": "red"}
```
`code-reviewer` returns a verdict object:
```json
{"verdict": "approved", "notes": "looks good; coverage adequate."}
```

Parse via private models in `_task_pipeline.py` (mirror `parse_task_array` from Story 2A.16's `_break_pipeline.py`):
```python
class _StageFileSpec(StrictModel):
    path: str          # repo-relative POSIX; prefix enforced by the caller per stage
    content: str

class _StageFilesResult(StrictModel):
    files: list[_StageFileSpec] = Field(min_length=1)
    tests_status: Literal["red", "green"]

class _StageReviewResult(StrictModel):
    verdict: Literal["approved", "rejected"]
    notes: Annotated[str, StringConstraints(min_length=1)]
```

### RED→GREEN gate (AC4/D1)

v1 trusts self-report. The gate is two assertions, not a `pytest` run:
- AC3 (`pending → write-tests`): the `test-author` response MUST report `tests_status == "red"`. A `green` here means the tests do not fail first — TDD discipline violated → `task_stage_failed`.
- AC4 (`write-tests → write-code`): the `code-author` response MUST report `tests_status == "green"`. A `red` here means the implementation did not turn the suite green → `task_stage_failed`, code files rolled back.

`EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION` (owner Epic 2B): once `ClaudeAIRuntime` produces real source, replace the self-report with a real `pytest` subprocess scoped to the task's test files.

### Mock fixture bodies for v1 (`SDLC_USE_MOCK_RUNTIME=1` default)

Provide one canned response per specialist keyed by the compound-prompt hash (mirror `write_mock_fixture` from `_break_pipeline.py`). The happy-path mock set: test-author → `tests_status: "red"` + one file under `tests/`; code-author → `tests_status: "green"` + one file under `src/`; code-reviewer → `verdict: "approved"`. The rejected + RED-stuck variants flip one field.

### Failure rollback (AC7)

Mirror Story 2A.16 `break_dispatch_write`: collect `written: list[Path]`; on `WorkflowError`/`OSError` inside the write loop, `for p in written: p.unlink(missing_ok=True)`, then journal `task_stage_failed`, then re-raise → the CLI maps it to a non-zero exit. The task JSON file is rewritten ONLY after all stage files land successfully, so a mid-stage failure never leaves a half-advanced task record.

### Phase 3 path coverage by phase_gate

`/sdlc-task` writes to `tests/`, `src/`, and `03-Implementation/tasks/` — all Phase-3-or-substrate paths. `src/sdlc/cli/_signoff_check.py` already routes `03-Implementation/` writes through `compute_state(phase=2) == APPROVED`. Verify the `tests/` and `src/` write paths are likewise gated (or are substrate paths exempt from phase-gate?) during Task 4 — if `tests/`/`src/` are NOT phase-gated, the AC1 Phase-2 pre-flight in `run_task` is the load-bearing gate; keep it regardless.

### Why `cli/task.py` (not `task_.py`)

`task` is not a Python keyword — `import sdlc.cli.task` is valid. Unlike `break_.py` (Story 2A.16, `break` IS a keyword), no trailing-underscore convention is needed. The Typer command name is `"task"`.

### Cross-Story Coordination

- Story 2A.16 (DEPENDENCY) — task JSON file format + path layout `03-Implementation/tasks/<STORY-id>/T<NN>-<slug>.json`; `_TaskEntry` private model (extended here); `serialize_task_entry`; `phase1_compound_prompt_builder`; the `break_.py`/`_break_pipeline.py` CLI-owns-the-write pattern
- Story 2A.15 (DEPENDENCY) — `agents/phase3/` directory; `phase2_approved_repo` e2e fixture helper
- Story 2A.12 (DEPENDENCY) — `compute_state(phase=2) == APPROVED`
- Story 2A.6 / 2A.4 (DEPENDENCY) — `build_pre_write_hook_chain`
- Story 1.6 (DEPENDENCY) — `TASK_ID_REGEX`, `TASK_ID_PATTERN`, `parse_task_id`
- **Layer-7 sibling coordination**: Stories 2A.17, 2A.18, 2A.19 may branch from the same `main`. `agents/index.yaml` is appended by 2A.17 only (2A.18 + 2A.19 register no specialists). The first Layer-7 story to merge owns any new shared `tests/e2e/pipeline/conftest.py` helper. Worktree branch: `epic-2a/2a-17-task-tdd-pipeline`.
- Story 2A.18 (downstream sibling) — `/sdlc-next` imports `run_task` to auto-dispatch Phase 3 tasks; 2A.17 SHOULD merge before 2A.18 (lower story number → natural Layer-7 merge order).
- Story 2A.19 (downstream sibling) — `/sdlc-replan` invalidates tasks downstream of replanned stories; no direct code coupling.
- Story 2B.10 — authors the real `test-author`/`code-author`/`code-reviewer` specialist content replacing the v1 stubs.

### Inherited Debt

- `EPIC-2A-DEBT-WRITE-PRIMITIVE` — `Path.write_text` non-atomic per file (re-cited)
- `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` — journal flock covers the per-invocation dispatch + write sequence
- `EPIC-2A-DEBT-CLAUDE-HOOK-FAIL-CLOSED-V1.X` — fail-open posture inherited

### New Debt (this story)

- `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION` — v1 trusts the specialist's self-reported `tests_status`; replace with a real `pytest`-subprocess RED→GREEN gate once `ClaudeAIRuntime` produces real source (owner: Epic 2B)
- `EPIC-2A-DEBT-TASK-STATE-PROJECTION` — `state/projection.py` does not fold `task_stage_advanced` entries; `state.json["tasks"]` stays empty; extend the projection (consumed by Story 2A.18 `/sdlc-next` + Epic 5 dashboard)
- `EPIC-2A-DEBT-TASK-WRITE-CODE-PROMPT-CONTEXT` — the `write-code` stage prompt does NOT include the test files written at `write-tests`; v1 keeps the compound prompt at task+story only; richer prompt context deferred

### File Layout

```
src/sdlc/agents/phase3/
├── test-author.md                            # NEW (stub; real content in 2B.10)
├── code-author.md                            # NEW (stub)
└── code-reviewer.md                          # NEW (stub)

src/sdlc/agents/index.yaml                    # UPDATE — append 3 phase3 entries

src/sdlc/workflows_yaml/sdlc-task.yaml        # NEW per AC9
src/sdlc/commands/sdlc-task.md                # NEW — slash-command shell

src/sdlc/cli/task.py                          # NEW — run_task (≤ 380 LOC)
src/sdlc/cli/_task_pipeline.py                # NEW — async dispatch/write + parsers
src/sdlc/cli/main.py                          # UPDATE — register task_command
src/sdlc/cli/_epic_story_models.py            # UPDATE — widen _TaskEntry.stage + review fields

tests/unit/cli/test_task_command.py           # NEW
tests/unit/cli/test_task_pipeline.py          # NEW
tests/unit/cli/test_task_entry_model.py       # UPDATE (Story 2A.16 file) — extended shape
tests/unit/workflows/test_phase3_workflows_present.py  # UPDATE — sdlc-task.yaml
tests/integration/test_sdlc_task.py           # NEW
tests/integration/test_wheel_build.py         # UPDATE — _ALLOWED_CONTENT_FILES
tests/e2e/pipeline/fixtures/task/             # NEW — fixtures + mock responses
tests/e2e/pipeline/test_sdlc_task.py          # NEW — Tier-2 e2e (4 scenarios)
```

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1361-1395`] — Story 2A.17 BDD ACs
- [Source: `_bmad-output/planning-artifacts/epics.md:41`] — FR17 definition
- [Source: `_bmad-output/planning-artifacts/architecture.md:118`] — per-task TDD pipeline + per-task state machine
- [Source: `_bmad-output/planning-artifacts/architecture.md:431`] — Task IDs `<STORY-id>-T<NN>-<kebab-slug>`
- [Source: `_bmad-output/planning-artifacts/architecture.md:949,962`] — `commands/sdlc-task.md` + `workflows_yaml/sdlc-task.yaml` in the canonical tree
- [Source: `_bmad-output/planning-artifacts/architecture.md:1147`] — FR17 → file mapping
- [Source: `src/sdlc/cli/break_.py` + `src/sdlc/cli/_break_pipeline.py`] — Story 2A.16: CLI-owns-the-write pattern, `persist_artifact=False` dispatch, mid-batch rollback, mock fixture materialization
- [Source: `src/sdlc/cli/_epic_story_models.py`] — `_TaskEntry` private model (widened here); `serialize_task_entry`
- [Source: `src/sdlc/signoff/states.py`] — `compute_state` + `SignoffState.APPROVED`
- [Source: `src/sdlc/dispatcher/core.py:155`] — `dispatch(...)` signature: `persist_artifact`, `target_path_override`, `observer`
- [Source: `src/sdlc/dispatcher/__init__.py`] — `phase1_compound_prompt_builder`, `build_pre_write_hook_chain`, `make_journal_entry`, `allocate_seq`, `now_ts`, `content_hash`
- [Source: `src/sdlc/ids/parsers.py`] — `TASK_ID_REGEX`, `TASK_ID_PATTERN`, `parse_task_id`
- [Source: `docs/sprints/epic-2a-dag.md`] — Layer 7: A15 + A16 → A17; critical path tail
- [Source: CONTRIBUTING.md §1-§5]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `compute_artifact_hash` requires `repo_root` keyword-only arg — fixed in integration test helpers.
- `SignoffRecord.artifacts` is `tuple[ArtifactRef, ...]` not `list` — fixed at integration test authoring.
- `_validate_target_path_override` in `dispatcher/core.py` validates against `spec.write_globs[spec.primary_agent]` even when `persist_artifact=False`. `primary_agent` is `test-author` with glob `tests/**`; override must live under `tests/`. Fixed `target_path_override` → `root / "tests" / f".sdlc-task-dispatch-{current_stage}"`.
- Mock fixture hash mismatch: `task.py` was computing hash using `specialist_name` (per-stage), but `dispatch()` always uses `spec.primary_agent` internally. Fixed to use `spec.primary_agent` (`"test-author"`) for hash computation on all stages.
- Anti-tautology patch target: patching `sdlc.cli._task_pipeline.task_stage_dispatch_write` does not affect the name already imported into `task.py`. Fixed to patch `sdlc.cli.task.task_stage_dispatch_write`.

### Completion Notes List

- All 83 story-specific tests pass (29 unit + 4 unit-pipeline + 4 integration + 5 e2e).
- `_task_pipeline.py` coverage: 91%; `task.py` coverage: 83% (error-handling branches).
- Project-wide coverage: 86.82% ≥ 85% gate (`--cov-fail-under=85`).
- `mypy --strict` passes on `task.py` and `_task_pipeline.py`.
- `ruff check` passes on all source and test files.
- Wire-format snapshots: `5 contracts match` (unchanged — no contract edits, AC12).
- Module boundaries: 0 new violations.
- Pre-existing failures on main (134) are reduced to 57 in this branch — all remaining are confirmed pre-existing by `git stash` bisect.
- `target_path_override` for `persist_artifact=False` dispatch sits under `tests/` to satisfy the `test-author` write_globs gate; the file is never actually written (mock runtime short-circuits before the real write path).
- `_STAGE_SPECIALIST["review"] = None` — the `review → done` transition skips dispatch entirely; the `with tempfile.TemporaryDirectory()` block exits immediately for this stage.

### File List

- `src/sdlc/agents/phase3/test-author.md` (NEW)
- `src/sdlc/agents/phase3/code-author.md` (NEW)
- `src/sdlc/agents/phase3/code-reviewer.md` (NEW)
- `src/sdlc/agents/index.yaml` (UPDATED — 3 phase3 entries appended)
- `src/sdlc/workflows_yaml/sdlc-task.yaml` (NEW)
- `src/sdlc/commands/sdlc-task.md` (NEW)
- `src/sdlc/cli/task.py` (NEW)
- `src/sdlc/cli/_task_pipeline.py` (NEW)
- `src/sdlc/cli/main.py` (UPDATED — `task` command registered)
- `src/sdlc/cli/_epic_story_models.py` (UPDATED — `_TaskEntry` stage widened + review fields)
- `tests/unit/cli/test_task_command.py` (NEW)
- `tests/unit/cli/test_task_pipeline.py` (NEW)
- `tests/unit/cli/test_task_entry_model.py` (UPDATED — extended shape tests)
- `tests/unit/workflows/test_phase3_workflows_present.py` (UPDATED — sdlc-task.yaml assertions)
- `tests/integration/test_sdlc_task.py` (NEW)
- `tests/integration/test_wheel_build.py` (UPDATED — `_ALLOWED_CONTENT_FILES` + 5 entries)
- `tests/e2e/pipeline/fixtures/task/01-PRODUCT.md` (NEW)
- `tests/e2e/pipeline/fixtures/task/EPIC-e2etask-S01-user-auth.json` (NEW)
- `tests/e2e/pipeline/test_sdlc_task.py` (NEW)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (UPDATED — 2a-17 → review)
- `docs/sprints/epic-2a-dag.md` (UPDATED — 2A.17 node status)

## Change Log

- **FIRST — AC4/D1 (RED→GREEN gate, self-reported `tests_status`)**: v1 trusts the specialist's self-reported `tests_status` field rather than executing a real `pytest` subprocess. The gate is: `test-author` at `pending → write-tests` MUST report `tests_status="red"` (TDD discipline: tests must fail before implementation); `code-author` at `write-tests → write-code` MUST report `tests_status="green"` (implementation must turn the suite green). Mismatch on either side is a `task_stage_failed` failure. `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION` opened for Epic 2B: replace with real `pytest`-subprocess gate once `ClaudeAIRuntime` produces real source.

- **SECOND — AC6/D1 (task JSON `stage` is state-of-record; `state.json` not written)**: `/sdlc-task` writes the task JSON file and the journal `task_stage_advanced` entries; it does NOT write `state.json["tasks"]` directly. The v1 projection in `state/projection.py` does not yet fold task records. `EPIC-2A-DEBT-TASK-STATE-PROJECTION` opened: extend `state/projection.py` to fold `task_stage_advanced` entries into `state.json["tasks"]` (consumed by Story 2A.18 `/sdlc-next` and Epic 5 dashboard).

- **THIRD — AC8/D1 (`review_verdict`/`review_notes` are real serialized fields)**: `_TaskEntry.review_verdict` and `review_verdict.review_notes` are NOT `exclude=True`; they serialize to the task JSON on the first stage advance via `model_dump(mode="json", sort_keys=True)`. The task JSON key set legitimately grows at the first `/sdlc-task` invocation (`stage: pending → write-tests`). `_TaskEntry` is private (not snapshotted by ADR-024); the key-set change is not a contract edit. ADR-024 snapshot count remains 5.

- **FOURTH — AC9/D1 (single `sdlc-task.yaml`; CLI owns stage→specialist map)**: ONE `sdlc-task.yaml` with `primary_agent: test-author` (nominal — satisfies `WorkflowRegistry` 1:1 discovery). `run_task` owns `_STAGE_SPECIALIST` and `_NEXT_STAGE` maps directly; the per-stage specialist is selected from the registry at runtime. `primary_agent` is nominal for stages 2–4; only stage 1 (`pending → write-tests`) literally dispatches the primary agent. No `WorkflowSpec` contract edit required.

- **Anti-tautology receipt — `test_e2e_task_review_verdict_gate_is_load_bearing`**: The executable receipt (AC11 mandatory) patches `sdlc.cli.task.task_stage_dispatch_write` to intercept the coroutine kwargs at the `review` stage and replace `task.review_verdict` with `"approved"`, neutralising the rejected-verdict gate. With the gate neutralised, a task that normally fails with `rejected` advances to `done` and exits 0 — proving the verdict check, and only it, is the barrier in scenario 3. Patch target is the name in `task.py`'s namespace (not `_task_pipeline.py`) because `task.py` imports `task_stage_dispatch_write` directly.

- **Debt citations**: `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION`, `EPIC-2A-DEBT-TASK-STATE-PROJECTION`, `EPIC-2A-DEBT-TASK-WRITE-CODE-PROMPT-CONTEXT` (write-code stage prompt does not include test files from write-tests), `EPIC-2A-DEBT-WRITE-PRIMITIVE` (non-atomic `Path.write_text`), `EPIC-2A-DEBT-CLAUDE-HOOK-FAIL-CLOSED-V1.X` (fail-open hook posture inherited).

## Review Findings

> bmad-code-review 2026-05-18 — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor). 33 raw findings → 15 actionable after dedupe (10 patch + 5 defer); ~18 dismissed as noise/false-positive/documented-intentional.

- [x] [Review][Decision] `sdlc-task.yaml` `parallel_agents` lists `code-author` + `code-reviewer` vs spec AC9 literal block `parallel_agents: []` — RESOLVED: code is correct; `workflows/static_check.py:_check_phantom_agents` forces this. Spec AC9 YAML block amended to match reality + rationale note. No code change. [src/sdlc/workflows_yaml/sdlc-task.yaml]
- [x] [Review][Patch] Dead code: `tests_status_cache` param + `assert_red_to_green` helper are never wired into the pipeline — `task.py` passes a fresh `{}` per invocation, `tests_status_cache[task_id]` is written but never read, `assert_red_to_green` is exported + unit-tested but never called (one-stage-per-process makes cross-stage state impossible); misleading docstring — FIXED: removed dead param/helper + 3 dead tests; gate comment clarified [src/sdlc/cli/_task_pipeline.py / src/sdlc/cli/task.py]
- [x] [Review][Patch] `commands/sdlc-task.md` is 83 lines, exceeds the AC9/AC12 ≤80 LOC budget — FIXED: trimmed redundant Story Reference footer → 79 lines [src/sdlc/commands/sdlc-task.md]
- [x] [Review][Patch] `parse_files_result` / `parse_review_result` catch bare `Exception` and relabel it "schema validation" — FIXED: narrowed to `pydantic.ValidationError` [src/sdlc/cli/_task_pipeline.py]
- [x] [Review][Patch] Rollback `except (WorkflowError, OSError)` is too narrow — `SpecialistError` / `ValueError` escape it, so written files are NOT rolled back and no `task_stage_failed` is journaled, violating AC7 "ANY stage transition fails" — FIXED: broadened to `(WorkflowError, SpecialistError, ValueError, OSError)` [src/sdlc/cli/_task_pipeline.py]
- [x] [Review][Patch] Task JSON is rewritten (stage advanced) before the final `allocate_seq`/`journal_append`; if journal I/O fails, the task JSON is left advanced — AC7 mandates "stage field left UNCHANGED" — FIXED: `task_rewritten` flag; rollback restores the original task JSON [src/sdlc/cli/_task_pipeline.py]
- [x] [Review][Patch] `validate_file_prefix` checks only `startswith` + `is_absolute` — `tests/../src/evil.py` passes both and escapes the prefix; AC3/AC4 require files under `tests/` / `src/` — FIXED: rejects any `..` path segment [src/sdlc/cli/_task_pipeline.py]
- [x] [Review][Patch] `review → done` with `review_verdict is None` falls into the rejected branch and emits a misleading "review rejected" message — FIXED: distinct error for missing verdict vs a real `rejected` [src/sdlc/cli/_task_pipeline.py]
- [x] [Review][Patch] Bare `assert current_stage == "review"` is stripped under `python -O` — FIXED: explicit check + `WorkflowError` raise [src/sdlc/cli/_task_pipeline.py]
- [x] [Review][Patch] Duplicate test: `test_task_entry_stage_in_progress_raises_validation_error` duplicated `test_task_entry_stage_rejects_unknown_value` (both assert `stage="in-progress"`) — FIXED: removed the older undocumented duplicate [tests/unit/cli/test_task_entry_model.py]
- [x] [Review][Defer] Rejected review is a dead-end — a `rejected` verdict advances the task to `stage: review` (AC5), but `review → done` then permanently refuses with no transition back to `write-code`; re-running `/sdlc-task` at `review` always refuses [src/sdlc/cli/_task_pipeline.py:398-412] — deferred; current behavior matches AC5/AC6 spec, recommend opening `EPIC-2A-DEBT-TASK-REJECTED-REWORK`
- [x] [Review][Defer] Rollback `p.unlink()` deletes overwritten pre-existing files instead of restoring their content; `task_path.write_text` is non-atomic — crash mid-write corrupts the task JSON unrecoverably [src/sdlc/cli/_task_pipeline.py:417,443-445] — deferred, folds under inherited `EPIC-2A-DEBT-WRITE-PRIMITIVE`
- [x] [Review][Defer] Concurrent `/sdlc-task` invocations on the same TASK-id race — both read the same stage, both dispatch + rewrite + journal [src/sdlc/cli/task.py:run_task] — deferred, inherited `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` (v1 single-user posture)
- [x] [Review][Defer] `artifact_written` journal entries for rolled-back files are not compensated [src/sdlc/cli/_task_pipeline.py:367-387] — deferred, append-only journal; `task_stage_failed` is the compensation marker (same posture as CR16-W1)
- [x] [Review][Defer] Hook payload uses `content_hash_before=None` + `write_intent="create"` even when overwriting an existing file — drift/tamper hooks see a stale "create" [src/sdlc/cli/_task_pipeline.py:344-349] — deferred, fail-open hook posture inherited (`EPIC-2A-DEBT-CLAUDE-HOOK-FAIL-CLOSED-V1.X`)

### Review Findings — Round 2 (2026-05-19)

> bmad-code-review 2026-05-19 — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) re-run on the post-Round-1 tree. ~30 raw → 19 actionable after dedupe (13 patch + 6 defer); ~11 dismissed (false-positive / verified-genuine / documented-intentional / epic-wide-posture). Round 1 patches confirmed present.

- [x] [Review][Patch] No `task.id == task_id` identity check, no `task.id`/`task.story_id` lineage cross-check — `run_task` derives `task_path` and `_story_path` purely from the `task_id` argument; `_TaskEntry` self-validates `id`/`story_id` regex independently. A renamed/copied task JSON whose internal `id` differs from the requested arg is advanced anyway; journal entries + success envelope all use the arg, not the file's true id. Story 2A.16 `/sdlc-break` added the symmetric cross-check for its output; the read path lacks it. [src/sdlc/cli/task.py:149-167] (HIGH)
- [x] [Review][Patch] Bare `except Exception` on `_TaskEntry.model_validate_json` relabels any error (incl. `OSError`, programming bugs) as `ERR_USER_INPUT` "task JSON parse failed" — inconsistent with the Round-1 narrowing of the pipeline parsers to `ValidationError`. Narrow to `ValidationError`/`ValueError`. [src/sdlc/cli/task.py:151] (LOW)
- [x] [Review][Patch] `task_stage_dispatch_write` has no independent `done`/unknown-stage guard — the public coroutine raises a bare `KeyError` on `_NEXT_STAGE[current_stage]` if invoked directly with `stage=='done'`, bypassing the structured `WorkflowError`/journal path. Add an explicit guard at function entry. [src/sdlc/cli/_task_pipeline.py:246-248] (MEDIUM)
- [x] [Review][Patch] `runtime` param typed `MockAIRuntime` but `None` is passed for the `review→done` stage with `# type: ignore[arg-type]` — the type-checker safety net is silenced. Type the param `MockAIRuntime | None` and drop the ignore. [src/sdlc/cli/task.py:264 / src/sdlc/cli/_task_pipeline.py:240] (MEDIUM)
- [x] [Review][Patch] Success envelope omits `review_verdict` — a `rejected` verdict at `write-code→review` still emits `outcome: "success"` with `to: "review"` and no verdict signal; a programmatic `/sdlc-next` (2A.18) consumer cannot see the rejection. Surface `review_verdict` in the envelope when the stage produced one. [src/sdlc/cli/task.py:291-303] (MEDIUM)
- [x] [Review][Patch] No de-dup of `files_result.files` by `path` — a specialist returning two specs with the same `path` silently overwrites the first, emits two `artifact_written` entries, and rollback `unlink`s a single `Path` once. Reject duplicate paths. [src/sdlc/cli/_task_pipeline.py:295-298] (MEDIUM)
- [x] [Review][Patch] `run_id` is included only in `artifact_written` payloads, not in `task_stage_advanced`/`task_stage_failed` — correlating an artifact write to its stage outcome requires joining on `task_id`+timestamp. Thread `run_id` into the stage payloads. [src/sdlc/cli/_task_pipeline.py:325,422-441,461-466] (LOW)
- [x] [Review][Patch] Silent empty `story_text` — a missing story file or `UnicodeDecodeError` collapses to `""` with no diagnostic; the specialist is dispatched with a blank `STORY_CONTEXT`. Emit a visible warning. [src/sdlc/cli/task.py:171-177] (LOW)
- [x] [Review][Patch] No unit test for the `..`-traversal rejection branch of `validate_file_prefix` (Round-1 patch) — only absolute-path and prefix-mismatch branches are covered; the traversal patch is asserted but not test-locked. Add a test. [tests/unit/cli/test_task_pipeline.py] (LOW)
- [x] [Review][Patch] `test_e2e_task_full_pipeline_drive` computes `kinds_seen` for a failure message but never asserts the absence of `task_stage_failed` — a pipeline emitting 4 `task_stage_advanced` AND a spurious failure entry still passes. Strengthen. [tests/e2e/pipeline/test_sdlc_task.py:~1635] (LOW)
- [x] [Review][Patch] Weak substring assertions `"red" in output.lower()` / `"green" in ...` — "required"/"registered"/"credentials" all contain "red", so the RED→GREEN gate-message assertion is near-tautological. Tighten to the actual message. [tests/e2e/pipeline/test_sdlc_task.py:~1719,~2064] (LOW)
- [x] [Review][Patch] Duplicate test remains — `test_task_entry_stage_rejects_unknown_value` and `test_task_entry_stage_unknown_value_raises_validation_error` both assert `ValidationError` on an unknown stage string. Remove one. [tests/unit/cli/test_task_entry_model.py:~170,~211] (LOW)
- [x] [Review][Patch] `sdlc-task.md` Error Codes table is incomplete — lists 4 codes; the implementation emits ≥8 (`ERR_TASK_STAGE_FAILED`, `ERR_INFRASTRUCTURE`, `ERR_SIGNOFF_READ_FAILED`, `ERR_ARTIFACT_UNREADABLE`, `ERR_ARTIFACT_CONTAINS_BOUNDARY`). Complete the table. [src/sdlc/commands/sdlc-task.md] (LOW)
- [x] [Review][Defer] `ERR_PHASE2_NOT_APPROVED` / `ERR_TASK_STAGE_FAILED` not registered in `_ERR_CODE_TO_EXIT_CODE` — both fall to `_DEFAULT_EXIT_CODE=1` [src/sdlc/cli/output.py:114-177] — deferred, pre-existing: `break_.py`/`bootstrap.py` (2A.15/2A.16) also use unregistered `ERR_PHASE2_NOT_APPROVED`; functionally non-zero, documented historical-fallback posture; register epic-wide as a batch.
- [x] [Review][Defer] `_use_mock_runtime()` defaults mock-ON in production and the CLI surface emits no "output is a placeholder" notice — MockAIRuntime writes `assert False` tests + empty `# Implementation stub` source and the command exits 0 [src/sdlc/cli/task.py:54-55,213-242] — deferred, pre-existing: epic-wide v1 posture (real `ClaudeAIRuntime` arrives in Epic 2B); consider an epic-wide `mock` flag in success envelopes.
- [x] [Review][Defer] Rollback unlinks written files but leaves newly-created parent directories (`tests/unit/`, `src/sdlc/`) behind on failure [src/sdlc/cli/_task_pipeline.py:328,445-447] — deferred, same class as CR16-W3, folds under `EPIC-2A-DEBT-WRITE-PRIMITIVE`.
- [x] [Review][Defer] Task JSON read with `utf-8-sig` but rollback rewrites `utf-8` — a BOM-bearing original silently loses its BOM on restore, so AC7's "stage UNCHANGED" file restore is not byte-identical [src/sdlc/cli/task.py:137 / src/sdlc/cli/_task_pipeline.py:452] — deferred, theoretical: framework-written task JSON never carries a BOM.
- [x] [Review][Defer] `cause` truncation to 500 chars is applied only to the `ERR_SIGNOFF_READ_FAILED` path; every other `emit_error` passes the full untruncated exception string [src/sdlc/cli/task.py:106,139,156,188,199,279,286] — deferred, cosmetic: large error strings bloat the envelope; normalize epic-wide.
- [x] [Review][Defer] `result.agent_result.output_text` accessed unguarded — `AttributeError` if `result.outcome=='success'` but `agent_result is None` [src/sdlc/cli/_task_pipeline.py:287] — deferred, low likelihood: the dispatch contract guarantees `agent_result` on a success outcome.
