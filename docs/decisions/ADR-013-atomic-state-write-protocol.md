# ADR-013: Atomic State Write Protocol

**Status:** Accepted
**Date:** 2026-05-08
**Story:** 1.10 — Atomic Write Protocol + Chaos Tests at 10 Kill Points

---

## Context

FR30 (atomic state writes) and NFR-REL-1 ("0 state.json corruption under OS-crash") require a
crash-safe protocol for updating `state.json`. Architecture §569-§589 defines a canonical 9-step
sequence. This ADR records the decisions made in implementing the substrate layer (steps 1, 4-7, 9)
for Story 1.10.

Key drivers:
- **FR30**: Every state.json update must be atomic — no process crash can leave a partial/malformed file.
- **NFR-REL-1**: Zero corruption across 10 declared kill points (including OS-crash simulation).
- **Decision B2** (Architecture §346): Per-file flock granularity; lock sentinel is `<state.json>.lock`, NOT the state file itself.
- **Decision B5** (Architecture §349): `state.json` is a cached projection of the journal; the atomic-write primitive is the substrate the projection update sits on.

---

## Decision

Implement a 7-step POSIX-only atomic write protocol in `src/sdlc/state/atomic.py`:

1. `open <target>.tmp` (`O_CREAT | O_WRONLY | O_TRUNC`, mode `0o644`)
2. Write canonicalized JSON bytes (`sort_keys=True`, `ensure_ascii=False`, `separators=(",",":")`, NFC-normalized, terminating `\n`)
3. `os.fsync(tmp_fd)` — durability of tmp content
4. Acquire `flock(<target>.lock)` via Story 1.9 `file_lock(...)` async context manager
5. `os.replace(tmp_path, target_path)` — atomic rename
6. `os.fsync(parent_dir_fd)` — directory entry durability (Architecture §580; critical for OS-crash survival)
7. Release `flock` (automatic on `__aexit__`)

**Protocol superset**: The epic's AC1 lists 6 steps (omitting parent-dir fsync). Step 6 is added
because NFR-REL-1's "0 state.json corruption under OS-crash" is impossible without it
(Architecture §580: "critical — survives OS crash, not just process kill").

**No third-party libraries**: stdlib `os.replace + os.fsync` is used directly over `python-atomicwrites`
(unmaintained) and `portalocker` (Story 1.9 precedent). Direct stdlib gives full control over
parent-dir fsync that libraries do not guarantee.

**Dual API**: A synchronous `write_state_atomic_sync` is provided exclusively for chaos tests running
in `multiprocessing.Process` children (no event loop). Production code MUST use the async
`write_state_atomic`. A runtime guard raises `StateError` if `write_state_atomic_sync` is called
from inside an event loop.

---

## Consequences

### POSIX-only stance

`state/atomic.py` raises `ImportError` on Windows. `state/model.py` and `state/__init__.py` remain
importable on Windows (stubs raise `NotImplementedError` at call time) so `mypy --strict` and
model unit tests can run cross-platform.

### Chaos test cardinality

10 declared kill points:
- KP1-KP8: inter-step kills (8 points between protocol steps)
- KP9: OS-crash simulation (page-cache eviction via `posix_fadvise` — best effort)
- KP10: recovery-of-recovery (orphan `.tmp` from prior kill does not block next write)

Architecture §219 formula: `2n-1` inter-step + recovery-of-recovery + process-kill vs. OS-crash distinction.

### Deferral of journal-coupled operations

Steps 2-3 (hash-verify existing state) and step 8 (journal append) are deferred:
- Step 8 journal append: Story 1.11
- Hash-verified read: Story 1.12
- Full `read_state` with `before_hash` parameter: Story 1.12

The minimal `read_state` shipped here has no hash check — documented in module docstring.

### Static enforcement

`scripts/check_no_direct_state_writes.py` (AST-based pre-commit hook) enforces that no code
outside `src/sdlc/state/atomic.py` writes to `state.json` directly.
Pre-commit hook chain: `boundary-validator → state-write-protocol-validator → secret-hardcode-validator`.
