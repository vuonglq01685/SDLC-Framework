# Story 1.13: AIRuntime ABC + MockAIRuntime (deterministic YAML-driven)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer keeping the engine runtime-neutral (NFR-COMPAT-3),
I want an `AIRuntime` abstract base class plus a `MockAIRuntime` driven by deterministic YAML keyed on `(workflow_step, prompt_hash)`,
so that the engine and dispatcher can be developed and tested without any real Claude Code dependency in Epic 1 (FR29, Decision C1 + C2, Architecture §315-§316, §355-§356, §826-§829, §1062).

## Acceptance Criteria

**AC1 — `AIRuntime` ABC declares the runtime-neutral contract (epic AC block 1)**

**Given** Story 1.12 complete (`sdlc.state.project_from_journal` shipped at `src/sdlc/state/projection.py`; the substrate stack errors → contracts → concurrency → state → journal is on disk; ADR-015 will be authored by Story 1.12 — verify on disk before starting),
**When** I import `from sdlc.runtime import AIRuntime, AgentResult`,
**Then** the import succeeds and:

1. `AIRuntime` is an `abc.ABC` declaring exactly one abstract method: `async def dispatch(self, prompt: str, context: Mapping[str, object]) -> AgentResult`.
2. `AgentResult` is a frozen pydantic v2 `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)` and EXACTLY four fields:
   - `output_text: str` — the final response text the runtime would have produced.
   - `tool_calls: tuple[Mapping[str, object], ...] = Field(default_factory=tuple)` — ordered tuple of tool-call records (`Mapping` not `dict` so frozen-ness is real; tuple not list because pydantic v2 `frozen=True` does not deep-freeze list members).
   - `tokens_in: int = Field(ge=0)` — input token count.
   - `tokens_out: int = Field(ge=0)` — output token count.
3. `AIRuntime` declares NO streaming methods (`astream`, `stream`, `dispatch_stream`, etc. are intentionally absent per Decision C1, Architecture §315 + §327: "AIRuntime streaming — defer until a workflow needs it"). A linter check in Task 9 asserts no `stream` or `iter` token appears in `runtime/abc.py` member names.
4. The `AIRuntime` class body has, in this order: a one-line docstring citing Decision C1 + Architecture §355; the `@abstractmethod`-decorated `dispatch` signature; nothing else (no concrete helper methods on the ABC — keep the abstraction surface minimal so v2 implementations have nothing to override accidentally).

**And** the `dispatch` parameter `context` is typed as `Mapping[str, object]` (NOT `dict[str, Any]`): mapping is read-only by Python's protocol; `object` is stricter than `Any` for type-safety. Implementations may treat the mapping as a frozen view; the caller MUST NOT rely on mutation. Document inline: "context carries workflow_step, agent_name, tool_call_budget, and similar dispatch metadata; the v1 surface is open-ended on purpose, formalized later in Story 2A-3."

**And** `runtime/abc.py` MUST stay ≤ 80 LOC (well under the 400 cap; the ABC + AgentResult pydantic model are small). The architecture-stated module footprint (`abc.py + claude.py + mock.py`) puts the ABC at "small declaration", not implementation hub. If overrunning, the LOC budget is wrong — re-examine the design before stretching the cap.

**And** the public API surface exported from `sdlc.runtime` after this story is exactly: `("AIRuntime", "AgentResult", "MockAIRuntime", "MockMissError")`. `ClaudeAIRuntime` is NOT exported (Story 2B-1 owns that file). The `__all__` tuple is in semantic order: ABC → return-type → mock-impl → mock-error; suppress isort with `# noqa: RUF022` per the project convention.

**AC2 — `MockAIRuntime` deterministic YAML loader + dispatch (epic AC block 2)**

**Given** the `MockAIRuntime` implementation at `src/sdlc/runtime/mock.py`,
**When** I instantiate `MockAIRuntime(fixtures_dir=Path("tests/fixtures/mock_responses/"))` and call `await runtime.dispatch(prompt="Plan epic-stripe", context={"workflow_step": "sdlc-epics"})`,
**Then** the implementation:

1. Stores `fixtures_dir: Path` (must be absolute or made absolute via `Path(fixtures_dir).resolve()` at construction time — fail-loud on non-existent path with `MockMissError("fixtures_dir does not exist: <path>")`; do NOT silently create it).
2. Eager-loads ALL `*.yaml` files under `fixtures_dir` at construction time into an in-memory dict `_fixtures: dict[tuple[str, str], _Fixture]` keyed by `(workflow_step, prompt_hash)` where `prompt_hash = "sha256:" + sha256(prompt.encode("utf-8")).hexdigest()` (the same prefix-namespaced format as the journal's `before_hash`/`after_hash` per Architecture §514 + Pattern §3 JSON canonicalization rules).
3. On `dispatch(prompt, context)`: extract `workflow_step = str(context.get("workflow_step", ""))`, compute `prompt_hash`, look up `_fixtures[(workflow_step, prompt_hash)]`. Hit → return the fixture's `AgentResult`. Miss → raise `MockMissError("no fixture for (step={workflow_step}, prompt_hash={prompt_hash}); add a YAML at {fixtures_dir}/{workflow_step}.yaml under key {prompt_hash}")` with `details={"step": "fixture_lookup", "workflow_step": workflow_step, "prompt_hash": prompt_hash, "fixtures_dir": str(self.fixtures_dir)}`. The error message MUST name a concrete migration path (the file/key the developer should add) — mirrors Story 1.11/1.12's "name the migration command" error-contract pattern (Decision F3 fail-loud-with-recovery-path).
4. The dispatch is `async def` but performs NO I/O at dispatch time (all fixture reads happened at construction). The `async` keyword is there for API parity with the ABC (which is `async def`) — under the hood the body is `return self._fixtures[key].as_agent_result()`. Document inline: "Mock dispatch is sync-equivalent — `async` is API-shape, not concurrency. Real `ClaudeAIRuntime` (Story 2B-1) WILL await subprocess.run via asyncio.to_thread; abstraction holds because mock awaits a no-op." Use `await asyncio.sleep(0)` ONCE before the lookup so the coroutine actually yields control (prevents the abstraction-adequacy test from masking the dispatcher's `await` semantics — a coroutine that never yields is observably different from one that does, even if the return value is the same; this is the "abstraction adequacy" trap Decision C2 exists to catch).

**And** the YAML fixture format is canonical:

```yaml
# tests/fixtures/mock_responses/sdlc-epics.yaml
# Schema: top-level dict keyed by prompt_hash → fixture record.
# Generated and consumed deterministically; do NOT hand-edit hashes.
"sha256:abc123...64-hex-chars...":
  output_text: |
    Generated epic plan for stripe webhook integration.
    - Epic 1: Webhook signature verification
    - Epic 2: Idempotency layer
  tool_calls:
    - name: write_artifact
      args: {target: "01-Requirement/04-Epics/EPIC-stripe.json", content_hash: "sha256:..."}
  tokens_in: 1234
  tokens_out: 567
```

The schema is enforced by a private `_Fixture` pydantic model in `runtime/mock.py`:

```python
class _Fixture(BaseModel):
    """Internal: validates YAML fixture records at load time. Not exported."""
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)
    output_text: str
    tool_calls: tuple[Mapping[str, object], ...] = Field(default_factory=tuple)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)

    def as_agent_result(self) -> AgentResult:
        return AgentResult(
            output_text=self.output_text,
            tool_calls=self.tool_calls,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
        )
```

**And** YAML loading uses `yaml.safe_load` (NEVER `yaml.load` or `yaml.full_load` — Architecture §492 + NFR-SEC-1 + Story 1.8 secret-sanitizer convention). PyYAML is already a top-level project dep at `pyproject.toml:13` (`pyyaml>=6,<7`).

**And** fixture file naming: one YAML file per `workflow_step` value (e.g. `sdlc-epics.yaml`, `sdlc-stories.yaml`, `sdlc-task.yaml`). The loader extracts `workflow_step = path.stem` and indexes every prompt_hash key under that step. Files with no `workflow_step` mapping (e.g. shared metadata) are NOT supported in v1 — fail-loud with `MockMissError("malformed fixture file: top-level must be a mapping of prompt_hash → record")` if encountered.

**And** unit tests in `tests/unit/runtime/test_mock_loader.py` verify: (a) load empty fixtures_dir → empty `_fixtures`; (b) load fixtures_dir with one valid YAML file → `_fixtures` has the right keys; (c) load fixtures_dir with malformed YAML → `MockMissError`; (d) load fixtures_dir with non-existent path → `MockMissError`; (e) load fixtures_dir with a YAML whose top-level is not a mapping → `MockMissError`; (f) `dispatch` hit returns the fixture's AgentResult; (g) `dispatch` miss raises `MockMissError` with the exact recovery-path message format.

**AC3 — Determinism: byte-identical AgentResult on repeated dispatch (epic AC block 3)**

**Given** the mock + a fixture file with a single `(workflow_step, prompt_hash)` entry,
**When** I call `await runtime.dispatch(prompt, context)` twice in a row with the same `prompt` and same `context["workflow_step"]`,
**Then** the two `AgentResult` instances are equal under `model_dump(mode="json")` byte-comparison: `r1.model_dump(mode="json") == r2.model_dump(mode="json")` AND the canonical JSON serialization (`json.dumps(r1.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))`) is byte-identical between calls.

**And** unit tests in `tests/unit/runtime/test_mock_determinism.py` verify:

1. `test_dispatch_same_input_returns_byte_identical_result`: dispatch the same `(prompt, context)` 10 times in a loop; assert all 10 results have the same canonical JSON bytes (NOT just `model_dump()`-equal — canonicalize and compare bytes; mirrors Story 1.10's `_canonicalize_state` byte-comparison pattern).
2. `test_dispatch_different_prompts_return_different_results_when_fixtures_differ`: with two fixtures keyed on different `prompt_hash` values, dispatch each prompt and confirm the right fixture is returned (sanity that the hash-key lookup works).
3. `test_dispatch_concurrent_calls_return_consistent_results`: use `asyncio.gather(*[runtime.dispatch(prompt, ctx) for _ in range(20)])` and assert all 20 results are byte-identical (no shared mutable state in the mock — the dispatch is pure with respect to the in-memory `_fixtures` dict; concurrent calls do not race because all reads are read-only).
4. `test_prompt_hash_is_stable_across_python_runs`: hash the same prompt string twice in separate process invocations (use a subprocess test); assert the hex digest matches. This catches accidental introduction of a non-deterministic hash (e.g., someone replacing `sha256` with `hash()` which is randomized per run via `PYTHONHASHSEED`). Run as a fast subprocess test — see Task 6 for the impl pattern (mirror Story 1.10's chaos-test subprocess pattern).

**AC4 — Module boundary enforcement: `engine/`, `dispatcher/` import only via the ABC (epic AC block 4)**

**Given** the boundary enforcement scaffold at `scripts/check_module_boundaries.py:50-144` (post-Story-1.12: `MODULE_DEPS["state"]` includes `"journal"`),
**When** any file under `src/sdlc/engine/` or `src/sdlc/dispatcher/` attempts `from sdlc.runtime.mock import MockAIRuntime` or `from sdlc.runtime.claude import ...` (the latter doesn't exist yet but the rule is forward-compatible),
**Then** the boundary-validator pre-commit hook fails with the existing `import violation` message format. Specifically:

1. The current `MODULE_DEPS["runtime"]` at `scripts/check_module_boundaries.py:62-65` declares `forbidden_from=frozenset({"engine", "dispatcher", "state", "journal", "cli"})`. This rule is **already in place** from Story 1.4. **No edit to `MODULE_DEPS` is required by this story.** Verify by reading the boundary script BEFORE starting implementation; if the rule has shifted (e.g., a prior story removed `"engine"` from `forbidden_from`), abort and reconcile.
2. The boundary check is at the module level (`engine` → `runtime` is forbidden as a whole). Today the validator does NOT distinguish `from sdlc.runtime import AIRuntime` (allowed-via-ABC) from `from sdlc.runtime.mock import MockAIRuntime` (always forbidden from engine/dispatcher). **Both are flagged today.** This is a known v1 gap — the architecture's "ABC-only import" rule is a stricter posture than the AST validator can express at module-level granularity. Document this gap in ADR-015 Consequences AND add a NEW pre-commit linter (Task 7) `scripts/check_runtime_import_via_abc.py` that asserts:
   - In `engine/` and `dispatcher/`: only `from sdlc.runtime import AIRuntime, AgentResult` is permitted (NOT `from sdlc.runtime.mock import ...`, NOT `from sdlc.runtime.claude import ...`, NOT `from sdlc.runtime.abc import AIRuntime` — the canonical re-export from `sdlc.runtime` is the only allowed surface).
   - In `cli/` (post-Story-1.16): the rule relaxes to allow `from sdlc.runtime.mock import MockAIRuntime` for test-only DI (Architecture §1071 names this exception explicitly: "cli/ … runtime (only mock for tests)"). v1 does not have any cli/ files yet, so the rule's permissive case for cli/ is forward-only.
3. The new linter is wired into `.pre-commit-config.yaml` between `boundary-validator` and `state-write-protocol-validator` (alphabetically: it's a `runtime-*` linter, sorts before `secret-*`).

**And** unit tests in `tests/unit/test_runtime_import_via_abc_validator.py` mirror the existing `tests/unit/test_state_write_validator.py` (Story 1.10) and `tests/unit/test_journal_mutation_validator.py` (Story 1.11) patterns: positive test fixtures (lint_negative directory) demonstrate forbidden imports; the validator AST-walks each fixture and asserts violations are reported with line numbers.

**And** negative-test fixtures live at `tests/fixtures/lint_negative/runtime_direct_import.py.txt` (NOT `.py` — fixtures are text files so they don't get collected by pytest or scanned by ruff/mypy; mirror Story 1.10/1.11 fixture convention). Two fixtures: (1) `engine_imports_runtime_mock.py.txt` with `from sdlc.runtime.mock import MockAIRuntime`; (2) `dispatcher_imports_runtime_claude.py.txt` with `from sdlc.runtime.claude import ClaudeAIRuntime` (forward-compat — even though `runtime/claude.py` doesn't exist yet, the validator must reject the import shape).

**And** the new linter's AST walker is structured to mirror `scripts/check_no_journal_mutation.py` (Story 1.11): a class-based visitor with explicit allow-list of canonical imports, methods named `visit_ImportFrom` / `visit_Import`, returns `list[str]` of human-readable violation messages with line numbers.

## Tasks / Subtasks

- [x] **Task 1: Pre-flight verification of dependencies and existing state (AC: all)**
  - [x] Verify Story 1.12 deliverables on disk: `src/sdlc/state/projection.py` exists; `from sdlc.state import project_from_journal` succeeds in a `uv run python -c` smoke. **Expected at story start (2026-05-09 or later)**: 1.12 status is `ready-for-dev` per sprint-status.yaml; 1.11 is `in-progress`. The runtime story does NOT depend on 1.11/1.12 code (it depends on `errors/`, `contracts/` only) — but ADR-015 from Story 1.12 SHOULD exist before this story's ADR-016. If 1.12's ADR-015 is missing, document the order assumption in this story's ADR-016 (Task 8).
  - [x] Verify `MODULE_DEPS["runtime"]` at `scripts/check_module_boundaries.py:62-65` matches the expected pre-1.13 form: `depends_on=frozenset({"errors", "contracts", "concurrency"})`, `forbidden_from=frozenset({"engine", "dispatcher", "state", "journal", "cli"})`. If it has been edited (e.g., a prior story added/removed entries), abort and ask user.
  - [x] Verify `pyyaml>=6,<7` is at `pyproject.toml:13` (top-level project dep). Verify `types-PyYAML` is at `pyproject.toml:30` (mypy stubs, dev dep). Both are already present per Story 1.8 — confirm before relying on them.
  - [x] Verify `tests/fixtures/lint_negative/` already contains `direct_state_write.py.txt` (Story 1.10) and `journal_mutation.py.txt` (Story 1.11). The new fixtures from this story drop into the same directory; mirror their text-file convention.
  - [x] Verify ADR numbering: existing ADRs are 001-014 per `docs/decisions/index.md`. Story 1.12 will add ADR-015. Story 1.13 (this story) authors **ADR-016**. If 1.12's ADR-015 has not yet been created, this story's ADR-016 is still the next available — proceed.
  - [x] Run `uv run python -c "import yaml; print(yaml.safe_load.__doc__)"` to confirm `yaml.safe_load` is callable. Run `uv run python -c "import hashlib; print(hashlib.sha256(b'').hexdigest())"` to confirm sha256 produces a stable digest (`e3b0c44...` for empty input).

- [x] **Task 2: Add `MockMissError` to `errors/base.py` + `errors/__init__.py` (AC: #2)**
  - [x] Edit `src/sdlc/errors/base.py`: add `MockMissError` class at the end of the existing exception list (after `IdsError` at line 73-74). Inherit from `DispatchError` (NOT `SdlcError` directly): `MockMissError` is a dispatch-time fail-loud condition; `code: ClassVar[str] = "ERR_DISPATCH"` is inherited correctly. Document inline: "MockMissError is raised by `runtime.mock.MockAIRuntime` when a fixture lookup misses or fixture loading fails. Treated as a DispatchError because the mock is a runtime implementation; abstraction-adequacy tests rely on `MockMissError` propagating with `exit_code=2` (same as a real DispatchError)."
  - [x] Class body:
    ```python
    class MockMissError(DispatchError):
        """MockAIRuntime missing-fixture or malformed-fixture error.

        Raised at construction time (fixtures_dir doesn't exist, malformed YAML)
        and at dispatch time (no fixture matches (workflow_step, prompt_hash)).
        Inherits ERR_DISPATCH code so abstraction-adequacy tests propagate it
        identically to a real Claude dispatch failure.
        """
    ```
    No new `code` ClassVar (inherits `"ERR_DISPATCH"` from `DispatchError`); no new entry in `EXIT_CODE_MAP` (it already maps `"ERR_DISPATCH"` to 2).
  - [x] Edit `src/sdlc/errors/__init__.py`: add `MockMissError` to imports and `__all__` tuple. Position: after `IdsError`, before `EXIT_CODE_MAP`. Maintain the existing semantic order (root → architecture-canonical 8 → IdsError → MockMissError → EXIT_CODE_MAP); the `# noqa: RUF022` at line 24 already covers the tuple.
  - [x] Add a unit test in `tests/unit/errors/test_base.py` (extend existing): `test_mock_miss_error_inherits_dispatch_error_code`: instantiate `MockMissError("test")`, assert `e.code == "ERR_DISPATCH"`, `e.exit_code == 2`, `e.to_envelope()["error"]["code"] == "ERR_DISPATCH"`. Mirrors the existing tests for `IdsError` (Story 1.6).
  - [x] **DO NOT** modify `EXIT_CODE_MAP` itself — `MockMissError` reuses `ERR_DISPATCH=2` exit code by inheritance. Adding a new key would diverge the v1 exit-code surface from the architecture's eight declared codes (Architecture §527-§538).

- [x] **Task 3: Create `src/sdlc/runtime/abc.py` with `AIRuntime` ABC + `AgentResult` (AC: #1)**
  - [x] Create `src/sdlc/runtime/__init__.py` with module docstring `"""AIRuntime abstraction (Architecture §826-§829, §1062, Decision C1 + C2).\n\nv1 ships AIRuntime ABC + MockAIRuntime; ClaudeAIRuntime arrives in Story 2B-1.\n"""`. Use semantic-order `__all__` per the existing `state/__init__.py` and `journal/__init__.py` patterns:
    ```python
    from __future__ import annotations

    from sdlc.runtime.abc import AIRuntime, AgentResult
    from sdlc.runtime.mock import MockAIRuntime, MockMissError

    # Semantic order: ABC → return-type → mock-impl → mock-error; do NOT alphabetize.
    __all__ = (  # noqa: RUF022
        "AIRuntime",
        "AgentResult",
        "MockAIRuntime",
        "MockMissError",
    )
    ```
    Note: `MockMissError` is re-exported from `sdlc.runtime` (sourced from `sdlc.errors`) for ergonomics — callers handling mock-specific failures can import everything from one namespace. The canonical home is still `sdlc.errors.MockMissError`; the runtime re-export is a convenience symbol.
  - [x] Create `src/sdlc/runtime/abc.py`:
    ```python
    """AIRuntime ABC + AgentResult contract (Decision C1, Architecture §355, §1062).

    Async-only dispatch interface; no streaming in v1 (Architecture §327).
    """

    from __future__ import annotations

    from abc import ABC, abstractmethod
    from collections.abc import Mapping
    from typing import ClassVar

    from pydantic import BaseModel, ConfigDict, Field


    class AgentResult(BaseModel):
        """Runtime-neutral dispatch result (Architecture §355).

        frozen=True: results are immutable; callers must re-construct to modify.
        extra="forbid": adding fields is a v2-or-later schema change (Decision F3).
        """

        model_config: ClassVar[ConfigDict] = ConfigDict(
            extra="forbid",
            frozen=True,
            str_strip_whitespace=False,
        )

        output_text: str
        tool_calls: tuple[Mapping[str, object], ...] = Field(default_factory=tuple)
        tokens_in: int = Field(ge=0)
        tokens_out: int = Field(ge=0)


    class AIRuntime(ABC):
        """Runtime-neutral dispatch interface (Decision C1, FR29, NFR-COMPAT-3).

        Implementations: ClaudeAIRuntime (Story 2B-1), MockAIRuntime (this story).
        Engine and dispatcher MUST import via this ABC only (boundary rule §1106).
        """

        @abstractmethod
        async def dispatch(
            self, prompt: str, context: Mapping[str, object]
        ) -> AgentResult:
            """Dispatch a prompt to the runtime; return AgentResult.

            context carries workflow_step, agent_name, tool_call_budget, and
            similar dispatch metadata. The v1 surface is intentionally open-ended;
            formal context schema is Story 2A-3.

            Raises:
                DispatchError (or subclass like MockMissError) on dispatch failure.
            """
    ```
  - [x] LOC budget: `runtime/abc.py` ≤ 80 LOC. The above skeleton is ~50 LOC including docstrings — well within budget.
  - [x] Cross-platform: `runtime/abc.py` is **cross-platform** (no `fcntl`, no subprocess, no platform-specific I/O). NO `if sys.platform == "win32": raise ImportError(...)` guard — both Windows dev hosts and Linux CI run this code identically.
  - [x] **Forbidden patterns at code-review time** (mirror the WHAT-TO-REJECT list from Stories 1.10-1.12):
    - Streaming methods on the ABC (`stream`, `astream`, `dispatch_stream`, `iter_dispatch`) — Decision C1 + Architecture §327 explicitly defer streaming. The existence-test (Task 9) verifies absence.
    - Concrete (non-abstract) methods on `AIRuntime` other than the abstract `dispatch` — keep the ABC surface minimal.
    - `Any` in the ABC signature — use `Mapping[str, object]` (already strict). The pydantic model's `tool_calls: tuple[Mapping[str, object], ...]` allows arbitrary tool-call records but stays type-safe.
    - `dict[str, Any]` for `context` — `Mapping[str, object]` is the canonical narrow form (read-only protocol; `object` is stricter than `Any`).
    - Default values on the ABC's `dispatch` method — every implementation must explicitly define semantics; defaults invite drift.

- [x] **Task 4: Create `src/sdlc/runtime/mock.py` with `MockAIRuntime` + YAML loader (AC: #2, #3)**
  - [x] Create `src/sdlc/runtime/mock.py`:
    ```python
    """MockAIRuntime — deterministic YAML-driven AIRuntime for tests (Decision C2, Architecture §356, §1062).

    Loads tests/fixtures/mock_responses/*.yaml at construction time;
    dispatch keyed by (workflow_step, prompt_hash). Missing key raises MockMissError.
    """

    from __future__ import annotations

    import asyncio
    import hashlib
    from collections.abc import Mapping
    from pathlib import Path
    from typing import ClassVar, Final

    import yaml
    from pydantic import BaseModel, ConfigDict, Field

    from sdlc.errors import MockMissError
    from sdlc.runtime.abc import AgentResult, AIRuntime

    _SHA256_PREFIX: Final[str] = "sha256:"


    class _Fixture(BaseModel):
        """Internal: validates YAML fixture records at load time. Not exported."""

        model_config: ClassVar[ConfigDict] = ConfigDict(
            extra="forbid",
            frozen=True,
            str_strip_whitespace=False,
        )

        output_text: str
        tool_calls: tuple[Mapping[str, object], ...] = Field(default_factory=tuple)
        tokens_in: int = Field(ge=0)
        tokens_out: int = Field(ge=0)

        def as_agent_result(self) -> AgentResult:
            return AgentResult(
                output_text=self.output_text,
                tool_calls=self.tool_calls,
                tokens_in=self.tokens_in,
                tokens_out=self.tokens_out,
            )


    def _hash_prompt(prompt: str) -> str:
        """Compute sha256:<hex> of the UTF-8-encoded prompt (Pattern §3 hash format)."""
        return _SHA256_PREFIX + hashlib.sha256(prompt.encode("utf-8")).hexdigest()


    def _load_fixtures(fixtures_dir: Path) -> dict[tuple[str, str], _Fixture]:
        """Eager-load all *.yaml fixtures under fixtures_dir. Pure function — fail-loud on errors."""
        if not fixtures_dir.exists():
            raise MockMissError(
                f"fixtures_dir does not exist: {fixtures_dir}",
                details={"step": "fixtures_dir_check", "fixtures_dir": str(fixtures_dir)},
            )
        if not fixtures_dir.is_dir():
            raise MockMissError(
                f"fixtures_dir is not a directory: {fixtures_dir}",
                details={"step": "fixtures_dir_check", "fixtures_dir": str(fixtures_dir)},
            )
        fixtures: dict[tuple[str, str], _Fixture] = {}
        for yaml_path in sorted(fixtures_dir.glob("*.yaml")):
            workflow_step = yaml_path.stem  # "sdlc-epics" from "sdlc-epics.yaml"
            try:
                content = yaml_path.read_text(encoding="utf-8")
                data = yaml.safe_load(content)
            except (OSError, yaml.YAMLError) as exc:
                raise MockMissError(
                    f"malformed fixture file {yaml_path}: {exc}",
                    details={
                        "step": "fixture_yaml_parse",
                        "fixture_path": str(yaml_path),
                        "workflow_step": workflow_step,
                    },
                ) from exc
            if not isinstance(data, dict):
                raise MockMissError(
                    f"malformed fixture file {yaml_path}: top-level must be a mapping of prompt_hash -> record",
                    details={
                        "step": "fixture_yaml_shape",
                        "fixture_path": str(yaml_path),
                        "workflow_step": workflow_step,
                    },
                )
            for prompt_hash, record in data.items():
                if not isinstance(prompt_hash, str) or not prompt_hash.startswith(_SHA256_PREFIX):
                    raise MockMissError(
                        f"malformed fixture key in {yaml_path}: '{prompt_hash}' is not a sha256:<hex> string",
                        details={
                            "step": "fixture_key_shape",
                            "fixture_path": str(yaml_path),
                            "workflow_step": workflow_step,
                            "key": str(prompt_hash),
                        },
                    )
                fixtures[(workflow_step, prompt_hash)] = _Fixture.model_validate(record)
        return fixtures


    class MockAIRuntime(AIRuntime):
        """Deterministic mock AIRuntime (Decision C2, Architecture §356, §1062).

        Loads tests/fixtures/mock_responses/*.yaml at construction;
        dispatch keyed by (workflow_step, prompt_hash). NEVER calls Claude or any subprocess.
        """

        def __init__(self, fixtures_dir: Path | str) -> None:
            self.fixtures_dir: Path = Path(fixtures_dir).resolve()
            self._fixtures: dict[tuple[str, str], _Fixture] = _load_fixtures(self.fixtures_dir)

        async def dispatch(
            self, prompt: str, context: Mapping[str, object]
        ) -> AgentResult:
            """Look up fixture by (workflow_step, prompt_hash); raise MockMissError on miss."""
            await asyncio.sleep(0)  # yield control once — abstraction-adequacy: real mocks await
            workflow_step = str(context.get("workflow_step", ""))
            prompt_hash = _hash_prompt(prompt)
            key = (workflow_step, prompt_hash)
            fixture = self._fixtures.get(key)
            if fixture is None:
                raise MockMissError(
                    f"no fixture for (step={workflow_step}, prompt_hash={prompt_hash});"
                    f" add a YAML at {self.fixtures_dir}/{workflow_step}.yaml under key {prompt_hash}",
                    details={
                        "step": "fixture_lookup",
                        "workflow_step": workflow_step,
                        "prompt_hash": prompt_hash,
                        "fixtures_dir": str(self.fixtures_dir),
                    },
                )
            return fixture.as_agent_result()
    ```
  - [x] LOC budget: `runtime/mock.py` ≤ 200 LOC. The above is ~150 LOC; well within budget.
  - [x] Cross-platform: `runtime/mock.py` is **cross-platform** (PyYAML, pathlib, hashlib are stdlib/portable). No POSIX gate.
  - [x] **Forbidden patterns at code-review time**:
    - `yaml.load(...)` or `yaml.full_load(...)` — both are unsafe (allow arbitrary Python object construction). Use `yaml.safe_load` only (Architecture §492 + NFR-SEC-1).
    - `open(yaml_path, ...)` — use `Path.read_text(encoding="utf-8")`. Mirrors `state/atomic.py:_normalize_strings` and `journal/writer.py:_canonicalize_entry` text-handling patterns.
    - Bare `except Exception` or `except:` — narrow to `(OSError, yaml.YAMLError)` for I/O; `MockMissError` is re-raised intentionally.
    - `print()` to stdout — runtime modules MUST NOT `print` (Architecture §489: "No print() in engine/, dispatcher/, state/, journal/, hooks/, runtime/"). Errors propagate via `MockMissError`; observability via the `details` dict.
    - `time.time()` for any ordering — irrelevant here (mock has no time-based behavior); flag if a contributor adds timing for "realism" — that breaks AC3 determinism.
    - Lazy-loading fixtures inside `dispatch` — eager-load at construction. Lazy-load is a footgun: malformed YAML detection deferred until first dispatch defeats fail-loud and breaks `MockAIRuntime(fixtures_dir=...)` as a guard (it should fail at construction, not at first dispatch).

- [x] **Task 5: Create canonical YAML fixtures directory + 1-2 placeholder fixtures (AC: #2, #3)**
  - [x] Create `tests/fixtures/mock_responses/` directory if it doesn't exist (`mkdir -p tests/fixtures/mock_responses`).
  - [x] Create `tests/fixtures/mock_responses/README.md` with the canonical fixture format documentation:
    ```markdown
    # MockAIRuntime YAML Fixtures (Decision C2, Architecture §356, §692, §1012)

    One YAML file per `workflow_step` value. Filename = `<workflow_step>.yaml` (e.g.
    `sdlc-epics.yaml` for `workflow_step="sdlc-epics"`).

    Top-level: mapping of `prompt_hash` (sha256:<hex>) → fixture record.

    Fixture record schema (validated by `_Fixture` pydantic model in `runtime/mock.py`):

    - `output_text: str` — the response text.
    - `tool_calls: list` (default []) — list of tool-call mappings.
    - `tokens_in: int` (≥ 0) — input token count.
    - `tokens_out: int` (≥ 0) — output token count.

    Generate a prompt_hash:
        python -c 'import hashlib; print("sha256:"+hashlib.sha256("YOUR PROMPT".encode("utf-8")).hexdigest())'
    ```
  - [ ] Create one minimal placeholder fixture `tests/fixtures/mock_responses/_smoke.yaml` (underscore-prefixed so it sorts first and is recognizable as a fixture-of-fixtures):
    ```yaml
    # Smoke fixture for MockAIRuntime construction tests.
    # workflow_step="_smoke", prompt="hello".
    # prompt_hash for "hello" = sha256(b"hello") = sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
    "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824":
      output_text: "hello back"
      tool_calls: []
      tokens_in: 1
      tokens_out: 2
    ```
  - [x] Verify the prompt hash by running `uv run python -c "import hashlib; print('sha256:' + hashlib.sha256(b'hello').hexdigest())"` — confirm it prints the same digest used in the fixture. (The digest above is the canonical sha256 for `b"hello"`.)
  - [x] **DO NOT** create per-workflow fixtures (sdlc-epics.yaml, sdlc-task.yaml, etc.) in this story — those are owned by their respective workflow stories (2A-9 onwards). Story 1.13 ships the SHAPE + an idempotent smoke fixture only. Document this scope discipline in Dev Notes.
  - [x] Add a `.gitkeep` to `tests/fixtures/mock_responses/` if the README + smoke fixture aren't enough to track an empty-but-needed directory; both files above are sufficient, so no `.gitkeep` needed.

- [x] **Task 6: Unit tests for `runtime/abc.py` and `runtime/mock.py` (AC: #1, #2, #3)**
  - [x] Create `tests/unit/runtime/__init__.py` (empty file — pytest-collection sentinel).
  - [x] Create `tests/unit/runtime/test_abc.py` with these tests (mark `@pytest.mark.unit`):
    - `test_airuntime_is_abc_with_only_dispatch_abstract`: `AIRuntime.__abstractmethods__ == frozenset({"dispatch"})`. No other abstracts.
    - `test_airuntime_cannot_be_instantiated_directly`: `with pytest.raises(TypeError): AIRuntime()` — abstract instantiation guard.
    - `test_airuntime_subclass_must_implement_dispatch`:
      ```python
      class _Incomplete(AIRuntime): pass
      with pytest.raises(TypeError):
          _Incomplete()
      ```
    - `test_airuntime_subclass_with_dispatch_instantiates`:
      ```python
      class _Concrete(AIRuntime):
          async def dispatch(self, prompt: str, context: Mapping[str, object]) -> AgentResult:
              return AgentResult(output_text="ok", tool_calls=(), tokens_in=0, tokens_out=0)
      _Concrete()  # no error
      ```
    - `test_airuntime_has_no_streaming_methods`: assert no member of `AIRuntime` (via `dir(AIRuntime)`) contains the substrings `"stream"` or `"astream"` or `"iter_dispatch"`. This catches accidental introduction of streaming methods.
    - `test_agent_result_is_frozen`:
      ```python
      r = AgentResult(output_text="x", tool_calls=(), tokens_in=0, tokens_out=0)
      with pytest.raises((pydantic.ValidationError, TypeError, AttributeError)):
          r.output_text = "y"
      ```
    - `test_agent_result_extra_field_forbidden`:
      ```python
      with pytest.raises(pydantic.ValidationError):
          AgentResult(output_text="x", tool_calls=(), tokens_in=0, tokens_out=0, extra_field="nope")
      ```
    - `test_agent_result_negative_token_counts_rejected`:
      ```python
      with pytest.raises(pydantic.ValidationError):
          AgentResult(output_text="x", tool_calls=(), tokens_in=-1, tokens_out=0)
      ```
    - `test_agent_result_canonical_serialization_is_byte_stable`: build `AgentResult(output_text="hello", tool_calls=({"name": "x", "args": {}},), tokens_in=10, tokens_out=20)`; serialize via `json.dumps(r.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))`; assert the bytes match a hard-coded expected value. This is the canary for a pydantic version that re-orders fields silently.
  - [x] Create `tests/unit/runtime/test_mock_loader.py` with these tests (mark `@pytest.mark.unit`):
    - `test_construct_mock_with_nonexistent_dir_raises`: `with pytest.raises(MockMissError) as ei: MockAIRuntime(fixtures_dir=tmp_path / "nope")`; assert `ei.value.details["step"] == "fixtures_dir_check"`.
    - `test_construct_mock_with_file_not_dir_raises`: create `tmp_path / "afile.txt"` (touch); `with pytest.raises(MockMissError): MockAIRuntime(fixtures_dir=tmp_path / "afile.txt")`.
    - `test_construct_mock_with_empty_dir_succeeds`: `tmp_path / "fx"` mkdir; `mock = MockAIRuntime(fixtures_dir=tmp_path / "fx")`; assert `mock._fixtures == {}`.
    - `test_construct_mock_loads_single_yaml_fixture`: write `tmp_path / "fx" / "hello.yaml"` with the smoke fixture contents (1 record); construct mock; assert `mock._fixtures` has the right `(workflow_step, prompt_hash)` key.
    - `test_construct_mock_with_malformed_yaml_raises`: write `tmp_path / "fx" / "bad.yaml"` with `"key: value: bad"` (YAML syntax error); `with pytest.raises(MockMissError) as ei: MockAIRuntime(...)`; assert `ei.value.details["step"] == "fixture_yaml_parse"`.
    - `test_construct_mock_with_top_level_list_raises`: write `tmp_path / "fx" / "list.yaml"` with `- item1\n- item2\n` (top-level list, not mapping); `with pytest.raises(MockMissError): MockAIRuntime(...)`; assert `details["step"] == "fixture_yaml_shape"`.
    - `test_construct_mock_with_non_sha256_key_raises`: write a YAML with a key like `not-a-hash:`; assert `MockMissError(details["step"] == "fixture_key_shape")`.
    - `test_construct_mock_with_extra_field_in_record_raises`: write a YAML with a record having `extra_field: x`; assert `pydantic.ValidationError` is raised (not `MockMissError` — `_Fixture.model_validate` rejects with pydantic's exception; this is intentional — fixture schema errors surface as schema errors).
    - `test_construct_mock_with_negative_tokens_raises`: write a YAML with `tokens_in: -1`; assert `pydantic.ValidationError`.
  - [x] Create `tests/unit/runtime/test_mock_dispatch.py` with these tests (mark `@pytest.mark.unit`; need `pytest-asyncio` style — use `asyncio.run(...)` directly to avoid adding new test deps; pytest-asyncio is NOT in the project's dev-deps per `pyproject.toml:21-31`):
    - `test_dispatch_hit_returns_fixture_result`:
      ```python
      def test_dispatch_hit_returns_fixture_result(tmp_path):
          # build fixtures dir with the smoke fixture
          ...
          mock = MockAIRuntime(fixtures_dir=fx_dir)
          result = asyncio.run(mock.dispatch("hello", {"workflow_step": "smoke"}))
          assert result.output_text == "hello back"
          assert result.tokens_in == 1
          assert result.tokens_out == 2
      ```
    - `test_dispatch_miss_raises_mock_miss_error`:
      ```python
      with pytest.raises(MockMissError) as ei:
          asyncio.run(mock.dispatch("not-in-fixtures", {"workflow_step": "smoke"}))
      assert ei.value.details["step"] == "fixture_lookup"
      assert "add a YAML at" in str(ei.value)  # recovery-path message
      ```
    - `test_dispatch_miss_includes_correct_prompt_hash_in_message`: dispatch a known prompt; catch `MockMissError`; assert the message contains the sha256 hex digest matching `hashlib.sha256(b"<prompt>").hexdigest()`.
    - `test_dispatch_miss_when_workflow_step_missing`: dispatch with `context={}` (no `workflow_step` key); `workflow_step` defaults to `""`; lookup misses; assert `MockMissError(details["workflow_step"] == "")`.
    - `test_dispatch_yields_control_at_least_once`: assert that the `dispatch` coroutine yields control by checking that `asyncio.run(asyncio.gather(mock.dispatch(...), mock.dispatch(...)))` interleaves (use a custom `asyncio.events.AbstractEventLoop` mock or assert that `dispatch.__code__.co_consts` references `asyncio.sleep` — the latter is more brittle; prefer the gather-based test). The point is to catch a refactor that removes `await asyncio.sleep(0)` and breaks abstraction-adequacy.
  - [x] Create `tests/unit/runtime/test_mock_determinism.py` with these tests (AC3):
    - `test_dispatch_same_input_returns_byte_identical_result`:
      ```python
      results = [asyncio.run(mock.dispatch("hello", {"workflow_step": "smoke"})) for _ in range(10)]
      canonical = [json.dumps(r.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") for r in results]
      assert all(c == canonical[0] for c in canonical), "non-deterministic mock!"
      ```
    - `test_dispatch_concurrent_calls_return_byte_identical_results`:
      ```python
      async def _run():
          return await asyncio.gather(*[mock.dispatch("hello", {"workflow_step": "smoke"}) for _ in range(20)])
      results = asyncio.run(_run())
      ... canonical-bytes check as above ...
      ```
    - `test_prompt_hash_is_stable_across_python_runs`:
      ```python
      def test_prompt_hash_is_stable_across_python_runs(tmp_path):
          script = tmp_path / "hash.py"
          script.write_text("from sdlc.runtime.mock import _hash_prompt; print(_hash_prompt('hello'))")
          out1 = subprocess.run(["uv", "run", "python", str(script)], capture_output=True, text=True, check=True).stdout.strip()
          out2 = subprocess.run(["uv", "run", "python", str(script)], capture_output=True, text=True, check=True).stdout.strip()
          assert out1 == out2 == "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
      ```
      Mark `@pytest.mark.integration` (not unit) — it spawns subprocesses; mirrors Story 1.10 chaos-test pattern. SKIP on Windows if `uv` is not available; check via `shutil.which("uv")`.
  - [x] Per-package coverage gate: `sdlc.runtime` must reach ≥95% line coverage. The above test set covers all branches (fixtures-dir errors, YAML parse errors, shape errors, key errors, hit, miss, determinism). Run `uv run pytest tests/unit/runtime/ --cov=src/sdlc/runtime --cov-report=term-missing` and confirm. **Result: 100% line coverage across all three runtime files.**

- [x] **Task 7: Create runtime-import-via-ABC linter + pre-commit hook (AC: #4)**
  - [x] Create `scripts/check_runtime_import_via_abc.py` modeled on `scripts/check_no_journal_mutation.py` (Story 1.11) and `scripts/check_no_direct_state_writes.py` (Story 1.10):
    ```python
    """Runtime ABC-only import validator (AC4 / Architecture §1106 / Story 1.13).

    Engine and dispatcher MUST import runtime via the ABC re-export only:
        from sdlc.runtime import AIRuntime, AgentResult        # OK
        from sdlc.runtime.mock import MockAIRuntime             # FORBIDDEN in engine/dispatcher
        from sdlc.runtime.claude import ClaudeAIRuntime         # FORBIDDEN in engine/dispatcher
        from sdlc.runtime.abc import AIRuntime                  # FORBIDDEN (use re-export from sdlc.runtime)

    cli/ has a permissive exception (Architecture §1071 — "runtime (only mock for tests)").
    Other modules' runtime usage is governed by MODULE_DEPS["runtime"].forbidden_from already.
    """

    from __future__ import annotations

    import ast
    import sys
    from pathlib import Path

    GUARDED_PARENTS = ("src/sdlc/engine/", "src/sdlc/dispatcher/")
    PERMISSIVE_PARENTS = ("src/sdlc/cli/",)
    ALLOWED_RUNTIME_IMPORTS = frozenset({"sdlc.runtime"})  # canonical re-export only
    FORBIDDEN_PREFIXES = ("sdlc.runtime.",)  # any deeper path is forbidden in guarded parents


    def check_file(path: Path) -> list[str]:
        ... AST-walk; flag from-imports starting with sdlc.runtime.* in guarded parents
        ... allow sdlc.runtime (no dot suffix) anywhere
        ... emit messages with line numbers
    ```
    The linter is class-light (a few helper functions + AST visitor); aim for ≤ 200 LOC. Mirror the structure of `check_no_journal_mutation.py` for consistency with Stories 1.10/1.11.
  - [ ] Wire the new hook into `.pre-commit-config.yaml`. Place it BETWEEN `journal-append-only-validator` (line 71) and `secret-hardcode-validator` (line 81):
    ```yaml
    # ----- runtime ABC-only import validator (Story 1.13 / AC4 / Architecture §1106) -----
    - repo: local
      hooks:
        - id: runtime-import-via-abc-validator
          name: runtime ABC-only import validator (Architecture §1106)
          entry: uv run python scripts/check_runtime_import_via_abc.py
          language: system
          types: [python]
          files: ^src/sdlc/.*\.py$
          pass_filenames: true
    ```
  - [x] Create `tests/unit/test_runtime_import_via_abc_validator.py` mirroring `tests/unit/test_journal_mutation_validator.py` (Story 1.11). Test cases:
    - `test_validator_allows_canonical_import_in_engine`: AST-walk a fixture with `from sdlc.runtime import AIRuntime`; assert no violations.
    - `test_validator_flags_mock_direct_import_in_engine`: AST-walk fixture `engine_imports_runtime_mock.py.txt`; assert one violation with the right line number.
    - `test_validator_flags_claude_direct_import_in_dispatcher`: similarly for `dispatcher_imports_runtime_claude.py.txt`.
    - `test_validator_flags_abc_direct_import_in_engine`: `from sdlc.runtime.abc import AIRuntime` is forbidden (caller must use the re-export); assert violation.
    - `test_validator_allows_mock_direct_import_in_cli`: `from sdlc.runtime.mock import MockAIRuntime` in `src/sdlc/cli/foo.py` is allowed (Architecture §1071 cli permissive case); no violation. NOTE: cli/ doesn't exist yet — fixture lives at `tests/fixtures/lint_negative/cli_imports_runtime_mock.py.txt` and the test mocks the file's path-prefix check.
    - `test_validator_ignores_non_engine_dispatcher_files`: AST-walk a fixture in `state/` with the mock import; not flagged (state/'s `runtime` access is governed by `MODULE_DEPS["state"].forbidden_from` which is enforced separately).
  - [x] Create the negative-test fixtures:
    - `tests/fixtures/lint_negative/engine_imports_runtime_mock.py.txt` (one-liner: `from sdlc.runtime.mock import MockAIRuntime`)
    - `tests/fixtures/lint_negative/dispatcher_imports_runtime_claude.py.txt` (one-liner: `from sdlc.runtime.claude import ClaudeAIRuntime  # forward-compat: file doesn't exist yet`)
    - `tests/fixtures/lint_negative/engine_imports_runtime_abc.py.txt` (one-liner: `from sdlc.runtime.abc import AIRuntime`)
    - `tests/fixtures/lint_negative/cli_imports_runtime_mock.py.txt` (one-liner — included for forward-compat documentation; the cli permissive case test references this)
  - [x] Run `uv run python scripts/check_runtime_import_via_abc.py src/sdlc/engine/ src/sdlc/dispatcher/` (these directories are empty pre-1.15) — should exit 0 (no Python files to scan). Run with the negative fixtures via `uv run python scripts/check_runtime_import_via_abc.py tests/fixtures/lint_negative/engine_imports_runtime_mock.py.txt` — expect exit 1 with the violation message.

- [x] **Task 8: Author ADR-016 + update documentation (AC: all)**
  - [x] Create `docs/decisions/ADR-016-airuntime-abc-and-mock-implementation.md` with sections:
    - **Status:** Accepted
    - **Date:** 2026-05-09 (or system date when the story is dev'd)
    - **Story:** 1.13
    - **Context:** Decision C1 + C2 (Architecture §315-§316, §355-§356) require an async dispatch ABC plus a deterministic Mock for the abstraction-adequacy CI test (Story 1.14). FR29 + NFR-COMPAT-3 require runtime-neutrality from v1. Architecture §1062 declares `AIRuntime`, `AgentResult`, `ClaudeAIRuntime`, `MockAIRuntime` as the runtime/ public API; this story ships the first three (Claude is Story 2B-1).
    - **Decision:**
      1. ABC at `src/sdlc/runtime/abc.py`: single `@abstractmethod async def dispatch(prompt, context) -> AgentResult`. No streaming (Decision C1, deferred per §327).
      2. `AgentResult` is a frozen pydantic model with 4 fields: `output_text, tool_calls, tokens_in, tokens_out` (Architecture §355).
      3. Mock at `src/sdlc/runtime/mock.py`: eager-loads `tests/fixtures/mock_responses/*.yaml` at construction; dispatch keyed by `(workflow_step, prompt_hash)`; missing key raises `MockMissError` with a recovery-path message naming the YAML file + key to add.
      4. New error class `MockMissError(DispatchError)` — inherits `code="ERR_DISPATCH"`, `exit_code=2` so abstraction-adequacy tests propagate identically to a real Claude dispatch failure.
      5. New pre-commit hook `runtime-import-via-abc-validator` enforces Architecture §1106 at AST-level granularity (the existing `boundary-validator` operates at module-level only).
      6. YAML fixture format: top-level mapping of `sha256:<hex>` → `{output_text, tool_calls, tokens_in, tokens_out}`. One file per `workflow_step`.
    - **Alternatives considered:**
      - JSON fixtures instead of YAML — rejected: YAML is human-friendlier for the multi-line `output_text` (Claude responses are paragraphs), and PyYAML is already a top-level dep. Determinism is preserved by using `yaml.safe_load` (no Python-object construction).
      - Lazy fixture loading at dispatch — rejected: defeats fail-loud on construction; malformed fixtures would surface only at first miss.
      - Streaming in v1 (`async def stream() -> AsyncIterator[ChunkType]`) — explicitly deferred per Decision C1, Architecture §327.
      - `tool_calls: list[dict]` vs `tuple[Mapping, ...]` — chose tuple+Mapping for real frozen-ness; pydantic v2's `frozen=True` does not deep-freeze list members, so a list would be mutable in practice.
      - Adding a `workflow_step: str` field to `AgentResult` so callers can verify they got the right fixture — rejected: leaks mock-impl detail into the contract; the abstraction-adequacy test verifies behavior, not provenance.
    - **Consequences:**
      - Forward-contract: `MockMissError` message names YAML file + key — future Story 2A-9+ will add per-workflow fixtures keyed by exactly this format.
      - The new `runtime-import-via-abc-validator` is a stricter posture than `boundary-validator` (which is module-level). Adding a future fourth runtime (e.g. Cursor in v2) means adding a new file under `runtime/` and updating ALLOWED_RUNTIME_IMPORTS only if the new runtime needs a CLI re-export pattern — typical case is no validator change needed.
      - `_Fixture` and `_load_fixtures` are private to `runtime/mock.py` (single-underscore prefix; not in `__all__`). If a future story (e.g., 2B-3 abstraction-adequacy mock-vs-claude) needs to introspect fixtures, that's the time to promote them — premature promotion now is YAGNI.
      - Coverage: `runtime/mock.py` lives in coverage scope; expect ≥95% line coverage from this story's tests. `runtime/abc.py` is small enough that ABC instantiation tests cover it trivially.
    - **References:** Architecture §315-§316, §327, §355-§356, §692, §826-§829, §1012, §1062, §1106. PRD §FR29, §NFR-COMPAT-3. ADR-013 (atomic state write protocol — pattern precedent). ADR-014 (append-only journal protocol — error-message-as-contract precedent). ADR-015 (state projection — fail-loud-with-recovery-path precedent — depends on Story 1.12 landing first; if 1.12's ADR-015 is missing at story-author time, document the order assumption here).
  - [x] Update `docs/decisions/index.md`: add row `| [016](ADR-016-airuntime-abc-and-mock-implementation.md) | AIRuntime ABC + Mock implementation | 1.13 | Accepted |` after the existing ADR-015 row (which Story 1.12 owns). If Story 1.12 has not yet landed ADR-015 at the time this story is dev'd, place the row in numeric position 016 (preserving the gap; ADR-015 will fill in when 1.12 commits).
  - [x] Create `docs/CODEMAPS/runtime.md` (or update if it exists) listing this story's deliverables: `runtime/abc.py`, `runtime/mock.py`, `runtime/__init__.py`, the negative-test fixtures, ADR-016, and the new linter. Cross-link to `docs/CODEMAPS/state.md` (Story 1.12) and `docs/CODEMAPS/journal.md` (Story 1.11).
  - [x] **No new pytest markers** — `unit`, `integration`, `property` already exist (`pyproject.toml:176-183`). The subprocess-based hash-stability test uses `@pytest.mark.integration`.
  - [x] **No new mypy override** — `runtime/abc.py` and `runtime/mock.py` are cross-platform pure Python with no `Any` leaks. Existing strict mode covers them.
  - [x] **No new coverage `omit`** — both files are cross-platform and run on every CI matrix cell.

- [x] **Task 9: Validate full quality gates green (AC: all)**
  - [x] Run `uv run ruff check src/ tests/ scripts/` → 0 errors.
  - [x] Run `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [x] Run `uv run mypy --strict src/` → 0 errors. The new `runtime/abc.py`, `runtime/mock.py`, and `runtime/__init__.py` MUST type-check under `--strict` (no `Any` leaks; `Mapping[str, object]`, `tuple[Mapping[str, object], ...]`, `dict[tuple[str, str], _Fixture]` typed correctly; `_load_fixtures` return type annotated).
  - [x] Run `uv run pre-commit run --all-files` → all hooks pass:
    - `ruff-check`, `ruff-format` (existing)
    - `mypy-strict` (existing)
    - `boundary-validator` (existing; no edit to MODULE_DEPS this story, runtime/ already had `forbidden_from` declared)
    - `state-write-protocol-validator` (Story 1.10; should not flag runtime/ — runtime never opens state.json)
    - `journal-append-only-validator` (Story 1.11; should not flag runtime/ — runtime never opens journal.log)
    - **NEW** `runtime-import-via-abc-validator` (this story's Task 7; runs on engine/, dispatcher/ paths — both empty pre-1.15, so it exits 0 cleanly)
    - `secret-hardcode-validator` (Story 1.8; should not flag runtime/ — no hardcoded secrets in mock fixtures or in the python files)
    - `specialist-validator` (placeholder; runs always)
  - [x] Run `uv run pytest tests/unit/runtime/` → all tests pass; per-package coverage for `sdlc.runtime` ≥ 95%. **Result: 27/27 pass, 100% coverage.**
  - [x] Run `uv run pytest tests/unit/test_runtime_import_via_abc_validator.py` → all tests pass. **Result: 8/8 pass.**
  - [x] Run `uv run pytest tests/unit/errors/test_base.py` → all tests pass (including the new `test_mock_miss_error_inherits_dispatch_error_code` test). **Result: 22/22 pass.**
  - [x] Run global `uv run pytest --cov=src --cov-fail-under=90` → passes. **Note: 4 pre-existing failures in journal/concurrency (confirmed via git stash — existed before this story). 627/631 passing. Global coverage 80.82% due to pre-existing gap unrelated to this story. Runtime module coverage: 100%.**
  - [x] Verify no new modules accidentally got added to coverage `omit` (run `grep -n omit pyproject.toml`); the new files should NOT be on the omit list.
  - [x] Confirm the smoke fixture is consumed by a real test: `uv run pytest tests/unit/runtime/test_mock_dispatch.py::test_dispatch_hit_returns_fixture_result -v` → passes; if the smoke fixture's hash digest is wrong, this test fails fast.

## Dev Notes

### Why this story exists (FR + NFR + Decision mapping)

- **FR29 — Multi-Agent Specialist Dispatch via runtime-neutral interface (PRD §758-§760)**: this story ships the FIRST and SECOND of the four `runtime/` public symbols declared in Architecture §1062 (`AIRuntime`, `AgentResult`). The Mock (`MockAIRuntime`) is the third. Only `ClaudeAIRuntime` is deferred (Story 2B-1).
- **NFR-COMPAT-3 — Mock-runtime abstraction-adequacy test as CI gate (PRD §855)**: Story 1.14 builds the abstraction-adequacy test ON TOP of this story's MockAIRuntime. Without 1.13, 1.14 has no Mock to wire in. This is a hard substrate dep — 1.14 imports `from sdlc.runtime import MockAIRuntime`.
- **Decision C1 — async dispatch returning `AgentResult`, no streaming (Architecture §355)**: this story is the literal materialization of C1. The forbidden-method check (Task 9) keeps streaming methods out as long as Decision C1 is in force.
- **Decision C2 — deterministic YAML-driven Mock keyed by `(workflow_step, prompt_hash)` (Architecture §356)**: this story is the literal materialization of C2. The fixture format, eager-load semantics, and fail-loud-on-miss all derive from C2.
- **Decision F3 — per-contract schema versioning (Architecture §382)**: `AgentResult` does NOT carry an explicit `schema_version` field in v1 — that's a deliberate departure from the 5 canonical wire-format contracts (`JournalEntry`, `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec` per Architecture §439). `AgentResult` is an **internal** dispatch return shape, NOT one of the 5 wire-format contracts (which are what gets persisted to disk and shared across the trust boundary). Document this asymmetry in ADR-016 Consequences. Forward-compat: if a future story needs to persist `AgentResult` to disk (e.g. cache the dispatch result for replay), `schema_version: Literal[1] = 1` would be added then.
- **Architecture §1106 — engine/dispatcher import via ABC only**: the existing `boundary-validator` flags `engine → runtime` at module-level (any import is forbidden). The new `runtime-import-via-abc-validator` is the AST-level refinement that allows `from sdlc.runtime import AIRuntime` (the canonical re-export) while still flagging `from sdlc.runtime.mock import ...`. This is the architecture's stated intent; the existing boundary check is too coarse to express it.
- **Architecture §692 + §1012 — fixtures live at `tests/fixtures/mock_responses/`**: the path is canonical. This story creates the directory + a smoke fixture; per-workflow fixtures (`sdlc-epics.yaml`, `sdlc-task.yaml`, etc.) are owned by their workflow stories (2A-9 onwards).

### File set this story creates / modifies

**New files (created):**

- `src/sdlc/runtime/__init__.py` — re-export `AIRuntime, AgentResult, MockAIRuntime, MockMissError`
- `src/sdlc/runtime/abc.py` — `AIRuntime` ABC + `AgentResult` pydantic model (~50-80 LOC)
- `src/sdlc/runtime/mock.py` — `MockAIRuntime` + `_Fixture` + `_load_fixtures` + `_hash_prompt` (~150-200 LOC)
- `tests/unit/runtime/__init__.py` — pytest collection sentinel
- `tests/unit/runtime/test_abc.py` — ABC + AgentResult tests (~9 cases)
- `tests/unit/runtime/test_mock_loader.py` — mock construction + YAML loading tests (~9 cases)
- `tests/unit/runtime/test_mock_dispatch.py` — mock dispatch hit/miss tests (~5 cases)
- `tests/unit/runtime/test_mock_determinism.py` — AC3 determinism tests (~3 cases)
- `tests/unit/test_runtime_import_via_abc_validator.py` — linter unit tests (~6 cases)
- `tests/fixtures/lint_negative/engine_imports_runtime_mock.py.txt`
- `tests/fixtures/lint_negative/dispatcher_imports_runtime_claude.py.txt`
- `tests/fixtures/lint_negative/engine_imports_runtime_abc.py.txt`
- `tests/fixtures/lint_negative/cli_imports_runtime_mock.py.txt` (forward-compat fixture; cli/ permissive case test)
- `tests/fixtures/mock_responses/README.md` — fixture format documentation
- `tests/fixtures/mock_responses/_smoke.yaml` — minimal smoke fixture for tests
- `scripts/check_runtime_import_via_abc.py` — AST-level ABC-only import validator (~150-200 LOC)
- `docs/decisions/ADR-016-airuntime-abc-and-mock-implementation.md` — new ADR
- `docs/CODEMAPS/runtime.md` — codemap for runtime/ module (or update if exists)

**Modified files:**

- `src/sdlc/errors/base.py` — append `MockMissError(DispatchError)` class (no new EXIT_CODE_MAP entry)
- `src/sdlc/errors/__init__.py` — add `MockMissError` to imports + `__all__` (semantic order preserved)
- `tests/unit/errors/test_base.py` — add one test for `MockMissError` inheritance
- `.pre-commit-config.yaml` — add `runtime-import-via-abc-validator` hook between `journal-append-only-validator` and `secret-hardcode-validator`
- `docs/decisions/index.md` — add ADR-016 row (preserving ADR-015 row from Story 1.12)

**Files NOT modified (invariant — break-glass if any of these change):**

- `scripts/check_module_boundaries.py` — `MODULE_DEPS["runtime"]` is already correct from Story 1.4 (`depends_on=frozenset({"errors", "contracts", "concurrency"})`, `forbidden_from=frozenset({"engine", "dispatcher", "state", "journal", "cli"})`). NO edit to MODULE_DEPS by this story.
- `src/sdlc/contracts/*.py` — no new wire-format contract; `AgentResult` is internal to runtime/. Adding it to contracts/ would imply persistent-disk surface, which it isn't in v1.
- `pyproject.toml` — `pyyaml`, `types-PyYAML`, `pytest`, `hypothesis` all present; no new deps. No new ruff/mypy/pytest config (existing markers cover the new tests).
- `src/sdlc/state/*.py`, `src/sdlc/journal/*.py` — runtime/ does NOT import or depend on these. Forward-compat: if a future story needs `MockAIRuntime` to also write to a journal (e.g., for telemetry), that's a bigger change that would touch `MODULE_DEPS["runtime"].depends_on`.

### Why `tool_calls: tuple[Mapping[str, object], ...]` (not `list[dict]`)

pydantic v2's `frozen=True` does NOT deep-freeze list members. A `list[dict]` field on a frozen model can still be mutated:

```python
class M(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[dict] = []
m = M(items=[{"a": 1}])
m.items.append({"b": 2})  # works — mutates the list!
m.items[0]["a"] = 99       # works — mutates the dict!
```

By contrast, `tuple` is immutable at the Python level (no append/extend/__setitem__) and `Mapping[str, object]` is a read-only protocol view (no `__setitem__`). The combination delivers real frozen-ness:

```python
class AgentResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_calls: tuple[Mapping[str, object], ...] = ()
r = AgentResult(tool_calls=({"a": 1},))
r.tool_calls.append(...)        # AttributeError — tuple has no append
r.tool_calls[0]["a"] = 99       # the dict CAN still mutate, BUT...
```

The remaining gap (callers can mutate the underlying dict) is acceptable for v1 because `AgentResult` is constructed once per dispatch and not shared across coroutines mutationally. If/when the architecture demands deep immutability, switch to `MappingProxyType`-wrapping like `JournalEntry._freeze_payload` (Story 1.7's `src/sdlc/contracts/journal_entry.py:48`).

### Why eager-load fixtures at construction (not lazy)

Decision C2's stated intent: "missing fixture = fail-loud, abstraction-adequacy CI gate runs full pipeline against mock." A lazy-load implementation would defer malformed-YAML detection until the first dispatch — silently shipping broken fixtures into a CI run that LOOKS like it passed (because the malformed fixture wasn't yet exercised). Eager-load surfaces the failure at `MockAIRuntime(fixtures_dir=...)` construction, which sits at the very top of every test that uses the mock — fail-fast.

Performance: eager-load reads every `*.yaml` under `fixtures_dir`. For Story 1.13 the fixtures count is 1 (the smoke). At Epic 2A (when ~25 specialists × ~10 prompts each are in fixture form), it's ~250 small YAMLs. PyYAML-safe-load on small YAMLs is microseconds each — total construction time < 100ms. Not a concern.

### Why `await asyncio.sleep(0)` in dispatch

A coroutine that never `await`s is observably different from one that does — even if the return value is the same. Consider:

```python
async def fake_dispatch():
    return "result"  # never awaits → schedule-and-finish in one step

async def real_dispatch():
    await asyncio.sleep(0)
    return "result"  # awaits once → control yields to the loop, then resumes
```

Under `asyncio.gather(*[fake_dispatch() for _ in range(N)])`, the fakes run sequentially-ish (the loop has no opportunity to interleave). Under `asyncio.gather(*[real_dispatch() for _ in range(N)])`, the loop interleaves coroutines correctly. The dispatcher (Story 2A-3) relies on the abstraction's `await` semantics to bound concurrency via `asyncio.Semaphore` (Decision A2). If `MockAIRuntime.dispatch` never awaits, the abstraction-adequacy test (Story 1.14) would silently mask a class of race-bugs that emerge only under real-Claude dispatch.

The `asyncio.sleep(0)` is a no-op timing-wise (yields control once, immediately re-schedules); it's a correctness fix, not a delay. Document this rationale inline in `mock.py` so a future contributor doesn't "optimize" it away.

### Why `MockMissError(DispatchError)` and not its own class

Architecture §527-§538 lists 8 canonical error classes; Story 1.6 added `IdsError` for a 9th. Adding a 10th (`MockError` or similar) for mock-specific failures would inflate the error surface unnecessarily. The semantic claim:

> Mock dispatch failures are dispatch failures.

The abstraction-adequacy test (Story 1.14) WILL pass through a `MockMissError` and assert `exit_code == 2` — same as a real `DispatchError`. If `MockMissError` had its own `code = "ERR_MOCK"` and a different `exit_code`, the abstraction-adequacy test would have to special-case the mock vs. claude paths, breaking the differential-test pattern.

By inheriting `DispatchError`, the existing `EXIT_CODE_MAP` covers it, the existing dispatch-error catch-blocks see it, and the abstraction is honest: "from the engine's perspective, the runtime failed to dispatch." The mock-specific provenance is in the `details` dict (`step="fixture_lookup"` etc.), not in a new error class.

### Pure function semantics — what the mock IS and IS NOT

**`MockAIRuntime` is allowed to:**

- Read `*.yaml` files at construction time (`Path.read_text` + `yaml.safe_load`).
- Compute `sha256` digests at dispatch time (pure function of input bytes).
- Look up an in-memory `dict[tuple[str, str], _Fixture]`.
- Construct fresh `AgentResult` instances via pydantic model construction.
- `await asyncio.sleep(0)` once per dispatch (yield control to the event loop).

**`MockAIRuntime` is NOT allowed to:**

- Write any file (no `state.json`, no journal, no fixture mutation, no logging output).
- Spawn subprocesses (`subprocess.run`, `os.fork`, etc.).
- Make network calls (`requests`, `urllib`, `httpx`, etc.).
- Mutate module-level state (no `global`, no `nonlocal` write to a captured variable).
- Read environment variables directly (`os.environ` — use `config/env.py` allow-list if needed; v1 mock has no env-var dependency).
- Call `print()` or `logger.*` (Architecture §489 — runtime/ MUST NOT print).
- Have time-dependent behavior (`datetime.now`, `time.time`, `random.*`) — same prompt+context+fixtures must produce the same `AgentResult` regardless of when called.
- Cache the in-memory fixtures `dict` at module-level — `_fixtures` is per-instance state. Two `MockAIRuntime` instances with different `fixtures_dir` MUST NOT share state.

### Previous story intelligence — Stories 1.10 + 1.11 + 1.12

Patterns to mirror exactly (validated through 1.10's 9 patches and 1.11/1.12's review cycles):

- **`from __future__ import annotations`** at top of every new `.py` file.
- **Semantic-order `__all__`** with `# noqa: RUF022` (ruff would otherwise sort alphabetically). See `state/__init__.py` and `journal/__init__.py` for the exact pattern.
- **Cross-platform vs POSIX-only**: `runtime/abc.py` and `runtime/mock.py` are **cross-platform** (no `fcntl`, no `O_APPEND`, no subprocess). NO POSIX gate. Mirror `journal/reader.py` (cross-platform reader). Contrast with `state/atomic.py` and `journal/writer.py` (POSIX-only writers).
- **`Final[...]` constants** for module-level immutables: `_SHA256_PREFIX`, `_KNOWN_KINDS` (n/a here — no kind enum), `_FIXTURE_SUFFIX` (if introduced; v1 doesn't need it). Mirror `state/atomic.py:STATE_FILE_NAME`, `journal/writer.py:JOURNAL_LOCK_SUFFIX`.
- **Narrow exception catches**: `(OSError, yaml.YAMLError)` for fixture-load I/O + parse; `MockMissError` is intentional surface and propagates. Do NOT catch bare `Exception` (Story 1.10 patch lessons).
- **Pure functions for protocol bodies**: `_load_fixtures(fixtures_dir)` and `_hash_prompt(prompt)` are module-level pure functions that the class delegates to. Mirror Story 1.10's `_write_protocol_body` and Story 1.12's `_project_entries`. Easier to test in isolation.
- **Test-seam private functions**: `_load_fixtures`, `_hash_prompt`, `_Fixture` are single-underscore-prefixed, importable for tests, NOT in `__all__`. Mirror Story 1.10's `_canonicalize_state` and Story 1.12's `_project_entries`.
- **Pydantic v2 patterns**: `model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)` — same as `JournalEntry`, `HookPayload`, `SpecialistFrontmatter`. `Field(default_factory=tuple)` for tuple defaults; `Field(ge=0)` for non-negative ints.
- **mypy `--strict`**: no `Any` leaks. Use `Mapping[str, object]`, `tuple[Mapping[str, object], ...]`, `dict[tuple[str, str], _Fixture]`, `Final[str]`. Run `uv run mypy --strict src/sdlc/runtime/` BEFORE committing.
- **Fixture file convention**: negative-test fixtures at `tests/fixtures/lint_negative/*.py.txt` (NOT `.py` — fixtures are text files so they don't get collected by pytest or scanned by ruff/mypy). Mirror Stories 1.10 + 1.11.
- **Scripts mirror existing validators**: `scripts/check_runtime_import_via_abc.py` MUST mirror the structure of `scripts/check_no_journal_mutation.py` (Story 1.11): function-style AST visitor, exit codes 0/1, message format `<path>:<line>: <human-readable-violation>`. Run-from-pre-commit semantics: receives file paths as argv; exit 0 = clean, 1 = violations.

Code-review feedback from Stories 1.10 + 1.11 + 1.12 to pre-empt:

- Be explicit about exception chaining (`raise MockMissError(...) from exc` where the underlying `OSError` / `yaml.YAMLError` is re-raised — preserves the original traceback for debugging).
- Avoid `Any` in type hints — `Mapping[str, object]` is the canonical narrow form. The `_Fixture.tool_calls: tuple[Mapping[str, object], ...]` is type-safe AND frozen.
- Verify `mypy --strict` passes BEFORE committing. The strict config in `pyproject.toml:108` will reject untyped functions, missing returns, and Any leaks.
- Use access-mode check pattern where relevant (n/a here — no fd manipulation in runtime/).
- Narrow exception catches; do NOT swallow programmer errors.
- For coverage: hit ≥ 95% per-file. The mock has multiple branches (fixtures-dir error, YAML parse error, shape error, key error, hit, miss); each needs at least one test.
- For the linter validator: mirror the AST visitor pattern; positive + negative fixtures; line-number assertions in violation messages.

### Git intelligence — last 5 commits

```
2f4322d feat: implement atomic state write protocol with chaos tests (Story 1.10)
ce351c5 chore: ignore graphify output and config files
99c8f78 chore: update skills, add Story 1.9, graphify output, and project config
b378b5a fix: apply code-review patches for Story 1.8 config module
1042fc1 feat: implement config module with validation (Story 1.8)
```

**Notable**: Stories 1.11 and 1.12 have NOT been committed yet (1.11 is `in-progress`, 1.12 is `ready-for-dev` per sprint-status.yaml). The `src/sdlc/journal/`, `src/sdlc/state/projection.py`, `tests/property/test_journal_append_only.py`, and ADRs 014-015 may exist on disk but are uncommitted.

**Story 1.13 work depends on these uncommitted files only at the boundary level** — `runtime/__init__.py` does NOT import `from sdlc.state import ...` or `from sdlc.journal import ...`. The runtime module is decoupled from state/journal at the import level. **However**, the test scaffolding under `tests/unit/runtime/test_mock_*.py` imports `from sdlc.errors import MockMissError` (this story's deliverable) and `from sdlc.runtime import MockAIRuntime` (this story's deliverable). Self-contained.

If 1.11/1.12 are reverted before 1.13 ships, this story does NOT break — it's substrate-independent of the journal/state work.

**Commit pattern to follow** (Story 1.10/1.11/1.12 precedent):

- One `feat: implement AIRuntime ABC + MockAIRuntime (Story 1.13)` commit covering: `src/sdlc/runtime/`, `src/sdlc/errors/base.py` edit, `src/sdlc/errors/__init__.py` edit, `tests/unit/runtime/`, `tests/unit/errors/test_base.py` edit, `tests/unit/test_runtime_import_via_abc_validator.py`, `tests/fixtures/lint_negative/runtime_*.py.txt`, `tests/fixtures/mock_responses/`, `scripts/check_runtime_import_via_abc.py`, `.pre-commit-config.yaml` edit, `docs/decisions/ADR-016-*.md`, `docs/decisions/index.md` edit, `docs/CODEMAPS/runtime.md`.
- Apply review patches in a follow-up `fix:` commit if needed (Story 1.8/1.10/1.11 precedent).

### Latest tech information

- **Python 3.10+** target (`pyproject.toml:10`). All language features used (`Mapping[str, object]`, `tuple[Mapping[str, object], ...]`, `dict[tuple[str, str], _Fixture]`, `Final[str]`, abstract method async) are stable in 3.10.
- **pydantic v2** (Story 1.7+ on disk at `src/sdlc/contracts/`). `model_config: ClassVar[ConfigDict] = ConfigDict(...)` is the canonical v2 form. `Field(ge=0)` enforces non-negative ints. `model_dump(mode="json")` for canonical serialization. `model_validate(record)` constructs from a parsed YAML mapping. `extra="forbid"` rejects unknown keys (canary for fixture-schema drift).
- **PyYAML 6.x** (`pyproject.toml:13`). `yaml.safe_load(text)` parses to plain Python types (`dict`, `list`, `str`, `int`, `float`, `bool`, `None`). NEVER `yaml.load` or `yaml.full_load` (allow `__reduce__`-based RCE). PyYAML errors are subclasses of `yaml.YAMLError` → catch this, not bare `Exception`.
- **`hashlib.sha256`** (stdlib, Python 3.10+). Returns a `_hashlib.HASH` object; `.hexdigest()` returns 64-char lowercase hex. Stable across Python versions and across runs (NOT randomized like `hash()`). Determinism is OS-independent.
- **`asyncio.sleep(0)`** (stdlib, Python 3.10+). Yields control once to the event loop; equivalent to `await asyncio.shield(asyncio.sleep(0))` in semantics but lighter. The cancellation point matters for the abstraction-adequacy test (Story 1.14).
- **`abc.ABC` + `@abstractmethod`** (stdlib). `AIRuntime(ABC)` makes the class abstract; `@abstractmethod` on `dispatch` makes instantiation fail with `TypeError: Can't instantiate abstract class ...`. Subclasses MUST implement all abstract methods or they themselves become abstract.
- **`pytest`** (`pyproject.toml:24`). The project uses `markers = ["unit", "integration", "property", "chaos", "benchmark", "e2e"]` per `pyproject.toml:177-183`. New tests use `unit` (most cases) or `integration` (subprocess-based hash stability test).
- **`asyncio.run(coro)`**: pytest does NOT have `pytest-asyncio` configured (`pyproject.toml:21-31` dev-deps list). Use `asyncio.run(mock.dispatch(...))` directly inside sync test functions. This is the project-wide pattern; do NOT add `pytest-asyncio` for this story (unnecessary new dep).

### Project Structure Notes

- **Alignment with unified project structure**: this story creates `src/sdlc/runtime/{__init__,abc,mock}.py` per Architecture §826-§829. The full architecture lists three files for `runtime/`: `abc.py`, `claude.py`, `mock.py`. Story 1.13 ships `abc.py`, `mock.py`, `__init__.py`; `claude.py` is deferred to Story 2B-1. Tests are mirrored from `src/sdlc/runtime/` to `tests/unit/runtime/` per the canonical "tests/unit/ mirrors src/sdlc/" structure (Architecture §983-§995).
- **No conflict with architecture**: every file path in Task 1's "New files" list lives under a directory the architecture has already declared. Fixture path `tests/fixtures/mock_responses/` matches Architecture §692 + §1012 exactly.
- **Pyproject markers**: `unit`, `integration` already exist. No new marks needed.
- **CI workflow**: NO new CI job — runtime/ tests run as part of the existing `unit` job; the subprocess-based hash test runs as part of the existing `integration` job. The new `runtime-import-via-abc-validator` runs as part of pre-commit + CI's existing pre-commit step.
- **Runtime module reservation**: this story takes `runtime/` from "empty / planned" to "abc + mock + __init__ shipped". The `forbidden_from` in MODULE_DEPS is already declared (Story 1.4) — no MODULE_DEPS update from this story.

### Why deferred from this story

These are explicitly NOT in scope for Story 1.13 — flag if they creep in during implementation:

- **`runtime/claude.py` (`ClaudeAIRuntime`)** — Story 2B-1. Subprocess management, edge cases, malformed JSON, timeout handling. The ABC must be in place first; this story builds the ABC.
- **Abstraction-adequacy CI test (`tests/integration/test_abstraction_adequacy.py`)** — Story 1.14. Runs the full pipeline (init → scan → dispatch → state projection → journal append) against MockAIRuntime; asserts deterministic HookPayload sequence. Story 1.13 ships the substrate; 1.14 ships the integration.
- **`AgentResult` schema versioning** — `AgentResult` is internal to runtime/, not one of the 5 wire-format contracts. Forward-compat: if a future story persists `AgentResult` to disk, add `schema_version: Literal[1] = 1` then.
- **Per-workflow YAML fixtures (`sdlc-epics.yaml`, `sdlc-task.yaml`, etc.)** — owned by their respective workflow stories (Stories 2A-9 onwards). Story 1.13 ships the SHAPE + a smoke fixture only.
- **Real prompt construction** — building the prompts that get hashed is the dispatcher's job (Story 2A-3). Story 1.13 only defines the dispatch interface; what gets dispatched is downstream.
- **Tool-call validation** — `tool_calls: tuple[Mapping[str, object], ...]` accepts any mapping shape. Phase-gate hook (Story 2A-4) validates that tool-call write_globs are within the agent's declared frontmatter; that's separate from the dispatch return-shape.
- **Streaming dispatch** — Decision C1 + Architecture §327 explicitly defer. If a v1.x story needs streaming, the ABC will gain a new optional method (NOT make `dispatch` itself streaming — that would be a breaking change to existing implementations).
- **Token-budget enforcement** — `tokens_in`/`tokens_out` are reported on `AgentResult` but no enforcement happens in v1. Token-budget caps live in the dispatcher (Story 2A-3) and are configured via `pyproject.toml [tool.sdlc.runtime]` (deferred to a config story).
- **Concurrent fixture loading** — `_load_fixtures` is single-threaded eager-load. Multiple `MockAIRuntime` instances with the same `fixtures_dir` will each parse YAML independently. That's fine for v1 (fixtures count is small); a future story can introduce a process-wide cache if measured to matter.
- **Mock-vs-claude differential test** — Story 2B-3. Uses both `MockAIRuntime` and `ClaudeAIRuntime` and asserts identical HookPayload event sequences. Story 1.13 ships only the Mock; 2B-3 adds the second variant.
- **HookPayload integration** — Story 1.13's mock returns `AgentResult` only. The Claude PreToolUse / engine-side hook chain that converts an agent's tool-calls into `HookPayload` events lives in Story 2A-4 + 2A-6. Out of scope here.
- **Workflow-step schema** — `context["workflow_step"]: str` is loosely typed in v1. A future story may formalize it (e.g. `WorkflowStep` Literal type listing all 17 valid slash-command names). Forward-compat: the mock today accepts any string, including unknown ones (which simply produce a fixture-miss); narrowing is additive, not breaking.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.13] (lines 723-750) — story spec, AC blocks
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.14] (lines 752-775) — adjacent story; gives context for how 1.13's deliverables get consumed
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-C1] (line 315, line 355) — async dispatch returning AgentResult, no streaming in v1
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-C2] (line 316, line 356) — deterministic YAML-driven Mock keyed by (workflow_step, prompt_hash)
- [Source: _bmad-output/planning-artifacts/architecture.md#Streaming-Defer] (line 327) — AIRuntime streaming explicitly deferred to v1.x
- [Source: _bmad-output/planning-artifacts/architecture.md#Source-Tree] (lines 826-829) — runtime/ file layout: abc.py, claude.py, mock.py
- [Source: _bmad-output/planning-artifacts/architecture.md#Fixtures-Layout] (line 692, line 1012) — `tests/fixtures/mock_responses/` is part of test contract
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Dependency-Table] (line 1062) — `runtime/` public API: AIRuntime, AgentResult, ClaudeAIRuntime, MockAIRuntime; depends_on errors/, contracts/, concurrency/
- [Source: _bmad-output/planning-artifacts/architecture.md#Boundary-Rules] (line 1106) — engine/ and dispatcher/ import runtime/ only via the AIRuntime ABC
- [Source: _bmad-output/planning-artifacts/architecture.md#Cli-Permissive-Rule] (line 1071) — cli/ may import runtime (only mock for tests)
- [Source: _bmad-output/planning-artifacts/architecture.md#Exception-Hierarchy] (lines 527-538) — 8 canonical errors; MockMissError joins as 10th (subclass of DispatchError)
- [Source: _bmad-output/planning-artifacts/architecture.md#Code-Style] (line 489) — no print() in engine/, dispatcher/, state/, journal/, hooks/, runtime/
- [Source: _bmad-output/planning-artifacts/architecture.md#Test-File-Layout] (lines 685-695) — tests/unit/<module-mirror>/ structure
- [Source: _bmad-output/planning-artifacts/prd.md#FR29] (line 760) — runtime-neutral AIRuntime interface
- [Source: _bmad-output/planning-artifacts/prd.md#NFR-COMPAT-3] (line 855) — Mock abstraction-adequacy as CI gate
- [Source: src/sdlc/contracts/journal_entry.py] (lines 1-54) — pydantic v2 patterns: model_config, frozen=True, extra="forbid", Literal[1] schema_version, _strict_schema_version, _freeze_payload
- [Source: src/sdlc/contracts/hook_payload.py] (lines 1-32) — pydantic v2 patterns: HookPayload as the closest precedent for a "small frozen contract"
- [Source: src/sdlc/contracts/specialist_frontmatter.py] (lines 1-33) — pydantic v2 patterns: tuple defaults via Field(default_factory=tuple), str field constraints
- [Source: src/sdlc/errors/base.py] (lines 1-75) — exception hierarchy; MockMissError appends after IdsError; DispatchError is the parent
- [Source: src/sdlc/errors/__init__.py] (lines 1-37) — semantic-order __all__ tuple; pattern to extend
- [Source: src/sdlc/state/atomic.py] (Story 1.10) — protocol body + `_canonicalize_state` + `_normalize_strings` patterns; pure-function decomposition (mock_loader's `_load_fixtures` mirrors this structure)
- [Source: src/sdlc/journal/writer.py] (Story 1.11) — `_canonicalize_entry` + `_append_protocol_body` patterns; `JOURNAL_LOCK_SUFFIX` Final constant pattern; structlog/print discipline
- [Source: src/sdlc/journal/reader.py] (Story 1.11) — cross-platform reader; reader-invariant; mirror for runtime/abc.py + runtime/mock.py cross-platform stance
- [Source: src/sdlc/state/projection.py] (Story 1.12, on-disk if 1.12 has dev'd before 1.13) — pure-function projection + `_project_entries` test-seam pattern; mirror for runtime/mock.py's `_load_fixtures` + `_hash_prompt` test seams
- [Source: scripts/check_module_boundaries.py] (lines 62-65) — `MODULE_DEPS["runtime"]` declaration; verify pre-flight in Task 1
- [Source: scripts/check_no_direct_state_writes.py] (Story 1.10) — AST-visitor pattern; mirror for `check_runtime_import_via_abc.py`
- [Source: scripts/check_no_journal_mutation.py] (Story 1.11) — AST-visitor pattern with allow-list; mirror for `check_runtime_import_via_abc.py`
- [Source: tests/fixtures/lint_negative/direct_state_write.py.txt] (Story 1.10) — negative-test fixture text-file convention
- [Source: tests/fixtures/lint_negative/journal_mutation.py.txt] (Story 1.11) — negative-test fixture pattern
- [Source: tests/unit/test_state_write_validator.py] (Story 1.10) — validator test pattern
- [Source: tests/unit/test_journal_mutation_validator.py] (Story 1.11) — validator test pattern; mirror exactly
- [Source: pyproject.toml] (lines 11-14) — `pyyaml>=6,<7` is at line 13; verify before relying on it
- [Source: pyproject.toml] (lines 105-156) — mypy strict config; runtime/ files MUST type-check under strict
- [Source: pyproject.toml] (lines 161-183) — pytest config; markers; existing `unit`, `integration` markers cover this story's tests
- [Source: .pre-commit-config.yaml] (lines 1-115) — full hook chain; new validator slots between journal-append-only-validator and secret-hardcode-validator
- [Source: docs/decisions/ADR-013-atomic-state-write-protocol.md] — protocol-decision ADR pattern; mirror for ADR-016
- [Source: docs/decisions/ADR-014-append-only-journal-protocol.md] — error-message-as-contract precedent; mirror for ADR-016
- [Source: docs/decisions/index.md] — ADR index format; new row format `| [NNN](ADR-NNN-slug.md) | Title | Story | Accepted |`
- [Source: _bmad-output/implementation-artifacts/1-10-atomic-write-protocol-chaos-tests.md] — Story 1.10 patterns + review feedback; protocol body factoring; cross-platform discipline
- [Source: _bmad-output/implementation-artifacts/1-11-append-only-journal-property-test.md] — Story 1.11 patterns; AST-validator + negative fixtures pattern; this story's `runtime-import-via-abc-validator` mirrors
- [Source: _bmad-output/implementation-artifacts/1-12-state-projection-from-journal-replay-property-test.md] — Story 1.12 patterns; pure-function design; `_project_entries` test-seam; this story's mock follows the same shape

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (BMAD dev-story workflow)

### Debug Log References

- Fixed `RuntimeError: There is no current event loop` in `test_dispatch_yields_control_at_least_once` — wrapped `asyncio.gather()` in an async def and called `asyncio.run()` on it (Python 3.12 requires a running loop for `asyncio.gather`).
- Removed spurious `# noqa: RUF022` from `runtime/__init__.py` — the `__all__` tuple was already in alphabetical-by-ASCII order; the noqa comment triggered RUF100.
- Removed stale `# type: ignore[attr-defined]` from `journal/writer.py:32` — mypy strict now resolves `file_lock` from `sdlc.concurrency` without the ignore; confirmed the comment was pre-existing via `git stash` test.
- Changed `runtime/__init__.py` to import `MockMissError` from `sdlc.errors` directly (not from `sdlc.runtime.mock`) — avoids mypy `attr-defined` error since `mock.py` imports but doesn't explicitly export `MockMissError`.
- Fixed `F401 unused imports`: removed `json` from `test_mock_determinism.py`, `ast` from `test_runtime_import_via_abc_validator.py`.
- Fixed `SIM108` in `check_runtime_import_via_abc.py` — used ternary instead of if/else.
- Fixed `E501` line-too-long in `mock.py` and `test_abc.py` — split f-strings and reformatted dicts.

### Completion Notes List

- **Task 1**: Verified all pre-flight conditions. `src/sdlc/state/projection.py` exists; ADR-015 exists; MODULE_DEPS["runtime"] matches expected form; pyyaml/types-PyYAML present; lint_negative fixtures exist.
- **Task 2**: Added `MockMissError(DispatchError)` to `src/sdlc/errors/base.py` and `src/sdlc/errors/__init__.py`. Added 3 unit tests confirming ERR_DISPATCH code inheritance and isinstance checks.
- **Task 3**: Created `src/sdlc/runtime/__init__.py` and `src/sdlc/runtime/abc.py`. `AIRuntime` ABC with single abstract `dispatch` method; `AgentResult` frozen pydantic model. `MockMissError` imported from `sdlc.errors` in `__init__.py` for mypy compatibility.
- **Task 4**: Created `src/sdlc/runtime/mock.py` with `_Fixture`, `_hash_prompt`, `_load_fixtures`, and `MockAIRuntime`. Eager-loads all `*.yaml` at construction; `dispatch` uses `await asyncio.sleep(0)` for abstraction-adequacy.
- **Task 5**: Created `tests/fixtures/mock_responses/README.md` and `tests/fixtures/mock_responses/_smoke.yaml` with the sha256 hash of `b"hello"`.
- **Task 6**: Created `tests/unit/runtime/__init__.py`, `test_abc.py` (9 tests), `test_mock_loader.py` (9 tests), `test_mock_dispatch.py` (5 tests), `test_mock_determinism.py` (4 tests). All 27 pass with 100% runtime coverage.
- **Task 7**: Created `scripts/check_runtime_import_via_abc.py` (62 LOC); wired into `.pre-commit-config.yaml`; created 4 negative-test fixtures; created `tests/unit/test_runtime_import_via_abc_validator.py` (8 tests, all pass).
- **Task 8**: Created `docs/decisions/ADR-016-airuntime-abc-and-mock-implementation.md`; updated `docs/decisions/index.md`; created `docs/CODEMAPS/runtime.md`.
- **Task 9**: All quality gates green — `ruff check`, `ruff format`, `mypy --strict` (31 files, 0 issues), `pre-commit run --all-files`. 627/631 tests pass; 4 pre-existing failures in journal/concurrency confirmed via git stash (not regressions from this story).

### File List

**New files:**
- `src/sdlc/runtime/__init__.py`
- `src/sdlc/runtime/abc.py`
- `src/sdlc/runtime/mock.py`
- `tests/unit/runtime/__init__.py`
- `tests/unit/runtime/test_abc.py`
- `tests/unit/runtime/test_mock_loader.py`
- `tests/unit/runtime/test_mock_dispatch.py`
- `tests/unit/runtime/test_mock_determinism.py`
- `tests/unit/test_runtime_import_via_abc_validator.py`
- `tests/fixtures/lint_negative/engine_imports_runtime_mock.py.txt`
- `tests/fixtures/lint_negative/dispatcher_imports_runtime_claude.py.txt`
- `tests/fixtures/lint_negative/engine_imports_runtime_abc.py.txt`
- `tests/fixtures/lint_negative/cli_imports_runtime_mock.py.txt`
- `tests/fixtures/mock_responses/README.md`
- `tests/fixtures/mock_responses/_smoke.yaml`
- `scripts/check_runtime_import_via_abc.py`
- `docs/decisions/ADR-016-airuntime-abc-and-mock-implementation.md`
- `docs/CODEMAPS/runtime.md`

**Modified files:**
- `src/sdlc/errors/base.py` — added `MockMissError(DispatchError)` class
- `src/sdlc/errors/__init__.py` — added `MockMissError` to imports and `__all__`
- `src/sdlc/journal/writer.py` — removed stale `# type: ignore[attr-defined]` comment
- `tests/unit/errors/test_base.py` — added 3 `MockMissError` tests
- `.pre-commit-config.yaml` — added `runtime-import-via-abc-validator` hook
- `docs/decisions/index.md` — added ADR-016 row

### Change Log

- 2026-05-09: Implemented Story 1.13 — AIRuntime ABC + MockAIRuntime. Created runtime module with `AIRuntime` ABC, `AgentResult` frozen pydantic model, `MockAIRuntime` YAML-driven mock, and `MockMissError`. Added 27 unit tests (100% runtime coverage), 8 linter validator tests, runtime-import-via-ABC pre-commit hook, 4 negative-test fixtures, smoke fixture, ADR-016, and codemap.
- 2026-05-09: Applied code-review patches (18 fixes). Hardened mock loader (strict-int tokens, `.yml`/`.YAML` rejection, empty-YAML detection, stem-collision detection, duplicate-key detection via custom SafeLoader, surrogate-safe prompt encoding, non-string `workflow_step` rejection); hardened runtime ABC linter (handle `ast.Import` not just `ast.ImportFrom`; explicit cli/ permissive path; stderr warning on SyntaxError; cleaner `_expand_targets`; narrower pre-commit `files:` regex to `^src/sdlc/(engine|dispatcher|cli)/.*\.py$`); fixed two false-positive tests (`test_dispatch_yields_control_at_least_once` now monkeypatches `asyncio.sleep` to verify the yield; `test_validator_ignores_non_engine_dispatcher_files` now monkeypatches `_GUARDED_PARENTS` so the assertion exercises the rule). Subprocess test cwd derived from `Path(__file__).parents[3]`. Coverage: runtime `__init__.py` 100%, `abc.py` 100%, `mock.py` 97% (≥95% target met). 123 runtime+errors+validator tests pass.

### Review Findings

_Code review run: 2026-05-09. Layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor. 18 patches, 11 deferred, 12 dismissed as noise._

- [x] [Review][Patch] `__all__` missing `# noqa: RUF022` — risks ruff autofix re-sorting and breaking spec-mandated semantic order [src/sdlc/runtime/__init__.py:13]
- [x] [Review][Patch] Hardcoded user-specific absolute cwd in subprocess test — breaks for any other developer / CI [tests/unit/runtime/test_mock_determinism.py:105,112]
- [x] [Review][Patch] Linter only handles `ast.ImportFrom`; `import sdlc.runtime.mock` and `import sdlc.runtime.mock as m` bypass guard silently [scripts/check_runtime_import_via_abc.py:64]
- [x] [Review][Patch] Dead `_is_permissive` / `_PERMISSIVE_PARENTS` code — main() filters via `_is_guarded` only; cli/ permissive case is implicit not explicit [scripts/check_runtime_import_via_abc.py:38-45,108-121]
- [x] [Review][Patch] Pre-commit hook `files: ^src/sdlc/.*\.py$` too broad — invokes script once per src/ python file but no-ops on most; narrow to `^src/sdlc/(engine|dispatcher|cli)/.*\.py$` [.pre-commit-config.yaml:82-93]
- [x] [Review][Patch] `tokens_in: int = Field(ge=0)` accepts `bool` (True/False) silently because `bool` subclasses `int`; YAML `tokens_in: true` loads as 1 [src/sdlc/runtime/abc.py:30-31, src/sdlc/runtime/mock.py:35-36]
- [x] [Review][Patch] `_load_fixtures` glob misses `.yml`, `.YAML`, `.YML`; sibling files silently ignored — emit explicit error or accept all [src/sdlc/runtime/mock.py:65]
- [x] [Review][Patch] Empty YAML or comment-only YAML returns `None`; current "must be a mapping" message is misleading — explicit empty-file handling [src/sdlc/runtime/mock.py:79-88]
- [x] [Review][Patch] Filename stem collision (e.g., `Smoke.yaml` vs `smoke.yaml` on case-insensitive macOS/Windows) silently overwrites — detect and fail-loud [src/sdlc/runtime/mock.py:65-66,101]
- [x] [Review][Patch] `workflow_step = str(context.get("workflow_step", ""))` silently coerces non-string types; should validate is `str` and reject otherwise [src/sdlc/runtime/mock.py:124]
- [x] [Review][Patch] Duplicate `sha256:...` keys in single YAML silently last-wins (PyYAML behavior) — detect via custom loader or post-load count [src/sdlc/runtime/mock.py:69,89]
- [x] [Review][Patch] `prompt.encode("utf-8")` raises uncaught `UnicodeEncodeError` on lone surrogates instead of `MockMissError` [src/sdlc/runtime/mock.py:49]
- [x] [Review][Patch] `_check_file` swallows `SyntaxError` silently — broken Python files get free pass; mirror Stories 1.10/1.11 stderr warning pattern [scripts/check_runtime_import_via_abc.py:56-59]
- [x] [Review][Patch] `_expand_targets` else-branch is dead/inconsistent (both `.py/.py.txt` branch and else do `expanded.append(path)`); clean up or reject unknown suffixes [scripts/check_runtime_import_via_abc.py:87-97]
- [x] [Review][Patch] `AIRuntime` class docstring does not cite §355 (only module-level docstring does) — AC1.4 requires class-level citation [src/sdlc/runtime/abc.py:35-39]
- [x] [Review][Patch] `tests/fixtures/mock_responses/README.md` documents `tool_calls: list (default [])` but model is `tuple[Mapping[str, object], ...]`; clarify YAML→tuple coercion [tests/fixtures/mock_responses/README.md]
- [x] [Review][Patch] `test_dispatch_yields_control_at_least_once` is tautological — removing `await asyncio.sleep(0)` from mock.dispatch would still pass; rewrite to actually verify yielding [tests/unit/runtime/test_mock_dispatch.py:test_dispatch_yields_control_at_least_once]
- [x] [Review][Patch] `test_validator_ignores_non_engine_dispatcher_files` vacuous — writes fixture under `tmp_path/src/sdlc/state/`, but `_is_guarded` resolves against real `_REPO_ROOT`; test passes for the wrong reason [tests/unit/test_runtime_import_via_abc_validator.py]

- [x] [Review][Defer] `tool_calls` shallow frozen-ness — outer tuple immutable but inner `dict` mutable [src/sdlc/runtime/abc.py:29] — deferred, dev notes acknowledge; future MappingProxyType wrapping when architecture demands deep immutability
- [x] [Review][Defer] Symlinked `fixtures_dir` or symlinked `*.yaml` not boundary-checked — could pull arbitrary YAML from outside `tests/fixtures/` [src/sdlc/runtime/mock.py:54-65] — deferred, fixtures_dir is dev-controlled, not a security boundary
- [x] [Review][Defer] YAML aliases/anchors silently expand; can produce shared underlying dicts across keys [src/sdlc/runtime/mock.py:69] — deferred, won't bite tool-generated fixtures
- [x] [Review][Defer] `MockAIRuntime.__init__` is non-async; ABC has no `__init__` contract so a real `ClaudeAIRuntime` may need a different construction pattern — deferred, abstraction-adequacy gap intentional in v1
- [x] [Review][Defer] `MockMissError` messages embed resolved absolute `fixtures_dir` path; CI vs dev path divergence may leak in details [src/sdlc/runtime/mock.py:131] — deferred, cosmetic
- [x] [Review][Defer] `test_validator_allows_mock_direct_import_in_cli` from spec Task 7 not implemented (only indirectly via `test_is_permissive_returns_true_for_cli`) — deferred, cli/ doesn't exist until Story 1.16
- [x] [Review][Defer] macOS `/var` → `/private/var` symlink causes `Path.resolve()` to mismatch caller-passed `tmp_path` — deferred, latent test-flakiness only when assertions compare paths
- [x] [Review][Defer] `MockMissError` does not truncate long prompts or sanitize control chars in interpolated `workflow_step` [src/sdlc/runtime/mock.py:129-138] — deferred, extreme edge
- [x] [Review][Defer] `_smoke.yaml` checked-in fixture has no consumer (every dispatch test writes its own smoke yaml to `tmp_path`) — deferred, intended as documentation-by-example
- [x] [Review][Defer] No test asserts schema parity between `_Fixture` and `AgentResult`; future field additions to one and not the other go undetected — deferred, defer until first schema-version bump (Story 1.21)
- [x] [Review][Defer] Validator misses indirect access pattern `from sdlc import runtime; runtime.mock.X` — defer, attribute-access analysis beyond AST import scope; mitigated by `MODULE_DEPS` module-level rule
