# Story 1.12: State Projection from Journal + Replay Property Test

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer relying on the journal-as-source-of-truth model (Decision B5),
I want `state.project_from_journal(journal_path)` implementing pure-function state reconstruction, with a hypothesis property test asserting `replay(journal[0:k]) == state_at_step_k` for every k,
so that `state.json` is provably a deterministic projection of the journal (FR35, NFR-REL-2, Decision B4 + B5, Architecture §220 + §348 + §845).

## Acceptance Criteria

**AC1 — Pure-function projection over the full journal (epic AC block 1)**

**Given** Story 1.11 complete (`sdlc.journal.append`, `iter_entries`, `iter_after` shipped at `src/sdlc/journal/{__init__,writer,reader}.py`; `JournalEntry` v1 contract on disk at `src/sdlc/contracts/journal_entry.py`; `State` minimal model on disk at `src/sdlc/state/model.py` with fields `schema_version: int = 1`, `next_monotonic_seq: int = 0`, `epics: dict[str, Any] = {}`),
**When** I call `project_from_journal(journal_path: Path) -> State` on a journal containing N entries,
**Then** the function:

1. Returns `State()` defaults if the journal is missing or empty (no entries).
2. Iterates entries via `sdlc.journal.iter_entries(journal_path)` — file-order is monotonic_seq order (Story 1.11 reader-invariant guarantees this).
3. Applies a deterministic per-`kind` reducer to fold each entry into the running state. For v1 minimum schema, the only stateful effects are: (a) `next_monotonic_seq = max(seq across entries) + 1`; (b) `epics[target_id]` is updated with `payload` for `kind == "state_mutation"` entries whose `target_id` matches the regex `^epic-\d+$`; (c) all other kinds (`agent_dispatch`, `signoff`, `bypass_signoff`, `auto_mad_resolve`, `hook_bypass`) advance `next_monotonic_seq` only — they do NOT mutate `epics`.
4. Returns the final `State` as a new pydantic instance — original `State()` (the seed) is NOT mutated; intermediate states are not retained on disk.

**And** the function is **pure** in the sense Decision B4 + B5 require:
   - **No I/O writes**: no `state.json` write, no journal write, no telemetry side-effect, no `print` to stdout (stderr warnings on malformed lines via the reader are fine — they originate inside `journal/reader.py`, not inside the projection function itself).
   - **No global mutation**: no module-level state, no class-level cache, no `nonlocal` write to a captured variable.
   - **Deterministic**: `project_from_journal(p)` called twice in the same process returns two `State` instances that are `model_dump()`-equal (the `State` model is `frozen=True` so `==` works structurally).
   - **Idempotent under replay**: calling `project_from_journal(p)` after appending a new entry to `p` returns a state where `next_monotonic_seq` advanced and the relevant `epics[target_id]` slot is updated; calling it again with no new entries returns the same state.

**And** intermediate states at any prefix `journal[0:k]` are recoverable: the helper `_project_entries(entries: Iterable[JournalEntry]) -> State` is exposed as a private-but-importable function (single underscore prefix; not in `__all__` but reachable from `sdlc.state.projection`) so the property test can drive it with a Python iterable directly without writing-then-reading a file. **Public API contract**: only `project_from_journal(path)` is added to `sdlc.state.__all__`; `_project_entries(iterable)` is a test seam, NOT a stable API surface.

**And** the public API exported from `sdlc.state` after this story is exactly: `("State", "write_state_atomic", "write_state_atomic_sync", "read_state", "project_from_journal")` (semantic order, with `# noqa: RUF022`). `project_from_journal` is appended at the end of the existing `__all__` tuple — this is the ONLY edit to `state/__init__.py`.

**And** unit tests in `tests/unit/state/test_state_projection.py` verify each behavior in isolation: empty/missing journal returns `State()` defaults; single `state_mutation` entry on `target_id="epic-1"` produces `state.epics["epic-1"] == dict(payload)`; sequence of mixed kinds advances `next_monotonic_seq` exactly to `max(seq) + 1`; non-`state_mutation` kinds leave `epics` untouched; an entry with `target_id` not matching the `^epic-\d+$` regex (e.g., `target_id="task-1.2.3"`) does NOT touch `epics` (forward-compat — task/story projections will be added in later stories).

**AC2 — Replay invariant property test: replay(journal[0:k]) == state_at_step_k (epic AC block 2)**

**Given** the property test module at `tests/property/test_replay_invariant.py`,
**When** hypothesis generates arbitrary journal append sequences and arbitrary `k` values in `[0, N]`,
**Then** for every prefix length `k`: the state produced by `project_from_journal(journal_with_first_k_entries)` equals the state produced by an independent **oracle reducer** that folds the first `k` entries one at a time. The oracle reducer is a separate, minimal Python function defined in the property test file itself (NOT imported from `sdlc.state.projection` — Murat's invariant requires two independent implementations to provably exercise the contract; co-locating the oracle with the test makes the contract explicit and reviewable in one place).

**And** the property is structured as: hypothesis generates a sequence of `N` valid `JournalEntry` instances (1 ≤ N ≤ 30; `monotonic_seq` strictly increasing across the sequence — reusing the `monotonic_sequence_strategy` pattern from Story 1.11's `tests/property/test_journal_append_only.py`); the test then iterates `k` from 0 to N inclusive; for each `k`:
  - Truncate the journal file to contain only entries `[0:k]` — implemented as: write `entries[0:k]` to a fresh `tmp_path / "journal.log"` via `append_sync` in a loop (clean file per `k` to keep state isolated; tmp_path resets per hypothesis example).
  - Compute `actual = project_from_journal(journal_path)`.
  - Compute `expected = _oracle_reduce(entries[0:k])` using the in-test oracle.
  - Assert `actual.model_dump(mode="json") == expected.model_dump(mode="json")` — JSON-equality via `model_dump(mode="json")` to bypass any pydantic `__eq__` quirks with `MappingProxyType` payloads (Story 1.7's `JournalEntry._freeze_payload` returns a `MappingProxyType`; pydantic's `frozen=True` model `__eq__` should work but JSON-equality is the canonical assertion).

**And** the property test runs **≥1000 hypothesis examples** in CI per run (`@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])`). Reasoning for `function_scoped_fixture` suppression: each hypothesis example uses `tmp_path` (function-scoped); hypothesis warns by default, but the alternative (regenerating the same `tmp_path` across examples) introduces cross-example state leakage — exactly the bug the property exists to detect. Mirror Story 1.11's per-example fixture isolation pattern.

**And** the property test runs **also as a single-trace fast smoke test** with `@settings(max_examples=20, deadline=2000)` — same property body, smaller surface — runs in unit jobs so failures surface in normal `pytest` invocations without waiting for the full property job.

**And** mark all property functions with `@pytest.mark.property` and `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — depends on journal.append_sync which requires fcntl + O_APPEND")` (mirror Story 1.10/1.11 pattern). The Windows skip is mandated by the writer's POSIX gate; the projection function ITSELF is cross-platform (it only reads), but the test must write entries to a journal file via `append_sync` to construct the fixture, which forces POSIX-only execution.

**And** the property suite runs in CI as part of the existing property job in `.github/workflows/ci.yml` — the existing `pytest -m property` step picks up `test_replay_invariant.py` automatically. No new CI job is added (consistent with Story 1.11 scope discipline).

**AC3 — Schema-version migration refusal (epic AC block 3)**

**Given** a journal containing entries with `schema_version` fields,
**When** projection encounters an entry where `schema_version != 1` (the only version recognized in v1),
**Then** `project_from_journal` raises `JournalError` with the message `"unknown schema_version=N for kind=X; run sdlc migrate-vN"` where `N` is the entry's actual `schema_version` and `X` is the entry's `kind` field, formatted exactly:
   - `f"unknown schema_version={entry.schema_version} for kind={entry.kind}; run sdlc migrate-v{entry.schema_version}"`

**And** the `JournalError` carries `details={"path": str(journal_path), "step": "project_unknown_schema", "schema_version": entry.schema_version, "kind": entry.kind, "monotonic_seq": entry.monotonic_seq, "lineno": <lineno-or-None>}`. **Note on `lineno`**: the projection function consumes `JournalEntry` instances from `iter_entries` which does not surface line numbers; setting `lineno=None` is acceptable. If a later story adds line-number propagation through the reader, this field becomes populated automatically.

**And** the error is raised **before** any further entries are consumed — projection halts on first unknown-version entry. The partial state up to (but not including) the offending entry is NOT returned (no half-projected `State` value escapes; the function either returns a valid `State` or raises). Document inline: this is **fail-loud-on-schema-drift** (Decision F3 — per-contract versioning with explicit migration). It mirrors Story 1.11's monotonicity validate-fail-then-no-write pattern.

**And** the error message names the migration command (`sdlc migrate-vN`) — even though `cli/migrate.py` is not yet implemented (FR49, deferred); naming the command in the error is the **forward-contract**: future stories implementing `migrate-vN` will key off this exact wording, and users seeing this message in v1 will know what command will eventually exist. Document this contract in ADR-015's Consequences.

**And** since `JournalEntry` is declared as `schema_version: Literal[1] = 1` in `src/sdlc/contracts/journal_entry.py:29`, **a journal line written today with `schema_version=2` will fail pydantic validation in `JournalEntry.model_validate_json` BEFORE it ever reaches the projection's schema_version check** — pydantic's `Literal[1]` rejects `2` at parse time. The projection's schema_version check is therefore **the second line of defence**: it catches the case where a future build with `schema_version: int = Field(...)` (broader literal range) parses the entry but the projection still recognizes only v1. Document this dual-defence model inline in `projection.py` and in the unit tests for AC3 (Task 5).

**AC4 — Module boundary update: state depends on journal (NEW for this story)**

**Given** the architectural intent that `state.json` is a projection of the journal (Decision B5, Architecture §349, §845),
**When** `state/projection.py` is implemented,
**Then** `MODULE_DEPS["state"].depends_on` in `scripts/check_module_boundaries.py:50-53` MUST be updated from `frozenset({"errors", "contracts", "concurrency", "config"})` to `frozenset({"errors", "contracts", "concurrency", "config", "journal"})` — adding `"journal"` exactly once. This is the first explicit `MODULE_DEPS` update by any story since the boundary scaffold was registered (Story 1.4); document the change in ADR-015 with a citation back to Architecture §1059 (which lists `project_from_journal` as part of state's public API) + §349 (Decision B5 — state is a projection of journal).

**And** the inverse — `MODULE_DEPS["journal"]` — is NOT modified. Journal continues to NOT depend on state. The directed dependency `state → journal` is acyclic with the existing graph (verified by the `_validate_no_cycles` check in `scripts/check_module_boundaries.py:_validate_topology`).

**And** `scripts/check_module_boundaries.py` continues to have a `_validate_module_deps_keys` invariant test confirming all deps reference declared modules (line 164-170) — re-run as a sanity check after the edit.

**And** the property test in Task 6 includes an explicit assertion: `assert "journal" in MODULE_DEPS["state"].depends_on` — this is an **invariant test** that catches a future refactor that accidentally removes the dep edge.

## Tasks / Subtasks

- [ ] **Task 1: Pre-flight checks before implementation (AC: all)**
  - [ ] Verify Story 1.11 deliverables on disk: `src/sdlc/journal/__init__.py`, `src/sdlc/journal/writer.py`, `src/sdlc/journal/reader.py` all exist; `from sdlc.journal import iter_entries, append_sync` succeeds in a `uv run python -c` smoke. **Expected at story start (2026-05-08)**: all three files present (Story 1.11 status is `in-progress` per sprint-status.yaml; the journal module is fully implemented even though 1.11 hasn't been signed-off / committed yet — verify by reading the disk state). If 1.11 files are missing on disk, abort and ask user to complete 1.11 first.
  - [ ] Verify `MODULE_DEPS["state"]` is in its pre-1.12 form at `scripts/check_module_boundaries.py:50-53`: `depends_on=frozenset({"errors", "contracts", "concurrency", "config"})`, `forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"})`. If it has been edited away (e.g., already includes `"journal"`), abort and ask user — that means a prior story already made the change.
  - [ ] Verify `JournalEntry.schema_version` is declared as `Literal[1] = 1` at `src/sdlc/contracts/journal_entry.py:29` (current state); document in Dev Notes that this means schema_version-2 entries fail pydantic parse before projection — projection's check is the second line of defence (see AC3).
  - [ ] Verify ADR numbering: existing ADRs are 001-014 per `ls docs/decisions/ADR-*.md`. ADR-015 is the next available number for this story.
  - [ ] Verify `tests/property/test_journal_append_only.py` exists (Story 1.11 deliverable) — its strategy helpers (`journal_entry_strategy`, `monotonic_sequence_strategy`) MAY be reused or duplicated. **Decision: duplicate** the strategy helpers into `test_replay_invariant.py` rather than import; rationale: (a) the property test is a contract assertion — keeping its strategy local makes the contract self-contained and reviewable in one file; (b) cross-test imports between property tests are fragile (test discovery order matters, and pytest's collection sometimes imports modules in surprising order); (c) the property test in 1.11 is a SIBLING contract, not a dependency. If the strategies drift over time, that's acceptable for now — both files use the same `JournalEntry` model so the surface is bounded. Document this choice inline in `test_replay_invariant.py`'s docstring.

- [ ] **Task 2: Bootstrap `src/sdlc/state/projection.py` with module skeleton (AC: #1)**
  - [ ] Create `src/sdlc/state/projection.py` with module docstring: `"""State projection from journal — pure function (Decision B5, Architecture §348, §845, FR35).\n\nReplay invariant: project_from_journal(journal[0:k]) == state_at_step_k for every k.\nUses sdlc.journal.iter_entries; respects MODULE_DEPS["state"].depends_on (post-Story-1.12 includes "journal").\n"""`.
  - [ ] First import line: `from __future__ import annotations`. Stdlib imports next: `import re`, `from collections.abc import Iterable, Iterator`, `from pathlib import Path`, `from typing import Any, Final`. Third-party imports: none (no pydantic re-import — `JournalEntry` and `State` are both imported via project paths below). Project imports last: `from sdlc.contracts.journal_entry import JournalEntry`, `from sdlc.errors import JournalError`, `from sdlc.journal import iter_entries`, `from sdlc.state.model import State`.
  - [ ] **CROSS-PLATFORM**: `state/projection.py` is **cross-platform** (no `fcntl`, no `O_APPEND`). Do NOT add the POSIX-only `ImportError` guard at top of file. The function only reads the journal via `iter_entries` (which is cross-platform per Story 1.11 reader). Mirror `state/reader.py` (NOT yet on disk — referenced in Architecture §844 but deferred) and Story 1.11's `journal/reader.py` cross-platform stance.
  - [ ] Define module-level constants:
    - `_EPIC_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^epic-\d+$")` — only `state_mutation` entries with `target_id` matching this pattern affect `state.epics` in v1. Other patterns (story-, task-) are reserved for later stories.
    - `_KNOWN_KINDS: Final[frozenset[str]] = frozenset({"state_mutation", "agent_dispatch", "signoff", "bypass_signoff", "auto_mad_resolve", "hook_bypass"})` — enumerated from Architecture §601-§602. Unknown kinds are NOT raised here (forward-compat: a future kind added in a later story should not break replay of journals written today). Document inline: "if an unknown kind appears, it advances next_monotonic_seq but produces no other state effect — reducer fails open. The schema_version check (AC3) is the strict drift detector; kind drift is permissive by design."
    - `_SCHEMA_VERSION: Final[int] = 1` — the only version this v1 projection recognizes.
  - [ ] LOC budget: `state/projection.py` MUST stay ≤ 200 LOC (well under the 400 cap — projection is a small pure function, not a protocol). If overrunning, split kind-reducers into a `state/_reducers.py` private module — but the simple v1 reducer is ~10 lines; splitting now would be premature.

- [ ] **Task 3: Implement `_project_entries` reducer + `project_from_journal` (AC: #1, #3)**
  - [ ] Implement private reducer:
    ```python
    def _project_entries(entries: Iterable[JournalEntry]) -> State:
        """Fold an iterable of JournalEntry into a State. Pure function — no I/O.

        Test seam: importable as sdlc.state.projection._project_entries for property tests
        that drive the reducer with a Python iterable directly (skipping the file-read step).
        Not part of the stable public API; do NOT call from production code paths.
        """
        next_seq: int = 0
        epics: dict[str, Any] = {}
        for entry in entries:
            if entry.schema_version != _SCHEMA_VERSION:
                raise JournalError(
                    f"unknown schema_version={entry.schema_version} for kind={entry.kind};"
                    f" run sdlc migrate-v{entry.schema_version}",
                    details={
                        "step": "project_unknown_schema",
                        "schema_version": entry.schema_version,
                        "kind": entry.kind,
                        "monotonic_seq": entry.monotonic_seq,
                    },
                )
            # All known + unknown kinds advance the counter (forward-compat).
            next_seq = max(next_seq, entry.monotonic_seq + 1)
            # Only state_mutation on epic-N target_id touches epics in v1.
            if entry.kind == "state_mutation" and _EPIC_ID_PATTERN.match(entry.target_id):
                epics[entry.target_id] = dict(entry.payload)
        return State(next_monotonic_seq=next_seq, epics=epics)
    ```
    - **`max(next_seq, entry.monotonic_seq + 1)`** rather than `next_seq = entry.monotonic_seq + 1`: defensive against an out-of-order journal (which the reader would already have rejected via reader_invariant, but cheap belt-and-suspenders). Both yield the same result on a well-formed journal.
    - **`dict(entry.payload)`**: convert the `MappingProxyType`-wrapped payload (Story 1.7's `_freeze_payload` returns `MappingProxyType`) to a fresh `dict` so the State's epics value is mutable-on-the-outside (the State itself is `frozen=True`, but the payload-as-dict isn't a constraint we enforce yet — full schema in later stories).
    - **`State(next_monotonic_seq=..., epics=...)`** uses pydantic's standard construction; defaults for `schema_version=1` are taken automatically.
  - [ ] Implement public function:
    ```python
    def project_from_journal(journal_path: Path) -> State:
        """Pure-function state projection from journal (Decision B5).

        Returns State() defaults for missing/empty journal. Raises JournalError with
        message "unknown schema_version=N for kind=X; run sdlc migrate-vN" on schema drift.
        No I/O writes; no global mutation.
        """
        return _project_entries(iter_entries(journal_path))
    ```
    - The function is a one-liner because `iter_entries` already handles missing files (yields nothing → `_project_entries` returns `State()` defaults).
    - **No path validation here**: `iter_entries` is permissive about non-absolute paths (it just calls `journal_path.exists()`). The projection caller is responsible for path correctness — projection is a pure function that takes whatever the caller gives it. If we add path validation, mirror the Story 1.10 / 1.11 pattern: `if not journal_path.is_absolute(): raise JournalError(step="validate_path", ...)`. **Decision: do NOT add path validation in v1.** The projection is a read-only pure function; relative paths are sometimes useful in tests; the writer's path validation already covers production paths. Document this asymmetry inline.
  - [ ] Re-raise `JournalError` from `iter_entries` (the reader-invariant check) without wrapping — the projection is transparent to reader errors. Do NOT add a try/except that converts reader errors to projection errors; the caller can already distinguish via `details["step"]` ("reader_invariant" vs "project_unknown_schema").
  - [ ] **Forbidden patterns to flag at code-review time** (mirror the `WHAT TO REJECT` list from Story 1.11 review):
    - `Any` in type hints → use `Iterable[JournalEntry]`, `dict[str, Any]` (the `Any` here is unavoidable until State.epics gets a typed schema).
    - bare `except Exception` → narrow to `(ValueError, TypeError)` for schema; `OSError` for I/O; `JournalError` is intentional surface and should propagate.
    - Top-level `print()` calls → none. The reader emits stderr warnings on malformed lines; projection MUST NOT add its own.
    - Module-level mutable state → none. `_EPIC_ID_PATTERN`, `_KNOWN_KINDS`, `_SCHEMA_VERSION` are `Final` immutables.

- [ ] **Task 4: Wire `project_from_journal` into `sdlc.state` public API (AC: #1)**
  - [ ] Edit `src/sdlc/state/__init__.py` to add the import + `__all__` entry:
    - Add `from sdlc.state.projection import project_from_journal` after the existing platform-conditional imports (line 8-19 currently). The new import is **unconditional** because `projection.py` is cross-platform.
    - Add `"project_from_journal"` to the `__all__` tuple AT THE END (semantic-order: model → write-async → write-sync → read → projection). Do NOT alphabetize; the existing `# noqa: RUF022` comment covers this.
  - [ ] Run `uv run python -c "from sdlc.state import project_from_journal; print(project_from_journal)"` — confirm it imports clean (NOT a no-op stub) cross-platform.
  - [ ] On Windows, since `iter_entries` IS cross-platform per Story 1.11, `project_from_journal` works — verify with `uv run python -c "from sdlc.state import project_from_journal; from pathlib import Path; print(project_from_journal(Path('nonexistent.log')))"` returns `State(schema_version=1, next_monotonic_seq=0, epics={})`.
  - [ ] **DO NOT** add a Windows-stub fallback to `state/__init__.py` for `project_from_journal` — it's genuinely cross-platform. The existing Windows stubs cover `write_state_atomic`, `write_state_atomic_sync`, `read_state` only.

- [ ] **Task 5: Unit tests for `state/projection.py` (AC: #1, #3)**
  - [ ] Create `tests/unit/state/test_state_projection.py`. Use `tmp_path` fixture for a clean journal file per test. Mark all tests `@pytest.mark.unit`. Where a test depends on `append_sync` to populate the journal, also mark `@pytest.mark.skipif(sys.platform == "win32", ...)` — but for tests that drive `_project_entries` directly with a Python list of `JournalEntry` instances, skip the marker (those run cross-platform).
  - [ ] Test cases (cross-platform — drive `_project_entries` directly):
    - `test_project_empty_iterable_returns_default_state`: `_project_entries([])` → `State()` defaults (`next_monotonic_seq=0, epics={}`).
    - `test_project_single_state_mutation_on_epic_updates_epics`: build a `JournalEntry(kind="state_mutation", target_id="epic-1", payload={"phase": "1", "status": "in-progress"}, monotonic_seq=0, ...)`; assert resulting `State.epics["epic-1"] == {"phase": "1", "status": "in-progress"}` AND `State.next_monotonic_seq == 1`.
    - `test_project_state_mutation_on_non_epic_target_does_not_touch_epics`: `target_id="task-1.2.3"` → `epics == {}` AND `next_monotonic_seq == 1`. **This is forward-compat documentation**: when later stories add story-/task-projection, this test will be the canary that catches an inadvertent regression.
    - `test_project_advances_seq_for_all_known_kinds`: build entries with kinds `state_mutation, agent_dispatch, signoff, bypass_signoff, auto_mad_resolve, hook_bypass` (one each, seqs 0-5); assert `next_monotonic_seq == 6` AND `epics` has only the `state_mutation` entry (if its target_id is `epic-N`).
    - `test_project_unknown_kind_advances_seq_only`: build entry with `kind="totally_made_up_v2_kind"`, `target_id="epic-1"`; assert `next_monotonic_seq == 1` AND `epics == {}` (unknown kind is permissive — does NOT touch epics, even on epic-1 target_id, because the dispatcher key is the kind not the target).
    - `test_project_unknown_schema_version_raises_journal_error`: monkey-construct an entry-like-mapping that bypasses pydantic's `Literal[1]` (use `JournalEntry.model_construct(schema_version=2, ...)` — `model_construct` skips validation per pydantic v2); pass it to `_project_entries`; assert `JournalError` raised with `details["step"] == "project_unknown_schema"`, `details["schema_version"] == 2`, `details["kind"] == "<the-kind>"`, `details["monotonic_seq"] == <the-seq>`; assert error message exactly equals `"unknown schema_version=2 for kind=<the-kind>; run sdlc migrate-v2"`.
    - `test_project_halts_on_unknown_schema_version`: build a list of 5 entries where entries 0-2 are valid v1 entries and entry 3 has `schema_version=99`; assert `JournalError` raised; assert that NO partial state has been observable side-effect (the function never returns when it raises — test by asserting `pytest.raises(JournalError)` and inspecting nothing is yielded; this is implicit but document the test intent inline).
    - `test_project_max_seq_handles_out_of_order_defensively`: build entries with seqs `[0, 5, 2]` (out-of-order — would be rejected by the reader_invariant in `iter_entries`, but `_project_entries` accepts any iterable for testing); assert `next_monotonic_seq == 6` (max + 1, not last + 1). Document inline: this defensive max is belt-and-suspenders; in production, the reader rejects out-of-order seqs before projection sees them.
    - `test_project_returns_frozen_state`: `_project_entries([])` → result; assert `result.model_config["frozen"] is True` AND attempting `result.next_monotonic_seq = 99` raises `pydantic.ValidationError` (or `TypeError` depending on pydantic v2 version — use `pytest.raises((pydantic.ValidationError, TypeError, AttributeError))` for robustness).
    - `test_project_pure_no_module_state`: call `_project_entries([entry_a])` then call `_project_entries([entry_b])`; assert the second call's result depends ONLY on `entry_b` (no leakage from the first call's state). Implementation: assert `result_b.epics == {entry_b's epic_id: entry_b's payload}` (NOT containing entry_a's epic).
    - `test_project_payload_is_dict_not_mappingproxy`: build entry with `payload={"k": "v"}`; project; assert `type(state.epics["epic-1"]) is dict` (NOT `MappingProxyType`). Story 1.7 `_freeze_payload` wraps the input as `MappingProxyType`; projection must unwrap to plain dict so `state.json` serialization works (json.dumps doesn't handle `MappingProxyType` natively).
  - [ ] Test cases that need a real journal file (POSIX-only):
    - `test_project_from_journal_missing_file_returns_default_state`: `project_from_journal(tmp_path / "nonexistent.log")` → `State()` defaults. **Cross-platform**: this works on Windows too (no append_sync needed). Mark `@pytest.mark.unit` only, no platform skip.
    - `test_project_from_journal_empty_file_returns_default_state`: create `tmp_path / "journal.log"` via `Path.touch()`; `project_from_journal(...)` → `State()` defaults. **Cross-platform** — `iter_entries` handles empty files via the `if not stripped: continue` check.
    - `test_project_from_journal_round_trip_via_append_sync`: POSIX-only; `append_sync(entry, journal_path)` for 3 entries; `project_from_journal(journal_path)` → resulting state matches an oracle reduce of the same 3 entries. This is the integration smoke for AC1.
    - `test_project_from_journal_propagates_reader_invariant_error`: hand-craft a journal with seqs `[0, 1, 0]` (out-of-order line 3) using direct file writes (NOT append_sync — bypasses validate_seq); `project_from_journal(...)` → `JournalError(step="reader_invariant")` propagates from `iter_entries` without wrapping.
  - [ ] Per-package coverage gate: `sdlc.state` must reach ≥95% line coverage (mirrors Story 1.10 `state/atomic.py` 95% target).

- [ ] **Task 6: Implement hypothesis property test for replay invariant (AC: #2, #4)**
  - [ ] Create `tests/property/test_replay_invariant.py` with module docstring citing Decision B4 + B5 + Architecture §220 + epic AC block 2 (lines 713-716).
  - [ ] **Duplicate the strategy helpers** from `tests/property/test_journal_append_only.py` rather than import them — see Task 1 rationale. The duplicated strategies are:
    - `_iso_z_strategy()` — RFC3339 UTC strings.
    - `_sha256_strategy()` — `"sha256:" + 64-hex-char` strings.
    - `journal_entry_strategy` — `st.builds(JournalEntry, ...)` with the same field strategies as Story 1.11. **Constraint**: the `kind` strategy must sample from `_KNOWN_KINDS` plus a sentinel `"unknown_kind_for_drift_test"` (sampled at low probability, e.g., `st.one_of(st.sampled_from(list(_KNOWN_KINDS)), st.just("unknown_kind_for_drift_test").map(lambda x: x))`) so the property test exercises both the known-kind reducer path AND the unknown-kind-permissive path.
    - `monotonic_sequence_strategy` — produces a list of strictly-increasing seqs (composed with the entry strategy to inject seqs).
  - [ ] Define an **independent oracle reducer** at the top of the test file:
    ```python
    def _oracle_reduce(entries: list[JournalEntry]) -> State:
        """Independent oracle reducer for the replay invariant — must NOT import from
        sdlc.state.projection. Mirrors the same contract via a different implementation
        path so the property test provably exercises the contract end-to-end."""
        epics: dict[str, Any] = {}
        next_seq = 0
        for e in entries:
            if e.schema_version != 1:
                raise JournalError(...)  # same message format as projection
            next_seq = max(next_seq, e.monotonic_seq + 1)
            if e.kind == "state_mutation" and re.match(r"^epic-\d+$", e.target_id):
                epics[e.target_id] = dict(e.payload)
        return State(next_monotonic_seq=next_seq, epics=epics)
    ```
    The oracle is intentionally a separate code path (no import of `_project_entries`); two implementations of the same contract, exercised against each other on every hypothesis example — exactly the differential-test pattern Murat cited in Architecture §220.
  - [ ] **Property 1 — replay invariant** (`test_replay_invariant_holds_for_arbitrary_journal`):
    ```python
    @given(entries=monotonic_sequence_strategy(max_size=30))
    @settings(max_examples=1000, deadline=None,
              suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @pytest.mark.property
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — depends on append_sync")
    def test_replay_invariant_holds_for_arbitrary_journal(tmp_path, entries):
        journal_path = tmp_path / "journal.log"
        for k in range(0, len(entries) + 1):
            # Reset journal file for each k.
            if journal_path.exists():
                journal_path.unlink()
            for e in entries[:k]:
                append_sync(e, journal_path)
            actual = project_from_journal(journal_path)
            expected = _oracle_reduce(entries[:k])
            assert actual.model_dump(mode="json") == expected.model_dump(mode="json"), \
                f"replay invariant broken at k={k}: actual={actual.model_dump()} expected={expected.model_dump()}"
    ```
  - [ ] **Property 2 — schema-version drift fails-loud** (`test_unknown_schema_version_raises_journal_error`):
    ```python
    @given(entry=journal_entry_strategy, bad_version=st.integers().filter(lambda v: v != 1))
    @settings(max_examples=200, deadline=None)
    @pytest.mark.property
    def test_unknown_schema_version_raises_journal_error(entry, bad_version):
        # model_construct bypasses Literal[1] validation for the test
        bad_entry = entry.model_copy(update={"schema_version": bad_version}) if False else \
            JournalEntry.model_construct(**{**entry.model_dump(), "schema_version": bad_version})
        with pytest.raises(JournalError) as exc_info:
            _project_entries([bad_entry])
        assert exc_info.value.details["step"] == "project_unknown_schema"
        assert exc_info.value.details["schema_version"] == bad_version
        assert str(exc_info.value).startswith(
            f"unknown schema_version={bad_version} for kind={bad_entry.kind}"
        )
    ```
    Note: `entry.model_copy(update={"schema_version": ...})` would fail because `Literal[1]` rejects non-1 values via re-validation. Use `JournalEntry.model_construct(...)` which skips validation — this is the canonical pydantic v2 way to construct an "invalid" model for testing the second-line-of-defence check.
  - [ ] **Property 3 — projection idempotent under no-op replay** (`test_projection_idempotent`):
    ```python
    @given(entries=monotonic_sequence_strategy(max_size=20))
    @settings(max_examples=200, deadline=None)
    def test_projection_idempotent(entries):
        s1 = _project_entries(entries)
        s2 = _project_entries(entries)
        assert s1.model_dump(mode="json") == s2.model_dump(mode="json")
    ```
    Calling the reducer twice on the same input must produce equal results — no hidden state.
  - [ ] **Property 4 — module boundary invariant** (`test_state_module_depends_on_journal`): not a `@given`-decorated property — just a plain assertion run at test module import time. Keeps the boundary update from being silently reverted in a future refactor:
    ```python
    def test_state_module_depends_on_journal():
        from scripts.check_module_boundaries import MODULE_DEPS
        assert "journal" in MODULE_DEPS["state"].depends_on, \
            "MODULE_DEPS['state'] must include 'journal' (added by Story 1.12 — see ADR-015)"
    ```
    Tag with `@pytest.mark.unit` (NOT property — this is a static assertion, runs in unit tier).
  - [ ] **Smoke test variant — fast feedback for normal pytest runs**: define `test_replay_invariant_smoke` decorated with `@settings(max_examples=20, deadline=2000)` and `@pytest.mark.unit` (NOT `@pytest.mark.property` — gets picked up in the unit job, not gated behind the property job). Same body as Property 1, just smaller. Architecture intent: never let a regression in projection survive a normal `pytest -m unit` cycle for a full property job's wall-clock.
  - [ ] Per-test fixture: each `@given` function uses `tmp_path` (function-scoped); document the `function_scoped_fixture` health-check suppression rationale inline (see AC2).

- [ ] **Task 7: Update `MODULE_DEPS["state"]` to include `"journal"` (AC: #4)**
  - [ ] Edit `scripts/check_module_boundaries.py` line 51 (the `depends_on` field of `MODULE_DEPS["state"]`):
    - Change from: `depends_on=frozenset({"errors", "contracts", "concurrency", "config"}),`
    - Change to:   `depends_on=frozenset({"errors", "contracts", "concurrency", "config", "journal"}),`
  - [ ] Add a brief inline comment above the `"state"` entry: `# state depends on journal because state.json is a projection of the journal (Decision B5, ADR-015 / Story 1.12).`
  - [ ] Do NOT modify `MODULE_DEPS["journal"]` — journal continues to NOT depend on state. The directed edge `state → journal` is acyclic.
  - [ ] Run `uv run python -m scripts.check_module_boundaries` with no args (default scans `src/sdlc/`) — expect 0 violations. Run `uv run python scripts/check_module_boundaries.py src/sdlc/state/` — confirm `state/projection.py`'s `from sdlc.journal import iter_entries` is now allowed. Without the boundary update, this import would fail validation.
  - [ ] Confirm the `_validate_module_deps_keys` invariant test (line 164-170) still passes — `"journal"` is a known module so adding it to state's deps does not introduce a typo.

- [ ] **Task 8: Add ADR-015 + update documentation (AC: all)**
  - [ ] Create `docs/decisions/ADR-015-state-projection-from-journal.md` with sections: Status: Accepted; Date: 2026-05-08; Context (Decision B5 from Architecture §349 — journal is source of truth, state is projection; Decision B4 from §348 — full replay from journal[0] for v1; Architecture §220 — Murat's added invariant `replay(journal[0:k]) == state_at_step_k`; epic AC2 line 716 — ≥1000 hypothesis examples per CI run); Decision (the pure-function `project_from_journal` reading via `iter_entries`; per-kind reducer dispatch with `state_mutation` + `epic-N target_id` pattern as the only v1-effective combination; schema_version-drift fail-loud with `"unknown schema_version=N for kind=X; run sdlc migrate-vN"` message contract; MODULE_DEPS["state"] gains "journal" dependency); Consequences (forward-compat: v2 schemas will need a migration command named `sdlc migrate-vN` — the message contract reserves this name; permissive unknown-kind reducer means future kinds can be added without breaking replay of historical journals; `_project_entries` is a private test seam that future stories MAY rely on but MUST treat as semi-stable — moving it would require a coordinated update to property tests). Cite ADR-013 (atomic state write protocol) and ADR-014 (append-only journal protocol) as the precedents this story builds on.
  - [ ] Update `docs/decisions/index.md`: add row `| ADR-015 | State projection from journal | Accepted | 2026-05-08 |` (or matching the existing row format). The ADR-015 number is the next available — confirmed via `ls docs/decisions/ADR-*.md` at story-authoring time (last existing was ADR-014 from Story 1.11).
  - [ ] Update `docs/CODEMAPS/state.md` (if exists) or create a stub citing this story's deliverables (`projection.py`, the property test, ADR-015, the MODULE_DEPS update). Cross-link to `docs/CODEMAPS/journal.md` (created by Story 1.11).
  - [ ] **No new pytest markers needed** — `unit` and `property` markers already exist (`pyproject.toml` from Story 1.10).
  - [ ] **No mypy override needed** — `state/projection.py` is cross-platform pure Python with no `Any` leaks beyond `dict[str, Any]` for the `epics` field (which is already `Any` in `state/model.py`). Run `uv run mypy --strict src/sdlc/state/projection.py` and confirm 0 errors.
  - [ ] **No coverage `omit` needed** — `state/projection.py` is cross-platform; runs on Linux/macOS/Windows alike.

- [ ] **Task 9: Validate full quality gates green (AC: all)**
  - [ ] Run `uv run ruff check src/ tests/ scripts/` → 0 errors.
  - [ ] Run `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [ ] Run `uv run mypy --strict src/` → 0 errors. The new `state/projection.py` MUST type-check under `--strict` (no `Any` leaks; `Iterable[JournalEntry]` typed correctly; `_project_entries` return type annotated as `State`).
  - [ ] Run `uv run pre-commit run --all-files` → all hooks pass including `boundary-validator` (which now validates the new state→journal edge), `journal-append-only-validator` (Story 1.11; should remain green — projection.py reads via `iter_entries`, never opens journal directly), `state-write-protocol-validator` (Story 1.10), `secret-hardcode-validator`, `mypy-strict`, `ruff-check`, `ruff-format`.
  - [ ] Run `uv run pytest tests/unit/state/test_state_projection.py` → all pass; per-package coverage for `sdlc.state.projection` ≥95%.
  - [ ] Run `uv run pytest tests/property/test_replay_invariant.py` → 1000+ examples pass per `@given`-decorated property (Property 1 main + Property 2 + Property 3 + smoke; Property 4 is a unit-tier sanity check, not gated by `max_examples`).
  - [ ] Run global `uv run pytest --cov=src --cov-fail-under=90` → passes.
  - [ ] Verify `scripts/check_module_boundaries.py` recognizes the new `state → journal` edge: `uv run python scripts/check_module_boundaries.py src/sdlc/state/projection.py` → 0 violations (the file imports `from sdlc.journal import iter_entries` which is now allowed).
  - [ ] Verify `scripts/check_no_journal_mutation.py` does NOT flag `state/projection.py` (the projection only reads via `iter_entries`; does not call `open(journal_path, ...)`, `Path(journal_path).write_text(...)`, etc.).
  - [ ] Verify `scripts/check_no_direct_state_writes.py` does NOT flag `state/projection.py` (projection produces a NEW `State` instance via `State(next_monotonic_seq=..., epics=...)`; it does NOT call `open(state_path, "w")` or similar — it doesn't write at all).

## Dev Notes

### Why this story exists (FR + NFR + Decision mapping)

- **FR35 — `sdlc rebuild-state`**: `project_from_journal` is the substrate for FR35. Story 1.12 ships the pure projection primitive; FR35's `cli/rebuild_state.py` (Story 1.20) USES this function but is out of scope here. Architecture §1059 lists `project_from_journal` and `rebuild_state` as separate state/ public APIs — confirming the primitive/CLI split.
- **NFR-REL-2 — replay invariant under property test**: epic AC2 specifies ≥1000 hypothesis examples asserting `replay(journal[0:k]) == state_at_step_k`. The property test in Task 6 is the materialization of this invariant. Architecture §220 (Murat's added invariant) is the same constraint — this story is its first concrete realization.
- **Decision B4 — full replay from journal[0] for v1 (Architecture §348)**: snapshot caching is deferred. v1 always replays the full journal; performance optimization is a future story. The pure-function design makes snapshot caching trivial to add later (memoize on `(journal_path, mtime)` or wrap in a checkpoint reader). Document this forward-compat in ADR-015.
- **Decision B5 — state as projection of journal (Architecture §349)**: this story is the **literal materialization** of Decision B5. Before Story 1.12, the architecture says "state is a projection" but no code computes the projection. After Story 1.12, the function exists and is property-test verified.
- **Decision F3 — per-contract schema versioning (Architecture §382)**: the schema_version-drift refusal in AC3 is the per-contract version policy applied to `JournalEntry`. The error message names the migration command (`sdlc migrate-vN`) — even though `cli/migrate.py` is FR49 (deferred), the contract is established here.
- **Architecture §220 — replay invariant property**: "catches replay-divergence from semantic schema drift, which the existing append-only property cannot detect." Story 1.11's append-only property test asserts byte-identity of journal lines; Story 1.12's replay invariant asserts semantic-identity of state across replays. The two are complementary — neither replaces the other.
- **Architecture §1059 — state's public API includes `project_from_journal`**: the architecture's module table is the source of truth for what state/ exposes. Story 1.12 ships exactly this API symbol.
- **Architecture §845 — `state/projection.py` file location**: the planned file path is canonical. Story 1.12 creates this file.
- **Architecture §349 + §1059 ≠ MODULE_DEPS reality**: the boundary table at `scripts/check_module_boundaries.py:50-53` did NOT originally list `journal` as a dep of state — but the architecture clearly intends state to be a projection of journal. AC4 + Task 7 reconcile this by adding `"journal"` to state's `depends_on`. Document the architectural-intent-vs-boundary-table discrepancy in ADR-015's Context section, naming this story as the resolution.

### File set this story creates / modifies

**New files (created):**

- `src/sdlc/state/projection.py` — pure projection function (~100-150 LOC; cap 400)
- `tests/unit/state/test_state_projection.py` — projection unit tests (~12 test cases)
- `tests/property/test_replay_invariant.py` — hypothesis property test (4 properties)
- `docs/decisions/ADR-015-state-projection-from-journal.md` — new ADR

**Modified files:**

- `src/sdlc/state/__init__.py` — add `from sdlc.state.projection import project_from_journal`; add `"project_from_journal"` to `__all__` tuple (semantic order, end-of-tuple)
- `scripts/check_module_boundaries.py` — add `"journal"` to `MODULE_DEPS["state"].depends_on` (line 51); add inline comment citing ADR-015 / Story 1.12
- `docs/decisions/index.md` — add ADR-015 row

**Files NOT modified (invariant — break-glass if any of these change):**

- `src/sdlc/journal/{__init__,writer,reader}.py` — Story 1.11 deliverables, used as-is via `from sdlc.journal import iter_entries`. No edits.
- `src/sdlc/state/{__init__,model,atomic}.py` (atomic.py / model.py specifically) — not edited by this story. The init.py edit is only to add the new import + `__all__` entry; no logic changes to the existing platform-conditional block.
- `src/sdlc/contracts/journal_entry.py` — Story 1.7 deliverable; used as-is. No edits to the contract.
- `src/sdlc/errors/base.py` — `JournalError` already exists with code `ERR_JOURNAL`. Use as-is.
- `MODULE_DEPS["journal"]` — journal continues to NOT depend on state. Acyclic graph preserved.
- `.pre-commit-config.yaml` — no new hooks (the boundary-validator already covers the MODULE_DEPS edit; the journal-mutation linter from Story 1.11 already covers projection.py since it doesn't write to journal).

### Pure function semantics — what "no I/O writes" means precisely

**Allowed inside the projection function:**
- File reads (`iter_entries` opens the journal file in read-only mode).
- Stderr emission via `iter_entries` malformed-line warning (originates inside `journal/reader.py`, NOT inside projection).
- Constructing new `State` and `dict` objects (these are local-stack allocations, not side effects).
- Re-raising errors from `iter_entries` (transparent to the caller).

**Forbidden inside the projection function:**
- File writes (`open(p, "w")`, `Path(p).write_text(...)`, `os.write(fd, ...)`).
- Network I/O (no requests, sockets, etc. — would not arise in this scope but documented for completeness).
- Spawning subprocesses (`subprocess.run`, `os.fork`, etc.).
- Mutating module-level state (no `global`, no `nonlocal` writes to a captured variable).
- Calling `print()` or `logger.info(...)` to stdout (stderr warnings from the reader are bookkeeping, not projection output).
- Time-dependent behavior (`datetime.now()`, `time.time()`) — projection must produce the same output for the same input regardless of when called.

**Why this matters**: pure functions are trivially memoizable (Story 1.20 `sdlc rebuild-state` may cache projection results); composable in the auto-loop (Story 4.1) without surprising disk-state interactions; and provably correct (the property test's `replay(journal[0:k]) == state_at_step_k` invariant only holds for pure projection).

### Why the v1 reducer is so minimal (and the forward-compat plan)

The current `State` model has only three fields: `schema_version`, `next_monotonic_seq`, `epics: dict[str, Any]`. The reducer therefore only mutates `epics` — and only for `state_mutation` entries with `target_id` matching `^epic-\d+$`. This is **deliberately minimal** because:

1. **Story 1.12's contract is the projection FRAMEWORK**, not the full state schema. Adding fields to `State` (story-status, task-stage, signoff-records, etc.) is the work of later stories (engine/scanner.py, signoff/, etc.). The framework — pure function, kind dispatch, schema-version drift detection, replay invariant — must be cemented FIRST so that adding fields later is mechanical (extend the reducer; the property test catches divergence).
2. **The property test will catch any regression** when later stories extend the reducer. The oracle reducer is co-located with the test; updating the reducer means updating the oracle in the same commit, and the differential test guarantees the two stay in sync.
3. **Permissive unknown-kind handling is forward-compat**: when a future story adds `kind="dora_metric_recorded"`, replaying a journal that contains historical (pre-add) entries of that kind will not break — the projection advances `next_monotonic_seq` and ignores the unknown kind. This is the correct semantic for unknown-kind in a single-version schema (Decision F3 says version drift is loud; kind drift within a version is permissive).
4. **`_KNOWN_KINDS` documents the v1 surface**: the constant is enumerated for human readers and for static analysis. It is NOT used to reject unknown kinds (see point 3) — it documents what the reducer recognizes, in the same spirit as `_CANONICAL_WRITE_API` from Story 1.10.

When a later story (e.g., 2A-12 `sdlc-signoff` or 1.20 `sdlc rebuild-state`) needs to project signoffs into `state.signoffs`, that story will: (a) extend `State` with the `signoffs` field; (b) extend the reducer's `state_mutation` branch (or add a new branch for `kind="signoff"`); (c) update the oracle in the property test; (d) update unit tests. The framework laid down in Story 1.12 makes this a well-trodden path.

### Why MODULE_DEPS["state"] gains "journal" (and not the reverse)

**Direction**: `state → journal` (state can import from journal; journal cannot import from state).

**Rationale**:
- **Decision B5 (Architecture §349)**: state is a projection OF journal. By definition, the projection knows about its source — it's a one-way dependency.
- **Acyclicity**: `journal/` does not depend on `state/` today. Adding `journal` to state's `depends_on` keeps the dep graph acyclic. The `_validate_no_cycles` check in `check_module_boundaries.py` will pass.
- **Architecture §1059** explicitly lists `project_from_journal` as state's public API — implying state must read journal. The original boundary table missed this dep edge (or it was implicit; either way, this story makes it explicit).
- **Single point of truth for journal access**: by importing `iter_entries` (rather than opening journal files directly), `state/projection.py` automatically benefits from the reader-invariant monotonicity check (Story 1.11 `journal/reader.py:50-61`). If projection bypassed `iter_entries` and used raw JSONL parsing, that invariant would silently disappear. The MODULE_DEPS update is therefore not just a paperwork change — it's an architectural alignment.

**Why NOT bypass the dep update with raw JSONL parsing**: yes, technically `state/projection.py` could call `JournalEntry.model_validate_json(line)` directly via `from sdlc.contracts.journal_entry import JournalEntry`, sidestepping `journal/`. But:
- Loses the reader-invariant check (would have to be re-implemented in projection — duplication risk).
- Loses the malformed-line warning behavior — projection would either silently skip or raise on malformed lines, neither matching the reader's policy.
- Loses the file-not-found / empty-file fallthrough behavior — would have to re-implement.
- A future story changing the reader's behavior (e.g., adding line-number tracking) would have to change projection too, in lockstep.

The MODULE_DEPS update is the cheaper, more aligned answer.

### Property-test design — why an in-test oracle reducer

The replay invariant is the kind of contract that benefits from differential testing: two independent implementations of the same spec, asserted equal on every example. Standard test patterns:

- **A test that just checks `project_from_journal` against a hard-coded expected output** would pass even if both the projection and the test had the same bug.
- **A test that imports `_project_entries` and asserts it produces the right output** is structurally identical to the implementation — no differential.
- **A test with an in-test oracle** (`_oracle_reduce`) is differential: the property fails if EITHER implementation diverges from the spec. Since the property runs ≥1000 examples per CI run, divergence is caught quickly.

Murat (architect) explicitly named this pattern at Architecture §220 ("Catches replay-divergence from semantic schema drift") — Story 1.12 is the realization. Document the pattern's rationale in `test_replay_invariant.py`'s module docstring so future contributors don't refactor the oracle to "just call `_project_entries`" thinking they're DRY-ing up duplicate code.

### Previous story intelligence — Stories 1.10 + 1.11

Patterns to mirror exactly (these were code-review-validated through 1.10's 9 patches and the 1.11 dev cycle currently in progress):

- **`from __future__ import annotations`** at top of every new `.py` file in `state/`.
- **Semantic-order `__all__`** with `# noqa: RUF022` (ruff would otherwise sort alphabetically).
- **Cross-platform vs POSIX-only**: `state/projection.py` is **cross-platform** (no `fcntl`, no `O_APPEND`) — no POSIX gate needed. Mirror Story 1.11's `journal/reader.py` (cross-platform reader). Contrast with `state/atomic.py` (POSIX-only writer).
- **`Final[...]` constants** for module-level immutables: `_EPIC_ID_PATTERN`, `_KNOWN_KINDS`, `_SCHEMA_VERSION`. Mirror `state/atomic.py:STATE_FILE_NAME`, `journal/writer.py:JOURNAL_LOCK_SUFFIX`.
- **Narrow exception catches**: `(ValueError, TypeError)` for schema; `OSError` for I/O (n/a here — projection has no direct I/O); `JournalError` is intentional surface and propagates. Do NOT catch bare `Exception` (Story 1.10 patch lessons).
- **Pure functions for protocol bodies**: mirror Story 1.10's `_write_protocol_body` and Story 1.11's `_append_protocol_body`. The projection's `_project_entries` follows the same convention.
- **Test-seam private functions**: `_project_entries` is single-underscore-prefixed, importable for tests, NOT in `__all__`. Mirror Story 1.10's `_canonicalize_state` (used by tests via direct import from `sdlc.state.atomic`).
- **`@pytest.mark.skipif(sys.platform == "win32", ...)`** on tests that need POSIX features (here: tests that call `append_sync` to populate the journal). Mirror Story 1.11's property-test marker pattern.
- **`@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])`** on the main hypothesis property — mirrors Story 1.11 + adds `function_scoped_fixture` suppression for the `tmp_path` fixture (see AC2 rationale).
- **mypy `--strict`**: no `Any` leaks beyond what the State model already declares (`epics: dict[str, Any]`). Use `Iterable[JournalEntry]`, `Iterator[JournalEntry]`, `Final[re.Pattern[str]]`.
- **Test classes for ≥95% coverage on Windows** (Story 1.10 review patch pattern, used in `check_no_direct_state_writes.py` tests via `TestVisitorDirect`). Not relevant here — `state/projection.py` is small enough that direct unit tests + the property smoke test reach 95% trivially.

Code-review feedback from Stories 1.10 + 1.11 to pre-empt:
- Be explicit about exception chaining (`raise JournalError(...) from e` where applicable; here, `_project_entries` re-raises `iter_entries` errors transparently — no chaining needed).
- Avoid `Any` in type hints (use `Iterable[JournalEntry]`, `dict[str, Any]` where unavoidable, `Final[T]` for constants).
- Verify `mypy --strict` passes BEFORE committing.
- Use `(flags & os.O_ACCMODE) == os.O_WRONLY` access-mode check pattern (n/a here — no fd manipulation).
- Narrow exception catches; do NOT swallow programmer errors.
- For property tests: prefer `@settings(deadline=None, ...)` over per-`@given` deadline; suppress `HealthCheck.too_slow` and `HealthCheck.function_scoped_fixture` with documented rationale.

### Git intelligence — last 5 commits

```
2f4322d feat: implement atomic state write protocol with chaos tests (Story 1.10)
ce351c5 chore: ignore graphify output and config files
99c8f78 chore: update skills, add Story 1.9, graphify output, and project config
b378b5a fix: apply code-review patches for Story 1.8 config module
1042fc1 feat: implement config module with validation (Story 1.8)
```

**Notable**: Story 1.11 has NOT been committed yet (status `in-progress` in sprint-status.yaml). The `src/sdlc/journal/` files are on disk but uncommitted. Story 1.12 work depends on these uncommitted files — proceed assuming the disk state is the source of truth (NOT git HEAD). If 1.11 is reverted before 1.12 ships, this story breaks.

**Recommendation**: when the dev agent picks up this story, verify Story 1.11 disk state matches the files referenced in this story's References section (`src/sdlc/journal/{__init__,writer,reader}.py`). If 1.11 is in a different state (re-implemented, partially reverted, etc.), pause and reconcile — the story's assumed surface is the 1.11 deliverables.

**Commit pattern to follow**:
- One `feat: implement state projection from journal (Story 1.12)` commit covering all of: `src/sdlc/state/projection.py`, `src/sdlc/state/__init__.py` edit, `tests/unit/state/test_state_projection.py`, `tests/property/test_replay_invariant.py`, `scripts/check_module_boundaries.py` edit (the MODULE_DEPS update is part of the same logical change), `docs/decisions/ADR-015-*.md`, `docs/decisions/index.md`.
- Apply review patches in a follow-up `fix:` commit if needed (Story 1.10 + 1.11 precedent).

### Latest tech information

- **Python 3.10+** target (Architecture-stated minimum). All language features used (`Iterable[JournalEntry]`, `dict[str, Any]`, `Final[re.Pattern[str]]`) are stable.
- **pydantic v2** (Story 1.7+ on disk at `src/sdlc/contracts/`). Use `model_dump(mode="json")` for canonical serialization; use `model_construct(...)` to bypass validation when constructing test entries with invalid `schema_version` (Property 2's drift test). `model_construct` was added in pydantic v2 specifically for this kind of "I know better than the validator" test path.
- **`State.model_dump(mode="json")` vs `State.model_dump()`**: prefer `mode="json"` for assertion comparisons because it normalizes types (tuples → lists, datetime → str) — matches the canonical-JSON serialization used by `state/atomic.py`. `mode="json"` is the v1 contract for state-equality assertions across the codebase.
- **hypothesis 6.x**: `@settings(max_examples=N, deadline=None)` syntax stable. `st.builds(JournalEntry, ...)` works for pydantic v2 models that accept kwargs (`JournalEntry` does). `HealthCheck.function_scoped_fixture` is the canonical suppression for `tmp_path`-using property tests.
- **`re.compile(pattern)`** for `_EPIC_ID_PATTERN`: pre-compiled at module load; mypy-friendly type `Final[re.Pattern[str]]`. The regex `^epic-\d+$` matches `epic-0`, `epic-1`, ..., `epic-99`, etc. — does NOT match `epic-1.2.3` (story id), `task-1.2.3` (task id), `epic_1` (underscore — non-canonical).
- **`MappingProxyType` from `types`**: the `JournalEntry.payload` field is wrapped via Story 1.7's `_freeze_payload` validator. To get a mutable dict back: `dict(entry.payload)` — copies the proxy's items into a fresh dict. The projection's `epics[entry.target_id] = dict(entry.payload)` line is the canonical unwrap.
- **`pytest.raises(JournalError) as exc_info`**: pydantic v2's `JournalError` is a subclass of `Exception` (via `SdlcError` from `errors/base.py`). The standard pytest pattern works without extra ceremony. `exc_info.value.details["step"]` accesses the structured-error fields.

### Project Structure Notes

- **Alignment with unified project structure**: this story creates `state/projection.py` per Architecture §845. The architecture lists six files for `state/`: `model.py`, `atomic.py`, `reader.py`, `projection.py`, `rebuild.py`, `transitions.py`. Story 1.12 ships `projection.py`; `reader.py` (hash-verified read), `rebuild.py` (FR35 CLI substrate), `transitions.py` (epic/story/task state machines) are deferred to later stories. Currently on disk: `model.py`, `atomic.py`. After Story 1.12: + `projection.py`.
- **No conflict with architecture**: every file path in Task 1's "New files" list lives under a directory the architecture has already declared. Tests are mirrored from `src/sdlc/state/projection.py` to `tests/unit/state/test_state_projection.py` per the canonical "tests/unit/ mirrors src/sdlc/" structure (Architecture §983).
- **Pyproject markers**: `unit` and `property` marks already exist. No new marks needed.
- **CI workflow**: NO new CI job — the property test piggybacks on the existing `property` job; the smoke test piggybacks on the existing `unit` job. Boundary-validator runs in pre-commit and CI; the MODULE_DEPS edit is automatically picked up.

### Why deferred from this story

These are explicitly NOT in scope for Story 1.12 — flag if they creep in during implementation:

- **Hash verification on read** (`state/reader.py:read_state_with_hash` or similar). Architecture §844 lists `state/reader.py` as a separate file; not shipped here. Story 1.12's `read_state` (currently in `state/atomic.py`) does not hash-verify — that's a future story.
- **`sdlc rebuild-state` CLI** (`cli/rebuild_state.py`, FR35). Uses `project_from_journal` from this story but is its own story (1.20).
- **Snapshot caching for projection** (Architecture §326 — Decision B4 defers caching to v1.x). The pure-function design makes caching trivial to add later; this story keeps the function uncached for clarity and provably-correct semantics.
- **Story / task projection** (kinds that touch `state.stories` and `state.tasks` once those fields exist). Reducer is currently `state_mutation` + `epic-N` only; later stories extend.
- **Hash chain validation across consecutive entries** (`entry[i+1].before_hash == entry[i].after_hash`). Architecture §347-§349 implies this is part of the audit chain integrity. Not shipped here — `JournalEntry` carries `before_hash`/`after_hash` fields but the projection does NOT validate they form a chain. Add to ADR-015 Consequences as a known v1 gap.
- **`migrate-vN` CLI command** (FR49). The error message references `sdlc migrate-vN` as a forward-contract; the actual CLI is a later story.
- **State diff visualizer** (Architecture §206 — for debug observability). Out of v1 scope.
- **Performance benchmarks** for projection over large journals. `iter_entries` is O(N) in journal size; for journals of millions of entries this becomes slow. Optimization deferred until empirical evidence (DORA dashboards in Epic 5) shows it matters.
- **Concurrent-projection safety** — the projection is pure and side-effect-free, so it's trivially safe to call from multiple threads/processes. No locks needed; no test coverage of concurrent projection in this story.
- **Migration from journal v1 to v2** — the schema_version-drift error names the migration command but does NOT implement it. Migration is a separate story (FR49).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.12] (lines 699-722) — story spec, AC blocks
- [Source: _bmad-output/planning-artifacts/architecture.md#Replay-Invariant] (line 220) — Murat's added invariant `replay(journal[0:k]) == state_at_step_k`
- [Source: _bmad-output/planning-artifacts/architecture.md#Decisions] (line 348 — Decision B4 full replay; line 349 — Decision B5 state as projection of journal; line 382 — Decision F3 per-contract schema versioning)
- [Source: _bmad-output/planning-artifacts/architecture.md#Source-Tree] (lines 841-848) — full `state/` file layout: model.py, atomic.py, reader.py, projection.py, rebuild.py, transitions.py
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Dependency-Table] (line 1059) — `state/` public API includes `project_from_journal`
- [Source: _bmad-output/planning-artifacts/architecture.md#FR-Mapping] (line 1156 — FR30 atomic write; line 1158 — FR32 hash-drift validation; line 1187 — FR35 rebuild-state mapped to `state/rebuild.py`)
- [Source: _bmad-output/planning-artifacts/architecture.md#Five-Wire-Format-Schemas] (lines 595-606) — `JournalEntry` v1 schema; kinds enumeration
- [Source: _bmad-output/planning-artifacts/architecture.md#Test-File-Layout] (lines 991-995) — `tests/property/test_replay_invariant.py` is one of four planned property tests
- [Source: _bmad-output/planning-artifacts/architecture.md#Roadmap] (line 1405) — temporal-integrity substrate mentions both `test_replay_invariant.py` and `test_journal_append_only.py`
- [Source: src/sdlc/contracts/journal_entry.py] (lines 1-54) — `JournalEntry` pydantic v2 model on disk; consume as-is. `schema_version: Literal[1] = 1` is the dual-defence reference for AC3.
- [Source: src/sdlc/state/model.py] (lines 1-23) — `State` minimal model on disk: `schema_version`, `next_monotonic_seq`, `epics`. Story 1.12 does NOT modify.
- [Source: src/sdlc/state/__init__.py] (lines 1-29) — current `__all__` tuple; Story 1.12 appends `project_from_journal`.
- [Source: src/sdlc/state/atomic.py] (entire file, ~245 LOC) — Story 1.10 reference patterns: protocol body factoring, body-exception preservation, `_canonicalize_state` + `_normalize_strings`. Reference for code style + helper-function decomposition (no protocol body needed in projection — it's a pure read).
- [Source: src/sdlc/journal/reader.py] (lines 1-81) — Story 1.11 deliverable: `iter_entries`, `iter_after`, reader-invariant check at lines 50-61. The projection consumes `iter_entries`.
- [Source: src/sdlc/journal/__init__.py] (lines 1-32) — Story 1.11 deliverable: `iter_entries` is exported from `sdlc.journal`.
- [Source: src/sdlc/errors/base.py] (line 45) — `JournalError` with code `ERR_JOURNAL`, `exit_code=2`.
- [Source: scripts/check_module_boundaries.py] (lines 50-53) — `MODULE_DEPS["state"]` current state. Story 1.12 Task 7 edits line 51.
- [Source: scripts/check_no_journal_mutation.py] — Story 1.11 deliverable; verify it does NOT flag `state/projection.py`.
- [Source: scripts/check_no_direct_state_writes.py] — Story 1.10 deliverable; verify it does NOT flag `state/projection.py`.
- [Source: tests/property/test_journal_append_only.py] — Story 1.11 property test; reference for `journal_entry_strategy` and `monotonic_sequence_strategy` patterns to duplicate.
- [Source: docs/decisions/ADR-013-atomic-state-write-protocol.md] — atomic write protocol ADR (Story 1.10).
- [Source: docs/decisions/ADR-014-append-only-journal-protocol.md] — journal append protocol ADR (Story 1.11).
- [Source: _bmad-output/implementation-artifacts/1-10-atomic-write-protocol-chaos-tests.md] — Story 1.10 patterns + review feedback to pre-empt.
- [Source: _bmad-output/implementation-artifacts/1-11-append-only-journal-property-test.md] — Story 1.11 patterns; this story builds directly on its deliverables.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (BMAD dev-story workflow)

### Debug Log References

### Completion Notes List

### File List

### Review Findings
