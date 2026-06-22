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
| [025](ADR-025-pydantic-strict-mode-default.md) | Pydantic strict-mode default | Epic 2A prep (D2) | Accepted |
| [026](ADR-026-tdd-first-chunked-review-workflow.md) | TDD-first + chunked-review workflow | Epic 2A prep (A1+A2) | Accepted |
| [027](ADR-027-e2e-test-framework-strategy.md) | E2E test framework strategy (Tier-1/2/3) | Epic 2A prep (A3, Story 2A.0) | Accepted |
| [028](ADR-028-journal-kind-taxonomy.md) | Journal `kind` taxonomy + `after_hash` nullability | Epic 2B prep (DOC1) | Accepted |
| [029](ADR-029-mock-runtime-envelope-semantics.md) | MockAIRuntime envelope semantics + default-flip | Epic 2B prep (C8) | Accepted |
| [030](ADR-030-specialist-roster-freeze.md) | Specialist roster freeze + reconciliation | Epic 2B prep (C5) | Accepted |
| [031](ADR-031-atomic-write-primitive.md) | Atomic raw-text write primitive (`io_primitives`) | Epic 2B prep (C1) | Accepted |
| [032](ADR-032-append-with-seq-alloc.md) | `journal.append_with_seq_alloc` (cross-process) | Epic 2B prep (C2) | Accepted |
| [033](ADR-033-debt-decay-gate-a-zero-open.md) | Debt-decay Gate A — zero-open threshold | Epic 2B prep | Accepted |
| [034](ADR-034-debt-d7-split-signoff-flock.md) | EPIC-2A-D7 split — SIGNOFF-FLOCK / WIN32-RUNS-LOCK defer | Epic 2B prep | Accepted |
| [035](ADR-035-debt-decay-gate-c-severity-scoped.md) | Debt-decay Gate C — severity-scoped N-2 | Epic 2B prep | Accepted |
| [036](ADR-036-adopt-mutation-testing-harness.md) | Adopt-module mutation-testing harness | 3.7 | Accepted |
| [037](ADR-037-repo-containment-guard-clarification-signoff.md) | Repo-containment guard (clarification/signoff) — CR4.12-W1 | Epic 5 prep (retro D1) | Proposed |
| [038](ADR-038-sticky-halt-projection.md) | Sticky-halt projection (`halted` survives clean stop) — CR4.2-W3 | Epic 5 prep (retro D4) | Proposed |

Note: ADR-024 closes the Decision F3 wire-format-lock loop; future per-contract version bumps cite it.

Note: ADRs 025–027 were Epic-2A preparation-sprint outputs from the Epic 1 retrospective
(`_bmad-output/implementation-artifacts/epic-1-retro-2026-05-09.md`); they reached **Accepted**
when that prep sprint closed. ADRs 028–036 are Epic-2B prep + Epic-3/4 outputs.

Note: ADRs **037–038** are Epic-5 preparation outputs from the Epic 4 retrospective
(`_bmad-output/implementation-artifacts/epic-4-retro-2026-06-22.md`, actions D1/D4). They are
**Proposed**; per CONTRIBUTING §7.4 they must reach **Accepted** before Story 5.1 enters
implementation.

## Authoring a new ADR

Copy [`adr-template.md`](adr-template.md), bump the number, fill the six sections,
and add the file to `mkdocs.yml`'s `nav:` block. Filename convention is
`ADR-NNN-<kebab-slug>.md` (zero-padded `NNN`) per Architecture §440.
