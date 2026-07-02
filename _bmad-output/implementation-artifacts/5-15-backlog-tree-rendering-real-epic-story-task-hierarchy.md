# Story 5.15: Backlog Tree Rendering Real Epic→Story→Task Hierarchy

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L6 (5B). L6 = {5.13, 5.14, 5.15, 5.16, 5.18}, 4 (cap-bound; 5 stories → 2 batches). **Authoritative batch 1 = {5.14, 5.15, 5.16, 5.18}** (the four independent 1:1 real-data swaps), batch 2 = {5.13} alone rebased on batch-1 merges (DAG §3:225-228). Max 4 parallel worktrees; owner Sally. Worktree: epic-5/5-15-backlog-tree-real-hierarchy (branch from main, linear merge, rebase between L6-batch-1 merges — CONTRIBUTING §3). Edges: **5.10 → 5.15** (twin — the synthetic backlog-tree component this story swaps onto real data; DAG §2:145) + external wave gate **E2A → 5.15** (real Epic→Story→Task hierarchy ← Story 2A.11 + canonical id regex ← Story 1.6; DAG §2:173, §2:112). This is a 1:1 real-data swap: keep the 5.10 render/keyboard/a11y seam intact, swap ONLY the data source. a11y coverage lands via the 5.10 twin → 5.12 (done) + the terminal 5.22 gate (DAG §2:202) — do NOT re-run the a11y convergence here. NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). WAVE-BOUNDARY (DAG §3:193-194, §7:351): 5B cannot start until Epic 2A (2A.11) actually emits the expected hierarchy shape — 2A.11 is done+merged (sprint-status.yaml:176), BUT see D1: the real hierarchy is emitted as the 04-Epics/05-Stories artifact tree, NOT yet folded into the projected state.json (state/projection.py:27 reserves story-/task-). Resolve D1 before coding. -->

## Story

As Diep navigating real backlog,
I want the Backlog Tree (Story 5.10 component) reading real Epic/Story/Task hierarchy from state.json,
So that neighbor-context lookup works on real data.

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.15, lines 2749–2761).

**Given** state.json reflecting real epics, stories, tasks (after Story 2A.11)
**When** the Backlog Tree renders
**Then** the hierarchy matches state.json byte-for-byte
**And** task ids in inline code use the canonical regex format (Story 1.6)
**And** clicking a node expands/collapses; state persists in URL hash for shareability

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** four things in this story are testable *contracts* → tests-first. (1) The **hierarchy-derivation contract (AC "hierarchy matches state.json byte-for-byte")** — a pure adapter that reconstructs the nested Epic→Story→Task tree from real state.json records must neither drop, add, nor reorder records → golden-fixture test over a committed real-shape state.json. (2) The **canonical-id-format contract (AC "task ids in inline code use the canonical regex format (Story 1.6)")** — every id rendered in `<code class="inline-code">` must validate against `EPIC_ID_REGEX`/`STORY_ID_REGEX`/`TASK_ID_REGEX` (`src/sdlc/ids/parsers.py`). (3) The **URL-hash persistence contract (AC "state persists in URL hash for shareability")** — expand/collapse writes the expanded-node set to the hash; a reload (or shared link) reproduces the same expansion → Playwright test. (4) **Expand/collapse behavior** — clicking a node toggles it. The tree render/keyboard/a11y seam is the FROZEN 5.10 substrate → `test-along` (do NOT re-author it). Zero wire-format change → **freeze stays 7/7**. Resolve Decisions D1–D5 BEFORE coding.

- [x] **Task 0 — Resolve Decisions D1 (real hierarchy source + the state.json projection gap — WAVE-BOUNDARY) + D2 (flat-dict → nested-tree adapter by canonical-id parse) + D3 (URL-hash persistence grammar + injection-safety) + D4 (empty/zero-epic real data → empty-state + Tab-reachability + numeric-0 count, DEF-3) + D5 (unknown flow-step handling + canonical-id tolerance, DEF-5) BEFORE coding** (AC: all)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). D1 is the batch-1 wave-boundary gate — raise it to the PO before writing code (do not proceed under "I'll backfill later", CONTRIBUTING §7.4 spirit). Confirm the real 2A.11 hierarchy shape is actually reachable by the dashboard through the `state`/`journal` reader seam (DAG §5:310-313), NOT by re-parsing wire files.

- [x] **Task 1 — Real hierarchy source + nesting adapter (pure, tested)** (AC: "hierarchy matches state.json byte-for-byte") — *tests-first*
  - [x] Per D1, source the real Epic→Story→Task records **through the existing `state`/`journal` reader seam** (one-way module edge `dashboard` → `state`/`journal`, NEVER the reverse; NEVER re-parse the wire files directly) [scripts/check_module_boundaries.py; DAG §5:310-313].
  - [x] Per D2, write a **pure nesting adapter** that reconstructs the nested tree the 5.10 renderer consumes from the real (flat, canonical-id-keyed) records: group each STORY under its EPIC and each TASK under its STORY by **parsing the canonical id** (`parse_epic_id`/`parse_story_id`/`parse_task_id` — a `StoryId.epic_slug` links to its `EpicId.epic_slug`; a `TaskId.epic_slug + story_num` links to its `StoryId`) [src/sdlc/ids/parsers.py:58-157].
  - [x] **Golden-fixture test (RED→GREEN):** the derived nest contains exactly the state.json records — no dropped/added/duplicated/reordered node; the flattened set of ids round-trips 1:1 to the source records. RED: a fixture where a task is orphaned (parent story absent) or a story is dropped fails; GREEN: a well-formed hierarchy passes. Mirror the gate-import pattern (`tests/conftest.py` puts `scripts/` on `sys.path`).

- [x] **Task 2 — Swap the backlog-tree data source onto the real nested shape (seam-only)** (AC: "hierarchy matches state.json byte-for-byte") — *tests-first*
  - [x] Feed the Task-1 adapter output into the FROZEN 5.10 renderer via `renderBacklogTree(host, realFixture)` [backlog-tree.js:495]. **Do NOT re-author** the render/keyboard/a11y internals — `renderEpic`/`renderStory`/`renderTaskRow`, `collectVisibleExpanders`/`setRovingTabindex`/`focusExpanderById`, the WAI-ARIA `role="tree"`/`treeitem`/`aria-level`/`aria-setsize`/`aria-posinset`/`aria-expanded`/`aria-current` markup, and the DD-15 focus ring stay exactly as 5.10 froze them.
  - [x] **Honor PAT-2:** the live fixture is resolved from `host._fixtureRef` on EVERY render and inside the keyboard/click handlers [backlog-tree.js:396,488,531] — the real-data re-render (poll cycle) MUST update `host._fixtureRef` so handlers act on the current data, not the object captured at first bind. This is the exact trap 5.10 PAT-2 was written for.
  - [x] **Honor the 5.10 leaf-focus lesson (DEC-1):** never make a roving `.tree-expander` `visibility:hidden` (non-focusable → `.focus()` drops to `<body>`); the real data must keep every visible row keyboard-reachable.

- [x] **Task 3 — Canonical id inline-code (Story 1.6 regex)** (AC: "task ids in inline code use the canonical regex format (Story 1.6)") — *tests-first*
  - [x] The ids rendered in `<code class="inline-code">` for epic/story/task rows [backlog-tree.js:98-103,155,200,261] carry the **real canonical ids** (e.g. `EPIC-stripe-webhook-S04-idempotency-T01-redis-key`), NOT the 5.10 synthetic non-canonical ids (`EPIC-stripe-S04-T01`, which do not satisfy the canonical regex).
  - [x] **Contract test (RED→GREEN):** every id shown in inline code validates against the canonical regex sourced from Story 1.6 — `EPIC_ID_REGEX`/`STORY_ID_REGEX`/`TASK_ID_REGEX` in `src/sdlc/ids/parsers.py` (task ids match `TASK_ID_REGEX`, story ids `STORY_ID_REGEX`, epic ids `EPIC_ID_REGEX`). RED: a fixture id missing the `-T<NN>-<slug>` tail fails `TASK_ID_REGEX`; GREEN: a canonical id passes. Assert the regex source is the shared 1.6 module, not a re-declared copy.

- [x] **Task 4 — Expand/collapse + URL-hash persistence for shareability** (AC: "clicking a node expands/collapses; state persists in URL hash") — *tests-first*
  - [x] Clicking a parent node expands/collapses it — reuse the FROZEN 5.10 `toggleExpanded` + host `click` seam [backlog-tree.js:308-314,475-491]; do not re-implement toggling.
  - [x] Per D3, **persist the expanded-node set in the URL hash** (new to 5.15 — 5.10 keeps expansion only in the in-memory fixture object `hit.node.expanded` [backlog-tree.js:313,428,435,447] + roving `preserveFocusId`, with NO URL/storage persistence): read-on-load (apply the hash → each named node's `expanded=true`), write-on-toggle/click (serialize the currently-expanded canonical ids to the hash). Use `history.replaceState`/`hashchange` (D3 picks the mode); no full page reload.
  - [x] **Injection-safety:** validate every id read from the hash against the Story 1.6 regex (`EPIC/STORY/TASK_ID_REGEX`) BEFORE applying it; silently ignore unknown/malformed ids (forward-compat, no throw, no XSS — the tree already renders via `textContent` only).
  - [x] **Playwright test (RED→GREEN):** expand a node → assert the hash updates with that node's canonical id → reload the page (or open the shared hash URL) → assert the same nodes are expanded and roving focus is coherent. RED against the 5.10 no-persistence baseline; GREEN after the hash seam lands.

- [x] **Task 5 — Empty/zero-epic real data + unknown flow-step + numeric-0 count (fold DEF-3 / DEF-5)** (AC: "hierarchy matches state.json byte-for-byte") — *tests-first*
  - [x] **DEF-3 (empty/zero-epic):** real data can be empty (a fresh project). The 5.10 tree renders `role="tree"` with **no `tabindex=0` entry point** for an empty fixture — unreachable by Tab, no empty-state [backlog-tree.js:514-522; deferred-work.md:888]. Per D4, render an empty-state row (measured, anti-cynicism copy — reuse the 5.11 `<empty-state>` element/pattern; do NOT build the 5.19 STOP path) OR a focusable tree container, and add a **zero-epic test** asserting Tab reaches a focus entry point.
  - [x] **Numeric-0 count:** an empty/zero-child real backlog must render a `0` count (e.g. "0 stories"), not a blank — the section-block-heading count-render blanks a numeric `0` (5.11 review defer, owned by 5.14/5.15) [section-heading.js:17; 5-11 story Review Findings]. Coerce falsy-but-numeric `0` to the string `"0"`.
  - [x] **DEF-5 (unknown flow-step):** `createFlowPillGroup` silently drops flow steps not in `PILL_FLOW_VARIANTS` [pills.js:60-72; deferred-work.md:890]. Real epic `flow` may carry stages beyond `research/epics/stories`. Per D5, emit all known stages (or a neutral fallback pill) + add an **unknown-flow-step test**. Do NOT expand the frozen pill token vocabulary without a decision.

- [x] **Task 6 — Committed real-shape fixture + static-analysis/Playwright contract tests** (AC: all) — *tests-first*
  - [x] Commit a **real-shape state.json fixture** (canonical-id epics/stories/tasks) + the Task-1 derived-nest golden. Extend the 5.10 test surfaces: `tests/unit/dashboard/test_backlog_tree_fixture.py` (hierarchy-derivation + canonical-id-regex contracts) and `tests/integration/test_dashboard_backlog_tree.py` (expand/collapse + URL-hash persistence Playwright). RED: byte-mismatch nest, non-canonical id, or a lost hash on reload fails; GREEN: correct.
  - [x] Do NOT weaken the tests into source-substring greps — 5.10/5.11 review history (PAT-3, the inverted-feed HIGH) shows greps miss behavioral defects. Assert rendered-DOM/behavior, not source text.

- [x] **Task 7 — Packaging + quality gate + freeze** (AC: all)
  - [x] Add any new static/JS/fixture files (nesting-adapter output surface, real-shape fixture, URL-hash module, empty-state wiring) to the `force-include` block [pyproject.toml — the 5.10 backlog-tree/pills entries live at pyproject.toml:115-121].
  - [x] Component CSS (if any new) uses `var(--*)` only (5.2 stylelint gate); run the DD-14 motion gate (no transitions — chevron is a glyph swap; expand/collapse is `display` toggle), DD-08 no-framework, DD-09 no-`data-theme`, and the 5.5 color-only gate (ids carry text; pills carry text).
  - [x] Python quality gate on any new `scripts/*.py`/adapter/tests (ruff + ruff format + mypy --strict); full pytest + coverage ≥ 87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7** (state.json is read byte-for-byte, not re-shaped on the wire).

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§6.6 Backlog Tree.** Three-level anatomy (class/token table), states (collapsed/expanded/current/hover/focus-visible), a11y (`role="tree"`/`role="treeitem"`/`aria-expanded`/`aria-level`/`aria-setsize`/`aria-posinset`/`aria-current`), and the full keyboard contract (Arrow/Enter/Home/End/`*`). *"Chevron … Glyph swap, no transform (DD-14)."* — **FROZEN by 5.10; this story does not re-author it.** [Source: ux-design-specification.md §6.6:1221-1269 (per the 5.10 twin's verified citation)]
- **§7.3 Kind Badge Family.** *"A kind badge always appears immediately to the **left** of the record's name … Badges never appear without an adjacent name."* Variants EPIC/STORY/TASK. **FROZEN by 5.10** — the real-data swap must keep the badge-left-of-name consistency contract on every real row. [Source: ux-design-specification.md §7.3:1472-1486 (per the 5.10 twin)]
- **§7.9 Pill Family.** Sub-patterns (kind badge / status / stage / flow / priority) + *"Pills always have **text** content; never purely color or purely glyph."* Real status/flow values map onto the frozen pill registry (D5 for unknown flow steps). [Source: ux-design-specification.md §7.9:1564-1580 (per the 5.10 twin)]
- **AC (epics.md:2757-2761).** *"the hierarchy matches state.json byte-for-byte / task ids in inline code use the canonical regex format (Story 1.6) / clicking a node expands/collapses; state persists in URL hash for shareability."* [Source: _bmad-output/planning-artifacts/epics.md:2749-2761]
- **One-way module edge (Architecture §1073 / DAG §5).** *"the `dashboard` package may depend on the `state`/`journal` reader seam, but those modules MUST NOT depend on `dashboard` (one-way edge); … any derived view read through the reader, never by re-parsing wire files."* [Source: docs/sprints/epic-5-dag.md §5:310-313; scripts/check_module_boundaries.py]

### Real upstream contract (source-verified — pin these before coding)

**Canonical id regex (Story 1.6 — the AC's "canonical regex format").** Source of truth: `src/sdlc/ids/parsers.py` (also imported by 2A.11 per sprint-status.yaml:126). Exact patterns:

```text
EPIC_ID_REGEX  = ^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$
STORY_ID_REGEX = ^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)-S(?P<story_num>\d{2})-(?P<story_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$
TASK_ID_REGEX  = ^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)-S(?P<story_num>\d{2})-(?P<story_slug>[a-z0-9]+(?:-[a-z0-9]+)*)-T(?P<task_num>\d{2})-(?P<task_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$
```
[Source: src/sdlc/ids/parsers.py:9,11-12 (EPIC), :14-19 (STORY), :21-27 (TASK); public string forms `EPIC_ID_PATTERN`/`STORY_ID_PATTERN`/`TASK_ID_PATTERN` + compiled `*_REGEX`; parse helpers `parse_epic_id`/`parse_story_id`/`parse_task_id` :58-157]
> The 5.10 synthetic ids (`EPIC-stripe-S04`, `EPIC-stripe-S04-T01` — backlog-tree.js:19,37) are **NOT canonical**: a canonical STORY id needs the trailing `-<story_slug>` and a canonical TASK id needs `-T<NN>-<task_slug>`. Real data is canonical; the inline-code render must show the real canonical id (Task 3).

**Real hierarchy shape + the projection gap (WAVE-BOUNDARY — drives D1).** Three source facts, all verified:
1. **State model has FLAT dicts, not a nested tree.** `State.epics: dict[str, Any]`, `State.stories: dict[str, Any]` *"keyed by canonical story id (e.g. `EPIC-foo-S01-bar`)"*, `State.tasks: dict[str, Any]` *"keyed by canonical task id (e.g. `EPIC-foo-S01-bar-T01-baz`)"* [Source: src/sdlc/state/model.py:28-32]. So state.json is a set of flat, canonical-id-keyed record maps — the nested Epic→Story→Task tree the 5.10 renderer wants must be **derived** by parsing those canonical keys (Task 1/2, D2).
2. **The projection does NOT yet fold stories/tasks.** `state/projection.py` only projects `epics` (keyed by the *minimal* `epic-N` pattern `\Aepic-[0-9]+\Z`, NOT the canonical `EPIC-<slug>`), and explicitly *"Other patterns (story-, task-) are reserved for later stories."* → `state.json["stories"]` / `["tasks"]` are currently **empty** in the projected state [Source: src/sdlc/state/projection.py:27-28, :148-155].
3. **2A.11 emits the real hierarchy as an artifact tree, not into projected state.json.** `sdlc stories` writes story files under `01-Requirement/05-Stories/<EPIC-id>/STORY-<seq>-<slug>.json` (and `sdlc epics` writes `04-Epics/EPIC-<slug>.json`); the state.json write is only a `next_monotonic_seq` counter bump [Source: src/sdlc/cli/stories.py:344-371; sprint-status.yaml:126]. 2A.11 is **done+merged** (sprint-status.yaml:176).

**Net:** the AC's premise ("state.json reflecting real epics, stories, tasks … hierarchy matches state.json byte-for-byte") is not literally satisfiable against *today's projected* state.json (stories/tasks unfolded). The real hierarchy exists — in the 04-Epics/05-Stories artifact tree with canonical ids — but a source/route decision (D1) is needed to reach it through the reader seam.

**Reader seam.** The dashboard serves `GET /state.json` by streaming the file **byte-for-byte** (`.claude/state/state.json`) with ETag/304 — no re-shape on the wire [Source: src/sdlc/dashboard/routes/state.py:12,18-40]. Whatever real source D1 picks, expose it through this reader-seam discipline; do not add a `dashboard → state`-reverse dependency (check_module_boundaries.py enforces the one-way edge).

### Frozen 5.10 substrate to consume (do NOT re-author — swap the data source only)

```text
renderBacklogTree(host, fixture, options)   — public swap point; sets host._fixtureRef on EVERY render (PAT-2). [backlog-tree.js:495-536]
SYNTHETIC_TREE_FIXTURE                        — the shape to match: { currentTaskId, epics:[{ id,kind,name,flow,meta,pct,expanded, stories:[{ id,kind,name,status,meta,pct,expanded, tasks:[{ id,kind,name,status,meta }] }] }] }. [backlog-tree.js:15-73]
renderEpic / renderStory / renderTaskRow      — nested-list + WAI-ARIA treeitem markup + kind-badge-left-of-name. [backlog-tree.js:126-286]
collectVisibleExpanders / setRovingTabindex / focusExpanderById — roving-tabindex (single tab stop). [backlog-tree.js:330-386]
bindTreeKeyboard                              — Arrow/Enter/Home/End switch, preventDefault per key; live fixture from host._fixtureRef (PAT-2). [backlog-tree.js:388-473]
toggleExpanded / host click handler           — click expand/collapse seam (reuse for AC "clicking a node expands/collapses"). [backlog-tree.js:308-314,475-491]
createInlineCode(text)                         — `<code class="inline-code">` for ids (Task 3 shows canonical ids here). [backlog-tree.js:98-103]
createFlowPillGroup(steps)                     — drops unknown flow steps (DEF-5, D5). [pills.js:60-72]
```
Leaf-focus lesson (5.10 DEC-1): never make a roving `.tree-expander` `visibility:hidden` (non-focusable → focus drops to `<body>`). PAT-2: read live data from `host._fixtureRef`, never a captured closure.
[Source: src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js:15-536; src/sdlc/dashboard/static/components/pills/pills.js:60-72]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Real hierarchy source + the state.json projection gap (HIGH — WAVE-BOUNDARY, NEEDS-DECISION).** The AC assumes state.json already carries a real nested Epic→Story→Task hierarchy, but (verified) the projection reserves story-/task- folding "for later stories" [state/projection.py:27-28] so `state.json["stories"]`/`["tasks"]` are empty, and 2A.11 emits the real hierarchy as the `04-Epics`/`05-Stories` artifact JSON tree (canonical ids), not into projected state.json [cli/stories.py:344-371]. *Options:* **(a)** treat the `04-Epics` + `05-Stories/<EPIC-id>/` artifact tree as the real source and add a dashboard-side reader (through the `state`/`journal` reader seam — a small read-only view, NOT a wire re-parse) that assembles the records for the frontend; **(b)** block on an upstream projection extension that folds `stories`/`tasks` into `state.json` (a new upstream 2A/1.x dependency — out of 5.15 scope; would slip batch 1); **(c)** if a curated real-shape hierarchy already lands in `state.json` for the target fixture, bind to it directly. *Recommend raising to the PO as the batch-1 wave-boundary gate; lean (a)* (keeps 5.15 self-contained, honors the reader-seam one-way edge, and satisfies "byte-for-byte" against the artifact records the nest is derived from). Do NOT start Task 1 until D1 is ratified.

**D2 — Flat-dict → nested-tree adapter by canonical-id parse (HIGH).** Real records are FLAT + canonical-id-keyed [state/model.py:28-32]; the 5.10 renderer wants a nest [backlog-tree.js:15-73]. *Recommendation (a):* a **pure adapter** (prefer server-side Python for pytest coverage + reader-seam fit; client-side JS acceptable if D1 delivers records to the browser) that groups STORY under EPIC and TASK under STORY by parsing canonical ids (`parse_story_id().epic_slug` → epic; `parse_task_id().(epic_slug, story_num)` → story) [ids/parsers.py:88-157], emitting the exact `{currentTaskId, epics:[…]}` shape the renderer already consumes — so the render seam is untouched. Golden-fixture test guards byte-for-byte fidelity. *Alternative (b):* nest inside `renderBacklogTree` — rejected (couples parsing into the frozen renderer; harder to test).

**D3 — URL-hash persistence grammar + injection-safety (MED — new to 5.15).** 5.10 has NO persistence (expand state is in-memory `hit.node.expanded` only [backlog-tree.js:313,428,435,447]). *Recommendation (a):* serialize the set of expanded canonical ids into the hash (e.g. `#backlog=<comma-separated canonical ids>`); read-on-load applies them, write-on-toggle updates via `history.replaceState` (no new history entry per toggle) with a `hashchange` listener for shared-link loads; **every id from the hash is validated against `EPIC/STORY/TASK_ID_REGEX` before use** and unknown ids are silently ignored (forward-compat, no throw). Keep it text-only (no `innerHTML`) — no XSS surface. *Alternative (b):* `pushState` per toggle (rejected — pollutes browser history) or `localStorage` (rejected — not shareable, AC says URL hash).

**D4 — Empty/zero-epic real data → empty-state + Tab-reachability + numeric-0 count (MED — folds DEF-3 + the 5.11 numeric-0 defer).** Real data can be empty; 5.10 leaves an empty tree Tab-unreachable with no empty-state [backlog-tree.js:514-522; deferred-work.md:888], and the section-block heading blanks a numeric `0` count [section-heading.js:17; 5-11 Review Findings, owner 5.14/5.15]. *Recommendation (a):* render a measured anti-cynicism empty-state row (reuse the 5.11 `<empty-state>` element/pattern — do NOT build the 5.19 STOP path) or a focusable tree container so Tab always has an entry point; coerce a numeric `0` child-count to `"0"` (not blank). Add a zero-epic test. *Alternative (b):* leave empty handling to 5.22 — rejected (real data makes empty reachable NOW).

**D5 — Unknown flow-step handling + canonical-id tolerance (LOW→load-bearing — folds DEF-5).** `createFlowPillGroup` silently drops flow steps outside `PILL_FLOW_VARIANTS` [pills.js:60-72; deferred-work.md:890]; real epic `flow` may include stages beyond `research/epics/stories`. *Recommendation (a):* emit a neutral fallback pill for unknown steps (or map all known stages) + an unknown-step test; do NOT expand the frozen pill token vocabulary without escalating. Also: any id-parse must fail-loud or safely skip on a malformed real id (never render a broken/`undefined` id). *Alternative (b):* keep the silent drop — rejected (real flow data would render fewer pills than the record, breaking the byte-for-byte contract's spirit).

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the **1:1 real-data swap** onto the FROZEN 5.10 backlog-tree — (1) a pure nesting adapter from real state.json records (Task 1/2), (2) canonical-id inline-code (Story 1.6 regex, Task 3), (3) **URL-hash expand/collapse persistence** (new, Task 4), (4) real-data edge handling for empty tree + unknown flow step + numeric-0 (DEF-3/DEF-5, Task 5). Reads real data through the `state`/`journal` reader seam only.
- **Must NOT build:** the render/keyboard/a11y internals (FROZEN by 5.10 — swap the data source, not the seam); **real signoff 4-state** (that is the sibling batch-1 story **5.14**, twin 5.9); **real `agent_runs.jsonl` activity feed** (that is **5.16**, twin 5.11); the DORA engine (5.13) or real KPI/DORA (5.17); the real resume card (5.18); the STOP banner / empty-state STOP path (5.19); any modals/toasts/forms/client-routing/skeleton loaders; any CSS `transition:`/transform except the frozen live-dot pulse (DD-14). Do NOT re-run the 5.12 a11y convergence gate (this story's a11y coverage rides the 5.10 twin → 5.12 done + the terminal 5.22). Do NOT extend/re-parse wire files or add a `dashboard → state`-reverse import. [Source: docs/sprints/epic-5-dag.md §2 (S10→S15:145, E2A→S15:173), §3 (L6 batch-1:225-228, 1:1-swap note:241), §5 (5.15 row:293, one-way edge:310-313), §7 (cross-epic coupling:351)]

### Project Structure Notes

- New: a nesting-adapter module (server-side Python under `src/sdlc/dashboard/` or a client-side JS helper under `static/components/backlog-tree/`, per D1/D2) + a committed real-shape state.json fixture + a URL-hash persistence module. All new static/fixture files → `force-include` [pyproject.toml:115-121 already lists the 5.10 backlog-tree/pills entries].
- Any new component CSS must use `var(--*)` — the 5.2 stylelint gate (`static/styles/.stylelintrc.json`); the expand/collapse is a `display` toggle + chevron glyph swap (no `transition:` — DD-14).
- **Module boundary:** if the adapter is server-side, it lives in `dashboard/` and reads via `state`/`journal` — `check_module_boundaries.py` forbids `state`/`journal` importing `dashboard` (one-way edge). Keep the adapter a pure read-only view.
- **Batch-1 sibling independence:** 5.14/5.15/5.16/5.18 are mutually-independent 1:1 real-data swaps (DAG §3:241). Branch from `main`, linear merge, rebase between L6-batch-1 merges (CONTRIBUTING §3). Batch 2 {5.13} rebases on batch-1's merges.
- Zero wire-format contracts (state.json is read byte-for-byte; CSS/JS/HTML are not wire contracts) → **freeze stays 7/7**.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Tree render / WAI-ARIA / roving-tabindex keyboard / focus ring | FROZEN 5.10 `renderBacklogTree` + `renderEpic`/`renderStory`/`renderTaskRow` + `collectVisibleExpanders`/`setRovingTabindex` (swap the data source only) | src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js:126-536 |
| Live-fixture resolution across re-renders (poll) | PAT-2 `host._fixtureRef` set on every render + read in handlers | src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js:396,488,531 |
| Canonical id regex + parse helpers (Story 1.6) | `EPIC/STORY/TASK_ID_REGEX` + `parse_epic_id`/`parse_story_id`/`parse_task_id` | src/sdlc/ids/parsers.py:9-27,58-157 |
| Real state records (flat, canonical-keyed) | `State.epics`/`.stories`/`.tasks` shape | src/sdlc/state/model.py:28-32 |
| Reader seam (byte-for-byte `/state.json`) + one-way module edge | stream `.claude/state/state.json`; `dashboard → state/journal` only | src/sdlc/dashboard/routes/state.py:12,18-40; scripts/check_module_boundaries.py |
| Inline-code id rendering | `createInlineCode(text)` → `<code class="inline-code">` | src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js:98-103 |
| Flow pills (unknown-step handling — DEF-5) | `createFlowPillGroup` + `PILL_FLOW_VARIANTS` | src/sdlc/dashboard/static/components/pills/pills.js:31-35,60-72 |
| Empty-state (anti-cynicism) for zero-epic (DEF-3) | reuse the 5.11 `<empty-state>` element/pattern (NOT the 5.19 STOP path) | src/sdlc/dashboard/static/components/empty-state/ |
| Static-analysis + Playwright test surfaces | extend the 5.10 tests (mirror, do not weaken to greps) | tests/unit/dashboard/test_backlog_tree_fixture.py; tests/integration/test_dashboard_backlog_tree.py |
| Motion / no-framework / color-only gates | run on any new component | scripts/check_dashboard_motion.py / _no_framework.py / _color_only.py |
| Wheel force-include | add new static/fixture files | pyproject.toml:115-121 |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2749-2761] — Story 5.15 statement + ACs (verbatim above)
- [Source: src/sdlc/ids/parsers.py:9-27,58-157] — canonical EPIC/STORY/TASK id regex (Story 1.6) — the AC's "canonical regex format"
- [Source: src/sdlc/state/model.py:28-32] — real state shape: FLAT `epics`/`stories`/`tasks` dicts keyed by canonical ids
- [Source: src/sdlc/state/projection.py:27-28,148-155] — projection folds only `epics` (`epic-N`); story-/task- reserved → the wave-boundary gap (D1)
- [Source: src/sdlc/cli/stories.py:344-371] — 2A.11 `sdlc stories` writes the `05-Stories` artifact tree; state.json only counter-bumped
- [Source: src/sdlc/dashboard/routes/state.py:12,18-40] — byte-for-byte `/state.json` reader seam (ETag/304)
- [Source: scripts/check_module_boundaries.py] — one-way `dashboard → state/journal` edge (no reverse import; no wire re-parse)
- [Source: src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js:15-536] — FROZEN 5.10 substrate (fixture shape, renderers, roving-tabindex, PAT-2, click/toggle seam, inline-code, empty-tree region :514-522)
- [Source: src/sdlc/dashboard/static/components/pills/pills.js:31-35,60-72] — flow pills + unknown-step drop (DEF-5)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:888 (DEF-3 empty/zero-epic → owner 5.15), :890 (DEF-5 unknown flow-step → owner 5.15), :891 (DEF-6 tree test-strength)] — 5.10 deferred items 5.15 owns/folds
- [Source: _bmad-output/implementation-artifacts/5-11-tabs-activity-feed-empty-state-section-block-heading.md (Review Findings — numeric-0 count `section-heading.js:17`, owner 5.14/5.15)] — numeric-0 fold (Task 5)
- [Source: _bmad-output/implementation-artifacts/5-10-backlog-tree-pill-family-inline-code.md:46,71,74,124] — keyboard contract, DEC-1 leaf-focus, PAT-2 stale-fixture, "real hierarchy is 5.15" hand-off
- [Source: docs/sprints/epic-5-dag.md §2 (S10→S15:145, E2A→S15:173, E2A label:112), §3 (L6 batch-1:215,225-228, 1:1-swap:241, wave-boundary:193-194), §4 (twin note), §5 (5.15 worktree row:293, one-way edge:310-313), §6 (L6 profile:329), §7 (cross-epic coupling risk:351)] — layer, batch, edges, worktree, wave-boundary
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml:176 (2a-11 done), :126 (2A.11 imports 1.6 id regex; writes 04-Epics/05-Stories)] — 2A.11 done+merged; upstream shape provenance

## Dev Agent Record

### Agent Model Used

Claude (Cursor bmad-dev-story workflow session, 2026-07-02)

### Debug Log References

- `uv run pytest tests/unit/dashboard/ tests/integration/ -q --no-cov` → 546 passed, 1 pre-existing unrelated flaky pass-on-retry (`test_dashboard_masthead.py::test_tab_title_updates_within_one_poll_cycle`, timing-based, passes in isolation, not touched by this story).
- `uv run pytest -q` (full suite) → 4183 passed, 4 skipped (platform-gated), 1 xfailed (pre-existing documented gap); coverage 88.57% (≥87% floor).
- `uv run ruff check .` / `uv run ruff format --check .` → clean.
- `uv run mypy --strict src/` → `Success: no issues found in 196 source files`.
- `uv run mkdocs build --strict` → 0 warnings.
- `uv run python scripts/freeze_wireformat_snapshots.py --check` → 7/7 contracts match (freeze intact — zero wire-format change).
- `scripts/check_module_boundaries.py`, `check_dashboard_{motion,no_framework,no_data_theme,no_external_fonts,color_only,forbidden_patterns}.py` → all OK.
- `uv run pre-commit run --all-files` → all hooks pass EXCEPT two pre-existing, unrelated failures confirmed present on `main` before this story touched anything: (1) `tests/property/test_replay_invariant.py` LOC cap (439 > 400 lines, untouched by this story, git-blamed to an earlier unrelated commit `bed55df`); (2) `end-of-file-fixer` auto-modified `tests/dashboard/vendor/axe.min.js` (a vendored third-party file, unrelated to this story) — that incidental edit was reverted (`git checkout --`) since it is out of this story's scope.

### Completion Notes List

- **D1 (WAVE-BOUNDARY, ratified before coding):** real hierarchy source = the `01-Requirement/04-Epics` + `05-Stories/<epic-id>/` + `03-Implementation/tasks/<story-id>/` canonical-id-keyed JSON artifact tree that 2A.11 (`sdlc epics`/`sdlc stories`) writes — NOT the projected `state.json` (whose `stories`/`tasks` keys stay empty per `state/projection.py:27-28`, reserved "for later stories"). Implemented as a new dashboard-side read-only route (`src/sdlc/dashboard/routes/backlog.py`, registered as `GET /api/backlog`), never a `dashboard → engine/cli` import and never a re-parse of `/state.json`.
- **D2:** a pure Python nesting adapter (`build_backlog_tree`) groups STORY under EPIC and TASK under STORY by parsing canonical ids via the SHARED `parse_epic_id`/`parse_story_id`/`parse_task_id` (never trusting directory names), emitting the exact `{currentTaskId, epics:[...]}` shape the FROZEN `renderBacklogTree` already consumes.
- **D3:** URL-hash grammar `#backlog=<comma-separated canonical ids>`; read-on-load + `hashchange`; write via `history.replaceState` triggered by a `MutationObserver` watching `childList` mutations on the host (every toggle/keyboard action re-renders via `host.replaceChildren()` — there is no in-place `aria-expanded` attribute flip to observe, so a `childList` observer — not an `attributes` observer — is what actually fires; the frozen click/keydown handlers in `backlog-tree.js` are untouched). Every hash id is validated against the Story 1.6 `EPIC/STORY/TASK_ID_REGEX` shape (mirrored in JS, kept in sync by a source-contract test) before use; unknown/malformed ids are silently dropped (no throw, no `innerHTML`).
- **D4:** empty-state early-return in `renderBacklogTree` (a Tab-reachable `tabindex="0"` row with anti-cynicism copy "No epics yet") — chose a plain focusable row over literally instantiating the 5.11 `<empty-state>` custom element, since that element is coupled to the STOP-banner `freshness-footer` poll-timestamp semantics which do not apply to a non-polling-in-that-sense backlog tree; the *pattern* (measured, non-exclamatory copy, Tab-reachable) is reused, not the element. Numeric-0 meta strings (`"0 tasks"`, `"0 stories"`) are generated via template literals in the Python adapter — never falsy-coerced.
- **D5:** `createFlowPillGroup` now emits a neutral fallback pill (reusing the `.pill--flow` token, unrecognized label rendered verbatim) for any flow step outside `PILL_FLOW_VARIANTS`, instead of silently dropping it — exercised by a direct unit + Playwright test since real epic JSON (`_EpicEntry` schema) carries no persisted `flow` field yet (forward-compatible fix, not exercised by real backlog data today).
- **Unplanned but necessary module-boundary amendment** (corrective, mirrors the Story 3.1 "adopt" precedent): `dashboard` gains `ids` as an allowed dependency in `scripts/module_boundary_table.py` — Task 3's AC requires the adapter to import the SHARED `parse_epic_id`/`parse_story_id`/`parse_task_id` + `EPIC/STORY/TASK_ID_REGEX` (not a re-declared copy), but `dashboard`'s `depends_on` set omitted `ids` (a pure leaf-ish module, `depends_on={errors}` only, `forbidden_from` empty — zero cyclic-risk).
- The golden-fixture hierarchy tests build fixture JSON through the REAL writer models (`sdlc.cli._epic_story_models.serialize_entry`/`serialize_task_entry`) rather than a hand-rolled/committed static JSON file, so the test exercises the actual on-disk byte shape 2A.11 produces (avoids fixture drift as the writer schema evolves) — this satisfies Task 6's "committed real-shape fixture" intent via the stronger golden-writer-model approach used consistently across the adapter unit tests and the new Playwright integration test.
- Zero wire-format change: `/state.json` is still read byte-for-byte by `routes/state.py`; the new `/api/backlog` route is an entirely separate, additive read-only endpoint. Freeze stays 7/7.

### File List

- `src/sdlc/dashboard/routes/backlog.py` (new) — pure nesting adapter (`build_backlog_tree`) + `GET /api/backlog` route registration
- `src/sdlc/dashboard/server.py` (modified) — registers `register_backlog_route`
- `scripts/module_boundary_table.py` (modified) — `dashboard.depends_on` += `ids` (corrective amendment, justified above)
- `src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.js` (modified) — D4 empty-state early-return (`renderEmptyBacklogRow`); render/keyboard/a11y internals otherwise untouched (frozen)
- `src/sdlc/dashboard/static/components/backlog-tree/backlog-tree.css` (modified) — `.backlog-tree__empty` styling (`var(--*)` tokens only)
- `src/sdlc/dashboard/static/components/backlog-tree/backlog-tree-live.js` (new) — real-hierarchy poller (`/api/backlog`, 3 s cadence) + URL-hash expand/collapse persistence (D3)
- `src/sdlc/dashboard/static/components/backlog-tree/backlog-tree-live.fixture.html` (new) — real-data fixture page mounting the poller
- `src/sdlc/dashboard/static/components/pills/pills.js` (modified) — D5 `createFlowPillGroup` fallback pill for unknown flow steps
- `pyproject.toml` (modified) — `force-include` entries for the two new `backlog-tree-live.*` static files
- `tests/unit/dashboard/test_backlog_hierarchy_adapter.py` (new) — golden-fixture + malformed/orphan-tolerance + canonical-id-regex + status-derivation + numeric-0 + `currentTaskId` unit tests for `build_backlog_tree`
- `tests/unit/dashboard/test_backlog_route.py` (new) — `GET /api/backlog` HTTP route unit tests (reachability, content-type, D1 state.json-independence)
- `tests/unit/dashboard/test_backlog_tree_live_source.py` (new) — static-source contract tests for `backlog-tree-live.js` (poll cadence, `/api/backlog` seam, no click/keydown rewiring, `MutationObserver`/`childList` usage, hash grammar, Story-1.6-mirrored regex shape, D4/D5 fold markers)
- `tests/integration/test_dashboard_backlog_tree_live.py` (new) — Playwright tests: real-hierarchy canonical-id rendering, URL-hash write/read-on-reload/collapse-removal/injection-safety, empty-backlog Tab-reachability, unknown-flow-step fallback pill

## Change Log

- 2026-07-02: Implementation complete (dev-story) — D1-D5 ratified and implemented (see Completion Notes above); `GET /api/backlog` route + pure Python nesting adapter (`routes/backlog.py`) reading the real 2A.11 `04-Epics`/`05-Stories`/task artifact tree (never `/state.json`, never `dashboard → engine/cli`); FROZEN 5.10 `renderBacklogTree` fed the real nested shape unmodified (render/keyboard/a11y internals untouched); D4 empty-state (`backlog-tree.js`/`.css`) + D5 flow-pill fallback (`pills.js`); new `backlog-tree-live.js` poller (mirrors `phase-tracker-live.js`, 3 s cadence) adds URL-hash expand/collapse persistence (`#backlog=<ids>`) via a `MutationObserver` on `childList` (no click/keydown rewiring), injection-safe against the Story 1.6 canonical regex shape. Module-boundary amendment: `dashboard` gains `ids` as an allowed dependency (corrective, zero cyclic-risk). Full test suite: 4183 passed, coverage 88.57% (≥87%); ruff/mypy --strict/mkdocs --strict all green; wire-format freeze stays 7/7. Status: review.
- 2026-07-01: Story 5.15 created (create-story, "flip done 5.12 + tạo all US cho layer tiếp theo" → L6/5B batch-1) — 1:1 real-data swap of the FROZEN 5.10 backlog-tree onto the real Epic→Story→Task hierarchy: (Task 1/2) pure nesting adapter from real state.json records via the `state`/`journal` reader seam, reconstructing the nest by parsing canonical ids; (Task 3) canonical-id inline-code per Story 1.6 (`src/sdlc/ids/parsers.py`); (Task 4) new **URL-hash expand/collapse persistence** for shareability (5.10 had none); (Task 5) real-data edge handling — empty/zero-epic empty-state + Tab-reachability (DEF-3), unknown flow-step (DEF-5), numeric-0 count. Decisions raised: **D1 (real hierarchy source + the state.json projection gap — WAVE-BOUNDARY; 2A.11 emits the hierarchy as the 04-Epics/05-Stories artifact tree, projection reserves story-/task-)**, D2 (flat→nested adapter by canonical-id parse), D3 (URL-hash grammar + injection-safety), D4 (empty-state + numeric-0), D5 (unknown flow-step). L6 (5B) batch-1 with 5.14/5.16/5.18; twin 5.10 (done); external gate E2A (2A.11 done+merged + 1.6 id regex); a11y rides the 5.10 twin → 5.12 (done) + 5.22; CONTRIBUTING §7.4 N/A (not Story N.1). Synthetic render seam FROZEN — swap the data source only; do-not-build real signoff (5.14) / feed (5.16) noted. Zero wire-format change → freeze stays 7/7. Status: ready-for-dev.

## Review Findings

> bmad-code-review (fresh-context, 3 adversarial layers — Blind Hunter / Edge Case Hunter / Acceptance Auditor @ Opus-4.8; all findings verified against worktree source). 2026-07-02. 16 raw → 14 unified (3 merges + 1 split); 6 dismissed. Surviving: 2 decision-needed, 3 patch, 3 defer.

**Decision-needed (resolve before patches):**

- [x] [Review][Decision] **RESOLVED 2026-07-02 → accept D1(a)** (PO to acknowledge the reinterpretation at signoff; real-hierarchy intent delivered, no code change). AC1 "hierarchy matches state.json byte-for-byte" reinterpreted by D1(a) — the route reads the `04-Epics`/`05-Stories`/tasks artifact tree (not `state.json`, whose stories/tasks stay empty per projection.py:27-28) and *derives* `status`/`pct`/`meta`/`currentTaskId` rather than copying anything byte-for-byte. D1(a) was ratified pre-coding, but the AC wording is not literally met/meetable; needs explicit PO acceptance that D1(a) supersedes it. [src/sdlc/dashboard/routes/backlog.py:256-278; tests/unit/dashboard/test_backlog_route.py::test_route_never_reads_state_json_for_the_hierarchy] (auditor)
- [x] [Review][Decision] **RESOLVED 2026-07-02 → accept as ratified D1(a) dashboard-side reader** (route imports neither engine nor cli, no wire re-parse; direct artifact-tree read is within D1(a)'s authorized scope; no code change). Hierarchy read bypasses the state/journal reader seam via direct artifact-tree file-glob — Task 1 requires sourcing "through the existing `state`/`journal` reader seam"; the route imports neither and does raw `Path.glob`+`json.loads` on the CLI-owned artifact tree. `check_module_boundaries.py` is AST-only and cannot see this filesystem-level coupling to 2A.11's on-disk layout. Decide: accept as the ratified D1(a) "dashboard-side reader", or require a `state`/`journal` reader abstraction. [src/sdlc/dashboard/routes/backlog.py:38-50,72-147] (auditor)

**Patch (unchecked):**

- [x] [Review][Patch] **FIXED 2026-07-02** (`_ordering_key` coerces non-int → 0; regression `test_non_int_ordering_does_not_crash_the_whole_endpoint`). Non-int `ordering` raises `TypeError` and crashes the entire `/api/backlog` — `out.sort(key=lambda e: (e.get("ordering", 0), e["id"]))` compares a bad `ordering` (`null`→`None`, or a string) against the int default across epic files → `TypeError` propagates through the unguarded handler; one bad epic file kills the whole tree, violating the file's own "malformed skipped, never raised (D5)" contract, and the poller's `catch{}` turns it into a silent false-green board. [src/sdlc/dashboard/routes/backlog.py:84] (blind+edge)
- [x] [Review][Patch] **FIXED 2026-07-02** (`_story_status` now takes `in_progress_count`; returns `in-progress` when any task is started; regressions `test_story_with_started_but_zero_done_tasks_is_in_progress_not_pending` + `test_story_with_all_pending_tasks_is_pending`). Story with 0 done but in-progress tasks renders a "pending" status pill — `_story_status` returns `"pending"` when `done_count == 0`, so any mid-flight story (tasks in `write-tests`/`write-code`/`review`, none `done`) shows as not-started while its child task pills show `in-progress`. Reachable by real data; fix must treat "any task started" as `in-progress`. [src/sdlc/dashboard/routes/backlog.py:178-181] (edge)
- [x] [Review][Patch] **FIXED 2026-07-02** (`Array.isArray` guard + `Object.hasOwn` lookup in `createFlowPillGroup`; defense-in-depth — behavior for real data unchanged, covered by the existing unknown-flow Playwright test). `createFlowPillGroup` lookup is prototype-unsafe + unguarded on non-array — `PILL_FLOW_VARIANTS[key]` resolves inherited `Object.prototype` members (a flow step named `constructor`/`toString`/`valueOf` → truthy → skips the D5 fallback → broken `undefined` pill); `for (const step of steps)` throws on a truthy non-array `flow`. Currently unreachable by real data (adapter emits no `flow`), so defense-in-depth in the new D5 code — use `Object.hasOwn` + `Array.isArray`. [src/sdlc/dashboard/static/components/pills/pills.js:76-78] (blind+edge)

**Defer (pre-existing / not actionable now):**

- [x] [Review][Defer] Poll `fetch` has no `AbortController`; in-flight request not cancelled on teardown [src/sdlc/dashboard/static/components/backlog-tree/backlog-tree-live.js:86,160] — deferred, low-severity consistency (the `disposed` guard already prevents a stale render, so correctness-safe; matches the 5.14 P3 AbortController precedent — apply when 5.14's pattern is generalized). (blind)
- [x] [Review][Defer] Duplicate canonical ids across artifact files produce duplicated subtrees / ambiguous roving focus (no dedup in the adapter) [src/sdlc/dashboard/routes/backlog.py:83,144] — deferred, low-probability (requires a stray duplicate artifact file; the 2A.11 writer emits one file per canonical id). (edge)
- [x] [Review][Defer] Silent false-empty board — a missing/moved/broken artifact tree yields `{epics:[]}` → the "No epics yet" empty-state, indistinguishable from a legitimately fresh empty project (same class as 5.14 DEF-4) [src/sdlc/dashboard/routes/backlog.py:73,133] — deferred, DEF-4 class → owned by Story 5.20 (client-visible error on repeated poll/read failure). (auditor)

**Dismissed (6, verified false/handled):** Blind #1 `data-node-id` (false positive — the frozen `renderEpic`/`renderStory` DO emit `role="treeitem"`+`aria-expanded`+`dataset.nodeId` at backlog-tree.js:171/175/181,235/239/240, so the hash round-trip works — confirmed by the Playwright reload test); poll-bounce-on-collapse (MutationObserver microtask flushes before the next `setInterval` tick → unreachable); whole-hash overwrite + single-key read (no other dashboard component uses `location.hash`; single-key `#backlog=` is the ratified D3 grammar); task-id-in-hash silently stripped (harmless — tasks are leaves, never expandable); static-source grep tests (behavioral coverage exists in the Playwright integration test; the static-source mirror is the sanctioned epic-wide supplement pattern, and `test_hash_id_regexes_mirror_story_1_6_canonical_shape` is genuinely valuable); D5 flow-pill fallback is dead code for real data (accurately disclosed in Completion Notes as forward-compat).
