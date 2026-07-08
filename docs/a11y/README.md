# Accessibility — Per-Release Minimum & Regression Policy

**Story:** 5.22 (Per-Release a11y Testing Minimum) · **DD-19** · **NFR-A11Y-1**

This page codifies the dashboard's per-release accessibility minimum and what happens when a
regression is found. It does not re-define any per-component contract — those live in
`ux-design-specification.md` §8.3–§8.5 and are enforced by the tests listed below.

## 1. What already runs automatically (every PR)

The axe-core scan and the keyboard-only smoke test are **not new in this story** — they have run
on every dashboard PR since Story 5.12:

| Gate | Test | CI job |
|---|---|---|
| axe-core, Level A blocking / Level AA reported | `tests/dashboard/test_a11y_axe.py` (composite) + `tests/dashboard/test_release_a11y_surface.py` (full terminal surface, Story 5.22 D1) | `quality-gates` (`uv run pytest`, `.github/workflows/ci.yml:96-97`) and the release `qa` job (ADR-008) |
| Keyboard-only smoke | `tests/dashboard/test_keyboard_only.py` | same as above |

Both are marked `integration` and Playwright-gated (skip cleanly when Chromium is absent); CI
installs Chromium (`ci.yml:85-88`) so they run for real on every PR and on every release.
**A red result here already blocks the PR / release mechanically** — there is nothing extra to
wire for "the release is blocked" (AC3); it is enforced today.

## 2. The per-release minimum (DD-19)

On top of the automated gate above, every release additionally requires:

1. **The full-surface axe report**, generated via `uv run python scripts/generate_a11y_report.py`
   (Story 5.22 D2) and pasted into `docs/a11y/release-<version>.md` (copy from
   [`release-template.md`](release-template.md)).
2. **A 5-minute NVDA smoke** (Windows/Firefox) and **a 5-minute VoiceOver smoke**
   (macOS/Safari) — human execution, signed off by a designated reviewer.
3. **A 5-minute keyboard-only smoke** — human execution (automated coverage already exists via
   `test_keyboard_only.py`; this is the release-time human confirmation).
4. **A color-vision spot-check** (DevTools emulation) — optional per release.
5. **A designated-reviewer signoff**, recorded in the same `release-<version>.md`.

See `release-template.md` for the fill-in form covering all five.

## 3. Regression → block → ticket → §8.4 (D4)

When a Level-A regression is found — by the automated scan, a manual smoke test, or a
color-vision spot-check:

1. **The release is blocked** — mechanically, because the Level-A axe gate (§1) already reds
   `quality-gates` on every PR and the release `qa` job. There is no separate "block" step to
   perform; a red gate cannot merge/tag.
2. **File a bug ticket** per CONTRIBUTING §8: label `kind:bug`, cite the failing axe rule (or the
   manual-smoke step) plus a reproducer, and name the violated NFR/ADR
   (`NFR-A11Y-1`, `ux-design-specification.md` §8.3).
3. **Consult the §8.4 per-component checklist** (embedded in `release-template.md` §5) to
   identify which component owns the failing behavior — the checklist is written as a Level-A
   sign-off form, one section per component, so the failing line points directly at the fix.
4. Fix the regression, re-run `scripts/generate_a11y_report.py`, and re-attach the updated report
   to the release record before the release proceeds.

## 4. What this page does NOT own

- **Per-component a11y implementation** — owned by each component's story (5.6–5.21) and
  enforced by the per-component witnesses (`test_stop_banner_a11y.py`,
  `test_connection_state_a11y.py`, `test_viewport_banner_a11y.py`, etc.).
- **Level AA enforcement** — AA is reported, not blocking (UX §8.3); this story does not change
  that.
- **Lighthouse / pa11y** — nice-to-have, per-release only, not gated (UX §8.5).
- **Screen-reader automation** — NVDA/VoiceOver remain a human per-release smoke test.

See also: CONTRIBUTING.md §1 (quality gate) and §8 (bug-ticket process) — CONTRIBUTING.md lives
at the repo root, outside the published docs site, so it is cited by section number here rather
than linked.
