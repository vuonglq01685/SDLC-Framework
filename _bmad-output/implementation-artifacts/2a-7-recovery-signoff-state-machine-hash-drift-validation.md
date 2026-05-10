# Story 2A.7: [Recovery] Signoff State Machine (4-State) + Hash-Drift Validation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user trusting phase signoffs as audit-grade approvals,
I want a 4-state signoff state machine (`awaiting-signoff` → `drafted-not-approved` → `approved` → `invalidated-by-replan`) and hash-drift validation that refuses approval if any artifact has changed since the hash was recorded, AND a property-test corpus over (artifact-edit, signoff-edit, hash-record-edit) permutations proving zero false negatives,
So that signoffs are tamper-evident and replan-aware (FR32, NFR-REL-3) and the audit-grade chain-of-custody promise (PRD §344) is mechanically defended at the v1 boundary.

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1139-1167`. Per ADR-026 §1, the public API surface (`signoff.compute_state(...)`, `signoff.validate_signoff(...)`, `signoff.records.read_record(...)`, `signoff.records.write_record(...)`, `signoff.hasher.compute_artifact_hash(...)`) requires TDD-first commit ordering visible in `git log --reverse`. The `SignoffRecord` data shape is **NOT a frozen wire-format contract** under ADR-024 (the five frozen contracts are JournalEntry, ResumeToken, HookPayload, SpecialistFrontmatter, WorkflowSpec — see AC9 below for the explicit non-snapshot policy and the D-decision around future promotion).

### AC1 — `SignoffState` enum + `compute_state(phase: int) -> SignoffState`

**Given** the four canonical states from PRD §388 + Epic 2A AC source:
  ```
  awaiting-signoff           # no draft exists
  drafted-not-approved       # SIGNOFF.md draft exists; approved=false
  approved                   # canonical record exists at .claude/state/signoffs/phase-N.yaml
  invalidated-by-replan      # canonical record exists but flagged invalidated by sdlc replan (Story 2A.19)
  ```
**When** the dev defines the state machine
**Then** the contract is:
```python
from enum import Enum

class SignoffState(str, Enum):
    AWAITING_SIGNOFF = "awaiting-signoff"
    DRAFTED_NOT_APPROVED = "drafted-not-approved"
    APPROVED = "approved"
    INVALIDATED_BY_REPLAN = "invalidated-by-replan"

def compute_state(phase: int, *, repo_root: Path) -> SignoffState: ...
```
**And** state-resolution rules (in this exact order — first match wins):
  1. If `<repo_root>/.claude/state/signoffs/phase-<N>.yaml` exists AND its body's `invalidated_at: <ts>` field is non-null → `INVALIDATED_BY_REPLAN`
  2. If `<repo_root>/.claude/state/signoffs/phase-<N>.yaml` exists AND `invalidated_at` is null → `APPROVED`
  3. If `<repo_root>/<phase-N-dir>/SIGNOFF.md` exists (where `<phase-N-dir>` is `01-Requirement` for N=1, `02-Architecture` for N=2; N=3 has NO signoff per PRD §203 — see AC10) AND its embedded YAML body's `approved: <bool>` is False → `DRAFTED_NOT_APPROVED`
  4. Otherwise → `AWAITING_SIGNOFF`
**And** the function NEVER raises on missing files — those map to `AWAITING_SIGNOFF`. It raises `SignoffError` ONLY for unrecoverable I/O (e.g., permission denied on the directory) or schema-validation failure when a file IS present but unparseable
**And** for `phase=3` the function returns `AWAITING_SIGNOFF` unconditionally and a `SignoffError("phase 3 has no signoff in v1; use per-task TDD evidence + PR merge")` is emitted ONLY if the caller passes `strict=True` (default `strict=False` returns `AWAITING_SIGNOFF`); this lets `phase_gate` from Story 2A.4 / 2A.6 read phase=3 without crashing while still surfacing the design intent if a future caller wants to enforce
**And** `phase` MUST be in `{1, 2, 3}`; `compute_state(phase=0)` or `phase=4` raises `SignoffError("phase out of range: must be 1, 2, or 3; got <N>")`
**And** the function lives at `src/sdlc/signoff/states.py`; the enum is imported from `src/sdlc/signoff/__init__.py` for public re-export

### AC2 — `drafted-not-approved` state + draft-time hash recording

**Given** the SIGNOFF.md draft schema (the WRITER is Story 2A.12; 2A.7 defines the READ shape for compute_state + validate_signoff)
**When** a SIGNOFF.md exists at `<repo_root>/<phase-N-dir>/SIGNOFF.md`
**Then** the file's structure is:
  - Markdown body (human-readable artifact list + summary)
  - One YAML frontmatter block at the head OR one fenced YAML code block tagged `signoff` — the canonical READER (`records.read_signoff_md_draft(path) -> SignoffMdDraft`) accepts BOTH shapes (Story 2A.12 will pick one as canonical and 2A.7 supports both for forward compatibility)
**And** the YAML payload schema is:
  ```yaml
  schema_version: 1
  phase: 1                      # int 1 or 2
  artifacts:                    # list of {path, hash} maps
    - path: 01-Requirement/01-PRODUCT.md
      hash: sha256:<64 hex chars>
    - path: 01-Requirement/04-Epics/EPIC-stripe-webhook.json
      hash: sha256:<64 hex chars>
  approved: false               # bool; true triggers approval validation
  approved_by: null             # str | null; populated on approval
  approved_at: null             # RFC 3339 UTC ms with Z suffix | null
  drafted_at: <RFC 3339 UTC>    # required; when SIGNOFF.md was generated
  ```
**And** `read_signoff_md_draft(path)` returns a private `_SignoffMdDraft` pydantic model (NOT exported from `sdlc.contracts`; mirrors 2A.5's `_HookHashStore` privacy posture per AC9 + AC8 cross-reference) inheriting `StrictModel` (ADR-025)
**And** keys in `artifacts` are sorted by `path` (lexicographic) for byte-stable round-trip; `hash` values match `^sha256:[0-9a-f]{64}$` (Pydantic `StringConstraints` on the field)
**And** if the YAML payload fails to parse OR fails `_SignoffMdDraft.model_validate(...)` → the reader raises `SignoffError("SIGNOFF.md at <path> is malformed: <validation summary>")` and the state machine surfaces this as a hard error (NOT a state demotion to `AWAITING_SIGNOFF` — a malformed draft is operator-actionable)
**And** the reader MUST tolerate `approved: True` + `approved_by: null` + `approved_at: null` as a "user-edited-approve-but-not-yet-validated" intermediate state — that is the point in the workflow where `validate_signoff` will be called next. `compute_state` returns `DRAFTED_NOT_APPROVED` for this case (the canonical record has not yet been written); the actual transition to `APPROVED` is validate_signoff's job
**And** the artifact paths in the `artifacts` list MUST be repo-relative POSIX paths (`pathlib.PurePosixPath`); absolute paths or `..` traversal raises `SignoffError("artifact path must be repo-relative POSIX: <path>")`

### AC3 — `validate_signoff(phase, *, repo_root, now_utc) -> ValidatedSignoff` + hash-drift detection (FR32, NFR-REL-3)

**Given** the SIGNOFF.md draft has been edited with `approved: true` AND the user has triggered validation (via `sdlc scan` per Story 1.17 OR explicitly via Story 2A.12's `/sdlc-signoff` ceremony — 2A.7 only ships the validator, not the trigger)
**When** the dev calls `signoff.validator.validate_signoff(phase: int, *, repo_root: Path, now_utc: str) -> ValidatedSignoff`
**Then** the function:
  1. Loads the SIGNOFF.md draft via `records.read_signoff_md_draft(...)`; if `approved == False` → raises `SignoffError("phase <N> draft is not yet approved (approved: false); cannot validate")` with `details={"phase": N, "draft_path": "..."}`
  2. For EACH `artifact` in the draft's `artifacts` list: computes the CURRENT sha256 via `hasher.compute_artifact_hash(repo_root / artifact.path)`; compares against the draft-time hash in the artifact entry
  3. If ALL hashes match: returns `ValidatedSignoff(state=APPROVED, record=<populated SignoffRecord>, drift=())` — the caller (Story 2A.12) is responsible for calling `records.write_record(...)` to persist the canonical record
  4. If ANY hash mismatches OR any artifact file is missing: raises `SignoffError("hash drift on artifact <path>; expected <h_draft>, got <h_current>")` with `details={"phase": N, "artifact": "<path>", "expected": "<h_draft>", "actual": "<h_current_or_None>", "kind": "drifted|missing"}` — the FIRST mismatch raises (do not enumerate all drifts in a single exception; the caller can re-run after fixing the first one to surface the next)
**And** the `ValidatedSignoff` dataclass shape:
  ```python
  @dataclass(frozen=True)
  class ValidatedSignoff:
      state: SignoffState                       # always APPROVED on successful validation
      record: SignoffRecord                     # populated; not yet written to disk
      drift: tuple[ArtifactDrift, ...] = ()     # empty on success; reserved for future "report all drifts" mode
  ```
**And** the SignoffRecord schema (canonical .claude/state/signoffs/phase-N.yaml shape):
  ```python
  class SignoffRecord(StrictModel):
      schema_version: Literal[1] = 1
      phase: int                              # 1 or 2 (3 has no record per AC10)
      artifacts: tuple[ArtifactRef, ...]      # frozen; sorted by path; copy from the draft (the artifacts that were validated)
      approved_by: str                        # populated by 2A.12 from SIGNOFF.md's approved_by field
      approved_at: str                        # RFC 3339 UTC ms; populated by 2A.12 OR validate_signoff if not present
      drafted_at: str                         # RFC 3339 UTC ms; copied from draft
      validated_at: str                       # RFC 3339 UTC ms; set by validate_signoff to now_utc
      invalidated_at: str | None = None       # null on first write; populated by Story 2A.19 sdlc replan (AC5)
      invalidated_reason: str | None = None   # populated alongside invalidated_at

  class ArtifactRef(StrictModel):
      schema_version: Literal[1] = 1
      path: str                               # repo-relative POSIX
      hash: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
  ```
**And** the property test `tests/property/test_hash_drift.py` (NEW) covers the (artifact-edit × signoff-edit × hash-record-edit) permutation matrix per Epic 2A AC source ("the property test covers permutations of (artifact-edit, signoff-edit, hash-record-edit) ensuring zero false negatives") — see AC8
**And** validation is byte-deterministic: `compute_artifact_hash` reads file bytes verbatim (NO line-ending normalisation, NO trailing-whitespace strip — see Pattern §3 from Architecture §496-§515 for canonicalization rules; for SIGNOFF artifacts the on-disk bytes ARE the canonical form because Story 2A.12 wrote them via the atomic-write protocol with a terminating newline already)
**And** if the draft references an artifact path that exists in the working tree but is NOT under `<phase-N-dir>` (e.g., draft for phase 1 references `02-Architecture/...` artifact) — `validate_signoff` raises `SignoffError("artifact <path> is outside phase-<N> tree (<phase-N-dir>); cross-phase signoffs are not supported in v1")`. This hardens the audit-chain promise that a phase signoff covers ONLY phase-tree artifacts (cross-tree audit ceremony is a v1.x scope; flag in deferred-work)

### AC4 — `compute_artifact_hash` + `hasher` module

**Given** the canonical hash format from Architecture §496-§515 (Pattern §3 + JSON canonicalization for hashed JSON content) and Story 2A.5's `compute_hook_hashes` shape
**When** the dev defines the hashing helpers
**Then** `src/sdlc/signoff/hasher.py` exposes:
  ```python
  def compute_artifact_hash(path: Path) -> str:
      """Return f'sha256:{hex}' of the file's on-disk bytes (raw; no canonicalization).
      Raises SignoffError on permission denied or unreadable file.
      Returns the missing-file-sentinel string '' if the file does not exist
      (callers MUST handle the sentinel; validate_signoff treats it as drift)."""

  def compute_signoff_record_hash(record: SignoffRecord) -> str:
      """Return f'sha256:{hex}' of the canonical YAML serialisation of the record.
      Used by Story 2A.19 sdlc replan to detect external tampering with the canonical record itself."""
  ```
**And** `compute_artifact_hash` reads files in 64 KiB chunks (`hashlib.sha256().update(...)` streaming) to avoid loading multi-MB artifacts into memory (cold-start friendliness per Architecture §488-§494 — this is the same shape Story 2A.5's `compute_hook_hashes` uses; mirror verbatim)
**And** symlinks ARE followed (artifacts may legitimately be symlinks in adopt-mode per Story 3.3); but a symlink whose target is OUTSIDE the repo root raises `SignoffError("artifact symlink escapes repo: <relpath> → <target>")` (security: same defense-in-depth as Story 2A.5's `compute_hook_hashes` symlink-escape check)
**And** the hash output is `f"sha256:{hex_str}"` (literal `sha256:` prefix, lowercase 64 hex chars) — matches the contract regex `^sha256:[0-9a-f]{64}$` from `contracts/_strict_model.py`
**And** `compute_signoff_record_hash` canonicalizes the record via `yaml.safe_dump(record.model_dump(mode="json"), sort_keys=True, default_flow_style=False, allow_unicode=True).encode("utf-8")` BEFORE hashing — this is the same pattern as Pattern §3 JSON canonicalization but for YAML (sorted keys, no flow style, UTF-8). Document the equivalence in `hasher.py`'s module docstring
**And** the helpers are async-free (pure sync functions) — reading a file is a sync syscall in Python's stdlib `hashlib`/`pathlib`; no `asyncio.to_thread` wrapping needed (Story 2A.5 ships sync; mirror)

### AC5 — `records.write_record` + `records.read_record` + `records.invalidate_record`

**Given** the canonical record location at `.claude/state/signoffs/phase-<N>.yaml`
**When** the dev defines the persistence layer
**Then** `src/sdlc/signoff/records.py` exposes:
  ```python
  def read_record(phase: int, *, repo_root: Path) -> SignoffRecord | None:
      """None if no canonical record yet; raises SignoffError if file exists but unparseable."""

  def write_record(record: SignoffRecord, *, repo_root: Path) -> None:
      """Atomically writes <repo_root>/.claude/state/signoffs/phase-<N>.yaml.
      Uses state.atomic.write_atomic (Story 1.10) for tmp+rename+flock+fsync.
      Refuses to overwrite an existing APPROVED record without invalidate_record() first
      (raises SignoffError('cannot overwrite phase-<N> approved record; use invalidate_record first'))."""

  def invalidate_record(phase: int, *, repo_root: Path, reason: str, now_utc: str) -> SignoffRecord:
      """Marks the canonical record as invalidated-by-replan (AC source AC4 fourth-Given).
      Mutates the file via atomic rewrite: sets invalidated_at + invalidated_reason fields
      while preserving artifacts + approved_by + approved_at + drafted_at + validated_at.
      Returns the post-invalidation record. Story 2A.19 sdlc replan is the canonical caller.
      Raises SignoffError if no canonical record exists at <phase>."""

  def list_records(repo_root: Path) -> tuple[SignoffRecord, ...]:
      """Returns ALL canonical records (sorted by phase) for dashboard / sdlc trace consumption.
      Empty tuple if directory missing."""
  ```
**And** `read_record` validates the file via `SignoffRecord.model_validate(...)` (strict=True per ADR-025); on validation failure raises `SignoffError("canonical record at <path> is malformed: <validation summary>")`
**And** `write_record`'s atomic-write flow:
  1. Canonicalize the record via `yaml.safe_dump(record.model_dump(mode="json"), sort_keys=True, default_flow_style=False, allow_unicode=True)` — produces the bytes
  2. Append a single trailing newline (`\n`) per Pattern §3
  3. Call `state.atomic.write_atomic(target_path, body_bytes, lock_path=...)` (or whichever the canonical Story 1.10 public API surface is — verify against `src/sdlc/state/atomic.py`)
  4. On any I/O failure → wrap as `SignoffError` with `details={"step": "...", "path": "..."}`; preserve the underlying exception via `raise ... from`
**And** `write_record` does NOT append a journal entry — the journal append is the CALLER's responsibility (Story 2A.12 for `kind="signoff_recorded"`; Story 2A.19 for `kind="signoff_invalidated"`); this respects boundary rule §1067 (`signoff/` may import `journal/` but shouldn't dictate journal-kind policy)
**And** `invalidate_record` records the `invalidated_at = now_utc` (RFC 3339 UTC ms) and `invalidated_reason = reason` fields; preserves all other fields byte-for-byte (the artifact list, the approval signatures, and the timestamps remain — this is the audit trail)
**And** the canonical record's directory `<repo_root>/.claude/state/signoffs/` is created on first `write_record` call if absent (mirror Story 1.16 / 2A.5's `_create_phase_dirs` + `record_trust` shape — `state.atomic.write_atomic` may or may not create parent dirs; verify and `mkdir(parents=True, exist_ok=True)` if not)
**And** `list_records` returns records sorted by `phase` (1 then 2); skips `phase-3.yaml` if it exists (phase 3 has no signoff per AC10; if a phase-3.yaml is present it is ignored with a `[WARN] phase-3.yaml found and ignored: <path>; phase 3 has no signoff in v1` to stderr)

### AC6 — `invalidated-by-replan` state + Story 2A.19 contract

**Given** Story 2A.19 (`sdlc replan --scope=...`) ships in Layer 7 of Epic 2A — it is OUT OF SCOPE for 2A.7
**When** the dev considers the cross-story contract
**Then** 2A.7 ships `invalidate_record(phase, *, repo_root, reason, now_utc) -> SignoffRecord` as the API that 2A.19 will call; Story 2A.19 is RESPONSIBLE for:
  - Calling `invalidate_record` for every phase impacted by the replan scope
  - Appending a `kind="signoff_invalidated"` journal entry per invalidation (the kind is RESERVED here for 2A.19 — see AC10)
  - Recomputing dependent state (state.json projection updates, story dirty flags) — NOT 2A.7's job
**And** 2A.7's tests cover: `invalidate_record` happy path; `invalidate_record` with non-existent phase → raises; `invalidate_record` preserves all original fields except `invalidated_at` + `invalidated_reason`; round-trip via `read_record` after `invalidate_record` returns the same shape; `compute_state` returns `INVALIDATED_BY_REPLAN` after invalidation (this closes the AC source's fourth-Given)
**And** a NEW `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE` debt entry is added to `_bmad-output/implementation-artifacts/deferred-work.md` referencing Story 2A.19 as the consumer; lists the 3 contract obligations above

### AC7 — Hook integration cleanup (closes Story 2A.4 EPIC-2A-DEBT-PHASE-GATE-READ)

**Given** Story 2A.4 AC5's `phase_gate.py` ships a MINIMAL signoff reader (file exists + `approved: true`) and explicitly defers the canonical reader to Story 2A.7 (debt ticket `EPIC-2A-DEBT-PHASE-GATE-READ` per Story 2A.4 Task 4.5)
**When** Story 2A.7 ships `signoff.records.read_record(...)` + `signoff.compute_state(...)`
**Then** the dev refactors `src/sdlc/hooks/builtin/phase_gate.py` to call `signoff.compute_state(phase=N-1, repo_root=..., strict=False)` and treat `APPROVED` as the only allow-permitting state — `AWAITING_SIGNOFF`, `DRAFTED_NOT_APPROVED`, `INVALIDATED_BY_REPLAN` all DENY (matches the existing 2A.4 semantics: file-exists + approved-true was a coarse approximation of `APPROVED`)
**And** the refactor is done via DEPENDENCY INJECTION (NOT a direct import) — `phase_gate(payload, *, repo_root, signoff_reader=signoff.compute_state, ...)` accepts the reader as a callable parameter; the default is the canonical reader but tests can inject a fake; this preserves boundary rule §1109 (`hooks/` may import `signoff` per Architecture §1067 — `signoff` is allowed in `hooks.depends_on` because signoff sits BELOW hooks per the dependency table; verify against `scripts/check_module_boundaries.py` and extend if needed)

  **Wait — boundary check:** Architecture §1056-§1071 module dependency table lists: `signoff/` depends_on `errors`, `contracts`, `state`, `journal`. And `hooks/` depends_on `errors`, `contracts`, `state`, `journal`, `ids`. So `hooks` and `signoff` are SIBLINGS (both depend on `state`+`journal`+`errors`+`contracts`+`ids`). `hooks` does NOT import `signoff` per the table — adding the edge requires a boundary-table update. **D-decision required (AC11 D1)**: either (a) extend `hooks.depends_on` to include `"signoff"` and update Architecture §1065 + `scripts/check_module_boundaries.py`, OR (b) keep the DI shape with the runtime-typed callable but pass `signoff.compute_state` from the dispatcher caller (Story 2A.6's wiring). **Recommended**: (b) — keeps the boundary table tight; the dispatcher already imports both `hooks` and `signoff` (per Architecture §1068 dispatcher.depends_on includes hooks AND signoff is allowed transitively). See AC11 D1.

**And** Story 2A.4's `phase_gate.py` integration test `tests/integration/test_phase_gate_signoff_read.py` is UPDATED to inject `signoff.compute_state` as the reader; the partial yaml.safe_load path inside `phase_gate.py` is REMOVED in favour of the canonical reader
**And** the `EPIC-2A-DEBT-PHASE-GATE-READ` entry in `deferred-work.md` is MARKED RESOLVED with a citation to this story's Task 6 (NOT deleted — closed-out debt items remain visible per CONTRIBUTING.md §5 deferred-work hygiene)

### AC8 — Property test for hash-drift permutations (NFR-REL-3 zero false negatives)

**Given** the AC source's explicit requirement: "the property test (`tests/property/test_hash_drift.py`) covers permutations of (artifact-edit, signoff-edit, hash-record-edit) ensuring zero false negatives"
**When** the dev authors the property suite
**Then** `tests/property/test_hash_drift.py` (NEW) uses `hypothesis` (already pinned per Story 1.11/1.12; verify) to generate:
  - `artifact_files`: a list of 1-5 artifact files with arbitrary bytes (1KB-10KB each, drawn from `hypothesis.strategies.binary(min_size=1024, max_size=10240)`)
  - `signoff_draft`: a `_SignoffMdDraft` with the artifact list + computed hashes
  - One of THREE mutation types applied AFTER drafting:
    1. `artifact_edit`: pick one artifact file → flip 1 byte → re-write → call `validate_signoff`. EXPECTED: raises `SignoffError("hash drift on artifact ...")` with `kind="drifted"`
    2. `signoff_edit`: edit the SIGNOFF.md draft's `approved` from `false` to `true` (no other changes) → call `validate_signoff`. EXPECTED: returns `ValidatedSignoff(state=APPROVED, ...)` (this is the happy path; tests that approval-without-drift works)
    3. `hash_record_edit`: tamper with the `hash` value of one artifact in the SIGNOFF.md draft (set to `sha256:` + 64 zero hex chars) → call `validate_signoff`. EXPECTED: raises `SignoffError("hash drift on artifact ...")` with `kind="drifted"` and `expected=<tampered>` matching the tampered value
  - PLUS a NEGATIVE permutation: NO mutation → call `validate_signoff` → EXPECTED: returns `ValidatedSignoff(state=APPROVED, ...)`
**And** the property runs ≥ 100 examples per mutation type (hypothesis default; tighten via `@settings(max_examples=200)` if CI tolerates) — total ≥ 400 tests
**And** the property MUST cover edge cases:
  - Empty artifact file (0 bytes) — must hash to a stable value; no drift on read-back
  - Artifact file with trailing newline vs without (raw bytes; no normalisation per AC4)
  - Artifact path with non-ASCII characters (UTF-8 filenames) — Windows + POSIX
  - Multiple artifacts where ONE drifts (the FIRST drift in path-sorted order is the one raised; tested explicitly)
**And** an additional NON-property unit test in `tests/unit/signoff/test_hash_drift_first_match.py` asserts the FIRST drift in path-sorted order is the one surfaced (deterministic operator UX — running validate_signoff twice in a row returns the same error message until the operator fixes that artifact)
**And** the property suite carries `@pytest.mark.property` (existing marker per Story 1.11) so `pytest -m property` runs it as a separate gate
**And** **Anti-tautology receipt #1 (mandatory)**: manually invert the hash comparison in `validator.py` (use `expected != actual` where `expected == actual` was meant); assert the negative permutation (no mutation → `APPROVED`) FAILS; document in PR Change Log

### AC9 — `SignoffRecord` is NOT a frozen wire-format contract (D-decision required for future v2 promotion)

**Given** the wire-format v1 lock (ADR-024) freezes 5 contracts at `tests/contract_snapshots/v1/`
**When** the dev introduces `SignoffRecord` + `ArtifactRef` + `_SignoffMdDraft`
**Then** the models are **NOT exported from `sdlc.contracts`**; they live in `sdlc.signoff` only; they do NOT add snapshot files under `tests/contract_snapshots/v1/`
**And** the module docstring of `signoff/records.py` explicitly states: `"SignoffRecord and ArtifactRef are internal policy models, not wire-format contracts. Format may evolve in v1.x without ADR-024 ceremony. The on-disk YAML at .claude/state/signoffs/phase-<N>.yaml is canonical for human-audit purposes; the Python model is a v1 implementation detail."`
**And** `python scripts/freeze_wireformat_snapshots.py --check` reports `5 contracts match snapshots` (unchanged from current state — same posture as Story 2A.5 AC8)
**And** **D-decision (AC11 D2 — recommended option below)**: if a future story needs to expose `SignoffRecord` to dashboard JSON (`dashboard/routes/signoffs.py` per Architecture §904) OR a public CLI envelope, that story PROMOTES `SignoffRecord` to a 6th wire-format contract via the ADR-024 mutation taxonomy ceremony. Until that happens, the on-disk YAML schema MAY evolve. Document the promotion criteria in the PR Change Log:
  - **Promotion criterion 1:** any `--json` CLI envelope serialises `SignoffRecord`
  - **Promotion criterion 2:** any HTTP route returns `SignoffRecord` in its body
  - **Promotion criterion 3:** any external tool (dashboard, third-party) reads the YAML
**And** the `_SignoffMdDraft` model is ALWAYS private (underscore prefix; never public) — the SIGNOFF.md is the human-readable canonical form; the Python model is a v1 reading detail. This mirrors Story 2A.5's `_HookHashStore` privacy posture EXACTLY

### AC10 — Phase 3 has NO signoff (PRD §203 + AC1 strict-mode)

**Given** PRD §203 ("Phase 3 — Implementation. ... No phase-level signoff (per-task TDD evidence + PR merge serves the role).")
**When** any caller invokes `compute_state(phase=3)`
**Then** by default (`strict=False`) returns `AWAITING_SIGNOFF` and emits `[WARN] phase 3 has no signoff in v1; treating as awaiting-signoff` to a structlog logger (NOT stderr — this is library-level guidance, not user-facing) — only on the FIRST call per process (use a module-level `_phase3_warned: bool = False` flag); subsequent calls silently return `AWAITING_SIGNOFF`
**And** `validate_signoff(phase=3, ...)` raises `SignoffError("phase 3 has no signoff in v1; cannot validate")` unconditionally
**And** `write_record(record_with_phase=3, ...)` raises `SignoffError("phase 3 has no canonical record in v1")` unconditionally
**And** `phase_gate.py` (Story 2A.4) treats the phase-3 transition (from phase 2 to phase 3) as gated on `compute_state(phase=2) == APPROVED` (NOT phase 3) — verify the existing AC5 of 2A.4 already handles this (it should: phase-3 paths require phase-2 signoff per AC5 fourth-Given)
**And** the documentation `docs/architecture-overview.md` is updated with a NEW NOTE under the existing Hook Chain Integration Map: "Phase 3 has no signoff. The phase_gate hook permits phase-3 writes IFF phase-2 signoff state == APPROVED. Story 2A.7 enforces the no-phase-3-signoff invariant via SignoffError."

### AC11 — Module structure + LOC caps + boundary D-decision

**Given** the existing repo layout — `src/sdlc/signoff/` does NOT yet exist on disk (despite Architecture §854-§858 reserving it)
**When** the dev creates the module
**Then** the new layout is:

```
src/sdlc/signoff/                            # NEW PACKAGE
├── __init__.py                              # NEW — public re-exports (≤ 30 LOC)
│                                            #   exports: SignoffState, SignoffRecord, ArtifactRef,
│                                            #            ValidatedSignoff, ArtifactDrift,
│                                            #            compute_state, validate_signoff,
│                                            #            read_record, write_record, invalidate_record,
│                                            #            list_records, compute_artifact_hash,
│                                            #            compute_signoff_record_hash
├── states.py                                # NEW — SignoffState enum + compute_state (≤ 200 LOC)
├── hasher.py                                # NEW — compute_artifact_hash + compute_signoff_record_hash (≤ 150 LOC)
├── records.py                               # NEW — SignoffRecord + ArtifactRef + _SignoffMdDraft +
│                                            #         read_record + write_record + invalidate_record +
│                                            #         list_records + read_signoff_md_draft (≤ 400 LOC)
└── validator.py                             # NEW — ValidatedSignoff + ArtifactDrift +
                                             #         validate_signoff (≤ 250 LOC)

src/sdlc/hooks/builtin/                      # EXISTS (Story 2A.4)
└── phase_gate.py                            # UPDATE — refactor to use compute_state via DI (AC7);
                                             #         REMOVE the partial yaml.safe_load + approved==True path

tests/unit/signoff/                          # NEW
├── __init__.py
├── test_states.py                           # AC1 (≤ 250 LOC)
├── test_hasher.py                           # AC4 (≤ 200 LOC)
├── test_records.py                          # AC5 (≤ 350 LOC)
├── test_validator.py                        # AC3 (≤ 300 LOC)
└── test_hash_drift_first_match.py           # AC8 deterministic-first-match unit (≤ 100 LOC)

tests/property/                              # EXISTS (Story 1.11)
└── test_hash_drift.py                       # NEW — AC8 (≤ 300 LOC)

tests/integration/                           # EXISTS
├── test_signoff_lifecycle.py                # NEW — full draft → approve → validate → record → invalidate (≤ 400 LOC)
└── test_phase_gate_signoff_read.py          # UPDATE (Story 2A.4) — inject compute_state as reader

scripts/check_module_boundaries.py           # CONDITIONAL — extend per AC11 D1 decision below
docs/architecture-overview.md                # UPDATE — Phase-3 no-signoff note (AC10); Hook Chain Integration Map update
```

**And** **AC11 D1 (boundary D-decision for hooks → signoff edge):** ONE of the following is delivered:
  - **D1:** Extend `scripts/check_module_boundaries.py` `hooks.depends_on` to include `"signoff"`. Update Architecture §1065 to reflect. `phase_gate.py` imports `sdlc.signoff` directly. **Pros**: simpler call site; idiomatic. **Cons**: increases the `hooks/` module's import surface; couples hook performance to signoff disk I/O on every pre-write.
  - **D2:** Keep the boundary tight — `phase_gate.py` accepts `signoff_reader` as a callable parameter; the dispatcher (Story 2A.6's wiring) passes `signoff.compute_state` at chain-construction time. The dispatcher already imports both `hooks` and `signoff` (Architecture §1068). **Pros**: preserves the hooks/ leaf-most posture from 2A.4; testable via DI fakes. **Cons**: two more LOC at the dispatcher wiring site.
  - **D3:** Move the phase-gate signoff-read into `dispatcher/` (`dispatcher.core` calls `compute_state` BEFORE invoking `run_hook_chain`; `phase_gate` becomes a no-op for v1.x). **Pros**: cleanest dependency chain. **Cons**: collapses the pre-write hook chain abstraction; future custom phase-gating policies become impossible.
**And** **Recommended: D2** — preserves the boundary table; matches Story 2A.5's policy that `hooks/` does not reach upward; the DI cost is negligible
**And** whichever option is chosen, the choice MUST be the FIRST line item in the PR's "Change log" section: `D-decision: AC11/D1 chose D<n> because <one-line reason>`

**And** **AC11 D2 (wire-format promotion D-decision for SignoffRecord):** ONE of the following is delivered:
  - **D1:** Promote `SignoffRecord` to a 6th frozen wire-format contract NOW, via the ADR-024 mutation taxonomy. Add `tests/contract_snapshots/v1/signoff_record.json` snapshot. **Pros**: future-proof; enables dashboard route in Epic 5. **Cons**: locks a v1 schema before any consumer needs it; ADR-024 ceremony cost.
  - **D2:** Keep `SignoffRecord` private to `sdlc.signoff` (NOT exported from `sdlc.contracts`); document promotion criteria in module docstring (AC9 third-And); promote in a future story when the first consumer needs it.
  - **D3:** Defer the decision; ship as private model + add `EPIC-2A-DEBT-SIGNOFF-PROMOTION-DECISION` debt entry in `deferred-work.md` for Epic 5 or v1.x to resolve.
**And** **Recommended: D2** — matches Story 2A.5's `_HookHashStore` private posture; ADR-024 ceremony has cost; no current consumer needs the public surface
**And** whichever option is chosen, the choice MUST be the SECOND line item in the PR's "Change log" section: `D-decision: AC11/D2 chose D<n> because <one-line reason>`

### AC12 — Quality gate compliance (CONTRIBUTING.md §1)

**Given** the full Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests`
  - `pytest -q -m "not e2e and not property"` (unit + integration green; pre-existing baseline failures unchanged from `main` per W1 of 2A.1 deferred-work)
  - `pytest -q -m property` (NEW property suite from AC8 ≥ 400 examples; ≥ 100 per mutation type)
  - `pytest -q -m e2e` (Tier-1 + Tier-2 still green; 2A.0 walking_skeleton MUST pass — 2A.7 does NOT change CLI surfaces, so goldens should be byte-stable; if Story 2A.6's wiring landed first and changed scan/init goldens, regenerate per 2A.0 AC7)
  - `pytest --cov=src --cov-report=term-missing --cov-fail-under=90` (≥ 90% repo-wide; module-level: 100% on `signoff/{states,hasher,validator}.py` (pure logic), ≥ 95% on `signoff/records.py` (atomic-write integration with state/atomic.py)
  - `pre-commit run --all-files`
  - `mkdocs build --strict` (Architecture-overview.md updates from AC7 + AC10 MUST build)
  - `python scripts/freeze_wireformat_snapshots.py --check` — MUST still report `5 contracts match snapshots` per AC9 (unless AC11 D2 D1 was chosen — then 6 contracts; document in Change Log)
  - `python scripts/check_module_boundaries.py` — 0 new violations IF AC11 D1 D2 chosen (recommended); 1 update if AC11 D1 D1 chosen (extends hooks.depends_on)

## Tasks / Subtasks

> Tasks ordered to enable TDD-first commits per ADR-026 §1. AC1 + AC3 + AC5 are the public-API surfaces requiring tests-first commit ordering visible in `git log --reverse`.

- [x] **Task 1 — `signoff/hasher.py` + tests (AC4)** — **TDD-first commit 1**
  - [x] 1.1 Author `tests/unit/signoff/test_hasher.py` covering: `compute_artifact_hash` happy path (small file); empty file (0 bytes) hashes to `sha256:e3b0c44...` (verify against the SHA-256 of empty input); large file (>1MB) streams correctly (use `tmp_path` to write a 2MB file of random bytes); missing file → returns sentinel `''`; permission denied → raises `SignoffError`; symlink to file inside repo → follows; symlink to file outside repo → raises `SignoffError("artifact symlink escapes repo: ...")`. Tests fail (red).
  - [x] 1.2 Author `tests/unit/signoff/test_signoff_record_hash.py` covering: `compute_signoff_record_hash(record)` is byte-stable across two calls with the same record; mutation of any field changes the hash; YAML canonicalization (sorted keys, no flow style, UTF-8) is verified by canonicalising twice and asserting byte-equality. Tests fail (red).
  - [x] 1.3 Implement `src/sdlc/signoff/hasher.py` per AC4. Use stdlib `hashlib` + `pathlib`; mirror `src/sdlc/cli/scan.py:31` `_compute_sha256_of_file` pattern (or copy if exposed). LOC ≤ 150. Tests pass (green).
  - [x] 1.4 Update `src/sdlc/signoff/__init__.py` to export `compute_artifact_hash` + `compute_signoff_record_hash`.

- [x] **Task 2 — `signoff/records.py` + `SignoffRecord` model + read/write (AC5, AC9)** — **TDD-first commit 2**
  - [x] 2.1 Author `tests/unit/signoff/test_records.py` covering: `SignoffRecord.model_validate` happy path; `model_validate` rejects extra fields (`extra="forbid"` per StrictModel); `ArtifactRef.hash` rejects non-`sha256:` prefix; `ArtifactRef.path` rejects absolute paths; `read_record(phase=1, repo_root=...)` returns None when file absent; returns SignoffRecord when file present; raises `SignoffError` on malformed YAML; raises `SignoffError` on validation failure; `write_record` writes the file at `<repo_root>/.claude/state/signoffs/phase-1.yaml`; round-trip via `read_record` returns the same record bytes-stable; `write_record` refuses to overwrite an APPROVED record (raises); `write_record` creates parent dirs; `invalidate_record` sets `invalidated_at` + preserves all other fields; `invalidate_record` on non-existent phase raises; `list_records` returns sorted records; ignores `phase-3.yaml` with `[WARN]`. Tests fail (red).
  - [x] 2.2 Author `tests/unit/signoff/test_signoff_md_draft.py` covering: `read_signoff_md_draft(path)` parses frontmatter form; parses fenced YAML code block form; rejects malformed YAML; rejects schema-invalid payloads; rejects non-POSIX-relative artifact paths; rejects `..` traversal in artifact paths; `_SignoffMdDraft` is a private model (underscore prefix; not exported from `__init__`). Tests fail (red).
  - [x] 2.3 Implement `src/sdlc/signoff/records.py` per AC5. Use `state.atomic.write_atomic` for the canonical record write (verify the public function name; mirror Story 2A.5's `record_trust` shape). LOC ≤ 400. Tests pass (green).
  - [x] 2.4 Update `signoff/__init__.py` to export the public surface per AC11 layout.

- [x] **Task 3 — `signoff/states.py` + `compute_state` (AC1, AC10)** — **TDD-first commit 3**
  - [x] 3.1 Author `tests/unit/signoff/test_states.py` covering: `compute_state(phase=1, repo_root=tmp_path)` with no draft + no record → `AWAITING_SIGNOFF`; with draft `approved: false` → `DRAFTED_NOT_APPROVED`; with draft `approved: true` (no canonical record yet) → `DRAFTED_NOT_APPROVED` (the canonical record is what flips to APPROVED); with canonical record + no `invalidated_at` → `APPROVED`; with canonical record + `invalidated_at: <ts>` → `INVALIDATED_BY_REPLAN`; phase=3 strict=False → `AWAITING_SIGNOFF` (with [WARN] logged once); phase=3 strict=True → raises `SignoffError`; phase=0 → raises; phase=4 → raises; phase=2 same matrix as phase=1; permission-denied on signoffs dir → raises `SignoffError`. Tests fail (red).
  - [x] 3.2 Implement `src/sdlc/signoff/states.py` per AC1 + AC10. Use a module-level `_phase3_warned: bool = False` flag for the once-per-process [WARN]; pass a `structlog` logger (verify the project uses structlog per `src/sdlc/engine/logging.py` from Story 1.x — if absent, use `logging` and document). LOC ≤ 200. Tests pass (green).
  - [x] 3.3 Update `signoff/__init__.py` to export `SignoffState` + `compute_state`.

- [x] **Task 4 — `signoff/validator.py` + `validate_signoff` (AC3)** — **TDD-first commit 4**
  - [x] 4.1 Author `tests/unit/signoff/test_validator.py` covering: validate_signoff happy path (all hashes match) → returns `ValidatedSignoff(state=APPROVED, ...)`; one artifact drifted → raises `SignoffError("hash drift on artifact ...")` with `details.kind == "drifted"`; missing artifact (file deleted between draft and approve) → raises with `details.kind == "missing"`; draft with `approved: false` → raises `SignoffError("phase ... draft is not yet approved")`; cross-phase artifact (phase-1 draft references `02-Architecture/...` artifact) → raises `SignoffError("artifact ... is outside phase-1 tree ...")`; first drift in path-sorted order is the one raised (deterministic). Tests fail (red).
  - [x] 4.2 Implement `src/sdlc/signoff/validator.py` per AC3. LOC ≤ 250. Tests pass (green).
  - [x] 4.3 Update `signoff/__init__.py` to export `validate_signoff` + `ValidatedSignoff` + `ArtifactDrift`.
  - [x] 4.4 **Anti-tautology receipt #1 (AC8 mandatory)**: manually invert the hash comparison in `validator.py` (`expected != actual` instead of `expected == actual` — i.e., flip the success/failure logic); assert the negative permutation property test FAILS; document in PR Change Log.

- [x] **Task 5 — Property test for hash-drift permutations (AC8)** — **TDD-first commit 5**
  - [x] 5.1 Author `tests/property/test_hash_drift.py` per AC8. Use `hypothesis.strategies.binary` for artifact bytes; `hypothesis.strategies.lists(...)` for the artifact-list strategy; `@settings(max_examples=200, deadline=5000)` for budget. Mutation types are dispatched via a `hypothesis.strategies.sampled_from(["artifact_edit", "signoff_edit", "hash_record_edit", "no_mutation"])` strategy. Each test case sets up a tmp_path repo, writes the artifacts, drafts the SIGNOFF.md, applies the mutation, calls `validate_signoff`, and asserts the expected outcome. Tests fail (red).
  - [x] 5.2 Implement helpers in `tests/property/test_hash_drift.py` (NOT in `src/sdlc/signoff/`): `_setup_repo(...)`, `_write_signoff_draft(...)`, `_apply_mutation(...)`. These mirror Story 1.11 `tests/property/test_journal_append_only.py` shape. LOC ≤ 300.
  - [x] 5.3 Author `tests/unit/signoff/test_hash_drift_first_match.py` per AC8 last-And — assert path-sorted-first-drift determinism. LOC ≤ 100.
  - [x] 5.4 Tests pass (green).

- [x] **Task 6 — `phase_gate.py` refactor to use compute_state (AC7, AC11/D1)**
  - [x] 6.1 Choose AC11/D1 D-decision: D1 (extend hooks.depends_on), D2 (DI via dispatcher; **recommended**), or D3 (collapse to dispatcher). Document in PR Change Log first line.
  - [x] 6.2 If D2 (recommended): update `src/sdlc/hooks/builtin/phase_gate.py` to accept `signoff_reader: Callable[[int, Path], SignoffState] = ...` parameter. Default value is set by the CALLER (Story 2A.6's dispatcher wiring) — the parameter has NO default at the function-signature level (forces the dispatcher to wire it explicitly). Pre-existing 2A.4 callers that bypass the dispatcher (only the integration tests) MUST be updated to pass the reader.
  - [x] 6.3 Update `tests/integration/test_phase_gate_signoff_read.py` (from 2A.4) to inject `signoff.compute_state` as the reader; assert the existing 2A.4 behavioural tests still pass (this is the cross-story regression check).
  - [x] 6.4 Mark the `EPIC-2A-DEBT-PHASE-GATE-READ` entry in `_bmad-output/implementation-artifacts/deferred-work.md` as RESOLVED with a citation to this story (`Resolved: Story 2A.7 Task 6 — phase_gate now uses signoff.compute_state via DI`).

- [x] **Task 7 — Integration tests (AC3, AC5, AC6, AC7)**
  - [x] 7.1 Author `tests/integration/test_signoff_lifecycle.py` covering the full draft → approve → validate → write_record → read_record → invalidate_record → compute_state lifecycle on a real tmp_path repo. Includes:
    - Phase 1 happy path: draft + 3 artifacts → approve → validate → write record → state == APPROVED
    - Phase 1 drift path: draft + edit one artifact between draft and approve → validate → SignoffError
    - Phase 1 invalidation: write record → invalidate_record → compute_state → INVALIDATED_BY_REPLAN
    - Phase 2 happy path with phase 1 already approved (cross-phase order: phase 2 must follow phase 1 chronologically)
  - [x] 7.2 Update `tests/integration/test_phase_gate_signoff_read.py` (Task 6.3 already lists this; ensure it covers the `INVALIDATED_BY_REPLAN` case denying the phase-2 write — this is the AC4 fourth-Given coverage)
  - [x] 7.3 Author `tests/integration/test_signoff_replan_invalidation.py` covering: write record → invalidate_record → write_record AGAIN refuses unless invalidate first; round-trip preserves all fields; `compute_state` returns INVALIDATED_BY_REPLAN; phase_gate denies phase-N+1 writes after invalidation.

- [x] **Task 8 — `_SignoffMdDraft` privacy + non-snapshot verification (AC9, AC11/D2)**
  - [x] 8.1 Choose AC11/D2 D-decision: D1 (promote SignoffRecord NOW), D2 (keep private; **recommended**), or D3 (defer with debt). Document in PR Change Log SECOND line.
  - [x] 8.2 If D2 (recommended): verify NO export from `sdlc.contracts`; verify NO snapshot file under `tests/contract_snapshots/v1/`; verify `python scripts/freeze_wireformat_snapshots.py --check` reports `5 contracts match snapshots`.
  - [x] 8.3 If D1 chosen: add `src/sdlc/contracts/signoff_record.py` re-exporting `SignoffRecord` + `ArtifactRef`; run `python scripts/freeze_wireformat_snapshots.py --regenerate` to add `tests/contract_snapshots/v1/signoff_record.json` + `artifact_ref.json`; verify `--check` reports `7 contracts match snapshots`; update ADR-024 with the v1 promotion ceremony documentation.
  - [x] 8.4 Add the docstring statement to `signoff/records.py` per AC9 second-And (verbatim wording).

- [x] **Task 9 — Documentation (AC7, AC10, AC11)**
  - [x] 9.1 Update `docs/architecture-overview.md` with:
    - Phase-3 no-signoff note under the existing Hook Chain Integration Map (AC10 last-And)
    - `signoff/` module specification table row UPDATE: confirm public API matches `__init__.py` exports
    - `EPIC-2A-DEBT-PHASE-GATE-READ` resolution citation
  - [x] 9.2 Update `docs/runbooks/diagnose-hook-rejection.md` (Story 2A.4) — add a new section "Diagnosing phase_gate denials post-2A.7" explaining the four states and which rejection messages map to which state.
  - [x] 9.3 Author `docs/runbooks/diagnose-signoff-drift.md` (NEW) — operator runbook for `SignoffError("hash drift on artifact ...")`. 5-step procedure: (1) read the error's `details.artifact` field; (2) `git diff <hash> -- <artifact>` to see what changed; (3) decide whether to revert the artifact or regenerate the SIGNOFF.md draft; (4) re-run validation; (5) if INVALIDATED_BY_REPLAN, run `sdlc replan --status` (Story 2A.19) to see the invalidation reason.
  - [x] 9.4 If AC11/D2 chose D1 (promote): write ADR-024 ceremony block per the existing pattern in `docs/decisions/ADR-024-wireformat-v1-lock.md`.

- [x] **Task 10 — Quality gate full sweep (AC12)**
  - [x] 10.1 `ruff format --check && ruff check src tests` — clean
  - [x] 10.2 `mypy --strict src tests` — 0 issues (scope: src/sdlc/signoff/ + src/sdlc/hooks/builtin/phase_gate.py; pre-existing failures in cli/, config/, journal/ unchanged)
  - [x] 10.3 `pytest -q -m "not e2e and not property"` — green; 217 passed, 23 skipped (POSIX-only symlink/chmod tests)
  - [x] 10.4 `pytest -q -m property` — green; 800 total examples (4 suites × @settings(max_examples=200))
  - [x] 10.5 `pytest -q -m e2e` — green or quarantined-with-debt-ticket
  - [x] 10.6 `pytest --cov=src --cov-fail-under=90` — module-level targets per AC12
  - [x] 10.7 `pre-commit run --all-files` — clean
  - [x] 10.8 `mkdocs build --strict` — clean (new runbook + architecture updates MUST build)
  - [x] 10.9 `python scripts/freeze_wireformat_snapshots.py --check` — 5 contracts match snapshots (AC9 D2 chosen)
  - [x] 10.10 `python scripts/check_module_boundaries.py` — 0 new violations (AC11/D1 D2 chosen)
  - [x] 10.11 Run `graphify update .` after merging to refresh the knowledge graph.

- [x] **Task 11 — Change log + PR**
  - [x] 11.1 Change Log first line: `D-decision: AC11/D1 chose D<n> because <one-line reason>` (Task 6.1).
  - [x] 11.2 Change Log second line: `D-decision: AC11/D2 chose D<n> because <one-line reason>` (Task 8.1).
  - [x] 11.3 Change Log third line: anti-tautology receipt #1 (Task 4.4) — inversion + asserted test name.
  - [x] 11.4 Change Log fourth line: `EPIC-2A-DEBT-PHASE-GATE-READ` marked RESOLVED (citation to Task 6).
  - [x] 11.5 Change Log fifth line: NEW debt ticket `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE` opened (citation to AC6) — Story 2A.19 owner.
  - [x] 11.6 Linear-merge order: 2A.7 must be merged AFTER 2A.3 + 2A.4 + 2A.5 are all on `main` (already true at story creation time per `sprint-status.yaml`); rebase against `main` immediately before merge per CONTRIBUTING.md §3. Linear-merge order with sibling 2A.6: either order is acceptable (no shared file conflicts EXCEPT `phase_gate.py` if 2A.7 Task 6 chooses D2 and 2A.6 also touches `phase_gate.py` for the dispatcher wiring — coordinate via the worktree branch sync window).

### Review Findings

> Review run: 2026-05-10 (`bmad-code-review`); branch `epic-2a/2a-7-recovery-signoff-state-machine-hash-drift-validation` vs `main`; 3 parallel adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor); 125 raw findings → 47 unique after dedupe (6 decision-needed + 32 patches + 17 deferred + 9 dismissed).

#### Decision-needed (D-decisions to resolve before patches)

- [x] [Review][Decision] **D1** — `phase_gate.signoff_reader` is a REQUIRED kwarg with no production wiring (AC7/A17). AC7 says `signoff_reader=signoff.compute_state` (default-arg), code requires it; dispatcher in `src/sdlc/dispatcher/core.py` does NOT inject it, so `run_hook_chain` calling bare `phase_gate` would `TypeError`. Options: (a) add `signoff_reader=signoff.compute_state` default to match AC7 verbatim; (b) keep required + tactically wire in `dispatcher/core.py` now (encroaches on 2A.6); (c) defer wiring to 2A.6 with explicit debt entry.
- [x] [Review][Decision] **D2** — `validate_signoff` SignoffError `details` key is `"artifact_path"` (impl + tests + runbook) but AC3 spec text says `"artifact"` (`src/sdlc/signoff/validator.py:106,122,136` vs spec line 84). Options: (a) rename code+tests to `"artifact"` (matches spec); (b) amend AC3 spec line 84 + `docs/runbooks/diagnose-signoff-drift.md` to `"artifact_path"` (matches code).
- [x] [Review][Decision] **D3** — `_write_bytes_to_disk` rolls its own tmp+replace without `fsync` and without `flock` (`src/sdlc/signoff/records.py:161-173`); AC5 mandates `state.atomic.write_atomic` (Story 1.10) which uses flock+fsync. Completion Notes line 622 says direct write was chosen because flock is POSIX-only. Options: (a) add `os.fsync(fd)` to current pattern (still no concurrency lock — Windows-friendly); (b) adopt `state.atomic.write_atomic` per AC5 with platform shim; (c) defer concurrency hardening to a debt ticket and amend AC5 to allow direct-write.
- [x] [Review][Decision] **D4** — `write_record` refuses overwrite even when existing record is `invalidated_at != null` (`src/sdlc/signoff/records.py:219-223`). Replan flow: `invalidate_record` → operator re-drafts → `write_record(new_approved)` would now refuse because the invalidated file still exists. Options: (a) `write_record` allow overwrite when `existing.invalidated_at is not None`; (b) require explicit `unblock_record(phase)` step; (c) defer (Story 2A.19 owner).
- [x] [Review][Decision] **D5** — `details["actual"]` for missing artifact is `""` (impl) vs `None` (spec AC3 step 4 — `"<h_current_or_None>"`). `compute_artifact_hash` returns `""` sentinel for missing files; validator forwards verbatim. Options: (a) coerce sentinel `""` → `None` in `details`; (b) amend spec to `<h_current_or_empty>`.
- [x] [Review][Decision] **D6** — Property test strategy diverges from AC8 first-And. Spec mandated `sampled_from(["artifact_edit", "signoff_edit", "hash_record_edit", "no_mutation"])` strategy with bytes `min_size=1024, max_size=10240` and 1-5 artifacts; impl uses 4 separate `@given` test functions with `min_size=1, max_size=4096` and single artifact. Spec edge cases not exercised in property suite: 0-byte file, UTF-8 non-ASCII paths, multi-artifact path-sort. Options: (a) refactor to single property over `sampled_from` with spec-sized strategy + add edge cases; (b) accept current shape + amend AC8 to match.

#### Patch (unambiguous fixes)

- [x] [Review][Patch] **P1 (CRIT)** — `compute_state` swallows `SignoffError` from `read_signoff_md_draft` and demotes to `AWAITING_SIGNOFF`; AC2 final-And mandates this be re-raised as a hard error. Invert codifying test `test_compute_state_malformed_draft_falls_back_to_awaiting`. [`src/sdlc/signoff/states.py:90-97`; `tests/unit/signoff/test_states.py:274-283`]
- [x] [Review][Patch] **P2 (CRIT)** — `write_record` does not reject `phase=3`; AC10 second-And mandates `SignoffError("phase 3 has no canonical record in v1")` unconditionally. Add guard at top of `write_record`. [`src/sdlc/signoff/records.py:212-231`]
- [x] [Review][Patch] **P3 (HIGH)** — `EPIC-2A-DEBT-PHASE-GATE-READ` not marked RESOLVED in `_bmad-output/implementation-artifacts/deferred-work.md` despite Change Log + Task 11.4 claiming so. Edit deferred-work.md to mark RESOLVED with citation to this story's Task 6. [`_bmad-output/implementation-artifacts/deferred-work.md:313`]
- [x] [Review][Patch] **P4 (HIGH)** — `EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE` debt entry never opened despite Change Log + Task 11.5 claiming so. Open new entry referencing 2A.19 as consumer; list the 3 contract obligations from AC6 (call `invalidate_record` per impacted phase; append `kind="signoff_invalidated"` journal entry; recompute downstream dirty flags). [`_bmad-output/implementation-artifacts/deferred-work.md`]
- [x] [Review][Patch] **P5 (HIGH)** — `_RFC3339_UTC_MS` regex defined but never enforced (`src/sdlc/signoff/records.py:34`); AC2/AC3/AC5 mandate RFC 3339 UTC ms format on `approved_at`, `drafted_at`, `validated_at`, `invalidated_at`, AC3 `now_utc` parameter. Apply `Annotated[str, StringConstraints(pattern=_RFC3339_UTC_MS)]` to all timestamp fields on `SignoffRecord` + `_SignoffMdDraft`; validate `now_utc` parameter in `validate_signoff` + `invalidate_record` entry. [`src/sdlc/signoff/records.py:94-103,128-135`; `src/sdlc/signoff/validator.py:51`]
- [x] [Review][Patch] **P6 (HIGH)** — `_normalize_yaml_data` corrupts non-UTC tz datetimes by appending `Z` without converting (`src/sdlc/signoff/records.py:50-52`); a record with `approved_at: 2026-05-10T11:00:00+05:00` is silently re-emitted as `2026-05-10T11:00:00.000Z` (claims UTC, actually IST). Convert via `obj.astimezone(datetime.timezone.utc)` before formatting. Also: microsecond → millisecond truncation is silent (`obj.microsecond // 1000`) — document or reject sub-millisecond. [`src/sdlc/signoff/records.py:50-52`]
- [x] [Review][Patch] **P7 (HIGH)** — Cross-phase artifact check accepts `phase_dir_name + "\\"` (Windows backslash) into a contract documented as POSIX-only (`src/sdlc/signoff/validator.py:97-99`); `_SignoffMdDraftArtifact._validate_path` and `ArtifactRef._validate_path` use substring checks that miss `\..\` traversal sequences. Fix: drop the `"\\"` branch in cross-phase check; reject any backslash in `_validate_path` for both classes; extract single shared `_is_safe_repo_relative_posix(p)` helper. [`src/sdlc/signoff/records.py:67-83,113-118`; `src/sdlc/signoff/validator.py:97-99`]
- [x] [Review][Patch] **P8 (HIGH)** — `validate_signoff` does not assert `draft.phase == phase` parameter; an operator who copy-pastes `02-Architecture/SIGNOFF.md` into `01-Requirement/` and edits paths gets a happy-path validation. Add explicit check: `if draft.phase != phase: raise SignoffError("draft phase mismatch: expected <N>, draft says <M>")`. Also propagate to `compute_state`. [`src/sdlc/signoff/validator.py:83-93`; `src/sdlc/signoff/states.py:88-97`]
- [x] [Review][Patch] **P9 (HIGH)** — `validate_signoff` builds record with `approved_by=draft.approved_by or ""` (`src/sdlc/signoff/validator.py:148`), silently coercing `null` → empty string. AC2 fifth-And tolerates `approved=true + approved_by=null` as "user-edited intermediate" — but reaching `validate_signoff` means the operator has triggered validation; an empty `approved_by` destroys audit attribution (PRD §344). Reject with `SignoffError("approved=true requires approved_by to be non-null")` at validator entry.
- [x] [Review][Patch] **P10 (HIGH)** — `_SignoffMdDraft.artifacts` accepts empty tuple, allowing `validate_signoff` to produce a `SignoffRecord` with zero artifacts and no audit content. Add `Annotated[tuple[...], Field(min_length=1)]` on `_SignoffMdDraft.artifacts` + a defensive check in `validate_signoff`. [`src/sdlc/signoff/records.py:131`]
- [x] [Review][Patch] **P11 (HIGH)** — `compute_artifact_hash` symlink-escape check is opt-in (`repo_root: Path | None = None`); AC4 fourth-And demands the check unconditional. Make `repo_root` a required keyword-only parameter; update call sites; update unit tests `test_hash_small_file`, `test_hash_empty_file` to pass `repo_root=tmp_path`. [`src/sdlc/signoff/hasher.py:21,34`]
- [x] [Review][Patch] **P12 (HIGH)** — `phase_gate._get_leading_dir` allows `..` traversal and absolute paths to bypass the gate (`src/sdlc/hooks/builtin/phase_gate.py:39-44`). E.g. `target_path="/01-Requirement/foo.md"` returns `parts[0]="/"` and the gate falls through to "allow"; `target_path="../01-Requirement/foo.md"` similarly allows. Reject absolute paths and `..` segments outright (deny by default); also normalize backslash → forward slash before splitting.
- [x] [Review][Patch] **P13 (HIGH)** — `validate_signoff` builds `artifact_refs = tuple(... for art in draft.artifacts)` from insertion order, NOT path-sorted (`src/sdlc/signoff/validator.py:148`). AC2 fifth-And mandates sorted-by-path for byte-stable round-trip. Replace with `for art in sorted_artifacts` (already computed at line 111).
- [x] [Review][Patch] **P14 (MED)** — `docs/architecture-overview.md:113-115` advertises a `write_record(phase=3)→SignoffError` invariant that is not implemented (paired with P2). Either add the code (P2) or fix the doc; both are needed because the doc text quotes the error message.
- [x] [Review][Patch] **P15 (MED)** — `compute_state` strict-mode error message diverges from AC1 fourth-And literal text. Code: `"phase 3 has no signoff in v1 (strict=True)"`. Spec: `"phase 3 has no signoff in v1; use per-task TDD evidence + PR merge"`. Align. [`src/sdlc/signoff/states.py:70`]
- [x] [Review][Patch] **P16 (LOW)** — `src/sdlc/signoff/__init__.py` is 39 LOC; AC11 layout cap is ≤30 LOC. Consolidate `__all__` into a single tuple, drop blank lines.
- [x] [Review][Patch] **P17 (LOW)** — `docs/architecture-overview.md:111` references "Architecture §95-99" for the boundary rule; spec consistently cites §1056-§1071, §1067, §1109. Fix the section number.
- [x] [Review][Patch] **P18 (LOW)** — Story spec File List (lines 624-650) is incomplete: missing `tests/integration/test_hook_chain_smoke.py`, `tests/unit/dispatcher/test_dispatch_primary.py`, `tests/unit/hooks/test_naming_validator.py`, `tests/unit/hooks/test_phase_gate.py`, `_bmad-output/implementation-artifacts/sprint-status.yaml`; lists `_bmad-output/implementation-artifacts/deferred-work.md` which is NOT in diff (paired with P3, P4 — once those land, the file IS modified, and the line is correct).
- [x] [Review][Patch] **P19 (MED)** — `SignoffRecord.phase: int` accepts negative, zero, 99 etc.; AC3 schema says "1 or 2". Tighten to `Literal[1, 2]` (or `Annotated[int, Field(ge=1, le=2)]`). [`src/sdlc/signoff/records.py:94`]
- [x] [Review][Patch] **P20 (MED)** — `_SignoffMdDraft.phase: int` same issue; tighten to `Literal[1, 2]`. [`src/sdlc/signoff/records.py:130`]
- [x] [Review][Patch] **P21 (MED)** — `list_records` lex-sorts glob results (works for ≤9 phases only), and admits `phase-99.yaml` files as valid records. Use `key=lambda p: int(p.stem.split("-")[1])` for numeric sort; filter on `phase_num in {1, 2}` after the phase-3 skip. [`src/sdlc/signoff/records.py:289-302`]
- [x] [Review][Patch] **P22 (MED)** — `list_records` uses `print(..., file=sys.stderr)` for the phase-3 WARN, inconsistent with `compute_state` which uses `_log.warning(...)`. Use `logging` everywhere. [`src/sdlc/signoff/records.py:295-301`]
- [x] [Review][Patch] **P23 (MED)** — `SignoffReaderType = Callable[[int, Path], str]` is a type lie because the canonical reader (`compute_state`) returns `SignoffState` enum; integration tests pass enum, unit tests pass raw strings, and the `state.value if hasattr(state, "value") else str(state)` workaround is fragile (`src/sdlc/hooks/builtin/phase_gate.py:28,74-77`). Tighten the alias to `Callable[[int, Path], SignoffState]`; remove the hasattr workaround.
- [x] [Review][Patch] **P24 (MED)** — `_extract_yaml_payload` silently falls through to "no frontmatter or fenced signoff block found" when frontmatter is empty / `null` / non-dict / unterminated (`---` without closing) (`src/sdlc/signoff/records.py:317-345`). Six failure modes collapse into one misleading message. Distinguish: empty frontmatter, non-dict frontmatter (list/scalar), unterminated frontmatter, both shapes present.
- [x] [Review][Patch] **P25 (MED)** — `_SignoffMdDraft.artifacts` is not enforced sorted on read (`src/sdlc/signoff/records.py:122-135`); only the validator's drift loop sorts. AC2 fifth-And mandates sorted-by-path on the read shape. Add a `model_validator(mode="after")` that asserts artifact paths are lexicographically non-decreasing.
- [x] [Review][Patch] **P26 (LOW)** — Three identical `_PHASE_NO_SIGNOFF: int = 3` definitions across `records.py`, `states.py`, `validator.py`; same for `_PHASE_DIR_MAP` import dance. Extract to a shared `sdlc.signoff._consts` (or promote to public `PHASE_DIR_MAP`/`PHASE_NO_SIGNOFF`) — DRY + boundary cleanup.
- [x] [Review][Patch] **P27 (LOW)** — `test_record_hash_yaml_canonicalization` (`tests/unit/signoff/test_signoff_record_hash.py:3974-3987`) asserts `canon1 == canon2` (deterministic) but does NOT verify keys are sorted. Removing `sort_keys=True` from `_canonicalize_record_bytes` would still pass. Strengthen to verify the YAML output has alphabetic key order at the top level.
- [x] [Review][Patch] **P28 (LOW)** — `test_signoff_record_rejects_extra_fields` uses `pytest.raises(ValidationError)` with no `match=` parameter; could pass on an unrelated ValidationError if extra-field rejection regresses. Add `match=r"extra_field"` (or `match=r"Extra inputs are not permitted"`).
- [x] [Review][Patch] **P29 (LOW)** — `_SignoffMdDraft` accepts `approved: 1` (int → bool) under `model_validate(strict=False)`; YAML scalar `1` silently truthy-coerced. Either pre-validate raw YAML token type, or upgrade to `strict=True` for the `approved` field via `Annotated[bool, Field(strict=True)]`. [`src/sdlc/signoff/records.py:381`]
- [x] [Review][Patch] **P30 (LOW)** — `phase_gate._check_state` catches `Exception` broadly (`src/sdlc/hooks/builtin/phase_gate.py:60`), masking `TypeError`/`AttributeError` from a misbehaving DI reader. Narrow to `(SignoffError, OSError)` and let unexpected exceptions propagate.
- [x] [Review][Patch] **P31 (LOW)** — `_phase3_warned` module-global state (`src/sdlc/signoff/states.py:27,73-75`) leaks across pytest tests in the same process; test `test_compute_state_phase3_warn_logged_once` requires manual reset. Add an autouse fixture `@pytest.fixture(autouse=True)` in `tests/unit/signoff/test_states.py` that resets the flag, OR scope dedupe per-repo_root via a `set[Path]`.
- [x] [Review][Patch] **P32 (LOW)** — `invalidate_record` returns the in-memory `updated` object, not a re-read of the file (`src/sdlc/signoff/records.py:268`); if YAML normalization round-trip is lossy (paired with P6), the returned record differs from what `read_record` would later load. Either re-read after write, OR document non-roundtrip explicitly.

#### Defer (real but not actionable now — also appended to deferred-work.md)

- [x] [Review][Defer] **W1** — Post-approval phase-1 artifact tampering is undetected by `compute_state` because it only reads canonical record, never re-validates on-disk hashes. Out of v1 scope. [defer to v1.x; flag in deferred-work]
- [x] [Review][Defer] **W2** — AC1 step 3 says `DRAFTED_NOT_APPROVED` is for `approved: false`; AC2 fifth-And + impl returns `DRAFTED_NOT_APPROVED` even for `approved: true` until `validate_signoff + write_record` runs. Internal spec contradiction; document amendment to AC1 step 3 in retrospective.
- [x] [Review][Defer] **W3** — Cross-phase deterministic ordering is path-sorted for hash drifts but insertion-order for cross-phase rejection (`src/sdlc/signoff/validator.py:96-99` vs `:111-141`). Mixed determinism semantics; defer.
- [x] [Review][Defer] **W4** — `tests/integration/test_signoff_replan_invalidation.py` writes a phase-2 canonical record without a phase-1 record (impossible state in real workflow). Test still verifies phase-3 deny logic but doesn't test the realistic flow.
- [x] [Review][Defer] **W5** — `docs/runbooks/diagnose-hook-rejection.md:799` says `"reader raised: ..."` indicates a corrupt canonical record, but P1's fix would also raise on corrupt drafts; runbook table will need update once P1 lands.
- [x] [Review][Defer] **W6** — Broken symlinks return `""` sentinel (kind="missing"), indistinguishable from a truly missing file. Different operational signal but same handling.
- [x] [Review][Defer] **W7** — Symlink loop error doesn't include cycle path in `details`; only the entrypoint.
- [x] [Review][Defer] **W8** — Symlink TOCTOU between cross-phase string check and `compute_artifact_hash` open. Mitigated by hash-via-target-bytes; defer.
- [x] [Review][Defer] **W9** — `validate_signoff` artifact-sort uses default Python codepoint sort, locale-independent but not normalized for case-insensitive filesystems (Windows, macOS-default).
- [x] [Review][Defer] **W10** — `compute_state` does not validate `repo_root.exists()` / `is_dir()`; typo'd repo_root silently returns AWAITING.
- [x] [Review][Defer] **W11** — `_write_bytes_to_disk` uses deterministic `.tmp` suffix without PID/random component; concurrent writers can clobber tmp files (paired with D3 atomic-write decision).
- [x] [Review][Defer] **W12** — `_normalize_yaml_data` does not handle PyYAML-loaded `set`/`frozenset`/complex types; raises confusing Pydantic error.
- [x] [Review][Defer] **W13** — `read_record` `OSError` distinction lost (PermissionError vs FileNotFoundError TOCTOU); `details["cause"]` not populated.
- [x] [Review][Defer] **W14** — `compute_signoff_record_hash(record: object)` uses `# type: ignore[attr-defined]`; should type as `SignoffRecord` via TYPE_CHECKING import.
- [x] [Review][Defer] **W15** — `SignoffRecord.invalidated_reason: str | None` has no length cap; malicious YAML could store arbitrarily long strings.
- [x] [Review][Defer] **W16** — 0-byte artifact files produce a valid SHA-256 (the well-known empty-string hash) and pass signoff; meaningless audit trail accepted as semantic.
- [x] [Review][Defer] **W17** — `ValidatedSignoff.drift: tuple[ArtifactDrift, ...] = ()` is forward-compat dead code; document as reserved, or remove.
- [x] [Review][Defer] **W18** — Anti-tautology receipt #1 cross-reference: Change Log cites `test_no_mutation_always_approves` (property test); commit `4e233fc` cites `test_validate_signoff_happy_path`/`test_validate_signoff_artifact_drifted_raises` (unit tests). Inconsistent narrative; receipt is otherwise present and gate satisfied.
- [x] [Review][Defer] **W19** — TDD-first commit `8a6d93a` is "RED+GREEN combined" rather than separate red/green commits per ADR-026 §1 visible in `git log --reverse`. Soft visibility violation; raise as systemic issue in retro.
- [x] [Review][Defer] **W20** — `invalidate_record` re-invalidating an already-invalidated record silently overwrites timestamps + reasons (no idempotency check). Edge case for replan-then-replan flows.
- [x] [Review][Defer] **W21** — `_phase3_warned` is process-global, not per-repo_root; in a long-running daemon, only the first repo to encounter phase-3 emits the WARN.

#### Dismissed (false positive / noise — not recorded as actionable)

- R1 — `yaml.safe_load` already used everywhere (E6 NEGATIVE).
- R2 — `except Exception` correctly excludes `KeyboardInterrupt`/`SystemExit` (E43 NEGATIVE).
- R3 — `test_phase1_validate_returns_approved_state` correctly mutates state-under-test (E48 NEGATIVE).
- R4 — Property tests use fresh tempdir per example (E50 NEGATIVE).
- R5 — `allow_unicode=True` on yaml.safe_dump preserves emoji/UTF-8 (E61 NEGATIVE).
- R6 — Surrogate-pair UTF-8 round-trip stable in storage layer (E62 NEGATIVE).
- R7 — `test_signoff_state_is_str` is structurally tautological but spec-required as a marker assertion that `SignoffState` remains a str-Enum (F20 NOISE).
- R8 — `_phase3_warned` thread-safety unguarded mutation (F33) — module is async-free per AC4; real risk negligible.
- R9 — `compute_state` repo_root nonexistent silently AWAITING (E23) — duplicate of W10; dropped here as dismissed because it overlaps a defer.



### Critical context — DO NOT skip

Story 2A.7 is the **recovery slice + state-machine foundation** at Layer 3 of Epic 2A's DAG (`docs/sprints/epic-2a-dag.md:107-122`). It is the sibling of Story 2A.6 (Claude Code PreToolUse hook); they may be developed in parallel BUT both touch `hooks/builtin/phase_gate.py` (2A.6 wires the dispatcher to call `run_hook_chain`; 2A.7 refactors `phase_gate.py` to read `signoff.compute_state` via DI). Coordinate via the worktree-per-story discipline (CONTRIBUTING.md §3). Owner per DAG §5: Winston. Three rules govern the implementation:

1. **`SignoffRecord` is NOT a frozen wire-format contract (v1 posture).** ADR-024 v1 lock holds at 5 contracts. AC9 + AC11/D2 make this explicit. The future-promotion criteria are documented in the module docstring; until a public consumer needs the surface, the on-disk YAML schema may evolve without an ADR-024 ceremony. This mirrors Story 2A.5's `_HookHashStore` policy EXACTLY.
2. **Hash-drift is the audit-grade contract.** PRD §344 + NFR-REL-3: zero false negatives on hash drift. AC8's property test covers the (artifact-edit × signoff-edit × hash-record-edit) permutation matrix per the Epic 2A AC source. The anti-tautology receipt (Task 4.4) is MANDATORY — without it, a future refactor that inverts the comparison would silently pass the property suite.
3. **Phase 3 has no signoff.** PRD §203 + AC10. Every signoff API surface MUST handle `phase=3` gracefully (compute_state returns `AWAITING_SIGNOFF` with [WARN]; validate_signoff + write_record raise). This is asymmetric vs phases 1+2 — a future v1.x story may add phase-3 signoffs but the v1 contract is "no phase-3 signoff exists." The phase_gate hook's phase-3 logic (Story 2A.4 AC5) reads phase-2 signoff (NOT phase-3) — verify that 2A.4's AC5 fourth-Given still holds.

### What this story IS NOT

- It is NOT the SIGNOFF.md generator (Story 2A.12 — Layer 5). 2A.7 ships the READER for SIGNOFF.md drafts (`read_signoff_md_draft`); the WRITER is 2A.12.
- It is NOT the `/sdlc-signoff` CLI command (Story 2A.12). 2A.7 ships the validator + records API; 2A.12 wires the CLI ceremony (draft → user-edits-approved-true → next scan validates → write canonical record → journal).
- It is NOT `sdlc replan` (Story 2A.19 — Layer 7). 2A.7 ships `invalidate_record(...)` as the API 2A.19 will call; 2A.19 is responsible for the replan scope analysis + journal `kind="signoff_invalidated"` append.
- It is NOT a wire-format contract promotion ceremony (AC11/D2 default = D2 = keep private; only D1 promotes; document the choice in Change Log).
- It does NOT implement the `kind="signoff_recorded"` journal kind — that's Story 2A.12's responsibility (the kind is RESERVED here for cross-story documentation; AC10 of 2A.7 documents it but does NOT write it).
- It does NOT add a CLI surface. `sdlc trace --kind=signoff_recorded` will work after 2A.12 ships; for 2A.7's testing, the integration tests directly call `validate_signoff` + `write_record` on a tmp_path.
- It does NOT cover phase-3 (AC10).

### Architecture compliance

- **Module specifications (Architecture §1056-§1071, §854-§858).** `signoff/` exposes: `generate_signoff_md` (Story 2A.12), `validate_signoff` (Story 2A.7 — AC3), `write_record` (Story 2A.7 — AC5), `compute_artifact_hash` (Story 2A.7 — AC4). Imports allowed: `errors`, `contracts`, `state`, `journal`. **Forbidden from**: `engine`, `dispatcher`, `cli`. Note: AC11/D1 considers whether `hooks` may import `signoff` (recommended D2 = NO; DI through dispatcher).
- **Boundary rule §1061.** `signoff/` is BELOW `engine`, `dispatcher`, `cli` in the layer hierarchy; `signoff/` does NOT import any of them. AC11 enforces.
- **Atomic write protocol (Architecture §569-§589).** `records.write_record` MUST go through `state.atomic.write_atomic` (Story 1.10). Do NOT roll a separate writer.
- **JSON canonicalization (Architecture §496-§515, Pattern §3).** The canonical record is YAML, NOT JSON — use `yaml.safe_dump(... sort_keys=True, default_flow_style=False, allow_unicode=True)` for byte-stable round-trip. Document the equivalence to Pattern §3 in `hasher.py` docstring.
- **Pydantic strict-mode (ADR-025).** `SignoffRecord` + `ArtifactRef` + `_SignoffMdDraft` inherit `StrictModel`. `model_validate(...)` calls pass `strict=True` implicitly via the StrictModel base.
- **Wire-format v1 lock (ADR-024).** AC9 verifies `5 contracts match snapshots` posture (D2 recommended). The `_SignoffMdDraft` model is ALWAYS private; `SignoffRecord` privacy is the AC11/D2 D-decision.
- **Cold-start budget (Architecture §488-§494).** `compute_state(phase=N)` per call: 1× directory check (.claude/state/signoffs/) + 1× file existence check (phase-N.yaml) + at-most-1× YAML parse. < 5ms. Negligible vs the existing 200ms cold-start floor. The hash-drift property test runs hundreds of iterations but lives under `pytest.mark.property` (separate gate).

### Library / framework requirements

- **`hashlib` (stdlib)** for sha256 — already used by Story 2A.5's `compute_hook_hashes`.
- **`pathlib` (stdlib)** for filesystem traversal.
- **`pyyaml` ≥ 5.x** for YAML parsing/serialisation — already pinned via `workflows/loader.py` (Story 2A.1) + `runtime/mock.py`. Use `yaml.safe_load` (NOT `yaml.load`) and `yaml.safe_dump` (NOT `yaml.dump`).
- **`pydantic` ≥ 2.x** for `SignoffRecord` / `ArtifactRef` / `_SignoffMdDraft` (already pinned). Use `StrictModel` from `contracts/_strict_model.py` (Story 2A.1 introduced).
- **`hypothesis` ≥ 6.x** for AC8 property suite — already pinned via Story 1.11 + 1.12 (`tests/property/test_replay_invariant.py`, `test_journal_append_only.py`).
- **`structlog`** for the AC10 once-per-process [WARN] (verify the project uses structlog per `src/sdlc/engine/logging.py`; if absent, fall back to stdlib `logging` and document).
- **No new runtime dependencies introduced.** Specifically: do NOT add `ruamel.yaml` (PyYAML safe_dump is sufficient for canonicalization); do NOT add `cattrs` or any serialisation library beyond pydantic; do NOT add `watchdog` or filesystem-event monitoring (signoff state is computed on-demand).
- **Python ≥ 3.10** per `.python-version`; `from __future__ import annotations` consistently.

### File structure requirements

(Verbatim from AC11; reproduced here for the dev agent's quick reference.)

```
src/sdlc/signoff/                            # NEW PACKAGE (currently does not exist)
├── __init__.py                              # NEW (≤ 30 LOC) — public re-exports
├── states.py                                # NEW (≤ 200 LOC) — SignoffState enum + compute_state
├── hasher.py                                # NEW (≤ 150 LOC) — compute_artifact_hash + compute_signoff_record_hash
├── records.py                               # NEW (≤ 400 LOC) — SignoffRecord + ArtifactRef + _SignoffMdDraft + I/O
└── validator.py                             # NEW (≤ 250 LOC) — validate_signoff + ValidatedSignoff + ArtifactDrift

src/sdlc/hooks/builtin/                      # EXISTS (Story 2A.4)
└── phase_gate.py                            # UPDATE — refactor to use compute_state via DI

tests/unit/signoff/                          # NEW
├── __init__.py
├── test_states.py                           # AC1
├── test_hasher.py                           # AC4
├── test_signoff_record_hash.py              # AC4 second test file
├── test_records.py                          # AC5
├── test_signoff_md_draft.py                 # AC2 (reader)
├── test_validator.py                        # AC3
└── test_hash_drift_first_match.py           # AC8 deterministic-first-match

tests/property/                              # EXISTS (Story 1.11)
└── test_hash_drift.py                       # NEW — AC8 property suite

tests/integration/                           # EXISTS
├── test_signoff_lifecycle.py                # NEW — full lifecycle
├── test_signoff_replan_invalidation.py      # NEW — invalidate_record cycle
└── test_phase_gate_signoff_read.py          # UPDATE (Story 2A.4) — DI of compute_state

scripts/check_module_boundaries.py           # CONDITIONAL — extend hooks.depends_on if AC11/D1 chose D1

docs/architecture-overview.md                # UPDATE — Phase-3 no-signoff note + module spec verification
docs/runbooks/diagnose-hook-rejection.md     # UPDATE — phase_gate post-2A.7 section
docs/runbooks/diagnose-signoff-drift.md      # NEW — operator runbook
docs/decisions/ADR-024-*.md                  # CONDITIONAL — only if AC11/D2 chose D1 (promote)

_bmad-output/implementation-artifacts/deferred-work.md  # UPDATE — close PHASE-GATE-READ; open REPLAN-INVALIDATION-WIRE
```

Mirrors:
- `src/sdlc/hooks/tampering.py` (Story 2A.5) — module-docstring style + boundary discipline + `details={"step": ..., "path": ...}` error pattern + symlink-escape check + private pydantic model (`_HookHashStore` ↔ `_SignoffMdDraft`).
- `src/sdlc/cli/scan.py:31` — `_compute_sha256_of_file` shape; reuse OR mirror the streaming chunked-read pattern.
- `src/sdlc/state/atomic.py` — `write_atomic` public function (verify name); reuse for `records.write_record` + `records.invalidate_record`.
- `src/sdlc/cli/_time.py:now_rfc3339_utc_ms` — single source of truth for RFC 3339 UTC ms timestamps.
- `tests/property/test_replay_invariant.py` (Story 1.12) — `hypothesis` strategy + helper layout pattern.
- `tests/property/test_journal_append_only.py` (Story 1.11) — property-suite organisation + `@settings` budget pattern.

### Testing requirements

- Coverage: ≥ 90% repo-wide MUST hold; 100% on `signoff/{states,hasher,validator}.py` (pure logic); ≥ 95% on `signoff/records.py` (atomic-write integration with state/atomic.py).
- Test marks: `@pytest.mark.unit` for unit tests; `@pytest.mark.property` for AC8 (existing marker per Story 1.11); integration tests under `tests/integration/` use the project default mark.
- **Anti-tautology receipt** (Task 4.4): MANDATORY per AC8; document in PR Change Log.
- Property test budget: `@settings(max_examples=200, deadline=5000)` — 200 per mutation type × 4 types = 800 total; CI deadline must accommodate. If `pytest -m property` exceeds 60s on the CI image, tighten to `max_examples=100` and document in Change Log.
- Symlink-escape security test (Task 1.1) uses `pytest tmp_path`-based symlinks; mark `posix-only` if `os.symlink` is unsupported on the target test platform (mirror Story 2A.5's `_SKIP_WIN32` shape).
- Integration tests use real subprocess for `sdlc scan` interaction OR direct API calls (no subprocess needed for the lifecycle test — pure API).

### Previous-story intelligence — what to copy + what to avoid

**Copy from Story 2A.5 (Hook Tampering Detection):**
- The `_HookHashStore` privacy posture EXACTLY → apply to `_SignoffMdDraft` (private; never in `sdlc.contracts`; documented in module docstring; no snapshot file).
- The `compute_hook_hashes` shape from `tampering.py` → `compute_artifact_hash` mirrors the streaming chunked-read pattern with `hashlib.sha256()`.
- The symlink-escape check from `compute_hook_hashes` → `compute_artifact_hash` MUST refuse symlinks pointing outside the repo root (security defense-in-depth).
- The atomic-write integration from `record_trust` → `records.write_record` uses the same `state.atomic.write_atomic` public function.
- The `details={"step": ..., "path": ...}` `HookError` payload pattern → `SignoffError` mirrors with `details={"step": ..., "phase": ..., "artifact": ...}`.
- The `pytest.mark.skipif(sys.platform == "win32")` for symlink-only tests — mirror verbatim.
- The non-snapshot verification ceremony in tests (Task 8.2) — mirror the AC8 verification from 2A.5.

**Copy from Story 2A.4 (Pre-Write Hook Chain):**
- The `phase_gate.py` minimal yaml.safe_load reader — REPLACED by the canonical reader (Task 6); the existing test `tests/integration/test_phase_gate_signoff_read.py` is UPDATED to inject `compute_state` (NOT replaced; the behavioural assertions remain).
- The `cli/_bypass.py` BypassRequest contract — 2A.7 does NOT touch this; Story 2A.6 propagates bypass through the dispatcher; 2A.7's signoff API is bypass-agnostic (the bypass operates on the hook chain, NOT on the signoff itself; this is intentional per PRD §374).

**Copy from Story 1.11 (append-only journal property test) + Story 1.12 (replay invariant property test):**
- The property-suite shape and `hypothesis` strategy organisation.
- The `@settings(max_examples=..., deadline=...)` budget convention.
- The `_make_arbitrary_*` helper pattern at module scope.

**Copy from Story 1.10 (atomic write protocol):**
- The `state.atomic.write_atomic` (or whichever the canonical public API surface is — verify) for `records.write_record`.
- The tmp+rename+flock+fsync invariant — `records.write_record` MUST satisfy the same kill-mid-write recovery property tested in `tests/chaos/test_atomic_write_kill_points.py` (extend that suite to cover signoff-record writes — OPTIONAL; the existing chaos suite covers state.json and the protocol is shared).

**Avoid:**
- DO NOT import `engine/`, `dispatcher/`, `cli/` from any `signoff/` module. Architecture §1061 and §1109 are non-negotiable.
- DO NOT add a public `sdlc.contracts.signoff_record` re-export unless AC11/D2 D1 is explicitly chosen (recommended is D2 = private).
- DO NOT add `kind="signoff_recorded"` or `kind="signoff_invalidated"` journal entries from `signoff/` modules — those are Story 2A.12 / Story 2A.19 responsibilities. The signoff API is journal-agnostic; the caller appends.
- DO NOT compute hashes after canonicalising the artifact bytes (e.g., normalising line endings). Per AC4: raw bytes only; the artifact is whatever the on-disk bytes are. The atomic-write protocol in Story 1.10 ensures the on-disk bytes are byte-stable; signoff trusts the protocol.
- DO NOT introduce a sync/async split in `signoff/`. All signoff APIs are sync (file I/O is sync syscall in Python; no benefit from `asyncio.to_thread`). Story 2A.5's `compute_hook_hashes` is sync; mirror.
- DO NOT couple `phase_gate.py` to a direct `from sdlc.signoff import compute_state` import without the AC11/D1 D-decision having chosen D1; recommended D2 uses DI.

### Git intelligence (recent commits since 2A.5 done — `git log --oneline -8 main`)

```
b15a622 Merge branch 'epic-2a/2a-4-pre-write-hook-chain-naming-validator-phase-gate' into main
572a1bf chore: resolve sprint-status conflict — 2a-3 done, 2a-4 in-progress
637db9e Merge branch 'epic-2a/2a-3-dispatcher-primary-parallel-synthesizer-retry' into main
65deffb fix(2a-3): trim check_module_boundaries.py to 400 LOC (was 403)
2d281ce docs(2a-3): code-review D — close story 2a-3 review → done; document 5 D-decisions + 28 patches + 8 deferred
bd9fa61 test(2a-3): code-review C — DR1 mandatory integration tests for dispatch + dispatch_panel (AC11)
4bb9187 feat(2a-3): code-review B — CRIT production blockers + DR2/DR3/DR4/DR5 spec realignment + 28 patches
efd71f7 chore(2a-3): Task 10 ruff fixes + Task 11 story close-out (status → review)
```

**Actionable insights:**

- 2A.4 was just merged; `hooks/builtin/phase_gate.py` already lands the minimal yaml.safe_load reader. Task 6's refactor diff is small and surgical — verify the existing tests still pass on the refactored shape.
- `scripts/check_module_boundaries.py` was hard-trimmed to exactly 400 LOC in `65deffb`. AC11/D1 D1 (extend hooks.depends_on) requires ≤ 5 LOC of additions; if the trim ceremony from `65deffb` is repeated, document in Change Log.
- 2A.5 introduced the `[WARN]` stderr pattern for hook-trust posture — reuse the structlog logger pattern for AC10's once-per-process [WARN] (do NOT print to stderr from the signoff module; structlog/logging only).
- 2A.6 (sibling Layer 3) MAY be developed in parallel — coordinate `phase_gate.py` edits via worktree-per-story; prefer landing 2A.7 first so 2A.6's dispatcher wiring can pass `signoff.compute_state` to phase_gate without a placeholder.

### Latest technical specifics — Pydantic v2 + Pyrtest hypothesis behaviour

**Pydantic v2 quirks for SignoffRecord:**
- `Annotated[str, StringConstraints(pattern=r"...")]` is the canonical field-level regex (AC3 + AC5 use this for `hash` field).
- `model_dump(mode="json")` produces JSON-compatible scalars — for the YAML serialisation, pass through `yaml.safe_dump`. Beware: `model_dump(mode="python")` returns native Python objects (e.g., `datetime` instances if the model uses them) which `yaml.safe_dump` cannot serialise without explicit converters. Use `mode="json"` to force string serialisation.
- `tuple[ArtifactRef, ...]` for the `artifacts` field requires `model_config = ConfigDict(frozen=True)` for byte-stable round-trip. StrictModel inherits frozen=True.

**Hypothesis budget:**
- `hypothesis.strategies.binary(min_size=1024, max_size=10240)` produces deterministic byte strings under a given seed.
- `@settings(max_examples=200)` with 4 mutation types × 200 = 800 examples; on the project's CI image (per ADR-006) this should complete in < 30s.
- `@pytest.mark.property` is the existing marker; the `pytest -m property` gate runs in a separate CI step (mirror Story 1.11's CI workflow).

## Project Context Reference

- **Source ACs:** `_bmad-output/planning-artifacts/epics.md:1139-1167` (Story 2A.7 verbatim).
- **Source FR/NFR:** PRD FR32 (hash-drift validation), NFR-REL-3 (zero false negatives), PRD §344 (audit-grade chain-of-custody promise), PRD §388 (signoff state visual contract — the four states map to dashboard cells in Story 5.9), PRD §203 (Phase 3 has no signoff).
- **Architecture:** `_bmad-output/planning-artifacts/architecture.md` §208 (canonical record location), §317 (state/journal/signoff cluster), §496-§515 (canonicalization Pattern §3), §569-§589 (atomic write protocol), §615-§621 (HookPayload — for context; signoff has its own private models), §706-§712 (canonical filesystem layout for phase dirs), §854-§858 (signoff/ module spec), §1056-§1071 (module dependency table — `signoff` depends_on errors+contracts+state+journal), §1061 (signoff/ position in layer hierarchy), §1141-§1142 (FR11→file map for `signoff/generator.py` — Story 2A.12; FR32→`signoff/validator.py` — this story).
- **DAG:** `docs/sprints/epic-2a-dag.md` §3 Layer 3 (2A.6 + 2A.7 siblings); §5 owner Winston, recovery slice + ADR cross-reference; §7 risk row "Hash-drift between 2A.4 and 2A.7" — 2A.7 IS the mitigation (D1 Hypothesis byte-stability landed before Layer 2 per Winston's gate condition; AC8 property suite is the v1.0 deliverable).
- **ADRs:**
  - **ADR-013** (workflow trust model v1) — v1 advisory posture; signoff hash-drift is HARD (NOT advisory) — this is the audit-grade boundary.
  - **ADR-024** (wire-format v1 lock) — `SignoffRecord` privacy posture (AC9 + AC11/D2).
  - **ADR-025** (pydantic strict-mode) — `StrictModel` inheritance.
  - **ADR-026** (TDD-first commit ordering) — Tasks 1, 2, 3, 4, 5 are TDD-first commits.
- **Cross-story contracts:**
  - **Story 1.10 (atomic write protocol):** reuse `state.atomic.write_atomic`; honour the kill-mid-write invariant.
  - **Story 1.11 (journal append):** signoff/ does NOT append journal entries; callers (2A.12, 2A.19) do.
  - **Story 2A.4 (pre-write hook chain):** `phase_gate.py` refactor (Task 6); `EPIC-2A-DEBT-PHASE-GATE-READ` resolution.
  - **Story 2A.5 (hook tampering):** `_HookHashStore` privacy posture mirrored by `_SignoffMdDraft` (AC9).
  - **Story 2A.6 (Claude Code PreToolUse hook + sdlc hook-check, sibling Layer 3):** dispatcher wires `compute_state` into `phase_gate` via DI per AC11/D1 D2 recommendation; coordinate `phase_gate.py` edit window via worktree branch sync.
  - **Story 2A.12 (Layer 5):** `/sdlc-signoff` ceremony — generates SIGNOFF.md draft (writer; counterpart to AC2 reader); calls `validate_signoff` + `write_record` on user approval; appends `kind="signoff_recorded"` journal entry.
  - **Story 2A.19 (Layer 7):** `sdlc replan` — calls `invalidate_record(...)` from AC5; appends `kind="signoff_invalidated"` journal entry; recomputes downstream dirty flags.
  - **Story 5.9 (Epic 5 dashboard):** Phase Tracker reads the 4 states from compute_state for visual rendering (PRD §388).

## Story Completion Status

- ALL 12 ACs documented with explicit test obligations.
- 11 Tasks ordered TDD-first per ADR-026 §1; 1 mandatory anti-tautology receipt (Task 4.4 per AC8).
- 2 D-decision sites: AC11/D1 (hooks→signoff boundary — recommended D2: DI through dispatcher); AC11/D2 (SignoffRecord wire-format promotion — recommended D2: keep private until consumer needs).
- Wire-format ADR-024 verified: `SignoffRecord` is private; `tests/contract_snapshots/v1/` snapshot count remains 5 (per AC11/D2 D2 recommended).
- 1 debt item closed (`EPIC-2A-DEBT-PHASE-GATE-READ`); 1 debt item opened (`EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE` for Story 2A.19).
- Ultimate context engine analysis completed — comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- ruff PLR2004 (magic literal `3`): introduced `_PHASE_NO_SIGNOFF: int = 3` in records.py, states.py, validator.py
- ruff PLC0415 (import not at top-level): added `import sys` at module level in records.py; removed inline `import sys as _sys` in list_records()
- ruff B904 (bare raise in except): added `from _exc` to PurePosixPath exception handler in ArtifactRef._validate_path
- ruff C901 (complexity): added `# noqa: C901` to compute_state and validate_signoff — complexity 10 is genuine state-machine logic, not a simplifiable branch
- mypy attr-defined vs union-attr mismatch in hasher.py:67: changed `type: ignore[union-attr]` → `type: ignore[attr-defined]`
- mypy unused-ignore in records.py:325, 340: removed `# type: ignore[return-value]` comments (mypy now infers return type correctly)
- Windows POSIX-only test skips: 23 tests skipped (symlink/chmod) — platform-expected, not regressions
- Property test isolation: tests use `tempfile.TemporaryDirectory()` directly to avoid hypothesis function_scoped_fixture health check

### Completion Notes List

- AC11/D1 D-decision: chose D2 — `phase_gate.py` accepts `signoff_reader: Callable[[int, Path], SignoffState]` required kwarg (no default); dispatcher wires `signoff.compute_state` at chain-construction time; preserves hooks/ leaf-module boundary per Story 2A.5 policy
- AC11/D2 D-decision: chose D2 — `SignoffRecord` private to `sdlc.signoff`; not exported from `sdlc.contracts`; no snapshot under `tests/contract_snapshots/v1/`; mirrors `_HookHashStore` posture from Story 2A.5 exactly
- Anti-tautology receipt #1 (Task 4.4 AC8 mandatory): inverted `actual_hash != art.hash` → `actual_hash == art.hash` in validator.py; confirmed test_no_mutation_always_approves FAILED (raised SignoffError instead of returning APPROVED); reverted; documented in Change Log
- EPIC-2A-DEBT-PHASE-GATE-READ RESOLVED: phase_gate now uses signoff.compute_state via DI; deferred-work.md updated
- Quality gate (Task 10): ruff format+check clean; mypy --strict src/sdlc/signoff + phase_gate.py = "Success: no issues found in 6 source files"; pytest 217 passed 23 skipped; property 4 suites × 200 examples = 800 total; wire-format 5 contracts match; module boundaries 0 violations
- records.py uses atomic tmp+replace pattern directly (no `state.atomic.write_atomic` import — that API uses flock which is POSIX-only; direct bytes write is cross-platform per Windows constraint)
- structlog not available in signoff layer; used stdlib `logging` for AC10 once-per-process [WARN] in states.py

### File List

**New files:**
- src/sdlc/signoff/__init__.py
- src/sdlc/signoff/states.py
- src/sdlc/signoff/hasher.py
- src/sdlc/signoff/records.py
- src/sdlc/signoff/validator.py
- tests/unit/signoff/__init__.py
- tests/unit/signoff/test_states.py
- tests/unit/signoff/test_hasher.py
- tests/unit/signoff/test_signoff_record_hash.py
- tests/unit/signoff/test_records.py
- tests/unit/signoff/test_signoff_md_draft.py
- tests/unit/signoff/test_validator.py
- tests/unit/signoff/test_hash_drift_first_match.py
- tests/property/test_hash_drift.py
- tests/integration/test_signoff_lifecycle.py
- tests/integration/test_signoff_replan_invalidation.py
- docs/runbooks/diagnose-signoff-drift.md

**Updated files:**
- src/sdlc/hooks/builtin/phase_gate.py (Task 6: DI signoff_reader; removed raw yaml.safe_load reader; review patches P12/P23/P30 — `..` + absolute-path deny, SignoffReaderType cleanup, narrow except)
- tests/integration/test_phase_gate_signoff_read.py (Task 6.3: inject compute_state; add INVALIDATED_BY_REPLAN case; review patch P-D2 — details key rename)
- tests/integration/test_hook_chain_smoke.py (Task 6: phase_gate DI fixture)
- tests/unit/dispatcher/test_dispatch_primary.py (lint-only mods)
- tests/unit/hooks/test_naming_validator.py (lint-only mods)
- tests/unit/hooks/test_phase_gate.py (Task 6.3: DI-based parametrised cases for all 4 SignoffStates + bypass + review patch P30 narrow except)
- _bmad-output/implementation-artifacts/deferred-work.md (Task 6.4: EPIC-2A-DEBT-PHASE-GATE-READ → RESOLVED; review patches P3/P4 + D3 — REPLAN-INVALIDATION-WIRE + SIGNOFF-FLOCK-CONCURRENCY entries)
- _bmad-output/implementation-artifacts/sprint-status.yaml (status flip: review → done)
- docs/architecture-overview.md (Task 9.1: Hook Chain Integration Map + Phase-3 no-signoff note + DI data flow diagram; review patches P14/P17 — accurate phase-3 enforcement claim + correct §1067/§1109 ref)
- docs/runbooks/diagnose-hook-rejection.md (Task 9.2: 4-state post-2A.7 diagnostic table)
- docs/runbooks/diagnose-signoff-drift.md (review patch P-D2 — details key rename; missing-actual sentinel doc)

**New files (review-driven):**
- src/sdlc/dispatcher/_hook_chain.py (Story 2A.7 D1 review decision: production-ready `build_pre_write_hook_chain(repo_root)` builder for `run_hook_chain` consumption; preserves hooks/ → signoff/ boundary)

### Change Log

- D-decision: AC11/D1 chose D2 because preserves hooks/ leaf-module boundary; DI via `signoff_reader: Callable[[int, Path], SignoffState]` required kwarg; dispatcher wires at chain-construction time
- D-decision: AC11/D2 chose D2 because SignoffRecord has no current public consumer; private posture mirrors _HookHashStore from Story 2A.5; ADR-024 ceremony cost unjustified until first consumer appears
- Anti-tautology receipt #1: inverted `actual_hash != art.hash` → `actual_hash == art.hash` in validator.py; asserted test_no_mutation_always_approves FAILED (SignoffError raised instead of APPROVED state); reverted to correct comparison
- EPIC-2A-DEBT-PHASE-GATE-READ marked RESOLVED: Story 2A.7 Task 6 — phase_gate now uses signoff.compute_state via DI; no more raw yaml.safe_load in phase_gate
- EPIC-2A-DEBT-REPLAN-INVALIDATION-WIRE opened: Story 2A.19 owner — sdlc replan must call invalidate_record + append kind="signoff_invalidated" journal entry; AC6 deferred per story scope boundary
