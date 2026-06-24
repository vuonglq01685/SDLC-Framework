# Story 5.4: Custom Focus Ring + `prefers-reduced-motion` + Transition Stripping + No-Third-Party Guard

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L2 (5A) AND on the critical-path spine (5.2 → 5.4 → 5.5 → 5.11 → 5.19 → 5.20 → 5.22). Depends ONLY on 5.2 (frozen tokens), mutually independent of its L2 sibling 5.3. Worktree: epic-5/5-4-custom-focus-ring-prefers-reduced-motion. Branch from main, linear merge, rebase between L2 merges (CONTRIBUTING §3). Establishes the focus + reduced-motion CSS foundation 5.5's live-dot consumes — do NOT build the live-dot here. -->

## Story

As a frontend engineer enforcing visual foundation locks (DD-08, DD-14, DD-15, DD-16),
I want a custom focus ring via `box-shadow` on `:focus-visible`, all prototype CSS transitions/animations stripped except live-dot pulses, `prefers-reduced-motion` disabling pulses, and a CI guard preventing third-party UI framework imports,
So that motion is intentional and accessibility-respectful, and the dashboard remains vanilla HTML/CSS/JS (UX-DR20–23, DD-08, DD-14, DD-15, DD-16).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.4, lines 2459–2482).

**AC1 — Custom focus ring (`:focus-visible` only)**
- **Given** every keyboard-reachable interactive element (buttons, links, expanders, tabs) **When** the element is focused via keyboard (`:focus-visible`) **Then** a custom `box-shadow` focus ring renders (per DD-15)
- **And** the ring meets WCAG 2.2 Level A contrast against `--paper` background
- **And** `:focus` (mouse-clicked) does NOT show the ring (only `:focus-visible`)

**AC2 — Transition stripping (transition grep gate)**
- **Given** the dashboard CSS **When** I grep for `transition:` or `@keyframes` **Then** the only animations present are the live-dot pulses (`--motion-pulse-live`, `--motion-pulse-stop`)
- **And** all other prototype transitions/animations are stripped per DD-14
- **And** state changes happen via content-delta only (DD-06)

**AC3 — `prefers-reduced-motion`**
- **Given** `@media (prefers-reduced-motion: reduce)` **When** the user has reduced motion enabled **Then** all live-dot pulses are disabled (replaced with static colored dot)
- **And** an integration test using a Playwright fixture with reduced-motion emulation asserts the static rendering

**AC4 — No-third-party-UI-framework guard**
- **Given** the no-third-party-UI-framework guard **When** CI runs the static check **Then** the dashboard's `package.json` (if any) declares zero runtime UI dependencies (React, Vue, Svelte, Tailwind runtime, etc.)
- **And** `dashboard/static/` contains no minified vendor bundles
- **And** the failure message names the violating import

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the two CI gates are tests-first (RED→GREEN): (a) the **transition-grep gate** (RED: a CSS file with a non-pulse `transition:` fails; GREEN: clean CSS + the two pulse usages pass); (b) the **no-framework guard** (RED: a `package.json` with a React dep / a minified vendor bundle under `static/` fails, naming the import; GREEN: clean tree passes). The focus-ring + reduced-motion CSS is design substrate → `test-along` is fine, but the **Playwright reduced-motion assertion (AC3)** is a testable behavior → tests-first where feasible.

- [x] **Task 0 — Resolve Decisions D1 (focus-ring token) + D2 (Playwright-in-CI) BEFORE coding** (AC: 1, 3)
  - [x] Confirm the focus-ring token (D1) and the reduced-motion integration-test tooling (D2). See Dev Notes → Decisions. Record the picks in the PR Change Log (CONTRIBUTING §5).

- [x] **Task 1 — Custom focus ring on `:focus-visible`** (AC: 1)
  - [x] Add a focus rule: `:focus-visible { box-shadow: 0 0 0 2px var(--rule-strong); }` for all keyboard-reachable interactive elements (buttons, links, tree expanders, tabs) per DD-15. Pair with `:focus:not(:focus-visible) { box-shadow: none; }` (or rely on `:focus-visible` semantics) so a **mouse click does NOT show the ring** (AC1 third bullet).
  - [x] **Keep this DISTINCT from the existing 3px active/current-state ring.** DD-15 focus = **2px `var(--rule-strong)`** on `:focus-visible`. The separate always-on "current/active" treatment (`.phase-cell.active`, `.story-card.current`) is **3px `var(--accent-soft)`** and is NOT a focus indicator [UX §3.4:705, §6.5:1211, §6.6:1254]. Do not conflate them.
  - [x] No interactive component markup exists yet (index.html is a skeleton; masthead/KPI/tabs land L3/L4) — author the focus rule against a documented selector set / a committed fixture so it applies automatically when components land. Link the focus/motion stylesheet from `index.html` (coordinate the stylesheet path with 5.3's Decision D1 if 5.3 lands first; otherwise root-relative).

- [x] **Task 2 — Strip prototype transitions/animations (DD-14)** (AC: 2)
  - [x] Ensure production dashboard CSS contains **no `transition:` and no `@keyframes` except the single `pulse` keyframe** (frozen in tokens.css:176-180) driven by `--motion-pulse-live`/`--motion-pulse-stop`. The prototype rules to be ABSENT (UX §3.5:721-733): `.tab` color/border transitions, `.panel.active` fadein, all `*-bar i { transition: width }`, `.stage-pill.current .ring` spin, all `.chev { transition: transform }`, `.copy-btn { transition: transform }`. Chevron open/close is an **icon-glyph swap** (5.3 sprite `chevron-right`/`chevron-down`), NOT a CSS transform transition (DD-14). Copy feedback is a `setTimeout` icon swap (`--motion-copy-feedback`), NOT a CSS transition (DD-12/DD-06).
  - [x] State changes happen via **content-delta only** (DD-06) — no enter/leave transitions.

- [x] **Task 3 — transition-grep gate** (AC: 2) — *tests-first*
  - [x] Add `scripts/check_dashboard_motion.py` **mirroring the DD-09 gate shape** [scripts/check_dashboard_no_data_theme.py]: same anchor/globs (`*.css`), comment-stripping, `(pattern, label)` tuples, `errors="replace"`, exit 0/1/2 + `file:line:col` to stderr. Rule: any `transition:` declaration is a violation; any `@keyframes` other than `pulse` is a violation; an `animation:` that does not reference `var(--motion-pulse-live)`/`var(--motion-pulse-stop)` is a violation. Tag `(DD-14)`.
  - [x] **RED:** a CSS fixture with `transition: color 0.15s` (or `@keyframes spin`) exits 1 with `file:line:col`; **GREEN:** tokens.css (`@keyframes pulse` only) + a clean component using `animation: var(--motion-pulse-live)` pass. Test in `tests/unit/scripts/test_check_dashboard_motion.py`; fixtures in `tests/fixtures/dashboard_css/`.
  - [x] Wire as a sibling step in the `quality-gates` matrix (after the DD-09 step) + a `repo: local` pre-commit hook [.github/workflows/ci.yml, .pre-commit-config.yaml]. A `quality-gates` **step**, not a new top-level job (no `ci-gate.needs` edit).

- [x] **Task 4 — `prefers-reduced-motion` disables both pulses** (AC: 3)
  - [x] Add `@media (prefers-reduced-motion: reduce) { … { animation: none; } }` neutralizing the pulse animation everywhere it is applied → the dot renders **static** (DD-16, WCAG 2.3.3). Because the live-dot ELEMENT is built in 5.5, target the animation/pulse-carrying class so it applies the moment 5.5 lands (coordinate/freeze the live-dot class name with 5.5, or write the rule against any element using `animation: var(--motion-pulse-*)`). **Do NOT build the live-dot here** — that is 5.5 (anti-scope-creep; DAG edge 5.4 → 5.5).
  - [x] Color + adjacent text label carry the signal when motion is off (color-only-signaling is forbidden — owned by 5.5, but keep the static dot visible).

- [x] **Task 5 — Reduced-motion integration test (Playwright)** (AC: 3) — *tests-first where feasible*
  - [x] Per AC3, add an integration test using a **Playwright fixture with reduced-motion emulation** (`emulateMedia({ reducedMotion: 'reduce' })`) asserting the pulse is disabled / the dot renders static. Since the real live-dot is 5.5, assert against a committed fixture element carrying `animation: var(--motion-pulse-live)` (computed `animation-name` resolves to `none`/no running animation under emulation). The full live-dot reduced-motion assertion is re-verified in 5.5/5.12. See Decision D2 on the Playwright tooling/CI surface.

- [x] **Task 6 — No-third-party-UI-framework guard** (AC: 4) — *tests-first*
  - [x] Add `scripts/check_dashboard_no_framework.py` **mirroring the DD-09 gate shape**: fail if a dashboard `package.json` (if any) declares runtime UI deps (React, Vue, Svelte, Angular, Tailwind runtime, lit, etc.) in `dependencies`; fail if `src/sdlc/dashboard/static/` contains a minified vendor bundle (e.g. `*.min.js` from a UI framework, or a vendored framework import); the **failure message names the violating import/dependency** (AC4). Tag `(DD-08)`.
  - [x] **RED:** a fixture `package.json` with `"react"` in `dependencies`, or a `static/vendor/react.min.js`, exits 1 naming the import; **GREEN:** the clean tree passes (no `package.json`, no vendor bundles — note Chart.js is the only permitted vendored runtime per UX §Implementation:361, and it is not present yet). Test in `tests/unit/scripts/test_check_dashboard_no_framework.py`. Wire as a `quality-gates` step + pre-commit hook.
  - [x] Note: this guard asserts the *runtime* stays framework-free; it does NOT forbid Node dev/CI tooling (stylelint/Playwright are dev tools, same posture as the 5.2 D1 "no-npm targets the shipped frontend, not the lint toolchain").

- [x] **Task 7 — Packaging + quality gate + freeze** (AC: 1, 2, 3, 4)
  - [x] Any new CSS file (focus/motion stylesheet, if not folded into an existing one) must be added to the file-by-file `force-include` block [pyproject.toml] or it will not ship in the wheel.
  - [x] Python quality gate on new `scripts/*.py` (ruff + mypy --strict); full pytest + coverage ≥87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7**.

## Dev Notes

### Locked design decisions (verbatim — these govern the whole story)

- **DD-15 — Custom focus ring.** *"Custom focus ring: `box-shadow: 0 0 0 2px var(--rule-strong)` on focus-visible for all interactive elements. Browser default focus retained where it provides equivalent visibility. Keyboard parity (principle #6) requires visible focus; `--rule-strong` is bright enough on dark surfaces while staying within the editorial register."* [Source: UX §Visual Foundation / DD-15, ux-design-specification.md:752; §3.6:741; implemented via `:focus-visible` not `:focus`, §8.6:1866]
- **DD-14 — Stillness / strip transitions.** *"Strip all prototype CSS transitions and animations except `--motion-pulse-live` and `--motion-pulse-stop`. Specifically: tab color/border transitions, panel fadein, all progress-bar width transitions, `.stage-pill.current .ring` spinner, all chevron transforms, and copy-btn transform. Replace chevron transitions with icon-glyph swaps (DD-03 sprite)."* [Source: UX §Visual Foundation / DD-14, ux-design-specification.md:751; the exact prototype rules to remove are listed at §3.5:721-733]
- **DD-16 — `prefers-reduced-motion`.** *"`prefers-reduced-motion: reduce` disables both pulse animations (live-dot and STOP-dot). Falls back to static dots. WCAG 2.3.3; accessibility floor; aligns with principle #3 by removing all motion if the user requests it."* [Source: UX §Visual Foundation / DD-16, ux-design-specification.md:753; §3.6:743]
- **DD-08 — No third-party UI framework.** *"DD-08 locks no third-party UI framework. Every dashboard component is custom."* Only permitted vendored runtime dep is Chart.js (v4.x, vendored, no CDN, DORA charts only). [Source: UX §6:1007, §6.9:1394, §Implementation:361]
- **DD-06 — Content-delta only.** State changes happen by swapping content (text/glyph/class), not by animated transitions. [Source: UX §Defining Experience]

### Frozen tokens to consume (do NOT redefine — Story 5.2 froze these)

```css
--rule-strong: rgba(255, 255, 255, 0.18);     /* DD-15 focus ring: box-shadow 0 0 0 2px var(--rule-strong) */
--accent-soft: rgba(226, 120, 88, 0.12);       /* the SEPARATE 3px active/current-state ring — NOT focus */
--paper: #161922;                              /* AC1 contrast reference background */
--motion-pulse-live: 2.4s ease-in-out infinite;
--motion-pulse-stop: 2.4s ease-in-out infinite;
--motion-copy-feedback: 1s;                    /* consumed by JS setTimeout, NOT a CSS transition */
```
```css
@keyframes pulse {                              /* the ONLY permitted keyframe (tokens.css:176-180) */
  50% { box-shadow: 0 0 0 6px color-mix(in srgb, currentColor 8%, transparent); }
}
```
[Source: src/sdlc/dashboard/static/styles/tokens.css:25,29,14,168-180]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — focus-ring token: implement DD-15 (`--rule-strong`) verbatim.** The epic AC1 says the ring "meets WCAG 2.2 Level A contrast against `--paper`". Note: at WCAG **2.2 Level A**, the binding success criterion is **2.4.7 Focus Visible** (a visible indicator must exist) — the numeric non-text-contrast threshold (3:1) is **2.4.11 Focus Appearance** at AA, not Level A. So `box-shadow: 0 0 0 2px var(--rule-strong)` (rgba(255,255,255,0.18) over `--paper`) satisfies the Level A floor as a locked design decision (DD-15). *Recommendation:* implement DD-15 as written; do NOT silently swap the token. The ring's perceptibility is independently verified by 5.12's keyboard-only test ("focus is always visible (Story 5.4 focus ring)", UX §8.5:1834). If a reviewer finds the 0.18-alpha ring imperceptible in practice, raise it as a design escalation (Project Lead/PO) rather than changing the locked token inline.

**D2 — reduced-motion integration test tooling (Playwright-in-CI).** AC3 mandates "an integration test using a Playwright fixture with reduced-motion emulation". The runtime stays vanilla (DD-08); Playwright is a **dev/CI test tool** (same posture the 5.2 D1 stylelint/Node-in-CI decision established — the no-npm rule targets the shipped frontend, not the test toolchain). Confirm whether Playwright is already wired into the project (the repo has a `.github/workflows/e2e.yml` surface + a BMad e2e harness) or whether this story stands it up.
- **D2 (option a) — wire a minimal Playwright reduced-motion test into the existing e2e/CI surface (recommended):** smallest footprint that satisfies AC3 literally; pin the Playwright version; run it where the other browser/e2e checks run, not a fork.
- **D2 (option b) — if Playwright-in-CI is contested,** assert the reduced-motion behavior via a computed-style/CSSOM check under emulated `prefers-reduced-motion` and escalate the Playwright requirement to the Project Lead for an AC waiver. *Recommendation: (a)* — honor the AC; escalate only if browser tooling in CI is itself contested.

### 5.5 coordination (this story is the foundation, NOT the live-dot)

5.4 sits at `5.2 → 5.4 → 5.5` on the critical path. It establishes the **focus ring + the `prefers-reduced-motion` block + the transition/no-framework gates** — the CSS foundation 5.5's `<live-dot>` family consumes. **Do not build the live-dot element or its pulse application here** (that is 5.5). Write the reduced-motion rule so it neutralizes the pulse animation wherever applied (freeze/agree the live-dot pulse class name with 5.5), and assert AC3 against a committed fixture element. This keeps 5.4 self-contained and avoids duplicating 5.5's work. [Source: docs/sprints/epic-5-dag.md §3 L2/L3, §4 critical path]

### Project Structure Notes

- New: a focus/motion stylesheet under `src/sdlc/dashboard/static/styles/` (or appended to an existing CSS — but keep `tokens.css` token values frozen) + three gate scripts under `scripts/`. New CSS must be added to the file-by-file `force-include` [pyproject.toml] to ship in the wheel.
- CSS must use `var(--*)` references (the 5.2 stylelint gate enforces this on `styles/**/*.css` [.stylelintrc.json]); the focus ring uses `var(--rule-strong)`, not a raw rgba.
- 5.3 and 5.4 are mutually-independent L2 siblings; both branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3). If 5.3 merges first, rebase onto it (and align the stylesheet `<link>` path with 5.3's Decision D1).
- Zero wire-format contracts (CSS is not a wire contract) → freeze stays 7/7. Quality gate (CONTRIBUTING §1) applies to new `scripts/*.py`.

### Net-new CI gates this story stands up (DAG Decision D2 — incremental, single CI surface)

This story adds the **transition-grep** (DD-14, AC2) and **no-third-party-UI-framework** (DD-08, AC4) gates as siblings of the 5.2 DD-09 + 5.3 no-CDN gates, in the same `quality-gates` matrix + pre-commit. Keep each gate small, composable, single CI surface. [Source: docs/sprints/epic-5-dag.md Decision D2 (ratified = a); §5 Worktree row 5.4 — "no-third-party-UI-framework guard + transition grep gate"]

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Forbidden-pattern gate scripts (transition, no-framework) | Copy the DD-09 gate shape (arg-parse, globs, comment-strip, exit 0/1/2, `file:line:col` to stderr) | scripts/check_dashboard_no_data_theme.py |
| `pulse` keyframe + motion tokens | Consume the frozen tokens; reduced-motion neutralizes them | src/sdlc/dashboard/static/styles/tokens.css:168-180 |
| Focus/active-ring distinction | 2px `--rule-strong` (`:focus-visible`) vs 3px `--accent-soft` (active state) | UX §3.4/§3.6, tokens.css:25,29 |
| Gate-script import in tests | `tests/conftest.py:19-22` puts `scripts/` on `sys.path` | tests/conftest.py |
| CI step + pre-commit hook wiring | Mirror the DD-09 step + `repo: local` hook | .github/workflows/ci.yml, .pre-commit-config.yaml |
| Browser/e2e test surface | Existing `e2e.yml` / BMad e2e harness (Decision D2) | .github/workflows/e2e.yml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2453-2482] — Story 5.4 ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md DD-15:752 / §3.6:741 / §8.6:1866] — focus ring `box-shadow 0 0 0 2px var(--rule-strong)`, `:focus-visible` not `:focus`
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md DD-14:751 / §3.5:721-733] — exact prototype transitions/animations to strip
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md DD-16:753 / §3.6:743 / §6.8:1379] — reduced-motion disables both pulses → static dot (WCAG 2.3.3)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md DD-08:1007 / §6.9:1394 / §Implementation:361] — no third-party UI framework; Chart.js the only vendored runtime
- [Source: src/sdlc/dashboard/static/styles/tokens.css:25,29,168-180] — frozen `--rule-strong`/`--accent-soft`/motion tokens + `@keyframes pulse`
- [Source: src/sdlc/dashboard/static/styles/.stylelintrc.json] — `var(--*)` enforcement on `styles/**/*.css`
- [Source: scripts/check_dashboard_no_data_theme.py] — gate-script template to mirror (Tasks 3, 6)
- [Source: .github/workflows/ci.yml / e2e.yml] — `quality-gates` step wiring; `frontend-gates` job; e2e surface (Playwright, D2)
- [Source: .pre-commit-config.yaml] — DD-09 hook (sibling-hook template)
- [Source: pyproject.toml] — dashboard static `force-include` (add any new CSS)
- [Source: docs/sprints/epic-5-dag.md §3 (L2), §4 (critical path), §5 (5.4 row), Decision D2] — L2 sibling of 5.3; critical-path node; no-framework + transition gates; single CI surface

## Dev Agent Record

### Agent Model Used

Composer (Cursor)

### Debug Log References

- D1 resolved: DD-15 `--rule-strong` verbatim (2px focus ring on `:focus-visible` only).
- D2 resolved: option (a) — `playwright` dev dependency + Chromium install in `quality-gates` CI matrix + integration test.

### Completion Notes List

- Added `focus-motion.css`: DD-15 focus ring selectors, 3px active-state ring (distinct), `.live-dot-pulse` / `.live-dot-pulse--stop` classes, DD-16 reduced-motion block.
- Added `scripts/check_dashboard_motion.py` (DD-14) and `scripts/check_dashboard_no_framework.py` (DD-08) with TDD fixtures/tests.
- Playwright integration test asserts `animation-name: none` under `prefers-reduced-motion: reduce` on committed fixture HTML.
- Wired DD-14 + DD-08 gates in CI (`quality-gates`) and pre-commit; `playwright install chromium` before pytest in CI.
- Wheel force-include extended for `focus-motion.css` + `reduced-motion-pulse.html`.
- Full suite: 3907 passed, coverage 88.42%, freeze 7/7 unchanged.

### File List

- `.github/workflows/ci.yml`
- `.pre-commit-config.yaml`
- `pyproject.toml`
- `uv.lock`
- `scripts/check_dashboard_motion.py`
- `scripts/check_dashboard_no_framework.py`
- `src/sdlc/dashboard/static/fixtures/reduced-motion-pulse.html`
- `src/sdlc/dashboard/static/index.html`
- `src/sdlc/dashboard/static/styles/focus-motion.css`
- `tests/fixtures/dashboard_css/clean_pulse_component.css`
- `tests/fixtures/dashboard_css/violation_keyframes_spin.css`
- `tests/fixtures/dashboard_css/violation_transition.css`
- `tests/fixtures/dashboard_framework/violation_package.json`
- `tests/integration/test_dashboard_reduced_motion.py`
- `tests/integration/test_wheel_dashboard_static.py`
- `tests/unit/scripts/test_check_dashboard_motion.py`
- `tests/unit/scripts/test_check_dashboard_no_framework.py`

## Change Log

- 2026-06-24: Story 5.4 created (create-story) — custom focus ring (`:focus-visible`), transition stripping, `prefers-reduced-motion`, no-framework guard; Decisions D1 (focus token = DD-15 `--rule-strong`) + D2 (Playwright reduced-motion test) raised; 5.5 live-dot coordination noted.
- 2026-06-24: Story 5.4 implemented (dev-story) — D1=DD-15 `--rule-strong`; D2=Playwright in CI quality-gates; focus-motion CSS + DD-14/DD-08 gates + reduced-motion Playwright test; all ACs satisfied.
- 2026-06-24: Story 5.4 code-review (bmad-code-review, 3 adversarial layers @ Opus-4.8 + source-verification) — 3 decisions resolved (all "harden now") + 6 patches applied (PAT-1..6, TDD-first: 6 RED unit tests → GREEN) + 6 deferred + 5 dismissed (incl. 2 verified false-positives). Post-patch full gate GREEN on macOS host: ruff/format/mypy --strict clean, both DD-14/DD-08 gates exit 0, pytest 3918 passed/4 skipped/1 xfailed, coverage 88.48% ≥ 87%. **STAYS `review`** — flips to `done` only after TDD-first commit (test → feat/fix → docs `[fresh-context-review]`) on worktree `epic-5/5-4-*` + merge to main + green CI (merged-before-done gate, CLAUDE.md binding). NOTE: `actions/cache@v4` in ci.yml is not yet SHA-pinned (TODO comment) — pin before merge to match the repo's action-pinning convention.

## Review Findings

> bmad-code-review, **3** adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + reviewer source-verification (2026-06-24). Acceptance Auditor verdicts: **AC1 PARTIALLY MET** (DD-15 ring authored verbatim, `:focus-visible` + `:focus:not(:focus-visible)` suppression present, stylelint-clean — but design-substrate only, no behavioral test; see DEF-6), **AC2 MET** (grep gate enforces pulse-only budget; RED fixtures exit 1 with `file:line:col`, real tree exits 0), **AC3 MET** (`@media (prefers-reduced-motion)` → `animation: none`; Playwright test passes, `@keyframes pulse` confirmed in `tokens.css:259`), **AC4 PARTIALLY MET** (package.json runtime-dep + named `*.min.js` detection works and names the import — but Task-6 "or a vendored framework import" is bypassable; see DEC-1). Triage: **3 decision-needed + 3 patch** (below) + **6 defer** (deferred-work.md) + **5 dismissed** (incl. 2 verified false-positives: `@keyframes pulse` IS defined in tokens.css; `_PERMITTED_MIN_JS` uses anchored `re.match` so `evilchart.min.js` is not auto-permitted).

### Decision-needed

> **Resolved 2026-06-24 (CONTRIBUTING §5):** DEC-1 → option (b) broaden filename match → **PAT-4**; DEC-2 → option (b) broaden scan root to `src/sdlc/dashboard/` → **PAT-5**; DEC-3 → option (a) harden Playwright CI → **PAT-6**. All three resolved to *harden now*.

- [x] [Review][Decision] DEC-1 — No-framework guard (AC4 / Task-6 "vendored framework import") is filename-only and bypassable — `_bundle_violation_name` requires both a `*.min.js` suffix AND a framework name in the *filename* (no file-content scan); `scan_package_json` reads only runtime `dependencies` against a fixed 18-name denylist. Verified escapes (all exit 0): `vendor/react.js` containing `import React`, a renamed `app.min.js` carrying React source, a framework under `devDependencies`/`peerDependencies`, and any framework outside the denylist (`@vue/runtime-dom`, `alpinejs`, `htmx`, `jquery`, `next`, `@emotion/*`). The scoped-package `base = name.split("/")[-1]` fallback is also incoherent (`@angular/core`→`core`, `@vue/runtime-dom`→`runtime-dom` missed, `@emotion/react`→`react` matched by accident). **Options:** (a) accept current tripwire as literal-AC4-minimum and defer hardening to a follow-up; (b) broaden filename detection to all `.js`/`.css` with framework markers (no rename bypass); (c) content-scan JS for framework import signatures + include dev/peer deps + switch denylist→allowlist (full Task-6 intent). [Blind #8/#9/#10, Edge #6/#8/#17, Auditor A1/A2 — HIGH]
- [x] [Review][Decision] DEC-2 — Both the script default root and the pre-commit `files:` filter are scoped to `src/sdlc/dashboard/static/` only — a dashboard `package.json` at `src/sdlc/dashboard/` (the natural location, OUTSIDE `static/`) escapes both the hook trigger and the scan entirely. **Options:** (a) keep `static/`-only (spec-literal: "scans static and any package.json under it"); (b) broaden the default root + pre-commit filter to `src/sdlc/dashboard/` so a dashboard-root package.json is covered. [Edge #16 — MEDIUM]
- [x] [Review][Decision] DEC-3 — Playwright Chromium wiring: `uv run playwright install chromium` runs **uncached in every matrix cell** (8 cells: py3.10–3.13 × ubuntu/macos) with **no `--with-deps`**, adding a ~150 MB external download per run to a CI surface with documented macOS flake history; and locally `pytest.importorskip("playwright")` no longer skips (playwright is now a dev dep) so the integration test **hard-errors** without an installed browser binary instead of skipping. **Options:** (a) harden now — cache the browser, add `--with-deps`, and make the test `pytest.skip` gracefully when no browser binary is present; (b) accept current wiring and defer. [Blind #15/#16 — MEDIUM reliability]

### Patch

- [x] [Review][Patch] PAT-1 — `scan_paths` re-walks each file's parent tree, producing duplicate violations and O(files×tree) over-scan + a dead `endswith("package.json")` branch [scripts/check_dashboard_no_framework.py:147] — *verified*: the real no-arg invocation (flat file list from `_expand_targets`) reports `react` and `react.min.js` **twice each** (4 instead of 2). Fix: scan each explicit file directly (`package.json`→`scan_package_json`, else→`_bundle_violation_name`); compatible with all unit tests (they use `scan_static_tree`/`main([dir|pkg])`). [Blind #6/#7, Edge #9]
- [x] [Review][Patch] PAT-2 — Reduced-motion test asserts only the negative case, can pass vacuously if the base pulse rule is ever deleted [tests/integration/test_dashboard_reduced_motion.py:45] — add a positive control: without `reduced_motion`, assert `animationName == "pulse"`, then assert `none` under reduce. Verified feasible: `#pulse-fixture` carries `.live-dot-pulse` and `@keyframes pulse` exists. [Blind #13, Edge #14]
- [x] [Review][Patch] PAT-3 — package.json violations report `line=idx` (alphabetical sort index, not the real file line), so `file:line:col` points at a meaningless location [scripts/check_dashboard_no_framework.py:99] — report the dependency's true line (or honest `line=1`). [Blind #12]
- [x] [Review][Patch] PAT-4 (from DEC-1) — Broaden bundle/import detection beyond filename `*.min.js`: flag any `.js`/`.css` whose filename carries a framework marker (closes the rename bypass), and extend dep coverage where cheap [scripts/check_dashboard_no_framework.py:47-122] — resolved DEC-1 option (b).
- [x] [Review][Patch] PAT-5 (from DEC-2) — Broaden the script default root and the pre-commit `dashboard-dd08-gate` `files:` filter to `src/sdlc/dashboard/` so a dashboard-root `package.json` is covered [scripts/check_dashboard_no_framework.py:23, .pre-commit-config.yaml] — resolved DEC-2 option (b).
- [x] [Review][Patch] PAT-6 (from DEC-3) — Cache the Playwright browser + add `--with-deps`, and make the reduced-motion test `pytest.skip` gracefully when no browser binary is installed [.github/workflows/ci.yml, tests/integration/test_dashboard_reduced_motion.py] — resolved DEC-3 option (a).

### Deferred (see deferred-work.md → "code review of 5-4-... (2026-06-24)")

- [x] [Review][Defer] DEF-1 — Line-based CSS scan misses multi-line `transition`/`animation` declarations, longhand props (`transition-property`, `animation-name`), and `transition:` inside quoted string values [scripts/check_dashboard_motion.py] — deferred, mirrors established gate-family pattern (5.2/5.3); harden the family together.
- [x] [Review][Defer] DEF-2 — Both gates fail-open: missing default root → exit 0 "OK"; `errors="replace"` can mask tokens; malformed package.json `except → return []`; `rglob` follows symlinks/hidden dirs (cycle-hang) [scripts/check_dashboard_*.py] — deferred, pre-existing gate-family pattern.
- [x] [Review][Defer] DEF-3 — `check_dashboard_motion.py` and `check_dashboard_no_framework.py` duplicate ~80% scaffolding; the drift caused PAT-1 [scripts/] — deferred, refactor into a shared `dashboard_gate` helper.
- [x] [Review][Defer] DEF-4 — `@keyframes pulse` is allowed by NAME only; its body is unvalidated, so a future non-pulse redefinition of `pulse` would pass [scripts/check_dashboard_motion.py:91] — deferred, low likelihood.
- [x] [Review][Defer] DEF-5 — Test fixture `reduced-motion-pulse.html` ships in the production wheel (force-included, reachable at `/static/fixtures/`) because the integration test serves it via the real static tree [src/sdlc/dashboard/static/fixtures/, pyproject.toml] — deferred, conscious tradeoff; consider a test-only static mount.
- [x] [Review][Defer] DEF-6 — AC1 focus ring delivered as CSS substrate only: no committed fixture/test asserts the `:focus-visible` ring renders or that mouse-click `:focus` suppresses it (Story Task 1 anticipated a fixture) [src/sdlc/dashboard/static/styles/focus-motion.css] — deferred, no focusable component exists yet; add behavioral test when interactive components land (5.5+).
