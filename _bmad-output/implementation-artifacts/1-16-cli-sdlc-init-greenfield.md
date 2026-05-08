# Story 1.16: CLI `sdlc init` (Greenfield) + `sdlc --version` + package_data

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user installing the framework for the first time,
I want `sdlc init` to scaffold a fresh project layout in any git repo and `sdlc --version` to report the installed version,
so that the framework's first user contact succeeds — `pip install sdlc-framework && sdlc init && sdlc status` works end-to-end on a clean machine — and the canonical SDLC layout (`.claude/state/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`, `.claude/workflows/`, `.claude/memory/`, `01-Requirement/`, `02-Architecture/`, `03-Implementation/`) is materialized exactly as Architecture §443 defines (FR1, FR47, FR50, NFR-COMPAT-1, ADR-001, ADR-005, Architecture §117, §388, §443, §790-§811, §1131, §1402, §1408).

## Acceptance Criteria

**AC1 — `sdlc --version` reports the installed wheel's version (epic AC block 1)**

**Given** the framework is installed via `pip install sdlc-framework` (or `uv sync` in dev),

**When** the user invokes `sdlc --version`,

**Then**:

1. The command exits 0 on success.
2. stdout contains exactly one line of the form `sdlc <version>` (e.g. `sdlc 0.0.0`); no leading/trailing blank lines, no ANSI escapes (the bare `--version` flag is non-decorated; rich coloring is reserved for Story 1.17's `--no-color` toggle on long-form output).
3. The version string equals `importlib.metadata.version("sdlc-framework")` AND equals `sdlc.__version__` (Story 1.1's static placeholder `"0.0.0"` per ADR-001). If the two diverge, the test fixture surfaces it; ADR-001 explicitly accepted the duplication for v0.2 with a v1.x revisit on dynamic-version sourcing.
4. The handler for `--version` lives in `src/sdlc/cli/version.py`, NOT in `src/sdlc/cli/main.py` and NOT in `src/sdlc/__main__.py` (which does NOT exist in v1; the entry point is the console script `sdlc`, NOT `python -m sdlc`). Per epic AC block 1 explicitly: "implemented in `cli/version.py`, not in `__main__.py`".
5. `cli/version.py` exposes a single public callable `get_version() -> str` that returns the canonical version string. `cli/main.py` registers a Typer `--version` callback that calls `get_version()` and uses `typer.echo` (NOT `print`) to emit the line + `raise typer.Exit(code=0)`.
6. The console script entry point is wired in `pyproject.toml` `[project.scripts]`:
   ```toml
   [project.scripts]
   sdlc = "sdlc.cli.main:app"
   ```
   The currently-commented stub at `pyproject.toml:16-18` is uncommented and the `# TODO: Wire CLI entry point in Story 1.16` comment is removed (the wiring lands here).

**And** invoking `sdlc` with NO arguments (zero-arg invocation) prints the typer-default help summary on stdout (NOT stderr) and exits 0 — consistent with Typer's default `no_args_is_help=False` behavior overridden to `True` so usage is helpful rather than silent. Exit on missing-subcommand is 0 because help is informational, not an error (Story 1.17 may revisit if `sdlc` should default to `sdlc status` in the future).

**And** invoking `sdlc --help` prints a usage block listing the registered subcommands (`init`) plus the `--version` flag. Exit 0.

**And** the `cli/main.py` Typer app is named `app` (singular, lowercase) so the console-script reference `"sdlc.cli.main:app"` resolves cleanly.

**AC2 — `sdlc init` scaffolds the canonical SDLC layout in an empty git repository (epic AC block 2)**

**Given** a freshly-initialized git repository (`git init` only; no `.claude/` or SDLC trees exist) at `<repo_root>`,

**When** the user runs `sdlc init` from `<repo_root>` (or any cwd inside `<repo_root>` — the command resolves the repo root via `git rev-parse --show-toplevel` when a git repo is detected, else uses `Path.cwd()` for non-git use cases),

**Then** the following filesystem state is created with `<repo_root>` as the parent:

1. **State subtree** (Architecture §443-§456):
   - `.claude/state/` directory.
   - `.claude/state/state.json` with the canonical empty `State` projection (Story 1.10/1.15 schema): `{"schema_version":1,"next_monotonic_seq":0,"phase":1,"epics":{},"stories":{},"tasks":{}}`. The bytes are produced via `json.dumps(State().model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")` + trailing `\n` — matching `state/atomic.py`'s canonical-bytes contract from Story 1.10. The write goes through `state.write_state_atomic_sync` (Story 1.10) on POSIX; on Windows it falls back to `Path.write_bytes` (since `state.atomic` is POSIX-only per `pyproject.toml:199`). The Windows fallback emits a single advisory log line via `_logger.warning("sdlc init on Windows uses non-atomic write fallback for state.json (POSIX-only atomic protocol unavailable). Recommended: run sdlc on Linux/macOS or via WSL2.")` — matching ADR-001's "Linux/macOS first-class; Windows via WSL2" stance.
   - `.claude/state/journal.log` is created as an empty file (`Path.touch()`). Story 1.11's `journal/writer.py:append_sync` is NOT called here — `sdlc init` itself does NOT append a `framework_initialized` journal entry in v1 (the journal stays "no entries until first state mutation"; Story 1.17's `cli/scan.py` adds the first entry on `sdlc scan`, not on `sdlc init`). The empty file is the expected starting state for `journal.iter_entries` (Story 1.11's reader returns an empty iterator on a 0-byte journal).
   - `.claude/state/state.json.lock` and `.claude/state/journal.log.lock` are NOT pre-created — the lock files are created on-demand by `concurrency/locks.py` (Story 1.9). Pre-creating them would couple init to the lock protocol's internals.
   - `.claude/state/hook-hashes.json` is NOT created in v1.16 — Story 2A.5 owns hook tampering detection; the file appears the first time `sdlc trust-hooks` runs.
2. **Static asset subtrees** (Architecture §457-§464, ADR-005):
   - `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`, `.claude/workflows/`, `.claude/memory/`, `.claude/skills/`. Each is created as an empty directory. Where the framework wheel ships content (under `src/sdlc/<tree>/` per ADR-005 force-include patterns added in Task 5), every file from that tree is COPIED into the corresponding `.claude/<tree>/` location, preserving relative paths. v1.16 ships ZERO content trees — the directories are empty placeholders that Stories 2A-2 (specialist registry), 2A-1 (workflow YAMLs), 2A-6 (hooks), 2B-8/9/10 (specialists) will populate. This story creates the SCAFFOLDING; later stories add the contents. The copy step is implemented but iterates over an empty source tree as a no-op for v1.16.
3. **Phase artifact trees** (Architecture §465-§481):
   - `01-Requirement/` (with no contents in v1 — `01-PRODUCT.md`, `02-Research/`, `03-Clarifications.md`, `04-Epics/`, `05-Stories/`, `SIGNOFF.md` are produced by Phase 1 commands in Story 2A.8+).
   - `02-Architecture/` (likewise empty in v1 — Phase 2 commands populate).
   - `03-Implementation/` (likewise empty — Phase 3 commands populate).
   The three top-level phase directories ARE created so `engine/scanner.py` (Story 1.15) finds them on first scan. Their canonical subtrees (`04-Epics/`, `05-Stories/`, `tasks/`) are created LAZILY by the commands that need them, NOT eagerly by `sdlc init`. The scanner already tolerates missing optional subdirectories per Story 1.15's AC1.2.
4. **Output**: stdout prints a confirmation block:
   ```
   Initialized SDLC framework in <repo_root>
     .claude/state/         (state.json, journal.log)
     .claude/{agents,commands,hooks,workflows,memory,skills}/
     01-Requirement/  02-Architecture/  03-Implementation/
   Next: sdlc status
   ```
   Exact bytes are not load-bearing for tests; tests assert presence of the canonical paths via `Path.exists()` rather than parsing stdout. The "Next: sdlc status" line MIRRORS Story 1.17's resume-card "Suggested next:" pattern — first user contact ends with a hint at the next command.
5. **Exit code 0** on successful initialization.

**And** the implementation lives in `src/sdlc/cli/init.py` per Architecture §797 + §1131. The Typer command function `init_cmd()` is registered in `cli/main.py` via `app.command(name="init")(init_cmd)` (or equivalent decorator usage). `init_cmd` defers heavy imports (`from sdlc.state import State, write_state_atomic_sync` etc.) to function-body level per Architecture §488 — the cold-start budget for `sdlc --version` MUST stay under 200 ms (no `state` / `journal` import cost paid until `sdlc init` actually runs).

**And** zero ANSI escape sequences leak into the bare `sdlc init` output (no `--no-color` flag in v1.16; that flag lands in Story 1.17 along with `--json`). Use `typer.echo` (which auto-suppresses color when stdout is not a TTY) or plain `print` via `cli/output.py`. The story does NOT need full `--no-color` / `--json` flag plumbing — that's Story 1.17.

**And** `sdlc init` does NOT mutate `<repo_root>/.git/` and does NOT run any `git` subprocess (other than the optional `git rev-parse --show-toplevel` to find repo root, which is read-only). The "git diff after init" surface is bounded to NEW files only — no source tree modification (NFR-REL-6 spirit applies, even though the hard adopt-mode invariant is Story 3.x's domain).

**AC3 — Re-running `sdlc init` in an already-initialized repo refuses without overwriting (epic AC block 3)**

**Given** a repository where `sdlc init` has already completed once (so `.claude/state/state.json` exists),

**When** the user runs `sdlc init` a second time,

**Then**:

1. The command exits 1 (user error per `cli/exit_codes.py:EXIT_USER_ERROR = 1`, Architecture §540).
2. stderr (NOT stdout) prints the message:
   ```
   sdlc: already initialized at <repo_root>; use `sdlc scan` to refresh state.json
   ```
   `<repo_root>` is the discovered repo root; the message names the path so the user can disambiguate when working in nested git submodules. The error format is plain text in v1 (no `--json` envelope; that lands in Story 1.17 — when `sdlc init --json` is added, the envelope wraps this message in `{"error": {"code": "ERR_ALREADY_INITIALIZED", "message": ...}}`).
3. NO existing files are modified or overwritten. Specifically:
   - `state.json` byte-equality before vs. after the failed second `init` MUST hold (canonical bytes test).
   - `journal.log` mtime + bytes unchanged.
   - All `.claude/` subtrees and phase-artifact trees unchanged.
4. NO new files are created (no half-initialization on re-run).
5. The detection signal is the presence of `.claude/state/state.json`, NOT `.claude/` itself. Rationale: a user could create an empty `.claude/` directory accidentally (or a worktree could ship one); requiring the canonical state.json file means we only refuse when the framework has actually run init before. Empty `.claude/` does NOT trigger refusal — it's tolerated and `sdlc init` proceeds (overwriting nothing because the subtree is empty).

**And** the refusal logic does NOT raise; it returns the exit code via `raise typer.Exit(code=1)`. A `ConfigError` would be misleading (this is a user re-run, not a config malformation).

**And** the message text is NOT internationalized in v1 (English only; i18n is out of scope for the substrate per PRD §472).

**AC4 — `package_data` extension is wired so the wheel ships content trees (epic AC block 2 sub-bullet)**

**Given** ADR-005's deferred extension contract: "package_data extension lands in Story 1.16+ when the first content tree is authored under `src/sdlc/`",

**When** Story 1.16 ships,

**Then**:

1. `pyproject.toml` `[tool.hatch.build.targets.wheel]` is extended to ship the canonical content-tree roots when they exist. Use `force-include` rather than `include` so empty directories ARE NOT silently included (matching ADR-005's "no empty placeholder dirs" decision):
   ```toml
   [tool.hatch.build.targets.wheel]
   packages = ["src/sdlc"]
   # ADR-005: force-include the content trees under src/sdlc/ that ship as
   # package_data. Each tree is created as content lands in later stories
   # (agents → Story 2A.2; commands → Story 2A.6/2A.8+; workflows → Story 2A.1;
   # hooks → Story 2A.4-2A.6; skills/memory/dashboard → Stories 2A/5/x).
   # Empty trees are NOT pre-created; force-include is a no-op until content
   # exists. Story 1.16's `sdlc init` is the consumer — it copies whatever
   # exists from these trees into `.claude/` at init time.
   [tool.hatch.build.targets.wheel.force-include]
   "src/sdlc/agents" = "sdlc/agents"
   "src/sdlc/commands" = "sdlc/commands"
   "src/sdlc/hooks" = "sdlc/hooks"
   "src/sdlc/workflows" = "sdlc/workflows"
   "src/sdlc/skills" = "sdlc/skills"
   "src/sdlc/memory" = "sdlc/memory"
   "src/sdlc/dashboard/static" = "sdlc/dashboard/static"
   ```
   Hatch's `force-include` skips a missing source path (it does NOT error) — confirmed via `hatch build` on a clean checkout where none of these trees yet exist. The `# TODO: ADR-005` comment at `pyproject.toml:39-40` is removed; the comment block above (preserving ADR-005 rationale) replaces it.
2. The init command's "copy package_data into `.claude/`" step uses `importlib.resources` to enumerate each shipped tree:
   ```python
   from importlib.resources import files as _resource_files

   def _copy_package_data_tree(tree_name: str, target_dir: Path) -> None:
       """Copy every file under sdlc/<tree_name>/ into target_dir/, preserving
       relative paths. No-op if the tree doesn't exist in the wheel."""
       try:
           src_root = _resource_files("sdlc") / tree_name
       except (ModuleNotFoundError, FileNotFoundError):
           return
       if not src_root.is_dir():
           return  # tree absent from this wheel build (ADR-005 force-include = no-op)
       target_dir.mkdir(parents=True, exist_ok=True)
       for src_path in src_root.iterdir():
           rel = src_path.name
           dst = target_dir / rel
           if src_path.is_dir():
               # recurse — production-grade depth handler
               _copy_tree_recursive(src_path, dst)
           else:
               dst.write_bytes(src_path.read_bytes())
   ```
   Use `importlib.resources.files` (Python 3.9+, zip-safe) — NOT `pkg_resources` (deprecated) and NOT direct `Path` joins (which break for zipped wheels per Architecture §1216-§1219 install semantics).
3. v1.16 ships ZERO content trees, so the copy step is a no-op for the test fixtures. The infrastructure is in place; future stories drop content into `src/sdlc/agents/index.yaml` etc. and the copy step automatically picks them up.
4. The wheel-shipping smoke test asserts the build artifact: `uv build --wheel; python -m zipfile -l dist/sdlc_framework-0.0.0-py3-none-any.whl | head -50` — for v1.16 the listing contains ONLY `sdlc/__init__.py` and `sdlc/cli/*.py` (whatever the cli module ships). The ADR-005-named content trees appear in the listing only after their owning stories ship.

**AC5 — `cli/` module wiring + boundary table updates (epic AC block 2 + Architecture §1052-§1112 update)**

**Given** `src/sdlc/cli/` does not exist on disk before Story 1.16 (verified by Story 1.15's pre-flight),

**When** Story 1.16 lands,

**Then**:

1. `src/sdlc/cli/__init__.py` is created with `from __future__ import annotations` + an empty body (no re-exports — the cli module is a leaf consumer, NOT a re-export hub). Subsequent stories (1.17, 1.18, etc.) ADD modules under `cli/` but do NOT touch this `__init__.py`.
2. `src/sdlc/cli/main.py` is created with the Typer app instance + the `--version` callback + the `init` subcommand registration. LOC ≤ 100 (this is the entry shell; thick logic lives in `cli/init.py`, `cli/version.py`).
3. `src/sdlc/cli/version.py` is created with `get_version()` per AC1.5. LOC ≤ 30.
4. `src/sdlc/cli/init.py` is created with the `init_cmd()` Typer command function. LOC ≤ 250 (mirroring `engine/scanner.py`'s budget — if you exceed 200, factor out helpers into `cli/_init_helpers.py` per the `journal/_canonical.py`, `journal/_seq.py` precedent).
5. `src/sdlc/cli/output.py` is created as a minimal v1.16 stub: a single `echo(message: str, *, err: bool = False) -> None` helper that wraps `typer.echo`. Story 1.17 expands this with `--no-color`, `--json` envelope handling. Stub size ≤ 30 LOC.
6. `src/sdlc/cli/exit_codes.py` is created with the four constants per Architecture §540:
   ```python
   from __future__ import annotations
   from typing import Final
   EXIT_OK: Final[int] = 0
   EXIT_USER_ERROR: Final[int] = 1
   EXIT_FRAMEWORK_FAILURE: Final[int] = 2
   EXIT_INFRASTRUCTURE: Final[int] = 3
   __all__ = ("EXIT_OK", "EXIT_USER_ERROR", "EXIT_FRAMEWORK_FAILURE", "EXIT_INFRASTRUCTURE")
   ```
7. `scripts/check_module_boundaries.py` is updated: `MODULE_DEPS["cli"].depends_on` is widened from `{"engine", "adopt", "dashboard", "runtime", "config", "errors"}` (current line 132-135) to also include `"state"`, `"journal"`, `"contracts"`, `"ids"`. Concretely:
   ```python
   "cli": ModuleSpec(
       depends_on=frozenset(
           {
               "engine",
               "adopt",
               "dashboard",
               "runtime",
               "config",
               "errors",
               "state",        # NEW (Story 1.16) — cli/init.py writes state.json via state.write_state_atomic_sync
               "journal",      # NEW (Story 1.16) — cli/init.py creates empty journal.log; later cli/scan.py appends entries
               "contracts",    # NEW (Story 1.16) — JournalEntry / State are pydantic contracts; cli imports for re-export & validation
               "ids",          # NEW (Story 1.16) — cli/init.py + cli/scan.py validate canonical IDs from user inputs
           }
       ),
       forbidden_from=frozenset(),
   ),
   ```
   Add inline comments naming Story 1.16 + the import need so future readers understand the widening rationale (mirroring Story 1.15's engine→ids comment style at AC5.3).
8. The boundary linter MUST self-pass after the change: `uv run python scripts/check_module_boundaries.py src/sdlc/ tests/` exits 0. Existing self-tests at `tests/test_check_module_boundaries.py` and `tests/test_module_boundaries_main.py` continue to pass; a new regression test asserts the cli widening:
   ```python
   def test_cli_can_import_state_journal_per_story_116() -> None:
       from scripts.check_module_boundaries import MODULE_DEPS
       cli_deps = MODULE_DEPS["cli"].depends_on
       assert "state" in cli_deps, "Story 1.16 requires cli→state for state.json writes"
       assert "journal" in cli_deps, "Story 1.16 requires cli→journal for journal.log creation"
       assert "ids" in cli_deps, "Story 1.16 requires cli→ids for canonical id validation"
       assert "contracts" in cli_deps, "Story 1.16 requires cli→contracts for pydantic JournalEntry / State"
   ```
9. `cli/init.py` and `cli/main.py` use NO `print()` directly — all stdout goes through `typer.echo` (or `cli/output.py:echo`). All stderr goes through `typer.echo(..., err=True)`. The architecture §489 ban on `print` excludes `cli/` (the exclusion is intentional: cli IS the user-facing surface), but project discipline still routes through `cli/output.py` to keep `--no-color` / `--json` plumbing centralized when Story 1.17 adds it.
10. `cli/init.py` uses NO `os.environ[...]` direct access (Architecture §491) — env-var reads in v1.16 are zero. (Story 1.18's `sdlc logs` may need `NO_COLOR`; that goes through `config/env.py` per Story 1.8.)
11. `cli/init.py` uses NO `subprocess.run` other than the optional `git rev-parse --show-toplevel` — and that ONE invocation is wrapped in a try/except and falls back to `Path.cwd()` on any error (e.g., `git` not on PATH, not in a git repo). Architecture §492 permits `cli/git.py` and `cli/gh.py` as the only modules outside `runtime/` that may invoke external binaries — `cli/init.py` ITSELF does NOT shell out; it imports and uses a `_get_repo_root_or_cwd() -> Path` helper that lives either inline (preferred for v1.16 — single-use) or in `cli/git.py` (Story 1.18 owns the broader `cli/git.py` shell — for v1.16, inline is acceptable to avoid materializing `cli/git.py` before its owning story).
12. New runtime dependencies: add `typer>=0.12,<1` to `[project] dependencies` (was `[]` per ADR-001). Typer is a thin click wrapper that the architecture pre-locked at line 791 + `_bmad/config.toml:40` (`cli_framework: 'typer'`). The cap `<1` is defensive against the major bump; Typer 0.x is the current line. NOTE: `rich` is a transitive dep of Typer; do NOT add it as a direct dep in 1.16 (Story 1.17's `cli/output.py` rich-styling work declares `rich` as a direct dep at that point — mirror the "first-direct-consumer-owns-the-direct-dep" pattern).

**AC6 — Tests prove `sdlc init` is correct, idempotent (refusing-on-rerun), and cross-platform (epic AC block 2 + 3)**

**Given** the test pyramid established by Stories 1.10-1.15,

**When** Story 1.16 lands,

**Then** the test suite contains:

1. **Unit tests** at `tests/unit/cli/test_version.py`:
   - `test_get_version_returns_canonical_string`: `from sdlc.cli.version import get_version; assert get_version() == sdlc.__version__`.
   - `test_get_version_matches_importlib_metadata`: `assert get_version() == importlib.metadata.version("sdlc-framework")`. SKIP if the package is not installed (e.g. running tests from an uninstalled checkout): use `pytest.importorskip` or a guard that catches `importlib.metadata.PackageNotFoundError` and skips with a clear reason. In CI (`uv sync --frozen --group dev` in `quality-gates`), the package IS installed in editable mode, so this runs. Mirror the skip pattern from `tests/integration/test_scan_idempotent.py` (Story 1.15).

2. **Unit tests** at `tests/unit/cli/test_init.py`:
   - `test_sdlc_init_creates_canonical_state_subtree(tmp_path)`: invoke `init_cmd(project_root=tmp_path)` directly (function-level, no Typer runner); assert `(tmp_path / ".claude/state/state.json").exists()`, `(tmp_path / ".claude/state/journal.log").exists()`, `(tmp_path / ".claude/state/journal.log").stat().st_size == 0`.
   - `test_sdlc_init_state_json_is_empty_canonical_state(tmp_path)`: after init, read state.json bytes; assert `json.loads(...)` equals `{"schema_version": 1, "next_monotonic_seq": 0, "phase": 1, "epics": {}, "stories": {}, "tasks": {}}`. Pydantic-validate via `State.model_validate(...)` and assert success. NOTE: This test depends on Story 1.15's `State` schema extension (`phase`, `stories`, `tasks` fields). If Story 1.15 has NOT yet landed at story-implement time, the asserted shape is `{"schema_version": 1, "next_monotonic_seq": 0, "epics": {}}` (Story 1.10's minimal shape); Task 1 pre-flight gates this.
   - `test_sdlc_init_creates_static_asset_dirs(tmp_path)`: assert each of `.claude/agents`, `.claude/commands`, `.claude/hooks`, `.claude/workflows`, `.claude/memory`, `.claude/skills` exists as a directory.
   - `test_sdlc_init_creates_phase_artifact_dirs(tmp_path)`: assert `01-Requirement`, `02-Architecture`, `03-Implementation` each exist as a directory under `tmp_path`.
   - `test_sdlc_init_returns_zero_on_success(tmp_path)`: invoke and assert the function returns `0` (or whatever success sentinel `init_cmd` returns; if it raises `typer.Exit(code=0)`, catch and assert `e.exit_code == 0`).
   - `test_sdlc_init_refuses_on_rerun(tmp_path)`: invoke once; invoke again; assert second invocation raises `typer.Exit` with `exit_code == 1`. Capture stderr via `capsys` (pytest); assert "already initialized" appears in `capsys.readouterr().err`.
   - `test_sdlc_init_rerun_does_not_modify_state_json(tmp_path)`: invoke once; capture `state.json` bytes; invoke second time (catching `typer.Exit`); re-read state.json; assert byte-equality. The hash test catches a subtle bug: if the dev accidentally writes `state.json` then checks for prior init, the second-run write would change mtime even if content matches.
   - `test_sdlc_init_rerun_does_not_create_new_files(tmp_path)`: snapshot the recursive file list after first init; re-run; snapshot again; assert sets are equal (no new files appeared).
   - `test_sdlc_init_tolerates_pre_existing_empty_dot_claude_dir(tmp_path)`: `(tmp_path / ".claude").mkdir()` BEFORE init (no state.json yet); invoke; assert init proceeds and creates the canonical layout (per AC3.5 — empty `.claude/` is not the "already initialized" signal).
   - `test_sdlc_init_does_not_run_git_subprocess_when_no_git(tmp_path)`: invoke in a non-git directory (no `.git/`); assert `subprocess.run` is NOT called for `git rev-parse` (use `unittest.mock.patch` on `subprocess.run` and assert no calls). The fallback path uses `Path.cwd()` directly. NOTE: `cli/init.py` may catch `FileNotFoundError` (git missing) AND `subprocess.CalledProcessError` (git installed but cwd not in a repo) — both fall back gracefully.

3. **Unit tests** at `tests/unit/cli/test_main.py`:
   - `test_main_app_has_init_subcommand`: `from sdlc.cli.main import app; from typer.testing import CliRunner; runner = CliRunner(); result = runner.invoke(app, ["--help"]); assert "init" in result.stdout`.
   - `test_main_app_version_flag_prints_version_and_exits_zero`: `result = runner.invoke(app, ["--version"]); assert result.exit_code == 0; assert sdlc.__version__ in result.stdout`. NOTE: Typer's `CliRunner` captures stdout; assert the bare version string appears (e.g. `"0.0.0"`).
   - `test_main_app_no_args_shows_help`: `result = runner.invoke(app, []); assert result.exit_code in (0, 2)` (Typer's default for missing-subcommand-with-help is 2; we override `no_args_is_help=True` which exits 0 — accept both for resilience to Typer version drift). Assert `"Usage:" in result.stdout` regardless.

4. **Integration test** at `tests/integration/test_sdlc_init_e2e.py` with `pytestmark = pytest.mark.integration`:
   - `test_sdlc_init_via_subprocess_creates_layout`: spawn `subprocess.run(["uv", "run", "sdlc", "init"], cwd=tmp_path, ...)`; assert exit code 0; assert all canonical paths exist. SKIP on Windows if `shutil.which("uv") is None` (mirror Story 1.13/1.15 subprocess-test skip pattern). This catches any console-script wiring bug that unit tests miss.
   - `test_sdlc_version_via_subprocess_prints_version`: spawn `subprocess.run(["uv", "run", "sdlc", "--version"], ...)`; assert exit code 0; assert stdout matches the regex `^sdlc \d+\.\d+\.\d+\s*$` (or the literal `sdlc 0.0.0\n` for v0.0.0). SKIP on Windows where `uv` is missing.

5. **Wheel-build smoke test** (optional but recommended) at `tests/integration/test_wheel_build.py`:
   - `test_wheel_contains_only_sdlc_package_in_v1_16`: `subprocess.run(["uv", "build", "--wheel"], cwd=<repo_root>)`; list the wheel's contents via `zipfile.ZipFile.namelist`; assert no entries match `sdlc/agents/`, `sdlc/commands/`, etc. (those trees don't exist yet). Assert `sdlc/__init__.py`, `sdlc/cli/main.py`, `sdlc/cli/version.py`, `sdlc/cli/init.py` ARE present. This is a regression gate: the moment Story 2A.1 ships `src/sdlc/workflows/sdlc-start.yaml`, this test's "no workflows/" assertion needs flipping. SKIP on CI matrix cells where `uv build` is not available; this is a dev-host smoke test primarily.

**And** `tests/unit/cli/__init__.py` is created as an empty pytest-collection sentinel with `from __future__ import annotations`.

**And** all new tests carry the appropriate marker (`pytest.mark.unit` for `tests/unit/cli/`, `pytest.mark.integration` for `tests/integration/`); markers already declared in `pyproject.toml:181-186`.

**AC7 — ADR-019 records the CLI skeleton + Typer adoption + boundary widening + idempotency contract**

**Given** NFR-MAINT-5 ("every load-bearing decision recorded as an ADR") and the in-flight ADR sequence (ADR-018 reserved for Story 1.15 per `1-15-engine-scanner-skeleton.md` Task 1 pre-flight),

**When** Story 1.16 lands,

**Then** `docs/decisions/ADR-019-cli-skeleton-typer-adoption.md` is authored using `docs/decisions/adr-template.md` covering:

1. **Status:** Accepted, dated to story-implement day.
2. **Context:** FR1, FR47, FR50 mapping; the 6-month-deferred ADR-005 contract; cli/ module materialization timing; Typer adoption per Architecture §791 + `_bmad/config.toml:40`.
3. **Decision:**
   - Typer (>=0.12,<1) is the v1 CLI framework; Click and argparse rejected (rationale below).
   - `cli/main.py` is the Typer app; `cli/version.py`, `cli/init.py`, `cli/output.py`, `cli/exit_codes.py` are subordinate modules.
   - `[project.scripts] sdlc = "sdlc.cli.main:app"` is the canonical entry point.
   - `[tool.hatch.build.targets.wheel.force-include]` ships the seven content-tree paths conditionally; missing trees are no-ops.
   - `MODULE_DEPS["cli"].depends_on` widens to include `state`, `journal`, `contracts`, `ids`.
   - `sdlc init` is idempotent-via-refusal: second run fails with exit 1 + clear message; never partial-overwrites.
   - Console script's static `__version__` source is `sdlc/__init__.py:3` (matches ADR-001's deferred-dynamic-version contract); `importlib.metadata.version("sdlc-framework")` is asserted to match in CI but is NOT the runtime source until ADR-008's first-release revisit.
4. **Alternatives considered:**
   - `argparse` (stdlib): rejected — saves ~80 KB of transitive deps but loses Typer's type-driven argument parsing, auto-generated `--help` from docstrings, and decorator-based subcommand registration. Architecture pre-locked Typer.
   - `click` directly: rejected — Typer is a thin wrapper that adds type-hint-driven argument parsing and subcommand decorators. Click would force boilerplate Typer hides.
   - `sdlc init --force` to overwrite on re-run: rejected for v1 — `--force-bypass-signoff` is the only "force" flag in the v1 spec (PRD §FR38). `sdlc init --force` would be a non-trivial new flag with security implications (overwriting state.json is dangerous; if the user really wants a fresh start, they delete `.claude/` manually).
   - Materializing `cli/git.py` for the `git rev-parse` call: rejected for v1.16 — Story 1.18's `sdlc trace` / `sdlc logs` are the actual `cli/git.py` consumers; pulling forward the module just for a 5-line helper inflates the story scope. Inline `_get_repo_root_or_cwd()` in `cli/init.py` until Story 1.18 lands.
   - Pre-creating `.claude/state/hook-hashes.json` in v1.16: rejected — Story 2A.5 owns hook tampering detection; pre-creating an empty hash dict is dead infrastructure that misleads code review.
   - Eagerly creating `01-Requirement/04-Epics/`, `05-Stories/`, `03-Implementation/tasks/` subtrees: rejected — Story 1.15's scanner tolerates missing optional subtrees; the Phase 1/2/3 commands (Story 2A.x) create them lazily when content is authored. Eager creation adds noise that confuses `git status` on the framework's own dogfood checkout.
   - Adding a `framework_initialized` journal entry on `sdlc init`: rejected — `sdlc init` is the SUBSTRATE creation; the journal is an audit log of state mutations, and `init` does not mutate state (it CREATES the empty initial state). The first journal entry is appended by Story 1.17's `cli/scan.py:cmd_scan` on first `sdlc scan`. ADR-014 (journal) records: "the first entry corresponds to the first state mutation."
5. **Consequences:**
   - First user contact (`pip install && sdlc init && sdlc status` per Architecture §1408) is now end-to-end demonstrable. Story 1.17 closes the demo by adding `sdlc scan` + `sdlc status` so "Phase 1, no progress yet" appears.
   - The Typer dep adds ~5 transitive deps (click, rich, shellingham, typer-extras, etc.). Cold-start `sdlc --version` is measured at ~80-120 ms on a typical dev host; well within the 200 ms budget. If a future regression pushes past 200 ms, the diagnosis path is `python -X importtime -m sdlc.cli.main --version | sort -k 2 -n | tail` (the Architecture §488 deferred-import discipline is the mitigation — every command body should `from sdlc.<module> import ...` lazily).
   - The cli→state widening means all four cli modules (init, scan, rebuild_state, etc., across Stories 1.16-1.20) can write state.json without further boundary changes. This is intentional — the cli IS the surface that owns I/O write side effects; `engine/` stays read-only per Story 1.15's scanner contract.
   - `package_data` force-include pattern is now active. Future stories adding `src/sdlc/<tree>/<file>` automatically get the file shipped in the wheel — no further pyproject.toml edit. This is a small "infrastructure debt repayment" — Stories 2A.x can focus on content, not packaging.
   - The empty placeholder dirs (`.claude/agents/`, `.claude/commands/`, etc.) created by `sdlc init` in v1.16 are an end-user-visible commitment to the Architecture §457-§464 layout. Stories 2A.x WILL ship content into them. If Story 1.16 or any 2A.x story ever needs to RENAME a tree (e.g. `claude_hooks/` → `hooks/` per the architecture rename in §1218), it's a minor breaking change for any user who already ran `sdlc init` — handled via the `sdlc migrate-vN` framework (Story 1.19).
6. **Revisit-by:** Story 1.21 (wire-format v1 lock — the moment console-script API is locked at v1.0; flag/subcommand additions after that point require RFC + ADR amendment).
7. **References:** Architecture §117 (FR1 mapping), §388 (v0.2 implementation sequence), §443 (canonical filesystem layout), §488-§494 (cli code-style rules), §540-§548 (exit codes), §765-§811 (module specification), §1052-§1112 (boundary table), §1131 (FR1 lives in cli/init.py), §1173 (FR47 lives in pyproject.toml + sdlc/__init__.py), §1176 (FR50 lives in pyproject.toml hatch.build), §1216-§1219 (build + package_data), §1402-§1408 (v0.2 implementation sequence). PRD §FR1, §FR47, §FR50, §472 (Python 3.10+ macOS/Linux first-class). ADR-001 (pyproject metadata), ADR-005 (package_data layout), ADR-013 (atomic state write), ADR-014 (journal), ADR-018 (Story 1.15 engine scanner — extends State model that init writes).

**And** `docs/decisions/index.md` gains the row `| [019](ADR-019-cli-skeleton-typer-adoption.md) | CLI skeleton + Typer + boundary widening + idempotency | 1.16 | Accepted |` after ADR-018's row. If ADR-018 has not yet landed at story-implement time (Story 1.15 still in `ready-for-dev`), Story 1.16 takes the next free number after the most recent ADR on disk and the index reflects that. The numbering is stable because ADRs are append-only — each story ADR claims its number in its own commit.

## Tasks / Subtasks

- [ ] **Task 1: Pre-flight verification of dependencies, environment, and prior-story state (AC: all)**
  - [ ] Verify Story 1.10 deliverables on disk: `src/sdlc/state/atomic.py` exists and exports `write_state_atomic_sync` (sprint-status `1-10: done`). Smoke: `uv run python -c "from sdlc.state import State, write_state_atomic_sync; print('ok')"`.
  - [ ] Verify Story 1.11 deliverables: `src/sdlc/journal/__init__.py` exports `append_sync`. Smoke: `uv run python -c "from sdlc.journal import append_sync, iter_entries; print('ok')"`. Story 1.11 is in `review` per sprint-status snapshot 2026-05-08; `sdlc init` does NOT call `append_sync` (it only `Path.touch()`s journal.log), so 1.11 review status is non-blocking.
  - [ ] Verify Story 1.6 deliverables: `src/sdlc/ids/__init__.py` exports `parse_epic_id`, `parse_story_id`, `parse_task_id`. Smoke: `uv run python -c "from sdlc.ids import parse_epic_id, parse_story_id, parse_task_id; print('ok')"`. Story 1.16 imports for boundary-table widening but the actual id-validation use is in Story 1.17's `cli/scan.py`; 1.16's only direct id consumer is the new test for the boundary linter. Hard dep.
  - [ ] Determine whether Story 1.15 (`engine/scanner.py` + `State` schema extension with `phase`/`stories`/`tasks`) has landed on disk. Sprint-status 2026-05-08 says `1-15: ready-for-dev` (NOT done). Run: `test -d src/sdlc/engine && echo "ENGINE_PRESENT" || echo "ENGINE_MISSING"`. Run: `grep -F "phase: int" src/sdlc/state/model.py && echo "STATE_EXTENDED" || echo "STATE_NOT_EXTENDED"`. Branch behavior:
    - **If Story 1.15 has landed** (engine present + state extended): `sdlc init` writes the extended canonical bytes `{"schema_version":1,"next_monotonic_seq":0,"phase":1,"epics":{},"stories":{},"tasks":{}}`. Tests assert the extended shape.
    - **If Story 1.15 has NOT landed yet**: `sdlc init` writes Story 1.10's minimal shape `{"schema_version":1,"next_monotonic_seq":0,"epics":{}}`. Tests assert the minimal shape. Story 1.15 dev later picks up the State extension and re-runs the goldens (their AC5 is already aware of this).
    - The decision branches via a runtime check on `State.model_fields.keys()`: if `"phase" in State.model_fields`, write extended; else write minimal. The State() default-factory handles either case automatically — pydantic supplies the defaults that exist.
  - [ ] Verify boundary-linter location: `scripts/check_module_boundaries.py` exists with the `MODULE_DEPS["cli"]` entry at lines 132-135. Confirm `depends_on=frozenset({"engine", "adopt", "dashboard", "runtime", "config", "errors"})`. Task 5 widens this.
  - [ ] Verify ADR numbering: existing ADRs are 001-014 + 015 (Story 1.12 if landed) + 016 (Story 1.13 if landed) + 017 (Story 1.14 if landed) + 018 (Story 1.15 if landed) per `docs/decisions/index.md`. Story 1.16 (this story) authors **ADR-019**. If 015-018 haven't all shipped, take the next free number after the most recent ADR on disk; the index reflects whatever is actually present.
  - [ ] Verify pyproject.toml current state: `[project] dependencies` is `["pydantic>=2,<3", "pyyaml>=6,<7"]` (line 11-14). `[project.scripts]` is commented out (line 16-18). `[tool.hatch.build.targets.wheel]` has `packages = ["src/sdlc"]` only (line 37-40). Task 2 wires the console script + ADR-005 force-include patterns.
  - [ ] Confirm `src/sdlc/cli/` does not exist: `test -d src/sdlc/cli && echo "EXISTS — abort, Story 1.16 expects fresh creation" || echo "ok, fresh"`. If `src/sdlc/cli/` already exists from a half-merged earlier story, HALT and reconcile manually before proceeding.
  - [ ] Verify Typer is NOT yet a dep: `grep -F "typer" pyproject.toml` returns no match. Task 2 adds it.
  - [ ] Verify `tests/unit/cli/` does not exist: `test -d tests/unit/cli && echo "ABORT" || echo "ok"`. Task 6 creates it.
  - [ ] Verify the existing pre-commit hooks pass on `main`: `uv run pre-commit run --all-files`. Establish a green baseline before mutating.

- [ ] **Task 2: Wire console script + Typer dep + package_data force-include in `pyproject.toml` (AC: #1.6, #4, #5.12)**
  - [ ] Open `pyproject.toml`. In `[project] dependencies`, add `"typer>=0.12,<1"` after `"pyyaml>=6,<7"`. Final `dependencies` block:
    ```toml
    dependencies = [
        "pydantic>=2,<3",   # cap: pydantic 2→3 will introduce schema breaks (v3 is on the roadmap)
        "pyyaml>=6,<7",     # cap: pyyaml 6→7 has not been released; defensive guard against future major
        "typer>=0.12,<1",   # cap: typer 0→1 is the architectural pre-lock (Architecture §791); thin click wrapper
    ]
    ```
  - [ ] Uncomment `[project.scripts]`. Replace lines 16-18 with:
    ```toml
    [project.scripts]
    sdlc = "sdlc.cli.main:app"
    ```
    Remove the `# TODO: Wire CLI entry point in Story 1.16` comment — the wiring lands here.
  - [ ] Replace the `# TODO: ADR-005` comment block at lines 39-40 with the ADR-005 force-include extension. Final `[tool.hatch.build.targets.wheel]` section:
    ```toml
    [tool.hatch.build.targets.wheel]
    packages = ["src/sdlc"]
    # ADR-005: force-include the content trees under src/sdlc/ that ship as
    # package_data. Each tree is created as content lands in later stories
    # (agents → Story 2A.2; commands → Story 2A.6/2A.8+; workflows → Story 2A.1;
    # hooks → Story 2A.4-2A.6; skills/memory/dashboard → Stories 2A/5/x).
    # Empty trees are NOT pre-created; force-include is a no-op when the source
    # path is missing (verified: hatch silently skips missing force-include sources).
    # Story 1.16's `sdlc init` is the consumer — it copies whatever exists from
    # these trees into `.claude/` at init time.

    [tool.hatch.build.targets.wheel.force-include]
    "src/sdlc/agents" = "sdlc/agents"
    "src/sdlc/commands" = "sdlc/commands"
    "src/sdlc/hooks" = "sdlc/hooks"
    "src/sdlc/workflows" = "sdlc/workflows"
    "src/sdlc/skills" = "sdlc/skills"
    "src/sdlc/memory" = "sdlc/memory"
    "src/sdlc/dashboard/static" = "sdlc/dashboard/static"
    ```
  - [ ] Run `uv lock` to refresh `uv.lock` with Typer + its transitive deps (click, rich, shellingham). Commit the lock change in the same commit as the dep addition.
  - [ ] Smoke-test the lock: `uv sync --frozen --group dev` from a clean checkout; assert success. Run `uv run python -c "import typer; print(typer.__version__)"` to confirm Typer imports.
  - [ ] Smoke-test the wheel build: `uv build --wheel`; assert `dist/sdlc_framework-0.0.0-py3-none-any.whl` exists; run `python -m zipfile -l dist/sdlc_framework-0.0.0-py3-none-any.whl` and verify the listing includes `sdlc/__init__.py` (and after Task 3 lands, `sdlc/cli/main.py` etc.). The seven force-include trees do NOT appear yet (no source files); that's expected.

- [ ] **Task 3: Create `cli/` module skeleton (`__init__.py`, `main.py`, `version.py`, `output.py`, `exit_codes.py`) (AC: #1, #5.1-#5.6, #5.9)**
  - [ ] Create `src/sdlc/cli/__init__.py` with content:
    ```python
    """SDLC framework CLI surface (Story 1.16+).

    Public entry point: the `sdlc` console script registered in pyproject.toml
    [project.scripts] points at `sdlc.cli.main:app` (a Typer application).
    Submodules are leaf consumers — the package itself does not re-export.
    """

    from __future__ import annotations
    ```
    LOC ≤ 10. No `__all__` (no re-exports). The docstring satisfies ruff's package-docstring expectation.
  - [ ] Create `src/sdlc/cli/exit_codes.py`:
    ```python
    """CLI exit code constants (Architecture §540-§548)."""

    from __future__ import annotations

    from typing import Final

    EXIT_OK: Final[int] = 0
    EXIT_USER_ERROR: Final[int] = 1
    EXIT_FRAMEWORK_FAILURE: Final[int] = 2
    EXIT_INFRASTRUCTURE: Final[int] = 3

    __all__ = (
        "EXIT_OK",
        "EXIT_USER_ERROR",
        "EXIT_FRAMEWORK_FAILURE",
        "EXIT_INFRASTRUCTURE",
    )
    ```
    LOC ≤ 25.
  - [ ] Create `src/sdlc/cli/output.py` (minimal v1.16 stub):
    ```python
    """CLI output helpers (Story 1.16 minimal stub; Story 1.17 expands with
    --no-color / --json envelope handling)."""

    from __future__ import annotations

    import typer

    __all__ = ("echo",)


    def echo(message: str, *, err: bool = False) -> None:
        """Emit ``message`` on stdout (or stderr if ``err=True``).

        Wraps ``typer.echo`` so Story 1.17 can centralize ``--no-color`` /
        ``--json`` plumbing in one place. v1.16 forwards verbatim.
        """
        typer.echo(message, err=err)
    ```
    LOC ≤ 30.
  - [ ] Create `src/sdlc/cli/version.py`:
    ```python
    """`sdlc --version` handler (FR47, AC1.4)."""

    from __future__ import annotations

    import sdlc

    __all__ = ("get_version",)


    def get_version() -> str:
        """Return the canonical framework version string.

        Sourced from ``sdlc.__version__`` per ADR-001's deferred-dynamic-version
        contract; ``importlib.metadata.version("sdlc-framework")`` is asserted
        to match in CI but is not the runtime source until ADR-008's first-release
        revisit.
        """
        return sdlc.__version__
    ```
    LOC ≤ 25.
  - [ ] Create `src/sdlc/cli/main.py`:
    ```python
    """Typer application entry — registers all `sdlc <subcommand>` handlers.

    Per Architecture §488, command-body imports are deferred to keep the
    cold-start budget under 200 ms; only the Typer machinery is imported at
    module level.
    """

    from __future__ import annotations

    import typer

    from sdlc.cli.version import get_version

    __all__ = ("app",)


    def _version_callback(value: bool) -> None:  # noqa: FBT001 (Typer flag)
        if value:
            typer.echo(f"sdlc {get_version()}")
            raise typer.Exit(code=0)


    app = typer.Typer(
        name="sdlc",
        help="Deterministic, auditable, multi-agent SDLC orchestration framework.",
        no_args_is_help=True,
        add_completion=False,
    )


    @app.callback()
    def _root(
        version: bool = typer.Option(  # noqa: FBT001
            False,
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Print the installed version and exit.",
        ),
    ) -> None:
        """SDLC framework CLI."""
        # Body intentionally empty: Typer dispatches to the subcommand below.


    @app.command(name="init")
    def init_command(
        adopt: bool = typer.Option(  # noqa: FBT001
            False,
            "--adopt",
            help="Brownfield mode (Story 3.1+; v1.16 does not implement --adopt).",
            hidden=True,
        ),
    ) -> None:
        """Initialize the SDLC framework in the current git repository."""
        if adopt:
            typer.echo(
                "sdlc init --adopt is not implemented in v1.16 (Story 3.1+).",
                err=True,
            )
            raise typer.Exit(code=1)
        from sdlc.cli.init import run_init  # deferred per Architecture §488

        run_init()
    ```
    LOC ≤ 100. Note: the `--adopt` flag is registered as `hidden=True` so `sdlc init --help` does NOT advertise it in v1.16 — the flag exists as a placeholder so Story 3.1 can flip `hidden=False` without breaking CLI compatibility. The "not implemented" path is the AC-compliant refusal until Story 3.1 lands the brownfield orchestrator.
  - [ ] Run `uv run mypy --strict src/sdlc/cli/` — must pass on all five files.
  - [ ] Run `uv run ruff check src/sdlc/cli/` — must pass.
  - [ ] Run `uv run ruff format --check src/sdlc/cli/` — must pass.

- [ ] **Task 4: Implement `cli/init.py` — the canonical-layout scaffolder (AC: #2, #3, #4, #5.4)**
  - [ ] Create `src/sdlc/cli/init.py`. Top-of-file order:
    1. Module docstring: "`sdlc init` (greenfield) implementation (FR1, Architecture §1131, §443). Scaffolds the canonical SDLC layout: `.claude/state/`, `.claude/{agents,commands,hooks,workflows,memory,skills}/`, `01-Requirement/`, `02-Architecture/`, `03-Implementation/`. Idempotent-via-refusal: re-running on an already-initialized repo exits 1 without overwriting (AC3)."
    2. `from __future__ import annotations`
    3. Stdlib imports (alphabetized): `import json`, `import logging`, `import shutil`, `import subprocess`, `import sys`, `from importlib.resources import files as _resource_files`, `from importlib.resources.abc import Traversable`, `from pathlib import Path`, `from typing import Final`
    4. Third-party imports: `import typer`
    5. SDLC imports: `from sdlc.cli.exit_codes import EXIT_USER_ERROR`, `from sdlc.cli.output import echo`, `from sdlc.state import State` (deferred — see below for the import strategy decision)
    6. `_logger = logging.getLogger(__name__)`
    7. Module-level constants:
       ```python
       _CLAUDE_DIR: Final[str] = ".claude"
       _STATE_SUBDIR: Final[str] = ".claude/state"
       _STATIC_ASSET_TREES: Final[tuple[str, ...]] = (
           "agents",
           "commands",
           "hooks",
           "workflows",
           "memory",
           "skills",
       )
       _PHASE_DIRS: Final[tuple[str, ...]] = (
           "01-Requirement",
           "02-Architecture",
           "03-Implementation",
       )
       _ALREADY_INITIALIZED_TEMPLATE: Final[str] = (
           "sdlc: already initialized at {root}; "
           "use `sdlc scan` to refresh state.json"
       )
       ```
  - [ ] Implement `_get_repo_root_or_cwd() -> Path`:
    - Try `subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False, timeout=5)`.
    - If `result.returncode == 0`: return `Path(result.stdout.strip()).resolve()`.
    - If `FileNotFoundError` (git missing) or non-zero exit (not in a git repo) or `subprocess.TimeoutExpired`: fall back to `Path.cwd().resolve()`.
    - Wrap the entire thing in a single try/except that catches `OSError`, `subprocess.SubprocessError`, `FileNotFoundError`. The fallback path is silent (no warning) — `sdlc init` is meant to work outside git repos for tests + odd environments.
  - [ ] Implement `_state_already_exists(root: Path) -> bool`:
    - Return `(root / ".claude" / "state" / "state.json").exists()`. Per AC3.5, this is the canonical "is initialized" signal.
  - [ ] Implement `_canonical_initial_state_bytes() -> bytes`:
    ```python
    def _canonical_initial_state_bytes() -> bytes:
        """Canonical bytes for the empty initial State (Story 1.10/1.15 schema).

        Follows the canonical-bytes contract from `state/atomic.py`: sort_keys,
        no ASCII escaping, compact separators, trailing newline.
        """
        from sdlc.state import State  # deferred per Architecture §488

        payload = State().model_dump(mode="json")
        return (
            json.dumps(
                payload,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ```
    NOTE: pydantic's `model_dump(mode="json")` supplies whatever default fields the current `State` schema has. If Story 1.15 has not yet extended the model, `payload` is `{"schema_version": 1, "next_monotonic_seq": 0, "epics": {}}`; if it has, `payload` includes `phase`, `stories`, `tasks` too. Either way, the canonical bytes are correct for the current schema.
  - [ ] Implement `_write_state_json(state_path: Path) -> None`:
    ```python
    def _write_state_json(state_path: Path) -> None:
        """Write the canonical initial state.json.

        Uses `state.write_state_atomic_sync` on POSIX; on Windows falls back to
        `Path.write_bytes` (since `state.atomic` is POSIX-only per
        pyproject.toml omit list and Architecture §573).
        """
        from sdlc.state import State  # deferred per Architecture §488

        canonical = State()
        if sys.platform == "win32":
            _logger.warning(
                "sdlc init on Windows uses non-atomic write fallback for "
                "state.json (POSIX-only atomic protocol unavailable). "
                "Recommended: run sdlc on Linux/macOS or via WSL2."
            )
            state_path.write_bytes(_canonical_initial_state_bytes())
            return
        from sdlc.state import write_state_atomic_sync  # deferred

        write_state_atomic_sync(canonical, target=state_path)
    ```
    NOTE: `write_state_atomic_sync` may have a slightly different signature than `(state, target=...)` — verify against `src/sdlc/state/atomic.py` and adjust. The pattern is "write canonical bytes to state.json via the atomic protocol".
  - [ ] Implement `_create_state_subtree(root: Path) -> None`:
    - `state_dir = root / _STATE_SUBDIR; state_dir.mkdir(parents=True, exist_ok=True)`.
    - `_write_state_json(state_dir / "state.json")`.
    - `(state_dir / "journal.log").touch()` — creates an empty file. Existing-file no-op (touch is idempotent).
  - [ ] Implement `_create_static_asset_dirs(root: Path) -> None`:
    - For each `tree in _STATIC_ASSET_TREES`: `(root / _CLAUDE_DIR / tree).mkdir(parents=True, exist_ok=True)`.
    - Then call `_copy_package_data_tree(tree, root / _CLAUDE_DIR / tree)` for each (per AC4.2).
  - [ ] Implement `_copy_package_data_tree(tree_name: str, target_dir: Path) -> None`:
    ```python
    def _copy_package_data_tree(tree_name: str, target_dir: Path) -> None:
        """Copy every file under sdlc/<tree_name>/ from the wheel into target_dir/.

        Uses importlib.resources for zip-safe enumeration. No-op when the tree
        doesn't exist in the wheel (ADR-005 force-include = silent skip on
        missing source).
        """
        try:
            src_root: Traversable = _resource_files("sdlc") / tree_name
        except (ModuleNotFoundError, FileNotFoundError):
            return
        if not src_root.is_dir():
            return
        for src_entry in src_root.iterdir():
            _copy_traversable_entry(src_entry, target_dir / src_entry.name)
    ```
  - [ ] Implement `_copy_traversable_entry(src: Traversable, dst: Path) -> None`:
    ```python
    def _copy_traversable_entry(src: Traversable, dst: Path) -> None:
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            for child in src.iterdir():
                _copy_traversable_entry(child, dst / child.name)
        else:
            dst.write_bytes(src.read_bytes())
    ```
    NOTE: `Traversable` is the abstract base; works for both filesystem and zip-based resources.
  - [ ] Implement `_create_phase_dirs(root: Path) -> None`:
    - For each `phase_dir in _PHASE_DIRS`: `(root / phase_dir).mkdir(parents=True, exist_ok=True)`.
  - [ ] Implement the public `run_init() -> None`:
    ```python
    def run_init() -> None:
        """Scaffold the canonical SDLC layout in the current repo.

        Idempotent-via-refusal: if `.claude/state/state.json` already exists,
        prints an error to stderr and exits 1 (no overwrite, no partial write).
        """
        root = _get_repo_root_or_cwd()
        if _state_already_exists(root):
            echo(
                _ALREADY_INITIALIZED_TEMPLATE.format(root=root),
                err=True,
            )
            raise typer.Exit(code=EXIT_USER_ERROR)
        _create_state_subtree(root)
        _create_static_asset_dirs(root)
        _create_phase_dirs(root)
        echo(f"Initialized SDLC framework in {root}")
        echo(f"  .claude/state/         (state.json, journal.log)")
        echo(f"  .claude/{{agents,commands,hooks,workflows,memory,skills}}/")
        echo(f"  01-Requirement/  02-Architecture/  03-Implementation/")
        echo(f"Next: sdlc status")
    ```
  - [ ] Verify LOC ≤ 250 for `cli/init.py`. If exceeded, factor out `_copy_package_data_tree` + `_copy_traversable_entry` into `src/sdlc/cli/_init_helpers.py` (single-underscore prefix marks private; mirror `journal/_canonical.py` precedent).
  - [ ] **Forbidden patterns at code-review time** (mirror Stories 1.10–1.15):
    - `print()` — use `typer.echo` via `cli/output.py:echo`.
    - `time.time()` / `datetime.now()` — `sdlc init` doesn't compute timestamps in v1.16.
    - `os.environ[...]` direct — use `config/env.py` (none needed in v1.16).
    - `subprocess.run` other than the optional `git rev-parse --show-toplevel`.
    - Bare `except:` / `except Exception:` — narrow catches (`OSError`, `subprocess.SubprocessError`, `FileNotFoundError`, `ModuleNotFoundError`).
    - Mutating function arguments.
    - Float arithmetic.
  - [ ] Type annotations: every public and private function fully annotated. `mypy --strict` must pass.

- [ ] **Task 5: Update `MODULE_DEPS` boundary table + linter self-tests (AC: #5.7, #5.8)**
  - [ ] Edit `scripts/check_module_boundaries.py`. Locate `MODULE_DEPS["cli"]` at lines 132-135. Replace with:
    ```python
    "cli": ModuleSpec(
        depends_on=frozenset(
            {
                "engine",
                "adopt",
                "dashboard",
                "runtime",
                "config",
                "errors",
                # Story 1.16 widening: cli/init.py + cli/scan.py (Story 1.17) +
                # cli/rebuild_state.py (Story 1.20) all need direct access to
                # state.json + journal.log writes. The architecture's "cli is
                # the only module that may invoke external binaries" rule
                # (Architecture §1105) is satisfied by gating subprocess use
                # to cli/git.py + cli/gh.py + runtime/claude.py; the boundary
                # widening is orthogonal and concerns import-graph dependencies.
                "state",
                "journal",
                "contracts",
                "ids",
            }
        ),
        forbidden_from=frozenset(),
    ),
    ```
  - [ ] Run the boundary linter: `uv run python scripts/check_module_boundaries.py src/sdlc/ tests/`. Exit code MUST be 0. If any unrelated module fires, that's a pre-existing issue; only the cli widening is in this story's scope.
  - [ ] Add the regression test in `tests/test_check_module_boundaries.py`:
    ```python
    def test_cli_can_import_state_journal_per_story_116() -> None:
        from scripts.check_module_boundaries import MODULE_DEPS
        cli_deps = MODULE_DEPS["cli"].depends_on
        assert "state" in cli_deps, (
            "Story 1.16 requires cli→state for state.json writes"
        )
        assert "journal" in cli_deps, (
            "Story 1.16 requires cli→journal for journal.log creation"
        )
        assert "ids" in cli_deps, (
            "Story 1.16 requires cli→ids for canonical id validation in scan/rebuild"
        )
        assert "contracts" in cli_deps, (
            "Story 1.16 requires cli→contracts for pydantic JournalEntry / State"
        )
    ```
    Match the existing test's marker convention — read the top of `tests/test_check_module_boundaries.py` to confirm whether `pytest.mark.unit` is module-level. If yes, the marker auto-applies; if no, omit.
  - [ ] Run `uv run pre-commit run boundary-validator --all-files` — must pass.
  - [ ] Verify the existing tests at `tests/test_module_boundaries_main.py` still pass.

- [ ] **Task 6: Tests — unit + integration + wheel-build smoke (AC: #6)**
  - [ ] Create `tests/unit/cli/__init__.py` (empty pytest collection sentinel; needs `from __future__ import annotations` per project convention).
  - [ ] Create `tests/unit/cli/test_version.py` with `pytestmark = pytest.mark.unit` and the two tests from AC6.1. The `importlib.metadata` test guards against `PackageNotFoundError` to skip gracefully when running tests outside an editable install.
  - [ ] Create `tests/unit/cli/test_main.py` with `pytestmark = pytest.mark.unit` and the three tests from AC6.3 (using `typer.testing.CliRunner`).
  - [ ] Create `tests/unit/cli/test_init.py` with `pytestmark = pytest.mark.unit` and the nine tests from AC6.2. Key implementation notes:
    - The `test_sdlc_init_state_json_is_empty_canonical_state` test branches on `State.model_fields`: if `phase` is in the fields (Story 1.15 landed), assert the extended shape; else assert Story 1.10's minimal shape. Use a helper `_expected_initial_state_payload() -> dict[str, Any]` to encapsulate the branch.
    - The `test_sdlc_init_does_not_run_git_subprocess_when_no_git` test uses `unittest.mock.patch("sdlc.cli.init.subprocess.run")` to verify zero calls in the no-git path. NOTE: the patch target is the IMPORT site (`sdlc.cli.init.subprocess.run`), not `subprocess.run` globally — pytest's mock semantics. If git IS installed and tmp_path happens to be inside a real git checkout (rare on CI), the test creates a non-git subdir explicitly to avoid the cwd-walk-up. Use `tmp_path / "isolated"` and `chdir` there if needed.
    - The `test_sdlc_init_refuses_on_rerun` test invokes `init_cmd` (or directly `run_init`) twice; the second invocation raises `typer.Exit`. Catch and assert `e.exit_code == 1`. Use pytest's `capsys.readouterr().err` to verify the stderr message contains "already initialized".
    - The `test_sdlc_init_rerun_does_not_modify_state_json` test snapshots `state.json` bytes via `read_bytes()` before the second invocation, and asserts byte-equality after.
  - [ ] Create `tests/integration/test_sdlc_init_e2e.py` with `pytestmark = pytest.mark.integration` and the two tests from AC6.4. Skip on Windows when `shutil.which("uv") is None` (mirror Story 1.13/1.15 patterns).
  - [ ] (Optional but recommended) Create `tests/integration/test_wheel_build.py` with the test from AC6.5. Skip on CI matrix cells where `uv build` is not available; this is primarily a dev-host smoke gate.
  - [ ] Run all new tests: `uv run pytest tests/unit/cli/ -m unit -v`; `uv run pytest tests/integration/test_sdlc_init_e2e.py -m integration -v`. All green.
  - [ ] Verify coverage: `uv run pytest tests/unit/cli/ --cov=src/sdlc/cli --cov-report=term-missing`. The new `cli/init.py`, `cli/main.py`, `cli/version.py`, `cli/output.py`, `cli/exit_codes.py` should each reach ≥ 90% line coverage. Uncovered lines should be limited to the Windows-fallback branch in `_write_state_json` (covered on Windows CI cells via the existing `quality-gates` matrix) and unreachable defensive paths.

- [ ] **Task 7: Author ADR-019 + update documentation (AC: #7)**
  - [ ] Determine the next free ADR number. Read `docs/decisions/index.md` and `ls docs/decisions/`. Story 1.16 takes the next number after the most recent ADR — typically 019 if ADR-018 (Story 1.15) has landed; otherwise the next free integer.
  - [ ] Create `docs/decisions/ADR-019-cli-skeleton-typer-adoption.md` (or whatever number is next) using `docs/decisions/adr-template.md`. Populate per AC7.
  - [ ] Update `docs/decisions/index.md`: add the row for ADR-019 after the most-recent ADR row. Preserve any 015-018 gaps for in-flight stories that haven't landed.
  - [ ] Update or create `docs/CODEMAPS/cli-module.md`: a one-paragraph orientation + table listing the v1.16 cli submodules (main.py, version.py, init.py, output.py, exit_codes.py) with one-line responsibilities each. Future cli stories (1.17-1.20) extend this table.
  - [ ] Update `README.md` (if it has a "Quick start" section) to include the now-working `pip install sdlc-framework && sdlc init && sdlc --version` flow. If README has no such section, defer to Story 1.17 which closes the demo loop.

- [ ] **Task 8: Run the full quality gate stack and verify CI green (AC: all)**
  - [ ] `uv run ruff check src/ tests/ scripts/` → 0 errors. The new `cli/*.py` files MUST satisfy `from __future__ import annotations` (auto-required by `tool.ruff.lint.isort`).
  - [ ] `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [ ] `uv run mypy --strict src/` → 0 errors. `cli/init.py` is fully annotated; no `Any` leak through public surface.
  - [ ] `uv run pre-commit run --all-files` → all hooks pass:
    - `ruff-check`, `ruff-format`, `mypy-strict` (existing).
    - `boundary-validator` — verify the cli widening allows the new imports.
    - `state-write-protocol-validator` (Story 1.10) — `cli/init.py` calls `write_state_atomic_sync`; the validator's allowlist must include `cli/init.py` OR the validator must be permissive of cli-layer atomic writes. Read `scripts/check_no_state_mutation.py` (or wherever Story 1.10's validator lives) to confirm; if cli is not yet in the allowlist, this story adds it. Mirror the pattern Story 1.10 used for non-state files that legitimately call `write_state_atomic_sync`.
    - `journal-append-only-validator` (Story 1.11) — `cli/init.py` calls `Path.touch()` on `journal.log`, NOT `append_sync`. Confirm the validator does not flag bare-touch as a journal mutation; if it does, narrow the rule to "only writes via direct append() calls fire the validator".
    - `secret-hardcode-validator` (Story 1.8) — scoped to `^src/sdlc/.*\.py$`; `cli/*.py` has no secrets.
    - `runtime-import-via-abc-validator` (Story 1.13, if landed) — `cli/init.py` does NOT import `runtime/`; should not fire.
    - `specialist-validator` (placeholder) — no impact.
  - [ ] `uv run pytest tests/unit/cli/ -m unit -v` → all green.
  - [ ] `uv run pytest tests/integration/test_sdlc_init_e2e.py -m integration -v` → green (skipped on Windows if `uv` not on PATH).
  - [ ] `uv run pytest tests/integration/test_wheel_build.py -v` → green (or skipped if optional and `uv build` unavailable).
  - [ ] Global `uv run pytest --cov=src --cov-fail-under=90` → coverage gate passes. New `cli/*.py` modules should reach ≥ 90% line coverage from the unit + integration suites combined.
  - [ ] Confirm new files are tracked: `git status` → `src/sdlc/cli/__init__.py`, `src/sdlc/cli/main.py`, `src/sdlc/cli/init.py`, `src/sdlc/cli/version.py`, `src/sdlc/cli/output.py`, `src/sdlc/cli/exit_codes.py`, `tests/unit/cli/__init__.py`, `tests/unit/cli/test_version.py`, `tests/unit/cli/test_main.py`, `tests/unit/cli/test_init.py`, `tests/integration/test_sdlc_init_e2e.py`, `docs/decisions/ADR-019-cli-skeleton-typer-adoption.md`, `docs/CODEMAPS/cli-module.md` are all tracked. `pyproject.toml`, `uv.lock`, `scripts/check_module_boundaries.py`, `tests/test_check_module_boundaries.py`, `docs/decisions/index.md` show modifications.
  - [ ] Run from a clean clone-equivalent: `git clean -fdx; uv sync --frozen --group dev; uv run pytest`. Everything must pass.
  - [ ] Smoke-test the actual user flow:
    ```bash
    cd $(mktemp -d)
    git init
    uv run sdlc --version          # prints "sdlc 0.0.0", exits 0
    uv run sdlc init               # creates canonical layout, exits 0
    uv run sdlc init               # refuses with "already initialized", exits 1
    ls -la .claude/state/          # state.json + journal.log present
    cat .claude/state/state.json   # canonical empty State bytes
    ```
    Document the smoke in the Story 1.16 dev notes / completion log so the reviewer can replay it.

## Dev Notes

### Why this story exists (FR + NFR + Decision mapping)

- **FR1 — `sdlc init` (greenfield) (PRD §FR1, Architecture §1131)**: Story 1.16 ships the FIRST USER CONTACT. Without 1.16, the framework is unrunnable as a CLI; users have only Python imports. The story closes the gap from "wheel installs cleanly" (Story 1.1) to "user runs `sdlc init` and gets a working SDLC project."
- **FR47 — `sdlc --version` reports installed version (PRD §FR47, Architecture §1173)**: Required for any "verify install worked" smoke test. Trivial in implementation but architecturally significant — it locks the console-script entry point at `sdlc.cli.main:app`.
- **FR50 — `package_data` payloads ship in the wheel (PRD §FR50, Architecture §1176, ADR-005)**: 6-month-deferred infrastructure repayment. ADR-005 explicitly named Story 1.16+ as the owner. Without this, content trees authored in Stories 2A-1, 2A-2, etc. would not appear in installed wheels.
- **NFR-COMPAT-1 — Python 3.10+ on macOS/Linux first-class (PRD §472)**: Tested by the integration test running on the existing CI matrix.
- **Architecture §388 — v0.2 sequence: "CLI skeleton (`sdlc init`, `sdlc scan`, `sdlc status`)"**: Story 1.16 closes the `sdlc init` half; Story 1.17 closes `sdlc scan` + `sdlc status`. Story 1.18 closes `sdlc trace`/`replay`/`logs`.
- **Architecture §1408 — "First demonstrable behaviour: `sdlc init && sdlc status` shows 'Phase 1, no progress yet'"**: Story 1.16 ships HALF this milestone; Story 1.17 ships the other half. Together they are the v0.2 walking-skeleton ship signal.
- **ADR-005 — package_data layout deferred to Story 1.16+**: Direct contract; Story 1.16 IS the owner.

### File set this story creates / modifies

**New files (created):**

- `src/sdlc/cli/__init__.py` — package docstring + future-import only (no re-exports)
- `src/sdlc/cli/main.py` — Typer app entry + `--version` callback + `init` subcommand registration (~80-100 LOC)
- `src/sdlc/cli/version.py` — `get_version()` per AC1.5 (~25 LOC)
- `src/sdlc/cli/init.py` — `run_init()` + helpers (~200-250 LOC)
- `src/sdlc/cli/output.py` — `echo()` stub (~30 LOC)
- `src/sdlc/cli/exit_codes.py` — four constants (~25 LOC)
- `tests/unit/cli/__init__.py` — pytest collection sentinel
- `tests/unit/cli/test_version.py` — version handler tests
- `tests/unit/cli/test_main.py` — Typer app tests via `CliRunner`
- `tests/unit/cli/test_init.py` — init scaffolder tests (~9 cases)
- `tests/integration/test_sdlc_init_e2e.py` — subprocess-driven end-to-end tests
- `tests/integration/test_wheel_build.py` (optional) — wheel content smoke test
- `docs/decisions/ADR-019-cli-skeleton-typer-adoption.md` — new ADR
- `docs/CODEMAPS/cli-module.md` — new codemap

**Optional new file** (factor out if `cli/init.py` grows past 200 LOC):

- `src/sdlc/cli/_init_helpers.py` — `_copy_package_data_tree`, `_copy_traversable_entry`, `_get_repo_root_or_cwd` helpers.

**Modified files:**

- `pyproject.toml` — add `typer>=0.12,<1` dep; uncomment `[project.scripts]`; add `[tool.hatch.build.targets.wheel.force-include]` block per ADR-005
- `uv.lock` — refreshed by `uv lock` after Typer addition
- `scripts/check_module_boundaries.py` — `MODULE_DEPS["cli"].depends_on` widens to include `state`, `journal`, `contracts`, `ids`
- `tests/test_check_module_boundaries.py` — add `test_cli_can_import_state_journal_per_story_116` regression test
- `docs/decisions/index.md` — add ADR-019 row
- `README.md` (optional) — add quick-start usage if a Quick Start section exists

**Conditionally modified files** (only if a `state-write-protocol-validator` allowlist needs extending):

- `scripts/check_no_state_mutation.py` (or wherever Story 1.10's validator lives) — add `cli/init.py` to the allowlist of modules permitted to call `write_state_atomic_sync` directly.

**Files NOT modified (invariant — break-glass if any of these change):**

- `src/sdlc/__init__.py` — Story 1.1 owns; `__version__` stays at "0.0.0" until ADR-008's first-release revisit.
- `src/sdlc/state/atomic.py`, `src/sdlc/state/model.py` — Stories 1.10 and 1.15 own; this story consumes their public APIs only.
- `src/sdlc/journal/writer.py`, `src/sdlc/journal/__init__.py` — Story 1.11 owns; not called from `cli/init.py` (only `Path.touch()` is used).
- `src/sdlc/ids/*.py` — Story 1.6 owns; consumer-only.
- `src/sdlc/errors/*.py` — Story 1.6 owns; consumer-only.
- `.pre-commit-config.yaml` — no new hook.

### Why Typer over argparse / click

Architecture §791 + `_bmad/config.toml:40` pre-locked Typer as the CLI framework. The dev MUST honor that lock.

If the dev is tempted to swap to argparse for "fewer deps," the rationale to NOT do that:

- Typer is a thin click wrapper (~50 KB direct + ~200 KB transitive including click + rich + shellingham); the cold-start cost is measured at ~80-120 ms on a typical dev host (well under the 200 ms budget).
- Typer's type-hint-driven argument parsing means `def init_command(adopt: bool = typer.Option(False, "--adopt"))` is the entire spec. argparse would require ~10 LOC of `add_argument` boilerplate per subcommand × 16 subcommands across Stories 1.16-1.20 = ~160 LOC of boilerplate that Typer eliminates.
- Subcommand registration via `@app.command()` decorators scales naturally as Stories 1.17+ add `scan`, `status`, `trace`, `replay`, `logs`, `rebuild-state`, `trust-hooks`, `unsign`, `migrate-vN`, `upgrade`, `dashboard`, `hook-check`. argparse subparser nesting is comparatively verbose.
- `typer.testing.CliRunner` provides a battle-tested in-process test harness — avoids spawning subprocesses for every CLI test.

### Why `sdlc init` does NOT append a journal entry

The architecture treats `sdlc init` as SUBSTRATE creation, not a state mutation. The journal is an audit log of state mutations. State mutations happen when:

- `sdlc scan` runs (Story 1.17) — first journal entry is `kind=scan_completed`.
- A workflow YAML's `state_mutations:` block fires (Story 2A.x).
- A specialist's hook chain produces a `state_mutation` payload (Story 2A.4-2A.6).

`sdlc init` creates the EMPTY state from which all subsequent mutations accrue. Appending a `framework_initialized` entry would:

1. Force a journal entry whose target_id is undefined (no epic/story/task exists yet — what does the entry "target"?).
2. Make `sdlc rebuild-state` (Story 1.20) misbehave: if the journal has a `framework_initialized` entry, but the user deleted state.json and runs rebuild-state, the rebuilt state would re-execute the "init" — but state.json existing IS the init evidence; replaying init when state.json is missing is the expected-but-broken flow.
3. Pollute the journal's "first state mutation" semantics — Story 1.12's projection reducer (already shipped as `ready-for-dev`) treats `state_mutation` as the canonical entry kind. A `framework_initialized` entry would need its own reducer branch that's a no-op, which is dead code.

The cleaner contract: `sdlc init` writes the empty state AT REST. The journal stays empty until the first real mutation. ADR-014's "first entry is the first state mutation" invariant is preserved.

### Why `sdlc init` is idempotent-via-refusal (NOT --force / NOT silent re-run)

Three options for the second-run behavior:

1. **Silently re-create canonical layout** (overwrite state.json with empty state): catastrophic — wipes any project work the user did. Rejected.
2. **Refuse with clear message + exit 1** (this story): safe; user must explicitly `rm -rf .claude/` to start fresh. Mirrors PostgreSQL's `initdb` behavior (refuses on non-empty DATA dir).
3. **`sdlc init --force` to overwrite**: rejected for v1 — `--force-bypass-signoff` is the only "force" flag in v1 (PRD §FR38), and adding `sdlc init --force` introduces a footgun. Stories 1.20 (`sdlc rebuild-state`) and 1.19 (`sdlc migrate-vN`) provide safer recovery paths.

### Why the empty `.claude/{agents,commands,...}` placeholder dirs are created in v1.16

ADR-005 said "no empty placeholder dirs in v0.2." Story 1.16's `sdlc init` creates these dirs at INIT TIME (in the user's project), NOT at SOURCE TIME (in `src/sdlc/`). The two are different:

- ADR-005's "no empty dirs in v0.2" applies to `src/sdlc/<tree>/` — those stay missing until Story 2A-x authors content.
- Story 1.16's `sdlc init` creates `<user_repo>/.claude/{agents,commands,hooks,workflows,memory,skills}/` — these are RUNTIME directories that the framework's hook chain + workflow loader expect to find.

The ADR-005 rule and the Story 1.16 init step are orthogonal. Both are correct.

### Why the `--adopt` flag is a hidden placeholder in v1.16

Story 3.1 owns `sdlc init --adopt`. Two options for v1.16:

1. **Don't register `--adopt` at all**: Story 3.1 has to add the flag, which is a CLI surface change requiring all `--adopt` consumers to update.
2. **Register `--adopt` as `hidden=True` + refuse-with-error**: Story 3.1 flips `hidden=False` + replaces the refusal body with the orchestrator. No CLI surface change.

Option 2 is the cleaner forward-compat — the flag exists in v1.16 even though it's a no-op refusal; Story 3.1 lights it up.

### Cold-start budget verification

Architecture §488 sets the cold-start budget at < 200 ms for `sdlc --version`. The defer-import discipline means `cli/main.py` imports ONLY:

- `typer` (~80-100 ms first-import; cached for subsequent invocations in same process — but each `sdlc <cmd>` is a fresh Python process)
- `sdlc.cli.version` → `sdlc.__version__` (~5 ms)

No `state`, `journal`, `engine` imports happen for `--version`. The diagnosis path if a regression pushes past 200 ms:

```bash
python -X importtime -m sdlc.cli.main --version 2>&1 | sort -k 2 -n | tail -20
```

Heaviest imports historically: `pydantic` (~30 ms), `rich` (~20 ms transitive via Typer). If pydantic gets pulled into `cli/main.py` accidentally (e.g. via `from sdlc.state import State` at module level), cold-start jumps by ~30 ms.

### State write protocol on Windows

`state/atomic.py` is POSIX-only (Story 1.10, Architecture §573). On Windows, `_write_state_json` falls back to `Path.write_bytes(canonical_bytes)` with a one-line warning. This is acceptable because:

1. Windows is "WSL2 only" per ADR-001 / PRD §472. Native Windows is not first-class.
2. The atomic-write protocol's value (no torn writes during crash) requires `fcntl` / `O_TMPFILE`-style guarantees that Windows doesn't provide cleanly.
3. The fallback is honest: the warning tells the user to use WSL2 for production.

If Story 1.20's `sdlc rebuild-state` ever runs on Windows + native filesystem, it'll re-write state.json from journal — even if init's non-atomic write got torn, rebuild-state recovers cleanly. Defense-in-depth.

## Project Structure Notes

### Alignment with unified project structure

Story 1.16 ALIGNS with Architecture §765-§811 (Module Specification). Adds:

- `src/sdlc/cli/` populated with the v0.2 substrate's first six modules (`__init__`, `main`, `version`, `init`, `output`, `exit_codes`).

The cli module's subdirectory layout matches Architecture §790-§811 verbatim:

```
src/sdlc/cli/
├── __init__.py        # this story
├── main.py            # this story (Architecture §791)
├── output.py          # this story stub (Architecture §792)
├── exit_codes.py      # this story (Architecture §793)
├── version.py         # this story (FR47)
├── init.py            # this story (Architecture §797, FR1)
└── ...                # Stories 1.17-1.20 add scan, status, adopt, trace, replay, etc.
```

### Detected variances

None. All paths and module responsibilities align with Architecture §790-§811.

## References

- [Source: docs/CODEMAPS/journal.md] — journal append protocol context (cli/init.py uses Path.touch, NOT append_sync)
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Lifecycle Management (FR1–FR5)] — line 117
- [Source: _bmad-output/planning-artifacts/architecture.md#Distribution, Versioning & Migration (FR47–FR50)] — line 124
- [Source: _bmad-output/planning-artifacts/architecture.md#Canonical Filesystem Layout (within a user's project)] — lines 443-481
- [Source: _bmad-output/planning-artifacts/architecture.md#Code Style Beyond Ruff] — lines 483-494 (cli defer-import discipline)
- [Source: _bmad-output/planning-artifacts/architecture.md#CLI exit code mapping] — lines 540-548
- [Source: _bmad-output/planning-artifacts/architecture.md#Module Specification — cli/] — lines 790-811
- [Source: _bmad-output/planning-artifacts/architecture.md#Functional Requirements → File Mapping] — lines 1131-1178 (FR1, FR47, FR50)
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-level Boundary Rules] — lines 1052-1112
- [Source: _bmad-output/planning-artifacts/architecture.md#Development Workflow Integration] — lines 1207-1219
- [Source: _bmad-output/planning-artifacts/architecture.md#v0.2 Implementation Sequence] — lines 1402-1410
- [Source: _bmad-output/planning-artifacts/prd.md#FR47] — line 790
- [Source: _bmad-output/planning-artifacts/prd.md#FR50] — line 793
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.16] — lines 802-825
- [Source: docs/decisions/ADR-001-pyproject-metadata.md] — pyproject metadata + deferred-dynamic-version contract
- [Source: docs/decisions/ADR-005-package-data-layout.md] — package_data extension contract for Story 1.16+
- [Source: docs/decisions/ADR-013-atomic-state-write-protocol.md] — atomic write protocol (consumed by cli/init.py on POSIX)
- [Source: docs/decisions/ADR-014-append-only-journal-protocol.md] — journal append-only invariant (cli/init.py creates empty journal.log via touch, NOT append)
- [Source: scripts/check_module_boundaries.py:132-135] — MODULE_DEPS["cli"] entry (this story widens)
- [Source: pyproject.toml:16-18] — commented `[project.scripts]` stub (this story uncomments)
- [Source: pyproject.toml:39-40] — `# TODO: ADR-005` marker (this story replaces with force-include block)
- [Source: src/sdlc/__init__.py:3] — `__version__: str = "0.0.0"` (sourced by cli/version.py)
- [Source: src/sdlc/state/__init__.py] — public re-export of `State`, `write_state_atomic_sync` (consumed by cli/init.py)
- [Source: _bmad-output/implementation-artifacts/1-15-engine-scanner-skeleton.md] — Story 1.15 dev notes mention `cli/scan.py` calling `write_state_atomic_sync` + `append_sync` directly (precedent for cli→state widening)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m]

### Debug Log References

### Completion Notes List

### File List
