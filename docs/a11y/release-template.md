# Per-Release Accessibility Signoff — release-\<version\>

**Story:** 5.22 (Per-Release a11y Testing Minimum) · **Applies to:** every tagged release (`v*.*.*`, `.github/workflows/release.yml`)

Copy this file to `docs/a11y/release-<version>.md` when preparing a release and fill in every
section below. It is the single per-release record combining the automated axe report, the
manual screen-reader + keyboard smoke tests, and the designated reviewer's signoff (D3).

> Do not fabricate an instance of this file for a version that has not shipped. The first
> concrete `release-<version>.md` is produced when the first tag (`v0.1.0` or later) is cut.

---

## 1. Automated axe-core report

Generate with `uv run python scripts/generate_a11y_report.py --date <YYYY-MM-DD> --out release-a11y.tmp`
(Story 5.22 Task 2 / D2), then paste the **contents of `release-a11y.tmp`** below verbatim. Use
`--out` (not a stdout redirect): the nested keyboard-suite run prints its own pytest progress to
stdout, which `--out` keeps out of the byte-clean report body. The `A11Y-REPORT-STATUS: PASS` line
is the machine-checkable release gate: a `FAIL` means the release is blocked (AC3) until the
underlying Level-A violation or keyboard-suite failure is fixed and the report is regenerated
(exit 2 = the scan could not run — Playwright/Chromium missing — not an a11y verdict).

```text
<paste the contents of the --out file from `scripts/generate_a11y_report.py` here>
```

## 2. Manual screen-reader smoke test (NVDA + VoiceOver, ~5 min each)

Per UX §8.5: land on the dashboard, scan the masthead, read the resume card, expand a tree node,
dismiss a STOP banner via its action button. Run once per screen reader / browser combination.

| Screen reader | Browser | Tester | Date | Result |
|---|---|---|---|---|
| NVDA | Firefox | | | ☐ Pass ☐ Fail |
| VoiceOver | Safari | | | ☐ Pass ☐ Fail |

Smoke steps (both combinations):

1. Land on the dashboard — confirm the **masthead** (`role="banner"`, `<h1>`) is announced first.
2. Scan the **KPI strip** — confirm each cell's label + value are read together.
3. Read the **resume card** — confirm the breadcrumb, suggested command, and copy button are
   announced with accessible names.
4. Navigate to the **phase tracker** — confirm each phase cell's state is read in plain language.
5. Expand a **backlog tree** node — confirm `aria-expanded` state changes are announced.
6. Dismiss a **STOP banner** via its action button — confirm the severity ("CRITICAL:" /
   "WARNING:" / "INFO:") is read, not just a color/icon.
7. Confirm the **activity feed** announces new entries with their outcome as text.

If any step fails: note the failing surface + screen reader below, then follow §3 of
`docs/a11y/README.md` (regression → block → ticket → §8.4).

**Findings (if any):**

<!-- one row per finding -->

## 3. Manual keyboard-only smoke test (~5 min)

Per UX §8.5 — using **only the keyboard** (no mouse / trackpad):

1. Reach the resume card via **Tab**; copy the suggested command via **Enter** on the copy
   button.
2. Reach the backlog tree; navigate **Down** 5 rows, **Right-arrow** to expand, **Down** into
   children, **Left-arrow** to collapse, **Up** to return to the start.
3. Reach the tabs; **Arrow-Right** to switch tabs.
4. Confirm focus is **visibly indicated** (DD-15 focus ring) at every step above.

| Tester | Date | Result |
|---|---|---|
| | | ☐ Pass ☐ Fail |

Automated coverage: `tests/dashboard/test_keyboard_only.py` (Story 5.12) already gates this in
CI on every PR — this manual pass is the release-time human confirmation, not a replacement.

## 4. Color-vision spot-check (DevTools, optional per-release)

Emulate deuteranopia / protanopia / tritanopia (Chrome/Firefox DevTools) and spot-check the
phase cells, KPI deltas, and STOP banners. §3.1's color-only-signaling rule (every state also
carries a text label) means this should never surface a NEW finding — it's a confirmation pass.

| Tester | Date | Result |
|---|---|---|
| | | ☐ Pass ☐ Fail |

## 5. §8.4 Per-Component Accessibility Checklist (Level-A sign-off form)

AC3: when any smoke test or the automated scan fails, consult this checklist to identify the
failing component. Verbatim from `ux-design-specification.md` §8.4 — check every applicable
line for the component(s) implicated by a finding above.

**Masthead**

- [ ] `role="banner"` on container.
- [ ] `<h1>` carries the accessible name; project name + phase are concatenated for screen readers.
- [ ] Live region (`aria-live="polite"`) on the right rail; rate-limited to 60 s between announcements.
- [ ] Live-dot is decorative (`aria-hidden="true"`); its semantic state is conveyed by the adjacent text label.
- [ ] Disconnection state: live region announces the change exactly once when entering / exiting disconnected state.

**KPI Strip + KPI Cell**

- [ ] `role="region"` `aria-label="Project KPIs"` on the strip container.
- [ ] Each cell uses semantic `<dl>`/`<dt>`/`<dd>` or `aria-labelledby` linking label and value.
- [ ] No-data state: `n/a` is real text, not a glyph; the reason is in `aria-describedby`.
- [ ] Stale state: the freshness footer is screen-reader-readable.

**Resume Card**

- [ ] `role="region"` `aria-label="Resume position and suggested command"`.
- [ ] Breadcrumb is plain text; slash separators are real `/` characters (not glyphs).
- [ ] Command surface: `<code>` element wrapped in a focusable group with `aria-label="Suggested command, click button to copy"`.
- [ ] Copy button: `<button>` with `aria-label="Copy suggested command"`.
- [ ] Live region (`aria-live="polite"`) wraps breadcrumb + command for poll-update announcements.
- [ ] Disabled state: `aria-disabled="true"` on the copy button when the card is in disconnected state.

**Phase Tracker + Phase Cell**

- [ ] `role="region"` `aria-label="Phase tracker"`.
- [ ] Each cell has `role="status"`; `aria-label` summarizes the cell's state in plain language.
- [ ] Color is never the only signal — every state has a glyph + text label.
- [ ] Glyphs are inline SVGs with `<title>` elements or `aria-label`.

**Backlog Tree**

- [ ] `role="tree"` on root container.
- [ ] Each row: `role="treeitem"`, correct `aria-expanded`, `aria-level`, `aria-setsize`, `aria-posinset`.
- [ ] `aria-current="true"` on the row matching the resume card's current task.
- [ ] Full keyboard contract (Arrow keys, Enter, Home/End).
- [ ] Focus-visible ring (DD-15) is rendered on the focused row, not just hovered ones.

**STOP Banner**

- [ ] `role="alert"` (assertive) for `crit` severity; `role="status"` (polite) for `info` and `warn`.
- [ ] Each alert has unique `aria-labelledby` referencing its title.
- [ ] Severity tag in title (e.g., "CRITICAL: …") makes the severity readable without color.
- [ ] Action buttons are `<button>` elements with explicit text; no icon-only buttons.

**Tabs**

- [ ] `role="tablist"`, `role="tab"`, `role="tabpanel"` correctly assigned.
- [ ] `aria-selected` reflects active tab.
- [ ] Arrow-key navigation between tabs.
- [ ] Focus moves with selection (automatic activation).

**Activity Feed**

- [ ] `role="log"` `aria-live="polite"` on the feed container.
- [ ] New entries are announced in order of arrival, rate-limited to one announcement per poll.
- [ ] Each row's outcome is announced as text (e.g., "approved", "rejected", "error"), not just the glyph.

**Copy Button**

- [ ] `<button>` element, not a `<div>` or `<span>`.
- [ ] `aria-label="Copy command"` (or component-specific equivalent).
- [ ] On copy, the button optionally announces "Copied" via `aria-live="assertive"` once.
- [ ] Disabled state: `aria-disabled="true"` + visual `--ink-dim` treatment.

**Disconnected State**

- [ ] When entering disconnected state, the page-wide announcement is made via the masthead live region.
- [ ] The disconnection banner is `role="alert"`.
- [ ] Disabled controls (copy button, etc.) carry `aria-disabled="true"`.

## 6. Designated reviewer signoff

| Field | Value |
|---|---|
| Reviewer | |
| Date | |
| Result | ☐ Approved — release may proceed ☐ Blocked — see findings above |
| Notes | |

Signoff here is the human confirmation gate for AC2/AC3. It does not replace the automated
Level-A axe gate (§1), which already blocks `quality-gates` (every PR) and the release `qa` job
mechanically regardless of this signoff — see `docs/a11y/README.md`.
