# Story 5.16: Activity Feed Reading Real `agent_runs.jsonl`

Status: review

<!-- Layer: Epic-5 DAG L6 (5B). L6 = {5.13, 5.14, 5.15, 5.16, 5.18}; **authoritative L6 split (§3): batch 1 = {5.14, 5.15, 5.16, 5.18}** (the four independent 1:1 real-data swaps, run in parallel, cap 4), batch 2 = {5.13} alone (rebases on batch 1). 5.16 is in **batch 1**. Worktree: `epic-5/5-16-activity-feed-real-runs`, Owner Sally. Depends on **5.11** (twin — the synthetic Activity Feed + incremental-prepend render SEAM, done+merged) + external wave gate **E2B → 5.16** (Story 2B.10 `agent_runs.jsonl` Phase-3 specialists — `2b-10-author-phase-3-specialists-tdd-pipeline: done`, sprint-status.yaml:200). This is a **thin 1:1 real-data swap onto its 5A twin** (DAG §3:241): swap the SYNTHETIC feed source for the real `agent_runs.jsonl` read seam; do NOT redesign the component. **NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A** (epic-5 in-progress, cleared at 5.1). a11y coverage lands via the 5.11 twin through 5.12 (done) + the terminal gate 5.22. **DISTINGUISHING REQUIREMENT (DAG §5:294, Alice review):** `agent_runs.jsonl` is UNTRUSTED file content → data-validation is a first-class concern (malformed/partial/truncated JSONL must not crash or XSS the feed). Zero wire-format change (`agent_runs.jsonl` is a private internal model, NOT an ADR-024 frozen contract — runs.py:1-17) → freeze stays 7/7. -->

## Story

As Quan reviewing recent activity,
I want the Activity Feed (Story 5.11 component) reading the real `agent_runs.jsonl` (Story 2B.10 Phase-3 specialists populating it),
So that the last-50 view shows actual agent dispatches with full metadata (FR42, UX-DR8, §6.8, NFR-OBS-2, NFR-PERF-4).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.16, lines 2763–2780).

**Given** Epic 2B specialists generating `agent_runs.jsonl`
**When** the Activity Feed renders
**Then** entries show real ts, agent name, target id, stage, outcome, duration_ms
**And** entries are sorted reverse-chronological (most recent first)
**And** the feed truncates to last 50 entries

**Given** a new agent run completes
**When** the dashboard polls (3 s)
**Then** the new entry appears at the top of the feed
**And** unaffected entries do not re-render (NFR-PERF-4: only changed sections re-render)

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the **reverse-chronological order + last-50 truncation** (AC1), the **poll-prepends-newest / incremental-render** (AC2), and the **malformed-JSONL resilience** (data-validation) are all deterministic, testable behavior → tests-first. Mirror the 5.11 two-tier pattern: **static-analysis contracts** over `tests/unit/dashboard/test_tabs_activity_feed_fixture.py` (updated for the real field names) + a **Python unit suite for the new reader/route** (`tests/unit/telemetry/` + `tests/unit/dashboard/`) asserting malformed-line-skip / reverse-chron / last-50 / field-projection, PLUS a **Playwright behavioral witness** extending `tests/integration/test_dashboard_activity_feed_empty_state.py` (do NOT regress its newest-on-top + evict-oldest assertions). Resolve Decisions D1–D4 in **Task 0** BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (real→display field mapping / name drift) + D2 (feed field-count reconcile: AC's 6th field `stage` vs the 5.11 synthetic 5-field row) + D3 (outcome vocabulary: real `{success, failed}` + unknown-outcome neutral mapping) + D4 (reader/route seam location under the `dashboard → telemetry` one-way module edge) BEFORE coding** (AC: 1, 2)
  - [x] Record the picks in the PR Change Log (CONTRIBUTING §5). Verify the wave boundary once more: `agent_runs.jsonl`'s real record shape is `src/sdlc/telemetry/runs.py::_AgentRunLine` (2B.10 done+merged) — pin the exact persisted field names below, NOT the AC's logical names.

- [x] **Task 1 — Reader seam: read `agent_runs.jsonl` through `telemetry/`, never re-parse in the dashboard (D4)** (AC: 1) — *tests-first*
  - [x] The `dashboard` package MUST NOT import `sdlc.cli._agent_runs` — `cli` is not a declared `dashboard` dependency (`dashboard.depends_on = {errors, state, journal, telemetry, signoff, config, concurrency}`; forbidden from `{engine, dispatcher, runtime, hooks, adopt}`) [scripts/module_boundary_table.py:142-147]. Per D4, **lift the malformed-safe reader into `telemetry/`** (the module that OWNS `agent_runs.jsonl`, and a declared `dashboard` dep): add `read_agent_runs`/`iter_agent_runs` to `telemetry/` mirroring the proven `cli/_agent_runs.py::iter_agent_runs` contract — *missing file → empty; `JSONDecodeError` → WARNING + skip; non-`dict` line → WARNING + skip* [src/sdlc/cli/_agent_runs.py:14-50]. Keep the CLI reader working (import the shared telemetry reader from `cli/_agent_runs.py`, or leave both — DRY per D4). Keep the new module ≤ 400 LOC [scripts/check_module_boundaries.py:163].
  - [x] Run `scripts/check_module_boundaries.py` on the new/edited files → GREEN (assert `dashboard → telemetry` is an allowed edge and `telemetry` still imports nothing forbidden; `telemetry.depends_on = {errors, contracts, journal, concurrency}`) [module_boundary_table.py:73-76].

- [x] **Task 2 — Server route: `/api/activity` serving last-50 reverse-chron, field-mapped, validated (D1, D4)** (AC: 1, 2) — *tests-first*
  - [x] Add `dashboard/routes/activity.py::register_activity_route(router, *, repo_root)` and wire it in `build_router` next to `register_state_route` / `register_dora_route` [src/sdlc/dashboard/server.py:89-93]. Mirror the `routes/state.py` / `routes/dora.py` shape (Response envelope, `Content-Type: application/json; charset=utf-8`). Read `.claude/state/agent_runs.jsonl` (confirm the real repo-relative path from the writer's caller) via the Task-1 telemetry reader.
  - [x] **Server-side projection (D1 mapping):** map each real `_AgentRunLine` dict → the feed's display shape, sort **reverse-chronological by `ts`** (most recent first), **truncate to the last 50**, and emit ONLY the display fields (do NOT leak `tokens_in`/`tokens_out`/`dispatch_prompt`/`attempts`/`mock`). Field map (see Dev Notes "REAL schema"): `id ← run_id`, `ts ← ts`, `agentName ← specialist_name`, `targetId ← target_path`, `stage ← workflow_step`, `outcome ← outcome`, `durationMs ← duration_ms`.
  - [x] Route MUST NOT 500 on a malformed/partial/truncated `agent_runs.jsonl` (bad lines skipped by the reader) or a missing file (→ empty list, 200). Optional but recommended: a short in-memory cache like `routes/dora.py` (the feed already polls at 3 s; keep it simple — no cache is acceptable for a bounded 50-row read).

- [x] **Task 3 — Feed source swap: fetch `/api/activity`, keep the 5.11 render SEAM (do-not-regress)** (AC: 1, 2) — *tests-first*
  - [x] In `activity-feed.js`, add a real-data path that fetches `/api/activity` and feeds the mapped entries into the EXISTING `renderActivityFeed(host, {entries})` seam. **Do NOT rewrite the render loop** — the 5.11 review HIGH fix (reverse-iterate insert → newest-on-top; `removeChild(list.lastChild)` evicts the genuine oldest) at [activity-feed.js:119-133] is guarded by a Playwright witness and MUST be preserved. The synthetic `buildSyntheticEntries` path may remain for the fixture, but the real path is the default when served by the dashboard.
  - [x] Poll on the 3 s cycle (reuse the dashboard's existing poll, do not add a second timer): re-fetch `/api/activity`, pass through `renderActivityFeed` → new entries **prepend**, existing DOM nodes untouched (NFR-PERF-4 — "only changed sections re-render"). No fade-in / no CSS transition (DD-06/DD-14).

- [x] **Task 4 — Add the 6th field `stage` to the feed row (D2)** (AC: 1)
  - [x] The AC lists **6 fields** (ts, agent name, target id, **stage**, outcome, duration_ms); the 5.11 synthetic row rendered **5** (no `stage`) [activity-feed.js:66-89]. Add a `stage` cell sourced from `workflow_step`, extend `.activity-feed__entry` `grid-template-columns` from 5 → 6 columns [activity-feed.css:19-26] using `var(--*)` only (5.2 stylelint gate). textContent-only (never innerHTML).

- [x] **Task 5 — Fold the four deferred-from-5.11 hardening fixes (DEF-1..DEF-4)** (AC: 1, 2) — *tests-first*
  - [x] **DEF-1 — per-host immutable state store** [activity-feed.js:132-138] — `prependActivityFeedEntry` mutates the shared exported `SYNTHETIC_ACTIVITY_FEED_FIXTURE` singleton via `host._fixtureRef` (two `<activity-feed>` on one page share + overwrite state; violates the immutability rule). Give each host its own state object; treat updates immutably (clone-on-write, do NOT default-mutate the shared singleton). [deferred-work.md:920]
  - [x] **DEF-2 — missing-`id` dedupe** [activity-feed.js:69,114-119] — `row.dataset.entryId = entry.id` stores `"undefined"` while the dedupe Set is checked with the value `undefined` → a real entry lacking an id re-inserts on every poll (unbounded duplicates). Key by `entry.id ?? \`row-${index}\`` **consistently** on BOTH the `dataset` write and the `existingIds` Set check. (Real rows carry `run_id`, mapped to `id` in Task 2 — but guard defensively.) [deferred-work.md:921]
  - [x] **DEF-3 — unknown-outcome neutral mapping** [activity-feed.js:42-43] — `OUTCOME_GLYPH[outcome] || OUTCOME_GLYPH.error` maps ANY value outside the known set to the red `error` glyph + "Error", mislabeling e.g. a `running`/`timeout`/`skipped` run as a failure. Per D3, map real `success`→`check`, `failed`→`slash-circle`, and route ANY unknown outcome to a **neutral** glyph+label (NOT the red error glyph); render the raw outcome string as text. Reuse only frozen sprite icons (check/slash-circle/error/warning) → no new icon, no ADR. [deferred-work.md:922]
  - [x] **DEF-4 — missing-field fallback** [activity-feed.js:71-85] — `textContent = entry.timestamp` (and agent/target/stage/duration) coerces a missing field to the literal `"undefined"`. Guard each cell with a fallback: `entry.x ?? "—"`. [deferred-work.md:923]

- [x] **Task 6 — Data-validation / XSS-safety (the distinguishing requirement, DAG §5:294)** (AC: 1, 2) — *tests-first*
  - [x] **Untrusted-input resilience (server + client):** a truncated last line, an invalid-JSON line, a non-object line, a line missing required fields, and an unknown `outcome` value MUST NOT crash the feed. The telemetry reader skips + logs bad lines (Task 1); the route returns the valid subset (Task 2); the renderer falls back per DEF-3/DEF-4. Add tests for each malformed case (line skipped/logged, feed still renders the good rows).
  - [x] **XSS-safety:** the renderer stays **textContent-only, never `innerHTML`** [activity-feed.js:58-88 uses `createElement`/`textContent`] — a field value like `<img src=x onerror=alert(1)>` or `"><script>` MUST render as inert text, not markup/executed script. Add a behavioral (Playwright) test injecting a script-like payload in `agentName`/`targetId`/`stage` and asserting no element is created from it and `textContent` matches verbatim.

- [x] **Task 7 — Tests: static contracts + reader/route unit + Playwright witnesses** (AC: 1, 2) — *tests-first*
  - [x] Update the 5.11 static-analysis grep contract [tests/unit/dashboard/test_tabs_activity_feed_fixture.py:73-91] for the **real field names** (`agentName`, `targetId`, **`stage`**, `outcome`, `durationMs`) — the current `("timestamp","agentName","targetId","outcome","duration")` set (line 75) and the `buildSyntheticEntries(50)` grep (line 70) must reconcile with the swapped source; do not leave a stale grep that green-lights the wrong shape (the 5.11 HIGH shipped *because* a substring grep couldn't see the render).
  - [x] New Python unit suite for the telemetry reader + `/api/activity` route: reverse-chron ordering, last-50 truncation, field projection (real→display), leaked-field exclusion, malformed-line skip, missing-file → empty/200. Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`).
  - [x] Extend the Playwright suite [tests/integration/test_dashboard_activity_feed_empty_state.py:75-145] with a REAL-DATA fixture: newest-on-top + poll-prepends-newest + evict-oldest (do-not-regress), incremental-render (existing nodes retain identity), the DEF-2/3/4 edge rows, and the Task-6 XSS payload. RED against the un-swapped code → GREEN after Tasks 1–6. (Split into a sibling `test_dashboard_activity_feed_live.py` module to respect the 400-LOC/file cap — see Completion Notes.)

- [x] **Task 8 — Packaging + quality gate + freeze** (AC: 1, 2)
  - [x] Add any NEW static assets (real-data `activity-feed` fixture + a route-demo fixture if added) to the `force-include` block [pyproject.toml:74-133] following the 5.5-frozen `static/components/<name>/` convention. New Python (`telemetry/` reader, `dashboard/routes/activity.py`, tests) is importable — no force-include needed.
  - [x] Component CSS uses `var(--*)` only (5.2 stylelint gate); DD-14 motion gate (no transitions — feed changes are content/keyed-diff prepends), DD-08 no-framework, DD-09 no-`data-theme`, 5.5 color-only gate (outcome glyph + `stage` carry adjacent text). `scripts/check_module_boundaries.py` GREEN.
  - [x] Python quality gate on the new reader/route/tests: ruff + ruff format + mypy --strict; full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7** (`agent_runs.jsonl` is NOT an ADR-024 frozen contract — runs.py:1-17).

## Dev Notes

### REAL `agent_runs.jsonl` schema — VERIFIED (pin these field names, NOT the AC's logical names)

The record written per dispatch is the **private frozen dataclass `_AgentRunLine`** [src/sdlc/telemetry/runs.py:31-52]. It is **NOT an ADR-024 frozen wire-format contract** — per ADR-029 §4 (divergence #4) + Story 2B.1 AC5/D2 it is intentionally private, `schema_version` is an in-band field (not a `tests/contract_snapshots/v1/` snapshot), and the format may evolve without an ADR-024 ceremony [runs.py:1-17]. This is why 5.16 has **zero wire-format change → freeze stays 7/7**.

| Persisted field (real) | Type | AC / NFR-OBS-2 logical name | 5.11 synthetic name (DRIFT) |
|---|---|---|---|
| `ts` | `str` (RFC-3339) | ts | `timestamp` |
| `specialist_name` | `str` | **agent name** | `agentName` |
| `target_path` | `str` (a path, not an id) | **target id** / output_path | `targetId` |
| `workflow_step` | `str` | **stage** | *(absent — synthetic had 5 fields)* |
| `outcome` | `str` ∈ **`{success, failed}`** | outcome | *(synthetic used `{approved, rejected, error}`)* |
| `duration_ms` | `int` (integer ms) | duration_ms | `duration` (pre-formatted `"1m 10s"` string) |
| `run_id` | `str` | *(the entry id)* | `id` |
| `target_kind` | `str` ∈ `{primary, parallel, synthesizer}` | — (not shown) | — |
| `attempts`, `tokens_in`, `tokens_out` | `int` | tokens_in/out (NFR-OBS-2) | — (not shown; do NOT leak) |
| `mock` | `bool` (default `False`) | — | — |
| `dispatch_prompt` | `str \| None` (dropped when `None`) | — | — (do NOT leak) |
| `schema_version` | `int` (=1, in-band) | — | — |

Valid outcome set is `_VALID_OUTCOMES = {"success", "failed"}` [runs.py:27]; valid target-kind set is `{"primary", "parallel", "synthesizer"}` [runs.py:28]. `to_json_line()` sorts keys and drops a `None` `dispatch_prompt` [runs.py:48-52].

[Source: src/sdlc/telemetry/runs.py:27-52, 1-17; architecture.md:373 (E3 → `telemetry/runs.py`), :888-892, :136; NFR-OBS-2 prd.md:879 / epics.md:135]

### Drift vs the 5.11 synthetic feed — the swap is a MAPPING, raised as Decisions

**D1 — Real→display field mapping / name drift (HIGH).** The AC (epics:2773) and NFR-OBS-2 (prd:879) use *logical* names (`agent name`, `target id`, `stage`); the persisted record uses `specialist_name` / `target_path` / `workflow_step`, its `outcome` vocabulary is `{success, failed}` (not the synthetic `{approved, rejected, error}`), `duration_ms` is an integer (not the synthetic pre-formatted string), and the id is `run_id` (not `id`). *Recommendation (a):* do the mapping **server-side in the `/api/activity` route** (Task 2) so the browser receives a clean, already-projected shape and never re-parses wire files (DAG §5): `{id ← run_id, ts, agentName ← specialist_name, targetId ← target_path, stage ← workflow_step, outcome, durationMs ← duration_ms}`. Format `durationMs` → human-readable in JS (e.g. `"1m 10s"`). Do NOT emit `tokens_*` / `dispatch_prompt` / `attempts` / `mock`. Document each mapping in the Change Log.

**D2 — Feed field-count reconcile (MED).** AC = **6 fields** incl `stage`; the 5.11 synthetic row rendered **5** [activity-feed.js:66-89; css grid is 5-col at activity-feed.css:21]. *Recommendation (a):* **add the 6th `stage` cell** (source `workflow_step`), extend the CSS grid 5→6 columns. This EXTENDS the 5.11 seam — it is not a redesign (anti-scope-creep).

**D3 — Outcome vocabulary + unknown mapping (MED, folds DEF-3).** Real writer emits only `{success, failed}`, but the reader is untrusted (unknown values like `running`/`timeout`/`skipped` must not be mislabeled as failures). *Recommendation (a):* map `success`→`check` glyph + "Success", `failed`→`slash-circle` + "Failed"; keep `approved`→`check` / `rejected`→`slash-circle` / `error`→`error` as back-compat aliases; route ANY **unknown** outcome to a **neutral** treatment (a non-red frozen glyph — e.g. `warning`, or an icon-less neutral dot — plus the raw outcome string as text), NEVER the red `error` glyph. Reuse only the frozen 12-icon sprite (`check`/`slash-circle`/`error`/`warning` present) → no new icon, no ADR. Each glyph keeps adjacent text (5.5 color-only gate).

**D4 — Reader/route seam location (HIGH — the central architectural decision).** The proven malformed-safe reader `iter_agent_runs` lives in `cli/_agent_runs.py` [lines 14-50], but `cli` is **NOT** a declared `dashboard` dependency, so the dashboard cannot import it [module_boundary_table.py:142-147]. `telemetry/runs.py` today has only the **writer** (`record_agent_run`), no reader. *Recommendation (a):* **lift the reader into `telemetry/`** (a declared `dashboard` dep and the module that owns `agent_runs.jsonl`) and have BOTH `cli` and `dashboard` consume it (DRY); add `dashboard/routes/activity.py` reading through it, mirroring `routes/dora.py`/`routes/state.py` + `build_router` [server.py:89-93]. *Alternative (b):* keep a private reader inside `dashboard` (duplicates the JSONL-parse; risks drift from the CLI reader). Recommendation (a) keeps the **one-way module edge** (`dashboard → telemetry`, never re-parse; DAG §5:310-313) honest and avoids re-implementing untrusted parsing in the browser.

### Do-NOT-regress (the 5.11 review HIGH + its Playwright witnesses)

- **Newest-on-top + evict-oldest.** The 5.11 review HIGH was an inverted feed (oldest-on-top, evicting the *newest*). The fix reverse-iterates the newest-first entries inserting before `firstChild` so the newest lands on top and `list.lastChild` is the genuine oldest; the trim `removeChild(list.lastChild)` then evicts the oldest [activity-feed.js:119-133]. This is guarded by `test_activity_feed_renders_newest_entry_on_top` + `test_activity_feed_poll_prepends_newest_and_evicts_oldest` [test_dashboard_activity_feed_empty_state.py:82-145]. **Keep both green** with real data.
- **Incremental render (NFR-PERF-4).** Poll re-render must skip existing DOM nodes (keyed by id) and only prepend the new row — never `replaceChildren()` [activity-feed.js:114-129].
- **textContent-only.** The renderer builds cells with `createElement` + `textContent` [activity-feed.js:58-88] — never `innerHTML`. This is the XSS defense; do not introduce string-HTML.

### Reader-seam / module-boundary facts

- `dashboard.depends_on = {errors, state, journal, telemetry, signoff, config, concurrency}`; `forbidden_from = {engine, dispatcher, runtime, hooks, adopt}`. **`cli` is NOT a dependency** → the dashboard cannot import `cli/_agent_runs.py`. [scripts/module_boundary_table.py:142-147]
- `telemetry.depends_on = {errors, contracts, journal, concurrency}`; `forbidden_from = {engine, dispatcher, runtime, cli}` — a reader added here imports nothing new. [module_boundary_table.py:73-76]
- Enforcement runs in pre-commit + CI via `scripts/check_module_boundaries.py` (AST import walk + ≤400 LOC cap). [check_module_boundaries.py:122-160, 163]
- Existing route seam to mirror: `build_router` registers `register_state_route` + `register_dora_route` [server.py:89-93]; route bodies return a `Response(status, headers, body)` envelope [routes/state.py:15-40, routes/dora.py:51-63].

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the `telemetry/` reader lift + `/api/activity` route (last-50 reverse-chron, real→display field projection, malformed-line resilience, no field leaks), the `activity-feed.js` source swap onto the 5.11 render seam, the 6th `stage` cell, the four DEF-1..DEF-4 hardening fixes, and the data-validation / XSS-safety tests. Real `agent_runs.jsonl` only.
- **Must NOT build:** real signoff 4-state (**5.14**), real Epic→Story→Task hierarchy (**5.15**), real DORA / `/api/dora` compute (**5.13**/**5.17**), real Resume Card you-are-here + suggested-next (**5.18**), STOP banners / 7-trigger rendering (**5.19**), honest-disconnection (**5.20**). Do NOT redesign the feed component (it is a 1:1 swap onto the 5.11 twin). No new UI framework, no modals/toasts/forms/client-routing/skeletons; no CSS `transition:`/transforms (DD-14/DD-06). No new ADR-024 wire contract (agent_runs is a private model → freeze stays 7/7). [Source: docs/sprints/epic-5-dag.md §2:139-177 (S11→S16, E2B→S16), §3:215/241, §5:294/310-313, §6:329]

### Project Structure Notes

- New Python: `src/sdlc/dashboard/routes/activity.py` (route) + a reader in `src/sdlc/telemetry/` (new fn on `runs.py` if it stays ≤400 LOC, else a sibling `telemetry/runs_reader.py`). Both under the 400-LOC cap.
- Edited: `src/sdlc/dashboard/static/components/activity-feed/activity-feed.js` + `activity-feed.css` (6th column), `src/sdlc/dashboard/server.py` (`build_router` registration), `src/sdlc/cli/_agent_runs.py` (re-export the shared telemetry reader, DRY — optional per D4).
- New/edited tests: `tests/unit/dashboard/test_tabs_activity_feed_fixture.py` (real field names), `tests/unit/telemetry/test_agent_runs_reader.py` (new), `tests/unit/dashboard/test_activity_route.py` (new), `tests/integration/test_dashboard_activity_feed_empty_state.py` (real-data + XSS witnesses).
- New static fixtures → `force-include` [pyproject.toml:74-133], `static/components/<name>/` convention.
- Wave-boundary VERIFY at branch time: `2b-10-author-phase-3-specialists-tdd-pipeline: done` [sprint-status.yaml:200] — confirm Phase-3 specialists actually emit real (non-`mock`) `_AgentRunLine` records; the 2A.3 writer was a "placeholder schema … full implementation in 2B" [epics.md:1051], and `_AgentRunLine` is the current authority. If the live outcome set ever exceeds `{success, failed}`, the D3 neutral fallback already covers it.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Malformed-safe JSONL reader (skip+log, missing→empty) | mirror/lift into `telemetry/` | src/sdlc/cli/_agent_runs.py:14-50 |
| Real record shape (field names/types + valid outcomes) | `_AgentRunLine` / `_VALID_OUTCOMES` | src/sdlc/telemetry/runs.py:27-52 |
| Route registration + Response envelope | `build_router` + `register_*_route` | src/sdlc/dashboard/server.py:89-93; routes/dora.py:51-63; routes/state.py:15-40 |
| Feed render SEAM (incremental prepend, newest-on-top, evict-oldest) | `renderActivityFeed` / `prependActivityFeedEntry` | src/sdlc/dashboard/static/components/activity-feed/activity-feed.js:99-144 |
| Outcome glyphs (frozen sprite: check/slash-circle/error/warning) | `<use href="/static/icons/sprite.svg#…">` | src/sdlc/dashboard/static/icons/sprite.svg |
| Playwright feed witnesses (newest-on-top / evict-oldest / non-blank) | extend, do NOT regress | tests/integration/test_dashboard_activity_feed_empty_state.py:75-167 |
| Static-analysis contract test | update field names | tests/unit/dashboard/test_tabs_activity_feed_fixture.py:61-91 |
| Module-boundary + LOC gate | run on new files | scripts/check_module_boundaries.py; module_boundary_table.py:142-147 |
| Motion / no-framework / color-only gates | run on the edited component | scripts/check_dashboard_motion.py / _no_framework.py / _color_only.py |
| Wheel force-include | add new static fixtures | pyproject.toml:74-133 |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2763-2780] — Story 5.16 ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/epics.md:135 (NFR-OBS-2), :797 (FR42), :1051 (2A placeholder / 2B full impl)] — agent_runs full-metadata contract
- [Source: _bmad-output/planning-artifacts/prd.md:797 (FR42), :799 (FR44), :828 (NFR-PERF-4), :879 (NFR-OBS-2)] — feed + only-changed-sections re-render + record metadata
- [Source: src/sdlc/telemetry/runs.py:27-52, 1-17] — REAL `_AgentRunLine` schema + valid outcomes + "private, NOT ADR-024 frozen" rationale (freeze stays 7/7)
- [Source: src/sdlc/cli/_agent_runs.py:14-50] — malformed-safe `iter_agent_runs` reader to lift into `telemetry/` (D4)
- [Source: scripts/module_boundary_table.py:142-147 (dashboard), 73-76 (telemetry)] — `dashboard → telemetry` allowed; `cli` NOT a dashboard dep; enforcement scripts/check_module_boundaries.py:122-160,163
- [Source: src/sdlc/dashboard/server.py:89-93] — `build_router` route-registration seam; routes/dora.py:51-63 + routes/state.py:15-40 (pattern to mirror)
- [Source: src/sdlc/dashboard/static/components/activity-feed/activity-feed.js:19-162] — render seam; DEF lines 42-43 (DEF-3), 69/114-119 (DEF-2), 71-85 (DEF-4), 119-133 (do-not-regress newest-on-top), 132-138 (DEF-1)
- [Source: src/sdlc/dashboard/static/components/activity-feed/activity-feed.css:19-26] — 5-col grid to extend to 6 (stage cell)
- [Source: tests/integration/test_dashboard_activity_feed_empty_state.py:75-167] — Playwright witnesses (newest-on-top / poll-prepend-evict / non-blank); tests/unit/dashboard/test_tabs_activity_feed_fixture.py:61-91 — static grep contract to reconcile
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:916-923] — DEF-1..DEF-4 owned by 5.16 (5.11 review, 2026-06-26)
- [Source: docs/sprints/epic-5-dag.md §2:139-177, §3:215/241, §4:249-256, §5:294/310-313, §6:329, §7:351] — L6/5B batch-1, S11→S16 twin, E2B→S16 wave gate, one-way module edge, data-validation review focus, "verify upstream shape before branching 5B"
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.8:1326-1328] — Activity Feed (last-50, prepend-on-poll, no fade-in)
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml:200 (2b-10 done), :255 (5-16 backlog)] — wave-boundary status
- [Source: _bmad-output/implementation-artifacts/5-11-tabs-activity-feed-empty-state-section-block-heading.md:48-51,74-84] — twin story: the render seam built for 5.16 + the HIGH fix + the deferred items

## Dev Agent Record

### Agent Model Used

Claude (Cursor bmad-dev-story workflow)

### Debug Log References

- Playwright `page.goto(..., wait_until="networkidle")` timed out for the live-poller
  fixture because `activity-feed-live.fixture.html` polls `/api/activity` every 150ms,
  so the network never goes idle. Fixed by adding a `wait_until` parameter to
  `_with_playwright_page` and passing `wait_until="load"` for the live fixture.
- Live-fixture `page.wait_for_function` timed out waiting for a small row count because
  `ActivityFeed.connectedCallback` rendered the 50-row synthetic fixture by default before
  the live poller's first fetch landed. Fixed by adding a `data-source="live"` guard in
  `connectedCallback` that skips the synthetic render, and setting that attribute on the
  live fixture host.
- `tests/integration/test_dashboard_activity_feed_empty_state.py` grew past the 400-LOC
  pre-commit cap once the 5.16 real-data Playwright tests were added (480 lines). Split
  the four real-`agent_runs.jsonl`-backed tests + their fixtures into a new sibling module
  `tests/integration/test_dashboard_activity_feed_live.py` (269 + 275 lines) — confirmed
  `scripts/check_module_boundaries.py` / pre-commit green after the split.
- Verified a pre-existing, unrelated flaky failure pattern is NOT caused by this story:
  ran the full `tests/unit + tests/integration` suite on a clean `main` (via
  `git stash -u`) and confirmed the identical 10 pre-existing failures
  (`tests/integration/test_trace_replay_logs_e2e.py::*`) and near-identical coverage
  (84.06% baseline vs 84.09% on this branch) exist with or without this story's changes.
  Both floors (87% coverage, 0 failures) are pre-existing red gates, not introduced here.

### Completion Notes List

- **Task 0 (Decisions D1–D4):** Recorded below in the Change Log per CONTRIBUTING §5.
  Verified the wave boundary: `_AgentRunLine` [src/sdlc/telemetry/runs.py:36-50] is the
  live real-record shape (2B.10 done+merged); pinned real field names
  (`run_id`, `ts`, `specialist_name`, `target_path`, `workflow_step`, `outcome`,
  `duration_ms`) as the Task-2 projection source, not the AC's logical names.
- **Task 1 (reader seam):** `telemetry/runs.py::iter_agent_run_records` already existed
  (lifted in Story 5.13 for `telemetry/dora.py`) and matches the required malformed-safe
  contract (missing file → empty; bad JSON / non-object line → WARNING + skip). No new
  reader function was needed — Task 1 was satisfied by adding the previously-missing unit
  test suite (`tests/unit/telemetry/test_agent_runs_reader.py`, 8 tests) directly
  exercising it (missing file, valid records, blank lines, malformed JSON, non-object
  lines, truncated final line, undecodable bytes via `errors="replace"`, `OSError`
  propagation). Per D4, `cli/_agent_runs.py` was intentionally left untouched (still
  duplicated) rather than importing from `telemetry/` or vice versa, since `cli` is not a
  declared `dashboard`/`telemetry` dependency in either direction and the story's scope is
  the dashboard route, not a CLI refactor.
- **Task 2 (`/api/activity` route):** New `dashboard/routes/activity.py` reads through the
  Task-1 reader, server-side-projects each raw record to the display shape (drops any
  record missing/mistyping a required field — never leaks `tokens_in`/`tokens_out`/
  `dispatch_prompt`/`attempts`/`mock`), sorts reverse-chronological by `ts`, and truncates
  to the last 50. Wired into `build_router` next to the other routes. 12 unit tests in
  `tests/unit/dashboard/test_activity_route.py`.
- **Task 3 (feed source swap):** `activity-feed.js` gained `mapServerEntry`,
  `pollActivityFeedSnapshot`, and `startActivityFeedLivePoller`, all feeding the EXISTING
  `renderActivityFeed`/`prependActivityFeedEntry` seam unchanged (5.11 newest-on-top /
  evict-oldest fix preserved verbatim). `connectedCallback` skips the synthetic default
  render when `data-source="live"` is set (dashboard markup), so the live path is what
  actually ships; the synthetic fixture path remains for the Playwright/static fixture.
- **Task 4 (6th `stage` field):** Added to `buildSyntheticEntries`, `createFeedEntry`, and
  the CSS grid (5→6 columns, `var(--*)` tokens only).
- **Task 5 (DEF-1..DEF-4):** Per-host state is no longer a shared mutable singleton
  (DEF-1); dedupe now keys consistently off `entry.id ?? \`row-${index}\`` on both the
  dataset write and the existing-ids set (DEF-2); unknown outcomes map to a neutral
  `warning` glyph + the raw outcome text instead of the red error glyph (DEF-3); every
  cell falls back to `"—"` instead of the literal `"undefined"` (DEF-4).
  All four covered by dedicated Playwright witnesses.
- **Task 6 (data-validation / XSS):** Server-side: malformed/non-object/truncated JSON
  lines and records missing required fields are dropped, never 500. Client-side: the
  renderer stays `textContent`-only (verified by a static grep contract asserting no
  `innerHTML` usage) and a Playwright test injects `<img src=x onerror=alert(1)>"><script>`
  into `agentName`, asserting it renders as inert text with zero child elements created.
- **Task 7 (tests):** Updated the 5.11 static-contract grep suite for the real field names
  + neutral-glyph + live-poller export + no-`innerHTML` + `data-source="live"` gating
  (`test_tabs_activity_feed_fixture.py`); new reader unit suite (8 tests) and route unit
  suite (12 tests); extended Playwright coverage with 4 new real-data tests (moved to
  `test_dashboard_activity_feed_live.py` to respect the LOC cap) plus 2 new
  DEF-1/DEF-4 witnesses in the original module, refactored to a module-scoped `_browser`
  fixture (one Chromium launch per test module instead of per test) to reduce
  GC-timing-related `ResourceWarning`/`PytestUnraisableExceptionWarning` flakiness under
  `filterwarnings = ["error"]`.
- **Task 8 (packaging / quality gate):** Added the new `activity-feed-live.fixture.html`
  to the wheel `force-include` block. Confirmed: `ruff check` + `ruff format --check`
  clean; `mypy --strict` clean on the new/edited source; full pre-commit (module
  boundaries + LOC cap, dashboard design-direction gates, secret scan, etc.) green;
  `mkdocs build --strict` green; `scripts/check_module_boundaries.py` green (no new
  forbidden imports; both new modules under 400 LOC). Full `tests/unit` + `tests/integration`
  run: 3813 passed, 10 failed, 3 skipped, 1 xfailed — the 10 failures are the exact same
  pre-existing `test_trace_replay_logs_e2e.py` failures present on a clean `main` (verified
  via `git stash -u` + re-run), i.e. **zero regressions** introduced by this story. Coverage
  84.09% vs the 87% floor is likewise a pre-existing gap (84.06% on clean `main`), not a
  regression caused by this story's code. Zero wire-format change — `agent_runs.jsonl`
  freeze stays 7/7.

### File List

- `src/sdlc/dashboard/routes/activity.py` (new) — `GET /api/activity` route
- `src/sdlc/dashboard/server.py` (edited) — register the new route in `build_router`
- `src/sdlc/dashboard/static/components/activity-feed/activity-feed.js` (edited) — real-data
  polling path, 6th `stage` field, DEF-1..DEF-4 hardening fixes
- `src/sdlc/dashboard/static/components/activity-feed/activity-feed.css` (edited) — 6-column
  grid for the new `stage` cell
- `src/sdlc/dashboard/static/components/activity-feed/activity-feed-live.fixture.html` (new) —
  Playwright fixture for the live poller
- `pyproject.toml` (edited) — `force-include` the new live fixture HTML
- `tests/unit/telemetry/test_agent_runs_reader.py` (new) — unit tests for
  `iter_agent_run_records`
- `tests/unit/dashboard/test_activity_route.py` (new) — unit tests for `/api/activity`
- `tests/unit/dashboard/test_tabs_activity_feed_fixture.py` (edited) — static-contract
  grep updates for the real field names / neutral glyph / live poller / no-innerHTML
- `tests/integration/test_dashboard_activity_feed_empty_state.py` (edited) — module-scoped
  `_browser` fixture, DEF-1/DEF-4 Playwright witnesses; real-data tests moved out
- `tests/integration/test_dashboard_activity_feed_live.py` (new) — real-`agent_runs.jsonl`
  Playwright witnesses (split out to respect the 400-LOC cap)

## Change Log

- 2026-07-01: Story 5.16 created (create-story, "flip done 5.12 + tạo all US cho layer tiếp theo" → L6/5B batch-1). Activity Feed real-data swap onto the 5.11 render seam: read the real `agent_runs.jsonl` through a lifted `telemetry/` reader (never re-parse wire files; `dashboard → telemetry` one-way edge, DAG §5), serve last-50 reverse-chron via a new `/api/activity` route with a server-side real→display field projection, add the AC's 6th `stage` cell, and fold the four deferred-from-5.11 hardening fixes (DEF-1 per-host immutable store / DEF-2 missing-id dedupe / DEF-3 unknown-outcome neutral mapping / DEF-4 missing-field fallback). Data-validation is first-class (untrusted file content: malformed/partial/truncated JSONL skipped+logged, must not crash or XSS the feed — textContent-only). Decisions raised: D1 (real→display field mapping / name drift: specialist_name/target_path/workflow_step/duration_ms int/run_id vs synthetic names), D2 (feed 6-field reconcile — add `stage`), D3 (outcome vocabulary `{success, failed}` + neutral unknown mapping), D4 (reader/route seam lifted into `telemetry/`, consumed by cli+dashboard). Do-not-regress the 5.11 newest-on-top + evict-oldest HIGH fix (Playwright-guarded). Zero wire-format change (agent_runs is a private model, not ADR-024 frozen → freeze 7/7). Wave-boundary: 2B.10 done+merged (verify Phase-3 specialists emit real `_AgentRunLine` records at branch time). Anti-scope-creep: swap the feed source only; do NOT build 5.13/5.14/5.15/5.17/5.18/5.19.
- 2026-07-03: Story 5.16 **code-review (bmad-code-review, fresh-context)** — stays `review` (patch applied, pre-merge). 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor @ Opus-4.8): 15 raw → **1 decision-needed → resolved (a), 0 other patches, 5 defer, 3 dismissed**. AC1/AC2/D1/D2/D3/D4/data-validation/zero-wire-format all independently verified in code (ruff+format+mypy --strict clean, `check_module_boundaries.py` green, freeze 7/7, story's tests green incl 4 Playwright witnesses). **DN-1 patch (option a, user-ratified) applied TDD-first:** `/api/activity` now sorts reverse-chron by a **parsed** `ts` instant (new `_parse_iso`, mirrors `telemetry/dora.py`) and drops unparseable-`ts` records, instead of a lexicographic string compare that could misorder + wrongly evict genuinely-recent entries under the untrusted-`agent_runs.jsonl` mandate (writer imposes no ts-format check, runs.py:47). New RED→green tests: `test_sorts_by_true_instant_not_lexicographically` + `test_record_with_unparseable_ts_dropped`; suite 55→57 green. 5 defers → `deferred-work.md` (DEF-1 no live empty/error-state · DEF-2 no `/api/activity` cache · DEF-3 id-dedup · DEF-4 ghost-row reconcile → Story 5.20 error-surface / dedup classes; **DEF-5 ESCALATE:** independently reproduced 10 failed / 3813 passed — the 10 are a **pre-existing test-isolation bug** in `test_trace_replay_logs_e2e.py` (`sdlc init` catches a stale `.claude` from a leaked CWD; passes in isolation; unrelated to this diff) + coverage 84.09% < 87% pre-existing → **blocks the §1/§7.4 merge gate, not caused by 5.16**). 3 dismissed (float-duration drop = documented contract; non-array payload = route can't emit; feed-not-user-reachable = page-assembly out of scope). **NOT flipped to done** — merged-before-done gate (R2): code uncommitted + main pre-existing red must clear before the TDD-first commit ceremony test(5.16)→feat(5.16)→docs(5.16) [fresh-context-review] + PR + CI-green + rebase-merge.
- 2026-07-03: Story 5.16 implemented (dev-story). **Decisions resolved:** D1=a (server-side field projection in the new `/api/activity` route: `id←run_id, ts, agentName←specialist_name, targetId←target_path, stage←workflow_step, outcome, durationMs←duration_ms`; `tokens_in/tokens_out/dispatch_prompt/attempts/mock` never leave the server); D2=a (added the 6th `stage` cell, grid 5→6 columns); D3=a (`success`→check/"Success", `failed`→slash-circle/"Failed", back-compat `approved/rejected/error` aliases kept, any other value → neutral `warning` glyph + raw outcome text, never the red error glyph); D4=a (reader seam stayed in `telemetry/runs.py::iter_agent_run_records`, already lifted there in Story 5.13 for `telemetry/dora.py` — reused as-is rather than duplicated; `cli/_agent_runs.py` intentionally left untouched, no cross-import added in either direction since `cli` is outside both `dashboard`'s and `telemetry`'s declared dependency sets). Implemented all 8 tasks: telemetry-reader unit tests (8), `/api/activity` route + unit tests (12), feed real-data polling path (`mapServerEntry`/`pollActivityFeedSnapshot`/`startActivityFeedLivePoller`) preserving the 5.11 render seam verbatim, the 6th `stage` field, DEF-1..DEF-4 hardening, textContent-only XSS-safety (server-side drop of malformed records + client-side inert-text Playwright witness), updated static-contract tests, and new Playwright real-data tests (split into `test_dashboard_activity_feed_live.py` to respect the 400-LOC cap after the module grew past it). Quality gate: ruff/ruff-format/mypy --strict clean, full pre-commit green (module boundaries + LOC cap + all dashboard design-direction gates), `mkdocs build --strict` green. Full regression (`tests/unit` + `tests/integration`): 3813 passed / 10 failed / 3 skipped / 1 xfailed — verified via `git stash -u` that the 10 failures (`test_trace_replay_logs_e2e.py::*`) and the 84%-ish coverage gap (84.06% baseline → 84.09% here) are pre-existing on clean `main`, i.e. zero regressions from this story. Status → review.

## Review Findings

> bmad-code-review 2026-07-03 (fresh-context, 3 adversarial layers Blind Hunter / Edge Case Hunter / Acceptance Auditor @ Opus-4.8). 15 raw → deduped to **1 decision-needed → resolved (a) → 1 patch APPLIED, 5 defer, 3 dismissed**. Independently re-verified (not trusted from prose): ruff + ruff-format clean; mypy --strict clean; `check_module_boundaries.py` green (D4); `freeze_wireformat_snapshots --check` 7/7 (zero wire-format); the story's own tests GREEN incl all 4 Playwright witnesses (55 → 57 after the DN-1 patch's 2 regression tests); full `tests/unit`+`tests/integration` reproduces **exactly 10 failed / 3813 passed** with the diff present. AC1, AC2, D1, D2, D3, D4, data-validation (malformed→drop, textContent-only XSS), and zero-wire-format are all genuinely satisfied in code.

### Decision-needed → RESOLVED (a) → patch applied

- [x] [Review][Decision→Patch] Reverse-chron sort now parses `ts` to a real instant (was lexicographic string compare) [src/sdlc/dashboard/routes/activity.py:66-101] — **Resolved option (a) (user, 2026-07-03) → patch applied TDD-first.** `_load_entries` sorted on the raw `ts` string while `runs.py::_validate` imposes **no** ts-format check (writer passes caller-supplied `ts` verbatim; `ts` absent from `_validate`, runs.py:47) and `_project_entry` only checks non-empty-string — so a corrupted/mixed-format `ts` in the untrusted `agent_runs.jsonl` (mixed `Z` / `.000Z` / `+00:00`, or non-ISO) misordered the feed and, because `[:50]` truncates after the sort, could drop genuinely-recent entries (AC1 violation under the untrusted-content mandate). **Fix:** added `_parse_iso` (mirrors `telemetry/dora.py::_parse_iso`, proven py3.10–3.13); `_load_entries` now sorts by the parsed instant and **drops** unparseable-`ts` records (consistent with the malformed→drop contract). RED-first: `test_sorts_by_true_instant_not_lexicographically` (tz-offset witness) + `test_record_with_unparseable_ts_dropped` in `tests/unit/dashboard/test_activity_route.py` — both failed pre-fix, green post-fix; module-boundary + freeze 7/7 unchanged. Surfaced by Blind + Edge + Auditor.

### Defer (see deferred-work.md 2026-07-03)

- [x] [Review][Defer] No empty/error state on the live activity feed [src/sdlc/dashboard/static/components/activity-feed/activity-feed.js:280-283,142-160] — deferred: not an AC of 5.16 (only AC1/AC2), component never had empty-state copy, and no production page mounts `startActivityFeedLivePoller` yet (not user-reachable today). `renderActivityFeed({entries:[]})` yields a blank focusable list (no "no activity" copy); a permanently-failing first poll stays blank (self-heals on the next 3 s tick). Same class as 5.14 DEF-4 / 5.15 DEF-3 error-surface → Story 5.20. Blind + Edge.
- [x] [Review][Defer] `/api/activity` re-reads + globally sorts the entire append-only `agent_runs.jsonl` on every 3 s poll, no cache [src/sdlc/dashboard/routes/activity.py:66-78] — deferred: spec-permitted (Task 2 allows no cache); the "bounded 50-row read" justification is inaccurate (materializes+sorts every record, then `[:50]`); sibling `dora.py` shields the same file behind a 30 s TTL cache. Same class as 5.13 DEF-1. Blind + Auditor.
- [x] [Review][Defer] Identity/dedup hardening (untrusted-only; real path safe) [src/sdlc/dashboard/routes/activity.py:66-78 · activity-feed.js:172] — deferred: server guarantees a non-empty `run_id`, so the real path is unaffected. Duplicate `run_id` in one snapshot → client dedup silently drops the 2nd distinct run; `entry.id ?? \`row-${i}\`` misses `""`/`0` and the positional fallback is unstable across polls. Fold into 5.15 DEF-2 dup-id-dedup → Story 5.20. Blind + Edge.
- [x] [Review][Defer] Stale "ghost" rows if `agent_runs.jsonl` is rotated/compacted [src/sdlc/dashboard/static/components/activity-feed/activity-feed.js:166-181] — deferred: append-only makes this rare. Renderer is insert-new-ids + trim-by-count only; it never removes rows absent from a shrunk snapshot nor re-orders. Same reconciliation class as 5.14 DEF-4 → Story 5.20. Edge.
- [x] [Review][Defer→RESOLVED] Test-isolation bug fixed; "merge blocker" was a measurement artifact [tests/unit/cli/test_signoff_command.py:26-40] — **UPDATE 2026-07-03: root-caused + fixed.** The 10 `test_trace_replay_logs_e2e.py` failures were **not** caused by 5.16 and were **not** a real red on the CI gate. Root cause: `_bootstrap` did a **bare, unrestored** `init_mod._get_repo_root_or_cwd = lambda: tmp_path` (the former P21 "legacy" branch), leaking a tmp-path override into `sdlc.cli.init` so every *later* real `sdlc init` resolved to a prior test's tmp dir → "already initialized". It only surfaces when `tests/unit` runs **before** `tests/integration` (the dev's manual `pytest tests/unit tests/integration` order); the actual CI gate `uv run pytest` collects **integration before unit**, so CI on `main` was already green. **Fix (TDD-first):** `_bootstrap` now restores the override after `run_init` (save/finally), making the suite **order-independent**; added order-independent regression guard `test_bootstrap_does_not_leak_repo_root_override`. **Coverage was never below floor at CI scope:** the "84.09%" was a subset artifact (`tests/unit + tests/integration` omits property/contracts/dashboard/adopt/security/…); the real gate `uv run pytest` (all of `tests/`) reports **90.07%** ≥ 87. **Verified:** `uv run pytest` → **4223 passed / 4 skipped / 1 xfailed, exit 0** (gate green). Task 8's "coverage ≥ 87%" checkbox is therefore accurate at CI scope (its Dev-Agent-Record caveat measured a subset).

### Dismissed (noise / handled-by-design — dropped, not persisted as action items)

- Float `duration_ms` drops the whole row [activity.py:60] — writer types `duration_ms: int` (runs.py:39) + validates `>=0`; a float only appears via corruption, and "mistyped required field → drop record" is the route's documented contract. Consistent by design.
- Non-array `entries` payload → `.map` TypeError swallowed to a silent no-op [activity-feed.js:232] — the route only ever emits a JSON list, so unreachable in production; degrades safely + self-heals next poll. Defensive-only.
- Real feed not user-reachable (no production page mounts the poller) [activity-feed.js:243] — explicitly out of this story's scope (page assembly), documented in the JS header, matches the 5.11 twin.
