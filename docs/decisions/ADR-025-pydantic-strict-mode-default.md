# ADR-025: Pydantic Strict-Mode Default

**Status:** Proposed (2026-05-10, Epic 2A prep — Story 2A.1)

## Context

Epic 1 retrospective (2026-05-09, §3 Pattern 4 "Pydantic Lax-Mode Coercion Bugs") identified
recurring silent-coercion failures across Stories 1.7, 1.8, 1.13:

- `Literal[1]` accepted `True` and `1.0` (boolean and float collapsing onto integer literal 1)
- Integer fields accepted `bool` (since `bool` is a subclass of `int` in Python — pydantic
  inherits this in lax mode)
- Float `4.5` silently truncated to `4` when target type was `int`

Each story addressed the bug locally with `Field(strict=True)` per field. This produced:

1. **Inconsistent surface** — some fields strict, others not; reviewer cognitive load to track.
2. **Drift risk** — newly added fields default to lax mode unless author remembers `strict=True`.
3. **Wire-format implications** — wire-format contracts (frozen at v1 per ADR-024) must reject
   adversarial inputs by construction, not by per-field discipline.

Epic 2A Story 2A.1 (`WorkflowSpec` loader) is the immediate dependency: loader must reject
instruction-shaped strings in unexpected fields per NFR-SEC-7 adversarial fixtures. Lax-mode
coercion would let `True` slip through where `Literal[1]` is expected, defeating the static check.

Per retrospective debt item **D2** (owner: Winston, priority HIGH, blocks Story 2A.1, ~0.3 day).

## Decision

1. **Project-wide default:** All pydantic v2 `BaseModel` subclasses use strict-mode validation
   via a base-class helper:

   ```python
   from pydantic import BaseModel, ConfigDict

   class StrictModel(BaseModel):
       model_config = ConfigDict(
           strict=True,         # reject lax type coercion globally
           extra="forbid",      # already required by ADR-024 for wire-format contracts
           frozen=True,         # already required by ADR-024 for wire-format contracts
       )
   ```

2. **Surface:** `src/sdlc/contracts/_strict_model.py` exports `StrictModel`. All five wire-format
   contracts (`JournalEntry`, `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`,
   `WorkflowSpec`) inherit from `StrictModel` rather than `BaseModel`. Internal-only models
   (e.g. CLI argument parsers, ephemeral DTOs) MAY opt out via direct `BaseModel` inheritance
   when documented in-line with reason.

3. **Lint enforcement:** A new AST visitor in `scripts/lint/check_strict_model_inheritance.py`
   (paired pre-commit + pytest gate, mirroring the wire-format-lock pattern in ADR-024) asserts
   that any class extending `pydantic.BaseModel` directly inside `src/sdlc/contracts/` carries
   an `# strict-opt-out: <reason>` comment on the class line. Default deny.

4. **Migration:** Stories 1.7, 1.8, 1.13 retain their per-field `Field(strict=True)` calls until
   the next contract-version migration; the inherited base config supersedes them but does not
   conflict. Per-field calls become redundant and are scheduled for removal in Epic 2A's
   debt-reduction parallel-prep slot (P-task to be assigned).

## Alternatives Considered

- **A. Per-field `Field(strict=True)` everywhere** — rejected: status quo. Drift risk persists;
  reviewer burden compounds across Epic 2A's 20 stories.
- **B. Global pydantic plugin / monkey-patch** — rejected: opaque, hostile to mypy and IDE
  navigation; violates "load-bearing decisions are explicit" principle (cf. ADR-012).
- **C. Strict mode only on wire-format contracts (5 classes), lax elsewhere** — rejected: the
  wire-format / non-wire-format split is not a clear boundary in practice (e.g. `WorkflowSpec`
  embeds nested step-models), and reviewers would re-debate the boundary on every new model.

## Consequences

- **+** Adversarial-input robustness becomes structural. NFR-SEC-7 fixtures pass without
  per-field hardening.
- **+** Reviewer reads class definition once, knows strict-mode applies. Cognitive load per
  Epic 2A review drops.
- **+** Foundation for future strict-only invariants (e.g. UUID-only ID fields per `ids/` module).
- **−** Adoption cost: 5 wire-format contracts + ~10 internal models must be touched in P-task
  cleanup. Not free.
- **−** Strict mode is stricter than legacy callers expect — any external integration ingesting
  legacy lax-mode JSON (e.g. older test fixtures) must pre-coerce types before
  validation. Mitigation: a one-time fixture-audit pass in Epic 2A prep.
- **−** Lint gate is a new always-on check; failures must surface clear remediation
  ("add `# strict-opt-out: <reason>` or inherit from `StrictModel`").

## Revisit-by

2026-11-10 — or when the first cross-version contract migration ships (Epic 2B real-Claude
adopt + first `schema_version=2` bump), whichever comes first.
