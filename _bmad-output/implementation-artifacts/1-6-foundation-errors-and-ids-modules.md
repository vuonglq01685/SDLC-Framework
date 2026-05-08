# Story 1.6: Foundation — `errors/` and `ids/` Modules

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer building the dependency leaves first per Architecture §1100 (`errors/` is the deepest leaf; `ids/` depends only on `errors/`),
I want the canonical `errors/` exception hierarchy (`SdlcError` + named subclasses with machine-readable `code` fields, exit-code mapping per Architecture §540, secret-aware error envelope per Architecture §549) and the `ids/` identifier-parsing/-building module (canonical regex constants, frozen dataclass return types, BDD-stable invalid-ID messages) implemented with ≥95% line+branch coverage and ≥0 mypy-strict diagnostics, all under the active 16-module boundary-validator hook from Story 1.4 (which already grants `errors → ∅` and `ids → {errors}` per `scripts/check_module_boundaries.py:30-37`),
So that all higher modules (`contracts/` next in Story 1.7, then `config/`, `concurrency/`, `state/`, `journal/`, …) can import these two leaf modules without circular-dependency risk, every framework-emitted error carries a stable `code` for the `--json` envelope + CLI exit-code routing, every epic/story/task identifier flowing through CLI/dispatcher/hooks is parsed and re-built through one canonical surface, and the architecture-canonical 8-subclass exception taxonomy plus the per-AC 9th `IdsError` subclass become the single source of truth that downstream modules in Stories 1.7–1.21 build against (resolving the epic-vs-architecture subclass-naming variance flagged in Dev Notes below).

## Acceptance Criteria

**AC1 — `src/sdlc/errors/` ships the 8 architecture-canonical subclasses + `IdsError` (9 total non-root) under one `SdlcError` root, every subclass declares a `ClassVar[str] code`, and the package surface re-exports everything via `sdlc.errors`.**

**Given** Story 1.4 complete (boundary-validator hook active; `MODULE_DEPS["errors"]` declared with `depends_on=frozenset()`, `forbidden_from=frozenset()` per `scripts/check_module_boundaries.py:30-33`) **AND** Story 1.5 complete (ADR-012 documents the 16-module DAG; ADR template available at `docs/decisions/adr-template.md`)
**When** I import `from sdlc.errors import SdlcError, StateError, JournalError, SignoffError, DispatchError, HookError, SchemaError, AdoptError, ConfigError, IdsError`
**Then** all 10 names resolve cleanly (1 root + 9 subclasses)
**And** `SdlcError` is the sole base; every other class inherits **directly** from `SdlcError` (one-level hierarchy — Architecture §526–§538 shows the subclasses as direct children of `SdlcError`, no intermediate parents)
**And** every concrete class declares `code: ClassVar[str]` matching the table below — codes are SCREAMING_SNAKE_CASE, prefixed `ERR_`, and stable across the v0.x line (changing a code is a wire-format break per Decision F3):

| Class | `code` value | Exit code (Architecture §541) | Architecture rationale |
|---|---|---|---|
| `SdlcError` | `ERR_SDLC` (root catch-all; not normally raised) | n/a (abstract-ish; subclasses always preferred) | §529 — root |
| `StateError` | `ERR_STATE` | 2 | §530 — `state.json` read/write/validation |
| `JournalError` | `ERR_JOURNAL` | 2 | §531 — journal append/read/replay |
| `DispatchError` | `ERR_DISPATCH` | 2 | §532 — agent dispatch / retry exhaustion |
| `HookError` | `ERR_HOOK` | 2 | §533 — hook execution / hook tampering |
| `SchemaError` | `ERR_SCHEMA` | 2 | §534 — pydantic validation / migration |
| `SignoffError` | `ERR_SIGNOFF` | 2 | §535 — hash drift / approval refusal |
| `AdoptError` | `ERR_ADOPT` | 2 | §536 — adopt-mode source-modification attempt |
| `ConfigError` | `ERR_CONFIG` | 1 | §537 — missing env / malformed `project.yaml` |
| `IdsError` | `ERR_IDS` | 1 | Story 1.6 addition (see Dev Notes "Epic-vs-Architecture variance: 9th subclass `IdsError`") |

**And** `SdlcError.__init__` accepts `(message: str, *, details: dict[str, object] | None = None)`; sets `self.message = message`, `self.details = dict(details) if details else {}` (defensive copy — defaults must NOT share state across instances), and calls `super().__init__(message)` so the standard `str(e)` machinery returns the message
**And** `SdlcError` exposes `to_envelope() -> dict[str, object]` returning the `--json` mode shape from Architecture §549–§560: `{"error": {"code": <self.code>, "message": <self.message>, "details": <self.details>, "exit_code": <self.exit_code>}}`
**And** `SdlcError` exposes a class-level mapping `EXIT_CODE_MAP: ClassVar[dict[str, int]]` declaring `{"ERR_CONFIG": 1, "ERR_IDS": 1, "ERR_STATE": 2, "ERR_JOURNAL": 2, "ERR_DISPATCH": 2, "ERR_SCHEMA": 2, "ERR_SIGNOFF": 2, "ERR_HOOK": 2, "ERR_ADOPT": 2}` and a `@property exit_code` that resolves via `EXIT_CODE_MAP.get(self.code, 2)` (default-2 for unknown — framework-failure semantics per Architecture §546)
**And** `src/sdlc/errors/__init__.py` re-exports the 10 names plus `EXIT_CODE_MAP` via an explicit `__all__` (immutable tuple style) so star-imports from downstream modules surface only the canonical names
**And** `src/sdlc/errors/base.py` is the single implementation file (Architecture §919–§920 — `errors/` directory contains exactly `base.py` plus the package `__init__.py`); LOC count of `base.py` is ≤ 200 (well under the 400 ceiling — comfortable headroom for the secret-sanitization hook the future ADR may add)

**AC2 — `src/sdlc/ids/` ships canonical regex constants (frozen at module level), three `parse_*` functions (epic/story/task), three `build_*` functions, and three immutable dataclass return types — all behind a public surface re-exported via `sdlc.ids`.**

**Given** AC1 complete (errors/ available for `IdsError` raise) **AND** Architecture §424–§441 + §1055 specify the identifier conventions
**When** I import `from sdlc.ids import (parse_epic_id, parse_story_id, parse_task_id, build_epic_id, build_story_id, build_task_id, EpicId, StoryId, TaskId, EPIC_ID_REGEX, STORY_ID_REGEX, TASK_ID_REGEX)`
**Then** all 12 names resolve cleanly
**And** the three regex constants are pre-compiled at module import time (NOT inside the parse functions — Pattern §5 forbids per-call recompile; constants are `re.Pattern[str]` typed; the underlying string literals are `Final[str]` constants beside them so docs / introspection can read the source pattern):

| Constant | Pattern (Python verbose-mode, see Dev Notes for raw form) | Match invariants |
|---|---|---|
| `EPIC_ID_REGEX` | `^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$` | Whole string; `epic_slug` group is the kebab-slug minus the `EPIC-` prefix |
| `STORY_ID_REGEX` | `^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)-S(?P<story_num>\d{2})-(?P<story_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$` | `story_num` is exactly 2 digits, zero-padded; matches `S00`–`S99` |
| `TASK_ID_REGEX` | `^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)-S(?P<story_num>\d{2})-(?P<story_slug>[a-z0-9]+(?:-[a-z0-9]+)*)-T(?P<task_num>\d{2})-(?P<task_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$` | Both `story_num` and `task_num` are zero-padded 2-digit; matches `T00`–`T99` |

**And** the three return types are `@dataclass(frozen=True, slots=True)` (Architecture coding-style: immutability — Story 1.4 review patches confirmed `frozen=True, slots=True` on `ModuleSpec`; same convention here):
```python
@dataclass(frozen=True, slots=True)
class EpicId:
    raw: str        # full canonical string e.g. "EPIC-stripe-webhook"
    epic_slug: str  # the slug without the "EPIC-" prefix, e.g. "stripe-webhook"

@dataclass(frozen=True, slots=True)
class StoryId:
    raw: str
    epic_slug: str
    story_num: int   # zero-padded in `raw` but stored as int (1–99 typical; type allows 0–99)
    story_slug: str

@dataclass(frozen=True, slots=True)
class TaskId:
    raw: str
    epic_slug: str
    story_num: int
    story_slug: str
    task_num: int
    task_slug: str
```

**And** the three `parse_*` functions return the matching dataclass on success; raise `IdsError(message, details={"input": <raw>, "rule": <named violated rule>})` on any of the failure modes below (each failure mode produces a deterministic, machine-readable `rule` value):

| Failure | `rule` value | Example input | Expected message fragment |
|---|---|---|---|
| Empty / not a string | `"empty_or_non_string"` | `""`, `None` (rejected by type-check at runtime) | `"identifier must be a non-empty string"` |
| Wrong prefix (epic) | `"missing_epic_prefix"` | `"stripe-webhook"`, `"epic-stripe-webhook"` (lower) | `"epic identifier must start with 'EPIC-'"` |
| Slug fails kebab pattern | `"invalid_slug"` | `"EPIC-Stripe_Webhook"` (uppercase), `"EPIC-stripe--webhook"` (double dash), `"EPIC-stripe-"` (trailing dash) | `"slug must be lowercase kebab-case"` |
| Wrong story shape | `"invalid_story_shape"` | `"EPIC-foo-S4-bar"` (story_num not zero-padded), `"EPIC-foo-bar"` (no `S<NN>`) | `"story identifier must contain '-S<NN>-' with a 2-digit story number"` |
| Wrong task shape | `"invalid_task_shape"` | `"EPIC-foo-S04-bar-T1-baz"`, `"EPIC-foo-S04-bar"` (passed to `parse_task_id`) | `"task identifier must contain '-T<NN>-' with a 2-digit task number"` |
| Wrong function for shape | `"wrong_id_shape"` | `parse_epic_id("EPIC-foo-S04-bar")` | `"input parses as a story identifier, not an epic identifier"` |

**And** the three `build_*` functions are pure constructors that re-emit the canonical `raw` string from the dataclass components, never re-parse: `build_epic_id(epic_slug)` / `build_story_id(epic_slug, story_num, story_slug)` / `build_task_id(epic_slug, story_num, story_slug, task_num, task_slug)` — `build_*` validates the components against the same kebab/digit invariants and raises `IdsError(rule="invalid_component", details=...)` on bad input (zero-padding is enforced by the builder via `f"{n:02d}"`; passing `n < 0` or `n > 99` raises with `rule="invalid_component"`; passing non-`int` raises `TypeError`)

**And** every successful round-trip is exact: `parse_X(build_X(...components...))` reconstructs the same dataclass, and `build_X(*parse_X(s).<components>...).raw == s` (property-test fixture lives in `tests/property/test_ids_roundtrip.py` per AC4)

**AC3 — `errors/` and `ids/` are leaf-discipline-clean: the boundary-validator hook from Story 1.4 stays green, no module under `src/sdlc/{errors,ids}/` imports anything else from `sdlc.*` except (for `ids/`) the `errors` package.**

**Given** the boundary-validator hook from Story 1.4 (`scripts/check_module_boundaries.py`) is active in pre-commit
**When** I add `from sdlc.contracts import JournalEntry` to any file under `src/sdlc/errors/` (illustrative violation)
**Then** the hook fails with the exact message format from `check_module_boundaries.py:298-302`:
```
src/sdlc/errors/<file>.py:<line>:<line>: import violation: errors/ -> contracts/ (errors/ is a leaf module; see Architecture §1054 + §1103-#8)
```
**And** the commit is rejected (exit 1)

**Given** the boundary-validator hook is active
**When** I add `from sdlc.contracts import JournalEntry` to any file under `src/sdlc/ids/` (illustrative violation; `contracts/` is NOT in `ids.depends_on={"errors"}` per `MODULE_DEPS`)
**Then** the hook fails with `check_module_boundaries.py:312-318`'s "does not declare … as a dependency" branch:
```
src/sdlc/ids/<file>.py:<line>:<line>: import violation: ids/ -> contracts/ (ids/ does not declare contracts/ as a dependency; see Architecture §1052 dependency-table row)
```
**And** the commit is rejected (exit 1)

**Given** the canonical implementation from AC1 + AC2
**When** I run `uv run pre-commit run --all-files` after authoring `src/sdlc/errors/{__init__.py,base.py}` and `src/sdlc/ids/{__init__.py,parsers.py,builders.py}`
**Then** every hook in the Story 1.4 chain (ruff-check → ruff-format → mypy-strict → boundary-validator → specialist-validator → hygiene hooks) exits 0
**And** the boundary-validator specifically OK's `src/sdlc/ids/parsers.py: from sdlc.errors import IdsError` (this is the only legal cross-module import in either of these two modules)

**AC4 — Test coverage: ≥ 95% line+branch on `src/sdlc/errors/` and `src/sdlc/ids/` (per epic AC + Architecture §1248 NFR-MAINT-2 raised gate); the project-wide ≥ 90% gate from `pyproject.toml:127` stays green.**

**Given** `[tool.coverage.report] fail_under = 90` is the project-wide gate (`pyproject.toml:146`); Architecture §1248 calls out "engine modules ≥95%" but the leaf-foundation modules carry the same discipline
**When** I run `uv run pytest --cov=src/sdlc/errors --cov=src/sdlc/ids --cov-branch --cov-report=term-missing --cov-fail-under=95 tests/unit/errors tests/unit/ids tests/property/test_ids_roundtrip.py`
**Then** the targeted coverage exits 0 (≥95% line+branch on both modules, separately measured)
**And** the unit-test set covers, at minimum:
  - **errors** (`tests/unit/errors/test_base.py`):
    - Each subclass instantiates with both forms: `StateError("msg")` and `StateError("msg", details={"path": "/tmp/state.json"})`.
    - `details` defaults are NOT shared across instances (regression guard against the classic mutable-default-arg trap; create two errors without `details=`, mutate one's `.details`, assert the other's `.details` is unchanged).
    - `to_envelope()` for every subclass emits exactly the four-key shape (`code`, `message`, `details`, `exit_code`) under the top-level `"error"` key, JSON-serializable via `json.dumps`.
    - `EXIT_CODE_MAP` has exactly 9 entries (one per concrete subclass; `SdlcError` itself is not mapped — its `exit_code` defaults via the `.get(..., 2)` fallback).
    - `isinstance(StateError("x"), SdlcError) is True` for every concrete subclass.
    - `str(StateError("boom"))` returns `"boom"` (delegation to `Exception.__str__`).
    - `repr(StateError("boom"))` includes the class name (regression guard against silent `__repr__` override).
  - **ids** (`tests/unit/ids/test_parsers.py`, `tests/unit/ids/test_builders.py`):
    - Happy path: 3 canonical inputs (one each from Architecture §429–§431) parse into the matching dataclass.
    - Each of the 6 failure-mode rows in AC2's table raises `IdsError` with the listed `rule` value.
    - Slug edge cases: single-character slug `"a"` ✓; trailing dash `"a-"` ✗; double dash `"a--b"` ✗; uppercase `"A"` ✗; underscore `"a_b"` ✗; starting digit `"1abc"` ✓ (per the regex); empty between dashes is impossible (regex prevents).
    - Story/task num edge cases: `"S00"`–`"S99"` ✓; `"S100"` ✗ (3 digits); `"S0"` ✗ (1 digit); `"s04"` ✗ (lowercase prefix).
    - `build_*` round-trips: every successful parse round-trips back to the original `raw` (covered also by AC4's property test).
    - `build_*` validation: invalid component (negative `story_num`, non-kebab `epic_slug`, etc.) raises `IdsError(rule="invalid_component")`; non-int num raises `TypeError`.
  - **ids property test** (`tests/property/test_ids_roundtrip.py`):
    - `hypothesis`-driven generators for canonical kebab slugs, num in [0, 99], full epic/story/task triples; assert `parse_X(build_X(...)).raw == build_X(...).raw`; tag with `@pytest.mark.property` per `pyproject.toml:133` marker registry.
**And** the project-wide post-Story-1.6 gate (`uv run pytest`) still exits 0 with coverage ≥ 90% across all sources (`source = ["src/sdlc", "scripts"]` from `pyproject.toml:139`)
**And** if `hypothesis` is added as a dev dep for the property test, it lands in `[dependency-groups] dev` of `pyproject.toml` immediately after the existing `mkdocs>=1.6.0,<2` entry (chronological-by-story convention from Story 1.5), with constraint `hypothesis>=6.100,<7` (forward-defensive `<7` cap matching Story 1.2's mypy/pytest cap pattern)

**AC5 — `mypy --strict` passes; ruff stays clean; both modules satisfy the universal `from __future__ import annotations` + line-length + complexity ≤ 8 + LOC ≤ 400 disciplines.**

**Given** Story 1.2's `[tool.mypy] strict = true` (`pyproject.toml:97`) + Story 1.4's boundary-validator + Story 1.4's per-file-ignores
**When** I run `uv run mypy --strict src/`
**Then** mypy exits 0 — no `[no-untyped-def]`, `[var-annotated]`, `[misc]`, or `[type-arg]` diagnostics under either of the two new modules
**And** every public function in `errors/` and `ids/` has a typed signature (return type included, even on `__init__` returning `None`)
**And** `ClassVar[str]` on each subclass's `code` is the only acceptable annotation form (do NOT use a bare `code = "ERR_X"` class attribute — mypy under `--strict` treats bare class-level constants as `Final[str]`-typed but `ClassVar[str]` documents intent and is the convention Architecture's pattern code uses)
**And** every `.py` file under `src/sdlc/errors/` and `src/sdlc/ids/` opens with `from __future__ import annotations` (Story 1.2 ruff rule `required-imports = ["from __future__ import annotations"]` enforces this; Story 1.4's boundary-validator does NOT enforce this — ruff does)
**And** `uv run ruff check src/sdlc/errors src/sdlc/ids` exits 0; `uv run ruff format --check src/sdlc/errors src/sdlc/ids` exits 0
**And** no file exceeds 400 LOC (boundary-validator's `LOC_CAP` from `scripts/check_module_boundaries.py:326` enforces this — the LOC check is module-agnostic and applies to every `.py` in argv)

**AC6 — Public-surface stability + `__all__` declarations: every re-export is intentional and documented; no accidental private leak.**

**Given** Architecture §483–§494 forbids `print()` in low-level modules, `subprocess.run` outside `runtime/`/`cli/git`/`cli/gh`, and `os.environ[...]` outside `config/env.py`; none of these patterns belong in foundation modules
**When** I read `src/sdlc/errors/__init__.py`
**Then** the file declares an explicit `__all__` tuple containing exactly the 10 public names from AC1 + `EXIT_CODE_MAP`:
```python
__all__ = (
    "SdlcError",
    "StateError",
    "JournalError",
    "DispatchError",
    "HookError",
    "SchemaError",
    "SignoffError",
    "AdoptError",
    "ConfigError",
    "IdsError",
    "EXIT_CODE_MAP",
)
```
**And** any helper symbols inside `base.py` (e.g. a private `_default_exit_code` helper if you need one) are prefixed with a leading underscore and NOT in `__all__`
**And** `src/sdlc/ids/__init__.py` declares an explicit `__all__` tuple containing exactly the 12 public names from AC2:
```python
__all__ = (
    "EpicId",
    "StoryId",
    "TaskId",
    "parse_epic_id",
    "parse_story_id",
    "parse_task_id",
    "build_epic_id",
    "build_story_id",
    "build_task_id",
    "EPIC_ID_REGEX",
    "STORY_ID_REGEX",
    "TASK_ID_REGEX",
)
```
**And** there is NO `print()`, NO `subprocess.run`, NO `os.environ`, NO `time.time()` ordering use, NO `open()` for state-or-journal writes anywhere under either module (none of these have any reason to appear in a leaf-foundation module; ruff doesn't enforce this — code review does, and the relevant rules are listed in Architecture §483–§494)
**And** the regex constants are exported as `re.Pattern[str]` AND their source string literals are exported as sibling `Final[str]` constants (the precompiled `Pattern` is the public surface for `match` calls; the string is for debugging / introspection / docs):
```python
_EPIC_ID_PATTERN: Final[str] = r"^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
EPIC_ID_REGEX: Final[re.Pattern[str]] = re.compile(_EPIC_ID_PATTERN)
```

**AC7 — Sprint status + deferred-work ledger updates: Story 1.6 marks itself in-progress at start, review at code-review handoff, done after merge; opens NO new deferred items at planning level (any surfacing during dev is recorded in `deferred-work.md` per the Story 1.5 convention).**

**Given** `_bmad-output/implementation-artifacts/sprint-status.yaml` lists `1-6-foundation-errors-and-ids-modules: backlog` (line 56) under `epic-1: in-progress`
**When** the dev-story workflow runs
**Then** the dev-story workflow flips the status `backlog → ready-for-dev → in-progress` (this story's create-story workflow already does the first transition; dev-story owns the second)
**And** at code-review handoff: `in-progress → review`
**And** at merge: `review → done`
**And** `last_updated` is bumped on every transition (the existing `# generated:` comment on line 1 stays untouched; the human-readable `last_updated:` field on line 39 is the live one)
**And** no new entries are added to `deferred-work.md` at PLANNING level — every choice in this story (8-vs-9 subclass count, `IdsError` 9th-subclass addition, no new ADR for this story, slug regex strictness) traces back to either (a) Architecture §526–§538 + §424–§441 verbatim, or (b) the Dev Notes "Epic-vs-Architecture variance" decision below. Any item surfaced during dev or code-review is added to `deferred-work.md` with the `## Deferred from: code review of 1-6-…` header pattern Story 1.5 established (`deferred-work.md:5,19,26,34,43`)

## Tasks / Subtasks

- [x] **Task 1 — Author `src/sdlc/errors/base.py` + `src/sdlc/errors/__init__.py` per AC1 + AC5 + AC6.** (AC: #1, #5, #6)
  - [x] 1.1 Create `src/sdlc/errors/__init__.py` with `from __future__ import annotations`, the AC6 `__all__` tuple, and re-exports from `sdlc.errors.base`.
  - [x] 1.2 Create `src/sdlc/errors/base.py` declaring `SdlcError(Exception)` with the AC1 `__init__` shape (`message: str, *, details: dict[str, object] | None = None`), `code: ClassVar[str] = "ERR_SDLC"`, the `to_envelope()` method, the `EXIT_CODE_MAP: ClassVar[dict[str, int]]` constant, and the `exit_code` property that resolves via `EXIT_CODE_MAP.get(self.code, 2)`.
  - [x] 1.3 Declare the 9 concrete subclasses (`StateError`, `JournalError`, `DispatchError`, `HookError`, `SchemaError`, `SignoffError`, `AdoptError`, `ConfigError`, `IdsError`) — each as a one-line `class X(SdlcError): code: ClassVar[str] = "ERR_X"`. No additional methods; the inherited `__init__` + `to_envelope` cover everything.
  - [x] 1.4 Verify LOC count: `wc -l src/sdlc/errors/base.py` should print ≤ 200; `wc -l src/sdlc/errors/__init__.py` should print ≤ 30. Both well under the 400 cap.
  - [x] 1.5 Run `uv run ruff check src/sdlc/errors`, `uv run ruff format --check src/sdlc/errors`, `uv run mypy --strict src/sdlc/errors` — all exit 0 before moving to Task 2.

- [x] **Task 2 — Author `src/sdlc/ids/parsers.py`, `src/sdlc/ids/builders.py`, `src/sdlc/ids/__init__.py` per AC2 + AC5 + AC6.** (AC: #2, #5, #6)
  - [x] 2.1 Create `src/sdlc/ids/__init__.py` with `from __future__ import annotations`, the AC6 `__all__` tuple, and re-exports.
  - [x] 2.2 Create `src/sdlc/ids/parsers.py` with the three `re.compile`'d regex constants (sibling `_*_PATTERN: Final[str]` literals + `Final[re.Pattern[str]]` compiled objects per AC6), the three frozen-slot dataclasses (`EpicId`, `StoryId`, `TaskId`), and the three `parse_*` functions. Every failure path raises `IdsError(message, details={"input": <raw>, "rule": <named-rule>})` with the rule values from AC2's failure table.
  - [x] 2.3 Create `src/sdlc/ids/builders.py` with the three `build_*` functions. Each builder validates components against the regex / digit invariants and raises `IdsError(rule="invalid_component", details=...)` on violation. Use `f"{n:02d}"` for zero-padded num formatting (NOT `str(n).zfill(2)` — both work; `f"{n:02d}"` is the convention Architecture coding-style §483 implicitly favours via type-strict formatting).
  - [x] 2.4 Verify LOC + ruff + mypy on `src/sdlc/ids/` per Task 1.4 + 1.5 pattern.

- [x] **Task 3 — Verify the boundary-validator hook stays green AND emits the right message on illustrative violations.** (AC: #3)
  - [x] 3.1 Run `uv run pre-commit run --all-files` — every hook exits 0 (no NEW work needed; the hook from Story 1.4 already grants `errors → ∅` and `ids → {errors}`).
  - [x] 3.2 Spot-test (NOT committed) the violation messages: temporarily add `from sdlc.contracts import JournalEntry` to `src/sdlc/errors/base.py`, run `uv run python scripts/check_module_boundaries.py src/sdlc/errors/base.py`, confirm exit 1 with the AC3 leaf-violation message format, then revert. Repeat for `src/sdlc/ids/parsers.py` (expect "does not declare … as a dependency" branch). DO NOT commit either spot-test edit.

- [x] **Task 4 — Author unit tests under `tests/unit/errors/` and `tests/unit/ids/` per AC4.** (AC: #4)
  - [x] 4.1 Create `tests/unit/errors/__init__.py` (empty) and `tests/unit/ids/__init__.py` (empty) — pytest's collection works without these but the AC2 `__all__` discipline + Architecture §686 "tests/ mirrors src/sdlc/ structure" expects per-module test packages.
  - [x] 4.2 Create `tests/unit/errors/test_base.py` covering every bullet in AC4's "errors" sub-list. Use `pytest.mark.unit` per `pyproject.toml:131`. Assert mutable-default-arg isolation explicitly (most-likely silent bug if the AC1 implementation accidentally writes `details: dict = {}` instead of `details: dict | None = None` plus the defensive copy).
  - [x] 4.3 Create `tests/unit/ids/test_parsers.py` covering every parser bullet in AC4's "ids" sub-list. Use `pytest.parametrize` for the 6-row failure-mode table to keep one test per failure mode named (Architecture §700 — `test_<behavior>_<expected_outcome>`).
  - [x] 4.4 Create `tests/unit/ids/test_builders.py` covering builder happy-path + the `invalid_component` failure paths (AC2 last paragraph).
  - [x] 4.5 Run `uv run pytest tests/unit/errors tests/unit/ids -v` — all pass; capture the count for the Dev Agent Record.

- [x] **Task 5 — Author the property-test for the round-trip invariant per AC4.** (AC: #4)
  - [x] 5.1 Add `"hypothesis>=6.100,<7"` to `[dependency-groups] dev` in `pyproject.toml`, immediately after `"mkdocs>=1.6.0,<2"` (Story 1.5's last addition). Run `uv sync --group dev` (NOT `--frozen` this once) to regenerate `uv.lock` with hypothesis + its transitive deps.
  - [x] 5.2 Create `tests/property/__init__.py` (empty) if it does not exist (Story 1.5 may have created `tests/property/` already; check before writing).
  - [x] 5.3 Create `tests/property/test_ids_roundtrip.py` with hypothesis strategies for canonical kebab slugs (lowercase letters/digits, single-dash separators, no leading/trailing dashes), num in `[0, 99]`, and the three round-trip properties. Mark each test `@pytest.mark.property` per `pyproject.toml:133` marker registry.
  - [x] 5.4 Capture the resolved hypothesis version from `uv.lock` (`awk '/^name = "hypothesis"$/{getline; print}' uv.lock`); record it in the Dev Agent Record's "Latest tech information" section per the Story 1.5 convention.
  - [x] 5.5 Run `uv run pytest tests/property/test_ids_roundtrip.py -v` — all property tests pass.

- [x] **Task 6 — Verify coverage gates per AC4.** (AC: #4)
  - [x] 6.1 Run the targeted ≥ 95 gate: `uv run pytest --cov=src/sdlc/errors --cov=src/sdlc/ids --cov-branch --cov-report=term-missing --cov-fail-under=95 tests/unit/errors tests/unit/ids tests/property/test_ids_roundtrip.py`. Exit 0.
  - [x] 6.2 Run the project-wide ≥ 90 gate: `uv run pytest`. Exit 0; coverage stays ≥ 90% across `["src/sdlc", "scripts"]`.
  - [x] 6.3 If coverage < 95 on either module: do NOT add `# pragma: no cover` to bypass — find the missing branch (likely a defensive `else`/`raise` that one of the negative-path tests should hit). Adding `pragma: no cover` is a Story-1.4-deferred discipline ("acceptable only for `if TYPE_CHECKING:` and `@abstractmethod` per `pyproject.toml:150-152`"); nothing in `errors/` or `ids/` qualifies.

- [x] **Task 7 — Whole-suite regression sweep per AC5 + AC7.** (AC: #5, #7)
  - [x] 7.1 Run the full Story 1.4 + 1.5 quality chain locally:
    ```
    uv run ruff check src/ tests/ scripts/
    uv run ruff format --check src/ tests/ scripts/
    uv run mypy --strict src/
    uv run pre-commit run --all-files
    uv run pytest
    uv run mkdocs build --strict --site-dir _site
    ```
    Every command exits 0. Capture the test count delta for the Dev Agent Record (Story 1.5 baseline: 44 tests; Story 1.6 should add roughly 30+ unit tests + 3+ property tests).
  - [x] 7.2 Confirm `_site/` rebuild is byte-stable (no new docs were added — but mkdocs may regenerate; AC6's "no doc changes" claim is verified by `git diff _site/` after the rebuild — there should be no diff because `_site/` is gitignored by Story 1.5).
  - [x] 7.3 Confirm the boundary-validator hook prints zero violations across the whole tree: `uv run python scripts/check_module_boundaries.py $(git ls-files 'src/sdlc/**.py' 'tests/**.py' 'scripts/**.py')` — exit 0.

- [x] **Task 8 — Update `_bmad-output/implementation-artifacts/sprint-status.yaml` AT EACH transition, NOT in a single end-of-story write.** (AC: #7)
  - [x] 8.1 At the start of dev (after `bmad-create-story` completes): `1-6-foundation-errors-and-ids-modules: ready-for-dev` (this transition is owned by the create-story workflow itself; dev-story does NOT redo it).
  - [x] 8.2 When dev-story begins implementation: `1-6-foundation-errors-and-ids-modules: in-progress`. Bump `last_updated:` to today's ISO date. Update `last_action:` to `"dev-story 1-6-foundation-errors-and-ids-modules (status: ready-for-dev → in-progress)"`.
  - [x] 8.3 At code-review handoff: `1-6-foundation-errors-and-ids-modules: review`. Same `last_updated` + `last_action` discipline.
  - [x] 8.4 At merge: `1-6-foundation-errors-and-ids-modules: done`. Same discipline. Epic 1's `epic-1: in-progress` stays untouched (15 stories still backlog after Story 1.6 lands).
  - [x] 8.5 Preserve ALL comments + STATUS DEFINITIONS block in the YAML (Story 1.5 convention; the create-story workflow's `# Save file, preserving ALL comments and structure` instruction extends to dev-story).

- [x] **Task 9 — Resolve the epic-vs-architecture subclass-naming variance in the implementation choice (NOT in a new ADR — this is a documentation-only-via-this-story-file decision).** (AC: #1)
  - [x] 9.1 Implementation MUST follow the architecture-canonical 8 subclass names from Architecture §526–§538 (`StateError`, `JournalError`, `DispatchError`, `HookError`, `SchemaError`, `SignoffError`, `AdoptError`, `ConfigError`) — NOT the epic's older draft list (`MigrationError`, `WorkflowError` are **not** in the architecture; they conflate concepts that `SchemaError` + `ConfigError` already cover).
  - [x] 9.2 Add the 9th `IdsError` subclass to satisfy the epic's "invalid IDs raise `IdsError`" AC. The 9-vs-8 count gap is intentional: Architecture §526 says "+ 8 subclasses" describing the as-of-architecture-write taxonomy; Story 1.6 extends it by exactly one (`IdsError`) because identifier parsing is a distinct concern from pydantic schema or migration. Architecture §1054 + §1100's claim "errors/ exports SdlcError + 8 subclasses" remains numerically inaccurate until a future ADR back-fills (see Dev Notes "Future ADR backlog item — NOT this story"). The incremental count delta is documented IN this story file and IN the eventual code-review patch's commit message; no ADR is opened.
  - [x] 9.3 Do NOT add an ADR for this story. Rationale: this story implements two leaf modules whose every load-bearing decision (8+1 subclasses, exit-code mapping, regex patterns, dataclass shape, leaf-discipline) is **directly cited** from Architecture §424–§441 + §526–§560 + §1052–§1112. ADRs are for "load-bearing decisions" (NFR-MAINT-5); this story is "implement what architecture already decided". The single new decision (`IdsError` 9th subclass) is small enough to live in Dev Notes; if it grows (e.g. future stories add a 10th subclass, or `EXIT_CODE_MAP` shape changes), THAT future story authors `ADR-014-errors-module-finalization.md`.

## Dev Notes

### File set this story creates / modifies

**NEW files (created by Story 1.6):**

```
src/sdlc/errors/__init__.py                                                # Task 1.1
src/sdlc/errors/base.py                                                    # Task 1.2 + 1.3
src/sdlc/ids/__init__.py                                                   # Task 2.1
src/sdlc/ids/parsers.py                                                    # Task 2.2
src/sdlc/ids/builders.py                                                   # Task 2.3
tests/unit/errors/__init__.py                                              # Task 4.1 (empty marker)
tests/unit/errors/test_base.py                                             # Task 4.2
tests/unit/ids/__init__.py                                                 # Task 4.1 (empty marker)
tests/unit/ids/test_parsers.py                                             # Task 4.3
tests/unit/ids/test_builders.py                                            # Task 4.4
tests/property/__init__.py                                                 # Task 5.2 (only if not present)
tests/property/test_ids_roundtrip.py                                       # Task 5.3
```

**MODIFIED files:**

```
pyproject.toml                                                             # Task 5.1 (+hypothesis>=6.100,<7 in [dependency-groups] dev)
uv.lock                                                                    # Task 5.1 (regenerated)
_bmad-output/implementation-artifacts/sprint-status.yaml                   # Task 8 (4 transitions)
```

**Do NOT** create:
- `src/sdlc/contracts/`, `src/sdlc/config/`, `src/sdlc/concurrency/`, or any module that's not `errors/` or `ids/`. Those are owned by Stories 1.7 / 1.8 / 1.9 respectively (per Architecture §1404 implementation-order: `errors/ → ids/ → contracts/ → config/ → concurrency/`).
- A new `ADR-014-errors-module-finalization.md` (or any new ADR). Task 9.3 explains why; the future-story trigger is documented in "Future ADR backlog item" below.
- `IdsError` outside `src/sdlc/errors/base.py` (e.g. NOT in `src/sdlc/ids/parsers.py`). The leaf discipline (AC3) requires `errors/` to OWN every error class; `ids/` only IMPORTS from `errors/`.
- `MigrationError` or `WorkflowError` (the epic's older draft names). Task 9.1's variance resolution makes architecture-canonical names the implementation. If a future Story 1.19 (migration framework) or Story 2A.1 (workflow loader) needs a more specific error class, that future story chooses between (a) reusing `SchemaError` per architecture intent or (b) adding a new subclass with its own ADR.
- A `secrets`-aware error envelope. Architecture §566 describes a `secrets.py` regex sanitizer for log lines; the `to_envelope()` method here just serializes `self.details` verbatim. The sanitization is a `config/secrets.py` concern (Story 1.8). DO NOT pre-emptively redact in `to_envelope` — the redaction layer belongs at the OUTPUT boundary, not the construction site (else every test that asserts on `details` content has to know the redaction rules; YAGNI for v0.2).

### Epic-vs-Architecture variance: 9th subclass `IdsError`

The epic file (`_bmad-output/planning-artifacts/epics.md:562`) says:

> the module exports `SdlcError` plus 8 named subclasses (`StateError`, `JournalError`, `SignoffError`, `DispatchError`, `HookError`, **`MigrationError`**, `AdoptError`, **`WorkflowError`**)

Architecture (`architecture.md:528-538`) says:

> `SdlcError` (root) | `StateError` | `JournalError` | `DispatchError` | `HookError` | **`SchemaError`** (pydantic validation / migration) | `SignoffError` | `AdoptError` | **`ConfigError`** (missing env / malformed `project.yaml`)

Then `epics.md:569` independently adds: "invalid IDs raise `IdsError` with a clear message naming the violated rule" — without listing `IdsError` in the 8-subclass enumeration.

**Resolution (this story):** follow architecture for the 8 names (`StateError`, `JournalError`, `DispatchError`, `HookError`, `SchemaError`, `SignoffError`, `AdoptError`, `ConfigError`). Architecture's enumeration is more recent + tighter (`SchemaError` collapses pydantic + migration into one class per the parenthetical "(pydantic validation / migration)"; `ConfigError` covers env + project.yaml per its parenthetical). The epic's `MigrationError` + `WorkflowError` are an older draft that pre-dates the architecture's "Step 5 — Patterns" pass.

**Add `IdsError` as the 9th** subclass — explicitly going beyond the architecture's "8 subclasses" count — because:
1. The epic AC #5 (`epics.md:569`) directly requires `IdsError`.
2. Identifier parsing is a distinct concern from pydantic schema validation — collapsing it into `SchemaError` would make `--json` envelope's `code: ERR_SCHEMA` ambiguous between "your wire-format payload had bad shape" and "your CLI argument `STORY-id` was malformed" (different exit codes — pydantic schema is exit 2 / framework failure, ID parsing is exit 1 / user error per AC1's `EXIT_CODE_MAP`).
3. The architecture's "8 subclasses" wording is descriptive (a count of the as-of-architecture-write taxonomy), not prescriptive (a hard cap). Adding the 9th `IdsError` is a minor extension; adding a 10th would re-trigger the ADR conversation.

The architecture text + ADR-012's module-spec table will need a one-line update at the next architecture-revision pass to reflect "+ 9 subclasses". This is captured in "Future ADR backlog item" below; **do NOT** open the ADR within this story (per Task 9.3).

### Future ADR backlog item — NOT this story

A future story (likely whichever first lands a 10th subclass, or whichever first revises the `EXIT_CODE_MAP` semantics) will author `ADR-014-errors-module-finalization.md`. Its scope:

- Record the 9-subclass implementation (`SdlcError` + 8 architecture-canonical + `IdsError`).
- Update Architecture §526 + §1054 + §1100's verbatim "8 subclasses" wording to "9 subclasses (or more, if the rationale below applies)".
- Document the `code: ClassVar[str]` + `EXIT_CODE_MAP` policy as the wire-format-stable surface — and call out that adding a new subclass is a wire-format event (Decision F3) requiring per-contract migration discipline (touch `migrations/` + bump `schema_version`?  or claim that error codes are NOT pydantic-versioned and only the named-class set is the contract — TBD by the ADR author).
- Document the `to_envelope()` shape as the canonical `--json` mode error contract.

**Owner:** the future story that crosses this trigger. Recorded HERE so a story-slicer or sprint-planner knows the trigger.

### Why `IdsError` lives in `src/sdlc/errors/`, NOT `src/sdlc/ids/`

The leaf discipline (Architecture §1054 + §1100) makes `errors/` the deepest leaf. `ids/` depends on `errors/` (Architecture §1055), but NOT vice versa. If `IdsError` lived in `src/sdlc/ids/parsers.py`, then any third module wanting to catch `IdsError` (e.g. `cli/init.py` rendering "your supplied STORY-id was malformed") would have to import from `sdlc.ids` just to get the error type — coupling the upper stack to a leaf module purely for type access. Centralising every error class under `sdlc.errors` matches the architecture's "errors/ is the SINGLE source of error types" intent (`scripts/check_module_boundaries.py:30-33` — `errors.depends_on=frozenset()` means it can't even import its own consumers' types).

**Implementation:** `IdsError` is declared in `src/sdlc/errors/base.py` alongside the other 8 subclasses. `src/sdlc/ids/parsers.py` imports it: `from sdlc.errors import IdsError` — this is the SOLE legal cross-module import in either of these two new modules.

### Why `code: ClassVar[str]` on each subclass (and not an instance attribute)

The `code` is INTRINSIC TO THE CLASS, not the instance — every `StateError` instance has the same code; the variation is in the `message` and `details`. Putting `code` on the class level (via `ClassVar`) means:

1. `mypy --strict` recognizes it as a class-level constant (not an instance attribute that needs `__init__`-time assignment).
2. Subclassing-by-value-substitution works cleanly: a future `class HashDriftError(SignoffError): code = "ERR_HASH_DRIFT"` overrides the parent's class-level `code` without any `__init__` plumbing.
3. The `--json` envelope's `code` field (`{"error": {"code": "ERR_STATE", ...}}`) reads `self.code` and resolves via Python's normal MRO — no per-instance override needed.

If you needed per-instance code variation (you don't), use `details` for the variant data instead.

### Slug regex strictness rationale (AC2)

The regex `^EPIC-[a-z0-9]+(?:-[a-z0-9]+)*$` is intentionally strict:

- **Lowercase only**: matches Architecture §424's "kebab-case" convention. The naming-validator hook from Story 2A.4 will reject mixed-case at WRITE time; `ids/` rejects at PARSE time. Two layers, same rule.
- **Digits allowed inside slug** (e.g. `EPIC-checkout-v2`): matches the expected real-world identifier patterns (versioned components, numbered iterations) without forcing dashes between letters and digits.
- **Single-character slug allowed** (`EPIC-x`): follows minimal-validity principle — the convention is "kebab-case", not "kebab-case with at least N characters".
- **No double dashes** (e.g. `EPIC-foo--bar`): the inner non-capturing group `(?:-[a-z0-9]+)*` forces single dashes only. Double-dash inputs trigger the `invalid_slug` rule.
- **No trailing dash** (e.g. `EPIC-foo-`): the inner group requires at least one `[a-z0-9]+` after each dash, so trailing dashes don't match.
- **No leading digit at the slug start? — Allowed** (e.g. `EPIC-1abc`): the regex's `[a-z0-9]+` is permissive at the first character; this matches Architecture's convention which doesn't forbid leading digits. If a future hook wants to forbid leading digits (e.g. for legibility), that's a separate naming-validator concern, NOT the parser's concern.

### `details: dict[str, object]` typing rationale

Why `dict[str, object]` and not `dict[str, Any]` or `Mapping[str, object]`?

- **`dict[str, object]`**: mypy `--strict` treats `object` as the most specific common base; consumers that read `details["path"]` get an `object` type and must `isinstance`-narrow before use. This forces type-discipline at consumption sites.
- **`dict[str, Any]`**: mypy `--strict` accepts but `Any` poisons inference downstream; banned in framework code per the `extra_checks = true` setting in `pyproject.toml:105`.
- **`Mapping[str, object]`**: read-only protocol; would block the `dict(details)` defensive copy from the AC1 `__init__` shape unless we switch to `dict(details) if details else {}` — which is what AC1 prescribes anyway. So `dict[str, object]` is the lowest-friction match.

The defensive copy (`dict(details) if details else {}`) is mandatory to prevent the classic "mutable default argument" trap: without the copy, two errors created without `details=` could share a single `dict` instance via aliasing, making mutations on one visible on the other. AC4's regression-guard test for this is named `test_details_default_is_not_shared_across_instances`.

### Pre-commit hook chain interaction

Story 1.4's pre-commit chain (ruff-check → ruff-format → mypy-strict → boundary-validator → specialist-validator → hygiene hooks) plus Story 1.5's `check-yaml` extension:

- **ruff-check / ruff-format**: matches `src/sdlc/errors/**.py`, `src/sdlc/ids/**.py`, and the new `tests/unit/{errors,ids}/**.py` + `tests/property/test_ids_roundtrip.py`. All must pass; the ruff config (`pyproject.toml:50-90`) enforces the future-import line, complexity ≤ 8, line length ≤ 100, etc.
- **mypy-strict**: pinned to `src/` via `entry: uv run mypy --strict src/`. New `src/sdlc/errors/` and `src/sdlc/ids/` are type-checked. Tests under `tests/` are NOT type-checked at this hook (per the `[[tool.mypy.overrides]] module = "tests.*"` block in `pyproject.toml:107-110`); the test files use type hints anyway as good discipline.
- **boundary-validator**: matches `^(src/sdlc/|tests/|scripts/).*\.py$`. New tests under `tests/unit/{errors,ids}/` and `tests/property/` are NOT in `src/sdlc/`, so the boundary-validator just checks LOC cap (no import rules apply outside `src/sdlc/`). New source files under `src/sdlc/errors/` are routed to the `errors` MODULE_DEPS row; new source files under `src/sdlc/ids/` to the `ids` row.
- **specialist-validator**: `pass_filenames: false, always_run: true` — runs unconditionally, returns 0 (placeholder until Story 2A-2). No interaction.
- **trailing-whitespace, end-of-file-fixer, mixed-line-ending, check-yaml, check-toml**: matches the new `.py` files + the modified `pyproject.toml`. Author all new files with trailing newline + LF line endings to keep these green first-shot.
- **check-added-large-files --maxkb=500**: largest new file is `tests/property/test_ids_roundtrip.py` at maybe ~3 KB; well under 500 KB.

### Coverage gate impact + interaction with AC4

`[tool.coverage.run] source = ["src/sdlc", "scripts"]` (Story 1.4 patch). Story 1.6 adds two NEW source modules (`src/sdlc/errors/`, `src/sdlc/ids/`) AND new test files — so:

- The project-wide ≥ 90% gate (`pyproject.toml:127, 146`) covers both new modules. With the AC4 unit + property tests authored, 95%+ on both modules is achievable.
- The **branch** dimension (`pyproject.toml:141`) means every `if/else` AND every `match`/`raise` path counts. The AC2 failure-mode table's 6 rules + the regex's group-success-vs-failure paths are the branches the property test alone won't hit (the property test is a happy-path generator); the per-rule unit tests in Task 4.3 + 4.4 are how branches get covered.
- **DO NOT** add `# pragma: no cover` to bypass. The acceptable-bypass list (`pyproject.toml:150-152`) is `if TYPE_CHECKING:` and `@abstractmethod`; nothing in `errors/` or `ids/` qualifies — they're concrete leaf code with no abstract methods and no TYPE_CHECKING-guarded imports (their `from __future__ import annotations` makes runtime-import-of-only-typing-symbols unnecessary).

### Previous story intelligence (Stories 1.1 + 1.2 + 1.3 + 1.4 + 1.5 learnings)

From the five implementation-artifact files + the deferred-work.md:

1. **Story 1.4 closed all of its own deferred items** AT planning level; Story 1.4's deferred-work entries (6 items in `deferred-work.md:43-50`) are all owned by FUTURE stories beyond Story 1.6. Story 1.6 opens NO new deferred items at planning level (Task 9.3's Dev-Notes-only resolution of the subclass-naming variance is intentional; if dev or code-review surface a real issue, those entries land in `deferred-work.md` per the Story 1.5 convention).
2. **Story 1.5 added `mkdocs>=1.6.0,<2`** to `[dependency-groups] dev` with `<2` cap. Story 1.6's `hypothesis>=6.100,<7` follows the same `<N` defensive-cap convention (mypy `<3`, pytest `<10`, pre-commit `<5`, mkdocs `<2` — now hypothesis `<7`).
3. **Story 1.5's chronological-by-story dep ordering** (NOT alphabetic): `ruff` → `mypy` → `pytest` → `pytest-cov` → `coverage[toml]` → `pre-commit` → `mkdocs` (per `pyproject.toml:18-26`). Story 1.6 appends `hypothesis` at the END of this list, NOT inserted alphabetically. Rationale per Story 1.5 Task 1.1 Dev Notes: "chronological-by-story makes the audit trail of 'when did this dep land' easy to read at the dep table".
4. **Story 1.4's `MODULE_DEPS` in `scripts/check_module_boundaries.py`** already grants `errors/ → ∅` (line 30-33) and `ids/ → {errors}` (line 34-37). Story 1.6 implements the modules; the boundary-validator is already configured. No changes to `MODULE_DEPS` in this story.
5. **Story 1.4's `scripts/check_module_boundaries.py` LOC check** treats every `.py` in argv (`scripts/check_module_boundaries.py:343-358`); LOC cap applies to test files too. No Story-1.6 file should breach 400 LOC.
6. **Story 1.4 + 1.5's `frozen=True, slots=True` dataclass convention** is the standard for read-only DTO-shaped classes (see `scripts/check_module_boundaries.py:20-23` `ModuleSpec`). Story 1.6's `EpicId`/`StoryId`/`TaskId` dataclasses use the same convention.
7. **Story 1.5's ADR-template establishment** + AC8's "no ADR for this story" decision: Story 1.6 leaves ADR count at 12 (the "ADR-013 reserved for Story 1.21" placeholder remains). The mkdocs `nav:` block in `mkdocs.yml` is unchanged by this story.
8. **Story 1.5's `--strict` mkdocs build** (`docs.yml`'s `mkdocs build --strict`) — Story 1.6 adds NO docs surfaces (no new ADR, no new architecture doc, no new index entry). The build stays green by virtue of doing nothing in `docs/`.
9. **Story 1.4's `tests/conftest.py`** (`tests/conftest.py:1-12`) adds `scripts/` to `sys.path` so the `tests/test_check_module_boundaries.py` import works. Story 1.6's new test files DO NOT need any `sys.path` injection — they import `sdlc.errors` / `sdlc.ids` via the standard hatchling-installed package (the `src/sdlc/` layout is editable-installed by `uv sync`).
10. **Story 1.5's revisit-by 12-month-from-authoring rule**: irrelevant to Story 1.6 (no new ADR), but keep the discipline in mind if a future Story 1.6.1 or Story 2A-X needs a back-fill ADR.

### Git intelligence (last 5 commits)

- `67489d3 feat: implement module boundary enforcement with pre-commit hooks (Story 1.4)` — added `scripts/check_module_boundaries.py` with `MODULE_DEPS` already configured for `errors/` and `ids/` (lines 30-37). Story 1.6 ONLY needs to author the source files; the boundary-validator pre-grants the leaf-discipline rules.
- `ca4cb92 feat: add BMad workflow infrastructure and Story 1-3 CI/CD implementation` — added `.github/workflows/{ci,e2e,release,docs}.yml` + ADR-006/007/008/009. The `ci.yml` matrix (Python 3.10/3.11/3.12/3.13 × ubuntu/macos = 8 cells) will run Story 1.6's tests on every PR; the `--frozen` CI sync will invalidate the cache once when `hypothesis` is added (Task 5.1), then cache for subsequent runs.
- `0b4acd9 upload (Story 1.2)` — established `[tool.mypy] strict = true`, `[tool.pytest.ini_options] minversion = "8.0"`, `[tool.coverage.report] fail_under = 90`. Story 1.6 inherits all three.
- `0dd96ea feat: bootstrap sdlc-framework with uv + hatchling (Story 1.1)` — initial `pyproject.toml`, `src/sdlc/__init__.py`, `uv.lock`. The `src/sdlc/__init__.py` re-exports `__version__` only; Story 1.6 does NOT touch this file (no need to re-export `errors` / `ids` at package level — consumers import via `from sdlc.errors import X` / `from sdlc.ids import Y`, not via `sdlc.X`).
- (Story 1.5's commit lands as the next `feat:` between `67489d3` and Story 1.6's commit — it added `mkdocs.yml`, `docs/index.md`, `docs/architecture-overview.md`, `docs/decisions/index.md`, `docs/decisions/adr-template.md`, ADRs 001/005/011/012, plus `_site/` to `.gitignore`. None of these files affects Story 1.6's source code; Story 1.5's `pyproject.toml` extend-exclude widening to include `_site/` is benign for new `.py` files.)

The 5-commit window confirms: the substrate is in place, every quality gate is configured, the boundary-validator pre-knows about `errors/` and `ids/`, and `pyproject.toml` is the single source of truth for dep additions.

### Latest tech information (2026-05 lookup)

- **Python 3.10 floor + `from __future__ import annotations`**: `dataclass(slots=True)` requires Python 3.10+. Both new modules use `slots=True`; minimum-version invariant is honored (the project's `requires-python = ">=3.10"` floor at `pyproject.toml:10`).
- **`re.Pattern[str]`**: requires Python 3.9+ for the generic alias form; under `from __future__ import annotations`, the annotation is stringified anyway, so 3.10 floor is fine.
- **`hypothesis` 6.x**: latest stable is 6.x line; 6.100+ has Python 3.10+ floor + improved `text()` strategy + the `@example()` decorator for fixed cases. Use `from hypothesis import given, strategies as st` + `@pytest.mark.property` (per Story 1.4's marker registry).
- **`pytest.mark.parametrize` for the 6-row failure-mode table (Task 4.3)**: Pytest 8.x stable feature; no version constraints beyond `pyproject.toml:115` (`minversion = "8.0"`).
- **`ClassVar` import from `typing`**: stable since Python 3.5; under `from __future__ import annotations` the import is needed at runtime ONLY if the class is introspected via `typing.get_type_hints()` — for our purpose (just type annotations), `ClassVar` is a typing-only import that mypy resolves without runtime help.
- **`Final` from `typing`**: same situation as `ClassVar`. Both are imported in the typing block at top of file.
- **mypy `--strict` mode**: `extra_checks = true` (Story 1.2's `pyproject.toml:105`) catches `Any`-leak through dict-of-Any, untyped `**kwargs`, etc. Story 1.6's `details: dict[str, object]` is the strict-friendly form.
- **`re.compile` performance**: precompiling at module import is the canonical Python idiom. The cost is paid once at first `import sdlc.ids`; subsequent calls reuse the compiled pattern. NO need for an `@lru_cache` wrapper around the `parse_*` functions — the regex match itself is microseconds; a cache layer adds complexity without measurable wins for this AC's workload.

### Project Structure Notes

- **Alignment with unified project structure** (Architecture §919–§927, §1054–§1055): canonical `src/sdlc/errors/{__init__.py,base.py}` + `src/sdlc/ids/{__init__.py,parsers.py,builders.py}` filenames are honored exactly. The architecture lists `src/sdlc/errors/base.py` (no `parsers.py` for errors — single-file `base.py` is sufficient at this leaf). For `ids/`: the architecture lists `parsers.py` AND `builders.py`; both are authored as separate files per the spec.
- **Detected variance: zero — but with a documented 9-vs-8 subclass-count delta** in the IMPLEMENTATION's count of `SdlcError` subclasses (9, including `IdsError`) vs. Architecture §526's "+ 8 subclasses" wording. Resolution captured in Dev Notes "Epic-vs-Architecture variance" + Task 9.2 above. This is a numerical-count variance, NOT a structural-tree variance.
- **`tests/unit/errors/` and `tests/unit/ids/` and `tests/property/`** are NEW subdirectories under `tests/` introduced by this story. Architecture §686 says "tests/ mirrors src/sdlc/ structure"; before this story the only `tests/unit/` content was the implicit-flat `tests/test_*.py` (no subdirs). Story 1.6 establishes the per-module subdir convention, which Story 1.7+ will follow (one subdir per Architecture-§686 module).
- **`tests/property/` directory creation**: Architecture §687 + §991 lists `tests/property/`. Story 1.6 introduces it (Task 5.2's "create if not present"). The `[tool.pytest.ini_options] markers` table at `pyproject.toml:130-136` already declares the `property:` marker (`pyproject.toml:133`); no marker registry change needed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.6](#) (lines 552–574) — original BDD acceptance criteria for `errors/` + `ids/`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Error-Handling-and-Logging](#) (lines 524–567) — canonical 8-subclass exception hierarchy + CLI exit-code mapping + error-envelope shape + structlog logging policy.
- [Source: _bmad-output/planning-artifacts/architecture.md#Identifier-Naming-Conventions](#) (lines 424–441) — Phase/Epic/Story/Task identifier conventions (zero-padded NN, kebab-slug, `EPIC-`/`S<NN>`/`T<NN>` prefixes).
- [Source: _bmad-output/planning-artifacts/architecture.md#Code-Style-Beyond-Ruff](#) (lines 483–494) — no `print()` in foundation modules, no `time.time()` for ordering, no `os.environ[...]` direct access, no floats in state/journal/signoff.
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Specifications](#) (lines 1052–1071) — `errors/` row (`depends_on: (none)`, `forbidden_from: everything`); `ids/` row (`depends_on: errors/`, `forbidden_from: depends only on errors`).
- [Source: _bmad-output/planning-artifacts/architecture.md#Architectural-Boundaries-Import-Rules](#) (lines 1077–1112) — eight specific boundary rules; rule #8 ("foundation layer; none imports from upper stack") covers `errors/`+`ids/`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Test-Organization-and-Naming](#) (lines 682–701) — `tests/unit/<module-mirror>/test_<module>.py` mirror; `tests/property/test_<invariant>.py` shape; function naming `test_<behavior>_<expected_outcome>`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Cross-Cutting-Concerns-Module-Mapping](#) (lines 1180–1202) — Concern #1 (temporal integrity) is `state/`+`journal/`+`signoff/` — not `errors/`/`ids/`. No cross-cutting concern is OWNED by `errors/` or `ids/`; they are the foundation layer that owns NO concerns directly but is depended-on by every concern's owner.
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation-Handoff](#) (line 1404) — implementation order: `errors/ → ids/ → contracts/ → config/ → concurrency/`. Story 1.6 implements the first two; Story 1.7 implements `contracts/`.
- [Source: _bmad-output/planning-artifacts/prd.md#Maintainability-NFRs](#) (NFR-MAINT-2 ≥95% engine coverage) — applies to `errors/` and `ids/` per the leaf-foundation-discipline convention.
- [Source: scripts/check_module_boundaries.py](scripts/check_module_boundaries.py) (lines 26–37, 297–319) — `FOUNDATION = frozenset({"errors", "ids", ...})`, `MODULE_DEPS["errors"]` + `MODULE_DEPS["ids"]` rows, leaf-discipline violation message format.
- [Source: pyproject.toml](pyproject.toml) (lines 17–26) — `[dependency-groups] dev` chronological-by-story convention; lines 95–110 mypy-strict config; lines 115–157 pytest+coverage gates.
- [Source: docs/decisions/ADR-012-module-layout.md](docs/decisions/ADR-012-module-layout.md) — Story 1.5 back-fill of the 16-module DAG; cites Architecture §1052–§1112 verbatim. `errors/` + `ids/` are the deepest two layers per the §1100 ASCII diagram.
- [Source: docs/decisions/ADR-010-pre-commit-config.md](docs/decisions/ADR-010-pre-commit-config.md) — Story 1.4 boundary-validator hook decision; documents the LOC cap (400) + the leaf-discipline behavior.
- [Source: docs/decisions/ADR-002-ruff-config.md](docs/decisions/ADR-002-ruff-config.md) — `required-imports = ["from __future__ import annotations"]` + complexity ≤ 8 + line length 100.
- [Source: docs/decisions/ADR-003-mypy-strict.md](docs/decisions/ADR-003-mypy-strict.md) — `strict = true` + `extra_checks = true` ban-Any policy.
- [Source: docs/decisions/ADR-004-pytest-config.md](docs/decisions/ADR-004-pytest-config.md) — `--strict-markers` + `--strict-config` + `filterwarnings = ["error"]` + `xfail_strict = true`.
- [Source: _bmad-output/implementation-artifacts/1-1-project-bootstrap-with-uv-init-hatchling.md](#) — Story 1.1 baseline: `requires-python = ">=3.10"` + hatchling layout + `src/sdlc/__init__.py` shape.
- [Source: _bmad-output/implementation-artifacts/1-2-pyproject-toml-quality-gates-configuration.md](#) — Story 1.2: ruff/mypy/pytest config + the chronological-by-story dep convention.
- [Source: _bmad-output/implementation-artifacts/1-3-github-actions-cicd-pipelines.md](#) — Story 1.3: `ci.yml` 8-cell matrix; `--frozen` cache discipline.
- [Source: _bmad-output/implementation-artifacts/1-4-pre-commit-config-module-boundary-enforcement-hook.md](#) — Story 1.4: `MODULE_DEPS` configuration + the boundary-validator hook + the LOC cap; `tests/conftest.py` `sys.path` injection (does NOT apply to Story 1.6 tests).
- [Source: _bmad-output/implementation-artifacts/1-5-mkdocs-adr-log-skeleton.md](#) — Story 1.5: ADR template + `<2` defensive-cap convention + ADR-014 reservation pattern.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md](#) — current deferred-work ledger; Story 1.6 opens NO new entries at planning level.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- ruff: 4 errors fixed (E501 ×2 in test files, PLW0108 lambda → `.map("-".join)`, UP035 `typing.Callable` → `collections.abc.Callable`)
- coverage first run: missed branches in parsers.py (73, 86, 91, 111, 116) and builders.py (23, 49, 54, 59) — resolved by adding 9 additional unit tests for task-shaped input, empty/prefix failures in parse_story_id/parse_task_id, and invalid slug/num/slug in build_task_id
- targeted coverage used `--override-ini="addopts="` to isolate from global `--cov=scripts` addopts when measuring errors/ and ids/ separately

### Completion Notes List

- Implemented `src/sdlc/errors/base.py` (74 LOC): `SdlcError` root with `ClassVar[str] code`, `to_envelope()`, `EXIT_CODE_MAP`, `exit_code` property, defensive-copy `__init__`; 9 concrete subclasses as one-liners
- Implemented `src/sdlc/ids/parsers.py` (133 LOC): 3 pre-compiled `re.Pattern[str]` constants with sibling `Final[str]` literals, 3 frozen-slot dataclasses (`EpicId`/`StoryId`/`TaskId`), 3 `parse_*` functions covering all 6 failure modes
- Implemented `src/sdlc/ids/builders.py` (81 LOC): 3 `build_*` functions with component validation, `_MAX_ID_NUM: Final[int] = 99` constant, `f"{n:02d}"` zero-padding
- Added `hypothesis>=6.100,<7` to `[dependency-groups] dev`; resolved version: hypothesis==6.152.4 + sortedcontainers==2.4.0
- Test count: 44 (Story 1.5 baseline) → 216 (+172 total; 157 unit + 3 property + 12 pre-existing test files)
- Coverage: 97.97% project-wide; errors/ and ids/ both at 100% line+branch
- All quality gates green: ruff check, ruff format, mypy --strict, pre-commit, pytest, mkdocs build --strict
- Task 9 (epic-vs-architecture variance): followed architecture-canonical 8 subclass names + added `IdsError` as 9th; no ADR opened per Task 9.3 rationale

### File List

**New files:**
- `src/sdlc/errors/__init__.py`
- `src/sdlc/errors/base.py`
- `src/sdlc/ids/__init__.py`
- `src/sdlc/ids/parsers.py`
- `src/sdlc/ids/builders.py`
- `tests/unit/__init__.py`
- `tests/unit/errors/__init__.py`
- `tests/unit/errors/test_base.py`
- `tests/unit/ids/__init__.py`
- `tests/unit/ids/test_parsers.py`
- `tests/unit/ids/test_builders.py`
- `tests/property/__init__.py`
- `tests/property/test_ids_roundtrip.py`

**Modified files:**
- `pyproject.toml` (+hypothesis dep)
- `uv.lock` (regenerated with hypothesis==6.152.4)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (in-progress → review)

### Review Findings

_Code review run: 2026-05-08 (3 layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor)_
_Result: 10 patches, 5 deferred, 6 dismissed as noise. (3 decision-needed resolved by user → 2 patches + 1 defer.)_

**Patches:**

- [x] [Review][Patch] `EXIT_CODE_MAP` module-level alias is a live mutable reference to `SdlcError.EXIT_CODE_MAP` [`src/sdlc/errors/__init__.py:18`] — `Final` only prevents rebinding, not mutation; mutating `EXIT_CODE_MAP["ERR_X"]` silently changes the class attribute for all subclasses.
- [x] [Review][Patch] `to_envelope()` returns live `self.details` reference [`src/sdlc/errors/base.py:31-38`] — caller mutating `envelope["error"]["details"]` mutates the exception's `details`. Wrap with `dict(self.details)` inside `to_envelope`.
- [x] [Review][Patch] `float`/`bool` accepted as `story_num`/`task_num` [`src/sdlc/ids/builders.py:27,53,63`] — `0 <= 3.5 <= 99` and `0 <= True <= 99` both pass; floats crash later at f-string format with `ValueError`, bools silently store `True` in the dataclass. Add `isinstance(n, int) and not isinstance(n, bool)` guard.
- [x] [Review][Patch] `pytest.raises((AttributeError, TypeError))` without `match=` [`tests/unit/ids/test_parsers.py:177,184`] — passes for any unrelated AttributeError/TypeError. Anchor with `match=r"cannot assign"`.
- [x] [Review][Patch] `parse_story_id` / `parse_task_id` error message says "epic identifier must start with 'EPIC-'" [`src/sdlc/ids/parsers.py:91-93,116-118`] — copy-paste from `parse_epic_id`; should read "story identifier" / "task identifier".
- [x] [Review][Patch] `test_exit_code_map_has_exactly_9_entries` hardcodes `9` [`tests/unit/errors/test_base.py:100-101`] — replace with `assert len(EXIT_CODE_MAP) == len(_ALL_SUBCLASSES)` so it self-documents.
- [x] [Review][Patch] `errors/__init__.py` `__all__` order is alphabetical, not spec-prescribed [`src/sdlc/errors/__init__.py:20-32`] — AC6 lines 160-172 mandate verbatim semantic order (`SdlcError`, `StateError`, `JournalError`, `DispatchError`, `HookError`, `SchemaError`, `SignoffError`, `AdoptError`, `ConfigError`, `IdsError`, `EXIT_CODE_MAP`).
- [x] [Review][Patch] `ids/__init__.py` `__all__` order is alphabetical, not spec-prescribed [`src/sdlc/ids/__init__.py:16-29`] — AC6 lines 178-190 mandate semantic groupings: dataclasses → parsers → builders → regexes.
- [x] [Review][Patch] (from D1) Asymmetric `wrong_id_shape` detection across parsers [`src/sdlc/ids/parsers.py:84-106,109-133`] — `parse_epic_id` detects task/story-shaped inputs and raises `wrong_id_shape`, but `parse_story_id` and `parse_task_id` emit only generic `invalid_*_shape` for any non-matching input. Add symmetric `wrong_id_shape` detection so machine-readable error contracts are consistent across all three parsers.
- [x] [Review][Patch] (from D3) Replace implicit comparison-`TypeError` with explicit `isinstance` guard in builders [`src/sdlc/ids/builders.py:27,53,63`] — current code relies on Python's mixed-comparison semantics (`0 <= "3" <= 99` → `TypeError`) to satisfy spec line 90 "non-`int` raises `TypeError`". Add explicit `isinstance(n, int) and not isinstance(n, bool)` check that raises `TypeError("story_num must be int, got <type>")` directly. Tests at `test_builders.py:157-165` continue to assert `TypeError`; spec contract preserved verbatim.

**Deferred (real concerns, not addressed in this story):**

- [x] [Review][Defer] Hypothesis `_slug` strategy capped at `max_size=5` and only generates valid slugs [`tests/property/test_ids_roundtrip.py:18,23`] — deferred, pre-existing; property tests cover round-trip, invalid coverage lives in unit tests.
- [x] [Review][Defer] `parse_epic_id` fallthrough emits "slug must be lowercase kebab-case" for any non-matching `EPIC-*` input [`src/sdlc/ids/parsers.py:77-80`] — deferred, message is technically correct for most cases; same string used in builders with different `rule` tag.
- [x] [Review][Defer] Scope leak in `pyproject.toml` diff — `mkdocs>=1.6.0,<2` and `extend-exclude` widening belong to Story 1.5 [`pyproject.toml:25-26,55`] — deferred, process issue (Story 1.5 work was uncommitted when 1.6 began); user to decide on commit splitting.
- [x] [Review][Defer] `SdlcError.code = "ERR_SDLC"` is intentionally NOT in `EXIT_CODE_MAP`, no inline comment explaining the deliberate omission [`src/sdlc/errors/base.py:9-20`] — deferred, behavior is documented in `test_sdlc_error_root_exit_code_defaults_to_2` but not in source.
- [x] [Review][Defer] (from D2) `details` JSON-safety contract not enforced [`src/sdlc/errors/base.py:22-25,31-38`] — deferred per Dev Notes line 307 layering principle: redaction/serialization-safety belongs at the OUTPUT boundary (CLI `--json` writer or `config/secrets.py` in Story 1.8), not at error-construction site. Type-narrowing at construction would block legitimate nested-detail use cases.

**Dismissed (false positives / spec-mandated):**

- `test_repr_includes_class_name` flagged as trivial — AC4 line 130 explicitly mandates this exact regression guard.
- `test_to_envelope_shape` strict-key check flagged as forward-incompatible — intentional per Decision F3 (wire-format additions are breaking changes).
- AC1 `super().__init__()` ordering flagged — runtime behavior identical.
- Regex source-string `_*_PATTERN` not in `__all__` — implementation matches AC6 line 195's verbatim code example.
- Shallow copy of `details` flagged as not protecting nested mutables — spec line 36 explicitly prescribes `dict(details) if details else {}` (shallow).
- `_SLUG_RE` cross-file private import flagged — intentional intra-package pattern, commented at `parsers.py:25`.

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-08 | Implemented `errors/` and `ids/` modules with full test suite (216 tests, 97.97% coverage); all quality gates green; sprint status in-progress → review | claude-sonnet-4-6 |
| 2026-05-08 | Code review complete: 10 patches applied (3 decision-needed → 2 patches + 1 defer); 224 tests pass, 98.10% coverage; status review → done | claude-opus-4-7 |
