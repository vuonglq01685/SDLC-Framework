# ADR-022: Migration Framework and Major-Version Schema Gate

**Status:** Accepted (2026-05-09, Story 1.19)

## Context

As the SDLC Framework evolves, `state.json` will undergo breaking schema changes.
Without a forward-migration mechanism, users upgrading the framework binary would find
their existing `state.json` silently unreadable or — worse — parsed incorrectly by a
pydantic model that no longer matches the on-disk layout.

Story 1.19 addresses three related concerns:

1. **Schema-gate refusal** — the CLI must refuse to operate on a `state.json` whose
   `schema_version` does not match `CURRENT_SCHEMA_VERSION`, surfacing a targeted
   error message that names the exact migration command to run.

2. **Migration registry** — a discoverable, contract-validated registry of
   `migrations/v<N>.py` scripts that each export a `migrate(state: dict) -> dict`
   callable, enabling the CLI to build a forward-migration chain automatically.

3. **`sdlc migrate-vN` command** — a safe, idempotent, backup-first orchestrator that
   applies a single migration step and atomically writes the result.

Stories 1.10–1.12 established the POSIX atomic write protocol and the flock-based
serialisation contract. Story 1.19 extends that protocol with a raw-dict variant
(`write_state_raw_atomic_sync`) so the migration orchestrator can persist
post-migration payloads whose `schema_version` may be unknown to the current pydantic
`State` model.

## Decision

### Schema gate (`sdlc.state.reader`)

A new module `sdlc.state.reader` owns `CURRENT_SCHEMA_VERSION: Final[int] = 1` as the
single source of truth. All CLI command bodies that read state must call
`read_state_or_refuse(path)` — which raises `SchemaError` on version mismatch with a
message that includes `sdlc migrate-v<N>` — rather than calling raw JSON parsing
directly.

The migration orchestrator (`cli/migrate.py`) and any future state-rebuild tool must
bypass the gate via `read_state_raw(path)`, which returns the raw dict without pydantic
validation or version enforcement.

### Migration registry (`sdlc.migrations`)

Migration scripts live in `src/sdlc/migrations/v<N>.py` for each integer N ≥ 2.
Discovery uses `pkgutil.iter_modules` against the package's `__path__` — filename
enumeration only, no imports. The `^v(?P<n>[1-9][0-9]*)$` regex rejects `v0`, `v01`
(leading zeros), and non-version files.

Each script must export `migrate(state)` accepting exactly one positional parameter.
`load_migration(n)` validates this contract via `inspect.signature` and raises
`SchemaError` (code `ERR_MIGRATION_INVALID`) for any violation.

For `CURRENT_SCHEMA_VERSION = 1` there are no expected scripts; the discovery list is
empty and the migration chain is a no-op. This keeps the v1 baseline clean.

### `sdlc migrate-vN` command (dynamic registration)

`_register_migrate_commands(app)` in `cli/main.py` calls `discover_migrations()` at
module-import time (one `pkgutil` scan, fast) and registers one Typer command per
discovered script. For v1 the function is a no-op. A closure-capture factory
(`_make_command(version)`) avoids the Python late-binding bug — each command captures
its own `version` integer.

The `run_migrate` orchestrator follows a 13-step flow:

1. Resolve repo root + paths.
2. Verify `state.json` exists.
3. Read raw state (bypass gate).
4. Validate `target_version` is in the discovered list.
5. Idempotency check — if already at target, emit no-op and exit 0.
6. Validate `schema_version` is an integer.
7. Downgrade guard — refuse if `state_version > target_version`.
8. Create byte-identical backup in `.claude/state/backups/`.
9. Load migration function.
10. Run migration (sandboxed; catch all exceptions).
11. Validate result is a dict with `schema_version == target_version`.
12. Atomic write (`write_state_raw_atomic_sync`).
13. Emit success output.

### Raw atomic write (`write_state_raw_atomic_sync`)

The existing `_write_protocol_body` is refactored to accept pre-canonicalized bytes,
making the sync/async paths share a single protocol body. A `_canonicalize_raw`
function serialises arbitrary `Mapping[str, object]` payloads with the same NFC
normalisation and `sort_keys=True` policy as the typed `_canonicalize_state`.

### CI lint (`scripts/check_migration_registry.py`)

A script validates chain completeness for each integer in `[2, CURRENT_SCHEMA_VERSION]`
and contract validity for every discovered script. For `CURRENT_SCHEMA_VERSION = 1` it
is a no-op. The script is registered in both `.pre-commit-config.yaml` and
`.github/workflows/ci.yml`.

## Consequences

- Every new breaking schema change requires: (a) bumping `CURRENT_SCHEMA_VERSION`,
  (b) adding `migrations/v<N>.py`, and (c) the CI registry lint will fail if the
  script is missing or invalid.
- Migration is **forward-only** — downgrades are explicitly rejected. Rollback requires
  restoring from the backup created in step 8.
- The `--json` flag propagates correctly through `run_migrate`'s success and no-op
  output paths via the existing `emit_json` / `echo` surface.
- `sdlc.migrations` is a leaf cluster: it may import `errors` and `state`, but must
  not import `engine`, `dispatcher`, `runtime`, or `cli`. This is enforced by
  `check_module_boundaries.py`.
- The schema gate is enforced at read time in every CLI command that calls
  `read_state_or_refuse`. Commands that bypass the gate (`migrate`, future
  `rebuild-state`) do so explicitly via `read_state_raw` — the bypass is visible in
  code review.
