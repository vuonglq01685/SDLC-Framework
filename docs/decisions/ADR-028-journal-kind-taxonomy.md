# ADR-028: Journal `kind` Taxonomy + `after_hash` Nullability Policy

**Status:** Accepted (2026-05-21, prep-sprint DOC1 — pre-Story-2B.1 ratify gate).

**Source:** Epic 2A retrospective §6.3 DOC1 + §1 ("~11 new journal kinds on open-string
posture pending ADR-028 ratify") + Team Agreement (H) "Journal `kind` taxonomy frozen via
ADR-028 before 2B.4 corpus tests".

## Context

The `JournalEntry.kind` field (`src/sdlc/contracts/journal_entry.py`) is declared as bare
`str` — not a `Literal[...]` union — so the wire-format contract is invariant under new kind
additions per ADR-024 (no snapshot regen). The trade-off is that the *set of kinds in active
use* must be ratified out-of-band; otherwise Epic 2B.4 (prompt-injection corpus tests) and
Epic 2B.3 (behavioural conformance Mock vs Claude) have no authoritative reference to assert
against.

A second sub-question is `after_hash` nullability. The current schema declares
`after_hash: ... ` as *non-nullable* and pattern-constrained to `sha256:[0-9a-f]{64}`. But
many kinds (e.g. `stop_trigger_raised`, `dispatch_attempt`) record *events*, not *content
writes* — there is no "after content" to hash. Inspection of `src/sdlc/hooks/runner.py:135`
shows the convention already in use: `after_hash="sha256:" + "0" * 64` — the all-zero hash
acts as a sentinel meaning "no content write occurred at this entry". This convention has
never been documented; ADR-028 ratifies it.

Inventory from `src/sdlc/` (grep-derived, 2026-05-21):

```
agent_dispatched     artifact_verified         artifact_written
bootstrap_completed  dispatch_attempt          dispatch_task
hooks_trusted        phase_advance             replan_invalidated
run_command          signoff_draft_generated   signoff_invalidated
signoff_recorded     signoff_hash_drift_detected  signoff_validation_failed
stop_trigger_raised  story_broken_into_tasks   task_stage_advanced
task_stage_failed    write_intent
```

= **20 distinct kinds** in active use at the close of Epic 2A. The retrospective's
"~11 new" count refers to kinds added during Epic 2A on top of the Epic 1 foundation set.

## Decision

### 1. Ratified kind set (frozen at this snapshot)

The 20 kinds listed above are the canonical set as of 2026-05-21. Adding a new kind in
Epic 2B+ requires a one-line amendment to this ADR's §3 table at the time the emission
lands — paired with the PR that introduces the emission.

### 2. `after_hash` sentinel convention (zero-hash for non-writing kinds)

The all-zero sha256 sentinel `sha256:` + (`"0"` × 64) is the canonical value for journal
entries that do not represent a content write:

```
sha256:0000000000000000000000000000000000000000000000000000000000000000
```

This preserves the strict pattern-match constraint on the `after_hash` field (no schema
edit needed) while making "no content was written" machine-detectable. Consumers (`sdlc trace`,
dashboard, telemetry) treat the sentinel as an explicit "event-only" marker.

The sentinel is *not* extended to `before_hash` because `before_hash` is already declared
nullable in the schema (`Optional[str]`) and the natural absent-meaning is `None`.

### 3. Per-kind taxonomy table

| Kind | First story | `before_hash` | `after_hash` | Payload notes |
|---|---|---|---|---|
| `artifact_written` | 1.x foundation | nullable / prior sha | sha256 of new content | `path`, `producer` |
| `phase_advance` | 1.x foundation | sha256 of prior state.json | sha256 of state.json after | `from_phase`, `to_phase` |
| `run_command` | 1.x foundation | n/a (sentinel) | sentinel | `cmd`, `argv`, `exit_code` |
| `agent_dispatched` | 2A.3 | nullable | sha256 of agent output_text | `agent_name`, `tool_calls`, `tokens_in/out` |
| `dispatch_attempt` | 2A.3 | n/a (sentinel) | sentinel | `agent_name`, `attempt_n`, `outcome` |
| `dispatch_task` | 2A.3 | nullable | sha256 of dispatched task json | `task_id`, `stage` |
| `destructive_op_reconfirmed` | 2B.6 | n/a (sentinel) | sentinel | `category`, `tool_call_excerpt`, `outcome="accepted"`, `nonce_sha256` |
| `destructive_op_rejected` | 2B.6 | n/a (sentinel) | sentinel | `category`, `tool_call_excerpt`, `outcome="rejected"`, `nonce_sha256` |
| `destructive_op_from_readonly_specialist` | 2B.6 (review) | n/a (sentinel) | sentinel | `category`, `tool_call_excerpt`, `outcome="blocked"`, `nonce_sha256` |
| `stop_trigger_raised` | 2A.3 | n/a (sentinel) | sentinel | `trigger_kind`, `reason`, `epic_4_placeholder` |
| `stop_triggered` | 4.2 | n/a (sentinel) | sentinel | `trigger`, `target`, `reason`, `correlation_id` |
| `write_intent` | 2A.4 | sha256 of current file | sha256 of intended content | `target_kind`, `target_path` |
| `high_risk_confirmed` | 4.7 | n/a (sentinel) | sentinel | `tool`, `tool_call_id`, `category`, `tool_call_excerpt`, `outcome="accepted"`, `nonce_sha256` |
| `hooks_trusted` | 2A.6 | n/a (sentinel) | sentinel | `manifest_sha`, `installer` |
| `signoff_draft_generated` | 2A.7 | nullable | sha256 of draft md | `phase`, `draft_path` |
| `signoff_recorded` | 2A.7 | nullable (prior canonical hash if re-sign) | sha256 of canonical record | `phase`, `approved`, `actor` |
| `signoff_invalidated` | 2A.7 + 2A.19 | sha256 of canonical at invalidation | sentinel | `phase`, `reason`, `scope` |
| `signoff_hash_drift_detected` | 2A.7 | sha256 of recorded canonical | sha256 of re-computed | `phase`, `drift_path` |
| `signoff_validation_failed` | 2A.7 | nullable | sentinel | `phase`, `cause` |
| `artifact_verified` | 2A.10 | n/a (sentinel) | sha256 of verified artifact | `path`, `expected_hash` |
| `bootstrap_completed` | 2A.15 | n/a (sentinel) | sha256 of bootstrap output digest | `placeholder_path`, `files_written` |
| `story_broken_into_tasks` | 2A.16 | n/a (sentinel) | sha256 of tasks dir digest | `story_id`, `task_count` |
| `task_stage_advanced` | 2A.17 | sha256 of task json before | sha256 of task json after | `task_id`, `from_stage`, `to_stage`, `run_id` |
| `task_stage_failed` | 2A.17 | nullable | sentinel | `task_id`, `stage`, `cause`, `run_id` |
| `replan_invalidated` | 2A.19 | n/a (sentinel) | sentinel | `scope`, `downstream_count`, `phases_invalidated` |
| `adopt_re_run` | 3.6 | n/a (sentinel) | sentinel | `new_adoptions`, `skipped_existing` |
| `auto_brainstorm_dispatched` | 4.10 | n/a (sentinel) | sentinel | `clarification_id`, `task_id`, `correlation_id`, `panel_invoked`, `framework_picks` |
| `auto_loop_iteration` | 4.1 | n/a (sentinel) | sentinel | `iteration_seq`, `action`, `correlation_id`, optional `task_id`, `reason` |
| `auto_mad_resolve` | 4.11 | n/a (sentinel) | sentinel | `target`, `decision`, `correlation_id` |
| `signoff_unsigned` | 4.12 | n/a (sentinel) | sentinel | `phase`, `mad_only`, `removed_count`, optional `clarification_id` |
| `adopt_pass_completed` | 3.1 | n/a (sentinel) | sentinel | `pass` (1\|2\|3) |
| `adopt_pass_failed` | 3.1 | n/a (sentinel) | sentinel | `pass` (1\|2\|3), `reason` |
| `adopt_pass_started` | 3.1 | n/a (sentinel) | sentinel | `pass` (1\|2\|3) |
| `adopt_rollback_started` | 3.5 | n/a (sentinel) | sentinel | `targets`, `orphaned_phases`, `reason` |
| `imported_from_existing` | 3.4 | n/a (sentinel) | sentinel | `source`, `target`, `marker` |
| `symlink_accepted` | 3.3 | n/a (sentinel) | sentinel | `source`, `target`, `kind` |
| `symlink_replaced` | 3.6 | n/a (sentinel) | sentinel | `target`, `old_source` |
| `symlink_rolled_back` | 3.5 | n/a (sentinel) | sentinel | single: `{target, source}`; bulk: `{count, targets}` |

Per-kind exactness lives in the source code (each emission site documents intent inline).
This table is the authoritative reference for cross-kind audits — if the table disagrees with
an emission, the emission is the bug and the PR amends both.

### 4. Forward rule

When Epic 2B+ adds a new emission:

1. The PR adds a row to §3 above (alphabetised by kind name within source-story column).
2. The PR adds a one-line entry to this ADR's "Revision Log" (see §below) citing the new
   kind, story number, and date.
3. Re-running `bmad-code-review` SHOULD flag any `kind="..."` literal in `src/sdlc/` whose
   string does NOT appear in §3 as a finding (this becomes a future enhancement to
   `scripts/check_journal_kinds.py` — not in scope today, tracked as deferred work).

## Alternatives Considered

- **Convert `kind` to `Literal[<union of strings>]` in the contract.** Rejected: would
  trigger an ADR-024 snapshot regeneration for every kind addition, taxing every Epic 2B
  story that emits a new event. The open-string posture + ratified-table is the lighter
  contract burden.
- **Make `after_hash` Optional in the schema.** Rejected: would trigger ADR-024 snapshot
  regeneration, plus introduces an "absent" code path that consumers must handle. The
  sentinel convention preserves the type signature while expressing the same intent.
- **Per-kind schema unions (e.g. JournalEntry[ArtifactWritten] | JournalEntry[StopTrigger]).**
  Rejected: requires Pydantic discriminated-union machinery, three orders of magnitude more
  complex than the open-string + table convention. Future v2 contract may revisit.

## Consequences

- **+** Epic 2B.3 (Mock vs Claude conformance) and Epic 2B.4 (prompt-injection corpus tests)
  have an authoritative reference to assert kind coverage against.
- **+** New kind additions in Epic 2B+ have a clear ceremony (table-row + log-entry) — no
  guess-work, no PR churn.
- **+** The all-zero sentinel convention is now documented; consumer code that ignored or
  miscoded the sentinel can be audited against this ADR.
- **−** The kind set is now an out-of-band contract surface that must stay in sync with code.
  Mitigation: the deferred `scripts/check_journal_kinds.py` audit (future) closes this.
- **−** The `after_hash` sentinel breaks the literal-truth of the field name for ~10 of the
  20 kinds. Reader documentation (CONTRIBUTING + sdlc trace help text) should explain.

## Revision Log

| Date | Author | Change |
|---|---|---|
| 2026-05-21 | Vuonglq01685 + Claude (prep-sprint DOC1) | Initial ratification — 20 kinds catalogued from Epic 1+2A code base; zero-hash sentinel convention codified; forward rule for Epic 2B+ kind additions established |
| 2026-05-28 | Vuonglq01685 + Claude (Story 2B.6) | Added `destructive_op_reconfirmed` and `destructive_op_rejected` — dispatcher-side nonce-echo gate (AC3); closes CR2B5-W1 and CR2B5-W2 |
| 2026-05-28 | Vuonglq01685 + Claude (Story 2B.6 bmad-code-review) | D4: amend `destructive_op_reconfirmed` + `destructive_op_rejected` payload `nonce` → `nonce_sha256` (hex digest) — journal is append-only audit artifact, raw nonce was a residual VCS-leak surface. D3: added `destructive_op_from_readonly_specialist` — emitted when a read-only specialist (empty/_bmad-output-only write_globs) proposes a destructive tool_call; raised as `DispatchError` WITHOUT user prompt (integrity violation, not user-confirmable). |
| 2026-06-02 | Vuonglq01685 + Claude (Story 3.1) | Added `adopt_pass_started`, `adopt_pass_completed`, `adopt_pass_failed` — the three-pass `sdlc init --adopt` orchestrator journals each pass start/complete (event-only zero-sentinel `after_hash`). `adopt_pass_failed` (D4 in 3.1) carries `{pass, reason}` to satisfy AC6 failure-journaling — the frozen `AdoptReport` schema has no error field, so the failure reason lives in the journal. |
| 2026-06-04 | Vuonglq01685 + Claude (Story 3.4) | Added `imported_from_existing` — Pass 3 emits one event-only entry per accepted symlink mapping, payload `{source, target, marker: "imported-from-existing"}`. External metadata sidecars under `.claude/state/imported-metadata/` (internal-state, not 8th wire-format). |
| 2026-06-04 | Vuonglq01685 + Claude (Story 3.5) | Added `symlink_rolled_back` — `sdlc adopt-rollback` removes adopt symlinks from `adopted-symlinks.json`; single-target payload `{target, source}`, bulk `--all` payload `{count, targets}` (event-only zero-sentinel `after_hash`). |
| 2026-06-04 | Vuonglq01685 + Claude (Story 3.5 code-review P5) | Added `adopt_rollback_started` — leading intent anchor journaled BEFORE `--force` signoff invalidation (mirrors `replan_invalidated`'s journal-first fail-loud posture); payload `{targets, orphaned_phases, reason}` (event-only zero-sentinel `after_hash`). Records rollback intent so the audit chain survives a mid-operation failure. |
| 2026-06-04 | Vuonglq01685 + Claude (Story 3.6) | Added `adopt_re_run` (re-run summary: `new_adoptions`, `skipped_existing`) and `symlink_replaced` (prior symlink removed before accept; payload `target`, `old_source`). |
| 2026-06-15 | Vuonglq01685 + Claude (Story 4.2) | Added `stop_triggered` — auto-loop halt when a Layer-2 STOP trigger fires; payload `trigger`, `target`, optional `reason`, `correlation_id` (event-only zero-sentinel `after_hash`). Distinct from `stop_trigger_raised` (4.6). |
| 2026-06-21 | Vuonglq01685 + Claude (Story 4.7) | Added `high_risk_confirmed` — auto-loop resume after explicit `--confirm-tool-call <id>`; payload `tool`, `tool_call_id`, `category`, `tool_call_excerpt`, `outcome="accepted"`, `nonce_sha256` (event-only zero-sentinel `after_hash`). Halt path still uses `stop_triggered{high_risk_path}`. |
| 2026-06-22 | Vuonglq01685 + Claude (Story 4.10) | Added `auto_brainstorm_dispatched` — auto-loop ambiguity→panel decision audit; payload `clarification_id`, `task_id`, `correlation_id`, `panel_invoked`, `framework_picks` (event-only zero-sentinel `after_hash`). |
| 2026-06-22 | Vuonglq01685 + Claude (Story 4.12) | Added `signoff_unsigned` — mad-only unsign recovery; payload `phase`, `mad_only`, `removed_count`, optional `clarification_id` (event-only zero-sentinel `after_hash`). |
| 2026-06-22 | Vuonglq01685 + Claude (Story 4.11) | Added `auto_mad_resolve` — mad-mode auto-resolution audit for signoff/clarification STOPs; payload `target`, `decision`, `correlation_id` (event-only zero-sentinel `after_hash`). |
| 2026-06-10 | Vuonglq01685 + Claude (Story 4.1) | Added `auto_loop_iteration` — auto-loop iteration audit entries via `append_with_seq_alloc`; payload carries `iteration_seq`, `action` (`dispatch`/`stopped`/`continued`), and `correlation_id` (event-only zero-sentinel `after_hash`). |
| 2026-06-04 | Vuonglq01685 + Claude (Story 3.3) | Added `symlink_accepted` — Pass 2 of `sdlc init --adopt` emits one event-only entry per accepted symlink (zero-sentinel `after_hash`), payload `{source, target, kind}`. The accepted-symlink manifest lives in the new `adopted-symlinks.json` wire-format contract (ADR-024 7th); the journal is the append-only audit trail Story 3.5 rollback / 3.6 idempotency replay against. |

## Revisit-by

After Story 2B.4 (prompt-injection corpus) lands. Confirm corpus assertions reference §3
table; if any kind in §3 has zero corpus coverage, decide whether to add coverage or remove
the kind. Also revisit at Epic 2B retrospective.
