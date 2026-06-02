# Story 3.8: Brownfield-Aware Phase 3 Specialists (`task-breaker` + characterization-test author respect `legacy_code_globs`)

**Status:** review

**Epic:** 3 — Brownfield Adopt Mode (`sdlc init --adopt`)
**Layer:** 1 (`docs/sprints/epic-3-dag.md` §3 — **independent leaf**, not on the adopt spine)
**Worktree:** `epic-3/3-8-brownfield-specialists` (owner: Alice, DAG §5)
**Critical Path:** off the critical path (DAG §4). Front-loaded into Layer 1 alongside 3.1 to use otherwise-idle capacity while the spine is built (DAG §3 dependency notes).
**Depends on (all on `main`):** 2B.10 (`task-breaker` + `tdd-strategist` shipped), Story 1.8 (`legacy_code_globs` config field), 2A.16 (`/sdlc-break`), 2A.17 (`/sdlc-task` 5-stage pipeline), 2A.2 (registry validator), 2B.3 (conformance harness). **Does NOT depend on 3.1–3.7** (DAG §2 "independent leaf").

---

## Story

As a **maintainer continuing into Phase 3 on a brownfield project**,
I want **the `task-breaker` (Story 2B.10) and a characterization-test author to respect `legacy_code_globs` declared in `project.yaml` — tasks that touch legacy files get `tdd_strategy: characterization-test` and are dispatched to a characterization-test author (capture current behavior, then refactor under that net) instead of `test-author`, while non-legacy tasks keep the strict write-tests-first pipeline**,
so that **touching legacy code in adopt-mode does not require retroactively writing failing-first tests for code that was never designed for testability (PRD §FR2 brownfield continuation, PRD:292 `legacy_code_globs` TDD exemption)**.

---

## Acceptance Criteria

> **Read first — two verified-ground-truth corrections (binding), and the central decision D1.**
>
> **(1) `tdd-strategist` ALREADY EXISTS and has a DIFFERENT role.** Epics.md:1972,1985 describe
> `tdd-strategist` as "a *new* Phase-3 specialist" that "produces characterization tests … instead of
> `test-author`." But Story 2B.10 already shipped `src/sdlc/agents/phase3/tdd-strategist.md` as a
> **strategy-layer advisor** that "sits **above** test-author," emits a **markdown test-strategy document**
> ("Output ONLY the markdown document — no JSON envelope", tdd-strategist.md:106), and writes to
> `03-Implementation/tasks/**` (tdd-strategist.md:12-13). It has **zero** notion of characterization tests.
> `docs/specialists-matrix.md:53` + ADR-030 Revision-Log (2026-06-01) confirm it is **shipped**, not planned.
> The epics' "characterization-test author" and the shipped "tdd-strategist" are **incompatible
> responsibilities** (markdown→`tasks/` vs `{files, tests_status}`→`tests/`). **D1 resolves which specialist
> plays the characterization role.** This story's title/ACs use a neutral "characterization-test author"
> until D1 locks the name.
>
> **(2) The dispatch swap is at the `pending` stage, not "write-tests".** Epics.md:1985 says dispatch the
> characterization author "for the `write-tests` stage." Verified against `_task_pipeline.py:53-58`: test
> authoring runs at the **`pending`** stage (`_STAGE_SPECIALIST["pending"] = "test-author"`); the
> `write-tests` stage runs `code-author` (GREEN). The swap MUST target the real `pending` stage. ACs use
> `pending`.

1. **`task-breaker` emits a `tdd_strategy` per task, honoring `legacy_code_globs` (AC: classification).**
   Given a `project.yaml` declaring e.g. `legacy_code_globs: ["src/legacy/**", "src/main/java/**"]`, when
   `/sdlc-break <STORY-id>` runs, every generated task carries a new `tdd_strategy ∈
   {write-tests-first, characterization-test}`. Tasks whose work targets files matching the globs get
   `characterization-test`; all others get `write-tests-first` (the default, so existing greenfield
   behavior is unchanged). The legacy-vs-not classification is **deterministic** (glob match), per **D2**.

2. **`tdd_strategy` is added to the task record + `_TaskEntry` model (AC: contract, no snapshot ceremony).**
   The `task-breaker.md` output contract (currently 5 fields: `id, story_id, label, stage, dependencies` —
   task-breaker.md:46-71) and the `_TaskEntry` model (`src/sdlc/cli/_epic_story_models.py`, class at line 77,
   field block 84-90) gain `tdd_strategy: Literal["write-tests-first", "characterization-test"] =
   "write-tests-first"`. The default keeps existing task files valid — mirror the `_StoryEntry.status`
   **default** value (:60) **but NOT its `exclude=True`**: `status` is `Field("pending", exclude=True)` and is
   kept out of serialized JSON; `tdd_strategy` MUST serialize so `/sdlc-task` can read it back off the task
   file (AC3 depends on it surviving the `serialize_task_entry` → re-parse round-trip). **No ADR-024
   snapshot regeneration:** `_TaskEntry` is explicitly NOT a wire-format snapshot contract
   (`_epic_story_models.py:1-6,80`; `tests/contract_snapshots/v1/` has no task entry). It IS a
   `StrictModel`, so the field must be a real declared field with a default.

3. **`/sdlc-task` dispatches the characterization-test author for `characterization-test` tasks (AC: pipeline
   swap).** When `/sdlc-task <id>` runs (Story 2A.17) on a task whose `tdd_strategy == characterization-test`,
   the pipeline dispatches the **characterization-test author** (D1) at the **`pending`** stage instead of
   `test-author`. The author produces characterization tests (capture current behavior; tests are expected
   to **pass**, not fail-first), written under `tests/**`. The rest of the pipeline (`write-tests`→`code-author`
   → `write-code`→`code-reviewer` → `review`→done) continues unchanged. For `write-tests-first` tasks the
   pipeline is byte-for-byte unchanged from today.

4. **The RED-gate is conditional on `tdd_strategy` (AC: gate correctness).** Today `_task_pipeline.py:178-185`
   hard-requires `tests_status == "red"` at the `pending` stage. Characterization tests capture current
   behavior and are expected to **pass**, so for `characterization-test` tasks the gate MUST NOT fail on
   non-`red`. **The characterization author reports `tests_status: "green"`** — do NOT invent a new status
   value: the parser contract `_StageFilesResult.tests_status` is `Literal["red", "green"]`
   (`src/sdlc/cli/_task_pipeline_parsers.py:21`); a `"characterization"` value would fail at
   `parse_files_result` before the gate runs. So: keep the `Literal` as-is, and make the `pending`-stage gate
   accept `"green"` (skip the RED requirement) when `task.tdd_strategy == "characterization-test"`. For
   `write-tests-first` tasks the RED-gate is unchanged. The downstream `write-tests`→`code-author` GREEN-gate
   (`_task_pipeline.py:186-199`) is unchanged for both strategies.

5. **Registry + roster stay valid (AC: 2A.2 / ADR-030).** If D1 authors a NEW specialist file, it lands at
   `src/sdlc/agents/phase3/<name>.md` with the shipped frontmatter schema (schema_version, name, title, icon,
   model: sonnet, tools: [], read_globs, write_globs **including `tests/**`**, description), an `index.yaml`
   row (`{name, phase: 3, file: phase3/<name>.md}`), a `docs/specialists-matrix.md` shipped-row, and a
   one-line ADR-030 amendment for the planned-vs-shipped naming deviation (ADR-030 forward rule). The
   registry loads clean (`load_registry` orphan check `registry.py:177-184`; three-way name match: file stem
   == frontmatter `name` == `index.yaml` slug). Count band: current roster = **39**; band is **`≥39, ≤45`**
   (ADR-030 Revision-Log 2026-06-01) → a new specialist makes 40 ✅ in-band. If D1 redefines the existing
   `tdd-strategist` instead, roster stays 39 but the 2B.10 role pins + matrix:53 row must be updated.

6. **Brownfield Phase-3 path covered by conformance (AC: 2B.3, mock-vs-claude byte identity).** Extend
   `tests/integration/test_abstraction_adequacy.py` with a brownfield assertion mirroring
   `test_phase3_representative_dispatched_byte_identical_mock_vs_claude` (:270-346): exercise the
   characterization-test author against a brownfield fixture and assert byte-identical `AgentResult` across
   `MockAIRuntime` and the claude stub. Characterization-test outputs are validated against fixtures
   (epics.md:1996-1997). **Do NOT add a third runtime factory** (`_RUNTIME_FACTORIES` invariant, :83,235-237);
   build a self-contained fixture, do not mutate the seed goldens (:284-285).

7. **`/sdlc-break` reads `project.yaml` (AC: config wiring).** `run_break` (`cli/break_.py`) /
   `break_dispatch_write` (`cli/_break_pipeline.py`) call `load_project_config()` (`config/project.py:33`)
   and apply `legacy_code_globs` (`config/project.py:29`, `tuple[str,...]`, default `()`). With an empty/absent
   `legacy_code_globs` (greenfield), all tasks get `write-tests-first` and behavior is identical to today
   (regression guard). The mock body (`mock_task_batch_body`, `_break_pipeline.py:168-195`) gains a
   brownfield variant so the conformance/byte-identity path holds.

8. **Quality gate + process discipline (AC: §1/§2/§5).** Quality gate green per CONTRIBUTING §1 (ruff
   format/check, `mypy --strict src/`, `pytest`, coverage ≥90%, pre-commit, `mkdocs build --strict`,
   `freeze_wireformat_snapshots --check` — unchanged, since no wire-format contract is touched). TDD-first
   (§2): this story touches **CLI behavior + the dispatch pipeline + a (non-wire) contract field**, so the
   failing-first commit is the classification + dispatch-swap + RED-gate + conformance tests, RED before the
   field/specialist/pipeline changes land, visible in `git log --reverse`. Material decisions surfaced as
   D1/D2/D3 (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the behavior suite — glob classification sets
> `tdd_strategy`; `/sdlc-task` dispatches the characterization author at `pending` for legacy tasks; the
> RED-gate accepts characterization status; greenfield path unchanged; brownfield conformance byte-identity.
> All RED before the field, specialist, and pipeline edits.

- [x] **(AC: all, §5) T0 — Resolve D1/D2/D3.** Locked all Recommended: **D1=(a)** new
  `phase3/characterization-author.md`; **D2=(a)** deterministic CLI classifier (task-breaker emits
  `touches`, CLI stamps `tdd_strategy`); **D3=(a)** `task-breaker.md` updated in place. (Change Log)
- [x] **(AC2, AC7, §2) Write failing classification tests FIRST:** `tests/unit/cli/test_brownfield_classify.py`
  (greenfield regression + nested `**` + no-match + multiple globs + segment-aware non-cross-slash);
  `test_break_command_brownfield.py` legacy→characterization, non-legacy→wtf, greenfield. RED verified.
- [x] **(AC3, AC4, §2) Write failing pipeline tests:** `test_task_command_brownfield.py` — characterization
  task dispatches characterization-author at `pending` + advances on green + red rejected; `write-tests-first`
  unchanged (test-author + strict RED-gate). RED verified.
- [x] **(AC6) Write failing conformance test:** `tests/integration/test_abstraction_adequacy_brownfield.py`
  mirroring `test_phase3_representative_dispatched_byte_identical_mock_vs_claude`. RED verified.
- [x] **(AC2) Add `tdd_strategy` field** to `_TaskEntry` (`Literal[...]` default `"write-tests-first"`,
  serialized) + `touches: list[str]` input-only (`exclude=True`) + `task-breaker.md` output contract. Wire-format
  snapshot `--check` green (6 contracts unchanged — `_TaskEntry` is not a snapshot).
- [x] **(AC1, AC2, D3) Make `task-breaker` brownfield-aware** — `task-breaker.md` updated in place (D3=(a)):
  emits `touches`, brownfield-mode section, must NOT emit `tdd_strategy` (CLI stamps it).
- [x] **(AC7, AC1, D2) Wire `/sdlc-break` to config + classify** — `run_break` loads `legacy_code_globs` from
  `project.yaml`; `break_dispatch_write` stamps `tdd_strategy` via `_brownfield.classify_tdd_strategy`;
  brownfield mock variant `mock_task_batch_body_brownfield` added.
- [x] **(AC1, AC3, AC5, D1) Provide the characterization-test author** — authored new
  `src/sdlc/agents/phase3/characterization-author.md` (D1=(a)) emitting `{files, tests_status:'green'}` to
  `tests/**`; index.yaml row + matrix shipped-row + ADR-030 amendment + three-way name match. No boundary line
  in body. `tdd-strategist` left untouched.
- [x] **(AC3, AC4) Pipeline swap + conditional RED-gate** — `_task_pipeline.select_stage_specialist()` returns
  the characterization author at `pending` for characterization tasks (static `_STAGE_SPECIALIST` kept frozen);
  RED-gate conditional (characterization requires green). Mirrored in `cli/task.py` (selector + mock-body
  branch). `_NEXT_STAGE` + GREEN/review stages untouched.
- [x] **(AC6) Brownfield conformance** — byte-identity test + self-contained fixture; no third runtime factory;
  seed goldens untouched.
- [x] **(AC5) Registry/matrix/ADR reconciliation** — index.yaml + `docs/specialists-matrix.md` (§1 row +
  §4 totals 39→40) + ADR-030 Revision Log + wheel allowlist + `_ALL_PHASE3_NAMES` union; `load_registry`
  clean; roster 40 ∈ [39,45].
- [x] **(AC8, §1) Full quality gate to green** — ruff format/check, `mypy --strict src/` (149 files),
  pytest 2994 passed (1 pre-existing flaky perf benchmark, green in isolation), coverage 89.78% ≥87
  operational gate (`EPIC-2B-DEBT-COVERAGE-90-FLOOR` carries the 90 floor), pre-commit all hooks, `mkdocs
  build --strict`, wire-format snapshots 6/6.
- [x] **(§3) Worktree.** Branch `epic-3/3-8-brownfield-specialists` off up-to-date `main` (sibling 3.1
  already merged; no `agents/` collision).
- [ ] **(§4) Chunked review** — review-A/B/C executed by the separate `code-review` workflow once status is
  `review` (the handoff this story now reaches). Pending.

---

## Dev Notes

### The central conflict — `tdd-strategist` already exists (resolve as D1)

`src/sdlc/agents/phase3/tdd-strategist.md` was shipped by Story 2B.10:
- frontmatter: `name: tdd-strategist`, `model: sonnet`, `tools: []`, `write_globs: ["03-Implementation/tasks/**"]`
  (tdd-strategist.md:2-13);
- role (tdd-strategist.md:17-26): "delivery-layer specialist operating **above** the test-author/code-author
  cycle … dispatched **before** the TDD pipeline begins";
- output (tdd-strategist.md:46-106): a markdown **test-strategy document** — "Output ONLY the markdown
  document — no JSON envelope";
- **no** characterization / brownfield / legacy notion at all.

The epics-3.8 "characterization-test author" must: run **inside** the pipeline at the `pending` stage, emit
`{files, tests_status}` JSON under `tests/**`, and produce passing characterization tests. These are
**incompatible** with the shipped `tdd-strategist` (markdown advisor → `tasks/`). `docs/specialists-matrix.md:53`
("Strategy-layer role above `test-author`; production body authored 2B.10") + ADR-030 Revision-Log confirm the
shipped role. **You cannot have one specialist satisfy both contracts under deterministic dispatch.** → D1.

### Pipeline dispatch — hardcoded map; the swap (verified)

`src/sdlc/cli/_task_pipeline.py:53-65`:
```python
_STAGE_SPECIALIST = {"pending": "test-author", "write-tests": "code-author",
                     "write-code": "code-reviewer", "review": None}
_NEXT_STAGE = {"pending": "write-tests", "write-tests": "write-code",
               "write-code": "review", "review": "done"}
```
- Specialist for a stage is a module-level `Final` dict lookup at `:101` (`_STAGE_SPECIALIST[current_stage]`)
  — **no per-task data path today**. The swap makes `pending`-stage selection consult `task.tdd_strategy`.
- **RED-gate** at `:178-185` hard-requires `tests_status == "red"` for the `pending` stage → must become
  conditional for `characterization-test`.
- Mirror sites: `cli/task.py:249` (same lookup), `:261-267` (mock materialization), `:278-283`
  (`mock_test_author_body` selection) — route all through the same helper.
- **"Frozen" status:** `_task_pipeline.py` carries NO `# DO NOT MODIFY`/FROZEN marker; the "frozen" wording
  in epic-3-dag.md:185 refers to **3.1's adopt module + JSON schemas**, not this pipeline. Editing dispatch
  is allowed — BUT the pipeline's byte-output is gated by the 2B.3 conformance test, so the brownfield path
  needs its own conformance coverage (AC6) and the greenfield path must remain byte-identical (AC3/AC7).

### `task-breaker` + `_TaskEntry` — `tdd_strategy` is net-new (no snapshot ceremony)

- `task-breaker.md:46-71` declares exactly 5 task fields; **no `tdd_strategy`** today.
- `_TaskEntry` (`src/sdlc/cli/_epic_story_models.py`, class line 77, fields 84-90) has `id, story_id, label,
  stage, dependencies, review_verdict, review_notes`; **no `tdd_strategy`**. It is a `StrictModel` (extra
  forbidden) but **explicitly NOT a wire-format snapshot** (`cli/_epic_story_models.py:1-6,80`) — adding a
  field needs **no** `freeze_wireformat_snapshots` regen and does **not** touch the ADR-024 locked set. Add as
  `Literal["write-tests-first","characterization-test"] = "write-tests-first"` (default = existing behavior;
  copy the `_StoryEntry.status` default value at :60 but **omit `exclude=True`** — `tdd_strategy` must
  serialize, `status` deliberately does not). `_validate_task_batch` (`_break_pipeline.py:49-108`) doesn't
  inspect `tdd_strategy` → existing validation unaffected; add brownfield-mode validation if needed.

### `legacy_code_globs` — already shipped (Story 1.8); only the glob-match logic is new

`config/project.py:29` — `legacy_code_globs: tuple[str, ...] = Field(default_factory=tuple)` on
`ProjectConfig` (frozen, `extra="forbid"`). Loader `load_project_config(path=None) -> ProjectConfig`
(:33; default `<cwd>/project.yaml`; missing→defaults; unknown key/wrong type→`ConfigError`). `/sdlc-break`
does **not** read config today (verified) — AC7 wires it. The deterministic glob-matching of task targets
against the globs is the only net-new logic (use `pathlib`/`fnmatch`/`PurePath.match` with `**` support;
keep it deterministic for conformance).

### How `tdd_strategy` is assigned — resolve as D2

A task record has no structured "files it touches" field (only `label`), so the classifier needs a source of
truth for which files each task targets. Two designs (D2). Whichever wins, classification must be
**deterministic** (the LLM should not perform glob-matching) so the 2B.3 mock-vs-claude byte-identity holds —
the mock body must reproduce the same `tdd_strategy` the claude path yields.

### Registry / matrix / ADR-030 (if D1 authors a new specialist)

- Roster currently **39**; band **`≥39, ≤45`** (ADR-030 Revision-Log 2026-06-01; `docs/specialists-matrix.md`
  shipped total 39). A new specialist → 40, in-band ✅.
- Adding a `.md` requires: `index.yaml` row (else orphan check fails, `registry.py:177-184`), three-way name
  match (file stem == frontmatter `name` == index slug), a `docs/specialists-matrix.md` shipped row, and a
  one-line ADR-030 amendment (planned→shipped naming deviation, ADR-030 forward rule lines 26-31). Also add
  the name to `_ALL_PHASE3_NAMES` in `tests/unit/specialists/test_phase3_2b10_authoring.py:42-43` and the
  wheel allow-list (`tests/integration/test_wheel_build.py` `_ALLOWED_CONTENT_FILES`) — the same chores 2B.10
  performed for its 4 new files.
- New Phase-3 specialist must declare `tools: []` and no network/destructive op (2B.6 gates
  `scripts/check_no_outbound_http.py` + safety.py stay green); boundary line present in the prompt body
  (2B.5 discipline — the gate scans `dispatcher/prompts.py`, not markdown, so authoring markdown can't
  regress it, but keep the in-body `<BOUNDARY>` framing for dispatch-time discipline).

### 2B.3 conformance extension point

`tests/integration/test_abstraction_adequacy.py`: Phase-3 representative pinned to `code-author`
(`_PHASE3_CONFORMANCE_REPRESENTATIVE`, :63). The pattern to mirror for AC6 is
`test_phase3_representative_dispatched_byte_identical_mock_vs_claude` (:270-346) — load specialist → use its
`spec.body` as prompt → single-row fixture keyed by `compute_prompt_hash` → dispatch through both runtimes →
assert runtime-neutral `AgentResult` byte-identity (strip the audit-only `mock` flag). **Invariant: do NOT
add a third `_RUNTIME_FACTORIES` entry** (:83,235-237). Build a self-contained brownfield fixture; do not
touch the `_REGENERATE_GOLDENS` seed goldens (:284-285).

### Previous-story intelligence

- **2A.16** authored `task-breaker` (`/sdlc-break`), enriched to production in **2B.10**. **2A.17** froze the
  5-stage `_task_pipeline.py` dispatch + RED→GREEN gate. **2B.10** authored `tdd-strategist` (strategy role),
  `pr-author`, `security-reviewer`, `edge-case-reviewer`, and pinned `code-author` as the conformance rep.
  **2B.11** set the ADR-030 count band to `[39,45]` and reconciled the matrix.
- **Story 1.8** shipped `legacy_code_globs`. **2B.3** is the conformance harness gating Phase-3 dispatch
  changes. **2A.2** is the registry validator (orphan + three-way name + count gate).

### Sibling / worktree coordination (DAG §3/§5)

Layer 1 = {3.1, 3.8}, parallel, max 2 worktrees. 3.8 is the independent leaf — it touches `agents/`,
`config/`-consumers, and the task pipeline; 3.1 touches `contracts/` + new `adopt/`. **No shared source
files** → low collision. If 3.8 adds an `index.yaml` row it is the only Layer-1 writer of `agents/`, so no
rebase race with 3.1. ADR-030 already pre-absorbs the roster headroom (DAG §3 note: "ADR-030's count band
already pre-absorbs … 3.8 introduces no roster-gate churn").

### Testing standards

pytest; AAA; coverage ≥90% (§1). TDD-first (§2): classification + dispatch-swap + RED-gate + conformance
tests are the failing-first commit. **Greenfield regression is a first-class AC** (empty `legacy_code_globs`
→ byte-identical to today). Brownfield conformance asserts mock-vs-claude byte identity (2B.3) without a
third factory.

---

## Decisions Needed

- **D1 — Which specialist plays the characterization-test author role?** (The central decision — `tdd-strategist`
  already exists with an incompatible role.)
  - **(a) Author a NEW specialist** (e.g. `phase3/characterization-author.md`) for the `pending`-stage swap;
    leave the shipped `tdd-strategist` (strategy advisor) untouched. Roster 39→40 (in-band). Clean separation
    of responsibilities; no 2B.10 breakage; well-named for its `{files, tests_status}`→`tests/**` contract.
    Cost: deviates from the epics' literal "tdd-strategist" name → one-line ADR-030 planned-vs-shipped
    amendment + matrix shipped-row + index.yaml + three-way name + test-list/wheel-allowlist chores.
    **(Recommended — the shipped `tdd-strategist` is a genuinely different role; overloading it would force
    one specialist to emit two contradictory contracts and would destroy the 2B.10 strategy capability + its
    test pins.)**
  - **(b) Redefine the existing `tdd-strategist`** into the characterization-test author (rewrite role + I/O
    contract → `{files, tests_status}` to `tests/**`; update its `write_globs`). Roster stays 39; matches the
    epics' literal name. Cost: destroys the 2B.10 strategy-advisor role, breaks `test_phase3_2b10_authoring.py`
    pins + `docs/specialists-matrix.md:53`, and needs an ADR-030 amendment for the role change. Higher blast
    radius, semantically muddled name.
- **D2 — How is `tdd_strategy` assigned per task (deterministically)?**
  - **(a) Deterministic classifier in the CLI/pipeline layer** — `/sdlc-break` post-pass matches each task's
    target paths against `legacy_code_globs` and stamps `tdd_strategy`. Requires a way to know a task's target
    paths: add a lightweight `target_globs`/`touches: list[str]` field to the task record the breaker fills,
    or derive from a convention. Most deterministic + testable; conformance-friendly. **(Recommended — keeps
    glob-matching out of the LLM; the mock trivially reproduces it.)**
  - **(b) LLM `task-breaker` sets `tdd_strategy`** — pass `legacy_code_globs` into the breaker prompt; it sets
    the field per task using its understanding of what each task implements. No new field, but the LLM performs
    glob reasoning (less deterministic; the mock body must hardcode matching outputs to preserve byte identity).
- **D3 — `task-breaker` in-place vs separate file?** (epics.md:1992 — "either way is acceptable per Architecture".)
  - **(a) Update `task-breaker.md` in place** with brownfield-mode guidance (the deterministic classifier in
    D2(a) does the actual stamping). Roster stays 39; no index.yaml/matrix churn; single source of truth for
    task breaking. **(Recommended.)**
  - **(b) Add `task-breaker-brownfield.md`** — separate specialist for brownfield runs. Roster 39→40; needs
    full registry/matrix/ADR-030 reconciliation; duplicates most of `task-breaker`. Larger surface, more drift.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

claude-opus-4-8 (dev-story)

### Debug Log References

- StrictModel strict config rejects Python `list → tuple` coercion → `touches` typed `list[str]`
  (matching `dependencies`) rather than `tuple[str, ...]`, so both Python construction and JSON-array
  parsing succeed under `_TaskEntry`'s strict config.
- `_task_pipeline.py` LOC cap: the swap pushed it to 403 (cap 400); trimmed helper docstring + gate
  comment to land at exactly 400. (Larger refactor of this file is out of scope.)

### Completion Notes List

- **D1=(a)/D2=(a)/D3=(a)** — all Recommended. The shipped `tdd-strategist` (2B.10 strategy-layer
  markdown advisor → `03-Implementation/tasks/**`) was left untouched; a NEW
  `characterization-author` (Phase 3, emits `{files, tests_status:'green'}` → `tests/**`) plays the
  brownfield characterization role. Roster 39 → 40, in band `[39,45]`.
- **Deterministic, CLI-side classification (D2(a))** keeps glob-matching out of the LLM so the 2B.3
  mock-vs-claude byte identity holds: `task-breaker` emits `touches`; `/sdlc-break` stamps
  `tdd_strategy` via `classify_tdd_strategy(touches, legacy_code_globs)`. `touches` is input-only
  (`exclude=True`) and never serialized; only `tdd_strategy` persists to the task JSON.
- **Greenfield regression is byte-identical:** empty `legacy_code_globs` → every task
  `write-tests-first`; the static `_STAGE_SPECIALIST` map stays frozen (the `pending` swap is a
  data-driven helper, not a map mutation), so the 2A.17 pipeline tests + e2e break path are unchanged.
- **Conditional RED-gate:** characterization tasks require `tests_status == green` (tests capture
  current behavior → must pass); `write-tests-first` keeps the strict RED requirement. The parser
  `Literal["red","green"]` is unchanged (no new status value).
- **No wire-format ceremony:** `_TaskEntry` is not an ADR-024 snapshot contract; the 6 frozen
  contracts are unchanged (`freeze_wireformat_snapshots --check` green).
- **§4 chunked review pending** — executed by the `code-review` workflow now that status is `review`.

### File List

New:
- `src/sdlc/cli/_brownfield.py` — deterministic classifier + segment-aware `**` matcher + brownfield mock body
- `src/sdlc/agents/phase3/characterization-author.md` — net-new Phase-3 specialist (D1=(a))
- `tests/unit/cli/test_brownfield_classify.py`
- `tests/unit/cli/test_task_entry_tdd_strategy.py`
- `tests/unit/cli/test_break_command_brownfield.py`
- `tests/unit/cli/test_task_command_brownfield.py`
- `tests/unit/specialists/test_phase3_38_brownfield_authoring.py`
- `tests/integration/test_abstraction_adequacy_brownfield.py`

Modified:
- `src/sdlc/cli/_epic_story_models.py` — `_TaskEntry.tdd_strategy` (serialized) + `touches` (input-only)
- `src/sdlc/cli/_break_pipeline.py` — `break_dispatch_write(legacy_code_globs=...)` + per-task stamping
- `src/sdlc/cli/break_.py` — load `project.yaml` `legacy_code_globs`; brownfield mock selection
- `src/sdlc/cli/_task_pipeline.py` — `select_stage_specialist()` + conditional RED-gate
- `src/sdlc/cli/_task_pipeline_mocks.py` — `mock_characterization_author_body`
- `src/sdlc/cli/task.py` — selector wiring + characterization mock-body branch
- `src/sdlc/agents/phase3/task-breaker.md` — `touches` field + brownfield-mode guidance (D3=(a))
- `src/sdlc/agents/index.yaml` — `characterization-author` row
- `docs/specialists-matrix.md` — §1 row + §4 totals 39→40 + §3 note
- `docs/decisions/ADR-030-specialist-roster-freeze.md` — Revision Log amendment
- `tests/integration/test_wheel_build.py` — wheel allowlist row
- `tests/unit/specialists/test_phase3_2b10_authoring.py` — `_ALL_PHASE3_NAMES` union

## Change Log

- 2026-06-02: Story drafted (create-story) — Layer-1 independent leaf of Epic 3. Surfaced the
  `tdd-strategist`-already-exists conflict (D1), the `pending`-vs-`write-tests` stage correction, and the
  `tdd_strategy` net-new field. Status: ready-for-dev.
- 2026-06-02: dev-story T0 — decisions locked (all Recommended): **D1=(a)** author a NEW
  `phase3/characterization-author.md` (leave shipped `tdd-strategist` untouched); **D2=(a)** deterministic
  CLI-side classifier (`task-breaker` emits a `touches` field; `/sdlc-break` stamps `tdd_strategy` by glob
  match — glob-matching stays out of the LLM so mock-vs-claude byte identity holds); **D3=(a)** update
  `task-breaker.md` in place (no separate brownfield specialist file). Status: ready-for-dev → in-progress.
- 2026-06-02: dev-story implementation complete (TDD-first: test→feat). All 8 ACs satisfied; classifier +
  `tdd_strategy`/`touches` contract field + `/sdlc-break` wiring + `/sdlc-task` characterization dispatch +
  conditional RED-gate + `characterization-author` specialist + registry/matrix/ADR-030 reconciliation +
  brownfield conformance. Quality gate green (ruff, mypy --strict, pytest 2994 passed, coverage 89.78%≥87,
  pre-commit, mkdocs --strict, wire-format 6/6). Roster 39→40. Status: in-progress → review.
