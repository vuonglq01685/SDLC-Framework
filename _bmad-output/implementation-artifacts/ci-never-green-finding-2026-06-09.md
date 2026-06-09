# Findings: `main` Has Never Been Green at the CI-Matrix Tier

**Date:** 2026-06-09
**Discovered during:** Epic 3 retro action **A2** (branch-protection toggle) — the last `§7`
gate item before `bmad-create-story 4.1`.
**Severity:** HIGH — blocks the §7 "green main" precondition for Epic 4.
**Status:** Reported for Project-Lead scoping. No source/test changes made (per decision).

---

## 1. Headline

The required-status-check toggle (A2) could not be applied while the repo was private on a
free plan, so the repo was made **public** (Project-Lead authorized; pre-flight secret scan
clean — all matches are Story 1.8 Secret-Sanitizer fixtures). Setting branch protection then
required the real CI check contexts, which exposed that **every CI run on recent `main`
commits fails at the `Set up job` step in ~10 s** and has done so for at least the last several
commits (`f0a9835`, the 2026-06-08 mutation-campaign commit, and the nightly `e2e` schedule).

**Root cause of the outage:** all five workflows reference `astral-sh/setup-uv@v8`, but the
action publishes **no moving `v8` major tag** (highest moving major is `v7`; only the immutable
`v8.1.0` exists — which is exactly what the `# pin: 08807647…` comment documents). The Actions
resolver fails with `unable to find version v8` before any code runs.

**Consequence (the real finding):** because the matrix never executed, a backlog of
**pre-existing test failures across Python 3.10–3.13 was never caught by CI**. Every prior
"green main / N tests pass / ≥87% coverage" claim in the audit log was produced by **local runs
on a single interpreter** (effectively 3.12), **not** the 8-cell CI matrix. The §7 "green main"
gate (Epic 3 retro P3) was asserted, never actually true at the CI tier.

---

## 2. Root-cause chain (three layers, peeled in order)

| Layer | Symptom | Cause | Nature |
|-------|---------|-------|--------|
| 1 | All runs fail in ~10 s, private-repo Actions 403 on branch-protection API | Repo private on free plan | Plan limitation → resolved by going public |
| 2 | All cells fail at `Set up job` (~3 s), `unable to find version v8` | `astral-sh/setup-uv@v8` moving tag does not exist | **CI-config bug** → fix in [PR #4](https://github.com/vuonglq01685/SDLC-Framework/pull/4) (`@v8` → `@v8.1.0`, 11 refs) |
| 3 | After Layer-2 fix, cells run and fail on real tests | Pre-existing test failures never caught by a functioning matrix | **Multi-story remediation** (this finding) |

PR #4 is correct and necessary — it is the change that makes CI *function* and reveals Layer 3.
It is **workflow-file-only**, so all Layer-3 failures below are 100% pre-existing on `main`,
not introduced by the PR.

---

## 3. Full failure surface (observed on PR #4, run 27190304432)

All 8 `quality-gates` cells fail. The downstream gates (`mutation-tests`, `posix-adopt-ran`,
`chaos`, `benchmarks`, `parity-perf`) are `needs: quality-gates` → skipped. `Debt-Decay Budget
Gate` passes.

### 3a. Deterministic — Python 3.10 incompatibility (py3.10 ubuntu + macos)
- `ModuleNotFoundError: No module named 'tomllib'` at **collection time**.
  - `src/sdlc/config/hooks.py:19` — `import tomllib` (the inline comment even reads
    *"stdlib 3.11+; CI/pre-commit use 3.12"* — an assumption that is false: the matrix runs 3.10).
  - `tests/unit/cli/test_compat_check.py:11` — `import tomllib`.
- `tomllib` is stdlib **3.11+**. On 3.10 these modules cannot import.
- **Fix shape:** `try: import tomllib / except ModuleNotFoundError: import tomli as tomllib`,
  add `tomli; python_version < "3.11"` to deps, regenerate `uv.lock`. Small and clear.
- `release.yml` also uses `import tomllib` but in a 3.12-pinned step — **not affected**.

### 3b. Real-or-flaky batch — Python 3.11/3.12/3.13 (cells that ran 7–12 min)
These match the audit log's long-standing "≈34 pre-existing baseline failures". Triage needed:

| Test(s) | Failure | Likely class |
|---------|---------|--------------|
| `tests/benchmark/test_scan_perf.py::test_scan_perf_warm` | scan ran 116–143 ms vs 100 ms budget (NFR-PERF-1) | **Env flake** — shared-runner speed variance |
| `tests/unit/cli/test_logs_poll.py` ×2 (`*_rotation_detected`) | `assert 8188325 != 8188325` — "new file should have a different inode" | **FS flake** — inode reuse on CI fs |
| `tests/integration/test_no_color_every_command.py` ×2 (`[--help]`) | ANSI escapes present despite `--no-color` / `NO_COLOR=1` | **CLI render in CI** — Rich/Click terminal detection |
| `tests/unit/cli/test_replan_command.py::test_replan_command_registered` | `--scope` not found in `--help` output | Same render family, or real registration gap |
| `tests/e2e/cli/test_walking_skeleton_goldens.py::test_walking_skeleton_goldens` | GOLDEN MISMATCH on `03_status.stdout` | Golden drift — needs inspection |
| `tests/property/test_journal_append_only.py` ×3 | `pydantic ValidationError for JournalEntry` | **Possibly real** — investigate first |

> The list is the observed set from the ubuntu 3.11/3.12 cells; per-cell subsets may vary
> (esp. the speed/inode flakes). Not asserted exhaustive per cell.

---

## 4. Why CI never caught this (process gap)

- The `setup-uv@v8` reference made the matrix non-functional, so **no run ever reached the test
  step** on recent commits — a silent red that *looked* like infra/billing noise.
- Local verification used one interpreter; the **3.10 cell never ran anywhere**, so a 3.10-only
  `import` bug shipped through Epics 1–3.
- The Epic 3 retro recorded P3 "green main … green" — true locally, false at the CI tier. The
  retro/discipline machinery trusted a CI signal that was never actually flowing.

---

## 5. What is already done (no re-work needed)

- ✅ **A2 toggle complete** — repo public; `main` branch protection set with all **10** required
  status checks (8 `quality-gates` cells + `Adopt mutation testing (Story 3.7 AC2)` +
  `POSIX adopt suite actually-ran gate (Epic 3 retro A2)`), `enforce_admins=false`,
  `strict=false`. (Note: ADR-006's illustrative `gh api` command lists job-ids
  `mutation-tests`/`posix-adopt-ran`; the real check **contexts** are the job `name:` values —
  ADR-006 example should be corrected to match.)
- ✅ Sprint-planning refresh — `epic-3: in-progress → done` (8/8 stories + retro done).
- ✅ [PR #4](https://github.com/vuonglq01685/SDLC-Framework/pull/4) — `setup-uv` `@v8 → @v8.1.0`
  (Layer-2 fix). Open; **cannot auto-merge** because the 10 required checks are red (by design).

---

## 6. Recommendation (for Project-Lead scoping)

1. **Treat "CI never green" as a blocking prep-effort before `create-story 4.1`** — `§7` "green
   main" is not yet satisfiable; this is remediation, not a toggle. Do **not** start Epic 4 under
   an "I'll backfill later" rationale (CLAUDE.md / CONTRIBUTING §7).
2. **Sequence the remediation:**
   - (a) Land PR #4 first (makes CI real). Decide merge path — admin-merge to surface red on
     `main` honestly, vs. hold until the suite is green.
   - (b) Fix the deterministic **3.10 `tomllib`** bug (small, own PR/story).
   - (c) Triage the 3.11+ batch: confirm flakes (perf/inode/no-color) vs. real (JournalEntry
     `ValidationError`, golden, replan `--scope`); stabilize or quarantine-with-ticket per the
     existing debt taxonomy.
3. **Process / docs follow-ups:**
   - Correct ADR-006's required-check example to use the real `name:` contexts (not job-ids).
   - Note in ADR-006 that a moving-major action tag can vanish; consider SHA-pinning `setup-uv`
     per the "future supply-chain hardening" direction already stated there.
   - Carry a retro line: "P3 green-main was local-only; CI matrix was non-functional" — and add
     a guard so a never-started / all-failed-at-setup CI run is not read as green.
   - Open debt items for the confirmed-real Layer-3 failures.

---

## 7. Evidence pointers

- Failing run: `27190304432` (PR #4). Layer-2 annotation:
  `Unable to resolve action 'astral-sh/setup-uv@v8', unable to find version 'v8'`.
- Pin SHA `08807647…` → tag `v8.1.0` (commit 2026-04-16) on `astral-sh/setup-uv`.
- 3.10 trace: `src/sdlc/config/hooks.py:19` / `tests/unit/cli/test_compat_check.py:11`.
