# Specialists Matrix — Canonical Roster

**Status:** Frozen (prep-sprint C5, 2026-05-21). Epic 2A retro action A4 success criterion.
**Source of truth:** This document, paired with `src/sdlc/agents/index.yaml` (machine-readable).
**Update rule (per ADR-026 §4 + retro A4):** Adding or renaming a specialist requires either
(a) an entry here and in `index.yaml`, paired with the implementation PR, OR (b) an ADR.
**Reconciliation reference:** ADR-030 (drafted under prep-sprint C5) records the one-time
amendment that promoted shipped names over PRD §214 declared names.

This matrix is the canonical list referenced from PRD §214 ("~25 markdown specialist agents")
and Architecture.md (§932/933/934 phase-counts). When the prose in those documents disagrees
with this matrix, **this matrix wins**.

---

## 1. Shipped Specialists (40 — verified against `src/sdlc/agents/index.yaml`)

| Name | Phase | File | Story | Notes |
|---|---|---|---|---|
| `product-strategist` | 1 | `phase1/product-strategist.md` | 2A.8 / 2B.8 | Compound prompt PRODUCT.md author; production body authored 2B.8 |
| `technical-researcher` | 1 | `phase1/technical-researcher.md` | 2A.9 / 2B.8 | `/sdlc-research` workhorse; production body authored 2B.8 |
| `devil-advocate` | 1 | `phase1/devil-advocate.md` | 2A.8 / 2B.8 | Adversarial panel role; production body authored 2B.8 |
| `requirement-synthesizer` | 1 | `phase1/requirement-synthesizer.md` | 2A.8 / 2B.8 | Renamed from PRD `synthesizer`; production body authored 2B.8 |
| `artifact-verifier` | 1 | `phase1/artifact-verifier.md` | 2A.10 / 2B.8 | Renamed from PRD `requirement-validator`; production body authored 2B.8 |
| `epic-generator` | 1 | `phase1/epic-generator.md` | 2A.11 / 2B.8 | Renamed from PRD `epic-planner`; production body authored 2B.8 |
| `story-writer` | 1 | `phase1/story-writer.md` | 2A.11 / 2B.8 | Production body authored 2B.8 |
| `phase1-signoff-summarizer` | 1 | `phase1/phase1-signoff-summarizer.md` | 2A.12 / 2B.8 | Renamed from PRD `signoff-summarizer`; registered, not dispatched v1; production body authored 2B.8 |
| `requirement-analyst` | 1 | `phase1/requirement-analyst.md` | 2B.8 | New in 2B.8; analysis pass before synthesis |
| `market-researcher` | 1 | `phase1/market-researcher.md` | 2B.8 | New in 2B.8; pairs with `technical-researcher` |
| `stakeholder-simulator` | 1 | `phase1/stakeholder-simulator.md` | 2B.8 | New in 2B.8; adversarial role, pairs with `devil-advocate` |
| `dependency-mapper` | 1 | `phase1/dependency-mapper.md` | 2B.8 | New in 2B.8; cross-epic dependency tracking |
| `prioritizer` | 1 | `phase1/prioritizer.md` | 2B.8 | New in 2B.8; epic-level priority synthesis |
| `acceptance-criteria-author` | 1 | `phase1/acceptance-criteria-author.md` | 2B.8 | New in 2B.8; BDD-format AC authoring |
| `story-prioritizer` | 1 | `phase1/story-prioritizer.md` | 2B.8 | New in 2B.8; story-level MoSCoW prioritization |
| `ux-designer` | 2 | `phase2/ux-designer.md` | 2A.13 / 2B.9 | Production body authored 2B.9 |
| `ux-reviewer` | 2 | `phase2/ux-reviewer.md` | 2A.13 / 2B.9 | Parallel review role; full production body authored 2B.9 (D3=(a)) |
| `system-architect` | 2 | `phase2/system-architect.md` | 2A.14 / 2B.9 | Renamed from PRD `solution-architect`; production body authored 2B.9 |
| `database-architect` | 2 | `phase2/database-architect.md` | 2A.14 / 2B.9 | Renamed from PRD `data-modeler`; sub-track; production body authored 2B.9 |
| `security-architect` | 2 | `phase2/security-architect.md` | 2A.14 / 2B.9 | Sub-track; production body authored 2B.9 |
| `observability-architect` | 2 | `phase2/observability-architect.md` | 2A.14 / 2B.9 | Sub-track; production body authored 2B.9 |
| `ux-researcher` | 2 | `phase2/ux-researcher.md` | 2B.9 | New in 2B.9; research pass before UX design |
| `design-system-author` | 2 | `phase2/design-system-author.md` | 2B.9 | New in 2B.9; token contract + component inventory |
| `a11y-reviewer` | 2 | `phase2/a11y-reviewer.md` | 2B.9 | New in 2B.9; WCAG audit role; parallel review |
| `infra-architect` | 2 | `phase2/infra-architect.md` | 2B.9 | New in 2B.9; sub-track: deployment topology + cloud resources |
| `devex-architect` | 2 | `phase2/devex-architect.md` | 2B.9 | New in 2B.9; sub-track: CI/CD + toolchain + contributor workflow |
| `api-designer` | 2 | `phase2/api-designer.md` | 2B.9 | New in 2B.9; REST/GraphQL endpoint + schema contract |
| `code-bootstrapper` | 3 | `phase3/code-bootstrapper.md` | 2A.15 | Renamed from PRD `codebase-scaffolder` (Pattern 7 in retro) |
| `task-breaker` | 3 | `phase3/task-breaker.md` | 2A.16 | |
| `test-author` | 3 | `phase3/test-author.md` | 2A.17 | TDD pipeline stage 1 |
| `code-author` | 3 | `phase3/code-author.md` | 2A.17 | Renamed from PRD `developer-agent` |
| `code-reviewer` | 3 | `phase3/code-reviewer.md` | 2A.17 | TDD pipeline stage 3 |
| `pr-author` | 3 | `phase3/pr-author.md` | 2B.10 | GH PR creation; consumes `GH_TOKEN` per PRD NFR-SEC-2; production body authored 2B.10 |
| `tdd-strategist` | 3 | `phase3/tdd-strategist.md` | 2B.10 | Strategy-layer role above `test-author`; production body authored 2B.10 |
| `security-reviewer` | 3 | `phase3/security-reviewer.md` | 2B.10 | Pairs with `code-reviewer` for security-sensitive stories; production body authored 2B.10 |
| `edge-case-reviewer` | 3 | `phase3/edge-case-reviewer.md` | 2B.10 | Pairs with `code-reviewer`; closes Edge Case Hunter layer; production body authored 2B.10 |
| `characterization-author` | 3 | `phase3/characterization-author.md` | 3.8 | Brownfield: dispatched at `pending` for `tdd_strategy=characterization-test`; captures current behavior, emits `tests_status:'green'` (D1=(a) — distinct from the strategy-layer `tdd-strategist`) |
| `clarification-triager` | 0 | `support/clarification-triager.md` | 2B.11 | Cross-cutting; routes open-clarification STOP triggers; registered, not dispatched v1 |
| `agent-failure-recovery` | 0 | `support/agent-failure-recovery.md` | 2B.11 | Cross-cutting; post-retry failure diagnosis and recovery planning; registered, not dispatched v1 |
| `orchestrator-helper` | 0 | `support/orchestrator-helper.md` | 2B.11 | Cross-cutting; complex multi-step workflow consolidation; registered, not dispatched v1 |

---

## 2. Reconciled Renames (drift closed by C5)

The following PRD §214 names were drifted vs the shipped code. Per retro A4, the shipped
name is now canonical:

| PRD §214 name | Shipped name | Phase | Rationale |
|---|---|---|---|
| `codebase-scaffolder` | `code-bootstrapper` | 3 | "Bootstrap" emphasises one-shot init posture; called out as Pattern 7 in Epic 2A retro |
| `developer-agent` | `code-author` | 3 | Aligns with `test-author` / `code-reviewer` naming pattern (role-verb suffix) |
| `signoff-summarizer` | `phase1-signoff-summarizer` | 1 | Explicit phase scope; phase-2/3 may grow analogues later |
| `requirement-validator` | `artifact-verifier` | 1 | Broader scope than just requirements; verifies hash + presence on all phase-1 artifacts |
| `epic-planner` | `epic-generator` | 1 | Closer to actual behaviour (generates the epic file, doesn't plan capacity) |
| `solution-architect` | `system-architect` | 2 | "System" matches Architecture.md vocabulary |
| `data-modeler` | `database-architect` | 2 | Aligns with `*-architect` Phase-2 pattern |
| `synthesizer` (generic) | `requirement-synthesizer` (Phase 1) | 1 | Generic synthesizer role lives in the dispatcher (PRD FR26); the shipped specialist is the Phase-1 requirement-focused variant |
| `signoff-summarizer` (generic) | `phase1-signoff-summarizer` (Phase 1) | 1 | Generic signoff-summarizer reconciled; Phase-1 scoped variant shipped 2B.8; registered, not dispatched v1 — staffed-by-shipped (2B.11 D1=(a)) |

**FR28 support roles staffed-by-shipped (2B.11 D1=(a)):** `devil-advocate` → `phase1/devil-advocate.md` (shipped Phase 1, §1 above); `synthesizer` → `requirement-synthesizer` + dispatcher `synthesizer_agent` field; `signoff-summarizer` → `phase1-signoff-summarizer` (§1 above). No new file authored for these; re-authoring `devil-advocate` under the same `name` would be a registry duplicate-name rejection.

---

## 3. Planned Specialists (0 — all targets shipped as of 2B.11)

All specialists originally planned in this section have been shipped as of Story 2B.11.

> **Phase 1 planned (7) removed**: all 7 authored in Story 2B.8 → §1 Shipped.
>
> **Phase 2 planned (6) removed**: all 6 authored in Story 2B.9 → §1 Shipped (D1=(b)).
>
> **Phase 3 planned (4) removed**: `tdd-strategist`, `security-reviewer`,
> `edge-case-reviewer`, `pr-author` authored in Story 2B.10 → §1 Shipped.
>
> **Phase 3 net-new (1, Story 3.8)**: `characterization-author` — the brownfield
> characterization-test author. The epics named this role `tdd-strategist`, but that
> name was already shipped (2B.10) as an incompatible strategy-layer advisor, so 3.8
> ships a distinct name (D1=(a); see ADR-030 Revision Log).
>
> **Support planned (1) removed**: `clarification-triager` deferred from 2B.8, authored in
> Story 2B.11 → §1 Shipped. `agent-failure-recovery` + `orchestrator-helper` also authored
> in 2B.11 (net-new; not previously in this planned table).

---

## 4. Roster Totals

| Category | Count | Breakdown |
|---|---|---|
| Shipped Phase 1 | 15 | 8 re-authored stubs + 7 net-new (2B.8) |
| Shipped Phase 2 | 12 | 6 re-authored stubs + 6 net-new (2B.9) |
| Shipped Phase 3 | 10 | 5 re-authored stubs + 4 net-new (2B.10) + 1 brownfield (3.8) |
| Shipped Support (phase 0) | 3 | 3 net-new (2B.11 D1=(a)) |
| **Shipped total** | **40** | verified against `src/sdlc/agents/index.yaml` |
| Planned | 0 | all shipped (3.8 adds `characterization-author`) |
| **Grand total** | **40** | FR28 complete |

The PRD §214 prose "~25 markdown specialist agents" reflects the original v0.1 plan. Actual
total has grown via Epic 2A sub-track design (Phase 2 sub-architects), the deliberate addition
of pair-reviewers, 7 Phase-1 net-new (2B.8), 6 Phase-2 net-new (2B.9), 4 Phase-3 net-new
(2B.10), and 3 support net-new (2B.11). **This matrix is the authoritative count.**

**D5=(a) consistency gate (Story 2B.11):** `tests/unit/specialists/test_support_2b11_authoring.py`
asserts `len(load_registry(...).names()) ∈ [39, 45]` (band tolerates near-future additions).
`test_all_workflow_yaml_specialist_refs_resolve` asserts all workflow YAML refs resolve. These
two tests pin matrix rows ↔ `index.yaml` and prevent silent drift.

---

## 5. Cross-References

- `src/sdlc/agents/index.yaml` — machine-readable manifest the dispatcher consumes
- `scripts/validate_specialists.py` — cross-reference validator (placeholder; activates in
  Story 2A-2 / next round)
- ADR-010 — module boundary + LOC cap policy (specialists are content, not modules)
- ADR-030 (drafted under C5) — reconciliation direction record
- Epic 2A retrospective §4 Pattern 7 — original Pattern-7 drift call-out
- Epic 2A retrospective §6.1 A4 — freeze ceremony action
- PRD §214 — original target list
- Architecture.md §932/933/934 — phase-count prose (now subordinate to this matrix)
