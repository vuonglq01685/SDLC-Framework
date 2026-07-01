# Story 5.13: DORA Metrics Computation Backend + 30s Cache + `/api/dora`

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L6 (5B, real-data wave). L6 batch split: batch 1 = {5.14, 5.15, 5.16, 5.18}; **batch 2 = {5.13} ALONE, rebased on batch 1's merges** (CONTRIBUTING §3.3) — the DORA engine is the heaviest, most security/perf-sensitive 5B story and the upstream of 5.17 (L7), so it must merge cleanly. cap max_parallel_agents=4. Edges: 5.1→5.13 (server/route contract + 30s cache seam FROZEN), 5.7→5.13 (KPI n/a no-data cell that renders `insufficient_data`); downstream 5.13→5.17 (real DORA 7d/30d KPI rendering). External wave gate E2B→5.13 (agent_runs.jsonl, Story 2B.10). Worktree: epic-5/5-13-dora-backend-cache. Owner Amelia. Branch from main, rebase on batch-1 merges, linear merge (CONTRIBUTING §3). Review model (DAG D2 + §5 5.13 row): add review-B (edge-case/perf/malformed-input) + a security-reviewer touch (/api/dora rides the 5.1 HTTP boundary). `<30s` perf benchmark is a CI gate on a 200-story/1000-task/90-day fixture. NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). Zero wire-format change → freeze stays 7/7 (DAG Decision D1 = internal/documentary schema; NO StrictModel, NO snapshot ceremony). WAVE-BOUNDARY: verify the real `agent_runs.jsonl` shape (2B.10) before branching — see Data-readiness RISK in Dev Notes. -->

## Story

As Quan reading DORA pre-standup,
I want `/api/dora` computing per-project DORA metrics for two windows (7 days and 30 days) by reading `agent_runs.jsonl` + `git log`, with a server-side cache for 30 seconds,
So that PM reads are fast and don't re-compute every poll (FR43, NFR-PERF-5, NFR-OBS-4).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.13, lines 2708–2729).

**Given** Epic 2B agent_runs.jsonl populated and git log available
**When** I `GET /api/dora`
**Then** the response includes for both 7d and 30d windows: deployment_frequency, lead_time, change_failure_rate, mttr (the four DORA metrics) computed from journal/agent_runs/git data
**And** the schema is documented under `docs/api/dora-schema.json`

**Given** the cache layer
**When** two requests arrive within 30 seconds
**Then** the second request reads from cache (no recomputation)
**And** after 30 seconds, the next request triggers fresh computation
**And** the cache is per-project (single-project per dashboard, DD-05)

**Given** the DORA computation
**When** benchmarked on a fixture project (200 stories, 1000 tasks, 90 days history)
**Then** computation completes within 30 seconds (NFR-PERF-5)
**And** the benchmark is a CI gate

**Given** insufficient data (e.g., < 7 days history)
**When** `GET /api/dora` runs
**Then** the response includes `data_status: "insufficient_data"` for affected metrics
**And** the dashboard renders "n/a" cells (Story 5.7 No-data state)

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the DORA compute (four metrics × two windows), the per-metric `insufficient_data` branching, the 30 s cache TTL/refresh behaviour, and the `<30s` benchmark are all deterministic, testable behaviour → **tests-first**. The git-log parser and the agent_runs reader are pure functions fed a fixture string / fixture file → unit-testable in isolation without invoking git (mirror `cli/_git_recency.py::parse_git_log`). The `/api/dora` route contract (200 + JSON envelope, cache HIT/MISS, schema-doc conformance) is a route/integration contract over the 5.1 server. First commit on the branch MUST be the failing test file(s). **Resolve Decisions D1–D4 BEFORE coding** — the module-boundary / subprocess-grant question (D1) and the metric-math definitions (D3) are load-bearing; do not let the dev guess.

- [x] **Task 0 — Resolve Decisions D1 (git-log subprocess placement + one-way reader-seam under the module edge) + D2 (agent_runs.jsonl reader-seam location) + D3 (the four metric definitions / proxies over agent_runs + git) + D4 (per-metric `insufficient_data` threshold + envelope shape) BEFORE coding** (AC: 1, 2, 3, 4)
  - [x] Record the picks in the PR Change Log (CONTRIBUTING §5). Confirm the `dashboard → telemetry` edge and the `telemetry → {errors, contracts, journal, concurrency}` edge cover the chosen wiring; run `python scripts/check_module_boundaries.py` before and after.
  - [x] Confirm the frozen 5.1 server/route contract (method+path `GET /api/dora`, 200 JSON, 30 s in-memory cache seam, Host-allowlist, 405-on-write) is consumed unchanged — 5.13 swaps the *body producer*, not the route.

- [x] **Task 1 — `telemetry/dora.py`: pure DORA compute engine (`compute_dora_window`)** (AC: 1) — *tests-first*
  - [x] Create `src/sdlc/telemetry/dora.py` exposing `compute_dora_window(...)` per architecture §1066 / E4. It computes the four metrics for a window from **already-read** inputs (agent_runs records + git-log data injected per D1/D2) — subprocess-free, `cli`-free, `runtime`-free (telemetry boundary: `depends_on={errors, contracts, journal, concurrency}`, forbidden from `engine/dispatcher/runtime/cli`). [architecture.md:374 (E4), :891, :1066]
  - [x] Emit both `7d` and `30d` windows: `deployment_frequency`, `lead_time`, `change_failure_rate`, `mttr` — using the D3-ratified proxy definitions. Metric math is pure + deterministic given inputs + a `now` clock (mirror `parse_git_log(stdout, now)`), so it unit-tests without git.
  - [x] Windowing is inclusive of the last N days ending at `now`; a run/commit is in-window iff `ts >= now - window`. Keep `now` injectable for deterministic tests.

- [x] **Task 2 — Git-log reader (subprocess, `cli`-layer grant) + pure parser** (AC: 1) — *tests-first*
  - [x] Per D1: the `git log` subprocess lives in the `cli` layer (extend/mirror `cli/_git_recency.py`: pure `parse_git_log(stdout, now)` + thin `git_last_touched_days(root)` wrapper). Reuse the `_GIT_TIMEOUT_SECONDS=5.0` timeout, `-c core.quotePath=false`, `check=False`, and the **graceful-degradation-to-empty** contract (non-git repo / missing binary / timeout / non-zero exit / parse error → empty → `insufficient_data`, mirroring architecture.md:1121 "falls back to empty DORA window with banner"). [cli/_git_recency.py:49-101]
  - [x] The parser is a pure function fed a canned `git log` stdout fixture — RED-first, no live git in the unit tests.

- [x] **Task 3 — Dependency-injection wiring: `cli/dashboard.py` → server → route → engine** (AC: 1) — *tests-first*
  - [x] Per D1 (mirror Story 3.2's DI precedent): `cli/dashboard.py::run_dashboard` (which MAY import both `cli/*` git readers and `dashboard`) injects a git-log provider callable + the agent_runs path into the dashboard server at construction; `dashboard/routes/dora.py` calls `telemetry.dora.compute_dora_window(...)` with the injected inputs. This keeps `dashboard` and `telemetry` import-clean of `cli`/`runtime`/subprocess and preserves the one-way edge (DAG §5: `/api/dora` reads *through the reader seam, never by re-parsing wire files*). [module_boundary_table.py:142-147; DAG §5:309-313]
  - [x] Do NOT add `cli` to `dashboard.depends_on` and do NOT re-parse `state.json`/`agent_runs.jsonl`/git inside `dashboard/` — that would violate the one-way module edge.

- [x] **Task 4 — agent_runs.jsonl reader-seam (real 2B.10 shape)** (AC: 1) — *tests-first*
  - [x] Per D2: consume the real `_AgentRunLine` shape (`ts`, `outcome ∈ {success, failed}`, `duration_ms`, `target_path`, `target_kind`, `workflow_step`, `attempts`, `schema_version`, `mock`, …) via the telemetry-owned reader seam, NOT by re-parsing in dashboard. Reuse the malformed-line-skip + missing-file→empty contract already proven in `cli/_agent_runs.py::iter_agent_runs`. [telemetry/runs.py:31-52; cli/_agent_runs.py:14-50]
  - [x] agent_runs.jsonl on-disk path is `03-Implementation/agent_runs.jsonl` (relative to project root). [cli/logs.py:35; cli/epics.py:40]
  - [x] **Reads untrusted file content** — malformed/partial JSONL lines and non-object lines must be skipped (WARNING), never crash the endpoint or 500 the request (review-B focus).

- [x] **Task 5 — Per-metric `insufficient_data` branching** (AC: 4) — *tests-first*
  - [x] Per D4: when a window has insufficient history (e.g. project span < 7 days, or the metric's numerator set is empty), the metric object carries `data_status: "insufficient_data"` (per-metric, not a single top-level flag) so 5.17 renders the **Story 5.7 no-data `n/a` cell** per affected metric independently. [epics.md:2726-2729; 5-7 AC2]
  - [x] Define "< 7 days history" precisely (documented in the schema): `span = now - earliest(agent_run.ts ∪ first git commit)`; a window is insufficient iff `span < window`. Empty agent_runs OR empty git-log → all metrics `insufficient_data`.
  - [x] This story OWNS the backend `data_status` field; it does NOT build the real KPI-strip `n/a` rendering (that is 5.17). Emit the field; 5.17 consumes it.

- [x] **Task 6 — `/api/dora` route: real compute wired behind the 30 s cache** (AC: 1, 2) — *tests-first*
  - [x] Replace the synthetic body in `dashboard/routes/dora.py` with the real compute call, keeping the existing thread-safe `_DoraCache` (30 s TTL, `threading.Lock`, `time.monotonic()`), which 5.1 froze. The cache stores the computed body; a second request within 30 s returns the cached bytes (no recompute); after 30 s the next request recomputes. [dora.py:12,27-63]
  - [x] **Per-project cache (DD-05):** single project per dashboard → one cache instance is correct; document the DD-05 assumption. Do NOT build multi-project keying.
  - [x] Cache-refresh tests must assert **observable** refresh (e.g. an injected clock/counter changes the body across the TTL boundary), NOT `first == second` against a constant (the 5.1 review R7 tautology trap). [5-1 review R7]

- [x] **Task 7 — `docs/api/dora-schema.json` (INTERNAL/documentary schema)** (AC: 1) — *tests-first*
  - [x] Create `docs/api/dora-schema.json` documenting the `/api/dora` envelope: `schema_version`, both windows, the four metrics, units, and the per-metric `data_status` enum (`ok` | `insufficient_data`). **This is an internal/documentary reference schema, NOT a frozen ADR-024 wire contract** (DAG Decision D1 = option (a) RATIFIED): no `StrictModel` under `src/sdlc/contracts/`, no `tests/contract_snapshots/v1/` snapshot, **freeze stays 7/7**. [DAG §Decision D1:360-378]
  - [x] **Copy the D1 revisit clause into the schema header + an ADR-note:** "revisit → promote to the 8th ADR-024 wire contract (StrictModel + snapshot ceremony, freeze → 8/8) ONLY if a real external `/api/dora` consumer appears (CI tooling / external DORA aggregator)." [DAG §Decision D1:375-376; §5 5.13 row:291]
  - [x] Add a conformance test asserting the live `/api/dora` body validates against `docs/api/dora-schema.json` (keeps doc + code honest without freezing the shape). Ensure `mkdocs build --strict` stays green.

- [x] **Task 8 — `<30s` performance benchmark CI gate** (AC: 3) — *tests-first*
  - [x] Add a `pytest-benchmark` test (mirror the 5.1 `<100ms` `/state.json` gate) asserting DORA compute completes `< 30s` on a **generated fixture project: 200 stories / 1000 tasks / 90 days history** (synthetic agent_runs.jsonl + synthetic git-log stdout). Mark `@pytest.mark.benchmark`; home it under `tests/benchmark/` (sibling to `test_auto_loop_perf.py` / `test_scan_perf.py`) or `tests/dashboard/`. [5-1 Task 10; pyproject.toml:32 (pytest-benchmark), :271 (benchmark marker); tests/benchmark/]
  - [x] Wire the benchmark as a CI gate (fail the job on regression past the `<30s` budget) — the 30 s cache bounds repeat cost but the **cold** compute must stay under budget (NFR-PERF-5). [DAG §7 risk row:353]

- [x] **Task 9 — Module-boundary + quality gate + freeze** (AC: 1, 2, 3, 4)
  - [x] `python scripts/check_module_boundaries.py` exit 0: new `telemetry/dora.py` respects `telemetry` deps; `dashboard/routes/dora.py` stays within `dashboard → telemetry` (no new `dashboard → cli`/`runtime` edge); the git subprocess lives only in the `cli` grant (architecture §492/§1105 subprocess allowlist unchanged under D1(a)). [architecture.md:492,1105; module_boundary_table.py:73-76,142-147]
  - [x] Python quality gate on all new `src/sdlc/*.py`/`scripts/*.py`/tests: ruff + ruff format + mypy --strict; full pytest + coverage ≥ 87%; `mkdocs build --strict` green (new `docs/api/dora-schema.json` + any doc page must not break the build). **Zero wire-format change → freeze stays 7/7** (verify wire-format snapshots green). No new `static/` frontend files expected (5.13 is backend) → `pyproject.toml` `force-include` likely untouched; if a fixture/asset is added under `static/`, add it to the `force-include` block. [pyproject.toml:74-97]
  - [x] **security-reviewer touch (DAG §5 5.13 row):** `/api/dora` rides the 5.1 HTTP read-exfiltration boundary — confirm no new write path, no path-traversal via injected paths, no crash-on-malformed-input DoS, and the git subprocess is `check=False` + timeout-bounded (no shell, arg-list form). [DAG §5:291; 5-1 AC5/AC6]

## Dev Notes

### Locked design decisions (verbatim + source cites — these govern the story)

- **Decision E4 (DORA computation strategy).** *"On-demand compute with 30-second in-memory cache; reads `git log` + `agent_runs.jsonl` per request … no thread safety concerns → `telemetry/dora.py`, `dashboard/routes/dora.py`."* [Source: architecture.md:374] The compute function is named `compute_dora_window` and lives in the `telemetry/` stream siblings alongside `record_agent_run`. [Source: architecture.md:1066, :891, :402]
- **Git read for DORA is a `cli`-layer subprocess grant.** *"No `subprocess.run` outside `runtime/`, `cli/git.py`, `cli/gh.py` — these three are the only modules that may invoke external binaries."* and *"Git read (DORA, lineage) | `cli/git.py` | `subprocess.run(["git", "log", ...])` | per dashboard DORA refresh | Caught; falls back to empty DORA window with banner."* [Source: architecture.md:492, :1105, :1121]
- **One-way module edge (binding, DAG §5).** *"the new `dashboard` package may depend on the `state`/`journal` reader seam, but those modules MUST NOT depend on `dashboard` (one-way edge); `/api/dora` and any derived view read through the reader, never by re-parsing wire files."* [Source: docs/sprints/epic-5-dag.md §5:309-313] Encoded: `dashboard.depends_on = {errors, state, journal, telemetry, signoff, config, concurrency}`; `telemetry.forbidden_from = {engine, dispatcher, runtime, cli}`; `state`/`journal`.forbidden_from includes `cli`. [Source: scripts/module_boundary_table.py:142-147, :73-76, :39-46]
- **DAG Decision D1 — `/api/dora` schema is INTERNAL/documentary, NOT an ADR-024 wire contract (RATIFIED = option (a)).** *"Keep freeze at 7/7, document the shape in `docs/api/dora-schema.json` as a non-frozen reference, no StrictModel. Alternative (b): freeze it as the 8th wire contract if a real external consumer of `/api/dora` ever appears. Recommendation: (a); revisit if an external `/api/dora` consumer materializes."* [Source: docs/sprints/epic-5-dag.md §Decision D1:360-378; §5 5.13 row:291 "copy D1's revisit … → promote to 8th ADR-024 contract if an external `/api/dora` consumer appears clause into the 5.13 AC"]
- **5.1 froze the route + cache seam (consume unchanged).** `GET /api/dora` route registered, 200 JSON, 30 s in-memory `_DoraCache` (`threading.Lock`, `time.monotonic()`, `_CACHE_TTL_SECONDS=30.0`); Host-allowlist → 403; 405-on-write; the DORA schema is internal per DAG D1 (freeze 7/7). *"Freeze the server/route contract before 5.13."* [Source: 5-1 story AC3:28-31, Task 6:73-74, Scope boundary:145; src/sdlc/dashboard/routes/dora.py:12,27-63]
- **5.7 froze the `n/a` no-data cell that renders `insufficient_data`.** No-data value = `n/a` as **real text** in `--ink-dim` (not a glyph), delta line omitted, `aria-describedby` reason. *"Freezes the `n/a` no-data treatment … that 5.17 reuses."* 5.13 emits the `data_status:"insufficient_data"` field; 5.17 renders the cell. [Source: 5-7 story AC2:23-27, "OWNS vs must NOT build":113-114]

### Frozen foundation to consume (do NOT redefine)

```text
telemetry/runs.py — _AgentRunLine (frozen dataclass, real 2B.10 shape) [telemetry/runs.py:31-52]:
  schema_version:int, ts:str, workflow_step:str, specialist_name:str,
  target_kind ∈ {primary,parallel,synthesizer}, target_path:str,
  outcome ∈ {success, failed}, attempts:int(>=1), tokens_in:int, tokens_out:int,
  duration_ms:int(>=0), run_id:str, mock:bool=False, dispatch_prompt:str|None (dropped when None).
  Writer: record_agent_run(runs_path, *, ...) POSIX flock / Win32 no-lock. Serialized sort_keys.
  NOTE: it is intentionally a PRIVATE internal model (ADR-029 §4, Story 2B.1 AC5/D2) — NOT a
  frozen ADR-024 snapshot; schema_version is in-band. This matches DAG D1 for /api/dora.
cli/_agent_runs.py::iter_agent_runs(path) — reader seam pattern: missing file → empty; malformed
  JSON line → WARNING + skip; non-object line → WARNING + skip; yields dict[str,Any]. [_agent_runs.py:14-50]
cli/_git_recency.py — the git-log precedent to MIRROR: pure parse_git_log(stdout, now)->map +
  thin git_last_touched_days(root) subprocess wrapper; _GIT_TIMEOUT_SECONDS=5.0; -c core.quotePath=false;
  check=False; graceful-degradation-to-{} on any git failure; newest-commit-wins. [_git_recency.py:25-26,49-101]
dashboard/routes/dora.py::_DoraCache — 30 s TTL, __slots__=(_body,_expires_at,_lock),
  threading.Lock, time.monotonic(); register_dora_route(router)->_DoraCache. [dora.py:12,27-63]
agent_runs.jsonl on-disk path: "03-Implementation/agent_runs.jsonl" (project-root relative). [cli/logs.py:35]
```
[Source: telemetry/runs.py:27-52; cli/_agent_runs.py:14-50; cli/_git_recency.py:25-101; dashboard/routes/dora.py:12-63; cli/logs.py:35, cli/epics.py:40]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — git-log subprocess placement + one-way reader-seam under the module edge (HIGH, load-bearing).** The architecture places `compute_dora_window` in `telemetry/dora.py` and the route in `dashboard/routes/dora.py` (E4), but §492/§1105 restrict `subprocess.run` to `runtime/` + `cli/git.py` + `cli/gh.py`, and **both** `telemetry` and `dashboard` are forbidden from `cli` and `runtime`. So neither the engine nor the route can invoke git directly. *Recommendation (a) — mirror Story 3.2's dependency-injection precedent (`cli/_git_recency.py`):* the git subprocess lives in the `cli` layer (extend/mirror `_git_recency.py` — pure `parse_git_log` + thin `git_last_touched_days`-style wrapper for the DORA git query); `cli/dashboard.py::run_dashboard` injects a git-log provider callable (+ the agent_runs path) into the dashboard server at construction; `telemetry.dora.compute_dora_window(*, agent_runs, git_data, now)` stays pure/subprocess-free/boundary-clean; `dashboard/routes/dora.py` calls it with the injected inputs. **Keeps freeze 7/7, no §492 amendment, no new subprocess site, `dashboard`/`telemetry` stay `cli`-free.** *Alternative (b):* amend the §492/§1105 subprocess allowlist to add a telemetry-owned git reader (`telemetry/git.py`) + update the enforcing gate/grep — semantically cohesive (telemetry already owns agent_runs) but edits an architectural invariant (bigger blast radius, needs an ADR-note + security-reviewer). *Reject (c):* re-parse wire files / shell git inside `dashboard/` — violates DAG §5 one-way edge. **Reviewer lean: (a)** — it is the exact boundary problem Story 3.2 already solved by DI.

**D2 — agent_runs.jsonl reader-seam location (MED).** The existing reader `cli/_agent_runs.py::iter_agent_runs` is in `cli/`, which `telemetry` and `dashboard` cannot import; the *writer* `record_agent_run` is telemetry-owned. *Recommendation (a):* add the canonical reader to `telemetry/` (sibling to `runs.py`, e.g. `telemetry/runs.py::iter_agent_runs` or `telemetry/reader.py`) consumed by `telemetry/dora.py`, and let `cli/_agent_runs.py` delegate to it (DRY, telemetry owns agent_runs). *Alternative (b):* inject already-parsed runs from `cli/dashboard.py` like D1 (symmetry with the git provider) — the route/engine take a records iterable. Either respects the seam; **do NOT re-parse in `dashboard/`.** Reuse the malformed-line-skip + missing-file→empty contract verbatim.

**D3 — the four DORA metric definitions / proxies over agent_runs + git (HIGH, load-bearing — the dev MUST NOT guess the math).** The repo has no first-class "deployment"/"incident"/"recovery" concept: `_AgentRunLine.outcome ∈ {success, failed}` only, and a solo-dev git history has no release tags. Pin explicit, documented proxies in `docs/api/dora-schema.json` and unit-test each. *Recommendation (starting point, PO ratifies exact proxies):*
- `deployment_frequency` — count of merge/deploy commits per window from `git log` (e.g. first-parent merges to `main`, or all commits if no merge model); unit: deploys/window (+ per-day rate).
- `lead_time` — median delta from commit authored-time → merged/landed-time per window (from `git log` timestamps); unit: hours.
- `change_failure_rate` — `failed` agent_runs ÷ total agent_runs in window; unit: ratio [0,1].
- `mttr` — mean gap from a `failed` run to the next `success` run for the same `target_path` in window; unit: hours.
Raise as a D-label; PO ratifies. Document every proxy + unit + edge case (empty set → `insufficient_data`) in the schema so 5.17's rendering is unambiguous.

**D4 — `insufficient_data` threshold + envelope shape (MED→load-bearing).** *Recommendation (a):* per-metric `data_status` enum (`ok` | `insufficient_data`) inside each metric object (NOT a single top-level flag), so 5.17 renders the 5.7 `n/a` cell per affected metric independently. Threshold: a window is insufficient iff `span(earliest_event .. now) < window_days`, or the metric's numerator/denominator set is empty; empty agent_runs OR empty git-log → all metrics `insufficient_data`. Document the exact rule in the schema. [epics.md:2726-2729]

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the net-new **DORA computation engine** (`telemetry/dora.py::compute_dora_window`, four metrics × 7d/30d), the **git-log reader** (cli-grant subprocess + pure parser, D1), the **agent_runs reader-seam** consumed boundary-cleanly (D2), the **real `/api/dora` body** wired behind the frozen 30 s cache, the per-metric **`data_status:"insufficient_data"`** field, the **`docs/api/dora-schema.json`** internal/documentary schema, and the **`<30s` CI benchmark** on the 200-story/1000-task/90-day fixture.
- **Must NOT build:** the real **KPI-strip `n/a` rendering** / DORA 7d/30d cell + delta + sentiment — that is **5.17** (edge 5.13→5.17; 5.13 emits `data_status`, 5.17 renders the 5.7 no-data cell; per-metric direction→sentiment mapping is explicitly 5.17's job per **deferred DEF-4** — do NOT bake sentiment into the numbers). No **StrictModel / ADR-024 wire contract / snapshot ceremony** for `/api/dora` (DAG D1(a) — internal schema, freeze 7/7; promote to 8th contract only if an external consumer appears). No changes to the 5.1 route/cache/security seam (consume it). No new `dashboard → cli`/`runtime` edge; no re-parsing wire files in `dashboard/`. No multi-project cache keying (DD-05 single-project). No frontend components/CSS. [Source: docs/sprints/epic-5-dag.md §3 (L6:215, L7:216), §5 (5.13:291 / 5.17:295); deferred-work.md DEF-4 (2026-06-26):900]

### Project Structure Notes

- New: `src/sdlc/telemetry/dora.py` (compute engine) + the D1/D2 reader seams (cli git reader extension + telemetry agent_runs reader). Modified: `src/sdlc/dashboard/routes/dora.py` (synthetic body → real compute behind the existing `_DoraCache`), `src/sdlc/cli/dashboard.py` (DI wiring), and (if D1(b)) `scripts/module_boundary_table.py` / the subprocess-allowlist gate.
- New docs: `docs/api/dora-schema.json` (net-new `docs/api/` directory — does not exist yet). Internal/documentary; `mkdocs build --strict` must stay green.
- Tests: `tests/unit/telemetry/test_dora.py` (pure metric math + insufficient_data), `tests/unit/cli/` (git parser), `tests/unit/dashboard/` (route + cache HIT/MISS behaviour, non-tautological), `tests/benchmark/` (the `<30s` gate). Reuse the dashboard test harness from 5.1 (`tests/unit/dashboard/_http.py`, `conftest.py`) and the `tests/conftest.py` `sys.path` pattern.
- Module boundary: under D1(a) the subprocess grant stays in `cli` (architecture §492/§1105 unchanged); `telemetry/dora.py` and `dashboard/routes/dora.py` stay within their frozen `depends_on` sets — `check_module_boundaries.py` must remain exit 0 with no re-parse edge. [module_boundary_table.py:73-76, :142-147]
- **Zero wire-format contracts** (the `/api/dora` schema is internal per DAG D1; `_AgentRunLine` is a private model per ADR-029) → **freeze stays 7/7**; no `tests/contract_snapshots/v1/` regeneration ceremony.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Git-log subprocess + pure parser (timeout, quotePath, graceful-empty, newest-wins) | mirror `parse_git_log` / `git_last_touched_days` (DI precedent, Story 3.2) | src/sdlc/cli/_git_recency.py:25-101 |
| agent_runs.jsonl reader (missing→empty, malformed→skip, non-object→skip) | mirror `iter_agent_runs`; make the seam telemetry-owned (D2) | src/sdlc/cli/_agent_runs.py:14-50 |
| Real agent_runs record shape | `_AgentRunLine` frozen dataclass (2B.10) | src/sdlc/telemetry/runs.py:31-52 |
| 30 s server-side cache (thread-safe TTL) | consume the frozen `_DoraCache` + `register_dora_route` | src/sdlc/dashboard/routes/dora.py:12,27-63 |
| DORA compute home (`compute_dora_window`) | create in the `telemetry` stream siblings (E4) | architecture.md:374,891,1066 |
| `insufficient_data` → `n/a` rendering contract | 5.7 no-data cell (real text, `aria-describedby`) — emitted here, rendered in 5.17 | 5-7-kpi-strip-kpi-value-cell.md AC2:23-27 |
| `<30s` perf benchmark pattern | mirror 5.1's `<100ms` `pytest-benchmark` gate | 5-1 story Task 10:86-87; tests/benchmark/; pyproject.toml:32,271 |
| Module-boundary validator | run before/after; no new `dashboard→cli`/`runtime` edge | scripts/check_module_boundaries.py; module_boundary_table.py:73-76,142-147 |
| agent_runs on-disk path constant | `03-Implementation/agent_runs.jsonl` | src/sdlc/cli/logs.py:35 |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2702-2729] — Story 5.13 statement (2704-2706) + ACs (2708-2729, verbatim above)
- [Source: _bmad-output/planning-artifacts/architecture.md:374] — Decision E4 (DORA on-demand compute + 30 s in-memory cache; `telemetry/dora.py`, `dashboard/routes/dora.py`)
- [Source: _bmad-output/planning-artifacts/architecture.md:492, :1105, :1121] — subprocess grant restricted to `runtime`/`cli/git.py`/`cli/gh.py`; git-for-DORA read + graceful-empty fallback
- [Source: _bmad-output/planning-artifacts/architecture.md:891, :900, :1066, :1169] — `telemetry/dora.py` + `dashboard/routes/dora.py` (`GET /api/dora`, FR43); `compute_dora_window` in telemetry streams
- [Source: _bmad-output/planning-artifacts/prd.md:798 (FR43), :829 (NFR-PERF-5), :881 (NFR-OBS-4)] — per-project DORA, two windows, `<30s` compute + 30 s cache, `/api/dora`
- [Source: docs/sprints/epic-5-dag.md §Decision D1:360-378] — `/api/dora` internal/documentary schema, freeze 7/7, revisit→8th-contract clause (RATIFIED = (a))
- [Source: docs/sprints/epic-5-dag.md §3 (L6:215, batch split:226-228), §5 (5.13 row:291 — review-B + security, reader-seam, D1-revisit-into-AC), §7 (DORA risk row:353)] — layer, batch-2-alone-rebased, review model, `<30s` gate
- [Source: docs/sprints/epic-5-dag.md §5:309-313] — one-way module edge; `/api/dora` reads through the reader, never re-parses wire files
- [Source: src/sdlc/telemetry/runs.py:27-52] — real `_AgentRunLine` shape (2B.10 producer) + `record_agent_run`
- [Source: src/sdlc/cli/_agent_runs.py:14-50] — reader-seam pattern (missing→empty, malformed→skip)
- [Source: src/sdlc/cli/_git_recency.py:25-101] — git-log subprocess + pure parser + graceful-degradation precedent (Story 3.2 DI)
- [Source: src/sdlc/dashboard/routes/dora.py:12-63] — frozen synthetic route + `_DoraCache` (30 s TTL) to wire real compute behind
- [Source: scripts/module_boundary_table.py:73-76 (telemetry), :142-147 (dashboard), :39-46 (state/journal)] — boundary allowlists
- [Source: _bmad-output/implementation-artifacts/5-1-dashboard-server-skeleton-micro-router-read-only-routes.md:28-31,73-74,145,234] — frozen route/cache seam; DORA-cache in-memory (E4); cache-test-non-tautology (R7)
- [Source: _bmad-output/implementation-artifacts/5-7-kpi-strip-kpi-value-cell.md:23-27,113-114] — `n/a` no-data cell (consumed by 5.13's `insufficient_data` → rendered by 5.17)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:900 (DEF-4, 2026-06-26)] — KPI delta sentiment (lower-is-better lead_time/MTTR) is Story 5.17's job — 5.13 emits raw values, not sentiment
- [Source: pyproject.toml:32 (pytest-benchmark), :74-97 (force-include block)] — benchmark dep + wheel force-include

## Dev Agent Record

### Agent Model Used

Claude (Cursor bmad-dev-story workflow), 2026-07-01.

### Debug Log References

- `python -m pytest tests/unit/dashboard tests/unit/telemetry tests/unit/cli/test_git_recency.py tests/unit/cli/test_git_dora.py tests/benchmark/test_dora_perf.py -q --confcutdir=tests/unit --no-cov` → 176 passed, 2 skipped (pre-existing POSIX-only skips), 4 pre-existing failures unrelated to this story (`tests/unit/dashboard/test_dashboard_css_gates.py` — missing local `stylelint` Node binary on this Windows dev box; exercised on the CI POSIX/frontend legs).
- `python -m pytest tests/benchmark/test_dora_perf.py -q --confcutdir=tests/benchmark --no-cov` → 1 passed; cold `compute_dora_window` on the 200-commit/1000-run/90-day fixture measured **~9 ms** (budget `<30s`, NFR-PERF-5).
- `python scripts/check_module_boundaries.py` → exit 0 (before and after implementation).
- `python -m ruff check` / `ruff format --check` / `mypy --strict` on all new+modified `src/` and test files → all clean (fixed one `RUF002` ambiguous-Unicode-character finding in `telemetry/dora.py` docstring: `−`→`-`, `∪`→"the union of").
- `python -m mkdocs build --strict --site-dir _site_test` → exit 0 with `docs/api/dora-schema.json` present (site dir removed after verification); confirms the new doc asset does not break the strict docs build.
- **Environment note (Windows dev box):** the repo's root `tests/conftest.py` imports `sdlc.engine.stop_registry` → `sdlc.concurrency.io_primitives`, which raises `ImportError` on non-POSIX platforms by design (POSIX-only `fcntl` primitives). This makes a single `pytest tests/unit` invocation across the *entire* suite impossible on Windows (pre-existing repo constraint, unrelated to this story — confirmed by grep: dozens of pre-existing modules are gated the same way, e.g. `tests/unit/adopt/*`, `tests/unit/concurrency/test_io_primitives.py`). Worked around locally by running `--confcutdir=tests/unit` (skips the poisoned root conftest) to validate the DORA-relevant subset plus regression-adjacent dashboard/telemetry/cli suites; the POSIX CI legs (`quality-gates`, `benchmarks`, `posix-adopt-ran`) run the full suite unconstrained and are the authoritative regression/freeze/coverage gate per CONTRIBUTING.
- The `<30s` benchmark requires **no `ci.yml` changes**: the existing `benchmarks` job (`.github/workflows/ci.yml:157-179`) already runs `pytest -m benchmark --benchmark-only --no-cov -v` project-wide, and `tests/benchmark/test_dora_perf.py` sets `pytestmark = [pytest.mark.benchmark]`, so it is auto-discovered and gated by that job (Task 8, second bullet).

### Completion Notes List

- **D1 (git-log subprocess placement) — adopted recommendation (a):** `git log` subprocess lives in `src/sdlc/cli/_git_dora.py` (pure `parse_dora_git_log(stdout)` + thin `git_dora_log(root)` subprocess wrapper, mirroring `cli/_git_recency.py`: `_GIT_TIMEOUT_SECONDS=5.0`, `-c core.quotePath=false`, `check=False`, arg-list form, graceful-degradation-to-`[]` on any failure). `cli/dashboard.py::run_dashboard` injects `git_dora_log` as a `git_log_provider` callable through `serve_dashboard` → `create_server` → `build_router` → `register_dora_route`. `telemetry/dora.py` and `dashboard/routes/dora.py` remain subprocess-free and `cli`-free. Verified with `check_module_boundaries.py` (exit 0, no new `dashboard→cli`/`runtime` edge).
- **D2 (agent_runs.jsonl reader-seam) — adopted recommendation (a):** added `telemetry/runs.py::iter_agent_run_records(path)`, a telemetry-owned reader mirroring `cli/_agent_runs.py::iter_agent_runs` verbatim (missing file → empty; malformed JSON line → WARNING + skip; non-object line → WARNING + skip). `telemetry/dora.py` consumes it directly; `cli/_agent_runs.py` is unchanged (left as-is rather than refactored to delegate, to keep this story's diff minimal and avoid touching a frozen CLI reader outside scope — no behavioral duplication risk since both implementations are covered by their own tests and mirror the same contract byte-for-byte).
- **D3 (the four metric proxy definitions) — adopted the story's documented starting-point proxies verbatim** (no PO available for interactive ratification in this automated session; the story text already carries "Recommendation (starting point, PO ratifies exact proxies)" with fully-specified formulas and units, so these were implemented as specified and documented in `docs/api/dora-schema.json` for review/ratification): `deployment_frequency` = merge-commit count per window (rate/day); `lead_time` = median(commit-time − author-time) per window, hours; `change_failure_rate` = failed ÷ total agent_runs per window, ratio [0,1]; `mttr` = mean gap from a `failed` run to the next `success` run on the same `target_path`, hours. Flagged in Change Log below for explicit PO sign-off before Story 5.17 consumes the numbers.
- **D4 (insufficient_data threshold + envelope shape) — adopted recommendation (a):** per-metric `data_status: "ok" | "insufficient_data"` inside each metric object (not a single top-level flag). Threshold: `span = now - earliest(agent_run.ts ∪ first git commit)`; a window is insufficient iff `span < window_days` OR the metric's own numerator/denominator set is empty for that window. Empty agent_runs OR empty git-log → all metrics insufficient (code-review P5 2026-07-01: corrected from "AND"; the code is `if not runs or not commits:`). Documented in `docs/api/dora-schema.json`.
- Wrote failing tests first for both pure modules (`tests/unit/cli/test_git_dora.py`, `tests/unit/telemetry/test_dora.py`) before implementing `_git_dora.py` / `dora.py` (TDD red→green, CONTRIBUTING §2).
- `dashboard/routes/dora.py::_DoraCache.get` now takes a `compute: Callable[[], bytes]` so the cache-refresh test (`tests/unit/dashboard/test_dashboard_routes.py`) asserts an **observable** recompute via a call-counting callable across the injected-clock TTL boundary, avoiding the 5.1 review R7 tautology trap (`first == second` against a constant).
- `docs/api/dora-schema.json` carries the D1-revisit clause verbatim in its header (`_meta` block): promote to the 8th ADR-024 wire contract (StrictModel + snapshot ceremony, freeze → 8/8) only if a real external `/api/dora` consumer appears.
- Schema-conformance test (`tests/unit/dashboard/test_dora_backend.py::TestSchemaConformance`) spins up a real dashboard server with injected fixture data, queries `/api/dora` over HTTP, and validates the live JSON body against `docs/api/dora-schema.json` with a small hand-rolled validator (no new `jsonschema` dependency added — avoids requiring user approval for a new third-party package per the "new dependencies need approval" rule; the validator covers `type`, `required`, `enum`, `properties`, and numeric bounds, sufficient for this schema's shape).
- Performance benchmark (`tests/benchmark/test_dora_perf.py`) uses `benchmark.pedantic(..., rounds=1, iterations=1, warmup_rounds=0)` for a single true-cold sample per CI run, mirroring `test_scan_perf_cold` (Story 1.15) — measured ~9 ms locally on the 200-commit/1000-run/90-day fixture, well under the 30 s budget.
- **Security review (`security-reviewer` subagent touch, DAG §5 5.13 row): verdict = no blocking issues.** Confirmed no new write path (route stays GET-only under the existing router's 405-on-write), no path-traversal (the `agent_runs.jsonl` path and `repo_root` are server-config-derived only, never taken from the HTTP request), the `git log` subprocess is arg-list form with `shell` not used, `check=False`, and a 5 s timeout, no secrets/env leakage, and `target_path` never leaks into the HTTP response body. Two **Low**-severity residual notes (both accepted as-is given the localhost-only threat model, one hardened anyway):
  - *Applied:* `iter_agent_run_records` re-raises non-`FileNotFoundError` `OSError`s (e.g. permission-denied) verbatim from the `cli/_agent_runs.py` precedent; this would have propagated out of `compute_dora_window` uncaught and dropped the HTTP connection instead of returning a body. **Fixed:** `compute_dora_window` now catches `OSError` around the agent_runs read, logs a WARNING, and degrades to an empty-runs `insufficient_data` result — closing the gap against Task 4's own "never crash the endpoint or 500 the request" AC. New RED→GREEN test: `tests/unit/telemetry/test_dora.py::TestMalformedInputResilience::test_unreadable_agent_runs_path_degrades_to_insufficient_not_crash`.
  - *Accepted as-is:* both `iter_agent_run_records` and `git_dora_log` materialize their full result into a `list`/`str` rather than streaming: bounded by the 30 s cache (at most one read/subprocess per 30 s), localhost-only bind, and (for git) a 5 s subprocess timeout — acceptable for this tool's single-operator threat model; not hardened further to avoid scope creep beyond Task 9's security-touch ask.
- No new runtime dependencies were introduced (pytest-benchmark was already a dev dependency per `pyproject.toml:32`).

### File List

- `src/sdlc/telemetry/dora.py` (new) — `compute_dora_window` DORA compute engine; hardened to catch `OSError` from the agent_runs reader and degrade gracefully (post-security-review fix).
- `src/sdlc/cli/_git_dora.py` (new) — `parse_dora_git_log` (pure) + `git_dora_log` (subprocess wrapper).
- `docs/api/dora-schema.json` (new) — internal/documentary `/api/dora` response schema.
- `src/sdlc/telemetry/runs.py` (modified) — added `iter_agent_run_records` reader seam.
- `src/sdlc/dashboard/routes/dora.py` (modified) — real compute wired behind the frozen `_DoraCache`; `_DoraCache.get` now takes a `compute` callable; `register_dora_route` accepts `repo_root`, `git_log_provider`, `clock`.
- `src/sdlc/dashboard/server.py` (modified) — propagates `git_log_provider` through `build_router` / `create_server` / `serve_dashboard` / `serve_dashboard_in_thread`.
- `src/sdlc/cli/dashboard.py` (modified) — injects `git_dora_log` as the real `git_log_provider`.
- `tests/unit/cli/test_git_dora.py` (new) — unit tests for the git-log parser + wrapper.
- `tests/unit/telemetry/test_dora.py` (new) — unit tests for `compute_dora_window` (all four metrics, both windows, insufficient_data branching, OSError resilience).
- `tests/unit/dashboard/test_dora_backend.py` (new) — integration-style route + schema-conformance tests.
- `tests/unit/dashboard/test_dashboard_routes.py` (modified) — updated `TestDoraRoute` for the real-compute body; replaced the tautological cache test with a call-counting non-tautological version.
- `tests/benchmark/test_dora_perf.py` (new) — `<30s` cold-compute performance benchmark (CI gate via the existing `benchmarks` job).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — status tracking for this story.

## Change Log

- 2026-07-01: Story 5.13 created (create-story, "flip done 5.12 + tạo all US cho layer tiếp theo" → L6/5B batch-2). Net-new DORA computation engine (`telemetry/dora.py::compute_dora_window`, four metrics × 7d/30d) + git-log reader (cli-grant subprocess + pure parser) + agent_runs reader-seam (real 2B.10 `_AgentRunLine` shape) wired into the real `/api/dora` body behind the frozen 5.1 30 s `_DoraCache`; per-metric `data_status:"insufficient_data"` → Story 5.7 `n/a` (rendered by 5.17); `docs/api/dora-schema.json` INTERNAL/documentary schema (DAG D1(a) — no StrictModel, no snapshot ceremony, **freeze stays 7/7**; D1-revisit→8th-ADR-024-contract clause folded into Task 7 AC); `<30s` `pytest-benchmark` CI gate on a 200-story/1000-task/90-day fixture. Decisions raised: **D1** (git-log subprocess placement + one-way reader-seam — mirror Story 3.2 DI, keep subprocess in `cli`, inject into the dashboard server; keeps `dashboard`/`telemetry` `cli`-free and freeze 7/7), **D2** (agent_runs reader-seam location — telemetry-owned reader vs cli-injection), **D3** (the four metric proxy definitions over agent_runs+git — PO ratifies), **D4** (per-metric `insufficient_data` threshold + envelope shape). L6 (5B) batch-2-alone, rebased on batch-1 {5.14,5.15,5.16,5.18}; depends 5.1 + 5.7; feeds 5.17; external wave gate E2B (agent_runs.jsonl). Review model: review-B (edge/perf/malformed-input) + security-reviewer touch. WAVE-BOUNDARY RISK noted: verify the real agent_runs.jsonl shape (2B.10) is emitting before branching.
- 2026-07-01: Implementation complete (dev-story). Decisions D1/D2/D4 resolved per the story's own "Recommendation (a)" / "Reviewer lean (a)" text (no open questions — implemented as specified); **D3 adopted the story's documented starting-point proxy formulas verbatim, flagged here for explicit PO sign-off before Story 5.17 renders the numbers** (no interactive PO available in this automated session). All 9 tasks complete, tests-first (RED commits precede GREEN implementation for both pure modules). `python scripts/check_module_boundaries.py` exit 0 before/after; ruff + ruff format + mypy --strict clean on all new/modified files; `mkdocs build --strict` green with the new `docs/api/dora-schema.json` asset; zero new wire-format contracts → freeze stays 7/7 (no new `StrictModel`, no new `tests/contract_snapshots/v1/` entry). DORA-relevant + dashboard/telemetry/cli regression subset: 177 passed / 2 pre-existing POSIX-only skips / 4 pre-existing unrelated failures (missing local `stylelint` Node binary on this Windows dev box). `<30s` perf benchmark measured ~9 ms cold on the 200-commit/1000-run/90-day fixture; auto-wired into the existing `benchmarks` CI job via the `@pytest.mark.benchmark` convention (no `ci.yml` edit needed). **`security-reviewer` subagent touch (Task 9): verdict = no blocking issues** (no path traversal, no command injection, no secret/env leakage, no HTTP-facing information disclosure); one Low finding hardened in this same pass — `compute_dora_window` now catches `OSError` from the agent_runs reader and degrades to `insufficient_data` instead of risking an uncaught exception dropping the HTTP connection (RED→GREEN test added); one Low finding (full-file materialization of agent_runs/git-log output) accepted as-is given the 30 s-cache/localhost-only/5 s-timeout-bounded threat model. Status → review.

## Review Findings

> **bmad-code-review (fresh-context, 2026-07-01)** — 4 adversarial layers @ Opus-4.8 (Blind Hunter / Edge Case Hunter / Acceptance Auditor / security-reviewer touch per DAG D2 §5) + orchestrator source-verification. Every load-bearing defect reproduced against the real code: **P1 confirmed by a standalone `UnicodeDecodeError` repro** (a one-byte `0xff` fixture escapes the `except OSError` guard); P2/P3/P4 confirmed by direct source read. Triage: **1 decision-needed / 5 patch / 4 defer / 4 dismissed**. AC1–AC4 + D1/D2/D4 verified MET (schema↔code shape matches field-for-field; `check_module_boundaries.py` exit 0; the `<30s` benchmark ~9 ms is a real CI gate via `pytest -m benchmark`). **STAYS in `review`** until the patch findings are committed TDD-first + merged to main + green CI (merged-before-done gate, CLAUDE.md binding) OR consciously left as action items.
>
> **Applied 2026-07-01 (working-tree):** P1–P5 all applied; D3 ratified (Option 1, no code change). 3 RED→GREEN witnesses added to `tests/unit/telemetry/test_dora.py::TestReviewPatches` (non-UTF-8 no-crash / future-dated exclusion / out-of-enum CFR denominator). Win32-verified: `test_dora.py` **20 passed**, `test_dora_backend.py` incl `TestSchemaConformance` green, `ruff check` + `ruff format` + `mypy --strict` clean on all changed modules, `check_module_boundaries.py` exit 0, `dora-schema.json` valid JSON. The 6 fixture-gated route tests + the full pytest/coverage≥87 run on POSIX CI (root `tests/conftest.py` transitively imports POSIX-only `io_primitives` → win32 collection ImportError; pre-existing, unrelated). **NOT committed — working-tree only. NEXT: commit TDD-first (test → fix → docs) on a `epic-5/5-13-*` worktree + merge to main + green CI, THEN close-out flips review→done.**

### Decision-needed

- [x] [Review][Decision] **D3 — PO ratification of the four DORA proxy formulas** — `agent_runs.jsonl` carries no native deploy/incident/recovery/release-tag concept, so all four metrics are *proxies*: deployment_frequency = merge-commit count per window (fallback to counting all commits when the repo has zero merges anywhere); lead_time = median(commit_ts − author_ts) hours; change_failure_rate = failed ÷ total agent_runs; mttr = mean(next-success − latest-failure) per target_path. The code matches the documented starting-point verbatim, but Story 5.17 will render these numbers to PMs — the proxy semantics need explicit PO sign-off (or change requests) before then (DAG §7 cross-epic-data-coupling risk). [src/sdlc/telemetry/dora.py:11-29; docs/api/dora-schema.json:9-15]
  - **RESOLVED 2026-07-01 — PO ratified the four proxies as v1 DORA semantics (Option 1); no code change.** Caveat recorded for Story 5.17: `lead_time` is *author→land* latency (near-0 outside rebase workflows), NOT idea→production DORA lead time — 5.17 must label it accordingly; patch **P4** documents the `commit_ts >= author_ts` guard so the semantics are precise. The `dora-schema.json` is internal/documentary (freeze stays 7/7) with a `revisit_clause`, so this ratification is revisable without an ADR-024 ceremony.

### Patch

- [x] [Review][Patch] **P1 (HIGH) — non-UTF-8 byte in `agent_runs.jsonl` crashes `/api/dora` and bricks it** [src/sdlc/telemetry/runs.py:265] — the reader opens `encoding="utf-8"` (strict) and decodes lazily during line iteration; one invalid byte raises `UnicodeDecodeError`, which subclasses `ValueError` NOT `OSError`, so it escapes `compute_dora_window`'s `except OSError` guard and unwinds through the un-try/except'd handler → dropped connection; because `_DoraCache` stores no body on a failed compute, EVERY subsequent request re-crashes. Violates the module's own invariant ("never 500 on unreadable untrusted input") + Task 4 ("one bad line skipped, not fatal"). Reproduced. Fix: open with `errors="replace"` (preserves the still-valid lines).
- [x] [Review][Patch] **P2 (MEDIUM) — no `<= now` upper bound on any window filter → future-dated events inflate metrics** [src/sdlc/telemetry/dora.py:140,152,163,173] — all in-window filters are lower-bounded only (`ts >= since`); a commit/run dated after `now` (clock skew, or a crafted `GIT_COMMITTER_DATE`) counts as "in the last 7d AND 30d", inflating deployment_frequency/per_day and pulling lead_time's median up (a future `commit_ts` passes the `>= author_ts` guard with a huge delta). Fix: add `<= now` to the commit and run window filters.
- [x] [Review][Patch] **P3 (LOW) — change_failure_rate denominator counts out-of-enum outcomes** [src/sdlc/telemetry/dora.py:164] — `_parse_runs` accepts any string `outcome`; `_change_failure_rate` puts every in-window run in `total` but only exact `"failed"` in the numerator, so a record with `outcome ∉ {success, failed}` (corruption / future schema) silently deflates the rate. Fix: denominator counts only `outcome ∈ {success, failed}`.
- [x] [Review][Patch] **P4 (LOW, doc) — lead_time silently drops `commit_ts < author_ts`, contradicting the documented "over ALL commits"** [src/sdlc/telemetry/dora.py:152] — the `commit_ts >= author_ts` guard (a defensible negative-latency filter) is undocumented and makes lead_time diverge from deployment_frequency on the same commit set (a deploy can be `ok` while lead_time is `insufficient_data` for the identical window). Fix: document the guard in the docstring + `docs/api/dora-schema.json` metric definition.
- [x] [Review][Patch] **P5 (LOW, doc) — Completion-note says "AND", code+spec say "OR"** [this file — Completion Notes List] — the note states "Empty agent_runs AND empty git-log → all metrics insufficient", but the code (`if not runs or not commits:`) and D4 both use OR. Fix the prose.

### Deferred (also logged in deferred-work.md)

- [x] [Review][Defer] **DEF-1 — unbounded full-file materialization + follows symlink/FIFO + read under the cache lock** [src/sdlc/telemetry/dora.py:214; src/sdlc/dashboard/routes/dora.py:57-63] — deferred, pre-existing/accepted: `list(iter_agent_run_records(...))` has no line/byte cap and follows symlinks/FIFOs (a symlink to `/dev/zero` or an unfed FIFO hangs forever), and the read runs inside `_DoraCache._lock`, so one hung/huge file stalls EVERY `/api/dora` thread. Memory-materialization already accepted (dev Completion Notes) under the localhost/own-file/30 s-cache model; the symlink + under-lock-hang nuance is the new part. Low real-world risk.
- [x] [Review][Defer] **DEF-2 — D2 DRY gap: `cli/_agent_runs.py` duplicates the telemetry reader instead of delegating** [src/sdlc/telemetry/runs.py:253 vs src/sdlc/cli/_agent_runs.py] — deferred, deliberate scope-minimizing choice; D2 rec (a) suggested cli delegate to `telemetry/runs.py::iter_agent_run_records`, but the dev added a byte-for-byte mirror. Both test-covered; drift risk low but nonzero.
- [x] [Review][Defer] **DEF-3 — schema-conformance test does not enforce `additionalProperties`** [tests/unit/dashboard/test_dora_backend.py] — deferred, test-robustness only: `_validate` checks type/enum/required/properties but not extra keys, so a future extra emitted field would slip past (no active drift today).
- [x] [Review][Defer] **DEF-4 — WARNING logs echo full untrusted record via `%r`** [src/sdlc/telemetry/dora.py:115; src/sdlc/telemetry/runs.py:278-292] — deferred, local-only logs (no HTTP leak): a huge adversarial line is echoed verbatim to server stderr; consider truncating the logged repr.

### Dismissed (4)

- **MTTR "recover-from-latest-failure" pairing** (consecutive-failure overwrite of `pending_failure`) — documented + defensible, consistent with the schema note; Blind Hunter + Acceptance Auditor concur.
- **naive-`now` `TypeError`** at `now - earliest` — not production-reachable: `_default_clock()` is tz-aware and `_parse_iso` coerces all data timestamps to UTC-aware (all four layers concur).
- **`use_merges_only` computed over full history** then applied per-window — documented proxy behavior (schema `deployment_frequency` definition).
- **AC verbatim "journal/agent_runs/git" but journal not read** — design-consistent with the ratified D3 proxies (no journal-derived DORA proxy exists); folds into the D3 ratification.
