# ADR-027: E2E Test Framework Strategy (Tier-1 / Tier-2 / Tier-3)

**Status:** Accepted (2026-05-10) — Implemented by Story 2A.0; seed scenarios under tests/e2e/cli/walking_skeleton + tests/e2e/pipeline/happy_path_smoke.

## Context

Epic 1 shipped 1,114 tests at 93.37% coverage, but the retrospective (2026-05-09, §3 Pattern 1)
flagged that this coverage figure over-states behavioral coverage: nearly half the epic's
stories shipped at least one tautological/placebo test. The substrate (Stories 1.10/1.11/1.12)
is unit-tested deeply but the **end-to-end CLI surface** (Stories 1.16-1.21) was tested only in
narrow integration slices.

Epic 2A introduces phase orchestration mechanics — every slash command (`/sdlc-start`,
`/sdlc-research`, `/sdlc-verify`, `/sdlc-epics`, `/sdlc-signoff`, `/sdlc-ux`, `/sdlc-architect`,
`/sdlc-bootstrap`, `/sdlc-break`, `/sdlc-task`, `/sdlc-next`) is a public surface that must be
exercised against a deterministic harness, not unit-mocked.

Project Lead directive 4 (retrospective §9) and action **A3** require shipping a precursor
E2E test harness before Story 2A.1 begins implementation. This ADR defines the three-tier
testing strategy that the harness implements.

Per retrospective Story 2A.0 (E2E harness — owner: Dana lead + Charlie review, ~1 day, blocks
all of Epic 2A).

## Decision

The framework is organized into three tiers, each with distinct fixtures, scope, and intended
defect class. **Tier-1 and Tier-2 ship in Story 2A.0; Tier-3 is deferred to Epic 2B
(real-Claude adopt).**

### Tier-1 — CLI Golden Tests

**Location:** `tests/e2e/cli/`
**Fixtures:** `tests/e2e/cli/fixtures/<scenario>/` — input project state (init'd `.sdlc/` tree)
+ command sequence + expected goldens.
**Scope:** A single `sdlc <command>` invocation against a fixture project state.
**Goldens asserted (byte-stable):**

1. stdout (with `--no-color` to strip ANSI noise; `--json` flag for structured commands)
2. stderr (only command-emitted lines; tooling preamble stripped via fixture filter)
3. process exit code
4. post-command journal byte-hash (`sha256` of `state/journal.jsonl`)
5. post-command state byte-hash (`sha256` of canonical `state/active.json`)

**Defect class targeted:** Output regressions, exit-code drift, journal-shape drift across
refactors. Catches "I changed the underlying module and forgot the CLI now prints differently."

**Mock policy:** No `AIRuntime` involvement — Tier-1 tests must NOT cross any AI dispatch
boundary. Commands that would dispatch (`/sdlc-research`, `/sdlc-architect`) skip Tier-1.

**Golden-update workflow:** Intentional changes regenerate goldens via
`pytest tests/e2e/cli/ --update-goldens` (fixture-aware harness flag). PR Change Log MUST cite
the golden update with rationale.

### Tier-2 — Pipeline Tests Against MockAIRuntime

**Location:** `tests/e2e/pipeline/`
**Fixtures:** `tests/e2e/pipeline/fixtures/<scenario>/` — multi-phase command sequence + YAML
script driving `MockAIRuntime` deterministically.
**Scope:** Multi-command Phase 1 → Phase 2 → Phase 3 happy-path replays; specialist dispatch
exercised against `MockAIRuntime` (Story 1.13's deterministic YAML-driven mock).
**Goldens asserted:**

1. Final journal hash after the full replay
2. Signoff hash sequence (one per phase) — must match `tests/contract_snapshots/v1/` byte-stable
   forms
3. Hook chain firing order (sequence of `(hook_name, command, arg_summary)` tuples)
4. Specialist invocation order — sequence of `(specialist_id, primary|parallel, write_glob_set)`
   per dispatch

**Defect class targeted:** Cross-phase contract drift, hook-firing order regression, dispatcher
mis-routing, specialist-write-glob overlap (cross-checked with Story 2A.1's static
disjoint-writes check).

**Mock policy:** `MockAIRuntime` returns YAML-scripted responses. Real Claude Code dispatch is
**explicitly excluded** from Tier-2 — that is Tier-3's role.

### Tier-3 — Real Claude Pipeline Tests (DEFERRED to Epic 2B)

**Location:** `tests/e2e/claude/` (placeholder per Epic 2B Story 2B.3 — behavioral conformance
mock-vs-claude).
**Status in Epic 2A:** **Not implemented.** Epic 2A treats `MockAIRuntime` as authoritative
ground-truth (per ADR-016 abstraction-adequacy contract).
**Deferral rationale:** Tier-3 requires real `claude` subprocess invocation, prompt-injection
corpus (Story 2B.4), and adversarial network conditions; ship as a unit when those substrates
are ready.

## Alternatives Considered

- **A. Single integration-test layer (no tier distinction).** Rejected — Tier-1 and Tier-2
  detect different defect classes; conflating them produces brittle tests that fail for the
  wrong reasons. Epic 1 Pattern 1 (tautological tests) is the worst-case end of this option.
- **B. Defer all E2E until Epic 2A.4 (when hook chain is real).** Rejected — directly
  contradicts retrospective directive A3. Without Tier-1/2, Layer-1 stories (2A.1/2A.2/2A.5)
  are unit-tested only and re-create the Pattern 1 risk.
- **C. Adopt an external E2E framework (Robot Framework, Cucumber, etc.).** Rejected — Adds
  toolchain (third dependency on top of pytest + Hypothesis) without proportional value;
  pytest-only goldens are sufficient for a CLI surface and integrate cleanly with the
  Epic 1 quality gate (`ruff` / `mypy --strict` / `coverage fail_under=90`).
- **D. Property-test only (Hypothesis-based) end-to-end.** Considered viable but rejected as
  the *primary* tier — Hypothesis excels at substrate invariants (already used in 1.10/1.11/1.12),
  but fails the Tier-1 byte-stable-output contract because randomized inputs cannot match a
  golden. Hypothesis remains the right tool for substrate; goldens are right for surface.

## Consequences

- **+** Every Epic 2A story carries at least one Tier-1 OR Tier-2 test (per team agreement
  (B)). Behavioral coverage gap from Epic 1 closes structurally.
- **+** Goldens are deterministic and reviewable as ordinary diffs; review-A reviewer can
  inspect the surface change without reading implementation.
- **+** Tier-2's hook-firing-order golden surfaces dispatcher regressions that would otherwise
  ship silently — directly addresses the Pattern 1 "mocks subvert behavior" risk.
- **+** Tier-3 deferral is explicit and dated (Epic 2B), not implicit; prevents drift toward
  "we'll add real-Claude tests someday."
- **−** Golden maintenance burden — refactors that change output formatting force a
  golden-update commit. Mitigated by `--update-goldens` flag + Change Log discipline.
- **−** Tier-2 fixtures are large (multi-phase YAML scripts). First fixture authoring is
  ~0.3 day; reuse drives marginal cost down per story thereafter.
- **−** Mock/real divergence risk — Tier-2 cannot detect bugs that only manifest with real
  Claude. ADR-016 abstraction-adequacy contract is the structural guard; Tier-3 in Epic 2B is
  the empirical guard.

## Revisit-by

2026-11-10 — or when Epic 2B Story 2B.3 (mock-vs-claude behavioral conformance) lands,
whichever comes first. Tier-3 design is part of that revisit.
