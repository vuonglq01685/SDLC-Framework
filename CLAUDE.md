## Process discipline (binding for all AI agents and human contributors)

This project enforces hard process discipline established in the Epic 1 retrospective and
codified in `CONTRIBUTING.md`. The single source of truth for *how* work happens here is
`CONTRIBUTING.md` — read it before starting any non-trivial task.

**Per-Epic Prerequisites (CONTRIBUTING.md §7) — hard gate before any Story `N.1`:**
- `docs/sprints/epic-<N>-dag.md` exists and is approved (4 signoffs in §8)
- Previous epic's retro: all "Before Story N.1" A/D/DOC items closed
- Wire-format snapshots green; quality gate green on `main`

If the user asks "let's start Epic N" or "create Story N.1", **verify §7.4 checklist before
invoking `bmad-create-story`**. Do not proceed under "I'll backfill later" rationale.

**When auditing post-retrospective progress** (e.g. user asks "what's been done since the retro?"):
check ALL of the following — not just `src/`:
- `docs/decisions/ADR-*.md` (status: Proposed → Accepted)
- `docs/sprints/epic-*-dag.md` (approval state in §8)
- `CONTRIBUTING.md` (process additions)
- `tests/property/`, `tests/unit/`, `scripts/` (debt-item closures often live here, not in `src/`)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (story status)

**Per-story discipline (CONTRIBUTING.md §1-§6):**
- Quality gate (§1): ruff format/check, mypy --strict, pytest, coverage ≥90%, pre-commit, mkdocs --strict, wire-format snapshots
- TDD-first (§2): tests-first commit ordering for CLI/contracts/public-API; visible in `git log --reverse`
- Worktree-per-story (§3): one branch per story at the same DAG layer; linear merge; rebase between merges
- Chunked review (§4): review-A → review-B → review-C labels on a single PR; no skipping
- Decision protocol (§5): material decisions raised as D1/D2/D3 option-labels, not free-text

**Wire-format and contracts (ADR-024 + ADR-025):**
- All wire-format contracts are frozen at `schema_version=1` with JSON-Schema snapshots in `tests/contract_snapshots/v1/`
- All `pydantic.BaseModel` subclasses in `src/sdlc/contracts/` MUST inherit from `StrictModel` or carry `# strict-opt-out: <reason>`
- A contract-shape edit pairs with a snapshot regeneration ceremony (see ADR-024 mutation taxonomy)

---

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
