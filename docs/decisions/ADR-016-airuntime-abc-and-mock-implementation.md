# ADR-016: AIRuntime ABC + MockAIRuntime Implementation

**Status:** Accepted
**Date:** 2026-05-09
**Story:** 1.13

## Context

Decision C1 + C2 (Architecture §315-§316, §355-§356) require an async dispatch ABC plus a
deterministic Mock for the abstraction-adequacy CI test (Story 1.14). FR29 + NFR-COMPAT-3
require runtime-neutrality from v1. Architecture §1062 declares `AIRuntime`, `AgentResult`,
`ClaudeAIRuntime`, `MockAIRuntime` as the runtime/ public API; this story ships the first
three (Claude is Story 2B-1).

The existing `boundary-validator` (Story 1.4) enforces module-level isolation (`engine →
runtime` forbidden), but cannot distinguish "allowed" `from sdlc.runtime import AIRuntime`
(canonical re-export) from "forbidden" `from sdlc.runtime.mock import MockAIRuntime`. A
new AST-level validator is needed to enforce Architecture §1106 at sub-module granularity.

`AgentResult` is an *internal* dispatch return shape, NOT one of the 5 wire-format contracts
(`JournalEntry`, `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec`) that
are persisted to disk and shared across the trust boundary. This asymmetry is intentional:
`AgentResult` does not carry `schema_version` in v1 because it is never written to disk.

## Decision

1. **ABC at `src/sdlc/runtime/abc.py`**: single `@abstractmethod async def dispatch(prompt,
   context) -> AgentResult`. No streaming (Decision C1, deferred per Architecture §327).

2. **`AgentResult`** is a frozen pydantic v2 model with 4 fields: `output_text, tool_calls,
   tokens_in, tokens_out` (Architecture §355). Uses `tuple[Mapping[str, object], ...]` for
   `tool_calls` to achieve real frozen-ness (pydantic v2 `frozen=True` does not deep-freeze
   list members).

3. **Mock at `src/sdlc/runtime/mock.py`**: eager-loads `tests/fixtures/mock_responses/*.yaml`
   at construction; dispatch keyed by `(workflow_step, prompt_hash)` where
   `prompt_hash = "sha256:" + sha256(prompt.encode("utf-8")).hexdigest()`. Missing key raises
   `MockMissError` with a recovery-path message naming the YAML file + key to add.

4. **`MockMissError(DispatchError)`** — inherits `code="ERR_DISPATCH"`, `exit_code=2` so
   abstraction-adequacy tests propagate identically to a real Claude dispatch failure.

5. **New pre-commit hook `runtime-import-via-abc-validator`** (`scripts/check_runtime_import_via_abc.py`)
   enforces Architecture §1106 at AST-level granularity. The existing `boundary-validator`
   operates at module-level; this hook adds sub-module import precision.

6. **YAML fixture format**: top-level mapping of `sha256:<hex>` → `{output_text, tool_calls,
   tokens_in, tokens_out}`. One YAML file per `workflow_step`.

7. **`await asyncio.sleep(0)` in dispatch**: yields control once per call so the event loop
   can interleave coroutines. A coroutine that never yields is observably different from one
   that does; removing this would mask race-bugs under the dispatcher's `asyncio.Semaphore`
   concurrency bound (Decision A2, Story 2A-3).

## Alternatives Considered

- **JSON fixtures instead of YAML** — rejected: YAML is human-friendlier for multi-line
  `output_text` (Claude responses are paragraphs), and PyYAML is already a top-level dep.

- **Lazy fixture loading at dispatch** — rejected: defeats fail-loud on construction;
  malformed fixtures would surface only at first miss, not at `MockAIRuntime(...)` construction.

- **Streaming in v1 (`async def stream() -> AsyncIterator[ChunkType]`)** — explicitly
  deferred per Decision C1, Architecture §327.

- **`tool_calls: list[dict]` vs `tuple[Mapping, ...]`** — chose tuple+Mapping for real
  frozen-ness; pydantic v2's `frozen=True` does not deep-freeze list members.

- **Adding `workflow_step: str` field to `AgentResult`** — rejected: leaks mock-impl detail
  into the contract; the abstraction-adequacy test verifies behavior, not provenance.

- **Separate `MockError` class** — rejected: mock dispatch failures are dispatch failures.
  Inheriting `DispatchError` keeps the error surface at 9 classes and ensures abstraction-
  adequacy tests propagate `exit_code=2` identically to real Claude failures.

## Consequences

- **Forward-contract**: `MockMissError` message names YAML file + key — future Story 2A-9+
  will add per-workflow fixtures keyed by exactly this format.

- **ABC-only import gap documented**: the existing `boundary-validator` cannot distinguish
  sub-module imports. The new `runtime-import-via-abc-validator` covers this gap. Adding a
  future fourth runtime (e.g. Cursor in v2) requires no validator change in the typical case.

- **`_Fixture` and `_load_fixtures` are private** (single-underscore prefix; not in `__all__`).
  If a future story (e.g. 2B-3 abstraction-adequacy mock-vs-claude) needs to introspect
  fixtures, that's the time to promote them.

- **Per-workflow fixtures** (`sdlc-epics.yaml`, `sdlc-task.yaml`, etc.) are owned by their
  respective workflow stories (Stories 2A-9 onwards). Story 1.13 ships the SHAPE + a smoke
  fixture only.

- **ADR-015 order note**: ADR-015 (state projection from journal, Story 1.12) was authored
  before this ADR. Both were committed in a single sprint push; the dependency ordering
  (1.12 ADR-015 → 1.13 ADR-016) is preserved in commit history.

## References

Architecture §315-§316, §327, §355-§356, §492, §527-§538, §692, §826-§829, §1012, §1062,
§1106. PRD §FR29, §NFR-COMPAT-3. ADR-013 (atomic state write protocol — pattern precedent).
ADR-014 (append-only journal protocol — error-message-as-contract precedent). ADR-015 (state
projection — fail-loud-with-recovery-path precedent).
