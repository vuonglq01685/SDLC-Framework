# Story 1.15: Engine Scanner Skeleton (Idempotent, Side-Effect-Free)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer building the engine's read path first,
I want `engine/scanner.py` exposing a pure `scan(project_root) -> State` function that walks the canonical filesystem layout (`01-Requirement/04-Epics/`, `01-Requirement/05-Stories/`, `03-Implementation/tasks/`) and returns a deterministic `State` projection with no I/O writes,
so that `sdlc scan` (Story 1.17) has a complete underlying engine, NFR-PERF-1 (`scan` < 2 s on 200 stories / 1000 tasks) is benchmarked as a CI regression gate, and the abstraction-adequacy CI pipeline (Story 1.14) can replace its scan-stub with the real call when the substrate is upgraded (FR3, FR35-adjacent, NFR-PERF-1, NFR-REL-5, Decision A4 + B5, Architecture §117, §388, §815, §1133, §1407).

## Acceptance Criteria

**AC1 — `scan(project_root)` is a pure read of the filesystem layout, returns a `State` value, and never writes to disk (epic AC block 1)**

**Given** Stories 1.10 (atomic write) and 1.11 (journal append) on disk:

- `src/sdlc/state/atomic.py` exports `write_state_atomic_sync` (Story 1.10) — NOT called by the scanner
- `src/sdlc/journal/writer.py` exports `append_sync` (Story 1.11) — NOT called by the scanner
- `src/sdlc/state/model.py` exports `State` with `schema_version: int = 1`, `next_monotonic_seq: int = 0`, `epics: dict[str, Any]` (Story 1.10) — extended in AC3 of THIS story
- `src/sdlc/ids/__init__.py` exports `parse_epic_id`, `parse_story_id`, `parse_task_id`, `EPIC_ID_REGEX`, `STORY_ID_REGEX`, `TASK_ID_REGEX` (Story 1.6)

**When** the file `src/sdlc/engine/scanner.py` exposes a single public function `scan(project_root: Path) -> State`,

**Then** the function obeys the following contract:

1. **Pure**: zero filesystem writes, zero journal appends, zero subprocess calls, zero stdout/stderr writes (no `print` per Architecture §489), zero network I/O, zero `os.environ` writes, zero `state.json` writes (Story 1.17's `cli/scan.py` wraps `scan` with `write_state_atomic_sync` + `journal.append_sync`; the scanner itself MUST stay write-free so that `tests/integration/test_abstraction_adequacy.py` can call it without touching the journal/state layer). Reads from `project_root` are allowed.
2. **Total**: returns a `State` for every reachable input (empty project, partial project, fully-populated project). Returning early via `raise` is allowed only on programmer errors (`project_root` not absolute, points at a file rather than a directory) — not on missing layout directories. A project that lacks `01-Requirement/04-Epics/` is a valid empty project, not an error.
3. **Deterministic**: two calls back-to-back on the same on-disk state MUST produce `State` values that are `model_dump(mode="json")`-byte-equal. The byte-equality assertion is canonical:
   ```python
   import json
   def _state_bytes(s: State) -> bytes:
       return json.dumps(s.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
   assert _state_bytes(scan(p)) == _state_bytes(scan(p))
   ```
4. **Empty-project shape**: `scan(<absolute-path-to-empty-dir>)` returns `State(schema_version=1, next_monotonic_seq=0, phase=1, epics={}, stories={}, tasks={})`. This matches the canonical "fresh project" stub used by Story 1.14's `tests/integration/test_abstraction_adequacy.py` (line documented as "scan step is a no-op stub for Epic 1; Story 1.15 will replace this") and unblocks the goldens regen described in Story 1.14 AC4.
5. **POSIX + Windows portable**: scanner does NOT depend on `fcntl`, `O_APPEND`, parent-dir fsync, or any `state.atomic` / `journal.writer` POSIX-only paths. Pure `pathlib.Path.iterdir` + `Path.read_text` walk. The scanner runs on `windows-latest` as well as `ubuntu-latest` / `macos-latest` (Architecture §573 carves POSIX-only at the WRITE layer; the read layer is portable).

**And** the function signature is exactly `def scan(project_root: Path) -> State` (sync, no async — scanning is a fast read, no event-loop coupling). `from __future__ import annotations` is the first non-comment line of `engine/scanner.py` (project convention; `from __future__` keeps the annotation literal-only at runtime — see `tool.ruff.lint.isort.required-imports` in `pyproject.toml:85`).

**And** the scanner raises `StateError` (with `details={"path": ..., "reason": ...}`) when:

- `project_root` is not absolute (`raise StateError("scan requires an absolute project_root path", details={"path": str(project_root), "reason": "not_absolute"})`).
- `project_root` exists but is a regular file (`details={"reason": "not_a_directory"}`).
- A discovered epic/story/task JSON file fails `json.loads` or `parse_*_id` validation (`details={"reason": "malformed_artifact", "file": <relative-path>}`). Use `from sdlc.errors import StateError`.

**And** all other error paths (missing optional directories, empty subdirectories, non-`.json` files in the artifact dirs) are NOT raises — they are graceful zero-yield walks. Story 1.20's `rebuild-state` will introduce stricter recovery semantics; v1 scanner is permissive.

**AC2 — Filesystem walk extracts epics, stories, and tasks in canonical naming sort order (epic AC block 2)**

**Given** a `project_root` with the canonical SDLC layout:

```
<project_root>/
├── 01-Requirement/
│   ├── 04-Epics/
│   │   ├── EPIC-alpha.json           # canonical id parsed via ids/
│   │   ├── EPIC-beta.json
│   │   └── EPIC-gamma.json
│   └── 05-Stories/
│       ├── EPIC-alpha/
│       │   ├── EPIC-alpha-S01-bootstrap.json
│       │   └── EPIC-alpha-S02-validate.json
│       └── EPIC-beta/
│           └── EPIC-beta-S01-replan.json
└── 03-Implementation/
    └── tasks/
        ├── EPIC-alpha-S01-bootstrap/
        │   ├── EPIC-alpha-S01-bootstrap-T01-init.json
        │   └── EPIC-alpha-S01-bootstrap-T02-lockfile.json
        └── EPIC-alpha-S02-validate/
            └── EPIC-alpha-S02-validate-T01-rules.json
```

**When** `scan(project_root)` runs,

**Then** the returned `State` has:

1. `state.epics` is a `dict[str, dict[str, Any]]` keyed by canonical epic id (`"EPIC-alpha"`, `"EPIC-beta"`, `"EPIC-gamma"`). Insertion order MUST follow the canonical naming sort (Python's default lexicographic sort on the kebab-case slug — `"alpha" < "beta" < "gamma"`). The order is observable because `json.dumps(..., sort_keys=True)` re-sorts on serialization, BUT the in-memory `State.epics` dict's insertion order is also canonicalized (use `dict(sorted(...))`) to keep the iteration order — and any downstream `journal.append` payload — deterministic before serialization.
2. Each epic value is the parsed JSON content of `EPIC-<slug>.json` (via `json.loads(path.read_text(encoding="utf-8"))`) — no model coercion in v1 (epic schema is owned by Story 2A.11 / 2A.12). The value is `dict[str, Any]`. Required keys are NOT enforced by the scanner; that's the artifact-write hook's job (Story 2A.4).
3. `state.stories` is a `dict[str, dict[str, Any]]` keyed by canonical story id (`"EPIC-alpha-S01-bootstrap"`, `"EPIC-alpha-S02-validate"`, `"EPIC-beta-S01-replan"`), insertion order canonical-sorted. Each value is the parsed JSON of `<STORY-id>.json`.
4. `state.tasks` is a `dict[str, dict[str, Any]]` keyed by canonical task id (`"EPIC-alpha-S01-bootstrap-T01-init"`, etc.), insertion order canonical-sorted. Each value is the parsed JSON of `<TASK-id>.json`.
5. Filename validation: every JSON file under `04-Epics/` MUST have a stem matching `EPIC_ID_REGEX` (`^EPIC-[a-z0-9]+(?:-[a-z0-9]+)*$`); under `05-Stories/<EPIC-id>/` matching `STORY_ID_REGEX`; under `tasks/<STORY-id>/` matching `TASK_ID_REGEX`. Files that don't match the regex are SKIPPED (logged via `structlog` at WARN — but this v1 substrate uses Python's stdlib `logging.getLogger(__name__).warning(...)` since `engine/logging.py` lands in Story 2A.x; the import is local to scanner.py and uses the canonical `_logger = logging.getLogger(__name__)` pattern from `journal/writer.py:34`). NEVER raise on a foreign filename — that would couple scanner correctness to filesystem hygiene the user can't control during adopt-mode.
6. The scanner uses `sdlc.ids.parse_epic_id`, `sdlc.ids.parse_story_id`, and `sdlc.ids.parse_task_id` to validate the filename stems; the boundary table extension (AC5 below) authorizes this engine→ids dependency.
7. Cross-link integrity is NOT enforced in v1: a story file under `05-Stories/EPIC-foo/` whose parent directory's epic doesn't exist in `04-Epics/` is still loaded. Story 1.20 (rebuild-state) introduces orphan detection; v1 scanner is purely additive.

**And** scanner ignores hidden files and directories (any path component starting with `.` — e.g. `.gitkeep`, `.DS_Store`). Symlinks are followed only if `path.is_file()` (default `pathlib` behavior); broken symlinks are skipped silently (logged at INFO).

**And** the scan does NOT read or modify `<project_root>/.claude/state/state.json`, `<project_root>/.claude/state/journal.log`, or any file under `.claude/`. The scanner is a projection of the *artifact tree*, not a re-projection of the journal (Story 1.12 owns journal-based projection; Story 1.15 owns artifact-based projection; Story 1.20 owns reconciliation).

**AC3 — State model schema extension: add `phase`, `stories`, `tasks` fields with safe defaults (epic AC block 3)**

**Given** the current `src/sdlc/state/model.py` (Story 1.10):

```python
class State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)
    schema_version: int = 1
    next_monotonic_seq: int = 0
    epics: dict[str, Any] = Field(default_factory=dict)
```

**When** Story 1.15 extends the model,

**Then** the new shape is:

```python
class State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)
    schema_version: int = 1                                  # unchanged — additive, no v2
    next_monotonic_seq: int = 0                              # unchanged
    phase: int = 1                                           # NEW: SDLC phase 1 (Requirement) / 2 (Architecture) / 3 (Implementation); default 1 for fresh projects
    epics: dict[str, Any] = Field(default_factory=dict)      # unchanged
    stories: dict[str, Any] = Field(default_factory=dict)    # NEW: story records keyed by canonical story id
    tasks: dict[str, Any] = Field(default_factory=dict)      # NEW: task records keyed by canonical task id
```

The schema_version stays at `1` because the change is purely additive: existing on-disk `state.json` files written under Story 1.10's minimal model will continue to validate (missing optional fields use the field defaults). `extra="forbid"` rejects EXTRA fields, not MISSING ones — pydantic v2 confirms this in the `Config.extra` docs.

**And** `pyproject.toml [tool.coverage.run] omit` does NOT change for `state/model.py` (it's not omitted today; coverage stays in scope on Linux CI per `pyproject.toml:185-203`).

**And** the migration story is named in ADR-018: "no migration required because schema_version is unchanged; old state.json files validate against the extended model thanks to pydantic v2 default-supplying behavior. Migration becomes mandatory only when a NON-DEFAULTABLE field is added or a field type tightens (e.g. `int` → `Literal[1, 2, 3]`)."

**And** Story 1.14's golden state.json file (`tests/fixtures/abstraction_adequacy/expected_state.json`) WILL drift because the canonical JSON now includes `"phase": 1, "stories": {}, "tasks": {}` keys at top level. Story 1.15's Task 5 explicitly regenerates these goldens via the `_REGENERATE_GOLDENS=True` toggle Story 1.14 documented; the regen-history line in `tests/fixtures/abstraction_adequacy/README.md` is updated to record "Story 1.15: state model gained phase/stories/tasks fields, regenerated goldens." If Story 1.14 has not yet landed on disk at story-implement time, this step is a no-op (the goldens don't exist; Story 1.14's dev will pick up the extended State model directly). Task 1 pre-flight branches on Story 1.14's presence.

**AC4 — Performance: scan completes in < 2 s on 200 stories / 1000 tasks; warm cache in < 100 ms; CI regression gate via pytest-benchmark (epic AC block 4)**

**Given** a benchmark fixture function `_build_perf_corpus(root: Path) -> None` that scaffolds:

- 4 epic JSON files under `01-Requirement/04-Epics/EPIC-perf-{a,b,c,d}.json`
- 200 story JSON files distributed under `01-Requirement/05-Stories/EPIC-perf-<x>/EPIC-perf-<x>-S<NN>-perf.json` — 50 stories per epic × 4 epics, with `NN` in `01..50` (NEVER above 99 — `STORY_ID_REGEX` from `sdlc/ids/parsers.py:14` enforces exactly 2 digits in the `-S<NN>-` segment, so `S100+` would fail the regex and be silently skipped)
- 1000 task JSON files distributed under `03-Implementation/tasks/<STORY-id>/<STORY-id>-T<MM>-perf.json` — 5 tasks per story × 200 stories = 1000 total. `MM` in `01..05`.

Each artifact's content is a small canonical JSON object: `{"id": "<canonical-id>", "title": "perf"}` (~50 bytes). The fixture is built at runtime in `tmp_path` (no committed corpus) so the benchmark is reproducible from a clean checkout in < 30 s.

**When** `pytest -m benchmark tests/benchmark/test_scan_perf.py` runs,

**Then** the benchmark file declares two test cases backed by `pytest-benchmark`:

1. `test_scan_perf_cold[on_200_stories_1000_tasks]`: builds the corpus, invokes `benchmark(scan, corpus_root)`. Asserts via `pytest-benchmark`'s built-in stats that mean wall time is < 2.0 seconds on the CI worker (`ubuntu-latest`). Use `benchmark.pedantic(scan, args=(corpus_root,), iterations=1, rounds=5, warmup_rounds=0)` to disable warmup so the "cold" measurement is a true first-call cost.
2. `test_scan_perf_warm[on_200_stories_1000_tasks]`: same corpus; calls `scan(corpus_root)` once outside the benchmark to warm the OS file cache, then `benchmark.pedantic(scan, args=(corpus_root,), iterations=10, rounds=5, warmup_rounds=2)`. Asserts mean wall time is < 100 ms (0.1 s).

Both budgets MUST hold on the project's existing `quality-gates` CI matrix cell (`ubuntu-latest`, python 3.12). Don't gate on `windows-latest` for v1 — Windows file-cache and `pathlib` behavior differ enough that the budget is tuned for Linux. Document in ADR-018 that Windows is observed (no skip), but the strict numeric assertion fires only on `ubuntu-latest`.

**And** the benchmark file uses `pytestmark = pytest.mark.benchmark` (the `benchmark` marker is already declared in `pyproject.toml:181`).

**And** assertions are wired via `pytest-benchmark`'s native gate API:

```python
def test_scan_perf_cold(benchmark, tmp_path: Path) -> None:
    corpus = tmp_path / "perf_corpus"
    corpus.mkdir()
    _build_perf_corpus(corpus)
    benchmark.pedantic(scan, args=(corpus,), iterations=1, rounds=5, warmup_rounds=0)
    # pytest-benchmark records stats; manual assertion ensures the budget gate is in the test source, not just the report.
    assert benchmark.stats.stats.mean < 2.0, (
        f"scan() cold ran in {benchmark.stats.stats.mean:.3f}s on 200/1000 corpus; budget is 2.0s (NFR-PERF-1)"
    )
```

(Manual `benchmark.stats.stats.mean` access is the pytest-benchmark canonical post-run assertion; `pytest --benchmark-compare-fail=mean:5%` flag is the suite-level CI gate documented in pytest-benchmark's docs but is supplementary, not the primary assertion.)

**And** `pytest-benchmark>=4.0.0,<6` is added to `[dependency-groups] dev` in `pyproject.toml`. (The `benchmark` marker pre-exists at `pyproject.toml:181` from Story 1.2; only the dev dep is new.)

**And** the existing CI workflow `.github/workflows/ci.yml` is extended to include a `benchmarks` job that runs `uv run pytest -m benchmark --benchmark-only --no-cov` on `ubuntu-latest` python 3.12 only (matrix cell single-pinned for stability). Job name: `benchmarks`. Failure of `benchmarks` is a hard CI fail (not informational). Place the new job after `chaos-tests` to keep the YAML readable; mirror the matrix-skip pattern (`os: ubuntu-latest`, `python-version: "3.12"`). Use `--no-cov` because pytest-benchmark stats overhead would skew coverage measurements; coverage is enforced by `quality-gates` separately.

**And** the benchmark sub-corpus is NOT committed: `tests/benchmark/conftest.py` (or an inline helper in the test file) builds the corpus in `tmp_path` per test run. The fixture file IS committed; the corpus tree is not. Document in `tests/benchmark/README.md`: "All benchmark corpora are scaffolded at runtime via tmp_path. NOT a committed fixture tree — regen is automatic per test."

**AC5 — `engine/` module wiring + boundary table updates (epic AC block 5)**

**Given** `src/sdlc/engine/` does not exist on disk before Story 1.15,

**When** Story 1.15 lands,

**Then**:

1. `src/sdlc/engine/__init__.py` is created with:
   ```python
   from __future__ import annotations
   from sdlc.engine.scanner import scan
   __all__ = ("scan",)
   ```
   Naked `__all__` re-exports the public API surface; future engine submodules (`auto_loop`, `stop_triggers`, etc., owned by Stories 4.x) extend this tuple.
2. `src/sdlc/engine/scanner.py` is created with the implementation per AC1+AC2.
3. `scripts/check_module_boundaries.py` is updated: `MODULE_DEPS["engine"].depends_on` gains `"ids"`. Concretely the `frozenset({...})` literal at `scripts/check_module_boundaries.py:99-113` adds `"ids"`. Rationale: the scanner needs `parse_epic_id`/`parse_story_id`/`parse_task_id` to validate filename stems; without the dep, the boundary linter (`boundary-validator` pre-commit hook) would FAIL the scanner's import. ADR-018 records this widening.
4. The boundary linter MUST self-pass after the change: `uv run python scripts/check_module_boundaries.py src/sdlc/ tests/` exits 0. The linter's own self-tests at `tests/integration/test_module_boundary_self.py` (or wherever the AC2/AC3 self-discipline tests live per Story 1.4) must continue to pass — adding `ids` to engine.depends_on widens the allow-set; it does not narrow forbidden_from.
5. `engine/scanner.py` LOC is ≤ 300 lines (project soft cap is 400 per ruff `tool.ruff.lint.pylint`-adjacent guidance + Architecture §137). If the implementation exceeds 250 LOC, factor out helpers into `engine/_scanner_helpers.py` (private module, leading underscore) — same pattern Story 1.11 used (`journal/_canonical.py`, `journal/_seq.py`). The boundary linter doesn't distinguish public/private submodules; both fall under `engine`.
6. `engine/scanner.py` uses no `print()` (Architecture §489 — no print in `engine/`); uses `_logger = logging.getLogger(__name__)` for warnings about skipped files.
7. `engine/scanner.py` uses no `time.time()` for ordering (Architecture §490). The scanner doesn't compute timestamps at all; ordering is filename-derived.
8. `engine/scanner.py` uses no `os.environ[...]` direct access (Architecture §491) — scanner takes `project_root: Path` as input; environment never enters.
9. `engine/scanner.py` uses no `subprocess.run` (Architecture §492) — pure read.
10. `engine/scanner.py` uses no `open()` for state/journal writes (Architecture §493) — N/A; scanner is read-only.
11. `engine/scanner.py` uses no floats in any computed value (Architecture §494) — N/A; scanner doesn't compute numeric state.

**And** `docs/decisions/ADR-018-engine-scanner-skeleton.md` is authored documenting:
- The pure-function contract (no I/O writes from scanner; CLI Story 1.17 wires the writes).
- The schema extension (phase / stories / tasks fields, additive, schema_version unchanged).
- The engine→ids boundary widening.
- Why goldens regen for Story 1.14's `expected_state.json` is expected and named.
- The pytest-benchmark CI regression gate as the canonical NFR-PERF-1 enforcer.

## Tasks / Subtasks

- [ ] **Task 1: Pre-flight verification of dependencies and environment (AC: all)**
  - [ ] Verify Story 1.10 deliverables on disk: `src/sdlc/state/atomic.py` exists and exports `write_state_atomic_sync` (already known done — sprint-status `1-10: done`); smoke `uv run python -c "from sdlc.state import State, write_state_atomic_sync; print('ok')"`.
  - [ ] Verify Story 1.11 deliverables on disk: `src/sdlc/journal/__init__.py` exports `append_sync` and `iter_entries`; smoke `uv run python -c "from sdlc.journal import append_sync, iter_entries; print('ok')"`. **If 1.11 is still in `review`** (per sprint-status snapshot 2026-05-08), the scanner does NOT consume `append_sync` from inside `engine/scanner.py`; it consumes it ONLY at `cli/scan.py` (Story 1.17). Story 1.15 has NO hard import dep on `journal/writer.py`, so 1.11 review status is not blocking.
  - [ ] Verify Story 1.6 (`ids/`) deliverables on disk: `src/sdlc/ids/__init__.py` exports `parse_epic_id`, `parse_story_id`, `parse_task_id`. Smoke `uv run python -c "from sdlc.ids import parse_epic_id, parse_story_id, parse_task_id; print('ok')"`. Hard dep — must succeed.
  - [ ] Verify boundary-linter location: `scripts/check_module_boundaries.py` exists with the `MODULE_DEPS` table at lines 29-144. Confirm the engine row is at lines 98-118 with `depends_on=frozenset({...})`. The Task 5 edit adds `"ids"` to that frozenset.
  - [ ] Determine whether Story 1.14 has landed on disk: `ls tests/fixtures/abstraction_adequacy/expected_state.json`. If present, Task 5 includes the goldens-regen step; if absent, Task 5 skips that step (Story 1.14 dev later will produce goldens against the extended `State` model directly).
  - [ ] Verify ADR numbering: existing ADRs are 001-014 per `docs/decisions/index.md`. ADRs 015 (Story 1.12), 016 (Story 1.13), 017 (Story 1.14) are in flight (their stories are `ready-for-dev`). Story 1.15 (this story) authors **ADR-018**. If 1.12/1.13/1.14 ADRs land first, 018 is still next-available; if any of those haven't shipped at story-implement time, just take the next free number after 014 + however many landed.
  - [ ] Verify `pyproject.toml [tool.pytest.ini_options].markers` contains `benchmark` at line 181 (already added by Story 1.2). No new marker.
  - [ ] Verify CI matrix in `.github/workflows/ci.yml`: existing jobs are `quality-gates` (matrix `os × python-version`) and `chaos-tests` (single cell). Locate the `chaos-tests` job (around lines 60-90 per the architecture/sprint-status timeline) — the new `benchmarks` job slots in immediately after.
  - [ ] Confirm engine module directory is absent: `test -d src/sdlc/engine && echo "EXISTS — abort, Story 1.15 expects fresh creation" || echo "ok, fresh"`. If `src/sdlc/engine/` already exists (from a half-merged earlier story), HALT and reconcile manually before proceeding — this story owns the initial population.
  - [ ] Confirm pyproject.toml dev deps exclude `pytest-benchmark` today: `grep -F "pytest-benchmark" pyproject.toml` returns no match. Task 6 adds it.

- [ ] **Task 2: Extend `state/model.py` with `phase`, `stories`, `tasks` fields (AC: #3)**
  - [ ] Open `src/sdlc/state/model.py`. Add three new fields to the `State` class, ordered after `next_monotonic_seq` and before/after `epics` per the canonical SDLC layout: `phase` (project phase) sits BEFORE `epics` because phase is project-scope; `stories` and `tasks` sit AFTER `epics` because they're refinements of epic-scope. Final field order:
    ```python
    schema_version: int = 1
    next_monotonic_seq: int = 0
    phase: int = 1
    epics: dict[str, Any] = Field(default_factory=dict)
    stories: dict[str, Any] = Field(default_factory=dict)
    tasks: dict[str, Any] = Field(default_factory=dict)
    ```
    Pydantic v2 serializes fields in declaration order by default; `model_dump(mode="json")` then `json.dumps(..., sort_keys=True)` re-orders alphabetically — so the on-disk byte form is alphabetical regardless of declaration order. Declaration order is for code readability.
  - [ ] Update the docstring of `State` to: "`State` v1 projection (Architecture §520, §841). Skeleton schema for substrate stories 1.10-1.20; further field additions remain backward-compatible until schema_version bumps in Story 1.21."
  - [ ] Confirm `model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)` is unchanged. `frozen=True` ensures the State is hashable (prereq for hash-chain protocol Story 1.20); `extra="forbid"` rejects EXTRA keys but TOLERATES MISSING ones (pydantic v2 default-supplying behavior).
  - [ ] Add a unit test at `tests/unit/state/test_state_model.py` (extend if already present from Story 1.10):
    - `test_state_default_construction_has_skeleton_fields`: `s = State()`; assert `s.phase == 1`, `s.stories == {}`, `s.tasks == {}`. Already-present fields (`schema_version`, `next_monotonic_seq`, `epics`) keep their existing assertions.
    - `test_state_old_state_json_validates_against_extended_model`: build a dict matching the Story-1.10-era shape `{"schema_version": 1, "next_monotonic_seq": 0, "epics": {}}`, call `State.model_validate(d)`, assert success and that `phase == 1`, `stories == {}`, `tasks == {}` (defaults supplied).
    - `test_state_canonical_json_includes_new_fields`: `s = State()`; canonical bytes via `json.dumps(s.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")`; assert `b'"phase":1' in bytes_` and `b'"stories":{}' in bytes_` and `b'"tasks":{}' in bytes_`.
  - [ ] Verify the existing tests that lock the State shape from Story 1.10 still pass (they shouldn't break — additive only). The chaos test at `tests/chaos/test_atomic_write_kill_points.py` writes a `State()` and re-reads; check it tolerates the extra default fields by reading its assertions.

- [ ] **Task 3: Implement `engine/scanner.py` (AC: #1, #2)**
  - [ ] Create `src/sdlc/engine/__init__.py` with the public API re-export per AC5.1.
  - [ ] Create `src/sdlc/engine/scanner.py`. Top-of-file order:
    1. Module docstring (one paragraph): "Filesystem scanner for SDLC projects (FR3, Architecture §815, §1133, Decision A4 + B5). Pure read-only function: walks `01-Requirement/04-Epics/`, `01-Requirement/05-Stories/`, `03-Implementation/tasks/`; returns a `State` projection. NO writes — `cli/scan.py` (Story 1.17) handles state.json + journal append."
    2. `from __future__ import annotations`
    3. Stdlib imports (alphabetized within block): `import json`, `import logging`, `from pathlib import Path`, `from typing import Any`
    4. Third-party imports: none (pydantic only consumed via `state.model`)
    5. SDLC imports: `from sdlc.errors import StateError`, `from sdlc.ids import parse_epic_id, parse_story_id, parse_task_id, EPIC_ID_REGEX, STORY_ID_REGEX, TASK_ID_REGEX`, `from sdlc.state import State`
    6. `_logger = logging.getLogger(__name__)`
    7. Module-level `Final[str]` constants for the three subdirectory paths:
       ```python
       _EPICS_SUBDIR: Final[str] = "01-Requirement/04-Epics"
       _STORIES_SUBDIR: Final[str] = "01-Requirement/05-Stories"
       _TASKS_SUBDIR: Final[str] = "03-Implementation/tasks"
       ```
       (Use `from typing import Final`.)
  - [ ] Implement helper `_validate_project_root(project_root: Path) -> None`:
    - If `not project_root.is_absolute()`: raise `StateError("scan requires an absolute project_root path", details={"path": str(project_root), "reason": "not_absolute"})`.
    - If `project_root.exists() and not project_root.is_dir()`: raise `StateError("scan project_root points at a non-directory path", details={"path": str(project_root), "reason": "not_a_directory"})`.
    - Missing project_root is NOT an error — falls through to the main walk which produces an empty State.
  - [ ] Implement helper `_load_json_artifact(path: Path) -> dict[str, Any]`:
    - `text = path.read_text(encoding="utf-8")`.
    - `try: payload = json.loads(text); except json.JSONDecodeError as e: raise StateError(f"scan failed to parse JSON artifact: {e}", details={"file": str(path), "reason": "malformed_artifact"}) from e`.
    - If `not isinstance(payload, dict)`: raise `StateError("scan expected JSON object at top level", details={"file": str(path), "reason": "non_object_artifact"})`.
    - Return `payload` (typed `dict[str, Any]`).
  - [ ] Implement helper `_walk_dir_sorted(dir_path: Path, regex: re.Pattern[str]) -> list[Path]`:
    - If `not dir_path.exists()`: return `[]`.
    - If `not dir_path.is_dir()`: return `[]` (defensive — symlink to a file, etc.).
    - Iterate `sorted(dir_path.iterdir(), key=lambda p: p.name)`. Filter:
      - Skip if `not p.is_file()` (subdirs handled separately by caller).
      - Skip if `p.name.startswith(".")` (hidden files — `.gitkeep`, `.DS_Store`).
      - Skip if `p.suffix != ".json"`.
      - Skip if `not regex.match(p.stem)` — log at WARN: `_logger.warning("scan: skipping foreign filename %s under %s (does not match %s)", p.name, dir_path, regex.pattern)`. NEVER raise.
    - Return sorted list of matching paths.
  - [ ] Implement the public `scan(project_root: Path) -> State`:
    1. Call `_validate_project_root(project_root)`.
    2. Walk epics: `epic_paths = _walk_dir_sorted(project_root / _EPICS_SUBDIR, EPIC_ID_REGEX)`. For each path: `epic_id = parse_epic_id(path.stem).raw` (validates + canonicalizes); load JSON; insert into a local `epics_dict: dict[str, Any]`. Use `dict(sorted(epics_dict.items()))` at the end to canonicalize insertion order (defensive — `_walk_dir_sorted` already sorted).
    3. Walk stories: iterate `sorted((project_root / _STORIES_SUBDIR).iterdir(), key=lambda p: p.name)` (subdirs per epic). For each subdir matching `EPIC_ID_REGEX` on its name, walk its `*.json` files via `_walk_dir_sorted(subdir, STORY_ID_REGEX)` and merge into `stories_dict`. Cross-link integrity is NOT checked (epic existence not verified).
    4. Walk tasks: same pattern, two-level nested, `regex=TASK_ID_REGEX`.
    5. Construct `State(schema_version=1, next_monotonic_seq=0, phase=1, epics=epics_dict, stories=stories_dict, tasks=tasks_dict)`. Return.
  - [ ] **Forbidden patterns at code-review time** (mirror Stories 1.10–1.14):
    - `print()` — use `_logger`.
    - `time.time()` / `datetime.now()` — scanner doesn't compute timestamps.
    - `os.environ[...]` — scanner takes `project_root` as input; environment never enters.
    - `subprocess.run` — pure read, no subprocess.
    - `open()` for writing state/journal — N/A; scanner is read-only.
    - Bare `except:` / `except Exception:` — narrow catches (`json.JSONDecodeError`, `OSError`).
    - Mutating function arguments — `project_root` is read-only input.
    - Float arithmetic — no numerics.
    - Caching scan results in module globals — scanner is per-call pure; no module-level state. (Future caching, if needed, lives in a dedicated cache layer with explicit invalidation; out of scope for v1 substrate.)
  - [ ] LOC budget for `scanner.py`: ≤ 300 LOC including module docstring, imports, helpers, and the public function. If the implementation grows beyond 250, factor out `_walk_dir_sorted` + `_load_json_artifact` into `engine/_scanner_helpers.py` (mirror `journal/_canonical.py`).
  - [ ] Type annotations: every public and private function fully annotated. `mypy --strict` must pass on `src/sdlc/engine/`.

- [ ] **Task 4: Update `MODULE_DEPS` boundary table + linter self-tests (AC: #5.3, #5.4)**
  - [ ] Edit `scripts/check_module_boundaries.py` lines 98-113. Add `"ids"` to the `engine.depends_on` frozenset:
    ```python
    "engine": ModuleSpec(
        depends_on=frozenset(
            {
                "errors",
                "ids",                                # NEW (Story 1.15) — scanner.py needs parse_epic_id/_story_id/_task_id
                "state",
                "journal",
                "signoff",
                "dispatcher",
                "hooks",
                "telemetry",
                "workflows",
                "specialists",
                "runtime",
                "config",
            }
        ),
        forbidden_from=frozenset({"cli", "dashboard"}),
    ),
    ```
    Add the inline comment naming Story 1.15 + scanner.py's import need so future readers understand the widening rationale.
  - [ ] Run the boundary linter against the codebase including the new scanner: `uv run python scripts/check_module_boundaries.py src/sdlc/ tests/`. Exit code MUST be 0. If any unrelated module fires, that's a pre-existing issue; only the engine→ids edit is in this story's scope.
  - [ ] Find the boundary self-discipline tests at `tests/test_check_module_boundaries.py` (and `tests/test_module_boundaries_main.py` for the CLI runner shape — per Story 1.4 patterns). Add a regression test in `tests/test_check_module_boundaries.py`:
    ```python
    def test_engine_can_import_ids_per_story_115() -> None:
        from scripts.check_module_boundaries import MODULE_DEPS
        assert "ids" in MODULE_DEPS["engine"].depends_on, (
            "Story 1.15 requires engine→ids dependency for scanner.py id parsing"
        )
    ```
    Match the existing test's marker convention — read the top of `tests/test_check_module_boundaries.py` to confirm whether it uses `@pytest.mark.unit` (or has no module-level marker, in which case omit). DO NOT add a new pytest marker.
  - [ ] Run `uv run pre-commit run boundary-validator --all-files` — must pass.

- [ ] **Task 5: Unit + integration tests for scanner; goldens regen if Story 1.14 already landed (AC: #1, #2, #3)**
  - [ ] Create `tests/unit/engine/__init__.py` (empty pytest collection sentinel; needs `from __future__ import annotations` per project convention even when empty — confirm by checking existing empty `__init__.py` files in `tests/unit/`).
  - [ ] Create `tests/unit/engine/test_scanner.py` with `pytestmark = pytest.mark.unit` and the following tests:
    - `test_scan_returns_empty_state_on_empty_project`: `scan(tmp_path)` returns `State(schema_version=1, next_monotonic_seq=0, phase=1, epics={}, stories={}, tasks={})`. Assert via `model_dump(mode="json")` equality.
    - `test_scan_returns_empty_state_when_artifact_dirs_missing`: same as above, also assert `_logger` did not raise (use `caplog` if logging assertions are needed).
    - `test_scan_raises_on_relative_project_root`: pass `Path("relative/path")`; assert `StateError` with `details["reason"] == "not_absolute"`.
    - `test_scan_raises_when_project_root_is_a_file`: `tmp_file = tmp_path / "x"; tmp_file.write_text("data")`; `scan(tmp_file)` raises `StateError` with `details["reason"] == "not_a_directory"`.
    - `test_scan_loads_epics_in_canonical_sort_order`: scaffold three epic files (`EPIC-charlie.json`, `EPIC-alpha.json`, `EPIC-bravo.json`) in `tmp_path/01-Requirement/04-Epics/`. Each contains `{"id": "<epic-id>", "title": "<x>"}`. `result = scan(tmp_path)`; assert `list(result.epics.keys()) == ["EPIC-alpha", "EPIC-bravo", "EPIC-charlie"]`.
    - `test_scan_loads_stories_under_epic_subdirs`: scaffold `04-Epics/EPIC-alpha.json` + `05-Stories/EPIC-alpha/EPIC-alpha-S01-x.json` + `05-Stories/EPIC-alpha/EPIC-alpha-S02-y.json`. Assert `result.stories.keys()` contains both story ids in canonical order.
    - `test_scan_loads_tasks_under_story_subdirs`: scaffold an epic + story + 2 task files. Assert `result.tasks.keys()` contains both task ids.
    - `test_scan_skips_foreign_filenames_with_warn`: scaffold `04-Epics/EPIC-good.json` and `04-Epics/random.json`. `scan(tmp_path)` returns a State with `epics == {"EPIC-good": ...}`; `caplog.records` (with `caplog.set_level(logging.WARNING)`) contains a warning naming `random.json`.
    - `test_scan_raises_on_malformed_json`: scaffold `04-Epics/EPIC-bad.json` containing `"not valid json{`. `scan(tmp_path)` raises `StateError` with `details["reason"] == "malformed_artifact"` and `details["file"]` ends in `EPIC-bad.json`.
    - `test_scan_raises_on_non_object_json`: scaffold `04-Epics/EPIC-list.json` containing `"[1, 2, 3]"`. `scan(tmp_path)` raises `StateError` with `details["reason"] == "non_object_artifact"`.
    - `test_scan_skips_hidden_files`: scaffold `04-Epics/EPIC-real.json` and `04-Epics/.DS_Store`. `scan(tmp_path).epics` contains only `"EPIC-real"`.
    - `test_scan_skips_non_json_files`: scaffold `04-Epics/EPIC-real.json` and `04-Epics/EPIC-text.txt`. `scan(tmp_path).epics` contains only `"EPIC-real"`.
    - `test_scan_is_idempotent_byte_equal`: scaffold a non-trivial corpus; `s1 = scan(p); s2 = scan(p)`; assert `_state_bytes(s1) == _state_bytes(s2)` per the canonical-bytes helper from AC1.3.
  - [ ] Create `tests/integration/test_scan_idempotent.py` with `pytestmark = pytest.mark.integration` and:
    - `test_scan_idempotent_across_processes`: scaffold a corpus in `tmp_path`; run `scan` twice via `subprocess.run` invoking small inline `uv run python -c "..."` scripts that print the canonical state bytes hex; assert the two hex strings match. SKIP on Windows if `shutil.which("uv") is None` (mirror Story 1.13's subprocess-test skip pattern). This catches non-determinism that's latent in single-process tests (e.g. `Path.iterdir()` order on filesystems where it's nondeterministic).
  - [ ] **If Story 1.14's goldens exist on disk** (Task 1 pre-flight check):
    - Open `tests/integration/test_abstraction_adequacy.py`. Find the inline scan-stub: `initial_state = State(schema_version=1, next_monotonic_seq=0, epics={})`. Replace with:
      ```python
      from sdlc.engine import scan
      initial_state = scan(tmp_path)  # Story 1.15: real scan replaces 1.14's no-op stub
      ```
      Update the inline comment from "scan step is a no-op stub for Epic 1; Story 1.15 will replace this with `engine.scanner.scan` when the scanner ships." to "scan step uses real `engine.scanner.scan`. Story 2B.3 will run the FULL pipeline including hook chain (Story 2A.4 substrate)."
    - Set `_REGENERATE_GOLDENS = True` in `tests/integration/test_abstraction_adequacy.py`.
    - Run `uv run pytest tests/integration/test_abstraction_adequacy.py -m integration -v`. The test will WRITE the goldens with the extended State shape and `pytest.fail(...)`. Verify `tests/fixtures/abstraction_adequacy/expected_state.json` now contains `"phase":1,"stories":{},"tasks":{}` keys.
    - Set `_REGENERATE_GOLDENS = False` and re-run. Test should pass green.
    - Update the `Regen history` block in `tests/fixtures/abstraction_adequacy/README.md`: add line `- 2026-05-09 (Story 1.15): regenerated after State model gained phase/stories/tasks fields and scan-stub replaced by engine.scanner.scan.`
    - Commit the regenerated goldens with the rest of the Story 1.15 commit (single commit per Story 1.14's `_REGENERATE_GOLDENS` discipline).
  - [ ] **If Story 1.14's goldens do NOT exist on disk yet**: skip the goldens regen step entirely. Story 1.14 dev later will pick up the extended State model and `scan()` from the start; their initial goldens generation will use the v1.15 shape directly, avoiding a regen.

- [ ] **Task 6: Add `pytest-benchmark` dev dep + benchmark test + CI job (AC: #4)**
  - [ ] Add `"pytest-benchmark>=4.0.0,<6"` to `[dependency-groups] dev` in `pyproject.toml` (after `hypothesis>=6.100,<7` per the alphabet-friendly insertion point — but the existing list is partially-sorted-by-purpose, so place it where consistency is best with neighbors; line ~30 is the natural slot). The `<6` cap is defensive against a future major: pytest-benchmark 5.x is current; 6 may shift the `benchmark.pedantic` API. Mirror the cap-pattern from `pyproject.toml:23-30`.
  - [ ] Run `uv lock` to refresh `uv.lock`. Commit the lock change in the same commit as the dep addition.
  - [ ] Create `tests/benchmark/__init__.py` (empty pytest collection sentinel with `from __future__ import annotations`).
  - [ ] Create `tests/benchmark/conftest.py` with the `_build_perf_corpus(root: Path) -> None` helper (per AC4 spec). Use `from __future__ import annotations`. The corpus is 4 epics × 50 stories per epic × 5 tasks per story = 200 stories + 1000 tasks total. Distributing across 4 epics keeps every per-epic story number in the regex-valid `S01..S50` range — `STORY_ID_REGEX` from `sdlc/ids/parsers.py:14` requires EXACTLY 2 digits in the `-S<NN>-` segment, so `S100+` would be silently skipped by `_walk_dir_sorted`'s regex filter. The helper:
    ```python
    def _build_perf_corpus(root: Path) -> None:
        """Scaffold 4 epics + 200 stories + 1000 tasks under root for the perf gate.

        Distributing 200 stories across 4 epics (50 each) keeps every story
        number in the regex-valid S01..S50 range. Single-epic 200-story
        layouts would emit S100..S200 filenames that STORY_ID_REGEX silently
        skips, undercounting the corpus.
        """
        epics_dir = root / "01-Requirement" / "04-Epics"
        stories_root = root / "01-Requirement" / "05-Stories"
        tasks_root = root / "03-Implementation" / "tasks"
        epics_dir.mkdir(parents=True)
        stories_root.mkdir(parents=True)
        tasks_root.mkdir(parents=True)
        for letter in ("a", "b", "c", "d"):
            eid = f"EPIC-perf-{letter}"
            (epics_dir / f"{eid}.json").write_text(
                json.dumps({"id": eid, "title": "perf"}),
                encoding="utf-8",
            )
            sdir = stories_root / eid
            sdir.mkdir()
            for n in range(1, 51):  # 50 stories per epic, S01..S50
                sid = f"{eid}-S{n:02d}-perf"
                (sdir / f"{sid}.json").write_text(
                    json.dumps({"id": sid, "title": "perf"}),
                    encoding="utf-8",
                )
                tdir = tasks_root / sid
                tdir.mkdir()
                for m in range(1, 6):  # 5 tasks per story, T01..T05 = 1000 tasks total
                    tid = f"{sid}-T{m:02d}-perf"
                    (tdir / f"{tid}.json").write_text(
                        json.dumps({"id": tid, "title": "perf"}),
                        encoding="utf-8",
                    )
    ```
    Total writes: 4 + 200 + 1000 = 1204 small JSON files (~60 KB). Construction time on a typical SSD is ~200-400 ms; the benchmark itself is the long pole, not the corpus build.
  - [ ] Create `tests/benchmark/test_scan_perf.py` with the cold + warm benchmark tests per AC4. Use `pytestmark = pytest.mark.benchmark` at module level. Skip on Windows (`@pytest.mark.skipif(sys.platform == "win32", reason="perf budget tuned for Linux/macOS; Windows pathlib walk diverges")`) — the warm-cache test is too sensitive on Windows for v1.
  - [ ] Create `tests/benchmark/README.md` with one paragraph: "Benchmark suite for performance-sensitive substrate. All corpora are scaffolded at runtime via `tmp_path` (see `conftest.py`); NO committed fixture trees. Run: `uv run pytest -m benchmark --benchmark-only`. Failures are CI gates, not informational."
  - [ ] Edit `.github/workflows/ci.yml`. Add a `benchmarks` job after `chaos-tests`:
    ```yaml
    benchmarks:
      name: Performance Benchmarks (Story 1.15)
      runs-on: ubuntu-latest
      needs: quality-gates
      timeout-minutes: 10
      steps:
        - uses: actions/checkout@v4
        - name: Install uv
          uses: astral-sh/setup-uv@v3
          with:
            version: "latest"
        - name: Set up Python 3.12
          run: uv python install 3.12
        - name: Install dev dependencies
          run: uv sync --frozen --group dev
        - name: Run benchmarks
          run: uv run pytest -m benchmark --benchmark-only --no-cov -v
    ```
    Pin Python 3.12 (single cell) — performance budgets are sensitive to interpreter version; running on every matrix cell would explode the gate's complexity for v1. Match the existing `chaos-tests` job's `setup-uv@v3` and `actions/checkout@v4` versions exactly. Story 1.3's CI workflow may use `astral-sh/setup-uv` at a different version; ALIGN to whatever `chaos-tests` already uses.
  - [ ] Update `pyproject.toml [tool.coverage.run].omit` if needed: `tests/benchmark/test_scan_perf.py` is under `tests/`; tests aren't in coverage scope, so no omit edit. Verify by re-reading the existing `omit = [...]` block.

- [ ] **Task 7: Author ADR-018 + update documentation (AC: all)**
  - [ ] Create `docs/decisions/ADR-018-engine-scanner-skeleton.md` using the structure of `docs/decisions/adr-template.md`:
    - **Status:** Accepted
    - **Date:** 2026-05-09 (or system date when story is dev'd)
    - **Story:** 1.15
    - **Context:** FR3 names `sdlc scan` as a v1 capability; Decision A4 makes `scan() → dispatch_next() → STOP_check()` the auto-loop's atomic step and "scan = pure function of disk state" (Architecture §339). Decision B5 makes `state.json` a projection — the scanner is the artifact-tree projection counterpart to Story 1.12's journal projection (NFR-PERF-1's < 2 s budget on 200/1000 corpora forces a benchmark gate so post-merge performance regressions are caught at CI rather than in production).
    - **Decision:**
      1. `engine.scanner.scan(project_root: Path) -> State` is a pure function: zero I/O writes, deterministic byte-equal output for a given on-disk state, total over the input space.
      2. The scanner is the v1 substrate read path; the `cli/scan.py` wrapper (Story 1.17) handles `state.json` write + journal append.
      3. The `State` model is extended with `phase: int = 1`, `stories: dict[str, Any]`, `tasks: dict[str, Any]` — additive, schema_version unchanged. Old `state.json` files validate against the extended model thanks to pydantic v2 default-supplying.
      4. The `MODULE_DEPS["engine"].depends_on` table widens to include `"ids"` so `scanner.py` can use `parse_epic_id/_story_id/_task_id`. No other engine→ids API surface ships in v1.
      5. NFR-PERF-1 is enforced by a `benchmark` CI job running pytest-benchmark on `ubuntu-latest` python 3.12, asserting `< 2 s` cold + `< 100 ms` warm on a 200/1000 corpus scaffolded at runtime.
      6. The scanner is read-only and POSIX/Windows portable. `cli/scan.py`'s wrapper is POSIX-only (inherits from `state.atomic` + `journal.writer`).
    - **Alternatives considered:**
      - `scan` writes state.json directly inside the function — rejected: couples scanner to atomic-write protocol; harms Story 1.14's stub story (which currently calls scan-equivalent code WITHOUT writing) and Story 1.20's `rebuild-state` (which will need scan output without the side effect). Pure read-only is the cleaner contract.
      - State model extension is deferred to Story 1.20 — rejected: Story 1.15's AC explicitly mentions `phase`, `stories`, `tasks` shape; pushing the extension to a later story leaves scanner returning incomplete State for Epic 1's substrate gate. The schema bump is additive; no migration cost.
      - Benchmark fixture is committed under `tests/fixtures/scanner_corpus/` — rejected: 1200 small JSON files inflate the repo by ~70 KB and add fixture-drift risk if the artifact schema evolves. Runtime scaffolding via `_build_perf_corpus` is reproducible from a clean clone in < 30 s.
      - `pytest-benchmark` is replaced by stdlib `time.perf_counter()` measurements — rejected: pytest-benchmark provides built-in regression detection (`--benchmark-compare`), per-run statistics aggregation, and IDE-friendly reports. The 1-line dev dep is worth the ergonomics for a CI-gated metric.
      - Benchmark runs on every CI matrix cell (`os × python-version`) — rejected: 8 cells × performance variance = noisy gate. Single-cell `ubuntu-latest` python 3.12 is the determinism floor; budget is tuned for that cell. Other cells are observed (test runs in `quality-gates` via `benchmark` marker SKIPPED there) but not gated.
      - Engine→ids dependency is avoided by inlining ID regex in scanner.py — rejected: duplicates `ids/parsers.py` source-of-truth; would drift the moment Story 1.6's regexes are tightened. The boundary widening is the canonical fix.
    - **Consequences:**
      - Story 1.14's golden state.json will drift on the FIRST run after this story lands (because `phase`, `stories`, `tasks` keys join the canonical bytes). The regen is documented in Story 1.14 AC4 / Task 4 + this story's Task 5; commit message NAMES the drift trigger.
      - Story 1.17's `cli/scan.py` will be a thin wrapper: `state = scan(project_root); write_state_atomic_sync(state, target=...); journal.append_sync(JournalEntry(kind="scan_completed", ...), journal_path=...)`. 1.17's complexity is in the CLI flag handling (`--no-color`, `--json`); the engine work is closed by 1.15.
      - Story 1.20's `rebuild-state` operates on the journal (1.12's projection), NOT the artifact tree (1.15's projection). The two are deliberately decoupled: artifact-tree mutations after the journal's last entry produce a divergent State that 1.20 surfaces as a recovery prompt. This is the canonical "audit-tree vs artifact-tree" reconciliation pattern.
      - Adding fields to `State` is now additive in Story 1.15-1.19; the schema_version bump (Story 1.21 wire-format-v1 lock ceremony) finalizes the v1 schema. Until then, adding fields is mechanical (extend the model + regenerate Story 1.14 goldens once).
      - The benchmark gate is now a hard CI requirement. PRs that regress scan performance > 5% beyond the 2 s / 100 ms budget will fail CI. The escape valve is `pytest --benchmark-compare-fail=mean:5%` for soft warnings or removing the `assert` line entirely (NEVER do this; the assertion is the gate).
    - **Revisit by:** Story 1.21 (wire-format v1 lock ceremony — the moment State schema_version is locked at 1; all field additions after that point require schema_version bump + migration script).
    - **References:** Architecture §117 (Project Lifecycle Mgmt FR1-FR5), §339 (Decision A4), §349 (Decision B5), §388 (v0.2 substrate roadmap), §815 (engine/scanner.py spec), §1133 (FR3 mapping), §1407 (engine implementation timeline). PRD §FR3, §NFR-PERF-1, §NFR-REL-5. ADR-013 (atomic state write protocol), ADR-014 (journal append-only), ADR-015 (state projection from journal — Story 1.12), ADR-017 (abstraction-adequacy — Story 1.14).
  - [ ] Update `docs/decisions/index.md`: add row `| [018](ADR-018-engine-scanner-skeleton.md) | Engine scanner skeleton — pure read, idempotent, perf-gated | 1.15 | Accepted |` after the existing ADR-014 row. Place in numeric position 018 (preserving any 015-017 gaps for in-flight stories).
  - [ ] Create or update `docs/CODEMAPS/engine-module.md` (one paragraph + table of submodules + scanner one-pager). For v1 the only submodule is `scanner.py`; future entries (`auto_loop.py`, `stop_triggers.py`) land in their respective stories.

- [ ] **Task 8: Run the full quality gate stack and verify CI green (AC: all)**
  - [ ] `uv run ruff check src/ tests/ scripts/` → 0 errors. The new `engine/scanner.py` and `engine/__init__.py` MUST satisfy `from __future__ import annotations` (auto-required by `tool.ruff.lint.isort`).
  - [ ] `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [ ] `uv run mypy --strict src/` → 0 errors. `engine/scanner.py` is fully annotated; no `Any` leak through public surface (the `dict[str, Any]` epic/story/task value is legitimate — artifact schema is not modeled in v1).
  - [ ] `uv run pre-commit run --all-files` → all hooks pass:
    - `ruff-check`, `ruff-format`, `mypy-strict` (existing).
    - `boundary-validator` — verify the `engine` row's added `ids` dep allows the scanner's import. The new file's imports MUST satisfy the boundary table (engine→{errors, ids, state} all permitted post-edit).
    - `state-write-protocol-validator` (Story 1.10) — runs on `src/sdlc/`; scanner.py does NOT call `Path.write_text` / `state.json` / atomic writes, so the validator's allowlist isn't relevant. Should not fire.
    - `journal-append-only-validator` (Story 1.11) — runs on `src/sdlc/`; scanner.py does NOT mutate `journal/`, so should not fire.
    - `runtime-import-via-abc-validator` (Story 1.13, if landed by then) — scanner.py does NOT import `runtime/`; should not fire.
    - `secret-hardcode-validator` (Story 1.8) — scoped to `^src/sdlc/.*\.py$`; scanner.py has no secrets.
    - `specialist-validator` (placeholder) — no impact.
  - [ ] `uv run pytest tests/unit/engine/ -m unit -v` → green; all scanner unit tests pass.
  - [ ] `uv run pytest tests/integration/test_scan_idempotent.py -m integration -v` → green (skipped on Windows if `uv` not on PATH).
  - [ ] `uv run pytest tests/benchmark/ -m benchmark --benchmark-only --no-cov -v` → green; cold mean < 2.0 s, warm mean < 100 ms on the dev host. (CI repeats on `ubuntu-latest`.)
  - [ ] If Story 1.14 already landed: `uv run pytest tests/integration/test_abstraction_adequacy.py -m integration -v` → green with regenerated goldens.
  - [ ] Global `uv run pytest --cov=src --cov-fail-under=90` → coverage gate passes. New `engine/scanner.py` should reach ≥ 95% line coverage from the unit + integration suites combined; the only uncovered branches should be unreachable defensive `_validate_project_root` paths (e.g. `not project_root.exists()` is graceful, not raising).
  - [ ] Confirm new files are tracked: `git status` → `src/sdlc/engine/__init__.py`, `src/sdlc/engine/scanner.py`, `tests/unit/engine/__init__.py`, `tests/unit/engine/test_scanner.py`, `tests/integration/test_scan_idempotent.py`, `tests/benchmark/__init__.py`, `tests/benchmark/conftest.py`, `tests/benchmark/test_scan_perf.py`, `tests/benchmark/README.md`, `docs/decisions/ADR-018-engine-scanner-skeleton.md`, `docs/CODEMAPS/engine-module.md` are all tracked. `pyproject.toml`, `uv.lock`, `scripts/check_module_boundaries.py`, `src/sdlc/state/model.py`, `.github/workflows/ci.yml` show modifications; if Story 1.14 landed, `tests/integration/test_abstraction_adequacy.py` and `tests/fixtures/abstraction_adequacy/expected_state.json` + `README.md` show modifications.
  - [ ] Verify `_REGENERATE_GOLDENS = False` in any committed file referencing the toggle (`tests/integration/test_abstraction_adequacy.py`). Mirror Story 1.14's belt-and-braces discipline.
  - [ ] Run the full suite from a clean clone-equivalent: `git clean -fdx; uv sync --frozen --group dev; uv run pytest`. Everything must pass.

## Dev Notes

### Why this story exists (FR + NFR + Decision mapping)

- **FR3 — `sdlc scan` (PRD §117, Architecture §1133)**: Story 1.15 ships the engine read path; Story 1.17 ships the CLI wrapper. Without 1.15, `sdlc scan` has no engine implementation; without 1.17, the engine has no user-facing surface.
- **NFR-PERF-1 — `< 2 s scan on 200/1000 corpus`**: This story is the literal materialization of the perf gate. The CI `benchmarks` job is the gate's enforcement.
- **NFR-REL-5 — `auto-loop is a pure function of disk state` (PRD)**: Decision A4 makes `scan()` the loop's read-side primitive. Story 1.15 ships scan; Story 4.1 ships the auto-loop.
- **Decision A4 — pure-function auto-loop (Architecture §339)**: "scan() → dispatch_next() → STOP_check() per iteration; no in-memory continuation." The pure-function contract for scan() ships in this story.
- **Decision B5 — state as projection of journal (Architecture §349)**: Story 1.12 ships journal-projection; Story 1.15 ships artifact-projection. Story 1.20 reconciles. The scanner is the artifact-projection half of B5.
- **Architecture §815 — `scanner.py — FR3 implementation; projection rebuild`**: this story creates that file.
- **Architecture §1407 — `Implement engine/scanner.py + engine/auto_loop.py skeleton against the mock runtime. Verify NFR-REL-5 (pure function of disk state) by killing the loop mid-iteration.`**: Story 1.15 ships scanner.py; auto_loop.py is Story 4.1. NFR-REL-5 verification (kill-mid-iteration) is Story 4.1's chaos test.

### File set this story creates / modifies

**New files (created):**

- `src/sdlc/engine/__init__.py` — public API re-export (`scan`)
- `src/sdlc/engine/scanner.py` — the scanner implementation (~250-300 LOC)
- `tests/unit/engine/__init__.py` — pytest collection sentinel
- `tests/unit/engine/test_scanner.py` — unit tests for scanner (~13 cases)
- `tests/integration/test_scan_idempotent.py` — cross-process determinism integration test
- `tests/benchmark/__init__.py` — pytest collection sentinel
- `tests/benchmark/conftest.py` — `_build_perf_corpus` fixture helper
- `tests/benchmark/test_scan_perf.py` — pytest-benchmark cold + warm gates
- `tests/benchmark/README.md` — short doc on perf-suite shape
- `docs/decisions/ADR-018-engine-scanner-skeleton.md` — new ADR
- `docs/CODEMAPS/engine-module.md` — engine module codemap (or update if exists)

**Optional new file** (factor out if scanner.py grows past 250 LOC):

- `src/sdlc/engine/_scanner_helpers.py` — `_walk_dir_sorted`, `_load_json_artifact`, `_validate_project_root` (single-underscore prefix marks private; importable from `tests/unit/engine/` for direct testing).

**Modified files:**

- `src/sdlc/state/model.py` — extend `State` with `phase`, `stories`, `tasks` fields (additive, schema_version unchanged)
- `scripts/check_module_boundaries.py` — `MODULE_DEPS["engine"].depends_on` gains `"ids"`
- `pyproject.toml` — add `pytest-benchmark>=4.0.0,<6` to dev deps
- `uv.lock` — refreshed by `uv lock` after dep addition
- `.github/workflows/ci.yml` — new `benchmarks` job after `chaos-tests`
- `docs/decisions/index.md` — add ADR-018 row

**Conditionally modified files** (only if Story 1.14 has landed at story-implement time):

- `tests/integration/test_abstraction_adequacy.py` — replace scan-stub with real `scan()` call; flip `_REGENERATE_GOLDENS=True`, regenerate, flip back to `False`.
- `tests/fixtures/abstraction_adequacy/expected_state.json` — regenerated bytes (now includes `phase`/`stories`/`tasks` keys).
- `tests/fixtures/abstraction_adequacy/README.md` — append regen-history line for Story 1.15.

**Files NOT modified (invariant — break-glass if any of these change):**

- `src/sdlc/state/atomic.py` — Story 1.10 closed; scanner does NOT write state.json.
- `src/sdlc/journal/writer.py`, `src/sdlc/journal/reader.py` — Story 1.11 closed; scanner does NOT touch journal.
- `src/sdlc/runtime/*.py` — Story 1.13's surface; scanner is runtime-agnostic.
- `src/sdlc/contracts/*.py` — Story 1.7 closed; scanner doesn't add/modify contracts.
- `src/sdlc/ids/*.py` — Story 1.6 closed; scanner consumes parsers, doesn't extend them.
- `.pre-commit-config.yaml` — no new hook. The benchmark gate runs in CI, not pre-commit (perf budgets are noisy on dev hosts).

### Why pure-function scanner (no I/O writes from inside `scan()`)

The epic AC says "it makes no writes to artifacts (only to state.json + journal append)". On its surface this could be read as "scanner writes state.json + appends journal." The cleaner architectural reading is: "the SCANNING OPERATION (engine.scanner.scan + cli/scan.py wrapper, viewed as a system-level transition) writes ONLY state.json + a journal entry — and writes ZERO artifacts."

We commit to the pure-function shape because:

1. **Story 1.14's stub is a pure-function shape**. Story 1.14's `tests/integration/test_abstraction_adequacy.py` substitutes `initial_state = State(...)` for the future scan call. When Story 1.15 lands, that line becomes `initial_state = scan(tmp_path)` — a 1-line replacement. If scan() also wrote state.json + appended journal, the test would have to RE-WRITE its substrate (the test owns the journal/state writes for its deterministic golden-bytes contract). The pure shape preserves the 1-line-replacement contract.
2. **Story 1.20's `rebuild-state` will reuse `scan()` output** to compare artifact-tree state against journal-projected state during reconciliation. If scan() wrote state.json on every call, rebuild-state would have to either (a) suppress the write via a flag (kludgy) or (b) call a half-private internal function. Pure shape avoids both.
3. **Testability**: pure functions test cleanly; functions that write disk require `tmp_path` fixtures + cleanup + race-condition awareness. The unit-test count is roughly halved by the pure shape.
4. **Decision A4 + B5 alignment**: the auto-loop's `scan() → dispatch_next() → STOP_check()` step contract treats scan as a read; writes are downstream effects of the loop's mutation logic, not scan's responsibility.

The CLI wrapper at `cli/scan.py` (Story 1.17) does:

```python
def cmd_scan(project_root: Path) -> int:
    state = scan(project_root)
    state_path = project_root / ".claude" / "state" / "state.json"
    journal_path = project_root / ".claude" / "state" / "journal.log"
    write_state_atomic_sync(state, target=state_path)
    seq = _next_seq(state)
    je = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=_utc_now_iso_ms(),
        actor="cli",
        kind="scan_completed",
        target_id=None,
        before_hash=None,
        after_hash=_state_hash(state),
        payload={"epic_count": len(state.epics)},
    )
    append_sync(je, journal_path=journal_path)
    return 0
```

(Pseudo-code, not in scope for Story 1.15. Documented to clarify the boundary.)

### Why `phase`, `stories`, `tasks` schema extension lands here

The epic AC explicitly names these fields: `phase=1, epics=[], stories=[], tasks=[]`. Three options for where the extension lands:

1. **Story 1.10 retroactively** — would amend a closed story. Rejected.
2. **Story 1.12 (state projection)** — reasonable but Story 1.12's scope is the projection FRAMEWORK, not field count. Story 1.12's reducer is intentionally narrow (only `state_mutation` + `epic-N` target_id). Adding fields there muddles the framework's purpose.
3. **Story 1.15 (this story)** — the FIRST consumer that produces a `State` with non-trivial structure. The scanner walks epics + stories + tasks; the natural place to add the corresponding fields is the consumer that needs them.

Option 3 is the cleanest. The `phase` field also lands here because it's a project-scope value the scanner can determine from filesystem inspection (e.g. presence of `02-Architecture/SIGNOFF.md` advances phase to 3; presence of `01-Requirement/SIGNOFF.md` advances to 2 — but for v1 minimal, the scanner returns `phase=1` unconditionally; signoff-driven phase advancement is Story 2A.12's work).

The schema_version stays at 1 because the addition is additive: pydantic v2 default-supplies missing optional fields when validating older `state.json` files. The schema_version bump is Story 1.21's wire-format-v1 lock ceremony — until then, additive growth is the discipline.

### Why pytest-benchmark over stdlib `time.perf_counter()`

Two options for the perf gate:

1. **Stdlib `time.perf_counter()` measurements** — pros: zero new dep. Cons: per-developer variance dominates the signal (a noisy `time.perf_counter` test trips on slow laptops); CI matrix variance ditto. We'd need bespoke statistical aggregation + comparison logic.
2. **pytest-benchmark** — pros: built-in `pedantic(iterations=N, rounds=R)` runs the function N×R times and reports median/mean/stddev; CI can compare against a stored baseline via `--benchmark-compare`. Cons: ~50 KB dep + lockfile churn.

Option 2 wins because the perf budget (`< 2 s` / `< 100 ms`) is tight enough that stdlib timing would be noise-dominated. pytest-benchmark's pedantic mode + dedicated CI cell isolates the signal. The dep cost is one-time.

### Why benchmarks run on a dedicated CI job, not in `quality-gates`

Adding the `benchmark` marker to the existing `quality-gates` job would multiply test runtime by N (per matrix cell) and cross-contaminate budget assertions with version-specific perf variance (Python 3.10 vs 3.13 have different `pathlib.iterdir()` micro-optimization profiles).

The dedicated `benchmarks` job:

- Runs single-cell (`ubuntu-latest` python 3.12) — deterministic budget reference.
- Runs ONLY `-m benchmark` tests — no overlap with `quality-gates`'s coverage gate.
- Runs after `quality-gates` (`needs: quality-gates`) — saves CI minutes if the suite already failed.
- Failure is hard, not informational — perf regression is a code-merge-block per NFR-PERF-1.

### Forward-compat: What Story 1.17 changes (and what it MUST NOT change)

When Story 1.17 lands `cli/scan.py`:

**MUST change:**

- New file `src/sdlc/cli/scan.py` exposing `cmd_scan(args) -> int`. Wraps `engine.scanner.scan` + `state.atomic.write_state_atomic_sync` + `journal.append_sync` per the pseudocode in "Why pure-function scanner" above.
- `pyproject.toml [project.scripts]` adds `sdlc = "sdlc.cli.main:app"` (uncommented; landed by 1.16 + 1.17).
- New CLI flag handling for `--no-color`, `--json` (per Story 1.17 AC).

**MUST NOT change:**

- The pure-function contract of `engine.scanner.scan` — Story 1.17 wraps it; does not subsume or replace it.
- The State model fields — additions are reserved for later substrate stories.
- The benchmark CI job — Story 1.17's CLI overhead is small enough to NOT shift the budget; if it does, the gate fires and the CLI is the regression source.

### Substrate dependencies — concrete API surface this story consumes

```python
# from sdlc.errors import StateError
# already shipped in Story 1.6; .details=dict[str, object] required

# from sdlc.ids import parse_epic_id, parse_story_id, parse_task_id, EPIC_ID_REGEX, STORY_ID_REGEX, TASK_ID_REGEX
parse_epic_id("EPIC-foo") -> EpicId(raw="EPIC-foo", epic_slug="foo")           # raises IdsError on invalid
parse_story_id("EPIC-foo-S01-bar") -> StoryId(...)                              # raises IdsError on invalid
parse_task_id("EPIC-foo-S01-bar-T01-baz") -> TaskId(...)                        # raises IdsError on invalid
EPIC_ID_REGEX.match("EPIC-foo") -> re.Match | None                              # used to skip foreign filenames before parse

# from sdlc.state import State
State(schema_version=1, next_monotonic_seq=0, phase=1, epics={}, stories={}, tasks={})
```

If any of these signatures shift between Stories 1.6/1.10 dev and Story 1.15 dev, this story's pre-flight (Task 1) catches it; abort and reconcile.

### Previous story intelligence — Stories 1.10 + 1.11 + 1.12 + 1.13 + 1.14

Patterns to mirror exactly (validated through 1.10's 9 patches, 1.11's review cycle, and 1.13/1.14 design):

- **`from __future__ import annotations`** at top of every new `.py` file.
- **`Final[...]` constants** for module-level immutables: `_EPICS_SUBDIR`, `_STORIES_SUBDIR`, `_TASKS_SUBDIR`. Mirror Story 1.10's `STATE_FILE_NAME` and Story 1.11's `JOURNAL_LOCK_SUFFIX`.
- **Pure helper functions with leading underscore**: `_validate_project_root`, `_load_json_artifact`, `_walk_dir_sorted`. Importable from `tests/unit/engine/` for direct testing without going through the public API. Mirror Story 1.10's `_canonicalize_state` and Story 1.11's `_canonicalize_entry`.
- **Narrow exception catches**: `json.JSONDecodeError`, `OSError` — never bare `except` or `except Exception`. Mirror Story 1.10's `OSError`-only catches in `_open_tmp` / `_write_bytes`.
- **Logger pattern**: `_logger = logging.getLogger(__name__)` — mirror `journal/writer.py:34`. Use `_logger.warning(...)` / `_logger.info(...)` for skipped-file diagnostics; never `print()`.
- **Type discipline**: `dict[str, Any]` is acceptable for the artifact value (schema is unmodeled in v1); every public + private function fully annotated; `mypy --strict` must pass.
- **Cross-platform vs POSIX-only**: scanner is **cross-platform** (no `fcntl`, no `O_APPEND`, no parent-dir fsync). DO NOT add a `sys.platform` skip. Tests run on Windows-latest as well as Linux/macOS — except the `test_scan_idempotent_across_processes` integration test which uses `subprocess.run` + `uv` (skip on Windows if `shutil.which("uv") is None`, mirror Story 1.13).
- **`pytestmark = pytest.mark.<marker>`**: module-level marker stacking for unit/integration/benchmark. Mirror Stories 1.10–1.14's pattern.
- **`_REGENERATE_GOLDENS` toggle** (only relevant if Story 1.14 has landed): mirror Story 1.14's regen discipline exactly. The goldens regen is a one-time event when this story merges.

Code-review feedback from Stories 1.10-1.14 to pre-empt:

- Be explicit about exception chaining (`raise StateError(...) from exc`) in `_load_json_artifact`.
- Avoid `Any` in PUBLIC type hints — `dict[str, Any]` for artifact values is OK because the artifact schema is genuinely unmodeled in v1; document via docstring.
- Verify `mypy --strict` passes BEFORE committing. The strict config rejects untyped functions, missing returns, and Any leaks. Tests under `tests/*` are NOT under strict (`tests.*` override at `pyproject.toml:118-121`), but the helpers should still type-annotate cleanly.
- Use `path.read_text(encoding="utf-8")` always — never bare `path.read_text()` (default encoding is locale-dependent and breaks Windows UTF-8 reads).
- Use `path.iterdir()` + sort — never `os.listdir()` (returns strings, not Paths) or `glob.glob()` (sorting semantics differ across OS).
- Narrow exception catches; do NOT swallow programmer errors.
- For coverage: `engine/scanner.py` IS in coverage scope (`source = ["src/sdlc", "scripts"]` per `pyproject.toml:186`). Target ≥ 95% line + branch coverage.
- For boundary linter: confirm the `engine→ids` widening edit's specific test catches the case where the linter forgets to revalidate `engine.depends_on`.

### Git intelligence — last 5 commits (as of story authoring)

```
26f619a feat: implement append-only journal with property tests and linter (Story 1.11)
2f4322d feat: implement atomic state write protocol with chaos tests (Story 1.10)
ce351c5 chore: ignore graphify output and config files
99c8f78 chore: update skills, add Story 1.9, graphify output, and project config
b378b5a fix: apply code-review patches for Story 1.8 config module
```

**Notable**: Stories 1.12 (state projection), 1.13 (AIRuntime + Mock), 1.14 (abstraction-adequacy CI test) are `ready-for-dev` per sprint-status.yaml — all three authored but not yet implemented at Story 1.15 author time. Story 1.15 has NO HARD DEP on any of them: scanner consumes `state.model.State`, `errors`, `ids` — all from closed stories (1.6, 1.10).

If Story 1.14 lands BEFORE Story 1.15, Task 5 includes the goldens regen step. If Story 1.14 has not landed, Task 5 skips that step entirely (Story 1.14's eventual dev will use the extended State + scan() from the start).

**Commit pattern to follow** (Stories 1.10/1.11/1.12/1.13/1.14 precedent):

- One `feat: implement engine scanner skeleton with perf gate (Story 1.15)` commit covering: `src/sdlc/engine/{__init__,scanner}.py`, optional `src/sdlc/engine/_scanner_helpers.py`, `src/sdlc/state/model.py` (additive fields), `tests/unit/engine/`, `tests/integration/test_scan_idempotent.py`, `tests/benchmark/`, `pyproject.toml` + `uv.lock` (dev dep), `scripts/check_module_boundaries.py` (engine→ids), `.github/workflows/ci.yml` (benchmarks job), `docs/decisions/ADR-018-*.md`, `docs/decisions/index.md` edit, `docs/CODEMAPS/engine-module.md`. If Story 1.14 has landed, also includes `tests/integration/test_abstraction_adequacy.py` + regenerated goldens + README update.
- Optional: one `fix: apply code-review patches for Story 1.15` follow-up if reviewers flag scanner correctness or perf-gate stability (Stories 1.8/1.10/1.11 precedent).

### Latest tech information

- **Python 3.10+** target (`pyproject.toml:10`). Used: `Final[...]`, `dict[str, Any]`, `Path`. All stable in 3.10+. `pathlib.Path.iterdir()` order is OS-dependent (NOT alphabetical on ext4 by default); the scanner explicitly `sorted(...)` for determinism.
- **pydantic 2.x** (`pyproject.toml:12`). `model_config = ConfigDict(frozen=True, extra="forbid")`; default-supplying behavior for missing optional fields is documented in pydantic v2 docs and stable. `model_dump(mode="json")` produces a JSON-coercible dict.
- **pytest-benchmark 4.x / 5.x** (NEW dev dep). Stable since 4.0; cap at `< 6` defensively. `benchmark.pedantic(func, args, iterations, rounds, warmup_rounds)` is the canonical fine-grained API. `benchmark.stats.stats.mean` gives mean wall time post-run.
- **`pathlib.Path.read_text(encoding="utf-8")`** (stdlib). Stable; explicit encoding mandatory because default encoding is `locale.getpreferredencoding()` which differs Windows vs Linux.
- **`json.loads`** + `json.JSONDecodeError` (stdlib). Stable.
- **`re.Pattern[str].match`** (stdlib). Compiled regexes from `sdlc.ids.parsers` (`EPIC_ID_REGEX`, etc.) — already-compiled `Pattern` objects, just call `.match(stem)`.
- **`logging.getLogger(__name__)`** (stdlib). Plain logger — `engine/logging.py` (structlog wrapper) lands in Story 2A.x; until then, stdlib logging is the canonical engine logger per Architecture §564 deferral.

### Project Structure Notes

- **Alignment with unified project structure**: this story creates `src/sdlc/engine/__init__.py` and `src/sdlc/engine/scanner.py` per Architecture §812-§819. It uses `tests/unit/engine/` (mirrors `src/sdlc/engine/`), `tests/integration/test_scan_idempotent.py`, `tests/benchmark/test_scan_perf.py` per Architecture §685-§691.
- **No conflict with architecture**: every file path lives under directories the architecture has declared. `tests/benchmark/` is a sibling of `tests/{unit,integration,property,chaos,e2e,fixtures}`. The `benchmark` marker is already declared (`pyproject.toml:181`); only the dev dep is new.
- **Pyproject markers**: `unit`, `integration`, `benchmark` already exist. No new marks.
- **CI workflow**: ONE new job (`benchmarks`); does not modify the existing `quality-gates` or `chaos-tests` jobs. Single-cell runner (`ubuntu-latest` python 3.12) for perf-budget determinism.
- **Coverage**: `src/sdlc/engine/scanner.py` IS in coverage scope. Target ≥ 95% via the unit + integration suites. Coverage-omit list at `pyproject.toml:187-203` does NOT include `engine/`.
- **MODULE_DEPS**: `engine.depends_on` extends from 11 entries to 12 (gain `ids`). The boundary self-discipline test catches the change.

### Why deferred from this story

These are explicitly NOT in scope for Story 1.15 — flag if they creep in during implementation:

- **`cli/scan.py` + `sdlc scan` CLI command** — Story 1.17. The scanner is consumable from Python imports only in v1.15.
- **`engine/auto_loop.py`** — Story 4.1. Story 1.15 ships scanner only; auto-loop comes later.
- **`engine/stop_triggers.py`, `engine/auto_brainstorm.py`, `engine/auto_mad.py`, `engine/replan.py`** — Stories 4.x. Out of scope.
- **`engine/logging.py` (structlog wrapper)** — Story 2A.x. Until then, scanner uses stdlib `logging`.
- **State model `next_monotonic_seq` advancement** — scanner returns `next_monotonic_seq=0` for all artifact-tree-derived states. Advancement is journal-driven (Stories 1.12 + 1.20).
- **State `phase` advancement based on signoff presence** — Story 2A.12 (signoff records). For v1 scanner returns `phase=1` unconditionally. Document this in scanner.py inline.
- **Cross-link integrity validation** (orphaned story without parent epic; orphaned task without parent story) — Story 1.20 (rebuild-state). v1 scanner is purely additive.
- **Watching for filesystem changes (inotify-style)** — out of scope; scanner is on-demand only.
- **Caching scan results** — out of scope; scanner is per-call pure.
- **Reading hook-hashes.json, adopt-report.json, etc.** — Stories 2A.5 (tampering detection), 3.x (adopt-mode). Scanner reads only the canonical artifact tree.
- **Property tests (hypothesis-driven)** — out of scope for v1.15; the unit + integration tests cover the deterministic shape. A future test-hardening story (or first regression that escapes coverage) introduces property tests.
- **Brownfield (adopt-mode) scanning** — Epic 3. v1 scanner assumes a greenfield project; symlinks created by adopt-mode are followed transparently (default `Path.is_file()` semantics) but not specially tagged.
- **NFC normalization of filename stems** — Architecture §513 mandates NFC for hashed JSON content; filenames are out of scope (filesystem handles normalization at the OS level). Mirror Story 1.10's NFC discipline only at JSON content boundary, not filenames.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.15] (lines 777-800) — story spec, AC blocks
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.14] (lines 692-775) — predecessor; scan-stub replacement contract
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.17] (lines 827-855) — successor; cli/scan.py wraps engine.scanner.scan
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.20] (lines 906-929) — successor; rebuild-state reconciles artifact-tree vs journal projections
- [Source: _bmad-output/planning-artifacts/architecture.md#FR-Map] (line 117) — FR1-FR5 lifecycle includes filesystem scanner
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-A4] (lines 339, 388) — pure-function auto-loop step contract
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-B5] (line 349) — state as projection
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Layout] (lines 812-819) — engine/scanner.py canonical location
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Deps] (line 1068) — engine module dependency table row (extended by this story)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR3-Mapping] (line 1133) — FR3 → cli/scan.py + engine/scanner.py
- [Source: _bmad-output/planning-artifacts/architecture.md#Test-Layout] (lines 685-695) — tests/unit/engine/, tests/integration/, tests/benchmark/ canonical locations
- [Source: _bmad-output/planning-artifacts/architecture.md#Code-Style] (lines 487-494) — no print/no time.time/no os.environ/no subprocess/no open() rules
- [Source: _bmad-output/planning-artifacts/architecture.md#Naming-Conventions] (lines 425-441) — Epic/Story/Task ID grammar
- [Source: _bmad-output/planning-artifacts/architecture.md#Filesystem-Layout] (lines 443-481) — canonical project filesystem
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation-Plan] (line 1407) — substrate roadmap location
- [Source: _bmad-output/planning-artifacts/prd.md#FR3] — sdlc scan
- [Source: _bmad-output/planning-artifacts/prd.md#NFR-PERF-1] — < 2 s scan budget
- [Source: _bmad-output/implementation-artifacts/1-14-behavioral-conformance-abstraction-adequacy-ci-test.md] — Story 1.14 (predecessor) — scan-stub replacement target
- [Source: _bmad-output/implementation-artifacts/1-12-state-projection-from-journal-replay-property-test.md] — Story 1.12 — sibling projection (journal-side)
- [Source: _bmad-output/implementation-artifacts/1-11-append-only-journal-property-test.md] — Story 1.11 — journal substrate (consumed by cli/scan.py wrapper, NOT by scanner)
- [Source: _bmad-output/implementation-artifacts/1-10-atomic-write-protocol-chaos-tests.md] — Story 1.10 — State model + atomic write
- [Source: _bmad-output/implementation-artifacts/1-6-foundation-errors-and-ids-modules.md] — Story 1.6 — ids parsers consumed by scanner
- [Source: src/sdlc/state/model.py:1-23] — current State (extended by Task 2)
- [Source: src/sdlc/ids/__init__.py:1-32] — parsers consumed by scanner
- [Source: src/sdlc/ids/parsers.py:9-27] — EPIC/STORY/TASK_ID_REGEX
- [Source: src/sdlc/errors/__init__.py:1-37] — StateError consumed by scanner
- [Source: scripts/check_module_boundaries.py:98-118] — engine module spec (modified by Task 4)
- [Source: pyproject.toml:21-31] — dev deps (extended by Task 6)
- [Source: pyproject.toml:181] — benchmark marker (already declared)
- [Source: pyproject.toml:118-121] — tests.* mypy override (relaxed strictness)
- [Source: pyproject.toml:186-203] — coverage source / omit (engine/ NOT omitted)
- [Source: .github/workflows/ci.yml] — CI workflow (extended by Task 6 with benchmarks job)
- [Source: docs/decisions/index.md] — ADR log table (extended by Task 7)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
