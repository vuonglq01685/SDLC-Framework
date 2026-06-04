# Story 3.3: Pass 2 — Interactive Symlink Offer + `adopted-symlinks.json` Tracking

**Status:** done

**Epic:** 3 — Brownfield Adopt Mode (`sdlc init --adopt`)
**Layer:** 3 (`docs/sprints/epic-3-dag.md` §3 — second serial-spine pass; max-parallel 1)
**Worktree:** `epic-3/3-3-pass2-symlink-offer` (owner: Charlie, DAG §5 table)
**Critical Path:** 3.1 → 3.2 → **3.3** → 3.4 → 3.6 → 3.7 (DAG §4 — 3.3 is the 2nd spine pass; 3.4 stamps the symlinks 3.3 produces, 3.5 rolls them back, 3.6 recognises them for idempotency, 3.7 property-tests them; any slip here stalls 3.4/3.5/3.6/3.7).
**Depends on (satisfied):** Story 3.2 (`done`, merged to `main`) — froze the `detected[]` Pass 1 produces (`DetectedArtifact{path, kind, confidence:int, suggested_target}`), the `offer_symlinks(root, detected)` seam (`adopt/passes/symlink_offer.py:16`), and the `git_signal`/`legacy_code_globs` dependency-injection pattern this story mirrors. Story 3.1 (`done`) froze the `adopt/` layout, the three-pass driver, and the `AdoptReport` contract (6th locked).
**Parallel sibling (same layer):** none — Layer 3 is a single story (the adopt spine is serial; DAG §3/§6).

---

## Story

As an **engineer implementing Pass 2 of the three-pass adopt driver**,
I want **`offer_symlinks(root, detected)` to walk the `detected[]` Pass 1 produced and, for each artifact at or above a configurable confidence threshold, offer (interactively `[Y/n/edit]`, or auto-accept when non-interactive) to create a relative symlink from the canonical SDLC slot to the pre-existing source artifact — recording every accepted mapping atomically in a new frozen `.claude/state/adopted-symlinks.json` wire-format contract and journaling a `symlink_accepted` event per symlink — without ever modifying a source file**,
so that **a maintainer (Khanh persona) running `sdlc init --adopt` keeps file-by-file control over which legacy artifacts become "officially" adopted into the canonical layout, Pass 3 (Story 3.4) has a manifest to stamp, and Story 3.5 has a manifest to roll back (FR2 Pass 2, NFR-REL-6)**.

---

## Acceptance Criteria

> **Scope note — read first.** Story 3.3 fills the **Pass 2 interactive symlink offer + tracking ONLY**, behind the
> `offer_symlinks(root, detected) -> None` seam that Story 3.1 froze (`adopt/passes/symlink_offer.py:16`, currently
> `return None`). It does **NOT** implement Pass 3's `imported_from_existing` stamp (Story 3.4), does **NOT** implement
> rollback (`sdlc adopt rollback`, Story 3.5), does **NOT** implement target-exists conflict resolution (Story 3.6 —
> 3.3 only **detects** the collision and defers, AC4), and does **NOT** own the source-untouched property/mutation
> gate (Story 3.7 — 3.3 must merely *be* correct, not run that property). It consumes the frozen `detected[]` read-only.
> Five material decisions — **D1** (threshold value + single-vs-two thresholds), **D2** (`AdoptedSymlinks` contract
> shape), **D3** (`edit` action behaviour), **D4** (symlink-helper module location), **D5** (AC4 conflict interim
> behaviour) — are resolved at T0 in "Decisions Needed" before any code is written.
>
> **Verified-ground-truth correction (binding) — `confidence` is an integer percent, NOT a float.**
> Epics.md:1803/1826/1839 show `confidence ∈ [0.0, 1.0]` and a prompt reading `confidence 0.92`. **The FROZEN
> contract supersedes this:** `DetectedArtifact.confidence: int = Field(ge=0, le=100)` (`contracts/adopt_report.py:46`,
> Story 3.1 D2(a)). Architecture.md:494,515 forbid Python floats in `.claude/state/*` JSON, and `StrictModel`
> (`strict=True`) rejects a float at validation. **Pass 2 MUST render `confidence 92` (or `92%`), NOT `0.92`**, the
> `project.yaml` auto-accept threshold MUST be an **integer percent**, and every `confidence ≥ threshold` comparison
> is integer math. A float threshold in config would itself violate the no-floats-in-state rule.
>
> **Verified-ground-truth correction (binding) — this story ADDS a wire-format contract (NOT populate-only).**
> Unlike Story 3.2 (which only populated the frozen `detected[]`), Story 3.3 introduces `adopted-symlinks.json` as a
> cross-invocation surface (read by 3.4 stamp, 3.5 rollback, 3.6 idempotency). It is the **7th locked wire-format
> contract** (`ADR-024:157` — "Story 3.3 will add `adopted_symlinks` as the 7th"). This REQUIRES the full ADR-024
> ceremony: a new `AdoptedSymlinks(StrictModel)` model at `schema_version=1`, registration as the 7th entry in
> `_WIRE_FORMAT_REGISTRY` + `__all__` (`contracts/__init__.py:34`), a committed JSON-Schema snapshot at
> `tests/contract_snapshots/v1/adopted_symlinks.json` via `scripts/freeze_wireformat_snapshots.py --write`, and an
> ADR-024 amendment Change-Log row. The two-gate enforcement (`tests/contracts/test_wireformat_immutability.py` +
> the `freeze_wireformat_snapshots.py` pre-commit hook) will fail until the snapshot is committed. **Do NOT touch
> `AdoptReport`/`DetectedArtifact`** (6th locked contract) — consume them read-only.
>
> **Verified-ground-truth correction (binding) — new journal kind needs an ADR-028 amendment.**
> Pass 2 emits `kind=symlink_accepted` per accepted symlink. `JournalEntry.kind` is a free-form `str` (no contract
> edit needed), BUT ADR-028 §3 is the canonical kind taxonomy and today lists only `adopt_pass_started/completed/failed`
> (`ADR-028:92-94`). Adding `symlink_accepted` requires an ADR-028 §3 table row + Change-Log entry; `bmad-code-review`
> flags any undocumented `kind="..."` literal in `src/sdlc/` (`ADR-028:107`).

1. **Interactive per-artifact offer (AC: FR2 Pass 2, epics.md:1824-1829).** When Pass 2 runs **interactively** (a TTY
   and not `--json`/`--non-interactive`), for each `DetectedArtifact` in `detected[]` whose `confidence ≥` the
   threshold (D1) and whose `suggested_target` is non-empty, the user is prompted (rendering confidence as an
   **integer**): `Found docs/architecture-2024.md (architecture, confidence 92). Symlink to
   02-Architecture/02-System/ARCHITECTURE.md? [Y/n/edit]`. **`Y`** → create the symlink + record the mapping;
   **`n`** → skip (no symlink, no record); **`edit`** → let the user override the suggested target path before
   re-deciding (D3). Artifacts with an empty `suggested_target` (detect-only kinds per Story 3.2 D1:
   readme/runbook/ci-workflow/build-file/dockerfile) are **not** offered.

2. **Symlink creation + atomic tracking + journal (AC: epics.md:1831-1835).** On accept, a **relative** symlink
   (`os.symlink`, POSIX-only per ADR-034) is created at the canonical target path pointing back to the source
   artifact; `.claude/state/adopted-symlinks.json` is updated **atomically** (reuse `atomic_write_bytes`, canonical
   JSON bytes identical to the driver's `_report_bytes` — sorted keys, UTF-8, `ensure_ascii=False`,
   `separators=(",",":")`, NFC, trailing `\n`, no floats); and a journal entry
   `kind=symlink_accepted, payload={source, target, kind}` is appended via the SYNC API
   (`allocate_next_seq_for_append_sync` + `append_sync`, event-only zero-sentinel `after_hash`), mirroring
   `driver._append_event`.

3. **Non-interactive auto-accept threshold — THIS STORY OWNS IT (AC: epics.md:1837-1841).** When Pass 2 runs
   **non-interactively** (`--non-interactive`, OR `--json`, OR no TTY), every candidate with `confidence ≥` the
   auto-accept threshold is accepted automatically; candidates below threshold are **skipped with a warning** (via
   `cli/output`, not `print`). **The threshold is an integer percent, has a documented default (D1), and is
   configurable via `project.yaml`** (`auto_accept_threshold` field added to `config/project.py:ProjectConfig`). A
   new `--non-interactive` flag is added to the `init` command (none exists today); `--json` implies
   `--non-interactive` (prompts would corrupt the machine-readable channel).

4. **Target-exists conflict detected and deferred to Story 3.6 (AC: epics.md:1843-1845).** If the canonical target
   path already exists (a real file, or a symlink pointing elsewhere), Pass 2 does **not** clobber it: per the D5
   interim posture it is skipped with a warning and **not** recorded (full skip/backup-replace/different-target
   resolution is Story 3.6). An already-correct symlink (target already points at this source) is treated as a no-op
   success (idempotent), recorded if not already present.

5. **`adopted-symlinks.json` is a frozen wire-format contract (AC: ADR-024 7th locked, epic-3-dag.md:186/D1).**
   `AdoptedSymlinks(StrictModel)` exists with `schema_version: Literal[1]` and a `mappings` tuple of
   `{source: str, target: str, accepted_at: <RFC-3339 UTC>, kind: ArtifactKind}` (D2); it is registered as the 7th
   `_WIRE_FORMAT_REGISTRY` entry + in `__all__`; its JSON-Schema snapshot is committed at
   `tests/contract_snapshots/v1/adopted_symlinks.json`; and ADR-024 carries an amendment row. A round-trip
   (`model_validate_json(model_dump_json())`) is byte-stable and `test_wireformat_immutability.py` passes 7/7.

6. **Source untouched (AC: NFR-REL-6, prd.md:290/841, epics.md:1820).** Pass 2 writes ONLY: (a) the symlinks at
   canonical SDLC target paths (the one sanctioned write *outside* `.claude/`), and (b)
   `.claude/state/adopted-symlinks.json` + the journal. Every source artifact (the symlink *source*, e.g.
   `docs/architecture-2024.md`) is byte-identical pre/post. `assert_path_under_claude` guards the manifest write but
   **cannot** guard the symlink-target write (the target lives in the project root, outside `.claude/`); the
   correctness obligation is "source files unchanged," which Story 3.7 mechanically verifies.

7. **Boundary held + dependency injection (AC: architecture.md:1110, module_boundary_table.py).** `adopt/` does NOT
   import `cli/` (or `engine/`/`dispatcher/`/`runtime/`). Interactivity and the threshold are **injected from the
   `cli` layer**, mirroring Story 3.2's `git_signal` DI exactly: `cli/adopt.py` builds a confirm-callback +
   resolves the threshold (from `project.yaml`) and the interactivity mode, and threads them through
   `run_adopt(...)` → `_run_pass(2, ...)` → `offer_symlinks(...)`. New kwargs default to the non-interactive /
   no-op value so resume runs and non-adopt callers are unaffected.

8. **Quality gate green (AC: §1).** ruff format/check + `mypy --strict src/` + pytest + coverage (operational floor
   `--cov-fail-under=87`; ≥90 tracked as `EPIC-2B-DEBT-COVERAGE-90-FLOOR`) + pre-commit (incl.
   `check_module_boundaries`, `check_subprocess_allowlist`, `freeze_wireformat_snapshots --check` **7/7**) + mkdocs
   `--strict`. TDD-first (§2): tests-first RED commit before implementation, visible in `git log --reverse`.

---

## Tasks / Subtasks

- [x] **(AC8, §5) T0 — Resolve D1/D2/D3/D4/D5 in the PR Change Log BEFORE writing code.** Lock: D1 (threshold
  default value + single-vs-two-threshold semantics), D2 (`AdoptedSymlinks` model shape + file location + field
  names), D3 (`edit`-action override behaviour + validation), D4 (symlink-helper module path — reconcile DAG's
  `adopt/symlink.py` name with the 3.1-frozen `adopt/passes/` layout), D5 (AC4 conflict interim behaviour). D2/D4
  gate the wire-format snapshot + the file you create, so settle them first.
- [x] **(AC5, §2) Add the `AdoptedSymlinks` wire-format contract + ceremony (tests-first where applicable):**
  - new `src/sdlc/contracts/adopted_symlinks.py` — `AdoptedSymlinks(StrictModel)` + `SymlinkMapping(StrictModel)`
    (D2); reuse `ArtifactKind` + the `_RFC3339_UTC` pattern from `contracts/adopt_report.py`; `mappings` is a
    `tuple[SymlinkMapping, ...] = Field(default_factory=tuple, strict=False)`; `schema_version: Literal[1]` with the
    same `_strict_schema_version` before-validator as `AdoptReport`;
  - register `("adopted_symlinks", AdoptedSymlinks)` as the **7th** entry in `_WIRE_FORMAT_REGISTRY` and add to
    `__all__` (`contracts/__init__.py:19-41`);
  - commit the snapshot: `python -m scripts.freeze_wireformat_snapshots --write` → `tests/contract_snapshots/v1/adopted_symlinks.json`;
  - add an ADR-024 amendment Change-Log row (7th contract) and confirm `freeze_wireformat_snapshots.py --check` is 7/7.
- [x] **(AC1, AC2, AC3, §2) Write the failing Pass-2 unit tests FIRST, commit before implementation** (`tests/unit/adopt/test_symlink_offer.py`):
  - interactive: a high-confidence artifact + a `Y` decision → relative symlink created at the canonical target,
    pointing at the source; mapping appended to `adopted-symlinks.json`; `symlink_accepted` journal entry emitted;
  - `n` decision → no symlink, no record; `edit` decision → target overridden then created (D3);
  - non-interactive: confidence ≥ threshold auto-accepted; confidence < threshold skipped **with a warning** and not
    recorded; detect-only kinds (empty `suggested_target`) never offered;
  - confidence rendered as **int** in the prompt (assert no `0.` float substring); threshold read as int from config.
- [x] **(AC4, §2) Write the conflict + idempotency tests FIRST:** pre-existing real file at target → skipped + warned
  + not recorded (defer to 3.6, D5); target already a correct symlink → idempotent no-op success.
- [x] **(AC6, AC7, §2) Write the source-untouched + boundary tests FIRST:** after Pass 2, the source artifact bytes
  are unchanged and only `.claude/` + the new symlinks changed; `adopt/` imports contain no `cli`/`engine`/
  `dispatcher`/`runtime` (covered by `check_module_boundaries`, but add a focused assertion on `symlink_offer.py`).
- [x] **(AC1-AC4, AC7) Implement `offer_symlinks` (GREEN):** in `src/sdlc/adopt/passes/symlink_offer.py`, extend the
  seam signature with injected kwargs (e.g. `*, confirm: Callable[[DetectedArtifact, str], SymlinkDecision] | None = None,
  auto_accept_threshold: int = <default>, journal_path: Path | None = None`) — keep the no-op default so 3.1's
  orchestrator-ordering test and resume runs are unaffected. Add the symlink-creation helper at the D4-ratified
  location (relative `os.symlink` + `os.path.relpath`). The pure core decides; the `cli` layer prompts.
- [x] **(AC1-AC3, AC7) Thread the DI through the driver:** extend `driver._run_pass` + `run_adopt` to accept and
  forward `confirm` + `auto_accept_threshold` (+ `journal_path` to Pass 2 so it can journal), exactly mirroring how
  `git_signal`/`legacy_code_globs` are threaded (`driver.py:117-140,158-189`); defaults keep non-adopt callers
  unaffected.
- [x] **(AC3) Add the `auto_accept_threshold` config field:** `config/project.py:ProjectConfig` — integer percent,
  `Field(default=<D1>, ge=0, le=100, strict=True)`; document it in the `project.yaml` schema docs.
- [x] **(AC1, AC3) Add the CLI flag + build the confirm-callback + inject (cli layer):** add `--non-interactive`
  (and decide on `--yes` alias, D1) to the `init` command (`cli/main.py`); in `cli/adopt.py` resolve the
  interactivity mode (TTY + `--json` + flag), read the threshold from `project.yaml` (extend
  `_load_legacy_code_globs`'s config read), build a `typer`-based `[Y/n/edit]` confirm-callback that renders the
  prompt via `cli/output`, and inject both into `run_adopt(...)`. `--json` ⇒ non-interactive.
- [x] **(ADR-028) Amend the journal taxonomy:** add a `symlink_accepted` row to ADR-028 §3 (alphabetised within the
  Story-3.3 source column) + a Change-Log entry; payload `{source, target, kind}`.
- [ ] **(AC8, §4) Chunked review** review-A (correctness / AC↔tests / confidence-int + threshold-int fidelity) →
  review-B (boundary: no `adopt→cli` import, confirm-callback DI clean, source-untouched, atomic write,
  subprocess/path guards) → review-C (wire-format snapshot 7/7 + ADR-024/028 amendments + relative-symlink
  correctness + prompt-string exactness + naming); no skipping. Review commits carry `[fresh-context-review]` and
  stage no `src/` files (§4.4). **→ Runs in the `code-review` workflow once dev-story sets status=review.**

---

## Dev Notes

### What 3.1 + 3.2 froze — the seam 3.3 fills

- **The seam (do NOT change its public name):** `offer_symlinks(root: Path, detected: Sequence[DetectedArtifact]) -> None`
  at `src/sdlc/adopt/passes/symlink_offer.py:16` — a Story-3.1 no-op. The driver dispatches Pass 2 at
  `driver.py:136-138`: `symlink_offer.offer_symlinks(root, detected); return detected`. You MAY add keyword-only
  injected params (with no-op defaults) without breaking the 3.1 orchestrator-ordering tests.
- **The input (frozen, read-only):** `detected: tuple[DetectedArtifact, ...]`, `DetectedArtifact{path: str,
  kind: ArtifactKind, confidence: int[0,100], suggested_target: str}` (`contracts/adopt_report.py:41-47`). Empty
  `suggested_target` ⇒ detect-only kind (Story 3.2 D1) ⇒ not offerable.
- **The DI pattern to mirror (Story 3.2):** `cli/_git_recency.py` computes a signal in the `cli` layer (which holds
  the grant) and injects it via `detect_existing(root, *, git_signal=...)`; the driver threads `git_signal` +
  `legacy_code_globs` through `_run_pass` and `run_adopt` with no-op defaults (`driver.py:117-140,158-189`). Do the
  identical thing for `confirm` + `auto_accept_threshold` + `journal_path`.

### The new `AdoptedSymlinks` contract — ADDITION, full ADR-024 ceremony (the big difference from 3.2)

- Story 3.2 was **populate-only** (no contract/snapshot change). Story 3.3 is **NOT** — it adds the 7th locked
  wire-format contract. The snapshot dir currently holds **6**: `journal_entry, resume_token, hook_payload,
  specialist_frontmatter, workflow_spec, adopt_report` (`tests/contract_snapshots/v1/`). ADR-024:157 explicitly
  reserves the 7th for `adopted_symlinks`; `contracts/__init__.py:33` comment says "3.3 adds `adopted_symlinks`".
- Mirror `AdoptReport` exactly (`contracts/adopt_report.py:50-65`): inherit `StrictModel`
  (`strict=True, extra="forbid", frozen=True`, per CLAUDE.md binding rule + ADR-025), `schema_version: Literal[1] = 1`
  with the `_strict_schema_version` before-validator, reuse `ArtifactKind` + `_RFC3339_UTC`, and make container
  fields `Field(default_factory=tuple, strict=False)` (the StrictModel container opt-out convention).
- Canonical shape (epics.md:1834): `{schema_version: 1, mappings: [{source, target, accepted_at: <iso8601 Z>, kind}]}`.
  Use `now_rfc3339_utc_ms()` (`ids.clock`) for `accepted_at` — same source the driver uses.
- Ceremony order: write model → register 7th in `_WIRE_FORMAT_REGISTRY` + `__all__` → `freeze_wireformat_snapshots
  --write` → ADR-024 amendment row → confirm `--check` 7/7. The pre-commit hook + `test_wireformat_immutability.py`
  block until the snapshot is committed.

### Symlink creation — relative, POSIX-only, source-untouched

- Create a **relative** symlink (epics.md:1827): `os.symlink(os.path.relpath(source_abs, start=target_parent), target)`.
  POSIX-only (ADR-034; the integration/e2e adopt tests `pytest.skip` on win32 at module level — follow that pattern).
- The symlink **target** (canonical slot, e.g. `02-Architecture/02-System/ARCHITECTURE.md`) lives in the project
  root, OUTSIDE `.claude/`. `assert_path_under_claude(root, path)` (`adopt/invariant.py`) guards the *manifest* write
  but CANNOT guard the symlink-target write — this is the one sanctioned write outside `.claude/`. The invariant that
  matters is "the **source** file is byte-identical"; never copy-into-source.
- Wrap `OSError` from `os.symlink`/manifest write into a typed `AdoptError` (don't leak tracebacks), mirroring
  `driver._write_report`'s `except OSError` handling. The driver already wraps any Pass exception into `AdoptError`
  → `cli/adopt.py` maps to the `ERR_ADOPT` envelope (exit 2).

### Atomic manifest write + journal

- Reuse `atomic_write_bytes` (`concurrency.io_primitives`) — the same primitive the driver uses for
  `adopt-report.json` — with byte-for-byte the same canonicalisation as `driver._report_bytes` (sorted keys, UTF-8,
  `ensure_ascii=False`, `separators=(",",":")`, NFC, trailing `\n`). Pre-guard with `assert_path_under_claude`.
- Journal `symlink_accepted` via the SYNC API (`allocate_next_seq_for_append_sync` + `append_sync`), event-only
  (`before_hash=None`, `after_hash="sha256:"+"0"*64`), `actor="cli"`, copying `driver._append_event`. The driver must
  pass `journal_path` into Pass 2 (it currently only journals pass start/complete itself).

### Boundary, interactivity, JSON mode

- `adopt/` granted deps: `errors, contracts, ids, concurrency, state, journal, signoff, config` — NO `cli`/git grant
  (`scripts/module_boundary_table.py`). The prompt must be produced in the `cli` layer; the pure core receives a
  `confirm` callback and returns/acts on a decision. `adopt/` must NOT `print()` — human output goes through
  `cli/output` only (architecture.md:489).
- No confirm/prompt helper exists in `cli/` yet — Story 3.3 introduces the first interactive prompt (use
  `typer.prompt`/`typer.confirm` or a small `[Y/n/edit]` reader in `cli`). The only TTY precedent is
  `sys.stdin.isatty()` in `cli/hook_check.py:127`. Global flags today are `--version/--no-color/--json`
  (`cli/main.py`); `ctx.obj["json"]` carries JSON mode. `--json` ⇒ force non-interactive (no prompts on the
  machine-readable channel).

### Citation-drift / reconciliation notes (verified)

- **Module name:** `epic-3-dag.md:116/151` and the 3.7 mutation-target list name `adopt/symlink.py`, but Story 3.1
  froze the realised layout as `adopt/passes/symlink_offer.py` (`adopt/passes/__init__.py`). **D4** ratifies the
  helper location (recommended: a sibling helper under `adopt/passes/` to stay consistent with the frozen layout;
  note the rename so 3.7's target list is updated).
- **`confidence 0.92`** in the epics prompt string (epics.md:1826) is stale vs the frozen int contract — render `92`.
- **`--non-interactive` flag** is named in epics.md:1837 but does not exist on the CLI yet — add it.
- **Auto-accept threshold has NO numeric default anywhere** (epics.md:1841 only says "documented + configurable via
  `project.yaml`") — **D1** defines it. `ProjectConfig` has no threshold field today (`config/project.py:27-30`).

### Project Structure Notes

- **New:** `src/sdlc/contracts/adopted_symlinks.py`; `tests/contract_snapshots/v1/adopted_symlinks.json`;
  `tests/unit/adopt/test_symlink_offer.py`; tests under `tests/contracts/`; ADR-024 + ADR-028 amendment rows.
- **Edit:** `src/sdlc/adopt/passes/symlink_offer.py` (implement); `src/sdlc/adopt/driver.py` (thread `confirm` +
  `auto_accept_threshold` + `journal_path` through `_run_pass`/`run_adopt`); `src/sdlc/contracts/__init__.py`
  (register 7th); `src/sdlc/cli/adopt.py` + `src/sdlc/cli/main.py` (add `--non-interactive`, build + inject the
  confirm-callback + threshold); `src/sdlc/config/project.py` (add `auto_accept_threshold`).
- **Do NOT edit:** `src/sdlc/contracts/adopt_report.py` (FROZEN 6th contract); the existing 6 snapshots; the journal
  / atomic primitives.
- ≤400 LOC per file (NFR-MAINT-3); extract the symlink helper rather than bloating `symlink_offer.py`.

### Testing standards

- pytest; AAA structure; coverage ≥90% (§1 target; operational ≥87 floor). TDD-first (§2): contract test + Pass-2
  unit tests in a RED commit before the GREEN implementation (the 3.2 commits show this `test(3.2) RED → feat(3.2)
  GREEN` ordering). adopt mode is POSIX-only (ADR-034) — module-level `pytest.skip` on win32 (see
  `tests/integration/test_adopt_mode_invariant.py:19-20`, `tests/unit/cli/test_adopt.py:17-18`).
- The binding brownfield golden/property CI gate over fixtures is **Story 3.7**, not 3.3 — 3.3 needs correctness +
  unit/contract coverage, not the multi-fixture property test.

### Previous-story intelligence (Story 3.2, done + merged)

- 3.2 landed `detect_existing` + the `git_signal` DI + the brownfield fixture corpus + the golden-corpus gate. Its
  code-review (CR3.2) applied 7 patches; **relevant carry-over for 3.3**:
  - **CR3.2-W3 (deferred):** `_load_legacy_code_globs` (`cli/adopt.py:66-75`) catches only `ConfigError` — a
    permission-denied/non-UTF8 `project.yaml` escapes uncaught. When you extend that config read for
    `auto_accept_threshold`, consider broadening the catch (it's a documented project-wide gap).
  - 3.2's `cli/adopt.py` already reads `project.yaml` via `_load_legacy_code_globs` and injects `git_signal` +
    `legacy_code_globs` into `run_adopt` — extend that exact read+inject path for the threshold + confirm-callback.
  - 3.2 used `core.excludesFile=/dev/null` in its real-git integration fixture for hermeticity (a global
    `~/.gitignore_global` with `*.md` had silently untracked `.md` artifacts). If any 3.3 test builds a real git repo
    with `.md` sources, set the same hermetic config.
  - `confidence` int-percent encoding is firmly established; the recency boost (+5, capped 100) is applied in Pass 1,
    so a `detected[]` confidence may be up to 100 in production. Threshold comparisons are pure integer.

## Decisions Needed

> Resolve at T0 in the PR Change Log (CONTRIBUTING §5), mirroring Story 3.2's D1-D4 ratification. Recommended option
> first; the dev locks the choice before writing code.

- **D1 — Auto-accept threshold value + single-vs-two-threshold semantics.**
  - **(a) [Recommended]** ONE integer `auto_accept_threshold` (default **80**), used both to gate which artifacts are
    offered interactively (confidence ≥ threshold ⇒ prompt; below ⇒ silent skip) and to auto-accept non-interactively
    (≥ ⇒ accept, below ⇒ skip+warn). Rationale: matches the single "threshold" word in epics.md:1826/1841; default 80
    auto-accepts architecture(≥85)/readme(≥90)/ci/build/dockerfile(95) and leaves prd(80 — boundary, included)/
    research(75)/runbook(75)/unknown(40) — tune the exact default with the Story 3.2 confidence table in mind.
  - (b) Two separate fields (`offer_threshold` for interactive gating, `auto_accept_threshold` for non-interactive).
- **D2 — `AdoptedSymlinks` contract shape + location.**
  - **(a) [Recommended]** new file `contracts/adopted_symlinks.py` with `SymlinkMapping(StrictModel){source, target,
    accepted_at, kind: ArtifactKind}` + `AdoptedSymlinks(StrictModel){schema_version: Literal[1], mappings: tuple[...]}`.
    Keeps `adopt_report.py` (frozen) untouched.
  - (b) co-locate both models in `adopt_report.py` (risks touching a frozen file — not recommended).
- **D3 — `edit` action behaviour.**
  - **(a) [Recommended]** `edit` re-prompts for a replacement target path (free text), validates it is a relative
    path under the project root (reject absolute / `..`-escaping), then re-offers `[Y/n]`.
  - (b) `edit` only allowed to pick among canonical SDLC slots (stricter; more code).
- **D4 — Symlink-helper module location** (reconcile DAG `adopt/symlink.py` vs 3.1-frozen `adopt/passes/`).
  - **(a) [Recommended]** helper under `adopt/passes/` (e.g. `adopt/passes/_symlink.py`) for layout consistency;
    note the rename so the 3.7 mutation-target list (`adopt/symlink.py`) is updated.
  - (b) create top-level `adopt/symlink.py` to match the DAG/3.7 text literally.
- **D5 — AC4 conflict interim behaviour (target exists).**
  - **(a) [Recommended]** skip + warn + do not record; leave full resolution (skip/backup-replace/different-target)
    to Story 3.6. An already-correct symlink is an idempotent no-op success.
  - (b) raise a typed marker that 3.6 will later catch (more coupling; defer).

### References

- [Source: epics.md:1818-1845] — Story 3.3 Pass 2 ACs: interactive offer, symlink+tracking, auto-accept threshold, conflict→3.6.
- [Source: epics.md:1834] — `adopted-symlinks.json` canonical shape `{schema_version, mappings:[{source,target,accepted_at,kind}]}`.
- [Source: epics.md:1826-1829] — prompt string + `[Y/n/edit]` semantics (confidence rendered int per binding correction).
- [Source: prd.md:290] — Journey 3 (Khanh): file-by-file symlink offer; accepted tracked in `.claude/state/adopted-symlinks.json` for rollback.
- [Source: prd.md:739] — FR2 adopt mode; [Source: prd.md:841] — NFR-REL-6 "adopt-mode never modifies source code".
- [Source: docs/decisions/ADR-024-*.md:157] — `adopted_symlinks` reserved as the 7th locked wire-format contract.
- [Source: docs/decisions/ADR-028-*.md:92-94,107] — adopt journal kinds today; undocumented `kind=` flagged by code-review.
- [Source: docs/sprints/epic-3-dag.md:95-97,109-116,144,151,186] — Layer 3, deps, serial spine, worktree owner, contract-drift risk.
- [Source: src/sdlc/adopt/passes/symlink_offer.py:16] — the seam to fill.
- [Source: src/sdlc/adopt/driver.py:117-140,158-212] — `_run_pass`/`run_adopt` DI threading + journal/atomic-write patterns to mirror.
- [Source: src/sdlc/contracts/adopt_report.py:24-65] — StrictModel + `schema_version` + `_RFC3339_UTC` + `ArtifactKind` to mirror.
- [Source: src/sdlc/contracts/__init__.py:33-41] — `_WIRE_FORMAT_REGISTRY` (register 7th here).
- [Source: src/sdlc/config/project.py:15-30] — `ProjectConfig` (add `auto_accept_threshold`).
- [Source: src/sdlc/cli/adopt.py:87-101] — existing config-read + DI injection point to extend.
- [Source: architecture.md:455,489,494-515,1110] — `.claude/state` layout, output-via-cli/output, no-floats canonical JSON, adopt boundary.

## Dev Agent Record

### Context Reference

- Story drafted by `bmad-create-story` (2026-06-03) on `main` after Story 3.2 was reviewed (done) and merged. Context
  extracted from epics.md, prd.md, architecture.md, ADR-024/025/028/034, epic-3-dag.md, and the frozen
  `adopt/`/`contracts/` code via parallel research agents.

### Agent Model Used

claude-opus-4-8 (1M context) — bmad-dev-story workflow, 2026-06-04.

### Debug Log References

- TDD-first: contract namespace RED (`test_init.py` 6-tuple) + Pass-2 RED (`ImportError: SymlinkDecision`) → GREEN. Wire-format gate RED (`adopted_symlinks.json` snapshot missing) → 7/7 GREEN after `freeze_wireformat_snapshots.py --write`.
- `offer_symlinks` initially tripped ruff C901 (complexity 10 > 8); extracted `_select_target` (detect-only / threshold-gate / confirm decision / `resolve_target`) so the loop body stays simple.
- Story-3.1/3.2 integration test `test_adopt_detects_artifacts_without_touching_source` updated: it predated Pass 2 and asserted "nothing outside `.claude/` changes" — Pass 2 now creates the sanctioned canonical symlink (AC6), so the invariant is restated as source-byte-identity + no tracked-file mutation.

### Completion Notes List

- **All 8 ACs MET.** AC1 interactive `[Y/n/edit]` offer (cli `_build_confirm_callback`, confidence rendered int); AC2 relative `os.symlink` + atomic `adopted-symlinks.json` (canonical bytes mirror `driver._report_bytes`) + `symlink_accepted` journal via SYNC API; AC3 non-interactive auto-accept threshold owned here (`auto_accept_threshold` in `ProjectConfig`, default 80, int-percent) + `--non-interactive` flag (`--json` ⇒ non-interactive); AC4 target-exists conflict → skip+warn (deferred to 3.6), already-correct symlink → idempotent record; AC5 `AdoptedSymlinks` = 7th locked wire-format contract (full ADR-024 ceremony, snapshot 7/7); AC6 source bytes byte-identical (the symlink TARGET write is the one sanctioned write outside `.claude/`; manifest pre-guarded by `assert_path_under_claude`); AC7 boundary held (no `adopt→cli`; `confirm`/`auto_accept_threshold`/`warn` DI mirrors 3.2's `git_signal`); AC8 quality gate.
- **T0 D1-D5 = all Recommended (a)** (see Change Log). Single threshold (D1), new `contracts/adopted_symlinks.py` (D2), free-text validated `edit` (D3), helper at `adopt/passes/_symlink.py` (D4), conflict skip+warn (D5).
- **Bonus — closed CR3.2-W3:** the cli `project.yaml` read (`_load_legacy_code_globs` → renamed `_load_project_config`) now also catches `OSError`/`UnicodeDecodeError`, not just `ConfigError`.
- **Binding ground-truth honoured:** `confidence` rendered as integer percent (never `0.92`); threshold is an integer field; the directory-style research slot (`…/02-Research/`) is normalised by appending the source basename before symlinking.
- adopt mode POSIX-only (ADR-034) — all new test modules `pytest.skip` on win32.

### File List

**New:**
- `src/sdlc/contracts/adopted_symlinks.py` — `AdoptedSymlinks` + `SymlinkMapping` (7th wire-format contract)
- `src/sdlc/adopt/passes/_symlink.py` — relative-symlink filesystem helper (D4) + `SymlinkOutcome` + target-under-root guard
- `tests/contract_snapshots/v1/adopted_symlinks.json` — committed JSON-Schema snapshot (7th)
- `tests/unit/contracts/test_adopted_symlinks.py` — contract strict-mode unit tests
- `tests/unit/adopt/test_symlink_offer.py` — Pass-2 core unit tests (AC1-AC7, fake-callback DI)

**Edited:**
- `src/sdlc/adopt/passes/symlink_offer.py` — implemented `offer_symlinks` + `SymlinkDecision`/`ConfirmCallback`/`WarnCallback` + manifest/journal helpers
- `src/sdlc/adopt/driver.py` — thread `confirm`/`auto_accept_threshold`/`warn` (+ `journal_path` to Pass 2) through `_run_pass`/`run_adopt`
- `src/sdlc/contracts/__init__.py` — register `AdoptedSymlinks` as the 7th `_WIRE_FORMAT_REGISTRY` entry + `__all__`
- `src/sdlc/config/project.py` — add `auto_accept_threshold` field + `DEFAULT_AUTO_ACCEPT_THRESHOLD` constant
- `src/sdlc/cli/main.py` — add `--non-interactive` to `init`; pass through to `run_adopt`
- `src/sdlc/cli/adopt.py` — resolve interactivity + build/inject confirm + warn callbacks + threshold; `_load_legacy_code_globs` → `_load_project_config` (broadened catch, CR3.2-W3)
- `docs/decisions/ADR-024-wire-format-v1-lock.md` — 7th-contract amendment row
- `docs/decisions/ADR-028-journal-kind-taxonomy.md` — `symlink_accepted` §3 row + Revision Log entry
- `tests/unit/contracts/test_init.py` + `tests/unit/contracts/test_f3_independence.py` — extend for the 7th contract
- `tests/unit/adopt/test_driver.py` — update `offer_symlinks` monkeypatch stubs for the extended seam signature
- `tests/unit/cli/test_adopt.py` — Story 3.3 cli wiring tests (auto-accept, `--non-interactive`, `--json`, threshold-from-config, confirm-callback int render + edit)
- `tests/integration/test_adopt_mode_invariant.py` — restate source-untouched invariant for Pass 2 (sanctioned symlink writes)

## Change Log

| Date | Change |
|---|---|
| 2026-06-04 | **T0 — D1-D5 ratified, all Recommended (a)** (user confirmation at dev-story T0). **D1=(a):** ONE integer `auto_accept_threshold` (default **80**), used both to gate which artifacts are offered interactively (confidence ≥ threshold ⇒ prompt; below ⇒ silent skip) and to auto-accept non-interactively (≥ ⇒ accept; below ⇒ skip+warn). Default 80 auto-includes architecture(85)/prd(80, boundary) and excludes research(75). **D2=(a):** new file `contracts/adopted_symlinks.py` with `SymlinkMapping(StrictModel){source, target, accepted_at, kind: ArtifactKind}` + `AdoptedSymlinks(StrictModel){schema_version: Literal[1], mappings: tuple[...]}`; `adopt_report.py` (frozen) untouched. **D3=(a):** `edit` re-prompts a replacement target (free text), validated relative + under project root (reject absolute / `..`-escape), then re-offers `[Y/n]`. **D4=(a):** symlink helper under `adopt/passes/_symlink.py` for layout consistency with the 3.1-frozen `passes/` package (DAG `adopt/symlink.py` name noted as superseded; 3.7 mutation-target list to be updated). **D5=(a):** target-exists conflict → skip + warn + do not record (full resolution = Story 3.6); an already-correct symlink is an idempotent no-op success, recorded if not already present. |

---

### Review Findings

> bmad-code-review (2026-06-04) — Blind Hunter + Edge Case Hunter + Acceptance Auditor (3 layers, none failed).
> Acceptance Auditor: **all 8 ACs MET, all 4 binding ground-truth corrections honored, no conformance violation.**
> Gate verified locally: ruff ✅, ruff format ✅, mypy --strict (153 files) ✅, wire-format snapshots 7/7 ✅, Story-3.3 test surface 84 passed ✅.
> Findings below are robustness/crash-consistency issues *beyond* the explicit ACs.

**Decisions (RESOLVED 2026-06-04 — both option (a), user ratified; now patch action items):**

- [x] [Review][Patch] (was Decision, RESOLVED → option a) Crash-consistency contract: make the journal authoritative — append the `symlink_accepted` journal event BEFORE writing the manifest, move `_write_manifest` to a SINGLE write after the per-artifact loop, and sample the accept timestamp once (reused for manifest `accepted_at` + journal `ts`). Absorbs the standalone timestamp patch (old P5) and the O(n²)-manifest-write item. Full crash-recovery (orphan-symlink reconciliation) explicitly stays with Stories 3.5/3.6 — document the residual gap in the module docstring. [`symlink_offer.py:104,185,199,204-206`]
- [x] [Review][Patch] (was Decision, RESOLVED → option a) Fail-soft on per-artifact errors — wrap each artifact's `create_relative_symlink`/target-validation in a try/except `AdoptError` inside `offer_symlinks`: on OSError (permission / read-only FS / no-symlink-support) OR abs/`..`-escaping target, emit a warning and `continue` (do not record), mirroring the CONFLICT branch, so one bad artifact no longer aborts the whole Pass 2. [`symlink_offer.py:185`, `_symlink.py:45-60,96-98`]

**Patches (unambiguous fixes):**

- [x] [Review][Patch] Guard source existence before creating the symlink [src/sdlc/adopt/passes/_symlink.py:66-93] — `source_abs` (`:77`) is never existence-checked; a source deleted between Pass 1/2, or a source that is itself a dangling symlink, yields a broken symlink recorded as accepted success + journaled. Add a source lexists/exists guard → skip+warn, do not record.
- [x] [Review][Patch] Unify + complete target path-safety validation [src/sdlc/cli/adopt.py:100-107 + src/sdlc/adopt/passes/_symlink.py:45 + symlink_offer.py:147] — CLI `_is_safe_relative_target` returns False→skip while core `assert_target_under_root` raises→abort: two divergent "stay under root" implementations that will drift. Core `_select_target` forwards `decision.target` from the injected callback with no re-validation (`:147`), so empty/whitespace/abs/`..` reaches the core unchecked. Consolidate into one shared helper + re-validate the callback target in the core (outcome ties to the fail-fast/soft decision).
- [x] [Review][Patch] Don't silently swallow a corrupt prior manifest [src/sdlc/adopt/passes/symlink_offer.py:82-95] — `_load_existing_mappings` catches `(OSError, ValueError)` and returns `[]` with no warning/journal (`:91`), permanently dropping previously-recorded mappings (their symlinks become untracked). Violates the "never silently swallow errors" rule. Warn (and/or journal) on a corrupt manifest.
- [x] [Review][Patch] Strengthen driver-order unit tests — they assert the mock [tests/unit/adopt/test_driver.py:93,205] — the order/resume tests stub `offer_symlinks` with `lambda root, detected, **_kw`, absorbing the new `journal_path`/`confirm`/`auto_accept_threshold`/`warn` kwargs, so the driver→Pass-2 wiring is never asserted at the unit layer. Capture + assert the forwarded kwargs.
- [x] [Review][Patch] Sample the accept timestamp once [src/sdlc/adopt/passes/symlink_offer.py:199 + :104] — FOLDED into the crash-consistency patch above (single timestamp reused for manifest `accepted_at` + journal `ts`).
- [x] [Review][Patch] Fix `--non-interactive` on greenfield `init` [src/sdlc/cli/main.py:78-89] — accepted on `init` but only consumed when `--adopt` is set, so `sdlc init --non-interactive` (no `--adopt`) is a silent no-op; unlike `--adopt` it is not `hidden=True`. Honor it, hide it, or error when used without `--adopt`; align help text.
- [x] [Review][Patch] Improve duplicate-target-within-run handling [src/sdlc/adopt/passes/symlink_offer.py:185-194] — two `detected[]` entries resolving to the same slot are deduped only AFTER `create_relative_symlink` (`recorded_targets` checked at `:194`, post-creation), and the second is reported via the CONFLICT message that misframes it as a pre-existing-file conflict. Pre-filter before creation and/or distinguish the duplicate-within-run message. (Overlaps Story 3.6.)

**Deferred (pre-existing / out-of-scope — see deferred-work.md):**

- [x] [Review][Defer→RESOLVED 2026-06-04] Stale global `sdlc` shadowed the project CLI → 70 environment test failures [environment / e2e+parity harness] — NOT caused by 3.3. Was: full suite 70 failed / 3039 passed; ALL 70 were e2e/parity/trust-hooks/latency tests shelling out via bare `uv run sdlc` from a temp cwd, hitting a stale `uv tool`-installed `sdlc-framework v1.3.0` (`~/.local/bin/sdlc`, old package `sdlc_framework`) emitting `sdlc: unknown command: --json`. **RESOLVED + ROOT-FIXED:** durable harness chore shipped (separate from 3.3) — `tests/_clihelper.py` pins `uv run --project <repo-root>` for the 11 `uv run sdlc` e2e files and injects `venv_path_env()` for the 2 parity/latency files (whose `pre_tool_use.py` shells out to bare `["sdlc","hook-check"]` by design); `conftest.py` puts `tests/` on `sys.path`. **Proven durable:** full suite **3118 passed / 4 skipped** with NO `sdlc` on PATH and NO uv tool installed (was 70 failed). Coverage gate `--cov-fail-under=87` green. (`sdlc` tool reinstalled only so the live Claude-Code `pre_tool_use` hook keeps enforcing — tests no longer depend on it.)
- [x] [Review][Defer] Concurrent multi-process adopt races on the manifest [src/sdlc/adopt/passes/symlink_offer.py:176-206] — deferred, out-of-scope. Unlocked read→append→write (last-writer-wins). Multi-process adopt unsupported today; `io_primitives` documents a caller-managed `.lock`.
- [x] [Review][Defer] AC8 residual gate elements — coverage now CONFIRMED. After the env fix the FULL suite is green (**3118 passed / 4 skipped**) and the `--cov-fail-under=87` coverage gate passed. Still open (minor): `mkdocs build --strict` not run in this review; TDD-first ordering via `git log --reverse` cannot be verified because the whole story is still an uncommitted working-tree blob (ordering established at commit time per CONTRIBUTING.md §2).

**Dismissed as noise (5):** below-threshold silent when `warn=None` (CLI always wires `warn`; AC3 MET — auditor F7) · `journal_path` optional footgun (driver always passes it; intentional no-op default — F7) · `_ACTOR="cli"` in core (adopt run originates at the CLI entrypoint; defensible provenance) · `threshold==0` auto-accepts confidence 0 (internally consistent `<` gate; operator opt-in via config; spec mandates no floor) · two-call journal seq alloc (CONFORMS, in-spec, mirrors `driver._append_event`, single-process — auditor F11).

**Applied 2026-06-04 (all 8 patches, user ratified both decisions as option (a)):**
- `_symlink.py`: new shared `is_target_under_root` predicate (P2) + `assert_target_under_root` now delegates to it; new `SymlinkOutcome.SOURCE_MISSING` + source-existence guard (P1).
- `symlink_offer.py`: journal-before-manifest, single post-loop manifest write, single reused timestamp (D1); fail-soft `_create_for_record` helper — unsafe target / missing source / conflict / OSError warn-and-skip, never abort the pass (D2); core target re-validation (P2); duplicate-target pre-filter before FS touch (P7); corrupt-manifest now warns instead of silently swallowing (P3).
- `cli/adopt.py`: `_is_safe_relative_target` delegates to the shared predicate (P2); dropped now-unused `os` import.
- `cli/main.py`: `init --non-interactive` without `--adopt` → typed `ERR_USER_INPUT`; flag now `hidden=True` (P6).
- Tests: +7 in `test_symlink_offer.py` (source-missing, shared-timestamp, escape fail-soft continue, OSError fail-soft, duplicate-once, corrupt-manifest-warn), +1 driver kwarg-forwarding (P4), +1 cli non-interactive-without-adopt guard.
- Gate (verified): ruff ✅ · ruff format ✅ · mypy --strict 153 files ✅ · wire-format snapshots 7/7 ✅ · `check_module_boundaries` exit 0 (adopt→cli still zero imports) ✅ · 1072 adopt/cli/contracts/integration tests passed.
