# ADR-003: Mypy Strict Type Checking Configuration

**Status:** Accepted (2026-05-07, Story 1.2)

## Context

NFR-MAINT-1 demands `mypy --strict` on every internal module. PRD §622 lists
"mypy --strict discipline" as a required skill for solo build.

## Decision

```toml
[tool.mypy]
python_version = "3.10"
strict = true
mypy_path = ["src"]
namespace_packages = true
explicit_package_bases = true
show_error_codes = true
pretty = true
warn_unused_configs = true
warn_unreachable = true
extra_checks = true
```

`strict = true` expands to all 13 strict-mode flags including `disallow_untyped_defs`,
`disallow_untyped_calls`, `disallow_incomplete_defs`, `check_untyped_defs`,
`no_implicit_reexport`, `warn_return_any`, and more.

`python_version = "3.10"` is the floor (not the host 3.12) so mypy emits errors compatible
with the lowest supported Python — catches 3.11+-only syntax sneaking into the codebase.

`mypy_path = ["src"]` + `explicit_package_bases = true` are required for src layout;
without them mypy may treat `src/sdlc/` as a namespace package and fail to import.

### Tests Relaxation Override

```toml
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
disallow_untyped_decorators = false
```

Pytest fixtures and `@pytest.mark.parametrize` decorators routinely defeat
`disallow_untyped_decorators`. AC2 requires strict on **internal** modules (`src/sdlc/...`);
tests are explicitly excluded from this requirement.

## Alternatives Considered

- **Pyright** — rejected: extra runtime, less mature inline config.
- **Pyre** — rejected: Facebook-aligned, weaker community, non-pyproject-native.
- **Per-file `# type: ignore` strategy** — rejected: no enforcement, defeats the purpose.

## Consequences

- Every internal module ships with full type discipline from the first commit.
- Tests are pragmatically relaxed; cannot enable `--strict` on tests without breaking
  pytest's decorator typing surface.

## Revisit-by

2026-12-01 or when adopting `Self` types or PEP 695 generics on the engine surface.
