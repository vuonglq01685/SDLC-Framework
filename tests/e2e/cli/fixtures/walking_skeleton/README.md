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
