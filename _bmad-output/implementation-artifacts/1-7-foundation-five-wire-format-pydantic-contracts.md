# Story 1.7: Foundation — Five Wire-Format Pydantic Contracts at `schema_version=1`

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer locking the framework's wire format at v1 (Decision F3 — per-contract independent versioning, Architecture §382 + §1238) on top of the leaf foundation Stories 1.6 has just landed (`errors/` + `ids/` available; `MODULE_DEPS["contracts"]` already grants `depends_on={"errors", "ids"}` and `forbidden_from={"engine", "dispatcher", "cli"}` per `scripts/check_module_boundaries.py:38-41`),
I want five pydantic v2 `BaseModel` classes (`JournalEntry`, `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec`) — each with its own independent `schema_version: int = 1`, each in its own `src/sdlc/contracts/<snake_case>.py` file per Architecture §881-§886, all `model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)` (strict + immutable + no whitespace munging — wire format must be byte-stable), `JournalEntry` as the prototype shape that the other four follow, and ≥95% line+branch coverage on every contract module via per-contract Cartesian unit tests (valid input × missing required field × extra field × wrong type × `schema_version != 1`),
So that Story 1.8's `config/` (`depends_on={"errors", "contracts"}`) can ground its loader on `schema_version`-bearing types, Story 1.10's `state/atomic.py` can serialize `JournalEntry` instances through the canonicalization helper from Architecture §501-§508, Stories 1.11–1.12's append-only journal + projection rebuilds replay against locked `JournalEntry` v1 (Concern §1184 temporal-integrity owner), Story 1.21's wire-format-immutability lock ceremony (`tests/contracts/test_wireformat_immutability.py` per Story 1.21 AC2, `epics.md:945`) has 5 stable models to freeze, and the wire-format gap (Architecture §169-§179: "these five cross run/process/version boundaries and **must** be schema-versioned") closes for v0.5 replay-divergence prevention.

## Acceptance Criteria

**AC1 — `src/sdlc/contracts/` ships exactly 5 pydantic v2 `BaseModel` classes — one per file per Architecture §881-§886 — each with `schema_version: int = 1`, strict `extra="forbid"` + `frozen=True` config, and `JournalEntry` as the prototype shape.**

**Given** Story 1.6 complete (`sdlc.errors.SchemaError` + `sdlc.errors.IdsError` available; `errors/` is a leaf, no upward import) **AND** `pydantic>=2,<3` added to `[project] dependencies` per Task 1 below **AND** the `MODULE_DEPS["contracts"]` row already declares `depends_on=frozenset({"errors", "ids"})` (Story 1.4 pre-grant; `scripts/check_module_boundaries.py:38-41`)
**When** I import `from sdlc.contracts import JournalEntry, ResumeToken, HookPayload, SpecialistFrontmatter, WorkflowSpec`
**Then** all 5 names resolve cleanly via the package re-export
**And** each is a subclass of `pydantic.BaseModel` (verified via `issubclass(JournalEntry, BaseModel)` etc.)
**And** each declares `schema_version: int = 1` as the FIRST field in its model definition (declaration order matters for pydantic v2's `model_fields` introspection; `JournalEntry` is the prototype Architecture §594 + §1238 — the other four follow its `schema_version`-first ordering)
**And** each lives in its own dedicated file matching Architecture §882-§886:
  - `src/sdlc/contracts/journal_entry.py` → `JournalEntry`
  - `src/sdlc/contracts/resume_token.py` → `ResumeToken`
  - `src/sdlc/contracts/hook_payload.py` → `HookPayload`
  - `src/sdlc/contracts/specialist_frontmatter.py` → `SpecialistFrontmatter`
  - `src/sdlc/contracts/workflow_spec.py` → `WorkflowSpec`
**And** every contract sets `model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)` — `extra="forbid"` causes pydantic to raise `ValidationError` on unknown fields; `frozen=True` prevents post-construction mutation; `str_strip_whitespace=False` keeps whitespace byte-for-byte (canonicalization preserves what was given — see Pattern §3 + §496-§515)
**And** the per-contract field shapes match Architecture §595-§643 verbatim (see "Field Shapes Reference" in Dev Notes for the line-by-line match):

| Contract | Field set (in declaration order) | Architecture source |
|---|---|---|
| `JournalEntry` | `schema_version: int = 1`, `monotonic_seq: int`, `ts: str`, `actor: str`, `kind: str`, `target_id: str`, `before_hash: str \| None`, `after_hash: str`, `payload: dict[str, object]` | §595-§606 |
| `ResumeToken` | `schema_version: int = 1`, `phase: int`, `cursor: dict[str, object]`, `suggested_next_command: str`, `state_hash: str` | §608-§613 |
| `HookPayload` | `schema_version: int = 1`, `hook_name: str`, `target_path: str`, `target_kind: str`, `content_hash_before: str \| None`, `write_intent: str` | §615-§621 |
| `SpecialistFrontmatter` | `schema_version: int = 1`, `name: str`, `title: str`, `icon: str`, `model: str`, `tools: list[str]`, `read_globs: list[str]`, `write_globs: list[str]`, `description: str` | §623-§632 |
| `WorkflowSpec` | `schema_version: int = 1`, `name: str`, `slash_command: str`, `primary_agent: str`, `parallel_agents: list[str] = []`, `synthesizer_agent: str \| None = None`, `postconditions: list[str] = []`, `write_globs: dict[str, list[str]]`, `stop_on_postcondition_failure: bool = True` | §634-§643 |

**And** `payload`/`cursor`/`write_globs` use the strict-friendly `dict[str, object]` (NOT `dict[str, Any]`) — same rationale as Story 1.6 `details: dict[str, object]` (Story 1.6 Dev Notes line 370-374); `mypy --strict + extra_checks = true` (`pyproject.toml:106`) bans `Any`-leak.

**And** ALL list/dict default factories use `Field(default_factory=list)` / `Field(default_factory=dict)` — pydantic v2 forbids bare `[]`/`{}` mutable defaults at class level (raises at model build time). Use:
```python
parallel_agents: list[str] = Field(default_factory=list)
write_globs: dict[str, list[str]]  # required, no default — see WorkflowSpec
postconditions: list[str] = Field(default_factory=list)
```
NOT `parallel_agents: list[str] = []` (pydantic v2 build error).

**AC2 — Each contract has its own independent `schema_version` discipline and rejects `schema_version != 1` with a pydantic v2 `ValidationError` (Decision F3 — per-contract independent migration; Architecture §382).**

**Given** AC1 complete and the 5 contracts importable
**When** I attempt `JournalEntry(schema_version=2, ...all-other-required-fields...)`
**Then** pydantic raises `ValidationError` with at least one error whose `type == "literal_error"` (or equivalent) and `loc == ("schema_version",)`
**And** the SAME behavior holds independently for `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec` — each rejects `schema_version=2` independently (changing one contract's version does NOT change the others)
**And** `schema_version` is typed as `Literal[1]` (pydantic-idiomatic for "this field accepts ONLY the value 1") so the rejection happens at the type-coercion layer, NOT at a custom validator. Use:
```python
from typing import Literal
class JournalEntry(BaseModel):
    schema_version: Literal[1] = 1
    ...
```
**And** each `schema_version` field has its `default = 1` so user code that does `JournalEntry(monotonic_seq=..., ...without schema_version)` succeeds with `instance.schema_version == 1`
**And** the F3 independence is asserted by the unit tests: a test inserts `schema_version=2` into ONE contract's input dict, asserts `ValidationError`, then constructs the OTHER FOUR contracts with their normal defaults and asserts all succeed (no cross-contract version coupling).

**AC3 — Strict mode rejects extra fields per pydantic v2 with `extra="forbid"`; the `ValidationError` names the offending field; missing required fields produce a `ValidationError` listing each missing field.**

**Given** AC1's `model_config = ConfigDict(extra="forbid", ...)` configuration
**When** I construct any of the 5 contracts with an unrecognized field, e.g. `JournalEntry(schema_version=1, monotonic_seq=1, ts="2026-05-08T...", actor="cli", kind="state_mutation", target_id="EPIC-x", before_hash=None, after_hash="sha256:...", payload={}, **bogus_field="x"**)`
**Then** pydantic raises `ValidationError` with at least one error whose `type == "extra_forbidden"` and `loc == ("bogus_field",)`
**And** the `ValidationError.errors()` list of dicts includes the exact field name `"bogus_field"` (regression guard: a future `extra="ignore"` config flip would silently drop it)
**And** the same behavior holds independently for all 5 contracts

**Given** AC1's required-field set per contract
**When** I omit ANY required field (e.g. `JournalEntry(schema_version=1)` missing `monotonic_seq`/`ts`/etc.)
**Then** pydantic raises `ValidationError` listing every missing required field with `type == "missing"` and the field name in `loc`
**And** unit tests cover the FULL Cartesian per contract: `(valid input, missing each required field one-at-a-time, one extra field, one wrong-type field per non-trivial type, schema_version != 1)` — see AC5 for the test layout

**AC4 — `frozen=True` prevents post-construction mutation; downstream consumers can rely on contract instances as hashable, immutable values.**

**Given** AC1's `model_config = ConfigDict(..., frozen=True, ...)` configuration
**When** I construct an instance and attempt `instance.monotonic_seq = 999` (or any other field assignment)
**Then** pydantic raises `ValidationError` (pydantic v2's frozen-model assignment guard) — NOT a silent overwrite
**And** the same behavior holds independently for all 5 contracts (regression guard: a future `frozen=False` flip would silently allow mutation)
**And** `JournalEntry` instances support `hash(instance)` (frozen models are hashable by default in pydantic v2 when all fields are hashable) — `payload: dict` field BREAKS the default hash-eligibility, so `JournalEntry` and `ResumeToken` are NOT hashable. The unit test asserts `TypeError` on `hash()` for these two and asserts hashability for the other three. (See Dev Notes "Hashability matrix" for which contracts get free hashability.)
**And** equality is structural: `JournalEntry(...same args...) == JournalEntry(...same args...)` returns `True` for all 5 contracts (pydantic v2 model `__eq__` is field-wise by default).

**AC5 — JSON canonicalization produces deterministic output: `json.dumps(instance.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))` is byte-stable across Python invocations.**

**Given** AC1 complete and the canonicalization rule from Architecture §501-§508 + Pattern §3 (`canonicalize(obj: dict) -> bytes` — `sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`)
**When** I serialize `instance.model_dump()` (mode="python", which returns JSON-compatible primitives) and feed it through the Architecture-§501-§508 canonicalize function
**Then** the byte output is stable: two separate Python processes producing the same `JournalEntry(...)` produce byte-identical canonicalized output (no reliance on `id()`, no random salt, no hash-randomization-sensitive ordering)
**And** the unit-test fixture asserts this for every contract: construct `instance`, canonicalize, assert against a checked-in golden bytes value (one golden per contract, kept short enough to read inline; the 5 goldens together form the wire-format-immutability prototype that Story 1.21's lock ceremony will pin).
**And** `model_dump(mode="json")` is the form used for canonicalization (returns JSON-primitives — `str`, `int`, `bool`, `dict`, `list`, `None`); `model_dump_json()` is NOT used directly because pydantic v2's `model_dump_json()` wraps `json.dumps` with its own separators that are NOT necessarily Architecture §501-§508-compliant (run-time behavior may drift across pydantic versions; canonical reference uses our own `json.dumps` call with the explicit separators).
**And** Unicode strings in any field round-trip as Unicode (`ensure_ascii=False`); the test fixture includes a string with at least one non-ASCII character (e.g. `actor="agent:café"`) and asserts the canonical bytes contain the UTF-8 encoding of `é`, NOT a `\uXXXX` escape.
**And** field order in the canonical bytes is alphabetical (`sort_keys=True` in canonicalize), NOT pydantic's declaration order — the canonicalization function imposes its own ordering for hash stability per Architecture §501.

**AC6 — `tests/unit/contracts/<contract>.py` covers the full Cartesian per contract; ≥95% line+branch coverage on every contract file; ≥0 mypy-strict diagnostics under `src/sdlc/contracts/`.**

**Given** `[tool.coverage.report] fail_under = 90` is the project-wide gate (`pyproject.toml:147`); Architecture §1248 + Story 1.6 AC4 establish the ≥95% expectation on every NEW leaf-foundation module (`errors/` + `ids/` already at 100% per Story 1.6 Dev Agent Record; `contracts/` follows the same discipline)
**When** I run `uv run pytest --cov=src/sdlc/contracts --cov-branch --cov-report=term-missing --cov-fail-under=95 tests/unit/contracts`
**Then** the targeted coverage exits 0 (≥95% line+branch on the entire `contracts/` package; per-contract files all individually clear 95%)
**And** the test set covers, per contract:
  - **Happy path** — one canonical instance constructed with exactly the required fields plus `schema_version=1`; assert `model_dump()` round-trips back to the same field values via `Contract(**dump)`.
  - **Schema-version rejection** — `schema_version=2` raises `ValidationError`; `schema_version=0` also rejected (only `1` is valid per `Literal[1]`).
  - **Missing required fields** — for each required field (i.e. fields without a default), omit it and assert `ValidationError` names that field with `type == "missing"`. (`payload: dict` is REQUIRED for `JournalEntry`; `cursor: dict` is REQUIRED for `ResumeToken`; etc. — see "Required-field matrix" in Dev Notes.)
  - **Extra-field rejection** — pass one bogus field (`bogus_field="x"`) and assert `ValidationError` with `type == "extra_forbidden"`.
  - **Wrong-type rejection** — for one non-trivial field per contract, pass the wrong type (e.g. `monotonic_seq="not-an-int"` on `JournalEntry`) and assert `ValidationError` with the offending field in `loc`.
  - **Frozen-mutation rejection** — `instance.field = newvalue` raises `ValidationError`.
  - **Equality** — two instances with identical args are `==`.
  - **Hashability matrix** — `hash(instance)` works for `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec` (no `dict` fields with `dict` content — but see WorkflowSpec note below); `hash(instance)` raises `TypeError` for `JournalEntry` (has `payload: dict`) and `ResumeToken` (has `cursor: dict`). **NOTE:** `WorkflowSpec` has `write_globs: dict[str, list[str]]` so `WorkflowSpec` is ALSO unhashable. Final hashable set: `{HookPayload, SpecialistFrontmatter}`. Unhashable set: `{JournalEntry, ResumeToken, WorkflowSpec}`. The test pins this matrix exactly.
  - **JSON-canonicalization stability** — golden-bytes fixture per contract; canonical bytes are checked in.

**Given** Story 1.2's `[tool.mypy] strict = true` + `extra_checks = true` (`pyproject.toml:96-110`)
**When** I run `uv run mypy --strict src/`
**Then** mypy exits 0 — no `[no-untyped-def]`, `[var-annotated]`, `[misc]`, or `[type-arg]` diagnostics under `src/sdlc/contracts/`
**And** every public class has a typed signature; `model_config: ClassVar[ConfigDict]` is the canonical form (NOT bare `model_config = ConfigDict(...)` — `ClassVar` documents intent and prevents mypy from treating it as an instance attribute)
**And** every `.py` file under `src/sdlc/contracts/` opens with `from __future__ import annotations` (Story 1.2 ruff rule `required-imports = ["from __future__ import annotations"]` enforces; ruff `I002` fires otherwise — `pyproject.toml:80-81`)
**And** `uv run ruff check src/sdlc/contracts tests/unit/contracts` exits 0; `uv run ruff format --check src/sdlc/contracts tests/unit/contracts` exits 0
**And** no file in `src/sdlc/contracts/` exceeds 400 LOC (boundary-validator's `LOC_CAP` enforces — `scripts/check_module_boundaries.py:343-358`); the largest contract (`WorkflowSpec` with 9 fields) is comfortably under 80 LOC.

**AC7 — `contracts/` is leaf-discipline-clean: the boundary-validator hook from Story 1.4 stays green; only `sdlc.errors` and `sdlc.ids` are imported from `sdlc.*`; pydantic is the only third-party import.**

**Given** the boundary-validator hook from Story 1.4 (`scripts/check_module_boundaries.py:38-41`) declares `MODULE_DEPS["contracts"]` as `depends_on=frozenset({"errors", "ids"})`, `forbidden_from=frozenset({"engine", "dispatcher", "cli"})`
**When** I run `uv run pre-commit run --all-files` after authoring `src/sdlc/contracts/{__init__.py, journal_entry.py, resume_token.py, hook_payload.py, specialist_frontmatter.py, workflow_spec.py}`
**Then** every hook in the chain (ruff-check → ruff-format → mypy-strict → boundary-validator → specialist-validator → hygiene hooks) exits 0
**And** the boundary-validator OK's the legal cross-module imports listed in Dev Notes "Cross-module import inventory" (mostly: `from sdlc.errors import SchemaError` if a custom validator-side error wrap is used — actually NOT used in v1 per Dev Notes "No errors/ import in contracts/ for v1" decision; the only legal import is from third-party `pydantic`)

**Given** the boundary-validator hook is active
**When** I add an illustrative violation `from sdlc.config import load_project_config` to any file under `src/sdlc/contracts/` (illustrative only — `config/` is forbidden because `contracts/` MUST NOT depend on it; the dependency direction is `config/ → contracts/` per `MODULE_DEPS["config"].depends_on = {"errors", "contracts"}`)
**Then** the hook fails with the AC3-of-Story-1.6 "does not declare … as a dependency" branch from `check_module_boundaries.py:312-318`:
```
src/sdlc/contracts/<file>.py:<line>:<line>: import violation: contracts/ -> config/ (contracts/ does not declare config/ as a dependency; see Architecture §1056 dependency-table row)
```
**And** the commit is rejected (exit 1)
**And** there is NO `print()`, NO `subprocess.run`, NO `os.environ`, NO `time.time()`, NO `open()` for state-or-journal writes anywhere under `src/sdlc/contracts/` (Architecture §483-§494; ruff doesn't enforce — code review does)
**And** the `__init__.py` re-exports the 5 names via an explicit `__all__` tuple in semantic order (the prototype `JournalEntry` first, then the other 4 alphabetically per Architecture §1238's enumeration order):
```python
__all__ = (  # noqa: RUF022
    "JournalEntry",
    "ResumeToken",
    "HookPayload",
    "SpecialistFrontmatter",
    "WorkflowSpec",
)
```
**And** any helper symbols inside any contract file (e.g. a private `_canonicalize` helper if you need one — you DO NOT for v1 per Dev Notes) are prefixed `_` and NOT in `__all__`.

**AC8 — `pydantic>=2,<3` lands in `[project] dependencies` (NOT `[dependency-groups] dev`); `uv.lock` is regenerated; the `<3` defensive cap matches the Story 1.2 / 1.5 / 1.6 convention; the CI matrix's `--frozen` cache invalidates once for this dep, then re-caches.**

**Given** `pyproject.toml:11` currently shows `dependencies = []` (Story 1.1 baseline; the framework has had ZERO runtime deps until now)
**When** I edit `pyproject.toml` to add `pydantic` to runtime `[project] dependencies`:
```toml
[project]
...
dependencies = [
    "pydantic>=2,<3",   # cap: pydantic 2→3 will introduce schema breaks (v3 is on the roadmap)
]
```
**Then** the location is `[project] dependencies`, NOT `[dependency-groups] dev` (pydantic is shipped at runtime — Story 1.7's contracts are imported by `state/`, `journal/`, `signoff/`, `runtime/`, `workflows/`, `specialists/`, `hooks/`, `telemetry/`, `dispatcher/`, `engine/`, `cli/`; every consumer needs pydantic at runtime, not just at test time)
**And** the version constraint `>=2,<3` honours both Architecture's `schema_validation: 'pydantic v2'` (architecture.md:43) AND the chronological-by-story `<N` defensive-cap convention from Story 1.2/1.5/1.6 (mypy `<3`, pytest `<10`, pre-commit `<5`, mkdocs `<2`, hypothesis `<7` — now pydantic `<3`)
**And** I run `uv sync` (NOT `--frozen` this once) to regenerate `uv.lock` with pydantic + its transitive deps (`pydantic-core`, `typing-extensions`, `annotated-types`)
**And** I capture the resolved `pydantic` and `pydantic-core` versions from `uv.lock` (`awk '/^name = "pydantic"$/{getline; print}' uv.lock` and `awk '/^name = "pydantic-core"$/{getline; print}' uv.lock`); record both in the Dev Agent Record's "Latest tech information" section per the Story 1.5 + 1.6 convention
**And** the CI cache discipline matches Story 1.6's hypothesis precedent: the `--frozen` step in `.github/workflows/ci.yml` invalidates ONCE (the first run after the lockfile change), then caches for subsequent PRs.

**Given** the package surface
**When** I run `uv run python -c "import pydantic; print(pydantic.VERSION)"` after the sync
**Then** the version print is `2.x.y` (any 2.x is acceptable; the floor `>=2` is permissive about patch/minor releases within v2)
**And** `uv run python -c "from pydantic import BaseModel, ConfigDict, Field; from typing import Literal; print('ok')"` exits 0 — the imports Story 1.7's contracts depend on resolve.

**AC9 — Sprint status + deferred-work ledger updates: Story 1.7 marks itself `ready-for-dev` (this create-story workflow's responsibility) → `in-progress` (dev-story start) → `review` (code-review handoff) → `done` (merge); opens NO new deferred items at planning level (any surfacing during dev is recorded in `deferred-work.md` per the Story 1.5 + 1.6 convention).**

**Given** `_bmad-output/implementation-artifacts/sprint-status.yaml` lists `1-7-foundation-five-wire-format-pydantic-contracts: backlog` (line 57) under `epic-1: in-progress` (line 50)
**When** the create-story workflow finishes
**Then** the create-story workflow has flipped `1-7-foundation-five-wire-format-pydantic-contracts: backlog → ready-for-dev` (this is Step 6 of the active workflow; dev-story does NOT redo it)
**And** at dev-story start: `ready-for-dev → in-progress`
**And** at code-review handoff: `in-progress → review`
**And** at merge: `review → done`
**And** `last_updated:` is bumped on every transition (the `# generated:` comment on line 1 stays untouched; `last_updated:` at line 39 is the live one)
**And** `last_action:` is updated at every transition with the standard format `"<workflow> 1-7-foundation-five-wire-format-pydantic-contracts (status: <from> → <to>)"`
**And** Epic 1's `epic-1: in-progress` status is UNCHANGED by this story (14 stories — 1.8 through 1.21 — remain backlog after Story 1.7 lands)
**And** ALL existing comments + the `STATUS DEFINITIONS` block (lines 9-36) + `WORKFLOW NOTES` (lines 31-36) are preserved verbatim (the create-story workflow's "preserving ALL comments and structure" instruction extends to dev-story)
**And** NO new entries are added to `deferred-work.md` AT PLANNING level — every choice in this story (Literal[1] for schema_version, frozen=True for immutability, dict[str, object] for payload/cursor, semantic-order `__all__`, no errors/ import for v1, hookpayload-in-contracts-not-hooks/ resolution) traces back to (a) Architecture §169-§179 + §382 + §595-§643 + §881-§886 + §1056 + §1238 verbatim, (b) Story 1.6's established conventions (`details: dict[str, object]`, `frozen=True, slots=True` dataclass / pydantic-equivalent immutability), or (c) Dev Notes "HookPayload location resolution" + "No errors/ import" decisions below. Any item surfaced during dev or code-review is added to `deferred-work.md` with the `## Deferred from: code review of 1-7-…` header pattern Story 1.5 + 1.6 established (`deferred-work.md:5,13,27,34,42,51`).

## Tasks / Subtasks

- [x] **Task 1 — Add `pydantic>=2,<3` to `[project] dependencies` and regenerate `uv.lock`.** (AC: #8)
  - [x] 1.1 Edit `pyproject.toml`: change `dependencies = []` (line 11) to `dependencies = ["pydantic>=2,<3",  # cap: pydantic 2→3 will introduce schema breaks]` — single-element list with inline comment matching the Story 1.2 mypy/pytest cap-comment style.
  - [x] 1.2 Run `uv sync` (NOT `--frozen`) to regenerate `uv.lock` with pydantic + transitive deps (`pydantic-core`, `typing-extensions`, `annotated-types`). Capture the resolved `pydantic` version + `pydantic-core` version for the Dev Agent Record's "Latest tech information" section.
  - [x] 1.3 Verify post-sync: `uv run python -c "from pydantic import BaseModel, ConfigDict, Field; from typing import Literal; print(BaseModel.__module__)"` should print `pydantic.main` (or similar) — confirms the imports resolve.
  - [x] 1.4 Verify CI: the next `uv sync --frozen` call (e.g. inside a fresh checkout or CI) succeeds; the lockfile is the single source of truth post-edit.
  - [x] 1.5 Confirm pydantic is at runtime `[project] dependencies` (NOT `[dependency-groups] dev`); a downstream consumer doing `pip install sdlc-framework` (no `--group dev`) MUST get pydantic.

- [x] **Task 2 — Author `src/sdlc/contracts/journal_entry.py` (the prototype).** (AC: #1, #2, #3, #4, #5, #6, #7)
  - [x] 2.1 Create `src/sdlc/contracts/__init__.py` with `from __future__ import annotations`, the AC7 `__all__` tuple, and re-exports from the 5 sibling files. Suppress `RUF022` for the deliberate non-alphabetic order (prototype `JournalEntry` first, then the other 4 in Architecture §1238 enumeration order — same `# noqa: RUF022` pattern Story 1.6 used in `errors/__init__.py`).
  - [x] 2.2 Create `src/sdlc/contracts/journal_entry.py`:
    ```python
    from __future__ import annotations

    from typing import ClassVar, Literal

    from pydantic import BaseModel, ConfigDict, Field


    class JournalEntry(BaseModel):
        """Wire-format contract: append-only journal record (Architecture §595-§606, Decision B3)."""

        model_config: ClassVar[ConfigDict] = ConfigDict(
            extra="forbid",
            frozen=True,
            str_strip_whitespace=False,
        )

        schema_version: Literal[1] = 1
        monotonic_seq: int
        ts: str
        actor: str
        kind: str
        target_id: str
        before_hash: str | None
        after_hash: str
        payload: dict[str, object] = Field(default_factory=dict)
    ```
    Note: `payload` defaults to empty dict per Architecture §606 ("kind-specific structured payload" — empty is valid for a no-payload kind); `before_hash: str | None` is required-but-nullable per Architecture §604 (None for creates).
  - [x] 2.3 Verify LOC count: `wc -l src/sdlc/contracts/journal_entry.py` should print ≤ 30 (well under 400 cap). `wc -l src/sdlc/contracts/__init__.py` should print ≤ 25.
  - [x] 2.4 Run `uv run ruff check src/sdlc/contracts`, `uv run ruff format --check src/sdlc/contracts`, `uv run mypy --strict src/sdlc/contracts/journal_entry.py` — all exit 0 before moving to Task 3.

- [x] **Task 3 — Author the 4 follow-on contracts mirroring `JournalEntry`'s shape.** (AC: #1, #2, #3, #4, #5, #6, #7)
  - [x] 3.1 Create `src/sdlc/contracts/resume_token.py` with `ResumeToken` per Architecture §608-§613:
    ```python
    schema_version: Literal[1] = 1
    phase: int
    cursor: dict[str, object] = Field(default_factory=dict)
    suggested_next_command: str
    state_hash: str
    ```
    Note: `cursor` defaults to empty dict (resume-from-clean-slate is valid).
  - [x] 3.2 Create `src/sdlc/contracts/hook_payload.py` with `HookPayload` per Architecture §615-§621:
    ```python
    schema_version: Literal[1] = 1
    hook_name: str
    target_path: str
    target_kind: str
    content_hash_before: str | None
    write_intent: str
    ```
    Note: `content_hash_before: str | None` is required-but-nullable (None for new-file creates per the implicit pattern Architecture §620 establishes for hash-before-create cases — same as `JournalEntry.before_hash`).
  - [x] 3.3 Create `src/sdlc/contracts/specialist_frontmatter.py` with `SpecialistFrontmatter` per Architecture §623-§632:
    ```python
    schema_version: Literal[1] = 1
    name: str
    title: str
    icon: str
    model: str
    tools: list[str] = Field(default_factory=list)
    read_globs: list[str] = Field(default_factory=list)
    write_globs: list[str] = Field(default_factory=list)
    description: str
    ```
    Note: `tools`/`read_globs`/`write_globs` default to empty lists. Architecture §629 says "tools: list[str]" without specifying empty-list semantics; Story 1.7 chooses default empty (a specialist with no tools is conceptually valid); validation that `write_globs` is pairwise-disjoint with sibling parallel agents is a `specialists/validator.py` (Story 2A.2) concern, NOT the contract's concern. The CONTRACT just enforces the field shape.
  - [x] 3.4 Create `src/sdlc/contracts/workflow_spec.py` with `WorkflowSpec` per Architecture §634-§643:
    ```python
    schema_version: Literal[1] = 1
    name: str
    slash_command: str
    primary_agent: str
    parallel_agents: list[str] = Field(default_factory=list)
    synthesizer_agent: str | None = None
    postconditions: list[str] = Field(default_factory=list)
    write_globs: dict[str, list[str]]
    stop_on_postcondition_failure: bool = True
    ```
    Note: `write_globs: dict[str, list[str]]` is REQUIRED (no default — Architecture §642 declares it as the per-agent write-glob map; an empty workflow with no write-globs is meaningless, fail loud).
  - [x] 3.5 Each new file opens with `from __future__ import annotations` then the typing imports then `from pydantic import ...`; no other imports. Architecture §483 + Story 1.6 leaf-discipline.
  - [x] 3.6 Verify each file: `wc -l <file>` ≤ 30; `uv run ruff check src/sdlc/contracts`; `uv run ruff format --check src/sdlc/contracts`; `uv run mypy --strict src/sdlc/contracts` — all exit 0.

- [x] **Task 4 — Verify `__init__.py` re-exports all 5 contracts and the boundary-validator stays green.** (AC: #1, #7)
  - [x] 4.1 `src/sdlc/contracts/__init__.py` body:
    ```python
    from __future__ import annotations

    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.contracts.resume_token import ResumeToken
    from sdlc.contracts.hook_payload import HookPayload
    from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
    from sdlc.contracts.workflow_spec import WorkflowSpec

    # Explicit semantic order per Story 1.7 AC1 + Architecture §1238 enumeration:
    # JournalEntry (prototype) first, then the other 4 in architecture-canonical order.
    __all__ = (  # noqa: RUF022
        "JournalEntry",
        "ResumeToken",
        "HookPayload",
        "SpecialistFrontmatter",
        "WorkflowSpec",
    )
    ```
    Architecture §1238 enumerates the 5 in order: `resume_token, journal_entry, specialist_frontmatter, workflow_yaml, hook_payload` (note: the architecture lists `journal_entry` second). Story 1.7 deliberately places `JournalEntry` FIRST in `__all__` because it is the prototype (Architecture §594 + §1238 explicitly: "`journal_entry` is the prototype; the other four follow its `schema_version` discipline"). The other 4 follow alphabetically by class name: `HookPayload`, `ResumeToken`, `SpecialistFrontmatter`, `WorkflowSpec` — but Architecture §1238 enumeration order is `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec` (which is the same sequence with `HookPayload` last per architecture's "hook_payload" position). **Final order chosen for `__all__`**: `JournalEntry`, `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec` — this matches Architecture §882-§886 directory listing order (which IS the canonical reference for file layout).
  - [x] 4.2 Verify the package surface: `uv run python -c "from sdlc.contracts import JournalEntry, ResumeToken, HookPayload, SpecialistFrontmatter, WorkflowSpec; print('ok')"` exits 0.
  - [x] 4.3 Run `uv run pre-commit run --all-files` — every hook exits 0. The boundary-validator from Story 1.4 already pre-grants `contracts/ → {errors, ids}` (via `MODULE_DEPS["contracts"]`); since Story 1.7's contracts import ONLY pydantic (third-party — boundary-validator does not flag third-party imports per `check_module_boundaries.py:177-194`), there are NO sdlc.* cross-module imports to validate, and the hook is a no-op for this story's source files.
  - [x] 4.4 Spot-test (NOT committed) the boundary-violation message: temporarily add `from sdlc.config import load_project_config` to `src/sdlc/contracts/journal_entry.py` (illustrative — `config/` is forbidden because direction is `config/ → contracts/`, not `contracts/ → config/`). Run `uv run python scripts/check_module_boundaries.py src/sdlc/contracts/journal_entry.py`; confirm exit 1 with the AC7's "does not declare … as a dependency" message. Then revert. DO NOT commit the spot-test edit.

- [x] **Task 5 — Author per-contract unit tests under `tests/unit/contracts/`.** (AC: #6)
  - [x] 5.1 Create `tests/unit/contracts/__init__.py` (empty marker); Architecture §686 "tests/ mirrors src/sdlc/ structure" expects per-module test packages. Story 1.6 established this convention with `tests/unit/errors/__init__.py` and `tests/unit/ids/__init__.py`.
  - [x] 5.2 Create `tests/unit/contracts/test_journal_entry.py` covering the AC6 Cartesian:
    - **Happy path** — construct with all required fields + canonical `monotonic_seq=1`, `ts="2026-05-08T09:42:13.487Z"`, `actor="cli"`, `kind="state_mutation"`, `target_id="EPIC-x"`, `before_hash=None`, `after_hash="sha256:abc"`, `payload={}`.
    - **Default schema_version** — `JournalEntry(monotonic_seq=1, ts="...", ...)` without explicit `schema_version` → `instance.schema_version == 1`.
    - **Schema-version rejection** — `schema_version=2` raises `ValidationError`; `schema_version=0` raises `ValidationError`.
    - **Missing required fields** — for each of `monotonic_seq, ts, actor, kind, target_id, after_hash` (omitting `payload` is OK due to default; omitting `before_hash` is NOT OK because it is required-but-nullable, MUST be passed as `None` explicitly), assert `ValidationError` names the missing field.
    - **Extra-field rejection** — `bogus_field="x"` raises `ValidationError(type="extra_forbidden", loc=("bogus_field",))`.
    - **Wrong-type rejection** — `monotonic_seq="not-an-int"` raises `ValidationError`.
    - **Frozen-mutation rejection** — `instance.monotonic_seq = 2` raises `ValidationError`.
    - **Equality** — two instances with identical args are `==`.
    - **Unhashable** — `hash(instance)` raises `TypeError` (because `payload: dict` is unhashable).
    - **JSON-canonicalization stability** — golden bytes fixture; canonicalize via:
      ```python
      import json
      def canonicalize(obj: dict) -> bytes:
          return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
      ```
      Assert `canonicalize(instance.model_dump(mode="json")) == EXPECTED_BYTES` where `EXPECTED_BYTES` is a `b'{"actor":"cli",...}'` literal checked into the test.
    - Use `@pytest.mark.unit` per `pyproject.toml:131`.
  - [x] 5.3 Create `tests/unit/contracts/test_resume_token.py` mirroring 5.2's structure for `ResumeToken`:
    - Happy path: `ResumeToken(phase=1, cursor={}, suggested_next_command="/sdlc-start", state_hash="sha256:def")`.
    - Schema-version, missing-required, extra-field, wrong-type, frozen-mutation, equality, unhashable (because `cursor: dict`), JSON-canonicalization-stability — same shape as 5.2.
  - [x] 5.4 Create `tests/unit/contracts/test_hook_payload.py` for `HookPayload`:
    - Happy path: `HookPayload(hook_name="phase_gate", target_path="04-Epics/EPIC-x.json", target_kind="epic", content_hash_before=None, write_intent="create")`.
    - Schema-version, missing-required, extra-field, wrong-type, frozen-mutation, equality.
    - **Hashability** — `hash(instance)` works (no dict fields); the test asserts `isinstance(hash(instance), int)`.
    - JSON-canonicalization-stability with golden bytes.
  - [x] 5.5 Create `tests/unit/contracts/test_specialist_frontmatter.py` for `SpecialistFrontmatter`:
    - Happy path: `SpecialistFrontmatter(name="requirement-analyst", title="Requirement Analyst", icon="📝", model="opus", tools=[], read_globs=[], write_globs=[], description="Drafts PRDs")`.
    - Schema-version, missing-required, extra-field, wrong-type (e.g. `tools="not-a-list"`), frozen-mutation, equality.
    - **Hashability** — verified in dev: pydantic v2 does NOT auto-convert `list[str]` to tuples; `SpecialistFrontmatter` is ALSO unhashable. AC6 matrix corrected to `Hashable: {HookPayload}` ONLY. Test asserts `TypeError`.
    - JSON-canonicalization-stability with golden bytes including the unicode `📝` character.
  - [x] 5.6 Create `tests/unit/contracts/test_workflow_spec.py` for `WorkflowSpec`:
    - Happy path: `WorkflowSpec(name="sdlc-start", slash_command="/sdlc-start", primary_agent="orchestrator", write_globs={"orchestrator": ["**/*"]})` — minimal required fields (the 4 list/optional defaults exercise default factories).
    - Schema-version, missing-required (especially `write_globs` — assert clear `ValidationError`), extra-field, wrong-type (e.g. `parallel_agents="not-a-list"`), frozen-mutation, equality.
    - **Unhashable** — `hash(instance)` raises `TypeError` (because `write_globs: dict`).
    - JSON-canonicalization-stability with golden bytes.
  - [x] 5.7 Run `uv run pytest tests/unit/contracts -v` — all pass. 82 tests across 5 files (16 HP + 20 JE + 14 RT + 17 SF + 15 WS).

- [x] **Task 6 — Author the F3-independence cross-contract test.** (AC: #2)
  - [x] 6.1 Create `tests/unit/contracts/test_f3_independence.py` (NEW file — not per-contract; lives under `tests/unit/contracts/` because it spans all 5):
    - Test name: `test_schema_version_is_independent_per_contract` — for each contract, construct it with `schema_version=1` (success); then for the SAME contract construct with `schema_version=2` and assert `ValidationError`; then construct the OTHER FOUR contracts with their normal defaults and assert all succeed (no cross-contract version coupling).
    - This is the explicit Decision-F3-independence guard: a future bump of `JournalEntry.schema_version` to 2 must NOT require bumping `ResumeToken`/`HookPayload`/`SpecialistFrontmatter`/`WorkflowSpec` in lockstep.
  - [x] 6.2 Use `pytest.mark.parametrize` over the 5 contract classes for compactness; the test parametrizes a `(class_under_test, valid_kwargs_for_class)` tuple and runs the same 3-step pattern (construct-v1, construct-v2-fail, sibling-survival).
  - [x] 6.3 Run `uv run pytest tests/unit/contracts/test_f3_independence.py -v` — all 5 parametrized cases pass.

- [x] **Task 7 — Verify coverage gates per AC6.** (AC: #6)
  - [x] 7.1 Run the targeted ≥ 95 gate: `uv run pytest --cov=src/sdlc/contracts --cov-branch --cov-report=term-missing --cov-fail-under=95 tests/unit/contracts`. Exit 0. (Actual: 100%).
  - [x] 7.2 Run the project-wide ≥ 90 gate: `uv run pytest`. Exit 0; coverage 98.37% across `["src/sdlc", "scripts"]`.
  - [x] 7.3 If coverage < 95 on `contracts/`: do NOT add `# pragma: no cover` to bypass — find the missing branch (likely a defensive `else`/`raise` that one of the negative-path tests should hit — but `contracts/` v1 has NO custom validators, NO defensive branches, only declarative pydantic models, so coverage gaps would be unusual). Adding `pragma: no cover` is a Story-1.4-deferred discipline ("acceptable only for `if TYPE_CHECKING:` and `@abstractmethod` per `pyproject.toml:150-152`"); nothing in `contracts/` qualifies.

- [x] **Task 8 — Whole-suite regression sweep.** (AC: #6, #7)
  - [x] 8.1 Run the full Story 1.4 + 1.5 + 1.6 quality chain locally:
    ```
    uv run ruff check src/ tests/ scripts/
    uv run ruff format --check src/ tests/ scripts/
    uv run mypy --strict src/
    uv run pre-commit run --all-files
    uv run pytest
    uv run mkdocs build --strict --site-dir _site
    ```
    Every command exits 0. Test count delta: 216 baseline → 311 total (+95 tests: 87 contract unit tests + 5 F3 parametrized + 3 existing tests delta).
  - [x] 8.2 Confirm the boundary-validator hook prints zero violations across the whole tree: `uv run python scripts/check_module_boundaries.py $(git ls-files 'src/sdlc/**.py' 'tests/**.py' 'scripts/**.py')` — exit 0.
  - [x] 8.3 Confirm `uv run python -c "import sdlc.contracts; print(sdlc.contracts.__all__)"` prints the 5-name tuple in the Task 4.1 semantic order.

- [x] **Task 9 — Update `_bmad-output/implementation-artifacts/sprint-status.yaml` AT EACH transition, NOT in a single end-of-story write.** (AC: #9)
  - [x] 9.1 At the start of dev (after `bmad-create-story` completes): `1-7-foundation-five-wire-format-pydantic-contracts: ready-for-dev` (this transition is owned by the create-story workflow itself; dev-story does NOT redo it).
  - [x] 9.2 When dev-story begins implementation: `1-7-foundation-five-wire-format-pydantic-contracts: in-progress`. Bump `last_updated:` to today's ISO date. Update `last_action:` to `"dev-story 1-7-foundation-five-wire-format-pydantic-contracts (status: ready-for-dev → in-progress)"`.
  - [x] 9.3 At code-review handoff: `1-7-foundation-five-wire-format-pydantic-contracts: review`. Same `last_updated` + `last_action` discipline.
  - [ ] 9.4 At merge: `1-7-foundation-five-wire-format-pydantic-contracts: done`. Same discipline. Epic 1's `epic-1: in-progress` stays untouched (14 stories — 1.8 through 1.21 — still backlog after Story 1.7 lands).
  - [x] 9.5 Preserve ALL comments + STATUS DEFINITIONS block in the YAML (Story 1.5 + 1.6 convention; the create-story workflow's `# Save file, preserving ALL comments and structure` instruction extends to dev-story).

- [x] **Task 10 — Resolve the HookPayload-location architectural drift in the implementation choice (NOT in a new ADR — this is a documentation-only-via-this-story-file decision following Story 1.6 Task 9 precedent).** (AC: #1, #7)
  - [x] 10.1 Architecture §884 says "`hook_payload.py # re-export from hooks/payload.py`" — i.e. the canonical pydantic model is supposed to live in `hooks/payload.py` and be re-exported from `contracts/`. BUT `hooks/` is NOT yet implemented (it's a downstream module — `MODULE_DEPS["hooks"].depends_on = {"errors", "contracts", "state", "journal", "ids"}` per `scripts/check_module_boundaries.py:74-77`). Story 1.7 implements `contracts/`, which `hooks/` will later import — the dependency direction is `hooks/ → contracts/`, NOT `contracts/ → hooks/`.
  - [x] 10.2 **Resolution (this story):** define `HookPayload` directly in `src/sdlc/contracts/hook_payload.py` (NOT a re-export from `hooks/`). Architecture §404 + §1238 explicitly enumerate `hook_payload` as one of the 5 wire-format contracts that lives in `contracts/`; §884's "re-export from hooks/payload.py" is a documentation drift from an earlier draft where the canonical home was `hooks/`. The CORRECT canonical home is `contracts/` — this is the consensus of §169-§179 (5 wire-format contracts), §382 (Decision F3 — all 5 in contracts), §403 ("5 wire-format models live in their own module … `contracts/{resume_token,journal_entry,specialist_frontmatter,workflow_yaml,hook_payload}.py`"), §1056 (`contracts/` row of the dependency table lists `HookPayload` as a member), §1238 (wire-format cluster F3+B3+D2+C3 all live in `contracts/`).
  - [x] 10.3 **DO NOT** create `src/sdlc/hooks/payload.py` for v1. When `hooks/` is later implemented (likely Story 2A.X), `hooks/payload.py` will be a THIN convenience re-export `from sdlc.contracts import HookPayload as HookPayload` — but that re-export is owned by THE FUTURE STORY that implements `hooks/`, NOT this story.
  - [x] 10.4 Document this resolution IN this story file (Dev Notes "HookPayload location resolution") and IN the eventual code-review patch's commit message; no ADR is opened. Architecture §884 will be back-fixed at the next architecture-revision pass (recorded in "Future ADR backlog item — NOT this story" below).

## Dev Notes

### File set this story creates / modifies

**NEW files (created by Story 1.7):**

```
src/sdlc/contracts/__init__.py                                            # Task 4.1
src/sdlc/contracts/journal_entry.py                                       # Task 2.2
src/sdlc/contracts/resume_token.py                                        # Task 3.1
src/sdlc/contracts/hook_payload.py                                        # Task 3.2
src/sdlc/contracts/specialist_frontmatter.py                              # Task 3.3
src/sdlc/contracts/workflow_spec.py                                       # Task 3.4
tests/unit/contracts/__init__.py                                          # Task 5.1 (empty marker)
tests/unit/contracts/test_journal_entry.py                                # Task 5.2
tests/unit/contracts/test_resume_token.py                                 # Task 5.3
tests/unit/contracts/test_hook_payload.py                                 # Task 5.4
tests/unit/contracts/test_specialist_frontmatter.py                       # Task 5.5
tests/unit/contracts/test_workflow_spec.py                                # Task 5.6
tests/unit/contracts/test_f3_independence.py                              # Task 6.1
```

**MODIFIED files:**

```
pyproject.toml                                                            # Task 1.1 (+pydantic>=2,<3 in [project] dependencies)
uv.lock                                                                   # Task 1.2 (regenerated)
_bmad-output/implementation-artifacts/sprint-status.yaml                  # Task 9 (4 transitions)
```

**Do NOT** create:
- `src/sdlc/hooks/`, `src/sdlc/config/`, `src/sdlc/concurrency/`, `src/sdlc/state/`, `src/sdlc/journal/`, or any module that is not `contracts/`. Those are owned by Stories 1.8 / 1.9 / 1.10 / 1.11 (per Architecture §1404 implementation order: `errors/ → ids/ → contracts/ → config/ → concurrency/ → state/ → journal/`).
- A new `ADR-013-wire-format-contracts.md` or any new ADR. Task 10.4 explains why; the future-story trigger is documented in "Future ADR backlog item" below. (ADR-013 is reserved for Story 1.21's wire-format-immutability lock ceremony per the Story 1.5 ADR-template precedent.)
- A `hooks/payload.py` re-export. Task 10.3 explains why; the re-export is owned by the future story implementing `hooks/`.
- A canonicalize helper inside `contracts/`. Architecture §501-§508 places `canonicalize()` at `state/` or `journal/hasher.py` (Architecture §855). Story 1.7's contracts are PURE schema declarations; the canonicalization helper is a CONSUMER concern (Stories 1.10 + 1.11). The unit-test fixture in Task 5.2-5.6 inlines a 4-line `canonicalize()` for golden-bytes assertion ONLY; it is NOT exported.
- `model_validate_json()` overrides or custom serializer methods. Pydantic v2's default `model_dump(mode="json")` produces JSON-compatible primitives that round-trip correctly with `model_validate(...)`; custom serializers would couple `contracts/` to JSON-shape concerns that are downstream consumers' responsibility.
- ADR-014 (the Story 1.6 future-trigger). Story 1.6 deferred ADR-014 to "the future story that crosses the trigger" (10th subclass or `EXIT_CODE_MAP` semantics change). Story 1.7 does NOT cross either trigger.

### HookPayload location resolution (Architecture §884 documentation drift)

Architecture §884 (`src/sdlc/contracts/hook_payload.py # re-export from hooks/payload.py`) suggests the canonical pydantic model lives in `hooks/payload.py`. This is a documentation drift from an earlier architecture draft. The CORRECT canonical home is `contracts/hook_payload.py`, supported by:

1. **§169-§179** ("five contracts cross run/process/version boundaries") — `hook_payload` is enumerated as the 5th wire-format contract; all 5 share the same architectural treatment (versioned, in `contracts/`).
2. **§382** (Decision F3 row) — "5 wire-format pydantic models" with `hook_payload` listed; per-contract `schema_version`; all live in their own module.
3. **§403** ("F3 (per-contract versioning) → 5 wire-format models live in their own module (e.g. `contracts/{resume_token,journal_entry,specialist_frontmatter,workflow_yaml,hook_payload}.py`)") — explicit enumeration places `hook_payload` in `contracts/`.
4. **§1056** (dependency-table row) — `contracts/` exports `HookPayload`; `depends_on = {"errors", "ids"}`. If `HookPayload` were OWNED by `hooks/`, the table row would be inconsistent (since `hooks/` depends on `contracts/`, putting `HookPayload` in `hooks/` would create circular import via the re-export).
5. **§1238** (wire-format cluster) — "five wire-format contracts (resume_token, journal_entry, specialist_frontmatter, workflow_yaml, hook_payload) versioned independently with their own pydantic models. `journal_entry` is the prototype" — explicitly groups all 5 as `contracts/` members.

**Resolution:** define `HookPayload` directly in `src/sdlc/contracts/hook_payload.py`. The future `hooks/` module (Story 2A.X) will import it via `from sdlc.contracts import HookPayload`. Architecture §884's verbiage is back-fixed at the next architecture-revision pass; recorded in "Future ADR backlog item" below.

### No `errors/` import in `contracts/` for v1

`MODULE_DEPS["contracts"].depends_on = frozenset({"errors", "ids"})` GRANTS the import; Story 1.7's contracts do NOT actually use `errors/` because pydantic raises its own `ValidationError` (NOT an `SdlcError` subclass) on schema violations. Wrapping `pydantic.ValidationError` in `SchemaError` would be a `state/` or `journal/` concern (the consumer that validates user-supplied JSON before storing it), NOT the contract's concern.

The `MODULE_DEPS` grant is forward-defensive: a hypothetical future contract MIGHT raise an `SdlcError` subclass from a custom validator (e.g. `WorkflowSpec` rejecting a self-referencing `parallel_agents` graph). For v1, no contract needs this. The grant remains in place; the import is unused.

**Implication:** `src/sdlc/contracts/*.py` files import ONLY from `pydantic` and `typing` (and `__future__`). The boundary-validator's "no upper-stack import" rule is satisfied trivially.

### Field Shapes Reference (verbatim from Architecture §595-§643)

| Class | Field declaration order |
|---|---|
| `JournalEntry` | `schema_version: Literal[1] = 1`, `monotonic_seq: int`, `ts: str`, `actor: str`, `kind: str`, `target_id: str`, `before_hash: str \| None`, `after_hash: str`, `payload: dict[str, object] = Field(default_factory=dict)` |
| `ResumeToken` | `schema_version: Literal[1] = 1`, `phase: int`, `cursor: dict[str, object] = Field(default_factory=dict)`, `suggested_next_command: str`, `state_hash: str` |
| `HookPayload` | `schema_version: Literal[1] = 1`, `hook_name: str`, `target_path: str`, `target_kind: str`, `content_hash_before: str \| None`, `write_intent: str` |
| `SpecialistFrontmatter` | `schema_version: Literal[1] = 1`, `name: str`, `title: str`, `icon: str`, `model: str`, `tools: list[str] = Field(default_factory=list)`, `read_globs: list[str] = Field(default_factory=list)`, `write_globs: list[str] = Field(default_factory=list)`, `description: str` |
| `WorkflowSpec` | `schema_version: Literal[1] = 1`, `name: str`, `slash_command: str`, `primary_agent: str`, `parallel_agents: list[str] = Field(default_factory=list)`, `synthesizer_agent: str \| None = None`, `postconditions: list[str] = Field(default_factory=list)`, `write_globs: dict[str, list[str]]`, `stop_on_postcondition_failure: bool = True` |

### Required-field matrix (for AC6 missing-field tests)

| Class | Required (no default) | Has default |
|---|---|---|
| `JournalEntry` | `monotonic_seq, ts, actor, kind, target_id, before_hash, after_hash` | `schema_version=1`, `payload={}` |
| `ResumeToken` | `phase, suggested_next_command, state_hash` | `schema_version=1`, `cursor={}` |
| `HookPayload` | `hook_name, target_path, target_kind, content_hash_before, write_intent` | `schema_version=1` |
| `SpecialistFrontmatter` | `name, title, icon, model, description` | `schema_version=1`, `tools=[]`, `read_globs=[]`, `write_globs=[]` |
| `WorkflowSpec` | `name, slash_command, primary_agent, write_globs` | `schema_version=1`, `parallel_agents=[]`, `synthesizer_agent=None`, `postconditions=[]`, `stop_on_postcondition_failure=True` |

**Note on `before_hash`/`content_hash_before`:** These fields are typed `str | None` and are REQUIRED — i.e. the user MUST pass either a hash string or explicitly `None`. Pydantic does not auto-default `None` for `str | None`-typed fields without an explicit default (`= None`). Story 1.7 chooses NOT to add `= None` default, because Architecture §604 + §620 specify these fields as carrying meaning ("None for creates" — the consumer must affirmatively decide if the operation is a create vs. update; silent default to `None` would mask logic errors). Test the missing-field rejection accordingly.

### Hashability matrix (for AC6 hash tests — VERIFY in dev)

Pydantic v2 frozen models compute `__hash__` by default IFF all fields are hashable. List and dict fields BREAK hashability (lists are unhashable in Python; pydantic v2 does NOT auto-convert `list[str]` to `tuple[str, ...]` for hashing).

| Class | Has dict field | Has list field | Hashable? |
|---|---|---|---|
| `JournalEntry` | yes (`payload: dict`) | no | NO — `hash(j)` raises `TypeError` |
| `ResumeToken` | yes (`cursor: dict`) | no | NO |
| `HookPayload` | no | no | YES |
| `SpecialistFrontmatter` | no | yes (`tools`, `read_globs`, `write_globs`) | NO (lists unhashable) |
| `WorkflowSpec` | yes (`write_globs: dict`) | yes | NO |

**Final matrix:** Hashable: `{HookPayload}`. Unhashable: `{JournalEntry, ResumeToken, SpecialistFrontmatter, WorkflowSpec}`.

**Action (Task 5.5):** the `SpecialistFrontmatter` test should assert `TypeError` on `hash(instance)`. If a future need for hashability surfaces (e.g. specialists used as dict keys), the future story can override `__hash__` in `SpecialistFrontmatter` to convert lists to tuples — but for v1, unhashable is correct and aligns with pydantic v2 default behaviour.

### Why pydantic v2 (not v1)

Architecture line 43: `schema_validation: 'pydantic v2'`. Decision recorded at architecture-write time; not re-litigated by this story. Key v2 features Story 1.7 relies on:

- `ConfigDict(extra="forbid", frozen=True, ...)` — replaces v1's nested `class Config:` style; cleaner + mypy-friendly.
- `Field(default_factory=...)` — same in v1 and v2, but v2 raises a build error on bare `[]`/`{}` defaults (v1 allowed them); Story 1.7 uses `default_factory` to avoid the build error.
- `Literal[1]` — both v1 and v2 support this; v2's error messages are more pydantic-idiomatic (`type == "literal_error"`).
- `model_dump(mode="json")` — v2 method (replaces v1's `dict()` + `json()` split); produces JSON-compatible primitives suitable for the canonicalize step.
- `model_config: ClassVar[ConfigDict]` — v2 idiom; mypy-strict friendly (matches Story 1.6's `code: ClassVar[str]` discipline on errors).
- Hashable frozen models — v2's frozen-model `__hash__` is field-wise-hash-of-tuple-of-values; v1's was identity-based. The Hashability matrix above relies on v2 semantics.

### Why `Literal[1]` for `schema_version` (not `int = 1`)

Architecture §587 ("pydantic validation rejects entries with `schema_version != 1`") demands strict-equals-1 semantics. Two implementations satisfy this:

| Implementation | Pros | Cons |
|---|---|---|
| `schema_version: int = 1` + custom `@field_validator("schema_version")` raising on `!= 1` | Works; mypy-strict friendly | Adds a custom validator (extra LOC, extra coverage burden, drift risk between 5 contracts) |
| **`schema_version: Literal[1] = 1` (chosen)** | Type system enforces; pydantic v2 produces `ValidationError(type="literal_error")` automatically; zero custom code; mypy-strict friendly | Adds `from typing import Literal` import (1 LOC) |

The `Literal[1]` choice is consistent with pydantic v2 idiom for "this field accepts only this constant". It also makes a future v2 bump (`schema_version: Literal[1, 2]` during a transition window, then `Literal[2]` after migration) a one-line type-annotation change instead of a custom-validator rewrite.

### Coverage gate impact + interaction with AC6

`[tool.coverage.run] source = ["src/sdlc", "scripts"]` (Story 1.4). Story 1.7 adds 5 NEW source files under `src/sdlc/contracts/` AND 6 new test files (5 per-contract + 1 F3-independence) — so:

- The project-wide ≥ 90% gate (`pyproject.toml:127, 147`) covers all 5 contract files. With pure-declarative pydantic models (zero custom validators in v1, zero conditional branches), achieving 100% line+branch coverage is trivial: every line of every model is executed by importing the module + constructing one happy-path instance.
- The **branch** dimension (`pyproject.toml:142`) is essentially free here — there are NO `if/else` branches in declarative pydantic models. Coverage gaps would come from import-time-only branches (e.g. `if TYPE_CHECKING:`) which `from __future__ import annotations` makes unnecessary; Story 1.7 contracts do NOT use `if TYPE_CHECKING:`.
- **DO NOT** add `# pragma: no cover` to bypass — the acceptable-bypass list (`pyproject.toml:150-152`) is `if TYPE_CHECKING:`, `raise NotImplementedError`, and `@(abc\.)?abstractmethod`; nothing in `contracts/` qualifies.

### Pre-commit hook chain interaction

Story 1.4 + 1.5 + 1.6 quality chain (ruff-check → ruff-format → mypy-strict → boundary-validator → specialist-validator → hygiene hooks):

- **ruff-check / ruff-format**: matches `src/sdlc/contracts/**.py` and `tests/unit/contracts/**.py`. The `required-imports = ["from __future__ import annotations"]` rule (`pyproject.toml:81`) fires if any file omits it. The `extend-exclude = ["docs/ux/", ".claude/", "_bmad/", "_bmad-output/", "_site/"]` (`pyproject.toml:55`) does NOT cover `tests/` or `src/` — both ARE linted. Per-file-ignores `tests/**` exempts `PLR2004` (magic numbers) — Story 1.7's golden-bytes literals in tests are fine under this exemption.
- **mypy-strict**: pinned to `src/` via `entry: uv run mypy --strict src/`. New `src/sdlc/contracts/` IS type-checked. `[[tool.mypy.overrides]] module = "tests.*"` (`pyproject.toml:108-110`) relaxes `disallow_untyped_defs` for tests; tests under `tests/unit/contracts/` MAY have untyped fixtures, but Story 1.7 prefers fully-typed tests as good discipline (Story 1.6 precedent).
- **boundary-validator**: matches `^(src/sdlc/|tests/|scripts/).*\.py$`. New `src/sdlc/contracts/*.py` files are routed to the `contracts` MODULE_DEPS row (already configured in Story 1.4 — `scripts/check_module_boundaries.py:38-41`). Test files under `tests/unit/contracts/` are NOT in `src/sdlc/`, so the boundary-validator just checks LOC cap (no import rules apply outside `src/sdlc/`).
- **specialist-validator**: `pass_filenames: false, always_run: true` — runs unconditionally, returns 0 (placeholder until Story 2A.2). No interaction.
- **trailing-whitespace, end-of-file-fixer, mixed-line-ending, check-yaml, check-toml**: matches the new `.py` files + the modified `pyproject.toml`. Author all new files with trailing newline + LF line endings to keep these green first-shot.
- **check-added-large-files --maxkb=500**: largest new files are the per-contract test files at maybe ~5 KB each; well under 500 KB. The lockfile diff (Task 1.2) regenerates `uv.lock` to add ~10 lines of pydantic + pydantic-core + transitive deps; the file size delta is negligible.

### Pydantic v2 import discipline (don't import what you don't use)

`from pydantic import BaseModel, ConfigDict, Field` — these are the THREE pydantic symbols Story 1.7's contracts use. NOT to be imported (and NOT used in v1):

- `from pydantic import field_validator, model_validator` — no custom validators in v1 (the `Literal[1]` and `extra="forbid"` config replace what custom validators would do).
- `from pydantic import Annotated` — no constrained-field types in v1 (`int` and `str` are sufficient; constraints like `min_length`, `gt=0` would be a v0.3 addition under a separate story).
- `from pydantic import RootModel` — no root-typed contracts in v1; all 5 contracts have at least 5 fields, so `RootModel[...]` is inappropriate.
- `from pydantic import TypeAdapter` — TypeAdapter is for parsing arbitrary types into typed values; consumer concern (Stories 1.8+).

### Previous story intelligence (Stories 1.1 + 1.2 + 1.3 + 1.4 + 1.5 + 1.6 learnings)

From the six implementation-artifact files + the deferred-work.md:

1. **Story 1.6's review patches established 5 patterns Story 1.7 inherits:**
   - Patch on `__all__` order: AC6 / AC7 mandates SEMANTIC order, not alphabetic — Story 1.7's `contracts/__init__.py` follows the same `# noqa: RUF022` pattern with semantic order (`JournalEntry` first, then the other 4).
   - Patch on `to_envelope()` returning live `details` reference: Story 1.7's contracts are FROZEN (pydantic v2 `frozen=True`), so this class of bug cannot occur — `instance.payload` is the original dict (still aliased), but the model itself cannot be mutated to swap payloads. Per Story 1.6 deferred line 535: "Type-narrowing at construction would block legitimate nested-detail use cases." — Story 1.7's `dict[str, object]` types follow the same layering principle.
   - Patch on `bool` accepted as `int`: pydantic v2's default behaviour for `int` fields is to accept `True`/`False` (silent coercion: `True == 1`, `False == 0`). For Story 1.7's `monotonic_seq: int`, `phase: int`, etc., a future patch may add `model_config = ConfigDict(strict=True)` to disable coercion. **For v1**, this is OUT-OF-SCOPE (Story 1.6's identical concern was deferred to deferred-work.md); record it as a Story 1.7 deferred item ONLY IF code review surfaces it as a real risk for the wire-format contracts.
   - Patch on `pytest.raises(... match=)` discipline: Story 1.7's tests using `pytest.raises(ValidationError)` SHOULD assert on the error's `.errors()` list contents (specifically `error["type"]` and `error["loc"]`) for clarity, NOT just the exception type.
   - Patch on hardcoded numbers in tests: Story 1.7's "5 contracts" tests should NOT hardcode `5` — derive from `__all__` length or a `_ALL_CONTRACTS` tuple at module top.
2. **Story 1.6's `details: dict[str, object]` typing rationale** (Story 1.6 Dev Notes line 370-374) extends to Story 1.7's `payload: dict[str, object]`, `cursor: dict[str, object]`, `write_globs: dict[str, list[str]]` — strict-friendly, mypy-`extra_checks`-clean.
3. **Story 1.6's `frozen=True, slots=True` dataclass convention** translates to pydantic v2's `frozen=True` config in Story 1.7. Pydantic v2 frozen models do NOT auto-add `__slots__` (that's a `dataclass` feature); the `__slots__` discipline is unique to plain dataclasses. Story 1.7 contracts are pydantic models, NOT dataclasses; `__slots__` is N/A.
4. **Story 1.6's chronological-by-story `[dependency-groups] dev` ordering** (`ruff` → `mypy` → `pytest` → `pytest-cov` → `coverage[toml]` → `pre-commit` → `mkdocs` → `hypothesis`): Story 1.7 does NOT add to dev-deps; Story 1.7 adds to `[project] dependencies` (NEW section — currently `dependencies = []`). The `<3` defensive-cap convention (mypy `<3`, pytest `<10`, pre-commit `<5`, mkdocs `<2`, hypothesis `<7`) extends naturally: pydantic gets `<3`.
5. **Story 1.5's revisit-by 12-month-from-authoring rule** is irrelevant to Story 1.7 (no new ADR), but Architecture §884 (the HookPayload-location drift) is a candidate for the next architecture revision.
6. **Story 1.4's boundary-validator hook** pre-grants `MODULE_DEPS["contracts"]` (line 38-41 of `check_module_boundaries.py`) with `depends_on = {"errors", "ids"}`. Story 1.7's source files import ONLY pydantic (third-party — boundary-validator does not flag third-party imports per `check_module_boundaries.py:177-194`); the `errors` + `ids` grants are unused but reserved for future contract evolutions.
7. **Story 1.6's `__init__.py` LOC ≤ 30** convention extends: Story 1.7's `contracts/__init__.py` will be ~25 LOC (5 imports + 5-element `__all__` + `# noqa: RUF022` comment + blank lines).
8. **Story 1.6's per-module test subdir convention** (`tests/unit/errors/`, `tests/unit/ids/`) extends: Story 1.7 adds `tests/unit/contracts/` as the third per-module test subdir.
9. **Story 1.6's `tests/property/` directory** is NOT extended by Story 1.7. Architecture §687 + §991 lists `tests/property/`; Story 1.7 does NOT add property tests because (a) the contracts have NO algorithmic properties to test (they are pure declarative schemas; the only "invariant" is the F3 independence which is a single explicit test, NOT a hypothesis-generated one), (b) the JSON-canonicalization stability is asserted via golden-bytes fixtures — a hypothesis generator would not stress this any further than the per-contract unit tests do. If a future story adds runtime invariants to contracts (e.g. `WorkflowSpec` graph reachability checks), THAT story adds a property test under `tests/property/test_<contract>_invariant.py`.
10. **Story 1.5's mkdocs `--strict` build**: Story 1.7 adds NO docs surfaces (no new ADR, no new architecture doc, no new index entry). The build stays green by virtue of doing nothing in `docs/`.

### Git intelligence (last 5 commits)

- `4673090 feat: implement foundation modules - errors and ids (Story 1.5-1.6)` — added `src/sdlc/errors/` + `src/sdlc/ids/` + `tests/unit/{errors,ids}/` + `tests/property/test_ids_roundtrip.py` + `hypothesis>=6.100,<7` dev-dep + ADR-012-module-layout.md + ADR template + 10 review patches. Story 1.7 follows the exact same per-module structural pattern (per-contract source file + per-contract test file + `__init__.py` re-exports + semantic-ordered `__all__`). Test count baseline: 216 → ~290-310 after Story 1.7.
- `67489d3 feat: implement module boundary enforcement with pre-commit hooks (Story 1.4)` — added `scripts/check_module_boundaries.py` with `MODULE_DEPS["contracts"]` already configured (line 38-41, granting `depends_on={"errors","ids"}` and `forbidden_from={"engine","dispatcher","cli"}`). Story 1.7 needs ZERO changes to `MODULE_DEPS`; the hook is pre-configured.
- `ca4cb92 feat: add BMad workflow infrastructure and Story 1-3 CI/CD implementation` — added `.github/workflows/{ci,e2e,release,docs}.yml` + ADR-006/007/008/009. The `ci.yml` 8-cell matrix (Python 3.10/3.11/3.12/3.13 × ubuntu/macos) will run Story 1.7's tests on every PR; the `--frozen` cache invalidates ONCE when pydantic is added (Task 1.2), then caches for subsequent runs.
- `0b4acd9 upload (Story 1.2)` — established `[tool.mypy] strict = true`, `[tool.pytest.ini_options] minversion = "8.0"`, `[tool.coverage.report] fail_under = 90`. Story 1.7 inherits all three. `extra_checks = true` (line 106) bans `Any`-leak; Story 1.7's `dict[str, object]` typing matches.
- `0dd96ea feat: bootstrap sdlc-framework with uv + hatchling (Story 1.1)` — initial `pyproject.toml` with `dependencies = []`. Story 1.7 is the FIRST story to add to `[project] dependencies` (pydantic). No prior story has touched `dependencies`; the field has been empty since project bootstrap.

The 5-commit window confirms: every quality gate is configured, the boundary-validator pre-knows about `contracts/`, the `MODULE_DEPS` table reserves `contracts/`'s slot at the 5th-deepest leaf level, and `pyproject.toml` is ready to receive its first runtime dep.

### Latest tech information (2026-05 lookup)

- **Pydantic v2.x stability**: pydantic v2.x has been GA since June 2023; the latest 2.x line as of 2026-05 is 2.9+. Architecture line 43 specifies "pydantic v2" without minor pin; Story 1.7's `>=2,<3` constraint is correct. Note: pydantic v2 has a planned v3 on the medium-term roadmap with rust-core stabilization changes; the `<3` cap is defensive-future-proofing, not a current-version concern. Resolved version on disk will be captured per Task 1.2.
- **`pydantic-core` transitive dep**: pydantic v2 depends on `pydantic-core` (Rust-backed validator). The `uv sync` regeneration in Task 1.2 pulls both. The wheel install is fast (~50 ms cold-start budget impact); CLI cold-start is unaffected because `cli/` defers imports per Architecture §488 ("No top-level imports in `cli/` modules — defer-import inside command bodies"). Story 1.7's contracts import pydantic at module-load time, but `contracts/` is NOT a `cli/` module.
- **`Literal[1]` + pydantic v2**: pydantic v2 produces `ValidationError` with `error["type"] == "literal_error"` for non-matching inputs (NOT `"value_error"` as in pydantic v1). Tests must assert on the v2 error type, not the v1 type.
- **`Field(default_factory=list)` + pydantic v2**: standard idiom; supported since pydantic v1; v2 retains it. Bare `= []` triggers `PydanticUserError` at model-build time in v2 (was a silent bug in v1).
- **`model_config: ClassVar[ConfigDict]` + mypy-strict**: the `ClassVar[ConfigDict]` annotation is the canonical form for pydantic v2 + mypy-strict. Bare `model_config = ConfigDict(...)` typechecks but mypy may emit `[misc]` warnings about the dynamic-attribute pattern; explicit `ClassVar[ConfigDict]` documents intent and silences the warning.
- **`model_dump(mode="json")` vs `model_dump()`**: `mode="python"` (default) returns Python primitives that include things like `datetime` objects (NOT JSON-serializable directly); `mode="json"` returns JSON-serializable primitives (`datetime` becomes `str` etc.). Story 1.7's golden-bytes fixtures use `mode="json"` for canonicalize-compatibility.
- **`extra="forbid"` + pydantic v2**: error type is `"extra_forbidden"` in v2 (was `"value_error.extra"` in v1). Tests assert on the v2 type.
- **`frozen=True` + pydantic v2**: post-construction mutation raises `ValidationError` in v2 (was `TypeError` in v1). Tests assert on `ValidationError` for v2.
- **`pydantic-core` performance**: Rust-backed validator; ~10× faster than pydantic v1 for typical model construction; the per-contract construction in Story 1.7's tests should run in microseconds. No benchmark concern.

### Project Structure Notes

- **Alignment with unified project structure** (Architecture §881-§886, §1056): canonical `src/sdlc/contracts/{__init__.py, journal_entry.py, resume_token.py, hook_payload.py, specialist_frontmatter.py, workflow_spec.py}` filenames are honored exactly. Architecture §884's "re-export from hooks/payload.py" wording is back-fixed by Task 10.2's resolution; the FILENAME `hook_payload.py` is correct.
- **Detected variance: HookPayload-location drift** (Architecture §884) — resolved in this story per Task 10. This is a documentation drift, NOT a structural variance; the file is `src/sdlc/contracts/hook_payload.py` per the consensus of §169-§179, §382, §403, §1056, §1238.
- **`tests/unit/contracts/` directory creation**: NEW subdirectory introduced by this story. Architecture §686 says "tests/ mirrors src/sdlc/ structure"; Story 1.6 established `tests/unit/errors/` and `tests/unit/ids/` (the first two per-module subdirs). Story 1.7 adds `tests/unit/contracts/` as the third.
- **No `tests/property/test_<contract>_*.py` added**: contracts are pure declarative schemas without algorithmic invariants; per Dev Notes "Previous story intelligence" #9, property tests are deferred to a future story if invariants surface.

### Future ADR backlog item — NOT this story

A future story (likely Story 1.21's wire-format-immutability lock ceremony, OR the next architecture-revision pass) will:

- Author `ADR-013-wire-format-contracts.md` (the Story 1.5 ADR-template precedent reserves ADR-013 for wire-format-related decisions; Story 1.21's lock ceremony is the natural carrier).
- Back-fix Architecture §884's wording from "`hook_payload.py # re-export from hooks/payload.py`" to "`hook_payload.py # canonical HookPayload pydantic model`".
- Document the `extra="forbid", frozen=True, str_strip_whitespace=False` config triple as the wire-format-stable pattern; call out that any change to this triple is a wire-format event (Decision F3) requiring per-contract migration discipline.
- Document the `Literal[1]` schema_version idiom as the canonical pydantic-v2 pattern for "this field accepts only this value" — and the migration path (`Literal[1, 2]` during transition window, then `Literal[2]` after migration).
- Document the JSON-canonicalize-via-`json.dumps(model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))` pattern as the canonical wire-format-byte-stable pattern; reference Story 1.21's golden-corpus fixtures.

**Owner:** Story 1.21 (the natural carrier — its lock ceremony codifies all wire-format decisions). Recorded HERE so a story-slicer or sprint-planner knows the trigger.

### Why no JSON-canonicalize helper in `contracts/`

Architecture §501-§508 + §855 places `canonicalize()` at `state/` (specifically `journal/hasher.py` per §855: "canonicalize + sha256 (Pattern §3)"). The architecture's intent is:
- `contracts/` declares WHAT the wire format IS.
- `state/` + `journal/` declare HOW to serialize/hash it.

Putting `canonicalize()` in `contracts/` would couple schema declarations to serialization concerns — a violation of the "pure declarative schemas" principle. Story 1.7's tests inline a 4-line `canonicalize()` ONLY for golden-bytes assertion; the real `canonicalize()` lives in Story 1.10 / 1.11 modules.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.7](_bmad-output/planning-artifacts/epics.md) (lines 576–599) — original BDD acceptance criteria for the 5 wire-format pydantic contracts.
- [Source: _bmad-output/planning-artifacts/architecture.md#Wire-format-contracts](_bmad-output/planning-artifacts/architecture.md) (lines 169–179) — 5 wire-format contracts cross run/process/version boundaries; must be schema-versioned.
- [Source: _bmad-output/planning-artifacts/architecture.md#The-Five-Wire-Format-Contract-Schemas](_bmad-output/planning-artifacts/architecture.md) (lines 591–644) — verbatim pydantic model definitions for all 5 contracts; AC1's field shape table maps directly to these lines.
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-F3](_bmad-output/planning-artifacts/architecture.md) (line 382) — per-contract `schema_version` field; each contract evolves independently.
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-B3](_bmad-output/planning-artifacts/architecture.md) (line 347) — JournalEntry as the prototype: flat JSONL with `{schema_version: 1, ts, monotonic_seq, actor, kind, target_id, before_hash, after_hash, payload}`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision-D2](_bmad-output/planning-artifacts/architecture.md) (line 364) — HookPayload as the 5th wire-format contract; Pydantic model `HookPayload(schema_version=1, hook_name, target_path, target_kind, content_hash_before, write_intent)`.
- [Source: _bmad-output/planning-artifacts/architecture.md#JSON-Canonicalization-Rules](_bmad-output/planning-artifacts/architecture.md) (lines 496–515) — `canonicalize()` formula (`sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`); used in AC5's golden-bytes test.
- [Source: _bmad-output/planning-artifacts/architecture.md#Identifier-Naming-Conventions](_bmad-output/planning-artifacts/architecture.md) (line 439) — Pydantic wire-format models use canonical PascalCase names per contract.
- [Source: _bmad-output/planning-artifacts/architecture.md#Code-Style-Beyond-Ruff](_bmad-output/planning-artifacts/architecture.md) (lines 483–494) — no `print()` in foundation modules, no `time.time()` for ordering, no `os.environ[...]` direct access.
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Specifications](_bmad-output/planning-artifacts/architecture.md) (line 1056) — `contracts/` row: 5 wire-format pydantic models; `depends_on: errors/, ids/`; `forbidden_from: engine, dispatcher, cli`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Architectural-Boundaries-Import-Rules](_bmad-output/planning-artifacts/architecture.md) (lines 1077–1112) — eight specific boundary rules; rule #8 ("foundation layer; none imports from upper stack") covers `contracts/`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Folder-File-Layout](_bmad-output/planning-artifacts/architecture.md) (lines 881–886) — `src/sdlc/contracts/` directory listing (5 files).
- [Source: _bmad-output/planning-artifacts/architecture.md#Wire-format-cluster](_bmad-output/planning-artifacts/architecture.md) (line 1238) — F3+B3+D2+C3 wire-format cluster: 5 contracts with `journal_entry` as the prototype.
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation-Handoff](_bmad-output/planning-artifacts/architecture.md) (line 1404) — implementation order: `errors/ → ids/ → contracts/ → config/ → concurrency/`. Story 1.7 implements `contracts/`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Test-Organization-and-Naming](_bmad-output/planning-artifacts/architecture.md) (lines 682–701) — `tests/unit/<module-mirror>/test_<module>.py` mirror; function naming `test_<behavior>_<expected_outcome>`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Cross-Cutting-Concerns-Module-Mapping](_bmad-output/planning-artifacts/architecture.md) (line 1198) — Concern 14 (Wire-format contracts) is owned by `contracts/` (5 modules, independently versioned).
- [Source: _bmad-output/planning-artifacts/architecture.md#Technical-Constraints](_bmad-output/planning-artifacts/architecture.md) (line 43) — `schema_validation: 'pydantic v2'` baseline.
- [Source: _bmad-output/planning-artifacts/prd.md](_bmad-output/planning-artifacts/prd.md) — NFR-MAINT-2 (≥95% coverage) applies; NFR-REL-2 (journal append-only) future-couples to `JournalEntry`.
- [Source: scripts/check_module_boundaries.py](scripts/check_module_boundaries.py) (lines 38–41, 297–319) — `MODULE_DEPS["contracts"]` row; leaf-discipline violation message format.
- [Source: pyproject.toml](pyproject.toml) (lines 11, 17–27, 95–110, 115–157) — `[project] dependencies` (currently empty — Story 1.7 adds pydantic); `[dependency-groups] dev` chronological-by-story convention; mypy-strict config; pytest+coverage gates.
- [Source: docs/decisions/ADR-012-module-layout.md](docs/decisions/ADR-012-module-layout.md) — Story 1.5 back-fill of the 16-module DAG; cites Architecture §1052–§1112 verbatim. `contracts/` is the 3rd-deepest leaf per the §1100 ASCII diagram.
- [Source: docs/decisions/ADR-002-ruff-config.md](docs/decisions/ADR-002-ruff-config.md) — `required-imports = ["from __future__ import annotations"]` + complexity ≤ 8 + line length 100.
- [Source: docs/decisions/ADR-003-mypy-strict.md](docs/decisions/ADR-003-mypy-strict.md) — `strict = true` + `extra_checks = true` ban-Any policy.
- [Source: docs/decisions/ADR-004-pytest-config.md](docs/decisions/ADR-004-pytest-config.md) — `--strict-markers` + `--strict-config` + `filterwarnings = ["error"]` + `xfail_strict = true`.
- [Source: docs/decisions/ADR-010-pre-commit-config.md](docs/decisions/ADR-010-pre-commit-config.md) — Story 1.4 boundary-validator hook; LOC cap 400; leaf-discipline behavior.
- [Source: _bmad-output/implementation-artifacts/1-6-foundation-errors-and-ids-modules.md](_bmad-output/implementation-artifacts/1-6-foundation-errors-and-ids-modules.md) — Story 1.6 establishes the per-module subdir convention, the `# noqa: RUF022` semantic-`__all__` pattern, and the 10-patch review checklist that Story 1.7 inherits as best-practice baseline.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md](_bmad-output/implementation-artifacts/deferred-work.md) — current deferred-work ledger; Story 1.7 opens NO new entries at planning level.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (claude-sonnet-4-6)

### Latest Tech Information (Resolved)

- **pydantic**: 2.13.4 (resolved by `uv sync`)
- **pydantic-core**: 2.46.4 (transitive dep, Rust-backed validator)
- **typing-inspection**: 0.4.2 (transitive dep added by pydantic 2.13.x)
- **annotated-types**: 0.7.0 (transitive dep)

### Debug Log References

No blocking issues encountered. Key dev-time findings:
- `SpecialistFrontmatter` is unhashable due to `list[str]` fields — pydantic v2 does NOT auto-convert lists to tuples for hashing. Final hashable set: `{HookPayload}` only.
- Ruff's `I001` (import sort) flagged `__init__.py` imports since they were in semantic order; fixed by sorting imports alphabetically (independent of `__all__` semantic order).
- Several test file lines exceeded 100-char limit; fixed by splitting golden-bytes literals and `_canonicalize` call.

### Completion Notes List

- Task 1: Added `pydantic>=2,<3` to `[project] dependencies` in `pyproject.toml`; regenerated `uv.lock` with pydantic 2.13.4 + pydantic-core 2.46.4 + typing-inspection 0.4.2 + annotated-types 0.7.0. Verified `from pydantic import BaseModel, ConfigDict, Field` resolves.
- Task 2: Authored `src/sdlc/contracts/journal_entry.py` with `JournalEntry` — prototype contract with `Literal[1]`, `frozen=True`, `extra="forbid"`, `str_strip_whitespace=False`. 25 LOC. `__init__.py` created with sorted imports + `# noqa: RUF022` semantic `__all__`. 17 LOC.
- Task 3: Authored all 4 follow-on contracts: `resume_token.py` (21 LOC), `hook_payload.py` (22 LOC), `specialist_frontmatter.py` (25 LOC), `workflow_spec.py` (25 LOC). All follow `JournalEntry` prototype shape. `HookPayload` defined directly in `contracts/` per architecture consensus (§169-§179, §382, §403, §1056, §1238).
- Task 4: `__init__.py` re-exports all 5 in semantic order; ruff+mypy+boundary-validator all green. `uv run pre-commit run --all-files` exits 0.
- Task 5: 82 per-contract unit tests across 6 files. Full Cartesian per contract: happy path, default schema_version, schema_version rejection (v0 + v2), missing required fields (parametrized), extra-field, wrong-type, frozen-mutation, equality, hashability matrix, JSON-canonicalization golden bytes. Hashability: `HookPayload` hashable; `JournalEntry`, `ResumeToken`, `SpecialistFrontmatter`, `WorkflowSpec` unhashable.
- Task 6: `test_f3_independence.py` with 5 parametrized cases (one per contract). Verifies Decision F3 independence: bumping one contract's schema_version does not affect siblings. All 5 pass.
- Task 7: Targeted 95% gate: 100% line+branch coverage on `src/sdlc/contracts/`. Project-wide 90% gate: 98.37% (311 tests). Both gates pass.
- Task 8: Full quality chain (ruff check + format, mypy --strict, pre-commit, pytest, mkdocs --strict) all exit 0. Boundary-validator zero violations. `__all__` tuple confirmed correct.
- Task 9: Sprint-status updated: `ready-for-dev → in-progress` at dev-story start; `in-progress → review` at code-review handoff.
- Task 10: HookPayload defined in `contracts/hook_payload.py` (canonical per §169-§179, §382, §403, §1056, §1238). Architecture §884 drift documented; back-fix deferred to Story 1.21 / next architecture-revision pass.

### File List

**New files:**
- `src/sdlc/contracts/__init__.py`
- `src/sdlc/contracts/journal_entry.py`
- `src/sdlc/contracts/resume_token.py`
- `src/sdlc/contracts/hook_payload.py`
- `src/sdlc/contracts/specialist_frontmatter.py`
- `src/sdlc/contracts/workflow_spec.py`
- `tests/unit/contracts/__init__.py`
- `tests/unit/contracts/test_journal_entry.py`
- `tests/unit/contracts/test_resume_token.py`
- `tests/unit/contracts/test_hook_payload.py`
- `tests/unit/contracts/test_specialist_frontmatter.py`
- `tests/unit/contracts/test_workflow_spec.py`
- `tests/unit/contracts/test_f3_independence.py`

**Modified files:**
- `pyproject.toml` (added `pydantic>=2,<3` to `[project] dependencies`)
- `uv.lock` (regenerated with pydantic 2.13.4 + transitive deps)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status transitions)

### Review Findings

**Code review completed: 2026-05-08** — 3 parallel layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor). All AC1–AC9 PASS per Auditor verdict; coverage 100% per file; mypy --strict + ruff exit 0. Findings below are quality/discipline improvements, not AC blockers.

#### Resolved decisions (now patches)

- [x] [Review][Patch][Decision-A] **Deep-freeze container fields via immutable types** [src/sdlc/contracts/journal_entry.py:25, resume_token.py:19, specialist_frontmatter.py:22-24, workflow_spec.py:21-24] — Switch `list[str]` fields → `tuple[str, ...]`; switch `dict[str, object]` and `dict[str, list[str]]` → `Mapping[...]` with `@field_validator(mode="after")` auto-wrap into `MappingProxyType` (and inner lists into tuples for `WorkflowSpec.write_globs`). Update tests to assert `TypeError` on mutation attempts (`je.payload["x"] = 1`, `sf.tools.append("rogue")`, etc.). Hashability matrix changes: with tuples instead of lists and frozen-dicts instead of dicts, `JournalEntry`/`ResumeToken`/`WorkflowSpec` MAY become hashable — re-verify and update `test_hashability` per contract.
- [x] [Review][Patch][Decision-A] **`Field(ge=0)` on `monotonic_seq` and `phase`** [src/sdlc/contracts/journal_entry.py:90, resume_token.py:121] — Add `Field(ge=0)` constraint; add negative-int rejection test per contract (`type=="greater_than_equal"`).
- [x] [Review][Patch][Decision-A] **RFC 3339 regex on `ts` (UTC `Z` only)** [src/sdlc/contracts/journal_entry.py:91] — Use `Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")]`. Keeps `str` (byte-stability preserved), enforces format. Add test rejecting `"yesterday"` and accepting `"2026-05-08T09:42:13.487Z"`.
- [x] [Review][Patch][Decision-C] **`sha256:` regex on all `*_hash` fields with nullable handling** [journal_entry.py:95-96, hook_payload.py:65, resume_token.py:124] — `Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]` for required hashes (`after_hash`, `state_hash`); union with `None` for nullables (`before_hash`, `content_hash_before`). Update test fixtures from `"sha256:abc"` to a real-shape literal (e.g. `"sha256:" + "a"*64`). Add per-contract format-rejection test.
- [x] [Review][Patch][Decision-B] **`Field(min_length=1, max_length=4)` on `icon`** [src/sdlc/contracts/specialist_frontmatter.py:150] — Pragmatic cap allows compound emojis (ZWJ, skin-tone modifiers, up to 4 codepoints). Add rejection test for empty string and 5+ codepoint strings.

#### Patch

- [x] [Review][Patch] **`Literal[1]` accepts `True` and `1.0` due to pydantic lax-mode coercion** [src/sdlc/contracts/*.py:17] — `JournalEntry(schema_version=True)` and `JournalEntry(schema_version=1.0)` both succeed. Same root cause: `WorkflowSpec(stop_on_postcondition_failure="yes")` coerces to `True`. Fix: add per-field `Field(strict=True)` on `schema_version` (5 contracts) + `stop_on_postcondition_failure` (workflow_spec.py:25), and add 5+1 negative tests. CRITICAL severity per Edge Case Hunter.
- [x] [Review][Patch] **Canonicalization-stability test only constructs each instance once** [tests/unit/contracts/test_*.py — `_GOLDEN`/`test_canonical_bytes_stable`] — AC5 requires byte-stability across init orders, but tests construct one path and compare to golden. Add a parametrized test that initializes the same logical instance with kwargs in two different declaration orders and asserts identical canonical bytes.
- [x] [Review][Patch] **`test_roundtrip_via_model_dump` uses default `mode="python"`, not `mode="json"`** [tests/unit/contracts/test_journal_entry.py:55-59 + 4 siblings] — Real wire-format invariant is `cls(**json.loads(json.dumps(model_dump(mode="json"))))`. Add explicit JSON-mode roundtrip test per contract.
- [x] [Review][Patch] **No test locks in `str_strip_whitespace=False` semantics** [tests/unit/contracts/*] — Whitespace preservation is intentional for byte-stability, but a future flip to `True` would not be caught by existing canonical-bytes tests on whitespace-free goldens. Add `test_whitespace_is_preserved_not_stripped` per contract using `"  hook_name  "` style fixtures.
- [x] [Review][Patch] **`__all__` tuple contents not asserted by any test** [src/sdlc/contracts/__init__.py:32-38] — Spec mandates 5 specific names in semantic order with `# noqa: RUF022`. Add a test: `assert sdlc.contracts.__all__ == ("JournalEntry","ResumeToken","HookPayload","SpecialistFrontmatter","WorkflowSpec")` to lock-in drift.
- [x] [Review][Patch] **`__init__.py` imports are alphabetic but `__all__` is semantic — unmotivated inconsistency** [src/sdlc/contracts/__init__.py] — Either reorder imports to match `__all__` semantic order (with paired `# noqa: I001`), OR add an inline comment explaining the intentional discrepancy (ruff `I001` requires alphabetic imports; `__all__` is semantic per Architecture §1238).
- [x] [Review][Patch] **`# type: ignore[call-overload]` is the wrong code — should be `[call-arg]`** [tests/unit/contracts/test_hook_payload.py:379, test_journal_entry.py:529, test_resume_token.py:664, test_specialist_frontmatter.py:803, test_workflow_spec.py:946] — Expected mypy error for unexpected keyword is `[call-arg]`, not `[call-overload]`. If mypy upgrades or `--warn-unused-ignores` is enabled, all 5 will surface as `unused-ignore`.
- [x] [Review][Patch] **`_REQUIRED_FIELDS` lists are not asserted exhaustive against `model_fields`** [tests/unit/contracts/test_*.py] — If a new required field is added to a contract, the parametrized missing-field test won't fail; it'll silently skip coverage. Add an assertion per contract: `assert set(_REQUIRED_FIELDS) == {n for n,f in Contract.model_fields.items() if f.is_required()}`.
- [x] [Review][Patch] **Unicode canonical-bytes test only on 2/5 contracts** [tests/unit/contracts/test_journal_entry.py + test_specialist_frontmatter.py only] — `HookPayload`, `ResumeToken`, `WorkflowSpec` have no UTF-8 round-trip assertion. Parametrize the unicode test across all 5 contracts using a non-ASCII fixture per contract (e.g. `target_path` with `é`, `suggested_next_command` with emoji).

#### Deferred (real but not blocking this story)

- [x] [Review][Defer] **Empty-string `before_hash`/`after_hash`/`content_hash_before`/`state_hash` accepted as valid** [journal_entry.py:23-24, hook_payload.py:21, resume_token.py:21] — broader "non-empty string" invariant unenforced; fix when hash-format regex is decided.
- [x] [Review][Defer] **`dict[str, object]` payload/cursor doesn't propagate `extra="forbid"` to nested keys** [journal_entry.py:25, resume_token.py:19] — likely intentional (open-ended `payload` per Architecture §606), but no test documents the choice; add documentation test in next contracts revision.
- [x] [Review][Defer] **Five contracts repeat identical `model_config` ClassVar — DRY refactor candidate** [all 5 contract files] — `ContractBase(BaseModel)` with shared `model_config` would centralize byte-stability config. Defer to follow-up refactor; risk of premature abstraction now.
- [x] [Review][Defer] **F3 module-import-time entanglement check via AST** [test_f3_independence.py] — Stronger test would inspect each module's `model_fields["schema_version"].annotation` to assert separate `Literal` per class. Lower-confidence enhancement.
- [x] [Review][Defer] **`WorkflowSpec.write_globs={}` is structurally valid but semantically empty** [workflow_spec.py:24] — Empty dict satisfies type but means "no agent can write anything." Semantic invariant; defer to dispatcher integration story.
- [x] [Review][Defer] **Coverage gate discrepancy: `pyproject.toml` 90% vs AC6 95% on contracts/** [pyproject.toml:129, :149] — Currently moot (100% achieved per file), but per-package gate at 95% would protect the AC. Track for future per-package coverage configuration.
- [x] [Review][Defer] **Hypothesis is a dev dependency but no property tests for canonicalization** [pyproject.toml:28] — Canonical-bytes byte-stability is a natural fit for `@given`. Add in future test-hardening story.
- [x] [Review][Defer] **Spec inconsistencies in story 1.7 itself** [_bmad-output/implementation-artifacts/1-7-foundation-five-wire-format-pydantic-contracts.md] — (a) AC1 surface text says `schema_version: int = 1` but AC2 mandates `Literal[1]` — dev correctly chose Literal; (b) AC4/AC6 contradict on SpecialistFrontmatter hashability (lines 84 vs 110 vs 333) — dev correctly implemented as unhashable. Spec edit follow-up; no code change needed.

#### Dismissed (5 findings — false positives or intentional)

- `JournalEntry` hashability test asserts unhashable correctly (AC4 mandates this; not "passing for wrong reason").
- `WorkflowSpec.write_globs` having no `default_factory` is INTENTIONAL per spec (required field).
- `str_strip_whitespace=False` is INTENTIONAL documentation of byte-stability invariant, not redundant.
- F3 vs per-contract test fixture differences (`name="req-analyst"` vs `"requirement-analyst"`) are cosmetic.
- F3 independence test scope (only `Literal[1]` vs `2`) is adequate per AC2 surface contract.

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-08 | Story 1.7 created via bmad-create-story workflow (status: backlog → ready-for-dev) | Vuonglq01685 |
| 2026-05-08 | Story 1.7 implemented via bmad-dev-story workflow (status: ready-for-dev → review). Added 5 pydantic v2 wire-format contracts + 13 source/test files + pydantic>=2,<3 runtime dep. 311 tests, 98.37% project-wide coverage, 100% contracts coverage. | claude-sonnet-4-6 |
| 2026-05-08 | Story 1.7 code-reviewed via bmad-code-review workflow (status: review → done). Applied 14 patches: 5 from decisions (deep-freeze containers via tuple+MappingProxyType, Field(ge=0) on monotonic_seq/phase, RFC 3339 regex on ts, sha256 regex on *_hash with nullable, icon length cap), 9 from initial review (strict schema_version + bool, JSON-mode roundtrip, kwargs-order canonical stability, whitespace preservation, __all__ namespace test, imports-vs-__all__ ordering, # type: ignore code fix, _REQUIRED_FIELDS exhaustiveness, unicode canonical for all 5 contracts). 374 tests, 98.58% project coverage, 100% contracts coverage. mypy --strict + ruff + pre-commit all green. 8 items deferred to deferred-work.md, 5 dismissed as noise. | claude-opus-4-7 |
