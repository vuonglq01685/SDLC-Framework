# Epic 5 — Story DAG & Parallelism Plan

**Epic:** 5 — Local Dashboard & DORA Visibility (`sdlc dashboard --port`)
**Status:** Draft — rev 2 (authored 2026-06-22 per CONTRIBUTING.md §7 + Epic 4 retro Epic-5 prep A3; revised 2026-06-22 post 3-agent review)
**Authors:** Charlie + Alice (drafted via Claude) — review by Winston
**Source-of-truth:** `_bmad-output/planning-artifacts/epics.md` § "Epic 5: Local Dashboard & DORA Visibility" (lines 2359–2911)
**Retrospective rationale:** `_bmad-output/implementation-artifacts/epic-4-retro-2026-06-22.md` §6 (Epic 5 preview) + §7 (action plan A1–A4 / D1–D4) + §8 (significant discovery)

---

## 1. Purpose

Per CONTRIBUTING.md §7.3 (Mandatory DAG-First Rule) and §7.1 row 1 (mandatory artifact: Story DAG
document), every epic begins with a story-DAG identifying parallelism layers, the critical path, and
worktree assignments before Story `5.1` enters implementation. This document is the canonical
sprint-planning output for Epic 5.

**Epic shape (key insight).** Epic 5 is **data-readiness-gated**, not purely dependency-gated. Its 22
stories split into three waves by *when their data source exists*: **5A** (5.1–5.12) builds every
component against synthetic fixtures and is gated on Epic 1 only; **5B** (5.13–5.18) swaps in real
engine data and is gated on Epic 2A + 2B; **5C** (5.19–5.22) renders real auto-mode / Epic-4 STOP
state + disconnection. Within 5A the graph fans out hard (peak width 4, cap-saturating) from two
zero-indegree roots (`5.1` server, `5.2` tokens), converges on the a11y/forbidden-patterns gate
`5.12`, then each 5B story is a thin 1:1 real-data swap onto its 5A twin. The schedule risk lives in
two places: the **wave boundaries** (5B cannot start until upstream epics actually emit the expected
shapes) and the **terminal release gate `5.22`** (axe-core + manual screen-reader on the full
real-data surface).

**Substrate is the story (not Epic 4).** Epic 5's true Epic-4 coupling is narrow: only **`5.19`
(STOP banner)** reads the 7 trigger types from Epic-4 STOP-trigger state, and **`5.20`
(honest-disconnection)** pairs with the auto-loop liveness model. Most data dependencies trace
elsewhere — `agent_runs.jsonl` ← Epic 2B (2B.10), signoff 4-state ← Epic 2A (2A.7), Epic→Story→Task
hierarchy ← 2A.11, `ResumeToken` + `sdlc status` ← Epic 1 (1.7 / 1.17), id regex ← 1.6. Crucially,
`5.19` does **not** require real auto-loop dispatch (the `EPIC-4-DEBT-AUTO-REAL-DISPATCH` mock-only
posture rides to its own future epic per the Epic 4 retro D-RETRO-2); it requires STOP state to be
correctly persisted and **sticky** — i.e. it is gated on the Epic-4 retro **D4 / CR4.2-W3
sticky-halt fix** (mandatory before Epic 5), not on real dispatch.

**Epic 5 introduces an entirely new technology layer** absent from Epic 1–4: a localhost-bound HTTP
server (`sdlc dashboard`, Python micro-router, no framework), a vanilla HTML/CSS/JS frontend
(self-hosted fonts, SVG sprite, CSS design tokens, content-delta polling), a DORA computation engine,
and an accessibility toolchain. The existing Python-substrate gate (ruff / mypy --strict / pytest /
wire-format snapshots) covers the **server**; the **frontend** needs net-new CI gates (stylelint,
axe-core, forbidden-patterns, no-UI-framework, no-Google-Fonts, perf benchmarks) stood up by the
foundation stories. See Decision D2.

**Gate status note (updated 2026-06-22).** The §7.4 Pre-Story-5.1 gate is **NOT yet satisfied** — this
is an honest pre-gate posture, not green-washed. Open items:

- #1 this DAG exists — ✅ (this document, **Draft**).
- #2 §8 four approvals — ⏳ **OPEN (3/4)**. Decisions **D1 / D2 / D3 RATIFIED = (a)** by the
  Project Lead (2026-06-22). A genuine 3-agent adversarial review was run (2026-06-22): **Charlie
  (correctness) FAIL** — 2 CRITICAL graph defects + missing `E2A→5.18` — **all fixed in rev 2 (§9),
  then independently re-verified PASS**. **Alice (capacity) + Winston (architecture)
  PASS-WITH-FINDINGS** — fixable items applied; residual HIGH items tracked below. **All 3 reviewer
  boxes now signed; the only open box is the Project Lead directive sign-off.** (Even at 4/4, §8 is
  necessary-not-sufficient — the §7.4 gate stays open on the items below.)
- Previous-epic (Epic 4) retro "Before Story 5.1" closure — ⏳ **OPEN** (the gating dependency for
  this whole epic; tracked in the Epic 4 retro action plan):
  - **A1** (CI gate-signal: `setup-uv` SHA-pin + "CI-never-started ≠ green" guard) — ✅ **CLOSED** (`ci-gate` aggregating job, commit `8a7417b`; CI run `27959791325` green with **`ci-gate`=success**; `setup-uv` already SHA-pinned). Residual ops: branch protection still requires the 10 individual checks — swap to require only `ci-gate` (GitHub-admin step).
  - **A2** (cp1252 `encoding="utf-8"` on the merged-before-done / fresh-context-review guards + install commit-msg hooks) — ✅ **CLOSED** (commit `69add71`; commit-msg hook installed after unsetting the blocking local `core.hooksPath`; validated live — em-dash subjects now pass both gates instead of false-passing).
  - **A4** (CR4.2-W1: split/waive the 5 adopt-mutation files >400 LOC → green `main`) — ⏳ OPEN.
  - **D1** CR4.12-W1 symlink/path-containment — ⏳ OPEN (its containment helper is **reused by 5.1's static-serve path-traversal control** — see §7 security row). **D2** CR4.7-W1 secret_exfil regex/ReDoS — ⏳ OPEN. **D3** CR4.8-W2 cross-trigger precedence — ⏳ OPEN. **D4** CR4.2-W3 sticky-halt (load-bearing for `5.19`) — ⏳ OPEN. **Architectural note (review):** retro-D4 is **not** a one-line fix — `state/projection.py::_fold_auto_loop_status` is last-write-wins (an `action="stopped"` iteration folds back to `idle`, silently overwriting a prior `halted`) and `State` carries no sticky-halt field; the fix is a State-projection change that needs its own review.
  - DOC: ADRs from retro-D1 (atomic-write containment) + retro-D4 (sticky-halt projection) must reach `Accepted` — ⏳ OPEN. **The retro-D4 sticky-halt ADR is not yet drafted** (highest ADR in `docs/decisions/` is 034); the `E4 → 5.19` edge silently assumes it. The 2A.3 `EPIC-4-STOP-TRIGGER-WIRE` **journal** seam itself **IS resolved** (consumed by the 4.6 projection); only the sticky-halt half is open — mark the `deferred-work.md` EPIC-4-STOP-TRIGGER-WIRE entry as journal-resolved to clear stale "never consumed" text.
- #6 wire-format snapshots green on `main` — ✅ (freeze 7/7; re-verify at gate time).
- #7 quality gate green on `main` — ⏳ blocked by A4 (`pre-commit --all-files` red on the pre-existing Epic-3 adopt-LOC cap); full pytest / coverage ≥87 otherwise green per the 4.12 close-out CI run.
- #8 debt-decay strict run green for `--target-epic 5` (lineage N-1=4, N-2=3) — ⏳ to run after the Epic-4 defers are inventoried/dispositioned in `debt-budget.yaml`.

**This DAG unblocks §7.1 row 1 only.** Story 5.1 remains blocked until §8 reaches 4/4, the Epic-4
retro A/D/DOC items above close, and #7/#8 verify green.

---

## 2. Story DAG (Mermaid)

```mermaid
graph TD
  %% ---- Wave 5A roots (synthetic data; gated on Epic 1) ----
  S1["5.1 — Dashboard server skeleton<br/>micro-router · localhost-bind · read-only · 405-on-write · ETag/304"]:::layer1
  S2["5.2 — Design token foundation<br/>color/type/spacing/motion · stylelint gate"]:::layer1

  %% ---- Wave 5A components ----
  S3["5.3 — Self-host fonts + 12-icon sprite"]:::layer2
  S4["5.4 — Focus ring + reduced-motion + no-framework guard"]:::layer2
  S5["5.5 — Live-dot family + freshness footer (cross-cutting)"]:::layer2
  S6["5.6 — Masthead + tab-title automation"]:::layer2
  S7["5.7 — KPI strip + KPI value cell"]:::layer2
  S8["5.8 — Resume card + copy button"]:::layer2
  S9["5.9 — Phase tracker + signoff 4-state cell"]:::layer2
  S10["5.10 — Backlog tree + pill family"]:::layer2
  S11["5.11 — Tabs + activity feed + empty state"]:::layer2

  %% ---- Wave 5A convergence gate ----
  S12["5.12 — Forbidden-patterns + WCAG 2.2 A baseline + axe harness"]:::layer3

  %% ---- Wave 5B real-data swaps (gated on Epic 2A + 2B) ----
  S13["5.13 — DORA backend + 30s cache + /api/dora"]:::layer3
  S14["5.14 — Phase tracker: real signoff 4-state"]:::layer3
  S15["5.15 — Backlog tree: real hierarchy"]:::layer3
  S16["5.16 — Activity feed: real agent_runs.jsonl"]:::layer3
  S17["5.17 — KPI strip: real DORA 7d/30d"]:::layer3
  S18["5.18 — Resume card: real you-are-here + next"]:::layer3

  %% ---- Wave 5C real auto-mode / Epic-4 state ----
  S19["5.19 — STOP banner (all 7 trigger types)"]:::layer4
  S20["5.20 — Honest-disconnection state"]:::layer4
  S21["5.21 — Below-1280px degradation banner"]:::layer4
  S22["5.22 — Per-release a11y gate (axe + screen-reader + keyboard)"]:::layer5

  %% ---- External wave gates ----
  E1["Epic 1 substrate<br/>(synthetic host)"]:::ext
  E2A["Epic 2A — 2A.7 / 2A.11 / 2A.19<br/>+ Epic 1 1.6 / 1.7 / 1.17"]:::ext
  E2B["Epic 2B — 2B.10 agent_runs.jsonl"]:::ext
  E4["Epic 4 STOP state<br/>+ retro D4 / CR4.2-W3 sticky-halt"]:::ext

  %% ---- 5A token/foundation edges ----
  S2 --> S3
  S2 --> S4
  S2 --> S5
  S2 --> S7
  S2 --> S8
  S2 --> S9
  S2 --> S10
  S3 --> S8
  S3 --> S9
  S4 --> S5
  S4 --> S10
  S4 --> S12

  %% ---- 5.5 live-dot is the high-fanout cross-cutting node ----
  S5 --> S6
  S5 --> S7
  S5 --> S8
  S5 --> S11
  S5 --> S12
  S5 --> S19
  S5 --> S20

  %% ---- 5B real-data swaps onto their 5A twins ----
  S1 --> S13
  S7 --> S13
  S7 --> S17
  S13 --> S17
  S9 --> S14
  S10 --> S15
  S11 --> S16
  S8 --> S18

  %% ---- 5.12 5A convergence gate: fans-in from EVERY 5A component ----
  S6 --> S12
  S7 --> S12
  S8 --> S12
  S9 --> S12
  S10 --> S12
  S11 --> S12

  %% ---- 5C banners / disconnection / release gate ----
  S11 --> S19
  S6 --> S20
  S8 --> S20
  S19 --> S20
  S19 --> S21
  S12 --> S22
  S18 --> S22
  S19 --> S22
  S20 --> S22
  S21 --> S22

  %% ---- External wave gates (data readiness) ----
  E1 --> S1
  E1 --> S2
  E2A --> S14
  E2A --> S15
  E2A --> S18
  E2B --> S13
  E2B --> S16
  E4 --> S19

  %% NOTE: classDef names layer1..layer5 denote the 5 PHASE colors (5A-roots / 5A-components /
  %% 5A-gate+5B / 5C-banners / 5C-terminal), NOT the §3 topological layer numbers — e.g. 5.22 is
  %% :::layer5 but sits at topological L10, and 5.19 is :::layer4 but sits at L8. Read §3 for layers.
  classDef layer1 fill:#d6eaff,stroke:#1f6feb,color:#000
  classDef layer2 fill:#cdf2d4,stroke:#1a7f37,color:#000
  classDef layer3 fill:#f5d0e6,stroke:#9333ea,color:#000
  classDef layer4 fill:#fae3b6,stroke:#a16207,color:#000
  classDef layer5 fill:#ffd8d8,stroke:#b91c1c,color:#000
  classDef ext fill:#eee,stroke:#999,color:#000,stroke-dasharray:4 3
```

**Note on edges.** Colors group the four *phases* (roots → 5A components → 5A-gate + 5B real-data →
5C), while the **Parallelism Layers** table (§3) schedules the precise topological layers. The
dashed `ext` nodes are **data-readiness wave gates**, not stories: 5A needs only Epic 1; **5B cannot
start until Epic 2A (2A.7/2A.11/2A.19) and Epic 2B (2B.10) actually emit the expected shapes into
`state.json` / `agent_runs.jsonl`** — verify those contracts before branching 5B. `E2A → S18` is
included because 5.18 reads the real `ResumeToken` (Epic 1 1.7) + `sdlc status` logic (1.17), bundled
under the E2A gate label. The `E4 → S19` edge is the load-bearing Epic-4 coupling: it depends on STOP
state being **sticky** (retro D4 / CR4.2-W3), *not* on real-loop dispatch (which rides per retro
D-RETRO-2). **`5.12` now draws its full 5A fan-in** (5.4–5.11 → 5.12) since the convergence gate's
axe-core/forbidden-patterns scan must see every rendered 5A component. **`5.22` now draws its full 5C
fan-in** (5.12 + 5.18 + 5.19 + 5.20 + 5.21) — the terminal release-blocking node also covers
disconnection (5.20) and the degradation banner (5.21); conceptually it additionally re-scans the full
5.14–5.19 real-data surface (those swaps land their a11y coverage via their 5A twins through 5.12).

---

## 3. Parallelism Layers

| Layer | Stories | Max parallel worktrees | Depends on |
|---|---|---|---|
| **L1 (5A)** | 5.1, 5.2 | **2** | Epic 1 substrate (synthetic data) |
| **L2 (5A)** | 5.3, 5.4 | **2** | 5.2 |
| **L3 (5A)** | 5.5, 5.9, 5.10 | **3** | 5.2, 5.3, 5.4 |
| **L4 (5A)** | 5.6, 5.7, 5.8, 5.11 | **4 (cap-saturating)** | 5.5 (+ 5.2 / 5.3) |
| **L5 (5A)** | 5.12 | **1** | all of 5A (a11y / forbidden-patterns convergence gate) |
| **L6 (5B)** | 5.13, 5.14, 5.15, 5.16, 5.18 | **4 (cap-bound; 5 stories → 2 batches)** | Epic 2A (2A.7/2A.11/2A.19) + Epic 2B (2B.10) + Epic 1 (1.6/1.7/1.17); each ← its 5A twin |
| **L7 (5B)** | 5.17 | **1** | 5.7, 5.13 |
| **L8 (5C)** | 5.19 | **1** | Epic 4 STOP state + **retro D4 / CR4.2-W3 sticky-halt** + 5.5, 5.11 |
| **L9 (5C)** | 5.20, 5.21 | **2** | 5.19 (+ 5.6 / 5.8 for 5.20) |
| **L10 (5C)** | 5.22 | **1** | 5.12 + 5.18 + the full 5.14–5.19 real-data surface (terminal release gate) |

**Project-cap reminder:** `max_parallel_agents=4` — the value is defined in **CONTRIBUTING.md §3.2 +
PRD FR51 (default 4)**; no `project.yaml` exists in-repo (a prior draft cited one in error). The cap is
prose-enforced, not config-enforced — if CI is to programmatically gate concurrency, land a
`project.yaml` carrying `max_parallel_agents: 4` as a foundation task. **L4 saturates the cap** (4
stories, zero slack) and **L6 exceeds it** (5 stories → must batch). **Authoritative L6 split:** batch 1
= {5.14, 5.15, 5.16, 5.18} (the four independent 1:1 real-data swaps), batch 2 = {5.13} alone (the DORA
engine — heaviest, security/perf-sensitive, and the upstream of 5.17 at L7, so it must merge cleanly);
per CONTRIBUTING §3.3 batch 2 **rebases on batch 1's merges**. The binding wall-clock constraints are
the **two wave boundaries** (5A→5B waits on real upstream data; 5B→5C waits on Epic-4 sticky STOP
state) and the **terminal `5.22`** release gate.

**Dependency notes:**

- **5.1 and 5.2 are the two true zero-indegree roots** and are mutually independent — start both
  immediately. `5.2` roots the entire CSS/component tree; `5.1` roots the server + `/api/dora` (5.13).
- **5.5 (live-dot) is the single most load-bearing component node** — a convergence of the foundations
  (5.2 + 5.4) that then fans out to 5.6, 5.7, 5.8, 5.11, 5.12, 5.19, 5.20 and owns the
  color-only-signaling contract enforced project-wide by 5.12.
- **5.12 is the 5A convergence gate** — it scans the whole synthetic SPA for WCAG 2.2 Level A + forbidden
  patterns; it cannot run until every 5A component lands.
- **5B is a 1:1 real-data swap layer** — 5.13↔(5.1+5.7), 5.14↔5.9, 5.15↔5.10, 5.16↔5.11, 5.17↔(5.7+5.13),
  5.18↔5.8. These are mutually independent leaves once their upstream data sources are confirmed.
- **5.22 is the terminal release gate** — depends on 5.12 + 5.18 + the full real-data surface; any a11y
  regression blocks release. 5.20 / 5.21 should land before it so the gate covers disconnection + the
  degradation banner.

---

## 4. Critical Path

The longest dependency chain through the DAG:

```
5.2 → 5.4 → 5.5 → 5.11 → 5.19 → 5.20 → 5.22     (depth-7 component → STOP → disconnection → release spine)
                                                (terminal gate 5.22 also fans-in from 5.12 + 5.18 + 5.21 + the 5.14–5.19 real-data surface)
```

**Length:** 6 stories to `5.20`; 7 to the terminal release gate `5.22`. A **co-critical** depth-7 path
runs through `5.21` (`5.2 → 5.4 → 5.5 → 5.11 → 5.19 → 5.21 → 5.22`), so `5.21` sits on the critical
boundary, not a freely-parallelizable leaf. Unlike Epic 4's single serial
spine, Epic 5's critical path is **gated by data-readiness wave boundaries** more than by raw
dependency depth — the wall-clock bottleneck is waiting for Epic 2A/2B to emit real shapes (5B) and for
the Epic-4 sticky-halt fix (5C), not the within-wave chain. Protect the schedule by (1) front-loading
5A entirely against synthetic fixtures while upstream data matures, (2) verifying the upstream
contracts (2A.7 / 2A.11 / 2A.19 / 2B.10 shapes) **before** branching 5B, and (3) landing retro-D4
(CR4.2-W3 sticky-halt) before 5C. The two highest-risk stories are **`5.1`** (the security keystone —
a net-new localhost-bound, no-auth, no-write HTTP server; `0.0.0.0` blocked with `SecurityError`,
`405` on writes, the entire trusted-local-user threat model — SECURITY-SENSITIVE) and **`5.13`** (the
net-new DORA computation engine under a hard `<30s` perf gate on a 200-story / 1000-task / 90-day
fixture — the only real algorithmic risk). Honorable mention: the **a11y hard gates `5.12` / `5.22`**
(zero WCAG 2.2 Level A violations, release-blocking).

---

## 5. Worktree Assignments (preliminary)

| Worktree branch | Story | Owner | Layer | Notes |
|---|---|---|---|---|
| `epic-5/5-1-dashboard-server-skeleton` | 5.1 | Amelia | 1 | Net-new `sdlc dashboard` micro-router (Python, no framework); localhost-bind + 405-on-write + ETag/304; `pytest-benchmark` `<100ms` (wire the benchmark at L1 — do not defer to 5.13). **Security-sensitive — review-B + security-reviewer.** **5.1 AC MUST add (review finding, see §7 security row): (a) `Host`-header allowlist (`localhost`/`127.0.0.1`/`[::1]`) → `403` to defeat DNS-rebinding — 405-on-write does not cover read exfiltration; (b) canonicalized static-path containment under the static root (reject `..`/abs/symlink-escape), reusing the retro-D1 containment helper once it lands; (c) ETag = hash over content, not mtime/inode.** **Freeze the server/route contract before 5.13.** |
| `epic-5/5-2-design-token-foundation` | 5.2 | Sally | 1 | `tokens.css` color/type/spacing/motion; **stands up stylelint gate + DD-09 no-`data-theme` guard.** Root of the CSS tree — **freeze token names before L2.** |
| `epic-5/5-3-self-host-fonts-sprite` | 5.3 | Sally | 2 | `@font-face` + 12-icon SVG sprite; **no-Google-Fonts CI grep gate**; ADR if sprite >12 icons. |
| `epic-5/5-4-focus-ring-reduced-motion` | 5.4 | Sally | 2 | Focus ring (WCAG A contrast) + `prefers-reduced-motion`; **no-third-party-UI-framework guard + transition grep gate.** |
| `epic-5/5-5-live-dot-freshness-footer` | 5.5 | Sally | 3 | Cross-cutting `<live-dot>` family + freshness footer; **owns the color-only-signaling contract.** Highest-fanout component. |
| `epic-5/5-6-masthead-tab-title` | 5.6 | Sally | 4 | Masthead + tab-title sync (3s poll, Decision E2); owns 60s `aria-live` rate-limit reused by 5.20. |
| `epic-5/5-7-kpi-strip-value-cell` | 5.7 | Sally | 4 | KPI strip + value cell incl. no-data `n/a` state (consumed by 5.13/5.17). |
| `epic-5/5-8-resume-card-copy-button` | 5.8 | Sally | 4 | Resume card + clipboard copy (icon-swap from 5.3 sprite). |
| `epic-5/5-9-phase-tracker-signoff-cell` | 5.9 | Sally | 3 | Phase tracker + signoff 4-state cell (synthetic; 4-state vocabulary mirrors 2A.7); committed `signoff-states.html` fixture. |
| `epic-5/5-10-backlog-tree-pills` | 5.10 | Sally | 3 | Backlog tree (collapsible, keyboard-reachable) + pill registry. |
| `epic-5/5-11-tabs-activity-feed-empty` | 5.11 | Sally | 4 | Tabs (full ARIA pattern) + activity feed + empty state (consumed by 5.16 / 5.19). |
| `epic-5/5-12-forbidden-patterns-wcag-baseline` | 5.12 | Murat | 5 | **5A a11y convergence gate.** Net-new `tests/dashboard/` — forbidden-patterns + axe-core harness + keyboard-only test + color-only static analysis. **HARD GATE.** |
| `epic-5/5-13-dora-backend-cache` | 5.13 | Amelia | 6 | Net-new DORA engine; `/api/dora` real compute + 30s cache; `docs/api/dora-schema.json`; **`<30s` perf benchmark CI gate.** **2nd-highest-risk story — add review-B (edge-case/perf/malformed-input) + a security-reviewer touch since `/api/dora` rides the 5.1 HTTP boundary.** Must read `agent_runs.jsonl`/git-log **through the existing journal/state reader seam, not by re-parsing** (one-way module edge: `dashboard` → `state`/`journal`, never the reverse). See Decision D1; copy D1's "revisit if an external `/api/dora` consumer appears → promote to 8th ADR-024 contract" clause into the 5.13 AC. |
| `epic-5/5-14-phase-tracker-real-signoff` | 5.14 | Sally | 6 | Real 4-state from `state.json` (2A.7 + 2A.19 invalidate-by-replan). |
| `epic-5/5-15-backlog-tree-real-hierarchy` | 5.15 | Sally | 6 | Real Epic→Story→Task (2A.11) + id regex (1.6); URL-hash persistence. |
| `epic-5/5-16-activity-feed-real-runs` | 5.16 | Sally | 6 | Real `agent_runs.jsonl` (2B.10); only changed sections re-render (NFR-PERF-4). **Reads untrusted file content — add a data-validation review focus (malformed/partial JSONL lines must not crash or XSS the feed).** |
| `epic-5/5-17-kpi-strip-real-dora` | 5.17 | Sally | 7 | Real `/api/dora` (5.13) + deltas; insufficient-data → `n/a` per 5.7. |
| `epic-5/5-18-resume-card-real-you-are-here` | 5.18 | Sally | 6 | Real `ResumeToken` (1.7) + suggested-next (`sdlc status` logic, 1.17); gated by `E2A → 5.18` (verify the 1.7/1.17 shapes before branching). **Reads untrusted state content — add a data-validation review focus.** The full-real-data baseline 5.22 builds on. |
| `epic-5/5-19-stop-banner-7-triggers` | 5.19 | Amelia | 8 | Renders all 7 Epic-4 trigger types from STOP state; trigger→severity mapping test. **Load-bearing on retro D4 / CR4.2-W3 sticky-halt.** See Decision D3. |
| `epic-5/5-20-honest-disconnection` | 5.20 | Sally | 9 | Recovery slice — N-consecutive-poll-fail → disconnected state on masthead/resume/banner; `aria-live` enter+leave. |
| `epic-5/5-21-below-1280-degradation-banner` | 5.21 | Sally | 9 | Viewport degradation banner (reuses 5.19 treatment, `--blue` info); sessionStorage dismiss. |
| `epic-5/5-22-per-release-a11y-minimum` | 5.22 | Murat | 10 | **Terminal release gate.** Per-release axe-core (real-data) + NVDA/VoiceOver manual smoke → `docs/a11y/release-<version>.md`; a11y regression blocks release. |

Owners are tentative — the Sprint Planning meeting locks the roster. **Owner-load caveat (review
finding):** the placeholder column funds Sally with ~16 of 22 stories, including all four
cap-saturating L4 worktrees (5.6/5.7/5.8/5.11) — one author cannot realize 4-way concurrency, so the
§3/§6 "peak width 4" is only achievable if the locked roster spreads L4 and the L6 batch across **≥3
authors** (cf. CONTRIBUTING §4.3's two-simultaneous-assignment ceiling). Treat the concurrency profile
as a staffing requirement, not a given. The net-new interfaces frozen by `5.1` (server/route contract)
and `5.2` (design-token names) are consumed by the rest of the epic; agree both in their review before
L2/L6 branch. **Module-boundary rule (add to `check_module_boundaries.py` in 5.1):** the new
`dashboard` package may depend on the `state`/`journal` reader seam, but those modules MUST NOT depend
on `dashboard` (one-way edge); `/api/dora` and any derived view read through the reader, never by
re-parsing wire files. Frontend file naming under `dashboard/static/` (components, pills, fixtures)
MUST follow a single committed layout convention established in 5.2/5.5.

---

## 6. Sequencing & Parallelism Profile

*(Absolute durations are intentionally omitted — AI-paced development makes calendar estimates
unreliable; see the retrospective facilitation convention. Effort is expressed as structure.)*

| Layer | Concurrency | Stories | Character |
|---|---|---|---|
| 1 | 2 | 5.1, 5.2 | Two independent roots: server/security keystone + design-token tree |
| 2 | 2 | 5.3, 5.4 | Token consumers + frontend CI-gate stand-up |
| 3 | 3 | 5.5, 5.9, 5.10 | Cross-cutting live-dot + standalone components |
| 4 | 4 (cap-saturating) | 5.6, 5.7, 5.8, 5.11 | 5A component fan-out (peak width) |
| 5 | 1 | 5.12 | 5A a11y / forbidden-patterns convergence gate |
| 6 | 4 then 1 (2 batches; see §3 split) | 5.13, 5.14, 5.15, 5.16, 5.18 | 5B real-data swaps (gated on Epic 2A/2B); batch 1 {5.14,5.15,5.16,5.18}, batch 2 {5.13} rebased on batch 1 |
| 7 | 1 | 5.17 | Real KPI strip (component + DORA API join) |
| 8 | 1 | 5.19 | STOP banner (gated on Epic-4 sticky STOP state) |
| 9 | 2 | 5.20, 5.21 | Disconnection recovery + viewport banner |
| 10 | 1 | 5.22 | Terminal per-release a11y gate |

**Profile:** depth-7 critical path to the release gate, **peak width 4** (L4 cap-saturating; L6
cap-exceeding → batch). The binding constraint is **data-readiness at the two wave boundaries**, not
within-wave dependency depth — 5A is fully front-loadable against synthetic fixtures. Acceleration
levers: (1) run all of 5A in parallel batches while upstream Epic 2A/2B data matures; (2) the six 5B
stories are independent 1:1 real-data swaps — batch them as soon as their upstream contracts are
verified; (3) land retro-D4 (sticky-halt) early so 5C is unblocked the moment 5B completes. Contrast
with Epic 4's single deep serial spine: Epic 5 is **wider and more wave-gated** — its risk is upstream
data availability + the new frontend toolchain, not loop-correctness.

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **New technology layer with no existing review/CI coverage.** Epic 1–4 patterns (mypy --strict, pytest, wire-format snapshots) do not cover JS/CSS/HTTP — first HTTP server + browser frontend + a11y toolchain in the project. | **Decision D2.** Server rides the existing Python gate; frontend gets net-new CI gates (stylelint 5.2, no-Google-Fonts 5.3, no-framework + transition 5.4, color-only 5.5, forbidden-patterns + axe-core + keyboard 5.12, perf benchmarks 5.1/5.13) stood up by the foundation/gate stories. Single CI surface, added incrementally. |
| **Cross-epic data coupling — 5B/5C stall if upstream shapes drift.** 5B reads real 2A.7 / 2A.11 / 2A.19 / 2B.10; 5C reads Epic-4 STOP state. If any upstream contract isn't emitting the expected shape, the synthetic→real swap stalls. | Verify the upstream contracts (signoff 4-state, hierarchy, `agent_runs.jsonl`, STOP-trigger state) **before branching each wave** (§3 dependency notes). 5A is fully decoupled (synthetic) so it proceeds regardless. Confirm the 2A.3 `EPIC-4-STOP-TRIGGER-WIRE` placeholder is resolved into real recorded STOP state. |
| **`5.19` STOP banner reads non-sticky halt (the Epic-4 retro CR4.2-W3).** `state.json` can read `idle` while a clarification stays open (last-write-wins fold) → the banner would flicker/lose the halt. | **Decision D3.** `5.19` is gated on the Epic-4 retro **D4 / CR4.2-W3 sticky-halt fix** (mandatory before Epic 5), NOT on real-loop dispatch (which rides per retro D-RETRO-2). The banner renders whatever STOP state exists (mock or real); the fix makes it persist. |
| **DORA compute correctness + `<30s` perf gate.** Four metrics over git log + `agent_runs.jsonl`, 7d/30d windows, with insufficient-data branching, under a CI-gated `<30s` benchmark on a large fixture. | Story 5.13 owns the benchmark + `docs/api/dora-schema.json`. **Decision D1** keeps the schema internal (no ADR-024 wire contract, freeze stays 7/7) unless an external consumer appears. 30s server-side cache bounds repeat cost. |
| **a11y hard gate vs editorial-design ambition.** Zero WCAG 2.2 Level A violations + forbidden-patterns (no modals/toasts/forms/client-routing/skeletons) + no color-only signaling, gated per-release with manual NVDA/VoiceOver. | 5.5 owns the color-only contract; 5.12 is the 5A convergence gate (axe-core + keyboard + forbidden-patterns); 5.22 is the per-release gate. Manual screen-reader smoke is a designated-reviewer signoff in `docs/a11y/release-<version>.md` — schedule the human reviewer as a release dependency. |
| **Vanilla-JS-at-scale maintainability.** 22 stories of interactive components (tabs, collapsible tree, clipboard, polling, aria-live, content-delta render) with zero UI framework, under the <800-line/file + review discipline. | Cross-cutting components (live-dot 5.5, pill registry 5.10, tabs 5.11) are built once and reused; the no-framework guard (5.4) keeps the constraint honest; component fixtures (`signoff-states.html` 5.9) enable visual review without a heavy test rig. |
| **§7.4 GATE — Epic 5 is NOT gate-ready (updated 2026-06-22).** Progress: D1/D2/D3 **RATIFIED = (a)**; retro **A1 ✅ + A2 ✅ CLOSED** (CI `ci-gate`=success; cp1252 fix live). Still open: §8 **3/4** (3 reviewer boxes signed post re-verify; only the Project Lead directive sign-off remains), the Epic-4 retro **A4 + D1–D4 + DOC** items, **5.1 security ACs** (Host-header + static path-traversal — see security row) not yet in `epics.md`, **retro-D4 sticky-halt ADR** not drafted, #7 quality gate blocked by A4, #8 debt-decay target-5 not yet run. #1 DAG exists ✅; #6 snapshots 7/7 ✅. | Before `bmad-create-story 5.1`: (1) Charlie re-verifies the revised DAG → §8 4/4; (2) close retro A4 + D1–D4 + DOC (with evidence) + land the retro-D1 & retro-D4 ADRs to `Accepted`; (3) add the 5.1 Host-header + path-traversal + ETag-over-content controls to the `epics.md` 5.1 AC; (4) re-verify #7 green on `main` + run #8 `--target-epic 5` strict. Do NOT proceed under "I'll backfill later" (CONTRIBUTING §7.4). |

---

## Decision D1 — `/api/dora` schema: internal vs frozen ADR-024 wire contract (prep)

**Question.** Is the `/api/dora` response (and `docs/api/dora-schema.json`, Story 5.13) a frozen
ADR-024 wire-format contract (StrictModel + snapshot ceremony, freeze → 8/8), or an internal/
documentary schema (freeze stays 7/7)?

**Affected shapes:** the `/api/dora` JSON envelope (deployment_frequency / lead_time /
change_failure_rate / MTTR over 7d/30d), `docs/api/dora-schema.json`, and whether
`src/sdlc/contracts/` gains a new StrictModel subject to the ADR-024 mutation ceremony.

**Recommendation (a) — internal/documentary schema (no ADR-024 contract).** The dashboard is
read-only and localhost-bound; `/api/dora` is consumed only by the bundled frontend, never by an
external integrator — exactly the boundary Epic-4 D1 used for internal state ("zero new ADR-024
contracts"). Keep freeze at **7/7**, document the shape in `docs/api/dora-schema.json` as a
non-frozen reference, no StrictModel. **Alternative (b):** freeze it as the 8th wire contract if a
real external consumer of `/api/dora` ever appears (CI tooling, external DORA aggregator). *Recommendation:
(a); revisit if an external `/api/dora` consumer materializes.*

**PROPOSED 2026-06-22 — option (a), pending §8 ratification.**

---

## Decision D2 — New frontend tech-stack gating & review model

**Question.** Where do the net-new JS/CSS/HTTP quality gates live, and what is the review model for a
layer the Python-substrate gates don't cover?

**Affected shapes:** CI workflow(s), the foundation stories that own each new gate, and the
adversarial-review roster for frontend + a11y stories.

**Recommendation (a) — single CI surface, gates added incrementally by the foundation stories.** The
`sdlc dashboard` server is Python (stdlib micro-router) → it rides the existing ruff / mypy --strict /
pytest gate. The frontend gets net-new gates stood up by the stories that introduce the concern:
stylelint + DD-09 (5.2), no-Google-Fonts (5.3), no-UI-framework + transition grep (5.4), color-only
static analysis (5.5), forbidden-patterns + axe-core + keyboard (5.12), `<100ms`/`<30s` perf
benchmarks (5.1/5.13) — all running in the same CI matrix. Review uses the existing 3-layer adversarial
model, with **security-reviewer on 5.1** (HTTP boundary) and an **a11y-focused review on 5.12/5.22**.
**Alternative (b):** a separate frontend CI workflow + separate review track. *Recommendation: (a) —
keep one gate surface; isolating the frontend invites drift between two CI systems.*

**PROPOSED 2026-06-22 — option (a), pending §8 ratification.**

---

## Decision D3 — 5C's Epic-4 dependency: sticky STOP state, not real dispatch

**Question.** 5C (esp. `5.19` STOP banner) depends on Epic-4 STOP-trigger state. Epic 4 ships
mock-only dispatch (`EPIC-4-DEBT-AUTO-REAL-DISPATCH` rides to its own epic). Does 5C wait for real
dispatch, or proceed on the STOP state that already exists?

**Affected shapes:** the gating precondition for L8–L10 (5.19–5.22) and the Epic-4 retro action
linkage.

**Recommendation (a) — 5C is gated on the retro D4 / CR4.2-W3 sticky-halt fix, independent of
real-dispatch.** `5.19` reads STOP state from the `state.json` projection; it renders whatever STOP
state exists (mock or real). The real requirement is that the state be **correctly persisted and
sticky across runs** — which is exactly the Epic-4 retro **D4 (CR4.2-W3 sticky-halt)** mandatory
prep item. Real auto-loop dispatch (`CR4.7-W6` etc.) rides to a dedicated real-dispatch epic per
retro **D-RETRO-2** and is NOT a 5C precondition. **Alternative (b):** defer 5.19 until real-dispatch
lands (couples the dashboard to an unscheduled epic). *Recommendation: (a) — render STOP state now;
gate only on the sticky-halt fix.*

**PROPOSED 2026-06-22 — option (a), pending §8 ratification.**

---

## 8. Approvals

Per CONTRIBUTING.md §7.1 rows 3–4 — minimum 3 reviewers + Project Lead directive sign-off.
**All 4 boxes must be checked, and Decisions D1/D2/D3 ratified, before any Story 5.1 file is created
via `bmad-create-story`.** A genuine 3-agent adversarial review was run **2026-06-22**; verdicts are
recorded against each box. **Current state: D1/D2/D3 RATIFIED = (a); §8 still < 4/4.**

- [x] Charlie — DAG correctness + dependency checks. **rev 1: FAIL** (2 CRITICAL graph defects —
  5.12 missing its 5.6–5.11 fan-in; 5.20/5.21 not feeding terminal gate 5.22 — + HIGH missing
  `E2A→5.18`) → **all fixed in rev 2** → **rev 2 re-verify (independent reviewer): PASS** — all six
  `5.6–5.11→5.12` edges, the `5.20/5.21→5.22` terminal edges, and `E2A→5.18` confirmed present; graph
  acyclic, every non-root node has an in-edge, layering topologically valid, depth-7 critical path real
  (5.21 co-critical). Two LOW/INFO nits (classDef-vs-layer naming, 5.21 co-path) also closed.
- [x] Alice — sprint capacity + reviewer assignment. **Verdict: PASS-WITH-FINDINGS** (no FAIL). Applied
  in rev 2: corrected the fabricated `project.yaml` cap citation → CONTRIBUTING §3.2/PRD FR51; named the
  authoritative L6 batch split {5.14,5.15,5.16,5.18}+{5.13}-rebased; added review-B/security to 5.13 and
  data-validation review to 5.16/5.18. **Residual (feeds Sprint Planning, not a DAG fix):** the locked
  roster MUST staff L4/L6 across ≥3 authors — the placeholder single-owner load can't realize width 4.
- [x] Winston — architectural cross-reference. **Verdict: PASS-WITH-FINDINGS** (no FAIL). Confirmed
  D1(a)/D2(a)/D3(a) consistent with ADR-024 (UI-render-model exclusion), ADR-025, and retro
  D-RETRO-2/D4; net-new `dashboard` layer respects module boundaries. Applied in rev 2: module
  one-way-edge rule, /api/dora-via-reader-seam, 5.1 `<100ms` benchmark-at-L1 note, D1 revisit clause →
  5.13 AC. **Residual HIGH (gate items, NOT DAG fixes):** (F4) retro-D4 sticky-halt needs a State
  projection change + an as-yet-undrafted ADR before `E4→5.19`; (F5) the **5.1 security AC must add
  Host-header allowlist + static path-traversal containment + ETag-over-content** — these belong in
  `epics.md`, Project-Lead/PO call.
- [ ] **Vuonglq01685 (Project Lead)** — **D1 = (a), D2 = (a), D3 = (a) RATIFIED (2026-06-22).**
  Charlie's re-verify is now PASS, so **all 3 reviewer boxes are signed — this directive sign-off
  (parallelism plan + worktree-per-layer policy) is the only box left to reach §8 4/4**, and is the
  Project Lead's to give. **NOTE — §7.4 gate is NOT satisfied even at 4/4:** Story 5.1 also requires
  the Epic-4 retro A4 + D1–D4 + DOC items closed, the 5.1 security ACs added to `epics.md`, the
  retro-D4 sticky-halt ADR drafted-to-Accepted, and #7/#8 re-verified green (see §1 + §7 gate row).

---

## 9. Revision Log

| Date | Author | Change |
|---|---|---|
| 2026-06-22 | Charlie + Alice (drafted via Claude, per Epic 4 retro A3) | Initial draft — DAG (22 stories) + 10 parallelism layers across 3 data-readiness waves (5A synthetic / 5B real-engine-data / 5C real-auto-mode) + critical path `5.2 → 5.4 → 5.5 → 5.11 → 5.19 → 5.20` (depth 6; depth 7 to terminal release gate `5.22`; peak width 4 — L4 cap-saturating, L6 cap-exceeding) + preliminary worktree assignments + risk register + Decisions D1 (`/api/dora` internal schema), D2 (single-CI-surface frontend gating), D3 (5C gated on retro-D4 sticky-halt not real-dispatch). §8: **all 4 approvals OPEN**; **Project Lead directive sign-off OPEN**; D1/D2/D3 **proposed, not ratified**. Gate note states the §7.4 Pre-Story-5.1 gate is **NOT yet satisfied** — pending §8 4/4 + the Epic-4 retro "Before Story 5.1" items (A1 gate-signal CI fix, A2 cp1252 encoding fix, A4 adopt-LOC green main, D1 symlink/path-containment, D2 secret_exfil regex, D3 cross-trigger precedence, D4 CR4.2-W3 sticky-halt) + two ADRs to `Accepted` + #7/#8 re-verification (honest posture per the belief→evidence lesson; not green-washed). |
| 2026-06-22 | Reviewers Charlie/Alice/Winston (3-agent adversarial review) + Project Lead (decisions) | **Rev 2 — review-driven revision.** Project Lead **ratified D1/D2/D3 = (a)**. 3-agent adversarial review run. **Charlie FAIL→fixed:** added 5.6–5.11 → 5.12 convergence-gate fan-in (6 edges), 5.20→5.22 + 5.21→5.22 terminal-gate edges (5.21 no longer orphan), `E2A→5.18` wave gate; corrected §4 critical path to true depth-7 spine `5.2→5.4→5.5→5.11→5.19→5.20→5.22`; added 5.12 to the §2 + §3 fan-in/fan-out prose. **Alice PASS-WITH-FINDINGS→applied:** fixed the non-existent `project.yaml` cap citation (→ CONTRIBUTING §3.2 / PRD FR51), named the authoritative L6 batch split {5.14,5.15,5.16,5.18}+{5.13}-rebased, added review-B/security to 5.13 + data-validation review to 5.16/5.18, recorded the owner-load staffing caveat (≥3 authors for width 4). **Winston PASS-WITH-FINDINGS→applied:** D1/D2/D3 confirmed vs ADR-024/025 + retro D-RETRO-2/D4; added module one-way-edge rule + /api/dora-via-reader-seam, 5.1 benchmark-at-L1 note, D1 revisit clause. **Residual gate items (NOT DAG fixes, tracked in §1/§7/§8):** retro-D4 sticky-halt = State-projection change + undrafted ADR; 5.1 security AC must add Host-header allowlist + static path-traversal containment + ETag-over-content in `epics.md`. Flipped retro **A1/A2 → ✅ CLOSED** (CI `ci-gate`=success; cp1252 fix live). §8 reviewer boxes: Alice + Winston signed (PASS-WITH-FINDINGS); **Charlie re-verified independently → PASS**, so **all 3 reviewer boxes signed** — only the Project Lead directive sign-off remains → §8 **3/4**. Also closed 2 LOW/INFO re-verify nits (Mermaid classDef-vs-layer legend comment; 5.21 co-critical-path note in §4). |
