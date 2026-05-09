# CLI Module — `src/sdlc/cli/`

The `cli/` package is the user-facing surface of the framework. It owns the `sdlc`
console script entry point (`sdlc.cli.main:app`) and all subcommand implementations.
It is the only module permitted to invoke external binaries (via `cli/git.py` and
`cli/gh.py` once materialised, or inline helpers for single-use cases) and the only
module with write access to `state.json` and `journal.log` at the I/O level.

## Submodules (v1.18)

| File | LOC | Responsibility |
|------|-----|----------------|
| `__init__.py` | ~8 | Package docstring; no re-exports |
| `main.py` | ~141 | Typer app; `--version`/`--no-color`/`--json` callbacks; `init`/`scan`/`status`/`trace`/`replay`/`logs` registration |
| `version.py` | ~20 | `get_version() -> str` — sources `sdlc.__version__` per ADR-001 |
| `init.py` | ~180 | `run_init()` — scaffolds canonical SDLC layout; idempotent-via-refusal (AC3) |
| `scan.py` | ~200 | `run_scan()` — wraps `engine.scanner.scan`; atomic state write + journal append |
| `status.py` | ~180 | `run_status()` — read-only resume card: phase, counts, suggested next, last_updated |
| `output.py` | ~200 | `echo`, `emit_json`, `emit_error`, `make_console`, `is_no_color_active`; 9-entry error code table; per-command schema constants |
| `exit_codes.py` | ~20 | Exit code constants: `EXIT_OK=0`, `EXIT_USER_ERROR=1`, `EXIT_FRAMEWORK_FAILURE=2`, `EXIT_INFRASTRUCTURE=3` |
| `trace.py` | ~200 | `run_trace()` — filters journal + agent_runs by task-id; chronological merge; exits 0 always (FR33, ADR-021) |
| `replay.py` | ~160 | `run_replay()` — pretty-prints JournalEntry at 1-indexed line(s); `_parse_line_spec`; 1000-line cap (FR34, ADR-021) |
| `logs.py` | ~320 | `run_logs()` — tails journal + agent_runs with `--filter-task`, `--filter-agent`, `--follow`; NDJSON in follow+json mode (FR45, ADR-021) |
| `_paths.py` | ~30 | `get_repo_root_or_cwd()` — shared repo-root resolver via `git rev-parse`; falls back to cwd |

## Planned additions (Stories 1.19–1.20)

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
