# Story 5.14: Phase Tracker Rendering Real Signoff 4-State

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L6 (5B). L6 = {5.13, 5.14, 5.15, 5.16, 5.18}, cap-bound 4 → 2 batches; **batch 1 = {5.14, 5.15, 5.16, 5.18}** (four independent 1:1 real-data swaps, run in parallel; cap 4), batch 2 = {5.13} rebased on batch-1 merges. Depends on **5.9 (twin — phase-tracker/signoff-cell FROZEN)** + external wave gate **E2A → 5.14** (Epic 2A: **2A.7 signoff 4-state machine** + **2A.19 invalidate-by-replan**) — 2A epics done+merged. Edges: 5.9→5.14 (twin data swap), E2A→5.14 (real shapes). Worktree: **epic-5/5-14-phase-tracker-real-signoff**. Owner Sally. Branch from main, linear merge, rebase between L6 batch-1 merges (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate **N/A** (epic-5 in-progress, cleared at 5.1). Wave-boundary: 5B needs the real 2A shapes — the signoff **vocabulary is VERIFIED present** (`signoff/states.py SignoffState`), but the **source is the `signoff` reader module, NOT `state.json`** (see D1 + RISK). REAL-data swap only — do NOT rebuild the 5.9 component; swap its data source. a11y coverage lands through the 5.9 twin → 5.12 (done) + the terminal 5.22 re-scan. Zero wire-format change → **freeze stays 7/7** (a new read route is internal/documentary per DAG Decision D1, mirroring `/api/dora`). Any new static/fixture → pyproject.toml force-include. -->

## Story

As a team member viewing real phase status,
I want the Phase Tracker (Story 5.9 component) reading real signoff state from the Story 2A.7 4-state machine (surfaced through the dashboard's signoff reader seam), invalidated phases showing the red `slash-circle` variant with a click-through to the replan scope,
So that the dashboard reflects actual phase progression, not synthetic fixtures.

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.14, lines 2731–2747).

**Given** Epic 2A Story 2A.7 implementing the signoff state machine
**When** `state.json` reflects phase 1 = `approved`, phase 2 = `drafted-not-approved`, phase 3 = `awaiting-signoff`
**Then** the Phase Tracker renders the 4-state cells matching the data
**And** state transitions reflected in state.json appear in the next dashboard poll cycle (3 s)

**Given** a phase invalidated by replan (Story 2A.19)
**When** state.json reflects `invalidated-by-replan`
**Then** the Phase Tracker shows the red `slash-circle` variant
**And** the user can click through to see the replan scope

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the real-state → cell mapping (AC1), the **invalidate-by-replan → red `slash-circle` + click-through** variant (AC2), the **3 s poll only-changed re-render** (NFR-PERF-4), and the **numeric-0 count** fix (DEF-6) are all testable → tests-first, mirroring 5.9's static-analysis contract + the 5.5/5.10/5.11 Playwright surface. The server-side signoff **read seam** (D1) is a pure read → a Python contract test asserts it maps `compute_state(phase)` → the 4-state wire value and never re-parses YAML. Component CSS is design substrate already shipped by 5.9 → `test-along`. **Resolve Decisions D1–D4 BEFORE coding.**

- [x] **Task 0 — Resolve Decisions D1 (real signoff data-source seam: `state.json` epic-literal vs the `signoff` reader module — the actual 2A.7 shape) + D2 (click-through-to-replan-scope surface + data source) + D3 (fold the DEF-6 numeric-0 count fix) + D4 (3 s poll cadence + only-changed-render seam) BEFORE coding** (AC: all)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). Confirm the **wave-boundary data-readiness RISK** (the 4-state vocabulary exists in `signoff/states.py` but is NOT projected into `state.json`) is ratified with the PO before branching — the swap targets the `signoff` reader seam, not a `state.json` signoff field that does not exist.

- [x] **Task 1 — Server-side real-signoff read seam (through the `signoff` module, NOT re-parsing YAML)** (AC: 1) — *tests-first*
  - [x] Add a minimal read surface (D1(a): a new `GET /api/signoff` route, mirroring `register_dora_route` [routes/dora.py:51-63], wired in `server.py:90-92`) that returns the real 4-state per phase by calling `sdlc.signoff.states.compute_state(phase, repo_root=...)` for phases 1/2/3 and `sdlc.signoff.records.read_record(phase)` for the invalidated reason/timestamp. The `dashboard` module **may** import `signoff` (module_boundary_table.py:142-149) — this is the sanctioned reader seam. **Never** re-parse `.claude/state/signoffs/*.yaml` in the dashboard; **never** import `engine` (see D2). [Reader-seam rule: docs/sprints/epic-5-dag.md §5:309-312]
  - [x] Emit the state as the **exact wire values** already used by 5.9: `awaiting-signoff` / `drafted-not-approved` / `approved` / `invalidated-by-replan` (the `SignoffState` enum values equal the `signoff-cell.js SIGNOFF_STATES` keys — the mapping is **1:1, zero drift**; do NOT introduce a translation table).
  - [x] **Do NOT fold computed signoff into `/state.json`** — that route streams the file byte-for-byte with ETag-over-content [routes/state.py:18-40]; injecting computed data breaks the 5.1 contract. Keep the read internal/documentary (no `StrictModel`, no ADR-024 snapshot) → **freeze stays 7/7** (DAG Decision D1 precedent for `/api/dora`). **RED:** a phase whose canonical record has `invalidated_at` non-null must read `invalidated-by-replan`, a draft-only phase `drafted-not-approved`, a record with null `invalidated_at` `approved`, neither `awaiting-signoff`; a malformed record must propagate (fail-loud, not demote). [signoff/states.py:47-100]

- [x] **Task 2 — Phase Tracker consumes real signoff → existing `<signoff-cell>` (data swap, NOT a rebuild)** (AC: 1) — *tests-first*
  - [x] The frontend maps each real phase-signoff to the existing `<signoff-cell state="…">` / `<phase-item-row state="…">` by setting the `state` attribute (which triggers the element's content-delta re-render via `attributeChangedCallback`). Reuse `signoff-cell.js` `SIGNOFF_STATES` / `resolveState` and `phase-item-row.js` `ROW_GLYPHS` **verbatim** — no new component, no new vocabulary. [signoff-cell.js:7-42; phase-item-row.js:9-38]
  - [x] `<phase-tracker>` stays the thin ARIA-decorator it became after 5.9 DEC-2/PAT-4 (`role="region"` + `aria-label="Phase tracker"`; **no default strip synthesis**) — 5.14 supplies the real per-cell data; it must NOT resurrect a `DEFAULT_STRIP` render path. [phase-tracker.js:14-31]
  - [x] The single `state.json` `phase` int (current phase, `state/model.py:25-27`) still drives the phase-cell future/active/complete framing; the **per-phase signoff 4-state** comes from the Task 1 seam (D1), not from `state.json`.

- [x] **Task 3 — 3 s poll, only-changed-sections re-render (NFR-PERF-4 / DD-06)** (AC: 1 final-And) — *tests-first*
  - [x] The phase-tracker consumes the Task-1 signoff read on the **3 s poll cadence** (mirror `masthead.js` `setInterval(tick, 3000)`), and updates **only the changed** `<signoff-cell>` / `<phase-item-row>` via attribute swaps — content-delta only, **no CSS transition** (DD-06 / DD-14 gate). Do NOT full-replace the grid each poll. [ux §6.5:130-133; DD-06 ux:255]
  - [x] **RED (Playwright):** flip a phase's signoff (e.g. `drafted-not-approved` → `approved`) in the served data → assert the next poll re-renders that one cell (label/glyph/progress change) while sibling cells retain DOM node identity; assert no `transition:` fires. Mirror the 5.11 incremental-render witness (existing nodes keep identity). [NFR-PERF-4]

- [x] **Task 4 — Invalidated-by-replan → red `slash-circle` + click-through to replan scope** (AC: 2) — *tests-first*
  - [x] Wire the real `invalidated-by-replan` state to the existing red-left-edge + `slash-circle` glyph + "INVALIDATED" treatment already in `signoff-cell.js` (`INVALIDATED_BY_REPLAN → { label:"INVALIDATED", glyph:"slash-circle" }`) and `phase-item-row.js` `ROW_GLYPHS` (`invalidated-by-replan → slash-circle`). `slash-circle` is present in the frozen sprite [icons/sprite.svg:18]. **RED:** an `invalidated-by-replan` phase renders `sprite.svg#slash-circle` + the red edge + "INVALIDATED" text label (color-only forbidden — text carries meaning). [ux §7.2:1462, 1470]
  - [x] **Click-through to replan scope (D2):** surface the persisted replan scope for the invalidated phase — the `replan_invalidated` journal payload `{scope, scope_phase, downstream_artifacts, downstream_count, reason}` (read via the `journal` seam) [cli/replan_cmd.py:115-130] and/or `SignoffRecord.invalidated_reason` + `invalidated_at` (via `signoff.records.read_record`) [signoff/records.py:154-155]. **Do NOT recompute scope** — `engine.replan.compute_downstream` is in `engine`, which the dashboard is FORBIDDEN to import [module_boundary_table.py:142-149; engine/replan.py:43-62]. The click-through is an **inline disclosure / read-only detail region — NOT a `<dialog>`/modal/toast** (§7.12 forbidden-patterns gate, enforced by 5.12). **RED:** clicking the invalidated cell reveals the replan scope (reason + downstream file list) sourced from persisted data, with no modal element and no engine import.

- [x] **Task 5 — Fold DEF-6: `renderSectionBlockHeading({count:0})` numeric-0 blanks the count** (AC: 1) — *tests-first*
  - [x] Fix `count || ""` → `count == null ? "" : String(count)` so a numeric `0` renders "0 …" instead of an empty cell [section-heading.js:17]. 5.14 renders real numeric signoff/phase counts (e.g. "0 approved"), so this is now load-bearing. **RED:** `renderSectionBlockHeading({count:0})` currently blanks; GREEN renders "0". [deferred-work.md:925 — DEF-6, owner 5.14/5.15]

- [x] **Task 6 — Real-data fixtures + contract tests (mirror 5.9) + gates** (AC: 1, 2) — *tests-first*
  - [x] Commit a real-shaped fixture (phase-1 `approved`, phase-2 `drafted-not-approved`, phase-3 `awaiting-signoff`; plus an `invalidated-by-replan` variant with a persisted replan scope) exercising the real seam, mirroring `signoff-states.html` + `test_signoff_states_fixture.py`. Static-analysis contract: the seam maps every `SignoffState` value → its mandated glyph+label 1:1; the reader never re-parses YAML; the click-through carries no modal. Plus the Task-3 Playwright poll test.
  - [x] Run the **module-boundary gate** (`scripts/check_module_boundaries.py`) — assert `dashboard → signoff` / `dashboard → journal` are declared one-way edges and `dashboard → engine` is absent (a stray `engine` import must FAIL). Run the DD-14 motion gate (no transitions), the forbidden-patterns gate (no `<dialog>`/modal/toast for the click-through), and the 5.5 color-only gate (`slash-circle` + "INVALIDATED" text). [check_module_boundaries.py; scripts/check_dashboard_forbidden_patterns.py]

- [x] **Task 7 — Packaging + quality gate + freeze** (AC: 1, 2)
  - [x] Add any new static/JS/HTML/fixture to the `force-include` block [pyproject.toml]; component CSS (already 5.9's) uses `var(--*)` only (5.2 stylelint gate).
  - [x] Python quality gate on the new route + tests (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; module-boundary + LOC-cap green; **zero wire-format change → freeze stays 7/7** (the read route is internal/documentary, no `StrictModel`, no snapshot).

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **REAL 2A.7 state machine (the source-of-truth vocabulary).** *"4-state machine: `awaiting-signoff` → no draft and no canonical record; `drafted-not-approved` → SIGNOFF.md exists; approved: false (or true before record written); `approved` → canonical record exists; invalidated_at is null; `invalidated-by-replan` → canonical record exists; invalidated_at is non-null."* Priority order (AC1): canonical record + `invalidated_at` non-null → INVALIDATED_BY_REPLAN; record + null → APPROVED; SIGNOFF.md draft → DRAFTED_NOT_APPROVED; neither → AWAITING_SIGNOFF. [Source: src/sdlc/signoff/states.py:1-100 — `class SignoffState(str, Enum)` :30-36, `compute_state` :39-100]
- **§7.2 Signoff 4-State Cell Pattern.** The four-state table (border / fill / glyph / label color / progress) + *"Anywhere a signoff state is rendered, **all four** treatments must be implemented even if some appear rarely. This guarantees content-delta swaps work cleanly across state transitions (DD-06)."* `invalidated-by-replan` = left edge `3px solid var(--red)`, `--paper`, **`slash-circle` glyph top-right 16px `--red`**, "INVALIDATED" label, `--red` dashed progress. Glyph map: `awaiting → circle`, `drafted → circle (filled)`, `approved → check`, `invalidated → slash-circle`. [Source: ux-design-specification.md §7.2:1451-1470]
- **§6.5 Phase Tracker + Phase Cell.** 5-column strip `[P1][S1][P2][S2][P3]`; two signoff gate cells carry the four-state contract; a11y `role="region"`/`role="status"` + plain-language `aria-label`; keyboard "No interactions in v1. Read-only." Signoff variants table + `invalidated-by-replan` = `--red` left-edge + dashed progress + "INVALIDATED" + slash-circle top-right. [Source: ux-design-specification.md §6.5:1166-1219 — variants :1200-1207, a11y :1216]
- **State transition = next poll, content delta only.** *"When a signoff progresses (`awaiting → drafted → approved`, or `→ invalidated`), the cell updates synchronously on the next poll via content swap … the four distinct cell treatments make the change perceivable at a glance without choreography."* DD-06: acknowledge state changes via content delta only — no transitions. [Source: ux-design-specification.md §6.5:130-133; DD-06 :255; NFR-PERF-4]

### Frozen foundation to consume (do NOT rebuild — 5.9 froze the component; 2A.7/2A.19 froze the data)

```text
5.9 components (SWAP THE DATA SOURCE, do NOT re-author):
  signoff-cell.js   — SIGNOFF_STATES {awaiting-signoff, drafted-not-approved, approved, invalidated-by-replan}
                      → {label, glyph, aria, progress}; resolveState() normalizes+validates; render is content-delta.
                      approved→check(16px), invalidated-by-replan→slash-circle(16px). [signoff-cell.js:7-42,60-113]
  phase-item-row.js — ROW_GLYPHS {awaiting→circle, drafted→circle-filled, approved→check, invalidated→slash-circle}. [phase-item-row.js:9-38]
  phase-tracker.js  — thin ARIA-decorator ONLY (role=region + aria-label); NO default strip (5.9 DEC-2/PAT-4). [phase-tracker.js:14-31]
  phase-cell.js     — future/active/complete framing; active-ring reuses focus-motion.css .phase-cell.active.
  fixture           — static/test-fixtures/signoff-states.html (synthetic — 5.14 adds a REAL-shaped fixture).

REAL data seam (2A.7 / 2A.19) — the dashboard reads THROUGH the signoff/journal modules, never re-parses:
  signoff/states.py   — compute_state(phase, repo_root) → SignoffState (reads YAML records + SIGNOFF.md drafts). [:39-100]
  signoff/records.py  — read_record(phase) → SignoffRecord{…, invalidated_at, invalidated_reason}. [:141-155,252-282]
  replan (2A.19)      — cli/replan_cmd.py journals `replan_invalidated`{scope, scope_phase, downstream_artifacts,
                        downstream_count, reason} + per-phase `signoff_invalidated`. [:115-130,170-183]
  sprite.svg          — slash-circle PRESENT (:18); circle (:9), circle-filled (:12), check present.
```
[Source: src/sdlc/dashboard/static/components/{signoff-cell,phase-item-row,phase-tracker}/*.js; src/sdlc/signoff/{states,records}.py; src/sdlc/cli/replan_cmd.py; src/sdlc/dashboard/static/icons/sprite.svg]

### REAL 4-state vocabulary — VERIFIED (matches the epic AC + the 5.9 twin, zero drift)

| Epic 5.14 AC name | `SignoffState` enum value (states.py:33-36) | 5.9 `SIGNOFF_STATES` key | 5.9 `ROW_GLYPHS` glyph | Match |
|---|---|---|---|---|
| `approved` | `APPROVED = "approved"` | `approved` | `check` | ✅ |
| `drafted-not-approved` | `DRAFTED_NOT_APPROVED = "drafted-not-approved"` | `drafted-not-approved` | `circle-filled` | ✅ |
| `awaiting-signoff` | `AWAITING_SIGNOFF = "awaiting-signoff"` | `awaiting-signoff` | `circle` | ✅ |
| `invalidated-by-replan` | `INVALIDATED_BY_REPLAN = "invalidated-by-replan"` | `invalidated-by-replan` | `slash-circle` | ✅ |

**Result: the wire values are byte-identical across the epic AC, the real 2A.7 enum, and the 5.9 component — the swap is a pure data-source swap with NO translation table.** The one drift is the *source*, not the vocabulary (see D1 + RISK): the AC says "from `state.json`", but the 4-state is computed by `signoff/states.py`, not projected into `state.json`.

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Real signoff data-source seam: `state.json` (epic-AC literal) vs the `signoff` reader module (the actual 2A.7 shape) [HIGH / wave-boundary].** The AC premise "`state.json` reflects phase 1 = `approved`, …" is **not satisfiable as written**: `State` carries only a single scalar `phase: int` (`state/model.py:25-27`, comment: *"Phase advancement (signoff-based) is Story 2A.12; v1 scanner returns 1 unconditionally"*) and `projection.py` folds **no** signoff into state (`_project_entries` handles only `state_mutation`/`auto_loop_iteration`/`stop_*`) [projection.py:113-167]. The real 4-state is computed by `sdlc.signoff.states.compute_state(phase, repo_root)` from `.claude/state/signoffs/phase-<N>.yaml` records + `SIGNOFF.md` drafts. The `dashboard` module **is allowed** to depend on `signoff` [module_boundary_table.py:142-149]. *Recommendation (a):* add a minimal **read surface through the signoff seam** — a new `GET /api/signoff` route mirroring `register_dora_route` (calls `compute_state(1..3)` + `read_record`) [routes/dora.py:51-63; server.py:90-92], returning a small JSON the phase-tracker polls; **do NOT re-parse the YAML** in the dashboard, **do NOT fold computed signoff into `/state.json`** (that route streams the file byte-for-byte with ETag-over-content — injecting computed data breaks the 5.1 contract). Keep it internal/documentary (no `StrictModel`, freeze 7/7 — DAG Decision D1 precedent for `/api/dora`). Treat the AC's "from `state.json`" wording as documentation drift (vocabulary matches; source differs). *Alternative (b):* extend the `State` projection to carry per-phase signoff — but that is 2A.12 phase-advancement territory, mutates `state.json` shape (freeze risk), and exceeds a 1:1-swap scope. **PO ratifies before branching.**

**D2 — Click-through-to-replan-scope: surface + data source [MEDIUM].** The scope is persisted in two allowed-to-read places: (i) the `replan_invalidated` journal payload `{scope, scope_phase, downstream_artifacts, downstream_count, reason}` + per-phase `signoff_invalidated` entries [cli/replan_cmd.py:115-130,170-183], readable via the `journal` seam; (ii) `SignoffRecord.invalidated_reason` + `invalidated_at` [signoff/records.py:154-155], via `read_record`. The dashboard **must NOT recompute** scope: `engine.replan.compute_downstream` lives in `engine`, which is **not** in the dashboard's `depends_on` (forbidden) [module_boundary_table.py:142-149; engine/replan.py:43-62]. *Recommendation (a):* the click-through is a read-only **inline disclosure / detail region (NOT a `<dialog>`/modal/toast — §7.12 forbidden)** showing the persisted `invalidated_reason` + downstream file list from the latest `replan_invalidated` journal entry, read via the journal/signoff seams. *Alternative (b):* reason text only (simplest). **PO/UX ratify the exact surface;** it must pass the 5.12 forbidden-patterns gate.

**D3 — Fold the DEF-6 numeric-0 count fix [LOW, load-bearing here].** DEF-6 (5.11 review, deferred-work.md:925) tags 5.14/5.15 to fix `renderSectionBlockHeading({count:0})` blanking a numeric-0 count (`count || ""` at section-heading.js:17). *Recommendation (a):* fold it in tests-first (`count == null ? "" : String(count)`), since 5.14 renders real numeric signoff/phase counts (e.g. "0 approved"). No ADR.

**D4 — Poll cadence + only-changed-render seam [LOW].** The AC binds "next dashboard poll cycle (3 s)". *Recommendation (a):* a small frontend poller (mirroring `masthead.js` `setInterval(tick, 3000)`) consumes the D1 read on the 3 s cadence and drives **attribute swaps** on the existing `<signoff-cell>`/`<phase-item-row>` (content-delta re-render, DD-06, no transition — NFR-PERF-4); it must not resynthesize the grid (respects the phase-tracker thin-decorator contract). *Alternative (b):* server-rendered markup — rejected (breaks the poll/JSON architecture + the reader seam).

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** swapping the **data source** of the 5.9 `<phase-tracker>` / `<signoff-cell>` / `<phase-item-row>` from the synthetic fixture → **real per-phase signoff via the `signoff` reader seam** (D1); the **`invalidated-by-replan` → red `slash-circle`** variant wired to the real state + a **click-through to the persisted replan scope** (D2, inline, no modal); the **3 s poll only-changed re-render** (D4, NFR-PERF-4/DD-06); the **DEF-6 numeric-0 count** fix (D3). Reuse `SIGNOFF_STATES` / `ROW_GLYPHS` / `resolveState` **verbatim** (the wire values already equal the enum — 1:1).
- **Must NOT build:** a rebuilt 5.9 component (swap the data source only — the vocabulary already matches); real Epic→Story→Task hierarchy (= **5.15**); real activity feed (= **5.16**); real DORA / KPI (= **5.13 / 5.17**); the STOP banner / 7 triggers (= **5.19**); any `<dialog>`/modal/toast/skeleton (§7.12 forbidden — the click-through is an inline disclosure). Do **NOT** extend the `State` projection or mutate the `state.json` shape (freeze 7/7). Do **NOT** import `engine` to recompute replan scope — read persisted scope through the `journal`/`signoff` seams only. [Source: docs/sprints/epic-5-dag.md §2 (5.9→5.14 :144, E2A→5.14 :172), §3 (L6 :215), §5 (5.14 row :292), §6 (L6 batch :329); §5 reader-seam rule :309-312]

### Project Structure Notes

- The 5.9 component tree (`static/components/{signoff-cell,phase-item-row,phase-tracker,phase-cell}/`) is **frozen substrate** — 5.14 adds a real-data poller + (D1) a server read route, not new components. New static/JS/fixtures → `force-include` [pyproject.toml].
- **Module-boundary one-way edge (enforced):** `dashboard → {errors, state, journal, telemetry, signoff, config, concurrency}` is declared; `dashboard → engine` is **forbidden** [module_boundary_table.py:142-149]. The real signoff read goes through `signoff.states.compute_state` / `signoff.records.read_record` (and the journal seam for replan scope) — never by re-parsing wire files, never through `engine`. `scripts/check_module_boundaries.py` gates it; keep the new route ≤ 400 LOC (LOC cap).
- A new `GET /api/signoff` read route (D1(a)) is **internal/documentary** (localhost-bound, read-only, consumed only by the bundled frontend) — no `StrictModel`, no `tests/contract_snapshots/v1/` snapshot → **freeze stays 7/7** (mirrors the `/api/dora` DAG Decision D1 posture). It rides the 5.1 HTTP boundary (405-on-write, Host-header allowlist) — no new write path.
- a11y is **not** re-owned here: it lands through the 5.9 twin → 5.12 convergence gate (done) + the terminal 5.22 real-data re-scan [DAG §2:202]. The §8.4 focus-order assertion for the assembled SPA is deferred to 5.14–5.18 / 5.22 (deferred-work.md:934 — DEF-2) — 5.14 keeps the phase tracker read-only (no new tab stops).
- L6 batch-1 siblings (5.14/5.15/5.16/5.18) are mutually independent; branch from `main`, linear merge, rebase between batch-1 merges (CONTRIBUTING §3). Zero wire-format contracts → freeze 7/7.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| 4-state → cell treatment (label/glyph/progress/aria) | `SIGNOFF_STATES` + `resolveState` + `renderSignoffCell` (verbatim; wire values = enum) | src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.js:7-113 |
| 4-state → item-row glyph | `ROW_GLYPHS` + `renderPhaseItemRow` | src/sdlc/dashboard/static/components/phase-item-row/phase-item-row.js:9-38 |
| Phase-tracker landmark (thin ARIA-decorator; no default strip) | `renderPhaseTracker` | src/sdlc/dashboard/static/components/phase-tracker/phase-tracker.js:14-31 |
| Real signoff 4-state (the source-of-truth) | `compute_state(phase, repo_root)` → `SignoffState` (reader seam; never re-parse) | src/sdlc/signoff/states.py:30-100 |
| Invalidated reason/timestamp (click-through) | `read_record(phase)` → `SignoffRecord.invalidated_reason`/`invalidated_at` | src/sdlc/signoff/records.py:141-155,252-282 |
| Replan scope (persisted; do NOT recompute via engine) | `replan_invalidated` journal payload (downstream list + reason) via the journal seam | src/sdlc/cli/replan_cmd.py:115-130 |
| New read route registration | mirror `register_dora_route` / `register_state_route` | src/sdlc/dashboard/routes/dora.py:51-63; routes/state.py:15-40; server.py:90-92 |
| `slash-circle` glyph | `<use href="/static/icons/sprite.svg#slash-circle"/>` (frozen) | src/sdlc/dashboard/static/icons/sprite.svg:18 |
| 3 s poll cadence | mirror `masthead.js` `setInterval(tick, 3000)` | src/sdlc/dashboard/static/components/masthead/masthead.js |
| Static-analysis contract test | mirror `test_signoff_states_fixture.py` (4 states, glyph+label per state) | tests/unit/dashboard/test_signoff_states_fixture.py |
| Module-boundary + forbidden-patterns gates | run on the new route + click-through | scripts/check_module_boundaries.py; scripts/check_dashboard_forbidden_patterns.py |
| Wheel force-include | add new static/route/fixtures | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2731-2747] — Story 5.14 ACs (verbatim above)
- [Source: src/sdlc/signoff/states.py:1-100] — **REAL 2A.7 4-state machine** (`SignoffState` enum :30-36; `compute_state` priority order :47-100) — the source-of-truth vocabulary, verified 1:1 with the epic AC + 5.9
- [Source: src/sdlc/signoff/records.py:141-155,252-282,331-392] — `SignoffRecord` (`invalidated_at`/`invalidated_reason`); `read_record`; `invalidate_record` (2A.19)
- [Source: src/sdlc/cli/replan_cmd.py:115-130,170-183] — 2A.19 `sdlc replan`: `replan_invalidated` journal payload (downstream scope) + `signoff_invalidated`
- [Source: src/sdlc/engine/replan.py:43-62] — `compute_downstream` lives in `engine` (dashboard FORBIDDEN to import — click-through must read persisted scope, not recompute)
- [Source: src/sdlc/state/model.py:10-36] — `State` has only scalar `phase: int` (:25-27), NO per-phase signoff field (drives D1 + RISK)
- [Source: src/sdlc/state/projection.py:113-167] — `_project_entries` folds no signoff into state (confirms the AC's "from state.json" is not satisfiable)
- [Source: src/sdlc/dashboard/routes/state.py:15-40] — `/state.json` streams the file as-is with ETag/304 (do NOT inject computed signoff)
- [Source: src/sdlc/dashboard/routes/dora.py:51-63; src/sdlc/dashboard/server.py:90-92] — `register_dora_route` pattern + wiring point to mirror for the D1(a) signoff read route
- [Source: scripts/module_boundary_table.py:142-149] — `dashboard` depends_on {errors, state, journal, telemetry, signoff, config, concurrency}; `engine` FORBIDDEN
- [Source: scripts/check_module_boundaries.py] — one-way-edge + LOC-cap gate (run on the new route)
- [Source: src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.js:7-141; phase-item-row/phase-item-row.js:9-64; phase-tracker/phase-tracker.js:14-31] — 5.9 components (swap data source; do NOT rebuild)
- [Source: src/sdlc/dashboard/static/icons/sprite.svg:9,12,18] — `circle` / `circle-filled` / `slash-circle` present (frozen)
- [Source: src/sdlc/dashboard/static/components/section-heading/section-heading.js:17] — DEF-6 numeric-0 count blank (D3 fold)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.5:1166-1219, §7.2:1451-1470; §6.5 poll-transition:130-133; DD-06:255] — Phase Tracker / Signoff 4-State Cell / content-delta on next poll
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:925 (DEF-6 → 5.14/5.15), :934 (5.12 DEF-2 focus-order §8.4 → 5.14–5.18/5.22)] — folded / referenced
- [Source: docs/sprints/epic-5-dag.md §2 (5.9→5.14 :144, E2A→5.14 :172, 5.22 re-scan :202), §3 (L6 :215), §5 (5.14 row :292, reader-seam rule :309-312), §6 (L6 batch :329)] — layer, edges, twin, worktree, wave gate, one-way-edge rule
- [Source: _bmad-output/implementation-artifacts/5-9-phase-tracker-signoff-4-state-cell-item-row-progress-bar.md] — the 5A twin (component + `SIGNOFF_STATES`/`ROW_GLYPHS` + DEC-2/PAT-4 thin-decorator lesson)

## Dev Agent Record

### Agent Model Used

Claude (Cursor bmad-dev-story agent), worktree `epic-5/5-14-phase-tracker-real-signoff` (`wt-5-14`).

### Debug Log References

- D1–D4 ratified per sprint-status.yaml changelog (2026-07-02 entry): D1(a) new internal `GET /api/signoff` route through `signoff.states.compute_state` / `signoff.records.read_record` (never `state.json`, never re-parse YAML); D2(a) inline disclosure (no dialog/modal/toast) reading persisted `invalidated_reason` + journal `replan_invalidated` downstream scope; D3(a) DEF-6 numeric-0 fix; D4(a) 3 s poller mirroring `masthead.js`, content-delta attribute swaps only.
- Discovered + fixed a **pre-existing infinite-recursion defect** (not introduced by this story) in the frozen Story 5.9 `signoff-cell.js` / `phase-cell.js`: both call `element.setAttribute(observedAttr, value)` unconditionally from inside the render triggered by that same attribute's change. The DOM does **not** dedupe `setAttribute` by value — `attributeChangedCallback` re-fires even when the new value is identical — so the unguarded write recurses synchronously until `RangeError: Maximum call stack size exceeded`. Story 5.9 never caught this because its only tests are static-analysis (`test_signoff_states_fixture.py` explicitly documents "the cell renders its glyph/label via JS that a static-text test never executes"); Story 5.14 is the first to actually `page.goto()` these components in a real browser (`tests/integration/test_dashboard_phase_tracker_live.py`), which hung/crashed on load until fixed. Fix: added a `setAttributeIfChanged(el, name, value)` guard (diff-checked before writing) in `signoff-cell.js`, exported and reused by `phase-cell.js` (mirrors its existing `createGlyph` re-use). Pinned with a new regression test, `tests/unit/dashboard/test_signoff_cell_attribute_recursion_guard.py`.
- Full non-integration suite: 3780 passed / 4 skipped / 1 xfailed (261 s); coverage 87.90% (≥ 87% floor). `tests/e2e/cli/test_walking_skeleton_goldens.py` is a documented pre-existing flaky test in isolation from full-suite pollution (deferred-work.md QG1, unrelated to this story's changed files) — passes 2/2 in isolation and passed in this run's full-suite invocation too.
- Gates green: `check_module_boundaries.py`, `check_dashboard_forbidden_patterns.py`, `check_dashboard_motion.py` (DD-14), `check_dashboard_color_only.py`, full `pre-commit run` on all changed files, `mkdocs build --strict`, `mypy --strict` on `routes/signoff.py` + `server.py`.

### Completion Notes List

- **Task 1 (`/api/signoff` read seam):** new `src/sdlc/dashboard/routes/signoff.py` (102 LOC, well under the 400 LOC cap) computes phases 1–3 via `signoff.states.compute_state`, reads `SignoffRecord.invalidated_at`/`invalidated_reason` via `signoff.records.read_record` for phases 1–2 when invalidated, and surfaces the persisted replan scope by scanning the journal for the matching `replan_invalidated` entry (by `invalidated_at` timestamp correlation). Phase 3 is hardcoded `awaiting-signoff` (no signoff gate in v1). Wire values are byte-identical to `SignoffState` enum values — zero translation table. Malformed canonical records propagate (fail-loud), never silently demote. Wired in `server.py`. No `StrictModel`, no snapshot — freeze stays 7/7.
- **Task 2/3/4 (frontend poller):** new `phase-tracker-live.js` (`startPhaseTrackerPoller`) polls `/api/signoff` every 3 s (mirrors `masthead.js`), drives only-changed attribute swaps on the frozen `<signoff-cell data-phase>` / `<phase-item-row data-phase>` elements (never resynthesizes `.phase-tracker__grid`), and wires a click-through on `invalidated-by-replan` cells that toggles an inline `[data-role="replan-detail"]` region (no dialog/modal/toast) showing the persisted reason + downstream artifact list. New real-data fixture `phase-tracker-live.fixture.html` + CSS `phase-tracker-live.css` (design tokens only). Playwright suite (7 tests) proves: real state renders on load, a disk-state transition appears on the next 3 s poll, sibling DOM nodes keep identity across a poll (NFR-PERF-4), a repeated identical snapshot is a no-op, the invalidated cell shows the red `slash-circle` + "INVALIDATED" label, click-through reveals the scope with zero `dialog`/`role=dialog`/toast elements, and an approved cell's click does not disclose anything.
- **Defect fix (unplanned, blocking):** fixed the pre-existing `signoff-cell.js`/`phase-cell.js` setAttribute-recursion bug described above (Debug Log) — required for Task 2/3/4's Playwright tests to run at all.
- **Task 5 (DEF-6):** `section-heading.js` count now uses a nullish guard (`count == null ? "" : String(count)`) instead of `count || ""`, so a real numeric `0` count renders "0" instead of blanking.
- **Task 6 (fixtures + contract tests + gates):** `test_signoff_backend.py` (Python contract: 4-state mapping, phase-3-always-awaiting, invalidated+replan-scope, missing-journal-entry omits `replan` key, approved never carries `replan`, fail-loud on malformed record) + `test_phase_tracker_live_source.py` (static-analysis: 3 s cadence, `/api/signoff` seam not `/state.json`, no grid resynthesis, change-guarded state writes, `phase-tracker.js` untouched, no dialog/modal/toast/engine-import, fixture `data-phase` hooks). Module-boundary, forbidden-patterns, DD-14 motion, and color-only gates all pass.
- **Task 7 (packaging + quality gate):** all 3 new static files + fixture added to `pyproject.toml` force-include; full pre-commit suite green; `mypy --strict` clean; `ruff` + `ruff format` clean repo-wide; `mkdocs build --strict` green; full non-integration suite 3780 passed/4 skipped/1 xfailed, coverage 87.90%; zero wire-format contract change (7 snapshots unchanged) → freeze stays 7/7.

### File List

- `src/sdlc/dashboard/routes/signoff.py` (new) — `GET /api/signoff` read route (D1)
- `src/sdlc/dashboard/server.py` (modified) — wire `register_signoff_route`
- `src/sdlc/dashboard/static/components/phase-tracker/phase-tracker-live.js` (new) — 3 s poller + click-through (D2/D4)
- `src/sdlc/dashboard/static/components/phase-tracker/phase-tracker-live.css` (new) — replan-detail disclosure styles
- `src/sdlc/dashboard/static/components/phase-tracker/phase-tracker-live.fixture.html` (new) — real-data fixture
- `src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.js` (modified) — DEF: fix pre-existing setAttribute-recursion defect (`setAttributeIfChanged` guard, exported)
- `src/sdlc/dashboard/static/components/phase-cell/phase-cell.js` (modified) — same recursion-guard fix (reuses `setAttributeIfChanged`)
- `src/sdlc/dashboard/static/components/section-heading/section-heading.js` (modified) — DEF-6 numeric-0 count fix (D3)
- `pyproject.toml` (modified) — force-include the 3 new `phase-tracker-live.*` static files
- `tests/unit/dashboard/test_signoff_backend.py` (new) — Task 1 contract tests
- `tests/unit/dashboard/test_phase_tracker_live_source.py` (new) — Task 2/3/4 static-analysis contract
- `tests/unit/dashboard/test_signoff_cell_attribute_recursion_guard.py` (new) — regression guard for the setAttribute-recursion defect
- `tests/unit/dashboard/test_section_heading_count.py` (new) — Task 5 / DEF-6 regression test
- `tests/integration/test_dashboard_phase_tracker_live.py` (new) — Task 2/3/4 Playwright behavioral suite (7 tests)

## Change Log

- 2026-07-02: Implementation complete, status → review. D1(a)/D2(a)/D3(a)/D4(a) ratified (see sprint-status.yaml changelog). Task 1: new internal `GET /api/signoff` route (`routes/signoff.py`) reading through `signoff.states.compute_state`/`signoff.records.read_record` + the journal seam for replan scope — no `state.json` fold, no re-parse, fail-loud on malformed records, freeze stays 7/7. Task 2–4: new `phase-tracker-live.js` 3 s poller drives only-changed attribute swaps on the frozen 5.9 `<signoff-cell>`/`<phase-item-row>` (NFR-PERF-4/DD-06), wires the `invalidated-by-replan` red `slash-circle` + inline (no modal) click-through disclosure to the persisted replan scope; new real-data fixture + CSS. **Unplanned but blocking defect fix:** discovered and fixed a pre-existing infinite-recursion bug in the frozen Story 5.9 `signoff-cell.js`/`phase-cell.js` (`setAttribute` on an observed attribute re-fires `attributeChangedCallback` even when the value is unchanged — unguarded, this recurses until stack overflow); Story 5.9's tests were static-analysis only and never exercised real rendering, so this went undetected until 5.14's Playwright suite first loaded the components in a browser. Fixed with a `setAttributeIfChanged` diff-guard (shared between the two files) + a dedicated regression test. Task 5: folded DEF-6 (numeric-0 count fix in `section-heading.js`). Task 6: real-data fixture + Python contract tests (`test_signoff_backend.py`) + JS static-analysis contract (`test_phase_tracker_live_source.py`) + module-boundary/forbidden-patterns/motion/color-only gates all green. Task 7: force-include entries added; full pre-commit green; `mypy --strict` clean; full non-integration suite 3780 passed/4 skipped/1 xfailed, coverage 87.90%; `mkdocs build --strict` green; zero wire-format change, freeze stays 7/7. Pre-existing flaky `test_walking_skeleton_goldens` (deferred-work.md QG1) is unrelated to this story's changed files (passes in isolation).
- 2026-07-01: Story 5.14 created (create-story, "flip done 5.12 + tạo all US cho layer tiếp theo" → L6/5B batch-1 {5.14,5.15,5.16,5.18}) — Phase Tracker rendering **real signoff 4-state** by swapping the 5.9 component's data source onto the real 2A.7 `SignoffState` machine (surfaced through the `signoff` reader seam) + the `invalidated-by-replan` → red `slash-circle` variant with a click-through to the persisted replan scope (2A.19) + 3 s-poll only-changed re-render (NFR-PERF-4/DD-06). **REAL 4-state vocabulary VERIFIED 1:1** with the epic AC + the 5.9 `SIGNOFF_STATES`/`ROW_GLYPHS` (`awaiting-signoff`/`drafted-not-approved`/`approved`/`invalidated-by-replan` = `signoff/states.py SignoffState`). Decisions D1 (data-source seam: the 4-state is **NOT** in `state.json` — read through the `signoff` module, not the epic-literal `state.json` field, which does not exist — recommend a new internal `/api/signoff` read route) / D2 (click-through surface + persisted replan-scope source; no engine recompute; no modal) / D3 (fold DEF-6 numeric-0 count fix) / D4 (3 s poll only-changed-render seam) raised. **Wave-boundary RISK flagged:** vocabulary present + verified, but source differs from the AC wording — PO ratify before branching. L6 (5B) twin-swap; module one-way edge `dashboard → signoff/journal` (never `engine`, never re-parse); zero wire-format change → freeze 7/7; §7.4 gate N/A (not Story N.1). Do-not-build real hierarchy (5.15) / real feed (5.16) / DORA (5.13) / STOP banner (5.19) noted.

## Review Findings

> **bmad-code-review** (2026-07-02) — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor). Target: uncommitted 5.14 changes in worktree `wt-5-14` (base `8d2b4e1`), ~1470 diff lines. Independently verified: all 7 dashboard gates green (module-boundary → no `engine`; forbidden-patterns → no dialog/modal/toast; DD-14 motion; color-only; no-framework/theme/external-fonts). D1–D4, freeze 7/7, `force-include`, and anti-scope-creep constraints all hold. Triage: **1 decision-needed, 3 patch, 3 defer, 3 dismissed**.

### Decision-Needed

- [x] [Review][Decision → Deferred to Story 5.20] Server fail-loud on a corrupt signoff record is defeated by the client `catch{}` → false-green board — The server deliberately fails loud on a malformed canonical record (documented `routes/signoff.py:14-19`, tested by `test_malformed_canonical_record_does_not_silently_demote`). But (a) `_compute_body` builds all phases in one comprehension with no per-phase guard [`routes/signoff.py:64,88-92`], so one corrupt phase blacks out healthy phases too; and (b) the poller's `catch{}` [`phase-tracker-live.js:121-124`] swallows the resulting connection drop every 3 s, so the operator sees a stale/false-`awaiting-signoff` board with no error — exactly what the server docstring says must never happen — while the server logs a traceback each poll. Options: **(1)** accept as-is (masthead precedent + "real disconnect handling is Story 5.20"); **(2)** per-phase isolation now (corrupt phase → only that gate fails, healthy gates still render) + a minimal client error indicator on repeated poll failure; **(3)** per-phase isolation server-side only, leave the client surface to 5.20. Options 2/3 change the ratified whole-endpoint fail-loud contract and its test. **RESOLVED 2026-07-02 → option 1 (accept + defer):** the whole-endpoint fail-loud contract + `test_malformed_canonical_record_does_not_silently_demote` are intentional and left untouched; the poll error-surface is owned by Story 5.20. Tracked as `deferred-work.md` DEF-4 — 5.20 must cover corruption→false-green, not just network disconnect.

### Patch

- [x] [Review][Patch] ✅ APPLIED 2026-07-02 — Open replan-detail disclosure is rebuilt on every 3 s poll — `renderReplanDetail` unconditionally `replaceChildren` even when reason+downstream are unchanged, wiping the user's text selection while the panel is open; `changed` return ignores it so the "no-op on identical snapshot" test gives false confidence (violates the story's own DD-06/NFR-PERF-4 content-delta rule) [`phase-tracker-live.js:56,67,86`]
- [x] [Review][Patch] ✅ APPLIED 2026-07-02 — No in-flight guard on the async poll — `setInterval(tick,3000)` with an un-awaited async `tick`; a slow poll resolving after a newer one applies a stale snapshot → a gate flaps backward until the next cycle [`phase-tracker-live.js:117-127`]
- [x] [Review][Patch] ✅ APPLIED 2026-07-02 — Incomplete teardown — disposer only `clearInterval`; the `wireClickThrough` click listener is never removed (leak) and re-init attaches two listeners → each click toggles twice → the disclosure never opens; an in-flight tick still mutates after dispose [`phase-tracker-live.js:116,128`]

### Deferred

- [x] [Review][Defer] No cache on `/api/signoff` + unbounded full-journal rescan per invalidated phase every 3 s poll (`/api/dora` has a 30 s cache seam) [`routes/signoff.py:57-60,88-97`] — deferred, perf-hardening follow-up (not blocking for a localhost v1 board)
- [x] [Review][Defer] Replan-scope correlation by exact `ts` string equality + one shared payload for all phases invalidated in a single replan; both test helpers use one `_TS_INVAL` literal so serialization drift is uncatchable [`routes/signoff.py:58`] — deferred, robustness follow-up (correct in the sanctioned same-`now` replan flow)
- [x] [Review][Defer] `signoff-cell` `aria-label` frozen across state transitions — `customAria || …` short-circuits to the first-rendered accessible name, so a transitioning cell keeps its original ARIA name while the visible label updates [`signoff-cell.js:74,80`] — deferred, pre-existing frozen-5.9 substrate; a11y re-scan owned by Story 5.22 (DEF-2)

### Dismissed (3, dropped)

- `section-heading` stringifies `NaN`/`false`/`[object Object]` for non-null non-numeric count — D3 mandates exactly `count == null ? "" : String(count)`; `count` is always an integer.
- `renderReplanDetail` assumes `downstream_artifacts` is an array — requires a corrupt journal the app never writes; cosmetic, no XSS (`textContent`).
- null-`root` deref at `startPhaseTrackerPoller` — internal entrypoint; caller always passes the authored mount.
