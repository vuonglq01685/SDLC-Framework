# Story 3.5: [Recovery] Adopt Rollback via `adopted-symlinks.json`

**Status:** done

**Epic:** 3 — Brownfield Adopt Mode (`sdlc init --adopt`)
**Layer:** 5 (`docs/sprints/epic-3-dag.md` §3 — runs in parallel with 3.6; max-parallel 2)
**Worktree:** `epic-3/3-5-adopt-rollback` (owner: Elena, DAG §5 table)
**Critical Path:** 3.1 → 3.2 → 3.3 → 3.4 → 3.6 → 3.7 — **3.5 is OFF the critical path** (the `… → 3.5` branch has length 5; DAG §4). It shares the 3.3/3.4 foundation with its Layer-5 sibling 3.6 but is not on the spine; nothing downstream waits on 3.5 (3.7 depends on 3.4 + 3.6, not 3.5).
**Depends on (satisfied):** Story 3.3 (`done`, merged to `main` @ `bc07c23`) — froze the `adopted-symlinks.json` / `AdoptedSymlinks{schema_version:1, mappings:[SymlinkMapping{source,target,accepted_at,kind}]}` 7th wire-format contract (`contracts/adopted_symlinks.py`), the `symlink_accepted` journal event (ADR-028 §3), and the atomic-manifest / `_append_symlink_event` / `WarnCallback` fail-soft patterns this story mirrors. Story 3.4 (`done`, merged @ `bc07c23`) — produced the `imported_from_existing` journal events + `.claude/state/imported-metadata/<artifact-id>.yaml` sidecars that rollback reverts, plus the `cli/_adopted_targets.py` manifest-reader helper and the `imported_metadata.artifact_id_for_target` slug derivation 3.5 reuses to locate sidecars.
**Parallel sibling (same layer):** 3.6 (Idempotency + Conflict Resolution). **Both 3.5 and 3.6 edit `docs/decisions/ADR-028-journal-kind-taxonomy.md`** (§3 table + Revision Log) — shared-file contention; CONTRIBUTING §3 (rebase-between-merges, first merger owns shared edits) applies. 3.5 additionally edits `cli/main.py` (new `adopt rollback` command); 3.6 likely does not.
**§7.4 gate:** N/A — 3.5 is **not** Story N.1 (the Pre-Story 3.1 gate was cleared 2026-06-02, DAG §8 4/4; epic-3 stays `in-progress`).

---

## Story

As a **maintainer who accepted a symlink in error (or detection assigned the wrong canonical target)**,
I want **`sdlc adopt rollback [--all | --target <path>]` to remove the symlinks tracked in `adopted-symlinks.json`, prune (or empty) the manifest, journal a `symlink_rolled_back` event, refuse if a rollback would orphan a downstream signoff (overridable with `--force`, which then invalidates that signoff), and behave idempotently when the on-disk symlink no longer matches the manifest**,
so that **adopt-mode mistakes are reversible (FR2 adopt-mode recovery; prd.md:290/296/336 — "the accepted ones are tracked in `adopted-symlinks.json` for rollback") while the NFR-REL-6 source-untouched invariant continues to hold byte-for-byte (removing a symlink never touches the file it pointed at)**.

---

## Acceptance Criteria

> **Scope note — read first.** Story 3.5 ADDS a **new** `sdlc adopt rollback` command (there is no `adopt`
> command group today — only a hidden `--adopt` flag on `init`, see correction (A)). It does **NOT** implement
> Pass 1/2/3 (3.2/3.3/3.4, all `done`), does **NOT** implement re-run idempotency of the adopt *passes* (Story 3.6
> — 3.5 only makes the *rollback* idempotent against on-disk drift, AC group 4), and does **NOT** own the
> source-untouched property/mutation gate (Story 3.7 — 3.5 must merely *be* correct and assert byte-identity in its
> own unit tests). It consumes the frozen `adopted-symlinks.json` (read) and REWRITES it (prune/empty) per ACs 1-2.
>
> **Six material decisions — D1 (rollback-core module location + the `cli`/`adopt` split), D2 (command surface:
> Typer sub-group vs flat + `--all`/`--target` mutual-exclusion), D3 (bulk `--all` journal shape + single-target
> payload), D4 (orphan-signoff detection + `--force` invalidation seam — the headline cross-module decision), D5
> (idempotent reconciliation semantics), D6 (manifest-rewrite reuse: extract a shared writer vs duplicate) — are
> resolved at T0 in "Decisions Needed" BEFORE any code is written.** D1 + D4 gate the file set and the boundary, so
> settle them first.

> ### Binding ground-truth corrections (verified against `main` @ `bc07c23`, 2026-06-04) — READ BEFORE CODING
>
> **(A) There is NO `sdlc adopt` command group today — only a hidden `--adopt` flag on `init`.** `cli/main.py`
> registers `@app.command(name="init")` with `--adopt` / `--non-interactive` hidden flags
> (`main.py:75-105`) that call `sdlc.cli.adopt.run_adopt`. Story 3.5 must add a NEW command. **Decide the surface
> (D2):** the realised sub-app precedent is `register_migrate_commands(app)` (`main.py:390`), which calls
> `app.command(name=f"migrate-v{n}")(...)` — i.e. the repo uses **flat commands**, NOT Typer sub-`Typer()` groups,
> even for the migrate family (`cli/_migrate_register.py:8-27`). No `typer.Typer()` sub-group exists anywhere in
> `cli/main.py`. Command-body imports are deferred per Architecture §488 (every command body imports its `run_*`
> inside the function — see `main.py:70,89,103,119`).
>
> **(B) The orphan-signoff invalidation machinery lives in `engine/replan.py`, which `adopt/` is FORBIDDEN to
> import (AC group 3 — the headline cross-module fact).** `scripts/module_boundary_table.py` declares
> `adopt.forbidden_from = {engine, dispatcher, runtime}` and `adopt.depends_on = {errors, contracts, ids,
> concurrency, state, journal, signoff, config}` (NO `cli`, NO `engine`). The downstream-signoff detection
> functions — `compute_downstream(root, scope_phase)`, `plan_invalidations(root, scope_phase)`,
> `resolve_scope_phase(scope)` — all live in `engine/replan.py:28-83`. **`adopt/` cannot call them.** The
> per-record invalidation primitive `invalidate_record(phase, repo_root=, reason=, now_utc=)` lives in
> `signoff/records.py:331` — which `adopt/` **CAN** import (`signoff` is in `depends_on`). The clean split (D1/D4):
> the orphan-check + `--force` invalidation ORCHESTRATION lives in `cli/` (which holds `engine` access via
> deferred import — see `replan_cmd.py:27`), the symlink-removal + manifest-rewrite + `symlink_rolled_back` journal
> CORE lives in `adopt/`.
>
> **(C) There is NO `sdlc unsign` command — the real invalidation seam is the `replan` pattern (`--force` must
> mirror it).** Grep finds no `unsign` CLI. The realised "invalidate a downstream signoff" precedent is
> `cli/replan_cmd.py:run_replan` (FR4, Story 2A.19): it journals `replan_invalidated` first, then per-phase calls
> `signoff.records.invalidate_record(...)` + journals `signoff_invalidated` (kind already in ADR-028 §3:83). The
> epics.md phrase *"the signoff is invalidated (Story 2A.7 state machine)"* maps to: the `SignoffState` enum +
> `compute_state` (`signoff/states.py`, consumed by `engine/replan.plan_invalidations`
> at `replan.py:15,80`) for DETECTION, and `signoff/records.invalidate_record` (`records.py:331-392`, which sets
> `invalidated_at`/`invalidated_reason` on `phase-<N>.yaml`) for the WRITE. **The dev must NOT hallucinate an
> `sdlc unsign`.** D4 must decide whether `--force` reuses `invalidate_record` directly or delegates to a shared
> helper extracted from `replan_cmd.py`.
>
> **(D) "phase-N" in the AC group 3 error message is derived from the target's leading phase directory.**
> `engine/replan.resolve_scope_phase(scope)` maps a repo-relative path's leading dir
> (`01-Requirement`→1, `02-Architecture`→2, `03-Implementation`→3) to a phase
> (`replan.py:17-40`). The example target `02-Architecture/02-System/ARCHITECTURE.md` → phase 2 →
> `AdoptError("rollback would orphan signoff phase-2; replan first or use --force")`. A target NOT under a
> recognised phase dir has no signoff dependency → no orphan check fires (D4). Note `signoff` records only exist
> for phases {1,2} (`signoff/records.py:57` `_VALID_RECORD_PHASES`); phase 3 has no canonical record
> (`records.py:56,293`).
>
> **(E) `symlink_rolled_back` is a NEW journal kind (no contract edit) and needs an ADR-028 §3 row + Revision-Log
> entry in THIS PR.** `JournalEntry.kind` is a free `str` (`contracts/journal_entry.py`), so the new kind adds NO
> wire-format snapshot churn — but ADR-028 §3 is the canonical taxonomy (newest adopt row today is
> `imported_from_existing`, `ADR-028:96`) and the forward rule (`ADR-028:104-110`) REQUIRES a §3 row + a
> Revision-Log entry (`ADR-028:139+`). The bulk-summary entry shape (D3) is part of this row. **Shared-file
> contention with sibling 3.6** — both add ADR-028 rows; whoever merges first owns the merge (CONTRIBUTING §3).
>
> **(F) Removing a symlink touches ONLY the link node, never the source (NFR-REL-6) — and the symlink slot is the
> one sanctioned non-`.claude/` mutation.** `os.unlink`/`Path.unlink()` on a symlink removes the LINK, not its
> target (mirror the inverse of 3.3's `os.symlink` at `_symlink.py:111`). Rollback's writes are: (i) `unlink` the
> canonical-slot symlink (OUTSIDE `.claude/`, the inverse of 3.3's one sanctioned exception — justify it the same
> way `_symlink.py:8-12` justified creating it), (ii) rewrite the manifest under `.claude/` (pre-guarded by
> `assert_path_under_claude`, `invariant.py:24`), (iii) append the journal under `.claude/`, and (iv) optionally
> delete the `imported-metadata/<id>.yaml` sidecar under `.claude/` (D5 — decide whether rollback prunes the 3.4
> sidecar too). Assert the SOURCE file (`mapping.source`) is byte-identical (sha256) pre/post in every test.
>
> **(G) Coverage floor is operationally `--cov-fail-under=87`, not 90.** `pyproject.toml:248,294` set
> `--cov-fail-under=87` and `fail_under = 87`; CONTRIBUTING.md:22's table says ≥90. The gold-standard 3.4 framed
> this as "operational floor 87; ≥90 tracked as `EPIC-2B-DEBT-COVERAGE-90-FLOOR`". **Unverified:** the exact debt
> token string `EPIC-2B-DEBT-COVERAGE-90-FLOOR` was NOT found verbatim in `CONTRIBUTING.md` / `deferred-work.md`
> during drafting — treat 87 as the operational gate; reconcile the token name at T0 if a code-review flags it.
>
> **(H) `adopt/` may NOT `print()` — human warnings go through the injected `WarnCallback`.** Mirror 3.3/3.4: the
> `cli` layer (`cli/adopt.py:170-171`, `_warn` → `echo(..., err=True)`) injects a `warn` callback into the
> boundary-respecting core. AC group 4's "succeeds idempotently with a warning" routes through that callback (or is
> journaled), never a raw `print`.

1. **Single-target rollback removes one symlink, prunes the manifest, journals, leaves source untouched
   (CORE in `adopt/`; cli orchestration; AC: epics.md:1879-1884).** Given `adopted-symlinks.json` records N
   mappings, when `sdlc adopt rollback --target 02-Architecture/02-System/ARCHITECTURE.md` runs and that target is
   in the manifest: (i) the canonical-slot symlink is `unlink`ed from disk (the LINK only — F); (ii) that one entry
   is removed from `adopted-symlinks.json` (the other N-1 mappings preserved), rewritten atomically
   (`atomic_write_bytes`, pre-guarded by `assert_path_under_claude`); (iii) a journal entry
   `kind=symlink_rolled_back` with payload `{target, source, ...}` (D3) is appended via the SYNC API
   (`allocate_next_seq_for_append_sync` + `append_sync`), event-only (`before_hash=None`, zero-sentinel
   `after_hash`), `actor="cli"`, `target_id="adopt"`; (iv) the source file (`docs/architecture-2024.md`) is
   byte-identical pre/post (assert sha256). A `--target` NOT in the manifest → a typed `AdoptError` (or fail-soft
   warn per D5) — never a silent success that touches nothing. (Optionally also delete the 3.4
   `imported-metadata/<id>.yaml` sidecar — D5.)

2. **Bulk `--all` rollback removes every symlink, empties (preserves) the manifest, single summary journal entry
   (CORE in `adopt/`; AC: epics.md:1886-1890).** Given multiple mappings, when `sdlc adopt rollback --all` runs:
   every symlink in the manifest is `unlink`ed; `adopted-symlinks.json` is left as
   `{schema_version: 1, mappings: []}` — **PRESERVED for audit, NOT deleted** (write `AdoptedSymlinks(mappings=())`
   via the same atomic path); and a SINGLE journal entry summarizes the bulk rollback with the COUNT (D3 — epics is
   explicit: *"a single journal entry summarizes the bulk rollback with the count"*, so prefer one summary
   `kind=symlink_rolled_back` carrying `{count, targets:[...]}` over per-target events). Every source file is
   byte-identical pre/post.

3. **Orphan-signoff refusal + `--force` override (cli ORCHESTRATION, security-sensitive; AC:
   epics.md:1892-1896).** Given a `--target` (or any target in an `--all` set) whose leading phase directory has a
   downstream signoff that depends on it (D), when rollback is requested WITHOUT `--force` → the command refuses
   with `AdoptError("rollback would orphan signoff phase-N; replan first or use --force")` and makes NO change
   (no unlink, no manifest rewrite, no journal mutation). With `--force` → rollback proceeds AND the orphaned
   signoff is invalidated using the realised seam (C): `signoff.records.invalidate_record(phase, ...)` +
   a `signoff_invalidated` journal entry (mirroring `replan_cmd.py:141-192`). "phase-N" is derived via
   `resolve_scope_phase` (D); a target outside a recognised phase dir has no orphan dependency. The detection uses
   `SignoffState.APPROVED` (`signoff/states.compute_state`, the Story-2A.7 state machine — C) exactly as
   `engine/replan.plan_invalidations` does (`replan.py:65-83`). **This orchestration lives in `cli/`** (the
   `engine.replan` + `signoff.records` helpers are reachable from `cli` via deferred import, but NOT from `adopt/`
   — B/D1/D4).

4. **Idempotent reconciliation when on-disk drift (CORE in `adopt/`; AC: epics.md:1898-1901).** Given the symlink
   target on disk no longer matches the manifest (user manually deleted it, or it was repointed), when rollback
   runs → it SUCCEEDS idempotently with a warning (via the `WarnCallback` — H), and the manifest is updated to
   reflect actual state (the stale entry is still pruned/emptied so the manifest converges to disk truth). Cases to
   handle: (a) slot already absent (`not lexists`) → warn "already removed", still prune the entry; (b) slot exists
   but is a real file or a symlink pointing elsewhere (not the recorded `source`) → warn "no longer an adopt
   symlink; leaving on-disk file untouched", still prune the entry (do NOT delete a non-adopt file — NFR-REL-6);
   (c) slot is a dangling/broken symlink → `unlink` it (it's our link) + prune. No case ever raises; reconciliation
   is the whole point (D5).

5. **Boundary held + source untouched + no `print` (AC: NFR-REL-6, prd.md:290/336, architecture.md:1110).** The
   `adopt/` rollback core imports contain no `cli`/`engine`/`dispatcher`/`runtime`/`specialists`
   (`check_module_boundaries` — add a focused assertion on the new module). The cli orchestration may import
   `engine.replan` + `signoff.records` (deferred per §488) — that is `cli`'s grant, not `adopt`'s. Removing a
   symlink and the manifest/journal/sidecar writes touch ONLY the link node + `.claude/`; every adopt SOURCE file
   is byte-identical pre/post (assert sha256 in tests). No `print()` in `adopt/` (warnings via `WarnCallback`).

6. **Quality gate green + TDD-first (AC: CONTRIBUTING §1-§2).** ruff format/check + `mypy --strict src/` + pytest +
   coverage (operational floor `--cov-fail-under=87` per `pyproject.toml:248`; the table-stated ≥90 is the tracked
   stretch — G) + pre-commit (incl. `check_module_boundaries`, `check_subprocess_allowlist`,
   `freeze_wireformat_snapshots --check` — **stays 7/7: rollback adds NO new wire-format contract**, it only
   consumes + rewrites the frozen `adopted-symlinks.json` and adds a free-`str` journal kind) + mkdocs `--strict`.
   TDD-first (§2): tests-first RED commit before implementation, visible in `git log --reverse` (mirror
   `test(3.4) RED → feat(3.4) GREEN`).

---

## Tasks / Subtasks

- [x] **(AC6, §5) T0 — Resolve D1-D6 in the PR Change Log BEFORE writing code.** Lock D1 (rollback-core module
  location + `cli`/`adopt` split — gates the file set + boundary), D2 (command surface + `--all`/`--target`
  mutual-exclusion validation), D3 (bulk `--all` journal shape + single-target payload), D4 (orphan-signoff
  detection + `--force` invalidation seam), D5 (idempotent reconciliation semantics + whether to prune the 3.4
  sidecar), D6 (manifest-rewrite reuse). D1 + D4 gate the boundary, so settle them first. Also reconcile the
  coverage-debt token name (G) if a reviewer asks.
- [x] **(AC1, AC2, AC4, §2) Write the failing rollback CORE unit tests FIRST, commit before implementation**
  (`tests/unit/adopt/test_rollback.py`):
  - `--target` present in a 5-mapping manifest → that symlink `unlink`ed; manifest down to 4 entries (others
    intact); one `symlink_rolled_back` event with `{target, source}` payload; **source bytes byte-identical**
    (assert sha256 before == after); only `.claude/` + the one slot changed.
  - `--target` NOT in the manifest → typed `AdoptError` / fail-soft warn (per D5), no mutation.
  - `--all` over 3 mappings → all 3 symlinks gone; manifest = `{schema_version:1, mappings:[]}` (NOT deleted —
    file still exists); ONE summary journal entry carrying the count (D3); all 3 sources byte-identical.
  - idempotency (AC4): slot already deleted → success + warn + entry still pruned; slot is a real file → success +
    warn + file untouched + entry pruned; dangling symlink → unlinked + pruned. **No case raises.**
  - boundary: the new `adopt/` rollback module imports contain no `cli`/`engine`/`dispatcher`/`runtime`/
    `specialists` (focused assertion mirroring 3.4's stamp boundary test).
- [x] **(AC1, AC2, AC4, D1/D3/D5/D6) Implement the rollback CORE (GREEN)** — propose home `src/sdlc/adopt/rollback.py`
  (D1; note the DAG naming drift, citation-drift note below). A pure-ish function e.g.
  `rollback(root, *, targets: Sequence[str] | None, journal_path, warn) -> RollbackResult` that: loads the manifest
  (`symlink_offer._load_existing_mappings`, reused), selects the mappings to remove (`--all` ⇒ all; `--target` ⇒
  the matching entry), per mapping unlinks the slot **fail-soft / idempotent** (D5 reconciliation), prunes/empties
  the manifest, REWRITES it atomically (D6 — reuse `symlink_offer._write_manifest` or extract a shared
  `adopt/_manifest.py` writer so the two passes can't drift), appends the `symlink_rolled_back` journal event(s)
  (D3), and optionally deletes the 3.4 sidecar via `imported_metadata.metadata_record_path(root, target)` (D5).
  Keep ≤400 LOC (NFR-MAINT-3); extract a `_remove_one_symlink` reconciliation helper. Source files are NEVER
  unlinked — only the link node + `.claude/` writes.
- [x] **(AC3, D4 — cli ORCHESTRATION, security-sensitive) Write the failing orphan-signoff tests FIRST**
  (`tests/unit/cli/test_adopt_rollback.py`): a target under `02-Architecture/` with an APPROVED phase-2 signoff →
  rollback WITHOUT `--force` refuses with the exact `AdoptError("rollback would orphan signoff phase-2; replan
  first or use --force")` message and makes NO change; WITH `--force` → proceeds AND `phase-2.yaml` shows
  `invalidated_at` set + a `signoff_invalidated` journal entry; a target outside a phase dir (or whose phase has no
  APPROVED signoff) → no orphan check, rollback proceeds. Then implement `cli/adopt_rollback.py` (or extend
  `cli/adopt.py`) — D2 command wiring + the orphan check (reuse `engine.replan.resolve_scope_phase` +
  `signoff.states.compute_state` / `signoff.records` via deferred import) + the `--force` invalidation (mirror
  `replan_cmd.py:141-192`: `invalidate_record` + `signoff_invalidated` journal entry).
- [x] **(AC2, D2) Register the `sdlc adopt rollback` command in `cli/main.py`** (D2: flat command e.g.
  `adopt-rollback`, or a Typer sub-`Typer()` group `adopt` with a `rollback` subcommand — note the repo precedent
  is FLAT, A). Validate `--all` XOR `--target` (exactly one required); `--json` ⇒ machine envelope (mirror
  `cli/adopt.py:195-205`). Defer the body import per Architecture §488. **Shared-file note:** `cli/main.py` is
  edited by 3.5 (new command); confirm 3.6 does not also edit it before merge.
- [x] **(AC1/AC2, E) Amend the journal taxonomy:** add a `symlink_rolled_back` row to ADR-028 §3 (alphabetised
  within the Story-3.5 source column) + a Revision-Log entry describing the single-target payload `{target,
  source}` AND the bulk-summary payload `{count, targets}` (D3). **Shared-file contention with 3.6** — rebase
  before merge; first merger owns the table merge (CONTRIBUTING §3).
- [x] **(AC5, §1) Boundary + gate verification:** `check_module_boundaries` green (adopt core has no forbidden
  import; cli orchestration's `engine`/`signoff` imports are cli's grant); `freeze_wireformat_snapshots --check`
  stays 7/7 (no new contract); `mypy --strict src/`; coverage ≥87.
- [x] **(AC6, §4) Chunked review** review-A (correctness / AC↔tests / manifest-prune fidelity / source-byte-identity /
  `--all` empties-not-deletes) → review-B (boundary: no `adopt→cli`/`engine`/`specialists`; **the orphan-signoff
  refusal + `--force` invalidation is security-critical — verify the refusal is fail-CLOSED (no partial mutation
  before the check) and `--force` actually invalidates via the real seam, not a no-op**; idempotent reconciliation
  never deletes a non-adopt file) → review-C (ADR-028 row + 7/7 snapshot count + payload exactness + `phase-N`
  derivation + command-surface naming + `--all`/`--target` XOR validation). No skipping; review commits carry
  `[fresh-context-review]`, stage no `src/` (§4.4). → Runs in the `code-review` workflow once `dev-story` sets
  status=review.

### Review Findings

> Code review (`bmad-code-review`) — 2026-06-04. Layers: Blind Hunter, Edge Case Hunter, Acceptance
> Auditor (all 3 completed; none failed). Initial triage: **3 decision-needed, 4 patch, 2 defer, ~10
> dismissed**. After decision resolution + commit gate (2026-06-04): **6 patch, 2 defer, ~12 dismissed**
> (1 decision→patch P5, 2 decisions→dismiss; P6 LOC-cap caught by the `boundary-validator` pre-commit hook).
> (false-positive / by-design). Load-bearing facts verified against `main`@`bc07c23`: `emit_error` is
> `NoReturn` (raises `typer.Exit`); `append_sync` raises `JournalError`; `compute_state` raises
> `SignoffError`; `JournalEntry.schema_version` defaults to 1; `compute_state(3, strict=False)` returns
> `AWAITING_SIGNOFF` (no crash).

**Decision-needed (resolved 2026-06-04 — `Vuonglq01685`):**

- [x] [Review][Decision→Patch P5] `--force` crash-consistency ordering — `_invalidate_phases` invalidates
  signoffs + journals `signoff_invalidated` BEFORE `_rollback_core` removes symlinks
  (`cli/adopt_rollback.py` `run_adopt_rollback`). **RESOLVED:** add a leading intent journal anchor before
  invalidation (mirror `replan_cmd.py` fail-loud posture). Tracked as patch **P5** below.
- [x] [Review][Decision→Dismiss] Drift-skipped targets counted as "removed" (`adopt/rollback.py`
  `rollback()` loop ~:148). **RESOLVED:** keep as-is — manifest-prune == rollback semantically per AC4
  ("still prune the entry"); the `WarnCallback` already signals the left-on-disk file.
- [x] [Review][Decision→Dismiss] `--json` drops AC4 reconciliation warnings (`echo` no-ops under `--json`;
  core never journals drift). **RESOLVED:** accept — warnings are advisory and `removed_targets` stays
  accurate; no JSON-envelope change.

**Patch:**

- [x] [Review][Patch] `_invalidate_phases` misses `JournalError` from `append_sync` — `append_sync` raises
  `JournalError` (verified `journal/writer.py`), but the guard is `except OSError` only
  [cli/adopt_rollback.py:106]. A lock/IO failure on the `signoff_invalidated` append leaks a raw
  traceback (no error envelope) after the signoff was already invalidated on disk. Fix:
  `except (OSError, JournalError)`.
- [x] [Review][Patch] Orphan check does not catch `SignoffError` — `compute_state` raises `SignoffError`
  on a malformed canonical record / malformed `SIGNOFF.md` draft (verified `signoff/states.py:66,73`),
  but `_phases_orphaned_by_rollback` catches only `WorkflowError` [cli/adopt_rollback.py:51,53]. A
  malformed signoff crashes the orphan check with a raw traceback (fail-closed preserved, but ugly). Fix:
  also catch `SignoffError` → `emit_error("ERR_INFRASTRUCTURE", ...)`.
- [x] [Review][Patch] Core `_reconcile_and_unlink` unlinks without an under-root guard —
  `slot = root / mapping.target` is unlinked [adopt/rollback.py:88,99,103] without the
  `is_target_under_root(root, target)` guard the Reuse map lists for exactly this purpose ("validate
  manifest target/source before touching disk"). A tampered manifest `target` with `../` could unlink
  outside the repo (mitigated only by the source-match check) — AC5 says writes touch ONLY the link node
  + `.claude/`. Fix: guard `mapping.target` (+ `mapping.source`) before unlink; warn+skip on escape.
- [x] [Review][Patch] `signoff_file.read_bytes()` unwrapped — after `invalidate_record` succeeds, the
  read at [cli/adopt_rollback.py:88] is unwrapped; an OSError there leaks a raw traceback. Fix: wrap →
  `emit_error("ERR_INFRASTRUCTURE", ...)` (or fold into the P1-broadened guard).
- [x] [Review][Patch] P5 (from D-a) `--force` audit anchor — `_invalidate_phases` mutates signoff records
  + journals `signoff_invalidated` before `_rollback_core` runs (`cli/adopt_rollback.py`
  `run_adopt_rollback`); a leading intent anchor is missing vs the `replan_cmd.py` precedent. Fix: journal
  a leading intent entry (e.g. an `adopt-rollback` intent marker) BEFORE the first `invalidate_record`,
  mirroring `run_replan`'s journal-first fail-loud posture, so the audit chain records intent even if a
  later step raises.
- [x] [Review][Patch] P6 (commit-gate-caught) `cli/main.py` LOC cap exceeded — the new `adopt-rollback`
  command pushed `cli/main.py` to 419 lines, over the 400-line NFR-MAINT-3 cap (flagged by the
  `boundary-validator` pre-commit hook; missed by all 3 review layers — none had LOC-cap context). Fix:
  extract the command shell into a lightweight `cli/_adopt_rollback_register.py` (mirrors
  `_migrate_register`; only `typer` at module top, `run_adopt_rollback`/`emit_error` deferred into the body
  per §488); `main.py` now calls `register_adopt_rollback_command(app)` → 392 lines.

**Defer (pre-existing / by-design):**

- [x] [Review][Defer] `load_adopted_target_sources` silent `{}` on corrupt manifest
  [cli/_adopted_targets.py:23-26] — deferred, pre-existing (Story 3.4 helper). Consumed by the new
  `--all`/`--target` paths: `--all` on a corrupt manifest skips the orphan check (the core still warns via
  `_load_existing_mappings`); `--target` reports "not in manifest" misleadingly. Fail-open lives in 3.4's
  helper, not in 3.5 code.
- [x] [Review][Defer] Core journal-vs-manifest crash-consistency residual gap (unlink-all → journal →
  rewrite-manifest) [adopt/rollback.py:135-170] — deferred, by-design; documented in the module docstring
  + spec (CR3.4-W1, full reconciliation is 3.6 scope). Converges on re-run via AC4 idempotency.

---

## Dev Notes

### What 3.3 + 3.4 froze — the surfaces 3.5 consumes + reverts

- **The manifest (frozen, read + REWRITE):** `AdoptedSymlinks.mappings: tuple[SymlinkMapping, ...]`,
  `SymlinkMapping{source: str, target: str, accepted_at: <RFC-3339>, kind: ArtifactKind}`
  (`contracts/adopted_symlinks.py:29-50`). Rollback READS it like Pass 2/3 do
  (`symlink_offer._load_existing_mappings`, `symlink_offer.py:91-113` — including the corrupt-manifest
  warn-don't-swallow stance) and REWRITES it atomically (`--target` ⇒ N-1 entries; `--all` ⇒ `mappings=()`
  PRESERVED not deleted) via `symlink_offer._write_manifest` (`symlink_offer.py:116-120`) — which already calls
  `assert_path_under_claude` + `atomic_write_bytes`. D6: reuse it directly, or extract both passes' manifest I/O
  into `adopt/_manifest.py` to prevent drift.
- **The journal event pattern to mirror:** `symlink_offer._append_symlink_event` (`symlink_offer.py:123-142`) and
  `driver._append_event` (`driver.py:48-62`) — event-only, `before_hash=None`, `after_hash=_ZERO_HASH`
  (`"sha256:"+"0"*64`), `actor="cli"`, `target_id="adopt"`, SYNC API
  (`allocate_next_seq_for_append_sync(journal_path)` + `append_sync(entry, journal_path=)`).
- **The slug for locating 3.4 sidecars (D5):** `imported_metadata.artifact_id_for_target(target)`
  (`imported_metadata.py:28-35`) + `metadata_record_path(root, target)` (`imported_metadata.py:49-51`) — if D5
  prunes the sidecar, reuse these to find `.claude/state/imported-metadata/<slug>.yaml`.
- **The manifest reader the cli side already has:** `cli/_adopted_targets.load_adopted_target_sources(root)`
  (`_adopted_targets.py:13-27`) returns `{target: source}` — handy for the cli orchestration to validate
  `--target` membership before invoking the core. `load_adopted_targets(root)` returns the target set
  (`_adopted_targets.py:30-32`).

### Reuse map (do NOT reinvent — verified file:line)

| Need | Reuse | Source |
|---|---|---|
| Load + parse the manifest (warn-on-corrupt) | `_load_existing_mappings(root, warn=)` | `adopt/passes/symlink_offer.py:91-113` |
| Atomic manifest rewrite (`--target` prune / `--all` empty) | `_write_manifest(root, mappings)` (calls `assert_path_under_claude` + `atomic_write_bytes`) | `adopt/passes/symlink_offer.py:116-120` |
| Canonical manifest bytes | `_manifest_bytes(AdoptedSymlinks(mappings=...))` | `adopt/passes/symlink_offer.py:80-88` |
| Append event-only journal entry | copy `_append_symlink_event` shape (zero-sentinel `after_hash`, SYNC API) | `adopt/passes/symlink_offer.py:123-142`; `adopt/driver.py:48-62` |
| SYNC journal API | `allocate_next_seq_for_append_sync(path)` + `append_sync(entry, journal_path=)` | `journal/writer.py:224,309`; re-exported `journal/__init__.py:11-15` |
| `JournalEntry` fields | `kind` free `str`; `after_hash` non-null (zero-sentinel); `before_hash` nullable | `contracts/journal_entry.py` |
| Stay-under-`.claude/` guard | `assert_path_under_claude(root, path)` (raises `AdoptError`) | `adopt/invariant.py:24` |
| Target-under-root guard (validate manifest `target`/`source` before touching disk) | `is_target_under_root(root, target_rel)` | `adopt/passes/_symlink.py:46-57` |
| RFC-3339 timestamp | `now_rfc3339_utc_ms()` | `ids/clock.py:13` |
| Typed error envelope | `AdoptError` → `ERR_ADOPT` (exit 2); wrap `OSError`, don't leak tracebacks | `errors/base.py`; mapped in `cli/adopt.py:192-193` |
| `--target` membership + source map (cli side) | `load_adopted_target_sources(root)` → `{target: source}` | `cli/_adopted_targets.py:13-27` |
| 3.4 sidecar location (D5 prune) | `metadata_record_path(root, target)` / `artifact_id_for_target` | `adopt/imported_metadata.py:28-51` |
| Phase derivation for "phase-N" | `resolve_scope_phase(scope)` (leading dir → phase) | `engine/replan.py:28-40` |
| Orphan-signoff detection (APPROVED state) | `compute_state(phase, repo_root=)` + `SignoffState.APPROVED` | `signoff/states.py` (via `engine/replan.py:15,80`) |
| `--force` signoff invalidation | `invalidate_record(phase, repo_root=, reason=, now_utc=)` + `signoff_invalidated` journal entry | `signoff/records.py:331-392`; pattern at `cli/replan_cmd.py:141-192` |
| cli `--force`/orchestration precedent | `run_replan` (journal-first, per-phase invalidate, `signoff_invalidated`) | `cli/replan_cmd.py:37-205` |

### The orphan-signoff seam (AC group 3 / D4) — the headline cross-module decision

`adopt/` is **forbidden** from importing `engine` (`module_boundary_table.py` — `adopt.forbidden_from =
{engine, dispatcher, runtime}`), and the downstream-detection functions live in `engine/replan.py`. `adopt/` CAN
import `signoff` (it's in `depends_on`), and `invalidate_record` lives in `signoff/records.py`. So:

- **Detection** (`resolve_scope_phase` + `compute_downstream`/`plan_invalidations`) → `engine/replan.py` → reachable
  ONLY from `cli/` (mirror `replan_cmd.py:27` `from sdlc.engine.replan import ...`). Therefore the orphan-CHECK
  must live in the `cli` orchestration.
- **Invalidation** (`invalidate_record`) → `signoff/records.py` → reachable from `cli` AND from `adopt`. But since
  the check already lives in `cli` (it needs `engine`), keep the `--force` invalidation in `cli` too, mirroring
  `replan_cmd.py` exactly (journal `signoff_invalidated` after `invalidate_record`). Do NOT split it across the
  boundary.
- This is the crux of **D1/D4**: the symlink-removal + manifest-rewrite + `symlink_rolled_back` journal is pure
  `adopt/` core; the orphan-check + `--force` invalidation + TTY/arg parsing is `cli/` orchestration. The core is
  invoked AFTER the cli orchestration has cleared (or `--force`-overridden) the orphan check — **fail-CLOSED:** no
  unlink, no manifest rewrite, no journal mutation happens before the check passes (review-B verifies this).
- **There is NO `sdlc unsign`** — the `replan` pattern IS the seam (C). "Story 2A.7 state machine" = `SignoffState`
  / `compute_state` (detection) + `invalidate_record` setting `invalidated_at`/`invalidated_reason` (write). If a
  reviewer expects a literal "state machine" object, point them at `signoff/states.py` (the `SignoffState` enum +
  `compute_state` transition logic) — surfaced here as a binding correction so the dev doesn't invent a new API.

### Bulk `--all` journal shape (D3)

epics.md:1890 is explicit: *"a single journal entry summarizes the bulk rollback with the count."* So `--all`
should emit ONE `symlink_rolled_back` entry with payload `{count: <n>, targets: [...]}` (NOT one event per target).
The single-target path emits ONE `symlink_rolled_back` with `{target, source}`. Reconcile the two payload shapes in
the one ADR-028 §3 row (E). Alternative (per-target events even for `--all`) contradicts the verbatim AC — note it
as the rejected option.

### Idempotent reconciliation (AC group 4 / D5)

Mirror 3.3/3.4 fail-soft: a per-mapping helper warns + continues, never raises. Use `Path.is_symlink()` /
`os.path.lexists()` (NOT `.exists()`, which follows the link and is False for a dangling symlink). Decide per case:
slot absent → warn + prune; slot is a real file or a symlink to something other than `mapping.source` → warn +
DO NOT delete (NFR-REL-6 — never touch a non-adopt file) + prune the stale entry; dangling/our-symlink → unlink +
prune. The manifest converges to disk truth in all cases. D5 also decides whether the 3.4 sidecar
(`imported-metadata/<id>.yaml`) is pruned alongside — recommended yes (keeps `.claude/state/` consistent), via
`metadata_record_path`, fail-soft.

### Boundary, fail-soft, crash-consistency

- `adopt/` granted deps: `{errors, contracts, ids, concurrency, state, journal, signoff, config}` — NO
  `cli`/`engine`/`dispatcher`/`runtime`/`specialists` (`module_boundary_table.py`). No `print()` in `adopt/`
  (warnings via `WarnCallback`, H).
- Order (crash-consistency, mirror Pass 2's stance `symlink_offer.py:21-26,271-275`): per mapping — `unlink` the
  slot → append the `symlink_rolled_back` journal event → (after the loop) rewrite the manifest once. The journal
  is the audit source of truth; the manifest is a derived cache. A mid-loop crash may leave the manifest lagging
  the journal — note the residual gap in the module docstring (3.3/3.4 set this precedent; full reconciliation is
  the rollback's own idempotency on re-run, AC4).
- The driver wraps any exception into `AdoptError` → `cli/adopt.py` maps to `ERR_ADOPT` (exit 2). The new command
  should mirror `cli/adopt.py:185-193`'s `AdoptError`/`JournalError` → `emit_error("ERR_ADOPT", ...)`.

### Citation-drift / reconciliation notes (verified)

- **`adopt/symlink.py` name** appears in `epic-3-dag.md:116,145,151` + the 3.7 mutation-target list, but Stories
  3.1/3.3 froze the realised layout as `adopt/passes/*.py` (`symlink_offer.py`, `_symlink.py`) + `adopt/driver.py`
  + `adopt/invariant.py` + `adopt/imported_metadata.py`. Put the rollback core under `adopt/` as a NEW module
  (`adopt/rollback.py` recommended) — note the rename so 3.7's mutation-target list is updated (3.4 raised the same
  `adopt/symlink.py` caveat).
- **PRD §275 / §321 citation drift (epics.md Story-3.5 prose).** epics.md cites *"PRD §275, §321 — closes John's
  recovery gap"*, but `prd.md` lines 273-277 / 319-323 are the **Lam/Quan auto-loop journey**, NOT a "John"
  recovery narrative. The actual adopt/rollback PRD content is **`prd.md:290`** (Khanh journey — *"The accepted
  ones are tracked in `.claude/state/adopted-symlinks.json` for rollback"*), **`prd.md:296`** (*"adopted-symlinks
  rollback record"*), and **`prd.md:336`** (*"rollback via `adopted-symlinks.json`"*). The story As-a/so-that
  cites the verified `prd.md:290/296/336` lines instead. There is no "John" persona for adopt mode in the realised
  PRD — the brownfield-adopt persona is **Khanh**. Do not cite §275/§321; do not invent a "John" persona.
- **No floats in `.claude/state/*`** (`architecture.md:496-515`) — N/A for the journal/manifest rewrite (no
  confidence floats touched by rollback), but the rule still applies to any payload field added.

### Previous-story intelligence (Stories 3.3 + 3.4, done + merged @ `bc07c23`)

- 3.3 landed the `adopted-symlinks.json` + `symlink_accepted` + atomic-manifest + `_append_symlink_event` +
  `WarnCallback` + fail-soft patterns 3.5 mirrors. Its CR3.3 carry-overs relevant to 3.5:
  - **CR3.3-P3:** a corrupt prior manifest must WARN, not be silently swallowed. Apply to rollback's manifest read.
  - adopt mode is **POSIX-only (ADR-034)** — all new test modules `pytest.skip` on win32 (see
    `tests/unit/adopt/test_symlink_offer.py`, `tests/integration/test_adopt_mode_invariant.py:19-20`). The journal
    writer is POSIX-only (`journal/__init__.py` raises `JournalError` on win32).
- 3.4 (CR3.4) carry-overs relevant to 3.5:
  - **CR3.4-P0 (source-binding):** the verify/signoff consuming side now binds a known-adopted symlink to its
    manifest `source` (`resolved == (root/mapping.source).resolve()`) — defense-in-depth via
    `load_adopted_target_sources`. Rollback's AC4 case (b) is the mirror: when the on-disk slot does NOT resolve to
    the recorded `source`, treat it as drift (do not delete it). Reuse `load_adopted_target_sources`
    (`_adopted_targets.py`) on the cli side for the membership/source check.
  - **CR3.4-W1 (deferred to 3.6):** crash between journal-append and sidecar/manifest write leaves an orphan event
    — full reconciliation is 3.6's scope; rollback's own re-run idempotency (AC4) covers the rollback path. Add a
    residual-gap note to the new module docstring.
  - D2 stayed **internal-state** (7/7 snapshots, no 8th contract). Rollback adds NO contract → stays 7/7 (AC6).

### Project Structure Notes

- **New:** `src/sdlc/adopt/rollback.py` (rollback core, D1); `src/sdlc/cli/adopt_rollback.py` (cli orchestration +
  orphan check + `--force` invalidation, D1/D4 — or fold into `cli/adopt.py` if small);
  `tests/unit/adopt/test_rollback.py`; `tests/unit/cli/test_adopt_rollback.py`; (D6, optional)
  `src/sdlc/adopt/_manifest.py` if the manifest I/O is extracted from `symlink_offer.py`; ADR-028 §3 row +
  Revision-Log entry.
- **Edit:** `src/sdlc/cli/main.py` (register the `adopt rollback` command, D2);
  `docs/decisions/ADR-028-journal-kind-taxonomy.md` (§3 row + Revision Log — **shared with 3.6**); (D6 only) maybe
  `src/sdlc/adopt/passes/symlink_offer.py` (export/relocate the manifest writer — keep it backward-compatible so
  Pass 2 is unaffected).
- **Do NOT edit:** `src/sdlc/contracts/adopted_symlinks.py` (FROZEN 7th contract) — consume + rewrite, never
  reshape; the 7 existing snapshots; the journal/atomic primitives; `engine/replan.py` (consume read-only from
  `cli`); `signoff/records.py` (consume `invalidate_record` read-only — do not change the signoff write path).
- ≤400 LOC per file (NFR-MAINT-3); extract the reconciliation helper rather than bloating `rollback.py`.

### Testing standards

- pytest; AAA structure; coverage ≥87 operational floor (G). TDD-first (§2): rollback CORE + cli orchestration unit
  tests in a RED commit before the GREEN implementation (mirror `test(3.4) RED → feat(3.4) GREEN`). adopt mode
  POSIX-only (ADR-034) — module-level `pytest.skip` on win32.
- **Security tests are non-optional (AC3):** the orphan-signoff refusal must be fail-CLOSED — assert NO mutation
  (no unlink, no manifest change, no journal entry) when the refusal fires WITHOUT `--force`; assert `--force`
  actually sets `invalidated_at` on the signoff record + journals `signoff_invalidated`. The idempotent
  reconciliation (AC4) must NEVER delete a non-adopt file (assert a real file at the slot survives + bytes
  unchanged).
- **Source-byte-identity** is asserted per test (sha256 before == after on `mapping.source`); the binding
  multi-fixture property/mutation gate is **Story 3.7**, not 3.5 — 3.5 needs correctness + unit coverage + the
  focused byte-identity assertion, not the corpus property test.

## Decisions Needed

> Resolve at T0 in the PR Change Log (CONTRIBUTING §5), mirroring Stories 3.3/3.4. Recommended option first; the
> dev locks the choice before writing code. **D1 + D4 are the headline** — they set the module boundary split and
> the security-critical invalidation seam.

- **D1 — Rollback-core module location + the `cli`/`adopt` split.**
  - **(a) [Recommended]** Core in `src/sdlc/adopt/rollback.py` (symlink-unlink + manifest-rewrite +
    `symlink_rolled_back` journal + idempotent reconciliation + optional sidecar prune); orchestration in
    `src/sdlc/cli/adopt_rollback.py` (arg parsing, `--all`/`--target` XOR, orphan check via `engine.replan`,
    `--force` invalidation via `signoff.records`, `--json` envelope). Rationale: `adopt/` is forbidden from
    `engine` (B), so the orphan-check MUST be in `cli`; the symlink/manifest/journal mechanics belong in `adopt/`
    with the rest of the pass infra. Mirrors the established `adopt/`-core + `cli/`-orchestration split of
    Pass 2/3.
  - (b) Everything in `cli/adopt_rollback.py` (no `adopt/` core). Rejected: duplicates the manifest/journal infra
    `adopt/` already owns; loses the boundary discipline + reuse of `_write_manifest`/`_append_symlink_event`.
  - (c) Core in `adopt/passes/` (e.g. `adopt/passes/rollback.py`). Plausible (sits with the other passes) but
    rollback is not one of the 3 ordered passes — a top-level `adopt/rollback.py` reads truer to its recovery role.
- **D2 — `sdlc adopt rollback` command surface + `--all`/`--target` validation.**
  - **(a) [Recommended] Flat command `adopt-rollback`** (matches the realised repo precedent — `migrate-v{n}` is
    flat, `cli/_migrate_register.py`; no Typer sub-`Typer()` group exists in `cli/main.py`, A). `--all` XOR
    `--target` validated in the body: exactly one required, else `ERR_USER_INPUT`. Lowest-friction; consistent
    surface. (epics.md WRITES it as `sdlc adopt rollback` — a flat `adopt-rollback` is the closest realised
    idiom; document the spelling choice.)
  - (b) Typer sub-group `adopt` (a `typer.Typer()` mounted via `app.add_typer(adopt_app, name="adopt")`) with a
    `rollback` subcommand — matches the epics.md spelling literally (`sdlc adopt rollback`) and leaves room for
    future `sdlc adopt <verb>` commands. Cost: introduces the FIRST sub-`Typer()` group in the codebase (novel
    pattern; verify `app.obj`/`--json` context propagation through the sub-app). Choose this if the literal
    `adopt rollback` spelling is required by the AC.
- **D3 — Bulk `--all` journal shape + single-target payload.**
  - **(a) [Recommended] `--all` → ONE summary `symlink_rolled_back` entry** with `{count, targets:[...]}` (epics is
    explicit: *"a single journal entry summarizes the bulk rollback with the count"*, epics.md:1890);
    `--target` → ONE `symlink_rolled_back` with `{target, source}`. Both event-only (zero-sentinel `after_hash`).
  - (b) Per-target `symlink_rolled_back` events even for `--all`. Rejected: contradicts the verbatim "single journal
    entry … with the count" AC.
- **D4 — Orphan-signoff detection + `--force` invalidation seam (security-sensitive).**
  - **(a) [Recommended] Reuse the realised `replan` seam from `cli/`** (C): detect via
    `engine.replan.resolve_scope_phase(target)` → phase, then `signoff.states.compute_state(phase, repo_root=)` ==
    `APPROVED` (the Story-2A.7 state machine); refuse without `--force` (`AdoptError("rollback would orphan signoff
    phase-N; replan first or use --force")`, fail-closed); with `--force`, invalidate via
    `signoff.records.invalidate_record(phase, repo_root=, reason="invalidated by adopt rollback", now_utc=)` +
    append a `signoff_invalidated` journal entry (mirror `replan_cmd.py:141-192`). "phase-N" via
    `resolve_scope_phase` (D); targets outside a recognised phase dir skip the check. **There is NO `sdlc unsign`.**
  - (b) Extract a shared `invalidate_phase_signoff(...)` helper from `replan_cmd.py` and call it from both. Cleaner
    DRY, but a larger blast radius (touches the 2A.19 replan path) — defer unless review-B asks. Recommended only if
    duplication is flagged.
  - (c) Use the richer `engine.replan.plan_invalidations(root, scope_phase)` (returns ALL APPROVED phases ≥ scope)
    instead of a single `compute_state` check. Consider for `--all` (a bulk rollback could orphan multiple phases),
    but heavier; (a)'s per-target check is sufficient for v1 — note `--all` may need to aggregate phases (D4 sub).
- **D5 — Idempotent reconciliation semantics (AC group 4) + sidecar pruning.**
  - **(a) [Recommended] Fail-soft converge-to-disk-truth + prune the 3.4 sidecar.** slot absent → warn + prune;
    slot is a real file / foreign symlink (not `mapping.source`) → warn + DO NOT delete + prune the stale entry;
    dangling/our symlink → unlink + prune. Always also delete `metadata_record_path(root, target)` (fail-soft) so
    `.claude/state/imported-metadata/` stays consistent. No case raises. Use `lexists`/`is_symlink` (not `exists`).
  - (b) Same reconciliation but LEAVE the 3.4 sidecar in place (rollback only touches the manifest + slot).
    Lighter, but leaves a stale `imported-from-existing` sidecar for a target that's no longer adopted — mildly
    inconsistent. Choose only if D5's sidecar coupling is deemed out of scope.
- **D6 — Manifest-rewrite reuse.**
  - **(a) [Recommended] Reuse `symlink_offer._write_manifest` / `_manifest_bytes` directly** (import from
    `adopt.passes.symlink_offer`). Zero drift risk; both surfaces produce byte-identical manifests. (The leading
    underscore is intra-`adopt/` — acceptable to import within the package, but consider (b) if a reviewer objects
    to importing a private name across modules.)
  - (b) Extract the manifest I/O (`_manifest_bytes`, `_load_existing_mappings`, `_write_manifest`) into a new
    `src/sdlc/adopt/_manifest.py` and have BOTH `symlink_offer.py` and `rollback.py` import it. Cleaner public
    seam; small refactor of the (frozen-behaviour) Pass 2 imports — keep Pass 2 byte-identical. Recommended if
    importing the private `_write_manifest` is flagged in review-C.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1873-1901] — Story 3.5 ACs (single-target rollback, `--all`,
  orphan-signoff refusal + `--force`, idempotent reconciliation).
- [Source: _bmad-output/planning-artifacts/epics.md:1883] — journal `kind=symlink_rolled_back, target, source`.
- [Source: _bmad-output/planning-artifacts/epics.md:1888-1890] — `--all` → `{schema_version:1, mappings:[]}`
  preserved; single journal entry summarizes the bulk rollback with the count.
- [Source: _bmad-output/planning-artifacts/epics.md:1892-1896] — `AdoptError("rollback would orphan signoff
  phase-N; replan first or use --force")`; `--force` invalidates the signoff (Story 2A.7 state machine).
- [Source: _bmad-output/planning-artifacts/prd.md:290,296,336] — Khanh journey: adopted symlinks tracked in
  `adopted-symlinks.json` for rollback; rollback record; "rollback via `adopted-symlinks.json`". (NB: epics.md's
  "PRD §275, §321 / John" citation is a drift — those PRD lines are the Lam/Quan auto-loop journey; see
  citation-drift note.)
- [Source: docs/sprints/epic-3-dag.md:52-53,97,111-113,126,132-133,146] — Layer 5 (3.5 ‖ 3.6, max 2), deps 3.3+3.4,
  off-critical-path branch (length 5), worktree `epic-3/3-5-adopt-rollback` (Elena), "refuses if it orphans a
  downstream signoff".
- [Source: src/sdlc/cli/main.py:75-105,390] — `init --adopt` hidden flag (no `adopt` group today); flat-command
  registration precedent `register_migrate_commands(app)`.
- [Source: src/sdlc/cli/_migrate_register.py:8-27] — the only dynamic command registration; FLAT `migrate-v{n}`
  commands, no sub-`Typer()` (D2).
- [Source: src/sdlc/contracts/adopted_symlinks.py:29-50] — `AdoptedSymlinks`/`SymlinkMapping` (read + rewrite
  target); 7th frozen contract.
- [Source: src/sdlc/adopt/passes/symlink_offer.py:80-120,123-142] — `_manifest_bytes` / `_load_existing_mappings`
  / `_write_manifest` (reuse for rewrite) + `_append_symlink_event` (mirror for `symlink_rolled_back`).
- [Source: src/sdlc/adopt/driver.py:48-62] — `_append_event` event-only zero-sentinel pattern.
- [Source: src/sdlc/adopt/passes/_symlink.py:46-57,108-117] — `is_target_under_root` guard; `os.symlink` (the
  inverse of the `unlink` rollback performs; the slot is the one sanctioned non-`.claude/` mutation, :8-12).
- [Source: src/sdlc/adopt/invariant.py:24] — `assert_path_under_claude` (manifest/journal/sidecar writes).
- [Source: src/sdlc/adopt/imported_metadata.py:28-51] — `artifact_id_for_target` / `metadata_record_path` (D5
  sidecar prune).
- [Source: src/sdlc/journal/writer.py:224,309] — `allocate_next_seq_for_append_sync` + `append_sync`; POSIX-only
  (`journal/__init__.py:9-15`).
- [Source: src/sdlc/contracts/journal_entry.py] — `JournalEntry` (free-`str` `kind`; non-null `after_hash`
  zero-sentinel; nullable `before_hash`).
- [Source: src/sdlc/cli/_adopted_targets.py:13-32] — `load_adopted_target_sources` (`{target: source}`) /
  `load_adopted_targets` (membership + source binding for the cli side).
- [Source: src/sdlc/engine/replan.py:17-40,43-83] — `resolve_scope_phase` (phase-N derivation, D),
  `compute_downstream` / `plan_invalidations` (downstream detection; `engine`-only → cli-reachable, NOT
  adopt-reachable, B).
- [Source: src/sdlc/cli/replan_cmd.py:27,141-192] — the realised invalidation orchestration to mirror for
  `--force` (`invalidate_record` + `signoff_invalidated` journal); deferred `from sdlc.engine.replan import ...`.
- [Source: src/sdlc/signoff/records.py:57,293,331-392] — `invalidate_record` (sets `invalidated_at`/
  `invalidated_reason`); phases {1,2} only (`_VALID_RECORD_PHASES`), phase 3 has no record.
- [Source: src/sdlc/signoff/states.py (via src/sdlc/engine/replan.py:15,80)] — `SignoffState.APPROVED` +
  `compute_state` = the "Story 2A.7 state machine" the AC references (C).
- [Source: docs/decisions/ADR-028-journal-kind-taxonomy.md:65-96,102-110,139-148] — §3 taxonomy + forward rule;
  newest adopt rows `symlink_accepted` (3.3), `imported_from_existing` (3.4); `signoff_invalidated` (2A.7+2A.19,
  :83) reused for `--force`. New `symlink_rolled_back` row required (E).
- [Source: scripts/module_boundary_table.py (adopt entry)] — `adopt.depends_on = {errors, contracts, ids,
  concurrency, state, journal, signoff, config}`; `adopt.forbidden_from = {engine, dispatcher, runtime}` (NO `cli`,
  NO `engine`) — B/D1/D4.
- [Source: pyproject.toml:248,294] — `--cov-fail-under=87` / `fail_under = 87` (operational floor, G).
- [Source: CONTRIBUTING.md:20-25] — quality gate (mypy --strict, coverage table-stated ≥90, wire-format snapshots,
  mkdocs --strict).
- [Source: docs/decisions/ADR-034 (POSIX-only)] — adopt POSIX-only; win32 `pytest.skip` (mirror
  `tests/integration/test_adopt_mode_invariant.py:19-20`).

## Dev Agent Record

### Context Reference

- Story drafted by `bmad-create-story` (2026-06-04) on `main` after Stories 3.3 + 3.4 were reviewed (`done`) and
  merged (`bc07c23`). Context extracted from epics.md, prd.md, epic-3-dag.md, ADR-024/028/034, CONTRIBUTING.md, and
  the frozen `adopt/`/`contracts/`/`journal/`/`signoff/`/`engine/`/`cli/` code on `main`. The headline cross-module
  fact (orphan-signoff detection lives in `engine/replan.py`, which `adopt/` is forbidden to import; the real
  invalidation seam is the `replan` pattern, NOT a non-existent `sdlc unsign`) was discovered during boundary
  analysis and recorded as binding corrections (B)/(C). The PRD §275/§321 / "John" citation drift and the
  `adopt/symlink.py` naming drift are recorded so the dev does not chase ghost references.

### Agent Model Used

Cursor Auto (Composer)

### Debug Log References

### Completion Notes List

- T0 locked D1–D6 option (a) in Change Log; rollback core in `adopt/rollback.py`, CLI in `adopt_rollback.py`, flat `adopt-rollback` command.
- Core + CLI tests TDD-first; ADR-028 `symlink_rolled_back` row alphabetised after `adopt_pass_started`.
- Orphan signoff fail-closed without `--force`; `--force` invalidates via `signoff.records` + `signoff_invalidated` journal.
### File List

- `src/sdlc/adopt/rollback.py` (new)
- `src/sdlc/cli/adopt_rollback.py` (new)
- `src/sdlc/cli/main.py` (adopt-rollback command)
- `tests/unit/adopt/test_rollback.py` (new)
- `tests/unit/cli/test_adopt_rollback.py` (new)
- `docs/decisions/ADR-028-journal-kind-taxonomy.md`
## Change Log

| Date | Change |
|---|---|
| 2026-06-04 | Story drafted (`bmad-create-story`). D1-D6 OPEN — to be ratified at dev-story T0 in this Change Log. |
| 2026-06-04 | T0 D1–D6 locked (option a each): D1 `adopt/rollback.py` + `cli/adopt_rollback.py`; D2 flat `adopt-rollback`; D3 bulk one summary journal + per-target payload; D4 replan/signoff seam + `--force`; D5 fail-soft reconcile + sidecar prune; D6 reuse `symlink_offer._write_manifest`. Implementation complete → review. |
