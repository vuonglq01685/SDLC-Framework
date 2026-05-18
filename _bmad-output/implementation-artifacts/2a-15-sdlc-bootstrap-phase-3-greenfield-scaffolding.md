# Story 2A.15: `/sdlc-bootstrap` (Phase 3 Greenfield Codebase Scaffolding, Auto-Skip)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer entering Phase 3 on a greenfield project,
I want `/sdlc-bootstrap` to scaffold the codebase per architecture decisions, auto-skipping when source already exists,
So that brownfield projects (Epic 3) and post-bootstrap re-runs are no-ops (FR15).

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1319-1336`. Per ADR-026 §1, the public API surface (`cli/bootstrap.py:run_bootstrap`) requires TDD-first commit ordering visible in `git log --reverse`. This story **depends on Story 2A.12** (`compute_state` for Phase 2 APPROVED gate) and **depends on Story 2A.14** (Phase 2 architect track must be APPROVED before Phase 3 entry). It is **Layer 6** of the Epic 2A DAG, the FIRST Phase 3 entry-point story. This story introduces NO new wire-format contracts (ADR-024 snapshot count remains 5). It introduces ONE new open-string `JournalEntry.kind` value (`bootstrap_completed`) per AC4.

### AC1 — Phase 2 signoff gate + auto-skip precedence

**Given** Phase 2 signoff is in state `APPROVED` and the project source root (default `src/`) is empty or absent
**When** I run `/sdlc-bootstrap`
**Then** the workflow dispatches the `code-bootstrapper` specialist
**And** scaffolded files land under the configured source root and `tests/` per architecture decisions
**And** the phase-gate hook (Story 2A.4) permits the writes (Phase 2 APPROVED → Phase 3 writes unblocked)
**And** journal entries are appended in this order:
  1. ONE `kind="agent_dispatched"` for `code-bootstrapper`
  2. Zero or more `kind="dispatch_attempt"` per retry policy
  3. ONE `kind="artifact_written"` per scaffolded file
  4. ONE `kind="bootstrap_completed"` final marker with `payload={"files_written": <count>, "source_root": "<abs-rel-path>"}`
**And** emit_json at end: `{"phase": 3, "track": "bootstrap", "specialist": "code-bootstrapper", "files_written": <count>, "source_root": "<path>", "outcome": "success"}`

**Given** Phase 2 signoff is NOT in state `APPROVED`
**When** I run `/sdlc-bootstrap`
**Then** the CLI pre-flight refuses with `ERR_PHASE2_NOT_APPROVED` (defense-in-depth alongside phase-gate hook)
**And** no dispatch is attempted; no files are written

> **Skip precedence (auto-skip beats gate)**: Per AC1/D2 below, the auto-skip check (AC2) runs BEFORE the Phase 2 gate check. Rationale: brownfield projects (Epic 3) must be no-ops without requiring Phase 2 signoff at all. This matches the FR15 invariant "brownfield projects (Epic 3) and post-bootstrap re-runs are no-ops".

### AC2 — Auto-skip when source already exists

**Given** the configured source root contains user code (any file under `src/` other than the framework's own placeholder)
**When** I run `/sdlc-bootstrap`
**Then** the command auto-skips with message `bootstrap skipped: source already exists at <abs-path>`
**And** exit code is 0 (skip is a success, not an error)
**And** NO files are written or modified anywhere
**And** NO journal entries are appended (skip is invisible to the audit chain — it's a no-op)
**And** emit_json: `{"phase": 3, "track": "bootstrap", "outcome": "skipped", "reason": "source-exists", "source_root": "<path>"}`

**And** **AC2/D1 (placeholder-detection D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** "Source exists" means at least one regular file under the source root that is NOT in the framework placeholder allowlist `_BOOTSTRAP_PLACEHOLDER_ALLOWLIST: frozenset[str]` (initially `{".gitkeep", "README.md"}`). Directories alone do NOT count as source. **Pros**: explicit allowlist; predictable; YAGNI. **Cons**: allowlist needs updating if `uv init` adds new placeholder files.
  - **D2:** "Source exists" means the source-root directory exists AND is non-empty by any criterion (any directory entry). **Pros**: simplest possible check. **Cons**: framework's own `uv init`-generated placeholders trigger false-positive skip.
  - **D3:** "Source exists" means scanning for actual code files by extension (`*.py`, `*.ts`, `*.go`, ...). **Pros**: most accurate. **Cons**: language-list maintenance; couples to language stack.

**And** **Recommended: D1** — explicit placeholder allowlist is correct for v1; project.yaml may later extend the allowlist (deferred debt). The detector is a private helper `_source_exists(src_root: Path) -> bool` in `cli/bootstrap.py`.
**And** the choice MUST be the FIRST line item in PR Change Log.

**And** **AC2/D2 (source-root resolution D-decision)**: ONE of the following is delivered:
  - **D1 (Recommended):** Source root is the literal string `"src"` resolved relative to `repo_root`. **Pros**: simple; matches PRD §FR15 wording; matches `architecture.md:787` canonical tree. **Cons**: not configurable in v1.
  - **D2:** Source root is read from `project.yaml` (`source_root: "src"` default). **Pros**: configurable. **Cons**: project.yaml schema may not yet expose it; requires Story 1.8 config wiring.

**And** **Recommended: D1** — hardcoded `src/` in v1; `EPIC-2A-DEBT-BOOTSTRAP-SOURCE-ROOT-CONFIG` opens for v1.x project.yaml exposure.
**And** the choice MUST be the SECOND line item in PR Change Log.

### AC3 — Workflow YAML + specialist stub + slash-command shell

**Given** the architecture canonical tree at `architecture.md:947` lists `sdlc-bootstrap.md`
**When** the dev authors the workflow YAML
**Then** `src/sdlc/workflows_yaml/sdlc-bootstrap.yaml` is authored:
  ```yaml
  schema_version: 1
  name: phase3-bootstrap-track
  slash_command: /sdlc-bootstrap
  primary_agent: code-bootstrapper
  parallel_agents: []
  synthesizer_agent: null
  postconditions:
    - source_root_populated
    - boundary_line_present_in_prompts
  write_globs:
    code-bootstrapper:
      - "src/**"
      - "tests/**"
  stop_on_postcondition_failure: true
  ```
**And** `src/sdlc/commands/sdlc-bootstrap.md` is authored (slash-command shell, mirror Story 2A.14 AC4 pattern)
**And** the specialist stub is authored at `src/sdlc/agents/phase3/code-bootstrapper.md`
**And** `agents/index.yaml` is updated to register the new Phase 3 entry:
  ```yaml
  - name: code-bootstrapper
    phase: 3
    file: phase3/code-bootstrapper.md
  ```
**And** `scripts/validate_specialists.py` passes with the new Phase 3 entry registered

> **Specialist naming discrepancy**: `epics.md:1329` + `architecture.md:1696` use `code-bootstrapper`; `architecture.md:214` (Phase-3 specialist roster) uses `codebase-scaffolder`. AC3/D1 **Recommended**: ship as `code-bootstrapper` (matches the dedicated specialist file naming at `architecture.md:1696` and the slash-command directive at epics.md:1329); flag the roster line for amendment in the Story 2B.10 specialist-authoring sprint. Document the resolution as the THIRD line item in PR Change Log.

### AC4 — Workflow YAML loader regression + new `bootstrap_completed` journal kind

**Given** the workflow loader from Story 2A.1
**When** loader is invoked with the new YAML
**Then** `sdlc-bootstrap.yaml` loads cleanly; `WorkflowRegistry` discovery picks it up; `primary_agent == "code-bootstrapper"`; write_globs covers `src/**` and `tests/**`
**And** the disjoint-writes static check (Story 2A.1) confirms the new workflow's write_globs do NOT overlap with any existing workflow's globs (Phase 2 workflows write to `02-Architecture/**`; bootstrap writes to `src/**` + `tests/**`; disjoint by leading directory).

**And** the new `JournalEntry.kind` value `bootstrap_completed` is permitted because `JournalEntry.kind` is an open `str` field (per Story 2A.3 + ADR-024 — no contract change required). The new kind is documented in a one-line entry in `docs/architecture-overview.md` (Journal Kinds glossary section, if present; otherwise inline-comment the dispatch site).

### AC5 — CLI surface: `sdlc bootstrap`

**Given** the Typer subcommand pattern from Stories 2A.9–2A.14
**When** the dev registers the command
**Then** `src/sdlc/cli/bootstrap.py:run_bootstrap(*, ctx)` is implemented with this exact ordering:
  1. Resolve `repo_root` from `ctx` (mirror the helpers used in `cli/architect.py` / `cli/ux.py`)
  2. Resolve `source_root = repo_root / "src"` (AC2/D1)
  3. **Auto-skip check FIRST** (AC2): if `_source_exists(source_root)` → print skip message to stdout (NOT stderr); emit_json skipped envelope; exit 0; return
  4. **Phase 2 gate**: if `compute_state(phase=2, repo_root=repo_root) != SignoffState.APPROVED` → raise / emit `ERR_PHASE2_NOT_APPROVED`; exit non-zero
  5. Create `src/` + `tests/` directories via `Path.mkdir(parents=True, exist_ok=True)` (outside hook chain)
  6. Compose prompt using `phase1_compound_prompt_builder` (Story 2A.11 export, also used by 2A.14) with:
     - `primary_input` = `01-Requirement/01-PRODUCT.md` content
     - `secondary_input` = `02-Architecture/02-System/ARCHITECTURE.md` content
     - `primary_label = "PRODUCT_BRIEF"`
     - `secondary_label = "SYSTEM_ARCHITECTURE"`
     If either input contains `BOUNDARY_LINE` → `ERR_ARTIFACT_CONTAINS_BOUNDARY`
  7. Call `dispatch(...)` with `code-bootstrapper`; primary output is a JSON array of `{path, content}` records (mirror Story 2A.11 `mock_epics_body` pattern; SDLC_USE_MOCK_RUNTIME env gate retained)
  8. For each record: run hook chain BEFORE write; write file under `src/` or `tests/`; append `kind="artifact_written"` journal entry
  9. Append final `kind="bootstrap_completed"` journal entry per AC1
  10. emit_json success envelope per AC1

**And** `@app.command(name="bootstrap")` is registered in `cli/main.py`:
  ```python
  @app.command(name="bootstrap")
  def bootstrap_command(ctx: typer.Context) -> None:
      """Initiate Phase 3 codebase scaffolding (FR15)."""
      from sdlc.cli.bootstrap import run_bootstrap
      run_bootstrap(ctx=ctx)
  ```

**And** the module LOC budget is ≤ 350 (smaller than 2A.14 — narrower scope, no dynamic sub-tracks). Extraction to `_bootstrap_pipeline.py` is permitted if the natural breakdown exceeds 250 LOC (mirror 2A.13 D2 pattern), but is not required up-front.

### AC6 — Per-record write contract + path-traversal safety

**Given** the specialist returns a JSON array of write-records
**When** parsing each record
**Then** each record is validated:
  - `path` field is required, must be a string, must be relative (no leading `/`, no `..` segments, no Windows drive letter)
  - `path` must start with `src/` OR `tests/` (allowed prefixes for v1; rejects any other prefix with `WorkflowError("bootstrap path outside allowed roots: <path>")`)
  - `content` field is required, must be a string (binary scaffolds deferred to v1.x)
  - Duplicate `path` values across records are rejected with `WorkflowError("duplicate bootstrap path: <path>")`
**And** a private helper `_validate_bootstrap_record(record: dict) -> tuple[Path, str]` in `cli/bootstrap.py` enforces all of the above
**And** the helper rejects path traversal via `PurePosixPath(path).parts` check (no `..` parts; consistent with `phase_gate.py` `_get_leading_dir` traversal-defense pattern)

### AC7 — Postconditions: `source_root_populated`

**Given** the primary dispatch completes
**When** postcondition evaluation runs
**Then** `source_root_populated` postcondition checks that `src/` exists and is non-empty (at least one regular file present, ignoring placeholders per AC2/D1 allowlist)
**And** this postcondition is registered in `src/sdlc/dispatcher/postconditions.py` (UPDATE existing module)
**And** failure surfaces as `ERR_POSTCONDITION_FAILED` with details including the source-root path

### AC8 — Idempotency on re-run after success

**Given** a successful bootstrap has populated `src/`
**When** I run `/sdlc-bootstrap` a second time
**Then** the auto-skip check (AC2) fires; the command exits 0 with skip message
**And** the prior run's files are NOT mutated, deleted, or hashed-against-original (skip is intentionally invisible)
**And** the journal contains the ORIGINAL run's `bootstrap_completed` entry, unchanged; the second run appends nothing

### AC9 — Tier-2 e2e (3 scenarios)

**Given** the Tier-2 e2e harness from Story 2A.0
**When** the dev authors the bootstrap e2e
**Then** `tests/e2e/pipeline/test_sdlc_bootstrap.py` (NEW) covers THREE scenarios:

  1. **Greenfield happy path**: tmp repo with Phase 2 APPROVED signoff fixture + `01-PRODUCT.md` + `02-Architecture/02-System/ARCHITECTURE.md` + empty `src/`; MockAIRuntime response = JSON array of 2–3 write-records spanning `src/` and `tests/`; invoke `sdlc bootstrap`; assert exit 0; assert all files written; journal has 1 `agent_dispatched` + N `artifact_written` + 1 `bootstrap_completed`; `BOUNDARY_LINE` present in compound prompt; emit_json `outcome: success`
  2. **Auto-skip with existing source**: tmp repo with `src/main.py` already present (non-placeholder); ANY signoff state; invoke `sdlc bootstrap`; assert exit 0; assert no dispatch occurred (MockAIRuntime call count == 0); assert no journal entries appended for this run; emit_json `outcome: skipped, reason: source-exists`
  3. **Phase 2 not approved + empty source**: tmp repo with empty `src/` but Phase 2 signoff in `AWAITING_SIGNOFF` (or any non-APPROVED state); invoke `sdlc bootstrap`; assert non-zero exit; assert `ERR_PHASE2_NOT_APPROVED`; assert no files written; assert no dispatch

**And** **Anti-tautology receipt (AC9 mandatory)**: in scenario 2, temporarily flip the auto-skip check's polarity (`return not _source_exists(...)` instead of `return _source_exists(...)`); re-run scenario 2 and confirm it now FAILS (a dispatch is attempted on a populated source-root, which would corrupt the user's code); revert; document the inversion + restoration in PR Change Log.

### AC10 — Module boundary + quality gate compliance (CONTRIBUTING.md §1)

**Given** the Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests` (Story 2A.13 baseline blocker accepted per precedent)
  - `pytest -q -m "not e2e and not property"` — new unit + integration tests green
  - `pytest -q -m e2e` — new `test_sdlc_bootstrap.py` (3 scenarios) + all existing e2e green
  - `python scripts/freeze_wireformat_snapshots.py --check` — `5 contracts match snapshots` (unchanged — no contract edits in this story)
  - `python scripts/check_module_boundaries.py` — 0 new violations; `cli.depends_on` already includes `signoff` (added in 2A.11/2A.14); no new edges required
  - `python scripts/validate_specialists.py` — passes with `code-bootstrapper` registered
  - `mkdocs build --strict` — clean

## Tasks / Subtasks

> Tasks ordered for TDD-first commits per ADR-026 §1. AC1/AC2/AC5 (CLI surface), AC4 (workflow), AC6 (record validation), AC9 (e2e) are public-API surfaces requiring tests-first commit ordering.

- [x] **Task 1 — `phase3/` specialist stub + workflow YAML + slash-command (AC3, AC4)** — **TDD-first commit 1**
  - [x] 1.1 Create `src/sdlc/agents/phase3/` directory if not already created.
  - [x] 1.2 Author stub `src/sdlc/agents/phase3/code-bootstrapper.md` (specialist frontmatter minimal; real content lands in Story 2B.10).
  - [x] 1.3 Update `src/sdlc/agents/index.yaml` — append the Phase 3 entry without disturbing Phase 1 + Phase 2 entries (Story 2A.13 + 2A.14 may have added entries since main snapshot — rebase before edit).
  - [x] 1.4 Author `src/sdlc/workflows_yaml/sdlc-bootstrap.yaml` per AC3.
  - [x] 1.5 Author `src/sdlc/commands/sdlc-bootstrap.md` (slash-command shell, ≤ 60 LOC).
  - [x] 1.6 Extend `tests/unit/workflows/test_phase2_workflows_present.py` OR create `tests/unit/workflows/test_phase3_workflows_present.py` to assert `sdlc-bootstrap.yaml` loads, `primary_agent == "code-bootstrapper"`, write_globs match AC3. Tests fail (red) → author YAML → pass (green).
  - [x] 1.7 Run `scripts/validate_specialists.py` — must pass with the new entry.
  - [x] 1.8 Document AC2/D1 (placeholder allowlist), AC2/D2 (source-root resolution), AC3/D1 (specialist naming) decisions as FIRST + SECOND + THIRD line items in PR Change Log.

- [x] **Task 2 — `dispatcher/postconditions.py`: `source_root_populated` (AC7)** — **TDD-first commit 2**
  - [x] 2.1 Author tests for `source_root_populated`: passes when `src/` has at least one non-placeholder regular file; fails when missing; fails when only `.gitkeep` present. Tests fail (red).
  - [x] 2.2 Add `source_root_populated` to `src/sdlc/dispatcher/postconditions.py`; reuse the allowlist from `cli/bootstrap.py` via module-level import (or duplicate the small frozenset locally with a comment cross-referencing the CLI module — choose the simpler option in implementation; document the choice in PR Change Log).
  - [x] 2.3 Tests pass (green).

- [x] **Task 3 — `cli/bootstrap.py:run_bootstrap` (AC1, AC2, AC5, AC6, AC8)** — **TDD-first commit 3**
  - [x] 3.1 Author `tests/unit/cli/test_bootstrap_command.py`:
    - Auto-skip when `src/main.py` exists → exit 0; no dispatch; no journal entries; emit_json skipped envelope (AC2)
    - Auto-skip when only `.gitkeep` exists → DOES proceed (not a real source file per allowlist) (AC2/D1 edge)
    - Phase 2 not approved + empty source → ERR_PHASE2_NOT_APPROVED (AC1)
    - Happy path: phase 2 APPROVED + empty `src/` → 2 files written; 1 `agent_dispatched` + 2 `artifact_written` + 1 `bootstrap_completed`; emit_json success (AC1)
    - Record validation: path with `..` segment → WorkflowError; path outside `src/`/`tests/` → WorkflowError; duplicate paths → WorkflowError; missing content key → WorkflowError (AC6)
    - Compound prompt assembly: assert `phase1_compound_prompt_builder` called with secondary_input=ARCHITECTURE.md content (AC5)
    - BOUNDARY_LINE pollution in PRODUCT.md → ERR_ARTIFACT_CONTAINS_BOUNDARY (AC5)
    - Idempotency: second run after success skips invisibly (AC8)
    Tests fail (red).
  - [x] 3.2 Implement `src/sdlc/cli/bootstrap.py:run_bootstrap(*, ctx)` per AC5. Include `_source_exists`, `_BOOTSTRAP_PLACEHOLDER_ALLOWLIST`, `_validate_bootstrap_record` private helpers. LOC ≤ 350.
  - [x] 3.3 Register `bootstrap_command` in `cli/main.py`. Tests pass (green).
  - [x] 3.4 Integration test `tests/integration/test_sdlc_bootstrap.py`: tmp repo with APPROVED phase-2 signoff fixture + PRODUCT.md + ARCHITECTURE.md + empty `src/`; MockAIRuntime returns 3 write-records; invoke `run_bootstrap(ctx=...)`; assert 3 files written; assert journal sequence per AC1; assert `bootstrap_completed` entry has `details.files_written == 3`.

- [x] **Task 4 — Tier-2 e2e: 3 scenarios (AC9)** — **TDD-first commit 4**
  - [x] 4.1 Confirm or create APPROVED phase-2 signoff fixture helper in `tests/e2e/pipeline/conftest.py` (coordinate with Story 2A.16; may be the first Phase-3-entry story to need a phase-2 APPROVED fixture).
  - [x] 4.2 Author `tests/e2e/pipeline/test_sdlc_bootstrap.py` (3 scenarios per AC9).
  - [x] 4.3 Author fixtures under `tests/e2e/pipeline/fixtures/bootstrap/` (PRODUCT.md, ARCHITECTURE.md, canned bootstrapper response with 2–3 write-records).
  - [x] 4.4 Run targeted Tier-2 e2e: all 3 scenarios green.
  - [x] 4.5 **Anti-tautology receipt (AC9 mandatory)**: invert the auto-skip polarity; rerun scenario 2; observe failure (dispatch is attempted on populated source); revert; document in PR Change Log.

- [x] **Task 5 — Module boundary verification + Quality gate + Change Log (AC10)**
  - [x] 5.1 Run `python scripts/check_module_boundaries.py` — confirm no new edge required (`cli` already depends on `signoff`, `dispatcher`, `hooks`, `journal`, `runtime`, `contracts`, `errors`, `ids`).
  - [x] 5.2 Run full quality gate; record baseline state in PR Change Log.
  - [x] 5.3 Author PR Change Log with D-decisions FIRST/SECOND/THIRD, anti-tautology receipt, debt citations.

## Dev Notes

### The Critical Invariant: Auto-Skip Runs BEFORE Phase Gate

Per FR15, "brownfield projects (Epic 3) and post-bootstrap re-runs are no-ops". This means the auto-skip MUST fire even when Phase 2 signoff is not APPROVED — otherwise brownfield projects (which never go through Phase 1/2 signoff in adopt-mode) would fail to bootstrap-skip.

Flow:

```
run_bootstrap()
  ├── 1. resolve repo_root + source_root
  ├── 2. if _source_exists(source_root): → emit skip + exit 0 (NO gate check)  ← AC2 / FR15
  ├── 3. if compute_state(phase=2) != APPROVED: → ERR_PHASE2_NOT_APPROVED      ← AC1 gate
  ├── 4. mkdir src/ + tests/
  ├── 5. compose compound prompt (PRODUCT + ARCHITECTURE)
  ├── 6. dispatch(code-bootstrapper) → output = JSON array of {path, content}
  ├── 7. for record in records:
  │       ├── _validate_bootstrap_record(record)
  │       ├── hook chain (pre-write)
  │       ├── write file
  │       └── journal artifact_written
  └── 8. journal bootstrap_completed + emit_json success
```

### Placeholder Allowlist (`_BOOTSTRAP_PLACEHOLDER_ALLOWLIST`)

```python
from typing import Final

_BOOTSTRAP_PLACEHOLDER_ALLOWLIST: Final[frozenset[str]] = frozenset({
    ".gitkeep",
    "README.md",
})

def _source_exists(src_root: Path) -> bool:
    """True if src_root contains at least one regular file outside the allowlist.

    Returns False if src_root does not exist, is empty, or contains only placeholders.
    """
    if not src_root.exists() or not src_root.is_dir():
        return False
    for path in src_root.rglob("*"):
        if path.is_file() and path.name not in _BOOTSTRAP_PLACEHOLDER_ALLOWLIST:
            return True
    return False
```

`rglob` walks the full tree — once user code exists at any depth under `src/`, the project is "post-bootstrap" and must skip.

### Record Validation (`_validate_bootstrap_record`)

```python
from pathlib import PurePosixPath

_ALLOWED_PREFIXES: Final[tuple[str, ...]] = ("src/", "tests/")

def _validate_bootstrap_record(record: object) -> tuple[Path, str]:
    if not isinstance(record, dict):
        raise WorkflowError(f"bootstrap record not a dict: {record!r}")
    path_raw = record.get("path")
    content = record.get("content")
    if not isinstance(path_raw, str) or not path_raw:
        raise WorkflowError(f"bootstrap record missing 'path': {record!r}")
    if not isinstance(content, str):
        raise WorkflowError(f"bootstrap record missing 'content' for path={path_raw!r}")
    normalized = path_raw.replace("\\", "/")
    if normalized.startswith("/"):
        raise WorkflowError(f"bootstrap path must be relative: {path_raw!r}")
    parts = PurePosixPath(normalized).parts
    if any(p == ".." for p in parts):
        raise WorkflowError(f"bootstrap path contains '..' traversal: {path_raw!r}")
    if not any(normalized.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        raise WorkflowError(
            f"bootstrap path outside allowed roots {_ALLOWED_PREFIXES}: {path_raw!r}"
        )
    return Path(normalized), content
```

This mirrors `phase_gate.py:_get_leading_dir`'s traversal-defense pattern (Story 2A.4) and the prefix-allowlist pattern from `cli/_epics_pipeline.py` (Story 2A.11).

### Mock body for v1 (`SDLC_USE_MOCK_RUNTIME=1` default)

Per the `use_mock_runtime()` gate established in Story 2A.11 (`cli/_epics_pipeline.py`), the v1 mock response for `code-bootstrapper` is:

```python
def _mock_bootstrap_body() -> str:
    return json.dumps([
        {
            "path": "src/.gitkeep",
            "content": "",
        },
        {
            "path": "tests/.gitkeep",
            "content": "",
        },
        {
            "path": "tests/conftest.py",
            "content": "# bootstrap placeholder\n",
        },
    ])
```

The mock writes minimal placeholders to satisfy `source_root_populated` postcondition without imposing language opinions. Real scaffolding lands in Story 2B.10.

**Important**: the mock writes `src/.gitkeep` (a placeholder), which by AC2/D1's allowlist does NOT count as "source exists" — so the second run will still try to bootstrap. Resolution: the mock also writes `tests/conftest.py` which is real, and the postcondition `source_root_populated` covers `src/`. To make the second-run skip work, either (a) add `tests/main_module.py` (a real file outside the allowlist) to the mock body, OR (b) ensure the second-run skip looks at the FULL bootstrap surface, not just `src/`. **AC8/D1 (idempotency D-decision)**:
  - **D1 (Recommended):** Mock writes one real file under `src/` (e.g., `src/__init__.py`) so the next run auto-skips. Adjust the mock body accordingly. This keeps `_source_exists` semantics simple (scan `src/` only).
  - **D2:** `_source_exists` scans both `src/` AND `tests/`. **Cons**: complicates the semantic; "tests exist" ≠ "source exists" linguistically.
  **Recommended: D1** — mock writes `src/__init__.py: "# placeholder\n"`. Document as FOURTH line item in PR Change Log.

### Compound prompt: PRODUCT + ARCHITECTURE

`code-bootstrapper` needs BOTH the product brief AND the architecture decisions. Reuse `phase1_compound_prompt_builder` (Story 2A.11 / 2A.14):

```python
from sdlc.dispatcher import phase1_compound_prompt_builder

product_md = (repo_root / "01-Requirement" / "01-PRODUCT.md").read_text(encoding="utf-8")
arch_md = (repo_root / "02-Architecture" / "02-System" / "ARCHITECTURE.md").read_text(encoding="utf-8")

prompt = phase1_compound_prompt_builder(
    specialist=specialist,
    spec=workflow_spec,
    primary_input=product_md,
    secondary_input=arch_md,
    primary_label="PRODUCT_BRIEF",
    secondary_label="SYSTEM_ARCHITECTURE",
    role="primary",
)
```

Both inputs are scanned for `BOUNDARY_LINE` pollution (inherits Story 2A.11 AC6 guard).

### Phase Gate Coverage for Phase 3 Writes

`phase_gate.py:111-115` already says:
> Phase 3 paths (03-Implementation/) → require compute_state(phase=2) == APPROVED.

BUT bootstrap writes to `src/**` and `tests/**`, NOT to `03-Implementation/`. Verify the hook's `_PHASE_WRITE_DIRS` (or equivalent) covers `src/` and `tests/` for Phase 3 enforcement, OR confirm the CLI's `ERR_PHASE2_NOT_APPROVED` pre-flight check is sufficient defense-in-depth (i.e., hook is permissive on `src/` because it's outside the Phase 1/2/3 canonical directories).

**AC1/D3 (gate posture D-decision)**:
  - **D1 (Recommended):** CLI pre-flight `ERR_PHASE2_NOT_APPROVED` is the primary gate; the phase-gate hook is permissive on `src/`/`tests/` (these dirs are outside Phase-1/2 boundaries). **Pros**: matches the existing hook's scope; YAGNI. **Cons**: depends on the CLI being the only writer to `src/` in a normal run.
  - **D2:** Extend `phase_gate.py` to also gate `src/` and `tests/` on Phase 2 APPROVED. **Pros**: deeper defense-in-depth. **Cons**: scope-creep into 2A.4; risks blocking unrelated tooling that touches `src/` during Phase 2 (e.g., specialist-authoring workflows).

**Recommended: D1** — CLI pre-flight is the gate; document as FIFTH line item in PR Change Log. Open `EPIC-2A-DEBT-PHASE-GATE-SRC-TESTS-COVERAGE` for D2 evaluation in v1.x.

### Coordination with Story 2A.16 on phase-2 APPROVED e2e fixture

Both 2A.15 and 2A.16 are the FIRST Phase-3-entry stories. Whichever lands first authors the `phase-2 APPROVED` fixture helper in `tests/e2e/pipeline/conftest.py`. Suggested helper signature:

```python
@pytest.fixture
def phase2_approved_repo(tmp_path: Path) -> Path:
    """Return a tmp repo with Phase 1 + Phase 2 signoffs both APPROVED."""
    ...
```

If 2A.15 merges first, the helper lives in conftest.py and 2A.16 reuses it without conflict. If 2A.16 merges first, this story rebases and reuses. Worktree branch names per CONTRIBUTING.md §3:
  - `epic-2a/2a-15-sdlc-bootstrap`
  - `epic-2a/2a-16-sdlc-break`

### Inherited Debt

- `EPIC-2A-DEBT-WRITE-PRIMITIVE` — `Path.write_text` non-atomic for each bootstrap-written file (re-cited)
- `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` — journal flock covers full primary + per-record write sequence
- `EPIC-2A-DEBT-CLAUDE-HOOK-FAIL-CLOSED-V1.X` — fail-open posture inherited

### New Debt (this story)

- `EPIC-2A-DEBT-BOOTSTRAP-SOURCE-ROOT-CONFIG` — defer project.yaml exposure of `source_root` (AC2/D2) to v1.x when adopt-mode (Epic 3) needs `legacy_code_globs` interaction
- `EPIC-2A-DEBT-PHASE-GATE-SRC-TESTS-COVERAGE` — defer phase_gate.py extension to `src/`/`tests/` (AC1/D3 D2) until a non-bootstrap-CLI writer to `src/` emerges
- `EPIC-2A-DEBT-BOOTSTRAP-BINARY-SCAFFOLDS` — defer binary-content scaffolds (images, fonts) per AC6 string-only contract; v1.x adds base64 envelope
- `EPIC-2A-DEBT-BOOTSTRAP-PLACEHOLDER-ALLOWLIST-CONFIG` — defer project.yaml exposure of `_BOOTSTRAP_PLACEHOLDER_ALLOWLIST` (AC2/D1) for users with non-standard placeholders

### Cross-Story Coordination

- Story 2A.11 (DEPENDENCY for `phase1_compound_prompt_builder` + `use_mock_runtime` pattern) — verify both exports
- Story 2A.12 (DEPENDENCY for `compute_state(phase=2) == APPROVED`) — Phase 2 signoff state machine
- Story 2A.14 (DEPENDENCY for Phase 2 architect track must produce ARCHITECTURE.md before bootstrap can compose its prompt) — operationally: 2A.14 must reach `done` before bootstrap is run in a real project (but story creation is independent)
- Story 2A.16 (Layer 6 sibling) — both create Phase-3-entry e2e infrastructure; coordinate on conftest helper
- Story 2A.17 (downstream) — `/sdlc-task` consumes tasks created by 2A.16, runs in the codebase scaffolded by 2A.15
- Story 2B.10 — authors real `code-bootstrapper` specialist content replacing the v1 stub

### File Layout

```
src/sdlc/agents/phase3/                       # NEW directory (this story creates it)
└── code-bootstrapper.md                      # NEW (stub; real content in 2B.10)

src/sdlc/agents/index.yaml                    # UPDATE — append phase-3 entry

src/sdlc/workflows_yaml/
└── sdlc-bootstrap.yaml                       # NEW per AC3

src/sdlc/commands/
└── sdlc-bootstrap.md                         # NEW — slash-command shell

src/sdlc/cli/
└── bootstrap.py                              # NEW — run_bootstrap (≤ 350 LOC)

src/sdlc/cli/main.py                          # UPDATE — register bootstrap_command

src/sdlc/dispatcher/postconditions.py         # UPDATE — add source_root_populated

tests/unit/cli/
└── test_bootstrap_command.py                 # NEW (≤ 400 LOC)

tests/unit/dispatcher/
└── test_postconditions_bootstrap.py          # NEW or UPDATE — source_root_populated

tests/unit/workflows/
└── test_phase3_workflows_present.py          # NEW or extend test_phase2_workflows_present.py

tests/integration/
└── test_sdlc_bootstrap.py                    # NEW (≤ 300 LOC)

tests/e2e/pipeline/
├── fixtures/bootstrap/                       # NEW — PRODUCT.md + ARCHITECTURE.md + bootstrapper mock body
└── test_sdlc_bootstrap.py                    # NEW — Tier-2 e2e (3 scenarios ≤ 400 LOC)

tests/e2e/pipeline/conftest.py                # UPDATE (or NEW helper) — phase2_approved_repo fixture
```

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1319-1336`] — Story 2A.15 BDD ACs
- [Source: `_bmad-output/planning-artifacts/epics.md:40`] — FR15 definition
- [Source: `_bmad-output/planning-artifacts/epics.md:1696`] — `code-bootstrapper.md` specialist file naming
- [Source: `_bmad-output/planning-artifacts/architecture.md:203`] — Phase 3 flow: `/sdlc-bootstrap` (greenfield only) → `/sdlc-break` → `/sdlc-task`
- [Source: `_bmad-output/planning-artifacts/architecture.md:214`] — Phase 3 specialist roster (note: uses `codebase-scaffolder` naming variant — flag for amendment per AC3/D1)
- [Source: `_bmad-output/planning-artifacts/architecture.md:934`] — `phase3/` 9 specialists directory
- [Source: `_bmad-output/planning-artifacts/architecture.md:947`] — `commands/sdlc-bootstrap.md` in canonical tree
- [Source: `_bmad-output/planning-artifacts/architecture.md:1145`] — FR15 → file mapping
- [Source: `_bmad-output/planning-artifacts/prd.md:740`] — FR15 wording in PRD
- [Source: `src/sdlc/cli/architect.py`] — Phase-2 entry CLI module pattern (2A.14)
- [Source: `src/sdlc/cli/_epics_pipeline.py`] — `use_mock_runtime` gate + JSON-array response contract pattern (2A.11)
- [Source: `src/sdlc/cli/_signoff_check.py:111-115`] — Phase 2 → Phase 3 gate contract
- [Source: `src/sdlc/signoff/states.py`] — `compute_state` + `SignoffState.APPROVED`
- [Source: `src/sdlc/hooks/builtin/phase_gate.py`] — phase boundary enforcement (2A.4 + 2A.7)
- [Source: `src/sdlc/dispatcher/__init__.py`] — `phase1_compound_prompt_builder` + `dispatch` exports (2A.11)
- [Source: `src/sdlc/dispatcher/postconditions.py`] — existing postconditions (extend)
- [Source: `src/sdlc/contracts/workflow_spec.py`] — WorkflowSpec frozen v1
- [Source: `docs/sprints/epic-2a-dag.md`] — Layer 6: A12 + A14 → A15; A11 → A16
- [Source: CONTRIBUTING.md §1-§5]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `emit_json()` requires `ctx=ctx` kwarg — not a positional arg; fixed both auto-skip and success paths.
- Auto-skip path needed `raise typer.Exit(0)` after `emit_json`; otherwise the function continued to the Phase 2 gate.
- `print(...)` before `emit_json` in auto-skip path polluted stdout before the JSON object, causing `json.loads(r.stdout)` to raise `JSONDecodeError`; removed the `print`.
- `target_path_override=root / "03-Implementation" / "bootstrap-anchor.json"` failed write_globs validation (must match `src/**` or `tests/**`); changed to `root / "src" / ".bootstrap-dispatch-anchor"` (sentinel within allowed globs; not written due to `persist_artifact=False`).
- Journal entries store `monotonic_seq` not `seq` — integration test updated accordingly.
- `JournalEntry` has `payload` not `details`; `bootstrap_completed` payload carries `files_written` directly in `payload` dict.

### Completion Notes List

- D1 (placeholder allowlist): `_BOOTSTRAP_PLACEHOLDER_ALLOWLIST = frozenset({".gitkeep", "README.md"})` duplicated in both `cli/bootstrap.py` and `dispatcher/postconditions.py` with a cross-reference comment (duplication simpler than import in postconditions module).
- D2 (source-root): hardcoded `src/` relative to `repo_root`; debt `EPIC-2A-DEBT-BOOTSTRAP-SOURCE-ROOT-CONFIG`.
- D3 (specialist naming): shipped as `code-bootstrapper` per `architecture.md:1696` + `epics.md:1329`; flag `architecture.md:214` roster for amendment in Story 2B.10.
- D4 (idempotency): mock body writes `src/__init__.py` (non-placeholder) so second run auto-skips.
- D5 (gate posture): CLI pre-flight `ERR_PHASE2_NOT_APPROVED` is primary gate; phase-gate hook is permissive on `src/`/`tests/`; debt `EPIC-2A-DEBT-PHASE-GATE-SRC-TESTS-COVERAGE`.
- Anti-tautology receipt (AC9): `test_e2e_sdlc_bootstrap_skip_guard_is_load_bearing` patches `_source_exists` to always return False; with skip guard neutralised the pre-populated `src/app.py` run no longer produces `outcome=skipped` — instead exits 1 with `ERR_PHASE2_NOT_APPROVED`, proving the guard is load-bearing.
- Wire-format snapshot count: still 5 (no new contracts added). `bootstrap_completed` uses open-string `JournalEntry.kind` per ADR-024.
- Quality gate: 2274 passed, 4 skipped, 18 xfailed (all pre-existing quarantined failures), 0 new failures.

### File List

- `src/sdlc/agents/phase3/code-bootstrapper.md` (NEW)
- `src/sdlc/agents/index.yaml` (UPDATED — appended phase3 entry)
- `src/sdlc/workflows_yaml/sdlc-bootstrap.yaml` (NEW)
- `src/sdlc/commands/sdlc-bootstrap.md` (NEW)
- `src/sdlc/cli/bootstrap.py` (NEW)
- `src/sdlc/cli/main.py` (UPDATED — bootstrap_command registered)
- `src/sdlc/dispatcher/postconditions.py` (UPDATED — source_root_populated)
- `tests/unit/cli/test_bootstrap_command.py` (NEW — 18 tests)
- `tests/unit/dispatcher/test_postconditions_bootstrap.py` (NEW — 7 tests)
- `tests/unit/workflows/test_phase3_workflows_present.py` (NEW — 3 tests)
- `tests/integration/test_sdlc_bootstrap.py` (NEW — 3 tests)
- `tests/integration/test_wheel_build.py` (UPDATED — bootstrap allowlist entries)
- `tests/e2e/pipeline/test_sdlc_bootstrap.py` (NEW — 4 tests including anti-tautology)
- `tests/e2e/pipeline/fixtures/bootstrap/01-PRODUCT.md` (NEW)
- `tests/e2e/pipeline/fixtures/bootstrap/ARCHITECTURE.md` (NEW)

### Review Findings

**Decision-needed (resolve before patching):**
- [x] [Review][Decision] D1 — Hook denial mid-batch: accept current behaviour + open `EPIC-2A-DEBT-BOOTSTRAP-HOOK-PARTIAL-ROLLBACK` — deferred, per-file hook denial leaves partial writes on disk; next run auto-skips masking partial state; YAGNI for v1 MockAIRuntime; atomic write semantics deferred to Story 2B scope [`bootstrap.py:200-214`]

**Patch findings (apply after D1 resolved):**
- [x] [Review][Patch] P1 — LOC budget exceeded: bootstrap.py is 474 lines vs spec ≤350; extract `_bootstrap_dispatch_write` to `cli/_bootstrap_pipeline.py` per story spec line 135 [bootstrap.py entire file]
- [x] [Review][Patch] P2 — Unit test LOC budget exceeded: test_bootstrap_command.py is 456 lines vs spec ≤400 [tests/unit/cli/test_bootstrap_command.py]
- [x] [Review][Patch] P3 — `"src/"` / `"tests/"` trailing-slash paths accepted by `_validate_bootstrap_record` — `Path("src/")` resolves to the src directory, causing `IsADirectoryError` on write; add `len(PurePosixPath(normalized).parts) >= 2` guard [bootstrap.py:97-103]
- [x] [Review][Patch] P4 — `src` existing as a file (not dir) causes unhandled `FileExistsError` from `source_root.mkdir(exist_ok=True)` at step 5; wrap in try/except with `emit_error` [bootstrap.py:313]
- [x] [Review][Patch] P5 — `assert isinstance(sp_obj, Specialist)` is compiled out with `-O`; replace with explicit `if not isinstance(...): raise WorkflowError(...)` [bootstrap.py:387]
- [x] [Review][Patch] P6 — `TypeError` from `json.loads(None)` not caught in inner handler; add `TypeError` to the except tuple at `json.loads(result.agent_result.output_text)` [bootstrap.py:181-183]
- [x] [Review][Patch] P7 — Missing test: `src` existing as a file (not dir) — no coverage for the `FileExistsError` path from finding P4 [tests/unit/cli/test_bootstrap_command.py]
- [x] [Review][Patch] P8 — Missing test: pre-write hook denying a file in a multi-file batch — hook path at bootstrap.py:209-213 is completely untested [tests/unit/cli/test_bootstrap_command.py or tests/integration/]
- [x] [Review][Patch] P9 — AC9 e2e scenario 2: dispatch absence verified via journal entries only; spec says "call count == 0" — add `mock_dispatch.assert_not_called()` or equivalent assertion [tests/e2e/pipeline/test_sdlc_bootstrap.py:212-214]
- [x] [Review][Patch] P10 — Auto-skip emit_json `source_root` field not asserted in e2e scenario 2 (AC2 requires it in emit_json output) [tests/e2e/pipeline/test_sdlc_bootstrap.py]
- [x] [Review][Patch] P11 — BOUNDARY_LINE not independently verified in e2e scenario 1 (AC9 lists it as a check); verify via agent_runs.jsonl or prompt capture [tests/e2e/pipeline/test_sdlc_bootstrap.py]
- [x] [Review][Patch] P12 — Spec AC1 uses `details={"files_written": ...}` but JournalEntry has `payload` field (no `details` field); fix spec typo [2a-15-sdlc-bootstrap-phase-3-greenfield-scaffolding.md:28]
- [x] [Review][Patch] P13 — Null-byte path not rejected by `_validate_bootstrap_record`; add null-byte check before PurePosixPath construction [bootstrap.py:94]

**Defer findings (pre-existing / out-of-scope):**
- [x] [Review][Defer] W1 — tempfile TemporaryDirectory cleanup on Windows: MockAIRuntime may hold open file handles [bootstrap.py:382-435] — deferred, Windows-only; pre-existing mock infrastructure design
- [x] [Review][Defer] W2 — Symlink traversal in `_source_exists` / `_check_source_root_populated`: `rglob("*")` follows symlinks; cyclic symlinks cause infinite loops [bootstrap.py:78, postconditions.py:361] — deferred, adversarial scenario; pre-existing pattern in codebase
- [x] [Review][Defer] W3 — Duplicate `_BOOTSTRAP_PLACEHOLDER_ALLOWLIST` in cli/bootstrap.py and dispatcher/postconditions.py without shared import; silent divergence risk — deferred, documented D1 decision; cross-reference comment exists
- [x] [Review][Defer] W4 — Mock fixture hash-key collision: if prompt content changes, MockAIRuntime finds no matching key [bootstrap.py:118-122] — deferred, mock infrastructure design; acceptable for v1
- [x] [Review][Defer] W5 — `noqa: C901, PLR0912, PLR0915` complexity suppression on `run_bootstrap` — deferred, pre-existing pattern in similar CLI modules

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-17 | D1 (FIRST): `_BOOTSTRAP_PLACEHOLDER_ALLOWLIST = frozenset({".gitkeep", "README.md"})` — explicit allowlist for "source exists" detection; duplicated in postconditions.py with cross-reference comment (simpler than import coupling) | claude-sonnet-4-6 |
| 2026-05-17 | D2 (SECOND): source root hardcoded as `src/` relative to `repo_root` (AC2/D1 recommended); debt `EPIC-2A-DEBT-BOOTSTRAP-SOURCE-ROOT-CONFIG` opened | claude-sonnet-4-6 |
| 2026-05-17 | D3 (THIRD): specialist shipped as `code-bootstrapper` per `architecture.md:1696` + `epics.md:1329`; `architecture.md:214` roster variant `codebase-scaffolder` flagged for amendment in Story 2B.10 | claude-sonnet-4-6 |
| 2026-05-17 | D4 (FOURTH): mock body writes `src/__init__.py: "# placeholder\n"` so second run auto-skips (AC8/D1 idempotency decision) | claude-sonnet-4-6 |
| 2026-05-17 | D5 (FIFTH): CLI pre-flight `ERR_PHASE2_NOT_APPROVED` is primary gate; phase-gate hook is permissive on `src/`/`tests/` (AC1/D3 recommended); debt `EPIC-2A-DEBT-PHASE-GATE-SRC-TESTS-COVERAGE` opened | claude-sonnet-4-6 |
| 2026-05-17 | Anti-tautology receipt: `test_e2e_sdlc_bootstrap_skip_guard_is_load_bearing` patches `_source_exists` → always `False`; pre-populated `src/app.py` run exits 1 with `ERR_PHASE2_NOT_APPROVED` instead of `skipped` — proving the guard is load-bearing; reverted after verification | claude-sonnet-4-6 |
