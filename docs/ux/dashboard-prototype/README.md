# Dashboard Prototype — Reference Artifact

This folder holds the canonical visual prototype that the UX design specification codifies.

## Files

| File | Purpose |
|---|---|
| `dashboard.html` | The "editorial ops console" prototype — single-page HTML embodying the dark editorial register, the masthead/KPI/phase tracker/tree/resume card layouts, and the design token system. Treated as the canonical visual contract. |
| `state.json` | Sample state payload used by the prototype to render realistic content. Useful for understanding the data shape that real components must consume. |

## Provenance

Originally authored at `../../../../SDLC/dashboard/` (outside this repository).
Copied into the project on 2026-05-07 so the UX specification can reference an in-tree artifact instead of a path outside the project root.

## Status

Reference-only. The production dashboard implementation (under `dashboard/` in the eventual `src/sdlc/` package) will be derived from this prototype and from the formal specification at:

- `_bmad-output/planning-artifacts/ux-design-specification.md`

Modifications to the prototype after the UX spec is signed off should be made in the production dashboard, not here. This folder is frozen as the historical reference unless the spec is explicitly re-opened.

## Tightening required before production

Per the UX specification, three modifications must be applied when porting the prototype to production:

- **DD-09** — strip the prototype's light-mode `:root` block; promote `[data-theme="dark"]` to canonical `:root`. Remove every `data-theme` read or write.
- **DD-10** — remove the prototype's Google Fonts `<link>` tags. Self-host Fraunces / Inter / JetBrains Mono under `dashboard/static/fonts/`.
- **DD-14** — strip every CSS transition and animation except the live-dot pulse and STOP-dot pulse. Replace chevron transforms with icon-glyph swaps from the SVG sprite.

See the UX specification for the full list of decisions (DD-01 through DD-16+).
