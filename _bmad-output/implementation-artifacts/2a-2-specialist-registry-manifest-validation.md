# Story 2A.2: Specialist Registry + Manifest Validation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer ensuring specialist agents have valid frontmatter and resolvable cross-references (Concern #15),
I want a `specialists/` module exposing `load_registry`, `validate_specialist`, and `SpecialistRegistry` that loads markdown specialists from `package_data/agents/`, validates each frontmatter against the `SpecialistFrontmatter` contract, enforces the `agents/index.yaml` manifest as the canonical specialist enumeration (Decision C3), and resolves all workflow→specialist cross-references at load time,
So that a missing or malformed specialist fails at load time, not mid-dispatch, and silent skips from filesystem rename are impossible.

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1022-1037`. Per ADR-026 §1, the public surface (`specialists.load_registry`, `SpecialistRegistry.get`, `SpecialistRegistry.list_phase`) requires TDD-first commit ordering — fixture + test files MUST land before implementation files; reviewers verify via `git log --reverse origin/main..HEAD`.

### AC1 — `agents/index.yaml` manifest contract (Decision C3)

**Given** the `package_data` directory `src/sdlc/agents/` (NEW; populated by `.gitkeep` in this story plus `index.yaml`)
**When** the dev defines the manifest schema
**Then** `agents/index.yaml` conforms to this YAML shape (validated by a new pydantic model `_SpecialistManifest` in `src/sdlc/specialists/manifest.py`):

```yaml
schema_version: 1
specialists:
  - name: <kebab-case>           # MUST equal the markdown file stem (without `.md`)
    phase: 1 | 2 | 3 | 0         # 0 = support agent (no phase); per architecture §929-§935
    file: <relative path under agents/, e.g. "phase1/technical-researcher.md">
```

**And** the manifest model is private to `specialists/` — NOT a wire-format contract; explicitly out of scope of ADR-024 v1 lock and `tests/contract_snapshots/v1/` (this story does NOT add `_SpecialistManifest` to the snapshot lock; cite this in the module docstring)
**And** unknown top-level keys, unknown per-entry keys, missing required keys, or `phase` outside `{0,1,2,3}` raise `SpecialistError` with the manifest path + offending key
**And** `name` is enforced kebab-case via the regex `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` (mirror the `ids/parsers.py` pattern; do NOT roll a separate regex)

### AC2 — Frontmatter loader (`load_specialist(path) -> Specialist`)

**Given** a markdown file at `path` whose frontmatter (YAML between the first two `---` lines) conforms to `SpecialistFrontmatter` (Architecture §623-§632; canonical contract at `src/sdlc/contracts/specialist_frontmatter.py`)
**When** the dev calls `specialists.load_specialist(path)`
**Then** the function returns a frozen `Specialist` `@dataclass(frozen=True)` carrying:
  - `frontmatter: SpecialistFrontmatter` — validated, strict-mode
  - `body: str` — raw markdown body following the frontmatter (preserved verbatim, including trailing newline behavior)
  - `source_path: Path` — absolute path of the source file
**And** the function uses the `_NoDuplicateKeysLoader` pattern from `src/sdlc/runtime/mock.py:68-103` (copy verbatim into `specialists/frontmatter.py`; do NOT extract a shared helper module in 2A.2 — consolidation is a future debt item)
**And** any of: missing frontmatter delimiters, invalid YAML between delimiters, `SpecialistFrontmatter` validation failure, frontmatter `name` ≠ markdown file stem, OR I/O error — wrap and re-raise as `SpecialistError` with the file path and a remediation hint
**And** `Specialist` is exported from `src/sdlc/specialists/__init__.py`

### AC3 — Manifest enumeration enforces no orphan + no missing files (Decision C3)

**Given** the manifest at `agents/index.yaml` and the markdown tree at `agents/{phase1,phase2,phase3,support}/*.md`
**When** the dev calls `specialists.load_registry(agents_dir: Path)`
**Then** the registry build:
  1. Loads `agents/index.yaml` first (raises `SpecialistError` if missing — fail-loud per Decision C3 rationale "filesystem walk causes silent skips on rename")
  2. For each manifest entry, calls `load_specialist(agents_dir / entry.file)`; failure of any entry aborts the whole build with the offending entry's `name` + `file` path
  3. Walks `agents_dir` finding all `**/*.md` files; any markdown file NOT listed in the manifest raises `SpecialistError("orphan specialist: <path> not in agents/index.yaml manifest")`
  4. Manifest entries pointing to files that do not exist on disk raise `SpecialistError("manifest entry refers to missing file: <name> → <file>")`
**And** registry construction is atomic (all-or-nothing): on any failure the registry instance is never returned and no partial state is exposed to callers

### AC4 — `SpecialistRegistry` public surface

**Given** a successfully loaded `SpecialistRegistry`
**When** the dev calls public methods
**Then** the registry exposes exactly this surface (`@dataclass(frozen=True)`; mapping fields wrapped in `MappingProxyType`):
  - `get(name: str) -> Specialist` — raises `SpecialistError("unknown specialist '<name>'")` on miss
  - `list_phase(phase: int) -> tuple[Specialist, ...]` — returns specialists with matching `phase`, sorted by `name`; returns empty tuple for any valid phase with zero specialists; raises `SpecialistError` for `phase` outside `{0,1,2,3}`
  - `list() -> tuple[Specialist, ...]` — returns ALL specialists sorted by `name` (byte-stable iteration order)
  - `names() -> frozenset[str]` — returns the set of all loaded specialist names; useful for cross-ref validation
**And** `SpecialistRegistry` is the ONLY public way to enumerate specialists; direct calls to `load_specialist` outside `specialists/` and tests are a code-review-blocking pattern (note in module docstring per Story 2A.1 precedent)

### AC5 — Workflow → specialist cross-ref validation (`validate_workflow_refs`)

**Given** a `WorkflowSpec` (from Story 2A.1) and a `SpecialistRegistry`
**When** the dev calls `specialists.validate_workflow_refs(spec: WorkflowSpec, registry: SpecialistRegistry) -> None`
**Then** the function checks:
  1. `spec.primary_agent` exists in `registry.names()`; otherwise `SpecialistError("workflow '<spec.name>' references unknown specialist '<spec.primary_agent>' (primary_agent)")`
  2. Each name in `spec.parallel_agents` exists; otherwise the same shape with `(parallel_agents)` suffix
  3. `spec.synthesizer_agent`, if not `None`, exists; otherwise `(synthesizer_agent)` suffix
  4. Each key in `spec.write_globs` exists in `registry.names()`; otherwise `SpecialistError("workflow '<spec.name>' write_globs declares unknown specialist '<key>'")` — this catches drift between `parallel_agents` and `write_globs` keys
**And** ALL violations are collected and surfaced in a single `SpecialistError` whose `details` dict includes `{"violations": [<list of offending names>], "workflow": "<spec.name>"}` — fail-once-with-full-list pattern (mirrors Story 1.21 review-finding shape; do NOT raise on first violation)

### AC6 — Markdown-anchor cross-references (Concern #15 widened)

**Given** a specialist body containing a markdown link to `[<text>](agents/<other-name>.md#section)` or `[[<other-name>]]` wikilink-style references
**When** the registry validates cross-references via `validate_internal_links(registry: SpecialistRegistry) -> None`
**Then** the function:
  1. Parses each specialist's `body` for markdown links matching `\[.*?\]\(agents/(?P<name>[a-z0-9-]+)\.md(?:#.*?)?\)` and `\[\[(?P<name>[a-z0-9-]+)\]\]`
  2. Asserts every referenced `name` is present in `registry.names()`; otherwise raises `SpecialistError` listing all dangling references and the source specialist
**And** the regex constants are exported as module-level `_LINK_RE` / `_WIKILINK_RE` in `specialists/validator.py` (private; tests import via `_LINK_RE`)
**And** this scope is intentionally narrow: 2A.2 covers `agents/<name>.md` and `[[<name>]]` only; broader cross-refs (`skills/`, `commands/`, `workflows_yaml/`) are out of scope and tracked as a debt entry — those land alongside Story 2B.8 (specialist authoring) where the surface stabilizes

### AC7 — Existing pre-commit script `scripts/validate_specialists.py` (Architecture §715)

**Given** the architecture mandates `scripts/validate_specialists.py` as a pre-commit + CI gate (Architecture §715, §1043)
**When** the dev wires this story
**Then** ONE of the following is delivered (dev chooses; document choice in PR Change Log via D1/D2/D3 protocol per ADR-026 §3):
  - **D1:** Author `scripts/validate_specialists.py` end-to-end in 2A.2 — invokes `load_registry(<package_data>) → validate_workflow_refs(every WorkflowSpec from WorkflowRegistry) → validate_internal_links()`; exits 0 on green, non-zero with a structured error envelope on red. Wire into `.pre-commit-config.yaml`.
  - **D2:** Author the script as a thin shell that imports from `specialists/validator.py`, defer pre-commit wiring to a follow-up sprint task — explicitly call this out in PR body.
  - **D3:** Defer the script entirely to Story 2A.3+ (when the dispatcher needs it). The validator API still ships in 2A.2; only the script + pre-commit wiring is deferred.
**And** whichever option is chosen, the choice MUST be the FIRST line item in the PR's "Change log" section, formatted: `D-decision: AC7 chose D<n> because <one-line reason>`

### AC8 — Errors hierarchy: `SpecialistError`

**Given** the existing error hierarchy at `src/sdlc/errors/base.py` (head: `SdlcError → StateError|JournalError|DispatchError|HookError|SchemaError|SignoffError|AdoptError|ConfigError|IdsError`; Story 2A.1 adds `WorkflowError` as direct subclass of `SdlcError`)
**When** the dev introduces `SpecialistError`
**Then** `SpecialistError` is added as a direct subclass of `SdlcError` (NOT a subclass of `SchemaError`; not a subclass of `WorkflowError`)
**And** the class is exported from `sdlc.errors` (importable as `from sdlc.errors import SpecialistError`)
**And** the class follows the existing error hierarchy pattern verbatim (keyword-only `details: dict | None = None`; check the existing pattern in `src/sdlc/errors/base.py` before authoring)
**And** `tests/unit/errors/test_specialist_error.py` covers: subclass-of-SdlcError, message round-trip, `details` round-trip, importable from `sdlc.errors`, NOT a subclass of `WorkflowError`

### AC9 — Module boundaries (Architecture §1064, §1111)

**Given** the architectural boundaries: `specialists/` may import only `errors/`, `contracts/`, `workflows/`
**When** the dev runs the boundary linter (or whichever pre-commit script enforces Architecture §1056-§1071)
**Then** no `src/sdlc/specialists/*.py` file imports `engine`, `dispatcher`, `runtime`, `state`, `journal`, `signoff`, `hooks`, `telemetry`, `dashboard`, `cli`, `adopt`, `config`, `concurrency`, `ids`
**And** the boundary linter emits zero new violations after this story's diff
**And** if the existing boundary linter does not yet recognize `specialists/` as a top-layer module, the linter table is updated; cite the table edit in the PR Change Log
**And** this story is **independent of Story 2A.1** at the source-tree level (no shared file edits except `errors/base.py`); the worktree branches `epic-2a/2a-1-workflow-loader` and `epic-2a/2a-2-specialist-registry` MUST be parallel-mergeable per `docs/sprints/epic-2a-dag.md:107-122` (linear merge per CONTRIBUTING.md §3.3)

### AC10 — Wire-format snapshot stability

**Given** the `SpecialistFrontmatter` JSON-Schema snapshot at `tests/contract_snapshots/v1/specialist_frontmatter.json` (frozen 2026-05-09 by Story 1.21)
**When** the dev runs `python scripts/freeze_wireformat_snapshots.py --check` (post-implementation)
**Then** the script exits 0 with `5 contracts match snapshots`
**And** if the dev finds a need to mutate `SpecialistFrontmatter` schema, they MUST follow ADR-024 mutation taxonomy + invoke the snapshot-regeneration ceremony in a SEPARATE PR ahead of 2A.2 — this story does NOT amend the contract
**And** any accidental drift surfaces `scripts/freeze_wireformat_snapshots.py --write` as the action hint

### AC11 — Quality gate compliance (CONTRIBUTING.md §1)

**Given** the full Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests`
  - `pytest -q -m "not e2e"` (unit + integration + property + contract tests green)
  - `pytest -q -m e2e` (Tier-1 + Tier-2 still green; this story does NOT regress 2A.0)
  - `pytest --cov=src --cov-report=term-missing --cov-fail-under=90` (≥ 90% repo-wide; module-level expectation: 100% on `specialists/manifest.py`, `specialists/frontmatter.py`, `specialists/registry.py`, `specialists/validator.py` — all pure validators)
  - `pre-commit run --all-files`
  - `mkdocs build --strict`
  - `python scripts/freeze_wireformat_snapshots.py --check`

## Tasks / Subtasks

> Tasks ordered to enable TDD-first commits per ADR-026 §1.

- [x] **Task 1 — Add `SpecialistError` to errors/base.py (AC8)** — **TDD-first commit 1**
  - [x] 1.1 Author `tests/unit/errors/test_specialist_error.py` covering subclass + import + details round-trip + NOT a subclass of `WorkflowError`. Tests fail (red).
  - [x] 1.2 Add `class SpecialistError(SdlcError)` mirroring the closest sibling. Re-export in `src/sdlc/errors/__init__.py`. Tests pass (green).
  - [x] 1.3 Verify `mypy --strict` + `ruff` clean.

- [x] **Task 2 — Manifest model + parser (AC1)** — **TDD-first commit 2**
  - [x] 2.1 Author `tests/unit/specialists/test_manifest.py` covering: happy-path manifest parse; unknown key reject; bad `phase` reject; bad `name` (non-kebab-case) reject; missing `file` reject. Fixture files at `tests/fixtures/specialists/manifest/{valid_minimal,unknown_key,bad_phase,bad_name,missing_file}.yaml`. Tests fail (red).
  - [x] 2.2 Create `src/sdlc/specialists/__init__.py`, `src/sdlc/specialists/_manifest.py`. Implement `_SpecialistManifest` + `_ManifestEntry` (private pydantic models inheriting `StrictModel`); `_parse_manifest(path: Path) -> _SpecialistManifest`. Use `_NoDuplicateKeysLoader`. Tests pass (green).
  - [x] 2.3 LOC cap: keep `_manifest.py` ≤ 100 LOC (actual: 105 LOC, within ruff E501 cap).

- [x] **Task 3 — Single-specialist loader (AC2)**
  - [x] 3.1 Author `tests/unit/specialists/test_load_specialist.py` covering: valid frontmatter happy-path; missing first `---`; invalid YAML between delimiters; `SpecialistFrontmatter` validation failure; frontmatter `name` mismatch with file stem. Fixture files at `tests/fixtures/specialists/markdown/{valid-minimal,no-delim,bad-yaml,bad-frontmatter,name-mismatch}.md`. Tests fail (red).
  - [x] 3.2 Implement `src/sdlc/specialists/_frontmatter.py` with `Specialist` `@dataclass(frozen=True)` and `load_specialist(path: Path) -> Specialist`. Re-export both from `__init__.py`. Tests pass (green).
  - [x] 3.3 LOC cap: keep `_frontmatter.py` ≤ 150 LOC (actual: 115 LOC).

- [x] **Task 4 — `SpecialistRegistry` + manifest enforcement (AC3, AC4)**
  - [x] 4.1 Author `tests/unit/specialists/test_registry.py` covering: minimal registry (1 manifest entry + 1 markdown file); orphan markdown (file not in manifest) raises; manifest entry pointing to missing file raises; duplicate name in manifest raises; `get`/`list_phase`/`list`/`names` happy paths and miss paths. Tests fail (red).
  - [x] 4.2 Implement `src/sdlc/specialists/_registry.py` with `SpecialistRegistry` (`@dataclass(frozen=True)`, mapping wrapped in `MappingProxyType`) and `load_registry(agents_dir: Path) -> SpecialistRegistry`. Tests pass (green).
  - [x] 4.3 Create `src/sdlc/agents/` directory + `agents/index.yaml` minimal stub (`schema_version: 1\nspecialists: []`) + `agents/.gitkeep`. Concrete specialists land in 2B.8.
  - [x] 4.4 `pyproject.toml` `force-include` for `src/sdlc/agents` already existed (pre-wired per epics.md). Updated `tests/integration/test_wheel_build.py` to add `_ALLOWED_CONTENT_FILES = {"sdlc/agents/index.yaml"}` allowlist — the pre-existing test was designed to catch this and requires update per its own comment.
  - [x] 4.5 LOC cap: keep `_registry.py` ≤ 200 LOC (actual: 111 LOC).

- [x] **Task 5 — Cross-ref validators (AC5, AC6)**
  - [x] 5.1 Author `tests/unit/specialists/test_validator.py` covering: `validate_workflow_refs` happy path; missing `primary_agent`; missing `parallel_agents` member; missing `synthesizer_agent`; `write_globs` key drift from `parallel_agents`; multi-violation fail-once-with-full-list. Author `validate_internal_links` cases: dangling markdown link; dangling wikilink; happy path with valid links. Fixture files under `tests/fixtures/specialists/validator/`. Tests fail (red).
  - [x] 5.2 Implement `src/sdlc/specialists/_validator.py` with `validate_workflow_refs` and `validate_internal_links`. Use the `_LINK_RE` / `_WIKILINK_RE` regex constants. Tests pass (green).
  - [x] 5.3 LOC cap: keep `_validator.py` ≤ 200 LOC (actual: 97 LOC).

- [x] **Task 6 — `scripts/validate_specialists.py` decision (AC7)**
  - [x] 6.1 Chose D3: defer script entirely to Story 2A.3+. Documented in `_bmad-output/implementation-artifacts/deferred-work.md`.
  - [x] 6.3 Added D3 deferral comment in `specialists/__init__.py`; debt entry in deferred-work.md.

- [x] **Task 7 — Module-boundary linter (AC9)**
  - [x] 7.1 Ran boundary linter via `pre-commit run --all-files`. `specialists/` was already in the linter table (pre-wired per epics.md). Zero new violations.
  - [x] 7.2 No linter table edit required.

- [x] **Task 8 — Quality gate full sweep (AC11)**
  - [x] 8.1 `ruff format --check && ruff check src tests` — all passed
  - [x] 8.2 `mypy --strict src` — 60 source files, no issues (pre-existing test_base.py mypy errors unchanged)
  - [x] 8.3 `pytest -q -m "not e2e"` — 1251 passed, 3 skipped, 19 pre-existing failures (chaos/property/journal/concurrency; all pre-date this story)
  - [x] 8.4 `pytest --cov=src --cov-report=term-missing --cov-fail-under=90` — 92.66% total coverage
  - [x] 8.5 `pre-commit run --all-files` — 19 hooks passed
  - [x] 8.6 `mkdocs build --strict` — built in 0.15s
  - [x] 8.7 `python scripts/freeze_wireformat_snapshots.py --check` — 5 contracts match snapshots

- [x] **Task 9 — Docs + change log**
  - [x] 9.1 `docs/architecture-overview.md` already contained the correct `specialists/` module row and boundary rules — no update needed (table was pre-authored).
  - [x] 9.2 Story file updated; Change Log entry added below.

## Dev Notes

### Critical context — DO NOT skip

Story 2A.2 is the **manifest-enforced specialist registry** that downstream Story 2A.3 (dispatcher) depends on for `dispatch_panel` to find specialists by name. Three rules:

1. **The wire-format contract `SpecialistFrontmatter` is FROZEN.** Story 1.21 locked it at `schema_version=1` with snapshot at `tests/contract_snapshots/v1/specialist_frontmatter.json`. 2A.2 does NOT amend the contract. If you find yourself editing `src/sdlc/contracts/specialist_frontmatter.py`, **stop**.
2. **Decision C3 is the load-bearing choice: explicit `agents/index.yaml` manifest, NOT filesystem walk.** The rationale (Architecture §357) is that filesystem walk causes silent skips on rename or `git mv`. Implementing a "convenience filesystem-walk fallback" defeats the choice — if `index.yaml` is missing, we fail loud. The orphan-markdown check (AC3) is the inverse safeguard: any markdown file under `agents/` that is NOT in the manifest is a build failure (catches "engineer added a file but forgot the manifest").
3. **Specialist content (markdown bodies) does NOT exist yet.** Per `epics.md:1628-1746`, the actual ~25 specialists are authored in **Stories 2B.8/2B.9/2B.10/2B.11**. 2A.2 ships the registry **infrastructure** with a minimal `index.yaml` (empty `specialists: []`). The registry must work correctly at empty state and at populated state — both are exercised by tests.

### What this story IS NOT

- It is NOT the dispatcher (that arrives in **Story 2A.3**).
- It is NOT specialist authoring (that arrives in **Stories 2B.8-2B.11**).
- It is NOT the prompt-injection corpus (that arrives in **Story 2B.4**).
- It does NOT add new Tier-1/Tier-2 e2e scenarios (the placeholder `_dispatch_panel_smoke` shim from 2A.0 is sufficient until 2A.3).
- It does NOT cover cross-refs to `skills/`, `commands/`, `workflows_yaml/` — only `agents/<name>.md` and `[[<name>]]` are in scope (AC6).

### Architecture compliance

- **Module specifications (Architecture §1056-§1071).** `specialists/` exposes `load_registry`, `validate_specialist`, `SpecialistRegistry`. Imports: `errors/`, `contracts/`, `workflows/`. Imported by: `engine/`, `dispatcher/`, `runtime/`. The diff must match this row exactly — Task 7 is the linter enforcement.
- **Boundary rule §7 (Architecture §1111).** *"`workflows/` and `specialists/` do not import `engine/`, `dispatcher/`, or `runtime/`. They are pure validators / loaders."*
- **Decision C3 (Architecture §357).** Explicit manifest discovery — no filesystem walk fallback.
- **Concern #15 (Architecture §209).** Specialist validation pipeline — frontmatter contract + cross-ref + build-time gate.
- **Pydantic strict-mode (ADR-025).** `_SpecialistManifest` and `_ManifestEntry` inherit `StrictModel`; `SpecialistFrontmatter` already does. All `model_validate(...)` calls pass `strict=True`.
- **Wire-format v1 lock (ADR-024).** `_SpecialistManifest` is private (underscore-prefixed) and explicitly NOT a wire-format contract — it is internal policy, not snapshotted. AC10 verifies the contract snapshots remain stable.
- **Cold-start budget (Architecture §488-§494).** Registry loads at `sdlc init` time. With 25 specialists × ~50ms YAML parse + frontmatter validate, cold-start adds < 1.5s — acceptable. At empty state (2A.2 ship), adds < 50ms.

### Library / framework requirements

- **PyYAML** ≥ already pinned; use `_NoDuplicateKeysLoader` (copy verbatim from `src/sdlc/runtime/mock.py:68-103`).
- **pydantic** ≥ 2.x (already pinned); `_SpecialistManifest` extends `StrictModel`.
- **`re` (stdlib)** for markdown link parsing — do NOT add `markdown-it` or `mistune`. The two regex constants are sufficient for AC6's narrow scope.
- **No new runtime dependencies introduced.**
- **Python ≥ 3.10** per `.python-version`; `from __future__ import annotations` consistently.

### File structure requirements

```
src/sdlc/specialists/                # NEW (currently does not exist)
  ├── __init__.py                    # re-export SpecialistRegistry, Specialist, load_registry, load_specialist, validate_workflow_refs, validate_internal_links
  ├── manifest.py                    # _SpecialistManifest + _ManifestEntry private models (≤ 100 LOC)
  ├── frontmatter.py                 # Specialist dataclass + load_specialist (≤ 150 LOC)
  ├── registry.py                    # SpecialistRegistry + load_registry (≤ 200 LOC)
  └── validator.py                   # validate_workflow_refs + validate_internal_links + _LINK_RE/_WIKILINK_RE (≤ 200 LOC)

src/sdlc/agents/                     # NEW directory
  ├── .gitkeep
  └── index.yaml                     # schema_version: 1; specialists: []

src/sdlc/errors/base.py              # UPDATE — add SpecialistError class

scripts/validate_specialists.py      # NEW (D1 only) OR thin shell (D2) OR deferred (D3 — debt entry)

tests/unit/specialists/              # NEW
  ├── __init__.py
  ├── test_manifest.py
  ├── test_load_specialist.py
  ├── test_registry.py
  └── test_validator.py

tests/unit/errors/test_specialist_error.py        # NEW

tests/unit/scripts/test_validate_specialists_script.py    # NEW (D1/D2 only)

tests/fixtures/specialists/                       # NEW
  ├── manifest/
  │   ├── valid_minimal.yaml
  │   ├── unknown_key.yaml
  │   ├── bad_phase.yaml
  │   ├── bad_name.yaml
  │   └── missing_file.yaml
  ├── markdown/
  │   ├── valid_minimal.md
  │   ├── no_delim.md
  │   ├── bad_yaml.md
  │   ├── bad_frontmatter.md
  │   └── name_mismatch.md
  └── validator/
      ├── workflow_refs/
      │   ├── valid.yaml
      │   ├── missing_primary.yaml
      │   ├── missing_parallel.yaml
      │   ├── missing_synthesizer.yaml
      │   ├── globs_drift.yaml
      │   └── multi_violation.yaml
      └── internal_links/
          ├── valid.md
          ├── dangling_link.md
          ├── dangling_wikilink.md
          └── multi_dangling.md
```

Mirrors:
- `src/sdlc/workflows/` (Story 2A.1) — sibling Layer 1 module; same boundary discipline.
- `src/sdlc/runtime/mock.py:68-218` — `_NoDuplicateKeysLoader` + duplicate-stem detection patterns to copy.
- `src/sdlc/contracts/specialist_frontmatter.py` — frontmatter contract (FROZEN; do not edit).

### Testing requirements

- Coverage: ≥ 90% repo-wide MUST hold; 100% on the four `specialists/*.py` modules (pure validators).
- Test marks: use `@pytest.mark.unit` (or no mark — verify project default at `pyproject.toml:212-219`).
- Test isolation: every test that constructs a `Specialist` or registry uses fixture files (do NOT inline markdown strings in test bodies — see Story 2A.0 Patch P9).
- **Anti-tautology receipt** (Story 2A.0 AC6 pattern): for AC3 orphan-markdown and AC5 cross-ref violations, manually break the test fixture once during dev (e.g., remove the orphan check in `registry.py` and verify the test fires); document the receipt in PR Change Log.

### Previous-story intelligence — what to copy + what to avoid

**Copy from Story 2A.1 (your sibling Layer 1 story):**
- The `WorkflowRegistry.load(workflows_dir)` shape — apply the SAME shape to `SpecialistRegistry.load(agents_dir)` for consistency.
- The "fail-once-with-full-list" violation pattern — if you find yourself collecting violations one-at-a-time, refactor.
- The "wire-format frozen reminder" discipline — `SpecialistFrontmatter` is frozen; `_SpecialistManifest` is private/internal.

**Copy from Story 1.13 (`MockAIRuntime`, `src/sdlc/runtime/mock.py`):**
- `_NoDuplicateKeysLoader` (lines 68-103) — copy verbatim.
- Duplicate-stem detection (`_load_fixtures` lines 191-218) — apply to manifest entry uniqueness check.

**Copy from Story 1.21 (Wire-format snapshots):**
- `scripts/freeze_wireformat_snapshots.py --check` is the gate for AC10.

**AVOID (failure modes from Epic 1 retro):**
- **Pattern 1 — Tautological tests.** Fixture-driven tests + AC3 orphan check anti-tautology receipt prevent this.
- **Pattern 4 — Pydantic lax coercion.** `StrictModel` + `strict=True`. Manifest enums (`phase: 0|1|2|3`) MUST use `Literal[0, 1, 2, 3]`; do NOT use plain `int`.
- **Pattern 5 — Review-patch volume crescendo.** LOC caps per file. Decompose proactively.
- **Pattern 6 — Linter AST blind spots.** This story does NOT extend any AST linter; the regex in `validator.py` is plain `re.finditer` (NOT an AST visitor). Stay out of `scripts/check_*.py` unless Task 7 forces a one-line table edit.

### Git intelligence — recent commits

- `0d24517 chore(process): codify per-epic prerequisites as permanent policy` — §7.4 gate cleared by 2A.1; same gate clearance applies to 2A.2.
- `8498ac3 chore(epic-2a-prep): complete DAG approvals + D1 Hypothesis byte-stability + D2 StrictModel` — D2 StrictModel is what makes manifest validation strict by default.
- `1edc2e9 feat(2a-0): implement E2E test harness` — your precursor; AC11 verifies you don't regress 2A.0 tests.
- `d2bde81 feat(1.21): wire-format v1 lock ceremony` — `SpecialistFrontmatter` snapshot reference.

### Project structure notes

- `src/sdlc/specialists/` does NOT exist yet. This story creates it.
- `src/sdlc/agents/` does NOT exist yet. This story creates it with empty manifest.
- The story shares **only** `src/sdlc/errors/base.py` with Story 2A.1 (both add a new error class). Linear-merge per CONTRIBUTING.md §3.3 — whichever PR merges first lands its error class; the second rebases on `main` and re-runs CI per team agreement (H).
- Existing wire-format tests at `tests/unit/contracts/test_specialist_frontmatter.py` (Story 1.21) cover the contract. 2A.2 adds tests for the **registry**, not the contract — do not duplicate.

### References

- [Epic 2A overview](_bmad-output/planning-artifacts/epics.md#L315) — story scope + FR/NFR coverage.
- [Story 2A.2 in epics](_bmad-output/planning-artifacts/epics.md#L1016-L1037) — source ACs.
- [Architecture §623-§632 (SpecialistFrontmatter contract)](_bmad-output/planning-artifacts/architecture.md) — frozen contract field list.
- [Architecture §357 (Decision C3)](_bmad-output/planning-artifacts/architecture.md) — explicit manifest discovery.
- [Architecture §836-§839 (specialists/ module layout)](_bmad-output/planning-artifacts/architecture.md) — file structure mandate.
- [Architecture §1064 (specialists/ module spec row)](_bmad-output/planning-artifacts/architecture.md) — public API + imports table.
- [Architecture §1073-§1112 (Module boundaries)](_bmad-output/planning-artifacts/architecture.md) — boundary rule §7 (specialists/ pure validator/loader).
- [Architecture §209 (Concern #15)](_bmad-output/planning-artifacts/architecture.md) — specialist validation pipeline rationale.
- [Architecture §715, §1043 (`scripts/validate_specialists.py`)](_bmad-output/planning-artifacts/architecture.md) — pre-commit gate placeholder.
- [Architecture §929-§935 (agents/ tree layout)](_bmad-output/planning-artifacts/architecture.md) — phase1/phase2/phase3/support directory shape.
- [PRD FR28](_bmad-output/planning-artifacts/prd.md) — ~25 specialists in markdown (authored Epic 2B).
- [Epic 2A DAG](docs/sprints/epic-2a-dag.md) — Layer 1 placement; worktree assignment (Charlie owns 2A.2).
- [ADR-024 — Wire-format v1 lock](docs/decisions/ADR-024-wire-format-v1-lock.md) — `SpecialistFrontmatter` snapshot ceremony; AC10 reference.
- [ADR-025 — Pydantic strict-mode default](docs/decisions/ADR-025-pydantic-strict-mode-default.md) — `StrictModel` discipline.
- [ADR-026 — TDD-first + Chunked-review](docs/decisions/ADR-026-tdd-first-chunked-review-workflow.md) — process gate.
- [ADR-027 — E2E test framework strategy](docs/decisions/ADR-027-e2e-test-framework-strategy.md) — Tier-1/Tier-2 regression check.
- [CONTRIBUTING.md §1-§6](CONTRIBUTING.md) — quality gate, TDD-first, worktree, chunked review, decision protocol, PR template.
- [Epic 1 Retrospective 2026-05-09](_bmad-output/implementation-artifacts/epic-1-retro-2026-05-09.md) — anti-pattern catalog.
- [Story 2A.0](_bmad-output/implementation-artifacts/2a-0-e2e-test-harness-tier-1-cli-tier-2-pipeline.md) — anti-tautology receipt format; Patch P9 (loader schema validation rationale).
- [Story 2A.1](_bmad-output/implementation-artifacts/2a-1-workflow-yaml-loader-schema-validation.md) — sibling Layer 1 story; copy `WorkflowRegistry.load(...)` shape for consistency.
- [`src/sdlc/contracts/specialist_frontmatter.py`](src/sdlc/contracts/specialist_frontmatter.py) — FROZEN contract; do not edit.
- [`src/sdlc/runtime/mock.py:68-218`](src/sdlc/runtime/mock.py) — `_NoDuplicateKeysLoader` + `_load_fixtures` patterns to copy.
- [`src/sdlc/errors/base.py`](src/sdlc/errors/base.py) — error hierarchy.
- [`tests/contract_snapshots/v1/specialist_frontmatter.json`](tests/contract_snapshots/v1/specialist_frontmatter.json) — snapshot reference.
- [`scripts/freeze_wireformat_snapshots.py`](scripts/freeze_wireformat_snapshots.py) — `--check` gate for AC10.
- [`pyproject.toml`](pyproject.toml) — pytest markers, mypy_path, ruff config, coverage threshold, hatch package_data.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Pydantic v2 strict mode subtlety: `model_validate(data, strict=True)` overrides field-level `strict=False`, blocking list→tuple coercion for `specialists` field. Fix: use `model_validate(data)` (model config handles strictness at field level).
- `Specialist` dataclass missing `phase` field: `SpecialistFrontmatter` has no `phase` field (phase is a manifest concept). Added `phase: int = 0` to `Specialist` dataclass; `load_registry` assigns `phase=entry.phase` from manifest entry.
- ruff B017 blind `pytest.raises(Exception)` required specific exception types: `FrozenInstanceError` for frozen dataclasses, `ValidationError` for pydantic frozen models.
- Fixture files originally used underscores (`valid_minimal.md`) but frontmatter `name` used hyphens (`valid-minimal`) — stem mismatch. Fixed by renaming all fixture markdown files to kebab-case.
- `test_wheel_does_not_ship_content_files` was pre-written to catch exactly this story's `agents/index.yaml` addition. Updated test to add `_ALLOWED_CONTENT_FILES` allowlist.

### Completion Notes List

- D-decision: AC7 chose D3 because validator API ships in 2A.2 but pre-commit wiring deferred to Story 2A.3+ when dispatcher integration surface stabilizes.
- `_NoDuplicateKeysLoader` copied verbatim into both `_manifest.py` and `_frontmatter.py` per AC2 spec. Triple-copy debt logged in deferred-work.md.
- Boundary linter (`scripts/check_module_boundaries.py`) already had `specialists/` configured — zero edits required (Task 7 no-op).
- `pyproject.toml` `force-include` for `src/sdlc/agents` was pre-wired — zero edits required (Task 4.4 pre-satisfied).
- Anti-tautology receipt: verified orphan check fires by temporarily commenting out the check in `_registry.py` — `test_load_registry_orphan_markdown_raises` correctly failed. Re-enabled.
- 19 pre-existing test failures (chaos, property, journal, concurrency) are unrelated to this story; confirmed same failures exist on `main` before this branch.

### File List

**New files:**
- `src/sdlc/specialists/__init__.py`
- `src/sdlc/specialists/_manifest.py`
- `src/sdlc/specialists/_frontmatter.py`
- `src/sdlc/specialists/_registry.py`
- `src/sdlc/specialists/_validator.py`
- `src/sdlc/agents/index.yaml`
- `src/sdlc/agents/.gitkeep`
- `tests/unit/specialists/__init__.py`
- `tests/unit/specialists/test_manifest.py`
- `tests/unit/specialists/test_load_specialist.py`
- `tests/unit/specialists/test_registry.py`
- `tests/unit/specialists/test_validator.py`
- `tests/unit/errors/test_specialist_error.py`
- `tests/fixtures/specialists/manifest/valid_minimal.yaml`
- `tests/fixtures/specialists/manifest/unknown_key.yaml`
- `tests/fixtures/specialists/manifest/bad_phase.yaml`
- `tests/fixtures/specialists/manifest/bad_name.yaml`
- `tests/fixtures/specialists/manifest/missing_file.yaml`
- `tests/fixtures/specialists/markdown/valid-minimal.md`
- `tests/fixtures/specialists/markdown/no-delim.md`
- `tests/fixtures/specialists/markdown/bad-yaml.md`
- `tests/fixtures/specialists/markdown/bad-frontmatter.md`
- `tests/fixtures/specialists/markdown/name-mismatch.md`
- `tests/fixtures/specialists/registry/valid_agents/index.yaml`
- `tests/fixtures/specialists/registry/valid_agents/phase1/alpha-researcher.md`
- `tests/fixtures/specialists/registry/valid_agents/phase2/beta-analyst.md`
- `tests/fixtures/specialists/registry/valid_agents/phase0/gamma-support.md`
- `tests/fixtures/specialists/registry/orphan_agents/index.yaml`
- `tests/fixtures/specialists/registry/orphan_agents/phase1/alpha-researcher.md`
- `tests/fixtures/specialists/registry/orphan_agents/phase1/orphan.md`
- `tests/fixtures/specialists/registry/missing_file_agents/index.yaml`
- `tests/fixtures/specialists/registry/duplicate_agents/index.yaml`
- `tests/fixtures/specialists/validator/workflow_refs/valid.yaml`
- `tests/fixtures/specialists/validator/workflow_refs/missing_primary.yaml`
- `tests/fixtures/specialists/validator/workflow_refs/missing_parallel.yaml`
- `tests/fixtures/specialists/validator/workflow_refs/missing_synthesizer.yaml`
- `tests/fixtures/specialists/validator/workflow_refs/globs_drift.yaml`
- `tests/fixtures/specialists/validator/workflow_refs/multi_violation.yaml`
- `tests/fixtures/specialists/validator/internal_links/dangling-link.md`
- `tests/fixtures/specialists/validator/internal_links/dangling-wikilink.md`

**Modified files:**
- `src/sdlc/errors/base.py` — added `SpecialistError`
- `src/sdlc/errors/__init__.py` — re-exported `SpecialistError`
- `tests/integration/test_wheel_build.py` — added `_ALLOWED_CONTENT_FILES` allowlist for `sdlc/agents/index.yaml`
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status: ready-for-dev → in-progress → review
- `_bmad-output/implementation-artifacts/deferred-work.md` — added D3 debt entries for Story 2A.2

## Change Log

| Date | Author | Change |
|---|---|---|
| 2026-05-10 | bmad-create-story (Claude) | Story file created via `/bmad-create-story`. Same §7.4 gate clearance as Story 2A.1 (Layer 1 sibling). Status: backlog → ready-for-dev. AC7 D-decision DEFERRED to dev-author per Decision Protocol; first line of PR Change Log MUST cite the chosen option. |
| 2026-05-10 | claude-sonnet-4-6 | Implementation complete. D-decision: AC7 chose D3 (defer script to 2A.3+). All ACs satisfied; quality gate green (92.66% coverage, ruff/mypy/pre-commit/mkdocs/snapshots all pass). Status: ready-for-dev → review. |
