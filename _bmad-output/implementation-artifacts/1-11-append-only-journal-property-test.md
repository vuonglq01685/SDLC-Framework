# Story 1.11: Append-Only Journal + Append-Only Property Test

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user trusting the audit chain,
I want `journal/writer.py` implementing append-only JSONL writes (with reader iter helpers), backed by a hypothesis property test that proves the framework never mutates an existing line and a static linter that rejects any `seek()`/`write_at_offset` pattern,
so that the journal can serve as the single source of truth for state replay (FR31, NFR-REL-2, NFR-OBS-1, Decision B5).

## Acceptance Criteria

**AC1 — Append protocol implementation (epic AC block 1)**

**Given** Story 1.10 complete (`write_state_atomic` + `file_lock` shipped, `JournalEntry` pydantic contract from Story 1.7 already on disk at `src/sdlc/contracts/journal_entry.py`, `JournalError` already declared in `src/sdlc/errors/base.py`),
**When** I call `await journal.append(entry, journal_path)` with a valid `JournalEntry`,
**Then** the executable protocol is exactly:

1. acquire `flock(<journal>.lock)` via the Story 1.9 `file_lock(...)` async context manager (sentinel file, NOT the journal itself — Decision B2 per-file flock granularity, mirroring `state/atomic.py:STATE_LOCK_SUFFIX`).
2. canonicalize `entry` via `_canonicalize_entry(entry)` → `bytes`: `payload = entry.model_dump(mode="json")` → recursively NFC-normalize every string value via `unicodedata.normalize("NFC", s)` → `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"` (per Architecture §501-§508 and §513 — terminating `\n` is REQUIRED for JSONL, distinct from the hash-canonicalization variant which omits it).
3. open journal for append: `fd = os.open(str(journal_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)`. **Must use `O_APPEND`** (kernel-enforced atomic-to-EOF semantics) — NOT `os.O_WRONLY` with manual `os.lseek(fd, 0, os.SEEK_END)` (race-prone). NOT the `open()` builtin in mode `"a"` (we follow the `state/atomic.py:69-71` pattern of `os.open` for explicit flag visibility and to bypass any test-side monkeypatching of builtins).
4. drain canonical bytes via a short-write loop: `while offset < len(buf): written = os.write(fd, buf[offset:]); if written == 0: raise JournalError(... step="write_journal" ...); offset += written` (mirrors `state/atomic.py:_write_bytes`). Architecture §493 forbids any other code path from opening the journal for write.
5. `os.fsync(fd)` — durability of the appended bytes.
6. `os.close(fd)`.
7. release `flock` (handled automatically on `__aexit__` of `file_lock`).

**And** unit tests in `tests/unit/journal/test_journal_append_protocol.py` verify each step in isolation: tmp file is opened in `O_APPEND` mode (assert `(flags & os.O_ACCMODE) == os.O_WRONLY` AND `(flags & os.O_APPEND) != 0` — pattern lifted from Story 1.10's review patch on `os.O_RDONLY == 0` test theatre); canonical bytes match `entry.model_dump(mode="json")` round-tripped through canonical JSON; fsync is called once per append (verified via `pytest`-mocking `os.fsync` to record fd); flock is held during the protocol (verified via `lock_registry()` introspection from Story 1.9); flock is released after the protocol exits.
**And** the public API exported from `sdlc.journal` is exactly: `append` (async), `append_sync` (sync — for property/chaos tests; see Dev Notes "Sync vs async API reconciliation"), `iter_entries` (sync iterator), `iter_after` (sync iterator with `monotonic_seq` predicate).
**And** `append` is `async def` (matches Story 1.9 + 1.10 async-default direction); the thin sync convenience `append_sync` is provided for property tests / chaos tests that run inside `subprocess`-killed children where no event loop exists, and it MUST share its protocol body with the async path (no logic divergence — see Dev Notes "Sync vs async API reconciliation"). `append_sync` MUST raise `JournalError` if called from inside a running event loop (footgun guard mirroring `state.atomic.write_state_atomic_sync`).
**And** `append` accepts a `JournalEntry` pydantic model (from `sdlc.contracts.journal_entry`); does NOT accept arbitrary `dict` — `dict` callers must pass `JournalEntry.model_validate(d)` first.
**And** any failure path (OSError on open / write / fsync / close, flock unavailable, canonicalization error) raises `JournalError` (already in `errors/base.py:45` with code `ERR_JOURNAL`) with `details={"path": str(journal_path), "errno": int, "step": "<protocol-step-name>", "monotonic_seq": int}` chained via `raise ... from e`. The body-exception preservation pattern from Story 1.9 + Story 1.10 (`body_exc` capture before `os.close` in `finally`) MUST be applied so a cleanup OSError does not mask the real append error.
**And** the protocol body validates that `entry.monotonic_seq` is strictly greater than the highest `monotonic_seq` already present in the file (read via the AC1 Step 2.5 below). Equality or regression raises `JournalError` with `details={"step": "validate_seq", "supplied": entry.monotonic_seq, "expected_min": highest + 1}`. **Rationale**: epic AC1 line 685 — "the file's monotonic_seq is strictly greater than the previous entry's". Architecture §520: counter advances atomically; `journal.append` is the second-line-of-defence monotonicity check (the first being the state-write that incremented `next_monotonic_seq`). The check uses `iter_entries(journal_path)` if the file exists; treats `0` as the floor for an empty/missing file.

**Step 2.5 — monotonicity precondition (inserted between Step 1 and Step 2 above)**: while holding the lock, before canonicalization, call a private `_read_highest_seq(journal_path) -> int` helper that returns the maximum `monotonic_seq` across all parseable entries (or `-1` if file empty/missing). If `entry.monotonic_seq <= highest`, raise `JournalError(step="validate_seq", ...)`. This single read happens inside the lock so two concurrent appenders can't both read `N`, both compute `N+1`, and both succeed (lock serializes).

**AC2 — Append-only property test: file grows-only, line bytes immutable (epic AC block 2)**

**Given** the property test module at `tests/property/test_journal_append_only.py`,
**When** hypothesis generates arbitrary append sequences interleaved with reads,
**Then** for every read of any line N (1-indexed), the content is **byte-identical** to the bytes that were originally appended at line N.
**And** the file size only ever grows monotonically — `os.path.getsize(journal_path)` after the i-th append is strictly greater than after the (i-1)-th append, and never decreases between appends or reads.
**And** truncation, in-place edit, and line deletion are asserted impossible by the API surface: there is no `journal.write_at_offset(...)`, no `journal.truncate(...)`, no `journal.replace_line(...)` — only `append` / `append_sync` / `iter_entries` / `iter_after`. The property test asserts these by `assert not hasattr(sdlc.journal, "write_at_offset")`, etc.
**And** the property test runs ≥1000 hypothesis examples (`@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])` — same knob as Story 1.10's invariant test).
**And** the property is structured as: hypothesis generates a sequence of `N` valid `JournalEntry` instances (1 ≤ N ≤ 50; `monotonic_seq` strictly increasing across the sequence; payload size capped at `dict[str, str]` with ≤ 5 keys to keep the example space bounded). For each prefix `s[0:k]`, append in order via `append_sync(...)`, then:
  - read all lines; assert exactly `k` lines.
  - for every `i ∈ [0, k)`: `lines[i].encode("utf-8") == _canonicalize_entry(s[i])`.
  - `os.path.getsize(journal_path)` strictly increased from before the append.
  - `iter_entries(journal_path)` yields entries with `monotonic_seq` strictly increasing.
  - `iter_after(journal_path, threshold=s[k//2].monotonic_seq)` yields entries with `monotonic_seq > threshold`, count = `k - (k//2 + 1)`.
**And** the property test also covers a **negative case** (in a separate `@given`-decorated function): generate a valid `JournalEntry`, append it, then attempt to append a second entry with `monotonic_seq <= first.monotonic_seq`; assert `JournalError(step="validate_seq", ...)` is raised AND the on-disk file size is unchanged after the failed call (file must not have been truncated/written by the failed validate-step).
**And** mark the property tests with `@pytest.mark.property` and `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — fcntl + O_APPEND atomicity required")` (mirrors Story 1.10's marker pattern).
**And** the property suite runs in CI as part of the existing property job in `.github/workflows/ci.yml` (the chaos-tests job from Story 1.10 stays focused on chaos; this new property test piggybacks on the existing `pytest -m property` step — adding a new CI job is NOT in scope for this story).

**AC3 — No-mutation API + static linter (epic AC block 3)**

**Given** the journal append-only protocol is implemented and property-verified,
**When** any code path under `src/sdlc/` (other than `src/sdlc/journal/writer.py` itself) attempts to mutate the journal file,
**Then** the API surface guarantees this cannot happen by name — `journal.write_at_offset`, `journal.truncate`, `journal.replace_line`, and similar mutation helpers DO NOT EXIST in the module. The public `__all__` of `sdlc.journal` exposes only `("append", "append_sync", "iter_entries", "iter_after")` (semantic order, with `# noqa: RUF022` to suppress alphabetical sort, mirroring Story 1.9 + 1.10 patterns).
**And** a **separate static linter** at `scripts/check_no_journal_mutation.py` rejects any of the following AST patterns when invoked from a Python file under `src/sdlc/` that is **not** `src/sdlc/journal/writer.py`:

  - `open(<expr>, "w")`, `open(<expr>, "wb")`, `open(<expr>, "r+")`, `open(<expr>, "rb+")`, `open(<expr>, "w+")`, `open(<expr>, "wb+")` where the path expression contains the literal substring `journal.log`, `journal.jsonl`, `journal_path`, or matches the regex `JOURNAL_(PATH|FILE|LOG|JSONL)`.
  - `pathlib.Path(...).write_text(...)` or `Path(...).write_bytes(...)` on `journal.log`-suffixed / `journal.jsonl`-suffixed literals.
  - `os.replace(<src>, <dst>)` or `os.rename(<src>, <dst>)` where `<dst>` is a `journal.log`-suffixed / `journal.jsonl`-suffixed literal (replacing the journal file in-place would break the append-only invariant).
  - **`<expr>.seek(<n>)` followed by `<expr>.write(<...>)` on the same expression within a single function body** — the canonical "write_at_offset" anti-pattern. Detection: walk every function body; for each `Call(func=Attribute(attr="seek"))` followed within the same `FunctionDef` (any later statement, same receiver-name) by `Call(func=Attribute(attr="write"))` on a name that resolves (heuristically — by `ast.unparse` string equality of the receiver expression) to the same handle, emit a violation. Receiver heuristic: `ast.unparse(seek_call.func.value) == ast.unparse(write_call.func.value)`. This is best-effort literal-match (no full dataflow); good enough to catch the obvious anti-pattern, and the `noqa` escape hatch covers false positives.
  - `os.lseek(<fd>, <offset>, <whence>)` followed by `os.write(<fd>, ...)` on the same fd-name in the same function body — the syscall-level equivalent of the seek+write pattern.
  - Any `open(<expr>, "a")` or `open(<expr>, "ab")` where the path is journal-suffixed — DOES TRIGGER a violation in this story (only `journal/writer.py` may open the journal for writing, even in append mode; FR31 + Architecture §493).

**And** the linter exempts: `tests/` (except cross-checks), `scripts/`, `src/sdlc/journal/writer.py` itself, the linter's own file `scripts/check_no_journal_mutation.py`, `_bmad/`, `_bmad-output/`, `.claude/`, `_site/`, `docs/`. Exemption uses the same `_EXEMPT_DIRS` first-segment-anchored convention as `scripts/check_no_hardcoded_secrets.py:30` and `scripts/check_no_direct_state_writes.py:26`.
**And** the linter's own file structure mirrors `scripts/check_no_direct_state_writes.py` (AST-based, top-of-file docstring, exit codes 0/1, `_NOQA_PATTERN` escape hatch `# noqa: journal-mutation -- <reason ≥ 10 chars>` with the same em-dash/double-dash regex variant, plain `# noqa: journal-mutation` without reason is itself flagged, OSError on `path.read_text` printed to stderr as `warning: could not read <path>: <err> — skipping` per Story 1.10's review patch).
**And** the linter is wired as a new pre-commit hook entry in `.pre-commit-config.yaml` named `journal-append-only-validator`, runs immediately AFTER `state-write-protocol-validator` and BEFORE `secret-hardcode-validator` (groups all write-protocol validators together — see Dev Notes "Pre-commit hook chain interaction"), exits non-zero on any violation, prints a fix suggestion: `"<file>:<line>: journal mutation detected. Use sdlc.journal.append (or append_sync) instead. (FR31 + Architecture §493 + Pattern §6)"`.
**And** unit tests for the linter live at `tests/unit/test_journal_mutation_validator.py` and cover: (a) every banned pattern triggers a violation (open-w on journal.log, Path.write_text on journal.jsonl, os.replace journal-suffixed, seek+write same-handle, lseek+write same-fd, open-a on journal); (b) the noqa escape hatch silences with a valid reason and is itself flagged when reason missing; (c) exempt directories are not scanned; (d) `journal/writer.py` self-exempt; (e) AST nodes that look similar but are NOT mutations (`open(p, "r")` on journal, `seek(0)` without subsequent `write`, `read+seek+read` patterns) do not trigger; (f) seek+write on a non-journal handle (e.g., a generic file in another module) IS still flagged (the linter is conservative — exempt-dir + self-exempt are the only escape hatches). For (f), document inline: this is intentional aggressiveness — false positives can use `# noqa: journal-mutation -- <reason>`; the cost of one occasional false positive is far lower than the cost of a missed mutation in the audit chain.
**And** linter coverage: `scripts/check_no_journal_mutation.py` must have ≥95% line coverage (mirrors Story 1.10's per-script ≥95% expectation, achieved via in-process `TestVisitorDirect` test class as added in Story 1.10's review patches).

## Tasks / Subtasks

- [x] **Task 1: Bootstrap `src/sdlc/journal/` package skeleton (AC: #1)**
  - [x] Create `src/sdlc/journal/__init__.py` with `from __future__ import annotations`, `from sdlc.journal.writer import append, append_sync`, `from sdlc.journal.reader import iter_entries, iter_after`, and `__all__` in semantic order: `("append", "append_sync", "iter_entries", "iter_after")` with `# noqa: RUF022` comment to suppress alphabetical sort (mirror `concurrency/__init__.py` Story 1.9 pattern + `state/__init__.py` Story 1.10 pattern).
  - [x] Add a Windows-stub fallback in `journal/__init__.py`: when `sys.platform == "win32"`, the names `append`, `append_sync` exist but invoking them raises `NotImplementedError("sdlc.journal.append is POSIX-only — see Architecture §573, §493")`. `iter_entries` and `iter_after` are pure-read and CAN remain functional on Windows (they use `Path.read_text` + iter; no `flock` needed for read). Document inline why the read path is cross-platform but the write path is not. Mirror the pattern in `state/__init__.py` Story 1.10 stub fallbacks.
  - [x] Verify package imports cleanly: `uv run python -c "from sdlc.journal import append, iter_entries"` (POSIX); on Windows the names exist at import time but `append(...)` raises `NotImplementedError` and `iter_entries(...)` works.
  - [x] **DO NOT** create `src/sdlc/journal/compactor.py` — Architecture §852 marks it "placeholder for v1.x" and Story 1.11's scope is writer + reader only. If the LOC budget allows a stub `compactor.py` raising `NotImplementedError`, it is acceptable but not required.

- [x] **Task 2: Implement `journal.append` async + sync (AC: #1)**
  - [x] Create `src/sdlc/journal/writer.py` with module docstring: `"""POSIX append-only JSONL journal writer (FR31, Architecture §493 + §849-§851, NFR-REL-2, NFR-OBS-1).\n\nO_APPEND-based atomic line semantics; flock serializes monotonic_seq validation.\nFull hash-verified projection-from-journal deferred to Story 1.12."""`.
  - [x] At top of file (after `from __future__ import annotations` and stdlib imports): `if sys.platform == "win32": raise ImportError("sdlc.journal.writer is POSIX-only — fcntl + O_APPEND semantics are required (Architecture §573, §493)")`. Mirror `src/sdlc/state/atomic.py:11-15` and `src/sdlc/concurrency/locks.py` line-1-11 patterns exactly.
  - [x] Define module-level constants: `JOURNAL_LOCK_SUFFIX: Final[str] = ".lock"`. Compute lock path from journal path: `lock_path = journal_path.with_suffix(journal_path.suffix + JOURNAL_LOCK_SUFFIX)`. Same sentinel-file approach as `state/atomic.py:30` (Decision B2).
  - [x] Implement private helper `_canonicalize_entry(entry: JournalEntry) -> bytes`: `payload = entry.model_dump(mode="json")` → recursively NFC-normalize all string values via the same `_normalize_strings` helper (consider importing from `state/atomic.py` to avoid duplication; if cross-module helper needs to live somewhere shared, place in a new `src/sdlc/_canonical.py` module or extend `contracts/__init__.py`. **Decision: import the helper from `sdlc.state.atomic._normalize_strings` is FORBIDDEN — that's a journal → state dependency that breaks `MODULE_DEPS["journal"].depends_on` which is `{"errors", "contracts", "concurrency", "config"}` and excludes `state`. Resolution: copy the 8-line `_normalize_strings` into `journal/writer.py` as a private helper, with a module docstring comment "Duplicated from state/atomic.py:_normalize_strings to respect MODULE_DEPS — DO NOT factor up the dependency graph; both copies must stay in lockstep. If they ever drift, journal → contracts → state will need restructuring (out of v1 scope)."`). The `json.dumps(...).encode("utf-8") + b"\n"` step is identical (terminating newline is REQUIRED for JSONL — distinct from `state.atomic._canonicalize_state` where the newline is for POSIX-cleanliness on a single-object file).
  - [x] Implement private helper `_read_highest_seq(journal_path: Path) -> int`: if file does not exist or is empty, return `-1`. Else, iterate the file line-by-line via `journal_path.open("r", encoding="utf-8")` (read-only — no flock needed for read; the caller already holds the write lock); for each line, `entry = JournalEntry.model_validate_json(line)`; track the maximum `monotonic_seq`. Return the max, or `-1` if no parseable entries. **Skip parse errors with a stderr warning** (`warning: malformed journal line at <path>:<lineno>: <err> — skipping`) rather than raising, because the highest-seq check is best-effort robustness; the property test asserts that all written entries are well-formed, so malformed lines indicate either (a) a partial line from a kill-mid-write (handled by `O_APPEND` atomicity for newer writes) or (b) external tampering (out of v1 trust model). This matches the resilience pattern from `scripts/check_no_direct_state_writes.py`'s OSError-on-read handling (Story 1.10 review patch).
  - [x] Implement private helper `_append_protocol_body(entry: JournalEntry, journal_path: Path) -> None`: synchronous protocol body. Steps: (1) compute highest_seq via `_read_highest_seq(journal_path)`; (2) validate `entry.monotonic_seq > highest_seq` else raise `JournalError(step="validate_seq", details={"supplied": entry.monotonic_seq, "expected_min": highest_seq + 1, "path": str(journal_path)})`; (3) `canonical_bytes = _canonicalize_entry(entry)`; (4) `fd = os.open(str(journal_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)` → on OSError raise `JournalError(step="open_journal", ...)`; (5) drain bytes in short-write loop with 0-byte-write guard (mirror `state/atomic.py:_write_bytes` exactly); (6) `os.fsync(fd)` → on OSError raise `JournalError(step="fsync_journal", ...)`; (7) `os.close(fd)` in `finally` with body-exception preservation pattern from Story 1.9 + 1.10. Each step that can raise OSError gets `details={"path": str(journal_path), "errno": e.errno, "step": "<name>", "monotonic_seq": entry.monotonic_seq}`.
  - [x] Implement `async def append(entry: JournalEntry, journal_path: Path) -> None`: validate `journal_path` is absolute (raise `JournalError(step="validate_path", ...)` if not); compute `lock_path`; use `async with file_lock(lock_path):` from `sdlc.concurrency`; inside the lock body, run the protocol body via `await asyncio.to_thread(_append_protocol_body, entry, journal_path)` to avoid blocking the event loop on `os.fsync` + `_read_highest_seq` linear-scan. Architecture §727: this matches the `state/atomic.py:write_state_atomic` async pattern.
  - [x] Implement `def append_sync(entry: JournalEntry, journal_path: Path) -> None`: same protocol but uses the sync `with file_lock(lock_path):` context manager and calls `_append_protocol_body` directly. Document inline: `# Sync entrypoint exists ONLY for property tests / chaos tests running in subprocess-killed children where no event loop exists. Do NOT call from production code paths — use the async append.` Add the same runtime guard as `state.atomic.write_state_atomic_sync`: if `asyncio.get_running_loop()` succeeds, raise `JournalError(step="loop_check", ...)`.
  - [x] Body-exception preservation: any cleanup-path OSError (fd close failures after a successful body) must NOT mask a body exception — apply the Story 1.9 / 1.10 `body_exc` capture pattern verbatim (see `state/atomic.py:151-165`).
  - [x] LOC budget: `journal/writer.py` MUST stay ≤ 200 LOC (well under the 400 cap, matching `state/atomic.py`'s ~245 LOC ceiling). If it overruns, factor `_canonicalize_entry` and `_read_highest_seq` into `journal/_canonical.py` and `journal/_seq.py`. **Constraint check before splitting**: `MODULE_DEPS["journal"]` (boundary registry line 54-57) accepts only `{"errors", "contracts", "concurrency", "config"}`; new sibling files inside `journal/` are fine — only EXTERNAL deps would break boundaries.

- [x] **Task 3: Implement `journal.iter_entries` + `journal.iter_after` reader (AC: #1, #2)**
  - [x] Create `src/sdlc/journal/reader.py` with module docstring: `"""POSIX-cross-platform journal reader: pure read, no flock required (Architecture §522, §1060).\n\nReads sort strictly by monotonic_seq; order in file IS the order returned (O_APPEND guarantees)."""`.
  - [x] Implement `def iter_entries(journal_path: Path) -> Iterator[JournalEntry]`: if file does not exist, yield nothing (return empty iterator). Else open with `journal_path.open("r", encoding="utf-8")`; for each non-empty line, `yield JournalEntry.model_validate_json(line)`. Architecture §522: "journal reader sorts strictly by monotonic_seq, never by ts" — but because writes are append-only with monotonic_seq strictly increasing per the AC1 validate_seq check, **file order IS monotonic_seq order**. Document this invariant inline; do NOT add a sort step (sort would mask a writer bug). Add a SECOND-LINE-OF-DEFENCE assertion: track the previous yielded entry's `monotonic_seq`; if the next yielded entry's `monotonic_seq <= prev`, raise `JournalError(step="reader_invariant", details={"path": str(journal_path), "prev_seq": prev, "next_seq": next, "lineno": <lineno>})`. Rationale: the reader is the last sentinel before downstream code (Story 1.12 projection) trusts the order; a corrupted journal with out-of-order seqs must fail loudly here, not silently project a wrong state.
  - [x] Implement `def iter_after(journal_path: Path, threshold: int) -> Iterator[JournalEntry]`: same as `iter_entries` but skips entries where `entry.monotonic_seq <= threshold`. Useful for incremental projection (Story 1.12 will call this with the last-seen seq).
  - [x] Malformed-line handling: same policy as `_read_highest_seq` — print stderr warning `warning: malformed journal line at <path>:<lineno>: <err> — skipping` and continue. Document inline: this differs from the writer's strict-validate behavior. The reader is permissive because (a) Story 1.20 `sdlc rebuild-state` may need to recover from a partially-corrupted journal, and (b) the property test in AC2 generates only well-formed entries so the test surface is clean. **Trade-off**: a malformed line silently skipped could mask a real bug. Mitigation: the `JournalError(step="reader_invariant")` in `iter_entries` triggers if seqs go out-of-order, which would be a likely consequence of a missing entry. Document this trade-off in the module docstring and in ADR-014.
  - [x] Reader is **cross-platform** (no `fcntl`, no `O_APPEND` — pure file read). Do NOT add the POSIX `ImportError` guard at top of `reader.py`. The Windows stub in `journal/__init__.py` (Task 1) only stubs out the writer.
  - [x] LOC budget: `journal/reader.py` ≤ 100 LOC (typical for a 2-function reader module).

- [x] **Task 4: Add `journal/` to module boundary registry — VERIFY ZERO EDITS REQUIRED (AC: #1, #3)**
  - [x] Verify `scripts/check_module_boundaries.py` already has `MODULE_DEPS["journal"]` registered at lines 54-57 (confirmed at story-authoring time 2026-05-08): `depends_on={"errors", "contracts", "concurrency", "config"}`, `forbidden_from={"engine", "dispatcher", "runtime", "cli"}`. **Pre-flight check at story start**: `grep -n '"journal"' scripts/check_module_boundaries.py` should return the same line numbers; if a prior story has edited this entry, abort and ask the user. **Zero edits to `scripts/check_module_boundaries.py` expected** — paralleling Story 1.10's invariant about `MODULE_DEPS["state"]`.
  - [x] Run `uv run python scripts/check_module_boundaries.py src/sdlc/journal/` and confirm 0 boundary violations once the module is implemented (Tasks 1-3 complete).

- [x] **Task 5: Implement hypothesis property test for append-only invariant (AC: #2)**
  - [x] Create `tests/property/test_journal_append_only.py` with module docstring citing FR31 + NFR-REL-2 + epic AC block 2 (lines 688-692).
  - [x] Define `journal_entry_strategy = st.builds(JournalEntry, schema_version=st.just(1), monotonic_seq=st.integers(min_value=0, max_value=2**62-1), ts=_iso_z_strategy(), actor=st.text(min_size=1, max_size=20).filter(str.isprintable), kind=st.sampled_from(["state_mutation", "agent_dispatch", "signoff", "bypass_signoff"]), target_id=st.text(min_size=1, max_size=40).filter(str.isprintable), before_hash=st.one_of(st.none(), _sha256_strategy()), after_hash=_sha256_strategy(), payload=st.dictionaries(st.text(min_size=1, max_size=10).filter(str.isprintable), st.text(min_size=0, max_size=20), max_size=5))`. Helper `_iso_z_strategy()` produces RFC3339 UTC strings via `st.datetimes()` + `.isoformat(timespec="milliseconds") + "Z"` then validates against `_RFC3339_UTC` (the regex from `contracts/journal_entry.py:16`). Helper `_sha256_strategy()` produces `"sha256:" + 64-hex-char` strings via `st.text(alphabet="0123456789abcdef", min_size=64, max_size=64).map(lambda h: f"sha256:{h}")`. Cap dictionary depth at 1 (no nested dicts) to keep examples bounded.
  - [x] Define a strategy `monotonic_sequence_strategy` that produces a list of `(N, [seq_0 < seq_1 < ... < seq_{N-1}])` tuples with `1 ≤ N ≤ 50` and strictly increasing seqs. Compose with `journal_entry_strategy` to inject the seq into each entry: `entries = [entry.model_copy(update={"monotonic_seq": seq_i}) for entry, seq_i in zip(base_entries, seqs)]`.
  - [x] **Property 1 — file grows-only + line bytes immutable**: append each entry in order via `append_sync`; after the i-th append, assert: (a) `os.path.getsize(journal_path)` strictly greater than the size before the i-th append, (b) reading the file line-by-line yields exactly `i+1` lines, (c) for every `j ∈ [0, i]`: `lines[j].encode("utf-8") == _canonicalize_entry(entries[j])` — exact byte identity (this is the strong append-only-immutability assertion from epic AC2 line 690). After the final append, assert one final read still equals the full sequence.
  - [x] **Property 2 — no-mutation API surface**: assert at module-import time (not inside the `@given` body — module-level constant): `_JOURNAL_PUBLIC_API = set(sdlc.journal.__all__)`; `assert _JOURNAL_PUBLIC_API == {"append", "append_sync", "iter_entries", "iter_after"}`. Then assert: `for forbidden_name in ("write_at_offset", "truncate", "replace_line", "edit_line", "delete_line", "overwrite", "seek_and_write"): assert not hasattr(sdlc.journal, forbidden_name)`. This is structural — runs once per test session.
  - [x] **Property 3 — iter_after correctness**: pick `threshold = entries[k].monotonic_seq` for `k = N // 2`; assert `list(iter_after(journal_path, threshold)) == entries[k+1:]` (strict inequality semantics).
  - [x] **Property 4 — monotonic_seq regression rejected (negative case)**: in a separate `@given(entry=journal_entry_strategy)`-decorated function: append the entry; record `os.path.getsize(journal_path)`; attempt to append a second entry constructed via `entry.model_copy(update={"monotonic_seq": entry.monotonic_seq})` (same seq → must reject); assert `pytest.raises(JournalError) as exc_info: append_sync(...)`; assert `exc_info.value.details["step"] == "validate_seq"`; assert `os.path.getsize(journal_path)` is **unchanged** (the failed append must not have written or truncated).
  - [x] Use `@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])` per epic AC3.
  - [x] Mark all property functions with `@pytest.mark.property` and `@pytest.mark.skipif(sys.platform == "win32", ...)`.
  - [x] Per-test fixture: each `@given` function uses a `tmp_path`-scoped journal file so hypothesis examples don't share state across iterations (mirror Story 1.10's `tmp_target_dir` fixture pattern).

- [x] **Task 6: Implement static linter `check_no_journal_mutation.py` (AC: #3)**
  - [x] Create `scripts/check_no_journal_mutation.py` patterned after `scripts/check_no_direct_state_writes.py`. AST-based — walks `ast.Call` nodes looking for the banned patterns enumerated in AC3. Use `ast.unparse()` on path-argument nodes to render the literal for substring matching.
  - [x] Detection rules (each emits a violation with file:line + fix suggestion):
    - `_check_open_call(node)`: `ast.Call(func=ast.Name(id="open"), args=[<path>, ast.Constant(value=mode)])` where `mode in {"w", "wb", "a", "ab", "r+", "rb+", "w+", "wb+"}` AND `ast.unparse(<path>)` matches `_JOURNAL_PATH_NAMES = re.compile(r"(journal\.log|journal\.jsonl|journal_path|JOURNAL_(PATH|FILE|LOG|JSONL))", re.IGNORECASE)`. **Note**: this is stricter than `check_no_direct_state_writes.py` which only blocks `w/wb/a/ab/w+/wb+` — for the journal, even read-write modes (`r+/rb+`) are forbidden because they enable `seek+write` mutation. Read-only `"r"`/`"rb"` modes are allowed (the reader uses them).
    - `_check_path_write_call(node)`: `ast.Call(func=ast.Attribute(attr="write_text"|"write_bytes"))` where the receiver chain ends in a `journal.log`/`journal.jsonl`-suffixed path.
    - `_check_replace_call(node)`: `ast.Call(func=ast.Attribute(value=ast.Name(id="os"), attr="rename"|"replace"))` where arg[1] (`<dst>`) is a journal-suffixed literal.
    - `_check_seek_then_write_in_function(func: ast.FunctionDef)`: walk the function body in document order; for every `ast.Call(func=ast.Attribute(attr="seek"))`, look for any subsequent `ast.Call(func=ast.Attribute(attr="write"))` in the same function body where `ast.unparse(seek_call.func.value) == ast.unparse(write_call.func.value)`. Emit a violation on the `write` call's lineno.
    - `_check_lseek_then_write_in_function(func: ast.FunctionDef)`: same pattern but for `os.lseek(fd, ...)` followed by `os.write(fd, ...)` where `ast.unparse(lseek.args[0]) == ast.unparse(write.args[0])`.
  - [x] Exempt directories (`_EXEMPT_DIRS`): `{"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"}` — first path segment match, mirroring `check_no_direct_state_writes.py:26`.
  - [x] Self-exempt: `src/sdlc/journal/writer.py` is the canonical writer (it's the only module that opens journal in append mode); the linter's own file is also self-exempt. Note: `src/sdlc/journal/reader.py` is NOT self-exempt — the reader uses `"r"` mode which is not flagged, so no exemption is needed; if the reader ever introduces a `seek+read` pattern that's fine (read-only seeks are allowed).
  - [x] Escape hatch: `# noqa: journal-mutation -- <reason ≥ 10 chars>` regex `r"#\s*noqa:\s*journal-mutation(?:\s*(?:—|--)\s*(.{10,}))?"`. Plain `# noqa: journal-mutation` without reason is itself a violation (mirror `check_no_direct_state_writes.py:35`).
  - [x] CLI signature: `python scripts/check_no_journal_mutation.py [path ...]`; no args → recurse `src/sdlc/`. Exit 0 = clean, 1 = violations. Print violations to stderr. Print warning + skip on `OSError` from `path.read_text` (Story 1.10 review patch pattern).
  - [x] Add module-level invariant assertion: list of canonical write API names = `_CANONICAL_WRITE_API = frozenset({"sdlc.journal.writer.append", "sdlc.journal.writer.append_sync"})` — if `journal/writer.py` ever renames either, this constant breaks the linter (intentional drift detector, mirroring `state/atomic.py:_CANONICAL_WRITE_API`).

- [x] **Task 7: Wire pre-commit hook for the static linter (AC: #3)**
  - [x] Edit `.pre-commit-config.yaml`: add a new `local` repo hook entry `journal-append-only-validator` between `state-write-protocol-validator` (line 60) and `secret-hardcode-validator` (line 71). Entry: `id: journal-append-only-validator`, `name: journal append-only protocol validator (FR31 + Architecture §493)`, `entry: uv run python scripts/check_no_journal_mutation.py`, `language: system`, `types: [python]`, `files: ^src/sdlc/.*\.py$`, `pass_filenames: true`.
  - [x] Run `uv run pre-commit run journal-append-only-validator --all-files` locally; expect 0 violations on the current tree (no production code mutates `journal.log` yet — `journal/writer.py` is the only new write site and is self-exempt).
  - [x] Add a deliberately-banned snippet to `tests/fixtures/lint_negative/journal_mutation.py.txt` (NOT `.py` — outside scope of the validator's `files:` filter) — used by the linter unit test in Task 8 as a fixture that is parsed and asserted to flag.

- [x] **Task 8: Unit tests for the static linter (AC: #3)**
  - [x] Create `tests/unit/test_journal_mutation_validator.py`. Use `subprocess.run([sys.executable, "scripts/check_no_journal_mutation.py", str(fixture_path)])` with `capture_output=True, text=True`. Test cases:
    - `test_open_journal_log_w_mode_flagged`: `open("path/to/journal.log", "w")` → exit 1 with the expected error message.
    - `test_open_journal_jsonl_a_mode_flagged`: `open("journal.jsonl", "a")` → flagged (append mode also banned outside `journal/writer.py`).
    - `test_open_journal_r_plus_mode_flagged`: `open("journal.log", "r+")` → flagged (read-write mode enables seek+write).
    - `test_path_write_text_journal_log_flagged`: `Path("journal.log").write_text("...")` → flagged.
    - `test_os_replace_journal_log_flagged`: `os.replace(tmp, "journal.log")` → flagged.
    - `test_seek_then_write_same_handle_flagged`: `f = open("/tmp/foo", "rb+"); f.seek(0); f.write(b"x")` → flagged (seek+write anti-pattern, regardless of journal naming).
    - `test_lseek_then_write_same_fd_flagged`: `os.lseek(fd, 0, 0); os.write(fd, b"x")` → flagged.
    - `test_open_journal_r_mode_not_flagged`: `open("journal.log", "r")` → exit 0.
    - `test_seek_alone_not_flagged`: `f.seek(0); data = f.read()` → exit 0 (seek without subsequent write is fine).
    - `test_write_alone_not_flagged`: `f.write(data)` (no preceding seek) → exit 0 (append-mode writes to a non-journal file are out of scope).
    - `test_seek_then_write_different_handles_not_flagged`: `f.seek(0); g.write(b"x")` (different receivers) → exit 0.
    - `test_noqa_with_reason_silences`: `f.seek(0); f.write(b"x")  # noqa: journal-mutation -- restoring backup snapshot in test fixture` → exit 0.
    - `test_noqa_without_reason_flagged`: bare `# noqa: journal-mutation` → exit 1 with "noqa: journal-mutation requires a reason ≥ 10 chars".
    - `test_exempt_dir_not_scanned`: a fixture under `tests/fixtures/...` with banned content is NOT flagged (exempt dir).
    - `test_self_exempt_writer_py`: passing `src/sdlc/journal/writer.py` → exit 0 even though it contains the actual writes (`os.open(..., O_APPEND)`).
    - `test_reader_py_not_self_exempt_but_has_no_violations`: passing `src/sdlc/journal/reader.py` → exit 0 (no banned patterns; not self-exempt either, but happens to be clean).
  - [x] In-process test class `TestVisitorDirect` (mirror Story 1.10's review patch pattern) for ≥95% coverage on Windows where subprocess `multiprocessing.Process` semantics differ. Direct AST-walk tests on synthetic AST nodes ensure the visitor logic is hit.
  - [x] Coverage threshold: `scripts/check_no_journal_mutation.py` must have ≥95% line coverage in `pytest --cov=scripts/check_no_journal_mutation` (mirrors Story 1.10's per-script ≥95% expectation).

- [x] **Task 9: Unit tests for `journal/writer.py` and `journal/reader.py` (AC: #1, #2)**
  - [x] Create `tests/unit/journal/__init__.py` (empty) and `tests/unit/journal/test_journal_append_protocol.py`:
    - `test_append_creates_file_when_missing`: append once to a non-existent path; assert file exists with one line.
    - `test_append_uses_o_append_flag`: monkeypatch `os.open` to capture flags; assert `(flags & os.O_APPEND) != 0` AND `(flags & os.O_ACCMODE) == os.O_WRONLY` AND `(flags & os.O_CREAT) != 0` (proper access-mode check pattern from Story 1.10 review).
    - `test_append_canonical_bytes_match_model_dump`: append a known entry; read the line; assert byte-for-byte equality with `_canonicalize_entry(entry)`.
    - `test_append_fsyncs_after_write`: monkeypatch `os.fsync` to count calls; assert exactly 1 call per `append_sync`.
    - `test_append_holds_flock_during_protocol`: import `lock_registry` from `sdlc.concurrency`; spawn the protocol body in a thread with a deliberate sleep; assert the lock is in the registry during the sleep, gone after.
    - `test_append_releases_flock_on_failure`: monkeypatch `_canonicalize_entry` to raise; assert lock is NOT in registry after the failed call.
    - `test_append_rejects_non_absolute_path`: `append_sync(entry, Path("relative/path"))` → `JournalError(step="validate_path")`.
    - `test_append_rejects_seq_regression`: append entry with seq=5; attempt seq=5 again → `JournalError(step="validate_seq", details["expected_min"]=6)`.
    - `test_append_rejects_seq_equal_to_highest`: same as above (boundary condition).
    - `test_append_accepts_seq_strictly_greater`: append seq=5, then seq=6 → succeeds, file has 2 lines.
    - `test_append_sync_inside_event_loop_raises`: run `append_sync` from inside `asyncio.run(...)` body → `JournalError(step="loop_check")`.
    - `test_append_short_write_loop`: monkeypatch `os.write` to return half the bytes on first call, full on second; assert two write syscalls total, one fsync.
    - `test_append_zero_byte_write_raises`: monkeypatch `os.write` to return 0; assert `JournalError(step="write_journal", details["errno"]=0)`.
    - `test_append_body_exception_preserved_over_close_oserror`: monkeypatch `_write_bytes` to raise `OSError(EIO)`; monkeypatch `os.close` to also raise `OSError(EBADF)`; assert the EIO bubbles up (body_exc preserved), EBADF is suppressed.
    - `test_append_cross_platform_stub_on_windows`: skip if not on Windows; assert importing `sdlc.journal.append` works but calling it raises `NotImplementedError`. Mirror Story 1.10's `state/__init__.py` Windows-stub test pattern.
  - [x] Create `tests/unit/journal/test_journal_reader.py`:
    - `test_iter_entries_empty_file_yields_nothing`.
    - `test_iter_entries_missing_file_yields_nothing`.
    - `test_iter_entries_yields_in_file_order`: write 3 entries with seqs 0/1/2; assert order is 0, 1, 2.
    - `test_iter_entries_raises_on_seq_regression`: write a hand-crafted file with seqs 0, 1, 0 (third line regression — bypassing the writer's validate_seq); assert `iter_entries` yields the first two then raises `JournalError(step="reader_invariant")`.
    - `test_iter_entries_skips_malformed_lines_with_warning`: write a file with one valid line and one `"not json\n"` line; assert one entry yielded, stderr contains "warning: malformed journal line".
    - `test_iter_after_filters_strictly_greater`: write entries 0/1/2/3; `iter_after(threshold=1)` yields only seqs 2 and 3.
    - `test_iter_after_threshold_above_all`: `iter_after(threshold=99)` yields nothing.
    - `test_iter_after_threshold_below_all`: `iter_after(threshold=-1)` yields all entries.
    - `test_iter_entries_works_on_windows`: confirm the reader has no POSIX-only guard — the test runs cross-platform via `pytest.mark.skipif(sys.platform == "win32", ...)` REMOVED for these reader tests. (Subset of read tests must run on Windows CI to validate the cross-platform contract.)
  - [x] Per-package coverage gate: `sdlc.journal` must reach ≥95% line coverage (per Architecture's per-package gate, mirroring Story 1.10's `sdlc.state` 95% target).

- [x] **Task 10: Add ADR-014 + update documentation (AC: all)**
  - [x] Create `docs/decisions/ADR-014-append-only-journal-protocol.md` with sections: Status: Accepted; Date: 2026-05-08; Context (FR31 + NFR-REL-2 + NFR-OBS-1 + Architecture §493 + §849-§851 + Decision B5 single-source-of-truth journal); Decision (the 7-step POSIX append protocol with `O_APPEND` + flock + fsync; sync-vs-async dual API; reader as last-line-of-defence monotonicity check; static linter rejecting seek+write); Consequences (POSIX-only writer / cross-platform reader split; permissive reader (skip malformed lines) trades silent-skip for rebuild-state recoverability — accepted because seq-regression detection catches the dangerous case; `_normalize_strings` duplicated from `state/atomic.py` to respect MODULE_DEPS["journal"] not depending on state — must stay in lockstep). Cite Story 1.10's ADR-013 as the precedent for the dual-API pattern.
  - [x] Update `docs/decisions/index.md`: add row `| ADR-014 | Append-only journal protocol | Accepted | 2026-05-08 |` (or matching the existing row format). Note the ADR-014 number is the next available — confirmed via `ls docs/decisions/ADR-*.md` at story-authoring time (last existing was ADR-013 from Story 1.10).
  - [x] Update `docs/CODEMAPS/journal.md` (if exists) or create a stub citing this story's deliverables (`writer.py`, `reader.py`, the property test, the static linter, the pre-commit hook, ADR-014).
  - [x] Add `journal` mark to `pyproject.toml`'s `[tool.pytest.ini_options].markers` table if not already present (existing marks: `unit`, `integration`, `chaos`, `property` — no new mark needed for this story; the property test reuses the existing `property` mark).
  - [x] Add mypy override in `pyproject.toml` for `sdlc.journal.writer` mirroring the Story 1.10 pattern: `disable_error_code = ["unreachable", "attr-defined", "no-any-return"]` because the POSIX-only `if sys.platform == "win32"` guard creates unreachable code on Linux mypy runs and `attr-defined` errors on Windows mypy runs (review-patch from Story 1.10's D2 resolution).
  - [x] Add coverage `omit` in `pyproject.toml` for `src/sdlc/journal/writer.py` on Windows-only test runs (mirror Story 1.10's pattern for `state/atomic.py`).

- [x] **Task 11: Validate full quality gates green (AC: all)**
  - [x] Run `uv run ruff check src/ tests/ scripts/` → 0 errors.
  - [x] Run `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [x] Run `uv run mypy --strict src/` → 0 errors. The new `journal/writer.py` MUST type-check under `--strict` (no `Any` leaks; `os.fsync` returns `None`; `JournalEntry` typed correctly; iterator return types annotated as `Iterator[JournalEntry]`).
  - [x] Run `uv run pre-commit run --all-files` → all hooks pass including `journal-append-only-validator` (NEW), `state-write-protocol-validator` (Story 1.10), `boundary-validator`, `secret-hardcode-validator`, `mypy-strict`, `ruff-check`, `ruff-format`.
  - [x] Run `uv run pytest tests/unit/journal/ tests/unit/test_journal_mutation_validator.py -m "not chaos and not property"` → all pass; per-package coverage ≥95% for `sdlc.journal` and `scripts.check_no_journal_mutation`.
  - [x] Run `uv run pytest tests/property/test_journal_append_only.py` → 1000 examples pass (multiplied by 4 properties = 4000 hypothesis trials in the canonical run).
  - [x] Run global `uv run pytest --cov=src --cov-fail-under=90` → passes.
  - [x] Verify `scripts/check_module_boundaries.py` recognizes `journal/` imports correctly (it already does — `MODULE_DEPS["journal"]` registered at line 54-57; `journal` may import `errors`, `contracts`, `concurrency`, `config`).
  - [x] Verify the boundary registry has NOT been edited by this story: `git diff scripts/check_module_boundaries.py` → empty (the ZERO-edits invariant from Task 4).

## Dev Notes

### Why this story exists (FR + NFR mapping)

- **FR31 — append-only journal**: PRD-named functional requirement directly mapped to `journal/writer.py` (Architecture §1157, §849-§851). The protocol is the realization of FR31. **FR38** (`--force-bypass-signoff` writes a `bypass_signoff` journal entry) depends on this story's `append` API but is implemented in a later story (Architecture §1164) — Story 1.11 only ships the primitive.
- **NFR-REL-2 — append-only invariant under property test**: explicitly named in the epic AC2 — file grows-only, line bytes immutable, no mutation API. The property test in Task 5 is the materialization of NFR-REL-2.
- **NFR-OBS-1 — `journal.log` as one of three observability streams (Decision E3, Architecture §480, §567)**: this story ships the writer for the `journal.log` stream. The other two streams (`agent_runs.jsonl` and `debug_events.jsonl`) are owned by `telemetry/` (Architecture §888-§892) and ship in later stories.
- **Decision B3 — JournalEntry wire-format contract (Architecture §347, §595-§606)**: `JournalEntry` pydantic model already exists at `src/sdlc/contracts/journal_entry.py` (Story 1.7 deliverable, 54 LOC). Story 1.11 does NOT redefine it — only consumes it. The fields enforced (`schema_version`, `monotonic_seq`, `ts`, `actor`, `kind`, `target_id`, `before_hash`, `after_hash`, `payload`) are the wire-format v1 frozen surface; downstream stories (signoff, dispatcher) use the same contract.
- **Decision B5 — journal as source of truth (Architecture §349)**: `state.json` is a cached projection; the journal is the durable audit chain. Story 1.11 ships the substrate; Story 1.12 ships the projection (`state.project_from_journal`); Story 1.20 ships `sdlc rebuild-state` which uses `iter_entries` from this story.
- **Architecture §493 — "no `open()` for state / journal writes — use `state/atomic.py` and `journal/writer.py` only"**: the `journal-append-only-validator` static linter from Task 6 is the enforcement of this architectural rule. Pairs with the `state-write-protocol-validator` from Story 1.10 (same enforcement pattern, different file).
- **Architecture §581 step 8 — "append journal entry referencing the mutation (own atomic protocol, separate file)"**: this story implements the "own atomic protocol" for the journal. The state-write protocol from Story 1.10 ends at step 7 (parent-dir fsync); step 8 (journal append) is a SEPARATE protocol call by the upper-stack caller (engine/dispatcher in later stories). Story 1.11 does NOT integrate with `state/atomic.py` — they are sibling primitives. The caller is responsible for the ordering: write_state_atomic THEN journal.append. Architecture §589 acknowledges the kill-between-7-and-8 case as recoverable via `sdlc rebuild-state` (Story 1.20).

### File set this story creates / modifies

**New files (created):**

- `src/sdlc/journal/__init__.py` — package init, semantic-order `__all__`, Windows-stub for writer
- `src/sdlc/journal/writer.py` — append protocol implementation (~150-200 LOC; cap 400)
- `src/sdlc/journal/reader.py` — `iter_entries` + `iter_after` (~80-100 LOC)
- `tests/unit/journal/__init__.py` — empty package marker
- `tests/unit/journal/test_journal_append_protocol.py` — per-step isolation tests (~16 test cases)
- `tests/unit/journal/test_journal_reader.py` — reader tests (~9 test cases)
- `tests/unit/test_journal_mutation_validator.py` — static linter unit tests (~16 test cases incl. `TestVisitorDirect`)
- `tests/property/test_journal_append_only.py` — hypothesis property test (4 properties, 1000 examples each)
- `scripts/check_no_journal_mutation.py` — static linter (~150-200 LOC)
- `tests/fixtures/lint_negative/journal_mutation.py.txt` — fixture for linter test
- `docs/decisions/ADR-014-append-only-journal-protocol.md` — new ADR

**Modified files:**

- `.pre-commit-config.yaml` — add `journal-append-only-validator` hook entry between `state-write-protocol-validator` (line 60) and `secret-hardcode-validator` (line 71)
- `docs/decisions/index.md` — add ADR-014 row
- `pyproject.toml` — add mypy override for `sdlc.journal.writer` + coverage omit for POSIX-only journal writer
- `docs/CODEMAPS/journal.md` (create or update) — codemap stub citing deliverables

**Files explicitly NOT modified (invariant):**

- `scripts/check_module_boundaries.py` — `MODULE_DEPS["journal"]` is already registered (line 54-57) with `depends_on={"errors", "contracts", "concurrency", "config"}` and `forbidden_from={"engine", "dispatcher", "runtime", "cli"}`. **Zero edits required** — paralleling Story 1.9's AC5 "ZERO edits to MODULE_DEPS" pattern and Story 1.10's same invariant for `state`. Verify with `grep -n '"journal"' scripts/check_module_boundaries.py` before starting and again after — same line numbers, same content.
- `src/sdlc/contracts/journal_entry.py` — Story 1.7 deliverable (54 LOC); used as-is via `from sdlc.contracts.journal_entry import JournalEntry`. No edits.
- `src/sdlc/errors/base.py` — `JournalError` already exists at line 45 with code `ERR_JOURNAL`. Use as-is.
- `src/sdlc/state/atomic.py` — Story 1.10 deliverable; not touched by this story. Story 1.11's writer is a sibling primitive.
- `src/sdlc/state/model.py` — `next_monotonic_seq` field already exists. Story 1.11 reads `entry.monotonic_seq` from the input but does NOT increment any state counter — counter advancement is the caller's responsibility (per Architecture §520 "advances atomically with the state mutation that referenced it").
- `src/sdlc/concurrency/locks.py` — Story 1.9 deliverable; used as-is via `from sdlc.concurrency import file_lock`.
- `scripts/check_no_direct_state_writes.py` — Story 1.10 deliverable; not touched.

### Sync vs async API reconciliation

The Story 1.9 + 1.10 precedent: ship the protocol body as a pure synchronous function (`_append_protocol_body`); wrap with `async def append(...)` for production callers; provide `def append_sync(...)` for property/chaos tests inside subprocess-killed children where `asyncio.run` is wasteful and obstructs debugging. Story 1.11 follows this exactly:

1. `_append_protocol_body(entry, journal_path) -> None` — pure synchronous function. Single source of truth for the protocol.
2. `async def append(entry, journal_path)` — production async API: `async with file_lock(...): await asyncio.to_thread(_append_protocol_body, entry, journal_path)`.
3. `def append_sync(entry, journal_path)` — test-only sync API: `with file_lock(...): _append_protocol_body(entry, journal_path)`.

The runtime check `asyncio.get_running_loop()` in `append_sync` enforces that production code paths use async (footgun guard from `state/atomic.py:196-204`).

**Why both APIs**: property tests using `@given(...)` work fine with sync test bodies; introducing `pytest-asyncio` ceremony for every property test is overkill, and hypothesis has well-documented quirks with async-mode tests. The sync API exists ONLY for testing; the linter does not flag `append_sync` as a banned name (it's intentional public API). Production code paths (engine, dispatcher, hooks) MUST use the async API.

### Why no aiofiles / aiofile / similar libraries

Story 1.9 explicitly chose stdlib `fcntl` over `portalocker`, and Story 1.10 chose stdlib `os.replace + os.fsync` over `python-atomicwrites`. Story 1.11 follows the same precedent: stdlib `os.open + O_APPEND + os.fsync` over `aiofiles`. Reasons:

- `O_APPEND` is the kernel-enforced atomic-to-EOF guarantee on POSIX. Library wrappers add a layer that may or may not preserve that guarantee — direct `os.open` makes the flag visible.
- `aiofiles` uses a thread pool internally — same as our `asyncio.to_thread` wrapping. No win, just a third-party dependency on a critical durability path.
- No third-party dependency on the audit-chain primitive.
- Identical semantics across Linux/macOS without library-version surprises.

This decision is recorded in ADR-014's Consequences section.

### Append-protocol superset: epic vs. architecture vs. this story

The epic's AC1 lists 4 protocol intents: "serialized via canonical JSON, written with newline, fsync'd, flushed". Architecture §581 step 8 says "append journal entry referencing the mutation (own atomic protocol, separate file)" — without enumerating the steps. This story formalizes the steps as 7:

1. acquire `flock(<journal>.lock)`.
2. canonicalize entry (NFC + sort_keys + separators + `\n`).
3. **(NEW — Step 2.5 in AC1)** read highest existing `monotonic_seq`; validate `entry.monotonic_seq > highest`.
4. open journal in `O_WRONLY | O_CREAT | O_APPEND` mode.
5. drain canonical bytes via short-write loop.
6. `os.fsync(fd)`.
7. `os.close(fd)`.
8. release `flock`.

The monotonicity validation (Step 2.5) is added beyond the epic's brief because epic AC1 line 685 says "the file's monotonic_seq is strictly greater than the previous entry's" — that's a precondition the appender must check. Without the in-protocol check, two concurrent appenders could both compute the same `next_monotonic_seq` from a stale state read (the lock serializes, so the second one would see the first's append on re-read; but the lock-based serialization is exactly what makes this check correct). The reader-side `JournalError(step="reader_invariant")` from Task 3 is the second line of defence if a malicious or buggy writer ever bypassed the appender.

The writer does NOT fsync the parent directory after the append — this is **intentional** and differs from `state/atomic.py`'s 7-step protocol. Rationale: `O_APPEND` writes do not change the directory entry (the file already exists after the first append, and subsequent appends only extend the file in place — directory entries point to inodes, and inode size changes don't invalidate the directory). Architecture §580's "fsync(parent directory) — critical" comment applies to the rename-based atomic-write protocol where a NEW directory entry must be created/updated; for `O_APPEND`-based writes, file-level `fsync` is sufficient. Document this distinction inline in `journal/writer.py` and in ADR-014.

**One edge case**: the FIRST append to a non-existent journal file DOES create a new directory entry (via `O_CREAT`). For full OS-crash durability of the very first entry, a parent-dir fsync would be needed. Trade-off: adding a parent-dir fsync only on first-write adds branching complexity to a hot path; the property test in AC2 always pre-creates the journal file via `journal_path.touch()` in the test fixture, so the first-append edge case is not exercised by the property test. **Decision: accept this gap for v1.** A kill between `O_CREAT` and the `fsync(fd)` at the very first append could lose the directory entry for the journal under OS crash; recovery via `sdlc rebuild-state` (Story 1.20) re-creates the journal from `journal[0]` (which is empty in this case — there's nothing to recover). Document the gap in ADR-014's Consequences.

### Module dependency invariants — post-Story-1.11 state

After this story, `MODULE_DEPS["journal"]` continues to declare:

- `depends_on = {"errors", "contracts", "concurrency", "config"}` — `journal/writer.py` imports `JournalError` (errors), `JournalEntry` (contracts), `file_lock` (concurrency). `config` is permissive — Story 1.11 may not need to import `sdlc.config` (no config-driven behavior in the journal primitive); listed for forward-compatibility.
- `forbidden_from = {"engine", "dispatcher", "runtime", "cli"}` — these upper-stack modules MUST go through `sdlc.journal.append`, never directly `open(journal_path, "a")`. The new `journal-append-only-validator` linter is the enforcement.

**Cross-module invariant**: `journal/writer.py` MUST NOT import from `sdlc.state` (state is forbidden_from journal? — actually: state is NOT in journal's `forbidden_from` set). Re-checking: looking at `MODULE_DEPS["journal"].depends_on = {errors, contracts, concurrency, config}` — `state` is not in this set, so journal cannot import state. The boundary validator enforces this. **Practical consequence for Task 2**: the `_normalize_strings` helper must be duplicated from `state/atomic.py:43-51` into `journal/writer.py` rather than imported. See Task 2's bullet on this.

**Pre-flight check before Task 2**: confirm `MODULE_DEPS["journal"]` is registered. If `scripts/check_module_boundaries.py` line 54-57 has been edited away in any prior story, abort and ask user. (At time of story authoring 2026-05-08, lines 54-57 are intact:
```
"journal": ModuleSpec(
    depends_on=frozenset({"errors", "contracts", "concurrency", "config"}),
    forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
),
```
)

### Pre-commit hook chain interaction

After Task 7, the chain is: `ruff-check → ruff-format → mypy-strict → boundary-validator → state-write-protocol-validator (Story 1.10) → journal-append-only-validator (NEW, Story 1.11) → secret-hardcode-validator → specialist-validator → standard-hygiene`. Both write-protocol validators are grouped together for readability and because the patterns they detect are conceptually paired.

The new hook fires only on `^src/sdlc/.*\.py$` so it does not slow whole-tree commits. Wall-clock budget: AST walk of all `src/sdlc/` files should add <50ms per commit (the linter is single-pass with no I/O beyond reading each file once).

A regression case for the reviewer to confirm: edit `src/sdlc/journal/writer.py` to add a deliberate `f.seek(0); f.write(b"x")` line; commit; expect `journal-append-only-validator` to PASS (writer.py is self-exempt) but the unit test `test_self_exempt_writer_py` MUST not have been weakened to accept this. Test this in `tests/unit/test_journal_mutation_validator.py::test_self_exempt_writer_py_does_not_exempt_other_journal_files` — only `journal/writer.py` self-exempt, not `journal/reader.py`, not `journal/__init__.py`.

### Previous story intelligence — Story 1.10 (atomic state write protocol)

Patterns to mirror exactly (these were code-review-validated; Story 1.10 went through 4 D-decisions + 9 patches and converged):

- **POSIX-only ImportError at module top** (`state/atomic.py:11-15`): `if sys.platform == "win32": raise ImportError("... is POSIX-only ...")`. Apply to `journal/writer.py` only — `journal/reader.py` is cross-platform.
- **`from __future__ import annotations`** at top of every new `.py` file in `journal/`.
- **Semantic-order `__all__`** with `# noqa: RUF022` (ruff would otherwise sort alphabetically).
- **Body-exception preservation in cleanup paths** (`state/atomic.py:151-165`): capture `body_exc` in `try`/`except BaseException`; in `finally`, attempt `os.close(fd)` and re-raise the close error ONLY if `body_exc is None`. This pattern is non-negotiable — Story 1.9 + 1.10 reviewers explicitly validated it.
- **`asyncio.to_thread` for blocking syscalls** (`state/atomic.py:188`): `os.fsync` + `os.write` + linear scan of the journal in `_read_highest_seq` are all blocking; offload via `to_thread` in the async API.
- **5-helper-function decomposition for protocol body** (`state/atomic.py:_open_tmp`, `_write_bytes`, `_fsync_fd`, `_rename`, `_fsync_parent_dir`): keeps each helper ≤ ruff C901 complexity ≤ 8. Apply analogously: `_open_journal_for_append`, `_write_bytes` (could share with state/atomic if not for module-boundary constraint), `_fsync_journal`, `_close_journal`.
- **Constants `_MIN_ARGS_FOR_OPEN = 2`** (`state/atomic.py:39`): magic-number suppression for AST-walking helpers. Mirror in `check_no_journal_mutation.py`.
- **Per-pytest-mark structure**: `@pytest.mark.unit` on unit tests; existing marks `@pytest.mark.property` for property tests (already declared in `pyproject.toml` from Story 1.10). No new marks needed.
- **Linter file structure mirrors `check_no_hardcoded_secrets.py` + `check_no_direct_state_writes.py`**: AST-based, exempt-dirs first-segment match, `_NOQA_PATTERN` regex, `OSError`-on-read warning-and-skip pattern (Story 1.10 review patch), in-process `TestVisitorDirect` test class for ≥95% Windows coverage (Story 1.10 review patch).
- **mypy override pattern** (`pyproject.toml`): `disable_error_code = ["unreachable", "attr-defined", "no-any-return"]` for POSIX-only modules — narrow override, NOT wholesale `ignore_errors = true`. Story 1.10 D2 resolved this from wholesale to narrow.
- **`_node_name_fs_unsafe` sanitization** in chaos fixtures (`tests/chaos/conftest.py`): not relevant to Story 1.11 (no chaos tests in this story); but if Task 5 ends up using `tmp_path_factory` with `request.node.name`, sanitize the name first per Story 1.10 review patch.

Code-review feedback from Story 1.10 to pre-empt:
- Be explicit about exception chaining (`raise JournalError(...) from e`).
- Avoid `Any` in type hints (use `Iterator[JournalEntry]`, `Final[str]`, etc.).
- Verify `mypy --strict` passes BEFORE committing.
- Sanitize fs-unsafe characters in any path-derived test names.
- Use `(flags & os.O_ACCMODE) == os.O_WRONLY` access-mode check instead of `flags & os.O_RDONLY == 0` test theatre (Story 1.10 review patch on `test_state_atomic_protocol.py`).
- Narrow exception catches: `OSError` for I/O, `(ValueError, TypeError)` for schema (pydantic.ValidationError subclasses ValueError). Do NOT catch bare `Exception` (Story 1.10 patch on `read_state`).

### Git intelligence — last 5 commits

```
2f4322d feat: implement atomic state write protocol with chaos tests (Story 1.10)
ce351c5 chore: ignore graphify output and config files
99c8f78 chore: update skills, add Story 1.9, graphify output, and project config
b378b5a fix: apply code-review patches for Story 1.8 config module
1042fc1 feat: implement config module with validation (Story 1.8)
```

Story 1.10's commit (`2f4322d`) is the immediate predecessor and is on disk as `done` status in `sprint-status.yaml`. Confirm via `git log --oneline -5` at story start that Story 1.10's commit is present and that `src/sdlc/state/atomic.py`, `tests/chaos/`, and `scripts/check_no_direct_state_writes.py` are all on disk before beginning Task 1. If Story 1.10 is missing, abort and ask user.

Patterns established by recent commits (relevant for this story):
- One commit per story (`feat: implement <module> (Story X.Y)`); apply review patches in a follow-up `fix:` commit if needed.
- Test files always co-shipped — no `feat` without accompanying `tests/unit/`.
- `--cov-fail-under=90` enforced globally; per-package ≥95% for foundation modules.
- ADR commits ride along with the implementation commit unless the ADR is large enough to warrant its own.

### Latest tech information

- **Python 3.10+** target (Architecture-stated minimum). All language features used (`@dataclass(frozen=True)`, pydantic v2 `ConfigDict(frozen=True)`, `Iterator[T]` from `collections.abc`) are stable.
- **pydantic v2** (Story 1.7 introduced; on disk at `src/sdlc/contracts/`). Use `model_dump(mode="json")` not deprecated `dict()`. Use `model_validate(payload)` and `model_validate_json(line)` (the latter parses+validates in one shot — efficient for the reader's per-line dispatch).
- **`JournalEntry.model_validate_json`** is the v2 API; pydantic v2 docs note this is faster than `model_validate(json.loads(line))` because it uses Rust-backed parsing internally. Use it in `_read_highest_seq` and `iter_entries`.
- **hypothesis** is already a project dev dependency; latest stable is 6.x. `@settings(max_examples=N, deadline=None)` syntax stable. `st.builds(Model, ...)` works for pydantic v2 models that accept kwargs (which `JournalEntry` does).
- **`os.open` + `O_APPEND`**: POSIX guarantees that each `write(2)` call to an `O_APPEND`-opened fd is atomic to EOF and atomic-vs-other-`O_APPEND`-writers; this is the kernel-enforced append-only semantics that makes our property test true. Document this guarantee inline.
- **`os.lseek` + `os.write`**: bypasses `O_APPEND`'s atomic-to-EOF guarantee — exactly the anti-pattern the linter rejects. Confirmed via `man 2 write`: "If the file was open(2)ed with O_APPEND, the file offset is first set to the end of the file before writing. The adjustment of the file offset and the write operation are performed as an atomic step."
- **JSONL reading with `model_validate_json`**: pydantic v2's per-line validate-and-parse is the canonical pattern; document inline that line-bounded JSON parsing is ENFORCED — multi-line JSON in a single journal entry is forbidden by the canonicalizer's `separators=(",", ":")` (which has no whitespace — including no newlines — within a single entry's serialization).
- **Hypothesis health check `HealthCheck.too_slow`**: suppress in property tests because the per-example fsync makes wall-clock variable. Same pattern as Story 1.10.

### Project Structure Notes

- **Alignment with unified project structure**: this story creates the `journal/` namespace per Architecture §849-§852. The architecture lists three files for `journal/`: `writer.py` (FR31), `reader.py` (Pattern §4 iter sorted by monotonic_seq), `compactor.py` (placeholder for v1.x). Story 1.11 ships `writer.py` + `reader.py`; `compactor.py` is OUT OF SCOPE (architecture marks it placeholder).
- **No conflict with architecture**: every file path in Task 1's "New files" list lives under a directory the architecture has already declared.
- **Pyproject markers**: `chaos` and `property` marks already exist (added by Story 1.10's Task 4/5). No new marks needed.
- **CI workflow**: NO new CI job — the property test piggybacks on the existing `property` job from Story 1.10. The linter piggybacks on the existing `pre-commit` job. This is consistent with the principle of keeping CI surface minimal.

### Why deferred from this story

These are explicitly NOT in scope for Story 1.11 — flag if they creep in during implementation:

- **Hash verification on read** (`iter_entries` returns whatever's on disk; no hash-chain validation). Deferred to Story 1.12 / signoff hasher integration.
- **State projection from journal** (`project_from_journal`, the pure function that replays journal[0:k] to produce State_k). Deferred to Story 1.12 — that story will USE `iter_entries` from this story.
- **`monotonic_seq` counter advancement at the state-write site** — Story 1.11 only validates the supplied seq; it does NOT compute or advance the counter. Counter advancement is owned by the caller (engine/dispatcher in later stories) per Architecture §520. State 1.10 already ships the `next_monotonic_seq` field on `State`.
- **`compactor.py`** — Architecture §852 marks it "placeholder for v1.x". Out of v1 scope.
- **`post_write_journal.py` hook** (Architecture §867 + §973) — auto-append journal on artifact writes. This is a `hooks/builtin/` deliverable; depends on this story but is wired in a later (hook system) story.
- **Multi-writer concurrency property test** — the property test in this story is single-writer-sequential (the `file_lock` already serializes; demonstrating concurrent-safety would require a second flock-aware client which doesn't exist yet). Deferred to Story 1.12 if needed.
- **OS-crash chaos tests for the journal** — Architecture §219 + Story 1.10 chaos cardinality formula could be extended to journal kills (KP-J1 mid-append, KP-J2 post-fsync-pre-close, etc.). NOT in scope for Story 1.11 — epic AC2 specifies a property test, not a chaos test, and the kill-points ROI is lower for `O_APPEND` (kernel-atomic) than for the rename-based state protocol. If a future audit-chain story adds chaos coverage, that's a separate story.
- **Compaction / rotation** of `journal.log` (size-based or time-based). Out of v1 scope (Architecture §852 placeholder).
- **Encryption-at-rest** for `journal.log`. Out of v1 scope; framework runs on user's local disk per the threat model.
- **Journal-replay performance benchmarks** — `iter_entries` is a linear file read; for journals of millions of entries, this becomes slow. Optimization deferred until empirical evidence (DORA dashboards in Epic 5) shows it matters.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.11] (lines 674-697) — story spec, AC blocks
- [Source: _bmad-output/planning-artifacts/architecture.md#Atomic-Write-Protocol] (lines 569-589) — canonical 9-step protocol; step 8 is the journal append (this story's primitive)
- [Source: _bmad-output/planning-artifacts/architecture.md#JSON-Canonicalization-Rules] (lines 496-515) — canonical JSON + NFC normalization, JSONL `\n` per line
- [Source: _bmad-output/planning-artifacts/architecture.md#Timestamp-and-Ordering] (lines 517-522) — `monotonic_seq` as totally-ordered field; reader sorts by `monotonic_seq`, never by `ts`
- [Source: _bmad-output/planning-artifacts/architecture.md#Decisions] (line 347 — Decision B3 JournalEntry schema; line 349 — Decision B5 journal as source of truth; line 373 — Decision E3 three observability streams)
- [Source: _bmad-output/planning-artifacts/architecture.md#Code-Style-Beyond-Ruff] (line 493) — "no `open()` for state / journal writes — use `state/atomic.py` and `journal/writer.py` only"
- [Source: _bmad-output/planning-artifacts/architecture.md#FR-Mapping] (line 1157) — FR31 → `journal/writer.py`; (line 1164) — FR38 `--force-bypass-signoff` writes via `journal/writer.py`
- [Source: _bmad-output/planning-artifacts/architecture.md#Five-Wire-Format-Schemas] (lines 595-606) — `JournalEntry` v1 schema reference
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Dependency-Table] (line 1060) — `journal/` depends on `errors/, contracts/, concurrency/, config/`; forbidden from `engine, dispatcher, runtime, cli`
- [Source: _bmad-output/planning-artifacts/architecture.md#Source-Tree] (lines 849-852) — full `journal/` file layout: writer.py, reader.py, compactor.py
- [Source: _bmad-output/planning-artifacts/architecture.md#Pattern-Enforcement] (line 700-701 — test naming convention; line 712 — atomic write enforcement also covers journal)
- [Source: _bmad-output/planning-artifacts/architecture.md#Hooks] (line 867 — `post_write_journal.py` planned but out of scope)
- [Source: _bmad-output/planning-artifacts/architecture.md#FilesAndPaths] (line 973 — post_write_journal hook path; line 993 — test_journal_append_only.py path; line 1002 — test_journal_durability.py path placeholder)
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-05-07-old.md#NFR-REL] — "append-only invariant under property test" (NFR-REL-2 named target)
- [Source: src/sdlc/contracts/journal_entry.py] (lines 1-54) — `JournalEntry` pydantic v2 model already on disk; consume as-is
- [Source: src/sdlc/errors/base.py] (line 45) — `JournalError` with `code = "ERR_JOURNAL"`, exit_code 2
- [Source: src/sdlc/state/atomic.py] (entire file, ~245 LOC) — Story 1.10 reference patterns: POSIX gate, helper-function decomposition, body-exception preservation, sync+async API split, `_canonicalize_state` + `_normalize_strings` to be duplicated in journal/writer.py per MODULE_DEPS
- [Source: src/sdlc/state/__init__.py] — Windows-stub fallback pattern for cross-platform stub
- [Source: src/sdlc/state/model.py] — `next_monotonic_seq: int = 0` already exists; this story does NOT modify
- [Source: src/sdlc/concurrency/locks.py] (entire file) — Story 1.9 reference patterns (POSIX gate, async path via `asyncio.to_thread`, body-exception preservation, `_FileLock` registry)
- [Source: src/sdlc/concurrency/__init__.py] — semantic-order `__all__` with `# noqa: RUF022`, POSIX-only conditional imports
- [Source: scripts/check_module_boundaries.py] (lines 54-57) — `MODULE_DEPS["journal"]` pre-registered, ZERO edits required
- [Source: scripts/check_no_hardcoded_secrets.py] — patterning for AST-walk linter, exempt-dirs convention, noqa escape hatch
- [Source: scripts/check_no_direct_state_writes.py] (entire file, ~200 LOC) — Story 1.10 reference for the new `check_no_journal_mutation.py` linter; AST visitor patterns + OSError-on-read handling + `TestVisitorDirect` for ≥95% coverage
- [Source: .pre-commit-config.yaml] (lines 57-66 state-write-protocol-validator entry; lines 68-77 secret-hardcode-validator entry) — patterns to mirror for the new `journal-append-only-validator` hook entry between them
- [Source: _bmad-output/implementation-artifacts/1-10-atomic-write-protocol-chaos-tests.md] (entire file, 462 lines) — previous-story patterns + 9 review patches + 4 D-decisions to pre-empt
- [Source: docs/decisions/ADR-013-atomic-state-write-protocol.md] — precedent for ADR-014 structure and Consequences enumeration

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (BMAD dev-story workflow)

### Debug Log References

### Completion Notes List

- All 11 tasks completed. `src/sdlc/journal/writer.py` (POSIX-only, 7-step O_APPEND protocol with flock + fsync + monotonicity validation), `src/sdlc/journal/reader.py` (cross-platform, permissive skip + seq-regression guard), and `src/sdlc/journal/__init__.py` (Windows-stub fallback) implemented.
- `tests/property/test_journal_append_only.py` runs 4 properties × 1000 examples on POSIX (skipped on Windows as designed).
- `scripts/check_no_journal_mutation.py` AST linter with `_EXEMPT_DIRS`, noqa escape hatch, and `journal-append-only-validator` pre-commit hook wired.
- All quality gates green: ruff 0 errors, ruff format clean, mypy --strict 0 errors (25 files), all 15 pre-commit hooks pass, 579 unit tests pass, 44 skipped (POSIX/Windows expected). `sdlc.journal` per-package coverage 100%; `check_no_journal_mutation.py` 99% (only `__main__` guard pragma-excluded). Global `--cov=src/sdlc --cov-fail-under=90` passes at 100%.
- `_normalize_strings` duplicated into `journal/writer.py` to honour `MODULE_DEPS["journal"]` not depending on `state` (per boundary registry at `scripts/check_module_boundaries.py:54-57`).
- `scripts/check_module_boundaries.py` zero-edits invariant verified: `git diff scripts/check_module_boundaries.py` is empty.
- Two extra reader tests added (`test_iter_entries_skips_blank_lines`, `test_iter_entries_raises_journal_error_on_oserror`) to bring `reader.py` to 100% coverage.
- ~20 `TestVisitorDirect` in-process test methods added to `tests/unit/test_journal_mutation_validator.py` to bring `check_no_journal_mutation.py` to 99% line coverage (matching Story 1.10's pattern).
- `# type: ignore[misc]` removed from Windows stubs in `__init__.py` (mypy on Windows reports "unused-ignore").
- `# pragma: no cover` added to `if __name__ == "__main__":` guard in linter script (standard convention for unreachable-under-import blocks).

### File List

**New files created:**
- `src/sdlc/journal/__init__.py`
- `src/sdlc/journal/writer.py`
- `src/sdlc/journal/reader.py`
- `tests/unit/journal/__init__.py`
- `tests/unit/journal/test_journal_append_protocol.py`
- `tests/unit/journal/test_journal_reader.py`
- `tests/unit/test_journal_mutation_validator.py`
- `tests/property/test_journal_append_only.py`
- `scripts/check_no_journal_mutation.py`
- `tests/fixtures/lint_negative/journal_mutation.py.txt`
- `docs/decisions/ADR-014-append-only-journal-protocol.md`

**Modified files:**
- `.pre-commit-config.yaml` — added `journal-append-only-validator` hook between `state-write-protocol-validator` and `secret-hardcode-validator`
- `docs/decisions/index.md` — added ADR-014 row
- `pyproject.toml` — added mypy override for `sdlc.journal.writer`, coverage omit for POSIX-only writer on Windows, `docs/CODEMAPS/journal.md` codemap stub
- `docs/CODEMAPS/journal.md` — created codemap stub

### Review Findings

### Change Log

- 2026-05-08: Story 1.11 implementation complete — append-only journal writer (POSIX, 7-step O_APPEND protocol), cross-platform reader, hypothesis property test (4 properties × 1000 examples), AST linter `check_no_journal_mutation.py`, `journal-append-only-validator` pre-commit hook, ADR-014, all quality gates green.
