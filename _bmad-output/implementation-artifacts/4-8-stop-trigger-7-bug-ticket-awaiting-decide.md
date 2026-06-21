# Story 4.8: STOP Trigger 7 — Bug Ticket Awaiting Decide

**Status:** review

**Epic:** 4 — Auto-Mode & Autonomous Execution (`/sdlc-auto`)
**Layer:** 2 (`docs/sprints/epic-4-dag.md` §3 — one of the 8-story STOP-trigger fan-out, batch 2)
**Worktree:** `epic-4/4-8-stop-bug-awaiting` (owner: Charlie, DAG §5:196)
**Critical Path:** **OFF** the critical path (the critical path is `4.1 → 4.2 → 4.10 → 4.11 → 4.12`, DAG §4). 4.8 is a leaf STOP trigger that plugs into the registry seam 4.2 froze.
**Depends on (all on `main`):** **4.1** — the frozen `engine/auto_loop.py` loop + the `State.auto_loop_status`/`stop_reason` fields (done, `2cc8ce4`). **4.2** — the **real** registry seam: `engine/stop_registry.py` (`_ORDERED_TRIGGERS`, `register`, `check_all`), the generic loop halt-finalizer `auto_loop._finish_halted_on_stop_trigger`, the projection fold for `kind=stop_triggered`, and the `OpenClarificationTrigger` structural template (done, close-out `e539d5f`). Epic 1 substrate — `state.projection.project_from_journal` (1.12), `MockAIRuntime` (1.13). **Does NOT depend on Epic 3 (adopt).**
**Consumed by (downstream):** **4.11** mad-mode must **HALT** on this STOP (it is one of "the other 5" non-clarification triggers mad-mode does not auto-resolve, DAG §5:199); **5.19** renders this STOP as a dashboard banner (epics.md:2819 family).

> **Layer-2 precondition — VERIFIED.** 4.8 is **not** Story N.1, so the CONTRIBUTING §7.4 epic-entry gate does **not** re-apply (epic-4 is `in-progress`; the gate cleared at 4.1). The Layer-2 precondition is **"4.1's loop + 4.2's registry seam frozen on `main`"** — **SATISFIED**: 4.1 is `done` (merged-before-done R1/R2 passed, flip `2cc8ce4`); 4.2 is `done` (close-out `e539d5f`, merged-before-done R1/R2 satisfied; the registry seam was explicitly **frozen on `main`** in 4.2's review before the 4.3–4.9 batch branches). `engine/stop_registry.py`, `engine/auto_loop.py`, `engine/stop_clarification.py`, `state/projection.py` are on `main`; `freeze_wireformat_snapshots --check` is **7/7**. **4.8 is purely additive against that frozen seam** (see C2/C-correction).

---

## Story

As a **user managing in-flight bug tickets**,
I want **the loop to halt when a bug ticket is in `awaiting-decide` state (created during execution, requires triage)**,
so that **auto-mode pauses for explicit triage instead of either silently ignoring or auto-resolving bugs** (PRD **FR21** trigger 7 [prd.md:764 family]; the loop's resume/perf contracts **NFR-REL-5** + **NFR-PERF-6** are inherited from 4.1 and must be preserved).

---

## Acceptance Criteria

> **READ FIRST — binding ground-truth corrections + scope boundaries (verified first-hand against the codebase 2026-06-18). These prevent the most likely implementation disasters. Do not skip.**
>
> **(C1) SCOPE — 4.8 DETECTS + HALTS only; it never creates, writes, triages, or resolves a bug ticket.** 4.8 detects the **presence** of a bug ticket `.claude/state/bugs/<id>.yaml` whose `state` field equals `awaiting-decide`, and halts the auto-loop with the registry's generic halt-emit. It does **NOT** write that file (the WRITE side — who *creates* bug tickets during execution — is **out of 4.8's scope**, undefined in `src/` today, and noted below), and it does **NOT** transition the bug to `accepted`/`rejected` (the human/triage flow does — epics.md:2222–2225). This is the exact detect-only posture of 4.2's C1: 4.8 reads a `.claude/state/<thing>` marker and folds a halt; it owns neither end of the lifecycle.
>
> **(C2 / C-correction) THE REGISTRY MECHANISM ALREADY EXISTS — 4.8 is PURELY ADDITIVE.** Unlike 4.2 (which *built* the real registry from the `NotImplementedError` stub), 4.8 lands **after** the seam is frozen on `main`. The full halt machinery is done: the ordered registry (`stop_registry._ORDERED_TRIGGERS` + `check_all`, first-fired), the generic loop halt-finalizer `auto_loop._finish_halted_on_stop_trigger` (`auto_loop.py:153–178`) which already journals `kind=stop_triggered {trigger, target, reason?, correlation_id}` for **any** fired decision, the `check_stop` post-dispatch call site (`auto_loop.py:286`), and the projection fold (`projection.py` already lists `stop_triggered` in `_KNOWN_KINDS`, the dispatch set, and `_fold_auto_loop_status` → `("halted", payload["trigger"])`). **So 4.8 is exactly: (1) ONE new file `src/sdlc/engine/stop_bug_awaiting.py` (a single `StopTrigger` class, mirroring `OpenClarificationTrigger`), (2) ONE appended line in `stop_registry._ORDERED_TRIGGERS`, (3) a unit test, (4) a 4-cell integration test.** **ZERO edits** to `auto_loop.py`, `projection.py`, `stop_triggers.py`, or `ADR-028`. A vanilla pure-disk trigger requires no machinery build. This is the **closest structural sibling to 4.2** — a pure-disk presence+field check.
>
> **(C3) REUSE the existing `stop_triggered` journal kind + `bug_awaiting_decide` trigger — NO new journal kind, NO ADR-028 edit.** Per **ADR-028** (`docs/decisions/ADR-028-journal-kind-taxonomy.md:79`), the `stop_triggered` row already covers *"auto-loop halt when a Layer-2 STOP trigger fires; payload `trigger`, `target`, optional `reason`, `correlation_id`"* — it is the generic kind for **every** Layer-2 trigger, registered by 4.2. 4.8's trigger returns `StopDecision(fired=True, trigger="bug_awaiting_decide", target=<bug_id>, reason=<summary>)` and the loop's existing `_finish_halted_on_stop_trigger` journals it as `kind=stop_triggered, trigger=bug_awaiting_decide, target=<bug_id>, reason=<summary>`. Do **NOT** add a new taxonomy row, do **NOT** touch ADR-028 (grep-confirmed: the row exists). `grep -rn bug_awaiting_decide src/ tests/` → **zero hits** today; 4.8 introduces the trigger_id but reuses the kind.
>
> **(C4) THE 4-FIELD `StopDecision` IS FROZEN — encode `bug_id` in `target`, `summary` in `reason`.** `StopDecision` has exactly 4 fields: `fired, trigger, target, reason` (`stop_triggers.py:16–23`, `@dataclass(frozen=True)`, **byte-stable** for Layer 2). The epics AC names a richer shape — `trigger=bug_awaiting_decide, bug_id=<id>, summary=<short>` (epics.md:2215). **Do NOT add fields.** Map: `trigger="bug_awaiting_decide"`, **`target=<bug_id>`** (the `<id>` from the filename stem), **`reason=<summary>`** (the bug's short summary, read from the yaml). The projection fold reads `payload["trigger"]` → `stop_reason="bug_awaiting_decide"`; the journal `target`/`reason` carry the bug id + summary for the user-facing message + the 5.19 dashboard. This is the same envelope 4.2 used (`target` carried the clarification path); 4.8 carries the bug id there instead because the AC's identifier is the id, not a path.
>
> **(C5) ZERO new wire-format contracts — the bug-ticket schema is INTERNAL STATE (Epic-4 Decision D1, RATIFIED).** Per DAG §5 + **Decision D1** (`docs/sprints/epic-4-dag.md:248–271`, ratified 2026-06-09, option (a)): *"the bug-ticket schema is internal state, not a frozen wire-format contract."* So 4.8 must **NOT** add a `StrictModel` in `src/sdlc/contracts/`, **NOT** add a `tests/contract_snapshots/v1/` snapshot, and **NOT** run a snapshot-regeneration ceremony. `freeze_wireformat_snapshots --check` stays **7/7**. Parse the yaml as opaque internal state with `yaml.safe_load`; read the minimal fields (see **D1**) defensively. (The DAG explicitly notes the Epic-5 dashboard *may* revisit freezing it later — but **not in 4.8**.)
>
> **(C6) NET-NEW GROUND — nothing reads or writes `.claude/state/bugs/` in `src/` today.** `grep -rniE "awaiting.decide|state/bugs|bug_awaiting|bug_id" src/ tests/` → **zero hits** (re-confirmed first-hand). 4.8 is the **first** story to reference `.claude/state/bugs/`, exactly as 4.2 was the first to reference `.claude/state/clarifications/`. Follow the established `.claude/state/<thing>` convention (cf. `signoff/records.py` → `.claude/state/signoffs`, 4.2 → `.claude/state/clarifications/`). The path is named only in the planning docs (epics.md:2213, DAG §5:196, §6 risk row :241). 4.8 **defines the minimal read-side bug-ticket shape** (see **D1**) — keep it minimal and internal.
>
> **(C7) FAIL-SOFT — missing dir is "no bug" (not an error); malformed yaml is "not awaiting" (skip, don't crash).** Mirror 4.2's missing-dir pattern exactly: a missing `.claude/state/bugs/` directory on a greenfield project → `StopDecision(fired=False)`, **never** an error (epics.md:2218–2220). A `*.yaml` that fails `yaml.safe_load` (or is not a mapping, or lacks `state`) → **skip it, treat as not-awaiting**, do not raise — a single corrupt ticket must not crash the auto-loop. Wrap parse in `try/except (OSError, yaml.YAMLError)` and tolerate non-dict / missing-key shapes.
>
> **(C8) MODULE BOUNDARY + LOC + first-fired + unused `state` param.** New code lives in `engine/` — `engine` MAY import `state`/`journal`/`ids`/`errors`/`config` and the third-party `yaml`, but MUST NOT import `cli`/`dashboard` (`scripts/module_boundary_table.py`; gate `scripts/check_module_boundaries.py`). The trigger needs only `pathlib`, `yaml`, `sdlc.engine.stop_triggers.StopDecision`, and `sdlc.state.model.State`. Every new `src/` file is **≤ 400 LOC** (NFR-MAINT-3 gate). `check_stop` returns the **FIRST fired** decision in `_ORDERED_TRIGGERS` order (`stop_registry.py:35–38`); 4.8 appends its trigger after the existing entries (story-order; see C9/D3). The trigger is a **pure-disk** scan, so `check(self, *, repo_root, state)` **accepts but does not consult** `state` (`_ = state`), identical to `OpenClarificationTrigger` (C7-of-4.2). Tests run under `SDLC_USE_MOCK_RUNTIME=1` (autouse, `tests/conftest.py`); the trigger is runtime-immaterial but the loop-integration cells inherit the posture.
>
> **(C9) SHARED-FILE MERGE POINT — `_ORDERED_TRIGGERS` is the one line every sibling touches.** Stories 4.3–4.8 each **append one line** to `stop_registry._ORDERED_TRIGGERS` (`stop_registry.py:13`). This is the single shared edit across the 8 parallel Layer-2 worktrees → the merge/rebase contention point. **Rebase `epic-4/4-8-stop-bug-awaiting` on up-to-date `main` before merge** and re-run the full suite (CONTRIBUTING §3 linear-merge + §4.4). Add only the one tuple line + the import — do not reorder or touch sibling entries. The autouse `_reset_stop_trigger_registry` fixture (`tests/conftest.py:64`) already isolates the runtime `register()` path; the static `_ORDERED_TRIGGERS` tuple needs no fixture.

---

**AC1 — Positive trigger: a bug ticket awaiting decide halts the loop (FR21 trigger 7).** *(epics.md:2213–2216)*
**Given** the auto-loop running and a bug ticket file `.claude/state/bugs/<id>.yaml` with `state: awaiting-decide`,
**When** the next STOP-check runs,
**Then** the loop halts with `trigger=bug_awaiting_decide`, **`bug_id=<id>`** (encoded in `StopDecision.target` — C4), **`summary=<short>`** (encoded in `StopDecision.reason` — C4),
**And** the journal records `kind=stop_triggered, trigger=bug_awaiting_decide, target=<id>, reason=<summary>` (via the **existing** generic `_finish_halted_on_stop_trigger` — C2/C3, no auto_loop edit),
**And** `state.json` reflects `auto_loop_status: halted, stop_reason: bug_awaiting_decide` (via the **existing** projection fold — C2, no projection edit),
**And** the user-facing surface shows the bug summary and tells them to triage (`/sdlc-bug-triage <id>` or equivalent — carried by `target`/`reason`; the CLI/banner rendering itself is downstream, **not** 4.8's surface).

**AC2 — Negative case: no awaiting-decide bug → continue.** *(epics.md:2218–2220)*
**Given** no bug tickets in `awaiting-decide` state — including a **missing** `.claude/state/bugs/` directory on a greenfield project (treat as "no bug", **never** an error — C7), and including bugs whose `state` is anything other than `awaiting-decide` (e.g. `accepted`, `rejected`, `open`),
**When** the loop iterates,
**Then** STOP-check for trigger 7 returns `StopDecision(fired=False)`,
**And** the loop continues to the next ready item (no `stop_triggered` entry for `bug_awaiting_decide`, no halt).

**AC3 — Resume: triaged → loop continues (preserves NFR-REL-5).** *(epics.md:2222–2225)*
**Given** the loop halted on this trigger and the user triages the bug — transitions its `state` to `accepted` or `rejected` (and runs `sdlc scan`),
**When** I re-run `/sdlc-auto`,
**Then** the loop resumes; STOP-check for trigger 7 now returns `fired=False` (the yaml's `state` no longer equals `awaiting-decide`),
**And** processing continues from the disk state at resume time (pure-function-of-disk — the resume reads the re-triaged filesystem, no in-memory continuation),
**And** the **downstream** consequence is noted but **out of 4.8 scope**: if `accepted`, a later story's loop can spawn fix work; if `rejected`, the bug is closed — 4.8 only observes that the ticket is no longer `awaiting-decide` and stops halting on it.

**AC4 — 4-cell test matrix gate (the merge gate).** *(epics.md:2227–2229)*
**Given** the 4-cell test matrix,
**When** `tests/integration/stop_triggers/test_stop_bug_awaiting.py` runs (the `tests/integration/stop_triggers/` dir already exists from 4.2 — reuse it; do not recreate `__init__.py`/conftest),
**Then** all 4 cells pass: **(1) positive** (awaiting-decide bug present → halt + `stop_triggered` journal entry with `trigger=bug_awaiting_decide`), **(2) negative** (no awaiting-decide bug → continue, no halt), **(3) termination state** (`project_from_journal(journal)` yields `auto_loop_status="halted"`, `stop_reason="bug_awaiting_decide"` via the existing fold), **(4) resume** (bug re-triaged to `accepted`/`rejected` → `check()` now `fired=False`, loop continues),
**And** an **N>1** case: multiple `awaiting-decide` bugs → deterministic **first-by-lexical-id** choice (mirror 4.2's D4; see **D2**), so resume is stable for NFR-REL-5.

**AC5 — Quality gate green + TDD-first (CONTRIBUTING §1/§2/§5).**
Quality gate green per §1 (ruff format/check, `mypy --strict src/`, **FULL** pytest suite — not just the new files — coverage ≥ 87 operational floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` **7/7 unchanged**, module-boundary + LOC ≤ 400). TDD-first (§2): the trigger unit suite + the 4-cell integration matrix are the **failing-first commit**, **RED before** `engine/stop_bug_awaiting.py` + the `_ORDERED_TRIGGERS` append land, visible in `git log --reverse` (`test(4.8)` → `feat(4.8)`). Material decisions surfaced as **D1/D2** (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the behavior suite — `BugAwaitingDecideTrigger` existence+field detection + `StopDecision` shape + the 4-cell loop-halt matrix + the registry-fires assertion (`check_stop` picks up the appended trigger) + the N>1 lexical-id determinism. All RED before `engine/stop_bug_awaiting.py` and the one-line `_ORDERED_TRIGGERS` append land.

- [x] **(§5) T0 — Resolve D1/D2** (minimal read-side bug-ticket shape · multiple-awaiting-bug ordering) and record the choices in the Change Log **before writing code**. Recommended answers are pre-filled in §Decisions; confirm or override.
- [x] **(AC1–AC4, §2) Write failing trigger + matrix tests FIRST.**
  - `tests/unit/engine/test_stop_bug_awaiting.py` — instantiate `BugAwaitingDecideTrigger()`; assert `isinstance(trigger, StopTrigger)` (mirror `test_stop_clarification.py:26–27`); on a `tmp_path` repo, `check(repo_root=tmp_path, state=State())` returns `StopDecision(fired=True, trigger="bug_awaiting_decide", target="<id>", reason="<summary>")` when `.claude/state/bugs/<id>.yaml` has `state: awaiting-decide`; `fired=False` when the dir is **missing**, when **empty**, when the bug's `state` is `accepted`/`rejected`/`open`, and when a yaml is **malformed/unreadable** (C7 fail-soft — assert no raise). Add the **N>1 lexical-id** determinism test (D2). RED.
  - `tests/integration/stop_triggers/test_stop_bug_awaiting.py` — the **4-cell matrix** driving `run_auto_loop` (mirror `test_stop_clarification.py` exactly — reuse `_write_phase3_ready_project`, `_bootstrap_journal`, `_mock_runtime`, `SpecialistRegistry({})`, `AsyncMock` dispatch, `max_iterations=1`): **(1)** awaiting-decide bug → `AutoLoopResult(halted=True, stop_reason="bug_awaiting_decide")` + a `stop_triggered` journal entry whose `payload["trigger"] == "bug_awaiting_decide"` (read via `iter_entries`); **(2)** no awaiting-decide bug → loop continues, no `stop_triggered`; **(3)** termination → `project_from_journal(journal).auto_loop_status == "halted"`, `stop_reason == "bug_awaiting_decide"`; **(4)** resume → rewrite the yaml `state: accepted`, re-run, `check_stop(...).fired is False` and `resumed.halted is False`. RED.
  - A registry-integration assertion: with the trigger appended to `_ORDERED_TRIGGERS`, `check_stop(repo_root=tmp_path, state=State())` fires `trigger="bug_awaiting_decide"` when an awaiting-decide bug exists (proves the append wired the trigger into the ordered list). RED.
- [x] **(AC1, AC2, C1, C4, C7, C8) Implement the trigger** — `src/sdlc/engine/stop_bug_awaiting.py`: class `BugAwaitingDecideTrigger` with `trigger_id = "bug_awaiting_decide"` and `def check(self, *, repo_root: Path, state: State) -> StopDecision`. Module-level `_BUGS_DIR_REL = ".claude/state/bugs"` (mirroring `_CLARIFICATIONS_DIR_REL`), `_AWAITING_STATE = "awaiting-decide"`. Missing dir → `fired=False`. Iterate `sorted(bugs_dir.glob("*.yaml"))` (lexical, deterministic — D2); for each, `try` `yaml.safe_load(path.read_text(...))`, `except (OSError, yaml.YAMLError): continue`; tolerate non-`dict`; if `data.get("state") == "awaiting-decide"` → return `StopDecision(fired=True, trigger=self.trigger_id, target=path.stem, reason=<summary from data, see D1>)` for the **first** such file. No match → `fired=False`. `_ = state` (C8). ≤ 400 LOC.
- [x] **(AC1, C2, C9) Append the trigger to the registry** — in `src/sdlc/engine/stop_registry.py`: add `from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger` and append `BugAwaitingDecideTrigger()` as **one** new line in `_ORDERED_TRIGGERS` (story-order, after the existing entries — D2). **No other edit** to the registry; keep sibling entries untouched (C9). This is the **only** shared-file change in 4.8.
- [x] **(C2, C3) Confirm — do NOT edit `auto_loop.py`, `projection.py`, `stop_triggers.py`, or `ADR-028`.** The generic halt path (`_finish_halted_on_stop_trigger`), the `check_stop` call site, the `stop_triggered` projection fold, and the ADR-028 `stop_triggered` row all already handle a fired `bug_awaiting_decide` decision. Verify by running the cell-1/cell-3 tests green **without** touching those files. If a test fails, the bug is in the trigger or the append — **not** in the frozen machinery.
- [x] **(AC3, D2) Resolution + multiplicity** — the resume cell is pure-fn-of-disk: rewrite the yaml `state` (or delete the file) and re-run; `check()` returns `fired=False`. The N>1 case picks the lexically-first `*.yaml` by id (D2) — deterministic for NFR-REL-5; remaining awaiting-decide bugs re-trigger on subsequent runs after the first is triaged.
- [ ] **(AC5, §1) Full quality gate to green** — ruff, `mypy --strict src/`, pytest (**full** suite, not just the new files — the 4.1/4.2 lesson: a partial run hides pre-existing failures), coverage ≥ 87, pre-commit, `mkdocs build --strict`, freeze **7/7**, module-boundary + LOC ≤ 400. Run `scripts/check_module_boundaries.py src/sdlc/engine/stop_bug_awaiting.py` explicitly. *(Partial: ruff + mypy on new module PASS on win32; full pytest blocked — POSIX-only conftest import.)*
- [x] **(§3) Worktree** — branch `epic-4/4-8-stop-bug-awaiting` off up-to-date `main`; **rebase before merge** (C9 — `_ORDERED_TRIGGERS` is the shared-file merge point shared with siblings 4.3–4.7).
- [ ] **(§4) Chunked review** — review-A/B/C via the `code-review` workflow once status is `review` (use a different LLM context). Route the trigger's fail-soft parse (C7) + the `bug_id`/`summary` field mapping (C4) through review-B. **Run the full suite during review** (CONTRIBUTING §4.4 / the 4.2 post-patch lesson — layer reviews only diff the change).

---

## Dev Notes

### Substrate map (verified 2026-06-18 — exact symbols; wrong names break the build)

| Concern | Symbol / path | Notes |
|---|---|---|
| **frozen STOP result** | `engine.stop_triggers.StopDecision` (`stop_triggers.py:16–23`) | `@dataclass(frozen=True)`; exactly `fired: bool`, `trigger/target/reason: str \| None`. **Byte-stable** (C4). 4.8 returns `StopDecision(fired=True, trigger="bug_awaiting_decide", target=<bug_id>, reason=<summary>)`. **Do NOT add `bug_id`/`summary` fields.** |
| **frozen STOP Protocol** | `engine.stop_triggers.StopTrigger` (`:26–32`) | `@runtime_checkable`; `trigger_id: str` + `check(self, *, repo_root: Path, state: State) -> StopDecision`. 4.8's class must satisfy `isinstance(...)` (assert it, mirror `test_stop_clarification.py:26–27`). |
| **structural template (COPY THIS)** | `engine.stop_clarification.OpenClarificationTrigger` (`stop_clarification.py:14–41`) | 4.8 is the closest sibling. Same shape: module-level `_..._DIR_REL` constant, `is_dir()` guard → `fired=False`, `sorted(...)` deterministic scan, `candidates[0]`, `_ = state`. 4.8 adds a **field check** (`state == "awaiting-decide"`) + a `yaml.safe_load` parse where 4.2 only checked filename presence. |
| **ordered registry (APPEND HERE)** | `engine.stop_registry._ORDERED_TRIGGERS` (`stop_registry.py:13`) | The shared-file merge point (C9). Append `BugAwaitingDecideTrigger()` as one line; add the import. `check_all` (`:33–39`) iterates in order, first-fired. `register()`/`_extra_triggers` are the runtime path (not used by 4.8). |
| **loop halt-finalizer (DO NOT EDIT — reuse)** | `engine.auto_loop._finish_halted_on_stop_trigger` (`auto_loop.py:153–178`) | **Generic** — journals `kind=stop_triggered {trigger, target, reason?, correlation_id}` for any fired decision via `_append_stop_triggered`; rebuilds state. `check_stop` consulted at `auto_loop.py:286` (post-dispatch) → on fire calls this finalizer (`:288–295`). A vanilla trigger needs **ZERO** `auto_loop.py` edits (C2). |
| **projection fold (DO NOT EDIT — reuse)** | `state.projection._fold_auto_loop_status` (`projection.py:84–101`), `_KNOWN_KINDS` (`:40–52`), dispatch (`:147`) | `stop_triggered` is **already** listed in all three (added by 4.2). Folds `stop_triggered` → `("halted", payload["trigger"])` via `_halt_reason_from_stop_payload` (`:69–81`). A `trigger="bug_awaiting_decide"` payload folds to `stop_reason="bug_awaiting_decide"` with **no edit** (C2/C4). |
| **yaml parse (established idiom)** | `yaml.safe_load(...)` + `except yaml.YAMLError` | PyYAML is a confirmed `src/` dependency (`config/project.py:6,62–63`; `signoff/records.py:27,262`; `adopt/imported_metadata.py:76–78`). Use `yaml.safe_load`, wrap in `try/except (OSError, yaml.YAMLError)`, tolerate non-`dict` (C7). |
| **state fields (exist)** | `state.model.State.auto_loop_status: str = "idle"`, `stop_reason: str \| None = None` | Added by 4.1, folded by 4.2. **Reuse — do not re-add.** |
| **timestamp** | `ids.clock.now_rfc3339_utc_ms() -> str` | Used inside the loop's `_finish_halted_on_stop_trigger` — 4.8 never calls it directly (the loop journals on 4.8's behalf). |
| **NOT 4.8's** | `dispatcher._panel_helpers._emit_stop_trigger` → `kind=stop_trigger_raised` | The 2A.3 agent-failure seam — **Story 4.6** consumes it. **Different kind** (`stop_trigger_raised` ≠ `stop_triggered`), different owner. Do not touch. |
| **bug surface (new)** | `.claude/state/bugs/<id>.yaml` with `state: awaiting-decide` | **No `src/` reader/writer today** (grep-confirmed, C6). Follows the `.claude/state/<thing>` convention (cf. `.claude/state/signoffs`, `.claude/state/clarifications/`). 4.8 is the first to reference it. |

### The bug surface — what exists vs what 4.8 does

- **Nothing in `src/` reads or writes `.claude/state/bugs/` today** (verified — `grep -rniE "awaiting.decide|state/bugs|bug_awaiting|bug_id" src/ tests/` → zero hits). 4.8 is net-new ground, exactly as 4.2 was for `.claude/state/clarifications/`. The path is established only in planning docs (epics.md:2213, DAG §5:196, §6 risk row :241).
- **The WRITE side (who creates bug tickets) is OUT of 4.8's scope** and undefined in `src/` today. The epics frame bugs as *"created during execution"* (epics.md:2208) — a future story / agent flow writes the `awaiting-decide` ticket. 4.8 **detects + halts** only (C1). Note this explicitly so the dev does not invent a writer.
- **Triage (the resolver) is the human / a downstream flow**: the user transitions `state` → `accepted` or `rejected` and runs `sdlc scan` (epics.md:2222–2225). 4.8 only observes that the ticket's `state` is no longer `awaiting-decide`. The `accepted`→spawn-fix-work and `rejected`→close consequences are **out of 4.8 scope** (note them per AC3).
- Detection = **`state == "awaiting-decide"` in `.claude/state/bugs/*.yaml`**, parsed safely. The `<id>` is the filename **stem** (`path.stem`), carried as `StopDecision.target`; the `<summary>` is read from the yaml, carried as `StopDecision.reason` (C4).

### The minimal net-new read-side bug-ticket shape (read D1 before implementing)

4.8 is the **first** story to read `.claude/state/bugs/<id>.yaml`, so it **defines** the minimal read-side shape. Per **D1 (recommended)** the trigger reads exactly:
- **`<id>`** — the filename stem (`path.stem`), not a yaml field. → `StopDecision.target`.
- **`state: str`** — the discriminator; halt iff `state == "awaiting-decide"`. The **only** required field.
- **`summary: str`** (optional) — short human-readable bug summary. → `StopDecision.reason`. Fall back to a stable default (e.g. `None` or `"bug <id>"`) when absent, so a summary-less ticket still halts (the discriminator is `state`, not `summary`).

This shape is **internal state, NOT a wire-format contract** (C5 / Epic-4 D1): no `StrictModel`, no snapshot, freeze stays 7/7. Keep parsing defensive (C7): a yaml that is not a mapping, or lacks `state`, is treated as "not awaiting" (skip), never a crash.

### Why 4.8 is purely additive (the C2 consequence — re-read before opening any frozen file)

4.2 had to *build* the registry mechanism from a `NotImplementedError` stub, land the `stop_triggered` journal kind, and extend the projection fold. **4.8 lands after all of that is frozen on `main`.** The generic `_finish_halted_on_stop_trigger` already journals any fired decision; the projection already folds `stop_triggered`; ADR-028 already lists the kind. **A vanilla pure-disk trigger therefore touches exactly two production surfaces: the new trigger file and one appended tuple line.** If you find yourself editing `auto_loop.py`, `projection.py`, `stop_triggers.py`, or `ADR-028`, stop — you are re-doing 4.2's work and breaking the frozen seam. The cell-1 (halt + journal) and cell-3 (projection → halted) tests must go green **without** any edit to those files; that is the proof the seam is reused, not rebuilt.

### Test idioms (reuse from 4.2 — do not invent)

- **Unit shape:** copy `tests/unit/engine/test_stop_clarification.py` structure — a `_write_*` helper, `isinstance(..., StopTrigger)`, fired/not-fired/missing-dir/empty-dir cases, and the N>1 lexical-id determinism test (`test_multiple_clarifications_picks_lexically_first_id`). Add a **malformed-yaml fail-soft** case (write garbage to a `*.yaml`, assert `check()` does not raise and returns the right decision — C7) and a **wrong-state** case (`state: accepted` → `fired=False`).
- **Integration 4-cell:** copy `tests/integration/stop_triggers/test_stop_clarification.py` wholesale — `_write_phase3_ready_project`, `_bootstrap_journal`, `_mock_runtime`, `SpecialistRegistry({})`, `AsyncMock(return_value=None)` dispatch, `max_iterations=1`, `iter_entries`, `project_from_journal`. Swap the clarification-writer for a `_write_awaiting_bug(repo_root, bug_id, summary=...)` helper writing `.claude/state/bugs/<id>.yaml` with `yaml.safe_dump({"state": "awaiting-decide", "summary": ...})` (or a hand-written yaml string).
- **Mock-runtime autouse:** `tests/conftest.py` sets `SDLC_USE_MOCK_RUNTIME=1` suite-wide; the trigger is pure-disk (runtime-immaterial) but the loop cells inherit it.
- **Registry isolation:** the autouse `_reset_stop_trigger_registry` fixture (`tests/conftest.py:64`) snapshots/restores the runtime `_extra_triggers`. 4.8 uses the **static** `_ORDERED_TRIGGERS` append (not `register()`), so no fixture interaction — but the canary `test_registry_isolated_after_registration` will count `_ORDERED_TRIGGERS` including 4.8's new entry (expected; that test compares against `_ORDERED_TRIGGERS` itself, so it stays correct).
- **Integration dir already exists:** `tests/integration/stop_triggers/` (with `__init__.py` + conftest) was created by 4.2 — **reuse it**, do not recreate the wiring.

### Project Structure Notes

- **New files:** `src/sdlc/engine/stop_bug_awaiting.py` (the trigger); `tests/unit/engine/test_stop_bug_awaiting.py`; `tests/integration/stop_triggers/test_stop_bug_awaiting.py`.
- **Modified:** `src/sdlc/engine/stop_registry.py` (one import + one appended `_ORDERED_TRIGGERS` line — the **only** shared-file edit, C9). **Nothing else** in `src/` or `docs/`.
- **NOT modified (frozen seam — C2/C3/C5):** `src/sdlc/engine/auto_loop.py`, `src/sdlc/state/projection.py`, `src/sdlc/engine/stop_triggers.py`, `docs/decisions/ADR-028-journal-kind-taxonomy.md`, `src/sdlc/contracts/*`, `tests/contract_snapshots/v1/*`.
- **Conventions:** every `src/` file ≤ 400 LOC; absolute `from sdlc.X import Y` imports only (relative imports inside `src/sdlc/<module>/` are gate-forbidden, Architecture §1075); `engine` never imports `cli`/`dashboard` (C8).

### References

- Epic + ACs: `_bmad-output/planning-artifacts/epics.md:2205–2229` (Story 4.8 + the 4 BDD ACs); 4-cell convention `:2227–2229`.
- Frozen seam (consume; do not edit): `src/sdlc/engine/stop_triggers.py:16–32` (StopDecision/StopTrigger), `src/sdlc/engine/stop_registry.py:13,33–39` (`_ORDERED_TRIGGERS` append point + `check_all`), `src/sdlc/engine/auto_loop.py:153–178,286–295` (generic halt-finalizer + call site), `src/sdlc/state/projection.py:40–52,69–101,147` (the `stop_triggered` fold — already wired).
- Structural template: `src/sdlc/engine/stop_clarification.py` (the sibling trigger to mirror); 4.2 story `_bmad-output/implementation-artifacts/4-2-stop-trigger-1-open-clarification.md` (the gold standard + the registry-seam freeze in its Review Findings, incl. CR4.2-W3 inherited halt-stickiness).
- Journal taxonomy (reuse, no edit): `docs/decisions/ADR-028-journal-kind-taxonomy.md:79` (the `stop_triggered` row already covers Layer-2 triggers).
- Requirements: `_bmad-output/planning-artifacts/prd.md:764` family (FR21 trigger 7); NFR-REL-5 / NFR-PERF-6 (inherited from 4.1).
- DAG / decisions: `docs/sprints/epic-4-dag.md` §3 (layers `:129`), §5 (worktree `:196`), §6 risk row (`:241` bug-ticket internal-state), **Decision D1** (`:248–271`, zero new wire-format contracts — bug schema is internal state).
- yaml idiom: `src/sdlc/config/project.py:62–63`, `src/sdlc/signoff/records.py:262`, `src/sdlc/adopt/imported_metadata.py:76–78` (`yaml.safe_load` + `except yaml.YAMLError`).
- NOT 4.8's: `src/sdlc/dispatcher/_panel_helpers.py` (`stop_trigger_raised` → 4.6 — different kind).

---

## Decisions Needed

- **D1 — The minimal read-side bug-ticket shape (4.8 is the first reader, so it defines it).** Nothing in `src/` reads `.claude/state/bugs/<id>.yaml` today (C6); 4.8 must decide which fields the trigger reads. Constraint: internal state, NOT a wire-format contract (C5 / Epic-4 D1) — so no `StrictModel`, no snapshot.
  - **(a) Read the minimum: `<id>` = filename stem, `state` = the only required field (halt iff `== "awaiting-decide"`), `summary` = optional human string for the user message.** Parse with `yaml.safe_load`, tolerate non-`dict`/missing-key (fail-soft, C7). `summary` absent → fall back to `None`/`"bug <id>"` (the discriminator is `state`, not `summary`, so a summary-less ticket still halts). Smallest internal surface, matches the AC's `bug_id`/`summary` exactly, leaves any richer schema to the writer-story / Epic-5 dashboard. **(Recommended.)**
  - **(b) Define a fuller schema now** (`id`, `state`, `summary`, `severity`, `created_at`, ...) and validate it. Over-reaches 4.8's detect-only scope, invents fields no AC requires, and risks contradicting whatever the (out-of-scope) writer-story chooses. Rejected — YAGNI.
  - **(c) Require `summary` (halt only on well-formed tickets).** A ticket missing `summary` would not halt → a real awaiting-decide bug could be silently skipped, violating AC1's intent. Rejected — the discriminator must be `state` alone.

- **D2 — Multiple `awaiting-decide` bugs + the singular `bug_id` (`target`).** AC1 carries one `bug_id`/`summary` but N>1 awaiting-decide tickets are possible. NFR-REL-5 (pure-fn-of-disk) requires a **deterministic** choice.
  - **(a) Halt on the first by lexical `<id>` ordering (`sorted(bugs_dir.glob("*.yaml"))`); `target` = that id, `reason` = that summary.** Deterministic across runs (stable resume), matches the singular `bug_id` AC, smallest surface, mirrors 4.2's D4 exactly. Remaining awaiting-decide bugs re-trigger on subsequent runs after the first is triaged. **(Recommended.)**
  - **(b) Enumerate all** — add an `all_bug_ids` payload list for the 5.19 dashboard. Exceeds the singular AC, adds payload surface, and the dashboard story can derive it from disk itself. Defer to 5.19 unless a panel reviewer wants it now.

- **Registry append position (sub-decision of C9).** 4.8 appends its trigger to `_ORDERED_TRIGGERS` in **story order** (after the existing entries). First-fired ordering only matters when two triggers could fire on the same disk state; a bug-awaiting STOP and an open-clarification STOP are independent surfaces, so position is not semantically load-bearing here — but keep it **story-ordered and reviewable** (C9), not reordered, to minimize sibling merge contention.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

Composer (bmad-dev-story)

### Debug Log References

- D1 resolved: option (a) — minimal read-side shape (`id`=stem, `state` required, `summary` optional with fallback `"bug <id>"`).
- D2 resolved: option (a) — first by lexical `<id>` via `sorted(bugs_dir.glob("*.yaml"))`.
- TDD-first: unit + integration test files authored before production trigger/registry append.
- Local gate: ruff check/format PASS; mypy --strict on `stop_bug_awaiting.py` PASS. Full pytest/pre-commit/mkdocs/freeze **not runnable on win32 host** (POSIX-only `io_primitives` blocks conftest import; Docker daemon unavailable). POSIX CI verification required before merge per CONTRIBUTING §1.

### Completion Notes List

- Implemented `BugAwaitingDecideTrigger` — pure-disk scan of `.claude/state/bugs/*.yaml`, halt when `state == awaiting-decide`, maps `bug_id`→`target` and `summary`→`reason` (C4).
- Appended trigger to `_ORDERED_TRIGGERS` in story order (C9); zero edits to frozen seam files (`auto_loop.py`, `projection.py`, `stop_triggers.py`, ADR-028).
- Unit suite: protocol satisfaction, positive/negative/malformed-yaml/wrong-state/N>1 lexical determinism, registry integration via `check_stop`.
- Integration suite: 4-cell matrix (positive halt, negative continue, projection termination, resume after triage to `accepted`).
- Branch: `epic-4/4-8-stop-bug-awaiting`.

### File List

- `src/sdlc/engine/stop_bug_awaiting.py` (new)
- `src/sdlc/engine/stop_registry.py` (modified — import + one `_ORDERED_TRIGGERS` append)
- `tests/unit/engine/test_stop_bug_awaiting.py` (new)
- `tests/integration/stop_triggers/test_stop_bug_awaiting.py` (new)

---

## Change Log

- 2026-06-21: **bmad-code-review (fresh-context, 3 adversarial layers @ Opus-4.8)** — 0 violated binding constraints; frozen seam C2 byte-untouched (verified). 1 decision + 2 patches + 4 deferred + 7 dismissed (see Review Findings). **CR4.8-P1** (HIGH) fixed: added `UnicodeDecodeError` to the yaml-read except tuple so a non-UTF-8 bug file fails soft instead of crashing the unguarded post-dispatch `check_stop` (+fail-soft unit test). **CR4.8-P2** (LOW) fixed: empty/whitespace `summary` now falls back to `bug <id>` (+blank-summary unit test). Patched logic verified by standalone behavioral proof (win32 pytest blocked by POSIX-only `io_primitives` — CR4.8-W1). ruff + mypy --strict + module-boundary + LOC(49≤400) green. **CR4.8-D1** resolved → committed tests-first (`test(4.8)` RED → `feat(4.8)` GREEN). Deferred CR4.8-W1..W4 logged to deferred-work.md; **green POSIX CI is a hard blocker before `review→done`**.
- 2026-06-21: dev-story implementation — D1a/D2a ratified; TDD-first unit + 4-cell integration tests; `BugAwaitingDecideTrigger` + registry append landed on branch `epic-4/4-8-stop-bug-awaiting`. Status: review (POSIX full gate pending CI).
- 2026-06-18: Story drafted (create-story) — STOP trigger 7 (bug ticket awaiting-decide), a **purely additive** Layer-2 leaf that plugs into the registry seam **4.2 froze on `main`** (close-out `e539d5f`). Authored after the Layer-2 precondition was verified first-hand: **4.1 + 4.2 `done` and merged to `main`**, the registry seam (`stop_registry._ORDERED_TRIGGERS`, the generic `auto_loop._finish_halted_on_stop_trigger`, the `stop_triggered` projection fold, the ADR-028 `stop_triggered` row) all present and frozen, freeze 7/7. Confirmed net-new ground: `grep -rniE "awaiting.decide|state/bugs|bug_awaiting|bug_id" src/ tests/` → zero hits (4.8 is the first to reference `.claude/state/bugs/`). Surfaced 9 binding ground-truth corrections (C1 detect-only scope; C2 the C-correction — purely additive, zero machinery build; C3 reuse the `stop_triggered` kind + no ADR edit; C4 the 4-field `StopDecision` — `bug_id`→`target`, `summary`→`reason`, no new fields; C5 zero new wire-format / internal-state per Epic-4 D1; C6 net-new `.claude/state/bugs/` ground; C7 fail-soft missing-dir + malformed-yaml; C8 module-boundary + LOC + first-fired + unused `state`; C9 the `_ORDERED_TRIGGERS` shared-file merge point) and 2 decisions (D1 minimal read-side bug schema, D2 multiplicity/lexical-id ordering) + a registry-append-position sub-decision. Status: ready-for-dev.

---

## Review Findings

> bmad-code-review fresh-context, 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) at Opus-4.8, 2026-06-21. 0 VIOLATED binding constraints — C2 frozen-seam byte-untouched (verified via `git diff`: `auto_loop.py`/`projection.py`/`stop_triggers.py`/`ADR-028`/`contracts/`/`contract_snapshots/v1/` all blank), C4/C7/C8 clean, every C1–C9 + D1a/D2a + AC1–AC4 mapped to real code+tests. 1 decision, 2 patches, 4 deferred, 7 dismissed.

### Decision-needed

- [x] **[Review][Decision] CR4.8-D1 — TDD-first commit ordering unprovable while uncommitted** — **RESOLVED 2026-06-21 → option (a):** committed tests-first (`test(4.8)` RED → `feat(4.8)` GREEN), provable in `git log --reverse`; see Change Log. — AC5 / CONTRIBUTING §2 mandate `test(4.8)` RED → `feat(4.8)` GREEN visible in `git log --reverse`, but `git log --grep=4.8` is empty and all three new files are untracked (`??`) — the entire change sits in the working tree, so the mandated ordering cannot be audited. Recurs CR4.2–4.7-W1. Options: **(a)** commit tests-first now (`test(4.8)` then `feat(4.8)`) to make the ordering provable before merge [recommended]; **(b)** defer to the 4.8 close-out commit ceremony (commit-msg gates `check_story_merged_before_done.py` + `check_fresh_context_review_tag.py` enforce R1/R2 at `review→done`). Surfaced by Acceptance Auditor (F1, HIGH-process).

### Patches

- [x] **[Review][Patch] CR4.8-P1 — `UnicodeDecodeError` uncaught in yaml read → crashes the post-dispatch STOP check** [src/sdlc/engine/stop_bug_awaiting.py:29] — `path.read_text(encoding="utf-8")` raises `UnicodeDecodeError` (a `ValueError` subclass, **not** `OSError`) on a non-UTF-8 `*.yaml`; `except (OSError, yaml.YAMLError)` does not catch it, so it propagates out of `check()` through the **unguarded** `check_stop` call site (`auto_loop.py:286`, no try/except) and aborts the auto-loop iteration. `BugAwaitingDecideTrigger` is the first STOP trigger to do a raw `read_text` in the post-dispatch check, so it is uniquely exposed; the sibling `AgentFailedTrigger` (`stop_agent_failed.py:93-100`) deliberately fails-open per the documented NFR-REL posture ("must never crash the post-dispatch STOP check"). Realistic given the project's documented Windows cp1252 history. **Fix:** add `UnicodeDecodeError` to the caught tuple → `except (OSError, UnicodeDecodeError, yaml.YAMLError): continue`; add a fail-soft unit test (write invalid UTF-8 bytes, assert no raise + `fired=False`). Surfaced by Blind Hunter (M) + Edge Case Hunter (HIGH).

- [x] **[Review][Patch] CR4.8-P2 — empty/whitespace-only `summary` yields an empty operator `reason`** [src/sdlc/engine/stop_bug_awaiting.py:36-37] — `reason = summary if isinstance(summary, str) else f"bug {path.stem}"` accepts `summary: ""` (an empty string IS a `str`) and emits `reason=""` into the `stop_triggered` payload — an empty/unhelpful halt reason, contradicting D1's intent that a summary-less ticket still halts with a usable reason. (Projection reads `trigger`, not `reason`, so this is cosmetic, not a state break.) **Fix:** `reason = summary if isinstance(summary, str) and summary.strip() else f"bug {path.stem}"`; add a `summary: ""` unit case. Surfaced by Blind Hunter (L) + Edge Case Hunter (L).

### Deferred (tracked in deferred-work.md)

- [x] **[Review][Defer] CR4.8-W1 — RESOLVED 2026-06-21 (close-out 4.8)** [AC5] — green POSIX CI run **27894535510** ran the FULL gate on real POSIX hosts (8/8 ubuntu+macos × py3.10–3.13: full pytest + coverage ≥87 + freeze 7/7 + mkdocs --strict, all pass); PR #9 rebase-merged to main. The win32-asserted coverage/freeze are now **measured green**. _(Original deferral: only `ruff` + `mypy --strict` ran on win32; POSIX-only `io_primitives` blocks conftest import. Surfaced by Acceptance Auditor F2.)_
- [x] **[Review][Defer] CR4.8-W2 — Cross-trigger precedence untested** [src/sdlc/engine/stop_registry.py:_ORDERED_TRIGGERS] — deferred, cross-cutting (all 8 Layer-2 siblings). The trigger is appended last (first-fired); no test asserts behavior when `bug_awaiting_decide` AND another trigger could fire on the same disk state. The registry-append sub-decision ratified position as not semantically load-bearing (independent surfaces), so this is a registry-level coverage gap, not a 4.8 defect. Surfaced by Blind Hunter (H).
- [x] **[Review][Defer] CR4.8-W3 — `reason` carries unbounded/unsanitized `summary` content** [src/sdlc/engine/stop_bug_awaiting.py:36-37] — deferred, minor hardening. `summary` flows verbatim (no length cap / newline strip) into the journal payload; the sibling `AgentFailedTrigger` caps via `_truncate_error` (`_MAX_REASON_ERROR_LEN=200`). Low risk (internal repo state, spec'd as "short"). Surfaced by Blind Hunter (L).
- [x] **[Review][Defer] CR4.8-W4 — `.yml` extension not scanned** [src/sdlc/engine/stop_bug_awaiting.py:27] — deferred, writer-contract alignment. `glob("*.yaml")` misses a `bug-001.yml`; 4.8 defines the read convention as `.yaml` (per epics.md/DAG), and the writer is out of scope/undefined, so `.yml` support is YAGNI now — but the (future) writer-story must emit `.yaml`. Surfaced by Blind Hunter (L) + Edge Case Hunter (M).

### Dismissed (noise / handled elsewhere — 7)

- `trigger=self.trigger_id` "conflation" — the established convention every sibling follows (`AgentFailedTrigger`, `OpenClarificationTrigger`); not a defect.
- Silent skip on malformed/unreadable yaml without logging — spec C7 explicitly mandates skip-don't-crash; matches sibling fail-soft; these triggers have no logger by design.
- First-match hides additional awaiting-decide bugs — ratified D2a (remaining bugs re-trigger on subsequent runs after the first is triaged).
- Lexical (not chronological) ordering, `bug-10` < `bug-2` — D2a chose `sorted(glob)` for deterministic stable resume (NFR-REL-5), not urgency; all awaiting bugs eventually surface.
- `_ = state` discard "smell" — spec-mandated C8 (pure-disk trigger; identical to `OpenClarificationTrigger`).
- A directory named `<x>.yaml` matched by glob — correctly handled (`IsADirectoryError` ⊂ `OSError`, caught); explicit `is_file()` guard is stylistic.
- `sorted(glob)` materialization perf — negligible single short scan (NFR-PERF-6); Acceptance Auditor (F3) flagged no action.
