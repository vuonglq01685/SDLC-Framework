# Story 5.16: Activity Feed Reading Real `agent_runs.jsonl`

Status: ready-for-dev

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

- [ ] **Task 0 — Resolve Decisions D1 (real→display field mapping / name drift) + D2 (feed field-count reconcile: AC's 6th field `stage` vs the 5.11 synthetic 5-field row) + D3 (outcome vocabulary: real `{success, failed}` + unknown-outcome neutral mapping) + D4 (reader/route seam location under the `dashboard → telemetry` one-way module edge) BEFORE coding** (AC: 1, 2)
  - [ ] Record the picks in the PR Change Log (CONTRIBUTING §5). Verify the wave boundary once more: `agent_runs.jsonl`'s real record shape is `src/sdlc/telemetry/runs.py::_AgentRunLine` (2B.10 done+merged) — pin the exact persisted field names below, NOT the AC's logical names.

- [ ] **Task 1 — Reader seam: read `agent_runs.jsonl` through `telemetry/`, never re-parse in the dashboard (D4)** (AC: 1) — *tests-first*
  - [ ] The `dashboard` package MUST NOT import `sdlc.cli._agent_runs` — `cli` is not a declared `dashboard` dependency (`dashboard.depends_on = {errors, state, journal, telemetry, signoff, config, concurrency}`; forbidden from `{engine, dispatcher, runtime, hooks, adopt}`) [scripts/module_boundary_table.py:142-147]. Per D4, **lift the malformed-safe reader into `telemetry/`** (the module that OWNS `agent_runs.jsonl`, and a declared `dashboard` dep): add `read_agent_runs`/`iter_agent_runs` to `telemetry/` mirroring the proven `cli/_agent_runs.py::iter_agent_runs` contract — *missing file → empty; `JSONDecodeError` → WARNING + skip; non-`dict` line → WARNING + skip* [src/sdlc/cli/_agent_runs.py:14-50]. Keep the CLI reader working (import the shared telemetry reader from `cli/_agent_runs.py`, or leave both — DRY per D4). Keep the new module ≤ 400 LOC [scripts/check_module_boundaries.py:163].
  - [ ] Run `scripts/check_module_boundaries.py` on the new/edited files → GREEN (assert `dashboard → telemetry` is an allowed edge and `telemetry` still imports nothing forbidden; `telemetry.depends_on = {errors, contracts, journal, concurrency}`) [module_boundary_table.py:73-76].

- [ ] **Task 2 — Server route: `/api/activity` serving last-50 reverse-chron, field-mapped, validated (D1, D4)** (AC: 1, 2) — *tests-first*
  - [ ] Add `dashboard/routes/activity.py::register_activity_route(router, *, repo_root)` and wire it in `build_router` next to `register_state_route` / `register_dora_route` [src/sdlc/dashboard/server.py:89-93]. Mirror the `routes/state.py` / `routes/dora.py` shape (Response envelope, `Content-Type: application/json; charset=utf-8`). Read `.claude/state/agent_runs.jsonl` (confirm the real repo-relative path from the writer's caller) via the Task-1 telemetry reader.
  - [ ] **Server-side projection (D1 mapping):** map each real `_AgentRunLine` dict → the feed's display shape, sort **reverse-chronological by `ts`** (most recent first), **truncate to the last 50**, and emit ONLY the display fields (do NOT leak `tokens_in`/`tokens_out`/`dispatch_prompt`/`attempts`/`mock`). Field map (see Dev Notes "REAL schema"): `id ← run_id`, `ts ← ts`, `agentName ← specialist_name`, `targetId ← target_path`, `stage ← workflow_step`, `outcome ← outcome`, `durationMs ← duration_ms`.
  - [ ] Route MUST NOT 500 on a malformed/partial/truncated `agent_runs.jsonl` (bad lines skipped by the reader) or a missing file (→ empty list, 200). Optional but recommended: a short in-memory cache like `routes/dora.py` (the feed already polls at 3 s; keep it simple — no cache is acceptable for a bounded 50-row read).

- [ ] **Task 3 — Feed source swap: fetch `/api/activity`, keep the 5.11 render SEAM (do-not-regress)** (AC: 1, 2) — *tests-first*
  - [ ] In `activity-feed.js`, add a real-data path that fetches `/api/activity` and feeds the mapped entries into the EXISTING `renderActivityFeed(host, {entries})` seam. **Do NOT rewrite the render loop** — the 5.11 review HIGH fix (reverse-iterate insert → newest-on-top; `removeChild(list.lastChild)` evicts the genuine oldest) at [activity-feed.js:119-133] is guarded by a Playwright witness and MUST be preserved. The synthetic `buildSyntheticEntries` path may remain for the fixture, but the real path is the default when served by the dashboard.
  - [ ] Poll on the 3 s cycle (reuse the dashboard's existing poll, do not add a second timer): re-fetch `/api/activity`, pass through `renderActivityFeed` → new entries **prepend**, existing DOM nodes untouched (NFR-PERF-4 — "only changed sections re-render"). No fade-in / no CSS transition (DD-06/DD-14).

- [ ] **Task 4 — Add the 6th field `stage` to the feed row (D2)** (AC: 1)
  - [ ] The AC lists **6 fields** (ts, agent name, target id, **stage**, outcome, duration_ms); the 5.11 synthetic row rendered **5** (no `stage`) [activity-feed.js:66-89]. Add a `stage` cell sourced from `workflow_step`, extend `.activity-feed__entry` `grid-template-columns` from 5 → 6 columns [activity-feed.css:19-26] using `var(--*)` only (5.2 stylelint gate). textContent-only (never innerHTML).

- [ ] **Task 5 — Fold the four deferred-from-5.11 hardening fixes (DEF-1..DEF-4)** (AC: 1, 2) — *tests-first*
  - [ ] **DEF-1 — per-host immutable state store** [activity-feed.js:132-138] — `prependActivityFeedEntry` mutates the shared exported `SYNTHETIC_ACTIVITY_FEED_FIXTURE` singleton via `host._fixtureRef` (two `<activity-feed>` on one page share + overwrite state; violates the immutability rule). Give each host its own state object; treat updates immutably (clone-on-write, do NOT default-mutate the shared singleton). [deferred-work.md:920]
  - [ ] **DEF-2 — missing-`id` dedupe** [activity-feed.js:69,114-119] — `row.dataset.entryId = entry.id` stores `"undefined"` while the dedupe Set is checked with the value `undefined` → a real entry lacking an id re-inserts on every poll (unbounded duplicates). Key by `entry.id ?? \`row-${index}\`` **consistently** on BOTH the `dataset` write and the `existingIds` Set check. (Real rows carry `run_id`, mapped to `id` in Task 2 — but guard defensively.) [deferred-work.md:921]
  - [ ] **DEF-3 — unknown-outcome neutral mapping** [activity-feed.js:42-43] — `OUTCOME_GLYPH[outcome] || OUTCOME_GLYPH.error` maps ANY value outside the known set to the red `error` glyph + "Error", mislabeling e.g. a `running`/`timeout`/`skipped` run as a failure. Per D3, map real `success`→`check`, `failed`→`slash-circle`, and route ANY unknown outcome to a **neutral** glyph+label (NOT the red error glyph); render the raw outcome string as text. Reuse only frozen sprite icons (check/slash-circle/error/warning) → no new icon, no ADR. [deferred-work.md:922]
  - [ ] **DEF-4 — missing-field fallback** [activity-feed.js:71-85] — `textContent = entry.timestamp` (and agent/target/stage/duration) coerces a missing field to the literal `"undefined"`. Guard each cell with a fallback: `entry.x ?? "—"`. [deferred-work.md:923]

- [ ] **Task 6 — Data-validation / XSS-safety (the distinguishing requirement, DAG §5:294)** (AC: 1, 2) — *tests-first*
  - [ ] **Untrusted-input resilience (server + client):** a truncated last line, an invalid-JSON line, a non-object line, a line missing required fields, and an unknown `outcome` value MUST NOT crash the feed. The telemetry reader skips + logs bad lines (Task 1); the route returns the valid subset (Task 2); the renderer falls back per DEF-3/DEF-4. Add tests for each malformed case (line skipped/logged, feed still renders the good rows).
  - [ ] **XSS-safety:** the renderer stays **textContent-only, never `innerHTML`** [activity-feed.js:58-88 uses `createElement`/`textContent`] — a field value like `<img src=x onerror=alert(1)>` or `"><script>` MUST render as inert text, not markup/executed script. Add a behavioral (Playwright) test injecting a script-like payload in `agentName`/`targetId`/`stage` and asserting no element is created from it and `textContent` matches verbatim.

- [ ] **Task 7 — Tests: static contracts + reader/route unit + Playwright witnesses** (AC: 1, 2) — *tests-first*
  - [ ] Update the 5.11 static-analysis grep contract [tests/unit/dashboard/test_tabs_activity_feed_fixture.py:73-91] for the **real field names** (`agentName`, `targetId`, **`stage`**, `outcome`, `durationMs`) — the current `("timestamp","agentName","targetId","outcome","duration")` set (line 75) and the `buildSyntheticEntries(50)` grep (line 70) must reconcile with the swapped source; do not leave a stale grep that green-lights the wrong shape (the 5.11 HIGH shipped *because* a substring grep couldn't see the render).
  - [ ] New Python unit suite for the telemetry reader + `/api/activity` route: reverse-chron ordering, last-50 truncation, field projection (real→display), leaked-field exclusion, malformed-line skip, missing-file → empty/200. Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`).
  - [ ] Extend the Playwright suite [tests/integration/test_dashboard_activity_feed_empty_state.py:75-145] with a REAL-DATA fixture: newest-on-top + poll-prepends-newest + evict-oldest (do-not-regress), incremental-render (existing nodes retain identity), the DEF-2/3/4 edge rows, and the Task-6 XSS payload. RED against the un-swapped code → GREEN after Tasks 1–6.

- [ ] **Task 8 — Packaging + quality gate + freeze** (AC: 1, 2)
  - [ ] Add any NEW static assets (real-data `activity-feed` fixture + a route-demo fixture if added) to the `force-include` block [pyproject.toml:74-133] following the 5.5-frozen `static/components/<name>/` convention. New Python (`telemetry/` reader, `dashboard/routes/activity.py`, tests) is importable — no force-include needed.
  - [ ] Component CSS uses `var(--*)` only (5.2 stylelint gate); DD-14 motion gate (no transitions — feed changes are content/keyed-diff prepends), DD-08 no-framework, DD-09 no-`data-theme`, 5.5 color-only gate (outcome glyph + `stage` carry adjacent text). `scripts/check_module_boundaries.py` GREEN.
  - [ ] Python quality gate on the new reader/route/tests: ruff + ruff format + mypy --strict; full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7** (`agent_runs.jsonl` is NOT an ADR-024 frozen contract — runs.py:1-17).

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

### Debug Log References

### Completion Notes List

### File List

## Change Log

- 2026-07-01: Story 5.16 created (create-story, "flip done 5.12 + tạo all US cho layer tiếp theo" → L6/5B batch-1). Activity Feed real-data swap onto the 5.11 render seam: read the real `agent_runs.jsonl` through a lifted `telemetry/` reader (never re-parse wire files; `dashboard → telemetry` one-way edge, DAG §5), serve last-50 reverse-chron via a new `/api/activity` route with a server-side real→display field projection, add the AC's 6th `stage` cell, and fold the four deferred-from-5.11 hardening fixes (DEF-1 per-host immutable store / DEF-2 missing-id dedupe / DEF-3 unknown-outcome neutral mapping / DEF-4 missing-field fallback). Data-validation is first-class (untrusted file content: malformed/partial/truncated JSONL skipped+logged, must not crash or XSS the feed — textContent-only). Decisions raised: D1 (real→display field mapping / name drift: specialist_name/target_path/workflow_step/duration_ms int/run_id vs synthetic names), D2 (feed 6-field reconcile — add `stage`), D3 (outcome vocabulary `{success, failed}` + neutral unknown mapping), D4 (reader/route seam lifted into `telemetry/`, consumed by cli+dashboard). Do-not-regress the 5.11 newest-on-top + evict-oldest HIGH fix (Playwright-guarded). Zero wire-format change (agent_runs is a private model, not ADR-024 frozen → freeze 7/7). Wave-boundary: 2B.10 done+merged (verify Phase-3 specialists emit real `_AgentRunLine` records at branch time). Anti-scope-creep: swap the feed source only; do NOT build 5.13/5.14/5.15/5.17/5.18/5.19.
