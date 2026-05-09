# ADR-024: Wire-Format v1 Lock Ceremony

**Status:** Accepted (2026-05-09, Story 1.21)

## Context

The SDLC-Framework substrate crosses five distinct process and version boundaries via
wire-format contracts (Architecture §169-§179). Each contract is a pydantic model that
serialises to/from disk, IPC, and hook payloads:

- `JournalEntry` — append-only audit record (Decision B3, Architecture §595-§606)
- `ResumeToken` — checkpoint for mid-phase resume (Architecture §608-§613)
- `HookPayload` — unified pre-write hook envelope (Decision D2, Architecture §615-§621)
- `SpecialistFrontmatter` — YAML header for ~25 specialist agents (Decision C3, Architecture §623-§632)
- `WorkflowSpec` — YAML workflow definition (Architecture §634-§643)

Decision F3 (Architecture §382) mandates per-contract independent versioning. Stories
1.1–1.20 ship the walking skeleton, and Story 1.7 pins each contract at
`schema_version: Literal[1] = 1` with `extra="forbid"` and `frozen=True`. However, an
in-code `Literal[1]` annotation is an insufficient lock: a maintainer can silently widen
it to `Literal[1, 2]` or rename a field without any CI gate firing, causing replay
divergence and hook-enforcement failures in production (Architecture §397, §1237).

The wire-format cluster F3 + B3 + D2 + C3 (Architecture §1238) is the binding rationale.
Epic 2A specialist authors need a frozen contract surface before authoring agents against
these models. Story 1.21 is the Epic 1 ship gate.

`State.schema_version` (Decision B5, `src/sdlc/state/model.py`) is explicitly excluded —
it is a process-internal projection, not a wire-crossing surface. Its discipline is
Story 1.19's migration gate (`src/sdlc/state/reader.py:CURRENT_SCHEMA_VERSION`).

## Decision

1. The five wire-format contracts are **pinned at `schema_version=1`** via JSON-Schema
   snapshots committed under `tests/contract_snapshots/v1/<slug>.json`. Bytes are
   deterministic: `model_json_schema(mode="serialization")` canonicalized with
   `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"), indent=2)`
   encoded UTF-8 with a trailing `\n`. The `mode="serialization"` choice is deliberate —
   the wire format is the OUTPUT shape, not the input-validation shape.

2. The lock is **mechanically enforced by two redundant gates**:
   - `tests/contracts/test_wireformat_immutability.py` (pytest, `@pytest.mark.unit`) —
     runs in the test job; catches drift even if the lint hook is bypassed.
   - `scripts/freeze_wireformat_snapshots.py` (pre-commit hook + CI lint step) —
     fastest feedback; fires only when a contract `.py` or snapshot `.json` is staged.

3. Any future contract evolution is a **deliberate, version-bumped, migration-paired
   event**: `Literal[1]` → `Literal[1, 2]` AND a sibling snapshot at
   `tests/contract_snapshots/v2/<slug>.json` AND a migration script at
   `src/sdlc/migrations/contracts/v2/<slug>.py` (the `migrations/contracts/` package is
   a forward-compat seam — created on first bump, not today).

## Alternatives Considered

- **Alternative A — golden-bytes only (Story 1.7 `_GOLDEN` literals):** Locks the shape
  of one fixture per contract; does not lock the full schema field-set. A field rename
  that avoids the golden fixture would slip through. Rejected: insufficient surface
  coverage.

- **Alternative B — `model_fields.keys()` diff only:** Misses type narrowing (e.g.,
  `int` → `Literal[0,1]`) and constraint drift (e.g., regex pattern change). Rejected:
  too coarse.

- **Alternative C — single combined snapshot for all 5 contracts:** Loses per-contract
  PR-diff granularity and defeats Decision F3's "evolve independently" affordance (a v2
  of one contract forces regeneration of the combined file). Rejected.

- **Alternative D — runtime hash check on import (no committed file):** Shows only
  "hash mismatch" with no diff; loses git history as the audit trail. Rejected: diff
  legibility and history are load-bearing.

## Consequences

**Positive:**
- Epic 2A specialists can be authored against a frozen contract surface.
- Replay divergence (Architecture §397) becomes mechanically detectable before it
  reaches production.
- The migration discipline gains a reified artifact (the snapshot file) that ADRs can
  reference and PR reviewers can inspect in seconds.

**Negative:**
- Five extra committed JSON files (~1 KB each) in `tests/contract_snapshots/v1/`.
- Regeneration (`scripts/freeze_wireformat_snapshots.py --write`) is a deliberate manual
  action; CI runs `--check` only.

**Excluded from the lock:** `State` (process-internal projection, Decision B5),
`AgentResult` / `_Fixture` (runtime-internal; parity enforced by
`tests/unit/runtime/test_mock.py:test_fixture_and_agent_result_have_parity_fields`).

**Forward-compat seams:**
- `tests/contract_snapshots/v<N>/` — sibling directories per schema version; v1 stays
  when v2 ships (historical migration tests).
- `src/sdlc/migrations/contracts/v<N>/<slug>.py` — created on first bump, not today.
  Per-slug subdir distinguishes from Story 1.19's flat `migrations/v<N>.py` (state).
- NFC normalization not applied today (ASCII-only schemas); add `_normalize_strings` if
  a future contract introduces non-ASCII descriptions.
- `_CONTRACTS` registry — adding a 6th contract requires an ADR amendment + new snapshot.
- `--write` mechanical `schema_version`-bump guard — soft in v1; formalizable in v2.x.
- `mode="serialization"` vs `mode="validation"` — revisit if contracts develop sharply
  divergent input/output shapes.

## Revisit-by

On the first wire-format contract version bump (creates `migrations/contracts/v2/<slug>.py`
+ sibling `tests/contract_snapshots/v2/<slug>.json`) OR first non-trivial Epic 2A
specialist authoring that exposes F3-cluster gaps. No calendar-based revisit — this ADR's
discipline is event-triggered.

## References

- `_bmad-output/planning-artifacts/architecture.md` §169-§179 — wire-format gap
- `_bmad-output/planning-artifacts/architecture.md` §347 — Decision B3
- `_bmad-output/planning-artifacts/architecture.md` §357 — Decision C3
- `_bmad-output/planning-artifacts/architecture.md` §364 — Decision D2
- `_bmad-output/planning-artifacts/architecture.md` §382 — Decision F3
- `_bmad-output/planning-artifacts/architecture.md` §395-§397 — B3 + F3 coupling
- `_bmad-output/planning-artifacts/architecture.md` §501-§508 — JSON canonicalization prior art
- `_bmad-output/planning-artifacts/architecture.md` §591-§643 — 5 contracts canonical fields
- `_bmad-output/planning-artifacts/architecture.md` §1238 — wire-format cluster
- `_bmad-output/planning-artifacts/epics.md` §932-§953 — Story 1.21 epic AC block
- `src/sdlc/contracts/__init__.py` — public API surface (`__all__`)
- `src/sdlc/contracts/journal_entry.py:29` — `schema_version: Literal[1] = 1` prototype
- `tests/unit/contracts/test_f3_independence.py` — per-contract independence test
- `tests/unit/contracts/test_journal_entry.py:25-29` — Story 1.7 `_GOLDEN` golden-bytes
- `tests/contracts/test_wireformat_immutability.py` — this ADR's mechanical lock
- `scripts/freeze_wireformat_snapshots.py` — snapshot generator / verifier
- `_bmad-output/implementation-artifacts/1-19-migration-framework-major-version-refusal.md`
  — Story 1.19 state-migration discipline (parallel, not nested)
