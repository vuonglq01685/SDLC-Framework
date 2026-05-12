# Cluster J snapshot-regen ceremony — DC9 / PC9

**Story:** 2A.10 — sdlc-verify
**Created:** 2026-05-12 (Cluster C–J pre-implementation review, PC9)
**Status:** stub — populate when P29 / P30 / P34 / P36 land
**Blocking pre-condition for shipping:** any P-patch that mutates `agent_dispatched` or `artifact_verified` journal payload shape

## Why this ceremony exists

Cluster G/H/J patches mutate the journal wire-format. ADR-024 mutation taxonomy classifies these as **payload-shape mutations** and **status-flow mutations** that require:

1. Snapshot regeneration via `python scripts/freeze_wireformat_snapshots.py`
2. An ADR-024 mutation-taxonomy row naming each new key / new status flow / new kind
3. Downstream consumer migration notes (Story 2A.12 `/sdlc-signoff`, future Story 2B.x runtime consumers)

DC9 resolution selected **(c) bundle into ONE regen PR at end-of-Cluster-J** rather than per-patch regen. This ceremony PR is that bundle.

## In-scope mutations

| Patch | Mutation | Wire-format impact |
|-------|----------|--------------------|
| **P29** (DC8-amended) | Add `artifact_hash_at_dispatch` to `agent_dispatched.payload` ALONGSIDE legacy `idea_hash` (no rename). Add `before_hash = sha256(<pre-verify on-disk bytes>)` and `after_hash = sha256(<post-verify on-disk bytes>)` to `artifact_verified` event. DO NOT reintroduce `attempt` on `agent_dispatched` (P22 invariant holds). | Two new optional keys in `agent_dispatched.payload`; two new top-level fields on `artifact_verified` (`before_hash`, `after_hash` populated where previously `None`/`content_hash_at_verify`). |
| **P30** (DC10-scoped) | `artifact_verified.payload.status` may now legitimately carry `"failed"` or `"advisory"` when `result.outcome=="success"` but verdict was non-verified. | Status-flow mutation: existing enum {`verified`,`failed`,`advisory`} already permitted by AC6 model; what changes is that downstream consumers must now expect `"failed"` even when dispatcher outcome was `"success"`. |
| **P34** (DC11-contingent) | IF DC11 test shows dispatcher hooks already cover the frontmatter write → no new kind. IF NOT → new `kind="hook_rejected"` with `actor="cli"`, `payload={hook: <name>, reason: <str>}`. | New journal kind possible. AC5/i.5 sub-clause needs to define the deny envelope; pin in snapshot. |
| **P36** | Add optional `verifier_payload_malformed: bool` to `artifact_verified.payload` when verdict coerced to `"advisory"`. Add structured `warnings: list[str]` to JSON envelope (CLI output, not journal). | One new optional payload key + new envelope field. |

## Ceremony checklist (run after the four patches land)

- [ ] **Run snapshot regen**: `python scripts/freeze_wireformat_snapshots.py` — confirm only `journal_entry.json` (and possibly `hook_payload.json` if P34 lands) changes.
- [ ] **Diff snapshot** — every new key / new status / new kind has a corresponding entry in the regenerated file. No unintended changes.
- [ ] **ADR-024 amendment** — open `docs/decisions/ADR-024-*.md`, append a mutation-taxonomy row dated 2026-05-12 covering each in-scope mutation above. Cite P-IDs and DC-resolution numbers.
- [ ] **Wire-format invariant doc** — if CONTRIBUTING.md §wire-format names any guard rule that the new keys/kinds change, update verbatim.
- [ ] **Consumer migration backlog** — add a Story 2A.12 backlog item referencing the new optional keys (in-scope: `idea_hash` deprecation timeline if/when DC8-(2) progresses to DC8-(1) in 2A.12).
- [ ] **Tests** — every new payload key must be asserted in at least one unit + one e2e test; new kind (if any) must have a dedicated journal-shape regression.
- [ ] **PR description** — link DC9 decision row in `2a-10-sdlc-verify.md` `### Review Findings` section; cite each P-ID; note this is the gate for shipping Cluster G/H/J.

## Out-of-scope (deferred)

- `idea_hash → artifact_hash_at_dispatch` UNCONDITIONAL rename (DC8-(1)) — promote in Story 2A.12 with deprecation cycle.
- Rollback / down-migration for pre-mutation rows in the wild — track under W1 expansion (`deferred-work.md` DC-W2).
- Coverage rider for `_verify_dispatch.py` ≥ 95 % — tracked in PC6 (AC9/AC10 amendments), not here.
