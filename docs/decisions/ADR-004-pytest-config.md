# ADR-004: Pytest and Coverage Configuration

**Status:** Accepted (2026-05-07, Story 1.2)

## Context

NFR-MAINT-4 demands ≥90% engine line coverage, ≥80% workflow YAML coverage, ≥1 property test
per state machine. PRD §215 states "Full test pyramid" (unit + integration + nightly E2E +
property + benchmark).

## Decision

### Pytest Configuration

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--cov=src/sdlc",
    "--cov-report=term-missing",
    "--cov-report=xml",
    "--cov-fail-under=90",
]
xfail_strict = true
filterwarnings = ["error"]
```

Key choices:
- `--strict-markers` — unknown `@pytest.mark.X` → error (prevents typo-silent test skips).
- `--strict-config` — unknown ini keys → error (catches `[tool.pytest.ini_optoins]` typos).
- `xfail_strict = true` — xfail that unexpectedly passes → fail (forces real fix commitment).
- `filterwarnings = ["error"]` — warnings become errors (NFR-MAINT-1 discipline; catches
  deprecations early and prevents silent degradation).
- `--cov-report=xml` — produces `coverage.xml` for CI ingestion (Story 1.3).

### Coverage Configuration

```toml
[tool.coverage.run]
source = ["src/sdlc"]
branch = true
parallel = true

[tool.coverage.report]
fail_under = 90
show_missing = true
exclude_also = ["if TYPE_CHECKING:", "raise NotImplementedError", "@(abc\\.)?abstractmethod"]
```

`branch = true` — enables branch coverage (stronger than line coverage; catches dead `elif`/
`else` arms). This exceeds the NFR-MAINT-4 literal requirement (line coverage) intentionally.

### `fail_under = 90` — Coverage Interpretation

AC3 literally says "for engine modules". Coverage.py has no native per-module `fail_under`
syntax in pyproject.toml. Two options were evaluated:

- **Option A (chosen)**: Global `fail_under = 90`. Conservative — forces 90% on every module.
  Acceptable in v0.2 because almost every module IS engine (state, journal, dispatcher, hooks,
  signoff, runtime, telemetry, workflows, specialists). Non-engine modules (dashboard, CLI) ship
  in later stories and may need per-path relaxation.
- **Option B (rejected)**: `coverage report --include=src/sdlc/engine/*` with custom CI step.
  Adds complexity for a v0.2 substrate story; deferred until first sub-90% module appears.

When non-engine modules ship (Story 5.1 dashboard), switch to per-path thresholds via the
`[tool.coverage.report]` `include`/`precision` mechanism or `[tool.coverage.paths]` + a
custom CI step. ADR-004 records this migration path.

## Alternatives Considered

- **Separate `setup.cfg`** — rejected: single source of truth in pyproject.toml.
- **nose2** — rejected: pytest is canonical and PRD-named.
- **Per-module coverage threshold via custom CI step** — deferred: single global threshold
  is sufficient until non-engine modules ship in Stories 5.x.

## Consequences

- Every test run computes branch coverage; missing tests fail CI at <90%.
- Warnings are errors — catches deprecations early.
- `coverage.xml` is generated on every run (added to `.gitignore`; consumed by CI in Story 1.3).

## Revisit-by

When first non-engine module (dashboard, Story 5.1) lands and the 90% global threshold
is too aggressive for that module.
