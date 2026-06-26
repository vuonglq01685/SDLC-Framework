# Story 5.11: Tabs + Activity Feed + Empty State + Section-Block Heading + Editorial Scanning Rhythm

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L4 (5A). L4 = {5.6, 5.7, 5.8, 5.11}, max 4 parallel worktrees (cap-saturating). Depends on 5.5 (freshness-footer FROZEN) (+ 5.2 tokens, 5.3 sprite) — ALL done+merged. ON THE CRITICAL-PATH SPINE: 5.2→5.4→5.5→5.11→5.19→5.20→5.22 (depth-7). Edges: 5.5→5.11; downstream 5.11→5.16 (real agent_runs.jsonl rendering — reuses the feed render seam), 5.11→5.19 (STOP banner consumes the empty-state + tabs), 5.11→5.12 (a11y convergence gate). Worktree: epic-5/5-11-tabs-activity-feed-empty. Branch from main, linear merge, rebase between L4 merges (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). SYNTHETIC fixtures only — real agent-runs read is 5.16; the actual STOP banners are 5.19 (this story builds only the empty-state shown when there are zero STOPs). The Tabs WAI-ARIA keyboard pattern mirrors the 5.10 backlog-tree roving-tabindex approach. -->

## Story

As any team member navigating dashboard sections,
I want Tabs for section navigation, Activity Feed for last 50 agent runs, Empty State (anti-cynicism, never blank silent) for the alert column when no STOP, plus the cross-cutting Section-Block Heading and Editorial Scanning Rhythm patterns,
So that supporting components and page-level rhythm are consistent across surfaces (UX-DR7, UX-DR8, UX-DR15, UX-DR28, UX-DR29, §6.8, §7.8, §7.10).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.11, lines 2650–2672).

**AC1 — Tabs (semantic + keyboard)**
- **Given** the Tabs component **When** rendered for section navigation **Then** the implementation uses semantic `role="tablist"` + `role="tab"` + `role="tabpanel"` with proper `aria-selected` and `aria-controls`
- **And** keyboard navigation: Left/Right arrows move focus, Enter/Space activates, Home/End jumps to first/last

**AC2 — Activity Feed**
- **Given** the Activity Feed **When** rendered with synthetic data of 50 agent runs **Then** entries show timestamp, agent name, target id, outcome, duration
- **And** entries are bounded to the last 50 (older entries scroll out)
- **And** the feed updates on each poll without re-rendering unaffected entries

**AC3 — Empty State (anti-cynicism)**
- **Given** the Empty State **When** the alert column has no STOP banners to render **Then** the empty state shows a friendly anti-cynicism message (e.g., "All clear — no STOPs in flight")
- **And** the empty state still includes the freshness footer
- **And** silent blank is forbidden

**AC4 — Section-Block Heading + Editorial Scanning Rhythm**
- **Given** every main section ("Phase tracker", "Backlog", "Activity", "Alerts") **When** rendered **Then** they share the Section-Block Heading treatment (per §7.8): identical structure, typography, eyebrow/heading hierarchy
- **And** page-level section ordering follows the Editorial Scanning Rhythm (§7.10) for trust UX

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the **Tabs WAI-ARIA keyboard contract (AC1)** is testable behavior → tests-first via the Playwright surface (Story 5.4 D2): assert Left/Right move focus (roving tabindex, exactly one tab stop), Home/End jump, Enter/Space flips `aria-selected` + reveals the controlled `tabpanel`, and arrows NEVER drop focus to `<body>` (the 5.10 leaf-focusability RED-witness lesson). The **5-field / last-50 / incremental-render (AC2)**, the **empty-state contract (AC3)**, and the **section-block-heading / ordering (AC4)** are deterministic → static-analysis/DOM contracts over the committed fixtures. Tab/feed/heading CSS is `test-along`. Resolve Decisions D1–D5 BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (Activity Feed field count: AC 5-field vs §6.8 4-field) + D2 (empty-state copy: AC "All clear…" vs §6.8 "No active alerts" ban) + D3 (tab-type token choice) + D4 (Section-Block Heading: reusable element vs documented pattern) + D5 (error-outcome glyph: §6.8 `alert-triangle` is ABSENT → use frozen `error`) BEFORE coding** (AC: 1, 2, 3, 4)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). Align the component layout to the 5.5-frozen `static/components/<name>/` convention.

- [x] **Task 1 — Tabs: semantic markup + full WAI-ARIA keyboard** (AC: 1) — *tests-first*
  - [x] `role="tablist"` container; each `role="tab"` with `aria-selected="true|false"` + `aria-controls="<panel-id>"`; each `role="tabpanel"` with `aria-labelledby` → its tab. Active tab = `--border-accent` underline; inactive = `--ink-mute`; counter pill bg `--rule`(inactive)→`--accent`(active). State change = content-class swap, **NO transition** (DD-14). [§6.8 ux:1322-1324; epics:2652-2655]
  - [x] **Mirror the 5.10 backlog-tree roving-tabindex pattern** (`collectVisibleExpanders`/`setRovingTabindex`): exactly one `role="tab"` has `tabIndex=0`, others `-1`; Left/Right index ±1, Home→first, End→last; `Enter`/`Space` activate (manual-activation variant — focus moves on arrow, selection on Enter/Space). `event.preventDefault()` on every handled key. Reuse the existing focus ring — `focus-motion.css` already names `[role="tab"]:focus-visible` AND `.tab:focus-visible` (no new focus CSS).
  - [x] **Apply the 5.10 review lessons:** (a) never make a `role="tab"` `visibility:hidden` (a hidden element is non-focusable → `.focus()` drops to `<body>`); (b) PAT-2 — read live active-tab state from `host._fixtureRef` (set on EVERY render), do NOT close over the fixture captured at first bind (real trap for 5.16's data swap).

- [x] **Task 2 — Activity Feed: 5 fields, last-50, incremental content-delta render** (AC: 2) — *tests-first*
  - [x] Each entry shows **5 fields** (D1, AC binding): timestamp (`--type-mono-data`), agent name, target id, outcome, duration. Outcome glyph: `check`=approved, `slash-circle`=rejected, `error`=error (D5 — `alert-triangle` is NOT in the sprite). Each outcome glyph carries adjacent text (color-only gate). [§6.8 ux:1326-1328; epics:2657-2661]
  - [x] Bounded to the last 50 (older scroll out) → fixed `max-height` scroll region; synthetic fixture has exactly 50 runs.
  - [x] **Incremental render (DD-06):** new entries **prepend** on poll; existing DOM nodes are untouched ("only changed sections re-render", NFR-PERF-4). Keyed-diff prepend, NOT `replaceChildren()`. No fade-in / no CSS transition. Test: insert a synthetic new entry → assert existing nodes retain identity, only the new node prepends. (5.16 swaps the synthetic source for real `agent_runs.jsonl`; build the render SEAM here.)

- [x] **Task 3 — Empty State (anti-cynicism) + freshness footer** (AC: 3) — *tests-first*
  - [x] Shown when the alert column has zero STOP banners. `--paper` bg, dashed border (`--border-dashed`), `--ink-dim` centered text. Message per D2 (measured anti-cynicism phrasing). **Still includes `<freshness-footer>`** (reuse the element). **Silent blank is FORBIDDEN** (UX-DR15). [§6.8 ux:1381-1383; epics:2663-2667]

- [x] **Task 4 — Section-Block Heading (§7.8) + Editorial Scanning Rhythm (§7.10)** (AC: 4)
  - [x] Section-Block Heading (cross-cutting): serif heading (`--type-display-3` 22px or `--type-display-4` 20px, `letter-spacing -0.01em`) + right-aligned mono count (`--type-mono-data` `--ink-mute`, e.g. "12 stories"); `flex; justify-content: space-between; align-items: baseline`; `--space-6`–`--space-7` bottom margin. Every main section ("Phase tracker", "Backlog", "Activity", "Alerts") adopts it (D4: a reusable element/markup + fixture). [§7.8 ux:1550-1562]
  - [x] Editorial Scanning Rhythm (page-level): canonical order Masthead → KPI strip → Tabs → Phase tracker → Main content (main col: backlog/phase-detail/focus; side col: resume → STOP → activity feed). Assert ordering via a committed fixture page. [§7.10 ux:1582-1597]

- [x] **Task 5 — Committed synthetic fixtures + static-analysis contract tests** (AC: 1, 2, 3, 4) — *tests-first*
  - [x] Commit `tabs.fixture.html` (+ activity feed + empty state + section-heading + rhythm-order fixture page). Add tests: Tabs markup contract (tablist/tab/tabpanel, every tab has `aria-selected` + `aria-controls` resolving to a real panel); feed (exactly 50 entries, each with all 5 fields); empty state (contains `<freshness-footer>`, non-empty visible text, no silent blank); section-block heading present on every named section; fixture section order matches §7.10. Plus the Playwright tabs keyboard test. **RED:** a missing `aria-controls`, a 49/51-entry feed, a blank empty-state, or out-of-order sections fail; **GREEN:** correct. Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`).

- [x] **Task 6 — Packaging + quality gate + freeze** (AC: 1, 2, 3, 4)
  - [x] Add new CSS/JS/HTML (tabs, activity-feed, empty-state, section-heading, fixtures) to the `force-include` block [pyproject.toml].
  - [x] Component CSS uses `var(--*)` only (5.2 stylelint gate); run DD-14 motion gate (no transitions — tab/feed changes are content/class swaps), DD-08 no-framework, DD-09 no-data-theme, and the 5.5 color-only gate (outcome glyphs + empty-state carry text).
  - [x] Python quality gate on any new `scripts/*.py`/tests (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7**.

### Review Findings

> bmad-code-review (2026-06-26) — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + orchestrator source-verification. Reviewed uncommitted working-tree changes (story in `review`). Triage: **0 decision-needed, 4 patch, 8 defer, 2 dismissed**. Acceptance Auditor: **AC1 MET, AC2 PARTIAL** (HIGH feed-ordering defect), **AC3 MET, AC4 MET**; D1–D5 implemented as resolved (a); no anti-scope-creep; no XSS (textContent-only). The HIGH was independently surfaced by ALL THREE layers and reproduced against the real `activity-feed.js`.

**Patch (unchecked — fix before close-out):**

- [x] [Review][Patch] **(HIGH) Activity feed renders oldest-on-top and evicts the *newest* entry — AC2 "older entries scroll out" inverted** [src/sdlc/dashboard/static/components/activity-feed/activity-feed.js:118-127] — `buildSyntheticEntries` is newest-first (`entries[0]`=run-050 @10:59), but the render loop forward-iterates with `insertBefore(node, list.firstChild)` → DOM ends oldest-on-top, newest-at-bottom; the `removeChild(list.lastChild)` trim then evicts the *newest* historical run on each poll. Fix: insert in reverse (oldest→newest) so newest lands on top and `lastChild` is genuinely the oldest. Triple-confirmed (blind+edge+auditor), source-verified.
- [x] [Review][Patch] **(MEDIUM) Feed incremental/count tests are source-substring greps that cannot catch the HIGH defect** [tests/unit/dashboard/test_tabs_activity_feed_fixture.py:68-85] — `assert "buildSyntheticEntries(50)" in js` and the `insertBefore`/`replaceChildren` substring checks never render a DOM, so the inverted order + wrong-end eviction sailed through green. Add a behavioral (Playwright) feed test: 50 entries, newest-on-top order, and a poll prepends the newest + evicts the oldest while preserving existing node identity (RED against current code → GREEN after the F1 fix).
- [x] [Review][Patch] **(MEDIUM) Empty-state "not silently blank" assertion matches any HTML** [tests/unit/dashboard/test_tabs_activity_feed_fixture.py:100] — `re.search(r">\s*\S", html)` matches the surrounding `<h1>`/`<title>` markup regardless of what `<empty-state>` renders, so UX-DR15 ("silent blank FORBIDDEN") is unenforced. Replace with a behavioral check that the rendered `.empty-state__message` carries non-empty text + a real `<freshness-footer>`.
- [x] [Review][Patch] **(LOW) `renderTabs` throws on a payload missing both `activeTabId` and `tabs`** [src/sdlc/dashboard/static/components/tabs/tabs.js:176] — `data.tabs[0]?.id` dereferences `data.tabs[0]` before the `?.`; inconsistent with line 187's guarded `data.tabs || []`. Fix: `data.tabs?.[0]?.id`.

**Deferred (logged to deferred-work.md → "code review of 5-11… (2026-06-26)"):**

- [x] [Review][Defer] Shared module-singleton mutation across instances [tabs.js:88; activity-feed.js:135] — deferred, latent (single-instance synthetic; immutability + multi-instance state leak)
- [x] [Review][Defer] Missing-id feed entry duplicates on every poll [activity-feed.js:69,119] — deferred, 5.16 real-data seam
- [x] [Review][Defer] Unknown outcome → `error` glyph + "Error" mislabels non-failures [activity-feed.js:42-43] — deferred, 5.16
- [x] [Review][Defer] Missing feed field renders literal "undefined" [activity-feed.js:73-85] — deferred, 5.16
- [x] [Review][Defer] `renderEmptyState({message:""})` blanks the message on the function path [empty-state.js:12] — deferred, 5.19 consumer
- [x] [Review][Defer] `renderSectionBlockHeading({count:0})` blanks a numeric-0 count [section-heading.js:17] — deferred, 5.14/5.15 real counts
- [x] [Review][Defer] No standalone `section-heading.fixture.html` (D4 named "+ .fixture.html") [components/section-heading/] — deferred, non-AC-blocking
- [x] [Review][Defer] Remaining unit "contract" tests are substring greps (tabs markup / 5-fields / heading export) [test_tabs_activity_feed_fixture.py:45-76,109-113] — deferred, AC1 behaviorally covered by Playwright

**Dismissed (noise/handled):** Playwright `!= "body"` assertion is redundant but harmless (the real focus-drop guard is `assert active`); duplicated Change Log block in this story doc (cosmetic).

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§6.8 Tabs.** *"Editorial tab bar above the main content panel. Active tab carries `--border-accent` underline; inactive tabs are `--ink-mute`. Counter pill follows tab text, swapping bg between `--rule` (inactive) and `--accent` (active). No transition (DD-14); state changes are content-class swaps. `role="tablist"` + `role="tab"` + `aria-selected`. Arrow-key navigation per WAI-ARIA tabs pattern."* [Source: ux-design-specification.md §6.8:1322-1324]
- **§6.8 Activity Feed.** *"List of last 50 agent runs (PRD FR42). Each row: timestamp (mono), agent name, outcome glyph (`check` for approved, `slash-circle` for rejected, `alert-triangle` for error), one-line summary. Container is a scroll region with fixed max-height. New entries prepend on poll; positional shift is the perception of change (DD-06). No fade-in."* [Source: ux-design-specification.md §6.8:1326-1328] — NOTE the field-count + glyph conflicts (D1, D5).
- **§6.8 Empty State.** *"Used in alert column when no STOP exists. `--paper` bg, `--border-hairline` (dashed), `--ink-dim` text, centered: 'No active alerts'. The dashed border distinguishes it from an active alert; no celebratory copy ('All clear!', '✓ Healthy') — that would violate emotional principle #6."* [Source: ux-design-specification.md §6.8:1381-1383] — NOTE the copy conflict with epic AC + missing-footer (D2).
- **§7.8 Section-Block Heading.** Heading = `--type-display-3`/`--type-display-4` (Fraunces 22/20px), `letter-spacing -0.01em`; Count (right) = `--type-mono-data` `--ink-mute`; Layout = `flex; justify-content: space-between; align-items: baseline`; bottom margin `--space-6`–`--space-7`. *"Every main page section opens with this heading. Sections without headings are forbidden."* [Source: ux-design-specification.md §7.8:1550-1562]
- **§7.10 Editorial Scanning Rhythm.** Canonical top→bottom order: 1. Masthead, 2. KPI strip, 3. Tabs (if present), 4. Phase tracker, 5. Main content (main col: backlog tree / phase detail / story focus; side col: resume card → STOP banners → activity feed). *"Sections appear in this order on every dashboard page."* [Source: ux-design-specification.md §7.10:1582-1597]

### Frozen foundation to consume (do NOT redefine — 5.2/5.3/5.5 froze these)

```css
/* tokens.css — tabs/feed/empty/heading vocabulary */
--border-accent:2px solid var(--accent) (active tab underline);  --ink-mute(inactive tab);  --rule/--accent (counter pill bg);
--type-label-mono-{…}/--type-label-mono-sm-{…} (tab text — D3);  --type-mono-pill-* (counter pill);
--type-mono-data-{size:11px,weight:500} (feed timestamp + heading count);
--type-display-3-{size:22px,…ls:-0.01em} / --type-display-4-{size:20px,…} (section heading);  --font-serif;
--paper(empty bg);  --border-dashed:1px dashed var(--rule) (empty border);  --ink-dim(empty text);
--space-6:14px; --space-7:16px (heading margin);
```
```text
sprite.svg — outcome glyphs: `check`, `slash-circle` PRESENT; `alert-triangle` ABSENT (12-icon set has `error`+`warning` instead) → D5 maps error→`error`.
backlog-tree.js (5.10) — roving-tabindex pattern to MIRROR: collectVisibleExpanders / setRovingTabindex (tabIndex 0 vs -1) / bindTreeKeyboard keydown switch (preventDefault per key) / `_keyboardBound` once-guard. PAT-2: read live data from host._fixtureRef set on EVERY render. Leaf-focus lesson: never make a roving target visibility:hidden. [backlog-tree.js:330-376,388-473,532-535]
<freshness-footer last-poll variant now> — reuse in the empty state. [freshness-footer.js:62-90]
focus-motion.css ALREADY names [role="tab"]:focus-visible AND .tab:focus-visible → DD-15 ring auto-applies; NO new focus CSS. [focus-motion.css:19-24]
```
[Source: tokens.css:103-241; icons/sprite.svg; backlog-tree.js:330-535; freshness-footer.js:62-90; focus-motion.css:19-24]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Activity Feed field count (HIGH).** §6.8 (ux:1328) = 4 fields (timestamp / agent name / outcome glyph / one-line summary); epic AC (epics:2659) = **5 fields** (timestamp, agent name, **target id**, outcome, **duration**). *Recommendation (a):* follow the **epic AC (5 fields)** as the acceptance contract; treat §6.8's "one-line summary" as an additional optional cell or fold it under "outcome". Document the reconciliation.

**D2 — Empty-state copy (HIGH).** §6.8 (ux:1383) mandates "No active alerts" and explicitly BANS "All clear!" (emotional principle #6); epic AC (epics:2665) gives the example "All clear — no STOPs in flight" + requires a freshness footer (§6.8 omits one). *Recommendation (a):* keep the **freshness footer** (AC binding); for copy, use a measured anti-cynicism phrasing that satisfies the AC's "friendly … (e.g., …)" illustrative example WITHOUT the banned exclamatory "All clear!" form — e.g. "No STOPs in flight" / "No active alerts — pipeline clear". Raise as a D-label; PO ratifies the exact string.

**D3 — Tab-type token (MED).** No token is literally named for tab-label text. *Recommendation (a):* `--type-label-mono` (11px/500/0.12em) for the editorial tab register; counter pill `--type-mono-pill` (10px/500/0.12em). Document the choice; no new token (avoids unfreezing tokens.css).

**D4 — Section-Block Heading: reusable element vs documented pattern (LOW).** §7.8 is cross-cutting markup. *Recommendation (a):* a small reusable element/markup + `.fixture.html` + CSS (display-3/4 + mono-count flex), referenced by other sections — matches the "build cross-cutting once, reuse" principle. Default heading size `--type-display-3` (22px) unless density argues for display-4.

**D5 — Error-outcome glyph: `alert-triangle` is ABSENT from the frozen sprite (LOW→load-bearing).** §6.8 names `alert-triangle` for the error outcome, but the 12-icon sprite ships `check`/`slash-circle`/`error`/`warning` (no `alert-triangle`). *Recommendation (a):* map the error outcome to the frozen **`error`** glyph (or `warning`) — NO ADR needed (the >12-icons→ADR gate from 5.3 does not fire; we reuse an existing icon). Document the §6.8 `alert-triangle`→`error` drift.

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the reusable **Tabs** (full WAI-ARIA + roving-tabindex keyboard) + **Activity Feed** (5-field, last-50, incremental render SEAM) + **Empty State** (anti-cynicism + freshness footer) + the cross-cutting **Section-Block Heading (§7.8)** + **Editorial Scanning Rhythm (§7.10)** patterns. SYNTHETIC fixture data only (50 synthetic agent runs).
- **Must NOT build:** real `agent_runs.jsonl` reads — that is **5.16** (edge 5.11→5.16, twin; build the render seam so 5.16 can swap the source); the actual STOP banner / 7-trigger rendering — that is **5.19** (edge 5.11→5.19; 5.11 builds only the empty-state shown when there are zero STOPs); real DORA / signoff / hierarchy (5.13/5.14/5.15); the full live page-shell assembly beyond fixtures (the §7.10 ordering is asserted via committed fixtures). No modals/toasts/forms/client-routing/skeleton loaders; no CSS `transition:`/transforms except the frozen live-dot pulse (DD-14/DD-06). [Source: docs/sprints/epic-5-dag.md §2 (5.11→5.16/5.19/5.12, twin:241), §3 (L4:213), §4 (critical path:254), §6 (5.11 row:289, 5.16 row:294, 5.19 row:297)]

### Project Structure Notes

- New: `static/components/tabs/`, `static/components/activity-feed/`, `static/components/empty-state/`, `static/components/section-heading/` (CSS/JS/fixture) under the 5.5-frozen convention. All new static files → `force-include` [pyproject.toml].
- Component CSS must use `var(--*)` — the 5.2 stylelint gate (at `src/sdlc/dashboard/static/styles/.stylelintrc.json`) FORBIDS raw color/font-size/padding/letter-spacing/etc.
- 5.11 is the FIRST tab widget — the Tabs keyboard handling mirrors the 5.10 backlog-tree roving-tabindex (single tab stop, Arrow/Home/End). `[role="tab"]`/`.tab` `:focus-visible` is pre-wired in `focus-motion.css` (5.4) — no new focus CSS.
- **Critical-path node:** 5.11 is on the depth-7 spine (5.2→5.4→5.5→5.11→5.19→5.20→5.22) — it must merge cleanly so 5.19 (STOP banner) is unblocked.
- L4 siblings (5.6/5.7/5.8/5.11) mutually independent; cap-saturating. Branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3).
- Zero wire-format contracts (CSS/JS/HTML are not wire contracts) → freeze stays 7/7.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Tabs roving-tabindex / Arrow / Home / End keyboard | mirror backlog-tree `collectVisibleExpanders`/`setRovingTabindex`/`bindTreeKeyboard` + PAT-2 + leaf-focus lesson | src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js:330-535 |
| Tab focus ring (DD-15) | `[role="tab"]`/`.tab` `:focus-visible` already wired | src/sdlc/dashboard/static/styles/focus-motion.css:19-24 |
| Empty-state freshness footer | `<freshness-footer last-poll variant>` (composes live-dot) | src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:62-90 |
| Outcome glyphs (check/slash-circle/error) | `<use href="/static/icons/sprite.svg#…">` (frozen; D5 error→`error`) | src/sdlc/dashboard/static/icons/sprite.svg |
| Tabs/feed/empty/heading tokens | Consume frozen tokens (D3 tab type) | src/sdlc/dashboard/static/styles/tokens.css:103-241 |
| Playwright test surface | Extend the 5.4/5.10 Playwright surface for tabs keyboard | tests/integration/test_dashboard_backlog_tree.py |
| Static-analysis contract test pattern | mirror `test_backlog_tree_fixture.py` | tests/unit/dashboard/test_backlog_tree_fixture.py |
| Motion / no-framework / color-only gates | Run on the new components | scripts/check_dashboard_motion.py / _no_framework.py / _color_only.py |
| Wheel force-include | Add new static files | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2644-2672] — Story 5.11 ACs (verbatim above); UX-DR7:197, UX-DR8:198, UX-DR15:205, UX-DR28:222, UX-DR29:223
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.8:1322-1328, 1381-1383] — Tabs / Activity Feed / Empty State
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.8:1550-1562, §7.10:1582-1597] — Section-Block Heading + Editorial Scanning Rhythm
- [Source: src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js:330-535] — roving-tabindex pattern + PAT-2 + leaf-focus lesson (mirror for Tabs)
- [Source: src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:62-90] — `<freshness-footer>` (empty state)
- [Source: src/sdlc/dashboard/static/icons/sprite.svg] — `check`/`slash-circle`/`error` present; `alert-triangle` ABSENT (drives D5)
- [Source: src/sdlc/dashboard/static/styles/focus-motion.css:19-24] — `[role="tab"]`/`.tab` focus ring pre-wired
- [Source: src/sdlc/dashboard/static/styles/tokens.css:103-241] — `--border-accent`, `--border-dashed`, `--type-display-3/4`, `--type-mono-data`, `--ink-dim`
- [Source: src/sdlc/dashboard/static/styles/.stylelintrc.json] — var(--*) enforcement (drives D3)
- [Source: docs/sprints/epic-5-dag.md §2 (5.11→5.16/5.19/5.12, twin:241), §3 (L4:213), §4 (critical path:254-259), §6 (5.11 row:289 / 5.16:294 / 5.19:297)] — layer, critical path, edges, "consumed by 5.16/5.19"
- [Source: _bmad-output/implementation-artifacts/5-10-backlog-tree-pill-family-inline-code.md:46,71,74,119] — keyboard contract + DEC-1 leaf-focus + PAT-2 stale-fixture + component convention

## Dev Agent Record

### Agent Model Used

Composer

### Debug Log References

### Completion Notes List

- D1-D5 resolved per story recommendations: (D1) 5-field feed per epic AC; (D2) "No STOPs in flight" + freshness footer; (D3) --type-label-mono + --type-mono-pill; (D4) reusable section-block-heading element; (D5) error outcome maps to frozen `error` glyph.
- Implemented tabs (WAI-ARIA manual-activation keyboard mirroring 5.10 roving tabindex), activity feed (50 synthetic runs, incremental prepend), empty state (anti-cynicism + freshness footer), section-block heading, and editorial scanning rhythm fixture.
- 17 unit contract tests + 5 Playwright keyboard tests added; full suite 4037 passed; dashboard gates + stylelint green.

### File List

- src/sdlc/dashboard/static/components/tabs/tabs.js
- src/sdlc/dashboard/static/components/tabs/tabs.css
- src/sdlc/dashboard/static/components/tabs/tabs.fixture.html
- src/sdlc/dashboard/static/components/activity-feed/activity-feed.js
- src/sdlc/dashboard/static/components/activity-feed/activity-feed.css
- src/sdlc/dashboard/static/components/activity-feed/activity-feed.fixture.html
- src/sdlc/dashboard/static/components/empty-state/empty-state.js
- src/sdlc/dashboard/static/components/empty-state/empty-state.css
- src/sdlc/dashboard/static/components/empty-state/empty-state.fixture.html
- src/sdlc/dashboard/static/components/section-heading/section-heading.js
- src/sdlc/dashboard/static/components/section-heading/section-heading.css
- src/sdlc/dashboard/static/test-fixtures/editorial-scanning-rhythm.html
- tests/unit/dashboard/test_tabs_activity_feed_fixture.py
- tests/integration/test_dashboard_tabs.py
- pyproject.toml
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-06-25: Story 5.11 created (create-story, "tạo US cho layer tiếp theo" → L4 batch with 5.6/5.7/5.8) — Tabs (full WAI-ARIA `tablist`/`tab`/`tabpanel` + roving-tabindex keyboard mirroring 5.10) + Activity Feed (5-field, last-50, incremental content-delta render seam) + Empty State (anti-cynicism + freshness footer, never blank) + cross-cutting Section-Block Heading (§7.8) + Editorial Scanning Rhythm (§7.10). Decisions D1 (feed 5-field AC over §6.8 4-field) / D2 (empty-state copy reconcile AC vs §6.8 ban + keep footer) / D3 (tab-type token) / D4 (section-heading reusable element) / D5 (`alert-triangle` absent → map error→frozen `error` glyph, no ADR) raised. L4 (5A) + critical-path spine node; synthetic only; depends on 5.5 + 5.2 + 5.3; feeds 5.16 (real agent runs) + 5.19 (STOP banner) + 5.12 a11y gate. Do-not-build real agent-runs/STOP-banner noted.
- 2026-06-26: Story 5.11 implemented (dev-story) — all ACs satisfied; D1-D5 (a); 4037 tests pass; freeze 7/7 unchanged.
- 2026-06-25: Story 5.11 created (create-story, "tạo US cho layer tiếp theo" → L4 batch with 5.6/5.7/5.8) — Tabs (full WAI-ARIA `tablist`/`tab`/`tabpanel` + roving-tabindex keyboard mirroring 5.10) + Activity Feed (5-field, last-50, incremental content-delta render seam) + Empty State (anti-cynicism + freshness footer, never blank) + cross-cutting Section-Block Heading (§7.8) + Editorial Scanning Rhythm (§7.10). Decisions D1 (feed 5-field AC over §6.8 4-field) / D2 (empty-state copy reconcile AC vs §6.8 ban + keep footer) / D3 (tab-type token) / D4 (section-heading reusable element) / D5 (`alert-triangle` absent → map error→frozen `error` glyph, no ADR) raised. L4 (5A) + critical-path spine node; synthetic only; depends on 5.5 + 5.2 + 5.3; feeds 5.16 (real agent runs) + 5.19 (STOP banner) + 5.12 a11y gate. Do-not-build real agent-runs/STOP-banner noted.
- 2026-06-26: Story 5.11 implemented (dev-story) — all ACs satisfied; D1-D5 (a); 4037 tests pass; freeze 7/7 unchanged.
