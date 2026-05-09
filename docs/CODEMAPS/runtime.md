# CODEMAP: runtime/

Story 1.13 deliverables for `src/sdlc/runtime/`.

## Public API (`sdlc.runtime`)

| Symbol | File | Notes |
|---|---|---|
| `AIRuntime` | `runtime/abc.py` | Abstract base class; single `@abstractmethod dispatch` |
| `AgentResult` | `runtime/abc.py` | Frozen pydantic v2 model; 4 fields |
| `MockAIRuntime` | `runtime/mock.py` | YAML-driven deterministic mock; Story 1.13 |
| `MockMissError` | `sdlc.errors` | Re-exported via `sdlc.runtime` for ergonomics |
| `ClaudeAIRuntime` | *(Story 2B-1)* | Not yet implemented |

## Files

### `src/sdlc/runtime/__init__.py`
Re-exports `AIRuntime, AgentResult, MockAIRuntime, MockMissError` in semantic order.
`ClaudeAIRuntime` is NOT in `__all__` until Story 2B-1.

### `src/sdlc/runtime/abc.py`
- `AgentResult(BaseModel)` — frozen, extra=forbid, 4 fields
- `AIRuntime(ABC)` — single abstract async `dispatch(prompt, context) -> AgentResult`
- ≤80 LOC (AC1 budget)
- Cross-platform (no POSIX I/O)

### `src/sdlc/runtime/mock.py`
- `_Fixture(BaseModel)` — private YAML record schema
- `_hash_prompt(prompt) -> str` — pure function, sha256 prefix
- `_load_fixtures(fixtures_dir) -> dict` — pure eager-loader
- `MockAIRuntime(AIRuntime)` — construction loads all `*.yaml`; dispatch is O(1) dict lookup
- ≤200 LOC (AC2 budget)
- Cross-platform (PyYAML, pathlib, hashlib)

## Tests

| File | Covers |
|---|---|
| `tests/unit/runtime/test_abc.py` | AC1: AIRuntime ABC + AgentResult shape |
| `tests/unit/runtime/test_mock_loader.py` | AC2: YAML loading + error paths |
| `tests/unit/runtime/test_mock_dispatch.py` | AC2: dispatch hit/miss |
| `tests/unit/runtime/test_mock_determinism.py` | AC3: byte-identical results + subprocess hash stability |
| `tests/unit/test_runtime_import_via_abc_validator.py` | AC4: linter correctness |

## Fixtures

| Path | Purpose |
|---|---|
| `tests/fixtures/mock_responses/_smoke.yaml` | Smoke fixture for construction tests (`_smoke` step) |
| `tests/fixtures/mock_responses/README.md` | Fixture format documentation |
| `tests/fixtures/lint_negative/engine_imports_runtime_mock.py.txt` | Negative test: forbidden in engine/ |
| `tests/fixtures/lint_negative/dispatcher_imports_runtime_claude.py.txt` | Negative test: forbidden in dispatcher/ |
| `tests/fixtures/lint_negative/engine_imports_runtime_abc.py.txt` | Negative test: must use re-export |
| `tests/fixtures/lint_negative/cli_imports_runtime_mock.py.txt` | Forward-compat: cli permissive case |

## Scripts

| Path | Purpose |
|---|---|
| `scripts/check_runtime_import_via_abc.py` | AST-level ABC-only import enforcer (pre-commit hook) |

## Cross-links

- `docs/CODEMAPS/state.md` (Story 1.12) — `state/` module; runtime is independent
- `docs/CODEMAPS/journal.md` (Story 1.11) — `journal/` module; runtime is independent
- `docs/decisions/ADR-016-airuntime-abc-and-mock-implementation.md` — design rationale

## Module Dependencies

```
runtime/ depends_on: errors/, contracts/, concurrency/
runtime/ forbidden_from: engine/, dispatcher/, state/, journal/, cli/
```

(Declared at `scripts/check_module_boundaries.py:64-67`; unchanged from Story 1.4.)
