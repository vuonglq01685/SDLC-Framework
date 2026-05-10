# walking_skeleton — Tier-1 Seed Scenario

Exercises the shipped walking-skeleton CLI surface: `init → scan → status`.

## Inputs

`commands.yaml` declares three commands in order:
1. `init` — creates `.sdlc/` project structure
2. `scan` — scans workspace for epics/stories/tasks; writes journal entry (POSIX-only)
3. `status` — reads and reports current phase and last-updated timestamp

## Expected goldens

After `--update-goldens`, the `goldens/` directory contains five files per command
(15 files total). All are byte-stable on Linux CI; the `02_scan.*` files require
POSIX (skipped on Windows).

## Relationship to integration tests

`tests/integration/test_walking_skeleton_e2e.py` tests the same CLI surface but with
assertion-only (no goldens). This scenario reproduces the same behavior at byte-level
granularity, proving the Tier-1 harness works against the shipped CLI.

## Story 2A.5 (hook trust) impact

Goldens were regenerated on 2026-05-10 to absorb the new behavior introduced by
Story 2A.5:

- `sdlc init` now writes a `hooks_trusted` journal entry at seq=0 and creates
  `.claude/state/hook-hashes.json`. The `init` goldens (`01_init.*`) reflect
  the post-baseline state.
- `sdlc scan --json` now exposes a `trust_state: {status, drift_count}` field
  in the JSON envelope (advisory-only per FR39 / NFR-SEC-5 / ADR-013). For the
  walking-skeleton happy path the value is `{"status": "clean", "drift_count": 0}`.
- The journal-hash canonicalization in `tests/e2e/cli/conftest.py` strips
  `before_hash` and `after_hash` from `hooks_trusted` entries because those
  reference `hook-hashes.json`'s wall-clock `trusted_at` field. This keeps the
  golden byte-stable across runs without coupling the e2e harness to the wall
  clock. Other entry kinds keep full-chain canonicalization.
