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
