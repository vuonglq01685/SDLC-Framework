# Story 5.10: Backlog Tree + Pill Family + Inline Code

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L3 (5A). L3 = {5.5, 5.9, 5.10}, max 3 parallel worktrees. Depends on 5.2 (frozen tokens) + 5.3 (sprite: chevron-right/chevron-down) + 5.4 (focus ring — focus-motion.css already names `.tree-expander:focus-visible`) — ALL done+merged. Mutually independent of L3 siblings 5.5 / 5.10 (no edge; 5.10 is NOT on the critical path). Edges: 5.2→5.10, 5.4→5.10; downstream 5.10→5.15 (real hierarchy swap) and 5.10→5.12 (a11y convergence gate). Worktree: epic-5/5-10-backlog-tree-pills. Branch from main, linear merge, rebase between L3 merges (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). FIRST keyboard-interactive component (full WAI-ARIA tree) → CLOSES the 5.4 DEF-6 focus-ring behavioral-test carryover. SYNTHETIC fixtures only — real Epic→Story→Task hierarchy is 5.15. -->

## Story

As Diep navigating to neighbor context,
I want the Backlog Tree (collapsible Epic→Story→Task) with kind badges (EPIC purple / STORY blue / TASK ink-soft) + status/stage/flow/priority pills + inline code for ids, all keyboard-reachable with visible focus rings,
So that the backlog is scannable and accessible (UX-DR5, UX-DR9, UX-DR12, §6.6, §7.3).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.10, lines 2619–2642).

**AC1 — Backlog Tree (collapsible, keyboard-reachable)**
- **Given** the Backlog Tree **When** rendered with synthetic fixture data **Then** the structure is a nested list with Epic header rows containing kind badge (`EPIC` purple) + flow pill + story head + tasks
- **And** every kind badge appears immediately to the LEFT of its record's name (consistency contract §7.3)
- **And** every interactive element (expanders) is keyboard-reachable via Tab; arrow keys navigate within the tree

**AC2 — Pill family (UX-DR9)**
- **Given** the Pill family (UX-DR9) **When** I render `kind`/`status`/`stage`/`flow`/`priority` pills in fixtures **Then** all pills share shape: uppercase mono, 700 weight, letter-spacing 0.14em, padding `--space-2 × --space-3`, radius `--radius-sm` (3 px)
- **And** kind variants: EPIC (`--purple` bg / white text), STORY (`--blue` bg / white text), TASK (`--ink-soft` bg / white text)
- **And** the pill registry under `dashboard/static/components/pills/` lists all variants

**AC3 — Inline code (UX-DR12)**
- **Given** inline code (UX-DR12) **When** rendered for ids and CLI snippets **Then** the font is JetBrains Mono with appropriate size token
- **And** the visual treatment is distinct from prose body text

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the **WAI-ARIA tree keyboard contract (AC1)** is testable behavior → tests-first via the Playwright surface (Story 5.4 D2): assert Tab reaches expanders, Arrow keys move focus / expand / collapse, the `:focus-visible` ring renders, and `aria-expanded` flips. This **closes DEF-6** (the first focusable component — assert the 5.4 focus ring behaviorally). The **kind-badge-immediately-left-of-name (§7.3)** and **all-pill-variants-present (AC2)** contracts are deterministic → a static-analysis/DOM test over the committed fixtures. The pill/tree CSS is substrate → `test-along`. Resolve Decisions D1/D2 BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (pill weight/letter-spacing token mapping) + D2 (tree state model: web component vs class-based, align to 5.5 layout) BEFORE coding** (AC: 1, 2)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). Align the component/registry layout to the 5.5-frozen convention (DAG §5; epic AC2 names `dashboard/static/components/pills/`).

- [x] **Task 1 — Backlog Tree structure + collapse (glyph-swap, not transform)** (AC: 1)
  - [x] Nested list (3 levels): Tree-epic → Tree-story → Tree-task, per the §6.6 class/token table (`.tree-epic` / `.tree-epic-head` / `.tree-epic-body` / `.tree-story` / `.tree-story-head` / `.tree-story-body` / `.tree-task`). Epic header row = kind badge (`EPIC` purple) + flow pill + name + meta + percentage; story/task rows scale down.
  - [x] **Kind badge immediately to the LEFT of the record's name** in every header row (§7.3 consistency contract — badges never appear without an adjacent name).
  - [x] **Collapse = chevron glyph SWAP** (`chevron-right` collapsed ↔ `chevron-down` expanded, 5.3 sprite) + body `display: none`, **NOT a CSS transform** (DD-14 strips chevron transforms; the DD-14 gate fails any `transition:`). Hover = instant `--bg` background swap on the head row (no transition).

- [x] **Task 2 — WAI-ARIA tree + full keyboard navigation** (AC: 1) — *tests-first*
  - [x] `role="tree"` on the root; each row `role="treeitem"`, `aria-expanded="true|false"` on parents, `aria-level="1|2|3"`, `aria-setsize`, `aria-posinset`; `aria-current="true"` on the row matching the resume card's current task. [§6.6 a11y]
  - [x] Keyboard contract (§6.6): `ArrowDown`/`ArrowUp` focus next/prev **visible** row; `ArrowRight` expand collapsed parent (no-op on expanded/leaf); `ArrowLeft` collapse expanded parent (else focus parent); `Enter` toggle expand on parent (no-op on leaf — read-only); `Home`/`End` first/last visible row; `*` expand sibling parents at the focused level (optional, per WAI-ARIA tree pattern). Use roving `tabindex` (single tab stop into the tree) per the WAI-ARIA tree pattern — "keyboard-reachable via Tab; arrow keys navigate within" (AC1).
  - [x] **Reuse the existing focus ring** — `focus-motion.css:21` already names `.tree-expander:focus-visible { box-shadow: 0 0 0 2px var(--rule-strong); }`. Use the `.tree-expander` class on the focusable element so DD-15 applies automatically. **This closes 5.4 DEF-6** — add the behavioral test that the ring renders on keyboard focus and is suppressed on mouse `:focus` (Playwright `:focus-visible`).

- [x] **Task 3 — Pill family + registry** (AC: 2)
  - [x] Shared pill shape (§7.3 / §7.9): uppercase mono, **700 weight, letter-spacing 0.14em**, padding `--space-2 × --space-3`, radius `--radius-sm` (3px), white text on colored bg for kind badges. See **Decision D1** on the token mapping (no single type token is 700-weight + 0.14em; the stylelint gate forbids raw `letter-spacing`/`font-size`/`padding`).
  - [x] Kind variants: `EPIC` (`--purple` bg / white), `STORY` (`--blue` bg / white), `TASK` (`--ink-soft` bg / white). Author the broader family the AC names — `status` (soft-bg/solid-text), `stage` (`--radius-pill` border+soft-bg), `flow` (joined-edge `fp`), `priority` (soft-bg/solid-text) per §7.9 sub-patterns — in the fixtures.
  - [x] **Pill registry** under `dashboard/static/components/pills/` (epic AC2 path; align to 5.5 layout per D2) listing ALL variants — a committed fixture/registry page for visual + a11y review. Pills always have TEXT content (never color-only / glyph-only); uppercase for kind badges, lowercase for status/stage/flow/priority (§7.9 contract) — satisfies the 5.5 color-only-signaling gate.

- [x] **Task 4 — Inline code** (AC: 3)
  - [x] Inline code for ids + CLI snippets: `--font-mono` (JetBrains Mono) with an appropriate size token; visual treatment distinct from prose body (§6.8 inline-code / UX-DR12) — e.g. `--bg` background, `--radius-sm`, subtle. Distinct from the §7.7 *inverted command surface* (that is the runnable-command treatment, 5.8 — do NOT use it for inline ids).

- [x] **Task 5 — Committed synthetic fixtures + static-analysis contract test** (AC: 1, 2) — *tests-first*
  - [x] Commit synthetic Epic→Story→Task fixture data + the pill registry page. Add a test asserting: (a) every kind badge sits immediately left of its name (§7.3); (b) all pill variants the AC names are present; (c) the tree keyboard contract behaves (Playwright). **RED:** a fixture with a badge after the name, or a missing pill variant, fails; **GREEN:** the complete tree/registry passes. Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`).

- [x] **Task 6 — Packaging + quality gate + freeze** (AC: 1, 2, 3)
  - [x] Add new CSS/JS/HTML (tree, pills, inline-code, registry, fixtures) to the `force-include` block [pyproject.toml] to ship in the wheel.
  - [x] Ensure new component CSS is inside the (5.5-broadened) stylelint glob and uses `var(--*)` only; run the DD-14 motion gate (no transitions — chevron is a glyph swap) and the DD-08 no-framework gate (a native Custom Element is vanilla and clean).
  - [x] Python quality gate on any new `scripts/*.py`/tests (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7**.

### Review Findings

> bmad-code-review 2026-06-25 — fresh context, **3** adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + orchestrator source-verification (every load-bearing defect reproduced against the real `backlog-tree.js` / `pills.js` / `backlog-tree.css` / fixtures / tests). Orchestrator gate run GREEN: ruff + ruff-format clean (new tests), DD-14 motion + DD-08 no-framework + color-only gates exit 0, **full suite 3961 passed / 4 skipped / 1 xfailed** (incl. the 4 Playwright integration tests). Triage: **2 decision-needed + 5 patch (below), 6 defer (deferred-work.md), 2 dismissed**. Acceptance Auditor: AC1 MET, **AC2 PARTIAL→DEC-2**, AC3 MET; D1/D2/anti-scope-creep HONORED. Zero wire-format (CSS/JS/HTML are not contracts) → freeze stays 7/7.
>
> **RESOLUTION (2026-06-25).** DEC-1→(a) + DEC-2→(a) ratified; **6 patches APPLIED to working tree** (PAT-1..5 + PAT-6 from DEC-1). DEC-1 reproduced RED→GREEN: new `test_arrow_down_reaches_task_row_keyboard_focus` FAILED on the unfixed leaf (`visibility:hidden` non-focusable → ArrowDown dropped to `<body>`), PASSES after the glyph-only-hide fix. Post-patch verification GREEN: ruff + ruff-format clean, `mypy --strict src/` no issues (192 files), DD-14 + DD-08 + color-only gates exit 0, **full suite 3962 passed / 4 skipped / 1 xfailed** (+1 = the new witness). DEC-2 ratified → **AC2 now MET** (kind = uppercase/700/0.14em; status·stage·flow·priority = lowercase/500/0.12em; shared "shape" = mono + `--space-2×--space-3` padding + `--radius-sm`). **Status STAYS `review`** — flips to `done` only after the TDD-first commit ceremony (test→feat→docs) + worktree `epic-5/5-10-backlog-tree-pills` + merge to main + GREEN CI, per CLAUDE.md merged-before-done gate. NOT committed — working-tree only.

- [x] [Review][Decision] **RESOLVED→(a), APPLIED as PAT-6.** **DEC-1 (HIGH) — Task rows are NOT keyboard-focusable; ArrowDown/Up/End onto a task drops focus to `<body>`** — `renderTaskRow` builds the row expander with `isLeaf:true` → class `tree-expander--leaf` → CSS `visibility:hidden; pointer-events:none` [backlog-tree.css:181-184], yet `collectVisibleExpanders` still collects it [backlog-tree.js:344-346] and `setRovingTabindex`/ArrowDown call `.focus()` on it [backlog-tree.js:373,412,467]. A `visibility:hidden` element is non-focusable, so focus falls back to `<body>` and the keydown handler then early-returns (target no longer a `.tree-expander`) — the user is stranded at the first story and can never reach a task row. Violates **AC1** ("every interactive element keyboard-reachable; arrow keys navigate within the tree") and undermines the story's headline purpose (FIRST keyboard component / closes DEF-6). The dead `.tree-task-focus` CSS [backlog-tree.css:190-200] is abandoned scaffolding for exactly this focus target. The integration test `test_arrow_down_moves_focus_to_next_visible_row` passes only because it does ONE hop (epic→story) and never steps onto a task leaf (placebo coverage). **Options:** (a) minimal — keep the leaf expander focusable (hide only its inner glyph: drop `visibility:hidden` from the button, keep `pointer-events:none`), so roving focus lands on the glyph-less leaf button [smallest diff, preserves button-focus model] + add a RED-witness test (ArrowDown story→task lands on the task row); (b) WAI-ARIA-correct refactor — move roving `tabindex` + `aria-expanded`/`aria-current` onto the `role="treeitem"` element and focus the row (also fixes "focus on a roleless button → AT never announces aria-level/setsize/posinset" — Edge/Blind), larger diff touching every render path. **Recommend (a)** for v1 (unblocks AC1) + drop the duplicate `aria-expanded` on the button; defer the full treeitem-focus refactor to the 5.12 a11y convergence gate.
- [x] [Review][Decision] **RESOLVED→(a): §7.9 reading RATIFIED → AC2 MET (no code change).** Binding contract: kind badges = uppercase / 700 / 0.14em; status·stage·flow·priority = lowercase / 500 / 0.12em; "shared pill shape" = mono + padding `--space-2×--space-3` + radius `--radius-sm`. Future pill consumers (5.9+) match this. **DEC-2 (MED) — AC2 verbatim "ALL pills … 700 weight, 0.14em, uppercase" vs §7.9 "lowercase for status/stage/flow/priority"** — base `.pill` resolves to 500-weight / 0.12em [pills.css base]; only kind badges override to 700 / 0.14em / uppercase [pills.css `.pill--kind-*`]. So status/stage/flow/priority render 500/0.12em/lowercase. This honors §7.9 (cited in the story body) but contradicts the literal AC2 first sentence. **Options:** (a) ratify the §7.9 reading — AC2 "all pills share shape" = shared SHAPE (mono, padding `--space-2×--space-3`, radius `--radius-sm`); weight/letter-spacing/case are sub-pattern-specific (kind=uppercase/700/0.14em, others=lowercase/500/0.12em) → mark AC2 MET; (b) force every pill to 700/0.14em/uppercase (contradicts §7.9, makes status pills shout). **Recommend (a)** — §7.9-consistent intent; record the ratification so 5.9/future pill consumers match.
- [x] [Review][Patch] **[APPLIED] PAT-1 (MED) — Dual `aria-current`** [backlog-tree.js:134-136,177-179] — `aria-current="true"` is set on BOTH the current task row AND its ancestor story wrapper → two "current" nodes for one item (spec: one — "the row matching the resume card's current task"). Fix: keep `aria-current` on the task row only; drive the story-ancestor highlight via a class (e.g. `.tree-story.is-current-ancestor`) and update the CSS selector [backlog-tree.css:77-80].
- [x] [Review][Patch] **[APPLIED] PAT-2 (MED) — Stale-fixture closure / re-render aliasing** [backlog-tree.js:387,400,484,524-528] — `bindTreeKeyboard(host, data)` runs once (guarded by `_keyboardBound`) and captures `data`; `host._fixtureRef` is set only on first render. A later `renderBacklogTree(host, otherFixture)` (exported public API, consumed by 5.15) re-renders the DOM from the new fixture but the keyboard/click handlers keep mutating the original → DOM/state desync. Fix: set `host._fixtureRef = data` on EVERY render and resolve the live fixture from `host._fixtureRef` inside the handlers instead of the captured `data`. Latent in v1 synthetic; real trap for 5.15.
- [x] [Review][Patch] **[APPLIED] PAT-3 (MED) — `kind-badge-left-of-name` test is a source-order tautology + skips the task-row path** [tests/unit/dashboard/test_backlog_tree_fixture.py:63-77] — it greps the `appendKindBadgeLeftOfName` body for `createPillElement` index < `'className = "name"'` index: (a) a SOURCE-substring check, not rendered DOM order; (b) does NOT cover `renderTaskRow`, which appends the kind pill + name via a separate inline path [backlog-tree.js:147-152] — a reversal there passes green. §7.3 is the story's headline consistency rule. Fix: assert badge-before-name for ALL three render paths (epic/story helper + task inline), ideally a rendered-DOM order check (anti-tautology).
- [x] [Review][Patch] **[APPLIED] PAT-4 (MED) — Registry contract under-asserts AC2-named variants** [tests/unit/dashboard/test_backlog_tree_fixture.py:106-117] — `test_pills_js_declares_all_variant_labels` asserts only `len(labels) >= 10`; with 15 labels an entire AC2-named variant (EPIC/STORY/TASK, high/medium/low, …) could be renamed and still pass. Fix: assert the specific AC2-required labels/keys are present (EPIC/STORY/TASK at minimum), not just a count.
- [x] [Review][Patch] **[APPLIED] PAT-5 (LOW) — Dead CSS + misleading grid comment** [backlog-tree.css:155-158,190-200] — `.tree-head__badges { display: contents }` and the `.tree-task-focus` rules reference classes the JS never emits; the comment "grid places: expander | kind | flow/status | name" contradicts the real DOM order (expander | kind | name | flow/status | meta | pct). Fix: remove the dead rules and correct/remove the comment.
- [x] [Review][Defer] **DEF-1 — Playwright suite is chromium-only; focus-ring tests depend on Chromium's `:focus-visible` heuristic** [tests/integration/test_dashboard_backlog_tree.py:102-117] — deferred, pre-existing (consistent with 5.5 Playwright-chromium DEF); cross-browser unverified.
- [x] [Review][Defer] **DEF-2 — No `disconnectedCallback`; host keydown/click listeners + `_keyboardBound` never torn down** [backlog-tree.js:531-536] — deferred, pre-existing (sibling components share the no-teardown pattern; first with host listeners).
- [x] [Review][Defer] **DEF-3 — Empty/zero-epic fixture → `role="tree"` with no `tabindex=0` entry point, unreachable by Tab, no empty-state** [backlog-tree.js:514-522] — deferred, pre-existing (v1 fixture always has data; no empty-state requirement).
- [x] [Review][Defer] **DEF-4 — Grid `1fr` lands on the status/flow column, not the name; epic head without `flow` appends 5 children into a 6-col grid** [backlog-tree.css:27,57,85] — deferred, pre-existing (cosmetic slack; no AC covers it; synthetic always has flow).
- [x] [Review][Defer] **DEF-5 — `createFlowPillGroup` silently drops flow steps not in `PILL_FLOW_VARIANTS`** [pills.js:64-70] — deferred, pre-existing (no signal; v1 flow data is valid).
- [x] [Review][Defer] **DEF-6 — `test_enter_toggles_aria_expanded_on_parent` asserts only the first true→false toggle (not the round-trip, body-hide, or focus preservation)** [tests/integration/test_dashboard_backlog_tree.py:91-99] — deferred, pre-existing (test-strength).

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§6.6 Backlog Tree.** Three-level anatomy (class/token table), states (collapsed/expanded/current/hover/focus-visible), a11y (`role="tree"`/`role="treeitem"`/`aria-expanded`/`aria-level`/`aria-setsize`/`aria-posinset`/`aria-current`), and the full keyboard contract (Arrow/Enter/Home/End/`*`). *"Chevron … Glyph swap, no transform (DD-14)."* *"Focus-visible — `box-shadow: 0 0 0 2px var(--rule-strong)` (DD-15)."* [Source: ux-design-specification.md §6.6, lines 1221–1269]
- **§7.3 Kind Badge Family.** *"Uppercase mono pill, `--type-mono-pill`, 700 weight, `letter-spacing: 0.14em`, `--space-2 × --space-3` padding, `--radius-sm` (3 px), white text on a colored solid background."* Variants EPIC/STORY/TASK. *"A kind badge always appears immediately to the **left** of the record's name … Badges never appear without an adjacent name."* [Source: ux-design-specification.md §7.3, lines 1472–1486]
- **§7.9 Pill Family.** Sub-patterns (kind badge / status / stage / flow / priority) + *"Pills always have **text** content; never purely color or purely glyph. … uppercase for kind badges, lowercase for status/stage/flow/priority."* [Source: ux-design-specification.md §7.9, lines 1564–1580]
- **DD-14 — Stillness.** Chevron open/close is a glyph swap, not a transform; no `transition:`. [Source: ux-design-specification.md DD-14; scripts/check_dashboard_motion.py]
- **DD-15 — Focus ring.** `box-shadow: 0 0 0 2px var(--rule-strong)` on `:focus-visible` — already authored for `.tree-expander` in focus-motion.css. [Source: src/sdlc/dashboard/static/styles/focus-motion.css:15-38]

### Frozen foundation to consume (do NOT redefine — 5.2/5.3/5.4 froze these)

```css
/* tokens.css — pill + tree vocabulary */
--purple: #a78bfa;  --blue: #60a5fa;  --ink-soft: #c2c7d2;             /* kind-badge bg */
--purple-soft / --blue-soft / *-soft (12%)                            /* status/stage/priority soft bg */
--space-2: 6px;  --space-3: 8px;  --radius-sm: 3px;  --radius-pill: 999px;
--font-mono: "JetBrains Mono", ...;  --bg: #0e0f13;                   /* inline code */
--type-mono-pill-*  (10px/500/0.12em)   --type-mono-tag-*  (9px/700/0.12em)
--type-label-mono-sm-letter-spacing: 0.14em                          /* the 0.14em the badge needs */
--type-display-6-*  (Fraunces 17px epic name)   --type-mono-data-*  (meta line)
```
```css
/* focus-motion.css:15-38 — REUSE: `.tree-expander` already has the focus ring + suppression */
.tree-expander:focus-visible { box-shadow: 0 0 0 2px var(--rule-strong); outline: none; }
.tree-expander:focus:not(:focus-visible) { box-shadow: none; outline: none; }
```
Sprite glyphs available (exactly 12; this story uses 2): `chevron-right`, `chevron-down`.
[Source: src/sdlc/dashboard/static/styles/tokens.css:95-256, focus-motion.css:15-38, icons/sprite.svg]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Pill 700-weight + 0.14em letter-spacing: token mapping under the stylelint gate.** §7.3/AC2 require the badge to be **700 weight + `letter-spacing: 0.14em`**, but the 5.2 stylelint gate FORBIDS raw `letter-spacing`/`font-size`/`padding` values [.stylelintrc.json:42-44,23-37] AND no single type token is both 700-weight and 0.14em (`--type-mono-pill` = 10px/500/0.12em; `--type-mono-tag` = 9px/700/0.12em; `--type-label-mono-sm` = 10px/500/**0.14em**). *Recommendation (a):* compose — use `var(--type-mono-pill-size)` for size, **set `font-weight: 700` explicitly** (font-weight is NOT in the stylelint disallow-list, so a literal 700 is allowed), and use `var(--type-label-mono-sm-letter-spacing)` for the **0.14em** (it is exactly 0.14em). Padding via `var(--space-2)`/`var(--space-3)`. Document the composition so 5.9/future pill consumers match. *Alternative (b):* if a reviewer wants a single dedicated `--type-pill-badge-*` token group, propose adding it to tokens.css (which is stylelint-ignored) and escalate the token-name freeze (5.2 froze names) to the Project Lead — but prefer composition (a) to avoid re-freezing tokens.

**D2 — Tree state model + registry layout (align to 5.5).** The tree needs interactive state (expand/collapse, roving focus). *Recommendation (a):* native Custom Element / vanilla JS module under the 5.5-frozen `static/components/backlog-tree/`, with the pill registry at the epic-literal `static/components/pills/` (AC2 string). Match whatever component model 5.5 establishes (Custom Element vs class-based) so the epic has ONE convention, not two. *Alternative (b):* class-based render helper if 5.5 chose that. Either way, keep DD-08-clean (vanilla; the no-framework gate scans for React/Vue/etc., not Web Components) and ensure the registry/fixtures ship via force-include + sit inside the stylelint glob.

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the reusable **Backlog Tree** (collapsible, full WAI-ARIA keyboard) + the **Pill family + registry** (§7.3/§7.9) + **inline code** (§6.8). Closes the 5.4 **DEF-6** focus-ring behavioral test (first focusable component). Synthetic data only.
- **Must NOT build:** real Epic→Story→Task hierarchy from `state.json` (that is **5.15**, edge 5.10→5.15 — real 2A.11 hierarchy + 1.6 id regex + URL-hash persistence). Keep 5.10 fully synthetic. Do not build the inverted command surface (5.8) or signoff cell (5.9). [Source: docs/sprints/epic-5-dag.md §2 (5.10→5.15, 5.10→5.12), §3 (L3 dependency notes)]

### Project Structure Notes

- New: backlog-tree + pills + inline-code component CSS/JS under the 5.5-frozen `static/components/` convention (per D2), a `components/pills/` registry page (AC2), and synthetic tree fixtures. All new static files → `force-include` [pyproject.toml] (else absent from the wheel).
- Component CSS must use `var(--*)` — the 5.2 stylelint gate FORBIDS raw values for color/background-color/font-size/font-family/padding/margin/gap/letter-spacing/line-height/border-radius/border-width [.stylelintrc.json:5-54]. The 0.14em pill letter-spacing maps to `var(--type-label-mono-sm-letter-spacing)` (D1); `font-weight: 700` is allowed literal. Ensure the new CSS sits inside the (5.5-broadened) stylelint glob.
- DEF-6 close: 5.4 deferred the focus-ring behavioral test "when interactive components land (5.5+)" — 5.10's `.tree-expander` is the first such focusable element. Add the behavioral assertion here (ring on `:focus-visible`, suppressed on mouse `:focus`). [Source: deferred-work.md → "code review of 5-4-... (2026-06-24)" DEF-6]
- L3 siblings (5.5/5.9/5.10) mutually independent; branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3).
- Zero wire-format contracts (CSS/JS/HTML are not wire contracts) → freeze stays 7/7.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Tree-expander focus ring (DD-15) | `.tree-expander:focus-visible` already authored | src/sdlc/dashboard/static/styles/focus-motion.css:15-38 |
| Chevron glyphs (collapse via glyph swap) | `<use href="/static/icons/sprite.svg#chevron-right\|chevron-down"/>` | src/sdlc/dashboard/static/icons/sprite.svg |
| Pill/tree/inline-code tokens | Consume frozen tokens (D1 mapping for 0.14em/700) | src/sdlc/dashboard/static/styles/tokens.css |
| File-layout convention + color-only gate | Align to the 5.5-frozen `static/components/` layout; pass `check_dashboard_color_only.py` | Story 5.5 / docs/sprints/epic-5-dag.md §5 |
| Keyboard-tree test surface (Playwright) | Extend the 5.4 Playwright surface for WAI-ARIA tree + DEF-6 focus ring | tests/integration/test_dashboard_reduced_motion.py, .github/workflows/ci.yml (D2 Playwright) |
| Motion + no-framework gates | Run `check_dashboard_motion.py` + `check_dashboard_no_framework.py` on the new tree | scripts/check_dashboard_motion.py, scripts/check_dashboard_no_framework.py |
| Wheel force-include | Add new static files | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2619-2642] — Story 5.10 ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.6:1221-1269] — Backlog Tree anatomy + states + a11y + keyboard contract
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.3:1472-1486] — Kind Badge Family (shape + EPIC/STORY/TASK + left-of-name contract)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.9:1564-1580] — Pill Family sub-patterns + text-content contract
- [Source: src/sdlc/dashboard/static/styles/focus-motion.css:15-38] — `.tree-expander` focus ring (reuse; closes DEF-6)
- [Source: src/sdlc/dashboard/static/styles/tokens.css] — frozen pill/tree/inline-code tokens (0.14em = `--type-label-mono-sm-letter-spacing`)
- [Source: src/sdlc/dashboard/static/icons/sprite.svg] — chevron-right/chevron-down glyphs
- [Source: src/sdlc/dashboard/static/styles/.stylelintrc.json:5-54] — var(--*) enforcement (drives D1)
- [Source: scripts/check_dashboard_motion.py / check_dashboard_no_framework.py] — DD-14 / DD-08 gates (run on new tree)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md → code review of 5-4 (2026-06-24) DEF-6] — focus-ring behavioral test deferred to first focusable component (this story)
- [Source: docs/sprints/epic-5-dag.md §2 (5.10→5.15, 5.10→5.12), §3 (L3), §5 (5.10 row — pill registry)] — layer, edges, registry path
- [Source: _bmad-output/implementation-artifacts/5-5-live-dot-family-freshness-footer-pattern.md] — L3 sibling that freezes the file-layout convention + color-only gate

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor)

### Debug Log References

- D1 resolved (a): compose pill badge typography — `var(--type-mono-pill-size)` + literal `font-weight: 700` + `var(--type-label-mono-sm-letter-spacing)` for 0.14em; padding via `var(--space-2)`/`var(--space-3)`.
- D2 resolved (a): native Custom Element `<backlog-tree>` under `static/components/backlog-tree/`; pill registry at `static/components/pills/` per AC2; aligns to 5.5 component layout convention.
- DEF-6 closed: Playwright behavioral test asserts `.tree-expander:focus-visible` ring on keyboard focus, suppressed on mouse `:focus`.

### Completion Notes List

- Implemented `<backlog-tree>` custom element with WAI-ARIA tree (`role="tree"`/`treeitem`, `aria-expanded`, `aria-level`, roving `tabindex`), full keyboard contract (Arrow/Enter/Home/End), chevron glyph swap (no transform, DD-14), synthetic Epic→Story→Task fixture.
- Pill family + registry: kind (EPIC/STORY/TASK), status, stage, flow, priority variants in `pills.css`/`pills.js` and `pills.registry.html`; D1 token composition for 700-weight + 0.14em letter-spacing.
- Inline code component (`inline-code.css`) for ids/CLI snippets — JetBrains Mono via `--font-mono`, distinct from prose (UX-DR12).
- 14 new tests: unit fixture/static-analysis contract + integration Playwright WAI-ARIA keyboard + DEF-6 focus ring; full suite 3961 passed; `pyproject.toml` force-include updated for new static assets.

### File List

- src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.css (new)
- src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js (new)
- src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.fixture.html (new)
- src/sdlc/dashboard/static/components/pills/pills.css (new)
- src/sdlc/dashboard/static/components/pills/pills.js (new)
- src/sdlc/dashboard/static/components/pills/pills.registry.html (new)
- src/sdlc/dashboard/static/components/inline-code/inline-code.css (new)
- tests/integration/test_dashboard_backlog_tree.py (new)
- tests/unit/dashboard/test_backlog_tree_fixture.py (new)
- pyproject.toml (modified — force-include new dashboard static components)
- _bmad-output/implementation-artifacts/sprint-status.yaml (modified)
- _bmad-output/implementation-artifacts/5-10-backlog-tree-pill-family-inline-code.md (modified)

## Change Log

- 2026-06-24: Story 5.10 created (create-story) — Backlog Tree (collapsible WAI-ARIA, full keyboard) + Pill family + registry + inline code; Decisions D1 (pill 700-weight/0.14em token mapping under the stylelint gate — compose `--type-mono-pill-size` + literal `font-weight:700` + `--type-label-mono-sm-letter-spacing`) + D2 (tree component model + registry layout aligned to 5.5) raised. L3 (5A), synthetic only; first keyboard-interactive component → closes 5.4 DEF-6 focus-ring behavioral test; feeds 5.15 real hierarchy + 5.12 a11y gate; do-not-build real wiring noted.
- 2026-06-25: Story 5.10 implementation complete — Backlog Tree (`<backlog-tree>` custom element, WAI-ARIA + keyboard navigation, chevron glyph swap), Pill family + registry (all AC2 variants), inline code (UX-DR12). D1=(a) compose tokens for pill 700-weight/0.14em; D2=(a) native Custom Element + `components/pills/` registry aligned to 5.5. DEF-6 focus-ring behavioral test closed. 14 new tests; full suite 3961 passed. Status: ready-for-dev → review.
