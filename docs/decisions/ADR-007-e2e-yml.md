# ADR-007: E2E Workflow (`e2e.yml`) — Nightly Real-Claude Suite

**Status:** Accepted (2026-05-08, Story 1.3); workflow ships in scaffold form, becomes meaningfully green once Epic 2B-1 ships `ClaudeAIRuntime`.

## Context

PRD §531 specifies "framework's CI `e2e.yml` workflow runs the fixtures nightly against a real `claude` binary (not on every PR — cost/time tradeoff)". Architecture §1219 + AR-CI mandate the E2E workflow. For v0.2, GitHub-hosted runners do **not** have `claude` pre-installed. Triggering a red failure every night until Epic 2B would train the maintainer to ignore the nightly signal — the antithesis of the "honest signal" architecture (PRD §215, §580).

**Timezone rationale:** The cron `0 6 * * *` UTC fires at 13:00 ICT (Vietnam, UTC+7), aligning the nightly run with the start of the maintainer's working day so failures are visible before the day's main commits land.

## Decision

- **Trigger:** Nightly cron `0 6 * * *` UTC + `workflow_dispatch` (manual ad-hoc trigger).
- **Runner:** `ubuntu-latest` only. Single Python version: 3.12. (E2E test correctness is not Python-version-sensitive; the per-cell cost/time tradeoff per PRD §531 applies.)
- **Graceful skip when `claude` absent or `tests/e2e/` not yet present:** A `detect` step probes both `command -v claude` and `[ -d tests/e2e ]`, exposing two outputs (`claude`, `fixtures`). Run-suite and scaffold-check steps gate on the right combination of both. When either is missing, the step emits a `::notice::` and is `if`-skipped — never a red failure. This prevents chronic red nights during the v0.2 → Epic 2B / Story 1.20 transition windows where one precondition can land before the other.
- **Test selection:** `pytest tests/e2e -m e2e -v --no-cov --log-file=pytest-e2e.log` (when both probes pass). The `--no-cov` override neutralizes the project-wide `--cov-fail-under=90` from `pyproject.toml` `addopts` — that gate is for unit/integration tests; e2e tests subprocess-launch the CLI without importing `src/sdlc`, so coverage would always be ~0%. The `e2e` marker was pre-declared in Story 1.2's `[tool.pytest.ini_options] markers`.
- **Scaffold-check exit-code discipline:** When `claude` is absent but `tests/e2e/` exists, the workflow runs `pytest --collect-only` and accepts only exit codes `0` (tests collected) or `5` (no tests collected, expected pre-Story-1.20). Any other exit code (broken conftest, plugin error, import bug) surfaces as a real `::error::` rather than being swallowed by an unconditional `|| echo`.
- **Concurrency:** `concurrency: { group: e2e, cancel-in-progress: false }` — single-flight, so a manual `workflow_dispatch` and the cron cannot race on the v4 upload-artifact unique-name constraint.
- **Artifacts:** `actions/upload-artifact@v4` with `retention-days: 14`, path covers `tests/e2e/_artifacts/` and `pytest-e2e.log`, `if-no-files-found: ignore`. The pytest invocations explicitly write `pytest-e2e.log` via `--log-file=` so the artifact path is honest.

## Alternatives Considered

- **PR-time E2E gate**: Rejected — cost; real-Claude billing is per-token per-call. Every PR would incur Claude API charges, violating the cost discipline of the v0.2 substrate.
- **GitHub-hosted runner with `claude` CLI installed per run**: Rejected — complex; the `claude` binary requires Claude Code authentication setup that is incompatible with ephemeral runners without secrets-based credential injection (which conflicts with NFR-SEC-1).
- **Self-hosted runner with `claude` pre-installed**: Rejected for v0.2 — premature ops complexity. Revisit when Epic 2B-1 ships and the team has a stable runner provisioning strategy.
- **Red failure instead of graceful skip**: Rejected — chronic red noise trains the maintainer to ignore the signal. The `::notice::` path is the "honest signal" pattern applied to CI health.

## Consequences

- For the duration of v0.2 → Epic 2B, the nightly run reports "claude absent; skipped" and remains green.
- The first real E2E pass requires: Epic 2B-1 (`ClaudeAIRuntime`) shipped + maintainer-side runner provisioning (or a self-hosted runner with `claude` installed).
- The canonical e2e fixture set (`tests/e2e/fixtures/{greenfield,brownfield,mad-mode}/`) ships in later stories on Epic 1 / Epic 3 / Epic 4 — see the backlog for current numbering. Story 1.3 establishes the workflow scaffolding only; the directory probe in the `detect` step keeps the workflow honest until those stories land.

## Revisit-by

2027-05-01 — or when Epic 2B-1 (`ClaudeAIRuntime`) lands and the cron frequency, runner
choice, and skip strategy are re-evaluated, whichever first.
