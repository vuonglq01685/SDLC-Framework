# Story 2B.2: Refuse-to-Start Below Documented Claude Code Minimum Version

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user upgrading Claude Code,
I want the framework to refuse-to-start with an explicit error if the detected Claude Code version is below the documented minimum,
so that incompatibility is surfaced immediately (NFR-COMPAT-5).

## Acceptance Criteria

> **Source ACs:** `_bmad-output/planning-artifacts/epics.md:1485-1505` (3 AC groups → AC1–AC3 below).
> **DAG position:** **Layer 1**, Epic 2B. Per `docs/sprints/epic-2b-dag.md` §3 "Dependency notes": **2B.2 is an independent leaf — nothing in-epic depends on it.** It does NOT depend on 2B.1; it is placed in Layer 1 for scheduling convenience and may run as a fully parallel worktree.
> **No new wire-format contract.** Introduces a new exception class (`CompatibilityError`) — see AC1/D1.
> **No new `JournalEntry.kind`.** A refuse-to-start gate that fires before command logic does not journal (no project state to mutate; the project may not even be initialized).

### AC1 — Version-too-low refusal

**Given** the framework declares a minimum Claude Code version (see AC1/D1 for *where*) — e.g. `claude_code_min_version = "2.0.0"`
**When** I run any `sdlc *` command and `claude --version` reports `1.5.0`
**Then** the framework refuses with `CompatibilityError("claude --version reported 1.5.0; framework requires ≥ 2.0.0. Upgrade Claude Code.")`
**And** **no command logic executes** — the refusal fires in the global CLI pre-flight, before any subcommand body runs
**And** the process exits with code **3** (Infrastructure — `architecture.md:547`: "claude/git/gh missing" family)

**And** **AC1/D1 — where the minimum version is declared:** ONE of:
  - **D1 (Recommended):** declare canonically in `pyproject.toml` under the existing `[tool.sdlc]` table (`claude_code_min_version = "..."`), AND mirror it as a `Final[str]` constant in the source module that performs the check; a unit test asserts the two agree. **Pros:** the epic AC literally says "declares … in `pyproject.toml`"; the source constant means the runtime check does **not** depend on `pyproject.toml` being present in an installed wheel (it often is not); the consistency test prevents drift. **Cons:** the value lives in two places (mitigated by the test).
  - **D2:** read `pyproject.toml` at runtime via `tomllib` (3.11+) / `tomli`. **Cons:** `requires-python = ">=3.10"` so `tomllib` is not guaranteed; installed wheels frequently omit `pyproject.toml` → the check silently has no minimum.
  - **Recommended: D1.** Record in the PR Change Log.

**And** **AC1/D2 — `CompatibilityError`:** this exception does **not** exist yet. Add `CompatibilityError(SdlcError)` to `src/sdlc/errors/base.py` with `code = "ERR_COMPATIBILITY"`, export it from `src/sdlc/errors/__init__.py` `__all__`, and register `ERR_COMPATIBILITY → 3` in the `EXIT_CODE_MAP` (`errors/base.py`) **and** `_ERR_CODE_TO_EXIT_CODE` (`cli/output.py`). The architecture error hierarchy (`architecture.md:526-538`) predates Epic 2B; adding a sibling for the external-tool-compat surface is consistent with how Epic 2A added `WorkflowError` / `SpecialistError`.

### AC2 — `claude` not installed / not on PATH

**Given** Claude Code is not installed or not on PATH
**When** I run any command requiring runtime dispatch
**Then** the error is `CompatibilityError("claude not found on PATH; install Claude Code")` with a documentation link in the message (or `error.details["docs_url"]`)
**And** the not-on-PATH case is detected from `FileNotFoundError` raised by `subprocess.run` (or a prior `shutil.which("claude")` probe) — handled distinctly from AC1's version-too-low case
**And** exit code **3**

### AC3 — Integration test with stub `claude` (CI gate)

**Given** an integration test using a **stub `claude` script** reporting versions `1.5.0`, `2.0.0`, `3.0.0`
**When** the test runs
**Then** `1.5.0` is **rejected**; `2.0.0` and `3.0.0` are **accepted** (boundary: the minimum is inclusive — `== min` passes)
**And** a fourth case — `claude` absent from PATH — asserts AC2's `CompatibilityError`
**And** a fifth case — `claude --version` emits unparseable output — is handled deterministically (see AC3/D1)
**And** the test is wired as a **CI gate** (it runs in the standard `pytest` job — no separate workflow needed)

**And** **AC3/D1 — version parsing + unparseable output:** parse the semver from `claude --version` stdout robustly (the real CLI prints a line like `claude X.Y.Z (...)` — extract with a regex, do not assume the whole line is the version). Use `packaging.version.Version` for comparison if `packaging` is an available dependency; otherwise a documented tuple-compare. If the output cannot be parsed, **fail closed** with `CompatibilityError("could not parse claude version from: <excerpt>")` (exit 3) — never silently treat unparseable as "compatible".

## Tasks / Subtasks

- [ ] **Task 1 — `CompatibilityError` + exit-code wiring** (AC: 1, 2)
  - [ ] Failing test: `CompatibilityError` exists, `code == "ERR_COMPATIBILITY"`, maps to exit 3 (RED)
  - [ ] Add `CompatibilityError(SdlcError)` to `errors/base.py`; export from `errors/__init__.py`; register exit code in both maps
- [ ] **Task 2 — minimum-version declaration** (AC: 1)
  - [ ] Add `claude_code_min_version` to `pyproject.toml` `[tool.sdlc]`
  - [ ] Mirror as `Final[str]` source constant (AC1/D1); unit test asserts the two agree
- [ ] **Task 3 — version detection + parse** (AC: 1, 2, 3)
  - [ ] Failing tests for: version-too-low, version-equal (accept), version-above (accept), not-on-PATH, unparseable
  - [ ] Implement `claude --version` invocation following the `cli/_paths.py:26-33` subprocess pattern (`capture_output=True, text=True, check=False, timeout=5`, handle `FileNotFoundError`)
  - [ ] Implement semver parse + compare (AC3/D1); fail-closed on unparseable
- [ ] **Task 4 — wire the global pre-flight gate** (AC: 1, 2)
  - [ ] Add the version check to the `cli/main.py` `@app.callback()` `_root()` pre-flight (runs before every subcommand)
  - [ ] Confirm the eager `--version` callback still exits BEFORE `_root()` — `sdlc --version` must NOT trigger the claude check (and must not regress the <200 ms cold-start budget, `architecture.md:488`)
- [ ] **Task 5 — integration test + CI gate** (AC: 3)
  - [ ] Stub `claude` scripts for `1.5.0` / `2.0.0` / `3.0.0`; PATH monkeypatch; absent-PATH + unparseable cases
  - [ ] Assert reject/accept matrix; verify it runs in the standard CI `pytest` job
- [ ] **Task 6 — quality gate**
  - [ ] ruff format/check, mypy --strict, pytest, coverage ≥87, pre-commit --all-files, mkdocs --strict, wire-format snapshots

## Dev Notes

### Relevant architecture patterns and constraints

- **CLI pre-flight hook** — `src/sdlc/cli/main.py`: Typer app; `@app.callback()` `_root(ctx, ...)` runs before *every* `sdlc <command>`. The `--version` option is **eager** — `_version_callback()` fires and exits before `_root()`. **Wire the claude-version gate inside `_root()`** so it gates all real commands while `sdlc --version` stays fast and claude-independent. Command imports are deferred inside function bodies (`architecture.md:488`) to protect cold-start — keep the version-check module import light.
- **Subprocess pattern (canonical)** — `src/sdlc/cli/_paths.py:26-33` and `src/sdlc/hooks/runner.py:103-113`: `subprocess.run([...], capture_output=True, text=True, check=False, timeout=<5s const>)`, `except (OSError, subprocess.SubprocessError)`. `FileNotFoundError` (a subclass of `OSError`) is how "not on PATH" surfaces — branch on it explicitly for AC2's distinct message.
- **Error taxonomy** — `src/sdlc/errors/base.py`: `SdlcError` root, `details: dict[str, object]`. Exit codes: `architecture.md:540-547` — **3 = Infrastructure (external binary missing)**. `CompatibilityError` belongs at exit 3, not 1 or 2.
- **`errors` module boundary** — `scripts/module_boundary_table.py`: `errors` has zero dependencies (it is the root module). `CompatibilityError` is a pure addition there. The version-check logic itself is **CLI-layer concern** — place it in the `cli` module (e.g. a private `src/sdlc/cli/_compat_check.py`), called from `cli/main.py:_root()`. `cli` may import everything; no boundary risk.
- **`pyproject.toml`** — an existing `[tool.sdlc.hooks]` table is present; add `claude_code_min_version` under `[tool.sdlc]` (create the bare `[tool.sdlc]` table header if only the `.hooks` subtable currently exists). FR47 (`--version`) maps to `pyproject.toml` + `src/sdlc/__init__.py` (`architecture.md:1173`) — adjacent territory.
- **NFR-COMPAT-5** is the requirement this story satisfies. It is sibling to FR48 (`architecture.md:1174`, upgrade with major-version *schema* refusal) — different surface: FR48 gates on state-schema version, this story gates on the external `claude` binary version. Do not conflate.

### Project Structure Notes

- **New:** `CompatibilityError` in `src/sdlc/errors/base.py`; version-check helper in `src/sdlc/cli/` (private module, e.g. `_compat_check.py`); `claude_code_min_version` key in `pyproject.toml`.
- **Modified:** `src/sdlc/errors/base.py` + `errors/__init__.py` (new exception + export + exit-code map), `src/sdlc/cli/main.py` (`_root()` pre-flight), `src/sdlc/cli/output.py` (`_ERR_CODE_TO_EXIT_CODE`), `pyproject.toml`.
- **Tests:** `tests/unit/cli/test_compat_check.py` (parse / compare / fail-closed), `tests/unit/errors/` (CompatibilityError), `tests/integration/test_claude_version_gate.py` (stub-script matrix). Stub `claude` scripts: a tiny shell/Python script that `echo`s a version line; place under a test fixtures dir; `monkeypatch.setenv("PATH", f"{stub_dir}:{...}")`.
- **Layer 1 sibling coordination — SHARED-FILE HOTSPOT:** **`src/sdlc/errors/base.py` + `errors/__init__.py` are touched by BOTH this story (adds `CompatibilityError`) and Story 2B.5 (adds `SecurityError`).** Per CONTRIBUTING §3 (worktree-per-story, linear merge, rebase between merges): the first of {2B.2, 2B.5} to merge owns the file; the second **rebases onto `main`** and re-applies its one-class addition. The additions are non-overlapping (different class, different `__all__` line, different exit-code entry) — a clean rebase, but it MUST be a rebase, not a divergent merge. `cli/main.py` is also touched by 2B.1 (`--allow-mock`); coordinate if both land options on the root callback.
- Worktree: `epic-2b/2b-2-version-refuse` (owner: Elena, DAG §5).

### Testing standards summary

- TDD-first (CONTRIBUTING §2): the version-gate behaviour is user-facing CLI surface — tests-first commit ordering visible in `git log --reverse`.
- Anti-tautology (ADR-026 §1): the stub-script matrix is itself the receipt — a stub reporting `1.5.0` must produce a RED test if the comparison logic is removed. Ensure the accept cases (`2.0.0`, `3.0.0`) and reject case (`1.5.0`) are distinct assertions, not a single tautological "it ran".
- Test org (`architecture.md:682-701`): unit under `tests/unit/cli/` mirroring src; integration under `tests/integration/`. Naming `test_<behavior>_<expected_outcome>`.
- Quality gate (CONTRIBUTING §1): ruff format + ruff check + `mypy --strict` + pytest + coverage ≥87 + `pre-commit run --all-files` + `mkdocs --strict` + wire-format snapshots.
- Watch the cold-start budget: a unit test or benchmark should confirm `sdlc --version` does NOT spawn a `claude` subprocess.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-2B.2] — AC source (lines 1485-1505)
- [Source: _bmad-output/planning-artifacts/architecture.md#Error-Handling-and-Logging] — exception hierarchy + exit codes (lines 524-547)
- [Source: _bmad-output/planning-artifacts/architecture.md#External-Integration-Points] — external-binary failure family (lines 1114-1125)
- [Source: docs/sprints/epic-2b-dag.md] — §3 Layer 1 + "2B.2 independent leaf" dependency note, §5 worktree assignment
- [Source: src/sdlc/cli/main.py] — `@app.callback()` `_root()` pre-flight hook
- [Source: src/sdlc/cli/_paths.py] — canonical subprocess pattern (lines 26-33)
- [Source: src/sdlc/errors/base.py] — `SdlcError` hierarchy + `EXIT_CODE_MAP`
- [Source: src/sdlc/cli/output.py] — `_ERR_CODE_TO_EXIT_CODE` mapping
- [Source: pyproject.toml] — existing `[tool.sdlc.hooks]` table
- [Source: CONTRIBUTING.md] — §1 quality gate, §2 TDD-first, §3 worktree workflow
- [Source: docs/decisions/ADR-026.md §1] — anti-tautology receipt requirement

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
