---
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
filesIncluded:
  prd: /Users/vuonglq01685/Documents/Projects/SDLC-new/SDLC-Framework/_bmad-output/planning-artifacts/prd.md
  architecture: /Users/vuonglq01685/Documents/Projects/SDLC-new/ARCHITECTURE.md
  epics: null
  ux: null
filesIncludedNotes:
  - "PRD: canonical, just completed via bmad-create-prd workflow on 2026-05-07"
  - "Architecture: pre-existing v0.1 draft at parent directory; predates the PRD's strategic decisions (AIRuntime abstraction-from-v1, hash signoff substrate, internal-first positioning) — included for cross-check, expected to be revised post-assessment"
  - "Epics & UX: not yet created — assessment will flag as expected gap, not failure"
date: 2026-05-07
projectName: SDLC-Framework
workflowType: implementation-readiness
---

# Implementation Readiness Assessment Report

**Date:** 2026-05-07
**Project:** SDLC-Framework

## Document Inventory

| Document | Path | Status | Note |
|---|---|---|---|
| PRD | `_bmad-output/planning-artifacts/prd.md` | ✅ Included | Canonical, 912 lines, 12/12 PRD workflow steps complete |
| Architecture | `../ARCHITECTURE.md` (parent dir) | ⚠️ Included as v0.1 draft | Predates PRD's strategic decisions; cross-check expected to surface revision items |
| Epics & Stories | — | ❌ Not yet created | Expected gap — workflow not yet run |
| UX Design | — | ❌ Not yet created | Expected gap — workflow not yet run |

## Discovery Notes

- No duplicate document formats (no whole-vs-sharded conflicts).
- PRD frontmatter records `inputDocuments: [PRODUCT.md, ARCHITECTURE.md]` — confirming both originals were source material during PRD creation.
- Assessment will validate PRD self-consistency (Step 2), check Architecture alignment with PRD (Step 3), and flag the absence of Epics/UX as known gaps to plan for.

## PRD Analysis

### Functional Requirements

The PRD declares the capability contract as 52 FRs in 9 capability areas. Full text in `prd.md` § Functional Requirements.

**Project Lifecycle Management (FR1–FR5).** FR1 `sdlc init` greenfield bootstrap. FR2 `sdlc init --adopt` three-pass brownfield with source-untouched invariant. FR3 idempotent `sdlc scan`. FR4 `sdlc replan --scope=<scope>` with downstream-dirty marking. FR5 framework refuses to run on malformed state with recovery prompt.

**Phase Workflow Orchestration (FR6–FR18).** FR6 `/sdlc-start` Phase 1 init. FR7 `/sdlc-research <topic>`. FR8 `/sdlc-verify <artifact-id>`. FR9 `/sdlc-epics` epic generation. FR10 `/sdlc-stories <EPIC-id>` Given-When-Then. FR11 `/sdlc-signoff <phase>` for phases 1–2. FR12 sign-by-edit + hash validation + canonical record. FR13 `/sdlc-ux`. FR14 `/sdlc-architect` with `requires:` sub-track dispatch. FR15 `/sdlc-bootstrap` greenfield-only. FR16 `/sdlc-break <STORY-id>` JIT. FR17 `/sdlc-task <TASK-id>` 5-stage TDD pipeline. FR18 `/sdlc-next` priority-ranked picker.

**Auto-Mode & STOP Triggers (FR19–FR24).** FR19 `/sdlc-auto`. FR20 `/sdlc-auto-mad` opt-in YOLO. FR21 seven explicit STOP conditions enumerated. FR22 auto-brainstorm dispatch on ambiguity (strategist + technical-researcher + devil-advocate + synthesizer). FR23 `sdlc unsign --mad-only` reversibility. FR24 configurable watchdog timeout (default 30 min).

**Multi-Agent Specialist Dispatch (FR25–FR29).** FR25 primary + parallel specialists with disjoint-writes static check. FR26 synthesizer specialist for overlapping outputs. FR27 retry policy (up to 2 retries, exponential backoff 1s/4s). FR28 ~25 specialist agents shipped as markdown. FR29 runtime-neutral `AIRuntime` interface (Claude Code v1; mock runtime in CI).

**State Persistence & Audit Chain (FR30–FR35).** FR30 atomic state mutations. FR31 append-only journal with full provenance fields. FR32 hash validation refusing approval on drift. FR33 `sdlc trace <task-id>` lineage reconstruction. FR34 `sdlc replay <line-or-range>`. FR35 `sdlc rebuild-state` from journal.

**Hook System & Phase Gates (FR36–FR40).** FR36 naming-validator pre-write hook. FR37 phase-gate pre-write hook. FR38 `--force-bypass-signoff` flag with journaled bypass record. FR39 hook-tampering detection by content hash. FR40 Claude-Code-side `PreToolUse` hook for tool-call enforcement.

**Status Visibility & Dashboard (FR41–FR46).** FR41 `sdlc dashboard --port <N>` localhost SPA. FR42 dashboard sections (masthead, phase tracker, backlog tree, STOP banners, activity feed). FR43 per-project DORA (7d + 30d windows, server-cached 30s). FR44 `sdlc status` resume card. FR45 `sdlc logs` rich tail. FR46 read-only HTTP endpoints (`/state.json`, `/api/dora`).

**Distribution, Versioning & Migration (FR47–FR50).** FR47 `pip install sdlc-framework` Python 3.10+ on macOS/Linux first-class, Windows via WSL2. FR48 upgrade-and-refuse-without-migrate on major-version. FR49 idempotent `sdlc migrate-vN` with state backup. FR50 wheel ships `package_data` payloads (agents, skills, commands, dashboard, workflows, memory).

**Configuration & Secret Hygiene (FR51–FR52).** FR51 `project.yaml` overrides (`max_parallel_agents`, `auto_brainstorm`, `legacy_code_globs`, watchdog). FR52 env-var allow-list (`SDLC_*`, `CLAUDE_*`, `GH_TOKEN` only).

**Total FRs: 52** across 9 capability areas. All FRs use the `[Actor] can [capability]` format with explicit actors (Tech lead / Engineer / Maintainer / PM / User / Framework / Orchestrator).

### Non-Functional Requirements

The PRD declares 48 NFRs across 9 categories, each with a measurable target and a verification method. Full text in `prd.md` § Non-Functional Requirements.

| Category | Count | Range | Representative invariants |
|---|---|---|---|
| Performance | 6 | NFR-PERF-1 … 6 | scan <2s on 200-story project; dispatch <500ms; dashboard <100ms; DORA cached 30s |
| Reliability | 6 | NFR-REL-1 … 6 | 0 state.json corruption; append-only journal; 0 hash-drift false negatives; 2-retry exponential backoff; auto-loop crash-recoverable; adopt-mode source-untouched |
| Security | 7 | NFR-SEC-1 … 7 | 0 secrets in state.json; env-var allow-list; data-vs-instruction prompt boundary; phase-gate tamper-evident; hook-tamper detection; localhost-only dashboard; YAML schema validation |
| Privacy | 4 | NFR-PRIV-1 … 4 | 0 outbound HTTP from framework; 0 telemetry in v1; local-only state; v2+ telemetry requires explicit consent |
| Compatibility | 5 | NFR-COMPAT-1 … 5 | Python 3.10+; macOS/Linux first-class + WSL2; runtime-neutral engine with mock-runtime CI gate; forward-compatible with Claude Code minor versions; refuses on too-old Claude Code |
| Observability | 6 | NFR-OBS-1 … 6 | every mutation journaled; every dispatch in agent_runs.jsonl; trace reconstructs lineage; per-project DORA via /api/dora; STOP banners 1-per-trigger; sdlc logs filter-by-id/agent |
| Maintainability | 6 | NFR-MAINT-1 … 6 | mypy --strict; ruff clean; ≤400 LOC/file, ≤50 LOC/function, complexity ≤8; ≥90% engine coverage / ≥80% workflow coverage; ADRs for load-bearing decisions; conventional commits |
| Accessibility | 5 | NFR-A11Y-1 … 5 | WCAG 2.2 Level A baseline; keyboard-only navigation; severity not color-only; CLI `--no-color` + `--json`; AA explicitly out-of-scope v1 |
| Disaster Recovery | 3 | NFR-DR-1 … 3 | rebuild-state from journal; pre-migration state backup; user owns `.claude/` backup |

**Total NFRs: 48.** Each has a specific target value and a named verification method (CI gate, integration test, chaos test, property test, microbenchmark, manual + Lighthouse, axe-core scan, etc.).

### Additional Requirements

Beyond the FR/NFR tables, the PRD also documents:

- **AI-Native Risk Profile** (§ Domain-Specific Requirements). Seven novel risks tabled with vector / mitigation / residual-risk owner: prompt injection via user text, prompt injection via workflow YAML or hooks, agent cascade failure, state corruption, schema drift, hook arbitrary code execution, secret leakage.
- **Visual Design Constraints** (§ Domain-Specific Requirements). Typography stack (Fraunces / JetBrains Mono / Inter), oklch color tokens, STOP banner visual contract, four signoff visual states, resume card treatment.
- **Innovation Validation Criteria** (§ Innovation & Novel Patterns). Six validation methods with target gates: process-layer differentiation (qualitative pilot interview), `AIRuntime` adequacy test (100% CI pass), hash-validated audit chain (zero false positives/negatives), disjoint-writes catch rate (100% on adversarial fixtures), STOP-trigger coverage (quarterly review), auto-brainstorm pick rate (≥60% target).
- **Required v1 Fixture Set** (§ Developer Tool Specific Requirements). Three runnable fixtures: greenfield walkthrough, brownfield adopt-mode walkthrough, mad-mode prototype walkthrough. Each ships with a README and is exercised by nightly E2E.
- **Migration & Semver Discipline** (§ Developer Tool Specific Requirements). Major-bump triggers explicitly enumerated (state.json schema, slash-command rename, agent path, hook signature, workflow YAML). Migration script contract: idempotent + backed-up.
- **Resolved Strategic Questions** (frontmatter `resolvedStrategicQuestions`). Anthropic-runtime risk → mitigated by `AIRuntime` abstraction. Multi-tool v2 → abstraction-from-v1, not rewrite.
- **PRD Rewrite Map** (frontmatter `prdRewrites`). Six load-bearing changes versus the original `PRODUCT.md` v0.1: vision reframe to internal-first, demote GTM metrics, distribution-as-forcing-function reframe, runtime abstraction promoted from roadmap to v1, fourth failure mode (vendor lock-in), persona hierarchy (Lam primary; Mai/Khanh secondary, non-driving).

### PRD Completeness Assessment (initial)

The PRD is *internally complete* for its intended scope:

- **Capability contract:** 52 FRs covering 9 areas, every actor named, every command pinned. Nothing implicit.
- **Quality contract:** 48 NFRs with measurable targets and verification methods, no subjective adjectives.
- **Strategic posture:** Internal-first declared, vendor risk structurally mitigated, multi-tool roadmap framed as additive (not rewrite).
- **Resource posture:** Solo build, 12-week roadmap declared not-a-commitment, "delay OK / substrate compromise NOT OK" policy explicit.
- **Risk posture:** Tech / market / resource risks each carry mitigation + early-warning signal + fallback.
- **Frontmatter:** Carries machine-readable state for downstream LLM consumption (classification, vision facts, resolved questions, addendums, rewrites, release mode, step log).

**Areas the PRD intentionally defers** (and which the assessment will check downstream artifacts cover):

- Specific persona acceptance criteria beyond Journey-narrative form — to be detailed in Stories.
- Architecture-level technology choices for individual sub-tracks — to be detailed in revised `ARCHITECTURE.md`.
- UX wireframes and design tokens at the pixel level — to be detailed in UX design deliverables.
- DORA absolute targets — defer until v0.2 baseline measurement.
- Auto-loop pick-rate target — defer until v0.5 telemetry data.

These deferrals are *explicit* in the PRD, not gaps.

## Epic Coverage Validation

### Coverage Matrix

| FR Number | PRD Requirement (capability area) | Epic Coverage | Status |
|---|---|---|---|
| FR1–FR5 | Project Lifecycle Management | **NOT FOUND** | ❌ MISSING |
| FR6–FR18 | Phase Workflow Orchestration | **NOT FOUND** | ❌ MISSING |
| FR19–FR24 | Auto-Mode & STOP Triggers | **NOT FOUND** | ❌ MISSING |
| FR25–FR29 | Multi-Agent Specialist Dispatch | **NOT FOUND** | ❌ MISSING |
| FR30–FR35 | State Persistence & Audit Chain | **NOT FOUND** | ❌ MISSING |
| FR36–FR40 | Hook System & Phase Gates | **NOT FOUND** | ❌ MISSING |
| FR41–FR46 | Status Visibility & Dashboard | **NOT FOUND** | ❌ MISSING |
| FR47–FR50 | Distribution, Versioning & Migration | **NOT FOUND** | ❌ MISSING |
| FR51–FR52 | Configuration & Secret Hygiene | **NOT FOUND** | ❌ MISSING |

### Missing Requirements

**All 52 FRs are missing from epic coverage** — but this is an *expected* missing state, not a coverage failure of the PRD.

Reason: The `bmad-create-epics-and-stories` workflow has not yet been run. No epics document exists in `_bmad-output/planning-artifacts/`. The PRD is the *first* completed planning artifact in this project's BMad lineage.

**Recommendation:** Run `bmad-create-epics-and-stories` after Architecture is revised to align with PRD. Suggested epic decomposition (high-level — to be confirmed during the epic workflow):

| Suggested Epic | FRs covered | MVP / Growth | Notes |
|---|---|---|---|
| EPIC-engine-substrate | FR30, FR31, FR32, FR35, NFR-REL-1…6 | MVP | Atomic state, journal, hash signoff, rebuild — *the substrate that the Platform MVP bets on* |
| EPIC-airuntime-abstraction | FR29, NFR-COMPAT-3 | MVP | Runtime-neutral interface + mock implementation — load-bearing for vendor-risk mitigation |
| EPIC-cli-init-and-scan | FR1, FR2, FR3, FR5 | MVP | `sdlc init` (greenfield + adopt) + `sdlc scan` |
| EPIC-phase1-workflow | FR6, FR7, FR8, FR9, FR10, FR11, FR12 | MVP | Phase 1 commands + Phase 1 signoff |
| EPIC-phase2-workflow | FR13, FR14, FR11, FR12 | MVP | Phase 2 commands + Phase 2 signoff (FR11/FR12 cover both signoffs) |
| EPIC-phase3-workflow | FR15, FR16, FR17, FR18 | MVP | Bootstrap, break, task, next |
| EPIC-auto-loop | FR19, FR20, FR21, FR22, FR23, FR24 | MVP | Auto, auto-mad, STOP triggers, auto-brainstorm, watchdog |
| EPIC-orchestrator-and-specialists | FR25, FR26, FR27, FR28 | MVP | Orchestrator + ~25 specialist library |
| EPIC-hooks-and-gates | FR36, FR37, FR38, FR39, FR40 | MVP | Naming, phase-gate, journal, refresh, hook-hash, PreToolUse |
| EPIC-dashboard | FR41, FR42, FR43, FR44, FR45, FR46 | MVP | Local dashboard + DORA + status + logs |
| EPIC-replan-and-recovery | FR4, FR33, FR34 | MVP | Replan, trace, replay |
| EPIC-distribution-and-migration | FR47, FR48, FR49, FR50 | MVP | PyPI install + upgrade + migrate-vN + package_data |
| EPIC-config-and-secret-hygiene | FR51, FR52 | MVP | `project.yaml` + env-var allow-list |
| EPIC-production-track | (Growth-only — Kanban + Bug flow) | Growth (v1.x) | Deferred per Step 3 of PRD |
| EPIC-cross-project-dora-aggregation | (Growth-only) | Growth (v1.x) | Deferred per Step 3 of PRD |

13 MVP epics + 2 Growth epics. The above is a *recommendation*, not an authoritative breakdown — the epic-and-stories workflow will produce the canonical version.

### Coverage Statistics

- **Total PRD FRs:** 52
- **FRs covered in epics:** 0
- **Coverage percentage:** 0%
- **Reason:** Epics document does not yet exist. Expected to reach 100% once `bmad-create-epics-and-stories` workflow runs.

**Status:** Expected gap. Not a PRD defect; a workflow-sequencing artefact.

## UX Alignment Assessment

### UX Document Status

**Not Found.** No standalone UX document in `_bmad-output/planning-artifacts/` (no `*ux*.md` whole or `*ux*/index.md` sharded). The `bmad-create-ux-design` workflow has not yet been run.

### UX Is Implied — Multi-Surface Product

Despite no standalone UX deliverable, the PRD makes clear that UX is a first-class concern. UX requirements are *partially documented inline* in the PRD across multiple sections:

| UX surface | Where in PRD | Detail level |
|---|---|---|
| **CLI** | § Functional Requirements (FR1–FR52); § Developer Tool Specific Requirements § API Surface | Command names, actor mapping, `--help` and `--json` modes — pinned. Output formatting not yet pinned. |
| **Local web dashboard** | § Functional Requirements FR41–FR46; § Domain-Specific Requirements § Visual Design Constraints; § User Journeys 4 and 5 | Sections enumerated (masthead / phase tracker / backlog tree / DORA strip / STOP banners / activity feed); typography stack named (Fraunces / JetBrains Mono / Inter); palette-token approach declared (`oklch`); WCAG 2.2 Level A baseline. **Pixel-level layout, exact color tokens, and component states not yet specified.** |
| **Markdown-as-UI (signoff)** | § Functional Requirements FR11, FR12, FR38; § User Journey 1 (Lam signs Phase 1 SIGNOFF.md); § Domain-Specific Requirements § Visual Design Constraints (4 signoff visual states named) | Pattern described and exemplified; YAML signoff block format pinned (PRODUCT.md / ARCHITECTURE.md). Editor-side affordances (markdown highlighting, hover hints) not specified. |
| **Auto-loop terminal output** | § User Journey 2 (Lam returns to terminal STOP message); § Functional Requirements FR21 (seven STOP triggers) | Tone and structure exemplified ("STOPPED — clarification_needed at … See: … Re-run /sdlc-auto after answering."). Exact message templates per STOP type not yet specified. |

### UX ↔ PRD Alignment

The PRD's user journeys (5 narratives) and Visual Design Constraints together provide enough UX intent to start technical architecture. Specifically:

- ✅ Every dashboard FR (FR41–FR46) maps to a user journey or visual constraint.
- ✅ Every command in the CLI surface has a named actor and named output expectation.
- ✅ Visual contract for the four signoff states (artifact-complete-awaiting-signoff / signoff-drafted-not-approved / signoff-approved / signoff-invalidated-by-replan) is named, even though pixel-level rendering is not.
- ✅ Accessibility baseline (WCAG 2.2 Level A) is declared as v1 commitment; AA explicitly out of scope.

### UX ↔ Architecture Alignment (preliminary, against pre-existing `ARCHITECTURE.md` v0.1)

| Architecture decision | Aligned with PRD UX needs? | Note |
|---|---|---|
| Single-file static dashboard (stdlib `http.server` + vanilla JS + Chart.js) | ✅ Aligns with no-build-step / local-first promise; no React; no Tailwind | OK |
| Dashboard typography stack (Fraunces / JetBrains Mono / Inter) | ⚠️ Mentioned in `ARCHITECTURE.md` §3 row but loaded fonts source not specified | Revised architecture should pin local-font policy (PRD's NFR-PRIV-1 forbids outbound HTTP, so Google Fonts CDN is forbidden) |
| `localhost:8765` server with no auth | ✅ Aligns with PRD NFR-SEC-6 | OK |
| Read-only API in v1 (`/state.json`, `/api/dora`); v2 may add `POST /api/kanban/move` | ✅ Aligns with PRD FR46 | OK |
| Dashboard polls `state.json` every 3s | ✅ Aligns with FR42 / NFR-PERF-4 | OK |
| Chart.js for DORA only | ✅ Aligns with FR43 | OK |

### Warnings

⚠️ **Standalone UX deliverables missing.** The PRD contains UX *intent* but not finalized UX *artifacts*. Items needed before pixel-level implementation can begin:

1. **Pixel-level dashboard wireframes** — Each section (masthead / phase tracker / backlog tree / DORA strip / Kanban-read-only / activity feed / side panel) needs at least one annotated wireframe.
2. **Color token specification** — The PRD names `oklch` paper-tone background and accent colors per phase. Specific values (e.g. `oklch(98% 0 0)`) need to be locked.
3. **STOP banner severity treatment** — Four severities (warning / error / info / success) need visual specification: color, icon, weight, dismissibility behavior.
4. **Phase tracker state cells** — Four signoff visual states need rendering specification (color, icon, hover behavior).
5. **Resume card layout** — "You are here" card needs annotated mockup specifying primary text, secondary text, and the copy-paste-ready next-action command surface.
6. **Auto-loop terminal output templates** — Each of the seven STOP triggers needs a message template.
7. **CLI output formats** — Default human-readable output and `--json` machine-readable schema for each `sdlc <command>`.

⚠️ **Markdown-as-UI signoff editor experience not specified.** When a user opens `SIGNOFF.md` to set `approved: true`, the editor experience is whatever editor they use. The PRD does not specify whether the framework provides editor-side affordances (e.g. linting, schema validation on save). This is a gap the UX workflow should address — even a "no, it's just a markdown file" decision should be documented.

⚠️ **No mobile / tablet design.** PRD § NFR-A11Y / Out-of-Scope explicitly says mobile dashboard is out of scope for v1 (laptop viewports 1280px+). This is consistent and not a defect — flagged here only for traceability.

### Status

UX is **partially documented inline in the PRD** — sufficient to start architecture revision but **not sufficient to start dashboard implementation**. `bmad-create-ux-design` workflow must run before the dashboard story enters Phase 3 implementation.

## Epic Quality Review

### Status

**Not Applicable.** No epics document exists. Quality review of actual epics will be conducted when the `bmad-create-epics-and-stories` workflow runs and produces the epic backlog.

### Forward-Looking Guidance for Epic Creation

Because the recommended epic decomposition from Step 3 is *forward-looking advice* rather than canonical epics, the following observations apply to the *future* epic-and-stories workflow:

#### 🔴 Tension to Resolve: Platform-Substrate Epics vs. "User Value" Doctrine

The classic BMad epic-quality doctrine treats "Setup Database", "Create Models", "API Development", and "Infrastructure Setup" as red flags — they are technical milestones, not user value. The recommended decomposition above includes:

- `EPIC-engine-substrate` (atomic state, journal, hash signoff, rebuild)
- `EPIC-airuntime-abstraction` (runtime-neutral interface)
- `EPIC-hooks-and-gates` (naming hook, phase-gate hook, journal hook, refresh hook)

Strict reading of the doctrine flags these as *technical-milestone* epics. **Resolution path** when the epic-and-stories workflow runs:

| Option | Trade-off |
|---|---|
| **(a)** Keep substrate epics as-is, document the deviation. Justification: this is a *Platform MVP* (declared in PRD § Project Scoping), where the "user" of substrate is the next epic, and end-user value emerges only when the full pipeline works. The PRD explicitly says: "user-visible features are downstream of substrate quality." | Cleanest mapping to PRD's MVP philosophy. Requires `epic-planner` agent to accept this deviation as documented intent. |
| **(b)** Re-frame substrate epics around the *first user-visible value* they deliver. E.g. `EPIC-engine-substrate` → `EPIC-trustworthy-state-engine-for-phase-1` (covers atomic state + journal + hash signoff *together with* Phase 1 commands). | More user-centric naming; trades epic atomicity for narrative coherence. Substrate work spread across multiple value-oriented epics. |
| **(c)** Use a single "foundation" epic explicitly tagged as Epic 0 / Sprint Zero, with the rest of the epics as user-value epics on top of it. | Common pattern for platform products. Honest about substrate being foundational. |

The PRD does not pre-decide this. The epic workflow should pick option (a), (b), or (c) consciously and document the rationale.

#### 🟠 Forward Dependency Risk to Watch

The phase-by-phase nature of the framework creates inherent ordering: Phase 1 commands need engine substrate; Phase 2 commands need Phase 1 to have produced a verified PRODUCT.md fixture; Phase 3 needs Phase 2's ARCHITECTURE.md. When epics are created:

- `EPIC-phase1-workflow` MUST be completable using only the substrate epic outputs — no Phase 2 features needed.
- `EPIC-phase2-workflow` MUST be completable using only Phase 1 outputs (test against a fixture project that has completed Phase 1).
- `EPIC-phase3-workflow` MUST be completable using only Phase 1 + Phase 2 outputs.

This is achievable but requires discipline — *do not* let auto-loop epic creep ahead of phase-1/2/3 epics, because auto-loop integrates all three.

#### 🟡 Greenfield Considerations for Epic 1 / Story 1.1

The framework itself is greenfield (no code yet) and there is no architecture-specified starter template (Python project from `hatchling`, `pyproject.toml`, no major framework). Epic 1 Story 1.1 should be:

> *"Initialize the Python project from `pyproject.toml`, configure `mypy --strict` and `ruff`, set up `pytest` test runner, configure GitHub Actions `ci.yml` workflow."*

This is an explicit setup story (not "build the framework"). Subsequent stories deliver substrate features.

#### 🟡 Story Sizing Note (Solo Build)

The PRD declares solo build over 12 weeks. With ~52 FRs to implement, that is roughly one merged FR per 1.6 days. Combined with TDD discipline, multi-agent reviews, and the framework eating its own dog food, story sizing should target ≤ 4 hours each per the PRD's Task definition (FR16 / FR17). Stories that exceed this should be split.

### Best Practices Compliance Checklist (deferred)

Cannot be evaluated until epics exist. Will be addressed by the post-epic-creation re-run of this assessment:

- [ ] Each epic delivers user value (or is explicitly tagged as foundation with rationale)
- [ ] Epics function independently in the declared order
- [ ] Stories appropriately sized (≤ 4 hours per PRD)
- [ ] No forward dependencies between stories
- [ ] Database / data structures created when first needed (N/A — framework uses JSON files, no DB)
- [ ] Acceptance criteria in Given-When-Then format (FR10 already requires this for stories)
- [ ] Traceability to FRs maintained (each story should reference one or more FR IDs)

### Status Summary

Epic Quality Review is **not executable in this assessment run** because epics don't exist. Forward-looking guidance has been provided so the future `bmad-create-epics-and-stories` workflow makes informed choices about Platform-MVP epic structure, forward-dependency discipline, and starter-template story.

## PRD ↔ Architecture Alignment (against pre-existing v0.1)

The pre-existing `../ARCHITECTURE.md` v0.1 was an input to PRD creation. The PRD that emerged made strategic decisions that the v0.1 architecture document predates. This section enumerates those decisions and flags items the architecture revision must address.

### Architecture decisions still aligned with PRD

These v0.1 decisions match PRD intent and need only documentation updates (not redesign):

| ARCHITECTURE.md §  | Decision | Alignment with PRD |
|---|---|---|
| §3 Tech stack | Python 3.10+, click, pydantic v2, rich, watchdog, hatchling, JSON Schema | ✅ Matches NFR-COMPAT-1, FR47 |
| §3 No SQLite, no Redis, no Node.js | Local-first JSON files | ✅ Matches NFR-PRIV-1, NFR-PRIV-3 |
| §5 Engine components | State, Scanner, Machine, Dispatcher, Orchestrator, Journal, Hooks, Naming, Claude, Signoff, AutoLoop | ✅ Matches FR3, FR25–FR29, FR30–FR40 |
| §7 Multi-agent orchestration via `asyncio.gather` | Parallel dispatch with disjoint-writes assertion at workflow load | ✅ Matches FR25, NFR-REL-3 |
| §11 Single-page HTML dashboard | stdlib `http.server`, vanilla JS, Chart.js, no build step | ✅ Matches FR41–FR46, NFR-PRIV-1 |
| §12 Adopt mode 3-pass | Detection / symlink offer / verifier marking | ✅ Matches FR2, NFR-REL-6 |
| §14 Test pyramid | Unit + integration + nightly E2E + property + performance benchmark | ✅ Matches NFR-MAINT-4 |
| §16 Threat model | User-provided text boundary, hook hash check, secret hygiene | ✅ Matches NFR-SEC-1 through NFR-SEC-7 |
| §17 PyPI distribution | `sdlc-framework`, hatchling, trusted publishing | ✅ Matches FR47, FR50 |

### Architecture decisions that REQUIRE revision in next workflow

The PRD made strategic decisions after the v0.1 architecture was written. The revised architecture must address:

| Required revision | Source in PRD | Architecture v0.1 status |
|---|---|---|
| **Introduce `AIRuntime` abstraction layer as first-class engine boundary** | PRD § Innovation §1; FR29; NFR-COMPAT-3; resolvedStrategicQuestions | ARCHITECTURE.md v0.1 §5 has `Claude wrapper (engine/claude.py)` as a single class — must be re-cast as an interface (`AIRuntime` abstract base) with `ClaudeCodeRuntime` as the concrete v1 implementation, plus a `MockRuntime` for tests. The dispatcher must hold an `AIRuntime` instance, not a `Claude` instance. |
| **Mock-runtime adequacy test as CI gate** | PRD § Innovation Validation; NFR-COMPAT-3 verification | ARCHITECTURE.md v0.1 §14 mentions "mocked Claude Code (`engine/claude.py` swapped for a stub)" but does not define an *adequacy* test. Revision must add an explicit integration test that runs the full pipeline against the mock runtime and asserts artifact validity. |
| **Workflow YAML schema validation as load-time hard-block** | PRD § Innovation §3 (disjoint-writes static check); NFR-SEC-7 | ARCHITECTURE.md v0.1 §7.3 mentions "engine asserts the globs are pairwise disjoint at workflow-load time" — must be expanded to full YAML schema validation including reject-on-malformed and reject-on-instruction-bearing. Pin the schema. |
| **Pin the seven STOP triggers as engine constants** | PRD FR21; FR auto-loop pseudo-code | ARCHITECTURE.md v0.1 §5 lists the auto-loop STOP categories in narrative form; revision must lift them to a typed enum or sealed class so the engine cannot drift. |
| **Hook subprocess isolation explicitly deferred to v1.x with rationale** | PRD § Risk Mitigation T3; § Domain-Specific § Risk Profile (hook execution row) | ARCHITECTURE.md v0.1 §9 says "Hooks today are imported as Python modules into the engine process" with "subprocess for v2" in §20. PRD revises this to v1.x, not v2 — revision must reflect the earlier graduation target. |
| **Dashboard typography served from local fonts (no Google Fonts CDN)** | PRD § Domain-Specific § Visual Design Constraints; NFR-PRIV-1 | ARCHITECTURE.md v0.1 §3 names the typography stack but does not pin font-loading source. Revision must explicitly forbid CDN-loaded fonts and bundle the font files in `package_data` (or document the user-installs-fonts fallback). |
| **Production track explicitly marked as Growth (v1.x), not v1.0** | PRD § Product Scope; § Project Scoping | ARCHITECTURE.md v0.1 covers Production track (§5.4 of `PRODUCT.md` v0.1) as part of v1. Revision must move all Production-track-specific architecture (Kanban interactivity, bug-flow state machine, ticket pipeline) to a "Growth (v1.x)" section. v1 dashboard renders Kanban read-only only. |
| **Internal-first positioning reflected in chapter on documentation** | PRD § Executive Summary; § Project Scoping; § Developer Tool § Documentation Strategy | ARCHITECTURE.md v0.1 §15 has `docs.yml` workflow building mkdocs site; revision must clarify this is for internal audit-chain use, not public marketing site. |
| **Add an `AI Output Provenance` section as forward-looking deliverable** | PRD § Domain-Specific Requirements § AI Output Provenance | ARCHITECTURE.md v0.1 has no provenance-chain section. Revision should add a stub even if the implementation is v1.x. |
| **Update Open Questions list** | PRD frontmatter `resolvedStrategicQuestions` | ARCHITECTURE.md v0.1 §20 lists 5 open ADR questions (async/sync, YAML/Python DSL, hook isolation, state sharding, fan-out caps). Two of these (hook isolation timeline, multi-tool abstraction) now have PRD-level answers and should move from "open" to "decided" with the rationale carried over. |
| **Persona references** | PRD § Executive Summary | ARCHITECTURE.md v0.1 §1 lists "Developer/Tech Lead, PM/Stakeholder, CI System, Reviewer". PRD elevates Lam as primary and demotes Mai/Khanh to non-driving secondary — revised architecture should align persona references. |

### Architecture decisions that are NEW in PRD and need fresh architecture content

The PRD introduced concepts that are not present at all in `ARCHITECTURE.md` v0.1:

| New concept | Source in PRD | What revised architecture must cover |
|---|---|---|
| **`AIRuntime` interface specification** | PRD FR29; § Innovation §1 | Abstract base, method signatures (`dispatch(agent, prompt, context) -> result`, etc.), error-types, retry contract, lifecycle hooks |
| **Mock-runtime test adequacy contract** | PRD § Validation | What "adequate" means: 100% dispatcher-code-path coverage; full pipeline runnable end-to-end; deterministic outputs |
| **Visual contract document (separate from PRD)** | PRD § Visual Design Constraints | Architecture should reference a UX deliverable for pixel-level specs, not duplicate them |
| **`sdlc rebuild-state`** | PRD FR35 | Algorithm: scan `journal.log`, replay events in chronological order, emit a fresh `state.json`; idempotency requirement |
| **`sdlc trust-hooks`** | PRD FR39 | Algorithm: recompute hashes for `.claude/hooks/`, write to `.claude/state/hook-hashes.json`, journal the trust event |
| **`sdlc unsign --mad-only`** | PRD FR23 | Algorithm: scan signoff records, identify `approved_by: ai-mad-mode` entries, revert them, journal the revert |
| **`sdlc trace <task-id>`** | PRD FR33 | Algorithm: filter journal for entries matching task-id ancestor chain, format chronologically |
| **`sdlc replay <line-or-range>`** | PRD FR34 | Algorithm: re-emit a journal event to engine for debug; must not mutate state |
| **CLI `--no-color` and `--json` modes for every command** | PRD NFR-A11Y-4 | Click options shared across all commands; output format contract per command |
| **Pre-migration `state.json` backup** | PRD NFR-DR-2 | File path convention `.claude/state/backups/state.json.pre-migrate-vN.json`; backup-then-mutate ordering |
| **Network-isolation CI test** | PRD NFR-PRIV-1 verification | CI job that runs the framework with network blocked except for declared subprocess calls |

## Summary and Recommendations

### Overall Readiness Status

**PRD: READY** ✅ — Capability contract complete, quality contract complete, strategic posture explicit, internal consistency verified.

**Architecture: NEEDS REVISION** ⚠️ — Pre-existing v0.1 has correct foundations but predates PRD's load-bearing strategic decisions. ~10 items require revision; ~10 new concepts need fresh architecture content.

**Epics: NOT YET CREATED** ⚠️ (expected gap) — `bmad-create-epics-and-stories` workflow has not run.

**UX: PARTIAL — INLINE IN PRD** ⚠️ (expected gap) — PRD documents UX *intent* (5 journeys, visual constraints, accessibility baseline). Standalone UX deliverables (pixel-level wireframes, color tokens, banner/state templates, CLI output schemas) needed before dashboard implementation.

**Implementation Readiness: NOT READY for implementation; READY to proceed to Architecture revision.**

### Critical Issues Requiring Immediate Action

The PRD itself has **zero critical issues**. The implementation-readiness gaps are all sequencing-driven (later workflows in the BMad chain have not yet run). The most load-bearing pending items:

1. 🔴 **Architecture revision** — `ARCHITECTURE.md` v0.1 must be rewritten or substantially revised to reflect PRD's `AIRuntime` abstraction-from-v1 commitment, the elevation of hook subprocess isolation from v2 to v1.x, and the demotion of Production track from v1 to v1.x. Without this, implementation will start from a misaligned design baseline.

2. 🟠 **UX deliverable — pixel-level dashboard spec** — Required before any dashboard story enters Phase 3 implementation. Visual contract is named in the PRD but not specified to the level needed for a developer to render pixels. This is not blocking architecture revision (architecture can stub a "see UX deliverable for visual contract" pointer), but it is blocking dashboard implementation.

3. 🟠 **Epic-and-stories breakdown** — Required before any sprint planning. The recommended decomposition in this report is *guidance only*; canonical breakdown emerges from `bmad-create-epics-and-stories`. Particular tension to resolve in that workflow: how to frame substrate-first epics under Platform MVP doctrine (option a / b / c documented above).

4. 🟡 **DORA baseline measurement during v0.2 pilot** — Not blocking v1 architecture or epic creation, but flagged so that v0.2's pilot project includes baseline DORA capture before v0.5 sets per-project targets.

5. 🟡 **Auto-loop pick-rate telemetry definition** — Not blocking immediate next steps, but the pick-rate metric (PRD § Innovation Validation, target ≥60%) must be operationalized: which file does the user edit, which signal counts as "picked from synthesis", how the journal captures it. To be addressed during v0.5 design.

### Recommended Next Steps (in order)

1. **Run `bmad-create-architecture` workflow** to produce a revised architecture document aligned with PRD. Output: `_bmad-output/planning-artifacts/solution-architecture.md`. This will replace `../ARCHITECTURE.md` v0.1 as the canonical architecture.
2. **Run `bmad-create-ux-design` workflow** to produce dashboard wireframes, color token specification, STOP banner severity treatments, signoff state visual specs, resume card layout, and CLI output format specs. Output: `_bmad-output/planning-artifacts/ux-design.md` (or sharded folder).
3. **Run `bmad-create-epics-and-stories`** to produce the canonical epic backlog. Decide consciously between epic-decomposition options (a)/(b)/(c) for the substrate-vs-user-value tension. Output: `_bmad-output/planning-artifacts/epics-and-stories.md`.
4. **Re-run `bmad-check-implementation-readiness`** after Steps 1–3 to validate that the new artifacts are aligned and that all FR coverage gaps are closed.
5. **Sign Phase 1 of the framework's own SDLC project** (the framework eats its own dog food). At this point the framework's own `01-Requirement/SIGNOFF.md` exists, the planning is hash-validated, and Phase 2 (architecture and design) can be locked.
6. **Begin implementation** following the v0.2 → v0.6 → v1.0 milestone calendar from PRD § Project Scoping § Resource Requirements (with explicit acknowledgement that calendar slip is acceptable, substrate compromise is not).

### Final Note

This assessment found **0 critical issues in the PRD itself**, **1 critical sequencing item (architecture revision)**, **2 high-priority sequencing items (UX deliverables, epic breakdown)**, and **2 lower-priority items deferred until v0.2 / v0.5 pilot data is available**. The PRD is high-quality and ready to drive downstream artifacts. The remaining work is executing the BMad workflow chain — not fixing PRD defects.

Address the critical and high-priority items before declaring the project ready for implementation. These findings can be used to brief the architecture / UX / epic workflows; you may also choose to begin implementation against the existing artifacts at your own risk.

---

**Report generated:** 2026-05-07
**Assessor:** bmad-check-implementation-readiness skill via Claude (Opus 4.7)
**Source artifacts assessed:** `_bmad-output/planning-artifacts/prd.md` (912 lines, canonical) and `../ARCHITECTURE.md` v0.1 (51 KB, pre-existing draft)
**Workflow status:** All 6 assessment steps complete (`step-01-document-discovery` → `step-06-final-assessment`).
