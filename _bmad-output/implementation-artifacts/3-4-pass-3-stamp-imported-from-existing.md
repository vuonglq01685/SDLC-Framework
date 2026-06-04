# Story 3.4: Pass 3 — Stamp `imported-from-existing` in Audit Log + Artifact Frontmatter

**Status:** done

**Epic:** 3 — Brownfield Adopt Mode (`sdlc init --adopt`)
**Layer:** 4 (`docs/sprints/epic-3-dag.md` §3 — third/last serial-spine pass; max-parallel 1)
**Worktree:** `epic-3/3-4-pass3-stamp` (owner: Winston, DAG §5 table)
**Critical Path:** 3.1 → 3.2 → 3.3 → **3.4** → 3.6 → 3.7 (DAG §4 — 3.4 is the terminal spine pass; 3.5 rolls back the stamps' symlinks, 3.6 re-runs idempotently stamping only NEW adoptions, 3.7 property/mutation-tests the whole module. Any slip here stalls 3.5/3.6/3.7 simultaneously.)
**Depends on (satisfied):** Story 3.3 (`done`, merged to `main`) — froze `adopted-symlinks.json` (the `AdoptedSymlinks{schema_version:1, mappings:[SymlinkMapping{source,target,accepted_at,kind}]}` 7th wire-format contract, `contracts/adopted_symlinks.py`), the `symlink_accepted` journal event (ADR-028 §3), and the `_append_symlink_event` / atomic-manifest / fail-soft per-artifact patterns this story mirrors. Story 3.1 (`done`) froze the `mark_imported(root, detected)` Pass-3 seam (`adopt/passes/stamp.py:16`, currently `return None`), the three-pass driver, and the `journal_path`/DI threading pattern.
**Parallel sibling (same layer):** none — Layer 4 is a single story (the adopt spine is serial; DAG §3/§6). This is the LAST spine story; Layer 5 (3.5 ‖ 3.6) and Layer 6 (3.7) unblock once 3.4 merges.

---

## Story

As a **maintainer wanting the audit chain to distinguish framework-native from imported artifacts**,
I want **Pass 3 (`mark_imported`) to read the `adopted-symlinks.json` manifest Pass 2 produced and, for every accepted symlink, (a) append an `imported_from_existing` journal event carrying `{source, target, marker: "imported-from-existing"}`, and (b) where the symlink target is a YAML-frontmatter-bearing format (`.md`), read that frontmatter and attach an EXTERNAL metadata record at `.claude/state/imported-metadata/<artifact-id>.yaml` — never editing the source file — so that downstream `/sdlc-verify` (Story 2A.10) is informed an artifact was imported and asks "is this still accurate?", and phase signoff (Story 2A.12 / 2A.7) hashes imported artifacts and distinguishes them from native ones in its summary**,
so that **future verification, signoff, and replan operations know which artifacts were imported (FR2 Pass 3, PRD §281), while the NFR-REL-6 source-untouched invariant continues to hold byte-for-byte**.

---

## Acceptance Criteria

> **Scope note — read first.** Story 3.4 fills the **Pass 3 stamp ONLY**, behind the `mark_imported(root, detected) -> None`
> seam Story 3.1 froze (`adopt/passes/stamp.py:16`, currently `return None`). It does **NOT** implement rollback
> (`sdlc adopt rollback`, Story 3.5), does **NOT** implement re-run idempotency / target-exists conflict resolution
> (Story 3.6 — 3.4 stamps whatever is in the manifest; recognising "already stamped on re-run" beyond a same-run no-op is
> 3.6), and does **NOT** own the source-untouched property/mutation gate (Story 3.7 — 3.4 must merely *be* correct). It
> consumes the frozen `adopted-symlinks.json` read-only.
>
> **Six material decisions — D1 (scope boundary: how much of the verify/signoff consuming side is in 3.4), D2
> (`imported-metadata` record status: internal-state model vs 8th wire-format contract), D3 (`<artifact-id>` derivation),
> D4 (journal payload shape + event-only vs content-hash), D5 (lenient frontmatter reader location/behaviour), D6
> (`mark_imported` seam signature) — are resolved at T0 in "Decisions Needed" before any code is written.** D1 gates how
> many ACs land in this story vs a follow-up, so settle it first.

> ### Binding ground-truth corrections (verified against `main`, 2026-06-04) — READ BEFORE CODING
>
> **(A) Pass 3 is MANIFEST-driven, not `detected[]`-driven.** Every AC keys off *"Given Pass 2 has produced
> `adopted-symlinks.json`"* (epics.md:1855). The authoritative input is the **`AdoptedSymlinks.mappings`** tuple
> (`source, target, accepted_at, kind`), read from `.claude/state/adopted-symlinks.json` — NOT the `detected[]` list the
> seam currently receives. `detected[]` may contain artifacts the user declined (`n`) in Pass 2; only *accepted* mappings
> are stamped. Read the manifest the same way Pass 2 does (`symlink_offer._load_existing_mappings` style:
> `AdoptedSymlinks.model_validate_json(path.read_text())`). The seam keeps `detected` for 3.1-ordering-test stability
> (D6) but the stamp loop iterates `mappings`.
>
> **(B) The Pass-3 seam does NOT currently receive `journal_path` — the driver must thread it (mirror 3.3).** The driver
> calls `stamp.mark_imported(root, detected)` at `driver.py:154` with no journal handle. Pass 3 must journal, so extend
> the seam + the `_run_pass(3, ...)` dispatch to forward `journal_path` (which `run_adopt` already holds and already
> passes to Pass 2), exactly as Story 3.3 extended Pass 2 (`driver.py:144-152`). Keep a no-op default so 3.1's
> orchestrator-ordering test + resume runs are unaffected.
>
> **(C) `/sdlc-verify` HARD-REJECTS adopted artifacts today (AC4 blocker — security-sensitive).**
> `cli/verify.py:_reject_symlink_ancestors()` (`verify.py:123-150`) walks **every** path component *including the leaf*
> and calls `emit_error("ERR_PATH_TRAVERSAL", …)` the moment any component `is_symlink()`. An adopted artifact lives at a
> canonical slot that IS a symlink (e.g. `02-Architecture/02-System/ARCHITECTURE.md → ../../docs/architecture-2024.md`),
> so verify aborts before `read_text()` is ever reached. **AC4 cannot pass without relaxing this guard** — and the guard
> is a deliberate path-traversal defence (P12). Any relaxation MUST stay safe: permit a leaf symlink ONLY when it is a
> known adopted target (present in `adopted-symlinks.json`), resolve it, and still escape-check (`compute_artifact_hash`
> already resolves+escape-checks symlinks safely — `signoff/hasher.py:41`). This change lives in `cli/` — **OUTSIDE the
> `adopt/` boundary** — so it is in-scope for 3.4 only if D1 = full-loop.
>
> **(D) Phase signoff SILENTLY SKIPS adopted artifacts today (AC5 blocker — zero-coverage, not partial).**
> `signoff/generator.py:_collect_artifacts()` hard-skips every symlink (`if p.is_symlink(): continue`, `generator.py:58`,
> added as path-traversal defence P12). Adopted artifacts (symlinks) are therefore **excluded from hashing, from the
> artifact count, and from the SIGNOFF.md table** — AC5's "imported artifacts ARE included in hash validation" is
> *zero-coverage* without a change. The clean fix: `generate_signoff_md` accepts a DI `adopted_targets: frozenset[str]`
> (repo-relative paths known-adopted from the manifest); symlinks in that set are resolved+hashed via the existing
> symlink-safe `compute_artifact_hash` (`hasher.py:25,41`), arbitrary symlinks still skipped (traversal defence
> preserved). `ArtifactRef` / `_SignoffMdDraftArtifact` are explicitly *non*-wire-format (`records.py:9`) so adding an
> `origin`/`imported` field carries NO ADR-024 ceremony. `signoff` IS in `adopt`'s `depends_on`, but `signoff` must NOT
> import `adopt` — pass the set IN from `cli/signoff.py`. The `cli/signoff.py` wiring is OUTSIDE the `adopt/` boundary →
> in-scope only if D1 = full-loop.
>
> **(E) `adopt/` CANNOT import `specialists/` — inline a lenient frontmatter reader.** The existing
> `specialists/frontmatter._split_frontmatter` (`frontmatter.py:67`) RAISES `SpecialistError` on a file without `---`
> delimiters, and `specialists` is NOT in `adopt`'s `depends_on` (`module_boundary_table.py:116-134`:
> `{errors, contracts, ids, concurrency, state, journal, signoff, config}`). AC2 needs an *optional* read that returns
> `None`/`{}` when an artifact has no frontmatter. Inline a tiny lenient `---`-split + `yaml.safe_load` reader inside
> `adopt/` (e.g. `adopt/passes/_frontmatter.py`); do NOT import `specialists`.
>
> **(F) The journal kind is a free `str` (no contract edit) but needs an ADR-028 §3 row.** `JournalEntry.kind` is bare
> `str` (`contracts/journal_entry.py`), so `imported_from_existing` adds NO wire-format snapshot churn — but ADR-028 §3
> is the canonical taxonomy (today its newest adopt row is `symlink_accepted`, `ADR-028:95`) and the forward rule
> (`ADR-028:101-110`) requires a §3 table row + Revision-Log entry in this PR. The `marker: "imported-from-existing"`
> value lives in the **payload**, not in a `kind`.

1. **Journal `imported_from_existing` per adopted symlink (PRODUCING — always in scope; AC: epics.md:1855-1857).**
   Given `.claude/state/adopted-symlinks.json` exists with N accepted mappings, when Pass 3 runs, for **each** mapping a
   journal entry is appended with `kind=imported_from_existing` and payload `{source: <original-path>, target:
   <canonical-path>, marker: "imported-from-existing"}` (D4), via the SYNC API (`allocate_next_seq_for_append_sync` +
   `append_sync`), event-only (`before_hash=None`, zero-sentinel `after_hash` per ADR-028 §2), `actor="cli"`,
   `target_id="adopt"` — mirroring `driver._append_event` / `symlink_offer._append_symlink_event`. An empty manifest
   (`mappings: []`) ⇒ Pass 3 is a clean no-op (no entries). ADR-028 §3 carries a new `imported_from_existing` row +
   Revision-Log entry (F).

2. **External frontmatter metadata record — source NEVER modified (PRODUCING — always in scope; AC: epics.md:1858-1859,
   NFR-REL-6).** For each accepted mapping whose symlink target is a YAML-frontmatter-bearing format (`.md`), Pass 3
   reads the target's frontmatter **leniently** (no frontmatter ⇒ `None`/empty, never an error — E/D5) and writes an
   EXTERNAL metadata record at `.claude/state/imported-metadata/<artifact-id>.yaml` (D2/D3) capturing at least
   `{source, target, kind, marker: "imported-from-existing", imported_at, frontmatter: <read block or null>}`. The
   record is written atomically (`atomic_write_bytes`) and pre-guarded by `assert_path_under_claude`; YAML is canonical
   (`yaml.safe_dump(sort_keys=True, default_flow_style=False, allow_unicode=True)` — the `signoff/records.py:205`
   Pattern-§3 convention). **The source artifact's bytes are byte-identical pre/post** — no frontmatter is ever written
   *into* the source; the marker lives only in the journal + the external record.

3. **Source untouched + boundary held (PRODUCING — always in scope; AC: NFR-REL-6, prd.md:290/739, architecture.md:1110).**
   Pass 3 writes ONLY under `.claude/` (the journal + `imported-metadata/*.yaml`). Every adopted source artifact (and the
   symlink target it points at) is byte-identical pre/post Pass 3 — verified by re-reading bytes in tests (the binding
   multi-fixture property/mutation gate is Story 3.7, not 3.4). `adopt/` imports contain no `cli`/`engine`/`dispatcher`/
   `runtime`/`specialists` (covered by `check_module_boundaries`; add a focused assertion on `stamp.py`).

4. **`/sdlc-verify` is informed of imported origin (CONSUMING — gated by D1; AC: epics.md:1861-1864, Story 2A.10).**
   Given an adopted artifact recorded as `imported-from-existing`, when the user later runs `/sdlc-verify <artifact>`:
   (i) verify no longer hard-rejects the adopted leaf symlink (the `_reject_symlink_ancestors` traversal guard is relaxed
   safely — leaf symlink permitted ONLY if it is a known adopted target, then resolved + escape-checked — C); and (ii)
   the verifier specialist is informed of the imported origin (the verify dispatch reads
   `.claude/state/imported-metadata/<artifact-id>.yaml` and injects an origin block into the verifier prompt /
   extra-context — `cli/_verify_dispatch.py:invoke_dispatch` + `dispatcher/prompts.py`), so the verifier's review
   explicitly addresses "is this imported content still accurate?". **If D1 = (b), AC4 moves to the deferred follow-up
   story and 3.4 ships only the producing-side record AC4 depends on.**

5. **Phase signoff includes + distinguishes imported artifacts (CONSUMING — gated by D1; AC: epics.md:1866-1869,
   Stories 2A.12/2A.7).** Given a phase signoff is generated on a project with imported (symlinked) artifacts, when
   signoff hashes are computed: imported artifacts ARE included in hash validation (the `_collect_artifacts` symlink-skip
   is lifted for known-adopted targets only — resolved + hashed via the symlink-safe `compute_artifact_hash`; drift
   detection then works equally for imported and native — D); **and** the SIGNOFF.md summary distinguishes imported vs
   native artifacts (an `origin`/`imported` field on the per-artifact record + render — `signoff/generator.py`
   `_render_signoff_md` + `records.py` `_SignoffMdDraftArtifact`, both non-wire-format). The known-adopted set is read
   from `adopted-symlinks.json` in `cli/signoff.py` and DI-passed into `generate_signoff_md`. **If D1 = (b), AC5 moves to
   the deferred follow-up story.**

6. **Quality gate green + TDD-first (AC: CONTRIBUTING §1-§2).** ruff format/check + `mypy --strict src/` + pytest +
   coverage (operational floor `--cov-fail-under=87`; ≥90 tracked as `EPIC-2B-DEBT-COVERAGE-90-FLOOR`) + pre-commit
   (incl. `check_module_boundaries`, `check_subprocess_allowlist`, `freeze_wireformat_snapshots --check` — **7/7 if D2 =
   internal-state (recommended); 8/8 if D2 = wire-format**) + mkdocs `--strict`. TDD-first (§2): tests-first RED commit
   before implementation, visible in `git log --reverse` (mirror the `test(3.3) RED → feat(3.3) GREEN` ordering).

---

## Tasks / Subtasks

- [x] **(AC6, §5) T0 — Resolve D1-D6 in the PR Change Log BEFORE writing code.** Lock D1 (scope boundary — gates how
  many ACs ship here), D2 (`imported-metadata` record status + model location), D3 (`<artifact-id>` derivation), D4
  (journal payload + event-only vs content-hash), D5 (lenient frontmatter reader), D6 (`mark_imported` seam signature).
  D1/D2 gate the file set + the snapshot count (7/7 vs 8/8), so settle them first.
- [x] **(AC1, AC2, AC3, §2) Write the failing Pass-3 unit tests FIRST, commit before implementation**
  (`tests/unit/adopt/test_stamp.py`):
  - manifest with 2 mappings → 2 `imported_from_existing` journal events with the exact payload (D4); empty manifest → no
    events (clean no-op); missing manifest → no events + (warn or silent per D-note).
  - a `.md` target with frontmatter → external record at `imported-metadata/<id>.yaml` capturing the read block; a `.md`
    target WITHOUT frontmatter → record with `frontmatter: null` (lenient, no error — E); a non-`.md` target (e.g.
    `Dockerfile`/`pom.xml`) → record with no frontmatter read.
  - **source-untouched:** after Pass 3, the source artifact bytes are byte-identical (assert sha256 before == after); only
    `.claude/` changed.
  - boundary: `stamp.py` imports contain no `cli`/`engine`/`dispatcher`/`runtime`/`specialists`.
- [x] **(AC1, AC2, AC3) Implement `mark_imported` (GREEN):** in `adopt/passes/stamp.py` — read the manifest (B/A), loop
  the accepted mappings, append the `imported_from_existing` event per mapping (reuse the `_append_event` event-only
  pattern; D4), lenient-read frontmatter (D5), write the external `imported-metadata/<id>.yaml` record (D2/D3) atomically
  pre-guarded by `assert_path_under_claude`. Keep ≤400 LOC (NFR-MAINT-3) — extract the frontmatter reader to
  `adopt/passes/_frontmatter.py` and (if D2 = model) the record model to its home. Fail-soft per mapping (mirror 3.3's
  `_create_for_record`): one bad target/read warns + continues, never aborts the pass.
- [x] **(AC1, B/D6) Thread `journal_path` into Pass 3 through the driver:** extend `stamp.mark_imported` signature (D6)
  + `driver._run_pass(3, …)` to forward `journal_path` (the driver already holds it and passes it to Pass 2); no-op
  default keeps 3.1's ordering test + resume unaffected. Update `tests/unit/adopt/test_driver.py` to assert the forwarded
  kwarg (do NOT let a `**_kw`-absorbing stub hide the wiring — the 3.3 review caught exactly this, CR3.3-P4).
- [x] **(ADR-028, F) Amend the journal taxonomy:** add an `imported_from_existing` row to ADR-028 §3 (alphabetised within
  the Story-3.4 source column) + a Revision-Log entry; payload `{source, target, marker}`.
- [x] **(D2, AC2) If D2 = wire-format (NOT recommended): full ADR-024 8th-contract ceremony** — new `ImportedMetadata`
  StrictModel, register as 8th in `_WIRE_FORMAT_REGISTRY` + `__all__`, `freeze_wireformat_snapshots --write` → snapshot,
  ADR-024 amendment row, confirm `--check` 8/8. **If D2 = internal-state (recommended): a plain validated model (or
  `StrictModel` NOT registered), no snapshot, no ADR-024 row** — document the rebuild-from-journal rationale in the
  module docstring (the record is a derived cache; the journal `imported_from_existing` events are the source of truth,
  mirroring 3.3's manifest-is-a-derived-cache stance).
- [x] **(AC4 — ONLY if D1 = full-loop) Verify consuming side (`cli/`, OUTSIDE adopt):**
  - relax `cli/verify.py:_reject_symlink_ancestors` to permit a leaf symlink that is a known adopted target (read from
    `adopted-symlinks.json`), then resolve + escape-check; arbitrary symlinks still rejected (C). **Write the
    security-regression test FIRST** (an arbitrary out-of-tree symlink at a slot still → `ERR_PATH_TRAVERSAL`; an adopted
    target symlink → allowed).
  - read the `imported-metadata/<id>.yaml` record in `cli/_verify_dispatch.py:invoke_dispatch` and inject an origin block
    into the verifier extra-context / prompt (`dispatcher/prompts.py`); the verifier review addresses "still accurate?".
  - optional: add an `imported_origin` field to the `artifact_verified` journal payload (`cli/_verify_post.py:219-229`).
- [x] **(AC5 — ONLY if D1 = full-loop) Signoff consuming side (`signoff/` + `cli/signoff.py`):**
  - add `adopted_targets: frozenset[str]` DI param to `generate_signoff_md`; in `_collect_artifacts` hash known-adopted
    symlinks via `compute_artifact_hash` (resolve + escape-check), skip arbitrary symlinks (D). **Security-regression test
    FIRST** (non-adopted symlink still skipped).
  - add an `origin`/`imported` field to `_SignoffMdDraftArtifact` + `ArtifactRef` (non-wire-format — no ceremony) and
    render the imported-vs-native distinction in `_render_signoff_md`.
  - wire `cli/signoff.py:run_signoff` to read `adopted-symlinks.json` and pass the set in.
- [x] **(AC6, §4) Chunked review** review-A (correctness / AC↔tests / manifest-driven fidelity / source-byte-identity) →
  review-B (boundary: no `adopt→cli`/`specialists`, lenient-frontmatter inlined, atomic write + path guard, fail-soft;
  **the verify/signoff traversal-guard relaxations are security-critical — verify the escape-check survives**) →
  review-C (ADR-028 row + D2 snapshot count 7/7-or-8/8 + `<artifact-id>` derivation correctness + payload exactness +
  naming). No skipping; review commits carry `[fresh-context-review]`, stage no `src/` (§4.4). → Runs in the
  `code-review` workflow once `dev-story` sets status=review.

---

## Dev Notes

### What 3.1 + 3.3 froze — the seam 3.4 fills

- **The seam (keep the public name):** `mark_imported(root: Path, detected: Sequence[DetectedArtifact]) -> None` at
  `adopt/passes/stamp.py:16` (Story-3.1 no-op). The driver dispatches Pass 3 at `driver.py:154`:
  `stamp.mark_imported(root, detected); return detected`. You MAY add a keyword-only `journal_path: Path | None = None`
  (no-op default) without breaking the 3.1 orchestrator-ordering test (D6). **The stamp loop reads
  `adopted-symlinks.json`, not `detected`** (A).
- **The input (frozen, read-only):** `AdoptedSymlinks.mappings: tuple[SymlinkMapping, ...]`, `SymlinkMapping{source: str,
  target: str, accepted_at: <RFC-3339 UTC>, kind: ArtifactKind}` (`contracts/adopted_symlinks.py:29-50`). Read via
  `AdoptedSymlinks.model_validate_json(path.read_text("utf-8"))` exactly like `symlink_offer._load_existing_mappings`
  (`symlink_offer.py:91-113`) — including the corrupt-manifest warn-don't-swallow stance.
- **The DI/threading pattern to mirror (Story 3.3):** the driver threads `journal_path` to Pass 2
  (`driver.py:144-152`); do the identical thing for Pass 3 (B/D6). `run_adopt` already constructs/holds `journal_path`.

### Reuse map (do NOT reinvent — verified file:line)

| Need | Reuse | Source |
|---|---|---|
| Append event-only journal entry | copy the `_append_event` shape (zero-sentinel `after_hash`, SYNC API) | `adopt/driver.py:48-62`; `symlink_offer.py:123-142` |
| SYNC journal API | `allocate_next_seq_for_append_sync(path)` + `append_sync(entry, journal_path=)` | `journal/writer.py:224,309`; re-exported `journal/__init__.py:10-15` |
| `JournalEntry` fields/constraints | `kind` is free `str`; `after_hash` non-null (zero-sentinel) | `contracts/journal_entry.py:15-42` |
| Read the manifest | `AdoptedSymlinks.model_validate_json(...)` + warn-on-corrupt | `symlink_offer.py:91-113`; `contracts/adopted_symlinks.py` |
| Atomic sidecar write | `atomic_write_bytes(path, content)` (POSIX-only; abs path) | `concurrency/io_primitives.py:157` |
| Stay-under-`.claude/` guard | `assert_path_under_claude(root, path)` (raises `AdoptError`) | `adopt/invariant.py:24` |
| RFC-3339 timestamp | `now_rfc3339_utc_ms()` | `ids/clock.py:13` |
| Canonical YAML write | `yaml.safe_dump(sort_keys=True, default_flow_style=False, allow_unicode=True)` (Pattern §3) | `signoff/records.py:205-213`; PyYAML is a runtime dep (`pyproject.toml:13`) |
| Symlink-safe hashing (AC5) | `compute_artifact_hash` resolves + escape-checks symlinks | `signoff/hasher.py:25,41` |
| Typed error envelope | `AdoptError` → `ERR_ADOPT` (exit 2); wrap `OSError`, don't leak tracebacks | `errors/base.py:19,68` |

### Frontmatter read — lenient, inlined, source-untouched (E/D5)

- `specialists/frontmatter._split_frontmatter` (`frontmatter.py:67`) RAISES on a file with no `---` delimiters AND lives
  in `specialists/`, which `adopt/` may NOT import. Inline a tiny reader in `adopt/passes/_frontmatter.py`: split on the
  first/second `---` line; if absent, return `None`; else `yaml.safe_load` the block (tolerate a non-dict → `None` +
  warn). The read is on the symlink TARGET (the source artifact) and is **read-only** — never write back.
- The marker is recorded EXTERNALLY (journal + `imported-metadata/*.yaml`); epics.md:1859 is explicit: *"source files are
  NOT modified — frontmatter changes happen only via metadata records, not by editing source content."* This is the whole
  point of NFR-REL-6.

### `.claude/state/imported-metadata/<artifact-id>.yaml` — new sidecar layout (D2/D3)

- No per-entity keyed-subdirectory sidecar precedent exists. Closest: `signoff/` uses fixed `phase-<N>.yaml`
  (`records.py:198`); adopt JSONs use fixed names. So `<artifact-id>` derivation is a genuine decision (D3).
- `<artifact-id>` must be derivable from the path `/sdlc-verify` is invoked with (the **canonical target** slot), so
  verify can locate the record. D3 options below.
- D2 status: the record is read back cross-invocation by verify → by the DAG-D1 logic that made the two JSONs wire-format,
  one could argue for a frozen contract. BUT ADR-024's registry comment says *"adding an 8th contract requires an ADR
  amendment + new snapshot"* and DAG Decision D1 enumerated wire-format treatment for ONLY `adopt-report.json` +
  `adopted-symlinks.json` + the journal kind + the frontmatter marker — it did NOT list `imported-metadata`. The record
  is also YAML (the snapshot harness is JSON) and is rebuildable from the journal events. Recommendation: internal-state
  validated model, NOT a frozen contract (D2(a)).

### Cross-story consuming side — scope boundary (D1) — the headline decision

Two ACs (AC4 verify, AC5 signoff) describe behaviour in modules **outside** the `adopt/` boundary, and BOTH have a
pre-existing blocker that silently/loudly excludes adopted (symlinked) artifacts:

- **Verify** (`cli/verify.py`, `cli/_verify_dispatch.py`, `dispatcher/prompts.py`): hard-rejects adopted symlinks
  (`ERR_PATH_TRAVERSAL`) before reading; no origin-injection seam. (C)
- **Signoff** (`signoff/generator.py`, `signoff/records.py`, `cli/signoff.py`): silently skips adopted symlinks from
  hashing + the summary. (D)

`adopt/` cannot import `cli`/`dispatcher`; the verify edits MUST live in `cli`/`dispatcher`. `signoff` IS an allowed
adopt dep, but the clean DI keeps `signoff` unaware of `adopt` (pass `adopted_targets` in from `cli/signoff.py`). So the
consuming side is a cross-module change. **The traversal-guard relaxations are security-sensitive** (they undo a
deliberate P12 path-traversal defence) and must preserve the escape-check (resolve + verify-under-root) and only ever
un-skip *known-adopted* targets. This is the crux of D1: full-loop (bigger, security-careful story) vs producing-only
(defer the consuming wiring to a `cli`/`signoff`-layer follow-up story, with a spec-deviation note moving AC4/AC5).

### Boundary, fail-soft, crash-consistency

- `adopt/` granted deps: `{errors, contracts, ids, concurrency, state, journal, signoff, config}` — NO `cli`/`engine`/
  `dispatcher`/`runtime`/`specialists` (`module_boundary_table.py:116-134`). No `print()` in `adopt/` — human warnings go
  through an injected `warn` callback (mirror 3.3's `WarnCallback`) or are journaled.
- Fail-soft per mapping (mirror 3.3's `_create_for_record`, `symlink_offer.py:186-211`): a bad frontmatter read /
  record-write OSError for one artifact warns + `continue`s, never aborting the whole pass. The driver already wraps any
  Pass exception into `AdoptError` → `cli/adopt.py` maps to the `ERR_ADOPT` envelope (exit 2).
- Crash-consistency: append the journal event BEFORE writing the metadata record (journal is the audit source of truth
  3.5/3.6 rebuild from; the `imported-metadata/*.yaml` is a derived cache). Full orphan-record reconciliation stays with
  Story 3.6 — note the residual gap in the module docstring (3.3 set this precedent).

### Citation-drift / reconciliation notes (verified)

- **`adopt/symlink.py` name** appears in `epic-3-dag.md:116/145/151` + the 3.7 mutation-target list, but Story 3.1/3.3
  froze the realised layout as `adopt/passes/*.py` (`symlink_offer.py`, `_symlink.py`). Keep new helpers under
  `adopt/passes/` (`stamp.py`, `_frontmatter.py`); note the rename so 3.7's mutation-target list is updated (same
  caveat 3.3 raised, D4).
- **`verifier_marker.py`** appears in the planning architecture tree (`architecture.md:874`) but the realised layout
  uses `adopt/passes/stamp.py` (`mark_imported`) per 3.1 (`stamp.py:1-6`, `architecture.md:1069`). Implement in
  `stamp.py`; do NOT create `verifier_marker.py`.
- **`confidence 0.92` / float** — N/A here (3.4 reads `kind`/`source`/`target` from the manifest, not confidence), but
  the same no-floats-in-`.claude/state/*` rule (`architecture.md:494-515`) applies to the YAML record.

### Previous-story intelligence (Story 3.3, done + merged)

- 3.3 landed `adopted-symlinks.json` + `symlink_accepted` + the `_append_symlink_event` / atomic-manifest / fail-soft /
  `WarnCallback` patterns 3.4 mirrors. Its code-review (CR3.3) carry-overs relevant to 3.4:
  - **CR3.3-P4:** driver-order unit tests that stub the pass with `lambda root, detected, **_kw` *absorb* the new kwargs
    and never assert the wiring — when you thread `journal_path` to Pass 3, **assert the forwarded kwarg** in
    `test_driver.py` (don't repeat the absorbed-kwarg gap).
  - **CR3.3-P3:** a corrupt prior manifest must WARN, not be silently swallowed (the "never silently swallow errors"
    rule). Apply the same to a corrupt/missing manifest in Pass 3.
  - 3.3 renamed the cli config reader `_load_legacy_code_globs → _load_project_config` and broadened its catch to
    `OSError`/`UnicodeDecodeError` (CR3.2-W3). If D1 = full-loop and `cli/signoff.py` reads `adopted-symlinks.json`, reuse
    a similarly-robust read.
  - adopt mode is POSIX-only (ADR-034) — all new test modules `pytest.skip` on win32 (see `test_symlink_offer.py`,
    `test_adopt_mode_invariant.py:19-20`).
  - The directory-style research slot is normalised by appending the source basename in Pass 2 (`resolve_target`); the
    `target` in the manifest is therefore already a concrete file path — `<artifact-id>` derivation (D3) keys off it.

### Project Structure Notes

- **New:** `src/sdlc/adopt/passes/_frontmatter.py` (lenient reader, E/D5); `tests/unit/adopt/test_stamp.py`; possibly
  `src/sdlc/contracts/imported_metadata.py` OR an `adopt/`-local model (D2); ADR-028 §3 row + Revision-Log; (only if
  D2 = wire-format) `tests/contract_snapshots/v1/imported_metadata.json` + ADR-024 row.
- **Edit (producing, always):** `src/sdlc/adopt/passes/stamp.py` (implement `mark_imported`); `src/sdlc/adopt/driver.py`
  (thread `journal_path` to Pass 3); `docs/decisions/ADR-028-journal-kind-taxonomy.md`; `tests/unit/adopt/test_driver.py`
  (assert forwarded kwarg).
- **Edit (consuming, ONLY if D1 = full-loop):** `src/sdlc/cli/verify.py` (relax leaf-symlink guard, security-careful);
  `src/sdlc/cli/_verify_dispatch.py` (read record + inject origin); `src/sdlc/dispatcher/prompts.py` (origin block);
  `src/sdlc/cli/_verify_post.py` (optional `imported_origin` payload); `src/sdlc/signoff/generator.py` (+`adopted_targets`
  DI, lift skip for adopted, render distinction); `src/sdlc/signoff/records.py` (`origin` field, non-wire-format);
  `src/sdlc/cli/signoff.py` (read manifest + pass set in); + their tests.
- **Do NOT edit:** `src/sdlc/contracts/adopt_report.py` + `adopted_symlinks.py` (FROZEN 6th/7th contracts) — consume
  read-only; the existing 7 snapshots; the journal/atomic primitives; `specialists/` (boundary).
- ≤400 LOC per file (NFR-MAINT-3); extract the frontmatter reader + (if any) the record model rather than bloating
  `stamp.py`.

### Testing standards

- pytest; AAA structure; coverage ≥90% target (operational ≥87 floor). TDD-first (§2): Pass-3 unit tests (+ ADR-028 row,
  + any contract test if D2 = wire-format) in a RED commit before the GREEN implementation (mirror `test(3.3) RED →
  feat(3.3) GREEN`). adopt mode POSIX-only (ADR-034) — module-level `pytest.skip` on win32.
- **Security tests are non-optional if D1 = full-loop:** verify must still reject an arbitrary out-of-tree symlink at a
  slot (`ERR_PATH_TRAVERSAL`); signoff must still skip a non-adopted symlink. Prove the traversal defence survives the
  relaxation.
- The binding multi-fixture source-untouched property/mutation CI gate is **Story 3.7**, not 3.4 — 3.4 needs correctness
  + unit coverage + a focused source-byte-identity assertion, not the corpus property test.

## Decisions Needed

> Resolve at T0 in the PR Change Log (CONTRIBUTING §5), mirroring Story 3.3's D1-D5 ratification. Recommended option
> first; the dev locks the choice before writing code. **D1 is the headline — it changes how many ACs ship in this story
> and may warrant a sprint-planning / DAG note if split.**

- **D1 — Scope boundary: how much of the verify (AC4) + signoff (AC5) consuming side lands in Story 3.4?**
  - **(a) [Recommended] Full loop in 3.4.** Implement the producing side (AC1-AC3, in `adopt/`) AND the minimal,
    security-preserving consuming edits (AC4 verify + AC5 signoff, in `cli`/`dispatcher`/`signoff`) so both epics.md ACs
    pass end-to-end. Rationale: epics.md places AC4/AC5 in Story 3.4; each edit lives in a module legally allowed to make
    it; the change is bounded (relax-for-known-adopted-only + an origin field). Cost: a larger story crossing 3 module
    boundaries + security-critical traversal-guard edits (mitigated by mandatory security-regression tests, review-B).
  - **(b) Producing side only; defer verify+signoff consuming to a follow-up.** Ship AC1-AC3 (journal + metadata record +
    source-untouched) in 3.4; move AC4 (verify) + AC5 (signoff) to a dedicated `cli`/`signoff`-layer follow-up story
    (new Layer-5+ story or fold into 3.6). Requires a spec-deviation ratification (the AC4/AC5 consuming clauses migrate)
    and a `correct-course` / DAG note. Lighter Layer-4 story, cleaner pass-layer discipline, isolates the security-
    sensitive verify/signoff changes from the spine.
  - **(c) Hybrid: producing + signoff (AC5) in 3.4; defer only verify (AC4).** AC5's signoff change is well-bounded and
    security-preservable (resolve+hash known-adopted only); AC4's verify change is the riskiest (security-critical
    preflight + novel prompt-origin-injection seam). Ship AC1-AC3 + AC5; defer AC4 to a `cli`-layer follow-up.
- **D2 — `imported-metadata/<artifact-id>.yaml` record status.**
  - **(a) [Recommended] Internal-state validated model, NOT a frozen wire-format contract.** A `pydantic` model (in
    `adopt/` or `contracts/` un-registered) for shape discipline; NO `_WIRE_FORMAT_REGISTRY` entry, NO JSON-Schema
    snapshot, snapshot count stays 7/7. Rationale: DAG Decision D1 scoped wire-format to the two JSONs + journal kind +
    frontmatter marker only; ADR-024's registry comment treats an 8th as a deliberate ceremony; the record is YAML +
    rebuildable from journal events (a derived cache).
  - (b) Promote to the 8th locked wire-format contract (StrictModel + JSON-Schema snapshot + ADR-024 amendment, count
    7→8). Heavier; verify reads it cross-invocation, but a YAML record doesn't fit the JSON snapshot harness cleanly.
- **D3 — `<artifact-id>` derivation for the sidecar filename** (must be derivable from the canonical target so verify can
  find it; filesystem-safe; collision-free; deterministic).
  - **(a) [Recommended] Deterministic slug of the repo-relative canonical target** (e.g. POSIX path with `/`→`__`,
    other unsafe chars escaped), with a length guard. Audit-readable; reversible-ish.
  - (b) `sha256(canonical_target_posix)[:16]` hex. Fixed-length + collision-safe, but opaque (a `target` field inside the
    record restores readability).
- **D4 — Journal payload shape + event-only vs content-hash.**
  - **(a) [Recommended] Event-only** (zero-sentinel `after_hash`, `before_hash=None`), payload `{source, target, marker:
    "imported-from-existing"}`, fresh `now_rfc3339_utc_ms()` `ts`. Mirrors `symlink_accepted`/`adopt_pass_*`; the stamp is
    a provenance marker, not a content write. Drift baseline is signoff's job (AC5).
  - (b) Content-hash `after_hash = sha256(imported artifact bytes)` to capture an import-time drift baseline. Heavier,
    overlaps signoff hashing, not what epics.md:1857 describes.
- **D5 — Lenient frontmatter reader.**
  - **(a) [Recommended] Inline a small lenient reader in `adopt/passes/_frontmatter.py`** (`---`-split + `yaml.safe_load`;
    no delimiters ⇒ `None`; non-dict ⇒ `None`+warn). Respects the boundary (no `specialists/` import).
  - (b) Add `specialists` to `adopt`'s `depends_on` and reuse `_split_frontmatter` with a try/except. Rejected: widens
    the adopt boundary for a 10-line helper; `_split_frontmatter` raises (wrong shape for optional read).
- **D6 — `mark_imported` seam signature.**
  - **(a) [Recommended]** `mark_imported(root: Path, detected: Sequence[DetectedArtifact], *, journal_path: Path | None =
    None) -> None` — keep `detected` for 3.1-ordering-test stability, add no-op-default `journal_path` (mirror 3.3's
    Pass-2 extension); read the manifest inside. Driver `driver.py:154` → `stamp.mark_imported(root, detected,
    journal_path=journal_path)`.
  - (b) Drop `detected` (manifest-only). Cleaner but churns the 3.1 ordering test + the `_run_pass` return contract — not
    worth it.

### References

- [Source: epics.md:1847-1869] — Story 3.4 ACs: journal stamp, external frontmatter metadata record, verify integration, signoff integration.
- [Source: epics.md:1857] — journal entry `kind=imported_from_existing, target, source, marker=imported-from-existing`.
- [Source: epics.md:1858-1859] — external metadata record at `.claude/state/imported-metadata/<artifact-id>.yaml`; source NOT modified.
- [Source: prd.md:290,296] — Journey 3 (Khanh): Pass 3 stamps every adopted artifact `imported-from-existing`; src/ identical to before.
- [Source: prd.md:739] — FR2 adopt mode; [Source: prd.md:211] — `imported-from-existing` verifier marking, source never modified.
- [Source: docs/sprints/epic-3-dag.md:50,98,116-117,145,199,206,214] — Layer 4, deps, serial-spine terminal pass, worktree owner (Winston), `imported_from_existing` extends ADR-028 forward rule.
- [Source: docs/decisions/ADR-028-journal-kind-taxonomy.md:65-99,101-110,146] — §3 taxonomy + forward rule; newest adopt row `symlink_accepted` (3.3).
- [Source: docs/decisions/ADR-024-wire-format-v1-lock.md:157-158] — 7 locked contracts; 8th requires ADR amendment + snapshot (D2).
- [Source: src/sdlc/adopt/passes/stamp.py:16] — the `mark_imported` seam to fill.
- [Source: src/sdlc/adopt/driver.py:48-62,144-155] — `_append_event` event-only pattern + Pass-2 `journal_path` threading to mirror for Pass 3.
- [Source: src/sdlc/adopt/passes/symlink_offer.py:91-142,186-211] — manifest read (`_load_existing_mappings`), `_append_symlink_event`, fail-soft `_create_for_record` patterns to mirror.
- [Source: src/sdlc/contracts/adopted_symlinks.py:29-50] — `AdoptedSymlinks`/`SymlinkMapping` (the read-only Pass-3 input).
- [Source: src/sdlc/contracts/journal_entry.py:15-42] — `JournalEntry` (free-str `kind`, non-null `after_hash` zero-sentinel).
- [Source: src/sdlc/journal/writer.py:224,309] — `allocate_next_seq_for_append_sync` + `append_sync` (SYNC API).
- [Source: src/sdlc/concurrency/io_primitives.py:157] — `atomic_write_bytes`; [Source: src/sdlc/adopt/invariant.py:24] — `assert_path_under_claude`; [Source: src/sdlc/ids/clock.py:13] — `now_rfc3339_utc_ms`.
- [Source: src/sdlc/signoff/records.py:205-213] — Pattern-§3 canonical `yaml.safe_dump`; [Source: src/sdlc/signoff/hasher.py:25,41] — symlink-safe `compute_artifact_hash` (AC5).
- [Source: src/sdlc/specialists/frontmatter.py:67] — `_split_frontmatter` (RAISES on absence; `specialists/` NOT importable by adopt — inline instead, E/D5).
- [Source: src/sdlc/cli/verify.py:123-150] — `_reject_symlink_ancestors` hard-rejects adopted leaf symlinks (AC4 blocker, C).
- [Source: src/sdlc/cli/_verify_dispatch.py + src/sdlc/dispatcher/prompts.py:209,266] — verifier prompt assembly (`idea_text`); origin-injection seam (AC4, D1=a).
- [Source: src/sdlc/signoff/generator.py:54-79,83] — `_collect_artifacts` symlink-skip (`:58`, AC5 blocker, D) + `_render_signoff_md` (distinction render).
- [Source: scripts/module_boundary_table.py:116-134] — `adopt` depends_on `{…signoff…}`, forbidden engine/dispatcher/runtime; `cli`/`specialists` not granted.
- [Source: pyproject.toml:13] — `pyyaml>=6,<7` runtime dep (no new dependency).
- [Source: docs/decisions/ADR-034 (POSIX-only)] — adopt POSIX-only; win32 `pytest.skip`.

## Dev Agent Record

### Context Reference

- Story drafted by `bmad-create-story` (2026-06-04) on `main` after Story 3.3 was reviewed (done) and merged. Context
  extracted from epics.md, prd.md, architecture.md, ADR-024/025/028/034, epic-3-dag.md, and the frozen `adopt/`/
  `contracts/`/`journal/`/`signoff/`/`cli/` code via parallel research agents (journal+YAML+frontmatter infra map; verify
  + signoff cross-story scope map). The two cross-story blockers (verify hard-reject + signoff silent-skip of adopted
  symlinks) were discovered during that analysis and are recorded as binding ground-truth corrections C/D.

### Agent Model Used

Composer (dev-story)

### Debug Log References

### Completion Notes List

- Implemented `mark_imported` manifest-driven loop: journal `imported_from_existing` + `imported-metadata/<slug>.yaml` sidecars (D2 internal-state).
- Threaded `journal_path`/`warn` through driver Pass 3; ADR-028 row added.
- AC4/AC5: verify allows known-adopted leaf symlinks (repo-root escape check); signoff hashes adopted symlinks with `origin` column; verify injects `<IMPORTED_ORIGIN>` block.
### File List

## Change Log

| Date | Change |
|---|---|
| 2026-06-04 | Story drafted (`bmad-create-story`). D1-D6 OPEN — to be ratified at dev-story T0 in this Change Log. |
| 2026-06-04 | dev-story T0: D1=(a) full loop, D2=(a) internal-state, D3=(a) target slug, D4=(a) event-only, D5=(a) inline frontmatter, D6=(a) journal_path kwarg. |
| 2026-06-04 | dev-story: Pass 3 stamp + verify/signoff consuming side; 119+ unit tests green. |
| 2026-06-04 | code-review (3 adversarial layers). Triage: 2 decision-needed, 11 patch, 8 defer, 6 dismissed. Findings below. |
| 2026-06-04 | code-review patches applied (12 = P0 from DN2 + 11). DN1→defer (CR3.4-W9), DN2→patch (P0 source-binding). Bonus fix: 3 pre-existing `test_verify_dispatch_errors` failures (dev-story 3.4 added required `idea_text` kwarg to `_run_dispatch_under_mock` but missed these direct callers) — caught by full-gate run, fixed. Gate GREEN: ruff format/check, mypy --strict 156 files, pytest 3136p/4s, coverage 88.59%≥87, wire-format 7/7, module-boundary + subprocess clean. Status review→done. |

## Review Findings

> code-review 2026-06-04 (bmad-code-review, 3 adversarial layers: Blind Hunter / Edge Case Hunter / Acceptance Auditor). D1 ratified as **(a) full-loop** (verify AC4 + signoff AC5 consuming edits shipped). Verdicts: AC1/AC2/AC3/AC5 MET; AC4 PARTIAL; AC6 PARTIAL (ruff format RED). Corrections (A)-(F) all MET; D2=(a) internal-state (snapshot 7/7), D3 slug, D6 seam confirmed.

**Decision-needed (RESOLVED 2026-06-04):**

- [x] [Review][Decision→Defer] AC4 verify-origin only functions for `01-Requirement/` artifacts — RESOLVED (a): accept Phase-1-only for v1. `sdlc verify` is Phase-1-only by design since Story 2A.10; multi-phase verify is a separate cross-cutting story, out of Layer-4 scope. Logged as CR3.4-W9 in deferred-work.md. `cli/verify.py:_resolve_artifact_path` hard-rejects any `artifact_id` whose `parts[0] != "01-Requirement"` before the leaf-symlink relaxation, so adopted artifacts at `02-Architecture/`/`03-Implementation/` never reach verify; AC4 is effectively Phase-1-only. — deferred, pre-existing 2A.10 constraint
- [x] [Review][Decision→Patch] Adopted-symlink relaxation does not bind the resolved target to the manifest `source` — RESOLVED (a): add defense-in-depth. `cli/verify.py:_assert_resolved_containment` + `signoff/generator.py:_collect_artifacts` authorize an adopted leaf symlink by manifest membership + under-repo-root escape-check but never verify it resolves to the recorded `source`; a repointed on-disk symlink / forged manifest target could make verify/signoff read/hash a different in-repo file. → promoted to **Patch P0** below (assert `resolved == (root/mapping.source).resolve()` for adopted targets in both surfaces).

**Patch (fixable without input):**

- [x] [Review][Patch] P0 (from DN2) — Bind resolved adopted symlink to manifest `source`: in `cli/verify.py:_assert_resolved_containment` and `signoff/generator.py:_collect_artifacts`, for a known-adopted target assert `resolved == (root/mapping.source).resolve()` (not merely under repo-root). Requires passing source→target mapping (not just the target set) into both surfaces. [src/sdlc/cli/verify.py:_assert_resolved_containment; src/sdlc/signoff/generator.py:_collect_artifacts; src/sdlc/cli/_adopted_targets.py]
- [x] [Review][Patch] BLOCKING — `ruff format --check` fails on `verify.py` (stray blank lines around new `_assert_resolved_containment`) [src/sdlc/cli/verify.py:158-160,193]
- [x] [Review][Patch] Path-traversal on frontmatter read + unconstrained record paths — `_write_metadata_record` reads `root / mapping.target` with NO containment check (only `record_path` is guarded); `ImportedMetadataRecord.source/target` are bare `str`. A `..`-bearing manifest `target` reads an arbitrary file whose bytes flow into the sidecar + verifier prompt. Validate `mapping.target`/`source` safe-repo-relative-under-root before reading; skip+warn if unsafe. Also closes the path-based prompt-injection vector. [src/sdlc/adopt/passes/stamp.py:65-67; src/sdlc/adopt/imported_metadata.py:38-39]
- [x] [Review][Patch] `sdlc verify` crashes with uncaught `UnicodeDecodeError` on an adopted non-UTF-8 `.md` — `_preflight_checks` `read_text` catches only `PermissionError`/`OSError`; `UnicodeDecodeError` (a `ValueError`) is newly reachable now that adopted leaf symlinks pass the guard. Add `except (UnicodeDecodeError, ValueError)` → `ERR_ARTIFACT_UNREADABLE`. [src/sdlc/cli/verify.py:330-345]
- [x] [Review][Patch] Signoff whole-phase abort on a forged/escaping adopted symlink — `_collect_artifacts` calls `compute_artifact_hash` (raises `SignoffError` on symlink-escape) unguarded for adopted targets → one bad entry aborts the entire signoff (non-adopted branch silently skips). Wrap per-adopted-artifact in try/except → skip+warn. [src/sdlc/signoff/generator.py:_collect_artifacts]
- [x] [Review][Patch] `read_metadata_record` silently returns `None` for both missing AND corrupt sidecars — a tampered sidecar silently downgrades verify to "native" (violates "never silently swallow"). Log a warning on corrupt/unreadable (distinct from missing). [src/sdlc/adopt/imported_metadata.py:62-71]
- [x] [Review][Patch] Journal `ts` and sidecar `imported_at` sampled from two separate `now()` calls — breaks Pass-2's single-timestamp cross-reference invariant. Sample once, pass into `_append_imported_event`. [src/sdlc/adopt/passes/stamp.py:45,108]
- [x] [Review][Patch] Missing test — fail-soft/warn path uncovered (the `warn` + OSError `continue` branches in stamp.py have no asserting test). [tests/unit/adopt/test_stamp.py]
- [x] [Review][Patch] Missing test — origin-injection (`<IMPORTED_ORIGIN>`) has zero coverage (the only AC4 test mocks `_invoke_dispatch`); a regression dropping the injection would not be caught. [tests/unit/cli/test_verify_adopted_symlink.py]
- [x] [Review][Patch] Missing test — missing-manifest case (empty-manifest covered; absent `adopted-symlinks.json` not). [tests/unit/adopt/test_stamp.py]
- [x] [Review][Patch] `test_non_adopted_symlink_still_skipped` uses an EMPTY allowlist — proves only the trivial baseline, not a populated `adopted_targets` + an unrelated `EVIL.md` symlink still skipped. [tests/unit/signoff/test_generator.py]
- [x] [Review][Patch] `test_unknown_symlink_still_rejected` weak assertion (`"symlink component" in out or "ERR_PATH_TRAVERSAL" in out`) — passes whether rejection came from the intended ancestor-guard or an unrelated path. Assert the specific guard. [tests/unit/cli/test_verify_adopted_symlink.py]

**Deferred (real, not actionable in this story):**

- [x] [Review][Defer] Crash between journal-append and sidecar-write leaves an orphan `imported_from_existing` event — full orphan reconciliation is Story 3.6's scope; add a residual-gap note to `stamp.py` docstring. [src/sdlc/adopt/passes/stamp.py:107-116] — deferred to 3.6
- [x] [Review][Defer] `artifact_id_for_target` slug (truncate at 200) can collide for over-long targets → sidecar overwrite; canonical slots are short. [src/sdlc/adopt/imported_metadata.py:25-32] — deferred, low likelihood
- [x] [Review][Defer] Known-adopted dangling/broken symlink silently omitted from `SIGNOFF.md` (broken link not `is_file`). [src/sdlc/signoff/generator.py:_collect_artifacts] — deferred, pre-existing
- [x] [Review][Defer] `stamp` OSError handling silent when `warn=None` (resume/ordering default); production always injects `warn`. [src/sdlc/adopt/passes/stamp.py:81-86,113-116] — deferred, acceptable fail-soft
- [x] [Review][Defer] Non-canonical adopted artifact id (`./`, `//`) over-rejected (fails safe; usability nit). [src/sdlc/cli/verify.py:137-156] — deferred, fails-safe
- [x] [Review][Defer] Empty-vs-missing manifest both → silent early return; could mask a Pass-2 persist failure. [src/sdlc/adopt/passes/stamp.py:103-105] — deferred, low
- [x] [Review][Defer] Signoff dir-symlink in manifest bypasses the `is_symlink` skip (saved by `is_file`); manifest never lists directories. [src/sdlc/signoff/generator.py:_collect_artifacts] — deferred, low
- [x] [Review][Defer] Duplicate manifest targets → double event + double sidecar (no `seen_targets` dedup unlike Pass 2); Pass 2 collapses dupes. [src/sdlc/adopt/passes/stamp.py:107] — deferred, low
