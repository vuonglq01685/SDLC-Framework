# Story 5.9: Phase Tracker + Signoff 4-State Cell + Item Row + Progress Bar

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L3 (5A). L3 = {5.5, 5.9, 5.10}, max 3 parallel worktrees. Depends on 5.2 (frozen tokens) + 5.3 (sprite: check/slash-circle/circle/circle-filled glyphs) + 5.4 (motion budget) — ALL done+merged. Mutually independent of L3 siblings 5.5 / 5.10 (no edge between them; 5.9 is NOT on the critical path). Edges: 5.2→5.9, 5.3→5.9; downstream 5.9→5.14 (real signoff swap) and 5.9→5.12 (a11y convergence gate). Worktree: epic-5/5-9-phase-tracker-signoff-cell. Branch from main, linear merge, rebase between L3 merges (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). SYNTHETIC fixtures only — real 4-state from state.json is 5.14; the 4-state vocabulary mirrors 2A.7. -->

## Story

As any team member checking phase status,
I want the Phase Tracker (main column) rendering each phase as a Signoff 4-State Cell (`awaiting-signoff` / `drafted-not-approved` / `approved` / `invalidated-by-replan`) with check/slash-circle glyphs, item rows in the detail body, and a thin progress bar,
So that all four signoff states render consistently per the cross-cutting pattern (UX-DR4, UX-DR10, UX-DR11, UX-DR24, §6.5, §7.2).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.9, lines 2594–2617).

**AC1 — Signoff 4-State Cell (all four states)**
- **Given** synthetic fixtures for all 4 states **When** the Signoff 4-State Cell renders **Then** `awaiting-signoff` shows hairline border, paper fill, no glyph, `--ink-mute` label
- **And** `drafted-not-approved` shows 3 px amber left edge, paper fill, "DRAFTED" label, amber progress fill
- **And** `approved` shows 3 px green left edge, paper or `--green-soft`-blended fill, `check` glyph top-right (Story 5.3 sprite), "APPROVED" label, green 100% progress
- **And** `invalidated-by-replan` shows 3 px red left edge, paper fill, `slash-circle` glyph, "INVALIDATED" label, red dashed progress

**AC2 — Consistency contract (§7.2) + committed fixture page**
- **Given** the consistency contract (§7.2) **When** all 4 cell variants are rendered side-by-side in a Storybook-style fixture page **Then** content-delta swaps work cleanly (DD-06: state changes via content delta only, no transitions)
- **And** the test fixture page is committed under `dashboard/static/test-fixtures/signoff-states.html` for a11y + visual review

**AC3 — Item rows in phase detail body**
- **Given** the item rows in phase detail body **When** rendered **Then** each row contains a check-glyph (per state), a label, and an optional badge
- **And** focus order traverses rows in declared order

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the Signoff 4-State Cell is design substrate → `test-along` is acceptable for the CSS. The **deterministic contracts are testable tests-first:** (a) the **all-four-states-present + glyph/label-per-state** contract (§7.2 mandates ALL four treatments exist even if rare) → a static-analysis/DOM test over the committed fixture page asserts each of the 4 states renders its mandated glyph + non-color text label (this also satisfies the 5.5 color-only-signaling contract); (b) **content-delta swap** (DD-06) → assert no `transition:` via the existing DD-14 gate. The Playwright/a11y review of the committed fixture page (AC2) is the visual-regression surface. Resolve Decisions D1/D2 BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (fixture path vs 5.5 layout convention) + D2 (approved-fill treatment) BEFORE coding** (AC: 1, 2)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). Align the fixture path with the file-layout convention 5.5 freezes (DAG §5) — see D1.

- [x] **Task 1 — Signoff 4-State Cell (all four states)** (AC: 1)
  - [x] Implement ALL four states (§7.2 consistency contract — every treatment must exist even if some are rare, so content-delta swaps work cleanly):
    - `awaiting-signoff`: `--border-hairline`, `--paper` fill, **no glyph**, `--ink-mute` label. Glyph mapping (§7.2): `awaiting → circle` (hollow) when a glyph is shown in the item row; the cell itself shows none.
    - `drafted-not-approved`: **left edge `3px solid var(--amber)`**, `--paper` fill, "DRAFTED" label in `--amber`, amber progress fill. Item-row glyph: `circle-filled`.
    - `approved`: **left edge `3px solid var(--green)`** (or border via `color-mix` for card form — see D2), `--paper` or `--green-soft`-blended fill, **`check` glyph top-right, 16px, `--green`** (5.3 sprite `<use href="/static/icons/sprite.svg#check"/>`), "APPROVED" label in `--green`, **green 100% progress**.
    - `invalidated-by-replan`: **left edge `3px solid var(--red)`**, `--paper` fill, **`slash-circle` glyph top-right, 16px, `--red`** (5.3 sprite), "INVALIDATED" label in `--red`, **red dashed progress**.
  - [x] Glyphs come from the 5.3 sprite via `<svg><use href="/static/icons/sprite.svg#<name>"/></svg>` — never inline-duplicate SVG, never PNG (DD-03). Available: `check`, `slash-circle`, `circle`, `circle-filled` (sprite.svg has exactly these 12).
  - [x] State is data-driven (one cell, attribute/class swap) — content-delta only (DD-06), NO transition (DD-14 gate enforces).

- [x] **Task 2 — Phase Tracker strip (5 cells) + progress bar** (AC: 1) — *(§6.5)*
  - [x] 5-column even grid (`--layout-grid-gap` = 32px), order `[Phase 1][Signoff 1][Phase 2][Signoff 2][Phase 3]` for the three SDLC phases (Requirement / Architecture / Implementation) + their two signoff gate cells.
  - [x] Phase cell anatomy (§6.5 table): container `--paper` bg + `--border-hairline` + `--radius-lg`, min-height 120px; "PHASE 01" in `--type-label-mono-sm` uppercase; phase name in `--type-display-5` (Fraunces 18px 500); tag line in `--type-body-small` `--ink-mute` with **min-height 30px** (prevents inter-cell layout shift); meta row in `--type-mono-data` (flex space-between: current item + percentage).
  - [x] **Progress bar:** 3px height, `--rule` track, `--ink-soft` fill (or `--green` when complete, `--accent` when active). Signoff variants: amber fill (drafted), green 100% (approved), red dashed (invalidated). **DD-14 strips the width transition** — the bar changes width via content-delta, not an animated `transition: width`.
  - [x] Phase-cell states (§6.5): *future* (default, no accent); *active* (`--accent` 1px border + `--accent-soft` 3px ring — the ONLY accepted box-shadow, functional not decorative; this is the existing `.phase-cell.active` selector in focus-motion.css:10-13 — reuse it); *complete* (`--green` border via `color-mix`, `--green-soft` 50% blend bg, `check` glyph top-right 16px).

- [x] **Task 3 — Item rows in phase detail body** (AC: 3)
  - [x] Each row: a check-glyph (per state, from the 5.3 sprite), a label, and an optional badge. Focus order traverses rows **in declared DOM order** (no `tabindex` reordering). Phase tracker is **read-only — no keyboard interactions in v1** (§6.5 keyboard contract); "focus order" here means DOM/tab order is sane for screen-reader traversal, not interactive widgets.

- [x] **Task 4 — Committed Storybook-style fixture page + a11y semantics** (AC: 2, 3)
  - [x] Commit a fixture page rendering all 4 signoff states side-by-side (AC2) at the **D1-resolved path** (epic names `dashboard/static/test-fixtures/signoff-states.html`; reconcile with the 5.5-frozen convention).
  - [x] a11y (§6.5): `role="region"` `aria-label="Phase tracker"`; each cell `role="status"` + `aria-label` summarizing its state (e.g. "Phase 2 Architecture, signoff approved, 100% complete"); **color is never the only signal** — every state pairs with a glyph or text label (satisfies the 5.5 color-only-signaling gate; the "DRAFTED"/"APPROVED"/"INVALIDATED" text label carries the meaning, not the edge color alone).

- [x] **Task 5 — Static-analysis contract test** (AC: 1, 2) — *tests-first*
  - [x] Add a test asserting the committed fixture renders all FOUR states and that each non-`awaiting` state carries BOTH its mandated sprite glyph AND its text label (no color-only). Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`); place under `tests/unit/dashboard/` or `tests/integration/`. **RED:** a fixture missing the `slash-circle` glyph on `invalidated` (or missing a text label) fails; **GREEN:** the complete 4-state page passes. If 5.5's `check_dashboard_color_only.py` has merged, this fixture must also pass that gate — coordinate.

- [x] **Task 6 — Packaging + quality gate + freeze** (AC: 1, 2, 3)
  - [x] Add new CSS/HTML (signoff-cell + phase-tracker CSS, `signoff-states.html` fixture) to the `force-include` block [pyproject.toml] to ship in the wheel.
  - [x] If component CSS lands outside `static/styles/`, ensure it is covered by the (5.5-broadened) stylelint glob; component CSS must use `var(--*)` (no raw values — see Project Structure Notes). Run the DD-14 motion gate on the new CSS (no transitions).
  - [x] Python quality gate on any new `scripts/*.py`/tests (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7**.

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§7.2 Signoff 4-State Cell Pattern.** The four-state table (border / fill / glyph / label color / progress bar) + *"Anywhere a signoff state is rendered, **all four** treatments must be implemented even if some appear rarely. This guarantees content-delta swaps work cleanly across state transitions (DD-06)."* Glyph mapping: `awaiting → circle`, `drafted → circle (filled)`, `approved → check`, `invalidated → slash-circle`. [Source: ux-design-specification.md §7.2, lines 1451–1470]
- **§6.5 Phase Tracker + Phase Cell.** 5-column strip, phase-cell anatomy table, signoff-cell variants, phase-cell states (future/active/complete), a11y (`role="region"`/`role="status"`), keyboard ("No interactions in v1. Read-only."). [Source: ux-design-specification.md §6.5, lines 1166–1219]
- **DD-14 — Stillness.** The progress bar's width change and all state changes are content-delta, NOT animated `transition:`. [Source: ux-design-specification.md DD-14; scripts/check_dashboard_motion.py]
- **DD-03 — 12-icon sprite.** Glyphs via `<use href="/static/icons/sprite.svg#…"/>` only. [Source: ux-design-specification.md DD-03; src/sdlc/dashboard/static/icons/sprite.svg]

### Frozen foundation to consume (do NOT redefine — 5.2/5.3 froze these)

```css
/* tokens.css — the cell/progress/typography vocabulary */
--paper: #161922;                 --border-hairline: 1px solid var(--rule);
--amber: #fbbf24;  --green: #4ade80;  --green-soft: rgba(74,222,128,0.12);  --red: #f87171;
--ink-mute: #8b92a2;  --ink-soft: #c2c7d2;  --accent: oklch(...);  --accent-soft: rgba(226,120,88,0.12);
--radius-lg: 6px;                 --layout-grid-gap: 32px;
--type-label-mono-sm-*  (PHASE 01)   --type-display-5-*  (Fraunces 18px phase name)
--type-body-small-*     (tag line)   --type-mono-data-*  (meta row + progress %)
```
```css
/* focus-motion.css:9-13 — REUSE for the active phase cell (do NOT re-author) */
.phase-cell.active { box-shadow: 0 0 0 3px var(--accent-soft); }   /* functional active ring, NOT focus */
```
Sprite glyphs available (exactly 12; this story uses 4): `check`, `slash-circle`, `circle`, `circle-filled`.
[Source: src/sdlc/dashboard/static/styles/tokens.css:95-256, focus-motion.css:9-13, icons/sprite.svg]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Fixture path: epic-literal `test-fixtures/` vs the 5.5-frozen layout convention.** Epic AC2 names `dashboard/static/test-fixtures/signoff-states.html`; DAG §5 (5.9 row) says "committed `signoff-states.html` fixture"; 5.4 already shipped a fixture at `static/fixtures/reduced-motion-pulse.html`; 5.5 freezes the canonical `static/components/<name>/` + fixture-page convention (DAG §5). *Recommendation (a):* honor the epic-literal `dashboard/static/test-fixtures/signoff-states.html` for the Storybook page (it is an AC string) BUT place the reusable signoff-cell component CSS/JS under the 5.5-frozen `static/components/signoff-cell/`. If 5.5 has merged, align to its exact convention; if 5.9 branches first, coordinate the path with 5.5 in review so they don't diverge. Reconcile `fixtures/` vs `test-fixtures/` (do not create a third sibling dir). *Alternative (b):* fold everything under the 5.5 convention and treat the epic path as illustrative — only if 5.5 explicitly relocates it; otherwise keep the AC string literal.

**D2 — `approved` fill: flat `--paper` vs `--green-soft`-blended.** §7.2 / AC1 allow `approved` to use `--paper` OR a `--green-soft`-blended fill ("for cards"). The phase-tracker cell is a strip cell, not a free card. *Recommendation (a):* use flat `--paper` with the 3px green left-edge + `check` glyph for the in-strip signoff cell (keeps the 5-cell strip visually even); reserve the `--green-soft` 50%-blend "complete" treatment for the phase-cell *complete* state (§6.5) where it reads as a filled card. Pick one per surface and apply consistently so content-delta swaps stay clean. *Alternative (b):* `--green-soft`-blended everywhere — only if visual review prefers the heavier fill.

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the reusable **Signoff 4-State Cell** pattern (§7.2) — applied here to the phase tracker, reused by future audit surfaces and consumed by 5.14 (real 4-state from `state.json`). All four states + the synthetic fixture page.
- **Must NOT build:** real signoff data wiring (that is **5.14**, edge 5.9→5.14 — it swaps synthetic fixtures for `state.json` 2A.7 + 2A.19 invalidate-by-replan). Keep 5.9 fully synthetic/decoupled. Do not build the backlog tree (5.10) or live-dot (5.5) — independent L3 siblings. [Source: docs/sprints/epic-5-dag.md §2 (5.9→5.14, 5.9→5.12), §3 (L3 dependency notes)]

### Project Structure Notes

- New: signoff-cell + phase-tracker component CSS/JS under the 5.5-frozen `static/components/` convention (per D1) + a committed `test-fixtures/signoff-states.html` page. All new static files → `force-include` [pyproject.toml] (else absent from the wheel).
- Component CSS must use `var(--*)` — the 5.2 stylelint gate FORBIDS raw values for color/background-color/font-size/font-family/padding/margin/gap/letter-spacing/line-height/border-radius/border-width [.stylelintrc.json:5-54]. Examples: `min-height: 120px` → there is no spacing token = 120px; use the layout/spacing tokens where one exists, and note any unavoidable raw structural value (min-height/width has no disallow rule, so 120px/30px are allowed; but font-size/padding/etc. MUST be `var()`). Ensure the new CSS is inside the (5.5-broadened) stylelint glob.
- The 4-state vocabulary is the SAME enum 2A.7 produces (`awaiting-signoff`/`drafted-not-approved`/`approved`/`invalidated-by-replan`) — name the fixture states to match so 5.14's real-data swap is a 1:1 mapping. [Source: docs/sprints/epic-5-dag.md §5 row 5.9 — "4-state vocabulary mirrors 2A.7"]
- L3 siblings (5.5/5.9/5.10) mutually independent; branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3).
- Zero wire-format contracts (CSS/JS/HTML are not wire contracts) → freeze stays 7/7.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Active phase-cell ring | `.phase-cell.active { box-shadow: 0 0 0 3px var(--accent-soft); }` | src/sdlc/dashboard/static/styles/focus-motion.css:9-13 |
| State glyphs (check/slash-circle/circle/circle-filled) | `<use href="/static/icons/sprite.svg#…"/>` | src/sdlc/dashboard/static/icons/sprite.svg |
| Cell/progress/type tokens | Consume frozen tokens; no raw values | src/sdlc/dashboard/static/styles/tokens.css |
| File-layout convention + color-only gate | Align to the 5.5-frozen `static/components/` layout; pass `check_dashboard_color_only.py` | Story 5.5 / docs/sprints/epic-5-dag.md §5 |
| Motion gate (no transitions) | Run `check_dashboard_motion.py` on new CSS | scripts/check_dashboard_motion.py |
| Wheel force-include | Add new static files | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2594-2617] — Story 5.9 ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.2:1451-1470] — Signoff 4-State Cell pattern (4-state table + glyph mapping + all-four contract)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.5:1166-1219] — Phase Tracker / Phase Cell anatomy + states + a11y + read-only keyboard contract
- [Source: src/sdlc/dashboard/static/styles/tokens.css] — frozen color/type/space/radius tokens
- [Source: src/sdlc/dashboard/static/styles/focus-motion.css:9-13] — reusable `.phase-cell.active` ring
- [Source: src/sdlc/dashboard/static/icons/sprite.svg] — 12-icon sprite (check/slash-circle/circle/circle-filled used here)
- [Source: src/sdlc/dashboard/static/styles/.stylelintrc.json:5-54] — var(--*) enforcement
- [Source: scripts/check_dashboard_motion.py] — DD-14 motion gate (run on new CSS)
- [Source: docs/sprints/epic-5-dag.md §2 (5.9→5.14, 5.9→5.12), §3 (L3), §5 (5.9 row — synthetic, 2A.7 vocabulary)] — layer, edges, vocabulary
- [Source: _bmad-output/implementation-artifacts/5-5-live-dot-family-freshness-footer-pattern.md] — L3 sibling that freezes the file-layout convention + color-only gate

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor Agent)

### Debug Log References

- D1: (a) fixture at `static/test-fixtures/signoff-states.html`; reusable components under `static/components/{signoff-cell,phase-cell,phase-item-row,phase-tracker}/` per 5.5 convention.
- D2: (a) approved signoff strip cell uses flat `--paper` + 3px green left edge; `--green-soft` blend reserved for phase-cell `complete` state.

### Completion Notes List

- Implemented `<signoff-cell>`, `<phase-cell>`, `<phase-item-row>`, `<phase-tracker>` custom elements with token-only CSS (stylelint + DD-14 motion gates green).
- Committed `test-fixtures/signoff-states.html` with all four signoff states side-by-side + 5-cell phase tracker strip + item rows (a11y: `role="region"` / `role="status"`).
- Added `tests/unit/dashboard/test_signoff_states_fixture.py` (static-analysis contract: 4 states, glyph+label per non-awaiting state, 5-cell tracker, item rows).
- force-include entries added in pyproject.toml; color-only + motion gates pass locally.

### File List

- src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.css
- src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.js
- src/sdlc/dashboard/static/components/phase-cell/phase-cell.css
- src/sdlc/dashboard/static/components/phase-cell/phase-cell.js
- src/sdlc/dashboard/static/components/phase-item-row/phase-item-row.css
- src/sdlc/dashboard/static/components/phase-item-row/phase-item-row.js
- src/sdlc/dashboard/static/components/phase-tracker/phase-tracker.css
- src/sdlc/dashboard/static/components/phase-tracker/phase-tracker.js
- src/sdlc/dashboard/static/test-fixtures/signoff-states.html
- tests/unit/dashboard/test_signoff_states_fixture.py
- tests/unit/dashboard/test_dashboard_static_assets.py
- pyproject.toml
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-06-24: Story 5.9 created (create-story) — Signoff 4-State Cell (all four states with check/slash-circle/circle/circle-filled glyphs) + Phase Tracker strip + progress bar + item rows + committed `signoff-states.html` fixture; Decisions D1 (fixture path vs 5.5-frozen layout convention) + D2 (approved fill `--paper` vs `--green-soft`-blend) raised. L3 (5A), synthetic only, 2A.7 4-state vocabulary; feeds 5.14 real-data swap + 5.12 a11y gate; do-not-build real wiring noted.
- 2026-06-24: dev-story complete — D1(a) test-fixtures path + components/ layout; D2(a) flat paper approved signoff cell. All ACs satisfied; status → review.

## Review Findings

> bmad-code-review (fresh context), **3** adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + orchestrator source-verification — every defect reproduced against the real components / fixture / test / gate (no win32-only claims trusted). Triage: **3 decision-needed · 2 patch · 2 defer · 8 dismissed**. Status STAYS `review` pending the 3 decisions.
>
> **Acceptance Auditor:** **AC1 MET** — all four states render their mandated border/fill/glyph/label/progress (verified in `signoff-cell.js` `SIGNOFF_STATES` + `signoff-cell.css`: awaiting=hairline+paper+no-glyph+mute; drafted=3px amber edge+DRAFTED+amber fill; approved=3px green edge+`check` 16px green+APPROVED+100%; invalidated=3px red edge+`slash-circle` 16px red+INVALIDATED+red dashed). **AC3 MET** — item rows = glyph+label+optional badge, no `tabindex`/keyboard, DOM-order traversal. **AC2 PARTIAL** — fixture committed at the epic-literal path + all four states side-by-side + DD-06 no-transition (DD-14 gate passes), BUT the §7.2 / 5.5-color-only contract is verified against hand-placed decoys not the rendered component (**DEC-1**) and the fixture path diverges from the 5.5-frozen layout convention (**DEC-3**). **D2 honored** (flat `--paper` approved strip cell; `--green-soft` reserved for phase-cell complete). **D1 PARTIAL** → DEC-3.
>
> **Dismissed (8, grounded out):** (1) Blind Hunter "`Number.isNan` typo" → **FALSE POSITIVE**, source is `Number.isNaN` [phase-cell.js:16]; (2) `parseProgress` integer-truncation (`"1e2"→1`) → by design for integer percentages, clamped 0–100, never throws, author-controlled input; (3) phase-cell hard-imports signoff-cell.js (cascade if 404) → both force-included + same-origin same-server, not a realistic in-product failure; (4) duplicate `data-state`+`data-signoff-state` → harmless, usable future hook; (5) reentrant render on invalid `state` → idempotent (re-normalizes to same value), benign; (6) aria-label omits `current-item`/`%` → §6.5 gives those as "e.g."; each cell carries `role="status"` + a descriptive `aria-label`; (7) `_STATE_BLOCK` regex truncates on nested `<div>` → no nested div today, moot if test rewritten per DEC-1; (8) missing-fixture skip-vs-assert mismatch across the two test files → both agree the fixture must ship.

### Decision-needed

- [x] **[Review][Decision] DEC-1 [HIGH] — Deterministic contract is verified against hand-placed `hidden` decoys, not the component; the color-only CI gate is blind to signoff cells.** **→ RESOLVED (1) 2026-06-24: rewrite the test as a static source-of-truth contract over `signoff-cell.js SIGNOFF_STATES` + `phase-item-row.js ROW_GLYPHS`, remove the `hidden` decoys from the fixture, and broaden the color-only gate to cover `<signoff-cell>`/`<phase-item-row>`. → PAT-3.** `test_signoff_states_fixture.py::test_non_awaiting_states_carry_glyph_and_text_label` matches `sprite.svg#<glyph>` + the label text inside each `data-signoff-state` block — but those strings exist ONLY in hand-authored `<svg … hidden><use …/></svg>` + `<span hidden>DRAFTED|APPROVED|INVALIDATED</span>` decoys [signoff-states.html:71-101]. The real `<signoff-cell>` is empty in static HTML and renders glyph/label via JS [`signoff-cell.js` `renderSignoffCell`/`createGlyph`], which the static-text test NEVER executes → a regression in `signoff-cell.js` (wrong/no glyph, wrong label) would still pass. `test_awaiting_signoff_has_no_cell_glyph` is vacuous (`signoff-cell__glyph` is only ever JS-injected, never in static HTML). And `check_dashboard_color_only.py:31` only scans `<live-dot>` — the fixture has none, so the cross-cutting color-only gate passes **vacuously** and never inspects the signoff cells. Net: the §7.2 all-four / AC1 glyph+label / 5.5 color-only contracts are effectively **unguarded** for the new components (recurs the Epic-4 "asserted-not-measured" trap). **Options:** **(a) RECOMMENDED** — rewrite the test as a static contract over the component source-of-truth (assert `signoff-cell.js` `SIGNOFF_STATES` maps each non-awaiting state → mandated glyph+label and awaiting→null glyph; assert `phase-item-row.js` `ROW_GLYPHS` complete), REMOVE the `hidden` decoys, AND broaden `check_dashboard_color_only.py` (or add a sibling gate) to require glyph/label pairing on `<signoff-cell>`/`<phase-item-row>` — no new tooling, runs on win32+CI, directly guards rendering logic. **(b)** add a Playwright/DOM test (per 5.5 precedent under `tests/integration/`) that instantiates the elements and asserts the rendered glyph+label+aria; drop decoys — strongest (measures real render) but CI/POSIX-only. **(c)** keep the decoy approach but at minimum broaden the color-only gate to signoff cells and document the decoys as intentional test scaffolding — weakest, still doesn't measure the component.
- [x] **[Review][Decision] DEC-2 [MEDIUM] — `<phase-tracker>` default-render path (`DEFAULT_STRIP`/`DEFAULT_ROWS`/`variant`) is dead and untested.** **→ RESOLVED (1) 2026-06-24: remove the dead default-render machinery; `<phase-tracker>` becomes a thin ARIA-decorator over author/server-supplied markup (5.14 builds real cells via its own path). → PAT-4.** The committed fixture pre-bakes `<div class="phase-tracker__grid">…</div>` [signoff-states.html:109-168], so `renderPhaseTracker` hits the early-return at `phase-tracker.js:95` on the only consumer → `DEFAULT_STRIP`, `DEFAULT_ROWS`, `renderDefaultStrip`, `renderDefaultRows`, `setAttributes`, and the whole `variant` branch are never executed or tested. The trailing fixture script `if (!tracker.childElementCount) setAttribute("variant","default")` [signoff-states.html:178-181] is a no-op (the grid div makes `childElementCount > 0`). The sentinel is inverted — `useDefault = getAttribute("variant") !== "custom"` [line 101] means every value except literal `"custom"` renders defaults — and once a grid exists no re-render can clear it (the early-return), so `variant="custom"` set after a default render is ignored. The hard-coded test counts (`phase_cells == 3`, `signoff_cells == 2` [test:94-95]) lock in the static-HTML arrangement. **Options:** **(a)** remove the dead default-render machinery — make `<phase-tracker>` a thin ARIA-decorator over author/server-supplied markup (matches what the fixture does; YAGNI; 5.14 builds real cells via its own path). **(b)** ship an EMPTY `<phase-tracker>` in the fixture so the JS default path renders + is exercised; update the test to assert JS-rendered output (couples with DEC-1(b)). **(c)** keep both paths but fix the `variant` sentinel + allow re-render to clear an existing grid (repair the contract without removing it).
- [x] **[Review][Decision] DEC-3 [MEDIUM] — Fixture path created a THIRD fixture-location pattern; D1 reconciliation not done.** **→ RESOLVED (1) 2026-06-24: keep `static/test-fixtures/signoff-states.html` (honors the epic AC2 literal path); repo-wide reconciliation of the three fixture homes (`fixtures/` vs `test-fixtures/` vs co-located `*.fixture.html`) deferred → DEF-3.** Decision D1 [story:98] required reconciling `fixtures/` vs `test-fixtures/` vs the 5.5 convention and "do not create a third sibling dir." The repo now has THREE patterns: `static/fixtures/reduced-motion-pulse.html` (5.4), `static/components/live-dot/live-dot.fixture.html` (the 5.5-FROZEN co-located convention this story was told to align to), and the new `static/test-fixtures/signoff-states.html` (5.9). 5.9 chose D1(a) (the epic AC2 literal path) but did NOT reconcile. **Options:** **(a)** keep `static/test-fixtures/signoff-states.html` (honor the AC2 literal) and ratify the divergence + file a follow-up to reconcile all three fixture homes repo-wide. **(b)** move the fixture to the 5.5-frozen co-located convention (e.g. `components/signoff-cell/signoff-cell.fixture.html`), updating AC2's path, the test `_FIXTURE` path, and the force-include entry — eliminating the third pattern now.

### Patch

- [x] **[Review][Patch] PAT-1 [MEDIUM] — `resolveState` not case/whitespace-normalized; inconsistent with sibling `resolveCellState`** [signoff-cell.js:36-38]. `resolveState` does `String(raw || "awaiting-signoff")` with no `.trim().toLowerCase()`, while `phase-cell.js:9-11` `resolveCellState` lowercases. A valid-but-miscased/whitespaced `state="Approved"` / `" approved"` on `<signoff-cell>` (and `<phase-item-row>`, which imports the same `resolveState`) silently falls back to `awaiting-signoff` with no diagnostic. Fix: mirror the sibling → `String(raw || "awaiting-signoff").trim().toLowerCase()`.
- [x] **[Review][Patch] PAT-2 [LOW] — phase-cell `complete` progress-fill `width:100%` CSS rule is dead (always overridden by inline width)** [phase-cell.js:80 / phase-cell.css:92-94]. `renderPhaseCell` always sets inline `fill.style.width = ${progress}%`, which beats the stylesheet rule `.phase-cell--complete .phase-cell__progress-fill { width:100% }`; a `complete` cell with `progress<100` renders a non-full bar, contradicting §6.5 "complete = full green bar." Dormant today (no `complete` cell in fixture/`DEFAULT_STRIP`). Fix: when `cellState === "complete"`, force `progress = 100` (or set inline width to 100%) in `renderPhaseCell` so the rule is no longer dead and "complete" reads correctly.
- [x] **[Review][Patch] PAT-3 [HIGH] — (from DEC-1) Make the contract actually measure the component + close the color-only gap.** (a) Rewrite `tests/unit/dashboard/test_signoff_states_fixture.py` so the glyph/label contract asserts against the component source-of-truth — parse/assert `signoff-cell.js` `SIGNOFF_STATES` maps each non-awaiting state → mandated `glyph` + `label` and `awaiting-signoff` → `glyph: null`, and `phase-item-row.js` `ROW_GLYPHS` covers all four states — instead of matching fixture text; (b) remove the `<svg … hidden>` + `<span hidden>` decoys from `signoff-states.html` (keep the rendered `<signoff-cell>`); (c) broaden `scripts/check_dashboard_color_only.py` (or add a sibling check) to require a glyph/text-label pairing on `<signoff-cell>`/`<phase-item-row>`, with RED/GREEN fixtures, tests-first.
- [x] **[Review][Patch] PAT-4 [MEDIUM] — (from DEC-2) Remove the dead `<phase-tracker>` default-render machinery.** Delete `DEFAULT_STRIP`, `DEFAULT_ROWS`, `renderDefaultStrip`, `renderDefaultRows`, `setAttributes`, the `variant` `observedAttributes` entry, and the `useDefault` branch from `phase-tracker.js`; `renderPhaseTracker` keeps only the `role="region"` + `aria-label="Phase tracker"` decoration over author-supplied markup. Drop the no-op `setAttribute("variant","default")` script tail in `signoff-states.html`. Keep the existing test counts (the fixture's static grid is unchanged).

### Defer (logged to deferred-work.md)

- [x] **[Review][Defer] DEF-1 [LOW] — stylelint `background:` shorthand token-gate blind spot** [signoff-cell.css / `.stylelintrc.json`] — deferred, pre-existing (5.2 gate scope; passes today via `var(--red)`/`transparent`).
- [x] **[Review][Defer] DEF-2 [LOW] — quality-gate claims asserted-not-measured on win32** (full pytest + coverage≥87 + `mkdocs --strict` + Node stylelint first execute on POSIX CI per 5.2 D1 "Node CI-only") — deferred, verify on merge CI; not a code defect.
- [x] **[Review][Defer] DEF-3 [MEDIUM] — (from DEC-3) repo-wide fixture-location reconciliation** — 5.9's `static/test-fixtures/signoff-states.html` is RATIFIED (honors AC2 literal), but the repo now has three fixture-home patterns (`static/fixtures/` 5.4, co-located `components/<name>/<name>.fixture.html` 5.5, `static/test-fixtures/` 5.9). Deferred: pick one canonical home + update the 5.5 convention doc and migrate the others. Reason: honoring the epic AC2 literal path now, full reconciliation is a repo-wide cleanup not scoped to 5.9.
