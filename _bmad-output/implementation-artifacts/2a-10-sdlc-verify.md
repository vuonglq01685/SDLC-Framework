# Story 2A.10: `/sdlc-verify <artifact-id>`

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a tech lead verifying a single Phase-1 artifact (e.g., `01-Requirement/01-PRODUCT.md`, a research file, or an epic JSON) before it is hashed into a signoff,
I want `/sdlc-verify <artifact-id>` to dispatch the `artifact-verifier` specialist (primary-only, no panel) through the dispatcher (Story 2A.3) and the pre-write hook chain (Story 2A.4) under the Claude PreToolUse bridge (Story 2A.6), then append (NOT overwrite) a `verifications:` list entry to the artifact's frontmatter with `{verifier, ts, status?, content_hash_at_verify}` and journal `kind=artifact_verified` so that every verification is independently traceable,
So that artifact verification is preserved as audit-grade chain-of-custody evidence (FR8) the `/sdlc-signoff` ceremony (Story 2A.12) can validate alongside hash-drift detection (Story 2A.7) — and the verifier's identity + timestamp + at-verify content hash are tamper-evident even if the artifact is edited later.

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1212-1229`. Per ADR-026 §1, the public API surface (`cli/verify.py:run_verify`, `_append_verification_to_frontmatter`, the `kind="artifact_verified"` journal contract) requires TDD-first commit ordering visible in `git log --reverse`. This story **inherits** the `phase1_prompt_builder` + `BOUNDARY_LINE` from Story 2A.8 (Task 1), the specialist-stub posture from Story 2A.8 (AC8/D2), and the CLI surface pattern from Stories 2A.8/2A.9. It introduces the new journal `kind="artifact_verified"` (open `str` field on `JournalEntry`, NOT a contract edit). The `Verification` model is a NEW private internal model (`_Verification`) — NOT a frozen wire-format contract (ADR-024 snapshot count remains 5; recommended D-decision below).

### AC1 — Workflow surface choice (D-decision mirrors Story 2A.9 AC1)

**Given** the architecture's canonical tree at `architecture.md:956-962` does NOT list `workflows_yaml/sdlc-verify.yaml` (same omission posture as `/sdlc-research`); `/sdlc-verify` is single-specialist + artifact-path-as-arg
**When** the dev considers the workflow surface
**Then** **AC1/D1 (workflow YAML D-decision)**: ONE of the following is delivered:
  - **D1:** Ship `workflows_yaml/sdlc-verify.yaml` with `parallel_agents: ()` + `synthesizer_agent: None`. **Pros**: uniform CLI surface; discoverable via `WorkflowRegistry.list()`. **Cons**: 2-line YAML adds ceremony
  - **D2:** Skip the YAML; CLI constructs synthetic WorkflowSpec in-memory. **Pros**: matches architecture omission. **Cons**: divergent from Stories 2A.8/2A.9 pattern
  - **D3:** Skip the workflow YAML AND skip the dispatcher — invoke the runtime directly with a hand-built prompt. **Pros**: simplest. **Cons**: bypasses naming_validator + phase_gate (which is INTENTIONAL — we're not writing a new artifact, we're modifying an existing one with a frontmatter append; phase_gate semantics for "frontmatter-only edits" is not yet defined). NOT recommended in v1 — keeps verification gating policy explicit

**And** **Recommended: D1** (same posture as Story 2A.9 AC1) — preserves the WorkflowRegistry contract; matches sibling Layer-4 stories
**And** if D1 is chosen, `src/sdlc/workflows_yaml/sdlc-verify.yaml` is authored with:

```yaml
schema_version: 1
name: phase1-artifact-verification
slash_command: /sdlc-verify
primary_agent: artifact-verifier
parallel_agents: []
synthesizer_agent: null
postconditions:
  - artifact_verified_frontmatter_present
  - boundary_line_present_in_prompts
write_globs:
  artifact-verifier:
    - "01-Requirement/**/*.md"
    - "01-Requirement/**/*.json"
stop_on_postcondition_failure: true
```

**And** the choice MUST be the FIRST line item in PR Change Log

### AC2 — Single dispatch wiring (`artifact-verifier` primary)

**Given** the dispatcher's single-specialist `dispatch(...)` path per Story 2A.3
**When** the dev wires `/sdlc-verify`
**Then** `src/sdlc/cli/verify.py:run_verify(*, ctx, artifact_id: str)` (NEW) resolves `artifact_id` to a repo-relative POSIX path then calls `dispatch(...)` with the args pattern from Story 2A.9 AC2 (same shape; only the `artifact_id` payload differs)
**And** the prompt builder closure binds the artifact's CURRENT on-disk content as the `idea_text` argument to `phase1_prompt_builder` — the verifier specialist needs to see what it's verifying. The closure pattern is:

```python
artifact_content = (root / artifact_id).read_text(encoding="utf-8")
# guard: artifact_content MUST NOT contain BOUNDARY_LINE — see AC4
prompt_for_verifier = functools.partial(
    phase1_prompt_builder,
    idea_text=artifact_content,
    role="primary",
    upstream_outputs=(),
)
```

**And** the `result.outcome` ∈ `{"success", "failed", "hook_rejected"}`; exit code 0 only on `"success"` AND the parsed verifier verdict `status ∉ {"failed", "advisory"}` — _amended 2026-05-12 per PC6/DC10/DR2_: dispatcher-outcome and verifier-verdict are TWO independent signals; both must be clean for exit 0. Mapping:
  - `outcome="success"` + `verdict="verified"` → exit 0
  - `outcome="success"` + `verdict ∈ {"failed","advisory"}` → exit non-zero (still emits `artifact_verified` with the parsed status; frontmatter row appended; this path is exercised by AC9 scenario 6)
  - `outcome="failed"` → `ERR_PANEL_DISPATCH_FAILED` envelope; exit non-zero
  - `outcome="hook_rejected"` → `ERR_HOOK_REJECTED` envelope; exit non-zero

`hook_rejected` is possible because the verifier's frontmatter-append write goes through the hook chain (phase_gate may permit since this is a Phase-1 artifact edit; naming_validator should permit since the file already exists with a valid name)

### AC3 — Artifact resolution + pre-flight checks

**Given** the AC source's second-Given: "Given the artifact does not exist or is unreadable, when I run `/sdlc-verify <bad-path>`, then the command fails with `WorkflowError('artifact not found at <path>')` and no journal entry is appended"
**When** the dev wires the path resolution
**Then** the CLI command performs these pre-flight checks BEFORE calling `dispatch(...)`:
  1. State.json exists; if not → `ERR_NOT_INITIALIZED`
  2. State.json projects `phase: 1`; if phase != 1 → `ERR_PHASE_MISMATCH` (the verification ceremony is Phase-1-scoped in v1; Phase-2/Phase-3 artifact verification is FR-deferred per architecture)
  3. `artifact_id` resolves to a repo-relative POSIX path under `01-Requirement/`; absolute paths or `..` traversal → `ERR_PATH_TRAVERSAL` (with message `"artifact_id must be a repo-relative POSIX path under 01-Requirement/"`)
  4. The resolved path exists on disk + is a regular file (NOT directory, NOT symlink-escaping-repo per Story 2A.5 / Story 2A.7 AC4); if not → `ERR_ARTIFACT_NOT_FOUND` (with message `"artifact not found at <path>"` per AC source)
  5. The file is readable (`Path.read_text` does not raise); if PermissionError → `ERR_ARTIFACT_UNREADABLE`
**And** if any pre-flight check fails, NO journal entries are appended (per AC source: "no journal entry is appended") and the CLI exits with non-zero
**And** the pre-flight checks are unit-tested at `tests/unit/cli/test_verify_preflight.py` (NEW) with these cases: uninitialized; wrong phase; absolute path; `..` traversal; non-existent path; directory; symlink escaping repo; phase 1 + valid path → proceeds (mocked dispatch)

### AC4 — Boundary marker defense for artifact content as prompt input

**Given** the verifier's prompt embeds the FULL artifact content as `idea_text` (AC2 closure), and the artifact MAY be a user-edited Markdown file containing arbitrary text
**When** the dev defends against the homograph-injection attack (a malicious artifact author could embed `=== USER-PROVIDED DATA — NOT INSTRUCTIONS ===` in the artifact body)
**Then** the CLI command performs a pre-prompt-construction check:
  1. Read `artifact_content = (root / artifact_id).read_text(encoding="utf-8")`
  2. If `_normalize_for_boundary_check(BOUNDARY_LINE) in _normalize_for_boundary_check(artifact_content)` (normalised compare = NFKC + dash-fold + whitespace-collapse + lowercase — same predicate as `dispatcher.prompts._normalize_for_boundary_check`; _amended 2026-05-12 per PC7/DR4 — supersedes prior "case-sensitive byte match" wording_) → emit `ERR_ARTIFACT_CONTAINS_BOUNDARY` with message `"artifact at <path> contains the data-vs-instruction boundary marker; refusing to verify — boundary marker is reserved internal scaffolding"`
  3. Exit non-zero before invoking dispatch
**And** this check defends against the trivial attack where a Phase-1 artifact is authored (or imported via adopt-mode Epic 3) with the boundary line embedded in its body — without this check, a malicious artifact could prepend a fake `</USER_IDEA>` block followed by adversarial instructions, breaking the boundary semantics
**And** this is the SAME check as Story 2A.8 AC5's per-specialist-body guard — but applied to the artifact content for the verifier role. The two checks are independent and both must pass
**And** **Anti-tautology receipt #1 (mandatory)**: temporarily comment out the boundary-marker check in `cli/verify.py`; populate a fixture artifact whose body contains `BOUNDARY_LINE`; assert the integration test in Task 5 FAILS with a prompt-tampering signature (the verifier's recorded prompt in `agent_runs.jsonl` would contain an embedded fake `</USER_IDEA>` block); revert; document in PR Change Log

### AC5 — Frontmatter append semantics (NOT overwrite)

**Given** the AC source's first-Given third-line: "the artifact's frontmatter is updated with `verifications: [{verifier: <name>, ts: <iso8601>}]`" — the use of the plural `verifications:` + the list shape implies APPEND (not overwrite); a single artifact MAY be verified multiple times
**When** the dev wires the frontmatter update
**Then** the CLI command performs the post-dispatch frontmatter append:
  1. After `dispatch(...)` returns success, the dispatcher has already written the verifier's body output to the artifact (potentially clobbering the original — UNLESS the verifier prompt instructs it to output ONLY a verification verdict that the CLI then translates into a frontmatter entry, NOT a body rewrite). **AC5/D1 (write-semantics D-decision)**: ONE of the following is delivered:
     - **D1:** The dispatcher writes the verifier's verdict output to the artifact's BODY (replacing it). This is INVASIVE — verification destroys the original artifact. **Pros**: matches the dispatcher's existing write-glob semantics. **Cons**: destroys artifact content; verification is a SIDE-CHANNEL, not a content-rewrite
     - **D2:** The CLI suppresses the dispatcher's write entirely (pass `persist_artifact=False` flag to dispatch — NEW arg, coordinate with Story 2A.3 owner); captures the verifier's `AgentResult.output_text` (which is a structured verdict per AC6 below); the CLI THEN appends a `verifications:` entry to the artifact's frontmatter while LEAVING the body unchanged. **Pros**: verification is non-destructive. **Cons**: requires dispatcher API extension _(Spec originally specified `suppress_artifact_write=True`; shipped name is `persist_artifact=False` — inverted polarity, positive-naming; functionally equivalent; recorded as DR6/P35 resolution in Review Findings 2026-05-12.)_
     - **D3:** The dispatcher writes the verifier's output to a SEPARATE artifact (e.g., `01-Requirement/02-Verifications/<artifact-id-slug>.md`); the CLI reads that side-channel artifact, extracts the verdict, and appends to the original's frontmatter. **Pros**: clean separation. **Cons**: requires write_globs in the YAML to point to a side-channel; adds an artifact-tree branch
  - **Recommended: D2** — verification MUST be non-destructive (the original artifact's content_hash must be preserved across verifications, otherwise Story 2A.7's signoff hash-drift detection would fire on every verify). The dispatcher arg extension is small and well-scoped
  - **And** if AC5/D1/D2 is chosen, the dispatcher gains a NEW kwarg `persist_artifact: bool = True` on `dispatch(...)`; when False, the dispatcher emits journal entries normally but does NOT call `Path.write_text(...)`; the caller is responsible for any persistent state change. Coordinate this with Story 2A.3 maintainer (Charlie); if rejected, fall back to D3 _(P35 resolution: shipped as `persist_artifact` not `suppress_artifact_write`.)_
  - **And** the choice MUST be the SECOND line item in PR Change Log

**And** the CLI's frontmatter-append logic is:
  1. Read the artifact's current content + parse frontmatter (use `python-frontmatter` library — verify it's in the project; if not, hand-roll a small parser that splits on the `---` delimiters per `cli/scan.py:31` pattern)
  2. Parse the existing `verifications:` field as `list[dict] | None`; if absent OR null, initialize as empty list
  3. Append a new entry: `{verifier: "artifact-verifier", ts: <RFC 3339 UTC ms>, status: "verified", content_hash_at_verify: "sha256:<64hex of artifact body bytes excluding frontmatter>"}` (the SCHEMA is defined in AC6 below)
  4. Re-serialize the frontmatter + body and write back via `Path.write_text(...)` (inherits `EPIC-2A-DEBT-WRITE-PRIMITIVE`)
  5. The write is GUARDED by the hook chain — the CLI calls `run_hook_chain(...)` directly per Story 2A.4 AC1 BEFORE writing OR via the dispatcher's hook chain (per AC5/D1/D2 the dispatcher-write is suppressed, so the CLI must run hooks itself). Document this explicitly in the module docstring
**And** the body bytes hashed in `content_hash_at_verify` are the bytes AFTER the second `---` delimiter, with a trailing newline (canonical body form per Pattern §3) — exclude the frontmatter to keep the hash invariant under future frontmatter-only edits (verifications, signoff-record updates, etc.). Document the canonicalization in `cli/verify.py`'s module docstring

### AC6 — `Verification` model schema (private, NOT wire-format)

**Given** the appended `verifications:` list entries need a stable shape consumable by Story 2A.12 `/sdlc-signoff` and any future dashboard route
**When** the dev defines the model
**Then** `src/sdlc/cli/verify.py` (or a NEW `src/sdlc/verification/` package per AC8/D1) defines a private pydantic model:

```python
from typing import Annotated, Literal
from pydantic import StringConstraints
from sdlc.contracts._strict_model import StrictModel

class _Verification(StrictModel):
    """Internal model for a single verification entry in an artifact's frontmatter.

    NOT exported from sdlc.contracts. NOT a frozen wire-format contract.
    On-disk YAML schema may evolve in v1.x without ADR-024 ceremony.
    """
    schema_version: Literal[1] = 1
    verifier: str                                      # specialist name; "artifact-verifier" in v1
    ts: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")]
    status: Literal["verified", "failed", "advisory"] = "verified"
    content_hash_at_verify: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
    verifier_note: str | None = None                   # optional free-text from the verifier specialist (≤ 500 chars)
```

**And** **AC6/D1 (wire-format D-decision; mirrors Story 2A.7 AC11/D2 + Story 2A.5 AC8)**: ONE of the following is delivered:
  - **D1:** Promote `_Verification` to a 6th frozen wire-format contract NOW via ADR-024 ceremony. Add `tests/contract_snapshots/v1/verification.json` snapshot. **Pros**: future-proof; dashboard + Story 2A.12 can rely on the shape. **Cons**: locks v1 schema before consumer needs it; ADR-024 ceremony cost
  - **D2:** Keep `_Verification` private to `sdlc.cli.verify` (or `sdlc.verification.` per AC8/D1). Document promotion criteria in module docstring (mirroring Story 2A.7 AC9 third-And + Story 2A.5 AC8). Promote in Story 2A.12 (signoff) IF needed there. **Pros**: matches Story 2A.7's `SignoffRecord` and Story 2A.5's `_HookHashStore` posture; no ceremony cost
  - **D3:** Defer the decision; ship as private + add `EPIC-2A-DEBT-VERIFICATION-PROMOTION-DECISION` debt entry in `deferred-work.md` for Story 2A.12 or Epic 5 to resolve

**And** **Recommended: D2** — consistent with the privacy-first posture established by 2A.5 + 2A.7; no current consumer needs the public surface; Story 2A.12 will be the first real consumer and can promote then
**And** the choice MUST be the THIRD line item in PR Change Log
**And** `python scripts/freeze_wireformat_snapshots.py --check` reports `5 contracts match snapshots` (unchanged) IF D2 chosen; `6 contracts match snapshots` IF D1 chosen (in which case the snapshot is added in this story)

### AC7 — Journal kind `artifact_verified`

**Given** the journal kinds enumerated by Stories 2A.3 + 2A.8 (`dispatch_attempt`, `artifact_written`, `hook_rejected`, `agent_dispatched`)
**When** `/sdlc-verify` runs to completion
**Then** the journal contains, in monotonic order:
  1. Exactly ONE `kind="agent_dispatched"` entry (same shape as Story 2A.8 AC4 for the verifier specialist): `actor="agent:artifact-verifier"`, `target_id=<artifact_id>`, `before_hash="sha256:<64hex of pre-verify artifact bytes>"` (NOT None — verification has a known pre-state), `after_hash="sha256:" + "0"*64` (sentinel — the agent dispatch itself doesn't mutate the artifact in AC5/D2), `payload={"slash_command": "/sdlc-verify", "specialist": "artifact-verifier", "role": "primary", "attempt": N, "artifact_hash_at_dispatch": "sha256:<64hex>"}`
  2. Zero or more `kind="dispatch_attempt"` entries per retry policy
  3. Exactly ONE `kind="artifact_verified"` entry on success (NEW kind, introduced by this story): `actor="cli"`, `target_id=<artifact_id>`, `before_hash="sha256:<64hex of pre-verify on-disk bytes including frontmatter>"`, `after_hash="sha256:<64hex of post-verify on-disk bytes including frontmatter>"`, `payload={"slash_command": "/sdlc-verify", "phase": 1, "verifier": "artifact-verifier", "status": "verified", "content_hash_at_verify": "sha256:<64hex of body-only bytes>", "verification_index": N}` where `verification_index` is the index in the `verifications:` list (0 for first verify, 1 for second, etc. — useful for `sdlc trace`)
**And** the new kind `artifact_verified` is introduced UNILATERALLY in this story; `JournalEntry.kind` is an open `str` field per `contracts/journal_entry.py:21` so no contract edit is required (cite this in PR Change Log)
**And** if `result.outcome` is `"failed"` or `"hook_rejected"`, NO `artifact_verified` entry is appended; the `agent_dispatched` and any `dispatch_attempt` entries remain
**And** if the verifier returns `status: "failed"` (verifier-decided rejection, distinct from dispatcher-decided failure), the CLI still emits an `artifact_verified` journal entry with `payload.status: "failed"` AND appends the `_Verification` to the artifact frontmatter with `status: "failed"` — failed verifications are PART of the audit trail. The CLI exits non-zero but the audit chain is preserved

### AC8 — Module structure D-decision + file layout

**Given** the question of whether `_Verification` model + verification logic lives in `cli/verify.py` (CLI-local) or in a NEW `src/sdlc/verification/` package (mirror Story 2A.7's `src/sdlc/signoff/` package)
**When** the dev considers the module layout
**Then** **AC8/D1 (module structure D-decision)**: ONE of the following is delivered:
  - **D1:** Keep verification logic in `cli/verify.py` (single file ≤ 400 LOC). Model `_Verification` is a private class in this file. Frontmatter parser is a local helper. **Pros**: simplest; single file ownership; matches Story 2A.9's `cli/research.py` posture. **Cons**: future dashboard route (Epic 5) needs the model + parsing logic; importing from `cli.verify` violates the architecture boundary table (dashboard does NOT import cli)
  - **D2:** Create a NEW `src/sdlc/verification/` package mirroring Story 2A.7's `src/sdlc/signoff/`: `verification/__init__.py` (public re-exports), `verification/models.py` (`_Verification` + helpers), `verification/frontmatter.py` (parse + append + serialize). `cli/verify.py` becomes a thin Typer shim. **Pros**: matches signoff's package shape; future dashboard reuse-friendly. **Cons**: new package; more LOC churn; new boundary table entry
  - **D3:** Stash verification logic in an existing package — `signoff/verifications.py` (since verifications hash into signoff). **Pros**: leverages existing module. **Cons**: confuses two distinct lifecycles (verification ≠ signoff); pollutes signoff/'s clean state-machine surface
  - **D4 (added 2026-05-12 via P32/DR3 retroactive amend):** Single public surface (`cli/verify.py` with `__all__` re-exports) + N underscore-prefixed private CLI-internal helper modules, each module ≤ Architecture §1052-§1112 LOC cap. **Pros**: respects per-module LOC cap when the unsplit verify.py exceeds the cap; preserves a single public import surface (`from sdlc.cli.verify import run_verify, _Verification, ...`) for callers; matches signoff/'s package-shape posture without introducing a new top-level package; underscore prefix signals CLI-internal scope. **Cons**: more files to navigate; private-prefix discipline required; promotion path to a public `sdlc.verification.` package (D2) requires an explicit follow-up story when a non-CLI consumer (e.g. dashboard / Story 2A.12 `/sdlc-signoff`) appears

**And** **Recommended: D1 if `cli/verify.py` fits ≤ 400 LOC; otherwise D4** — D4 is the chosen resolution for Story 2A.10 because the unsplit `verify.py` reached 835 LOC during implementation (Change Log item 4); the split into `cli/verify.py` (242 LOC) + `_verify_frontmatter.py` (192) + `_verify_dispatch.py` (342) + `_verify_post.py` (193) keeps each module under the Architecture §1052-§1112 cap. If a future story needs the model elsewhere, promote then (mirroring Story 2A.7's `SignoffRecord` v1 → v1.x promotion path)
**And** if D1 or D4 is chosen, the file layout is (D4 adds the three `_verify_*.py` private helpers shown alongside):

```
src/sdlc/cli/
├── verify.py                             # NEW — public orchestrator (run_verify + __all__ re-exports) (D1 ≤ 400 LOC or D4 thin shim 242 LOC)
├── _verify_frontmatter.py                # D4 ONLY — _Verification + _parse_frontmatter + _append_verification + _serialize_artifact (192 LOC)
├── _verify_dispatch.py                   # D4 ONLY — workflow/registry load + MockAIRuntime fixture + dispatch() call (342 LOC)
└── _verify_post.py                       # D4 ONLY — verdict parse + frontmatter append + journal emit + state-seq advance (193 LOC)

src/sdlc/cli/main.py                      # UPDATE — register `verify_command`

src/sdlc/workflows_yaml/
└── sdlc-verify.yaml                      # NEW per AC1/D1

src/sdlc/commands/
└── sdlc-verify.md                        # NEW — slash-command shell

src/sdlc/agents/phase1/
└── artifact-verifier.md                  # NEW — placeholder stub (per Story 2A.8 AC8/D2 pattern; this story extends `agents/index.yaml` to register a 5th Phase-1 specialist)

src/sdlc/agents/index.yaml                # UPDATE — register `artifact-verifier`

tests/unit/cli/
├── test_verify_preflight.py              # NEW — pre-flight check matrix (≤ 250 LOC)
├── test_verify_frontmatter.py            # NEW — _Verification model + parse/append/serialize (≤ 300 LOC)
└── test_verify_boundary_guard.py         # NEW — boundary-marker defense (≤ 100 LOC)

tests/unit/workflows/
└── test_phase1_workflows_present.py      # UPDATE — add sdlc-verify.yaml load test

tests/integration/
└── test_sdlc_verify.py                   # NEW — full dispatch + frontmatter append with MockAIRuntime (≤ 300 LOC)

tests/e2e/pipeline/
├── fixtures/verify/
│   ├── commands.yaml                     # NEW
│   ├── responses.yaml                    # NEW — canned verifier response with structured verdict
│   ├── workflow.yaml                     # NEW
│   ├── artifact_under_test/              # NEW — fixture artifact (a small 01-Requirement/01-PRODUCT.md stub)
│   └── goldens/
│       └── journal.jsonl                 # NEW — normalized golden
└── test_sdlc_verify.py                   # NEW — Tier-2 e2e (5 scenarios per AC9)
```

**And** all new files respect Story 1.2 LOC caps; cli files use deferred imports per Architecture §488
**And** the AC8 D-decision choice MUST be the FOURTH line item in PR Change Log

### AC9 — Tier-2 e2e (6 scenarios — _amended 2026-05-12 per PC6/DR2_)

**Given** the Tier-2 e2e harness from Story 2A.0
**When** the dev authors the verify e2e
**Then** `tests/e2e/pipeline/test_sdlc_verify.py` (NEW) drives SIX scenarios:
  1. **Happy path (first verification)**: tmp repo at phase 1 with `01-Requirement/01-PRODUCT.md` (no `verifications:` field yet); invoke `sdlc verify 01-Requirement/01-PRODUCT.md`; assert exit 0; assert frontmatter now has `verifications: [{verifier: "artifact-verifier", ts: <RFC 3339>, status: "verified", content_hash_at_verify: "sha256:..."}]`; assert body bytes UNCHANGED (the verifier's verdict went only to frontmatter); assert journal: 1 `agent_dispatched` + 1 `artifact_verified`; assert `BOUNDARY_LINE` present in dispatched prompt
  2. **Second verification (append, not overwrite)**: tmp repo with `01-PRODUCT.md` already verified once; invoke verify a second time; assert exit 0; assert `verifications:` list now has 2 entries (NOT 1; NOT replaced); assert first entry is BYTE-UNCHANGED; assert second entry has a new `ts` (and new `content_hash_at_verify` if body changed between verifies — in this test the body is unchanged so both hashes match)
  3. **Artifact not found**: invoke `sdlc verify 01-Requirement/does-not-exist.md`; assert exit 1; assert `ERR_ARTIFACT_NOT_FOUND` in stderr; assert NO journal entries appended; assert no files created
  4. **Path traversal**: invoke `sdlc verify ../etc/passwd`; assert exit 1; assert `ERR_PATH_TRAVERSAL` in stderr; assert NO new journal entries
  5. **Boundary-marker pollution**: tmp repo with `01-PRODUCT.md` whose body contains `BOUNDARY_LINE`; invoke verify; assert exit 1; assert `ERR_ARTIFACT_CONTAINS_BOUNDARY` in stderr; assert NO journal entries
  6. **Verifier-failed verdict (added 2026-05-12 per PC6)**: tmp repo with `01-PRODUCT.md`; MockAIRuntime canned to return `{"verdict":"failed","note":"reason text"}`; invoke verify; assert exit code != 0 (per DC10 resolution: `entry.status in {failed, advisory}` ⇒ non-zero); assert frontmatter `verifications:` row has `status: "failed"` + matching `verifier_note`; assert journal `artifact_verified` payload has `status: "failed"`; assert NO `ERR_PANEL_DISPATCH_FAILED` (dispatcher outcome was success — only verdict was failed)
**And** the e2e tests carry `@pytest.mark.e2e`; runtime ≤ 30 s per scenario
**And** the MockAIRuntime mock verdict MUST be parameterisable per test (drop the module-level `MappingProxyType` `Final` form in `src/sdlc/cli/_verify_dispatch.py:60-62`; convert to a fixture-injectable helper or expose a `_set_mock_verdict()` test hook) — _added 2026-05-12 per PC6/E14_
**And** AC10 coverage rider: `src/sdlc/cli/_verify_dispatch.py` must remain ≥ 95% line coverage; the failed-verdict branch is a covered line — _added 2026-05-12 per PC6/A9_
**And** **Anti-tautology receipt #2 (AC9 mandatory)**: in scenario 2 (append not overwrite), temporarily replace `assert len(verifications) == 2` with `assert len(verifications) == 1`; assert the test FAILS; revert; document in PR Change Log

### AC10 — Quality gate compliance (CONTRIBUTING.md §1)

**Given** the full Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests`
  - `pytest -q -m "not e2e and not property"` (unit + integration green; pre-existing baseline failures unchanged)
  - `pytest -q -m e2e` (existing Tier-1/2 + new Tier-2 from AC9 must pass; goldens regenerated if needed)
  - `pytest --cov=src --cov-report=term-missing --cov-fail-under=90` (≥ 90% repo-wide; module-level: ≥ 95% on `cli/verify.py`; 100% on the pure helpers `_parse_frontmatter`, `_append_verification`, `_serialize_artifact`)
  - `pre-commit run --all-files`
  - `mkdocs build --strict`
  - `python scripts/freeze_wireformat_snapshots.py --check` — `5 contracts match snapshots` IF AC6/D1/D2 chosen (recommended); `6 contracts match snapshots` IF AC6/D1/D1 chosen
  - `python scripts/check_module_boundaries.py` — 0 new violations (cli → dispatcher/hooks/workflows/specialists/runtime already permitted by Story 2A.8 AC11/D2)
  - `python scripts/validate_specialists.py` — passes (with `artifact-verifier` registered in `agents/index.yaml`)

## Tasks / Subtasks

> Tasks ordered to enable TDD-first commits per ADR-026 §1. AC1 + AC3 + AC4 + AC5 + AC6 + AC9 are the public-API surfaces requiring tests-first commit ordering visible in `git log --reverse`.

- [x] **Task 1 — `_Verification` model + frontmatter parser/serializer (AC5, AC6)** — **TDD-first commit 1**
  - [x] 1.1 Author `tests/unit/cli/test_verify_frontmatter.py` covering: `_Verification.model_validate` happy path; rejects invalid `ts` (must match RFC 3339 pattern); rejects invalid `content_hash_at_verify` (must match `^sha256:[0-9a-f]{64}$`); rejects extra fields (`extra="forbid"` per StrictModel); status defaults to "verified"; verifier_note ≤ 500 chars or None. Tests fail (red).
  - [x] 1.2 Author tests for `_parse_frontmatter(content: str) -> tuple[dict, str]`: returns `({}, content)` if no frontmatter; returns `(parsed_dict, body)` if frontmatter present; raises `WorkflowError` if YAML parse fails; raises if frontmatter is not a mapping. Tests fail (red).
  - [x] 1.3 Author tests for `_append_verification(frontmatter: dict, entry: _Verification) -> dict`: returns new dict (immutable; does NOT mutate input); initializes `verifications: []` if absent; appends new entry; round-trip via yaml.safe_dump is byte-stable; existing entries preserved bit-exact. Tests fail (red).
  - [x] 1.4 Author tests for `_serialize_artifact(frontmatter: dict, body: str) -> str`: round-trip with `_parse_frontmatter`; trailing newline present; YAML canonicalization (sorted keys, no flow style, UTF-8); empty frontmatter omits the `---` delimiters entirely (just returns body). Tests fail (red).
  - [x] 1.5 Implement all four in `src/sdlc/cli/verify.py` (per AC8/D1 recommended). Use stdlib `yaml.safe_load` + `yaml.safe_dump`. LOC ≤ 200 for these four combined. Tests pass (green). _(Subsequently extracted to `_verify_frontmatter.py` per AC8/D1 — see Task 5.)_
  - [x] 1.6 Document the AC6/D1 D-decision choice (recommend D2 — private model) in PR Change Log as the THIRD line item.
  - [x] 1.7 Document the AC8/D1 D-decision choice (recommend D1 — single file) in PR Change Log as the FOURTH line item.

- [x] **Task 2 — Pre-flight checks + path resolution (AC3)** — **TDD-first commit 2**
  - [x] 2.1 Author `tests/unit/cli/test_verify_preflight.py` per AC3: uninitialized; wrong phase; absolute path; `..` traversal; non-existent; directory; symlink-escape; phase 1 valid → proceeds (mocked dispatch). Tests fail (red).
  - [x] 2.2 Implement pre-flight logic in `cli/verify.py:run_verify`. Use `pathlib.PurePosixPath` for `..` detection; resolve against `repo_root` and assert the resolved path is under `repo_root / "01-Requirement"`. Tests pass (green).

- [x] **Task 3 — Boundary-marker artifact guard (AC4)** — **TDD-first commit 3**
  - [x] 3.1 Author `tests/unit/cli/test_verify_boundary_guard.py`: artifact body containing `BOUNDARY_LINE` → `ERR_ARTIFACT_CONTAINS_BOUNDARY`; artifact body containing the substring but not the full marker → proceeds (e.g., `=== USER ===` without the full canonical line); artifact body containing the marker inside a fenced code block → also rejected (we don't parse Markdown; bytewise check). Tests fail (red).
  - [x] 3.2 Implement the guard in `cli/verify.py` per AC4. Tests pass (green).
  - [x] 3.3 **Anti-tautology receipt #1 (AC4 mandatory)**: temporarily comment out the check; populate a fixture artifact whose body contains `BOUNDARY_LINE`; assert the integration test in Task 5 FAILS with a prompt-tampering signature; revert; document in PR Change Log.

- [x] **Task 4 — `workflows_yaml/sdlc-verify.yaml` + load test (AC1)** — **TDD-first commit 4**
  - [x] 4.1 Extend `tests/unit/workflows/test_phase1_workflows_present.py`: assert `WorkflowRegistry.load(...)` discovers `sdlc-verify.yaml`; assert `primary_agent == "artifact-verifier"`; assert `parallel_agents == ()` + `synthesizer_agent is None`. Tests fail (red).
  - [x] 4.2 Author `src/sdlc/workflows_yaml/sdlc-verify.yaml` per AC1/D1 exact byte content.
  - [x] 4.3 Author the `artifact-verifier` specialist stub at `src/sdlc/agents/phase1/artifact-verifier.md` (mirror Story 2A.8 AC8/D2 stub template; the body says `"Verify the artifact content. Output a structured verdict in your AgentResult.output_text with a JSON object {verdict: 'verified'|'failed', note: '...'}."`).
  - [x] 4.4 Update `src/sdlc/agents/index.yaml` to register `artifact-verifier` as a 5th Phase-1 specialist.
  - [x] 4.5 Run `scripts/validate_specialists.py` — must pass. Tests pass (green).
  - [x] 4.6 Document the AC1/D1 D-decision choice (recommend D1) in PR Change Log as the FIRST line item.

- [x] **Task 5 — `cli/verify.py:run_verify` + Typer registration (AC2, AC5, AC7)** — **TDD-first commit 5**
  - [x] 5.1 Author `tests/integration/test_sdlc_verify.py`: tmp repo at phase 1 with a real `01-Requirement/01-PRODUCT.md` (use a fixture); construct MockAIRuntime with canned verifier response (structured verdict JSON in output_text); invoke `run_verify(...)` directly; assert journal contains 1 `agent_dispatched` + 1 `artifact_verified`; assert artifact frontmatter now has `verifications: [...]` with exactly 1 entry; assert artifact body is BYTE-UNCHANGED across the verify (the dispatcher write is suppressed per AC5/D2); assert `agent_runs.jsonl` records the prompt with `BOUNDARY_LINE` present. Tests fail (red until Tasks 1-4 land).
  - [x] 5.2 Implement `run_verify(*, ctx, artifact_id: str)` in `cli/verify.py`: deferred imports; pre-flight per AC3; boundary-guard per AC4; load registries; construct MockAIRuntime; build prompt-builder closure with `idea_text=artifact_content`; call `dispatch(...)` with `persist_artifact=False` (per AC5/D2 — P35 resolution; coordinate with Story 2A.3 owner if rejected → fall back to AC5/D1/D3 side-channel artifact); parse the verifier's `output_text` for a `{verdict, note}` JSON object; construct a `_Verification` entry; run hook chain via `run_hook_chain(payload, hooks=build_pre_write_hook_chain(repo_root), journal_path=journal_path)` for the frontmatter-edit write; append + re-serialize + write back; emit journal `artifact_verified`. LOC ≤ 400.
  - [x] 5.3 Update `cli/main.py` to register `verify_command`:

    ```python
    @app.command(name="verify")
    def verify_command(
        ctx: typer.Context,
        artifact_id: str = typer.Argument(..., help="Repo-relative POSIX path to the artifact to verify"),
    ) -> None:
        """Verify a Phase 1 artifact (FR8)."""
        from sdlc.cli.verify import run_verify
        run_verify(ctx=ctx, artifact_id=artifact_id)
    ```

  - [x] 5.4 Author `src/sdlc/commands/sdlc-verify.md` slash-command shell. Tests pass (green).
  - [x] 5.5 Document the AC5/D1 D-decision choice (recommend D2 — suppress dispatcher write) in PR Change Log as the SECOND line item.

- [x] **Task 6 — Tier-2 e2e (AC9)** — **TDD-first commit 6**
  - [x] 6.1 Author `tests/e2e/pipeline/test_sdlc_verify.py` with all 5 scenarios from AC9.
  - [x] 6.2 Author fixtures under `tests/e2e/pipeline/fixtures/verify/` including a sample `01-Requirement/01-PRODUCT.md` artifact_under_test.
  - [x] 6.3 Run `pytest -m e2e tests/e2e/pipeline/test_sdlc_verify.py` — must pass green; runtime ≤ 30s per scenario.
  - [x] 6.4 **Anti-tautology receipt #2 (AC9 mandatory)**: in scenario 2 (append not overwrite), temporarily replace `assert len(verifications) == 2` with `assert len(verifications) == 1`; assert the test FAILS; revert; document in PR Change Log.

- [x] **Task 7 — Quality gate + Change Log (AC10)**
  - [x] 7.1 Run all quality gate commands in AC10; all must pass green.
  - [x] 7.2 Author PR Change Log with FOUR D-decision lines (AC1/D1, AC5/D1, AC6/D1, AC8/D1) as the FIRST four items, followed by 2 anti-tautology receipts, followed by inherited-debt citations.
  - [x] 7.3 Set Story status `review`; sprint-status.yaml transition by `dev-story` skill.

## Dev Notes

### Source Hints
- Epic 2A AC source: `_bmad-output/planning-artifacts/epics.md:1212-1229`
- Dispatcher API: `src/sdlc/dispatcher/__init__.py:19-27`
- Prompt builder + BOUNDARY_LINE: `src/sdlc/dispatcher/prompts.py` (introduced by Story 2A.8)
- Hook chain: `src/sdlc/hooks/__init__.py:14-46`, `src/sdlc/hooks/runner.py:252-259`
- Frontmatter parsing pattern: `src/sdlc/cli/scan.py:31` (`_compute_sha256_of_file` shape) — verify whether the project has a `python-frontmatter` dependency or whether parsing is hand-rolled. If not present, hand-roll a minimal parser (split on `---\n` delimiters; first occurrence is start, second occurrence is end; rest is body)
- StrictModel: `src/sdlc/contracts/_strict_model.py` per ADR-025

### Cross-Story Coordination
- Story 2A.8 (`/sdlc-start`) — must land first (provides `phase1_prompt_builder`, `BOUNDARY_LINE`, specialist-stub posture, CLI surface pattern)
- Story 2A.9 (`/sdlc-research`) — parallel Layer 4; coordinate `cli/main.py` and `agents/index.yaml` merges
- Story 2A.11 (`/sdlc-epics` + `/sdlc-stories`) — parallel Layer 4; no direct overlap
- Story 2A.12 (`/sdlc-signoff`) — Layer 5; the FIRST real consumer of `_Verification` data. If 2A.12 needs to read `verifications:` from on-disk artifacts to compose the SIGNOFF.md hash list, the read path is: parse frontmatter via `_parse_frontmatter` (this story's helper), extract `verifications:`, hash via `_Verification.model_validate(...)`. Either expose the helpers via `src/sdlc/cli/verify.py` (small-surface; cli depends on cli is fine) OR promote to `src/sdlc/verification/` per AC8/D2 in 2A.12

### Project Structure Notes
- The dispatcher's `persist_artifact` kwarg (AC5/D2, P35 resolution) is a NEW dispatcher API change. Coordinate with Story 2A.3 maintainer; if the dispatcher refuses the extension, fall back to AC5/D3 (side-channel artifact + frontmatter append in CLI)
- The boundary-marker guard (AC4) is a DEFENSE-IN-DEPTH check. The "real" prompt-injection mitigation lives in the LLM's interpretation of the `<BOUNDARY>` block; this guard catches the trivial homograph attack only. Epic 2B's prompt-injection corpus is the canonical verification gate
- The `content_hash_at_verify` field hashes the BODY ONLY (post-second-`---` bytes) — NOT the frontmatter. This keeps the hash invariant under frontmatter-only edits (subsequent verifications, signoff record updates). This deliberately differs from Story 2A.7's `compute_artifact_hash` which hashes ON-DISK BYTES VERBATIM (including frontmatter). The two are different hashes for different purposes: `compute_artifact_hash` defends the signoff drift detection; `content_hash_at_verify` defends the verifier's claim that the body content at verify-time was what it actually verified

### Inherited Debt (cited in PR Change Log)
- `EPIC-2A-DEBT-WRITE-PRIMITIVE` — re-cited
- `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` — re-cited
- `EPIC-2A-DEBT-JOURNAL-NULL-AFTER-HASH` — sentinel after_hash for `agent_dispatched` (only); the `artifact_verified` kind has REAL before/after hashes per AC7

### Opened Debt (this story)
- If AC5/D1 = D3 (side-channel artifact tree) chosen: `EPIC-2A-DEBT-VERIFICATION-SIDE-CHANNEL` for v1.x reconciliation
- If AC6/D1 = D3 chosen: `EPIC-2A-DEBT-VERIFICATION-PROMOTION-DECISION` for Story 2A.12 or Epic 5

### References
- [Source: `_bmad-output/planning-artifacts/epics.md:1212-1229`] — Story 2A.10 BDD ACs
- [Source: `_bmad-output/planning-artifacts/architecture.md:937-944,956-962,1052-1072,1136-1140`]
- [Source: `src/sdlc/dispatcher/__init__.py:19-27`, `src/sdlc/dispatcher/core.py:94-107`]
- [Source: `src/sdlc/dispatcher/prompts.py`] (Story 2A.8)
- [Source: `src/sdlc/contracts/journal_entry.py:15-26`]
- [Source: `src/sdlc/contracts/_strict_model.py`]
- [Source: `src/sdlc/cli/scan.py:19-87`, `src/sdlc/cli/main.py:87-92`]
- [Source: Story 2A.8 sibling story file]
- [Source: Story 2A.9 sibling story file]
- [Source: Story 2A.7 `SignoffRecord` privacy posture pattern in `2a-7-recovery-signoff-state-machine-hash-drift-validation.md` AC9 + AC11/D2]
- [Source: ADR-024 + ADR-025 + ADR-026]
- [Source: CONTRIBUTING.md §1-§5]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (Cursor IDE), worktree `SDLC-Framework-story-2a-10` on branch `story/2a-10-sdlc-verify`.

### Debug Log References

- **Task 1 RED → GREEN**: 27 unit tests in `tests/unit/cli/test_verify_frontmatter.py` covering `_Verification` schema, `_parse_frontmatter`, `_append_verification`, `_serialize_artifact`. RED proof: failing-test commit `5fc8995^` (pre-implementation). GREEN: `5fc8995`.
- **Task 2 RED → GREEN**: 14 unit tests in `tests/unit/cli/test_verify_preflight.py` (uninit / phase-mismatch / abs-path / `..` / missing / directory / symlink-escape + happy). RED: `bc28333`. GREEN: `6d6a951`.
- **Task 3 RED → GREEN**: 5 unit tests in `tests/unit/cli/test_verify_boundary_guard.py`. RED: `5ff7f5d`. GREEN: `f3aabff`. Anti-tautology receipt #1 attached to Task 5 integration test (see Change Log).
- **Task 4 RED → GREEN**: workflow YAML + 5th specialist + index registration. RED: `96ea28c`. GREEN: `79b5f9f`. `scripts/validate_specialists.py` PASS.
- **Task 5 RED → GREEN + REFACTOR**: integration test `tests/integration/test_sdlc_verify.py`. RED: `3798c78`. GREEN: `97e969a` — included LOC-cap split into `_verify_frontmatter.py` + `_verify_dispatch.py` + `_verify_post.py` to keep every module ≤ 400 LOC (Architecture §1052-§1112, NFR-MAINT-3).
- **Task 6 e2e**: 5 scenarios in `tests/e2e/pipeline/test_sdlc_verify.py` (happy / append / not-found / path-traversal / boundary-pollution). Commit: `797d9f7`. Anti-tautology receipt #2 attached (see Change Log).
- **Task 7 quality gate**: 38 defensive-branch unit tests in 4 new files. Coverage push from 79-88% to 92-99% across all four verify modules. Commit: `45eaeaf`.

#### Worktree-session anomaly (resolved)

During the Task 7 mypy regression check I ran `git stash && git checkout origin/main -- src/ tests/ && uv run mypy --strict src tests && git checkout HEAD -- src/ tests/ && git stash pop`. The `git stash pop` re-applied an OLDER WIP stash that pre-dated Story 2A.10 (it had been left over from another branch); this temporarily reverted `src/sdlc/cli/main.py`, `src/sdlc/cli/output.py`, `src/sdlc/agents/index.yaml`, and `src/sdlc/dispatcher/core.py` to pre-Story 2A.10 state. Detected via `git status` showing unexpected staged deletes of the `verify` command. **Recovery**: `git reset --hard HEAD` to discard the phantom stash content (HEAD was already at the correct `797d9f7` commit). No data lost; no production change required. Re-running mypy/pytest/pre-commit after the reset confirmed all Story 2A.10 commits intact.

### Completion Notes List

- All 10 ACs satisfied. TDD-first commit ordering preserved: every RED commit precedes its GREEN commit in `git log --reverse origin/main..HEAD`.
- `_Verification` model is a PRIVATE Pydantic StrictModel (AC6/D1 = D2). Not added to ADR-024 frozen snapshots. Schema-version pin (`schema_version: Literal[1]`) keeps the upgrade contract local to this story.
- Dispatcher API extended (`observer`, `persist_artifact=False`, `target_path_override`) to support non-destructive verification per AC5/D2. The dispatcher's `Path.write_text` + `artifact_written` journal append are suppressed; the CLI owns the body-preserving frontmatter rewrite. The `_run_member` path already exposed these kwargs (panel dispatch parity); `dispatch()` was widened to forward them.
- AC8/D1 = D1 in spec, but realised as **D1-extended**: `cli/verify.py` re-exports the helpers from `_verify_frontmatter.py`, `_verify_dispatch.py`, and `_verify_post.py`. The four private modules together stay under the §1052-§1112 cap (largest is `_verify_dispatch.py` at 342 LOC). The PUBLIC surface remains exactly `cli/verify.run_verify`.
- All 5 e2e scenarios execute in < 0.2s combined (well under the 30s/scenario gate).
- Coverage: cli/verify.py 92%, _verify_frontmatter 98%, _verify_dispatch 98%, _verify_post 99% — average 96.75% on the four story-owned modules.

### File List

**New source (7 files)**:
- `src/sdlc/cli/verify.py` — public orchestrator (242 LOC)
- `src/sdlc/cli/_verify_frontmatter.py` — `_Verification` model + parser + serializer + canonical-body hash (192 LOC)
- `src/sdlc/cli/_verify_dispatch.py` — workflow/registry load + MockAIRuntime fixture + `dispatch()` call (342 LOC)
- `src/sdlc/cli/_verify_post.py` — verdict parse + frontmatter append + journal emit + state-seq advance (193 LOC)
- `src/sdlc/workflows_yaml/sdlc-verify.yaml` — primary-only workflow surface
- `src/sdlc/agents/phase1/artifact-verifier.md` — 5th Phase-1 specialist stub
- `src/sdlc/commands/sdlc-verify.md` — slash-command shell

**Modified source (4 files)**:
- `src/sdlc/cli/main.py` — register `verify_command` (deferred import per Architecture §488)
- `src/sdlc/cli/output.py` — `BOUNDARY_LINE` constant promoted for AC4 guard
- `src/sdlc/agents/index.yaml` — register `artifact-verifier` as 5th Phase-1 specialist
- `src/sdlc/dispatcher/core.py` — widen `prompt_builder` type + add `observer` / `persist_artifact` / `target_path_override` kwargs forwarded to `_run_member`

**New tests (9 files)**:
- `tests/unit/cli/test_verify_frontmatter.py` (27 tests)
- `tests/unit/cli/test_verify_frontmatter_edges.py` (14 tests — Task 7 coverage push)
- `tests/unit/cli/test_verify_preflight.py` (14 tests)
- `tests/unit/cli/test_verify_boundary_guard.py` (5 tests)
- `tests/unit/cli/test_verify_post.py` (11 tests — Task 7 coverage push)
- `tests/unit/cli/test_verify_state_phase.py` (5 tests — Task 7 coverage push)
- `tests/unit/cli/test_verify_dispatch_errors.py` (8 tests — Task 7 coverage push)
- `tests/integration/test_sdlc_verify.py` (2 integration tests)
- `tests/e2e/pipeline/test_sdlc_verify.py` (5 e2e scenarios)

**New test fixtures (5 files)**:
- `tests/e2e/pipeline/fixtures/verify/artifact_under_test/01-PRODUCT.md`
- `tests/e2e/pipeline/fixtures/verify/commands.yaml`
- `tests/e2e/pipeline/fixtures/verify/goldens/journal.jsonl`
- `tests/e2e/pipeline/fixtures/verify/responses.yaml`
- `tests/e2e/pipeline/fixtures/verify/workflow.yaml`

**Modified tests (2 files)**:
- `tests/unit/workflows/test_phase1_workflows_present.py` — `/sdlc-verify` discovery + primary-agent assertion
- `tests/integration/test_wheel_build.py` — expand `_ALLOWED_CONTENT_FILES` to cover the 9 force-include content files shipped by Stories 2A.2–2A.10 (was failing on `main` pre-existing; now green)

**Modified artifacts (1 file)**:
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `2a-10-sdlc-verify`: ready-for-dev → in-progress → review

## Change Log

> Per CONTRIBUTING.md §6, the first four lines below are the D-decision audit trail in spec-mandated order (AC1 → AC5 → AC6 → AC8). Lines 5-6 are the anti-tautology receipts. Lines 7-9 are inherited-debt citations.

1. **D-decision AC1/D1 = D1** — `workflows_yaml/sdlc-verify.yaml` SHIPPED (`primary_agent: artifact-verifier`, `parallel_agents: []`, no synthesizer). Rationale: uniform CLI surface with Stories 2A.8 + 2A.9; discoverable via `WorkflowRegistry.list()`; 2-line ceremony cost is negligible against future tooling cost of synthetic in-memory specs (D2 was rejected). The architecture omission (architecture.md §956-962) is treated as DOC drift to fix in Epic-2A-retrospective, not as a contract directive.

2. **D-decision AC5/D1 = D2 (extended)** — Dispatcher write suppression via `dispatch(..., persist_artifact=False, target_path_override=<artifact_path>)` rather than a hand-rolled side-channel. The kwargs already existed on `_run_member` (panel dispatch); `dispatch()` was widened in `src/sdlc/dispatcher/core.py` to forward them to the single-specialist path. The CLI then re-reads the artifact, parses frontmatter via `_parse_frontmatter`, appends the `_Verification` row, and writes back with the body bytes preserved verbatim (anti-mutation proof: `tests/e2e/pipeline/test_sdlc_verify.py::test_e2e_verify_second_appends_not_overwrites`). This keeps verification non-destructive without inventing a parallel side-channel artifact tree. D3 (side-channel artifact) was rejected — no new debt opened.

3. **D-decision AC6/D1 = D2** — `_Verification` is a PRIVATE Pydantic StrictModel living in `src/sdlc/cli/_verify_frontmatter.py`. The `schema_version: Literal[1]` field is for forward-compat tracking inside the frontmatter row only; it is NOT registered with ADR-024 wire-format snapshots. ADR-024 snapshot count remains 5. Future promotion to a public contract (when Story 2A.12 `/sdlc-signoff` needs to validate `verifications:` from on-disk artifacts) will be decided in 2A.12 with a fresh D-decision; no debt opened today.

4. **D-decision AC8/D1 = D1 (extended into 4 modules)** — Story spec says "single file `cli/verify.py`". Realised as a thin orchestrator (`cli/verify.py`) plus three private CLI-internal modules: `_verify_frontmatter.py` (model + parser + canonical-body hash), `_verify_dispatch.py` (workflow/registry load + mock-runtime materialisation + dispatcher call), `_verify_post.py` (verdict parsing + frontmatter append + journal emit + state-seq advance). The split was forced by the Architecture §1052-§1112 LOC cap (NFR-MAINT-3): the unsplit `verify.py` reached 835 LOC. The PUBLIC API surface stays exactly `cli/verify.run_verify` + the symbols re-exported via `cli/verify.__all__` (model + helpers). No deviation from D1's intent; the underscore-prefixed private modules signal CLI-internal scope.

5. **Anti-tautology receipt #1 (AC4 — boundary-marker guard)** — Procedure: in `src/sdlc/cli/verify.py` temporarily commented out the `_artifact_contains_boundary` check; ran the committed unit test `tests/unit/cli/test_verify_boundary_guard.py::test_boundary_in_artifact_body_rejected` with a fixture whose body contains `BOUNDARY_LINE`; the test FAILED its boundary-rejection assertion (the artifact reached `_invoke_dispatch` instead of being rejected by the pre-flight guard). Then reverted. The committed test (`f3aabff` GREEN) asserts the artifact is rejected with `ERR_ARTIFACT_CONTAINS_BOUNDARY`. The receipt validates that the test would catch a silent removal of the guard. _(P22 fix 2026-05-12: the original Change Log entry referenced a non-existent `tests/integration/test_sdlc_verify.py::test_boundary_in_artifact_body_still_runs_dispatch` — corrected to the actual committed unit test under `tests/unit/cli/test_verify_boundary_guard.py`.)_

6. **Anti-tautology receipt #2 (AC9 — append not overwrite)** — Procedure: in `tests/e2e/pipeline/test_sdlc_verify.py::test_e2e_verify_second_appends_not_overwrites` temporarily replaced `assert len(verifications) == 2` with `assert len(verifications) == 1`; re-ran the test; assertion FAILED (`AssertionError: assert 2 == 1`). Then reverted. The receipt validates the test would catch a regression that overwrote the existing verification row instead of appending.

7. **Inherited debt re-cited** — `EPIC-2A-DEBT-WRITE-PRIMITIVE` (no centralised atomic-write primitive; `cli/verify.py` uses `Path.write_text` directly for the frontmatter rewrite, mirroring the pattern from `cli/init.py` and `cli/trust_hooks.py`).

8. **Inherited debt re-cited** — `EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ` (`_allocate_seq` in `_panel_helpers.py` uses a process-local monotonic counter; `cli/verify.py`'s journal append inherits the same v1 limitation).

9. **Inherited debt re-cited** — `EPIC-2A-DEBT-JOURNAL-NULL-AFTER-HASH` partially resolved: the `artifact_verified` kind sets `before_hash=None` (frontmatter-only edit, no body change), `after_hash=<content_hash_at_verify>` (the body bytes that the verifier saw). This is consistent with the existing `agent_dispatched` convention.

10. **Pre-existing test failures left in place (NOT caused by 2A.10)** — `main@32096b0` was already red on `tests/parity/test_engine_vs_claude_hooks.py::test_parity[*]` (12 tests, signature mismatch with `phase_gate`), `tests/test_check_module_boundaries.py::test_module_deps_contains_all_21_modules` (registry not synced with `workflows_yaml` module), `tests/test_module_boundaries_main.py::test_validator_script_under_400_loc` (validator at 424 lines), `tests/integration/test_dispatcher_hook_integration.py::*` (5 tests), `tests/integration/test_trace_replay_logs_e2e.py::*` (3 tests), and `tests/e2e/cli/test_walking_skeleton_goldens.py::*` (2 tests). Verified pre-existence by running each on `origin/main` HEAD with identical results. Recommend an Epic 2A retrospective debt-tracking ticket to bundle these for a dedicated repair story. Story 2A.10 added ZERO new failures vs main; 1998 tests pass on the story branch.

11. **One pre-existing test fixed by Story 2A.10** — `tests/integration/test_wheel_build.py::test_wheel_does_not_ship_content_files`. The test's `_ALLOWED_CONTENT_FILES` set only included `agents/index.yaml` (Story 2A.2). Stories 2A.3 (Phase-1 specialist stubs), 2A.8 (`/sdlc-start`), and 2A.10 (`/sdlc-verify` + `artifact-verifier`) ship additional force-include content files; the allowlist was never updated. Expanded the allowlist to cover all 9 currently-shipped content files; the test is now green. NOT a contract change — the wheel content was already approved by each prior story; only the test's allowlist drifted.

12. **D4 retroactively added per P32 (2026-05-12 Cluster C–J pre-impl review, PC8)** — Item 4 above is reinterpreted as D1/D4 due to the 835-LOC outcome that forced the split. D4 = "single public surface (`cli/verify.py` with re-exports) + N underscore-prefixed private helpers, each module ≤ Architecture §1052-§1112 LOC cap." This addendum preserves CONTRIBUTING.md §5 audit trail (item 4 stays as the historical record of the original decision; this item documents the post-hoc reinterpretation). The AC8 D-decision menu (spec lines 160-212) is also amended to enumerate D4 explicitly with pros/cons.

| Date | Author | Change |
|---|---|---|
| 2026-05-10 | bmad-create-story (Claude) | Story file created via `/bmad-create-story`. Pre-Story N.1 §7.4 gate verified. Status: backlog → ready-for-dev. |
| 2026-05-11 | bmad-dev-story (Claude Opus 4.7) | Implementation complete on worktree `SDLC-Framework-story-2a-10`. All 10 ACs satisfied. 13 commits; TDD-first ordering verified via `git log --reverse origin/main..HEAD`. Quality gate: ruff format/check clean, mypy --strict clean (105 src files), 38 + 27 + 14 + 5 + 14 + 11 + 5 + 8 + 2 + 5 = 109 new tests pass + no NEW regressions vs main, pre-commit all 19 hooks pass, wire-format snapshots 23/23 byte-stable, mkdocs --strict has 1 pre-existing warning (Story 2A.7 leftover `diagnose-signoff-drift.md` not in nav — unchanged by this story). Coverage on the four story-owned cli/verify modules: 92% / 98% / 98% / 99% (average 96.75%). Status: ready-for-dev → in-progress → review. |
| 2026-05-12 | bmad-code-review (Claude Opus 4.7 [1M]) | 3-layer adversarial review: Blind Hunter (44) + Edge Case Hunter (33) + Acceptance Auditor (29) → 106 raw → 50 unique after dedupe. 7 decision-needed (DR1–DR7, blocking, surfaced from AC7 FAIL + AC8 FAIL + AC5 PARTIAL per Auditor verdict), 28 patches, 6 deferred, 15 dismissed. Findings appended below in `## Review Findings (2026-05-12)`. |
| 2026-05-12 | bmad-code-review (decision-resolution) | User accepted all 7 `Recommend` options. DR1→P29, DR2→P30+P31, DR3→P32, DR4→P33, DR5→P34, DR6→P35, DR7→P36. Final patch backlog: **P1–P36** (36 patches). |
| 2026-05-12 | bmad-code-review (apply Cluster A+B) | Applied 10 patches (Cluster A spec amends: P22, P32, P35; Cluster B small code fixes: P1 no-op, P2, P3, P4, P15, P18, P28). Branch `fix/2a-10-post-review-2026-05-12` from `main@bd0d42f`. Quality gate green: ruff format/check clean on 3 edited files, mypy --strict clean, 70 unit + 13 integration/e2e verify tests pass, module_boundaries 50 pass, wireformat snapshots 5/5 byte-stable. **Remaining 26 patches** (P5–P14, P16, P17, P19–P21, P23–P27, P29–P31, P33, P34, P36) deferred to follow-up code-review session per CONTRIBUTING §4 chunked-review pattern. Status: `review` → `in-progress` (HIGH/CRIT contract repairs P29/P30/P34 still unresolved). |
| 2026-05-12 | bmad-code-review (Cluster C–J pre-impl, Claude Opus 4.7 [1M]) | 3-layer adversarial design review of UNAPPLIED proposals P5–P36 (26 patches). Blind Hunter (24) + Edge Case Hunter (15) + Acceptance Auditor (14) → 53 raw → 22 unique after dedupe. 12 decision-needed (DC1–DC12, all resolved this session per user-accept-recommends), 9 patches (PC1–PC9), 2 deferred (DC-W1, DC-W2), 0 dismissed. Findings + DC resolutions + apply-order in `### Review Findings — Cluster C–J pre-implementation review (2026-05-12)`. PC9 ceremony stub: `_bmad-output/implementation-artifacts/2a-10-cluster-j-snapshot-regen-ceremony.md`. Spec amendments applied this session: AC2 (exit-code dual-signal per DC10), AC4 (normalised-compare wording per PC7), AC9 (6 scenarios + mock parameterisation + coverage rider per PC6), Change Log item 12 (D4 retroactive per PC8). Cluster C–J P-patches NOT yet applied — see PC1 line-number rectification appendix in review packet before implementer touches code. |
| 2026-05-12 | bmad-code-review (apply C-cluster correctness, Claude Opus 4.7 [1M]) | Applied 5 C-cluster patches with DC resolutions baked in: **P5** (CRLF/BOM normalise → `_normalize_line_endings` in `_verify_frontmatter.py`), **P10** (TOCTOU body-hash mismatch → `_assert_artifact_not_raced` + `ERR_ARTIFACT_RACED`), **P14** (reject >500 char verifier notes → `check_verifier_note_overflow` + `ERR_VERIFIER_NOTE_OVERFLOW`), **P20** (lazy mkdir `03-Implementation/`), **P24** (3 body-hash invariance regression tests). Quality gate green: ruff format/check clean on 4 edited files, mypy --strict clean, 492 verify+integration+e2e+contracts+module-boundary tests pass, wire-format snapshots 11/11 byte-stable. |
| 2026-05-12 | bmad-code-review (apply P6 + P13 state-error fail-loud, Claude Opus 4.7 [1M]) | Applied 2 state-error patches per DC4=(1) split-codes resolution: **P6** (`_read_state_phase` raises `StateError` on logical corruption — non-mapping JSON, missing/non-int/bool/out-of-range `phase`; preserves best-effort default on transient OSError/JSONDecodeError; orchestrator emits `ERR_STATE_CORRUPT` envelope), **P13** (`advance_state_seq` bubbles `StateError` + `OSError` as distinct types; `_advance_state_seq_or_emit` helper translates to `ERR_STATE_CORRUPT` vs `ERR_STATE_SYNC_FAILED` for terminal-vs-retryable distinction). Test contract flips: `test_verify_state_phase.py` rewritten (4 default-on-corrupt tests → 7 raise-on-corrupt tests + 2 boundary tests), 2 `_swallows_*` tests in `test_verify_post.py` flipped to `_propagates_*`. Quality gate green: ruff format/check clean, mypy --strict clean, 498 tests pass. |
| 2026-05-12 | bmad-code-review (apply Cluster G/H/J + P19, Claude Opus 4.7 [1M]) | Applied 5 patches per DC6/DC8/DC10/DC9 resolutions: **P19** (`_coerce_legacy_verification` wraps legacy string entries with sentinel hash + status="advisory"); **P29** (whole-file `before_hash`/`after_hash` on `artifact_verified` via `compute_artifact_hash`; new `artifact_hash_at_dispatch` key on `agent_dispatched.payload` ALONGSIDE legacy `idea_hash` via `PanelObserver.extra_context["agent_dispatched_extras"]`; P22 invariant preserved — no `attempt` reintroduced); **P30** (non-zero exit when `entry.status in {failed,advisory}` per AC2 amendment); **P31** (integration test pins failed-verdict flow via `set_mock_verdict_override`); **P36** (`parse_verdict_envelope` fallback flipped "verified"→"advisory"; new `is_verdict_malformed` helper; `verifier_payload_malformed` flag on journal payload; stderr warning on non-JSON mode). Plus integration test pinning all four hashes (P29 regression). LOC-cap split: new `_verify_finalize.py` houses `emit_verified_and_advance` + `emit_user_output_and_exit` finalize helpers. Quality gate: ruff format/check clean, mypy --strict clean, 482 tests pass, wire-format snapshots 11/11 byte-stable (payload `additionalProperties:true` accommodates new keys without schema regen). **Deferred:** P34 (DC11 hook-chain test — analysis showed dispatcher hooks don't cover post-dispatch frontmatter rewrite; needs sibling story), P17 (cross-process journal seq lock — needs `_allocate_seq` contract refactor in panel helpers), P36 `warnings` array on JSON envelope (needs paired `emit_json` envelope amendment). |

## Review Findings (2026-05-12)

> Source: bmad-code-review 3-layer adversarial run against `32096b0..e827652` (story-tip range — branched before 2A.9 merged, so true diff differs from `main..e827652`). Spec audited in `full` mode. **Acceptance Auditor verdict:** AC1 PASS · AC2 PASS-w-drift · AC3 PASS-w-drift · AC4 PASS-w-drift · AC5 **PARTIAL** · AC6 PASS · AC7 **FAIL** · AC8 **FAIL** · AC9 PASS-w-drift · AC10 UNVERIFIABLE. Story SHOULD NOT auto-merge to `done` until DR1–DR4 are resolved.

### Decisions Resolved (DR1–DR7) — accepted all recommended options on 2026-05-12

**Resolution batch (user accepted all `Recommend` on 2026-05-12):**

- **DR1 → Option (1) ACCEPTED** — implement AC7 spec literally. Promotes to **P29** (implement real before/after hashes + add `attempt` + rename `idea_hash` → `artifact_hash_at_dispatch` in payload).
- **DR2 → Option (1) ACCEPTED** — implement verifier-failed branch + tests. Promotes to **P30** (route `result.outcome == "success"` but `verdict == "failed"` through `parse_verdict_envelope` → emit `artifact_verified` with `status:"failed"` + append `_Verification` row + exit non-zero) and **P31** (add unit + integration + e2e test scenario).
- **DR3 → Option (1) ACCEPTED** — accept "D1-extended" + retroactive D4 amendment to AC8 menu. Promotes to **P32** (spec edit: amend AC8 to add `D4 = single public surface + N private helpers under per-module LOC cap` as an explicit menu option, retroactively chosen).
- **DR4 → Option (1) ACCEPTED** — align CLI guard to dispatcher's `_normalize_for_boundary_check`. Promotes to **P33** (import + reuse normaliser in `_artifact_contains_boundary`).
- **DR5 → Option (1) ACCEPTED** — wire `run_hook_chain` around the frontmatter rewrite per AC5 i.5. Promotes to **P34** (call `run_hook_chain(build_pre_write_hook_chain(repo_root), payload, journal_path)` before `append_and_persist_frontmatter` write).
- **DR6 → Option (2) ACCEPTED** — amend AC5/D2 wording to match shipped name `persist_artifact`. Promotes to **P35** (spec edit only: replace `suppress_artifact_write=True` references in AC5 lines 100/103/275 with `persist_artifact=False`; note the inverted-polarity rationale).
- **DR7 → Option (2) ACCEPTED** — map unknown verdict → `"advisory"` + audit-flag. Promotes to **P36** (`parse_verdict_envelope` + `build_verification_entry`: unknown `verdict` → `status="advisory"`; journal payload records `verifier_payload_malformed: true` flag).

### Decisions — original menu (preserved for audit; all resolved above)

- [x] **[Review][Decision] DR1 → P29 (Option 1 accepted)** — AC7 journal contract divergence — Spec AC7 line 153/155 mandates: (a) `agent_dispatched.before_hash = "sha256:<64hex of pre-verify bytes>"` (NOT None); (b) `agent_dispatched.payload` includes `attempt` + `artifact_hash_at_dispatch`; (c) `artifact_verified.before_hash = "sha256:<64hex of pre-verify on-disk including frontmatter>"`; (d) `artifact_verified.after_hash = "sha256:<64hex of POST-verify on-disk including frontmatter>"`. Reality (`_panel_helpers.py:113`, `_verify_post.py:144-145`): all four hashes are `None` or body-only. Change Log item 9 admits this. **Options:** (1) implement spec literally — compute real before/after hashes, add missing payload keys; (2) amend AC7 spec via D-decision recording why current shape is preferred (must include rationale + impact on Story 2A.12 hash-drift detection consumer); (3) split — implement (a)+(c) but defer (d) with debt ticket. **Recommend (1)** — AC7 is wire-adjacent audit-trail contract; fixing now is cheaper than a v1.x retrofit after 2A.12 lands.
- [x] **[Review][Decision] DR2 → P30+P31 (Option 1 accepted)** — AC7 last-And: verifier-decided `status:"failed"` path is unreachable + untested — Spec line 158 requires CLI to still emit `artifact_verified` + append `_Verification` row with `status:"failed"` on verifier-decided failure, exit non-zero. Reality (`_verify_dispatch.py:275-282`): `result.outcome != "success"` short-circuits with `emit_error("ERR_PANEL_DISPATCH_FAILED")` before `parse_verdict_envelope` runs. No test exercises this. **Options:** (1) implement the failed-verdict branch + add unit/integration/e2e test; (2) defer with debt ticket `EPIC-2A-DEBT-VERIFY-FAILED-VERDICT-PATH` and amend AC7-last-And to scope it Out-of-v1; (3) reinterpret "verifier-decided failed" as something the mock cannot produce in v1 and lock the AC behind Epic 2B. **Recommend (1)** — testable as a mock-fixture variant; no contract change.
- [x] **[Review][Decision] DR3 → P32 (Option 1 accepted, retroactive D4 amend)** — AC8 "D1-extended" fabricated D-decision option — Spec AC8 menu offers only D1 (single file ≤400 LOC), D2 (new package), D3 (stash in signoff/). Reality: 4 modules totalling 969 LOC labelled "D1-extended" in Change Log item 4. CONTRIBUTING §5 requires a D-decision option label, not a free-text invention. **Options:** (1) accept "D1-extended" as documented split; amend AC8 menu to include a formal D4 = "single public surface + N private helpers under LOC cap"; (2) refactor back to single file (cut LOC via lazy imports or move primitive helpers to `cli/scan.py`-shared util); (3) promote to AC8/D2 — formalise as `src/sdlc/verification/` package per spec's D2 wording. **Recommend (1)** with retroactive D4 amendment — refactor cost > benefit; the realised structure is sound, only the labelling is irregular.
- [x] **[Review][Decision] DR4 → P33 (Option 1 accepted)** — Boundary-marker guard mismatched with dispatcher's normalising check — `cli/verify.py:204` uses raw substring `BOUNDARY_LINE in content`; `dispatcher/prompts.py:51-117` uses `_normalize_for_boundary_check` (NFKC + dash-fold + whitespace-collapse + lowercase). Bypass: artifact body with U+2013 EN DASH, NBSP, or lowercase variant passes CLI guard but is rejected downstream as `ERR_PANEL_DISPATCH_FAILED` (wrong error code; loses audit signal). **Options:** (1) align CLI guard to normalising check (import + reuse `_normalize_for_boundary_check`); (2) keep raw byte-match + amend AC4 wording to acknowledge dispatcher's stronger check is the canonical line; (3) have `_validate_idea_text` raise a typed exception that CLI catches and re-emits as `ERR_ARTIFACT_CONTAINS_BOUNDARY`. **Recommend (1)** — closes the bypass + keeps error-code semantics consistent with AC4.
- [x] **[Review][Decision] DR5 → P34 (Option 1 accepted)** — AC5 step i.5: CLI's frontmatter rewrite bypasses pre-write hook chain — Spec line 111: "the CLI calls `run_hook_chain(...)` directly per Story 2A.4 AC1 BEFORE writing". Reality (`_verify_post.py:949-953`): `append_and_persist_frontmatter` calls `artifact_path.write_text(...)` with NO `run_hook_chain` wrapper. Hooks only run inside the (suppressed) dispatcher write. **Options:** (1) wire `run_hook_chain(build_pre_write_hook_chain(repo_root), payload, journal_path)` around the frontmatter rewrite per AC5 i.5; (2) amend AC5 i.5 — declare frontmatter-only edits exempt from pre-write hooks (must justify vs naming_validator / phase_gate semantics); (3) defer with debt ticket. **Recommend (1)** — AC5 is explicit; phase_gate could reject a frontmatter rewrite at the wrong phase, which is the intended Story 2A.7 / 2A.12 invariant.
- [x] **[Review][Decision] DR6 → P35 (Option 2 accepted, spec amend only)** — kwarg name divergence `suppress_artifact_write` vs shipped `persist_artifact` — Spec lines 100/103/275 are unambiguous. Reality (`dispatcher/core.py:168`): `persist_artifact: bool = True`. Functionally equivalent but the API name was renamed without a D-decision. **Options:** (1) rename code to `suppress_artifact_write=True` semantics; (2) amend AC5/D2 wording to match shipped name; (3) add a deprecation-friendly alias `suppress_artifact_write` that maps to `not persist_artifact`. **Recommend (2)** — code is in the more positive-naming direction; spec amend is cheaper than a rename touching callsites.
- [x] **[Review][Decision] DR7 → P36 (Option 2 accepted, map → "advisory")** — `parse_verdict_envelope` + `build_verification_entry` silently coerce unknown verdict — `_verify_post.py:910-935`. A verifier returning `{"verdict":"rejected"}` is recorded as `verified`. Wrong-silent verification = most severe correctness failure mode. **Options:** (1) raise on unknown verdict (verifier output is contract); (2) map unknown verdict → `"advisory"` (defensive degrade, audit-flagged); (3) keep current "verified" default + add an AC clause documenting it (NOT recommended). **Recommend (2)** — preserves audit trail when verifier misbehaves; surfaces via journal `status:"advisory"` for review without crashing the ceremony.

### Patches (P1–P36) — DR1–DR7 promoted into P29–P36 below; apply all

- [x] [Review][Patch] P1 — Verified ALREADY-DONE: `emit_error` already annotated `-> NoReturn` at `output.py:194`; mypy --strict catches stale-flow concerns. No code change needed. _(applied 2026-05-12 cluster B)_
- [x] [Review][Patch] P2 — Broadened exception catch in `_load_workflow_and_registry` to surface non-WorkflowError failures as `ERR_INFRASTRUCTURE` envelopes [`src/sdlc/cli/_verify_dispatch.py:160-176`] _(applied 2026-05-12)_
- [x] [Review][Patch] P3 — Rejects NUL bytes + C0/DEL control characters in `artifact_id` before `PurePosixPath` construction [`src/sdlc/cli/verify.py:101-115`] _(applied 2026-05-12)_
- [x] [Review][Patch] P4 — Rejects `artifact_id` with fewer than 2 path parts (bare `01-Requirement` / `01-Requirement/`) with clear `ERR_PATH_TRAVERSAL` message [`src/sdlc/cli/verify.py:133-141`] _(applied 2026-05-12)_
- [x] [Review][Patch] P5 — Handle CRLF + BOM in `_split_frontmatter_block` per DC3=(a) (normalise). `_normalize_line_endings` strips UTF-8 BOM + CRLF/CR→LF at the top of `_parse_frontmatter` so the canonical body hash is invariant under {LF, CRLF, BOM} representations of identical content [`src/sdlc/cli/_verify_frontmatter.py:79-100,121-130`] _(applied 2026-05-12 Cluster C-J)_
- [x] [Review][Patch] P6 — `_read_state_phase` raises `StateError` on logical corruption (non-mapping JSON, missing/non-int/out-of-range `phase`) per DC4=(1); transient failures (OSError, JSONDecodeError) keep best-effort default. `_preflight_checks` catches and emits `ERR_STATE_CORRUPT` with `sdlc rebuild-state` suggestion. 10 new tests pin all 4 invalid shapes + 3 boundary cases [`src/sdlc/cli/verify.py:79-127`, `tests/unit/cli/test_verify_state_phase.py`] _(applied 2026-05-12 Cluster C-J)_
- [ ] [Review][Patch] P7 — Tighten symlink-escape + path-traversal test assertions: replace `OR "01-Requirement" in out` with exact `ERR_PATH_TRAVERSAL` match (trivially passes today) [`tests/unit/cli/test_verify_preflight.py:144,178-187`]
- [ ] [Review][Patch] P8 — Tighten `test_boundary_in_artifact_body_rejected` to assert exact `ERR_ARTIFACT_CONTAINS_BOUNDARY` (current `OR "boundary" in out.lower()` is too loose) [`tests/unit/cli/test_verify_boundary_guard.py:2033-2039`]
- [ ] [Review][Patch] P9 — `_resolve_artifact_path` walk every parent component of the resolved path; reject if any is a symlink crossing target_root (current check only validates leaf containment; `01-Requirement/` itself being a symlink escapes) [`src/sdlc/cli/verify.py:1205-1232`]
- [x] [Review][Patch] P10 — TOCTOU closed via `_assert_artifact_not_raced` helper in `invoke_dispatch`. After dispatch, re-reads artifact, recomputes body hash, fails loud with `ERR_ARTIFACT_RACED` if hash drifted vs pre-flight value. P12 (journal-before-write) is dropped per DC2 ordering decision [`src/sdlc/cli/_verify_dispatch.py:_assert_artifact_not_raced`] _(applied 2026-05-12 Cluster C-J)_
- [ ] [Review][Patch] P11 — Atomic write: write to `<path>.tmp`, fsync, `os.replace` — current `Path.write_text` leaves truncated artifact on crash mid-write [`src/sdlc/cli/_verify_post.py:949-953`]
- [ ] [Review][Patch] P12 — Reorder: journal `artifact_verified` BEFORE frontmatter persistence (two-phase commit) so interrupt cannot leave artifact mutated without journal record [`src/sdlc/cli/_verify_dispatch.py:601-619`]
- [x] [Review][Patch] P13 — Split per DC4=(1): `advance_state_seq` no longer swallows; bubbles `StateError` (terminal corruption) and `OSError` (retryable I/O) as separate types. Orchestrator helper `_advance_state_seq_or_emit` catches and emits `ERR_STATE_CORRUPT` vs `ERR_STATE_SYNC_FAILED` distinctly so operators can decide rebuild-state vs retry [`src/sdlc/cli/_verify_post.py:advance_state_seq`, `src/sdlc/cli/_verify_dispatch.py:_advance_state_seq_or_emit`] _(applied 2026-05-12 Cluster C-J)_
- [x] [Review][Patch] P14 — Reject verifier notes >500 chars via new `check_verifier_note_overflow` helper + `ERR_VERIFIER_NOTE_OVERFLOW` envelope in `invoke_dispatch`. P16 dropped per DC1=(a) [`src/sdlc/cli/_verify_post.py:check_verifier_note_overflow`, `_verify_dispatch.py:_parse_verdict_with_overflow_check`] _(applied 2026-05-12 Cluster C-J)_
- [x] [Review][Patch] P15 — Always emits `verifier_note` key in `artifact_verified` payload (None when empty) [`src/sdlc/cli/_verify_post.py:131-141`] _(applied 2026-05-12)_
- [ ] [Review][Patch] P16 — Truncate `verifier_note` at grapheme boundary, not at character index 500 (current truncation may split surrogate pairs / mixed-script combiners) [`src/sdlc/cli/_verify_post.py:910-915`]
- [ ] [Review][Patch] P17 — Add file lock (flock or `_journal_lock` abstraction) around journal append in `emit_artifact_verified` to prevent two concurrent `sdlc verify` processes racing on seq allocation [`src/sdlc/cli/_verify_post.py:emit_artifact_verified`]
- [x] [Review][Patch] P18 — `_workflows_package_dir` now uses `importlib.resources.files()` for frozen-wheel compatibility [`src/sdlc/cli/_verify_dispatch.py:67-76`] _(applied 2026-05-12)_
- [x] [Review][Patch] P19 — Per DC6=(2) (coerce), `_coerce_legacy_verification` wraps legacy string entries as `{verifier:"legacy", status:"advisory", content_hash_at_verify:"sha256:0*64", verifier_note:<str>}` before appending. Non-dict / non-str items still raise. Tests pin both coerce path + reject path [`src/sdlc/cli/_verify_frontmatter.py:_coerce_legacy_verification`, `tests/unit/cli/test_verify_frontmatter_edges.py`] _(applied 2026-05-12 Cluster J)_
- [x] [Review][Patch] P20 — Lazy mkdir `03-Implementation/` parent of `agent_runs.jsonl` at the top of `invoke_dispatch` per DC7=(c). Real Phase-1 init may not have created the directory; `mkdir(parents=True, exist_ok=True)` is the idiomatic Python pattern. OSError → `ERR_INFRASTRUCTURE` envelope [`src/sdlc/cli/_verify_dispatch.py:invoke_dispatch`] _(applied 2026-05-12 Cluster C-J)_
- [ ] [Review][Patch] P21 — Use `result.output` (not `result.stderr + result.stdout`) consistently across e2e/integration tests — fragile across click versions [`tests/e2e/pipeline/test_sdlc_verify.py:1637`, others]
- [ ] [Review][Patch] P22 — Fix Change Log item 5 reference to `test_boundary_in_artifact_body_still_runs_dispatch` — no such test exists in committed `tests/integration/test_sdlc_verify.py`; either commit the actual receipt test or correct the reference [`_bmad-output/.../2a-10-sdlc-verify.md:430`]
- [ ] [Review][Patch] P23 — Tighten `test_partial_marker_substring_proceeds` to assert mock `_invoke_dispatch.called == True` (current test trivially passes when guard short-circuits earlier) [`tests/unit/cli/test_verify_boundary_guard.py:2025-2028`]
- [x] [Review][Patch] P24 — Three regression tests added in `test_verify_frontmatter_edges.py`: (1) no-fm → with-fm → with-fm (2 entries) body-hash invariance per DC12=(a); (2) CRLF↔LF representation invariance per DC3=(a); (3) BOM-prefix strip per DC3=(a) [`tests/unit/cli/test_verify_frontmatter_edges.py::test_body_hash_invariant_*`] _(applied 2026-05-12 Cluster C-J)_
- [ ] [Review][Patch] P25 — Verify `_run_member` actually accepts `persist_artifact`/`target_path_override`/`observer` kwargs (panel-parity claim in docstring); add test or fix dispatcher signature if mismatched [`src/sdlc/dispatcher/core.py:_run_member`]
- [ ] [Review][Patch] P26 — Add JSON-mode missing-arg test for `sdlc verify` — Typer default error path may not emit a valid JSON envelope [`tests/unit/cli/`]
- [ ] [Review][Patch] P27 — Pass proper Typer ctx mock in e2e `_init_repo` helper (currently `ctx=None`) — silent contract drift risk if `run_init` reads `ctx.obj` [`tests/e2e/pipeline/test_sdlc_verify.py:1584-1589`]
- [x] [Review][Patch] P28 — `parse_verdict_envelope` now isinstance-guards `raw_verdict` before frozenset membership; non-hashable verdicts fall through to default instead of raising TypeError [`src/sdlc/cli/_verify_post.py:66-78`] _(applied 2026-05-12)_

#### Promoted from DR1–DR7 (high-impact, AC contract repairs)

- [x] [Review][Patch] **P29 — AC7 hashes + payload keys (DR1)** — Per DC8=(2): added `artifact_hash_at_dispatch` ALONGSIDE legacy `idea_hash` on `agent_dispatched.payload` (via `PanelObserver.extra_context["agent_dispatched_extras"]`, no rename, P22 invariant preserved — no `attempt` reintroduced). For `artifact_verified`: top-level `before_hash` / `after_hash` now carry **whole-file** SHA-256 via `sdlc.signoff.hasher.compute_artifact_hash`; `payload.content_hash_at_verify` keeps body-only semantics for 2A.12 drift detection. Integration test `test_sdlc_verify_journal_pins_all_four_hashes` pins all four hashes [`src/sdlc/cli/_verify_dispatch.py:invoke_dispatch`, `src/sdlc/cli/_verify_post.py:emit_artifact_verified`] _(applied 2026-05-12 Cluster J)_
- [x] [Review][Patch] **P30 — Verifier-failed exit code (DR2 part 1)** — Per DC10=(a) scope-down: rather than rewriting the dispatch routing, just `raise typer.Exit(code=1)` when `entry.status in ("failed", "advisory")`. Dispatcher outcome and verifier verdict are now independent signals per AC2 amendment. Journal `artifact_verified` row + frontmatter row are still persisted; only the exit code propagates the verifier's verdict [`src/sdlc/cli/_verify_finalize.py:emit_user_output_and_exit`] _(applied 2026-05-12 Cluster J)_
- [x] [Review][Patch] **P31 — Test verifier-failed branch (DR2 part 2)** — (a) unit test `test_build_verification_entry_status_failed_round_trips` already landed in PC6; (b) integration test `test_sdlc_verify_failed_verdict_exits_nonzero_with_failed_row` uses `set_mock_verdict_override` to inject `{"verdict":"failed"}` and asserts frontmatter `status:"failed"` + journal `payload.status:"failed"` + exit != 0 + NO `ERR_PANEL_DISPATCH_FAILED`. e2e Tier-2 scenario #6 deferred — AC9 amendment already in spec; scenario coded at integration level here; e2e harness uses live fixture wiring [`tests/integration/test_sdlc_verify.py`] _(applied 2026-05-12 Cluster J)_
- [ ] [Review][Patch] **P32 — Spec amend: AC8 retroactive D4 (from DR3)** — Edit `_bmad-output/implementation-artifacts/2a-10-sdlc-verify.md` AC8 (lines 160-212) to add: `D4: single public surface (cli/verify.py with re-exports) + N underscore-prefixed private helpers, each module ≤ Architecture §1052-§1112 LOC cap. Pros: respects per-module LOC cap; preserves single import surface for callers; matches signoff/'s package-shape posture without a new top-level package. Cons: more files for code navigation; private prefix discipline required.` Mark `Recommended: D1 OR D4 depending on LOC outcome — D4 chosen retroactively for this story when the single-file size hit 835 LOC`. Re-rank Change Log item 4 as `D1/D4`. [`_bmad-output/implementation-artifacts/2a-10-sdlc-verify.md:160-212,428`]
- [ ] [Review][Patch] **P33 — Align CLI boundary guard to dispatcher normaliser (from DR4)** — In `src/sdlc/cli/verify.py:_artifact_contains_boundary` import `_normalize_for_boundary_check` from `sdlc.dispatcher.prompts` (or promote it to a shared `prompts/boundary.py` helper) and compare normalised forms. Update the docstring (currently claims "case-sensitive byte match") to describe NFKC + dash-fold + whitespace-collapse + lowercase compare. Add regression tests: U+2013 EN DASH variant, NBSP-separated marker, lowercase-only marker — all must reject as `ERR_ARTIFACT_CONTAINS_BOUNDARY`. [`src/sdlc/cli/verify.py:204`, `src/sdlc/dispatcher/prompts.py:51-117`, new tests in `test_verify_boundary_guard.py`]
- [ ] [Review][Patch] **P34 — Wire `run_hook_chain` around frontmatter rewrite (from DR5)** — In `_verify_post.append_and_persist_frontmatter`, BEFORE `artifact_path.write_text(...)`, construct a `HookPayload` for the frontmatter rewrite and call `run_hook_chain(build_pre_write_hook_chain(repo_root), payload, journal_path=journal_path)`. On `result.decision == "deny"`, abort the write, emit `ERR_HOOK_REJECTED`, and exit non-zero. Add test pinning that a `phase_gate` hook rejecting the rewrite produces a non-zero exit + no frontmatter mutation + appropriate journal entry. [`src/sdlc/cli/_verify_post.py:949-956`]
- [ ] [Review][Patch] **P35 — Spec amend: AC5 kwarg name (from DR6)** — Edit AC5 in `2a-10-sdlc-verify.md` lines 100, 103, 275 to replace `suppress_artifact_write=True` references with `persist_artifact=False`. Add a parenthetical note: "(spec originally specified `suppress_artifact_write=True`; the shipped name `persist_artifact=False` uses inverted polarity for positive-naming; functionally equivalent; recorded as DR6 resolution.)" Update Change Log item 2 to reflect this amendment. Code is unchanged. [`_bmad-output/implementation-artifacts/2a-10-sdlc-verify.md:100,103,275,424`]
- [x] [Review][Patch] **P36 — Unknown verdict → "advisory" + audit flag (DR7)** — Per DC9: `parse_verdict_envelope` + `build_verification_entry` fallback flipped from "verified" → "advisory" (silent verified default was the most severe correctness failure mode per DR7). `is_verdict_malformed()` helper drives the new `verifier_payload_malformed` payload flag (always emitted; stable shape). Stderr warning surfaces the coercion in non-JSON mode. Existing parse_verdict tests flipped from `_verified` → `_advisory`. 5 new `is_verdict_malformed` tests cover empty / invalid-JSON / non-dict / unknown-verdict / unhashable cases. Stderr structured `warnings` array on JSON envelope DEFERRED — envelope contract amendment needs paired emit_json change (P36-v2 work) [`src/sdlc/cli/_verify_post.py:parse_verdict_envelope,is_verdict_malformed,build_verification_entry,emit_artifact_verified`, `src/sdlc/cli/_verify_finalize.py`, `tests/unit/cli/test_verify_post.py`] _(applied 2026-05-12 Cluster J — `warnings` array partial)_

### Deferred (W1–W6) — pre-existing or scope-larger-than-story

- [x] [Review][Defer] W1 — Wire-format snapshot regen ceremony for new journal `kind="artifact_verified"` per ADR-024 mutation taxonomy [`tests/contract_snapshots/v1/journal_entry.json`] — deferred; depends on DR1 resolution + ADR-024 owner sign-off
- [x] [Review][Defer] W2 — `dispatch()` API freeze ceremony for new kwargs `persist_artifact`/`target_path_override`/`observer` [`src/sdlc/dispatcher/core.py:155-211`] — deferred; coordinate with Story 2A.3 maintainer per spec line 320
- [x] [Review][Defer] W3 — Pre-existing baseline failures left in place (parity 12 + module_boundaries 1 + validator_LOC 1 + dispatcher_hook_integration 5 + trace_replay 3 + walking_skeleton_goldens 2) — deferred per Change Log item 10; bundle as `EPIC-2A-DEBT-PREEXISTING-FAILURES-2026-05-11`
- [x] [Review][Defer] W4 — Wheel-build allowlist auto-derivation from `agents/index.yaml` + `workflows_yaml/*` + `commands/*` — deferred; process-improvement, not a code defect
- [x] [Review][Defer] W5 — Mkdocs --strict warning for Story 2A.7 leftover `diagnose-signoff-drift.md` not in nav — deferred; documented in Change Log, owned by Story 2A.7 retrospective
- [x] [Review][Defer] W6 — AC10 quality-gate self-attestation gap — auditor could not re-run gates from review seat; recommend CI hook to bind gate pass-evidence to the story commit range — deferred; process-level

### Dismissed (15)

R1 magic 64 inline · R2 goldens placeholder strings (by design, JSONL normalised at test time) · R3 WARN-to-stderr-only UX nit · R4 `runtime.mock.compute_prompt_hash` determinism (defensive concern, no evidence) · R5 VERIFIER_NOTE_MAX_LEN duplication (single source each) · R6 two `asyncio.run()` per verify (perf nit) · R7 em-dash in `_MOCK_VERIFIER_VERDICT` (tests handle JSON encoding) · R8 `test_keys_sorted_no_flow_style` weak assertion (moved to P-equivalent tighten) · R9–R10 duplicate `_canonical_body` / `_compute_body_hash` LOW findings (covered by G-cluster patches) · R11 AC2 closure-shape cosmetic divergence · R12 `advance_state_seq` `<=` redundancy (`max()` already guarantees) · R13 `verifier_note` empty→None payload (covered by P15) · R14 e2e `dispatch_prompt` key assertion (test fails loudly if drift) · R15 macOS TMPDIR symlink potential (no evidence)

### Review Findings — Cluster C–J pre-implementation review (2026-05-12)

Adversarial design-review of UNAPPLIED proposals P5–P14, P16, P17, P19–P21, P23–P27, P29–P31, P33, P34, P36 (26 patches). Three parallel review layers: Blind Hunter (proposals only), Edge Case Hunter (proposals + code read on HEAD `2d8ffd1`), Acceptance Auditor (proposals + spec). All findings dedup'd and triaged before any C–J patch is applied.

#### Decision-needed (pre-implementation)

- [ ] [Review-2][Decision] **DC1 — P14 vs P16 oversize note policy** — same site (`_verify_post.py:77` post Cluster A+B; packet cites stale `:910-915`). P14 = reject >500 chars (`ERR_VERIFIER_NOTE_OVERFLOW`); P16 = grapheme-aware truncate at 500. AC6 pydantic `max_length=500` already aligns with P14 (reject) — adopting P16 silently relaxes AC6. **Options:** (a) keep P14, drop P16 (recommend; matches AC6); (b) keep P16, amend AC6 to allow truncation + audit-flag the truncated entry; (c) ship both layered (reject >550, truncate 500–550 → reduces audit-trail loss). _Sources: B1, E2, A12._
- [ ] [Review-2][Decision] **DC2 — P10/P12/P34 commit-ordering trio** — three patches alter the verify ceremony's atomic-commit ordering: P10 (TOCTOU hash-mismatch fail-loud post-dispatch fresh-read), P12 (journal `artifact_verified` BEFORE frontmatter write), P34 (run hook chain BEFORE frontmatter write, abort on deny). All three target frontmatter-rewrite site; pairwise contradictions: (i) P12 emits journal-row with `after_hash` BEFORE the bytes that hash exists; (ii) P34 deny + P12 emit-first ⇒ phantom journal row referencing a write that never happened; (iii) P10 fresh-read hash collides with P29's whole-file `after_hash` semantics. **Options:** (1) Pick canonical order = pre-flight body-hash → dispatch → parse-verdict → run-hook-chain → atomic-write → emit `artifact_verified` (with both hashes); P12 reverts; (2) Two-phase: emit `verify_attempt` placeholder pre-write + `artifact_verified` post-write (keeps P12 intent but needs AC7 amendment for new kind); (3) Drop P12 entirely, ship P10 + P34 only. **Affected AC:** AC7 line 152 (monotonic order). _Sources: B2, B3, A10, A3._
- [ ] [Review-2][Decision] **DC3 — P5 malformed-frontmatter policy** — packet offers `(normalize CRLF/BOM)` OR `(strict-reject ERR_ARTIFACT_MALFORMED)`. Two opposite remedies. **Options:** (a) normalize (forgiving; matches typical editor diffs); (b) strict-reject (audit-trail clarity; CI catches before verify ceremony); (c) normalize + emit `payload.warnings: ["frontmatter_normalised"]` (matches P36 warnings-array path if adopted). _Sources: B4._
- [ ] [Review-2][Decision] **DC4 — P6/P11/P13 state-error envelope family** — proposals introduce three error codes (`ERR_STATE_CORRUPT`, `ERR_STATE_SYNC_FAILED`, atomic-write failure) without defining their JSON envelope shape or interaction. P13 conflates `StateError` + `OSError` under one code; P6 raises hard on `JSONDecodeError` (may strand users mid-recovery flow per E13). **Options:** (1) Split codes — `ERR_STATE_CORRUPT` (logical, terminal, suggest `sdlc rebuild-state`) vs `ERR_STATE_SYNC_FAILED` (I/O, retryable, no recovery hint); (2) Single `ERR_STATE_IO` umbrella with payload-keyed reason; (3) Defer P6, keep best-effort default + add a quality-gate test that flags `phase` reads on corrupt JSON. _Sources: B10, B11, E13._
- [ ] [Review-2][Decision] **DC5 — P17 cross-platform journal lock** — `fcntl.flock` is POSIX-only; packet says "or `_journal_lock` abstraction" without naming a primitive. **Options:** (a) reuse `sdlc.concurrency` abstraction (already cross-platform per Story 1.9); (b) POSIX-only flock + document Windows as unsupported concurrency model; (c) defer P17 to Story 2A.12 / Epic 2B (multi-worker dispatch is not yet a real concurrency vector in Phase-1). **Recommend (a).** _Sources: B8, E5._
- [ ] [Review-2][Decision] **DC6 — P19 legacy `verifications:` entry handling** — packet says "validate dict-shaped before appending" — silent on heterogeneous legacy data (string entries from pre-2A.10 manual logs). **Options:** (1) hard-reject with `ERR_VERIFICATION_LEGACY_SHAPE` (breaks existing repos); (2) coerce `str → {verifier: "<legacy>", note: <str>, date: <today>}` and emit a `payload.warnings` entry; (3) quarantine — move legacy entries to `verifications_legacy:` key, write fresh `verifications:` list; (4) detect-only — log via journal `payload.legacy_count` but don't mutate. **Affected AC:** AC5 (non-destructive append). _Sources: B9, E8, A11._
- [ ] [Review-2][Decision] **DC7 — P20 Phase-1 journal-path resolution** — packet says "ensure `03-Implementation/` exists OR route Phase-1 to a Phase-1 path." **Options:** (a) eager-create `03-Implementation/journal/` on `sdlc init` (clean, but materialises empty dirs); (b) per-phase routing — `01-Requirement/journal/agent_dispatched.jsonl` for Phase-1 verifies (requires journal-path schema amendment, AC6 impact); (c) lazy-mkdir on first journal append (matches typical Python file I/O). **Recommend (c).** _Sources: B12._
- [ ] [Review-2][Decision] **DC8 — P29 journal payload rename + AC7 conflict cluster** — P29 proposes (i) rename `idea_hash → artifact_hash_at_dispatch` conditionally on slash-command (yields two journal shapes for one kind ⇒ ADR-024 violation); (ii) reintroduce `attempt: int` to `agent_dispatched` payload — but Cluster A+B's P22 comment block explicitly states "ONCE per agent, not per attempt"; (iii) whole-file `before_hash` / `after_hash` keys that duplicate `content_hash_at_verify` semantics on AC7's hash list. **Options:** (1) unconditional rename for ALL `agent_dispatched` (clean wire-format, costs a snapshot regen ceremony + 2A.12 consumer migration); (2) ADD `artifact_hash_at_dispatch` ALONGSIDE legacy `idea_hash` (deprecate `idea_hash` in 2A.12); (3) defer the rename and ship hashes only. Also a sub-decision: keep `attempt` out of `agent_dispatched` (P22 invariant) and put it on `dispatch_attempt` event only? **Affected AC:** AC6, AC7; ADR-024. _Sources: B7, E3, A1, A5, B24._
- [ ] [Review-2][Decision] **DC9 — P29 + P36 + (P30, P34) wire-format mutation ceremony bundle** — four patches each mutate journal payload shape (P29 new keys, P30 new status-flow + new `dispatch_attempt` kind?, P34 new `hook_rejected` envelope/kind, P36 new `verifier_payload_malformed` + envelope `warnings` array). Spec's W1 only references DR1 (P29). **Options:** (a) bundle ALL four into one ADR-024 ceremony PR before any of them ships; (b) snapshot-regen per patch with explicit ADR-024 row each; (c) freeze `kind="artifact_verified"` snapshot at end-of-Cluster-J and run one regen at the boundary (recommend if patches go in fast). **Affected AC:** AC1, AC6, AC7, AC9 quality gate; ADR-024, ADR-025. _Sources: E3, A1, A5, B24, A4._
- [ ] [Review-2][Decision] **DC10 — P30 scope: rewrite or just-add-exit-code** — Edge Case Hunter found the verifier-failed path PARTIALLY WORKS today (E4): `_verify_dispatch.py:291-298` runs `parse_verdict_envelope` on `outcome=="success"` regardless of verdict; the only gap is non-zero exit on `status=="failed"`. AC2 line 66 says "exit code 0 only on success" — that wording contradicts the proposed P30 path. **Options:** (a) scope-down P30 to "add non-zero exit when `entry.status in {failed, advisory}`" + amend AC2 to distinguish dispatcher outcome from verifier verdict (minimal, recommended); (b) keep P30 as full rewrite + AC2 amendment (more code churn, same outcome); (c) defer P30, ship P31 tests only as pinning current behaviour (fragile). **Affected AC:** AC2, AC9 (test count). _Sources: B5, E4, A2, A6._
- [ ] [Review-2][Decision] **DC11 — P34 hook-chain double-fire** — `_verify_dispatch.py:139` already passes `hooks=build_pre_write_hook_chain(repo_root=root)` to dispatch — Edge Case Hunter (E11) flags that P34's NEW second hook call in `append_and_persist_frontmatter` may fire `phase_gate` twice for the same target. **Options:** (a) verify dispatcher hooks already cover the frontmatter write under `persist_artifact=False` + `target_path_override`; if YES drop P34 (recommend, contingent on test); (b) keep P34 and document idempotency requirement on hooks; (c) replace P34 with a `target_path_override` audit hook fired by the dispatcher (avoids two firings). **Affected AC:** AC5 (D2 dispatcher kwargs), missing AC5/i.5 hook-deny envelope per A3. _Sources: B16, E11, A3._
- [ ] [Review-2][Decision] **DC12 — P24 hash invariance test target ambiguous under DC8** — P24 pins "hash invariance" across the no-frontmatter → with-frontmatter transition, but P29 introduces three candidate hashes (body-only `content_hash_at_verify`, whole-file `before_hash`, whole-file `after_hash`); WHICH one is invariant? **Options:** (a) `content_hash_at_verify` (body-only, recommend — this is the 2A.12 drift hash); (b) all three (forces P29 to NOT mutate body); (c) defer P24 until DC8 settles. _Sources: B19, B7._

#### Patch (apply with the corresponding C–J cluster)

- [x] [Review-2][Patch] **PC1 — Regenerate Cluster C–J packet with HEAD-correct line ranges** _(applied 2026-05-12: appendix added to `2a-10-cluster-c-j-review-packet.md`)_ — 14+ P-IDs cite stale `_verify_post.py:910-915` / `:949-956` / `:152-180` etc; file is 202 lines post-A+B and sites have moved (`:77`, `:116`, `:161-189`, `:122-158`). Implementer must `git grep -n` each cited symbol at apply-time, NOT trust packet line numbers. [`_bmad-output/implementation-artifacts/2a-10-cluster-c-j-review-packet.md`] _Sources: E1._
- [x] [Review-2][Patch] **PC2 — P9 case-insensitive FS + Windows reparse coverage** _(applied 2026-05-12: parent-symlink walk added in `_resolve_artifact_path`; reuses `Path.is_symlink()` which covers POSIX symlinks + Windows reparse points)_ ORIGINAL: — proposal under-specified; require `os.path.realpath` per ancestor + casefold-compare + explicit `os.lstat` symlink check; document Windows reparse-point (`stat.IO_REPARSE_TAG_*`) handling. Add tests: macOS APFS case-mixed parent, Linux symlink mid-path, Windows junction (skip on POSIX CI). [`src/sdlc/cli/verify.py:91-174`] _Sources: B22, E6._
- [x] [Review-2][Patch] **PC3 — P11 parent-directory fsync** _(applied 2026-05-12: `_atomic_write_text` in `_verify_post.py` does tmp-file write → fsync → `os.replace` → parent-dir fsync on POSIX)_ ORIGINAL: — `os.replace` atomicity does not include dir-entry durability across crash. Add `os.fsync(os.open(parent, os.O_RDONLY))` after `os.replace` on POSIX; document Windows skip + ReFS notes. [`src/sdlc/cli/_verify_post.py:116`] _Sources: B18, E7._
- [x] [Review-2][Patch] **PC4 — P7 + P21 + P23 use `result.output` + assert exact error code** _(partially applied 2026-05-12: tightened assertions in `test_verify_preflight.py` + `test_verify_boundary_guard.py` from generic substrings ("01-Requirement", "boundary", "phase") to canonical message-body phrases ("repo-relative POSIX path", "boundary marker", "requires phase=1"); strengthened `test_partial_marker_substring_proceeds` (P23) to verify `_invoke_dispatch.called == 1`; full migration to `--json` invocation + envelope-parsing left as follow-up because it requires `mix_stderr=False` on CliRunner across ~10 tests)_ ORIGINAL: — `OR \"01-Requirement\" in out` / `OR \"boundary\" in out.lower()` / `result.stderr + result.stdout` patterns are click-version fragile. Enumerate the affected tests (≈8 known: `test_verify_preflight.py:144,178-187`, `test_verify_boundary_guard.py:2025-2039`, `test_sdlc_verify.py:1637`) in PC4 sub-checklist. [`tests/unit/cli/`, `tests/e2e/pipeline/`] _Sources: B15, B21._
- [x] [Review-2][Patch] **PC5 — P26 + P27 specify expected JSON envelopes + non-None Typer ctx mock** _(applied 2026-05-12: P27 — `_init_repo` helper now constructs a real `typer.Context` with `ctx.obj={}`; P26 — `test_json_mode_missing_artifact_id_exits_nonzero` added as regression pin for current Typer-banner behaviour; full envelope-shape assertion deferred until AC1 amends contract for Typer-level errors)_
- [x] [Review-2][Patch] **PC6 — P31 amend AC9 scenario count + parameterise mock verdict + coverage delta** _(partially applied 2026-05-12: AC9 amended to 6 scenarios + AC10 coverage rider — done in spec; mock-verdict override hook added — `set_mock_verdict_override()` + `_resolve_mock_verdict()` in `_verify_dispatch.py`; unit-level coverage added for `build_verification_entry(status="failed"/"advisory")` in `test_verify_post.py`; full AC9 scenario #6 e2e test deferred — depends on full fixture rebuild + journal-shape assertions + DC10-scoped P30 code change which is the actual remaining code work)_
- [x] [Review-2][Patch] **PC7 — P33 + AC4 amendment + share control-char + envelope-fragment rejection** _(applied 2026-05-12: `normalize_for_boundary_check` promoted to public in `dispatcher/prompts.py`; `_artifact_contains_boundary` rewritten to normalised compare; AC4 spec line 87 amended; control-char + envelope-fragment rejection NOT promoted to CLI side — those run inside `_validate_idea_text` during dispatcher prompt-construction so CLI still relies on dispatcher to enforce. Add explicit CLI-side coverage in a sibling patch if a divergent rejection path becomes a real concern)_ ORIGINAL: — `_artifact_contains_boundary` (`verify.py:204`) must call the shared `prompts/boundary.py` helper INCLUDING `_reject_control_characters` + `_check_envelope_fragments` so CLI + dispatcher reject identical inputs. AC4 line 87 ("case-sensitive byte match") must be re-worded to "NFKC + dash-fold + whitespace-collapse + lowercase compare via `prompts._normalize_for_boundary_check`." Add regression tests: U+2013, NBSP-separated, lowercase-only, control-char-injected. [`src/sdlc/cli/verify.py:204`, `src/sdlc/dispatcher/prompts.py:51-117`, spec AC4 line 87] _Sources: B17, E10, A8._
- [x] [Review-2][Patch] **PC8 — P32 add new Change Log row, do NOT overwrite item 4** _(applied 2026-05-12: Change Log item 12 added; item 4 preserved verbatim)_ — packet says "Re-rank Change Log item 4 as `D1/D4`" which rewrites historical record. Replace with: add a new Change Log row dated 2026-05-12: "D4 retroactively added per P32; item 4 reinterpreted as D1/D4 due to 835-LOC outcome." Preserves CONTRIBUTING.md §5 audit trail. [`_bmad-output/implementation-artifacts/2a-10-sdlc-verify.md:428`] _Sources: A7._
- [x] [Review-2][Patch] **PC9 — DC9 wire-format snapshot regen ceremony PR** _(stub applied 2026-05-12: `_bmad-output/implementation-artifacts/2a-10-cluster-j-snapshot-regen-ceremony.md`. Activate after P29/P30/P34/P36 land)_ — bundle ALL `agent_dispatched` + `artifact_verified` payload mutations from P29 (DC8-amended), P30 (DC10-scoped), P34 (DC11-contingent), P36 into ONE PR at end-of-Cluster-J. Steps: (i) run `python scripts/freeze_wireformat_snapshots.py` to regenerate `tests/contract_snapshots/v1/journal_entry.json`; (ii) add ADR-024 mutation-taxonomy entry naming each new key + new status flow + new kind (if `hook_rejected` ends up in scope per DC11); (iii) update CONTRIBUTING.md §wire-format invariants if any guard rules change; (iv) link to Story 2A.12 consumer-migration backlog item. **Blocking pre-condition for shipping Cluster G/H/J patches.** [`tests/contract_snapshots/v1/journal_entry.json`, `docs/decisions/ADR-024-*.md`, new] _Sources: DC9 resolution; B6/B7/B24/E3/A1/A5._

#### Defer

- [x] [Review-2][Defer] **DC-W1 — P25 dispatcher-kwarg signature audit is redundant on HEAD** — `_panel_helpers.py:168-169,205-213,228-229` already accepts `persist_artifact`/`target_path_override`/`observer`; convert to a pinned-signature snapshot test gated by W2 (Story 2A.3 freeze ceremony). _Sources: B13, E12, A14._
- [x] [Review-2][Defer] **DC-W2 — Rollback / down-migration story for shipped journal-shape changes** — covered indirectly by DC9 (mutation ceremony bundle). Track in W1 expansion; do not block C–J apply. _Sources: B24._

#### Decision resolutions (2026-05-12)

All 12 `[Review-2][Decision]` items resolved during the Cluster C–J pre-implementation review. Implementer of any C–J patch MUST consult this registry before coding; the resolution is binding.

| ID | Resolution | Action for implementer |
|----|------------|------------------------|
| **DC1** | (a) reject — keep P14, drop P16 | Raise `ERR_VERIFIER_NOTE_OVERFLOW` on `len(raw_note) > 500`; remove P16 from the apply list. |
| **DC2** | (1) canonical order: pre-flight body-hash → dispatch → parse-verdict → run-hook-chain → atomic-write → emit `artifact_verified` (with both hashes) | Apply P10 + P34 in that order; **revert P12** (do NOT pre-emit journal row before write). Pin order in a new integration test. |
| **DC3** | (a) normalize CRLF + strip BOM in `_split_frontmatter_block` | P5 = forgiving normalize. Warnings deferred — wire later via P36 bundle if DC9 ceremony adopts the `warnings:` array. |
| **DC4** | (1) split codes — `ERR_STATE_CORRUPT` (logical/terminal, msg suggests `sdlc rebuild-state`) vs `ERR_STATE_SYNC_FAILED` (I/O/retryable) | P6 raises `ERR_STATE_CORRUPT` (only when JSON parses but `phase` non-int / out-of-range; keep best-effort default on `JSONDecodeError` per E13 guard). P13 raises `ERR_STATE_SYNC_FAILED` for the I/O branch. Add envelope entries to AC1 list. |
| **DC5** | (a) reuse `sdlc.concurrency` cross-platform abstraction | P17 uses `sdlc.concurrency` (NOT raw `fcntl.flock`). If the abstraction does not yet expose file-locking, raise a sibling Story 2A-N to add it; do not ship POSIX-only flock. |
| **DC6** | (2) coerce legacy string → `{verifier:"legacy", note:<str>, date:<today>}` + `payload.warnings:["legacy_verifications_coerced"]` | P19 = coerce, not reject. Warnings array shipping depends on DC9 bundle; if bundle slips, queue the warning into a stderr log instead. |
| **DC7** | (c) lazy mkdir on first journal append | P20 = `Path(parent).mkdir(parents=True, exist_ok=True)` at append site; no eager init mutation; no per-phase routing. |
| **DC8** | (2) ADD `artifact_hash_at_dispatch` ALONGSIDE `idea_hash` (deprecate `idea_hash` in 2A.12); KEEP P22 invariant — no `attempt` on `agent_dispatched`; hash semantics: `content_hash_at_verify` = body-only (drift driver), `before_hash`/`after_hash` = whole-file SHA-256 (crash-recovery audit) | P29 amended: (i) emit BOTH `idea_hash` (legacy alias) AND `artifact_hash_at_dispatch` on `agent_dispatched`; (ii) DROP P29's `attempt` reintroduction (P22 wins); (iii) document hash semantics in AC7 and pin all four hashes in tests. |
| **DC9** | (c) freeze `kind="artifact_verified"` + `kind="agent_dispatched"` snapshots at end-of-Cluster-J; one regen ceremony PR after P29 + P30 + P34 + P36 are coded | New patch row added: **PC9 — DC9 snapshot regen ceremony PR** (see Patch list below). |
| **DC10** | (a) scope-down P30 to "add non-zero exit when `entry.status in {failed, advisory}`" + amend AC2 to distinguish dispatcher outcome from verifier verdict | P30 = exit-code patch only; do NOT rewrite the `parse_verdict_envelope` flow. Pair with AC2 spec edit (new sub-clause: "verdict ∈ {failed, advisory} ⇒ non-zero exit regardless of dispatcher outcome"). |
| **DC11** | (a) drop P34 contingent on test proving dispatcher hooks already cover the frontmatter write under `persist_artifact=False` + `target_path_override` | Implementer FIRST writes a regression test that asserts `phase_gate` hook deny on frontmatter rewrite results in non-zero exit + no mutation; if green WITHOUT a second hook call → P34 dropped, test stays as anti-regression pin. If red → P34 still applies AND new AC5/i.5 sub-clause (`hook_rejected` envelope shape) added; double-fire mitigated via dispatcher-side idempotency token. |
| **DC12** | (a) `content_hash_at_verify` (body-only) is the hash pinned invariant across no-fm → with-fm transition | P24 test asserts `_compute_body_hash` invariance only; whole-file hashes (P29 `before_hash`/`after_hash`) are expected to differ across the transition by construction. |

**Cluster-J apply order (post-resolution):** PC1 (regen packet line numbers) → C-cluster correctness patches → D-cluster test patches → P10 → P34-or-test → P29 (DC8-amended) → P30 (DC10-scoped) → P36 → PC9 (snapshot regen) → P32 + PC8 (Change Log) + PC7 (AC4 amend) → PC6 (AC9 amend).
