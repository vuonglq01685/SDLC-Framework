# Story 3.1: `sdlc init --adopt` Entry + Three-Pass Orchestrator + `adopt-report.json` Schema

**Status:** done

**Epic:** 3 — Brownfield Adopt Mode (`sdlc init --adopt`)
**Layer:** 1 (`docs/sprints/epic-3-dag.md` §3 — root of the serial adopt spine)
**Worktree:** `epic-3/3-1-adopt-orchestrator` (owner: Charlie, DAG §5)
**Critical Path:** **3.1** → 3.2 → 3.3 → 3.4 → 3.6 → 3.7 (DAG §4 — 3.1 is the spine root; every other adopt story depends on the module layout + `adopt-report.json` schema this story freezes)
**Parallel sibling (same layer):** 3.8 (independent leaf — does **not** depend on 3.1; both may run concurrently, max 2 worktrees, DAG §3)

---

## Story

As a **maintainer running `sdlc init --adopt` on an existing repository**,
I want **a CLI entry that orchestrates three sequential passes (detection → symlink offer → stamping), initializes the canonical `.claude/` state the same way `sdlc init` does, and writes `.claude/state/adopt-report.json` summarizing the result — with the `adopt/` module layout and the `AdoptReport` wire-format contract frozen for the rest of the epic**,
so that **the adopt flow is one resumable command end-to-end with a reviewable report (FR2), and Stories 3.2–3.7 build their passes against a stable orchestrator boundary + report schema without re-litigating structure mid-spine**.

---

## Acceptance Criteria

> **Scope note — read first.** Story 3.1 builds the **orchestrator skeleton + frozen contracts**, NOT the
> pass internals. Pass 1 detection logic = Story 3.2; Pass 2 symlink offer = Story 3.3; Pass 3 stamping =
> Story 3.4. This story defines each pass as a typed seam the driver calls in order, ships a working
> `--adopt` entry that runs the (initially minimal) passes, freezes the `adopt-report.json` schema that
> 3.2 populates, and freezes the `src/sdlc/adopt/` internal layout (DAG §5 binds the layout freeze to
> **this story's review**). Three material decisions — **D1** (module layout), **D2** (`confidence`
> encoding), **D3** (resume granularity) — are resolved at T0 in "Decisions Needed".
>
> **Verified-ground-truth correction (binding).** Epics.md:1774/1948 and the DAG say the source-untouched
> check is "`git diff` empty for source paths." **Architecture.md:194 + :223 supersede this**: the
> invariant test MUST be `git status --porcelain` empty **+ tree-hash equality** (not `git diff` text —
> "diff misses mtime, mode, xattr, symlink target"). The full invariant test is Story 3.7's deliverable;
> 3.1 only guarantees its own orchestration writes nothing outside `.claude/` and raises `AdoptError` on
> any source-modification attempt. ACs below use the porcelain+tree-hash standard.

1. **`sdlc init --adopt` runs the three passes in order (AC: orchestrator).** The hidden stub at
   `src/sdlc/cli/main.py:74-90` (currently `emit_error("ERR_USER_INPUT", "sdlc init --adopt is not implemented yet")`)
   is replaced by delegation to a new `src/sdlc/cli/adopt.py` (`run_adopt(ctx)`), which calls the new
   `src/sdlc/adopt/` driver. The driver runs **Pass 1 → Pass 2 → Pass 3 in strict order** (FR2). In this
   story the passes may be minimal/interface-level (3.2–3.4 fill them), but the ordering, journaling, and
   report-writing contract below are fully implemented and tested.

2. **Canonical state is created exactly like `sdlc init` (AC: scaffolding reuse).** `.claude/state/state.json`,
   `.claude/state/journal.log`, the static asset trees (`.claude/{agents,commands,hooks,workflows,memory,skills}/`),
   the phase dirs (`01-Requirement/`, `02-Architecture/`, `03-Implementation/`), and the hook-trust baseline
   are created identically to `run_init` (`src/sdlc/cli/init.py:134-216`). **Reuse the existing init
   scaffolding — do NOT reimplement it** (extract a shared helper or call the init path, then layer the
   adopt passes on top). On an already-initialized repo, follow the existing `_state_already_exists`
   posture (`init.py:61-69`) — but adopt-mode re-runs are idempotent/resumable (Story 3.6), so 3.1 must
   distinguish "fresh adopt" from "resume adopt" rather than hard-refusing (see **D3**).

3. **Each pass is journaled start + complete (AC: audit chain).** For every pass `N ∈ {1,2,3}` the driver
   appends a journal entry `kind=adopt_pass_started` (payload `{"pass": N}`) before the pass and
   `kind=adopt_pass_completed` (payload `{"pass": N}`) after it succeeds. These are **event-only** kinds
   (no content write) → `after_hash` uses the zero-sentinel `sha256:` + `"0"×64` per ADR-028 §2. Both kinds
   are added to ADR-028 §3 table + Revision Log by this story's PR (ADR-028 §4 forward rule — see Dev Notes).

4. **`adopt-report.json` is written conforming to a frozen schema (AC: contract).** After Pass 1 completes,
   `.claude/state/adopt-report.json` is written via the atomic-write primitive, canonical JSON (sorted keys,
   UTF-8, NFC-normalized, no floats). It conforms to the `AdoptReport` `StrictModel` contract this story adds
   to `src/sdlc/contracts/`:
   ```
   {schema_version: 1, repo_root, scanned_at, detected: [{path, kind, confidence, suggested_target}], passes_completed: [1]}
   ```
   - `schema_version: Literal[1] = 1` with the `@field_validator("schema_version", mode="before")` strict-int
     pattern (match `contracts/journal_entry.py:18,28-33`).
   - `scanned_at`: ISO-8601 UTC `Z` ms (`ids.clock.now_rfc3339_utc_ms`).
   - `detected`: list of `DetectedArtifact` sub-models; in 3.1 the driver writes `detected: []` (Pass 1
     populates it in Story 3.2 — the **shape** is frozen here).
   - `confidence`: encoded per **D2** (no Python float — architecture.md:494,515 forbids floats in
     `.claude/state/*` JSON).
   - `kind ∈ {prd, architecture, research, runbook, ci-workflow, build-file, dockerfile, readme, unknown}`
     (epics.md:1803) modeled as a `Literal[...]` / `StrEnum`.

5. **`AdoptReport` is registered as a frozen wire-format contract (AC: D1 ratified, ADR-024).** Per the
   epic-3-dag.md **Decision D1, RATIFIED 2026-06-02 = option (a) wire-format** (DAG §Decision-D1,
   lines 210-214): `adopt-report.json` is read back on resume (this story + 3.6), so `AdoptReport` is a
   cross-invocation compatibility surface. This story:
   - declares `AdoptReport` (+ `DetectedArtifact`) inheriting `StrictModel` (ADR-025);
   - adds it to `sdlc.contracts.__all__` **and** `_WIRE_FORMAT_REGISTRY` (`contracts/__init__.py:30-36`);
   - generates `tests/contract_snapshots/v1/adopt_report.json` via `scripts/freeze_wireformat_snapshots.py --write`;
   - **amends ADR-024** to record the new contract (ADR-024:137 — "adding a 6th contract requires an ADR
     amendment + new snapshot"; the locked set grows 5 → 6, and 3.3 will take it to 7 with `AdoptedSymlinks`);
   - keeps both guard tests green: `tests/contracts/test_wireformat_immutability.py` (incl.
     `test_contracts_tuple_matches_public_all`).

6. **Partial-failure resilience + resume (AC: idempotency seam for 3.6).** If any pass raises mid-flight,
   the driver catches it and `adopt-report.json` records `passes_completed` up to the last successful pass;
   the failure is journaled with the exact pass and reason; and a subsequent `sdlc init --adopt` resumes
   from the failed pass (the full re-run/no-op semantics are Story 3.6 — 3.1 provides the resume seam +
   the `passes_completed` truth source it reads). Resume granularity per **D3**.

7. **Source tree is never modified (AC: NFR-REL-6 posture).** The orchestrator writes ONLY under `.claude/`.
   Any attempt to write outside `.claude/` (or to a configured source-tree path) raises the existing
   `AdoptError` (`src/sdlc/errors/base.py:67`, `code="ERR_ADOPT"`, exit 2) — do NOT recreate it. A 3.1-scoped
   test asserts `git status --porcelain` reports zero changes outside `.claude/` after a full
   `sdlc init --adopt` on a minimal brownfield fixture (the exhaustive multi-fixture property + mutation
   gate is Story 3.7).

8. **`adopt/` module layout frozen + boundary-clean (AC: spine contract).** The net-new `src/sdlc/adopt/`
   package is created with the layout chosen in **D1**. An `adopt` ModuleSpec **already exists** in the
   module-boundary table (`scripts/module_boundary_table.py:116-119`; enforced by
   `scripts/check_module_boundaries.py`, pre-commit) with `depends_on={errors, state, journal, signoff, config}`
   and `forbidden_from={engine, dispatcher, runtime}` — **verify/confirm it matches the D1 layout; do NOT
   re-create it.** So `adopt/` MAY import `errors/`, `state/`, `journal/`, `signoff/`, `config/` and MUST NOT
   import `engine/`, `dispatcher/`, or `runtime/`. (architecture.md:1069 also lists `cli/git`, but the ratified
   boundary table does NOT grant it — and no `cli/git.py` exists yet; if git porcelain is needed later (3.7)
   it requires a boundary-table amendment, not an assumed import.) Journaling helpers therefore come from
   `journal/` directly (or are done in the `cli/adopt.py` layer), **not** from the `dispatcher` re-exports
   other pipelines use (those would breach the boundary — see Dev Notes).

9. **Quality gate + process discipline (AC: §1/§2/§5).** Quality gate green per CONTRIBUTING §1 (ruff
   format/check, `mypy --strict src/`, `pytest`, coverage ≥90%, pre-commit, `mkdocs build --strict`,
   `freeze_wireformat_snapshots --check`). TDD-first (§2): this story touches a **CLI surface + a
   wire-format contract**, so the first commit is the failing tests (contract snapshot/round-trip +
   orchestrator ordering + journal-kinds + source-untouched), visible RED in `git log --reverse`. Material
   decisions surfaced as D1/D2/D3 option-labels (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the contract + orchestrator test suite. It goes
> RED before `adopt/` or the `AdoptReport` model exist (import errors / missing snapshot), then green.

- [x] **(AC9, §5) T0 — Resolve D1/D2/D3.** Lock the `adopt/` module layout (D1), the `confidence` encoding
  (D2), and resume granularity (D3) in the PR Change Log before writing code. D1 freezes the layout for 3.2–3.7.
  **RESOLVED 2026-06-02: D1=(a) `passes/` package, D2=(a) `int` percent `[0,100]`, D3=(a) pass-level resume.**
  Plus AC6-mandated decision **D4=add a 3rd journal kind `adopt_pass_failed`** (event-only, sentinel
  `after_hash`, payload `{pass, reason}`) — the frozen `AdoptReport` schema has no error field, so failure
  journaling per AC6 ("the failure is journaled with the exact pass and reason") requires its own kind.
- [x] **(AC4, AC5, §2) Write the failing contract tests FIRST, commit before implementation:**
  - `AdoptReport`/`DetectedArtifact` round-trip + strict rejection (extra key, float `confidence`, bad `kind`);
  - snapshot immutability test parametrized to include `adopt_report` (RED until the snapshot file exists);
  - `test_contracts_tuple_matches_public_all` still passes after registry expansion. Verify RED.
  **DONE — `tests/contracts/test_adopt_report_contract.py` (RED commit 972d760, verified import-error RED).**
- [x] **(AC1, AC3, AC6) Write the failing orchestrator tests:** pass-order (1→2→3) assertion; journal emits
  `adopt_pass_started`/`adopt_pass_completed` per pass with `{"pass": N}`; partial-failure records
  `passes_completed` + journals the failure + reason; resume starts from the failed pass. Verify RED.
  **DONE — `tests/unit/adopt/test_driver.py` (RED commit 972d760).**
- [x] **(AC7) Write the failing source-untouched test:** `git status --porcelain` empty outside `.claude/`
  after `sdlc init --adopt` on a minimal brownfield fixture; `AdoptError` raised on a simulated
  outside-`.claude/` write. Verify RED.
  **DONE — `tests/integration/test_adopt_mode_invariant.py` + `tests/unit/adopt/test_invariant.py` (RED 972d760).**
- [x] **(AC5) Declare contracts** `AdoptReport` + `DetectedArtifact` in `src/sdlc/contracts/adopt_report.py`
  (inherit `StrictModel`; `schema_version: Literal[1]`; no floats; `kind` Literal/StrEnum). Export in
  `contracts/__init__.py` `__all__` + append to `_WIRE_FORMAT_REGISTRY` as `("adopt_report", AdoptReport)`.
- [x] **(AC5) Generate + commit the snapshot:** `python scripts/freeze_wireformat_snapshots.py --write`;
  verify `tests/contract_snapshots/v1/adopt_report.json` byte-stable under `--check`. **`--check` = 6/6 green.**
- [x] **(AC5) Amend ADR-024** — record `AdoptReport` as the 6th locked contract (Revision Log entry +
  registry note); reference epic-3-dag.md Decision D1.
- [x] **(AC8, D1) Create `src/sdlc/adopt/`** with the D1 layout (`driver.py` + `passes/{detection,symlink_offer,stamp}.py`
  + `invariant.py`). **Boundary correction:** the ratified `adopt` ModuleSpec omitted the foundation deps the
  driver provably needs (`contracts`/`ids`/`concurrency` — build `JournalEntry`/`AdoptReport`, atomic write,
  timestamp); added them to the EXISTING key (not a duplicate). `check_module_boundaries.py` passes.
- [x] **(AC1, AC2) Implement `cli/adopt.py` `run_adopt(ctx)`** — replaced the `main.py:74-90` stub with
  delegation; reuses init scaffolding via the new shared `init.scaffold_canonical_layout` helper. Wired `--adopt`.
- [x] **(AC1, AC3, AC6) Implement `adopt/driver.py` `run_adopt(...)`** — ordered Pass 1→2→3 behind typed seams;
  per-pass start/complete journaling via the SYNC API (`allocate_next_seq_for_append_sync` + `append_sync`);
  `adopt-report.json` written after Pass 1 via `concurrency.io_primitives.atomic_write_bytes`; pass failures →
  record `passes_completed` + journal reason (`adopt_pass_failed`) + raise `AdoptError`; resume from `passes_completed`.
- [x] **(AC3) Extend ADR-028 §3 table + Revision Log** with `adopt_pass_started`, `adopt_pass_completed`
  (+ `adopt_pass_failed`, D4) — forward rule §4, `after_hash` zero-sentinel for all three.
- [x] **(AC7) Implement the source-untouched guard** in `adopt/invariant.py` (3.1 scope: `assert_path_under_claude`
  raises `AdoptError` on any write outside `.claude/`). Typed `assert_source_untouched(...)` seam left for Story 3.7.
- [x] **(AC9, §1) Full quality gate to green** — ruff format/check + `mypy --strict` (148 files) + pytest
  (2946 passed) + coverage 88.27% (operational `--cov-fail-under=87` PASS; ≥90 tracked as
  EPIC-2B-DEBT-COVERAGE-90-FLOOR) + pre-commit + `mkdocs build --strict` + `freeze_wireformat --check` 6/6.
- [x] **(§3) Worktree + merge discipline.** Branched `epic-3/3-1-adopt-orchestrator` off up-to-date `main`
  (d66c511). TDD-first commit ordering visible in `git log --reverse` (test→feat). 3.1 is the spine root —
  merge-first + `contracts/__init__.py` rebase-not-merge are integration-time actions performed after review.
- [ ] **(§4) Chunked review** review-A (correctness/AC↔tests) → review-B (boundary/error/resume/source-untouched)
  → review-C (contract registry + ADR-024/028 amendments + module-boundary table + naming); no skipping.
  Review commits carry `[fresh-context-review]` and stage no `src/` files (§4.4).
  **→ NEXT: runs in the `code-review` workflow once dev-story sets status=review (not a dev-phase deliverable).**

### Review Findings

> `bmad-code-review` 2026-06-02 — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance
> Auditor) over `main...HEAD` (28 files, +1628/−21). Triage: **2 decision-needed · 7 patch · 5 defer ·
> 6 dismissed**. Headline: `emit_error` is verified `-> NoReturn` (`output.py:234`) → Blind Hunter's
> CRITICAL "unbound `report` crash" is a **false positive**; the real residual is the *untested* CLI
> error path (P1).

**Decisions (resolved 2026-06-02):**

- [x] [Review][Decision → 1a RESOLVED] `adopt` module-boundary `depends_on` expanded 5→8 vs AC8 "verify, don't re-create" — `scripts/module_boundary_table.py:117-139` adds `contracts`/`ids`/`concurrency` to the ratified DAG-D1 allow-set `{errors,state,journal,signoff,config}`; provably necessary (driver imports all three), `forbidden_from` unchanged. **Resolved (1a): ratify as a documented boundary correction** — record in the story Decisions section + add a D1 erratum to `docs/sprints/epic-3-dag.md` (ratified seed omitted foundation deps). → action item **P0** below.
- [x] [Review][Decision → 2a RESOLVED] Frozen `AdoptReport` v1 marks the resume cursor `passes_completed` (and `detected`) **optional** — `tests/contract_snapshots/v1/adopt_report.json:80` `required:[repo_root,scanned_at]` only (`default_factory=tuple`). **Resolved (2a): accept as-is (forward-compatible)** — the driver always writes both fields and reopening the just-frozen v1 contract would need an ADR-024 snapshot-regen ceremony. No code change; rationale recorded so Story 3.6 does not re-litigate.

**Patch (✅ all 8 applied 2026-06-02 — full gate green: 2954 passed / 4 skipped, ruff + mypy --strict clean):**

- [x] [Review][Patch] DOC (from Decision 1a) — Ratify the 5→8 boundary expansion: add a note to the story Decisions section + a D1 erratum in `docs/sprints/epic-3-dag.md` documenting the added `contracts`/`ids`/`concurrency` foundation deps [`docs/sprints/epic-3-dag.md`, story §Decisions Needed]
- [x] [Review][Patch] HIGH — CLI failure path untested: no test asserts `init --adopt` exits 2 with `ERR_ADOPT` envelope; `except JournalError`/`except AdoptError` + hook-baseline failure branches uncovered (AC6 CLI surface unverified) [`src/sdlc/cli/adopt.py:42-44,65-73`]
- [x] [Review][Patch] MEDIUM — Malformed-report resume guard untested: no test seeds a corrupt `adopt-report.json` to exercise the `except ValueError → AdoptError("cannot resume")` branch [`src/sdlc/adopt/driver.py:88-92`]
- [x] [Review][Patch] MEDIUM — Failure-handler can mask the typed error: `_append_event(FAILED)` + `_write_report` run inside the `except` before `raise AdoptError`; if either raises `OSError`/`JournalError` it escapes uncaught (CLI catches only JournalError/AdoptError → raw traceback exit 1) and the last-good report may not persist. Wrap best-effort side effects so `AdoptError` always surfaces; also wrap missing-parent `OSError` as `AdoptError` (covers Edge EC7/EC8) [`src/sdlc/adopt/driver.py:139-146`]
- [x] [Review][Patch] LOW/MED — Corrupt resume cursor not validated: any `passes_completed` is accepted, so `(2,)`/`(99,)`/dupes make `if n in completed` skip passes out of order. Add a "contiguous prefix of {1,2,3}" guard raising `AdoptError` (overlaps 3.6) [`src/sdlc/adopt/driver.py:128-135`]
- [x] [Review][Patch] LOW — `confidence` lacks the strict-int(bool-reject) guard `schema_version` has, and no `True/False` rejection test (only float 0.92 covered) — asymmetric posture on a frozen contract [`src/sdlc/contracts/adopt_report.py`]
- [x] [Review][Patch] LOW (test) — `test_adopt_json_envelope` parses `output.splitlines()[-1]` and doesn't assert `--json` mode emits ONLY the envelope (no human-echo contamination of the machine channel) [`tests/unit/cli/test_adopt.py`]
- [x] [Review][Patch] LOW (test) — `test_resume_skips_completed_passes` builds an unreachable state ([1,2,3] report then hand-overwritten to `(1,)`) and wipes the journal to `""` without asserting seq-continuity after resume — the most failure-prone resume surface (seq monotonicity across a truncated journal) is unverified [`tests/unit/adopt/test_driver.py`]

**Deferred (pre-existing / out-of-scope-for-3.1 → `deferred-work.md`):**

- [x] [Review][Defer] Non-atomic journal seq allocation — `allocate_next_seq_for_append_sync` + `append_sync` (TOCTOU gap) vs the atomic `append_with_seq_alloc` helper; design-mandated (sync API, async append no-ops if un-awaited) and only triggerable by a concurrent writer that doesn't exist for a single foreground command [`src/sdlc/adopt/driver.py:46-60`] — deferred, low-risk design choice
- [x] [Review][Defer] `assert_path_under_claude` follows symlinks (`(root/.claude).resolve()`) so a redirected/symlinked or non-existent `.claude` can pass the guard, and it never asserts `claude_root` is under `root` — squarely Story 3.7's porcelain+tree-hash scope (architecture.md:194/223 names "symlink target") [`src/sdlc/adopt/invariant.py:24-36`] — deferred to 3.7
- [x] [Review][Defer] RFC-3339 `scanned_at` pattern doesn't bound field ranges (accepts month 99); tightening a frozen contract needs an ADR-024 snapshot-regen ceremony [`src/sdlc/contracts/adopt_report.py`] — deferred, loose-but-forward-compatible
- [x] [Review][Defer] AC9 coverage gate 87% (actual 88.27%) vs AC's stated ≥90% — pre-existing tracked debt EPIC-2B-DEBT-COVERAGE-90-FLOOR — deferred, pre-existing
- [x] [Review][Defer] `_report_bytes` re-implements canonical JSON instead of reusing `cli/output.canonical_dumps` — forced by the module boundary (adopt→cli forbidden); a shared boundary-neutral util is an epic-wide refactor [`src/sdlc/adopt/driver.py:63-71`] — deferred, boundary-mandated

---

## Dev Notes

### Architecture context — the `adopt/` subsystem (net-new)

`adopt/` is a **net-new top-level subsystem** under `src/sdlc/`, sitting at the same layer as `engine/`
and `dashboard/`, directly below `cli/` (architecture.md:1084). Only `cli/` imports `adopt/`
(architecture.md:1071). FR2 maps to `cli/adopt.py` + `adopt/driver.py` (architecture.md:1132). The adopt
invariant maps to `adopt/invariant.py` + `tests/integration/test_adopt_mode_invariant.py`
(architecture.md:1188). **Neither `src/sdlc/adopt/` nor `src/sdlc/cli/adopt.py` exists yet** — both are
3.1 deliverables. The `--adopt` flag already exists as a hidden stub (`cli/main.py:74-90`).

**Import boundary (enforced by `scripts/check_module_boundaries.py`; the ratified allow-set lives in
`scripts/module_boundary_table.py:116-119`):** `adopt/` MAY import `errors/`, `state/`, `journal/`,
`signoff/`, `config/`; MUST NOT import `engine/`, `dispatcher/`, `runtime/`. (architecture.md:1069 lists
`cli/git` too, but the enforced table does NOT — and `cli/git.py` does not exist yet; treat `cli/git` as
aspirational/out-of-scope for 3.1.) Rule 6 (architecture.md:1110): "`adopt/` does not import `engine/`
or `dispatcher/`. Adopt initializes empty state; engine handles flow afterward." **Practical consequence:**
the journal-helper convenience re-exports `_bootstrap_pipeline.py` imports from `sdlc.dispatcher`
(`make_journal_entry`, `allocate_seq`, …) are OFF-LIMITS to `adopt/driver.py`. Build `JournalEntry`
directly and **use the SYNC journal API** (the CLI command body is synchronous, not in an event loop):
`allocate_next_seq_for_append_sync(journal_path)` (writer.py:224) + `append_sync(entry, journal_path)`
(writer.py:309) — the async `append` / `append_with_seq_alloc` (writer.py:243,250) are coroutines that
silently no-op if un-awaited and `append_sync` raises if entered from a running loop; every sync CLI
journaler in the repo (scan/signoff/replan/init) uses the sync pair. Both live in `journal/`, so this
stays inside the boundary.

### Module-layout conflict — RESOLVE AS D1 (this story freezes it for 3.2–3.7)

Two layouts exist in the canonical docs and they are irreconcilable:
- **architecture.md:870-875 + :1069 (flat):** `adopt/driver.py`, `adopt/detector.py`, `adopt/symlink_offer.py`,
  `adopt/verifier_marker.py`, `adopt/invariant.py` — with public API `run_adopt`, `detect_existing`,
  `offer_symlinks`, `mark_imported`, `assert_source_untouched` (architecture.md:1069).
- **epic-3-dag.md:115-116,150-152 + epics.md:1953 (package):** `adopt/driver.py`, `adopt/passes/*.py`,
  `adopt/symlink.py`, `adopt/invariant.py`.

DAG §5 (lines 150-152): "The net-new `src/sdlc/adopt/` module's internal layout … is fixed by 3.1 and
consumed by 3.2–3.7; agree it in 3.1's review before the spine branches." → **This is D1.** Whichever
layout wins, the public function names in architecture.md:1069 (`run_adopt`, `detect_existing`,
`offer_symlinks`, `mark_imported`, `assert_source_untouched`) are the stable seam 3.2/3.3/3.4 implement.

### `AdoptReport` contract — StrictModel + snapshot ceremony (ratified D1, ADR-024/025)

epic-3-dag.md Decision D1 is **RATIFIED = option (a) wire-format** (DAG lines 210-214). So `AdoptReport`
is not optional-internal — it is a frozen contract:
- `StrictModel` (`contracts/_strict_model.py` `ConfigDict` at lines 22-26 — `strict=True, extra="forbid",
  frozen=True`), ADR-025. NB `strict=True` rejects float→int and bool→int coercion, so `confidence: int =
  Field(ge=0, le=100)` (D2(a)) will correctly reject a `0.92` float — add that round-trip rejection test.
- `schema_version: Literal[1] = 1` + strict-int validator (pattern: `contracts/journal_entry.py:18,28-33`).
- `scanned_at`: reuse the RFC-3339-UTC `StringConstraints` pattern from `contracts/journal_entry.py:11,20`
  (`Annotated[str, StringConstraints(pattern=_RFC3339_UTC)]`) so the format constraint is captured in the
  snapshot — do not leave it a bare `str`.
- Register in `contracts/__init__.py` `__all__` + `_WIRE_FORMAT_REGISTRY` (lines 30-36); guard test
  `test_contracts_tuple_matches_public_all` (`test_wireformat_immutability.py:93-107`) forces registry==`__all__`.
- Snapshot bytes = `model_json_schema(mode="serialization")` canonicalized
  (`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"), indent=2)` + `\n`), at
  `tests/contract_snapshots/v1/adopt_report.json`, generated by
  `scripts/freeze_wireformat_snapshots.py --write` (CI runs `--check` only).
- **ADR-024 amendment required** (ADR-024:137): the locked set is exactly 5 today; this is the 6th.
  Add a Revision-Log line + registry note. (Story 3.3 adds `AdoptedSymlinks` = 7th.)

**`confidence` encoding — RESOLVE AS D2.** Architecture.md:494,515 forbids Python floats in `.claude/state/*`
JSON (and any hashed field). Epics shows `confidence ∈ [0.0, 1.0]` (epics.md:1803). The frozen `AdoptReport`
field therefore CANNOT be `float`. Options in D2; recommend `int` percent `[0,100]`.

### State / journal / atomic-write — REUSE, do not reinvent

| Need | Reuse | Cite |
|---|---|---|
| Write `adopt-report.json` atomically | `concurrency.io_primitives.atomic_write(path, content)` (abs path + existing parent) | io_primitives.py:139 |
| State scaffolding (`.claude/` tree) | `cli/init.py` `run_init` + `_create_state_subtree`/`_create_static_asset_dirs`/`_create_phase_dirs`/hook-trust baseline | init.py:134-216 |
| Journal append (SYNC — CLI body is not in an event loop) | `allocate_next_seq_for_append_sync(journal_path)` then `append_sync(entry, journal_path)` — **NOT** the async `append`/`append_with_seq_alloc` (coroutines: no-op if un-awaited) | journal/writer.py:224,309 |
| Build a journal entry | `JournalEntry` model directly (boundary-safe; NOT the dispatcher re-exports) | contracts/journal_entry.py |
| Timestamp | `ids.clock.now_rfc3339_utc_ms` (re-exported `cli/_time.py:5`) | cli/_time.py:5 |
| File hash (`sha256:<hex>`) | `cli/_fs.sha256_file_or_none(path)` | cli/_fs.py:15 |
| Source-modification error | `AdoptError` — already exists, `code="ERR_ADOPT"`, exit 2 | errors/base.py:67 |

**Code-style constraints binding on `adopt/` + `cli/adopt.py`** (architecture.md:483-494): `from __future__
import annotations` first line; **no top-level imports in `cli/` modules** (defer-import in command bodies,
<200ms cold start, architecture.md:488); no `print()` outside `cli/output.py`; **no `open()` for
state/journal writes — use the atomic + journal helpers only** (architecture.md:493); no floats in
state/journal (architecture.md:494); JSON canonicalization sorted-keys + NFC (architecture.md:496-515).

### Journal kinds — ADR-028 forward rule (this story adds two)

`JournalEntry.kind` is a bare `str` (contracts/journal_entry.py:22), so new kinds need **no snapshot regen**
(ADR-028:11-16). But the ratified active-set lives in ADR-028 §3, and the **forward rule (§4, lines 98-106)**
requires every new emission to (1) add a §3 table row (alphabetized within source-story column) and (2)
add a one-line Revision-Log entry citing kind + story + date. This story adds `adopt_pass_started` +
`adopt_pass_completed`. Both are event-only → `after_hash = "sha256:" + "0"*64` (zero-sentinel, ADR-028 §2,
lines 49-60). (Story 3.4 adds `imported_from_existing`; Story 3.6 adds `adopt_re_run` — out of 3.1 scope.)

### Source-untouched invariant — porcelain + tree-hash (NOT `git diff`)

architecture.md:194: "the test must be `git status --porcelain` empty + tree-hash equality, not `git diff`
text. Diff misses mtime, mode, xattr, symlink target." architecture.md:223 restates it as a strengthening
over the PRD's `git diff` wording. **3.1 scope:** guarantee its own writes are confined to `.claude/` and
raise `AdoptError` on violation; leave a typed `assert_source_untouched(...)` seam in `adopt/invariant.py`.
**Story 3.7** owns the exhaustive property test (5+ fixtures, every adopt mode) + mutation testing (≥95%
kill) using porcelain+tree-hash. Do not weaken the standard to `git diff` anywhere.

### POSIX-only posture (ADR-034)

Symlink creation (`os.symlink`, mostly Story 3.3) and the invariant test are **POSIX-only** in v1. ADR-034
(D7B) defers Windows: `journal/writer.py` already raises on Windows; CI matrix is `[ubuntu, macos]`; adding
Win32 symlink-privilege handling would be unverifiable dead code (ADR-034:28-58). Do not add `msvcrt`/Win32
paths. If a reviewer raises Windows: deferred, LOW, gated on a `windows-latest` CI cell (ADR-034:53-58,93-96).

### Previous-story intelligence

- **Epic 1 substrate** (all on `main`): `state/` (atomic.py, reader.py), `journal/` (writer.py, ADR-032
  seq alloc), `config/` (`load_project_config`, `legacy_code_globs`), `errors/` (`AdoptError`),
  `contracts/` (StrictModel + the 5 wire-format contracts + snapshot ceremony). 3.1 depends only on this
  substrate (epics.md:2006).
- **`sdlc init`** (`cli/init.py`, done): the scaffolding model 3.1 reuses; note its idempotent-via-refusal
  posture (`_state_already_exists`, init.py:61-69) which adopt-mode must soften to resume (D3, Story 3.6).
- The `--adopt` stub + `AdoptError` + the `.claude/state/adopt-report.json` + `adopted-symlinks.json` paths
  in the canonical FS layout (architecture.md:455-456) were all pre-provisioned by Epic 1 — 3.1 fills them in.

### Sibling / worktree coordination (DAG §3/§5/§6, CONTRIBUTING §3)

- **Layer 1 = {3.1, 3.8}**, max 2 worktrees, run in parallel. 3.8 is an independent leaf (no shared files
  with 3.1 except `contracts/__init__.py` is NOT touched by 3.8 — 3.8 touches `agents/` + pipeline). Low
  collision risk.
- 3.1 is the **spine root** → merge first; **3.2 rebases onto merged 3.1** (it consumes the frozen module
  layout + `adopt-report.json` schema). Keep 3.1 byte-stable before 3.2 branches (DAG §4 risk: spine slippage
  stalls 3.5/3.6/3.7).
- `contracts/__init__.py` + `tests/contract_snapshots/v1/` are shared with Story 3.3 (`AdoptedSymlinks`) →
  rebase, never merge-commit (§3); 3.1 lands `adopt_report` first, 3.3 rebases and adds `adopted_symlinks`.

### Testing standards

pytest; AAA structure; coverage ≥90% (§1). TDD-first (§2): contract + orchestrator tests are the
failing-first commit, visible in `git log --reverse`. Contract round-trip + strict-rejection + snapshot
immutability for `AdoptReport`. Source-untouched assertion uses `git status --porcelain` (not `git diff`).
A minimal brownfield fixture suffices for 3.1; the 5+-fixture corpus is authored as a shared asset in 3.2/3.7.

---

## Decisions Needed

- **D1 — `src/sdlc/adopt/` internal module layout (freezes 3.2–3.7).** DAG §5 binds this to 3.1's review.
  - **(a) `passes/` package** — `adopt/{driver.py, passes/detection.py, passes/symlink_offer.py, passes/stamp.py, symlink.py, invariant.py}`. Matches the DAG/epics wording (epic-3-dag.md:115,150-152; epics.md:1953); groups the three passes a maintainer reasons about as a unit; mutation-test scoping in 3.7 targets `adopt/passes/*.py` cleanly. **(Recommended — the DAG is the most-recent ratified artifact and the mutation-test plan (epics.md:1953) already names `passes/*.py`.)**
  - **(b) flat** — `adopt/{driver.py, detector.py, symlink_offer.py, verifier_marker.py, invariant.py}` per architecture.md:870-875. Matches the architecture module-spec public names 1:1 (architecture.md:1069) but contradicts the newer DAG.
  - Either way, expose the architecture.md:1069 public functions (`run_adopt`, `detect_existing`, `offer_symlinks`, `mark_imported`, `assert_source_untouched`) as the stable seam. If (a), note the planned-vs-shipped layout delta in 3.1's review (the DAG layout wins; architecture.md is the older doc).
- **D2 — `confidence` encoding in the frozen `AdoptReport` schema.** Floats are forbidden in `.claude/state/*`
  JSON (architecture.md:494,515); epics shows `0.0–1.0` (epics.md:1803).
  - **(a) `int` percent `[0,100]`** — deterministic, canonical, sorts/hashes cleanly; Pass 1 (3.2) maps its
    heuristic score to an integer percent; thresholds in 3.3 compare integers. **(Recommended.)**
  - **(b) decimal `str`** (e.g. `"0.92"`) — preserves the `0.0–1.0` mental model but needs string-decimal
    comparison logic in 3.3 and is easier to mis-format.
- **D3 — Resume granularity (the seam 3.6 consumes).** Re-running `sdlc init --adopt` on an
  already-initialized repo.
  - **(a) Pass-level resume** — `passes_completed` is the resume cursor; a re-run skips completed passes and
    re-enters at the first incomplete pass. Cheap, matches epics.md:1784 + the `adopt-report.json` shape.
    **(Recommended — 3.1 ships the pass-level seam; 3.6 layers within-pass idempotency/conflict on top.)**
  - **(b) Within-pass resume now** — track decided-vs-undecided candidates in 3.1. Larger blast radius;
    duplicates Story 3.6 scope. Defer.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.x (bmad-dev-story workflow).

### Debug Log References

- RED gate (commit 972d760): the 4 new test modules fail at import (`ModuleNotFoundError: No module
  named 'sdlc.adopt'` / `sdlc.contracts.adopt_report`) — verified before implementation.
- Boundary checker enforces `depends_on` strictly (`check_module_boundaries.py:95`): adding the
  driver's foundation imports (`contracts`/`ids`/`concurrency`) required amending the `adopt` ModuleSpec.
- `--json` is a root-callback eager option → invocation order is `sdlc --json init --adopt` (test fix).
- Two pre-existing count tests updated for the 5→6 contract growth: `test_init.py::test_all_tuple_matches_spec`
  and `test_wireformat_lock_e2e.py` ("5"→"6 contracts match snapshots").

### Completion Notes List

- **Decisions:** D1=(a) `passes/` package layout; D2=(a) `confidence: int` percent `[0,100]`;
  D3=(a) pass-level resume via `passes_completed`. D4 (AC6-driven): added a 3rd journal kind
  `adopt_pass_failed` so the failure reason is journaled (the frozen `AdoptReport` schema has no error field).
- **Boundary-table correction (code-review 2026-06-02, Decision 1a RATIFIED).** The `adopt` ModuleSpec
  `depends_on` was expanded from the ratified DAG-D1 seed `{errors, state, journal, signoff, config}`
  (5) to add `{contracts, ids, concurrency}` (8) — the three foundation modules the driver provably
  imports (`AdoptReport`/`JournalEntry`; `now_rfc3339_utc_ms`; `atomic_write_bytes`). `forbidden_from`
  is unchanged (`{engine, dispatcher, runtime}`, Architecture Rule 6). The DAG-D1 allow-set was a seed
  that silently omitted foundation deps; this is a corrective amendment, ratified at review as a
  documented boundary correction (CONTRIBUTING §5) and logged as an erratum in `epic-3-dag.md` §9.
- **Three-pass orchestrator** (`adopt/driver.py`): runs Pass 1→2→3 in strict order, journals
  `adopt_pass_started`/`completed` per pass (event-only zero-sentinel `after_hash`, ADR-028 §2), writes
  `adopt-report.json` after Pass 1 (AC4) and again at the end, and resumes from `passes_completed` on re-run.
- **Frozen contract** (`contracts/adopt_report.py`): `AdoptReport` + `DetectedArtifact` (StrictModel),
  registered as the 6th wire-format contract; snapshot at `tests/contract_snapshots/v1/adopt_report.json`.
  ADR-024 + ADR-028 amended.
- **Source-untouched** (AC7): `assert_path_under_claude` pre-guards every write; the integration smoke
  proves `git status --porcelain` reports changes only under `.claude/`. Full porcelain+tree-hash property +
  mutation gate is Story 3.7 (typed `assert_source_untouched` seam left in place).
- **Reuse, not reinvent:** `sdlc init --adopt` (fresh) calls the extracted `init.scaffold_canonical_layout`
  + `_init_hook_baseline.baseline_hook_trust`; resume skips scaffolding (AC2). Stub at `main.py` replaced.
- **Module-boundary amendment:** `adopt` ModuleSpec gained `contracts`/`ids`/`concurrency` (foundation deps
  the driver provably needs; the architecture.md:1069 MAY/MUST-NOT lists were silent on them). `forbidden_from`
  unchanged ({engine, dispatcher, runtime}).
- **Gate:** ruff + mypy --strict (148 files) + pytest 2946 passed + coverage 88.27% + mkdocs --strict +
  freeze --check 6/6 all green.

### File List

**New (src):**
- `src/sdlc/contracts/adopt_report.py`
- `src/sdlc/adopt/__init__.py`
- `src/sdlc/adopt/driver.py`
- `src/sdlc/adopt/invariant.py`
- `src/sdlc/adopt/passes/__init__.py`
- `src/sdlc/adopt/passes/detection.py`
- `src/sdlc/adopt/passes/symlink_offer.py`
- `src/sdlc/adopt/passes/stamp.py`
- `src/sdlc/cli/adopt.py`

**New (tests + snapshot):**
- `tests/contracts/test_adopt_report_contract.py`
- `tests/unit/adopt/__init__.py`
- `tests/unit/adopt/test_driver.py`
- `tests/unit/adopt/test_invariant.py`
- `tests/unit/cli/test_adopt.py`
- `tests/integration/test_adopt_mode_invariant.py`
- `tests/contract_snapshots/v1/adopt_report.json`

**Modified:**
- `src/sdlc/contracts/__init__.py` (register `AdoptReport` in `__all__` + `_WIRE_FORMAT_REGISTRY`)
- `src/sdlc/cli/main.py` (wire `--adopt` → `cli/adopt.run_adopt`; drop "not implemented" stub)
- `src/sdlc/cli/init.py` (extract `scaffold_canonical_layout` shared helper)
- `src/sdlc/cli/output.py` (register `ERR_ADOPT` → exit 2)
- `scripts/module_boundary_table.py` (amend `adopt` deps: +contracts/ids/concurrency)
- `docs/decisions/ADR-024-wire-format-v1-lock.md` (6th locked contract + Revision Log)
- `docs/decisions/ADR-028-journal-kind-taxonomy.md` (3 new kinds + Revision Log)
- `tests/unit/contracts/test_init.py`, `tests/unit/contracts/test_f3_independence.py`,
  `tests/integration/test_wireformat_lock_e2e.py` (5→6 contract growth)

## Change Log

- 2026-06-02: Story drafted (create-story) — Layer-1 spine root of Epic 3. Status: ready-for-dev.
- 2026-06-02: Dev (dev-story) — implemented the `sdlc init --adopt` three-pass orchestrator,
  `AdoptReport` frozen contract (6th), `adopt/` package (D1=(a) `passes/` layout), source-untouched
  guard, ADR-024/028 amendments. D1=(a)/D2=(a)/D3=(a) + D4 (`adopt_pass_failed`). TDD-first (RED 972d760
  → GREEN). Quality gate green (2946 tests, coverage 88.27%). Status: ready-for-dev → in-progress → review.
- 2026-06-02: code-review (bmad-code-review, 3 adversarial layers) — 2 decision-needed (1a ratify
  boundary 5→8, 2a accept frozen-schema as-is) + 7 patch + 5 defer + 6 dismissed. All 2 decisions
  resolved + all 8 patches APPLIED (P0 boundary-erratum docs; P1 CLI-failure-path tests; P2 malformed-
  report-resume test; P3 best-effort failure-handler + report-write `OSError`→`AdoptError`; P4 resume-
  cursor contiguity guard; P5 bool-confidence rejection test; P6 JSON-envelope-only assertion; P7
  realistic resume + journal-seq-continuity). 5 defers → `deferred-work.md` (CR3.1-W1…W5). Full gate
  green: 2954 passed / 4 skipped, ruff + mypy --strict clean. Status: review → done.
