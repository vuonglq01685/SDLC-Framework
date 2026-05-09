# ADR-020: CLI `sdlc scan` + `sdlc status` + Accessibility Flags

**Status:** Accepted (2026-05-09, Story 1.17)

## Context

Story 1.17 closes the v0.2 walking-skeleton end state: after `sdlc init`, a user can run
`sdlc scan` (FR3) to parse the artifact tree into `state.json`, and `sdlc status` (FR44)
to receive a human-readable "resume card" showing current phase and suggested next action.
Two global accessibility flags — `--no-color` / `NO_COLOR` env var, and `--json` — are
also introduced here as they are prerequisites for machine-readable CI integration (FR49)
and accessible terminal output (NFR-A11Y-4, no-color.org informal standard).

The following constraints from prior ADRs govern the solution space:

- **ADR-013**: `state.json` writes must go through `write_state_atomic_sync` on POSIX; a
  Windows-safe fallback (`Path.write_bytes` + a `noqa: state-write` suppression) is
  accepted per the same precedent set in ADR-019 / `cli/init.py`.
- **ADR-014**: The append-only journal protocol: each `sdlc scan` invocation must append
  exactly one `scan_completed` `JournalEntry` with schema-compliant fields including
  `monotonic_seq` derived from `state.next_monotonic_seq` before increment.
- **ADR-019**: Typer is the CLI framework. All subcommand bodies use deferred imports
  (Architecture §488) to keep cold-start under 200 ms. Global flags are declared on the
  `@app.callback()` and propagated via `ctx.obj`.
- **NFR-COMPAT-1**: `journal.append_sync` and `state.write_state_atomic_sync` are
  POSIX-only (fcntl). On Windows, `sdlc scan` logs a warning and falls back to a
  non-atomic `Path.write_bytes`; `sdlc status` is fully portable (read-only).

## Decision

### 1. `sdlc scan` (`cli/scan.py`)

Wraps `engine.scanner.scan(root)` with the full write protocol:

1. Read `state.json` → `before_hash` (SHA-256).
2. Call `engine.scanner.scan(root)` → new `State`.
3. Derive `journal_seq = old_state.next_monotonic_seq`.
4. Increment `new_state.next_monotonic_seq = journal_seq + 1`.
5. Write `state.json` (POSIX: atomic; Windows: fallback).
6. Compute `after_hash`.
7. Append `JournalEntry(kind="scan_completed", monotonic_seq=journal_seq, ...)` to
   `journal.log`.

This matches Architecture §573–§583 step ordering (state first, journal second).

### 2. `sdlc status` (`cli/status.py`)

Read-only command — never writes to `state.json` or `journal.log`. Reads:

- `state.json` → phase, epic/story/task counts, `next_monotonic_seq`.
- `journal.log` last line → `last_updated_ts` (the most recent scan timestamp).
- `pyproject.toml` (regex on `^name\s*=\s*["']([^"']+)["']`) → project name fallback.

Emits a human-readable "resume card" or, with `--json`, a canonical JSON envelope with
keys: `command`, `project_name`, `project_root`, `phase`, `phase_name`, `last_updated_ts`,
`epic_count`, `story_count`, `task_count`, `suggested_next`, `next_monotonic_seq`.

### 3. Global accessibility flags on `@app.callback()`

`--no-color` (`is_eager=True`) and `--json` (`is_eager=True`) are declared on the root
callback and stored in `ctx.obj`. All output helpers in `cli/output.py` consult `ctx.obj`
to decide rendering mode.

`--no-color` is OR'd with `os.environ.get("NO_COLOR", "") != ""` per no-color.org: any
non-empty value of `NO_COLOR` disables colour regardless of the flag.

### 4. `cli/output.py` expansion

The stub from Story 1.16 is expanded to a full output layer:

| Symbol | Purpose |
|--------|---------|
| `echo(msg, *, err, ctx)` | No-op in JSON mode; strips ANSI if no-color active |
| `emit_json(cmd, payload, *, ctx)` | Canonical JSON (`sort_keys`, compact) to stdout |
| `emit_error(code, msg, *, ctx, details)` | JSON envelope to stderr or plain text; raises `typer.Exit` |
| `make_console(ctx)` | Lazy cached `rich.Console` factory |
| `is_no_color_active(ctx)` | Flag OR env check per no-color.org |
| `_ERR_CODE_TO_EXIT_CODE` | Error code → exit code table |

Exit codes: `ERR_NOT_INITIALIZED` → 1, `ERR_SCAN_FAILED` → 2,
`ERR_JOURNAL_APPEND_FAILED` → 2, `ERR_STATE_WRITE_FAILED` → 2,
`ERR_INFRASTRUCTURE` → 3.

### 5. `rich` direct dependency

`rich>=13,<15` added as a direct dependency. Import deferred inside `make_console` to
keep cold-start budget intact; only incurred when human-readable output is actually
rendered.

### 6. `state_to_canonical_bytes` exported from `sdlc.state`

Added as a standalone helper so that `cli/scan.py`, `cli/init.py` tests, and future
stories can produce canonical bytes without importing the POSIX-only `atomic` module.

## Consequences

**Positive:**
- The v0.2 walking skeleton is complete: `sdlc init && sdlc scan && sdlc status` works
  end-to-end on POSIX, and `sdlc init && sdlc status` works on Windows.
- `--json` flag makes every command scriptable from CI without screen-scraping.
- `--no-color` / `NO_COLOR` makes the CLI usable in accessibility contexts and CI logs.
- Output layer is now a stable internal API; future subcommands can use `echo`/`emit_json`
  without re-implementing colour logic.

**Negative / Accepted risk:**
- `sdlc scan` on Windows uses a non-atomic write for `state.json`. This is acceptable
  because Windows-native is a secondary target (WSL2 is recommended); a crash mid-write
  leaves either the old or the new file, never a partial file, on NTFS.
- `journal.append_sync` is POSIX-only; `sdlc scan` on Windows fails with `JournalError`.
  This is documented, expected, and flagged clearly in the CLI warning.
- `_version_callback` checks `sys.argv` directly for `--json` because it is `is_eager`
  and fires before `_root` sets `ctx.obj`. This is a known Typer limitation; documented
  in the callback's inline comment.

## Alternatives Considered

- **Defer `--no-color` / `--json` to a later story**: Rejected because `sdlc scan --json`
  is required for the CI gate introduced in this story, and retrofitting global flags onto
  existing subcommands would require touching every command module anyway.
- **Use Click's `make_context` to thread json/no-color via eager flags through ctx.obj**:
  The `sys.argv` approach for `--version` is a known limitation of Typer's eager flag
  processing. Replacing it with a Click-level workaround would reduce the codebase's
  Typer abstraction. Accepted as a bounded trade-off.
- **Single combined `cli/output.py` + `cli/formatting.py` split**: Rejected (YAGNI) — the
  output surface is small enough to fit in one cohesive module at current scale.
