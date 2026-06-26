# Story 5.7: KPI Strip + KPI Value Cell

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L4 (5A). L4 = {5.6, 5.7, 5.8, 5.11}, max 4 parallel worktrees (cap-saturating). Depends on 5.5 (freshness-footer/live-dot FROZEN) (+ 5.2 frozen tokens) — ALL done+merged. Edges: 5.2→5.7, 5.5→5.7; downstream 5.7→5.13 (real /api/dora backend), 5.7→5.17 (real DORA 7d/30d rendering, L7 — reuses 5.7's n/a no-data treatment), 5.7→5.12 (a11y convergence gate). Worktree: epic-5/5-7-kpi-strip-value-cell. Branch from main, linear merge, rebase between L4 merges (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). SYNTHETIC fixtures only — the 30s DORA cache + /api/dora compute is 5.13; real DORA data wiring is 5.17. This story renders the STALE state from a fixture flag; it does NOT compute the cache. -->

## Story

As Quan reading project KPIs pre-standup,
I want the KPI Strip (5 even cells below masthead) rendering each cell with mono uppercase label, Fraunces 44 px hero numeral, optional unit, and delta with up/down/neutral color, plus three states (Default / No-data `n/a` / Stale),
So that DORA + project KPIs carry editorial weight and screen-reader semantics are clean (UX-DR2, §6.3).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.7, lines 2545–2562).

**AC1 — KPI Strip (default / full data)**
- **Given** the KPI Strip **When** rendered with synthetic fixture data **Then** the structure is `<section role="region" aria-label="Project KPIs">` containing 5 cells with right-borders (`--rule`) except the last
- **And** each cell uses `<dl>`/`<dt>`/`<dd>` (or `aria-labelledby` linking label and value) for screen-reader semantics
- **And** the hero numeral uses `--type-display-hero` (Fraunces 44 px 500, letter-spacing -0.02em)

**AC2 — No-data cell (`n/a`)**
- **Given** a cell with no data **When** rendered **Then** the value displays `n/a` in `--ink-dim` text (real text, not a glyph)
- **And** the delta line is omitted
- **And** `aria-describedby` provides the reason

**AC3 — Stale cell**
- **Given** a cell with stale data (metric older than 30 s cache) **When** rendered **Then** the value uses `--ink-mute` instead of `--ink`
- **And** the delta line shows `as of HH:MM:SS`

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** all three states are deterministic and fixture-renderable → tests-first via a static-analysis/DOM contract over the committed fixtures (mirror 5.10's `test_backlog_tree_fixture.py`): assert the `role="region"`/5-cell/right-border-except-last structure, the `<dl>`/`<dt>`/`<dd>` semantics, the `n/a`-real-text + `aria-describedby` + dropped-delta no-data contract, and the stale `--ink-mute` + `as of HH:MM:SS` contract. The state-resolution normalizer (trim+lowercase) is unit-testable in isolation. The cell CSS is `test-along`. Resolve Decisions D1–D4 BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (`<dl>` vs `aria-labelledby` semantics) + D2 (Unit "16px Inter" has no token under the CSS gate) + D3 (delta non-color signal: text arrow/sign vs sprite glyph) + D4 (stale drops the trend delta for `as of HH:MM:SS`) BEFORE coding** (AC: 1, 2, 3)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). Align the component layout to the 5.5-frozen `static/components/<name>/` convention.

- [x] **Task 1 — KPI Strip + Value Cell structure (Default state)** (AC: 1)
  - [x] `<section role="region" aria-label="Project KPIs">` containing 5 even cells; cells 1–4 carry the right-border (`--rule`), cell 5 does NOT (epics:2549). [§6.3 ux:1091-1097]
  - [x] Each cell = the 3-line stack: label (`--type-label-mono-sm` uppercase, `--ink-mute`) → value (hero numeral) → delta. Each cell uses `<dl>`/`<dt>`/`<dd>` (or `aria-labelledby` linking label+value) — D1.
  - [x] Hero numeral = compose `--type-display-hero-{size:44px,line-height:1.05,weight:500,letter-spacing:-0.02em}` + `font-family: var(--font-serif)`, color `--ink` (NO single `--type-display-hero` var — per-property compose). Optional unit after the value (D2). Cell padding `--space-10 × --space-12`.

- [x] **Task 2 — Delta line (up / down / neutral)** (AC: 1) — *tests-first*
  - [x] Delta = `--type-mono-data` with up/down/neutral color: up `--green`, down `--red`, neutral `--ink-mute`. **Color is never the sole signal (§3.1 / §8.4):** embed a text arrow `↑`/`↓` (or sign `+`/`-`) in the delta text (D3) so the trend reads without color.
  - [x] Mirror the signoff-cell color-on-text pattern (color the delta TEXT, not just a swatch).

- [x] **Task 3 — No-data state (`n/a`)** (AC: 2) — *tests-first*
  - [x] Value `n/a` as **real text** in `--ink-dim` (NOT a glyph). Delta line **omitted**. `aria-describedby` points to a non-empty reason node (UX §6.3: "tooltip explains why, anti-cynicism, never blank"). [epics:2553-2557; ux:1101]

- [x] **Task 4 — Stale state** (AC: 3) — *tests-first*
  - [x] Value uses `--ink-mute` (instead of `--ink`). Replace the trend delta with `as of HH:MM:SS` (D4) — reuse `freshness-footer.formatLocalTime()`. The 30 s threshold is computed UPSTREAM (5.13 cache); 5.7 renders stale from a **fixture flag/attribute**, it does NOT compute the cache. [epics:2559-2562; ux:1102]
  - [x] State-resolution normalizer: mirror signoff-cell `resolveState` (`String(raw||"default").trim().toLowerCase()`, membership-check, safe fallback) for the KPI state vocab (`default`/`no-data`/`stale`). Unit-test it directly.

- [x] **Task 5 — Committed synthetic fixtures + static-analysis contract test** (AC: 1, 2, 3) — *tests-first*
  - [x] Commit a `kpi-strip.fixture.html` exercising all three states. Add a test asserting: structure (region + 5 cells + right-border-except-last), `<dl>`/`<dt>`/`<dd>` semantics, hero-numeral class consumes `--type-display-hero-*`, no-data (`n/a` text + `aria-describedby` + no delta), stale (`--ink-mute` + `/^as of \d{2}:\d{2}:\d{2}$/`). **RED:** a glyph `n/a`, a present delta in no-data, or missing right-border logic fails; **GREEN:** correct. Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`).

- [x] **Task 6 — Packaging + quality gate + freeze** (AC: 1, 2, 3)
  - [x] Add new CSS/JS/HTML (kpi-strip + fixture) to the `force-include` block [pyproject.toml].
  - [x] Component CSS uses `var(--*)` only (5.2 stylelint gate at `static/styles/.stylelintrc.json`); run DD-14 motion gate (no transitions), DD-08 no-framework, DD-09 no-data-theme, and the 5.5 color-only gate (the delta arrow/sign satisfies it).
  - [x] Python quality gate on any new `scripts/*.py`/tests (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7**.

### Review Findings

> bmad-code-review (2026-06-26) — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + orchestrator source-verification (every HIGH reproduced against the real `kpi-strip.js` / `kpi-strip.css` / fixture / tests). Reviewed jointly with Story 5.6. Triage for 5.7: **5 patch + 2 defer**.

- [x] [Review][Patch] Stale hero numeral renders `--ink`, not `--ink-mute` — CSS source-order cascade (AC3) — `.kpi-strip__hero--stale { color: var(--ink-mute) }` (css:50) is overridden by the later equal-specificity `.kpi-strip__hero { color: var(--ink) }` (css:60); the stale numeral span carries both classes so the later rule wins. Fix: move the `--stale` rule after `.kpi-strip__hero` or raise specificity. `test_stale_value_uses_ink_mute_in_css` only checks the class name exists → does not catch it [kpi-strip.css:49-61]
- [x] [Review][Patch] `n/a` reason node is a bare `<span>` appended directly under `<dl>` (invalid `<dl>` content model) — AC2 is functionally met but the describedby target should sit inside a `<dd>`/`<div>` [kpi-strip.js:34-39]
- [x] [Review][Patch] `<kpi-strip>` throws uncaught on a non-object cell (e.g. `fixture="[null]"`) — `renderKpiStrip` is outside the JSON `try/catch` and `renderKpiCell` dereferences `cell.state`; whole strip fails to render with no fallback. Guard non-object cells [kpi-strip.js:71,121-138]
- [x] [Review][Patch] Dead `_AS_OF_RE` regex — run against JS source (`as of ${formatLocalTime(when)}`, no digits) it never matches; the assertion only passes via the `or "as of"` fallback, giving false confidence the `HH:MM:SS` format is checked [test_kpi_strip_fixture.py:24,129]
- [x] [Review][Patch] Five-cell test counts `label:` across the whole file (incl. the placeholder cell) with `>= 5` → passes with 4 real fixture cells; does not pin cell count or the right-border-except-last structure [test_kpi_strip_fixture.py:77]
- [x] [Review][Defer] DORA delta sentiment — fixture `LEAD TIME FOR CHANGES` uses `direction:"down"` and renders red, though a lead-time decrease is an improvement [kpi-strip.js:151-155] — deferred: component is spec-compliant (5.7 Task 2: up=green/down=red); metric-direction sentiment is Story 5.17's job
- [x] [Review][Defer] Duplicate `kpi-no-data-reason-${index}` ids if multiple `<kpi-strip>` coexist (light DOM) → `aria-describedby` resolves to the first match [kpi-strip.js:83] — deferred: spec is one strip per dashboard (§6.3); latent only, add instance-scoped ids if that changes

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§6.3 KPI Strip + Value Cell.** One strip per dashboard, immediately below masthead. Five even cells. Part→token table [ux:1091-1097]: Cell = `--space-10 × --space-12` padding + `--rule` right-border (except last); Label = `--type-label-mono-sm` (mono 10px 500), `--ink-mute`, uppercase, letter-spacing 0.14em; Value = `--type-display-hero` (Fraunces 44px 500), `--ink`, letter-spacing -0.02em; Unit = inline 16px Inter, `--ink-mute`, weight 400; Delta = `--type-mono-data` with up/down/neutral color. Variants: *"None — differentiation is by content, not visual variant."* a11y: `role="region"` + `aria-label="Project KPIs"`; each cell `aria-labelledby` linking label+value. Keyboard: *"No interactions. Read-only."* States: Default / No-data (`n/a`, anti-cynicism, never blank) / Stale (`as of HH:MM:SS`). [Source: ux-design-specification.md §6.3:1077-1111]
- **§8.4 a11y checklist (KPI Strip).** `role="region"` `aria-label="Project KPIs"`; semantic `<dl>`/`<dt>`/`<dd>` OR `aria-labelledby`; No-data `n/a` is **real text, not a glyph**, reason in `aria-describedby`; Stale "the freshness footer is screen-reader-readable." [Source: ux-design-specification.md §8.4:1742-1747]
- **§3.1 / §8.4 color rule.** Color is never the only signal — the delta up/down needs an adjacent text arrow/sign. [Source: ux-design-specification.md §8.4:1762]

### Frozen foundation to consume (do NOT redefine — 5.2/5.5 froze these)

```css
/* tokens.css — KPI vocabulary (consume per-property var; NO composite --type-display-hero) */
--type-display-hero-size:44px; --type-display-hero-line-height:1.05; --type-display-hero-weight:500; --type-display-hero-letter-spacing:-0.02em;  /* hero numeral */
--type-label-mono-sm-size:10px; …-weight:500; …-letter-spacing:0.14em;   /* cell label */
--type-mono-data-size:11px; …-weight:500; …-letter-spacing:0;            /* delta + "as of" */
--rule (cell right-border);  --ink (#eceef3 value);  --ink-mute (#8b92a2 stale value + label);  --ink-dim (#5c6273 n/a);
--green (#4ade80 delta up);  --red (#f87171 delta down);  /* neutral delta → --ink-mute */
--space-10:22px; --space-12:28px (cell padding);  --font-serif (value);  --font-sans (unit);  --font-mono (label/delta);
```
```text
<freshness-footer> formatLocalTime(date) → zero-padded HH:MM:SS [freshness-footer.js:13-16]; STALE_MS=30_000 [freshness-footer.js:11] is the canonical 30s threshold helper.
signoff-cell.resolveState(raw): String(raw||"default").trim().toLowerCase() + membership-check (PAT-1) — mirror for KPI state vocab [signoff-cell.js:33-38].
createGlyph(iconId, className) exported from signoff-cell.js — reuse ONLY if a visual SVG arrow is required; prefer a plain-text arrow.
```
[Source: tokens.css:101-135,187-200,222-224,127-129,107; freshness-footer.js:11-16; signoff-cell.js:33-38]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Cell semantics: `<dl>`/`<dt>`/`<dd>` vs `aria-labelledby`.** Both epics:2550 and §8.4 explicitly permit either ("or"). *Recommendation (a):* use semantic `<dl>` (`<dt>`=label, `<dd>`=value+unit, `<dd>`=delta) as the primary structure — the most honest semantic, reads "label + value + delta" without ARIA gymnastics. The strip is `<section role="region" aria-label="Project KPIs">`.

**D2 — Unit "16px Inter" cannot be encoded under the CSS gate.** §6.3 specs the unit as "inline 16px Inter, weight 400" but `.stylelintrc.json` forbids `font-size: 16px` and NO `--type-*` token equals 16px (tokens are FROZEN by 5.2). *Recommendation (a):* render the unit with `--type-body-size` (14px, Inter 400, `--ink-mute`) — the nearest existing sans body token; document the 16px→14px spec-vs-frozen-token reconciliation. Do NOT add a token to the frozen tree. *(b)* escalate a new token — rejected (re-freeze risk).

**D3 — Delta non-color signal: text arrow/sign vs sprite glyph.** The UX anatomy shows `↑ +0.8 vs last 7d`. *Recommendation (a):* embed a plain-text arrow (`↑`/`↓`) or sign (`+`/`-`) in the delta `<dd>` text — satisfies the color-only rule with zero sprite dependency, matches the anatomy literally, avoids importing `createGlyph`. Neutral delta → `--ink-mute` with a `→`/`—` or no arrow.

**D4 — Stale + delta interaction.** In stale state epics:2562 replaces the delta with `as of HH:MM:SS`. *Recommendation (a):* drop the trend delta entirely in stale; the timestamp line occupies the delta slot (mirroring freshness-footer's `as of` format). The value is muted (`--ink-mute`).

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the visual + a11y **KPI Strip + Value Cell** component (3 states) rendered from **SYNTHETIC fixtures only**. Freezes the `n/a` no-data treatment + the cell DOM/a11y contract that **5.17** reuses.
- **Must NOT build:** the `/api/dora` endpoint, the DORA engine, or the **30 s cache** — that is **5.13** (the "metric older than 30 s cache" stale trigger is rendered from a fixture flag, NOT computed). Real DORA 7d/30d data + real deltas = **5.17** (L7). No reads of `state.json` / `agent_runs.jsonl` / git-log. [Source: docs/sprints/epic-5-dag.md §3 (L4:213, L7:216), §6 (5.7 row:285, 5.13 row:291, 5.17 row:295), §2 twin:241-242]

### Project Structure Notes

- New: `static/components/kpi-strip/` (CSS/JS/fixture) under the 5.5-frozen convention. All new static files → `force-include` [pyproject.toml].
- Component CSS must use `var(--*)` — the 5.2 stylelint gate (at `src/sdlc/dashboard/static/styles/.stylelintrc.json`, NOT repo root) FORBIDS raw color/font-size/padding/letter-spacing/etc. `--type-display-hero` is per-property only (expand all four props; mirror signoff-cell.css's `--type-label-mono-sm-*` / `--type-mono-data-*` expansion).
- The strip is read-only (no interactions) — no focusable elements; the a11y contract is the `region`/`dl`/`aria-describedby` semantics.
- L4 siblings (5.6/5.7/5.8/5.11) mutually independent; cap-saturating. Branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3).
- Zero wire-format contracts (CSS/JS/HTML are not wire contracts) → freeze stays 7/7.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| `HH:MM:SS` (stale "as of") + 30s threshold | `freshness-footer.formatLocalTime` / `STALE_MS` / `isStale` | src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:11-35 |
| State-resolution normalizer (trim+lowercase) | mirror signoff-cell `resolveState` (PAT-1) | src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.js:33-38 |
| Per-property type expansion pattern | signoff-cell.css expands `--type-*-{size,weight,…}` | src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.css:40-58 |
| KPI tokens (hero/label/delta/ink) | Consume frozen tokens (D2 unit reconciliation) | src/sdlc/dashboard/static/styles/tokens.css:101-135,187-200,222-224 |
| Color-only gate (delta needs adjacent arrow/sign) | `check_dashboard_color_only.py` | scripts/check_dashboard_color_only.py |
| Motion / no-framework gates | Run on the new cell | scripts/check_dashboard_motion.py / _no_framework.py |
| Wheel force-include | Add new static files | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2539-2562] — Story 5.7 ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.3:1077-1111] — KPI Strip anatomy + token table + 3 states + a11y
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §8.4:1742-1747, 1762] — KPI a11y checklist + color-never-only-signal
- [Source: src/sdlc/dashboard/static/styles/tokens.css:101-135,187-200,222-224] — `--type-display-hero` (per-property), `--rule`, `--ink-dim`/`--ink-mute`, `--green`/`--red`, `--space-10/12`
- [Source: src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:11-35] — `formatLocalTime` / `STALE_MS` / `isStale`
- [Source: src/sdlc/dashboard/static/components/signoff-cell/signoff-cell.js:33-38, signoff-cell.css:40-58] — `resolveState` PAT-1 + per-property type expansion
- [Source: src/sdlc/dashboard/static/styles/.stylelintrc.json] — var(--*) enforcement (drives D2)
- [Source: docs/sprints/epic-5-dag.md §3 (L4:213, L7:216), §6 (5.7:285 / 5.13:291 / 5.17:295), §2 (twin:241-242)] — layer, edges, "consumed by 5.13/5.17"
- [Source: _bmad-output/implementation-artifacts/5-5-live-dot-family-freshness-footer-pattern.md] — froze freshness-footer + the file-layout convention

## Dev Agent Record

### Agent Model Used

Composer (dev-story workflow)

### Debug Log References

- TDD: `tests/unit/dashboard/test_kpi_strip_fixture.py` authored first (19 contract tests), then component implementation.
- Dashboard gates: color-only, DD-14 motion, DD-08 no-framework, DD-09 no-data-theme — all GREEN.

### Completion Notes List

- **D1:** semantic `<dl>`/`<dt>`/`<dd>` per cell (label / value+unit / delta).
- **D2:** unit rendered with `--type-body-size` (14px Inter reconciliation vs spec 16px).
- **D3:** plain-text arrows `↑`/`↓`/`—` embedded in delta line (color-on-text, not color-only).
- **D4:** stale state drops trend delta; delta slot shows `as of HH:MM:SS` via `formatLocalTime`.
- `<kpi-strip>` custom element + `SYNTHETIC_KPI_FIXTURE` (5 cells: 3 default, 1 no-data, 1 stale).
- `resolveState` PAT-1 normalizer (`default`/`no-data`/`stale`).
- force-include entries added in `pyproject.toml`; freeze 7/7 unchanged (no wire-format edits).

### File List

- `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip.js` (new)
- `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip.css` (new)
- `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip.fixture.html` (new)
- `tests/unit/dashboard/test_kpi_strip_fixture.py` (new)
- `pyproject.toml` (modified — force-include)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — in-progress → review)

## Change Log

- 2026-06-26: Story 5.7 implemented (dev-story). KPI Strip component with 3 states (default/no-data/stale), D1–D4 decisions resolved per recommendations, 19 static-analysis contract tests, dashboard quality gates green.
- 2026-06-25: Story 5.7 created (create-story, "tạo US cho layer tiếp theo" → L4 batch with 5.6/5.8/5.11) — KPI Strip (`role="region"`, 5 cells) + KPI Value Cell (hero `--type-display-hero` numeral, `<dl>` semantics, delta up/down/neutral) + 3 states (Default / No-data `n/a` real-text / Stale `as of HH:MM:SS`). Decisions D1 (`<dl>` vs aria-labelledby) / D2 (Unit "16px Inter" → `--type-body` 14px reconciliation, no new token) / D3 (delta text arrow/sign for color-only) / D4 (stale drops trend delta) raised. L4 (5A), synthetic only; depends on 5.5 + 5.2; feeds 5.13/5.17 (real DORA) + 5.12 a11y gate. Boundary: renders stale from a fixture flag, does NOT compute the 30s cache (that's 5.13).
