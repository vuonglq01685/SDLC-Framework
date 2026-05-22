# Story 2B.1: ClaudeAIRuntime Implementation (Subprocess Management + Edge Cases)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer wiring real Claude Code into the AIRuntime ABC,
I want `runtime/claude.py` implementing `ClaudeAIRuntime` via `subprocess.run(["claude", ...])` with explicit handling of subprocess-died-mid-stream, stdout buffering, malformed JSON, and timeout,
so that the abstraction leaks Winston flagged are caught at implementation time, not in production (FR29).

## Acceptance Criteria

> **Source ACs:** `_bmad-output/planning-artifacts/epics.md:1454-1483` (the 4 subprocess AC groups → AC1–AC4 below).
> **AC5–AC6 are story-scoped per `docs/sprints/epic-2b-dag.md` §5 worktree note ("implements ADR-029 `mock: true` envelope + 4 collateral divergence fixes inside its own scope") + §7 Risk row + prep-sprint C8 (ADR-029 is a design-only doc; implementation lands here).** Omitting them leaves the system in the divergent state ADR-029 §4 documents — the dev agent owns end-to-end correctness, not just the literal epic text.
>
> **DAG position:** First story of **Layer 1**, Epic 2B. On the critical path `2B.1 → 2B.3 → 2B.10 → 2B.11`. **2B.3 and 2B.6 both depend on this story.** A slip here starves the entire downstream DAG — time-box to ~1.5 days (DAG §7 Risk row 1).
> **No new wire-format contract** is introduced; `AgentResult` gains one field — this is a contract-shape edit and **pairs with a snapshot regeneration ceremony** (ADR-024 mutation taxonomy + `tests/contract_snapshots/v1/`). See AC5/D-decision.
> **New `JournalEntry.kind` values:** none required by this story (real dispatch reuses existing `agent_dispatched` / `artifact_written` kinds; if a new kind is emitted, add an ADR-028 §3 table row in the same PR).

### AC1 — `ClaudeAIRuntime.dispatch` happy path (subprocess spawn + parse)

**Given** Claude Code installed and on PATH
**When** I instantiate `ClaudeAIRuntime()` and call `await runtime.dispatch(prompt, context)`
**Then** a subprocess is spawned via `subprocess.run(["claude", ...])` with the prompt sent via **stdin** (not argv — avoids ARG_MAX limits and process-table prompt leakage)
**And** the result is parsed into `AgentResult(output_text=..., tool_calls=..., tokens_in=..., tokens_out=..., mock=False)`
**And** the implementation lives **only** in `src/sdlc/runtime/claude.py` (module boundary enforced — see Dev Notes "Module boundary guardrail")
**And** `ClaudeAIRuntime` subclasses `AIRuntime` (`src/sdlc/runtime/abc.py`) and implements the exact ABC signature `async def dispatch(self, prompt: str, context: Mapping[str, object]) -> AgentResult`

**And** **AC1/D1 — async-subprocess strategy:** ONE of:
  - **D1 (Recommended):** call the blocking `subprocess.run(["claude", ...])` inside `await asyncio.to_thread(...)`. **Pros:** honours the epic's explicit `subprocess.run` wording verbatim; keeps `async def dispatch` non-blocking for the `asyncio.gather` panel path (Decision A2); minimal surface. **Cons:** one worker thread per in-flight dispatch.
  - **D2:** `asyncio.create_subprocess_exec`. **Cons:** diverges from the epic's literal `subprocess.run` instruction; re-implements timeout/kill semantics the dev would otherwise get from `subprocess.run(timeout=...)`.
  - **Recommended: D1.** Record as the first PR Change Log line.

### AC2 — Subprocess dies mid-stream (kill -9 during stdout flush)

**Given** a subprocess that dies mid-stream (`kill -9` during stdout flush)
**When** the runtime detects the failure (non-zero return / terminating signal)
**Then** `DispatchError("subprocess died with signal N at <stage>")` is raised, where `<stage>` names the dispatch stage (`spawn` | `stream` | `parse`)
**And** the partial output captured so far (if any) is preserved in `error.details["partial_output"]` for diagnostics
**And** an **integration test** simulates this kill (a stub `claude` script that prints a partial line then `os.kill(os.getpid(), SIGKILL)`) and asserts the error path, the signal number, and the preserved partial output
**And** `DispatchError` carries code `ERR_DISPATCH` (exit 2) — unchanged from `src/sdlc/errors/base.py`

### AC3 — Subprocess returns malformed JSON

**Given** a subprocess that returns malformed JSON on stdout
**When** the runtime parses the output
**Then** `DispatchError("malformed JSON from claude: <excerpt>")` is raised, where `<excerpt>` is a **200-char excerpt** of the offending output
**And** unit tests cover all four malformations: (a) truncated JSON, (b) invalid escape sequence, (c) mixed plain-text-and-JSON, (d) stdout mixed with stderr
**And** the excerpt is taken from the *raw* output and the 200-char cap is enforced even for multi-KB payloads

### AC4 — Subprocess exceeds the configured timeout

**Given** a subprocess that exceeds the configured timeout
**When** the timeout fires
**Then** the subprocess is terminated **SIGTERM first, then SIGKILL after a documented grace period** (name the grace constant, e.g. `_TERM_GRACE_SECONDS`)
**And** `DispatchError("timeout after Ns; subprocess terminated")` is raised
**And** **no orphaned subprocess remains** — an integration test asserts via `ps` (or `psutil` / `/proc` scan) that no child `claude` process survives
**And** the timeout value is configurable (constructor argument with a documented default; do NOT hard-code a magic number inline)

### AC5 — ADR-029 `mock: bool` envelope flag (contract-shape edit + snapshot ceremony)

**Given** ADR-029 §1 (`docs/decisions/ADR-029-mock-runtime-envelope-semantics.md`)
**When** this story ships
**Then** `AgentResult` (`src/sdlc/runtime/abc.py`) gains `mock: bool = Field(default=False, strict=True)`
**And** `ClaudeAIRuntime.dispatch` returns `mock=False`; `MockAIRuntime.dispatch` (`src/sdlc/runtime/mock.py`) is updated to return `mock=True` on every result
**And** the `mock` flag propagates through `DispatchMemberResult` → `PanelResult` → `DispatchResult` (dispatcher) and into the journal dispatch payload (`payload.mock`, per ADR-028)
**And** `_AgentRunLine` (`src/sdlc/telemetry/runs.py`) gains a peer `mock: bool` field so `agent_runs.jsonl` records mock-vs-real per dispatch

**And** **AC5/D1 — snapshot ceremony:** `AgentResult` is a wire-format-adjacent model. Determine whether it is one of the 5 frozen contract snapshots (`tests/contract_snapshots/v1/`); if so, the field addition pairs with an ADR-024 snapshot-regeneration ceremony **in this PR** and an ADR-024 mutation-taxonomy classification (additive-optional field with a default = backward-compatible). If `AgentResult` is *not* a snapshotted contract, state so explicitly with evidence (`grep` the snapshot dir). Do not leave this ambiguous.

**And** **AC5/D2 — `_AgentRunLine.schema_version`:** ADR-029 §4 fix #4 defers to this story's author whether `_AgentRunLine` is promoted to a real versioned contract or kept private. Pick one, record the rationale in the PR Change Log, and open a debt ticket if deferred.

### AC6 — ADR-029 default-flip + `--allow-mock` CLI gate + 4 collateral divergence fixes

**Given** ADR-029 §2 / §3 / §4
**When** this story ships (close-out)
**Then** `SDLC_USE_MOCK_RUNTIME` default flips `"1"` → `"0"` in `src/sdlc/cli/bootstrap.py` (`_use_mock_runtime()`) — real runtime is the default post-2B.1
**And** a `--allow-mock` flag is added to the 9 dispatch commands (`start`, `research`, `epics`, `stories`, `ux`, `architect`, `bootstrap`, `break`, `task`); if `SDLC_USE_MOCK_RUNTIME=1` (or set) but `--allow-mock` is absent, the command exits 1 (`ERR_USER_INPUT`); when both are set, a WARN is emitted to stderr and `payload.allow_mock_invoked=true` is recorded in the audit trail
**And** the **4 collateral divergence fixes** (ADR-029 §4) land in this PR:
  - **#1** — `MockAIRuntime` dispatch path now writes `agent_runs.jsonl` (closes the `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK` precondition; unblocks `sdlc-ux.yaml` boundary postcondition reactivation — prep-sprint C4)
  - **#2** — both mock and real hardening paths use the shared `phase1_compound_prompt_builder` (`src/sdlc/dispatcher/prompts.py`)
  - **#3** — `MockMissError` path disclosure switches to repo-relative / sentinel; absolute path exposed only under `SDLC_DEBUG=1` via `details["debug_abs_path"]`
  - **#4** — `_AgentRunLine.schema_version` resolved per AC5/D2

### AC7 — Anti-tautology receipt

**Given** ADR-026 §1 (anti-tautology requirement)
**When** the test suite runs
**Then** at least one **behavioural** test proves the real subprocess path actually executes — e.g. a stub `claude` script on PATH whose output is asserted to flow through into `AgentResult` — such that **deleting `runtime/claude.py`'s parse logic makes the test RED**, not a test that would pass against an empty stub
**And** the RED-before-GREEN ordering for `dispatch` is visible in `git log --reverse` per ADR-026 §1 (TDD-first commit ordering — `dispatch` is a public-API surface)

## Tasks / Subtasks

- [ ] **Task 1 — `runtime/claude.py` skeleton + ABC conformance** (AC: 1)
  - [ ] Write failing test: `ClaudeAIRuntime` is an `AIRuntime` subclass with the exact `dispatch` signature (RED)
  - [ ] Create `src/sdlc/runtime/claude.py`; add `ClaudeAIRuntime` to `src/sdlc/runtime/__init__.py` `__all__`
  - [ ] Implement happy-path `dispatch`: stdin prompt → `subprocess.run` via `asyncio.to_thread` (AC1/D1) → parse → `AgentResult(mock=False)`
- [ ] **Task 2 — Edge case: subprocess died mid-stream** (AC: 2)
  - [ ] Stub `claude` script that kills itself mid-flush; integration test asserts `DispatchError`, signal N, `partial_output`
  - [ ] Implement signal detection + `partial_output` capture in `error.details`
- [ ] **Task 3 — Edge case: malformed JSON** (AC: 3)
  - [ ] 4 unit tests (truncated / invalid-escape / mixed-text / stdout+stderr)
  - [ ] Implement parse-failure path with 200-char excerpt
- [ ] **Task 4 — Edge case: timeout + no orphans** (AC: 4)
  - [ ] Integration test: slow stub `claude`; assert `DispatchError`, `ps` shows no orphan
  - [ ] Implement SIGTERM→grace→SIGKILL; configurable timeout constructor arg
- [ ] **Task 5 — ADR-029 `mock` envelope** (AC: 5)
  - [ ] Add `mock` field to `AgentResult`; update `MockAIRuntime` → `mock=True`; propagate through dispatcher result chain + journal payload + `_AgentRunLine`
  - [ ] Snapshot ceremony per AC5/D1 (regenerate `tests/contract_snapshots/v1/` if `AgentResult` is snapshotted; ADR-024 classification)
- [ ] **Task 6 — ADR-029 default-flip + `--allow-mock` + collateral fixes** (AC: 6)
  - [ ] Flip `SDLC_USE_MOCK_RUNTIME` default in `cli/bootstrap.py`
  - [ ] Add `--allow-mock` to the 9 dispatch commands + gate logic + audit-trail field
  - [ ] Land collateral fixes #1–#4 (ADR-029 §4)
- [ ] **Task 7 — Anti-tautology receipt + quality gate** (AC: 7)
  - [ ] Behavioural stub-claude test (RED without parse logic)
  - [ ] Run full quality gate (CONTRIBUTING §1): ruff format/check, mypy --strict, pytest, coverage ≥87, pre-commit --all-files, mkdocs --strict, wire-format snapshots

## Dev Notes

### Relevant architecture patterns and constraints

- **AIRuntime ABC** — `src/sdlc/runtime/abc.py:35-52`. `dispatch` is `async`, takes `(prompt: str, context: Mapping[str, object])`, returns `AgentResult`, raises `DispatchError` (or subclass). No streaming in v1 (Decision C1, `architecture.md:355`).
- **AgentResult** — `src/sdlc/runtime/abc.py:15-32`. Pydantic `BaseModel`, `model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)`. Fields: `output_text: str`, `tool_calls: tuple[Mapping[str, object], ...]`, `tokens_in: int (ge=0, strict=True)`, `tokens_out: int (ge=0, strict=True)`. `extra="forbid"` means adding `mock` is a deliberate schema change — see AC5/D1.
- **MockAIRuntime** — `src/sdlc/runtime/mock.py:225-268`. Reference implementation of the ABC: `await asyncio.sleep(0)` to yield control once (abstraction-adequacy), keyed lookup, fail-loud `MockMissError`. **`ClaudeAIRuntime` is the second implementation Story 1.13/1.14 designed the abstraction for** — Winston's "abstraction leaks" are whatever `subprocess.run` forces that `MockAIRuntime` never had to model.
- **Error taxonomy** — `src/sdlc/errors/base.py`: `SdlcError` root; `DispatchError(SdlcError)` `code="ERR_DISPATCH"` (exit 2); `MockMissError(DispatchError)`. `error.details: dict[str, object]` is the diagnostic payload channel — use it for `partial_output`, `signal`, `stage`, excerpt.
- **`claude` invocation** — `architecture.md:1120` (External Integration Points): Claude Code AI runtime = `subprocess.run(["claude", ...])` in `runtime/claude.py`, per agent dispatch, failure mode `DispatchError`. Invoke `claude` in **non-interactive print mode with machine-readable output** (likely `claude -p` + a JSON output flag). **Verify the exact flags against the installed Claude Code CLI** (`claude --help`) — do not guess; the flag set is the v1 contract surface and Story 2B.2 will pin a minimum version.
- **Prep-sprint primitives available from day one:**
  - `atomic_write(path, content, *, encoding="utf-8")` / `atomic_write_bytes(path, content)` — `src/sdlc/concurrency/io_primitives.py:139-161` (ADR-031). Absolute path required; parent dir must exist.
  - `await append_with_seq_alloc(journal_path, entry_factory)` — `src/sdlc/journal/writer.py:250-306` (ADR-032). **Forward rule (DAG §7):** any *new* journal-emitting code this story adds uses this helper, not the process-local `_allocate_seq`. The `entry_factory` MUST be pure/fast and produce `entry.monotonic_seq == seq`.
- **Existing dispatch path** — `src/sdlc/dispatcher/_panel_helpers.py:479-530` builds `context = {"workflow_step", "agent_name", "target_kind"}` and calls `await with_retries(lambda: runtime.dispatch(prompt, context), ...)` (`dispatcher/retry.py:35-111` — 1 attempt + 2 retries, only `DispatchError` retryable). `ClaudeAIRuntime` plugs in here unchanged — the dispatcher already programs against the ABC.
- **Telemetry** — `src/sdlc/telemetry/runs.py:28-184`: `_AgentRunLine` (frozen dataclass, `to_json_line()` sorts keys) + `record_agent_run(...)`. ADR-029 §4 adds `mock` here.

### Module boundary guardrail (READ — primary cause of RED-checkpoint failures)

`scripts/module_boundary_table.py:53-56`: `runtime` may import **only** `errors`, `contracts`, `concurrency`. `runtime` is **forbidden from importing** `engine`, `dispatcher`, `state`, `journal`, `cli`.

**Consequence:** `runtime/claude.py` MUST NOT import `journal`. The runtime's `dispatch` returns an `AgentResult` and nothing more — it does **not** journal. Journal/`agent_runs.jsonl` emission for a dispatch happens in the **dispatcher / telemetry** layer, which already owns it. The DAG §5 / ADR-032 forward rule "2B.1 uses `append_with_seq_alloc` from day one" applies to any new journal-emitting code this story adds **in the dispatcher/telemetry layer** (e.g. ADR-029 §4 fix #1, mock writing `agent_runs.jsonl`) — NOT to `runtime/claude.py`. If a RED checkpoint shows `runtime/` importing `journal`, the design is wrong — relocate the journal-touching code to its owning module (this is exactly the C1 prep-sprint `engine/`→`concurrency/` lesson).

### Project Structure Notes

- **New file:** `src/sdlc/runtime/claude.py` (`ClaudeAIRuntime`). Add export to `src/sdlc/runtime/__init__.py` `__all__` (after `"MockAIRuntime"`).
- **Modified:** `src/sdlc/runtime/abc.py` (`AgentResult.mock`), `src/sdlc/runtime/mock.py` (`mock=True`, ADR-029 #3 path disclosure), `src/sdlc/cli/bootstrap.py` (default-flip), `src/sdlc/telemetry/runs.py` (`_AgentRunLine.mock`), `src/sdlc/dispatcher/` result chain (mock propagation), the 9 dispatch CLI command modules (`--allow-mock`).
- **Tests:** `tests/unit/runtime/test_claude.py` (mirrors src per `architecture.md:686`), `tests/integration/test_claude_runtime_*.py` (kill / timeout / orphan). Stub `claude` scripts under a test fixtures dir; add to PATH via `monkeypatch.setenv("PATH", ...)`.
- **Layer 1 sibling coordination:** 2B.1 is the only Layer-1 story touching `runtime/`. It touches CLI command modules for `--allow-mock`; **2B.2 also touches `cli/` (`cli/main.py` pre-flight) and `errors/base.py`**. Coordinate on `errors/__init__.py` if `ClaudeAIRuntime` work touches it. Worktree: `epic-2b/2b-1-claude-runtime` (owner: Charlie, DAG §5). Per CONTRIBUTING §3 — one branch, linear FF-merge, rebase between sibling merges.
- **Snapshot count:** ADR-024 frozen-contract count must stay correct — if `AgentResult` is snapshotted, regenerate; if not, the count is unchanged. Wire-format snapshot check (`scripts/freeze_wireformat_snapshots.py --check`) must stay green.

### Testing standards summary

- TDD-first (CONTRIBUTING §2): tests-first commit ordering visible in `git log --reverse` for `dispatch` (public API). RED commit must fail without the implementation (ADR-026 §1 anti-tautology).
- Test org (`architecture.md:682-701`): `tests/unit/runtime/test_claude.py`; integration under `tests/integration/`. Naming `test_<behavior>_<expected_outcome>`.
- Quality gate (CONTRIBUTING §1): ruff format + ruff check + `mypy --strict` + pytest + coverage ≥87 (`pyproject.toml --cov-fail-under`) + `pre-commit run --all-files` + `mkdocs --strict` + wire-format snapshots.
- No real `claude` binary in CI — every test uses a deterministic **stub `claude` script** (shell or Python) placed on PATH. The stub models each edge case (partial-then-kill, slow, malformed-JSON, well-formed).
- `mypy --strict`: `subprocess` + `asyncio` types must be clean; no bare `type: ignore`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-2B.1] — AC source (lines 1454-1483)
- [Source: _bmad-output/planning-artifacts/architecture.md#Category-C — AIRuntime & Dispatcher] — Decision C1 (line 351-357)
- [Source: _bmad-output/planning-artifacts/architecture.md#External-Integration-Points] — `runtime/claude.py` = `subprocess.run(["claude", ...])` (line 1114-1125)
- [Source: docs/decisions/ADR-029-mock-runtime-envelope-semantics.md] — `mock` flag, default-flip, `--allow-mock`, 4 collateral fixes
- [Source: docs/decisions/ADR-031-atomic-write-primitive.md] — `atomic_write` primitive
- [Source: docs/decisions/ADR-032-append-with-seq-alloc.md] — cross-process seq allocation forward rule
- [Source: docs/sprints/epic-2b-dag.md] — §3 Layer 1, §4 critical path, §5 worktree assignment, §7 Risk rows 1 & 4
- [Source: src/sdlc/runtime/abc.py] — `AIRuntime` ABC + `AgentResult` (lines 15-52)
- [Source: src/sdlc/runtime/mock.py] — `MockAIRuntime` reference implementation (lines 225-268)
- [Source: src/sdlc/errors/base.py] — `DispatchError`, `MockMissError`
- [Source: scripts/module_boundary_table.py] — `runtime` module import rules (lines 53-56)
- [Source: CONTRIBUTING.md] — §1 quality gate, §2 TDD-first, §3 worktree workflow
- [Source: docs/decisions/ADR-026.md §1] — anti-tautology receipt requirement

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
