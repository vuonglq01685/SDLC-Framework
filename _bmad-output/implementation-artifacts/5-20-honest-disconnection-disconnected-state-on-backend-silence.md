# Story 5.20: Honest-Disconnection + Disconnected State on Backend Silence

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG **L9 (5C)**, cap **2** — parallel with **5.21** (epic-5-dag.md §3:218, §6:332). Worktree: `epic-5/5-20-honest-disconnection`. Owner **Sally** (dag §5:298). On the **critical-path spine** `5.2→5.4→5.5→5.11→5.19→5.20→5.22` (dag §4:254). Depends on: **5.19→5.20** (disconnection reuses the STOP-banner treatment; dag §2:161, done) + **5.5→5.20** (live-dot `disconnected` variant; §2:137, done) + **5.6→5.20** (masthead 60 s aria-live rate-limit; §2:159, done) + **5.8→5.20** (resume card; §2:160, done). Downstream: **5.20→5.22** (terminal a11y release gate; §2:166). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate **N/A** (epic-5 in-progress, cleared at 5.1). Review focus: **a11y** (aria-live enter+leave, page-wide simultaneity) + **resilience** (never false-disconnect on ONE transient failure; recover within one poll). No wire-format shape edit → **freeze stays 7/7**. This builds disconnection DETECTION + page-wide coordination; it does NOT build the below-1280 viewport banner (**5.21**) or real auto-loop dispatch. Sibling L9 worktree 5.21 also reuses the STOP-banner treatment + may touch `index.html` — coordinate (CONTRIBUTING §3.3 rebase-between-merges). -->

## Story

As any user trusting the dashboard's liveness signal,
I want the dashboard detecting backend silence (poll failures) and rendering an honest disconnection treatment (Disconnected State component) on the masthead and resume card,
So that silent breakage is impossible (UX-DR16, UX-DR30, §7.11).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.20, lines 2844–2858).

**Given** the dashboard polling `/state.json` every 3 seconds
**When** N consecutive polls fail (network error, 5xx, timeout) where N is the documented threshold
**Then** the masthead's live-dot transitions to `disconnected` variant (Story 5.5)
**And** the masthead's sub-line replaces `UPDATED HH:MM:SS` with `DISCONNECTED · LAST POLL HH:MM:SS`
**And** the Resume Card's freshness footer transitions to `disconnected`

**Given** the disconnected state
**When** polling resumes successfully
**Then** the live-dot transitions back to `default` within one successful poll
**And** an `aria-live="polite"` announcement fires for entering AND leaving disconnected state (rate-limited per Story 5.6)

**Given** the disconnected banner option (info/warn/crit severity)
**When** disconnection is sustained
**Then** an explicit honest-disconnection banner can also be shown (per §7.11)
**And** the banner uses the same treatment as STOP banners (Story 5.19) for visual consistency

> ⚠️ **AC-vs-CODE — READ "Wave-boundary verification" + Decisions D1–D4 BEFORE coding.** Most of the *rendering* already exists (do NOT rebuild): the `<live-dot>` `disconnected` variant, the masthead `DISCONNECTED · LAST POLL HH:MM:SS` sub-line branch, and the 60 s `aria-live` enter/leave rate-limiter are **all already shipped** (5.5/5.6, see Reuse map). This story is **detection + page-wide coordination**, not rendering-from-scratch. Two premises the AC leaves implicit and this story locks down: (1) disconnection is **client-detected** — the server cannot send `connection_variant="disconnected"` when it is the thing that is down, so the disconnected state is *synthesized on the client* after **N=3 consecutive fetch failures** (§7.11); the JSON `connection_variant` flag exists only to drive the *synthetic* preview, never the real path (D3); (2) §7.11's "page-wide, all surfaces enter/exit **simultaneously**" contract cannot be met by today's **independent** per-poller catch blocks (masthead / resume / kpi / stop-banner each poll a different endpoint and silently keep last-good) — it needs a shared **connection-state broker** (D1). The **Resume Card disconnected treatment does not exist yet** and must be built (D4).

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** every AC clause is a testable contract → tests-first. **(AC clause 1) N-fail → disconnected** — a broker unit test drives 3 consecutive rejected polls → asserts page-wide `disconnected`; 1–2 failures do NOT flip (no false-disconnect); masthead live-dot=`disconnected` + sub-line=`DISCONNECTED · LAST POLL …` + resume footer=`disconnected`. **(AC clause 2) recover in one poll + aria-live enter/leave** — one successful poll after disconnect resets to `default`; assert the rate-limited live region announced BOTH "Disconnected" (enter) and "Connected" (leave). **(AC clause 3) honest-disconnection banner** — sustained disconnection renders the §7.11 banner via the reused STOP-banner treatment. **Resolve Decisions D1–D4 BEFORE coding.**

- [x] **Task 0 — Resolve Decisions D1 (page-wide coordination: shared connection-state broker vs per-poller independent count) + D2 (scope: broker + 3 AC-named surfaces fixture-first vs full §7.11 page assembly) + D3 (threshold N + 304-is-success + recovery semantics) + D4 (build the Resume Card disconnected treatment — extend `renderResumeCard` variant vs external wrap) BEFORE coding** (AC: all)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). Raise **D1** and **D2** as D-labels for architect/PO ratification before branching — D1 is load-bearing (a new client-side coordination primitive) and D2 sets the story boundary against the not-yet-assembled page.

- [x] **Task 1 — Net-new client connection-state broker (D1, D3)** (AC: 1, 2) — *tests-first*
  - [x] Create `components/connection-state/connection-state.js` — a tiny client-only pub/sub broker (NO server route, NO wire contract). API: `reportPollResult({ ok })` (pollers call on every tick), `subscribe(fn)` → dispose, `getState()` → `"default" | "disconnected"`. Keys off the **canonical `/state.json` liveness signal** (the masthead poll), NOT per-endpoint. Count **consecutive** failures; at **N=3** (D3, §7.11 "≥ 3") flip page-wide state to `disconnected` and notify subscribers; **one** `ok:true` (incl. a 304 — a 304 is a SUCCESS, see D3) resets the counter and flips back to `default` within that single poll (AC2). Own `DISCONNECT_THRESHOLD = 3` as the documented constant.
  - [x] **Never false-disconnect:** 1 or 2 consecutive failures MUST NOT flip state (the existing masthead catch already keeps last-known-good for transients). Unit-test the 1-fail, 2-fail, 3-fail, and fail→recover→fail sequences.
  - [x] Boundary: this is a **frontend-only** primitive (no `dashboard→engine/cli`, no new Python route). `check_module_boundaries.py` scans Python only; keep the JS file <300 LOC by convention (siblings ≤260).

- [x] **Task 2 — Masthead poll-fail detection wired to the broker (D1)** (AC: 1, 2) — *tests-first*
  - [x] In `startMastheadPoller` (`masthead.js:158–180`), call `connectionState.reportPollResult({ ok })` on every tick: `ok:false` in the `catch` (currently the swallow-and-keep-last-good block at `:170–175` — the comment there already names 5.20 as owner), `ok:true` on a 200 **and** on a 304 (D3). Subscribe the masthead render to broker state: when `disconnected`, render `connectionVariant="disconnected"` (which the EXISTING `formatMastheadSubLine` `:54–58` turns into `DISCONNECTED · LAST POLL HH:MM:SS`, and drives the live-dot red variant). Do **NOT** rewrite the sub-line/variant machinery — only *trigger* it from real failures instead of only the JSON flag.
  - [x] **aria-live enter/leave (AC2):** reuse the shipped `createAriaLiveRateLimiter` (`masthead.js:22–41`) — feed the broker-driven variant changes through it so BOTH "Disconnected" (enter) and "Connected" (leave) are announced, rate-limited to 60 s per Story 5.6. The rate-limiter's suppress-without-advancing subtlety (`:31–35`) already re-announces a change deferred inside a 60 s window — verify a disconnect+reconnect inside one window still surfaces the current state.
  - [x] **Recovery in one poll (AC2):** the first `ok:true` after disconnect resets the broker → masthead re-renders `default` within that tick. Playwright/unit witness the transition both ways.
  - [x] Reduced-motion (DD-16): the disconnected live-dot uses `live-dot-pulse--stop` → static red under `prefers-reduced-motion` (already handled by live-dot + focus-motion.css — assert, do not rebuild).

- [x] **Task 3 — Resume Card disconnected treatment (D4, §6.4)** (AC: 1) — *tests-first*
  - [x] Build the **not-yet-existing** disconnected treatment (`resume-card.css` has none today): per UX §6.4:1152 — freshness footer `variant="disconnected"` (red dot) showing `DISCONNECTED — last poll HH:MM:SS`; soft **amber** outline on the card (`--amber` / `--amber-soft`); copy button **disabled** (`aria-disabled="true"` + `--ink-dim` visual, click no-ops); the last-known suggested command **preserved** with explicit "may be stale" warning text. Extend the `renderResumeCard` seam via its existing `variant` parameter (D4a: it already carries `variant="loading"/"default"` — add `"disconnected"`), NOT an external wrapper.
  - [x] Subscribe the resume-card live poller (`resume-card-live.js:130–133`, whose catch currently silently keeps last-good) to the broker: on `disconnected`, re-render with `variant="disconnected"`; on recovery, back to `default`. Preserve the P3 unchanged-content optimization (`:118–128`) — do not tear down copy-button focus on steady-state.
  - [x] a11y: disabled copy button announces disabled state; the "may be stale" text is a real text signal (never color-only via the amber outline alone).

- [x] **Task 4 — Honest-disconnection banner via reused STOP-banner treatment (AC3, §7.11)** (AC: 3) — *tests-first*
  - [x] Render the §7.11 explicit banner — `"Dashboard cannot reach state. Last successful poll HH:MM:SS."` — reusing the **STOP-banner `.alert` treatment** (Story 5.19). §7.11 specifies a **red** (crit) banner; the AC permits an info/warn/crit option. Reuse `renderStopBanners`/`createStopBannerElement` (`stop-banner.js:228,160`) with a disconnection view-model, OR the `.alert` CSS class + a small banner element if the STOP `TRIGGER_META` keying is a poor fit — pick in D-note and keep it text-carrying (severity tag + copy, never color-only) and `role="status"`/`role="alert"` per severity.
  - [x] This banner is broker-driven (appears only while `disconnected`, removed on recovery — content-delta, DD-06). It is **not** user-dismissible (unlike 5.21's viewport banner). No `transition:` (DD-14).

- [x] **Task 5 — Scope boundary vs §7.11 remaining surfaces (D2)** (AC: 1) — *tests-first*
  - [x] §7.11 also dims KPI strip (`--ink-mute`), phase tracker / backlog tree (`--ink-mute`), and freezes the activity feed (stop appending), while the STOP-banner column is preserved as-is. Per **D2**, the page is NOT yet assembled (`index.html` is still the 5.1 skeleton + kpi-strip only — 5.19 shipped fixture-only). **D2a (recommended):** 5.20 owns the **broker + the three AC-named surfaces** (masthead, resume card, honest-disconnection banner) driven by committed fixtures, and exposes the broker `subscribe` API so the remaining §7.11 surfaces attach when the page assembles; the KPI-dim / feed-freeze / tree-mute wiring is a documented follow-on (or 5.22 baseline). **D2b:** fully assemble `index.html` with all §7.11 surfaces now — larger, and collides with sibling 5.21's `index.html` touch. Record the pick; if D2a, `log` the deferred surfaces explicitly (no silent scope-cut).

- [x] **Task 6 — Committed fixtures + tests + packaging + quality gate + freeze** (AC: 1, 2, 3) — *tests-first*
  - [x] Commit fixtures: a `connection-state.fixture.html` (or `*-live.fixture.html`) driving the fail→disconnect→recover sequence with an injectable `fetchFn` (mirror the sibling `*-live.js` poll-injection convention), plus a masthead + resume-card disconnected-state visual fixture. Use injected `fetchFn`/fake timers — never real network flakiness (web testing rule: deterministic waits, no timeout-based assertions).
  - [x] Tests: `tests/unit/dashboard/test_connection_state.py` (broker: 1/2-fail no-flip, 3-fail flip, 304-is-success, recover-in-one), `test_masthead_disconnection.py` (variant + sub-line + aria-live enter/leave via the rate-limiter), `test_resume_card_disconnected.py` (amber outline + disabled copy + "may be stale" + footer variant). Add a `tests/dashboard/` Playwright a11y witness (disconnected masthead + banner: `role`, live-region announcements both directions, reduced-motion static dot, keyboard order). RED template: `tests/unit/dashboard/test_phase_tracker_live_source.py` + the 5.19 `test_stop_banner_a11y.py`.
  - [x] Add new static files to `force-include` [pyproject.toml]. Component CSS uses `var(--*)` only (5.2 stylelint). Run **all dashboard static gates**: `check_dashboard_color_only.py` (the disconnected banner + resume "may be stale" must carry text, not amber-only), `check_dashboard_forbidden_patterns.py` (no `<dialog>`/toast/`<form>`/`pushState`/skeleton — the disconnection banner is NOT a toast), `check_dashboard_motion.py` (DD-14 — no `transition:`; pulse-stop keyframe OK), `check_dashboard_no_data_theme.py` (DD-09), `check_dashboard_no_framework.py` (DD-08), `check_dashboard_no_external_fonts.py`.
  - [x] Full `uv run pytest` (the **literal** invocation — subsets lie, memory `project_test_scope_and_order_gotcha`) + coverage ≥ 87%; ruff format/check; mypy --strict on any new `.py`; `check_module_boundaries.py` (JS broker is frontend-only; no new `dashboard→engine/cli`); `mkdocs build --strict`. **Zero wire-format shape change → `scripts/freeze_wireformat_snapshots.py --check` = 7/7** (disconnection is client-detected — no `State`-model field, no route change; the pre-existing `connection_variant` render flag is not a frozen contract).

## Dev Notes

### Wave-boundary verification (5.19 → 5.20) — READ FIRST

The `5.19→5.20` edge means 5.20 **reuses the STOP-banner treatment** (dag §2:161); the disconnection machinery it depends on from 5.5/5.6 is already shipped. Verification against the live codebase (2026-07-07):

- **`<live-dot>` `disconnected` variant — PRESENT.** `live-dot.js:8–12` — `disconnected: { label: "DISCONNECTED", pulse: "live-dot-pulse--stop" }` (red, stop-pulse). The masthead already sets `dot.setAttribute("variant", connectionVariant)` (`masthead.js:140–141`). ⇒ AC1 "live-dot → disconnected variant" is a *trigger* problem, not a build problem.
- **Masthead disconnected sub-line — PRESENT.** `formatMastheadSubLine` (`masthead.js:54–58`) already returns `DISCONNECTED · LAST POLL ${timestamp}` when `disconnected` is truthy. ⇒ AC1 sub-line is already built; 5.20 makes `disconnected` true on *real* poll failure.
- **60 s aria-live enter/leave rate-limiter — PRESENT.** `createAriaLiveRateLimiter` (`masthead.js:22–41`) + `variantAnnouncementText` (`:17–20`, "Connected"/"Disconnected"/"Connection warning"). It already announces BOTH directions on variant change, rate-limited to `ARIA_LIVE_INTERVAL_MS = 60_000` (Story 5.6). The suppress-**without-advancing** logic (`:31–35`) deliberately re-announces a change deferred inside a window. ⇒ AC2's "enter AND leave, rate-limited per 5.6" is satisfied by reuse.
- **The central gap — detection + coordination is NOT built.** `startMastheadPoller`'s catch (`masthead.js:170–175`) *swallows* failures and keeps last-known-good, with the explicit comment: *"Real disconnection detection (≥3 consecutive failures → page-wide disconnected) is Story 5.20's responsibility… The disconnected visual is driven only by the synthetic fixture flag, never synthesized on error."* Today `mapStateFromJson` sets `disconnected` **only** from the JSON `connection_variant` flag (`:66–78`) — i.e. a server-sent preview, never a real detection. ⇒ **5.20 owns the client-side consecutive-failure detector.**
- **Independent pollers = the §7.11 coordination gap.** masthead → `/state.json`, resume-card-live → `/api/resume`, kpi-strip-live → `/api/dora`, stop-banner-live → `/state.json`, activity-feed / backlog-tree → their own. Each has its own `catch` that keeps last-good. **No shared connection state exists.** §7.11's "page-wide, all surfaces enter/exit simultaneously" ⇒ **D1 broker.**
- **Resume Card disconnected treatment — ABSENT.** `resume-card.css` has no disconnected/amber/stale rules (grep 2026-07-07 = 0 hits). UX §6.4:1152 fully specifies it (amber outline, disabled copy, "may be stale", footer variant) — 5.20 **builds** it (D4).
- **Page not assembled.** `index.html` is still the Story-5.1 skeleton + a single `kpi-strip` live poller (`index.html:14,20–26`); masthead / resume card / stop-banner are fixture-only (5.19 Deferred). ⇒ D2 scope boundary.

### Locked design decisions (verbatim — these govern the story)

- **Threshold N = 3 consecutive poll failures** (§7.11 "polling fails ≥ 3 consecutive times"). A failure = a **thrown** fetch (network error / 5xx via `!response.ok` throw at `masthead.js:84` / timeout). A **304 is a SUCCESS** (no-change) — `pollStateJson` returns `null` on 304 (`masthead.js:83`) without throwing, so the broker must treat "no exception" as `ok:true`, including the 304 no-op path. Recovery = **one** `ok:true` resets the counter and exits disconnected within that poll (AC2). [Source: ux §7.11:1613; masthead.js:80–88,162–176]
- **Disconnection is CLIENT-detected and page-wide, not server-reported.** When the backend is silent the server sends nothing — the client synthesizes the disconnected state. §7.11 consistency contract: "Disconnection is a **page-wide** state, not a per-component state… all live surfaces enter… simultaneously… exit simultaneously on the next successful poll. There is no per-surface 'stale' treatment in v1." [Source: ux §7.11:1599–1613]
- **§7.11 surface application (normative).** Masthead → red static dot + `DISCONNECTED · LAST POLL HH:MM:SS`; below masthead → thin red banner `"Dashboard cannot reach state. Last successful poll HH:MM:SS."`; resume card → amber outline + disabled copy + stale footer; KPI strip → values dim `--ink-mute`; phase tracker / backlog tree → `--ink-mute` (preserved last-known); activity feed → stops appending, existing entries dim; STOP-banner column → preserved as-is (pre-disconnection alerts remain real). [Source: ux §7.11:1603–1611]
- **Resume Card disconnected (§6.4).** "entire card wrapped in a soft amber outline; freshness footer shows `DISCONNECTED — last poll HH:MM:SS`; copy button disabled (`aria-disabled="true"` + visual `--ink-dim`); suggested command preserved (last known) with explicit warning text 'may be stale'." [Source: ux §6.4:1152]
- **Masthead disconnected (§6.2).** "red live-dot, sub-line shows `DISCONNECTED · LAST POLL HH:MM:SS` instead of `UPDATED`. No silence — DD principle 'Honest disconnection' enforced." [Source: ux §6.2:1064]
- **Forbidden patterns (§7.12) still bind.** The honest-disconnection banner is a **persistent side/inline banner, NOT a toast/notification** (`Toasts` forbidden; `"Live region" toast announcements for routine polls` forbidden — the live region announces only **connection-state changes**, rate-limited 60 s). No browser-notifications. No modal. [Source: ux §7.12:1624–1625,1634]

### Frozen foundation to consume (do NOT redefine)

```text
Net-new for 5.20 (create):
  components/connection-state/connection-state.js   broker: reportPollResult({ok}) / subscribe(fn) / getState(); DISCONNECT_THRESHOLD=3 (D1,D3)
  components/connection-state/connection-state.fixture.html   fail→disconnect→recover (injected fetchFn/fake timer)
  (resume-card disconnected CSS — new rules in resume-card.css; §6.4 amber outline + disabled copy + stale)
  (honest-disconnection banner — reuses stop-banner treatment; Task 4)

Reuse (do NOT rebuild):
  live-dot disconnected variant     components/live-dot/live-dot.js:8–12   (red + live-dot-pulse--stop; already wired in masthead)
  masthead disconnected sub-line    components/masthead/masthead.js:54–58  formatMastheadSubLine (DISCONNECTED · LAST POLL …)
  60 s aria-live enter/leave        components/masthead/masthead.js:17–41  createAriaLiveRateLimiter + variantAnnouncementText
  masthead poll loop + catch seam   components/masthead/masthead.js:158–180  startMastheadPoller (report ok/!ok here; catch :170–175)
  /state.json + ETag/304 poll       components/masthead/masthead.js:80–88  pollStateJson (304 → null == SUCCESS; !ok → throw == FAIL)
  resume-card render seam (variant) components/resume-card/resume-card.js  renderResumeCard(host, {…, variant})  (extend with "disconnected", D4)
  resume-card live poller + catch   components/resume-card/resume-card-live.js:106–151  (subscribe broker; P3 unchanged-content guard :118–128)
  freshness-footer disconnected     components/freshness-footer/freshness-footer.js:37,54–56  variant="disconnected" → red dot
  STOP-banner treatment (AC3)       components/stop-banner/stop-banner.js:160,228  createStopBannerElement / renderStopBanners (+ stop-banner.css .alert)
  severity + soft tokens            styles/tokens.css:103–104,117–122,253  --ink-mute/--ink-dim/--amber(-soft)/--red(-soft)/--blue/--motion-pulse-stop
  poller hardening idiom            components/resume-card/resume-card-live.js:92–151  inFlight/disposed/AbortController/keep-last-good
```

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — page-wide disconnection coordination (HIGH / architecture).** §7.11 mandates a single page-wide state entered/exited **simultaneously** by all live surfaces; today every poller is independent with its own last-good catch. *Recommendation (a):* a shared **connection-state broker** (`connection-state.js`, client-only pub/sub) keyed off the canonical `/state.json` liveness poll — pollers `reportPollResult({ok})`, surfaces `subscribe`; flips at N=3, recovers in one poll. *(b)* each poller counts its own failures independently — **REJECTED** (different endpoints fail independently → surfaces flicker out of sync, breaking the §7.11 consistency contract). Prefer (a). Raise as a D-label (new client coordination primitive).

**D2 — disconnection scope vs the un-assembled page (MED→load-bearing / scope).** ACs name masthead + resume card + honest-disconnection banner; §7.11 also names KPI-dim / tree-mute / feed-freeze; `index.html` is not yet assembled. *Recommendation (a):* 5.20 owns the **broker + the three AC-named surfaces** (fixture-driven, mirroring 5.19) and exposes `subscribe` so the rest attach at page-assembly time; `log` the deferred surfaces (no silent cut). *(b)* fully assemble `index.html` with all §7.11 surfaces now — larger and collides with sibling 5.21's `index.html` touch (same L9). Prefer (a). Raise as a D-label.

**D3 — threshold N + failure/success semantics (MED / resilience).** *Recommendation (a):* **N = 3** consecutive **thrown** polls (network / 5xx / timeout); a **304 counts as success** (no-op render, resets counter); recovery on the first success within one poll. 1–2 failures never flip (no false-disconnect). This is the load-bearing correctness check — the review must witness the 2-fail-no-flip and fail→recover→fail sequences.

**D4 — build the Resume Card disconnected treatment (MED / correctness).** It does not exist yet (§6.4 fully specs it). *Recommendation (a):* extend the existing `renderResumeCard` `variant` parameter with `"disconnected"` (amber outline + disabled copy + "may be stale" + footer variant) — the seam already carries `variant="loading"/"default"`. *(b)* wrap the card externally — **REJECTED** (duplicates the render seam, risks the P3 focus-preservation regression). Prefer (a).

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the net-new client **connection-state broker** (consecutive-failure detection at N=3, page-wide pub/sub, recover-in-one-poll); wiring the masthead poll catch to report failures + drive the (already-built) disconnected variant / sub-line / aria-live; the **Resume Card disconnected treatment** (§6.4, new); the **honest-disconnection banner** reusing the STOP-banner `.alert` treatment (AC3); the broker `subscribe` API for the remaining §7.11 surfaces (D2).
- **Must NOT build:** the **below-1280 viewport degradation banner** (that is **5.21**, edge 5.19→5.21 — it *also* reuses the STOP-banner treatment but with `--blue` + a dismiss `×`; do not conflate). **Real auto-loop dispatch** (`EPIC-4-DEBT-AUTO-REAL-DISPATCH`, D-RETRO-2). A **server-side disconnection signal / new route** (disconnection is client-detected; the server can't report its own silence — no new `dashboard/routes/*`). Any **new/changed wire contract** (`connection_variant` is a render flag, not a frozen contract → freeze 7/7). No **false-disconnect on a single transient** (N=3). No modals/toasts/notifications (§7.12); no CSS `transition:`/transforms (DD-14); no per-surface "stale" treatment (§7.11 — page-wide only in v1).

### Project Structure Notes

- **Net-new component under the frozen layout convention** `static/components/<name>/<name>.js` + `<name>.fixture.html` (`live-dot.js:4` D2 convention). All new static files → `force-include` [pyproject.toml].
- **The broker is a frontend-only primitive** — no server route, no Python module, no `dashboard→engine/cli` edge. `check_module_boundaries.py` (Python-only AST) is unaffected; keep the JS file small by convention (<300 LOC; siblings ≤260).
- **Extend, don't fork, the frozen seams:** masthead poll loop, `renderResumeCard` (variant param), `createAriaLiveRateLimiter`, `renderStopBanners`, `freshness-footer` variant — all already carry the hooks 5.20 needs. The review checks that 5.20 *triggers* existing machinery rather than duplicating it.
- **Determinism (web testing rule):** inject `fetchFn` + fake timers; assert on state transitions, never on wall-clock timeouts. Disconnection tests are the classic flaky-test trap — no real network, no `sleep`.
- **L9/5C, cap 2 — parallel with 5.21.** Worktree `epic-5/5-20-honest-disconnection`, owner Sally. Branch from `main`, linear merge (CONTRIBUTING §3). Both L9 worktrees reuse the STOP-banner treatment and may touch `index.html`; per §3.3 the second-merged rebases on the first. Keep 5.20 fixture-first (D2a) to stay cleanly parallel. 5.22 (terminal a11y gate) re-scans the disconnected surface — it must merge clean + a11y-green.
- Zero wire-format contract shape change (client detection; no `State` field, no route) → **freeze stays 7/7**.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Disconnected live-dot (red, stop-pulse) | `VARIANTS.disconnected` | src/sdlc/dashboard/static/components/live-dot/live-dot.js:8–12 |
| Masthead disconnected sub-line | `formatMastheadSubLine` | src/sdlc/dashboard/static/components/masthead/masthead.js:54–58 |
| aria-live enter/leave, 60 s rate-limit | `createAriaLiveRateLimiter` + `variantAnnouncementText` | src/sdlc/dashboard/static/components/masthead/masthead.js:17–41 |
| Poll loop + fail seam (report !ok in catch) | `startMastheadPoller` / `pollStateJson` | src/sdlc/dashboard/static/components/masthead/masthead.js:80–88,158–180 |
| Resume-card render seam (add "disconnected" variant) | `renderResumeCard` | src/sdlc/dashboard/static/components/resume-card/resume-card.js |
| Resume-card poller (subscribe broker; unchanged-content guard) | `startResumeCardLivePoller` | src/sdlc/dashboard/static/components/resume-card/resume-card-live.js:106–151 |
| Freshness footer disconnected variant | `renderFreshnessFooter` (variant) | src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:37,54–56 |
| Honest-disconnection banner (AC3) | `renderStopBanners` / `createStopBannerElement` + stop-banner.css `.alert` | src/sdlc/dashboard/static/components/stop-banner/stop-banner.js:160,228 |
| Poller hardening (inFlight/disposed/AbortController/keep-last-good) | `startResumeCardLivePoller` | src/sdlc/dashboard/static/components/resume-card/resume-card-live.js:92–151 |
| sessionStorage guarded access (if needed) | try/catch precedent | src/sdlc/dashboard/static/components/resume-card/resume-card.js:48 |
| Color/soft/ink tokens | `--ink-mute`/`--ink-dim`/`--amber(-soft)`/`--red(-soft)` | src/sdlc/dashboard/static/styles/tokens.css:103–104,117–122 |
| RED live-source static-contract template | `test_phase_tracker_live_source.py` | tests/unit/dashboard/test_phase_tracker_live_source.py:27–119 |
| Playwright a11y + live-region witness | 5.19 a11y suite + helpers | tests/dashboard/test_stop_banner_a11y.py; tests/dashboard/_playwright_a11y.py |
| Module-boundary + dashboard static gates | boundary + gate scripts | scripts/check_module_boundaries.py; scripts/check_dashboard_{color_only,forbidden_patterns,motion,no_data_theme,no_framework,no_external_fonts}.py |
| Contract-snapshot freeze (assert unchanged) | 7/7 snapshots | tests/contract_snapshots/v1/ ; scripts/freeze_wireformat_snapshots.py --check |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2836–2858] — Story 5.20 statement (2838–2840) + ACs (2844–2858, verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.11:1599–1613] — Honest-Disconnection Treatment (all surfaces + page-wide consistency contract + ≥3-fail threshold). **AUTHORITATIVE for scope.**
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §6.2:1064 (masthead disconnected), §6.4:1152 (resume card disconnected), §6.8:1385–1400 (Disconnected State component, prototype-absent), §7.12:1624–1625,1634 (forbidden: toasts/notification-toasts), §7.13:1645–1654 (pattern application — masthead/kpi/resume/tracker/tree all consume Honest-disconnection)] — per-surface anatomy + forbidden patterns
- [Source: _bmad-output/planning-artifacts/epics.md UX-DR16:206, UX-DR30:224] — Disconnected State component + Honest-Disconnection treatment design requirements
- [Source: src/sdlc/dashboard/static/components/masthead/masthead.js:8–41,54–58,66–88,158–180] — connection variant + sub-line + aria-live rate-limiter + poll loop + the catch seam (`:170–175`) that names 5.20 as detection owner
- [Source: src/sdlc/dashboard/static/components/live-dot/live-dot.js:8–12] — `disconnected` variant (red + `live-dot-pulse--stop`)
- [Source: src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js:37,54–56] — `variant` attr → live-dot; disconnected footer
- [Source: src/sdlc/dashboard/static/components/resume-card/resume-card.js; resume-card-live.js:106–151; resume-card.css] — render seam (variant), live poller (subscribe target), **no disconnected CSS yet** (D4 builds it)
- [Source: src/sdlc/dashboard/static/components/stop-banner/stop-banner.js:160,228; stop-banner.css] — reused `.alert` treatment for the honest-disconnection banner (AC3, Story 5.19)
- [Source: src/sdlc/dashboard/static/styles/tokens.css:103–104,117–122,232–234,253] — `--ink-mute`/`--ink-dim`/`--amber(-soft)`/`--red(-soft)`/`--blue`/layout/`--motion-pulse-stop`
- [Source: src/sdlc/dashboard/static/index.html:14,19–27] — page NOT assembled (kpi-strip live poller only) → D2 scope boundary
- [Source: _bmad-output/implementation-artifacts/5-19-stop-banner-rendering-all-7-trigger-types.md — Deferred: live poller built but index.html not assembled; anti-scope names 5.20/5.21] — the sibling shipped precedent + the "downstream 5.20/5.21 assemble the page" hint
- [Source: docs/sprints/epic-5-dag.md §2 (5.19→S20:161, 5.5→S20:137, 5.6→S20:159, 5.8→S20:160, S20→S22:166), §3 (L9 cap 2:218), §4 (critical path:254), §5 (5.20 row:298), §6 (L9:332)] — layer, edges, owner, critical-path
- [Source: CONTRIBUTING.md §2 (TDD-first), §3 (worktree-per-story / linear merge / §3.3 rebase-between), §5 (decision protocol); memory project_test_scope_and_order_gotcha (literal `uv run pytest`)] — process discipline

## Dev Agent Record

### Agent Model Used

claude-sonnet-5-thinking-high

### Debug Log References

- D1(a)/D2(a)/D3(a)/D4(a) ratified per story recommendations before coding.
- `.copy-btn` class in resume-card.css tripped DEF-6 stop-banner static test — used `.resume-card__copy--disabled` instead.

### Completion Notes List

- Added client-only `connection-state.js` broker (`DISCONNECT_THRESHOLD=3`, `reportPollResult`/`subscribe`/`getState`) plus `renderHonestDisconnectionBanner` reusing STOP `.alert` treatment.
- Wired `masthead.js` poller: reports ok on 200+304, ok:false on catch; subscribes broker to overlay disconnected variant on last-known-good state; aria-live enter/leave via existing rate-limiter.
- Built resume-card disconnected treatment (amber outline, disabled copy, stale warning, footer `DISCONNECTED — last poll …`); `resume-card-live.js` subscribes broker with P3 focus preservation.
- Extended `freshness-footer.js` disconnected timestamp copy.
- Fixtures: `connection-state.fixture.html`, resume-card disconnected section; tests in unit + integration + Playwright a11y.
- D2a deferred: KPI-dim, phase-tracker/backlog mute, activity-feed freeze — broker `subscribe` API exposed for page assembly / 5.22.
- Quality gate: `uv run pytest` 4355 passed, coverage 88.62%, all dashboard static gates green, freeze 7/7, no wire-format change.

### File List

- `src/sdlc/dashboard/static/components/connection-state/connection-state.js` (new)
- `src/sdlc/dashboard/static/components/connection-state/connection-state.fixture.html` (new)
- `src/sdlc/dashboard/static/components/masthead/masthead.js` (modified)
- `src/sdlc/dashboard/static/components/resume-card/resume-card.js` (modified)
- `src/sdlc/dashboard/static/components/resume-card/resume-card.css` (modified)
- `src/sdlc/dashboard/static/components/resume-card/resume-card.fixture.html` (modified)
- `src/sdlc/dashboard/static/components/resume-card/resume-card-live.js` (modified)
- `src/sdlc/dashboard/static/components/freshness-footer/freshness-footer.js` (modified)
- `pyproject.toml` (modified — force-include)
- `tests/unit/dashboard/test_connection_state.py` (new)
- `tests/unit/dashboard/test_masthead_disconnection.py` (new)
- `tests/unit/dashboard/test_resume_card_disconnected.py` (new)
- `tests/integration/test_dashboard_connection_state.py` (new)
- `tests/dashboard/test_connection_state_a11y.py` (new)

### Change Log

- 2026-07-07: Story 5.20 — honest disconnection detection + page-wide coordination (broker, masthead, resume card, banner). Decisions: D1(a), D2(a), D3(a), D4(a).

### Review Findings

> bmad-code-review (fresh-context, 3 adversarial layers Blind / Edge-Case / Acceptance-Auditor @ Opus-4.8, 2026-07-07). Every finding verified against source before triage. No CRITICAL, no HIGH survived verification (the Edge Hunter's "render-throw → false disconnect" HIGH and the Blind Hunter's "signature mismatch" HIGH were both refuted — see Dismissed). Original triage: 8 patch, 4 defer, 2 dismissed. **Resolution (user chose "apply every patch"): 6 patches applied + 1 partially applied; patch #5 reclassified → dismissed on deeper verification (see Dismissed); patch #6 remainder → deferred (test-infra). Full suite re-run green.**

**Patch (applied):**

- [x] [Review][Patch] APPLIED — Resume-card catch force-rebuilds the card on any transient poll failure/abort, dropping copy-button focus + clobbering in-progress copy→check feedback (defeats the P3 signature guard it sits next to); `renderCurrent(true)` → `renderCurrent()` so an unchanged connected render stays a footer-only refresh while a real broker variant change still rebuilds [src/sdlc/dashboard/static/components/resume-card/resume-card-live.js:165]
- [x] [Review][Patch] APPLIED — Broker `notify()` (and `subscribe`'s initial delivery) now isolate each subscriber in try/catch — one throwing surface no longer aborts the others nor propagates through `reportPollResult` into the masthead tick catch to bounce a just-recovered state [src/sdlc/dashboard/static/components/connection-state/connection-state.js:16-25,40-49]
- [x] [Review][Patch] APPLIED — Masthead `tick` now has a `disposed` guard (entry + after the awaited poll + in the catch), and `dispose()` sets it — an in-flight poll resolving post-dispose no longer mutates the module-singleton broker or renders into a detached root (mirrors resume-card-live.js) [src/sdlc/dashboard/static/components/masthead/masthead.js:187-215]
- [x] [Review][Patch] APPLIED — Vacuous 304-is-success test rewritten to witness ORDERING inside the real tick body (`_tick_body` arrow-aware slice; asserts `reportPollResult({ok:true})` index < `json == null` index); dead `_fn_body`/import-matching branch removed. Load-bearing D3 "304 = success before early return" now genuinely guarded [tests/unit/dashboard/test_connection_state.py:72-92]
- [x] [Review][Patch] APPLIED (partial — deterministic half) — added `test_aria_live_suppresses_within_rate_limit_window` (within-60s suppress-without-advancing witness, injected clock) + `test_disconnection_banner_removed_on_recovery` (DD-06 content-delta). Remainder (full broker→live-region end-to-end with injectable fixture clock; resume-card added to the connection fixture; driving production `startMastheadPoller` vs the `__connectionFixture` simulate API) → **deferred to test-infra debt** (see deferred-work.md — the fixture's real-clock rate-limiter can't be driven deterministically without clock-injection infra; auto-applying risked flaky tests) [tests/integration/test_dashboard_connection_state.py:130-150; tests/dashboard/test_connection_state_a11y.py:54-71]
- [x] [Review][Patch] APPLIED — Tautological broker-export test now asserts the `export { ... }` block itself lists `reportPollResult`/`subscribe`/`getState` (via `_export_block`), not the bare identifier anywhere [tests/unit/dashboard/test_connection_state.py:51-58]
- [x] [Review][Patch] APPLIED — Removed dead `cursor: not-allowed` (never renders under `pointer-events: none`); comment explains why [src/sdlc/dashboard/static/components/resume-card/resume-card.css:33-37]

**Deferred (real, out of current scope):**

- [x] [Review][Defer] Resume card stuck on "Loading…" if the broker disconnects before the first successful `/api/resume` poll (`renderCurrent` early-returns while `lastRenderedData` is null) — masthead+banner show DISCONNECTED but the card never flips; underspecified by UX §6.4 (assumes a last-known command). Deferred to page-assembly / 5.22 [src/sdlc/dashboard/static/components/resume-card/resume-card-live.js:102-121]
- [x] [Review][Defer] Masthead render sits inside the poll try — a render exception folds incoherently into the failure counter and re-throws uncaught. NOT a false disconnect (the `reportPollResult({ok:true})` at :190 resets the counter first each tick, so it can never reach 3 — refutes the Edge Hunter HIGH). Low-probability; recommend separating render from the network try/catch [src/sdlc/dashboard/static/components/masthead/masthead.js:194-200]
- [x] [Review][Defer] Malformed-JSON 200 counts as a poll failure (`response.json()` throw → `ok:false`); outside §7.11's stated threshold (network/5xx/timeout). First-party endpoint, "cannot reach valid state" is arguably honest, low risk [src/sdlc/dashboard/static/components/masthead/masthead.js:88-89,196-197]
- [x] [Review][Defer] Broker singleton assumes a single canonical reporter — module-level `consecutiveFailures` is correct only while the masthead is the sole reporter; a second `poll="true"` masthead would interleave and corrupt the count. Not reachable today (one reporter by design); document the invariant [src/sdlc/dashboard/static/components/connection-state/connection-state.js:12-13]

**Dismissed (verified false / negligible):**

- [Dismiss] Blind Hunter HIGH "signature mismatch between the poll path and `renderCurrent`" — FALSE POSITIVE: `mapResumeToken` sets `variant:"default"` (resume-card-live.js:55), so the connected signature is `[bc,cmd,"default"]` on both paths; they match, no spurious rebuild after recovery. Acceptance Auditor's rebuttal confirmed.
- [Dismiss] Masthead double-render on the disconnect-transition tick — real but negligible: fires once per disconnect event (not per tick), the render is idempotent, and the rate-limiter dedups the announcement (`normalized === lastVariant`).
- [Dismiss] (was Patch #5) Contradictory `disabled` + `aria-disabled` on the disconnected copy button [resume-card.js:237-241] — RECLASSIFIED on deeper verification: (1) the a11y tests deliberately lock in BOTH attributes (`test_connection_state_a11y.py::test_resume_card_disconnected_fixture...` asserts `aria-disabled=="true"` AND `button.is_disabled()`); (2) native `disabled` is a11y-acceptable — a disabled `<button>` is still in the accessibility tree and announced in reading/browse mode (WCAG 4.1.2 exempts disabled controls from focus), and the disconnected state is independently conveyed by the visible "may be stale" text + red `DISCONNECTED` footer (not color-only); (3) native `disabled` is load-bearing — it is what blocks copying a stale command (the click handler has no disconnected guard), so removing it to gain tab-focus would need a new JS guard and would break green tests. Redundant-but-harmless; not a defect worth a behavior/test change.
