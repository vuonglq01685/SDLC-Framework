# `/sdlc-architect` — Phase 2 System Architecture Track (FR14)

Generates the primary system architecture document and dispatches sub-track
specialists declared in the document's `requires:` frontmatter block.

## Usage

```
sdlc architect
```

## Prerequisites

- Phase 1 signoff must be in state `APPROVED` (run `/sdlc-signoff 1` first)
- `01-Requirement/01-PRODUCT.md` must exist

## Outputs

- `02-Architecture/02-System/ARCHITECTURE.md` — primary system architecture
- `02-Architecture/02-System/sub-tracks/{name}.md` — per sub-track (if `requires:` present)

## Sub-tracks

The system architect may declare sub-tracks in the YAML frontmatter of `ARCHITECTURE.md`:

```yaml
---
requires:
  - database
  - security
  - observability
---
```

Sub-tracks are dispatched **sequentially** after the primary document is written (v1).

## Supported Sub-tracks

| Sub-track     | Specialist              | Output Path                                    |
|---------------|-------------------------|------------------------------------------------|
| database      | database-architect      | `sub-tracks/database.md`                       |
| security      | security-architect      | `sub-tracks/security.md`                       |
| observability | observability-architect | `sub-tracks/observability.md`                  |

## Error Codes

- `ERR_PHASE1_NOT_APPROVED` — Phase 1 signoff is not approved
- `ERR_SIGNOFF_READ_FAILED` — Phase 1 signoff could not be read (corrupt/missing)
- `ERR_ARTIFACT_CONTAINS_BOUNDARY` — `01-PRODUCT.md` contains the boundary marker

## Story Reference

Story 2A.14 — `_bmad-output/implementation-artifacts/2a-14-sdlc-architect-dynamic-sub-tracks.md`
