# Story 5.19: STOP Banner Rendering All 7 Trigger Types

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG **L8 (5C)**, single-story layer, cap 1 (epic-5-dag.md §3:217, §6:331). Worktree: `epic-5/5-19-stop-banner-7-triggers`. Owner **Amelia** (engine/security-adjacent — NOT Sally; dag §5:297). Depends on: external wave gate **E4 → S19** = Epic-4 STOP state **being STICKY** (retro D4 / CR4.2-W3 sticky-halt), **NOT real-loop dispatch** (Decision D3; dag §2:177,196-197, §7:352) + 5A twins **5.5** (live-dot/freshness-footer family, done) via 5.5→5.19 (dag §2:136) + **5.11** (tabs/activity-feed/**empty-state**, done) via 5.11→5.19 (dag §2:158). Downstream: **5.19 → 5.20** (disconnection reuses this banner treatment; dag §2:161), **5.19 → 5.21** (below-1280 banner reuses treatment w/ `--blue`; dag §2:162), **5.19 → 5.22** (terminal a11y release gate; dag §2:165). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate **N/A** (epic-5 in-progress, cleared at 5.1). Review focus: **data-validation** (renders untrusted `stop_reason`/journal `reason` content — CR4.8-W3) + **a11y** (role=alert/status, color-only, reduced-motion). No wire-format contract shape edit → **freeze stays 7/7**. This renders STOP state; do NOT build disconnection (5.20) / below-1280 (5.21) / real dispatch (real-dispatch epic). -->

## Story

As Lam catching auto-mode failures at-a-glance,
I want STOP banners on the side panel rendering all 7 trigger types from Epic 4's STOP-trigger state, with severity via semantic color + text label (never color-only),
So that the trust-UX surface for auto-mode is complete (UX-DR6, NFR-OBS-5, FR42).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.19, lines 2820–2834).

**Given** Epic 4 stories firing STOP triggers and recording them in state
**When** any of the 7 triggers is active
**Then** a STOP banner renders on the side panel (one banner per active trigger; up to 7 simultaneously)
**And** each banner shows: severity live-dot (Story 5.5 — `--blue` info / `--amber` warn / `--red` crit), text severity label, trigger name, target id, suggested user action

**Given** the trigger-to-severity mapping
**When** banners render
**Then** the mapping is documented and tested: clarification = info, signoff_required = warn, pr_ready = info, replan_dirty = warn, agent_failed = crit, high_risk = crit, bug_awaiting = warn

**Given** state has no active STOPs
**When** the side panel renders
**Then** the Empty State (Story 5.11) appears instead of any banner
**And** the freshness footer is still present

> ⚠️ **AC-vs-CODE DIVERGENCE — READ "Wave-boundary verification" + Decisions D1/D2 BEFORE coding.** The AC prose drifts from the shipped substrate in **four** load-bearing ways: (1) **4 of 7 trigger names are wrong** vs `engine/stop_registry.py` — use the code `trigger_id`s, not the AC labels; (2) `state.json` exposes a **single** `stop_reason` string, **not** a 7-trigger list — "up to 7 simultaneously" + `target id` + `suggested user action` cannot come from state alone (D1); (3) the `<live-dot>` element has only 3 variants (default/warn/disconnected) and **no `--blue`/info or crit** — severity is the `.alert` left-edge treatment + text label, **not** a live-dot variant (D2); (4) UX §6.7's `[Run command]/[Mark resolved]` buttons are **forbidden** (read-only 405, §7.12) — the action renders as copyable inline-code, not a write button (D5). The **corrected authoritative mapping** is in Dev Notes → "Locked design decisions".

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** every AC clause is a testable contract → tests-first. **(AC clause 1) all 7 types render as banners** — synthetic fixture listing all 7 `trigger_id`s drives `renderStopBanners`; static-source + Playwright assert each banner carries severity edge + **text severity label** + trigger name + target id + suggested action. **(AC clause 2) trigger→severity mapping** — a unit/static test over the banner-owned `TRIGGER_META` map asserts all 7 code `trigger_id`s map to the documented severity (+ the 2 out-of-registry strings + unknown→neutral). **(AC clause 3) empty → Empty State + footer** — Playwright: state with no active STOP renders `<empty-state>` (which embeds `<freshness-footer>`), zero `.stop-banner` nodes. **Resolve Decisions D1–D5 BEFORE coding.**

- [ ] **Task 0 — Resolve Decisions D1 (STOP data source: `state.json` single-halt vs journal-derived `/api/stops` vs `stops[]` projection) + D2 (severity indicator: `.alert` treatment, NOT `<live-dot>`) + D3 (severity map ownership + boundary-legal placement) + D4 (suggested-action + untrusted-content sanitization, CR4.8-W3) + D5 (read-only action surface — copyable inline-code, no write buttons) BEFORE coding** (AC: all)
  - [ ] Record picks in the PR Change Log (CONTRIBUTING §5). D1/D2 are load-bearing because verification found the AC premise is only **partially realized**: state.json carries a single sticky `stop_reason`, not a 7-trigger list, and the trigger metadata (severity/target/action) is not projected (see Dev Notes → "Wave-boundary verification"). Raise D1 as a D-label for PO/architect ratification before branching.

- [ ] **Task 1 — Net-new `stop-banner` render seam + authoritative `TRIGGER_META` map (D2, D3)** (AC: 1, 2) — *tests-first*
  - [ ] Create `components/stop-banner/stop-banner.js` with a **frozen render seam** `renderStopBanners(host, triggers)` (mirror `activity-feed.js::renderActivityFeed` structure) that renders one `.stop-banner` (`.alert`) per trigger. Own a `TRIGGER_META` constant keyed on the **code `trigger_id`** (NOT the AC labels) → `{ severity, label, defaultAction }` per Dev Notes "Locked design decisions". Include the 2 out-of-registry strings (`watchdog_timeout`, `agent_failure_after_retries`) and a **neutral default** for any unknown id (mirror `activity-feed.js` `OUTCOME_GLYPH` + `NEUTRAL_OUTCOME_GLYPH` fallback, lines 30–46) — never crash, never mislabel an unknown as `crit`.
  - [ ] Severity treatment (D2): copy the `.alert.{info,warn,crit}` left-edge pattern from `docs/ux/dashboard-prototype/dashboard.html:132–140` using tokens `--blue`/`--amber`/`--red` (`styles/tokens.css:117–121`) into `stop-banner.css`. Do **NOT** reuse `<live-dot>` for severity (it has no info/crit variant and carries a known recursion defect — see Dev Notes). Optional severity dot uses `--motion-pulse-stop` (2.4s) — a banner-owned dot, disabled under reduced-motion (DD-16).
  - [ ] **Color-only contract (5.5-owned, hard gate):** every banner MUST carry a **text severity tag** in its title ("CRITICAL:" / "WARNING:" / "INFO:") in addition to the color edge (UX §6.7 a11y; `check_dashboard_color_only.py`). Consider a severity **pill** (`components/pills/pills.js` registry) for the tag per §7.13.
  - [ ] **Mapping test (AC2):** static/unit test asserts `TRIGGER_META[<each of the 7 code trigger_ids>].severity` equals the documented value, cross-checked against `engine/stop_registry.py:17–34` severity-hint ordering so the JS map does not drift from the engine's precedence tiers.

- [ ] **Task 2 — a11y + banner anatomy per UX §6.7** (AC: 1) — *tests-first*
  - [ ] Anatomy: `.alert` container (`--paper` bg, `--border-hairline` + 3px semantic left edge, `--radius-lg`), `.a-title` (`--type-body-strong`), `.a-detail` (`--type-body-small` `--ink-mute`), `.a-action` row. Title = text severity tag + trigger name; detail = reason/summary; action = suggested user action (D5).
  - [ ] `role="alert"` (assertive) for `crit`; `role="status"` (polite) for `info`/`warn` (§6.7). Each banner has a unique `aria-labelledby` referencing its `.a-title`. **Not user-dismissible** — v1 banners vanish only when the underlying state resolves (Resolved state = removed from DOM on next poll, content delta only, DD-06). No `×`/dismiss control.
  - [ ] Reduced-motion (DD-16): pulse disabled → static dot; DD-14: **no `transition:`** anywhere (only the `--motion-pulse-stop` keyframe animation is permitted — confirm `check_dashboard_motion.py` passes the pulse).
  - [ ] Playwright a11y witness (`tests/dashboard/`): all-7 fixture → assert per-banner `role`, `aria-labelledby`, text-severity-label present (reuse `assert_live_dots_have_text_labels` pattern / extend for `.stop-banner`), keyboard order of any `.a-action` inline elements, reduced-motion static-dot.

- [ ] **Task 3 — Empty State + freshness footer (AC3) + fold DEF-5** (AC: 3) — *tests-first*
  - [ ] When there are **no active STOPs**, mount `<empty-state>` (`components/empty-state/empty-state.js`, default copy `"No STOPs in flight"`) into `#alertsHost` instead of any banner — it renders its own `<freshness-footer>` internally, satisfying "Empty State appears + freshness footer still present". For the **non-empty** branch, also append a `<freshness-footer>` to the alerts column so the footer is present in both branches (consistency).
  - [ ] **Fold 5.5 DEF-5 (owned by 5.19):** `renderEmptyState({message:""})` currently blanks the anti-cynicism copy because the `{ message = EMPTY_STATE_MESSAGE }` default only fires for `undefined` — coerce any **falsy** `message` to `EMPTY_STATE_MESSAGE` inside `renderEmptyState` (`empty-state.js:12`). Unit-test `""` → default copy. [deferred-work.md:924]
  - [ ] Playwright: state with `auto_loop_status != "halted"` (or empty active set) renders exactly one `<empty-state>`, zero `.stop-banner`, footer present.

- [ ] **Task 4 — Live poller (content-delta / NFR-PERF-4) + column shell (D1)** (AC: 1, 3) — *tests-first*
  - [ ] Create `components/stop-banner/stop-banner-live.js` `startStopBannerLivePoller(host, opts)`. **D1 recommended (a):** reuse the masthead `/state.json` + ETag/304 idiom (`masthead.js::pollStateJson` / `startMastheadPoller`, lines 80–88,158+) — read the `auto_loop_status`/`stop_reason` slice; do **NOT** add a new route unless D1(b)/(c) is ratified. Map the slice → the banner view-model (single active trigger for the real path); feed `renderStopBanners`. `POLL_INTERVAL_MS = 3_000`.
  - [ ] **Content-delta (NFR-PERF-4):** diff on a banner-list signature (mirror `kpi-strip-live.js` `cellsSignature`/`lastSignature`, lines 192,233–236) and re-render `#alertsHost` only when the STOP slice changes; **no `.innerHTML =` wholesale replacement** (mirror `test_phase_tracker_live_source.py::test_never_replaces_..._wholesale`).
  - [ ] **Poller hardening (shipped-precedent, `resume-card-live.js:106–151`):** `inFlight` re-entrancy guard, `disposed` flag, `AbortController` aborted on dispose, `try/catch` that keeps last-known-good (never surface a visible error), a neutral **loading state** before the first poll. Dispose returns `() => clearInterval(...)`.
  - [ ] **Column shell:** mount `<div class="alerts-col">` with a section-block heading (`components/section-heading/section-heading.js::renderSectionBlockHeading(host, { title: "Alerts", count })` — its nullish guard renders a legitimate `0`) + `#alertsHost`; grid placement `.overview-grid` = `minmax(0,1.6fr) minmax(0,1fr)` (focus + alerts). Wire it into the assembling page mirroring `index.html:23–26` (kpi-strip poller start). If no full-page host exists yet, ship `stop-banner-live.fixture.html` as the driven surface (matches sibling `*-live.fixture.html` convention).

- [ ] **Task 5 — Untrusted-content hardening + read-only action (D4, D5, CR4.8-W3) + fold DEF-6** (AC: 1) — *tests-first*
  - [ ] **Data-validation (D4 / CR4.8-W3):** `stop_reason` and any journal `reason`/`summary` are **untrusted** at the client edge (unbounded, unsanitized, control chars per `stop_bug_awaiting.py:36-37`). Render with `textContent` only (no `innerHTML`), **cap length** (mirror `_MAX_REASON_ERROR_LEN=200`), and strip/collapse newlines + control chars. **Allowlist** `stop_reason` against the known `trigger_id` set before keying `TRIGGER_META`; an unrecognized value → neutral banner showing the raw (sanitized, capped) string, never `[object Object]`/`undefined`/a crash. Unit-test hostile inputs (`<img onerror>`, 10 KB string, `null`, unknown id).
  - [ ] **Read-only action (D5):** render the "suggested user action" as a copyable **inverted-command surface** (reuse `components/inverted-command/`, per §7.13 "Inverted command surface when alert action is a literal command") or plain inline-`code` — **NOT** a functional `[Run command]`/`[Mark resolved]` write button (forbidden: read-only 405 + §7.12 button-hierarchy). The only button permitted is the copy button (DD-12).
  - [ ] **Fold 5.8 DEF-6 (owned by 5.11/5.19 as surface consumers):** if the inverted-command surface is reused, relocate the `.copy-btn` chrome reset (`min-width:36px`, `border:none`, `background:transparent`) from `resume-card.css:64–77` into the reusable `inverted-command.css` (or a shared button partial) and re-point the `assert "36px" in css` / `assert ".copy-btn" in css` unit assertions. [deferred-work.md:912] If 5.19 does NOT reuse the copy button, note DEF-6 stays with the next consumer.

- [ ] **Task 6 — Committed fixtures + tests + packaging + quality gate + freeze** (AC: 1, 2, 3) — *tests-first*
  - [ ] Commit fixtures: `stop-banner.fixture.html` (synthetic — **all 7 code `trigger_id`s**, each with target id + suggested action + text severity tag), `stop-banner-live.fixture.html`, and a real-shaped active-STOP `state.json` fixture (`{"schema_version":1,"auto_loop_status":"halted","stop_reason":"high_risk_path",…}`) + a no-STOP fixture. No committed active-STOP `state.json` exists today — create them (journal-project approach per `tests/unit/state/test_state_projection_auto_loop.py:19–75`, or hand-authored).
  - [ ] Tests mirror the 5B surface: `tests/unit/dashboard/test_stop_banner_fixture.py` (all 7 declared + text severity labels + no dialog/toast/form) + `test_stop_banner_live_source.py` (3s cadence; reads the STOP slice NOT a wrong endpoint; content-delta guarded; Empty State when zero; mapping covers all 7 + 2 extras + unknown→neutral) — RED template `tests/unit/dashboard/test_phase_tracker_live_source.py`. Add a `tests/dashboard/` Playwright a11y witness. Extend `tests/fixtures/dashboard_color_only/` with `clean_`/`violation_` stop-banner cases.
  - [ ] Add new static files to `force-include` [pyproject.toml]. Component CSS uses `var(--*)` only (5.2 stylelint). Run **all dashboard static gates**: `check_dashboard_color_only.py` (extend for `.stop-banner`), `check_dashboard_forbidden_patterns.py` (no `<dialog>`/`<modal>`/`data-toast`/`<form>`/`pushState`/skeleton), `check_dashboard_motion.py` (DD-14 — pulse OK, no `transition:`), `check_dashboard_no_data_theme.py` (DD-09), `check_dashboard_no_framework.py` (DD-08), `check_dashboard_no_external_fonts.py`.
  - [ ] Python quality gate on any new `.py` (route only if D1(b)/(c)) + tests: ruff + ruff format + mypy --strict; `check_module_boundaries.py` — the severity map + any producer MUST stay boundary-legal (`dashboard → state`/`journal` one-way; **`dashboard → engine` and `dashboard → cli` are FORBIDDEN** — do NOT import `engine.stop_registry`; own the display severity map in JS). Full `uv run pytest` + coverage ≥ 87% (run the **literal** `uv run pytest tests/` — subsets lie; memory `project_test_scope_and_order_gotcha`). `mkdocs build --strict`. **Zero wire-format shape change → `scripts/freeze_wireformat_snapshots.py --check` = 7/7** (`StopDecision` is not a frozen wire contract; `auto_loop_status`/`stop_reason` already exist on the `State` model; a `stops[]` projection field under D1(c) is a `State`-model change within `schema_version=1`, NOT one of the 7 frozen snapshots).

## Dev Notes

### Wave-boundary verification (E4 → 5.19) — READ FIRST

The `E4 → S19` gate requires Epic-4 STOP state to be **sticky**, NOT real-loop dispatch (Decision D3; dag §2:177,196-197). Verification against the live codebase (2026-07-06):

- **Sticky-halt fix — CONFIRMED PRESENT + WIRED + TESTED.** `state/projection.py:86–110` `_fold_auto_loop_status`, wired into `_project_entries` at `:156–161`; halt kinds set `("halted", trigger)` (`:106–109`); an `auto_loop_iteration{action="stopped"}` arriving **after** a halt returns state unchanged (does NOT reset to `idle`, `:94–103`); a genuine resume (`action in {dispatch, continued}`) clears back to `("running", None)` (`:104–105`). ADR-038 (`docs/decisions/ADR-038-sticky-halt-projection.md`, Accepted), commit `5bd4e22`; pinned by `tests/unit/state/test_state_projection_auto_loop.py:49–101`. The projection comment at `:97–98` explicitly names Story 5.19 as the reader. **⇒ the load-bearing dependency exists.**
- **STALE NOTE reconciled:** `deferred-work.md:761` (dated 2026-06-16) says CR4.2-W3 was "deferred to 4.10/4.11" — that note is **superseded** by the Epic-5-prep sticky-halt fix above (commit `5bd4e22` / ADR-038). Treat the DAG (§1: D4 CLOSED) as authoritative.
- **State shape (the central risk).** `state/model.py:33–35` projects only `auto_loop_status: str` (`"idle"|"running"|"halted"`) + `stop_reason: str | None` (the raw `trigger_id`). An active STOP = `auto_loop_status=="halted"` + `stop_reason=="<trigger_id>"`. **There is NO `target`, NO `severity`, NO suggested action, NO timestamp, and NO list in `state.json`.** The rich fields (`target`, `reason`, `ts`) exist ONLY in journal payloads (`stop_triggered`/`stop_trigger_raised`, `auto_loop.py:112–137`; `StopDecision` = `{fired, trigger, target, reason}`, `stop_triggers.py:16–23`). And `check_all()` **short-circuits on the first fired trigger** (`stop_registry.py:63–69`) → the live engine surfaces **ONE** active trigger at a time. **⇒ AC1's "up to 7 simultaneously" + "target id" + "suggested user action" cannot come from `state.json` — they are a rendering-capability requirement driven by the synthetic all-7 fixture (see D1).**
- **Emission is mock/placeholder-gated.** Real dispatch rides `EPIC-4-DEBT-AUTO-REAL-DISPATCH` (`cli/auto.py:27`, D-RETRO-2); the dispatcher placeholder emits a NON-registry string `"agent_failure_after_retries"` (`dispatcher/_panel_helpers.py:241–260`, `epic_4_placeholder=True`). 5.19 does NOT need real dispatch (D3) — it reads whatever STOP state exists (mock or real) and the sticky-halt fix makes it persist. No committed active-STOP `state.json` fixture exists → 5.19 creates them.

### Locked design decisions (verbatim — these govern the story)

**⭐ AUTHORITATIVE trigger→severity map (keyed on CODE `trigger_id`, NOT the AC labels).** Source of truth: `engine/stop_registry.py:35–43` `_ORDERED_TRIGGERS` + severity-hint ordering `:17–34`. **4 of the 7 AC names are wrong** — the banner MUST key off the code strings:

| Registry order (D-RETRO-3/D3) | Code `trigger_id` (USE THIS) | AC label (WRONG) | Severity | Source |
|---|---|---|---|---|
| 1 | `high_risk_path` | high_risk | **crit** | `stop_high_risk.py:74` |
| 2 | `agent_failed` | agent_failed ✓ | **crit** | `stop_agent_failed.py:85` |
| 3 | `open_clarification` | clarification | **info** | `stop_clarification.py:17` |
| 4 | `signoff_required` | signoff_required ✓ | **warn** | `stop_signoff.py:26` |
| 5 | `replan_dirty` | replan_dirty ✓ | **warn** | `stop_replan_dirty.py:18` |
| 6 | `bug_awaiting_decide` | bug_awaiting | **warn** | `stop_bug_awaiting.py:19` |
| 7 | `pr_ready_story` | pr_ready | **info** | `stop_pr_ready.py:19` |
| (out-of-registry) | `watchdog_timeout` | — | **crit** | pre-empts `check_all` in `auto_loop.py` |
| (out-of-registry, mock) | `agent_failure_after_retries` | — | **crit** | `dispatcher/_panel_helpers.py:250` placeholder |
| (any unknown) | `*` | — | **neutral** (default) | never crash / never mislabel |

The severity *intent* of AC2 is preserved (crit/warn/info tiers align with `stop_registry.py:17–34`: irrecoverability→crit, human-blocked→warn/info, positive-completion→info); only the AC *keys* were stale. Precedence = first-match-wins (`stop_registry.py:63–69`).

- **7 STOP triggers / total ordering (FR21, Decision A3/D).** `engine/stop_registry.py` + one `engine/stop_*.py` per trigger. `StopDecision` fields `{fired, trigger, target, reason}` (`stop_triggers.py:16–23`). [Source: architecture.md:817,1151,1190; epics.md FR21]
- **UX §6.7 STOP Banner / Alert (normative anatomy).** Side-panel column between resume card and activity feed; **stack vertically, never as toasts**. Container `.alert` (`--paper` bg, `--border-hairline` + 3px semantic left edge, `--radius-lg`); `.a-title` (`--type-body-strong` Inter 13px 600), `.a-detail` (`--type-body-small` `--ink-mute`), `.alert code` (`--type-mono-data`), `.a-action` (inline, link-style — NOT full button chrome). Severity variants: `info`→`--blue`, `warn`→`--amber`, `crit`→`--red`, neutral→`--ink-mute`. States: Default / Resolved (removed from DOM next poll, content-delta DD-06) / Reduced-motion (DD-16 pulse off). **Color never the only signal — every alert carries a text severity tag ("CRITICAL:/WARNING:/INFO:") in its title.** `role="alert"` (crit) / `role="status"` (info/warn); `aria-labelledby` per alert; not user-dismissible. [Source: ux-design-specification.md §6.7:1271–1319]
- **STOP-outranks-routine hierarchy (PRD).** Banners visually outweigh everything via sticky side-panel position, weight (heavier than body), size (≥1.25× body), semantic color + text, and **absence of decay (no auto-dismiss)**. Only motion permitted = live-dot pulse + STOP-dot pulse (`--motion-pulse-stop` 2.4s); `prefers-reduced-motion` disables both (DD-16). No sound, no browser-notifications, no toasts. [Source: ux-design-specification.md:64,155,157,234-235,716,743,753; §7.13:1650]
- **Empty State (§6.8).** Alert column when no STOP: `--paper` bg, dashed `--border-hairline`, `--ink-dim`, default copy `"No STOPs in flight"` — **no celebratory copy** ("All clear!"/"✓ Healthy") (emotional principle #6). Renders its own `<freshness-footer>` internally. [Source: ux-design-specification.md §6.8:1381–1383; empty-state.js:10,20–28]

### Frozen foundation to consume (do NOT redefine — 5.5 + 5.11 + upstream froze these)

```text
Net-new for 5.19 (create):
  components/stop-banner/stop-banner.js        renderStopBanners(host, triggers) + TRIGGER_META (keyed on code trigger_id)
  components/stop-banner/stop-banner.css       .stop-banner/.alert.{info,warn,crit} left-edge (copy prototype dashboard.html:132–140)
  components/stop-banner/stop-banner.fixture.html         synthetic ALL-7 + target + action + text severity tag
  components/stop-banner/stop-banner-live.js   startStopBannerLivePoller(host) — reads state.json STOP slice (D1a)
  components/stop-banner/stop-banner-live.fixture.html

Reuse (do NOT rebuild):
  Empty State (AC3)              components/empty-state/empty-state.js:10-28   (default "No STOPs in flight"; embeds footer; FOLD DEF-5 :12)
  Freshness footer              components/freshness-footer/freshness-footer.js:37  (STALE_MS=30_000)
  Section heading (Alerts N)    components/section-heading/section-heading.js  renderSectionBlockHeading(host,{title,count})  (count==null guard → renders 0)
  Severity pill (severity tag)  components/pills/pills.js  PILL_* registry + createPillElement(variant)
  Inverted command (D5 action)  components/inverted-command/inverted-command.js/.css  (§7.13; FOLD DEF-6 relocate .copy-btn)
  /state.json + ETag/304 poller components/masthead/masthead.js:80-88,158+   pollStateJson / startMastheadPoller (D1a; content-delta idiom)
  Alert-column markup + grid    docs/ux/dashboard-prototype/dashboard.html:105-140  .overview-grid 1.6/1 · .alerts-col · #alertsHost · .alert.{info,warn,crit}
  Severity tokens               styles/tokens.css:117-121  --blue / --amber / --red ; --motion-pulse-stop (2.4s)

Real substrate (READ-ONLY through the reader seam — dashboard → state/journal ONLY):
  7 trigger ids + ordering      engine/stop_registry.py:17-34,35-43,63-69   (do NOT import from dashboard — engine is boundary-forbidden)
  StopDecision shape            engine/stop_triggers.py:16-23   {fired, trigger, target, reason}
  Sticky-halt projection        state/projection.py:86-110 (wired :156-161) — auto_loop_status + stop_reason (single sticky halt)
  State model fields            state/model.py:33-35   auto_loop_status: str ; stop_reason: str | None
  Typed state reader (if server-side extraction) state/reader.py:39-92  read_state_or_refuse(target) -> State | None  (precedent resume.py:45,76)
  Journal reader (if D1b rich payload)          journal/reader.py  iter_entries(kind=...)  (precedent signoff.py:36)
  Current /state.json route     dashboard/routes/state.py:15-40  (streams raw bytes + ETag; does NOT parse into State)
```

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — STOP banner data source (HIGH / architecture + data-validation).** `state.json` carries a single sticky `stop_reason`, not a 7-trigger list with target/action (see Wave-boundary verification). Options: *(a)* **read the `state.json` `auto_loop_status`/`stop_reason` slice** via the masthead `/state.json`+ETag/304 idiom — renders the ONE real active banner (mapped via `TRIGGER_META`); `target`/rich-action unavailable → banner shows trigger label + severity + a static suggested-action; **all-7 rendering + mapping proven by the synthetic fixture**. Boundary-clean, no new route, matches the sticky-halt gate + shipped 5B pattern. *(b)* add `dashboard/routes/stops.py` → `GET /api/stops` reading `iter_entries(kind=stop_trigger_raised/stop_triggered)` and computing the active unresolved set with `target`/`reason` — satisfies "up to 7 + target id + suggested action" from real data + matches the architecture-planned route + `EPIC-4-STOP-TRIGGER-WIRE`, BUT the rich payload only exists on the mock/placeholder path, the "which raised triggers are still active" resolver is unbuilt/non-trivial, and it is arguably the real-dispatch epic's job. *(c)* extend the projection to emit `stops: []` (a `State`-model change within `schema_version=1`, freeze stays 7/7) — cleanest data model but a deeper reducer change. ***Recommendation (a)*** for the real path + synthetic all-7 fixture; raise as a D-label so the architect/PO ratify whether real `target id`/multi-trigger are required now (→ b/c) or deferred (→ 5.20/real-dispatch epic). *(Mirrors 5.18 D1 exactly: state-projection vs dedicated route vs client-rederive.)*

**D2 — severity indicator: `.alert` treatment, NOT `<live-dot>` (HIGH / correctness).** AC1 says "severity live-dot (`--blue` info / `--amber` warn / `--red` crit)", but `<live-dot>` has only 3 variants (`default`/`warn`/`disconnected` = green/amber/red) and **no `--blue`/info and no crit** (`live-dot.js:8–12`), plus a known recursive-`setAttribute` defect (5.18 Debug Log / deferred-work). *Recommendation (a):* express severity via the `.alert` **left-edge color** (`--blue`/`--amber`/`--red`) + a **text severity tag** + optional banner-owned severity dot with `--motion-pulse-stop` — do NOT reuse the `<live-dot>` element. *(b)* extend `<live-dot>` `VARIANTS` with info/crit — **REJECTED** (widens the frozen 5.5 contract + inherits the recursion defect). Prefer (a).

**D3 — severity-map ownership + boundary-legal placement (MED / architecture).** `state.json` carries no severity; the map is a NEW artifact 5.19 owns (AC2 "documented and tested"). `engine/stop_registry.py` is **import-forbidden** from `dashboard`. *Recommendation (a):* own `TRIGGER_META` (severity + label + default action, keyed on code `trigger_id`) as a constant in `stop-banner.js`, documented + tested, cross-checked against `stop_registry.py:17–34` so it doesn't drift. *(b)* lift a severity map into a boundary-legal shared module — heavier; only if the CLI needs the same map. Prefer (a).

**D4 — untrusted STOP content sanitization (MED→load-bearing / data-validation, CR4.8-W3).** `stop_reason` (client edge) and journal `reason`/`summary` are unbounded/unsanitized (`stop_bug_awaiting.py:36–37`; no length cap, no control-char strip). *Recommendation (a):* `textContent`-only render, cap length (`_MAX_REASON_ERROR_LEN=200` precedent), strip/collapse newlines+control chars, allowlist `stop_reason` against the known `trigger_id` set before keying `TRIGGER_META`; unknown id → neutral banner with the sanitized raw string. This is the review's load-bearing check.

**D5 — read-only action surface (MED / read-only contract).** UX §6.7 anatomy shows `[Run command]/[Mark resolved]` buttons, but the dashboard is **405-on-write** and §7.12 forbids button hierarchy (only the copy button is allowed). *Recommendation (a):* render the suggested action as a copyable **inverted-command surface** (§7.13) or inline-`code` — never a functional write button. *(b)* functional action buttons — **REJECTED** (violates read-only + forbidden-patterns).

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the net-new `stop-banner` component (render seam + `TRIGGER_META` severity map keyed on **code `trigger_id`s** + `.alert` severity treatment + a11y `role`/`aria-labelledby` + reduced-motion) rendering all 7 types (synthetic fixture) and the single real sticky-halt (state.json); the content-delta live poller + alerts-column shell (D1); Empty State + freshness-footer wiring for the zero-STOP branch (AC3); untrusted-content sanitization (D4/CR4.8-W3); read-only copyable action (D5); the folded deferred fixes now load-bearing — **5.5 DEF-5** (empty-state falsy-message coercion) and, if the copy button is reused, **5.8 DEF-6** (relocate `.copy-btn` into `inverted-command.css`).
- **Must NOT build:** the **honest-disconnection / Disconnected state** (poll-fail detection, masthead red dot, "cannot reach state" banner) — that is **5.20** (edge 5.19→5.20); it *reuses* this banner treatment but 5.19 does not build it. The **below-1280 degradation banner** (reuses the treatment with `--blue` info) — that is **5.21** (edge 5.19→5.21). **Real auto-loop dispatch** (`EPIC-4-DEBT-AUTO-REAL-DISPATCH`, D-RETRO-2) — the real-dispatch epic. A **journal-derived multi-trigger `/api/stops` resolver** — only if D1(b) is ratified; default is state.json single-halt + synthetic all-7. **No write actions**, no modals/toasts/forms/notifications (§7.12), no CSS `transition:`/transforms (DD-14), no new/changed wire contract (freeze 7/7).

### Project Structure Notes

- **Net-new component under the frozen layout convention** `static/components/<name>/<name>.{js,css}` + `<name>.fixture.html` + `<name>-live.js` + `<name>-live.fixture.html` (`live-dot.js:4` D2 convention). All new static files → `force-include` [pyproject.toml].
- **Module boundary is the guardrail:** `dashboard → state`/`journal` is the only legal data edge (one-way); **`dashboard → engine` and `dashboard → cli` are FORBIDDEN** (`module_boundary_table.py:142–152`). Do NOT import `engine.stop_registry` — own the display severity map in JS (D3). A `routes/stops.py` (only under D1b) reads via `journal.reader.iter_entries` (boundary-legal). `check_module_boundaries.py` enforces this.
- **The 400-LOC cap is AST-enforced on Python only** (`check_module_boundaries.py:163,202` — does not scan JS/CSS); keep each JS file small by convention (siblings stay <300; largest live pollers ~260) — split the render seam (`stop-banner.js`) from the poller (`stop-banner-live.js`), mirroring 5.16/5.17/5.18.
- **Data-validation + a11y review focus:** `stop_reason`/journal `reason` are untrusted (D4); severity must never be color-only (text tag mandatory); `role=alert` (crit) vs `role=status` (info/warn); reduced-motion static dot. These are the load-bearing review checks (dag §5:297, §7:352).
- **L8/5C single-story layer**, worktree `epic-5/5-19-stop-banner-7-triggers`, owner Amelia. Branch from `main`, linear merge (CONTRIBUTING §3). Downstream 5.20/5.21 reuse this treatment and 5.22 (terminal a11y gate) re-scans it — it must merge clean + a11y-green.
- Zero wire-format contract shape change (CSS/JS/HTML are not wire contracts; `StopDecision` unfrozen; `auto_loop_status`/`stop_reason` pre-exist) → **freeze stays 7/7**.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| STOP banner render seam (new) | Model on `renderActivityFeed` defensive structure | src/sdlc/dashboard/static/components/activity-feed/activity-feed.js:142,214,243 |
| Unknown-value neutral fallback | `OUTCOME_GLYPH` + `NEUTRAL_OUTCOME_GLYPH` pattern | src/sdlc/dashboard/static/components/activity-feed/activity-feed.js:30–46,72–77 |
| Content-delta signature diff | `cellsSignature`/`lastSignature` | src/sdlc/dashboard/static/components/kpi-strip/kpi-strip-live.js:192,233–236 |
| Poller hardening (guard/AbortController/loading) | `startResumeCardLivePoller` | src/sdlc/dashboard/static/components/resume-card/resume-card-live.js:106–151 |
| `/state.json` + ETag/304 poll (D1a) | `pollStateJson`/`startMastheadPoller` | src/sdlc/dashboard/static/components/masthead/masthead.js:80–88,158+ |
| Empty State (AC3) + DEF-5 fold | `renderEmptyState` (embeds footer; coerce falsy message) | src/sdlc/dashboard/static/components/empty-state/empty-state.js:10,12,20–28 |
| Freshness footer | `renderFreshnessFooter` | src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:37 |
| Alerts column header (count 0-safe) | `renderSectionBlockHeading` | src/sdlc/dashboard/static/components/section-heading/section-heading.js |
| Severity tag pill | pill registry + `createPillElement` | src/sdlc/dashboard/static/components/pills/pills.js:53 |
| Read-only action surface (D5) + DEF-6 | inverted-command surface (relocate `.copy-btn`) | src/sdlc/dashboard/static/components/inverted-command/inverted-command.{js,css} |
| Alert-column markup + `.alert.{info,warn,crit}` + grid | Prototype reference (copy, tokens only) | docs/ux/dashboard-prototype/dashboard.html:105–140 |
| Severity tokens + STOP pulse | `--blue`/`--amber`/`--red`/`--motion-pulse-stop` | src/sdlc/dashboard/static/styles/tokens.css:117–121 |
| 7 trigger ids + severity ordering (READ, don't import) | `_ORDERED_TRIGGERS` + policy comment | src/sdlc/engine/stop_registry.py:17–34,35–43 |
| Sticky-halt state (single active) | `_fold_auto_loop_status` | src/sdlc/state/projection.py:86–110 (wired :156–161) |
| Typed state reader (if server-side, D1) | `read_state_or_refuse` | src/sdlc/state/reader.py:39–92 (precedent resume.py:45,76) |
| Journal reader (if D1b) | `iter_entries` | src/sdlc/journal/reader.py (precedent signoff.py:36) |
| Module-boundary + gate scripts | `check_module_boundaries.py` + dashboard static gates | scripts/check_module_boundaries.py; scripts/check_dashboard_{color_only,forbidden_patterns,motion,no_data_theme,no_framework,no_external_fonts}.py |
| RED test template (live-source static contract) | `test_phase_tracker_live_source.py` | tests/unit/dashboard/test_phase_tracker_live_source.py:27–119 |
| Playwright a11y + color-only-with-label | `_playwright_a11y.py` helpers | tests/dashboard/_playwright_a11y.py; tests/dashboard/test_color_only_dom.py |
| Active-STOP fixture (journal-project) | build `[stop_trigger_raised, auto_loop_iteration(stopped)]` → project | tests/unit/state/test_state_projection_auto_loop.py:19–75 |
| Contract-snapshot freeze (assert unchanged) | 7/7 snapshots | tests/contract_snapshots/v1/ ; scripts/freeze_wireformat_snapshots.py --check |
| Wheel force-include | Add new static/fixtures | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2814–2834] — Story 5.19 statement (2816–2818) + ACs (2820–2834, verbatim above)
- [Source: src/sdlc/engine/stop_registry.py:17–34,35–43,63–69] — `_ORDERED_TRIGGERS` (7 code `trigger_id`s + D-RETRO-3 ordering + first-match precedence); severity-hint tiers. **AUTHORITATIVE over the AC labels.**
- [Source: src/sdlc/engine/stop_triggers.py:16–23] — `StopDecision` = `{fired, trigger, target, reason}`
- [Source: src/sdlc/engine/stop_{high_risk,agent_failed,clarification,signoff,replan_dirty,bug_awaiting,pr_ready}.py] — per-trigger `trigger_id` (high_risk_path/agent_failed/open_clarification/signoff_required/replan_dirty/bug_awaiting_decide/pr_ready_story)
- [Source: src/sdlc/state/projection.py:86–110 (wired :156–161); src/sdlc/state/model.py:33–35] — sticky-halt fold (ADR-038); `auto_loop_status` + `stop_reason` (single sticky halt, no list/target/severity)
- [Source: docs/decisions/ADR-038-sticky-halt-projection.md; commit 5bd4e22; tests/unit/state/test_state_projection_auto_loop.py:19–75,49–101] — sticky-halt Accepted + tests; **supersedes deferred-work.md:761 (stale 2026-06-16 defer note)**
- [Source: src/sdlc/state/reader.py:39–92; src/sdlc/journal/reader.py; src/sdlc/dashboard/routes/state.py:15–40] — reader seams (`read_state_or_refuse`; `iter_entries`; `/state.json` streams raw bytes + ETag)
- [Source: src/sdlc/dispatcher/_panel_helpers.py:241–260; src/sdlc/cli/auto.py:27; _bmad-output/implementation-artifacts/deferred-work.md:51 (EPIC-4-STOP-TRIGGER-WIRE)] — mock/placeholder emission; `agent_failure_after_retries` non-registry string; real dispatch gated (D-RETRO-2)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.7:1271–1319] — STOP Banner / Alert normative anatomy + severity variants + a11y + keyboard
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.8:1381–1383 (Empty State), §7.11:1599–1613 (Disconnection — 5.20, do-not-build), §7.12:1615–1637 (Forbidden Patterns), §7.13:1650 (STOP banner → live-dot severity + inverted-command + pill), :64,155–157,234–235,716,743,753] — hierarchy/motion/forbidden-patterns/pattern-application
- [Source: _bmad-output/planning-artifacts/architecture.md:817,901,1151,1168–1172,1190] — `engine/stop_triggers.py` (FR21, total ordering); planned `dashboard/routes/stops.py → GET /api/stops` (D1b); read-only HTTP endpoints
- [Source: src/sdlc/dashboard/static/components/{empty-state,freshness-footer,section-heading,pills,inverted-command,activity-feed,kpi-strip,masthead}/…] — reused components (see Reuse map for exact lines)
- [Source: docs/ux/dashboard-prototype/dashboard.html:105–140] — `.overview-grid` 1.6/1 + `.alerts-col` + `#alertsHost` + `.alert.{info,warn,crit}` markup to reproduce (tokens only)
- [Source: src/sdlc/dashboard/static/styles/tokens.css:117–121] — `--blue`/`--amber`/`--red` + `--motion-pulse-stop`
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:924 (5.5 DEF-5 empty-state falsy message → owned by 5.19), :912 (5.8 DEF-6 relocate .copy-btn → 5.11/5.19), :798 (CR4.8-W3 unbounded reason → 5.19 render), :51 (EPIC-4-STOP-TRIGGER-WIRE)] — folded/related deferred items
- [Source: scripts/check_module_boundaries.py:142–152,163,202; scripts/check_dashboard_{color_only,forbidden_patterns,motion,no_data_theme,no_framework,no_external_fonts}.py] — boundary + dashboard static gates
- [Source: tests/unit/dashboard/test_phase_tracker_live_source.py:27–119; tests/dashboard/_playwright_a11y.py; tests/dashboard/test_color_only_dom.py] — RED live-source + Playwright a11y templates
- [Source: docs/sprints/epic-5-dag.md §2 (5.5→S19:136, 5.11→S19:158, E4→S19:177, S19→S20:161, S19→S21:162, S19→S22:165), §3 (L8:217), §5 (5.19 row:297), §6 (L8:331), §7 (D3 sticky-halt risk:352), Decision D3:404–422] — layer, edges, owner, gating, D3 ratified=(a)
- [Source: _bmad-output/implementation-artifacts/5-18-resume-card-rendering-real-you-are-here-suggested-next.md] — the shipped 5B swap precedent (dedicated route + `*-live.js` poller + poller hardening + review pattern); its Debug Log records the `live-dot.js` recursion defect (avoid live-dot dependence, D2)

## Dev Agent Record

### Agent Model Used

Composer

### Debug Log References

- Fixed duplicate `export sanitizeReason` in stop-banner.js (Playwright fixture rendered 0 banners until resolved).

### Completion Notes List

- **D1=(a):** Live poller reads `/state.json` ETag/304 slice (`auto_loop_status`/`stop_reason`); single real banner via `mapStateToTriggers`; all-7 proven by synthetic fixture.
- **D2=(a):** Severity via `.alert` left-edge + text tag + optional `live-dot-pulse--stop` dot — no `<live-dot>` element.
- **D3=(a):** `TRIGGER_META` owned in `stop-banner.js`, keyed on code `trigger_id`s; engine import forbidden.
- **D4=(a):** `sanitizeReason` — textContent-only, 200-char cap, control-char strip; unknown id → neutral banner.
- **D5=(a):** Suggested action via inverted-command + copy button only (read-only).
- Folded **DEF-5** (empty-state falsy message) and **DEF-6** (`.copy-btn` → `inverted-command.css`).
- Extended `check_dashboard_color_only.py` for `.stop-banner alert` text severity tags.
- Quality gate: 4319+ tests pass, coverage 88.62%, freeze 7/7, dashboard static gates green.

### File List

- src/sdlc/dashboard/static/components/stop-banner/stop-banner.js (new)
- src/sdlc/dashboard/static/components/stop-banner/stop-banner.css (new)
- src/sdlc/dashboard/static/components/stop-banner/stop-banner.fixture.html (new)
- src/sdlc/dashboard/static/components/stop-banner/stop-banner-live.js (new)
- src/sdlc/dashboard/static/components/stop-banner/stop-banner-live.fixture.html (new)
- src/sdlc/dashboard/static/components/empty-state/empty-state.js (modified — DEF-5)
- src/sdlc/dashboard/static/components/inverted-command/inverted-command.css (modified — DEF-6)
- src/sdlc/dashboard/static/components/resume-card/resume-card.css (modified — DEF-6)
- scripts/check_dashboard_color_only.py (modified — stop-banner severity tag gate)
- pyproject.toml (modified — force-include stop-banner assets)
- tests/unit/dashboard/test_stop_banner_fixture.py (new)
- tests/unit/dashboard/test_stop_banner_live_source.py (new)
- tests/dashboard/test_stop_banner_a11y.py (new)
- tests/unit/scripts/test_check_dashboard_color_only.py (modified)
- tests/unit/dashboard/test_resume_card_fixture.py (modified — DEF-6 assertion target)
- tests/fixtures/dashboard_color_only/clean_stop_banner_with_severity_tag.html (new)
- tests/fixtures/dashboard_color_only/violation_stop_banner_no_text_tag.html (new)
- tests/fixtures/dashboard/state-halted.json (new)
- tests/fixtures/dashboard/state-no-stop.json (new)
- _bmad-output/implementation-artifacts/sprint-status.yaml (modified)

### Review Findings

> bmad-code-review 2026-07-07 — layers: Blind Hunter + Edge Case Hunter + Acceptance Auditor (all Opus 4.8). Diff: uncommitted working-tree changes (story 5.19). Result: 1 decision-needed, 12 patch, 1 deferred, 1 dismissed. Core corrected-spec conformance verified FAITHFUL by all three layers (all 9 trigger_ids + severities, text tags, roles, empty-state branch, DEF-5/DEF-6 folds, D5 read-only action, no-transition motion, freeze 7/7).

> **Resolution 2026-07-07 — all 13 patches applied + verified.** Decision resolved → option (a): `SEVERITY_TAG.neutral = "NOTICE:"`. Verification: full `uv run pytest` GREEN (4329 passed, 4 platform-skips, 1 pre-existing xfail CR4.6-W2), coverage ≥87%; ruff format/check, color-only gate (incl. new multi-banner masking guard), and motion DD-14 gate all green. Added/strengthened 9 tests — 6 Playwright behavioral witnesses (hostile-reason inert render, empty-state branch, DEF-5 render, NOTICE neutral, reduced-motion pulse-off, keyboard tab-order) + live engine-registry cross-check + P2 multi-banner regression fixture. **Story stays `review`** — per project discipline `done` flips only post-merge (changes are still uncommitted); next step is the TDD-first commit ceremony (test→feat→docs) + merge + CI-green on main.

**Decision-needed** (RESOLVED 2026-07-07 → option (a), now a patch):

- [x] [Review][Patch] (from Decision, resolved (a)) Neutral/unknown-trigger banner has neither a severity color edge nor a text severity tag — `resolveMeta` maps an out-of-registry `trigger_id` to `NEUTRAL_META` (`severity:"neutral"`); `SEVERITY_TAG.neutral=""` and the class drops the severity token, so the banner renders `role="status"`, no `.info/.warn/.crit` edge, and a title of just the label. **Resolution:** add a neutral text marker `"NOTICE:"` so every banner carries a text tag (never gives an unknown a real severity). Fix: set `SEVERITY_TAG.neutral = "NOTICE:"` and update the mapping test to assert the neutral title carries it [src/sdlc/dashboard/static/components/stop-banner/stop-banner.js:74,159,168]

**Patch** (fixable without human input):

- [x] [Review][Patch] (HIGH) STOP-banner copy-to-clipboard aria-live announcement never reaches assistive tech — `ensureLiveRegion(host)` appends the sr-only region, then `host.replaceChildren()` on the next line wipes it, so the `liveRegion` handed to every copy button is detached (found by blind+edge+auditor). Fix: clear the host first, then `ensureLiveRegion`, or mirror resume-card.js:143-144,233 (remove only `.stop-banner` children, keep the region, `insertBefore`) [src/sdlc/dashboard/static/components/stop-banner/stop-banner.js:225-226]
- [x] [Review][Patch] (MEDIUM) Color-only gate's severity search leaks across adjacent banners — the `_SEVERITY_TAG` search runs over a flat ±window (`start-200 : start+800`), so a color-only banner passes when a sibling within that span carries a tag. Fix: scope the search to the banner's own element (forward-only from the match, bounded by the next `stop-banner alert` / element close), mirroring the live-dot path's `stripped[start:tag_end]` [scripts/check_dashboard_color_only.py:154-157]
- [x] [Review][Patch] (MEDIUM) Live poller commits the new ETag before `response.json()` resolves — a truncated/invalid body advances `etagRef.value`, so the next poll gets a 304 and the STOP slice freezes at last-good. Fix: parse the body first, set the ETag only after a successful parse [src/sdlc/dashboard/static/components/stop-banner/stop-banner-live.js:30-34]
- [x] [Review][Patch] (MEDIUM) `aria-labelledby` title ids are only per-host-unique (`stop-banner-title-${index}`) → duplicate ids when two banner hosts co-mount (`<stop-banner-host>` + live `#alertsHost`), so labels resolve to the wrong host's title. Fix: prefix the id with a per-host/per-render unique token [src/sdlc/dashboard/static/components/stop-banner/stop-banner.js:162]
- [x] [Review][Patch] (MEDIUM) D4 hostile-input hardening (the named load-bearing review check, CR4.8-W3) has no behavioral test — `test_untrusted_content_hardening_in_js` only greps source; `sanitizeReason` is never invoked on `<img onerror>` / a 10 KB string / control chars / `null`. Fix: add a behavioral witness that exercises `sanitizeReason` on hostile input [tests/unit/dashboard/test_stop_banner_fixture.py:94-98]
- [x] [Review][Patch] (MEDIUM) AC3 empty-state branch has no behavioral witness — Task 3 required a Playwright test asserting "no active STOPs → exactly one `<empty-state>`, zero `.stop-banner`, footer present"; the suite only drives the all-7 fixture and the live-source empty check is a grep. Fix: add the empty-branch Playwright witness [tests/dashboard/test_stop_banner_a11y.py:14-48]
- [x] [Review][Patch] (MEDIUM) AC2 mapping test hardcodes a duplicate severity dict and never cross-checks `engine/stop_registry.py` — Task 1 required cross-check against the engine severity ordering so the JS map cannot co-drift with the test copy. Fix: derive/assert the expected severities from the engine registry [tests/unit/dashboard/test_stop_banner_fixture.py:31-41,64-73]
- [x] [Review][Patch] (LOW) Re-invoking `startStopBannerLivePoller` on the same host leaks the prior `setInterval` — `host._stopPoller` is overwritten without disposing the old poller. Fix: call any existing `host._stopPoller()` before starting [src/sdlc/dashboard/static/components/stop-banner/stop-banner-live.js:133]
- [x] [Review][Patch] (LOW) Reduced-motion static-dot and `.a-action` keyboard-order Playwright witnesses (Task 2) are absent (CSS behavior itself is correct). Fix: add the two witnesses [tests/dashboard/test_stop_banner_a11y.py]
- [x] [Review][Patch] (LOW) DEF-5 falsy-message coercion is asserted only by source grep, not by rendering `renderEmptyState({message:""})`. Fix: add a behavioral witness for the empty-string → default-copy path [tests/unit/dashboard/test_stop_banner_fixture.py:135-139]
- [x] [Review][Patch] (LOW) Confused assertion `assert "innerHTML" not in js.replace("//", "")` — stripping `//` leaves comment bodies, so a harmless comment mentioning innerHTML would fail it; the replace does not do what it intends. Fix: `assert "innerHTML" not in js` [tests/unit/dashboard/test_stop_banner_fixture.py:98]
- [x] [Review][Patch] (LOW) Order-fragile assertion on `violations[0]` — `_scan_html` appends stop-banner violations after live-dot ones, so any future rule firing on the fixture would occupy index 0. Fix: assert membership across `violations`, not `[0]` [tests/unit/scripts/test_check_dashboard_color_only.py:84]

**Deferred:**

- [x] [Review][Defer] Live STOP-banner poller (`startStopBannerLivePoller` + `ensureAlertsColumn`) is built but not yet wired into the assembled dashboard `index.html` (still the Story-5.1 skeleton, kpi-strip only) — shipped fixture-only, which Task 4 explicitly permits when no full-page alerts host exists [src/sdlc/dashboard/static/index.html] — deferred, downstream 5.20/5.21 assemble the page and reuse this treatment

**Dismissed (1):** "Copy button copies raw actionText but displays normalized" (blind) — false positive: `bindCopyButton` (resume-card.js:110-118) calls `normalizeCommand(command)` internally before `clipboard.writeText`, so the copied text equals the displayed `normalizeCommand(actionText)`; stop-banner faithfully mirrors resume-card's own pattern.

## Change Log

- 2026-07-06: Story 5.19 implemented (dev-story). Net-new `stop-banner` component + live poller; decisions D1(a)/D2(a)/D3(a)/D4(a)/D5(a) ratified. Folds DEF-5 + DEF-6. Tests + Playwright a11y + color-only gate extension. Freeze 7/7 unchanged.
- 2026-07-06: Story 5.19 created (create-story, "tạo US cho layer tiếp theo" → Epic-5 DAG **L8/5C**, single-story layer after all of L1–L7 (5.1–5.18) done). Net-new `stop-banner` component rendering all 7 Epic-4 trigger types with severity via `.alert` treatment + text severity label (never color-only), Empty State + freshness footer when zero, content-delta live poller reading the sticky `state.json` STOP slice. **Two code-analysis passes (Opus, `engine/`+`state/`+frontend) surfaced four AC-vs-code divergences the story locks down authoritatively:** (1) **4 of 7 AC trigger names are wrong** — `high_risk`→`high_risk_path`, `clarification`→`open_clarification`, `bug_awaiting`→`bug_awaiting_decide`, `pr_ready`→`pr_ready_story` (agent_failed/signoff_required/replan_dirty OK) per `engine/stop_registry.py:35–43`; the corrected map (keyed on code ids, severity intent preserved) is in Dev Notes; (2) `state.json` exposes a **single** sticky `stop_reason` string, not a 7-trigger list, so "up to 7 + target id + suggested action" is a rendering-capability requirement driven by a synthetic all-7 fixture, not from state (D1); (3) `<live-dot>` has only 3 variants (no info/crit) + a known recursion defect → severity is `.alert` left-edge + text tag, NOT live-dot (D2); (4) UX §6.7's Run-command/Mark-resolved buttons are forbidden (read-only 405 + §7.12) → copyable inline-code action (D5). Decisions raised: D1 (data source — state.json single-halt [rec] vs `/api/stops` journal resolver vs `stops[]` projection) / D2 (severity via `.alert` not live-dot) / D3 (JS-owned severity map, engine import-forbidden) / D4 (untrusted `stop_reason`/`reason` sanitization, CR4.8-W3) / D5 (read-only copyable action). **Wave-boundary verified:** sticky-halt fix `_fold_auto_loop_status` (ADR-038, commit 5bd4e22, `state/projection.py:86–110`) present + wired + tested — the load-bearing E4→5.19 gate; the DAG (D4 CLOSED) supersedes the stale `deferred-work.md:761` defer note. Real emission is mock/placeholder-gated (EPIC-4-DEBT-AUTO-REAL-DISPATCH, D-RETRO-2); 5.19 gated on sticky STOP state only (Decision D3=(a)), not real dispatch. Folds 5.5 DEF-5 (empty-state falsy message) + 5.8 DEF-6 (relocate `.copy-btn`, if copy reused). Data-validation + a11y review focus. Anti-scope: do-not-build disconnection (5.20) / below-1280 (5.21) / real dispatch / journal `/api/stops` (unless D1b ratified). No wire-format shape edit → freeze stays 7/7.
