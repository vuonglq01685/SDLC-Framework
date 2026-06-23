# Story 5.2: Design Token Foundation (Colors, Typography, Spacing, Motion)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L1 (zero-indegree root, mutually independent of 5.1). Worktree: epic-5/5-2-design-token-foundation. Roots the entire CSS/component tree — FREEZE token names before L2 (5.3/5.4 consume them). -->

## Story

As a frontend engineer codifying the prototype's design language,
I want CSS custom properties under canonical `:root` declaring all design tokens (color, type scale, spacing, border/radius/elevation, motion), with the prototype's `[data-theme="dark"]` block promoted to canonical and the light-mode block stripped per DD-09,
so that subsequent component stories reference tokens, not raw values, and the editorial register is consistent (UX-DR17, DD-01, DD-02, DD-09).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.2).

**AC1 — `tokens.css` declares all tokens under a single canonical `:root`**
- **Given** `dashboard/static/styles/tokens.css` **When** I open the file **Then** it declares all tokens under `:root` (single canonical block; no `[data-theme="dark"]` selector remains)
- **And** color tokens cover: `--accent` (oklch equivalent of `#E27858` per DD-02), `--paper`, `--ink`, `--ink-mute`, `--ink-soft`, `--ink-dim`, `--rule`, `--green`, `--amber`, `--red`, `--blue`, `--purple`
- **And** typography tokens cover Fraunces (display + hero), Inter (body + label), JetBrains Mono (code + data); type scale per UX spec §3.2
- **And** spacing tokens follow a 2-pixel base scale per UX spec §3.3
- **And** motion tokens define `--motion-pulse-live`, `--motion-pulse-stop`, plus easing curves

**AC2 — stylelint gate: raw values fail CI with line:column**
- **Given** the tokens file **When** any component CSS uses raw color/spacing/font values instead of `var(--*)` references **Then** a stylelint rule fails the CI build with the exact line:column
- **And** `dashboard/static/styles/.stylelintrc.json` configures this rule

**AC3 — DD-09 enforcement: no `data-theme` anywhere**
- **Given** DD-09 enforcement **When** any CSS file references `[data-theme="dark"]` or attempts to read/set `data-theme` in JS **Then** the boundary check fails (no theme switching mechanism exists in v1)

## Tasks / Subtasks

> The pure token declarations are novel design substrate → `test-along` is fine. **But the two CI gates (AC2 stylelint, AC3 DD-09 guard) are testable and MUST be tests-first** (RED: a raw value / a `data-theme` reference fails; GREEN: `var(--*)` passes, clean files pass). Per CONTRIBUTING §2 the gate scripts/config are the test-first surface.

- [x] **Task 0 — Resolve Decisions D1 (stylelint-in-CI) and D2 (accent oklch) before coding** (AC: 1, 2)
  - [x] Raise D1 + D2 (see Dev Notes → Decisions); record the picks in the PR Change Log per CONTRIBUTING §5.

- [x] **Task 1 — Author `src/sdlc/dashboard/static/styles/tokens.css`** (AC: 1)
  - [x] Promote the prototype's `[data-theme="dark"]` block (`docs/ux/dashboard-prototype/dashboard.html` lines 32–52) to a single canonical `:root` — change the selector from `[data-theme="dark"]` to `:root`, **strip the light-mode `:root` block entirely**, leave no `[data-theme]` selector (DD-09)
  - [x] Declare the FULL token set from UX §3.1–§3.5 (the AC's 12 named colors are the *minimum* the gate checks; downstream components need the soft variants + `--bg` + `--rule-strong`). Use the canonical block in Dev Notes below
  - [x] Color: `--bg`, `--paper`, `--ink`, `--ink-soft`, `--ink-mute`, `--ink-dim`, `--rule`, `--rule-strong`, `--accent` (+ `--accent-soft`), and `--green/--amber/--red/--blue/--purple` each with a `-soft` 12%-alpha variant. `--accent` per D2 (oklch vs hex)
  - [x] Typography: `--font-serif/--font-sans/--font-mono` family tokens + the §3.2 type scale (`--type-display-hero` … `--type-mono-tag`). Pick a token-granularity convention (per-property tokens, or a documented `font:`-shorthand) and FREEZE the naming this story (5.6/5.7/5.9/5.10 reference them). Hero = `44px/1.05 serif 500 ls -0.02em`; Masthead H1 = `32px/1 serif 600 ls -0.015em`
  - [x] Spacing: `--space-1`…`--space-18` (2px base, 4px→40px) + `--space-shell-top/-bottom` + layout tokens (`--layout-shell-max-width: 1360px`, `--layout-min-viewport: 1280px`, `--layout-grid-gap: 32px`, `--layout-shell-padding-x: 40px`)
  - [x] Border/radius: `--border-hairline`, `--border-strong` (the masthead broadsheet rule = `1px solid var(--ink)`), `--border-dashed`, `--border-accent`; `--radius-none/-sm(3px)/-md(4px)/-lg(6px)/-xl(8px)/-pill(999px)`. **No box-shadows except the functional live-dot glow + `0 0 0 3px var(--accent-soft)` focus ring** (DD-09 strips the prototype's light-mode `0 1px 0` card shadow)
  - [x] Motion: `--motion-pulse-live: 2.4s ease-in-out infinite`, `--motion-pulse-stop: 2.4s ease-in-out infinite`, `--motion-copy-feedback: 1.0s`, plus the `@keyframes pulse { 50% { box-shadow: 0 0 0 6px color-mix(in srgb, currentColor 8%, transparent); } }`. (Live-dot consumes these in 5.5; reduced-motion stripping is 5.4 — do not implement pulses here, only the tokens/keyframe.)

- [x] **Task 2 — `@font-face` placeholder note** (AC: 1)
  - [x] `tokens.css` declares the family tokens only; the actual `@font-face` rules + self-hosted font files land in **Story 5.3** (no-Google-Fonts). Do NOT add `<link>` to a font CDN. Family token fallbacks per UX §3.2 (`'Fraunces', Georgia, serif` etc.)

- [x] **Task 3 — stylelint gate** (AC: 2) — *tests-first*
  - [x] Add `src/sdlc/dashboard/static/styles/.stylelintrc.json` configuring a rule that fails on raw color/spacing/font literals where a `var(--*)` is expected (e.g. `declaration-property-value-disallowed-list` / `scale-unlimited/declaration-strict-value` or equivalent), reporting `file:line:column`
  - [x] Wire a `stylelint` CI job (Decision D2 of the DAG = single CI surface, gate added by this foundation story). RED fixture: a CSS file using a raw `#fff`/`12px`/`Inter` fails; GREEN: `var(--ink)`/`var(--space-5)`/`var(--font-sans)` passes
  - [x] See D1 on the Node-in-CI reconciliation with the "no npm runtime" rule

- [x] **Task 4 — DD-09 boundary check** (AC: 3) — *tests-first*
  - [x] Add a forbidden-pattern gate (Python grep-style script in `scripts/`, mirroring `check_module_boundaries.py`’s shape, wired into CI + pre-commit) that fails if any `dashboard/static/**` CSS references `[data-theme` OR any JS reads/sets `data-theme` (`getAttribute/setAttribute/dataset.theme/data-theme`). Name the violating `file:line`
  - [x] RED: a file containing `[data-theme="dark"]` fails; GREEN: the clean `tokens.css` passes. This is the first of the net-new frontend gates (5.3 no-Google-Fonts, 5.4 no-framework, 5.5 color-only, 5.12 forbidden-patterns) — keep it small and composable

- [x] **Task 5 — Quality gate + docs**
  - [x] Ensure the new CSS/scripts pass the Python quality gate where applicable (ruff/mypy for any new `scripts/*.py`); `mkdocs build --strict` green; zero wire-format change (freeze stays 7/7)

### Review Findings

> bmad-code-review 2026-06-23 — Blind Hunter + Edge Case Hunter + Acceptance Auditor (Opus 4.8). AC1 fully satisfied (token set + `--accent` oklch ≈ `#E27858` verified accurate); AC3 CSS/JS gate works for the in-scope extensions; AC2 satisfied literally for the RED fixture. 2 decisions RESOLVED (Decision 2 → patch P5 "extend gate to .html"; Decision 1 → defer "accept minimum stylelint now + switch to declaration-strict-value before Story 5.5"). Net: 5 patches, 3 deferred, 5 dismissed (incl. 2 Blind-Hunter false-positives grounded out: `!important` is excluded from postcss `decl.value` so it does NOT bypass the gate; the `import check_dashboard_no_data_theme` works via `tests/conftest.py:20-22` sys.path wiring).
>
> **✅ All 5 patches APPLIED 2026-06-23 (TDD-first RED→GREEN).** P1 `errors="replace"`; P2 newline-preserving comment blanking + match-based col; P3 `\[\s*data-theme` + `dataset['theme']` pattern + JS patterns reordered specific-first; P4 unknown explicit path → warn + exit 2; P5 `*.html` added to globs + scanned via JS pattern set (`+ pre-commit files: …|html`), `.html` RED fixture added. Full gate green: `ruff format/check` + `mypy --strict` + **full pytest 3873 passed / coverage 88.64% ≥ 87%** + pre-commit DD-09 hook pass. **NOTE — story stays `review`, NOT flipped to `done`:** per CONTRIBUTING the done-flip waits for TDD-first commit ordering (`test(5.2)→feat(5.2)`) → worktree `epic-5/5-2-*` → PR → CI green (10 required checks) → linear merge. Defers W1/W2/W3 remain open (W3 = hard prerequisite before Story 5.5).

- [x] [Review][Defer] stylelint raw-value gate is materially narrower than AC2 "raw color/spacing/font values" — `.stylelintrc.json` only blocks: named-functional/hex colors (NOT named colors `red`/`white`/`transparent`/`currentColor`), `px`-only numerics (NOT `em`/`rem`/`%`/unitless), spacing on padding/margin/gap/border-radius/border-width only (NOT width/height/inset/top/left/grid-template), and font literals only for the 3 known families (quoted form only for `Inter`). Shorthands (`font:`/`border:`/`box-shadow:`/`outline:`/SVG `fill`) carry raw literals on un-listed properties → uncaught. The `violation_data_theme.css` fixture even uses `color: red`, which stylelint does NOT catch. Story prose already calls this "the minimum the gate checks" + raised Decision D1. Options: (a) accept narrow scope now, document the limitation, widen before L2 component stories (5.5+) land; (b) switch to a token-enforcing plugin (`scale-unlimited/declaration-strict-value`) requiring `var(--*)` comprehensively; (c) incrementally extend the disallowed-list (named colors + more properties + units). **RESOLVED 2026-06-23 → (a):** accept the current minimum disallowed-list now (no component CSS exists yet to validate a broad rule; gate strictness is NOT a frozen contract, so tightening later is safe and adds no token-name churn). **Hard action item (Story 5.5 prerequisite):** switch to `@scale-unlimited/declaration-strict-value` (require `var(--*)` comprehensively for color/spacing/font properties + a curated `ignoreValues`; CI-only, satisfies Decision D1) — skip the denylist whack-a-mole. Document the limitation in the gate notes; add a stylelint fixture for named colors when widening. Tracked in deferred-work.md as 5.2-W3.
- [x] [Review][Patch] DD-09 gate does not scan `index.html` (a shipped, force-included asset) — `_expand_targets` globs only `*.css`/`*.js`/`*.mjs`; `src/sdlc/dashboard/static/index.html` exists (clean today) and is the most plausible host for `<html data-theme>`, an inline `<script>` theme write, or inline `<style>[data-theme]`. `.ts`/`.cjs`/`.jsx` also uncovered (none exist yet). Task 4 literally scoped "CSS … any JS", not HTML. Options: (a) extend the gate to `.html` now (attribute + inline `<script>` + inline `<style>`) to close the hole before component markup grows; (b) accept current scope, document the limitation, revisit when dashboard HTML/JS grows. **RESOLVED 2026-06-23 → (a) Option 1 (patch P5):** extend the gate to `*.html` now — add `*.html` to the globs and run the `data-theme` patterns over the full HTML text (catches `<html data-theme=>` attribute, inline `<script>` `dataset.theme`/`getAttribute`/`setAttribute`, inline `<style>` `[data-theme]`); add a `.html` RED fixture. index.html is the highest-probability DD-09 host in a no-JS dashboard and the gate is being frozen [scripts/check_dashboard_no_data_theme.py:41-58,91-102]
- [x] [Review][Patch] Non-UTF-8 asset crashes the gate with an unhandled `UnicodeDecodeError` instead of a 0/1 verdict — read with `errors="replace"` (keeps `[data-theme` detection working, no false negative) or wrap in try/except; add a non-UTF-8 regression fixture [scripts/check_dashboard_no_data_theme.py:96]
- [x] [Review][Patch] Multi-line CSS comment shifts every reported `file:line:col` — `_CSS_COMMENT.sub("", text)` collapses embedded newlines before `splitlines()`, so any violation after `tokens.css`'s 10-line header comment is mislocated; replace comments with newline-preserving blanks; add a multiline-comment-then-violation fixture [scripts/check_dashboard_no_data_theme.py:63]
- [x] [Review][Patch] DD-09 detection completeness — `_CSS_PATTERN` `\[data-theme` misses whitespace form `[ data-theme ]` (use `\[\s*data-theme`); JS `dataset\.theme\b` misses bracket access `dataset['theme']`; bare `data-theme` JS pattern (first in the tuple, loop `break`s) shadows the `getAttribute`/`setAttribute` patterns → dead code + wrong violation label (reorder specific-before-broad). Latent only (no `.js` exists yet) but cheap to harden while the gate is being frozen [scripts/check_dashboard_no_data_theme.py:24,25-30]
- [x] [Review][Patch] `_expand_targets` silently drops explicit path args that are neither dir nor file — a renamed/typo'd path in a misconfigured CI/pre-commit invocation scans nothing and exits 0 (false "clean" pass); warn on stderr and/or exit non-zero for unknown explicit paths [scripts/check_dashboard_no_data_theme.py:50-58]
- [x] [Review][Defer] DD-09 CSS regex evaded by newline-split selector `[data-\ntheme]` [scripts/check_dashboard_no_data_theme.py:24] — deferred: line-by-line scan can't see it without whole-text parsing; implausible to write accidentally (no formatter produces it)
- [x] [Review][Defer] stylelint CI step globs `styles/**/*.css`, not the broader `static/**/*.css` [.github/workflows/ci.yml] — deferred: no CSS ships outside `styles/` today; revisit if the static tree grows

## Dev Notes

### DD-01 / DD-02 / DD-09 (verbatim — these govern the whole story)

- **DD-01 — Dark mode only.** No light theme ships in v1. *Supersedes PRD §381–388* (which committed to a light editorial palette as v1 default). [Source: UX §Locked Design Decisions]
- **DD-02 — No external brand.** Accent token derives from the prototype value (`oklch` equivalent of `#E27858` warm-coral) and is the framework's de-facto brand color. [Source: UX §Locked Design Decisions]
- **DD-09 — Promote dark to canonical `:root`.** *"Strip prototype's light-mode `:root` tokens; promote `[data-theme="dark"]` block to canonical `:root`. Remove all `data-theme` reads/writes."* Dual-theme infrastructure is dead weight under DD-01. [Source: UX §1.1 Locked Design Decisions Update]

### Canonical token block (lift this; promote `[data-theme="dark"]` → `:root` per DD-09)

Source of truth: prototype `docs/ux/dashboard-prototype/dashboard.html` lines 32–52 (colors), UX §3.2–§3.5 (type/space/border/radius/motion). Colors below are verbatim from the prototype; type/space/border/radius/motion are from the UX §3 tables.

```css
:root {
  /* ── COLOR: surface ── */
  --bg: #0E0F13;
  --paper: #161922;
  /* ── COLOR: ink (text) ── */
  --ink: #ECEEF3;
  --ink-soft: #C2C7D2;
  --ink-mute: #8B92A2;
  --ink-dim: #5C6273;
  /* ── COLOR: rule (borders/dividers) ── */
  --rule: rgba(255,255,255,0.08);
  --rule-strong: rgba(255,255,255,0.18);
  /* ── COLOR: accent (brand) ── DD-02: oklch equivalent of #E27858 (keep hex in comment) */
  --accent: #E27858;               /* D2: convert to oklch(...) per AC1/DD-02; hex is the validated source */
  --accent-soft: rgba(226,120,88,0.12);
  /* ── COLOR: semantic states (solid + 12% soft) ── */
  --green: #4ADE80;  --green-soft: rgba(74,222,128,0.12);
  --amber: #FBBF24;  --amber-soft: rgba(251,191,36,0.12);
  --red:   #F87171;  --red-soft:   rgba(248,113,113,0.12);
  --blue:  #60A5FA;  --blue-soft:  rgba(96,165,250,0.12);
  --purple:#A78BFA;  --purple-soft:rgba(167,139,250,0.12);

  /* ── TYPOGRAPHY: families ── */
  --font-serif: 'Fraunces', Georgia, serif;
  --font-sans:  'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono:  'JetBrains Mono', ui-monospace, 'Menlo', monospace;
  /* type scale per UX §3.2 — declare --type-display-hero…--type-mono-tag; pick a granularity convention and freeze names */

  /* ── SPACING (2px base) ── */
  --space-1:4px; --space-2:6px; --space-3:8px; --space-4:10px; --space-5:12px;
  --space-6:14px; --space-7:16px; --space-8:18px; --space-9:20px; --space-10:22px;
  --space-11:24px; --space-12:28px; --space-14:32px; --space-16:36px; --space-18:40px;
  --space-shell-top:28px; --space-shell-bottom:80px;
  /* ── LAYOUT ── */
  --layout-shell-max-width:1360px; --layout-shell-padding-x:40px;
  --layout-min-viewport:1280px; --layout-grid-gap:32px;

  /* ── BORDERS ── */
  --border-hairline:1px solid var(--rule);
  --border-strong:1px solid var(--ink);     /* masthead broadsheet rule */
  --border-dashed:1px dashed var(--rule);
  --border-accent:2px solid var(--accent);
  /* ── RADIUS ── */
  --radius-none:0; --radius-sm:3px; --radius-md:4px; --radius-lg:6px; --radius-xl:8px; --radius-pill:999px;

  /* ── MOTION ── */
  --motion-pulse-live:2.4s ease-in-out infinite;
  --motion-pulse-stop:2.4s ease-in-out infinite;
  --motion-copy-feedback:1.0s;
}
@keyframes pulse { 50% { box-shadow: 0 0 0 6px color-mix(in srgb, currentColor 8%, transparent); } }
```

[Source: UX §3.1 colors / §3.2 type scale / §3.3 spacing / §3.4 border-radius / §3.5 motion; prototype dashboard.html:32–52]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — stylelint requires Node in CI; architecture says "no npm/webpack/build step".** The epic AC2 explicitly mandates *stylelint* + `.stylelintrc.json`. Architecture.md:157 says the *shipped dashboard* uses "No npm, no webpack, no React, no build step."
- **D1 (option 1) — stylelint as a CI lint gate only (recommended):** add a pinned `npx stylelint` job to the existing CI matrix (DAG Decision D2 = single CI surface, gates added incrementally). Node is a dev/CI tool like ruff is for Python; the *runtime artifact* still ships zero npm deps / no bundle / no build step — which 5.4's no-framework guard asserts (zero runtime UI deps, no vendor bundles). The "no npm" rule targets the shipped frontend, not the lint toolchain. *Pro:* satisfies AC2 literally; *Con:* introduces a pinned Node toolchain to CI.
- **D2 (option 2) — Python regex gate instead of stylelint:** a `scripts/check_dashboard_css_tokens.py` that flags raw literals. *Pro:* Python-only, no Node; *Con:* **violates AC2's literal "a stylelint rule" + `.stylelintrc.json" requirement** → would need an epic AC waiver from the Project Lead.
- **Reviewer recommendation:** **D1 option 1** — keep stylelint (epic-mandated) scoped to CI; keep the runtime artifact npm-free. Escalate to Project Lead only if adding Node to CI is itself contested.

**D2 — `--accent`: oklch vs hex.** AC1 says `--accent` is the *"oklch equivalent of `#E27858`"*; the prototype + UX §3.1 use the hex `#E27858` as the validated stakeholder value. *Recommendation:* write `--accent: oklch(<computed>)` to satisfy the AC's literal wording, keeping `/* #E27858 */` as a source comment (DD-02). Compute the oklch from `#E27858` with a real converter — **do not guess the value.** (Minor; resolve inline, no escalation needed.)

### Project Structure Notes

- New file `src/sdlc/dashboard/static/styles/tokens.css` + `src/sdlc/dashboard/static/styles/.stylelintrc.json`. Static assets live inside the `dashboard` package (ADR-005 `package_data`). The epic writes `dashboard/static/...` (package-relative shorthand). [Source: architecture.md#Module Specification, :276]
- **Variance from architecture/UX (rationale):** architecture §Module-Spec shows a single flat `static/styles.css`; UX §1.1 names `dashboard/static/dashboard.css`. The **epic AC is the binding path** and uses `dashboard/static/styles/tokens.css` (a `styles/` subdir, tokens split into their own file) — follow the epic. Component CSS in later stories lives alongside under `static/`.
- `5-1` and `5-2` are mutually-independent L1 roots — no dependency between them; both branch from `main`, linear merge, rebase-between-merges (CONTRIBUTING §3). 5.2 freezes token NAMES before L2 (5.3 fonts, 5.4 focus-ring/motion both consume tokens).
- Zero wire-format contracts (CSS is not a wire contract) — freeze stays 7/7. Quality gate (CONTRIBUTING §1) applies to any new `scripts/*.py` (ruff/mypy --strict); `mkdocs --strict` green.

### Net-new CI gates this story stands up (DAG Decision D2 — incremental, single CI surface)

This is the first frontend gate story. It stands up: the **stylelint** job (AC2) and the **DD-09 no-`data-theme`** guard (AC3). Later foundation stories add: no-Google-Fonts (5.3), no-framework + transition grep (5.4), color-only signaling (5.5), forbidden-patterns + axe-core + keyboard (5.12). Keep each gate small, composable, and in the same CI matrix — do not fork a second CI system. [Source: docs/sprints/epic-5-dag.md Decision D2 (ratified = a)]

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.2] — ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §3.1–§3.5] — color/type/spacing/border-radius/motion tokens; DD-01/DD-02/DD-09
- [Source: docs/ux/dashboard-prototype/dashboard.html:32–52] — prototype `[data-theme="dark"]` block (promote to `:root` per DD-09)
- [Source: docs/sprints/epic-5-dag.md#5. Worktree Assignments] — 5.2 row (stylelint gate + DD-09 guard; freeze token names before L2)
- [Source: docs/sprints/epic-5-dag.md#Decision D2] — single-CI-surface frontend gating (ratified = a)
- [Source: _bmad-output/planning-artifacts/architecture.md:157, #Module Specification, :276] — stdlib/no-npm runtime; dashboard/static layout; ADR-005 package_data
- [Source: _bmad-output/planning-artifacts/prd.md §400–404] — typography stack (local fonts, no CDN), color/STOP/signoff visual contracts

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor)

### Debug Log References

- D1 resolved: option 1 — stylelint as CI lint gate only (`npx stylelint@16.18.0`); Node is dev/CI tooling, runtime artifact stays npm-free.
- D2 resolved: `--accent: oklch(68.62% 0.140 37.57)` with `/* #E27858 */` source comment.
- DD-09 scanner strips CSS block comments so tokens.css header docs do not false-positive.
- Hatch force-include lists explicit dashboard static runtime files only; `.stylelintrc.json` excluded from wheel.

### Completion Notes List

- Authored canonical `tokens.css` under `:root` with full color/type/spacing/layout/border/radius/motion token set per UX §3.1–§3.5 and DD-01/DD-02/DD-09.
- Added `.stylelintrc.json` with `declaration-property-value-disallowed-list` (tokens.css ignored).
- Added `scripts/check_dashboard_no_data_theme.py` + CI + pre-commit wiring.
- Added `frontend-gates` CI job for stylelint; DD-09 gate in quality-gates matrix.
- TDD: 12 new tests (8 DD-09 script + 4 stylelint integration) all green; full suite 3863 passed.

### File List

- src/sdlc/dashboard/static/styles/tokens.css (new)
- src/sdlc/dashboard/static/styles/.stylelintrc.json (new)
- scripts/check_dashboard_no_data_theme.py (new)
- tests/unit/scripts/test_check_dashboard_no_data_theme.py (new)
- tests/unit/dashboard/test_dashboard_css_gates.py (new)
- tests/fixtures/dashboard_css/violation_data_theme.css (new)
- tests/fixtures/dashboard_css/violation_raw_literals.css (new)
- tests/fixtures/dashboard_css/clean_component.css (new)
- .github/workflows/ci.yml (modified)
- .pre-commit-config.yaml (modified)
- pyproject.toml (modified — explicit dashboard static force-include)
- _bmad-output/implementation-artifacts/sprint-status.yaml (modified)

## Change Log

- 2026-06-23: Story 5.2 implementation — design token foundation, stylelint CI gate (D1a), DD-09 no-data-theme guard, oklch accent (D2).
