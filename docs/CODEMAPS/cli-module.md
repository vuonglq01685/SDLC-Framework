# CLI Module — `src/sdlc/cli/`

The `cli/` package is the user-facing surface of the framework. It owns the `sdlc`
console script entry point (`sdlc.cli.main:app`) and all subcommand implementations.
It is the only module permitted to invoke external binaries (via `cli/git.py` and
`cli/gh.py` once materialised, or inline helpers for single-use cases) and the only
module with write access to `state.json` and `journal.log` at the I/O level.

## Submodules (v1.16)

| File | LOC | Responsibility |
|------|-----|----------------|
| `__init__.py` | ~8 | Package docstring; no re-exports |
| `main.py` | ~60 | Typer app instance; `--version` callback; `init` subcommand registration |
| `version.py` | ~20 | `get_version() -> str` — sources `sdlc.__version__` per ADR-001 |
| `init.py` | ~180 | `run_init()` — scaffolds canonical SDLC layout; idempotent-via-refusal (AC3) |
| `output.py` | ~20 | `echo()` stub — wraps `typer.echo`; Story 1.17 adds `--no-color`/`--json` |
| `exit_codes.py` | ~20 | Exit code constants: `EXIT_OK=0`, `EXIT_USER_ERROR=1`, `EXIT_FRAMEWORK_FAILURE=2`, `EXIT_INFRASTRUCTURE=3` |

## Planned additions (Stories 1.17–1.20)

- `scan.py` — `sdlc scan` (Story 1.17)
- `status.py` — `sdlc status` (Story 1.17)
- `trace.py` / `replay.py` / `logs.py` — audit commands (Story 1.18)
- `git.py` — `git rev-parse` / `git log` helpers (Story 1.18)
- `migrate.py` — `sdlc migrate-vN` (Story 1.19)
- `rebuild_state.py` — `sdlc rebuild-state` (Story 1.20)

## Key design constraints

- **Cold-start budget**: `sdlc --version` must complete in < 200 ms.
  All heavy imports (`state`, `journal`, `engine`) are deferred to command-body
  level per Architecture §488.
- **No `print()`**: all stdout/stderr goes through `cli/output.py:echo()` so Story 1.17
  can add `--no-color`/`--json` envelope plumbing in one place.
- **No `os.environ` direct access**: env-var reads go through `config/env.py` (Story 1.8).
- **`subprocess.run` restricted**: only `cli/git.py`, `cli/gh.py`, and single-use inline
  helpers (e.g. `_get_repo_root_or_cwd()` in `init.py`) may invoke external binaries
  (Architecture §492, §1105).
