# ADR-021: CLI `sdlc trace` + `sdlc replay` + `sdlc logs` + Cross-Stream Merge

**Status:** Accepted (2026-05-09, [Story 1.18](../../_bmad-output/implementation-artifacts/1-18-cli-sdlc-trace-replay-logs.md))

> **Cross-Stream Merge** — the `journal.log` (audit) and `agent_runs.jsonl` (dispatches) streams are read independently and chronologically merged into a single deterministic output stream by `trace` and `logs`, with journal entries tie-breaking before agent_run records at the same `ts`.

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
`JournalError` mapped to `ERR_USER_INPUT` exit 1 with the message `"line N not in
journal (journal has K lines)"`; missing journal file emits the variant `"line N not
in journal (journal log not found at <path>)"` with `details.exists == False`.
Range cap: 1000 lines (the underscore-prefixed `_MAX_REPLAY_RANGE` symbol is private
file-scope encapsulation only — the 1000-line cap is the documented contract; users
hitting it are redirected to `sdlc logs`). Pretty-prints each `JournalEntry` as a
labelled block; `--json` mode emits
`{"command":"replay","lines":[{"lineno":N,"entry":<model_dump>}],"line_count":K}`.

**`cli/logs.py`** (`run_logs`) merges journal + agent_runs streams using the same
predicate logic and chronological sort as `trace`. Supports:

- `--filter-task <id>`: restricts to task-matching entries; validated via `parse_task_id`
  (rejects empty / malformed forms with `ERR_USER_INPUT` exit 1).
- `--filter-agent <name>`: restricts to entries where `actor == "agent:<name>"` (the
  canonical writer convention; journal actors take the `agent:` prefix to disambiguate
  from `cli:` / `hook:`) OR `payload["agent"] == name` (journal payload fallback) OR
  `record["agent"] == name` (agent_runs). Empty `<name>` is rejected with
  `ERR_USER_INPUT` ("must not be empty"); a non-empty `<name>` that does not match the
  canonical convention will silently match nothing (e.g. `--filter-agent claude-code`
  against an entry whose `actor` is bare `claude-code` without `agent:` prefix returns
  zero results — this is intentional). Combined `--filter-task` AND `--filter-agent`
  is intersection (an entry must satisfy both to be kept).
- `--follow`: tail-polls both files at 0.25 s intervals until `KeyboardInterrupt` →
  exit 0. `BrokenPipeError` is also suppressed so `sdlc logs --follow | head -5` exits
  cleanly without a Python traceback when the downstream pipe closes. `--follow` does
  NOT detect file rotation, truncation, or inode replacement in v1.18 (see
  "Deferred to v1.18.1+" below).

**NDJSON shape under `--follow --json`** — one JSON object per line (rather than a
single envelope); each line is a canonical-bytes serialization (`sort_keys=True`,
`ensure_ascii=False`, compact separators) and carries a top-level `"command":"logs"`
key alongside the event fields. The historical-pass and live-pass emissions share the
same shape so a consumer parsing `sdlc logs --follow --json | jq` sees one schema
across the historical→live transition. This is the only command in v1 with
continuous-stream JSON output. Schema-version emission (`"schema_version":"v1"`) on
the wire is intentionally deferred to Story 1.21's wire-format-lock ceremony — the
`_*_OUTPUT_SCHEMA` constants are internal-only until then.

**`agent_runs.jsonl`** has no contract module in v1.18 — records are read as
`dict[str, object]`. Story 2A.3 owns the schema-lock; ADR-021 recommends adding
`contracts/agent_run.py` when the first writer ships.

**`cli/output.py`** is extended with two new error codes (`ERR_JOURNAL_READ_FAILED → 2`,
`ERR_AGENT_RUNS_READ_FAILED → 2`) and three schema constants
(`_TRACE_OUTPUT_SCHEMA`, `_REPLAY_OUTPUT_SCHEMA`, `_LOGS_OUTPUT_SCHEMA`, all `"v1"`).
Story 1.21's wire-format-lock ceremony freezes these constants.

All three commands respect Story 1.17's global `--no-color` / `--json` flags via
`ctx.obj` and are fully read-only (no writes to journal, state, or agent_runs).

JSON output uses `ensure_ascii=False` (canonical-bytes contract); consumers must
accept UTF-8 byte streams. Non-ASCII task-ids are rejected at the `parse_task_id`
layer (Story 1.6); non-ASCII payload values pass through verbatim.

## Error catalog

The `_ERR_CODE_TO_EXIT_CODE` table in `cli/output.py` (extended in Story 1.18 from 7
to 9 entries) maps each error code to a process exit code:

| Code | Exit | Triggered when |
|------|------|----------------|
| `ERR_NOT_INITIALIZED`       | 1 | `state.json` missing at resolved repo root (`sdlc init` not yet run). |
| `ERR_ALREADY_INITIALIZED`   | 1 | `sdlc init` invoked against a repo that already has `state.json`. |
| `ERR_USER_INPUT`            | 1 | Malformed task-id, replay spec, or filter argument. Most user-facing rejections. |
| `ERR_SCAN_FAILED`           | 2 | Scanner walk or state recompute crashed (Story 1.15). |
| `ERR_JOURNAL_APPEND_FAILED` | 2 | Append-only journal write rejected (sequence regression, hash mismatch, etc. — Story 1.11). |
| `ERR_STATE_WRITE_FAILED`    | 2 | Atomic-write to `state.json` failed (Story 1.10). |
| `ERR_INFRASTRUCTURE`        | 3 | Reserved for environment-level failures (filesystem mount loss, etc.). |
| `ERR_JOURNAL_READ_FAILED`   | 2 | `iter_entries` raised `JournalError` while serving `trace` / `replay` / `logs` (Story 1.18). |
| `ERR_AGENT_RUNS_READ_FAILED`| 2 | `iter_agent_runs` raised `OSError` (e.g. permission denied; missing file is silently empty) while serving `trace` / `logs` (Story 1.18). |

Story 1.21's wire-format-lock ceremony freezes this table at the v1 contract.

## Examples

```bash
# Full chronological history of a task (joins journal + agent_runs)
$ sdlc trace EPIC-stripe-webhook-S04-idempotency-T01-redis-key-design
sdlc trace EPIC-stripe-webhook-S04-idempotency-T01-redis-key-design — 3 events
  [2026-05-09T15:30:42.123Z]   kind=state_mutation        target=EPIC-...   actor=cli
  [2026-05-09T15:30:43.001Z]   agent_run             agent=implementer   target_id=EPIC-...   stage=draft   outcome=success   duration_ms=842
  [2026-05-09T15:30:43.500Z]   kind=hook_invocation       target=EPIC-...   actor=hook:naming-validator

# Empty trace — exits 0 with sentinel
$ sdlc trace EPIC-not-touched-yet-S01-foo-T01-bar
sdlc trace EPIC-not-touched-yet-S01-foo-T01-bar — 0 events
(no events recorded for this task yet)

# Combined filters — AND-semantics intersection
$ sdlc logs --filter-task EPIC-... --filter-agent implementer
2026-05-09T15:30:43.001Z  [agent_run/implementer]   stage=draft   outcome=success   task=EPIC-...

# Follow-mode with downstream pipe — exits cleanly when head closes
$ sdlc logs --follow | head -5     # no traceback; BrokenPipeError suppressed

# Range replay — capped at 1000 lines
$ sdlc replay 1-1000               # OK
$ sdlc replay 1-1001               # ERR_USER_INPUT exit 1: "replay range too large (1001 lines requested; max 1000)"

# Missing journal — clearer diagnostic
$ sdlc replay 1                    # before any scan: "line 1 not in journal (journal log not found at <path>)"
```

## Deferred to v1.18.1+

Two behaviors were considered for v1.18 but explicitly deferred (decisions D2 and
D3 from the 2026-05-09 code-review of Story 1.18; tracked in `deferred-work.md`):

- **Rotation / truncation / inode-replacement under `--follow`** — `_poll_journal`
  and `_poll_agent_runs` track a numeric `journal_pos` only. After a truncate (file
  shrinks below `journal_pos`) the loop silently waits forever; after a rotate-replace
  (new inode at the same path) the new file's prefix is skipped. Real `tail -F`
  handles this; v1.18 does not. **Recommendation: avoid `logrotate` on
  `journal.log` / `agent_runs.jsonl` in v1.18.** Revisit when Story 1.20
  (`sdlc rebuild-state`) finalizes truncate semantics — at that point switch to
  `(inode, size)` tracking via `os.stat`.
- **Rich styling for human-readable trace / replay / logs output** — ACs 1.8 / 3.5 /
  4.2 declared rich-styled output via `make_console(ctx)` (bold kind name, dim hashes,
  rule separators, `_OUTCOME_STYLES` color mapping `success`=green / `failure`=red /
  `partial`=yellow). v1.18 ships plain-text via `echo()` only; `make_console` is not
  imported in `trace.py` / `replay.py` / `logs.py`. The spec self-permits this defer
  in dev-note line 938 ("v1.18 ships the plain-text format"). Tracked for v1.18.1.

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

2027-05-09 (per NFR-MAINT-5 12-month revisit) — or earlier when one of these
triggers fires:

- **Story 2A.3 ships** the first `agent_runs.jsonl` writer → add `contracts/agent_run.py`
  and lock the schema; the v1.18 raw-dict reader posture is intentionally provisional.
- **Story 1.21 runs the wire-format-lock ceremony** → freezes the v1 contract surface.
  The ceremony will lock the following items at `"v1"` (currently provisional in v1.18):
  1. The 9-entry `_ERR_CODE_TO_EXIT_CODE` table and its exit-code mappings.
  2. The `_TRACE_OUTPUT_SCHEMA`, `_REPLAY_OUTPUT_SCHEMA`, `_LOGS_OUTPUT_SCHEMA`
     constants AND the decision whether to emit `"schema_version":"v1"` on the wire
     (decision E1 from the Story 1.18 code-review: deferred to 1.21 to avoid
     double-work; consumers cannot detect schema version at runtime in v1.18).
  3. The NDJSON `"command":"logs"` per-line key for `--follow --json`.
  4. The canonical-bytes serialization contract (`sort_keys=True`, `ensure_ascii=False`,
     compact separators, trailing newline) used by `emit_json` / `emit_error`.
- **Story 1.18.1** lands rich styling and (likely) `tail -F`-style rotation handling
  for `--follow`, closing the two "Deferred to v1.18.1+" items above.
