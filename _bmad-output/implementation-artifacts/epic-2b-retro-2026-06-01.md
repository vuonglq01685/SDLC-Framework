# Epic 2B Retrospective — AI-Native Runtime & Specialist Authoring

**Date:** 2026-06-01
**Facilitator:** Amelia (Senior Software Engineer)
**Project Lead:** Vuonglq01685
**Status:** Complete · all 11 stories `done` · retrospective `done`
**Predecessor retro:** `epic-2a-retro-2026-05-21.md`

---

## 1. Epic Summary & Metrics

Epic 2B is the **first external ship**: it moved the framework from mock-only to **real Claude
dispatch behind a safety boundary**, and authored the specialist roster across all phases.

| Metric | Value |
|--------|-------|
| Stories completed | **11 / 11 (100%)** |
| Structure | 4 DAG layers · critical path `2B.1 → 2B.3 → 2B.10 → 2B.11` |
| Tests passing | 2832 → 2840 → **2894** (growing through authoring stories) |
| Coverage | **88.10%** at 2B.11 (operational floor 87; aspirational 90 parked as `EPIC-2B-DEBT-COVERAGE-90`) |
| Review intensity | **2B.6: 157 raw findings**; 2B.3: 102 (7 decisions D1–D7) — heaviest to date |
| Production incidents | 0 (framework, not a deployed service; but first real-dispatch path) |
| Quality gate | Green on `main` (2B.11 review patches landed at `fb49ee9`) |

**Stories:** 2B.1 ClaudeAIRuntime/subprocess · 2B.2 min-version refuse-to-start · 2B.3 Mock-vs-Claude
conformance · 2B.4 prompt-injection corpus · 2B.5 boundary-line static check · 2B.6 tool-safety
contract tests · 2B.7 threat-model docs · 2B.8/9/10/11 author Phase-1/2/3/support specialists.

## 2. Participants

Amelia (Senior Software Engineer, facilitator) · Winston (System Architect) · John (Product Manager) ·
Mary (Business Analyst) · Paige (Technical Writer, threat-model docs) · Sally (UX Designer, specialist
UX track) · Vuonglq01685 (Project Lead).

## 3. What Went Well (all four endorsed by Project Lead)

1. **First external ship.** Real Claude dispatch with a working safety boundary; default flipped to
   mock-off with an explicit `--allow-mock` gate on 9 commands (ADR-029, 2B.1).
2. **The debt-decay gate caught its own defects.** The A1 policy authored in the 2A retro, on first
   strict run, exposed two broken gates (Gate A `≥5` unreachable; Gate C self-contradicting). ADR-033
   + ADR-035 fixed them *before* they could block 2B.1 — strongest signal a prior lesson was internalized.
3. **Adversarial review caught claimed-but-missing tests.** 2B.11 review-B caught a three-way
   name-match test the story *claimed* but had not written; review-C caught a matrix-pin overclaim.
4. **TDD-first + anti-tautology receipts matured into reusable technique.** From naive string-mutation
   (rejected 2B.4 P2) → monkeypatch-the-production-symbol → negative fixtures reused across 2B.5/6/8/11.

## 4. Challenges & Growth Areas (all four endorsed by Project Lead)

**Root cause (one, two altitudes): "claim outran evidence."**

1. **Spec-vs-reality divergence — 8/11 stories.** Create-story briefs were systematically optimistic:
   `subprocess.run` impossible for SIGTERM→SIGKILL (2B.1), nonexistent frontmatter fields
   `phase`/`role`/`boundary_line` (2B.8/9/10/11), `api-architect` vs real `api-designer` (2B.9), corpus
   layout `attacks/` vs real `user_text/`+`workflow_yaml/` (2B.7), stale `≥23,≤27` count gate (2B.10/11).
   Dev-time grep verification was mandatory and load-bearing.
2. **"Done" outran `main`.** 2B.9/2B.10 were marked `done` but never merged to `main`; the 2B.11
   capstone had to commit siblings' review patches, rebase, and FF-merge before it could branch.
3. **Claimed-but-missing tests.** Completion claims outran git reality (2B.10 AC9; 2B.11 review-B/C).
4. **Debt riding multiple epics.** EPIC-1 D4/D5/D7 now on their third epic as open MED; coverage sits
   at 87 while CLAUDE.md still claims ≥90; A3/P6 squash-receipt was silently dropped.

## 5. Key Insights

- One process fix attacks all four pains: **tighten the belief→evidence join** at spec, status, test,
  and debt boundaries.
- A correction in one story propagating forward as "Previous-Story Intelligence" works
  (the "builder rejects bodies containing `BOUNDARY_LINE`" invariant, carried 2B.8→2B.9→2B.10→2B.11).
- High review intensity concentrated exactly where risk did (2B.6/2B.3, dispatcher + nonce + projection).

## 6. Previous-Retro (Epic 2A) Follow-Through — ~15/20 closed (75%); every BLOCKING item closed

| Commitment | Status | Evidence |
|------------|--------|----------|
| A1 Debt-decay policy + CI gate | ✅ | CONTRIBUTING §7.5; self-corrected via ADR-033 + ADR-035 before 2B.1 |
| A2/C7 Fresh-context review hook | ✅ | ADR-026 §4 + commit-msg hook, in live use |
| A3/P6 Squash-flow receipt format | ❌ | No §2 amendment — "TDD drift under squash" risk still open |
| A4/C5 Specialist roster freeze | ✅ | ADR-030 + matrix; amended at 2B.11 (band ≥39/≤45) |
| C1 Atomic write primitive | ✅ | ADR-031; killed write-race root cause surviving 2 epics (17 callsites) |
| C3 Coverage gate | ⏳ | gate 85→87 only; CLAUDE.md still says ≥90 |
| EPIC-1 D4/D5/D7 | ❌ | open MED, riding into a third epic |

**Wins:** debt-decay policy fired and self-corrected; cross-epic write-race finally killed; fresh-context
review hard-enforced. **Misses:** A3 squash receipt dropped; coverage still 87 not 90; old MED debt
reclassified rather than closed.

## 7. Next Epic Preview — Epic 3: Brownfield Adopt (`sdlc init --adopt`)

8 stories (3.1–3.8): 3-pass orchestrator detect→symlink→stamp, rollback, idempotency, **source-untouched
invariant + mutation testing (3.7)**, brownfield-aware specialists (3.8). **Dependencies on Epic 2B are
satisfied on `main`** (`task-breaker` + `tdd-strategist` shipped; conformance harness merged; ADR-030
pre-absorbs `tdd-strategist`). The plan is **valid, not stale — but gated.** Substantive engineering
risk concentrates in 3.7 (novel mutation-testing harness + fixture corpus) and 3.8 (brownfield wiring);
most of Epic 3 is net-new design (`src/sdlc/adopt/`, `tests/fixtures/brownfield/`, detection heuristics,
new schemas, `legacy_code_globs` config), not deferred pull-forward.

## 8. Significant Discovery — MEDIUM (no epic re-plan required)

Epic 2B does **not** invalidate Epic 3's architecture (designed parallel on the Epic-1 substrate).
**No epic planning review session is required.** The discovery is **two hard prep gates** (missing
`epic-3-dag.md`; debt-decay Gate C red). Both are commissioned as critical-path prep below.

## 9. Decisions (CONTRIBUTING §5)

- **D1 — Coverage 87 vs CLAUDE.md ≥90 → RESOLVED (a):** reconcile CLAUDE.md to the honest operational
  floor (87) now; keep `EPIC-2B-DEBT-COVERAGE-90` open with a concrete target of closing **during Epic 3**
  (not prep-blocking). Stops the documentation drift immediately.
- **D2 — EPIC-1 D4/D5/D7 (MED) → RESOLVED (a):** schedule closure as owned work items in the Epic 3 prep
  sprint; stop the silent multi-epic ride.

## 10. Action Items

### Process (A-series)

| # | Action | Owner | Done when |
|---|--------|-------|-----------|
| A1 | Ground-Truth Recon gate in create-story/dev-story: grep-verify brief claims (frontmatter fields, file layout, registry/count, API/symbol names) against `src/` before implementing; log a "Stub-vs-Production" block on mismatch | John + Amelia | create-story checklist item; recon block standard for L3/L4 |
| A2 | Tighten "done": a story may not flip `done` while its branch is unmerged to `main` or has uncommitted review patches | Winston | CONTRIBUTING §3 amend + `check_story_merged_before_done.py` guard |
| A3 | "Test exists" becomes a mandatory review check: Acceptance Auditor grep-verifies every AC/task "test X added" claim against git at review time | Amelia + Mary | ADR-026 review workflow / §4 checklist item |
| A4 | Land the dropped A3/P6 squash-receipt — write ADR-026 §2 amendment + format, **or** formally retire it with rationale; no silent second drop | Amelia | ADR-026 §2 or a "Retired decisions" entry |

### Technical Debt (D-series)

| # | Item | Owner | Severity |
|---|------|-------|----------|
| D-CRIT | Close `EPIC-2A-D4-PHASE2-PROMPT-BOUNDARY-CHECK` (restore Phase-2 prompt-boundary postcondition + SECURITY-INVARIANT; flip in `debt-budget.yaml`) — clears Epic 3 Gate C | Winston | 🔴 CRITICAL PATH |
| D-COV | Reconcile CLAUDE.md to 87 floor now; close `EPIC-2B-DEBT-COVERAGE-90` to 90 during Epic 3 (per D1) | Amelia | HIGH |
| D-MIG | `EPIC-2B-DEBT-MIGRATE-PROCESS-LOCAL-SEQ-CALLSITES` (N-1) — slot into prep so Gate B does not regress | Winston | HIGH |
| D-OLD | EPIC-1 D4/D5/D7 — scheduled for prep closure (per D2) | Mary | MED |

## 11. Epic 3 Preparation Tasks (critical path before Story 3.1)

| # | Prep task | Owner | §7.4 gate |
|---|-----------|-------|-----------|
| P1 | Author + approve `docs/sprints/epic-3-dag.md` (4 signoffs §8) | Winston + Project Lead | #1, #2 |
| P2 | Close `EPIC-2A-D4` → debt-decay Gate C green for `--target-epic 3` | Winston | #8 |
| P3 | Verify wire-format snapshots green + quality gate green on `main`; remove 4 untracked `.tmp_2b8_*` scratch files | Amelia | #6, #7 |
| P4 | Decide whether Epic 3's new on-disk contracts (`adopt-report.json`, `adopted-symlinks.json`, `imported-metadata/*.yaml`) enter the ADR-024 snapshot ceremony or are exempt as internal state | Winston | design before 3.1 |

## 12. Critical Path — Blockers Before Epic 3

1. **`epic-3-dag.md` authored + 4 signoffs** (P1) — Winston + Project Lead.
2. **`EPIC-2A-D4` closed → Gate C green** (P2 / D-CRIT) — Winston.
3. **Clean `main`: snapshots + quality gate green, scratch files removed** (P3) — Amelia.

## 13. Readiness Assessment

| Dimension | Status |
|-----------|--------|
| Testing & Quality | ✅ 2894 passing · 88.10% · gate green on `main` (coverage-90 debt open) |
| "Deployment" | ➖ N/A (framework). First external ship works: default mock-off + `--allow-mock` gate |
| Stakeholder acceptance | ✅ Project Lead confirmed all findings |
| Technical health | ✅ Stable, debt tracked — ⚠️ Gate C **red** for Epic 3 until D4 closes |
| Unresolved blockers | ⚠️ missing `epic-3-dag.md`; Gate C red; 4 untracked scratch files (covered by P1/P2/P3) |

**Conclusion:** Epic 2B is complete and solid at story level. Before Story 3.1: **2 hard blockers + 4
action items + 4 debt items.** Epic 3's plan is valid — gated, not stale.

## 14. Commitments & Next Steps

- Action items: 4 · Preparation tasks: 4 · Critical-path blockers: 3.
- **Before Story 3.1:** author/approve `epic-3-dag.md`; close `EPIC-2A-D4`; verify green `main`.
- Reconcile CLAUDE.md coverage claim (D1); schedule EPIC-1 D4/D5/D7 closure in prep (D2).
- Epic update required: **NO** — no architecture invalidation; proceed to prep, then Epic 3.

---

*Generated by the BMAD retrospective workflow. Owners are roster personas; the Project Lead executes or
delegates. No time estimates by project convention — effort expressed as complexity/scope only.*
