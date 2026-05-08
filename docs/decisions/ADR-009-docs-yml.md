# ADR-009: Docs Workflow (`docs.yml`) — MkDocs → GitHub Pages

**Status:** Accepted (2026-05-08, Story 1.3); active on first push to main after Story 1.5 lands `mkdocs.yml`.

## Context

PRD §580 specifies "`docs.yml` build mkdocs to GitHub Pages on push to main". Architecture §1219 + AR-DOCS mandate the docs workflow. Story 1.3's AC4 literally requires the workflow file to be **configured** in this story. However, `mkdocs.yml` and the `mkdocs` dev dependency ship in Story 1.5 (ADR-011) — not this story.

Without a guard, `docs.yml` would fail on every main push from now until Story 1.5 lands, producing chronic red noise in the Actions UI. A probe-and-skip pattern resolves this: the workflow is configured and correct, but gracefully no-ops when `mkdocs.yml` is absent.

**Architecture §215 "honest signal" principle:** A workflow that always fails is noise that trains maintainers to ignore it. A workflow that says "skipped: dependency not yet present" is an honest signal. The `::notice::` path achieves this.

## Decision

Two-job pipeline: `build` → `deploy`.

**`build` job:** Runs on `ubuntu-latest`. A `probe` step checks `[ -f mkdocs.yml ]`:
- If `ready=true`: installs `astral-sh/setup-uv@v8`, runs `uv sync --frozen --group dev`, runs `uv run mkdocs build --strict --site-dir _site`, then uses `actions/configure-pages@v5` + `actions/upload-pages-artifact@v3` to prepare the Pages artifact.
- If `ready=false`: emits `::notice::mkdocs.yml absent (Story 1.5 territory); docs build skipped this run.` All subsequent steps are skipped via `if: steps.probe.outputs.ready == 'true'` guards.

**`deploy` job:** Depends on `build`. Uses GitHub Environment `github-pages` with `pages: write` + `id-token: write` permissions. Runs `actions/deploy-pages@v4`. Condition: `if: needs.build.result == 'success'` — only fires when build job succeeds (which includes the graceful-skip path).

**Concurrency:** `group: pages, cancel-in-progress: false` — never interrupt an in-flight Pages deploy, which can leave the live site in a half-deployed state.

**`mkdocs build --strict`:** Turns broken links and unrecognized tokens into hard errors (Architecture §215 honest-signal discipline applied to docs as much as code).

**Trigger:** `push.branches: [main]` + `workflow_dispatch` (manual ad-hoc trigger).

**Activation path for Story 1.5:** Once `mkdocs.yml` + `mkdocs` dev dep land, the next push to main automatically activates the full build/deploy path — no edit to `docs.yml` required.

### Operator Setup (one-time, not enforceable by this story)

Repo Settings → Pages → Source: "GitHub Actions". The first successful `docs.yml` deploy auto-creates the `github-pages` environment.

## Alternatives Considered

- **Build directly on the runner without artifact upload**: Rejected — the canonical GitHub Pages flow uses the artifact handoff (`upload-pages-artifact` → `deploy-pages`) for atomicity and correct OIDC scope isolation.
- **`peaceiris/actions-gh-pages`**: Rejected — third-party action, predates the official Pages deployment chain, lacks OIDC integration, requires a PAT or deploy key rather than the OIDC flow.
- **Deferring `docs.yml` entirely to Story 1.5**: Rejected — AC4 of this story explicitly requires the workflow file to be **configured** in Story 1.3. Deferring would violate the acceptance criterion.
- **Single-job pipeline**: Rejected — minimum-privilege isolation. `build` job needs only `contents: read`; `deploy` needs `pages: write` + `id-token: write`. Splitting enforces least-privilege per-job.
- **`cancel-in-progress: true` for Pages concurrency**: Rejected — GitHub Pages deployments are global (one live site at a time). Cancelling an in-flight deploy risks leaving the site in a half-deployed state.

## Consequences

- The docs site becomes live the moment Story 1.5 lands `mkdocs.yml` + `mkdocs` dev dep — no edit to `docs.yml` required.
- Until Story 1.5 lands, every main push surfaces a `::notice::mkdocs.yml absent` line in the Actions UI — by design (honest signal, not silent success or noisy failure).
- `mkdocs build --strict` will catch broken anchors and unrecognized plugin tokens from day one, preventing docs rot.

## Revisit-by

When the first non-ADR doc surface (runbooks, threat-model.md, prompt-library) ships and demands plugin support beyond stock mkdocs (e.g. `mkdocs-material`, `mkdocs-mermaid2`). At that point, the `[dependency-groups] dev` entry in `pyproject.toml` gains plugin deps, and this workflow activates them via `uv sync --frozen`.
