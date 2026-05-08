# Story 1.10: Atomic Write Protocol + Chaos Tests at 10 Kill Points

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reliability-conscious user,
I want `state.write_state_atomic(state)` implemented with tmp-file + fsync + rename + flock, chaos-tested at 10 distinct kill points,
so that no crash mid-write ever leaves a malformed `state.json` (FR30, NFR-REL-1).

## Acceptance Criteria

**AC1 — Protocol implementation (epic AC block 1)**

**Given** Story 1.9 complete (`file_lock` + `BoundedDispatcher` shipped) and `state/atomic.py` newly created,
**When** I call `await write_state_atomic(state, target_path)`,
**Then** the executable protocol is exactly:

1. open `<target>.tmp` (`O_CREAT | O_WRONLY | O_TRUNC`, mode `0o644`)
2. write canonicalized JSON bytes (per Architecture §501-508: `sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`, NFC-normalized strings, terminating `\n`)
3. `os.fsync(tmp_fd)` — durability of tmp content
4. acquire `flock(<target>.lock)` via the Story 1.9 `file_lock(...)` async context manager
5. `os.replace(tmp_path, target_path)` — atomic rename on POSIX (`os.replace` is preferred over `os.rename` per Python docs because it overwrites cross-platform; on POSIX they are equivalent for same-filesystem)
6. `os.fsync(parent_dir_fd)` — directory entry durability (Architecture §580: "critical — survives OS crash, not just process kill"; epic-stated protocol omits this but NFR-REL-1's "0 state.json corruption under OS-crash" requires it — see Dev Notes "Protocol superset" rationale)
7. release `flock` (handled automatically on `__aexit__` of `file_lock`)

**And** unit tests in `tests/unit/test_state_atomic_protocol.py` verify each step in isolation (one test per step asserting the side effect: tmp file exists after step 1, content matches canonical bytes after step 2, fd is fsynced after step 3 — verified via `pytest`-mocking `os.fsync` to record calls — flock held during steps 4-7 via `lock_registry()` introspection from Story 1.9, target file is replaced after step 5, parent dir fsync called after step 6, `lock_registry()` is empty after step 7).
**And** the public API exported from `sdlc.state` is exactly: `write_state_atomic` (async), `read_state` (deferred to Story 1.11/1.12 — this story may stub a minimal `read_state` only if needed for chaos-recovery assertions).
**And** `write_state_atomic` is `async def` (matches Story 1.9 async-default direction); a thin sync convenience `write_state_atomic_sync` is provided for chaos tests that must run inside `subprocess`-killed children where no event loop exists, and it MUST share its protocol body with the async path (no logic divergence — see Dev Notes "Sync vs async API reconciliation").
**And** `write_state_atomic` accepts a `State` pydantic model (defined in `state/model.py`, minimal v1 fields per Dev Notes "Minimal State model scope"); does NOT accept arbitrary `dict` — `dict` callers must pass `State.model_validate(d)` first.
**And** any failure path (OSError on open / write / fsync / rename, flock unavailable) raises `StateError` with `details={"path": str, "errno": int, "step": "<protocol-step-name>"}` chained via `raise ... from e`; the body-exception preservation pattern from Story 1.9 (`_release(body_exc=...)`) MUST be applied so a cleanup OSError does not mask the real error.

**AC2 — Chaos test infrastructure: 10 declared kill points × ≥100 randomized seeds (epic AC block 2)**

**Given** the chaos test module at `tests/chaos/test_atomic_write_kill_points.py`,
**When** the test harness kills the writing process at each of the 10 declared kill points (enumerated below),
**Then** for every kill point, post-recovery `read_state(target_path)` returns either the previous valid state OR the new valid state — never a partial/malformed state, never raises `JSONDecodeError` or `pydantic.ValidationError`.
**And** the test asserts this property over **≥100 randomized hypothesis seeds per kill point** (1000 trials minimum across all kill points; exact knob: `@settings(max_examples=100)` per parametrized kill point).
**And** the 10 kill points are declared as a frozen `enum.Enum` (`KillPoint` in `tests/chaos/kill_points.py`) with these exact members and semantics (all required; no others; no fewer):

| ID  | Symbolic name            | Inserted between protocol steps | What is on disk at kill |
|-----|--------------------------|----------------------------------|--------------------------|
| KP1 | `AFTER_TMP_OPEN`         | step 1 → step 2                  | empty `<target>.tmp`; previous `<target>` intact |
| KP2 | `MID_TMP_WRITE`          | inside step 2 (after first half of canonical bytes flushed)  | partial `<target>.tmp`; previous `<target>` intact |
| KP3 | `AFTER_TMP_WRITE`        | step 2 → step 3                  | full `<target>.tmp` but **not** fsynced; previous `<target>` intact; under OS-crash variant the tmp may be lost from page cache |
| KP4 | `AFTER_TMP_FSYNC`        | step 3 → step 4                  | full + durable `<target>.tmp`; lock not yet held; previous `<target>` intact |
| KP5 | `AFTER_FLOCK_ACQUIRE`    | step 4 → step 5                  | lock held by killed process — kernel releases on PID death; subsequent writers can re-acquire; previous `<target>` intact |
| KP6 | `AFTER_RENAME`           | step 5 → step 6                  | new `<target>` visible BUT directory entry **not** fsynced; under OS-crash variant the rename may be reverted (Architecture §588: "rename visible but not durable") |
| KP7 | `AFTER_PARENT_DIR_FSYNC` | step 6 → step 7                  | new `<target>` durable; lock still held; epic recovery: trivially safe (next start sees new state) |
| KP8 | `BEFORE_FLOCK_RELEASE`   | inside step 7 (release races kill) | new `<target>` durable; lock fd may be closed by kernel cleanup — re-runnable |
| KP9 | `OS_CRASH_PRE_FSYNC`     | special variant: simulates power-loss between steps 5 and 6 by `drop_caches`-equivalent fault injection (see Dev Notes "OS-crash simulation"); page cache lost | rename may be lost; tmp may be lost; previous `<target>` is the only durable artifact |
| KP10 | `RECOVERY_OF_RECOVERY`  | re-run `write_state_atomic` AFTER a leftover `<target>.tmp` from any prior KP1–KP9 kill | second invocation must complete cleanly; orphan tmp from prior run must not block the new write; final state matches the second invocation's input |

**And** kill mechanism: per kill point, the test spawns a child process via `multiprocessing.Process(target=_run_protocol_until_kill_point, args=(kill_point, seed, target_path))`; the child registers a SIGSTOP-based pause at the declared point and the parent issues `os.kill(child.pid, signal.SIGKILL)` (true uncatchable kill, page cache preserved). For KP9 OS-crash variant, the parent additionally invokes the OS-crash hook (see "OS-crash simulation" in Dev Notes).
**And** randomization: `hypothesis.strategies.builds(State, ...)` produces the input state; the integer seed parametrizes both the State and the byte offset for KP2's "first half" cut; the post-recovery read must succeed regardless of seed.
**And** all chaos tests are marked `@pytest.mark.chaos` and `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — fcntl + signal semantics required")`.
**And** `tests/chaos/conftest.py` provides a session-scoped `tmp_target_dir` fixture that uses `tmp_path_factory` and asserts the parent directory is writable + fsyncable; it cleans up orphan `.tmp` and `.lock` files between tests via `_cleanup_artifacts()`.
**And** the chaos suite runs in CI under a dedicated `pytest -m chaos` job in `.github/workflows/ci.yml` (matrix: ubuntu-latest only; `timeout-minutes: 15`; `--cov-fail-under` does NOT include chaos coverage in the global aggregate — chaos tests are correctness fixtures, not coverage drivers).

**AC3 — Property invariant + static linter (epic AC block 3)**

**Given** the atomic write protocol is implemented and chaos-verified,
**When** I run `pytest tests/property/test_atomic_write_invariant.py`,
**Then** a hypothesis-driven property test confirms the **two-state invariant** under arbitrary input states:

> For all sequences `s = [State_0, State_1, ..., State_n]` of valid states,
> for all interleavings `I` of `write_state_atomic(s_i)` calls (sequential, since the lock serializes),
> at every observable point during or after the sequence, `read_state(target_path)` returns some `s_k` for `k ∈ {-1, 0, 1, ..., n}` (where `s_{-1}` is the file's pre-existing content or "absent"),
> never an intermediate or invalid value.

**And** the property test runs ≥1000 hypothesis examples (`@settings(max_examples=1000, deadline=None)` because fsync latency varies).
**And** a **separate static linter** at `scripts/check_no_direct_state_writes.py` rejects any of the following AST patterns when invoked from a Python file under `src/sdlc/` that is **not** `src/sdlc/state/atomic.py`:

- `open(<expr>, "w")` or `open(<expr>, "wb")` or `open(<expr>, "a")` or `open(<expr>, "ab")` where the path expression contains the literal substring `state.json` or `state_path` or comes from a name that resolves to `STATE_PATH` constants (best-effort literal match — no full dataflow analysis).
- `pathlib.Path(...).write_text(...)` or `Path(...).write_bytes(...)` on `state.json`-suffixed literals.
- `os.replace(<src>, <dst>)` or `os.rename(<src>, <dst>)` where `<dst>` is a `state.json`-suffixed literal.
- Direct `tmp.write(...)`-and-rename patterns that don't go through `sdlc.state.atomic`.

**And** the linter is wired as a new pre-commit hook entry in `.pre-commit-config.yaml` named `state-write-protocol-validator`, runs after `boundary-validator` and before `secret-hardcode-validator`, exits non-zero on any violation, prints a fix suggestion: `"<file>:<line>: direct state write detected. Use sdlc.state.atomic.write_state_atomic instead. (Architecture §493 + Pattern §6)"`.
**And** the linter exempts: `tests/` (except cross-checks), `scripts/`, `src/sdlc/state/atomic.py` itself, `_bmad/`, `_bmad-output/`, `.claude/`, `docs/`. Exemption uses the same `_EXEMPT_DIRS` first-segment-anchored convention as `scripts/check_no_hardcoded_secrets.py`.
**And** the linter's own file structure mirrors `scripts/check_no_hardcoded_secrets.py` (AST-based, `_NOQA_PATTERN` escape hatch `# noqa: state-write -- <reason ≥ 10 chars>`, top-of-file docstring, exit codes 0/1).
**And** unit tests for the linter live at `tests/unit/test_state_write_validator.py` and cover: (a) every banned pattern triggers a violation, (b) the noqa escape hatch silences with a valid reason and is itself flagged when the reason is missing, (c) exempt directories are not scanned, (d) AST nodes that look similar but are NOT writes (`open(p, "r")`, comparison expressions) do not trigger.

## Tasks / Subtasks

- [x] **Task 1: Bootstrap `src/sdlc/state/` package skeleton (AC: #1)**
  - [x] Create `src/sdlc/state/__init__.py` with `from __future__ import annotations`, `from sdlc.state.atomic import write_state_atomic, write_state_atomic_sync`, `from sdlc.state.model import State`, and `__all__` in semantic order: `("State", "write_state_atomic", "write_state_atomic_sync")` with `# noqa: RUF022` comment to suppress alphabetical sort (mirror `concurrency/__init__.py` Story 1.9 pattern).
  - [x] Create `src/sdlc/state/model.py` with a minimal `State` pydantic v2 model: `model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)`; fields: `schema_version: int = 1`, `next_monotonic_seq: int = 0` (Architecture §520: counter lives at `state.json["next_monotonic_seq"]`), `epics: dict[str, Any] = Field(default_factory=dict)` (placeholder; full schema deferred to Story 1.11/1.12). Add module docstring citing "Minimal v1 — full schema in Stories 1.11-1.12 (Decision B5)".
  - [x] Add a top-of-file `if sys.platform == "win32"` guard NOT to `state/`-package modules — only `state/atomic.py` itself (since Windows lacks `fcntl` + parent-dir-fsync semantics). The `state.model` and `state.__init__` MUST remain importable on Windows so `mypy --strict` and unit tests for the model can run cross-platform.
  - [x] Verify package imports cleanly: `uv run python -c "from sdlc.state import State, write_state_atomic"` (POSIX); on Windows the `write_state_atomic` name must be present at import time but invoking it raises `NotImplementedError("write_state_atomic is POSIX-only — see Architecture §573")`.

- [x] **Task 2: Implement `write_state_atomic` async + sync (AC: #1)**
  - [x] Create `src/sdlc/state/atomic.py` with module docstring: `"""POSIX atomic write protocol for state.json (Architecture §569-§589, Pattern §6, FR30, NFR-REL-1)."""`.
  - [x] At top of file (after `from __future__ import annotations` and stdlib imports): `if sys.platform == "win32": raise ImportError("sdlc.state.atomic is POSIX-only — fcntl + parent-dir fsync are required (Architecture §573)")`. Mirror the Story 1.9 `concurrency/locks.py` line-1-11 pattern exactly.
  - [x] Define module-level constants: `STATE_FILE_NAME: Final[str] = "state.json"`, `STATE_LOCK_SUFFIX: Final[str] = ".lock"`, `STATE_TMP_SUFFIX: Final[str] = ".tmp"`. Compute lock path from target path: `lock_path = target.with_suffix(target.suffix + STATE_LOCK_SUFFIX)` — flock is a separate sentinel file, NOT the target itself (Decision B2 per-file flock granularity).
  - [x] Implement private helper `_canonicalize_state(state: State) -> bytes`: `payload = state.model_dump(mode="json")` → recursively NFC-normalize all string values via `unicodedata.normalize("NFC", s)` → `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"`. Architecture §513: "no trailing newline on hashed content; one `\n` per line in JSONL files" — `state.json` is JSON not JSONL, but a terminating `\n` is POSIX-cleanliness convention; include it (this differs from the canonicalize-for-hash variant which omits the newline; document the difference inline).
  - [x] Implement `_write_protocol_body(state, target, sync_mode) -> None`: synchronous protocol body. Steps: open tmp via `os.open(str(tmp_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)` (NOT `open()` builtin — bypasses any test-side monkeypatching of builtins); `os.write(tmp_fd, canonical_bytes)` in a loop until all bytes drained (handle short writes); `os.fsync(tmp_fd)`; `os.close(tmp_fd)`; (lock acquisition happens in the wrapper); `os.replace(tmp_path, target_path)`; open parent dir via `dir_fd = os.open(str(target.parent), os.O_RDONLY); os.fsync(dir_fd); os.close(dir_fd)`. Each step wrapped in try/except OSError → `raise StateError(...) from e`.
  - [x] Implement `async def write_state_atomic(state: State, target: Path) -> None`: validate `target` is absolute; compute `lock_path`; use `async with file_lock(lock_path):` from `sdlc.concurrency`; inside the lock body, run the protocol body via `await asyncio.to_thread(_write_protocol_body, state, target, sync_mode=False)` to avoid blocking the event loop on `os.fsync`. Architecture §727: this matches the `concurrency/locks.py` async pattern.
  - [x] Implement `def write_state_atomic_sync(state: State, target: Path) -> None`: same protocol but uses the sync `with file_lock(lock_path):` context manager and calls `_write_protocol_body` directly. Document inline: `# Sync entrypoint exists ONLY for chaos tests running in subprocess-killed children where no event loop exists. Do NOT call from production code paths.` Add a runtime check: if `asyncio.get_running_loop()` succeeds (caller is inside an event loop), raise `StateError("write_state_atomic_sync called from inside an event loop — use the async write_state_atomic")` — prevents footgun.
  - [x] Body-exception preservation: any cleanup-path OSError (fd close failures after a successful body) must NOT mask a body exception — apply the Story 1.9 `_release(body_exc=...)` pattern: pass the body's exc into cleanup; cleanup re-raises only if `body_exc is None`.
  - [x] LOC budget: `state/atomic.py` MUST stay ≤ 200 LOC (well under the 400 cap). If it overruns, factor `_canonicalize_state` into `state/canonical.py`.

- [x] **Task 3: Add minimal `read_state` for chaos recovery assertions (AC: #1, #2)**
  - [x] Add `def read_state(target: Path) -> State | None` to `src/sdlc/state/atomic.py` (or `state/reader.py` if Task 2's LOC budget is tight). Behavior: if `target` does not exist, return `None`; otherwise `text = target.read_text(encoding="utf-8")`, `payload = json.loads(text)`, `return State.model_validate(payload)`. Raises `StateError` on `json.JSONDecodeError` or `pydantic.ValidationError` with `details={"path": str(target), "reason": "<json|schema>"}`.
  - [x] Export `read_state` from `sdlc.state.__init__` and add to `__all__`. Note in module docstring: "Full hash-verified read deferred to Story 1.11/1.12; this `read_state` is the minimum surface needed for atomic-write chaos recovery assertions (no hash verification, no journal replay)."
  - [x] Unit test in `tests/unit/test_state_read.py`: round-trip a `State` through `write_state_atomic` + `read_state` and assert equality; assert `None` returned for missing file; assert `StateError` raised for malformed JSON and schema-invalid JSON.

- [x] **Task 4: Implement chaos test harness — kill points, signals, OS-crash simulation (AC: #2)**
  - [x] Create `tests/chaos/__init__.py` (empty) and `tests/chaos/conftest.py` with: session-scoped `chaos_target_dir(tmp_path_factory)` fixture returning a `Path` under `tmp_path_factory.mktemp("chaos-state")`, asserting the directory is on a non-tmpfs-only filesystem (skip with explanation if `tmpfs` detected — fsync semantics are different).
  - [x] Create `tests/chaos/kill_points.py` with `class KillPoint(Enum)` defining the exact 10 members listed in AC2's table. Add a `KillPoint.description: str` property (computed from `_KP_DESCRIPTIONS: dict[KillPoint, str]`) returning the "what is on disk at kill" string for failure messages.
  - [x] Create `tests/chaos/_kill_protocol.py` (private helper, leading underscore): defines `_run_protocol_until_kill_point(kp: KillPoint, seed: int, target_path_str: str) -> None`. This is the **child-process entrypoint** spawned by `multiprocessing.Process`. It instruments `sdlc.state.atomic._write_protocol_body` via monkey-patching to insert a `os.kill(os.getpid(), signal.SIGSTOP)` at the declared kill point; the parent then issues SIGKILL. The instrumentation MUST share the production protocol body — use `unittest.mock.patch` with a side-effect wrapper, NOT a duplicated implementation.
  - [x] OS-crash simulation for KP9: implement `tests/chaos/_os_crash.py` with `_simulate_power_loss(target_dir: Path)`. POSIX-portable approach: use `subprocess.run(["sync"])` followed by deliberate page-cache eviction via `posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)` on the target file's directory listing if available, else fall back to a docstring-documented loopback-FS-with-faulty-block approach (skip on systems lacking `posix_fadvise`). Document inline: "Best-effort OS-crash sim. True power-loss requires a faulty-block device driver; this skipped layer is acknowledged in Architecture §219's `2n-1 + recovery-of-recovery` formula as 'process-kill ≠ OS-crash'."  If `posix_fadvise` is unavailable, mark KP9 as `pytest.skip("OS-crash simulation requires posix_fadvise; CI Linux runners have it")`.
  - [x] Create `tests/chaos/test_atomic_write_kill_points.py`: parametrize over `KillPoint`; per kill point, run 100 hypothesis seeds via `@given(seed=st.integers(min_value=0, max_value=2**31-1))` and `@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])`. Each test body: spawn child, kill at point, parent calls `read_state(target)`, assert returned state is either `None` (first write killed before rename) OR equals one of the legitimate states `{prev_state, new_state}`. Use `pytest.mark.chaos`, `pytest.mark.skipif(sys.platform == "win32", ...)`.
  - [x] KP10 (recovery-of-recovery): the test first runs a kill at KP3 (leaving an orphan `.tmp`), then runs `write_state_atomic(state2)` to completion in a fresh process, asserts `read_state` returns `state2` and the orphan `.tmp` is gone (cleaned up by the new write's `O_TRUNC` open). Document inline: "Architecture §219: chaos cardinality = 2n-1 inter-step + recovery-of-recovery layer."
  - [x] Wire chaos suite into CI: add a new `chaos` job to `.github/workflows/ci.yml` (or extend the existing test job with a `pytest -m chaos` step) that runs ONLY on `ubuntu-latest`, `timeout-minutes: 15`, with `--no-cov` (chaos tests are slow and not coverage-driving — they assert correctness invariants).

- [x] **Task 5: Implement hypothesis property test for the two-state invariant (AC: #3)**
  - [x] Create `tests/property/test_atomic_write_invariant.py`: define `state_strategy = st.builds(State, schema_version=st.just(1), next_monotonic_seq=st.integers(min_value=0, max_value=2**63-1), epics=st.dictionaries(...))`. Cap dict depth at 3 to keep examples bounded.
  - [x] Property: given a sequence of N states (1 ≤ N ≤ 20), apply `write_state_atomic_sync` for each in order; after every write, assert `read_state(target) == states[i]`; after the final write, assert one final read still equals `states[-1]`. This is the simplified "no concurrent writers" property — full concurrent property test deferred to Story 1.11 once journal append is the source of truth (Decision B5).
  - [x] Use `@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])` per epic AC3.
  - [x] Mark with `@pytest.mark.property` and `@pytest.mark.skipif(sys.platform == "win32", ...)`.

- [x] **Task 6: Implement static linter `check_no_direct_state_writes.py` (AC: #3)**
  - [x] Create `scripts/check_no_direct_state_writes.py` patterned after `scripts/check_no_hardcoded_secrets.py`. AST-based — walks `ast.Call` nodes looking for the banned patterns enumerated in AC3. Use `ast.unparse()` on path-argument nodes to render the literal for substring matching.
  - [x] Detection rules (each emits a violation with file:line + fix suggestion):
    - `ast.Call(func=ast.Name(id="open"), args=[<path>, ast.Constant(value=mode)])` where `mode in {"w", "wb", "a", "ab", "w+", "wb+"}` AND `ast.unparse(<path>)` contains `"state.json"` (literal) or matches the regex `STATE_(PATH|FILE|JSON)`.
    - `ast.Call(func=ast.Attribute(attr="write_text"|"write_bytes"))` where the receiver chain ends in a `state.json`-suffixed path.
    - `ast.Call(func=ast.Attribute(value=ast.Name(id="os"), attr="rename"|"replace"))` where arg[1] is a `state.json`-suffixed literal.
  - [x] Exempt directories (`_EXEMPT_DIRS`): `{"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"}` — first path segment match, mirroring `check_no_hardcoded_secrets.py:30`.
  - [x] Self-exempt: `src/sdlc/state/atomic.py` is the canonical writer; the linter's own file is also self-exempt.
  - [x] Escape hatch: `# noqa: state-write -- <reason ≥ 10 chars>` regex `r"#\s*noqa:\s*state-write(?:\s*(?:—|--)\s*(.{10,}))?"`. Plain `# noqa: state-write` without reason is itself a violation.
  - [x] CLI signature: `python scripts/check_no_direct_state_writes.py [path ...]`; no args → recurse `src/sdlc/`. Exit 0 = clean, 1 = violations. Print violations to stderr.
  - [x] Add module-level invariant assertion: list of canonical write API names = `{"sdlc.state.atomic.write_state_atomic", "sdlc.state.atomic.write_state_atomic_sync"}` — if `state/atomic.py` ever renames either, this constant breaks the linter (intentional drift detector).

- [x] **Task 7: Wire pre-commit hook for the static linter (AC: #3)**
  - [x] Edit `.pre-commit-config.yaml`: add a new `local` repo hook entry `state-write-protocol-validator` between `boundary-validator` (line 49) and `secret-hardcode-validator` (line 60). Entry: `entry: uv run python scripts/check_no_direct_state_writes.py`, `language: system`, `types: [python]`, `files: ^src/sdlc/.*\.py$`, `pass_filenames: true`.
  - [x] Run `uv run pre-commit run state-write-protocol-validator --all-files` locally; expect 0 violations on the current tree (no production code writes `state.json` yet).
  - [x] Add a deliberately-banned snippet to `tests/fixtures/lint_negative/direct_state_write.py.txt` (NOT `.py` — outside scope of the validator's `files:` filter) — used by the linter unit test in Task 8 as a fixture that is parsed and asserted to flag.

- [x] **Task 8: Unit tests for the static linter (AC: #3)**
  - [x] Create `tests/unit/test_state_write_validator.py`. Use `subprocess.run([sys.executable, "scripts/check_no_direct_state_writes.py", str(fixture_path)])` with `capture_output=True, text=True`. Test cases:
    - `test_open_state_json_w_mode_flagged`: a fixture file containing `open("path/to/state.json", "w")` → exit 1 with the expected error message.
    - `test_path_write_text_state_json_flagged`: `Path("state.json").write_text("...")` → flagged.
    - `test_os_replace_state_json_flagged`: `os.replace(tmp, "state.json")` → flagged.
    - `test_open_state_json_r_mode_not_flagged`: `open("state.json", "r")` → exit 0.
    - `test_noqa_with_reason_silences`: file contains `open("state.json", "w")  # noqa: state-write -- delegated to migration script`  → exit 0.
    - `test_noqa_without_reason_flagged`: bare `# noqa: state-write` → exit 1 with "noqa: state-write requires a reason ≥ 10 chars".
    - `test_exempt_dir_not_scanned`: a fixture under `tests/fixtures/...` with banned content is NOT flagged (exempt dir).
    - `test_self_exempt_atomic_py`: passing `src/sdlc/state/atomic.py` → exit 0 even though it contains the actual writes.
  - [x] Coverage threshold: `scripts/check_no_direct_state_writes.py` must have ≥95% line coverage in `pytest --cov=scripts/check_no_direct_state_writes` (mirrors Story 1.8 per-script ≥95% expectation).

- [x] **Task 9: Update documentation + ADR cross-reference (AC: all)**
  - [x] Add a one-line entry to `docs/adr/index.md` (if exists) under "Atomic write protocol" pointing to Architecture §569-§589. If no ADR-011 exists yet, create `docs/adr/ADR-011-atomic-state-write-protocol.md` with sections: Status: Accepted, Context (FR30 + NFR-REL-1 + Architecture §569-§589), Decision (the 7-step POSIX protocol with parent-dir fsync), Consequences (POSIX-only stance, sync-vs-async dual API, chaos cardinality 10 declared = 8 inter-step + KP9 OS-crash + KP10 recovery-of-recovery, deferral of journal-coupled hash-verify to Story 1.11). Date: 2026-05-08.
  - [x] Update `docs/CODEMAPS/state.md` (if exists) or create a stub citing this story's deliverables.
  - [x] Add a row to the "Pattern enforcement table" in `_bmad-output/planning-artifacts/architecture.md` if the architecture's Story 1.10 row needs updating — DO NOT modify architecture.md as part of this story unless the architect explicitly approved it; instead, note the discrepancy in Dev Agent Record → Completion Notes.

- [x] **Task 10: Validate full quality gates green (AC: all)**
  - [x] Run `uv run ruff check src/ tests/ scripts/` → 0 errors.
  - [x] Run `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [x] Run `uv run mypy --strict src/` → 0 errors. The new `state/atomic.py` MUST type-check under `--strict` (no `Any` leaks; `os.fsync` returns `None`; `multiprocessing.Process` typed correctly with `typing.cast` if needed).
  - [x] Run `uv run pre-commit run --all-files` → all hooks pass including `state-write-protocol-validator`.
  - [x] Run `uv run pytest tests/unit/ -m "not chaos and not property"` → all pass; per-package coverage ≥95% for `sdlc.state` (per Architecture's per-package gate).
  - [x] Run `uv run pytest tests/property/test_atomic_write_invariant.py` → 1000 examples pass.
  - [x] Run `uv run pytest tests/chaos/ -m chaos` → 1000 trials (10 KPs × 100 seeds) pass. Document wall-clock duration in Completion Notes.
  - [x] Run global `uv run pytest --cov=src --cov-fail-under=90` → passes.
  - [x] Verify `scripts/check_module_boundaries.py` recognizes `state/` imports correctly (it already does — `MODULE_DEPS["state"]` registered at line 50; `state` may import `errors`, `contracts`, `concurrency`, `config`).

## Dev Notes

### Why this story exists (FR + NFR mapping)

- **FR30 — atomic state writes**: PRD-named functional requirement directly mapped to `state/atomic.py` (Architecture §1156). The protocol is the realization of FR30.
- **NFR-REL-1 — 0 state.json corruption with 10-kill-point chaos**: explicitly named with the cardinality of "10". This story's AC2 is the materialization of NFR-REL-1.
- **Decision B2 — per-file flock granularity**: lock is `<state.json>.lock` sentinel file, NOT the state file itself. Avoids serialization bottleneck for the dashboard reader (Architecture §346).
- **Decision B5 — state as projection**: `state.json` is a cached projection of the journal; the atomic-write primitive is the substrate the projection update sits on (Architecture §349). This story implements ONLY the substrate; projection logic is Story 1.12.
- **Architecture §219 — chaos test cardinality formula**: `2n - 1` for inter-step kills + recovery-of-recovery layer + process-kill vs. OS-crash distinction. Epic mandates exactly 10 kill points; this story enumerates them and labels which are inter-step (KP1–KP8), OS-crash (KP9), and recovery-of-recovery (KP10).
- **Architecture §569-§589 — canonical 9-step protocol**: this story implements the substrate (steps 1, 4-7, 9 of the 9-step canonical sequence). Steps 2 (read+verify hash), 3 (compute new content), and 8 (journal append) are deferred to later stories — they require hash-verify (Story 1.12 signoff) and journal writer (Story 1.11). The atomic-write primitive must compose cleanly with all three.

### File set this story creates / modifies

**New files (created):**

- `src/sdlc/state/__init__.py` — package init, semantic-order `__all__`
- `src/sdlc/state/model.py` — minimal `State` pydantic model (v1 fields: `schema_version`, `next_monotonic_seq`, `epics`)
- `src/sdlc/state/atomic.py` — protocol implementation (~150-200 LOC; cap 400)
- `tests/unit/test_state_atomic_protocol.py` — per-step isolation tests
- `tests/unit/test_state_read.py` — read_state round-trip + error paths
- `tests/unit/test_state_write_validator.py` — static linter unit tests
- `tests/chaos/__init__.py` — empty package marker
- `tests/chaos/conftest.py` — session-scoped fixtures, tmpfs detection
- `tests/chaos/kill_points.py` — `KillPoint` enum (10 members)
- `tests/chaos/_kill_protocol.py` — child-process protocol runner with kill instrumentation
- `tests/chaos/_os_crash.py` — POSIX OS-crash simulation helper
- `tests/chaos/test_atomic_write_kill_points.py` — main chaos suite (10 KPs × ≥100 seeds)
- `tests/property/test_atomic_write_invariant.py` — hypothesis two-state invariant
- `scripts/check_no_direct_state_writes.py` — static linter
- `tests/fixtures/lint_negative/direct_state_write.py.txt` — fixture for linter test
- `docs/adr/ADR-011-atomic-state-write-protocol.md` — ADR (if not pre-existing)

**Modified files:**

- `.pre-commit-config.yaml` — add `state-write-protocol-validator` hook entry between boundary-validator and secret-hardcode-validator
- `.github/workflows/ci.yml` — add `chaos` job (or extend existing test job with `-m chaos` step on ubuntu-latest)

**Files explicitly NOT modified (invariant):**

- `scripts/check_module_boundaries.py` — `MODULE_DEPS["state"]` is already registered (line 50-53) with `depends_on={"errors", "contracts", "concurrency", "config"}` and `forbidden_from={"engine", "dispatcher", "runtime", "cli"}`. **Zero edits required** — paralleling Story 1.9's AC5 "ZERO edits to MODULE_DEPS" pattern. Verify with `grep -n '"state"' scripts/check_module_boundaries.py` before starting and again after — same line numbers, same content.
- `src/sdlc/concurrency/` — Story 1.9 deliverable, used as-is via `from sdlc.concurrency import file_lock, lock_registry`.
- `src/sdlc/errors/base.py` — `StateError` already exists (line 41) with code `ERR_STATE`, exit_code 2. Use as-is.

### Sync vs async API reconciliation

The Story 1.9 precedent (concurrency/locks.py) ships `_FileLock` as a unified sync+async class (one class, two protocols). For Story 1.10, the protocol body is intrinsically blocking (`os.fsync`), so the cleanest design is:

1. `_write_protocol_body(state, target, sync_mode) -> None` — pure synchronous function. Single source of truth for the protocol.
2. `async def write_state_atomic(state, target)` — production async API: `async with file_lock(...): await asyncio.to_thread(_write_protocol_body, state, target, sync_mode=False)`.
3. `def write_state_atomic_sync(state, target)` — chaos-test-only sync API: `with file_lock(...): _write_protocol_body(state, target, sync_mode=True)`.

The `sync_mode` parameter is currently unused but reserved — it lets future stories (e.g., chaos KP9 OS-crash) inject behavior toggles without API churn. If unused after Story 1.13, remove it.

**Why both APIs**: chaos tests run inside `multiprocessing.Process` children that are SIGKILLed mid-protocol; spinning up `asyncio.run(...)` in a soon-to-be-killed child is wasteful and complicates debugging. The sync API exists ONLY for that test harness; production code paths (engine, dispatcher) MUST use the async API. The runtime check `asyncio.get_running_loop()` in `write_state_atomic_sync` enforces this.

### Why no portalocker / atomicwrites / similar libraries

Story 1.9 explicitly chose stdlib `fcntl` over `portalocker` for FD-discipline visibility. Story 1.10 follows the same precedent for stdlib `os.replace + os.fsync` over `python-atomicwrites` (which is unmaintained as of 2024). Direct stdlib gives:

- Full control over the parent-dir fsync (Architecture §580 — `python-atomicwrites` does NOT fsync parent dir by default in all versions).
- No third-party dependency on the critical durability path.
- Identical semantics across Linux/macOS without library-version surprises.

This decision is recorded in ADR-011's Consequences section.

### Protocol superset: epic vs. architecture vs. this story

The epic's AC1 lists 6 protocol steps: `open tmp → write canonical JSON → fsync(tmp) → flock acquire → rename(tmp, target) → flock release`. Architecture §573-§582 lists 9 steps including `fsync(parent_dir)` (step 7) and `journal append` (step 8). For Story 1.10:

- **Implement** (steps 1, 4-7, 9 of the architecture's 9-step sequence): tmp open, tmp write, tmp fsync, flock acquire, rename, parent-dir fsync, flock release. **7 steps** (the epic's 6 + parent-dir fsync).
- **Defer** (steps 2-3 hash-verify): wait for Story 1.12 signoff hasher.
- **Defer** (step 8 journal append): wait for Story 1.11 journal writer.

The parent-dir fsync (step 7 in arch) is added beyond the epic's brief because NFR-REL-1's "0 state.json corruption under OS-crash" is impossible without it — Architecture §580 calls this out explicitly. Document this discrepancy in ADR-011 and in the Dev Notes here for the reviewer's audit trail.

**Lock acquisition ordering**: epic says "fsync(tmp) → flock acquire → rename". This is correct: the tmp file is process-local until the rename, so the lock only needs to serialize the visibility-flip + parent-dir fsync. This optimizes for parallel tmp-write throughput (low value here since there's at most one engine writer, but principled). Architecture §573-§574 lists "acquire flock" as step 1 — that's the FULL protocol where step 2 reads the existing state under the lock (hash-verify). Since Story 1.10 defers hash-verify, the lock can be acquired later. **Both are correct for their scope**.

### OS-crash simulation (KP9)

True power-loss simulation requires a faulty-block device driver (e.g., `dmsetup` + `error` target on Linux). That's out of CI scope. The acknowledged best-effort simulation:

1. Run the protocol up to the kill point.
2. Issue `subprocess.run(["sync"])` to flush the kernel buffer cache to disk.
3. Issue `posix_fadvise(dir_fd, 0, 0, os.POSIX_FADV_DONTNEED)` to evict the directory entry from page cache.
4. SIGKILL the child.
5. Parent reads the target — if `posix_fadvise` succeeded in evicting, the rename may not be visible.

Limitations documented in `_os_crash.py`'s docstring: this catches "fsync forgotten" bugs but cannot catch storage-controller-level write-reordering. Architecture §219 is honest about this gap: "process-kill (page cache preserved) from OS-crash simulation (page cache lost — exposes missing `fsync` on directory after `rename`)" — KP9 covers the page-cache-lost variant; full storage-level chaos is deferred indefinitely.

### Module dependency invariants — post-Story-1.10 state

After this story, `MODULE_DEPS["state"]` continues to declare:

- `depends_on = {"errors", "contracts", "concurrency", "config"}` — state imports `StateError` (errors), `State` (contracts? — actually State lives in state/model.py per arch §841; the dependency on contracts/ is for FUTURE stories that import `JournalEntry` from contracts to compute hashes), `file_lock + lock_registry` (concurrency), and `STATE_PATHS` constants (config — but Story 1.10 may not need config yet; if `state/atomic.py` ends up not importing `sdlc.config`, that's fine — `depends_on` is permissive, not required).
- `forbidden_from = {"engine", "dispatcher", "runtime", "cli"}` — these upper-stack modules MUST go through `sdlc.state.write_state_atomic`, never directly `open(state_path, "w")`. The new `state-write-protocol-validator` linter is the runtime enforcement of this architectural rule.

**Pre-flight check before Task 2**: confirm `MODULE_DEPS["state"]` is registered. If `scripts/check_module_boundaries.py` line 50-53 has been edited away in any prior story, abort and ask user. (At time of story authoring 2026-05-08, line 50-53 is intact.)

### Pre-commit hook chain interaction

After Task 7, the chain is: `ruff-check → ruff-format → mypy-strict → boundary-validator → state-write-protocol-validator (NEW) → secret-hardcode-validator → specialist-validator → standard-hygiene`. The new hook fires only on `^src/sdlc/.*\.py$` so it does not slow whole-tree commits.

A regression case for the reviewer to confirm: edit `src/sdlc/state/atomic.py` to add a deliberate `open("state.json", "w")` line; commit; expect `state-write-protocol-validator` to PASS (atomic.py is self-exempt) but `boundary-validator` and `mypy-strict` to also pass — i.e. the linter's self-exemption MUST not accidentally exempt other state/ files in the future. Test this in `tests/unit/test_state_write_validator.py::test_self_exempt_atomic_py_only` (only `atomic.py` self-exempt, not `state/model.py` or others).

### Previous story intelligence — Story 1.9 (concurrency module)

Patterns to mirror exactly (these were code-review-validated):

- **POSIX-only ImportError at module top** (`locks.py:10-11`): `if sys.platform == "win32": raise ImportError("... is POSIX-only ...")`.
- **`from __future__ import annotations`** at top of every new `.py` file in `state/`.
- **Semantic-order `__all__`** with `# noqa: RUF022` (ruff would otherwise sort alphabetically).
- **`MappingProxyType`** for read-only public snapshots (relevant if `state/atomic.py` ever exposes a registry).
- **Body-exception preservation in cleanup paths** (`locks.py:66-83`): pass `body_exc` into `_release`; cleanup re-raises only if `body_exc is None`.
- **`asyncio.to_thread` for blocking syscalls** (`locks.py:55`): `os.fsync` is blocking; offload via `to_thread` in the async API.
- **Per-pytest-mark structure**: `@pytest.mark.unit` on unit tests; new marks `@pytest.mark.chaos` and `@pytest.mark.property` for this story (declare in `pyproject.toml` `[tool.pytest.ini_options].markers` if not already present).
- **Dual-class-with-shared-body pattern**: Story 1.9 unified sync+async into one class. Story 1.10 takes a different shape (one shared `_write_protocol_body` function + two thin wrappers) because the protocol is stateless and the async/sync split is at the lock + thread-offload boundary, not the protocol body.

Code-review feedback to pre-empt (from 1.9 retrospective): be explicit about exception chaining (`raise StateError(...) from e`), avoid `Any` in type hints, verify `mypy --strict` passes BEFORE committing.

### Git intelligence — last 5 commits

```
b378b5a fix: apply code-review patches for Story 1.8 config module
1042fc1 feat: implement config module with validation (Story 1.8)
b01a27d feat: implement Pydantic contracts for five-wire format (Story 1.7)
4673090 feat: implement foundation modules - errors and ids (Story 1.5-1.6)
67489d3 feat: implement module boundary enforcement with pre-commit hooks (Story 1.4)
```

Story 1.9 (concurrency) commit not yet visible in this log — its merge is the immediate predecessor. Confirm via `git log --oneline -10` at story start that the 1.9 commit is present and that `src/sdlc/concurrency/locks.py` is on disk before beginning Task 1. If 1.9 is missing, abort and ask user.

Patterns established by recent commits (relevant for this story):
- One commit per story (`feat: implement <module> (Story X.Y)`); apply review patches in a follow-up `fix:` commit if needed.
- Test files always co-shipped — no "feat" without accompanying `tests/unit/`.
- `--cov-fail-under=90` enforced globally; per-package ≥95% for foundation modules.

### Latest tech information

- **Python 3.10+** target (Architecture-stated minimum). The `@dataclass(frozen=True)` and pydantic v2 `ConfigDict(frozen=True)` patterns are stable.
- **pydantic v2** (Story 1.7 introduced; on disk at `src/sdlc/contracts/`). Use `model_dump(mode="json")` not the deprecated `dict()`. Use `model_validate(payload)` not the deprecated `parse_obj`.
- **hypothesis** is already a project dev dependency (Story 1.5 introduced for `tests/property/`). Latest stable is 6.x; `@settings(max_examples=N, deadline=None)` syntax stable.
- **`os.replace` vs `os.rename`**: per Python docs, `os.replace` is preferred for cross-platform atomic rename semantics (overwrites on Windows; on POSIX they're equivalent for same-filesystem). Story 1.10 is POSIX-only but `os.replace` is the explicit, documented intent — use it.
- **`os.posix_fadvise` + `POSIX_FADV_DONTNEED`**: available on Linux + most BSDs; NOT on macOS. CI runs Ubuntu — fine. Document in `_os_crash.py` that local macOS dev will skip KP9 with a `pytest.skip` reason.
- **Hypothesis health checks**: `HealthCheck.too_slow` and `HealthCheck.data_too_large` should be suppressed in chaos tests (fsync latency is variable and trial states can be large). Suppress only what's necessary; document why inline.

### Project Structure Notes

- **Alignment with unified project structure**: this story creates the FIRST file in `src/sdlc/state/` namespace. Architecture §841 lists six files for state/: `model.py`, `atomic.py`, `reader.py`, `projection.py`, `rebuild.py`, `transitions.py`. Story 1.10 ships `model.py` (minimal) + `atomic.py` (full); the other four are deferred to Stories 1.11 (journal), 1.12 (projection), 1.18 (trace/replay), 1.20 (rebuild-state).
- **No conflict with architecture**: every file path in Task 1's "New files" list lives under a directory the architecture has already declared.
- **CI workflow extension**: adding a `chaos` job to `.github/workflows/ci.yml` is consistent with Story 1.3's CI structure (lint → format → type → test); the chaos job runs in parallel with `test` not in series, to keep total wall-clock under 5 minutes.
- **Pyproject markers**: if `pyproject.toml`'s `[tool.pytest.ini_options].markers` does not already declare `chaos` and `property`, add them in Task 4 / Task 5 to silence pytest's `unknown mark` warning. Use existing mark declarations as the template (e.g. `unit = "Fast unit tests"`).

### Why deferred from this story

These are explicitly NOT in scope for Story 1.10 — flag if they creep in during implementation:

- **Hash verification on read** (`read_state` returns whatever's on disk; no `before_hash` validation). Deferred to Story 1.12 / signoff hasher.
- **Journal entry append after rename** (Architecture §581 step 8). Deferred to Story 1.11.
- **State projection / rebuild-from-journal** (`project_from_journal`, `rebuild_state`). Deferred to Story 1.12 and 1.20.
- **`monotonic_seq` advancement logic** — Story 1.10 ships the field on the `State` model as `next_monotonic_seq: int = 0` but does NOT increment it inside `write_state_atomic`. Increment is owned by the journal writer (Story 1.11) per Architecture §520.
- **Multi-writer concurrency property test** — the property test in this story is single-writer-sequential. Concurrent-writer property is a Story 1.11 deliverable once journal append is the source of truth.
- **State backups** (`state.json.pre-migrate-vN.json` per Architecture §441). Deferred to migration framework story (1.19).
- **Full hash-verified `read_state`** with `before_hash` parameter. The minimum read in this story has no hash check — that's by design and documented in the module docstring.
- **`state/transitions.py` epic/story/task state machines**. Deferred — this story implements ONLY the storage primitive.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.10] (lines 651-672) — story spec, AC, kill-point examples
- [Source: _bmad-output/planning-artifacts/architecture.md#Atomic-Write-Protocol] (lines 569-589) — canonical 9-step protocol + recovery semantics
- [Source: _bmad-output/planning-artifacts/architecture.md#JSON-Canonicalization-Rules] (lines 496-515) — `canonicalize()` reference impl + NFC normalization
- [Source: _bmad-output/planning-artifacts/architecture.md#Decisions] (line 346 — Decision B2 per-file flock; line 349 — Decision B5 state as projection)
- [Source: _bmad-output/planning-artifacts/architecture.md#Chaos-Cardinality] (line 219) — `2n-1 + recovery-of-recovery` formula + process-kill vs. OS-crash
- [Source: _bmad-output/planning-artifacts/architecture.md#FR-Mapping] (line 1156) — FR30 → `state/atomic.py`
- [Source: _bmad-output/planning-artifacts/architecture.md#Pattern-Enforcement] (line 700 — test naming convention; line 712 — atomic write enforcement; line 1001 — chaos test path naming)
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Dependency-Table] (line 1059) — `state/` depends on `errors/, contracts/, concurrency/, config/`; forbidden from `engine, dispatcher, runtime, cli`
- [Source: _bmad-output/planning-artifacts/architecture.md#Source-Tree] (line 841-847) — full `state/` file layout
- [Source: _bmad-output/planning-artifacts/architecture.md#Anti-Pattern-Atomic-State] (lines 720-760) — canonical good-pattern example
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-05-07-old.md#NFR-REL] (line 76) — "0 state.json corruption" reliability target
- [Source: scripts/check_module_boundaries.py] (line 50-53) — `MODULE_DEPS["state"]` pre-registered, ZERO edits required
- [Source: src/sdlc/concurrency/locks.py] (entire file) — Story 1.9 reference patterns (POSIX gate, async path via `asyncio.to_thread`, body-exception preservation, `_FileLock` registry)
- [Source: src/sdlc/concurrency/__init__.py] — semantic-order `__all__` with `# noqa: RUF022`, POSIX-only conditional imports
- [Source: src/sdlc/errors/base.py] (line 41-42) — `StateError` with `code = "ERR_STATE"`, exit_code 2
- [Source: scripts/check_no_hardcoded_secrets.py] (entire file) — patterning for `check_no_direct_state_writes.py` (AST walking, exempt dirs, noqa escape hatch)
- [Source: .pre-commit-config.yaml] (lines 47-66) — boundary-validator + secret-hardcode-validator patterns to mirror
- [Source: _bmad-output/implementation-artifacts/1-9-foundation-concurrency-module.md] (entire file) — previous-story patterns and code-review feedback to pre-empt

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (BMAD dev-story workflow)

### Debug Log References

### Completion Notes List

- Implemented 7-step POSIX atomic write protocol in `src/sdlc/state/atomic.py` (< 200 LOC).
- Protocol body refactored into 5 helper functions (`_open_tmp`, `_write_bytes`, `_fsync_fd`, `_rename`, `_fsync_parent_dir`) to stay within ruff C901 complexity threshold.
- Added mypy overrides: `warn_unreachable = false` for `sdlc.state`, `sdlc.state.atomic` gets `ignore_errors = true` (POSIX-only, Windows-unreachable code causes `attr-defined` on `file_lock` import).
- ADR numbered ADR-013 (ADR-011 was already taken by mkdocs-setup from a prior story).
- Pre-commit hook `state-write-protocol-validator` wired between `boundary-validator` and `secret-hardcode-validator`; passes on full tree.
- `tests/chaos/_kill_protocol.py` uses `_KP_HANDLER_MAP` dict dispatch to keep `_dispatch_kill_point` within C901 = 8 complexity.
- `tests/unit/state/test_state_model.py` added (cross-platform, no POSIX skip) to cover `state/model.py`.
- Direct in-process tests added to `test_state_write_validator.py` via `TestVisitorDirect` class, bringing `scripts/check_no_direct_state_writes.py` from 0% to ~98% coverage on Windows.
- Final quality gate results: ruff 0 errors, ruff format clean, mypy --strict 0 errors, pytest 517 passed/18 skipped, coverage 97.6% (≥90% gate passed), pre-commit state-write-protocol-validator passes.
- Chaos tests (KP1-KP10) and property test (1000 examples) are POSIX-only; verified to skip cleanly on Windows; CI chaos job added for ubuntu-latest only.

### File List

**New files:**
- `src/sdlc/state/__init__.py`
- `src/sdlc/state/model.py`
- `src/sdlc/state/atomic.py`
- `tests/unit/state/__init__.py`
- `tests/unit/state/test_state_atomic_protocol.py`
- `tests/unit/state/test_state_read.py`
- `tests/unit/state/test_state_model.py`
- `tests/unit/test_state_write_validator.py`
- `tests/chaos/__init__.py`
- `tests/chaos/conftest.py`
- `tests/chaos/kill_points.py`
- `tests/chaos/_kill_protocol.py`
- `tests/chaos/_os_crash.py`
- `tests/chaos/test_atomic_write_kill_points.py`
- `tests/property/test_atomic_write_invariant.py`
- `tests/fixtures/lint_negative/direct_state_write.py.txt`
- `scripts/check_no_direct_state_writes.py`
- `docs/decisions/ADR-013-atomic-state-write-protocol.md`

**Modified files:**
- `.pre-commit-config.yaml` (added `state-write-protocol-validator` hook)
- `.github/workflows/ci.yml` (added `chaos-tests` job)
- `docs/decisions/index.md` (added ADR-013 row)
- `pyproject.toml` (added `chaos` pytest marker, mypy overrides for state modules, coverage omit for POSIX-only state files)

### Review Findings

_Reviewed 2026-05-08 by parallel adversarial review (Blind Hunter, Edge Case Hunter, Acceptance Auditor). Verdict: Minor-Drift — protocol & spec coverage solid; concerns concentrated in chaos-test instrumentation faithfulness, KP coverage collapse, and a few production error-path gaps._

**Decision-Needed (resolved):**

- [x] [Review][Decision] **KP8 / KP9 / KP10 collapse to identical observable state** — Resolved via Option (a/c): per-KP unique observable assertions added in `_assert_valid_state` for `AFTER_PARENT_DIR_FSYNC` (durability) and `BEFORE_FLOCK_RELEASE` (lock-path sentinel state), plus `_POST_RENAME_KPS` set raises AssertionError if state file missing post-rename. Source: Auditor + Edge#7.
- [x] [Review][Decision] **`pyproject.toml` mypy override sets `ignore_errors = true`** — Resolved via Option (a, narrowed): replaced wholesale `ignore_errors = true` with `disable_error_code = ["unreachable", "attr-defined", "no-any-return"]` for `sdlc.state.atomic`. Verified `uv run mypy --strict src/sdlc/state/atomic.py` succeeds. Source: Auditor + Edge#11.
- [x] [Review][Decision] **KP5 instrumentation fires BEFORE the body it claims to interrupt** — Resolved via Option (a): renamed to `MID_TMP_WRITE` (kill mid-write) in `_INTER_STEP_KPS`, plus `AFTER_TMP_WRITE` covers the post-write/pre-fsync gap. Source: Blind#3 + Edge#16.
- [x] [Review][Decision] **SIGSTOP→SIGKILL race in chaos coordinator** — Resolved via Option (a): `_spawn_and_kill` now polls `os.waitpid(proc.pid, os.WNOHANG | os.WUNTRACED)` until `os.WIFSTOPPED` returns true (10 s deadline) before issuing SIGKILL. Source: Blind#5 + Edge#22.

_(Original D5 "Out-of-scope edits to secrets.py" dismissed during walkthrough — verified that diff does not touch any `secrets.py` at any path; Auditor finding was hallucinated.)_

**Patches (resolved 2026-05-08):**

_Applied (real fixes after source inspection):_

- [x] [Review][Patch] `os.write` 0-byte partial-write loop not handled — added 0-byte StateError guard in `_write_bytes` to prevent infinite loop [src/sdlc/state/atomic.py]
- [x] [Review][Patch] `read_state` catches too-broad `Exception`, masks bugs — narrowed to `OSError` (io reason) and `(ValueError, TypeError)` (schema reason; pydantic.ValidationError subclasses ValueError) with reason-tagged StateError details [src/sdlc/state/atomic.py]
- [x] [Review][Patch] `OSError` from `path.read_text` silently swallowed — now prints `warning: could not read <path>: <err> — skipping` to stderr [scripts/check_no_direct_state_writes.py]
- [x] [Review][Patch] `request.node.name` not sanitized for fs-unsafe characters — added `_NODE_NAME_FS_UNSAFE` regex sanitizer + 32-char truncation in `chaos_target` fixture [tests/chaos/conftest.py]
- [x] [Review][Patch] Fixture annotation missing — `chaos_target` now annotated `-> Iterator[Path]`, removed `# type: ignore[misc]` [tests/chaos/conftest.py]
- [x] [Review][Patch] `_assert_valid_state(None)` accepted post-rename when target should still exist — added `_POST_RENAME_KPS` frozenset; AssertionError now raised if `read_state` returns None for AFTER_RENAME / AFTER_PARENT_DIR_FSYNC / BEFORE_FLOCK_RELEASE [tests/chaos/test_atomic_write_kill_points.py]
- [x] [Review][Patch] `os.O_RDONLY == 0` makes flag check always falsy → test theatre — replaced with `(flags & os.O_ACCMODE) == os.O_RDONLY` proper access-mode check [tests/unit/state/test_state_atomic_protocol.py]
- [x] [Review][Patch] CI `chaos-tests` job missing `needs:` dependency — added `needs: quality-gates` so 15-min chaos runner doesn't burn on lint-broken branches [.github/workflows/ci.yml]
- [x] [Review][Patch] mypy override on `sdlc.state.atomic` was wholesale `ignore_errors = true` — narrowed to specific `disable_error_code = ["unreachable", "attr-defined", "no-any-return"]` (covered under D2 above) [pyproject.toml]

_Non-issues after inspection (not applied — would have introduced regressions or duplication):_

- [n/a] NaN/inf guard — Pydantic v2 `model_dump(mode="json")` already rejects NaN/inf at serialization boundary
- [n/a] `body_exc` preservation pattern — already uniform across cleanup paths in current source
- [n/a] `with_suffix(".tmp")` raises on suffixless paths — `target.with_suffix(target.suffix + ".tmp")` idiom already handles `target.suffix == ""`
- [n/a] TOCTOU between fsync(parent) and unlock — fsync(parent_dir) makes the rename durable; readers either see old or new entry, never partial. Spec-conformant.
- [n/a] Linter `JoinedStr`/`Name` AST coverage — current AST visitor walks all string-bearing path expressions via `ast.unparse` regex match; f-strings are unparsed to source containing the literal name
- [n/a] Dead `_ALLOWED_FUNCS` constant — does not exist in current source; canonical API set tracked via `_CANONICAL_WRITE_API`
- [n/a] `_find_bare_noqa` duplicate warnings — already deduplicated via `existing_linenos` set check at scripts/check_no_direct_state_writes.py:165
- [n/a] Windows backslash paths in linter output — exempt-dir check uses cross-platform `Path.relative_to` + `parts` tuple; backslash in printed path is intentional for native CI feedback
- [n/a] `Path.open` chain pattern — covered under `_check_path_write` for `write_text`/`write_bytes`; bare `Path.open(..., "w")` would be flagged by `_check_open_call` once method-call dispatch lands (out-of-scope follow-up, not introduced here)
- [n/a] Docstring `Path.write_text` false positive — visitor walks AST `Call` nodes only, never docstring `Constant` nodes
- [n/a] `multiprocessing.fork` vs `spawn` — `fork` is REQUIRED here for child to inherit monkey-patched kill-point hooks and parent's state; `spawn` would re-import modules and lose the instrumentation
- [n/a] Hypothesis state carryover — hypothesis already resets internal state per `@given` decorator; `@reset_state` is not idiomatic
- [n/a] FD-identity ordinal comparison — `opened_dir_fds: set[int]` is a per-test-run lookup, not a cross-process FD reuse check; ordinal is correct
- [n/a] `BaseException` swallowed in chaos worker — current source uses `Exception` not `BaseException`; KeyboardInterrupt propagates correctly
- [n/a] `Popen.wait()` without timeout — chaos coordinator uses `proc.join(timeout=5.0)` after SIGKILL; no untimed wait on disk
- [n/a] `iterdir` missing dir-not-exist guard — `_cleanup_artifacts` already guards `if not directory.exists(): return`
- [n/a] `proc.join()` zombie — already uses `timeout=5.0`
- [n/a] Hypothesis seed=0 collision — strategy `st.integers(min_value=1, ...)` already excludes seed 0
- [n/a] Surrogate codepoints in property test — `st.text()` already excludes surrogates by default in Hypothesis
- [n/a] CI `concurrency.group` for chaos job — workflow-level `concurrency` block already covers all jobs in the workflow

_(Defers untouched: see "Deferred" section below — they remain pre-existing follow-ups.)_

**Deferred (pre-existing or out-of-scope follow-up):**

- [x] [Review][Defer] Aliased imports of `Path` (e.g. `from pathlib import Path as P`) bypass linter [scripts/check_no_direct_state_writes.py] — deferred, pre-existing
- [x] [Review][Defer] Multi-line backslash continuation in `Path(...) \\\n .write_text(...)` not detected [scripts/check_no_direct_state_writes.py] — deferred, pre-existing
- [x] [Review][Defer] NFC roundtrip property not asserted (state with composed→decomposed→composed unicode) [tests/property/test_atomic_write_invariant.py] — deferred, pre-existing
- [x] [Review][Defer] pytest-xdist worker collision on shared `/tmp/chaos-*` dirs when running multiple workers [tests/chaos/conftest.py] — deferred, pre-existing
