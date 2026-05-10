# Runbook: Handle Hook Hash Drift

**Applies to:** `sdlc scan` warning `[WARN] hook tampering detected`

## Background

`sdlc scan` compares the sha256 hashes of every `.py` file under `.claude/hooks/`
against the stored baseline in `.claude/state/hook-hashes.json`. If any file was
added, removed, or modified since the last `sdlc trust-hooks` call, scan emits a
warning to stderr and sets `trust_state.status = "tampered"` in the JSON envelope.

In v1, this is **advisory-only**: scan still exits 0 and the project is still
scanned normally. Hard-blocking is scoped to v1.x (see deferred-work.md).

## Status Values

| `trust_state.status` | Meaning | Action |
|---|---|---|
| `clean` | Hashes match baseline | None |
| `tampered` | One or more files changed since last trust | See below |
| `uninitialized` | No baseline recorded yet | Run `sdlc trust-hooks` |
| `corrupted` | `hook-hashes.json` is malformed | Run `sdlc trust-hooks` to re-initialize |

## Procedure: Tampered Hooks

### Step 1 — Identify what changed

```bash
sdlc scan --json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(x) for x in d.get('trust_state',{}).get('drift',[])]"
```

Or read stderr from `sdlc scan` directly — each drifted file is listed with its
kind (`added`, `removed`, or `modified`).

### Step 2 — Investigate the change

- **modified**: Review the diff against the previous hook content. The warning
  shows the first 15 hex chars of the expected and actual sha256 digests for a
  quick sanity check.
- **added**: A new hook was installed without recording trust. Confirm the file
  is intentional.
- **removed**: A previously-trusted hook is gone. Confirm it was intentionally
  removed.

### Step 3 — Accept or restore

**If the change is intentional** (you updated a hook, added a new one, etc.):

```bash
sdlc trust-hooks
```

This recomputes all hook hashes and writes a new baseline. The next `sdlc scan`
will show `trust_state.status = "clean"`.

**If the change is NOT intentional** (unexpected modification):

1. Restore the hook file from version control:
   ```bash
   git checkout HEAD -- .claude/hooks/<filename>.py
   ```
2. Confirm `sdlc scan` now shows `trust_state.status = "clean"`.
3. Investigate how the unexpected modification occurred.

## Procedure: Uninitialized or Corrupted Baseline

```bash
sdlc trust-hooks
```

This creates or re-creates `hook-hashes.json` from the current hook files.

## Notes

- `sdlc trust-hooks` appends a `hooks_trusted` journal entry at the current
  `next_monotonic_seq` and advances the state seq by 1.
- The baseline file lives at `.claude/state/hook-hashes.json` and is written
  atomically (POSIX) to prevent partial-write corruption.
- On Windows, a non-atomic write fallback is used (best-effort).
- See FR39 and NFR-SEC-5 in the PRD for the security rationale.
