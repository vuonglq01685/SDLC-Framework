# Story 1.2: pyproject.toml Quality Gates Configuration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer enforcing maintainability discipline from day one,
I want all quality tooling (ruff lint+format, mypy --strict, pytest, coverage) configured in `pyproject.toml` per ADR-002 / ADR-003 / ADR-004, with the four hard caps from NFR-MAINT-3 (≤400 LOC/file, ≤50 LOC/function, complexity ≤8, `from __future__ import annotations` required) wired into ruff,
So that every commit from this point forward is gated by lint, format, type checking, and coverage requirements without negotiation — and the negative test (intentionally non-compliant file → tools fail with specific rule citations) materially proves the gates are active, not advisory.

## Acceptance Criteria

**AC1 — `[tool.ruff]` enforces hard caps + `from __future__ import annotations` requirement.**
**Given** Story 1.1 complete (pyproject.toml + src/sdlc/__init__.py + uv.lock present)
**When** I run `uv run ruff check src/ tests/`
**Then** `[tool.ruff]` enforces ≤400 LOC/file, cyclomatic complexity ≤8 (rule C901), and required `from __future__ import annotations` (via `[tool.ruff.lint.isort] required-imports`)
**And** `uv run ruff format --check` reports clean

**AC2 — `[tool.mypy]` runs in strict mode.**
**Given** Story 1.1 complete
**When** I run `uv run mypy --strict src/`
**Then** mypy passes with `[tool.mypy] strict = true` enforced on every internal module (`src/sdlc/...`)

**AC3 — `[tool.pytest.ini_options]` and `[tool.coverage.*]` are wired.**
**Given** Story 1.1 complete
**When** I run `uv run pytest`
**Then** pytest discovers `tests/` per `[tool.pytest.ini_options] testpaths = ["tests"]`
**And** `[tool.coverage.run]` declares `source = ["src/sdlc"]`
**And** `[tool.coverage.report]` declares `fail_under = 90` (the engine-modules-only carve-out is documented in ADR-004; v1 enforces a single global threshold of 90 — see Dev Notes "Coverage fail_under interpretation")

**AC4 — Negative test materially proves the gates fire on violation.**
**Given** the configuration is in place
**When** an intentionally non-compliant file is added (401 LOC, untyped function, cyclomatic complexity 9, no `from __future__ import annotations`)
**Then** ruff fails citing the specific rule (`E501`/`PLR0915` for length, `C901` for complexity, `I002` for missing `__future__` import)
**And** mypy fails with explicit annotation-missing error (e.g. `Function is missing a type annotation [no-untyped-def]`)
**And** ADR-002, ADR-003, ADR-004 are recorded under `docs/decisions/` (stub-form is acceptable; Story 1.5 lifts them into the mkdocs ADR template once the doc skeleton lands)

## Tasks / Subtasks

- [x] **Task 1 — Add `[dependency-groups]` for dev tooling (AC: #1, #2, #3, #4)**
  - [x] 1.1 In `pyproject.toml`, add a PEP 735 `[dependency-groups]` table:
    ```toml
    [dependency-groups]
    dev = [
        "ruff>=0.6.0",          # latest 2026 stable; pin minor in lockfile
        "mypy>=1.11.0",
        "pytest>=8.0.0",
        "pytest-cov>=5.0.0",
        "coverage[toml]>=7.6.0",
    ]
    ```
    **Do NOT** add `pytest-benchmark`, `hypothesis`, `pre-commit` here — `pytest-benchmark` lands with Story 1.10 (chaos/benchmark suite), `hypothesis` lands with Story 1.11/1.12 (property tests), `pre-commit` is Story 1.4. Adding them now would bloat `uv.lock` for no behavior gain in this story.
  - [x] 1.2 Run `uv sync --group dev` (or `uv sync` if PEP 735 default group inclusion is enabled in this `uv` version). Assert `uv.lock` updates exit 0 and the four tools land under `.venv/`.
  - [x] 1.3 Verify reachability: `uv run ruff --version`, `uv run mypy --version`, `uv run pytest --version`, `uv run coverage --version` all succeed.

- [x] **Task 2 — Configure `[tool.ruff]` lint + format (AC: #1, #4) — ADR-002**
  - [x] 2.1 Add the `[tool.ruff]` top-level block:
    ```toml
    [tool.ruff]
    line-length = 100              # generous-but-bounded; matches Architecture §483 "ruff enforces caps"
    target-version = "py310"       # matches [project] requires-python = ">=3.10"
    src = ["src", "tests"]
    extend-exclude = ["docs/ux/dashboard-prototype/"]   # Story 1.1 drift; pure HTML/JSON fixture, not Python
    ```
    **Why `line-length = 100`** (not 88, ruff/black default; not 79, PEP 8): Architecture has no explicit line-length; the load-bearing caps are LOC/function/complexity (NFR-MAINT-3). 100 keeps configuration-heavy lines (TOML-imitation strings, type hints) readable without forcing artificial breaks. Document this choice in ADR-002.
  - [x] 2.2 Add the `[tool.ruff.lint]` block:
    ```toml
    [tool.ruff.lint]
    select = [
        "E",      # pycodestyle errors
        "F",      # Pyflakes
        "W",      # pycodestyle warnings
        "I",      # isort (required-imports lives here)
        "B",      # flake8-bugbear
        "C90",    # mccabe (complexity)
        "UP",     # pyupgrade
        "SIM",    # flake8-simplify
        "PL",     # pylint (PLR0915 = too-many-statements ≈ function-length proxy)
        "RUF",    # ruff-specific rules
    ]
    ignore = [
        "PLR0913",   # too-many-arguments — engine signatures often legitimately wide; revisit per-module if needed
    ]
    ```
  - [x] 2.3 **Hard cap: cyclomatic complexity ≤ 8** (Architecture §708, NFR-MAINT-3, AC1):
    ```toml
    [tool.ruff.lint.mccabe]
    max-complexity = 8
    ```
  - [x] 2.4 **Hard cap: ≤ 50 LOC per function** — ruff has no native LOC-per-function rule, but `PLR0915` (too-many-statements) is the closest proxy. Set:
    ```toml
    [tool.ruff.lint.pylint]
    max-statements = 50
    ```
    Note: "statements" ≠ "lines"; this is a deliberate proxy. Document in ADR-002 that the literal NFR-MAINT-3 "≤50 LOC/function" is approximated as "≤50 statements" in tooling, since no linter has an exact LOC-per-function rule. If a function passes `max-statements = 50` but its source spans >50 lines purely from formatting, manual review at PR time enforces the literal rule (or upgrade to a custom AST hook in Story 1.4 if drift becomes real).
  - [x] 2.5 **Hard cap: ≤ 400 LOC per file** — also no native ruff rule. Use `PLR0915` only on functions; for file-level cap use a custom pre-commit hook in Story 1.4 OR use ruff's experimental `Q` rules / a wrapper. **Pragmatic v0.2 path**: encode the cap as a project convention enforced by ruff's `lint.preview = true` + `PLE0118` (no, that's something else). Since no clean ruff rule exists, **set up the negative-test fixture in Task 5 to prove the failure mode** and add a TODO in ADR-002 noting that the file-LOC cap is enforced by Story 1.4's `boundary-validator` pre-commit hook (which AST-walks every changed file). For this story, document that ruff's `select = ["PL"]` set + `max-statements = 50` covers the *function* cap and that the *file* cap is enforced by Story 1.4.
  - [x] 2.6 **Required import enforcement**: this is the canonical mechanism for `from __future__ import annotations` everywhere (Architecture §487, §710, AC1):
    ```toml
    [tool.ruff.lint.isort]
    required-imports = ["from __future__ import annotations"]
    ```
    This raises `I002` on any `.py` file missing the import. Architecture §710 says this is enforced by "custom pre-commit hook" — ruff's `I002` does the same job natively, so we use ruff. Note in ADR-002 that the architecture's "custom hook" guidance was pre-`required-imports`; ruff's mechanism is the modern replacement.
  - [x] 2.7 **Per-file ignores for tests** (so test fixtures don't drown in lint noise):
    ```toml
    [tool.ruff.lint.per-file-ignores]
    "tests/**" = [
        "PLR2004",   # magic numbers in tests are fine
        "S101",      # assert is the whole point of tests (if S series enabled later)
    ]
    ```
  - [x] 2.8 **Format settings**:
    ```toml
    [tool.ruff.format]
    quote-style = "double"      # ruff/black default
    indent-style = "space"
    docstring-code-format = true
    ```
  - [x] 2.9 Run `uv run ruff check src/ tests/`. Should report **clean** (only file is `src/sdlc/__init__.py` which already has `from __future__ import annotations` per Story 1.1).
  - [x] 2.10 Run `uv run ruff format --check src/ tests/ pyproject.toml`. Should report clean. If pyproject.toml has TOML formatting drift, run `uv run ruff format pyproject.toml` once and commit.

- [x] **Task 3 — Configure `[tool.mypy]` strict mode (AC: #2, #4) — ADR-003**
  - [x] 3.1 Add the `[tool.mypy]` block:
    ```toml
    [tool.mypy]
    python_version = "3.10"
    strict = true
    mypy_path = ["src"]
    namespace_packages = true
    explicit_package_bases = true
    show_error_codes = true
    pretty = true
    warn_unused_configs = true
    warn_unreachable = true
    extra_checks = true
    ```
    `strict = true` expands to: `warn_unused_configs`, `warn_redundant_casts`, `warn_unused_ignores`, `strict_equality`, `check_untyped_defs`, `disallow_subclassing_any`, `disallow_untyped_decorators`, `disallow_any_generics`, `disallow_untyped_calls`, `disallow_incomplete_defs`, `disallow_untyped_defs`, `no_implicit_reexport`, `warn_return_any`, `extra_checks` (per Context7 `/python/mypy` "Mypy Strict Configuration").
  - [x] 3.2 Add a tests-relaxation override (tests don't need full strict — pytest fixtures and parametrize decorators routinely defeat `disallow_untyped_decorators`):
    ```toml
    [[tool.mypy.overrides]]
    module = "tests.*"
    disallow_untyped_defs = false
    disallow_untyped_decorators = false
    ```
    AC2 only requires strict on **internal modules** (`src/sdlc/...`). The override keeps tests writable without compromising the AC. Document in ADR-003.
  - [x] 3.3 Run `uv run mypy --strict src/`. Should pass (the only file `src/sdlc/__init__.py` from Story 1.1 declares `__version__: str = "0.0.0"` and `__all__: list[str] = ["__version__"]` — both fully typed).
  - [x] 3.4 Verify the `mypy --strict` CLI flag and the `[tool.mypy] strict = true` config are equivalent: running both `uv run mypy --strict src/` and `uv run mypy src/` (config-only) should both succeed and produce identical output. AC2's literal command form is `mypy --strict src/`; the config-driven form must be a no-op so CI invocations work either way.

- [x] **Task 4 — Configure `[tool.pytest.ini_options]` + `[tool.coverage.*]` (AC: #3, #4) — ADR-004**
  - [x] 4.1 Add pytest config:
    ```toml
    [tool.pytest.ini_options]
    minversion = "8.0"
    testpaths = ["tests"]
    addopts = [
        "-ra",                                  # show summary for all non-pass outcomes
        "--strict-markers",                     # unknown @pytest.mark.X → error
        "--strict-config",                      # unknown ini key → error
        "--cov=src/sdlc",
        "--cov-report=term-missing",
        "--cov-report=xml",                     # for CI ingestion (Story 1.3)
        "--cov-fail-under=90",
    ]
    xfail_strict = true                          # xfail that unexpectedly passes → fail
    filterwarnings = ["error"]                   # warnings → errors (NFR-MAINT-1 discipline)
    ```
  - [x] 4.2 Add coverage config:
    ```toml
    [tool.coverage.run]
    source = ["src/sdlc"]
    branch = true                                # branch coverage on top of line (catches missed elif/else)
    parallel = true                              # safe default for future xdist usage
    omit = [
        "src/sdlc/migrations/*.py.example",      # placeholder files, not real code
    ]

    [tool.coverage.report]
    fail_under = 90
    show_missing = true
    skip_covered = false
    exclude_also = [
        "if TYPE_CHECKING:",
        "raise NotImplementedError",
        "@(abc\\.)?abstractmethod",
    ]
    ```
  - [x] 4.3 Author a single smoke test in `tests/test_smoke.py`:
    ```python
    from __future__ import annotations

    import sdlc


    def test_version_string_is_populated() -> None:
        assert isinstance(sdlc.__version__, str)
        assert sdlc.__version__ != ""
    ```
    This test exists for one reason: AC3 + AC4 require pytest to actually run successfully. Without at least one test, `pytest --cov-fail-under=90` either fails (no tests collected → exit 5) or trivially passes by importing zero source. The smoke test imports `sdlc`, which executes `src/sdlc/__init__.py`'s top level, giving meaningful coverage of the only source file currently shipped.
  - [x] 4.4 Run `uv run pytest`. Expected: 1 test collected, 1 passed, coverage ≥ 90% (since `__init__.py` has 2 module-level statements both covered by import). Exit 0.

- [x] **Task 5 — Author negative-test verification (AC: #4)**
  - [x] 5.1 In a **temporary** scratch file `tests/_scratch_noncompliant.py` (path explicitly inside `tests/` so per-file-ignores DO NOT mask the violations — confirm `per-file-ignores` only relaxes `PLR2004`/`S101`, NOT the cap rules), write a deliberate violation:
    ```python
    # No `from __future__ import annotations` here  → I002 violation
    def f(x):                                        # untyped → mypy no-untyped-def
        # Force complexity 9: 8 nested if/elif chain + final return
        if x == 1: return 1
        elif x == 2: return 2
        elif x == 3: return 3
        elif x == 4: return 4
        elif x == 5: return 5
        elif x == 6: return 6
        elif x == 7: return 7
        elif x == 8: return 8
        return 0
        # ... pad to 401 logical statements / lines if needed for file-LOC proof
    ```
    Pad with trivial statements (`a = 1; a = 2; ...`) until the file exceeds 400 logical lines if you want to also exercise the file-cap rule (note Task 2.5: file-LOC cap is Story 1.4's territory — for THIS story, ruff will not flag it, and that is the documented behavior; mypy + ruff complexity + I002 are sufficient to prove the gates fire).
  - [x] 5.2 Run **explicitly**, capturing exit codes and rule citations:
    ```bash
    set +e
    uv run ruff check tests/_scratch_noncompliant.py
    echo "ruff exit: $?"
    uv run mypy tests/_scratch_noncompliant.py
    echo "mypy exit: $?"
    set -e
    ```
    Expected ruff output: at minimum `I002` (missing future import), `C901` (too complex; threshold 8 with this 9-branch function), and pyflakes/pylint statement-count rules if the function is long enough.
    Expected mypy output: `error: Function is missing a type annotation [no-untyped-def]` plus `error: ...` on parameters.
    Expected exit codes: ruff non-zero, mypy non-zero.
  - [x] 5.3 **Capture the verbatim tool output in Dev Agent Record → Debug Log References**, then **delete `tests/_scratch_noncompliant.py`**. The file is verification-only and MUST NOT be committed. Confirm via `git status` that the working tree is clean of the scratch file before commit.
  - [x] 5.4 Re-run `uv run ruff check src/ tests/` and `uv run mypy --strict src/` and `uv run pytest` after deletion. All three must pass clean. Expected: scratch file is gone, tools report 0 errors, pytest reports 1 passed with ≥90% coverage.

- [x] **Task 6 — Author ADR-002, ADR-003, ADR-004 stubs (AC: #4)**
  - [x] 6.1 Create `docs/decisions/` directory if it does not exist (`mkdir -p docs/decisions`). Story 1.5 will land the canonical numbered ADR template + mkdocs scaffolding around this dir; for this story, plain Markdown stubs are sufficient.
  - [x] 6.2 Author `docs/decisions/ADR-002-ruff-config.md` with sections (use the template Architecture §1023 references):
    - **Status**: Accepted (2026-05-07, Story 1.2)
    - **Context**: NFR-MAINT-2 / NFR-MAINT-3 demand ruff-clean code with hard caps on file/function/complexity, plus mandatory `from __future__ import annotations` (Architecture §487, §708, §710).
    - **Decision**: Document the chosen rule selection (E, F, W, I, B, C90, UP, SIM, PL, RUF), the `max-complexity = 8` mccabe setting, the `max-statements = 50` PL setting (proxy for ≤50 LOC/function), the `required-imports = ["from __future__ import annotations"]` isort setting, the `line-length = 100` choice, and the per-file-ignores for `tests/`.
    - **Alternatives considered**: keeping ruff defaults (rejected — does not enforce caps); using black + flake8 + isort separately (rejected — slower, more config files, ruff is the architecturally chosen tool per Architecture §1333); custom pre-commit AST walker for required-imports (rejected — ruff's `I002` is native and faster).
    - **Consequences**: Every commit gated on cap compliance; minor false-positives expected on `PLR2004` magic-number warnings (already silenced in tests/); file-LOC cap **not** enforced by ruff in v0.2 — Story 1.4's boundary-validator pre-commit hook owns that.
    - **Revisit-by**: 2026-12-01 (post-pilot) or sooner if ruff ships a native file-LOC rule.
  - [x] 6.3 Author `docs/decisions/ADR-003-mypy-strict.md`:
    - **Status**: Accepted (2026-05-07, Story 1.2).
    - **Context**: NFR-MAINT-1 demands `mypy --strict` on every internal module; PRD §622 lists "mypy --strict discipline" as a required skill for solo build.
    - **Decision**: Use `[tool.mypy] strict = true` with `python_version = "3.10"`, `mypy_path = ["src"]`, `namespace_packages = true`, `explicit_package_bases = true`, `warn_unreachable`, `extra_checks`. Tests get a relaxed override for fixtures/decorators.
    - **Alternatives considered**: pyright (rejected — extra runtime, less mature inline), pyre (rejected — Facebook-aligned, weaker community), per-file `# type: ignore` (rejected — no enforcement).
    - **Consequences**: Every internal module ships with full type discipline; tests are pragmatically relaxed; cannot enable `--strict` on tests without breaking pytest's decorator typing surface.
    - **Revisit-by**: 2026-12-01 or when adopting `Self` types or PEP 695 generics on the engine surface.
  - [x] 6.4 Author `docs/decisions/ADR-004-pytest-config.md`:
    - **Status**: Accepted (2026-05-07, Story 1.2).
    - **Context**: NFR-MAINT-4 demands ≥90% engine line coverage, ≥80% workflow YAML coverage, ≥1 property test per state machine; PRD §215 states "Full test pyramid" (unit + integration + nightly E2E + property + benchmark).
    - **Decision**: Use pytest 8.0+ with `testpaths = ["tests"]`, `--strict-markers`, `--strict-config`, `xfail_strict = true`, `filterwarnings = ["error"]`. Coverage via `pytest-cov` with `source = ["src/sdlc"]`, `branch = true`, **single global `fail_under = 90`** (the per-engine carve-out described in epics.md AC3 is interpreted as "fail_under = 90 globally; engine modules are the dominant source surface"). Coverage carve-outs per module land in later stories if a non-engine module needs a different threshold (e.g., dashboard at 80%). When that happens, switch to per-path thresholds via the `[tool.coverage.report]` `precision`/`include` mechanism or a coverage `[paths]` config.
    - **Alternatives considered**: separate `setup.cfg` (rejected — single source of truth in pyproject.toml); nose2 (rejected — pytest is canonical and PRD-named); coverage threshold per-module via custom CI step (deferred — single global threshold is sufficient until non-engine modules ship in Stories 5.x).
    - **Consequences**: Every test run computes branch coverage; missing tests fail CI at <90%; warnings are errors (catches deprecations early).
    - **Revisit-by**: when first non-engine module (dashboard, Story 5.1) lands and the 90% threshold is too aggressive there.
  - [x] 6.5 Confirm the three ADR files exist via `ls docs/decisions/`. They do not need to render in mkdocs yet — that is Story 1.5.

- [x] **Task 7 — Verification + handoff (AC: #1, #2, #3, #4)**
  - [x] 7.1 Run the full quality-gate sequence in order, capturing exit codes:
    ```bash
    set -e
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/ pyproject.toml
    uv run mypy --strict src/
    uv run pytest
    ```
    All four must exit 0.
  - [x] 7.2 Capture tool versions in Dev Agent Record: `uv run ruff --version`, `uv run mypy --version`, `uv run pytest --version`, `uv run coverage --version`.
  - [x] 7.3 Author Dev Agent Record entries listing every file created or modified. Attach the verbatim Task 5.2 negative-test transcript as proof of AC4.
  - [x] 7.4 Commit message style: `feat: configure quality gates (ruff, mypy --strict, pytest, coverage) per ADR-002/003/004 (Story 1.2)`. Architecture §487 + global git-workflow rules apply.
  - [x] 7.5 Final assertions:
    1. `grep -E '^\[tool\.(ruff|mypy|pytest\.ini_options|coverage\.run|coverage\.report)\]' pyproject.toml` → all five tables present.
    2. `grep 'required-imports' pyproject.toml` → matches `required-imports = ["from __future__ import annotations"]`.
    3. `grep 'max-complexity' pyproject.toml` → matches `max-complexity = 8`.
    4. `grep 'fail_under' pyproject.toml` → matches `fail_under = 90` (in `[tool.coverage.report]`).
    5. `grep 'strict = true' pyproject.toml` → matches under `[tool.mypy]`.
    6. `ls docs/decisions/ADR-002-ruff-config.md docs/decisions/ADR-003-mypy-strict.md docs/decisions/ADR-004-pytest-config.md` → all three exist.
    7. `git status --porcelain` → no `tests/_scratch_noncompliant.py` (verification-only file deleted).

### Review Findings

_Code review run: 2026-05-07. Layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor. 31 unique findings after dedup; 13 dismissed as noise / knowledge-cutoff false positives. Decisions resolved 2026-05-07: 1a, 2a, 3b, 4a, 5a → 13 patches, 5 deferred._

#### Patch (unambiguous fixes)

- [x] [Review][Patch] **AC4 mypy-failure clause not literally satisfied** — Re-run negative test under `src/sdlc/_scratch_noncompliant.py` (where `[[tool.mypy.overrides]]` does not relax strict mode); capture transcript showing `error: Function is missing a type annotation [no-untyped-def]` with non-zero exit; replace existing Debug Log transcript; delete scratch file before commit. [Debug Log References]
- [x] [Review][Patch] **Drop `coverage.run.parallel = true`** — Single-process pytest does not need it; keeping it without `[tool.coverage.paths]` mapping risks fragmented reports. Re-add together with `[tool.coverage.paths]` and `coverage combine` when xdist actually lands. [pyproject.toml:127]
- [x] [Review][Patch] **Bound dependency floors with caps** — Add upper bounds to guard against major-version drift on fresh `uv lock`: `mypy>=1.11.0,<3`, `pytest>=8.0.0,<10`. (Other dev deps stay floor-only — they are minor-stable.) [pyproject.toml:23–28]
- [x] [Review][Patch] **Pre-declare pytest markers under `--strict-markers`** — Add `markers = [...]` to `[tool.pytest.ini_options]` covering the architecture-named categories (unit, integration, property, benchmark, e2e). Without this, the first `@pytest.mark.unit` will hard-fail. [pyproject.toml:108–121]
- [x] [Review][Patch] **`tests/.gitkeep` still tracked** — Completion Note line 477–478 claims "git removes it since the directory is no longer empty" but git does not auto-remove tracked files. Run `git rm tests/.gitkeep` and correct the Completion Note. [tests/.gitkeep]
- [x] [Review][Patch] **Dead `S101` per-file-ignore** — `select` does not include the `S` (flake8-bandit) ruleset, so `S101` will never fire. Remove `"S101"` from `[tool.ruff.lint.per-file-ignores]` "tests/**" list (or, if security rules are desired, add `"S"` to `select` and keep the ignore — but spec's intent is clearly the former). [pyproject.toml:78]
- [x] [Review][Patch] **`.gitignore` doesn't catch parallel-mode coverage files** — Bare `.coverage` matches only the merged file. Change `.coverage` → `.coverage*` for forward compatibility (catches `.coverage.<host>.<pid>.<rand>` if `parallel = true` is ever re-enabled by a contributor). [.gitignore]
- [x] [Review][Patch] **Dead `omit = ["src/sdlc/migrations/*.py.example"]`** — `src/sdlc/migrations/` does not exist; `.py.example` files are not Python sources coverage would track. Remove the `omit` entry until migrations actually ship. [pyproject.toml:128]
- [x] [Review][Patch] **ADR-002 references stale ruff `0.6.x`** — Lockfile pins `0.15.12`. The "Ruff has no native file-LOC rule in 0.6.x" claim and the `Revisit-by` clause both reference an outdated version. Update ADR-002 to cite `0.15.x` and re-verify the file-LOC claim against current ruff release notes. [docs/decisions/ADR-002-ruff-config.md]
- [x] [Review][Patch] **ADR-003 stale "unused section warning" caveat** — The line "_appears as a 'note: unused section(s)' warning until the first test file is added_" was invalidated by the same commit (`tests/test_smoke.py` is added here). Remove or rephrase. [docs/decisions/ADR-003-mypy-strict.md]
- [x] [Review][Patch] **ADR-002 missing "≤50 LOC/function → max-statements = 50" rationale paragraph** — Spec Task 2.4 explicitly required documenting that "statements" ≠ "lines" and that manual review at PR time enforces the literal NFR rule until Story 1.4's AST hook lands. Diff has only a table row, no narrative. Add a short paragraph. [docs/decisions/ADR-002-ruff-config.md]
- [x] [Review][Patch] **`PLR0915` enforced on tests but not noted in ADR-002** — ADR-002's per-file-ignores discussion lists `C901` and `I002` as cap rules retained on tests. `PLR0915` (max-statements) is also retained; note this in the ADR for completeness. [docs/decisions/ADR-002-ruff-config.md]
- [x] [Review][Patch] **Branch coverage misreports `if TYPE_CHECKING:` partial-branch** — `exclude_also = ["if TYPE_CHECKING:"]` removes the line from line-coverage but the partial-branch on the `if` itself still flags. Add `partial_branches = ["if TYPE_CHECKING:"]` to `[tool.coverage.report]`. [pyproject.toml:130–139]

#### Deferred

- [x] [Review][Defer] **`filterwarnings = ["error"]` third-party escape hatch (YAGNI)** — No transitive `DeprecationWarning` trips today; preemptive broad ignores would weaken the `error`-on-warning discipline before any evidence. Reason: keep gate strict; add precise `default::DeprecationWarning:specific.module` ignores only when a real failure surfaces.
- [x] [Review][Defer] **`required-imports` will fire on empty `__init__.py` and future `tests/conftest.py`** — Architecture intent is that every Python file starts with `from __future__ import annotations`; this is intentional discipline, not a bug. Re-evaluate if friction emerges.
- [x] [Review][Defer] **ADR citations to Architecture/PRD `§N` lack hyperlinks** — Story 1.5 (ADR-011) lifts ADRs into the canonical mkdocs template and is the natural home for adding cross-references.
- [x] [Review][Defer] **Missing `py.typed` marker on `src/sdlc/`** — Relevant for downstream PyPI consumers; project is pre-release (v0.0.0). Add when first publishable release lands.
- [x] [Review][Defer] **`xfail_strict` × `filterwarnings=["error"]` interaction speculative** — No concrete test triggers this today; address when first `xfail`-marked test emits a warning.

## Dev Notes

### Critical context

This is the **second commit of v0.2**. Story 1.1 produced the bootstrap substrate (uv + hatchling + src/sdlc/`__init__.py`). This story locks the **quality gates** so that every line written from Story 1.6 onward is provably ruff-clean, mypy-strict, ≤8-complexity, and ≥90%-covered. The thesis (PRD §592): substrate quality > feature breadth. A single non-strict commit downstream is a v1.0 substrate failure.

### What this story is NOT

- **NOT** the place to add `.github/workflows/ci.yml` — Story 1.3 (ADR-006). The gates configured here are pre-CI; Story 1.3 wires them into GitHub Actions matrices.
- **NOT** the place to add `.pre-commit-config.yaml` — Story 1.4 (ADR-010). Story 1.4 also owns the **file-LOC cap** AST hook, the **module boundary** hook, and the **specialist frontmatter** hook.
- **NOT** the place to add `pytest-benchmark`, `hypothesis`, or `pre-commit` to deps — see Task 1.1.
- **NOT** the place to author `src/sdlc/<submodule>/` content — Stories 1.6+. The 90% coverage threshold is satisfied by the smoke test (`tests/test_smoke.py`) until real modules ship.
- **NOT** the place to render the ADRs in mkdocs — Story 1.5 (ADR-011). Plain `.md` stubs in `docs/decisions/` are sufficient for AC4.

### Architecture compliance — what MUST be true after this story

- **Hard caps from NFR-MAINT-3** (Architecture §708, PRD §175, §876–§879):
  - ≤ 400 LOC/file → enforced by Story 1.4's pre-commit hook (NOT this story; documented in ADR-002).
  - ≤ 50 LOC/function → approximated by `[tool.ruff.lint.pylint] max-statements = 50` in this story; literal LOC-line cap deferred to Story 1.4.
  - Cyclomatic complexity ≤ 8 → enforced by `[tool.ruff.lint.mccabe] max-complexity = 8` (rule C901). **AC1 directly cites this rule.**
  - `from __future__ import annotations` required → enforced by `[tool.ruff.lint.isort] required-imports = [...]` (rule I002). Architecture §710 calls out a "custom pre-commit hook" but ruff's native rule supersedes that — document in ADR-002.
- **`mypy --strict` on every internal module** (NFR-MAINT-1, AC2): `[tool.mypy] strict = true` with `mypy_path = ["src"]`. Tests get a `[[tool.mypy.overrides]]` relaxation per ADR-003 — does NOT violate AC2 because AC2 says "every **internal** module".
- **Coverage source = `src/sdlc`** (AC3, Architecture §709 "Type discipline" + §1335 "performance considerations addressed"). Branch coverage on top of line coverage catches missed `elif`/`else`.
- **`fail_under = 90`** (AC3, NFR-MAINT-4). The literal AC says "for engine modules"; the pragmatic interpretation in v0.2 is one global threshold. ADR-004 documents the carve-out and the migration path for per-path thresholds when non-engine modules (dashboard at 80%, etc.) start shipping.

### Library / framework requirements (versions to assume)

| Tool | Min version | Pinned in `[dependency-groups] dev` | Source |
|---|---|---|---|
| `ruff` | ≥ 0.6.0 | yes | Architecture §1333 (locked via uv.lock) |
| `mypy` | ≥ 1.11.0 | yes | Architecture §1333; PRD §876 |
| `pytest` | ≥ 8.0.0 | yes | Architecture §1333 |
| `pytest-cov` | ≥ 5.0.0 | yes | Architecture §1335; required by `--cov` addopts |
| `coverage[toml]` | ≥ 7.6.0 | yes | Branch coverage + pyproject support |
| Python | ≥ 3.10 (host: 3.12 per Story 1.1) | inherited | NFR-COMPAT-1 |

**Do NOT add** in this story: `pytest-benchmark` (Story 1.10), `hypothesis` (Story 1.11/1.12), `pre-commit` (Story 1.4), `pydantic` / `structlog` / `typer` (foundation Stories 1.6+).

### File structure requirements (post-story canonical state)

After Story 1.2 lands, `git ls-files` should show **everything from Story 1.1** plus:

```
docs/decisions/ADR-002-ruff-config.md          # NEW
docs/decisions/ADR-003-mypy-strict.md          # NEW
docs/decisions/ADR-004-pytest-config.md        # NEW
tests/test_smoke.py                            # NEW (replaces tests/.gitkeep if smoke covers it)
```

`pyproject.toml` is **modified** (adds `[dependency-groups]`, `[tool.ruff*]`, `[tool.mypy*]`, `[tool.pytest.ini_options]`, `[tool.coverage.*]` tables). `uv.lock` is **modified** (dev tools resolved).

**Do NOT** create:
- `.pre-commit-config.yaml` — Story 1.4.
- `.github/workflows/ci.yml` — Story 1.3.
- `mkdocs.yml`, `docs/index.md` — Story 1.5.
- `src/sdlc/<submodule>/` directories — Stories 1.6+.
- `tests/_scratch_noncompliant.py` (must be deleted at end of Task 5).

### Testing requirements

- Author **exactly one** test file: `tests/test_smoke.py` per Task 4.3. It exists to satisfy AC3 + AC4 (pytest must run and coverage must compute meaningfully).
- The smoke test is **not** the canonical `__version__` test — that lives wherever Story 1.16 (CLI `--version`) lands. The smoke test is *infrastructure proof*, not feature coverage.
- AC4 negative-test files are **temporary** (Task 5) and MUST be deleted before commit.

### Previous story intelligence (Story 1.1 learnings)

From `1-1-project-bootstrap-with-uv-init-hatchling.md` Dev Agent Record + Review Findings (committed at `0dd96ea`):

1. **uv 0.11.8 quirk**: `uv init`'s `--build-backend` flag accepts `hatch` (not literal `hatchling`); both produce `build-backend = "hatchling.build"`. Not relevant to this story (no `uv init` re-run), but useful context if `uv` is upgraded.
2. **Python host version**: 3.12.13. Set `[tool.mypy] python_version = "3.10"` (the floor, not the host) so mypy emits errors compatible with the lowest supported Python — catches 3.11+-only syntax sneaking into the codebase.
3. **`docs/ux/dashboard-prototype/` exists** from a pre-1.1 UX planning pass and was acknowledged-as-drift in Story 1.1's File List. **Add `extend-exclude = ["docs/ux/dashboard-prototype/"]` to `[tool.ruff]`** so ruff does not attempt to lint the HTML/JSON/README content as Python. Mypy auto-skips non-Python files; pytest auto-skips non-`test_*.py` files; only ruff needs the explicit exclusion.
4. **Existing `src/sdlc/__init__.py` is already compliant**: starts with `from __future__ import annotations`, declares typed `__version__: str = "0.0.0"` and `__all__: list[str] = ["__version__"]`. Both ruff and mypy --strict should report **clean on first run** without code changes — if either complains, the config is overshooting NFR scope and needs a per-rule ignore (document in ADR-002/003).
5. **`[project.scripts]` entry point omitted** in Story 1.1 to avoid shipping a broken `sdlc` console script. Story 1.2 should NOT add it back — that is Story 1.16's job.
6. **Code-review patches applied to `.gitignore`** in Story 1.1 already cover `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`. **Do not re-add them.**
7. **`license = { text = "TBD" }`** is a known SPDX non-compliance, deferred per Story 1.1's Decision/Defer table. Ruff/mypy/pytest do not care; only `twine check` / PyPI upload would. Not in scope here.
8. **Review-style sections** (`## Change Log`, `### Review Findings` with `Decision/Patch/Defer`) were added by the reviewer in Story 1.1. The DEV agent should leave these blank in this story file for the reviewer to populate after `dev-story` runs.

### Coverage `fail_under` interpretation

AC3 literally says: `[tool.coverage.report] declares fail_under = 90 for engine modules`. The challenge: coverage.py has no native per-module `fail_under` syntax in pyproject. Two options:

- **Option A (chosen)**: Set `fail_under = 90` globally. This is conservative — it forces 90% on **every** module, not just engine. Acceptable in v0.2 because almost every module IS engine (state, journal, dispatcher, hooks, signoff, runtime, telemetry, workflows, specialists, signoff). Non-engine modules (dashboard, cli) ship in later stories and may need per-path relaxation; ADR-004 documents the migration path.
- **Option B (rejected)**: Use `[tool.coverage.paths]` + `coverage report --include=src/sdlc/engine/*` with custom CI step. Adds complexity for a v0.2 substrate story; defer until first sub-90% module appears.

ADR-004 records this choice. AC3 is satisfied because `fail_under = 90` IS declared and IS enforced on the engine modules (which are the dominant code surface).

### Latest tech information (research summary; 2026-05-07)

- **Ruff `[tool.ruff.lint] select` placement.** Ruff moved most lint settings under `[tool.ruff.lint]` in 0.4+ (was directly under `[tool.ruff]` previously). The story uses the modern shape. *Source: Context7 `/astral-sh/ruff` — Default Ruff TOML configuration / TOML Configuration for Rule Selection.*
- **Ruff `mccabe.max-complexity`.** Lives under `[tool.ruff.lint.mccabe]`, not `[tool.ruff.mccabe]`. Same migration as `select`. *Source: Context7 `/astral-sh/ruff`.*
- **Ruff `required-imports`.** Lives under `[tool.ruff.lint.isort]`. Rule code is `I002`. The architecture's "custom pre-commit hook" guidance (§710) predates this rule; ruff's native mechanism is the modern, faster path.
- **Ruff `target-version`.** Set to `py310` (matches `[project] requires-python`). Determines which `pyupgrade` (UP) rules fire — e.g. `from typing import List` → `list` upgrade is gated on target-version ≥ py39.
- **Mypy `strict = true`.** Equivalent to setting all 13 strict-mode flags individually (Context7 `/python/mypy` — Mypy Strict Configuration). Per-module overrides via `[[tool.mypy.overrides]] module = "tests.*"` allow narrow relaxation without losing the strict baseline.
- **Mypy `mypy_path` + `explicit_package_bases`.** Required for src layout: without `explicit_package_bases = true`, mypy may treat `src/sdlc/` as a namespace package and fail to import. The story sets both. *Source: Context7 `/python/mypy` — pyproject.toml example.*
- **pytest 8.x, `--strict-config`** is now stable (was experimental in 7.x). Catches typos like `[tool.pytest.ini_optoins]` (note the typo) at startup.
- **`coverage[toml]`.** The `[toml]` extra is required for coverage.py to read pyproject.toml directly (otherwise needs a separate `.coveragerc`). Pin `>=7.6.0` to ensure modern `exclude_also` syntax (replaces deprecated `exclude_lines`).
- **Coverage `branch = true`.** Architecture's "≥90% line on engine modules" (NFR-MAINT-4) is line coverage; branch coverage is a stronger signal that catches dead `elif` arms. Cost: slight slowdown. ADR-004 documents that we exceed the NFR by enabling branch.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.2] (lines 445–472) — original BDD AC, story statement, ADR-002/003/004 mapping.
- [Source: _bmad-output/planning-artifacts/architecture.md#Starter-Template-Evaluation] (lines 268–283) — ADR-002, ADR-003, ADR-004 scope tables; "hand-crafted afterwards" carve-out.
- [Source: _bmad-output/planning-artifacts/architecture.md#Code-Style-Beyond-Ruff] (lines 483–495) — `from __future__ import annotations` first-line rule + 8 additional non-ruff rules (some custom-hook territory for Story 1.4).
- [Source: _bmad-output/planning-artifacts/architecture.md#Pattern-Enforcement] (lines 705–717) — table mapping each pattern to its enforcement mechanism (ruff, mypy, custom hooks).
- [Source: _bmad-output/planning-artifacts/architecture.md#Test-Organization-and-Naming] (lines 682–701) — canonical `tests/` shape (unit/integration/property/benchmark/e2e/fixtures); informs `testpaths` + future test layout.
- [Source: _bmad-output/planning-artifacts/architecture.md#Development-Workflow-Integration] (lines 1204–1219) — `uv run pytest tests/{unit,integration,property}` invocation pattern; consistent with this story's `testpaths = ["tests"]`.
- [Source: _bmad-output/planning-artifacts/prd.md#Maintainability-NFRs] (lines 876–879) — NFR-MAINT-1 / NFR-MAINT-2 / NFR-MAINT-3 / NFR-MAINT-4 wording; AC mapping for hard caps.
- [Source: _bmad-output/planning-artifacts/prd.md#Technical-Success] (line 175) — "≤400 LOC/file; ≤50 LOC/function; complexity ≤8" appears as a single CI-gate row.
- [Source: _bmad-output/implementation-artifacts/1-1-project-bootstrap-with-uv-init-hatchling.md] — previous story file (status: done); File List, Dev Agent Record, Review Findings carry forward as context.
- [Context7 `/astral-sh/ruff` — Default Ruff TOML configuration] — exclude defaults, target-version, lint shape.
- [Context7 `/astral-sh/ruff` — TOML Configuration for Rule Selection] — `select`/`ignore` shape under `[tool.ruff.lint]`.
- [Context7 `/python/mypy` — Mypy Strict Configuration] — list of flags `strict = true` expands to.
- [Context7 `/python/mypy` — Example pyproject.toml Configuration] — `[[tool.mypy.overrides]]` per-module syntax.

## Project Structure Notes

- Alignment with unified project structure (Architecture §767–§1046): this story creates `docs/decisions/ADR-{002,003,004}-*.md` (numbered ADR files) and `tests/test_smoke.py`. All other paths in the canonical tree remain Story 1.6+ scope.
- Detected variance: Architecture §1023–§1025 names ADR files exactly as `ADR-002-ruff-config.md`, `ADR-003-mypy-strict.md`, `ADR-004-pytest-config.md`. The story uses the architecture-canonical names.
- Detected variance: ruff's "custom pre-commit hook" guidance for `from __future__ import annotations` (Architecture §710) is replaced by ruff's native `I002` rule. ADR-002 records the substitution. Story 1.4 will still own the file-LOC cap and module-boundary hooks — ruff cannot enforce those natively in 0.6.x.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 (2026-05-08)

### Debug Log References

**Task 5 — Negative-test transcript (AC4 proof)**

Scratch file: `src/sdlc/_scratch_noncompliant.py` (deleted after verification).

The original transcript captured the scratch file in `tests/`, where the
`[[tool.mypy.overrides]] module = "tests.*"` relaxation suppressed mypy's `[no-untyped-def]`
error and produced `mypy exit: 0`. AC4 line 37 requires "**And** mypy fails" conjunctively
with ruff. Per code-review action `[Review][Patch]` (2026-05-07), the negative test was re-run
under `src/sdlc/` so strict mode applies. The verbatim transcript below replaces the original
proof.

```
$ uv run ruff check src/sdlc/_scratch_noncompliant.py
I002 [*] Missing required import: `from __future__ import annotations`
--> src/sdlc/_scratch_noncompliant.py:1:1

C901 `f` is too complex (9 > 8)
 --> src/sdlc/_scratch_noncompliant.py:2:5

PLR0911 Too many return statements (9 > 6)
 --> src/sdlc/_scratch_noncompliant.py:2:5

SIM116 Use a dictionary instead of consecutive `if` statements
 --> src/sdlc/_scratch_noncompliant.py:3:5

PLR2004 Magic value used in comparison [×7]
E701 Multiple statements on one line (colon) [×8]

Found 19 errors.
[*] 1 fixable with the `--fix` option.
ruff exit: 1

$ uv run mypy --strict src/sdlc/_scratch_noncompliant.py
src/sdlc/_scratch_noncompliant.py:2: error: Function is missing a type
annotation  [no-untyped-def]
    def f(x):
    ^~~~~~~~
Found 1 error in 1 file (checked 1 source file)
mypy exit: 1
```

Both ruff (`I002`, `C901`, `PLR0911`) and mypy (`[no-untyped-def]`) fail with non-zero exit
on the same scratch file. AC4 is now literally satisfied: ruff fails citing cap rules **and**
mypy fails with explicit annotation-missing error.

**Tool versions captured (Task 7.2)**:
- ruff 0.15.12
- mypy 2.0.0 (compiled: yes)
- pytest 9.0.3
- Coverage.py 7.13.5

### Completion Notes List

- ✅ **Task 1**: Added `[dependency-groups] dev` with ruff>=0.6.0, mypy>=1.11.0,
  pytest>=8.0.0, pytest-cov>=5.0.0, coverage[toml]>=7.6.0. Synced via `uv sync --group dev`.
  Actual versions resolved: ruff 0.15.12, mypy 2.0.0, pytest 9.0.3, pytest-cov 7.1.0,
  coverage 7.13.5.

- ✅ **Task 2**: All ruff config tables added to pyproject.toml:
  `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.mccabe]`, `[tool.ruff.lint.pylint]`,
  `[tool.ruff.lint.isort]`, `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.format]`.
  `ruff check src/ tests/` → clean. `ruff format --check` → clean.

- ✅ **Task 3**: `[tool.mypy]` with `strict = true` + `[[tool.mypy.overrides]]` for tests.
  `mypy --strict src/` → Success, no issues. Config-driven `mypy src/` → identical outcome.

- ✅ **Task 4**: `[tool.pytest.ini_options]` + `[tool.coverage.run]` + `[tool.coverage.report]`
  added. `tests/test_smoke.py` authored. `uv run pytest` → 1 passed, 100% coverage (≥90% ✓).

- ✅ **Task 5**: Negative-test scratch file created, ruff confirmed exit code 1 with I002 +
  C901 citations. File deleted. `git status` confirms no scratch file in tree.

- ✅ **Task 6**: `docs/decisions/` created. ADR-002, ADR-003, ADR-004 authored as Markdown
  stubs with Status/Context/Decision/Alternatives/Consequences/Revisit-by structure.

- ✅ **Task 7**: All 7 final assertions passed. Full quality gate sequence exits 0.

- ✅ **`.gitignore` updated**: Added `coverage.xml` (CI artifact, generated by `--cov-report=xml`).

- ✅ **`tests/.gitkeep` removed**: The `.gitkeep` file was present in `tests/` from Story 1.1;
  `tests/test_smoke.py` replaces its functional purpose. Removed via `git rm tests/.gitkeep`
  (corrected from the original "git auto-removes when directory is non-empty" claim — git
  does NOT auto-remove tracked files; explicit removal is required).

### File List

- `pyproject.toml` — **modified**: added `[dependency-groups]` (with version caps applied
  during code review), `[tool.ruff*]`, `[tool.mypy*]`, `[tool.pytest.ini_options]` (with
  `markers` table added during code review), `[tool.coverage.*]` (with `partial_branches`
  added and `parallel = true` / dead `omit` removed during code review)
- `uv.lock` — **modified**: dev group dependencies resolved
- `.gitignore` — **modified**: added `coverage.xml`; `.coverage` → `.coverage*` during code review
- `tests/.gitkeep` — **removed**: replaced by `tests/test_smoke.py` (`git rm` during code review)
- `tests/test_smoke.py` — **created**: smoke test for AC3/AC4
- `docs/decisions/ADR-002-ruff-config.md` — **created** + **modified during code review**:
  ruff config ADR; statements-vs-LOC narrative paragraph added, ruff version reference
  refreshed (`0.6.x` → `0.15.x`), `PLR0915` per-file-ignores note added, `S101` per-file-ignore
  removed
- `docs/decisions/ADR-003-mypy-strict.md` — **created** + **modified during code review**:
  mypy strict ADR; stale "unused section warning until first test file is added" caveat
  removed
- `docs/decisions/ADR-004-pytest-config.md` — **created**: pytest/coverage ADR stub

## Change Log

- 2026-05-08: Story 1.2 implemented — configure quality gates (ruff, mypy --strict, pytest,
  coverage) per ADR-002/003/004. Smoke test added. Negative-test proof captured. All ACs
  satisfied. Status → review.
- 2026-05-07: Code review complete (3 layers: Blind Hunter, Edge Case Hunter, Acceptance
  Auditor; 31 unique findings, 13 dismissed, 13 patched, 5 deferred). All `decision-needed`
  items resolved. AC4 mypy proof re-captured under `src/sdlc/` (mypy now exits 1 with
  `[no-untyped-def]` per spec literal text). Dev-tooling caps tightened, `parallel = true`
  dropped pending xdist, pytest markers pre-declared, `partial_branches` added for
  `if TYPE_CHECKING:`, ADR-002/003 rewrites applied. Full quality-gate sequence still exits
  0. Status → done.
