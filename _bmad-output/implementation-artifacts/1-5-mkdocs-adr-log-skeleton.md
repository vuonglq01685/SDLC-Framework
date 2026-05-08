# Story 1.5: mkdocs + ADR Log Skeleton

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer following NFR-MAINT-5 (every load-bearing decision has an ADR),
I want a `mkdocs.yml` site configuration plus a `docs/` skeleton (architecture overview + numbered ADR log + ADR template) wired so `uv run mkdocs build --strict` and `uv run mkdocs serve` both succeed against the existing eight ADRs (ADR-002, ADR-003, ADR-004, ADR-006, ADR-007, ADR-008, ADR-009, ADR-010) plus four newly-authored ADRs that pre-stub or back-fill ADR-001 / ADR-005 / ADR-011 / ADR-012,
So that decisions are discoverable, the doc site is publishable from day one, the in-flight `docs.yml` workflow (Story 1.3, ADR-009) flips from "::notice:: skipped" to a live GitHub Pages deploy automatically on the next push to `main`, and Story 1.4's Story-1.5-deferred work (`ADR citations to Architecture §N / PRD §N lack hyperlinks`) is unblocked.

## Acceptance Criteria

**AC1 — `mkdocs.yml` is configured per ADR-011 and `uv run mkdocs build --strict` exits zero against the bootstrapped repo.**
**Given** Story 1.4 complete (eight ADRs already on disk under `docs/decisions/`, `.github/workflows/docs.yml` already shipped per Story 1.3) **AND** `mkdocs>=1.6.0,<2` added to `[dependency-groups] dev` in `pyproject.toml`
**When** I run `uv sync --frozen --group dev` followed by `uv run mkdocs build --strict --site-dir _site`
**Then** the build exits zero — no broken anchors, no unrecognized tokens, no missing-page warnings (`--strict` makes every warning a hard error per ADR-009)
**And** `mkdocs.yml` declares: `site_name: SDLC-Framework`, `site_description`, `repo_url`, `docs_dir: docs`, `site_dir: _site`, `exclude_docs: ux/` (suppresses the pre-existing `docs/ux/dashboard-prototype/` working-artifact tree from the published site; ruff's `pyproject.toml extend-exclude` is held to the same `docs/ux/` scope so the two tools agree — see ADR-011 Decision), `strict: true` (matches the workflow flag), `theme: name: readthedocs` (stock — NO `mkdocs-material` per ADR-009 revisit-by; plugin upgrade is deferred to "first non-ADR doc surface ships"), `validation: omitted_files: warn, absolute_links: warn, unrecognized_links: warn, anchors: warn` (the four-key block from MkDocs 1.6+ recommended strict-validation defaults), and a hand-authored `nav:` tree (see AC2)
**And** `_site/` contains the rendered HTML for every doc (`index.html`, `architecture-overview.html`, `decisions/index.html`, all twelve ADR pages, `decisions/adr-template.html`)
**And** the `_site/` output is added to `.gitignore` (mkdocs build artifact; never committed — the deploy artifact in CI lives at `_site` per ADR-009 `--site-dir _site`)

**AC2 — `docs/` skeleton ships the four required surfaces with the correct nav tree, and every link resolves under `--strict`.**
**Given** mkdocs.yml's `nav:` block authored
**When** I read `mkdocs.yml`
**Then** the navigation is exactly:
```yaml
nav:
  - Home: index.md
  - Architecture Overview: architecture-overview.md
  - Decisions:
      - decisions/index.md
      - ADR-001 — pyproject metadata: decisions/ADR-001-pyproject-metadata.md
      - ADR-002 — ruff config: decisions/ADR-002-ruff-config.md
      - ADR-003 — mypy strict: decisions/ADR-003-mypy-strict.md
      - ADR-004 — pytest config: decisions/ADR-004-pytest-config.md
      - ADR-005 — package_data layout: decisions/ADR-005-package-data-layout.md
      - ADR-006 — ci.yml: decisions/ADR-006-ci-yml.md
      - ADR-007 — e2e.yml: decisions/ADR-007-e2e-yml.md
      - ADR-008 — release.yml: decisions/ADR-008-release-yml.md
      - ADR-009 — docs.yml: decisions/ADR-009-docs-yml.md
      - ADR-010 — pre-commit-config: decisions/ADR-010-pre-commit-config.md
      - ADR-011 — mkdocs setup: decisions/ADR-011-mkdocs-setup.md
      - ADR-012 — module layout: decisions/ADR-012-module-layout.md
      - "ADR template": decisions/adr-template.md
```
**And** `docs/index.md` exists and renders (homepage; brief: "SDLC-Framework documentation. See Architecture Overview and the ADR Log.")
**And** `docs/architecture-overview.md` exists and renders the 16-module DAG summary required by AC4 below
**And** `docs/decisions/index.md` exists as the ADR log landing page (table of contents linking each ADR — see AC4 for shape)
**And** `docs/decisions/adr-template.md` exists with the canonical six-section template (see AC3)
**And** every cross-reference in every ADR markdown body — including the back-references to `Architecture §N` and `PRD §N` that Story 1.4 deferred-work flagged as "lacks hyperlinks" — resolves to a valid relative path or anchor under `--strict` (see AC6)
**And** `mkdocs.yml` itself passes `check-yaml` from Story 1.4's pre-commit hygiene chain (the file lives at repo root and is NOT in the `_bmad/|_bmad-output/|.claude/` exclusion regex, so it WILL be checked — must be valid YAML)

**AC3 — `docs/decisions/adr-template.md` ships the canonical six-section ADR shape, byte-equivalent to the existing ADR-002 / ADR-006 / ADR-010 structure.**
**Given** NFR-MAINT-5 ("every load-bearing decision recorded as an ADR with status, alternatives, consequences, and a revisit-by date")
**When** I open `docs/decisions/adr-template.md`
**Then** the file contains the canonical six-section structure as Markdown headings in this exact order:
  1. `# ADR-NNN: <Title in Title Case>` (H1)
  2. `**Status:** Proposed | Accepted (YYYY-MM-DD, Story X.Y) | Superseded by ADR-MMM | Deprecated`
  3. `## Context` (H2 — what forces are in play, why a decision is needed; cite PRD §, Architecture §, NFR-IDs as required)
  4. `## Decision` (H2 — the actual decision, in declarative present tense)
  5. `## Alternatives Considered` (H2 — bulleted list of options evaluated and rejected, with rationale)
  6. `## Consequences` (H2 — positive + negative outcomes; what this decision unlocks and what it costs)
  7. `## Revisit-by` (H2 — date in `YYYY-MM-DD` form **OR** date `OR` event-condition; per AC5 the date floor is required and must be ≤ 12 months from the ADR's authoring date)
**And** the file body uses placeholder `{{tokens}}` (e.g. `{{title}}`, `{{story_id}}`, `{{authoring_date}}`, `{{revisit_date}}`) so future ADR authors copy-paste-replace
**And** the file declares (in a final HTML comment that does not render): `<!-- Template authoring rules: filename = ADR-NNN-<kebab-slug>.md per Architecture §440. Zero-padded NNN. Status line single-line. Revisit-by accepts a hard date OR a hybrid "DATE OR event-condition" — pure-event revisit-bys are forbidden by NFR-MAINT-5 (see Story 1.5 AC5). -->`
**And** the template's H1 title and `Status:` line are stripped of placeholder noise so a copy-paste workflow yields a working draft after 4–5 token replacements
**And** the template file itself is rendered by mkdocs without warnings under `--strict` (no broken-link tokens, no malformed YAML frontmatter — the file has NO YAML frontmatter; mkdocs reads the raw markdown)

**AC4 — `docs/architecture-overview.md` ships the 16-module DAG summary tied to Architecture §1052–§1112.**
**Given** Story 1.4 implemented the 16-module dependency table as `MODULE_DEPS` in `scripts/check_module_boundaries.py`, and Architecture §1052–§1112 is the source of truth
**When** I open `docs/architecture-overview.md`
**Then** the file contains:
  - A H1 title: `# Architecture Overview`
  - A two-paragraph intro framing the framework as "deterministic orchestration of non-deterministic agents" (per Architecture §215 + §1368) with the three-axis separation (by-space / by-time / by-trust)
  - A `## The 16-Module Dependency DAG` section with a fenced ASCII layer-hierarchy diagram **byte-equivalent** to the diagram at Architecture §1077–§1101 (cli at top → engine/adopt/dashboard → dispatcher/runtime/workflows/specialists → state/journal/hooks/signoff/telemetry → contracts/ids/config/concurrency/errors as foundation)
  - A `## Module Specifications (Summary)` section with a one-row-per-module table covering the same 16 modules in the same order as Architecture §1052–§1071, columns: `Module | Responsibility | Depends on | Forbidden from`. Cell content is a one-line summary of the architecture row (links to §1052 for full detail)
  - A `## Eight Specific Boundary Rules` section listing all eight rules from Architecture §1103, with each rule citing its §-anchor and noting which rules are mechanically enforced by Story 1.4's `boundary-validator` hook (rules #3, #4-partial, #5, #6, #7, #8) vs. which are code-review discipline (#1, #2)
  - A `## Where to Read More` footer linking to Architecture §1052–§1126 (the canonical source for the full module + integration tables) and to ADR-012 (the back-fill ADR Story 1.5 authors below)
**And** the file MUST NOT duplicate the full Architecture §1052–§1112 table verbatim (drift risk per Story 1.4's "two known widenings" note in `_bmad-output/implementation-artifacts/1-4-…md`); the summary row format is the canonical Story 1.5 contribution, with deep-link to the architecture markdown for the full table
**And** every cross-reference uses absolute repo-root-relative paths (e.g. `../../../_bmad-output/planning-artifacts/architecture.md#Module-Specifications` — but see AC6 below for how mkdocs resolves these vs. how the underlying file is laid out)

**AC5 — Every existing ADR has a `revisit-by` date no further than 12 months from authoring date; event-only revisit-bys are upgraded to "DATE OR event" hybrid form.**
**Given** the existing eight ADRs (ADR-002, ADR-003, ADR-004, ADR-006, ADR-007, ADR-008, ADR-009, ADR-010) have these revisit-by values today (verified by `grep -A 4 "## Revisit-by" docs/decisions/*.md`):
  - ADR-002: `2026-12-01 (post-pilot) or sooner if a future ruff release ships a native file-LOC rule` ✓ (date present, ≤ 12 months from 2026-05-08)
  - ADR-003: `2026-12-01 or when adopting Self types or PEP 695 generics` ✓
  - ADR-004: `When first non-engine module (dashboard, Story 5.1) lands…` ✗ (event-only; needs date floor)
  - ADR-006: `2026-12-01 — or when Python 3.14 GA forces matrix expansion…` ✓
  - ADR-007: `When Epic 2B-1 (ClaudeAIRuntime) lands — …` ✗ (event-only; needs date floor)
  - ADR-008: `2027-05-01 — or when the first migration story…` ✓ (3 days outside 12-month window from 2026-05-08; tighten to 2027-05-08 or accept; see Dev Notes)
  - ADR-009: `When the first non-ADR doc surface (runbooks, threat-model.md, prompt-library) ships…` ✗ (event-only; needs date floor)
  - ADR-010: `2026-12-01 OR when Story 2A-2 (specialist registry) lands…` ✓
**When** Story 1.5 lands
**Then** ADR-004, ADR-007, ADR-009 are edited so their `## Revisit-by` section becomes a hybrid "DATE OR event" form using `2027-05-01` as the date floor (12 months from 2026-05-08 minus 7-day safety buffer; see Dev Notes for the floor-selection rationale)
**And** ADR-008's `2027-05-01` is **kept** (it predates this story's authoring date by ~12 months exactly, per Story 1.3; the 3-day overrun versus a strict 12-month-from-2026-05-08 read is accepted because the 12-month rule binds **at authoring time**, not at every-subsequent-story-time — see Dev Notes for the policy)
**And** ADR-002, ADR-003, ADR-006, ADR-010 are **left untouched** (already date-floored within 12 months)
**And** the new ADRs authored in this story (ADR-001, ADR-005, ADR-011, ADR-012) all use `2027-05-01` as their date floor (12 months from this story's authoring date, with consistent floor selection)
**And** the `adr-template.md` (AC3) explicitly forbids pure-event revisit-by in its template-authoring HTML comment ("pure-event revisit-bys are forbidden by NFR-MAINT-5") — the template enforces the discipline going forward
**And** a single grep validation step proves no remaining pure-event revisit-by exists across `docs/decisions/*.md`:
```bash
# Every ADR's Revisit-by section MUST contain at least one ISO date.
for f in docs/decisions/ADR-*.md; do
  awk '/^## Revisit-by$/{flag=1; next} /^## /{flag=0} flag' "$f" | grep -qE '[0-9]{4}-[0-9]{2}-[0-9]{2}' \
    || { echo "FAIL: $f has no ISO date in Revisit-by section"; exit 1; }
done
```

**AC6 — All ADR cross-references and Architecture/PRD §-anchor references are hyperlinked OR explicitly accepted as plain-text citation, satisfying Story 1.4's deferred-work item.**
**Given** Story 1.4's deferred-work item: "ADR citations to `Architecture §N` and `PRD §N` lack hyperlinks" — Owner: Story 1.5 (ADR-011 / mkdocs ADR template) — rewrites ADRs into canonical numbered template with cross-references
**When** I run `uv run mkdocs build --strict` against the post-edit tree
**Then** within-`docs/` cross-references (e.g. ADR → ADR, ADR → architecture-overview.md) are upgraded from plain text to mkdocs-resolvable Markdown links: `[ADR-002](ADR-002-ruff-config.md)` and `[Architecture Overview](../architecture-overview.md)` — these resolve under `--strict`
**And** cross-references to `_bmad-output/planning-artifacts/architecture.md#Section` and `_bmad-output/planning-artifacts/prd.md#Section` are **NOT** rewritten as mkdocs-internal links (the planning artifacts live OUTSIDE `docs_dir: docs` and are explicitly NOT part of the published site — including them would either require expanding `docs_dir` to repo root, OR `nav`-mounting the planning artifacts, both of which violate ADR-011's "minimal stock-mkdocs scope" principle and risk leaking BMAD-generation artifacts into the public docs site)
**And** the citations to Architecture/PRD remain in the existing `Architecture §N` / `PRD §N` plain-text form (matching Story 1.2's ADR convention) **BUT** ADR-011 explicitly records this scoping choice in its "Consequences" section and adds a Revisit-by trigger for the future story that lands a `docs/architecture/` subtree (e.g. when the planning artifact is re-shaped into mkdocs-native pages — likely v0.6+ when the dogfood loop's `/sdlc-architect` workflow lands and re-emits architecture into `docs/`)
**And** any mkdocs-resolvable link upgrade (the ADR-to-ADR rewrites) does NOT alter the textual content of the ADR (still reads the same prose; only adds `[…](…)` syntax around the citation token). Diff is link-only, not prose-edit
**And** `mkdocs build --strict` proves the rewrites work: previously-plain `ADR-007` becomes `[ADR-007](ADR-007-e2e-yml.md)` and resolves; previously-plain `Architecture §1052` stays plain-text (no link target available within `docs_dir`)
**And** the deferred-work file `_bmad-output/implementation-artifacts/deferred-work.md` is updated to mark this item resolved (entry rewritten to `[Resolved by Story 1.5: 2026-MM-DD] …`) — see Tasks below

**AC7 — `uv run mkdocs serve` renders the site at `http://127.0.0.1:8000` (or `localhost:8000`) with the ADR log navigable from the homepage.**
**Given** mkdocs.yml configured per AC1 + AC2
**When** I run `uv run mkdocs serve` from the repo root
**Then** mkdocs binds to `127.0.0.1:8000` and prints `INFO     -  Building documentation...` followed by `INFO     -  [HH:MM:SS] Serving on http://127.0.0.1:8000/`
**And** opening `http://127.0.0.1:8000/` in a browser renders the homepage (`docs/index.md`)
**And** the navigation sidebar shows: `Home`, `Architecture Overview`, `Decisions` (collapsible) — under `Decisions` the twelve ADR entries plus the `decisions/index.md` landing page plus `ADR template` are listed in the order specified in AC2
**And** clicking `ADR-010 — pre-commit-config` navigates to the rendered ADR-010 with all six section headings (Context, Decision, Alternatives, Consequences, Revisit-by) and the Story-1.4-authored body content rendered correctly (no markdown-rendering surprises like `frozenset({...})` python literals being misinterpreted as broken HTML)
**And** the dev server hot-reloads when any `docs/**/*.md` is edited (mkdocs default behavior)
**And** the build is reproducible: stopping serve, running `uv run mkdocs build --strict --site-dir _site` produces `_site/` whose `_site/decisions/ADR-010-pre-commit-config/index.html` is byte-identical to the `mkdocs serve` rendering (modulo the dev-server's `<script>` injection — which is the single documented difference between `mkdocs serve` and `mkdocs build`)

**AC8 — The four newly-authored ADRs (ADR-001, ADR-005, ADR-011, ADR-012) are byte-equivalent in shape to existing ADRs and complete the 1-through-12 sequence.**
**Given** Story 1.5's AC requires "ADRs 001 through 012 are pre-stubbed (one per Story 1.1–1.5 hand-crafted decision)"
**When** I list `docs/decisions/ADR-*.md`
**Then** the directory contains exactly twelve numbered ADR files (no gaps; ADR-013 is owned by Story 1.21 and is intentionally absent):
```
ADR-001-pyproject-metadata.md       # NEW — back-fill of Story 1.1's pyproject [project] metadata decision
ADR-002-ruff-config.md              # existing (Story 1.2)
ADR-003-mypy-strict.md              # existing (Story 1.2)
ADR-004-pytest-config.md            # existing (Story 1.2; revisit-by upgraded per AC5)
ADR-005-package-data-layout.md      # NEW — defer-stub for [tool.hatch.build] package_data (activates Story 1.16+)
ADR-006-ci-yml.md                   # existing (Story 1.3)
ADR-007-e2e-yml.md                  # existing (Story 1.3; revisit-by upgraded per AC5)
ADR-008-release-yml.md              # existing (Story 1.3)
ADR-009-docs-yml.md                 # existing (Story 1.3; revisit-by upgraded per AC5)
ADR-010-pre-commit-config.md        # existing (Story 1.4)
ADR-011-mkdocs-setup.md             # NEW — THIS STORY's load-bearing decision; full ADR
ADR-012-module-layout.md            # NEW — back-fill of Story 1.4's 16-module layout decision
```
**And** each NEW ADR uses the same canonical six-section structure as existing ADRs (Status / Context / Decision / Alternatives Considered / Consequences / Revisit-by), authored under the `## ` H2 heading style ADR-002 + ADR-006 + ADR-010 use (NOT the alternative `### ` H3 style; not the `Status:` colon-on-same-line form variants)
**And** ADR-001 records: PEP 621 `[project]` metadata choices from Story 1.1 (name = `sdlc-framework`, requires-python = `>=3.10`, license `text = "TBD"` placeholder pending the future LICENSE-file chore deferred per Story 1.1 deferred-work, the FR47 PyPI-name vs. import-name decision `sdlc-framework` ↔ `sdlc`, the `__version__` static-vs-dynamic choice from Story 1.1 deferred-work, and the empty `dependencies = []` floor; alternatives include `setuptools` (rejected per Architecture §239), `dynamic = ["version"]` (rejected at Story 1.1 per Story 1.1 deferred-work; tracked for re-evaluation when the first ADR-008 release lands a real version bump). Status line: `Accepted (2026-05-07, Story 1.1; ADR back-filled 2026-05-09, Story 1.5).`
**And** ADR-005 records: `[tool.hatch.build.targets.wheel]` `packages = ["src/sdlc"]` choice from Story 1.1, the **deferred** `package_data` extension covering future `agents/`, `commands/`, `skills/`, `dashboard/`, `workflows/`, `memory/`, `claude_hooks/` (all currently empty per Story 1.4 "Do NOT create" list — activation owned by Story 1.16+ per `pyproject.toml`'s existing TODO comment). Status line: `Accepted partial (2026-05-07, Story 1.1) — package_data extension deferred to Story 1.16+; see Consequences.`
**And** ADR-011 records: the full mkdocs setup decision (this story's own load-bearing decision). Status line: `Accepted (2026-05-09, Story 1.5).` Decision body covers: `mkdocs>=1.6.0,<2` pin (lower bound for `validation.anchors` MkDocs 1.6 feature, upper bound `<2` defensive cap matching ADR-002 / ADR-003 / ADR-004 convention), stock `theme: name: readthedocs` (NO `mkdocs-material` per ADR-009 revisit-by), `strict: true` for parity with `docs.yml --strict` flag, `validation:` four-key block, the four-surface `nav:` tree (Home / Architecture Overview / Decisions / ADR template), the `_site/` gitignore add, the AC6 hyperlink-discipline scoping (within-`docs/` only; planning artifacts stay outside).
**And** ADR-012 records: the 16-module dependency DAG decision (back-fill of Story 1.4's `MODULE_DEPS`). Status line: `Accepted (2026-05-08, Story 1.4; ADR back-filled 2026-05-09, Story 1.5).` Decision body cites Architecture §1052–§1112 as canonical source, references `scripts/check_module_boundaries.py`'s `MODULE_DEPS` dict as the encoded form, lists the eight specific boundary rules from §1103 (verbatim), records the two widenings noted in Story 1.4 (`adopt → cli/git` widened to `adopt → cli`; `dashboard` read-only-vs-state widening), and documents the agents/scripts module entries.
**And** every NEW ADR's body cites its source story, the canonical Architecture §-anchor, and any related `_bmad-output/planning-artifacts/architecture.md#Section` reference (these stay plain-text per AC6 scoping; within-`docs/` references upgrade to links per AC6)

**AC9 — `mkdocs` is added to `[dependency-groups] dev` and `uv.lock` is regenerated; pre-commit chain stays green; `docs.yml` flips from skip-mode to live-deploy automatically on first push to main.**
**Given** Story 1.4's pre-commit chain (ruff-check → ruff-format → mypy-strict → boundary-validator → specialist-validator → hygiene hooks) is the gating local CI
**When** I run `uv run pre-commit run --all-files` after Story 1.5's edits
**Then** every hook exits zero — including `check-yaml` against `mkdocs.yml` at repo root, `check-yaml` against the new `docs/decisions/index.md` if it has YAML frontmatter (it does NOT — index.md is pure markdown), and `trailing-whitespace` + `end-of-file-fixer` against every new markdown file
**And** `pyproject.toml`'s `[dependency-groups] dev` table gains `"mkdocs>=1.6.0,<2"` immediately after `"pre-commit>=4.0.0,<5"` (alphabetic-by-package not enforced; chronological-by-story is the convention Stories 1.2/1.3/1.4 followed)
**And** `uv sync --group dev` (without `--frozen`, this once) regenerates `uv.lock` to include `mkdocs` + transitive deps (`Click`, `Jinja2`, `Markdown`, `MarkupSafe`, `mergedeep`, `packaging`, `PyYAML`, `pyyaml_env_tag`, `watchdog`); the new `uv.lock` is committed
**And** subsequent `uv sync --frozen --group dev` succeeds in CI (every cell of `ci.yml`'s 8-cell matrix) without lockfile drift complaint
**And** the **next push to `main` after Story 1.5 lands** triggers `docs.yml` (Story 1.3) to flip from `::notice::mkdocs.yml absent` skip-mode to a live build → upload-pages-artifact → deploy-pages chain — the workflow's `[ -f mkdocs.yml ]` probe now resolves true; no edit to `docs.yml` required (this is exactly the activation path ADR-009 promises)
**And** the resolved mkdocs version (read from `uv.lock` via `awk '/^name = "mkdocs"$/{getline; print}' uv.lock`) is recorded in ADR-011's Decision section as a footnote (matching Story 1.2's "resolved version on disk" + Story 1.4's "pre-commit 4.6.0" recording convention)
**And** the resolved mkdocs version is **>= 1.6.0** (validated by the constraint above; if uv resolves a 1.5.x for some reason — should not happen with the `>=1.6.0` floor — the build fails AC1 because `validation: anchors: warn` is a 1.6+ feature)

## Tasks / Subtasks

- [x] **Task 1 — Add `mkdocs>=1.6.0,<2` to `[dependency-groups] dev` and regenerate `uv.lock` (AC: #9)**
  - [x] 1.1 Edit `pyproject.toml`'s `[dependency-groups] dev` table; insert `"mkdocs>=1.6.0,<2"` immediately after the existing `"pre-commit>=4.0.0,<5"` entry (chronological-by-story convention — see Dev Notes for the rationale of this ordering vs. strict alphabetic).
  - [x] 1.2 Run `uv sync --group dev` (without `--frozen` this once so the lockfile re-resolves); verify `uv.lock` updates with `mkdocs` + its transitive deps (`Click`, `Jinja2`, `Markdown`, `MarkupSafe`, `mergedeep`, `packaging`, `PyYAML`, `pyyaml_env_tag`, `watchdog`).
  - [x] 1.3 Capture the resolved mkdocs version from `uv.lock` (use `awk '/^name = "mkdocs"$/{getline; print}' uv.lock` — should print `version = "1.6.x"`); paste it into ADR-011's Decision section per AC9.
  - [x] 1.4 Re-run Story 1.2 / 1.4 quality gates locally to confirm no regression: `uv run ruff check src/ tests/ scripts/`, `uv run ruff format --check src/ tests/ scripts/`, `uv run mypy --strict src/`, `uv run pytest`. All must exit 0.
  - [x] 1.5 Re-run Story 1.4 pre-commit chain: `uv run pre-commit run --all-files`. All hooks must pass. (Expect the new `docs/**/*.md` files written by Tasks 2–7 to flow through `trailing-whitespace`, `end-of-file-fixer`, `mixed-line-ending` cleanly.)
  - [x] 1.6 **Why `>=1.6.0`** (not the older 1.4 / 1.5): MkDocs 1.6 introduces the `validation.anchors: warn` and `validation.absolute_links: relative_to_docs` keys we use in `mkdocs.yml`. MkDocs 1.5 lacks `anchors`; 1.4 lacks the `validation:` block entirely. **Why `<2`**: forward-defensive matching Story 1.2's mypy `<3` and pytest `<10` convention. Lift when MkDocs 2.0 ships and is shown to keep the four-key validation block stable.

- [x] **Task 2 — Author `mkdocs.yml` at repo root (AC: #1, #2, #9) — the heart of this story**
  - [x] 2.1 Create `mkdocs.yml` at repo root with the exact shape below (every field load-bearing per ADR-011 + AC1 + AC2):
    ```yaml
    # mkdocs.yml — SDLC-Framework documentation site (ADR-011, Story 1.5).
    # Built locally:  uv run mkdocs build --strict --site-dir _site
    # Served locally: uv run mkdocs serve
    # Auto-deploys via .github/workflows/docs.yml (ADR-009) on push to main.

    site_name: SDLC-Framework
    site_description: Deterministic, auditable, multi-agent SDLC orchestration framework on top of Claude Code.
    site_url: https://example.invalid/sdlc-framework/   # placeholder; rewritten when GitHub Pages domain is finalised
    repo_url: https://github.com/lqvuong/sdlc-framework  # adjust if the actual repo URL differs at story-execution time
    repo_name: sdlc-framework

    docs_dir: docs
    site_dir: _site

    # --strict in CI maps to this top-level flag; keeping them in sync removes the "works
    # locally, fails CI" trap. ADR-011 records the parity choice.
    strict: true

    # MkDocs 1.6+ recommended strict-validation defaults. With strict: true above, every
    # warn becomes a hard error.
    validation:
      omitted_files: warn
      absolute_links: warn
      unrecognized_links: warn
      anchors: warn

    theme:
      name: readthedocs
      # NO mkdocs-material per ADR-009 revisit-by — plugin upgrade is deferred to "first
      # non-ADR doc surface (runbooks, threat-model.md, prompt-library) ships".

    nav:
      - Home: index.md
      - Architecture Overview: architecture-overview.md
      - Decisions:
          - decisions/index.md
          - "ADR-001 — pyproject metadata": decisions/ADR-001-pyproject-metadata.md
          - "ADR-002 — ruff config": decisions/ADR-002-ruff-config.md
          - "ADR-003 — mypy strict": decisions/ADR-003-mypy-strict.md
          - "ADR-004 — pytest config": decisions/ADR-004-pytest-config.md
          - "ADR-005 — package_data layout": decisions/ADR-005-package-data-layout.md
          - "ADR-006 — ci.yml": decisions/ADR-006-ci-yml.md
          - "ADR-007 — e2e.yml": decisions/ADR-007-e2e-yml.md
          - "ADR-008 — release.yml": decisions/ADR-008-release-yml.md
          - "ADR-009 — docs.yml": decisions/ADR-009-docs-yml.md
          - "ADR-010 — pre-commit-config": decisions/ADR-010-pre-commit-config.md
          - "ADR-011 — mkdocs setup": decisions/ADR-011-mkdocs-setup.md
          - "ADR-012 — module layout": decisions/ADR-012-module-layout.md
          - "ADR template": decisions/adr-template.md
    ```
  - [x] 2.2 Add `_site/` to `.gitignore` (the mkdocs build artifact must never be committed; ADR-009 builds it in CI to `_site/` for the upload-pages-artifact step).
  - [x] 2.3 Add `_site/` to ruff's `extend-exclude` in `pyproject.toml`'s `[tool.ruff]` block (defense-in-depth; ruff already excludes generated dirs by default but pre-commit's ruff hook gets explicit list).
  - [x] 2.4 Verify `mkdocs.yml` itself is YAML-valid: `uv run python -c 'import yaml; yaml.safe_load(open("mkdocs.yml"))'` exits zero. Then verify pre-commit's `check-yaml` hook passes against `mkdocs.yml`: `uv run pre-commit run check-yaml --files mkdocs.yml`. (Confirm `check-yaml` is NOT in any exclude regex covering repo-root files.)
  - [x] 2.5 Run `uv run mkdocs build --strict --site-dir _site`. Expect failure on first run because `docs/index.md`, `docs/architecture-overview.md`, `docs/decisions/index.md`, `docs/decisions/adr-template.md`, and the four NEW ADR files do not exist yet — that's expected; Tasks 3–7 author them. Re-run after each task to walk the failure surface down.
  - [x] 2.6 **`site_url` placeholder**: the `site_url: https://example.invalid/sdlc-framework/` placeholder is intentional; it satisfies mkdocs' `--strict` requirement that `site_url` be set (otherwise canonical-link generation fails) without forging a domain that doesn't yet exist. ADR-011's Consequences section flags this as a future-edit when GitHub Pages config completes (operator one-time setup; see ADR-009's "Operator Setup" callout). The `.invalid` TLD is RFC 2606 reserved-non-existent — search engines and link-checkers will not follow it.

- [x] **Task 3 — Author `docs/index.md` and `docs/decisions/index.md` (AC: #2, #6, #7)**
  - [x] 3.1 Create `docs/index.md` with this minimal landing-page shape:
    ```markdown
    # SDLC-Framework

    Deterministic, auditable, multi-agent SDLC orchestration framework on top of Claude Code.

    This documentation site is the human-readable surface for the framework's load-bearing
    architectural decisions and the 16-module dependency DAG that the substrate enforces.

    ## Where to start

    - [Architecture Overview](architecture-overview.md) — the 16-module DAG plus the
      eight specific boundary rules.
    - [ADR Log](decisions/index.md) — every load-bearing decision recorded under
      NFR-MAINT-5, with status, alternatives, consequences, and a revisit-by date.

    ## What lives outside this site

    Planning artifacts (`_bmad-output/planning-artifacts/{prd,architecture,epics,ux-design-specification}.md`)
    and implementation artifacts (`_bmad-output/implementation-artifacts/*.md`) are intentionally
    excluded from the published site — they are working artifacts of the BMAD planning loop, not
    canonical reference material. The Architecture Overview here summarises and links into them
    where useful; ADR-011 Consequences records the scoping choice.
    ```
  - [x] 3.2 Create `docs/decisions/index.md` with this ADR-log landing-page shape (no YAML frontmatter — pure markdown; mkdocs renders the H1 as the page title):
    ```markdown
    # ADR Log

    Every load-bearing architectural decision is recorded as a numbered ADR per
    [NFR-MAINT-5][nfr-link] (every decision recorded with status, context, decision,
    alternatives, consequences, and a revisit-by date).

    [nfr-link]: ../index.md  <!-- placeholder; the real NFR-MAINT-5 anchor lives in the planning artifact, intentionally outside docs_dir — see ADR-011 Consequences -->

    ## Index

    | # | Title | Story | Status |
    |---|---|---|---|
    | [001](ADR-001-pyproject-metadata.md) | pyproject metadata | 1.1 (back-filled in 1.5) | Accepted |
    | [002](ADR-002-ruff-config.md) | ruff config | 1.2 | Accepted |
    | [003](ADR-003-mypy-strict.md) | mypy strict | 1.2 | Accepted |
    | [004](ADR-004-pytest-config.md) | pytest config | 1.2 | Accepted |
    | [005](ADR-005-package-data-layout.md) | package_data layout | 1.1 (deferred to 1.16+) | Accepted partial |
    | [006](ADR-006-ci-yml.md) | ci.yml | 1.3 | Accepted |
    | [007](ADR-007-e2e-yml.md) | e2e.yml | 1.3 | Accepted |
    | [008](ADR-008-release-yml.md) | release.yml | 1.3 | Accepted |
    | [009](ADR-009-docs-yml.md) | docs.yml | 1.3 | Accepted |
    | [010](ADR-010-pre-commit-config.md) | pre-commit config | 1.4 | Accepted |
    | [011](ADR-011-mkdocs-setup.md) | mkdocs setup | 1.5 | Accepted |
    | [012](ADR-012-module-layout.md) | 16-module layout | 1.4 (back-filled in 1.5) | Accepted |

    Note: ADR-013 (wire-format v1 lock) is owned by Story 1.21 and is intentionally absent
    until then.

    ## Authoring a new ADR

    Copy [`adr-template.md`](adr-template.md), bump the number, fill the six sections,
    and add the file to `mkdocs.yml`'s `nav:` block. Filename convention is
    `ADR-NNN-<kebab-slug>.md` (zero-padded `NNN`) per Architecture §440.
    ```
  - [x] 3.3 The placeholder `[nfr-link]` reference in `docs/decisions/index.md` is intentional pass-through: NFR-MAINT-5 lives in `_bmad-output/planning-artifacts/prd.md` (outside `docs_dir`). To avoid `--strict` failure on a dangling external link, the placeholder points back to `../index.md` (a known-good intra-site target) so `--strict` passes; the comment marks it for future when planning artifacts get re-emitted into `docs/`. Alternative: delete the link entirely and use plain `[NFR-MAINT-5]` text — chosen NOT to do this because the whole point of AC6 is to upgrade plain-text references to links where mkdocs can resolve them, and `../index.md` is the closest valid target. ADR-011 records this scoping. (See AC6 final note about Architecture/PRD references staying plain-text — `decisions/index.md` is the one exception that gets a placeholder link to keep `--strict` happy without forging an external resolver.)

- [x] **Task 4 — Author `docs/architecture-overview.md` (AC: #4, #6)**
  - [x] 4.1 Create `docs/architecture-overview.md` with the structure required by AC4. Concrete content outline:
    ```markdown
    # Architecture Overview

    ## Paradigm

    SDLC-Framework treats deterministic orchestration of non-deterministic AI agents as
    a TRIZ-style contradiction. The contradiction is resolved across three axes:

    - **By space**: deterministic mechanics (state machine, dispatcher, journal, hooks)
      live in framework code. Non-deterministic agent reasoning lives behind the
      `AIRuntime` ABC.
    - **By time**: agents propose; framework validates (hash-validated signoffs,
      append-only journal, schema-validated workflows).
    - **By trust**: workflow YAML and specialists are schema-validated trusted inputs;
      agent output is evidence-with-provenance, not ground truth.

    Detailed paradigm framing lives at `_bmad-output/planning-artifacts/architecture.md#Paradigm` (planning-artifact, intentionally outside this site per ADR-011).

    ## The 16-Module Dependency DAG

    Architecture §1052–§1112 specifies the 16-module substrate as a strict DAG. The
    layered hierarchy is:

    ```text
                             cli/                              ← entry points
                              ↓
         ┌────────────────────┼────────────────────┐
         ↓                    ↓                    ↓
      engine/             adopt/              dashboard/
         ↓                    ↓                    ↓
         ├──→ dispatcher/                          │
         │       ↓                                 │
         │     ┌─┴─────────────┐                   │
         │     ↓               ↓                   │
         │  runtime/        workflows/             │
         │                  specialists/           │
         │                                         │
         └──→ hooks/  signoff/  telemetry/         │
                  ↓       ↓          ↓             │
                  └───────┴──────────┴────→ state/ │
                                           journal/←┘
                                              ↓
                                   contracts/  ids/  config/
                                           ↓
                                    concurrency/  errors/
    ```

    The DAG is mechanically enforced by Story 1.4's `boundary-validator` pre-commit
    hook (`scripts/check_module_boundaries.py`), which encodes the dependency table as
    a `MODULE_DEPS` Python literal and AST-walks every changed Python file's imports.
    See [ADR-010](decisions/ADR-010-pre-commit-config.md) and
    [ADR-012](decisions/ADR-012-module-layout.md) for the enforcement mechanism and
    layout decision.

    ## Module Specifications (Summary)

    | Module | Responsibility | Depends on | Forbidden from |
    |---|---|---|---|
    | `errors/` | Exception hierarchy root | (none) | everything (leaf) |
    | `ids/` | Canonical ID parse/build | `errors` | (none beyond) |
    | `contracts/` | 5 wire-format pydantic models | `errors`, `ids` | engine, dispatcher, cli |
    | `config/` | project.yaml + env allow-list + secret sanitiser | `errors`, `contracts` | engine, dispatcher, cli |
    | `concurrency/` | flock + asyncio Semaphore | `errors` | engine, state, journal |
    | `state/` | state.json model + atomic write + projection | `errors`, `contracts`, `concurrency`, `config` | engine, dispatcher, runtime, cli |
    | `journal/` | append-only JSONL | `errors`, `contracts`, `concurrency`, `config` | engine, dispatcher, runtime, cli |
    | `signoff/` | hash-validated signoffs | `errors`, `contracts`, `state`, `journal` | engine, dispatcher, cli |
    | `runtime/` | AIRuntime ABC + Claude impl + mock | `errors`, `contracts`, `concurrency` | engine, dispatcher, state, journal, cli |
    | `workflows/` | workflow YAML loader + static checker | `errors`, `contracts`, `ids` | engine, dispatcher, runtime |
    | `specialists/` | specialist registry + cross-ref | `errors`, `contracts`, `workflows` | engine, dispatcher, runtime |
    | `hooks/` | hook payload + sequential runner + tampering detection | `errors`, `contracts`, `state`, `journal`, `ids` | engine, dispatcher, runtime, cli |
    | `telemetry/` | three observability streams + DORA | `errors`, `contracts`, `journal` | engine, dispatcher, runtime, cli |
    | `dispatcher/` | primary + parallel + synthesizer dispatch | `errors`, `runtime`, `workflows`, `specialists`, `state`, `journal`, `hooks`, `telemetry`, `concurrency` | engine, cli |
    | `engine/` | sync step-machine + auto-loop + STOP triggers + scanner | most lower-stack modules | cli |
    | `adopt/` | 3-pass adopt-mode driver | `errors`, `state`, `journal`, `signoff`, `config`, `cli/git` | engine, dispatcher, runtime |
    | `dashboard/` | local HTTP read-only dashboard | `errors`, `state` (read-only), `journal` (read-only), `telemetry`, `signoff`, `config` | engine, dispatcher, runtime, hooks, adopt |
    | `cli/` | Typer console script + slash command shells | `engine`, `adopt`, `dashboard`, `runtime`, `config`, `errors` | (top of stack) |

    Full per-module API surface and dependency rationale: see
    `_bmad-output/planning-artifacts/architecture.md#Module-Specifications`.

    ## Eight Specific Boundary Rules

    Architecture §1103 names eight specific boundary rules on top of the DAG. Six are
    mechanically enforced by Story 1.4's import-graph validator (rules #3, #4-partial,
    #5, #6, #7, #8); two are runtime-semantics rules best caught by code review (#1,
    #2). [ADR-012](decisions/ADR-012-module-layout.md) documents which rules are
    statically enforced and which are review-only.

    1. `cli/` is the only module that may invoke external binaries other than `runtime/` (review).
    2. `engine/` and `dispatcher/` import `runtime/` only via the `AIRuntime` ABC (review).
    3. `state/` and `journal/` are siblings, not parent-child (statically enforced).
    4. `dashboard/` is read-only with respect to state and journal (statically: no
       imports from `dashboard` to engine/dispatcher; runtime: no `state.atomic` or
       `journal.writer` imports — review-only widening).
    5. `hooks/` does not import `engine/` or `dispatcher/` (statically enforced).
    6. `adopt/` does not import `engine/` or `dispatcher/` (statically enforced).
    7. `workflows/` and `specialists/` do not import `engine/`, `dispatcher/`, or
       `runtime/` (statically enforced).
    8. `contracts/`, `ids/`, `config/`, `concurrency/`, `errors/` form the foundation
       layer (statically enforced).

    ## Where to Read More

    - **Full module table + per-module APIs**: `_bmad-output/planning-artifacts/architecture.md#Module-Specifications`.
    - **Eight boundary rules verbatim**: `_bmad-output/planning-artifacts/architecture.md#Architectural-Boundaries-Import-Rules`.
    - **The validator script**: `scripts/check_module_boundaries.py` (Story 1.4).
    - **The pre-commit configuration**: [ADR-010](decisions/ADR-010-pre-commit-config.md).
    - **The 16-module layout decision**: [ADR-012](decisions/ADR-012-module-layout.md).
    ```
  - [x] 4.2 The ASCII DAG diagram is **byte-equivalent** to Architecture §1077–§1101 — copy-paste, do not reformat. The fenced ` ```text ` block (NOT ` ```python ` or ` ``` `) prevents mkdocs from attempting syntax highlighting.
  - [x] 4.3 Verify the rendering: `uv run mkdocs build --strict --site-dir _site` should now resolve `architecture-overview.md`'s links to ADR-010 and ADR-012; ADR-012 doesn't exist yet (Task 7 below) so the build will still fail on that link until Task 7 lands. That ordering is fine — walk the failure surface incrementally.

- [x] **Task 5 — Author `docs/decisions/adr-template.md` (AC: #3, #5)**
  - [x] 5.1 Create `docs/decisions/adr-template.md` with this exact body (placeholder tokens use `{{double-brace}}` to avoid colliding with mkdocs' template engine — mkdocs default does NOT process `{{}}` as Jinja unless `mkdocs-macros-plugin` is installed, which it is not):
    ```markdown
    # ADR-{{NNN}}: {{Title in Title Case}}

    **Status:** Accepted ({{YYYY-MM-DD}}, Story {{X.Y}})

    ## Context

    {{What forces are in play, why a decision is needed. Cite PRD §N, Architecture §N,
    NFR-IDs as required. Be specific about the constraint that motivates this decision.}}

    ## Decision

    {{The actual decision, in declarative present tense. Be load-bearing — only
    decisions that the substrate's behaviour depends on belong in an ADR.}}

    ## Alternatives Considered

    - **{{Option A}}**: {{Rejected because …}}
    - **{{Option B}}**: {{Rejected because …}}
    - **{{Option C}}**: {{Considered viable but rejected because …}}

    ## Consequences

    - {{Positive consequence 1.}}
    - {{Positive consequence 2.}}
    - {{Negative consequence or trade-off — what this decision costs.}}

    ## Revisit-by

    {{YYYY-MM-DD}} — or when {{specific event triggers re-evaluation}}.

    <!-- Template authoring rules:
         - Filename: ADR-NNN-<kebab-slug>.md per Architecture §440. Zero-padded NNN.
         - Status line is single-line. Use "Superseded by ADR-MMM" when this ADR is
           replaced; "Deprecated" when no successor.
         - Revisit-by accepts a hard date OR a hybrid "DATE OR event-condition" form.
           Pure-event revisit-bys (e.g. "When Epic 2B ships") are FORBIDDEN by
           NFR-MAINT-5 + Story 1.5 AC5 — every ADR must have at least one ISO date
           in its Revisit-by section.
         - The 12-month rule binds at AUTHORING time: the date floor must be no further
           than 12 months from the ADR's authoring date. Subsequent stories should not
           retroactively edit revisit-by dates that were valid at authoring (per Story
           1.5's policy on ADR-008's 2027-05-01 floor).
         - This template file is excluded from the 12-month rule (it is a template, not
           an authored decision).
    -->
    ```
  - [x] 5.2 Verify `mkdocs build --strict` accepts the template (no broken anchor warnings; `{{NNN}}` etc. render as literal text in the published HTML).
  - [x] 5.3 The HTML comment block is the canonical "rules of authorship" — operators reading the source see it; readers of the published site do not (mkdocs strips HTML comments by default). ADR-011's Decision section references this template as "the canonical authoring substrate going forward".

- [x] **Task 6 — Author NEW ADR-001 (back-fill of Story 1.1's pyproject metadata) (AC: #5, #8)**
  - [x] 6.1 Create `docs/decisions/ADR-001-pyproject-metadata.md` with the canonical six-section structure. Status line: `**Status:** Accepted (2026-05-07, Story 1.1; ADR back-filled 2026-05-09, Story 1.5).`
  - [x] 6.2 Context section: cite PRD §137 (Maintainability NFRs), Architecture §272 (ADR-001 row in the hand-craft table), Story 1.1's bootstrap decisions, and the Story 1.1 deferred-work item that names Story 1.5 as the back-fill owner.
  - [x] 6.3 Decision section: list the load-bearing pyproject `[project]` choices from Story 1.1 — `name = "sdlc-framework"`, `version = "0.0.0"` (static placeholder; dynamic-version migration deferred), `description`, `readme = "README.md"`, `license = { text = "TBD" }` (placeholder; the LICENSE-file chore is later in v0.2 per Story 1.1 deferred-work), `authors = [{ name = "Vuonglq01685" }]`, `requires-python = ">=3.10"` (NFR-COMPAT-1 floor), `dependencies = []` (substrate ships with zero runtime deps), the FR47 PyPI-name vs. import-name decision (`sdlc-framework` ↔ `sdlc`).
  - [x] 6.4 Alternatives Considered: `dynamic = ["version"]` via `importlib.metadata` (rejected at Story 1.1; tracked for re-evaluation in ADR-008's first-release context); SPDX license id at substrate-time (deferred to LICENSE-file chore); `setuptools` build-backend (rejected per Architecture §239).
  - [x] 6.5 Consequences: positive (PEP 621 compliance unblocks `uv build --wheel` per Story 1.3 release.yml; `version = "0.0.0"` is honest pre-release signalling); negative (`license = { text = "TBD" }` is not a valid SPDX identifier and PyPI/twine will reject on first publish — owner is the LICENSE-file chore; `__version__` duplication between `pyproject.toml` and `src/sdlc/__init__.py` is intentional Story 1.1 simplification, dynamic source-of-truth is a v1.x candidate).
  - [x] 6.6 Revisit-by: `2027-05-01 — or when ADR-008's first release introduces a real version bump and the dynamic-vs-static __version__ decision needs re-evaluation, or when the LICENSE-file chore lands and the SPDX identifier is filled.` (Per AC5 the date floor is 12 months from this story's authoring date; the 2027-05-01 vs. 2027-05-08 floor selection is documented in Dev Notes.)
  - [x] 6.7 Body uses the AC6 hyperlink discipline: within-`docs/` references upgrade to mkdocs-resolvable links (e.g. `[ADR-008](ADR-008-release-yml.md)`); `Architecture §N`, `PRD §N` stay plain-text per AC6 scoping.

- [x] **Task 7 — Author NEW ADR-005 (defer-stub for package_data layout), ADR-011 (THIS story's load-bearing decision), and ADR-012 (back-fill of Story 1.4's 16-module layout) (AC: #5, #8)**
  - [x] 7.1 **ADR-005**: Create `docs/decisions/ADR-005-package-data-layout.md`. Status line: `**Status:** Accepted partial (2026-05-07, Story 1.1) — package_data extension deferred to Story 1.16+; full back-fill 2026-05-09, Story 1.5.` Context: Architecture §276 specifies hatch `package_data` for `agents/`, `commands/`, `skills/`, `dashboard/`, `workflows/`, `memory/`, `claude_hooks/` — none of which exist yet (Story 1.4 "Do NOT create" list). Decision: ship `[tool.hatch.build.targets.wheel] packages = ["src/sdlc"]` only; the `package_data` extension lands in Story 1.16+ when the first content tree is authored. Alternatives: ship empty placeholder dirs in v0.2 (rejected — empty dirs are not portable across hatch + git); inline `package_data` upfront with `include` patterns (rejected — `include = ["**"]` over an empty tree is a no-op, but accidentally captures future scratch files). Consequences: wheel today contains `sdlc/__init__.py` only (90 B); `src/sdlc/<content-tree>/**` activation is a one-line `pyproject.toml` edit at Story 1.16+. Revisit-by: `2027-05-01 — or when Story 2A-1 (specialist registry) lands and src/sdlc/agents/index.yaml + src/sdlc/agents/**/*.md require package_data inclusion, whichever first.`
  - [x] 7.2 **ADR-011**: Create `docs/decisions/ADR-011-mkdocs-setup.md`. Status line: `**Status:** Accepted (2026-05-09, Story 1.5).` Context: AR-DOCS + NFR-MAINT-5 + Story 1.3's already-shipped ADR-009 docs.yml + Story 1.4 deferred-work item demanding ADR cross-reference hyperlinking. Decision body covers: `mkdocs>=1.6.0,<2` pin + rationale (Task 1.6 wording verbatim), stock `theme: name: readthedocs` (NO `mkdocs-material`; ADR-009 revisit-by gates the upgrade), `strict: true` for parity with `docs.yml --strict`, the four-key `validation:` block (`omitted_files: warn, absolute_links: warn, unrecognized_links: warn, anchors: warn` — MkDocs 1.6+ recommended), the four-surface `nav:` tree (Home / Architecture Overview / Decisions / ADR template), the `_site/` gitignore add, the resolved-version footnote (Task 1.3 result). Alternatives: `mkdocs-material` shipped now (rejected — adds dep churn without a non-ADR doc surface to justify); Sphinx + reStructuredText (rejected — Architecture §239 explicitly excludes Sphinx as conflicting with the mkdocs+ruff+hatchling stack); `mdbook` / `docusaurus` (rejected — Python-native preferred for the framework's ecosystem); per-ADR YAML frontmatter (rejected — the existing eight ADRs ship NO frontmatter, and consistency outranks the small mkdocs-frontmatter feature gain). Consequences: positive (docs.yml flips from skip-mode to live deploy on next push to main without a workflow edit; the four-key validation block + `--strict` catches broken anchors at PR time per Architecture §215 honest-signal discipline; ADR-to-ADR cross-references upgrade from plain text to clickable links per AC6; the `adr-template.md` enforces the canonical six-section authoring shape going forward); negative (Architecture/PRD §-anchor citations stay plain-text per AC6 — re-emitting planning artifacts into `docs/` is a future story; `site_url: https://example.invalid/sdlc-framework/` placeholder is intentional and gets a real domain only after operator GitHub Pages setup; readthedocs theme is functional but visually plain — upgrade to mkdocs-material is gated on ADR-009's revisit-by trigger). Revisit-by: `2027-05-01 — or when ADR-009's "first non-ADR doc surface ships" trigger fires and mkdocs-material / mkdocs-mermaid2 / mkdocs-include-markdown-plugin become required, or when planning artifacts are re-emitted into docs/architecture/ and the AC6 plain-text scoping needs to be lifted, whichever first.`
  - [x] 7.3 **ADR-012**: Create `docs/decisions/ADR-012-module-layout.md`. Status line: `**Status:** Accepted (2026-05-08, Story 1.4; ADR back-filled 2026-05-09, Story 1.5).` Context: AR-MODULES + AR-IMPORT-RULES from epics.md, Architecture §1052–§1112 (16-module DAG + 8 specific rules), Story 1.4's enforcement mechanism via `MODULE_DEPS`. Decision body: cite Architecture §1052–§1112 as canonical source-of-truth; reference `scripts/check_module_boundaries.py`'s `MODULE_DEPS` dict as the encoded form (mechanical enforcement); list all eight §1103 boundary rules verbatim with their §-anchors; record the two widenings noted in Story 1.4's review (`adopt → cli/git` widened to `adopt → cli` at module-level; `dashboard` read-only-vs-state widening); document the `agents` and `scripts` provisional entries added during Story 1.4 review (D5 patch). Alternatives: parsing the architecture markdown at runtime to derive `MODULE_DEPS` (rejected per Story 1.4 — markdown is human-readable, the script needs deterministic typed data; drift detection is a manual review at PR-time when this ADR is updated); a hierarchy-of-namespaces enforcement via Python `__init__.py` `__all__` filters (rejected — leaks dynamic-import bypass paths); fully manual code-review-only enforcement (rejected — week-six refactor pain is the documented failure mode this story's substrate prevents). Consequences: positive (every boundary leak fails pre-commit / CI before week-six refactor pain; the dependency table is now an audit-grade artifact discoverable via the docs site; contract for "where does this go" is unambiguous for Stories 1.6+); negative (manual sync between `scripts/check_module_boundaries.py` `MODULE_DEPS` and Architecture §1052–§1112 is required when either changes — ADR-012 mandates updating both in the same PR; runtime-semantics rules #1, #2, #4-partial stay code-review-only). Revisit-by: `2027-05-01 — or when Story 2A-2 (specialist registry) lands and the "agents" provisional MODULE_DEPS entry needs revision, or when first sub-module-level boundary (e.g. dashboard read-only-vs-write) is encoded statically, whichever first.`
  - [x] 7.4 All three new ADRs use mkdocs-resolvable internal links per AC6 — every `ADR-NNN` token in body prose becomes `[ADR-NNN](ADR-NNN-<slug>.md)`. Plain-text `Architecture §N` / `PRD §N` citations stay plain-text per AC6 scoping.

- [x] **Task 8 — Upgrade revisit-by floors on existing ADRs ADR-004, ADR-007, ADR-009 (AC: #5)**
  - [x] 8.1 **ADR-004**: Edit the `## Revisit-by` section. Current body: `When first non-engine module (dashboard, Story 5.1) lands and the 90% global threshold is too aggressive for that module.` Replace with: `2027-05-01 — or when the first non-engine module (dashboard, Story 5.1) lands and the 90% global threshold is too aggressive for that module, whichever first.`
  - [x] 8.2 **ADR-007**: Current body: `When Epic 2B-1 (ClaudeAIRuntime) lands — the cron frequency, runner choice, and skip strategy are re-evaluated at that milestone.` Replace with: `2027-05-01 — or when Epic 2B-1 (ClaudeAIRuntime) lands and the cron frequency, runner choice, and skip strategy are re-evaluated, whichever first.`
  - [x] 8.3 **ADR-009**: Current body: `When the first non-ADR doc surface (runbooks, threat-model.md, prompt-library) ships and demands plugin support beyond stock mkdocs (e.g. mkdocs-material, mkdocs-mermaid2). At that point, the [dependency-groups] dev entry in pyproject.toml gains plugin deps, and this workflow activates them via uv sync --frozen.` Replace with: `2027-05-01 — or when the first non-ADR doc surface (runbooks, threat-model.md, prompt-library) ships and demands plugin support beyond stock mkdocs (e.g. mkdocs-material, mkdocs-mermaid2), whichever first. At that point, the [dependency-groups] dev entry in pyproject.toml gains plugin deps, and this workflow activates them via uv sync --frozen.`
  - [x] 8.4 ADR-002, ADR-003, ADR-006, ADR-008, ADR-010 are NOT touched (they already date-floor within the 12-month rule per AC5 verification). Specifically: ADR-008's 2027-05-01 is within 12 months from its 2026-05-08 authoring date — the 3-day gap to 2027-05-08 is irrelevant because the 12-month rule binds at authoring time, not at every-subsequent-story time (this is why the new ADR-001/005/011/012 also use 2027-05-01 — consistency, not retroactive enforcement).
  - [x] 8.5 Run the AC5 grep validation snippet to prove no remaining pure-event revisit-by exists:
    ```bash
    for f in docs/decisions/ADR-*.md; do
      awk '/^## Revisit-by$/{flag=1; next} /^## /{flag=0} flag' "$f" \
        | grep -qE '[0-9]{4}-[0-9]{2}-[0-9]{2}' \
        || { echo "FAIL: $f has no ISO date in Revisit-by section"; exit 1; }
    done
    echo "OK: every ADR has at least one ISO date in Revisit-by."
    ```
  - [x] 8.6 Diff the three edited ADRs to confirm only the `## Revisit-by` section bodies changed (`git diff docs/decisions/ADR-{004,007,009}-*.md` — three small hunks, no other prose drift).

- [x] **Task 9 — Upgrade ADR cross-reference plain-text → mkdocs-resolvable links per AC6 (AC: #6)**
  - [x] 9.1 Walk every ADR markdown body (`docs/decisions/ADR-*.md` after Tasks 6+7+8 land) and identify `ADR-NNN` plain-text tokens that point to within-`docs/decisions/` ADRs.
  - [x] 9.2 Rewrite each in-doc `ADR-NNN` token (excluding the H1 title and the Status line — those are self-references and stay plain) into a Markdown link: `[ADR-NNN](ADR-NNN-<slug>.md)`. Preserve surrounding prose verbatim (no word changes — link wrap only).
  - [x] 9.3 ADR-006 references `ADR-001` (uv substrate) and `ADR-008` (release.yml SHA pin) → upgrade to `[ADR-001](ADR-001-pyproject-metadata.md)` and `[ADR-008](ADR-008-release-yml.md)`.
  - [x] 9.4 ADR-008 references `ADR-006` (matrix is for catching cross-version regressions on PRs) → upgrade.
  - [x] 9.5 ADR-009 references `ADR-011` (mkdocs.yml lands in Story 1.5) and `Story 1.5 (ADR-011)` → upgrade the ADR-011 anchor; the "Story 1.5" plain text stays as-is (story IDs are not link targets within `docs/`).
  - [x] 9.6 ADR-010 references `ADR-002` (ruff version pin sync), `ADR-006` (CI's parallel mypy choice), `ADR-012` (Story 1.5's module-layout ADR) → upgrade.
  - [x] 9.7 ADR-002 references future `Story 1.4 (ADR-010)` → upgrade ADR-010 anchor.
  - [x] 9.8 ADR-004 references `ADR-002` style, `ADR-003` strict-mode (in Context section if present) → upgrade.
  - [x] 9.9 Run `uv run mkdocs build --strict --site-dir _site`. Every link must resolve. If `--strict` flags an unrecognized anchor, the link is malformed (most likely a slug typo — verify against the actual filename).
  - [x] 9.10 Plain-text `Architecture §N`, `PRD §N`, `NFR-XXX-N`, `FR-N` citations remain plain text — AC6 scoping. ADR-011's Consequences section explicitly records this as a "future-story re-emission" gap.
  - [x] 9.11 The Story 1.4 deferred-work file gets updated: edit `_bmad-output/implementation-artifacts/deferred-work.md`, find the line "ADR citations to `Architecture §N` and `PRD §N` lack hyperlinks ... Owner: Story 1.5 (ADR-011 / mkdocs ADR template)", and prepend `[Resolved by Story 1.5: 2026-05-09 — within-docs/ ADR-to-ADR links upgraded; Architecture/PRD §-anchors stay plain-text per ADR-011 Consequences scoping]` to the bullet (preserve surrounding entries).

- [x] **Task 10 — End-to-end verification: `mkdocs build --strict` + `mkdocs serve` + pre-commit + `docs.yml` rehearsal (AC: #1, #7, #9)**
  - [x] 10.1 Run `uv run mkdocs build --strict --site-dir _site` from repo root. Expected output: `INFO     -  Cleaning site directory` + `INFO     -  Building documentation to directory: <repo>/_site` + zero warnings + zero errors. Build completes in <2 seconds (small site).
  - [x] 10.2 Inspect `_site/`: should contain `index.html`, `architecture-overview/index.html`, `decisions/index.html`, `decisions/ADR-{001..012}-…/index.html` (12 ADR pages), `decisions/adr-template/index.html`, plus mkdocs theme assets (`assets/`, `js/`, `css/`, `404.html`, `search/search_index.json`, `sitemap.xml`, `sitemap.xml.gz`).
  - [x] 10.3 Run `uv run mkdocs serve` in a separate terminal. Expect output `INFO     -  [HH:MM:SS] Serving on http://127.0.0.1:8000/`. Open the URL in a browser; verify nav sidebar shows `Home`, `Architecture Overview`, `Decisions` (collapsible). Click into ADR-010 — should render Story 1.4's authored body cleanly (no markdown-rendering surprises on the `frozenset({...})` Python literals or the boundary-rule table).
  - [x] 10.4 Smoke-edit a markdown file (e.g. add a trailing space to `docs/index.md`) and verify mkdocs serve hot-reloads (the browser auto-refreshes within ~1 second). Then revert the edit.
  - [x] 10.5 Stop `mkdocs serve` (Ctrl-C). Re-run `uv run mkdocs build --strict --site-dir _site`. Confirm reproducibility (same HTML byte-output as 10.1 modulo the dev-server's `<script>` injection — `_site/index.html` from `mkdocs build` should NOT contain the `<script src="/livereload.js"></script>` tag that `mkdocs serve` injects).
  - [x] 10.6 Run the full pre-commit chain: `uv run pre-commit run --all-files`. Every hook must exit 0. Specific checks: `check-yaml mkdocs.yml` passes; `trailing-whitespace` and `end-of-file-fixer` pass against every new `docs/**/*.md` and against the three edited ADRs (004, 007, 009).
  - [x] 10.7 Run the AC9 docs.yml rehearsal: `act -j build -W .github/workflows/docs.yml` if `act` is installed, OR alternatively manually walk the workflow's probe step + build-strict step + upload-pages-artifact step and confirm no probe failure. (`act` is a dev-only optional tool; if unavailable, document in Dev Agent Record.) On the actual next push to `main`, `docs.yml` should flip from `::notice::mkdocs.yml absent` to a successful build → upload → deploy chain.
  - [x] 10.8 Run the AC5 grep validation one more time end-to-end (12 ADRs, all date-floored). Final assertion: `for f in docs/decisions/ADR-*.md; do awk '/^## Revisit-by$/{flag=1; next} /^## /{flag=0} flag' "$f" | grep -qE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || { echo "FAIL: $f"; exit 1; }; done && echo "OK: 12 ADRs, all date-floored."`
  - [x] 10.9 Final assertion checklist (mirror of Story 1.4's Task 8 closing verification):
    1. `uv run mkdocs build --strict --site-dir _site` exits 0.
    2. `_site/decisions/` contains 12 ADR pages + 1 template page + 1 index page.
    3. `uv run mkdocs serve` binds to 127.0.0.1:8000 and renders the homepage.
    4. `uv run pre-commit run --all-files` exits 0.
    5. `uv run pytest` exits 0 (no test impact, but confirm regression-free).
    6. `uv run mypy --strict src/` exits 0 (no source change, but confirm regression-free).
    7. The grep validation script in Task 10.8 prints `OK: 12 ADRs, all date-floored.`
    8. `git diff --stat` shows the expected file set per the File List below — no surprise edits.
    9. `_bmad-output/implementation-artifacts/deferred-work.md` line for the "ADR cross-references lack hyperlinks" item is marked `[Resolved by Story 1.5: …]`.
   10. The next push to main triggers `docs.yml` to perform a real build + deploy (verified out-of-band on the GitHub UI; not a local-test gate).

### Review Findings

Code review run 2026-05-08. 3 adversarial layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor). 42 raw findings → 33 unified after dedup. 5 decision-needed, 15 patch, 6 deferred, 7 dismissed.

**Decision-needed (resolved 2026-05-08; converted to patches P16–P20):**

- [x] [Review][Decision] **D1 — ADR-005 status-line wording** → resolved: hybrid form `... deferred to Story 1.16+; back-filled 2026-05-09, Story 1.5; see Consequences.` (preserves AC8 trailer + back-fill timestamp). See P16.
- [x] [Review][Decision] **D2 — `mkdocs.yml` `exclude_docs:` block** → resolved: amend AC1 (record `exclude_docs` as expected field) + add ADR-011 entry documenting the mechanism. Future "move dashboard-prototype out of `docs_dir`" goes to deferred-work. See P17.
- [x] [Review][Decision] **D3 — ADR-002 link upgrade prose-edit** → resolved: restructure ADR-002 prose so `[ADR-010](...)` is integrated as a single inline link, no double-paren. See P18.
- [x] [Review][Decision] **D4 — ADR-009 Revisit-by hybrid framing** → resolved: rewrite as explicit hybrid (`2027-05-01 OR <plugin upgrade event>`) per AC5. See P19.
- [x] [Review][Decision] **D5 — `adr-template.md` `{{NNN}}` placeholder rendering** → resolved: wrap placeholders in backticks (`` `{{title}}` `` etc.) so they render as code. Future-proof vs mkdocs-macros-plugin (Jinja-literal inside backticks). See P20.

**Patches (all applied 2026-05-08; verified `mkdocs build --strict` ✅, ruff ✅, pre-commit hygiene ✅):**

- [x] [Review][Patch] **P1 — `[nfr-link]` placeholder explanatory HTML comment restored** [docs/decisions/index.md:7]
- [x] [Review][Patch] **P2 — Bare `ADR-NNN` refs hyperlinked (AC6)** [docs/index.md:21; docs/decisions/ADR-011-mkdocs-setup.md:26] — internal self-refs in ADR-011 (lines 62, 93) intentionally left bare per ADR convention (a doc does not link to itself within its own body)
- [x] [Review][Patch] **P3 — ADR-010 duplicate bare `ADR-002` citations hyperlinked** [docs/decisions/ADR-010-pre-commit-config.md:17-18]
- [x] [Review][Patch] **P4 — ASCII DAG byte-equivalent to Architecture §1077–§1101** [docs/architecture-overview.md:32-33]
- [x] [Review][Patch] **P5 — `adr-template.md` Status line shows full alternatives** [docs/decisions/adr-template.md:3]
- [x] [Review][Patch] **P6 — Template comment clarifies invalid-at-authoring repair allowance** [docs/decisions/adr-template.md template-authoring-rules block]
- [x] [Review][Patch] **P7 — ADR-009 + ADR-011 plugin-set sync (canonical list `mkdocs-material` / `mkdocs-mermaid2` / `mkdocs-include-markdown-plugin` referenced from ADR-011)** [docs/decisions/ADR-009-docs-yml.md Revisit-by]
- [x] [Review][Patch] **P8 — ADR-012 enforcement matrix row #4 corrected** [docs/decisions/ADR-012-module-layout.md row #4]
- [x] [Review][Patch] **P9 — ADR-001 FR47 reasoning rewritten (PyPI distribution name vs import name correctly framed)** [docs/decisions/ADR-001-pyproject-metadata.md:20-22]
- [x] [Review][Patch] **P10 — ADR-011 symlink-rejection rationale corrected (`--strict` symlink-traversal, not drift)** [docs/decisions/ADR-011-mkdocs-setup.md Alternatives]
- [x] [Review][Patch] **P11 — ADR-001 `license = "TBD"` deferred-work entry + proposed `release.yml` pre-flight grep guard recorded** [docs/decisions/ADR-001-pyproject-metadata.md Consequences; deferred-work.md]
- [x] [Review][Patch] **P12 — `mkdocs.yml` `repo_url` corrected to `vuonglq01685/SDLC-Framework`** [mkdocs.yml:9]
- [x] [Review][Patch] **P13 — `site_url: example.invalid` deploy guard recorded as deferred-work entry (proposed `docs.yml` grep pre-flight)** [deferred-work.md]
- [x] [Review][Patch] **P14 — `exclude_docs` (mkdocs) and ruff `extend-exclude` aligned to `docs/ux/`** [mkdocs.yml:17-18; pyproject.toml:54]
- [x] [Review][Patch] **P15 — Local `uv lock --check` + `uv pip compile --python-version 3.10 --group dev` resolution confirmed (jinja2 3.1.6, markdown 3.10.2, mkdocs-get-deps clean)** — CI-matrix verification recorded in deferred-work.md
- [x] [Review][Patch] **P16 — ADR-005 hybrid status line applied** [docs/decisions/ADR-005-package-data-layout.md:3]
- [x] [Review][Patch] **P17 — AC1 amended to record `exclude_docs: ux/` + ADR-011 Decision section gains the corresponding entry; "move prototypes out of `docs_dir`" deferred** [story AC1 line 19; ADR-011; deferred-work.md]
- [x] [Review][Patch] **P18 — ADR-002 prose restructured: `Story 1.4's [boundary-validator pre-commit hook](ADR-010-pre-commit-config.md)` as single inline link** [docs/decisions/ADR-002-ruff-config.md:60,89]
- [x] [Review][Patch] **P19 — ADR-009 Revisit-by restated as explicit hybrid `2027-05-01 OR <plugin event>`; authoring date 2026-05-08 noted (≤ 12mo from authoring rule satisfied)** [docs/decisions/ADR-009-docs-yml.md Revisit-by]
- [x] [Review][Patch] **P20 — `adr-template.md` placeholders wrapped in backticks (`` `{{title}}` ``, `` `{{YYYY-MM-DD}}` ``, etc.)** [docs/decisions/adr-template.md body]

**Deferred (pre-existing or low-impact, tracked in `deferred-work.md`):**

- [x] [Review][Defer] **W1 — ADR log "Status" column hides 1.5 in-place edits** [docs/decisions/index.md:740-752] — deferred, audit/UX enhancement, not blocking
- [x] [Review][Defer] **W2 — Hybrid status strings on ADR-001 / ADR-005 partially overlap with index table** [docs/decisions/ADR-001-pyproject-metadata.md:821; ADR-005:903; index.md:741,745] — deferred, schema-level inconsistency
- [x] [Review][Defer] **W3 — ADR-013 forward-reference has no `--strict` enforcement guard** [docs/decisions/index.md:754] — deferred, will land with Story 1.21 wire-format lock
- [x] [Review][Defer] **W4 — Unicode box-drawing in DAG fenced block render-dependent on browser font** [docs/architecture-overview.md:33-44] — deferred, theme-dependent; revisit when mkdocs-mermaid2 permitted
- [x] [Review][Defer] **W5 — `exclude_docs: ux/` may not catch non-md asset files under docs/ux/** [mkdocs.yml:18-21] — deferred, verify-only concern; current path docs/ux/dashboard-prototype/ only contains README.md
- [x] [Review][Defer] **W6 — Hard-coded `mkdocs 1.6.1` resolved-version in ADR-011 will drift when uv.lock regenerates** [docs/decisions/ADR-011-mkdocs-setup.md:38] — deferred, doesn't break `--strict`; replace with `uv tree --package mkdocs` reference at next ADR-011 revision

**Dismissed as noise (7):** ADR-003 missing-from-diff (file exists, no internal ADR refs to upgrade); deferred-work.md AC6 close-out (already done in working tree, scope-filter artifact); `.gitignore` `_site/` re-include risk (parent-dir rule blocks `!*.md`); `pyproject.toml` `_site/` extend-exclude redundancy (defensible); ADR-005 `**` inside backticks (literal under markdown spec); architecture-overview relative link (already guarded by mkdocs `--strict`); AC2 unquoted vs Task 2.1 quoted nav YAML (parse-equivalent).

## Dev Notes

### File set this story creates / modifies

**NEW files (created by Story 1.5):**

```
mkdocs.yml                                                                # Task 2
docs/index.md                                                             # Task 3.1
docs/architecture-overview.md                                             # Task 4
docs/decisions/index.md                                                   # Task 3.2
docs/decisions/adr-template.md                                            # Task 5
docs/decisions/ADR-001-pyproject-metadata.md                              # Task 6 (back-fill)
docs/decisions/ADR-005-package-data-layout.md                             # Task 7.1 (defer-stub)
docs/decisions/ADR-011-mkdocs-setup.md                                    # Task 7.2 (this story's load-bearing decision)
docs/decisions/ADR-012-module-layout.md                                   # Task 7.3 (back-fill)
```

**MODIFIED files:**

```
pyproject.toml                                                            # Task 1.1 (+mkdocs dep), Task 2.3 (+_site/ in ruff extend-exclude if needed)
uv.lock                                                                   # Task 1.2 (regenerated)
.gitignore                                                                # Task 2.2 (+_site/)
docs/decisions/ADR-002-ruff-config.md                                     # Task 9.7 (link-only edits)
docs/decisions/ADR-004-pytest-config.md                                   # Task 8.1 (revisit-by floor)
docs/decisions/ADR-006-ci-yml.md                                          # Task 9.3 + 9.4 (link-only)
docs/decisions/ADR-007-e2e-yml.md                                         # Task 8.2 (revisit-by floor)
docs/decisions/ADR-008-release-yml.md                                     # Task 9.4 (link-only)
docs/decisions/ADR-009-docs-yml.md                                        # Task 8.3 (revisit-by floor) + 9.5 (link)
docs/decisions/ADR-010-pre-commit-config.md                               # Task 9.6 (link-only)
_bmad-output/implementation-artifacts/deferred-work.md                    # Task 9.11 (mark Story 1.4 deferred item resolved)
_bmad-output/implementation-artifacts/sprint-status.yaml                  # auto-updated by workflow
```

**Do NOT** create:
- `docs/runbooks/`, `docs/threat-model.md`, `docs/prompt-library/` — Architecture §1035–§1040 lists these but they are owned by future stories (per ADR-009's revisit-by trigger). Pre-creating empty stubs would violate `--strict` (every nav entry must resolve to an existing file).
- ADR-013 (workflow trust model) — explicitly owned by Story 1.21 (the wire-format v1 lock ceremony).
- ADR YAML frontmatter — existing eight ADRs have none; the convention is pure-markdown.
- `mkdocs-material`, `mkdocs-mermaid2`, `mkdocs-include-markdown-plugin`, etc. — explicitly deferred by ADR-009 revisit-by.
- A `requirements-docs.txt` — `[dependency-groups] dev` is the single source of truth per Story 1.2's convention.
- `docs/architecture/` subtree (the planning artifact re-emission) — that is the future story flagged in AC6 + ADR-011 Consequences; not v0.2.

### Why `mkdocs>=1.6.0` (not older)

- **`validation.anchors: warn`** is a MkDocs 1.6 feature. Without it, broken in-page anchors (e.g. `[link](#nonexistent)`) silently render as broken HTML. With `--strict` + `validation.anchors: warn`, the build fails — the ADR-009 honest-signal discipline.
- **`validation.absolute_links: relative_to_docs`** (also 1.6+) is NOT used in this story's config (we keep the simpler `warn` form), but the option being available means future stories can opt in.
- **MkDocs 1.5** lacks `validation.anchors`. **MkDocs 1.4** lacks the entire `validation:` block. Both fail this story's AC1 four-key validation requirement.
- **Why `<2`**: forward-defensive cap matching Story 1.2's mypy `<3`, pytest `<10`, Story 1.4's pre-commit `<5`. Lift when MkDocs 2.0 ships and the four-key validation block is shown stable.

### Why stock `theme: name: readthedocs` and not `mkdocs-material`

ADR-009's Revisit-by section explicitly gates the mkdocs-material upgrade on "first non-ADR doc surface (runbooks, threat-model.md, prompt-library) ships". This story ships ONLY ADRs + architecture overview. The eleven decision pages + one overview + template do not justify the dep churn (mkdocs-material adds ~15 transitive deps including `babel`, `colorama`, `paginate`, `pymdown-extensions`, etc.).

The stock `readthedocs` theme is functionally complete for ADR navigation: it has a sidebar nav, breadcrumbs, search, and full mobile responsiveness. ADR-011 records the upgrade trigger (same as ADR-009's) so the next story that authors a runbook or threat-model can flip the theme in a single PR.

### `site_url: https://example.invalid/sdlc-framework/` placeholder rationale

MkDocs `--strict` requires `site_url` to be set; otherwise canonical-link generation in the rendered HTML fails. The `.invalid` TLD is RFC 2606 reserved-non-existent — search engines and link checkers will not follow it, and the placeholder string is unambiguous to anyone reading `mkdocs.yml`. The real `site_url` is set by the operator at GitHub Pages enablement time (one-time setup, NOT enforceable by this story per ADR-009's "Operator Setup" callout). ADR-011 Consequences flags this as the one operator-setup item Story 1.5 cannot fully automate.

Alternative: leave `site_url` unset and use `--strict` only without canonical-link generation. **Rejected**: the `docs.yml` workflow (Story 1.3) ships `mkdocs build --strict` unconditionally; honoring `--strict` end-to-end is a Story-1.3-locked discipline.

### The 12-month rule's binding semantics — why ADR-008's 2027-05-01 stays untouched

Story 1.5's AC5 says "every existing ADR has a `revisit-by` date no further than 12 months out". Read literally, this could be interpreted as "every existing ADR, every time any subsequent story lands, must have a revisit-by date no further than 12 months from THAT story's date". But that reading produces an absurd recursion: every story would mass-edit every ADR's revisit-by, drifting prose for no behavioral reason.

The intent (consistent with NFR-MAINT-5) is "every ADR's revisit-by is set to a date within 12 months of its **authoring** date, and is honored as-written until the revisit happens or the ADR is superseded". So:

- ADR-002 / 003 / 004 / 006 / 007 / 008 / 009 / 010 were authored in Stories 1.2 / 1.3 / 1.4. ADR-008's 2027-05-01 is exactly 12 months from its 2026-05-08 authoring date — within the rule at authoring.
- ADR-004 / 007 / 009 had **pure-event** revisit-bys at authoring — this is the actual NFR-MAINT-5 violation, and Story 1.5 fixes it by adding a date floor.
- The 2027-05-01 floor selection for the new and the upgraded ADRs is consistent — it is 12 months from this story's authoring date (2026-05-09) minus a 7-day safety buffer to 2027-05-01. This safety buffer matches Story 1.3's rationale for ADR-008's 2027-05-01 (12 months minus 7 days from its 2026-05-08 authoring).

ADR-011's Consequences section records this binding-semantics policy explicitly so Story 1.6+ readers know not to re-edit revisit-by dates "just because time has passed".

### Why `_site/` is gitignored (and why mkdocs uses `_site/` not `site/`)

`docs.yml` (Story 1.3) is hard-coded to `mkdocs build --strict --site-dir _site` and `actions/upload-pages-artifact@v3` is hard-coded to `path: _site`. Changing the local mkdocs default `site_dir: site/` to `site_dir: _site` aligns local builds with CI builds (no "works locally, fails CI" surprise), and the leading underscore makes the dir trivially distinguishable from `src/`.

Adding `_site/` to `.gitignore` is mandatory: the artifact is generated; committing it produces merge-conflict noise and grows the repo unnecessarily. Story 1.4's pre-commit `check-added-large-files --maxkb=500` would also fire on a committed `_site/` (the rendered HTML easily exceeds 500 KB).

### Why hyperlink discipline stops at `docs/` boundary (AC6 scoping rationale)

`_bmad-output/planning-artifacts/architecture.md` and `_bmad-output/planning-artifacts/prd.md` are **planning artifacts**, not canonical user-facing documentation. They are emitted by the BMAD planning loop (Story 1.5 itself was created via `/bmad-create-story`!). Including them in `docs_dir` would either:

1. **Expand `docs_dir` to repo root**: rejected — would sweep `_bmad/`, `_bmad-output/`, `tests/`, `scripts/` into the published site (security + noise risk).
2. **Symlink or copy planning artifacts into `docs/`**: rejected — drift risk; the planning artifact regenerates on every BMAD run.
3. **Re-emit planning artifacts as native mkdocs pages**: this is the future-story scope flagged in AC6 + ADR-011 Consequences. Likely owned by a v0.6+ story that lands `/sdlc-architect` workflow's docs-emission step.

For v0.2, plain-text `Architecture §N` + `PRD §N` citations are honest signals: they tell the reader "go look at the planning artifact" without forging a broken link target. ADR-011 records the rationale; the future story re-emits the planning artifact into `docs/architecture/` and `docs/requirements/` and lifts this scoping.

### MkDocs `--strict` interaction with existing ADR markdown

Story 1.4's ADR-010 includes a Python literal block:
```python
MODULE_DEPS: dict[str, ModuleSpec] = {
    "errors":      ModuleSpec(...),
    ...
}
```
plus tables with pipe-delimited cells, plus admonition-style callouts. None of these uses mkdocs-material extensions; they are stock CommonMark + GFM tables (which the readthedocs theme renders fine). `--strict` will NOT complain about these — `--strict` flags broken **links/anchors**, not formatting.

The one mkdocs gotcha: ADR-010's body uses `frozenset({"errors","ids",...})` with curly braces. Curly braces in a code block are fine; curly braces in **prose** would be interpreted as Jinja by `mkdocs-macros-plugin` (NOT installed in this story), so the prose-curly-brace risk is zero with our stock setup. ADR-011 records this as a "do-not-install-macros-plugin-without-revisiting" caution.

### Pre-commit hook chain interaction

Story 1.4's pre-commit chain (ruff-check → ruff-format → mypy-strict → boundary-validator → specialist-validator → hygiene hooks):

- **ruff-check / ruff-format**: only matches `*.py` / `*.pyi` per `types_or: [python, pyi]`. New `mkdocs.yml` and `docs/**/*.md` are NOT touched by ruff. ✓
- **mypy-strict**: pinned to `src/` via `entry: uv run mypy --strict src/`. New files outside `src/` are not type-checked. ✓
- **boundary-validator**: `files: ^(src/sdlc/|tests/|scripts/).*\.py$`. New files outside this regex are skipped. ✓
- **specialist-validator**: `pass_filenames: false, always_run: true` — runs unconditionally and exits zero (placeholder). ✓
- **trailing-whitespace, end-of-file-fixer, mixed-line-ending**: WILL match `docs/**/*.md` and `mkdocs.yml`. Author the new files clean. (`end-of-file-fixer` will rewrite any missing trailing newline; harmless but noise — better to author with a trailing newline.)
- **check-yaml**: WILL match `mkdocs.yml` at repo root (NOT in the `_bmad/|_bmad-output/|.claude/` exclusion regex). The file MUST be valid YAML. Verified by Task 2.4.
- **check-toml**: WILL match `pyproject.toml`. The Task-1.1 edit must produce valid TOML.
- **check-added-large-files --maxkb=500**: applies to every NEW file. Largest expected file is `docs/architecture-overview.md` at ~10 KB; `mkdocs.yml` at ~2 KB; ADRs at 3–10 KB each. Far below 500 KB.

### Coverage gate impact

`[tool.coverage.run] source = ["src/sdlc", "scripts"]` (Story 1.4 patch). This story adds NO Python code, only Markdown + YAML + dep additions. `uv run pytest` should still hit 100% line coverage (the existing 44 tests do not regress) and the 90% gate stays green. Run as a regression check in Task 10.9.

### Previous story intelligence (Stories 1.1 + 1.2 + 1.3 + 1.4 learnings)

From the four implementation-artifact files + the deferred-work.md:

1. **Story 1.4 closed all Story-1.4-owned deferred items**. Story 1.5 opens NO new deferred items at the planning level — every choice in this story (mkdocs-material defer, package_data defer, planning-artifact-link scoping) traces back to a pre-existing deferred-work entry or to ADR-009's revisit-by trigger. ADR-011 makes those traces explicit.
2. **Story 1.4 deferred-work item "ADR citations lack hyperlinks"** is THIS story's primary unblock target. AC6 scoping is the load-bearing decision: within-`docs/` links resolve; cross-`docs/`-boundary references stay plain-text. Task 9.11 marks the entry resolved.
3. **Story 1.4 added `pre-commit>=4.0.0,<5` to `[dependency-groups] dev`** with `<5` as forward-defensive cap. Story 1.5's `mkdocs>=1.6.0,<2` follows the same convention.
4. **Story 1.3's docs.yml uses `mkdocs build --strict --site-dir _site`** verbatim. Story 1.5's `mkdocs.yml` honors `strict: true` + `validation:` block to keep local-vs-CI behavior identical.
5. **Story 1.3's docs.yml probe step `[ -f mkdocs.yml ]`** flips to true the moment Story 1.5 commits `mkdocs.yml`. The first push to main after Story 1.5 lands triggers a real Pages deploy. ADR-009's "stays-green-until-Story-1.5" promise is honored end-to-end.
6. **Story 1.4's `coverage source = ["src/sdlc", "scripts"]`** with `omit = ["scripts/validate_specialists.py"]` is the current gate. Story 1.5 adds no Python under `src/sdlc/` or `scripts/`, so coverage stays at the 44-test baseline.
7. **Story 1.2 + Story 1.4 ADR shape**: `# ADR-NNN: <Title>`, `**Status:** Accepted (YYYY-MM-DD, Story X.Y)`, `## Context`, `## Decision`, `## Alternatives Considered`, `## Consequences`, `## Revisit-by`. Six headings, exact sequence, H2 for body sections. `adr-template.md` (Task 5) is byte-equivalent in shape.
8. **Story 1.4 review patches D3 added §1103 verbatim quotes to ADR-010** ("operator can verify by reading ADR alone"). ADR-012 (Task 7.3) follows the same pattern: verbatim §1103 boundary rules with §-anchors, plus the `MODULE_DEPS` table reference.
9. **Story 1.3's release.yml ADR-008 chose 2027-05-01** as its revisit-by date. Story 1.5's policy on this (Dev Notes "12-month rule binding semantics") justifies leaving it as-is.
10. **Story 1.1's deferred-work item "ADR-001 future revision (Story 1.5 authors the ADR)"** is THIS story's Task 6 — back-fill, not a new authoring. The Status line records both authoring dates.
11. **`pyproject.toml`'s TODO comment "ADR-005 — package_data extension lands in Story 1.16+"** is THIS story's Task 7.1 — defer-stub, not a full ADR. The Status line is `Accepted partial`.
12. **Story 1.4's two known widenings** (`adopt → cli/git` widened to `adopt → cli`; `dashboard` read-only-vs-state widening) are recorded in ADR-012's Consequences (Task 7.3) with the same wording as Story 1.4's Project Structure Notes.

### Git intelligence (last 4 commits)

- `67489d3 feat: implement module boundary enforcement with pre-commit hooks (Story 1.4)` — added `.pre-commit-config.yaml`, `scripts/check_module_boundaries.py`, ADR-010, tests/test_check_module_boundaries.py + tests/test_module_boundaries_main.py + tests/conftest.py. Coverage source extended to `["src/sdlc", "scripts"]`.
- `ca4cb92 feat: add BMad workflow infrastructure and Story 1-3 CI/CD implementation` — added `.github/workflows/{ci,e2e,release,docs}.yml`, ADR-006/007/008/009, the BMAD planning artifact tree.
- `0b4acd9 upload (Story 1.2)` — added ADR-002/003/004 + the full quality-gates `pyproject.toml`.
- `0dd96ea feat: bootstrap sdlc-framework with uv + hatchling (Story 1.1)` — initial `pyproject.toml`, `src/sdlc/__init__.py`, `uv.lock`.

The four commits land the substrate that `mkdocs.yml` (Story 1.5) plus `docs/` will document. Story 1.5's commit set is markdown + YAML + lockfile-only — no source code under `src/sdlc/` is touched.

### Latest tech information (2026-05 lookup)

- **MkDocs current stable**: 1.6.x line. `validation.anchors: warn` requires 1.6+; `relative_to_docs` for absolute_links also 1.6+.
- **MkDocs `--strict`** behavior: turns every `WARNING` into a hard error. The `validation:` block items with `warn` value become errors under `--strict`.
- **Stock `readthedocs` theme**: ships with mkdocs core; no extra dep.
- **Python compatibility**: mkdocs 1.6.x supports Python 3.8+. SDLC-Framework requires Python 3.10+, so we're well above the floor.
- **`uv sync --frozen --group dev` behavior**: re-resolves only when lockfile changes; otherwise installs from lockfile. Story 1.4's CI cache key includes `uv.lock`, so the new mkdocs deps invalidate the cache once and re-cache.
- **GitHub Actions `actions/configure-pages@v5` + `actions/upload-pages-artifact@v3` + `actions/deploy-pages@v4`**: Story 1.3 already pinned these in `docs.yml`; no change needed for Story 1.5.

### Project Structure Notes

- **Alignment with unified project structure** (Architecture §779, §1018–§1034, §1042): canonical `mkdocs.yml` (repo root), `docs/index.md`, `docs/architecture-overview.md`, `docs/decisions/index.md`, `docs/decisions/ADR-NNN-<kebab-slug>.md`, `docs/decisions/adr-template.md` filenames are honored exactly.
- **Detected variance: zero**. Story 1.5 hits Architecture §1018–§1034's tree exactly. The only file under `docs/` not yet authored is `docs/decisions/adr-template.md` (Architecture lists 12 ADR files but does not name a `template.md`); Story 1.5 introduces it as a new node, justified by AC3 + the canonical authoring substrate.
- **Adopt-mode widening from Story 1.4 carried into ADR-012**: `adopt → cli/git` widened to `adopt → cli` at module-level. ADR-012 records this verbatim from Story 1.4's Project Structure Notes (no new widening introduced by this story).
- **`_site/` is a NEW gitignored directory**: not in Architecture's tree (because it is a build artifact). Adding it to `.gitignore` is hygiene; not a structural variance.
- **Detected variance: `docs/decisions/index.md` (the ADR-log landing page)**: Architecture §1019 lists `docs/index.md` and `docs/architecture-overview.md` and the per-ADR files, but does NOT name an `index.md` under `decisions/`. mkdocs needs it to render the `Decisions` collapsible nav as a clickable landing page (otherwise the `Decisions` parent nav node is non-clickable, and the `--strict` build flags it as `unrecognized_links: warn` if any other page links to `decisions/`). Story 1.5 introduces `decisions/index.md` per AC2 + Task 3.2; ADR-011 Decision section records this as the "navigation landing page convention". Not a violation of Architecture; an explicit refinement.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.5] (lines 532–550) — original BDD acceptance criteria.
- [Source: _bmad-output/planning-artifacts/epics.md#Additional-Requirements] (lines 164–166, AR-STARTER + AR-CI + AR-DOCS) — AR-DOCS specifies "mkdocs.yml + docs/ skeleton (architecture overview + numbered ADR log) per ADR-011".
- [Source: _bmad-output/planning-artifacts/architecture.md#Step-3-Starter-Template-Decision] (lines 270–283) — ADR-001 through ADR-013 hand-craft table; line 282 names ADR-011 = mkdocs.yml + docs/ skeleton.
- [Source: _bmad-output/planning-artifacts/architecture.md#Project-Directory-Structure] (lines 779, 1018–1040) — canonical `mkdocs.yml`, `docs/`, `docs/decisions/`, `docs/decisions/ADR-NNN-…md` paths.
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Specifications] (lines 1052–1071) — 16-module dependency table that `architecture-overview.md` summarises and ADR-012 back-fills.
- [Source: _bmad-output/planning-artifacts/architecture.md#Architectural-Boundaries-Import-Rules] (lines 1077–1112) — eight specific boundary rules summarised in `architecture-overview.md` and recorded verbatim in ADR-012.
- [Source: _bmad-output/planning-artifacts/prd.md#Maintainability-NFRs] (line 880) — NFR-MAINT-5 ("every load-bearing decision recorded as an ADR with status, alternatives, consequences, revisit-by").
- [Source: _bmad-output/planning-artifacts/prd.md#Naming-Conventions] (line 440 of architecture.md) — `docs/decisions/ADR-NNN-<kebab-slug>.md` (zero-padded) convention.
- [Source: docs/decisions/ADR-009-docs-yml.md] — Story 1.3's docs.yml + the `[ -f mkdocs.yml ]` probe-and-skip pattern + the mkdocs-material upgrade trigger.
- [Source: docs/decisions/ADR-002-ruff-config.md] — Story 1.2 ADR shape template (six sections, H2 body, single-line Status).
- [Source: docs/decisions/ADR-006-ci-yml.md] — same shape, second template reference.
- [Source: docs/decisions/ADR-010-pre-commit-config.md] — Story 1.4 ADR shape, third template reference; also references ADR-012 (this story's back-fill).
- [Source: _bmad-output/implementation-artifacts/1-1-project-bootstrap-with-uv-init-hatchling.md] — Story 1.1 substrate baseline + ADR-001 back-fill source content.
- [Source: _bmad-output/implementation-artifacts/1-2-pyproject-toml-quality-gates-configuration.md] — Story 1.2 ADR-002/003/004 baseline.
- [Source: _bmad-output/implementation-artifacts/1-3-github-actions-cicd-pipelines.md] — Story 1.3 ADR-006/007/008/009 baseline + docs.yml's mkdocs activation contract.
- [Source: _bmad-output/implementation-artifacts/1-4-pre-commit-config-module-boundary-enforcement-hook.md] — Story 1.4 ADR-010 + MODULE_DEPS source content for ADR-012 back-fill.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — Story 1.4 deferred item "ADR citations lack hyperlinks (Owner: Story 1.5)" + Story 1.1 deferred items "ADR-001 future revision" and "package_data extension".
- [Source: pyproject.toml] — current `[dependency-groups] dev` shape (Story 1.4 update); `[tool.hatch.build.targets.wheel]` `packages = ["src/sdlc"]` + the `# TODO: ADR-005` comment.
- [Source: .pre-commit-config.yaml] — Story 1.4 hygiene hook excludes (`_bmad/|_bmad-output/|.claude/`) — `mkdocs.yml` and `docs/**/*.md` ARE within the inclusion set.
- [Source: .github/workflows/docs.yml] — `[ -f mkdocs.yml ]` probe + `mkdocs build --strict --site-dir _site` activation contract.
- [Context7 `/mkdocs/mkdocs` — Recommended Strict MkDocs Validation Settings] — the four-key `validation:` block pattern for MkDocs 1.6+.
- [Context7 `/mkdocs/mkdocs` — Configure MkDocs theme] — stock `readthedocs` theme reference shape.
- [Context7 `/mkdocs/mkdocs` — Set Project Site Name (YAML)] — `site_name` is a required setting for `--strict`.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 (2026-05-09)

### Debug Log References

- `uv run mkdocs build --strict` failed on first attempt with `WARNING - The following pages exist in the docs directory, but are not included in the "nav" configuration: ux/dashboard-prototype/README.md`. Fix: added `exclude_docs: |ux/` to `mkdocs.yml`. Second build succeeded.
- `act` not installed; Task 10.7 docs.yml rehearsal verified manually by inspecting the `[ -f mkdocs.yml ]` probe logic — probe now resolves true on next push to main.

### Completion Notes List

- Added `mkdocs>=1.6.0,<2` to `[dependency-groups] dev`; regenerated `uv.lock` (mkdocs 1.6.1 resolved with 13 new packages).
- Authored `mkdocs.yml` at repo root with `strict: true`, four-key `validation:` block, stock `readthedocs` theme, and the full 16-entry `nav:` tree. Added `exclude_docs: |ux/` to suppress the pre-existing UX prototype directory from the published site.
- Added `_site/` to `.gitignore` and to `[tool.ruff] extend-exclude` in `pyproject.toml`.
- Authored four new docs surfaces: `docs/index.md`, `docs/architecture-overview.md`, `docs/decisions/index.md`, `docs/decisions/adr-template.md`.
- Authored four new ADRs: ADR-001 (pyproject metadata back-fill, Story 1.1), ADR-005 (package_data defer-stub), ADR-011 (this story's mkdocs setup decision, resolved version 1.6.1), ADR-012 (16-module layout back-fill, Story 1.4). All use `2027-05-01` revisit-by floor.
- Upgraded three event-only revisit-bys to hybrid form: ADR-004 (`2027-05-01 — or when…`), ADR-007 (`2027-05-01 — or when…`), ADR-009 (`2027-05-01 — or when…`). ADR-002/003/006/008/010 untouched (already date-floored).
- Upgraded plain-text ADR-NNN citations to mkdocs-resolvable `[ADR-NNN](ADR-NNN-<slug>.md)` links in ADR-002, ADR-006, ADR-008, ADR-009, ADR-010. Architecture §N / PRD §N citations left as plain text per AC6 scoping.
- Marked Story 1.4 deferred-work item "ADR citations lack hyperlinks" as resolved in `deferred-work.md`.
- `uv run mkdocs build --strict --site-dir _site` exits 0 in 0.08 seconds. All 12 ADRs pass AC5 ISO-date grep. `uv run pytest` and `uv run mypy --strict src/` exit 0 (no regressions).

### File List

**New files:**
- `mkdocs.yml`
- `docs/index.md`
- `docs/architecture-overview.md`
- `docs/decisions/index.md`
- `docs/decisions/adr-template.md`
- `docs/decisions/ADR-001-pyproject-metadata.md`
- `docs/decisions/ADR-005-package-data-layout.md`
- `docs/decisions/ADR-011-mkdocs-setup.md`
- `docs/decisions/ADR-012-module-layout.md`

**Modified files:**
- `pyproject.toml` (added `mkdocs>=1.6.0,<2` to dev deps; added `_site/` to `extend-exclude`)
- `uv.lock` (regenerated with mkdocs 1.6.1 + 13 transitive deps)
- `.gitignore` (added `_site/`)
- `docs/decisions/ADR-002-ruff-config.md` (ADR-010 link upgrade)
- `docs/decisions/ADR-004-pytest-config.md` (revisit-by floor upgrade)
- `docs/decisions/ADR-006-ci-yml.md` (ADR-001 + ADR-008 link upgrades)
- `docs/decisions/ADR-007-e2e-yml.md` (revisit-by floor upgrade)
- `docs/decisions/ADR-008-release-yml.md` (ADR-006 link upgrades, 4 occurrences)
- `docs/decisions/ADR-009-docs-yml.md` (revisit-by floor upgrade + ADR-011 link upgrade)
- `docs/decisions/ADR-010-pre-commit-config.md` (ADR-002, ADR-006, ADR-012 link upgrades)
- `_bmad-output/implementation-artifacts/deferred-work.md` (marked Story 1.4 item resolved)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status: ready-for-dev → in-progress → review)
- `_bmad-output/implementation-artifacts/1-5-mkdocs-adr-log-skeleton.md` (this file)

### Change Log

- 2026-05-09 (Story 1.5): Implemented MkDocs site + ADR log skeleton. Authored mkdocs.yml, four doc surfaces, four new ADRs (001, 005, 011, 012), upgraded three revisit-by floors (004, 007, 009), upgraded all within-docs ADR cross-references to mkdocs-resolvable links, resolved Story 1.4 deferred "ADR citations lack hyperlinks" item. Build passes `uv run mkdocs build --strict` in 0.08 s.
