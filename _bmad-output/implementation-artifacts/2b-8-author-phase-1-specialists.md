# Story 2B.8: Author Phase 1 Specialists

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer populating the Phase 1 specialist suite for the FIRST EXTERNAL SHIP,
I want every Phase-1 specialist markdown file authored as a production-quality system prompt (real role body + canonical data-vs-instruction boundary line) that replaces the registry-valid placeholders shipped under Epic 2A, AND the new matrix §3 Phase-1 specialists authored + registered,
so that when real Claude dispatch (2B.1) runs the Phase-1 panel, every specialist emits the intended artifact instead of a placeholder stub, and the roster passes registry validation + the 2B.3 conformance harness.

## Acceptance Criteria

> **Source ACs:** `_bmad-output/planning-artifacts/epics.md:1628-1656` ("Story 2B.8: Author Phase 1 Specialists (~7 Markdown Files)") + `docs/sprints/epic-2b-dag.md` §5 (worktree/scope node) + `docs/specialists-matrix.md` §3 (canonical planned roster) + ADR-030 (roster reconciliation). The epics.md story body + the matrix §3 planned rows are the binding scope.
> **DAG position:** **Layer 3**, Epic 2B. Depends on **2B.3** (`done` — behavioral conformance Mock-vs-Claude). Critical path `2B.1 → 2B.3 → {2B.8, 2B.9, 2B.10} → 2B.11` (DAG §4). 2B.11's 25-specialist count gate + matrix regen depends on this story completing.
> **No wire-format contract is touched.** `SpecialistFrontmatter` (`src/sdlc/contracts/specialist_frontmatter.py`, `StrictModel`, `schema_version: Literal[1]`, ADR-024) is **consumed, not modified**. Authoring markdown that conforms to the frozen schema does NOT require a snapshot regeneration ceremony. `scripts/freeze_wireformat_snapshots.py --check` MUST stay green (5/5); snapshot count unchanged. `index.yaml` and the matrix are data/docs, not wire-format.
>
> **Scope boundary — do NOT reinvent:**
> - **The `SpecialistFrontmatter` contract already exists** (Story 1.7 / 2A.2, `src/sdlc/contracts/specialist_frontmatter.py`). Author files to satisfy it; do **not** add/remove fields or relax validators. **Verified exact schema in Dev Notes** — note it has NO `role`, NO `phase`, NO `boundary_line` field; `phase` lives in `index.yaml`, not the frontmatter.
> - **The registry + manifest validator already exists** (Story 2A.2, `src/sdlc/specialists/`). Do NOT rebuild it — add files + manifest entries that pass `load_registry()` + the 2A.2 validators.
> - **The existing 7 Phase-1 files are PLACEHOLDER STUBS authored under Epic 2A explicitly for THIS story to replace** (see Dev Notes "Stub-vs-Production finding"). Their bodies literally say *"placeholder; Story 2B.8 ships the real specialist content"* / *"Replaced by Story 2B.8 with full content"*. Re-authoring them to production prompts is **IN SCOPE** (this is the core of the story — see D1).

### AC1 — Existing Phase-1 placeholder stubs replaced with production prompts

**Given** the 8 Phase-1 specialist files registered in `src/sdlc/agents/index.yaml` (`product-strategist`, `technical-researcher`, `devil-advocate`, `requirement-synthesizer`, `artifact-verifier`, `epic-generator`, `story-writer`, `phase1-signoff-summarizer`)
**When** each file's body is rewritten from its current placeholder ("(Phase 1 placeholder)" / "Replaced by Story 2B.8 with full content") to a production-quality system prompt
**Then** each body contains a real role statement, explicit responsibilities, the artifact it authors + its output contract/shape, and the canonical data-vs-instruction boundary line (AC4)
**And** the frontmatter `description` is updated from the placeholder text (e.g. "Replaced by Story 2B.8 with full content") to a real one-line description
**And** the `name` / `schema_version` / `title` / `icon` / `model` / `read_globs` / `write_globs` frontmatter values remain valid (changing `write_globs` is allowed if the production prompt requires it — verify the target path matches the Phase-1 artifact layout, see D3)
**And** no placeholder marker string (`placeholder`, `Replaced by Story 2B.8`, `until Story 2B.x`) remains in any Phase-1 file

> **`phase1-signoff-summarizer` caveat:** its stub says it is "NOT dispatched in v1 (AC1/D1 decision) — SIGNOFF.md generated mechanically". Authoring its production prompt is still in scope (it is registered), but confirm whether v1 actually dispatches it before investing in deep prompt content. See D4.

### AC2 — New matrix §3 Phase-1 specialists authored (exact names)

**Given** the canonical planned roster in `docs/specialists-matrix.md` §3 "Phase 1 planned (7)" + "Support planned (1)", all tagged target story 2B.8
**When** the net-new specialist markdown files are authored under `src/sdlc/agents/phase1/`
**Then** one file is authored per net-new planned name resolved in **D1**, using the **exact** matrix name (or a rename per ADR-030, with the matrix row updated in the same PR)
**And** each new file's `name:` frontmatter equals its filename stem
**And** each new file carries a complete, production-quality body (role statement, responsibilities, output contract, boundary line) — not a placeholder

> **Matrix §3 Phase-1 planned roster (target 2B.8), verified against disk + manifest at story-creation 2026-05-29 — NONE of these 8 exist yet:**
>
> | Matrix §3 name | Section | On disk / in manifest? |
> |---|---|---|
> | `requirement-analyst` | Phase-1 planned | no |
> | `market-researcher` | Phase-1 planned | **no** (matrix says "Pairs with technical-researcher"; NOT yet authored) |
> | `stakeholder-simulator` | Phase-1 planned | no |
> | `dependency-mapper` | Phase-1 planned | no |
> | `prioritizer` | Phase-1 planned | no |
> | `acceptance-criteria-author` | Phase-1 planned | no |
> | `story-prioritizer` | Phase-1 planned | no |
> | `clarification-triager` | Support planned | no |
>
> The DAG node says "~7 markdown files" — that maps to the 7 §3 "Phase 1 planned" rows. `clarification-triager` is a §3 Support row also tagged 2B.8 (D1 decides whether it lands here). **Net-new files = 7 (Phase-1 planned) or 8 (incl. Support), per D1.**

### AC3 — Complete frontmatter + manifest entry per new file; registry loads clean

**Given** each newly-authored specialist markdown file
**When** the Story 2A.2 registry loader parses it (`src/sdlc/specialists/` — `load_registry()` / frontmatter validator)
**Then** the frontmatter validates against `SpecialistFrontmatter` with all required fields present (exact schema in Dev Notes): `schema_version: 1`, `name`, `title`, `icon` (1–4 chars), `model` (`sonnet` is the established Phase-1 default — every existing Phase-1 stub uses `sonnet`; confirm against any per-role guidance), `description`, plus `tools` / `read_globs` / `write_globs` lists (empty list allowed)
**And** a manifest entry is appended to `src/sdlc/agents/index.yaml` for each new file with `name` / `phase: 1` / `file: phase1/<name>.md` (the manifest schema — NO `role`/`model` keys in `index.yaml`; those live in the frontmatter)
**And** `load_registry()` loads the full roster with **zero** error — every manifest entry resolves to a file whose frontmatter `name` matches, and the 2A.2 cross-ref validators (`validate_workflow_refs` / `validate_internal_links`) pass

### AC4 — Canonical data-vs-instruction boundary line in every Phase-1 prompt body

**Given** the NFR-SEC-3 boundary-line convention (Story 2B.5 / `docs/threat-model.md`) and `EPIC-2B-DEBT-SPECIALIST-BODY-BOUNDARY-NORMALIZE` (CR2B4-W4)
**When** each Phase-1 specialist body (both the 8 re-authored AND the net-new) is finalized
**Then** the body contains the canonical data-vs-instruction boundary directive so that, when the dispatcher interpolates the specialist body into a real Claude prompt, the agent treats downstream user/artifact text as DATA not INSTRUCTIONS
**And** the exact canonical boundary-line form is taken from `docs/threat-model.md` / the 2B.5 `BOUNDARY_LINE` constant (`src/sdlc/dispatcher/prompts.py`) — verify the canonical string at implementation time; do NOT invent a new wording

> **AC4 scope clarification — which boundary check applies:** `scripts/check_boundary_line_presence.py` (Story 2B.5) scans `src/sdlc/dispatcher/prompts.py` `*_prompt_builder` **functions** for `BOUNDARY_LINE` ordering — it does **NOT** scan agent `.md` frontmatter or bodies. So there is **no automated gate** today that forces a boundary line into a specialist `.md` body. AC4 is therefore an authoring-quality requirement backed by the open debt `EPIC-2B-DEBT-SPECIALIST-BODY-BOUNDARY-NORMALIZE` (CR2B4-W4) + `EPIC-2B-DEBT-SPECIALIST-BODY-BOUNDARY` (CR2B5-related). **D2** decides whether 2B.8 also ships a lightweight static check that asserts each Phase-1 body contains the canonical boundary string (closing the debt), or authors-by-convention and leaves the gate to a later story.

### AC5 — 2B.3 conformance harness exercises ≥1 Phase-1 specialist

**Given** the 2B.3 behavioral-conformance harness (`tests/integration/test_abstraction_adequacy.py`, `done`)
**When** the harness runs (offline Mock + stub-Claude legs; `_RUNTIME_FACTORIES = [_mock_factory, _claude_factory]`)
**Then** the pipeline dispatches a Phase-1 specialist through BOTH runtimes and asserts byte-identical HookPayload sequences + final `state.json` (the existing `test_abstraction_adequacy_pipeline` + `test_cross_runtime_byte_identity`)
**And** the harness exercises **≥1 Phase-1 specialist** — satisfied because the abstraction-adequacy seed fixture (`tests/fixtures/mock_responses/abstraction-adequacy.yaml`) drives a Phase-1 dispatch
**And** per epics.md AC ("adding a fixture for the new specialist is sufficient to extend conformance coverage; no test code changes are required for typical specialist additions") — if D5 elects to extend coverage to a NEW specialist, do so by **adding a fixture**, not by editing harness code
**And** the conformance suite stays green (current baseline per sprint-status: full suite `2825 passed`)

> **AC5 satisfaction note:** the epics.md 2B.8 AC says "When Phase 1 specialists are exercised end-to-end through Mock and Claude runtimes / Then [conformance passes]". The ≥1-specialist bar is already met by the existing seed fixture's Phase-1 dispatch. Re-authoring the existing stubs to production bodies changes the **prompt text** the builder emits, which can shift Phase-1 prompt hashes and may invalidate MockAIRuntime fixtures (this exact hazard bit 2B.6 — see Dev Notes "Fixture-hash hazard"). The dev MUST re-run the full suite and regenerate affected goldens/fixtures with justification, NOT force-pass. See D3 + Dev Notes.

### AC6 — Anti-tautology receipt (ADR-026 §1)

**Given** ADR-026 §1 (anti-tautology requirement)
**When** the test suite runs
**Then** a **load-bearing receipt** proves the new authoring is actually validated:
  - a positive receipt asserts `load_registry()` returns a roster whose keys include every NEW specialist name (proves the new files parsed + manifest-linked)
  - a negative receipt asserts a deliberately-malformed specialist (e.g. `name` with a space, missing `description`, or `icon` >4 chars) is **rejected** by the 2A.2 frontmatter validator — proving the gate *can* fail (model on the existing 2A.2 loader-failure tests; verify their location — the 2A.2 tests live under `tests/unit/` near the `specialists` mirror, NOT `tests/unit/agents/` which does not exist)
**And** RED-before-GREEN ordering is visible in `git log --reverse` for any net-new test/helper surface (CONTRIBUTING §2)

## Tasks / Subtasks

- [x] **Task 0 — Resolve D1–D5 before authoring** (AC: all)
  - [x] D1 (authoring scope): confirm net-new count = 7 (Phase-1 planned) vs 8 (incl. `clarification-triager`). **Decision: D1=(a)** — author the 7 Phase-1-planned net-new + re-author the 8 existing stubs; defer `clarification-triager`.
  - [x] D2 (boundary-line gate): **Decision: D2=(a)** — convention-only; no `.md`-body boundary check. Implementation finding: `phase1_prompt_builder` (prompts.py:241) REJECTS bodies containing `BOUNDARY_LINE` (builder injects it automatically between `<INSTRUCTIONS>` and `<USER_IDEA>`). D2=(b) was architecturally incorrect; CR2B4-W4 remains open for the correct gate (verifying compiled prompt, not body).
  - [x] D3 (write_globs / artifact paths): authoring roles → `01-Requirement/...`; adversarial/analysis/routing roles → `write_globs: []`. Confirmed matches existing layout.
  - [x] D4 (`phase1-signoff-summarizer`): NOT dispatched in v1 (SIGNOFF.md generated mechanically). Authored real-but-concise production body; registered.
  - [x] D5 (conformance breadth): D5=(a) — leave harness unchanged. Conformance fixture uses static seed hash; re-authored bodies caused zero fixture drift (3/3 conformance tests pass).
  - [x] **CRITICAL re-verify**: confirmed 8 placeholder stubs on disk + 0 net-new present at start. Registry loaded 19 specialists (8 phase1) before implementation.

- [x] **Task 1 — Anti-tautology receipt FIRST (RED)** (AC: 6)
  - [x] Failing test: `tests/unit/specialists/test_phase1_2b8_authoring.py` — 5 tests failed RED (positive receipt + boundary + placeholder), 2 passed (negative receipts). RED confirmed before implementation.
  - [x] Negative receipt: `icon-too-long.md` + `missing-description.md` fixtures created; both rejected by 2A.2 validator immediately.

- [x] **Task 2 — Re-author the 8 existing Phase-1 placeholder stubs to production prompts** (AC: 1, 4)
  - [x] All 8 stubs re-authored with role statement, responsibilities, output contract; descriptions updated; frontmatter valid.
  - [x] No placeholder marker strings remain under `src/sdlc/agents/phase1/` (verified by `test_no_phase1_body_contains_placeholder_marker`).

- [x] **Task 3 — Author the net-new matrix §3 Phase-1 specialists** (AC: 2, 3, 4)
  - [x] All 7 net-new files created with full frontmatter + production body. `write_globs` per D3: authoring roles → `01-Requirement/...`; analysis/adversarial/routing → `write_globs: []`.

- [x] **Task 4 — Manifest + registry** (AC: 3)
  - [x] 7 entries appended to `src/sdlc/agents/index.yaml` (name/phase:1/file). Registry loads: 26 total specialists, 15 phase1, zero errors.

- [x] **Task 5 — Reconcile `docs/specialists-matrix.md` in the SAME PR** (AC: 2)
  - [x] §1 Shipped updated 19→26 with all 15 Phase-1 specialists (8 re-authored + 7 net-new). §3 Phase-1 planned section removed (all 7 authored). §4 totals updated (Shipped 26, Planned 11, Grand total 37 unchanged).
  - [x] No renames occurred; ADR-030 amendment not required.

- [x] **Task 6 — Conformance + fixture hygiene** (AC: 5)
  - [x] `tests/integration/test_abstraction_adequacy.py` — 3/3 passed. Zero fixture drift (abstraction-adequacy fixture uses static "seed prompt" hash, independent of specialist body text).
  - [x] D5=(a): harness unchanged; existing seed fixture meets ≥1-Phase-1 bar.

- [x] **Task 7 — Quality gate** (AC: all)
  - [x] `ruff format` + `ruff check` + `mypy --strict` — all passed.
  - [x] `pytest` full suite — **2832 passed**, 4 skipped, 0 failed. Coverage **87.28% ≥ 87%**.
  - [x] `pre-commit run --all-files` — all 19 hooks PASS. `mkdocs --strict` — PASS. `freeze_wireformat_snapshots.py --check` — **5/5**.

## Dev Notes

### Stub-vs-Production finding (resolves the DAG §6 / brief scope ambiguity)

The DAG node says "~7 markdown files" and the brief asked whether 2B.8 must enrich the existing Phase-1 files. **Verified by reading every file: the existing Phase-1 files ARE placeholder stubs, authored under Epic 2A explicitly for 2B.8 to replace.** Examples (verbatim):
- `product-strategist.md` body: *"# product-strategist (Phase 1 placeholder) … This is a placeholder; Story 2B.8 ships the real specialist content."*
- `technical-researcher.md` body: *"# technical-researcher (Phase 1 placeholder) … Placeholder until Story 2B.8."*; description: *"Replaced by Story 2B.8 with full content."*
- `requirement-synthesizer.md`, `devil-advocate.md`, `epic-generator.md`, `story-writer.md`: same "(Phase 1 placeholder)" pattern.
- `phase1-signoff-summarizer.md`: *"v1 stub — NOT dispatched in v1 … Registered for Story 2B.8 activation."*

**Therefore the recommended scope (D1=(a)) is: BOTH re-author the 8 existing stubs to production prompts AND author the 7 net-new §3 planned specialists.** This is the OPPOSITE of "the existing files are already production-quality" — they are explicitly placeholders. This is the core reason 2B.8 exists now that 2B.1 ships REAL Claude dispatch: a real model running a placeholder body produces a one-line stub artifact instead of the intended deliverable.

### EXACT frontmatter schema (verified from `src/sdlc/contracts/specialist_frontmatter.py`)

`SpecialistFrontmatter(StrictModel)` — frozen wire-format contract (ADR-024). Fields (NOTE: there is **NO `role`, NO `phase`, NO `boundary_line`** field — the brief/template assumptions about those are wrong):

| Field | Type | Constraints |
|---|---|---|
| `schema_version` | `Literal[1]` | strict int, must be `1` |
| `name` | `str` | (validated downstream against filename + manifest) |
| `title` | `str` | human-readable title |
| `icon` | `str` | `min_length=1, max_length=4` (emoji) |
| `model` | `str` | every existing Phase-1 file uses `sonnet` |
| `tools` | `tuple[str, ...]` | default empty; YAML list (coerced from list) |
| `read_globs` | `tuple[str, ...]` | default empty; YAML list |
| `write_globs` | `tuple[str, ...]` | default empty; YAML list |
| `description` | `str` | one-line description |

`StrictModel` base forbids extra fields (`# strict-opt-out` would be required to deviate — do NOT). **`phase` is declared in `index.yaml`, not in the frontmatter.**

Canonical example (verbatim shape from the current `product-strategist.md` stub — body to be replaced, frontmatter shape preserved):
```yaml
---
schema_version: 1
name: product-strategist
title: "Product Strategist"
icon: "🎯"
model: sonnet
tools: []
read_globs: []
write_globs:
  - "01-Requirement/01-PRODUCT.md"
description: "Phase 1 product strategy. Replaced by Story 2B.8 with full content."
---
```
[Source: src/sdlc/contracts/specialist_frontmatter.py] [Source: src/sdlc/agents/phase1/product-strategist.md]

### `index.yaml` manifest schema (verified)

```yaml
schema_version: 1
specialists:
  - name: product-strategist
    phase: 1
    file: phase1/product-strategist.md
  # ... one entry per specialist
```
Keys are `name` / `phase` / `file` only — **no `role`, no `model`** in the manifest (those live in the `.md` frontmatter). Manifest currently holds 19 specialists (8 phase1 + 6 phase2 + 5 phase3). [Source: src/sdlc/agents/index.yaml]

### Artifact-path layout (existing stubs use `01-Requirement/...`)

The existing Phase-1 stubs write to a `01-Requirement/`-rooted layout, NOT `_bmad-output/planning-artifacts/`:
- `product-strategist` / `technical-researcher` / `requirement-synthesizer` / `devil-advocate` → `01-Requirement/01-PRODUCT.md`
- `epic-generator` → `01-Requirement/04-Epics/*.json`
- `story-writer` → `01-Requirement/05-Stories/*/*.json`
- `artifact-verifier` → `01-Requirement/**/*.md`
- `phase1-signoff-summarizer` → `01-Requirement/SIGNOFF.md`

**New specialists' `write_globs` MUST match this `01-Requirement/...` convention**, not the `_bmad-output/` path. Confirm the exact sub-path per role at implementation time (D3). [Source: src/sdlc/agents/phase1/*.md]

### Registry-validation contract (what a new specialist MUST pass — Story 2A.2)

The real validator lives in `src/sdlc/specialists/` (Story 2A.2: registry + manifest + frontmatter validators — `load_registry`, `validate_workflow_refs`, `validate_internal_links`). A new specialist requires a coordinated change in the **same PR**: (1) the `.md` file with valid frontmatter, (2) the `index.yaml` manifest entry, (3) the matrix row.

**IMPORTANT — `scripts/validate_specialists.py` is a v0.2 PLACEHOLDER, not the real validator.** It currently prints *"[v0.2 placeholder] specialists/ is empty; cross-ref pipeline activates with Story 2A-2"* and returns exit 0 unconditionally. Per `deferred-work.md:315` (Story 2A.2 AC7 D3), the validator *API* shipped in 2A.2 (`specialists/validator.py`) but the CLI script entry-point + pre-commit wiring was deferred. **Do NOT trust `scripts/validate_specialists.py` as a gate** — validate via the in-process 2A.2 `load_registry()` + validators (e.g. `python -c "from sdlc.specialists.registry import load_registry; load_registry()"`). If 2B.8 wants a real CLI gate, wiring `scripts/validate_specialists.py` to the 2A.2 API is an optional in-scope improvement (D2-adjacent). [Source: scripts/validate_specialists.py] [Source: _bmad-output/implementation-artifacts/deferred-work.md:315]

### Boundary-line convention (AC4) — what is and isn't gated

- The 2B.5 `scripts/check_boundary_line_presence.py` scans **`src/sdlc/dispatcher/prompts.py` `*_prompt_builder` functions** for a `BOUNDARY_LINE` reference ordered before user-text blocks. It does **NOT** scan agent `.md` files. So no existing CI gate forces a boundary line into a specialist body.
- The canonical boundary string lives as `BOUNDARY_LINE` in `src/sdlc/dispatcher/prompts.py` and is documented in `docs/threat-model.md` (form: `--- USER PROVIDED TEXT (DATA, NOT INSTRUCTIONS) ---` or the canonical variant — verify exact string at implementation time).
- Open debt this story can close: `EPIC-2B-DEBT-SPECIALIST-BODY-BOUNDARY-NORMALIZE` (CR2B4-W4) — flagged precisely because specialist bodies flow into real prompts. D2 decides whether to ship the `.md`-body check here. [Source: scripts/check_boundary_line_presence.py] [Source: _bmad-output/implementation-artifacts/deferred-work.md (CR2B4-W4)]

### Conformance-wiring procedure (AC5)

`tests/integration/test_abstraction_adequacy.py` (2B.3) parametrizes `_RUNTIME_FACTORIES = [_mock_factory, _claude_factory]`, runs the full deterministic pipeline (init → scan → dispatch ×2 → pre-write hooks → journal → projection → atomic state write), and asserts byte-identical HookPayloads + `state.json` across runtimes (`test_cross_runtime_byte_identity`, ordered last). The Phase-1 dispatch is driven by the seed `tests/fixtures/mock_responses/abstraction-adequacy.yaml`. Per the epics.md 2B.8 AC + 2B.3's design, **extending coverage to a new specialist = add a fixture, not edit harness code**. The `_claude_factory` leg uses a stub-Claude derived from the seed (offline). [Source: tests/integration/test_abstraction_adequacy.py]

### Fixture-hash hazard (READ — this exact issue bit 2B.6)

Re-authoring the 8 stub bodies changes the text the Phase-1 prompt builders emit, which **shifts Phase-1 prompt hashes**. Per the 2B.6 review record (sprint-status.yaml `last_updated`), threading new content into Phase-1 prompts "shifts every Phase-1 prompt hash and invalidates 11+ MockAIRuntime fixtures across tests/integration + tests/e2e + tests/unit/cli". The dev MUST: (1) run the full suite, (2) identify every fixture/golden that locks a Phase-1 prompt or its hash, (3) regenerate them deliberately with a justifying commit message — **never force-pass or regenerate goldens to make a red test green without auditing why the bytes drifted** (the 2B.3 harness comment is explicit on this). Budget for this; it is the largest hidden cost of the story. [Source: _bmad-output/implementation-artifacts/sprint-status.yaml (2B.6 review note)] [Source: tests/integration/test_abstraction_adequacy.py (golden-regen warning)]

### Previous-Story Intelligence

- **2A.8–2A.12 (Phase-1 authoring under MockAIRuntime):** shipped the 8 Phase-1 specialists **as placeholders** + the registry plumbing + the `phase1_prompt_builder` / `phase1_compound_prompt_builder`. Established the frontmatter shape, the `01-Requirement/...` artifact layout, and the `sonnet` model default. `_default_prompt_builder` returns `specialist.body` (a prompt-injection vector flagged as deferred — the boundary-line in the body is the mitigation). [Source: src/sdlc/agents/phase1/*.md, deferred-work.md W1:333]
- **2A.2 (registry/manifest/validator):** built `src/sdlc/specialists/` (loader, manifest, frontmatter validator, `validate_workflow_refs`/`validate_internal_links`) + `SpecialistFrontmatter`. The contract surface 2B.8 must satisfy. [Source: src/sdlc/specialists/, src/sdlc/contracts/specialist_frontmatter.py]
- **2B.1 (`done`):** real `ClaudeAIRuntime` + subprocess management — the reason placeholder bodies are now a correctness bug, not just incompleteness. [Source: epics.md Epic 2B]
- **2B.3 (`done`):** behavioral conformance Mock-vs-Claude (`test_abstraction_adequacy.py`) — the AC5 harness. [Source: tests/integration/test_abstraction_adequacy.py]
- **2B.5 (`done`):** boundary-line presence check for prompt-builder functions + the `BOUNDARY_LINE` constant + the destructive-op token block. [Source: scripts/check_boundary_line_presence.py]
- **2B.6 (`done`):** demonstrated the Phase-1-prompt-hash fixture-invalidation hazard (Dev Notes above). [Source: sprint-status.yaml]

### Sibling / Worktree Coordination (CRITICAL — shared `index.yaml` + matrix edits)

- **Worktree:** `epic-2b/2b-8-phase1-specialists` (owner: **Alice**, DAG §5).
- **2B.8 / 2B.9 / 2B.10 ALL edit `src/sdlc/agents/index.yaml`** (phase1 / phase2 / phase3 sections) AND `docs/specialists-matrix.md` (§1/§3/§4). Per CONTRIBUTING §3 (worktree-per-story at the same DAG layer; only one worktree merges to `main` at a time; others rebase + re-run CI after each merge): the **first merger owns the shared `index.yaml` + matrix edits**; the later two **rebase** onto updated `main` and re-apply their phase section + matrix rows additively. The three stories touch **disjoint** `index.yaml` phase sections and **disjoint** matrix rows, so conflicts are mechanical (adjacent list/table additions). The matrix §4 totals row is the one truly shared line — whoever merges later updates the running total. [Source: docs/sprints/epic-2b-dag.md §5] [Source: CONTRIBUTING.md §3 (lines 77-88)]
- 2B.8 ALSO re-authors the 8 existing `phase1/*.md` bodies — these are 2B.8-exclusive files (phase2/phase3 stubs are 2B.9/2B.10's). No cross-story file conflict on the bodies themselves.

### Module boundary guardrail

Specialists are **content, not modules** (ADR-010) — no `src/` module-boundary table row applies to the `.md` files. `index.yaml` + the matrix are data/docs. Any new Python (AC6 test helpers only) lives under `tests/` (unrestricted). No `src/sdlc/` runtime module is added or re-wired.

### Project Structure Notes

- **New:** `src/sdlc/agents/phase1/<name>.md` × (7 or 8 per D1); an anti-tautology test + negative-fixture (AC6) beside the existing 2A.2 specialist tests.
- **Modified:** all 8 existing `src/sdlc/agents/phase1/*.md` bodies (AC1); `src/sdlc/agents/index.yaml` (append phase1 entries — shared; rebase per §3); `docs/specialists-matrix.md` (§1 rows + §3 removals + §4 totals — shared; rebase per §3); possibly affected MockAIRuntime fixtures/goldens (AC5 hash drift); possibly `docs/decisions/ADR-030-specialist-roster-freeze.md` (if a rename occurs); possibly `_bmad-output/implementation-artifacts/deferred-work.md` (close CR2B4-W4 if D2=(b)).
- **NOT touched:** `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flip handled by the workflow), any phase2/phase3 file, any wire-format contract or snapshot, `src/sdlc/contracts/specialist_frontmatter.py`.

### Testing standards summary

- TDD-first (CONTRIBUTING §2): AC6's registry-inclusion + negative malformed-frontmatter tests written RED-before-GREEN; visible in `git log --reverse`.
- Anti-tautology (ADR-026 §1): the negative receipt proves the validator can reject; the positive receipt proves new files actually loaded.
- Test org: place AC6 tests beside the existing 2A.2 `specialists` tests (NOT `tests/unit/agents/`, which does not exist — verify the 2A.2 test path: the `specialists` mirror under `tests/unit/`).
- Quality gate (CONTRIBUTING §1): ruff format + ruff check + mypy --strict + pytest + coverage ≥87 + pre-commit --all-files + mkdocs --strict + wire-format snapshots 5/5.

### Decisions Needed (per CONTRIBUTING §5 — option-labels)

- **D1 — Authoring scope.** Matrix §3 lists 7 Phase-1 planned + 1 Support (`clarification-triager`), all tagged 2B.8; plus 8 existing stubs to re-author.
  - **D1(a) [Recommended]:** re-author the **8 existing stubs** to production prompts + author the **7 net-new Phase-1-planned** specialists; defer `clarification-triager` (Support / dispatcher-routing role, not a pure Phase-1 panel prompt). Matches "~7 markdown files" + the stub-replacement mandate. **Con:** `clarification-triager` stays planned one more sprint.
  - **D1(b):** D1(a) + `clarification-triager` (8 net-new). **Pro:** clears the entire §3 "target 2B.8" queue. **Con:** `clarification-triager` behaviour depends on dispatcher STOP-trigger routing — may not be wireable as a standalone prompt yet.
  - **D1(c):** author the 7 net-new only, leave the 8 stubs as-is. **Con:** contradicts the stubs' own "Story 2B.8 ships the real content" mandate and leaves real Claude dispatch emitting placeholder artifacts; **not recommended.**
- **D2 — Boundary-line gate for `.md` bodies (AC4).**
  - **D2(a):** author-by-convention; no new check; leave `EPIC-2B-DEBT-SPECIALIST-BODY-BOUNDARY-NORMALIZE` open. **Con:** a future specialist can ship without the boundary line undetected — and these bodies now feed REAL Claude.
  - **D2(b) [Recommended]:** ship a light static check asserting each Phase-1 `.md` body contains the canonical `BOUNDARY_LINE` string; close CR2B4-W4. **Pro:** closes a live prompt-injection gap now that 2B.1 dispatches real Claude. **Con:** small extra surface; coordinate the canonical-string source with 2B.5.
- **D3 — `write_globs` / artifact paths.** New specialists' globs must use the `01-Requirement/...` layout (NOT `_bmad-output/`). **Recommended:** authoring roles → a specific `01-Requirement/...` artifact path; adversarial/analysis/routing roles → `write_globs: []`. Confirm exact sub-paths against the Phase-1 artifact layout + any FR mapping at implementation time.
- **D4 — `phase1-signoff-summarizer` depth.** Its stub says "NOT dispatched in v1 (SIGNOFF.md generated mechanically)". **Recommended:** author a real-but-concise production body (it is registered + 2B.3 may load it) but do not over-invest until v1 dispatch status is confirmed; record the confirmation in the PR.
- **D5 — Conformance breadth (AC5).**
  - **D5(a) [Recommended]:** leave the harness unchanged; the existing seed fixture meets the ≥1-Phase-1-specialist bar. Re-run full suite + regenerate Phase-1 fixtures that drift from re-authored bodies (the real work).
  - **D5(b):** add a seed fixture exercising a NEW specialist Mock-vs-Claude (fixture-only, per 2B.3's "no code change" contract). **Pro:** stronger per-specialist coverage. **Con:** more golden maintenance.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1628-1656] — Story 2B.8 body + ACs ("~7 Markdown Files"; "exercised end-to-end through Mock and Claude runtimes"; "adding a fixture is sufficient")
- [Source: docs/sprints/epic-2b-dag.md] — §3 Layer 3 (2B.8 depends on 2B.3), §4 critical path, §5 worktree (owner Alice, `epic-2b/2b-8-phase1-specialists`, "names per frozen docs/specialists-matrix.md C5/ADR-030")
- [Source: docs/specialists-matrix.md] — §1 Shipped (8 Phase-1), §3 Planned (7 Phase-1 + 1 Support, target 2B.8), §4 Totals, §5 update rule
- [Source: docs/decisions/ADR-030-specialist-roster-freeze.md] — reconciliation; forward rule "matrix planned→shipped on landing; rename requires ADR amendment"
- [Source: src/sdlc/contracts/specialist_frontmatter.py] — `SpecialistFrontmatter` EXACT schema (schema_version/name/title/icon/model/tools/read_globs/write_globs/description; NO role/phase/boundary_line)
- [Source: src/sdlc/agents/index.yaml] — manifest schema (name/phase/file); 19 specialists today (8 phase1)
- [Source: src/sdlc/agents/phase1/*.md] — the 8 placeholder stubs (verbatim "(Phase 1 placeholder)" / "Replaced by Story 2B.8") + `01-Requirement/...` write_globs
- [Source: src/sdlc/specialists/] — Story 2A.2 registry/manifest/frontmatter validators (`load_registry`, `validate_workflow_refs`, `validate_internal_links`)
- [Source: scripts/validate_specialists.py] — v0.2 PLACEHOLDER (exit 0; CLI entry-point deferred per deferred-work.md:315) — NOT a trustworthy gate
- [Source: scripts/check_boundary_line_presence.py] — 2B.5 check scans `dispatcher/prompts.py` builders, NOT agent `.md` files
- [Source: tests/integration/test_abstraction_adequacy.py] — 2B.3 conformance harness (Mock+stub-Claude, byte-identity, golden-regen discipline)
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml] — `2b-8-author-phase-1-specialists: backlog`; `2b-3-...: done`; 2B.6 Phase-1-prompt-hash fixture-invalidation note; full-suite baseline 2825 passed
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — 2A.2 AC7 D3 (validate_specialists CLI deferred, line 315); CR2B4-W4 EPIC-2B-DEBT-SPECIALIST-BODY-BOUNDARY-NORMALIZE
- [Source: CONTRIBUTING.md] — §1 quality gate, §2 TDD-first, §3 worktree/rebase/first-merger-owns-shared-edits, §5 decision protocol
- [Source: pyproject.toml] — `--cov-fail-under=87`; `EPIC-2B-DEBT-COVERAGE-90-FLOOR` tracks the CONTRIBUTING ≥90 gap

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (1M context) — claude-opus-4-8[1m]

### Debug Log References

- **D2 architectural correction**: Initial implementation included `BOUNDARY_LINE` in all specialist bodies per D2=(b) recommendation. Full suite run revealed `phase1_prompt_builder` (prompts.py:241) actively rejects bodies containing `BOUNDARY_LINE` — builder injects it automatically into compiled prompt. Corrected D2→(a); stripped BOUNDARY_LINE from all 15 bodies; updated anti-tautology test from "body must contain" to "body must NOT contain" BOUNDARY_LINE. CR2B4-W4 remains open for a future gate verifying the compiled prompt, not the body.
- **Wheel allowlist**: `test_wheel_does_not_ship_content_files` failed because 7 new `.md` files were not in `_ALLOWED_CONTENT_FILES`. Added all 7 net-new specialists to the allowlist with `# Story 2B.8` comment.
- **No fixture drift**: abstraction-adequacy fixture uses a static `"abstraction-adequacy seed prompt"` hash independent of specialist body text; 3/3 conformance tests passed without regeneration.

### Completion Notes List

- ✅ **AC1**: 8 existing Phase-1 placeholder stubs replaced with production-quality system prompts (role, responsibilities, output contract). No placeholder markers remain (verified by automated test).
- ✅ **AC2**: 7 net-new Phase-1 specialists authored: `requirement-analyst`, `market-researcher`, `stakeholder-simulator`, `dependency-mapper`, `prioritizer`, `acceptance-criteria-author`, `story-prioritizer`. Each carries full frontmatter + production body.
- ✅ **AC3**: All 7 net-new specialists validate against `SpecialistFrontmatter`; `index.yaml` updated with 7 new entries; `load_registry()` loads 26 specialists (15 Phase-1) with zero errors.
- ✅ **AC4**: BOUNDARY_LINE injected automatically by `phase1_prompt_builder` for every Phase-1 compiled prompt. Bodies correctly do NOT contain BOUNDARY_LINE (builder rejects them if they do). D2=(a) is architecturally correct.
- ✅ **AC5**: Conformance harness 3/3 pass; zero fixture drift from re-authored bodies.
- ✅ **AC6**: Anti-tautology receipts: positive (7 tests confirming new specialists load + correct phase + schema_version), boundary invariant (no body contains BOUNDARY_LINE), placeholder-clean, 2 negative receipts (icon-too-long + missing-description — validator can reject).
- ✅ **Wheel**: 7 new `.md` files added to `_ALLOWED_CONTENT_FILES` allowlist.
- ✅ **Matrix**: `docs/specialists-matrix.md` §1 updated (19→26), §3 Phase-1 planned section removed, §4 totals corrected.
- ✅ **Quality gate**: 2832 passed / 0 failed / 87.28% coverage / all 19 pre-commit hooks / mkdocs strict / wireformat 5/5.

### File List

**New files:**
- `src/sdlc/agents/phase1/requirement-analyst.md`
- `src/sdlc/agents/phase1/market-researcher.md`
- `src/sdlc/agents/phase1/stakeholder-simulator.md`
- `src/sdlc/agents/phase1/dependency-mapper.md`
- `src/sdlc/agents/phase1/prioritizer.md`
- `src/sdlc/agents/phase1/acceptance-criteria-author.md`
- `src/sdlc/agents/phase1/story-prioritizer.md`
- `tests/unit/specialists/test_phase1_2b8_authoring.py`
- `tests/fixtures/specialists/markdown/icon-too-long.md`
- `tests/fixtures/specialists/markdown/missing-description.md`

**Modified files:**
- `src/sdlc/agents/phase1/product-strategist.md` (stub → production)
- `src/sdlc/agents/phase1/technical-researcher.md` (stub → production)
- `src/sdlc/agents/phase1/devil-advocate.md` (stub → production)
- `src/sdlc/agents/phase1/requirement-synthesizer.md` (stub → production)
- `src/sdlc/agents/phase1/artifact-verifier.md` (stub → production)
- `src/sdlc/agents/phase1/epic-generator.md` (stub → production)
- `src/sdlc/agents/phase1/story-writer.md` (stub → production)
- `src/sdlc/agents/phase1/phase1-signoff-summarizer.md` (stub → production)
- `src/sdlc/agents/index.yaml` (7 new phase1 entries appended)
- `docs/specialists-matrix.md` (§1 19→26, §3 Phase-1 planned removed, §4 totals updated)
- `tests/integration/test_wheel_build.py` (7 new entries in `_ALLOWED_CONTENT_FILES`)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (2b-8 → review)

## Change Log

| Date | Version | Description | Author |
|---|---|---|---|
| 2026-05-29 | 0.1 | Story contextualized to ready-for-dev via bmad-create-story | create-story |
| 2026-05-30 | 1.0 | Story implemented: 8 stubs re-authored + 7 net-new Phase-1 specialists; AC6 anti-tautology receipts; wheel allowlist; matrix reconciled; all ACs green; 2832 passed 0 failed | dev-story |
| 2026-06-01 | 1.1 | bmad-code-review (3 adversarial layers: Blind Hunter / Edge Case Hunter / Acceptance Auditor). 2 decision-needed, 1 patch, 1 defer, 12 dismissed. Edge Case Hunter ran the full registry/conformance/wheel suite live and verified clean; most diff-only suspicions disproven. | code-review |

## Review Findings (bmad-code-review 2026-06-01)

> 3 adversarial layers run in parallel (Blind Hunter = diff-only; Edge Case Hunter = diff + live project verification; Acceptance Auditor = diff + spec + context). Edge Case Hunter ran `load_registry()` (26 specialists / 15 phase-1, zero errors), the negative-fixture rejections, conformance harness, wheel allowlist, and `tests/unit/specialists/` (241 passed) live — these results downgraded most Blind-Hunter diff-only suspicions to dismissed. AC1–AC5 + D1–D5 independently verified PASS by the Acceptance Auditor; scope boundaries (frozen `specialist_frontmatter.py`, wire-format snapshots 5/5, phase2/3 files) untouched.

### Decision-needed (resolve before patches)

- [x] [Review][Decision → RESOLVED 1(a), applied as patch] **Requirement Synthesizer does not consume the new Phase-1 analysis specialists** — `requirement-analyst.md:36-37` states its `02-ANALYSIS.md` output "is consumed by the Requirement Synthesizer", but `requirement-synthesizer.md:17-18` lists only Product Strategist / Technical Researcher / Devil Advocate as inputs (omits Requirement Analyst, Market Researcher `03-MARKET.md`, Stakeholder Simulator). Internal contradiction introduced by this same changeset. Note: the 7 net-new specialists are not yet wired into any workflow YAML (dispatch composition is a later integration concern), so the resolution depends on how much cross-wiring to encode in prompt bodies now. [src/sdlc/agents/phase1/requirement-synthesizer.md:17-18]
- [x] [Review][Decision → RESOLVED 2(a)] **AC6 RED-before-GREEN ordering not provable from git** — the entire story is uncommitted (working tree only), so `git log --reverse -- tests/unit/specialists/test_phase1_2b8_authoring.py` shows no tests-first ordering. The tests pass and both negative receipts genuinely reject (validator can fail), but CONTRIBUTING §2 / AC6 require the TDD ordering to be git-visible. [tests/unit/specialists/test_phase1_2b8_authoring.py]

### Patch

- [x] [Review][Patch → APPLIED] **Output-contract template uses non-nestable triple-backtick fences** — the AC author's emitted template wraps ```` ```gherkin ```` blocks inside a 3-backtick outer fence; the bare ```` ``` ```` (line 55) prematurely closes the outer fence and the ```` ``` ```` (line 74) opens a dangling block, so the example the specialist is told to emit is malformed Markdown. Fix: make the outer template fence four backticks (````` ```` `````) so the inner 3-backtick gherkin blocks nest. Zero fixture-drift risk (net-new specialist, not dispatched in any fixture). [src/sdlc/agents/phase1/acceptance-criteria-author.md:44-74]

### Defer

- [x] [Review][Defer] **Placeholder-marker test swallows `SpecialistError`** — `test_no_phase1_body_contains_placeholder_marker` does `except SpecialistError: continue`, so a re-authored *legacy* stub that failed to load would be silently skipped, and the positive-receipt test covers only the 7 net-new names (not the 8 legacy). Low risk because the global `load_registry()` in the conformance suite fails loudly on any broken specialist. [tests/unit/specialists/test_phase1_2b8_authoring.py] — deferred, low-risk test hardening

### Dismissed (12 — diff-only suspicions disproven by live verification)

1. "signoff-summarizer placeholder-marker is dead/self-defeating" — markers correctly match **nothing** (the green success state); test fails if any marker reappears. Non-vacuous.
2. "matrix planned count unverifiable" — independently reconciled: §1=26, §3=11 (Phase2 6 + Phase3 4 + Support 1), §4 total 37.
3. "`read_globs: []` contradicts bodies that read upstream" — `read_globs` is declared-only in `specialist_frontmatter.py:20`, **not enforced** in `src/sdlc/`; HEAD stubs already shipped `read_globs: []`. Pre-existing advisory metadata.
4. "`write_globs: []` contradicts promised output" — resolved by D3 (analysis/adversarial/routing roles write nothing; output flows via `AgentResult.output_text`).
5. "icon-too-long fixture is ASCII not emoji" — Edge Case Hunter verified pydantic counts code points; all 15 production icons ≤2 cp (incl. 🗺️/✍️); a 7-cp ZWJ emoji is rejected. Negative receipt valid as-is.
6. "tautological `schema_version` test" — harmless documentation assertion; overall anti-tautology satisfied by load-bearing positive + negative receipts.
7. "rotting `prompts.py:241` line citations in test docstrings" — currently correct; docstring nit only.
8. "synthesizer icon 📋→🔗 unexplained" — cosmetic; 🔗 fits the integrator role; validates fine.
9. "prioritizer formula example weak" — Blind Hunter itself confirmed the math is correct (3.33).
10. "new artifact paths (02-ANALYSIS/03-MARKET/06-AC) not in wheel allowlist" — these are runtime output artifacts, not packaged source files; allowlist correctly covers only the 7 specialist `.md`.
11. "literal word `placeholder` in artifact-verifier.md:34" — legitimate domain content (the verifier *detects* placeholder content), not a stub marker.
12. "redundant overlapping marker pair" — `placeholder until Story` ⊂ `Placeholder until Story 2B` under case-insensitive match; harmless.

### Resolution (2026-06-01)

- **Decision 1 → 1(a) minimal reconcile [APPLIED as patch]:** `requirement-synthesizer.md` Role + Responsibility-1 updated to consume the Requirement Analyst's `02-ANALYSIS.md` (classified requirements / ambiguities / missing-info; the analyst's `FR-draft-N` IDs are renumbered and finalised by the synthesizer). Market-researcher (`03-MARKET.md`) / stakeholder-simulator cross-wiring deferred to the dispatch-integration story (these specialists are not yet wired into any workflow YAML).
- **Decision 2 → 2(a) [APPLIED]:** RED-before-GREEN reconstructed in git on branch `epic-2b/2b-8-phase1-specialists` — the AC6 test + 2 negative fixtures committed first (RED), implementation + docs committed second (GREEN); ordering visible in `git log --reverse`.
- **Patch A [APPLIED]:** `acceptance-criteria-author.md` output-contract outer fence changed to four backticks so the inner ` ```gherkin ` blocks nest correctly.
- **Verification:** `tests/unit/specialists` + `tests/unit/dispatcher` + `tests/integration/test_abstraction_adequacy.py` → **244 passed**; AC6 receipts (`test_phase1_2b8_authoring.py`) **7/7**; registry loads **26 / 15 phase-1**; no `BOUNDARY_LINE` or placeholder marker introduced by the patches.
