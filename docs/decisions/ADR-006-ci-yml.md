# ADR-006: CI Workflow (`ci.yml`) — Python × OS Matrix Quality Gates

**Status:** Accepted (2026-05-08, Story 1.3)

## Context

NFR-COMPAT-1 requires CI coverage across Python 3.10–3.13. NFR-COMPAT-2 names macOS and Linux as v1 first-class platforms. Architecture §222 specifies filesystem case-sensitivity testing requires both macOS (case-insensitive) and Ubuntu (case-sensitive) in the matrix. AR-CI mandates `ci.yml` runs lint → type → unit → integration on every PR. Story 1.2 codified the quality gates in `pyproject.toml`; this story wires them into CI.

## Decision

An 8-cell matrix (Python `{3.10, 3.11, 3.12, 3.13}` × OS `{ubuntu-latest, macos-latest}`) runs on every PR to `main` and on every push to `main`. Each cell executes the canonical sequential pipeline:

1. `uv sync --frozen --group dev` (lockfile-frozen install)
2. `uv run ruff check src/ tests/` (lint)
3. `uv run ruff format --check src/ tests/` (format enforcement; `ruff format` handles `.py`/`.pyi` only — `pyproject.toml` is omitted because the formatter silently no-ops on TOML)
4. `uv run mypy --strict src/` (type checking)
5. `uv run pytest` (unit + integration tests with coverage gate; `--cov-fail-under=90` in `addopts`)

Additional settings:
- `astral-sh/setup-uv@v8` with `enable-cache: true` and `cache-dependency-glob` covering `pyproject.toml` + `uv.lock`
- `concurrency.group: ${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: ${{ github.event_name == 'pull_request' }}` — superseded PR runs are dropped, but pushes to `main` never cancel each other (canceling a merged commit's CI would leave branch protection's "passing CI" record stale).
- `fail-fast: false` — reveals cross-version failure patterns instead of stopping on the first cell failure
- Coverage XML uploaded as artifact (`retention-days: 14`, `if-no-files-found: ignore`)
- Action SHA comments document long-form SHAs for future supply-chain hardening (e.g. `actions/checkout@v5 # pin: 11bd71901bbe5b1630ceea73d27597364c9af683`). The single literal-SHA pin in the substrate is `pypa/gh-action-pypi-publish` in `release.yml` — see [ADR-008](ADR-008-release-yml.md) for the deliberate exception.

**Operator setup (one-time, not enforceable by this story):** Repo Settings → Branches → Add protection rule for `main` → "Require status checks to pass before merging" → select the required checks below.

**Required status checks (amended 2026-06-09, Epic 3 retro action A2).** The
original note named only the 8 `quality-gates` matrix cells. That predated the
POSIX-only adopt gates, so a red mutation or all-skipped adopt run would not have
blocked merge. The required set is now:

- all 8 `quality-gates` matrix cells (py3.10–3.13 × {ubuntu, macos});
- **`mutation-tests`** — Adopt mutation gate (≥95% kill, Story 3.7 / ADR-036);
- **`posix-adopt-ran`** — POSIX adopt suite actually-ran gate (Epic 3 retro A2;
  `scripts/check_posix_suite_ran.py`). The adopt suite is POSIX-only (ADR-034)
  and skips on win32; this gate fails an all-/mostly-skipped run so a "green on
  Windows" or a broadened-skip-marker false green cannot reach `main`.

A story may not be flipped to `done` until these checks are green on its branch
(paired with the local merged-before-done gate, `check_story_merged_before_done.py`).
Set them via the GitHub UI, or:

```sh
gh api -X PATCH repos/{owner}/{repo}/branches/main/protection/required_status_checks \
  -f 'checks[][context]=mutation-tests' \
  -f 'checks[][context]=posix-adopt-ran'
```

## Alternatives Considered

- **pip + venv instead of uv**: Rejected — slower cache invalidation, no native lockfile reproducibility, diverges from Story 1.1's uv substrate decision ([ADR-001](ADR-001-pyproject-metadata.md)).
- **`actions/setup-python@v5` standalone + manual uv install**: Rejected — `astral-sh/setup-uv@v8` integrates Python provisioning, binary caching, and dependency-glob cache invalidation in one action.
- **Single-OS PR gate + cross-OS nightly**: Rejected — filesystem case-sensitivity bugs (Architecture §222) are PR-time blockers. A macOS-only or Ubuntu-only gate would miss them until nightly, too late in the review cycle.
- **`fail-fast: true` (default)**: Rejected — when py3.13 fails on macOS, the pattern across other versions is diagnostic. A cancelled matrix hides whether it's a version-specific or a universal failure.

## Consequences

- ~8 minutes per PR run on warm cache (ruff: ~2 s, mypy: ~15 s, pytest: ~30 s per cell; 8 cells in parallel).
- Free-tier GitHub Actions minutes consumed by every push to main and every PR commit.
- Branch protection rule (configured in repo settings, not this story) makes the matrix authoritative for merge blocking.
- Coverage XML artifacts are available to downstream tooling (Codecov, SonarQube) without committing them to the repo.

## Revisit-by

2026-12-01 — or when Python 3.14 GA forces matrix expansion, or when the Windows-via-WSL2 stretch goal (NFR-COMPAT-2 v1.x) lands.
