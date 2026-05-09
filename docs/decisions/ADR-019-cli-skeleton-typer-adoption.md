# ADR-019: CLI Skeleton + Typer Adoption + Boundary Widening + Idempotency Contract

**Status:** Accepted (2026-05-09, Story 1.16)

## Context

Story 1.16 materialises the `cli/` module — the first user-contact surface of the framework.
Three requirements converge here:

- **FR1** (PRD §FR1, Architecture §1131): `sdlc init` scaffolds the canonical SDLC layout
  in a fresh git repository so users can begin managed development.
- **FR47** (PRD §FR47, Architecture §1173): `sdlc --version` reports the installed wheel
  version; essential for any "did the install work?" smoke test.
- **FR50** (PRD §FR50, Architecture §1176, ADR-005): The wheel must ship content trees
  (`agents/`, `commands/`, `hooks/`, `workflows/`, `skills/`, `memory/`, `dashboard/static/`)
  as `package_data` so later stories can drop files into `src/sdlc/<tree>/` and have them
  automatically appear in installed environments.

Architecture §791 and `_bmad/config.toml:40` pre-locked **Typer** as the CLI framework.
ADR-005 deferred the `package_data` extension to "Story 1.16+". The module boundary table
(Architecture §1052–§1112) listed `cli/` dependencies conservatively; Story 1.16's
`cli/init.py` needs direct access to `state/`, `journal/`, `contracts/`, and `ids/`.

NFR-COMPAT-1 (PRD §472) requires Python 3.10+ on Linux/macOS first-class; Windows is
supported via WSL2. The POSIX-only `state/atomic.py` protocol (ADR-013) cannot be used
on Windows native, which requires a documented fallback path in `cli/init.py`.

## Decision

1. **Typer (≥0.12, <1)** is the v1 CLI framework. The entry point is the console script
   `sdlc = "sdlc.cli.main:app"` in `[project.scripts]`.

2. **`cli/` module layout** (Architecture §790–§811):
   - `cli/main.py` — Typer app; `--version` callback; `init` subcommand registration.
   - `cli/version.py` — `get_version() -> str` sourcing `sdlc.__version__` (ADR-001).
   - `cli/init.py` — `run_init()` scaffolder for the canonical SDLC layout.
   - `cli/output.py` — `echo()` stub; Story 1.17 expands with `--no-color`/`--json`.
   - `cli/exit_codes.py` — `EXIT_OK=0`, `EXIT_USER_ERROR=1`, `EXIT_FRAMEWORK_FAILURE=2`,
     `EXIT_INFRASTRUCTURE=3` (Architecture §540).

3. **`[tool.hatch.build.targets.wheel.force-include]`** ships seven content-tree roots.
   Source trees (`src/sdlc/agents/`, etc.) are seeded with `.gitkeep` markers so that
   hatchling's editable-install builder (which raises `FileNotFoundError` for missing
   `force-include` paths) can build cleanly. The `.gitkeep` files are skipped at `sdlc init`
   copy-time; real content from Stories 2A.x replaces them tree-by-tree.

4. **`MODULE_DEPS["cli"].depends_on`** widens to include `"state"`, `"journal"`,
   `"contracts"`, and `"ids"` — the four modules that `cli/init.py` (and future
   `cli/scan.py`, `cli/rebuild_state.py`) require for direct state/journal I/O.

5. **`sdlc init` is idempotent-via-refusal**: the detection signal is the presence of
   `.claude/state/state.json`; second run exits 1 with a plain-text stderr message and
   makes no filesystem changes.

6. **Windows fallback**: `_write_state_json` emits a one-line `logging.warning` and uses
   `Path.write_bytes` instead of `write_state_atomic_sync` on `sys.platform == "win32"`.

7. **Console script version source**: `sdlc.__version__` (static `"0.0.0"` per ADR-001).
   `importlib.metadata.version("sdlc-framework")` is asserted to match in CI but is not
   the runtime source until ADR-008's first-release revisit.

8. **Command-body imports are deferred** per Architecture §488 to keep the cold-start
   budget for `sdlc --version` under 200 ms. Module-level imports in `cli/main.py` are
   limited to `typer` and `sdlc.cli.version`.

## Alternatives Considered

- **`argparse` (stdlib)**: Rejected — saves ~80 KB of transitive deps but loses Typer's
  type-driven argument parsing, auto-generated `--help`, and decorator-based subcommand
  registration. Architecture pre-locked Typer.

- **`click` directly**: Rejected — Typer is a thin wrapper that adds type-hint-driven
  argument parsing. Direct Click requires boilerplate Typer hides (~10 LOC per subcommand
  × 16 planned subcommands).

- **`sdlc init --force` to overwrite on re-run**: Rejected — `--force-bypass-signoff` is
  the only `--force` flag in v1 (PRD §FR38). An overwrite flag is a footgun; Stories 1.19
  and 1.20 provide safer recovery paths (`sdlc migrate-vN`, `sdlc rebuild-state`).

- **Materialising `cli/git.py` in v1.16**: Rejected — Story 1.18 (`sdlc trace/logs`) is
  the actual owner; an inline `_get_repo_root_or_cwd()` in `cli/init.py` avoids pulling
  forward the module before its owning story.

- **Adding a `framework_initialized` journal entry on `sdlc init`**: Rejected — `sdlc init`
  is substrate creation, not a state mutation. ADR-014 records: "the first entry corresponds
  to the first state mutation." The journal stays empty until `sdlc scan` runs (Story 1.17).

- **Pre-creating content-tree dirs eagerly without `.gitkeep`**: Rejected — empty
  directories are not tracked by git, so a clean checkout would fail the editable install.
  `.gitkeep` markers are the standard git idiom for committing empty directories; they are
  excluded from the `sdlc init` copy step via an explicit `src_entry.name == ".gitkeep"`
  guard.

## Consequences

- First user contact (`pip install sdlc-framework && sdlc init && sdlc --version`) is now
  end-to-end demonstrable. Story 1.17 closes the demo by adding `sdlc scan` + `sdlc status`.
- The Typer dep adds ~5 transitive packages (click, rich, shellingham, markdown-it-py,
  mdurl). Cold-start `sdlc --version` measured at ~80–120 ms; within the 200 ms budget.
- The `cli→state` widening means all future CLI commands (`scan`, `rebuild-state`, etc.)
  can write `state.json` without further boundary changes. The cli IS the write-side I/O
  surface; `engine/` stays read-only per Story 1.15's scanner contract.
- `.gitkeep` markers in `src/sdlc/<tree>/` are a minor repo hygiene cost. They must be
  removed as real content lands in each tree (or retained — they are harmless).
- The `package_data` force-include pattern is now active: future stories adding
  `src/sdlc/<tree>/<file>` automatically get the file shipped in the wheel with no further
  `pyproject.toml` edits.
- Empty placeholder dirs (`.claude/agents/`, `.claude/commands/`, etc.) created by
  `sdlc init` in user repos are a public commitment to the Architecture §457–§464 layout.
  Renaming a tree after v1.0 is a breaking change handled by `sdlc migrate-vN` (Story 1.19).

## Revisit-by

2027-05-09 — or when Story 1.21 locks the v1 wire format and console-script API; any
flag/subcommand addition after that lock requires RFC + ADR amendment.

## References

Architecture §117, §388, §443–§481, §488–§494, §540–§548, §765–§811,
§1052–§1112, §1131, §1173, §1176, §1207–§1219, §1402–§1410.
PRD §FR1, §FR47, §FR50, §472. ADR-001, ADR-005, ADR-013, ADR-014, ADR-018.
