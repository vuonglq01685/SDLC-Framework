# Contributing to SDLC-Framework

**Status:** Initial publication 2026-05-10 (per Epic 1 retrospective action **A7** + DOC4)
**Audience:** All contributors to Epic 2A onward. Epic 1 patterns are codified retroactively.
**Related ADRs:** [ADR-025](docs/decisions/ADR-025-pydantic-strict-mode-default.md) (Pydantic
strict-mode) · [ADR-026](docs/decisions/ADR-026-tdd-first-chunked-review-workflow.md) (TDD-first
+ chunked review) · [ADR-027](docs/decisions/ADR-027-e2e-test-framework-strategy.md) (E2E tier
strategy)

---

## 1. Quality Gate (Day-1 Discipline)

Every PR — every story — must pass the full quality gate locally before push and again in CI:

| Gate | Command | Floor |
|---|---|---|
| Format | `ruff format --check .` | clean |
| Lint | `ruff check .` | zero violations |
| Type-check | `mypy --strict src/` | zero errors |
| Tests | `pytest -q` | zero failures, zero flaky |
| Coverage | `pytest --cov=sdlc --cov-fail-under=90` | ≥ 90% |
| Pre-commit | `pre-commit run --all-files` | all hooks pass |
| Docs | `mkdocs build --strict` | zero warnings |
| Wire-format snapshots (ADR-024) | `python scripts/freeze_wireformat_snapshots.py --check` | byte-stable |

**Bypass policy:** No `--no-verify`, no `# type: ignore` without inline justification, no
`# noqa` without a citation to the ADR or NFR that motivates the suppression.

---

## 2. TDD-First Discipline (per ADR-026)

For stories touching **CLI surface**, **wire-format contracts**, or **public APIs**:

1. **First commit** on the worktree branch MUST be the test file(s), with tests visibly failing.
   Capture the failing-run log in the PR description.
2. **Subsequent commits** turn red tests green.
3. Reviewer-A confirms ordering: `git log --reverse origin/main..HEAD` shows tests-first commits.

For **novel substrate** stories (where the test API itself is being designed): **test-along**
is permitted with explicit justification in the PR body.

The story PR template includes:

```markdown
- [ ] Tests committed before implementation (verify: `git log --reverse origin/main..HEAD`)
      OR test-along justification provided here: <reason>
```

---

## 3. Worktree Workflow (per ADR-A6 + A7)

### 3.1 Branch-off

- Worktree path convention: `worktrees/epic-<N>/<story-key>/` under repo root, OR a sibling
  directory of the main checkout (developer preference).
- Branch name: `epic-<N>/<story-key>` (e.g. `epic-2a/2a-1-workflow-loader`).
- Always branch from up-to-date `main`:

  ```sh
  git fetch origin
  git worktree add -b epic-2a/2a-1-workflow-loader ../wt-2a-1 origin/main
  cd ../wt-2a-1
  ```

### 3.2 Parallelism Layer Discipline

- Worktree-per-story for stories on the **same** parallelism layer (per Epic-N DAG document
  under `docs/sprints/epic-<N>-dag.md`).
- Project cap: `max_parallel_agents=4` (in `project.yaml`). Layers exceeding 4 must batch.
- Cross-layer parallelism is **not** permitted — wait for the upstream layer to merge.

### 3.3 Linear Merge on Main

- Only **one** worktree merges to `main` at a time.
- Other worktrees on the same layer rebase + re-run CI **after** each merge:

  ```sh
  cd ../wt-2a-2
  git fetch origin
  git rebase origin/main
  pre-commit run --all-files && pytest -q  # re-run quality gate locally
  git push --force-with-lease origin epic-2a/2a-2-specialist-registry
  ```

- Each worktree independently passes the full quality gate before its turn to merge.
- **Rebase, not merge.** The repo enforces a linear history on `main`.

### 3.4 Worktree Cleanup

After merge:

```sh
git worktree remove ../wt-2a-1
git branch -d epic-2a/2a-1-workflow-loader
```

Stale worktrees that fail to remove (e.g. due to uncommitted state) are pruned by
`git worktree prune` only after manual inspection — never silently.

---

## 4. Chunked Review Workflow (per ADR-026)

### 4.1 The Three Labels

| Label | Reviewer focus | Reviewer agent (cf. ADR-027) |
|---|---|---|
| `review-A` | Functional correctness — happy path, AC mapped to tests | Blind Hunter |
| `review-B` | Edge-case completeness — boundary, error, recovery, concurrency, security | Edge Case Hunter |
| `review-C` | Quality, naming, docs, ADR cross-reference, debt-register entries | Acceptance Auditor |

### 4.2 Sequential Gate Progression on a Single PR

1. Author opens PR with label `review-A` only. CI runs the full quality gate.
2. Reviewer-A applies patches **as commits to the same PR branch** (NOT separate PRs).
3. When reviewer-A is satisfied, author resolves all open A-discussions and re-labels to
   `review-B`. Reviewer-B never sees A's still-open discussions.
4. Repeat for `review-C`.
5. Final label `ready-to-merge` triggers the author's merge.
6. **No skipping.** Trivial stories pass through A → B → C; missing gates are an audit failure.

### 4.3 Review Cadence

- Each chunk targets ≤ 24-hour reviewer turnaround.
- Reviewer-fatigue protection: a single reviewer SHOULD NOT carry more than two simultaneous
  `review-X` assignments. Project Lead arbitrates capacity at sprint planning.

### 4.4 Fresh-Context Review Tag (per ADR-026 §4)

Every code-review commit MUST run in a *fresh-context* session distinct from the one that
authored the implementation. The commit-msg hook
`scripts/check_fresh_context_review_tag.py` enforces this via two sub-rules:

- **R1:** Commits whose message mentions `code-review`, `chunked review`, `review patches`,
  `bmad-code-review`, etc. MUST contain the literal tag `[fresh-context-review]` in subject
  or body.
- **R2:** Commits carrying `[fresh-context-review]` MUST NOT stage any `src/` files —
  implementation lives in a separate `feat`/`fix` commit in an earlier (now-pushed) session.

One-time install per clone:

```bash
uv run pre-commit install --hook-type commit-msg
# or, install every hook type configured:
uv run pre-commit install --install-hooks
```

Violating either rule blocks the commit with a stderr explanation listing the offending files
or the missing tag. See ADR-026 §4 for the worked example and full rationale.

---

## 5. Decision Protocol (D1/D2/D3 Option-Labels)

When reviewers raise a material decision (architectural, security-relevant, or wire-format
adjacent), they MUST present it as a structured option list:

```markdown
**D1 (option 1):** <approach A>
- Pro: <…>
- Con: <…>

**D2 (option 2):** <approach B>
- Pro: <…>
- Con: <…>

**D3 (option 3):** Defer to debt register / do nothing now
- Pro: <…>
- Con: <…>

**Reviewer recommendation:** D2 because <…>
```

The author (or Project Lead, escalated) selects D1 / D2 / D3 in a **single line reply**. The
selection is recorded in the PR Change Log. Free-text rebuttals to material decisions are
disallowed — the reviewer reframes as D1/D2/D3 if the author's response is unstructured.

Cosmetic / non-material decisions (variable rename, comment polish) are exempt and resolved
via ordinary PR discussion.

---

## 6. Story PR Template

```markdown
## Story X.Y — <title>

**Spec:** `_bmad-output/planning-artifacts/epics.md` (Epic <N>, Story X.Y)
**Story doc:** `_bmad-output/implementation-artifacts/X-Y-<slug>.md`
**Worktree:** `epic-<N>/<story-key>`
**Layer:** <DAG layer N>

### Acceptance criteria
<copy from epics.md>

### TDD-first ordering
- [ ] Tests committed before implementation (verify: `git log --reverse origin/main..HEAD`)
      OR test-along justification: <…>

### E2E coverage (per ADR-027)
- [ ] Tier-1 (CLI golden) added under `tests/e2e/cli/`
- [ ] Tier-2 (pipeline-vs-MockAIRuntime) added under `tests/e2e/pipeline/`
      OR rationale for omission: <…>

### Quality gate (verify locally)
- [ ] ruff format + check
- [ ] mypy --strict
- [ ] pytest (zero failures)
- [ ] coverage ≥ 90%
- [ ] pre-commit run --all-files
- [ ] mkdocs build --strict
- [ ] freeze_wireformat_snapshots --check

### ADR cross-reference (if any)
<list new or updated ADRs>

### Debt register entries (if any)
<list new entries created in deferred-work.md>

### Change log
<one-line summary of major commits / patches>
```

---

## 7. Per-Epic Prerequisites (Pre-Story N.1 Gate)

**Status:** Permanent policy from Epic 2A onward (Epic 1 patterns codified retroactively).
**Source:** Epic 1 retrospective Team Agreements (A) and (F) — generalized for all future epics.

Before Story `N.1` of any epic enters implementation, the following artifacts and gates MUST be
satisfied. This is a hard prerequisite, not a checklist of recommendations.

### 7.1 Mandatory Artifacts

| # | Artifact | Path | Owner |
|---|---|---|---|
| 1 | Story DAG document | `docs/sprints/epic-<N>-dag.md` | Senior dev + PO |
| 2 | Sprint-planning output | DAG §3 (parallelism layers) + §4 (critical path) + §5 (worktree assignments) | included in #1 |
| 3 | DAG approval signoffs | DAG §8 — minimum **3 approvers**: dispatcher-correctness, sprint-capacity, architectural cross-reference | individual reviewers |
| 4 | Project Lead directive sign-off | DAG §8 final checkbox | Project Lead |

### 7.2 Mandatory Closed-Items Gate

Before Story `N.1` starts, the previous epic's retrospective action items MUST be in the
following state:

- **All process actions (A-series)** flagged "Before Story N.1" in the retro: **closed** (visible
  in CONTRIBUTING.md, ADR, or PR-merged code).
- **All technical debt items (D-series) marked HIGH or "blocks Story N.x"**: **closed** with
  evidence (test file path, ADR, or merged PR).
- **All documentation actions (DOC-series)** flagged "Before Story N.1": **published** (ADR
  status `Accepted`, not `Proposed`).

Items marked MEDIUM/LOW priority MAY remain open and run in parallel-prep slots (per Epic 1
retro §6.2 pattern).

### 7.3 Mandatory DAG-First Rule (Team Agreement F)

> Every epic begins with a sprint-planning session producing a story-DAG and parallelism plan.

No exceptions for "small" epics. The DAG document is the single source of truth for:

- Story dependencies (which stories block which)
- Parallelism layers (which stories may run as concurrent worktrees)
- Critical path (longest chain — sets epic minimum wall-clock)
- Worktree assignments (per Team Agreement G — worktree-per-story at same layer)
- Risks and mitigations (cross-story coupling, capacity bottlenecks)

The DAG document SHALL be approved (§7.1 row 3+4) before any Story `N.1` story file is created
via `bmad-create-story` or equivalent.

### 7.4 Pre-Story N.1 Verification Checklist

The story author (or AI agent) verifies the gate is satisfied immediately before invoking
`bmad-create-story` for `N.1`:

```markdown
## Pre-Story N.1 Verification — Epic <N>

- [ ] `docs/sprints/epic-<N>-dag.md` exists
- [ ] DAG §8 has all 4 approvals checked (dispatcher / capacity / architecture / Project Lead)
- [ ] Previous epic's retro: all "Before Story N.1" A-actions closed (linked)
- [ ] Previous epic's retro: all HIGH-priority D-items closed (linked)
- [ ] Previous epic's retro: all "Before Story N.1" DOC-items published (ADR Accepted)
- [ ] Wire-format snapshots green (`scripts/freeze_wireformat_snapshots.py --check`)
- [ ] Quality gate green on `main` (`pre-commit run --all-files && pytest -q`)
- [ ] Debt-decay budget gate green (`scripts/check_debt_decay_budget.py --target-epic <N> --mode strict`)
```

If any item is unchecked, **stop and escalate to Project Lead**. Do not proceed with story
creation under "I'll backfill later" rationale — the prerequisites exist precisely because Epic
1 demonstrated the cost of skipping them.

### 7.5 Debt-Decay Policy

**Status:** Permanent policy from Epic 2B onward (Epic 2A retrospective action A1).
**Source:** Epic 2A retro top concern — debt accumulation across epics with no closure gate.

**Purpose:** Prevent unbounded debt accumulation across epics by enforcing a machine-checkable
budget before each `Story N.1` opens. Each prep sprint MUST close enough carry-forward debt to
keep the next epic from inheriting a load-bearing burden.

**Three policy gates:**

| Gate | Rule | Threshold |
|---|---|---|
| A | BLOCKING items currently closed (any `epic_of_origin`) | ≥5 |
| B | HIGH carry-forward items closed (`epic_of_origin != target_epic`) | ≥50% |
| C | Items open from two epics back (N-2 zero-out, any severity) | 0 open |

Gate A is absolute — it does NOT scope to "closed during this cycle"; the rolling count of
BLOCKING-closed items across the whole budget must reach 5. Gate B treats *all* non-target
epics as carry-forward (consistent with retro wording — not scoped to N-1 alone). Gate C is the
zero-tolerance heel-drag check: anything that has lingered for two epics must close.

**Budget tracker:** `_bmad-output/implementation-artifacts/debt-budget.yaml` is the
machine-readable inventory the gate consumes. Each item declares `id`, `severity`, `status`,
`epic_of_origin`, and `title`. Owners update the file when a closure lands (linked to the
corresponding PR or commit). Free-form context stays in `deferred-work.md`; the YAML is the
single source of truth for severity + status.

**Runner:** `scripts/check_debt_decay_budget.py` renders a markdown audit table and exits:

| Exit | Meaning |
|---|---|
| 0 | All three gates pass, OR `--mode warn` (default — advisory) |
| 1 | One or more gates fail AND `--mode strict` |
| 2 | IO error (missing budget file, malformed YAML, unknown target epic) |

```bash
# Advisory run (default — used by CI on every PR)
uv run python scripts/check_debt_decay_budget.py --target-epic 2b

# Strict run (used during prep-sprint close-out, gates Story N.1)
uv run python scripts/check_debt_decay_budget.py --target-epic 2b --mode strict
```

**CI integration:** The `debt-decay-gate` job in `.github/workflows/ci.yml` runs the script on
every PR. Mode defaults to `warn` (audit visibility without blocking); a PR carrying a label
matching `before-story-<N>.1` (e.g. `before-story-2b.1`) is upgraded to `--mode strict` and
hard-fails if any gate is red. Label the PR that gates the Story N.1 worktree opening so the
gate fires at the right moment.

**Audit table example** (live output for target Epic 2B at end of Epic 2A close-out):

```markdown
# Debt-Decay Audit — Target Epic 2b

| Gate | Status | Observed | Threshold |
|---|---|---|---|
| Gate A (BLOCKING absolute) | FAIL | 0 closed | ≥5 |
| Gate B (HIGH carry-forward) | PASS | 2/4 closed | ≥50% |
| Gate C (N-2 zero-out) | FAIL | 4 open | 0 |

**Overall:** FAIL
```

**Lineage table** — known target epics and their `(previous, two_back)` mapping (extend in
`scripts/check_debt_decay_budget.py::EPIC_LINEAGE` as new epics open):

| Target | Previous (N-1) | Two-back (N-2) |
|---|---|---|
| 2a | 1 | — (sentinel) |
| 2b | 2a | 1 |
| 3  | 2b | 2a |
| 4  | 3  | 2b |
| 5  | 4  | 3 |

**Integration with §7.4 checklist:** Every Story N.1 verification cycle MUST include a
`--mode strict` invocation. The debt-budget green check is a peer of the wire-format snapshot
check and the pre-commit quality gate — not an optional add-on. The Project Lead's signoff in
DAG §8 implicitly attests that the budget check passed at gate time.

### 7.6 Audit Trail

Each epic's prerequisite verification SHALL leave one of:

- A commit message citing this section (preferred for solo runs)
- A row in the relevant DAG `§9. Revision Log` (preferred for team runs)
- A signed-off PR description on the first story PR

This is how a future contributor (or auditor) reconstructs whether the gate fired.

---

## 8. Reporting Issues


- **Bugs in shipped substrate:** Open an issue with `kind:bug` label, cite the failing test or
  reproducer, and specify which ADR's invariant is violated (if any).
- **Process / workflow concerns:** Surface at retrospective, OR raise immediately with the
  Project Lead if blocking.
- **Security concerns:** Direct message the Project Lead — do NOT open a public issue first.
  See `docs/threat-model.md` (Story 2B.7, planned) for the full disclosure protocol.

---

## 9. Code of Conduct

This project is an internal milestone today; team agreements (A) — (I) recorded in the Epic 1
retrospective govern collaboration. Public-contributor terms will be added when the project
ships externally.

---

## 10. Revision Log

| Date | Author | Change |
|---|---|---|
| 2026-05-10 | Alice (drafted via sprint-planning skill) | Initial publication — TDD-first + chunked review + worktree workflow + decision protocol per Epic 1 retro DOC4 |
| 2026-05-10 | Vuonglq01685 + Claude | Added §7 Per-Epic Prerequisites — codifies Team Agreements (A)+(F) as permanent policy for all future epics; Pre-Story N.1 gate with mandatory DAG approval + retro-action closure |
| 2026-05-21 | Vuonglq01685 + Claude (prep-sprint C6) | Added §7.5 Debt-Decay Policy per Epic 2A retro action A1; renumbered Audit Trail to §7.6; updated §7.4 verification checklist to include debt-budget gate; backed by `scripts/check_debt_decay_budget.py` + `debt-budget.yaml` + `debt-decay-gate` CI job |
| 2026-05-21 | Vuonglq01685 + Claude (prep-sprint C7) | Added §4.4 Fresh-Context Review Tag per Epic 2A retro action A2; ADR-026 §4 amendment ratified; commit-msg hook `scripts/check_fresh_context_review_tag.py` enforces R1 (tag required when review commit) + R2 (no `src/` in tagged commits); `.pre-commit-config.yaml` gains `commit-msg` stage |
