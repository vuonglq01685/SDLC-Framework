# ADR-014: Append-Only Journal Protocol

**Status:** Accepted
**Date:** 2026-05-08
**Story:** 1.11

## Context

FR31 requires a durable, append-only journal (`journal.log`) that serves as the single
source of truth for state replay (Decision B5, Architecture §349). NFR-REL-2 demands
the append-only invariant be verified under a property test: file grows-only, line bytes
immutable, no mutation API. NFR-OBS-1 lists `journal.log` as one of three observability
streams (Decision E3, Architecture §480).

Architecture §493 prohibits any `open()` call on state/journal files outside of their
canonical writer modules. Architecture §581 step 8 declares journal append as a separate
atomic protocol from the state-write protocol (Story 1.10).

`JournalEntry` (pydantic v2) is the wire-format contract shipped by Story 1.7. The
`file_lock` async context manager is the flock primitive shipped by Story 1.9.

## Decision

### 7-Step POSIX Append Protocol

1. Acquire `flock(<journal>.lock)` via `file_lock(lock_path)` — sentinel file, NOT the
   journal itself (Decision B2 per-file flock granularity, mirrors `state/atomic.py`).
2. **(Step 2.5)** While holding the lock, read the highest existing `monotonic_seq`
   via `_read_highest_seq`. Validate `entry.monotonic_seq > highest`; raise `JournalError`
   otherwise. Lock serializes concurrent appenders so both cannot read the same highest
   value and both succeed.
3. Canonicalize entry: `model_dump(mode="json")` → recursively NFC-normalize strings →
   `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"`.
   Terminating `\n` is REQUIRED for JSONL (distinct from hash-canonicalization which omits it).
4. `os.open(O_WRONLY | O_CREAT | O_APPEND, 0o644)` — kernel-enforced atomic-to-EOF.
   POSIX guarantees each `write(2)` on an `O_APPEND` fd is atomic to EOF.
5. Drain bytes via short-write loop with 0-byte-write guard (mirrors `state/atomic.py:_write_bytes`).
6. `os.fsync(fd)` — durability of appended bytes.
7. `os.close(fd)`. Release flock (automatic on `__aexit__`).

**Parent-directory fsync on first-ever `O_CREAT`** matches `state/atomic.py:119-134`;
no power-loss window for the very first journal entry. Subsequent appends do NOT
re-fsync the directory because `O_APPEND` extends an existing inode in place; the
directory entry is not modified after the file already exists.

### Dual Sync/Async API

- `async def append(entry, journal_path)` — production API; uses `asyncio.to_thread` to
  avoid blocking the event loop on `os.fsync` and the linear `_read_highest_seq` scan.
- `def append_sync(entry, journal_path)` — sync-only entrypoint for property/chaos tests
  running in subprocess-killed children with no event loop. Raises `JournalError` if called
  from inside a running loop (footgun guard mirroring `state.atomic.write_state_atomic_sync`).
- Single `_append_protocol_body` function is the shared source of truth; no logic divergence.

### Reader as Last-Line-of-Defence

`iter_entries` tracks the previous yielded `monotonic_seq` and raises
`JournalError(step="reader_invariant")` on any regression — protecting downstream
projection (Story 1.12) from silently replaying a corrupted audit chain.

Malformed lines are skipped with a stderr warning (permissive) to support Story 1.20's
`sdlc rebuild-state` recovery path. The seq-regression detection catches the dangerous
case: a missing entry would likely break the sequence.

### Static Linter

`scripts/check_no_journal_mutation.py` is an AST-based linter that rejects:

- `open(journal_path, w/wb/a/ab/r+/rb+/w+/wb+)` outside `journal/writer.py`
- `Path(journal_path).write_text/write_bytes(...)`
- `os.replace/os.rename(..., journal_path)` as destination
- `f.seek(...); f.write(...)` on the same handle (seek+write anti-pattern)
- `os.lseek(fd, ...); os.write(fd, ...)` on the same fd (syscall-level equivalent)

Wired as `journal-append-only-validator` in `.pre-commit-config.yaml` between
`state-write-protocol-validator` and `secret-hardcode-validator`.

### Module Dependency Constraint on `_normalize_strings`

`MODULE_DEPS["journal"].depends_on` = `{"errors", "contracts", "concurrency", "config"}`.
`state` is NOT in this set, so `journal/writer.py` cannot import from `sdlc.state`.
The `_normalize_strings` helper is duplicated from `state/atomic.py` into `journal/writer.py`
with a documentation comment requiring both copies to stay in lockstep.

## Consequences

**Accepted:**

- Writer is POSIX-only (Linux/macOS); reader is cross-platform (pure file read). Windows
  users get `JournalError(step="windows_unsupported")` from `append`/`append_sync` (review
  fix Edge M6 — symmetric with POSIX so cross-platform `except JournalError` callers work
  on every OS) but can still read journals.
- Permissive reader (skip malformed lines) trades a potential silent-skip for
  rebuild-state recoverability. Mitigated by `reader_invariant` seq-regression detection.
- `_normalize_strings` duplicated from `state/atomic.py` into `sdlc.journal._canonical` —
  must stay in lockstep, enforced by `tests/unit/journal/test_canonical_lockstep.py`.
  Factoring it up the dependency graph requires restructuring `MODULE_DEPS` (out of v1 scope).
- **NFC normalization on hash-suffix string fields:** `_normalize_strings` recurses into
  `before_hash`/`after_hash`. The `JournalEntry` contract (Story 1.7) regex
  `^sha256:[0-9a-f]{64}$` ensures these fields are pure hex, making the NFC pass a no-op
  at the contract boundary. **If the contract is ever loosened**, `_normalize_strings`
  must add a sentinel-skip set to avoid silently rewriting hash bytes; tracked in
  `_bmad-output/implementation-artifacts/deferred-work.md`.
- **Local-disk-only assumption:** the framework runs on the user's local filesystem per
  the architecture threat model. NFS / fuse / virtio-9p multi-process file-cache
  visibility (where the highest-seq scan can read a stale view despite holding flock) is
  out of v1 scope; tracked as a future "remote-filesystem hardening" story in
  `deferred-work.md`.
- Multi-writer concurrency property test deferred — single-writer-sequential is sufficient
  for v1 (the lock already serializes; the property test validates the lock-protected
  invariant).

**Precedent:**

ADR-013 (Story 1.10) established the dual-API pattern (async + sync), the body-exception
preservation pattern, and the `O_WRONLY | O_CREAT | O_TRUNC` flag visibility rationale.
ADR-014 applies the same patterns to `O_WRONLY | O_CREAT | O_APPEND`.
