# Architecture Overview

## Paradigm

SDLC-Framework treats deterministic orchestration of non-deterministic AI agents as
a TRIZ-style contradiction. The contradiction is resolved across three axes:

- **By space**: deterministic mechanics (state machine, dispatcher, journal, hooks)
  live in framework code. Non-deterministic agent reasoning lives behind the
  `AIRuntime` ABC.
- **By time**: agents propose; framework validates (hash-validated signoffs,
  append-only journal, schema-validated workflows).
- **By trust**: workflow YAML and specialists are schema-validated trusted inputs;
  agent output is evidence-with-provenance, not ground truth.

Detailed paradigm framing lives at `_bmad-output/planning-artifacts/architecture.md#Paradigm` (planning-artifact, intentionally outside this site per ADR-011).

## The 16-Module Dependency DAG

Architecture §1052–§1112 specifies the 16-module substrate as a strict DAG. The
layered hierarchy is:

```text
                         cli/                              ← entry points
                          ↓
     ┌────────────────────┼────────────────────┐
     ↓                    ↓                    ↓
  engine/             adopt/              dashboard/
     ↓                    ↓                    ↓
     ├──→ dispatcher/                          │
     │       ↓                                 │
     │     ┌─┴─────────────┐                  │
     │     ↓               ↓                  │
     │  runtime/        workflows/             │
     │                  specialists/           │
     │                                         │
     └──→ hooks/  signoff/  telemetry/         │
              ↓       ↓          ↓             │
              └───────┴──────────┴────→ state/ │
                                       journal/←┘
                                          ↓
                               contracts/  ids/  config/
                                       ↓
                                concurrency/  errors/
```

The DAG is mechanically enforced by Story 1.4's `boundary-validator` pre-commit
hook (`scripts/check_module_boundaries.py`), which encodes the dependency table as
a `MODULE_DEPS` Python literal and AST-walks every changed Python file's imports.
See [ADR-010](decisions/ADR-010-pre-commit-config.md) and
[ADR-012](decisions/ADR-012-module-layout.md) for the enforcement mechanism and
layout decision.

## Module Specifications (Summary)

| Module | Responsibility | Depends on | Forbidden from |
|---|---|---|---|
| `errors/` | Exception hierarchy root | (none) | everything (leaf) |
| `ids/` | Canonical ID parse/build | `errors` | (none beyond) |
| `contracts/` | 5 wire-format pydantic models | `errors`, `ids` | engine, dispatcher, cli |
| `config/` | project.yaml + env allow-list + secret sanitiser | `errors`, `contracts` | engine, dispatcher, cli |
| `concurrency/` | flock + asyncio Semaphore | `errors` | engine, state, journal |
| `state/` | state.json model + atomic write + projection | `errors`, `contracts`, `concurrency`, `config` | engine, dispatcher, runtime, cli |
| `journal/` | append-only JSONL | `errors`, `contracts`, `concurrency`, `config` | engine, dispatcher, runtime, cli |
| `signoff/` | hash-validated signoffs | `errors`, `contracts`, `state`, `journal` | engine, dispatcher, cli |
| `runtime/` | AIRuntime ABC + Claude impl + mock | `errors`, `contracts`, `concurrency` | engine, dispatcher, state, journal, cli |
| `workflows/` | workflow YAML loader + static checker | `errors`, `contracts`, `ids` | engine, dispatcher, runtime |
| `specialists/` | specialist registry + cross-ref | `errors`, `contracts`, `workflows` | engine, dispatcher, runtime |
| `hooks/` | hook payload + sequential runner + tampering detection | `errors`, `contracts`, `state`, `journal`, `ids` | engine, dispatcher, runtime, cli |
| `telemetry/` | three observability streams + DORA | `errors`, `contracts`, `journal` | engine, dispatcher, runtime, cli |
| `dispatcher/` | primary + parallel + synthesizer dispatch | `errors`, `runtime`, `workflows`, `specialists`, `state`, `journal`, `hooks`, `telemetry`, `concurrency` | engine, cli |
| `engine/` | sync step-machine + auto-loop + STOP triggers + scanner | most lower-stack modules | cli |
| `adopt/` | 3-pass adopt-mode driver | `errors`, `state`, `journal`, `signoff`, `config`, `cli/git` | engine, dispatcher, runtime |
| `dashboard/` | local HTTP read-only dashboard | `errors`, `state` (read-only), `journal` (read-only), `telemetry`, `signoff`, `config` | engine, dispatcher, runtime, hooks, adopt |
| `cli/` | Typer console script + slash command shells | `engine`, `adopt`, `dashboard`, `runtime`, `config`, `errors` | (top of stack) |

Full per-module API surface and dependency rationale: see
`_bmad-output/planning-artifacts/architecture.md#Module-Specifications`.

## Eight Specific Boundary Rules

Architecture §1103 names eight specific boundary rules on top of the DAG. Six are
mechanically enforced by Story 1.4's import-graph validator (rules #3, #4-partial,
#5, #6, #7, #8); two are runtime-semantics rules best caught by code review (#1,
#2). [ADR-012](decisions/ADR-012-module-layout.md) documents which rules are
statically enforced and which are review-only.

1. `cli/` is the only module that may invoke external binaries other than `runtime/` (review).
2. `engine/` and `dispatcher/` import `runtime/` only via the `AIRuntime` ABC (review).
3. `state/` and `journal/` are siblings, not parent-child (statically enforced).
4. `dashboard/` is read-only with respect to state and journal (statically: no
   imports from `dashboard` to engine/dispatcher; runtime: no `state.atomic` or
   `journal.writer` imports — review-only widening).
5. `hooks/` does not import `engine/` or `dispatcher/` (statically enforced).
6. `adopt/` does not import `engine/` or `dispatcher/` (statically enforced).
7. `workflows/` and `specialists/` do not import `engine/`, `dispatcher/`, or
   `runtime/` (statically enforced).
8. `contracts/`, `ids/`, `config/`, `concurrency/`, `errors/` form the foundation
   layer (statically enforced).

## Hook Chain Integration Map

Story 2A.4 ships the pre-write hook runner (`hooks/runner.py`) and two builtin hooks:
`naming_validator` (FR36, AC4) and `phase_gate` (FR37, AC5). The chain runs before every
artifact write. Engine-side wiring lands in Story 2A.6; this section documents the contract
so callers can conform before 2A.6 merges.

### Data flow

```
Caller (dispatcher / CLI)
  │
  ├─ constructs HookPayload(hook_name, target_path, target_kind, content_hash_before, write_intent)
  │
  └─ await run_hook_chain(payload, hooks=(naming_validator, phase_gate), journal_path=...)
            │
            ├─ naming_validator(payload)
            │     validates file stem against canonical id regex for:
            │       01-Requirement/04-Epics/      → EPIC_ID_REGEX
            │       01-Requirement/05-Stories/    → STORY_ID_REGEX (+ parent epic dir)
            │       01-Requirement/06-Tasks/      → TASK_ID_REGEX (+ both ancestor dirs)
            │     returns HookDecision.allow() | .deny(error_code="naming_violation")
            │
            └─ phase_gate(payload, repo_root=...)
                  reads .claude/state/signoffs/phase-{N-1}.yaml for Phase 2/3 writes
                  returns HookDecision.allow() | .deny(error_code="phase_gate_violation")
            │
            └─ HookDecision{decision, hook_name, reason, error_code}
                  "deny"  → caller blocks write + journal.append(kind="hook_rejected", ...)
                  "allow" → caller proceeds with write (no journal entry from the chain)
```

### Write-site integration table

| Write site | Caller module | `target_kind` | Story that wires it |
|---|---|---|---|
| Engine pre-write (every artifact write) | `dispatcher.core` | `"write_intent"` | Story 2A.6 (engine-side wiring) |
| Claude Code PreToolUse hook | `claude_hooks/pre_tool_use.py` | `"write_intent"` | Story 2A.6 (shells to `sdlc hook-check`) |
| Signoff record write | `signoff.records.write_record` | `"signoff_record"` | Story 2A.12 |

### Bypass policy (AC6, NFR-SEC-4)

`--force-bypass-signoff "<justification>"`:

- `naming_validator` is **never bypassed** — bypassing it would corrupt the artifact-id audit trail
  that `sdlc trace` and `sdlc rebuild-state` depend on.
- `phase_gate` is bypassed **per-dispatch** when: (a) the justification is ≥ 10 characters,
  (b) the hook trust store is initialized (not `uninitialized` or `corrupted`).
- Every bypass appends `kind="bypass_signoff"` to the journal (actor: `hooks.runner`).

See `docs/runbooks/diagnose-hook-rejection.md` for operator resolution steps.

### Journal kinds introduced by Story 2A.4

| `kind` | Actor | Payload fields | When emitted |
|---|---|---|---|
| `hook_rejected` | `hooks.runner` | `hook`, `target`, `reason`, `error_code` | First hook in chain returns `deny` |
| `bypass_signoff` | `hooks.runner` | `target`, `justification`, `justification_truncated`, `user`, `phase_attempted`, `missing_signoff_path` | `phase_gate` is bypassed for a Phase 2/3 write |

---

## Where to Read More

- **Full module table + per-module APIs**: `_bmad-output/planning-artifacts/architecture.md#Module-Specifications`.
- **Eight boundary rules verbatim**: `_bmad-output/planning-artifacts/architecture.md#Architectural-Boundaries-Import-Rules`.
- **The validator script**: `scripts/check_module_boundaries.py` (Story 1.4).
- **The pre-commit configuration**: [ADR-010](decisions/ADR-010-pre-commit-config.md).
- **The 16-module layout decision**: [ADR-012](decisions/ADR-012-module-layout.md).
- **Workflow YAML loader and static checker** (`src/sdlc/workflows/`): implemented in Story 2A.1.
  Provides `load_workflow(path) → WorkflowSpec`, `validate_workflow(spec) → None`, and
  `WorkflowRegistry`. The module validates workflow YAML against the frozen `WorkflowSpec` v1
  contract (ADR-024), rejects unknown fields and instruction-shaped strings (NFR-SEC-7, ADR-013),
  and enforces disjoint write-glob invariants between parallel specialists at load time (FR25).
  The `workflows_yaml/` package-data directory (`src/sdlc/workflows_yaml/`) ships with the wheel
  (populated by Story 2A.8+); `WorkflowRegistry.load(dir)` is the canonical engine entrypoint.
- **Hook chain runbook**: `docs/runbooks/diagnose-hook-rejection.md` — operator guide for
  `hook_rejected` and `bypass_signoff` journal entries (Story 2A.4).

## Journal Kind Catalog

Every call to `sdlc.journal.writer.append` must use one of the registered `kind` discriminators
below. `JournalEntry.kind` is an open `str` (AC10, ADR-024 v1 lock), so new kinds require no
contract edit — but they MUST be catalogued here for observability via `sdlc trace`.

**D-decision AC10: D1** — all three 2A.3 kinds shipped in one story (tightly coupled to
dispatch outcomes; discoverable via `sdlc trace --kind=<kind>`).

| kind | written by | meaning | added in story |
|---|---|---|---|
| `hooks_trusted` | `cli.trust_hooks` (`sdlc trust-hooks`) | Hook files have been verified tamper-free and the trust record has been persisted | Story 2A.5 |
| `dispatch_attempt` | `dispatcher.core._run_member` | One attempt (success, retry, or final failure) of a specialist dispatch; one entry per attempt per specialist | Story 2A.3 |
| `artifact_written` | `dispatcher.core._run_member` | A specialist's `output_text` was successfully written to its declared write target on disk | Story 2A.3 |
| `stop_trigger_raised` | `dispatcher.core._emit_stop_trigger` | Terminal dispatch failure after retry exhaustion; Epic 4 Story 4.6 reads these entries to compute the STOP banner state (`epic_4_placeholder=True` until then) | Story 2A.3 |
| `hook_rejected` | `hooks.runner` | First hook in chain returns `deny`; fields: `hook`, `target`, `reason`, `error_code` | Story 2A.4 |
| `bypass_signoff` | `hooks.runner` | `phase_gate` bypassed for a Phase 2/3 write; fields: `target`, `justification`, `user`, `phase_attempted`, `missing_signoff_path` | Story 2A.4 |
