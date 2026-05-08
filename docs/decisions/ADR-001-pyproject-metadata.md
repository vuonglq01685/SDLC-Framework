# ADR-001: pyproject Metadata

**Status:** Accepted (2026-05-07, Story 1.1; ADR back-filled 2026-05-09, Story 1.5).

## Context

Story 1.1 bootstrapped the SDLC-Framework Python package using PEP 621 `[project]`
metadata in `pyproject.toml`. The choices made at that time were load-bearing for
downstream tooling (uv build, PyPI publishing, import semantics), but were not
formally recorded as an ADR. This back-fill captures the decision so the rationale
is discoverable alongside the other substrate ADRs.

PRD §137 (Maintainability NFRs) mandates NFR-MAINT-5: every load-bearing decision
recorded as an ADR with status, alternatives, consequences, and a revisit-by date.
Architecture §272 lists ADR-001 as "pyproject metadata" in the hand-craft ADR table.
Story 1.1's deferred-work entry names Story 1.5 as the back-fill owner.

The key forces in play at Story 1.1 time:

- FR47: the PyPI distribution name (`sdlc-framework`) is chosen to avoid clashing with
  the existing `sdlc` distribution on PyPI; the Python import name remains the shorter
  `sdlc` for ergonomic CLI + import use (`pip install sdlc-framework` → `import sdlc`).
- NFR-COMPAT-1: Python ≥ 3.10 floor (match Claude Code's Python requirement).
- No LICENSE file yet — legal review pending; placeholder `text = "TBD"` used.
- Architecture §239 explicitly rules out `setuptools` as build-backend.

## Decision

The `[project]` table in `pyproject.toml` is authored with these load-bearing choices:

- `name = "sdlc-framework"` — the PyPI distribution name (FR47 compliance).
- `version = "0.0.0"` — static placeholder signalling pre-release; dynamic version
  via `importlib.metadata` is deferred (see Alternatives Considered).
- `description = "Deterministic, auditable, multi-agent SDLC orchestration framework on top of Claude Code."`.
- `readme = "README.md"`.
- `license = { text = "TBD" }` — placeholder; SPDX identifier added when the
  LICENSE-file chore lands (v0.2+).
- `authors = [{ name = "Vuonglq01685" }]`.
- `requires-python = ">=3.10"` — NFR-COMPAT-1 floor.
- `dependencies = []` — substrate ships with zero runtime dependencies.

The import name is `sdlc` (the `src/sdlc/` package directory), making the
PyPI-name vs. import-name split explicit: `pip install sdlc-framework` → `import sdlc`.

## Alternatives Considered

- **`dynamic = ["version"]` via `importlib.metadata`**: Rejected at Story 1.1 for
  simplicity — a static `0.0.0` is honest pre-release signalling and avoids the
  `importlib.metadata` runtime import at package init time. Tracked for
  re-evaluation when the first real release lands via [ADR-008](ADR-008-release-yml.md).
- **`setuptools` as build-backend**: Rejected per Architecture §239 — the framework
  stack is uv + hatchling; mixing in setuptools adds a conflicting ecosystem dependency.
- **SPDX license identifier at Story 1.1 time**: Deferred to the LICENSE-file chore.
  Using `{ text = "TBD" }` is non-conformant with SPDX but passes `uv build --wheel`
  without error; PyPI/twine will reject on first publish — that is intentional (forces
  the LICENSE-file chore before any public release).
- **Import name `sdlc_framework` matching PyPI name**: Rejected — underscores in
  package names conflict with FR47's readability goal; `sdlc` is shorter and more
  ergonomic for CLI + import ergonomics.

## Consequences

- PEP 621 compliance unblocks `uv build --wheel` per Story 1.3's
  [ADR-008](ADR-008-release-yml.md) release workflow.
- `version = "0.0.0"` is honest pre-release signalling; no spurious version bumps
  pollute the git log before the first intentional release.
- `license = { text = "TBD" }` is not a valid SPDX identifier — PyPI/twine will
  reject on first publish; the LICENSE-file chore owns this gap (v0.2+). Tracked
  in `_bmad-output/implementation-artifacts/deferred-work.md` under "Deferred from:
  code review of 1-5-mkdocs-adr-log-skeleton (2026-05-08)" with a proposed
  `release.yml` pre-flight grep guard so a failed publish surfaces a clear local
  diagnostic before twine's opaque 400.
- `__version__` is duplicated between `pyproject.toml` and `src/sdlc/__init__.py`
  (intentional Story 1.1 simplification); dynamic source-of-truth is a v1.x candidate
  re-evaluated at the first release per [ADR-008](ADR-008-release-yml.md).

## Revisit-by

2027-05-01 — or when [ADR-008](ADR-008-release-yml.md)'s first release introduces a
real version bump and the dynamic-vs-static `__version__` decision needs re-evaluation,
or when the LICENSE-file chore lands and the SPDX identifier is filled, whichever first.
