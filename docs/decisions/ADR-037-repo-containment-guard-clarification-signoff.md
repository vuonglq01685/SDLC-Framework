# ADR-037: Repo-Containment Guard on Clarification/Signoff Writes & Unlinks (CR4.12-W1)

**Status:** Accepted

> Implemented (Epic-4 retro D1): `sdlc.concurrency.path_guard.assert_repo_contained` guards the
> auto_mad forward (resolution write + open unlink) and the `sdlc unsign` reverse
> (signoff/clarification removals) callsites; `find_mad_resolution_dirs` refuses symlinked dirs.
> Forward + reverse symlink-escape regression tests green on the CI POSIX legs.

## Context

The auto-orchestrator's clarification/signoff mutation surface writes and unlinks
files at paths derived from untrusted-ish inputs (a `StopDecision.target` string,
phase identifiers) and applies `Path.resolve()` before the operation:

- `src/sdlc/engine/auto_mad.py:247` — `atomic_write(resolution_path.resolve(), …)`
  where `resolution_path = (open_path.parent) / RESOLUTION_NAME` and `open_path`
  is built from `stop.target`.
- `src/sdlc/engine/auto_mad.py:257` — `open_path.unlink()` with no containment check.
- `src/sdlc/cli/unsign.py:122–143` — the reverse path: `atomic_write(open_path.resolve(), …)`
  plus `record_path.unlink()` / `draft_path.unlink()` on paths derived from `_signoff_path(...)`.
- `src/sdlc/cli/unsign.py` `find_mad_resolution_dirs` enumerates clarification dirs with
  `child.is_dir()`, which **follows symlinks**.

The write primitive `atomic_write` (`src/sdlc/concurrency/io_primitives.py:139`) guards
only `path.is_absolute()` — always true after `.resolve()` — and performs no repo-root
containment check. `Path.resolve()` follows symlinked ancestors, and `Path.unlink()`
traverses symlinked parent directories. So a symlink planted under `.claude/state/`
(local-FS write access) lets a write or unlink operate **outside the repo root**. This is
the Epic-4 retro **CR4.12-W1** finding (HIGH×2) and retro action **D1**; it is a hard
"Before Story 5.1" gate item (the same containment helper is reused by Story 5.1's
static-file path-traversal control — see `epics.md` Story 5.1 AC).

The repo already has two containment patterns, neither reused here:
`adopt/invariant.py::assert_path_under_claude` (reject-outright, used only by `adopt/`)
and `cli/_verify_paths.py::_reject_symlink_ancestors` (symlink-ancestor walk, used only
by `sdlc verify`).

## Decision

Add a single **standalone containment guard** — `assert_repo_contained(path, repo_root)`
in a new module `src/sdlc/concurrency/path_guard.py` (both `engine` and `cli` already
depend on `concurrency`, so this respects the module-boundary layout without a new edge).
The guard **rejects outright** (raises a `SecurityError`/`ValueError`) when either: a path
component is a symlink, **or** the fully-resolved path is not equal to or under the
resolved `repo_root`. Call the guard **at each callsite, immediately before every write and
unlink** across the whole clarification/signoff mutation surface — both the forward path
(`auto_mad.py`) and the reverse path (`unsign.py`). `find_mad_resolution_dirs` additionally
refuses symlinked directories (`not child.is_symlink()`).

`atomic_write` / `atomic_write_bytes` keep their current signatures — the containment check
lives at the callsite, **not** inside the primitive — so the **ADR-031 atomic-write
contract is unchanged** (no new parameter, no `__all__` change to `io_primitives`).

## Alternatives Considered

- **Add a `repo_root=` parameter to `atomic_write` and enforce containment inside the primitive**: Rejected — it changes the ADR-031 public contract and forces every existing caller (state writers, journal writers) to thread `repo_root`, far beyond the two surfaces this finding covers.
- **Clamp the path into `repo_root` instead of rejecting**: Rejected — silently redirecting a symlink-escaping write hides the attack and can corrupt a legitimate target; reject-outright matches the `adopt/invariant.py` and `_verify_paths.py` precedent.
- **Reuse `signoff/records.py::_is_safe_repo_relative_posix`**: Rejected — it validates that a *string* is a safe relative POSIX path; it does not resolve symlinked ancestors or compare the resolved path against `repo_root`, and it is a private cross-module import.

## Consequences

- Closes CR4.12-W1 (HIGH×2) on **both** the forward (`auto_mad`) and reverse (`unsign`) clarification/signoff mutation paths.
- One DRY guard, also consumable by Story 5.1's static-file path-traversal control — no second hand-rolled implementation.
- ADR-031's atomic-write contract and the 7/7 wire-format freeze are untouched (no `StrictModel`, no snapshot ceremony — the affected artifacts are plain `resolution.md`/`open_clarification.md`/`SIGNOFF.md`, not registered contracts).
- Cost: every mutation callsite must call the guard; an absence is a silent re-opening of the hole — enforce with a test that asserts a symlink-escaping `stop.target` is rejected on both paths (RED-first per CONTRIBUTING §2).
- Reject-outright could refuse a legitimately symlinked `.claude/state` layout; acceptable under the trusted-local-user threat model and the `.claude/` sandbox-integrity expectation.

## Revisit-by

2027-06-22 — or when a legitimate symlinked `.claude/state` layout must be supported, at which point the reject-outright policy is revisited in favor of resolve-then-compare.
