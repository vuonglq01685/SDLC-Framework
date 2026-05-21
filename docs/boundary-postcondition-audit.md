# Boundary-Line Postcondition Audit — Pre-Epic-2B Snapshot

**Status:** Verified (2026-05-21, prep-sprint C4 — pre-Story-2B.1 ratify gate).
**Source:** Epic 2A retro §6.1 + §7.1 C4 + tickets `EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK`
+ `EPIC-2A-DEBT-PHASE2-PROMPT-SECURITY-INVARIANT`.
**Scope:** Verification-only — no code changes. Restoration (D4) lands with Story 2B.1 once
the preconditions in §3 are met.

## 1. Current per-workflow status

Grep over `src/sdlc/workflows_yaml/*.yaml` for the
`boundary_line_present_in_prompts` postcondition entry:

| Workflow YAML | Phase | Postcondition present? | Postcondition list |
|---|---|---|---|
| `sdlc-start.yaml` | 1 | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-research.yaml` | 1 | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-epics.yaml` | 1 | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-stories.yaml` | 1 | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-signoff.yaml` | 1 (validator) | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-verify.yaml` | 1 (validator) | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-ux.yaml` | **2** | ❌ **MISSING** | `ux_dir_non_empty` only |
| `sdlc-architect.yaml` | 2 | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-bootstrap.yaml` | 3 | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-break.yaml` | 3 | ✅ yes | `boundary_line_present_in_prompts`, ... |
| `sdlc-task.yaml` | 3 | (not enumerated in this audit) | TBD per Story 2B.5 |

**Verdict:** 9 of 10 audited workflows enforce the postcondition. `sdlc-ux.yaml` is the
single gap, intentional, and tracked against two debt tickets.

## 2. Phase-2 gap — `sdlc-ux.yaml`

### 2.1 Why the postcondition is absent

The postcondition `boundary_line_present_in_prompts` is implemented at
`src/sdlc/dispatcher/postconditions.py:661 _check_boundary_line_in_runs` and reads
`agent_runs.jsonl` to assert every dispatched prompt carries the prompt-injection-boundary
line (NFR-SEC-3).

`MockAIRuntime` does NOT write `agent_runs.jsonl` (one of the five divergences enumerated in
ADR-029 §1). Phase-2 `sdlc-ux.yaml` dispatches the `ux-designer` specialist via the mock
runtime today; if `boundary_line_present_in_prompts` were enabled, every Phase-2 dispatch
would fail the postcondition because the file the validator reads simply does not exist.

The pragmatic resolution during Epic 2A was to drop the postcondition from `sdlc-ux.yaml`
only, leaving Phase-1 and Phase-3 protected (those paths plumb `agent_runs.jsonl` through
their own surfaces). The drop is documented in
`_bmad-output/implementation-artifacts/deferred-work.md` as
`EPIC-2A-DEBT-PHASE2-PROMPT-BOUNDARY-CHECK` and the security-side gap as
`EPIC-2A-DEBT-PHASE2-PROMPT-SECURITY-INVARIANT`.

### 2.2 Concrete current-state evidence

```yaml
# src/sdlc/workflows_yaml/sdlc-ux.yaml — head of file
schema_version: 1
name: phase2-ux-track
slash_command: /sdlc-ux
primary_agent: ux-designer
parallel_agents: []
synthesizer_agent: null
postconditions:
  - ux_dir_non_empty                           # ← only postcondition
write_globs:
  ux-designer:
    - "02-Architecture/01-UX/*.md"
stop_on_postcondition_failure: true
```

Compare `sdlc-start.yaml` (Phase 1):

```yaml
postconditions:
  - boundary_line_present_in_prompts
  - ...
```

## 3. Reactivation preconditions (Story 2B.1 owns D4)

Three preconditions must land before `boundary_line_present_in_prompts` can be re-added to
`sdlc-ux.yaml`:

| # | Precondition | Source | Status |
|---|---|---|---|
| P1 | `engine/io_primitives.py` atomic write primitive | prep-sprint C1 | **open** (BLOCKING) |
| P2 | `ClaudeAIRuntime` ships and writes `agent_runs.jsonl` | Story 2B.1 | **open** (Epic 2B work) |
| P3 | Mock divergence #1 fixed (`MockAIRuntime` also writes `agent_runs.jsonl` with `mock: true`) | ADR-029 §4 + Story 2B.1 | **design ratified** (C8/ADR-029); impl in 2B.1 |

When all three preconditions land, the D4 restoration ceremony is **single-line**:

```diff
 # src/sdlc/workflows_yaml/sdlc-ux.yaml
 postconditions:
+  - boundary_line_present_in_prompts
   - ux_dir_non_empty
```

…paired with the regression test added by Story 2B.5 ("automated boundary-line presence
test"), which asserts `_check_boundary_line_in_runs` rejects a Phase-2 `agent_runs.jsonl`
that omits the boundary line.

## 4. Epic 2B story dependencies

Per Epic 2A retro §7.4 Epic-2B Story → Epic 2A dependency map:

- **Story 2B.4 (Prompt-injection corpus + CI regression)** depends on this gap closing —
  the corpus needs a Phase-2 workflow that DOES enforce the boundary postcondition, so
  D4 reactivation IS a Story 2B.4 hard prerequisite.
- **Story 2B.5 (Automated boundary-line presence test)** owns the regression test that locks
  the restored postcondition in place across all Phase-1/2/3 workflows. Once 2B.5 ships, any
  future workflow author who omits `boundary_line_present_in_prompts` from a Phase-1/2/3
  YAML fails CI.

## 5. Verification steps (post-D4)

When D4 closes (under Story 2B.1 or shortly after), the following checks confirm
reactivation:

```bash
# All Phase-1/2/3 workflows now carry the postcondition
grep -lE 'boundary_line_present_in_prompts' src/sdlc/workflows_yaml/sdlc-*.yaml
# Expected: 10 of 10 (one of them is sdlc-task.yaml — confirm Phase-3 task path)

# The postcondition validator reads agent_runs.jsonl successfully under MockAIRuntime
SDLC_USE_MOCK_RUNTIME=1 uv run sdlc ux --allow-mock <test args>
test -f .claude/state/agent_runs.jsonl && echo "OK: mock writes agent_runs.jsonl"

# Phase-2 dispatch under mock now exits 0 with boundary postcondition active
SDLC_USE_MOCK_RUNTIME=1 uv run sdlc ux --allow-mock <test args>; echo "exit: $?"
# Expected: exit 0; previously would exit 1 with
#   "invariant violated: boundary_line_present_in_prompts" because no agent_runs.jsonl

# Debt-budget gate updates after D4 closure
sed -i '' '/EPIC-2A-D4-PHASE2-PROMPT-BOUNDARY-CHECK/{n;s/open/closed/;}' \
    _bmad-output/implementation-artifacts/debt-budget.yaml
uv run python scripts/check_debt_decay_budget.py --target-epic 2b --mode warn
# Gate B HIGH carry-forward count moves up; if ≥50%, gate flips PASS.
```

## 6. Cross-references

- `src/sdlc/dispatcher/postconditions.py:407` — postcondition dispatch table entry
- `src/sdlc/dispatcher/postconditions.py:661` — `_check_boundary_line_in_runs` implementation
- `src/sdlc/dispatcher/prompts.py:213` — NFR-SEC-3 docstring in Phase-1 prompt builder
- `src/sdlc/cli/_boundary.py` — Phase-2 CLI-layer NFR-SEC-3 pre-flight (defense-in-depth
  layer that exists today; the postcondition is the second-layer gate that is currently
  dropped for Phase 2)
- `src/sdlc/workflows_yaml/sdlc-ux.yaml` — the file D4 will edit
- ADR-029 §1 + §4 — MockAIRuntime divergence #1 and its fix
- `_bmad-output/implementation-artifacts/deferred-work.md:463-464` — both debt tickets
- `_bmad-output/implementation-artifacts/debt-budget.yaml::EPIC-2A-D4-PHASE2-PROMPT-BOUNDARY-CHECK`
  — HIGH-severity row that flips to closed at D4 close
- Epic 2A retro §6.2 D4 — restoration sentence
- Epic 2A retro §7.4 — Story 2B dependency map (2B.4 + 2B.5 rely on D4)
