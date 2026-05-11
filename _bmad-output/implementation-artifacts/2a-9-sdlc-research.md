# Story 2A.9: `/sdlc-research <topic>`

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a tech lead requesting deeper research on a focused topic during Phase 1,
I want `/sdlc-research "<topic>"` to dispatch the `technical-researcher` specialist (primary-only, no panel) through the dispatcher (Story 2A.3) and the pre-write hook chain (Story 2A.4) under the Claude PreToolUse bridge (Story 2A.6), producing a stand-alone research artifact at `01-Requirement/02-Research/<slug>.md` with a deduplicating `-N` suffix on re-runs and topic + timestamp recorded in the artifact's frontmatter,
So that focused topical research is preserved as a discrete, audit-grade Phase-1 artifact (FR7), prior research is never overwritten, and every invocation produces a journaled `agent_dispatched` + `artifact_written` pair with NFR-SEC-3 boundary-line-bearing prompts (inherited from Story 2A.8's `phase1_prompt_builder`).

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1193-1210`. Per ADR-026 §1, the public API surface (`cli/research.py:run_research`, slug derivation function `_slugify_topic`, deduplicating-suffix algorithm `_next_research_path`) requires TDD-first commit ordering visible in `git log --reverse`. This story **inherits** the `phase1_prompt_builder` + `BOUNDARY_LINE` from Story 2A.8 (Task 1) and the specialist stub posture from Story 2A.8 (AC8/D2). It introduces no new wire-format contracts (ADR-024 snapshot count remains 5). The `/sdlc-research` slash command has **no workflow YAML** per architecture `architecture.md:956-962` (canonical tree lists `workflows_yaml/sdlc-start.yaml`, `sdlc-epics.yaml`, `sdlc-stories.yaml`, `sdlc-ux.yaml`, `sdlc-architect.yaml`, `sdlc-task.yaml` — but NOT `sdlc-research.yaml`) — see AC1/D1 for the D-decision.

### AC1 — Workflow surface choice: D-decision on YAML vs primary-only-CLI-arg path

**Given** the architecture's canonical tree at `architecture.md:956-962` ships workflow YAMLs only for orchestrating slash commands that use the dispatcher's panel path; `/sdlc-research` is single-specialist + topic-as-arg and is NOT listed
**When** the dev considers the workflow surface
**Then** **AC1/D1 (workflow YAML D-decision)**: ONE of the following is delivered:
  - **D1:** Ship a minimal `workflows_yaml/sdlc-research.yaml` with `parallel_agents: ()` + `synthesizer_agent: None` so that the dispatcher's `dispatch(...)` primary path (NOT `dispatch_panel`) is invoked through `WorkflowRegistry`-mediated lookup. **Pros**: uniform CLI surface; every slash command goes through the registry; the static-check + disjoint-writes check runs uniformly. **Cons**: a 2-line YAML adds ceremony for a single-specialist dispatch; mismatches architecture's canonical-tree omission
  - **D2:** Skip the YAML entirely; `cli/research.py:run_research` constructs a synthetic `WorkflowSpec` in-memory and calls `dispatcher.dispatch(...)` directly. **Pros**: matches architecture's omission; less ceremony. **Cons**: the slash command can't be discovered via `WorkflowRegistry.list()` (Story 2A.1 surface); inconsistent with `/sdlc-start`
  - **D3:** Ship the YAML AND tag it with a `single_specialist: true` semantic marker (NEW field on `WorkflowSpec`); update the contract. **Pros**: explicit intent. **Cons**: bumps `WorkflowSpec` schema → ADR-024 ceremony → 5 → 6 contract snapshots; too heavy for this story

**And** **Recommended: D1** — preserves the `WorkflowRegistry` discovery contract; matches Story 2A.8's pattern; the 2-line YAML cost is negligible
**And** if D1 is chosen, `src/sdlc/workflows_yaml/sdlc-research.yaml` is authored with this exact body:

```yaml
schema_version: 1
name: phase1-topic-research
slash_command: /sdlc-research
primary_agent: technical-researcher
parallel_agents: []
synthesizer_agent: null
postconditions:
  - research_md_exists
  - boundary_line_present_in_prompts
write_globs:
  technical-researcher:
    - "01-Requirement/02-Research/*.md"
stop_on_postcondition_failure: true
```

**And** the WorkflowSpec contract permits `parallel_agents: ()` + `synthesizer_agent: None` (verify against `src/sdlc/contracts/workflow_spec.py:12-25` — `parallel_agents: tuple[str, ...] = ()` is the default; `synthesizer_agent: str | None = None`). If `dispatch_panel(...)` rejects a spec with no parallel/synthesizer (i.e., it only supports panel topology), then **the CLI uses `dispatch(...)` (single dispatch) instead** — verify against Story 2A.3 AC2 which documents `dispatch` as the single-specialist primary entry point
**And** whichever option is chosen, the choice MUST be the FIRST line item in the PR's "Change log" section: `D-decision: AC1/D1 chose D<n> because <one-line reason>`

### AC2 — Single dispatch wiring (`technical-researcher` primary)

**Given** the dispatcher public surface at `src/sdlc/dispatcher/__init__.py:19-27` (`dispatch` for primary single-specialist, `dispatch_panel` for panel)
**When** the dev wires `/sdlc-research`
**Then** `src/sdlc/cli/research.py:run_research` (NEW) calls `dispatch(...)` per `dispatcher/core.py:94-107` signature:

```python
result: DispatchResult = await dispatch(
    step=spec,                                # from registry.get("/sdlc-research") per AC1/D1
    runtime=runtime,                          # MockAIRuntime for v1; ClaudeAIRuntime in 2B.1
    registry=specialist_registry,
    repo_root=root,
    journal_path=root / ".claude/state/journal.log",
    agent_runs_path=root / "03-Implementation/agent_runs.jsonl",
    prompt_builder=_research_prompt_builder,  # NEW: thin wrapper that bridges to phase1_prompt_builder per AC4
    hooks=build_pre_write_hook_chain(repo_root=root),
)
```

**And** the single-dispatch retry policy (1+2 retries at 1s/4s exp backoff per Story 2A.3 AC4) is inherited unchanged via `with_retries`; this story does NOT override
**And** the pre-write hook chain is constructed via `build_pre_write_hook_chain(repo_root=root)` and passed explicitly via the `hooks` arg (the panel path passes hooks transitively through `dispatch_panel`; the single-dispatch path requires the caller to pass them). Verify against `dispatcher/__init__.py:9` exported `build_pre_write_hook_chain` and Story 2A.7 AC7's DI wiring
**And** `result.outcome` ∈ `{"success", "failed", "hook_rejected"}`; exit code 0 only on `"success"` (mirror Story 2A.8 AC2 + `cli/scan.py:137-143` `emit_error` pattern)

### AC3 — Slug derivation + deduplicating suffix

**Given** the AC source's second-Given: "When I run the same `/sdlc-research \"PCI compliance scope\"` again, a new file with a deduplicating suffix (e.g., `-2.md`) is created; prior research is not overwritten"
**When** the dev implements the path-derivation logic
**Then** `src/sdlc/cli/research.py` exposes two helper functions:

```python
def _slugify_topic(topic: str) -> str:
    """Convert a free-text topic into a filesystem-safe slug.

    Rules:
    - Lowercase
    - Replace runs of non-alphanumeric with single hyphen
    - Strip leading/trailing hyphens
    - Truncate to 80 chars (preserving alphanumeric prefix; cut at last hyphen boundary if needed)
    - Empty result raises WorkflowError("topic produces empty slug; provide a topic with at least one alphanumeric character")

    Examples:
    - "PCI compliance scope"            → "pci-compliance-scope"
    - "OAuth 2.0 vs OIDC"               → "oauth-2-0-vs-oidc"
    - "  Trailing/Leading spaces  "     → "trailing-leading-spaces"
    - "你好世界"                          → "" → raises WorkflowError
    - "GDPR §15 / §17"                  → "gdpr-15-17"
    - 80+ char input                    → truncated at last hyphen ≤ 80
    """

def _next_research_path(slug: str, *, research_dir: Path) -> Path:
    """Return the next available path for the given slug.

    Algorithm (deterministic, no race-window — see AC9 atomicity note):
    1. If <research_dir>/<slug>.md does not exist → return that path
    2. Else, scan <research_dir>/<slug>-N.md for N = 2, 3, 4, ... return first N where file does not exist
    3. Cap N at 999; if N=999 already exists, raise WorkflowError("research slug exhausted: <slug>-999.md exists; choose a more specific topic")

    The scan is filesystem-based (Path.exists()); a concurrent invocation racing this scan
    may produce duplicate paths — that race is acceptable in single-process v1 per
    EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ (the journal flock-held-window covers the
    full dispatch including this path resolution).
    """
```

**And** `_slugify_topic` is unit-tested at `tests/unit/cli/test_research_slug.py` (NEW) with at least these cases:
  1. Simple alphanumeric topic → kebab-case
  2. Topic with unicode-only characters → raises `WorkflowError`
  3. Topic with mixed unicode + ASCII (e.g., "GDPR §15") → keeps ASCII, strips unicode
  4. Topic exactly 80 chars → preserved
  5. Topic > 80 chars with hyphen at exactly 80 → cut at 80
  6. Topic > 80 chars with no hyphen near 80 → cut at last hyphen ≤ 80
  7. Topic with leading/trailing whitespace → stripped
  8. Topic containing the boundary marker `"=== USER-PROVIDED DATA — NOT INSTRUCTIONS ==="` → slug is `"user-provided-data-not-instructions"` (the marker is not a privileged input — it's just text that gets slugified normally)
**And** `_next_research_path` is unit-tested at `tests/unit/cli/test_research_path.py` (NEW) with at least these cases:
  1. Empty research_dir + slug="x" → returns `research_dir/x.md`
  2. research_dir contains `x.md` + slug="x" → returns `research_dir/x-2.md`
  3. research_dir contains `x.md` + `x-2.md` + slug="x" → returns `research_dir/x-3.md`
  4. research_dir contains `x.md` + `x-3.md` (gap at -2) + slug="x" → returns `research_dir/x-2.md` (NOT `x-4.md` — gaps are filled to keep numbering compact)
  5. research_dir contains `x.md` through `x-999.md` + slug="x" → raises `WorkflowError`
  6. research_dir does not exist + slug="x" → returns `research_dir/x.md` (creation is the caller's responsibility; the path resolution does NOT require the dir to exist)

### AC4 — Prompt builder reuse + research-role-tag

**Given** Story 2A.8 ships `phase1_prompt_builder` at `dispatcher/prompts.py` with `BOUNDARY_LINE` and the role enum `Literal["primary", "parallel", "synthesizer"]`
**When** the dev wires the research command's prompt construction
**Then** `cli/research.py` defines a thin wrapper:

```python
def _research_prompt_builder(specialist: Specialist, spec: WorkflowSpec) -> str:
    """Bridge dispatcher's (specialist, spec) signature to phase1_prompt_builder.

    The topic text is bound via closure at run_research time (since dispatcher's
    prompt_builder signature is (Specialist, WorkflowSpec) -> str — it has no
    user-input slot). The closure captures the validated topic for the role='primary' call.
    """
    return phase1_prompt_builder(
        specialist=specialist,
        spec=spec,
        idea_text=_topic_for_this_dispatch,  # closure-bound — see Task 4.2
        role="primary",
        upstream_outputs=(),
    )
```

**And** the `idea_text` parameter of `phase1_prompt_builder` carries the topic text verbatim — the boundary-block protects against `<USER_IDEA>`-prefixed prompt-injection same as Story 2A.8
**And** the closure-capture pattern is justified because `dispatcher.dispatch(...)` accepts a `prompt_builder` callable of signature `(Specialist, WorkflowSpec) -> str` (per `dispatcher/core.py:104`). The CLI command captures the topic at `run_research` entry and binds it via a local function or `functools.partial(phase1_prompt_builder, idea_text=topic, role="primary", upstream_outputs=())`. Document the closure capture in `cli/research.py`'s module docstring
**And** **Anti-tautology receipt #1 (mandatory)**: in the integration test of Task 5, temporarily replace the `idea_text=topic` closure with `idea_text="DIFFERENT_TOPIC"`; assert the integration test's prompt-text assertion FAILS (because the recorded prompt no longer contains the topic); revert; document in PR Change Log

### AC5 — Artifact frontmatter shape + write semantics

**Given** the Story 2A.8 frontmatter pattern (top-level keys `schema_version`, `kind`, `idea`, `drafted_at`, `drafted_by_specialists` on `01-PRODUCT.md`)
**When** the dev writes the research artifact
**Then** the file at `01-Requirement/02-Research/<slug>.md` (or `<slug>-N.md` per AC3) is written with:

```markdown
---
schema_version: 1
kind: research
topic: <topic text verbatim from CLI arg>
slug: <slug from _slugify_topic>
researched_at: <RFC 3339 UTC ms with Z suffix>
researched_by_specialist: technical-researcher
---

# <slug as title-cased H1>

<specialist output body — verbatim from technical-researcher's AgentResult.output_text>
```

**And** the `topic:` field carries the verbatim user-supplied topic — YAML-escaped if it contains characters that would break YAML parsing (single quotes wrapping; or use a literal block scalar `topic: |\n  <text>` if multiline). Verify byte-stability via a test that writes + reads + asserts the topic field round-trips bit-exact
**And** the artifact's `researched_at` timestamp is generated via `cli/_time.py:now_rfc3339_utc_ms` (same as Story 2A.8 + `cli/scan.py:20`)
**And** the file is written via the dispatcher's inherited `Path.write_text(...)` path per `EPIC-2A-DEBT-WRITE-PRIMITIVE` — same posture as Story 2A.8 AC3 (the debt is re-cited in this story's PR Change Log)
**And** if the SYNTHESIZER agent is `null` per AC1/D1's YAML, the `dispatch(...)` path writes the primary's output DIRECTLY to the resolved write_path — there is no consolidation step (no panel; no synthesizer). The frontmatter is prepended by the dispatcher's write-path logic OR by the specialist's prompt output (D-decision)

### AC6 — Frontmatter authorship D-decision (specialist vs CLI wrapper)

**Given** the choice of WHO writes the frontmatter — the specialist (LLM-generated as part of `AgentResult.output_text`) or the CLI command (post-dispatch wrapping of the raw specialist output)
**When** the dev wires the artifact write
**Then** **AC6/D2 (frontmatter authorship D-decision)**: ONE of the following is delivered:
  - **D1:** Specialist generates the frontmatter as part of its output. The prompt instructs the specialist to begin its response with the YAML block. **Pros**: single bytestream from specialist → file; no post-processing. **Cons**: LLM authorship of structured YAML is non-deterministic; the specialist may format the date wrong, omit fields, or hallucinate fields; tests must defend against this; impacts adopt-mode (Epic 3) imported research
  - **D2:** CLI wraps. The CLI post-dispatch reads the specialist's raw output, prepends a deterministic frontmatter block (constructed in Python with the topic from the CLI arg, the timestamp from `now_rfc3339_utc_ms`, the slug, and the specialist name), and writes the combined bytestream. **Pros**: frontmatter is byte-stable and CLI-controlled; the specialist focuses on the body; future verification (Story 2A.10) reliably parses the frontmatter. **Cons**: requires a post-write hook seam OR a pre-write wrap in the dispatch path
  - **D3:** Hybrid — specialist outputs the body only; CLI wraps; specialist's prompt includes an explicit instruction to NOT output a YAML frontmatter ("do not begin your response with `---`"). **Pros**: combines D1+D2 strengths. **Cons**: depends on LLM compliance with prompt instructions; weaker than D2

**And** **Recommended: D2** — frontmatter is structured data; CLI authorship guarantees byte-stability + future-tool compatibility (Story 2A.10 `/sdlc-verify` reads this frontmatter); the specialist focuses on the body
**And** if D2 is chosen, the CLI wraps the dispatch via a `_wrap_research_artifact(raw_body: str, *, topic: str, slug: str, ts: str) -> str` helper at `cli/research.py`; the helper is unit-tested at `tests/unit/cli/test_research_wrap.py` (NEW) with: byte-stability across two calls with the same inputs; topic with YAML-special characters (`'`, `"`, `:`, `\n`) round-trips correctly; H1 heading is the slug title-cased; trailing newline always present
**And** the wrapping happens INSIDE the dispatcher's write seam by REGISTERING a wrap callback OR by EXTRACTING the dispatcher write path into the CLI — both are heavyweight. The pragmatic approach: the CLI command issues `dispatch(...)`, captures the resulting `DispatchResult`, and IF success → re-reads the on-disk artifact, prepends the frontmatter, and re-writes (yes, this double-writes; non-atomic; cited as inherited debt). Document this two-step wrap explicitly in `cli/research.py`'s module docstring with the line: `NOTE: dispatcher writes the body; CLI re-writes with frontmatter prepended. Non-atomic — inherits EPIC-2A-DEBT-WRITE-PRIMITIVE.`
**And** the CLI's re-write step MUST happen BEFORE the `artifact_written` journal entry is appended — the journal's `after_hash` is computed against the FINAL (frontmatter-prepended) on-disk bytes. The dispatcher's internal `artifact_written` write may emit a journal entry with the pre-frontmatter hash; the CLI's re-write phase must INVALIDATE that and emit a corrected entry. **D-decision opportunity (AC11/D1)**: either (a) double-journal (one with body-only hash, one with frontmatter-included hash; clutter), or (b) suppress the dispatcher's internal `artifact_written` for `/sdlc-research` and emit a single journal from the CLI. Recommended: (b) — pass a `suppress_internal_journal=True` flag to `dispatch(...)` (NEW arg on dispatcher; coordinate with Story 2A.3 owner if needed) OR (c) accept the double-journal as the v1 cost and file a debt ticket for v1.x consolidation

### AC7 — Journal entries (`agent_dispatched` + `artifact_written`)

**Given** the journal kinds enumerated by Story 2A.8 AC4 (`agent_dispatched` + `artifact_written` + transient `dispatch_attempt`)
**When** `/sdlc-research <topic>` runs to completion
**Then** the journal contains, in monotonic order:
  1. Exactly ONE `kind="agent_dispatched"` entry: `actor="agent:technical-researcher"`, `target_id="01-Requirement/02-Research/<slug>.md"` (or `<slug>-N.md`), `before_hash=None`, `after_hash="sha256:" + "0"*64` (sentinel), `payload={"slash_command": "/sdlc-research", "specialist": "technical-researcher", "role": "primary", "attempt": N, "topic_hash": "sha256:<64hex of topic text>", "slug": "<slug>"}`
  2. Zero or more `kind="dispatch_attempt"` entries per Story 2A.3 retry policy
  3. Exactly ONE `kind="artifact_written"` entry on success (after CLI re-write per AC6 — single emission per AC6/D1/b): `actor="cli"`, `target_id="01-Requirement/02-Research/<slug>.md"`, `before_hash=None`, `after_hash="sha256:<64hex of final on-disk bytes including frontmatter>"`, `payload={"slash_command": "/sdlc-research", "phase": 1, "specialist": "technical-researcher", "topic_hash": "sha256:<64hex>", "research_seq": N}` where `research_seq` is the suffix integer (1 for first, 2 for `-2.md`, etc.) — useful for `sdlc trace` correlation
**And** the same `EPIC-2A-DEBT-JOURNAL-NULL-AFTER-HASH` and `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` posture from Story 2A.8 AC4 is inherited (cite in PR Change Log)
**And** the `topic_hash` field is `sha256:<hex of UTF-8 encoded topic text bytes>` — NOT for security; audit-trail correlation tag (same posture as Story 2A.8's `idea_hash`)

### AC8 — Pre-flight check: phase 1 entry permitted

**Given** the phase_gate hook (Story 2A.4) enforces that `01-Requirement/` writes require the project to be in phase 1 (or transitioning from phase 0)
**When** `/sdlc-research` runs
**Then** the CLI command performs pre-flight checks BEFORE calling `dispatch(...)`:
  1. State.json exists (per `cli/scan.py:127`); if not → `emit_error("ERR_NOT_INITIALIZED", "no .claude/state/state.json found; run 'sdlc init' first", ctx=ctx)`
  2. State.json projects `phase: 1` (NOT 0, 2, or 3); if phase != 1 → `emit_error("ERR_PHASE_MISMATCH", "phase 1 required for /sdlc-research; current phase: <N>", ctx=ctx, details={"current_phase": N})`. Phase 0 is NOT permitted — the user must run `/sdlc-start` first to transition into phase 1. This is stricter than Story 2A.8's pre-flight (which allows phase 0 → 1 transition); the asymmetry is intentional because `/sdlc-research` is a SUPPLEMENTARY artifact, not a phase-entry artifact
  3. The research dir exists OR will be created on first write (`mkdir(parents=True, exist_ok=True)` at the path resolved by `_next_research_path`)
**And** `cli/research.py:run_research` returns BEFORE calling `dispatch(...)` if any pre-flight check fails; no journal entries are appended in that case
**And** the pre-flight checks are unit-tested at `tests/unit/cli/test_research_preflight.py` (NEW) with: uninitialized repo → ERR_NOT_INITIALIZED; phase 0 → ERR_PHASE_MISMATCH; phase 2 → ERR_PHASE_MISMATCH; phase 3 → ERR_PHASE_MISMATCH; phase 1 + clean state → proceeds to dispatch (mocked)

### AC9 — Atomicity caveat + race-window note

**Given** the algorithm in AC3's `_next_research_path` uses a scan-and-pick-first-gap approach
**When** two `/sdlc-research <same-topic>` invocations race in different processes
**Then** they MAY resolve to the same path (both see `<slug>.md` exists; both pick `<slug>-2.md`); the second write overwrites the first — this is a known v1 limitation
**And** the v1 mitigation is the existing journal flock window: the CLI holds the journal flock from `pre_state = read_state_or_recover(...)` through `append_sync(...)` — but this DOES NOT cover the path-resolution step which happens BEFORE the dispatch is initiated. So concurrent `/sdlc-research <same-topic>` IS racey in v1
**And** the file `cli/research.py`'s module docstring carries this explicit warning: `Concurrency caveat: two simultaneous /sdlc-research invocations with the same topic may collide on the deduplicating suffix in v1. The journal flock covers the dispatch window but not the path resolution. v1.x: tighten via flock-on-research-dir.` and a NEW debt entry `EPIC-2A-DEBT-RESEARCH-DEDUP-RACE` is added to `deferred-work.md` referencing Story 4.x or v1.x as the consumer
**And** the unit tests for `_next_research_path` (AC3) cover the single-process happy path only; the race is NOT tested in v1 (race testing belongs in chaos tests; out of scope)

### AC10 — Module structure + LOC caps

**Given** the existing repo layout
**When** the dev introduces the new modules
**Then** the new layout is:

```
src/sdlc/cli/
└── research.py                           # NEW — run_research + _slugify_topic + _next_research_path + _wrap_research_artifact + _research_prompt_builder (≤ 350 LOC)

src/sdlc/cli/main.py                      # UPDATE — register `research_command`

src/sdlc/workflows_yaml/
└── sdlc-research.yaml                    # NEW per AC1/D1 (recommended)

src/sdlc/commands/
└── sdlc-research.md                      # NEW — slash-command shell (mirror Story 2A.8 AC9 body)

tests/unit/cli/
├── test_research_slug.py                 # NEW — _slugify_topic unit (≤ 200 LOC)
├── test_research_path.py                 # NEW — _next_research_path unit (≤ 200 LOC)
├── test_research_wrap.py                 # NEW — _wrap_research_artifact unit (≤ 150 LOC)
└── test_research_preflight.py            # NEW — pre-flight check matrix (≤ 200 LOC)

tests/unit/workflows/
└── test_phase1_workflows_present.py      # UPDATE (Story 2A.8) — add a test for sdlc-research.yaml load + WorkflowSpec shape

tests/integration/
└── test_sdlc_research.py                 # NEW — full dispatch with MockAIRuntime (≤ 250 LOC)

tests/e2e/pipeline/
├── fixtures/research/
│   ├── commands.yaml                     # NEW — Tier-2 fixture descriptor
│   ├── responses.yaml                    # NEW — MockAIRuntime canned response for technical-researcher
│   ├── workflow.yaml                     # NEW — fixture copy of sdlc-research.yaml
│   └── goldens/
│       └── journal.jsonl                 # NEW — normalized golden
└── test_sdlc_research.py                 # NEW — Tier-2 e2e (3 scenarios per AC11)

scripts/check_module_boundaries.py        # CONDITIONAL — `cli.depends_on` already updated by Story 2A.8 AC11/D2
```

**And** all new files respect Story 1.2 LOC caps; CLI files use deferred imports per Architecture §488; `cli/research.py` imports from `sdlc.dispatcher`, `sdlc.workflows`, `sdlc.specialists`, `sdlc.runtime`, `sdlc.journal`, `sdlc.state` — same surface as `cli/start.py` (no new boundary table edits beyond Story 2A.8 AC11/D2)

### AC11 — Tier-2 e2e (3 scenarios)

**Given** the Tier-2 e2e harness from Story 2A.0 + the pattern established by Story 2A.8 AC7
**When** the dev authors the research e2e
**Then** `tests/e2e/pipeline/test_sdlc_research.py` (NEW) drives three scenarios:
  1. **Happy path**: tmp repo at phase 1; invoke `sdlc research "PCI compliance scope"`; assert exit 0; assert `01-Requirement/02-Research/pci-compliance-scope.md` exists with correct frontmatter (`schema_version: 1`, `kind: research`, `topic: "PCI compliance scope"`, `slug: "pci-compliance-scope"`, `researched_at: <RFC 3339>`, `researched_by_specialist: technical-researcher`); assert journal contains 1 `agent_dispatched` + 1 `artifact_written`; assert prompts in `agent_runs.jsonl` contain `BOUNDARY_LINE`
  2. **Re-run dedup**: tmp repo with existing `01-Requirement/02-Research/pci-compliance-scope.md`; invoke `sdlc research "PCI compliance scope"` again; assert exit 0; assert NEW file `pci-compliance-scope-2.md` is created; assert ORIGINAL `pci-compliance-scope.md` is BYTE-UNCHANGED (read both files, diff, assert ORIGINAL preserved); assert journal has 1 NEW `artifact_written` for the `-2.md` path
  3. **Pre-flight: phase 0 refusal**: tmp repo at phase 0 (just `sdlc init`'d, no `/sdlc-start` run yet); invoke `sdlc research "topic"`; assert exit code 1; assert `ERR_PHASE_MISMATCH` is in stderr; assert NO new files created; assert NO new journal entries
**And** the e2e tests carry `@pytest.mark.e2e`; runtime budget ≤ 30 s per scenario
**And** **Anti-tautology receipt #2 (AC11 mandatory)**: in scenario 2 (re-run dedup), temporarily replace the assertion `assert original_bytes == reread_original_bytes` with `assert original_bytes != reread_original_bytes`; assert the test FAILS (this proves the dedup logic actually preserves the original — not just creates a new file alongside an overwritten original); revert; document in PR Change Log

### AC12 — Quality gate compliance (CONTRIBUTING.md §1)

**Given** the full Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests`
  - `pytest -q -m "not e2e and not property"` (unit + integration green; pre-existing baseline failures unchanged from `main`)
  - `pytest -q -m e2e` (existing Tier-1/2 + new Tier-2 from AC11 must pass; goldens regenerated if cli surface changes affect `sdlc init` etc.)
  - `pytest --cov=src --cov-report=term-missing --cov-fail-under=90` (≥ 90% repo-wide; module-level: ≥ 95% on `cli/research.py`; 100% on `_slugify_topic`, `_next_research_path`, `_wrap_research_artifact` pure helpers)
  - `pre-commit run --all-files`
  - `mkdocs build --strict`
  - `python scripts/freeze_wireformat_snapshots.py --check` — MUST still report `5 contracts match snapshots` (no contract churn; `WorkflowSpec` v1 reused unchanged; `JournalEntry.kind` open str field unchanged)
  - `python scripts/check_module_boundaries.py` — 0 new violations (Story 2A.8 AC11/D2 already updated the table to permit cli → dispatcher/workflows/specialists/runtime; this story inherits)
  - `python scripts/validate_specialists.py` — passes (`technical-researcher` registered by Story 2A.8 AC8)

## Tasks / Subtasks

> Tasks ordered to enable TDD-first commits per ADR-026 §1. AC1 + AC3 + AC5/AC6 + AC11 are the public-API surfaces requiring tests-first commit ordering visible in `git log --reverse`.

- [ ] **Task 1 — `_slugify_topic` + `_next_research_path` pure helpers (AC3)** — **TDD-first commit 1**
  - [ ] 1.1 Author `tests/unit/cli/test_research_slug.py` with all 8 cases from AC3. Tests fail (red).
  - [ ] 1.2 Author `tests/unit/cli/test_research_path.py` with all 6 cases from AC3. Tests fail (red).
  - [ ] 1.3 Implement `_slugify_topic(topic: str) -> str` at `src/sdlc/cli/research.py`. Use `re.sub(r'[^a-z0-9]+', '-', topic.lower()).strip('-')` for the core; handle the truncation-at-hyphen + 80-char cap explicitly. LOC ≤ 30 for this function.
  - [ ] 1.4 Implement `_next_research_path(slug: str, *, research_dir: Path) -> Path` per AC3. Scan with `Path.glob('<slug>*.md')` or a deterministic loop `for n in range(2, 1000): candidate = research_dir / f'{slug}-{n}.md'; if not candidate.exists(): return candidate`. Tests pass (green).

- [ ] **Task 2 — `_wrap_research_artifact` frontmatter wrap (AC5, AC6)** — **TDD-first commit 2**
  - [ ] 2.1 Author `tests/unit/cli/test_research_wrap.py` with byte-stability + YAML-special-character cases from AC6. Tests fail (red).
  - [ ] 2.2 Implement `_wrap_research_artifact(raw_body: str, *, topic: str, slug: str, ts: str) -> str` at `cli/research.py`. Construct frontmatter via `yaml.safe_dump({...}, sort_keys=True, default_flow_style=False, allow_unicode=True)`. Concatenate frontmatter + `'---\n'` separator + `'# ' + slug-title-cased + '\n\n'` + raw_body + trailing newline. LOC ≤ 40 for this function.
  - [ ] 2.3 Document the AC6/D1 D-decision choice (recommend D2 — CLI wraps) in PR Change Log.
  - [ ] 2.4 Document the AC6/D2 D-decision choice (recommend b — suppress dispatcher's internal `artifact_written`) — OR accept double-journal as v1 cost and file `EPIC-2A-DEBT-RESEARCH-JOURNAL-DOUBLE` debt. The choice MUST be the SECOND line item in PR Change Log. Tests pass (green).

- [ ] **Task 3 — `workflows_yaml/sdlc-research.yaml` + load test (AC1)** — **TDD-first commit 3**
  - [ ] 3.1 Extend `tests/unit/workflows/test_phase1_workflows_present.py` (created by Story 2A.8): assert `WorkflowRegistry.load(...)` discovers `sdlc-research.yaml`; assert `registry.get("/sdlc-research").primary_agent == "technical-researcher"`; assert `parallel_agents == ()`; assert `synthesizer_agent is None`. Tests fail (red).
  - [ ] 3.2 Author `src/sdlc/workflows_yaml/sdlc-research.yaml` per AC1/D1 (recommended) exact byte content.
  - [ ] 3.3 Verify `workflows/static_check.py` passes (single-specialist workflow with one glob; trivially disjoint). Tests pass (green).
  - [ ] 3.4 Document the AC1/D1 D-decision choice (recommend D1) in PR Change Log as the FIRST line item.

- [ ] **Task 4 — `cli/research.py` + Typer registration (AC2, AC4, AC8)** — **TDD-first commit 4**
  - [ ] 4.1 Author `tests/unit/cli/test_research_preflight.py` per AC8 (uninitialized; phase 0/2/3 refusal; phase 1 proceeds). Use mocked `dispatch(...)` to assert dispatch IS called only on the happy path. Tests fail (red).
  - [ ] 4.2 Implement `src/sdlc/cli/research.py:run_research(*, ctx, topic: str)`: deferred imports; pre-flight per AC8; load workflow + specialist registries; construct MockAIRuntime (v1); resolve path via `_next_research_path`; build the prompt-builder closure (`_research_prompt_builder`) that bridges to `phase1_prompt_builder` with `idea_text=topic, role="primary"`; call `dispatch(...)` per AC2 with `hooks=build_pre_write_hook_chain(...)`; on success, read the raw written body, prepend frontmatter via `_wrap_research_artifact`, re-write (cite AC6 double-write); emit_json on success with `{"phase": 1, "artifact": "<final path>", "specialist": "technical-researcher", "slug": "<slug>", "outcome": "success"}`. LOC ≤ 350.
  - [ ] 4.3 Update `src/sdlc/cli/main.py` to register the `research_command`:

    ```python
    @app.command(name="research")
    def research_command(
        ctx: typer.Context,
        topic: str = typer.Argument(..., help="The research topic"),
    ) -> None:
        """Phase 1 topic research (FR7)."""
        from sdlc.cli.research import run_research
        run_research(ctx=ctx, topic=topic)
    ```

  - [ ] 4.4 Author `src/sdlc/commands/sdlc-research.md` per Story 2A.8 AC9 body pattern. Tests pass (green).
  - [ ] 4.5 **Anti-tautology receipt #1 (AC4 mandatory)**: temporarily flip the closure binding `idea_text=topic` to `idea_text="DIFFERENT_TOPIC"`; assert the Task 5 integration test's prompt-text assertion FAILS; revert; document in PR Change Log.

- [ ] **Task 5 — Integration test: dispatch end-to-end (AC2, AC5, AC7)** — **TDD-first commit 5**
  - [ ] 5.1 Author `tests/integration/test_sdlc_research.py`: set up tmp repo at phase 1; populate fixture for `technical-researcher` specialist (reuse from Story 2A.8); construct MockAIRuntime with canned response; invoke `run_research(...)` directly; assert journal contains exactly 1 `agent_dispatched` + 1 `artifact_written`; assert artifact file exists with correct frontmatter (parse via `yaml.safe_load` and compare field-by-field); assert specialist body is present below `---` separator; assert prompt in `agent_runs.jsonl` contains `BOUNDARY_LINE` and the topic verbatim. Tests fail (red until Tasks 1-4 are merged).
  - [ ] 5.2 Drive green; verify `before_hash=None` + `after_hash="sha256:<actual>"` on the `artifact_written` entry computes against the FINAL (frontmatter-prepended) bytes per AC6.

- [ ] **Task 6 — Tier-2 e2e (AC11)** — **TDD-first commit 6**
  - [ ] 6.1 Author `tests/e2e/pipeline/test_sdlc_research.py` with the 3 scenarios from AC11.
  - [ ] 6.2 Author fixtures under `tests/e2e/pipeline/fixtures/research/` (commands.yaml, responses.yaml, workflow.yaml, goldens/journal.jsonl).
  - [ ] 6.3 Run `pytest -m e2e tests/e2e/pipeline/test_sdlc_research.py` — must pass green; runtime ≤ 30s per scenario.
  - [ ] 6.4 **Anti-tautology receipt #2 (AC11 mandatory)**: in scenario 2 (re-run dedup), temporarily replace `assert original_bytes == reread_original_bytes` with `assert original_bytes != reread_original_bytes`; assert FAIL; revert; document in PR Change Log.

- [ ] **Task 7 — Race-window debt + concurrency note (AC9)**
  - [ ] 7.1 Open `EPIC-2A-DEBT-RESEARCH-DEDUP-RACE` in `deferred-work.md` referencing v1.x or Story 4.x as the consumer per AC9.
  - [ ] 7.2 Add the concurrency caveat to `cli/research.py`'s module docstring per AC9.

- [ ] **Task 8 — Quality gate + Change Log (AC12)**
  - [ ] 8.1 Run all quality gate commands in AC12; all must pass green.
  - [ ] 8.2 Author the PR Change Log with the two D-decision lines (AC1/D1, AC6/D1 + AC6/D2) as the FIRST two-or-three items, followed by the two anti-tautology receipts, followed by the inherited-debt citations and the new debt opening.
  - [ ] 8.3 Set Story status `review`; sprint-status.yaml transition handled by `dev-story` skill.

## Dev Notes

### Source Hints
- Epic 2A AC source: `_bmad-output/planning-artifacts/epics.md:1193-1210`
- Dispatcher API: `src/sdlc/dispatcher/__init__.py:19-27`, `src/sdlc/dispatcher/core.py:94-107` (`dispatch` for primary-only path)
- Prompt builder: `src/sdlc/dispatcher/prompts.py` (introduced by Story 2A.8 — `phase1_prompt_builder` + `BOUNDARY_LINE`)
- WorkflowSpec contract: `src/sdlc/contracts/workflow_spec.py:12-25` (parallel_agents defaults to `()`, synthesizer_agent defaults to None)
- CLI pattern: `src/sdlc/cli/scan.py:19-87`, `src/sdlc/cli/start.py` (introduced by Story 2A.8)
- Pre-write hook chain: `src/sdlc/hooks/__init__.py:14-46`, `src/sdlc/dispatcher/__init__.py:9` (`build_pre_write_hook_chain`)
- Time: `src/sdlc/cli/_time.py:now_rfc3339_utc_ms`
- Paths: `src/sdlc/cli/_paths.py:get_repo_root_or_cwd`

### Previous Story Intelligence (Story 2A.8 done — sibling Layer 4)
- The `phase1_prompt_builder` + `BOUNDARY_LINE` constant is REUSED, not re-implemented. Closure-capture pattern bridges the `(Specialist, WorkflowSpec) -> str` dispatcher signature to the `(specialist, spec, idea_text, role, upstream_outputs)` signature of `phase1_prompt_builder`
- The specialist stub `technical-researcher.md` is authored by Story 2A.8 AC8/D2 (recommended). This story DEPENDS on Story 2A.8's stub registration via `agents/index.yaml`. Confirm at story start that the registration is on `main` (it should be — Story 2A.8 lands earlier in the Layer 4 batch)
- D-decision pattern: top of PR Change Log; clear-cut recommended option called out; choice locked at review

### Cross-Story Coordination
- Story 2A.8 (`/sdlc-start`) — must be done before this story (this story inherits `phase1_prompt_builder` + specialist stubs + workflow registry pattern). Both are Layer 4; coordinate merge order: 2A.8 → 2A.9 to avoid rebase pain on `cli/main.py` and `agents/index.yaml`
- Story 2A.10 (`/sdlc-verify`) — Layer 4 sibling. Operates on artifacts including those produced by `/sdlc-research`. Coordinates on frontmatter shape: this story locks `schema_version, kind, topic, slug, researched_at, researched_by_specialist`; 2A.10 appends `verifications: [...]` to this frontmatter
- Story 2A.11 (`/sdlc-epics` + `/sdlc-stories`) — Layer 4 sibling. Generates JSON artifacts. No direct cross-cutting concerns with 2A.9 beyond shared `phase1_prompt_builder` and pre-flight phase 1 check

### Project Structure Notes
- The `01-Requirement/02-Research/` directory does NOT exist at story start in a fresh repo. The CLI command creates it via `Path.mkdir(parents=True, exist_ok=True)` BEFORE the first `_next_research_path` call. This `mkdir` is OUTSIDE the phase_gate hook chain (phase_gate enforces writes, not directory creation per Story 2A.4 AC1 — verify against `hooks/builtin/phase_gate.py`). If phase_gate refuses directory creation, raise as a NEW D-decision (AC11/Dx) before merging
- The deduplicating suffix algorithm fills gaps (returns `-2.md` if `x.md` + `x-3.md` exist) — this is INTENTIONAL to keep numbering compact and prevent N=999 exhaustion on long-running projects with many research re-runs. If gap-filling is undesirable (e.g., for audit-chain-of-custody reasons), the algorithm becomes "return N = max_existing + 1" — D-decision-deferred for v1.x

### Inherited Debt (cited in PR Change Log)
- `EPIC-2A-DEBT-WRITE-PRIMITIVE` — `Path.write_text` non-atomic (re-cited from Story 2A.8)
- `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` — single-process monotonic_seq allocator (re-cited from Story 2A.8)
- `EPIC-2A-DEBT-JOURNAL-NULL-AFTER-HASH` — sentinel after_hash for `agent_dispatched` (re-cited from Story 2A.8)

### Opened Debt (this story)
- `EPIC-2A-DEBT-RESEARCH-DEDUP-RACE` (AC9) — multi-process race on `_next_research_path`; v1.x or Story 4.x owner
- Possibly: `EPIC-2A-DEBT-RESEARCH-JOURNAL-DOUBLE` (AC6/D2 alternative-c) — only if AC6 D-decision goes that way

### References
- [Source: `_bmad-output/planning-artifacts/epics.md:1193-1210`] — Story 2A.9 BDD ACs
- [Source: `_bmad-output/planning-artifacts/architecture.md:937-944,956-962,1052-1072,1136-1140`]
- [Source: `src/sdlc/dispatcher/__init__.py:19-27`, `src/sdlc/dispatcher/core.py:94-107`]
- [Source: `src/sdlc/dispatcher/prompts.py`] (introduced by Story 2A.8)
- [Source: `src/sdlc/workflows/registry.py:78-134`, `src/sdlc/workflows/loader.py:208`]
- [Source: `src/sdlc/specialists/__init__.py:21-32`]
- [Source: `src/sdlc/contracts/workflow_spec.py:12-25`]
- [Source: `src/sdlc/contracts/journal_entry.py:15-26`]
- [Source: `src/sdlc/cli/scan.py:19-87`, `src/sdlc/cli/main.py:87-92`]
- [Source: Story 2A.8 sibling story file `_bmad-output/implementation-artifacts/2a-8-sdlc-start-phase-1-entry.md`]
- [Source: ADR-026 §1] — TDD-first
- [Source: CONTRIBUTING.md §1-§5]

## Dev Agent Record

### Agent Model Used

(populated by `bmad-dev-story`)

### Debug Log References

(populated during implementation)

### Completion Notes List

(populated during implementation)

### File List

(populated during implementation)

## Change Log

(populated by `bmad-code-review` after review)
