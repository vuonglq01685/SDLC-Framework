# Story 4.12: `[Recovery] sdlc unsign --mad-only`

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**Story Key:** `4-12-recovery-sdlc-unsign-mad-only` · **Epic:** 4 (Auto-Mode & Autonomous Execution) · **DAG layer:** 5 (terminal) · **Branch:** `epic-4/4-12-unsign-mad-only` · **Critical-path spine:** `4.1 → 4.2 → 4.10 → 4.11 → 4.12` (terminal node) · **Depends on:** 4.11 (mad-signoff format `approved_by: ai-mad-mode` + `resolution.md` artifact it reverses) + 2A.7 (signoff state machine) · **Reverses:** Story 4.11.

## Story

As a tech lead reviewing a mad-mode run before promoting work to production,
I want `sdlc unsign --mad-only` to remove every signoff with `approved_by: ai-mad-mode` while preserving human-signed approvals,
so that mad-mode results can be selectively reverted without nuking legitimate human approvals (FR23).

## Acceptance Criteria

Verbatim from [Source: epics.md#2318-2346]. The dev agent owns making the system correct end-to-end, not just literal AC text — read the **design tension** in Dev Notes before coding (the AC words "removed" + "awaiting-signoff" are load-bearing and pin the mechanism).

1. **AC1 — Happy path (mixed signoffs → mad removed + journal entry).**
   **Given** a project with mixed signoffs: phase 1 signed by Lam (`approved_by: lam@example.com`), phase 2 signed by mad-mode (`approved_by: ai-mad-mode`)
   **When** I run `sdlc unsign --mad-only`
   **Then** phase 2's signoff record is **removed** from `.claude/state/signoffs/`
   **And** phase 1's signoff record is **preserved** (byte-intact)
   **And** the computed state reflects phase 2 transitioning back to `awaiting-signoff` (Story 2A.7 state machine)
   **And** a journal entry is appended `kind=signoff_unsigned, phase=2, mad_only=true, removed_count=1`

2. **AC2 — Empty case (no mad signoffs → exit 0 + exact message).**
   **Given** no mad-mode signoffs exist
   **When** I run `sdlc unsign --mad-only`
   **Then** the command exits **0** with the message `no mad-mode signoffs found; nothing to unsign`
   **And** **no** state mutations occur (no journal entry, no file change)

3. **AC3 — `--include-clarifications` extended flag.**
   **Given** mad-mode resolutions on clarifications (not signoffs)
   **When** I run `sdlc unsign --mad-only --include-clarifications`
   **Then** mad-resolved clarifications are also reverted (the `open_clarification.md` is **recreated**, the `resolution.md` is **removed**)
   **And** the journal records each reverted resolution

4. **AC4 — Mixed-signoff invariant (human signoffs survive) — integration.**
   **Given** the integration test
   **When** `tests/integration/test_unsign_mad_only.py` exercises mixed-signoff scenarios
   **Then** human signoffs survive every mad-only unsign
   **And** mad signoffs are removed cleanly with **no orphan state**

5. **AC5 (house standard) — quality gate + CLI conventions.** `--mad-only` (required in v1), `--include-clarifications`, `--json`, and `--help` all work; `--json` emits a sorted-key envelope reporting `removed_count` (and the empty case as `removed_count: 0`, exit 0). Full quality gate green on POSIX CI; freeze stays **7/7** (no new wire-format); module ≤400 LOC; `mypy --strict` clean.

## Tasks / Subtasks

TDD-first (CONTRIBUTING §2): the **first commit** is the failing test file(s); subsequent commits turn them green. `sdlc unsign` is a net-new CLI surface → tests-first is mandatory (NOT novel-substrate; do **not** waive R1).

- [x] **Task 1 — Tests first (RED).** (AC: 1,2,3,4,5)
  - [x] `tests/integration/test_unsign_mad_only.py` (AC-named): 5-cell matrix + audit lens — see Test idioms. Reuse `tests/_auto_mad_helpers.py` (do NOT re-duplicate seeds — CR4.11-W2).
  - [x] `tests/unit/cli/test_unsign.py`: the mad-signoff selector (filter `approved_by == "ai-mad-mode"` over `list_records`), the `--json` envelope shape, the exact empty-case message, exit codes, `--mad-only`-required guard.
  - [x] POSIX-skip cells that hit the signoff/journal write path: `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only signoff path in v1")`.
- [x] **Task 2 — `cli/unsign.py` selector + remover (GREEN).** (AC: 1,4)
  - [x] Enumerate signoff records via `list_records(repo_root)`; filter `rec.approved_by == "ai-mad-mode"`; skip everything else (preserves humans by construction).
  - [x] Per mad phase: journal **first** (`signoff_unsigned`), then remove **both** `.claude/state/signoffs/phase-<N>.yaml` **and** the `SIGNOFF.md` draft so `compute_state` reads `AWAITING_SIGNOFF` (see design tension — `invalidate_record` does **not** reach awaiting-signoff). Fail-loud on partial failure (replan's ratified posture).
- [x] **Task 3 — Journal `signoff_unsigned` (NET-NEW kind).** (AC: 1)
  - [x] Append `kind="signoff_unsigned"` with payload `{phase, mad_only: true, removed_count, correlation_id?}`; event-only → `before_hash=None` (or sha256 of the record-before), `after_hash="sha256:"+"0"*64` sentinel.
  - [x] Add the `signoff_unsigned` row to `docs/decisions/ADR-028-journal-kind-taxonomy.md` §3 + a Revision-Log line (ADR-028 §4 forward rule). Optionally add to `state/projection.py` `_KNOWN_KINDS` for parity (documentary only — see C3).
- [x] **Task 4 — `--include-clarifications` revert.** (AC: 3)
  - [x] Find `.claude/state/clarifications/<id>/resolution.md` with `resolved_by: ai-mad-mode`; recreate `open_clarification.md` from the original body preserved inside `resolution.md` (4.11 D3); remove `resolution.md`; journal each revert.
- [x] **Task 5 — Empty case + CLI conventions.** (AC: 2,5)
  - [x] No mad signoffs (and, if `--include-clarifications`, no mad resolutions) → exit **0**, print `no mad-mode signoffs found; nothing to unsign`, append **no** journal entry; `--json` → `{removed_count: 0, ...}`.
  - [x] `--mad-only` required in v1: bare `sdlc unsign` → `emit_error` with guidance (full unsign is out of scope). `--json`/`--help` via the global eager option.
- [x] **Task 6 — Register the command.** (AC: 5)
  - [x] `@app.command(name="unsign")` — prefer a `register_unsign_command(app)` module called from `main.py` (main.py is near the 400-LOC cap) mirroring `_auto_register.py`; or inline like `replan_command`. No dispatch → **no** mock-runtime guard.

## Dev Notes

### Substrate map (verified 2026-06-22 — exact symbols; wrong names break the build)

| Need | Exact symbol / path | Source |
|---|---|---|
| Mad discriminator | `approved_by == "ai-mad-mode"` (producer const `_APPROVED_BY = "ai-mad-mode"`) | `src/sdlc/engine/auto_mad.py:32`; `SignoffRecord.approved_by` `signoff/records.py:150` |
| Enumerate all signoffs | `list_records(repo_root) -> tuple[SignoffRecord, ...]` (globs `phase-*.yaml`, skips phase 3, sorted by phase) — **NO "find mad signoffs" helper exists; filter yourself** | `signoff/records.py:395` |
| Read one | `read_record(phase, *, repo_root) -> SignoffRecord \| None` | `signoff/records.py:252` |
| Record path | `.claude/state/signoffs/phase-<N>.yaml`; `_SIGNOFF_DIR=".claude/state/signoffs"`, `_VALID_RECORD_PHASES={1,2}` | `signoff/records.py:54,57,201` |
| Phase state derivation | `compute_state(phase, *, repo_root, strict=False) -> SignoffState` | `signoff/states.py:39-100` |
| State enum | `AWAITING_SIGNOFF`, `DRAFTED_NOT_APPROVED`, `APPROVED`, `INVALIDATED_BY_REPLAN` | `signoff/states.py:30-36` |
| Mad SIGNOFF producer (reversed) | `mad_sign_phase(...)` seeds `SIGNOFF.md` draft → `validate_signoff` → `write_record` (leaves **both** draft + `phase-N.yaml`) | `engine/auto_mad.py:131-175` |
| Mad CLARIFICATION producer (reversed) | `resolve_clarification(...)`: writes `resolution.md`, journals, unlinks `open_clarification.md` | `engine/auto_mad.py:208-257` |
| Clarification paths | `.claude/state/clarifications/<id>/{open_clarification.md, options.md, resolution.md}` | `engine/auto_mad.py:34-36`; `engine/stop_clarification.py:10-11` |
| Trigger re-fire | `OpenClarificationTrigger` fires on presence of any `open_clarification.md` | `engine/stop_clarification.py:14-41` |
| Journal append (sync) | `allocate_next_seq_for_append_sync(journal_path)` + `append_sync(entry, journal_path)` — the **replan** sibling uses this pair | `journal/writer.py:224-240,309-324`; `cli/replan_cmd.py:39,114,132,169,185` |
| Journal append (seq-safe) | `async append_with_seq_alloc(journal_path, factory)` — `auto_mad` uses this | `journal/writer.py:250-306`; `engine/auto_mad.py:17` |
| `JournalEntry.kind` | `kind: str` — **open string**, no Literal → freeze stays 7/7, no snapshot | `contracts/journal_entry.py:23` |
| Known-kinds set | `_KNOWN_KINDS` is **documentary** ("NOT used to reject unknown kinds") | `state/projection.py:38-53` |
| Atomic write | `atomic_write(path, content)` (absolute path, parent must exist) — **no atomic-delete primitive exists; use `Path.unlink()`** | `concurrency/io_primitives.py:139-154,32` |
| CLI app + register | `app = typer.Typer(...)` `cli/main.py:40`; register modules called `main.py:387-389`; `_auto_register.py:15-96`; inline `replan_command` `main.py:340-352` | — |
| `--json` / exit codes | `emit_json(command, payload, *, ctx)` `cli/output.py:216`; `emit_error(code, msg, *, ctx) -> NoReturn` (raises `typer.Exit`) `output.py:228-259`; model emitter `replan_cmd.py:195-205` | — |
| cli→signoff allowed | `cli.depends_on` includes `signoff, journal, state, concurrency, ids, contracts`; `cli.forbidden_from=frozenset()` — **table-legal, already used by replan** | `scripts/module_boundary_table.py:146-170`; `cli/replan_cmd.py:29` |
| LOC cap / boundary hook | `LOC_CAP = 400` per file; `scripts/check_module_boundaries.py:163` | — |

### THE HEADLINE — reaching `awaiting-signoff` requires DELETE, not `invalidate_record` (read before D1)

The DAG §5 row says *"reuse 3.5's replan invalidation seam"*. **That hint is structurally misleading and naming-drifted (same class of trap as 4.11's `auto_mad_resolve` ≠ `mad_resolution`).** Reuse replan's **orchestration shape** (journal-first, per-phase loop, fail-loud) — **NOT** its mechanism (`invalidate_record`).

Why: AC1 demands phase 2 transition back to **`awaiting-signoff`** and its record be **"removed"**. Per the verified state machine (`states.py:82-100`):
- a record with `invalidated_at` set → `INVALIDATED_BY_REPLAN` (this is what `invalidate_record` produces — it **rewrites in place, does not delete**: `records.py:331-392`);
- a record present + not invalidated → `APPROVED`;
- a `SIGNOFF.md` draft present + no record → `DRAFTED_NOT_APPROVED`;
- **neither record nor draft → `AWAITING_SIGNOFF`** ← the only branch that satisfies AC1.

The mad-sign forward path leaves **both** a patched `SIGNOFF.md` draft (`approved: true`) **and** a `phase-N.yaml` record (`auto_mad.py:152-175`). Therefore a faithful unsign must **delete both artifacts** for each mad phase. There is **no atomic-delete primitive** (`io_primitives` is write-only) — use `Path.unlink()` (consider parent-dir fsync). "state.json reflects awaiting-signoff" is loose prose: phase signoff state is **derived** by `compute_state` from file presence, **not** a mutable field — do **not** hand-edit `state.json`.

### `--include-clarifications` reverse semantics (AC3)

Reverses `resolve_clarification` (`auto_mad.py:208-257`). For each `.claude/state/clarifications/<id>/resolution.md` whose `resolved_by == "ai-mad-mode"`: **recreate** `open_clarification.md` from the original open-body that 4.11 deliberately preserved inside `resolution.md` (4.11 D3 — *"so 4.12 can recreate it"*), then **remove** `resolution.md`. Recreating `open_clarification.md` re-fires `OpenClarificationTrigger` (presence-based, `stop_clarification.py:21-36`). Journal each revert. Filenames are exact: `open_clarification.md`, `options.md`, `resolution.md`.

### Journal + audit invariant (the 4.11 D1 + replan CR19-W1 lesson)

Journal **before** the destructive disk mutation. 4.11's review patch (D1) moved the `auto_mad_resolve` append ahead of the unlink/`write_record` precisely so a crash never leaves a resolved-on-disk STOP with no audit entry. Symmetrically: append `signoff_unsigned` (with `removed_count` computed from the pre-delete set) **before** deleting, so the audit chain records the reversal even on partial failure. Fail-loud is the ratified posture (replan CR19-W1) — no silent rollback. The full audit chain is preserved across the round-trip: forward `auto_mad_resolve` + `signoff_recorded` (4.11) and reverse `signoff_unsigned` (4.12) all remain in the append-only journal even though the record **file** is deleted. Catch `SignoffError`/`SdlcError` (⊄ `OSError`) around signoff reads — `validator`/`records` raise `SignoffError`.

### Test idioms (reuse — do not invent)

- **Helpers:** `tests/_auto_mad_helpers.py` (importable as `from _auto_mad_helpers import ...`). `_write_approved_signoff(tmp, phase, rel)` writes a **human** record (`approved_by="human-test"`). Build a **mad** record with the same shape but `approved_by="ai-mad-mode"` via `write_record(SignoffRecord(..., approved_by="ai-mad-mode", ...), repo_root=tmp)`. `_seed_open_clarification(tmp, with_options=True)` seeds `clar-madtest01`. `_bootstrap_journal(tmp)` → `(journal, runs, state)`. (CR4.11-W2: reuse these; do not re-duplicate seeds.)
- **Mixed fixture for AC1/AC4:** human phase-1 + mad phase-2; assert post-run `read_record(2)` is gone / `compute_state(2)==AWAITING_SIGNOFF`, `read_record(1)` byte-intact.
- **Journal asserts are structured** (CR4.10-P2): `[e for e in iter_entries(journal) if e.kind == "signoff_unsigned"]`, assert `e.after_hash == "sha256:" + "0"*64`. Not JSON-substring.
- **5-cell matrix + audit lens:** (1) positive unsign mixed; (2) empty case exit-0 + exact message + no mutation; (3) preserve invariant (multiple human + multiple mad → only mad gone); (4) `--include-clarifications` revert + trigger re-fire; (5) idempotency (run twice → 2nd is the empty case) + audit-chain consistency.
- **POSIX-skip** signoff/journal-write cells (`skipif win32`); module-level `pytestmark = pytest.mark.integration` for the integration file. Coverage ≥ **87** operational floor; full pytest must run on a POSIX host (win32 dev host can't exercise the POSIX-only path — coverage/freeze are asserted-not-measured locally, CR4.9/4.11-W1).

### Project Structure Notes

- **New:** `src/sdlc/cli/unsign.py` (FR-map `architecture.md:1153`); optional `src/sdlc/cli/_unsign_register.py`; `tests/integration/test_unsign_mad_only.py`; `tests/unit/cli/test_unsign.py`.
- **Modified:** `src/sdlc/cli/main.py` (register, if not via a register module); `docs/decisions/ADR-028-journal-kind-taxonomy.md` (§3 row + Revision Log); optionally `src/sdlc/state/projection.py` (`_KNOWN_KINDS` parity).
- **No** module-boundary-table edit (cli already depends on signoff/journal/state/concurrency/contracts). **No** new wire-format contract (`SignoffRecord` is internal; `kind` is open-string) → freeze **7/7**, no snapshot ceremony. Keep `unsign.py` ≤400 LOC.
- **Security-sensitive:** this command **deletes approval + audit state**. Route review-B through `security-reviewer` in addition to the Edge Case Hunter (precedent: 4.11 review-B → security-reviewer for the autonomous gate).

### References

- [Source: epics.md#2318-2346] Story 4.12 user story + ACs (verbatim above). [Source: epics.md#2012,2352-2355] Epic-4 goal + dependency (4.12 ← 2A.7; reverses 4.11).
- [Source: prd.md#766] FR23. [Source: prd.md#391] forward kind `auto_mad_resolve` + reversibility. [Source: prd.md#526] CLI conventions (`--help` + `--json`). [Source: prd.md#544] mad-mode walkthrough fixture proves reversibility.
- [Source: architecture.md#1153] FR23 → `cli/unsign.py`. [Source: scripts/module_boundary_table.py:146-170] enforced cli grants (supersede the narrower `architecture.md §1071` prose).
- [Source: ADR-028 §3,§4] journal-kind taxonomy + forward rule (auto_mad_resolve row = template). [Source: ADR-024 §Decision] 7/7 wire-format lock; journal `kind` invariant.
- [Source: docs/sprints/epic-4-dag.md §2,§3,§5] Layer-5 node, deps, branch `epic-4/4-12-unsign-mad-only`, owner Winston (tentative — sprint planning locks roster).
- [Source: CONTRIBUTING.md §1,§2,§3,§4,§5] quality gate, TDD-first R1/R2, worktree/rebase, chunked review A→B→C + `[fresh-context-review]`, decision protocol.
- UX: `ux-design-specification.md` is dashboard-only — no CLI output spec. Only mandated user string is AC2's message; follow command-as-affordance (literal command strings, no `$`/`>` prefix) if echoing.

## Decisions Needed

Material decisions (CONTRIBUTING §5 protocol). Recommendations are strong defaults grounded in the verified substrate; ratify on the PR.

- **D1 (HEADLINE) — reversal mechanism.** (a) **Delete both `phase-N.yaml` + `SIGNOFF.md` draft** → phase reads `AWAITING_SIGNOFF` (the only path that satisfies AC1's "removed" + "awaiting-signoff"); audit preserved by the append-only journal. (b) `invalidate_record` → `INVALIDATED_BY_REPLAN`, keeps the file — **does NOT satisfy AC1**, but preserves the record on disk. **Recommend (a).** The DAG "reuse replan seam" hint = reuse the *orchestration shape*, not the mechanism.
- **D2 — journal API.** (a) sync pair `allocate_next_seq_for_append_sync` + `append_sync` (mirrors `replan_cmd`, the structural sibling; `unsign` is a sync CLI). (b) `append_with_seq_alloc` via `asyncio.run` (honors `EPIC-2B-DEBT-MIGRATE-PROCESS-LOCAL-SEQ-CALLSITES` forward rule for net-new write surfaces). **Recommend (a)** for sibling-consistency; flag the forward-rule debt for reviewers.
- **D3 — journal granularity.** (a) one `signoff_unsigned` entry **per removed phase** (`phase=N`), replan-consistent, with run-level `removed_count`. (b) single aggregate entry. **Recommend (a)** (AC1 shows a phase-scoped entry).
- **D4 — `--mad-only` requiredness.** (a) require explicit `--mad-only` in v1; bare `sdlc unsign` → `emit_error` with guidance (full unsign out of scope). (b) make `--mad-only` the implicit default. **Recommend (a)** — FR23 only defines the mad-only mode; explicit intent for a destructive command.

## Dev Agent Record

### Context Reference

- Story authored via 4 parallel research subagents (requirements/epics+prd+ux · architecture+ADR+DAG+CONTRIBUTING · source-seam verification · previous-story 4.11+deferred-work+git) + direct source verification of every load-bearing symbol on 2026-06-22.

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Implemented `sdlc unsign --mad-only` (FR23): filters `approved_by == "ai-mad-mode"`, journal-first `signoff_unsigned`, deletes both `phase-N.yaml` and `SIGNOFF.md` draft (D1 delete-both, not `invalidate_record`).
- `--include-clarifications` recreates `open_clarification.md` from preserved resolution body and removes `resolution.md`.
- Empty case: exit 0, exact AC2 message, no `signoff_unsigned` journal entries.
- 16 tests (10 unit + 6 integration), all green; mypy --strict clean on new modules; ruff clean.
- ADR-028 §3 + revision log updated; `_KNOWN_KINDS` parity in projection.py.

### File List

- src/sdlc/cli/unsign.py (new)
- src/sdlc/cli/_unsign_register.py (new)
- src/sdlc/cli/main.py (modified — register unsign)
- src/sdlc/state/projection.py (modified — signoff_unsigned in _KNOWN_KINDS)
- docs/decisions/ADR-028-journal-kind-taxonomy.md (modified)
- tests/unit/cli/test_unsign.py (new)
- tests/integration/test_unsign_mad_only.py (new)

### Debug Log References

- D1 ratified: delete both artifacts → `AWAITING_SIGNOFF` (not `invalidate_record`).
- D2 ratified: sync `allocate_next_seq_for_append_sync` + `append_sync` (replan sibling).
- D3 ratified: one `signoff_unsigned` per removed phase/clarification with run-level `removed_count`.
- D4 ratified: `--mad-only` required; bare `sdlc unsign` → ERR_USER_INPUT.

### Review Findings

> bmad-code-review (fresh-context, 4 adversarial layers @ Opus-4.8: Blind Hunter / Edge Case Hunter / Acceptance Auditor / **security-reviewer** per DAG §7 SECURITY-SENSITIVE) + reviewer source-verification. Acceptance Auditor verdicts: **AC1 MET, AC2 MET, AC3 MET, AC4 MET, AC5 MET; D1 MET, D2 MET, D3 PARTIAL (see CR4.12-D1), D4 MET.** D1 HEADLINE confirmed correct (deletes BOTH `phase-N.yaml` + `SIGNOFF.md` draft → `AWAITING_SIGNOFF`, NOT `invalidate_record`); journal-before-delete invariant HELD; human-approval preservation correct by construction (`select_mad_records` exact-match filter). KEY REFRAME: the two security HIGHs (symlink/path-containment) and the `extract_open_body` format brittleness are **cross-cutting + pre-existing** — the already-merged forward path `auto_mad.py:247,257` uses the identical `atomic_write(...resolve())` + bare `unlink` + raw-unfenced `open_body` interpolation; 4.12 faithfully mirrors it → deferred, not 4.12 regressions. Triage: **1 decision / 2 patch / 7 defer / 6 dismissed.** No NEW unambiguous CRITICAL/HIGH code bug introduced by 4.12.

**Decision-needed (1) — RESOLVED**

- [x] [Review][Decision→Patch] CR4.12-D1 — Per-entry `signoff_unsigned.removed_count` semantics [src/sdlc/cli/unsign.py:250-262,280-288] — Each per-phase/per-clarification entry carried the **per-category** count (`signoff_removed_count` / `clar_removed_count`), not 1 and not the run-level total. D3 prose said "run-level removed_count"; AC1 only exercised the single-item case (1==1==1); the field is audit-only (`projection.py` fold ignores it). **RESOLVED → option (c): `removed_count = 1` per entry** (cleanest per-event reading; makes partial-failure entries honest; run-level total stays in the `--json` envelope) **+ add a mixed signoff+clarification test.** Reclassified as patch CR4.12-D1 below.

**Patch (4) — ALL APPLIED (working tree)**

> **GATE VERIFICATION (measured on a POSIX/macOS host by the reviewer — closes the recurring "asserted-not-measured on win32" gap, cf. CR4.9/4.11-W1):** after patches, the FULL gate is green — `ruff check` clean, `ruff format --check` clean, `mypy --strict src/` (183 files) clean, **freeze 7/7**, module-boundary / no-direct-state-writes / no-journal-mutation clean, **full pytest 3776 passed / 4 skipped / 1 xfailed (CR4.6-W2)**, **coverage 89.82% ≥ 87**. The unsign suite is now **17 tests** (added the CR4.12-D1 mixed-run cell).

- [x] [Review][Patch] CR4.12-D1 (from decision) — Set per-entry `signoff_unsigned.removed_count` to `1` [src/sdlc/cli/unsign.py:250-262,280-288] — APPLIED: each `_append_signoff_unsigned` now passes `removed_count=1`; `total_removed` stays in the `--json` envelope. Added `test_mixed_signoff_and_clarification_removed_count_is_one_per_entry` (envelope total == 2, each entry removed_count == 1); `test_positive...` unchanged (still 1).

- [x] [Review][Patch] CR4.12-P1 — Strengthen near-tautological tests [tests/integration/test_unsign_mad_only.py, tests/unit/cli/test_unsign.py] — APPLIED: idempotency test now asserts run-1 `read_record(2) is None` + exactly one `signoff_unsigned` entry (removed_count==1) before run-2; both round-trip assertions now compare exact content (`== open_body.strip() + "\n"` / `== open_body`), pinning the `stripped + "\n"` newline contract.
- [x] [Review][Patch] CR4.12-P2 — Empty-case dual-output + manual JSON gate [src/sdlc/cli/unsign.py:185-186] — APPLIED: replaced `if not ctx.obj.get("json"): typer.echo(_EMPTY_MSG)` with the gated `echo(_EMPTY_MSG, ctx=ctx)` helper (NO-OP in `--json` mode). Behavior unchanged (sibling-consistent with `replan`'s always-`emit_json`); cosmetic consistency only.
- [x] [Review][Patch] CR4.12-P3 (reviewer-discovered) — Quality gate was RED, not "clean" as claimed [src/sdlc/cli/unsign.py, tests/integration/test_unsign_mad_only.py, tests/unit/cli/test_unsign.py] — APPLIED: the as-shipped files had `ruff` violations (`F401` unused `typer` + `_seed_open_clarification` imports in the integration test; `E501` on 4 lines) — the "ruff clean / mypy clean" Completion Note was asserted-not-measured on the win32 dev host (same class as CR4.9/4.11-W1). Fixed via `ruff check --fix` + `ruff format` + manual line-length; gate now measured green on POSIX (see GATE VERIFICATION above).

**Deferred (7 — checked, see deferred-work.md)**

- [x] [Review][Defer] CR4.12-W1 — Symlink/path-containment on writes & unlinks [src/sdlc/cli/unsign.py:122-139,181-198] — deferred, cross-cutting + pre-existing (forward path `auto_mad.py:247,257` identical; threat-model-bounded to local FS write access to `.claude/state/`).
- [x] [Review][Defer] CR4.12-W2 — Partial-failure over-claim + non-atomic seq pair [src/sdlc/cli/unsign.py:142-178,199-304] — deferred, by-design fail-loud/journal-first (sibling-consistent with `replan`) + ratified D2 debt `EPIC-2B-DEBT-MIGRATE-PROCESS-LOCAL-SEQ-CALLSITES`.
- [x] [Review][Defer] CR4.12-W3 — No parent-dir fsync after `unlink` [src/sdlc/cli/unsign.py:184,189,198] — deferred, durability hardening; Dev Notes flagged "consider"; no atomic-delete primitive exists; forward path unlink also lacks dir-fsync (cross-cutting).
- [x] [Review][Defer] CR4.12-W4 — `extract_open_body_from_resolution` format brittleness [src/sdlc/cli/unsign.py:103-114] — deferred, format-contract shared with 4.11 `_build_resolution_body` (raw, unfenced `open_body`); `## Decision`/marker matched anywhere → data loss only if a clarification body itself contains those headings. Cross-story robustness.
- [x] [Review][Defer] CR4.12-W5 — Selector silently swallows `OSError` [src/sdlc/cli/unsign.py:133-136] — deferred, low-likelihood; conservative selector skip; for a recovery command consider surfacing read failures rather than under-counting with success exit.
- [x] [Review][Defer] CR4.12-W6 — No confirmation/dry-run guard on a destructive command [src/sdlc/cli/unsign.py, _unsign_register.py] — deferred, D4 ratified `--mad-only` as the v1 intent gate; `--yes`/dry-run is future scope (prior-art 4.7 high-risk confirmation).
- [x] [Review][Defer] CR4.12-W7 — Misc low-risk hardening [src/sdlc/cli/unsign.py:117-119,162,166] — deferred, low: `_resolution_is_mad` matches `resolved_by:` anywhere (first-match safe today); `clarification_id` (dir name) flows unsanitized into journal `target_id` (JSON-escaped); absolute paths in error `details` (consistent with CLI; consider repo-relativizing).

**Dismissed (6)** — `emit_error` "might not raise → UnboundLocalError" (Blind HIGH; it IS `-> NoReturn`, output.py:234/259 — recurs CR4.9); "success envelope emitted after partial mutation" (Blind HIGH; `emit_error` raises → envelope unreachable on partial failure); "draft orphaned when phase ∉ `PHASE_DIR_MAP`" (Blind MED; unreachable — `list_records` yields only phases {1,2}, both mapped); "single `now` timestamp across batch" (Blind/Auditor LOW; sibling-consistent with `replan`); "happy-path JSON envelope in plain mode" (Blind/Auditor LOW; `replan` emits `emit_json` unconditionally = house style); "raw `OSError` from `allocate_next_seq` outside the try" (Blind LOW; sibling-consistent with `replan`, still caught → `ERR_JOURNAL_APPEND_FAILED`).

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-06-22 | bmad-code-review (4 layers + security-reviewer @ Opus-4.8, full gate measured green on POSIX). 1 decision resolved (CR4.12-D1 → per-entry `removed_count=1`), 4 patches applied (D1/P1/P2 + P3 ruff-gate-red fix), 7 defers, 6 dismissed. Unsign suite 16→17 tests; coverage 89.82%. STAYS `review` pending merged-before-done gate. | code-review |
| 2026-06-22 | Story 4.12 implemented — `sdlc unsign --mad-only`, journal kind `signoff_unsigned`, 16 tests green | dev-story |
| 2026-06-22 | Story created — ready-for-dev. Layer-5 terminal / critical-path spine terminus. 10 ground-truth corrections + 4 decisions (D1 headline: delete-both-artifacts, not `invalidate_record`). | Vuonglq01685 + Claude (create-story) |
