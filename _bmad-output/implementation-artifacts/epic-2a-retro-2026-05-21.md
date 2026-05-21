# Epic 2A Retrospective — Phase Orchestration Mechanics

**Project:** SDLC-Framework
**Epic:** 2A — Phase Orchestration Mechanics
**Retrospective Date:** 2026-05-21
**Facilitator:** Amelia (Developer)
**Project Lead:** Vuonglq01685
**Status:** Epic 2A → DONE from story perspective; conditionally production-ready PENDING prep sprint completion
**Format:** Two-part — (1) Epic Review (2) Next-Epic Preparation
**Preceding retro:** `epic-1-retro-2026-05-09.md`

---

## 1. Epic Summary

| Metric | Value |
|---|---|
| Stories completed | 20 / 20 (100%) — incl Story 2A.0 E2E harness precursor added per Epic 1 retro action A3 |
| Duration | 2026-05-10 → 2026-05-19 |
| Final test count | ~2,331 passed / 4 skipped / 18 xfailed / 1 xpassed (per 2A.16 review log) |
| Test delta vs Epic 1 | +1,217 tests (~109% increase from 1,114 baseline) |
| Coverage (pyproject `--cov-fail-under`) | 85 (CLAUDE.md still declares ≥90% — discrepancy ratified for resolution in prep sprint) |
| Wire-format snapshot count | 5 (unchanged from Epic 1.21 lock per ADR-024) |
| New Pydantic StrictModel contracts (all private, non-snapshotted) | 9 (`_TaskEntry`, `_EpicEntry`, `_StoryEntry`, `SignoffRecord`, `ArtifactRef`, `_SignoffMdDraft`, `_SpecialistManifest`, `_Verification`, `_AgentRunLine`) |
| New journal `kind` strings on open-string posture | ~11 (`hooks_trusted`, `signoff_recorded`, `signoff_invalidated`, `artifact_verified`, `bootstrap_completed`, `story_broken_into_tasks`, `task_stage_advanced`, `task_stage_failed`, `replan_invalidated`, `dispatch_attempt`, `stop_trigger_raised`) |
| Total review patches applied | ~250+ across 20 stories |
| Outlier patch volume (top 3) | 2A.7 = 32 patches · 2A.1 = 31 patches + 2 spec amends · 2A.5 = 24 patches |
| D-decisions resolved | ~25+ (peak: 2A.7 = 6 · 2A.5 = 5 · 2A.6 = 5) |
| EPIC-2A-DEBT tickets opened | 12+ named tickets + ~100 line-items in `deferred-work.md` |
| Worktree branches used | `epic-2a/2a-N-<slug>` across Layers 1 → 7 |
| Quality gates | ruff format/check · mypy --strict · pytest · pre-commit · mkdocs --strict · wireformat snapshots |
| ADRs added | ADR-025 (StrictModel default) · ADR-026 (TDD-first + chunked review) · ADR-027 (E2E test framework strategy) — all Accepted |

### Deliverables Shipped (Phase Orchestration Surface)

- **CLI/slash commands:** `/sdlc-start`, `/sdlc-research`, `/sdlc-verify`, `/sdlc-epics`, `/sdlc-stories`, `/sdlc-signoff`, `/sdlc-ux`, `/sdlc-architect`, `/sdlc-bootstrap`, `/sdlc-break`, `/sdlc-task` (5-stage TDD pipeline), `/sdlc-next`, `sdlc replan`, `sdlc hook-check`, `sdlc trust-hooks`
- **Engine modules:** `workflows/` (YAML loader + schema validation + disjoint-writes static check), `agents/registry` (manifest validation), `dispatcher/` (core + retry + postconditions), `signoff/` (4-state machine + hasher + records + validator), `hooks/` (payload + runner + builtin/{naming_validator, phase_gate}), `claude_hooks/pre_tool_use`, `engine/replan.py`, `telemetry/runs`
- **Specialist stubs (Phase 3, deferred to Epic 2B for real prompts):** test-author, code-author, code-reviewer, code-bootstrapper, task-breaker
- **E2E harness:** Tier-1 CLI goldens + Tier-2 MockAIRuntime pipeline (Story 2A.0) — reused by 17 of 20 stories
- **New ADRs:** ADR-024 wire-format-frozen invariant verified (5 snapshots preserved); ADR-025 StrictModel inheritance gate adopted; ADR-026 TDD-first commit ordering enforced; ADR-027 E2E framework strategy

### Participants

- Alice (Product Owner) — Epic 2B sponsorship, FIRST EXTERNAL SHIP gatekeeper
- Charlie (Senior Dev) — dispatcher/signoff/replan author, review-patch lead
- Dana (QA Engineer) — Tier-1/Tier-2 harness owner, anti-tautology receipt enforcer
- Elena (Junior Dev) — `_epic_story_models`, `_next_resolver`, CLI surface implementor; graduated from pair-programming (solo'd 2A.18)
- Winston (Architect) — ADR-024/025/026 steward, StrictModel + canonicalization gate
- Vuonglq01685 (Project Lead) — Retrospective decision authority

---

## 2. What Went Well — Top 5 Wins

1. **TDD-first + anti-tautology receipt enforced — Epic 1 retro Pattern 1 (placebo tests) systematically closed.** 8+ stories had receipt mandatory (2A.0, 2A.4×3, 2A.5, 2A.6×3, 2A.7, 2A.9, 2A.11, 2A.12, 2A.14, 2A.16 dual, 2A.17, 2A.18, 2A.19). Receipts caught real bugs — 2A.16 dual receipt split active-status polarity × seq-contiguity into separate assertions. Anti-tautology helpers from 2A.0 (`tests/e2e/_anti_tautology_helpers.py`) became the canonical mutation template reused by 2A.8 / 2A.9 / 2A.11.

2. **Wire-format invariant held: 5 snapshots preserved through 20 stories.** ADR-024 invariant verified on disk (`hook_payload.json`, `journal_entry.json`, `resume_token.json`, `specialist_frontmatter.json`, `workflow_spec.json`). All 9 new Pydantic StrictModel contracts marked private (`_TaskEntry`, `_EpicEntry`, `_StoryEntry`, `SignoffRecord`, `ArtifactRef`, `_SignoffMdDraft`, `_SpecialistManifest`, `_Verification`, `_AgentRunLine`) and explicitly NOT snapshotted. ADR-025 StrictModel inheritance adopted as default. Substrate proven drift-resistant by design, not by discipline.

3. **DAG 7-layer + worktree parallelization workflow proven (Actions A6 + A7 from Epic 1 retro).** Layer 3 (2A.6 + 2A.7), Layer 4 (2A.9 + 2A.10 + 2A.11), Layer 6 (2A.15 + 2A.16), Layer 7 (2A.17 + 2A.18 + 2A.19) all merged clean with linear merge sequence held. Sibling coordination notes assigned shared-file ownership (`agents/index.yaml`, `phase2_approved_repo` fixture helper) to first-merging story. Zero merge-conflict failures recorded.

4. **Reusable patterns emerged and compounded across stories:**
   - `phase1_compound_prompt_builder` from 2A.8 reused unchanged by 2A.11 + 2A.14 + 2A.15
   - `_X_pipeline.py` extraction pattern from 2A.11 (cli/epics 554→331 LOC, cli/stories 644→385) reused by 2A.13 (`_ux_pipeline`), 2A.14 (`_architect_pipeline`), 2A.16 (`_break_pipeline`), 2A.17 (`_task_pipeline`)
   - `build_pre_write_hook_chain(repo_root, signoff_reader)` DI pattern from 2A.6 + 2A.7 closed `EPIC-2A-DEBT-PHASE-GATE-READ`, reused by 2A.8 / 2A.11 / 2A.13 / 2A.17
   - `PanelObserver` observer-DI pattern from 2A.3 fixed dispatcher kwarg explosion in 2A.8; reused by 2A.10 + 2A.13

5. **Chunked review (Action A2) universally adopted.** Every story shows review-A; 2A.11 shipped A → B+C; 2A.13 shipped A → B with 15 WB items; 2A.17 ran a full Round-2 after Round-1 inline conflation was detected. Decision-protocol (D1/D2/D3 option-labels — Action A5) used across all 20 stories. Three-layer adversarial review (Blind Hunter / Edge Case Hunter / Acceptance Auditor) caught hundreds of bugs that would otherwise ship silently.

### Additional Highlights

- **Elena graduated from pair-programming** — solo-shipped 2A.18 (`/sdlc-next`) at Layer 7. Action A4 (Charlie ↔ Elena pair) executed and closed.
- **D-decision counts dropped sharply Layer 6 → 7** (2A.16 = 0, 2A.18 = 0, 2A.19 = 0). Patterns stabilized.
- **Story-DAG (Action A6) followed exactly** — Layer references explicit in sprint-status.yaml; siblings declared with coordination notes.

---

## 3. What Did Not Go Well — Top 6 Patterns

### Pattern 1: Defer Work Accumulating Across Epics (Critical)

**Project Lead surfaced this concern as the top worry.** Sub-agent analysis confirmed the magnitude:

- Epic 2A opened **12+ named EPIC-2A-DEBT tickets** + **~100 CR##-W# line-items** in `deferred-work.md`
- **4 of 7 Epic 1 technical debt items remain open** (D3 EINTR retry, D4 pre-commit rev pin drift, D5 POSIX helper, D7 linter test-harness)
- Distribution at Epic 2A close: 5 BLOCKING for Epic 2B + 7 HIGH for Epic 2B + 15+ MEDIUM/LOW
- No process gate prevented debt accumulation; "track in deferred-work.md" is necessary but insufficient

**Root cause:** No debt-decay policy in CONTRIBUTING.md. Each epic opens debt freely; close-out is opportunistic, not enforced. Two epics now carrying the same root cause (atomic write race condition — Epic 1 D3 EINTR + Epic 2A WRITE-PRIMITIVE).

### Pattern 2: Systemic Repetition of Non-Atomic Write — 7 Stories Affected

`Path.write_text` used directly in 7 stories (2A.3, 2A.8, 2A.9, 2A.13, 2A.14, 2A.15, 2A.17). Each story flagged in review; each deferred the fix to a shared `engine/io_primitives.py` that was never built. Same root cause as Epic 1 D3 EINTR debt. Pattern shows "YAGNI gone wrong" — we declined to build the primitive at Epic 1 thinking 1-2 callsites, ended up with 7.

### Pattern 3: Process-Local Seq Allocation Race — 5 Stories Affected

`EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` cited by 2A.3 / 2A.8 / 2A.11 / 2A.14 / 2A.17. Cross-process journal append needs `journal.append_with_seq_alloc` with flock. Currently in-process only. Affects audit-chain consistency when worktrees run in parallel CI.

### Pattern 4: Review-Patch Volume Stayed High in Layer 1–3 Stories

Peak counts: 2A.7 = 32 patches + 21 deferred (W1-W21), 2A.1 = 31 patches + 2 spec amends, 2A.5 = 24 patches + 5 D-decisions, 2A.6 = 23 patches + 5 D-decisions. All four share root cause: large new surface area landing in same story. Layer 6-7 stories (2A.16+) dropped D-counts to 0 — pattern stabilization is real.

### Pattern 5: Code-Review Inline Conflation → Round-2 Required (2A.17 case study)

Story 2A.17 (`/sdlc-task` 5-stage TDD pipeline) ran code-review **inline with implementation in the same session**, leading to Round-2 review on the post-Round-1 tree catching 13 additional patches. Story 2A.0 had the same problem (also required Round-2 with 39 patches). Root cause: ADR-026 §1 receipt format does not enforce "fresh-context session" for review.

### Pattern 6: Coverage Gate Silently Degraded 90% → 85%

`pyproject.toml --cov-fail-under=85` vs CLAUDE.md ≥90%. Discrepancy noted in 2A.19 review as "out of scope". Epic 1 retro Win #1 was "quality gates applied at Day-1". Two epics later, the headline gate value is silently lower. Root cause: `EPIC-2A-DEBT-PREEXISTING-FAILURES-2026-05-11` quarantined 18 xfails in 2A.10; un-quarantining required closing the underlying bugs first, which never happened.

### Pattern 7: Specialist-Naming Drift Between Architecture and Code

Story 2A.15 ships `code-bootstrapper` while architecture roster declares `codebase-scaffolder`. Other Phase-3 specialists may have similar drift. Affects Epic 2B Story 2B.10 (Phase-3 specialist authoring). Needs architecture roster amendment ceremony before 2B.10.

### Pattern 8: LOC-Cap Erosion via `_is_loc_exempt`

6 stories added files to `_is_loc_exempt` after grazing the LOC budget (2A.7 signoff/records.py, 2A.8 cli/start.py 376 vs 250 + dispatcher/_panel_helpers.py 543, 2A.9 cli/research.py 458 vs 350, 2A.11 dispatcher/postconditions.py 694, 2A.16 run_break ~240, 2A.19 `noqa C901`). LOC discipline weakening; Epic 1 Pattern 3 (LOC-cap fights) now systemic.

### Pattern 9: Module-Boundary Erosion vs ADR-010 Thin-CLI

`cli.depends_on` widened in 2A.6 / 2A.7 / 2A.8 / 2A.11 / 2A.13 to include `dispatcher`, `workflows`, `specialists`, `signoff`, `runtime`, `workflows_yaml`. ADR-010 thin-cli intent under pressure. Needs either ADR amendment OR new `engine/` intermediary before Epic 2B specialist-authoring adds another wave.

---

## 4. Previous Retrospective Follow-Through (Epic 1 → Epic 2A)

| Epic 1 Retro Item | Status | Evidence |
|---|---|---|
| **A1** TDD-first MANDATORY | ⚠️ Partial | Explicit failures in 2A.6 / 2A.7 / 2A.9 / 2A.11 / 2A.13 (debts opened: `EPIC-2A-DEBT-TDD-COMMIT-ORDERING-2A.6`, `-2A.9`). 2A.14 + 2A.19 executed correctly. Discipline drifts under squash. |
| **A2** Chunked review (review-A/B/C) | ✅ Universal | Every story shows review-A; 2A.11 shipped A→B+C; 2A.17 ran full Round-2. Pattern entrenched. |
| **A3** E2E harness Tier-1 + Tier-2 | ✅ Shipped | 2A.0 delivered (28 e2e, 92.53% coverage). Adoption high — 2A.9 → 2A.19 added Tier-2 fixtures. |
| **A4** Charlie ↔ Elena pair-mentoring | ✅ Done | Elena solo'd 2A.18 — graduate confirmed. |
| **A5** D1/D2/D3 option-labels | ✅ Universal | Every story uses D-decision format. |
| **A6** Story-DAG mandatory | ✅ Followed | Layer 1→7 explicit in sprint-status; siblings declared. |
| **A7** Worktree-per-story | ✅ Adopted | `epic-2a/2a-N-<slug>` consistent; linear merge held. |
| **D1** Hypothesis canonicalization byte-stability | ✅ Closed | 2A.7 wove sampled_from property strategy. |
| **D2** Pydantic strict-mode + ADR-025 | ✅ Closed | StrictModel adopted across all new contracts. |
| **D3** EINTR retry for `_write_bytes` + journal | ❌ NOT closed | Still in deferred-work.md. Now BLOCKING Epic 2B (relates to WRITE-PRIMITIVE). |
| **D4** Pre-commit rev pin drift automation | ❌ NOT closed | No CI sync vs uv.lock check shipped. |
| **D5** POSIX-only module helper extraction | ❌ NOT closed | LOC-cap erosion in 2A is partially a consequence. |
| **D6** Tautological-test linter spike | ⚠️ Partial | Anti-tautology RECEIPT enforced (better outcome than linter heuristic). |
| **D7** Linter test-harness consolidation | ❌ NOT closed | Each new linter still copies pattern. |
| **DOC1–DOC4** ADRs + CONTRIBUTING.md updates | ✅ Done | ADR-024/025/026/027 published. CONTRIBUTING.md §1-§7 updated. |

**Summary:** 4/7 Epic 1 technical debt items remain open. D3 EINTR especially is now load-bearing for Epic 2B prep.

---

## 5. Significant Discovery — Epic 2B Implications

### NO epic re-planning required

ADR-024 5-snapshot invariant held. Wire-format frozen. Epic 2B story shapes (11 stories) remain valid.

### One spec amendment needed before 2B.8

`architecture.md` specialist roster reconcile — `code-bootstrapper` canonical (matches code); other Phase-3 specialists must be verified. Folded into Action A4.

### One ADR addition needed before 2B.1

ADR-028 — Journal `kind` taxonomy ratify. ~11 new kinds rode the open-string posture during Epic 2A; ADR-024 still valid (kind field is open `str`), but Epic 2B.3 conformance test + 2B.4 corpus test need an authoritative reference. Folded into DOC1.

### MockAIRuntime divergences enumerated (Epic 2B.3 input)

Confirmed divergences from Epic 2A reviews:
- MockAIRuntime does not write `agent_runs.jsonl` (breaks Phase-2 boundary postcondition `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK`)
- `_default_prompt_builder` returns `specialist.body` verbatim (Phase-1 hardening only covers structural defenses)
- MockMissError leaks resolved absolute `fixtures_dir` path
- `_AgentRunLine.schema_version=1` hardcoded and unfrozen
- `SDLC_USE_MOCK_RUNTIME=1` is the default (mock-on-in-production posture)

---

## 6. Action Items

### 6.1 Process Improvements (A1–A4)

| # | Action | Owner | Deadline | Success Criteria |
|---|---|---|---|---|
| **A1** | Debt-decay policy: CONTRIBUTING.md §7.5 — before Story N.1 of each epic, close ≥5 BLOCKING + ≥50% HIGH carry-forward debt + ALL open carry-forward debt from epic N-2. Audit table + 4-signoff gate. | Alice + Amelia | Before Story 2B.1 | Policy committed; CI gate checks debt budget; Epic 2B prep sprint validates first run |
| **A2** | ADR-026 amendment §1: code-review MUST run as fresh-context session AFTER implementation is committed and pushed. Inline-with-implementation = blocked by pre-commit hook checking commit-message tag `[fresh-context-review]`. | Amelia | Before Story 2B.1 | ADR updated; pre-commit hook added; CI verifies tag |
| **A3** | ADR-026 amendment §2: TDD-first commit ordering receipt format accommodates squash flows (signed-off-by tag preserving original commit sequence). | Amelia | Before Story 2B.1 | ADR updated; receipt format documented; first squashed Epic 2B PR validates |
| **A4** | Specialist roster freeze ceremony — reconcile architecture.md ↔ code naming. Architecture.md becomes canonical; deviations require ADR. | Winston + Alice | Before Story 2B.8 | 25-specialist list frozen in architecture.md; `docs/specialists-matrix.md` generated |

### 6.2 Technical Debt Closure (D1–D8) — pre-Story-2B.1

| # | Debt Item | Owner | Effort |
|---|---|---|---|
| **D1** | Close Epic 1 D3 + Epic 2A WRITE-PRIMITIVE → ship `engine/io_primitives.py` with atomic raw-text write + EINTR retry | Charlie | ~1 day |
| **D2** | Close PANEL-V1-PROCESS-LOCAL-SEQ → `journal.append_with_seq_alloc` with cross-process flock | Charlie | ~0.5 day |
| **D3** | Close PREEXISTING-FAILURES-2026-05-11 → triage 18 xfails (genuine bugs vs flakies); restore CLAUDE.md ≥90% coverage gate in pyproject.toml | Dana | ~1 day |
| **D4** | Close PHASE2-PROMPT-BOUNDARY-CHECK + SECURITY-INVARIANT → restore boundary postcondition for `sdlc-ux.yaml` once 2B.1 writes `agent_runs.jsonl` | Winston + Dana | ~0.5 day |
| **D5** | Close TASK-STATE-PROJECTION + NEXT-CONSUME-PROJECTION + REPLAN-DIRTY-PROJECTION → state.json journal projection | Charlie | ~1 day (P7) |
| **D6** | Close Epic 1 D4 (pre-commit rev pin drift) + D5 (POSIX helper) + D7 (linter test-harness) — carry-forward zero-out | Elena | ~1.4 days |
| **D7** | Close WIN32-RUNS-LOCK + SIGNOFF-FLOCK-CONCURRENCY — cross-platform lock primitive | Charlie | ~0.7 day |
| **D8** | Close BREAK-MANUAL-STATUS-FLIP — `/sdlc-break` writes `_StoryEntry.status='in-progress'` | Elena | ~0.3 day |

### 6.3 Documentation (DOC1–DOC3)

| # | Document | Owner | Deadline |
|---|---|---|---|
| **DOC1** | ADR-028 — Journal `kind` taxonomy ratify 11 new kinds + per-kind `after_hash` nullability table | Winston | Before Story 2B.1 |
| **DOC2** | ADR-029 — MockAIRuntime envelope semantics (`mock: true` flag in success envelope; `SDLC_USE_MOCK_RUNTIME` default flip plan; CLI `--allow-mock` gate) | Charlie + Dana | Before Story 2B.1 |
| **DOC3** | `docs/sprints/epic-2b-dag.md` — Mermaid DAG + parallelism layers + 4-signoff gate (per CONTRIBUTING §7) | Alice + Charlie | After prep sprint, before Story 2B.1 |

### 6.4 Team Agreements

- **(A)** No story enters Epic 2B before C1–C8 critical-path complete (debt-decay policy enforced)
- **(B)** Every Epic 2B story carries at least one Tier-1 E2E test
- **(C)** Pre-commit chain + fresh-context review tag must pass before push
- **(D)** Code review = fresh-context session; inline conflation = blocked
- **(E)** Specialist names canonical from architecture.md; deviations require ADR
- **(F)** Worktree-per-story preserved (proven at Layer 1 → 7 in Epic 2A)
- **(G)** Linear merge sequence on `main`; rebase + CI re-run after each merge
- **(H)** Journal `kind` taxonomy frozen via ADR-028 before 2B.4 corpus tests
- **(I)** `MockAIRuntime` default OFF in non-test contexts after C8 design lands

---

## 7. Epic 2B Preparation — Critical Path & Parallel Prep

### 7.1 Critical Path (must complete before Story 2B.1 worktree opens)

| # | Task | Owner | Estimate | Blocking |
|---|---|---|---|---|
| **C1** | Atomic raw-text write primitive (`engine/io_primitives.py`) — closes Epic 1 D3 + Epic 2A WRITE-PRIMITIVE | Charlie | ~1 day | All 7 affected stories · 2B.1 |
| **C2** | `journal.append_with_seq_alloc` cross-process flock — closes PANEL-V1-PROCESS-LOCAL-SEQ | Charlie | ~0.5 day | 2B.1 · 2B.3 conformance |
| **C3** | Triage 18 xfails → restore ≥90% coverage gate | Dana | ~1 day | All Epic 2B CI |
| **C4** | Phase-1/3 boundary line verification + Phase-2 NFR-SEC-3 reactivation prep | Winston + Dana | ~0.5 day | 2B.4 · 2B.5 |
| **C5** | Specialist roster amendment in architecture.md (canonical names) | Winston + Alice | ~0.3 day | 2B.8–2B.11 |
| **C6** | Update CONTRIBUTING.md §7.5 — debt-decay clause | Alice + Amelia | ~0.3 day | Epic 2B prep gate |
| **C7** | Amend ADR-026 — fresh-context review enforced via pre-commit | Amelia | ~0.3 day | All Epic 2B reviews |
| **C8** | `SDLC_USE_MOCK_RUNTIME` flip plan + `mock: true` envelope flag design doc | Charlie + Dana | ~0.5 day | 2B.1 ship readiness |

**Total critical:** ~4.4 days.

### 7.2 Parallel Prep (concurrent with Story 2B.1 worktree)

| # | Task | Owner | Estimate |
|---|---|---|---|
| **P1** | Close Epic 1 D4 — pre-commit rev pin drift CI check | Elena | ~0.5 day |
| **P2** | Close Epic 1 D5 — POSIX helper extraction; collapse `_is_loc_exempt` exemptions | Charlie | ~0.5 day |
| **P3** | Close Epic 1 D7 — linter test-harness consolidation | Elena | ~0.4 day |
| **P4** | Ratify journal `kind` taxonomy (DOC1 / ADR-028) — define `after_hash` nullability per kind | Winston | ~0.4 day |
| **P5** | Close WIN32-RUNS-LOCK + SIGNOFF-FLOCK-CONCURRENCY — cross-platform lock primitive | Charlie | ~0.7 day |
| **P6** | TDD-commit-ordering receipt format amendment for squash flows (ADR-026 §1) | Amelia | ~0.3 day |
| **P7** | Close TASK-STATE-PROJECTION + NEXT-CONSUME-PROJECTION + REPLAN-DIRTY-PROJECTION | Charlie | ~1 day |
| **P8** | Close BREAK-MANUAL-STATUS-FLIP | Elena | ~0.3 day |

### 7.3 Nice-to-Have (track only)

- LOC-cap exemption audit + `EPIC-2A-DEBT-POSTCONDITIONS-SPLIT`
- `SHARED-TIME` (`_now_ts` dedup dispatcher↔cli)
- `BYPASS-FLAG-WIRING` CLI flag exposure
- `BOOTSTRAP-HOOK-PARTIAL-ROLLBACK` (2A.15)
- `TASK-REJECTED-REWORK` (2A.17 CR17-W1)
- `RESEARCH-DEDUP-RACE` intra/cross-process
- `EPIC-2A-DEBT-CLI-*-LOC-CAP` exemption resolution
- Module-boundary ADR amendment vs ADR-010 thin-cli

### 7.4 Epic 2B Story → Epic 2A Dependency Map

| Epic 2B Story | Depends on Epic 2A | Critical Debt Blocker |
|---|---|---|
| 2B.1 ClaudeAIRuntime impl | 1.13 AIRuntime ABC · 2A.1 · 2A.2 · 2A.3 | WRITE-PRIMITIVE · PANEL-V1-PROCESS-LOCAL-SEQ · D3 EINTR |
| 2B.2 Min-version refuse | 2A.3 | (none) |
| 2B.3 Behavioral conformance | 2A.0 Tier-2 + 2A.13/14/15/17 | MockAIRuntime divergences ratified |
| 2B.4 Prompt-injection corpus | 2A.1 NFR-SEC-7 heuristics + boundary line | PHASE2-PROMPT-BOUNDARY-CHECK |
| 2B.5 Boundary-line presence test | All prompt builders | PHASE2-PROMPT-SECURITY-INVARIANT |
| 2B.6 Tool-safety contract | 2A.3 dispatcher | CLAUDE-HOOK-FAIL-CLOSED-V1.X |
| 2B.7 Threat-model docs | (docs-only) | (none) |
| 2B.8 Phase 1 specialists | 2A.8/9/10/11/12 | Specialist roster ratify |
| 2B.9 Phase 2 specialists | 2A.13/14 | Roster + `requires:` parser |
| 2B.10 Phase 3 specialists TDD pipeline | 2A.15/16/17 | TASK-REAL-TEST-EXECUTION + naming drift |
| 2B.11 Support specialists | 2A.3 synthesizer | 25-count verification |

---

## 8. Readiness Assessment

| Dimension | Status | Note |
|---|---|---|
| Stories completion | ✅ 20/20 done | sprint-status confirmed |
| Tests passing | ⚠️ 2,331 pass / 4 skip / 18 xfailed / 1 xpass | 18 xfails = DEBT (closed by D3) |
| Coverage | ⚠️ 85% pyproject vs ≥90% CLAUDE.md | Discrepancy resolved by D3 |
| Quality gates | ✅ All green | ruff / mypy --strict / pre-commit / mkdocs --strict / wireformat |
| Wire-Format v1 lock | ✅ 5 snapshots preserved | ADR-024 invariant held |
| Production deployment | N/A | Internal milestone; Epic 2B = FIRST EXTERNAL SHIP |
| Stakeholder acceptance | ✅ Confirmed | Project Lead approved "Stories done; conditionally production-ready pending prep sprint" |
| Codebase stability | ⚠️ Conditional | 7 stories have non-atomic write debt → race-condition window; D1 closes |
| Unresolved blockers | ⚠️ 5 BLOCKING + 7 HIGH + Epic 1 D3/D4/D5/D7 | Debt-decay policy (A1) enforces close before 2B.1 |
| Process discipline (Epic 1 retro follow-through) | ⚠️ 4/7 carry-forward debt open | A1 + D6 close |

---

## 9. Project-Lead Reflections (Vuonglq01685)

Three pass-forward priorities into Epic 2B:

1. **Worktree + DAG discipline** — proven at Layer 1 → 7; extend to Epic 2B. Pattern is "invisible-default" and should stay that way.
2. **Honest defer tracking + debt-decay policy** — top concern. Stop bleeding debt accumulation. Each epic prep sprint MUST close ≥X% of carry-forward debt. Codified as Action A1 in CONTRIBUTING.md §7.5.
3. **Chunked review + fresh-context discipline** — Round-2 of 2A.17 proved inline conflation is a real risk. ADR-026 amendment (Action A2 + A3) must stick.

Implicit but no longer needing evangelism: anti-tautology receipt format + Tier-1/Tier-2 harness. These have become habits, signal of maturity.

---

## 10. Next Steps

1. **Execute preparation sprint** (~4.4 days critical path + parallel)
   - C1–C8 must complete before Story 2B.1 worktree opens
   - P1–P8 run in parallel with Story 2B.1
   - Nice-to-have items tracked, not blocking

2. **Run Epic 2B sprint-planning session** (per Action A6) — produces `docs/sprints/epic-2b-dag.md` with Mermaid DAG, parallelism layers, and 4-signoff gate. Sequence: after prep sprint, before Story 2B.1 worktree, since prep cleanup may reshape 2B.3 / 2B.8–2B.11 stories.

3. **Publish ADRs:**
   - ADR-026 amendments §1 + §2 (DOC actions A2 + A3)
   - ADR-028 — Journal kind taxonomy (DOC1)
   - ADR-029 — MockAIRuntime envelope semantics (DOC2)

4. **Update CONTRIBUTING.md §7.5** — debt-decay clause (Action A1)

5. **Begin Epic 2B** when preparation sprint complete, ADRs published, debt-decay policy validates first run, and Epic 2B story-DAG approved per CONTRIBUTING.md §7.4 (4 signoffs in §8).

---

## 11. Closure

**Epic 2A: Phase Orchestration Mechanics — DONE from story perspective.**

20 stories shipped across ~10 days at Layer 1 → 7 parallel-worktree pace. 2,331 tests passing (incl 18 xfails to be closed in prep sprint). Five wire-format snapshots intact. Eleven new journal kinds rode the open-string posture (to be ratified in ADR-028). Nine new private StrictModel contracts (all non-snapshotted) prove ADR-024 invariant scales.

Pattern 1 (placebo tests from Epic 1) systematically closed via anti-tautology receipt enforcement. Pattern A6 + A7 (story-DAG + worktree parallelization from Epic 1 retro) proven at scale. Elena graduated from pair-programming.

**Top concerns surfaced by the Project Lead:**
- 12+ EPIC-2A-DEBT tickets + 4/7 Epic 1 carry-forward debt items still open
- Review-patch volume stayed high in Layer 1–3 stories (peak 32 at 2A.7)
- Coverage gate silently degraded 90% → 85%

All three are addressed by the prep sprint (C1–C8 + P1–P8 + D1–D8) and Action A1 (debt-decay policy in CONTRIBUTING.md §7.5).

**Conditionally production-ready: PENDING prep sprint completion.** Epic 2B (FIRST EXTERNAL SHIP) cannot begin until C1–C8 close and Epic 2B sprint-planning produces the DAG.

The team identified 4 process improvements, 8 technical debt closures, 3 documentation deliverables, and 9 team agreements that, addressed during the preparation sprint, position Epic 2B for safe FIRST EXTERNAL SHIP through real Claude Code.

---

*Retrospective document generated 2026-05-21. Saved to `_bmad-output/implementation-artifacts/epic-2a-retro-2026-05-21.md`.*
