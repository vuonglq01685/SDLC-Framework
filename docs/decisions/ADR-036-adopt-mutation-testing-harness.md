# ADR-036: Adopt-module mutation testing harness

- **Status:** Accepted
- **Date:** 2026-06-04
- **Story:** 3.7 — Source-untouched invariant property + mutation testing

## Context

Epic 3 NFR-REL-6 requires mechanical proof that the `adopt/` package cannot mutate
the brownfield source tree. Property tests cover porcelain + tree-hash invariants across
the brownfield corpus; mutation testing (≥95% kill on `src/sdlc/adopt/`) catches
source-mutating regressions that unit tests might miss.

Story 3.7 decision **D1=(b)** keeps `git` subprocess verification in the **test layer**
only — `adopt/` retains its existing module boundary (no `cli`/`git` grant).
`assert_source_untouched` hardens the `.claude/` sandbox structurally; exhaustive
porcelain + tree-hash checks live in `tests/property/`.

## Decision

1. **Tool:** `mutmut` 3.x (D2=a), scoped to `paths_to_mutate = ["src/sdlc/adopt/"]`.
2. **Tree hash:** pure-Python `adopt.tree_hash.compute_source_tree_hash` (D4=b) over
   configured source paths — captures mode + symlink target, not only file bytes.
3. **Source-tree globs:** `adopt.source_tree` default set unioned with `legacy_code_globs`
   (D3=a); `.claude/**` never classified as source.
4. **CI:** separate `mutation-tests` job after `quality-gates` on `ubuntu-latest`,
   `--no-cov`, uploads `mutmut-cicd-stats.json` as an artifact; fails when kill rate < 95%.
5. **`# pragma: no mutate`:** sparingly, with inline justification only (review-C audit).

## Consequences

- **Positive:** Tier-1 gate for source-tree writes; aligns with epics mutmut wording.
- **Negative:** mutation job adds CI time; first run may require targeted tests to reach 95%.
- **Neutral:** no wire-format or journal-kind changes (stays 7/7).

## Revision log

| Date | Change |
|------|--------|
| 2026-06-04 | Accepted with Story 3.7 implementation |
