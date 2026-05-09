# ADR-018: Engine Scanner Skeleton — Pure Read, Idempotent, Perf-Gated

**Status:** Accepted (2026-05-09, Story 1.15)

## Context

FR3 (`sdlc scan`) is a v1 capability (PRD §117, Architecture §1133). Decision A4 (Architecture §339) makes `scan() → dispatch_next() → STOP_check()` the auto-loop's atomic step — and explicitly names `scan()` as "a pure function of disk state." Decision B5 (Architecture §349) establishes `state.json` as a projection; Story 1.15 is the artifact-tree projection counterpart to Story 1.12's journal-based projection.

NFR-PERF-1 mandates `scan < 2 s` on a 200-story / 1000-task corpus. Without a CI regression gate, a future change (e.g. `pathlib.iterdir` behavior, JSON parsing change, `sorted()` overhead) could silently regress performance before being caught in production. A pytest-benchmark gate enforcing both cold-start (`< 2 s`) and warm-cache (`< 100 ms`) budgets closes that gap.

Story 1.14 uses an inline scan-stub (`initial_state = State(...)`) in the abstraction-adequacy integration test. Story 1.15 replaces that stub with `engine.scanner.scan(tmp_path)`, advancing the pipeline fidelity while keeping the golden-bytes contract. This stub-replacement causes `expected_state.json` to drift (new `phase`, `stories`, `tasks` keys) — a named, deliberate goldens regen.

## Decision

1. `engine.scanner.scan(project_root: Path) -> State` is a **pure function**: zero filesystem writes, zero journal appends, zero subprocess calls, zero stdout/stderr writes, zero network I/O, zero `os.environ` reads. Reads from `project_root` are allowed. This shape preserves Story 1.14's 1-line stub-replacement contract, keeps Story 1.20's `rebuild-state` free of write-suppression flags, and halves unit-test setup overhead.

2. The scanner is the **v1 artifact-tree read path**; `cli/scan.py` (Story 1.17) is the write wrapper. Story 1.17 calls `scan()` then `write_state_atomic_sync()` + `journal.append_sync()`. The scanner itself never touches state.json or journal.log.

3. `State` model is extended **additively** with three new fields (`phase: int = 1`, `stories: dict[str, Any]`, `tasks: dict[str, Any]`). `schema_version` stays at `1` because pydantic v2 default-supplies missing optional fields when validating older `state.json` files. The schema_version bump is deferred to Story 1.21's wire-format-v1 lock ceremony.

4. `MODULE_DEPS["engine"].depends_on` widens to include `"ids"`. The scanner uses `parse_epic_id`, `parse_story_id`, `parse_task_id`, `EPIC_ID_REGEX`, `STORY_ID_REGEX`, and `TASK_ID_REGEX` from `sdlc.ids`. Without this boundary widening the `boundary-validator` pre-commit hook would block scanner's import. No other `engine→ids` API surface ships in v1.

5. **NFR-PERF-1** is enforced by a dedicated `benchmarks` CI job (ubuntu-latest, python 3.12) running `pytest-benchmark` with:
   - Cold gate: `benchmark.pedantic(scan, args=(corpus,), iterations=1, rounds=5, warmup_rounds=0)` → mean `< 2.0 s`
   - Warm gate: pre-warm + `benchmark.pedantic(scan, args=(corpus,), iterations=10, rounds=5, warmup_rounds=2)` → mean `< 100 ms`
   - Corpus: 4 epics × 50 stories × 5 tasks = 1 204 JSON files scaffolded at runtime in `tmp_path` (NOT committed).

6. The scanner is **POSIX + Windows portable**. No `fcntl`, `O_APPEND`, parent-dir fsync, or any POSIX-only path. Architecture §573 carves POSIX-only at the WRITE layer; the read layer is portable. Strict numeric budget assertions fire only on Linux CI; Windows observes but does not gate.

7. Strict numeric budget assertions (`benchmark.stats.stats.mean < threshold`) are declared **in the test source** (not only in a benchmark report), making the gate visible to code reviewers without consulting CI artifacts.

## Alternatives Considered

- **`scan()` writes `state.json` directly** — rejected: couples the scanner to the atomic-write protocol; breaks Story 1.14's 1-line stub-replacement contract; forces Story 1.20's `rebuild-state` to add a write-suppression flag. Pure read-only is the cleaner contract.

- **Defer `State` model extension to Story 1.20** — rejected: Story 1.15's AC explicitly requires `phase`, `stories`, `tasks` in the returned State; the scanner walk produces stories and tasks — their container fields must exist. The extension is additive (no migration cost) and the natural place for it is the first consumer that produces a non-trivial State.

- **Commit the benchmark corpus under `tests/fixtures/scanner_corpus/`** — rejected: ~1 200 small JSON files inflate the repo by ~70 KB and create fixture-drift risk when artifact schema evolves. `_build_perf_corpus` in `tests/benchmark/conftest.py` rebuilds the corpus reproducibly from a clean checkout in < 30 s.

- **Stdlib `time.perf_counter()` for perf measurement** — rejected: per-developer and per-matrix-cell variance would dominate a tight 2 s / 100 ms budget. `pytest-benchmark`'s `pedantic(rounds=5)` reduces noise to `< 1 %` and produces CI-comparable statistics with no bespoke aggregation logic.

- **Benchmark runs on every `quality-gates` matrix cell** — rejected: 8 matrix cells × perf variance (3.10–3.13 `pathlib` micro-optimization profiles differ) = noisy gate. Single-cell `ubuntu-latest` python 3.12 is the determinism floor; other cells observe via `quality-gates` skips but do not gate.

- **Inline ID regex in scanner.py (avoid engine→ids dep)** — rejected: duplicates `ids/parsers.py` source of truth; would drift the moment Story 1.6's regexes tighten. The boundary widening is the canonical fix.

## Consequences

- **Story 1.14 goldens drift** on the first run after this story lands because `expected_state.json` now includes `"phase":1`, `"stories":{}`, `"tasks":{}`. Regen is deliberate: `_REGENERATE_GOLDENS=True` toggle in `tests/integration/test_abstraction_adequacy.py`, run on Linux, commit, flip back to `False`. The `tests/fixtures/abstraction_adequacy/README.md` regen-history block names the trigger.

- **Story 1.17's `cli/scan.py`** is a thin wrapper: `state = scan(project_root); write_state_atomic_sync(state, ...); journal.append_sync(je, ...)`. The engine work is fully closed by Story 1.15; 1.17's complexity is CLI flag handling (`--no-color`, `--json`).

- **Story 1.20's `rebuild-state`** reconciles the artifact-tree projection (this story) against the journal projection (Story 1.12). The two are deliberately decoupled: artifact-tree mutations after the journal's last entry produce a divergent State that 1.20 surfaces as a recovery prompt.

- **Additive State extension continues** through Stories 1.16-1.19 without schema_version bumps. Story 1.21's wire-format-v1 lock ceremony finalizes the schema. Until then, adding fields is mechanical (extend model + regenerate Story 1.14 goldens once).

- **Benchmark gate is a hard CI requirement**. PRs that regress scan mean time beyond the 2 s / 100 ms budget fail CI. The escape valve is removing the inline `assert` (NEVER do this; the assertion IS the gate). `--benchmark-compare-fail=mean:5%` is a supplementary flag available for advisory comparison against a stored baseline.

- **No migration required** for existing `state.json` files. Old files written under Story 1.10's minimal model (`schema_version=1, next_monotonic_seq=0, epics={}`) continue to validate against the extended model — pydantic v2 supplies `phase=1, stories={}, tasks={}` from field defaults. Migration becomes mandatory only when a NON-DEFAULTABLE field is added or a field type tightens.

## Revisit-by

Story 1.21 — wire-format v1 lock ceremony. At that point `schema_version=1` is frozen and all field additions require a schema bump + migration script. The perf budget should also be re-evaluated against the then-current corpus shape (Stories 2A / 2B may expand the artifact tree significantly).

## References

Architecture §117 (FR1-FR5 lifecycle), §339 (Decision A4 — pure-function auto-loop step), §349 (Decision B5 — state as projection), §388 (substrate roadmap), §489 (no print in engine/), §490-§494 (code-style invariants), §513 (canonical hash protocol), §573 (POSIX-only write layer boundary), §815 (engine/scanner.py spec), §1133 (FR3 → cli/scan.py + engine/scanner.py), §1407 (implementation timeline). PRD §FR3 (sdlc scan), §NFR-PERF-1 (< 2 s scan), §NFR-REL-5 (auto-loop is a pure function of disk state). ADR-013 (atomic state write protocol), ADR-014 (journal append-only), ADR-015 (state projection from journal — Story 1.12), ADR-017 (abstraction-adequacy CI contract — Story 1.14).
