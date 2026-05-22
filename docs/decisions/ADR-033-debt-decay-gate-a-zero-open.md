# ADR-033: Debt-Decay Gate A — Inventory-Relative Zero-Open Threshold

**Status:** Accepted (2026-05-22, Epic 2B prep — `epic-2b-prep/gate-a-threshold`).
**Source:** Epic 2B §7.4 Pre-Story-2B.1 gate verification (2026-05-22) — the
debt-decay strict run reported `Gate A 3/5 FAIL` with no reachable path to pass.
**Supersedes:** the `≥5 BLOCKING closed` Gate A wording in CONTRIBUTING §7.5,
inherited verbatim from Epic 2A retrospective action A1.

## Context

CONTRIBUTING §7.5 (Debt-Decay Policy, added in prep-sprint C6) defined Gate A as:
*the rolling count of closed BLOCKING-severity items across the whole budget must
reach **≥5***. The number `5` was taken verbatim from Epic 2A retrospective action
A1 ("close ≥5 BLOCKING …") — a round target set before the budget inventory
existed.

`debt-budget.yaml` holds exactly **4 BLOCKING-severity items** total:
`EPIC-1-D3-EINTR-RETRY`, `EPIC-2A-D1-WRITE-PRIMITIVE`,
`EPIC-2A-D2-PANEL-V1-PROCESS-LOCAL-SEQ` (all closed) and
`EPIC-2A-D7-CROSS-PLATFORM-LOCK` (open). Even closing every BLOCKING item yields
4 closed — so the `≥5` threshold is **structurally unreachable**: Gate A cannot
pass for Epic 2B regardless of how much debt the prep sprint closes.

A gate that cannot pass is not a functioning gate. It would block every
early-epic `Story N.1` indefinitely, defeating §7.5's stated purpose — "a
machine-checkable budget before each Story N.1 opens". The defect surfaced during
the Epic 2B §7.4 verification on 2026-05-22.

## Decision

Gate A is redefined as an **inventory-relative zero-open rule**: *every
BLOCKING-severity item in `debt-budget.yaml` — regardless of `epic_of_origin` —
must have `status: closed`*. Equivalently, the count of open BLOCKING items must
be `0`.

`scripts/check_debt_decay_budget.py` evaluates `blocking_open == 0`. The gate is
independent of inventory size: it neither requires a minimum closed-count nor
breaks when the inventory grows or shrinks. The absolute `closed` count is no
longer consulted.

This is a strictly stronger guarantee than the superseded count — it asserts
exactly "nothing BLOCKING-severity is still open before Story N.1", which is the
property §7.5 actually intends.

## Alternatives Considered

- **Keep `≥5` unchanged**: Rejected — structurally unreachable against a 4-item
  BLOCKING inventory; blocks every early-epic Story N.1 regardless of diligence.
- **Cap the absolute count at `min(5, total_BLOCKING)`**: Rejected — still an
  arbitrary number that obscures intent and re-breaks whenever the inventory size
  crosses 5 in either direction; a patch, not a fix.
- **Expand the inventory with retro-classified closed BLOCKING items until ≥5
  closed exist**: Considered viable but rejected — Gate A counts *closed* items,
  so this requires retroactively labelling already-closed tickets BLOCKING purely
  to clear the gate. The honest inventory has no uncatalogued closed-BLOCKING
  debt (the C5–C8 prep items are A-/DOC-series, deliberately excluded from the
  budget). This amounts to metric-gaming.

## Consequences

- Gate A is now semantically correct and inventory-size-independent; it scales
  with each epic's actual BLOCKING debt rather than a fixed number.
- Gate A passes for Epic 2B once `EPIC-2A-D7-CROSS-PLATFORM-LOCK` — the sole open
  BLOCKING item — closes. Closing D7 remains mandatory before Story 2B.1.
- A budget with no BLOCKING items passes Gate A vacuously; Gates B and C remain
  the substantive checks in that case. This is acceptable — zero open BLOCKING
  genuinely is the intended pass condition.
- One-time policy churn: CONTRIBUTING §7.5, the runner, and its unit tests change
  in lockstep within this prep-item.
- The audit table renames `Gate A (BLOCKING absolute)` → `Gate A (BLOCKING
  zero-open)`; observed/threshold strings switch from `N closed`/`≥5` to
  `N open`/`0 open`.

## Revisit-by

2027-05-15 — or when a retrospective proposes re-introducing a positive
closed-count floor (e.g. if a future epic's BLOCKING inventory grows large enough
that "zero open" becomes too weak a bar on its own).
