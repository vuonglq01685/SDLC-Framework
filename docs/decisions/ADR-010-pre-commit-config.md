# ADR-010: Pre-commit Configuration + Module Boundary Enforcement Hook

## Status

Accepted (2026-05-08, Story 1.4)

## Context

PRD §877-§878 (NFR-MAINT-1, NFR-MAINT-2) demand mypy + ruff gate compliance at every commit.
PRD §878 (NFR-MAINT-3) demands per-file LOC ≤ 400, per-function ≤ 50 LOC, cyclomatic complexity ≤ 8.
Architecture §708-§711 (Pattern Enforcement table) requires pre-commit + CI for every cap, with
a custom hook for forbidden import rules.
Architecture §1073-§1112 defines the 16-module dependency DAG with 8 specific boundary rules
that the entire 25-30 module substrate rests on.
Architecture Concern #15 (§1043) declares `scripts/validate_specialists.py` as the specialist
cross-reference pipeline — not yet implemented in v0.2.
[ADR-002](ADR-002-ruff-config.md) (Story 1.2) explicitly delegated: the per-file LOC cap ([ADR-002](ADR-002-ruff-config.md) §"Hand-offs") and
module-boundary AST enforcement ([ADR-002](ADR-002-ruff-config.md) §"Scope boundary") to this story.
epics.md Story 1.4 BDD criteria are the authoritative acceptance criteria.

Without commit-time boundary enforcement, the Architecture §1300-§1310 "panel-review" leaks
materialise at week 6 of implementation (engine importing runtime/claude.py directly;
dashboard writing state; hooks calling back into engine) when refactoring cost is highest.

### Eight specific boundary rules from Architecture §1103

#### Encoding summary (at-a-glance)

| Rule | Anchor | Encoded in MODULE_DEPS |
|------|--------|------------------------|
| #1 | Only cli/ and runtime/ may invoke external binaries | Not encoded — code-review + subprocess callers policy |
| #2 | engine/, dispatcher/ import runtime/ only via AIRuntime ABC | Not module-level (the ABC sub-module discipline distinguishes `runtime.abc` vs `runtime.claude`); not in SPECIFIC_RULE_MAP. ABC discipline remains code-review |
| #3 | state/ and journal/ are siblings, not parent-child | Encoded: each excludes the other from depends_on (fires the "undeclared dep" branch on violation) |
| #4 | dashboard/ is read-only re state/journal | Cited via `SPECIFIC_RULE_MAP[("engine","dashboard")] = 4`; enforced by adding `dashboard` to `engine.forbidden_from`. Write discipline (no write API) remains code review |
| #5 | hooks/ does not import engine/ or dispatcher/ | Cited via `SPECIFIC_RULE_MAP[("hooks","engine"|"dispatcher")] = 5` |
| #6 | adopt/ does not import engine/ or dispatcher/ | Cited via `SPECIFIC_RULE_MAP[("adopt","engine"|"dispatcher")] = 6` |
| #7 | workflows/, specialists/ do not import engine/, dispatcher/, runtime/ | Cited via `SPECIFIC_RULE_MAP[("workflows"|"specialists","engine"|"dispatcher"|"runtime")] = 7` |
| #8 | foundation layer (errors leaf) | Cited inline by the errors-leaf branch in `check_imports` (`§1054 + §1103-#8`); not in `SPECIFIC_RULE_MAP` |

#### Rules — verbatim from Architecture §1103 (audit copy)

The text below is reproduced verbatim from `_bmad-output/planning-artifacts/architecture.md` §1103 ("Specific boundary rules") so an operator can verify the script matches the spec by reading this ADR alone (AC6).

1. **`cli/` is the only module that may invoke external binaries** other than `runtime/`. `cli/git.py` and `cli/gh.py` wrap subprocess calls; `runtime/claude.py` is the third permitted subprocess invoker.
2. **`engine/` and `dispatcher/` import `runtime/` only via the `AIRuntime` ABC.** Direct import of `runtime/claude.py` outside `runtime/` is forbidden (enforced by pre-commit).
3. **`state/` and `journal/` are siblings, not parent-child.** Both are leaves of the lower stack. Engine reads via `state.projection`; never imports `journal` and `state` together for read paths — projection is the bridge.
4. **`dashboard/` is read-only** with respect to state and journal. No write API in v1.
5. **`hooks/` does not import `engine/` or `dispatcher/`.** Hooks receive a `HookPayload` and operate; they do not call back into engine internals.
6. **`adopt/` does not import `engine/` or `dispatcher/`.** Adopt initializes empty state; engine handles flow afterward.
7. **`workflows/` and `specialists/` do not import `engine/`, `dispatcher/`, or `runtime/`.** They are pure validators / loaders.
8. **`contracts/`, `ids/`, `config/`, `concurrency/`, `errors/` form the foundation layer.** None imports anything from the upper stack.

## Decision

1. `.pre-commit-config.yaml` runs at repo root with `minimum_pre_commit_version: 4.0.0`,
   `default_language_version.python: python3.12` (matches CI), `default_install_hook_types:
   [pre-commit]`.

2. **Hook chain (in exact order):**
   `ruff-check` → `ruff-format` (from `astral-sh/ruff-pre-commit@v0.15.12`) →
   `mypy-strict` (local, runs `uv run mypy --strict src/`) →
   `boundary-validator` (local, `uv run python scripts/check_module_boundaries.py`) →
   `specialist-validator` (local placeholder, `uv run python scripts/validate_specialists.py`) →
   hygiene set (`pre-commit/pre-commit-hooks@v5.0.0`: trailing-whitespace, end-of-file-fixer,
   check-yaml, check-toml, check-merge-conflict, check-added-large-files, mixed-line-ending).

3. **Local hooks use `language: system`** so they run inside the `uv run` environment instead
   of pre-commit-managed venvs. Single source of truth: `uv.lock`.

4. **Module-boundary table is a Python literal `MODULE_DEPS`** inside
   `scripts/check_module_boundaries.py`, not parsed from architecture markdown at runtime.
   Architecture markdown is human-prose; the script needs deterministic, type-safe data.
   Drift is caught by the manual review discipline of [ADR-012](ADR-012-module-layout.md) (Story 1.5).

5. **File-LOC cap (≤ 400 raw lines per .py file)** is enforced by the same boundary-validator
   script. `tests/fixtures/` is exempt to allow long property-test seed files (Stories 1.10+).
   Raw line count = `text.count("\n") + (0 if text.endswith("\n") or text == "" else 1)`
   (matches Architecture §765 wording and `wc -l` POSIX semantics).

6. **Specialist-validator is a 30-LOC no-op stub** for v0.2; activates with Story 2A-2.
   `always_run: true` ensures the chain is wire-complete on every commit even when no agent
   files change. Once Story 2A-2 lands, flip to `files: ^src/sdlc/agents/` + `pass_filenames:
   true` (single edit, no config rework).

7. **`pre-commit` is a `[dependency-groups] dev` dependency** (`>=4.0.0,<5`). Resolved version:
   4.6.0. CI's existing `uv sync --frozen --group dev` step provisions it automatically.

8. **`scripts/` is added to `[tool.ruff] src = [...]`** so meta-tooling obeys the same
   `from __future__ import annotations` and ruff lint discipline as `src/sdlc/`.

9. **`.claude/` and `_bmad/` are added to `[tool.ruff] extend-exclude`** and to check-yaml /
   check-toml `exclude:` patterns, as these directories contain framework configuration files
   that are not part of the project source and are not subject to the same lint discipline.

### Dependency table source of truth

`MODULE_DEPS: dict[str, ModuleSpec]` inside `scripts/check_module_boundaries.py` is a
**second source of truth** alongside the architecture markdown table. PR review discipline
of [ADR-012](ADR-012-module-layout.md) (Story 1.5) is the drift mitigation.

### Specialist-validator placeholder shape

```python
def main() -> int:
    print("[v0.2 placeholder] specialists/ is empty; "
          "cross-ref pipeline activates with Story 2A-2 (specialist registry).")
    return 0
```

Activation story: Story 2A-2 ("Specialist registry + manifest validation").

### Known widenings vs. Architecture (recorded as known gaps)

1. `adopt/` widened to `adopt -> cli` at module-level (Architecture §1069 says `cli/git`
   sub-import only). Real enforcement that `adopt/` only touches `cli.git` lives at code review.
2. `dashboard/` "read-only with respect to state/journal" is not expressible at import-graph
   level. The validator allows dashboard to import state + journal modules generally; preventing
   write-path imports (state.atomic, journal.writer) is a code-review discipline for v0.2.

### Operator setup (one-time per clone)

```
uv run pre-commit install
```

## Alternatives

- **`pre-commit/mirrors-mypy`** for the mypy hook — rejected: introduces a parallel pin
  diverging from `uv.lock`'s mypy version. Local hook + `uv run mypy` is the single source
  of truth.

- **Encoding `MODULE_DEPS` as a YAML or TOML data file** outside the script — rejected: the
  type information (`frozenset`, `ModuleSpec` dataclass) is meaningful; a YAML file would
  re-introduce parse-and-validate friction every run.

- **Scraping the architecture markdown** for the dependency table at hook startup — rejected:
  brittle (any markdown formatting change breaks the parser); the architecture document is
  human-prose, not machine-readable. Drift discipline lives at PR review per [ADR-012](ADR-012-module-layout.md).

- **Running boundary-validator only on `src/sdlc/`** (skipping `tests/` LOC cap) — rejected:
  NFR-MAINT-3 applies to the whole codebase; tests can also balloon. The `tests/fixtures/`
  exemption is the precise relaxation.

- **`language: python` local hooks** with pre-commit-managed venv — rejected: would fork the
  dependency graph from `uv.lock` (single dep source of truth violated).

- **`pre-commit autoupdate` as a CI step** — deferred: useful for keeping rev pins fresh but
  introduces drift risk if the bumped rev breaks anything.

## Consequences

- Every developer's local commit runs the same gates as CI (substrate fidelity).
- CI's existing `uv sync --frozen --group dev` step provisions `pre-commit` automatically.
  CI does NOT add an explicit `pre-commit run` step in v0.2 — that wiring is a deliberate
  future hardening (see Deferred section below).
- `MODULE_DEPS` literal is a parallel source of truth; drift mitigation is PR review ([ADR-012](ADR-012-module-layout.md)).
- `astral-sh/ruff-pre-commit@v0.15.12` rev pin must move in lockstep with `uv.lock`'s ruff
  version. A comment in `.pre-commit-config.yaml` warns about this.
- First-time clones must run `uv run pre-commit install` once.
- `scripts/` is now in ruff's `src` list — any future `scripts/*.py` author must comply with
  `from __future__ import annotations`, line-length 100, complexity ≤ 8, etc.
- Two known widenings exist at module-level (see Decision §Known widenings).

### Deferred

- Adding a `pre-commit run` step to `.github/workflows/ci.yml` — deliberate v0.2 scoping
  choice; the substrate parity is intact (both surfaces call the same underlying tools). Lands
  in any later story that needs the additional CI-time guarantee.
- `commit-msg` hook + `compilerla/conventional-pre-commit` for NFR-MAINT-6 — deferred to a
  future story; today the discipline lives at PR review.
- `pre-commit autoupdate` as a CI cron job.
- Literal-SHA pinning of `astral-sh/ruff-pre-commit` (currently using mutable tag v0.15.12).

## Revisit-by

2026-12-01 OR when Story 2A-2 (specialist registry) lands and the placeholder is flipped,
whichever first. At that point:
- Flip `specialist-validator` to real implementation.
- Update `always_run: true` to `files: ^src/sdlc/agents/` + `pass_filenames: true`.
- Update this ADR status to "Updated".

## References

- Architecture §708-§711 (Pattern Enforcement table)
- Architecture §765 (LOC cap, ≤ 400 LOC/file)
- Architecture §1052-§1112 (Module Specifications + Architectural Boundaries + 8 specific rules)
- Architecture §1043 (`scripts/validate_specialists.py` declaration)
- PRD §876-§878 (NFR-MAINT-1, NFR-MAINT-2, NFR-MAINT-3)
- [ADR-002](ADR-002-ruff-config.md) (file-LOC + boundary-validator hand-off)
- [ADR-006](ADR-006-ci-yml.md) (CI yml — parallel choice for `uv run mypy --strict src/`)
- epics.md Story 1.4 (acceptance criteria)
