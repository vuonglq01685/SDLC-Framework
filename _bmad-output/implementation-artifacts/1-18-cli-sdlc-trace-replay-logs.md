# Story 1.18: CLI `sdlc trace` + `sdlc replay` + `sdlc logs`

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user debugging a task lifecycle or replaying a journal entry,
I want `sdlc trace <task-id>`, `sdlc replay <line-or-range>`, and `sdlc logs` (with `--filter-task`, `--filter-agent`, `--follow` flags),
so that the full audit chain is interrogable from the CLI without parsing JSONL files manually — closing the FR33/FR34/FR45 audit-surface gap so users can self-serve "what happened to this task?", "show me line 42 of the journal", and "tail every agent dispatch live" without writing one-off scripts (FR33, FR34, FR45, NFR-OBS-3, NFR-OBS-6, Architecture §117, §123, §347 Decision B3, §397 Decision E3, §479-§480 canonical layout, §540-§559 exit codes + error envelope, §595-§606 JournalEntry contract, §669-§680 CLI output conventions, §791-§810 cli/* layout, §1159-§1171 FR mapping, §1196 Concern 12 observability).

## Acceptance Criteria

**AC1 — `sdlc trace <task-id>` reconstructs the chronological history of all events affecting that task-id (epic AC block 1, FR33, NFR-OBS-3)**

**Given** the framework is initialized via `sdlc init` (Story 1.16) AND has been scanned at least once (Story 1.17 — so `state.json` and `journal.log` both exist),

**When** the user invokes `sdlc trace <task-id>` from any cwd inside `<repo_root>` (e.g. `sdlc trace EPIC-stripe-webhook-S04-idempotency-handling-T01-redis-key-design`),

**Then**:

1. The command resolves the repo root via the same `_get_repo_root_or_cwd()` helper used by Stories 1.16-1.17 (factor into `cli/_paths.py` if any prior story already extracted it; otherwise duplicate inline at ≤ 7 LOC). Calls `subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False, timeout=5)`; on failure, falls back to `Path.cwd().resolve()`. Catches only `OSError`, `subprocess.SubprocessError`, `FileNotFoundError` — narrow.
2. The command refuses with exit 1 + `emit_error("ERR_NOT_INITIALIZED", ...)` if `<repo_root>/.claude/state/state.json` does NOT exist. Mirror Story 1.17's refusal pattern verbatim:
   ```
   sdlc: project not initialized at <repo_root>; run `sdlc init` first
   ```
3. **Task-id validation**: the `<task-id>` positional argument is parsed via `sdlc.ids.parse_task_id` (Story 1.6). On `IdsError`, the command emits `emit_error("ERR_USER_INPUT", "invalid task identifier: <message>", ctx=ctx, details={"input": <raw>, "rule": <ids_rule>})` and exits 1. The error envelope's `details` block carries the `IdsError.details` mapping verbatim (already typed `dict[str, object]` in `errors/base.py:25`); no sanitization needed for ID strings (no secret patterns).
4. **Journal read**: the command calls `sdlc.journal.iter_entries(<repo_root>/.claude/state/journal.log)` (Story 1.11) to enumerate every entry in monotonic_seq order. Reader handles missing file (yields nothing → empty trace, exit 0).
5. **Filter predicate**: an entry matches the trace iff:
   - `entry.target_id == <task-id-raw>` (exact match), OR
   - `entry.kind == "agent_dispatch"` AND `entry.payload.get("task_id") == <task-id-raw>` (forward-compat for Story 2x's agent_dispatch entries that carry task_id in payload, NOT target_id), OR
   - `entry.kind == "hook_invocation"` AND `entry.payload.get("target_id") == <task-id-raw>` (forward-compat for hook entries scoped to a different `target_id` than the hook itself).

   The predicate is implemented as a private helper `_event_affects_task(entry: JournalEntry, task_id: str) -> bool` — small, pure, unit-testable. Future stories extend the predicate; v1.18 covers the three cases above.
6. **Agent runs read**: if `<repo_root>/03-Implementation/agent_runs.jsonl` exists (Architecture §479; Story 2x writes this, but the file may be absent on a fresh project), the command reads each line, parses as JSON, and includes any record where `record.get("target_id") == <task-id-raw>` OR `record.get("task_id") == <task-id-raw>` in the chronological output. Malformed lines (`json.JSONDecodeError`) are SKIPPED with a `_logger.warning("malformed agent_runs line at %s:%d: %s — skipping", path, lineno, exc)` — same permissive-reader posture as `journal/reader.py:45-50`. Missing file is silently treated as "no agent runs to display" (NOT an error — Story 2x hasn't shipped the writer yet at v1.18 time). For v1.18 there is NO contract module for agent_runs.jsonl entries — read as raw `dict[str, object]` and display selected fields (`ts`, `agent`, `target_id`, `stage`, `outcome`, `duration_ms`); the Story 2A/2B authors lock the schema later. Document this in dev notes as a known forward-compat seam.
7. **Chronological merge + sort**: the journal entries (already sorted by `monotonic_seq`) and the agent runs (sorted by `ts` parsed via `datetime.fromisoformat(ts.replace("Z", "+00:00"))` — same 3.10-compat trick as Story 1.17) are MERGED into a single chronological stream sorted by `ts`. Tie-break: when two events share an identical `ts` string (rare but possible at millisecond resolution), the journal entry sorts FIRST by `monotonic_seq`; agent runs without an explicit seq sort AFTER the journal entry by stable insertion order. This determinism matters for replay tests.
8. **Output (default human-readable mode)**: stdout prints a header line + one row per event:
   ```
   sdlc trace <task-id> — N events
     [ts]   kind=<kind>           target=<target_id>   actor=<actor>
     [ts]   agent_run             agent=<name>         stage=<stage>   outcome=<outcome>
     ...
   ```
   The format is rich-styled when `--no-color` is NOT set (use `make_console(ctx)` from Story 1.17's `cli/output.py`); plain text otherwise. Exact bytes are not load-bearing; tests assert presence of `<task-id>`, the count `N`, and at least one `kind=` substring per matching entry.
9. **Output (`--json` mode)**: stdout emits a single canonical JSON document per AC2 below.
10. **Exit code 0** ALWAYS for a valid task-id (per epic AC explicitly: "exits 0 even if the task has no events yet"). The "no events" case prints:
    ```
    sdlc trace <task-id> — 0 events
    (no events recorded for this task yet)
    ```
    and still exits 0.
11. The implementation lives in `src/sdlc/cli/trace.py`. The Typer command function `trace_command(ctx, task_id)` is registered in `cli/main.py` and defers `from sdlc.cli.trace import run_trace` to body level per Architecture §488.

**And** the trace operation is fully read-only: no writes to `state.json`, `journal.log`, or `agent_runs.jsonl`; no subprocess calls beyond the optional `git rev-parse` repo-root resolver.

**And** `sdlc trace` does NOT chain UP the hierarchy (it does NOT also include events for the parent story or epic). Rationale: a task-scoped trace is the canonical FR33 surface; a cross-scope trace is a future story (NOT in v1.18's contract). Document this scoping decision in dev notes — users wanting story-scope or epic-scope traces will get a v2.x feature; v1.18 trims to task-scope to match epic AC verbatim ("the full chronological history: state transitions, agent runs, hook invocations affecting that task-id").

**AC2 — `sdlc trace --json` envelope (epic AC block 1, Architecture §549, §678-§679)**

**Given** the user appends `--json` to `sdlc trace <task-id>`,

**When** the command executes successfully,

**Then** stdout contains EXACTLY ONE canonical JSON document:
```json
{
  "command": "trace",
  "task_id": "EPIC-stripe-webhook-S04-idempotency-handling-T01-redis-key-design",
  "project_root": "/abs/path/to/repo",
  "events": [
    {
      "source": "journal",
      "ts": "2026-05-08T15:30:42.123Z",
      "monotonic_seq": 7,
      "kind": "state_mutation",
      "actor": "cli",
      "target_id": "EPIC-stripe-webhook-S04-idempotency-handling-T01-redis-key-design",
      "before_hash": "sha256:...",
      "after_hash": "sha256:...",
      "payload": {<verbatim>}
    },
    {
      "source": "agent_runs",
      "ts": "2026-05-08T15:30:50.456Z",
      "agent": "implementer",
      "stage": "code",
      "outcome": "success",
      "duration_ms": 8420,
      "raw": {<verbatim agent_runs line dict>}
    }
  ],
  "event_count": 2
}
```

**And**:

1. The JSON document is canonical-bytes per Story 1.17's `cli/output.py:emit_json`: `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` + trailing `\n`.
2. The `source` discriminator (`"journal"` vs `"agent_runs"`) lets consumers distinguish stream provenance without parsing fields heuristically. Future v2.x adds `"debug_events"` source when Story 2x's `debug_events.jsonl` lands.
3. Empty result still emits a valid envelope: `{"command":"trace","event_count":0,"events":[],"project_root":"...","task_id":"..."}` (sorted-keys order).
4. Errors in `--json` mode use the standard error envelope per Architecture §549-§559 — emitted on STDERR, NOT stdout. Stdout stays clean (one JSON doc per success, zero JSON docs per failure).
5. Per-command schema documented in `cli/output.py` as `_TRACE_OUTPUT_SCHEMA: Final[str] = "v1"` constant alongside Story 1.17's `_SCAN_OUTPUT_SCHEMA` / `_STATUS_OUTPUT_SCHEMA`. Story 1.21's wire-format-lock ceremony freezes this.

**AC3 — `sdlc replay <line>` and `sdlc replay <start>-<end>` pretty-print parsed journal entries (epic AC block 2, FR34)**

**Given** a populated `<repo_root>/.claude/state/journal.log`,

**When** the user invokes `sdlc replay 42` (single 1-indexed line) or `sdlc replay 42-50` (inclusive range),

**Then**:

1. **Argument parser**: the `<line-or-range>` positional is parsed via a private helper `_parse_line_spec(spec: str) -> tuple[int, int]` returning `(start, end)` with `start <= end`, both 1-indexed inclusive. Accepted forms:
   - `"42"` → `(42, 42)` (single line)
   - `"42-50"` → `(42, 50)` (inclusive range; `50` IS read)
   - `"42-42"` → `(42, 42)` (degenerate range; allowed)

   Rejected forms (raise `JournalError("invalid replay spec: ...")` mapped to `ERR_USER_INPUT` exit 1 via `emit_error`):
   - Empty string `""`
   - Non-numeric: `"abc"`, `"1a"`, `"-5"`, `"5-"`, `"-"`
   - Inverted range: `"50-42"` (start > end) — message: `"replay spec start must be ≤ end (got 50-42)"`
   - Zero or negative: `"0"`, `"-1"`, `"0-5"` — line numbers are 1-indexed; `"0"` is rejected with `"line numbers are 1-indexed; got 0"`.
   - Multi-dash: `"1-2-3"` — message: `"replay spec must be 'N' or 'N-M'"`.
2. **Journal read**: calls `sdlc.journal.iter_entries(journal_path)` and enumerates entries with a 1-indexed counter (`for lineno, entry in enumerate(iter_entries(...), start=1):`). Collects entries where `lineno` falls in `[start, end]`.
3. **Out-of-range handling**: if any line in `[start, end]` exceeds the journal's actual line count, the command emits `emit_error("ERR_USER_INPUT", "line N not in journal (journal has K lines)", ctx=ctx, details={"requested_line": N, "journal_lines": K, "path": str(journal_path)})` and exits 1. The exact message **"line N not in journal"** is REQUIRED by epic AC ("an out-of-range line raises `JournalError(\"line N not in journal\")`"); the human-readable message string MUST contain this substring verbatim. The error code remains `ERR_USER_INPUT` (1) because the user supplied an invalid line number, not a framework failure.
4. **Empty journal handling**: if the journal is empty (0 lines) AND any line is requested, error per AC3.3 with `K=0` (i.e. `"line 42 not in journal (journal has 0 lines)"`).
5. **Pretty-print (default human-readable mode)**: each entry renders as a multi-line block:
   ```
   --- line 42 ---
   monotonic_seq:  7
   ts:             2026-05-08T15:30:42.123Z
   actor:          cli
   kind:           scan_completed
   target_id:      state
   before_hash:    sha256:e3b0c44298fc1c149afbf4c8996fb924...
   after_hash:     sha256:8a7f2c3d1e5b9a0d6e4f3c2b1a9d8e7f...
   payload:
     epic_count: 0
     story_count: 0
     task_count: 0
   ```
   The format uses Story 1.17's `make_console(ctx)` for color (kind name styled bold; hashes dimmed; `--- line N ---` separator styled with rule). With `--no-color`, output is plain text per the AC4 contract Story 1.17 already enforces. Tests assert presence of the line marker `--- line 42 ---` and the field names `monotonic_seq:`, `ts:`, etc., NOT exact byte format.
6. **`--json` mode**: emits ONE canonical JSON document on stdout containing the parsed pydantic models:
   ```json
   {
     "command": "replay",
     "lines": [{"lineno": 42, "entry": <JournalEntry.model_dump>}, ...],
     "line_count": <int>
   }
   ```
   The `entry` value is the result of `entry.model_dump(mode="json")` — same shape as state.json contract.
7. **Range size cap**: ranges larger than 1000 lines (`end - start + 1 > 1000`) are REJECTED with `ERR_USER_INPUT` and message `"replay range too large (N lines requested; max 1000)"`. Rationale: stdout flooding is unhelpful and `sdlc logs --filter-task` (AC5) is the canonical surface for arbitrary-size streams. Document the 1000 cap in dev notes + ADR-021. The cap is configurable via the constant `_MAX_REPLAY_RANGE: Final[int] = 1000` in `cli/replay.py` so v2.x can revisit cheaply.
8. **Exit code 0** on successful replay of any non-empty result.
9. The implementation lives in `src/sdlc/cli/replay.py`. The Typer command function `replay_command(ctx, line_spec)` is registered in `cli/main.py` and defers `from sdlc.cli.replay import run_replay` to body level.

**And** `sdlc replay` is fully read-only — no journal writes, no state mutation, no subprocess calls.

**AC4 — `sdlc logs` tails the journal AND `agent_runs.jsonl` with rich formatting + filters (epic AC block 3, FR45, NFR-OBS-6)**

**Given** a populated `<repo_root>/.claude/state/journal.log` AND optionally `<repo_root>/03-Implementation/agent_runs.jsonl`,

**When** the user invokes `sdlc logs` (with optional flags `--filter-task <id>`, `--filter-agent <name>`, `--follow`),

**Then**:

1. **Default behavior (no `--follow`)**: prints every entry from BOTH streams in chronological order (merged + sorted by `ts` per AC1.7's tie-break rule), then exits 0. Limit defaults to "all entries" (no implicit head/tail truncation in v1.18); v2.x can add `--limit N` if streams grow large. The journal is bounded by typical CLI session activity (≤ thousands of entries); `agent_runs.jsonl` similarly. Walltime budget: < 1 s for journals up to ~10k entries (no benchmark gate in v1.18; informal target).
2. **Format (default human-readable mode)**: each entry renders as a single styled line:
   ```
   2026-05-08T15:30:42.123Z  [journal/scan_completed]   actor=cli       target=state
   2026-05-08T15:30:50.456Z  [agent_run/implementer]    stage=code      outcome=success  task=EPIC-stripe-...-T01-redis-key-design
   ```
   Rich-styled with color when `--no-color` is not set:
   - Timestamp: dim
   - `[stream/kind]`: bold; stream prefix differentiates `journal/<kind>` vs `agent_run/<agent>`
   - Field key=value pairs: plain
   - Outcome `success`: green; `failure`: red; `partial`: yellow (forward-compat — v1.18's MockAIRuntime stories produce only `success` outcomes, but the styling is wired)
3. **`--filter-task <task-id>`**: restricts the merged stream to entries where the AC1.5 / AC1.6 predicate matches the supplied `<task-id>`. Validates the supplied `<task-id>` via `parse_task_id` — invalid → `ERR_USER_INPUT` exit 1.
4. **`--filter-agent <agent-name>`**: restricts the merged stream to entries where:
   - Journal entries: `entry.actor == f"agent:{<name>}"` (Architecture §600's actor format) OR `entry.payload.get("agent") == <name>`.
   - Agent runs: `record.get("agent") == <name>`.
   The `<name>` is a free-form string (no `parse_*` helper); the filter is a literal string equality.
5. **Combining filters**: `--filter-task` AND `--filter-agent` together AND-merge (entry must match BOTH). Tests cover the AND case explicitly.
6. **`--follow` mode**: after printing all current entries, the command POLLS both files for new lines and emits them as they arrive. Implementation:
   ```python
   def _follow_streams(...) -> None:
       # Open each file at the END (seek to current EOF), then loop:
       #   read any new bytes appended since last read
       #   parse new JSONL lines and emit
       #   sleep _FOLLOW_INTERVAL_S (default 0.25 s)
       # Loop terminates on KeyboardInterrupt (user presses Ctrl-C) — handler is silent
       # exit 0; no stack trace.
   ```
   The follow loop respects `_FOLLOW_INTERVAL_S: Final[float] = 0.25` constant. POSIX-cross-platform — uses `Path.open("r")` + `f.tell() / f.seek()` (NOT inotify, NOT fcntl); works on Windows for the read path. KeyboardInterrupt is caught at the `run_logs()` level and translates to `raise typer.Exit(code=0)` — Ctrl-C is the canonical termination signal, not an error.
7. **`--json` mode (with `--follow`)**: each line is a SEPARATE canonical JSON document on its own line (NDJSON format) — NOT a single document, because follow has no terminal. The command emits NDJSON and the user pipes through `jq -c` if they want line-by-line. Document this exception to "exactly one JSON doc per command" in dev notes — `--follow` is the only command in v1 where stdout is a continuous NDJSON stream.
8. **`--json` mode (without `--follow`)**: emits ONE canonical JSON document per the standard pattern:
   ```json
   {
     "command": "logs",
     "filters": {"task_id": "<id-or-null>", "agent": "<name-or-null>"},
     "events": [<as in trace>],
     "event_count": <int>
   }
   ```
9. **Exit code 0** on graceful termination (end-of-stream for non-follow; Ctrl-C for follow).
10. The implementation lives in `src/sdlc/cli/logs.py`. The Typer command function `logs_command(ctx, filter_task, filter_agent, follow)` is registered in `cli/main.py` and defers `from sdlc.cli.logs import run_logs` to body level.

**And** in `--follow` mode, file rotation is NOT handled (if a downstream tool truncates/replaces journal.log mid-follow, the follow loop may yield partial content or stale data). Document this as a known limitation; v1.18 is "happy-path follow only" — `journal.log` rotation is not a v1 concern (no rotation is performed by the framework itself; rotation policy is Story 4.x or later).

**And** `sdlc logs` is fully read-only — no writes to either stream.

**AC5 — `cli/output.py` extends with new error codes for trace/replay/logs (Architecture §549, Story 1.17's `_ERR_CODE_TO_EXIT_CODE` table)**

**Given** Story 1.17 shipped `cli/output.py` with `emit_error`, `emit_json`, and the `_ERR_CODE_TO_EXIT_CODE` table,

**When** Story 1.18 lands,

**Then** `src/sdlc/cli/output.py` is EXTENDED (NOT rewritten) to add the new error codes:

```python
_ERR_CODE_TO_EXIT_CODE: Final[Mapping[str, int]] = MappingProxyType(
    {
        # Existing from Story 1.17:
        "ERR_NOT_INITIALIZED": 1,
        "ERR_ALREADY_INITIALIZED": 1,
        "ERR_USER_INPUT": 1,
        "ERR_SCAN_FAILED": 2,
        "ERR_JOURNAL_APPEND_FAILED": 2,
        "ERR_STATE_WRITE_FAILED": 2,
        "ERR_INFRASTRUCTURE": 3,
        # New in Story 1.18:
        "ERR_JOURNAL_READ_FAILED": 2,    # iter_entries raised JournalError
        "ERR_AGENT_RUNS_READ_FAILED": 2, # agent_runs.jsonl read raised OSError beyond missing-file
    }
)
```

**And**:

1. Per-command output schema constants are added: `_TRACE_OUTPUT_SCHEMA: Final[str] = "v1"`, `_REPLAY_OUTPUT_SCHEMA: Final[str] = "v1"`, `_LOGS_OUTPUT_SCHEMA: Final[str] = "v1"`. Documented in module docstring + ADR-021.
2. NO new public functions are added to `cli/output.py` in v1.18 — `emit_json` / `emit_error` / `make_console` / `is_no_color_active` / `echo` cover all v1.18 needs. Story 1.18's modules are CONSUMERS of the 1.17 surface, NOT extenders.
3. The boundary linter (`scripts/check_module_boundaries.py`) does NOT need widening — `cli` already depends on `state, journal, contracts, ids, errors` per Story 1.16's widening + Story 1.17's verification step. Story 1.18's new files (`cli/trace.py`, `cli/replay.py`, `cli/logs.py`) consume only those modules. Confirm via `grep -A5 '"cli": ModuleSpec' scripts/check_module_boundaries.py`.

**AC6 — `cli/main.py` registers `trace`, `replay`, `logs` subcommands (Architecture §791)**

**Given** Story 1.17 shipped `cli/main.py` with `init`, `scan`, `status` subcommands + global `--no-color` / `--json` flags,

**When** Story 1.18 lands,

**Then**:

1. `cli/main.py` is EXTENDED (NOT rewritten) to register three new subcommands:
   ```python
   @app.command(name="trace")
   def trace_command(
       ctx: typer.Context,
       task_id: str = typer.Argument(..., help="Task identifier (EPIC-...-S<NN>-...-T<NN>-...)."),
   ) -> None:
       """Reconstruct chronological history of a task (FR33)."""
       from sdlc.cli.trace import run_trace  # deferred per Architecture §488
       run_trace(ctx=ctx, task_id=task_id)


   @app.command(name="replay")
   def replay_command(
       ctx: typer.Context,
       line_spec: str = typer.Argument(..., help="Line number or range (e.g. '42' or '42-50')."),
   ) -> None:
       """Pretty-print parsed journal entries by line (FR34)."""
       from sdlc.cli.replay import run_replay  # deferred
       run_replay(ctx=ctx, line_spec=line_spec)


   @app.command(name="logs")
   def logs_command(
       ctx: typer.Context,
       filter_task: str | None = typer.Option(None, "--filter-task", help="Restrict to entries matching this task-id."),
       filter_agent: str | None = typer.Option(None, "--filter-agent", help="Restrict to entries from this agent."),
       follow: bool = typer.Option(False, "--follow", "-f", help="Tail-follow streams; exit on Ctrl-C."),
   ) -> None:
       """Tail journal + agent_runs.jsonl with filters (FR45, NFR-OBS-6)."""
       from sdlc.cli.logs import run_logs  # deferred
       run_logs(ctx=ctx, filter_task=filter_task, filter_agent=filter_agent, follow=follow)
   ```
2. `cli/main.py` LOC stays ≤ 180 (Story 1.17 caps at ~130; Story 1.18 adds ~40-50 LOC of subcommand registrations + arg parsing). If exceeded, factor argument-help strings into a `cli/_main_helpers.py:HELP_TEXTS` constant.
3. Module-level imports stay minimal per Architecture §488: `typer`, `sdlc.cli.version.get_version`, `os`, `sys`, `json` (Story 1.16-1.17's set). NO `from sdlc.engine import ...`, NO `from sdlc.state import ...`, NO `from sdlc.journal import ...` at module level — all deferred to subcommand body. Cold-start regression test (Story 1.16's `test_main_app_imports_under_200ms` if it exists) MUST stay green.
4. The `--help` output includes `trace`, `replay`, `logs` in the subcommand list. Tests verify presence.

**AC7 — Tests prove `trace`, `replay`, `logs` all work end-to-end (epic AC block 1+2+3)**

**Given** the test pyramid established by Stories 1.10-1.17,

**When** Story 1.18 lands,

**Then** the test suite contains:

1. **Unit tests** at `tests/unit/cli/test_trace.py` (with `pytestmark = pytest.mark.unit`):
   - `test_trace_refuses_when_state_not_initialized(tmp_path)`: invoke `run_trace` against a `tmp_path` with no `.claude/state/state.json`; assert `typer.Exit` with `exit_code == 1`; capsys stderr contains "not initialized".
   - `test_trace_rejects_invalid_task_id(tmp_path)`: bootstrap project; invoke `run_trace(ctx, task_id="not-a-task-id")`; assert exit 1; stderr contains "invalid task identifier".
   - `test_trace_empty_journal_exits_zero(tmp_path)`: bootstrap (no scans yet); invoke `run_trace` with a syntactically valid task-id; assert exit 0 + stdout "0 events".
   - `test_trace_filters_by_target_id(tmp_path)`: bootstrap + manually append 3 journal entries (use `sdlc.journal.append_sync` directly with crafted `JournalEntry` instances) — entry A has `target_id=<our-task-id>`; entries B and C have different target_ids. Invoke `run_trace`; assert exactly entry A appears in output.
   - `test_trace_filters_by_payload_task_id_for_agent_dispatch(tmp_path)`: append a journal entry with `kind="agent_dispatch"`, `target_id="something-else"`, `payload={"task_id": "<our-task-id>", "agent": "implementer"}`; assert it appears in trace output (covers AC1.5 second clause).
   - `test_trace_includes_agent_runs_jsonl_entries(tmp_path)`: bootstrap; manually create `03-Implementation/agent_runs.jsonl` with 2 lines (one matching task-id, one not); invoke `run_trace`; assert exactly the matching line appears in output, sorted chronologically with journal entries.
   - `test_trace_handles_missing_agent_runs_silently(tmp_path)`: bootstrap; do NOT create agent_runs.jsonl; append journal entries; invoke `run_trace`; assert exit 0 + journal entries appear (agent_runs absence is non-fatal).
   - `test_trace_skips_malformed_agent_runs_lines(tmp_path, caplog)`: bootstrap; create agent_runs.jsonl with 1 valid line + 1 malformed (bad JSON); invoke `run_trace`; assert valid line appears + caplog has WARNING with "malformed agent_runs line".
   - `test_trace_chronological_sort(tmp_path)`: append 2 journal entries with timestamps T1 < T2; create agent_runs.jsonl with one record at timestamp T1.5; invoke `run_trace`; assert output order is journal[T1], agent_run[T1.5], journal[T2].
   - `test_trace_json_mode_envelope_keys(tmp_path)`: bootstrap; populate; invoke via CliRunner with `["--json", "trace", "<task-id>"]`; `json.loads(result.stdout)`; assert keys exactly `{"command", "task_id", "project_root", "events", "event_count"}`.
   - `test_trace_json_empty_envelope(tmp_path)`: bootstrap (empty journal); invoke `--json trace <task-id>`; assert `payload["events"] == []` and `payload["event_count"] == 0`.

2. **Unit tests** at `tests/unit/cli/test_replay.py` (with `pytestmark = pytest.mark.unit`):
   - `test_replay_refuses_when_state_not_initialized(tmp_path)`: same pattern as trace.
   - `test_replay_parse_line_spec_valid_forms`: parametrized over `["42"→(42,42), "42-50"→(42,50), "42-42"→(42,42), "1"→(1,1)]`; assert helper returns expected tuple.
   - `test_replay_parse_line_spec_invalid_forms`: parametrized over `["", "abc", "0", "-1", "5-", "-5", "50-42", "1-2-3", " ", "1.5", "1-2.5"]`; assert each raises `JournalError` with descriptive message.
   - `test_replay_single_line(tmp_path)`: bootstrap + append 5 journal entries; invoke `run_replay(line_spec="3")`; assert stdout contains `--- line 3 ---` AND the 3rd entry's `monotonic_seq` (e.g. `monotonic_seq:  2` — 0-indexed seqs vs 1-indexed lines).
   - `test_replay_range(tmp_path)`: bootstrap + append 10 entries; invoke `run_replay(line_spec="3-5")`; assert stdout contains 3 line markers (`--- line 3 ---`, `--- line 4 ---`, `--- line 5 ---`).
   - `test_replay_out_of_range_single(tmp_path)`: append 3 entries; invoke `run_replay(line_spec="42")`; assert exit 1 + stderr contains "line 42 not in journal".
   - `test_replay_out_of_range_range_partially_past_eof(tmp_path)`: append 5 entries; invoke `run_replay(line_spec="3-10")`; assert exit 1 + stderr names the actual line count.
   - `test_replay_empty_journal(tmp_path)`: bootstrap (no journal entries); invoke `run_replay(line_spec="1")`; assert exit 1 + stderr contains "line 1 not in journal" + "0 lines".
   - `test_replay_range_too_large(tmp_path)`: any large request like `"1-1001"`; assert exit 1 + stderr contains "range too large".
   - `test_replay_json_mode_envelope_keys(tmp_path)`: append entries; invoke `["--json", "replay", "1-3"]`; assert keys `{"command", "lines", "line_count"}` and `len(payload["lines"]) == 3`.
   - `test_replay_json_entry_field_shape(tmp_path)`: append a known entry; invoke `--json replay 1`; assert `payload["lines"][0]["entry"]` has the canonical JournalEntry field set (`schema_version`, `monotonic_seq`, `ts`, `actor`, `kind`, `target_id`, `before_hash`, `after_hash`, `payload`).
   - `test_replay_human_readable_includes_field_labels(tmp_path)`: invoke without `--json`; assert stdout contains `monotonic_seq:`, `kind:`, `target_id:`, `payload:`.

3. **Unit tests** at `tests/unit/cli/test_logs.py` (with `pytestmark = pytest.mark.unit`):
   - `test_logs_refuses_when_state_not_initialized(tmp_path)`: same pattern.
   - `test_logs_prints_all_entries_default(tmp_path)`: bootstrap + append 3 journal entries; invoke `run_logs(ctx, filter_task=None, filter_agent=None, follow=False)`; assert all 3 appear.
   - `test_logs_filter_task(tmp_path)`: append 5 journal entries (2 matching task-id, 3 not); invoke with `filter_task=<id>`; assert exactly 2 in output.
   - `test_logs_filter_task_invalid_id(tmp_path)`: invoke with `filter_task="not-a-task-id"`; assert exit 1 + stderr "invalid task identifier".
   - `test_logs_filter_agent_journal_actor(tmp_path)`: append journal entry with `actor="agent:implementer"`; invoke `filter_agent="implementer"`; assert entry appears (covers AC4.4 actor pattern).
   - `test_logs_filter_agent_payload(tmp_path)`: append entry with `actor="cli"`, `payload={"agent": "researcher"}`; invoke `filter_agent="researcher"`; assert entry appears (covers AC4.4 payload-fallback).
   - `test_logs_filter_agent_runs_record(tmp_path)`: create agent_runs.jsonl with one record `{"agent": "implementer", ...}`; invoke `filter_agent="implementer"`; assert record appears.
   - `test_logs_combined_filters_and_logic(tmp_path)`: append entries; invoke with both `filter_task` and `filter_agent`; assert only entries matching BOTH appear.
   - `test_logs_chronological_merge_with_agent_runs(tmp_path)`: same merge property as trace test 9; assert journal + agent_runs interleave by `ts`.
   - `test_logs_json_mode_envelope_keys_no_follow(tmp_path)`: invoke `["--json", "logs"]`; assert keys `{"command", "filters", "events", "event_count"}`.
   - `test_logs_json_filters_block_keys(tmp_path)`: invoke with `filter_task=<id>`; assert `payload["filters"]["task_id"] == <id>` and `payload["filters"]["agent"] is None`.
   - `test_logs_no_follow_returns_after_streams_exhausted(tmp_path)`: invoke without `--follow`; assert returns within ~1 second (no infinite loop).

4. **Unit test** at `tests/unit/cli/test_logs_follow.py` (with `pytestmark = pytest.mark.unit`):
   - `test_follow_emits_new_journal_entries(tmp_path)`: bootstrap + start `run_logs(..., follow=True)` in a thread; sleep ~0.5 s; append a NEW journal entry from the test thread; sleep ~0.5 s; raise `KeyboardInterrupt` into the thread (or send SIGINT via signal); assert the new entry appeared in captured stdout. Use `pytest.MonkeyPatch` to override `_FOLLOW_INTERVAL_S` to 0.05 s for test speed. Skip on Windows if signal-based interrupt is brittle (`pytest.mark.skipif(sys.platform == "win32", reason="signal-based KI flaky on Windows")`).
   - `test_follow_keyboard_interrupt_exits_zero(tmp_path)`: invoke follow + immediately raise KeyboardInterrupt; assert exit 0; assert NO stack trace on stderr.

5. **Unit tests** at `tests/unit/cli/test_main.py` (extends Stories 1.16-1.17's file):
   - `test_main_app_has_trace_subcommand`: invoke `["--help"]`; assert "trace" appears.
   - `test_main_app_has_replay_subcommand`: invoke `["--help"]`; assert "replay" appears.
   - `test_main_app_has_logs_subcommand`: invoke `["--help"]`; assert "logs" appears.
   - `test_main_app_trace_requires_task_id`: invoke `["trace"]` (no arg); assert non-zero exit + Typer's "missing argument" message.
   - `test_main_app_replay_requires_line_spec`: invoke `["replay"]`; same as above.

6. **Unit tests** at `tests/unit/cli/test_output.py` (extends Story 1.17's file):
   - `test_emit_error_new_codes_map_to_exit_codes`: parametrized over `[("ERR_JOURNAL_READ_FAILED", 2), ("ERR_AGENT_RUNS_READ_FAILED", 2)]`; invoke `emit_error(code, "test", ctx=<json_ctx>)`; assert raises `typer.Exit` with the mapped exit code.

7. **Integration test** at `tests/integration/test_trace_replay_logs_e2e.py` (with `pytestmark = [pytest.mark.integration, pytest.mark.e2e]`):
   - `test_full_lifecycle_init_scan_trace_replay_logs(tmp_path)`: in tmp_path: `subprocess.run(["uv", "run", "sdlc", "init"])`; create a synthetic task by manually appending a journal entry with target_id=<task-id>; `subprocess.run(["uv", "run", "sdlc", "trace", <task-id>])`; assert exit 0 + stdout contains the task-id; `subprocess.run(["uv", "run", "sdlc", "replay", "1"])`; assert exit 0 + stdout contains "--- line 1 ---"; `subprocess.run(["uv", "run", "sdlc", "logs"])`; assert exit 0 + entry appears. Skip on Windows when `shutil.which("uv") is None`.
   - `test_no_color_flag_strips_ansi_on_trace_replay_logs(tmp_path)`: parametrized variant of Story 1.17's `test_no_color_every_command.py` — extended to include `["trace", <task-id>]`, `["replay", "1"]`, `["logs"]`; assert zero ANSI in stdout AND stderr.
   - `test_json_mode_emits_canonical_envelope_for_trace_replay_logs(tmp_path)`: parametrized over the three commands; assert `json.loads(result.stdout)` succeeds and yields the expected key set.

8. **Integration test** at `tests/integration/test_logs_follow_subprocess.py` (with `pytestmark = pytest.mark.integration` AND `pytest.mark.skipif(sys.platform == "win32", reason="follow-mode tail under subprocess flaky on Windows")`):
   - `test_logs_follow_picks_up_new_entry`: spawn `subprocess.Popen(["uv", "run", "sdlc", "logs", "--follow"], stdout=PIPE)`; wait ~0.5 s; from the parent, append a new journal entry; wait ~0.5 s; send SIGINT to the child; read stdout; assert new entry appears. Wraps the child in a try/finally that always SIGINTs to avoid orphan processes.

9. **Coverage gate**: new modules `cli/trace.py`, `cli/replay.py`, `cli/logs.py` MUST reach ≥ 90% line coverage from unit + integration suites combined. Existing global `--cov-fail-under=90` (`pyproject.toml:177`) enforces this.

**And** all new test files include `from __future__ import annotations` as the first non-comment line + the module-level `pytestmark` declaration. Test classes are NOT used (project convention; bare functions only).

**And** the existing `tests/unit/cli/test_main.py` (Stories 1.16-1.17) is EXTENDED (not rewritten) with the 5 new tests from AC7.5.

**AC8 — ADR-021 records the trace/replay/logs design + cross-stream merge contract**

**Given** NFR-MAINT-5 ("every load-bearing decision recorded as an ADR"),

**When** Story 1.18 lands,

**Then** `docs/decisions/ADR-021-cli-trace-replay-logs.md` is authored using `docs/decisions/adr-template.md` covering:

1. **Status:** Accepted, dated to story-implement day.
2. **Context:** FR33, FR34, FR45, NFR-OBS-3, NFR-OBS-6 mapping; Story 1.7 (JournalEntry contract), Story 1.11 (journal reader), Story 1.16-1.17 (CLI scaffolding) provide the substrate. Story 2x will write `agent_runs.jsonl`; v1.18 reads it as raw JSONL with no contract module — schema-lock is deferred.
3. **Decision:**
   - `cli/trace.py` filters journal entries by task-id via three predicates (target_id match, agent_dispatch payload.task_id match, hook_invocation payload.target_id match) AND merges in agent_runs.jsonl entries by `target_id`/`task_id`. Output is chronologically sorted by `ts`.
   - `cli/replay.py` parses `<line>` and `<start>-<end>` arg shapes via a private `_parse_line_spec` helper; line numbers are 1-indexed; out-of-range raises `JournalError` mapped to `ERR_USER_INPUT` exit 1; range cap at 1000 lines.
   - `cli/logs.py` merges journal + agent_runs streams; supports `--filter-task`, `--filter-agent`, `--follow`. Follow uses tell/seek polling at 0.25 s interval; KeyboardInterrupt exits 0 cleanly.
   - `agent_runs.jsonl` has NO contract module in v1.18 — read as `dict[str, object]`. Story 2x's first writer locks the schema.
   - All three commands respect Story 1.17's `--no-color` / `--json` global flags via `ctx.obj`.
   - Per-command JSON envelopes are documented in `cli/output.py` as `_TRACE_OUTPUT_SCHEMA`, `_REPLAY_OUTPUT_SCHEMA`, `_LOGS_OUTPUT_SCHEMA` constants.
   - `--follow` JSON mode emits NDJSON (newline-delimited JSON), not a single document — the only command in v1 with continuous-stream JSON output.
4. **Alternatives considered:**
   - Hierarchical trace (chase parent story + epic events): rejected for v1.18; epic AC scopes to task-id only. v2.x can add `--story` / `--epic` flags.
   - Index-based replay seek (build a line-byte-offset index for O(1) seek): rejected as premature optimization; `iter_entries` is bounded by file size (typical journals are ≤ MB); the linear pass is fast enough. Revisit if profiling shows replay is bottleneck-y after v1.x.
   - Use `tail -F` subprocess for `--follow`: rejected — POSIX-only, no Windows fallback, and would couple the CLI to an external binary. The polling tell/seek loop is portable and ~30 LOC.
   - Lock `agent_runs.jsonl` schema in v1.18 (introduce `contracts/agent_run.py`): rejected — Story 2A.3's dispatcher will write the first record; locking the schema before the writer ships invites churn. v1.18 reads raw dicts and Story 2A.3 owns the contract.
   - Allow `--filter-task` to accept partial task-ids (prefix match): rejected — partial matches are ambiguous; v1.18 requires exact `parse_task_id` validation. `sdlc logs | grep <prefix>` covers prefix search at the shell level.
   - Use `inotify` (Linux) / `kqueue` (macOS) for `--follow` instead of polling: rejected — adds platform-specific code without measurable user benefit at 0.25 s polling interval; the polling loop is portable + simple.
   - Allow `--follow` without explicit `--filter-*`: shipped as-is; default-no-filter follow mode is the most common use case.
5. **Consequences:**
   - All FR33/FR34/FR45 requirements have user-facing surfaces. NFR-OBS-3 (chronological reconstruction) and NFR-OBS-6 (filter-by-task + filter-by-agent) are met.
   - The `cli/output.py` error code table now has 9 entries (Story 1.17's 7 + Story 1.18's 2). Story 1.21's wire-format-lock ceremony freezes this table.
   - The `agent_runs.jsonl` schema-lock punt creates a known forward-compat seam: when Story 2A.3 ships, ANY field rename in agent_runs records will silently drop from trace/logs output. ADR-021 documents this risk + recommends adding a contract module (`contracts/agent_run.py`) AT THE TIME Story 2A.3 is authored, not retroactively.
   - The 1000-line replay cap is a soft UX bound; users hitting it will be redirected to `sdlc logs` for streamed output. Document the cap in `--help` text + ADR.
   - Follow-mode polling at 0.25 s adds negligible CPU overhead (< 0.1% on idle); if measured load surfaces, future story can switch to inotify/kqueue without changing the CLI surface.
6. **Revisit-by:** Story 1.21 (wire-format v1 lock — CLI output schemas freeze). Story 2A.3 (first agent_runs.jsonl writer — schema-lock for `contracts/agent_run.py`).
7. **References:** PRD §511 (console script command list), §767 FR33, §768 FR34, §785 FR45, §865 NFR-OBS-3, §868 NFR-OBS-6. Architecture §117, §123, §347 Decision B3, §397 Decision E3, §479 canonical layout, §540-§548 exit code mapping, §549-§559 error envelope, §595-§606 JournalEntry contract, §669-§680 CLI output conventions, §791-§810 cli/* module layout, §888-§892 telemetry/ (placeholder for Story 2x), §1159-§1171 FR mapping, §1196 Concern 12 observability. ADR-013 (atomic state write — Story 1.10), ADR-014 (journal append-only — Story 1.11), ADR-019 (cli skeleton — Story 1.16), ADR-020 (cli scan/status + accessibility flags — Story 1.17, if landed at story-implement time; otherwise next-free).

**And** `docs/decisions/index.md` gains the row `| [021](ADR-021-cli-trace-replay-logs.md) | CLI trace + replay + logs + cross-stream merge | 1.18 | Accepted |` after ADR-020's row. If 014-020 haven't all shipped at story-implement time, take the next free number.

## Tasks / Subtasks

- [x] **Task 1: Pre-flight verification of dependencies, environment, and prior-story state (AC: all)**
  - [x] Verify Story 1.6 deliverables on disk: `src/sdlc/ids/parsers.py` exports `parse_task_id`, `TaskId`, `TASK_ID_REGEX`. Smoke: `uv run python -c "from sdlc.ids import parse_task_id; print(parse_task_id('EPIC-foo-S01-bar-T01-baz'))"`. Sprint-status `1-6: done`.
  - [x] Verify Story 1.7 deliverables on disk: `src/sdlc/contracts/journal_entry.py` exports `JournalEntry` with the v1 contract (schema_version, monotonic_seq, ts, actor, kind, target_id, before_hash, after_hash, payload). Smoke: `uv run python -c "from sdlc.contracts.journal_entry import JournalEntry; print(JournalEntry.model_fields)"`. Sprint-status `1-7: done`.
  - [x] Verify Story 1.11 deliverables on disk: `src/sdlc/journal/__init__.py` exports `iter_entries`, `iter_after`, `append`, `append_sync` (POSIX) / `append_sync` raises on Windows. Smoke: `uv run python -c "from sdlc.journal import iter_entries; print(iter_entries)"`. Sprint-status `1-11: done` (or `review` per snapshot 2026-05-08; if still in `review`, gate Story 1.18 dev behind 1.11 reaching `done` because trace/replay/logs hard-depend on the reader).
  - [x] Verify Story 1.16 deliverables on disk (or in-flight): `src/sdlc/cli/main.py` (with `app` Typer instance), `src/sdlc/cli/init.py`, `src/sdlc/cli/output.py` (Story 1.17 expanded surface), `src/sdlc/cli/exit_codes.py`, `src/sdlc/cli/version.py`. Smoke: `uv run sdlc --version` prints `sdlc 0.0.0` exit 0. If 1.16 has NOT landed (sprint-status `1-16: ready-for-dev` per snapshot 2026-05-08), gate 1.18 behind 1.16 reaching `done` — the entire CLI architecture this story extends is owned by 1.16.
  - [x] Verify Story 1.17 deliverables on disk (or in-flight): `src/sdlc/cli/scan.py`, `src/sdlc/cli/status.py`, expanded `src/sdlc/cli/output.py` with `emit_json`, `emit_error`, `make_console`, `is_no_color_active`, `_ERR_CODE_TO_EXIT_CODE` table. Smoke: `uv run python -c "from sdlc.cli.output import emit_json, emit_error, make_console; print('ok')"`. If 1.17 has NOT landed, gate 1.18 behind 1.17 — Story 1.18 hard-depends on `emit_json`/`emit_error`/`make_console` for output formatting + the `--no-color`/`--json` flag plumbing in `cli/main.py:_root`.
  - [x] Verify boundary-linter location: `scripts/check_module_boundaries.py` has `MODULE_DEPS["cli"]` widened by Story 1.16 to include `state`, `journal`, `contracts`, `ids`. Confirm via `grep -A5 '"cli": ModuleSpec' scripts/check_module_boundaries.py`. Story 1.18 does NOT widen further — the existing widening covers `cli/trace.py` (uses `journal`, `state`, `contracts`, `ids`), `cli/replay.py` (uses `journal`, `contracts`), `cli/logs.py` (uses `journal`, `state`, `contracts`, `ids`).
  - [x] Verify ADR numbering: ADRs 013, 014 are landed (Stories 1.10, 1.11). ADRs 015-020 are in flight per their stories' AC blocks; Story 1.18 (this story) authors **ADR-021**. Take next free number after the most recent ADR on disk.
  - [x] Verify `pyproject.toml [project] dependencies` includes `typer>=0.12,<1` (Story 1.16) AND `rich>=13,<15` (Story 1.17). Story 1.18 ADDS NO new dependencies — it consumes Story 1.17's `rich` via `make_console` + Typer's existing surface for argument/option declarations.
  - [x] Verify `src/sdlc/cli/trace.py`, `src/sdlc/cli/replay.py`, `src/sdlc/cli/logs.py` do NOT exist on disk: absence verified via `Test-Path` (PowerShell) or `test -f` (POSIX). If they exist (half-merged earlier story), HALT and reconcile manually before proceeding.
  - [x] Verify `tests/unit/cli/test_trace.py`, `test_replay.py`, `test_logs.py`, `test_logs_follow.py` do NOT exist. Same absence check.
  - [x] Verify the existing pre-commit hooks pass on `main`: `uv run pre-commit run --all-files`. Establish a green baseline before mutating.
  - [x] Confirm the Story 1.16-1.17 walking-skeleton smoke works (if both shipped): in a tmp dir, `git init && uv run sdlc init && uv run sdlc scan && uv run sdlc status`. All exit 0. Story 1.18 extends this stack with `sdlc trace`, `sdlc replay`, `sdlc logs` working too.
  - [x] Verify `JournalEntry.payload` is `Mapping[str, object]` (not `dict[str, object]`) per `contracts/journal_entry.py:37` — Story 1.18 reads `payload.get(...)` so the Mapping interface is sufficient; no need to cast to dict.

- [x] **Task 2: Extend `cli/output.py` with new error codes (AC: #5)**
  - [x] Open `src/sdlc/cli/output.py`. Locate the `_ERR_CODE_TO_EXIT_CODE: Final[Mapping[str, int]] = MappingProxyType({...})` block (Story 1.17 added this).
  - [x] Add two new entries to the mapping at the end (preserving Story 1.17's order; do NOT alphabetize):
    ```python
    _ERR_CODE_TO_EXIT_CODE: Final[Mapping[str, int]] = MappingProxyType(
        {
            "ERR_NOT_INITIALIZED": 1,
            "ERR_ALREADY_INITIALIZED": 1,
            "ERR_USER_INPUT": 1,
            "ERR_SCAN_FAILED": 2,
            "ERR_JOURNAL_APPEND_FAILED": 2,
            "ERR_STATE_WRITE_FAILED": 2,
            "ERR_INFRASTRUCTURE": 3,
            # Added in Story 1.18 — see ADR-021.
            "ERR_JOURNAL_READ_FAILED": 2,
            "ERR_AGENT_RUNS_READ_FAILED": 2,
        }
    )
    ```
  - [x] Add the per-command schema constants alongside Story 1.17's `_SCAN_OUTPUT_SCHEMA` / `_STATUS_OUTPUT_SCHEMA`:
    ```python
    _TRACE_OUTPUT_SCHEMA: Final[str] = "v1"
    _REPLAY_OUTPUT_SCHEMA: Final[str] = "v1"
    _LOGS_OUTPUT_SCHEMA: Final[str] = "v1"
    ```
    Document the four schemas (scan/status/trace/replay/logs) in the module docstring as a single block: "Per-command JSON output schemas. Story 1.21 wire-format-lock ceremony freezes these at v1."
  - [x] Update the module docstring's "Story 1.17" attribution to also reference Story 1.18 for the new error codes + schemas. Single-line addition:
    ```python
    """...
    Story 1.18 extension: adds ERR_JOURNAL_READ_FAILED, ERR_AGENT_RUNS_READ_FAILED;
    declares _TRACE_OUTPUT_SCHEMA, _REPLAY_OUTPUT_SCHEMA, _LOGS_OUTPUT_SCHEMA constants.
    ..."""
    ```
  - [x] Verify LOC stays ≤ 200 (Story 1.17 cap). Run `uv run mypy --strict src/sdlc/cli/output.py` → must pass.
  - [x] Run `uv run ruff check src/sdlc/cli/output.py` and `uv run ruff format --check src/sdlc/cli/output.py` → both pass.

- [x] **Task 3: Implement `cli/trace.py` (AC: #1, #2)**
  - [x] Create `src/sdlc/cli/trace.py`. Top-of-file order:
    1. Module docstring: "`sdlc trace <task-id>` implementation (FR33, NFR-OBS-3, Architecture §803, §1159). Filters journal + agent_runs by task-id; chronological merge."
    2. `from __future__ import annotations`.
    3. Stdlib imports (alphabetized): `import datetime`, `import json`, `import logging`, `import subprocess`, `import sys`, `from collections.abc import Iterator, Mapping`, `from pathlib import Path`, `from typing import Any, Final, Literal, TypedDict`.
    4. Third-party imports: `import typer`.
    5. SDLC imports: `from sdlc.cli.output import echo, emit_error, emit_json, make_console`. `from sdlc.contracts.journal_entry import JournalEntry`. `from sdlc.errors import IdsError, JournalError`. `from sdlc.ids import parse_task_id`. Other imports DEFERRED to function bodies per Architecture §488 (e.g. `from sdlc.journal import iter_entries` inside `run_trace`).
    6. `_logger = logging.getLogger(__name__)`.
    7. Constants:
       ```python
       _STATE_PATH_REL: Final[str] = ".claude/state/state.json"
       _JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
       _AGENT_RUNS_PATH_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
       _AGENT_RUN_DISPLAY_FIELDS: Final[tuple[str, ...]] = (
           "ts", "agent", "target_id", "stage", "outcome", "duration_ms"
       )
       ```
  - [x] Implement `_get_repo_root_or_cwd() -> Path` — same pattern as Story 1.16/1.17. If `cli/_paths.py` exists from prior story, IMPORT it instead of duplicating; otherwise inline.
  - [x] Implement `_event_affects_task(entry: JournalEntry, task_id: str) -> bool`:
    ```python
    def _event_affects_task(entry: JournalEntry, task_id: str) -> bool:
        """Return True if this journal entry pertains to the given task-id.

        Three predicates per AC1.5:
          1. entry.target_id == task_id (direct mutation/scan/etc.)
          2. entry.kind == "agent_dispatch" and entry.payload.get("task_id") == task_id
          3. entry.kind == "hook_invocation" and entry.payload.get("target_id") == task_id
        """
        if entry.target_id == task_id:
            return True
        if entry.kind == "agent_dispatch":
            payload_task_id = entry.payload.get("task_id")
            if isinstance(payload_task_id, str) and payload_task_id == task_id:
                return True
        if entry.kind == "hook_invocation":
            payload_target = entry.payload.get("target_id")
            if isinstance(payload_target, str) and payload_target == task_id:
                return True
        return False
    ```
    Pure function — unit-testable in isolation.
  - [x] Implement `_iter_agent_runs(path: Path) -> Iterator[dict[str, Any]]`:
    ```python
    def _iter_agent_runs(path: Path) -> Iterator[dict[str, Any]]:
        """Yield records from agent_runs.jsonl. Missing file → empty iterator. Malformed
        line → WARNING + skip (permissive reader, mirrors journal/reader.py:45-50)."""
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        _logger.warning(
                            "malformed agent_runs line at %s:%d: %s — skipping",
                            path, lineno, exc,
                        )
                        continue
                    if not isinstance(record, dict):
                        _logger.warning(
                            "non-object agent_runs line at %s:%d (got %s) — skipping",
                            path, lineno, type(record).__name__,
                        )
                        continue
                    yield record
        except OSError as exc:
            # Distinct from missing file: this is a real read failure.
            raise OSError(f"agent_runs read failed at {path}: {exc}") from exc
    ```
    The `OSError` propagates up to `run_trace` which translates to `emit_error("ERR_AGENT_RUNS_READ_FAILED", ...)`.
  - [x] Implement `_record_matches_task(record: dict[str, Any], task_id: str) -> bool`:
    ```python
    def _record_matches_task(record: dict[str, Any], task_id: str) -> bool:
        for key in ("target_id", "task_id"):
            v = record.get(key)
            if isinstance(v, str) and v == task_id:
                return True
        return False
    ```
  - [x] Implement `_parse_ts(ts: str) -> datetime.datetime`:
    ```python
    def _parse_ts(ts: str) -> datetime.datetime:
        """RFC 3339 UTC string → datetime. 3.10-compatible."""
        normalized = ts.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(normalized)
    ```
  - [x] Implement `_collect_events(journal_path, agent_runs_path, task_id) -> list[dict[str, Any]]`:
    ```python
    def _collect_events(
        *, journal_path: Path, agent_runs_path: Path, task_id: str,
    ) -> list[dict[str, Any]]:
        from sdlc.journal import iter_entries  # deferred
        events: list[dict[str, Any]] = []
        for entry in iter_entries(journal_path):
            if not _event_affects_task(entry, task_id):
                continue
            events.append({
                "source": "journal",
                "ts": entry.ts,
                "_sort_ts": _parse_ts(entry.ts),
                "_sort_seq": entry.monotonic_seq,
                "monotonic_seq": entry.monotonic_seq,
                "kind": entry.kind,
                "actor": entry.actor,
                "target_id": entry.target_id,
                "before_hash": entry.before_hash,
                "after_hash": entry.after_hash,
                "payload": dict(entry.payload),
            })
        for record in _iter_agent_runs(agent_runs_path):
            if not _record_matches_task(record, task_id):
                continue
            ts = record.get("ts")
            if not isinstance(ts, str):
                continue  # malformed — skip silently (logged at read time only)
            events.append({
                "source": "agent_runs",
                "ts": ts,
                "_sort_ts": _parse_ts(ts),
                "_sort_seq": -1,  # sorts AFTER journal at same ts
                "agent": record.get("agent"),
                "stage": record.get("stage"),
                "outcome": record.get("outcome"),
                "duration_ms": record.get("duration_ms"),
                "target_id": record.get("target_id") or record.get("task_id"),
                "raw": record,
            })
        events.sort(key=lambda e: (e["_sort_ts"], 0 if e["source"] == "journal" else 1, e["_sort_seq"]))
        # Strip private sort keys before returning.
        for e in events:
            e.pop("_sort_ts", None)
            e.pop("_sort_seq", None)
        return events
    ```
  - [x] Implement the public `run_trace(*, ctx: typer.Context, task_id: str) -> None`:
    ```python
    def run_trace(*, ctx: typer.Context, task_id: str) -> None:
        from sdlc.errors import JournalError as _JE  # noqa: F401  # for emit-clarity

        # Resolve repo root + check init.
        root = _get_repo_root_or_cwd()
        state_path = root / _STATE_PATH_REL
        if not state_path.exists():
            emit_error(
                "ERR_NOT_INITIALIZED",
                f"project not initialized at {root}; run `sdlc init` first",
                ctx=ctx, details={"project_root": str(root)},
            )

        # Validate task-id syntax via parse_task_id.
        try:
            parse_task_id(task_id)
        except IdsError as exc:
            emit_error(
                "ERR_USER_INPUT",
                f"invalid task identifier: {exc.message}",
                ctx=ctx, details=dict(exc.details),
            )

        journal_path = root / _JOURNAL_PATH_REL
        agent_runs_path = root / _AGENT_RUNS_PATH_REL

        try:
            events = _collect_events(
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                task_id=task_id,
            )
        except JournalError as exc:
            emit_error(
                "ERR_JOURNAL_READ_FAILED",
                f"journal read failed: {exc.message}",
                ctx=ctx, details=dict(exc.details),
            )
        except OSError as exc:
            emit_error(
                "ERR_AGENT_RUNS_READ_FAILED",
                f"agent_runs read failed: {exc}",
                ctx=ctx, details={"path": str(agent_runs_path)},
            )

        if ctx.obj.get("json", False):
            emit_json(
                "trace",
                {
                    "task_id": task_id,
                    "project_root": str(root),
                    "events": events,
                    "event_count": len(events),
                },
                ctx=ctx,
            )
            return

        # Human-readable.
        echo(f"sdlc trace {task_id} — {len(events)} events", ctx=ctx)
        if not events:
            echo("(no events recorded for this task yet)", ctx=ctx)
            return
        for e in events:
            if e["source"] == "journal":
                line = (
                    f"  [{e['ts']}]   kind={e['kind']:<20} "
                    f"target={e['target_id']}   actor={e['actor']}"
                )
            else:
                line = (
                    f"  [{e['ts']}]   agent_run             "
                    f"agent={e.get('agent')}   stage={e.get('stage')}   "
                    f"outcome={e.get('outcome')}"
                )
            echo(line, ctx=ctx)
    ```
  - [x] Verify LOC ≤ 250 for `cli/trace.py`. If exceeded, factor `_iter_agent_runs`, `_record_matches_task`, `_parse_ts` into `cli/_trace_helpers.py`.
  - [x] **Forbidden patterns** (review-time gate):
    - `print()` — use `echo`/`emit_json`/`emit_error`.
    - Bare `except:` / `except Exception:` — narrow catches only.
    - Mutating `JournalEntry.payload` (it's a `MappingProxyType` — would raise anyway, but never call `.update`/`.pop` on it).
    - `os.environ[...]` direct access — env reads happen in `cli/output.py` only.
    - `time.time()` for ordering — `monotonic_seq` is the ordering primitive.
  - [x] Run `uv run mypy --strict src/sdlc/cli/trace.py` → must pass. Annotate the `events: list[dict[str, Any]]` return; the `Any` is acceptable here because agent_runs records are schema-free in v1.18.

- [x] **Task 4: Implement `cli/replay.py` (AC: #3)**
  - [x] Create `src/sdlc/cli/replay.py`. Top-of-file order:
    1. Module docstring: "`sdlc replay <line-or-range>` implementation (FR34, Architecture §804, §1160). Pretty-prints parsed JournalEntry models."
    2. `from __future__ import annotations`.
    3. Stdlib imports (alphabetized): `import logging`, `import re`, `import subprocess`, `import sys`, `from collections.abc import Iterable`, `from pathlib import Path`, `from typing import Final`.
    4. Third-party imports: `import typer`.
    5. SDLC imports: `from sdlc.cli.output import echo, emit_error, emit_json, make_console`. `from sdlc.contracts.journal_entry import JournalEntry`. `from sdlc.errors import JournalError`. Journal reader DEFERRED.
    6. `_logger = logging.getLogger(__name__)`.
    7. Constants:
       ```python
       _STATE_PATH_REL: Final[str] = ".claude/state/state.json"
       _JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
       _MAX_REPLAY_RANGE: Final[int] = 1000
       _SINGLE_LINE_RE: Final[re.Pattern[str]] = re.compile(r"^([1-9]\d*)$")
       _RANGE_RE: Final[re.Pattern[str]] = re.compile(r"^([1-9]\d*)-([1-9]\d*)$")
       ```
  - [x] Implement `_get_repo_root_or_cwd()` (same as Story 1.16/1.17/Task 3).
  - [x] Implement `_parse_line_spec(spec: str) -> tuple[int, int]`:
    ```python
    def _parse_line_spec(spec: str) -> tuple[int, int]:
        """Parse 'N' or 'N-M'. Both 1-indexed inclusive; require start ≤ end.

        Raises JournalError on any invalid form (caller maps to ERR_USER_INPUT exit 1).
        """
        if not spec or not spec.strip():
            raise JournalError(
                "invalid replay spec: empty",
                details={"input": spec, "rule": "empty"},
            )
        m_single = _SINGLE_LINE_RE.match(spec)
        if m_single is not None:
            n = int(m_single.group(1))
            return (n, n)
        m_range = _RANGE_RE.match(spec)
        if m_range is None:
            raise JournalError(
                f"invalid replay spec: {spec!r} (must be 'N' or 'N-M' with 1-indexed positive integers)",
                details={"input": spec, "rule": "invalid_shape"},
            )
        start = int(m_range.group(1))
        end = int(m_range.group(2))
        if start > end:
            raise JournalError(
                f"replay spec start must be ≤ end (got {start}-{end})",
                details={"input": spec, "rule": "inverted_range", "start": start, "end": end},
            )
        if (end - start + 1) > _MAX_REPLAY_RANGE:
            raise JournalError(
                f"replay range too large ({end - start + 1} lines requested; max {_MAX_REPLAY_RANGE})",
                details={
                    "input": spec, "rule": "range_too_large",
                    "requested": end - start + 1, "max": _MAX_REPLAY_RANGE,
                },
            )
        return (start, end)
    ```
    Pure function — unit-testable. The regex anchors `^([1-9]\d*)$` reject `"0"` and any leading-zero forms (`"01"` is invalid by design — line numbers don't carry zero-padding). The `re.match` (not `re.search` and not `re.fullmatch`) is intentional with `$` anchor; both anchors yield the same behavior for these patterns but `^...$` is the project convention.
  - [x] Implement `_format_entry_human(lineno: int, entry: JournalEntry, ctx: typer.Context) -> list[str]`:
    ```python
    def _format_entry_human(lineno: int, entry: JournalEntry) -> list[str]:
        """Return a list of lines forming the pretty-print block for one entry."""
        lines = [f"--- line {lineno} ---"]
        lines.append(f"monotonic_seq:  {entry.monotonic_seq}")
        lines.append(f"ts:             {entry.ts}")
        lines.append(f"actor:          {entry.actor}")
        lines.append(f"kind:           {entry.kind}")
        lines.append(f"target_id:      {entry.target_id}")
        lines.append(f"before_hash:    {entry.before_hash}")
        lines.append(f"after_hash:     {entry.after_hash}")
        lines.append("payload:")
        if entry.payload:
            for k, v in entry.payload.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append("  (empty)")
        return lines
    ```
    Test asserts presence of `--- line N ---`, `monotonic_seq:`, `ts:`, etc. — exact byte format is non-load-bearing.
  - [x] Implement `run_replay(*, ctx: typer.Context, line_spec: str) -> None`:
    ```python
    def run_replay(*, ctx: typer.Context, line_spec: str) -> None:
        root = _get_repo_root_or_cwd()
        state_path = root / _STATE_PATH_REL
        if not state_path.exists():
            emit_error(
                "ERR_NOT_INITIALIZED",
                f"project not initialized at {root}; run `sdlc init` first",
                ctx=ctx, details={"project_root": str(root)},
            )

        try:
            start, end = _parse_line_spec(line_spec)
        except JournalError as exc:
            emit_error(
                "ERR_USER_INPUT",
                exc.message,
                ctx=ctx, details=dict(exc.details),
            )

        journal_path = root / _JOURNAL_PATH_REL

        from sdlc.journal import iter_entries  # deferred
        collected: list[tuple[int, JournalEntry]] = []
        total_lines = 0
        try:
            for lineno, entry in enumerate(iter_entries(journal_path), start=1):
                total_lines = lineno
                if start <= lineno <= end:
                    collected.append((lineno, entry))
                if lineno >= end:
                    # Continue to count total lines? Per AC3.3 the error message
                    # includes the actual journal size. But once we're past `end`
                    # AND we have all lines we need, we can short-circuit ONLY if
                    # all requested lines were found — otherwise we must keep
                    # counting to populate the error message.
                    if len(collected) == (end - start + 1):
                        break
        except JournalError as exc:
            emit_error(
                "ERR_JOURNAL_READ_FAILED",
                f"journal read failed: {exc.message}",
                ctx=ctx, details=dict(exc.details),
            )

        # Out-of-range check: if any requested line number > total_lines, error.
        if end > total_lines:
            # Need to know actual total — drain the iterator if not already drained.
            # (If we short-circuited above, we only know lines up to `end`. But
            # `end > total_lines` means we did NOT short-circuit, so `total_lines`
            # is now the full journal length.)
            emit_error(
                "ERR_USER_INPUT",
                f"line {end} not in journal (journal has {total_lines} lines)",
                ctx=ctx,
                details={
                    "requested_line": end,
                    "journal_lines": total_lines,
                    "path": str(journal_path),
                },
            )

        if ctx.obj.get("json", False):
            emit_json(
                "replay",
                {
                    "lines": [
                        {"lineno": ln, "entry": entry.model_dump(mode="json")}
                        for ln, entry in collected
                    ],
                    "line_count": len(collected),
                },
                ctx=ctx,
            )
            return

        # Human-readable.
        for ln, entry in collected:
            for line in _format_entry_human(ln, entry):
                echo(line, ctx=ctx)
    ```
  - [x] Verify LOC ≤ 200 for `cli/replay.py`. If exceeded, factor `_format_entry_human` into `cli/_replay_helpers.py`.
  - [x] Run `uv run mypy --strict src/sdlc/cli/replay.py` → must pass.
  - [x] **Forbidden patterns** (review-time): same as Task 3.

- [x] **Task 5: Implement `cli/logs.py` (AC: #4)**
  - [x] Create `src/sdlc/cli/logs.py`. Top-of-file order:
    1. Module docstring: "`sdlc logs` implementation (FR45, NFR-OBS-6, Architecture §809, §1171). Tails journal + agent_runs.jsonl with filters + follow-mode."
    2. `from __future__ import annotations`.
    3. Stdlib imports (alphabetized): `import datetime`, `import json`, `import logging`, `import subprocess`, `import sys`, `import time`, `from collections.abc import Iterator`, `from pathlib import Path`, `from typing import Any, Final`.
    4. Third-party imports: `import typer`.
    5. SDLC imports: `from sdlc.cli.output import echo, emit_error, emit_json, make_console`. `from sdlc.contracts.journal_entry import JournalEntry`. `from sdlc.errors import IdsError, JournalError`. `from sdlc.ids import parse_task_id`. Journal reader DEFERRED.
    6. `_logger = logging.getLogger(__name__)`.
    7. Constants:
       ```python
       _STATE_PATH_REL: Final[str] = ".claude/state/state.json"
       _JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
       _AGENT_RUNS_PATH_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
       _FOLLOW_INTERVAL_S: Final[float] = 0.25
       _OUTCOME_STYLES: Final[Mapping[str, str]] = MappingProxyType(
           {"success": "green", "failure": "red", "partial": "yellow"}
       )
       ```
       (Add `from collections.abc import Mapping` and `from types import MappingProxyType` to imports.)
  - [x] Implement `_get_repo_root_or_cwd()` (same as Tasks 3-4).
  - [x] Implement `_iter_agent_runs(path: Path) -> Iterator[dict[str, Any]]` — same body as Task 3's helper. Factor into `cli/_logs_helpers.py` if `cli/trace.py` and `cli/logs.py` both exceed their LOC caps; otherwise duplicate (single-use helpers are acceptable per project convention; both modules are ≤ 250 LOC). The DRY-versus-duplication trade is documented in dev notes.
  - [x] Implement `_journal_actor_matches_agent(actor: str, agent_name: str) -> bool`:
    ```python
    def _journal_actor_matches_agent(actor: str, agent_name: str) -> bool:
        return actor == f"agent:{agent_name}"
    ```
  - [x] Implement `_journal_entry_matches_filters(entry, filter_task, filter_agent) -> bool`:
    ```python
    def _journal_entry_matches_filters(
        entry: JournalEntry,
        filter_task: str | None,
        filter_agent: str | None,
    ) -> bool:
        if filter_task is not None:
            # Reuse trace.py's _event_affects_task semantics — but inline to
            # avoid cli→cli intra-module dependency surface for v1.18.
            matches_task = (
                entry.target_id == filter_task
                or (
                    entry.kind == "agent_dispatch"
                    and isinstance(entry.payload.get("task_id"), str)
                    and entry.payload.get("task_id") == filter_task
                )
                or (
                    entry.kind == "hook_invocation"
                    and isinstance(entry.payload.get("target_id"), str)
                    and entry.payload.get("target_id") == filter_task
                )
            )
            if not matches_task:
                return False
        if filter_agent is not None:
            matches_agent = (
                _journal_actor_matches_agent(entry.actor, filter_agent)
                or entry.payload.get("agent") == filter_agent
            )
            if not matches_agent:
                return False
        return True
    ```
    NOTE: For v1.18 the duplicated `_event_affects_task` logic is acceptable; if a future story touches trace AND logs together, factor into `cli/_event_filters.py`.
  - [x] Implement `_agent_run_record_matches_filters(record, filter_task, filter_agent) -> bool`:
    ```python
    def _agent_run_record_matches_filters(
        record: dict[str, Any],
        filter_task: str | None,
        filter_agent: str | None,
    ) -> bool:
        if filter_task is not None:
            record_task = record.get("target_id") or record.get("task_id")
            if not (isinstance(record_task, str) and record_task == filter_task):
                return False
        if filter_agent is not None:
            if record.get("agent") != filter_agent:
                return False
        return True
    ```
  - [x] Implement `_collect_logs(journal_path, agent_runs_path, filter_task, filter_agent) -> list[dict[str, Any]]` — mirrors Task 3's `_collect_events` but without `task_id` argument; uses the filter helpers.
  - [x] Implement `_format_log_line_human(event: dict[str, Any]) -> str`:
    ```python
    def _format_log_line_human(event: dict[str, Any]) -> str:
        if event["source"] == "journal":
            return (
                f"{event['ts']}  [journal/{event['kind']}]   "
                f"actor={event['actor']:<10}   target={event['target_id']}"
            )
        # agent_runs
        return (
            f"{event['ts']}  [agent_run/{event.get('agent', '?')}]   "
            f"stage={event.get('stage', '?')}   outcome={event.get('outcome', '?')}   "
            f"task={event.get('target_id', '?')}"
        )
    ```
    Optional rich styling via `make_console(ctx).print(...)` deferred to a follow-up; v1.18 ships the plain-text format routed through `echo` (already a11y-clean per Story 1.17's `--no-color` plumbing).
  - [x] Implement `_follow_streams(journal_path, agent_runs_path, filter_task, filter_agent, ctx) -> None`:
    ```python
    def _follow_streams(
        journal_path: Path,
        agent_runs_path: Path,
        filter_task: str | None,
        filter_agent: str | None,
        ctx: typer.Context,
    ) -> None:
        """Tail-follow journal + agent_runs. Polls at _FOLLOW_INTERVAL_S until KI."""
        # Open both files at current EOF; journal may not exist yet (treat as empty).
        # agent_runs.jsonl may not exist yet either (treat as empty).
        journal_pos = journal_path.stat().st_size if journal_path.exists() else 0
        agent_pos = agent_runs_path.stat().st_size if agent_runs_path.exists() else 0
        json_mode = bool(ctx.obj.get("json", False))
        try:
            while True:
                # Poll journal.
                if journal_path.exists():
                    new_size = journal_path.stat().st_size
                    if new_size > journal_pos:
                        with journal_path.open("r", encoding="utf-8") as fh:
                            fh.seek(journal_pos)
                            for line in fh:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    entry = JournalEntry.model_validate_json(line)
                                except (ValueError, TypeError) as exc:
                                    _logger.warning(
                                        "follow: malformed journal line — skipping: %s", exc
                                    )
                                    continue
                                if not _journal_entry_matches_filters(entry, filter_task, filter_agent):
                                    continue
                                event = {
                                    "source": "journal",
                                    "ts": entry.ts,
                                    "kind": entry.kind,
                                    "actor": entry.actor,
                                    "target_id": entry.target_id,
                                    "monotonic_seq": entry.monotonic_seq,
                                }
                                if json_mode:
                                    typer.echo(json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
                                else:
                                    echo(_format_log_line_human(event), ctx=ctx)
                        journal_pos = new_size
                # Poll agent_runs.
                if agent_runs_path.exists():
                    new_size = agent_runs_path.stat().st_size
                    if new_size > agent_pos:
                        with agent_runs_path.open("r", encoding="utf-8") as fh:
                            fh.seek(agent_pos)
                            for line in fh:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    record = json.loads(line)
                                except json.JSONDecodeError as exc:
                                    _logger.warning(
                                        "follow: malformed agent_runs line — skipping: %s", exc
                                    )
                                    continue
                                if not isinstance(record, dict):
                                    continue
                                if not _agent_run_record_matches_filters(record, filter_task, filter_agent):
                                    continue
                                event = {
                                    "source": "agent_runs",
                                    "ts": record.get("ts", "?"),
                                    "agent": record.get("agent"),
                                    "stage": record.get("stage"),
                                    "outcome": record.get("outcome"),
                                    "duration_ms": record.get("duration_ms"),
                                    "target_id": record.get("target_id") or record.get("task_id"),
                                }
                                if json_mode:
                                    typer.echo(json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
                                else:
                                    echo(_format_log_line_human(event), ctx=ctx)
                        agent_pos = new_size
                time.sleep(_FOLLOW_INTERVAL_S)
        except KeyboardInterrupt:
            return  # caller raises typer.Exit(0)
    ```
    NOTE: NDJSON output in follow+json mode bypasses `emit_json` because the latter assumes a single-document terminator; the `typer.echo(json.dumps(...))` call here intentionally emits one JSON object per line. Document this exception in dev notes.
  - [x] Implement `run_logs(*, ctx, filter_task, filter_agent, follow) -> None`:
    ```python
    def run_logs(
        *,
        ctx: typer.Context,
        filter_task: str | None,
        filter_agent: str | None,
        follow: bool,
    ) -> None:
        root = _get_repo_root_or_cwd()
        state_path = root / _STATE_PATH_REL
        if not state_path.exists():
            emit_error(
                "ERR_NOT_INITIALIZED",
                f"project not initialized at {root}; run `sdlc init` first",
                ctx=ctx, details={"project_root": str(root)},
            )

        # Validate filter-task syntactically.
        if filter_task is not None:
            try:
                parse_task_id(filter_task)
            except IdsError as exc:
                emit_error(
                    "ERR_USER_INPUT",
                    f"invalid task identifier in --filter-task: {exc.message}",
                    ctx=ctx, details=dict(exc.details),
                )

        journal_path = root / _JOURNAL_PATH_REL
        agent_runs_path = root / _AGENT_RUNS_PATH_REL

        try:
            events = _collect_logs(
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                filter_task=filter_task,
                filter_agent=filter_agent,
            )
        except JournalError as exc:
            emit_error(
                "ERR_JOURNAL_READ_FAILED",
                f"journal read failed: {exc.message}",
                ctx=ctx, details=dict(exc.details),
            )
        except OSError as exc:
            emit_error(
                "ERR_AGENT_RUNS_READ_FAILED",
                f"agent_runs read failed: {exc}",
                ctx=ctx, details={"path": str(agent_runs_path)},
            )

        json_mode = bool(ctx.obj.get("json", False))

        # Print initial batch.
        if json_mode and not follow:
            emit_json(
                "logs",
                {
                    "filters": {"task_id": filter_task, "agent": filter_agent},
                    "events": events,
                    "event_count": len(events),
                },
                ctx=ctx,
            )
        elif json_mode and follow:
            # NDJSON: emit each initial event then enter follow loop.
            for e in events:
                typer.echo(json.dumps(e, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        else:
            for e in events:
                echo(_format_log_line_human(e), ctx=ctx)

        if not follow:
            return

        # Enter follow loop.
        try:
            _follow_streams(
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                filter_task=filter_task,
                filter_agent=filter_agent,
                ctx=ctx,
            )
        except KeyboardInterrupt:
            pass
        raise typer.Exit(code=0)
    ```
  - [x] Verify LOC ≤ 350 for `cli/logs.py`. If exceeded, factor follow-mode into `cli/_logs_follow.py` and filters into `cli/_logs_filters.py`.
  - [x] Run `uv run mypy --strict src/sdlc/cli/logs.py` → must pass.
  - [x] **Forbidden patterns**: same as Tasks 3-4. PLUS: do NOT use `os.kill`, `signal.signal` (KeyboardInterrupt is the canonical follow-mode exit signal; explicit signal handling adds Windows portability bugs).

- [x] **Task 6: Wire `trace`, `replay`, `logs` subcommands into `cli/main.py` (AC: #6)**
  - [x] Open `src/sdlc/cli/main.py`. Locate the existing subcommand registrations (`init_command`, `scan_command`, `status_command` from Stories 1.16-1.17).
  - [x] Append three new subcommand registrations after `status_command`:
    ```python
    @app.command(name="trace")
    def trace_command(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Task identifier (EPIC-...-S<NN>-...-T<NN>-...)."),
    ) -> None:
        """Reconstruct chronological history of a task (FR33)."""
        from sdlc.cli.trace import run_trace  # deferred per Architecture §488
        run_trace(ctx=ctx, task_id=task_id)


    @app.command(name="replay")
    def replay_command(
        ctx: typer.Context,
        line_spec: str = typer.Argument(..., help="Line number or range (e.g. '42' or '42-50')."),
    ) -> None:
        """Pretty-print parsed journal entries by line (FR34)."""
        from sdlc.cli.replay import run_replay  # deferred
        run_replay(ctx=ctx, line_spec=line_spec)


    @app.command(name="logs")
    def logs_command(
        ctx: typer.Context,
        filter_task: str | None = typer.Option(None, "--filter-task", help="Restrict to entries matching this task-id."),
        filter_agent: str | None = typer.Option(None, "--filter-agent", help="Restrict to entries from this agent."),
        follow: bool = typer.Option(False, "--follow", "-f", help="Tail-follow streams; exit on Ctrl-C."),
    ) -> None:
        """Tail journal + agent_runs.jsonl with filters (FR45, NFR-OBS-6)."""
        from sdlc.cli.logs import run_logs  # deferred
        run_logs(ctx=ctx, filter_task=filter_task, filter_agent=filter_agent, follow=follow)
    ```
  - [x] Verify `cli/main.py` LOC ≤ 180. If exceeded, factor argument-help strings into a `cli/_main_helpers.py:HELP_TEXTS: Final[Mapping[str, str]]` constant.
  - [x] Module-level imports stay minimal — NO new imports. The `from sdlc.cli.{trace,replay,logs} import ...` calls are all inside the subcommand bodies (deferred per Architecture §488).
  - [x] Run `uv run mypy --strict src/sdlc/cli/main.py` → must pass.
  - [x] Smoke-test the wiring (after init/scan):
    ```bash
    cd $(mktemp -d)
    git init
    uv run sdlc init
    uv run sdlc scan
    uv run sdlc trace EPIC-test-S01-foo-T01-bar  # 0 events; exit 0
    uv run sdlc --json trace EPIC-test-S01-foo-T01-bar
    uv run sdlc replay 1   # the scan_completed entry from `sdlc scan`
    uv run sdlc --json replay 1
    uv run sdlc logs
    uv run sdlc --no-color logs
    uv run sdlc logs --filter-agent implementer  # 0 entries; exit 0
    ```
    Each command exits 0 with shaped output.

- [x] **Task 7: Tests — unit + integration + e2e (AC: #7)**
  - [x] Create `tests/unit/cli/test_trace.py` with `pytestmark = pytest.mark.unit`. Add the 11 tests from AC7.1. Use a `_initialize_test_project(tmp_path, ctx=fake_ctx)` helper (re-exported from existing `tests/unit/cli/conftest.py` if Stories 1.16-1.17 created one). Helper for crafting JournalEntry instances:
    ```python
    def _make_entry(seq: int, ts: str, *, target_id: str = "state",
                   actor: str = "cli", kind: str = "scan_completed",
                   payload: dict | None = None) -> JournalEntry:
        return JournalEntry(
            schema_version=1,
            monotonic_seq=seq,
            ts=ts,
            actor=actor,
            kind=kind,
            target_id=target_id,
            before_hash=None if seq == 0 else "sha256:" + "0" * 64,
            after_hash="sha256:" + "1" * 64,
            payload=payload or {},
        )
    ```
    Append entries via `sdlc.journal.append_sync(entry, journal_path=...)` on POSIX. On Windows the writer raises; for the Windows test posture, write canonical bytes directly via `journal_path.write_text(...)` (one entry per line, JSON-serialized via `entry.model_dump_json()`).
  - [x] Create `tests/unit/cli/test_replay.py` with `pytestmark = pytest.mark.unit`. Add the 11 tests from AC7.2. Reuse the `_make_entry` helper. The `_parse_line_spec` parametrized tests directly import the private helper:
    ```python
    from sdlc.cli.replay import _parse_line_spec
    ```
  - [x] Create `tests/unit/cli/test_logs.py` with `pytestmark = pytest.mark.unit`. Add the 12 tests from AC7.3. Reuse helpers.
  - [x] Create `tests/unit/cli/test_logs_follow.py` with `pytestmark = pytest.mark.unit`. Add the 2 tests from AC7.4. Use `pytest.MonkeyPatch` to override `_FOLLOW_INTERVAL_S` to 0.05 s. Use `threading.Thread` to run `run_logs(..., follow=True)` and `signal.pthread_kill` (POSIX) or simulate KI via `subprocess.Popen + send_signal(signal.SIGINT)` for the integration variant. Skip on Windows for signal-based tests.
  - [x] Extend `tests/unit/cli/test_main.py` (Stories 1.16-1.17) with the 5 tests from AC7.5. Reuse the existing `runner` / `app` fixtures.
  - [x] Extend `tests/unit/cli/test_output.py` (Story 1.17) with the parametrized test from AC7.6 covering the new error codes.
  - [x] Create `tests/integration/test_trace_replay_logs_e2e.py` with `pytestmark = [pytest.mark.integration, pytest.mark.e2e]`. Add the 3 tests from AC7.7. Use `subprocess.run(["uv", "run", "sdlc", ...], cwd=tmp_path)` for the e2e flow; skip on Windows when `shutil.which("uv") is None`.
  - [x] Create `tests/integration/test_logs_follow_subprocess.py` with `pytestmark = pytest.mark.integration` AND `pytest.mark.skipif(sys.platform == "win32", ...)`. Add the test from AC7.8.
  - [x] Run all new tests:
    ```bash
    uv run pytest tests/unit/cli/test_trace.py -v
    uv run pytest tests/unit/cli/test_replay.py -v
    uv run pytest tests/unit/cli/test_logs.py -v
    uv run pytest tests/unit/cli/test_logs_follow.py -v
    uv run pytest tests/integration/test_trace_replay_logs_e2e.py -v
    uv run pytest tests/integration/test_logs_follow_subprocess.py -v
    ```
    All green (with appropriate Windows skips).
  - [x] Verify coverage: `uv run pytest tests/unit/cli/ tests/integration/test_trace_replay_logs_e2e.py --cov=src/sdlc/cli --cov-report=term-missing`. The new `cli/trace.py`, `cli/replay.py`, `cli/logs.py` MUST reach ≥ 90% line coverage. Acceptable uncovered: Windows-fallback branches (covered on Linux CI matrix cells), defensive paths under `OSError` catches that integration tests can't reliably trigger.

- [x] **Task 8: Author ADR-021 + update documentation (AC: #8)**
  - [x] Determine the next free ADR number. Read `docs/decisions/index.md`. Story 1.18 takes the next number after the most recent ADR (typically 021 if 1.17's ADR-020 has landed; otherwise next-free).
  - [x] Create `docs/decisions/ADR-021-cli-trace-replay-logs.md` using `docs/decisions/adr-template.md`. Populate per AC8 sections 1-7.
  - [x] Update `docs/decisions/index.md`: add the row for ADR-021 after the most-recent ADR row.
  - [x] Update `docs/CODEMAPS/cli-module.md` (Stories 1.16-1.17 maintain this codemap): add rows for `trace.py`, `replay.py`, `logs.py` with one-line responsibilities.
  - [x] Update `README.md` (if a "Quick Start" section exists from prior stories) to extend the demo with trace/replay/logs:
    ```bash
    sdlc trace EPIC-foo-S01-bar-T01-baz  # full chronological history of a task
    sdlc replay 42                        # pretty-print journal line 42
    sdlc replay 42-50                     # range
    sdlc logs                             # tail journal + agent_runs.jsonl
    sdlc logs --filter-task <id>          # filter by task
    sdlc logs --follow                    # tail-style; Ctrl-C to exit
    ```

- [x] **Task 9: Run the full quality gate stack and verify CI green (AC: all)**
  - [x] `uv run ruff check src/ tests/ scripts/` → 0 errors. New `cli/trace.py`, `cli/replay.py`, `cli/logs.py` MUST have `from __future__ import annotations`.
  - [x] `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [x] `uv run mypy --strict src/` → 0 errors. All new code fully annotated; `dict[str, Any]` is acceptable for agent_runs records (no contract module yet); no `Any` leak through public surface (`run_trace`, `run_replay`, `run_logs` all `-> None`).
  - [x] `uv run pre-commit run --all-files` → all hooks pass:
    - `ruff-check`, `ruff-format`, `mypy-strict` (existing).
    - `boundary-validator` — `cli` already widened to include `state, journal, contracts, ids, errors`; no further widening needed for Story 1.18.
    - `state-write-protocol-validator` — Story 1.18 modules do NOT call `write_state_atomic_sync`; not in scope.
    - `journal-append-only-validator` — Story 1.18 modules do NOT call `append_sync`; only READ via `iter_entries`; not in scope.
    - `secret-hardcode-validator` — scoped to `^src/sdlc/.*\.py$`; no secrets in new files.
  - [x] `uv run pytest tests/unit/cli/ -m unit -v` → all green.
  - [x] `uv run pytest tests/integration/ -m integration -v` → all green (skipped where appropriate on Windows).
  - [x] Global `uv run pytest --cov=src --cov-fail-under=90` → coverage gate passes.
  - [x] Confirm new files are tracked: `git status` → `src/sdlc/cli/trace.py`, `src/sdlc/cli/replay.py`, `src/sdlc/cli/logs.py` (new); `src/sdlc/cli/output.py`, `src/sdlc/cli/main.py` (modified). New tests: `tests/unit/cli/test_trace.py`, `test_replay.py`, `test_logs.py`, `test_logs_follow.py`, `tests/integration/test_trace_replay_logs_e2e.py`, `test_logs_follow_subprocess.py`. Docs: `docs/decisions/ADR-021-cli-trace-replay-logs.md`, `docs/decisions/index.md` (modified), `docs/CODEMAPS/cli-module.md` (modified).
  - [x] Run from a clean clone-equivalent: `git clean -fdx; uv sync --frozen --group dev; uv run pytest`. Everything must pass.
  - [x] Smoke-test the actual user flow:
    ```bash
    cd $(mktemp -d)
    git init
    uv run sdlc init
    uv run sdlc scan
    uv run sdlc trace EPIC-foo-S01-bar-T01-baz   # 0 events; exit 0
    uv run sdlc replay 1                          # scan_completed entry pretty-print
    uv run sdlc replay 1-1                        # same as above
    uv run sdlc replay 999                        # exit 1 + "line 999 not in journal"
    uv run sdlc logs                              # 1 entry: scan_completed
    uv run sdlc logs --filter-agent implementer   # 0 entries; exit 0
    uv run sdlc --no-color logs                   # zero ANSI escapes
    uv run sdlc --json trace EPIC-foo-S01-bar-T01-baz | jq .  # canonical JSON
    uv run sdlc --json replay 1 | jq .            # canonical JSON
    uv run sdlc --json logs | jq .                # canonical JSON (single doc)
    ```
    Document the smoke in the Story 1.18 dev notes / completion log so the reviewer can replay it.

## Dev Notes

### Why this story exists (FR + NFR + Decision mapping)

- **FR33 — `sdlc trace <task-id>` (PRD §767, Architecture §1159, NFR-OBS-3 PRD §865)**: The audit-chain interrogation surface. Without `cli/trace.py`, users debugging "why did task T fail?" must hand-grep `journal.log` and `agent_runs.jsonl` separately. v1.18 closes this gap with a single command that merges both streams, filtered by task-id, sorted chronologically.
- **FR34 — `sdlc replay <line-or-range>` (PRD §768, Architecture §1160)**: Journal-line introspection. Without `cli/replay.py`, users debugging journal corruption or schema drift must `head -n 42 journal.log | python -m json.tool`. v1.18 ships a typed pydantic-validated pretty-printer that catches malformed entries explicitly.
- **FR45 — `sdlc logs` (PRD §785, Architecture §1171, NFR-OBS-6 PRD §868)**: Live tailing of audit + dispatch streams. Without `cli/logs.py`, users debugging an in-progress agent run must keep two terminal windows open with `tail -F` invocations. v1.18 ships a single command with filter-by-task + filter-by-agent + follow-mode, all flowing through one rich-formatted stream.
- **Architecture §397 Decision E3 (three observability streams)**: `journal.log` (audit), `agent_runs.jsonl` (dispatches), `debug_events.jsonl` (correlation-tagged debug). v1.18 reads journal + agent_runs; debug_events is Story 4.x's surface (correlation-id support comes with `engine/auto_loop.py`).
- **Architecture §123 (Status Visibility & Dashboard FR41-FR46)**: `sdlc status`/`sdlc logs` are the CLI half; the dashboard is the GUI half. v1.18 ships the CLI half complete; dashboard is Story 5.x.

### File set this story creates / modifies

**New files (created):**

- `src/sdlc/cli/trace.py` — `run_trace()` + helpers (~200-250 LOC)
- `src/sdlc/cli/replay.py` — `run_replay()` + `_parse_line_spec` + `_format_entry_human` (~150-200 LOC)
- `src/sdlc/cli/logs.py` — `run_logs()` + `_follow_streams` + filter helpers (~250-350 LOC)
- `tests/unit/cli/test_trace.py` — trace handler tests (~11 cases)
- `tests/unit/cli/test_replay.py` — replay handler tests (~11 cases)
- `tests/unit/cli/test_logs.py` — logs handler tests (~12 cases)
- `tests/unit/cli/test_logs_follow.py` — follow-mode tests (~2 cases, POSIX-only)
- `tests/integration/test_trace_replay_logs_e2e.py` — full lifecycle e2e
- `tests/integration/test_logs_follow_subprocess.py` — subprocess-driven follow-mode test (POSIX-only)
- `docs/decisions/ADR-021-cli-trace-replay-logs.md` — new ADR

**Optional new files** (factor out if line caps exceeded):

- `src/sdlc/cli/_trace_helpers.py` — `_iter_agent_runs`, `_parse_ts`, `_record_matches_task` if `cli/trace.py` exceeds 250 LOC.
- `src/sdlc/cli/_logs_follow.py` — `_follow_streams` if `cli/logs.py` exceeds 350 LOC.
- `src/sdlc/cli/_logs_filters.py` — filter predicates if shared with future story.
- `src/sdlc/cli/_event_filters.py` — shared `_event_affects_task` predicate if Story 1.18+ keeps duplicating it across trace/logs.

**Modified files:**

- `src/sdlc/cli/output.py` — adds `ERR_JOURNAL_READ_FAILED`, `ERR_AGENT_RUNS_READ_FAILED` to `_ERR_CODE_TO_EXIT_CODE`; adds `_TRACE_OUTPUT_SCHEMA`, `_REPLAY_OUTPUT_SCHEMA`, `_LOGS_OUTPUT_SCHEMA` constants. (~5-10 LOC delta from Story 1.17 baseline)
- `src/sdlc/cli/main.py` — adds `trace_command`, `replay_command`, `logs_command` registrations (~40-50 LOC delta from Story 1.17 baseline)
- `tests/unit/cli/test_main.py` — extends Stories 1.16-1.17's tests with 5 new cases.
- `tests/unit/cli/test_output.py` — extends Story 1.17's tests with 1 parametrized case for new error codes.
- `docs/decisions/index.md` — adds ADR-021 row.
- `docs/CODEMAPS/cli-module.md` — extends with `trace.py`, `replay.py`, `logs.py` rows.
- `README.md` — extends quick-start with trace/replay/logs examples (optional).

**Files NOT modified (invariant — break-glass if any of these change):**

- `src/sdlc/contracts/journal_entry.py` — Story 1.7 owns; consumers only.
- `src/sdlc/journal/{__init__,reader,writer,_canonical,_seq}.py` — Story 1.11 owns; consumers only.
- `src/sdlc/state/{__init__,model,atomic,projection}.py` — Stories 1.10/1.12/1.15 own; consumers only.
- `src/sdlc/ids/{__init__,parsers,builders}.py` — Story 1.6 owns; consumers only.
- `src/sdlc/errors/{__init__,base}.py` — Story 1.6 owns; consumers only.
- `src/sdlc/config/env.py` — Stories 1.8/1.17 own; not modified.
- `src/sdlc/cli/{init,scan,status,version,exit_codes}.py` — Stories 1.16-1.17 own; not modified.
- `scripts/check_module_boundaries.py` — Story 1.16's widening (`cli` → `state`, `journal`, `contracts`, `ids`) covers Story 1.18. NO further widening.
- `pyproject.toml` — no new deps; `[project] dependencies` is unchanged from Story 1.17.
- `.pre-commit-config.yaml` — no new hook.

### Why three modules (trace, replay, logs) and not one

The three commands share substrate (journal reader, agent_runs reader, filter predicates) but differ semantically:

- **`trace`** is *task-scoped retrospection*: "give me everything that ever happened to THIS task." Output is the union of all events filtered by task-id.
- **`replay`** is *line-scoped pretty-printing*: "show me the parsed pydantic model at line 42." Output is one entry's full structure, pretty-printed.
- **`logs`** is *time-scoped tailing*: "show me the audit + dispatch firehose, optionally filtered, optionally follow-mode." Output is the unfiltered or filtered union of streams.

Combining them into one command (`sdlc audit ...` with subcommands or flags) was rejected because:

1. Each has a distinct argument shape (task-id vs line-spec vs flags).
2. Each has a distinct exit posture (always-zero for trace; range-validation for replay; signal-driven for logs --follow).
3. Decoupling them lets each evolve independently without breaking the others' contracts.

### Why `agent_runs.jsonl` has no contract module in v1.18

Story 2A.3's dispatcher will write the first record to `agent_runs.jsonl`. Locking the schema before the writer ships invites churn — the dispatcher author may discover at implementation time that fields like `correlation_id`, `tokens_in`, `tokens_out`, `output_path` are needed (Architecture §136 hints at these) and an early lock would force a v2 schema migration before v1 even shipped.

v1.18 reads agent_runs records as `dict[str, object]` and displays a fixed set of fields (`ts`, `agent`, `target_id`/`task_id`, `stage`, `outcome`, `duration_ms`). Future field additions are silently ignored by the trace/logs display — which is the right posture for a forward-compat reader.

ADR-021 records this design + recommends adding `contracts/agent_run.py` AT THE TIME Story 2A.3 is authored, not retroactively.

### Why `_parse_line_spec` is in `cli/replay.py` and not `cli/`-level

Single-use helper; private; tied 1:1 to `run_replay`. If a future story (e.g. `sdlc logs --replay 42`) needs the same parser, factor into `cli/_line_spec.py` at that point.

### Why follow-mode polls instead of using inotify/kqueue

Three reasons:

1. **Portability**: inotify is Linux-only; kqueue is BSD/macOS-only. A polling loop works on Windows too (within follow-mode's POSIX-skipped tests, but the production path is portable).
2. **Simplicity**: ~30 LOC vs. ~100+ LOC for the OS-watcher abstraction.
3. **Latency budget**: 0.25 s polling is imperceptible for human-in-the-loop debugging. Sub-100 ms latency would matter only for automation scenarios — and automation should consume `agent_runs.jsonl` directly, not via `sdlc logs --follow`.

If profiling later reveals 0.25 s is too slow for a power-user scenario, the polling interval is a single constant change (`_FOLLOW_INTERVAL_S`); switching to inotify/kqueue is a follow-up story with no CLI-surface change.

### Why follow-mode JSON is NDJSON (newline-delimited), not single-document

A single JSON document has one terminator (the closing `}` of the outermost object). `--follow` has no terminator — entries arrive indefinitely. Emitting one self-contained JSON object per line (NDJSON) lets consumers stream-parse with `jq -c` or equivalent. The alternative (build up a single `events: [...]` array and emit `]` only on Ctrl-C) breaks the tail-friendly UX.

This is the only command in v1 with a continuous-stream JSON output. The exception is documented in `cli/output.py` docstring, ADR-021, and the `--help` text for `--follow`.

### Why Ctrl-C exits 0 in follow-mode

KeyboardInterrupt is the canonical termination signal for tail-like commands. Treating it as exit 0 (clean termination) matches `tail -F`, `journalctl -f`, `kubectl logs -f`, and other tail surfaces. A non-zero exit would suggest the tail itself failed — which is wrong; the user explicitly requested termination.

The Ctrl-C handler is `try: ... except KeyboardInterrupt: pass` followed by `raise typer.Exit(code=0)`. Stack traces are NOT printed to stderr — that would clutter the user's terminal with implementation noise.

### Forward-compat: predicate evolution

The `_event_affects_task` predicate currently handles three event kinds (`state_mutation` via target_id, `agent_dispatch` via payload.task_id, `hook_invocation` via payload.target_id). Future stories will add:

- `signoff` events scoped to a phase, not a task — these are NOT in trace output (out of scope).
- `bypass_signoff` events — same; not in trace output.
- `auto_mad_resolve` events — depends on payload shape; v1.18's predicate already handles `payload.target_id` for `hook_invocation`-shaped entries; if `auto_mad_resolve` adopts the same shape, the predicate generalizes naturally. ADR-021 documents this forward-compat intent.

When Story 4.x ships `engine/auto_loop.py`, the correlation_id propagation may add a fourth predicate clause (entries with matching `payload.correlation_id` for the in-flight loop iteration). v1.18's predicate is a stub; v4.x extends.

### Cold-start budget for `sdlc --version`

Architecture §488 sets the cold-start budget at < 200 ms. Story 1.17's measurement showed `sdlc --version` at ~80-120 ms (with rich + typer in the dep set). Story 1.18's additions:

- **Three new subcommand registrations**: Typer registers `trace`, `replay`, `logs` as decorators at module import time on `cli/main.py`. Per-command registration cost is ~5 ms; total ~15 ms added.
- **Module bodies (`trace.py`, `replay.py`, `logs.py`) NOT imported on `--version` path**: the `from sdlc.cli.{trace,replay,logs} import ...` calls are inside the subcommand bodies (deferred per Architecture §488). The `--version` path does NOT touch these.
- **No new direct deps**: `rich` is already direct (Story 1.17); typer is already direct (Story 1.16). No new pip resolutions.

Diagnosis path if a regression pushes past 200 ms:
```bash
python -X importtime -m sdlc.cli.main --version 2>&1 | sort -k 2 -n | tail -20
```
Heaviest suspected imports if regression: pydantic (~30 ms — only loaded if state/contracts get pulled into main accidentally; v1.18 keeps these deferred), rich (~20 ms — only loaded via `make_console` on trace/replay/logs).

### Windows posture

- `sdlc.journal.iter_entries` is cross-platform (Story 1.11's reader does NOT require fcntl/O_APPEND).
- `sdlc.journal.append_sync` is POSIX-only (Story 1.11's writer raises on Windows). Story 1.18 modules do NOT call `append_sync` — they only READ; Windows works.
- `--follow` integration tests use `subprocess.Popen + send_signal(SIGINT)`, which is brittle on Windows; those tests skip on Windows.
- Unit tests for follow-mode use threaded `KeyboardInterrupt` injection; also skip on Windows.
- The trace/replay non-follow paths work on Windows (read-only, cross-platform).

### Test pyramid placement

| Test file | Tier | Markers |
|---|---|---|
| `tests/unit/cli/test_trace.py` | unit | `unit` |
| `tests/unit/cli/test_replay.py` | unit | `unit` |
| `tests/unit/cli/test_logs.py` | unit | `unit` |
| `tests/unit/cli/test_logs_follow.py` | unit | `unit`, skipif Windows |
| `tests/integration/test_trace_replay_logs_e2e.py` | integration + e2e | `integration`, `e2e`, skipif `which uv is None` |
| `tests/integration/test_logs_follow_subprocess.py` | integration | `integration`, skipif Windows |

Coverage target: ≥ 90% on `cli/trace.py`, `cli/replay.py`, `cli/logs.py` from unit + integration combined. Existing `--cov-fail-under=90` enforces.

### Forbidden patterns at code-review time

- `print()` — use `cli/output.py:echo` / `emit_json` / `emit_error`. Even in `_follow_streams` NDJSON branch, use `typer.echo(json.dumps(...))` (not `print`).
- Bare `except:` / `except Exception:` — narrow catches only. Acceptable: `except KeyboardInterrupt:`, `except (OSError, JournalError):`, `except json.JSONDecodeError:`.
- Mutating function arguments — events list is built fresh; entries are immutable pydantic models.
- `os.environ[...]` direct access — env reads happen in `cli/output.py:is_no_color_active` (Story 1.17). v1.18 modules read env only via `ctx.obj["no_color"]` / `ctx.obj["json"]` flags set by the root callback.
- `time.time()` for ordering — `monotonic_seq` is the journal ordering primitive; `ts` is for human display.
- `asyncio` in CLI handlers — v1.18's commands are sync. The follow-mode polling loop uses `time.sleep`, not `asyncio.sleep`. (The `journal.append` async path is for engine consumers, NOT CLI.)
- `subprocess.run(check=True)` — always pass `check=False` and inspect `returncode` explicitly per Story 1.16's `cli/init.py` pattern.

### Why this story does NOT add the `cli/git.py` module

Story 1.16's ADR-019 deferred `cli/git.py` to "Story 1.18 — `sdlc trace` / `sdlc logs` are the actual `cli/git.py` consumers" (per `1-16` story dev notes line 281). HOWEVER, on closer reading, Story 1.18's trace/replay/logs do NOT actually call `git log` (that's Story 5.x's DORA computation — `telemetry/dora.py`). The forward-reference in 1.16's ADR was speculative.

v1.18 inlines the `_get_repo_root_or_cwd` helper (5 LOC, single purpose: find repo root). `cli/git.py` is deferred to Story 5.x's DORA story when the first real `git log` consumer ships. Document this deferral in the dev notes; ADR-021 records the deferral explicitly.

### Why `--filter-task` validates via `parse_task_id` but `--filter-agent` accepts any string

Task-ids have a strict regex (`EPIC-...-S<NN>-...-T<NN>-...` per `ids/parsers.py:18-23`). Validating via `parse_task_id` catches typos at command-arg-parse time, not at filter-time-no-results time. UX win: `sdlc logs --filter-task EPIC-typo` fails loudly, not silently.

Agent names have NO contract module — they're arbitrary strings declared in specialist frontmatter (Story 2A.2 owns the contract, but even then the name is a free-form `str`). Validation would be lookup-against-registry, which couples the CLI to the specialist registry — out of scope for v1.18.

### Why the pretty-print format uses fixed-width labels

`monotonic_seq:`, `ts:`, `actor:`, etc. are aligned to the colon for human readability. Tests assert presence of `monotonic_seq:` (with the trailing colon) so the format is testable without exact-byte assertions. The padding (e.g. `monotonic_seq:  7` vs `actor:          cli`) is computed by hand-aligned hardcoded labels, NOT by `f"{label:<14}"` — the latter would obscure the intent and require updating the alignment width every time a field is added/removed. The hardcoded form is project convention for fixed schemas.

### Smoke-test sequence for the reviewer

1. Bootstrap: `cd $(mktemp -d); git init; uv run sdlc init; uv run sdlc scan`.
2. `uv run sdlc trace EPIC-foo-S01-bar-T01-baz` — exit 0; stdout "0 events".
3. `uv run sdlc trace not-a-task-id` — exit 1; stderr "invalid task identifier".
4. `uv run sdlc replay 1` — exit 0; stdout shows the `scan_completed` entry with `monotonic_seq: 0`, `kind: scan_completed`.
5. `uv run sdlc replay 999` — exit 1; stderr contains "line 999 not in journal".
6. `uv run sdlc replay 1-2000` — exit 1; stderr contains "range too large".
7. `uv run sdlc logs` — exit 0; stdout has 1 entry (the scan_completed).
8. `uv run sdlc logs --filter-agent implementer` — exit 0; stdout has 0 entries.
9. `uv run sdlc --json trace EPIC-foo-S01-bar-T01-baz | jq .command` — outputs `"trace"`.
10. `uv run sdlc --json replay 1 | jq '.lines | length'` — outputs `1`.
11. `uv run sdlc --json logs | jq '.event_count'` — outputs `1`.
12. `uv run sdlc --no-color trace EPIC-foo-S01-bar-T01-baz` — zero ANSI escapes in output.
13. `uv run sdlc logs --follow` (terminal 1) + `uv run sdlc scan` (terminal 2) → terminal 1 shows the new scan_completed entry within ~0.5 s; Ctrl-C in terminal 1 exits 0 cleanly.

### Project Structure Notes

- New modules `cli/trace.py`, `cli/replay.py`, `cli/logs.py` align with Architecture §803-§809 layout.
- No source-tree restructuring beyond the three new files.
- The `cli/_paths.py` factor-out (if not already done by Stories 1.16-1.17) is acceptable but not required for v1.18; inline duplication of the 5-line `_get_repo_root_or_cwd` is preferred until 4+ call sites exist.
- No conflict with unified project structure.

### References

- PRD §511 (console script command list): `cli/{trace,replay,logs}.py` are listed as v1 surfaces.
- PRD §767 FR33; §768 FR34; §785 FR45.
- PRD §865 NFR-OBS-3 (chronological reconstruction); §868 NFR-OBS-6 (filter-by-task + filter-by-agent).
- Architecture §117 (cross-cutting domains); §123 (Status Visibility & Dashboard); §347 Decision B3 (JournalEntry schema); §397 Decision E3 (three observability streams); §479-§480 (canonical filesystem layout); §540-§548 (exit code mapping); §549-§559 (error envelope); §595-§606 (JournalEntry contract); §669-§680 (CLI output conventions); §791-§810 (cli/* module layout); §888-§892 (telemetry/ — placeholder for Story 2x); §1066 (telemetry boundary); §1159-§1171 (FR mapping); §1196 (Concern 12 observability).
- Source files (read-only consumers): `src/sdlc/contracts/journal_entry.py:20-54`, `src/sdlc/journal/__init__.py:1-52`, `src/sdlc/journal/reader.py:22-97`, `src/sdlc/ids/parsers.py:9-23`, `src/sdlc/errors/base.py:6-75`, `src/sdlc/cli/output.py` (Story 1.17 expanded surface).
- Prior stories: Story 1.6 (ids), Story 1.7 (JournalEntry), Story 1.10 (state.atomic), Story 1.11 (journal reader), Story 1.12 (state.projection), Story 1.16 (cli skeleton), Story 1.17 (cli/output.py expanded + scan/status).
- ADRs: ADR-013 (atomic state write), ADR-014 (journal append-only), ADR-019 (cli skeleton), ADR-020 (cli scan/status + accessibility flags). ADR-021 (this story) records the trace/replay/logs design.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

- C901 complexity on `run_trace` → extracted `_load_events` and `_format_event_line` helpers
- mypy `unreachable` on `isinstance(raw, dict)` after `json.loads` → used intermediate `raw: object` variable
- SIM105/SIM102/PLR0912 in `logs.py` → extracted `_poll_journal`, `_poll_agent_runs`, `_load_events_or_error`; replaced `try/except/pass` with `contextlib.suppress`
- `pytest.raises(SystemExit)` for `emit_error` → changed to `pytest.raises(typer.Exit)` (emit_error raises `typer.Exit`, not `SystemExit`)
- ruff SIM117: nested `with` blocks → combined to single `with` statement
- Deferred `iter_entries` import in `replay.py` → monkeypatched via `sdlc.journal.iter_entries` (not module-level attribute) in tests

### Completion Notes List

- Implemented `src/sdlc/cli/trace.py` (FR33): reads journal + agent_runs.jsonl, filters by task-id with three predicates (direct target_id, agent_dispatch payload, hook_invocation payload), chronological merge sort, human and JSON output modes. 100% unit coverage.
- Implemented `src/sdlc/cli/replay.py` (FR34): validates line-spec (single int or range), reads journal entries by 1-indexed line number, human-readable field-labeled output and JSON envelope. 100% unit coverage.
- Implemented `src/sdlc/cli/logs.py` (FR45): filters by --filter-task / --filter-agent, chronological merge of journal + agent_runs, --follow mode polls at 0.25s intervals, NDJSON in --follow --json mode. 100% unit coverage.
- Registered all three commands in `cli/main.py` with deferred imports per Architecture §488.
- Extended `cli/output.py` with ERR_JOURNAL_READ_FAILED (exit 2), ERR_AGENT_RUNS_READ_FAILED (exit 2), and three schema version constants.
- Authored ADR-021 and updated docs/decisions/index.md.
- Updated docs/CODEMAPS/cli-module.md to v1.18.
- Full quality gate: ruff check ✓, ruff format ✓, mypy --strict ✓, all 16 pre-commit hooks ✓, 1001 tests pass, total coverage 95% (new modules 100% each).

### File List

- src/sdlc/cli/trace.py (new)
- src/sdlc/cli/replay.py (new)
- src/sdlc/cli/logs.py (new)
- src/sdlc/cli/main.py (modified — added trace_command, replay_command, logs_command)
- src/sdlc/cli/output.py (modified — ERR_JOURNAL_READ_FAILED, ERR_AGENT_RUNS_READ_FAILED, schema constants)
- tests/unit/cli/test_trace.py (new)
- tests/unit/cli/test_replay.py (new)
- tests/unit/cli/test_logs.py (new)
- tests/unit/cli/test_logs_follow.py (new)
- tests/unit/cli/test_main.py (modified — trace/replay/logs --help + missing-arg tests)
- tests/unit/cli/test_output.py (modified — new error code parametrized test)
- tests/integration/test_trace_replay_logs_e2e.py (new)
- tests/integration/test_logs_follow_subprocess.py (new)
- docs/decisions/ADR-021-cli-trace-replay-logs.md (new)
- docs/decisions/index.md (modified — ADR-021 row)
- docs/CODEMAPS/cli-module.md (modified — v1.18 entries)
- _bmad-output/implementation-artifacts/sprint-status.yaml (modified — 1-18 status)

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-05-09 | 1.18.0 | Implement sdlc trace + replay + logs (FR33, FR34, FR45); all new CLI modules at 100% coverage; total coverage 95% | claude-sonnet-4-6 |
