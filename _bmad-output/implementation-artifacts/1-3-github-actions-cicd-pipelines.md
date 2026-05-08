# Story 1.3: GitHub Actions CI/CD Pipelines (lint, type, test, e2e, release, docs)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer protecting main branch quality and the v1 PyPI release pipeline,
I want four GitHub Actions workflows (`ci.yml`, `e2e.yml`, `release.yml`, `docs.yml`) executing the canonical lint → type → unit → integration pipeline on every PR across a Python 3.10/3.11/3.12/3.13 × {ubuntu, macOS} matrix, plus a nightly E2E job, a tag-driven PyPI trusted-publishing release job, and a main-push docs publish job,
So that no non-compliant code reaches main, every tagged release publishes a wheel-only artifact via OIDC trusted publishing (zero PyPI tokens stored in CI), and the documentation site auto-rebuilds — with all four pipelines wired to the Story 1.2 quality gates (`uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict src/`, `uv run pytest`) using the `[dependency-groups] dev` install path and a frozen lockfile (`uv sync --frozen --group dev`) so dev-environment drift is impossible between local and CI.

## Acceptance Criteria

**AC1 — `.github/workflows/ci.yml` runs the full quality-gate pipeline on every PR across the Python × OS matrix.**
**Given** Story 1.2 complete (pyproject.toml ships ruff, mypy --strict, pytest, coverage configured) and `.github/workflows/ci.yml` configured per ADR-006
**When** a PR is opened against main (or `main` receives a push)
**Then** the CI matrix runs Python 3.10, 3.11, 3.12, 3.13 on `macos-latest` and `ubuntu-latest` (8 jobs total; cancel-in-progress on the same PR ref)
**And** each job executes the canonical pipeline sequentially: `uv sync --frozen --group dev` → `uv run ruff check src/ tests/` → `uv run ruff format --check src/ tests/ pyproject.toml` → `uv run mypy --strict src/` → `uv run pytest` (coverage gate `--cov-fail-under=90` already in pytest addopts)
**And** any single step's non-zero exit fails that matrix cell, fails the job summary, and (when branch protection is configured) blocks merge
**And** uv is installed via `astral-sh/setup-uv@v8` with `enable-cache: true` and `cache-dependency-glob` covering `pyproject.toml` + `uv.lock`
**And** the Action versions used are pinned to commit SHAs in YAML comments (supply-chain hygiene; even if `@v8` is the version selector)

**AC2 — `.github/workflows/e2e.yml` runs nightly against real Claude Code (when available) plus on-demand via `workflow_dispatch`.**
**Given** `.github/workflows/e2e.yml` configured per ADR-007
**When** the nightly cron triggers (`0 6 * * *` UTC ≈ 13:00 ICT) **OR** a maintainer triggers `workflow_dispatch`
**Then** the E2E suite runs against real Claude Code (`uv run pytest tests/e2e -m e2e`) on `ubuntu-latest` only (cost/time tradeoff per PRD §531)
**And** when `claude` CLI is **not** available in the runner environment, the workflow gracefully skips with a documented "claude binary unavailable; nightly E2E skipped this run" outcome — **not** a red failure (this is the v0.2 reality: real-Claude E2E is gated until ClaudeAIRuntime ships in Epic 2B; for now the workflow scaffolding exists and runs the e2e-marked tests, which currently include only the `tests/e2e/fixtures/` placeholder set established by Story 1.20+ work)
**And** test results, captured stdout, and any artifacts under `tests/e2e/_artifacts/` are uploaded as workflow artifacts (`actions/upload-artifact@v4`) with a 14-day retention policy
**And** the cron timezone choice (UTC) is documented in ADR-007

**AC3 — `.github/workflows/release.yml` publishes wheel-only via PyPI trusted publishing on `v*.*.*` tag push, never on PR.**
**Given** `.github/workflows/release.yml` configured per ADR-008 **AND** PyPI's Trusted Publisher pre-registered (the framework maintainer registers `sdlc-framework` ↔ `Vuonglq01685/SDLC-Framework` ↔ `release.yml` ↔ `pypi` environment in PyPI account settings; this is a **one-time external setup** documented in ADR-008's "Operator setup" section but **NOT** enforceable from this story's automation)
**When** a `v*.*.*` tag is pushed to main (e.g. `v0.1.0`, `v1.0.0`)
**Then** the workflow runs the **full quality-gate sequence first** (lint → type → unit → integration on `ubuntu-latest`/Python 3.12 — single cell; the matrix is for catching cross-version regressions on PRs, not for gating release)
**And** only on green builds, runs `uv build --wheel` to produce `dist/*.whl` (wheel-only; sdist suppressed via `[tool.hatch.build.targets.sdist] exclude = ["**"]`)
**And** publishes via `pypa/gh-action-pypi-publish@release/v1` with `permissions: id-token: write` (OIDC), `environment: pypi`, **no** `password: ${{ secrets.PYPI_TOKEN }}` (zero stored secrets per Architecture §1219, PRD §503)
**And** the published version on PyPI matches the git tag stripped of the leading `v` (asserted at workflow time via a lightweight check: `[ "$(grep -E '^version' pyproject.toml | cut -d'"' -f2)" = "${GITHUB_REF_NAME#v}" ]`)

**AC4 — `.github/workflows/docs.yml` builds and publishes mkdocs to GitHub Pages on push to main.**
**Given** `.github/workflows/docs.yml` configured per ADR-009
**When** main is updated AND `mkdocs.yml` exists at repo root (Story 1.5 territory)
**Then** the workflow runs `uv sync --frozen --group dev` (mkdocs lands in `[dependency-groups] dev` in Story 1.5; **NOT** this story — see "What this story is NOT") → `uv run mkdocs build --strict --site-dir _site`
**And** publishes the built site to GitHub Pages via the canonical `actions/configure-pages@v5` + `actions/upload-pages-artifact@v3` + `actions/deploy-pages@v4` chain (the modern Pages deployment flow; **not** legacy `peaceiris/actions-gh-pages`)
**And** the workflow ships in this story but **gracefully no-ops** until Story 1.5 lands `mkdocs.yml` and the `mkdocs` dev dependency: an early `if: hashFiles('mkdocs.yml') != ''` guard skips the build/deploy steps with the message "mkdocs.yml absent; docs publish deferred to Story 1.5". This is the only way to satisfy AC4's "configured" clause without violating the Story 1.5 boundary
**And** ADR-006, ADR-007, ADR-008, ADR-009 are recorded under `docs/decisions/` as Markdown stubs (same shape as ADR-002/003/004 from Story 1.2: Status, Context, Decision, Alternatives, Consequences, Revisit-by)

## Tasks / Subtasks

- [x] **Task 1 — Add wheel-only sdist suppression to `pyproject.toml` (AC: #3) — closes Story 1.1 deferred-work item #2**
  - [x] 1.1 Edit `pyproject.toml` and add the sdist exclusion block immediately after `[tool.hatch.build.targets.wheel]`:
    ```toml
    [tool.hatch.build.targets.sdist]
    # PRD §499 + §216 mandate wheel-only distribution for v1.
    # Without this exclusion, `uv build` emits an sdist sweeping every non-gitignored
    # file (~3.3 MB / 1085 files in Story 1.1). release.yml uses `uv build --wheel` so
    # the wheel target alone is exercised in CI, but a contributor running plain `uv build`
    # locally would still produce a noisy sdist. Suppress entirely.
    exclude = ["**"]
    ```
  - [x] 1.2 Run `uv build --wheel` locally; confirm `dist/*.whl` is produced. Run `uv build` (no flag) and confirm the sdist target produces an empty/nearly-empty tarball OR that hatchling reports the sdist target is fully excluded. Capture transcript for Dev Agent Record.
  - [x] 1.3 This single edit closes the Story 1.1 code-review deferred-work entry "sdist contains 1085 non-package files" (`_bmad-output/implementation-artifacts/deferred-work.md` §1, owner: Story 1.3). Note the closure in this story's Completion Notes.

- [x] **Task 2 — Author `.github/workflows/ci.yml` (AC: #1) — ADR-006**
  - [x] 2.1 Create `.github/workflows/` directory if it does not exist (`mkdir -p .github/workflows`).
  - [x] 2.2 Author `.github/workflows/ci.yml` with the canonical PR-gate shape:
    ```yaml
    name: ci

    on:
      pull_request:
        branches: [main]
      push:
        branches: [main]

    concurrency:
      group: ${{ github.workflow }}-${{ github.ref }}
      cancel-in-progress: true

    permissions:
      contents: read

    jobs:
      quality-gates:
        name: py${{ matrix.python-version }} on ${{ matrix.os }}
        runs-on: ${{ matrix.os }}
        strategy:
          fail-fast: false
          matrix:
            os: [ubuntu-latest, macos-latest]
            python-version: ["3.10", "3.11", "3.12", "3.13"]
        steps:
          - name: Checkout
            uses: actions/checkout@v5  # pin: 11bd71901bbe5b1630ceea73d27597364c9af683

          - name: Install uv (with cache)
            uses: astral-sh/setup-uv@v8  # pin: 08807647e7069bb48b6ef5acd8ec9567f424441b
            with:
              python-version: ${{ matrix.python-version }}
              enable-cache: true
              cache-dependency-glob: |
                **/pyproject.toml
                **/uv.lock

          - name: Sync dev dependencies (frozen)
            run: uv sync --frozen --group dev

          - name: Lint (ruff check)
            run: uv run ruff check src/ tests/

          - name: Format check (ruff format)
            run: uv run ruff format --check src/ tests/ pyproject.toml

          - name: Type check (mypy --strict)
            run: uv run mypy --strict src/

          - name: Unit + integration tests (pytest with coverage gate)
            run: uv run pytest

          - name: Upload coverage XML (for downstream tooling)
            if: always()  # upload even if pytest failed, so reviewers can inspect
            uses: actions/upload-artifact@v4  # pin: ea165f8d65b6e75b540449e92b4886f43607fa02
            with:
              name: coverage-${{ matrix.os }}-py${{ matrix.python-version }}
              path: coverage.xml
              retention-days: 14
              if-no-files-found: ignore  # coverage.xml may not exist on early failure
    ```
  - [x] 2.3 **Why `concurrency.cancel-in-progress: true`**: a developer pushing rapid-fire commits to a PR drops superseded runs; protects free-tier minutes and matches the architecture's "no wasted work" cost discipline.
  - [x] 2.4 **Why pin Action SHAs (in YAML comments)**: GitHub's official supply-chain guidance recommends commit-SHA pins for workflows in security-sensitive repos. v1 keeps the readable `@v8` selector for ergonomics but documents the SHA next to it, so a future Story 1.4 (or a security review) can flip to literal-SHA pins by find-and-replace. ADR-006 records this choice.
  - [x] 2.5 **Why `fail-fast: false`**: when py3.13 fails on macOS, we want to still see whether py3.10 / py3.11 / py3.12 also fail or whether the failure is version-specific. Without `fail-fast: false`, the first cancelled cell hides the pattern.
  - [x] 2.6 Run `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` locally to validate YAML syntax (do **not** add `pyyaml` as a dev dep just for this; either use Python stdlib `yaml` if `pip show pyyaml` shows it's already in the venv from setup-uv's transitive set, or use `python -c "import json, subprocess, sys; ..."` — pragmatic: just push the file and let `actionlint` (run via `uvx` if available) or a real PR run validate it). Document in Dev Agent Record any local validation done.

- [x] **Task 3 — Author `.github/workflows/e2e.yml` (AC: #2) — ADR-007**
  - [x] 3.1 Author `.github/workflows/e2e.yml`:
    ```yaml
    name: e2e

    on:
      schedule:
        - cron: "0 6 * * *"  # 06:00 UTC = 13:00 ICT (Vietnam); align with maintainer's morning review
      workflow_dispatch: {}   # manual trigger for ad-hoc verification

    permissions:
      contents: read

    jobs:
      e2e:
        name: nightly e2e (real claude when available)
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v5

          - uses: astral-sh/setup-uv@v8
            with:
              python-version: "3.12"  # single cell; e2e correctness is not Python-version-sensitive
              enable-cache: true
              cache-dependency-glob: |
                **/pyproject.toml
                **/uv.lock

          - name: Sync dev dependencies (frozen)
            run: uv sync --frozen --group dev

          - name: Detect claude CLI availability
            id: detect-claude
            run: |
              if command -v claude >/dev/null 2>&1; then
                echo "available=true" >> "$GITHUB_OUTPUT"
                echo "Claude CLI detected: $(claude --version 2>&1 || true)"
              else
                echo "available=false" >> "$GITHUB_OUTPUT"
                echo "::notice::Claude CLI not present in runner; e2e suite will be skipped (Epic 2B will provision)."
              fi

          - name: Run e2e suite (only if claude available)
            if: steps.detect-claude.outputs.available == 'true'
            run: uv run pytest tests/e2e -m e2e -v

          - name: Run e2e suite scaffold check (when claude absent)
            if: steps.detect-claude.outputs.available == 'false'
            run: |
              # Substrate-level smoke: confirm the e2e test directory and at least the marker
              # are wired correctly even when claude CLI is absent. Until Story 1.20+ ships
              # real e2e fixtures, this is a no-op that proves the workflow itself is healthy.
              echo "e2e scaffold check (claude absent): pytest collection only"
              uv run pytest tests/e2e --collect-only -q || echo "no e2e tests collected yet (expected pre-Story-1.20)"

          - name: Upload e2e artifacts
            if: always()
            uses: actions/upload-artifact@v4
            with:
              name: e2e-artifacts
              path: |
                tests/e2e/_artifacts/
                pytest-e2e.log
              retention-days: 14
              if-no-files-found: ignore
    ```
  - [x] 3.2 **Why cron `0 6 * * *` UTC**: aligns the nightly run with the start of the maintainer's working day (ICT = UTC+7 → 13:00 local), so failures are visible before the day's main commits land. Document timezone reasoning in ADR-007.
  - [x] 3.3 **Why graceful skip on missing `claude`**: per PRD §531 + Architecture §1219, real Claude Code CI is a **future-state** wiring (Epic 2B, Story 2B-1 ships `ClaudeAIRuntime`). Today's GitHub-hosted runners do **not** have `claude` pre-installed. A red nightly every night until Epic 2B is noise that trains the maintainer to ignore the cron — the antithesis of the "honest signal" architecture (PRD §215, §580). The graceful-skip path keeps the workflow healthy while honestly reporting "real-claude e2e blocked on Epic 2B".
  - [x] 3.4 **Why `tests/e2e -m e2e`**: the `e2e` pytest marker was pre-declared in `[tool.pytest.ini_options] markers` during Story 1.2's code review. The marker expression `-m e2e` ensures unit/integration/property tests don't accidentally run in the e2e job. The `tests/e2e` path filter is belt-and-suspenders.
  - [x] 3.5 Note in ADR-007 that the canonical e2e fixture set (`tests/e2e/fixtures/{greenfield,brownfield,mad-mode}/`) ships in **Stories 1.20 / 3.x / 4.x**, not this one. Story 1.3 establishes the workflow scaffolding; the workflow becomes meaningfully green when Epic 2B + later wire the real-Claude path.

- [x] **Task 4 — Author `.github/workflows/release.yml` (AC: #3) — ADR-008**
  - [x] 4.1 Author `.github/workflows/release.yml`:
    ```yaml
    name: release

    on:
      push:
        tags:
          - "v*.*.*"   # semver tag triggers the publish pipeline; no other event publishes

    permissions:
      contents: read   # default; overridden per-job below

    jobs:
      qa:
        name: full quality gates (pre-publish)
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v5
          - uses: astral-sh/setup-uv@v8
            with:
              python-version: "3.12"
              enable-cache: true
              cache-dependency-glob: |
                **/pyproject.toml
                **/uv.lock
          - run: uv sync --frozen --group dev
          - run: uv run ruff check src/ tests/
          - run: uv run ruff format --check src/ tests/ pyproject.toml
          - run: uv run mypy --strict src/
          - run: uv run pytest

      build:
        name: build wheel
        needs: qa
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v5
          - uses: astral-sh/setup-uv@v8
            with:
              python-version: "3.12"
          - run: uv sync --frozen --group dev

          - name: Assert pyproject.toml version matches the tag
            run: |
              tag_version="${GITHUB_REF_NAME#v}"
              pyproject_version="$(grep -E '^version\s*=' pyproject.toml | head -n1 | cut -d'\"' -f2)"
              echo "tag=$tag_version  pyproject=$pyproject_version"
              if [ "$tag_version" != "$pyproject_version" ]; then
                echo "::error::Tag $GITHUB_REF_NAME does not match pyproject.toml version $pyproject_version"
                exit 1
              fi

          - name: Build wheel only
            run: uv build --wheel

          - name: Upload built wheel
            uses: actions/upload-artifact@v4
            with:
              name: dist
              path: dist/*.whl
              retention-days: 7
              if-no-files-found: error

      publish:
        name: publish to PyPI (trusted publishing)
        needs: build
        runs-on: ubuntu-latest
        environment: pypi   # GitHub Environment named "pypi" — pre-registered as PyPI Trusted Publisher
        permissions:
          id-token: write    # MANDATORY for OIDC trusted publishing
          contents: read
        steps:
          - name: Download built wheel
            uses: actions/download-artifact@v4
            with:
              name: dist
              path: dist

          - name: Publish package distributions to PyPI
            uses: pypa/gh-action-pypi-publish@release/v1
            # NO `with: password:` — OIDC handles authentication via PyPI Trusted Publisher
            # If publishing to TestPyPI for verification first, set:
            #   with:
            #     repository-url: https://test.pypi.org/legacy/
            # See ADR-008 "Test runs against TestPyPI" section.
    ```
  - [x] 4.2 **Why three jobs (`qa` → `build` → `publish`) instead of one**: separation of concerns and minimum-privilege. Only `publish` needs `id-token: write`; `qa` and `build` should not. Splitting also gives a clean re-run target if a single PyPI upload glitches.
  - [x] 4.3 **Why `environment: pypi`**: the GitHub Environment is the trust boundary. PyPI Trusted Publisher binds `<repo>` ↔ `<workflow>` ↔ `<environment>`; using a named environment lets the maintainer add deployment-protection rules later (e.g. required reviewers before publish). Architecture's "PyPI trusted publishing" pre-locks this.
  - [x] 4.4 **Why version-tag assertion**: prevents a footgun where someone tags `v1.0.0` but pyproject.toml still says `0.0.0`. The published wheel filename would be `sdlc_framework-0.0.0-...whl` while the tag claims `1.0.0`, creating exactly the kind of drift the audit chain exists to prevent. AC3 literally requires "the published version matches the tag".
  - [x] 4.5 **One-time external setup** (out-of-scope-for-automation, document in ADR-008):
    1. Maintainer logs into pypi.org → Account → Publishing → Add a new pending publisher.
    2. Project name: `sdlc-framework`. Owner: `Vuonglq01685`. Repo: `SDLC-Framework`. Workflow: `release.yml`. Environment: `pypi`.
    3. (Optional) Repeat against test.pypi.org for staged verification.
    4. In GitHub repo Settings → Environments → create environment named `pypi` (no required reviewers in v0.2; revisit for v1.0.0).
    Note this in ADR-008's "Operator setup" section. The first-ever release will fail with a PyPI 403 if Step 1 is forgotten — the error message ("project not configured for trusted publishing") is the documented signal.
  - [x] 4.6 **Why `uv build --wheel`** (not `uv build`): explicit wheel-only, even though Task 1's sdist exclusion makes plain `uv build` produce a wheel-only result. Belt-and-suspenders — a future regression where someone removes the sdist exclusion still ships wheel-only via this flag. ADR-008 records the redundancy as deliberate.

- [x] **Task 5 — Author `.github/workflows/docs.yml` with mkdocs-absent guard (AC: #4) — ADR-009**
  - [x] 5.1 Author `.github/workflows/docs.yml`:
    ```yaml
    name: docs

    on:
      push:
        branches: [main]
      workflow_dispatch: {}

    permissions:
      contents: read
      pages: write       # required for actions/deploy-pages
      id-token: write    # required for actions/deploy-pages OIDC

    concurrency:
      group: pages
      cancel-in-progress: false  # never interrupt an in-flight Pages deploy

    jobs:
      build:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v5

          - name: Check whether mkdocs.yml exists yet
            id: probe
            run: |
              if [ -f mkdocs.yml ]; then
                echo "ready=true" >> "$GITHUB_OUTPUT"
              else
                echo "ready=false" >> "$GITHUB_OUTPUT"
                echo "::notice::mkdocs.yml absent (Story 1.5 territory); docs build skipped this run."
              fi

          - name: Install uv (only if mkdocs.yml exists)
            if: steps.probe.outputs.ready == 'true'
            uses: astral-sh/setup-uv@v8
            with:
              python-version: "3.12"
              enable-cache: true
              cache-dependency-glob: |
                **/pyproject.toml
                **/uv.lock

          - name: Sync dev dependencies (frozen)
            if: steps.probe.outputs.ready == 'true'
            run: uv sync --frozen --group dev

          - name: Build site (mkdocs --strict)
            if: steps.probe.outputs.ready == 'true'
            run: uv run mkdocs build --strict --site-dir _site

          - name: Configure GitHub Pages
            if: steps.probe.outputs.ready == 'true'
            uses: actions/configure-pages@v5

          - name: Upload Pages artifact
            if: steps.probe.outputs.ready == 'true'
            uses: actions/upload-pages-artifact@v3
            with:
              path: _site

      deploy:
        if: needs.build.result == 'success'
        needs: build
        runs-on: ubuntu-latest
        environment:
          name: github-pages
          url: ${{ steps.deployment.outputs.page_url }}
        permissions:
          pages: write
          id-token: write
        steps:
          - name: Deploy to GitHub Pages
            id: deployment
            uses: actions/deploy-pages@v4
    ```
  - [x] 5.2 **Why the `ready=true|false` probe**: AC4's literal text says "When main is updated → mkdocs builds and publishes". With `mkdocs.yml` absent (Story 1.5 territory), an unguarded build would fail and turn the docs workflow red on every main push from now until Story 1.5 lands. The probe-and-skip pattern makes the workflow honest: it reports "skipped, mkdocs.yml absent" via `::notice::` instead of misleading red-X. Story 1.5 must land mkdocs.yml + the `mkdocs` dev dep; the moment both exist, the next main push activates this workflow with no edits required here.
  - [x] 5.3 **Why `mkdocs build --strict`**: `--strict` turns broken links and unrecognized tokens into hard errors. Architecture §215 "honest signal" applies to docs as much as code — a docs site with broken anchors is misinformation.
  - [x] 5.4 **Why `concurrency.group: pages, cancel-in-progress: false`**: GitHub Pages deployments are global (one live site at a time). Cancelling an in-flight deploy can leave the site in a half-deployed state. Match GitHub's own Pages-deployment best-practice template.
  - [x] 5.5 **Why split `build` and `deploy` jobs**: the build job needs only `contents: read`. `deploy` needs `pages: write` + `id-token: write`. Minimum-privilege isolation.
  - [x] 5.6 **One-time external setup** (out-of-scope-for-automation; document in ADR-009): repo Settings → Pages → Source: "GitHub Actions". The first deploy auto-creates the `github-pages` environment.

- [x] **Task 6 — Author ADR-006, ADR-007, ADR-008, ADR-009 stubs (AC: #1, #2, #3, #4)**
  - [x] 6.1 ADR file naming follows Story 1.2's pattern (Architecture §1027–§1030 canonical filenames):
    - `docs/decisions/ADR-006-ci-yml.md`
    - `docs/decisions/ADR-007-e2e-yml.md`
    - `docs/decisions/ADR-008-release-yml.md`
    - `docs/decisions/ADR-009-docs-yml.md`
  - [x] 6.2 Each stub uses the **Status / Context / Decision / Alternatives / Consequences / Revisit-by** structure (matches ADR-002/003/004 from Story 1.2; mkdocs render comes in Story 1.5/ADR-011).
  - [x] 6.3 **ADR-006-ci-yml.md** content:
    - **Status**: Accepted (2026-05-08, Story 1.3).
    - **Context**: NFR-COMPAT-1 (Python 3.10–3.13 matrix), NFR-COMPAT-2 (macOS + Linux first-class), Architecture §222 (filesystem case-sensitivity matrix), AR-CI (`ci.yml` runs lint → type → unit → integration on PR). Story 1.2 codified the gates in pyproject.toml; this story wires them into CI.
    - **Decision**: 8-cell matrix (Python {3.10, 3.11, 3.12, 3.13} × OS {ubuntu-latest, macos-latest}), `astral-sh/setup-uv@v8` with cache, `uv sync --frozen --group dev` install path, sequential lint → format-check → type → pytest pipeline, `concurrency.cancel-in-progress: true`, `fail-fast: false`, coverage XML uploaded as artifact.
    - **Alternatives considered**: pip + venv (rejected — slower than uv, no native lockfile reproducibility); `actions/setup-python@v5` standalone + manual uv install (rejected — `setup-uv` integrates Python provisioning); single-OS PR + cross-OS nightly (rejected — case-sensitivity bugs are PR-time blockers per Architecture §222).
    - **Consequences**: ~8 minutes per PR run (cache warm); free-tier minutes consumed by every push. Branch protection rule (configured in repo settings, **not** this story) makes the matrix authoritative for merge.
    - **Revisit-by**: 2026-12-01 or when Python 3.14 GA forces matrix expansion or when Windows-via-WSL2 stretch goal lands.
  - [x] 6.4 **ADR-007-e2e-yml.md** content:
    - **Status**: Accepted (2026-05-08, Story 1.3); the workflow ships in scaffold form, becomes meaningfully green once Epic 2B-1 ships ClaudeAIRuntime.
    - **Context**: PRD §531 "framework's CI e2e.yml workflow runs the fixtures nightly against a real claude binary (not on every PR — cost / time tradeoff)"; Architecture §1219; AR-CI nightly E2E mandate.
    - **Decision**: Nightly cron `0 6 * * *` UTC + manual `workflow_dispatch`. Single OS (ubuntu-latest) + single Python (3.12). Graceful skip when `claude` binary absent (current state until Epic 2B). `actions/upload-artifact@v4` retains 14 days. Marker-based test selection (`pytest tests/e2e -m e2e`).
    - **Alternatives considered**: PR-time E2E (rejected — cost; real-Claude billing is per-token per-call); GitHub-hosted runner with custom Claude install per run (rejected — complex, slow, untrusted binary at runner scope); self-hosted runner with `claude` pre-installed (rejected for v0.2 — premature ops complexity; revisit when Epic 2B is real).
    - **Consequences**: For the duration of v0.2 → Epic 2B, the nightly run reports "skipped, claude unavailable" and is honest-green. The first real pass requires Epic 2B-1 + maintainer-side runner provisioning.
    - **Revisit-by**: when Epic 2B-1 (`ClaudeAIRuntime`) lands; the cron/runner choice is re-evaluated then.
  - [x] 6.5 **ADR-008-release-yml.md** content:
    - **Status**: Accepted (2026-05-08, Story 1.3); first activation on `v0.1.0` tag (whenever shipped).
    - **Context**: PRD §503 (trusted publishing, no PYPI_TOKEN), PRD §499 (wheel-only), Architecture §1219, AR-CI release.yml mandate.
    - **Decision**: Three-job pipeline (`qa` → `build` → `publish`). Wheel-only build via `uv build --wheel` + Task 1's sdist exclusion. PyPI authentication via `pypa/gh-action-pypi-publish@release/v1` with `id-token: write` and `environment: pypi`. Tag/pyproject version assertion before build. Trigger: `push.tags: v*.*.*` only (no PR, no manual).
    - **Alternatives considered**: API token in `secrets.PYPI_TOKEN` (rejected — NFR-SEC-1 zero-secrets discipline + drift risk on token rotation); manual `twine upload` from maintainer's laptop (rejected — defeats audit chain); GitHub Releases as the trigger instead of tag push (deferred — release-driven trigger is fine but tag-push is simpler for v0.2; revisit when first release ships).
    - **Consequences**: Zero stored PyPI secrets. The first-ever release **will fail** if the maintainer forgets the one-time PyPI Trusted Publisher registration (documented in "Operator setup" — see Task 4.5). Failed publishes can be re-triggered by re-tagging or by `workflow_dispatch` if added later.
    - **Operator setup** (one-time, must occur before first `v*.*.*` tag): see Task 4.5 procedure.
    - **Revisit-by**: 2027-05-01 or when first migration story (`sdlc migrate-vN`) introduces release-asset shape changes.
  - [x] 6.6 **ADR-009-docs-yml.md** content:
    - **Status**: Accepted (2026-05-08, Story 1.3); active on first push to main after Story 1.5 lands `mkdocs.yml`.
    - **Context**: PRD §580 (`docs.yml` build mkdocs to GitHub Pages on push to main); Architecture §1219; AR-DOCS (`mkdocs.yml` + `docs/` skeleton via ADR-011 / Story 1.5).
    - **Decision**: Two-job pipeline (`build` → `deploy`) using the canonical `actions/configure-pages@v5` + `actions/upload-pages-artifact@v3` + `actions/deploy-pages@v4` chain (modern Pages flow; not `peaceiris/actions-gh-pages`). `mkdocs build --strict`. Probe-and-skip guard handles the Story 1.5 dependency (workflow exists in this story; mkdocs.yml lands later). Trigger: `push.branches: [main]` + manual.
    - **Alternatives considered**: Build directly on the runner without artifact upload (rejected — the canonical Pages flow uses the artifact handoff for atomicity); `peaceiris/actions-gh-pages` (rejected — third-party, less integrated, predates the official chain); deferring docs.yml entirely to Story 1.5 (rejected — AC4 of THIS story explicitly requires the workflow file).
    - **Consequences**: Docs site becomes live the moment Story 1.5 lands. Until then, every main push surfaces a `::notice::mkdocs.yml absent` line in the Actions UI — by design.
    - **Revisit-by**: when first non-ADR doc surface (runbooks, threat-model.md, prompt-library) ships and demands plugin support beyond stock mkdocs.

- [x] **Task 7 — Verification + handoff (AC: all)**
  - [x] 7.1 Local YAML well-formedness check: for each of the four workflow files, run a basic syntax check. The simplest path:
    ```bash
    for f in .github/workflows/*.yml; do
      uv run python -c "import yaml, sys; yaml.safe_load(open('$f')); print('OK', '$f')"
    done
    ```
    Note: `pyyaml` is **not** in `[dependency-groups] dev` and should not be added — it'll come in transitively or via `mkdocs` (Story 1.5). If `pyyaml` is unavailable, an alternative is `python -c "import json; ..."` (no, JSON parser won't help). Pragmatic alternative: use `uvx actionlint` (downloads ephemerally; no project dep change):
    ```bash
    uvx --from actionlint actionlint .github/workflows/*.yml
    ```
    `actionlint` validates both YAML syntax and GitHub Actions semantics (unknown action inputs, expression typos). Capture its output for Dev Agent Record. If `uvx actionlint` fails to run in the dev environment, fall back to syntax-only check via the Python one-liner above using whatever YAML library is available, OR ship the workflow files unvalidated locally and let the **first push to main** be the validation (acceptable for a substrate story; the worst case is one corrective commit).
  - [x] 7.2 **Do NOT run the workflows locally with `act` or similar** — Story 1.3's verification path is the **first push to main** (or a draft PR opened against main), at which point GitHub's built-in YAML parser will accept or reject. If a workflow rejects, fix the YAML and force-push.
  - [x] 7.3 Capture in Dev Agent Record:
    - All four workflow file paths + line counts.
    - All four ADR file paths + line counts.
    - The pyproject.toml diff (sdist exclusion added).
    - The `actionlint` output (or YAML syntax check output) if run locally.
    - Confirmation that pyproject.toml's `[project] version = "0.0.0"` still matches `src/sdlc/__init__.py`'s `__version__ = "0.0.0"` (no version drift introduced).
  - [x] 7.4 Final assertions before commit:
    1. `ls .github/workflows/ci.yml .github/workflows/e2e.yml .github/workflows/release.yml .github/workflows/docs.yml` → all four exist.
    2. `ls docs/decisions/ADR-006-ci-yml.md docs/decisions/ADR-007-e2e-yml.md docs/decisions/ADR-008-release-yml.md docs/decisions/ADR-009-docs-yml.md` → all four exist.
    3. `grep -l 'astral-sh/setup-uv@v8' .github/workflows/ci.yml .github/workflows/e2e.yml .github/workflows/release.yml .github/workflows/docs.yml` → all four match.
    4. `grep 'id-token: write' .github/workflows/release.yml .github/workflows/docs.yml` → at least one match per file.
    5. `grep 'PYPI_TOKEN\|PYPI_API_TOKEN' .github/workflows/release.yml` → **no matches** (NFR-SEC-1 audit; trusted publishing replaces tokens).
    6. `grep 'tool.hatch.build.targets.sdist' pyproject.toml` → matches the new exclusion table.
    7. `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/ pyproject.toml`, `uv run mypy --strict src/`, `uv run pytest` all exit 0 (substrate is still green after pyproject.toml edit).
  - [x] 7.5 Commit message: `feat: add ci/e2e/release/docs github actions workflows + ADR-006/007/008/009 (Story 1.3)`. Conventional commits per NFR-MAINT-6.

## Dev Notes

### Critical context

This is the **third commit of v0.2**. Story 1.1 produced bootstrap (uv + hatchling). Story 1.2 produced quality gates (ruff, mypy --strict, pytest, coverage in `pyproject.toml`). Story 1.3 wires those gates into GitHub Actions across the 8-cell Python × OS matrix, plus three out-of-band pipelines (e2e, release, docs). After Story 1.3, every PR from Story 1.6 onward is provably gated by the same checks the maintainer runs locally — and a tagged release ships a wheel to PyPI with zero stored secrets via OIDC.

The thesis (PRD §215 + §580): the framework that demands deterministic, auditable, multi-agent SDLC governance must hold itself to the same bar from day one. CI is part of the substrate, not a deferred concern.

### What this story is NOT

- **NOT** the place to add `mkdocs.yml`, `docs/index.md`, `docs/architecture-overview.md`, or any plugin-rich docs scaffolding — Story 1.5 (ADR-011). `docs.yml` ships in this story but **gracefully no-ops** until Story 1.5 lands the mkdocs config + dev dep.
- **NOT** the place to add `mkdocs` (or `mkdocs-material`) to `[dependency-groups] dev` — Story 1.5. Story 1.3's `docs.yml` already runs `uv sync --frozen --group dev`; once Story 1.5 adds the dep, the workflow activates with no edit required here.
- **NOT** the place to add `.pre-commit-config.yaml` or the boundary-validator hook — Story 1.4 (ADR-010). CI does NOT shell out to `pre-commit run` because pre-commit is not yet configured. The redundancy between pre-commit-time and CI-time gating is intentional once Story 1.4 lands; for now, CI is the only gate.
- **NOT** the place to add `pytest-benchmark`, `hypothesis`, `pydantic`, or any other production/test deps — Stories 1.6+, 1.10, 1.11.
- **NOT** the place to author `src/sdlc/<submodule>/` content — Stories 1.6+. The 90% coverage threshold from Story 1.2 still holds; CI runs `pytest` against the existing smoke test.
- **NOT** the place to set up branch protection rules in repo settings (Settings → Branches → "Require status checks to pass before merging" → select `quality-gates`) — that is a maintainer / repo-admin one-time action, recorded in ADR-006's "Operator setup" but **not enforceable by code in this story**.
- **NOT** the place to register the PyPI Trusted Publisher (one-time pypi.org account action; documented in ADR-008's "Operator setup" — see Task 4.5).
- **NOT** the place to wire `claude` CLI into runners (Epic 2B). E2E ships with the graceful-skip pattern described in AC2.
- **NOT** the place to add a Windows job to the matrix. Architecture §222 + NFR-COMPAT-2 names macOS + Linux as v1 first-class; native Windows is a v1.x stretch goal.
- **NOT** the place to enable Dependabot, Renovate, or any auto-update bot. Action SHA pinning is documented as a future hardening (revisit ADR-006 when threat surface expands).

### Architecture compliance — what MUST be true after this story

- **Pipeline order**: lint → format-check → type → unit/integration tests, in that exact order, exits 0 on every cell of the 8-cell matrix. Order chosen so the cheapest-fastest checks fail first (ruff is sub-second; mypy is seconds; pytest is dozens of seconds). NFR-MAINT-2 + NFR-MAINT-1 + NFR-MAINT-4.
- **Matrix: Python {3.10, 3.11, 3.12, 3.13} × OS {ubuntu-latest, macos-latest}**: NFR-COMPAT-1 + NFR-COMPAT-2 + Architecture §222. **No Windows cell** (v1.x scope per NFR-COMPAT-2).
- **uv install path = `uv sync --frozen --group dev`**: `--frozen` enforces lockfile reproducibility (matches Story 1.1's "uv.lock as reproducibility contract" decision and Resource Risk R4 mitigation). `--group dev` is the PEP 735 install path Story 1.2 codified; `dev` is the only group declared today.
- **`astral-sh/setup-uv@v8` with cache**: cache-dependency-glob includes both `pyproject.toml` and `uv.lock` per setup-uv's canonical glob list. Caching reduces cold-start cell from ~90s → ~15s on warm cache.
- **Wheel-only release**: `uv build --wheel` + the new `[tool.hatch.build.targets.sdist] exclude = ["**"]` in pyproject.toml together honor PRD §499. The redundancy is deliberate (Task 4.6).
- **PyPI trusted publishing**: `pypa/gh-action-pypi-publish@release/v1` with `id-token: write` + `environment: pypi`. **Zero `secrets.PYPI_TOKEN`** anywhere in the repo (NFR-SEC-1, Architecture §1219).
- **`mkdocs build --strict`**: docs.yml fails on broken anchors / unrecognized tokens (PRD §580 + Architecture §215 honest-signal discipline).
- **Action SHA documentation in YAML comments**: even though `@v8` / `@v5` etc. are the version selectors, the long-form commit SHA appears next to each `uses:` so a future SHA-pinning sweep is a find-and-replace. Rationale recorded in ADR-006.
- **Permissions: minimum-privilege per job**: `contents: read` default; `pages: write` + `id-token: write` only on the docs `deploy` job; `id-token: write` only on the release `publish` job. NFR-SEC-2 spirit.

### Library / framework requirements (versions to assume)

| Action / Tool | Pin | Source |
|---|---|---|
| `actions/checkout` | `@v5` (SHA `11bd71901bbe5b1630ceea73d27597364c9af683` documented in YAML comment) | GitHub canonical; v5 is current as of 2026-05-08 |
| `astral-sh/setup-uv` | `@v8` (SHA `08807647e7069bb48b6ef5acd8ec9567f424441b` = v8.1.0) | Context7 `/astral-sh/setup-uv` — Complete CI Workflow with uv, Test multiple Python versions with a matrix |
| `actions/upload-artifact` | `@v4` (SHA `ea165f8d65b6e75b540449e92b4886f43607fa02`) | GitHub canonical |
| `actions/download-artifact` | `@v4` | GitHub canonical |
| `actions/configure-pages` | `@v5` | GitHub canonical Pages deployment chain |
| `actions/upload-pages-artifact` | `@v3` | GitHub canonical Pages deployment chain |
| `actions/deploy-pages` | `@v4` | GitHub canonical Pages deployment chain |
| `pypa/gh-action-pypi-publish` | `@release/v1` (mutable tag — official PyPA convention; the action team maintains the tag) | Context7 `/websites/pypi` — Publish Package with GitHub Actions Trusted Publisher |
| Python | 3.10, 3.11, 3.12, 3.13 in matrix; 3.12 single-cell on e2e/release/docs | NFR-COMPAT-1 |
| `uv` | latest stable (resolved by setup-uv; no project pin) | Story 1.1 ADR-001 substrate |

**Do NOT add** in this story: `mkdocs`, `mkdocs-material`, any docs plugin (Story 1.5); `pre-commit`, `pyyaml` as a dev dep (transitive only); `pytest-benchmark`, `hypothesis` (later stories); any Windows runner.

### Latest tech information (research summary; 2026-05-08)

- **`astral-sh/setup-uv@v8` is the modern entry point.** v8.1.0 ships native Python provisioning via `python-version`, dependency-glob cache invalidation, and uv-binary caching. The Context7 canonical example (`/astral-sh/setup-uv` → "Complete CI Workflow with uv") matches this story's matrix shape one-to-one. *Source: Context7 `/astral-sh/setup-uv` 2026-05-08 fetch.*
- **`actions/checkout@v5` is current.** v5 (2026 line) replaces v4 with Node 24 runtime. Both work; v5 is GitHub's recommendation for new workflows.
- **`pypa/gh-action-pypi-publish@release/v1` is the canonical PyPI publish action.** The `release/v1` tag is intentionally mutable — the PyPA team updates it for security patches. PyPI documentation explicitly recommends this exact ref. *Source: Context7 `/websites/pypi` → "Publish Package with GitHub Actions Trusted Publisher".*
- **PyPI Trusted Publishing requires three things to align**: (1) the trusted-publisher registration on pypi.org, (2) `permissions: id-token: write` on the publish job, (3) the GitHub Environment named identically to what was registered. The action consumes the OIDC token automatically — **no `with: password:`** clause. *Source: Context7 `/websites/pypi` → "Migrate GitHub Actions to Trusted Publisher Authentication".*
- **GitHub Pages deployment via `actions/deploy-pages@v4`** is the modern flow. Older third-party actions (`peaceiris/actions-gh-pages`) still work but predate the official chain and lack OIDC integration. *GitHub canonical.*
- **`uv sync --frozen` is the CI canonical install command.** `--frozen` rejects any lockfile mutation; if the dependency graph in `pyproject.toml` drifted from `uv.lock`, the sync exits non-zero immediately — a stronger signal than "resolve and proceed".
- **Concurrency cancel-in-progress on PR ref** is GitHub's recommended pattern for cost-conscious matrix runs. The expression `github.workflow}}-${{ github.ref }}` keys per-PR-per-workflow.

### File structure requirements (post-story canonical state)

After Story 1.3 lands, `git ls-files` should show **everything from Stories 1.1 + 1.2** plus:

```
.github/workflows/ci.yml                       # NEW (Task 2)
.github/workflows/e2e.yml                      # NEW (Task 3)
.github/workflows/release.yml                  # NEW (Task 4)
.github/workflows/docs.yml                     # NEW (Task 5)
docs/decisions/ADR-006-ci-yml.md               # NEW (Task 6)
docs/decisions/ADR-007-e2e-yml.md              # NEW (Task 6)
docs/decisions/ADR-008-release-yml.md          # NEW (Task 6)
docs/decisions/ADR-009-docs-yml.md             # NEW (Task 6)
```

`pyproject.toml` is **modified** (adds `[tool.hatch.build.targets.sdist]` table per Task 1). `uv.lock` is **NOT** modified (no dep changes).

**Do NOT** create:
- `.pre-commit-config.yaml` — Story 1.4.
- `mkdocs.yml`, `docs/index.md`, `docs/architecture-overview.md` — Story 1.5.
- `LICENSE` (real SPDX license text) — later v0.2 chore (Story 1.1 deferred-work item #1).
- `src/sdlc/<submodule>/` directories — Stories 1.6+.
- Any pre-commit / hook configuration; any GitHub Actions reusable workflow file (`.github/workflows/_*.yml`); any composite action (`action.yml`).

### Testing requirements

- **No new pytest tests authored in this story.** The CI workflow itself **is** the verification — the first push to main / draft PR exercises every cell in the matrix. There is no local "test for the CI YAML" pattern (and `act` runs are not part of the substrate-level discipline).
- The **negative-test analog** for this story is the Task 7.4 final-assertion grep set (`grep 'PYPI_TOKEN' release.yml` → no match, etc.). These prove the security-relevant invariants without runtime execution.
- **Do not** add a `tests/test_ci_yml_parses.py` or similar metaprogrammatic test. YAML well-formedness is GitHub's job at workflow-load time.

### Previous story intelligence (Stories 1.1 + 1.2 learnings)

From `1-1-project-bootstrap-with-uv-init-hatchling.md` + `1-2-pyproject-toml-quality-gates-configuration.md` Dev Agent Records + Review Findings (last commit `0b4acd9`):

1. **Resolved tool versions actually on disk** (Story 1.2 Dev Agent Record): ruff 0.15.12, mypy 2.0.0, pytest 9.0.3, pytest-cov 7.1.0, coverage 7.13.5. CI install will resolve to these (or newer if uv.lock drifts; `--frozen` prevents drift). When debugging a CI failure that doesn't reproduce locally, the **first** check is whether local venv was synced with `--frozen` — see Task 7.1 for the canonical CI install command.
2. **`uv` host-tool version resolved to 0.11.8** in Story 1.1's environment. `astral-sh/setup-uv@v8.1.0` will install a version close to current stable (0.11.x as of May 2026); the precise version surfaces in `${{ steps.setup-uv.outputs.uv-version }}` (Context7 example shows the print pattern). Not pinned in this story to keep CI on the latest stable uv.
3. **Pytest markers `unit`, `integration`, `property`, `benchmark`, `e2e`** were pre-declared in Story 1.2 Code Review Patch (`[tool.pytest.ini_options] markers`). The e2e workflow's `pytest -m e2e` selector relies on the `e2e` marker existing — confirmed present.
4. **`coverage.xml` is gitignored** (Story 1.2 added it via `.gitignore: .coverage*`). The CI workflow uploads it as an artifact instead of committing it. AC1's coverage-XML upload step is the canonical consumption path.
5. **`docs/ux/dashboard-prototype/` exists from a pre-1.1 UX planning pass** (Story 1.1 admitted-drift item). Ruff's `extend-exclude` already covers it; the docs.yml workflow does **not** specially handle this directory — once Story 1.5 lands `mkdocs.yml`, the maintainer can decide to include or exclude this prototype from the published site.
6. **`license = { text = "TBD" }`** is a known SPDX non-compliance (Story 1.1 deferred-work item #1). PyPI Trusted Publishing **does not require a valid SPDX identifier** to publish, but `twine check dist/*` may warn. ADR-008 should note this is a v0.2 deferred item — a real LICENSE file lands before the first `v*.*.*` tag (otherwise the first release uploads "TBD" license metadata to PyPI, which is embarrassing but not blocking).
7. **`__version__` is currently hardcoded `"0.0.0"`** in both `pyproject.toml` and `src/sdlc/__init__.py` (Story 1.1 Task 3.3 + deferred-work item #3). Task 4.4's tag/pyproject version assertion catches the case where `pyproject.toml` is bumped without a matching tag, but not the dual-source-of-truth drift inside the repo. Mitigation: ADR-001 (Story 1.5) revisits switching to `importlib.metadata.version()`. For Story 1.3, the version-bump step before tagging a release is **a manual maintainer action** — document this in ADR-008's "Operator setup".
8. **Story 1.2's review-style sections** (`## Change Log`, `### Review Findings` with `Decision/Patch/Defer`) are reviewer-populated — DEV agent should leave them blank.

### Coverage interpretation in CI

- The `--cov-fail-under=90` gate is already in `[tool.pytest.ini_options] addopts` (Story 1.2). CI does **not** need to pass `--cov-fail-under` again; `uv run pytest` picks it up automatically.
- The matrix runs pytest 8 times (one per cell). All 8 cells must pass `--cov-fail-under=90` independently; the per-cell coverage measure is uploaded as `coverage-${{ matrix.os }}-py${{ matrix.python-version }}` artifact. Aggregation across cells is **not** done in this story (deferred until non-engine modules ship and per-path thresholds become relevant — see Story 1.2 ADR-004 "Migration path").

### Operator setup (one-time manual actions outside this story's commit scope)

The following are **not enforceable by this story's automation** but are required for the CI/CD pipeline to function end-to-end. ADRs 006/008/009 must each call out their respective setup step.

1. **Branch protection on main** (ADR-006): repo Settings → Branches → Add rule for `main` → Require status checks to pass before merging → select all 8 `quality-gates` matrix cells. Without this, the matrix runs but does not block merge.
2. **PyPI Trusted Publisher registration** (ADR-008): pypi.org → Account → Publishing → register `sdlc-framework` ↔ `Vuonglq01685/SDLC-Framework` ↔ `release.yml` ↔ environment `pypi`. **MUST** complete before first `v*.*.*` tag.
3. **GitHub Environment named `pypi`** (ADR-008): repo Settings → Environments → New environment → name `pypi`. No required reviewers in v0.2.
4. **GitHub Pages source = "GitHub Actions"** (ADR-009): repo Settings → Pages → Source: "GitHub Actions". First successful `docs.yml` deploy auto-creates the `github-pages` environment.

These are documented in the relevant ADRs and listed here as a single checklist for the maintainer's eventual setup pass.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.3] (lines 474–502) — original BDD acceptance criteria.
- [Source: _bmad-output/planning-artifacts/epics.md#Additional-Requirements] (lines 165) — AR-CI mandate (`ci.yml`, `e2e.yml`, `release.yml`, `docs.yml`).
- [Source: _bmad-output/planning-artifacts/architecture.md#Starter-Template-Evaluation] (lines 277–280, 297) — ADR-006/007/008/009 hand-crafted scope.
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete-Project-Directory-Structure] (lines 781–785, 1027–1030) — canonical `.github/workflows/` filenames + ADR filenames.
- [Source: _bmad-output/planning-artifacts/architecture.md#Development-Workflow-Integration] (lines 1219) — release.yml runs full test suite then publishes via trusted publishing.
- [Source: _bmad-output/planning-artifacts/architecture.md#Filesystem-case-sensitivity] (line 222) — macOS + Linux + (future) WSL2 matrix mandate.
- [Source: _bmad-output/planning-artifacts/prd.md#Maintainability-NFRs] (line 853, NFR-COMPAT-1) — Python 3.10/3.11/3.12/3.13 CI matrix.
- [Source: _bmad-output/planning-artifacts/prd.md#NFR-COMPAT-2] (line 854) — macOS + Linux first-class; native Windows out of scope for v1 CI.
- [Source: _bmad-output/planning-artifacts/prd.md#Installation-Methods] (lines 487–505) — wheel-only, hatchling, trusted publishing, no API tokens.
- [Source: _bmad-output/planning-artifacts/prd.md#Code-Examples-Fixtures] (lines 521–531) — nightly E2E against real `claude` binary, not on every PR (cost/time tradeoff).
- [Source: _bmad-output/planning-artifacts/prd.md#CI-CD-for-the-framework-itself] (line 580) — four GitHub Actions workflows enumerated.
- [Source: _bmad-output/implementation-artifacts/1-1-project-bootstrap-with-uv-init-hatchling.md] — Story 1.1 done; substrate baseline.
- [Source: _bmad-output/implementation-artifacts/1-2-pyproject-toml-quality-gates-configuration.md] — Story 1.2 done; quality gates pyproject configuration referenced by ci.yml + release.yml.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] (lines 7–8) — Story 1.1 sdist-suppression deferred to "Story 1.3 (CI/CD pipelines + release.yml)" — closed by this story's Task 1.
- [Context7 `/astral-sh/setup-uv` — Complete CI Workflow with uv] — canonical matrix example.
- [Context7 `/astral-sh/setup-uv` — Test multiple Python versions with a matrix] — Python matrix shape this story mirrors.
- [Context7 `/astral-sh/setup-uv` — Cache dependency glob for pyproject.toml and uv.lock] — `cache-dependency-glob` value reused verbatim.
- [Context7 `/websites/pypi` — Publish Package with GitHub Actions Trusted Publisher] — `pypa/gh-action-pypi-publish@release/v1` + `id-token: write` + `environment: pypi` shape.
- [Context7 `/websites/pypi` — Migrate GitHub Actions to Trusted Publisher Authentication] — explicit "no password:" migration pattern.

## Project Structure Notes

- Alignment with unified project structure (Architecture §781–§785, §1027–§1030): canonical `.github/workflows/{ci,e2e,release,docs}.yml` and `docs/decisions/ADR-{006,007,008,009}-*.md` filenames are honored exactly.
- Detected variance: AC4's literal text "When main is updated → mkdocs builds and publishes" cannot succeed end-to-end until Story 1.5 lands `mkdocs.yml` and the `mkdocs` dev dep. The probe-and-skip pattern in Task 5 is the v0.2-honest interpretation: the workflow file is **configured** (AC4's literal verb), and the build/deploy steps are wired correctly behind a guard that activates the moment Story 1.5's preconditions are met. ADR-009 records this interpretation.
- Detected variance: AC2's literal text "the E2E suite runs against real Claude Code" is graceful-skipped today because no GitHub-hosted runner has `claude` pre-installed (Epic 2B-1 ships ClaudeAIRuntime + the runner provisioning playbook). Same pattern: the workflow is configured and runs honestly; the green-on-real-claude path activates with Epic 2B. ADR-007 records this.
- Architecture §222 names "WSL2 (case-sensitive)" alongside macOS + Linux. Native Windows on the runner matrix is **NOT** in scope for v1 (NFR-COMPAT-2: "native Windows is a v1.x stretch goal"). ADR-006 records the deliberate exclusion.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 (2026-05-08)

### Debug Log References

- Task 1.2: `uv build --wheel` → `dist/sdlc_framework-0.0.0-py3-none-any.whl` (1.2KB). `uv build` → sdist 2.9KB / 4 files (PKG-INFO, pyproject.toml, .gitignore, README.md) confirming near-empty sdist suppression via `exclude = ["**"]`. Original sdist was ~3.3MB / 1085 files.
- Task 2.6 / 7.1: `pyyaml` not in venv (transitive); `uvx actionlint` not in registry. YAML validation path: first push to main per Task 7.2 (acceptable per story spec).
- Task 7: All final assertion checks passed (all 4 workflow files exist, all 4 ADR files exist, all 4 workflows use `astral-sh/setup-uv@v8`, `id-token: write` present in release.yml and docs.yml, no `PYPI_TOKEN` in release.yml, sdist exclusion table in pyproject.toml, all quality gates pass: ruff + mypy + pytest at 100% coverage).
- Version drift check: `pyproject.toml` `0.0.0` == `src/sdlc/__init__.py` `"0.0.0"` — PASS (initial grep returned false positive due to `__all__` line; confirmed with regex-based check).

### Completion Notes List

- **Task 1 closed Story 1.1 deferred-work item #2** ("sdist contains 1085 non-package files"). `[tool.hatch.build.targets.sdist] exclude = ["**"]` added to `pyproject.toml` immediately after `[tool.hatch.build.targets.wheel]`. Verified: `uv build --wheel` produces wheel-only; `uv build` produces minimal 4-file sdist (2.9KB vs original ~3.3MB).
- **Task 2** (ci.yml): 8-cell matrix (Python 3.10/3.11/3.12/3.13 × ubuntu-latest/macos-latest), `fail-fast: false`, `concurrency.cancel-in-progress: true`, `astral-sh/setup-uv@v8` with cache, sequential lint→format→type→pytest pipeline, coverage XML artifact. SHA comments document long-form SHAs for future supply-chain hardening.
- **Task 3** (e2e.yml): Nightly cron `0 6 * * *` UTC (13:00 ICT) + `workflow_dispatch`. Graceful-skip when `claude` absent (detect-claude step + `::notice::`). Scaffold-check runs `pytest --collect-only` when absent. Artifact retention 14 days.
- **Task 4** (release.yml): Three-job pipeline `qa → build → publish`. Full quality gates in `qa` before build. Tag/pyproject version assertion before `uv build --wheel`. `pypa/gh-action-pypi-publish@release/v1` with `id-token: write` + `environment: pypi`. Zero `PYPI_TOKEN`. Minimum-privilege per-job.
- **Task 5** (docs.yml): Two-job pipeline `build → deploy`. `mkdocs.yml` probe-and-skip guard (`ready=true|false`). `actions/configure-pages@v5` + `actions/upload-pages-artifact@v3` + `actions/deploy-pages@v4` modern Pages chain. `mkdocs build --strict`. `concurrency.cancel-in-progress: false` to prevent half-deployed Pages.
- **Task 6** (ADRs): ADR-006 (ci.yml), ADR-007 (e2e.yml), ADR-008 (release.yml), ADR-009 (docs.yml) authored in `docs/decisions/` with Status/Context/Decision/Alternatives/Consequences/Revisit-by structure. Operator setup sections in ADR-006, ADR-008, ADR-009.
- **All quality gates remain green** post-implementation: ruff check, ruff format --check, mypy --strict, pytest (1 test, 100% coverage).
- **No new pytest tests authored** per story spec (Testing requirements section): CI workflow is the verification path.

### File List

**Modified:**
- `pyproject.toml` — added `[tool.hatch.build.targets.sdist] exclude = ["**"]` table (Task 1)

**New:**
- `.github/workflows/ci.yml` — 60 lines (Task 2)
- `.github/workflows/e2e.yml` — 62 lines (Task 3)
- `.github/workflows/release.yml` — 83 lines (Task 4)
- `.github/workflows/docs.yml` — 74 lines (Task 5)
- `docs/decisions/ADR-006-ci-yml.md` — 44 lines (Task 6)
- `docs/decisions/ADR-007-e2e-yml.md` — 34 lines (Task 6)
- `docs/decisions/ADR-008-release-yml.md` — 55 lines (Task 6)
- `docs/decisions/ADR-009-docs-yml.md` — 51 lines (Task 6)

**Unchanged:**
- `uv.lock` — no dependency changes introduced
- `src/sdlc/__init__.py` — no changes
- All other files from Stories 1.1 + 1.2

## Change Log

- 2026-05-08 (Story 1.3): Added `.github/workflows/{ci,e2e,release,docs}.yml` — 4 GitHub Actions pipelines wiring Story 1.2 quality gates into CI across Python 3.10–3.13 × ubuntu/macOS matrix, plus nightly E2E scaffold, tag-driven PyPI trusted-publishing release, and mkdocs-absent-guarded docs publish.
- 2026-05-08 (Story 1.3): Added `[tool.hatch.build.targets.sdist] exclude = ["**"]` to `pyproject.toml` — closes Story 1.1 deferred-work item #2 (wheel-only distribution per PRD §499).
- 2026-05-08 (Story 1.3): Added `docs/decisions/ADR-{006,007,008,009}-*.md` — decision records for all four CI/CD pipelines.
- 2026-05-08 (Story 1.3 review): Applied 19 review patches across `ci.yml`, `e2e.yml`, `release.yml`, `docs.yml`, `pyproject.toml`, ADR-006, ADR-007, ADR-008. Notable behavior changes: docs.yml deploy now gates on the mkdocs probe output (not just `build.result == 'success'`); release.yml gains tag-on-`main` ancestor check + tomllib version assertion + PyPI version-exists pre-flight + `timeout-minutes: 15` on publish; `pypa/gh-action-pypi-publish` pinned to literal SHA `cef221092ed1bacb1cc03d23a2d87d1d172e277b` (ADR-008 deliberate exception to ADR-006 doc-only convention); ci.yml concurrency `cancel-in-progress` now scoped to PR events only; e2e.yml gains tests/e2e directory probe + `--no-cov` + exit-code-5-only allowlist; ADRs synchronized to reflect all wiring. Quality gates green (ruff, mypy --strict, pytest 100% coverage), all 4 workflow YAMLs parse clean.

## Review Findings

_Review run: 2026-05-08, mode=full, 3 reviewers (Blind Hunter, Edge Case Hunter, Acceptance Auditor)._
_Acceptance: all AC1–AC4 PASS (no spec deviations). Findings below are quality, security, and edge-case observations from adversarial review._

### Decisions resolved (2026-05-08)

- D1 → **(a) pin literal SHA for `pypa/gh-action-pypi-publish` only** (highest-value OIDC target; ADR-006 blanket doc-only policy doesn't differentiate by action criticality — this action warrants the exception). Now tracked as a patch below.
- D2 → **(a) accept current 4-file near-empty sdist; rewrite the pyproject.toml comment to match reality** (hatch has no clean "skip sdist" knob; the real barrier is `uv build --wheel` flag in release.yml + AC3 grep assertion). Now tracked as a patch below.
- D3 → **(b) move TestPyPI staged-verification recipe to ADR-008 "Operator setup"; remove commented-out block from `release.yml`** (workflow with `id-token: write` should not host alternative-destination toggles, even commented). Now tracked as a patch below.

### Patch (unambiguous fixes)

- [x] [Review][Patch] **Pin `pypa/gh-action-pypi-publish` to a literal SHA** — `release.yml:285`. Resolves D1(a). Replace `pypa/gh-action-pypi-publish@release/v1` with the SHA literal (looked up at apply time) and keep `# release/v1` as the doc-comment showing the version selector. ADR-008 should record the deliberate exception to ADR-006's doc-only policy for this single highest-value action. **(HIGH)**
- [x] [Review][Patch] **Rewrite the `pyproject.toml` sdist comment to match reality** — `pyproject.toml:12-18`. Resolves D2(a). The "Suppress entirely" claim is wrong; replace with a comment explaining: hatch always emits an sdist target if the table exists, `exclude = ["**"]` produces a near-empty 4-file sdist (PKG-INFO, pyproject.toml, .gitignore, README.md), and the wheel-only guarantee is enforced by `uv build --wheel` in `release.yml` + the AC3 grep assertion. **(LOW)**
- [x] [Review][Patch] **Move TestPyPI staged-verification recipe to ADR-008 and delete commented block from `release.yml`** — `release.yml:286-290` (delete) + `docs/decisions/ADR-008-release-yml.md` "Operator setup" (add). Resolves D3(b). Recipe contents unchanged; new home is the ADR. **(LOW)**

- [x] [Review][Patch] **`docs.yml` `deploy` job runs and fails when `mkdocs.yml` is absent** — `docs.yml:366-379`. All build steps gated `if: ready=='true'` get skipped → job result is `success` → deploy gate `if: needs.build.result == 'success'` passes → `actions/deploy-pages@v4` errors with "Artifact not found". This contradicts ADR-009's "stays green until Story 1.5" claim. Fix: expose `ready` as a `build` job output, then gate deploy on `needs.build.outputs.ready == 'true'`. **(CRITICAL)**
- [x] [Review][Patch] **`release.yml` version-tag assertion is fragile** — `release.yml:248-256`. `cut -d'"'` breaks on single-quoted version strings; `grep -E '^version\s*='` could match a `version =` line in another TOML table; future migration to `dynamic = ["version"]` (foreshadowed by ADR-008) silently fails. Fix: replace with `python -c "import tomllib,sys; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"`. **(CRITICAL)**
- [x] [Review][Patch] **`e2e.yml` `|| echo` swallows ALL pytest exit codes, not just exit-5 "no tests collected"** — `e2e.yml:186-188`. A future broken `tests/e2e/conftest.py`, plugin failure, or import error looks identical to "expected absence". Fix: branch on the actual exit code (allow 0 and 5 only). **(HIGH)**
- [x] [Review][Patch] **`e2e.yml` pytest invocations inherit `--cov-fail-under=90` from `pyproject.toml` `addopts`** — `e2e.yml:178, 187` × `pyproject.toml:121`. E2E tests typically subprocess-launch the CLI, not import `src/sdlc`, so coverage drops well below 90% and pytest fails with exit 2 even when all tests pass. Fix: add `--no-cov` (or `--cov-fail-under=0`) to both pytest invocations in `e2e.yml`. **(HIGH)**
- [x] [Review][Patch] **`e2e.yml` runs `pytest tests/e2e -m e2e -v` when `claude` is available but the directory does not exist** — `e2e.yml:177-178`. Directory `tests/e2e/` is not present in the repo; pytest exits 4 (path error). The moment Epic 2B-1 ships `claude` and Story 1.20 has not landed fixtures yet, every nightly run goes red. Fix: add `[ -d tests/e2e ]` directory probe analogous to docs.yml's mkdocs probe. **(HIGH)**
- [x] [Review][Patch] **`release.yml` re-publishes on tag retag/force-push** — `release.yml:210-213`. PyPI rejects duplicate version with HTTP 400; the build artifact is created but publish fails opaquely deep in the action. Fix: in the `qa` or `build` job, pre-check `pip index versions sdlc-framework` (or equivalent) and exit with `::notice::` if version already exists. **(HIGH)**
- [x] [Review][Patch] **`release.yml` does not validate the tag points to a commit on `main`** — `release.yml:210-213`. `push.tags: v*.*.*` fires regardless of branch; a tag pushed against a feature/personal-branch commit publishes unverified code that never passed the 8-cell PR matrix. Fix: add a step asserting `git merge-base --is-ancestor "$GITHUB_SHA" origin/main`. **(HIGH)**
- [x] [Review][Patch] **`ci.yml` `concurrency.cancel-in-progress: true` cancels in-flight CI on rapid pushes to `main`** — `ci.yml:40-42`. For push events to main, `github.ref == 'refs/heads/main'`; rapid commits cancel each other's CI run. The merged commit ends up with cancelled CI status; branch protection's "passing CI" record is stale. Fix: scope cancellation to PR events only — `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`. **(HIGH)**
- [x] [Review][Patch] **`ci.yml` and `release.yml` pass `pyproject.toml` to `ruff format --check` — no-op** — `ci.yml:111` and `release.yml:233`. Ruff format only handles `.py`/`.pyi`; TOML files are silently skipped. The check appears to enforce TOML formatting but doesn't. Fix: drop `pyproject.toml` from the `ruff format --check` arg list. **(MEDIUM)**
- [x] [Review][Patch] **`e2e.yml` artifact upload references `pytest-e2e.log` but no step writes that path** — `e2e.yml:196`. With `if-no-files-found: ignore`, the missing log fails silently; reviewers expect a log that never exists. Fix: either add `--log-file=pytest-e2e.log` to the pytest invocations, or remove the path from the artifact spec. **(MEDIUM)**
- [x] [Review][Patch] **`release.yml` `build` job's `astral-sh/setup-uv@v8` step omits `enable-cache: true` and `cache-dependency-glob`** — `release.yml:243-246`. Inconsistent with ci.yml/e2e.yml/docs.yml which all enable cache. Architecture-compliance section of the story makes cache mandatory. Fix: add the same cache config block as the other workflows. **(MEDIUM)**
- [x] [Review][Patch] **`e2e.yml` lacks a `concurrency:` block** — `e2e.yml:139-145`. A `workflow_dispatch` triggered minutes before the cron causes two simultaneous runs to upload identically-named artifacts; `actions/upload-artifact@v4` errors on duplicate names within a workflow. Fix: add `concurrency: { group: e2e, cancel-in-progress: false }`. **(MEDIUM)**
- [x] [Review][Patch] **`docs.yml` `deploy` job permissions block omits `contents: read`** — `docs.yml:373-375`. Inconsistent with `release.yml`'s publish job which explicitly lists `contents: read`. Functionally works (deploy-pages doesn't read repo contents) but the convention is split. Fix: add `contents: read` to the deploy-job `permissions:` map. **(MEDIUM)**
- [x] [Review][Patch] **`release.yml` `publish` job lacks `timeout-minutes`** — `release.yml:269-291`. A hung PyPI handshake or unattended environment-protection-rule wait blocks for the GitHub default 6h timeout, burning minutes. Fix: add `timeout-minutes: 15` to the `publish` job. **(MEDIUM)**
- [x] [Review][Patch] **5 actions lack the SHA-pin comment used elsewhere in the workflows** — consistency-only (the comment is doc-only per ADR-006). Affected: `release.yml:281` `actions/download-artifact@v4`; `docs.yml:358` `actions/configure-pages@v5`; `docs.yml:362` `actions/upload-pages-artifact@v3`; `docs.yml:379` `actions/deploy-pages@v4`. (`pypa/gh-action-pypi-publish@release/v1` is its own decision — see D1 above.) Fix: add `# pin: <sha>` comment for each, or skip if D1 chooses option (c) "accept release/v1 + lift the comment convention". **(LOW–MEDIUM)**
- [x] [Review][Patch] **ADR text fixes (combined)** — minor accuracy/clarity nits in the ADR stubs:
  - ADR-006: text says concurrency is "keyed on `workflow-ref`" but the YAML uses a composite expression `${{ github.workflow }}-${{ github.ref }}` — match the wording to the literal.
  - ADR-007: references "Story 1.20+" with no story-index anchor — orphan reference; add a `tests/e2e/README.md` link or backlog reference.
  - ADR-008: references "ADR-001 (Story 1.5)" — ADR-001 is the Story 1.1 substrate ADR; the (Story 1.5) parenthetical is ambiguous. Either remove or rephrase as "revisit per future ADR (Story 1.5)".
  - ADR-008: mentions a `twine check` warning concern but `release.yml` has no `twine check` step — drop the speculative mention or add the step. **(LOW)**

### Deferred (pre-existing or out of current scope)

- [x] [Review][Defer] **Future migration to `dynamic = ["version"]` will break the version-tag assertion** [release.yml:248-256] — addressed by P2 fix above; the dynamic-version migration story should re-verify. — deferred, future-migration concern.
- [x] [Review][Defer] **`release.yml` `qa` job runs single-cell (Python 3.12 / Ubuntu) bypassing the 8-cell PR matrix** [release.yml:204-237] — ADR-008 chose this consciously ("matrix is for catching cross-version regressions on PRs, not for gating release"); related security gap is closed by P7 (tag-on-main check). — deferred, ADR-008 explicit choice.
- [x] [Review][Defer] **`release.yml` qa job duplicates ci.yml's quality-gate command set** [release.yml:218-237 vs ci.yml:104-118] — refactor candidate (`workflow_call` reusable workflow) but neither current bug nor blocker. — deferred, refactor candidate.
- [x] [Review][Defer] **`release.yml` `--frozen` aborts release on stale `uv.lock`** [release.yml:231, 246] — fail-loud is the desired signal; ADR-008 should document this as a release-blocker mode. — deferred, document-only follow-up.
- [x] [Review][Defer] **`ci.yml` artifact name template is fragile if matrix gains a third axis** [ci.yml:122] — currently safe; future-proofing only. — deferred, future-proofing.
- [x] [Review][Defer] **`docs.yml` `concurrency.group: pages` is global; future workflows could collide** [docs.yml:319] — namespace e.g. `pages-prod`. — deferred, future-proofing.

### Dismissed (8) — false positives or design choices

Includes: "uv.lock supply-chain hash verification missing" (uv.lock IS hash-pinned and `--frozen` verifies); Python patch-version pinning (over-specification); cron DST drift (Vietnam/ICT no DST); `if-no-files-found: ignore` on `coverage.xml` (intentional design); top-level vs job-level permissions defensive duplication in docs.yml (harmless); positive INFO confirmations (YAML hygiene clean, no shell injection, all AC PASS).

