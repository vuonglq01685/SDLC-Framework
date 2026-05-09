# ADR-021: CLI `sdlc trace` + `sdlc replay` + `sdlc logs` + Cross-Stream Merge

**Status:** Accepted (2026-05-09, Story 1.18)

## Context

FR33 (`sdlc trace <task-id>`), FR34 (`sdlc replay <line>`), and FR45 (`sdlc logs`)
require user-facing CLI surfaces for audit-chain interrogation without manual JSONL
parsing (PRD §767, §768, §785; Architecture §1159, §1160, §1171).

NFR-OBS-3 (PRD §865) requires chronological reconstruction of all events affecting
a task. NFR-OBS-6 (PRD §868) requires filter-by-task and filter-by-agent on the
combined audit stream. Architecture §397 Decision E3 defines three observability
streams: `journal.log` (audit), `agent_runs.jsonl` (dispatches), `debug_events.jsonl`
(correlation). Story 1.18 reads the first two; `debug_events.jsonl` is Story 4.x.

Stories 1.7 (JournalEntry contract), 1.11 (journal reader), and 1.16–1.17 (CLI
scaffolding + output surface) provide the substrate this story extends.

Story 2A.3 will write the first record to `agent_runs.jsonl`; the schema-lock for
that file is intentionally deferred to avoid pre-emptive churn.

## Decision

**`cli/trace.py`** (`run_trace`) filters `journal.log` by task-id via three predicates:
1. `entry.target_id == task_id` (direct mutation)
2. `entry.kind == "agent_dispatch"` and `entry.payload["task_id"] == task_id`
3. `entry.kind == "hook_invocation"` and `entry.payload["target_id"] == task_id`

It also includes records from `agent_runs.jsonl` where `target_id` or `task_id` field
matches. Both streams are merged and sorted chronologically by `ts`; journal entries
tie-break before agent_run records at the same millisecond. Exits 0 even if no events.

**`cli/replay.py`** (`run_replay`) parses `<line>` or `<start>-<end>` via a private
`_parse_line_spec` helper. Line numbers are 1-indexed. Out-of-range raises
`JournalError` mapped to `ERR_USER_INPUT` exit 1. Range cap: `_MAX_REPLAY_RANGE = 1000`
lines. Pretty-prints each `JournalEntry` as a labelled block; `--json` mode emits
`{"command":"replay","lines":[{"lineno":N,"entry":<model_dump>}],"line_count":K}`.

**`cli/logs.py`** (`run_logs`) merges journal + agent_runs streams using the same
predicate logic and chronological sort as `trace`. Supports:
- `--filter-task <id>`: restricts to task-matching entries (validates via `parse_task_id`)
- `--filter-agent <name>`: restricts to entries where `actor == "agent:<name>"` or
  `payload["agent"] == name` (journal) or `record["agent"] == name` (agent_runs)
- `--follow`: tail-polls both files at 0.25 s intervals until `KeyboardInterrupt` → exit 0

`--follow --json` emits NDJSON (one JSON object per line) rather than a single document;
this is the only command in v1 with continuous-stream JSON output.

**`agent_runs.jsonl`** has no contract module in v1.18 — records are read as
`dict[str, object]`. Story 2A.3 owns the schema-lock; ADR-021 recommends adding
`contracts/agent_run.py` when the first writer ships.

**`cli/output.py`** is extended with two new error codes (`ERR_JOURNAL_READ_FAILED → 2`,
`ERR_AGENT_RUNS_READ_FAILED → 2`) and three schema constants
(`_TRACE_OUTPUT_SCHEMA`, `_REPLAY_OUTPUT_SCHEMA`, `_LOGS_OUTPUT_SCHEMA`, all `"v1"`).
Story 1.21's wire-format-lock ceremony freezes these constants.

All three commands respect Story 1.17's global `--no-color` / `--json` flags via
`ctx.obj` and are fully read-only (no writes to journal, state, or agent_runs).

## Alternatives Considered

- **Hierarchical trace (chase parent story + epic events)**: Rejected for v1.18; epic
  AC scopes trace to task-id only. Story 2.x can add `--story` / `--epic` flags.
- **Index-based replay seek**: Rejected as premature; journals are ≤ MB at v1 scale;
  linear scan via `iter_entries` is fast enough. Revisit if profiling surfaces a
  bottleneck after v1.x ships.
- **`tail -F` subprocess for `--follow`**: Rejected — POSIX-only, no Windows fallback,
  and couples the CLI to an external binary. The tell/seek polling loop is portable
  and ~30 LOC.
- **Lock `agent_runs.jsonl` schema in v1.18**: Rejected — Story 2A.3's dispatcher will
  write the first record; locking the schema before the writer ships invites churn.
  v1.18 reads raw dicts; Story 2A.3 owns `contracts/agent_run.py`.
- **Partial task-id match for `--filter-task`**: Rejected — partial matches are
  ambiguous; `sdlc logs | grep <prefix>` covers prefix search at the shell level.
- **inotify / kqueue for `--follow`**: Rejected — platform-specific complexity with no
  measurable benefit at 0.25 s polling interval; portable polling is simpler.
- **Single combined command (`sdlc audit`)**: Rejected — each command has a distinct
  argument shape, exit posture, and growth trajectory; separating them avoids coupling.

## Consequences

- FR33, FR34, FR45, NFR-OBS-3, and NFR-OBS-6 all have user-facing CLI surfaces.
- The `_ERR_CODE_TO_EXIT_CODE` table grows from 7 to 9 entries. Story 1.21 freezes it.
- The `agent_runs.jsonl` schema-lock punt creates a known forward-compat seam: field
  renames in Story 2A.3 records will silently drop from trace/logs output until
  `contracts/agent_run.py` is added. This risk is documented in ADR-021 and mitigated
  by the recommendation to add the contract module when the first writer ships.
- The 1000-line replay cap is a soft UX bound; users hitting it are redirected to
  `sdlc logs` for streamed output.
- `--follow` polling at 0.25 s adds negligible CPU overhead (< 0.1% on idle); future
  story can switch to inotify/kqueue without changing the CLI surface.
- Duplicated filter predicate logic between `cli/trace.py` and `cli/logs.py` is
  acceptable for v1.18 (single-use); a future story may factor into
  `cli/_event_filters.py`.

## Revisit-by

2027-05-09 — or when Story 2A.3 ships (first `agent_runs.jsonl` writer → add
`contracts/agent_run.py` and lock the schema), or when Story 1.21 runs the
wire-format-lock ceremony (freezes `_TRACE_OUTPUT_SCHEMA`, `_REPLAY_OUTPUT_SCHEMA`,
`_LOGS_OUTPUT_SCHEMA` at `"v1"`).
