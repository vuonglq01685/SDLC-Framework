# Story 5.21: Below-1280 px Viewport Degradation Banner

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG **L9 (5C)**, cap **2** — parallel with **5.20** (epic-5-dag.md §3:218, §6:332). Worktree: `epic-5/5-21-below-1280-degradation-banner`. Owner **Sally** (dag §5:299). **Co-critical** path `5.2→5.4→5.5→5.11→5.19→5.21→5.22` (dag §4:258–260 — on the critical boundary, NOT a freely-parallelizable leaf). Depends on: **5.19→5.21** (reuses the STOP-banner `.alert` treatment with `--blue` info; dag §2:162, done). Downstream: **5.21→5.22** (terminal a11y release gate; §2:167). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate **N/A** (epic-5 in-progress, cleared at 5.1). Review focus: **a11y** (color+text never color-only; keyboard-reachable `×`) + **forbidden-patterns** (the `×` dismiss is a SANCTIONED §8.2 exception to the §7.12 button-hierarchy ban — the only such exception besides the copy button; no `transition:` DD-14; no layout-collapse/hamburger/card-stacking). No wire-format shape edit → **freeze stays 7/7**. This builds ONLY the viewport banner; it does NOT build backend-silence disconnection (**5.20**). Sibling L9 worktree 5.20 also reuses the STOP-banner treatment + may touch `index.html` — coordinate (CONTRIBUTING §3.3 rebase-between-merges). -->

## Story

As a user accidentally viewing the dashboard below the supported viewport,
I want a persistent dismissible info banner ("Dashboard is optimized for screens ≥ 1280 px") below 1280 px and an upgraded copy ("desktop-only") below 768 px, with horizontal scroll (no layout collapse),
So that DD-04 (desktop-only) and DD-17 (degraded-but-functional) are honored explicitly (UX-DR32, UX-DR33, DD-04, DD-17, §8.2).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.21, lines 2868–2881).

**Given** the dashboard rendering at viewport width < 1280 px
**When** the page loads
**Then** a persistent info banner appears at the top: `Dashboard is optimized for screens ≥ 1280 px. Some elements may overflow below this width.`
**And** the banner uses the same treatment as STOP banners (Story 5.19) but with `--blue` info severity
**And** the banner has a `×` close button; clicking dismisses for the current session via sessionStorage; reappears on next page load

**Given** viewport width < 768 px
**When** the page loads
**Then** the banner copy is upgraded to: `This dashboard is desktop-only. Mobile / tablet are unsupported. Open on a screen ≥ 1280 px.`
**And** no layout-collapse logic, no hamburger menu, no card stacking

**Given** any viewport
**When** I resize the window
**Then** the dashboard does not silently break — horizontal scroll appears, content remains readable at native sizes

> ⚠️ **AC-vs-CODE — READ Decisions D1–D3 BEFORE coding.** Two divergences from 5.19 the AC glosses: (1) **the `×` dismiss makes this NOT a `createStopBannerElement`.** 5.19's STOP banners are explicitly **"not user-dismissible"** (`stop-banner.js` has no dismiss; banners vanish only when state resolves). "Same treatment as STOP banners" means **reuse the `.alert` CSS treatment** (left-edge + tokens), NOT the STOP `createStopBannerElement`/`TRIGGER_META` element — build a small dismissible `viewport-banner` (D1). (2) **`--blue` info is a real token** (`tokens.css:121`) but the STOP `.alert.info` edge already uses it — reuse the class, not a new color. Also note: **no viewport-detection code exists anywhere yet** (grep 2026-07-07 = 0 `matchMedia`/`innerWidth`) — this story introduces the first, via `matchMedia` (D2), not `resize` churn.

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** every AC clause is a testable contract → tests-first. **(AC clause 1) <1280 → info banner + `×` + sessionStorage** — a JS test drives a `matchMedia` matches:true → asserts the banner mounts with the exact copy, `--blue` `.alert.info` treatment, and a keyboard-reachable `×`; clicking sets the sessionStorage flag and removes it; re-init with the flag set → no banner (dismissed this session); re-init with a fresh session → banner returns. **(AC clause 2) <768 → upgraded copy + no layout collapse** — the <768 query swaps to the desktop-only copy; assert NO hamburger/stacking/`display:none` collapse. **(AC clause 3) resize does not break** — assert horizontal scroll, no layout-collapse. **Resolve Decisions D1–D3 BEFORE coding.**

- [x] **Task 0 — Resolve Decisions D1 (reuse `.alert` CSS treatment vs extend `createStopBannerElement`) + D2 (viewport detection: `matchMedia` change-listener vs resize) + D3 (`×` dismiss a11y + sanctioned forbidden-patterns exception) BEFORE coding** (AC: all)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). D1 is load-bearing (this banner is dismissible; STOP banners are not) — do not conflate the two semantics.

- [x] **Task 1 — Net-new `viewport-banner` component reusing the `.alert` treatment (D1)** (AC: 1) — *tests-first*
  - [x] Create `components/viewport-banner/viewport-banner.js` — a small element that renders a top-of-page info banner reusing the **`stop-banner.css` `.alert` + `.info`** treatment (`--blue` left-edge, `--paper` bg, `--border-hairline`, `--radius-lg`) with the exact `<1280` copy. It is **NOT** built from `createStopBannerElement` (that has no dismiss + STOP severity semantics — 5.19 banners are "not user-dismissible"). Own the two copy strings as constants (verbatim from AC/§8.2). Text is a real signal (color + text, never `--blue`-only).
  - [x] Carry a text/`role` so `check_dashboard_color_only.py` sees a text signal alongside the `--blue` edge (mirror the STOP-banner text-tag contract). `role="status"` or a labelled `<aside>` — the banner is informational; do NOT spam `aria-live` on every resize (D3).

- [x] **Task 2 — Viewport detection via matchMedia (D2)** (AC: 1, 2, 3) — *tests-first*
  - [x] Detect with `window.matchMedia("(max-width: 1279.98px)")` (banner visible) and `window.matchMedia("(max-width: 767.98px)")` (upgraded copy), subscribing via `.addEventListener("change", …)` — **not** a `resize` handler (perf rule: no scroll/resize churn; use matchMedia). On a `change` that crosses a boundary, mount/unmount the banner or swap the copy. At ≥ 1280 px the banner is absent (AC1 is "< 1280 px").
  - [x] **<768 upgrade (AC2):** swap the banner text to `This dashboard is desktop-only. Mobile / tablet are unsupported. Open on a screen ≥ 1280 px.` — copy swap only. **NO layout-collapse logic, NO hamburger, NO card stacking** (AC2 explicit; DD-04 single layout). The shell keeps its native size and gains horizontal scroll (already the shell's behavior — do not add collapse CSS).
  - [x] Inject the `matchMedia` factory (a `mediaQueryFn` opt defaulting to `window.matchMedia`) so tests drive boundaries deterministically without a real viewport (web testing rule: deterministic, no flaky resize timing).

- [x] **Task 3 — `×` dismiss via sessionStorage (D3)** (AC: 1) — *tests-first*
  - [x] Add a single `×` close button — `aria-label="Dismiss"`, keyboard-reachable, no transition (DD-14). Click → set a `sessionStorage` flag → remove the banner; the flag suppresses re-mount **for the current session only**, so it **reappears on next page load** (AC1). Use `sessionStorage` (NOT `localStorage` — session-scoped). Guard access in try/catch (restricted-context precedent `resume-card.js:48`).
  - [x] **Sanctioned forbidden-patterns exception:** §8.2 explicitly permits "a single `×` close button (one of the few buttons in the dashboard)" — this is a deliberate exception to §7.12's button-hierarchy ban (only the copy button + this `×` are allowed). Verify `check_dashboard_forbidden_patterns.py` does not flag the `×` (it is not a `<dialog>`/toast/form/modal). If the gate over-triggers, the fix is a narrowly-scoped allow, documented in the PR — do NOT relax the gate broadly.

- [x] **Task 4 — Committed fixtures + tests + packaging + quality gate + freeze** (AC: 1, 2, 3) — *tests-first*
  - [x] Commit fixtures: `viewport-banner.fixture.html` (drives both copies via an injected `mediaQueryFn` / fake MediaQueryList) and a `clean_`/`violation_` pair for `tests/fixtures/dashboard_color_only/` (clean = `--blue` edge + text; violation = color-only). Do NOT rely on real viewport resizing in tests.
  - [x] Tests: `tests/unit/dashboard/test_viewport_banner_fixture.py` (exact copies for <1280 and <768; `.alert.info` `--blue`; text present; `×` keyboard-reachable + `aria-label`; sessionStorage dismiss + reappear-next-load; ≥1280 → no banner; no hamburger/stacking) + a `tests/dashboard/` Playwright a11y witness (color+text, `×` focus order, reduced-motion, no `transition`). RED template: 5.19 `test_stop_banner_fixture.py` + `test_stop_banner_a11y.py`.
  - [x] Add new static files to `force-include` [pyproject.toml]. Component CSS uses `var(--*)` only (5.2 stylelint) and reuses `.alert`/`--blue` — no new color. Run **all dashboard static gates**: `check_dashboard_color_only.py` (banner carries text, not `--blue`-only), `check_dashboard_forbidden_patterns.py` (no `<dialog>`/toast/`<form>`/`pushState`/skeleton; the `×` is the sanctioned exception), `check_dashboard_motion.py` (DD-14 — **no `transition:`** on the banner or `×`), `check_dashboard_no_data_theme.py` (DD-09), `check_dashboard_no_framework.py` (DD-08), `check_dashboard_no_external_fonts.py`.
  - [x] Full `uv run pytest` (the **literal** invocation — subsets lie, memory `project_test_scope_and_order_gotcha`) + coverage ≥ 87%; ruff format/check; `check_module_boundaries.py` (frontend-only; no new Python/route); `mkdocs build --strict`. **Zero wire-format shape change → `scripts/freeze_wireformat_snapshots.py --check` = 7/7** (viewport detection is pure client CSS/JS — no `State` field, no route).

## Dev Notes

### Wave-boundary verification (5.19 → 5.21) — READ FIRST

The `5.19→5.21` edge means 5.21 **reuses the STOP-banner `.alert` treatment** with `--blue` (dag §2:162). Verification against the live codebase (2026-07-07):

- **`.alert`/`--blue` info treatment — PRESENT + reusable.** Story 5.19 shipped `stop-banner.css` with `.alert.info` using the `--blue` left-edge; the `--blue`/`--blue-soft` tokens exist (`tokens.css:121–122`). ⇒ 5.21 reuses the CSS class, not a new color.
- **But STOP banners are NOT dismissible — this banner IS.** `stop-banner.js` `createStopBannerElement` (`:160–210`) builds `role=alert/status`, a severity tag, and an optional copyable action — and **no `×`/dismiss** ("Not user-dismissible" — 5.19 Task 2). 5.21's viewport banner has a `×` (AC1) → it **cannot be built from `createStopBannerElement`**; it reuses the `.alert` **CSS treatment** in a small new element (D1).
- **No viewport-detection code exists yet.** Grep 2026-07-07: zero `matchMedia`/`innerWidth`/`resize`-for-layout anywhere in `dashboard/static/`. The only `1280` references are `--layout-min-viewport: 1280px` (`tokens.css:234`) and two fixture `max-width` decorations. ⇒ 5.21 introduces the first viewport detector (D2, `matchMedia`).
- **sessionStorage has a guarded precedent.** `resume-card.js:48` wraps `sessionStorage` in try/catch for restricted contexts (the once-per-session greeting flag) — reuse that pattern for the dismiss flag.
- **Single-layout contract already holds.** §8.1: "There is no responsive design in v1… single layout." The shell does not collapse; `--layout-shell-max-width: 1360px` centers in wider viewports (`tokens.css:232`). ⇒ 5.21 adds NO breakpoint variants, NO collapse — only the banner + horizontal-scroll acknowledgement.
- **Page not assembled.** `index.html` is still the Story-5.1 skeleton + a single `kpi-strip` live poller (`index.html:14,20–26`). The viewport banner mounts at the top of the page shell; if 5.21 wires `index.html`, coordinate with sibling 5.20 (same L9, §3.3 rebase-between). Fixture-first keeps them parallel.

### Locked design decisions (verbatim — these govern the story)

- **Exact banner copy (verbatim — do NOT paraphrase).**
  - `< 1280 px`: `Dashboard is optimized for screens ≥ 1280 px. Some elements may overflow below this width.`
  - `< 768 px`: `This dashboard is desktop-only. Mobile / tablet are unsupported. Open on a screen ≥ 1280 px.`
  [Source: ux §8.2:1692,1702; epics.md 5.21 AC:2870,2876]
- **§8.2 viewport behavior (normative).** Below 1280 px: horizontal scroll appears on the body, the shell does **not** collapse, all content stays readable at native sizes; a **persistent** banner at top with the copy above; "the banner uses the same treatment as the disconnection banner (§7.11) but with `--blue` (info) severity instead of `--red`"; dismissible for the session via **a single `×`** (reappears next load until viewport ≥ 1280 px). Below 768 px: same scroll behavior, upgraded copy, **no layout-collapse logic, no hamburger menu, no card stacking**. This honors emotional principle #4 (Honest disconnection / no silence). [Source: ux §8.2:1682–1706]
- **DD-04 desktop-only + DD-17 degraded-but-functional.** DD-04: minimum viewport 1280 px, no mobile/tablet layouts in v1. DD-17: below-1280 = horizontal scroll + persistent info banner; below 768 upgrades the copy. [Source: ux DD-04:91, DD-17:1890,1934]
- **The `×` is a sanctioned exception to §7.12.** §7.12 forbids button hierarchy ("the only button is the copy button, DD-12"); §8.2 explicitly carves out the dismiss `×` as "one of the few buttons in the dashboard." So the viewport banner's `×` is legal by explicit spec — but it must stay a single dismiss control, keyboard-reachable, no transition. [Source: ux §7.12:1621, §8.2:1695]
- **Motion / theme guards still bind.** No CSS `transition:`/transforms (DD-14; the `×` dismiss is an instant DOM removal, not an animated collapse). No `[data-theme]` (DD-09). No third-party UI framework (DD-08). Self-hosted fonts only. [Source: ux DD-14 (no transitions), DD-09, DD-08]

### Frozen foundation to consume (do NOT redefine)

```text
Net-new for 5.21 (create):
  components/viewport-banner/viewport-banner.js       matchMedia(<1280 / <768) → mount/swap; sessionStorage dismiss; × close (D1,D2,D3)
  components/viewport-banner/viewport-banner.css       reuse .alert/.info treatment (or @import tokens); NO new color, NO transition
  components/viewport-banner/viewport-banner.fixture.html   both copies via injected mediaQueryFn / fake MediaQueryList

Reuse (do NOT rebuild):
  .alert/.info treatment (--blue edge)   components/stop-banner/stop-banner.css  (.alert + .info; reuse the class, NOT createStopBannerElement)
  --blue / --blue-soft tokens            styles/tokens.css:121–122
  layout tokens (min-viewport / shell)   styles/tokens.css:232–234  --layout-shell-max-width / --layout-min-viewport
  sessionStorage guarded access          components/resume-card/resume-card.js:48  (try/catch restricted-context precedent)
  copy-button chrome (if a control is styled) components/inverted-command/inverted-command.css  (.copy-btn reset)
```

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — reuse the `.alert` CSS treatment, NOT `createStopBannerElement` (MED / correctness).** The viewport banner is **dismissible** and info-only; 5.19's STOP banners are **not user-dismissible** and severity/`TRIGGER_META`-driven. *Recommendation (a):* a small new `viewport-banner` element reusing `stop-banner.css` `.alert`/`.info` (+ `--blue`) for visual consistency, with its own matchMedia + `×` + sessionStorage logic. *(b)* extend `createStopBannerElement` with a dismiss option — **REJECTED** (pollutes STOP semantics; 5.19 is explicitly non-dismissible). Prefer (a).

**D2 — viewport detection: matchMedia change-listener (LOW / perf).** *Recommendation (a):* two `window.matchMedia` queries (`(max-width: 1279.98px)`, `(max-width: 767.98px)`) with `change` listeners — no scroll/resize churn (web performance rule). Inject the factory (`mediaQueryFn`) for deterministic tests. *(b)* a `resize` handler — **REJECTED** (churn + harder to test). Prefer (a). (Use `.98px` upper bounds so the ≥1280 / ≥768 boundaries are exact.)

**D3 — `×` dismiss a11y + sanctioned exception (LOW / a11y + forbidden-patterns).** *Recommendation (a):* single `×` button, `aria-label="Dismiss"`, keyboard-reachable, instant removal (no transition), sessionStorage flag (session-scoped → reappears next load). The banner itself is `role="status"` (informational; NOT `aria-live`-spammed on resize). Confirm `check_dashboard_forbidden_patterns.py` treats the `×` as the §8.2 sanctioned exception; if it over-fires, add a narrow documented allow (do not broadly relax the gate).

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the net-new `viewport-banner` component (matchMedia detection at <1280 / <768, exact copy + upgrade swap, `.alert`/`--blue` reused treatment, `×` dismiss via sessionStorage reappearing next load, horizontal-scroll acknowledgement); its fixtures, tests, and color-only/forbidden-patterns/motion gate coverage.
- **Must NOT build:** the **backend-silence disconnection** treatment (masthead red dot / "cannot reach state" banner / N-fail detection) — that is **5.20** (edge 5.19→5.20). Do NOT conflate the two banners: 5.20's is `--red`, broker-driven, non-dismissible; 5.21's is `--blue`, viewport-driven, dismissible. **Any responsive/breakpoint layout** — no mobile/tablet layouts, no hamburger, no card stacking, no `display:none` collapse (DD-04 single layout; AC2 explicit). **localStorage** (session-only — sessionStorage). **New wire contract / route** (pure client CSS/JS → freeze 7/7). No `transition:`/transforms (DD-14); no `[data-theme]` (DD-09); no framework (DD-08); no toast/modal/notification (§7.12).

### Project Structure Notes

- **Net-new component under the frozen layout convention** `static/components/<name>/<name>.{js,css}` + `<name>.fixture.html` (`live-dot.js:4` D2 convention). All new static files → `force-include` [pyproject.toml].
- **Frontend-only** — no server route, no Python module, no `dashboard→engine/cli` edge. `check_module_boundaries.py` (Python-only AST) is unaffected; keep the JS file small (<300 LOC; siblings ≤260).
- **Reuse, don't fork:** the `.alert`/`.info`/`--blue` treatment is 5.19's; import/reuse the class rather than duplicating the edge CSS. The only genuinely new logic is matchMedia + sessionStorage dismiss + the copy swap.
- **Determinism (web testing rule):** inject `mediaQueryFn` (a fake `MediaQueryList` with a settable `matches` + `dispatchEvent`) — never resize a real viewport in unit tests; Playwright may set an explicit viewport for the a11y witness.
- **L9/5C, cap 2 — co-critical, parallel with 5.20.** Worktree `epic-5/5-21-below-1280-degradation-banner`, owner Sally. Branch from `main`, linear merge (CONTRIBUTING §3). Both L9 worktrees reuse the STOP-banner treatment and may touch `index.html`; per §3.3 the second-merged rebases. Keep 5.21 fixture-first to stay cleanly parallel. 5.22 (terminal a11y gate) re-scans this banner — it must merge clean + a11y-green (color+text, keyboard `×`).
- Zero wire-format contract shape change (client CSS/JS only) → **freeze stays 7/7**.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| `.alert`/`.info` `--blue` edge treatment | `.alert.info` class (reuse CSS, not the JS element) | src/sdlc/dashboard/static/components/stop-banner/stop-banner.css |
| `--blue` / `--blue-soft` info tokens | token vars | src/sdlc/dashboard/static/styles/tokens.css:121–122 |
| Layout tokens (min-viewport / shell max) | `--layout-min-viewport` / `--layout-shell-max-width` | src/sdlc/dashboard/static/styles/tokens.css:232–234 |
| sessionStorage guarded access (dismiss flag) | try/catch restricted-context precedent | src/sdlc/dashboard/static/components/resume-card/resume-card.js:48 |
| Copy-button / control chrome reset (if styled control) | `.copy-btn` reset | src/sdlc/dashboard/static/components/inverted-command/inverted-command.css |
| Component fixture + injected-driver convention | sibling `*-live.fixture.html` + injected fetch/mediaQuery | src/sdlc/dashboard/static/components/*/*.fixture.html |
| RED fixture static-contract template | 5.19 fixture test | tests/unit/dashboard/test_stop_banner_fixture.py |
| Playwright a11y (color+text, focus order, reduced-motion) | 5.19 a11y suite + helpers | tests/dashboard/test_stop_banner_a11y.py; tests/dashboard/_playwright_a11y.py |
| Color-only clean/violation fixtures | `tests/fixtures/dashboard_color_only/` pair | tests/fixtures/dashboard_color_only/ |
| Dashboard static gates | gate scripts | scripts/check_dashboard_{color_only,forbidden_patterns,motion,no_data_theme,no_framework,no_external_fonts}.py |
| Contract-snapshot freeze (assert unchanged) | 7/7 snapshots | tests/contract_snapshots/v1/ ; scripts/freeze_wireformat_snapshots.py --check |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2860–2881] — Story 5.21 statement (2862–2864) + ACs (2868–2881, verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §8.2:1682–1706] — Viewport Behavior Below 1280 px (exact copy, horizontal-scroll, `×` dismiss, no-collapse). **AUTHORITATIVE.**
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §8.1:1660–1680 (single-layout contract), §7.11:1594 (disconnection banner treatment reused with --blue), §7.12:1621 (button-hierarchy ban + the `×` exception via §8.2)] — responsive strategy + treatment origin + forbidden-patterns exception
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md DD-04:91, DD-17:1890,1934; epics.md UX-DR32:228, UX-DR33:229] — desktop-only + degraded-but-functional design requirements
- [Source: src/sdlc/dashboard/static/components/stop-banner/stop-banner.css; stop-banner.js:160–210] — reused `.alert`/`.info` treatment; the STOP element is NON-dismissible (why D1 builds a new element)
- [Source: src/sdlc/dashboard/static/styles/tokens.css:121–122,232–234] — `--blue`/`--blue-soft`; `--layout-min-viewport`/`--layout-shell-max-width`
- [Source: src/sdlc/dashboard/static/components/resume-card/resume-card.js:48] — guarded `sessionStorage` precedent for the dismiss flag
- [Source: src/sdlc/dashboard/static/index.html:14,19–27] — page NOT assembled (kpi-strip only); mount point + 5.20 coordination
- [Source: _bmad-output/implementation-artifacts/5-19-stop-banner-rendering-all-7-trigger-types.md — anti-scope names 5.21 (below-1280 reuses treatment w/ `--blue`); banners "not user-dismissible"] — the treatment origin + the dismiss divergence
- [Source: docs/sprints/epic-5-dag.md §2 (5.19→S21:162, S21→S22:167), §3 (L9 cap 2:218), §4 (co-critical path:258–260), §5 (5.21 row:299), §6 (L9:332)] — layer, edges, owner, co-critical status
- [Source: CONTRIBUTING.md §2 (TDD-first), §3 (worktree-per-story / §3.3 rebase-between), §5 (decision protocol); memory project_test_scope_and_order_gotcha (literal `uv run pytest`)] — process discipline

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (Cursor) — bmad-dev-story workflow.

### Debug Log References

### Completion Notes List

**Task 0 — Decisions resolved (CONTRIBUTING §5):**

- **D1 → (a)** Net-new dismissible `viewport-banner` element that **reuses the `stop-banner.css` `.alert`/`.info` (`--blue`) treatment**, NOT `createStopBannerElement`. Rationale: 5.19 STOP banners are explicitly *not user-dismissible* and carry severity/`TRIGGER_META` semantics; the viewport banner is dismissible + info-only, so it reuses the CSS class only, not the JS element. Option (b) (extend `createStopBannerElement` with a dismiss flag) was REJECTED — it would pollute STOP semantics.
- **D2 → (a)** Viewport detection via two `window.matchMedia` queries (`(max-width: 1279.98px)`, `(max-width: 767.98px)`) subscribed with `.addEventListener("change", …)`; the `matchMedia` factory is injected (`mediaQueryFn` opt, defaults to `window.matchMedia`) so tests drive boundaries deterministically. Option (b) (`resize` handler) REJECTED — churn + flaky. `.98px` upper bounds keep the ≥1280 / ≥768 boundaries exact.
- **D3 → (a)** Single `×` `<button>` with `aria-label="Dismiss"`, keyboard-reachable (native button → inherits the DD-15 `:focus-visible` ring), instant DOM removal (no `transition:` — DD-14). Dismiss sets a **`sessionStorage`** flag (session-scoped → reappears next page load) guarded in try/catch (restricted-context precedent `resume-card.js:48`). The banner is `role="status"` (informational; NOT re-announced on every resize). The `×` is the §8.2 sanctioned exception to the §7.12 button-hierarchy ban.

**Definition of Done (verified):**

- AC1 (<1280 → info banner, `--blue` `.alert.info`, `×` dismiss via sessionStorage reappearing next load) — satisfied; behavioral + static witnesses green.
- AC2 (<768 → upgraded desktop-only copy; NO hamburger/stacking/collapse) — satisfied; copy-swap only, single layout preserved.
- AC3 (resize does not break — matchMedia change crossings mount/swap; shell keeps native size + horizontal scroll) — satisfied.
- Forbidden-patterns exception: the `×` is the sanctioned §8.2 control; `check_dashboard_forbidden_patterns.py` does not over-fire (no gate relax needed).
- Full `uv run pytest`: 4380 passed / 4 skipped / 1 xfailed; coverage 88.62% (≥87%). ruff, mypy --strict, module-boundaries+LOC cap, 6 dashboard gates, stylelint, mkdocs --strict, pre-commit — all green. Wire-format freeze **7/7** (no `State`/route shape change). Only permitted story sections modified.
- Not built (anti-scope): backend-silence disconnection (5.20, `--red`), any responsive/breakpoint layout, localStorage, new wire contract/route, transitions/`[data-theme]`/framework/toast.

### File List

**Added**

- `src/sdlc/dashboard/static/components/viewport-banner/viewport-banner.js` — matchMedia(<1280 / <768) mount/copy-swap; sessionStorage `×` dismiss (D1/D2/D3).
- `src/sdlc/dashboard/static/components/viewport-banner/viewport-banner.css` — reuses the `.alert`/`.info` (`--blue`) treatment; tokens only; no transition (DD-14).
- `src/sdlc/dashboard/static/components/viewport-banner/viewport-banner.fixture.html` — deterministic fixture (injected fake `matchMedia` via `?w=`).
- `tests/unit/dashboard/test_viewport_banner_fixture.py` — static contract (exact copy, boundaries, no-collapse, DD-14, D1, packaging).
- `tests/dashboard/test_viewport_banner_a11y.py` — Playwright behavioral + axe witness (mount/upgrade/dismiss/reappear/change/reduced-motion).
- `tests/fixtures/dashboard_color_only/clean_viewport_banner_with_text.html` — gate clean fixture.
- `tests/fixtures/dashboard_color_only/violation_viewport_banner_color_only.html` — gate violation fixture.

**Modified**

- `src/sdlc/dashboard/static/index.html` — mount `#viewport-banner-host` at the top of the shell + `startViewportBanner` wiring (real `window.matchMedia`).
- `scripts/check_dashboard_color_only.py` — `_scan_viewport_banners` requires a text signal on `viewport-banner alert` (mirrors the STOP-banner text contract; no broad relax).
- `tests/unit/scripts/test_check_dashboard_color_only.py` — clean/violation coverage for the new viewport-banner scan.
- `pyproject.toml` — `force-include` the three new static assets (ADR-005).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 5.21 status transitions.

### Change Log

| Date | Change |
|---|---|
| 2026-07-07 | Task 0 — resolved D1(a)/D2(a)/D3(a); recorded per CONTRIBUTING §5. Story ready-for-dev → in-progress on branch `epic-5/5-21-below-1280-degradation-banner`. |
| 2026-07-07 | Tasks 1-4 — implemented net-new `viewport-banner` component (matchMedia detection, exact <1280/<768 copy, reused `.alert`/`--blue` treatment, `×` sessionStorage dismiss reappearing next load), fixtures, unit + Playwright a11y tests, extended color-only gate, force-include packaging, wired `index.html`. All ACs satisfied. |
| 2026-07-07 | Quality gate GREEN: full `uv run pytest` 4380 passed / 4 skipped / 1 xfailed, coverage 88.62% (≥87%); ruff format+check; mypy --strict; module-boundaries + LOC cap; all 6 dashboard static gates; stylelint; mkdocs --strict; wire-format freeze 7/7 (no shape change); pre-commit all hooks pass. Status → review. |

### Review Findings

> `bmad-code-review` 2026-07-07 — 3 adversarial layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor @ Opus-4.8, fresh-context/no-conversation). Every substantive finding independently verified against source (`viewport-banner.js`, `index.html`, `check_dashboard_color_only.py`). Triage: **2 decision-needed · 4 patch · 0 defer · 1 dismissed.**

- [x] [Review][Decision] `sessionStorage` dismiss persists across a same-tab reload — "reappears on next page load" only holds in a NEW tab — The AC says both "dismisses for the current session **via sessionStorage**" AND "reappears on **next page load**". These conflict: `sessionStorage` survives an in-tab reload (only cleared on tab close), so after `×` the banner stays hidden on F5/reload and reappears only in a fresh tab/window. `viewport-banner.js:32,39,50,111` (`readDismissed` at init). The Playwright witness only drives a fresh `makeStorage()` (new session), never a reload → can't catch it. Options: (a) keep `sessionStorage` as the intended "current session" reading (AC explicitly names it) + fix the wording; (b) true per-load re-show (in-memory only, no storage — contradicts "via sessionStorage"); (c) defer. [blind+edge]
- [x] [Review][Decision] Dismissing the <1280 info banner also silences the escalated <768 "desktop-only / unsupported" copy for the whole session — `update()` short-circuits `if (dismissed || !mqlBelow1280.matches) return` (`viewport-banner.js:120`); after a dismiss at ~1000px, shrinking below 768px never shows `This dashboard is desktop-only. Mobile / tablet are unsupported.` AC2 requires the upgraded copy below 768px but is silent on whether a prior dismiss should suppress the escalation. Options: (a) keep — a dismiss silences the banner for the session at any width (user acknowledged degradation); (b) re-show the stronger copy when crossing below 768 even if previously dismissed (treat <768 as a distinct, more-urgent state); (c) defer. [edge]
- [x] [Review][Patch] **HIGH** — `index.html` mounts the banner JS but never links `viewport-banner.css` → banner renders UNSTYLED on the shipping page [src/sdlc/dashboard/static/index.html:7-9] — `startViewportBanner()` runs at `:27`, host at `:12`, JS import at `:23`, but `<head>` links only tokens/focus-motion/kpi-strip CSS. Below 1280px the real page injects `<aside class="viewport-banner alert info">` with NO `.viewport-banner.alert.info` rules applied → no `--blue` edge / bg / border / padding (AC1 treatment clause fails on the real surface). All Playwright tests hit the fixture (which links the CSS) → gap unguarded. Fix: add `<link rel="stylesheet" href="/static/components/viewport-banner/viewport-banner.css" />` after `tokens.css`; assert index.html links the sheet. [auditor]
- [x] [Review][Patch] **MEDIUM** — `_scan_viewport_banners` text window bleeds past the banner's own close tag → a color-only banner followed by any page text passes the gate (false negative) [scripts/check_dashboard_color_only.py:205-207] — `window_end` runs to the next `viewport-banner alert` match or EOF (not this banner's `</aside>`), and the check accepts ANY non-tag text in that window, so `<aside class="viewport-banner alert info"></aside>` + the page's `<h1>`/footer → non-empty `content` → no violation. `_scan_stop_banners` avoids this by requiring a specific `CRITICAL:/WARNING:/INFO:` token; a bare "any text" check is defeated by unrelated document text. Fix: bound the window to the element's own closing tag (text must live INSIDE the banner) + add a "color-only banner followed by page text" negative test. [blind+edge]
- [x] [Review][Patch] **LOW** — copy swap tears down + rebuilds the `role="status"` element on each boundary crossing → SR re-announcement + keyboard focus dropped to `<body>` [src/sdlc/dashboard/static/components/viewport-banner/viewport-banner.js:117-131] — `update()` calls `clear()` then `createBannerElement()` on every matchMedia `change`: (a) `role="status"` is implicitly `aria-live="polite"`, so a full re-insert re-announces on crossings (the `aria-live`-absent test gives false assurance); (b) if a keyboard user holds focus on `×` when a boundary crosses, the focused node is removed → focus resets to `document.body` (WCAG 2.4.3). Fix: update `message.textContent` in place when the banner already exists (mount/unmount only on the 1280 boundary). Focus-to-body on an intentional `×` dismiss is acceptable (banner gone by design). [blind+auditor+edge]
- [x] [Review][Patch] **LOW** — `startViewportBanner` is not idempotent — a repeat call on the same host leaks the first listener pair and orphans its dispose [src/sdlc/dashboard/static/components/viewport-banner/viewport-banner.js:102-145] — each call attaches new `change` listeners and overwrites `host._stopViewportBanner`; a second mount (re-init / hot-reload) leaks the first two listeners with no dispose handle. Not reachable via the current single-call wiring, but sibling components guard against it. Fix: `if (host._stopViewportBanner) host._stopViewportBanner();` before wiring. [blind+edge]

**Dismissed as noise (1):** `.alert`/`.info` (`--blue`) treatment is re-declared in `viewport-banner.css:11-27` rather than literally reused — `stop-banner.css` scopes it as `.stop-banner.alert`, so literal class reuse is impossible without applying a wrong semantic class or a shared-base refactor of 5.19's shipped CSS (out of story scope). Values verified byte-identical → faithful visual parity; DRY-drift risk only, an acceptable spec-consistent tradeoff. [auditor]

#### Resolution (2026-07-07 — all patches applied, quality gate re-run GREEN)

Decisions resolved per user ("all recommend"): **D1 → (a)**, **D2 → (b)**. Both decisions + all 4 patches implemented; 1 dismissed. Full `uv run pytest` **4385 passed / 4 skipped / 1 xfailed**, coverage **88.60%** (≥87%); ruff + mypy --strict; all 6 dashboard static gates; module-boundaries + LOC; wire-format freeze **7/7**; mkdocs --strict; pre-commit all green. **5 new regression tests** added (index.html-links-CSS, color-only-trailing-text mask, D2 escalation, P3 focus-preserved, P4 no-listener-leak).

- **D1(a) [resolved]** — kept `sessionStorage` (AC-named mechanism = correct "current session"); corrected the JS docstring to "reappears in a NEW tab/session (persists across an in-tab reload)". No logic change. `viewport-banner.js` docstring.
- **D2(b) [resolved → patched]** — dismiss is now scoped per severity **level** (`below-1280` / `below-768`): dismissing the milder <1280 info banner no longer silences the escalated <768 "desktop-only" copy — crossing below 768 re-surfaces it. `viewport-banner.js` (`dismissLevelForWidth` + level-keyed `readDismissed`/`markDismissed`/`update`). Witness: `test_dismiss_below_1280_still_escalates_to_desktop_only_below_768`.
- **P1 [fixed, HIGH]** — added `<link rel="stylesheet" href="/static/components/viewport-banner/viewport-banner.css" />` to `index.html`; the mounted banner is now styled on the real page. Guard: `test_index_html_links_stylesheet_when_banner_mounted`.
- **P2 [fixed, MED]** — `_scan_viewport_banners` text window now bounded to the banner's own closing tag; a color-only banner followed by page text is caught. Witness: `test_scan_flags_color_only_viewport_banner_with_trailing_page_text` + `violation_viewport_banner_color_only_trailing_text.html`.
- **P3 [fixed, LOW]** — `update()` swaps `message.textContent` in place when the banner already exists (mount/unmount only at the 1280 boundary) → no `role=status` re-announcement, keyboard focus on `×` preserved. Witness: `test_copy_swap_preserves_dismiss_focus_in_place`.
- **P4 [fixed, LOW]** — `startViewportBanner` disposes any prior instance on the host before re-wiring (idempotent). Witness: `test_repeat_start_on_same_host_has_no_listener_leak`.
- **Dismissed** — `.alert` CSS duplication (values byte-identical; shared-base refactor out of scope).
