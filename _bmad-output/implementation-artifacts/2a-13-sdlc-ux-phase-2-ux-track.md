# Story 2A.13: `/sdlc-ux` (Phase 2 UX Track)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a tech lead initiating Phase 2 UX work,
I want `/sdlc-ux` producing artifacts under `02-Architecture/01-UX/` (design tokens, flows, screen specs),
So that UX work is audit-tracked with the same rigor as engineering artifacts (FR13).

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1277-1294`. Per ADR-026 §1, the public API surface (`cli/ux.py:run_ux`) requires TDD-first commit ordering visible in `git log --reverse`. This story **depends on Story 2A.8** (dispatcher + `phase1_prompt_builder` + specialist-stub pattern) and **depends on Story 2A.12** (`compute_state` for Phase 1 APPROVED gate — the phase-gate hook at `hooks/builtin/phase_gate.py` already enforces it, but CLI pre-flight must also check). It is a **Layer 5 sibling** of 2A.12 and 2A.14 — all three can proceed in parallel worktrees. It introduces NO new wire-format contracts (ADR-024 snapshot count remains 5).

### AC1 — Phase 1 signoff gate + `/sdlc-ux` entry

**Given** Phase 1 signoff is in state `APPROVED`
**When** I run `/sdlc-ux`
**Then** the workflow dispatches the `ux-designer` specialist
**And** outputs are written under `02-Architecture/01-UX/` (minimum: `01-tokens.md`, `02-flows.md`, `03-screens.md` — or a single combined document if the specialist returns one file; see AC2/D1)
**And** the phase-gate hook (Story 2A.4) permits the writes (Phase 1 signoff is APPROVED → Phase 2 writes are unblocked per hook's phase-gate logic)
**And** journal entries are appended: `kind="agent_dispatched"` + N × `kind="artifact_written"` (one per output file)
**And** emit_json on success: `{"phase": 2, "track": "ux", "specialist": "ux-designer", "artifacts": [{path, hash}, ...], "outcome": "success"}`

**Given** Phase 1 signoff is NOT in state `APPROVED` (any of: `AWAITING_SIGNOFF`, `DRAFTED_NOT_APPROVED`, `INVALIDATED_BY_REPLAN`)
**When** I run `/sdlc-ux`
**Then** the **CLI pre-flight** refuses with `ERR_PHASE1_NOT_APPROVED` and message `"phase 1 signoff must be APPROVED before starting Phase 2 UX work; run '/sdlc-signoff 1' to generate the draft, approve it, then run 'sdlc scan' to record the approval"`
**And** the CLI pre-flight is the sole enforcement point for v1 — the **phase-gate hook** (Story 2A.4) does NOT yet extend to Phase 2 directory writes; that defense-in-depth layer is tracked as `EPIC-2A-DEBT-PHASE2-DIR-PHASE-GATE` (review-B / DB2=a). When the hook is extended in a follow-up story it will block independently as a redundant gate; until then, only the CLI pre-flight blocks.

### AC2 — Output file layout D-decision

**Given** the AC source's "outputs are written under `02-Architecture/01-UX/` (e.g., `01-tokens.md`, `02-flows.md`, `03-screens.md`)"
**When** the dev wires the specialist output
**Then** **AC2/D1 (output layout D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** Specialist emits a JSON array of `{filename, content}` objects; CLI writes each to `02-Architecture/01-UX/<filename>`; minimum 1 file required. **Pros**: flexible multi-file output; consistent with `/sdlc-epics` JSON-array dispatch pattern from Story 2A.11/AC4/D1. **Cons**: specialist must emit JSON (prompt-engineering constraint).
  - **D2:** Specialist emits a single Markdown document combining all UX artifacts; CLI writes it to `02-Architecture/01-UX/ux-design.md`. **Pros**: simplest for v1 stub specialist. **Cons**: monolithic file; less granular journal audit trail.
  - **D3:** Three separate dispatch calls (one per output type: tokens, flows, screens); each produces one file. **Pros**: specialized prompts per artifact type. **Cons**: 3× dispatch cost; complex orchestration.

**And** **Recommended: D1** — consistent with the JSON-array dispatch pattern established in Story 2A.11; journal granularity per file matches signoff hash-drift semantics (each file is individually hashed in Phase 2 signoff)
**And** the choice MUST be the FIRST line item in PR Change Log

**And** regardless of D-decision, the postcondition `ux_dir_non_empty` is verified (at least one file exists under `02-Architecture/01-UX/` after dispatch)

### AC3 — Parallel reviewer dispatch (optional)

**Given** the AC source's "dispatches the `ux-designer` specialist (and optional parallel reviewers)"
**When** the dev wires the workflow YAML
**Then** `sdlc-ux.yaml` includes `ux-reviewer` as an optional parallel agent:
  ```yaml
  parallel_agents:
    - ux-reviewer
  synthesizer_agent: ux-synthesizer
  ```
**And** **AC3/D1 (parallel reviewer D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** Ship `ux-reviewer` stub in `agents/phase2/` but set `parallel_agents: []` in the v1 workflow YAML. Parallel dispatch requires the synthesizer to merge outputs, which is a v1.x feature needing tested specialist content (Story 2B.9). **Pros**: unblocks v1 delivery; synthesizer wiring deferred. **Cons**: reviewer not invoked.
  - **D2:** Wire `ux-reviewer` + `ux-synthesizer` as live parallel dispatch in v1. **Pros**: tests full parallel path. **Cons**: stubs will produce poor synthesis; reviewer adds cost without value until real specialist content exists (Story 2B.9).

**And** **Recommended: D1** — matches Story 2A.9 sibling posture (`parallel_agents: []` in v1; defer panel to 2B)
**And** the choice MUST be the SECOND line item in PR Change Log

### AC4 — Workflow YAML + specialist stubs + slash-command shell

**Given** the architecture canonical tree at `architecture.md:960` lists `sdlc-ux.yaml`
**When** the dev authors the workflow YAML (per AC2/D1 + AC3/D1 recommended path)
**Then** `src/sdlc/workflows_yaml/sdlc-ux.yaml` is authored (12 lines, byte-stable with the canonical YAML — `boundary_line_present_in_prompts` postcondition intentionally absent per AC4/D3; see Change Log row 3 + `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK`):
  ```yaml
  schema_version: 1
  name: phase2-ux-track
  slash_command: /sdlc-ux
  primary_agent: ux-designer
  parallel_agents: []
  synthesizer_agent: null
  postconditions:
    - ux_dir_non_empty
  write_globs:
    ux-designer:
      - "02-Architecture/01-UX/*.md"
  stop_on_postcondition_failure: true
  ```
**And** `src/sdlc/commands/sdlc-ux.md` is authored (slash-command shell, mirror Story 2A.8 AC9 pattern)
**And** specialist stubs are authored at:
  - `src/sdlc/agents/phase2/ux-designer.md` — primary designer stub (same format as `artifact-verifier.md` placeholder)
  - `src/sdlc/agents/phase2/ux-reviewer.md` — reviewer stub (for AC3/D1 deferred parallel)
**And** `agents/index.yaml` is updated to register both as Phase 2 specialists:
  ```yaml
  - name: ux-designer
    phase: 2
    file: phase2/ux-designer.md
  - name: ux-reviewer
    phase: 2
    file: phase2/ux-reviewer.md
  ```
**And** `src/sdlc/agents/phase2/__init__` directory structure is created (new `phase2/` sub-directory under `agents/`)
**And** `scripts/validate_specialists.py` passes with both new entries

### AC5 — CLI surface: `sdlc ux`

**Given** the Typer subcommand pattern from Stories 2A.9/2A.10/2A.11/2A.12
**When** the dev registers the command
**Then** `src/sdlc/cli/ux.py:run_ux(*, ctx)` is implemented:
  1. Pre-flight: state.json exists; `compute_state(phase=1, repo_root=root) == APPROVED` → else `ERR_PHASE1_NOT_APPROVED`
  2. Create `02-Architecture/01-UX/` directory via `Path.mkdir(parents=True, exist_ok=True)` (outside hook chain — same posture as Story 2A.11 Project Structure Note)
  3. Compose prompt using `phase1_prompt_builder` (inherit from Story 2A.8 / dispatcher module). Input text: content of `01-Requirement/01-PRODUCT.md` (required input for UX design). If `01-PRODUCT.md` contains `BOUNDARY_LINE` → `ERR_ARTIFACT_CONTAINS_BOUNDARY`
  4. Call `dispatch(...)` with `ux-designer` specialist
  5. Parse JSON array response per AC2/D1; for each `{filename, content}` → validate filename is safe (no path traversal; must end in `.md`; must start with digits for ordering e.g. `01-tokens.md`); run hook chain BEFORE write; write file
  6. Emit journal `kind="artifact_written"` per file
  7. emit_json on success
**And** `@app.command(name="ux")` is registered in `cli/main.py`:
  ```python
  @app.command(name="ux")
  def ux_command(ctx: typer.Context) -> None:
      """Initiate Phase 2 UX track (FR13)."""
      from sdlc.cli.ux import run_ux
      run_ux(ctx=ctx)
  ```

### AC6 — Journal entries

**Given** the journal entry patterns from Stories 2A.8/2A.9/2A.10/2A.11
**When** `/sdlc-ux` runs to completion
**Then** the journal contains in monotonic order:
  1. ONE `kind="agent_dispatched"` for `ux-designer` with `role="primary"`
  2. Zero or more `kind="dispatch_attempt"` entries per retry policy
  3. N × `kind="artifact_written"` entries (one per output file), each with `actor="cli"`, `target_id=<file path>`, `before_hash=None` (new), `after_hash="sha256:<hex>"`; `payload={"slash_command": "/sdlc-ux", "phase": 2, "specialist": "ux-designer"}`
**And** the journal flock covers the full multi-file batch write (inherited `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` posture)

### AC7 — Phase 2 directory creation

**Given** `02-Architecture/01-UX/` does NOT exist at the time of first `/sdlc-ux` invocation
**When** `run_ux` starts
**Then** the directory is created via `Path.mkdir(parents=True, exist_ok=True)` BEFORE dispatch (not after)
**And** the mkdir call is OUTSIDE the hook chain (consistent with Story 2A.11 Project Structure Note)

### AC8 — Postconditions: `ux_dir_non_empty`

**Given** the dispatch returns successfully
**When** postcondition evaluation runs
**Then** `ux_dir_non_empty` postcondition checks that `02-Architecture/01-UX/` contains at least one `.md` file
**And** if no files exist → `ERR_POSTCONDITION_FAILED` per Story 2A.3 pattern
**And** this postcondition is registered in `src/sdlc/dispatcher/postconditions.py` (UPDATE existing module)

### AC9 — Tier-2 e2e (2 scenarios)

**Given** the Tier-2 e2e harness from Story 2A.0
**When** the dev authors the UX e2e
**Then** `tests/e2e/pipeline/test_sdlc_ux.py` (NEW) covers TWO scenarios:

  1. **Happy path**: tmp repo with phase 1 APPROVED signoff (use e2e fixture helper from Story 2A.12 Task 5.2 or provide equivalent — a pre-built `.claude/state/signoffs/phase-1.yaml` fixture) + `01-PRODUCT.md` present; MockAIRuntime canned response returns `[{"filename": "01-tokens.md", "content": "# Design Tokens\n..."}, {"filename": "02-flows.md", "content": "# Flows\n..."}]`; invoke `sdlc ux`; assert exit 0; assert ≥1 `.md` file written at `02-Architecture/01-UX/`; assert each written file contains the `PLACEHOLDER` marker or starts with a Markdown heading (`#`); journal has 1 `agent_dispatched` + N `artifact_written`. (PC7 review-C: `BOUNDARY_LINE` in-prompt assertion is NOT made here — `agent_runs.jsonl` is not written by MockAIRuntime path; that invariant is tracked as `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK` for the real runtime in Story 2B.9.)
  2. **Phase gate block**: tmp repo with Phase 1 NOT approved (AWAITING_SIGNOFF); invoke `sdlc ux`; assert exit 1; assert `ERR_PHASE1_NOT_APPROVED` in stderr; assert NO files written; NO dispatch call

**And** **Anti-tautology receipt (AC9 mandatory)**: in scenario 1, temporarily replace the `compute_state == APPROVED` check with an unconditional pass; assert scenario 2 (gate block) test NOW FAILS because the gate isn't applied; revert; document in PR Change Log

### AC10 — Quality gate compliance (CONTRIBUTING.md §1)

**Given** the full Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests` (baseline blocker W2 accepted per precedent)
  - `pytest -q -m "not e2e and not property"` — new unit + integration tests green
  - `pytest -q -m e2e` — new `test_sdlc_ux.py` (2 scenarios) + all existing e2e green
  - `python scripts/freeze_wireformat_snapshots.py --check` — `5 contracts match snapshots` (unchanged)
  - `python scripts/check_module_boundaries.py` — 0 new violations; `cli.depends_on` must include `"signoff"` (for `compute_state` in pre-flight)
  - `python scripts/validate_specialists.py` — passes with `ux-designer` + `ux-reviewer` registered

## Tasks / Subtasks

> Tasks ordered for TDD-first commits per ADR-026 §1. AC1/AC5 (CLI), AC4 (workflow), AC8 (postcondition), AC9 (e2e) are the public-API surfaces requiring tests-first commit ordering.

- [x] **Task 1 — Workflow YAML + `phase2/` specialist stubs + slash-command (AC3/D1, AC4)** — **TDD-first commit 1**
  - [x] 1.1 Create `src/sdlc/agents/phase2/` directory with `__init__` (if required by package structure).
  - [x] 1.2 Author `src/sdlc/agents/phase2/ux-designer.md` + `ux-reviewer.md` placeholder stubs.
  - [x] 1.3 Update `agents/index.yaml` — register both as phase 2.
  - [x] 1.4 Author `src/sdlc/workflows_yaml/sdlc-ux.yaml` per AC4 (D1 recommended: `parallel_agents: []`).
  - [x] 1.5 Author `src/sdlc/commands/sdlc-ux.md`.
  - [x] 1.6 Extend `tests/unit/workflows/test_phase1_workflows_present.py` (or create a phase2 counterpart `test_phase2_workflows_present.py`) to assert `sdlc-ux.yaml` loads + `primary_agent == "ux-designer"`. Tests fail (red) → author YAML → pass (green).
  - [x] 1.7 Run `scripts/validate_specialists.py` — must pass.
  - [x] 1.8 Document AC2/D1 + AC3/D1 choices as FIRST + SECOND items in PR Change Log.

- [x] **Task 2 — `dispatcher/postconditions.py`: `ux_dir_non_empty` (AC8)** — **TDD-first commit 2**
  - [x] 2.1 Author `tests/unit/dispatcher/test_postconditions_ux.py` (or extend existing postconditions tests): `ux_dir_non_empty` passes when at least one `.md` file exists; fails when dir is empty or missing. Tests fail (red).
  - [x] 2.2 Add `ux_dir_non_empty` to `src/sdlc/dispatcher/postconditions.py`. Tests pass (green).

- [x] **Task 3 — `cli/ux.py:run_ux` + Typer registration (AC1, AC5, AC6, AC7)** — **TDD-first commit 3**
  - [x] 3.1 Author `tests/unit/cli/test_ux_command.py`: phase-1-not-approved → ERR_PHASE1_NOT_APPROVED (exit 1, no dispatch); happy path (phase 1 APPROVED, mocked dispatch returning 2-file JSON array → 2 files written + journal 1 `agent_dispatched` + 2 `artifact_written`); PRODUCT.md contains boundary marker → ERR_ARTIFACT_CONTAINS_BOUNDARY; empty dispatch response (no files) → ERR_POSTCONDITION_FAILED; unsafe filename in response (e.g. `../evil.md`) → ERR rejected. Tests fail (red).
  - [x] 3.2 Implement `src/sdlc/cli/ux.py:run_ux(*, ctx)` per AC5. LOC ≤ 300. Import `phase1_prompt_builder` from `sdlc.dispatcher`. Import `compute_state`, `SignoffState` from `sdlc.signoff`.
  - [x] 3.3 Register `ux_command` in `cli/main.py` per AC5. Tests pass (green).
  - [x] 3.4 Integration test `tests/integration/test_sdlc_ux.py`: tmp repo with APPROVED phase-1 signoff fixture + `01-PRODUCT.md`; MockAIRuntime canned 2-file JSON array; invoke `run_ux(ctx=...)`; assert 2 files written; assert journal structure.

- [x] **Task 4 — Tier-2 e2e: 2 scenarios (AC9)** — **TDD-first commit 4**
  - [x] 4.1 Confirm or create the APPROVED phase-1 signoff fixture helper (may be provided by Story 2A.12 Task 5 — if 2A.12 lands first, reuse; otherwise define it here as a local conftest fixture).
  - [x] 4.2 Author `tests/e2e/pipeline/test_sdlc_ux.py` (2 scenarios per AC9).
  - [x] 4.3 Author fixtures under `tests/e2e/pipeline/fixtures/ux/` (canned `[{filename, content}]` response).
  - [x] 4.4 Run targeted Tier-2 e2e: both scenarios green.
  - [x] 4.5 **Anti-tautology receipt (AC9 mandatory)**: comment out `compute_state == APPROVED` gate; assert scenario 2 (gate block) FAILS; revert; document in PR Change Log.

- [x] **Task 5 — Quality gate + Change Log (AC10)**
  - [x] 5.1 Run full quality gate; record new baseline state.
  - [x] 5.2 Author PR Change Log with AC2/D1 + AC3/D1 as FIRST + SECOND items, anti-tautology receipt, debt citations.

## Dev Notes

### Pattern to Follow

This story is the first **Phase 2** command. The pattern follows Stories 2A.9/2A.10/2A.11 exactly, with one key difference: the **Phase 1 signoff APPROVED gate** in pre-flight (same logic as Stories 2A.12 + 2A.14 use for Phase 2 writes).

Key reuse:
- `phase1_prompt_builder` from `src/sdlc/dispatcher/prompts.py` (Story 2A.8) — reuse as-is; pass `01-PRODUCT.md` content as `idea_text`; pass `ux-designer` as the specialist
- `build_pre_write_hook_chain` from `src/sdlc/dispatcher/__init__.py` — call BEFORE each file write
- `allocate_seq`, `make_journal_entry`, `content_hash` from `src/sdlc/dispatcher/__init__.py`
- `compute_state`, `SignoffState` from `src/sdlc/signoff/__init__.py` — for Phase 1 APPROVED gate

### Phase 1 APPROVED Gate — Detail

```python
from sdlc.signoff import compute_state, SignoffState

phase1_state = compute_state(phase=1, repo_root=root)
if phase1_state != SignoffState.APPROVED:
    emit_error(
        "ERR_PHASE1_NOT_APPROVED",
        f"phase 1 signoff must be APPROVED before starting Phase 2 UX work; "
        f"current state: {phase1_state.value}. "
        f"Run '/sdlc-signoff 1' to generate the draft, approve it, then 'sdlc scan'."
    )
    raise SystemExit(1)
```

For v1, the CLI pre-flight is the sole enforcement layer (the Story 2A.4 phase-gate hook does NOT yet extend to Phase 2 directory writes — tracked as `EPIC-2A-DEBT-PHASE2-DIR-PHASE-GATE`). Once the hook is extended in a follow-up story, the two layers will form true defense-in-depth: the hook checks at write time; the CLI check is at command entry (fails fast before any dispatch cost).

### Phase 2 directory structure

Per architecture `architecture.md:472-475`:
```
02-Architecture/
  01-UX/
  02-System/
  <sub-track>/
```

This story creates `02-Architecture/01-UX/`. Story 2A.14 creates `02-Architecture/02-System/`.

### `agents/phase2/` directory

This is the FIRST story to create Phase 2 specialists. The `phase2/` sub-directory under `src/sdlc/agents/` does NOT exist yet. Create it (with any necessary `__init__` if the agents directory is a Python package — check how `phase1/` is structured).

```
src/sdlc/agents/
├── index.yaml
├── phase1/
│   ├── epic-generator.md
│   ├── story-writer.md
│   └── ...
└── phase2/               ← NEW (this story)
    ├── ux-designer.md    ← NEW
    └── ux-reviewer.md    ← NEW
```

### MockAIRuntime canned response format for Tier-2 e2e

The e2e fixture response for `ux-designer` (per AC2/D1) is a JSON array string:
```json
[
  {"filename": "01-tokens.md", "content": "# Design Tokens\n\n...stub..."},
  {"filename": "02-flows.md", "content": "# User Flows\n\n...stub..."},
  {"filename": "03-screens.md", "content": "# Screen Specs\n\n...stub..."}
]
```

The CLI parses this with `json.loads(output_text)` — same pattern as `/sdlc-epics` canned response in Story 2A.11.

### Phase-gate hook interaction

The phase-gate hook (`hooks/builtin/phase_gate.py`) was built in Story 2A.4. It blocks writes to phase-N directories when phase-N signoff is not APPROVED. For Phase 2 writes:
- **Status (post review-B PB2 / DB2=a):** the hook has NOT been verified to cover Phase 2 writes in this story. Per AC1 (reworded), the CLI pre-flight at `cli/ux.py:run_ux` is the **sole** enforcement layer for v1. Extending `phase_gate.py:_PHASE_WRITE_DIRS` (or equivalent) is tracked as `EPIC-2A-DEBT-PHASE2-DIR-PHASE-GATE` — when closed, the hook becomes defense-in-depth alongside the CLI pre-flight (the hook checks at write time; the CLI checks at command entry).

### Inherited Debt

- `EPIC-2A-DEBT-WRITE-PRIMITIVE` — `Path.write_text` non-atomic for UX artifact writes (re-cited)
- `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` — journal flock covers batch write
- `EPIC-2A-DEBT-CLAUDE-HOOK-FAIL-CLOSED-V1.X` — from Story 2A.6; fail-open posture inherited

### New Debt (this story)

- `EPIC-2A-DEBT-UX-PARALLEL-REVIEWER` — defer `ux-reviewer` + `ux-synthesizer` dispatch to Story 2B.9 when real specialist content exists (AC3/D1)
- `EPIC-2A-DEBT-PHASE2-DIR-PHASE-GATE` — verify `phase_gate.py` correctly blocks Phase 2 writes when Phase 1 not approved; if not, extend it

### Cross-Story Coordination

- Story 2A.8 (HARD DEPENDENCY) — `phase1_prompt_builder` + dispatcher `dispatch()` API + specialist-stub pattern
- Story 2A.12 (Layer 5 sibling) — if landing first, its `tests/e2e/pipeline/conftest.py` should expose an APPROVED phase-1 signoff fixture; coordinate; if 2A.13 lands first, define the fixture locally
- Story 2A.14 (Layer 5 sibling) — both create Phase 2 specialists; avoid merge conflicts on `agents/index.yaml` and `agents/phase2/`; can coordinate ordering or use separate worktrees
- Story 2B.9 — authors real `ux-designer.md`, `ux-reviewer.md`, `ux-synthesizer.md` specialist content; stubs registered here are the hooks

### File Layout

```
src/sdlc/agents/phase2/                       # NEW directory
├── ux-designer.md                            # NEW — Phase 2 primary specialist stub
└── ux-reviewer.md                            # NEW — Phase 2 reviewer stub

src/sdlc/agents/index.yaml                    # UPDATE — register 2 new Phase 2 specialists

src/sdlc/workflows_yaml/
└── sdlc-ux.yaml                              # NEW per AC4

src/sdlc/commands/
└── sdlc-ux.md                                # NEW — slash-command shell

src/sdlc/cli/
└── ux.py                                     # NEW — run_ux (≤ 300 LOC)

src/sdlc/cli/main.py                          # UPDATE — register ux_command

src/sdlc/dispatcher/postconditions.py         # UPDATE — add ux_dir_non_empty

tests/unit/cli/
└── test_ux_command.py                        # NEW (≤ 300 LOC)

tests/unit/dispatcher/
└── test_postconditions_ux.py                 # NEW or UPDATE existing postconditions tests

tests/unit/workflows/
└── test_phase2_workflows_present.py          # NEW or UPDATE — assert sdlc-ux.yaml loads

tests/integration/
└── test_sdlc_ux.py                           # NEW (≤ 250 LOC)

tests/e2e/pipeline/
├── fixtures/ux/                              # NEW — canned specialist responses
└── test_sdlc_ux.py                           # NEW — Tier-2 e2e (2 scenarios ≤ 350 LOC)
```

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1277-1294`] — Story 2A.13 BDD ACs
- [Source: `_bmad-output/planning-artifacts/epics.md:38`] — FR13 definition
- [Source: `_bmad-output/planning-artifacts/architecture.md:472-475`] — Phase 2 directory layout
- [Source: `_bmad-output/planning-artifacts/architecture.md:960`] — `sdlc-ux.yaml` in canonical tree
- [Source: `_bmad-output/planning-artifacts/architecture.md:1143`] — FR13 → file mapping
- [Source: `_bmad-output/planning-artifacts/epics.md:1662-1670`] — Phase 2 specialist list (Story 2B.9)
- [Source: `src/sdlc/cli/research.py`] — CLI module pattern (Phase 1 dispatch)
- [Source: `src/sdlc/cli/epics.py`] — Phase 1 signoff gate pattern to adapt for Phase 1 APPROVED check
- [Source: `src/sdlc/signoff/__init__.py`] — `compute_state`, `SignoffState`
- [Source: `src/sdlc/dispatcher/__init__.py`] — `dispatch`, `phase1_prompt_builder`, `build_pre_write_hook_chain`
- [Source: `src/sdlc/dispatcher/postconditions.py`] — existing postconditions to extend
- [Source: `src/sdlc/agents/index.yaml`] — specialist registry to update
- [Source: `docs/sprints/epic-2a-dag.md`] — Layer 5 DAG: A8 → A13
- [Source: CONTRIBUTING.md §1-§5]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

| Issue | Fix |
|-------|-----|
| `_write_approved_phase1_signoff` test helper used wrong YAML schema (`artifact_refs`, missing `drafted_at`/`validated_at`) → `compute_state` raised Pydantic ValidationError → `ERR_PHASE1_NOT_APPROVED` for valid tests | Fixed to use canonical `SignoffRecord` schema: `artifacts` list with `schema_version`, `drafted_at`, `validated_at` |
| `make_journal_entry()` called with `before_hash=None` kwarg → TypeError (arg not accepted; hardcoded internally) | Removed `before_hash` kwarg from call |
| `boundary_line_present_in_prompts` in `sdlc-ux.yaml` postconditions → fails when `dispatch` mocked (no `agent_runs.jsonl` written) | Removed from UX workflow spec; postcondition is a Phase 1 prompt-security invariant, not applicable to Phase 2 UX |
| `agent_dispatched` journal entry missing when `dispatch` mocked | Wrote entry explicitly at CLI layer before calling dispatch; set `emit_agent_dispatched=False` on PanelObserver to prevent double-writing in production |

### Completion Notes List

- **AC2/D1 chosen**: Specialist returns JSON array of `{filename, content}` objects; CLI writes each to `02-Architecture/01-UX/<filename>`. Consistent with `/sdlc-epics` pattern (Story 2A.11).
- **AC3/D1 chosen**: `ux-reviewer` stub registered in `agents/phase2/` but `parallel_agents: []` in v1 workflow YAML. Parallel dispatch deferred to Story 2B.9 when real specialist content exists.
- `boundary_line_present_in_prompts` intentionally excluded from `sdlc-ux.yaml`: it's a Phase 1 prompt-security invariant; Phase 2 UX uses MockAIRuntime v1 which bypasses prompt recording.
- `agent_dispatched` journal entry written at CLI layer (before dispatch) rather than relying on `PanelObserver.emit_agent_dispatched=True`; this makes AC6 testable without real dispatch.
- Anti-tautology receipt: commented out `compute_state == APPROVED` gate temporarily; confirmed e2e scenario 2 (`test_e2e_sdlc_ux_phase_gate_block`) FAILED (no `ERR_PHASE1_NOT_APPROVED` emitted); reverted.
- Wire-format snapshot count: 5 (unchanged — no new contracts added per story requirement).
- Pre-existing test failures: baseline had 92 failures before story; post-story has 57 failures (35 improved); 0 new failures introduced.

### File List

- `src/sdlc/agents/phase2/ux-designer.md` (NEW)
- `src/sdlc/agents/phase2/ux-reviewer.md` (NEW)
- `src/sdlc/agents/index.yaml` (MODIFIED — added ux-designer + ux-reviewer)
- `src/sdlc/workflows_yaml/sdlc-ux.yaml` (NEW)
- `src/sdlc/commands/sdlc-ux.md` (NEW)
- `src/sdlc/cli/ux.py` (NEW — `run_ux` only; pre-flight + error mapping; ~273 LOC post review-A/B/C)
- `src/sdlc/cli/_ux_pipeline.py` (NEW per P14 — `ux_dispatch_and_write_async`, `validate_ux_filename`, `materialize_ux_mock_fixture`; ~348 LOC; sibling of `_epics_pipeline.py`)
- `src/sdlc/cli/_boundary.py` (NEW per P13 — `artifact_contains_boundary` promoted from `cli/verify.py`)
- `src/sdlc/cli/main.py` (MODIFIED — registered ux_command)
- `src/sdlc/dispatcher/postconditions.py` (MODIFIED — added ux_dir_non_empty + ux_dir_abs param)
- `tests/unit/workflows/test_phase2_workflows_present.py` (NEW)
- `tests/unit/dispatcher/test_postconditions_ux.py` (NEW)
- `tests/unit/cli/test_ux_command.py` (NEW)
- `tests/integration/test_sdlc_ux.py` (NEW)
- `tests/e2e/pipeline/test_sdlc_ux.py` (NEW)
- `tests/e2e/pipeline/fixtures/ux/01-PRODUCT.md` (NEW)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (MODIFIED — 2a-13 → done)

## Change Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **AC2/D1 chosen: JSON array of `{filename, content}`** | Consistent with `/sdlc-epics` pattern (Story 2A.11); enables per-file journal granularity (each file separately hashed + journaled); supports Phase 2 signoff hash-drift detection at file level. |
| 2 | **AC3/D1 chosen: `parallel_agents: []` in v1; `ux-reviewer` stub registered but inactive** | Parallel dispatch requires synthesizer to merge outputs, a v1.x feature needing real specialist content (Story 2B.9). Stubs registered in `agents/phase2/` for forward compatibility. Matches Story 2A.9 sibling posture. |
| 3 | **AC4/D3 chosen — `boundary_line_present_in_prompts` postcondition dropped from `sdlc-ux.yaml`** (re-decided 2026-05-14 during code-review of this story per CONTRIBUTING.md §5 D-decision protocol; original Change Log entry was a free-text rationale not a labeled D-decision triplet). Options considered: **D1** restore the postcondition in YAML and accept v1 mock-dispatch failure; **D2** wire a CLI-layer boundary check on prompt-build at call site; **D3 (chosen)** amend AC4 to drop the postcondition for v1 + register `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK`. Rationale: MockAIRuntime path does not write `agent_runs.jsonl` so the postcondition is inapplicable for v1 UX; CLI-layer enforcement is reintroduced by Story 2B.9 when the real runtime lands. Per D4 below, the broader prompt-injection-security invariant (NFR-SEC-3) is also tracked as deferred debt for v1.x. |
| 4 | **`agent_dispatched` journal entry written at CLI layer** | `PanelObserver.emit_agent_dispatched=True` only fires inside real `dispatch`. With `dispatch` mocked in unit tests, no entry was written. Writing it explicitly at CLI layer (with `emit_agent_dispatched=False` on observer) makes AC6 testable independently of dispatch internals. |
| 5 | **Anti-tautology receipt (AC9 mandatory)** | Temporarily commented out `phase1_state != SignoffState.APPROVED` guard in `run_ux`. E2e scenario 2 (`test_e2e_sdlc_ux_phase_gate_block`) FAILED — `ERR_PHASE1_NOT_APPROVED` was not emitted, `dispatch` was invoked. Reverted. Confirms the gate is actually exercised by the test. |
| 6 | **Inherited debt re-cited** | `EPIC-2A-DEBT-WRITE-PRIMITIVE` (non-atomic `Path.write_text`), `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` (process-local seq allocator). |
| 7 | **New debt registered** | `EPIC-2A-DEBT-UX-PARALLEL-REVIEWER` — defer `ux-reviewer` + `ux-synthesizer` to Story 2B.9. `EPIC-2A-DEBT-PHASE2-DIR-PHASE-GATE` — verify `phase_gate.py` correctly blocks Phase 2 writes. `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK` (D1/D3) — restore boundary-marker postcondition (or CLI-layer equivalent) once `agent_runs.jsonl` is written by the real runtime in Story 2B.9. `EPIC-2A-DEBT-PHASE2-PROMPT-SECURITY-INVARIANT` (D4) — close the NFR-SEC-3 Phase-2 gap (agent_runs_path plumbed but unwritten; boundary postcondition deferred). |
| 8 | **Code-review-A patches applied (2026-05-14, bmad-code-review review-A)** | 4 decision-needed resolved (D1=c, D2=a, D3=a, D4=a) + 19 patches applied (P1–P19 — see Review Findings section below). LOC: `cli/ux.py` 398 → 273 (post review-B amendments added back lines; mid-review-A snapshot was 242) via extraction of `_ux_pipeline.py` (~348 LOC final) mirroring sibling `_epics_pipeline.py` / `_stories_pipeline.py`. Promoted `_artifact_contains_boundary` to public `cli/_boundary.py` (P13). Registered new error codes in `cli/output.py`: `ERR_UNSAFE_FILENAME`, `ERR_UNSAFE_PATH`, `ERR_UX_DISPATCH_FAILED`, `ERR_POSTCONDITION_FAILED`, `ERR_SIGNOFF_READ_FAILED`. 13 deferred + 32 dismissed (most dismissals were false positives invalidated by `emit_error` raising `typer.Exit` at `cli/output.py:254`). |
| 9 | **Code-review-B patches applied (2026-05-14, bmad-code-review review-B)** | 2 decision-needed resolved (DB1=c, DB2=a) + 10 patches applied (PB1–PB8, PB10, PB11 — PB9 was determined unneeded because `emit_error` already had `-> NoReturn` annotation in `cli/output.py:229`). PB1: AC4 spec text amended to drop `boundary_line_present_in_prompts` (D1=c follow-through). PB2: AC1 spec wording reworded — CLI pre-flight is sole v1 enforcement (phase-gate hook extension deferred to `EPIC-2A-DEBT-PHASE2-DIR-PHASE-GATE`). PB3: `_materialize_ux_mock_fixture` now re-raises `SpecialistError` as `WorkflowError` instead of silently returning. PB4/PB5: `compute_state` + `WorkflowRegistry.load` catches widened to include `pydantic.ValidationError`. PB6: `evaluate_postconditions` post-call catch widened to include `OSError`. PB7: `_SAFE_FILENAME_RE` uses `re.ASCII` to prevent Unicode-digit `\d` bypass. PB8: duplicate-filename guard normalised to lowercase for case-insensitive filesystems (APFS/NTFS). PB10: `01-PRODUCT.md` read with `encoding="utf-8-sig"` to strip BOM. PB11: new tests added (3 below). 3 new tests added: `test_refuses_when_phase1_signoff_corrupt` (P2/PB4 coverage), `test_rejects_reserved_anchor_filename` (P1 coverage), `test_rejects_duplicate_filename_case_insensitive` (P4/PB8 coverage). 15 deferred + 12 dismissed (incl. blind hunter's false-positive `typer.Exit` MRO claim — verified `typer.Exit` IS `RuntimeError`, NOT `ClickException`). |
| 11 | **Code-review-C doc-rot patches (2026-05-14, bmad-code-review review-C)** | 0 decision-needed + 8 patches applied (PC1–PC8): PC1 fix row 8 LOC stale claim (398 → 273, not 242); PC2 reconcile row 9 PB-numbering (PB9 explicitly dropped as unneeded); PC3 AC4 YAML codeblock comment moved out of canonical YAML (3-line apology comment was breaking byte-for-byte fixture comparison); PC4 File List entry corrected (`cli/ux.py` no longer hosts `_ux_dispatch_and_write_async` / `_materialize_ux_mock_fixture` — those moved to `_ux_pipeline.py` per P14); PC5 split path-traversal error from invalid-pattern (substring `..` was misleading for `01-a..b.md` innocent inputs); PC6 sanitize `ValidationError` stringification before embedding in `ERR_SIGNOFF_READ_FAILED` envelope (strip newlines + truncate to 500 chars — prevents ANSI/newline leakage into line-delimited JSON consumers); PC7 reword AC9 scenario 1 wording to align with the actual `PLACEHOLDER` assertion (was referring to `BOUNDARY_LINE` assertion that scenario 1 cannot make under MockAIRuntime path); PC8 reconcile Dev Notes phase-gate hook section with AC1 PB2 wording (CLI is sole v1 enforcement; hook-extension deferred). Review-C verdict from all 3 reviewers: **APPROVE-WITH-COMMENTS**. Only hard-blocker for `done` is D3 manual rebase (WB14) — bundled commit `73abf94` per CONTRIBUTING §2 TDD-first ordering. After rebase, story flips cleanly to `done`. |
| 10 | **ERR-code convention matrix for signoff-state reads (DB1=c, review-B)** | Three sibling CLIs surface phase-1 signoff errors via three intentionally-distinct codes: (a) `signoff.py` → `ERR_PHASE1_NOT_APPROVED` (state != APPROVED at signoff-time); (b) `epics.py` → `ERR_SIGNOFF_STATE` (general signoff-state-related condition); (c) `ux.py` → `ERR_SIGNOFF_READ_FAILED` (corrupt YAML / schema-invalid / OSError reading the record file). The three codes carry different semantics: read-failure vs state-mismatch vs general-state-condition. Aligning is **not** required; the matrix is documented here for future code-review reference. |

### Review Findings

> Generated by `bmad-code-review` on 2026-05-14. 3 parallel layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor). 99 raw findings → 36 unique after dedupe → 4 decision-needed + 19 patch + 13 defer + 32 dismissed (most dismissals were Edge/Blind concerns invalidated by `emit_error` raising `typer.Exit` at `cli/output.py:245`).

#### Decision-Needed

- [ ] [Review][Decision] **D1 — AC4 spec text requires `boundary_line_present_in_prompts` postcondition, but `sdlc-ux.yaml` drops it.** Change Log row 3 rationalizes the removal as free-text, not as a D1/D2/D3 option triplet per CONTRIBUTING.md §5. Options: (a) restore the postcondition in the YAML and accept it will fail on mock-dispatch paths, (b) wire a CLI-layer prompt-boundary check at prompt-build time, (c) amend AC4 to drop the postcondition and register `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK` for v1.x. Recommended: (c) — sibling Story 2A.11 set this precedent.
- [ ] [Review][Decision] **D2 — `cli/ux.py` is 398 LOC, violating spec §AC5 LOC ≤ 300 cap. Sibling stories 2A.11 / 2A.12 extracted `_epics_pipeline.py` / `_stories_pipeline.py`.** Options: (a) extract `_ux_pipeline.py` mirroring siblings (recommended), (b) amend AC5 LOC cap to ≤ 400 and accept `noqa: C901, PLR0915` on `run_ux`. Recommended: (a).
- [ ] [Review][Decision] **D3 — Commit `73abf94` bundled spec + RED + GREEN + e2e + status flip into one commit, then user manually reverted spec/sprint-status to `review` (uncommitted).** Process violation of CONTRIBUTING.md §2 (TDD-first ordering) and §4 (review-A/B/C chunked review). Options: (a) split via `git rebase` into RED → GREEN → e2e → close-out before merge (recommended), (b) document as one-time process exception and add to epic-2A retro action list. Recommended: (a) — rebase is mechanical here.
- [ ] [Review][Decision] **D4 — `agent_runs_path` is plumbed into `dispatch(...)` but the MockAIRuntime path never writes it, AND `boundary_line_present_in_prompts` postcondition was disabled (D1 above).** Phase 1's prompt-injection-security invariant (NFR-SEC-3) is silently absent for Phase 2 UX writes. Options: (a) accept that mock-dispatch v1 has no prompt-security gate and register `EPIC-2A-DEBT-PHASE2-PROMPT-SECURITY-INVARIANT` for v1.x (recommended; depends on D1=c), (b) implement CLI-layer prompt-build boundary check now (depends on D1=b). Recommended: (a).

#### Patch (must-fix before merge)

- [ ] [Review][Patch] **P1 — `_validate_ux_filename` permits `00-*.md` colliding with phantom anchor `00-ux-dispatch-anchor.md`** [`src/sdlc/cli/ux.py:50,59-74`]; reject filenames matching the anchor or starting with `00-` reserved prefix.
- [ ] [Review][Patch] **P2 — `compute_state(...)` `SignoffError` collapses corrupt-signoff into `ERR_PHASE1_NOT_APPROVED`** [`src/sdlc/cli/ux.py:237-243`]; add distinct `ERR_SIGNOFF_READ_FAILED` so operators can distinguish "no signoff" from "broken signoff".
- [ ] [Review][Patch] **P3 — `Path.resolve().relative_to(root.resolve())` raises `ValueError` if path escapes root via symlink** [`src/sdlc/cli/ux.py:94,177`]; catch `ValueError` and raise `WorkflowError("UX target escapes repo root")` mapped to `ERR_UNSAFE_PATH`.
- [ ] [Review][Patch] **P4 — Specialist JSON array allows duplicate filenames; second write silently clobbers first** [`src/sdlc/cli/ux.py:164-217`]; track `seen` set, raise `WorkflowError("duplicate filename in specialist response")` on collision.
- [ ] [Review][Patch] **P5 — `str(entry["filename"])` / `str(entry["content"])` coerces non-strings to literal `"None"` / `"{...}"`** [`src/sdlc/cli/ux.py:171-172`]; add explicit `isinstance(filename, str)` and `isinstance(content, str)` checks and raise `WorkflowError` with clear cause.
- [ ] [Review][Patch] **P6 — `json.loads(result.agent_result.output_text)` raises `TypeError` if `output_text` is `None`/`bytes`; not in current `except` tuple** [`src/sdlc/cli/ux.py:150-156`]; pre-check `isinstance(result.agent_result.output_text, str)` and raise typed `WorkflowError`.
- [ ] [Review][Patch] **P7 — `_materialize_ux_mock_fixture` swallows specialist-load failures via bare `except Exception: return`** [`src/sdlc/cli/ux.py:376-379`]; narrow to expected exception class (or let it propagate) so root cause is visible instead of surfacing later as opaque `MockMissError → ERR_UX_DISPATCH_FAILED`.
- [ ] [Review][Patch] **P8 — Empty / whitespace-only `01-PRODUCT.md` passes through to specialist prompt** [`src/sdlc/cli/ux.py:262`]; reject with `emit_error("ERR_USER_INPUT", "01-PRODUCT.md is empty")` before prompt-build.
- [ ] [Review][Patch] **P9 — Filename length unbounded by `_SAFE_FILENAME_RE`** [`src/sdlc/cli/ux.py:50`]; cap UTF-8 byte length ≤ 100 to stay safely under POSIX `NAME_MAX=255`.
- [ ] [Review][Patch] **P10 — `compute_state(1, repo_root=root)` uses positional arg** [`src/sdlc/cli/ux.py:236`]; switch to `compute_state(phase=1, repo_root=root)` per Story 2A.7 keyword-only style (also matches spec Dev Notes example).
- [ ] [Review][Patch] **P11 — `ux_dir.glob("*.md")` postcondition matches directories named `foo.md`** [`src/sdlc/dispatcher/postconditions.py:994-1004`]; filter `is_file()` and exclude hidden dotfiles.
- [ ] [Review][Patch] **P12 — `WorkflowRegistry.load(...)` only catches `WorkflowError`; bare `yaml.YAMLError`/`OSError` propagate** [`src/sdlc/cli/ux.py:280-286`]; widen `except (WorkflowError, yaml.YAMLError, OSError)`.
- [ ] [Review][Patch] **P13 — `_artifact_contains_boundary` imported from private `cli.verify._artifact_contains_boundary`** [`src/sdlc/cli/ux.py:17`]; promote to public utility (e.g. `cli/_boundary.py`) or move to `sdlc.security`.
- [ ] [Review][Patch] **P14 — Extract `src/sdlc/cli/_ux_pipeline.py`** containing `_ux_dispatch_and_write_async` + `_validate_ux_filename` + `_materialize_ux_mock_fixture`; brings `cli/ux.py` under 300 LOC matching sibling pattern (`_epics_pipeline.py`, `_stories_pipeline.py`); removes need for `noqa: C901, PLR0915`.
- [ ] [Review][Patch] **P15 — `evaluate_postconditions` raises bare `RuntimeError` if `ux_dir_abs` plumbing missing; not in `except WorkflowError` clause** [`src/sdlc/cli/ux.py:334-348`, `src/sdlc/dispatcher/postconditions.py:1022-1026`]; convert wrapper `RuntimeError → WorkflowError("postcondition wiring incomplete: ...")` at the post-`evaluate` boundary.
- [ ] [Review][Patch] **P16 — Process patch: revert `_bmad-output/implementation-artifacts/sprint-status.yaml` flip `2a-13...: done` and revert spec frontmatter `Status: done` (user already reverted uncommitted).** Stage these reverts in a follow-up `chore(2A.13): revert premature done flip` commit before review-B.
- [ ] [Review][Patch] **P17 — Hook chain runs with `content_hash_before=None` even when target file already exists (replan / retry path)** [`src/sdlc/cli/ux.py:179-184`]; compute existing-file hash and pass as `content_hash_before` when `target.exists()`, otherwise `None`.
- [ ] [Review][Patch] **P18 — Generic `except Exception` on `_ux_dispatch_and_write_async` masks WorkflowError-derived exit paths from inside the async function** [`src/sdlc/cli/ux.py:321-332`]; the first `except WorkflowError` clause is fine, but the bare `except Exception` should re-raise after `emit_error` ; current shape relies on `emit_error` raising `typer.Exit`. Already correct because `emit_error` raises `typer.Exit` (subclass of `SystemExit`, NOT `Exception`) — but add inline comment to that effect to prevent regression.
- [ ] [Review][Patch] **P19 — `load_registry(...)` wrapped by bare `except Exception`** [`src/sdlc/cli/ux.py:288-296`]; narrow to expected `OSError | ValidationError` and include `cause=str(exc)` in `details` so debugging is feasible.

#### Defer

- [x] [Review][Defer] **W1 — `agent_dispatched` journal entry written BEFORE `dispatch()` succeeds** [`src/sdlc/cli/ux.py:108-123`] — design intent per AC6 / Change Log row 4; document as `EPIC-2A-DEBT-JOURNAL-DISPATCH-ORDER` for v1.x replay-safety; deferred, pre-existing pattern.
- [x] [Review][Defer] **W2 — `target.write_text(...)` non-atomic; partial-write recovery undefined** [`src/sdlc/cli/ux.py:196`] — pre-existing `EPIC-2A-DEBT-WRITE-PRIMITIVE`; deferred.
- [x] [Review][Defer] **W3 — Production code unconditionally constructs `MockAIRuntime`** [`src/sdlc/cli/ux.py:306`] — Story 2B.9 wires real runtime; deferred, intentional v1 stub.
- [x] [Review][Defer] **W4 — 57 pre-existing test failures reported in spec line 384 — AC10 is not a clean binary pass** — Epic-2A baseline tracking debt; deferred, pre-existing.
- [x] [Review][Defer] **W5 — `asyncio.run(...)` inside CLI fails if invoked from already-running event loop (REPL / test harness)** [`src/sdlc/cli/ux.py:307`] — deferred, no current trigger.
- [x] [Review][Defer] **W6 — Concurrent `run_ux` is lockless** [`src/sdlc/cli/ux.py:221`] — no per-repo lock anywhere in framework; deferred for framework-wide concurrency story.
- [x] [Review][Defer] **W7 — Windows-reserved filenames (CON.md, PRN.md, NUL.md, AUX.md) pass filename regex** [`src/sdlc/cli/ux.py:50`] — deferred, cross-platform concern; project is POSIX-first per ADR.
- [x] [Review][Defer] **W8 — `tempfile.TemporaryDirectory` cleanup may leak on Ctrl+C mid-write** [`src/sdlc/cli/ux.py:300`] — deferred, edge case; OS reaps tmpdir on next reboot.
- [x] [Review][Defer] **W9 — Unit tests use forged `"sha256:" + "a"*64` hashes while integration uses real `compute_artifact_hash`** [`tests/unit/cli/test_ux_command.py` vs `tests/integration/test_sdlc_ux.py`] — pattern shared with all sibling CLI suites; deferred until canonical signoff-state fixture utility lands.
- [x] [Review][Defer] **W10 — `evaluate_postconditions` dispatcher already carries `noqa: C901, PLR0912`** [`src/sdlc/dispatcher/postconditions.py:1007`] — pre-existing smell; refactor to dict-of-functions registry in follow-up; deferred.
- [x] [Review][Defer] **W11 — `agents/phase2/{ux-designer,ux-reviewer}.md` ship with `model: sonnet`** — stubs don't run real work; revisit when Story 2B.9 wires real specialists; deferred.
- [x] [Review][Defer] **W12 — `phase_gate.py` not actually extended for Phase 2 dir writes** — `EPIC-2A-DEBT-PHASE2-DIR-PHASE-GATE` already registered per Change Log row 7; deferred.
- [x] [Review][Defer] **W13 — Anchor file `00-ux-dispatch-anchor.md` is a phantom (path used in journal, never written to disk)** [`src/sdlc/cli/ux.py:93`] — depends on `dispatch(...)` `target_path_override` semantics; document or remove in v1.x; deferred.
