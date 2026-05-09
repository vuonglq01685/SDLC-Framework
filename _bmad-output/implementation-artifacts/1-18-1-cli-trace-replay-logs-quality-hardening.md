# Story 1.18.1: CLI `sdlc trace` / `replay` / `logs` — Quality Hardening

Status: ready-for-dev

<!--
Status trail:
  2026-05-09 (creation): backlog → ready-for-dev (carved out from Story 1.18 code-review action items)

Origin: this story exists ONLY because the 2026-05-09 adversarial code-review of Story 1.18
surfaced quality-debt that does not block the FR33/34/45 user surface (which Story 1.18 fully
shipped) but should not ship unfixed long-term:
  - 30 chunk-B test patches (flake vectors + uncovered behavior changes from chunk-A patches)
  - D2 deferred: --follow rotation/truncation/inode-replacement handling
  - D3 deferred: rich styling for human-readable trace/replay/logs output

The full per-item detail is recorded in Story 1.18's "Review Findings — Chunk B (tests)" section
and "Decisions resolved (2026-05-09)" + "Deferred" subsections. This story file lists the work
items by reference and adds acceptance criteria for the hardening pass.
-->

## Story

As a maintainer of the `sdlc` CLI,
I want to close the test-quality gaps and behavior-deferrals surfaced in the 2026-05-09
adversarial review of Story 1.18,
so that flake vectors are removed, all source-patch behavior changes are regression-protected,
and the rich-styling + log-rotation deferrals from v1.18 are delivered.

This is a quality-hardening story — no new user-visible features beyond rich styling. FR33,
FR34, FR45 user surfaces are already shipped by Story 1.18.

## Acceptance Criteria

**AC1 — Flake vectors removed from follow-mode tests**

Given the v1.18 follow-mode test suite uses `ctypes.PyThreadState_SetAsyncExc` to inject
`KeyboardInterrupt` (B-PC1) and fixed `time.sleep(0.15..0.6)` budgets to gate output assertions
(B-PC2),

When AC1 is met,

Then:
- `tests/unit/cli/test_logs_follow.py` no longer calls `ctypes.pythonapi.PyThreadState_SetAsyncExc`.
  Replace with either (a) `os.kill(os.getpid(), signal.SIGINT)` from the main thread, or
  (b) a stop-event / sentinel the SUT honors.
- All `time.sleep(0.15..0.6)` budgets in `test_logs_follow.py` and
  `tests/integration/test_logs_follow_subprocess.py` replaced with explicit synchronization
  (event/queue handshake, polled assertion with deadline, or sentinel monkeypatch on
  `_follow_streams`).
- `pytest.mark.skipif(sys.platform == "win32")` removed from follow-mode tests once the flake
  vectors are gone (Windows must regain coverage).

**AC2 — All chunk-A source patches have regression-protecting tests**

For each of the 9 chunk-A patches with no test coverage today (see Story 1.18 Review Findings
— Chunk B for source-of-truth list, items B-P3 through B-P16), add at least one test:

- B-P3 (P7): empty `--filter-agent` → ERR_USER_INPUT exit 1
- B-P4 (P3): naive + aware ts mix sorts chronologically without TypeError
- B-P5 (P2): malformed `ts` warning + skip (no exception)
- B-P6 (P15): NDJSON live-mode lines under `--follow --json` carry `obj["command"] == "logs"`
  with same schema as historical events
- B-P12 (P8): replay against missing journal emits "journal log not found at <path>" with
  `details.exists == False`
- B-P13 (P9): trace human row for an `agent_run` includes `target_id=...` AND `duration_ms=...`
  substrings
- B-P14 (P11): replay payload with nested dict/list values renders as JSON, not Python repr
- B-P15 (P5): subprocess `sdlc logs --follow | head -1` exits 0, stderr free of Traceback
- B-P16 (P6): monkeypatch `Path.open` on agent_runs to raise `FileNotFoundError` → empty iterator
- B-P17: `_TRACE_OUTPUT_SCHEMA == "v1"`, `_REPLAY_OUTPUT_SCHEMA == "v1"`, `_LOGS_OUTPUT_SCHEMA == "v1"`
- B-P25 (P4): follow-mode race window — entry appended between historical-collect and follow-start
  is emitted exactly once

**AC3 — Test quality cleanup**

- B-P7 rewrite: `test_logs_emit_event_json_mode_follow_ndjson` (test_logs_coverage.py) — current
  monkeypatches `_follow_streams` to no-op and asserts on the pre-follow flush; either rename to
  reflect what it tests, or exercise the real follow path.
- B-P8: `test_replay_journal_error_exits_with_error` — tighten `exit_code in (1, 2)` to `== 2`.
- B-P9: replace `result.output / result.stderr or ""` stream-confused assertions with
  `mix_stderr=False` + envelope-code assertion.
- B-P10: replace 5 hand-rolled `try: orig=...; finally: ...=orig` patterns in `test_logs_poll.py`
  with `monkeypatch.setattr(...)`.
- B-P11: extract `EXIT_USER_ERROR=1` / `EXIT_SYSTEM_ERROR=2` constants (or import from
  `sdlc.cli.output`) and replace bare `== 1` / `== 2` exit-code assertions throughout.
- B-P18: replace brittle prose-string assertions (`"1 events"`, `"--- line 1 ---"`,
  `stdout.count("[journal/")`) with envelope-key assertions where the contract is explicit.
  Reserve at most one snapshot test per command for prose.
- B-P19: move duplicated `_make_ctx` / `_make_entry` / `_bootstrap_project` / `_append_entry`
  helpers from 6+ test files to `tests/unit/cli/conftest.py` (or `tests/_helpers/journal.py`).
- B-P20: add 1 byte-equality test on canonical JSON output (`assert stdout_bytes == expected_sorted_bytes`).
- B-P21: replace `time.monotonic()` budget `< 2.0` in `test_logs_no_follow_returns_after_streams_exhausted`
  with sentinel monkeypatch on `_follow_streams`.
- B-P22: convert `_uv_sdlc` e2e calls to in-process `CliRunner`; reserve subprocess only for
  SIGINT / broken-pipe.
- B-P23: rewrite `test_no_color_flag_strips_ansi_*` to drive a path that WOULD produce color
  (multi-event + outcome styling) instead of an empty-stream tautology.
- B-P24: add `replay 1-1000` (exact-at-cap) parametrize case alongside the existing `1-1001`.
- B-P26: tighten `test_replay_empty_journal` and `test_replay_out_of_range_single` to assert
  the verbatim `"line N not in journal"` substring (AC3.3 spec mandate).
- B-P27: tighten `test_trace_empty_journal_exits_zero` to assert `"(no events recorded for this task yet)"`
  sentinel line (AC1.10).
- B-P28: extend e2e parametrize to include `replay 1-1` (range form), `replay 999` (out-of-range
  exit-1), `logs --filter-agent <name>` smoke commands.
- B-P29: replace `__import__("typer.testing", fromlist=["CliRunner"]).CliRunner()` reflection in
  `test_logs.py:270` and `test_replay.py:1260` with a normal import.
- B-P30: add JSON-mode envelope assertion for `--filter-task <invalid>` path (envelope shape +
  `error.code == "ERR_USER_INPUT"`).

**AC4 — D2: `--follow` rotation/truncation/inode-replacement handling**

Given a long-running `sdlc logs --follow` invocation,

When the journal or agent_runs file is rotated (renamed + new file at same path), truncated to
0 bytes, or replaced (new inode at same path),

Then:
- `_poll_journal` and `_poll_agent_runs` track `(inode, size)` via `os.stat` instead of size
  alone.
- On inode change, `journal_pos` (or `agent_pos`) resets to 0 and emits a `_logger.warning`
  noting the rotation.
- On truncation (size shrinks below the tracked position), reset to 0 and emit warning.
- Tests cover both scenarios under `tests/unit/cli/test_logs_follow.py` (or a new
  `test_logs_follow_rotation.py`).
- ADR-021 "Deferred to v1.18.1+" section is updated: D2 now ships; remove the "v1.18 does NOT
  detect rotation" caveat and the `logrotate` warning.

**AC5 — D3: Rich styling for human-readable trace / replay / logs output**

Given a user invokes `sdlc trace` / `sdlc replay` / `sdlc logs` without `--no-color`,

When AC5 is met,

Then:
- All three commands route human-readable output through `make_console(ctx)` from
  `sdlc.cli.output` (currently they use plain `echo()` only).
- `_OUTCOME_STYLES: Final[Mapping[str, str]] = MappingProxyType({"success": "green",
  "failure": "red", "partial": "yellow"})` is defined in `sdlc/cli/logs.py` per spec line 859-862.
- Trace + replay: bold kind name, dim hashes, rule-styled `--- line N ---` separators (replay).
- Logs: dim timestamp, bold `[stream/kind]`, outcome-colored stage/outcome cells.
- `--no-color` and `NO_COLOR=` env var paths still emit plain text (regression test).
- ADR-021 "Deferred to v1.18.1+" section is updated: D3 now ships; remove the "v1.18 ships
  plain-text" caveat.

**AC6 — Coverage + verification gates**

Given the patches and tests added by AC1-AC5,

Then:
- `uv run pytest tests/unit/cli/ tests/integration/test_trace_replay_logs_*` passes.
- New CLI module coverage stays at ≥ 95% line (Story 1.18 baseline).
- `uv run ruff check src/` passes.
- `uv run mypy --strict src/` passes.
- All boundary-validator hooks pass (LOC caps, module boundaries, secret literals).
- Story 1.18's "Review Findings — Chunk B" patch list shows all items checked `[x]`.
- Story 1.18's "Deferred" subsection shows D2 and D3 marked as resolved (move from defer →
  done with link to this story's commit).

## Tasks / Subtasks

- [ ] Task 1: AC1 — Replace `ctypes.PyThreadState_SetAsyncExc` usage in `test_logs_follow.py`
      with signal-based or sentinel-based stop mechanism. Remove all `time.sleep(0.15..0.6)`
      gating; use synchronization primitives. Remove `pytest.mark.skipif(win32)`. Verify on a
      Windows CI run.
- [ ] Task 2: AC2 — Add the 11 missing tests for chunk-A patches (B-P3 through B-P17 + B-P25).
      Cross-check against Story 1.18 Review Findings — Chunk B for exact assertions.
- [ ] Task 3: AC3 — Apply the 16 test-quality cleanup items (B-P7 through B-P30 minus the
      AC2 items). Bulk of work is in `test_logs_poll.py` and `test_logs_coverage.py`.
- [ ] Task 4: AC4 — Implement `(inode, size)` tracking in `_poll_journal` / `_poll_agent_runs`.
      Add tests. Update ADR-021.
- [ ] Task 5: AC5 — Wire `make_console(ctx)` + `_OUTCOME_STYLES` in trace.py / replay.py /
      logs.py. Add tests for both rich + plain-text paths. Update ADR-021.
- [ ] Task 6: AC6 — Verify all gates green; flip Story 1.18's chunk-B/D2/D3 items to resolved.

## Dev Notes

### Why this story exists separately from Story 1.18

Story 1.18 shipped the FR33 / FR34 / FR45 user surfaces (CLI commands `sdlc trace`,
`sdlc replay`, `sdlc logs`). The features themselves are complete and tested at the happy-path
level. However, the 2026-05-09 adversarial code-review surfaced:

1. **Test-quality debt** — 30 patches' worth of flake vectors, untested-behavior-change gaps,
   and brittle assertions. None block the user surface; all should be addressed before the next
   substantive change to these modules to avoid CI flakes and regression risk.
2. **Two deferred features** — D2 (`--follow` rotation handling) and D3 (rich styling) were
   intentionally scoped out of v1.18 to keep the story bounded. Both are now tracked here.

Carving the quality-debt into 1.18.1 keeps Story 1.18's scope honest (delivered FR33/34/45 +
basic correctness) while ensuring the debt is not lost.

### Cross-references

- Source story: `_bmad-output/implementation-artifacts/1-18-cli-sdlc-trace-replay-logs.md`
  - "Review Findings — Chunk A (source)" — already resolved (15 patches applied in commit `626d87e`)
  - "Review Findings — Chunk B (tests)" — items consumed by this story's AC2 + AC3
  - "Review Findings — Chunk C (docs)" — already resolved (22 patches applied in commit `d4944d2`)
  - "Decisions resolved" → D2 / D3 → consumed by this story's AC4 + AC5
- ADR: `docs/decisions/ADR-021-cli-trace-replay-logs.md` — "Deferred to v1.18.1+" section
- Deferred-work ledger: `_bmad-output/implementation-artifacts/deferred-work.md`

### Out of scope

- E1 (schema-version emission on the wire) — explicitly deferred to **Story 1.21** wire-format-lock,
  not this story.
- Chunk-C deferred items — owned by future spec-hygiene / docs-hardening passes, not this story.

## File List

(populated by Dev Agent during execution)

## Change Log

| Date       | Author        | Change |
|------------|---------------|--------|
| 2026-05-09 | code-review   | Created from Story 1.18 chunk-B + D2/D3 carve-out |
