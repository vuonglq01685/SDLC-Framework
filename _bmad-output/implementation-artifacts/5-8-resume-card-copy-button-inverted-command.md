# Story 5.8: Resume Card + Copy Button + Inverted Command + Editorial Eyebrow

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L4 (5A). L4 = {5.6, 5.7, 5.8, 5.11}, max 4 parallel worktrees (cap-saturating). Depends on 5.5 (live-dot + freshness-footer FROZEN) + 5.3 (sprite: copy/check icons) + 5.2 (frozen tokens) — ALL done+merged. Edges: 5.2→5.8, 5.3→5.8, 5.5→5.8; downstream 5.8→5.18 (real "you are here"/"suggested next" rendering — reuses 5.8's card shell), 5.8→5.20 (honest-disconnection adds the Disconnected state), 5.8→5.12 (a11y convergence gate). Worktree: epic-5/5-8-resume-card-copy-button. Branch from main, linear merge, rebase between L4 merges (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). SYNTHETIC fixtures only — real ResumeToken/suggested-next compute is 5.18; the Disconnected + Phase-complete states are 5.20/5.18. Establishes the cross-cutting Inverted Command Surface (§7.7) reused by 5.11/5.19. -->

## Story

As Diep joining mid-stream,
I want the Resume Card (defining surface, DD-11) always visible without scroll at 1280 px, showing optional once-per-session greeting (DD-07), "You are here:" eyebrow + breadcrumb, "Suggested next:" inverted-command-surface line with copy button (DD-12 icon-swap to `check` for 1 s), and freshness footer,
So that Diep's onboarding job ("know what to do in 60 seconds") succeeds (UX-DR3, UX-DR13, UX-DR26, UX-DR27, DD-07, DD-11, DD-12, DD-13).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.8, lines 2570–2592).

**AC1 — Resume Card layout (defining surface)**
- **Given** the Resume Card **When** rendered at the top of the side panel **Then** the layout matches the verbatim spec in UX §2.5 / §6.4 (greeting line, "You are here:" eyebrow, breadcrumb, "Suggested next:" command line, copy button, freshness footer)
- **And** the container uses `--paper` background, `--border-hairline`, `--radius-xl` (8 px), padding `--space-12 × --space-14`, no shadow
- **And** the suggested-command line has no prefix marker (DD-13)

**AC2 — Once-per-session greeting (DD-07)**
- **Given** sessionStorage indicates first session **When** the card renders **Then** the greeting line is shown (DD-07)
- **And** sessionStorage is updated; subsequent renders in the same session omit the greeting

**AC3 — Copy button (DD-12)**
- **Given** the copy button (DD-12) **When** I click it **Then** the suggested command is written to the system clipboard via the Clipboard API
- **And** the icon swaps from `copy` to `check` for 1 second
- **And** screen readers announce "copied to clipboard" via `aria-live="polite"`

**AC4 — Inverted command surface (§7.7)**
- **Given** the inverted command surface pattern (§7.7) **When** the suggested-command line renders **Then** the visual treatment matches §7.7 (inverted background, mono font, no shell prefix)
- **And** the same treatment is reused on any future "literal CLI text" surface

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the **command normalization (DD-13)**, the **greeting gating (DD-07, AC2)**, and the **copy behavior + 1 s icon swap + aria-live (AC3)** are deterministic behavior → tests-first. DD-13 normalization is a pure function (no prefix marker, trimmed, no trailing newline) — unit test in isolation. DD-07 gating mocks `sessionStorage`. AC3 = Playwright (stub `navigator.clipboard.writeText`, assert exact command + `<use href>` swaps `copy`→`check`, advance 1 s → swaps back, assert the `aria-live="polite"` region text). The card CSS/inverted-surface is `test-along` + a static-analysis token contract. Resolve Decisions D1–D5 BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (command-surface mono size: prose 13px vs frozen `--type-mono-md` 12px) + D2 (copy `aria-label` wording) + D3 (aria-live politeness + message) + D4 (Phase-complete state scope) + D5 (command markup a11y: sole copy-button tab stop) BEFORE coding** (AC: 1, 3, 4)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). Align the component layout to the 5.5-frozen `static/components/<name>/` convention.

- [x] **Task 1 — Resume Card shell + layout (defining surface, DD-11)** (AC: 1)
  - [x] `role="region"` `aria-label="Resume position and suggested command"`; container = `--paper` bg, `--border-hairline`, `--radius-xl` (8px), `--space-12 × --space-14` padding, **no shadow**. Always visible without scroll at 1280 px (DD-11; DD-04 desktop-only — no mobile breakpoints). [§6.4 ux:1137-1146]
  - [x] Layout (top→bottom): greeting (conditional) → "You are here:" eyebrow (`--type-label-mono-sm` `--accent` uppercase) → breadcrumb (Inter 14px `--ink`, slash `/` separators visible) → "Suggested next:" eyebrow (`--type-label-mono-sm` `--ink-mute` uppercase) → inverted command line + copy button → `<freshness-footer>`. [§2.5 ux:453-472; §6.4 ux:1121-1146]

- [x] **Task 2 — Once-per-session greeting (DD-07)** (AC: 2) — *tests-first*
  - [x] First render with empty sessionStorage → show "Welcome, {user}." (`--type-body` Inter 14px 500 `--ink-soft`; no emojis/exclamation/time-of-day variants per DD-07); set the session flag; subsequent renders in the same session omit the greeting (layout shifts cleanly without placeholder). [DD-07 ux:256; §6.4 ux:1140,1150-1151]
  - [x] Unit-test with a mocked `sessionStorage` (first render shows + sets flag; second render omits). User identifier is fixture-injected for synthetic 5.8 (real `$USER`/`project.yaml` resolution rides 5.18).

- [x] **Task 3 — Inverted Command Surface (§7.7) + DD-13 no-prefix** (AC: 1, 4) — *tests-first*
  - [x] Author a reusable inverted-command treatment (CSS class, e.g. `.inverted-command`) so 5.11 (activity feed) + 5.19 (STOP banner) consume the same shape: background `--ink`, text `--bg`, `font-family: var(--font-mono)`, padding `--space-5 × --space-6`, `--radius-md` (4px). [§7.7 ux:1535-1541]
  - [x] **No prefix marker** (DD-13): no `$`/`>`/`❯`. Extract a pure `normalizeCommand(str)` — strips leading/trailing whitespace + trailing newlines, no shell-comment markers — and unit-test it. This is the literal string written to the clipboard. **Distinct from inline-code (§6.8, 5.10):** inline-code is `--bg` bg / `--ink` text (normal contrast); the command surface is INVERTED (`--ink` bg / `--bg` text). Do NOT use inline-code for the runnable command.

- [x] **Task 4 — Copy button + Clipboard API + 1 s icon swap + aria-live (DD-12)** (AC: 3) — *tests-first*
  - [x] `<button class="copy-btn">` (rides the 5.4 focus ring — `focus-motion.css` already names `.copy-btn:focus-visible`), `aria-label` per D2, click area ≥ 36×36 px, right edge of the command surface. Render the `copy` glyph via `createGlyph("copy", …)` (reuse from signoff-cell.js).
  - [x] On click: `navigator.clipboard.writeText(normalizeCommand(command))`; swap the SVG `<use href>` `#copy`→`#check` for **1.0 s** then back via `setTimeout` (value `--motion-copy-feedback: 1s`). **This is a content delta (DD-06/DD-12): change the `<use href>` via JS — NO CSS transition** (DD-14 forbids `transition:`; the glyph swap is a content swap, allowed).
  - [x] Announce "copied to clipboard" via `aria-live="polite"` (D3). No toast/banner/sound/"Copied!" text label (DD-12; §7.12 forbids toasts).
  - [x] Playwright test: stub `clipboard.writeText`, assert called with the exact normalized command; assert `<use href>` → `#check`, advance 1 s → `#copy`; assert the polite live-region text === "copied to clipboard"; assert focus ring on keyboard focus, suppressed on mouse focus.

- [x] **Task 5 — Committed synthetic fixture + tests** (AC: 1, 2, 3, 4) — *tests-first*
  - [x] Commit a `resume-card.fixture.html` (link tokens.css + focus-motion.css + own CSS; embed `<freshness-footer>`). Add the unit tests (normalizeCommand, greeting gating) + the Playwright copy test + a static-analysis token contract (all CSS values are `var(--*)`; inverted-surface bg=`--ink`/text=`--bg`; component present in force-include). Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`).

- [x] **Task 6 — Packaging + quality gate + freeze** (AC: 1, 2, 3, 4)
  - [x] Add new CSS/JS/HTML (resume-card + any shared inverted-command CSS + fixture) to the `force-include` block [pyproject.toml].
  - [x] Component CSS uses `var(--*)` only (5.2 stylelint gate); run DD-14 motion gate (icon swap is content delta — NO `transition:`), DD-08 no-framework, DD-09 no-data-theme, the 5.3 no-external-fonts gate, and the 5.5 color-only gate (the embedded freshness-footer pairs live-dot with text).
  - [x] Python quality gate on any new `scripts/*.py`/tests (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7**.

### Review Findings

> bmad-code-review 2026-06-26 — 3 parallel adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor @ Opus-4.8) + orchestrator source-verification (every load-bearing finding reproduced against the real `resume-card.js` / `.css` / `inverted-command.css` / fixture / tests). Full suite GREEN: **4015 passed / 4 skipped / 1 xfailed, coverage 88.39%** (≥87 floor). Acceptance Auditor: **AC1–AC4 all satisfied**; D1–D5 implemented as resolved (a); no anti-scope-creep items built; no XSS (textContent-only). Triage: **1 decision-needed (→ deferred to 5.18), 2 patch, 8 defer total, 8 dismissed**.

**Decision-needed** (1 — resolved 2026-06-26 → deferred to 5.18)

- [x] [Review][Defer] Greeting burned + redundant multi-render on attributed-card upgrade (was Decision) — `attributeChangedCallback` runs a full synchronous `_render` per observed attribute, and the greeting decision + `markGreetingShown` live inside the render path. A card authored with attributes AND storage-based greeting (no `show-greeting="false"`) upgrades with N renders: render #1 shows the greeting and burns the once-per-session flag, render #2+ omit it → the greeting is added then removed before paint and the flag is consumed without the user ever seeing it. Same multi-render leaves an uncancelled `setTimeout` / no `disconnectedCallback` (copy-feedback timer can fire on a detached button). **LATENT in 5.8** — the only attributed fixture card uses `show-greeting="false"`; the greeting card has no attributes (single render) — so no 5.8 AC is broken and the full suite is green. Bites **5.18** (real attributed Resume Card + storage greeting). [resume-card.js:118-124,197-201,88-107] (blind+edge) — **deferred to 5.18** (resolved 2026-06-26): lỗi tiềm ẩn, không kích hoạt trong fixture synthetic của 5.8 (không AC nào vỡ, suite xanh); fix render-coalescing + lifecycle-timer thuộc về 5.18 nơi card thật mang attributes + greeting theo storage.

**Patch**

- [ ] [Review][Patch] Clipboard-write failure silently swallowed — `catch { return; }` gives no signal; document the deliberate no-op (disabled/disconnected-copy state is 5.20) [resume-card.js:92-96]
- [ ] [Review][Patch] Dead `text.replace(/\n+$/u, "")` after `.trim()` in normalizeCommand — `.trim()` already strips trailing newlines, so the replace can never match [resume-card.js:19]

**Deferred** (also recorded in deferred-work.md)

- [x] [Review][Defer] normalizeCommand preserves interior newlines (multi-line command paste auto-exec risk) [resume-card.js:18-21] — deferred to 5.18 (real command source; DD-13 only mandates trailing-newline strip)
- [x] [Review][Defer] aria-live region not re-announced on repeat copies (identical textContent) [resume-card.js:98] — deferred to 5.12 (a11y convergence gate)
- [x] [Review][Defer] sessionStorage property-access throw at default-param eval (sandboxed-iframe) [resume-card.js:109] — deferred (low-likelihood for same-origin dashboard; getItem/setItem already guarded)
- [x] [Review][Defer] Long-command overflow/wrap on inverted surface [inverted-command.css:17-28] — deferred to 5.18/5.11 (synthetic command short; surface reused by 5.11/5.19)
- [x] [Review][Defer] §6.4 polite live-region does not wrap breadcrumb+command for poll updates [resume-card.js:69-79] — deferred to 5.18 (real poll updates; Auditor confirms not an AC breach)
- [x] [Review][Defer] `.copy-btn` styling lives in resume-card.css not inverted-command.css (reuse-contract refinement) [resume-card.css:64-77] — deferred to 5.11/5.19 (relocate when they consume the surface; would ripple into 36px/.copy-btn unit asserts)
- [x] [Review][Defer] Test gaps — attributed-card greeting (pairs w/ Decision), clipboard-failure path, double-click race, normalizeCommand boundaries, sessionStorage-throws [tests/integration + tests/unit] — deferred (test hardening alongside 5.18/5.12)

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§6.4 Resume Card.** *"The dashboard's defining surface (DD-11)."* Always visible without scroll at 1280 px; top of side panel, full panel width, below masthead. Token table [ux:1137-1146]: Container = `--paper` bg, `--border-hairline`, `--radius-xl` (8px), `--space-12 × --space-14` padding, "no shadow"; Greeting = `--type-body` Inter 14px 500 `--ink-soft` (once per session, sessionStorage, DD-07); "You are here:" eyebrow = `--type-label-mono-sm` `--accent` uppercase; Breadcrumb = `--type-body` Inter 14px `--ink`, slash separators visible; "Suggested next:" eyebrow = `--type-label-mono-sm` `--ink-mute` uppercase; Command surface = `--ink` bg (inverted), `--bg` text, `--radius-md`, `--type-mono-md` 13px, `--space-5 × --space-6` padding (DD-13); Copy button = §6.8, right edge; Freshness footer = `--type-mono-data` `--ink-mute`, "as of HH:MM:SS" + live-dot. a11y: `role="region"` `aria-label="Resume position and suggested command"`; copy = `<button>` `aria-label`; keyboard tab order = copy button → next (no focus on breadcrumb). [Source: ux-design-specification.md §6.4:1113-1164; §2.5:439-493]
- **§7.7 Inverted Command Surface.** Shared shape: bg `--ink`, text `--bg`, `--font-mono`, padding `--space-5 × --space-6`, radius `--radius-md`; copy button on the right edge. Used by: resume-card suggested-command (DD-13), activity-feed command rows, STOP-banner literal-command resolution. Consistency contract: *"reserved for runnable commands, not code samples, not inline IDs … Inline mono content uses the inline-code pattern (§6.8) instead."* [Source: ux-design-specification.md §7.7:1531-1548]
- **DD-07** *"Resume card greeting: 'Welcome, {user}.' once per browser session, then 'You are here:' only. … No emojis, no exclamation marks, no time-of-day variants."* [ux:256]
- **DD-11** *"Resume card is the dashboard's defining surface. Mandatory layout: greeting (first session only) → state breadcrumb → suggested-command line with explicit copy button → freshness footer with live-dot. Always visible without scroll at 1280 px."* [ux:499]
- **DD-12** *"Copy feedback = icon-swap to `check` for 1.0 second, then swap back. No toast, no animation, no text label."* (content delta only, DD-06). [ux:500]
- **DD-13** *"Suggested command is rendered with no prefix marker (no `$`, no `>`, no `❯`). The copyable string is the literal command exactly as it should be pasted … Whitespace is normalized; trailing newlines are stripped."* [ux:501]
- **§7.6 Editorial Eyebrow.** `--type-label-mono-sm` uppercase, weight ≤500; *Accent* for "you are here"/"current focus", *Mute* (`--ink-mute`) for routine labels ("Suggested next:"); above content with `--space-3`–`--space-6` margin below; never inline mid-paragraph. [ux:1519-1529]

### Frozen foundation to consume (do NOT redefine — 5.2/5.3/5.5 froze these)

```css
/* tokens.css — resume-card vocabulary */
--paper(#161922); --bg(#0e0f13); --ink(#eceef3); --ink-soft(#c2c7d2); --ink-mute(#8b92a2); --accent;
--border-hairline:1px solid var(--rule);  --radius-xl:8px(card);  --radius-md:4px(command surface);
--type-body-{size:14px,weight:400}  (greeting/breadcrumb — set font-weight:500 literal for greeting);
--type-label-mono-sm-{…}(eyebrows uppercase);  --type-mono-md-{size:12px,weight:400}(command surface — see D1);  --type-mono-data-*(footer);
--space-5:12px; --space-6:14px (command padding);  --space-12:28px; --space-14:32px (card padding);  --font-mono;
--motion-copy-feedback:1s  (the setTimeout duration — "timeout, not transition");
```
```text
sprite.svg — `copy` (id) + `check` (id) BOTH present in the frozen 12-icon set. [icons/sprite.svg]
createGlyph(iconId, className) — exported from signoff-cell.js (consumed by phase-cell.js); builds <svg><use href="/static/icons/sprite.svg#${iconId}"> aria-hidden. Reuse for the copy button; swap the <use href> for the 1s feedback. [signoff-cell.js:44-58]
<freshness-footer last-poll variant now> — reuse directly for the card footer (composes <live-dot>; satisfies the color-only gate). [freshness-footer.js:62-90]
focus-motion.css ALREADY names `.copy-btn:focus-visible` AND `button:focus-visible` → DD-15 ring auto-applies; NO new focus CSS. [focus-motion.css:16-26]
inline-code.css (5.10) is DISTINCT (--bg bg / --ink text) — do NOT use for the runnable command. [inline-code.css:4]
```
[Source: tokens.css:97-129,167-200,217-254; icons/sprite.svg; signoff-cell.js:44-58; freshness-footer.js:62-90; focus-motion.css:16-26; inline-code.css:4]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Command-surface mono size: prose 13px vs frozen `--type-mono-md` 12px.** §6.4/§2.5 say "JetBrains Mono 13px" but `--type-mono-md-size` is 12px and tokens.css is FROZEN (no 13px mono token; stylelint forbids a raw `font-size: 13px`). *Recommendation (a):* consume `--type-mono-md` (12px) and note the 13px prose as pre-freeze drift — the token governs. *(b)* add `--type-mono-lg`=13px — rejected (re-freeze risk). *(c)* raw 13px — forbidden by stylelint.

**D2 — Copy button `aria-label` wording.** "Copy command" (§6.8 ux:1375) vs "Copy suggested command" (§6.4 ux:1158). *Recommendation (a):* "Copy suggested command" (the §6.4 component-specific spec is more precise for this surface).

**D3 — aria-live politeness + message.** Story AC3 (epics:2587) = `polite` + "copied to clipboard"; §6.8 checklist offers `assertive` "Copied" or `aria-pressed` (ux:1797). *Recommendation (a):* honor the binding Story AC — `aria-live="polite"`, announce "copied to clipboard". Avoid `assertive` (the forbidden-patterns table warns against ARIA noise).

**D4 — Phase-complete state scope.** §6.4 (ux:1153) defines a terminal "Project complete. No further commands." state, but it depends on real phase progress. *Recommendation (a):* defer to the real-data twin (5.18) — render only Default + greeting (first/subsequent) states from synthetic fixtures. *(b)* a fixture-driven phase-complete variant for visual coverage — optional, low cost.

**D5 — Command markup a11y.** §6.4 (ux:1158) describes a `<code>` inside a focusable `<div role="group" aria-label="Suggested command, click to copy">`, but the keyboard contract (ux:1162) lists ONLY the copy button in tab order. *Recommendation (a):* the copy button is the SOLE tab stop; the `role="group"` wrapper carries the aria-label but is NOT tabbable (no tabindex) — the concrete tab-order spec wins over the "focusable div" wording.

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the **Resume Card shell/layout** + **copy-button interaction** (Clipboard API + 1 s icon swap + aria-live) + the cross-cutting **Inverted Command Surface (§7.7)** pattern (authored as a reusable class for 5.11/5.19) + **DD-07 greeting** (sessionStorage) + editorial-eyebrow usage. SYNTHETIC fixture data only.
- **Must NOT build:** the REAL "you are here" breadcrumb compute (from `ResumeToken` 1.7) or the REAL "Suggested next" command (from `sdlc status` 1.17) — that is **5.18** (edge 5.8→5.18, twin); the **Disconnected** state (§6.4 ux:1152, copy disabled + amber outline) — that is **5.20** (edge 5.8→5.20); the **Phase-complete** terminal state (D4 — defer to 5.18). No forms/validation, modals/dialogs, toasts/notification stacks (copy feedback is icon-swap only), browser notifications, search/filter/sort, loading spinners/skeleton loaders, onboarding tours (the DD-07 greeting IS the onboarding affordance), theme switcher (§7.12). No CSS `transition:`/transforms (DD-14). [Source: docs/sprints/epic-5-dag.md §2 (5.8→5.18/5.12/5.20, twin:242), §3 (L4:213), §6 (5.8 row:286, 5.18 row:296)]

### Project Structure Notes

- New: `static/components/resume-card/` (CSS/JS/fixture) + a shared inverted-command CSS (co-located or a small `static/components/inverted-command/`) under the 5.5-frozen convention. All new static files → `force-include` [pyproject.toml].
- Component CSS must use `var(--*)` — the 5.2 stylelint gate (at `src/sdlc/dashboard/static/styles/.stylelintrc.json`) FORBIDS raw color/font-size/padding/etc. `font-weight: 500` is allowed as a literal (greeting).
- The copy button is the ONLY interactive element / sole tab stop (D5); it rides the pre-wired `.copy-btn:focus-visible` ring — no new focus CSS. The icon swap is a content delta (`<use href>` change), NOT a CSS transition.
- L4 siblings (5.6/5.7/5.8/5.11) mutually independent; cap-saturating. Branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3).
- Zero wire-format contracts (CSS/JS/HTML are not wire contracts) → freeze stays 7/7.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| `copy` / `check` glyphs | `<use href="/static/icons/sprite.svg#copy\|check">` (frozen 12-icon set) | src/sdlc/dashboard/static/icons/sprite.svg |
| Glyph builder + icon swap | `createGlyph(iconId, className)` (swap `<use href>` for feedback) | src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.js:44-58 |
| Card freshness footer | `<freshness-footer last-poll variant>` (composes live-dot) | src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:62-90 |
| Copy-button focus ring | `.copy-btn:focus-visible` already wired (DD-15) — no new CSS | src/sdlc/dashboard/static/styles/focus-motion.css:16-26 |
| Inline-code vs inverted-command boundary | inline-code is distinct (`--bg`/`--ink`); command is inverted (`--ink`/`--bg`) | src/sdlc/dashboard/static/components/inline-code/inline-code.css:4 |
| Resume-card tokens | Consume frozen tokens (D1 command mono size) | src/sdlc/dashboard/static/styles/tokens.css:97-254 |
| Playwright test surface | Extend the 5.4/5.10 Playwright surface for the copy interaction | tests/integration/test_dashboard_*.py |
| Motion / no-framework / color-only gates | Run on the new card | scripts/check_dashboard_motion.py / _no_framework.py / _color_only.py |
| Wheel force-include | Add new static files | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2564-2592] — Story 5.8 ACs (verbatim above); UX-DR3:193, UX-DR13:203, UX-DR26:220, UX-DR27:221
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.4:1113-1164] — Resume Card token table + states + a11y + keyboard
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §2.5:439-493] — Experience mechanics (greeting / breadcrumb / command / copy / footer)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.7:1531-1548, §7.6:1519-1529] — Inverted Command Surface + Editorial Eyebrow
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md DD-07:256, DD-11:499, DD-12:500, DD-13:501] — design decisions
- [Source: src/sdlc/dashboard/static/icons/sprite.svg] — `copy` + `check` glyphs (frozen 12-icon set; NO `alert-triangle`)
- [Source: src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.js:44-58] — `createGlyph` (reuse for copy button + icon swap)
- [Source: src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:62-90] — `<freshness-footer>` (card footer)
- [Source: src/sdlc/dashboard/static/styles/focus-motion.css:16-26] — `.copy-btn:focus-visible` pre-wired (no new focus CSS)
- [Source: src/sdlc/dashboard/static/components/inline-code/inline-code.css:4] — inline-code-vs-inverted-command boundary
- [Source: src/sdlc/dashboard/static/styles/tokens.css:97-254] — frozen resume-card tokens (drives D1; `--motion-copy-feedback`)
- [Source: docs/sprints/epic-5-dag.md §2 (5.8→5.18/5.20, twin:242), §3 (L4:213), §6 (5.8 row:286, 5.18 row:296)] — layer, edges, real-data twin
- [Source: _bmad-output/implementation-artifacts/5-5-live-dot-family-freshness-footer-pattern.md] — froze live-dot + freshness-footer + file-layout convention

## Dev Agent Record

### Agent Model Used

Composer (Cursor)

### Debug Log References

### Completion Notes List

- Implemented `<resume-card>` defining surface (DD-11): region landmark, paper container tokens, editorial eyebrows, breadcrumb, inverted command + copy button, embedded `<freshness-footer>`.
- Decisions resolved: D1(a) `--type-mono-md` 12px; D2(a) "Copy suggested command"; D3(a) polite + "copied to clipboard"; D4(a) defer phase-complete to 5.18; D5(a) copy button sole tab stop.
- Added reusable `.inverted-command` CSS (§7.7) for 5.11/5.19; `normalizeCommand`, DD-07 sessionStorage greeting, DD-12 copy→check 1s icon swap + aria-live.
- Tests: 16 unit static-analysis + 6 Playwright integration; all dashboard gates green; full suite 4015 passed; coverage floor maintained.

### File List

- src/sdlc/dashboard/static/components/inverted-command/inverted-command.css
- src/sdlc/dashboard/static/components/resume-card/resume-card.css
- src/sdlc/dashboard/static/components/resume-card/resume-card.js
- src/sdlc/dashboard/static/components/resume-card/resume-card.fixture.html
- tests/unit/dashboard/test_resume_card_fixture.py
- tests/integration/test_dashboard_resume_card.py
- pyproject.toml

## Change Log

- 2026-06-26: Story 5.8 implemented — resume-card shell + inverted-command surface + DD-07 greeting + DD-12/DD-13 copy behavior; decisions D1–D5 resolved (a); tests + dashboard gates green; status → review.
- 2026-06-25: Story 5.8 created (create-story, "tạo US cho layer tiếp theo" → L4 batch with 5.6/5.7/5.11) — Resume Card (defining surface, DD-11) + once-per-session greeting (DD-07) + editorial eyebrows + Inverted Command Surface (§7.7, reusable for 5.11/5.19) + Copy button (Clipboard API + 1 s `copy`→`check` icon swap content-delta + `aria-live="polite"`). Decisions D1 (command mono 13px→`--type-mono-md` 12px) / D2 (copy aria-label) / D3 (aria-live polite + "copied to clipboard") / D4 (defer Phase-complete to 5.18) / D5 (copy button sole tab stop) raised. L4 (5A), synthetic only; depends on 5.5 + 5.3 + 5.2; feeds 5.18 (real you-are-here/suggested-next) + 5.20 (disconnected) + 5.12 a11y gate. Confirmed sprite has `copy`+`check` (no `alert-triangle`); focus ring pre-wires `.copy-btn`.
