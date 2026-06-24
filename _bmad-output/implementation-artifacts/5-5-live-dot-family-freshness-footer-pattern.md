# Story 5.5: Live Dot Family + Freshness Footer Pattern (Cross-Cutting)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L3 (5A) AND the next node on the critical-path spine (5.2 → 5.4 → **5.5** → 5.11 → 5.19 → 5.20 → 5.22). L3 = {5.5, 5.9, 5.10}, max 3 parallel worktrees, depends on 5.2 (frozen tokens) + 5.3 (sprite) + 5.4 (focus/motion foundation) — ALL done+merged. Mutually independent of L3 siblings 5.9 / 5.10 (no edge between them). Worktree: epic-5/5-5-live-dot-freshness-footer. Branch from main, linear merge, rebase between L3 merges (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). This is the SINGLE most load-bearing component node (fans out to 5.6/5.7/5.8/5.11/5.12/5.19/5.20) and OWNS the color-only-signaling contract + the frontend file-layout convention (DAG §5). -->

## Story

As a frontend engineer implementing two cross-cutting patterns used across multiple components,
I want a `<live-dot>` web component (or class-based equivalent) supporting Default/Warn/Disconnected variants, paired with an adjacent text label (no color-only signaling), and a `<freshness-footer>` pattern showing `as of HH:MM:SS` left + live-dot label right,
So that subsequent components (Masthead, Resume Card, KPI Strip, STOP Banner) reuse identical implementations (UX-DR14, UX-DR25, §7.4, §7.5).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.5, lines 2484–2508).

**AC1 — `<live-dot>` variants**
- **Given** the `<live-dot>` component **When** it renders with `variant="default" | "warn" | "disconnected"` **Then** the dot is a 7×7 px circle with a `box-shadow` glow at 25% alpha of the dot color
- **And** for `default`, color is `--green` and pulse is `--motion-pulse-live`
- **And** for `warn`, color is `--amber` and pulse is `--motion-pulse-stop`
- **And** for `disconnected`, color is `--red` and pulse is `--motion-pulse-stop`

**AC2 — Color-only-signaling contract (§7.4)**
- **Given** the consistency contract (§7.4) **When** any component renders a live dot **Then** an adjacent text label is always present (e.g., "LIVE", "WARN", "DISCONNECTED")
- **And** color-only indication is forbidden — a static analysis test grep for `<live-dot>` without a sibling text label fails

**AC3 — `<freshness-footer>` pattern (§7.5)**
- **Given** the `<freshness-footer>` pattern **When** rendered on a surface that displays state from `/state.json` **Then** the left side shows `as of HH:MM:SS` (local time of last successful poll)
- **And** the right side shows a `<live-dot>` + label
- **And** stale state (poll older than 30 s) renders with `--ink-mute` instead of `--ink`

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the **color-only-signaling CI gate (AC2)** is a deterministic public contract → tests-first (RED: a fixture with a `<live-dot>` lacking an adjacent text label exits 1 with `file:line:col`; GREEN: every dot paired with a sibling label exits 0). The `<live-dot>` / `<freshness-footer>` rendering is interactive JS/CSS substrate → `test-along` is acceptable, but the **reduced-motion behavior (AC1 pulse under DD-16)** and the **stale→`--ink-mute` swap (AC3)** are testable behaviors → assert them via the existing Playwright surface (Story 5.4 D2) + committed fixtures. Resolve Decisions D1/D2/D3 BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (resting glow vs `@keyframes pulse`), D2 (component model + file-layout convention), D3 (color-only gate scope) BEFORE coding** (AC: 1, 2)
  - [x] Record the picks in the PR Change Log (CONTRIBUTING §5). These are foundational — 5.6/5.7/5.8/5.11 and the L3 siblings 5.9/5.10 consume the convention D2 freezes.

- [x] **Task 1 — `<live-dot>` component (3 variants)** (AC: 1)
  - [x] Render a 7×7 px circle (`--space-3` (8 px) is the center-to-center distance to its label per §7.4 — the dot itself is 7×7). Apply the **resting glow as a static `box-shadow` at 25% alpha of the dot color** AND the **animated pulse via the frozen `.live-dot-pulse` / `.live-dot-pulse--stop` classes** (5.4 / focus-motion.css:41-47). See **Decision D1** — do NOT redefine `@keyframes pulse` (tokens.css:259 is byte-frozen and the DD-14 gate allows only the `pulse` keyframe).
  - [x] Variant → color + pulse mapping: `default` → `--green` + `.live-dot-pulse` (`--motion-pulse-live`); `warn` → `--amber` + `.live-dot-pulse--stop` (`--motion-pulse-stop`); `disconnected` → `--red` + `.live-dot-pulse--stop` (`--motion-pulse-stop`). Set the dot element's CSS `color` to the variant color so the pulse keyframe's `currentColor` resolves correctly (the keyframe is `box-shadow: 0 0 0 6px color-mix(in srgb, currentColor 8%, transparent)`).
  - [x] Variant is data-driven (attribute/prop), not three separate elements — content-delta swap on poll (DD-06: change the variant attribute/class, no transition).

- [x] **Task 2 — Adjacent text label is structural, not optional** (AC: 2)
  - [x] The `<live-dot>` API MUST require/emit an adjacent text label sibling ("LIVE" / "WARN" / "DISCONNECTED"). Make color-only rendering structurally hard: e.g. the component renders `dot + label` together, or the wrapper element carries both. The label uses `--type-label-mono` / `--type-label-mono-sm` uppercase (per the editorial register).

- [x] **Task 3 — Color-only-signaling CI gate** (AC: 2) — *tests-first*
  - [x] Add `scripts/check_dashboard_color_only.py` **mirroring the DD-09/DD-14 gate shape** [scripts/check_dashboard_no_data_theme.py, scripts/check_dashboard_motion.py]: same anchor/`_REPO_ROOT`, default root `src/sdlc/dashboard/static`, comment-strip, `errors="replace"`, exit 0 (clean) / 1 (violations, `file:line:col` to stderr) / 2 (explicit path not found). Rule: a `<live-dot>` element (or the frozen live-dot class) in any committed HTML/fixture without an adjacent text-label sibling is a violation. Tag the contract (§7.4 color-only) — see **Decision D3** on whether to gate HTML fixtures only or also the JS render template.
  - [x] **RED:** a fixture HTML with `<live-dot variant="warn"></live-dot>` and no sibling label exits 1 with `file:line:col`; **GREEN:** `<live-dot variant="warn"></live-dot><span class="...">WARN</span>` (or the paired-render output) exits 0. Test in `tests/unit/scripts/test_check_dashboard_color_only.py`; fixtures under `tests/fixtures/dashboard_color_only/`.
  - [x] Wire as a sibling **step** in the `quality-gates` matrix (after the DD-08 step, ci.yml:66-67) + a `repo: local` pre-commit hook mirroring `dashboard-dd14-gate` [.pre-commit-config.yaml]. A `quality-gates` step, NOT a new top-level job (no `ci-gate.needs` edit). 5.12 (the a11y convergence gate) consumes/extends this — keep it composable.

- [x] **Task 4 — `<freshness-footer>` pattern** (AC: 3)
  - [x] Bottom row, `--type-mono-data` `--ink-mute` (§7.5). Left: `as of HH:MM:SS` (local time of last successful poll — format the JS `Date` to `HH:MM:SS` local). Right: `<live-dot>` + label (Task 1/2).
  - [x] **Stale rule:** when the last successful poll is older than 30 s, the footer text renders `--ink-mute` instead of `--ink`. (Until the masthead/poll loop lands in 5.6, drive "last poll" from a fixture/injected timestamp so the stale path is testable now.) §7.5 consistency contract: a surface showing `/state.json` state must carry a freshness footer OR inherit the masthead's — author the reusable pattern; do NOT build the masthead (that is 5.6, edge 5.5→5.6).

- [x] **Task 5 — Reduced-motion + component review fixture** (AC: 1, 2) — *tests-first where feasible*
  - [x] Verify DD-16: under `@media (prefers-reduced-motion: reduce)` the live-dot pulse is disabled and the dot renders **static** (color + adjacent label still carry the signal). This is already wired in focus-motion.css:49-55 against `.live-dot-pulse`/`.live-dot-pulse--stop` — 5.5 just applies those exact classes. Re-verify on the REAL live-dot via the Playwright reduced-motion surface (Story 5.4 D2; `emulateMedia({ reducedMotion: 'reduce' })` → computed `animation-name: none`), upgrading the 5.4 fixture-only assertion to the real component. This also closes **DEF-6** carryover only for the live-dot if it is focusable (it is a status indicator, not interactive → no focus ring; DEF-6's focusable-component close lands in 5.10's tree expanders).
  - [x] Commit a Storybook-style review fixture page rendering all three variants + a freshness-footer (fresh + stale) for a11y/visual review. Place it per the **D2-frozen layout convention**.

- [x] **Task 6 — Packaging + quality gate + freeze** (AC: 1, 2, 3)
  - [x] Add every new component file (live-dot JS+CSS, freshness-footer JS+CSS, fixture HTML) to the file-by-file `force-include` block [pyproject.toml] or it will not ship in the wheel (5.3/5.4 precedent; note DEF-5 — review fixtures currently ship in the wheel, a conscious tradeoff).
  - [x] If D2 places component CSS OUTSIDE `static/styles/`, **broaden the 5.2 stylelint glob** `src/sdlc/dashboard/static/styles/**/*.css` → `src/sdlc/dashboard/static/**/*.css` [.github/workflows/ci.yml:123] so component CSS stays token-enforced (otherwise component CSS escapes the var(--*) gate). Link any new top-level CSS from `index.html` (or load per-component).
  - [x] Python quality gate on new `scripts/*.py` (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7**.

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§7.4 Live Dot Family.** *"Shared shape. 7 × 7 px circle, `--space-3` (8 px) center-to-center distance from its label, with a `box-shadow` glow at 25 % alpha of the dot color. Animation: `--motion-pulse-live` when green, `--motion-pulse-stop` when amber/red. Disabled under DD-16. … A live dot is **always** paired with a text label adjacent … Dot-only indication is forbidden (color-only signaling rule, §3.1)."* [Source: ux-design-specification.md §7.4, lines 1488–1502]
- **§7.5 Freshness Footer Pattern.** *"A bottom row, `--type-mono-data` `--ink-mute`, two parts: Left: `as of HH:MM:SS` … Right: live dot + 'live' label … When a surface displays state from `/state.json`, it must either (a) carry a freshness footer, or (b) inherit freshness from the masthead's footer."* [Source: ux-design-specification.md §7.5, lines 1504–1517]
- **DD-16 — `prefers-reduced-motion`.** Disables both pulse animations → static dots (WCAG 2.3.3). Already implemented in `focus-motion.css:49-55` against `.live-dot-pulse` / `.live-dot-pulse--stop`. [Source: ux-design-specification.md DD-16:753; src/sdlc/dashboard/static/styles/focus-motion.css:49-55]
- **DD-08 — No third-party UI framework.** Every component is custom/vanilla. A **native Custom Element** (`customElements.define('live-dot', …)`) is vanilla JS and does NOT trip the DD-08 gate (it scans for React/Vue/Svelte/etc. deps + vendor bundles, not Web Components). [Source: scripts/check_dashboard_no_framework.py; ux-design-specification.md DD-08]
- **DD-06 — Content-delta only.** Variant changes by swapping attribute/class, never an animated transition (the DD-14 gate forbids `transition:`). [Source: ux-design-specification.md §Defining Experience; scripts/check_dashboard_motion.py]

### Frozen foundation to consume (do NOT redefine — 5.2/5.3/5.4 froze these)

```css
/* tokens.css — colors + motion the dot consumes */
--green: #4ade80;  --amber: #fbbf24;  --red: #f87171;
--ink: #eceef3;    --ink-mute: #8b92a2;          /* freshness footer fresh vs stale */
--space-3: 8px;                                   /* dot→label center distance */
--motion-pulse-live: 2.4s ease-in-out infinite;   /* default (green) */
--motion-pulse-stop: 2.4s ease-in-out infinite;   /* warn/disconnected */
--type-mono-data-size: 11px; /* + -line-height/-weight/-letter-spacing */  /* freshness footer text */
--type-label-mono-size: 11px; /* + sm variant 10px */                       /* the adjacent label */
```
```css
/* focus-motion.css:40-55 — APPLY these exact classes; do NOT re-author the pulse */
.live-dot-pulse        { animation: pulse var(--motion-pulse-live); }
.live-dot-pulse--stop  { animation: pulse var(--motion-pulse-stop); }
@media (prefers-reduced-motion: reduce) {
  .live-dot-pulse, .live-dot-pulse--stop { animation: none; }   /* DD-16 — already wired */
}
```
```css
/* tokens.css:259 — the ONLY permitted keyframe; BYTE-FROZEN (DD-14 gate allows only `pulse`) */
@keyframes pulse { 50% { box-shadow: 0 0 0 6px color-mix(in srgb, currentColor 8%, transparent); } }
```
[Source: src/sdlc/dashboard/static/styles/tokens.css:95-256, focus-motion.css:40-55]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Resting glow (25% alpha) vs the frozen `@keyframes pulse` (8% color-mix).** AC1 mandates a `box-shadow` glow at **25% alpha of the dot color**, but the byte-frozen `@keyframes pulse` (tokens.css:259) animates a **6px spread at 8% `currentColor`**. These are two different shadows: (1) a **resting/static** glow that is always visible, and (2) the **animated** pulse that expands the spread. *Recommendation (a):* render the 25%-alpha resting glow as a **static `box-shadow` on the dot element itself** (using a `color-mix(in srgb, currentColor 25%, transparent)` or the variant `--*-soft` tokens which are 12% — NOT 25%, so prefer `color-mix` to hit 25% exactly), and keep the animated pulse via the frozen `.live-dot-pulse*` classes UNCHANGED. Do NOT edit `@keyframes pulse` — the DD-14 gate (`check_dashboard_motion.py:91-101`) fails any `@keyframes` other than `pulse` and any redefinition risks the byte-freeze. *Alternative (b):* if a reviewer reads "25% alpha glow" as the pulse peak, escalate to align the keyframe (Project Lead) rather than silently editing the frozen keyframe. The `--*-soft` tokens are 12% (`--green-soft` etc.) and do not match 25% — call this out so the dev does not reach for the wrong token.

**D2 — Component model + frozen file-layout convention (DAG §5 — this story owns it).** Epic AC says "`<live-dot>` web component (or class-based equivalent)". *Recommendation (a) — native Custom Element + a frozen `static/components/<name>/` layout:* define `<live-dot>` and `<freshness-footer>` via `customElements.define` (vanilla, DD-08-clean, matches the literal `<live-dot>` tag in the epic), with each component at `src/sdlc/dashboard/static/components/<name>/<name>.{js,css}` and a per-component review page `<name>.fixture.html` (or a shared `static/test-fixtures/` dir). FREEZE this convention — 5.9 (epic names `dashboard/static/test-fixtures/signoff-states.html`) and 5.10 (epic names `dashboard/static/components/pills/`) must align to it; reconcile the `fixtures/` (5.4 actual) vs `test-fixtures/` (5.9 epic) vs `components/` (5.10 epic) drift now. *Alternative (b)* class-based render helpers if Custom Elements are contested — but the epic's literal tag favors (a). **Whichever is chosen, broaden the stylelint glob** (Task 6) so component CSS outside `styles/` stays token-enforced.

**D3 — Color-only gate scope.** The static-analysis test (AC2) must grep committed HTML/fixtures for a `<live-dot>` without an adjacent label. *Recommendation (a):* gate the committed HTML + fixture surface (where dots are authored declaratively) — the deterministic, reviewable seam; mirror DD-09's `(css|js|mjs|html)` file scope where dots appear. *Alternative (b):* also static-scan the JS render template — defer if the render emits dot+label as one structural unit (Task 2 makes color-only structurally hard, reducing the gate to a tripwire). Keep the gate small/composable; 5.12 extends it into the broader forbidden-patterns + axe-core convergence gate.

### 5.5 is the foundation — what it OWNS vs what it must NOT build

- **Owns:** the reusable `<live-dot>` + `<freshness-footer>` patterns, the **color-only-signaling contract + CI gate**, and the **frontend file-layout convention** (DAG §5). It is the highest-fanout node — 5.6 (masthead live indicator), 5.7 (KPI stale), 5.8 (resume freshness), 5.11 (activity), 5.12 (a11y gate), 5.19 (STOP severity dot), 5.20 (disconnected) all reuse these. Build them **once, correctly, reusable**.
- **Must NOT build (anti-scope-creep — these are downstream edges):** the Masthead/poll loop (5.6, edge 5.5→5.6), the disconnection page-wide treatment (5.20, edge 5.5→5.20), the STOP banner (5.19). Author the patterns so those stories drop them in; provide injected/fixture timestamps + variants so the stale + disconnected paths are testable now without the poll loop. [Source: docs/sprints/epic-5-dag.md §2 (5.5 fan-out edges), §3 (L3), §4 (critical path)]

### Project Structure Notes

- New component files under `src/sdlc/dashboard/static/components/<name>/` (per D2) + one gate script `scripts/check_dashboard_color_only.py`. New CSS/JS/HTML must be added to the file-by-file `force-include` [pyproject.toml] to ship in the wheel.
- Component CSS must use `var(--*)` references — the 5.2 stylelint gate FORBIDS raw values for color/background-color/font-size/font-family/padding/margin/gap/letter-spacing/line-height/border-radius/border-width [.stylelintrc.json:5-54]. Map every value to a token (e.g. label letter-spacing → `var(--type-label-mono-letter-spacing)`; never a raw `0.12em`). **The stylelint glob is `styles/**` only** — broaden it if component CSS lands elsewhere (Task 6 / D2).
- L3 = {5.5, 5.9, 5.10} are mutually-independent siblings; all branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3). 5.5 should merge first if feasible (it freezes the layout convention 5.9/5.10 reference), else publish the D2 convention in review so siblings can align.
- Zero wire-format contracts (CSS/JS/HTML are not wire contracts) → freeze stays 7/7. Quality gate (CONTRIBUTING §1) applies to the new `scripts/*.py`.

### Net-new CI gate this story stands up (DAG Decision D2 — incremental, single CI surface)

This story adds the **color-only-signaling** gate as a sibling of the 5.2 DD-09, 5.3 DD-10, 5.4 DD-14/DD-08 gates, in the same `quality-gates` matrix step list + pre-commit. Keep it small, composable, single CI surface. [Source: docs/sprints/epic-5-dag.md Decision D2 (ratified = a); §5 worktree row 5.5 — "owns the color-only-signaling contract"]

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Live-dot pulse animation + reduced-motion | Apply `.live-dot-pulse` / `.live-dot-pulse--stop`; DD-16 already neutralizes them | src/sdlc/dashboard/static/styles/focus-motion.css:40-55 |
| `@keyframes pulse` + motion/color tokens | Consume frozen tokens; do NOT redefine the keyframe | src/sdlc/dashboard/static/styles/tokens.css:95-263 |
| Color-only / motion gate scripts | Copy the DD-09/DD-14 gate shape (arg-parse, globs, comment-strip, exit 0/1/2, `file:line:col` to stderr) | scripts/check_dashboard_no_data_theme.py, scripts/check_dashboard_motion.py |
| Gate-script import in tests | `tests/conftest.py` puts `scripts/` on `sys.path` | tests/conftest.py |
| CI step + pre-commit hook wiring | Mirror the DD-14 step (ci.yml:63-64) + `dashboard-dd14-gate` hook | .github/workflows/ci.yml:57-67, .pre-commit-config.yaml:123-128 |
| Reduced-motion Playwright assertion | Extend the 5.4 reduced-motion test onto the real `<live-dot>` | tests/integration/test_dashboard_reduced_motion.py |
| Wheel force-include for new static files | Add each new file to the force-include block | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2484-2508] — Story 5.5 ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.4:1488-1502] — live dot shape, variants, color-only contract
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.5:1504-1517] — freshness footer shape + stale rule + inherit-from-masthead
- [Source: src/sdlc/dashboard/static/styles/tokens.css:95-263] — frozen colors/motion/type tokens + `@keyframes pulse`
- [Source: src/sdlc/dashboard/static/styles/focus-motion.css:40-55] — `.live-dot-pulse*` classes + DD-16 reduced-motion (already wired)
- [Source: src/sdlc/dashboard/static/styles/.stylelintrc.json:5-54] — var(--*) enforcement (raw-value disallow-list)
- [Source: scripts/check_dashboard_no_data_theme.py / check_dashboard_motion.py] — gate-script template to mirror (Task 3)
- [Source: .github/workflows/ci.yml:57-67,107-125] — `quality-gates` step list; `frontend-gates` stylelint glob to broaden
- [Source: .pre-commit-config.yaml:104-136] — dashboard gate hooks (sibling-hook template)
- [Source: docs/sprints/epic-5-dag.md §2 (5.5 fan-out), §3 (L3), §4 (critical-path spine), §5 (5.5 row + file-layout convention), Decision D2] — load-bearing cross-cutting node; layout convention owner
- [Source: _bmad-output/implementation-artifacts/5-4-custom-focus-ring-prefers-reduced-motion.md] — L2 predecessor; pulse classes + reduced-motion test + DEF-5/DEF-6 carryovers

## Dev Agent Record

### Agent Model Used

Composer (dev-story workflow)

### Debug Log References

- D1/D2/D3 resolved option (a) for all three decisions before coding (see Change Log).
- TDD: gate script RED/GREEN verified via `tests/fixtures/dashboard_color_only/` + unit tests.
- Windows host: full pytest suite blocked by POSIX-only `io_primitives` in conftest; gate script + ruff + mypy + stylelint verified locally; Playwright integration tests require POSIX CI or local Chromium install.

### Completion Notes List

- Implemented native Custom Elements `<live-dot>` and `<freshness-footer>` under `static/components/<name>/` (D2 convention frozen).
- D1: 25% alpha resting glow via static `box-shadow` on `.live-dot__dot`; animated pulse via frozen `.live-dot-pulse*` classes (no keyframe edits).
- D3: color-only gate scans committed HTML in `src/sdlc/dashboard/static` for bare `<live-dot>` without adjacent text label.
- Added `scripts/check_dashboard_color_only.py` wired to CI + pre-commit; stylelint glob broadened to `static/**/*.css`.
- Review fixture at `components/live-dot/live-dot.fixture.html` (all variants + fresh/stale footers); Playwright tests in `test_dashboard_live_dot.py`.

### File List

- scripts/check_dashboard_color_only.py (new)
- src/sdlc/dashboard/static/components/live-dot/live-dot.js (new)
- src/sdlc/dashboard/static/components/live-dot/live-dot.css (new)
- src/sdlc/dashboard/static/components/live-dot/live-dot.fixture.html (new)
- src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js (new)
- src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.css (new)
- tests/fixtures/dashboard_color_only/violation_bare_live_dot.html (new)
- tests/fixtures/dashboard_color_only/clean_live_dot_with_label.html (new)
- tests/unit/scripts/test_check_dashboard_color_only.py (new)
- tests/integration/test_dashboard_live_dot.py (new)
- .github/workflows/ci.yml (modified)
- .pre-commit-config.yaml (modified)
- pyproject.toml (modified)
- _bmad-output/implementation-artifacts/sprint-status.yaml (modified)

## Change Log

- 2026-06-24: Story 5.5 implementation (dev-story) — `<live-dot>` + `<freshness-footer>` components; color-only CI gate; decisions D1/D2/D3 = option (a): static 25% resting glow + frozen pulse classes; native Custom Element + `static/components/<name>/` layout; HTML-only color-only gate scope.
- 2026-06-24: Story 5.5 created (create-story) — `<live-dot>` family (default/warn/disconnected) + `<freshness-footer>` + color-only-signaling CI gate; Decisions D1 (25%-alpha resting glow as static box-shadow vs the byte-frozen 8% `@keyframes pulse` — do not edit the keyframe), D2 (native Custom Element + frozen `static/components/<name>/` layout convention; broaden stylelint glob), D3 (color-only gate scope) raised. L3 (5A) critical-path node; foundation for 5.6/5.7/5.8/5.11/5.12/5.19/5.20; do-not-build masthead/disconnection noted.

### Review Findings

> bmad-code-review (2026-06-24, fresh-context) — **3** adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + orchestrator source-verification. Defects REPRODUCED against the real `scripts/check_dashboard_color_only.py` and a local `@contextmanager` repro. Triage: **1** decision-needed / **2** patch / **2** defer / **7** dismissed.
>
> **Per-AC verdict:** **AC1 = MET** (7×7 dot, 25% static glow via `color-mix`, variant→color+pulse mapping, frozen `.live-dot-pulse*` reused, `@keyframes pulse` untouched, all `var(--*)` resolve — verified). **AC2 = PARTIAL** (gate present + label structural in the JS render, but the gate has reproduced false-negatives + a false-positive → DEC-1, and currently guards **zero** literal HTML → DEF-1). **AC3 = MET** (`as of HH:MM:SS` local, dot+label right, stale→`--ink-mute`/fresh→`--ink` inversion + `>30s` threshold correct). **D1/D2/D3 = MET.** ⚠️ AC1-reduced-motion + AC3-stale behavioral verification is currently **VOID** — the 4 Playwright tests can never execute their assertions (PATCH-1).

**Decision-needed**

- [x] [Review][Decision] DEC-1 (RESOLVED → (a) harden now; applied to working tree as PATCH-3 — `_scan_html` rewritten to a document-level, quote-aware, cross-line scan + 5 regression fixtures + 5 unit tests; all 7 fixtures behave correctly, no-arg gate exits 0) — Color-only gate scanner is brittle (reproduced false-negatives + a false-positive). `_scan_html` is a line-by-line scanner. REPRODUCED against the real module: (1) a bare `<live-dot>` whose opening tag spans multiple lines escapes the gate (`close_idx==-1` → `continue` → reports CLEAN); (2) a bare `<live-dot data-x="a>b">` escapes (`line.find(">")` matches the `>` inside the attribute value → CLEAN); (3) a valid pairing with the label on the NEXT line is FLAGGED (false-positive — blocks normally-formatted markup). Plus the `[:200]` label-window false-positive, and unit tests cover only single-line fixtures (brittle `line==4`, no multi-line / attr-`>` / next-line negative controls). 5.5 OWNS this contract (DAG §5) and is the highest-fanout node (5.6/5.7/5.8/5.11/5.12/5.19/5.20 consume it). Options: **(a) [RECOMMENDED] harden now** — rewrite `_scan_html` to a document-level, quote-aware tag-span scan that finds the true tag end and searches the adjacent sibling across line boundaries; add multi-line + attr-`>` + next-line-label fixtures. **(b) defer** — ship brittle v1 (guards 0 literal HTML today), log debt, fix when 5.6+ first authors literal `<live-dot>` HTML. **(c) minimal** — fix only the next-line-label false-positive now (the one that will actively block downstream formatting), defer the false-negatives. [scripts/check_dashboard_color_only.py:159-181]

**Patch**

- [x] [Review][Patch] PATCH-1 (APPLIED to working tree — 4 sites changed to `with _with_playwright_page(...) as page:`) — Integration tests iterate a `@contextmanager` → `TypeError`; the 4 Playwright tests never run their assertions and red CI. `for page in _with_playwright_page(...)` iterates a `_GeneratorContextManager`, which is not iterable (reproduced: `TypeError: '_GeneratorContextManager' object is not iterable`). CI runs `uv run pytest` with Chromium installed (ci.yml:85,94) → the 4 tests error (red), blocking merged-before-done. Fix: `with _with_playwright_page(...) as page:` (4 sites). Until fixed, the AC1-reduced-motion + AC3-stale behavioral verification is void — recurrence of the documented Windows "asserted-not-measured" Playwright trap. [tests/integration/test_dashboard_live_dot.py:649,659,669,695]
- [x] [Review][Patch] PATCH-2 (APPLIED to working tree — `parseLastPoll` numeric branch re-checks `Number.isNaN(d.getTime())`; `now` guarded with `Number.isFinite`; verified in node) — freshness-footer renders `as of NaN:NaN:NaN` as "fresh" on malformed input. `parseLastPoll`'s numeric branch returns the Date without re-checking `Number.isNaN(date.getTime())` (e.g. `last-poll="1e21"` → Invalid Date → truthy → `isStale` does `now - NaN` = `NaN` → not stale → rendered "fresh" with `NaN:NaN:NaN`); same class for a non-numeric `now` attr → `Number(now)` = `NaN`. Fix: re-check `Number.isNaN(d.getTime())` on the numeric branch; guard `now` with `Number.isFinite(n) ? n : Date.now()`. [src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:461-467,519]

**Deferred**

- [x] [Review][Defer] DEF-1 — Color-only gate scans `.html` only; the JS render path is unguarded and there are ZERO literal `<live-dot>` tags in committed HTML (fixture + footer inject via `document.createElement`), so the CI no-arg gate currently guards nothing real [scripts/check_dashboard_color_only.py:90,190] — deferred, ratified D3(a) scope.
- [x] [Review][Defer] DEF-2 — Broadened stylelint glob `styles/**` → `static/**` token-lints ALL `static/**/*.css`; a future vendored/third-party CSS under `static/` would be wrongly failed against the design-token config [.github/workflows/ci.yml:21] — deferred, low / no current exposure.

**Dismissed (7)**

- DIS-1 — "empty `<div>` sibling accepted as a label" (Blind #4): DISPROVEN by reproduction — `empty_div_sibling` → VIOLATION (the `after` slice begins with the dot's own `</live-dot>` closing tag, tag=None → flagged).
- DIS-2 — `attributeChangedCallback` "double-render storm": no infinite loop (`setAttribute` to an equal value doesn't re-fire); negligible churn; not a correctness defect.
- DIS-3 — "no timer → footer never auto-goes-stale": BY DESIGN for v1; the poll loop that rewrites `now`/`last-poll` is explicitly 5.6's scope (Task 4 drives last-poll from an injected timestamp until 5.6).
- DIS-4 — "exit-2 suppressed when a violation co-occurs": violation-precedence (return 1) is reasonable; CI keys on non-zero exit. Not a defect.
- DIS-5 — pre-commit `files: …\.html$` with `pass_filenames:false`: harmless — the hook re-scans the full default root regardless; mirrors the frozen DD-14 hook shape.
- DIS-6 — "`>` vs `>=` at exactly 30000ms": AC3 says "older than 30s"; exactly 30s is NOT older → strict `>` is correct.
- DIS-7 — "`isStale(null)===true` dead vs render path": the null path renders the `--:--:--` placeholder and never consults `isStale`; the exported helper is correct in isolation. Not a defect.

**Verified passes (no finding):** all component CSS `var(--*)` resolve in `tokens.css`; `.live-dot-pulse`/`--stop` + reduced-motion + `@keyframes pulse` exist (`focus-motion.css`/`tokens.css`) and `currentColor` resolves via per-variant `color:`; 25% static glow exact; no `@keyframes` redefinition (D1); 6 component files force-included; AC text verbatim-faithful to `epics.md:2484-2508`.

**Close-out gate (Acceptance Auditor F11):** coverage ≥87% + the Playwright behaviors were NOT run on the Windows dev host. PATCH-1 must land AND CI must be GREEN before `review → done` (merged-before-done gate, CLAUDE.md binding).
