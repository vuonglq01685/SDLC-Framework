# Story 5.17: KPI Strip Rendering Real DORA 7d/30d

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG **L7 (5B)**. L7 = {5.17} alone, width 1 (epic-5-dag.md §3:216, §6:330). Worktree: **epic-5/5-17-kpi-strip-real-dora**, owner Sally (dag §5:295). Depends on TWO done+merged stories via edges 5.7→5.17 and 5.13→5.17 (dag §2:141-143): the 5A twin **5.7** (KPI strip + value cell renderer, FROZEN) and **5.13** (DORA backend + `/api/dora` + 30s cache, real compute). Wave gate: 5B data-readiness is satisfied — `/api/dora` reads `agent_runs.jsonl` (2B.10) + git log THROUGH 5.13, which is done+merged; 5.17 consumes only `/api/dora`. Downstream: 5.17 has NO direct successor edge, but its rendered real-data surface is re-scanned by the terminal a11y gate **5.22** (dag §2:200-202). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). This is a **pure frontend real-data swap** — `/api/dora` ALREADY EXISTS (5.13); do NOT touch the backend, do NOT build STOP banner (5.19) / disconnection (5.20) / degradation banner (5.21). Zero `/api/dora` shape edit → freeze stays 7/7. -->

## Story

As Quan reading DORA at-a-glance,
I want the KPI Strip (Story 5.7 component) consuming real `/api/dora` (Story 5.13) and rendering the cells with current values + comparative deltas,
So that DORA visibility lands in the browser without manual computation.

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.17, lines 2782–2795).

**Given** `/api/dora` returning real metrics for both 7d and 30d windows
**When** the KPI Strip renders
**Then** the 5 cells are populated from the response: deployment_frequency, lead_time, change_failure_rate, mttr (and one project KPI like backlog_health)
**And** delta lines compare current 7d vs preceding 7d (or 30d vs preceding 30d)
**And** insufficient-data states render `n/a` per Story 5.7

> ⚠️ **AC-vs-data reconciliation (READ the Wave-boundary verification + Decisions BEFORE coding).** Verification against the shipped `/api/dora` (5.13) found the literal AC premise is **partially unrealized by the real contract** — this drives D1 + D2:
> - **The delta clause is not literally computable.** `/api/dora` emits NO preceding-window and NO delta field — only **current-trailing-7d** and **current-trailing-30d** (both ending `now`). "current 7d vs *preceding* 7d" (days 8–14) does not exist in the payload and cannot be derived. The only comparative signal the payload supports is **7d vs 30d** — which the AC's own parenthetical "(or 30d vs preceding 30d)" already flags as flexible. → **D1**.
> - **`/api/dora` serves only the 4 DORA metrics.** There is no 5th metric and no `backlog_health` anywhere in the codebase (only in epics.md prose "one project KPI *like* backlog_health"). The 5.7 strip is pinned to **exactly 5 cells** by a frozen contract test. → **D2**.
> - **`/api/dora` carries no timestamp/staleness field** → the 5.7 `stale` cell state is NOT driven by real DORA data; real cells use `default`/`no-data` only (do not fabricate `staleAt`).

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2 / ADR-026):** every AC clause is a testable contract → tests-first commit ordering (`test(5.17)` RED before `feat(5.17)` GREEN, visible in `git log --reverse`). This story is NOT novel substrate (the `/api/dora` route + KPI renderer both exist) → no `[tdd-along]` waiver. **JS logic (envelope→cells mapper, delta, sentiment) is testable in this repo ONLY via the Playwright behavioral witness** (there is no JS unit runner) + the static-analysis source contract; write both. **Resolve Decisions D1–D4 in Task 0 BEFORE coding.**

- [x] **Task 0 — Wave-boundary verify + resolve Decisions D1–D4 (record picks in the PR Change Log, CONTRIBUTING §5)** (AC: all)
  - [x] **Wave-boundary check (before branching):** confirm `/api/dora` is live and done+merged — `GET /api/dora` on the real repo returns `200` with `content-type: application/json` and a body shaped `{ "schema_version": 1, "windows": { "7d": {...}, "30d": {...} } }`. (5.13 is `done`; this is a sanity re-verify, not a build.) [routes/dora.py; test_dora_backend.py::TestSchemaConformance]
  - [x] **D1 — delta basis** (HIGH; AC-vs-data). Pick the comparative basis given the payload has only 7d + 30d, no preceding-7d, no delta. **Recommendation (a):** headline value = **7d** window, delta line = **7d vs 30d** ("recent vs baseline"). See Decisions.
  - [x] **D2 — 5th cell / project KPI** (HIGH; AC-vs-data). `/api/dora` has only 4 metrics; the strip renders exactly 5. **Recommendation (a):** 4 real DORA cells + 1 documented `no-data` placeholder; defer the real 5th KPI to a follow-up story. See Decisions.
  - [x] **D3 — per-metric sentiment** (MED; correctness — the explicitly-deferred 5.7 review item). deployment_frequency is higher-is-better; lead_time / change_failure_rate / mttr are lower-is-better. **Recommendation (a):** the mapper owns a per-metric sentiment map and sets the renderer's `delta.direction` to SENTIMENT (up=green/improved, down=red/regressed), not raw numeric direction. See Decisions.
  - [x] **D4 — poller file convention** (LOW; mirror precedent). **Recommendation (a):** new `kpi-strip-live.js` poller importing the frozen `renderKpiStrip`, mirroring 5.18/5.15/5.14 `*-live.js`; keep the 5.7 base + its 19 static-contract tests untouched. See Decisions.

- [x] **Task 1 — `kpi-strip-live.js`: envelope → 5-cell mapper (D2, insufficient-data→n/a)** (AC: 1, 3) — *tests-first*
  - [x] Create `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip-live.js`. Import `renderKpiStrip` from `./kpi-strip.js` (do NOT re-implement it). Write a **pure** `mapDoraToCells(payload)` that reads `payload.windows["7d"]` + `payload.windows["30d"]` and returns an array of **exactly 5** cell objects in the renderer's field contract (`{label, state, value, unit, delta:{direction,text}}` / `{label, state:"no-data", noDataReason}`). [kpi-strip.js:72-124,126-146]
  - [x] Map the 4 DORA metrics 1:1 (D2a): `deployment_frequency` → `value = round(7d.per_day)`, `unit "/day"`; `lead_time` → `value = 7d.value`, `unit "hrs"`; `change_failure_rate` → `value` as a ratio/percent of `7d.value`, `unit` per 5.7; `mttr` → `value = 7d.value`, `unit "hrs"`. The **5th cell** is a documented `no-data` placeholder per D2a (`label` per design, `noDataReason` e.g. "Project KPI not yet wired").
  - [x] **Insufficient-data → `n/a` (AC clause 3):** per metric, if `data_status === "insufficient_data"` (⇒ `value === null`) for the **7d** window, emit a `no-data` cell (`state:"no-data"`, `noDataReason` from the window/metric context) — the frozen `renderNoDataValue` renders `n/a` as **real text** + `aria-describedby` reason. Each of the metrics is independent (7d vs 30d, metric vs metric can mix statuses) — decide each cell against its own `7d.<metric>.data_status`. [kpi-strip.js:24-42,84; test_dora_backend.py::TestMalformedInputResilience]
  - [x] **Client-edge numeric validation (untrusted served JSON):** coerce/clamp nonsensical numerics (`NaN`, `Infinity`, negative where meaningless) rather than rendering them; `textContent`-only (the frozen renderer already is — do NOT introduce `innerHTML`). A missing/partial `windows` object degrades to all-`no-data`, never a crash.

- [x] **Task 2 — Delta computation: 7d vs 30d (D1)** (AC: 2) — *tests-first*
  - [x] In the mapper, compute each cell's `delta` by comparing the 7d value to the 30d value of the same metric (use `per_day` for deployment_frequency so the rate is window-length-normalized; raw `value` for the median/mean/ratio metrics). Populate `delta.text` with the honest raw magnitude + basis, e.g. `"−0.3h vs 30d"` / `"+0.6/day vs 30d"`. The frozen `formatDeltaLine` prepends the arrow (`↑`/`↓`/`—`) + a `+` for `up`. [kpi-strip.js:17-22,111-120]
  - [x] **No-baseline / no-delta paths:** if the 7d metric is `ok` but the 30d metric is `insufficient_data`, render the 7d value with a **neutral** delta (`direction:"neutral"`, text e.g. "no 30d baseline") — do NOT invent a comparison. If 7d itself is `insufficient_data`, the cell is already `no-data` (Task 1) and carries no delta.

- [x] **Task 3 — Per-metric sentiment coloring (D3 — closes the deferred 5.7 review item)** (AC: 2) — *tests-first*
  - [x] The mapper owns a sentiment map: `HIGHER_IS_BETTER = {deployment_frequency}`, `LOWER_IS_BETTER = {lead_time, change_failure_rate, mttr}`. Compute the **raw numeric direction** (7d vs 30d), then translate to **sentiment** and set `delta.direction` accordingly: an *improvement* → `"up"` (renders `--green`), a *regression* → `"down"` (renders `--red`), no change/no baseline → `"neutral"` (`--ink-mute`). The frozen renderer colors purely off `delta.direction` (`--up`→green, `--down`→red). [kpi-strip.css:87-98]
  - [x] Concretely: `mttr` dropping 2.0h→1.2h is an IMPROVEMENT → `direction:"up"` (green) even though the number went down; `deployment_frequency` 0.4→0.6/day is an improvement → `"up"` (green). This inverts the raw up=green/down=red rule of 5.7 for the three lower-is-better metrics (the exact review item 5.7 deferred to 5.17). Playwright-assert the RENDERED delta class per metric (`.kpi-strip__delta--up` shows for an mttr decrease).

- [x] **Task 4 — Live poller + lifecycle (D4, re-entrancy + AbortController + loading state)** (AC: 1) — *tests-first*
  - [x] In `kpi-strip-live.js` add `pollDoraSnapshot({url="/api/dora", fetchFn=fetch, signal})` (guard `response.ok`, `.json()`, then `mapDoraToCells`) and `startKpiStripLivePoller(host, {url, intervalMs, fetchFn})` returning a `dispose` fn — mirror `startActivityFeedLivePoller` / `resume-card-live.js` exactly: `inFlight` re-entrancy guard, `disposed` flag, an `AbortController` aborted on teardown, **silent `catch` keeping last-known-good render** on a transient/aborted poll. Cadence `POLL_INTERVAL_MS = 3_000` (`setInterval`). `fetchFn`/`url`/`intervalMs` are injectable for tests. [activity-feed.js:213-266; resume-card-live.js]
  - [x] Render a neutral **loading** state on connect before the first successful poll (5 placeholder `no-data`/blank cells) so the strip is never blank; do not announce it as data.
  - [x] **Unchanged-signature guard (NFR-PERF-4):** compute a signature over the mapped cells; on an unchanged poll, refresh only the freshness footer in place — do NOT tear down the strip every 3s. [resume-card-live.js tick loop]
  - [x] Stash `host._stopPoller = dispose` and call it from the base element's `disconnectedCallback` (add a minimal `disconnectedCallback` to `kpi-strip.js` that invokes `this._stopPoller?.()` — the ONLY permitted edit to the frozen base; the base must NOT `import` the live module, to avoid an ES-module cycle). [kpi-strip.js:183-196]
  - [x] **Note — no ETag/304 on `/api/dora`** (it is a computed body, not file-streamed): the poller cannot do conditional GETs; freshness is bounded by the server-side 30s cache. Do not add `If-None-Match`. [routes/dora.py:85-92; etag.py]
  - [x] **Backend-silence / disconnection is OUT OF SCOPE** — a failing poll silently keeps last-good and self-heals next tick. The explicit "disconnected" surface (amber outline, banner) is **Story 5.20**. Do NOT build it here.

- [x] **Task 5 — Mount `<kpi-strip>` on the real dashboard shell + live fixture** (AC: 1) — *tests-first*
  - [x] Mount `<kpi-strip>` (live data source) in the real dashboard shell so "When the KPI Strip renders" holds end-to-end — `src/sdlc/dashboard/static/index.html` currently does NOT mount it. Follow the mount pattern the shipped sibling swaps (5.16 activity-feed / 5.18 resume-card) used for the real shell; verify their `index.html` wiring and match it (e.g. a `data-source="live"` attribute branch in `connectedCallback` that calls `startKpiStripLivePoller`, else `SYNTHETIC_KPI_FIXTURE`). [kpi-strip.js:183-196; index.html]
  - [x] Create `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip-live.fixture.html` mirroring `resume-card-live.fixture.html` / `activity-feed-live.fixture.html`: mounts the host, imports `startKpiStripLivePoller`, reads a `?intervalMs=` query-param override for fast deterministic polling in Playwright.
  - [x] Add both new static files (`kpi-strip-live.js`, `kpi-strip-live.fixture.html`) to the `force-include` block. [pyproject.toml:~139]

- [x] **Task 6 — Tests (RED first) + quality gate + freeze** (AC: 1, 2, 3) — *tests-first*
  - [x] **`tests/unit/dashboard/test_kpi_strip_live_source.py`** (static-analysis contract, "PAT-3", mirror `test_resume_card_live_source.py` / `test_backlog_tree_live_source.py`) — greps the poller source (does NOT execute JS): asserts it reads `/api/dora` (NOT re-parsing state/wire files), imports `renderKpiStrip` from the base module, defines `POLL_INTERVAL_MS = 3_000` + `setInterval`, has `inFlight` + `AbortController` + `.abort()`, sets `host._stopPoller`, has a loading state, and that the base module does NOT import the live module (no cycle).
  - [x] **`tests/integration/test_dashboard_kpi_strip_live.py`** (Playwright behavioral witness — the mapper/delta/sentiment/n-a RENDER assertions, since JS logic is only testable here). Serve a real dashboard on a free port (mirror `test_dashboard_resume_card_live.py`: module-scoped `_browser`, `wait_until="load"` NOT `networkidle`, `?intervalMs=150`). Cover: (1) all-ok payload → 5 cells populated with the right values+units; (2) an `insufficient_data` metric → that cell shows `n/a` real-text + reason; (3) **sentiment**: an mttr/lead_time/CFR *decrease* renders `.kpi-strip__delta--up` (green), a deployment_frequency *increase* renders `--up`; a regression renders `--down`; (4) no-30d-baseline → neutral delta; (5) poll update within one cycle without teardown of unchanged cells; (6) in-flight guard (`maxConcurrent == 1`) + AbortController fires on disconnect; (7) hostile/NaN numeric renders inert (`childElementCount == 0`, no injected nodes).
  - [x] **Keep the frozen 5.7 contract green:** do NOT modify `SYNTHETIC_KPI_FIXTURE`, the render exports, or `kpi-strip.css` — the 19 tests in `tests/unit/dashboard/test_kpi_strip_fixture.py` (exactly-5-cells, all-three-states-present, exports, no-data/stale/delta contracts, CSS tokens) MUST stay green. The `stale` state stays in the synthetic fixture (for the contract) but is NOT produced by the real mapper. [test_kpi_strip_fixture.py:85,182]
  - [x] **Frontend gates (Decision D2 of the DAG):** `check_dashboard_no_framework.py` (DD-08 — stay vanilla JS, no fetch-framework import), `check_dashboard_forbidden_patterns.py` (no skeleton/shimmer loader, no toast, no modal, no client routing), `check_dashboard_no_data_theme.py` (DD-09), `check_dashboard_no_external_fonts.py` (DD-10); `check_dashboard_color_only.py` **only if** you touch HTML with dots; stylelint + `check_dashboard_motion.py` (DD-14 no `transition:`) **only if** you touch CSS (this swap should touch NO CSS). Axe-core Level-A (`tests/dashboard/test_a11y_axe.py`, blocking tags `wcag2a`+`wcag21a` = WCAG 2.2 Level A) must be zero-violation on the mounted strip.
  - [x] **Python gate + freeze:** the swap adds NO `src/sdlc/dashboard/*.py` (route exists from 5.13) — if you add none, `check_module_boundaries.py` is unaffected; if you DO add a Python helper, it must respect `dashboard → {state, journal, telemetry, …}` one-way (never `dashboard → cli`) and the 400-LOC/file cap. Run the full `uv run pytest` (coverage ≥ 87%, ADR-004 amendment), `ruff check`/`ruff format --check`, `mypy --strict src/`, `mkdocs build --strict`, `python scripts/freeze_wireformat_snapshots.py --check` → **freeze stays 7/7** (`/api/dora` is internal, no StrictModel, no snapshot; DAG Decision D1).

## Dev Notes

### Wave-boundary verification (5B data-readiness) — READ FIRST

The `E2B → 5.13 → 5.17` chain is already satisfied — this is a **pure frontend swap onto an existing real endpoint**, unlike 5.18 (which had to build a producer). Verified against the live codebase:

- **`/api/dora` EXISTS and is real** — `routes/dora.py::register_dora_route` registers `GET /api/dora` → `handle_dora`, body = `json.dumps(compute_dora_window(...), sort_keys=True, separators=(",",":"))` behind a 30s `_DoraCache`. Compute is in `telemetry/dora.py::compute_dora_window` (pure), reading `agent_runs.jsonl` (2B.10) via `telemetry/runs.py::iter_agent_run_records` + git log via `cli/_git_dora.py` — **through the reader seam** (`dashboard → telemetry`, one-way). 5.13 is `done`+merged. **⇒ 5.17 does NOT touch the backend.** [routes/dora.py:39-92; telemetry/dora.py; telemetry/runs.py]
- **The KPI Strip renderer EXISTS and is frozen** — `<kpi-strip>` custom element + `renderKpiStrip/renderKpiCell/renderNoDataValue/renderStaleDelta/formatDeltaLine/resolveState` + `SYNTHETIC_KPI_FIXTURE`, all in `kpi-strip.js`, with 19 static-contract tests. 5.7 is `done`+merged. **⇒ 5.17 REUSES the renderer, swaps only the data source.** [kpi-strip.js; test_kpi_strip_fixture.py]
- **The literal AC over-specifies vs the real contract** (drives D1/D2): no preceding-7d window, no delta field, no 5th/`backlog_health` metric, no staleness timestamp in `/api/dora`. Reconcile via the Decisions below **before** coding, and record the picks in the PR Change Log.

### The real `/api/dora` envelope (the data 5.17 maps from) — verbatim shape

```jsonc
{
  "schema_version": 1,                          // int, always 1
  "windows": {
    "7d":  { /* 4 metric objects, identical shape to 30d */ },
    "30d": {
      "deployment_frequency": { "data_status": "ok"|"insufficient_data", "value": int|null,   "unit": "deploys_per_window", "per_day": number|null },
      "lead_time":            { "data_status": ...,                       "value": number|null, "unit": "hours" },
      "change_failure_rate":  { "data_status": ...,                       "value": number|null, "unit": "ratio", "failed_count": int|null, "total_count": int|null },
      "mttr":                 { "data_status": ...,                       "value": number|null, "unit": "hours", "recovery_count": int|null }
    }
  }
}
```

- `data_status ∈ {"ok","insufficient_data"}`. On `insufficient_data`, `value` **and every detail field** (`per_day`, `failed_count`, `total_count`, `recovery_count`) become `null`; `unit` stays. 7d and 30d are independent; metrics within a window can mix statuses — decide **each cell** against its own `7d.<metric>.data_status`.
- **No `delta`, no preceding window, no timestamp/staleness, no 5th metric.** Access as `payload.windows["7d"].deployment_frequency.per_day`, etc.
- Units: deployment_frequency `value`=raw window count (use `per_day` for the rate); lead_time/mttr `value`=hours (float); change_failure_rate `value`=ratio in `[0,1]`. lead_time here is author→land latency (near-zero outside rebase), NOT idea→prod — keep the 5.7 label, don't over-claim in copy.
[Source: routes/dora.py; telemetry/dora.py:137-141,236-249; docs/api/dora-schema.json; tests/unit/dashboard/test_dora_backend.py]

### Frozen foundation to consume (do NOT redefine — 5.7 + 5.13 froze these)

```text
5.7 KPI-strip seam (REUSE, feed it mapped cells — do NOT edit):
  kpi-strip.js:
    - renderKpiStrip(root, cells)      :126-146  — clears root, builds <section>, slices/pads to EXACTLY 5 cells
    - renderKpiCell(cell, index)       :72-124   — one cell: no-data early-return | <dt>label/<dd>value | delta
    - renderNoDataValue(dl, {...})     :24-42    — renders "n/a" REAL TEXT + aria-describedby reason (THE n/a path)
    - formatDeltaLine(direction,text)  :17-22    — {up:"↑",down:"↓",neutral:"—"}, +prefix for up
    - resolveState(raw)                :12-16    — normalizes state → default|no-data|stale (safe fallback)
    - SYNTHETIC_KPI_FIXTURE            :147-181  — KEEP (19 contract tests pin it); real cells come from the mapper, NOT this
    - class KpiStrip.connectedCallback :183-196  — THE MOUNT POINT (swap: live source vs SYNTHETIC_KPI_FIXTURE)
  kpi-strip.css                        — do NOT touch (delta colors --up→--green / --down→--red / --neutral→--ink-mute)

  Renderer cell field contract the mapper must PRODUCE (per cell):
    default:  { label, state:"default", value:"1.2", unit:"hrs", delta:{ direction:"up"|"down"|"neutral", text:"−0.3 vs 30d" } }
    no-data:  { label, state:"no-data", noDataReason:"…" }        // 5.17 uses default + no-data ONLY
    (stale:   { …, staleAt } — NOT produced by 5.17; /api/dora has no timestamp)

Real upstream (READ-ONLY — already shipped by 5.13; do NOT edit):
  /api/dora route              routes/dora.py:39-92        (GET-only, 30s cache, NO ETag/304, internal schema)
  DORA compute (pure)          telemetry/dora.py           (insufficient_data via _metric_insufficient)
  documentary schema           docs/api/dora-schema.json   (NOT a frozen wire contract → freeze stays 7/7)

Established live-poller precedent to MIRROR (do NOT invent a new shape):
  resume-card-live.js / backlog-tree-live.js / phase-tracker-live.js  — pollXSnapshot + startXLivePoller + dispose
  activity-feed.js:213-266                                            — inFlight/disposed/AbortController/silent-catch canon
```
[Source: kpi-strip.js; kpi-strip.css:87-98; routes/dora.py; telemetry/dora.py; resume-card-live.js; activity-feed.js:213-266]

### Locked design decisions (verbatim — these govern the story)

- **§6.3 KPI Strip (5.7 anatomy, inherited).** One strip per dashboard, immediately below masthead. Five even cells, `role="region"` `aria-label="Project KPIs"`, semantic `<dl>`/`<dt>`/`<dd>`. Value = Fraunces 44px (`--type-display-hero`), label = mono 10px uppercase, delta = `--type-mono-data` with up/down/neutral color. Variants: *"None — differentiation is by content, not visual variant."* [Source: ux-design-specification.md §6.3:1077-1111]
- **Anti-cynicism no-data rule.** *"KPI strip is always full and current; if a metric cannot be computed, display `n/a` with the reason on hover — never a blank cell."* The `n/a` is **real text, not a glyph**, reason in `aria-describedby`. [Source: ux-design-specification.md §2.5:233, §8.4:1742-1747]
- **Color-never-only-signal (WCAG).** The delta up/down MUST carry an adjacent text arrow/sign, not color alone — `formatDeltaLine` already embeds `↑`/`↓`/`—`; preserve it. [Source: ux-design-specification.md §8.4:1762; §3.1]
- **DORA snapshot content.** *"KPI strip — DORA snapshot (deployment frequency, lead time, change failure rate, MTTR) confirms broad health."* [Source: ux-design-specification.md:824]
- **Custom-element variance (5.7 precedent).** ux:338 said "no Web Components in v1", but 5.7 (done) implemented a `<kpi-strip>` custom element — DD-08 no-framework allows vanilla custom elements. 5.17 follows 5.7's shipped precedent; this is a settled variance, not a 5.17 decision. [Source: kpi-strip.js; ux:338]

### Decisions (resolve in Task 0 per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — delta basis: 7d-vs-30d, not 7d-vs-preceding-7d (HIGH / AC-vs-data).** `/api/dora` emits only current-7d + current-30d — no preceding-7d, no delta field (verified). Options: *(a)* headline value = **7d** window; delta line = **signed change of 7d vs 30d** ("recent vs 30-day baseline"), fully frontend-derivable from the existing payload, **no backend change, freeze stays 7/7**; *(b)* extend `/api/dora` (5.13's engine + `docs/api/dora-schema.json`) to emit a preceding-7d window or a precomputed delta block — enables the literal AC wording but **expands scope into a done story's surface** + adds compute/perf/tests (still internal-schema, but a real backend change); *(c)* drop delta lines — **REJECTED** (AC requires delta lines). ***Recommendation (a)*** — the AC parenthetical "(or 30d vs preceding 30d)" already signals the comparison basis is flexible; 7d-vs-30d is the honest, data-available signal. Raise as a D-label; PO/architect ratify before branching.

**D2 — 5th cell / project KPI (HIGH / AC-vs-data).** `/api/dora` serves only the 4 DORA metrics; `backlog_health` is nowhere in code (epics.md prose only, hedged "*like* backlog_health"); the strip is pinned to exactly 5 cells. Options: *(a)* render the **4 real DORA cells** + a **5th documented `no-data` placeholder** ("n/a", reason "Project KPI not yet wired") — keeps 5.17 scoped to its only two deps (5.7 + 5.13), satisfies the exactly-5-cells contract, defers the real 5th-KPI source to a follow-up story; *(b)* source a real 5th KPI (e.g. `backlog_health`) from another endpoint/computation — **expands deps beyond 5.7+5.13**, needs a KPI definition + endpoint that do not exist, more risk; *(c)* render only 4 cells — **REJECTED** (breaks `test_kpi_strip_five_cells_in_fixture_data`). ***Recommendation (a)*** — 4 real + 1 honest placeholder; log the deferred real-5th-KPI in `deferred-work.md`. Raise as a D-label.

**D3 — per-metric sentiment (MED / correctness — the deferred 5.7 review item).** 5.7's raw rule is up=green/down=red, but lead_time / change_failure_rate / mttr are **lower-is-better** (a decrease is an improvement → must be green); deployment_frequency is higher-is-better. Options: *(a)* the mapper owns `HIGHER_IS_BETTER={deployment_frequency}` / `LOWER_IS_BETTER={lead_time,change_failure_rate,mttr}` and sets the renderer's `delta.direction` to **sentiment** (improvement→`"up"`/green, regression→`"down"`/red, none→`"neutral"`) — closes the 5.7 deferred item; *(b)* keep raw numeric direction — **REJECTED** (renders improvements as red, the exact defect 5.7 flagged). ***Recommendation (a)*** — this is a correctness requirement, not really optional; Playwright-assert the rendered delta class per metric.

**D4 — poller file convention (LOW / mirror precedent).** *(a)* new `kpi-strip-live.js` poller importing the frozen `renderKpiStrip`, base never imports live (no ES cycle) — mirrors 5.18/5.15/5.14 `*-live.js`, keeps the 5.7 base + 19 contract tests untouched; *(b)* inline the poller into `kpi-strip.js` (activity-feed style) — **rejected**: risks the frozen contract tests + couples synthetic/live. ***Recommendation (a)***.

### Anti-patterns / regressions to prevent (harvested from 5.16 + 5.18 reviews)

1. **XSS / inert render:** `textContent` only, never `innerHTML`; a hostile/NaN numeric renders inert (`childElementCount == 0`). Playwright-witness it.
2. **Poll re-entrancy + AbortController:** `inFlight` guard so a slow poll never overlaps the next tick; a real `AbortController` aborted on `disconnectedCallback` so a late resolve can't mutate a detached strip (Playwright: `maxConcurrent == 1`, `signal.aborted`).
3. **No teardown on unchanged content (NFR-PERF-4):** unchanged-signature guard; on no-change, refresh only the freshness footer in place — don't rebuild the strip every 3s.
4. **No false "success"/announcement on the loading window:** the pre-first-poll loading state is not data; don't announce it.
5. **Frozen-twin regression:** do NOT edit `SYNTHETIC_KPI_FIXTURE`, the render exports, or `kpi-strip.css` — the 19 contract tests must stay green.
6. **Scope discipline (boundary):** build ONLY the KPI-strip swap. Do NOT build STOP banner (5.19), disconnection surface (5.20), degradation banner (5.21). `dashboard → cli` is forbidden; `dashboard → state/journal/telemetry` one-way only. Never construct/import the frozen `contracts.*` models from `dashboard/` (validate against them only from the test side). Zero `/api/dora` shape edit → freeze stays 7/7.
7. **404/degrade-not-crash on malformed payload:** a missing/partial `windows` object degrades to all-`no-data`, never a 500 or a JS throw that blanks the strip.

### Testing standards summary

- **CI test command is `uv run pytest`** over ALL `tests/` (coverage `--cov-fail-under=87`, ADR-004 amendment). Do NOT use a path/marker subset as the gate — subsets compute coverage over only the selected tests and report a **false pass** (project memory: "subsets lie"). [pyproject.toml:315-335; CONTRIBUTING §1]
- **JS behavior is tested via Playwright** (`tests/integration/test_dashboard_kpi_strip_live.py`) — module-scoped browser, `wait_until="load"` (NOT `networkidle` — the live poller never idles), `?intervalMs=150` to speed polls; plus the **static-analysis source contract** (`tests/unit/dashboard/test_kpi_strip_live_source.py`, greps source, does not execute JS). Mirror `test_dashboard_resume_card_live.py` + `test_resume_card_live_source.py`.
- **a11y:** axe-core Level-A (`tests/dashboard/test_a11y_axe.py`) zero WCAG 2.2 Level-A violations on the mounted strip (blocking tags `wcag2a`+`wcag21a`; there is no `wcag22a` tag in axe-core). Keep the frozen `<dl>` semantics + `n/a` real-text + `aria-describedby`.
- **AAA structure, behavior-named tests.** Budget for the 400-LOC/file pre-commit cap — split the Playwright witness into a `_live.py` sibling if it grows (5.16 had to).

### Commit ceremony (CONTRIBUTING §2/§3/§4 — mirror 5.18)

1. Branch `epic-5/5-17-kpi-strip-real-dora` off up-to-date `main` (worktree-per-story; rebase, not merge — linear history; rerun the full gate after any rebase).
2. `test(5.17): RED contracts for /api/dora consumption + kpi-strip real-data swap` — ALL test files first, failing, **zero production code** (keep review keywords OUT of this commit).
3. `feat(5.17): real kpi-strip 7d/30d DORA via /api/dora` — mapper + poller + fixture + base `disconnectedCallback` hook + index.html mount + `pyproject.toml` force-include; body enumerates D1–D4 resolutions; ends "Zero /api/dora shape edit → freeze stays 7/7." (keep review keywords OUT).
4. Run `bmad-code-review` (fresh context, 3 adversarial layers). Apply patches TDD-first.
5. `docs(5.17): bmad-code-review findings + deferred-work + sprint tracking [fresh-context-review]` — the `[fresh-context-review]` tag goes ONLY on this docs-only commit; it must stage NO `src/` files (`check_fresh_context_review_tag.py`).
6. Merge to `main`; verify **CI `ci` workflow green** (pushing `main` bypasses the 10 required checks — re-verify after; the `docs`/Pages workflow being red is pre-existing infra, NOT a regression). Judge green-main by the `ci` workflow only.
7. `chore(5.17): close out story 5.17 - status -> done (merged, CI green)` — flip `Status: review → done` **POST-merge only** (merged-before-done gate R2, unwaivable; a per-story `feat(5.17)`/`fix(5.17)` commit must be reachable from HEAD — do NOT squash under a coarse `feat(epic-5)` scope). Update `sprint-status.yaml` `5-17-…: done`.

### Project Structure Notes

- **NEW:** `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip-live.js`, `…/kpi-strip-live.fixture.html`, `tests/unit/dashboard/test_kpi_strip_live_source.py`, `tests/integration/test_dashboard_kpi_strip_live.py`.
- **MODIFIED (minimal):** `kpi-strip.js` (add `disconnectedCallback` + live-source mount branch only — renderer + fixture + exports frozen), `src/sdlc/dashboard/static/index.html` (mount `<kpi-strip>`), `pyproject.toml` (force-include), `deferred-work.md` (append real-5th-KPI defer + any long-value/keyboard a11y → 5.22), `sprint-status.yaml`.
- **FROZEN — do NOT modify:** `renderKpiStrip`/`renderKpiCell`/`renderNoDataValue`/`renderStaleDelta`/`formatDeltaLine`/`resolveState`, `SYNTHETIC_KPI_FIXTURE`, `kpi-strip.css`, `routes/dora.py`, `telemetry/dora.py`, `docs/api/dora-schema.json`, the 7 `tests/contract_snapshots/v1/*` snapshots.
- **Variance:** `/api/dora` route already exists (5.13) — unlike 5.18, this swap adds **no new Python route** (and likely no `src/**/*.py` at all beyond packaging), so `check_module_boundaries.py` is unaffected unless a Python helper is added.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-5.17 (lines 2782–2795)] — AC verbatim; the "one project KPI like backlog_health" hedge (D2)
- [Source: docs/sprints/epic-5-dag.md §2:141-143, §3:216, §5:295, §6:330] — L7 layer, edges 5.7→5.17 / 5.13→5.17, worktree, width-1; §2:200-202 (5.22 re-scans the real-data surface)
- [Source: docs/sprints/epic-5-dag.md Decision D1 (lines 360–376)] — `/api/dora` is INTERNAL/documentary, no ADR-024 contract → freeze stays 7/7
- [Source: src/sdlc/dashboard/static/components/kpi-strip/kpi-strip.js] — frozen renderer seam + `SYNTHETIC_KPI_FIXTURE` + mount point (:183-196)
- [Source: src/sdlc/dashboard/routes/dora.py; src/sdlc/telemetry/dora.py; docs/api/dora-schema.json] — the real `/api/dora` envelope + insufficient-data semantics + 30s cache/no-ETag
- [Source: _bmad-output/implementation-artifacts/5-7-kpi-strip-kpi-value-cell.md] — 5.7 File List; deferred DORA-delta-sentiment review item (→ D3); exactly-5-cells contract
- [Source: _bmad-output/implementation-artifacts/5-18-…md; 5-16-…md] — the real-data-swap pattern: poller shape, RED-contract test layout, commit ceremony, anti-pattern review findings
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.3:1077-1111, §2.5:233, §8.4:1742-1747,1762, :824] — KPI strip anatomy, no-data anti-cynicism rule, color-never-only-signal, DORA content
- [Source: CONTRIBUTING.md §1/§2/§3/§4/§5; pyproject.toml:315-335; .github/workflows/ci.yml] — quality gate, TDD-first, worktree, chunked review, coverage floor 87

## Dev Agent Record

### Agent Model Used

Composer

### Debug Log References

- Wave-boundary: `TestSchemaConformance` green on `/api/dora`
- Decisions ratified: D1(a) 7d headline + 7d-vs-30d delta; D2(a) 4 DORA + placeholder 5th; D3(a) per-metric sentiment; D4(a) `kpi-strip-live.js` poller
- Full gate: `uv run pytest` → 4290 passed, coverage 88.61%; freeze 7/7

### Completion Notes List

- Implemented `kpi-strip-live.js` with `mapDoraToCells`, 7d-vs-30d deltas, per-metric sentiment (closes 5.7 DEF-4), 3s poller with inFlight/AbortController/unchanged-signature guard
- Minimal `kpi-strip.js` edits: `data-source="live"` early-return + `disconnectedCallback` for `_stopPoller`
- Mounted live `<kpi-strip>` on `index.html`; added Playwright + static-analysis test suites (11 integration [7 core + 4 hardening] + 10 unit)
- Deferred real 5th project KPI to `deferred-work.md` (D2a)
- Close-out ceremony: split the Playwright witness into `test_dashboard_kpi_strip_live.py` (core) + `test_dashboard_kpi_strip_live_hardening.py` (lifecycle) + `_kpi_strip_live_support.py` (shared) to satisfy the 400-LOC/file cap the untracked file had exceeded (446→cap) — as the story's own testing-standards note anticipated.

### File List

- `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip-live.js` (new)
- `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip-live.fixture.html` (new)
- `src/sdlc/dashboard/static/components/kpi-strip/kpi-strip.js` (modified)
- `src/sdlc/dashboard/static/index.html` (modified)
- `pyproject.toml` (modified)
- `tests/unit/dashboard/test_kpi_strip_live_source.py` (new)
- `tests/integration/test_dashboard_kpi_strip_live.py` (new — core AC witnesses)
- `tests/integration/test_dashboard_kpi_strip_live_hardening.py` (new — lifecycle/hardening witnesses; split from the core file to stay under the 400-LOC cap)
- `tests/integration/_kpi_strip_live_support.py` (new — shared payload builders + selectors for the two witness modules)
- `_bmad-output/implementation-artifacts/5-17-kpi-strip-rendering-real-dora-7d-30d.md` (this story file)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modified)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)

### Change Log

- 2026-07-06: Story 5.17 implementation — real KPI strip consumes `/api/dora` (D1(a) 7d-vs-30d delta, D2(a) 4+placeholder, D3(a) sentiment, D4(a) live poller). Zero `/api/dora` shape edit → freeze stays 7/7.

### Review Findings

_`bmad-code-review` 2026-07-06 — 3 adversarial layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor), all completed, none failed/empty. Triage: **1 decision-needed, 4 patch, 4 defer, 2 dismissed**. The top finding (garbled `+-` delta) was independently surfaced by 2 layers and confirmed by direct source verification._

_**Resolution (2026-07-06):** decision-needed resolved → option 1 (1-decimal deploy freq). **All 5 patches applied + verified:** `formatDeltaMagnitude` now emits absolute magnitude (P1), `formatDisplayValue` uses `formatNumber` for deploy-freq (P4), dead ternary removed (P5), the no-teardown test asserts a real DOM marker (P2), the hostile-numeric test drives the mapper's coercion via a valid-JSON negative (P3) + a new `…delta_has_no_double_sign` witness added. Full gate `uv run pytest` → **4291 passed / 4 skipped / 1 xfailed, coverage 88.60% ≥ 87**; wire-format freeze **7/7**; ruff clean. Status stays `review` — flip to `done` only POST-merge per CONTRIBUTING R2 (merged-before-done gate) + story §7 ceremony._

- [x] [Review][Patch] MEDIUM — `deployment_frequency` sub-1/day rate collapses hero value to "0" [kpi-strip-live.js:68-71] — `formatDisplayValue` returns `String(Math.round(per_day))` (spec-faithful, Task 1 said `round(per_day)`), so a team deploying < ~0.5/day (≈ 3.5×/week) shows a hero of **"0 /day"** while the 7d-vs-30d delta still computes a colored non-zero change. **Resolved (Decision → option 1, 1-decimal):** change `formatDisplayValue` for `deployment_frequency` from `String(Math.round(value))` to `formatNumber(value)` so `per_day` 0.33 renders `0.3 /day` — consistent with the delta line's own `formatNumber`.

- [x] [Review][Patch] HIGH — Lower-is-better *improvements* render a garbled `↑ +-0.8h vs 30d` delta [kpi-strip-live.js:112-125 → frozen kpi-strip.js:20] — `formatDeltaMagnitude` emits a raw-signed negative (`"-0.8h"`) on a decrease while `sentimentDirection` sets `delta.direction="up"`; the frozen `formatDeltaLine` force-prepends `+` when `direction==="up"` and text doesn't start with `+` → double sign `+-`. Hits the headline good-news path for `lead_time`/`change_failure_rate`/`mttr`; **untested** (D3 tests assert only the `--up`/`--down` CSS class, never `textContent`). Fix: emit the **absolute** magnitude (drop the raw sign) so arrow+`+` compose cleanly (`↑ +0.8h vs 30d` improvement / `↓ 0.8h vs 30d` regression); add a Playwright assertion on delta `textContent` (no `+-`), covering `lead_time` + `change_failure_rate` too (closes the D3 coverage gap).
- [x] [Review][Patch] MEDIUM — `test_kpi_strip_unchanged_poll_does_not_teardown_cells` is vacuous [test_dashboard_kpi_strip_live.py:329-338] — `page.eval_on_selector(sel, "el => el")` JSON-serializes a DOM node to `{}`, so `assert first_hero == same_hero` is `{} == {}` → always true; a regression that rebuilt the strip every 3s would still pass. The unchanged-signature guard itself is correct (kpi-strip-live.js:228) — only the NFR-PERF-4 test can't catch its removal. Fix: tag the node on first render (`el.dataset.marker=…`) and assert it survives an unchanged poll, or `evaluate_handle` + `a === b`.
- [x] [Review][Patch] MEDIUM — `test_kpi_strip_hostile_nan_renders_inert_text` exercises the wrong path [test_dashboard_kpi_strip_live.py:407-416; _mock_dora_route:157] — `json.dumps(float("nan"))` emits the bare token `NaN` (invalid JSON) → `response.json()` throws → poller stays on `LOADING_CELLS`; the mapper's `isValidNonNegative`/`isValidRatio` coercion is never reached and the assertion passes on the *loading placeholder*, not the NaN cell. Fix: drive the mapper with a parseable-but-nonsensical value (negative `-999`, wrong-type string) to actually hit the coercion guards; optionally add a separate JSON-parse-failure→keep-last-good test.
- [x] [Review][Patch] LOW — Dead ternary in `formatNumber` [kpi-strip-live.js:52] — `Number.isInteger(rounded) ? String(rounded) : String(rounded)` — both branches identical; collapse to `return String(rounded);`.

- [x] [Review][Defer] LOW — Colored "+0"/"−0" delta when \|Δ\| rounds to zero at display precision [kpi-strip-live.js:92,114] — deferred, pre-existing (needs per-metric neutrality threshold; see deferred-work DEF-cr-1)
- [x] [Review][Defer] LOW — Live `<kpi-strip>` never restarts its poller on DOM re-attach (analog of resume-card DEF-cr-4) [kpi-strip.js:44-48,57-62] — deferred, pre-existing (mount-once shell; see deferred-work DEF-cr-2)
- [x] [Review][Defer] LOW — `startKpiStripLivePoller` not idempotent; double-start leaks the first interval [kpi-strip-live.js:251] — deferred, pre-existing (started once by index.html today; see deferred-work DEF-cr-3)
- [x] [Review][Defer] LOW — Live host stays permanently blank if `kpi-strip-live.js` fails to import [kpi-strip.js:44-48; index.html] — deferred, pre-existing (routed to Story 5.20 error surface; see deferred-work DEF-cr-4)

_Dismissed as noise: (1) empty/array `windows` reports "Insufficient data" rather than "missing windows" — degrades safely to all-`no-data`; (2) `schema_version` never validated before reading `windows` — server frozen at v1, forward-compat only (YAGNI)._
