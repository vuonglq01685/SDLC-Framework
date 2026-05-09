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
| Type-check | `mypy --strict src tests` | zero errors |
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

## 7. Reporting Issues

- **Bugs in shipped substrate:** Open an issue with `kind:bug` label, cite the failing test or
  reproducer, and specify which ADR's invariant is violated (if any).
- **Process / workflow concerns:** Surface at retrospective, OR raise immediately with the
  Project Lead if blocking.
- **Security concerns:** Direct message the Project Lead — do NOT open a public issue first.
  See `docs/threat-model.md` (Story 2B.7, planned) for the full disclosure protocol.

---

## 8. Code of Conduct

This project is an internal milestone today; team agreements (A) — (I) recorded in the Epic 1
retrospective govern collaboration. Public-contributor terms will be added when the project
ships externally.

---

## 9. Revision Log

| Date | Author | Change |
|---|---|---|
| 2026-05-10 | Alice (drafted via sprint-planning skill) | Initial publication — TDD-first + chunked review + worktree workflow + decision protocol per Epic 1 retro DOC4 |
