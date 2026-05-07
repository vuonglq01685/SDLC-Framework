# ADR-002: Ruff Linting + Formatting Configuration

**Status:** Accepted (2026-05-07, Story 1.2)

## Context

NFR-MAINT-2 and NFR-MAINT-3 demand ruff-clean code with hard caps on file/function/complexity,
plus mandatory `from __future__ import annotations` on every module (Architecture §487, §708, §710).

## Decision

### Rule Selection

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "C90", "UP", "SIM", "PL", "RUF"]
ignore = ["PLR0913"]   # too-many-arguments: engine signatures legitimately wide
```

### Hard Caps (NFR-MAINT-3)

| Cap | Rule | Config |
|-----|------|--------|
| Cyclomatic complexity ≤ 8 | `C901` | `[tool.ruff.lint.mccabe] max-complexity = 8` |
| ≤ 50 LOC/function (proxy) | `PLR0915` | `[tool.ruff.lint.pylint] max-statements = 50` |
| `from __future__ import annotations` | `I002` | `[tool.ruff.lint.isort] required-imports = [...]` |

### `line-length = 100`

Not 88 (ruff/black default) nor 79 (PEP 8). The architecture's load-bearing caps are
LOC/function/complexity (NFR-MAINT-3), not line length. 100 keeps configuration-heavy lines
(TOML-imitation strings, complex type hints) readable without artificial breaks.

### `from __future__ import annotations` (I002)

Architecture §710 originally described a "custom pre-commit hook" for this enforcement.
Ruff's native `required-imports` mechanism (rule `I002`) supersedes that — it is faster,
first-class, and CI-friendly. The custom hook is not needed. Story 1.4 owns file-LOC cap
and module-boundary enforcement via AST; this ADR does not.

### Statements vs. LOC for Function-Length Cap

The literal NFR-MAINT-3 rule is "≤ 50 LOC per function". Ruff has no native
LOC-per-function rule; the closest mechanism is `PLR0915` (too-many-statements) under
`[tool.ruff.lint.pylint] max-statements = 50`. **Statements are not lines.** A function
with 50 statements may legitimately span more than 50 source lines once formatting,
multi-line type hints, and string literals are counted; conversely, dense one-liners can
fit many statements per line.

The proxy is acceptable because it captures the spirit (function-level complexity budget)
without requiring custom AST tooling. When a function passes the statement cap but its
source genuinely exceeds 50 lines from formatting alone, the manual check at PR review
time enforces the literal rule. If drift becomes real and operational, Story 1.4 can
upgrade the boundary-validator pre-commit hook to also count function-source lines via
AST.

### File-LOC Cap (≤ 400 LOC/file)

Ruff (current locked version `0.15.x`) has no native file-LOC rule. This cap is enforced
by Story 1.4's `boundary-validator` pre-commit hook (AST walk on every changed file).
Until Story 1.4 lands, the `max-statements = 50` function-level proxy is the operational
enforcement; per-file LOC is checked at PR review time.

### Per-file Ignores

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["PLR2004"]   # magic numbers in tests are fine
```

Cap rules (`C901`, `I002`, `PLR0915`) are NOT in the per-file-ignores and remain enforced
on tests — long parametric fixtures must still respect the 50-statement budget. If a
specific test file legitimately needs the relaxation, prefer per-file-ignore over loosening
the project-wide cap.

## Alternatives Considered

- **Ruff defaults only** — rejected: does not enforce NFR-MAINT-3 caps.
- **black + flake8 + isort separately** — rejected: slower, more config files; ruff is the
  architecturally chosen tool (Architecture §1333).
- **Custom pre-commit AST walker for required-imports** — rejected: ruff `I002` is native,
  faster, and CI-friendly. Story 1.4 still owns file-LOC and boundary hooks.

## Consequences

- Every commit is gated on cap compliance.
- Minor false-positives expected on `PLR2004` magic-number warnings in tests (already silenced).
- File-LOC cap (≤ 400 LOC/file) is **not** enforced by ruff — Story 1.4's
  `boundary-validator` pre-commit hook owns that enforcement.

## Revisit-by

2026-12-01 (post-pilot) or sooner if a future ruff release ships a native file-LOC rule
(verify against latest release notes; locked version at time of writing is `0.15.12`).
