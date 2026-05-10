# tests/e2e — Two-Tier E2E Test Harness

Implements the two-tier E2E strategy from [ADR-027](../../docs/decisions/ADR-027-e2e-test-framework-strategy.md).
Tier-3 (real-Claude pipeline) is deferred to Epic 2B Story 2B.3.

## Strategy

| Tier | Location | What it tests | How it runs |
|------|----------|---------------|-------------|
| Tier-1 | `cli/` | CLI stdout/stderr/exit/journal-hash/state-hash goldens | `subprocess` (OS-level isolation) |
| Tier-2 | `pipeline/` | Full phase replay against `MockAIRuntime` | In-process `asyncio.run` |

**Tier-1** catches output regressions, exit-code drift, and journal-shape drift across
refactors. Tests are insensitive to internal refactors because they only touch the public CLI.

**Tier-2** catches dispatcher and specialist-invocation contract regressions using
deterministic `MockAIRuntime` fixtures. No outbound network calls ever.

## Time-freeze policy (2A.0)

No `SDLC_FAKE_NOW` hook is introduced in 2A.0. Journal golden comparisons therefore
use **ts-excluded re-canonicalization** (see `cli/conftest._hash_journal_no_ts`) instead
of raw-bytes hashing. State (`active.json`) is hashed raw because it contains no timestamps.
Time-freezing is tracked as a separate debt item.

## Relationship to existing integration tests

`tests/integration/test_*_e2e.py` predates this tier structure and coexists with it.
Those tests are narrow integration slices (assertion-only, no goldens). Migration into
Tier-1 is a per-story choice; 2A.0 does NOT delete them.

## Architecture §682–§702 extension

The architecture document anticipated `tests/e2e/test_<scenario>.py` flat layout.
2A.0 refines this with tier sub-directories `cli/` and `pipeline/` to enforce the
isolation boundary between subprocess-driven and in-process tests.

## Don't lie to yourself

`tests/e2e/test_harness_anti_tautology.py` contains three mutation-receipt tests (AC6)
that prove the harness correctly FAILS when a golden is corrupted. Run them after any
change to `cli/conftest.assert_goldens` or `pipeline/conftest.assert_pipeline_goldens`.

## How to add a new Tier-1 scenario

1. Create `cli/fixtures/<scenario>/commands.yaml` (see `walking_skeleton/commands.yaml`).
2. Run `pytest tests/e2e/cli/ --update-goldens` to bootstrap goldens.
3. Inspect each golden file manually — do NOT rubber-stamp `--update-goldens` output.
4. Add `cli/test_<scenario>_goldens.py` with `@pytest.mark.e2e`.

## How to add a new Tier-2 scenario

1. Create `pipeline/fixtures/<scenario>/pipeline.yaml` + `mock_responses/`.
2. Run `pytest tests/e2e/pipeline/ --update-goldens` to bootstrap goldens.
3. Add `pipeline/test_<scenario>.py` with `@pytest.mark.e2e`.
