# SDLC-Framework

Deterministic, auditable, multi-agent SDLC orchestration framework on top of Claude Code.

This documentation site is the human-readable surface for the framework's load-bearing
architectural decisions and the 16-module dependency DAG that the substrate enforces.

## Where to start

- [Architecture Overview](architecture-overview.md) — the 16-module DAG plus the
  eight specific boundary rules.
- [ADR Log](decisions/index.md) — every load-bearing decision recorded under
  NFR-MAINT-5, with status, alternatives, consequences, and a revisit-by date.

## What lives outside this site

Planning artifacts (`_bmad-output/planning-artifacts/{prd,architecture,epics,ux-design-specification}.md`)
and implementation artifacts (`_bmad-output/implementation-artifacts/*.md`) are intentionally
excluded from the published site — they are working artifacts of the BMAD planning loop, not
canonical reference material. The Architecture Overview here summarises and links into them
where useful; [ADR-011 Consequences](decisions/ADR-011-mkdocs-setup.md) records the scoping choice.
