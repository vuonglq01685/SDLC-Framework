# ADR-`{{NNN}}`: `{{Title in Title Case}}`

**Status:** Proposed | Accepted (`{{YYYY-MM-DD}}`, Story `{{X.Y}}`) | Superseded by ADR-`{{MMM}}` | Deprecated

## Context

`{{What forces are in play, why a decision is needed. Cite PRD §N, Architecture §N,
NFR-IDs as required. Be specific about the constraint that motivates this decision.}}`

## Decision

`{{The actual decision, in declarative present tense. Be load-bearing — only
decisions that the substrate's behaviour depends on belong in an ADR.}}`

## Alternatives Considered

- **`{{Option A}}`**: `{{Rejected because …}}`
- **`{{Option B}}`**: `{{Rejected because …}}`
- **`{{Option C}}`**: `{{Considered viable but rejected because …}}`

## Consequences

- `{{Positive consequence 1.}}`
- `{{Positive consequence 2.}}`
- `{{Negative consequence or trade-off — what this decision costs.}}`

## Revisit-by

`{{YYYY-MM-DD}}` — or when `{{specific event triggers re-evaluation}}`.

<!-- Template authoring rules:
     - Filename: ADR-NNN-<kebab-slug>.md per Architecture §440. Zero-padded NNN.
     - Status line is single-line. Pick exactly one of: Proposed | Accepted (DATE,
       Story X.Y) | Superseded by ADR-MMM | Deprecated. Strip the alternatives that
       do not apply when authoring a real ADR.
     - Placeholders are wrapped in backticks (`{{token}}`) so they render as inline
       code on the published site and so a future install of mkdocs-macros-plugin
       sees them as literal text rather than Jinja2 expressions. Strip the backticks
       when copy-pasting into a real ADR.
     - Revisit-by accepts a hard date OR a hybrid "DATE OR event-condition" form.
       Pure-event revisit-bys (e.g. "When Epic 2B ships") are FORBIDDEN by
       NFR-MAINT-5 + Story 1.5 AC5 — every ADR must have at least one ISO date
       in its Revisit-by section.
     - The 12-month rule binds at AUTHORING time: the date floor must be no further
       than 12 months from the ADR's authoring date. Subsequent stories should not
       retroactively edit revisit-by dates that WERE VALID at authoring; revisit-by
       dates that were INVALID at authoring (pure-event triggers, no ISO date) are
       repaired in place under the AC5 rule, and the repair is recorded in the
       relevant story's Change Log.
     - This template file is excluded from the 12-month rule (it is a template, not
       an authored decision).
-->
