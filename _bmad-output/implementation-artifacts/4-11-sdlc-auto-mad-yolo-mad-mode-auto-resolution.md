# Story 4.11: `/sdlc-auto-mad` (YOLO Mad-Mode Auto-Resolution)

**Status:** review

**Epic:** 4 — Auto-Mode & Autonomous Execution (`/sdlc-auto`)
**Layer:** 4 (`docs/sprints/epic-4-dag.md` §3:131 — the **convergence point**; the fan-out→converge graph collapses here. Max parallel worktrees = **1**). 4.11 is a hard synchronization barrier: it cannot branch until **every** STOP trigger (4.2–4.8), the watchdog (4.9), and auto-brainstorm (4.10) have merged (DAG §2:116-120).
**Worktree:** `epic-4/4-11-auto-mad-mode` (owners: Charlie + Winston, DAG §5:199)
**Critical Path:** **ON** the critical path — the spine is `4.1 → 4.2 → 4.10 → 4.11 → 4.12` (DAG §4:171). 4.11 is the convergence bottleneck; 4.12 (the mad-only unsign recovery slice) consumes the `approved_by: ai-mad-mode` signoff format + the clarification-resolution artifact that 4.11 *defines*.
**Depends on (all `done` + merged on `main`):**
- **All of Layer 2 (4.2–4.9, all `done`)** — 4.11's AC "mad-mode encounters any of the OTHER 5 STOP triggers → the loop still halts" is only testable once 4.4–4.8 exist, and "respects the watchdog" needs 4.9 (DAG §2:116-120). The 7 trigger_ids + the `_ORDERED_TRIGGERS` registry are FROZEN (4.1/4.2 root).
- **4.10** (`done`, merged `016f408`) — produces `.claude/state/clarifications/<id>/options.md` (the `## Option N:` + `### Pros/Cons/Risks` format 4.11 reads option 1 from) + `open_clarification.md` (STOP 1's surface). 4.11 reuses `engine/auto_brainstorm.py`'s `parse_options_contract`/option format and the `_maybe_run_auto_brainstorm_on_ambiguity` loop-seam pattern.
- **Story 2A.12** (sign flow, `done`) — `validate_signoff` → `write_record` → journal `signoff_recorded`. 4.11 auto-signs through this exact seam with `approved_by: ai-mad-mode`.
- **Story 2A.7** (signoff state machine, `done`) — `SignoffState` (`awaiting-signoff`/`drafted-not-approved`/`approved`/`invalidated-by-replan`) + `compute_state`. STOP 2 (4.3) halts on `AWAITING_SIGNOFF`/`DRAFTED_NOT_APPROVED`.
- **4.1** (`done`, merged `2cc8ce4`) — the frozen `engine/auto_loop.py` `run_auto_loop` iteration contract (`:239-371`). 4.11 inserts a mad-mode interception of the `if stop.fired:` branch (`:349-358`) + threads a `mad_mode: bool` param, without churning the iteration contract.

**Consumed by (downstream):**
- **4.12** mad-only unsign (Layer 5, the recovery slice) reverses `approved_by: ai-mad-mode` signoffs (preserving human ones) and, with `--include-clarifications`, recreates `open_clarification.md` + removes the resolution artifact (epics.md:2326-2341). **The `ai-mad-mode` signoff sentinel + the clarification-resolution artifact format are contracts 4.12 reverses — design them reversibly (see D3).**
- **5.19** dashboard renders STOP banners; **5.x** may surface mad-resolution audit trail.

> **Layer-4 precondition — VERIFIED.** 4.11 is **not** Story N.1, so the CONTRIBUTING §7.4 epic-entry gate does **not** re-apply (epic-4 is `in-progress`; the gate cleared at 4.1). The Layer-4 precondition (DAG §3:131) is **"all of Layer 2 complete (esp. 4.2 + 4.3) + 4.10 (options) + 2A.12 sign flow"** — **satisfied**: 4.2–4.10 are all `done` + merged; `stop_registry.py`/`stop_triggers.py`/the 7 triggers + `engine/auto_brainstorm.py` + `signoff/` (validate/write/states) are frozen on `main`; `freeze_wireformat_snapshots --check` is **7/7**. **Inherited debt (cite, do NOT fix):** ratified Epic-4 **Decision D3** (DAG §289-306) — real specialist dispatch is mock/nominal in v1; `/sdlc-auto-mad` inherits the same mock-only `EPIC-4-DEBT-AUTO-REAL-DISPATCH` guard 4.1/4.6/4.7/4.10 carry (C8). 4.11 **owns** the `CR4.10-W3` correlate-by-clarification-id hand-off (deferred-work.md; addressed by C7).

---

## Story

As a **tech lead opting into mad-mode for prototyping or low-stakes runs**,
I want **`/sdlc-auto-mad` to run the auto-loop with auto-resolution of the `signoff_required` and `open_clarification` STOPs — auto-signing with `approved_by: ai-mad-mode` (via the Story 2A.12 sign seam) and auto-resolving clarifications by picking the synthesizer's first option from `options.md` (or a `synth-pick` sentinel when no options notes) — while STILL halting on the other 5 STOP triggers and respecting the watchdog**,
so that **mad-mode iteration is fast for exploratory work, yet every mad-resolution is journaled (`kind=auto_mad_resolve`) and byte-distinguishable from human action, hence fully reversible by 4.12** (PRD **FR20** [epics.md:47], audit-trail/reversibility **FR23** [epics.md:50]; the watchdog **FR24** [epics.md:51]; the loop's pure-function-of-disk / resume contract **NFR-REL-5** is inherited from 4.1 and must be preserved).

---

## Acceptance Criteria

> **READ FIRST — binding ground-truth corrections + scope boundaries (verified against the codebase 2026-06-22). These prevent the most likely implementation disasters. Do not skip.**
>
> **(C1) THE HEADLINE CORRECTION — the journal kind is `auto_mad_resolve`, NOT `mad_resolution`.** epics.md:2301 prose says `kind=mad_resolution`, but the codebase **already commits to `auto_mad_resolve`**: it is pre-listed in `state/projection.py:46` `_KNOWN_KINDS` AND in `tests/unit/state/test_state_projection.py:129`. Use **`auto_mad_resolve`** verbatim. Do NOT introduce `mad_resolution`; do NOT "fix" the test or `_KNOWN_KINDS` to the prose spelling (same trap as 4.10's C1: epics said "synthesizer", the registry name `requirement-synthesizer` won). The projection fold `_fold_auto_loop_status` (`projection.py:85-102`) reacts only to `auto_loop_iteration`/`stop_triggered`/`stop_trigger_raised` — it **ignores `auto_mad_resolve`**, so a mad-resolution entry is **AUDIT-ONLY** (it does NOT set `auto_loop_status`). Add the `auto_mad_resolve` row to `docs/decisions/ADR-028-journal-kind-taxonomy.md` §3 (it is in `_KNOWN_KINDS` but NOT yet in the §3 taxonomy table → the bmad-code-review audit script flags any `kind="..."` literal absent from §3) + a Revision-Log line (ADR-028 forward rule). Event-only kind → all-zero `after_hash` sentinel (`sha256:` + 64×`0`). **No snapshot regen; freeze stays 7/7.**
>
> **(C2) AUTO-SIGN REUSES THE 2A.12 SEAM — there is NO standalone `sign(phase, approved_by=…)` function.** Signing is the `validate_signoff → write_record → journal signoff_recorded` chain in `cli/_signoff_check.py:check_signoffs`. `validate_signoff(phase, *, repo_root, now_utc)` (`validator.py:52`) **reads the SIGNOFF.md draft and RAISES if `approved=false` (`:100`) or `approved_by` is null (`:121`)**, then **hash-validates every artifact** (`:136/:154/:167`), then builds the `SignoffRecord` with `approved_by=draft.approved_by` (`:186`). `write_record(record, *, repo_root)` (`records.py:285`) persists `.claude/state/signoffs/phase-N.yaml`. **To inject `ai-mad-mode`, mad-mode must SEED the SIGNOFF.md draft** with `approved: true` + `approved_by: ai-mad-mode` (generate the draft via `signoff.generate_signoff_md` first if the phase is `AWAITING_SIGNOFF` — no draft exists yet), then run validate→write→journal. This produces a record byte-identical to a human's except the `approved_by` field (the AC's invariant). See **D1**. Import the public seam from `sdlc.signoff` (`__init__.py` re-exports `validate_signoff`, `write_record`, `generate_signoff_md`, `SignoffRecord`, `compute_state`, `SignoffState`, `read_signoff_md_draft`).
>
> **(C3) THE SIGNOFF RECORD IS A FROZEN StrictModel — mad-mode does NOT add a field or touch its snapshot.** `SignoffRecord` (`records.py:141`) is a `StrictModel`; `approved_by` is `Annotated[str, StringConstraints(min_length=1)]` — `"ai-mad-mode"` is a valid value, **no schema change**. Timestamps are RFC3339-UTC-ms (`approved_at`/`drafted_at`/`validated_at`; pattern `^\d{4}-…\.\d{3}Z$`) — use `cli._time.now_rfc3339_utc_ms()`. The `signoff_recorded`/`signoff_*` journal kinds already exist in ADR-028 §3. Zero new ADR-024 wire-format contracts (Epic-4 Decision D1; freeze 7/7).
>
> **(C4) STOP 1 + STOP 2 are RESOLVED; the OTHER 5 + watchdog still HALT.** The registry (`stop_registry.py:_ORDERED_TRIGGERS`, `:19-27`) + the 7 `trigger_id` strings are FROZEN (the 4.1/4.2 root — C5 of 4.10). Mad-mode registers NO trigger and edits NO `stop_*.py` / `stop_registry.py` / `stop_triggers.py`. The **only two** resolvable trigger_ids are exactly `"open_clarification"` (`stop_clarification.py:17`) and `"signoff_required"` (`stop_signoff.py:26`). The other five — `"high_risk_path"`, `"pr_ready_story"`, `"replan_dirty"`, `"agent_failed"`, `"bug_awaiting_decide"` — and `"watchdog_timeout"` MUST still halt (mad-mode does NOT auto-resolve them, epics.md:2305). `check_stop` returns the **first fired trigger in priority order** and `"high_risk_path"` is checked **before** `"open_clarification"`/`"signoff_required"` (`_ORDERED_TRIGGERS` order) → a high-risk path correctly **pre-empts** mad-resolution and halts. Good.
>
> **(C5) THE LOOP SEAM — intercept the `if stop.fired:` branch at `auto_loop.py:349-358`; NO new trigger.** When `mad_mode` is on AND `stop.trigger in {"open_clarification","signoff_required"}`: auto-resolve (write to disk + journal `auto_mad_resolve`) and **`continue` the `while` loop** — do NOT `return _finish_halted_on_stop_trigger`. Otherwise halt exactly as today. The next iteration re-scans disk (`scan` at `:269`) — the resolved STOP no longer fires (pure-fn-of-disk; D4). Keep the iteration contract + `check_stop` signature + the watchdog block (`:319-336`) + the brainstorm seam (`:338-347`) byte-stable. Thread a new **`mad_mode: bool = False`** param onto `run_auto_loop` (after `auto_brainstorm`, `:250`) — the same way 4.9 threaded `watchdog_timeout_minutes` and 4.10 threaded `auto_brainstorm`. Keep the loop edit a **thin delegate** into `engine/auto_mad.py` (NET-NEW, DAG §5:204); `auto_loop.py` is 377 LOC (≤400 cap) — do not bloat it.
>
> **(C6) CLARIFICATION AUTO-RESOLVE — read option 1, write a NET-NEW resolution artifact, REMOVE `open_clarification.md`.** `OpenClarificationTrigger` fires IFF `.claude/state/clarifications/<id>/open_clarification.md` exists (it re-reads disk, `stop_clarification.py`); **removing that file is the ONLY action that un-fires the STOP** (D4). Reuse `auto_brainstorm.py`'s option format (`## Option N:` headers + `### Pros/### Cons/### Risks`; `parse_options_contract`/`_AUTO_PICK_PATTERNS` at `:43-107`) — but there is **NO existing "extract option 1 text" helper** (4.11 writes it, e.g. regex split on `^## Option \d+:`). If `options.md` is absent (panel bypassed/failed → CR4.10-D1 wrote only `open_clarification.md`), use the `"synth-pick"` sentinel (epics.md:2300). The resolution artifact is **NET-NEW** — no `resolution`/`RESOLUTION.md` writer exists anywhere (grep-confirmed); 4.11 designs it (see **D3**) and must preserve enough for 4.12 to recreate `open_clarification.md` on reverse (epics.md:2340). Write via `concurrency.io_primitives.atomic_write` (POSIX-only; `ImportError` on win32 → full suite runs on Linux CI/WSL).
>
> **(C7) CORRELATE BY THE FIRED DIR (`stop.target`) — this closes CR4.10-W3.** `OpenClarificationTrigger` halts on the **lexicographically-first** clarification dir (`stop_clarification.py` sorts `iterdir()`), which may differ from the brainstorm's freshly-minted `clar-<digest>`. Mad-mode MUST resolve the dir named by **`stop.target`** (the one actually blocking the loop) and set the `auto_mad_resolve` journal `target` to **that same dir** — NOT the brainstorm's minted id. Multiple coexisting clarifications converge because mad-mode resolves + `continue`s, and the trigger re-fires on the next lex-first until none remain. (Explicit 4.10→4.11 hand-off: deferred-work.md CR4.10-W3 "the 4.11 consumer must correlate by clarification_id … NOT by the STOP halt target" — here the halt target IS the canonical dir to resolve; correlate the journal entry to it.)
>
> **(C8) `/sdlc-auto-mad` INHERITS THE MOCK-ONLY GUARD.** `run_auto` hard-aborts unless `use_mock_runtime()` (`cli/auto.py:69-77`, `ERR_AUTO_LOOP_REAL_DISPATCH_DEFERRED`, debt `EPIC-4-DEBT-AUTO-REAL-DISPATCH`). The new mad entrypoint MUST carry the **same guard** — mad-mode is mock-only in v1 (ratified Epic-4 D3; the not-production-reachable boundary 4.1/4.6/4.7/4.10 all used). Register `/sdlc-auto-mad` as `@app.command(name="auto-mad")` mirroring `cli/_auto_register.py:36`; the entrypoint (`run_auto_mad`) mirrors `run_auto` (`cli/auto.py:60`) and passes `mad_mode=True` into `run_auto_loop`. See **D2**.
>
> **(C9) WATCHDOG DISTINGUISH — thread `mad_mode` into the timeout decision's `reason`.** `make_watchdog_stop_decision(repo_root_str, *, elapsed_minutes)` (`watchdog.py:31`) yields `trigger="watchdog_timeout", reason="elapsed ~N min"`; the halt journals `kind=stop_triggered {trigger, target, reason, correlation_id}` via `_finish_halted_on_stop_trigger`. To satisfy "the timeout journal entry distinguishes mad-mode runs from normal runs" (epics.md:2311), thread `mad_mode` to the decision and mark `reason` (e.g. `"elapsed ~30 min (mad-mode)"`) — minimal, no `StopDecision` field add (it is a frozen 4-field dataclass; do NOT extend it). See **D5**.
>
> **(C10) MODULE BOUNDARY + LOC + POSIX + no-`print` + zero new wire-format.** `engine/auto_mad.py` MAY import `signoff` (validate_signoff/write_record/generate_signoff_md/SignoffRecord/compute_state/SignoffState), engine siblings (`auto_brainstorm` parse helpers, `stop_triggers`), `journal` (`append_with_seq_alloc`), `state`, `config`, `concurrency.io_primitives`, `ids`, `errors`, `contracts`, and `runtime` **only via the `AIRuntime` ABC by DI**. It MUST NOT import `cli`/`dashboard` (forbidden) or `runtime.claude` directly (pre-commit-enforced). No `print()` in `engine/` — use `structlog` (architecture.md:489); state writes via `atomic_write` only. Every `src/` file ≤ 400 LOC. Run `scripts/check_module_boundaries.py` on `auto_mad.py` + `auto_loop.py` explicitly. The **only** doc edit touching a contract surface is the ADR-028 §3 `auto_mad_resolve` row (forward rule — no snapshot regen). `freeze_wireformat_snapshots --check` stays **7/7**.

---

**AC1 — Positive: mad-mode auto-resolves STOP 2 (signoff) and STOP 1 (clarification); each is journaled (FR20).** *(epics.md:2297-2301)*
**Given** `/sdlc-auto-mad` running the auto-loop (`mad_mode=True`, mock runtime),
**When** the loop's `check_stop` fires STOP trigger 2 (`signoff_required`) **or** STOP trigger 1 (`open_clarification`),
**Then** for `signoff_required`: mad-mode seeds/patches the SIGNOFF.md draft with `approved: true` + `approved_by: ai-mad-mode` (+ `approved_at` RFC3339-UTC-ms) and runs `validate_signoff → write_record`, producing the canonical `.claude/state/signoffs/phase-N.yaml` with `approved_by: ai-mad-mode` + the standard `signoff_recorded` journal entry (Story 2A.12, C2/C3),
**And** for `open_clarification`: mad-mode reads the synthesizer's **first option** from `.claude/state/clarifications/<id>/options.md` (or the `"synth-pick"` sentinel when `options.md` is absent), writes the resolution artifact (D3), and **removes `open_clarification.md`** for the dir named by `stop.target` (C6/C7),
**And** every mad-resolution appends `kind=auto_mad_resolve, target=<id>, decision=<value>` (C1) carrying the iteration's `correlation_id`,
**And** the loop **continues** (does NOT halt) and proceeds to the next iteration (C5/D4).

**AC2 — Mad-mode HALTS on the other 5 STOP triggers (does NOT auto-resolve).** *(epics.md:2303-2306)*
**Given** mad-mode running,
**When** `check_stop` fires any of `high_risk_path`, `pr_ready_story`, `replan_dirty`, `agent_failed`, `bug_awaiting_decide`,
**Then** the loop still halts via `_finish_halted_on_stop_trigger` (journals `kind=stop_triggered`, projection `auto_loop_status="halted"`) exactly as normal auto-mode (C4),
**And** the user is shown the trigger as in normal auto-mode (the same `result.stop_reason`).

**AC3 — Mad-mode respects the watchdog; its timeout entry is distinguishable.** *(epics.md:2308-2311)*
**Given** the auto-loop running mad-mode,
**When** the watchdog timeout fires (`watchdog_deadline_exceeded`, `:319-336`),
**Then** mad-mode halts on the timeout (Story 4.9) — it does NOT auto-resolve past a timeout,
**And** the timeout journal entry **distinguishes mad-mode runs from normal runs** (e.g. a `(mad-mode)` marker in the `stop_triggered` `reason`, threaded via `make_watchdog_stop_decision`, C9/D5).

**AC4 — Audit-trail integrity: mad signoffs are byte-distinguishable + every auto-resolution is journaled.** *(epics.md:2313-2316)*
**Given** the integration fixture `tests/integration/test_auto_mad.py` running through a multi-phase project,
**When** mad-mode signs a phase and resolves a clarification,
**Then** mad-mode signoffs are **byte-distinguishable** from human signoffs by the `approved_by` field (`ai-mad-mode` vs a human identity) in `.claude/state/signoffs/phase-N.yaml`,
**And** the journal records **every** auto-resolution with a full audit trail (`auto_mad_resolve` per resolution + the canonical `signoff_recorded` for signs), sufficient for 4.12 to selectively reverse only the `ai-mad-mode` actions while preserving human ones (FR23 reversibility).

**AC5 — Test matrix: mad-mode behavioural cells (per Murat's 4-cell lens + the audit-trail test).** *(epics.md:2353)*
**Given** the Epic-4 test gates (under `SDLC_USE_MOCK_RUNTIME=1`),
**When** the 4.11 suite runs,
**Then** these cells pass:
  1. **positive — signoff auto-sign** — STOP 2 fires → `.claude/state/signoffs/phase-N.yaml` written with `approved_by: ai-mad-mode` + `signoff_recorded` + `auto_mad_resolve` journaled; loop continues (AC1);
  2. **positive — clarification auto-resolve** — STOP 1 fires → option 1 read, resolution artifact written, `open_clarification.md` removed for `stop.target`, `auto_mad_resolve {target, decision}` journaled; loop continues (AC1/C6/C7); plus the `synth-pick` sentinel sub-cell (no `options.md`);
  3. **negative — halts on another STOP** — an `agent_failed`/`pr_ready_story`/`high_risk_path` STOP under mad-mode → `result.halted is True`, `result.stop_reason == <that trigger>`, NO `auto_mad_resolve` for it (AC2/C4);
  4. **termination — watchdog** — sub-minute timeout under mad-mode → halts, `stop_reason="watchdog_timeout"`, the `reason` carries the mad-mode marker (AC3/C9);
  5. **resume / idempotency + audit** — re-running the loop after a mad-resolution does NOT re-sign an already-`approved` phase nor re-resolve a removed clarification (pure-fn-of-disk); mad signoffs stay byte-distinguishable + every resolution is journaled (AC4).
New tests at `tests/integration/test_auto_mad.py` (top-level; multi-phase, build a registry + project like `test_auto_brainstorm.py` / `test_sdlc_start_panel.py`) and `tests/unit/engine/test_auto_mad.py` (orchestrator unit cells: option-1 extraction, sentinel, draft-seed, resolve-then-remove, journal shape). Extend `tests/unit/engine/test_auto_loop.py` with a `mad_mode` loop cell (resolve-and-continue vs halt-on-other). The signoff cells need a real phase + draft fixture (mirror the signoff tests under `tests/`), NOT the empty-registry stop-trigger idiom.

**AC6 — Quality gate green + TDD-first (CONTRIBUTING §1/§2/§5).**
Quality gate green per §1 (ruff format/check, `mypy --strict src/`, **FULL** pytest — not just the new files (the 4.1/4.2 lesson: a partial run hides pre-existing failures; run the real gate-script args per memory `feedback_code_review_run_full_suite`), coverage ≥ **87** operational floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` **7/7 unchanged**, module-boundary + LOC ≤ 400). TDD-first (§2) is **MANDATORY** (this story touches CLI surface `/sdlc-auto-mad` + public API `run_auto_loop`/`engine/auto_mad.py` — NOT novel substrate): the failing integration + unit cells are the failing-first commit, **RED before** `engine/auto_mad.py`, the `auto_loop.py` seam, and the CLI entrypoint land, visible in `git log --reverse` (`test(4.11)` → `feat(4.11)` → `docs(4.11)`). Material decisions surfaced as **D1–D5** (§5). Merged-before-done (Epic-3 retro A1): a `feat(4.11)` commit reachable from `HEAD` + `test(4.11)` precedes the first GREEN before the story flips to `done`; flip `done` **POST-merge** with a **GREEN POSIX CI** run; verify R1/R2 **by hand on Windows** (the commit-msg gate cp1252 false-passes on win32 — memory). The `[fresh-context-review]` tag goes ONLY on the docs-only review commit (R2 forbids `src/` there).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the behaviour suite — the integration auto-mad cells (sign → `approved_by: ai-mad-mode`; clarification → resolve + remove `open_clarification.md`; halt-on-other-STOP; watchdog-distinguish; resume idempotency) + the orchestrator unit cells (option-1 extraction, `synth-pick` sentinel, draft-seed-and-validate, journal shape). All RED before `engine/auto_mad.py`, the `auto_loop.py` `mad_mode` seam, and the `/sdlc-auto-mad` entrypoint land.

- [x] **(§5) T0 — Resolve D1–D5** (mad-sign seam · CLI-flag vs config · resolution-artifact format · resolve-and-continue · watchdog-distinguish) and record the choices in the Change Log **before writing code**. Recommended answers are pre-filled in §Decisions; confirm or override. Cite (don't fix) the inherited debt: `EPIC-4-DEBT-AUTO-REAL-DISPATCH` (mock-only guard, C8), `EPIC-4-DEBT-AUTO-BRAINSTORM-REAL-SIGNAL`, `CR4.6-W2` (mad-mode HALTS on `agent_failed` → respected), `CR4.2-W3` (non-sticky halt). Mark `CR4.10-W3` as **addressed** by this story (C7) in `deferred-work.md`.
- [x] **(AC1–AC5, §2) Write failing tests FIRST.**
  - `tests/integration/test_auto_mad.py` (NEW; reuse `tests/integration/conftest.py`; mirror `test_auto_brainstorm.py` registry/project build + the signoff fixtures): drive `run_auto_loop(..., mad_mode=True)` (or the `run_auto_mad` path) over a fixture that reaches STOP 2 then STOP 1; assert the `phase-N.yaml` `approved_by == "ai-mad-mode"`, `signoff_recorded` + `auto_mad_resolve` journal entries (via `iter_entries(...).kind` — structured, NOT JSON-substring per CR4.10-P2), the clarification resolution artifact present + `open_clarification.md` removed, loop continued; plus a halt-on-`agent_failed` cell (`result.halted`, `result.stop_reason`), a watchdog cell (mad-mode marker in `reason`), and a resume cell. RED.
  - `tests/unit/engine/test_auto_mad.py` (NEW; mirror `tests/unit/engine/test_auto_brainstorm.py`): (a) extract-first-option from a sample `options.md` returns Option 1's body; (b) absent `options.md` → `synth-pick` sentinel; (c) the resolve writes the resolution artifact + unlinks `open_clarification.md` for a given dir; (d) the mad-sign helper seeds the draft + calls validate→write and the record carries `approved_by: ai-mad-mode`; (e) `auto_mad_resolve` entry has `target`/`decision`/all-zero `after_hash`. RED.
  - Extend `tests/unit/engine/test_auto_loop.py`: a `mad_mode=True` cell where a forced `open_clarification`/`signoff_required` STOP is resolved-and-continued (loop does NOT halt), and a `mad_mode=True` cell where a forced `agent_failed` STOP still halts; back-compat: every existing loop test (`mad_mode=False` default) stays green. RED.
- [x] **(C1, C2, C3, C6, C7, D1, D3) Implement `src/sdlc/engine/auto_mad.py`** (NEW, ≤ 400 LOC) — the mad-mode orchestrator. Public seam e.g. `async def maybe_mad_resolve_stop(repo_root, *, stop: StopDecision, journal_path, correlation_id, now_utc, ...) -> bool` returning `True` when it resolved (loop continues) / `False` when not (loop halts). Internals: (i) `_extract_first_option(options_text) -> str | None` (regex on `^## Option \d+:`), reusing `auto_brainstorm.parse_options_contract` shape; (ii) `_resolve_clarification(...)` — read option 1 (or `synth-pick`), `atomic_write` the resolution artifact (D3), unlink `open_clarification.md` at `stop.target`; (iii) `_mad_sign(...)` — seed SIGNOFF.md (generate via `generate_signoff_md` if `AWAITING_SIGNOFF`) with `approved: true`/`approved_by: ai-mad-mode`, `validate_signoff → write_record`, journal `signoff_recorded`; (iv) journal `auto_mad_resolve {target, decision}` via `append_with_seq_alloc` (all-zero `after_hash`). No `print` (structlog). Export from `engine/__init__.py`.
- [x] **(C4, C5, D4) Wire the loop seam in `run_auto_loop`**
- [x] **(C8, C9, D2, D5) Add the `/sdlc-auto-mad` entrypoint + watchdog marker.**
- [x] **(C1, C10) ADR-028 forward rule**
- [x] **(AC6, §1) Full quality gate to green**
- [x] **(§3) Worktree**
- [ ] **(§4) Chunked review**

---

## Dev Notes

### Substrate map (verified 2026-06-22 — exact symbols; wrong names break the build)

| Concern | Symbol / path | Notes |
|---|---|---|
| **NEW orchestrator (write here)** | `src/sdlc/engine/auto_mad.py` | NET-NEW per DAG §5:204. Mad-resolution orchestrator: option-1 extraction + clarification resolve + mad-sign + `auto_mad_resolve` journal. ≤ 400 LOC. Export from `engine/__init__.py`. |
| **loop seam (edit here — additive)** | `engine.auto_loop.run_auto_loop` (`auto_loop.py:239-371`); intercept `if stop.fired:` (`:349-358`); add `mad_mode: bool = False` after `auto_brainstorm` (`:250`) | Loop has `runtime, registry, journal_path, repo_root, correlation_id, state` in scope. Iteration contract + `check_stop` sig stay frozen (C5). On mad-resolve: `continue`, not `return`. |
| **halt path (reuse — do NOT call directly on resolve)** | `engine.auto_loop._finish_halted_on_stop_trigger` (`:156-181`) | Reads `StopDecision.{fired,trigger,target,reason}`; journals `kind=stop_triggered {trigger,target,correlation_id,reason}` + rebuilds state. Mad-mode calls this ONLY for the non-resolvable STOPs (the existing fall-through). |
| **STOP registry (consume — do NOT edit)** | `engine.stop_registry._ORDERED_TRIGGERS` (`:19-27`); `engine.stop_triggers.{StopDecision,StopTrigger,check_stop}` | 7 trigger_ids in priority order: `high_risk_path, open_clarification, signoff_required, pr_ready_story, replan_dirty, agent_failed, bug_awaiting_decide`. `check_stop` returns the FIRST fired (C4). `StopDecision` = frozen 4-field dataclass `(fired, trigger, target, reason)` — do NOT extend (C9). |
| **STOP 1 (open_clarification)** | `engine.stop_clarification.OpenClarificationTrigger` — `trigger_id="open_clarification"` (`:17`); consts `.claude/state/clarifications`, `open_clarification.md` | Halts on lex-first dir with `open_clarification.md`; `stop.target` = that dir path (C6/C7). Removing the file un-fires it. |
| **STOP 2 (signoff_required)** | `engine.stop_signoff.SignoffRequiredTrigger` — `trigger_id="signoff_required"` (`:26`); `_HALTING_STATES={AWAITING_SIGNOFF, DRAFTED_NOT_APPROVED}` (`:20`) | `target=f"{phase_dir}/SIGNOFF.md"`; re-reads disk via `compute_state`. Mad-mode signs the phase it names. |
| **sign seam (reuse — C2)** | `sdlc.signoff`: `validate_signoff(phase,*,repo_root,now_utc)` (`validator.py:52`), `write_record(record,*,repo_root)` (`records.py:285`), `generate_signoff_md` (draft if AWAITING), `compute_state`/`SignoffState` (`states.py:30/39`), `read_signoff_md_draft` | `validate_signoff` RAISES if draft `approved=false` (`:100`)/`approved_by` null (`:121`) + hash-validates artifacts; builds `SignoffRecord(approved_by=draft.approved_by, approved_at=draft.approved_at or now_utc, …)` (`:186-187`). Seed the draft with `ai-mad-mode` (C2/D1). |
| **signoff record (frozen StrictModel — C3)** | `signoff.records.SignoffRecord` (`records.py:141`); path `.claude/state/signoffs/phase-{1\|2}.yaml` (`_signoff_path`) | `approved_by: str(min_length 1)` — `"ai-mad-mode"` valid, no schema change. Timestamps RFC3339-UTC-ms. 4.12 reverses via `invalidate_record` filtered on `approved_by=="ai-mad-mode"`. |
| **signing flow reference (mirror)** | `cli._signoff_check.check_signoffs` (`_signoff_check.py:148-290`) | The human path: draft `approved=true` → `validate_signoff` → `write_record` → journal `signoff_recorded {phase, approved_by, artifact_count, all_hashes_clean}`. Copy this shape; substitute `approved_by="ai-mad-mode"`. |
| **options format (reuse parse — C6)** | `engine.auto_brainstorm`: `parse_options_contract` (`:92-107`), `_AUTO_PICK_PATTERNS` (`:43-52`), `OptionsContract` (`:61-66`), `_MIN_OPTIONS=2` | Format: `## Option N:` headers + `### Pros/### Cons/### Risks` + member-concern markers. **No extract-option-1 helper exists** — write `_extract_first_option` (regex `^## Option \d+:`). |
| **clarification id (reference)** | `engine.auto_brainstorm.clarification_id_for` (`:69`) → `clar-<16-hex>`; `AmbiguityContext(task_id, summary)` (`:55`) | 4.11 resolves by `stop.target` dir, not by re-minting the id (C7). |
| **watchdog (edit reason — C9)** | `engine.watchdog.make_watchdog_stop_decision(repo_root_str,*,elapsed_minutes)` (`:31`); `watchdog_deadline_exceeded` (`:8`) | `trigger="watchdog_timeout", reason="elapsed ~N min"`. Thread `mad_mode` → mark `reason` (D5). Call site `auto_loop.py:319-336`. |
| **CLI entrypoint (mirror — C8)** | `cli.auto.run_auto` (`auto.py:60-133`); register `cli._auto_register.py:36` `@app.command(name="auto")` | `run_auto` guards `use_mock_runtime()` (`:69-77`, `EPIC-4-DEBT-AUTO-REAL-DISPATCH`), loads cfg, `asyncio.run(run_auto_loop(...))`. `run_auto_mad` mirrors it + `mad_mode=True`; register `name="auto-mad"`. |
| **config (read only)** | `config.project.ProjectConfig` (`project.py:23-42`): `max_parallel_agents, auto_brainstorm, legacy_code_globs, watchdog_timeout_minutes, auto_accept_threshold` | NO `mad_mode` field — mad-mode is a per-invocation CLI flag, NOT config (D2). Do NOT add a field. |
| **journal kind (C1)** | `auto_mad_resolve` — pre-listed `state/projection.py:46` `_KNOWN_KINDS` + `tests/unit/state/test_state_projection.py:129`. ADR-028 §3 forward-rule row needed. | NOT `mad_resolution` (epics prose). Audit-only (fold ignores it). All-zero `after_hash`. |
| **atomic write / time / seq** | `concurrency.io_primitives.atomic_write` (POSIX-only); `cli._time.now_rfc3339_utc_ms`; `journal.append_with_seq_alloc` | Resolution + journal writes via these (C6/C10). `append_with_seq_alloc` is the Epic-4 day-one seq allocator (retro D-RIDE forward rule). |

### The mad-sign design tension (read before implementing D1)

STOP 2 fires on **two** states (`stop_signoff.py:20`): `AWAITING_SIGNOFF` (no SIGNOFF.md draft yet) and `DRAFTED_NOT_APPROVED` (draft exists, `approved=false`). `validate_signoff` **requires** a draft with `approved: true` + `approved_by` non-null (`validator.py:100,121`) and hash-validates artifacts. So mad-mode's auto-sign is NOT a one-liner:
- For `DRAFTED_NOT_APPROVED`: patch the existing SIGNOFF.md to set `approved: true` + `approved_by: ai-mad-mode`, then validate→write→journal.
- For `AWAITING_SIGNOFF`: there is no draft → `generate_signoff_md` first, then patch + validate→write→journal.

The honest, audit-faithful path (D1a) reuses 2A.12 end-to-end so the record is hash-validated and byte-identical to a human's except `approved_by`. The lighter path (D1b) constructs `SignoffRecord` directly + `write_record`, skipping the hash validation — **weaker audit integrity, rejected for the security-sensitive auto-sign** unless review-B accepts it. Verify which signoff state the mock-runtime auto-loop harness actually reaches; if only `DRAFTED_NOT_APPROVED` is reachable in v1, scope the `AWAITING_SIGNOFF` generate-draft sub-path behind a guard (D1c) and cover it with a unit cell.

### The resolve-and-continue invariant (D4) + projection safety

The loop is pure-function-of-disk (4.1, A4). After mad-mode resolves a STOP it `continue`s; the next iteration re-`scan`s (`:269`) and `check_stop` no longer fires that trigger (the signoff is `APPROVED` / the `open_clarification.md` is gone). The watchdog (`:319-336`) is the runaway guard (FR24) — mad-mode must NOT loop unbounded; the timeout still halts (AC3). `auto_mad_resolve` is AUDIT-ONLY: `_fold_auto_loop_status` (`projection.py:85-102`) ignores it, so it does not perturb `auto_loop_status`. Do NOT emit a `stop_triggered` for a mad-resolved STOP (that would latch `halted` in the projection even after the disk signal clears).

### Test idioms (reuse — do not invent)

- **Mock-runtime autouse:** `tests/conftest.py` sets `SDLC_USE_MOCK_RUNTIME=1` suite-wide.
- **Signoff fixtures:** build a real phase dir + SIGNOFF.md draft (mirror the `tests/` signoff tests) so `validate_signoff` has artifacts to hash; the empty-registry stop-trigger idiom will NOT suffice for the sign cells.
- **Clarification fixtures:** mirror `tests/integration/test_auto_brainstorm.py` (write `options.md` with ≥2 `## Option N:` + `### Pros/Cons/Risks`) and `tests/integration/stop_triggers/test_stop_clarification.py` (the `.claude/state/clarifications/<id>/open_clarification.md` convention + 4-cell shape).
- **Journal asserts:** structured `iter_entries(...).kind` (NOT exact JSON-substring — CR4.10-P2 lesson). Assert `auto_mad_resolve` `target`/`decision` + the canonical `signoff_recorded`.
- **Loop cells:** extend `tests/unit/engine/test_auto_loop.py`; assert resolve-and-continue (`result.halted is False`, advanced) vs halt-on-other-STOP (`result.halted is True`, `result.stop_reason`).

### Project Structure Notes

- **New files:** `src/sdlc/engine/auto_mad.py`; `tests/integration/test_auto_mad.py`; `tests/unit/engine/test_auto_mad.py`; optionally `src/sdlc/cli/auto_mad.py` (if D2 puts the entrypoint in its own module) + a register hook.
- **Modified:** `src/sdlc/engine/auto_loop.py` (`mad_mode` param + interception — C5), `src/sdlc/engine/__init__.py` (export), `src/sdlc/cli/auto.py` (`run_auto_mad` + watchdog `mad_mode` thread) **or** `cli/auto_mad.py`, `src/sdlc/cli/_auto_register.py` (`name="auto-mad"` command), `src/sdlc/engine/watchdog.py` (`mad_mode` → `reason`, C9), `tests/unit/engine/test_auto_loop.py` (mad cell), and `docs/decisions/ADR-028-journal-kind-taxonomy.md` (§3 row + Revision-Log).
- **NOT modified:** any `stop_*.py` / `stop_registry.py` / `stop_triggers.py` (C4); any `src/sdlc/contracts/` or `tests/contract_snapshots/v1/` (C3/C10 — freeze 7/7); `signoff/records.py`/`validator.py` (reuse as-is, C2); `state/projection.py` `_KNOWN_KINDS` (`auto_mad_resolve` already present, C1); `config/project.py` (no `mad_mode` field, D2); `dispatcher/` (reuse).
- **Conventions:** every `src/` file ≤ 400 LOC; absolute `from sdlc.X import Y`; `engine` MAY import `signoff`/`engine`/`journal`/`state`/`config`/`concurrency`, never `cli`/`dashboard`/`runtime.claude` (C10); no `print()` in `engine/` (structlog).

### References

- Epic + ACs: `epics.md:2289-2316` (Story 4.11 + 4 BDD ACs); `:2353` (audit-trail test gate); `:2355` (deps: 4.11 = 4.10 + 2A.12); FR map `:47` (FR20), `:50` (FR23), `:51` (FR24).
- Loop substrate (edit additively): `src/sdlc/engine/auto_loop.py:239-371` (`run_auto_loop`); seam `:349-358`; halt finalizer `:156-181`; watchdog block `:319-336`; brainstorm seam `:338-347`.
- STOP registry/triggers (consume): `src/sdlc/engine/stop_registry.py:19-27`; `stop_triggers.py:16-45`; `stop_clarification.py:17`; `stop_signoff.py:20,26`.
- Sign seam (reuse): `src/sdlc/signoff/__init__.py` (public API); `validator.py:52,100,121,186`; `records.py:141,285`; `cli/_signoff_check.py:148-290` (the human sign flow to mirror); `states.py:30,39`.
- Options/clarification (reuse parse + format): `src/sdlc/engine/auto_brainstorm.py:43-127` (`parse_options_contract`, `_AUTO_PICK_PATTERNS`, `_valid_options_text`), `:69` (`clarification_id_for`); 4.2 surface `engine/stop_clarification.py`.
- Watchdog (edit reason): `src/sdlc/engine/watchdog.py:8,31`.
- CLI (mirror + guard): `src/sdlc/cli/auto.py:60-133`; register `src/sdlc/cli/_auto_register.py:36`.
- Journal kind / forward rule: `docs/decisions/ADR-028-journal-kind-taxonomy.md` §3/§4; projection `src/sdlc/state/projection.py:40-53` (`_KNOWN_KINDS` — `auto_mad_resolve` at `:46`), `:85-102` (fold ignores it); test `tests/unit/state/test_state_projection.py:129`.
- Quality gate + TDD/merged-before-done: `CONTRIBUTING.md:14-28` (gate; coverage 87 floor `:22`), `:32-64` (TDD-first + R1/R2), `:146-167` (fresh-context-review tag).
- DAG / decisions: `docs/sprints/epic-4-dag.md` §2:116-120 (4.11 convergence edges), §3:131 (Layer-4 deps), §4:171-178 (critical path), §5:199 (worktree), §242 (mad-mode audit-trail integrity row), §289-306 (D3 real-dispatch deferred-with-guard).
- Inherited debt (cite, don't fix): `deferred-work.md` — `EPIC-4-DEBT-AUTO-REAL-DISPATCH` (C8 mock-only guard), `EPIC-4-DEBT-AUTO-BRAINSTORM-REAL-SIGNAL`, `CR4.6-W2` (mad-mode HALTS on `agent_failed`), `CR4.2-W3` (non-sticky halt); **mark `CR4.10-W3` addressed** (C7).

---

## Decisions Needed

- **D1 — The mad-sign seam (headline).** How does mad-mode write `approved_by: ai-mad-mode` (no standalone `sign()` exists, C2)?
  - **(a) Reuse the full 2A.12 path (Recommended).** Seed/patch SIGNOFF.md (`generate_signoff_md` if `AWAITING_SIGNOFF`) with `approved: true` + `approved_by: ai-mad-mode`, then `validate_signoff → write_record → journal signoff_recorded` + `auto_mad_resolve`. Hash-validated, canonical, byte-distinguishable, reversible by 4.12. Cost: must write the SIGNOFF.md draft markdown (the `_SignoffMdDraft` fenced format).
  - **(b) Construct `SignoffRecord` directly + `write_record`.** Lighter, but **skips `validate_signoff`'s artifact hash-drift validation** → weaker audit integrity for an autonomous gate-approval. Reject for the security-sensitive path unless review-B accepts.
  - **(c) Scope the `AWAITING_SIGNOFF` generate-draft sub-case behind a guard.** If the mock auto-loop harness only reaches `DRAFTED_NOT_APPROVED` in v1, cover the generate-draft path with a unit cell + a pre-emptive guard rather than a full integration cell.
  - *Recommendation: (a), combined with (c) for scope — verify which signoff state is reachable in the mock harness.*

- **D2 — Mad-mode surface: distinct CLI entrypoint vs config field vs `--mad` flag.**
  - **(a) Distinct `/sdlc-auto-mad` entrypoint passing `mad_mode=True` (Recommended).** Matches epics/DAG ("/sdlc-auto-mad" is a named command); `ProjectConfig` has no mad field and mad-mode is opt-in-per-run (FR20 "opt-in YOLO"), not a persistent project setting. Register `@app.command(name="auto-mad")` (C8).
  - **(b) A `--mad` flag on `run_auto`.** Fewer files, but conflates the safe + YOLO modes behind one command and diverges from the "/sdlc-auto-mad" spec.
  - **(c) A `project.yaml` `mad_mode` field.** Rejected — mad-mode must be an explicit per-invocation opt-in, not a sticky setting.
  - *Recommendation: (a).*

- **D3 — Clarification resolution artifact format (NET-NEW; 4.12 reverses it).**
  - **(a) `.claude/state/clarifications/<id>/resolution.md` (Recommended).** Metadata (`resolved_by: ai-mad-mode`, `decision`, `clarification_id`, `resolved_at`) + the picked option text + the **original `open_clarification.md` body** (so 4.12 can recreate it on `--include-clarifications`). Remove `open_clarification.md`. Mirrors the `options.md`/`open_clarification.md` sibling-file convention; `atomic_write`.
  - **(b) Journal-only resolution (no disk artifact).** Lighter, but epics.md:2340 ("the resolution is removed") implies a disk artifact, and 4.12 would have to reconstruct `open_clarification.md` from the journal.
  - *Recommendation: (a). Preserve enough for a clean 4.12 reverse.*

- **D4 — Post-resolve control flow.**
  - **(a) `continue` the `while` loop (Recommended).** Pure-fn-of-disk: re-scan + re-dispatch; the resolved STOP no longer fires; converges; the watchdog guards runaway. Matches the loop structure.
  - **(b) Re-run `check_stop` inline in the same iteration.** More complex, risks double-dispatch ambiguity. Reject.
  - *Recommendation: (a).*

- **D5 — Watchdog mad-mode distinguishing mechanism (C9).**
  - **(a) Thread `mad_mode` → mark `make_watchdog_stop_decision`'s `reason` (Recommended).** Minimal; the `stop_triggered` `reason` already flows to the journal; no contract change.
  - **(b) Add a `mad_mode` field to `StopDecision`.** Heavier — mutates the frozen 4.1-rooted `StopDecision` dataclass; ripples to every consumer. Reject for v1.
  - *Recommendation: (a).*

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

Composer (dev-story workflow)

### Debug Log References

- D1–D5 ratified per §Decisions (a/a/a/a/a); CR4.10-W3 marked addressed in deferred-work.md.
- Extracted `_maybe_finish_watchdog_halt` + `_try_mad_resolve_stop_and_continue` from `run_auto_loop` to satisfy ruff C901 without changing iteration contract.

### Completion Notes List

- Implemented `engine/auto_mad.py`: mad-sign via full 2A.12 `generate_signoff_md`→patch→`validate_signoff`→`write_record`; clarification resolve via option-1 extraction / `synth-pick` sentinel + `resolution.md` artifact; journals `auto_mad_resolve` (audit-only) + canonical `signoff_recorded`.
- Wired `mad_mode` seam in `run_auto_loop` (resolve-and-continue for `open_clarification`/`signoff_required`; other STOPs + watchdog unchanged).
- Added `/sdlc-auto-mad` CLI (`run_auto_mad`) with mock-only guard; watchdog `reason` carries `(mad-mode)` marker.
- ADR-028 §3 + Revision Log: `auto_mad_resolve` row (forward rule, freeze 7/7 unchanged).
- Tests: `tests/unit/engine/test_auto_mad.py`, `tests/integration/test_auto_mad.py`, mad-mode cells in `tests/unit/engine/test_auto_loop.py` — 15 new cells, full suite 3759 passed.
- Quality gate: ruff, mypy --strict (changed src), module-boundary, freeze 7/7 green locally.

### File List

- `src/sdlc/engine/auto_mad.py` (new)
- `src/sdlc/engine/auto_loop.py` (modified)
- `src/sdlc/engine/watchdog.py` (modified)
- `src/sdlc/engine/__init__.py` (modified)
- `src/sdlc/cli/auto.py` (modified)
- `src/sdlc/cli/_auto_register.py` (modified)
- `docs/decisions/ADR-028-journal-kind-taxonomy.md` (modified)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modified — CR4.10-W3 addressed)
- `tests/unit/engine/test_auto_mad.py` (new)
- `tests/integration/test_auto_mad.py` (new)
- `tests/unit/engine/test_auto_loop.py` (modified)

### Review Findings

_bmad-code-review (2026-06-22) — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor), all C1–C10 + D1–D5 SATISFIED. Triage: 1 decision-needed, 2 patch, 3 defer, ~19 dismissed (false positives / by-design pure-fn-of-disk / accepted POSIX invariant). Findings verified against source._

- [x] [Review][Decision→Patch applied 2026-06-22] Mad-resolve journal append runs AFTER the destructive disk mutation — `resolve_clarification` writes `resolution.md` → unlinks `open_clarification.md` → THEN journals `auto_mad_resolve` (auto_mad.py:234-243); `mad_sign_phase` `write_record`s → THEN journals (auto_mad.py:159-173). An exception between the mutation and the journal (e.g. `clar_dir.relative_to(repo_root)` raising on a repo_root form/symlink mismatch at :237, or an `OSError` from `append_with_seq_alloc`) leaves the STOP resolved on disk with NO `auto_mad_resolve` audit entry → breaks the "every mad-resolution is journaled & reversible by 4.12" invariant (FR23). Competing fixes (journal-before-unlink with idempotent double-entry on retry vs. resume-time reconciliation) affect the 4.12 reverse contract → human intent required. (blind+edge)
- [x] [Review][Patch applied 2026-06-22] `validate_signoff` raises `SignoffError` (⊂ `SdlcError`, NOT OSError/ValueError) → escapes the `except (OSError, ValueError)` in `maybe_mad_resolve_stop` → an un-auto-signable phase (e.g. artifact hash drift caught during validation) crashes the whole `run_auto_loop` instead of halting gracefully; fix = catch `SignoffError`/`SdlcError` so it falls through to `finish_halted` [src/sdlc/engine/auto_mad.py:341] (edge+blind, HIGH)
- [x] [Review][Patch applied 2026-06-22] `deferred-work.md` CR4.10-W3 "ADDRESSED" + "(historical)" bullets dropped their backtick code-spans on edit — renders "resolves by ⎵⎵ and journals ⎵⎵" and "—⎵⎵ halts on the lexicographically-first" (missing `stop.target` / `auto_mad_resolve` / `stop_clarification.py` spans); restore them [_bmad-output/implementation-artifacts/deferred-work.md:817-818] (auditor, LOW)
- [x] [Review][Defer] `allow_mock` accepted but ignored (`_ = allow_mock`) — mirrors sibling `run_auto` (auto.py:68); ADR-029 mock-acknowledgement gate deferred across the whole `/sdlc-auto*` surface under EPIC-4-DEBT-AUTO-REAL-DISPATCH [src/sdlc/cli/auto.py:143] — deferred, pre-existing (blind, LOW)
- [x] [Review][Defer] Test DRY — `_write_phase3_ready_project` vs `_write_phase3_ready_unsigned_signoffs` (~30 near-identical lines, differ by one call) + a near-verbatim failing-dispatch fixture duplicated across unit + integration (loop-level `registry`/`runtime` args unused) [tests/integration/test_auto_mad.py:978,1008,1081] — deferred, non-blocking test maintainability (blind, LOW)
- [x] [Review][Defer] `_phase_from_signoff_target` derives phase from the first path segment only and raises bare `ValueError` on drift/unmappable target; the resolve failure halts with only a `log.warning`, no audit diagnostic entry [src/sdlc/engine/auto_mad.py:53-58] — deferred, edge robustness (blind+edge, LOW)

---

## Change Log

- 2026-06-22: bmad-code-review (3 adversarial layers — Blind Hunter / Edge Case Hunter / Acceptance Auditor) — all C1–C10 + D1–D5 SATISFIED. Triage: 1 decision-needed + 2 patch applied, 3 defer, ~19 dismissed. **Applied:** P1 `maybe_mad_resolve_stop` now catches `SignoffError` (⊂ `SdlcError`) → hash-drift/un-patchable-draft halts gracefully instead of crashing `run_auto_loop`; P2 restored dropped backtick code-spans in `deferred-work.md` CR4.10-W3; D1→patch reordered both resolvers to **journal BEFORE the un-fire mutation** (`resolve_clarification`: resolution.md → journal → unlink; `mad_sign_phase`: journal → write_record) + `_rel_to_repo` helper so the audit target never raises mid-sequence (FR23 audit-completeness under failure). **Deferred:** CR4.11-W1 (`allow_mock` ignored, mirrors `run_auto`), CR4.11-W2 (test DRY), CR4.11-W3 (`_phase_from_signoff_target` diagnostic gap). Full pytest **3759 passed / 4 skipped / 1 xfailed**; ruff + mypy --strict clean. Status stays `review` — review→done close-out reserved for post-merge per project ceremony (code uncommitted).
- 2026-06-22: dev-story implementation complete — mad-mode auto-resolution (`auto_mad.py`, loop seam, `/sdlc-auto-mad`, ADR-028 `auto_mad_resolve`); 15 new tests; full pytest 3759 passed; freeze 7/7; status → review.
- 2026-06-22: T0 decisions resolved — D1(a)+D1(c) full 2A.12 validate→write path with generate_signoff_md guard for AWAITING_SIGNOFF; D2(a) distinct `/sdlc-auto-mad` CLI entrypoint; D3(a) `resolution.md` artifact; D4(a) resolve-and-continue; D5(a) watchdog `reason` mad-mode marker. Inherited debt cited (not fixed): EPIC-4-DEBT-AUTO-REAL-DISPATCH, EPIC-4-DEBT-AUTO-BRAINSTORM-REAL-SIGNAL, CR4.6-W2, CR4.2-W3. CR4.10-W3 marked addressed in deferred-work.md (C7).
- 2026-06-22: Story drafted (create-story) — the **Layer-4 convergence point** and penultimate node of the critical-path spine (`4.1 → 4.2 → 4.10 → 4.11 → 4.12`). Authored after verifying the Layer-4 precondition (**all of Layer 2 (4.2–4.9) + 4.10 `done` + merged**; `stop_registry`/the 7 triggers + `engine/auto_brainstorm.py` + `signoff/` validate/write/states frozen on `main`; freeze 7/7) and every load-bearing seam first-hand via 4 parallel research subagents + direct source reads: the journal-kind headline correction (**`auto_mad_resolve`** pre-listed in `projection.py:46` + a test, NOT epics' `mad_resolution` — C1), the no-standalone-`sign()` reality → reuse `validate_signoff → write_record` with a seeded `ai-mad-mode` draft (C2), the frozen `SignoffRecord` StrictModel (C3), the 7 frozen trigger_ids + check_stop priority order (C4), the `auto_loop.py:349-358` interception seam (C5), the non-existent option-1 extractor + net-new resolution artifact + `open_clarification.md`-removal-un-fires-STOP (C6), the CR4.10-W3 correlate-by-`stop.target` hand-off (C7), the `cli/auto.py:69-77` mock-only guard `/sdlc-auto-mad` inherits (C8), the watchdog `reason` distinguish seam (C9), and the engine module boundary + POSIX `io_primitives` + zero-new-wire-format constraints (C10). Surfaced 10 binding ground-truth corrections (C1–C10) and 5 decisions (D1 mad-sign seam → reuse 2A.12; D2 distinct `/sdlc-auto-mad` entrypoint; D3 net-new `resolution.md` artifact; D4 resolve-and-continue; D5 watchdog `reason` marker). Status: ready-for-dev.
