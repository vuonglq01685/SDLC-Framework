# ADR-026: TDD-First + Chunked-Review Workflow

**Status:** Proposed (2026-05-10, Epic 2A prep — process foundation)

## Context

Epic 1 retrospective (2026-05-09) surfaced two compounding patterns that motivated explicit
process discipline for Epic 2A onward:

1. **Tautological / placebo tests (§3 Pattern 1)** — Stories 1.13, 1.14, 1.16, 1.19, 1.20
   (nearly half the epic) shipped tests that passed for the wrong reason: mocks subverted the
   exact behavior the test claimed to exercise. Root cause: tests written **after** the
   implementation match the code that already runs, rather than spec'ing the behavior. Coverage
   of 93.37% therefore over-states behavioral coverage.

2. **Review-patch volume crescendo (§3 Pattern 5)** — Patch counts rose toward end-of-epic
   (1.5 = 15 cosmetic, 1.20 = 33 real-bug). Story 1.18 split into 1.18 + 1.18.1 because the PR
   landed at 1717 lines and reviewers could not maintain attention across the whole diff. Both
   reviewer fatigue and silent-bug ship-risk increased.

Project Lead (Vuonglq01685) issued two directives at retrospective close (§9):

- **Directive 2:** TDD-first discipline as default for Epic 2A (encoded as action **A1**).
- **Directive 3:** Chunked / layered code review to manage review-patch volume (encoded as
  action **A2**).

This ADR codifies both as the Epic 2A baseline workflow.

## Decision

### 1. TDD-First — MANDATORY for Stories with Public Surface

For every Epic 2A story whose acceptance criteria involve **CLI surface**, **wire-format
contract changes**, or **public-API additions**, the author MUST land tests *before* the
implementation. Concretely:

- The first commit on a story branch MUST be the test file(s) covering the acceptance criteria,
  with the tests visibly **failing** (run-log evidence in PR body).
- The implementation commit(s) follow, turning the failing tests green.
- Reviewers verify the test-first ordering by inspecting `git log --reverse origin/main..HEAD`
  on the worktree branch.

For stories whose primary work is **novel substrate** (e.g. a new POSIX-only invariant where
the test API itself is being designed), **test-along** is permitted: tests and implementation
land in the same commit, but the PR description must justify the deviation explicitly.

The story-template review checklist gains a single line:

```markdown
- [ ] Tests committed before implementation (reviewer: confirm via `git log --reverse`)
      OR test-along justification provided in PR description.
```

### 2. Chunked Review — Sequential Three-Gate Progression on a Single PR

A single PR per story, with three GitHub labels gating sequential review chunks:

| Label | Reviewer focus | Reviewer agent (cf. ADR-027) |
|---|---|---|
| `review-A` | Functional correctness — does the happy path work? Acceptance criteria mapped to tests? | Blind Hunter |
| `review-B` | Edge-case completeness — boundary, error, recovery, concurrency, security | Edge Case Hunter |
| `review-C` | Quality, naming, docs, ADR cross-reference, debt-register entries | Acceptance Auditor |

**Rules:**

1. The author opens the PR with label `review-A` only. CI runs the full quality gate.
2. Reviewer-A applies patches **as commits to the same PR branch** (NOT separate PRs). When
   reviewer-A is satisfied, author re-labels to `review-B`. Reviewer-B never sees A's open
   discussions — A discussions are resolved before relabel.
3. Repeat for `review-C`. Final label `ready-to-merge` triggers merge by author.
4. **No skipping.** Even trivial stories pass through A → B → C; missing gates are an audit
   failure.
5. **Review patches on the same branch, not separate PRs.** Epic 1 lesson: 250+ patches across
   stories proved that one-branch-many-commits is sustainable; separate PRs per chunk would
   triple the merge-coordination burden.

### 3. Decision Protocol — D1/D2/D3 Option-Labels

Reviewers MUST present material decisions to the author/Project Lead in a structured option
list (organic in Epic 1, explicit from Epic 2A):

```
**D1 (option 1):** <approach A> — pro: <…> con: <…>
**D2 (option 2):** <approach B> — pro: <…> con: <…>
**D3 (option 3):** <do nothing / defer to debt register> — pro: <…> con: <…>
**Reviewer recommendation:** D2 because <…>
```

Author selects D1/D2/D3 in a single reply. Selection appears in the PR Change Log. Replies with
free-text rebuttals are explicitly disallowed for material decisions — reviewer reframes as
D1/D2/D3 if the author's reply is unstructured.

## Alternatives Considered

- **Test-after with mandatory mutation testing as a counterweight** (would let Epic 1's habits
  continue while raising the floor): Rejected — mutation testing is a useful but partial
  signal; it cannot detect *missing-test-for-this-behavior* gaps that TDD makes visible by
  construction.
- **Multiple PRs per story (one per review chunk)**: Rejected — merge-coordination cost scales
  linearly per chunk; rebasing parallelism plan (per ADR-A6 worktree workflow) becomes
  intractable.
- **Reviewer-rotation random-assignment**: Considered viable but rejected for Epic 2A — the
  Blind/Edge/Quality split is reviewer-skill-aligned. Random assignment is revisited if the
  team graduates beyond five active reviewers.

## Consequences

- **+** Behavioral coverage rises: tautological-test pattern is structurally prevented for
  CLI/contract/public-API surface (the highest-risk slice).
- **+** Reviewer attention scales: each chunk has a single focus; reviewer fatigue at hour-3
  on a 1700-line PR is replaced by three focused 200-300-line passes.
- **+** Decision protocol formalizes what was organic in Epic 1; D1/D2/D3 labels improve
  audit-log quality and accelerate Project Lead intervention.
- **−** First-time authors will incur ~10-15% time overhead writing tests first. Mitigated by
  pair-mentoring (action A4) for Stories 2A.1/2A.2.
- **−** Three-label progression adds review-coordination overhead (~5 minutes per relabel
  + automation if CI auto-assigns). The retrospective P-task slot covers a CI auto-assignment
  prototype.
- **−** Strict TDD on substrate may generate "test the test" anti-patterns. Reviewer-B is the
  designated guard against that.

## Revisit-by

2026-11-10 — or after Epic 2A retrospective, whichever comes first.
