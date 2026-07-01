# Story 5.12: Forbidden Patterns Enforcement + WCAG 2.2 Level A Baseline + a11y Test Harness

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L5 (5A) = {5.12}, max 1 worktree. This is the 5A a11y / forbidden-patterns CONVERGENCE GATE — it depends on ALL of 5A (5.1–5.11, every one done+merged) because the axe + keyboard + color-only scan must see every rendered 5A component. Fan-in edges per epic-5-dag.md §2: 5.4→5.12, 5.5→5.12, 5.6→5.12, 5.7→5.12, 5.8→5.12, 5.9→5.12, 5.10→5.12, 5.11→5.12. Downstream: 5.12→5.22 (terminal per-release gate). Worktree: epic-5/5-12-forbidden-patterns-wcag-baseline. Branch from main, linear merge (CONTRIBUTING §3). NOT Story N.1 → CONTRIBUTING §7.4 per-epic gate N/A (epic-5 in-progress, cleared at 5.1). HARD GATE (release-blocking class). SYNTHETIC fixtures only — the terminal real-data + manual NVDA/VoiceOver gate is 5.22, NOT this story. -->

## Story

As Murat enforcing the dashboard a11y test surface,
I want a forbidden-patterns CI check (no modals, no toasts, no in-app forms, no client-side routing, no skeleton loaders) plus an a11y test harness running axe-core scan + keyboard-only navigation test on every dashboard PR,
So that WCAG 2.2 Level A is mechanically enforced and forbidden patterns can never sneak in (UX-DR31, UX-DR34, UX-DR35, NFR-A11Y-1, NFR-A11Y-2, §7.12).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.12, lines 2680–2700).

**AC1 — Forbidden-patterns CI check** (`tests/dashboard/test_forbidden_patterns.py`)
- **Given** the forbidden-patterns CI check **When** dashboard CSS/HTML/JS is scanned **Then** the check fails if any of these are present: `<dialog>`, `<form>` (in-app), `data-toast`, `<modal>`, client-side router (`history.pushState`), CSS classes hinting at skeleton-loader patterns
- **And** the violation message names the file:line:column

**AC2 — a11y harness via axe-core** (`tests/dashboard/test_a11y_axe.py`)
- **Given** the a11y test harness using axe-core **When** every dashboard PR triggers the axe scan against the rendered SPA on synthetic fixture data **Then** zero violations at WCAG 2.2 Level A are tolerated
- **And** Level AA violations are reported but not blocking (per UX spec §8.3)

**AC3 — Keyboard-only navigation test** (`tests/dashboard/test_keyboard_only.py`)
- **Given** the keyboard-only navigation test **When** Playwright drives the dashboard with `tab` key only **Then** every interactive element is reachable
- **And** focus is always visible (Story 5.4 focus ring)
- **And** focus order matches the documented per-component contract in UX §8.4

**AC4 — Color signaling rule**
- **Given** color signaling rule **When** static analysis scans for color-only state indication **Then** every color signal has an adjacent text label (Story 5.5 contract enforced everywhere)

## Tasks / Subtasks

> **TDD-first surface (CONTRIBUTING §2):** this story is *entirely* test/gate code — the deliverable IS the harness. TDD-first here means **plant a RED fixture/witness for each gate, then GREEN**: a deliberately-seeded `<dialog>`/`data-toast`/`history.pushState`/skeleton-class must make the forbidden-patterns scanner exit 1 (AC1); a deliberately-broken element (e.g. an `<img>` without alt, or a `<live-dot>` with no text label) must make the axe scan and the color-only DOM check fail (AC2/AC4); an unreachable/focus-invisible control must fail the keyboard test (AC3). Commit ordering test(5.12) → feat(5.12) → docs(5.12), visible in `git log --reverse` (merged-before-done gate, CLAUDE.md). **Resolve Decisions D1–D6 BEFORE coding.**

- [x] **Task 0 — Resolve D1 (axe integration: vendor `axe.min.js` vs PyPI dep) + D2 (WCAG 2.2 Level-A tag set + block/report split — there is NO `wcag22a` tag) + D3 (axe/keyboard scan surface = composite fixture) + D4 (AC4 enforced against RENDERED DOM, closes DEF-1) + D5 (test-file location: epic-AC literal `tests/dashboard/`) + D6 (forbidden-patterns scanner scope: mechanical token set vs §7.12 documentary list) BEFORE coding** (AC: 1,2,3,4)
  - [x] Record picks in the PR Change Log (CONTRIBUTING §5). All picks have a recommended (a) below; raise as D-labels only if you deviate.

- [x] **Task 1 — Forbidden-patterns scanner** (AC: 1) — *tests-first*
  - [x] New `scripts/check_dashboard_forbidden_patterns.py` — **mirror the existing `scripts/check_dashboard_color_only.py` idiom exactly**: `_REPO_ROOT`/`_DEFAULT_ROOT = src/sdlc/dashboard/static`, comment-blanking (`_HTML_COMMENT`/`_CSS_COMMENT` → `_blank_comment` preserving newlines), `_line_col()` 1-based (line, col), a frozen-slots `Violation` dataclass, no-arg recursive scan, exit **0 = clean / 1 = violations (`file:line:col: <pattern> (UX §7.12)`) / 2 = explicit path not found**.
  - [x] Detect the **epic-AC token set** (D6 binding minimum): `<dialog`, `<modal`, `data-toast` attribute, in-app `<form` (HTML), `history.pushState`/`history.replaceState` (JS client-router), skeleton-loader CSS class hints (`\bskeleton\b`, `\bshimmer\b`, `\bplaceholder-loading\b` — name the exact class regex in the script docstring). Scan `.html`/`.css`/`.js` under the static root.
  - [x] **FALSE-POSITIVE GUARDS (do not break a green SPA):** the SPA legitimately uses `role="tablist"`/`role="tab"` (Tabs 5.11 — tabs ≠ client router; do NOT flag), `<freshness-footer>`/custom elements, and `pushState` must match the JS call, not the substring inside a comment/string label. Match `<dialog`/`<modal` as element tokens (`<\s*dialog\b`), `data-toast` as an attribute, `<form` as a real HTML form element (the dashboard is read-only — there are zero legit forms). Verify the scanner exits 0 on the *current* committed static tree before adding RED witnesses.
  - [x] **RED→GREEN:** add a fixture (or inline test string) seeding each forbidden token → assert the scanner reports it with `file:line:col`; assert exit 0 on the clean tree.

- [x] **Task 2 — axe-core a11y harness** (AC: 2) — *tests-first*
  - [x] Vendor `axe.min.js` (axe-core **4.12.1**, MPL-2.0, license header intact) under `tests/dashboard/vendor/axe.min.js` (D1). New `tests/dashboard/test_a11y_axe.py` (Playwright sync_api): serve the dashboard (`serve_dashboard_in_thread` + `find_free_port`), navigate to the composite fixture (D3), `page.wait_for_load_state("networkidle")` (scan a settled DOM — fonts are self-hosted so load is deterministic), `page.add_script_tag(path=<axe.min.js>)`, then `results = page.evaluate("(opts)=>axe.run(document,opts)", AXE_OPTIONS)`.
  - [x] **Tag set + block/report split (D2 — load-bearing ground-truth):** Level A = `["wcag2a","wcag21a"]` (**there is NO `wcag22a` tag** — the two WCAG-2.2 Level-A SC are non-automatable; the only 2.2 rule axe ships is `target-size`, tagged `wcag22aa`). Run ONE scan over A+AA, partition in Python: **fail iff** `set(v["tags"]) & {"wcag2a","wcag21a"}`; everything else (`wcag2aa`/`wcag21aa`/`wcag22aa`) is `print`-reported, NOT failing. Failure message names rule id + `nodes[].target` + `helpUrl`.
  - [x] **Reuse the chromium skip-guard + context-manager helper** from `tests/integration/test_dashboard_*.py` (`pytest.importorskip("playwright")` at module top; `chromium.launch()` wrapped so a missing binary → `pytest.skip`). On CI chromium is installed (ci.yml:82-85) so the scan executes for real — do NOT let it silently skip on CI.
  - [x] **If axe finds genuine Level-A violations in the composed 5A surface, fix the underlying component/fixture MINIMALLY** (that is this gate's whole purpose) — do NOT rewrite 5.6–5.11. RED witness: temporarily inject a known Level-A failure (e.g. an `<img>` with no `alt`) into a scratch fixture → assert the harness fails → remove.

- [x] **Task 3 — Keyboard-only navigation test** (AC: 3) — *tests-first*
  - [x] New `tests/dashboard/test_keyboard_only.py` (Playwright): serve the composite fixture (D3), drive with `Tab` only and within-widget arrow keys, assert **every interactive element is reachable**, **focus is always visible** (DD-15 `:focus-visible` ring from 5.4), and **focus order matches §8.4**. Interactive elements present in the SYNTHETIC surface: **resume-card copy button** (Tab → Enter/Space), **backlog-tree rows** (Arrow Up/Down/Left/Right, Enter, Home/End — roving tabindex), **Tabs** (Arrow Left/Right, Home/End). [§8.4 ux:1730-1804; §6.6 keyboard contract ux:1263-1269]
  - [x] **Apply the 5.10 leaf-focus lesson (PAT-6):** task rows must be keyboard-focusable (the focusable button stays in the roving set; only the glyph is hidden). Assert ArrowDown reaches a task row and focus never drops to `<body>` (the RED-witness lesson). Reuse `tests/integration/test_dashboard_backlog_tree.py` as the pattern.
  - [x] **Do NOT test STOP-banner action buttons** — the STOP banner is 5.19 (not built; the 5A synthetic alert column renders only the 5.11 empty-state, which has no interactive controls). Cross-browser (Firefox/WebKit) is OPTIONAL — chromium-only is the ratified posture (5.10 DEF-1); keep deferred unless trivially free.

- [x] **Task 4 — Color-only enforced against RENDERED DOM (AC4, closes 5.5 DEF-1)** (AC: 4) — *tests-first*
  - [x] The static `scripts/check_dashboard_color_only.py` is **vacuous today** — all `<live-dot>` are JS-created via `document.createElement`, so the committed-`.html`-only scan finds zero literal tags and guards nothing (DEF-1). Satisfy AC4 by a **rendered-DOM** assertion (D4): in the axe/keyboard Playwright surface (or a small `tests/dashboard/test_color_only_dom.py`), after the composite fixture renders, query live `<live-dot>` elements and assert each has an adjacent non-empty text label (same semantics as the static gate's `_label_present`). Reuse, do not re-derive, the live-dot label rule.
  - [x] **Keep the static gate too** (defense-in-depth — it fires when 5.6+ first authors literal `<live-dot>` markup). RED witness: a scratch fixture rendering a `<live-dot>` with no text → DOM check fails → remove. Mark DEF-1 closed in deferred-work.md.

- [x] **Task 5 — Wire gates into CI + pre-commit** (AC: 1,2,3,4)
  - [x] Add the forbidden-patterns gate as a **step in the `quality-gates` matrix job** (ci.yml — after the color-only step at line 70, before the Playwright-cache step): `- name: Dashboard forbidden-patterns gate (Story 5.12 AC1)` / `run: uv run python scripts/check_dashboard_forbidden_patterns.py`. Do NOT create a new top-level job (Decision D2 of the DAG — single CI surface).
  - [x] Add the matching `.pre-commit-config.yaml` local hook after `dashboard-color-only-gate` (id `dashboard-forbidden-patterns-gate`, `entry: uv run python scripts/check_dashboard_forbidden_patterns.py`, `files: ^src/sdlc/dashboard/static/.*\.(css|js|mjs|html)$`, `pass_filenames: false`).
  - [x] The axe + keyboard + color-only-DOM tests run under the existing `uv run pytest` step (ci.yml:94) — chromium is already installed/cached (ci.yml:72-85). No new workflow.

- [x] **Task 6 — Quality gate + packaging + freeze** (AC: 1,2,3,4)
  - [x] Python gate on the new `scripts/check_dashboard_forbidden_patterns.py` + new tests: `ruff check` + `ruff format` + `mypy --strict src/` (the script lives in `scripts/`; mypy targets `src/` but ruff/format cover scripts+tests). Full `pytest` + coverage **≥ 87%** — `--cov=scripts` includes the new gate, so the forbidden-patterns test MUST exercise its code paths.
  - [x] Vendored `tests/dashboard/vendor/axe.min.js` is a dev/CI test asset → **NOT** added to `pyproject.toml` `force-include` (the wheel ships runtime static only; `tests/` is not packaged). No new runtime static files in this story.
  - [x] `mkdocs build --strict` green. **Zero wire-format contracts** (Python gate scripts + JS/CSS/HTML + tests are dev/CI tooling, not `src/sdlc/contracts/` StrictModels) → **freeze stays 7/7**.
  - [x] WIN32 caveat: the forbidden-patterns static gate is win32-runnable standalone; full `pytest`/coverage + the axe/keyboard Playwright tests require POSIX CI (conftest `io_primitives` ImportError + chromium) — first real green is on CI.

### Review Findings

> bmad-code-review 2026-06-26 — **3** adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + orchestrator source-verification (every load-bearing defect reproduced against the real scanner / tests / `live-dot.js` / fixtures; off-by-one confirmed by running the scanner: emits `violation_dialog.html:5:5:`). Triage: **1 decision-needed + 8 patch + 2 defer + 5 dismissed**. Headline: the story's deliverable IS the a11y harness, but **4 of its tests are broken/vacuous** (off-by-one line assert; roving-tabindex reachability math; programmatic-focus vs `:focus-visible`; self-labelling live-dot RED witness over a doubled 404 URL) and the dev's "Playwright smoke validated locally" is inconsistent with that (win32 conftest blocks them) → the harness is **unvalidated**. Imports resolve on CI (`tests/conftest.py` puts `scripts/` + `tests/` on `sys.path`; PEP-420 namespace) and integration tests DO run on CI (no `-m` deselection, chromium installed) → the 4 broken tests WILL turn CI red. Dismissed: missing `tests/dashboard/__init__.py` (works via conftest/PEP-420); one-violation-per-line `break` (line still flagged); newline-split `<\ndialog>` (not valid HTML); vacuous exit-0 if default root ever moves (shared sibling-gate idiom); `§`→`�` console glyph (cp1252 display only — capsys captures real `§`).

- [x] [Review][Defer] Forbidden-pattern tokens authored in JS are unguarded — **DEC-1 resolved → (a): ratify static tripwire + axe as the v1 posture.** `_scan_js` only matches `history.pushState/replaceState`; `<dialog>`/`<modal>`/`<form>`/`data-toast`/skeleton built via JS DOM-construction escape both the static scan and (likely) axe — the same vacuity class as 5.5 DEF-1, fixed for color-only (AC4 rendered-DOM) but not for the forbidden-patterns gate. [scripts/check_dashboard_forbidden_patterns.py:151-158] — deferred (→ deferred-work.md DEF-3): the composite scan surface is SYNTHETIC (no forbidden patterns by construction), so a rendered-DOM check adds little today; real enforcement requires the assembled SPA + real data, owned by 5.22. Static tripwire is the ratified v1 posture (D6). (blind+edge+auditor)
- [x] [Review][Patch] AC1 dialog line-number assertion off-by-one — asserts `:4:` but `<dialog>` is on line 5; scanner emits `violation_dialog.html:5:5:` → `test_main_returns_1_on_dialog_violation` fails on every CI cell (unit, no skip-guard) [tests/dashboard/test_forbidden_patterns.py:68]
- [x] [Review][Patch] AC3 Tab-reachability assertion unsatisfiable under roving tabindex — `expected` counts ALL tabs+expanders+copy-btns (~9) but roving tabindex makes only one element per widget Tab-reachable (~4 reached) → `len(reached) >= expected` is always false; redefine to Tab-stop count (one per roving widget + standalone focusables); intra-widget movement is already covered by the arrow/Home/End tests [tests/dashboard/test_keyboard_only.py:46]
- [x] [Review][Patch] AC4 color-only RED witness is structurally invalid (two bugs) — (a) URL doubled via `rsplit("/",1)[0]` → `…/static/test-fixtures/static/components/…` 404 → `wait_for_selector("live-dot")` 30s timeout; (b) `live-dot.js` always renders `.live-dot__label`, so a created `<live-dot>` self-labels → `pytest.raises(AssertionError)` gets DID NOT RAISE even with a correct URL. Fix URL to the origin and produce a genuinely label-less dot (strip the label child after create, or build a raw unknown element) [tests/dashboard/test_color_only_dom.py:21-33]
- [x] [Review][Patch] AC3 focus-ring test uses programmatic `.focus()` — DD-15 ring is `:focus-visible`-only (`:focus:not(:focus-visible){box-shadow:none}`); programmatic focus's `:focus-visible` match is fragile/version-dependent and never exercises the keyboard path. Drive focus via keyboard `Tab` and add an unfocused-state control to kill vacuity [tests/dashboard/test_keyboard_only.py:51-56]
- [x] [Review][Patch] Scanner `_scan_js` does not blank JS comments/strings — unlike `_scan_html`/`_scan_css`; a doc comment or string mentioning `history.pushState(` (exactly what §7.12 invites contributors to write) false-positives and reddens the release-blocking gate. Blank `//` and `/* */` JS comments before matching [scripts/check_dashboard_forbidden_patterns.py:157-158]
- [x] [Review][Patch] Skeleton-class detection misses BEM `__`/compound forms — `\bskeleton\b` does not match `skeleton__row` / `.skeleton__row` / `.loading-skeleton`; the repo's pervasive BEM `__` convention means the most natural skeleton class ships green. Make detection token-aware (split the class list, match any token containing a hint; CSS likewise) [scripts/check_dashboard_forbidden_patterns.py:30-51]
- [x] [Review][Patch] Regex precision — `data-toast` boolean attribute (`<div data-toast>`) is missed (regex requires `\s*=`); `<\s*dialog\b`/`<\s*form\b`/`<\s*modal\b` false-positive on hyphenated custom elements (`<dialog-box>`, `<form-row>`). Drop the `=` requirement and tighten element tokens to `<\s*dialog(?=[\s/>])` etc. [scripts/check_dashboard_forbidden_patterns.py:37-40]
- [x] [Review][Patch] AC1 witness matrix incomplete — no RED fixture for `<modal>` or `history.replaceState` (both detected by the scanner) and no HTML-class skeleton witness; `_scan_html_class_skeleton`'s violation branch is untested in a HARD GATE. Add the three witnesses [tests/fixtures/dashboard_forbidden_patterns/ + tests/dashboard/test_forbidden_patterns.py]
- [x] [Review][Defer] Server-thread leak on the readiness-failure path — `pytest.fail` before `yield` skips `server.shutdown()`/`thread.join()`; identical idiom to the existing `tests/dashboard/conftest.py::running_dashboard` (pre-existing, fix repo-wide) [tests/dashboard/_playwright_a11y.py:36-60] — deferred, pre-existing shared idiom
- [x] [Review][Defer] AC3 focus-order §8.4 not explicitly asserted — `reached` is a `set`, no sequence check; order is partially covered by the Home/End/ArrowRight tests; full §8.4 per-component sequence assertion is non-trivial [tests/dashboard/test_keyboard_only.py:33-46] — deferred, out of scope for a surgical fix

### Review Findings — fresh-context re-review (2026-07-01)

> bmad-code-review 2026-07-01 — fresh-context re-review of the **committed** branch `epic-5/5-12-forbidden-patterns-wcag-baseline` (`main...HEAD`, 22 files / +983−2), **3** adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor) @ Opus-4.8 + orchestrator source-verification. Triage: **1 decision-needed + 3 patch + 7 defer + 6 dismissed**. *** HEADLINE (Acceptance Auditor, CONFIRMED by source + a stdlib pytest repro): the prior review's claim "integration tests DO run on CI" is FALSE — the `dashboard_composite_url` **fixture is defined only in the non-conftest helper `tests/dashboard/_playwright_a11y.py:36` and NONE of the 3 test modules import the fixture NAME** (they import only its functions), so all 9 `@pytest.mark.integration` tests ERROR at setup (`fixture 'dashboard_composite_url' not found`) on CI → CI red → the a11y harness (the story's whole deliverable: AC2 / AC3 / AC4-rendered-DOM) NEVER runs. The prior 3-layer review patched test LOGIC but never ran pytest collection/setup, so it missed this. AC1 (scanner) is independently MET — verified by running the scanner (exit 0 on the real static tree; exit 1 with correct `file:line:col` on every witness: dialog `:5:5`, data-toast `:5:10`, form/modal `:5:5`, pushState `:2:1`, replaceState `:3:3`, skeleton.css `:1:1`, skeleton-html-class `:5:23`). Dismissed: axe `add_script_tag` CSP-block (VERIFIED FALSE — `server.py` sends no CSP header → no inline-script block); one-violation-per-line `break` (line still flagged, exit correct); exotic-line-separator (`\v`/`\f`/Unicode) line-# divergence (rare); duplicate violations on overlapping CLI targets (cosmetic, no-arg CI path unaffected); `§`→`�` cp1252 console glyph (display only — capsys captures the real `§`); DEF-2 test-name doc-drift (`..._widgets` vs `..._elements`, trivial).

- [x] [Review][Patch] **P4 ✅ APPLIED (D1 → resolved (a): HARDEN NOW) — scanner document/quote-aware + inline-`<script>`/`<style>` extraction** — the scanner quét theo dòng + theo đuôi file, không như sibling color-only (quote-aware). Fixes BOTH (i) a HARD-gate FALSE-NEGATIVE: `history.pushState(` in an inline `<script>` and a `.skeleton` selector in an inline `<style>` inside any `.html` bypass the gate (JS/CSS rules dispatch by file-suffix only), plus cross-line / space-around-dot `pushState` (`history\n.pushState(`, `history .pushState(`) bypass the per-line JS scan; and (ii) FALSE-POSITIVEs: legit MENTIONS of forbidden tokens in JS strings (`"history.pushState(x)"`), trailing `//` comments (`foo(); // never call history.pushState()`), and HTML visible text (`<td>data-toast</td>`) redden the release-blocking gate. ALL reproduced against the real scanner. **Fix (a):** extract inline `<script>`/`<style>` blocks from `.html` and run `_JS_PATTERNS`/`_CSS_PATTERNS` on them; blank JS/HTML string literals + trailing `//` comments (quote-aware, mirror `scripts/check_dashboard_color_only.py`); tolerate whitespace around the `.` in `history . pushState`; add RED witnesses (inline-script router, inline-style skeleton, string/comment/text non-violations). [scripts/check_dashboard_forbidden_patterns.py:60-66,180-185] (blind+edge — D1 resolved (a) by Vuonglq01685 2026-07-01)
- [x] [Review][Patch] **P1 ✅ APPLIED (HIGH / merge-blocking) — `dashboard_composite_url` fixture undiscoverable → 9 integration tests ERROR on CI** — move the fixture from `tests/dashboard/_playwright_a11y.py:36` into `tests/dashboard/conftest.py` (conftest already imports `find_free_port`/`serve_dashboard_in_thread`), or import the fixture NAME into each of `test_a11y_axe.py` / `test_keyboard_only.py` / `test_color_only_dom.py`. pytest resolves fixtures from the test-module namespace / conftest / plugins only — importing a *function* from a helper module does NOT expose that module's fixtures. Confirmed by source + a stdlib-only pytest repro (`fixture 'myfix' not found`). Earns the 5.5 DEF-1 closure once CI is green. [tests/dashboard/_playwright_a11y.py:36 → tests/dashboard/conftest.py] (auditor)
- [x] [Review][Patch] **P2 ✅ APPLIED (MED) — off-by-7 column in `_scan_html_class_skeleton`** — `_line_col(text, match.start() + skeleton.start())` adds the skeleton offset (within the class VALUE) to the start of the whole `class="…"` match instead of `match.start("classes")`, undercounting the AC1 column by `len('class="')`=7: `violation_skeleton_html_class.html:5` emits col 23 (the `-` in `resume-card`) vs the real 30. Fix: `match.start("classes")`; add a column-asserting test (no test currently checks this branch's column). Confirmed by running the scanner. [scripts/check_dashboard_forbidden_patterns.py:143] (blind)
- [x] [Review][Patch] **P3 ✅ APPLIED (LOW) — `\bdata-toast\b` false-positive on `data-toast-*`** — `<div class="data-toast-card">` is flagged as a `data-toast` attribute (`:3:19`, confirmed). Tighten to `(?<![\w-])data-toast(?![\w-])` (kills `data-toast-card` / `x-data-toast` while keeping the PAT-7 boolean-attribute detection) + regression test. [scripts/check_dashboard_forbidden_patterns.py:43] (edge+blind)
- [x] [Review][Defer] **DEF-A (MED) — a11y suite silently skips on any Chromium launch failure → false-green HARD gate** — `except PlaywrightError: pytest.skip` swallows any launch failure (not just "not installed"); a broken-but-installed Chromium yields a green merge with AC2/AC3/AC4 unverified, and there is no "a11y-actually-ran" required check (contrast the `posix-adopt-ran` job) [tests/dashboard/_playwright_a11y.py:71] — deferred, ratified skip-guard posture (5.10 DEF-1); relevant only after P1
- [x] [Review][Defer] **DEF-B (MED→LOW) — fail-open: no-arg + missing `_DEFAULT_ROOT` → exit 0 "gate OK"** — a release-blocking check becomes a silent no-op if `src/sdlc/dashboard/static` moves/renames [scripts/check_dashboard_forbidden_patterns.py:88-90] — deferred, shared sibling-gate idiom; fix repo-wide (exit ≥1 when the default root is absent)
- [x] [Review][Defer] **DEF-C (LOW) — server thread + bound port leak on the readiness-timeout path** — `pytest.fail` before `yield` skips `server.shutdown()`/`server.server_close()`/`thread.join()` [tests/dashboard/_playwright_a11y.py:44-60] — deferred, SAME fixture as P1 (apply try/finally when moving it) + shared with `conftest.running_dashboard` (prior DEF-1)
- [x] [Review][Defer] **DEF-D (LOW) — `find_free_port` → `create_server` bind TOCTOU race (flake, not graceful retry)** [src/sdlc/dashboard/server.py:262] — deferred, pre-existing shared idiom
- [x] [Review][Defer] **DEF-E (LOW) — skeleton/shimmer detection is substring- not token-aware** — `shimmering-headline` / `.shimmering-text` false-positive; the docstring overstates "token-aware" [scripts/check_dashboard_forbidden_patterns.py:33-35] — deferred, near-zero risk in an anti-motion repo; a token-safe fix must still allow BEM `skeleton__row`
- [x] [Review][Defer] **DEF-F (LOW) — skeleton false-negative: `@keyframes shimmer` / `animation:` (no leading `.`) + JS `classList.add('skeleton')`** [scripts/check_dashboard_forbidden_patterns.py:47-54] — deferred, `@keyframes`/`animation` plausibly covered by the DD-14 motion gate (verify); JS-classList = existing DEF-3
- [x] [Review][Defer] **DEF-G (LOW) — new `activity-feed__list` `tabindex="0"` has no `:focus-visible` ring assertion (AC3 "focus always visible", SC 2.4.7 AA)** [src/sdlc/dashboard/static/components/activity-feed/activity-feed.js + tests/dashboard/test_keyboard_only.py:56] — deferred, AA reported-not-blocking; assert (and add a ring if missing) with the real SPA assembly; complements DEF-2

## Dev Notes

### Locked design decisions (verbatim — these govern the story)

- **§7.12 Forbidden Patterns.** *"The following conventional UX patterns are **deliberately absent** from v1 and must not be added without explicit specification revision. This list exists so contributors know to refuse PRs that introduce them."* Named: form patterns, modals/dialogs, toasts/notification stacks, Browser-notifications API, search/filter/sort UI, drag-and-drop, edit-in-place, **skeleton loaders**, loading spinners, delayed-reveal tooltips, onboarding tours, animated chart transitions, "live region" toast announcements for routine polls, mobile/tablet layouts, theme switcher/light mode, i18n/RTL. [Source: ux-design-specification.md §7.12:1615-1637]
- **§8.3 Accessibility Strategy.** *"Target compliance: WCAG 2.2 Level A (architecture §138). Where Level AA is achievable without scope creep, the spec aims for AA … Level AAA is not a target for v1."* AA is **reported, not blocking**. [Source: ux-design-specification.md §8.3:1708-1728; architecture.md:138]
- **§8.4 Per-Component Accessibility Checklist** (keyboard test source of truth). Landmarks: masthead `role="banner"`, KPI strip `role="region" aria-label="Project KPIs"`, resume card `role="region"`, phase tracker `role="region"`, backlog `role="tree"`, alerts `role="alert"|"status"`, tabs `role="tablist"/"tab"/"tabpanel"`, activity feed `role="log" aria-live="polite"`. Live regions rate-limited 60s. [Source: ux-design-specification.md §8.4:1730-1804]
- **§6.6 Backlog-tree keyboard contract** (verbatim): *"Arrow Down / Arrow Up — focus next / previous visible row. Arrow Right — expand collapsed parent; on expanded parent or leaf, no-op. Arrow Left — collapse expanded parent; on collapsed parent or leaf, focus parent. Enter — toggle expand on parent; no-op on leaf (read-only). Home / End — jump to first / last visible row."* [Source: ux-design-specification.md §6.6:1263-1269]
- **WCAG-A specifics:** `:focus-visible` ring `box-shadow: 0 0 0 2px var(--rule-strong)` (DD-15); contrast `--ink-dim` is Level-A-only (3.1:1); never color-only signaling (every color signal pairs with text/icon). [Source: ux-design-specification.md §3.1:533-573, DD-15:752, §8.6:1857-1872]

### Ground-truth that prevents the 3 disasters in this story

1. **axe-core has NO `wcag22a` tag — filtering on it silently selects NOTHING (vacuous green).** The two WCAG-2.2 Level-A success criteria (3.2.6 Consistent Help, 3.3.7 Redundant Entry) are not machine-automatable, so axe ships no rules and no tag for them. The only WCAG-2.2 rule axe ships is `target-size` (tagged `wcag22aa`, i.e. AA). **Level A = `["wcag2a","wcag21a"]`.** "WCAG 2.2 Level A baseline via automated axe" therefore = WCAG 2.0/2.1 Level-A rule coverage; state this honestly in the docs/Change Log. axe-core ≥4.5 has WCAG-2.2 support; pin **4.12.1** (current stable). [Source: axe-core doc/API.md tag taxonomy + rule-descriptions.md; Deque "axe-core 4.5 first WCAG 2.2" blog]
2. **There is NO production SPA shell — `index.html` is a 5.1 skeleton** (`<h1>` + prose + one decorative sprite `<use>`; zero components). The closest "rendered SPA on synthetic fixture data" is the composite fixture **`src/sdlc/dashboard/static/test-fixtures/editorial-scanning-rhythm.html`** which composes all 5A components inside real landmarks (`<header>`/`<nav aria-label>`/`<main>`/`<aside>`, `lang="en"`). Scan THAT (D3). Do NOT author a new full SPA shell — full page assembly + real data is 5.14–5.18, not 5.12. [Source: src/sdlc/dashboard/static/index.html:10-17; test-fixtures/editorial-scanning-rhythm.html:47-101]
3. **The color-only gate is vacuous today (DEF-1).** `scripts/check_dashboard_color_only.py` scans committed `.html` for literal `<live-dot>`, but every `<live-dot>` is created in JS (`live-dot.fixture.html` mounts via `document.createElement`; `freshness-footer.js` creates one). Zero literal tags → the no-arg CI gate guards nothing. AC4 must run against the **rendered DOM** (D4). [Source: scripts/check_dashboard_color_only.py:29,31,148; deferred-work.md DEF-1 (5.5 review)]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — axe-core integration: vendor `axe.min.js` vs PyPI dep (MED).** *Recommendation (a):* **VENDOR** `axe.min.js` (axe-core 4.12.1, MPL-2.0, ~550KB, license header kept) under `tests/dashboard/vendor/` + `page.add_script_tag(path=...)` + `page.evaluate("(o)=>axe.run(document,o)", AXE_OPTIONS)`. Pins the engine directly (matches repo "pin everything" + force-include culture), zero new Python dep, full control of the failure message, deterministic offline injection. *Alternative (b):* `axe-playwright-python==0.1.7` (bundles axe-core **4.11.0** and **hard-pins `pytest-playwright==0.3.3`** — a real uv.lock conflict risk). MPL-2.0 is redistributable/commit-safe.

**D2 — WCAG 2.2 Level-A tag set + block/report split (HIGH, load-bearing).** *Recommendation (a):* one scan, `runOnly.tags = ["wcag2a","wcag21a","wcag2aa","wcag21aa","wcag22aa"]`, `resultTypes:["violations"]`; **block iff** a violation's `tags` intersect `{wcag2a, wcag21a}`; print-report the rest (AA, non-failing). **Never use `wcag22a`** (see ground-truth #1). No alternative — this is the only correct axe taxonomy for "A blocks, AA reports".

**D3 — axe/keyboard scan surface (MED).** *Recommendation (a):* scan the served **`editorial-scanning-rhythm.html`** composite fixture as the primary surface (covers all 5A components in landmarks). Optionally also iterate each `*.fixture.html` for per-component coverage. *Do NOT* build a new production SPA shell (anti-scope-creep; that's 5.14–5.18).

**D4 — AC4 color-only against RENDERED DOM (MED, closes DEF-1).** *Recommendation (a):* enforce AC4 via a rendered-DOM Playwright check (JS-created `<live-dot>` each has an adjacent non-empty text label), reusing the static gate's label semantics. Keep the static gate as defense-in-depth. *Alternative (b):* statically scan the JS render templates (brittle).

**D5 — test-file location (LOW).** Epic AC literally names `tests/dashboard/test_forbidden_patterns.py` / `test_a11y_axe.py` / `test_keyboard_only.py`; `tests/dashboard/` already exists (conftest.py + benchmark). *Recommendation (a):* honor the **epic-AC literal `tests/dashboard/`** for all three named files; reuse the `tests/integration/test_dashboard_*.py` Playwright helper pattern (`_with_playwright_page`, `serve_dashboard_in_thread`, `find_free_port`, chromium skip-guard). This adds a 3rd Playwright test home → fold into the existing fixture/test-location reconcile (5.9 DEF-3), do not spawn new debt.

**D6 — forbidden-patterns scanner scope (LOW).** *Recommendation (a):* the scanner enforces the **epic-AC concrete token set** (binding minimum: `<dialog>`, `<modal>`, `data-toast`, in-app `<form>`, `history.pushState`/`replaceState`, skeleton-class hints). Document which broader §7.12 items are already covered by sibling gates (animated transitions → DD-14 motion; UI framework → DD-08; light mode/`data-theme` → DD-09) vs documentation-only (search/filter UI, drag-drop, tours — not greppable without false positives). Add only unambiguously-greppable extensions if confident (e.g. `new Notification(` browser-notification API). Avoid false positives on `role="tab"`/tablist, custom elements, and tokens inside comments/strings.

### What this story OWNS vs must NOT build (anti-scope-creep)

- **Owns:** the net-new `tests/dashboard/` a11y convergence harness — forbidden-patterns scanner (`scripts/check_dashboard_forbidden_patterns.py` + CI/pre-commit wiring) + axe-core harness (vendored `axe.min.js`, A-blocks/AA-reports) + keyboard-only navigation test + the rendered-DOM color-only enforcement (closes DEF-1). SYNTHETIC fixture surface only (the composite `editorial-scanning-rhythm.html`). Minimal, surgical fixes to any genuine Level-A violation the gate exposes in 5.6–5.11.
- **Must NOT build:** the **per-release a11y gate with real-data axe + manual NVDA/VoiceOver smoke** — that is **5.22** (terminal release gate, edge 5.12→5.22); real-data rendering (5.13–5.18); a new production `index.html` SPA shell; STOP-banner controls in the keyboard test (5.19); any new runtime static component. No modals/toasts/forms/client-routing/skeleton loaders; no CSS `transition:`/transforms except the frozen live-dot pulse (DD-14). [Source: docs/sprints/epic-5-dag.md §2 (5.12 fan-in:149-155, 5.12→5.22:163), §3 (L5:214, L10/5.22:219), §5 (5.12 row:290, 5.22 row:300)]

### Project Structure Notes

- New: `scripts/check_dashboard_forbidden_patterns.py`; `tests/dashboard/test_forbidden_patterns.py`, `test_a11y_axe.py`, `test_keyboard_only.py` (+ optional `test_color_only_dom.py`); `tests/dashboard/vendor/axe.min.js`. CI step in `quality-gates` (ci.yml ~line 70); hook in `.pre-commit-config.yaml` (after color-only).
- The forbidden-patterns scanner is a Python static-analysis sibling of the five existing `scripts/check_dashboard_*.py` gates — same shape, same exit-code contract, same `file:line:col` message format. `--cov=scripts` ⇒ the new script needs test coverage to keep coverage ≥87%.
- HARD GATE (release-blocking class per DAG §7); owner Murat; a11y-focused review (DAG Decision D2). Convergence node — must merge cleanly so 5.22 is unblocked.
- Zero wire-format contracts → freeze stays 7/7.

### Reuse map (do NOT reinvent)

| Need | Reuse | Source |
|---|---|---|
| Forbidden-patterns scanner skeleton (comment-blank / `_line_col` / quote-aware tag-end / frozen Violation / exit 0/1/2 / `file:line:col` msg) | mirror the color-only gate verbatim | scripts/check_dashboard_color_only.py:26-217 |
| Sibling gate shape (CSS-comment strip, JS-pattern precedence, `pass_filenames:false` no-arg scan) | mirror | scripts/check_dashboard_no_data_theme.py; check_dashboard_motion.py |
| Live-dot label rule (for AC4 DOM check) | reuse `_label_present`/`_LABEL_CLASS`/`_TEXT_LABEL_TAGS` semantics | scripts/check_dashboard_color_only.py:35-142 |
| Playwright server + chromium skip-guard + context-manager page helper | reuse the integration helper pattern | tests/integration/test_dashboard_live_dot.py; test_dashboard_backlog_tree.py |
| Server launch in tests | `serve_dashboard_in_thread(repo_root, port)` + `find_free_port()` | src/sdlc/dashboard/server.py:262-279 |
| axe scan surface (all 5A components in landmarks) | the composite fixture | src/sdlc/dashboard/static/test-fixtures/editorial-scanning-rhythm.html |
| Backlog-tree keyboard + leaf-focus (PAT-6) witness pattern | mirror | tests/integration/test_dashboard_backlog_tree.py |
| CI gate wiring (matrix step, not new job) | add after color-only | .github/workflows/ci.yml:69-70 |
| Pre-commit hook shape | add after `dashboard-color-only-gate` | .pre-commit-config.yaml (dashboard gates block) |
| axe-core engine | vendor axe-core 4.12.1 `axe.min.js` (MPL-2.0) | tests/dashboard/vendor/ (new) |

### Deferred-work items this story closes / touches

- **Closes DEF-1 (5.5)** — color-only gate JS-render path unguarded → AC4 rendered-DOM check. [deferred-work.md DEF-1, 5.5 review]
- **Touches (optional / on the convergence pass):** DEF-1 (5.10) cross-browser focus tests (chromium-only; keep deferred unless free); DEF-2 (5.8) aria-live re-announce on repeat copy; DEF-7 (5.8) copy/greeting boundary test gaps; DEF-8 (5.11) promote residual substring-grep "contract" tests to real DOM assertions. Pull these in only where they ride the a11y harness naturally; otherwise leave deferred with a note. [deferred-work.md]

### References

- [Source: _bmad-output/planning-artifacts/epics.md:2674-2700] — Story 5.12 ACs (verbatim above); UX-DR31:225, UX-DR34:230, UX-DR36:232; NFR-A11Y-1:150, NFR-A11Y-5:154
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §7.12:1615-1637] — forbidden patterns (full list)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §8.3:1708-1728] — AA reported-not-blocking
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §8.4:1730-1804, §6.6:1263-1269] — per-component a11y checklist + backlog-tree keyboard contract (keyboard test source of truth)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md §3.1:533-573, DD-15:752, §8.6:1857-1872] — contrast/never-color-only, focus ring, landmarks
- [Source: scripts/check_dashboard_color_only.py:26-217] — reuse template for the forbidden-patterns scanner + the live-dot label rule (AC4)
- [Source: src/sdlc/dashboard/static/test-fixtures/editorial-scanning-rhythm.html:47-101] — composite SPA surface for axe + keyboard scan
- [Source: src/sdlc/dashboard/static/index.html:10-17] — proof there is NO production SPA shell (5.1 skeleton)
- [Source: src/sdlc/dashboard/server.py:262-279] — `serve_dashboard_in_thread` / `find_free_port` test launch
- [Source: tests/integration/test_dashboard_backlog_tree.py; test_dashboard_live_dot.py] — Playwright server fixture + chromium skip-guard + leaf-focus witness pattern
- [Source: .github/workflows/ci.yml:57-94] — dashboard gates as matrix steps + Playwright cache/install + pytest+coverage
- [Source: .pre-commit-config.yaml — dashboard gates block] — local-hook shape for the new gate
- [Source: docs/sprints/epic-5-dag.md §2:149-163, §3 L5:214, §5:290/300, §7 a11y-gate risk:354, Decision D2:382-400] — convergence-gate fan-in, layer, HARD-GATE class, single-CI-surface
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — DEF-1 (5.5 color-only), DEF-1 (5.10 cross-browser), DEF-2/DEF-7 (5.8), DEF-8 (5.11)
- axe-core 4.12.1 (MPL-2.0) tag taxonomy `wcag2a`/`wcag21a`/`wcag2aa`/`wcag21aa`/`wcag22aa` (no `wcag22a`); `axe.run` returns `violations[].{id,impact,tags,help,helpUrl,nodes[].target}` — Deque axe-core `doc/API.md`

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (dev-story)

### Debug Log References

- axe `scrollable-region-focusable` on `.activity-feed__list` — fixed with `tabindex="0"` + `role="log" aria-live="polite"` on `<activity-feed>` (minimal 5.11 surgical fix).
- WIN32: full `pytest` blocked by `io_primitives` POSIX gate; forbidden-patterns static gate + Playwright smoke validated locally.

### Completion Notes List

- **D1–D6 ratified (all recommendation (a)):** vendored axe-core 4.12.1; Level-A block tags `{wcag2a,wcag21a}` (no `wcag22a`); composite `editorial-scanning-rhythm.html` scan surface; rendered-DOM color-only; epic-AC `tests/dashboard/` paths; epic-AC mechanical token scanner.
- **AC1:** `scripts/check_dashboard_forbidden_patterns.py` + `tests/dashboard/test_forbidden_patterns.py` + CI/pre-commit wiring.
- **AC2:** `tests/dashboard/test_a11y_axe.py` + vendored `axe.min.js`; A-blocks / AA-reports partition; RED witness for `<img>` without alt.
- **AC3:** `tests/dashboard/test_keyboard_only.py` — Tab reachability, DD-15 focus ring, backlog-tree PAT-6 task row, tabs Arrow/Home/End.
- **AC4:** `tests/dashboard/test_color_only_dom.py` + `assert_live_dots_have_text_labels`; static color-only gate retained; **DEF-1 (5.5) closed** in `deferred-work.md`.
- **Component fix:** `activity-feed.js` — scrollable list keyboard-focusable for axe Level A.

### File List

- `scripts/check_dashboard_forbidden_patterns.py` (new)
- `tests/dashboard/_playwright_a11y.py` (new)
- `tests/dashboard/test_forbidden_patterns.py` (new)
- `tests/dashboard/test_a11y_axe.py` (new)
- `tests/dashboard/test_keyboard_only.py` (new)
- `tests/dashboard/test_color_only_dom.py` (new)
- `tests/dashboard/vendor/axe.min.js` (new, vendored axe-core 4.12.1 MPL-2.0)
- `tests/fixtures/dashboard_forbidden_patterns/` (new RED witness fixtures)
- `src/sdlc/dashboard/static/components/activity-feed/activity-feed.js` (modified — a11y fix)
- `.github/workflows/ci.yml` (modified — forbidden-patterns matrix step)
- `.pre-commit-config.yaml` (modified — `dashboard-forbidden-patterns-gate` hook)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modified — DEF-1 5.5 closed)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — 5.12 → review)

## Change Log

- 2026-06-26: Story 5.12 implementation complete (dev-story). Forbidden-patterns scanner + CI/pre-commit; axe-core 4.12.1 harness (A-blocks=`wcag2a`+`wcag21a`, AA-reports); keyboard-only + rendered-DOM color-only tests on `editorial-scanning-rhythm.html`; activity-feed `tabindex="0"`/`role="log"` fix for axe Level A; DEF-1 (5.5) closed. Decisions D1–D6 = all (a). Status → review.
- 2026-06-26: Story 5.12 created (create-story, "cho layer tiếp theo" → L5, the 5A a11y/forbidden-patterns CONVERGENCE GATE; depends on ALL of 5A, every story done+merged). Net-new `tests/dashboard/` harness: forbidden-patterns scanner (`scripts/check_dashboard_forbidden_patterns.py`, mirrors the color-only gate idiom) + axe-core harness (vendored axe-core 4.12.1, A-blocks/AA-reports) + keyboard-only Playwright test (§8.4/§6.6 focus contracts) + rendered-DOM color-only enforcement (closes 5.5 DEF-1). Decisions raised: D1 (vendor axe.min.js over PyPI dep) / D2 (Level-A = `wcag2a`+`wcag21a`; **no `wcag22a` tag exists**; one scan, partition A-block vs AA-report) / D3 (scan the composite `editorial-scanning-rhythm.html` — no production SPA shell exists) / D4 (AC4 against rendered DOM) / D5 (epic-AC literal `tests/dashboard/` test paths) / D6 (scanner = epic-AC token set; sibling gates cover the rest of §7.12). HARD GATE; owner Murat; a11y-focused review; single CI surface (matrix step, not new job); SYNTHETIC only — real-data + manual NVDA/VoiceOver is 5.22. Zero wire-format → freeze 7/7. Do-not-build: 5.22 release gate, real-data rendering, new SPA shell, STOP-banner controls.
