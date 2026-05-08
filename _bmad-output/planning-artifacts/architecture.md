---
stepsCompleted:
  - step-01-init
  - step-02-context
  - step-03-starter
  - step-04-decisions
  - step-05-patterns
  - step-06-structure
  - step-07-validation
  - step-08-complete
status: complete
lastStep: 8
completedAt: '2026-05-07'
inputDocuments:
  - /Users/vuonglq01685/Documents/Projects/SDLC-new/SDLC-Framework/_bmad-output/planning-artifacts/prd.md
  - /Users/vuonglq01685/Documents/Projects/SDLC-new/ARCHITECTURE.md
  - /Users/vuonglq01685/Documents/Projects/SDLC-new/PRODUCT.md
  - /Users/vuonglq01685/Documents/Projects/SDLC-new/SDLC-Framework/_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-07.md
workflowType: 'architecture'
project_name: 'SDLC-Framework'
user_name: 'Vuonglq01685'
date: '2026-05-07'
documentStructureApproved:
  - 1-system-context
  - 2-container-deployment
  - 3-module-specification
  - 4-data-model
  - 5-critical-flow-sequences
  - 6-cross-cutting-concerns
  - 7-nfr-traceability
  - 8-adr-log
  - 9-folder-file-layout
strategicConstraints:
  - airuntime-abstraction-from-v1
  - local-first-no-telemetry
  - hash-validated-signoff-substrate
  - internal-first-pypi-as-forcing-function
technicalConstraintsBaseline:
  language: 'Python 3.11+'
  cli_framework: 'typer'
  dashboard: 'FastAPI + HTMX (lightweight, no SPA)'
  git_interaction: 'read-only via git log subprocess; mutate via gh CLI shim'
  schema_validation: 'pydantic v2'
  logging: 'structlog / JSON formatter; journal = append-only JSONL'
  testing: 'pytest + record/replay fixtures for AI dispatches'
  packaging: 'pyproject.toml (PEP 621), hatchling or uv build'
  distribution: 'pip install sdlc-framework, deps: python + git + gh'
nfrBaseline:
  cli_cold_start: '< 200ms'
  dashboard_load: '< 1s with 10K journal records'
  journal_durability: 'crash-safe via fsync + atomic rename'
  secret_handling: 'zero secrets in journal (sanitization layer)'
inheritedFromOldArchitecture:
  status: 'reference-only — must re-validate against PRD before adoption'
  approach: 'cherry-pick decisions still valid; flag obsolete ones in ADR log'
---

# SDLC-Framework — Architecture Decision Document

> **Status:** Draft v1.0 (in progress) · **Owner:** Vuonglq01685 (Tech Lead) · **Started:** 2026-05-07
> **Companion to:** `_bmad-output/planning-artifacts/prd.md` · **Distribution target:** PyPI as `sdlc-framework`
> **Supersedes:** `/SDLC-new/ARCHITECTURE.md` (v0.1 draft, predates PRD strategic decisions)

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## How to read this document

This is an **engineering specification**, not a marketing artifact. It is organized as a navigable map (Sections 1–2 give the C4-style overview) followed by deep specifications (Sections 3–9) that any engineer or AI agent can consume to implement the system without guessing. Every load-bearing decision is recorded in the ADR Log (Section 8) with alternatives and rationale.

- Sections 1–2 — System Context & Containers (C4 L1+L2, navigation aid)
- Sections 3–7 — Module specs, data model, critical flows, cross-cutting concerns, NFR traceability (the "real" specification)
- Section 8 — ADR Log (decision record)
- Section 9 — Folder/File Layout (concrete grounding)

Anything labeled "v1" describes what ships at PyPI v1.0. Anything labeled "v2+" is roadmap reference.

---

## Approved Document Structure

The following 9-part structure was approved on 2026-05-07 and frames every subsequent step of this workflow:

1. **System Context** (C4 L1) — actors, external systems, trust boundaries
2. **Container / Deployment View** (C4 L2) — CLI, dashboard server, hooks, state store, journal
3. **Module Specification** — per module: responsibility, interface, invariants, dependencies
4. **Data Model** — JSON state schema, journal record schema, markdown artifact frontmatter
5. **Critical Flow Sequences** — `/sdlc-auto`, hash signoff, AIRuntime dispatch, kanban transition
6. **Cross-cutting Concerns** — security, observability, error handling, config, testing strategy
7. **NFR Traceability** — PRD NFR → architectural mechanism → measurement
8. **ADR Log** — every load-bearing decision with alternatives, chosen, rationale, consequences
9. **Folder / File Layout** — concrete repository tree + naming conventions

---

_Sections below will be appended as the workflow progresses._

---

## Project Context Analysis

### Paradigm: Deterministic Orchestration of Non-Deterministic Agents

The framework's central engineering challenge is a TRIZ-style physical contradiction: it must produce **deterministic, auditable, replayable artifacts** from **non-deterministic LLM agents**. Every architectural decision in this document either pushes determinism outward (toward state, audit, gates, replay) or contains non-determinism inward (within agent dispatch, behind the AIRuntime boundary, capped by STOP triggers).

The paradigm is resolved by separation:

- **By space.** State, audit chain, signoffs, and replay are deterministic by construction. Agent suggestion text is non-deterministic and quarantined behind the AIRuntime interface.
- **By time.** First-run is non-deterministic (LLM produces output). Replay is deterministic (journal entries reproduce state without re-invoking the runtime).
- **By trust.** Agent output is treated as evidence requiring provenance, not as ground truth. Hash-validated signoffs establish the chain of custody.

Naming this paradigm explicitly is itself a load-bearing decision. Every downstream concern — audit, atomic writes, AIRuntime, STOP triggers — is a consequence of where the determinism boundary is drawn. The sections below treat the paradigm as the first invariant; mechanisms are second-order.

### Requirements Overview

**Functional Requirements (52 FRs in 9 capability areas):**

1. **Project Lifecycle Management (FR1–FR5)** — `sdlc init` (greenfield + adopt), `sdlc scan`, `sdlc replan`, schema-incompatibility refusal. Implies: bootstrapper, filesystem scanner, replan engine, schema gate.
2. **Phase Workflow Orchestration (FR6–FR18)** — 13 slash commands across Phase 1/2/3, dynamic sub-track dispatch, signoff document generation, per-task TDD pipeline. Implies: workflow engine, slash router, YAML-driven dispatch graph, signoff generator, per-task state machine.
3. **Auto-Mode & STOP Triggers (FR19–FR24)** — `/sdlc-auto`, `/sdlc-auto-mad`, 7 STOP conditions, auto-brainstorm panel, watchdog. Implies: driver loop, 7 detectors, panel-dispatch utility, mad-mode reverse logic.
4. **Multi-Agent Specialist Dispatch (FR25–FR29)** — primary + parallel agents with disjoint-writes check, synthesizer, retry-with-backoff, ~25 markdown specialists, AIRuntime interface. Implies: dispatcher, orchestrator, workflow-load-time validator, AIRuntime ABC + Claude + Mock implementations, specialist registry.
5. **State Persistence & Audit Chain (FR30–FR35)** — atomic writes, append-only journal, hash-validated signoffs, `trace`/`replay`/`rebuild-state`. Implies: atomic-write protocol, journal log, hash record + validator, three reconstruction utilities.
6. **Hook System & Phase Gates (FR36–FR40)** — naming validator, phase-gate enforcer, bypass-with-journal, hook tampering detection, Claude-Code-side PreToolUse. Implies: in-process hook runner, hash-verification engine, framework-installed PreToolUse hook.
7. **Status Visibility & Dashboard (FR41–FR46)** — local web dashboard, full UI section set, `sdlc status`/`sdlc logs`, read-only HTTP. Implies: stdlib `http.server` dashboard, vanilla-JS frontend, DORA computation with 30s cache, JSONL log tailer.
8. **Distribution, Versioning & Migration (FR47–FR50)** — `pip install`, major-version refusal-without-migration, idempotent migrations with backup, `package_data` payload. Implies: hatchling build, migrations registry, version gate, packaged static assets.
9. **Configuration & Secret Hygiene (FR51–FR52)** — `project.yaml` overrides, env-variable allow-list. Implies: pydantic config loader, env-var access guard.

**Non-Functional Requirements (driving architectural decisions):**

| Category | Architectural impact |
|---|---|
| **Performance** | `sdlc scan` < 2s on 200-story/1000-task → indexed/incremental scanning; agent dispatch < 500ms → lazy specialist loading; dashboard < 100ms → stream `state.json` from disk without parse |
| **Reliability** | Atomic write protocol invariant; journal append-only by construction; chaos-test in CI; loop iterations are pure functions of disk state |
| **Security** | Zero secrets in state/journal; env allow-list with explicit error; data-vs-instruction prompt boundary; hook tampering advisory |
| **Privacy** | No outbound HTTP from framework process itself; all data local; zero telemetry in v1 |
| **Compatibility** | Python 3.10+; mac/Linux first-class; Windows via WSL2; Mock AIRuntime adequacy test as CI gate |
| **Observability** | Every state mutation produces journal line; every agent dispatch produces `agent_runs.jsonl`; full lineage via `sdlc trace`; per-project DORA cached 30s |
| **Maintainability** | `mypy --strict`, ruff clean, ≤400 LOC/file, ≤50 LOC/function, complexity ≤8; 90% engine / 80% workflow coverage; ADR for every load-bearing decision |
| **Accessibility** | Dashboard WCAG 2.2 Level A; STOP banners use color + text; CLI `--no-color` and `--json` modes |
| **DR** | `sdlc rebuild-state` from journal; migrations back up state |

### Scale & Complexity

- **Primary domain:** developer tool / agentic orchestration platform (Python CLI + local web dashboard + Claude Code extension surface).
- **Complexity level:** **HIGH** — multi-agent parallel orchestration with cryptographic invariants, dual hook execution model, plugin-shaped specialist registry of ~25 agents, autonomy spectrum manual → auto-mad, multiple user-facing surfaces plus a fifth implicit surface (state).
- **Module count (corrected after panel review).** ~25–30 top-level Python modules, **not** 12–15. The earlier count conflated *Python modules* with *content trees*; specialists (`agents/`) and workflows (`workflows/`) are markdown/YAML content, not modules. Several modules need internal sub-splits to honour the ≤400 LOC cap (notably `state/`, `dispatcher/`, `dashboard/routes/`, `journal/{writer,reader,compactor}.py`). Modules at risk of breaching the cap if kept monolithic: `engine/state.py`, `dispatcher.py`, `dashboard/server.py`, `journal.py`. Missing-from-original list and required: `telemetry/` (DORA collector), `concurrency/` (file-lock + dashboard reader race protection), `errors/` (shared exception hierarchy for replay correctness).
- **Surface model.** Originally framed as four surfaces (CLI, slash commands, subagents, hooks). Refined slicing after review: **CLI / Claude-prompt-surface / Hooks / State** — same arity, different semantics.
  - **State** is a fifth, implicit surface (humans read `state.json`, run `git diff`, view dashboard — it has its own contract: schema, naming, ordering, failure modes). Treating it as a surface gives it an architectural owner.
  - **Slash commands** and **subagents** collapse into a single user-facing surface (*Claude-prompt invocation*) at the contract layer, even though they differ at the dispatch mechanism layer. Slicing by mechanism risks abstraction leak when Claude Code changes how it dispatches.

### Technical Constraints & Dependencies

**Hard constraints from PRD (non-negotiable):**

- **Language:** Python 3.10+ only (NFR-COMPAT-1). CI matrix tests 3.10 / 3.11 / 3.12 / 3.13.
- **Build/distribution:** Wheel-only, hatchling (PEP 517), PyPI trusted publishing.
- **Runtime dependencies:** Python + `claude` + `git` + `gh` (optional). No SQLite, Redis, message broker, Docker.
- **Dashboard stack:** stdlib `http.server` + single-page HTML + vanilla JS + Chart.js (vendored). No npm, no webpack, no React, no build step.
- **State storage:** Local filesystem; `state.json` (atomic) + `journal.log` (append-only JSONL) + canonical SDLC folders + `.claude/`.
- **External integrations:** Claude Code subprocess, Git subprocess (read-only `git log` for DORA + explicit branch/commit/push), GitHub via `gh` CLI shim.
- **Outbound HTTP:** none from the framework process itself; the AIRuntime delegate (`claude` binary) is permitted to make network calls (privacy-policy phrasing must reflect this distinction — the framework does not initiate network IO; the runtime delegate may).

**Type & quality discipline:**

- `mypy --strict`, `from __future__ import annotations`, `ruff` lint + format clean.
- Hard caps: ≤ 400 LOC/file, ≤ 50 LOC/function, complexity ≤ 8.
- Test pyramid: unit + integration + nightly E2E + property tests + benchmark.
- Coverage: ≥ 90% engine, ≥ 80% workflow YAMLs, ≥ 1 property test per state machine.

**Wire-format contracts (versioned, even though the "internal Python API" is not).**

The PRD declares the internal Python API non-versioned in v1, but the following five contracts cross run / process / version boundaries and **must** be schema-versioned with explicit migration paths:

1. **`resume_token`** — encodes "you are here" state across sessions; consumed by dashboard, `sdlc status`, auto-loop resumption.
2. **`journal_entry`** — JSONL schema; replay correctness depends on a schema-version field.
3. **`specialist_frontmatter`** — markdown YAML on each of ~25 agents; engine field-additions must be backward-compatible or fail loud.
4. **`workflow_yaml`** — DSL schema; reachability + termination + disjoint-writes static check.
5. **`hook_payload`** — both engine-side and Claude-Code PreToolUse; ordering and idempotency contract.

These five are the framework's wire format. Conflating them with "internal Python API" hides the migration surface; treating them as first-class versioned contracts prevents replay divergence in v0.5+.

### Cross-Cutting Concerns Identified

Cross-cutting concerns are organised into three groups: **integrity primitives** (the load-bearing invariants), **architectural concerns** (mechanisms with cross-module reach), and **runtime / operational concerns** (originally absent from the framing, surfaced by panel review).

#### A. Integrity primitives — temporal truthfulness across crash and replay

1. **Temporal integrity** *(merges what was originally "audit chain" + "atomic state writes")*. The journal and state file are not two separate concerns — they are one CRDT-lite structure: the journal is the source of truth, state is its projection. Together they guarantee that history is not retroactively rewritten and current state is never half-written. Hash-validated signoffs are *tamper-evident*, not *tamper-proof*: there is no signing key, so a determined local actor can rewrite history if they also rewrite all hashes. Acceptable for internal-first single-actor use; must be named explicitly so downstream adopters do not over-claim.

#### B. Architectural concerns — mechanisms with cross-module reach

2. **AIRuntime abstraction.** Load-bearing only if exercised by ≥ 1 non-Claude implementation in v1. PRD specifies a Mock runtime for the abstraction-adequacy test in CI; this is the minimum discipline. Without it, the abstraction is aspirational and will leak Claude-specific assumptions (streaming semantics, tool-call format, context window management, retry policy) into the engine.
3. **Phase gating.** Engine-side pre-write hook + Claude-Code PreToolUse (dual enforcement). Fault isolation between the two layers is not implicit: if engine-side raises, what is the state of the in-flight workflow? If Claude-Code-side rejects, does the engine roll back the journal? The contract must be explicit, not discovered.
4. **Workflow YAML as a typed program** *(broader than the original "disjoint-writes static check")*. Disjoint writes is one property; reachability (no dead phase), termination (every loop has a STOP), and schema-state compatibility are siblings. Architecturally this is a static-analysis pipeline over the workflow DSL, not a single check.
5. **Adopt-mode invariant.** Source-untouched, but the test must be `git status --porcelain` empty + tree-hash equality, not `git diff` text. Diff misses mtime, mode, xattr, symlink target.
6. **Schema migration discipline.** Idempotent + backed-up + fixture-tested. Covers state and journal; does **not** cover the five wire-format contracts above (those need their own versioning track).
7. **Auto-loop control** *(split from the original "STOP taxonomy" into two concerns)*.
   - **7a. Termination safety** — framework halts when needed; STOP triggers have total ordering so no two triggers race to fire on the same tick without a deterministic resolution. Adding an 8th trigger later is cheap only if total ordering is established now.
   - **7b. Resumption fidelity** — after STOP, the framework resumes from the exact same point with the same context. This is a state-serialization concern (resume token + replay invariant), not a control-loop concern.
8. **Secret hygiene** — strengthened: per-surface redaction strategy. Secrets can appear in agent prompt, tool output, journal entry, or dashboard render. Each surface has a different redaction implementation; the policy is the same.

#### C. Runtime and operational concerns — surfaced by panel review

9. **Concurrency & process model.** Single-process or multi-process engine? Parallel agent dispatch implies the latter. Then: deadlock detection, fairness, recovery-of-recovery (kill happens during the recovery handler), and FD discipline for `flock`.
10. **Time and clock discipline.** Audit chain assumes total ordering; total ordering is not free. Decision: monotonic clock (`time.monotonic`) for ordering; wall-clock (`time.time`) only for human-readable timestamps; Lamport-style counter on journal entries to survive NTP adjustments.
11. **Resource budget and backpressure.** Auto-loop has 7 STOP triggers; none cover resource exhaustion (token spend, disk, memory, FD leaks). An eighth trigger is implied by NFR but unnamed. Plus: backpressure on parallel-agent fan-out under runtime cap.
12. **Observability for debug — separate from audit.** Audit chain serves correctness/compliance; observability serves the solo builder debugging at 2 AM. Distinct mechanisms: structured event log with per-loop correlation ID; deterministic replay from event log; heartbeat + per-trigger STOP counter; state-diff visualizer between snapshots. Coverage % does not substitute for debug observability.
13. **Workflow trust boundary and supply chain.** Two attack surfaces: (a) framework distribution itself — `pip install` runs arbitrary code; wheel signing and reproducible build are open questions; (b) workflow YAML as untrusted input — once the framework has external users (PyPI distribution forces this even in internal-first posture), workflow definitions become an injection vector. Capability-based execution model for workflows is a candidate; at minimum, the trust boundary must be named.
14. **Wire-format contracts** *(see Technical Constraints above)*. Five formats versioned independently of the internal Python API.
15. **Specialist validation pipeline.** ~25 markdown specialists × frontmatter cross-references to skills/workflows/commands = guaranteed drift without a build-time validator. Required: pre-commit + CI step that parses every specialist, validates frontmatter against the contract, cross-refs skill/workflow/command IDs, and fails the wheel build on any unresolved reference.
16. **Provenance / artifact lineage.** Distinct from audit chain: audit traces *events* (mutations, dispatches, signoffs); provenance traces *artifacts* (this file's lineage from raw idea → epic → story → task → PR → merged commit). The two graphs share data but answer different questions. Adopt-mode is one expression of provenance (`imported-from-existing` is a lineage tag); Diep's onboarding via dashboard is another (she needs to see "who and what produced this").
17. **Self-hosting compatibility / forward-build invariant.** The framework eats its own dog food: framework v_N must build framework v_{N+1} even when v_{N+1} changes schema, hooks, or agent contract. This is the compiler-bootstrap problem applied to an SDLC framework. Schema migration handles data; this concern handles tooling self-compatibility (the v_N agents must produce v_{N+1}-valid artifacts during the transition window).
18. **Canary substitute for the dogfood delay loop.** Internal-first removes the external-user canary that "normal" tools rely on. Regressions can hide for a sprint or more before the solo builder hits them. Substitute mechanisms: synthetic stress (replay over fixture corpus on every release), forced-fault drills (mandate a chaos exercise per release), explicit dogfood-version separation (current build runs the previous build's test suite, not its own).

### Verification Strengthening Notes

The PRD's verification strategy is broadly correct but needs sharpening on six points before substrate work begins:

- **Hash validator differential test.** Property tests with hypothesis prove the validator consistent with itself; they do not prove it semantically correct. Add a golden corpus: 3+ hand-written `(input, expected_hash)` pairs covering Unicode combining characters, nested objects with shadow-named keys, and empty inputs. Any implementation change that alters a golden hash fails CI.
- **Chaos test cardinality.** "Kill at 10 distinct points" is under-specified. Principled count: count the atomic boundaries `n` in the signoff-write protocol, then `kill_points = 2n − 1` for inter-step kills, plus a recovery-of-recovery layer. Tests must distinguish process-kill (page cache preserved) from OS-crash simulation (page cache lost — exposes missing `fsync` on directory after `rename`).
- **Journal replay invariant.** Add property: `replay(journal[0:k]) == state_at_step_k` for every k. Catches replay-divergence from semantic schema drift, which the existing append-only property cannot detect.
- **Encoding boundary.** Property test that agent output containing lone surrogates / NFC-vs-NFD differences / mixed line endings does not corrupt state. Without this, a single agent return value can produce invalid JSON that passes pydantic on write and fails on read.
- **Filesystem case-sensitivity.** Required in CI matrix: macOS (case-insensitive APFS) + Linux (case-sensitive ext4) + Windows-WSL2 (case-sensitive). One specialist filename mismatch will pass dogfood and fail public CI.
- **Adopt-mode invariant strengthening.** Replace `git diff` empty-check with `git status --porcelain` empty + tree-hash equality before/after `sdlc init --adopt`.

---

## Starter Template Evaluation

### Primary Technology Domain

Python library + CLI tool distributed via PyPI — opinionated framework for AI-augmented SDLC governance. The PRD has pre-locked the tooling stack (Python 3.10+, hatchling, pytest + hypothesis, mypy --strict, ruff, mkdocs, GitHub Actions trusted publishing). The role of a "starter template" is therefore not to make architectural decisions for us — those are already made — but to provide unopinionated bootstrap scaffolding so the first day of v0.2 implementation is not spent writing `pyproject.toml` from scratch.

### Starter Options Considered

| Option | Verdict | Rationale |
|---|---|---|
| `uv init --package --build-backend hatchling` (Astral) | **Selected** | Minimal opinion; hatchling-compatible; reproducible dev env via `uv.lock`; fast; ergonomic for solo build |
| `hatch new` (Hatchling) | Runner-up | Native to hatchling but produces a smaller skeleton and no lockfile management |
| `cookiecutter-pypackage` (audreyfeldroy) | Rejected | Setuptools-era; ships Sphinx/tox/bumpversion that conflict with mkdocs/ruff/hatchling stack |
| `python-blueprint` (johnthagen) | Rejected | Strongly opinionated; ships Dockerfile (PRD specifies no Docker), pre-baked dependency choices that would need to be un-picked |
| Hand-craft from scratch | Considered viable but slower | Aligns with PRD's "ADR for every load-bearing decision" but yields no time savings vs. `uv init` for the unopinionated portion |

### Selected Starter: `uv` (Astral) with hatchling build backend

**Rationale for selection:**

1. The PRD has pre-locked the architecture-significant tooling (build backend, language version, test framework, linter, type checker, doc generator, distribution channel). A heavyweight starter would force un-picking opinions, not save work.
2. `uv init` produces only the unopinionated portion (pyproject.toml shell, src layout, tests directory placeholder). Every load-bearing choice — ruff config, mypy strict mode, pytest configuration, package_data layout for agents/skills/commands/dashboard/workflows, GitHub Actions workflows, mkdocs setup, pre-commit config — is hand-crafted and recorded as an ADR per NFR-MAINT-5.
3. `uv`'s reproducible lockfile (`uv.lock`) provides dev-environment consistency that matters for a solo 12-week build where context loss across sessions is a known risk (Resource Risk R4).
4. `uv` is build-backend-neutral; selecting `hatchling` honours the PRD constraint without ceremony.

**Initialization Command:**

```bash
uv init --package --build-backend hatchling --python ">=3.10" sdlc-framework
```

**What this gets us (provided by `uv init`):**

- `pyproject.toml` with `[build-system] requires = ["hatchling"]`
- `src/sdlc_framework/__init__.py` skeleton (note: PRD names the package `sdlc`; rename on first commit)
- `tests/` placeholder directory
- `.python-version` file
- `README.md` skeleton
- `.gitignore` for Python projects
- `uv.lock` (created on first `uv sync`)

**What we hand-craft afterwards (each as a documented ADR):**

| Item | ADR scope |
|---|---|
| `pyproject.toml` `[project]` metadata, dependencies, optional-dependencies, console scripts | ADR-001 |
| `[tool.ruff]` lint + format config (≤400 LOC/file, complexity ≤8) | ADR-002 |
| `[tool.mypy]` strict mode, `from __future__ import annotations` enforcement | ADR-003 |
| `[tool.pytest.ini_options]` + `[tool.coverage.run]` (≥90% engine / ≥80% workflows) | ADR-004 |
| `[tool.hatch.build]` `package_data` for `agents/`, `skills/`, `commands/`, `dashboard/`, `workflows/`, `memory/` | ADR-005 |
| GitHub Actions `ci.yml` (lint → type → unit → integration on PR) | ADR-006 |
| GitHub Actions `e2e.yml` (nightly E2E against real Claude Code) | ADR-007 |
| GitHub Actions `release.yml` (PyPI trusted publishing on tag) | ADR-008 |
| GitHub Actions `docs.yml` (mkdocs → GitHub Pages on push to main) | ADR-009 |
| `.pre-commit-config.yaml` (ruff + mypy + specialist-validator hook) | ADR-010 |
| `mkdocs.yml` + `docs/` skeleton (architecture overview + numbered ADR log) | ADR-011 |
| `src/sdlc/` directory layout (engine, dispatcher, state, journal, etc. — see Module Specification section) | ADR-012 |

**Architectural decisions provided by the starter (versus hand-crafted):**

| Decision | Provided by starter | Hand-crafted |
|---|---|---|
| Language: Python 3.10+ | ✓ (via `--python ">=3.10"`) |  |
| Build backend: hatchling | ✓ (via `--build-backend hatchling`) |  |
| Project layout: src/ | ✓ (via `--package`) |  |
| Dependency lockfile | ✓ (via `uv.lock`) |  |
| Type checking discipline (mypy --strict) |  | ✓ (ADR-003) |
| Lint/format (ruff with hard caps) |  | ✓ (ADR-002) |
| Test framework + coverage gates |  | ✓ (ADR-004) |
| `package_data` payload structure |  | ✓ (ADR-005) |
| CI/CD pipelines |  | ✓ (ADR-006–009) |
| Documentation system (mkdocs) |  | ✓ (ADR-011) |
| Pre-commit hooks |  | ✓ (ADR-010) |
| Module layout (engine/dispatcher/state/journal/...) |  | ✓ (ADR-012, refined in Module Specification section) |

**Note:** Project initialization using this command is the **first implementation story** of milestone v0.2 (week 2). The hand-crafted scaffolding (ADR-001 through ADR-012 above) constitutes the remainder of v0.2 setup work, before the first specialist agent or workflow YAML is written.

---

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (block implementation if not made):**

- **A1 — Engine concurrency / process model:** single engine process + subprocess-per-agent dispatch.
- **A3 — Workflow execution paradigm:** hybrid sync step-machine + event-sourced read-side via journal.
- **B5 — State as projection of journal:** journal is source of truth; `state.json` is a cached projection.
- **C1 — AIRuntime interface:** async dispatch returning `AgentResult` (output text + tool calls + token counts), no streaming in v1.
- **C2 — Mock AIRuntime strategy:** deterministic YAML-driven generator (`tests/fixtures/mock_responses/*.yaml`), keyed by `(workflow_step, prompt_hash)`.
- **D1 — Hook ordering & idempotency:** sequential, declared in registry; every hook must be safe to retry.

**Important Decisions (shape architecture significantly):**

- A2 (parallel agent dispatch via `asyncio.gather` + Semaphore), A4 (auto-loop pure function of disk state), B1 (single `state.json` for v1), B2 (per-file flock granularity), B3 (flat JSONL journal record with `monotonic_seq`), B4 (full replay from journal[0] for v1), C3 (explicit specialist manifest), D2 (unified `HookPayload` pydantic model across both hook layers), D3 (workflow YAML as trusted input in v1), E1 (micro-router for dashboard), E2 (3-second polling with ETag/304), E3 (three observability streams), E4 (on-demand DORA with 30s cache), F1 (flat `package_data`), F2 (auto-discovered migrations), F3 (per-contract wire-format versioning).

**Deferred to Growth (v1.x) or later:**

- State sharding (B1) — when projects exceed ~1000 tasks.
- Snapshot + delta replay caching (B4) — optimization, not correctness.
- AIRuntime streaming (C1) — defer until a workflow needs it.
- Capability-restricted workflow execution (D3) — graduate when external workflow authors appear.
- SSE / long-polling for dashboard (E2) — graduate if 3-second polling causes measurable pain.
- Snapshot caching for DORA (E4) — only if compute exceeds 30s cache window.

### Category A — Process & Execution Model

| ID | Decision | Choice | Rationale | Affects |
|---|---|---|---|---|
| **A1** | Engine concurrency / process model | Single engine process + subprocess-per-agent for `claude` dispatch | Vendor boundary clean; engine owns state/journal/lock; matches PRD's "no SQLite/Redis" constraint; avoids in-process LLM client lifecycle | `engine/`, `concurrency/`, `runtime/claude.py` |
| **A2** | Parallel agent dispatch primitive | `asyncio.gather` with `asyncio.Semaphore(max_parallel_agents)` | PRD-named (`asyncio.gather`); Python 3.10 floor precludes `TaskGroup` (3.11+); `max_parallel_agents` config drives Semaphore | `dispatcher/`, `runtime/` |
| **A3** | Workflow execution paradigm | Hybrid: synchronous step-machine + event-sourced read-side via journal | Sync step-machine simple for solo-build; every step transition produces a journal entry; replay reconstructs state without re-invoking AIRuntime | `engine/`, `journal/`, `state/` |
| **A4** | Auto-loop iteration model | Pure function of disk state — `scan() → dispatch_next() → STOP_check()` per iteration; no in-memory continuation | PRD §NFR-REL-5 specified; crash-and-resume = re-run `/sdlc-auto`; eliminates entire class of in-memory bugs | `engine/auto_loop.py` |

### Category B — State, Journal & Replay

| ID | Decision | Choice | Rationale | Affects |
|---|---|---|---|---|
| **B1** | State storage layout | Single `state.json` for v1; sharding deferred to v1.x | ~5MB JSON for 1000-task project (PRD-named threshold); atomic write trivial; sharding adds operational complexity not yet warranted | `state/`, `scanner/` |
| **B2** | Atomic write lock granularity | Per-file flock (`state.json.lock`, `journal.log.lock`) | Avoids serialization bottleneck for dashboard reader (state-only access); `concurrency/locks.py` registry tracks all locks for FD discipline | `state/`, `journal/`, `concurrency/locks.py` |
| **B3** | Journal record schema (5th wire-format contract) | Flat JSONL with `{schema_version: 1, ts, monotonic_seq, actor, kind, target_id, before_hash, after_hash, payload}` | `monotonic_seq` is Lamport-style counter for total ordering under clock skew; `schema_version` enables migration without journal rewrite | `journal/`, all writers |
| **B4** | Replay model | Full replay from `journal[0]` for v1; snapshot caching deferred | Guarantees property `replay(journal[0:k]) == state_at_step_k` for every k (Murat's added invariant); snapshot caching is optimization, not correctness | `state/rebuild.py`, `journal/reader.py` |
| **B5** | State as primary vs projection | Journal is source of truth; `state.json` is a cached projection of the journal | Aligns with A3 hybrid; `sdlc rebuild-state` (FR35) materially proves the property; atomic state write becomes "atomic projection update", not "atomic SOT update" | `state/`, `journal/`, `engine/scanner.py` |

### Category C — AIRuntime & Dispatcher

| ID | Decision | Choice | Rationale | Affects |
|---|---|---|---|---|
| **C1** | AIRuntime interface shape | Async `await runtime.dispatch(prompt, tools) -> AgentResult` (final string + tool_calls + token counts); no streaming in v1 | Matches A2 (asyncio.gather); streaming complexity unjustified for v1 use cases; `AgentResult` dataclass provides typed return shape | `runtime/abc.py`, `runtime/claude.py`, `runtime/mock.py` |
| **C2** | Mock AIRuntime strategy | Deterministic YAML-driven generator: `MockAIRuntime` reads `tests/fixtures/mock_responses/*.yaml` keyed by `(workflow_step, prompt_hash)` | Forces abstraction adequacy without Claude Code dependency in unit tests; missing fixture = fail-loud; abstraction-adequacy CI gate runs full pipeline against mock | `runtime/mock.py`, `tests/fixtures/`, CI gate |
| **C3** | Specialist registry discovery | Explicit manifest `agents/index.yaml` listing every specialist with metadata | Pairs with specialist validation pipeline (concern #15); fail-loud on missing entry; filesystem walk causes silent skips on rename | `specialists/`, `agents/index.yaml`, validation pipeline |

### Category D — Hooks & Trust Boundaries

| ID | Decision | Choice | Rationale | Affects |
|---|---|---|---|---|
| **D1** | Engine-side hook ordering & idempotency | Sequential execution from declared registry in `pyproject.toml`; `[tool.sdlc.hooks] pre_write = ["naming_validator", "phase_gate"]`; idempotency contract enforced by test | Order = declaration order (no priority/topo-sort needed for v1); every hook must be safe to retry; debuggable for solo build | `hooks/`, `pyproject.toml` |
| **D2** | Hook payload schema (5th wire-format contract) | Pydantic model `HookPayload(schema_version=1, hook_name, target_path, target_kind, content_hash_before, write_intent)`; same envelope across engine-side and Claude-Code PreToolUse via `sdlc hook-check <payload-json>` | One contract, two callers; Claude Code-side hook shells out to engine for enforcement parity | `hooks/payload.py`, `cli/hook_check.py`, `.claude/hooks/` |
| **D3** | Workflow YAML trust model | v1 = schema-validate-only (treat workflow YAML as trusted input); capability-restricted execution graduated to v1.x roadmap | Internal-first = single-actor trust model in v1; schema validation + disjoint-writes static check sufficient for v1; trust posture re-evaluates when external authors appear | `workflows/loader.py`, ADR-013 (named) |

### Category E — Dashboard, Observability & Telemetry

| ID | Decision | Choice | Rationale | Affects |
|---|---|---|---|---|
| **E1** | HTTP routing approach | Custom micro-router (~30 LOC) with decorator-style registration; routes live in `dashboard/routes/*.py` | Keeps `dashboard/server.py` under 400 LOC cap; no external deps; easier per-route LOC discipline | `dashboard/server.py`, `dashboard/routes/` |
| **E2** | Live update mechanism | 3-second SPA polling with `ETag` + `304 Not Modified` on state.json hash | PRD-named (FR42, journey 4); ETag/304 makes polling cheap; SSE complexity defers to v1.x if measurable pain emerges | `dashboard/routes/state.py`, frontend JS |
| **E3** | Observability streams | Three independent JSONL streams: `journal.log` (audit, state mutations only), `agent_runs.jsonl` (dispatch records, FR-OBS-2), `debug_events.jsonl` (correlation-ID-tagged debug stream — NEW, panel-surfaced) | Explicit separation per concern #12; three retention policies; coverage % does not substitute for debug observability | `journal/`, `telemetry/runs.py`, `telemetry/debug.py` |
| **E4** | DORA computation strategy | On-demand compute with 30-second in-memory cache; reads `git log` + `agent_runs.jsonl` per request | PRD-locked (NFR-PERF-5); simpler than background aggregator; no thread safety concerns | `telemetry/dora.py`, `dashboard/routes/dora.py` |

### Category F — Distribution & Lifecycle

| ID | Decision | Choice | Rationale | Affects |
|---|---|---|---|---|
| **F1** | `package_data` layout | Flat: `src/sdlc/{agents,skills,commands,dashboard,workflows,memory}` | Matches Claude Code install-time copy semantic (`.claude/{agents,commands,skills}`); simpler hatchling wheel build rules | `pyproject.toml`, `src/sdlc/` |
| **F2** | Migration registry mechanism | Auto-discovery via `glob src/sdlc/migrations/v*.py`; CI lint asserts every major version has a corresponding migration | Aligns with FR48 ("framework refuses to start without migration"); auto-discovery is fail-loud on missing version | `migrations/`, CI lint step |
| **F3** | Wire-format versioning approach | Per-contract `schema_version` field on each of 5 contracts (resume_token, journal_entry, specialist_frontmatter, workflow_yaml, hook_payload); each contract evolves independently with its own migration | Enables `resume_token` to evolve without bumping `journal_entry`; aligns with evolutionary independence (Amelia's wire-format insight) | All 5 wire-format pydantic models |

### Decision Impact Analysis

**Implementation sequence (informs Module Specification in step-06):**

1. **v0.2 foundation** (week 2 in PRD calendar): atomic write protocol (B2) → journal append-only (B3) → state projection (B5) → AIRuntime ABC + Mock (C1, C2) → engine scanner + auto-loop skeleton (A4) → hook registry (D1, D2) → wire-format pydantic models (F3) → CLI skeleton (`sdlc init`, `sdlc scan`, `sdlc status`).
2. **v0.3 onward** (week 4+): dispatcher with `asyncio.gather` (A2), workflow YAML loader (D3), specialist registry (C3), dashboard micro-router (E1), three observability streams (E3), DORA computation (E4), migration registry (F2).

**Cross-component dependencies:**

- **A3 + B5 coupling.** Hybrid sync step-machine requires journal-as-SOT; either decision alone is insufficient. Build them together in v0.2 or build neither.
- **C1 + C2 coupling.** AIRuntime interface shape and Mock implementation must co-evolve; the abstraction-adequacy test is the contract that keeps them honest.
- **D1 + D2 coupling.** Hook ordering registry references hook names; hook payload schema must be stable before any hook is written.
- **B3 + F3 coupling.** Journal record schema is one of the 5 wire-format contracts; its `schema_version` field must be the prototype for the other 4.
- **E3 dependency on B3.** `journal.log` is the audit stream; `agent_runs.jsonl` and `debug_events.jsonl` are independent. Splitting them in v0.2 prevents an v0.5 schema migration.

**Decisions that shape the file layout (preview for step-06):**

- B5 (state as projection) → `state/` and `journal/` are sibling modules, neither nested.
- E3 (three observability streams) → `telemetry/{runs,debug,dora}.py` siblings.
- F3 (per-contract versioning) → 5 wire-format models live in their own module (e.g. `contracts/{resume_token,journal_entry,specialist_frontmatter,workflow_yaml,hook_payload}.py`).
- D2 (unified HookPayload) → `hooks/payload.py` is the boundary; engine-side and Claude-Code-side both import from here.
- C2 (deterministic mock) → `tests/fixtures/mock_responses/` is part of the test contract, not throwaway data.

**Open questions (recorded for future ADRs, not blocking implementation):**

1. **Wheel signing / supply chain** (concern #13a) — recorded but no v1 decision. ADR placeholder in `docs/decisions/`.
2. **Workflow YAML capability model** (concern #13b, D3 v1.x escalation) — recorded; trigger condition = first external workflow author.
3. **Auto-loop 8th STOP trigger for resource exhaustion** (concern #11) — recorded; trigger condition = first observed resource-related runaway.
4. **Self-hosting forward-build invariant test** (concern #17) — recorded; trigger condition = first major schema bump.

---

## Implementation Patterns & Consistency Rules

These patterns prevent drift across two distinct populations of agents: (a) AI assistants helping the maintainer build the framework itself (the dogfood loop), and (b) the ~25 specialist agents the framework dispatches at runtime when used. The same patterns apply to both unless noted.

### Pattern Categories Defined

Eleven pattern categories cover the conflict surface: identifier naming, canonical filesystem layout, JSON canonicalization, timestamp and ordering, error handling and logging, atomic write protocol, the five wire-format contract schemas, specialist agent output contract, CLI output conventions, test organization, and code-style rules beyond ruff.

### Identifier Naming Conventions

| Category | Convention | Example |
|---|---|---|
| Phase IDs | `phase-<N>` (1-indexed) | `phase-1` |
| Epic IDs | `EPIC-<kebab-slug>` | `EPIC-stripe-webhook` |
| Story IDs | `<EPIC-id>-S<NN>-<kebab-slug>` (zero-padded) | `EPIC-stripe-webhook-S04-idempotency-handling` |
| Task IDs | `<STORY-id>-T<NN>-<kebab-slug>` (zero-padded) | `EPIC-stripe-webhook-S04-idempotency-handling-T01-redis-key-design` |
| Specialist names | `kebab-case`, matches filename and frontmatter | `requirement-analyst.md` |
| Slash commands | `sdlc-<verb>` | `/sdlc-start`, `/sdlc-signoff` |
| Workflow YAML files | `<slash-command>.yaml` (1:1 with slash command) | `sdlc-start.yaml` |
| Hooks | `snake_case` | `phase_gate`, `naming_validator` |
| Python modules | `snake_case.py` (PEP 8, ruff-enforced) | `auto_loop.py` |
| Python classes | `PascalCase` | `JournalEntry`, `MockAIRuntime` |
| Python functions / vars | `snake_case` | `dispatch_specialist`, `state_hash` |
| Pydantic wire-format models | one canonical PascalCase name per contract | `JournalEntry`, `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec` |
| ADR files | `docs/decisions/ADR-NNN-<kebab-slug>.md` (zero-padded) | `ADR-007-journal-record-schema.md` |
| State backup files | `state.json.pre-migrate-v<N>.json` | `state.json.pre-migrate-v2.json` |

### Canonical Filesystem Layout (within a user's project)

```
.claude/
  state/
    state.json
    state.json.lock
    journal.log
    journal.log.lock
    signoffs/phase-<N>.yaml
    backups/state.json.pre-migrate-v<N>.json
    hook-hashes.json
    adopted-symlinks.json
    adopt-report.json
  agents/<specialist-name>.md
  commands/sdlc-<verb>.md
  skills/sdlc/
  skills/sdlc-phase1/
  skills/sdlc-phase2/
  skills/sdlc-phase3/
  skills/sdlc-production/
  hooks/<hook_name>.py
01-Requirement/
  01-PRODUCT.md
  02-Research/
  03-Clarifications.md
  04-Epics/<EPIC-id>.json
  05-Stories/<EPIC-id>/<STORY-id>.json
  SIGNOFF.md
02-Architecture/
  01-UX/
  02-System/ARCHITECTURE.md
  <sub-track>/
  SIGNOFF.md
03-Implementation/
  tasks/<STORY-id>/<TASK-id>.json
  agent_runs.jsonl
  debug_events.jsonl
```

### Code Style Beyond Ruff

Ruff enforces PEP 8, complexity ≤ 8, and the LOC caps; the rules below are additional and not all checkable by ruff alone (some by custom pre-commit hooks):

- `from __future__ import annotations` is the first non-comment line of every `.py` file.
- No top-level imports in `cli/` modules — defer-import inside command bodies (cold-start budget < 200 ms, NFR-PERF target).
- No `print()` in `engine/`, `dispatcher/`, `state/`, `journal/`, `hooks/`, `runtime/` — use `structlog` instead. CLI output goes through `cli/output.py` only.
- No `time.time()` for ordering decisions — only for human-readable display. Ordering uses `monotonic_seq`.
- No `os.environ[...]` direct access — all env reads go through `config/env.py` allow-list checker.
- No `subprocess.run` outside `runtime/`, `cli/git.py`, `cli/gh.py` — these three are the only modules that may invoke external binaries.
- No `open()` for state / journal writes — use `state/atomic.py` and `journal/writer.py` only (atomic-write protocol mandatory).
- No floats in any state, journal, or signoff field — use `int` (counts) or `str` (decimals).

### JSON Canonicalization Rules

All hashed JSON content (state.json, signoff records, journal entries, artifact frontmatter) is canonicalized before hashing or comparison:

```python
def canonicalize(obj: dict) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
```

Additional rules:

- All string values normalized to **Unicode NFC** (`unicodedata.normalize("NFC", s)`) before serialization.
- No trailing newline on hashed content; one `\n` per line in JSONL files.
- Hash format: `sha256:<64-hex-char>` (prefix-namespaced; never bare hex).
- Floats forbidden in any hashed field — use `int` for counts, `str` for decimals to avoid float-repr ambiguity.

### Timestamp and Ordering Conventions

- **Human-readable timestamps:** ISO 8601 UTC with `Z` suffix, millisecond precision: `2026-05-07T09:42:13.487Z`. Generated via `datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")`.
- **Total ordering:** `monotonic_seq: int` field on every journal entry. Counter is per-project, never decreases, advances atomically with the state mutation that referenced it. Counter lives at `state.json["next_monotonic_seq"]` and is incremented inside the same atomic write.
- Wall-clock from `time.time()` is **never** used for ordering decisions, only for display.
- The journal reader sorts strictly by `monotonic_seq`, never by `ts`.

### Error Handling and Logging

**Exception hierarchy** (`src/sdlc/errors/`):

```
SdlcError                          (root)
├── StateError                     (state.json read/write/validation)
├── JournalError                   (journal append/read/replay)
├── DispatchError                  (agent dispatch / retry exhaustion)
├── HookError                      (hook execution / hook tampering)
├── SchemaError                    (pydantic validation / migration)
├── SignoffError                   (hash drift / approval refusal)
├── AdoptError                     (adopt-mode source-modification attempt)
└── ConfigError                    (missing env / malformed project.yaml)
```

**CLI exit code mapping:**

| Code | Meaning | Caught from |
|---|---|---|
| 0 | Clean success or clean STOP | normal flow |
| 1 | User error (bad args, missing file, bad config) | `ConfigError`, missing CLI args |
| 2 | Framework failure (hash drift, agent retry exhausted, schema violation) | `SignoffError`, `DispatchError`, `SchemaError`, `StateError` |
| 3 | Infrastructure (claude/git/gh missing, lock unavailable, OS error) | `OSError` family, missing external binary |

**Error envelope (`--json` mode):**

```json
{
  "error": {
    "code": "ERR_HASH_DRIFT",
    "message": "human-readable message",
    "details": { "path": "...", "expected_hash": "sha256:...", "actual_hash": "sha256:..." },
    "exit_code": 2
  }
}
```

**Logging:**

- `structlog` configured at `engine/logging.py`; default level `INFO`, `--debug` enables `DEBUG`.
- Structured context fields on every log line: `correlation_id` (auto-generated per loop iteration), `phase`, `target_id`, `actor`.
- Secret sanitization layer in `config/secrets.py` regex-strips known patterns before any log line is emitted.
- Three observability streams (per Decision E3): `journal.log` for audit, `agent_runs.jsonl` for dispatches, `debug_events.jsonl` for correlation-tagged debug events.

### Atomic Write Protocol

Canonical sequence for every `state.json` or signoff write. Any kill between steps must leave the system in a recoverable state.

```
1. acquire flock(<file>.lock)
2. read current <file> + verify content hash matches expected (optimistic concurrency)
3. compute new content
4. write to <file>.tmp
5. fsync(<file>.tmp)
6. rename(<file>.tmp, <file>)            # atomic on POSIX
7. fsync(parent directory)               # critical — survives OS crash, not just process kill
8. append journal entry referencing the mutation (own atomic protocol, separate file)
9. release flock
```

**Recovery semantics:**

- Kill between steps 4–6: discard `.tmp` file on next start; previous `<file>` intact.
- Kill between steps 6–7: rename visible but not durable; reboot may revert. Repeat the operation.
- Kill between steps 7–8: state advanced but journal missing the entry. Engine refuses to start; `sdlc rebuild-state` recovers from journal + last known-good state.

### The Five Wire-Format Contract Schemas

Each contract is versioned independently (Decision F3). Field lists below are the v1 canonical shape.

```python
class JournalEntry(BaseModel):
    schema_version: int = 1
    monotonic_seq: int
    ts: str                    # ISO 8601 UTC with Z, ms precision
    actor: str                 # 'cli', 'engine', 'agent:<name>', 'hook:<name>'
    kind: str                  # 'state_mutation', 'agent_dispatch', 'signoff',
                               # 'bypass_signoff', 'auto_mad_resolve', 'hook_bypass', ...
    target_id: str
    before_hash: str | None    # 'sha256:...' or None for creates
    after_hash: str
    payload: dict              # kind-specific structured payload

class ResumeToken(BaseModel):
    schema_version: int = 1
    phase: int                 # 1, 2, or 3
    cursor: dict               # {epic_id?, story_id?, task_id?, stage?}
    suggested_next_command: str
    state_hash: str            # current state.json hash for staleness detection

class HookPayload(BaseModel):
    schema_version: int = 1
    hook_name: str
    target_path: str
    target_kind: str           # 'epic', 'story', 'task', 'signoff', 'state'
    content_hash_before: str | None
    write_intent: str          # 'create', 'update', 'delete'

class SpecialistFrontmatter(BaseModel):
    schema_version: int = 1
    name: str                  # kebab-case, must match filename
    title: str
    icon: str
    model: str                 # 'opus' | 'sonnet' | 'haiku' | 'inherit'
    tools: list[str]
    read_globs: list[str]
    write_globs: list[str]     # MUST be pairwise disjoint with sibling parallel agents
    description: str

class WorkflowSpec(BaseModel):
    schema_version: int = 1
    name: str
    slash_command: str
    primary_agent: str
    parallel_agents: list[str] = []
    synthesizer_agent: str | None = None
    postconditions: list[str] = []
    write_globs: dict[str, list[str]]   # agent_name → globs
    stop_on_postcondition_failure: bool = True
```

### Specialist Agent Output Contract

Every artifact produced by a specialist agent MUST conform to:

**Frontmatter required fields:**

```yaml
---
schema_version: 1
produced_by: <specialist-name>
produced_at: <ISO 8601 UTC>
inputs_hashes:
  - sha256:<hash of each input artifact>
decision_rationale: |
  1-3 sentence summary of why this artifact has the shape it does,
  citing inputs that drove the decision.
---
```

**Body structure:** per artifact-type schema (PRD shape, Epic shape, Story shape, ADR shape — defined in respective workflow YAMLs).

**Behavioral invariants:**

- **Idempotent writes.** Re-running the specialist on identical inputs produces byte-identical output after canonicalization. This is testable: dispatch the same agent twice in CI; assert post-canonicalization hashes match.
- **No filesystem writes outside declared `write_globs`.** Enforced by the phase-gate hook (Decision D1, D2). Violation = engine refuses to commit the agent's output.
- **No env-var reads outside the framework-wide allow-list** (`SDLC_*`, `CLAUDE_*`) plus the per-specialist explicit allow-list (e.g. `pr-author` declares `GH_TOKEN` in its frontmatter).
- **No outbound HTTP** from specialist code. Specialists are markdown prompts; if a specialist needs network access it must explicitly declare a tool that the engine controls.

### CLI Output Conventions

- Default mode: rich human-readable output via `rich` library (low-noise, color-aware terminal detection).
- `--no-color` flag disables ANSI codes; `NO_COLOR` env var also honoured.
- `--json` flag switches every command to machine-readable JSON output. Schema is stable per major version (versioned alongside the wire-format contracts).
- Every error path supports `--json`; the error envelope above is the canonical shape.
- Exit codes are stable per major version; documented in `cli/exit_codes.py` with constants.

### Test Organization and Naming

```
tests/
  unit/<module-mirror>/test_<module>.py     # mirrors src/sdlc/ structure
  integration/test_<feature>.py             # multi-module flows
  property/test_<invariant>.py              # hypothesis-based invariant tests
  benchmark/test_<perf-target>.py           # pytest-benchmark regression gates
  e2e/fixtures/                             # nightly E2E fixture projects
  e2e/test_<scenario>.py                    # scenario tests over fixtures
  fixtures/mock_responses/                  # MockAIRuntime YAML fixtures
  fixtures/golden_corpus/                   # hash-validator golden corpus
  conftest.py                               # shared fixtures
```

**Test naming:**

- File: `test_<unit-under-test>.py`
- Function: `test_<behavior>_<expected_outcome>` (e.g. `test_atomic_write_survives_kill_between_rename_and_fsync`)
- Property tests: `test_<property>_holds_for_<input-shape>` (e.g. `test_replay_invariant_holds_for_arbitrary_journal`)

### Pattern Enforcement

| Pattern | Enforced by |
|---|---|
| Identifier naming | `naming_validator` engine-side hook + `PreToolUse` Claude-Code-side hook |
| LOC caps + complexity | `ruff` (C901 + custom rules) in pre-commit + CI |
| Type discipline | `mypy --strict` in CI |
| `from __future__` imports | custom pre-commit hook |
| Forbidden imports per module | custom pre-commit hook reading allow-list table |
| JSON canonicalization | `state/atomic.py` and `journal/writer.py` only paths to write — they enforce the protocol |
| Atomic write protocol | property tests + chaos test in CI |
| Disjoint writes between parallel agents | `workflows/loader.py` static check at workflow-load time |
| Specialist frontmatter contract | `scripts/validate_specialists.py` in pre-commit + CI |
| Wire-format schema migration | per-contract tests + CI lint asserting matched migrations |
| No outbound HTTP from framework | network-isolated CI test (NFR-PRIV-1) |

### Pattern Examples

**Good — atomic state mutation:**

```python
async def transition_task_state(
    state: State, task_id: str, new_stage: TaskStage,
) -> State:
    async with file_lock(STATE_LOCK_PATH):
        current = read_state()
        new_state = current.with_task_stage(task_id, new_stage)
        seq = current.next_monotonic_seq
        await write_state_atomic(new_state.with_next_seq(seq + 1))
        await journal.append(
            JournalEntry(
                schema_version=1,
                monotonic_seq=seq,
                ts=utc_now_iso(),
                actor="engine",
                kind="state_mutation",
                target_id=task_id,
                before_hash=current.content_hash(),
                after_hash=new_state.content_hash(),
                payload={"transition": {"to": new_stage.value}},
            )
        )
        return new_state
```

**Anti-pattern — leaks several rules:**

```python
def transition_task_state(state, task_id, new_stage):
    state.tasks[task_id].stage = new_stage  # mutation
    with open("state.json", "w") as f:       # not atomic, no lock
        json.dump(state.dict(), f)            # no canonicalization
    print(f"Moved {task_id} to {new_stage}") # no print in engine
    journal_log(f"{time.time()}: {task_id}") # wall-clock for ordering
```

This anti-pattern violates: mutation discipline, atomic-write protocol, JSON canonicalization, no-print-in-engine, and wall-clock-for-ordering.

---

## Project Structure & Boundaries

This section translates every architectural decision (Step 4), pattern (Step 5), and cross-cutting concern (Step 2) into a concrete repository layout. Every Python module has a one-sentence responsibility, declared dependencies on sibling modules, and a LOC ceiling consistent with the ≤ 400 LOC/file cap. Every functional requirement (FR1–FR52) is mapped to a specific location.

### Complete Project Directory Structure

```text
sdlc-framework/
├── pyproject.toml                          # PEP 621 + hatchling + tool configs (ADR-001)
├── uv.lock                                 # uv-managed lockfile (Decision: starter)
├── .python-version                         # 3.10
├── README.md
├── CLAUDE.md                               # framework-self dogfood guide
├── LICENSE
├── .gitignore
├── .pre-commit-config.yaml                 # ruff + mypy + custom validators (ADR-010)
├── mkdocs.yml                              # ADR-011
│
├── .github/workflows/
│   ├── ci.yml                              # PR: lint → type → unit → integration (ADR-006)
│   ├── e2e.yml                             # nightly E2E with real claude (ADR-007)
│   ├── release.yml                         # PyPI trusted publishing on tag (ADR-008)
│   └── docs.yml                            # mkdocs → GH Pages on push to main (ADR-009)
│
├── src/sdlc/                               # the package; entry imported by CLI script
│   ├── __init__.py                         # version, narrow public re-exports
│   │
│   ├── cli/                                # console script `sdlc` + Claude-Code shells
│   │   ├── main.py                         # Typer app entry; defers heavy imports (cold-start NFR)
│   │   ├── output.py                       # rich-based output, --json, --no-color
│   │   ├── exit_codes.py                   # constants
│   │   ├── git.py                          # git subprocess wrapper (read-only `git log` for DORA)
│   │   ├── gh.py                           # gh subprocess wrapper (PR ops)
│   │   ├── hook_check.py                   # `sdlc hook-check <payload>` for Claude PreToolUse
│   │   ├── init.py                         # FR1
│   │   ├── adopt.py                        # FR2 (delegates to adopt/ subsystem)
│   │   ├── scan.py                         # FR3
│   │   ├── replan_cmd.py                   # FR4
│   │   ├── status.py                       # FR44 (resume card)
│   │   ├── dashboard_cmd.py                # FR41 launcher
│   │   ├── trace.py                        # FR33
│   │   ├── replay.py                       # FR34
│   │   ├── rebuild_state.py                # FR35
│   │   ├── trust_hooks.py                  # FR39 trust marker
│   │   ├── unsign.py                       # FR23 (mad-mode reversibility)
│   │   ├── upgrade.py                      # FR48 helper
│   │   ├── logs.py                         # FR45
│   │   └── migrate.py                      # FR49 dispatcher
│   │
│   ├── engine/                             # sync step-machine + auto-loop
│   │   ├── auto_loop.py                    # FR19, NFR-REL-5 (pure function of disk state)
│   │   ├── auto_mad.py                     # FR20 mad-mode driver
│   │   ├── scanner.py                      # FR3 implementation; projection rebuild
│   │   ├── replan.py                       # FR4 implementation
│   │   ├── stop_triggers.py                # FR21 (7 triggers, total ordering — Decision A3/D)
│   │   ├── auto_brainstorm.py              # FR22 panel + synthesizer
│   │   └── logging.py                      # structlog config + correlation IDs
│   │
│   ├── dispatcher/                         # workflow → agent dispatch
│   │   ├── core.py                         # FR25, FR26 (primary + parallel + synth)
│   │   ├── retry.py                        # FR27, NFR-REL-4 (exponential backoff)
│   │   └── postconditions.py               # postcondition validators
│   │
│   ├── runtime/                            # AIRuntime abstraction (Decision C1, C2)
│   │   ├── abc.py                          # AIRuntime ABC + AgentResult dataclass
│   │   ├── claude.py                       # ClaudeAIRuntime (subprocess to `claude` CLI)
│   │   └── mock.py                         # MockAIRuntime (YAML-driven, Decision C2)
│   │
│   ├── workflows/                          # workflow YAML loader + static checker
│   │   ├── loader.py                       # parse + WorkflowSpec validate
│   │   ├── static_check.py                 # disjoint writes + reachability + termination (Concern #4)
│   │   └── registry.py                     # slash-command → WorkflowSpec mapping
│   │
│   ├── specialists/                        # specialist registry + validation
│   │   ├── registry.py                     # reads agents/index.yaml manifest (Decision C3)
│   │   ├── frontmatter.py                  # parse + validate SpecialistFrontmatter
│   │   └── validator.py                    # cross-ref skills/workflows/commands (Concern #15)
│   │
│   ├── state/                              # state.json (cached projection of journal)
│   │   ├── model.py                        # State pydantic model
│   │   ├── atomic.py                       # tmp+rename+flock+fsync protocol (Pattern §6)
│   │   ├── reader.py                       # read with hash verification
│   │   ├── projection.py                   # state = projection(journal) (Decision B5)
│   │   ├── rebuild.py                      # rebuild from journal[0] (FR35)
│   │   └── transitions.py                  # epic/story/task state machines
│   │
│   ├── journal/                            # append-only audit log
│   │   ├── writer.py                       # FR31, atomic append protocol
│   │   ├── reader.py                       # iter sorted by monotonic_seq (Pattern §4)
│   │   └── compactor.py                    # placeholder for v1.x
│   │
│   ├── signoff/                            # hash-validated phase signoff
│   │   ├── hasher.py                       # canonicalize + sha256 (Pattern §3)
│   │   ├── generator.py                    # FR11 (produce SIGNOFF.md draft)
│   │   ├── validator.py                    # FR32 (hash-drift detection)
│   │   └── records.py                      # FR12 (phase-N.yaml read/write)
│   │
│   ├── hooks/                              # engine-side hook system
│   │   ├── payload.py                      # HookPayload pydantic (Decision D2)
│   │   ├── runner.py                       # sequential dispatch from registry (Decision D1)
│   │   ├── tampering.py                    # FR39 hook-hash advisory
│   │   └── builtin/
│   │       ├── naming_validator.py         # FR36
│   │       ├── phase_gate.py               # FR37
│   │       ├── post_write_journal.py       # auto-append journal on artifact writes
│   │       └── post_write_state_refresh.py # auto-refresh state projection
│   │
│   ├── adopt/                              # adopt-mode subsystem
│   │   ├── driver.py                       # FR2 3-pass orchestrator
│   │   ├── detector.py                     # Pass 1: detect existing artifacts
│   │   ├── symlink_offer.py                # Pass 2: interactive symlink mapping
│   │   ├── verifier_marker.py              # Pass 3: imported-from-existing tags
│   │   └── invariant.py                    # NFR-REL-6 (porcelain + tree-hash check)
│   │
│   ├── concurrency/                        # process model primitives
│   │   ├── locks.py                        # flock registry + FD discipline (Decision B2)
│   │   └── subprocess_pool.py              # asyncio Semaphore + subprocess wrapper (Decision A2)
│   │
│   ├── contracts/                          # 5 wire-format pydantic models (Decision F3)
│   │   ├── journal_entry.py                # JournalEntry v1
│   │   ├── resume_token.py                 # ResumeToken v1
│   │   ├── hook_payload.py                 # re-export from hooks/payload.py
│   │   ├── specialist_frontmatter.py       # SpecialistFrontmatter v1
│   │   └── workflow_spec.py                # WorkflowSpec v1
│   │
│   ├── telemetry/                          # observability streams (Decision E3)
│   │   ├── runs.py                         # agent_runs.jsonl writer (NFR-OBS-2)
│   │   ├── debug.py                        # debug_events.jsonl writer (Concern #12)
│   │   ├── dora.py                         # DORA computation + 30s cache (Decision E4)
│   │   └── correlation.py                  # correlation-ID per loop iteration
│   │
│   ├── dashboard/                          # local web dashboard (Decision E1, E2)
│   │   ├── server.py                       # stdlib http.server + micro-router
│   │   ├── router.py                       # decorator-based micro-router (~30 LOC)
│   │   ├── etag.py                         # ETag/304 helper (Decision E2)
│   │   ├── routes/
│   │   │   ├── state.py                    # GET /state.json (with ETag)
│   │   │   ├── dora.py                     # GET /api/dora (FR43)
│   │   │   ├── stops.py                    # GET /api/stops (active STOP banners)
│   │   │   ├── activity.py                 # GET /api/activity (last 50 runs)
│   │   │   ├── resume.py                   # GET /api/resume (resume card, FR42)
│   │   │   ├── signoffs.py                 # GET /api/signoffs
│   │   │   ├── healthz.py                  # GET /healthz
│   │   │   └── kanban.py                   # GET /api/kanban (read-only v1)
│   │   └── static/                         # vanilla JS + Chart.js (vendored)
│   │       ├── index.html
│   │       ├── app.js
│   │       ├── styles.css
│   │       ├── chart.umd.min.js            # vendored Chart.js v4
│   │       └── fonts/                      # Fraunces, JetBrains Mono, Inter (local, no CDN)
│   │
│   ├── config/                             # configuration + env access
│   │   ├── project.py                      # project.yaml loader (FR51)
│   │   ├── env.py                          # env-var allow-list checker (FR52, NFR-SEC-2)
│   │   └── secrets.py                      # secret pattern sanitizer (NFR-SEC-1)
│   │
│   ├── errors/                             # exception hierarchy (Pattern §5)
│   │   └── base.py                         # SdlcError + 8 subclasses
│   │
│   ├── migrations/                         # schema migrations registry (Decision F2)
│   │   └── v1_to_v2.py.example             # placeholder for first major bump
│   │
│   ├── ids/                                # identifier parsing + validation
│   │   ├── parsers.py                      # epic/story/task ID regex + parse
│   │   └── builders.py                     # construct IDs from parts
│   │
│   ├── agents/                             # ~25 specialist markdown files (PRD §FR28)
│   │   ├── index.yaml                      # canonical manifest (Decision C3)
│   │   ├── orchestrator.md
│   │   ├── phase1/                         # 12 specialists
│   │   ├── phase2/                         # 10 specialists
│   │   ├── phase3/                         # 9 specialists
│   │   └── support/                        # 4 support agents
│   │
│   ├── commands/                           # 17 slash command markdown shells
│   │   ├── sdlc-init.md
│   │   ├── sdlc-start.md
│   │   ├── sdlc-research.md
│   │   ├── sdlc-verify.md
│   │   ├── sdlc-epics.md
│   │   ├── sdlc-stories.md
│   │   ├── sdlc-signoff.md
│   │   ├── sdlc-ux.md
│   │   ├── sdlc-architect.md
│   │   ├── sdlc-bootstrap.md
│   │   ├── sdlc-break.md
│   │   ├── sdlc-task.md
│   │   ├── sdlc-next.md
│   │   ├── sdlc-auto.md
│   │   ├── sdlc-auto-mad.md
│   │   ├── sdlc-replan.md
│   │   └── sdlc-status.md
│   │
│   ├── workflows_yaml/                     # workflow YAML files (1:1 with orchestrating commands)
│   │   ├── sdlc-start.yaml
│   │   ├── sdlc-epics.yaml
│   │   ├── sdlc-stories.yaml
│   │   ├── sdlc-ux.yaml
│   │   ├── sdlc-architect.yaml
│   │   └── sdlc-task.yaml
│   │
│   ├── skills/
│   │   ├── sdlc/SKILL.md
│   │   ├── sdlc-phase1/SKILL.md
│   │   ├── sdlc-phase2/SKILL.md
│   │   ├── sdlc-phase3/SKILL.md
│   │   └── sdlc-production/SKILL.md
│   │
│   ├── claude_hooks/                       # hook .py files installed into user .claude/hooks/
│   │   ├── pre_tool_use.py                 # FR40 (Claude-Code-side gate)
│   │   ├── post_write_journal.py
│   │   └── post_write_state_refresh.py
│   │
│   └── memory/                             # CLAUDE.md templates per phase
│       ├── phase1.md
│       ├── phase2.md
│       └── phase3.md
│
├── tests/
│   ├── conftest.py
│   ├── unit/                               # mirrors src/sdlc/ structure
│   ├── integration/
│   │   ├── test_phase1_e2e.py
│   │   ├── test_signoff_validation.py
│   │   ├── test_adopt_mode_invariant.py
│   │   ├── test_auto_loop_resumes.py
│   │   ├── test_phase_gate_enforcement.py
│   │   └── test_secret_hygiene.py
│   ├── property/                           # ≥ 1 per state machine (NFR-MAINT-4)
│   │   ├── test_replay_invariant.py
│   │   ├── test_journal_append_only.py
│   │   ├── test_hash_validator_consistency.py
│   │   └── test_disjoint_writes_static_check.py
│   ├── benchmark/
│   │   ├── test_scan_perf.py               # NFR-PERF-1
│   │   ├── test_dispatch_latency.py        # NFR-PERF-2
│   │   └── test_dashboard_response.py      # NFR-PERF-3
│   ├── chaos/
│   │   ├── test_atomic_write_kill_points.py # 2n-1 + recovery-of-recovery
│   │   └── test_journal_durability.py
│   ├── e2e/
│   │   ├── fixtures/
│   │   │   ├── greenfield_walkthrough/
│   │   │   ├── brownfield_adopt/
│   │   │   └── mad_mode_prototype/
│   │   ├── test_greenfield_pipeline.py
│   │   ├── test_brownfield_adopt.py
│   │   └── test_mad_mode_reversibility.py
│   └── fixtures/
│       ├── mock_responses/                 # MockAIRuntime YAML fixtures (Decision C2)
│       └── golden_corpus/                  # Hash validator golden test (Murat)
│           ├── unicode_combining.json
│           ├── nested_shadow_keys.json
│           └── empty.json
│
├── docs/                                   # mkdocs source
│   ├── index.md
│   ├── architecture-overview.md
│   ├── decisions/                          # ADR log (numbered)
│   │   ├── ADR-001-pyproject-metadata.md
│   │   ├── ADR-002-ruff-config.md
│   │   ├── ADR-003-mypy-strict.md
│   │   ├── ADR-004-pytest-config.md
│   │   ├── ADR-005-package-data-layout.md
│   │   ├── ADR-006-ci-yml.md
│   │   ├── ADR-007-e2e-yml.md
│   │   ├── ADR-008-release-yml.md
│   │   ├── ADR-009-docs-yml.md
│   │   ├── ADR-010-pre-commit-config.md
│   │   ├── ADR-011-mkdocs-setup.md
│   │   ├── ADR-012-module-layout.md
│   │   └── ADR-013-workflow-trust-model-v1.md
│   ├── runbooks/
│   │   ├── recover-from-state-corruption.md
│   │   ├── handle-hash-drift.md
│   │   └── upgrade-major-version.md
│   ├── prompt-library/
│   └── threat-model.md                     # AI-Native Risk Profile
│
└── scripts/
    ├── validate_specialists.py             # CI cross-ref check (Concern #15)
    ├── chaos_test.py                       # parallel kill-points runner
    └── golden_corpus_check.py              # hash validator differential test
```

### Module Specifications

Per-module: responsibility, public API surface, depends-on (sibling modules it may import), forbidden-from (modules it must not import). Reading direction: top of table is leaf-most; bottom is closer to user-facing entry points.

| Module | Responsibility | Public API | Depends on | Forbidden from |
|---|---|---|---|---|
| `errors/` | Exception hierarchy root | `SdlcError` + 8 subclasses | (none) | everything (leaf module) |
| `ids/` | Parse + build canonical IDs | `parse_epic_id`, `build_task_id`, regex constants | `errors/` | (depends only on errors) |
| `contracts/` | 5 wire-format pydantic models | `JournalEntry`, `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec` | `errors/`, `ids/` | engine, dispatcher, cli |
| `config/` | project.yaml + env allow-list + secret sanitization | `load_project_config`, `read_env`, `sanitize` | `errors/`, `contracts/` | engine, dispatcher, cli |
| `concurrency/` | flock registry + asyncio Semaphore | `file_lock`, `BoundedDispatcher` | `errors/` | engine, state, journal |
| `state/` | state.json model + atomic write + projection | `read_state`, `write_state_atomic`, `project_from_journal`, `rebuild_state` | `errors/`, `contracts/`, `concurrency/`, `config/` | engine, dispatcher, runtime, cli |
| `journal/` | append-only JSONL writer + reader | `append`, `iter_entries`, `iter_after` | `errors/`, `contracts/`, `concurrency/`, `config/` | engine, dispatcher, runtime, cli |
| `signoff/` | hash-validated signoff records | `generate_signoff_md`, `validate_signoff`, `write_record`, `compute_artifact_hash` | `errors/`, `contracts/`, `state/`, `journal/` | engine, dispatcher, cli |
| `runtime/` | AIRuntime ABC + Claude impl + Mock impl | `AIRuntime`, `AgentResult`, `ClaudeAIRuntime`, `MockAIRuntime` | `errors/`, `contracts/`, `concurrency/` | engine, dispatcher, state, journal, cli |
| `workflows/` | workflow YAML loader + static checker | `load_workflow`, `validate_workflow`, `WorkflowRegistry` | `errors/`, `contracts/`, `ids/` | engine, dispatcher, runtime |
| `specialists/` | specialist registry + cross-ref validation | `load_registry`, `validate_specialist`, `SpecialistRegistry` | `errors/`, `contracts/`, `workflows/` | engine, dispatcher, runtime |
| `hooks/` | hook payload + sequential runner + tampering detection | `HookPayload`, `run_hook_chain`, `detect_tampering`, builtin hooks | `errors/`, `contracts/`, `state/`, `journal/`, `ids/` | engine, dispatcher, runtime, cli |
| `telemetry/` | three observability streams + DORA | `record_agent_run`, `record_debug_event`, `compute_dora_window`, `correlation_id` | `errors/`, `contracts/`, `journal/` | engine, dispatcher, runtime, cli |
| `dispatcher/` | primary + parallel + synthesizer dispatch | `dispatch`, `dispatch_panel`, retry policy | `errors/`, `runtime/`, `workflows/`, `specialists/`, `state/`, `journal/`, `hooks/`, `telemetry/`, `concurrency/` | engine, cli |
| `engine/` | sync step-machine + auto-loop + STOP triggers + scanner | `auto_loop`, `scanner`, `stop_triggers`, `auto_brainstorm`, `replan` | `errors/`, `state/`, `journal/`, `signoff/`, `dispatcher/`, `hooks/`, `telemetry/`, `workflows/`, `specialists/`, `runtime/` (mock injection only via DI), `config/` | cli |
| `adopt/` | 3-pass detect / symlink offer / verifier marker driver | `run_adopt`, `detect_existing`, `offer_symlinks`, `mark_imported`, `assert_source_untouched` | `errors/`, `state/`, `journal/`, `signoff/`, `config/`, `cli/git` | engine, dispatcher, runtime |
| `dashboard/` | local HTTP server + micro-router + read-only routes + static frontend | `serve`, `router`, route handlers | `errors/`, `state/` (read-only), `journal/` (read-only), `telemetry/`, `signoff/`, `config/` | engine, dispatcher, runtime, hooks, adopt |
| `cli/` | Typer console script + slash command shells | every subcommand | engine, adopt, dashboard, runtime (only mock for tests), config, errors | (top of stack) |

### Architectural Boundaries (Import Rules)

The dependency graph is a strict DAG. Boundaries are enforced by a custom pre-commit hook that parses every file's imports against the table above.

**Layer hierarchy (top depends on lower; never the reverse):**

```
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

**Specific boundary rules:**

1. **`cli/` is the only module that may invoke external binaries** other than `runtime/`. `cli/git.py` and `cli/gh.py` wrap subprocess calls; `runtime/claude.py` is the third permitted subprocess invoker.
2. **`engine/` and `dispatcher/` import `runtime/` only via the `AIRuntime` ABC.** Direct import of `runtime/claude.py` outside `runtime/` is forbidden (enforced by pre-commit).
3. **`state/` and `journal/` are siblings, not parent-child.** Both are leaves of the lower stack. Engine reads via `state.projection`; never imports `journal` and `state` together for read paths — projection is the bridge.
4. **`dashboard/` is read-only** with respect to state and journal. No write API in v1.
5. **`hooks/` does not import `engine/` or `dispatcher/`.** Hooks receive a `HookPayload` and operate; they do not call back into engine internals.
6. **`adopt/` does not import `engine/` or `dispatcher/`.** Adopt initializes empty state; engine handles flow afterward.
7. **`workflows/` and `specialists/` do not import `engine/`, `dispatcher/`, or `runtime/`.** They are pure validators / loaders.
8. **`contracts/`, `ids/`, `config/`, `concurrency/`, `errors/` form the foundation layer.** None imports anything from the upper stack.

### External Integration Points

The framework's only external integrations are subprocess invocations of three binaries; no network calls originate from the framework process itself.

| Integration | Module | Mechanism | Frequency | Failure mode |
|---|---|---|---|---|
| Claude Code AI runtime | `runtime/claude.py` | `subprocess.run(["claude", ...])` | per agent dispatch | `DispatchError` after retry; STOP trigger `agent_failed` |
| Git read (DORA, lineage) | `cli/git.py` | `subprocess.run(["git", "log", ...])` | per `sdlc scan`, per dashboard DORA refresh | Caught; falls back to empty DORA window with banner |
| Git write (branch/commit/push) | `cli/git.py` | `subprocess.run(["git", "checkout"/"commit"/"push"])` | when `pr-author` specialist requests | `DispatchError`; print manual instruction |
| GitHub PRs / CI status | `cli/gh.py` | `subprocess.run(["gh", "pr", ...])` | when `pr-author` specialist requests | Optional integration; falls back to manual instruction if `gh` not installed |
| Filesystem | `state/atomic.py`, `journal/writer.py`, `signoff/records.py` | atomic write protocol (Pattern §6) | continuous | `StateError`/`JournalError`; engine refuses to start if corruption detected |
| **Network (outbound HTTP)** | **none** | **never originates from framework process** | **never** | verified by network-isolated CI test (NFR-PRIV-1) |

### Functional Requirements → File Mapping

| FR # | Capability | Lives in |
|---|---|---|
| FR1 | `sdlc init` (greenfield) | `cli/init.py` |
| FR2 | `sdlc init --adopt` | `cli/adopt.py` + `adopt/driver.py` |
| FR3 | `sdlc scan` | `cli/scan.py` + `engine/scanner.py` |
| FR4 | `sdlc replan --scope` | `cli/replan_cmd.py` + `engine/replan.py` |
| FR5 | refuse on malformed/incompatible state | `state/reader.py` + `cli/migrate.py` |
| FR6 | `/sdlc-start` | `commands/sdlc-start.md` + `workflows_yaml/sdlc-start.yaml` |
| FR7 | `/sdlc-research <topic>` | `commands/sdlc-research.md` |
| FR8 | `/sdlc-verify <artifact>` | `commands/sdlc-verify.md` |
| FR9 | `/sdlc-epics` | `commands/sdlc-epics.md` + `workflows_yaml/sdlc-epics.yaml` |
| FR10 | `/sdlc-stories <EPIC-id>` | `commands/sdlc-stories.md` + `workflows_yaml/sdlc-stories.yaml` |
| FR11 | `/sdlc-signoff` (generate draft) | `signoff/generator.py` |
| FR12 | sign + validate + write canonical record | `signoff/validator.py` + `signoff/records.py` |
| FR13 | `/sdlc-ux` | `commands/sdlc-ux.md` + `workflows_yaml/sdlc-ux.yaml` |
| FR14 | `/sdlc-architect` + dynamic sub-tracks | `commands/sdlc-architect.md` + `workflows_yaml/sdlc-architect.yaml` |
| FR15 | `/sdlc-bootstrap` | `commands/sdlc-bootstrap.md` |
| FR16 | `/sdlc-break <STORY-id>` | `commands/sdlc-break.md` |
| FR17 | `/sdlc-task <TASK-id>` (TDD pipeline) | `commands/sdlc-task.md` + `workflows_yaml/sdlc-task.yaml` |
| FR18 | `/sdlc-next` | `commands/sdlc-next.md` |
| FR19 | `/sdlc-auto` | `commands/sdlc-auto.md` + `engine/auto_loop.py` |
| FR20 | `/sdlc-auto-mad` | `commands/sdlc-auto-mad.md` + `engine/auto_mad.py` |
| FR21 | 7 STOP triggers | `engine/stop_triggers.py` |
| FR22 | auto-brainstorm panel | `engine/auto_brainstorm.py` |
| FR23 | `sdlc unsign --mad-only` | `cli/unsign.py` |
| FR24 | watchdog timeout | `engine/auto_loop.py` |
| FR25–FR29 | dispatcher + AIRuntime | `dispatcher/`, `runtime/` |
| FR30 | atomic state writes | `state/atomic.py` |
| FR31 | append-only journal | `journal/writer.py` |
| FR32 | hash-drift validation | `signoff/validator.py` |
| FR33 | `sdlc trace <task-id>` | `cli/trace.py` |
| FR34 | `sdlc replay <line>` | `cli/replay.py` |
| FR35 | `sdlc rebuild-state` | `cli/rebuild_state.py` + `state/rebuild.py` |
| FR36 | naming validator hook | `hooks/builtin/naming_validator.py` |
| FR37 | phase-gate hook | `hooks/builtin/phase_gate.py` |
| FR38 | `--force-bypass-signoff` flag | `cli/output.py` flag handling + `journal/writer.py` bypass entry |
| FR39 | hook tampering detection | `hooks/tampering.py` |
| FR40 | Claude PreToolUse hook | `claude_hooks/pre_tool_use.py` + `cli/hook_check.py` |
| FR41 | `sdlc dashboard --port` | `cli/dashboard_cmd.py` + `dashboard/server.py` |
| FR42 | dashboard sections | `dashboard/routes/*.py` + `dashboard/static/` |
| FR43 | per-project DORA | `telemetry/dora.py` + `dashboard/routes/dora.py` |
| FR44 | `sdlc status` resume card | `cli/status.py` + `dashboard/routes/resume.py` |
| FR45 | `sdlc logs` | `cli/logs.py` |
| FR46 | read-only HTTP endpoints | `dashboard/routes/state.py`, `dashboard/routes/dora.py` |
| FR47 | PyPI install + `--version` | `pyproject.toml` + `src/sdlc/__init__.py` |
| FR48 | upgrade with major-version refusal | `cli/upgrade.py` + `state/reader.py` schema gate |
| FR49 | `sdlc migrate-vN` | `cli/migrate.py` + `migrations/v*.py` |
| FR50 | `package_data` payloads | `pyproject.toml` `[tool.hatch.build]` |
| FR51 | `project.yaml` overrides | `config/project.py` |
| FR52 | env-var allow-list | `config/env.py` |

### Cross-Cutting Concerns → Module Mapping

| Concern | Owner module(s) |
|---|---|
| 1. Temporal integrity | `state/` + `journal/` + `signoff/` |
| 2. AIRuntime abstraction | `runtime/abc.py` (boundary) + CI test in `tests/integration/` |
| 3. Phase gating | `hooks/builtin/phase_gate.py` + `claude_hooks/pre_tool_use.py` |
| 4. Workflow YAML as typed program | `workflows/static_check.py` |
| 5. Adopt-mode invariant | `adopt/invariant.py` + `tests/integration/test_adopt_mode_invariant.py` |
| 6. Schema migration discipline | `migrations/` + `cli/migrate.py` + `state/reader.py` schema gate |
| 7a. Termination safety | `engine/stop_triggers.py` (total ordering) |
| 7b. Resumption fidelity | `contracts/resume_token.py` + `engine/auto_loop.py` |
| 8. Secret hygiene | `config/secrets.py` (per-surface redaction) |
| 9. Concurrency & process model | `concurrency/` |
| 10. Time and clock discipline | `journal/writer.py` (`monotonic_seq`) + `state/model.py` (`next_monotonic_seq`) |
| 11. Resource budget and backpressure | `concurrency/subprocess_pool.py` (Semaphore) — 8th STOP trigger placeholder |
| 12. Observability for debug | `telemetry/debug.py` + `telemetry/correlation.py` |
| 13. Workflow trust boundary | `workflows/loader.py` (schema-validate, v1 trust) + ADR-013 |
| 14. Wire-format contracts | `contracts/` (5 modules, independently versioned) |
| 15. Specialist validation pipeline | `specialists/validator.py` + `scripts/validate_specialists.py` |
| 16. Provenance / artifact lineage | specialist frontmatter `inputs_hashes` + `cli/trace.py` |
| 17. Self-hosting forward-build invariant | placeholder; first migration triggers test creation |
| 18. Canary substitute | `tests/e2e/fixtures/` corpus + chaos drills in CI |

### Development Workflow Integration

**Local development:**

1. `uv sync` — install deps from `uv.lock`.
2. `uv run sdlc --version` — smoke test.
3. `uv run pytest tests/unit` — unit tests run in seconds.
4. `uv run pytest tests/integration` — integration tests with real filesystem.
5. `uv run pytest tests/property` — property tests via hypothesis.
6. `uv run pre-commit run --all-files` — run all linting / type checking before commit.

**Build and distribution:**

- `uv build` (or `hatch build`) produces `dist/*.whl` per `pyproject.toml`.
- `package_data` ensures `agents/`, `commands/`, `workflows_yaml/`, `skills/`, `claude_hooks/`, `memory/`, and `dashboard/static/` are included.
- GitHub Actions `release.yml` runs on tag push: builds wheel, runs full test suite, publishes via PyPI trusted publishing.

**Self-host (dogfood) layout:**

The framework's own repository, once initialized, has its own `.claude/state/`, `01-Requirement/`, `02-Architecture/`, `03-Implementation/` mirrors. This sits alongside `src/sdlc/` and `tests/`. The dogfood pipeline is documented in `CLAUDE.md` at the repository root.

---

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**

All 22 architectural decisions (Step 4) cohere into a single substrate. The four most critical decision clusters were stress-tested:

1. **Process & runtime cluster** (A1 + A2 + C1) — single engine process, subprocess-per-agent, `asyncio.gather` with `Semaphore`, async `AIRuntime` interface. The execution model is uniform from CLI through dispatcher to runtime: every dispatch is an `await` of a subprocess call, capped by the configured parallelism. No conflict.
2. **Event-sourced state cluster** (A3 + B3 + B4 + B5) — hybrid sync step-machine where each transition produces a journal entry, journal is source of truth, state.json is a cached projection, full replay from journal[0] holds the property `replay(journal[0:k]) == state_at_step_k` for every k. The four decisions are mutually reinforcing: removing any one weakens the other three. No conflict.
3. **Dual-layer hook cluster** (D1 + D2) — sequential hook execution from a declared registry, unified `HookPayload` pydantic model across both engine-side hooks and Claude-Code-side `PreToolUse`. Claude-Code hook shells out to `sdlc hook-check <payload-json>` for parity with engine-side enforcement. No conflict.
4. **Wire-format cluster** (F3 + B3 + D2 + C3) — five wire-format contracts (resume_token, journal_entry, specialist_frontmatter, workflow_yaml, hook_payload) versioned independently with their own pydantic models. `journal_entry` is the prototype; the other four follow its `schema_version` discipline. No conflict.

**Pattern Consistency:**

The 11 pattern categories (Step 5) directly support the architectural decisions: identifier naming + canonical filesystem layout enforce the state structure required by Decision B5; JSON canonicalization + timestamp / ordering rules support the temporal-integrity invariant (Concern #1); the atomic write protocol implements Decision B2's per-file flock granularity; the wire-format schemas are the implementation of Decision F3. No pattern contradicts any decision.

**Structure Alignment:**

The repository tree (Step 6) implements every decision with a concrete file location. The DAG of module dependencies prevents the boundary leaks that the panel review flagged (Step 2): `engine/` cannot import `runtime/claude.py` directly; `dashboard/` cannot import `engine/`; `contracts/` is a leaf module with no upward dependencies; the foundation layer (errors / ids / config / concurrency) underpins all higher layers without back-references. The 8 specific boundary rules (Step 6) are mechanically enforceable by a pre-commit hook parsing imports against the dependency table.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:**

All 52 FRs are mapped to specific files in the FR-to-file table (Step 6). No FR is orphaned; no FR is mapped to a module that does not exist.

| FR area | Coverage |
|---|---|
| Project lifecycle (FR1–FR5) | `cli/{init,adopt,scan,replan_cmd}.py`, `state/reader.py` schema gate |
| Phase orchestration (FR6–FR18) | `commands/sdlc-*.md` + `workflows_yaml/sdlc-*.yaml` + workflow-specific engine paths |
| Auto-mode + STOP triggers (FR19–FR24) | `engine/{auto_loop,auto_mad,stop_triggers,auto_brainstorm}.py`, `cli/unsign.py` |
| Specialist dispatch (FR25–FR29) | `dispatcher/`, `runtime/`, `specialists/`, `workflows/` |
| State + audit chain (FR30–FR35) | `state/`, `journal/`, `signoff/`, `cli/{trace,replay,rebuild_state}.py` |
| Hooks + phase gates (FR36–FR40) | `hooks/builtin/`, `hooks/tampering.py`, `claude_hooks/pre_tool_use.py` |
| Dashboard + status (FR41–FR46) | `dashboard/`, `cli/{status,dashboard_cmd,logs}.py`, `telemetry/` |
| Distribution + migration (FR47–FR50) | `pyproject.toml`, `cli/{upgrade,migrate}.py`, `migrations/` |
| Configuration + secrets (FR51–FR52) | `config/{project,env,secrets}.py` |

**Non-Functional Requirements Coverage:**

All 9 NFR categories (~48 NFRs) are addressed by specific architectural mechanisms (Step 2 NFR table mapped to modules in Step 6).

- **Performance** — lazy imports in `cli/`, projection cache in `state/`, ETag/304 in `dashboard/etag.py`, 30s DORA cache, indexed scanner.
- **Reliability** — atomic write protocol in `state/atomic.py` + `journal/writer.py`; chaos test in `tests/chaos/`; pure-function-of-disk-state auto-loop; full-replay property test.
- **Security** — `config/env.py` allow-list; `config/secrets.py` sanitizer; `hooks/tampering.py`; localhost-only dashboard bind.
- **Privacy** — no outbound HTTP from framework process verified by network-isolated CI test; no telemetry code.
- **Compatibility** — `runtime/abc.py` boundary; `runtime/mock.py` for adequacy test.
- **Observability** — three independent JSONL streams (`journal/`, `telemetry/runs.py`, `telemetry/debug.py`); `cli/trace.py`; per-iteration correlation IDs in `telemetry/correlation.py`.
- **Maintainability** — pre-commit + CI enforces mypy strict, ruff, LOC caps; ADR log discipline.
- **Accessibility** — dashboard WCAG checked via axe-core in CI; STOP banners use color + text; CLI `--no-color`/`--json`.
- **Disaster recovery** — `state/rebuild.py`; migration backup convention.

**Cross-Cutting Concerns Coverage:**

All 18 concerns from Step 2 are mapped to owner modules in Step 6's final table. None is orphaned.

### Implementation Readiness Validation ✅

**Decision Completeness:**

22 architectural decisions documented with rationale, alternatives implicit through option lists, cascading implications named, deferral conditions stated for the 6 v1.x candidates. Critical, important, and deferred decisions are categorised in Step 4's "Decision Priority Analysis" subsection.

**Structure Completeness:**

Every Python module in the source tree has a one-sentence responsibility, declared dependencies on sibling modules, declared forbidden imports, and a public API surface. The DAG is consistent: traversing the dependency table top-to-bottom produces a strict partial order. Test layout mirrors source layout one-to-one. Five content trees (`agents/`, `commands/`, `workflows_yaml/`, `skills/`, `claude_hooks/`, `memory/`) have explicit member files or known-fixed counts.

**Pattern Completeness:**

The 11 pattern categories (Step 5) cover every conflict surface flagged by the panel review (Step 2): identifier naming, filesystem layout, JSON canonicalization, timestamp ordering, error handling, atomic writes, the 5 wire-format schemas, specialist agent output contract, CLI conventions, test organisation, and code style beyond ruff. Each pattern has at least one good example and (where useful) an anti-pattern example.

### Gap Analysis Results

**Critical gaps blocking implementation:** None. The substrate is buildable as specified.

**Important gaps (non-blocking; materialise during the build):**

1. **Workflow YAML detailed grammar beyond `WorkflowSpec`.** The envelope schema is locked; the per-workflow body grammar emerges as actual workflow files are authored in v0.2 (`sdlc-start.yaml`, `sdlc-epics.yaml`, etc.). The static checker (`workflows/static_check.py`) constrains this grammar via reachability + termination + disjoint-writes; the grammar cannot violate those properties without failing CI.
2. **Per-specialist `read_globs` / `write_globs` for ~25 agents.** `agents/index.yaml` is the manifest container; per-specialist contracts are authored as each specialist is implemented (v0.2 → v0.6). The `specialists/validator.py` cross-ref pipeline catches drift.
3. **ADR-001 through ADR-013 content.** Files are identified in `docs/decisions/`. Each ADR is authored at the moment its decision is implemented (`pyproject.toml` work → ADR-001, etc.). The dogfood loop ensures every architectural decision in framework development goes through the same Phase 1/2/3 discipline.
4. **8th STOP trigger for resource exhaustion (Concern #11).** Placeholder; design triggered by first observed runaway in internal pilots.
5. **First migration script `migrations/v1_to_v2.py`.** Placeholder; first major schema bump triggers.
6. **Self-hosting forward-build invariant test (Concern #17).** Placeholder; first major schema bump triggers.

**Minor gaps:**

- Retry timeouts beyond exponential backoff (1s, 4s) — defaults sufficient for v1; revisit if telemetry shows pattern.
- Watchdog default 30-min — PRD-locked; will be referenced at `engine/auto_loop.py` implementation.
- Wheel signing / supply-chain hardening (Concern #13a) — explicit deferred ADR.

### Validation Issues Addressed

No critical issues required resolution during this validation. Important and minor gaps are documented as anticipated implementation work, not architectural deficits.

### Architecture Completeness Checklist

**Requirements Analysis**

- [x] Project context thoroughly analyzed (Step 2: paradigm + 18 concerns + 5 wire-format contracts identified; module count corrected from 12–15 to 25–30; surface model refined to CLI / Claude-prompt / Hooks / State)
- [x] Scale and complexity assessed (HIGH complexity confirmed; ~25–30 Python modules + 5 content trees; 4 user-facing surfaces + 1 implicit state surface)
- [x] Technical constraints identified (Python 3.10+, hatchling wheel-only, no SQLite/Redis/Docker, stdlib http.server + vanilla JS for dashboard, subprocess-only external integration)
- [x] Cross-cutting concerns mapped (18 concerns each owned by a specific module in Step 6's final table)

**Architectural Decisions**

- [x] Critical decisions documented with versions (22 decisions in Step 4 categorised as critical / important / deferred; all dependencies verifiable)
- [x] Technology stack fully specified (uv + hatchling + pydantic v2 + structlog + rich + Typer + pytest + hypothesis + ruff + mypy + mkdocs all locked)
- [x] Integration patterns defined (subprocess-only via three permitted modules; AIRuntime ABC + AgentResult dataclass; HookPayload unified across hook layers)
- [x] Performance considerations addressed (NFR-PERF mapped: lazy imports, ETag/304, projection cache, 30s DORA cache, pytest-benchmark regression gates)

**Implementation Patterns**

- [x] Naming conventions established (Step 5 §1 — 13-row table covers every identifier surface)
- [x] Structure patterns defined (Step 5 §2 + Step 6 — canonical filesystem layout for both framework repo and user project)
- [x] Communication patterns specified (5 wire-format schemas with canonical fields; atomic write protocol; hook payload contract)
- [x] Process patterns documented (8-class exception hierarchy; CLI exit code mapping; error envelope; structured logging conventions; retry policy)

**Project Structure**

- [x] Complete directory structure defined (Step 6 tree — every file or pattern named)
- [x] Component boundaries established (DAG dependency table + 8 specific boundary rules + import-rule enforcement via pre-commit)
- [x] Integration points mapped (5 external integrations + explicit "no outbound HTTP" verified by CI)
- [x] Requirements to structure mapping complete (52 FRs + 18 concerns each mapped to specific modules)

### Architecture Readiness Assessment

**Overall Status:** **READY FOR IMPLEMENTATION**

All 16 checklist items are checked. No critical gaps remain. The architecture covers every PRD requirement (52 FRs, ~48 NFRs), every panel-surfaced concern (18 cross-cutting), and every starter / decision / pattern / structure handoff necessary for v0.2 work to begin.

**Confidence Level:** HIGH

Confidence is grounded in:

- Two independent panel reviews (Step 2 brainstorming via Winston / Murat / Amelia / Dr. Quinn) that flagged real gaps and were absorbed into the framing.
- Decisions presented with options + tradeoffs + rationale, not as pre-baked recommendations.
- Every load-bearing concern (paradigm, temporal integrity, AIRuntime abstraction, dual-layer hooks, workflow trust) named explicitly rather than left implicit.
- Gap analysis distinguishes blocking from non-blocking honestly; no "all green" rubber-stamping.

**Key Strengths:**

1. **Paradigm named and resolved.** Deterministic orchestration of non-deterministic agents is treated as a TRIZ-style contradiction with explicit by-space / by-time / by-trust separation, rather than left as an implicit shape.
2. **Cross-cutting concerns are explicit, owned, and mapped.** All 18 concerns appear in the final structure table with specific module owners; none floats orphaned.
3. **Wire-format contracts are first-class.** Five contracts are independently versioned; the migration surface is small and bounded; per-contract evolution is supported without bumping unrelated contracts.
4. **Three observability streams are separated.** Audit (correctness), agent runs (FR-OBS-2), and debug (correlation-tagged 2 AM debugging) are distinct files, distinct retention, distinct purposes.
5. **Architectural boundaries are mechanically enforceable.** The dependency DAG plus per-module forbidden-imports table is parseable by a pre-commit hook; boundary leaks fail CI rather than emerging at week 6.
6. **Verification strengthening goes beyond PRD.** Golden corpus differential test, principled chaos kill-point cardinality, replay invariant property test, encoding-boundary test, and tree-hash-based adopt-mode invariant are added on top of PRD's verification stack.

**Areas for Future Enhancement (post-substrate):**

- Workflow DSL grammar formalisation (currently constrained by static checker, formalise after first 6 workflow YAMLs are authored).
- Per-specialist read/write contract definitions for the full ~25-agent library.
- Capability-restricted workflow execution (Decision D3 v1.x escalation when external workflow authors appear).
- Wheel signing / reproducible build / supply-chain hardening (Concern #13a deferred ADR).
- Snapshot + delta replay caching (Decision B4 deferred optimisation).
- Multi-tool AIRuntime implementations (v2: Cursor, Copilot, Aider, etc.).

### Implementation Handoff

**AI Agent Guidelines:**

- Follow all architectural decisions exactly as documented in the *Core Architectural Decisions* section. When a decision conflicts with intuition, the decision wins; raise the conflict as an ADR proposal.
- Use implementation patterns consistently across every module (Step 5). Pattern violations fail pre-commit / CI.
- Respect project structure and module boundaries (Step 6). Imports outside the declared dependency table fail pre-commit.
- Refer to this document as the source of architectural truth. Discrepancies between this document and code are bugs in code by default.
- Every load-bearing decision made during implementation is recorded as an ADR in `docs/decisions/` per NFR-MAINT-5.

**First Implementation Priority:**

```bash
uv init --package --build-backend hatchling --python ">=3.10" sdlc-framework
```

Then, in v0.2 sequence:

1. Hand-craft `pyproject.toml` per ADR-001 (metadata, deps, console scripts, hatch package_data).
2. Author `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`, `[tool.coverage.run]` per ADR-002 / ADR-003 / ADR-004.
3. Implement the foundation layer in this order: `errors/` → `ids/` → `contracts/` → `config/` → `concurrency/`.
4. Implement the temporal-integrity substrate: `state/atomic.py` + `journal/writer.py` + `signoff/hasher.py`. Add property tests (`tests/property/test_replay_invariant.py`, `test_journal_append_only.py`) and chaos tests (`tests/chaos/test_atomic_write_kill_points.py`) before moving on.
5. Implement `runtime/abc.py` + `runtime/mock.py` + the abstraction-adequacy test in `tests/integration/`. Defer `runtime/claude.py` until the abstraction passes mock pipeline.
6. Implement `engine/scanner.py` + `engine/auto_loop.py` skeleton against the mock runtime. Verify NFR-REL-5 (pure function of disk state) by killing the loop mid-iteration.
7. Implement `cli/init.py`, `cli/scan.py`, `cli/status.py`. First demonstrable behaviour: `sdlc init && sdlc status` shows "Phase 1, no progress yet."

This sequence follows the dependency DAG and surfaces the highest-risk substrate work (temporal integrity, AIRuntime adequacy) before any feature work begins.

---

_Sections below will be appended as the workflow progresses._
