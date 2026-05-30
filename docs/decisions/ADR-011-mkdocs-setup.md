# ADR-011: MkDocs Setup

**Status:** Accepted (2026-05-09, Story 1.5); amended 2026-05-29 (Story 2B.7 / CR2B7-W3 — ADR-009 "first non-ADR doc surface" trigger fired; `mkdocs-mermaid2` adopted — see Revision Log).

## Context

AR-DOCS (Additional Requirements) mandates a `mkdocs.yml` site configuration plus a
`docs/` skeleton (architecture overview + numbered ADR log + ADR template). Story 1.3
shipped `docs.yml` ([ADR-009](ADR-009-docs-yml.md)) with a `[ -f mkdocs.yml ]`
probe-and-skip guard, leaving it in `::notice:: skipped` mode until Story 1.5 creates
`mkdocs.yml`.

Story 1.4's deferred-work item "ADR citations to `Architecture §N` and `PRD §N` lack
hyperlinks — Owner: Story 1.5 (ADR-011 / mkdocs ADR template)" requires a hyperlink
discipline decision alongside the site config decision.

NFR-MAINT-5 requires every load-bearing decision recorded as an ADR; this story itself
is the decision it documents.

Key forces:

- `docs.yml` is hard-coded to `mkdocs build --strict --site-dir _site`; local config
  must match or create a "works locally, fails CI" trap.
- MkDocs 1.6+ introduces `validation.anchors: warn` — required for broken-anchor
  detection under `--strict`.
- [ADR-009](ADR-009-docs-yml.md)'s Revisit-by explicitly gates the mkdocs-material upgrade on "first non-ADR
  doc surface ships".
- Planning artifacts (`_bmad-output/planning-artifacts/architecture.md`,
  `_bmad-output/planning-artifacts/prd.md`) live outside `docs_dir` and must NOT be
  included in the published site to avoid leaking BMAD-generation artifacts.

## Decision

The following configuration choices are made for `mkdocs.yml`:

- **`mkdocs>=1.6.0,<2` pin**: Lower bound for `validation.anchors` (MkDocs 1.6
  feature); upper bound `<2` is forward-defensive matching the Story 1.2 `mypy <3`
  and `pytest <10` convention. Lift when MkDocs 2.0 ships and the four-key validation
  block is shown stable. Resolved version on disk: **1.6.1** (from `uv.lock`).
- **`theme: name: readthedocs`**: Stock theme retained. `mkdocs-material` remains deferred per
  [ADR-009](ADR-009-docs-yml.md) revisit-by; however **`mkdocs-mermaid2` is now adopted** (Story
  2B.7, 2026-05-29) because `threat-model.md` ships a Mermaid trust-boundary diagram — the exact
  trigger named in ADR-009's revisit-by. The plugin is theme-agnostic, so `readthedocs` is kept
  and no theme switch is required (`plugins: [search, mermaid2]` in `mkdocs.yml`). See Revision Log.
- **`strict: true`**: Parity with `docs.yml --strict` flag; every validation `warn`
  becomes a hard error.
- **`validation:` four-key block**: `omitted_files: warn`, `absolute_links: warn`,
  `unrecognized_links: warn`, `anchors: warn` — MkDocs 1.6+ recommended strict-
  validation defaults.
- **`nav:` four-surface tree**: Home / Architecture Overview / Decisions (with ADR
  log landing page + 12 ADR files + ADR template).
- **`exclude_docs: ux/`**: Suppresses the pre-existing `docs/ux/dashboard-prototype/`
  tree from `--strict`'s `omitted_files: warn` (it is a working artifact for Stories
  5.x, not a published doc surface). The mkdocs scope is `docs/ux/` and ruff's
  `extend-exclude` in `pyproject.toml` is held to the same `docs/ux/` scope so the
  two tools agree on what is "not source." Future "move prototypes out of `docs_dir`"
  is recorded in `deferred-work.md`.
- **`_site/` gitignored**: Build artifact; never committed. CI builds it at `_site/`
  per [ADR-009](ADR-009-docs-yml.md) `--site-dir _site`.
- **`site_url: https://example.invalid/sdlc-framework/` placeholder**: RFC 2606
  reserved-non-existent TLD; satisfies `--strict` canonical-link requirement without
  forging a real domain. Operator sets real URL at GitHub Pages enablement time.
- **Hyperlink discipline (AC6 scoping)**: Within-`docs/` cross-references (ADR-to-ADR,
  ADR-to-architecture-overview) upgrade from plain text to mkdocs-resolvable Markdown
  links. Cross-references to `_bmad-output/planning-artifacts/architecture.md#Section`
  and `_bmad-output/planning-artifacts/prd.md#Section` remain plain-text `Architecture §N`
  / `PRD §N` citations — planning artifacts are intentionally outside `docs_dir`.
- **`decisions/index.md`**: Added as ADR log landing page (not in Architecture §1019's
  file list, but required for mkdocs collapsible nav and `--strict` link resolution);
  ADR-011 records this as the "navigation landing page convention".
- **No YAML frontmatter in any ADR**: Consistent with the existing eight ADRs; mkdocs
  reads raw Markdown H1 as page title.

## Alternatives Considered

- **`mkdocs-material` shipped now**: Rejected — adds ~15 transitive deps (`babel`,
  `colorama`, `paginate`, `pymdown-extensions`, etc.) without a non-ADR doc surface
  to justify; [ADR-009](ADR-009-docs-yml.md) revisit-by gates the upgrade.
- **Sphinx + reStructuredText**: Rejected — Architecture §239 explicitly excludes
  Sphinx as conflicting with the mkdocs + ruff + hatchling stack.
- **`mdbook` / `docusaurus`**: Rejected — Python-native tooling preferred for the
  framework's ecosystem; mkdocs is the documented AR-DOCS target.
- **Per-ADR YAML frontmatter**: Rejected — the existing eight ADRs ship NO frontmatter;
  consistency outranks the small mkdocs-frontmatter feature gain.
- **Expand `docs_dir` to repo root**: Rejected — would sweep `_bmad/`, `_bmad-output/`,
  `tests/`, `scripts/` into the published site (security + noise risk).
- **Symlink planning artifacts into `docs/`**: Rejected — `mkdocs build --strict` follows
  symlinks into the symlinked directory and would surface every unrelated `_bmad-output/`
  page (sprint-status drafts, story spec markdown) as broken-link sources, failing CI.
  Planning artifacts are git-tracked snapshots, not regenerated on every BMAD run; the
  scoping reason is `--strict` symlink-traversal, not drift.

## Consequences

- `docs.yml` flips from `::notice::mkdocs.yml absent` skip-mode to a live build →
  upload → deploy chain on the next push to `main` after Story 1.5 lands — no workflow
  edit required (the `[ -f mkdocs.yml ]` probe now resolves true).
- The four-key `validation:` block + `strict: true` catches broken anchors at PR time
  per Architecture §215 honest-signal discipline.
- ADR-to-ADR cross-references upgrade from plain text to clickable links.
- The `adr-template.md` enforces the canonical six-section authoring shape going forward.
- `Architecture §N` and `PRD §N` citations stay plain-text — re-emitting planning
  artifacts into `docs/` is a future story (likely v0.6+ when `/sdlc-architect`
  workflow's docs-emission step lands). ADR-011 explicitly records this gap.
- `site_url: https://example.invalid/sdlc-framework/` placeholder requires one-time
  operator edit at GitHub Pages enablement (operator setup; not automatable by Story 1.5).
- Stock `readthedocs` theme is functional but visually plain; upgrade to
  `mkdocs-material` is gated on [ADR-009](ADR-009-docs-yml.md)'s revisit-by trigger.
- Subsequent stories should NOT install `mkdocs-macros-plugin` without revisiting the
  `{{double-brace}}` placeholder convention in `adr-template.md` (mkdocs-macros-plugin
  would interpret `{{NNN}}` as Jinja2 template syntax).

## Revisit-by

2027-05-01 — or when [ADR-009](ADR-009-docs-yml.md)'s "first non-ADR doc surface ships"
trigger fires and `mkdocs-material` / `mkdocs-mermaid2` / `mkdocs-include-markdown-plugin`
become required, or when planning artifacts are re-emitted into `docs/architecture/` and
the AC6 plain-text scoping needs to be lifted, whichever first.

> **Partially actioned 2026-05-29** (see Revision Log): the `mkdocs-mermaid2` half of the
> trigger fired and was adopted. `mkdocs-material` + `mkdocs-include-markdown-plugin` remain
> open under this Revisit-by.

## Revision Log

- **2026-05-29 (Story 2B.7, CR2B7-W3):** Adopted `mkdocs-mermaid2-plugin` (resolved **1.2.3**,
  added to `[dependency-groups] dev` in `pyproject.toml`; `uv.lock` updated) and registered the
  `mermaid2` plugin in `mkdocs.yml` (`plugins: [search, mermaid2]` — `search` re-listed explicitly
  now that a `plugins:` block exists). This fires the [ADR-009](ADR-009-docs-yml.md) / ADR-011
  "first non-ADR doc surface ships" Revisit-by trigger: `docs/threat-model.md` requires a rendered
  Mermaid trust-boundary diagram (Story 2B.7 AC4). The plugin converts ` ```mermaid ` fences to
  `<div class="mermaid">` and injects `mermaid@10.4.0` (ESM, unpkg CDN) at view time;
  `mkdocs build --strict` stays green (exit 0). **Scope limited to `mkdocs-mermaid2`** —
  `mkdocs-material` and `mkdocs-include-markdown-plugin` remain deferred (not yet required). Side
  effect: the previously non-rendering Mermaid diagrams in `docs/sprints/epic-2a-dag.md` and
  `epic-2b-dag.md` now render too. The line 107–109 `mkdocs-macros-plugin` / `{{double-brace}}`
  caveat is unaffected — `mkdocs-mermaid2` does not interpret Jinja syntax (full `--strict` build
  across the ADR template passed). Note: mermaid.js loads from a CDN at view time (acceptable for
  the docs site; vendoring is a possible future hardening).
