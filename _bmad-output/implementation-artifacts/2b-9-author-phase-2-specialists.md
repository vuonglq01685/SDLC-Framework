# Story 2B.9: Author Phase 2 Specialists

**Status:** done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **framework author**,
I want **the Phase 2 (Design) specialist agents — the architecture track and the UX track, including the dynamic sub-track architects from Story 2A.14 — authored as production-quality markdown prompt files instead of MockAIRuntime placeholders**,
so that **the Epic 2B real-Claude dispatch path produces real design output (architecture, sub-track docs, UX artifacts) rather than placeholder stubs, and the dispatcher's manifest stays internally consistent with `docs/specialists-matrix.md`**.

## Acceptance Criteria

> **Provenance.** This story owns Phase 2 of the Epic-2B authoring sweep
> (`docs/specialists-matrix.md §3` schedules the Phase-2 planned roster to **2B.9**;
> sibling stories 2B.8 = Phase 1, 2B.10 = Phase 3). Epic 2B dispatches via the REAL
> Claude runtime (`src/sdlc/runtime/claude.py`), so every prompt body MUST be production
> quality — a placeholder body shipped to a live model is a defect, not a stub.
> **Naming is matrix-exact:** every `name`/`title`/`model` MUST match the row that survives
> the D1 reconciliation in `docs/specialists-matrix.md` + `docs/decisions/ADR-030-specialist-roster-freeze.md`.

> **CRITICAL frontmatter note.** The shipped Phase-2 frontmatter schema is NOT
> `id/phase/tools:[read,grep,glob]`. The real schema observed in every
> `src/sdlc/agents/phase2/*.md` is:
> `schema_version, name, title, icon, model, tools, read_globs, write_globs, description`.
> `tools` is an **empty list `[]`** on all current Phase-2 specialists, and capability is
> expressed through `read_globs` / `write_globs`, not a tool allow-list. Author against the
> REAL schema. [Source: src/sdlc/agents/phase2/system-architect.md and the other 5 phase2 files]

1. **Existing Phase-2 stub bodies replaced with production prompts.** The six shipped
   `src/sdlc/agents/phase2/*.md` files currently carry placeholder bodies
   (`**PLACEHOLDER** — MockAIRuntime v1. Real ... lands in Story 2B.9.`). For the set fixed by
   **D1**, each placeholder body is replaced with a production-quality system prompt that
   specifies role, inputs (`read_globs`), required design deliverable(s) and output format
   (`write_globs`, including `ux-designer`'s JSON-array `{filename, content}` contract), and the
   read/produce-design-docs-only confinement. The six files are: `system-architect`,
   `database-architect`, `security-architect`, `observability-architect`, `ux-designer`,
   `ux-reviewer`. [Source: src/sdlc/agents/phase2/*.md bodies]

2. **New Phase-2 specialists authored (per D1/matrix §3).** For each new Phase-2 specialist that
   D1 admits into scope, a production-quality prompt file is created at
   `src/sdlc/agents/phase2/<name>.md` with matrix-exact frontmatter and body. The matrix §3
   "Phase 2 planned (6)" candidate set is: `ux-researcher`, `design-system-author`,
   `a11y-reviewer`, `infra-architect`, `devex-architect`, `api-designer`. The DAG estimates
   "~6 markdown files" for 2B.9, which maps to this planned-6 set — but the matrix marks these
   names *tentative*, so the concrete admitted set + any rename is fixed by D1 and recorded here
   before authoring. [Source: docs/specialists-matrix.md §3 "Phase 2 planned (6)"; docs/sprints/epic-2b-dag.md]

3. **Frontmatter matches the real schema and passes the frontmatter contract.** Every
   authored/enriched file opens with YAML frontmatter using exactly the shipped keys
   (`schema_version, name, title, icon, model, tools, read_globs, write_globs, description`),
   `name` equals the filename stem, and the file validates against the specialist-frontmatter
   contract. [Source: src/sdlc/contracts/specialist_frontmatter.py;
   tests/contract_snapshots/v1/specialist_frontmatter.json; tests/unit/contracts/test_specialist_frontmatter.py]

4. **Boundary-line present for every file (2B.5 gate).** Each authored/enriched file carries the
   boundary-line marker required by `scripts/check_boundary_line_presence.py` /
   `tests/security/test_boundary_line_presence.py`. Replicate the EXACT marker form already used
   by the shipped Phase-2 files (read one verbatim before authoring — do NOT invent the wording);
   the gate must exit 0 over all `src/sdlc/agents/*/*.md`. [Source:
   scripts/check_boundary_line_presence.py; tests/security/test_boundary_line_presence.py]

5. **No tool / write-glob escalation.** `tools` stays `[]` (matching every shipped Phase-2 file);
   `write_globs` for each specialist is scoped to its own design-output path under
   `02-Architecture/**` (architecture track → `02-Architecture/02-System/...`; UX track →
   `02-Architecture/01-UX/...`) and grants no write outside the design tree. No file declares a
   destructive/exec capability. [Source: src/sdlc/agents/phase2/*.md `tools`/`write_globs`;
   docs/decisions/ADR-030-specialist-roster-freeze.md — confirm tool-policy wording in the ADR]

6. **Registry mirrored and loadable (2A.2 manifest).** Every specialist this story
   authors/enriches has a `specialists:` entry in `src/sdlc/agents/index.yaml` with `name`,
   `phase: 2`, and `file: phase2/<name>.md`, and the manifest loader resolves each `file` to an
   existing path. Existing rows (the 6 already present) are kept; new names are appended; NO
   unrelated row is rewritten. Enriching an existing stub body requires NO `index.yaml` change
   (the row already exists). [Source: src/sdlc/agents/index.yaml; src/sdlc/specialists/manifest.py;
   tests/unit/specialists/test_manifest.py; tests/unit/specialists/test_registry.py]

7. **Matrix ↔ index.yaml stay in lockstep (ADR-026 §4 update rule).** For every new name added to
   `index.yaml`, the corresponding `docs/specialists-matrix.md` row is moved out of §3 "planned"
   into §1 "shipped" (the matrix update is paired with the implementation, per the matrix's own
   update rule and ADR-026 §4). Any rename at authoring time updates the matrix and removes the
   planned row simultaneously. [Source: docs/specialists-matrix.md header "Update rule"; §3 note]

8. **Sub-track architect set consistent with 2A.14.** The sub-track architects are dispatched by
   the architect pipeline via the hardcoded `_SUBTRACK_SPECIALISTS` allowlist in
   `src/sdlc/cli/architect.py`, keyed off `requires:` frontmatter that `system-architect` emits
   (handled by `src/sdlc/cli/_architect_pipeline.py`). After this story, every specialist named in
   that allowlist (the database/security/observability sub-track architects, plus any new
   architecture-track sub-track sibling D1 admits, e.g. `infra-architect`/`devex-architect` if
   selected) exists as a production prompt and is registered — so 2A.14 sub-track dispatch no
   longer materialises placeholder bodies. Confirm the live allowlist keys against
   `src/sdlc/cli/architect.py` before claiming this AC. [Source: src/sdlc/cli/architect.py
   `_SUBTRACK_SPECIALISTS`; src/sdlc/cli/_architect_pipeline.py `build_sub_track_prompt`;
   _bmad-output/implementation-artifacts/2a-14-sdlc-architect-dynamic-sub-tracks.md]

9. **`api-architect?` is NOT authored (D2 data defect).** `docs/specialists-matrix.md` carries no
   confirmed `api-architect` row; the planned Phase-2 wire-format role is **`api-designer`**
   (matrix §3), and any `api-architect?`-with-`?` reference is treated as unconfirmed. No
   `api-architect` file or `index.yaml` row is created. Whether `api-designer` itself is authored
   is governed by D1. Confirm ADR-030's stance on unconfirmed roster names before resolving D2.
   [Source: docs/specialists-matrix.md §3 (`api-designer`, not `api-architect`);
   docs/decisions/ADR-030-specialist-roster-freeze.md]

10. **2B.3 conformance still exercises ≥1 Phase-2 specialist.** The abstraction-adequacy harness
    `tests/integration/test_abstraction_adequacy.py` runs the deterministic pipeline against BOTH
    MockAIRuntime and ClaudeAIRuntime and asserts byte-identical HookPayload sequences + final
    `state.json`. Its mock fixture is seeded from
    `tests/fixtures/mock_responses/abstraction-adequacy.yaml`. After this story the harness stays
    green: the Phase-2 specialist(s) it exercises remain registered and prompt-resolvable, and any
    enriched body that the fixture keys on stays byte-consistent with the seeded golden (regenerate
    goldens via the documented `_REGENERATE_GOLDENS` ceremony ONLY if a fixture change is
    deliberate, with a justifying diff). [Source: tests/integration/test_abstraction_adequacy.py;
    tests/fixtures/mock_responses/abstraction-adequacy.yaml]

11. **2B.5 boundary-line gate passes.** `tests/security/test_boundary_line_presence.py` and
    `scripts/check_boundary_line_presence.py` are green across all agent markdown after this
    story's edits. [Source: tests/security/test_boundary_line_presence.py]

12. **Specialist validator passes.** `scripts/validate_specialists.py` (cross-reference validator,
    matrix ↔ index.yaml ↔ files) passes for the full post-2B.9 roster. [Source:
    scripts/validate_specialists.py; docs/specialists-matrix.md §5]

13. **Quality gate green (CONTRIBUTING.md §1).** `ruff format --check`, `ruff check`,
    `mypy --strict src/`, `pytest` with coverage ≥90% on touched lines,
    `pre-commit run --all-files`, `mkdocs build --strict`, and wire-format snapshots all pass.
    [Source: CONTRIBUTING.md §1]

## Tasks / Subtasks

> **TDD ordering note (CONTRIBUTING.md §2).** For prompt-authoring the "tests" are the
> frontmatter contract + boundary-line gate + specialist validator + manifest/registry tests +
> the 2B.3 conformance harness. Extend/assert the *failing* validation FIRST (red), then add the
> prompt bodies + `index.yaml` rows + matrix rows to turn it green. Tests-first ordering MUST be
> visible in `git log --reverse`.

- [x] **T0 — Resolve decisions before authoring** (AC: 1, 2, 9)
  - [x] Record selected options for **D1** (scope), **D2** (`api-architect?` defect — confirm
        `api-designer` is the real name; default: do not author `api-architect`), **D3** (UX track
        depth), and **D4** (matrix-rename) in the Decisions Needed section.
        → D1=(b): enrich all 6 existing stubs + author all 6 new planned = 12 files total.
        → D2=(a): `api-designer` only; `api-architect` not authored (not in frozen matrix).
        → D3=(a): full `ux-reviewer` production prompt; close EPIC-2A-DEBT-UX-PARALLEL-REVIEWER.
        → D4: ship matrix names verbatim (no renames; minimize churn).
  - [x] Read one shipped `src/sdlc/agents/phase2/*.md` end-to-end and record the EXACT
        boundary-line marker wording + the exact frontmatter key order to copy.
        → Boundary-line architectural invariant (from 2B.8): phase1_prompt_builder REJECTS
          specialist bodies that contain BOUNDARY_LINE — builder injects it automatically.
          Phase-2 files must NOT contain BOUNDARY_LINE in their bodies. No new markdown
          boundary marker needed; gate passes trivially for .md files (script scans Python only).
        → Frontmatter key order: schema_version, name, title, icon, model, tools, read_globs,
          write_globs, description. tools: [] (empty). Observed in all 6 existing Phase-2 files.
  - [x] Derive the concrete file list + `index.yaml` row list + matrix-row moves from the chosen
        options.
        → Enrich: system-architect, database-architect, security-architect, observability-architect,
          ux-designer, ux-reviewer.
        → Create: ux-researcher, design-system-author, a11y-reviewer, infra-architect,
          devex-architect, api-designer.
        → index.yaml: append 6 new rows (ux-researcher, design-system-author, a11y-reviewer,
          infra-architect, devex-architect, api-designer).
        → matrix: move 6 from §3 planned → §1 shipped; update §4 totals.
        → architect.py: add infra-architect + devex-architect to _SUBTRACK_SPECIALISTS (AC8).

- [x] **T1 — Red: validation/fixtures for the target Phase-2 set** (AC: 3, 4, 5, 6, 11, 12)
  - [x] Extend/assert that the chosen Phase-2 names are present in `index.yaml` with `phase: 2`
        and a resolvable `file:`; expect RED for new names until authored.
        → Created tests/unit/specialists/test_phase2_2b9_authoring.py; 5 tests RED, 4 GREEN.
  - [x] Capture the pre-authoring baseline: run `scripts/check_boundary_line_presence.py`,
        `scripts/validate_specialists.py`, and `pytest tests/unit/specialists`
        `tests/unit/contracts/test_specialist_frontmatter.py`
        `tests/integration/test_abstraction_adequacy.py -m integration`.
        → All gates green on baseline (existing stubs do not break gates).
  - [x] Commit the failing validation BEFORE touching prompt bodies / `index.yaml` / the matrix.
        → Committed as test(2b.9): anti-tautology receipts ... (RED) on branch
          epic-2b/2b-9-phase2-specialists. 5 RED / 4 GREEN confirmed before any implementation.

- [x] **T2 — Enrich existing Phase-2 stub bodies to production prompts** (AC: 1, 3, 4, 5)
  - [x] For each D1-selected file in {`system-architect`, `database-architect`,
        `security-architect`, `observability-architect`, `ux-designer`, `ux-reviewer`}, replace the
        `**PLACEHOLDER**` body with a production system prompt.
        → All 6 bodies replaced. system-architect: requires: frontmatter + full architecture doc
          template. database-architect: schema/ER/migration/query. security-architect: threat model
          + controls. observability-architect: logging/metrics/tracing/SLO. ux-designer: JSON-array
          output contract preserved. ux-reviewer: full parallel review report (D3=(a)).
  - [x] Preserve frontmatter values verbatim (they already match the matrix) and the existing
        boundary-line marker; keep `system-architect`'s `requires:`-emitting contract intact so the
        sub-track pipeline still works; keep `ux-designer`'s JSON-array output contract intact.
        → Frontmatter unchanged. requires: contract preserved. JSON-array contract preserved.
          Boundary-line architectural invariant: bodies must NOT contain BOUNDARY_LINE (verified).

- [x] **T3 — Author new Phase-2 specialists** (AC: 2, 3, 4, 5, 8) — set per D1
  - [x] Create `src/sdlc/agents/phase2/<name>.md` for each admitted new specialist from matrix §3
        (`ux-researcher`, `design-system-author`, `a11y-reviewer`, `infra-architect`,
        `devex-architect`, `api-designer`), matrix-exact frontmatter (real schema), production body,
        boundary-line marker, design-only `write_globs`.
        → All 6 created. infra-architect + devex-architect added to _SUBTRACK_SPECIALISTS (AC8).

- [x] **T4 — Mirror registry + matrix** (AC: 6, 7, 9)
  - [x] Append `specialists:` rows to `src/sdlc/agents/index.yaml` for each newly-authored name
        (`name` + `phase: 2` + `file: phase2/<name>.md`); keep the 6 existing rows untouched.
        → 6 rows appended. 6 existing rows untouched.
  - [x] Move each newly-shipped name's `docs/specialists-matrix.md` row from §3 planned → §1
        shipped (paired matrix update); update the §4 roster totals.
        → §1 shipped: 26→32. §3 planned: 11→5. §4 totals updated. Phase-2 planned section removed.
  - [x] Assert NO `api-architect` row is added (D2).
        → test_no_api_architect_in_registry confirms; D2=(a) invariant holds.

- [x] **T5 — Green + gate** (AC: 10, 11, 12, 13)
  - [x] `python scripts/check_boundary_line_presence.py` exits 0;
        `python scripts/validate_specialists.py` passes.
        → Boundary gate exit 0. Validator OK (placeholder, exits 0 per v0.2).
  - [x] `pytest tests/unit/specialists tests/unit/contracts/test_specialist_frontmatter.py
        tests/integration/test_abstraction_adequacy.py -m integration -q` green
        (mock-vs-claude byte identity holds; regenerate goldens only via the documented ceremony).
        → 111 specialist tests passed. 3 conformance tests passed. No golden regen needed.
  - [x] Full quality gate: `ruff format --check .`, `ruff check .`, `mypy --strict src/`,
        `pytest` (coverage ≥90% touched), `pre-commit run --all-files`, `mkdocs build --strict`,
        wire-format snapshots.
        → ruff ✅ mypy ✅ pre-commit 19/19 ✅ mkdocs --strict ✅ wireformat 5/5 ✅
          test_wheel_build updated (_ALLOWED_CONTENT_FILES + 6 new paths) → 4/4 ✅
          Full pytest: 2840 passed, 4 skipped, 0 failed ✅

- [x] **T6 — Sibling rebase discipline** (Dev Notes → Worktree Coordination)
  - [x] Before merging, rebase onto any already-merged sibling among 2B.8 / 2B.10 that has landed
        `index.yaml` / matrix rows; re-run the gate post-rebase (CONTRIBUTING.md §3).
        → 2B.8 already merged to main (branched from e5c72a0). 2B.10 not yet started.
          No rebase needed at this point; T6 gate satisfied.

### Review Findings

> Source: `bmad-code-review` (2026-06-01) — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) over `main...epic-2b/2b-9-phase2-specialists`.
> Triage: 3 decision-needed, 2 patch, 1 defer, 7 dismissed. Acceptance Auditor: all 13 ACs + D1–D5 PASS, TDD RED→GREEN ordering verified (61421b2 test → 53d5be0 feat).
> **Resolution (2026-06-01, user = "recommend"):** DN1 → deferred (intended; tracked in deferred-work.md as CR2B9-DN1). DN2 → deferred (CR2B9-W2). DN3 → debt kept OPEN; Completion Notes reworded.

**Decision-needed (resolved):**

- [x] [Review][Decision] CR2B9-DN1 — Wiring deferral for the 4 standalone net-new specialists — `api-designer`, `ux-researcher`, `design-system-author`, `a11y-reviewer` are authored but have NO dispatch path (no workflow-YAML reference, and `api-designer` is not a `requires:` sub-track value nor in `architect.py` `_SUBTRACK_SPECIALISTS`). Asymmetry noted: `infra`/`devex` WERE wired this story (AC8), these 4 were not. **Resolved → DEFER (intended):** story scope is "author, don't wire" (mirrors 2B.8's market-researcher/stakeholder-simulator deferral); wiring belongs to the dispatch-integration story. Latent risks recorded in deferred-work.md: (a) `write_globs` (`00-RESEARCH.md`, `design-system.md`, `API.md`) overlap `ux-designer`'s broad `02-Architecture/01-UX/*.md` with no single-owner/cleanup guarantee; (b) `a11y-reviewer`/`ux-reviewer` carry `write_globs: []` → `dispatch_and_write` indexes `write_globs[0]` and would fault on the empty tuple unless review-only roles are special-cased.
- [x] [Review][Decision] CR2B9-DN2 — Cross-reviewer accessibility contract is internally inconsistent — `ux-reviewer.md` grades touch-target (min 44×44) as BLOCKER/WARNING while `a11y-reviewer.md` grades the same check WARNING/NOTE (can never BLOCK); and both audit a "declared size" that `ux-designer.md`'s screen-spec template never emits. **Resolved → DEFER (CR2B9-W2):** the severity contradiction only manifests once `a11y-reviewer` is wired alongside `ux-reviewer`; harmonizing the full UX reviewer/designer/a11y contract (winning severity model + a touch-target size field in the ux-designer screen-spec) is best done coherently with the UX-track wiring story rather than piecemeal now.
- [x] [Review][Decision] CR2B9-DN3 — `EPIC-2A-DEBT-UX-PARALLEL-REVIEWER` closure was bodies-only — D3=(a) / Completion Notes claimed the debt closed, but the diff authors only the `ux-reviewer` prompt body; no synthesizer / parallel-dispatch wiring is added. **Resolved → debt kept OPEN:** Completion Notes reworded (line ~473) to state the debt closes only when the UX-track wiring lands; the production prompt body is delivered as scoped.

**Patch (unambiguous code fixes):**

- [x] [Review][Patch] CR2B9-P1 — `test_net_new_phase2_schema_version_is_one` aborted on first offender instead of aggregating [tests/unit/specialists/test_phase2_2b9_authoring.py:114-124] — `assert s.frontmatter.schema_version == 1` sat inside `try/except SpecialistError`, so a wrong version raised `AssertionError` that escaped the loop and bypassed the `violations` list. **APPLIED:** version check moved into `violations` (report-all pattern, mirrors `test_..._have_correct_phase`). 9/9 tests green.
- [x] [Review][Patch] CR2B9-P2 — `_PLACEHOLDER_MARKERS` was redundant + over-broad [tests/unit/specialists/test_phase2_2b9_authoring.py:65-72] — `"Placeholder until Story 2B.9"` duplicated `"placeholder until Story 2B.9"` under the case-insensitive match, and bare `"PLACEHOLDER"` matched ANY "placeholder" substring (latent AC1 false-positive on legitimate UX "placeholder text" vocabulary). **APPLIED:** dropped the redundant case-variant; anchored the sentinel to the real stub form `**PLACEHOLDER**`; added an explanatory comment. 9/9 tests green.

**Deferred (tracked, low risk):**

- [x] [Review][Defer] CR2B9-W1 — Inconsistent registry-absence handling across receipts [tests/unit/specialists/test_phase2_2b9_authoring.py:133-153 vs 170-192] — `test_no_phase2_body_contains_placeholder_marker` does `except SpecialistError: continue` (silent skip) while `test_no_phase2_body_contains_boundary_line` treats the same absence as a violation. Low risk: global `load_registry` + the boundary-line receipt catch any absence loudly. Mirrors the previously-deferred CR2B8-W1 — track together. — deferred, pre-existing pattern.

## Dev Notes

### Context & Provenance

Epic 2B runs the **real Claude dispatch path** (`src/sdlc/runtime/claude.py`); Epic 2A was
MockAIRuntime-only. Phase-2 prompts will therefore be sent to a live model, so production-quality
bodies are mandatory. This story is the Phase-2 leg of the L3 authoring sweep
(2B.8 = Phase 1, 2B.9 = Phase 2, 2B.10 = Phase 3 per `docs/specialists-matrix.md §3`).
[Source: docs/specialists-matrix.md §3; src/sdlc/runtime/claude.py]

### CRITICAL: Stub-vs-Production Finding (verified)

All **six** existing `src/sdlc/agents/phase2/*.md` files are **placeholders**. Each body ends with a
`**PLACEHOLDER** — MockAIRuntime v1. Real ... lands in Story 2B.9.` line (and `ux-reviewer` is a
deferred placeholder citing `EPIC-2A-DEBT-UX-PARALLEL-REVIEWER`). Their frontmatter is correct and
production-ready; only the prompt bodies are stubs. Files:
`database-architect.md`, `observability-architect.md`, `security-architect.md`,
`system-architect.md`, `ux-designer.md`, `ux-reviewer.md`. This is the central reason D1 exists:
2B.9 must decide whether it (a) only adds the matrix §3 planned-6 new files, (b) also enriches these
six stub bodies to production prompts, or (c) a subset. [Source: src/sdlc/agents/phase2/*.md bodies]

### Matrix-vs-Reality Reconciliation (READ — several brief assumptions were wrong)

Three views disagree and the dev MUST reconcile them, not trust a single source:

| view | Phase-2 contents |
|---|---|
| `docs/specialists-matrix.md §1` shipped (Phase 2) | `ux-designer`, `ux-reviewer`, `system-architect`, `database-architect`, `security-architect`, `observability-architect` (6) |
| `docs/specialists-matrix.md §3` planned (Phase 2, target **2B.9**) | `ux-researcher`, `design-system-author`, `a11y-reviewer`, `infra-architect`, `devex-architect`, `api-designer` (6, *tentative*) |
| `src/sdlc/agents/index.yaml` registered (phase 2) | the same 6 shipped names — rows present |
| filesystem `src/sdlc/agents/phase2/` | the same 6 files — all placeholder bodies |

Corrections vs the create-story brief: there is **no** `interaction-designer`, `content-designer`,
`integration-architect`, or `performance-architect` in this repo's matrix/files; the planned-6 are
the names above; the wire-format role is **`api-designer`** (not `api-architect`); and the
frontmatter schema is `name/title/icon/model/tools/read_globs/write_globs`, with `tools: []`
(NOT `id/phase/tools:[read,grep,glob]`). Author from the files as they actually exist.
[Source: docs/specialists-matrix.md §1, §3; src/sdlc/agents/index.yaml; src/sdlc/agents/phase2/*.md]

### Exact Frontmatter Schema (real — copy this shape verbatim)

Observed in every shipped Phase-2 file (e.g. `system-architect.md`):

```yaml
---
schema_version: 1
name: system-architect            # == filename stem == index.yaml `name`
title: "System Architect"         # matrix-exact display title
icon: "🏗️"
model: sonnet                     # all current Phase-2 specialists are `sonnet`
tools: []                         # EMPTY — capability is via read_globs/write_globs
read_globs:
  - "01-Requirement/**/*.md"
  - "02-Architecture/02-System/**/*.md"
write_globs:
  - "02-Architecture/02-System/ARCHITECTURE.md"
description: "Phase 2 ... specialist. ..."
---
```

The `index.yaml` row mirrors only `name` + `phase` + `file`:

```yaml
  - name: system-architect
    phase: 2
    file: phase2/system-architect.md
```

[Source: src/sdlc/agents/phase2/system-architect.md; src/sdlc/agents/index.yaml]
Validate authored frontmatter against `src/sdlc/contracts/specialist_frontmatter.py` +
`tests/contract_snapshots/v1/specialist_frontmatter.json` before claiming AC3 (this story does NOT
edit the contract or the frozen snapshot — a contract change would require the ADR-024 snapshot
ceremony, which is out of scope).

### Boundary-Line Convention (enforced by the 2B.5 gate)

`scripts/check_boundary_line_presence.py` + `tests/security/test_boundary_line_presence.py` require a
boundary-line marker in every agent markdown. **Read one shipped Phase-2 file end-to-end and copy
its marker form verbatim** — do not invent wording, and note the security corpus
(`tests/security/corpus/user_text/boundary_marker_smuggle_*`) shows the marker is security-sensitive
(homoglyph/whitespace smuggling is tested), so byte-exact replication matters. [Source:
scripts/check_boundary_line_presence.py; tests/security/test_boundary_line_presence.py + corpus]

### Sub-Track Architect Wiring (Story 2A.14)

Sub-track architects are dispatched at architect time, not via fresh `index.yaml` rows:
`system-architect` emits `requires:` frontmatter; `src/sdlc/cli/_architect_pipeline.py`
(`build_sub_track_prompt`, `materialize_sub_track_mock`) builds the compound sub-track prompt; and
`src/sdlc/cli/architect.py` dispatches them **sequentially** against a hardcoded
`_SUBTRACK_SPECIALISTS` allowlist (AC2/AC3/D1 of 2A.14 — sequential + hardcoded allowlist, YAGNI).
The sub-track specialists are the existing `database/security/observability` architects (and any new
architecture-track sibling D1 admits, e.g. `infra-architect`/`devex-architect`). Authoring their
bodies here removes the placeholder content the sub-track pipeline currently materialises.
**Confirm the live allowlist keys in `src/sdlc/cli/architect.py` (`_SUBTRACK_SPECIALISTS`) before
claiming AC8** — the brief's "integration/performance" base names do not exist in this repo.
[Source: src/sdlc/cli/architect.py; src/sdlc/cli/_architect_pipeline.py;
_bmad-output/implementation-artifacts/2a-14-sdlc-architect-dynamic-sub-tracks.md]

### Registry / Loader Contract (2A.2)

The machine-readable manifest is `src/sdlc/agents/index.yaml`
(`schema_version: 1`, `specialists: [{name, phase, file}, ...]`). The loader lives at
`src/sdlc/specialists/manifest.py` (+ `registry.py`, `frontmatter.py`, `validator.py`), with
behaviour pinned by `tests/unit/specialists/test_manifest.py` / `test_registry.py` and fixtures
under `tests/fixtures/specialists/` (orphan / missing-file / duplicate / path-traversal cases). A
specialist is "real" only when its file exists, its row is in `index.yaml`, and it passes the
frontmatter contract + boundary gate + validator. NOTE: there is **no** `src/sdlc/agents/registry.py`
module — the brief's reference to one is wrong; the loader is `src/sdlc/specialists/manifest.py`.
[Source: src/sdlc/agents/index.yaml; src/sdlc/specialists/manifest.py; tests/unit/specialists/*]

### Conformance Wiring (2B.3)

`tests/integration/test_abstraction_adequacy.py` runs the full deterministic pipeline
(init → scan → dispatch ×2 → pre-write hook chain → journal append → state projection → atomic
state write) against `_mock_factory` AND `_claude_factory`, asserting per-runtime goldens
(`tests/fixtures/abstraction_adequacy/expected_*.json`) and cross-runtime byte identity. The mock
side is seeded from `tests/fixtures/mock_responses/abstraction-adequacy.yaml`. Do NOT add a third
runtime factory (explicit invariant). If an enriched Phase-2 body changes bytes the harness keys on,
regenerate goldens ONLY via the documented `_REGENERATE_GOLDENS` ceremony with a justifying diff —
drift is the symptom this gate exists to catch. [Source: tests/integration/test_abstraction_adequacy.py;
tests/fixtures/mock_responses/abstraction-adequacy.yaml; tests/fixtures/abstraction_adequacy/*]

### Previous-Story Intelligence

- **2A.13 (`2a-13-sdlc-ux-phase-2-ux-track.md`, done)** — authored the Phase-2 UX track
  (`ux-designer`, `ux-reviewer`) frontmatter + the `/sdlc-ux` pipeline; `ux-reviewer` was shipped as
  a **deferred** placeholder (parallel reviewer dispatch deferred to 2B.9 per its AC3/D1 →
  `EPIC-2A-DEBT-UX-PARALLEL-REVIEWER`). Re-read its Dev Notes for the JSON-array output contract and
  the parallel-reviewer debt. [Source: src/sdlc/agents/phase2/ux-reviewer.md;
  _bmad-output/implementation-artifacts/2a-13-sdlc-ux-phase-2-ux-track.md]
- **2A.14 (`2a-14-sdlc-architect-dynamic-sub-tracks.md`, done)** — the dynamic sub-track architect
  dispatch (`requires:` → `_SUBTRACK_SPECIALISTS`, sequential). [Source above]
- **2B.1 (done)** — real Claude dispatch seam. **2B.3 (done)** — mock-vs-claude conformance harness.
  **2B.5 (done)** — boundary-line presence gate. **2B.6 (done)** — tool-safety contract.

### Sibling / Worktree Coordination (CONTRIBUTING.md §3)

Worktree `epic-2b/2b-9-phase2-specialists` (owner: Winston) per `docs/sprints/epic-2b-dag.md §5`.
**2B.8 (Phase 1), 2B.9 (Phase 2), 2B.10 (Phase 3) all append rows to the same two files —
`src/sdlc/agents/index.yaml` AND `docs/specialists-matrix.md`.** The per-phase markdown directories
(`phase1/`, `phase2/`, `phase3/`) are disjoint and do not collide, but `index.yaml` and the matrix
WILL. Per §3/§4: same-layer stories touching shared files MUST **rebase between merges** — rebase
onto any already-merged sibling before merging this story, then re-run the boundary gate + validator
+ conformance tests post-rebase. [Source: docs/sprints/epic-2b-dag.md §4–§5; CONTRIBUTING.md §3–§4]

### Testing Standards

- Framework: `pytest`. Verify authoring via the frontmatter contract
  (`tests/unit/contracts/test_specialist_frontmatter.py`), boundary gate
  (`tests/security/test_boundary_line_presence.py`), manifest/registry tests
  (`tests/unit/specialists/*`), the validator (`scripts/validate_specialists.py`), and the 2B.3
  conformance harness — extend/assert these rather than adding a parallel parser.
- No live Claude API call is required to verify authoring (gates are static over files + manifest;
  the conformance harness's claude leg uses a stubbed `claude` on PATH).
- Coverage ≥90% on touched lines; ruff/mypy/pre-commit/mkdocs/wire-format green. [Source: CONTRIBUTING.md §1–§2]

### Decisions Needed (CONTRIBUTING.md §5)

> Resolve in T0 and record the chosen option label here before authoring.

- **D1 — Authoring scope for Phase 2.** The DAG says "~6 markdown files"; the matrix §3 plans 6 NEW
  names; the filesystem has 6 EXISTING stub bodies. Choose:
  - **D1=(a)** Author only the matrix §3 planned-6 NEW files; leave the 6 existing stub bodies as-is.
    *(Maps most literally to "~6 files" + the matrix's stated 2B.9 target.)*
  - **D1=(b)** Author the planned-6 NEW files **and** enrich all 6 existing stub bodies to production
    prompts. *(Best fits "Epic 2B dispatches for real" — a placeholder body sent to a live model is a
    defect; ~12 files. Largest scope.)*
  - **D1=(c)** Enrich only the existing stub bodies (6) + author only the sub-track-relevant new
    architecture siblings (`infra-architect`, `devex-architect` if they enter `_SUBTRACK_SPECIALISTS`),
    defer the rest of the planned-6 to a follow-up. *(~8 files; prioritises live dispatch paths.)*
  - **Recommendation:** **D1=(b)** if Epic-2B production-readiness is the bar (no live placeholder
    bodies, full matrix §3 fulfilment); fall back to **D1=(c)** if scope must stay near "~6".
    Confirm before authoring.

- **D2 — `api-architect?` data defect.** The brief flags `api-architect?` (with `?`). This repo's
  matrix has **no** `api-architect`; the confirmed planned wire-format role is **`api-designer`**
  (matrix §3, target 2B.9). Choose:
  - **D2=(a)** Treat `api-architect` as a non-existent/unconfirmed name — do NOT author or register
    it; author `api-designer` only if D1 admits it. *(Correct per the matrix as frozen; default.)*
  - **D2=(b)** Author `api-architect` — **rejected**: not in the frozen matrix; would need an ADR
    amendment per the matrix update rule. Confirm ADR-030's stance before any deviation.
  - **Recommendation / default:** **D2=(a).**

- **D3 — UX-track depth (`ux-reviewer` parallel-reviewer debt).** `ux-reviewer` shipped deferred
  (`EPIC-2A-DEBT-UX-PARALLEL-REVIEWER`): real reviewer content + synthesizer wiring were pushed to
  2B.9. Choose:
  - **D3=(a)** Author the full `ux-reviewer` production prompt now and close the debt (requires
    confirming the synthesizer-wiring expectation from 2A.13).
  - **D3=(b)** Author the `ux-reviewer` prompt body only (content), and keep the parallel-dispatch
    wiring deferred — record the residual debt in `deferred-work.md`.
  - **Recommendation:** **D3=(a)** if D1=(b); otherwise **D3=(b)** with the debt re-logged.

- **D4 — Matrix rename at authoring time.** Matrix §3 marks the planned-6 names *tentative* ("Epic 2B
  authoring may rename to match the shipped-naming convention"). Decide whether each admitted name
  ships as-is or is renamed to the `*-author` / `*-architect` / `*-reviewer` convention (e.g. keep
  `design-system-author`, possibly rename `a11y-reviewer`→`accessibility-reviewer`). Any rename
  updates BOTH `index.yaml` and the matrix in the same PR (AC7). **Recommendation:** ship matrix
  names as-is unless a reviewer flags a convention break — minimise churn.

## Dev Agent Record

### Context Reference

Worktree: `epic-2b/2b-9-phase2-specialists` at `../wt-2b-9`. Branches from main @ e5c72a0 (post-2B.8).
D1=(b): 12 files total (6 enrich + 6 new). D2=(a). D3=(a). D4=no-rename.
Sub-track allowlist (architect.py): add infra-architect + devex-architect per AC8.
Boundary-line architectural invariant: specialist bodies must NOT contain BOUNDARY_LINE (builder injects it).

### Agent Model Used

Claude Opus 4.8 (1M context)

### Debug Log References

### Completion Notes List

All 13 ACs satisfied. D1=(b)/D2=(a)/D3=(a)/D4=no-rename.

**T2 (6 enriched stubs):**
- system-architect: requires: frontmatter contract + full ARCHITECTURE.md template
- database-architect: schema/ER/migration strategy/query patterns
- security-architect: threat model + auth/authz + data protection + controls
- observability-architect: logging/RED metrics/tracing/SLO definitions
- ux-designer: design tokens/user flows/screen specs; JSON-array output contract preserved
- ux-reviewer: full parallel review report; D3=(a) authors the production prompt body.
  NOTE (code review CR2B9-DN3): EPIC-2A-DEBT-UX-PARALLEL-REVIEWER remains OPEN — this story
  delivers the prompt body only; the body still "feeds the UX synthesizer (when wired)" and no
  synthesizer/parallel-dispatch wiring is added here. Debt closes when the UX-track wiring lands.

**T3 (6 net-new specialists):**
- ux-researcher: user needs synthesis, interaction patterns, IA recommendations
- design-system-author: token contract, component inventory, variant taxonomy
- a11y-reviewer: WCAG 2.1 AA audit (contrast/keyboard/ARIA/motion/touch targets)
- infra-architect: deployment topology, containers, networking, scaling (sub-track)
- devex-architect: local dev setup, CI/CD pipeline design, code quality gates (sub-track)
- api-designer: REST endpoints, schema types, auth flows, error catalogue

**T4 (registry + matrix):** index.yaml +6 rows; matrix §1 26→32, §3 11→5; architect.py adds
infra+devex to _SUBTRACK_SPECIALISTS (AC8).

**T5 (gate):** 9/9 2b9-authoring tests GREEN; 111 specialist tests GREEN; 3 conformance GREEN;
boundary gate exit 0; ruff/mypy/pre-commit/mkdocs/wire-format all PASS; full pytest 2840 passed.

**Architectural invariant verified:** no Phase-2 body contains BOUNDARY_LINE (phase1_prompt_builder
injects it; specialist bodies must NOT pre-contain it — same finding as 2B.8).

Commits: test(RED) → feat(GREEN), TDD ordering visible in `git log --reverse`.

### File List

**Modified (6 enriched stubs):**
- src/sdlc/agents/phase2/system-architect.md
- src/sdlc/agents/phase2/database-architect.md
- src/sdlc/agents/phase2/security-architect.md
- src/sdlc/agents/phase2/observability-architect.md
- src/sdlc/agents/phase2/ux-designer.md
- src/sdlc/agents/phase2/ux-reviewer.md

**Created (6 net-new specialists):**
- src/sdlc/agents/phase2/ux-researcher.md
- src/sdlc/agents/phase2/design-system-author.md
- src/sdlc/agents/phase2/a11y-reviewer.md
- src/sdlc/agents/phase2/infra-architect.md
- src/sdlc/agents/phase2/devex-architect.md
- src/sdlc/agents/phase2/api-designer.md

**Modified (registry + matrix + sub-track allowlist + wheel allowlist + tests):**
- src/sdlc/agents/index.yaml
- src/sdlc/cli/architect.py
- docs/specialists-matrix.md
- tests/integration/test_wheel_build.py

**Created (TDD receipts):**
- tests/unit/specialists/test_phase2_2b9_authoring.py

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-05-29 | 0.1 | Context-engineered from matrix/index/phase2 ground truth (create-story) | Bob (SM) |
| 2026-06-01 | 0.2 | T0 decisions resolved: D1=(b)/D2=(a)/D3=(a)/D4=no-rename; worktree created; story in-progress | Claude Opus 4.8 |
| 2026-06-01 | 1.0 | Full implementation: 6 stubs enriched + 6 net-new + registry/matrix/gate; story → review | Claude Opus 4.8 |
