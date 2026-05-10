# Story 2A.0: E2E Test Harness — Tier-1 CLI + Tier-2 Pipeline (MockAIRuntime)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Dana (QA Engineer, lead) and Charlie (Senior Dev, reviewer) building the precursor E2E test harness for Epic 2A,
I want a two-tier reusable harness — Tier-1 (CLI in → stdout/stderr/exit-code/journal-hash/state-hash goldens under `tests/e2e/cli/`) and Tier-2 (full Phase 1 → Phase 2 → Phase 3 pipeline replay against `MockAIRuntime` under `tests/e2e/pipeline/`) — committed before Story 2A.1 begins,
so that every Epic 2A story (2A.1–2A.19) can land with byte-stable behavioral coverage instead of unit-only verification, the Pattern 1 "tautological/placebo test" defect class identified in the Epic 1 retro is structurally closed, and parallelized worktree execution (per CONTRIBUTING.md §3) can rely on a shared deterministic golden corpus that diffs as ordinary text in PR review.

This story is the **Layer-0 precursor** for Epic 2A's DAG (`epic-1-retro-2026-05-09.md` §6.4). It blocks Stories 2A.1, 2A.2, 2A.5 (Layer 1 parallel) and every downstream layer. It implements the framework defined in [ADR-027](docs/decisions/ADR-027-e2e-test-framework-strategy.md); Tier-3 (real-Claude pipeline tests) is explicitly deferred to Epic 2B Story 2B.3 per ADR-027 §"Tier-3".

## Acceptance Criteria

### AC1 — Directory layout under `tests/e2e/`

**Given** Epic 1 shipped only narrow integration slices under `tests/integration/test_*_e2e.py` and tier discipline is missing,

**When** Story 2A.0 lands,

**Then** the following exact directory structure exists and is committed:

```
tests/e2e/
├── __init__.py                       # empty; declares the e2e package
├── conftest.py                       # tier-shared fixtures (see AC4)
├── cli/
│   ├── __init__.py                   # empty
│   ├── conftest.py                   # Tier-1 fixtures: cli_runner, golden_dir, update_goldens
│   ├── README.md                     # Tier-1 author guide (see AC8)
│   ├── fixtures/
│   │   └── walking_skeleton/         # seed scenario — proves the harness works end-to-end
│   │       ├── README.md             # describes scenario inputs/expected goldens
│   │       ├── commands.yaml         # ordered list of `sdlc <args>` invocations
│   │       └── goldens/
│   │           ├── 01_init.stdout
│   │           ├── 01_init.stderr
│   │           ├── 01_init.exit
│   │           ├── 01_init.journal_sha256
│   │           ├── 01_init.state_sha256
│   │           ├── 02_scan.stdout
│   │           ├── 02_scan.stderr
│   │           ├── 02_scan.exit
│   │           ├── 02_scan.journal_sha256
│   │           ├── 02_scan.state_sha256
│   │           ├── 03_status.stdout
│   │           ├── 03_status.stderr
│   │           ├── 03_status.exit
│   │           ├── 03_status.journal_sha256
│   │           └── 03_status.state_sha256
│   └── test_walking_skeleton_goldens.py   # at least one passing Tier-1 test exercising the seed scenario
├── pipeline/
│   ├── __init__.py                   # empty
│   ├── conftest.py                   # Tier-2 fixtures: pipeline_runner, mock_runtime_factory
│   ├── README.md                     # Tier-2 author guide (see AC8)
│   ├── fixtures/
│   │   └── happy_path_smoke/         # seed scenario — minimal pipeline replay (single-phase OK for 2A.0)
│   │       ├── README.md
│   │       ├── pipeline.yaml         # multi-step command sequence + MockAIRuntime fixture path
│   │       ├── mock_responses/       # YAML-driven MockAIRuntime fixtures (per src/sdlc/runtime/mock.py)
│   │       │   └── _smoke.yaml       # mirrors tests/fixtures/mock_responses/_smoke.yaml shape
│   │       └── goldens/
│   │           ├── final_journal_sha256
│   │           ├── signoff_hashes.json     # one hash per phase-N.yaml signoff produced
│   │           ├── hook_chain_order.json   # sequence of (hook_name, command, arg_summary) tuples
│   │           └── specialist_invocations.json  # sequence of (specialist_id, primary|parallel, write_glob_set)
│   └── test_happy_path_smoke.py       # at least one passing Tier-2 test exercising the seed scenario
```

**And** `tests/e2e/__init__.py`, `tests/e2e/cli/__init__.py`, `tests/e2e/pipeline/__init__.py` are empty files (mirrors `tests/contracts/__init__.py` per Story 1.21 AC2.1 — needed for `pytest --import-mode=prepend` in `pyproject.toml:203` to discover modules with the same basename across tiers without collision).

**And** every Python file in this tree begins with `from __future__ import annotations` as its first non-docstring line (project convention enforced by pre-commit hook per ADR-010).

**And** every Python file stays ≤ 400 LOC (Day-1 quality gate, ADR-002). Helper extraction to private `_*.py` siblings is permitted and expected (mirrors `tests/integration/_abstraction_adequacy_helpers.py` pattern).

### AC2 — Tier-1 CLI golden harness contract

**Given** the seed `walking_skeleton` scenario under `tests/e2e/cli/fixtures/walking_skeleton/`,

**When** `pytest tests/e2e/cli/ -m e2e` runs,

**Then** for each command in `commands.yaml` (loaded in declared order, indexed `01..NN`):

1. The harness creates a fresh `tmp_path` working directory per scenario (NOT per command — the command sequence shares a project root, mirroring the real CLI lifecycle).
2. The harness invokes `uv run sdlc <args> --no-color` (always with `--no-color` to strip ANSI; `--json` flag added per-command via `commands.yaml` `flags:` key when structured output is asserted) via `subprocess.run(..., check=False, capture_output=True, text=True)` — same shape as `tests/integration/test_walking_skeleton_e2e.py:_run`.
3. After each command, the harness asserts five goldens byte-for-byte:
   - `<NN>_<cmd>.stdout` — `result.stdout` UTF-8 bytes, with two sanctioned normalizations applied BEFORE comparison: (a) `_normalize_paths(text, tmp_path)` replaces both `str(tmp_path)` and `str(tmp_path.resolve())` with `<TMP>` (P5/AC5.3); (b) `_normalize_timestamps(text)` replaces ISO-8601-like timestamps with `<TIMESTAMP>` (P24/D1 — sanctioned 2026-05-10; the regex anchors to `YYYY-MM-DD[T ]HH:MM:SS(\.\d+)?(Z|[+-]HHMM|[+-]HH:MM)?` so isolated dates and times do not match). Trailing newline preserved verbatim modulo these normalizations.
   - `<NN>_<cmd>.stderr` — `result.stderr` UTF-8 bytes after `_strip_uv_preamble()` (strips `Resolved N packages in Xms`, `Built <pkg> @ <url>` — anchored to `@ <url>` so sdlc-emitted lines are safe — and `Audited N packages in Xms` for uv 0.5+) AND the same path/timestamp normalizations as stdout (P24/D1).
   - `<NN>_<cmd>.exit` — decimal exit-code as ASCII text + trailing `\n` (e.g. `"0\n"`).
   - `<NN>_<cmd>.journal_sha256` — `sha256` (lowercase hex + trailing `\n`) of `<sdlc_dir>/state/journal.log` if it exists; the literal string `"<no-journal>\n"` otherwise (path corrected per P26/D3 — the actual state writer uses `.claude/state/journal.log`, not `.sdlc/state/journal.jsonl`). The hash is computed via `_hash_journal_no_ts` which ts-strips each entry then sha256s the canonical join — see AC5.1 (P28/D5: this re-canonicalization is journal-only).
   - `<NN>_<cmd>.state_sha256` — `sha256` (lowercase hex + trailing `\n`) of `<sdlc_dir>/state/state.json` if it exists; `"<no-state>\n"` otherwise (path corrected per P26/D3 — the actual writer uses `state.json`, not `active.json`). State hash uses raw bytes-on-disk per AC5.5 (P28/D5: state is content-addressed, no ts to strip).
4. On golden mismatch, the harness MUST emit a unified diff via `difflib.unified_diff` for stdout/stderr/exit (text-comparable goldens) and a clear `expected != actual` line for the two `*_sha256` goldens, plus a single line: `action: review the diff. If intentional, regenerate via 'pytest tests/e2e/cli/ --update-goldens' and cite the change in the PR Change Log.` (per ADR-027 "Golden-update workflow").
5. `--update-goldens` is implemented as a custom pytest CLI flag in `tests/e2e/conftest.py` via `pytest_addoption`; when set, the harness rewrites the goldens in place and records nothing to journal/state (it MUST NOT mutate test outcomes — failing assertions still fail). CI never passes `--update-goldens` (enforced by absence in `.github/workflows/ci.yml`; an AC-bound test asserts `"--update-goldens" not in (Path(".github/workflows/ci.yml").read_text())`).

**And** the seed `walking_skeleton` scenario's `commands.yaml` declares exactly:
```yaml
schema_version: 1
scenario: walking_skeleton
commands:
  - id: "01_init"
    args: ["init"]
    flags: []
  - id: "02_scan"
    args: ["scan"]
    flags: []
  - id: "03_status"
    args: ["status"]
    flags: []
```

**And** the loader for `commands.yaml` is defined in `tests/e2e/cli/conftest.py` (NOT in `src/sdlc/`) — Tier-1 harness code is test-only and MUST NOT import from `src/sdlc/cli/` internals; it interacts only via the public CLI surface (subprocess). This is the load-bearing isolation that makes Tier-1 tests insensitive to internal refactors.

**And** `commands.yaml` is parsed with the same `_NoDuplicateKeysLoader` pattern as `src/sdlc/runtime/mock.py:68–103` (re-implemented locally in test code — copy-paste is acceptable per ADR-027 "pytest-only goldens are sufficient"; do NOT introduce a `tests/_lib/` shared helper in 2A.0 to avoid premature abstraction). Duplicate keys in `commands.yaml` raise on load with a clear error citing the offending line.

**And** the seed scenario passes against the `Story 1.16/1.17/1.18` walking-skeleton CLI surface that already exists today (Tier-1 harness is exercised against shipped behavior — proves harness works without depending on Epic 2A code).

### AC3 — Tier-2 pipeline harness contract (MockAIRuntime-driven)

**Given** the seed `happy_path_smoke` scenario under `tests/e2e/pipeline/fixtures/happy_path_smoke/`,

**When** `pytest tests/e2e/pipeline/ -m e2e` runs,

**Then**:

1. The harness loads `pipeline.yaml` declaring an ordered list of `sdlc <command>` invocations + a `mock_responses_dir:` pointing at the scenario-local `mock_responses/` subtree (one MockAIRuntime YAML per workflow step, per `src/sdlc/runtime/mock.py:191–218`).
2. The harness constructs `MockAIRuntime(fixtures_dir=<scenario>/mock_responses)` directly via in-process import (Tier-2 runs in-process; `subprocess` is reserved for Tier-1). Tier-2 needs in-process access to the runtime ABC because Epic 2A dispatcher (Story 2A.3) is async and the engine path under test consumes the ABC (Architecture §1062). For Story 2A.0, since 2A.3 has not landed, the seed scenario invokes a placeholder `engine.dispatch_panel_smoke(mock_runtime)` shim in `tests/e2e/pipeline/conftest.py` that `await`s `MockAIRuntime.dispatch(prompt="...", context={"workflow_step": "_smoke"})` once. The shim is replaced wholesale by Story 2A.3 — its purpose is to prove `MockAIRuntime` integrates with `asyncio.run` end-to-end before real dispatcher exists.
3. After the full replay, the harness asserts four goldens byte-for-byte:
   - `final_journal_sha256` — single-line lowercase hex sha256 of the final `<tmp_path>/.claude/state/journal.log` (or `"<no-journal>\n"`) — path corrected per P26/D3 to match Tier-1 and the actual state-writer convention. The path is harmless today (the 2A.0 smoke shim writes nothing) and becomes load-bearing in Story 2A.3 when the real journal-writing dispatcher lands.
   - `signoff_hashes.json` — JSON array of `{"phase": N, "hash": "sha256:<hex>"}` records per phase signoff written. For 2A.0 seed, this MUST be `[]` (no signoffs in single-step smoke); the file exists with content `"[]\n"` to lock the format.
   - `hook_chain_order.json` — JSON array of `{"hook": "<name>", "command": "<sdlc-cmd>", "arg_summary": "<short>"}` per hook fired. For 2A.0 seed, this MUST be `[]` (engine hooks ship with Story 2A.4).
   - `specialist_invocations.json` — JSON array of `{"specialist_id": "<id>", "kind": "primary|parallel|synthesizer", "write_glob_set": ["<glob>", ...]}` per dispatch. For 2A.0 seed, this MUST be `[{"specialist_id": "_smoke", "kind": "primary", "write_glob_set": []}]` (the single mock dispatch).
4. JSON goldens are canonicalized identically to journal entries: `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), indent=2).encode("utf-8") + b"\n"` (matches Story 1.21 AC1.3 canonicalization rule). This locks the format; the snapshot is human-reviewable as a diff while staying byte-stable.
5. `--update-goldens` flag from AC2 applies identically to Tier-2 fixtures.
6. The harness MUST NOT make any outbound network call (NFR-PRIV-1 — already enforced repo-wide; explicit reminder for harness authors). `MockAIRuntime` never crosses a process boundary.

**And** the seed `happy_path_smoke/pipeline.yaml` declares:
```yaml
schema_version: 1
scenario: happy_path_smoke
mock_responses_dir: "./mock_responses"
steps:
  - id: "01_smoke_dispatch"
    kind: "engine_dispatch_smoke"      # 2A.0 placeholder; Story 2A.3 introduces real `cli_invoke` kind
    workflow_step: "_smoke"
    prompt: "smoke test prompt"
```

**And** the seed `mock_responses/_smoke.yaml` declares one fixture record keyed by `_hash_prompt("smoke test prompt")` with the same shape as `tests/fixtures/mock_responses/_smoke.yaml` (refer to that file as the canonical example; do NOT duplicate its full contents here — link via README).

**And** the harness asserts that `MockAIRuntime` raised no `MockMissError` during the replay (positive assertion — explicitly check the absence; do NOT rely on "no exception => pass").

**And** Tier-2 harness code MAY import from `sdlc.runtime`, `sdlc.errors`, `sdlc.contracts` (the public ABC + error hierarchy + wire contracts). It MUST NOT import from `sdlc.cli`, `sdlc.engine`, `sdlc.dispatcher` internals — when those land in Stories 2A.1/2A.3, the harness consumes them through the same public seams that real callers use. The boundary is enforced by the existing `scripts/check_module_boundaries.py` linter under `tests/` (verified by extending its allow-list table; if the linter currently has no `tests/` rule, leave it as-is and document the convention in `tests/e2e/README.md` — do not expand the linter scope in 2A.0).

### AC4 — Shared `tests/e2e/conftest.py` fixtures + pytest plumbing

**Given** the harness must support both tiers cleanly,

**When** Story 2A.0 lands,

**Then** `tests/e2e/conftest.py` defines exactly these fixtures + plugins (and nothing more — keep the surface minimal):

1. `pytest_addoption(parser)` — adds `--update-goldens` (default `False`) and reads it via `request.config.getoption("--update-goldens")`.
2. `update_goldens` (session-scoped fixture) — returns the bool. Used by `cli/conftest.py` and `pipeline/conftest.py` golden-comparison helpers.
3. `e2e_repo_root` (session-scoped) — `Path` of the repo root resolved via `Path(__file__).resolve().parents[2]` (i.e. project root, the dir containing `pyproject.toml`). Used to invoke `uv run` from a stable cwd.
4. `_strip_uv_preamble(stderr: str) -> str` — a module-level helper (NOT a fixture) that removes `Resolved <N> packages in <X>ms` and `Built <pkg>` lines from stderr. Documented inline with rationale.

**And** `tests/e2e/cli/conftest.py` defines:

1. `cli_runner` (function-scoped) — yields a callable `(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]` that wraps `subprocess.run(["uv", "run", "sdlc", "--no-color", *args], cwd=cwd, capture_output=True, text=True, check=False, env=...)`. The `--no-color` flag is unconditional; per-command `--json` is added via the caller's `args` list.
2. `golden_dir(request)` — returns the `Path` to the current scenario's `goldens/` dir. Resolved from `request.node.nodeid` + the scenario name embedded in the test param.
3. `assert_goldens(scenario_dir: Path, command_id: str, result: subprocess.CompletedProcess, sdlc_dir: Path, update: bool)` — the central assertion helper. Implements all five golden comparisons (AC2.3) + the unified-diff error-emission rule (AC2.4) + the `--update-goldens` rewrite rule (AC2.5).

**And** `tests/e2e/pipeline/conftest.py` defines:

1. `pipeline_runner` (function-scoped, async-aware) — accepts a scenario dir and yields a coroutine that drives the replay. Uses `asyncio.run` internally; tests can be plain `def test_*` (NOT `async def`) and call `asyncio.run(...)` themselves OR use the runner fixture which encapsulates it. Pick one pattern in 2A.0 (the runner-fixture path) and document the choice in `pipeline/README.md`.
2. `mock_runtime_factory(scenario_dir: Path) -> MockAIRuntime` — instantiates the runtime against `<scenario_dir>/mock_responses`. Document that the factory caches per-scenario (avoid re-loading YAML across tests in the same session).
3. `assert_pipeline_goldens(scenario_dir: Path, observed: PipelineObservation, update: bool)` — central assertion helper for the four Tier-2 goldens. `PipelineObservation` is a `@dataclass(frozen=True)` declared inline in `pipeline/conftest.py` with fields: `final_journal_path: Path`, `signoff_hashes: tuple[dict, ...]`, `hook_chain: tuple[dict, ...]`, `specialist_invocations: tuple[dict, ...]`.

**And** `pyproject.toml:218` already declares the `e2e` marker — verify it exists and DO NOT re-declare. If it is missing, add it as a single-line patch with a citation to ADR-027.

**And** all e2e tests MUST be marked `@pytest.mark.e2e`. CI runs them in PR via the existing `pytest -q` gate (they're under `tests/` so `testpaths` discovers them); a separate `e2e.yml` nightly job is explicitly NOT introduced by 2A.0 (per ADR-007, that file is reserved for real-Claude Tier-3 deferred to Epic 2B).

### AC5 — Determinism + reproducibility invariants

**Given** the goldens are byte-stable artifacts in source control,

**When** the e2e suite runs,

**Then** the following determinism invariants hold and are asserted by at least one test each:

1. **No wall-clock leakage.** No golden contains a current-time timestamp.
   - **Journal goldens (`*.journal_sha256`):** `_hash_journal_no_ts` re-canonicalizes each JSON line WITHOUT the `ts` field before hashing (NOT raw bytes-on-disk). 2A.0 does not introduce a time-freeze hook; the ts-strip approach is the documented choice. (P28/D5 narrows AC5.1 scope to journals only.)
   - **Stdout/stderr goldens:** `_normalize_timestamps` replaces ISO-8601-like timestamps with `<TIMESTAMP>` BEFORE comparison. Sanctioned by the 2026-05-10 P24/D1 amendment — earlier wording said this normalization was forbidden, which contradicted the implementation's need to compare commands like `sdlc status` whose stdout includes a wall-clock `Last updated`. The regex is anchored to `YYYY-MM-DD[T ]HH:MM:SS(\.\d+)?(Z|[+-]HHMM|[+-]HH:MM)?` so an isolated date or time in epic content does not match.
2. **No environment leakage.** The `cli_runner` fixture passes a sanitized `env` dict containing only `PATH`, `HOME`, `USER`, `TMPDIR`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `NO_COLOR=1`, `PYTHONHASHSEED=0`, and the in-test-needed `UV_*` vars discovered by experiment. All other env is stripped. This closes the "developer's local env leaks into goldens" failure mode.
3. **No path leakage.** Goldens that contain absolute paths (e.g. error messages citing `tmp_path`) MUST be normalized via a `_normalize_paths(text: str, tmp_path: Path) -> str` helper that replaces `str(tmp_path)` with the literal sentinel `<TMP>` BEFORE comparison. Documented inline.
4. **OS-conditional skip discipline.** Every Tier-1 command that depends on POSIX-only code paths (e.g. `sdlc scan` per Story 1.17 → uses `journal.append_sync` flock — POSIX-only) is decorated with `@pytest.mark.skipif(sys.platform == "win32", reason="...")` mirroring `tests/integration/test_walking_skeleton_e2e.py:_SKIP_WIN32`. The skip marker is applied per-test, not per-scenario — Windows runs subset goldens (`init`, `status` non-scan) successfully.
5. **Hashing canonicality.** Hash discipline is asymmetric by artifact (P28/D5):
   - **State (`state.json`):** hashed on raw bytes-on-disk — what writers wrote is what readers hash. State has no timestamps.
   - **Journal (`journal.log`):** re-canonicalized without `ts` in test code (`_hash_journal_no_ts`) before hashing, because journal entries embed wall-clock `ts` that varies between runs. Until a frozen-time hook exists in production code (deferred), test-code re-canonicalization is the only viable byte-stable path.
   - **Pipeline JSON goldens (`*.json`):** canonicalized via `_canon_json` (`sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`, `indent=2`, trailing `\n`) — Story 1.21 AC1.3 rule.

   Earlier wording mandated raw-bytes-only hashing for everything (AC5.5 contradicted AC5.1 for journals). The asymmetry above is the formal resolution.

**And** at least one Tier-2 test runs the seed scenario twice in the same pytest invocation with the same `MockAIRuntime` instance and asserts byte-identical observations on both runs (replay-determinism / pure-mock invariant — closes the "mock state leaked between calls" failure mode).

### AC6 — Behavioral coverage receipt (anti-tautology gate)

**Given** Pattern 1 (Epic 1 retro §3) — tautological tests passed for the wrong reason in 5 of 22 stories,

**When** Story 2A.0 lands,

**Then** the harness MUST satisfy these anti-tautology checks:

1. **Mutation receipt.** `tests/e2e/test_harness_anti_tautology.py` exists and contains at least three explicit "mutation tests": each test deliberately corrupts a golden file (via tmp-path copy + edit), reruns the harness, and asserts the harness FAILS with a clear diff. The corruption targets: (a) flip a single byte in `01_init.stdout`, (b) bump `01_init.exit` from `0\n` to `1\n`, (c) replace `02_scan.journal_sha256` with a random hex. Each must produce a `pytest` failure that names the corrupted golden in the failure message.
2. **Mock-miss surfaces clearly.** A test deliberately omits a fixture record from `_smoke.yaml`, runs the Tier-2 harness, and asserts a `MockMissError` is raised with the offending `(workflow_step, prompt_hash)` in the message — proving the harness does not silently swallow a missing fixture.
3. **`--update-goldens` cannot mask a real bug.** A test runs the harness with `--update-goldens` against an intentionally corrupted scenario and asserts: (a) goldens are rewritten; (b) the test still fails because production code disagreed with itself between two runs of the same command (deterministic replay invariant). This proves the update flag regenerates goldens but does NOT silence semantic regressions.

**And** these three anti-tautology tests are themselves flagged in dev notes as **THE most important tests in this story** — without them the harness is just another way to ship Pattern 1 defects.

### AC7 — Documentation + ADR cross-references

**Given** ADR-027 is the load-bearing decision document for this work,

**When** Story 2A.0 lands,

**Then**:

1. `tests/e2e/README.md` exists; describes the two-tier strategy in ≤ 60 lines; cross-references ADR-027 and CONTRIBUTING.md §6 PR template; lists what kind of test belongs in which tier; includes a 5-line "How to add a new scenario" recipe per tier.
2. `tests/e2e/cli/README.md` exists; documents the seed scenario format (`commands.yaml` schema, golden file naming `<NN>_<cmd>.<ext>`, `--update-goldens` workflow); ≤ 80 lines.
3. `tests/e2e/pipeline/README.md` exists; documents `pipeline.yaml` schema, MockAIRuntime fixture authoring (delegates to `src/sdlc/runtime/mock.py` docstring for the YAML record shape — do NOT duplicate that content), and the four Tier-2 goldens; ≤ 100 lines.
4. ADR-027 status flips from `Proposed` → `Accepted` as a single-line edit, dated `2026-05-1?` (whatever date the story merges) with a one-line consequence: `Implemented by Story 2A.0; seed scenarios under tests/e2e/cli/walking_skeleton + tests/e2e/pipeline/happy_path_smoke.` Story PR cites the ADR transition in the Change Log.
5. `CONTRIBUTING.md §6 Story PR Template` lines 180–183 already reference Tier-1/Tier-2 — verify they remain accurate post-2A.0; no edit needed unless wording drifted.

**And** the per-tier README files explicitly call out the anti-tautology checks (AC6) under a "Don't lie to yourself" heading — this is a process-discipline marker, not just docs.

### AC8 — Quality gate compliance

**Given** the Day-1 quality gate (CONTRIBUTING.md §1),

**When** Story 2A.0 lands,

**Then** all of the following pass locally and in CI:

1. `ruff format --check tests/e2e` — clean.
2. `ruff check tests/e2e` — zero violations.
3. `mypy --strict tests/e2e` — zero errors. Test fixtures may need `# type: ignore[no-untyped-call]` on `subprocess.run` (pattern from `tests/integration/test_walking_skeleton_e2e.py:26`) — copy the pattern.
4. `pytest tests/e2e -q -m e2e` — zero failures, zero skips on Linux CI (Windows skips are expected per AC5.4 — the count is documented in dev notes).
5. `pytest --cov=src/sdlc --cov=scripts --cov-fail-under=90` — ≥ 90% repo-wide. Tier-1 tests contribute integration-shaped coverage to existing CLI modules; Tier-2 contributes engine-side coverage. Story 2A.0 MUST NOT regress repo coverage below 93% (Epic 1 final). If it does, the story is rejected at review-A.
6. `pre-commit run --all-files` — all hooks pass.
7. `python scripts/freeze_wireformat_snapshots.py --check` — byte-stable (Story 2A.0 does not touch wire-format contracts; this MUST remain green).
8. `mkdocs build --strict` — zero warnings (per ADR-011).

**And** the PR follows CONTRIBUTING.md §4 chunked review (review-A → review-B → review-C) with explicit `D1/D2/D3` decision-protocol use for any reviewer-raised material decision (per CONTRIBUTING.md §5).

**And** TDD-first ordering is OPTIONAL for Story 2A.0 explicitly because this story IS the test infrastructure (the tests don't have prior tests to test their tests against — meta-circular). Use **test-along** with explicit justification in the PR body per CONTRIBUTING.md §2 second paragraph.

## Tasks / Subtasks

- [x] **Task 1 — Bootstrap directory layout (AC: 1)**
  - [x] 1.1 Create `tests/e2e/` and tier subdirectories with `__init__.py` files.
  - [x] 1.2 Add `tests/e2e/conftest.py` with `pytest_addoption(--update-goldens)` + `update_goldens` + `e2e_repo_root` fixtures + `_strip_uv_preamble` helper.
  - [x] 1.3 Verify `pyproject.toml:218` `e2e` marker exists; if not, add.
- [x] **Task 2 — Tier-1 conftest + helpers (AC: 2, 4)**
  - [x] 2.1 Implement `tests/e2e/cli/conftest.py` with `cli_runner`, `golden_dir`, `assert_goldens`.
  - [x] 2.2 Implement local `_NoDuplicateKeysLoader` for `commands.yaml` (copy-paste from `src/sdlc/runtime/mock.py`).
  - [x] 2.3 Implement env-sanitization in `cli_runner` (AC5.2 allow-list).
  - [x] 2.4 Implement `_normalize_paths` helper (AC5.3).
- [x] **Task 3 — Tier-1 seed scenario `walking_skeleton` (AC: 1, 2, 5)**
  - [x] 3.1 Author `tests/e2e/cli/fixtures/walking_skeleton/commands.yaml` (init → scan → status).
  - [x] 3.2 Run the harness against shipped CLI surface to capture initial goldens via `--update-goldens` (this is the bootstrapping step).
  - [x] 3.3 Manually inspect each golden file in PR review (do NOT just rubber-stamp `--update-goldens` output).
  - [x] 3.4 Author `tests/e2e/cli/test_walking_skeleton_goldens.py` exercising the scenario; pass.
  - [x] 3.5 Apply `@pytest.mark.skipif(sys.platform == "win32")` to the `02_scan` step (POSIX-only, mirrors integration test).
- [x] **Task 4 — Tier-2 conftest + helpers (AC: 3, 4)**
  - [x] 4.1 Implement `tests/e2e/pipeline/conftest.py` with `pipeline_runner`, `mock_runtime_factory`, `assert_pipeline_goldens`, `PipelineObservation` dataclass.
  - [x] 4.2 Implement JSON canonicalization helper for goldens (AC3.4).
  - [x] 4.3 Implement the `engine.dispatch_panel_smoke(mock_runtime)` shim placeholder (clearly labeled as a 2A.0 placeholder; remove note added to dev notes that Story 2A.3 will replace it).
- [x] **Task 5 — Tier-2 seed scenario `happy_path_smoke` (AC: 1, 3)**
  - [x] 5.1 Author `pipeline.yaml` + `mock_responses/_smoke.yaml` (mirror existing `tests/fixtures/mock_responses/_smoke.yaml` shape).
  - [x] 5.2 Author `tests/e2e/pipeline/test_happy_path_smoke.py`; pass.
  - [x] 5.3 Capture the four goldens (`final_journal_sha256`, `signoff_hashes.json`, `hook_chain_order.json`, `specialist_invocations.json`).
- [x] **Task 6 — Anti-tautology tests (AC: 6) — HIGHEST RISK**
  - [x] 6.1 Author `tests/e2e/test_harness_anti_tautology.py` with the three mutation receipts (byte-flip stdout, exit-code drift, hash drift).
  - [x] 6.2 Add the mock-miss surface test.
  - [x] 6.3 Add the `--update-goldens` semantic-regression test.
  - [x] 6.4 Manually verify each test FAILS when its target invariant is broken — DO NOT trust that the test "looks right".
- [x] **Task 7 — Documentation (AC: 7)**
  - [x] 7.1 Author `tests/e2e/README.md` (≤ 60 lines).
  - [x] 7.2 Author `tests/e2e/cli/README.md` (≤ 80 lines).
  - [x] 7.3 Author `tests/e2e/pipeline/README.md` (≤ 100 lines).
  - [x] 7.4 Edit `docs/decisions/ADR-027-e2e-test-framework-strategy.md` — flip status `Proposed` → `Accepted`, add 1-line consequence citing 2A.0.
- [x] **Task 8 — Quality gate sweep (AC: 8)**
  - [x] 8.1 `ruff format --check tests/e2e` + `ruff check tests/e2e` clean.
  - [x] 8.2 `mypy --strict tests/e2e` zero errors.
  - [x] 8.3 `pytest tests/e2e -q -m e2e` zero failures.
  - [x] 8.4 `pytest --cov=src/sdlc --cov=scripts --cov-fail-under=90` ≥ 90%; verify 93%+ retained.
  - [x] 8.5 `pre-commit run --all-files` clean.
  - [x] 8.6 `python scripts/freeze_wireformat_snapshots.py --check` byte-stable.
  - [x] 8.7 `mkdocs build --strict` clean.

### Review Findings

_Code review run: 2026-05-10 (Blind Hunter + Edge Case Hunter + Acceptance Auditor — 3 layers, 0 failed)._

#### Decision-needed — RESOLVED (converted to patches)

All 5 decision-needed findings were resolved on 2026-05-10 by accepting recommended options. Each became a patch (P24-P28 below).

- **D1 RESOLVED → Option 2** — Amend spec AC2.3/AC5.1 to formally allow stdout/stderr timestamp normalization; tighten the `_normalize_timestamps` regex to anchor on expected formats. Tracked as **P24**.
- **D2 RESOLVED → Option 3** — Add a SECOND test matching spec AC6.3 semantics (production-code disagreement between two `--update-goldens` runs); keep current `test_update_goldens_cannot_mask_semantic_regression`. Tracked as **P25**.
- **D3 RESOLVED → Option 1** — Update spec AC2.3/AC3.3 to reality (`.claude/state/journal.log` + `state.json`); reconcile Tier-2 path in `pipeline/conftest.py:1132`. Tracked as **P26**.
- **D4 RESOLVED → Option 3** — Add explicit D-decision note in Change Log for `pyproject.toml` `mypy_path` deviation; no spec amendment. Tracked as **P27**.
- **D5 RESOLVED → Option 3** — Split AC5.1/AC5.5 by artifact: journal uses AC5.1 (re-canonicalize without `ts`), state.json uses AC5.5 (raw bytes-on-disk). Formalize via spec edit. Tracked as **P28**.

#### Patch

- [x] [Review][Patch] **P1 — Add CI `--update-goldens` absence assertion (AC2.5)** [`tests/e2e/test_harness_anti_tautology.py`] — Spec AC2.5 requires AC-bound test asserting `"--update-goldens" not in (Path(".github/workflows/ci.yml").read_text())`. Missing entirely. README claim ("asserted by `test_harness_anti_tautology.py`") is false.
- [x] [Review][Patch] **P2 — Tier-2 deterministic replay test is tautological** [`tests/e2e/pipeline/conftest.py:1080-1086` + `tests/e2e/pipeline/test_happy_path_smoke.py:1332-1356`] — `mock_runtime_factory` is `scope="session"` and path-cached; both replay runs share same MockAIRuntime instance. Test cannot detect inter-instance state. Also asserts only `not exists()` on journal — never byte-compares journal between runs. Fix: change scope to `function`, OR have determinism test instantiate two distinct runtimes, OR add explicit byte-comparison of all four golden artifacts between runs.
- [x] [Review][Patch] **P3 — `_dispatch_panel_smoke` records phantom invocation on `MockMissError`** [`tests/e2e/pipeline/conftest.py:1055-1065`] — Invocation record is built (lines 1056-1060) BEFORE dispatch runs. If `MockMissError` raises, `mock_miss_raised = True` but invocation is still appended — `specialist_invocations.json` shows successful dispatch when mock missed. Fix: move append to after successful await, OR drop the record when `mock_miss_raised`.
- [x] [Review][Patch] **P4 — Anti-tautology byte-flip has self-defeating fallback** [`tests/e2e/test_harness_anti_tautology.py:1462`] — `corrupted = (bytes([original[0] ^ 0xFF]) + original[1:]) if original else b"CORRUPTED\n"`. If golden becomes empty, "corruption" silently writes a different value and test "passes" tautologically. Also `^ 0xFF` may produce invalid UTF-8 leading byte, masking AssertionError with UnicodeDecodeError. Fix: assert `original` non-empty; assert `corrupted != original`; XOR a non-leading byte or use `^ 0x01` on a known-ASCII position.
- [x] [Review][Patch] **P5 — `_normalize_paths` substring replace unsafe** [`tests/e2e/cli/conftest.py:297-303`] — Naive `text.replace(str(tmp_path), "<TMP>")`. If `tmp_path = /tmp/pytest-X` and CLI emits `/tmp/pytest-X-extra/...`, only prefix replaced → `<TMP>-extra/...`. Misses paths via `realpath` (macOS `/var/folders` vs `/private/var/folders`). Fix: replace both `str(tmp_path)` and `str(tmp_path.resolve())`; consider word-boundary regex.
- [x] [Review][Patch] **P6 — `subprocess.run` has no timeout — CI hang risk** [`tests/e2e/conftest.py:797-804`] — Add `timeout=60` (or scenario-configurable), handle `TimeoutExpired` with actionable message.
- [x] [Review][Patch] **P7 — `subprocess.run` `text=True` lacks `errors='replace'`** [`tests/e2e/conftest.py:797-804`] — Undecodable bytes raise `UnicodeDecodeError` and abort test before goldens compared. Fix: add `errors='replace'` or capture as bytes and decode explicitly.
- [x] [Review][Patch] **P8 — `_strip_uv_preamble` "Built \\S+" pattern too permissive** [`tests/e2e/conftest.py:825-826`] — `re.match(r"^Built \S+", line)` silently drops any sdlc-emitted stderr starting with "Built ". Fix: anchor to known uv preamble shape (e.g., `r"^Built \S+ in [\d.]+s"`) or stop after first non-uv-preamble line.
- [x] [Review][Patch] **P9 — Schema validation missing on `commands.yaml` and `pipeline.yaml`** [`tests/e2e/cli/conftest.py:330-336` + `tests/e2e/pipeline/conftest.py:1101-1138`] — Loaders cast without validation; malformed YAML produces cryptic `AttributeError` / `KeyError`. Fix: validate `schema_version`, top-level keys (`commands` / `steps`), and per-item required fields (`id`/`args`, `kind`/`prompt`/`workflow_step`); raise with action hint.
- [x] [Review][Patch] **P10 — `cli_runner` ignores `e2e_repo_root`; cwd is caller's `tmp_path`** [`tests/e2e/conftest.py:781-806`] — Fixture argument unused; spec AC4 line 166 says "Used to invoke `uv run` from a stable cwd." Caller passes `tmp_path` instead. Fragile: `uv run sdlc` discovers project from cwd; with `tmp_path` having no `pyproject.toml`, fragile to UV cache misses. Fix: either remove `e2e_repo_root` arg, OR actually use it as `cwd` and have callers pass scenario `tmp_path` via env/arg.
- [x] [Review][Patch] **P11 — `golden_dir` fixture hard-coded to `walking_skeleton`** [`tests/e2e/cli/conftest.py:344-347`] — Spec AC4 line 172 says "Resolved from `request.node.nodeid` + the scenario name embedded in the test param." Diff hard-codes "walking_skeleton". Won't generalize. `test_walking_skeleton_goldens.py` doesn't actually use this fixture (computes `_SCENARIO_DIR` inline) — dead-but-wrong code. Fix: implement nodeid-based resolution OR remove the dead fixture.
- [x] [Review][Patch] **P12 — `mock_runtime_factory` session cache has no reset/invalidation** [`tests/e2e/pipeline/conftest.py:1080-1086`] — `scope="session"` + path-keyed. If a test mutates runtime state, subsequent tests inherit. Mock-responses YAML edits during a session yield stale cached runtime. Fix: include mtime/sha of `mock_responses/` in cache key, OR change scope to `function`/`module`, OR document stateless contract.
- [x] [Review][Patch] **P13 — Anti-tautology suite has structural gaps** [`tests/e2e/test_harness_anti_tautology.py`] — Missing mutation-receipt tests for: (a) `state_sha256` golden corruption; (b) `stderr` golden corruption; (c) pipeline goldens corruption (`specialist_invocations.json`, `hook_chain_order.json`, `signoff_hashes.json`, `final_journal_sha256`); (d) outright golden file deletion (vs corruption). Fix: add four mutation tests mirroring the existing pattern.
- [x] [Review][Patch] **P14 — Empty/whitespace-only journal hashes inconsistently** [`tests/e2e/cli/conftest.py:306-327` + `:430-433`] — `_journal_has_content` uses `stat().st_size > 0`. If journal exists with whitespace-only content, `_hash_journal_no_ts` returns `sha256(b"")` instead of `<no-journal>\n` sentinel. Fix: normalize — if journal has zero non-blank JSON entries, use sentinel.
- [x] [Review][Patch] **P15 — Anti-tautology imports may fail at collection time** [`tests/e2e/test_harness_anti_tautology.py:1386-1391`] — `from e2e.cli.conftest import ...` requires `tests/` on `sys.path`. Diff's `mypy_path = ["src", "tests"]` is mypy-only. If pytest rootdir doesn't add `tests/`, imports fail at collection — all 9 tests silently never run. Fix: add `tests/__init__.py` (or rely on pytest rootdir conftest with explicit path), and run `pytest --collect-only tests/e2e/` to verify collection.
- [x] [Review][Patch] **P16 — Malformed/non-dict journal entries raise cryptic errors** [`tests/e2e/cli/conftest.py:314-326`] — `json.loads` on bad lines raises bare `JSONDecodeError`; non-dict entries raise `AttributeError` on `entry.pop("ts")`. No actionable hint to the test author. Fix: wrap with explicit error and raise with regeneration hint.
- [x] [Review][Patch] **P17 — Anti-tautology tests don't fully clean `scenario_dir` between phases** [`tests/e2e/test_harness_anti_tautology.py:1419-1425, 1610-1639`] — `shutil.copytree` on existing dir doesn't clear stale goldens; `test_update_goldens_cannot_mask` reuses `scenario_dir` without resetting between subtests. If pytest reorders/reruns, cross-test state leaks. Fix: `rmtree(scenario_dir, ignore_errors=True)` + `copytree`; reset between subtests.
- [x] [Review][Patch] **P18 — `asyncio.run` may fail under `pytest-asyncio`** [`tests/e2e/pipeline/conftest.py:1125`] — Raises `RuntimeError: asyncio.run cannot be called from running event loop` if pytest-asyncio is active (or future plugin compat). Fix: detect running loop; use `asyncio.new_event_loop()` defensively or wrap with `asyncio.run` only when no loop is active.
- [x] [Review][Patch] **P19 — `schema_version: 1` declared but never read** [`tests/e2e/cli/fixtures/walking_skeleton/commands.yaml:1` + `tests/e2e/pipeline/fixtures/happy_path_smoke/pipeline.yaml:1`] — Either enforce (`assert spec.get("schema_version") == 1, "schema_version mismatch"`) or drop the field. Currently theatre.
- [x] [Review][Patch] **P20 — `request.fspath` deprecated in pytest 8+** [`tests/e2e/cli/conftest.py:344-347`] — Couples to P11; fix together by either removing the dead `golden_dir` fixture or modernizing to `request.path`.
- [x] [Review][Patch] **P21 — Missing `mock_responses/` directory raises cryptic error** [`tests/e2e/pipeline/conftest.py:1083`] — If scenario has typo or no `mock_responses/`, MockAIRuntime constructor emits cryptic error far from author's mistake. Fix: pre-check `mock_dir.exists()` and raise `FileNotFoundError` with hint.
- [x] [Review][Patch] **P22 — `03_status` not separately Windows-runnable** [`tests/e2e/cli/test_walking_skeleton_goldens.py:653-654, 680`] — Spec AC5.4 says "Windows runs subset goldens (`init`, `status` non-scan) successfully". `_SKIP_WIN32` decorates the full sequence test; only `init`-only test bypasses it. `03_status` isn't separately runnable on Windows. Fix: split into per-command tests so Windows can run init + status (skip scan).
- [x] [Review][Patch] **P23 — Sanitized env allow-list misses Windows + macOS-locale + PYTHONPATH essentials** [`tests/e2e/conftest.py:757-778`] — Misses `SYSTEMROOT`/`PATHEXT`/`COMSPEC`/`APPDATA` on Windows; `C.UTF-8` may be unavailable on macOS (only `en_US.UTF-8`). With cwd = `tmp_path`, no `PYTHONPATH`, `uv run` discovery is fragile. Fix: extend allow-list per-platform; locale fallback; pair with P10's cwd fix.
- [x] [Review][Patch] **P24 — Amend spec AC2.3/AC5.1 + tighten `_normalize_timestamps` regex** [`docs/sprints/...` story spec + `tests/e2e/conftest.py:830-841`] — _Resolution of D1._ (a) Edit spec AC2.3/AC5.1 to formally sanction `ts` normalization on stdout/stderr (currently the spec forbids the implicit time-freeze hook); (b) tighten the regex to anchor expected formats and exclude false positives — cover `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DDTHH:MM:SS`, fractional seconds (`\.\d+`), tz suffix (`[+-]\d{2}:?\d{2}` and `Z`); (c) optionally restrict to lines starting with the timestamp (anchor with `\b` or `^\s*`) so an epic title containing a date doesn't match.
- [x] [Review][Patch] **P25 — Add `test_update_goldens_replay_disagreement_detected` (spec AC6.3 semantics)** [`tests/e2e/test_harness_anti_tautology.py`] — _Resolution of D2._ Add a second anti-tautology test that: (a) runs the harness once with `--update-goldens` against a scenario where production code is non-deterministic between two runs (e.g., a deliberate scenario whose CLI emits a non-stripped randomized line); (b) asserts goldens were rewritten; (c) asserts a subsequent (non-update) run STILL FAILS because the second run differs from the just-captured golden. This is orthogonal to existing `test_update_goldens_cannot_mask_semantic_regression` (manual post-corruption); both stay.
- [x] [Review][Patch] **P26 — Update spec AC2.3/AC3.3 to reality + reconcile Tier-2 path** [story spec + `tests/e2e/pipeline/conftest.py:1132`] — _Resolution of D3._ (a) Edit spec AC2.3/AC3.3 to use `.claude/state/journal.log` + `state.json` (matches actual state-write code in `src/sdlc/state/*`); (b) change Tier-2 `final_journal_path` from `tmp_path / ".sdlc" / "state" / "journal.jsonl"` to `tmp_path / ".claude" / "state" / "journal.log"` so when 2A.3 lands a real journal-writing dispatcher, Tier-2 sees it. Add a one-line comment at the path constant citing the divergence-resolution.
- [x] [Review][Patch] **P27 — Add D-decision note to Change Log for `pyproject.toml mypy_path` deviation** [story spec `## Change Log` section] — _Resolution of D4._ Append a single Change Log line: `D-decision: mypy_path edit (src + tests) was a sanctioned deviation from Dev Notes line 302 — required for mypy to resolve e2e.* test imports. Owner: revisit if a different type-resolution path becomes preferable.` No spec amendment.
- [x] [Review][Patch] **P28 — Edit spec AC5.1/AC5.5 to formalize journal-vs-state asymmetry** [story spec] — _Resolution of D5._ Rewrite AC5.1 to scope re-canonicalization to the **journal** only ("Journal hashes re-canonicalize without `ts`; computed in test code"). Rewrite AC5.5 to scope raw-bytes hashing to **state.json** only ("State.json hash is sha256 of raw bytes-on-disk; NOT re-canonicalized in test code, since `state.json` contains no timestamps"). The contradiction disappears because the two ACs now address disjoint artifacts.

#### Defer

- [x] [Review][Defer] **W1 — `--update-goldens` writes back into source-tree `scenario_dir` (non-hermetic)** [`tests/e2e/cli/test_walking_skeleton_goldens.py:644`] — deferred, by design. Spec ("authors regenerate goldens via `--update-goldens`") explicitly requires write-back into the scenario dir. Read-only CI is covered by P1 (CI never passes the flag).
- [x] [Review][Defer] **W2 — `MockAIRuntime` constructor signature/error-format unverified** [`tests/e2e/test_harness_anti_tautology.py:1556-1567, 1581-1586`] — deferred, no current break. The 9 passing tests demonstrate construction works; tighten if signature/error format ever drifts.
- [x] [Review][Defer] **W3 — No positive stderr coverage in walking_skeleton scenario** [`tests/e2e/cli/fixtures/walking_skeleton/goldens/*.stderr`] — deferred, scope. Walking_skeleton CLI emits no stderr by design; positive stderr coverage requires a distinct scenario (e.g., `error_paths`). Plan for Story 2A.x or a dedicated negative-path scenario.
- [x] [Review][Defer] **W4 — No completeness check on per-command golden set (5 files × N commands)** — deferred, tooling concern. Adding/removing commands risks orphan/missing goldens with no mechanical guard. Add a meta-test walking `commands.yaml × command_id × {stdout,stderr,exit,journal_sha256,state_sha256}` later.
- [x] [Review][Defer] **W5 — `sprint-status.yaml` / ADR-027 status flipped in same PR as implementation** [`_bmad-output/implementation-artifacts/sprint-status.yaml:20`, `docs/decisions/ADR-027-e2e-test-framework-strategy.md:42`] — deferred, procedural pattern. Status-by-fiat IS the BMad workflow (dev → review, then code-review → done).
- [x] [Review][Defer] **W6 — `--update-goldens` write under xdist parallel may race** [`tests/e2e/pipeline/conftest.py:1182-1185`] — deferred, dev-only path. `--update-goldens` is a developer regeneration step, typically not run under xdist. Document; revisit if it ever runs concurrently.
- [x] [Review][Defer] **W7 — `assert_goldens` extra `tmp_path` parameter (signature drift)** [`tests/e2e/cli/conftest.py:393-400`] — deferred, couples to D1. Spec AC4 line 173 signature omits `tmp_path`; needed by `_normalize_paths`. If D1 resolves by removing stdout timestamp normalization, this signature may need a re-look.



### Critical context — DO NOT skip

This story IS the test infrastructure for all of Epic 2A. **A bug here ships invisibly in 19 downstream stories.** Three rules:

1. **No production-code edits unless absolutely necessary.** This story is test-infra. The only sanctioned production edit is flipping ADR-027 status `Proposed → Accepted`. If you find yourself editing `src/sdlc/`, stop and reconsider — almost certainly you've hit a missing seam that should be a follow-up debt item, not a 2A.0 expansion.
2. **The anti-tautology tests (AC6, Task 6) are the most important deliverable.** They are what makes this harness immune to Pattern 1. Skipping or weakening them defeats the entire story.
3. **Bootstrap goldens via `--update-goldens` is a one-way valve in 2A.0.** After bootstrap, every subsequent change to a golden requires a dev to: (a) explain WHY in the PR Change Log, (b) get it through review-A. Drift via `--update-goldens` without explanation is the #1 way this harness rots.

### What this story IS NOT

- It is NOT the full Epic 2A specialist-invocation contract (that arrives in Story 2A.3 — dispatcher).
- It is NOT a hook-chain test (that arrives in Story 2A.4 — pre-write hooks).
- It is NOT a real-Claude pipeline (Tier-3, Epic 2B Story 2B.3).
- It is NOT a property/Hypothesis-based harness (those live under `tests/property/` and stay there).
- It does NOT replace the existing narrow integration tests under `tests/integration/test_*_e2e.py` — those continue to exist for now. Future stories MAY migrate selected ones into Tier-1, but that migration is NOT 2A.0's scope. Document the existing tests' status in `tests/e2e/README.md` ("preexisting; coexists with new tier discipline; migration is per-story choice").

### Architecture compliance

- **Module boundaries (Architecture §1073–§1112).** Test code under `tests/e2e/` MAY import from public surfaces only: `sdlc.runtime` (ABC + Mock), `sdlc.errors`, `sdlc.contracts`. MUST NOT import from `sdlc.cli.*` internals (use subprocess for Tier-1) or from `sdlc.engine`/`sdlc.dispatcher` until those modules' public seams stabilize (post-2A.3). Tier-1 is fully subprocess-driven; Tier-2 imports the runtime ABC and that is the entire production surface contact point in 2A.0.
- **Test organization (Architecture §682–§702).** New layout `tests/e2e/cli/` and `tests/e2e/pipeline/` extends the architecture's `tests/e2e/` plan (Architecture §690 explicitly anticipates `tests/e2e/fixtures/` and `tests/e2e/test_<scenario>.py`). The tier sub-directories are an Epic 2A refinement — document this evolution in `tests/e2e/README.md` so future readers see the link to Architecture §682–§702.
- **JSON canonicalization (Architecture §496–§515, Pattern §3).** All JSON goldens use the canonicalization rule from Story 1.10 / Story 1.21 verbatim. Do NOT introduce a different canonicalization in test code — copy from `sdlc.journal._canonical` if needed (already a public-ish module per Story 1.10).
- **Atomic-write protocol (Architecture §569–§589).** The harness reads `state/active.json` and `state/journal.jsonl` AFTER each command — both files are produced atomically by the writers. Reading them mid-write is impossible because the harness is sequential per-command (no concurrency in 2A.0).
- **Pydantic strict-mode (ADR-025).** Any pydantic model authored in test code (`PipelineObservation` is a `dataclass`, not pydantic, on purpose to dodge this) follows ADR-025: `extra="forbid"`, `frozen=True`, `Field(strict=True)` on numerics. If unsure, use `@dataclass(frozen=True)` instead.
- **Cold-start budget (Architecture §488–§494).** Tier-1 tests fire `uv run sdlc <cmd>` in subprocess, paying the cold-start cost per invocation. The seed scenario has 3 commands → ~600ms minimum cold-start (200ms × 3). This is acceptable for 2A.0; future scenarios with > 10 commands SHOULD be flagged for consideration of in-process invocation via `typer.testing.CliRunner` (NOT done in 2A.0 — subprocess gives true OS-level isolation that `CliRunner` cannot match for filesystem-touching commands).

### Library / framework requirements

- **pytest** ≥ already pinned via `pyproject.toml`. No version bump needed.
- **PyYAML** ≥ already pinned (used by `MockAIRuntime`). Use the same version constraint; do NOT add a new YAML library.
- **No new dependencies introduced.** If you find yourself reaching for `pytest-snapshot`, `syrupy`, or similar — stop. ADR-027 §"Alternatives Considered" §C explicitly rejects external snapshot libraries; pytest-only goldens are the decision.
- **`subprocess.run` is the only way Tier-1 invokes the CLI.** Do NOT use `typer.testing.CliRunner` — see cold-start note above.
- **`asyncio.run` is the standard entry for Tier-2.** `pytest-asyncio` is NOT used (the runner-fixture pattern encapsulates the loop; per AC4 pipeline runner contract).
- **Python ≥ 3.10** per `.python-version`. Use the modern `from __future__ import annotations` + structural pattern matching as needed; mypy strict is the floor.

### File structure requirements

The exact tree in AC1 is the target. Mirrors:
- `tests/contract_snapshots/v1/` (Story 1.21) — fixture-as-data layout.
- `tests/integration/_abstraction_adequacy_helpers.py` (Story 1.13) — private helper module pattern; copy when 2A.0 grows past file-size cap.
- `tests/fixtures/mock_responses/` (Story 1.13) — YAML fixture pattern.

### Testing requirements

- All tests under `tests/e2e/` MUST be marked `@pytest.mark.e2e` (declared in `pyproject.toml:218`).
- Coverage: ≥ 90% repo-wide MUST hold. Tier-1 tests contribute coverage to existing CLI modules indirectly (subprocess invocation IS covered because `--cov` measures all process invocations against `src/sdlc/`); Tier-2 tests contribute coverage to `src/sdlc/runtime/mock.py` and `src/sdlc/errors/` directly. The placeholder `engine.dispatch_panel_smoke` shim is test-only code and does NOT count toward production coverage.
- The three anti-tautology tests (Task 6) are NOT placebos — manually break each invariant once during dev to confirm the test catches it. Document the manual verification in the PR Change Log: `"Manually verified anti-tautology tests by [byte-flip / exit-bump / hash-mut] — each failed as expected."`
- The harness MUST work in two CI contexts: (a) PR CI (Linux ubuntu-latest, all green); (b) the existing matrix (if any) per `.github/workflows/ci.yml` — verify by reading that file.

### Previous-story intelligence — what to copy + what to avoid

**Copy from Story 1.13 (`MockAIRuntime`):**
- The `_NoDuplicateKeysLoader` pattern (`src/sdlc/runtime/mock.py:68–103`) — copy-paste into `tests/e2e/cli/conftest.py` for `commands.yaml` + `tests/e2e/pipeline/conftest.py` for `pipeline.yaml`. Do NOT extract a shared helper in 2A.0.
- The `_load_fixtures` fail-loud pattern (`src/sdlc/runtime/mock.py:191–218`) — every malformed input raises with file path + key context. Mirror this in your YAML loaders.

**Copy from Story 1.16 (`sdlc init` E2E):**
- The `subprocess.run(["uv", "run", ...])` shape (`tests/integration/test_walking_skeleton_e2e.py:25–33`).
- The `_SKIP_NO_UV` + `_SKIP_WIN32` skip-marker pattern.
- The exit-code assertion idiom: `assert r.returncode == 0, f"... failed:\nstdout={r.stdout}\nstderr={r.stderr}"`.

**Copy from Story 1.21 (Wire-format snapshots):**
- The verify/update CLI flag pattern (`scripts/freeze_wireformat_snapshots.py`'s `--check` / `--write`). Adapt to `pytest --update-goldens` (pytest plugin, not standalone script).
- The "drift error message includes action" pattern: `"<diff>\naction: <exact command to fix>"`.
- The `tuple` (NOT `dict`) for ordered iteration — `commands.yaml` should preserve declared order.

**AVOID (failure modes from Epic 1 retro):**
- **Pattern 1 — Tautological tests.** AC6 directly addresses this. Do NOT skip Task 6.
- **Pattern 2 — POSIX-only sprawl.** When a Tier-1 command is POSIX-only, mark it skip on Windows AT THE TEST LEVEL — do NOT add new `mypy.overrides` or `coverage.omit` entries.
- **Pattern 4 — Pydantic lax coercion.** Use `@dataclass(frozen=True)` for `PipelineObservation` to dodge the issue; if pydantic is genuinely needed, follow ADR-025.
- **Pattern 6 — Linter AST blind spots.** This story does NOT extend any AST linter. Stay out of `scripts/check_*.py`.

### Git intelligence — recent commits

- `97bdd5e chore(epic-2a-prep): sprint planning — retro outputs, 3 ADRs, Story 2A.0 E2E harness, CONTRIBUTING` — your direct precursor. ADR-025/026/027 + CONTRIBUTING.md edits live here.
- `cb60d3f chore(1.21): apply code-review patches — 24 fixes, 5 deferred, 4 dismissed` — Story 1.21 final form. Cite when referencing wire-format lock.
- `d2bde81 feat(1.21): wire-format v1 lock ceremony — 5 JSON-Schema snapshots + dual-gate enforcement` — the canonical example for "snapshot harness with `--check` / `--write`". Read its `scripts/freeze_wireformat_snapshots.py` before designing `--update-goldens`.
- `b12f033 feat(1.20): implement rebuild-state command and recovery prompt (FR35)` — `sdlc rebuild-state` is in scope as a future Tier-1 scenario; not in 2A.0 seed scope.

### Project structure notes

- New tree at `tests/e2e/` extends Architecture §1003–§1016 layout. The architecture document showed `tests/e2e/test_<scenario>.py` flat; 2A.0 introduces tier sub-dirs `cli/` and `pipeline/`. This is a documented refinement (cite in `tests/e2e/README.md`); the architecture doc itself is NOT edited in 2A.0 (architectural-doc edits are out of scope; sprint-planning will reconcile if/when needed).
- No conflicts with existing `tests/integration/test_*_e2e.py` — those continue to exist; their relationship to Tier-1 is "ancestral, coexists, may migrate per-story" (document in `tests/e2e/README.md`).
- The seed Tier-1 scenario `walking_skeleton` overlaps semantically with `tests/integration/test_walking_skeleton_e2e.py`. Intentional — proves the new harness reproduces the integration test's behavior at byte-level granularity. Do NOT delete the integration test in 2A.0.

### References

- [ADR-027 — E2E Test Framework Strategy](docs/decisions/ADR-027-e2e-test-framework-strategy.md) — the load-bearing decision document.
- [ADR-016 — AIRuntime ABC + MockAIRuntime](docs/decisions/ADR-016-airuntime-abc-and-mock-implementation.md) — ground-truth for Tier-2 mock policy.
- [ADR-024 — Wire-format v1 Lock](docs/decisions/ADR-024-wire-format-v1-lock.md) — JSON canonicalization rule reference.
- [ADR-025 — Pydantic strict-mode default](docs/decisions/ADR-025-pydantic-strict-mode-default.md) — pydantic discipline (if used).
- [ADR-026 — TDD-first + chunked review](docs/decisions/ADR-026-tdd-first-chunked-review-workflow.md) — review gate.
- [CONTRIBUTING.md §1, §3, §4, §5, §6](CONTRIBUTING.md) — quality gate, worktree, review labels, decision protocol, PR template.
- [Epic 1 Retrospective 2026-05-09](_bmad-output/implementation-artifacts/epic-1-retro-2026-05-09.md) — §3 Pattern 1 (tautological tests) + §5.1 Action A3 (this story's mandate) + §6.4 DAG (this story's blocking position).
- [Architecture §682–§702 (Test organization)](_bmad-output/planning-artifacts/architecture.md) — test layout convention; this story extends it.
- [Architecture §496–§515 (JSON canonicalization)](_bmad-output/planning-artifacts/architecture.md) — golden canonicalization.
- [Architecture §1003–§1016 (Tests directory tree)](_bmad-output/planning-artifacts/architecture.md) — `tests/e2e/` layout origin.
- [Architecture §1073–§1112 (Module boundaries)](_bmad-output/planning-artifacts/architecture.md) — what test code may import.
- [`src/sdlc/runtime/mock.py`](src/sdlc/runtime/mock.py) — MockAIRuntime; pattern source for YAML-fixture loading.
- [`src/sdlc/runtime/abc.py`](src/sdlc/runtime/abc.py) — AIRuntime ABC; consume via this surface only.
- [`tests/integration/test_walking_skeleton_e2e.py`](tests/integration/test_walking_skeleton_e2e.py) — pattern source for `subprocess.run` + skip markers + walking-skeleton command sequence.
- [`tests/contracts/test_wireformat_immutability.py`](tests/contracts/test_wireformat_immutability.py) — pattern source for byte-stable golden assertion + drift error messages.
- [`scripts/freeze_wireformat_snapshots.py`](scripts/freeze_wireformat_snapshots.py) — pattern source for `--check`/`--write` flag design (adapt to `--update-goldens`).
- [`pyproject.toml:212–219`](pyproject.toml) — pytest markers including `e2e`.
- [`tests/conftest.py`](tests/conftest.py) — minimal repo-root sys.path setup; do not duplicate.
- [`tests/fixtures/mock_responses/_smoke.yaml`](tests/fixtures/mock_responses/_smoke.yaml) — canonical example for MockAIRuntime YAML record shape.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 — dev-story implementation (2026-05-10).

### Debug Log References

- ModuleNotFoundError `tests.e2e.*` → fixed by correcting all imports to `e2e.*` (pytest `--import-mode=prepend` makes `tests/` the sys.path root, not the project root).
- Wrong state paths `.sdlc/state/journal.jsonl` → actual paths are `.claude/state/journal.log` and `.claude/state/state.json`; discovered by running `sdlc init` in tmp dir.
- `cli_runner` fixture not found in anti-tautology tests → moved `cli_runner` + `_build_sanitized_env` to `tests/e2e/conftest.py` (parent conftest) so both `cli/` and the parent-level anti-tautology test can access it.
- `UnicodeDecodeError` reading byte-flipped golden → extracted `_compare_one_golden` helper; wraps read in try/except and returns a named error string.
- Timestamp in `03_status.stdout` non-deterministic → added `_normalize_timestamps` regex helper replacing `YYYY-MM-DD HH:MM:SS +ZZ` with `<TIMESTAMP>`.
- Empty `journal.log` after `init` → added `and journal_path.stat().st_size > 0` guard before hashing.
- `mypy_path` missing `tests/` → added `"tests"` to `mypy_path` list in `pyproject.toml`.
- `yaml.load` returning `Any` flagged by mypy `no-any-return` → assigned to typed local variable first.
- `spec["commands"]` typed as `object` (not iterable) → wrapped with `cast(list[dict[str, object]], ...)` at all usage sites.
- C901 complexity on `assert_goldens` → extracted `_compare_one_golden` private helper (also fixed the UnicodeDecodeError issue simultaneously).

### Completion Notes List

- All 8 tasks completed; 9 e2e tests pass (`pytest tests/e2e/ -q -m e2e`).
- Coverage retained at 93.50% ≥ 93% floor.
- Anti-tautology tests manually verified: byte-flip → `UnicodeDecodeError` caught and surfaced as AssertionError naming `01_init.stdout`; exit bump → AssertionError names `01_init.exit`; hash corruption → AssertionError names `02_scan.journal_sha256`.
- Walking skeleton goldens bootstrapped via `--update-goldens` and inspected: init creates 5 files in `.claude/state/` + 3 phase dirs; scan writes journal entries; status emits `<TIMESTAMP>` sentinel.
- Tier-2 smoke scenario uses `dispatch_panel_smoke` shim (Story 2A.3 replaces it); 4 goldens locked: `[]` for signoffs/hooks, single `_smoke` specialist invocation.
- ADR-027 status flipped `Proposed → Accepted (2026-05-10)`.
- `pyproject.toml` mypy_path extended to `["src", "tests"]` — only change to production config.

### File List

- `tests/e2e/__init__.py` (new)
- `tests/e2e/conftest.py` (new)
- `tests/e2e/README.md` (new)
- `tests/e2e/test_harness_anti_tautology.py` (new)
- `tests/e2e/cli/__init__.py` (new)
- `tests/e2e/cli/conftest.py` (new)
- `tests/e2e/cli/README.md` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/commands.yaml` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/README.md` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/01_init.stdout` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/01_init.stderr` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/01_init.exit` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/01_init.journal_sha256` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/01_init.state_sha256` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/02_scan.stdout` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/02_scan.stderr` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/02_scan.exit` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/02_scan.journal_sha256` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/02_scan.state_sha256` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/03_status.stdout` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/03_status.stderr` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/03_status.exit` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/03_status.journal_sha256` (new)
- `tests/e2e/cli/fixtures/walking_skeleton/goldens/03_status.state_sha256` (new)
- `tests/e2e/cli/test_walking_skeleton_goldens.py` (new)
- `tests/e2e/pipeline/__init__.py` (new)
- `tests/e2e/pipeline/conftest.py` (new)
- `tests/e2e/pipeline/README.md` (new)
- `tests/e2e/pipeline/fixtures/happy_path_smoke/pipeline.yaml` (new)
- `tests/e2e/pipeline/fixtures/happy_path_smoke/README.md` (new)
- `tests/e2e/pipeline/fixtures/happy_path_smoke/mock_responses/_smoke.yaml` (new)
- `tests/e2e/pipeline/fixtures/happy_path_smoke/goldens/final_journal_sha256` (new)
- `tests/e2e/pipeline/fixtures/happy_path_smoke/goldens/signoff_hashes.json` (new)
- `tests/e2e/pipeline/fixtures/happy_path_smoke/goldens/hook_chain_order.json` (new)
- `tests/e2e/pipeline/fixtures/happy_path_smoke/goldens/specialist_invocations.json` (new)
- `tests/e2e/pipeline/test_happy_path_smoke.py` (new)
- `docs/decisions/ADR-027-e2e-test-framework-strategy.md` (modified — status Proposed→Accepted)
- `pyproject.toml` (modified — mypy_path extended to include "tests")

## Change Log

- 2026-05-10: Story implemented (claude-sonnet-4-6). Two-tier harness landed: Tier-1 CLI golden harness (walking_skeleton scenario, 15 golden files, 2 tests) + Tier-2 pipeline harness (happy_path_smoke scenario, 4 goldens, 2 tests) + 5 anti-tautology tests. ADR-027 status flipped Proposed→Accepted. All quality gates pass: ruff clean, mypy strict zero errors, 9 e2e tests pass, coverage 93.50%. Manually verified all 3 anti-tautology mutation receipts fail as expected. pyproject.toml mypy_path extended to ["src", "tests"].
- 2026-05-10: Code review run (Blind Hunter + Edge Case Hunter + Acceptance Auditor — 3 layers, 41 raw findings). 5 decision-needed resolved (D1-D5), 23 + 5 = 28 patches applied (P1-P28), 7 deferred (W1-W7), 6 dismissed.
- 2026-05-10: **D-decision (resolution of D4)** — `pyproject.toml mypy_path = ["src", "tests"]` is a sanctioned deviation from Dev Notes line 302 ("only ADR-027 status flip is sanctioned"). Required for mypy --strict to resolve `e2e.*` imports under `tests/`. Risk: low — change is type-checker-only, has no runtime effect, and is reversible (alternative: `[[tool.mypy.overrides]] module = ["e2e.*"]`). **Owner:** revisit if a different type-resolution path becomes preferable.
- 2026-05-10: **Spec amendments shipping with patches** — AC2.3/AC5.1 amended to formally sanction stdout/stderr timestamp normalization (P24/D1). AC2.3/AC3.3 path fields corrected from `.sdlc/state/journal.jsonl + active.json` to `.claude/state/journal.log + state.json` (P26/D3 — match the actual state writer). AC5.1/AC5.5 split by artifact: journals re-canonicalize without `ts`, state.json hashes raw bytes (P28/D5 — resolves prior internal contradiction).
