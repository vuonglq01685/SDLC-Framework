# ADR-035: Debt-Decay Gate C — Severity-Scoped N-2 Zero-Out

**Status:** Accepted (2026-05-22, Epic 2B prep — `epic-2b-prep/gate-c-amend`).
**Source:** Epic 2B §7.4 Pre-Story-2B.1 gate verification (2026-05-22) — the
debt-decay strict run reported `Gate C FAIL (3 open)` against three MED-severity
Epic-1 carry-forward items.
**Amends:** CONTRIBUTING §7.5 Gate C (added in prep-sprint C6 per Epic 2A retro A1).

## Context

CONTRIBUTING §7.5 Gate C ("N-2 zero-out") required *every* debt item whose
`epic_of_origin` is two epics back from the target — **any severity** — to be
`closed` before `Story N.1`.

This directly contradicts CONTRIBUTING §7.2 (Mandatory Closed-Items Gate), which
states: *"Items marked MEDIUM/LOW priority MAY remain open and run in
parallel-prep slots."* The two clauses live in the same document, both gate
`Story N.1`, and disagree on whether a MED/LOW N-2 item blocks.

For Epic 2B the contradiction is live: `debt-budget.yaml` carries three open
Epic-1 (N-2) items — `EPIC-1-D4-PRECOMMIT-REV-PIN-DRIFT`,
`EPIC-1-D5-POSIX-HELPER-EXTRACTION`, `EPIC-1-D7-LINTER-TEST-HARNESS` — **all
MED**. The Epic 2A retrospective §7.2 placed their owners (P1/P2/P3) as
*"parallel prep, concurrent with the Story 2B.1 worktree"* — i.e. explicitly
**not** blockers. Gate C as written nonetheless fails the strict run on them.

A gate that contradicts the policy section two pages up is a defect, not a
control. (Same class of issue as ADR-033's Gate A.)

## Decision

Gate C is **severity-scoped**: only open N-2 items of severity **BLOCKING or
HIGH** fail the gate. MED/LOW N-2 items may remain open — consistent with §7.2.

`scripts/check_debt_decay_budget.py` filters the N-2 open count by
`severity in {"BLOCKING", "HIGH"}` (`_GATE_C_SEVERITIES`). The zero-tolerance
threshold itself is unchanged — zero open *gating-severity* N-2 items.

The intent of Gate C is preserved: load-bearing debt (BLOCKING/HIGH) must not
linger two epics; trivial debt (MED/LOW) may decay at parallel-prep pace, exactly
as §7.2 already permits.

## Alternatives Considered

- **Keep Gate C "any severity"**: Rejected — contradicts §7.2; blocks Story 2B.1
  on three MED items the Epic 2A retro explicitly scheduled as concurrent.
- **Amend §7.2 instead — drop the MED/LOW carve-out**: Rejected — §7.2's
  parallel-prep allowance is a deliberate Epic-1-retro pattern (small debt should
  not stall an epic); removing it to satisfy a newer mechanical gate inverts the
  precedence (general policy bent to fit the check).
- **Close `EPIC-1-D4/D5/D7` now as a prep-item**: Considered viable but rejected
  as the *gate* fix — it resolves this instance but leaves the §7.2 / §7.5
  contradiction in place to recur every epic. The three items remain open MED
  debt and may still be closed on their own merit at parallel-prep pace.

## Consequences

- The §7.2 / §7.5 contradiction is resolved; Gate C and §7.2 now agree.
- Gate C passes for Epic 2B — the three open Epic-1 N-2 items are all MED.
  Combined with Gate A (ADR-033 / ADR-034) and Gate B passing, the debt-decay
  strict run is now green for target 2B.
- `EPIC-1-D4/D5/D7` stay open as MED debt (owners P1/P2/P3); they no longer gate
  Story 2B.1 but remain tracked and should still close at parallel-prep pace.
- Gate C still hard-blocks on any BLOCKING/HIGH item that lingers two epics —
  the load-bearing-debt guarantee is intact.

## Revisit-by

2027-05-15 — or when a retrospective proposes tightening Gate C back to all
severities (which would first require removing the §7.2 MED/LOW carve-out).
