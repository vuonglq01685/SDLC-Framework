# Story 3.2: Pass 1 — Detection (Filesystem Scan + Content Heuristics + Git History)

**Status:** review

**Epic:** 3 — Brownfield Adopt Mode (`sdlc init --adopt`)
**Layer:** 2 (`docs/sprints/epic-3-dag.md` §3 — first serial-spine pass; max-parallel 1)
**Worktree:** `epic-3/3-2-pass1-detection` (owner: Dana, DAG §5)
**Critical Path:** 3.1 → **3.2** → 3.3 → 3.4 → 3.6 → 3.7 (DAG §4 — 3.2 is the first spine pass; 3.3 consumes the `detected[]` this story produces; any slip here stalls 3.3/3.4/3.5/3.6/3.7)
**Depends on (satisfied):** Story 3.1 (`done`, merged to `main`) — froze the `src/sdlc/adopt/` layout, the `detect_existing` seam (`adopt/passes/detection.py:16`), and the `AdoptReport`/`DetectedArtifact` wire-format contract (`contracts/adopt_report.py`, 6th locked, snapshot committed).
**Parallel sibling (same layer):** none — Layer 2 is a single story (the adopt spine is serial; DAG §3/§6).

---

## Story

As an **engineer implementing Pass 1 of the three-pass adopt driver**,
I want **`detect_existing(root)` to surface a brownfield repo's pre-existing SDLC artifacts via a filesystem name-pattern scan, content-pattern heuristics, and a git-history recency signal — classifying each into a frozen `kind` taxonomy with an integer-percent `confidence` and a canonical `suggested_target` — and to ship a multi-fixture golden corpus as a CI gate**,
so that **Pass 2 (Story 3.3) has a trustworthy, deterministic `detected[]` to offer symlinks for, and a maintainer (Khanh persona) running `sdlc init --adopt` on an existing repo sees their PRDs, architecture docs, runbooks, CI workflows, and build files recognized without a single source file being touched (FR2 Pass 1, NFR-REL-6)**.

---

## Acceptance Criteria

> **Scope note — read first.** Story 3.2 fills the **Pass 1 detection heuristics ONLY**, behind the
> `detect_existing(root) -> list[DetectedArtifact]` seam that Story 3.1 froze (`adopt/passes/detection.py:16`,
> currently `return []`). It does **NOT** create symlinks (Pass 2 = Story 3.3), does **NOT** stamp the audit
> log (Pass 3 = Story 3.4), does **NOT** own the auto-accept threshold (Story 3.3; `epics.md:1841`), and does
> **NOT** write the full source-untouched property/mutation gate (Story 3.7). Detection is **read-only**: it
> produces an in-memory `list[DetectedArtifact]`; the driver (`adopt/driver.py:181`) writes
> `adopt-report.json` under `.claude/` — Pass 1 itself writes nothing. Four material decisions —
> **D1** (`suggested_target` mapping), **D2** (git-history signal sourcing), **D3** (content-heuristic
> signatures), **D4** (`legacy_code_globs` exclusion) — are resolved at T0 in "Decisions Needed".
>
> **Verified-ground-truth correction (binding) — `confidence` is an integer percent, NOT a float.**
> Epics.md:1803 and :1826 say `confidence ∈ [0.0, 1.0]` ("0.92"). **The FROZEN contract supersedes this:**
> `DetectedArtifact.confidence: int = Field(ge=0, le=100)` (`contracts/adopt_report.py:46`, Story 3.1 D2(a)).
> Architecture.md:494,515 forbid Python floats in `.claude/state/*` JSON, and `StrictModel` (`strict=True`)
> rejects a `0.92` float at validation. **Pass 1 MUST emit `92`, not `0.92`.** The epics prose is stale; the
> contract is the law. Do not attempt to widen the contract — that would force an ADR-024 snapshot-regen
> ceremony this story does not perform.
>
> **Verified-ground-truth correction (binding) — no contract or snapshot change.** `DetectedArtifact` +
> `AdoptReport` are frozen by Story 3.1 (snapshot at `tests/contract_snapshots/v1/adopt_report.json`). Story
> 3.2 only **populates** the `detected[]` tuple — populating data is NOT in the ADR-024 mutation taxonomy
> (`ADR-024` §1; field add/remove/rename/type-change only), so there is **NO**
> `scripts/freeze_wireformat_snapshots.py --write` run and **NO** ADR-024/028 amendment in this story (the
> `adopt_pass_started/completed/failed` journal kinds Pass 1 emits were already added by Story 3.1, ADR-028).

1. **Filesystem name-pattern scan finds candidate artifacts (AC: FR2 Pass 1, epics.md:1797).** `detect_existing`
   walks `root` and collects candidates by name/path pattern — at minimum `README.md`, `docs/**/*.md`,
   `.github/workflows/*.yml` (and `.yaml`), `pom.xml`, `Dockerfile`, plus build files (`pyproject.toml`,
   `package.json`, `go.mod`, `build.gradle`) and runbook patterns (per the **D3** signature table). The scan is
   **read-only** (no writes), skips `.claude/`, `.git/`, and (per **D4**) optionally any path matching
   `legacy_code_globs`. The matched set is the input to classification.

2. **Content heuristics elevate or demote candidates (AC: epics.md:1798).** For matched candidates, content
   inspection adjusts the `kind` + `confidence`: a `docs/architecture-2024.md` containing **C4 diagrams or "ADR"
   headings** is classified `architecture` with **high confidence** (the one doc-blessed worked example,
   epics.md:1798). The full per-`kind` content-signature table is ratified in **D3** and frozen by the golden
   corpus (AC6) — whatever signatures are chosen become the contract the corpus pins.

3. **Git-history recency adds signal (AC: epics.md:1799).** Artifacts touched in the **last 90 days** score
   higher than abandoned files. Because `adopt/` has **no git grant** and **must not import `cli/`** (the only
   git surface), the recency signal is sourced per **D2** — recommended: the `cli/adopt.py` layer (which holds
   the git grant via `_paths`) reads `git log` and **injects** a per-path last-touched map down into
   `detect_existing(root, *, git_signal=...)`, mirroring Story 3.8's `legacy_code_globs` dependency-injection
   pattern (`cli/break_.py:220-298`). The signal **degrades gracefully**: on a non-git repo, git error, or
   absent signal, detection still completes using filesystem `mtime` as a fallback floor and/or no recency
   boost (house pattern: `cli/_paths.py:34-36`, `hooks/runner.py:112-115`).

4. **Each candidate is classified into the frozen taxonomy (AC: epics.md:1803-1804, contract).** Every
   detected artifact is assigned:
   - `kind ∈ {prd, architecture, research, runbook, ci-workflow, build-file, dockerfile, readme, unknown}`
     (the frozen `ArtifactKind` Literal, `contracts/adopt_report.py:28-38`);
   - `confidence: int` in `[0,100]` (integer percent — see the binding correction above; `adopt_report.py:46`);
   - `suggested_target: str` — the canonical SDLC path per the **D1** mapping table (e.g.
     `docs/architecture-2024.md → 02-Architecture/02-System/ARCHITECTURE.md`, epics.md:1804;
     `docs/PRD.md → 01-Requirement/01-PRODUCT.md`, prd.md:120). Kinds with **no** canonical SDLC slot
     (per D1: runbook/ci-workflow/build-file/dockerfile/readme) emit `suggested_target=""` (detect-only;
     `suggested_target` is a non-optional `str`, so empty-string — not null — encodes "no target", and Pass 2
     skips offering a symlink for it).

5. **Greenfield-disguised-as-brownfield → empty result + message (AC: epics.md:1806-1809).** On a repo with
   **no** SDLC-shaped artifacts, detection completes with `detected: []` (empty tuple in the report), and the
   user is told the **exact** string **`no candidate artifacts detected; will treat as greenfield`**
   (epics.md:1809, verbatim). The message is emitted at the CLI layer (`cli/adopt.py`, where `report.detected`
   length is already inspected, `adopt.py:81,89`) — `detect_existing` returning `[]` is the trigger.

6. **Multi-fixture golden corpus is a CI gate (AC: epics.md:1811-1814).** Author `tests/fixtures/brownfield/`
   as a **shared asset** (DAG §7 risk register — "3.2 and 3.7 consume the same corpus") covering the
   **union** of both fixture lists (epics.md:1811 ∪ epic-3-dag.md:148,183): **Java/Maven, Node/npm,
   Python/pyproject, Go module, monorepo-with-submodules, pre-existing-symlinks** — plus the **greenfield-
   disguised** fixture for AC5. For each fixture, an expected golden (canonical `detected[]` JSON) is matched
   against actual `detect_existing` output; **all fixtures pass = CI gate**. The git-history signal is stubbed
   deterministic in the corpus tests (no live `git log`), so goldens are reproducible. Reuse the established
   `assert_goldens` / `_compare_one_golden` + `--update-goldens` regeneration ceremony
   (`tests/e2e/cli/conftest.py:282-391`; canonical JSON via `_golden_assert.py:24-40`).

7. **Detection is read-only — source tree untouched (AC: NFR-REL-6 posture).** `detect_existing` performs
   **zero writes** to any path (it returns an in-memory list); the only on-disk write in the Pass 1 flow is the
   driver's `adopt-report.json` under `.claude/` (already pre-guarded by `assert_path_under_claude`,
   `adopt/invariant.py:24`). A 3.2 test asserts that running detection across the corpus produces no filesystem
   mutation outside `.claude/` (`git status --porcelain` clean for source paths). The exhaustive property +
   mutation gate (≥95% kill) over this corpus is **Story 3.7's** deliverable, not 3.2's (epics.md:1939,
   epic-3-dag.md:114-117); 3.2 guarantees read-only-by-construction and hands the corpus forward.

8. **Quality gate + process discipline (AC: §1/§2/§5).** Quality gate green per CONTRIBUTING §1 (ruff
   format/check, `mypy --strict src/`, `pytest`, coverage ≥90% [operational floor `--cov-fail-under=87`;
   ≥90 tracked as `EPIC-2B-DEBT-COVERAGE-90-FLOOR`], pre-commit incl. `check_module_boundaries` +
   `check_subprocess_allowlist`, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` 6/6 byte-stable
   — the contract is unchanged). TDD-first (§2): Pass 1 is a **public-API + behavioral surface**, so the first
   commit is the failing detection + corpus tests, visible RED in `git log --reverse`, then green. Material
   decisions surfaced as **D1/D2/D3/D4** option-labels (§5). No `src/` files staged on review commits (§4.4).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the detection unit tests + the (initially empty)
> golden corpus harness. They go RED against the `return []` stub, then green as the heuristics land. The
> corpus fixtures are authored before the goldens are frozen (`--update-goldens` writes the goldens only once
> the implementation is trusted).

- [x] **(AC8, §5) T0 — Resolve D1/D2/D3/D4.** Lock the `suggested_target` mapping table (D1), the git-history
  signal sourcing (D2), the content-heuristic signature table (D3), and the `legacy_code_globs` exclusion
  posture (D4) in the PR Change Log **before** writing code. D2 determines whether `detect_existing` gains a
  `git_signal` parameter (and whether `run_adopt`/`_run_pass`/`cli/adopt.py` are threaded) or stays a pure
  fs+content scan (defer git to 3.7). D3's chosen signatures are frozen by the golden corpus (AC6), so settle
  them first.
- [x] **(AC1, AC2, AC4, §2) Write the failing detection unit tests FIRST, commit before implementation:**
  - name-pattern scan finds `README.md`/`docs/**/*.md`/`.github/workflows/*.yml`/`pom.xml`/`Dockerfile`/build
    files (AC1);
  - content heuristic: a `docs/*.md` with C4/`ADR` headings → `kind=architecture`, high `confidence` (AC2);
  - classification emits a valid `DetectedArtifact` with `confidence: int [0,100]` (assert an `int`, and assert
    a `0.92`-style float is never produced) + the D1 `suggested_target` per kind (AC4);
  - `detected: []` + greenfield message trigger on an artifact-free tree (AC5).
  Verify RED against the `return []` stub. **Place in `tests/unit/adopt/test_detection.py`** (sibling of
  `test_driver.py`; reuse its `adopt_root` tmp_path fixture pattern, `test_driver.py:34-40`;
  `pytestmark = pytest.mark.unit`; the win32 module-skip in `test_driver.py:20-21` is NOT needed for pure
  filesystem-scan tests).
- [x] **(AC6, §2) Author the brownfield fixture corpus + failing golden harness:** create
  `tests/fixtures/brownfield/{java-maven-service, node-npm, python-pyproject, go-module, monorepo-submodules,
  preexisting-symlinks, greenfield-disguised}/` with realistic minimal trees (a `pom.xml`+`src/`+`README.md`+
  `docs/` for Java, etc.; the greenfield fixture has NO SDLC-shaped artifacts). Add the golden-corpus test
  (`tests/unit/adopt/test_detection_corpus.py` or under `tests/e2e/`) that runs `detect_existing` per fixture
  with a **deterministic stubbed git signal** and compares canonical `detected[]` JSON to
  `<fixture>/goldens/detection.json` via a `_compare_one_golden`-style helper with `--update-goldens`. Verify
  RED (goldens absent / output empty).
- [x] **(AC3, D2) Implement the git-history signal per D2.** If D2=(b) DI: add a small read-only git-log reader
  in the `cli/` layer (it already shells `git` via `_paths.py:27`; reuse the subprocess-allowlist entry or add
  one for the new callsite + `check_subprocess_allowlist` green), compute a `{path: days_since_last_touch}`
  map, and thread it: `run_adopt(*, root, journal_path, git_signal=...)` → `_run_pass(1, root, detected,
  git_signal)` → `detect_existing(root, *, git_signal=...)`. Add the `os.stat().st_mtime` fallback inside
  `detect_existing` for the no-signal path. If D2=(d) defer: skip the git wiring entirely and note the deferral
  (pre-sanctioned by `adopt/invariant.py:10-12`). **No `adopt → git` boundary grant** is added either way
  (avoids contradicting the documented 3.7 deferral).
- [x] **(AC1–AC5) Implement `detect_existing` heuristics** in `adopt/passes/detection.py`: name-pattern scan →
  content-signature classification (D3 table) → confidence scoring (int percent; recency boost from the git
  signal) → `suggested_target` mapping (D1 table) → return `list[DetectedArtifact]`. Skip `.claude/`/`.git/`
  and (D4) `legacy_code_globs`. Keep the module ≤400 LOC (NFR-MAINT-3 / architecture.md cap); extract a
  `_classify.py` / `_scan.py` helper under `adopt/passes/` if it grows.
- [x] **(AC5) Emit the greenfield message** at `cli/adopt.py`: when `report.detected` is empty, echo
  `no candidate artifacts detected; will treat as greenfield` (verbatim) before/instead of the detected-count
  line (`adopt.py:88-90`). Keep the `--json` envelope behavior intact (`detected_count: 0`).
- [x] **(AC6) Freeze the goldens + flip the corpus test green:** run `pytest ... --update-goldens` once the
  implementation is trusted; verify the corpus test passes byte-stable without `--update-goldens`; cite the
  golden regeneration in the PR Change Log (ADR-027 ceremony).
- [x] **(AC7) Source-untouched assertion:** add a test asserting `git status --porcelain` reports no changes
  outside `.claude/` after a full corpus detection run (3.2-scoped smoke; the exhaustive 3.7 gate stays out of
  scope).
- [x] **(AC8, §1) Full quality gate to green** — ruff format/check + `mypy --strict` + pytest + coverage
  (operational ≥87) + pre-commit (incl. `check_module_boundaries`, `check_subprocess_allowlist`) +
  `mkdocs build --strict` + `freeze_wireformat_snapshots --check` 6/6 (contract unchanged → byte-stable).
- [x] **(§3) Worktree + merge discipline.** Branch `epic-3/3-2-pass1-detection` off merged-`main` (post-3.1);
  TDD-first commit ordering visible in `git log --reverse` (test→feat). 3.2 freezes the `detected[]` shape +
  `suggested_target` mapping that 3.3 consumes — keep it byte-stable before 3.3 branches (DAG §4 spine-slippage
  risk). 3.2 touches `adopt/passes/detection.py` + `cli/adopt.py` (+ maybe `cli/_paths.py`/a new git helper) +
  `tests/` + `tests/fixtures/brownfield/`; no shared edit with any other open story (Layer 2 is solo).
- [ ] **(§4) Chunked review** review-A (correctness / AC↔tests / heuristic-table fidelity) → review-B
  (boundary: no `adopt→cli/git` import, git-signal DI clean, read-only invariant, subprocess-allowlist) →
  review-C (golden corpus completeness + `suggested_target` mapping + greenfield message exactness + naming);
  no skipping. Review commits carry `[fresh-context-review]` and stage no `src/` files (§4.4).
  **→ Runs in the `code-review` workflow once dev-story sets status=review (not a dev-phase deliverable).**

---

## Dev Notes

### What 3.1 froze — the seam 3.2 fills

Story 3.1 (`done`, merged `main`) shipped the orchestrator skeleton and the frozen contracts. 3.2 fills exactly
one seam:

```python
# src/sdlc/adopt/passes/detection.py:16 (CURRENT — Story 3.1 stub)
def detect_existing(root: Path) -> list[DetectedArtifact]:
    """Return artifacts detected under `root` (Story 3.2 heuristics; 3.1 returns []).“""
    return []
```

The driver calls it at `adopt/driver.py:117-125` (`_run_pass(1, ...)` → `detection.detect_existing(root)` →
the returned list flows into `_build_report` → `adopt-report.json`). The CLI entry is `cli/adopt.py`
(`run_adopt(*, ctx)`; `root` resolved at `:56`; driver invoked at `:64`; detected-count echoed at `:81,89`).
**Pass 1 returning a populated list is the entire behavioral delta** — the orchestration, journaling
(`adopt_pass_started/completed`, ADR-028), report-writing, and resume cursor are already implemented and tested
by 3.1. Do not re-litigate them.

### The `DetectedArtifact` contract — FROZEN, populate-only (no snapshot regen)

`contracts/adopt_report.py:41-47`:
```python
class DetectedArtifact(StrictModel):
    path: str
    kind: ArtifactKind                       # Literal[prd|architecture|research|runbook|
                                             #   ci-workflow|build-file|dockerfile|readme|unknown] (:28-38)
    confidence: int = Field(ge=0, le=100)    # INTEGER PERCENT — not float (D2(a), :9-12)
    suggested_target: str                    # non-optional; "" encodes "no canonical target"
```
- `StrictModel` (`strict=True, extra="forbid", frozen=True`, `contracts/_strict_model.py`) rejects a float
  `0.92`, a bool, an extra key, and a `kind` outside the 9-value Literal at validation. 3.2's detection must
  build valid `DetectedArtifact`s — write a test that a float confidence is never produced.
- **No contract edit, no snapshot regen, no ADR amendment.** Populating `detected[]` is not in the ADR-024
  mutation taxonomy. `freeze_wireformat_snapshots --check` stays 6/6 byte-stable. (Confirmed: the snapshot at
  `tests/contract_snapshots/v1/adopt_report.json` already marks `detected`/`passes_completed` optional with
  `default_factory=tuple`, accepted as forward-compatible in 3.1's review — 3.2 just fills the tuple.)

### `suggested_target` mapping — RESOLVE AS D1 (only 2 kinds are doc-blessed)

The canonical user-project SDLC layout is **architecture.md:465-481** (corroborated epics.md:178/AR-LAYOUT,
prd.md:201-202):
```
01-Requirement/01-PRODUCT.md          02-Architecture/02-System/ARCHITECTURE.md
01-Requirement/02-Research/           02-Architecture/01-UX/
03-Implementation/tasks/...
```
Only **two** mappings are explicitly blessed in the docs:
| kind | suggested_target | source |
|---|---|---|
| `prd` | `01-Requirement/01-PRODUCT.md` | prd.md:120 (`docs/PRD.md → …`) |
| `architecture` | `02-Architecture/02-System/ARCHITECTURE.md` | epics.md:1804, prd.md:290 |
| `research` | `01-Requirement/02-Research/` (dir) | inferred — only research slot (architecture.md:467, FR7 prd.md:747) |
| `runbook` / `ci-workflow` / `build-file` / `dockerfile` / `readme` | **no canonical SDLC slot** | GAP — see D1 |
| `unknown` | `""` | by definition |

The five "no-slot" kinds are a **GAP** the docs never resolve → **D1**. Recommended: map `prd`/`architecture`/
`research` as above; emit `suggested_target=""` for the rest (detect-only — they surface in the report so the
maintainer sees them, but Pass 2 offers no symlink). `src/sdlc/cli/_brownfield.py:45` has a `_canonical_path`
but it is a **glob-path normalizer** (backslash/`./`/trailing-slash cleanup), **NOT** a kind→target mapper —
3.2 authors its own mapping helper; do not reuse `_brownfield._canonical_path` for targets.

### Git-history recency signal — RESOLVE AS D2 (genuine boundary gap)

epics.md:1799 needs "touched in the last 90 days → higher score." The architecture spec is **thin**: there is
**no** git-history reader anywhere in `src/sdlc/` (verified — the only two git callsites are
`cli/_paths.py:27` `git rev-parse --show-toplevel` and `hooks/runner.py:103` `git config user.email`; no
`git log`, no `--since`, no last-modified reader exists). And the boundary blocks the obvious path:

- The enforced `adopt` ModuleSpec (`scripts/module_boundary_table.py:116-135`) grants
  `depends_on = {errors, contracts, ids, concurrency, state, journal, signoff, config}`,
  `forbidden_from = {engine, dispatcher, runtime}`. **No `git`, no `cli`.** `adopt → cli` is forbidden by the
  dependency-direction invariant ("Only `cli/` imports `adopt/`", architecture.md:1084; `adopt/__init__.py:8`).
- `adopt/invariant.py:10-12` already records the deferral in writing: *"Running git porcelain here would
  require a module-boundary-table grant for git that does not exist yet (Story 3.7)."*

**Options (D2):**
- **(b) Dependency injection — RECOMMENDED.** `cli/adopt.py` is the sole caller of the driver and already holds
  the git grant (`_paths.py:27`). Read `git log --format=%cI` per candidate path **in the `cli` layer**,
  compute a `{path: days_since}` map, and thread it down through `run_adopt(..., git_signal=...)` →
  `_run_pass(1, ..., git_signal)` → `detect_existing(root, *, git_signal=...)`. **This is a direct mirror of
  Story 3.8's pattern** (`cli/break_.py:220-298` reads `legacy_code_globs` from config and injects it into the
  pure boundary-respecting classifier `classify_tdd_strategy(touches, legacy_code_globs)`,
  `cli/_brownfield.py:29`). Keeps `detect_existing` pure + trivially testable (inject a fake map; no git in unit
  tests — mirrors `test_driver.py:91` monkeypatching the seam). The new git read needs a
  `check_subprocess_allowlist` entry (`scripts/check_subprocess_allowlist.py:37-52`).
- **(c) `mtime` fallback** — layer on top of (b): `os.stat().st_mtime` inside `detect_existing` as the recency
  floor when the injected signal is absent / not-a-git-repo (house "degrade when git absent" pattern,
  `_paths.py:34-36`). mtime is unreliable across checkouts → a floor, not a replacement. (Note: `st_mtime` is
  currently used only for journal file-size checks, never as a content-age signal — net-new but stdlib-only,
  boundary-free.)
- **(d) Defer the git signal to Story 3.7** — ship 3.2 with fs-scan + content heuristics only; the git recency
  clause moves to 3.7 (which already owns the git-grant deferral). Lowest risk; content heuristics dominate
  scoring without it. Clean retreat if review pushes back on the new git read.
- **(a) Add an `adopt → git` boundary grant + `cli/git.py`** — **NOT recommended.** Directly contradicts the
  documented 3.7 deferral (`invariant.py:10-12`), needs a boundary-table edit (4-signoff ceremony, CONTRIBUTING
  §7/§8) + a new subprocess callsite (security-reviewer trigger), and widens `adopt`'s blast radius.

Recommend **(b)+(c)** with **(d)** as the documented fallback. Whichever wins, **no `adopt → git` grant** is added.

### Content-heuristic signatures — RESOLVE AS D3 (under-specified, frozen by the corpus)

The docs specify exactly **one** content signature: C4 diagrams / `ADR` headings → `architecture`, high
confidence (epics.md:1798). Every other signature (PRD markers, runbook patterns, README detection,
research-doc markers) is the dev's design. Because the golden corpus (AC6) hard-freezes whatever is chosen,
**carry the full signature table explicitly in the PR Change Log as D3** so reviewers ratify it before the
goldens lock. Suggested starting signatures (ratify in D3): `# Product Requirements`/`PRD`/`User Stories` →
`prd`; `## Runbook`/`Runbook`/`On-call`/`Incident` → `runbook`; `.github/workflows/*.yml` → `ci-workflow`;
`pom.xml`/`pyproject.toml`/`package.json`/`go.mod`/`build.gradle` → `build-file`; `Dockerfile` → `dockerfile`;
`README.md` → `readme`; recognizable-but-unmapped → `unknown`. Name-pattern gives a base confidence; content
match elevates; git recency (D2) boosts; no content signal demotes toward `unknown`.

### `legacy_code_globs` exclusion — RESOLVE AS D4 (optional enhancement)

`config/project.py:29` — `legacy_code_globs: tuple[str, ...] = Field(default_factory=tuple)` (empty default;
`load_project_config`, `project.py:33`; frozen `ProjectConfig`). Story 3.8 uses it to mark **legacy source
code** needing characterization tests (`cli/break_.py:224` reads it, injects into `classify_tdd_strategy`). For
3.2, a path matching `legacy_code_globs` is by definition **source code, not an SDLC artifact** → use it as an
**exclusion/demotion** signal so detection never misclassifies `src/legacy/**` as an artifact. **No AC in 3.2
mentions it** (epics.md:1787-1814) → this is an *enhancement*, not a required AC; **D4** decides whether to
wire it now (via the same DI seam as D2 — read in `cli/adopt.py`, inject down, reuse the `cli/_brownfield.py`
segment-aware `**` matcher) or defer. Recommend wiring it as a cheap exclusion if D2=(b) is chosen (the DI seam
already exists); else defer.

### Read-only invariant + NFR-REL-6 (3.2 posture)

- **NFR-REL-6** (prd.md:841, epics.md:109): "Adopt-mode never modifies source code under any condition (hard
  invariant)." Architecture.md:194/223 strengthen the *test* to `git status --porcelain` empty + tree-hash
  equality (not `git diff` — "diff misses mtime, mode, xattr, symlink target").
- **3.2 scope:** `detect_existing` performs **zero writes** — it returns an in-memory list. The only Pass 1
  write is the driver's `adopt-report.json` under `.claude/` (pre-guarded, `invariant.py:24`). 3.2 ships a
  read-only smoke (AC7); the exhaustive 5+-fixture property + mutation (≥95% kill) gate is **Story 3.7**
  (epics.md:1939, epic-3-dag.md:114-117). Do not weaken the standard or pull 3.7's gate forward.

### Brownfield fixture corpus — shared asset (3.2 authors, 3.7 consumes)

`tests/fixtures/brownfield/` **does not exist yet** — 3.2 creates it. The two fixture lists differ; author the
**union** (epic-3-dag.md:183 mandates one shared corpus for 3.2 + 3.7):

| Fixture | From | Purpose |
|---|---|---|
| `java-maven-service` | epics.md:1795,1811 | `pom.xml` + `src/` + `README.md` + `docs/architecture-*.md` (the Khanh persona, prd.md:290) |
| `node-npm` | epics.md:1811 | `package.json` + `README.md` |
| `python-pyproject` | epics.md:1811 | `pyproject.toml` + `docs/` |
| `go-module` | epics.md:1811 | `go.mod` |
| `monorepo-submodules` | epics.md:1811, epic-3-dag.md:148 | nested packages + git submodules |
| `preexisting-symlinks` | epic-3-dag.md:148,183 | repo with existing symlinks (3.7 needs it; harmless for 3.2) |
| `greenfield-disguised` | epics.md:1806-1809 | NO SDLC artifacts → `detected: []` + greenfield message (AC5) |

3.7 needs "5+ fixtures" (epic-3-dag.md:114,148); the union (6 brownfield + 1 greenfield) satisfies both stories.
Keep each fixture **minimal but realistic** (golden diffs must stay legible).

### Golden-corpus CI gate — reuse the established pattern

The repo has a mature golden harness; reuse it rather than inventing one:
- `assert_goldens` / `_compare_one_golden` + `--update-goldens` regeneration ceremony
  (`tests/e2e/cli/conftest.py:282-391`) — collects all mismatches into one `AssertionError`, emits unified
  diffs, writes goldens under `--update-goldens`, cites the regen in the PR Change Log (ADR-027).
- Canonical JSON for golden bytes: `_canon_json` (`tests/e2e/pipeline/_golden_assert.py:24-40` —
  `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"), indent=2)` + `\n`). This is the
  **test-tier** helper (lives in `tests/`, importable by test code) — distinct from the **production** inline
  canonicalizer at `adopt/driver.py:64-72` (used by the driver to write the report; `detect_existing` itself
  writes no JSON, so 3.2 needs no production canonicalizer — it returns `list[DetectedArtifact]`).
- Stub the git signal deterministically in corpus tests so goldens are reproducible across machines.

### Reuse, do not reinvent

| Need | Reuse | Cite |
|---|---|---|
| Build `DetectedArtifact` | the frozen contract (StrictModel; int confidence) | `contracts/adopt_report.py:41-47` |
| Timestamp / "now" for recency math | `ids.clock.now_rfc3339_utc_ms` (adopt already depends on `ids`) | `adopt/driver.py:28`, `ids/clock.py:13` |
| Git read (D2=b) | the `cli` layer's existing git-subprocess posture | `cli/_paths.py:26-36` |
| DI pattern (git + legacy globs) | Story 3.8's read-in-cli-inject-into-pure-core | `cli/break_.py:220-298`, `cli/_brownfield.py:29` |
| `**` glob matcher (D4) | the segment-aware matcher | `cli/_brownfield.py:8-12` |
| Golden harness | `assert_goldens` + `--update-goldens` | `tests/e2e/cli/conftest.py:282-391` |
| Test fixture pattern | `adopt_root` tmp_path + `pytestmark = pytest.mark.unit` | `tests/unit/adopt/test_driver.py:28,34-40` |
| Greenfield-message emission | `report.detected` length already inspected at CLI | `cli/adopt.py:81,88-90` |

**Code-style constraints binding on `adopt/passes/detection.py`** (architecture.md:483-494): `from __future__
import annotations`; no top-level cross-module imports in `cli/` bodies (defer-import, <200ms cold start,
architecture.md:488 — `cli/adopt.py` already does this); no `print()` outside `cli/output.py`; **no floats in
state/journal** (architecture.md:494 — confidence is int); module ≤400 LOC (split to `_scan.py`/`_classify.py`
under `adopt/passes/` if needed).

### Previous-story intelligence

- **Story 3.1** (`done`): froze the `adopt/` layout + `detect_existing` seam + `AdoptReport` contract; resolved
  D1=(a) `passes/` layout, D2=(a) `confidence: int` percent, D3=(a) pass-level resume. Its code-review
  deferred CR3.1-W1…W5 (`deferred-work.md`) — notably the symlink-following gap in `assert_path_under_claude`
  (→ 3.7) and the boundary erratum (`depends_on` 5→8). **The 3.1 boundary erratum is why `contracts`/`ids`/
  `concurrency` are available to `adopt/`** — 3.2 relies on `contracts` (DetectedArtifact) + `ids` (clock).
- **Story 3.8** (`done`, sibling Layer-1): established the **DI pattern 3.2 mirrors** — `cli` reads config
  (`legacy_code_globs`) and injects it into a pure boundary-respecting core; the LLM/core never does the impure
  read. 3.2's git-signal + legacy-glob handling follow this exact shape (`cli/break_.py`, `cli/_brownfield.py`).
- **Epic 1 substrate** (all on `main`): `config/` (`legacy_code_globs`), `ids/clock`, `concurrency`
  (atomic write — used by the driver, not detection), `contracts/` (StrictModel + the 6 wire-format contracts).

### Citation-drift note (verified)

epics.md:1820 cites "PRD §275" for the adopt passes, but prd.md:275/§281 are actually **Journey 2 (Lam's
auto-loop)**. The canonical adopt / FR2 prose is **Journey 3 (prd.md:284-296)** — esp. **prd.md:290** for the
Pass 1 behavioral spec ("runs Pass 1: detection. It finds README.md, docs/architecture-2024.md, pom.xml,
Dockerfile, three GitHub Actions workflows, two runbooks. It writes .claude/state/adopt-report.json. It does
not touch a single source file.") and **prd.md:739** for FR2. Cite prd.md:290/:739, not :275.

### Sibling / worktree coordination (DAG §3/§5/§6, CONTRIBUTING §3)

- **Layer 2 = {3.2} alone** — solo story, no parallel sibling, no shared-file contention. The adopt spine is
  serial (DAG §6: peak width 2 lives in Layers 1 & 5, not here).
- 3.2 **freezes the `detected[]` shape + `suggested_target` mapping** that Pass 2 (3.3) consumes → keep it
  byte-stable before 3.3 branches (DAG §4: spine slippage stalls 3.3/3.4/3.5/3.6/3.7 simultaneously).
- Files 3.2 touches: `src/sdlc/adopt/passes/detection.py` (+ maybe `_scan.py`/`_classify.py`),
  `src/sdlc/cli/adopt.py` (greenfield message + git-signal DI), possibly `src/sdlc/cli/_paths.py` or a new
  `cli`-side git-log helper + `scripts/check_subprocess_allowlist.py` (if D2=b), `tests/unit/adopt/test_*.py`,
  `tests/fixtures/brownfield/**`. **No `contracts/` or snapshot edit** (contract frozen).

### Testing standards

pytest; AAA structure; coverage ≥90% (§1 target; operational ≥87 floor). TDD-first (§2): detection unit tests +
golden corpus are the failing-first commit, RED in `git log --reverse`. Golden corpus is the AC6 CI gate (all
fixtures pass). A read-only smoke (AC7) asserts no source mutation. Unit tests inject a fake git signal — no
live `git log` in tests. `pytestmark = pytest.mark.unit` (`rules/python/testing.md`).

---

## Decisions Needed

- **D1 — `suggested_target` mapping table.** Only `prd` → `01-Requirement/01-PRODUCT.md` (prd.md:120) and
  `architecture` → `02-Architecture/02-System/ARCHITECTURE.md` (epics.md:1804) are doc-blessed; `research` →
  `01-Requirement/02-Research/` is inferable; **runbook/ci-workflow/build-file/dockerfile/readme have no
  canonical SDLC slot** (architecture.md:465-481).
  - **(a) Map the 3 mappable kinds; emit `suggested_target=""` for the other 5 (detect-only).** They appear in
    the report (maintainer sees them) but Pass 2 offers no symlink. Minimal, honest, no invented paths.
    **(Recommended — `suggested_target` is a non-optional `str`; "" is the "no target" encoding, and inventing
    SDLC slots for build files/Dockerfiles would create orphaned symlink offers in 3.3.)**
  - **(b) Invent canonical slots for all 9 kinds** (e.g. a `03-Implementation/runbooks/` dir). Larger surface;
    introduces paths no other story/doc references; risks 3.3/3.4 churn. Defer unless a reviewer insists.
- **D2 — Git-history recency signal sourcing (the 90-day clause, epics.md:1799).** `adopt/` has no git grant
  and cannot import `cli/`; no git-log reader exists anywhere.
  - **(a) Dependency injection + mtime fallback** — `cli/adopt.py` reads `git log` (it holds the grant via
    `_paths.py:27`) and injects `{path: days_since}` into `detect_existing(root, *, git_signal=...)` via
    `run_adopt`/`_run_pass`; `os.stat().st_mtime` is the fallback floor on non-git repos. Mirrors Story 3.8's
    DI pattern (`cli/break_.py:220-298`); keeps `detect_existing` pure; adds a `check_subprocess_allowlist`
    entry; **no `adopt → git` grant**. **(Recommended.)**
  - **(b) Defer the git signal to Story 3.7** — ship fs-scan + content heuristics only; the recency clause
    moves to 3.7 (which already owns the git-grant deferral, `invariant.py:10-12`). Lowest risk; content
    heuristics dominate scoring. Clean retreat if review rejects the new git read.
  - **(c) New `cli/git.py` + `adopt → git` boundary grant** — contradicts the documented 3.7 deferral, needs a
    4-signoff boundary-table edit + new subprocess callsite. **Not recommended.**
- **D3 — Content-heuristic signature table (frozen by the golden corpus).** Only the C4/`ADR` → `architecture`
  signature is documented (epics.md:1798); all others are dev design.
  - **(a) Ratify an explicit per-kind signature table in the PR Change Log before freezing goldens** (PRD/
    runbook/readme/ci-workflow/build-file/dockerfile signatures as sketched in Dev Notes). Reviewers approve the
    table in review-A; the corpus pins it. **(Recommended — the golden corpus hard-freezes whatever ships, so
    the signatures must be a reviewed decision, not an implementation accident.)**
  - **(b) Implement ad-hoc signatures, document post-hoc.** Faster but the corpus locks unreviewed heuristics;
    rework if review disagrees. Not recommended.
- **D4 — Consume `legacy_code_globs` as an artifact-exclusion signal?** No 3.2 AC requires it
  (epics.md:1787-1814); it marks **source code** (Story 3.8 semantics) that should not be detected as an SDLC
  artifact.
  - **(a) Wire it as a cheap exclusion via the D2 DI seam** (read in `cli/adopt.py`, inject down, reuse the
    `cli/_brownfield.py:8-12` `**` matcher) **iff D2=(a) is chosen** (the seam already exists). Prevents
    misclassifying `src/legacy/**` as artifacts. **(Recommended when D2=(a).)**
  - **(b) Defer** — rely on the `.git/`/`.claude/` skip + name patterns to avoid source; revisit if the corpus
    shows false positives. Acceptable, lower scope.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- RED: `pytest tests/unit/adopt/test_detection.py tests/unit/adopt/test_detection_corpus.py` → 40 failed, 10 passed against the `return []` stub (commit `eac5e70`).
- GREEN: full suite `3067 passed, 4 skipped` (Windows/OS-only skips); coverage **88.52% ≥ 87%** (commit `117d700`).
- Gates: ruff format/check ✅, `mypy --strict src/` ✅ (151 files), `check_module_boundaries` ✅, `check_subprocess_allowlist` ✅, `freeze_wireformat_snapshots --check` 6/6 byte-stable ✅, `mkdocs build --strict` ✅, full pre-commit ✅.

### Completion Notes List

- **Pass 1 detection seam filled** (`adopt/passes/detection.py`, `return []` → real heuristics): `os.walk` scan pruning `.claude/`/`.git/`, name-pattern + content-signature classification, int-percent confidence, D1 `suggested_target`, git-recency boost, D4 legacy-glob exclusion → `list[DetectedArtifact]`. Read-only by construction (NFR-REL-6).
- **Classification extracted to `adopt/passes/_classify.py`** (229 LOC) to keep `detection.py` focused (99 LOC); both well under the 400-LOC cap.
- **Boundary respected:** `adopt/` gained NO git grant and does NOT import `cli/`. The 90-day recency signal (AC3) is computed in `cli/_git_recency.py` (new) and dependency-injected as `git_signal` through `cli/adopt.py → driver.run_adopt → _run_pass(1) → detect_existing` — a direct mirror of Story 3.8's `legacy_code_globs` DI. The `**`-aware glob matcher is a LOCAL copy in `_classify.py` (house pattern: one matcher per layer).
- **D2 refinement (binding):** the Change Log's "mtime fallback" was implemented as **graceful no-boost** when the git signal is absent (AC3's "and/or no recency boost" license) rather than an `os.stat().st_mtime` floor — this keeps `detect_existing` pure (no `time.time()` in the core) and the golden corpus deterministic (corpus stubs `git_signal={}`). No `os.stat` content-age read was added.
- **Contract untouched (populate-only):** `DetectedArtifact`/`AdoptReport` unchanged; `freeze_wireformat_snapshots --check` stays 6/6 byte-stable. No ADR-024 ceremony, no snapshot regen — confirmed not in the mutation taxonomy.
- **AC5 greenfield message** emitted verbatim at `cli/adopt.py` (`no candidate artifacts detected; will treat as greenfield`); `--json` envelope behavior preserved (`detected_count: 0`).
- **AC7 read-only** proven two ways: per-fixture no-mutation assertion in the corpus test, and a full-adopt `git status --porcelain` clean-outside-`.claude/` integration test over a REAL git repo (also exercises the live git-recency path end-to-end). The exhaustive property+mutation gate remains Story 3.7.
- **Scope note — `preexisting-symlinks` fixture:** authored as a plain brownfield repo (README + `docs/architecture.md` + `pom.xml`). Real committed symlinks were intentionally NOT added — they belong to Story 3.7's symlink-untouched property testing and would create cross-platform golden instability. The corpus slot is reserved per the union.

### File List

**Source (new):**
- `src/sdlc/adopt/passes/_classify.py` — D3 signature table, D1 target mapping, recency boost, local `**` matcher.
- `src/sdlc/cli/_git_recency.py` — git-log recency reader + pure `parse_git_log`; graceful `{}` on non-git/error.

**Source (modified):**
- `src/sdlc/adopt/passes/detection.py` — implemented `detect_existing(root, *, git_signal, legacy_code_globs)`.
- `src/sdlc/adopt/driver.py` — thread `git_signal` + `legacy_code_globs` into Pass 1 (`run_adopt`, `_run_pass`).
- `src/sdlc/cli/adopt.py` — compute git signal + read `legacy_code_globs`, inject down; emit greenfield message (AC5).
- `scripts/check_subprocess_allowlist.py` — allowlist `("src/sdlc/cli/_git_recency.py", "git")`.

**Tests (new):**
- `tests/unit/adopt/test_detection.py` — AC1–AC5 + D2/D4 + read-only smoke (parametrized).
- `tests/unit/adopt/test_detection_corpus.py` — 7-fixture golden corpus + per-fixture read-only assertion (AC6/AC7).
- `tests/unit/cli/test_git_recency.py` — `parse_git_log` recency math + non-git graceful degradation.
- `tests/fixtures/brownfield/{java-maven-service,node-npm,python-pyproject,go-module,monorepo-submodules,preexisting-symlinks,greenfield-disguised}/**` — corpus trees + frozen `goldens/detection.json`.

**Tests (modified):**
- `tests/unit/cli/test_adopt.py` — AC5 greenfield + brownfield-count + report-populated tests; `_boom` mock kwargs.
- `tests/unit/adopt/test_driver.py` — `detect_existing` stub signature (`lambda root, **_kw`).
- `tests/integration/test_adopt_mode_invariant.py` — AC7 brownfield-artifacts porcelain test (real git repo).
- `tests/conftest.py` — hoisted `--update-goldens` registration (shared by unit + e2e tiers).
- `tests/e2e/conftest.py` — removed the now-duplicate `pytest_addoption`.

**Config (modified):**
- `pyproject.toml` — ruff `extend-exclude += tests/fixtures/` (sample trees, not product Python).

## Change Log

- 2026-06-03: **GREEN + golden freeze** (dev-story). Implemented `detect_existing` heuristics + the
  `cli`-layer git-recency DI + AC5 greenfield message. Froze the AC6 golden corpus via
  `pytest tests/unit/adopt/test_detection_corpus.py --update-goldens` (ADR-027 regeneration ceremony) —
  7 `goldens/detection.json` files committed; corpus verified byte-stable without `--update-goldens`.
  Full quality gate green (3067 passed / coverage 88.52% / snapshots 6/6 / mkdocs strict). Status:
  in-progress → review. **D2 refinement:** mtime fallback realized as graceful no-boost (AC3 license)
  to keep the core pure + corpus deterministic; no `os.stat` content-age read added.



- 2026-06-03: **T0 — D1/D2/D3/D4 decisions locked** (dev-story). Branch: `epic-3/3-2-pass1-detection`.

  **D1 — `suggested_target` mapping — CHOICE (a): 3 mappable kinds; `""` for 6 detect-only.**
  | kind | suggested_target |
  |---|---|
  | `prd` | `01-Requirement/01-PRODUCT.md` |
  | `architecture` | `02-Architecture/02-System/ARCHITECTURE.md` |
  | `research` | `01-Requirement/02-Research/` |
  | `runbook`, `ci-workflow`, `build-file`, `dockerfile`, `readme`, `unknown` | `""` |
  Rationale: only 3 mappings are doc-blessed (prd.md:120, epics.md:1804, architecture.md:467); inventing slots for build files/Dockerfiles would create orphaned symlink offers in Pass 2 (3.3).

  **D2 — git-history recency — CHOICE (a): DI + mtime fallback.**
  `cli/adopt.py` reads `git log --format=%cI -- <path>` per candidate (reusing `cli/_paths.py` subprocess posture), computes `{rel_path: days_since}`, passes as `git_signal` kwarg through: `_run_adopt_driver(root, journal_path, git_signal=...) → driver.run_adopt(git_signal=...) → _run_pass(1, ..., git_signal) → detection.detect_existing(root, *, git_signal=...)`. `os.stat().st_mtime` inside `detect_existing` as recency floor on non-git repos. No `adopt → git` boundary grant. New subprocess allowlist entry: `("src/sdlc/cli/adopt.py", "git")`.

  **D3 — content-heuristic signature table — CHOICE (a): explicit per-kind table ratified here.**
  | Name pattern(s) | Content signatures (any match) | kind | Base conf | Content-boost conf |
  |---|---|---|---|---|
  | `README.md`, `README.rst` | — | `readme` | 90 | — |
  | `.github/workflows/*.{yml,yaml}` | — | `ci-workflow` | 95 | — |
  | `Dockerfile`, `Dockerfile.*`, `*.dockerfile` | — | `dockerfile` | 95 | — |
  | `pom.xml`, `pyproject.toml`, `package.json`, `go.mod`, `build.gradle` | — | `build-file` | 95 | — |
  | `docs/**/*.md`, `*.md` (non-README) | `C4`, `ADR`, `Architecture Decision`, `architecture`, `component diagram`, `system design` | `architecture` | 55 | 85 |
  | `docs/**/*.md`, `*.md` (non-README) | `Product Requirements`, `PRD`, `User Stories`, `User Story`, `As a`, `Epics` | `prd` | 55 | 80 |
  | `docs/**/*.md`, `*.md` (non-README) | `Research`, `Investigation`, `Findings`, `Analysis` | `research` | 50 | 75 |
  | `docs/**/*.md`, `*.md` (non-README) | `Runbook`, `On-call`, `Oncall`, `Incident`, `Escalation`, `SLA` | `runbook` | 50 | 75 |
  | any `.md` not classified above, any unmatched candidate | — | `unknown` | 40 | — |
  Git recency boost (D2): +5 if artifact touched within last 90 days. Content-boost supersedes base; git boost is additive (capped at 100). Golden corpus freezes this table — no post-hoc changes without `--update-goldens`.

  **D4 — `legacy_code_globs` exclusion — CHOICE (a): wire via D2 DI seam.**
  `cli/adopt.py` reads `legacy_code_globs` from `project.yaml` (same call as Story 3.8: `load_project_config(root / DEFAULT_PROJECT_YAML).legacy_code_globs`) and injects alongside `git_signal`. `detect_existing(root, *, git_signal=..., legacy_code_globs=...)` skips any path matching the globs (source code, not SDLC artifact). Reuses `_brownfield._match_path_glob` for `**`-aware matching.

  Status: ready-for-dev → in-progress.

- 2026-06-03: Story drafted (create-story) — Layer-2 first serial-spine pass of Epic 3. Authored against
  verified ground truth on `main` (3.1 merged: `detect_existing` seam + frozen `DetectedArtifact` contract).
  Binding corrections surfaced in-story: (1) `confidence` is `int [0,100]`, not the stale epics float `[0,1]`;
  (2) no contract/snapshot/ADR change (populate-only); (3) git-history signal has no legal seam in the adopt
  boundary → D2 dependency-injection (mirrors Story 3.8); (4) only 2 kinds have doc-blessed `suggested_target`
  → D1; (5) content signatures under-specified → D3 (frozen by golden corpus); (6) `legacy_code_globs`
  exclusion is an optional enhancement → D4; (7) PRD citation drift (adopt prose is Journey 3 / prd.md:290,739,
  not §275). Status: ready-for-dev. D1/D2/D3/D4 await user confirmation at dev-story T0.
