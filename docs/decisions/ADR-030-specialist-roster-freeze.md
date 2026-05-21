# ADR-030: Specialist Roster Freeze + Reconciliation Direction

**Status:** Accepted (2026-05-21, prep-sprint C5).

**Source:** Epic 2A retrospective action A4 + §4 Pattern 7 (Specialist-Naming Drift Between
Architecture and Code).

## Context

Epic 2A retrospective surfaced Pattern 7: Story 2A.15 shipped `code-bootstrapper` while PRD
§214 declared `codebase-scaffolder`. Sub-agent inventory under prep-sprint C5 revealed the
drift was wider than Pattern 7 reported — 8 PRD-declared names had been renamed by the
shipping authors, plus 2 entirely new specialists (`ux-reviewer`, `observability-architect`)
that PRD §214 did not list.

The retro proposed: *Architecture.md becomes canonical; deviations require ADR.* That rule is
forward-looking. This ADR fixes the **pre-existing drift one-time**, in the direction that is
cheap (rename docs) rather than the direction that is expensive (rename shipped + tested code).

## Decision

**For pre-C5 drift: shipped code wins.** Every specialist already authored and registered in
`src/sdlc/agents/index.yaml` keeps its shipped name. PRD §214 prose is amended (one-line
pointer) and the canonical roster is moved to `docs/specialists-matrix.md`.

**For post-C5 additions: forward rule applies.** New specialists authored under Epic 2B.8/9/10
land in `docs/specialists-matrix.md` first (planned row); when the implementation lands the
matrix row moves from "planned" to "shipped". Any deviation between the planned-row name and
the shipped-row name at that moment requires a one-line ADR amendment to ADR-030 (this file)
citing the rationale.

**Renames documented in `docs/specialists-matrix.md` §2 are now canonical:**

| PRD §214 → | Canonical (shipped) |
|---|---|
| `codebase-scaffolder` | `code-bootstrapper` |
| `developer-agent` | `code-author` |
| `signoff-summarizer` | `phase1-signoff-summarizer` |
| `requirement-validator` | `artifact-verifier` |
| `epic-planner` | `epic-generator` |
| `solution-architect` | `system-architect` |
| `data-modeler` | `database-architect` |
| `synthesizer` (generic) | `requirement-synthesizer` (Phase-1 specialised; the generic synthesizer role lives in the dispatcher per PRD FR26) |

Two new specialists shipped during Epic 2A that PRD §214 never listed are now first-class:
`ux-reviewer` (pairs with `ux-designer`) and `observability-architect` (sub-track sibling of
`system-architect`).

## Alternatives Considered

- **Rename shipped code to match PRD §214.** Rejected: would touch 7 specialist files,
  `src/sdlc/agents/index.yaml`, every story that references the specialist (2A.15-2A.17 at
  minimum), every workflow YAML that names them in `parallel_agents`, and every test fixture.
  Estimated effort ≥ 1 day. Provides no behaviour change.
- **Defer reconciliation to Epic 2B.8/9/10 authoring time.** Rejected: leaves Pattern 7 open
  as a live confusion vector during Epic 2B specialist authoring; new authors would not have
  a single source of truth to reference.

## Consequences

- **+** Single source of truth (`docs/specialists-matrix.md`) for current and future
  specialist roster discussions. Pattern 7 closed.
- **+** Forward rule "matrix is canonical, deviations require ADR amendment" applies cleanly
  to Epic 2B authoring without backporting churn.
- **+** PRD §214 prose remains as historical record of v0.1 intent; the pointer it now carries
  routes readers to current state without losing audit context.
- **−** PRD prose now requires readers to follow one indirection (the matrix link) for the
  authoritative list. Mitigated: the link is single-step and the matrix renders inline in any
  Markdown viewer.
- **−** Two specialists (`ux-reviewer`, `observability-architect`) ship without a v0.1 charter
  in PRD §214. Their authoring stories (2A.13, 2A.14) document the rationale; this ADR notes
  them as first-class additions.

## Revisit-by

2026-08-21 — or when Epic 2B.8/9/10 authoring lands the planned roster, whichever comes
first. At that point: collapse the matrix's "planned" section into "shipped" and update PRD
§214 if any planned-name rename occurred.
