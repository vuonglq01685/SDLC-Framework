# Story 5.1: Dashboard Server Skeleton + Micro-Router + Read-Only Routes + ETag/304 + Localhost-Bind

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- Layer: Epic-5 DAG L1 (zero-indegree root, mutually independent of 5.2). Worktree: epic-5/5-1-dashboard-server-skeleton. SECURITY-SENSITIVE → review-B + security-reviewer. Freeze the server/route contract before 5.13. -->

## Story

As a user launching the dashboard,
I want `sdlc dashboard --port <N>` running a tiny HTTP server (micro-router, no framework) bound to localhost only, exposing `/state.json` and `/api/dora` as read-only GETs with ETag/304 polling support and serving the SPA static files,
so that the dashboard surface is shippable from Epic 1 with synthetic data and the security boundary (localhost-only, no auth, no write endpoints) is encoded from day one (FR41, FR46, NFR-PERF-3, NFR-PERF-4, NFR-SEC-6).

## Acceptance Criteria

> Copied verbatim from `_bmad-output/planning-artifacts/epics.md` (Epic 5, Story 5.1). The two Host-header / static-path-containment AC blocks were added per Epic-5 DAG rev-2 architectural review (Winston F5).

**AC1 — Localhost bind + trusted-local threat model**
- **Given** the framework installed **When** I run `sdlc dashboard --port 8765` **Then** an HTTP server starts and binds to `127.0.0.1:8765` (NOT `0.0.0.0`)
- **And** binding to `0.0.0.0` is blocked at startup with `SecurityError("dashboard must bind localhost only; remote access not supported in v1")`
- **And** the server's documented threat model assumes the local user is trusted (no auth required by design)

**AC2 — `/state.json` streamed-as-is + ETag/304 + <100 ms**
- **Given** the server running **When** I `GET /state.json` **Then** the response streams the file as-is from disk (no parsing on the server) per Decision E1
- **And** `ETag` header is set to the file's content hash; subsequent requests with matching `If-None-Match` return `304 Not Modified`
- **And** response time is < 100 ms (NFR-PERF-3) — benchmarked via `pytest-benchmark`

**AC3 — `/api/dora` route registered (synthetic) + 30 s server-side cache**
- **Given** the server running **When** I `GET /api/dora` **Then** the route is registered and returns synthetic data (real implementation in Story 5.13)
- **And** the response is cached server-side for 30 seconds (NFR-PERF-5)

**AC4 — Write methods → 405, no write endpoints**
- **Given** any attempt to invoke a write method (`POST`, `PUT`, `DELETE`, `PATCH`) **When** the server processes the request **Then** the response is `405 Method Not Allowed`
- **And** v1 explicitly exposes no write endpoints (FR46)

**AC5 — Host-header localhost allowlist → 403 (DNS-rebinding defense)**
- **Given** the server running and any request arriving **When** the request's `Host` header is not in the localhost allowlist (`localhost`, `127.0.0.1`, `[::1]`, with or without the bound port) **Then** the response is `403 Forbidden`
- **And** this defeats DNS-rebinding / cross-origin reads: a localhost bind alone does not stop a malicious web page in the user's browser from reaching the server via a rebound hostname, and the dashboard is a read-exfiltration surface (project structure, story ids, agent activity) so `405`-on-write does not cover it (NFR-SEC-6)

**AC6 — Static-path containment under the static root → 404**
- **Given** a `GET` for a static asset under the SPA static root **When** the canonicalized resolved path escapes the static root — via `..`, an absolute path, or a symlink pointing outside the root **Then** the response is `404 Not Found` and no file outside the static root is ever served
- **And** the path-containment check reuses the repo-containment helper from Epic-4 retro D1 (CR4.12-W1) — `concurrency/path_guard.py` — rather than hand-rolling a second implementation. **See Decision D1: the helper contains under *repo root*; AC6 demands containment under the *static root* — this gap MUST be closed (compose or generalize), not papered over.**

## Tasks / Subtasks

> TDD-first per CONTRIBUTING §2 (this story adds CLI surface `sdlc dashboard`). The security ACs (bind address, 405, 403-Host, 404-traversal, ETag/304) are all cleanly testable RED-first — write those tests first. `test-along` is permitted **only** for the micro-router internals (novel substrate) with justification in the PR body; the AC-level contract tests are tests-first. First commit on the branch MUST be the failing test file(s).

- [x] **Task 0 — Resolve Decision D1 (static-root containment) before coding** (AC: 6)
  - [x] Raise D1 (see Dev Notes → Decisions) and record the selection in the PR Change Log per CONTRIBUTING §5. Do not start AC6 until D1 is chosen.

- [x] **Task 1 — Package skeleton + module boundary** (AC: 1–6)
  - [x] Create `src/sdlc/dashboard/__init__.py`, `server.py`, `router.py`, `etag.py`, `routes/__init__.py`, `routes/state.py`, `routes/dora.py` (architecture §"Module Specification" layout)
  - [x] Confirm the existing `dashboard` entry in `scripts/module_boundary_table.py:142` already permits `dashboard → {errors, state, journal, telemetry, signoff, config}` and forbids `engine/dispatcher/runtime/hooks/adopt → dashboard`. Run `python scripts/check_module_boundaries.py` and ensure the new package passes the one-way edge + 400-LOC cap. If `server.py` legitimately exceeds 400 LOC, add a `LOC_EXEMPT` entry with a debt id (`EPIC-5-DEBT-DASHBOARD-SERVER-SPLIT`) — but prefer splitting routes out first.

- [x] **Task 2 — Micro-router** (AC: 2–6) — *novel substrate, test-along OK with PR justification*
  - [x] `router.py`: decorator-style route registration (~30 LOC per Decision E1); dispatch by method + path; default `405` for write methods (AC4) and `404` for unknown GET paths
  - [x] Keep `server.py` under the 400-LOC cap by living the routing table in `router.py` + `routes/*.py`

- [x] **Task 3 — Localhost bind + SecurityError** (AC: 1)
  - [x] RED: test asserts bind address is `127.0.0.1` and that requesting `0.0.0.0` raises `SecurityError` with the exact message string
  - [x] GREEN: bind via stdlib `http.server.HTTPServer`/`ThreadingHTTPServer`; reuse `from sdlc.errors import SecurityError` (do NOT define a new error class); document the trusted-local-user threat model in the module docstring + `docs/`

- [x] **Task 4 — CLI command `sdlc dashboard --port <N>`** (AC: 1)
  - [x] Add `src/sdlc/cli/dashboard.py` exposing `run_dashboard(*, ctx, port)`; register a single `@app.command(name="dashboard")` in `cli/main.py` (inline pattern, mirroring `status_command` at `cli/main.py:207`), body uses a **deferred import** of `run_dashboard` (cold-start budget, architecture §488)
  - [x] `--port` option with a sane default; emit a friendly "serving on http://127.0.0.1:<port>" line

- [x] **Task 5 — `/state.json` route: stream-as-is + ETag/304** (AC: 2)
  - [x] Resolve `.claude/state/state.json` via `get_repo_root_or_cwd()` + `_STATE_PATH_REL` (`cli/_paths.py:17`, `cli/status.py:23`); **stream raw bytes** (`Path.read_bytes()` / chunked) — no `read_state()` parse on the hot path (Decision E1 + NFR-PERF-3)
  - [x] ETag = content hash. Reuse the sha256-over-content approach from `signoff/hasher.py::compute_artifact_hash(path, *, repo_root)` (returns `"sha256:<hex>"`) — NOT mtime/inode (DAG §5 5.1 note). See Decision D2 on import-vs-wrap
  - [x] `If-None-Match` matching ETag → `304 Not Modified` (empty body); missing file → `404` (or `200` with `{}` — choose and test)
  - [x] RED tests: ETag present, 304 on match, 200 + new ETag on change

- [x] **Task 6 — `/api/dora` synthetic route + 30 s in-memory cache** (AC: 3)
  - [x] Return a synthetic DORA envelope (real compute is Story 5.13); cache the response in-memory with a 30 s TTL (Decision E4 — **in-memory, not a file**; avoids `io_primitives` and keeps the server cross-platform). Freeze nothing here — schema is internal (DAG Decision D1 = internal/documentary, freeze stays 7/7)

- [x] **Task 7 — Write-method guard → 405** (AC: 4)
  - [x] RED: `POST/PUT/DELETE/PATCH` to any path → `405`; assert no write endpoints exist

- [x] **Task 8 — Host-header allowlist → 403** (AC: 5)
  - [x] RED: requests whose `Host` is not in `{localhost, 127.0.0.1, [::1]}` (± `:<port>`) → `403`; in-allowlist → pass. Apply the check to ALL requests (reads included), before routing

- [x] **Task 9 — Static serving + path-containment → 404** (AC: 6)
  - [x] Serve `src/sdlc/dashboard/static/**` (index.html + assets) with appropriate content-types + long-cache headers for immutable assets
  - [x] Per the D1 selection: canonicalize the requested path and reject `..` / absolute / symlink-escape outside the **static root** → `404`. RED tests for each escape vector (`..`, absolute, symlink)

- [x] **Task 10 — Performance benchmark gate** (AC: 2)
  - [x] `tests/dashboard/test_dashboard_response.py` (or `tests/unit/dashboard/`) using `pytest-benchmark` asserts `/state.json` p50 < 100 ms (NFR-PERF-3). Mark `@pytest.mark.benchmark`

- [x] **Task 11 — Docs + threat model**
  - [x] Document the localhost-only / no-auth security boundary and the trusted-local-user assumption (NFR-SEC-6) in module docstrings and a short `docs/` note; ensure `mkdocs build --strict` stays green

## Dev Notes

### Architecture compliance (read before coding)

- **STDLIB http.server — NOT FastAPI, NOT a framework.** `architecture.md` has a stale template line in `technicalConstraintsBaseline` reading *"FastAPI + HTMX"* — this is **superseded** by the authoritative Decision E1 and `architecture.md:157`: *"stdlib `http.server` + single-page HTML + vanilla JS + Chart.js (vendored). No npm, no webpack, no React, no build step."* Use stdlib only. Story 5.4 stands up a no-third-party-UI-framework CI guard that will fail if a framework sneaks in. [Source: architecture.md#technicalConstraintsBaseline (stale), architecture.md:157, architecture.md Decision E1]
- **Micro-router (~30 LOC), decorator-style, routes in `dashboard/routes/*.py`** — keeps `server.py` under the 400-LOC cap; no external deps. [Source: architecture.md Decision E1]
- **Module layout** (architecture §"Module Specification"): `src/sdlc/dashboard/{server.py, router.py, etag.py, routes/state.py, routes/dora.py, static/}`. 5.1 builds the skeleton + `state` + `dora` routes only. The fuller route set (`stops/activity/resume/signoffs/kanban/healthz`) belongs to later stories — **out of scope here** (see Scope boundary). [Source: architecture.md#Module Specification (dashboard/)]
- **One-way module edge (binding):** `dashboard` MAY read `state`/`journal` (and `errors/telemetry/signoff/config`); `state`/`journal`/`engine`/`dispatcher`/`runtime`/`hooks`/`adopt` MUST NOT import `dashboard`. Already encoded — `scripts/module_boundary_table.py:142` (`dashboard` ModuleSpec) and `:116` (engine `forbidden_from` includes `dashboard`). `/api/dora` and any derived view read *through the reader seam, never by re-parsing wire files*. [Source: architecture.md:1070,1108; module_boundary_table.py:142,116]
- **Decision E2 — polling:** 3-second SPA polling with `ETag` + `304` on the `state.json` hash. [Source: architecture.md Decision E2]
- **Decision E4 — DORA:** on-demand compute with a 30-second in-memory cache. For 5.1 the route is a synthetic stub; keep the cache in-memory. [Source: architecture.md Decision E4]

### Reuse map — DO NOT reinvent (all symbols source-verified)

| Need | Reuse this | Path:line | Signature / note |
|---|---|---|---|
| 0.0.0.0-bind error | `SecurityError` | `src/sdlc/errors/base.py:105` | `class SecurityError(SdlcError)` — import it; do not define a new class |
| Static-path containment | `assert_repo_contained` | `src/sdlc/concurrency/path_guard.py:38` | `(path: Path, repo_root: Path) -> Path`; rejects `..`/absolute/symlink-escape; raises `SecurityError`. **Repo-root scoped — see D1.** ADR-037. |
| ETag content hash | `compute_artifact_hash` | `src/sdlc/signoff/hasher.py:25` | `(path: Path, *, repo_root: Path) -> str` → `"sha256:<hex>"` (chunked sha256 of file bytes). See D2. |
| Repo root resolution | `get_repo_root_or_cwd` | `src/sdlc/cli/_paths.py:17` | `() -> Path` (git toplevel, 5 s timeout) |
| state.json on-disk path | `_STATE_PATH_REL` | `src/sdlc/cli/status.py:23` | `".claude/state/state.json"` (resolve under repo root) |
| CLI command shape | `status_command` | `src/sdlc/cli/main.py:207` | `@app.command(name=...)` + deferred body import |
| Perf benchmark | `pytest-benchmark` | `pyproject.toml:32` | already a dep (`>=5,<6`); `benchmark` marker registered at `:271` |

There is **no existing HTTP server / socket code** in `src/sdlc/` — the server is genuinely net-new, but every *security/util primitive* above already exists and MUST be reused. [Source: research subagent A, source-verified 2026-06-23]

### Decisions (resolve per CONTRIBUTING §5 — record the pick in the PR Change Log)

**D1 — Static-root containment (AC6). The reused helper is repo-root-scoped; AC6 demands static-root-scoped containment.** `assert_repo_contained(path, repo_root)` only proves the path stays under the *repo* root. Static files live at `src/sdlc/dashboard/static/`, a repo subdirectory, so a crafted `GET /../../cli/main.py` could resolve *inside* the repo yet *outside* the static root — passing repo-containment but violating AC6 ("no file outside the static root is ever served").
- **D1 (option 1) — Compose:** call `assert_repo_contained(candidate, repo_root)` then additionally assert `safe_path.is_relative_to(static_root)`; 404 on either failure. *Pro:* zero change to the frozen ADR-037 helper; smallest blast radius. *Con:* two-step, static-root check lives in dashboard code.
- **D2 (option 2) — Generalize the helper:** extract `assert_contained(root: Path, path: Path) -> Path` in `path_guard.py` and make `assert_repo_contained` a thin caller (`root=repo_root`); dashboard calls `assert_contained(static_root, candidate)`. *Pro:* single canonical containment primitive, semantically exact. *Con:* edits a security module under ADR-037 → pairs with an ADR-037 amendment note + security-reviewer sign-off.
- **D3 (option 3) — Defer:** ship repo-root containment only, debt-register the static-root gap. *Pro:* fastest. *Con:* **AC6 is unmet and this is a read-exfiltration surface — NOT acceptable for a security-sensitive story.**
- **Reviewer recommendation:** **D2** — AC6 is a security AC on the project's first HTTP server; a single, semantically-exact containment primitive is worth the ADR-037 amendment. D1 is acceptable if the team wants to keep `path_guard.py` byte-frozen this story. **Reject D3.**

**D2 (ETag source) — import `compute_artifact_hash` vs. local `etag.py` helper.** Architecture prescribes a `dashboard/etag.py`. `dashboard → signoff` is an allowed edge, so importing `compute_artifact_hash` is legal. *Recommendation:* `etag.py` wraps `compute_artifact_hash` (single hashing implementation, ETag-formatting lives in dashboard). Note `compute_artifact_hash` requires `repo_root` and runs a symlink-escape check (raises on escape) — pass `repo_root` and let escape → 404.

### Security model (NFR-SEC-6) — this is the keystone

- Bind `127.0.0.1` only; `0.0.0.0` → `SecurityError` at startup (AC1). Threat model: **local user trusted, no auth by design** — document it explicitly.
- **Host-header allowlist (AC5)** is NOT redundant with the localhost bind: a malicious page in the user's browser can DNS-rebind to reach a localhost-bound server. The dashboard leaks project structure / story ids / agent activity, so 405-on-write does not cover read exfiltration. Validate `Host ∈ {localhost,127.0.0.1,[::1]}(±:port)` on **every** request before routing. (Architecture.md does **not** specify AC5/AC1-error/AC4 mechanics — they are net-new from the epic ACs, added per DAG rev-2 Winston F5; implement to the epic, not to a gap in the architecture.) [Source: architecture.md gaps noted by research subagent B; epics.md Story 5.1 ACs]
- `405` on `POST/PUT/DELETE/PATCH` (AC4); no write endpoints (FR46).

### Performance

- `/state.json` streamed as-is, **no server-side parse** on the hot path → < 100 ms (NFR-PERF-3), gated by `pytest-benchmark`. [Source: architecture.md NFR-PERF-3]
- Only-changed-section re-render is a *frontend* concern (NFR-PERF-4) and lands in later component stories — not 5.1.
- `/api/dora` 30 s cache (NFR-PERF-5). [Source: architecture.md NFR-PERF-5, Decision E4]

### Cross-platform (Windows dev hosts can run these tests)

`src/sdlc/concurrency/io_primitives.py` raises `ImportError` on win32 (`io_primitives.py:19`). The dashboard server is **read-only** and needs no atomic writes — **do NOT import `io_primitives`**. Stream via `Path.read_bytes()` and keep the DORA cache in-memory (Decision E4). Keeping the server import-clean of `io_primitives` lets the full server test suite run on Windows dev hosts (the project's primary dev platform), avoiding the recurring "asserted-not-measured on win32" trap from the Epic-4 retro. If any test path unavoidably pulls a POSIX-only import, guard it with `@pytest.mark.skipif(sys.platform == "win32", ...)` (existing pattern). [Source: research subagent A]

### Scope boundary (prevent scope creep)

**In scope (5.1):** server skeleton (`server.py` + `router.py` + `etag.py`), `routes/state.py`, `routes/dora.py` (synthetic stub), static serving, and the five security/perf controls (AC1–AC6). **Out of scope:** real DORA compute (5.13), `/api/stops` (5.19), `/api/activity` (5.16), `/api/resume` (5.18), `/api/signoffs` (5.14), `/api/kanban`, design tokens/CSS (5.2), and frontend components. The architecture's fuller route list is the eventual target, not this story. **Freeze the server/route contract (method+path+ETag+status-code semantics) at review — 5.13 depends on it.**

### Project Structure Notes

- New package `src/sdlc/dashboard/`; static assets at `src/sdlc/dashboard/static/` (shipped via the wheel — architecture references ADR-005 `package_data` for `dashboard/`). The epic AC writes paths as `dashboard/static/...` (package-relative shorthand). [Source: architecture.md:276 (ADR-005 package_data), Module Specification]
- Tests under `tests/dashboard/` and/or `tests/unit/dashboard/` + `tests/unit/cli/test_dashboard.py`. Reuse `tests/unit/cli/conftest.py` factories (`make_ctx`, project bootstrap). [Source: research subagent A]
- Quality gate (CONTRIBUTING §1) must stay green: ruff format/check, mypy --strict, pytest, coverage ≥ 87%, pre-commit, mkdocs --strict, wire-format snapshots (this story adds **zero** wire-format contracts — `/api/dora` schema is internal per DAG Decision D1, freeze stays 7/7).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.1] — ACs (verbatim above)
- [Source: docs/sprints/epic-5-dag.md#5. Worktree Assignments] — 5.1 row (security ACs, benchmark-at-L1, freeze-before-5.13)
- [Source: docs/sprints/epic-5-dag.md#Decision D1] — `/api/dora` internal schema, freeze stays 7/7
- [Source: _bmad-output/planning-artifacts/architecture.md] — Decisions E1/E2/E4; Module Specification (dashboard/); NFR-PERF-3/4/5; NFR-SEC-6; module boundary §1070/§1108
- [Source: _bmad-output/planning-artifacts/prd.md] — FR41, FR46, NFR-SEC-6 (localhost-only, no-auth threat model)
- [Source: docs/decisions/ADR-037-repo-containment-guard-clarification-signoff.md] — `assert_repo_contained` containment guard (D1 reuse)
- [Source: src/sdlc/errors/base.py:105] · [src/sdlc/concurrency/path_guard.py:38] · [src/sdlc/signoff/hasher.py:25] · [src/sdlc/cli/_paths.py:17] · [src/sdlc/cli/status.py:23] · [src/sdlc/cli/main.py:207] · [scripts/module_boundary_table.py:142] · [pyproject.toml:32]

## Dev Agent Record

### Agent Model Used

claude-4.6-sonnet-medium-thinking (Cursor)

### Debug Log References

- D1 resolved as **D2**: generalized `assert_contained(path, root)` in `path_guard.py`; `assert_repo_contained` is now a thin alias. Added `concurrency` to `dashboard` `depends_on` in `module_boundary_table.py`.
- Missing `state.json` → **404** (not empty `{}`).
- IPv6 `Host` headers parsed via bracket notation (`[::1]:port`).

### Completion Notes List

- Implemented stdlib `ThreadingHTTPServer` dashboard at `src/sdlc/dashboard/` with micro-router, `/state.json` (stream-as-is + ETag/304), `/api/dora` (synthetic + 30s cache), static SPA skeleton, and security controls (localhost bind, Host allowlist, 405-on-write, static-root containment).
- CLI: `sdlc dashboard --port <N>` via deferred import in `cli/main.py`.
- Tests: 33 passed + 1 skipped (symlink on win32) + benchmark median < 100ms locally.
- Docs: SDLC-THREAT-006 added to `docs/threat-model.md`.

### File List

- `src/sdlc/concurrency/path_guard.py` (modified — `assert_contained` primitive)
- `src/sdlc/dashboard/__init__.py` (new)
- `src/sdlc/dashboard/server.py` (new)
- `src/sdlc/dashboard/router.py` (new)
- `src/sdlc/dashboard/etag.py` (new)
- `src/sdlc/dashboard/routes/__init__.py` (new)
- `src/sdlc/dashboard/routes/state.py` (new)
- `src/sdlc/dashboard/routes/dora.py` (new)
- `src/sdlc/dashboard/static/index.html` (new)
- `src/sdlc/cli/dashboard.py` (new)
- `src/sdlc/cli/main.py` (modified — register `dashboard` command)
- `scripts/module_boundary_table.py` (modified — `dashboard` → `concurrency`)
- `docs/threat-model.md` (modified — SDLC-THREAT-006)
- `tests/unit/concurrency/test_path_guard.py` (modified — `assert_contained` cases)
- `tests/unit/dashboard/__init__.py` (new)
- `tests/unit/dashboard/_http.py` (new)
- `tests/unit/dashboard/conftest.py` (new)
- `tests/unit/dashboard/test_dashboard_security.py` (new)
- `tests/unit/dashboard/test_dashboard_routes.py` (new)
- `tests/unit/dashboard/test_router.py` (new)
- `tests/unit/cli/test_dashboard.py` (new)
- `tests/dashboard/conftest.py` (new)
- `tests/dashboard/test_dashboard_response.py` (new)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)

## Change Log

- 2026-06-23: Story 5.1 implementation — dashboard server skeleton, read-only routes, security boundary (D1=D2 `assert_contained`).

## Review Findings

bmad-code-review (2026-06-23) — fresh-context, 4 adversarial layers @ Opus-4.8 (Blind Hunter / Edge Case Hunter / Acceptance Auditor / security-reviewer per SECURITY-SENSITIVE routing) + reviewer source/byte/import verification. Triage: 2 decision-needed / 7 patch / 0 defer / 8 dismissed.

**AC verdicts (reviewer-verified against real source):** AC2 MET · AC3 MET · AC4 MET · AC5 MET-with-gap (HEAD/OPTIONS bypass — see Decision R1) · AC6 MET (D1→D2 `assert_contained` correctly scopes to static root; ADR-037 alias-callers unaffected) but traversal defense is incidental for percent-encoded input (Decision R2) · AC1 PARTIAL (denylist, not allowlist — Patch R3). **BLOCKER:** the changeset cannot pass the quality gate as-is — see Patch R-CRIT.

### Decision-needed (resolved 2026-06-23)

- [x] [Review][Decision] **R1 — AC5 "Host-allowlist on ALL requests": HEAD/OPTIONS/TRACE/CONNECT bypass `_dispatch`** — RESOLVED → **(a)** funnel all verbs through `_dispatch` (Host-check first; HEAD = headers-only GET; other non-GET → 405). Now tracked as Patch R1 below.
- [x] [Review][Decision] **R2 — AC6 percent-encoded traversal defense is incidental, not explicit** — RESOLVED → **(b)** reject any static path containing `%` → 404 (safe for the index-only static set; revisit when encoded filenames are needed). Now tracked as Patch R2 below.

### Patch

- [x] [Review][Patch] **R1 (from Decision, MED) — funnel ALL HTTP verbs through `_dispatch` so the Host-allowlist (AC5) runs for every method** [src/sdlc/dashboard/server.py:154-167] — add `do_HEAD/do_OPTIONS/do_TRACE/do_CONNECT` (or a catch-all): Host-check first; HEAD → GET headers without body; other non-GET verbs → 405. Add tests: bad-Host HEAD/OPTIONS → 403, HEAD on `/state.json` → 200 headers + empty body.
- [x] [Review][Patch] **R2 (from Decision, MED) — make AC6 traversal defense explicit: reject any static path containing `%` → 404** [src/sdlc/dashboard/server.py:79-88] — guard `resolve_static_file` so a percent-encoded request path returns `None` (→404) rather than relying on file-non-existence. Add a regression test for `/%2e%2e%2fserver.py` and `/%2e%2e/` → 404.

- [x] [Review][Patch] **R-CRIT (CRITICAL) — `cli/main.py` is not valid UTF-8 → CLI fails to import → entire quality gate cannot pass** [src/sdlc/cli/main.py:1] — the 5.1 edit corrupted pre-existing non-ASCII bytes: the line-1 em-dash `—` became `\xff\xff\xff` and all 23 `§488` became `?488`. `import sdlc.cli.main` raises `SyntaxError: 'utf-8' codec can't decode byte 0xff`. Every test that imports the CLI app fails at collection, so the "33 passed / mypy clean" Completion Note is **not reproducible on this tree** (the recurring Windows cp1252 "asserted-not-measured" trap). Fix: restore `—` and the 23× `§` (committed HEAD is the pristine reference); the intended dashboard-command block (lines 215-223) is clean. Corruption is isolated to this one file (25 other changed files are valid UTF-8).
- [x] [Review][Patch] **R3 (HIGH) — `validate_bind_host` is a single-value denylist, not a localhost allowlist (AC1 intent)** [src/sdlc/dashboard/server.py:31-34] — only `host == "0.0.0.0"` is rejected; `"::"`, `""`, LAN IPs, and hostnames pass. `create_server/serve_dashboard/serve_dashboard_in_thread` all expose `host=`. Flagged by all 4 layers. Fix: invert to an allowlist (`frozenset({"127.0.0.1","::1","localhost"})`) raising the same `SecurityError`, consistent with the existing `_ALLOWED_HOSTS` pattern.
- [x] [Review][Patch] **R4 (MED) — `server_port` is the *requested* port, not the bound port → `--port 0` makes every request 403 + wrong banner** [src/sdlc/dashboard/server.py:191] — with an ephemeral bind the OS assigns a real port but `server_port` stays `0`, so `validate_host_header` rejects every browser request, and the CLI prints `serving on http://127.0.0.1:0`. Fix: after construction set `handler_cls.server_port = server.server_address[1]`.
- [x] [Review][Patch] **R5 (MED) — DORA cache: unlocked check-then-set under `ThreadingHTTPServer` + factually-wrong "single-threaded" docstring** [src/sdlc/dashboard/routes/dora.py:27,35-40] — server is `ThreadingHTTPServer` (one thread/connection, one shared cache); the comment claims the opposite. Benign today (constant body) but a data-race trap for 5.13's real per-data cache, at the freeze point. Fix: guard `get()` with a `threading.Lock` and correct the comment.
- [x] [Review][Patch] **R6 (MED) — 403/405 short-circuits never drain the request body / close the connection → HTTP keep-alive desync** [src/sdlc/dashboard/server.py:125-132] — a write-method or bad-Host request carrying a body over a keep-alive connection leaves unread bytes that corrupt the next request. Fix: set `self.close_connection = True` before writing the 403/405 (or drain `Content-Length`).
- [x] [Review][Patch] **R7 (MED) — DORA TTL/cache tests are tautological** [tests/unit/dashboard/test_dashboard_routes.py:~1290-1306] — `test_dora_cache_ttl_refreshes_entry` and `test_cache_serves_same_payload_on_rapid_requests` assert `first == second` against a module constant, so they pass even if the TTL/refresh branch is deleted. Fix: assert on observable refresh state (e.g. `_expires_at` advancing) or vary the cached value via an injected clock/counter.
- [x] [Review][Patch] **R8 (LOW) — missing test for absent/empty `Host` header** [tests/unit/dashboard/test_dashboard_security.py] — `validate_host_header(None/"")` → `False` (server.py:62) is a security branch not covered by the parametrize list. Fix: add `None` and `""` → 403 cases.

### Dismissed (verified non-issues / out-of-scope)

- `allow_reuse_address = True` set after construction (server.py:195): the functional claim is false — `DashboardHTTPServer(ThreadingHTTPServer)` inherits `HTTPServer.allow_reuse_address = 1`, so `SO_REUSEADDR` *is* applied at bind; the post-construction line is merely redundant/dead.
- Bracketless `Host: ::1` rejected: fails closed; browsers send bracketed `[::1]`. Cosmetic.
- Portless `Host` accepted regardless of bound port: not the rebinding vector — the dashboard runs on a non-default port (8765) so browsers send the port; a rebound hostname is rejected by name. Bind is the real boundary.
- `/state.json` double-read + TOCTOU (state.py:24,35): by-design — Decision D2 mandates reusing the path-based `compute_artifact_hash`; acceptable for small `state.json` (benchmark <100ms). Local single-user TOCTOU is benign.
- `If-None-Match: *` / weak / comma-list not handled (state.py:32): AC2 only requires "matching → 304" (met); the SPA polling client (Decision E2) echoes the exact ETag. Optional future HTTP conformance.
- `log_message` no-op silences security events (server.py:122): intentional suppression of the noisy stdlib default; security-event observability is a later concern, not in 5.1 scope/ACs.
- No commit history → TDD-first/worktree unverifiable: per project flow "review" = working-tree only; TDD-first ordering + worktree branch + merge + green CI are enforced at CLOSE-OUT (check_story_merged_before_done.py + check_fresh_context_review_tag.py). Close-out reminder, not a code defect — though R-CRIT means the gate currently cannot pass.
- Trailing-slash subdirectory resolves to top-level `index.html` (server.py:82): YAGNI — 5.1 ships only `static/index.html`; the fuller static set + subdirectories are explicitly out of scope. One-line fix (`rel + "index.html"`) noted for whoever adds subdirs.

### Patches applied + verification (2026-06-23, working-tree)

All 7 patches (incl. the 2 resolved decisions) applied to the working tree. **NOT committed** — per the merged-before-done gate (CONTRIBUTING §1 / Epic-3 retro A1 / CLAUDE.md), the story stays `review` and flips to `done` only after the TDD-first commit (`test(5.1)→feat(5.1)→docs(5.1)`) on worktree `epic-5/5-1-dashboard-server-skeleton`, merge to `main`, and **green POSIX CI** (which must also confirm the NFR-PERF-3 `<100ms` benchmark — Task 10).

Verified on Windows (dashboard is `io_primitives`-free by design):
- ruff `format --check` + `check`: clean (19 files); mypy `--strict`: clean (10 src files); `check_module_boundaries.py`: exit 0; `server.py` 266 ≤ 400 LOC; all 26 changed files valid UTF-8; `import sdlc.cli.main` OK.
- 31/31 direct live-server + unit smoke checks GREEN (bind allowlist incl. `::`/`""`/LAN reject; host allowlist incl. `None`/`""`; `%`-reject; DORA TTL clock set/hold/refresh; `server_port == bound` at `port=0`; GET 200+ETag; 304; HEAD 200 empty-body; OPTIONS/POST → 405 `Allow: GET, HEAD`; bad-Host 403 incl. HEAD; `/api/dora` synthetic; `/../` 404; `/%2e%2e%2f` 404; index 200).
- Full `pytest`/coverage≥87/freeze 7-7/`mkdocs --strict` **not runnable on win32** (root `tests/conftest.py` imports the engine → `concurrency.io_primitives` POSIX-only `ImportError` → blocks all collection; same constraint as the dev host — first execute on POSIX CI). Zero wire-format change (freeze stays 7/7; `/api/dora` schema internal per DAG Decision D1).
