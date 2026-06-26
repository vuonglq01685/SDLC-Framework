# Story 5.6: Masthead + Browser Tab Title Automation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L4 (5A). L4 = {5.6, 5.7, 5.8, 5.11}, max 4 parallel worktrees (cap-saturating — `max_parallel_agents=4`, CONTRIBUTING §3.2 / PRD FR51). Depends on 5.5 (live-dot + freshness-footer FROZEN) (+ 5.2 frozen tokens) — ALL done+merged. Edges: 5.2→5.6, 5.5→5.6; downstream 5.6→5.12 (a11y convergence gate), 5.6→5.20 (honest-disconnection REUSES the 60s aria-live rate-limit this story OWNS). Worktree: epic-5/5-6-masthead-tab-title. Branch from main, linear merge, rebase between L4 merges (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). SYNTHETIC fixtures only — real disconnection detection (≥3 consecutive poll fails) + real state.json identity wiring is 5.20/5.18; this story renders the disconnected VISUAL state from a fixture and OWNS the rate-limit MECHANISM 5.20 drives. -->

## Story

As Diep opening the dashboard mid-stream,
I want the Masthead at the top of every page rendering project name + arrow + phase title, sub-line (project · owner · last-updated), right rail (port + LIVE indicator), and the browser tab title kept in sync per poll,
So that project identity is unambiguous across multiple browser tabs (DD-05) and the editorial register is established (UX-DR1, §6.2).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.6, lines 2516–2537).

**AC1 — Masthead structure + typography**
- **Given** the Masthead component **When** rendered at the top of the dashboard **Then** the structure is: `<header role="banner">` containing `<h1>` (project name + arrow + phase) + `.sub` line + right rail (port + live dot)
- **And** the bottom `1px solid var(--ink)` rule is present (the broadsheet rule line)
- **And** typography matches §6.2 spec: Fraunces 32px 600 for h1, label-mono uppercase for sub and right rail

**AC2 — Right-rail live-region (aria-live, rate-limited)**
- **Given** the right-rail live-region **When** the polling state changes (live → warn → disconnected) **Then** an `aria-live="polite"` announcement fires (rate-limited to 60 s between announcements)
- **And** the live-dot variant updates accordingly (Story 5.5)

**AC3 — Browser tab title automation**
- **Given** the browser tab title automation **When** state.json is polled (3-second interval per Decision E2) **Then** `document.title` is set to `{project_name} · Phase {N} {P}%` per UX spec §6.2
- **And** an integration test (Playwright) opens the dashboard, polls state, and asserts the tab title updates within one poll cycle

**AC4 — Disconnected state sub-line**
- **Given** the disconnected state (Story 5.20) **When** the backend goes silent **Then** the masthead's sub-line shows `DISCONNECTED · LAST POLL HH:MM:SS` instead of `UPDATED HH:MM:SS`
- **And** the live-dot variant is `disconnected`

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the **tab-title format (AC3)**, the **aria-live rate-limit (AC2)**, and the **disconnected sub-line text (AC4)** are deterministic behavior → tests-first. AC3 mandates a **Playwright** test (open dashboard, poll synthetic state, assert `document.title` updates within one 3s poll cycle). AC2 = a pure unit test over an injected clock (one announcement per 60 s; fires only on state *change*, not every poll). AC4 = render a synthetic `disconnected` fixture, assert the sub-line + `<live-dot variant="disconnected">`. The masthead CSS/HTML substrate is `test-along`. Resolve Decisions D1–D4 BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (compose `--type-display-1` sub-tokens) + D2 (live-dot variant mapping `default`/`warn`/`disconnected`) + D3 (phase format: H1 `Phase N` vs tab-title `Phase N P%`) + D4 (sub-line separator `·` + `HH:MM:SS`) BEFORE coding** (AC: 1, 2, 3, 4)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). Align the component layout to the 5.5-frozen `static/components/<name>/` convention.

- [x] **Task 1 — Masthead structure + broadsheet typography** (AC: 1)
  - [x] `<header role="banner">` containing `<h1>` (project name + `→` arrow in `--accent` + `Phase {N}`) + `.sub` line (`project · owner · UPDATED HH:MM:SS`) + a right rail (`PORT {port}` + `<live-dot>`). [§6.2 anatomy table, ux:1052-1059]
  - [x] Bottom rule = `border-bottom: var(--border-strong)` (`1px solid var(--ink)`, the "broadsheet rule line"). Masthead radius `--radius-none`.
  - [x] H1 type = compose `--type-display-1-{size:32px,line-height:1,weight:600,letter-spacing:-0.015em}` + `font-family: var(--font-serif)` (D1 — NO single `--type-display-1` var exists). Sub + right rail = compose `--type-label-mono-{size,line-height,weight,letter-spacing}` + `var(--font-mono)` + `text-transform: uppercase` (mirror live-dot.css:24-30).

- [x] **Task 2 — Browser tab-title automation (3s poll, Decision E2)** (AC: 3) — *tests-first*
  - [x] Extract a pure formatter `formatTabTitle(project, n, p) => "${project} · Phase ${n} ${p}%"` (separator `·` U+00B7) and unit-test it (AAA). [§6.2 ux:1068; epics:2531]
  - [x] Poll `GET /state.json` on a **3-second** interval (Decision E2 — architecture.md §372: "3-second SPA polling with ETag + 304"; send `If-None-Match`, skip re-render on 304), map the synthetic state object → `document.title` via the formatter on each poll. Real `state.json` identity wiring is 5.18/5.20; 5.6 drives from a SYNTHETIC fixture state.
  - [x] **Playwright** integration test (AC3 binding): open the dashboard fixture, advance one poll cycle, assert `document.title === "{project_name} · Phase {N} {P}%"` within one cycle. Extend the 5.4/5.10 Playwright surface.

- [x] **Task 3 — Right-rail `aria-live` rate-limit (60 s, change-only)** (AC: 2) — *tests-first*
  - [x] `aria-live="polite"` region on the right rail. Announce ONLY connection-state *changes* (live→warn→disconnected), never routine polls (§7.12 forbids per-poll toast announcements, ux:1634). Rate-limit to **one announcement per 60 s** (epics:2526; §6.2 ux:1072). **This story OWNS the 60s rate-limit mechanism; 5.20 reuses it.**
  - [x] On state change, set `<live-dot variant>` (D2 mapping). Live-dot internals/colors/pulse are FROZEN by 5.5 — pass the `variant` attribute only; do NOT re-style the dot.
  - [x] Unit-test the rate-limiter with an injected clock: only one announcement per 60 s window across N changes; fires on *change* only (mirror freshness-footer's `now`-injection pattern).

- [x] **Task 4 — Disconnected sub-line + live-dot variant (synthetic)** (AC: 4)
  - [x] Given a synthetic `disconnected` state, render the sub-line as `DISCONNECTED · LAST POLL HH:MM:SS` (replacing `UPDATED HH:MM:SS`) and `<live-dot variant="disconnected">`. Reuse `freshness-footer.formatLocalTime()` for `HH:MM:SS`. [§6.2 States ux:1064; §7.11 ux:1605]
  - [x] Do NOT implement real disconnection detection (the ≥3-consecutive-poll-fail logic is 5.20). Render the visual state from a fixture flag only.

- [x] **Task 5 — Committed synthetic fixture + tests** (AC: 1, 2, 3, 4) — *tests-first*
  - [x] Commit a `masthead.fixture.html` (link tokens.css + focus-motion.css + own CSS, mirror live-dot.fixture.html). Add the unit tests (formatter, rate-limiter, disconnected sub-line) + the Playwright tab-title test. **RED:** wrong title format / per-poll announcement / `UPDATED` in disconnected state fails; **GREEN:** correct. Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`).

- [x] **Task 6 — Packaging + quality gate + freeze** (AC: 1, 2, 3, 4)
  - [x] Add new CSS/JS/HTML (masthead + fixture) to the `force-include` block [pyproject.toml] to ship in the wheel.
  - [x] Component CSS uses `var(--*)` only (5.2 stylelint gate); run DD-14 motion gate (no `transition:`/transforms — connection-state change is a content/class swap), DD-08 no-framework gate, DD-09 no-data-theme, the 5.3 no-external-fonts gate, and the 5.5 color-only gate.
  - [x] Python quality gate on any new `scripts/*.py`/tests (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7**.

### Review Findings

> bmad-code-review (2026-06-26) — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + orchestrator source-verification (every HIGH/MEDIUM reproduced against the real `masthead.js` / `masthead.css` / fixture / tests). Reviewed jointly with Story 5.7. Triage for 5.6: **1 decision-needed + 7 patch + 3 defer**.

- [x] [Review][Patch] (D1 → resolved **D1-(a)**) Poller `tick()` catch must swallow the error and keep the last-known-good render — remove the synthetic `mapStateFromJson({ connection_variant: "disconnected" }, …)` render [masthead.js:143-144]. Rationale: real disconnection detection (≥3-consecutive-fail) is reserved for Story 5.20 (5.6 anti-scope); the synthetic-disconnected fallback also wiped real state → `Unknown Project · Phase 1 0%`. Disconnected visual stays fixture-driven only.
- [x] [Review][Patch] aria-live rate-limiter permanently swallows a connection-state change (AC2) — `lastVariant` is advanced *before* the 60s rate-limit early-return, so a change suppressed within the window is never re-announced and `default→disconnected`(stays) is announced never [masthead.js:28-34]
- [x] [Review][Patch] aria-live region destroyed/recreated on every render → polite announcements unreliable (AC2) — `root.replaceChildren()` rebuilds the `aria-live` region as a fresh node each poll; the region must persist and only its text update [masthead.js:82,111-130]
- [x] [Review][Patch] Every masthead instance (incl. static/disconnected) hijacks `document.title` — unconditional `document.title =` clobbers the tab from non-poll instances and makes `test_tab_title_updates_within_one_poll_cycle` a false-pass (static sibling sets the exact asserted title synchronously) [masthead.js:131]
- [x] [Review][Patch] H1 spans rendered with no separating whitespace/margin → `SDLC-Framework→Phase 2` cramped — `.masthead__arrow` has no inline margin and the h1 is not flex [masthead.css:38-40, masthead.js:94-101]
- [x] [Review][Patch] `resolveConnectionVariant` does not `.trim()` (inconsistent with kpi `resolveState`) — `" disconnected"` falls through to LIVE, masking a real disconnect [masthead.js:9]
- [x] [Review][Patch] Static masthead without a `phase` attribute renders `Phase 0` — `Number(null)===0` is finite so the intended `1` default never applies; the poll path (undefined→NaN→1) is inconsistent [masthead.js:61]
- [x] [Review][Patch] Weak export assertion — `assert "export {" in js and "formatTabTitle" in js` passes via the function definition even if the symbol is dropped from the export block [test_masthead_fixture.py]
- [x] [Review][Defer] Overlapping/async polls — no in-flight re-entrancy guard or AbortController; a slow response can render out-of-order and an in-flight fetch can `renderMasthead`/setTitle after `disconnectedCallback` [masthead.js:148] — deferred: localhost + 304 make overlap low-probability; harden when real wiring lands (5.18/5.20)
- [x] [Review][Defer] `progress`/`phase` not range-validated (negative/>100/float → `Phase -1 · 150%`) [masthead.js:61-62] — deferred: state.json is framework-written; clamp when real identity wiring lands (5.18)
- [x] [Review][Defer] No initial/loading render — a first 304 or 200-`null` body (not produced by the real `/state.json` route) leaves the masthead blank until the next renderable poll [masthead.js:141] — deferred: real route 200s the first request; latent only

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§6.2 Masthead.** Anatomy table [ux:1052-1059]: Title `h1` = `--type-display-1` (Fraunces 32px 600), project name + arrow + phase; Arrow = `--accent` color; Sub-line `.sub` = `--type-label-mono` uppercase (project · owner · last-updated); Right rail = `--type-label-mono` uppercase (port + LIVE); Live dot = §6.8 (pulses, or static under DD-16); Bottom rule = `--border-strong` (1px solid `--ink`, "broadsheet rule line"). States: Default (green pulsing) / Warn (amber, poll succeeded but stale data) / Disconnected (red, sub-line `DISCONNECTED · LAST POLL HH:MM:SS`). *"No silence — DD principle 'Honest disconnection' enforced."* Browser tab title: *"set by JavaScript on each poll to `{project_name} · Phase {N} {P}%`."* a11y: `role="banner"`; live region `aria-live="polite"` on the right rail, **rate-limited to once per 60 s**. Keyboard: *"No interactions. Read-only."* [Source: ux-design-specification.md §6.2, lines 1036–1076]
- **§3.2 typography.** `--type-display-1` = 32px / serif 600 / `letter-spacing: -0.015em` (Masthead H1); `--type-label-mono` = 11px mono 500 / 0.12em / uppercase (section labels, masthead sub). Pairing rule #4: *"the masthead is the canonical mixing surface — serif H1, mono sub-line, mono right-rail."* [Source: ux-design-specification.md §3.2:603-624, §3.4:683]
- **§7.11 Honest-Disconnection.** *"Masthead — live-dot turns red and stops pulsing; sub-line shows `DISCONNECTED · LAST POLL HH:MM:SS`."* Disconnection is page-wide, triggers after polling fails **≥3 consecutive times** — that detection is **5.20's** job, not 5.6's. [Source: ux-design-specification.md §7.11:1605-1613]
- **§7.12 Forbidden Patterns.** *"'Live region' toast announcements for routine polls"* is FORBIDDEN — *"the masthead live region announces only changes in connection state, rate-limited to 60 s."* No animated transitions (DD-14). [Source: ux-design-specification.md §7.12:1634]
- **Decision E2 (3-second polling).** *"3-second SPA polling with ETag + 304 Not Modified on state.json hash."* NOT a `docs/sprints/epic-5-dag.md` decision (the DAG only defines D1/D2/D3) — it is an **architecture.md** decision. [Source: architecture.md §372; epics.md:2530]

### Frozen foundation to consume (do NOT redefine — 5.2/5.4/5.5 froze these)

```css
/* tokens.css — masthead vocabulary (consume per-property var; NO composite --type-display-1) */
--type-display-1-size:32px; --type-display-1-line-height:1; --type-display-1-weight:600; --type-display-1-letter-spacing:-0.015em;  /* h1 */
--type-label-mono-size:11px; --type-label-mono-line-height:1; --type-label-mono-weight:500; --type-label-mono-letter-spacing:0.12em; /* sub + right rail */
--font-serif:"Fraunces",…;  --font-mono:"JetBrains Mono",…;
--accent (arrow);  --ink (#eceef3);  --ink-mute (#8b92a2, dim timestamp);
--border-strong: 1px solid var(--ink);  /* broadsheet rule */   --radius-none: 0;
/* live-dot colors --green/--amber/--red live INSIDE <live-dot> — never re-declare */
```
```text
<live-dot variant="…">  — ONLY observed attribute is `variant`. Frozen keys: `default` (label "LIVE", green, pulses),
  `warn` (label "WARN", amber), `disconnected` (label "DISCONNECTED", red). Unknown → falls back to `default`.
  Exports: VARIANTS, renderLiveDot, resolveVariant. [live-dot.js:8-17,37,61]
<freshness-footer last-poll variant now>  — reuse formatLocalTime(date) → zero-padded HH:MM:SS [freshness-footer.js:12-15].
focus-motion.css — a/button/[role] :focus-visible ring already wired (project link / port info ride it as <a>/<button>).
GET /state.json — 200 + content-hash ETag + Content-Type application/json; 304 on If-None-Match; 404 if missing. [routes/state.py:18,24,31-40]
```
[Source: tokens.css:111,127-140,182-185,239,244; live-dot.js/.css; freshness-footer.js:12-15; focus-motion.css:16-26; routes/state.py:12-40]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — `--type-display-1` is not a single CSS var.** §6.2/§3.2 reference `--type-display-1` and `--type-label-mono` as if atomic, but the FROZEN tokens.css per-property convention only exposes the `-size/-line-height/-weight/-letter-spacing` sub-tokens. *Recommendation (a):* compose the four sub-tokens + `font-family: var(--font-serif)` (exactly as live-dot.css:24-30 composes `--type-label-mono-*`). Do NOT invent a shorthand token (would touch frozen tokens.css). *(b)* escalate a new composite token to the Project Lead — rejected; prefer composition.

**D2 — Live state attribute is `default`, not `live`.** epics:2525 and the right-rail label "LIVE" imply a `live` variant, but `live-dot.js` VARIANTS keys are `default`/`warn`/`disconnected` (the `default` variant's *label text* is "LIVE"). Passing `variant="live"` silently falls back to `default`. *Recommendation (a):* map the masthead's connection state to the FROZEN attribute values `default`/`warn`/`disconnected` (treat `default` = "live/connected"); document the mapping so 5.20 inherits it. Do NOT add a `live` alias to the frozen 5.5 element.

**D3 — Phase format differs by surface.** H1 shows `{project} → Phase {N}` (no %, ASCII ux:1046); tab title is `{project} · Phase {N} {P}%` (with %, ux:1068). *Recommendation (a):* render them as two distinct targets fed by the same synthetic state object — H1 (arrow in `--accent`, no percent) + `document.title` (with percent). AC3's Playwright assertion targets only the tab title.

**D4 — Sub-line separator + timestamp granularity.** ASCII shows `· · UPDATED 09:42` (minutes); §6.2 States + §7.11 specify `HH:MM:SS`. *Recommendation (a):* use `HH:MM:SS` via `freshness-footer.formatLocalTime` (the prose is binding; the ASCII `09:42` is illustrative); uppercase the whole sub-line via `text-transform: uppercase`; separator `·` (U+00B7).

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the **Masthead** (`role="banner"`, serif H1 + mono sub-line + right rail + broadsheet rule), the **browser tab-title automation** (3s poll → `document.title`), and the **60 s `aria-live` rate-limit mechanism** (reused by 5.20). Synthetic fixture data only.
- **Must NOT build:** real disconnection detection (≥3-consecutive-poll-fail → page-wide disconnected — that is **5.20**, edge 5.6→5.20); real `state.json` identity wiring / "you are here" (5.18); the below-masthead red disconnection banner (5.20/5.21); the KPI strip (5.7), resume card (5.8), tabs/feed (5.11); live-dot internals/pulse/colors (FROZEN by 5.5 — pass `variant` only). No toasts / browser notifications / animated transitions / spinners (§7.12); no responsive/mobile layout or theme switch (DD-04 desktop-only, DD-01 dark-only). [Source: docs/sprints/epic-5-dag.md §2 (5.6→5.12, 5.6→5.20), §3 (L4), §6 (5.6 row:284)]

### Project Structure Notes

- New: `static/components/masthead/` (CSS/JS/fixture) under the 5.5-frozen `static/components/` convention. All new static files → `force-include` [pyproject.toml] (else absent from the wheel).
- Component CSS must use `var(--*)` — the 5.2 stylelint gate FORBIDS raw values for color/background-color/font-size/font-family/padding/margin/gap/letter-spacing/line-height/border-radius/border-width [.stylelintrc.json]. `font-weight: 600` is allowed as a literal.
- The masthead is read-only (no interactions) — its only focusable elements are the optional project link / port info (`<a>`/`<button>`, which ride the 5.4 focus ring). The aria-live region is the sole dynamic a11y surface.
- L4 siblings (5.6/5.7/5.8/5.11) mutually independent; cap-saturating (4 worktrees, zero slack — staff ≥3 authors per DAG §6 note). Branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3).
- Zero wire-format contracts (CSS/JS/HTML are not wire contracts) → freeze stays 7/7.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Live indicator dot + variants | `<live-dot variant="default\|warn\|disconnected">` (frozen) | src/sdlc/dashboard/static/components/live-dot/live-dot.js |
| `HH:MM:SS` timestamp formatting | `freshness-footer.formatLocalTime(date)` | src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:12-15 |
| Masthead tokens (h1/sub/rule/arrow) | Consume frozen tokens (D1 compose for h1/sub) | src/sdlc/dashboard/static/styles/tokens.css:111,127-140,182-185,239,244 |
| Focus ring (project link / port info) | a/button/[role] `:focus-visible` already wired | src/sdlc/dashboard/static/styles/focus-motion.css:16-26 |
| Poll source (3s, ETag/304) | `GET /state.json` | src/sdlc/dashboard/routes/state.py:18,24,31-40 |
| Playwright test surface | Extend the 5.4/5.10 Playwright surface for the tab-title assertion | tests/integration/test_dashboard_*.py, .github/workflows/ci.yml |
| Motion / no-framework / color-only gates | Run the dashboard gate scripts on the new masthead | scripts/check_dashboard_motion.py / _no_framework.py / _color_only.py |
| Wheel force-include | Add new static files | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2510-2537] — Story 5.6 ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.2:1036-1076] — Masthead anatomy + states + tab-title + a11y + keyboard
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §3.2:603-624, §3.4:683] — `--type-display-1` / `--type-label-mono` / `--border-strong`
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.11:1605-1613, §7.12:1634] — honest-disconnection (≥3-fail = 5.20) + aria-live change-only/60s
- [Source: _bmad-output/planning-artifacts/architecture.md §372] — Decision E2 (3-second polling + ETag/304)
- [Source: src/sdlc/dashboard/static/components/live-dot/live-dot.js:8-17,37,61] — `<live-dot variant>` frozen keys default/warn/disconnected (drives D2)
- [Source: src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:12-15] — `formatLocalTime` HH:MM:SS
- [Source: src/sdlc/dashboard/static/styles/tokens.css:111,127-140,182-185,239,244] — frozen masthead tokens (drives D1)
- [Source: src/sdlc/dashboard/static/styles/focus-motion.css:16-26] — focus ring (project link / port info)
- [Source: src/sdlc/dashboard/routes/state.py:12-40] — `GET /state.json` poll source (ETag/304)
- [Source: src/sdlc/dashboard/static/styles/.stylelintrc.json] — var(--*) enforcement
- [Source: docs/sprints/epic-5-dag.md §2 (5.6→5.12, 5.6→5.20), §3 (L4:213), §6 (5.6 row:284)] — layer, edges, "owns 60s aria-live rate-limit reused by 5.20"
- [Source: _bmad-output/implementation-artifacts/5-5-live-dot-family-freshness-footer-pattern.md] — L4 upstream that froze live-dot + freshness-footer + the file-layout convention

## Dev Agent Record

### Agent Model Used

claude-opus-4-8-thinking-high (Cursor)

### Debug Log References

- Custom element tag `sdlc-masthead` (hyphen required by HTML CE registry; folder remains `masthead/` per 5.5 layout convention).

### Completion Notes List

- D1–D4 resolved per story recommendations (a): compose `--type-display-1-*` sub-tokens; map `default`/`warn`/`disconnected`; split H1 vs `document.title` formats; `·` + `formatLocalTime` HH:MM:SS.
- Implemented `<sdlc-masthead>` with inner `<header role="banner">`, broadsheet typography, right-rail `aria-live` rate-limiter (60s, change-only), 3s `state.json` poll with ETag/304, and `formatTabTitle`.
- Committed `masthead.fixture.html` + unit contract tests + Playwright integration tests (13 passing).
- Added masthead assets to `pyproject.toml` force-include; dashboard gates DD-08/09/10/14 + color-only GREEN on masthead tree.

### File List

- src/sdlc/dashboard/static/components/masthead/masthead.js
- src/sdlc/dashboard/static/components/masthead/masthead.css
- src/sdlc/dashboard/static/components/masthead/masthead.fixture.html
- tests/unit/dashboard/test_masthead_fixture.py
- tests/integration/test_dashboard_masthead.py
- pyproject.toml

## Change Log

- 2026-06-25: Story 5.6 created (create-story, "tạo US cho layer tiếp theo" → L4 batch with 5.7/5.8/5.11) — Masthead (`role="banner"`, serif H1 + mono sub-line + right rail + broadsheet rule) + browser tab-title automation (3s poll, Decision E2) + 60 s `aria-live` rate-limit (OWNED here, reused by 5.20). Decisions D1 (compose `--type-display-1` sub-tokens) / D2 (live-dot variant mapping `default`/`warn`/`disconnected`) / D3 (phase format H1 vs tab title) / D4 (`·` separator + `HH:MM:SS`) raised. L4 (5A), synthetic only; depends on 5.5 (live-dot/freshness-footer) + 5.2 (tokens); feeds 5.12 a11y gate + 5.20 disconnection. Do-not-build real disconnection/identity wiring noted.
- 2026-06-25: Implemented Story 5.6 masthead + tab-title automation (`sdlc-masthead`, synthetic fixture, Playwright + contract tests, wheel force-include).
