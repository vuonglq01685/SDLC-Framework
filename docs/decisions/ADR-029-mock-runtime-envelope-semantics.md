# ADR-029: MockAIRuntime Envelope Semantics + Default-Flip Plan

**Status:** Accepted (2026-05-21, prep-sprint C8 design doc; implementation lands with Story 2B.1).

**Source:** Epic 2A retrospective §5 "MockAIRuntime divergences enumerated" + §7.1 C8 + §6.3
DOC2 + §6.4 team agreement (I). Owners: Charlie + Dana.

## Context

Today (end of Epic 2A) the framework ships with `SDLC_USE_MOCK_RUNTIME=1` as the implicit
default. The mock IS the only working runtime — no `ClaudeAIRuntime` exists yet; Story 2B.1
ships it. Five concrete divergences from production-grade behaviour were enumerated in the
retrospective and constitute the entire risk surface this ADR addresses:

1. **MockAIRuntime does not write `agent_runs.jsonl`** — breaks Phase-2 boundary postcondition
   (`EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK`, owned by prep-sprint C4).
2. **`_default_prompt_builder` returns `specialist.body` verbatim** — bypasses Phase-1 prompt
   hardening defences that ClaudeAIRuntime will route through.
3. **`MockMissError` leaks resolved absolute `fixtures_dir` path** — information disclosure.
4. **`_AgentRunLine.schema_version=1` hardcoded + unfrozen** — drift risk vs ADR-024 frozen
   wire-format invariant.
5. **`SDLC_USE_MOCK_RUNTIME=1` is the default** — mock-on-in-production posture; operators
   may inadvertently ship to external users with mock outputs once a real runtime exists.

Once Story 2B.1 lands `ClaudeAIRuntime`, divergence #5 becomes the single largest external-ship
safety risk. Divergences #1–#4 are downstream of #5 — fixing them in isolation while keeping
default-on is treating symptoms.

## Decision

Four mutually-reinforcing changes, sequenced behind Story 2B.1.

### 1. `mock: bool` flag on the AgentResult envelope

`src/sdlc/runtime/abc.py::AgentResult` gains:

```python
mock: bool = Field(default=False, strict=True)
```

- Default `False` — real-runtime dispatch is non-mock by construction.
- `MockAIRuntime` constructs every result with `mock=True`.
- `ClaudeAIRuntime` (Story 2B.1) constructs with `mock=False`.

AgentResult declares `extra="forbid"` and is treated F3-wire-format-adjacent. The added field
is a minor non-breaking extension (existing consumers ignore the default-False field). The
runtime-neutral contract is preserved.

Downstream propagation:

- Dispatcher `DispatchMemberResult` + `PanelResult` + `DispatchResult` carry the flag through.
- Journal entries from mock dispatch carry `payload.mock=true` (covered by ADR-028 journal-kind
  taxonomy as a per-kind field-extension on `dispatch_attempt`, `artifact_written`).
- `agent_runs.jsonl` `_AgentRunLine` gains a peer `mock: bool` field — see decision 4.
- Dashboard + `sdlc trace` SHOULD surface a visible "MOCK" badge on any entry carrying the
  flag (Epic 5 surface work).

### 2. `SDLC_USE_MOCK_RUNTIME` default-flip (post-2B.1)

| Phase | Behaviour |
|---|---|
| Pre-Story-2B.1 (today) | env var defaults to `1`; setting `0` immediately errors with "no real runtime wired in v1" |
| Story 2B.1 close-out | env var default flips to `0`; setting `1` becomes the explicit opt-in for mock dispatch |
| Story 2B.3 verification | conformance suite asserts default-off behaviour rejects mock dispatch unless `--allow-mock` (decision 3) is also set |

The flip itself is mechanical (one constant in each of `cli/bootstrap.py`,
`cli/task.py`, `cli/break_.py`, `cli/_epics_pipeline.py`, `cli/_stories_pipeline.py`, plus
the error-emitting paths in `cli/epics.py` + `cli/stories.py` that currently advise
"wait for Story 2B.1 ClaudeAIRuntime"). The flip ships in Story 2B.1 alongside the real
runtime so no operator window exists where the framework has neither a real runtime nor a
default-on mock.

### 3. CLI `--allow-mock` gate

Every CLI command that dispatches specialists gains a `--allow-mock` flag:

`sdlc start`, `sdlc research`, `sdlc epics`, `sdlc stories`, `sdlc ux`, `sdlc architect`,
`sdlc bootstrap`, `sdlc break`, `sdlc task`.

Semantics:

- Default: not set. If `SDLC_USE_MOCK_RUNTIME=1` is present but `--allow-mock` is missing, the
  CLI exits 1 with `ERR_USER_INPUT` and message "mock runtime is enabled via
  `SDLC_USE_MOCK_RUNTIME=1` but `--allow-mock` was not provided; pass `--allow-mock` to
  acknowledge mock dispatch in this run".
- When set: mock dispatch is permitted; `ClaudeAIRuntime` is bypassed for this invocation
  (even if otherwise available); stderr emits a one-line WARN: `"WARN: --allow-mock is set;
  this run uses MockAIRuntime, outputs are fixture-derived, not real model outputs"`.
- The flag is an explicit acknowledgement, not a silent bypass — it appears in command audit
  trails (`sdlc trace --kind=dispatch_attempt` surfaces `payload.allow_mock_invoked=true`).

Note: `cli/research.py:399` already carries the placeholder comment `--allow-mock gating is
deferred to v1.x`; that v1.x is **Story 2B.1**, not later.

### 4. Fix the four collateral divergences inside Story 2B.1 scope

| # | Divergence | Fix |
|---|---|---|
| 1 | Mock doesn't write `agent_runs.jsonl` | `MockAIRuntime.dispatch()` appends an `_AgentRunLine` with `mock=true` exactly as `ClaudeAIRuntime` will. Closes `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK` (C4 reactivation). |
| 2 | `_default_prompt_builder` returns `body` verbatim | Replace with the shared `phase1_compound_prompt_builder` (Story 2A.8 export) so mock and real share the prompt-hardening path. Mock still returns a fixture-derived output_text, but the prompt that drives the lookup matches the real flow. |
| 3 | `MockMissError` leaks absolute fixtures_dir | Switch to repo-relative path or a stable `<fixtures>/<key>.json` sentinel string; absolute path stays in `details["debug_abs_path"]` if needed for local dev, gated by `SDLC_DEBUG=1`. |
| 4 | `_AgentRunLine.schema_version=1` hardcoded | Promote `_AgentRunLine` to a real wire-format contract candidate: add a snapshot under `tests/contract_snapshots/v1/` paired with the existing five, OR keep it private and document that decision explicitly in ADR-028 §scope. Decision deferred to Story 2B.1 author (Charlie); both options are F3-compliant. |

## Alternatives Considered

- **Detect mock via `isinstance(runtime, MockAIRuntime)` in the dispatcher.** Rejected:
  couples dispatcher to runtime concrete types; violates the AIRuntime ABC boundary
  (`engine ↛ runtime concrete`).
- **Separate `MockedAgentResult` subclass hierarchy.** Rejected: forces every consumer to
  pattern-match on type; the boolean flag carries the same signal with one-line cost.
- **Journal-only mock marker (no AgentResult field).** Rejected: loses signal at dispatch
  time; non-journal consumers (live telemetry, dashboard websocket if/when added) cannot
  distinguish.
- **Hard-block any mock dispatch in production (no `--allow-mock` escape hatch).** Rejected:
  CI runs, dev-loop iteration, and Epic 2B.3 conformance tests legitimately need mock
  dispatch; the explicit gate keeps the safety property (mock is never accidental) without
  removing the legitimate use case.

## Consequences

- **+** Operators have unambiguous machine-readable + human-visible signal on every dispatch
  about whether the result came from a real model or a fixture.
- **+** Post-2B.1 default posture is safe by construction; "ship to external users with mock
  outputs" requires three coincident operator errors (env var set + flag passed + warning
  ignored).
- **+** Closes four open divergence tickets (#1–#4) inside a single 2B.1 ship rather than
  letting them rot as `EPIC-2A-DEBT-*`.
- **+** Phase-2 boundary postcondition reactivation (prep-sprint C4) unblocked — Mock will
  now write `agent_runs.jsonl` like the real runtime.
- **−** Minor schema edit to `AgentResult` (extra="forbid" field add). Internal; no contract
  snapshot regen, but reviewer-A audit of every callsite to confirm propagation.
- **−** Nine CLI commands gain a `--allow-mock` arg — small surface change, audited at
  Story 2B.1 review-A label.
- **−** Existing test fixtures using `SDLC_USE_MOCK_RUNTIME=1` defaults must be audited
  for either explicit env-set or `--allow-mock` pass. Estimate: ~50 test files (Story 2B.1
  brings the migration script).

## Migration Plan

| When | Action | Owner |
|---|---|---|
| Now (this ADR) | Ratify design; no code changes | Charlie + Dana |
| Story 2B.1 | Land `ClaudeAIRuntime`; add `mock: bool` to `AgentResult` + `_AgentRunLine`; flip env-var default to OFF; add `--allow-mock` to 9 CLIs; fix divergences #1–#4 | Charlie (primary) + Dana (test migration) |
| Story 2B.3 | Behavioural conformance: `mock=true` round-trip; default-off rejects mock dispatch; `--allow-mock` warning emitted exactly once per invocation | Dana |
| Story 2B.4 / 2B.5 | Verify Phase-1/2/3 prompt-hardening boundary tests now pass with Mock (closes Phase-2 boundary postcondition reactivation from C4) | Winston |

## Revisit-by

After Story 2B.3 (behavioural conformance) lands and signs off. At that point: confirm
migration is complete; archive ADR-029 status as "Implemented"; and surface any unfixed
divergences as new ADRs.
