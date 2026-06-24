# Story 5.3: Self-Host Fonts (`@font-face`) + 12-Icon SVG Sprite

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L2 (5A). Depends ONLY on 5.2 (frozen tokens), mutually independent of its L2 sibling 5.4. Worktree: epic-5/5-3-self-host-fonts-and-12-icon-svg-sprite. Branch from main, linear merge, rebase between L2 merges (CONTRIBUTING §3). FREEZE the icon-reference URL convention this story — 5.8/5.9/5.10/5.11 consume the sprite. -->

## Story

As a frontend engineer honoring DD-10 (no Google Fonts CDN) and DD-03 (12-icon SVG sprite),
I want all fonts served from `dashboard/static/fonts/` via `@font-face` with `font-display: swap`, and a single 12-icon SVG sprite referenced via `<use>`,
So that the local-first promise is preserved and icon rendering is bandwidth-minimal (UX-DR18, UX-DR19, DD-10, DD-03).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.3, lines 2434–2451).

**AC1 — Fonts directory + `@font-face` + no-CDN grep gate**
- **Given** `dashboard/static/fonts/` **When** I list files **Then** the directory contains only the weights actually referenced: Fraunces 400/500/600, Inter 300/400/500/600/700, JetBrains Mono 400/500/600
- **And** `tokens.css` declares `@font-face` for each weight with `font-display: swap`
- **And** no `<link>` tag in any HTML file references `fonts.googleapis.com` or any external font CDN (CI grep gate)

**AC2 — SVG sprite (exactly 12 icons)**
- **Given** `dashboard/static/icons/sprite.svg` **When** I open the file **Then** it contains exactly 12 icons (per DD-03): `circle`, `circle-filled`, `check`, `slash-circle`, `arrow-right`, `chevron-right`, `chevron-down`, `copy`, `external-link`, `info`, `warning`, `error`
- **And** every component referencing an icon uses `<svg><use href="/static/icons/sprite.svg#<icon-name>"/></svg>` (no inline SVG duplicated, no PNG icons)
- **And** the sprite is served with long cache headers (immutable + max-age)

**AC3 — Sprite expansion contract / ADR trigger**
- **Given** the sprite contract **When** a component requires a 13th icon **Then** the team adds it to the single sprite (no per-component icon files)
- **And** ADR documenting any sprite expansion is required if the count grows beyond 12

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** the three testable contracts are tests-first (RED→GREEN): (a) the no-Google-Fonts gate script (RED: a fixture HTML with a `fonts.googleapis.com` `<link>` fails; GREEN: clean files pass); (b) the **woff2/woff `Content-Type`** server fix (RED: a `.woff2` served by the running server has no/`application/octet-stream` type; GREEN: `font/woff2`); (c) the wheel-content assertion (fonts + sprite ship). The `@font-face`/sprite SVG are design substrate → `test-along` is fine, but the gate + the MIME server change MUST be tests-first.

- [x] **Task 0 — Resolve Decision D1 (static-asset URL convention) BEFORE coding** (AC: 2)
  - [x] The epic AC2 `<use href>` is `/static/icons/sprite.svg#…`, but the shipped server (Story 5.1) serves static files at **root-relative** URLs — `resolve_static_file` does `rel = request_path.lstrip("/")` then `static_dir / rel` [src/sdlc/dashboard/server.py:93-96], so `/static/icons/sprite.svg` maps to `static/static/icons/sprite.svg` → 404. Pick ONE convention and FREEZE it (5.8/5.9/5.10/5.11 reference the sprite). See Dev Notes → Decisions D1. Record the pick in the PR Change Log (CONTRIBUTING §5).

- [x] **Task 1 — Self-host the font files** (AC: 1)
  - [x] Add `src/sdlc/dashboard/static/fonts/` containing **only** the referenced weights as `.woff2`: Fraunces 400/500/600, Inter 300/400/500/600/700, JetBrains Mono 400/500/600 (11 files). Source from the upstream OFL/SIL font projects (Fraunces — variable axis pinned to the three weights or 3 static cuts; Inter; JetBrains Mono). Do NOT ship other weights/formats (no `.ttf`/`.otf`/`.woff` unless a fallback is justified — DD-10 keeps wheel `package_data` lean).
  - [x] Record each font's license (OFL) — keep the `OFL.txt`/license alongside the fonts or noted in the PR; these are vendored third-party assets.

- [x] **Task 2 — `@font-face` declarations + remove any CDN link + wire the stylesheet** (AC: 1) — *MIME-dependent on Task 3*
  - [x] Declare `@font-face` for each of the 11 weights with `font-display: swap`, `src: url("…/fonts/<File>.woff2") format("woff2")`, and `font-family` names matching the FROZEN tokens **exactly** (`Fraunces`, `Inter`, `JetBrains Mono`) — the stylelint `font-family` allowlist already pins these [src/sdlc/dashboard/static/styles/.stylelintrc.json:26-32]; a mismatch fails the 5.2 stylelint gate.
  - [x] Per the epic AC1, the `@font-face` rules live in `tokens.css` (the AC says "`tokens.css` declares `@font-face`"). The frozen `tokens.css` header already reserves this: *"`@font-face` rules and self-hosted font files land in Story 5.3."* Append the `@font-face` block to `tokens.css`; do NOT touch the frozen token values (DD-09/freeze).
  - [x] Add `font-feature-settings: 'ss01', 'cv11'` on `html, body` per UX §3.2 (Inter stylistic-set/character-variant for the editorial register).
  - [x] `index.html` currently links nothing [src/sdlc/dashboard/static/index.html] — add `<link rel="stylesheet" href="…/styles/tokens.css">` (URL per Decision D1). Do NOT add any `<link rel="preload">` for fonts (UX spec relies on `font-display: swap` only). **NEVER add a `<link>` to `fonts.googleapis.com`/`fonts.gstatic.com` or any font CDN** (AC1 / DD-10) — the prototype's three CDN tags [docs/ux/dashboard-prototype/dashboard.html:7-9] are exactly what this story removes.

- [x] **Task 3 — Fix static `Content-Type` for `.woff2`/`.woff` (server change)** (AC: 1) — *tests-first, CRITICAL*
  - [x] **Bug:** `serve_static` resolves MIME via `mimetypes.guess_type` [src/sdlc/dashboard/server.py:107], and `.woff2`/`.woff` are absent from stdlib `mimetypes` on Python **3.10–3.13** (the full CI matrix) → `guess_type` returns `None` → no `Content-Type` header → browsers refuse the `@font-face` source. (`.svg`/`.css`/`.js` ARE present, so only fonts break.)
  - [x] Register the font types once at server init: `mimetypes.add_type("font/woff2", ".woff2")` + `mimetypes.add_type("font/woff", ".woff")` (or replace `guess_type` with a small explicit extension→type map). Keep the existing `_IMMUTABLE_CACHE` behavior for non-`index.html` (fonts get the immutable 1-yr cache — satisfies AC2 "immutable + max-age" for assets) [server.py:111-112].
  - [x] **RED→GREEN test against the RUNNING server** (use the `running_dashboard` fixture + `http_get`, mirror [tests/unit/dashboard/test_dashboard_routes.py:18-21]): assert a served `.woff2` returns `Content-Type: font/woff2`. **Do NOT assert via `mimetypes.guess_type` locally** — a dev host on Python 3.14 would falsely pass (3.14 added the type). This server edit touches the 5.1 "freeze server/route contract before 5.13" surface but is purely additive (a new MIME entry) — note it in the PR; re-run the 5.1 static-serving tests.

- [x] **Task 4 — Author the 12-icon sprite + reference convention** (AC: 2, 3)
  - [x] Create `src/sdlc/dashboard/static/icons/sprite.svg` as a single SVG containing **exactly 12** `<symbol id="…">` — the AC2 list verbatim: `circle`, `circle-filled`, `check`, `slash-circle`, `arrow-right`, `chevron-right`, `chevron-down`, `copy`, `external-link`, `info`, `warning`, `error`. Stroke-only, 1.5px, square caps per DD-03 (`circle-filled` is the one filled glyph). Use a consistent `viewBox` (e.g. `0 0 24 24`).
  - [x] Reference convention (per Decision D1): `<svg><use href="<URL>/icons/sprite.svg#<icon-name>"/></svg>`. No inline-duplicated SVG, no PNG icons (AC2). Decorative icons carry `aria-hidden="true"`; informative icons carry `<title>`/`aria-label` (UX §8.6).
  - [x] Do NOT build components that consume the icons here — masthead/KPI/resume/tree/tabs land in L3/L4. This story ships the sprite + freezes the `<use>` convention only (anti-scope-creep).
  - [x] Verify the sprite is served `immutable + max-age` — the existing `_IMMUTABLE_CACHE` already applies to every static file except `index.html` [server.py:111-112]; add a served-headers test asserting `Cache-Control` on the sprite.

- [x] **Task 5 — no-Google-Fonts / no-CDN CI grep gate** (AC: 1) — *tests-first*
  - [x] Add `scripts/check_dashboard_no_external_fonts.py` **mirroring the DD-09 gate shape** [scripts/check_dashboard_no_data_theme.py]: same `_REPO_ROOT`/`_DEFAULT_ROOT` anchor, `rglob` globs over `*.html`/`*.css`, comment-stripping, `(pattern, label)` tuples, `errors="replace"` reads, and the **exit 0/1/2 + `file:line:col` to stderr** contract. Patterns: `fonts.googleapis.com`, `fonts.gstatic.com`, `@import url(…http`, `<link[^>]+href=["']https?://…` (external font/style CDNs). Tag violations `(DD-10)`.
  - [x] **RED:** a fixture HTML with `<link href="https://fonts.googleapis.com/…">` exits 1 with `file:line:col`; **GREEN:** the cleaned `index.html` + self-hosted `tokens.css` pass. Put the gate-script test in `tests/unit/scripts/test_check_dashboard_no_external_fonts.py` (`import check_dashboard_no_external_fonts` via the `tests/conftest.py:19-22` scripts-on-`sys.path` wiring); fixtures in `tests/fixtures/dashboard_css/`.
  - [x] Wire the gate as a sibling step in the `quality-gates` matrix (right after the DD-09 step) [.github/workflows/ci.yml — `run: uv run python scripts/check_dashboard_no_external_fonts.py`] and a `repo: local` pre-commit hook mirroring the DD-09 hook [.pre-commit-config.yaml]. This is a `quality-gates` **step**, not a new top-level job — no `ci-gate.needs` edit required.

- [x] **Task 6 — Wheel packaging (force-include each asset)** (AC: 1, 2)
  - [x] The static tree ships **only via explicit, file-by-file `force-include`** (it is excluded from `packages`) [pyproject.toml]. Add an entry for **every** `static/fonts/*.woff2` (11) and `static/icons/sprite.svg` — a glob will NOT ship them. Mirror the existing `tokens.css` entry form.
  - [x] Add/extend a wheel-content test asserting the fonts + sprite are present in the built wheel (an unlisted asset silently 404s at runtime).

- [x] **Task 7 — ADR-trigger note (sprite >12)** (AC: 3)
  - [x] Add a short note in the sprite file header (or `docs/`) stating the 12-icon contract + "adding a 13th icon requires an ADR" (DD-03 "minimum set"). No ADR is needed now (the set is exactly 12).

- [x] **Task 8 — Quality gate + docs + freeze** (AC: 1, 2, 3)
  - [x] Python quality gate on any new `scripts/*.py` (ruff format/check + mypy --strict); full pytest + coverage ≥87%; `mkdocs build --strict` green; **zero wire-format change → freeze stays 7/7** (fonts/SVG/CSS are not wire contracts).

### Review Findings

_Code review 2026-06-24 (bmad-code-review: Blind Hunter + Edge Case Hunter + Acceptance Auditor, all at Opus capability). **0 decision-needed · 3 patch · 6 deferred · 5 dismissed.** The Acceptance Auditor verified AC1/AC2/AC3 + Decision D1 + the woff2 MIME fix (tested against a running server) + wheel-content + the TDD-first contracts all PASS._

**Patch (action required):**

- [x] [Review][Patch] HIGH — Untracked font/icon assets (11 `.woff2` + `sprite.svg` + `OFL.txt`) are not yet git-tracked; binaries are invisible in `git diff` and the wheel test only passes off the working tree, so a clean CI checkout would fail the `pyproject.toml` force-include. Stage them in the feat() commit. [src/sdlc/dashboard/static/fonts/, src/sdlc/dashboard/static/icons/]
- [x] [Review][Patch] MEDIUM — `test_sprite_header_documents_adr_trigger` is unfalsifiable: `assert "13" in text` matches the path coordinate `M13 6` in the arrow-right glyph, so the ADR-trigger guard stays green even if the header note is deleted. Require `"13th"` scoped to the leading comment block. [tests/unit/dashboard/test_dashboard_sprite.py:624]
- [x] [Review][Patch] LOW — Stray control byte `\x14` in the sprite header comment where an em-dash (`—`) was intended ("Exactly 12 icons `\x14` adding a 13th…"). Replace with `—`. [src/sdlc/dashboard/static/icons/sprite.svg:4]

**Deferred (real, not blocking — latent / no current exposure):**

- [x] [Review][Defer] MEDIUM — No-CDN font gate coverage gaps: the per-line scan defeats the dedicated multi-line `<link>` regex (the committed fixture only fails via the bare `fonts.googleapis.com` substring), and `_SCAN_GLOBS`/the pre-commit `files:` regex omit `*.js`/`*.mjs`/`*.svg` plus non-Google `src: url(https://…)` CDNs — contradicting the docstring's "mirrors DD-09" claim. The Google-Fonts threat IS caught; harden tests-first when the gate next changes. [scripts/check_dashboard_no_external_fonts.py, .pre-commit-config.yaml, .github/workflows/ci.yml] — deferred: latent, zero current exposure
- [x] [Review][Defer] MEDIUM — Gate strips CSS comments but not HTML comments → a commented-out (inert) CDN `<link>` in any `.html` would hard-fail CI; asymmetric with the CSS path. [scripts/check_dashboard_no_external_fonts.py] — deferred: latent, no such comment exists today
- [x] [Review][Defer] LOW — `_register_font_mime_types()` mutates the process-global `mimetypes` registry at import time (hidden side effect per coding rules); idiomatic, tested, and benign (override wins). [src/sdlc/dashboard/server.py:30-36] — deferred: idiomatic, functionally correct
- [x] [Review][Defer] LOW — `/static/` prefix strip is unanchored/single-level → every asset has two valid URLs (`/static/x` and `/x`, intentional per D1 + tested) and a theoretical `static/` subdir shadow; safe today (`assert_contained` guards). Document the dual-URL convention. [src/sdlc/dashboard/server.py:103-111] — deferred: by design (D1), safe
- [x] [Review][Defer] LOW — `main()` returns 1 on violations even when an unknown path argument was also passed, masking the documented exit-2 "path not found" operator-error signal. [scripts/check_dashboard_no_external_fonts.py:343-352] — deferred: minor contract precedence
- [x] [Review][Defer] LOW — Wheel-build test skip guard checks `shutil.which("python")`, but `_build_wheel` falls back to `sys.executable -m build`; the predicate doesn't match the gated code path. [tests/integration/test_wheel_dashboard_static.py:468-471] — deferred: test-infra robustness, no current failure

**Dismissed (false positives / noise — not action items):** Blind Hunter's two HIGH claims both verified FALSE — (1) "prefix-strip after containment guard = traversal bypass": `assert_contained(candidate, static_dir)` runs LAST on the final candidate (`server.py:111`), no validate-then-mutate gap; (2) "cache-poisoning via dual URL": intentional per D1 + tested. Also dismissed: `mimetypes` NameError (imported at `server.py:5`), `clean_component.css` "missing" (fixture exists, 180 B), redundant `len(woff2)==11` assert (harmless), and `.woff` MIME registered though unused (defensive YAGNI).

## Dev Notes

### Locked design decisions (verbatim — these govern the whole story)

- **DD-10 — Self-host fonts.** *"Remove prototype's Google Fonts `<link>` tags; serve all fonts from `dashboard/static/fonts/` via `@font-face`. Ship only the weights actually referenced (Fraunces 400/500/600, Inter 300/400/500/600/700, JetBrains Mono 400/500/600). PRD §385 forbids Google Fonts CDN. Limiting weights keeps wheel `package_data` size reasonable."* [Source: UX §Design System / DD-10, ux-design-specification.md:381]
- **DD-03 — 12-icon SVG sprite.** *"Inline SVG icon system, 12-icon minimum set. Stroke-only, 1.5px, square caps. Vendored as a single `sprite.svg` referenced via `<use>`. Local-first constraint forbids icon-font CDNs; text-first bias preserves editorial register."* [Source: UX §Executive Summary / DD-03, ux-design-specification.md:90]
- **Local-first asset constraint.** *"No Google Fonts CDN, no icon font CDN, no build step, vanilla JS only, Chart.js vendored. Every design choice must survive these constraints."* [Source: UX §Executive Summary:70; architecture.md:157 "No npm, no webpack, no React, no build step"; architecture.md:160 "Outbound HTTP: none from the framework process itself"]

### The 12 icons are CANONICAL in the epic AC (no enumeration ambiguity)

The UX spec only names ~7 sprite ids by usage, but **the epic AC2 itself names all 12 verbatim** — that list is binding. Final manifest (exactly 12, no more): `circle`, `circle-filled`, `check`, `slash-circle`, `arrow-right`, `chevron-right`, `chevron-down`, `copy`, `external-link`, `info`, `warning`, `error`. Known downstream consumers: signoff 4-state cell uses `check` + `slash-circle` + `circle` + `circle-filled` (5.9); tree expanders use `chevron-right`/`chevron-down` (5.10); copy button swaps `copy`→`check` (5.8, DD-12); activity feed uses `check`/`slash-circle`/`error` (5.11/5.16). Build the sprite to satisfy these glyphs. [Source: epics.md:2444; UX §7.2 / §6.6 / §6.8]

### Frozen tokens to consume (do NOT redefine — Story 5.2 froze these)

```css
--font-serif: "Fraunces", Georgia, serif;
--font-sans:  "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono:  "JetBrains Mono", ui-monospace, "Menlo", monospace;
```
Your `@font-face` `font-family` strings MUST be exactly `Fraunces`, `Inter`, `JetBrains Mono` (match these tokens **and** the stylelint allowlist [.stylelintrc.json:26-32]). [Source: src/sdlc/dashboard/static/styles/tokens.css:43-46; UX §3.2:584-594]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — static-asset URL convention (`/static/` prefix vs root-relative). BLOCKING — freeze before authoring the sprite reference + index.html links.**
The epic AC2 writes the `<use href>` as `/static/icons/sprite.svg#…`, and DD-10 places fonts under `dashboard/static/fonts/`. But the Story-5.1 server serves static at **root-relative** URLs: `resolve_static_file` strips the leading `/` and joins to `static_dir` [server.py:93-96], so a request for `/static/icons/sprite.svg` resolves to `static_dir/static/icons/sprite.svg` → **404**. Files physically at `static/icons/sprite.svg` are served at `/icons/sprite.svg`; `tokens.css` at `static/styles/tokens.css` is served at `/styles/tokens.css`.
- **D1 (option a) — add a `/static/` URL namespace to the server (recommended):** make the static handler strip a leading `/static/` so `/static/icons/sprite.svg` → `static_dir/icons/sprite.svg`. *Pro:* honors the epic AC `<use href>` verbatim; gives a clean URL namespace separating app assets (`/static/…`) from API routes (`/state.json`, `/api/dora`); future-proof for 5.12's forbidden-patterns/href grep. *Con:* a small additive server edit (update the 5.1 static-serving tests; note in the PR — additive, root-served files can still resolve or 404 unchanged).
- **D1 (option b) — reference assets at root-relative URLs (`/icons/sprite.svg`, `/styles/tokens.css`, `/fonts/…`):** treat the AC's `/static/` as illustrative package-relative shorthand (the same way the 5.2 epic path `dashboard/static/…` was treated as shorthand). *Pro:* zero server change. *Con:* the `<use href>` then literally diverges from the AC text; whatever you pick is frozen for every later component.
- **Recommendation: (a)** — honor the AC href and establish a durable `/static/` namespace. Either way, **freeze the chosen convention this story** and use it consistently in `index.html` and the sprite reference. Escalate to the Project Lead only if adding the `/static/` prefix to the server is contested.

### Project Structure Notes

- New: `src/sdlc/dashboard/static/fonts/*.woff2` (11), `src/sdlc/dashboard/static/icons/sprite.svg`. `@font-face` appended to the existing `src/sdlc/dashboard/static/styles/tokens.css`. Static assets live inside the `dashboard` package and ship via hatch `force-include` (ADR-005 `package_data`) [architecture.md:276, :912 names `fonts/` under `dashboard/static/`].
- **Path note:** the epic AC uses `dashboard/static/…` package-relative shorthand; the real tree is `src/sdlc/dashboard/static/…` (same convention 5.2 followed). The sprite goes under an `icons/` subdir per AC2; fonts under `fonts/` per DD-10.
- **Server module boundary unchanged:** static files are served by the `serve_static` fall-through [server.py:170], NOT via a route — fonts/sprite need no route registration. The only server edit is the MIME fix (Task 3) within the existing `dashboard` package (no new cross-module dependency; the one-way `dashboard → state/journal` edge is untouched).
- 5.3 and 5.4 are mutually-independent L2 siblings (no edge between them in the DAG); both branch from `main`, linear merge, rebase between merges (CONTRIBUTING §3). Both depend only on 5.2's frozen tokens.
- Zero wire-format contracts (CSS/SVG/fonts are not wire contracts) → freeze stays 7/7. Quality gate (CONTRIBUTING §1) applies to new `scripts/*.py`.

### Net-new CI gate this story stands up (DAG Decision D2 — incremental, single CI surface)

This story adds the **no-Google-Fonts / no-CDN** grep gate (AC1) as a sibling of the 5.2 DD-09 gate, in the same CI matrix + pre-commit. Later foundation stories add: no-framework + transition-grep (5.4), color-only signaling (5.5), forbidden-patterns + axe-core + keyboard (5.12). Keep each gate small, composable, and on one CI surface — do not fork a second CI system. [Source: docs/sprints/epic-5-dag.md Decision D2 (ratified = a)]

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Forbidden-pattern gate script | Copy the DD-09 gate shape (arg-parse, globs, comment-strip, exit 0/1/2, `file:line:col` to stderr) | scripts/check_dashboard_no_data_theme.py |
| Static serving + immutable cache | Existing `serve_static` (only add the woff2/woff MIME entry) | src/sdlc/dashboard/server.py:103-113 |
| Path-traversal containment | `assert_contained` (already guards static; real font files pass, symlinks rejected) | server.py:98 → concurrency/path_guard.py |
| Served-header test pattern | `running_dashboard` fixture + `http_get`, assert `headers.get(...)` | tests/unit/dashboard/test_dashboard_routes.py:18-21; conftest.py:20-48 |
| Gate-script import in tests | `tests/conftest.py:19-22` puts `scripts/` on `sys.path` | tests/conftest.py |
| Wheel force-include form | Mirror the `tokens.css` force-include entry | pyproject.toml |

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2428-2451] — Story 5.3 ACs (verbatim above)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §3.2:582-628] — font families, the self-host weight subsets, `font-feature-settings: 'ss01','cv11'`
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §Implementation:340-359 / DD-03:90 / DD-10:381] — file layout (`fonts/`, `sprite.svg`), `<use href>` mechanics, no-CDN
- [Source: docs/ux/dashboard-prototype/dashboard.html:7-9] — the three Google-CDN `<link>` tags to REMOVE
- [Source: src/sdlc/dashboard/server.py:86-113] — static resolution + the `mimetypes.guess_type` MIME gap (Task 3) + `_IMMUTABLE_CACHE` (AC2)
- [Source: src/sdlc/dashboard/static/index.html] — current skeleton (links nothing yet)
- [Source: src/sdlc/dashboard/static/styles/tokens.css:5-6,43-46] — `@font-face` reservation + frozen family tokens
- [Source: src/sdlc/dashboard/static/styles/.stylelintrc.json:26-32] — `font-family` allowlist (`Inter`/`Fraunces`/`JetBrains Mono`)
- [Source: scripts/check_dashboard_no_data_theme.py] — gate-script template to mirror (Task 5)
- [Source: .github/workflows/ci.yml] — `quality-gates` matrix step wiring; `frontend-gates` job; `ci-gate` required check
- [Source: .pre-commit-config.yaml] — DD-09 hook (sibling-hook template)
- [Source: pyproject.toml] — dashboard static `force-include` (file-by-file; add fonts + sprite)
- [Source: docs/sprints/epic-5-dag.md#5 Worktree Assignments (5.3 row) / Decision D2] — no-Google-Fonts gate; ADR-if-sprite>12; single CI surface
- [Source: _bmad-output/planning-artifacts/architecture.md:157,160,276,912] — no-npm/no-build runtime; no outbound HTTP; package_data; planned `fonts/` location

## Dev Agent Record

### Agent Model Used

Composer (bmad-dev-story)

### Debug Log References

- Decision D1 ratified: option (a) — `/static/` URL namespace in `resolve_static_file`
- TDD-first: gate script + MIME integration tests written before implementation
- Full suite: 3888 passed, coverage 88.59%, freeze 7/7 unchanged

### Completion Notes List

- Self-hosted 11 `.woff2` files (Fraunces 400/500/600, Inter 300–700, JetBrains Mono 400/500/600) + `OFL.txt`
- `@font-face` block + `font-feature-settings` appended to `tokens.css`; frozen token values untouched
- Server: `mimetypes.add_type` for woff2/woff; `/static/` prefix strip in `resolve_static_file`
- 12-icon `sprite.svg` with ADR-trigger header comment; `<use href="/static/icons/sprite.svg#…">` frozen in `index.html`
- DD-10 gate script + CI/pre-commit wiring; wheel force-include for all assets + integration test

### File List

- `.github/workflows/ci.yml`
- `.pre-commit-config.yaml`
- `pyproject.toml`
- `scripts/check_dashboard_no_external_fonts.py`
- `src/sdlc/dashboard/server.py`
- `src/sdlc/dashboard/static/index.html`
- `src/sdlc/dashboard/static/styles/tokens.css`
- `src/sdlc/dashboard/static/fonts/OFL.txt`
- `src/sdlc/dashboard/static/fonts/fraunces-400.woff2`
- `src/sdlc/dashboard/static/fonts/fraunces-500.woff2`
- `src/sdlc/dashboard/static/fonts/fraunces-600.woff2`
- `src/sdlc/dashboard/static/fonts/inter-300.woff2`
- `src/sdlc/dashboard/static/fonts/inter-400.woff2`
- `src/sdlc/dashboard/static/fonts/inter-500.woff2`
- `src/sdlc/dashboard/static/fonts/inter-600.woff2`
- `src/sdlc/dashboard/static/fonts/inter-700.woff2`
- `src/sdlc/dashboard/static/fonts/jetbrains-mono-400.woff2`
- `src/sdlc/dashboard/static/fonts/jetbrains-mono-500.woff2`
- `src/sdlc/dashboard/static/fonts/jetbrains-mono-600.woff2`
- `src/sdlc/dashboard/static/icons/sprite.svg`
- `tests/fixtures/dashboard_css/violation_google_fonts.html`
- `tests/integration/test_wheel_build.py`
- `tests/integration/test_wheel_dashboard_static.py`
- `tests/unit/dashboard/test_dashboard_fonts.py`
- `tests/unit/dashboard/test_dashboard_sprite.py`
- `tests/unit/dashboard/test_dashboard_static_assets.py`
- `tests/unit/scripts/test_check_dashboard_no_external_fonts.py`

## Change Log

- 2026-06-24: Story 5.3 created (create-story) — self-host fonts + 12-icon SVG sprite; Decision D1 (static URL convention) raised; woff2/woff MIME server gap flagged for tests-first fix.
- 2026-06-24: Implementation complete — D1=(a) `/static/` namespace; self-hosted fonts + sprite; DD-10 gate; MIME fix; wheel packaging.
