# Story 1.1: Project Bootstrap with `uv init` + hatchling

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a tech lead bootstrapping the framework,
I want a reproducible project skeleton initialized via `uv` with the hatchling build backend (package renamed to `sdlc`, src layout, Python ≥3.10, lockfile committed) and a smoke-buildable wheel exposing `sdlc.__version__`,
So that every subsequent story (1.2 quality gates, 1.3 CI, 1.4 boundaries, 1.5 mkdocs/ADRs, 1.6+ foundation modules) builds on a deterministic dev environment with a locked dependency graph and a working PyPI-shape wheel.

## Acceptance Criteria

**AC1 — `uv init` produces the canonical greenfield skeleton.**
**Given** an empty directory and `uv` ≥ 0.5 installed
**When** I run `uv init --package --build-backend hatchling --python ">=3.10" sdlc-framework`
**Then** `pyproject.toml` declares `[build-system] requires = ["hatchling"]` and `build-backend = "hatchling.build"`
**And** the package layout exists at `src/sdlc/` (renamed from default `sdlc_framework` per PRD §FR47 / Architecture §261)
**And** `tests/` and `docs/` placeholder directories exist
**And** `.python-version` declares `>=3.10`
**And** `uv sync` produces `uv.lock` with no errors

**AC2 — Wheel builds, installs, and exposes the version constant.**
**Given** the bootstrapped project
**When** I run `uv build`
**Then** a wheel is produced under `dist/*.whl`
**And** the wheel installs cleanly into a fresh venv via `pip install dist/*.whl`
**And** `python -c "import sdlc; print(sdlc.__version__)"` prints the version declared in `pyproject.toml`

## Tasks / Subtasks

- [x] **Task 1 — Bootstrap with `uv init` (AC: #1)**
  - [x] 1.1 Verify `uv --version` ≥ 0.5 in dev environment; if missing, document install via `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh` (do NOT add `uv` as a project dependency — it's a host tool).
  - [x] 1.2 From the empty repo root, run **exactly**: `uv init --package --build-backend hatchling --python ">=3.10" sdlc-framework`. **CRITICAL**: the `--build-backend hatchling` flag is non-negotiable — since uv 0.8.x, omitting it makes `uv_build` the default, which violates the PRD-locked build backend (Architecture §250).
  - [x] 1.3 Confirm `uv init` generated: `pyproject.toml`, `src/sdlc_framework/__init__.py`, `tests/` placeholder (or create `tests/.gitkeep` if absent — `uv init --package` creates tests dir but may leave it empty), `.python-version`, `README.md` skeleton, `.gitignore`.
  - [x] 1.4 Do NOT yet add ruff/mypy/pytest tool tables — those land in Story 1.2. Keep this story strictly to substrate.

- [x] **Task 2 — Rename package to `sdlc` (AC: #1)**
  - [x] 2.1 Move `src/sdlc_framework/` → `src/sdlc/` (the PyPI distribution name stays `sdlc-framework`; only the import name becomes `sdlc`).
  - [x] 2.2 Update `pyproject.toml`:
    - `[project] name = "sdlc-framework"` (PyPI name; **must remain** `sdlc-framework` per PRD §216, FR47).
    - Add `[tool.hatch.build.targets.wheel] packages = ["src/sdlc"]` so hatchling finds the renamed package.
    - Add `[project.scripts] sdlc = "sdlc.cli.main:app"` placeholder (the `cli/main.py` does not exist yet — leave a TODO comment to wire in Story 1.16; for v0.2 substrate, declare a stub `def app() -> None: print("sdlc CLI placeholder; wired in Story 1.16")` in `src/sdlc/__init__.py` OR omit the entry point until 1.16 — choose omit-until-1.16 to avoid shipping a broken script).
  - [x] 2.3 Edit `src/sdlc/__init__.py` to declare `__version__: str = "0.0.0"` (or read dynamically — see Task 3.3) and an explicit `__all__ = ["__version__"]`. First non-comment line MUST be `from __future__ import annotations` per Architecture §487.

- [x] **Task 3 — Configure `pyproject.toml` `[project]` metadata + version source (AC: #2)**
  - [x] 3.1 Set `[project]` fields exactly:
    - `name = "sdlc-framework"`
    - `version = "0.0.0"` (static for v0.2 — dynamic versioning via `hatch-vcs` is a v1.x candidate, NOT this story).
    - `description = "Deterministic, auditable, multi-agent SDLC orchestration framework on top of Claude Code."` (drawn from PRD §106).
    - `readme = "README.md"`
    - `license = { text = "TBD" }` (LICENSE file authored in a later v0.2 task; placeholder is acceptable for substrate-only commit).
    - `requires-python = ">=3.10"` (matches `.python-version` and PRD §FR47, NFR-COMPAT-1).
    - `authors = [{ name = "Vuonglq01685" }]`
    - `dependencies = []` — keep empty in this story. pydantic, structlog, typer, rich, etc. are added in later foundation stories (1.6+) when the modules importing them land.
  - [x] 3.2 **Do not** add `[project.optional-dependencies]` groups in this story — `[dependency-groups]` for `dev`/`test` lands with Story 1.2.
  - [x] 3.3 Keep `__version__` in `src/sdlc/__init__.py` hardcoded to match `[project] version` (`"0.0.0"`). A future ADR-001 update can switch to `importlib.metadata.version("sdlc-framework")` once the wheel is installable; for AC2 the simpler approach is fine and avoids the extra import path. Verify against AC2's `python -c "import sdlc; print(sdlc.__version__)"` requirement.

- [x] **Task 4 — Configure hatchling wheel build (AC: #1, #2)**
  - [x] 4.1 Add `[build-system]` block:
    ```toml
    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"
    ```
  - [x] 4.2 Add `[tool.hatch.build.targets.wheel]`:
    ```toml
    [tool.hatch.build.targets.wheel]
    packages = ["src/sdlc"]
    ```
  - [x] 4.3 **Do not** yet add `package_data` for `agents/`, `commands/`, `skills/`, `dashboard/static/`, `workflows/`, `memory/`, `claude_hooks/` — those payloads do not exist yet. ADR-005 (`package_data` layout) is realized when those directories are created in their respective stories (1.16 for `commands/`, 2B.8–2B.11 for `agents/`, etc.). Leave a `# TODO: ADR-005 — package_data extension lands in Story 1.16+` comment beside the wheel target.
  - [x] 4.4 Skip sdist target configuration: PRD §499 mandates **wheel-only** distribution for v1. Hatchling emits sdist by default; suppress via `[tool.hatch.build.targets.sdist] exclude = ["**"]` ONLY if Story 1.3 release.yml requires sdist suppression — for THIS story leave default (sdist will build but is not consumed). Document the v1 wheel-only intent as a comment.

- [x] **Task 5 — Lockfile + smoke build (AC: #1, #2)**
  - [x] 5.1 Run `uv sync` in repo root. Assert `uv.lock` is created at the repo root and exits 0. Commit `uv.lock` (it is the dev-environment reproducibility contract per Architecture §249).
  - [x] 5.2 Run `uv build`. Assert `dist/*.whl` exists with filename matching `sdlc_framework-0.0.0-py3-none-any.whl` (PEP 427 — note hyphen-to-underscore normalization in wheel filename).
  - [x] 5.3 Smoke-install in a clean throwaway venv (script step, not committed):
    ```bash
    python -m venv /tmp/sdlc-smoke && /tmp/sdlc-smoke/bin/pip install dist/*.whl \
      && /tmp/sdlc-smoke/bin/python -c "import sdlc; print(sdlc.__version__)"
    ```
    Expected stdout: `0.0.0`. Exit code 0.
  - [x] 5.4 Add `dist/`, `*.egg-info/`, `.venv/` to `.gitignore` (`uv init` covers most; verify `dist/` is present).

- [x] **Task 6 — Verification + handoff (AC: #1, #2)**
  - [x] 6.1 Author Dev Agent Record entries: list every file created or modified, the exact `uv` and `hatchling` versions used (capture via `uv --version` and `pip show hatchling | grep Version` inside the smoke venv).
  - [x] 6.2 Confirm Story 1.5 has the ADR-001 stub waiting; for THIS story it is sufficient to leave a TODO note in Dev Agent Record pointing to `docs/decisions/ADR-001-pyproject-metadata.md` (file authored in Story 1.5).
  - [x] 6.3 Run final assertions in order:
    1. `ls pyproject.toml uv.lock .python-version src/sdlc/__init__.py tests README.md` → all exist.
    2. `grep '^build-backend' pyproject.toml` → contains `"hatchling.build"`.
    3. `grep 'requires-python' pyproject.toml` → contains `">=3.10"`.
    4. `cat .python-version` → matches `>=3.10` constraint (file typically holds an exact pin like `3.10` or `3.12`; the constraint is enforced by `requires-python`).
    5. `uv build && pip install --force-reinstall dist/*.whl && python -c "import sdlc; print(sdlc.__version__)"` in a clean venv → prints version.
  - [x] 6.4 Commit message style (Architecture §487 + global git-workflow rules): `feat: bootstrap sdlc-framework with uv + hatchling (Story 1.1)`.

## Dev Notes

### Critical context

This is the **first implementation commit of v0.2** (Architecture §302, §1402). Every subsequent story in Epic 1 (1.2 → 1.21) and downstream epics depends on the substrate this story creates. **Substrate correctness > feature breadth** is the entire MVP thesis (PRD §592). Take the boring path; do not over-build.

### What this story is NOT

- **NOT** the place to add ruff/mypy/pytest configuration → Story 1.2 (ADR-002/003/004).
- **NOT** the place to add CI workflows → Story 1.3 (ADR-006–009).
- **NOT** the place to add pre-commit boundary hooks → Story 1.4 (ADR-010).
- **NOT** the place to add mkdocs / ADR log → Story 1.5 (ADR-011).
- **NOT** the place to author specialist `.md` files, slash commands, or workflow YAMLs — those start in Epic 2A/2B.
- **NOT** the place to scaffold every src/sdlc submodule (`engine/`, `state/`, `journal/`, etc.). Only `src/sdlc/__init__.py` exists after this story; submodules land in Stories 1.6+ as their tests demand them.

### Architecture compliance — what MUST be true after this story

- **Build backend**: `hatchling` (Architecture §237, §250, ADR-001 scope). **Reject `uv_build`**, the new uv 0.8+ default — see "Latest Tech Information" below for why this is a real foot-gun.
- **Layout**: `src/sdlc/` (renamed from `uv init`'s default `src/sdlc_framework/`). PyPI distribution name remains `sdlc-framework` (Architecture §261, PRD §FR47).
- **Python floor**: `>=3.10` enforced in `pyproject.toml [project] requires-python` AND `.python-version` (Architecture §773, NFR-COMPAT-1). Do NOT use 3.10-only-deprecated APIs; remember `asyncio.TaskGroup` is 3.11+ and is explicitly off-limits here per Decision A2 (Architecture §337).
- **Wheel-only distribution intent**: PRD §499 and PRD §216. Sdist suppression is a v1 release-pipeline concern (Story 1.3); for this story do not block on it.
- **Lockfile committed**: `uv.lock` is the reproducibility contract for solo-build context-loss mitigation (Architecture §249, Resource Risk R4).
- **Code style preview**: Even though Story 1.2 codifies ruff/mypy, this story's `src/sdlc/__init__.py` MUST already obey: `from __future__ import annotations` as first non-comment line (Architecture §487). One ≤400 LOC file with ≤50 LOC functions, complexity ≤8 (`__init__.py` here is trivially compliant).

### Library / framework requirements (versions to assume)

| Tool | Min version | Notes / source |
|---|---|---|
| Python | ≥ 3.10 (3.10, 3.11, 3.12, 3.13 will be CI-tested in Story 1.3) | NFR-COMPAT-1 |
| `uv` | ≥ 0.5 (host tool; not a project dep) | Story 1.1 AC, Architecture §237 |
| `hatchling` | latest stable (resolved transitively by build front-end) | Architecture §250 |
| `pip` | latest in target venv (smoke install) | AC2 |

**Do NOT add** as project dependencies in this story: pydantic, structlog, typer, rich, hypothesis, pytest, mypy, ruff, mkdocs, pre-commit. Each lands in the story whose module first uses it.

### File structure requirements (post-story canonical state)

After Story 1.1 lands, `git ls-files` should show **only**:

```
.gitignore
.python-version
README.md
pyproject.toml
src/sdlc/__init__.py
tests/.gitkeep                # if uv init didn't drop a placeholder
uv.lock
```

Plus whatever `uv init` adds that is harmless (e.g., `README.md` skeleton). **Do NOT** create:

- `src/sdlc/engine/`, `src/sdlc/state/`, `src/sdlc/journal/`, etc. — those are Story 1.6+ scope.
- `.github/workflows/` — Story 1.3.
- `docs/` — Story 1.5 (the AC mentions `docs/` as a placeholder directory; create a `docs/.gitkeep` if you want to mirror `tests/`, but mkdocs config is Story 1.5's job).
- `.pre-commit-config.yaml` — Story 1.4.
- `LICENSE` — placeholder text per Task 3.1; full LICENSE is a later v0.2 chore.

### Testing requirements

- **No pytest tests authored in this story.** The single behavioral assertion is the smoke install in Task 5.3 (`pip install dist/*.whl && python -c "import sdlc"`). Test infrastructure (pytest config, hypothesis, coverage gates) is Story 1.2.
- The Dev Agent Record MUST document the smoke install transcript (command + stdout + exit code).

### Project Structure Notes

- Alignment with unified project structure (Architecture §767 directory tree): this story creates the **leftmost root scaffolding only** (`pyproject.toml`, `uv.lock`, `.python-version`, `README.md`, `.gitignore`, `src/sdlc/__init__.py`, `tests/`). All other files in that tree are added by later stories.
- Detected variance: `uv init --package` produces `src/<distribution-name-snake-case>/` (i.e. `src/sdlc_framework/`). PRD §FR47 + Architecture §261 require the **import name** to be `sdlc`, while the **PyPI name** stays `sdlc-framework`. The rename is a deliberate one-time action in Task 2 — do **not** rename the PyPI distribution.
- Detected variance: `uv` 0.8+ defaults `--build-backend` to `uv_build`. Architecture §237 / §250 select hatchling explicitly. Always pass `--build-backend hatchling`. If a future maintainer reruns `uv init` accidentally, the explicit flag prevents silent drift.

### Latest tech information (research summary; 2026-05-07)

- **uv 0.8.x default-backend change.** Per `astral-sh/uv` changelogs, the `uv_build` backend was stabilized in uv 0.7.19 and became the default for `uv init --package` / `uv init --lib`. Explicit `--build-backend hatchling` is required to honour the architecture's hatchling decision. *Source: Context7 `/astral-sh/uv` "Project Initialization > Build Backend > Default Selection".*
- **Hatchling wheel target shape.** Modern hatchling expects `[tool.hatch.build.targets.wheel] packages = ["src/<pkg>"]`. Avoid the older `include`/`exclude` glob style for the package list — use `packages` for src layout. *Source: Context7 `/pypa/hatch` Wheel Builder Configuration.*
- **`shared-data`, `shared-scripts`, `force-include`** under `[tool.hatch.build.targets.wheel.*]` are the canonical mechanisms for shipping non-Python payload data into the wheel. They are the future home of ADR-005's `package_data` for `agents/`, `commands/`, `skills/`, `dashboard/static/`, `workflows/`, `memory/`, and `claude_hooks/` — but those payloads do not exist yet and **must not be configured in this story**.
- **uv lockfile committed.** `uv.lock` is intended to be checked in for reproducible dev environments; `uv sync` is the canonical install path. *Source: Context7 `/astral-sh/uv` "Lock and sync dependencies".*

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.1] — original AC, story statement.
- [Source: _bmad-output/planning-artifacts/architecture.md#Starter-Template-Evaluation] (lines 227–303) — `uv init --package --build-backend hatchling` rationale, hand-crafted-vs-starter table.
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete-Project-Directory-Structure] (lines 767–1046) — canonical post-v1 directory layout (this story creates only its root substrate).
- [Source: _bmad-output/planning-artifacts/architecture.md#Code-Style-Beyond-Ruff] (line 487) — `from __future__ import annotations` first-line rule.
- [Source: _bmad-output/planning-artifacts/prd.md#AR-STARTER] (line 164) — PRD's pre-locked starter command and ADR-001..012 mandate.
- [Source: _bmad-output/planning-artifacts/prd.md#Installation-Methods] (lines 487–505) — wheel-only build, hatchling, PyPI distribution `sdlc-framework`, console script `sdlc`.
- [Source: _bmad-output/planning-artifacts/prd.md#Technical-Success] (lines 161–179) — substrate invariants this story enables (lockfile reproducibility, mypy-strict-ready code style baseline).
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-05-07.md] (line 482) — explicit "Story 1.1 is exactly this" readiness call-out.
- [Context7 `/astral-sh/uv` — Project Initialization > Build Backend > Default Selection] — uv 0.8+ `uv_build` default warning.
- [Context7 `/pypa/hatch` — Wheel Builder Configuration / Hatch Build Configuration in pyproject.toml] — `[tool.hatch.build.targets.wheel] packages = ["src/<pkg>"]` canonical shape.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

**Smoke install transcript (Task 5.3):**
```
Command: python3 -m venv /tmp/sdlc-smoke && /tmp/sdlc-smoke/bin/pip install dist/sdlc_framework-0.0.0-py3-none-any.whl --quiet && /tmp/sdlc-smoke/bin/python -c "import sdlc; print(sdlc.__version__)"
Stdout: 0.0.0
Exit code: 0
```

**Tool versions used:**
- uv: 0.11.8 (0e961dd9a 2026-04-27 aarch64-apple-darwin)
- hatchling: latest stable (resolved by uv build tool as build-time dep; not pinned in uv.lock)
- Python (dev env): CPython 3.12.13

**uv init adaptation note:**
- uv 0.11.8 uses `--build-backend hatch` (not `hatchling`) as the CLI flag value; both resolve to `hatchling.build` in the generated pyproject.toml.
- `--name sdlc-framework` flag used instead of path argument to initialize in the current repo root directory (passing `sdlc-framework` as PATH would create a subdirectory).
- `--no-workspace` flag added to avoid discovering parent workspace.

**uv sync output:**
```
Using CPython 3.12.13
Resolved 1 package in 24ms
Built sdlc-framework @ file:///...SDLC-Framework
Installed 1 package in 0.81ms
+ sdlc-framework==0.0.0
```

### Completion Notes List

- ✅ AC1: pyproject.toml declares `[build-system] requires = ["hatchling"]` and `build-backend = "hatchling.build"`
- ✅ AC1: Package layout at `src/sdlc/` (renamed from `src/sdlc_framework/`); PyPI name remains `sdlc-framework`
- ✅ AC1: `tests/`, `docs/` (existing), `.python-version` (3.12 pin, `>=3.10` in pyproject), `.gitignore`, `README.md` all present
- ✅ AC1: `uv sync` produced `uv.lock` at repo root, exit 0
- ✅ AC2: `uv build` produced `dist/sdlc_framework-0.0.0-py3-none-any.whl`
- ✅ AC2: Smoke install in `/tmp/sdlc-smoke` venv → `python -c "import sdlc; print(sdlc.__version__)"` → `0.0.0`, exit 0
- ✅ `src/sdlc/__init__.py` starts with `from __future__ import annotations` (Architecture §487)
- ✅ `[project.scripts]` entry point omitted until Story 1.16 (avoids broken script)
- ✅ `# TODO: ADR-005` comment in pyproject.toml beside `[tool.hatch.build.targets.wheel]`
- ✅ `# TODO: ADR-001 — docs/decisions/ADR-001-pyproject-metadata.md` authored in Story 1.5
- ✅ No ruff/mypy/pytest tables added (Story 1.2 scope)
- ✅ `dist/`, `*.egg-info`, `.venv` in `.gitignore`

### File List

- `pyproject.toml` (created + modified: version 0.0.0, canonical metadata, hatchling build system, wheel target with src/sdlc)
- `src/sdlc/__init__.py` (created: `from __future__ import annotations`, `__version__ = "0.0.0"`, `__all__`)
- `.python-version` (created by uv init: `3.12`)
- `.gitignore` (created by uv init: dist/, *.egg-info, .venv, __pycache__)
- `README.md` (created by uv init: empty skeleton)
- `uv.lock` (created by uv sync: reproducibility lockfile)
- `tests/.gitkeep` (created: placeholder for test directory)
- `docs/ux/dashboard-prototype/dashboard.html` (carried over from prior UX planning workflow; tracked here per code-review decision 2026-05-07 to admit File-List drift rather than re-scope)
- `docs/ux/dashboard-prototype/state.json` (same as above)
- `docs/ux/dashboard-prototype/README.md` (same as above)

**File List drift acknowledgment (2026-05-07 code review, D1):** The canonical File List in Dev Notes (post-story state) lists `tests/.gitkeep` only and explicitly defers `docs/` content to Story 1.5. `docs/ux/dashboard-prototype/` was authored during a pre-1.1 UX planning pass and exists on disk before the bootstrap commit. Per user decision in the 2026-05-07 review, these three files are tracked as part of Story 1.1's bootstrap commit (option "admit drift, accept as-is") rather than gitignored or relocated. Story 1.5's mkdocs scaffolding will absorb or reorganize this content when authored.

## Change Log

- 2026-05-07: Story 1.1 implemented — bootstrapped sdlc-framework with uv 0.11.8 + hatchling; renamed package src/sdlc_framework → src/sdlc; configured pyproject.toml metadata + wheel target; smoke build and install verified (AC1 + AC2 satisfied).
- 2026-05-07: Code review run (3 reviewers: Blind Hunter, Edge Case Hunter, Acceptance Auditor). See Review Findings section.

### Review Findings

**Decision needed**

- [x] [Review][Decision] `docs/` contains populated `docs/ux/` subtree, not a Story-1.1 placeholder — **Resolved 2026-05-07: option (b) chosen.** `docs/ux/dashboard-prototype/{dashboard.html,state.json,README.md}` added to Story 1.1's File List with explicit drift acknowledgment. These were authored in a pre-1.1 UX planning pass and will be tracked as part of the bootstrap commit. Story 1.5's mkdocs scaffolding will absorb or reorganize the content when authored.

**Patch**

- [x] [Review][Patch] No bootstrap commit — **Resolved 2026-05-07: commit `0dd96ea` created** with spec-mandated message `feat: bootstrap sdlc-framework with uv + hatchling (Story 1.1)`. `uv.lock` now tracked. [git state]
- [x] [Review][Patch] Add scratch dirs to `.gitignore` to keep first commit canonical — **Resolved 2026-05-07.** Added `_bmad/`, `_bmad-output/`, `.claude/`, plus tooling caches and editor dirs. Bonus: also discovered user-global `*.md` exclusion was hiding `README.md` files; added `!*.md`/`!**/*.md` negation to override globally. [.gitignore]
- [x] [Review][Patch] `README.md` is empty — **Resolved 2026-05-07.** Authored real README with project description, requirements, quickstart, and license placeholder. Wheel METADATA now carries Description content. [README.md]
- [x] [Review][Patch] Add common Python tooling cache dirs to `.gitignore` — **Resolved 2026-05-07.** Added `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`, `.coverage`, `htmlcov/`, `.idea/`, `.vscode/`, `.DS_Store`. [.gitignore]
- [x] [Review][Patch] Tighten `*.egg-info` → `*.egg-info/` — **Resolved 2026-05-07.** [.gitignore:7]

**Deferred (per spec; tracked in `_bmad-output/implementation-artifacts/deferred-work.md`)**

- [x] [Review][Defer] `license = { text = "TBD" }` — not a valid SPDX identifier. Spec Task 3.1 explicitly authorizes "TBD" as placeholder for substrate-only commit; LICENSE file is later v0.2 chore. [pyproject.toml:6]
- [x] [Review][Defer] sdist suppression (wheel-only per PRD §499) — hatchling emits sdist by default; full suppression via `[tool.hatch.build.targets.sdist] exclude = ["**"]` deferred to Story 1.3. Patch P2 (gitignore scratch dirs) reduces leakage blast radius in the meantime. [pyproject.toml]
- [x] [Review][Defer] `__version__` duplicated between `pyproject.toml` and `src/sdlc/__init__.py` — spec Task 3.3 explicitly chose static hardcoded approach over `importlib.metadata.version()` for AC2 simplicity; ADR-001 future update will switch. [pyproject.toml:3, src/sdlc/__init__.py:3]
- [x] [Review][Defer] AC1.4 literal wording vs intent — `.python-version = 3.12` is a pin, not the constraint string AC1 literally requires. Dev Notes acknowledge "the file typically holds an exact pin like 3.10 or 3.12; the constraint is enforced by `requires-python`." Recommend tightening AC1 wording in a future spec edit; no code change needed. [.python-version]
