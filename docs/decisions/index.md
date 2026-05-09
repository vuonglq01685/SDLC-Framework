# ADR Log

Every load-bearing architectural decision is recorded as a numbered ADR per
[NFR-MAINT-5][nfr-link] (every decision recorded with status, context, decision,
alternatives, consequences, and a revisit-by date).

[nfr-link]: ../index.md  <!-- placeholder; the real NFR-MAINT-5 anchor lives in the planning artifact (`_bmad-output/planning-artifacts/prd.md`), intentionally outside docs_dir — see ADR-011 Consequences -->

## Index

| # | Title | Story | Status |
|---|---|---|---|
| [001](ADR-001-pyproject-metadata.md) | pyproject metadata | 1.1 (back-filled in 1.5) | Accepted |
| [002](ADR-002-ruff-config.md) | ruff config | 1.2 | Accepted |
| [003](ADR-003-mypy-strict.md) | mypy strict | 1.2 | Accepted |
| [004](ADR-004-pytest-config.md) | pytest config | 1.2 | Accepted |
| [005](ADR-005-package-data-layout.md) | package_data layout | 1.1 (deferred to 1.16+) | Accepted partial |
| [006](ADR-006-ci-yml.md) | ci.yml | 1.3 | Accepted |
| [007](ADR-007-e2e-yml.md) | e2e.yml | 1.3 | Accepted |
| [008](ADR-008-release-yml.md) | release.yml | 1.3 | Accepted |
| [009](ADR-009-docs-yml.md) | docs.yml | 1.3 | Accepted |
| [010](ADR-010-pre-commit-config.md) | pre-commit config | 1.4 | Accepted |
| [011](ADR-011-mkdocs-setup.md) | mkdocs setup | 1.5 | Accepted |
| [012](ADR-012-module-layout.md) | 16-module layout | 1.4 (back-filled in 1.5) | Accepted |
| [013](ADR-013-atomic-state-write-protocol.md) | atomic state write protocol | 1.10 | Accepted |
| [014](ADR-014-append-only-journal-protocol.md) | append-only journal protocol | 1.11 | Accepted |
| [015](ADR-015-state-projection-from-journal.md) | state projection from journal | 1.12 | Accepted |
| [016](ADR-016-airuntime-abc-and-mock-implementation.md) | AIRuntime ABC + Mock implementation | 1.13 | Accepted |
| [017](ADR-017-abstraction-adequacy-ci-contract.md) | Abstraction-adequacy CI contract | 1.14 | Accepted |
| [018](ADR-018-engine-scanner-skeleton.md) | Engine scanner skeleton — pure read, idempotent, perf-gated | 1.15 | Accepted |
| [019](ADR-019-cli-skeleton-typer-adoption.md) | CLI skeleton + Typer + boundary widening + idempotency | 1.16 | Accepted |
| [020](ADR-020-cli-scan-status-accessibility-flags.md) | CLI `sdlc scan` + `sdlc status` + accessibility flags | 1.17 | Accepted |
| [021](ADR-021-cli-trace-replay-logs.md) | CLI trace + replay + logs + cross-stream merge | 1.18 | Accepted |
| [022](ADR-022-migration-framework-and-schema-gate.md) | Migration framework + major-version schema gate | 1.19 | Accepted |
| [023](ADR-023-rebuild-state-and-recovery-prompt.md) | Rebuild-state command + malformed-state recovery prompt | 1.20 | Accepted |
| [024](ADR-024-wire-format-v1-lock.md) | wire-format v1 lock ceremony | 1.21 | Accepted |
| [025](ADR-025-pydantic-strict-mode-default.md) | Pydantic strict-mode default | Epic 2A prep (D2) | Proposed |
| [026](ADR-026-tdd-first-chunked-review-workflow.md) | TDD-first + chunked-review workflow | Epic 2A prep (A1+A2) | Proposed |
| [027](ADR-027-e2e-test-framework-strategy.md) | E2E test framework strategy (Tier-1/2/3) | Epic 2A prep (A3, Story 2A.0) | Proposed |

Note: ADR-024 closes the Decision F3 wire-format-lock loop; future per-contract version bumps cite it.

Note: ADRs 025–027 are Epic-2A preparation-sprint outputs from the Epic 1 retrospective
(`_bmad-output/implementation-artifacts/epic-1-retro-2026-05-09.md`). They move from
**Proposed** → **Accepted** when the prep sprint closes and Story 2A.1 enters implementation.

## Authoring a new ADR

Copy [`adr-template.md`](adr-template.md), bump the number, fill the six sections,
and add the file to `mkdocs.yml`'s `nav:` block. Filename convention is
`ADR-NNN-<kebab-slug>.md` (zero-padded `NNN`) per Architecture §440.
