# ADR-008: Release Workflow (`release.yml`) — Wheel-Only PyPI Trusted Publishing

**Status:** Accepted (2026-05-08, Story 1.3); first activation on `v0.1.0` tag (whenever shipped).

## Context

PRD §503 mandates trusted publishing with no `PYPI_TOKEN`. PRD §499 mandates wheel-only distribution. Architecture §1219 + AR-CI mandate `release.yml`. NFR-SEC-1 enforces zero-stored-secrets discipline. A tag-driven publish pipeline with OIDC authentication satisfies all three without storing any PyPI credentials in GitHub Secrets.

**Version management note:** `__version__` is currently hardcoded `"0.0.0"` in both `pyproject.toml` and `src/sdlc/__init__.py`. Before pushing the first `v*.*.*` tag, the maintainer must bump both sources to match. A future ADR (planned for Story 1.5) will revisit switching the runtime read to `importlib.metadata.version()` so a single source of truth lives in `pyproject.toml`. This is a manual maintainer action — documented below as "Operator setup".

**License note:** `license = { text = "TBD" }` is a known SPDX non-compliance (Story 1.1 deferred-work item #1). PyPI Trusted Publishing does not block on this. A real LICENSE file should land before the first `v*.*.*` tag.

## Decision

Three-job pipeline: `qa` → `build` → `publish`. Each job uses `astral-sh/setup-uv@v8` with `enable-cache: true` + `cache-dependency-glob` for `pyproject.toml` + `uv.lock` (cache parity with `ci.yml`).

**`qa` job:** Full quality gate sequence (lint → format-check → type → pytest) on `ubuntu-latest` / Python 3.12. Single cell — the matrix is for catching cross-version regressions on PRs, not for gating release; the assumption is that any commit reaching the build job has already passed the 8-cell PR matrix on `main` (enforced by the build job's tag-on-main check below). Only `contents: read` permission.

**`build` job:** Depends on `qa`. Checkout uses `fetch-depth: 0` for full history. Three pre-flight assertions before `uv build --wheel`, in order:

1. **Tag-on-main check** — `git merge-base --is-ancestor "$GITHUB_SHA" origin/main`. Tags pushed against feature-branch or personal commits that never landed on `main` are rejected here, closing the security gap that `push.tags: v*.*.*` would otherwise leave open (workflow fires regardless of branch).
2. **Version match** — `pyproject.toml` `[project] version` parsed via `tomllib` (Python 3.11+, available through the setup-uv 3.12 install) is compared to `${GITHUB_REF_NAME#v}`. The tomllib approach replaces the original `grep | cut -d'"'` so it survives single-quoted versions, comments after the value, and cleanly errors on the future migration to `dynamic = ["version"]`.
3. **PyPI version-exists pre-flight** — `curl` against `https://pypi.org/pypi/sdlc-framework/<version>/json`. A `200` response (force-pushed tag, accidental retag) fails fast with a clear `::error::` rather than letting the publish step fail opaquely with a PyPI 400.

`uv build --wheel` runs only after all three pass (explicit wheel-only, belt-and-suspenders alongside the sdist `exclude = ["**"]`). Uploads `dist/*.whl` as workflow artifact (`retention-days: 7`, `if-no-files-found: error`).

**`publish` job:** Depends on `build`. `timeout-minutes: 15` so a hung PyPI handshake or unattended environment-protection wait fails fast (default GitHub job timeout is 6 hours). Uses GitHub Environment `pypi` (the trust boundary for PyPI Trusted Publisher). Permissions: `id-token: write` + `contents: read`. Downloads artifact, runs `pypa/gh-action-pypi-publish` pinned to a literal SHA (see "Supply-chain pin exception" below) with **no** `with: password:` — OIDC handles authentication automatically.

**Trigger:** `push.tags: v*.*.*` only. No PR trigger, no manual trigger (add `workflow_dispatch` later if re-running a failed publish is needed).

### Supply-chain pin exception (vs [ADR-006](ADR-006-ci-yml.md) doc-only convention)

[ADR-006](ADR-006-ci-yml.md) documents long-form SHAs in `# pin:` comments next to floating-tag `uses:` directives — a deliberate doc-only convention so the repo can find-and-replace to literal SHAs in a future hardening sweep. `release.yml` makes one exception: `pypa/gh-action-pypi-publish` is pinned to a literal SHA (`@<sha> # release/v1`), not just commented. Rationale: this single action holds the OIDC keys to the PyPI project; a compromise of the moving `release/v1` branch would let arbitrary code publish wheels to `sdlc-framework` under our trusted-publisher binding. The asymmetric value justifies the asymmetric pin.

### Operator Setup (one-time, must occur before first `v*.*.*` tag)

1. Log into pypi.org → Account → Publishing → Add a new pending publisher.
   - Project name: `sdlc-framework`
   - GitHub owner: `Vuonglq01685`
   - Repository: `SDLC-Framework`
   - Workflow filename: `release.yml`
   - Environment: `pypi`
2. In GitHub repo Settings → Environments → create environment named `pypi` (no required reviewers in v0.2; revisit for v1.0.0).

**If Step 1 is skipped**, the first publish will fail with PyPI 403 "project not configured for trusted publishing" — this is the documented signal.

#### Optional: TestPyPI staged-verification recipe

Before the very first real publish, the maintainer can stage a verification run against TestPyPI:

1. Repeat Operator Setup Step 1 against test.pypi.org (separate Trusted Publisher pre-registration; same project/owner/repo/workflow values; environment name `testpypi`).
2. Create a temporary branch + workflow override (or a feature-branch copy of `release.yml`) that:
   - Adds `with: { repository-url: https://test.pypi.org/legacy/ }` to the `pypa/gh-action-pypi-publish` step.
   - Switches `environment: pypi` → `environment: testpypi`.
3. Push a throwaway tag (e.g. `v0.0.0-rc.1`) to that branch and observe the publish on test.pypi.org.
4. Tear down the temporary branch and proceed with the real `v*.*.*` tag on `main`.

This recipe lives here (the ADR) instead of as a commented-out block in `release.yml`, because in a workflow with `id-token: write` an inline alternative-destination toggle is a footgun (someone could uncomment the block thinking it's a switch — but the trusted-publisher binding only covers one repository-url, so uncommenting alone won't work and may surface a misleading error).

## Alternatives Considered

- **API token in `secrets.PYPI_TOKEN`**: Rejected — NFR-SEC-1 zero-secrets discipline; tokens require rotation management and drift risk on key rotation cycles.
- **Manual `twine upload` from maintainer's laptop**: Rejected — defeats the audit chain; no reproducible pipeline, no artifact provenance.
- **GitHub Releases as trigger instead of tag push**: Deferred — a release-driven trigger is ergonomically nicer but adds one manual step. Tag push is simpler for v0.2; revisit when first release ships.
- **Single-job pipeline**: Rejected — minimum-privilege isolation requires separating `qa`/`build` (no special permissions) from `publish` (`id-token: write`). Re-run granularity is also cleaner when a single PyPI upload glitches.
- **`uv build` without `--wheel`**: Redundant given Task 1's sdist exclusion, but belt-and-suspenders — a future regression where someone removes the exclusion still ships wheel-only via this flag.

## Consequences

- Zero stored PyPI secrets in the repository.
- The three-job split gives clean re-run targets.
- The version-tag assertion prevents `v1.0.0` tag + `0.0.0` pyproject.toml drift.
- The tag-on-main check makes branch protection on `main` the authoritative gate for what can be released; tags pointing to commits not on `main` are rejected before any wheel is built.
- The PyPI version-exists pre-flight makes accidental retags fail fast with a clear signal instead of an opaque PyPI 400 in the publish step.
- The single-cell `qa` job depends on the assumption that `main` is always green by virtue of branch protection (configured per [ADR-006](ADR-006-ci-yml.md) "Operator setup"). If branch protection is mis-configured to allow non-green merges to `main`, release-time gates are weaker than PR-time gates.
- The literal SHA pin on `pypa/gh-action-pypi-publish` is the one place in the substrate where [ADR-006](ADR-006-ci-yml.md)'s doc-only pin convention is broken. When the action ships a security update, the maintainer must manually look up the new SHA and bump both `release.yml` and the `# release/v1` comment.
- The one-time PyPI Trusted Publisher registration is external and cannot be automated by this story's code; a failed first publish is the expected signal if the maintainer skips it.

## Revisit-by

2027-05-01 — or when the first migration story (`sdlc migrate-vN`) introduces release-asset shape changes requiring sdist or multi-platform wheels.
