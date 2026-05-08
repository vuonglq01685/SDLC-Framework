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

Note: A future ADR for wire-format v1 lock ceremony is owned by Story 1.21 and is intentionally absent
until then.

## Authoring a new ADR

Copy [`adr-template.md`](adr-template.md), bump the number, fill the six sections,
and add the file to `mkdocs.yml`'s `nav:` block. Filename convention is
`ADR-NNN-<kebab-slug>.md` (zero-padded `NNN`) per Architecture §440.
