# ADR-012: 16-Module Dependency Layout

**Status:** Accepted (2026-05-08, Story 1.4; ADR back-filled 2026-05-09, Story 1.5).

## Context

Story 1.4 implemented the module-boundary enforcement pre-commit hook
(`scripts/check_module_boundaries.py`) encoding the 16-module DAG as a `MODULE_DEPS`
Python literal. This ADR back-fills the rationale for the layout decision.

Architecture §1052–§1112 is the canonical source-of-truth for the 16-module substrate
DAG and the eight specific boundary rules. Story 1.4's `MODULE_DEPS` literal in
`scripts/check_module_boundaries.py` is the machine-encoded form of that table.

AR-MODULES and AR-IMPORT-RULES (Additional Requirements from `epics.md`) mandate that
the 16-module layout is mechanically enforced, not just documented. Without commit-time
boundary enforcement, Architecture §1300–§1310 "panel-review leaks" materialise at
week 6 of implementation (engine importing runtime/claude.py directly; dashboard writing
state; hooks calling back into engine) when refactoring cost is highest.

## Decision

The 16-module dependency DAG is encoded as a `MODULE_DEPS: dict[str, ModuleSpec]`
Python literal in `scripts/check_module_boundaries.py`. The layout follows
Architecture §1052–§1112 exactly, with two documented widenings (see Consequences).

The canonical source-of-truth for the full DAG is Architecture §1052–§1112. The
`MODULE_DEPS` literal is a second source of truth; drift between them is caught by
PR review discipline (any PR touching `scripts/check_module_boundaries.py` or
`_bmad-output/planning-artifacts/architecture.md` must update both in the same commit).

### Eight specific boundary rules from Architecture §1103 (audit copy)

Reproduced verbatim from Architecture §1103 so an operator can verify the enforcement
matches the spec by reading this ADR alone.

1. **`cli/` is the only module that may invoke external binaries** other than `runtime/`.
   `cli/git.py` and `cli/gh.py` wrap subprocess calls; `runtime/claude.py` is the third
   permitted subprocess invoker.
2. **`engine/` and `dispatcher/` import `runtime/` only via the `AIRuntime` ABC.**
   Direct import of `runtime/claude.py` outside `runtime/` is forbidden.
3. **`state/` and `journal/` are siblings, not parent-child.** Both are leaves of the
   lower stack. Engine reads via `state.projection`; never imports `journal` and `state`
   together for read paths — projection is the bridge.
4. **`dashboard/` is read-only** with respect to state and journal. No write API in v1.
5. **`hooks/` does not import `engine/` or `dispatcher/`.** Hooks receive a `HookPayload`
   and operate; they do not call back into engine internals.
6. **`adopt/` does not import `engine/` or `dispatcher/`.** Adopt initializes empty
   state; engine handles flow afterward.
7. **`workflows/` and `specialists/` do not import `engine/`, `dispatcher/`, or
   `runtime/`.** They are pure validators / loaders.
8. **`contracts/`, `ids/`, `config/`, `concurrency/`, `errors/` form the foundation
   layer.** None imports anything from the upper stack.

### Enforcement matrix

| Rule | §-anchor | Statically enforced by boundary-validator | Enforcement mode |
|------|----------|-------------------------------------------|------------------|
| #1 | §1103-#1 | No — subprocess callers policy | Code review |
| #2 | §1103-#2 | No — ABC sub-module discipline | Code review |
| #3 | §1103-#3 | Yes — each of state/journal excludes the other | Static (undeclared-dep branch) |
| #4 | §1103-#4 | Partial — `dashboard` may import `state` and `journal` modules at module-level (read-only intent enforced by absence of write-path API in v1); write-path imports (`state.atomic`, `journal.writer`) blocked at code review | Static (no write API in v1 surface) + code review (write-path imports) |
| #5 | §1103-#5 | Yes — SPECIFIC_RULE_MAP hooks→engine/dispatcher | Static |
| #6 | §1103-#6 | Yes — SPECIFIC_RULE_MAP adopt→engine/dispatcher | Static |
| #7 | §1103-#7 | Yes — SPECIFIC_RULE_MAP workflows/specialists→engine/dispatcher/runtime | Static |
| #8 | §1103-#8 | Yes — errors-leaf branch in check_imports | Static |

## Alternatives Considered

- **Parsing architecture markdown at runtime** to derive `MODULE_DEPS`: Rejected per
  Story 1.4 — architecture markdown is human-readable prose, not machine-readable data.
  The script needs deterministic, typed data; a markdown parser introduces brittleness
  on any formatting change.
- **Python `__init__.py` `__all__` filters** for namespace enforcement: Rejected —
  leaks dynamic-import bypass paths; does not catch `from sdlc.engine import _internal`
  patterns; incompatible with the forward-AST-walk approach that catches imports
  before they execute.
- **Fully manual code-review-only enforcement**: Rejected — week-six refactor pain
  is the documented failure mode (Architecture §1300–§1310); boundary leaks are
  cheap to introduce and expensive to remove once the DAG is deep.
- **YAML or TOML data file for `MODULE_DEPS`**: Rejected — the `frozenset` and
  `ModuleSpec` dataclass types are meaningful; serialising them into YAML reintroduces
  parse-and-validate friction on every hook run.

## Consequences

- Every boundary leak fails pre-commit / CI before week-six refactor pain.
- The dependency table is an audit-grade artifact discoverable via this ADR and the
  docs site ([Architecture Overview](../architecture-overview.md)).
- "Where does this module go?" is unambiguous for Stories 1.6+ — the DAG is the
  contract.
- Manual sync between `scripts/check_module_boundaries.py` `MODULE_DEPS` and
  Architecture §1052–§1112 is required when either changes — ADR-012 mandates
  updating both in the same PR.
- Rules #1, #2, #4-partial stay code-review-only (runtime-semantics rules not
  expressible at import-graph level).

### Two documented widenings vs. Architecture (Story 1.4 review findings)

1. **`adopt → cli` widening**: Architecture §1069 says `adopt/` sub-imports only
   `cli/git` (sub-module precision). The `MODULE_DEPS` literal allows `adopt → cli`
   at module-level. Real enforcement that `adopt/` only touches `cli.git` lives at
   code review. This widening is intentional and recorded here.
2. **`dashboard/` read-only widening**: The validator allows `dashboard` to import
   `state` and `journal` modules generally; preventing write-path imports
   (`state.atomic`, `journal.writer`) is a code-review discipline for v0.2. Encoding
   sub-module write-path exclusions statically requires a more granular import-graph
   model deferred to a future story.

### Provisional entries added during Story 1.4 review (D5 patch)

- **`agents`**: provisional `MODULE_DEPS` entry added for the future `src/sdlc/agents/`
  tree (Story 2A-1+). Currently empty; boundary rules are placeholders.
- **`scripts`**: meta-tooling in `scripts/` is added to the ruff `src` list and
  boundary-validator scope; not a `src/sdlc/` module, but subject to the same lint
  discipline.

## Revisit-by

2027-05-01 — or when Story 2A-2 (specialist registry) lands and the `agents` provisional
`MODULE_DEPS` entry needs revision, or when the first sub-module-level boundary
(e.g. `dashboard` read-only-vs-write) is encoded statically, whichever first.
