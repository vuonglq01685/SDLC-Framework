# ADR-038: Sticky-Halt Projection — `halted` Survives a Clean `stopped` Iteration (CR4.2-W3)

**Status:** Accepted

> Implemented (Epic-4 retro D4): `_fold_auto_loop_status` preserves `(halted, stop_reason)` when a
> clean `stopped` iteration folds over an already-`halted` status; a genuine `dispatch`/`continued`
> still clears it. Cross-platform RED→GREEN tests in `tests/unit/state/test_state_projection.py`.

## Context

The journal→state projection folds auto-loop events into `State.auto_loop_status`.
In `src/sdlc/state/projection.py::_fold_auto_loop_status` (line 96), an
`auto_loop_iteration` entry with `action="stopped"` **unconditionally** returns
`("idle", …)`, regardless of the status carried into the fold. When a prior entry has
already folded to `"halted"` (via `stop_triggered` / `stop_trigger_raised`), a subsequent
`auto_loop_iteration{action="stopped"}` overwrites it back to `"idle"` — last-write-wins.

The projection replays the **entire** journal from scratch on every read
(`project_from_journal`), so a journal ending in the sequence
`stop_triggered → auto_loop_iteration{stopped}` projects to `idle`, and the halt is
**permanently lost across runs**. This is the Epic-4 retro **CR4.2-W3** finding and retro
action **D4** — and it directly load-bears **Epic-5 Story 5.19** (the STOP banner), which
reads `auto_loop_status` from the projected `State`: a non-sticky halt makes the banner
flicker or vanish even while a clarification/signoff is still open. Epic-5 DAG Decision D3
gates 5C on this fix (sticky halt), not on real auto-loop dispatch.

`State` (`src/sdlc/state/model.py:34`) is a plain `pydantic.BaseModel` with
`frozen=True, extra="forbid"`; it is explicitly "journal-replay derived, not wire-format"
(model.py:33), is **not** a `StrictModel`, and has **no** snapshot in
`tests/contract_snapshots/v1/`. So this change touches **no** frozen ADR-024/025 contract
and needs **no** snapshot ceremony.

## Decision

Make `"halted"` **sticky against a clean stop** in `_fold_auto_loop_status`: a folded
`auto_loop_iteration{action="stopped"}` no longer transitions away from `"halted"` — when
the incoming status is `"halted"`, the fold preserves `(halted, stop_reason)`. A **genuine
resume** — `auto_loop_iteration{action in {"dispatch","continued"}}` — still clears the
halt (transition to `"running"`), because a new dispatch means the halt condition was
resolved and the loop restarted. Net precedence within a run session:
`stop_triggered/stop_trigger_raised → halted` is **terminal against a `stopped` iteration**
and is cleared **only** by a subsequent explicit dispatch. No new `State` field; the fix is
confined to the fold's transition logic.

## Alternatives Considered

- **Once-halted blocks *all* subsequent iterations (including `dispatch`/`continued`)**: Rejected — a legitimate resume after the operator resolves the blocker could never restore `"running"`; the projection would be stuck `halted` forever.
- **Add a `halt_persisted: bool` field to `State`**: Rejected — it duplicates information already carried by `auto_loop_status == "halted"` and changes the projection's output shape for no functional gain (`State` is non-wire so it is *safe* to add, but unnecessary). The retro wording ("projection retains `halted`") points at the fold, not the schema.
- **Leave last-write-wins and have Story 5.19 infer the halt from the trigger files on disk**: Rejected — it pushes projection logic into the UI and re-derives auto-loop state from disk a second time, exactly the "two drifting interpretations of the same wire data" trap.

## Consequences

- Story 5.19's STOP banner reliably persists the halt across runs and process restarts.
- Minimal, fold-local change — no `State` field, no schema migration, no snapshot regeneration; the 7/7 freeze is untouched.
- A genuine resume still works: a subsequent `dispatch`/`continued` clears the halt to `"running"`.
- Cost: a `stopped` iteration recorded *after* a halt is intentionally ignored by the fold (the correct semantic) — this must be pinned by a new RED-first test feeding `[stop_trigger_raised, auto_loop_iteration{stopped}]` and asserting the final `auto_loop_status == "halted"` (no such test exists today — it is a coverage gap, not a regression of an existing assertion).
- Introduces an implicit fold precedence (`halted` dominates a clean `stopped`); documenting it here prevents a future edit to `_fold_auto_loop_status` from silently reintroducing the overwrite.

## Revisit-by

2027-06-22 — or when an explicit `resume_from_halt` journal kind is introduced (per ADR-028 taxonomy), which would make "a dispatch clears the halt" an explicit transition rather than an implicit one.
