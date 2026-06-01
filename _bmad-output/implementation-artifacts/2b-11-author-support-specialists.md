# Story 2B.11: Author Support Specialists

**Status:** review

**Epic:** 2B — Real Claude Dispatch + Safety Boundary (**FIRST EXTERNAL SHIP**)
**Layer:** 4 — the epic capstone (`docs/sprints/epic-2b-dag.md` §3)
**Worktree:** `epic-2b/2b-11-support-specialists` (owner: Elena, DAG §5)
**Critical path:** 2B.1 → 2B.3 → 2B.10 → **2B.11** (`docs/sprints/epic-2b-dag.md` §4 — terminal node)
**Depends on:** 2B.8 ✅ + 2B.9 + 2B.10 + 2B.3 ✅ (DAG §3, Layer 4)

---

## 🚧 BLOCKING PREREQUISITE — read before `dev-story`

> **2B.9 and 2B.10 are marked `done` in sprint-status but their specialist authoring is NOT on `main`.**
> It lives on un-merged worktrees `wt-2b-9` (`epic-2b/2b-9-phase2-specialists`, HEAD `53d5be0`) and
> `wt-2b-10` (`epic-2b/2b-10-phase3-specialists`, HEAD `46d3f32`). On `main`, `src/sdlc/agents/index.yaml`
> still has **26** specialists; neither worktree is rebased on the other (`merge-base = e5c72a0`, the 2B.8 tip).
>
> 2B.11's entire value (count gate, matrix regen, full-roster ship signal) requires the **complete** roster.
> Per CONTRIBUTING §3 (worktree-per-story, linear merge, rebase between merges) the required order is:
> **merge 2B.9 → rebase 2B.10 on new `main` → merge 2B.10 → branch `2b-11` from that `main`.**
> `index.yaml` and `tests/integration/test_wheel_build.py::_ALLOWED_CONTENT_FILES` are **guaranteed textual
> conflicts** between 2B.9/2B.10 (same insertion anchors) and must be hand-resolved into one unified roster.
> **Do not begin 2B.11 implementation until `git -C <main> grep -c '  - name:' src/sdlc/agents/index.yaml`
> returns 36.** This is AC1.

---

## Story

As an **engineer completing the ~25-specialist suite for the first external ship**,
I want **the cross-cutting support specialists authored (the genuinely missing orchestration/recovery/triage roles), the full roster reconciled against the canonical matrix with a real count gate + workflow-reference gate, and the 2B.3 conformance test re-run as the ship signal**,
so that **every FR28 support role is staffed, the specialist suite is internally consistent (registry ⟷ matrix ⟷ workflows), and green CI on the conformance test certifies v0.x is ready to ship**.

---

## Acceptance Criteria

> **Scope note — read first.** The epic AC (`epics.md:1716-1743`) lists 6 support files under a
> `package_data/agents/support/` path. Verified ground truth corrects this in three ways, resolved by
> **D1/D2** in "Decisions Needed":
> 1. The shipped layout is `src/sdlc/agents/` (no `package_data/` prefix); there is **no `support/` dir yet**.
> 2. **`devil-advocate` already ships** at `phase1/devil-advocate.md` (registered phase 1) — re-authoring it
>    under the same `name` is a **duplicate-name registry rejection** (`registry.py:72-83`), not a no-op.
> 3. **`synthesizer`** is already reconciled to `requirement-synthesizer` (matrix §2) and generic synthesis
>    is a per-workflow `synthesizer_agent` field (`contracts/workflow_spec.py:21`), **not** a dispatched
>    specialist — no workflow references a bare `synthesizer`. **`signoff-summarizer`** is staffed by the
>    shipped `phase1-signoff-summarizer`. So only **3** of the 6 named roles are genuinely net-new:
>    `clarification-triager`, `agent-failure-recovery`, `orchestrator-helper`. The "~6 markdowns" DAG estimate
>    counted the 3 already-shipped names as net-new; **actual net-new = 3** (D1).

1. **Prerequisite roster present (BLOCKING).** Before any 2B.11 work: 2B.9 + 2B.10 are merged to `main` (linear, rebased per CONTRIBUTING §3); `index.yaml` on `main` lists exactly **36** specialists (15 Phase-1 + 12 Phase-2 + 9 Phase-3) and `load_registry(Path("src/sdlc/agents"))` succeeds with no orphan/duplicate error. (See Blocking Prerequisite above.)

2. **Support specialists authored (per D1, per D2 location).** The genuinely net-new support markdowns exist with valid frontmatter matching the EXACT shipped 9-key schema (Dev Notes → "Frontmatter schema"):
   - `src/sdlc/agents/support/clarification-triager.md` — routes open-clarification STOP triggers to the right specialist (Epic 4 consumer; matrix §3 Support-planned, deferred from 2B.8).
   - `src/sdlc/agents/support/agent-failure-recovery.md` — retry/recovery role for the dispatcher retry policy (`src/sdlc/dispatcher/retry.py`, Story 2A.3).
   - `src/sdlc/agents/support/orchestrator-helper.md` — complex multi-step workflow consolidation.
   Each is `model: sonnet`, `tools: []`, declares no network/destructive capability, and is a **registered-but-not-dispatched-in-v1** specialist (no caller until Epic 4 / dispatcher wiring — this is acceptable per the matrix's existing `phase1-signoff-summarizer` "registered, not dispatched v1" precedent).

3. **Already-staffed roles NOT re-authored.** No new file is created for `devil-advocate` (shipped `phase1/devil-advocate.md`), `synthesizer` (shipped `requirement-synthesizer` + dispatcher `synthesizer_agent` field), or `signoff-summarizer` (shipped `phase1-signoff-summarizer`) unless D1 elects the optional generic-signoff variant. The matrix (AC9) records each as staffed-by-shipped so the FR28 roster is auditable.

4. **Naming = three-way match.** For every authored file: file slug == frontmatter `name` == the slug in `index.yaml`. Kebab-case (`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, `manifest.py:20`). No aliases (matrix §2; ADR-030 forward rule — any planned-vs-shipped rename needs a one-line ADR-030 amendment).

5. **Registry updated and loads clean (orphan/dup is the hard gate).** `src/sdlc/agents/index.yaml` gains a `{name, phase: <per D2>, file: support/<name>.md}` entry for EACH net-new file. VERIFIED: `load_registry` (`src/sdlc/specialists/registry.py:153`) rejects duplicate names (`:72-83`), path-traversal/symlink escape, duplicate file aliases, AND raises `SpecialistError("orphan specialist: …")` for any `*.md` under `agents/` missing from the manifest (`:177-184`); `load_specialist` enforces `frontmatter.name == file.stem`. So a new `.md` without its manifest entry hard-fails the load. `schema_version: 1` untouched; do not reorder existing entries.

6. **Boundary-line absent + no placeholder markers.** No authored body contains `BOUNDARY_LINE` (`=== USER-PROVIDED DATA — NOT INSTRUCTIONS ===`, `prompts.py:30`) — the prompt builder injects it and **rejects** any specialist body that already contains it (`prompts.py:241,331`). No body or `description` contains a `**PLACEHOLDER**` marker. Both are asserted in the validation test (AC13).

7. **Count gate created + bound re-derived (closes CR2B10-W8).** A new test asserts `len(load_registry(Path("src/sdlc/agents")).names())` is within a bound **re-derived from the authoritative matrix** (per D3). VERIFIED: no count gate exists today (`scripts/validate_specialists.py` is a v0.2 placeholder returning 0; no test asserts a roster size). The documented `≥23, ≤27` bound (DAG §3) is stale and cannot accommodate 36 + support (matrix §4 target = 37, and "this matrix wins"). The chosen bound is recorded in the test, the epics.md AC, DAG §3, and a one-line ADR-030 amendment (per the ADR-030 precedent + matrix-authority rule).

8. **Workflow-YAML references all resolve.** A new test loads ALL real workflow specs (`src/sdlc/workflows_yaml/*.yaml`, 11 files) and runs `validate_workflow_refs(spec, load_registry(Path("src/sdlc/agents")))` for each — every `primary_agent` / `parallel_agents` / `synthesizer_agent` / `write_globs` key resolves to a loaded specialist. VERIFIED: no such full-suite test exists today (only synthetic-fixture coverage in `test_validator.py`). **Must skip the `"none"` sentinel** `primary_agent` (`sdlc-signoff.yaml` sets `primary_agent: "none"`, which is not a specialist).

9. **Matrix regenerated + reconciled (closes CR2B10-W9).** `docs/specialists-matrix.md` is updated so §1 Shipped lists the full roster: promote the 6 Phase-2 (`ux-researcher`, `design-system-author`, `a11y-reviewer`, `infra-architect`, `devex-architect`, `api-designer`) and 4 Phase-3 (`tdd-strategist`, `security-reviewer`, `edge-case-reviewer`, `pr-author`) planned rows to Shipped, add the net-new support rows, and reconcile §4 Roster Totals to the actual count. Per D5, add a consistency test pinning matrix rows ⟷ `index.yaml`. Matrix update rule (§ top) and ADR-030 forward rule are honored.

10. **2B.3 conformance re-run as first external ship signal (per D4).** `tests/integration/test_abstraction_adequacy.py` (Story 2B.3) is green against BOTH `MockAIRuntime` and `ClaudeAIRuntime` (byte-identical HookPayload sequence + `state.json` via `test_cross_runtime_byte_identity`) with the full roster registered. The story documents that the wired gate is fixture-scoped (seed fixture `tests/fixtures/mock_responses/abstraction-adequacy.yaml`, roster-independent) and that the deeper "drives the whole specialist suite" reading is gated by carried coupling debt (`EPIC-2B-DEBT-CLAUDE-TOOL-CALLS`, `EPIC-2B-DEBT-CHAIN-EMISSION-CAPTURE`). Green CI on this test = ready for v0.x.

11. **Wheel packaging stays correct.** Each net-new support `.md` is added to `_ALLOWED_CONTENT_FILES` in `tests/integration/test_wheel_build.py` (a guard asserts every allowlist entry exists in-source, so paths must be exact). VERIFIED: the `agents/` tree is force-included (`pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]` `"src/sdlc/agents" = "sdlc/agents"`), so a new `support/` subdir is auto-packaged — **no `pyproject.toml` change needed**. `test_wheel_does_not_ship_content_files` stays green.

12. **Tool-safety gates stay green (no regression).** `scripts/check_no_outbound_http.py` and `scripts/check_subprocess_allowlist.py` stay green: support specialists are markdown-only, declare `tools: []`, add no `subprocess`/network callsite to `src/`, and instruct no destructive shell op. `src/sdlc/dispatcher/safety.py` destructive-op detection is unaffected. The 2B.5 boundary-line presence gate (`scripts/check_boundary_line_presence.py`) is unaffected — it scans `*_prompt_builder` functions in `dispatcher/prompts.py`, not agent `.md` files; this story adds no such function.

13. **Quality gate + process discipline.** Quality gate green per CONTRIBUTING §1 (ruff format/check, `mypy --strict src/`, `pytest`, coverage ≥ the enforced floor, pre-commit, `mkdocs build --strict`, `freeze_wireformat_snapshots.py --check`). No wire-format contract is touched (ADR-024 snapshot count unchanged; `SpecialistFrontmatter` + manifest schema reused as-is). TDD-first (§2): the registry-loads + naming + boundary-absence + count-gate validation test is the **failing-first commit** (RED until files + manifest entries exist), visible in `git log --reverse`. Chunked review-A → review-B → review-C (§4). Decisions surfaced as D1–D5 option-labels (§5).

---

## Tasks / Subtasks

> **TDD-first ordering (§2):** the **validation test is the failing-first commit**. Author/commit
> `tests/unit/specialists/test_support_2b11_authoring.py` (registry-loads-with-support-slugs +
> three-way-name-match + boundary-absence + count-gate band) and the workflow-ref test BEFORE any
> prompt body. They go RED until the files + `index.yaml` entries exist. Mirror
> `tests/unit/specialists/test_phase1_2b8_authoring.py` exactly.

- [x] **T0 — (AC1, blocking) Confirm the prerequisite roster.** Verify 2B.9 + 2B.10 are merged to `main` (rebased, linear) and `grep -c '  - name:' src/sdlc/agents/index.yaml` == 36. If not, **HALT** and merge them first (DAG §6 order; resolve the `index.yaml` + `_ALLOWED_CONTENT_FILES` conflicts into one unified roster). Do not proceed under "I'll reconcile later".
- [x] **T0 — (AC2-AC4, AC7, AC10, AC9, §5) Lock decisions D1–D5** (see "Decisions Needed"): D1 support scope, D2 location/phase, D3 count-gate bound, D4 ship-signal interpretation, D5 matrix-regen mechanism. Record chosen labels in Completion Notes.
- [x] **(AC13, §2) Write the failing validation test FIRST, commit before any prompt body:**
  - `load_registry(_AGENTS).names()` ⊇ the net-new support slug set (RED until both the `.md` files and their `index.yaml` entries exist);
  - each net-new `reg.get(name).phase == <D2 value>`; aggregate violations (report-all — do NOT abort on first offender; mirror the CR2B9-P1 fix);
  - three-way name match (file stem == frontmatter `name` == `index.yaml` slug);
  - `schema_version == 1`; no body contains `BOUNDARY_LINE`; no body/description contains a placeholder marker (harden the `except SpecialistError: continue` silent-skip per CR2B8-W1/CR2B9-W1 — append a violation instead);
  - reuse negative fixtures `tests/fixtures/specialists/markdown/{icon-too-long.md, missing-description.md}` as anti-tautology receipts. Verify RED.
- [x] **(AC7, §2) Count gate (RED first).** Add `test_specialist_roster_count_within_bound` asserting `LOW <= len(load_registry(Path("src/sdlc/agents")).names())) <= HIGH` with the D3-derived bound. RED until the support files land.
- [x] **(AC8, §2) Workflow-ref gate (RED/GREEN).** Add `test_all_workflow_yaml_specialist_refs_resolve` looping `WorkflowRegistry.load(Path("src/sdlc/workflows_yaml"))` × `validate_workflow_refs(spec, registry)`; skip the `"none"` sentinel primary_agent. (May be GREEN immediately if all existing refs already resolve — it's a standing regression gate.)
- [x] **(AC2, AC4, AC6, per D1/D2) NEW** Author `support/clarification-triager.md`, `support/agent-failure-recovery.md`, `support/orchestrator-helper.md` (+ optional generic `signoff-summarizer.md` if D1=(b)) — shipped 9-key frontmatter; `tools: []`; production prompt body (role, I/O contract, rubric, edge cases); NO boundary line in body.
- [x] **(AC5) UPDATE** `src/sdlc/agents/index.yaml` — append `{name, phase: <D2>, file: support/<name>.md}` per net-new file. `schema_version: 1` untouched; do not reorder.
- [x] **(AC9, closes CR2B10-W9) UPDATE** `docs/specialists-matrix.md` — promote the 10 Phase-2/Phase-3 planned rows → §1 Shipped; add net-new support rows; mark `devil-advocate`/`synthesizer`/`signoff-summarizer` as staffed-by-shipped; reconcile §4 totals to the actual count. Add the D5 consistency test.
- [x] **(AC7, closes CR2B10-W8) UPDATE** `_bmad-output/planning-artifacts/epics.md` (2B.11 count AC), `docs/sprints/epic-2b-dag.md` §3, and add a one-line ADR-030 amendment recording the re-derived count bound.
- [x] **(AC11) UPDATE** `tests/integration/test_wheel_build.py` `_ALLOWED_CONTENT_FILES` — add `Path("sdlc/agents/support/<name>.md").as_posix()` per net-new file under a `# Story 2B.11 — support specialists` comment. Run `test_wheel_does_not_ship_content_files`; confirm green.
- [x] **(AC12)** Run `scripts/check_no_outbound_http.py` + `scripts/check_subprocess_allowlist.py` + `scripts/check_boundary_line_presence.py` + `tests/security/test_boundary_line_presence.py`; confirm all still green (no regression — gates scan code, not the markdown).
- [x] **(AC10, per D4)** Run `tests/integration/test_abstraction_adequacy.py` end-to-end (mock + claude); confirm `test_cross_runtime_byte_identity` green with full roster. Document the fixture-scoped reality + carried coupling debt.
- [x] **(AC13, §1)** Full quality gate to green. Regenerate Mock fixtures ONLY via the documented ceremony with a justifying diff if a prompt-hash shift invalidates any (the abstraction-adequacy seed uses a static hash independent of body text — expect 0 drift, but verify).
- [x] **(§3 rebase)** 2B.11 is the LAST `index.yaml` / matrix / wheel-allowlist writer — rebase onto the merged 2B.9+2B.10 `main` before merge; never merge-commit the shared files.
- [ ] **(§4 chunked review)** review-A (correctness/scope) → review-B (registry/count-gate/workflow-ref) → review-C (matrix reconciliation + naming three-way + roster total); no skipping.

---

## Dev Notes

### Architecture context — support specialists and FR28

Support specialists are cross-cutting markdown prompt roles used across phases (orchestration consolidation, panel members, signoff summaries, recovery/triage). FR28 (`prd.md:774`, `epics.md:57`) targets "approximately 25 specialist agents … covering Phase 1, Phase 2, Phase 3, and support roles (orchestrator, synthesizer, devil-advocate, clarification-triager, signoff-summarizer)". 2B.11 is "FR28 complete" — it staffs the remaining support roles and reconciles the whole roster. Of the 5 FR28-named support roles, **3 are already staffed by shipped specialists** (`synthesizer`→`requirement-synthesizer`; `devil-advocate`→`phase1/devil-advocate.md`; `signoff-summarizer`→`phase1-signoff-summarizer`), so the genuine authoring work is the orchestration/recovery/triage roles.

### CRITICAL: support roles already staffed (do NOT re-author — verified)

| Epic-named role | Reality | Action |
|---|---|---|
| `devil-advocate` | Shipped `phase1/devil-advocate.md`, registered phase 1 (matrix §1). | **SKIP** — a 2nd file under `name: devil-advocate` is a **duplicate-name registry rejection** (`registry.py:72-83`, fires before file I/O). |
| `synthesizer` (generic) | Reconciled to `requirement-synthesizer` (matrix §2). Generic synthesis is a per-workflow `synthesizer_agent` field (`workflow_spec.py:21`); only `sdlc-start.yaml` sets it (`requirement-synthesizer`), all 10 others `null`. No workflow references a bare `synthesizer`. | **SKIP** — re-authoring = orphan with no caller; matrix already reconciled the rename. |
| `signoff-summarizer` (generic) | Shipped `phase1-signoff-summarizer` (registered, not dispatched v1; matrix §2 rename row). No caller for a generic variant. | **SKIP** (default) or author as optional generic per D1=(b). |
| `clarification-triager` | No file. Matrix §3 Support-planned (target 2B.8, deferred per 2B.8 D1=(a)). Consumer is the Epic-4 clarification STOP trigger (Epic 4 = backlog → no caller yet). | **NEW** (no-caller-in-v1). |
| `agent-failure-recovery` | No file. Retry policy `dispatcher/retry.py` (2A.3) is generic `with_retries(...)`, dispatches no named recovery specialist. | **NEW** (no-caller-in-v1). |
| `orchestrator-helper` (was FR28 `orchestrator`) | No file. Zero references in src/tests/workflows. | **NEW** (no-caller-in-v1). |

"Registered-but-not-dispatched-in-v1" is an accepted pattern (matrix §1 marks `phase1-signoff-summarizer` exactly this way). These specialists ship for FR28 completeness; their dispatch wiring is Epic 4 / a dispatch-integration story.

### Roster arithmetic (the count-gate reconciliation — closes CR2B10-W8)

```
main (current):                26   (15 P1 + 6 P2 + 5 P3)
+ 2B.9 net-new Phase-2:       + 6   (ux-researcher, design-system-author, a11y-reviewer,
                                     infra-architect, devex-architect, api-designer)
+ 2B.10 net-new Phase-3:      + 4   (tdd-strategist, security-reviewer, edge-case-reviewer, pr-author)
= pre-2B.11 (after merges):    36   (15 P1 + 12 P2 + 9 P3)   ← AC1 verifies this on main
+ 2B.11 net-new support:      + 3   (clarification-triager, agent-failure-recovery, orchestrator-helper)
= FINAL ROSTER:                39   (40 if D1=(b) adds generic signoff-summarizer)
```

The documented gate (`≥23, ≤27` / "25-count", DAG §3) is **stale and internally inconsistent** (the same DAG also says "25-count gate"). It was written against PRD §214's original "~25" v0.1 plan. The roster grew via Epic-2A sub-tracks, pair-reviewers, the 7 Phase-1 net-new (2B.8), and the support roles. Matrix §4 already declares itself "the authoritative count" (target 37 — but that 37 assumed only 1 support add; the real support count is 3). **2B.11 re-derives the bound from the actual matrix-reconciled roster** (D3) and amends the AC/DAG + a one-line ADR-030 amendment. ADR-030 governs roster reconciliation (matrix-first, shipped-name-wins) and backstops this via its "matrix wins / deviations require an ADR amendment" rule, though the numeric bound itself lives in the DAG/epics-AC, not ADR-030.

### Frontmatter schema (VERIFIED against the net-new 2B.8/2B.9/2B.10 files — use this EXACT 9-key shape)

```yaml
---
schema_version: 1
name: <file-slug>            # == file slug == index.yaml slug (three-way match), kebab-case
title: "Human Title"
icon: "🧭"                   # 1-4 chars (emoji ok)
model: sonnet                # every net-new specialist uses sonnet
tools: []                    # empty — support roles declare NO Bash/network/destructive tool
read_globs:
  - "<glob>"                 # scope to what the role observes (e.g. clarification JSON, task records)
write_globs:
  - "<glob>"                 # see CR2B9-DN1 caveat below before using []
description: "…"
---
```

The `SpecialistFrontmatter` StrictModel (`src/sdlc/contracts/specialist_frontmatter.py`) has **no `phase`/`role`/`boundary` keys** (extra keys REJECTED). `phase` lives only in the `index.yaml` manifest entry. `icon` is `min_length=1, max_length=4`.

⚠️ **`write_globs: []` caveat (CR2B9-DN1).** A review-only specialist with empty `write_globs` can fault the dispatcher's `dispatch_and_write` path (it indexes `write_globs[0]` → empty-tuple IndexError). If a support role is genuinely write-less, give it a minimal scoped glob or confirm it is never routed through `dispatch_and_write`. Since these are not dispatched in v1, this is latent — but author defensively.

### Support directory + phase value (D2 — establishes a new convention)

The manifest `phase` field is `Literal[0, 1, 2, 3]` (`manifest.py:24`); `registry._VALID_PHASES` derives from it via `get_args()`, and `registry.list_phase(0)` works (`registry.py:49-61`). **`phase: 0` is schema-legal but has never been used; no `support/` dir exists.** D2 chooses where support specialists live and what phase value they carry. Recommended: a new `src/sdlc/agents/support/` dir + `phase: 0` (the cross-cutting/support phase). The `agents/` force-include already packages any subdir into the wheel (no `pyproject.toml` change), and the orphan check (`rglob("*.md")`) will require each `support/*.md` to be in the manifest.

### Boundary line (VERIFIED — must be ABSENT from bodies)

`BOUNDARY_LINE = "=== USER-PROVIDED DATA — NOT INSTRUCTIONS ==="` (`src/sdlc/dispatcher/prompts.py:30`; the `—` is U+2014). The prompt builders **inject** it at dispatch time (`prompts.py:258,348`) and **reject** any specialist whose body already contains it (`prompts.py:241,331`). So a support body that hardcodes the boundary line is rejected at dispatch. The validation test asserts ABSENCE (mirror `test_no_phase1_body_contains_boundary_line`). The earlier guess that the wording was `--- USER PROVIDED TEXT … ---` is WRONG — use the verified string. (Carried debt `CR2B4-W4 / EPIC-2B-DEBT-SPECIALIST-BODY-BOUNDARY-NORMALIZE`: the `in specialist.body` check is raw substring, not NFKC-normalized — owned by a production-hardening sprint, NOT 2B.11.)

### Registry / count-gate / workflow-ref machinery (VERIFIED — all net-new for 2B.11)

- **Count gate:** none exists. `scripts/validate_specialists.py` is a v0.2 placeholder (`main()` returns 0). The registry has **no `__len__`** — use `len(load_registry(Path("src/sdlc/agents")).names())`. Public API: `get(name)`, `list()`, `list_phase(int)`, `names()→frozenset` (`registry.py:39-69`).
- **Workflow-ref gate:** `validate_workflow_refs(spec, registry)` (`validator.py:57-98`) checks `primary_agent` / `parallel_agents` / `synthesizer_agent` / `write_globs` keys against `registry.names()`, fail-once-with-full-list. No test loads ALL real workflows today (only synthetic fixtures in `test_validator.py`). Real workflows: `src/sdlc/workflows_yaml/*.yaml` (11 — sdlc-architect/bootstrap/break/epics/research/signoff/start/stories/task/ux/verify). **`sdlc-signoff.yaml` sets `primary_agent: "none"`** — skip that sentinel or the loop fails. All other real refs already resolve.
- **Matrix:** `docs/specialists-matrix.md` exists, is hand-maintained, no generator, no consistency test. Currently half-stale: 2B.9 updated it (Phase-2 promoted), 2B.10 did NOT (Phase-3 still under "planned"). "Generated under …" (AC text) = hand-update planned→shipped + (D5) a consistency test pinning rows ⟷ `index.yaml`; optionally a small generator + `--check` (also discharges the CR2B10-W2 triple-maintenance hazard).

### Conformance ship signal (Story 2B.3 — VERIFIED, with an honest caveat)

`tests/integration/test_abstraction_adequacy.py` parametrizes `_RUNTIME_FACTORIES = [_mock_factory, _claude_factory]`, runs the deterministic pipeline, and asserts byte-identical HookPayload sequence + final `state.json` per runtime (vs golden) and cross-runtime (`test_cross_runtime_byte_identity`, ordered last via `conftest.py`). It is driven by the **seed** fixture `tests/fixtures/mock_responses/abstraction-adequacy.yaml` — **not** a "greenfield-walkthrough" fixture; the epic's wording is aspirational. The gate is **fixture-scoped and roster-independent** (it does not iterate the registered specialists). The Claude path is coincidence-coupled (Claude v1 parses stdout only → `tool_calls` empty → seed-path fallback; `EPIC-2B-DEBT-CLAUDE-TOOL-CALLS`) and hook payloads are synthesized as chain input not emission (`EPIC-2B-DEBT-CHAIN-EMISSION-CAPTURE`). **D4** resolves whether the ship-signal AC is (a) re-use the existing test green with the full roster registered (honest given the wiring; recommended) or (b) author a new full-suite greenfield fixture (net-new scope, blocked by the coupling debt). Either way, regenerate goldens only via the documented ceremony with a justifying diff — never force-pass.

### Sibling pattern to mirror (TDD-first receipt)

Mirror `tests/unit/specialists/test_phase1_2b8_authoring.py` exactly → new `tests/unit/specialists/test_support_2b11_authoring.py`:
- `_REPO = Path(__file__).resolve().parents[3]`; `_AGENTS = _REPO/"src"/"sdlc"/"agents"`.
- frozensets `_NET_NEW_SUPPORT_NAMES`, `_PLACEHOLDER_MARKERS`; `pytestmark = pytest.mark.unit`.
- positive receipt (registry loads net-new), phase check (report-all aggregation per CR2B9-P1), schema_version==1, boundary-absence, placeholder-absence (harden the silent-skip), + reuse `icon-too-long.md` / `missing-description.md` negative receipts (ADR-026 §1 anti-tautology). The three-way name match is enforced structurally by the loader (orphan + `name==stem`).

### Wheel packaging (VERIFIED)

`agents/` is force-included (`pyproject.toml [tool.hatch.build.targets.wheel.force-include]` `"src/sdlc/agents" = "sdlc/agents"`) → a new `support/` subdir ships automatically; NO pyproject change. But `tests/integration/test_wheel_build.py::_ALLOWED_CONTENT_FILES` must gain each `Path("sdlc/agents/support/<name>.md").as_posix()` (a guard asserts each allowlist path exists in-source). CR2B10-W2 (triple-maintenance: `index.yaml` + wheel allowlist + test name-set) applies — update all three in lockstep.

### Sibling / worktree coordination (DAG §3/§5/§6, CONTRIBUTING §3)

- 2B.8 (merged), 2B.9, 2B.10, and 2B.11 ALL append to `src/sdlc/agents/index.yaml`, `docs/specialists-matrix.md`, and `tests/integration/test_wheel_build.py`. Per §3: rebase, never merge-commit the shared files. DAG §6: 2B.11 is the **terminal writer** → rebase onto the merged 2B.9+2B.10 `main` last.
- The matrix arrives at 2B.11 in a HALF-updated state (2B.9 promoted Phase-2; 2B.10 did not promote Phase-3). 2B.11 owns completing it (CR2B10-W9).

### Previous-story intelligence

- **2B.8** authored 7 Phase-1 net-new + the `test_phase1_2b8_authoring.py` receipt pattern; deferred `clarification-triager` (D1=(a)); reversed an initial guess and proved the boundary line must be ABSENT from bodies.
- **2B.9** authored 6 Phase-2 net-new (all `phase: 2`); updated the matrix (Phase-2 → Shipped); deferred 4 standalone specialists' dispatch wiring (CR2B9-DN1: `write_globs:[]` dispatch fault); CR2B9-P1 fixed report-all aggregation in the schema test.
- **2B.10** authored 4 Phase-3 net-new (all `phase: 3`); did NOT touch the matrix; explicitly handed the count-gate reconciliation (CR2B10-W8) and matrix regen (CR2B10-W9) to 2B.11.

### Open debt 2B.11 closes vs carries

- **CLOSES:** `CR2B10-W8` (count-gate reconciliation), `CR2B10-W9` (matrix planned→shipped regen).
- **CARRIES (not 2B.11's to close):** `CR2B9-DN1` (standalone-specialist dispatch wiring → dispatch-integration story — but author defensively re empty `write_globs`); `CR2B10-W2` (triple-maintenance — mitigated by D5 generator if chosen); `CR2B4-W4 / EPIC-2B-DEBT-SPECIALIST-BODY-BOUNDARY-NORMALIZE` (production-hardening sprint); `EPIC-2B-DEBT-SPECIALIST-FILE-INTEGRITY` (no sha256 verify — post-2B.7/Epic-3); `EPIC-2B-DEBT-COVERAGE-90-FLOOR` (operational floor is 87, CONTRIBUTING documents 90); `EPIC-2B-DEBT-CLAUDE-TOOL-CALLS` + `EPIC-2B-DEBT-CHAIN-EMISSION-CAPTURE` (conformance coupling).

### Testing standards

pytest; AAA; coverage ≥ the enforced floor (pyproject `--cov-fail-under=87`; CONTRIBUTING documents ≥90 per EPIC-2B-DEBT-COVERAGE-90-FLOOR). TDD-first: validation + count-gate tests are the failing-first commit, visible in `git log --reverse` (§2). Conformance asserts mock-vs-claude byte identity (2B.3). Quality-gate commands (CONTRIBUTING §1): `ruff format --check .`, `ruff check .`, `mypy --strict src/`, `pytest`, coverage, `pre-commit run --all-files`, `mkdocs build --strict`, `python scripts/freeze_wireformat_snapshots.py --check`.

### Decisions Needed (CONTRIBUTING §5)

- **D1 — Support specialist scope.** The epic lists 6; 3 are already shipped (`devil-advocate`/`synthesizer`/`signoff-summarizer`).
  - **(a) Author the 3 genuinely net-new** (`clarification-triager`, `agent-failure-recovery`, `orchestrator-helper`); record `devil-advocate`/`synthesizer`/`signoff-summarizer` as staffed-by-shipped in the matrix. Staffs all FR28 roles. **(Recommended — `devil-advocate` re-authoring is a hard duplicate-name registry failure; `synthesizer`/`signoff-summarizer` net-new files would be callerless orphans.)**
  - **(b) (a) + author a generic `support/signoff-summarizer.md`** (4 files) for literal FR28 parity — adds a 4th registered-but-undispatched file.
  - **(c) Author only `clarification-triager`** (the sole matrix-backed Support-planned row) — undershoots FR28 (orchestrator/recovery roles unstaffed).
- **D2 — Location + phase value.**
  - **(a) New `src/sdlc/agents/support/` dir, `phase: 0`** — establishes the cross-cutting support convention; `list_phase(0)` works; auto-packaged by the `agents/` force-include. **(Recommended — semantically honest; `phase: 0` is schema-legal.)**
  - **(b) Place in `phase1/` with `phase: 1`** (e.g. `clarification-triager` routes Phase-1 clarifications) — avoids a new dir + the phase:0 first-use, but mislabels cross-cutting roles as Phase-1.
- **D3 — Count-gate bound (closes CR2B10-W8).**
  - **(a) Re-derive from the matrix + pin a band** around the actual roster (e.g. `≥35, ≤45` for 39–40), amend epics.md AC + DAG §3 + one-line ADR-030 amendment. **(Recommended — matrix is authoritative; a band tolerates near-future small additions.)**
  - **(b) Assert registry count == matrix Shipped-row count** (consistency, not a hardcoded band) — most drift-proof; folds into D5's consistency test.
  - **(c) Keep `≥23, ≤27`** — NON-VIABLE (36+ roster; matrix wins; would require deleting shipped specialists).
- **D4 — Ship-signal interpretation (AC10).**
  - **(a) Re-use `test_abstraction_adequacy.py`** green in CI on `main` with full roster registered — honest given the fixture-scoped wiring + carried coupling debt. **(Recommended.)**
  - **(b) Author a new greenfield-walkthrough fixture** driving the real specialist suite end-to-end — faithful to epic prose but net-new scope and blocked by `EPIC-2B-DEBT-CLAUDE-TOOL-CALLS`.
- **D5 — Matrix-regen mechanism (closes CR2B10-W9).**
  - **(a) Hand-update matrix + add a consistency test** pinning rows ⟷ `index.yaml`. **(Recommended — cheap, prevents future drift.)**
  - **(b) Write a generator** that emits the matrix from `index.yaml` + `--check` mode — also discharges CR2B10-W2 triple-maintenance, but more scope.
  - **(c) Hand-update only** (no test) — leaves the drift hazard.

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context JSON/XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.8 (1M context)

### Debug Log References

### Completion Notes List

**T0 Decisions locked (2026-06-01):**
- D1=(a): 3 genuinely net-new: `clarification-triager`, `agent-failure-recovery`, `orchestrator-helper`. `devil-advocate`/`synthesizer`/`signoff-summarizer` recorded as staffed-by-shipped in matrix §2.
- D2=(a): New `src/sdlc/agents/support/` dir, `phase: 0` (cross-cutting support). First use of `phase:0`; schema-legal per `manifest.py:24 Literal[0,1,2,3]`.
- D3=(a): Count bound re-derived from matrix §4: actual roster = 39 after 2B.11; band `≥39, ≤45`. Recorded in test + DAG §3 + epics.md AC + ADR-030 Revision Log.
- D4=(a): Re-used `test_abstraction_adequacy.py` green as ship signal — fixture-scoped, roster-independent. 5/5 pass. Carried coupling debt: `EPIC-2B-DEBT-CLAUDE-TOOL-CALLS` + `EPIC-2B-DEBT-CHAIN-EMISSION-CAPTURE` unchanged.
- D5=(a): Hand-updated matrix + count-gate + workflow-ref tests as consistency gates. No generator written (D5=(b) deferred per scope).

**Prerequisite merge (blocking T0):** 2B.9 and 2B.10 were NOT on main when 2B.11 started. Executed:
- Committed CR2B9-P1/P2 patches (uncommitted in wt-2b-9) → rebased 2B.9 → fast-forward merged 2B.9 into main.
- Committed CR2B10 review patches (uncommitted in wt-2b-10) + fixed LOC cap (422→398 by parametrizing two OSError tests) + resolved `test_wheel_build.py` conflict → rebased 2B.10 → fast-forward merged 2B.10 into main.
- Post-merge: `index.yaml` has 36 specialists ✅ AC1 confirmed.

**TDD ordering:** RED commit (`test(2b.11)`) → GREEN commit (`feat(2b.11)`) → docs commit (`docs(2b.11)`) — visible in `git log --reverse` on `epic-2b/2b-11-support-specialists`.

**Quality gate (2026-06-01):** ruff ✅ | mypy --strict 139 files ✅ | pytest 2894 passed ✅ | coverage 88.10% ≥ 87% ✅ | pre-commit 19/19 ✅ | mkdocs --strict ✅ | wireformat 5/5 ✅. No mock fixture regen needed (abstraction-adequacy seed uses static hash, independent of specialist body text — 0 drift confirmed).

**Ship signal (AC10/D4=(a)):** `test_abstraction_adequacy.py` 5/5 GREEN with full 39-specialist roster. `test_cross_runtime_byte_identity` pass. Fixture-scoped caveat documented in Dev Notes.

**CR2B10-W8 CLOSED:** stale `≥23,≤27` → `≥39,≤45` updated in 4 locations.
**CR2B10-W9 CLOSED:** matrix §3 Planned collapsed to 0; all Phase-3 + support promoted to §1 Shipped.

### File List

**Worktree:** `epic-2b/2b-11-support-specialists` (branched from `main` after 2B.9 + 2B.10 merge)

NEW files:
- `src/sdlc/agents/support/clarification-triager.md`
- `src/sdlc/agents/support/agent-failure-recovery.md`
- `src/sdlc/agents/support/orchestrator-helper.md`
- `tests/unit/specialists/test_support_2b11_authoring.py`

MODIFIED files:
- `src/sdlc/agents/index.yaml` (3 support entries, `phase: 0`)
- `docs/specialists-matrix.md` (promote 4 P3 + 3 support; §3 Planned→0; §4 totals 32→39; D5 consistency note)
- `_bmad-output/planning-artifacts/epics.md` (2B.11 count AC: `≥39,≤45`)
- `docs/sprints/epic-2b-dag.md` (§3 count bound: `≥39,≤45` in 4 places)
- `docs/decisions/ADR-030-specialist-roster-freeze.md` (Revision Log entry 2026-06-01)
- `tests/integration/test_wheel_build.py` (`_ALLOWED_CONTENT_FILES` +3 support paths)
- `_bmad-output/implementation-artifacts/deferred-work.md` (CR2B10-W8/W9 CLOSED)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (ready-for-dev → in-progress → review)
- `_bmad-output/implementation-artifacts/2b-11-author-support-specialists.md` (this file)

PREREQUISITE MERGE commits on main (before 2B.11 branch):
- `fix(2b.9): apply CR2B9-P1 + CR2B9-P2 patches` (on 2B.9 worktree; then merged FF)
- `fix(2b.10): merge two _write_bytes_to_disk OSError tests into parametrized — trim LOC`
- `fix(2b.10): apply CR2B10 review patches P1-P8` (on 2B.10 worktree; then merged FF)
- 2B.9 FF merge + 2B.10 FF merge + chore(2b.11) tracking commit

## Change Log

| Date | Version | Description | Author |
|---|---|---|---|
| 2026-06-01 | 0.1 | Story created via `bmad-create-story` (ready-for-dev). Exhaustive analysis across the two un-merged worktrees + count-gate/matrix/conformance machinery. Surfaced the blocking 2B.9/2B.10 merge prerequisite, the `devil-advocate` duplicate-name hazard, the stale `≥23,≤27` count gate (closes CR2B10-W8), and the half-updated matrix (closes CR2B10-W9). 13 ACs / 14 tasks / 5 decisions. | Bob (Scrum Master) via Claude Opus 4.8 |
| 2026-06-01 | 1.0 | Implementation complete (in-progress→review). Executed blocking prerequisite merges: committed CR2B9-P1/P2 patches + rebased + FF-merged 2B.9; committed CR2B10 review patches (P1-P8, LOC-cap fix, conflict resolve) + rebased + FF-merged 2B.10. Branched 2B.11 from 36-specialist main. TDD RED→GREEN: test_support_2b11_authoring.py (10 tests: registry-loads/phase=0/schema_version/boundary/placeholder/tools/count-gate/workflow-ref/2 neg receipts). Authored 3 support specialists (clarification-triager, agent-failure-recovery, orchestrator-helper) with production bodies + registered phase:0. Matrix regen (§1 39, §3→0), count-gate [39,45], ADR-030 Revision Log. Ship signal: test_abstraction_adequacy.py 5/5 GREEN. Quality gate: ruff+mypy+2894 tests+88.10%+pre-commit+mkdocs+wireformat all PASS. CR2B10-W8+W9 CLOSED. | Elena (Dev) via Claude Opus 4.8 |
