# Graph Report - .  (2026-05-08)

## Corpus Check
- 101 files · ~207,114 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 875 nodes · 1258 edges · 67 communities (52 shown, 15 thin omitted)
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 363 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_ID Type System|ID Type System]]
- [[_COMMUNITY_Architecture Decision Records|Architecture Decision Records]]
- [[_COMMUNITY_Journal Wire Format|Journal Wire Format]]
- [[_COMMUNITY_Concurrency and File Locking|Concurrency and File Locking]]
- [[_COMMUNITY_Boundary Validator Tests|Boundary Validator Tests]]
- [[_COMMUNITY_WorkflowSpec Contract Tests|WorkflowSpec Contract Tests]]
- [[_COMMUNITY_Resume Token Contract|Resume Token Contract]]
- [[_COMMUNITY_Error Type Hierarchy|Error Type Hierarchy]]
- [[_COMMUNITY_Specialist Frontmatter Contract|Specialist Frontmatter Contract]]
- [[_COMMUNITY_Hook Payload Contract|Hook Payload Contract]]
- [[_COMMUNITY_Project Config Module|Project Config Module]]
- [[_COMMUNITY_Secret Redaction Tests|Secret Redaction Tests]]
- [[_COMMUNITY_Module Boundary Enforcement|Module Boundary Enforcement]]
- [[_COMMUNITY_Boundary Integration Tests|Boundary Integration Tests]]
- [[_COMMUNITY_FileLock Implementation|FileLock Implementation]]
- [[_COMMUNITY_ADR Cross-References|ADR Cross-References]]
- [[_COMMUNITY_Secret Detection Script|Secret Detection Script]]
- [[_COMMUNITY_Boundary Validator Internals|Boundary Validator Internals]]
- [[_COMMUNITY_Exit Code Mapping|Exit Code Mapping]]
- [[_COMMUNITY_TOML Customization Resolver|TOML Customization Resolver]]
- [[_COMMUNITY_TOML Config Resolver|TOML Config Resolver]]
- [[_COMMUNITY_Contracts Package Tests|Contracts Package Tests]]
- [[_COMMUNITY_Module Dependency Spec|Module Dependency Spec]]
- [[_COMMUNITY_Config Integration Cluster|Config Integration Cluster]]
- [[_COMMUNITY_Canonical Byte Patterns|Canonical Byte Patterns]]
- [[_COMMUNITY_Config Resolver Functions|Config Resolver Functions]]
- [[_COMMUNITY_Boundary Test Infrastructure|Boundary Test Infrastructure]]
- [[_COMMUNITY_Five-Wire Contract Set|Five-Wire Contract Set]]
- [[_COMMUNITY_16-Module Architecture|16-Module Architecture]]
- [[_COMMUNITY_Secret Scanner Core|Secret Scanner Core]]
- [[_COMMUNITY_BMAD Module Configurations|BMAD Module Configurations]]
- [[_COMMUNITY_BMAD Framework Manifest|BMAD Framework Manifest]]
- [[_COMMUNITY_IDs Public API|IDs Public API]]
- [[_COMMUNITY_Error Coverage Tests|Error Coverage Tests]]
- [[_COMMUNITY_Secret Suppression Logic|Secret Suppression Logic]]
- [[_COMMUNITY_Specialist Validator|Specialist Validator]]
- [[_COMMUNITY_Hook Payload Happy Path|Hook Payload Happy Path]]
- [[_COMMUNITY_Ops Dashboard Prototype|Ops Dashboard Prototype]]
- [[_COMMUNITY_Test Configuration|Test Configuration]]
- [[_COMMUNITY_Package Version API|Package Version API]]
- [[_COMMUNITY_ID Roundtrip Tests|ID Roundtrip Tests]]
- [[_COMMUNITY_ID Parser Failure Tests|ID Parser Failure Tests]]
- [[_COMMUNITY_TEA Workflow Architecture|TEA Workflow Architecture]]
- [[_COMMUNITY_Specialist Validator Stub|Specialist Validator Stub]]
- [[_COMMUNITY_Package Version|Package Version]]
- [[_COMMUNITY_JournalEntry Happy Path|JournalEntry Happy Path]]
- [[_COMMUNITY_ResumeToken Happy Path|ResumeToken Happy Path]]
- [[_COMMUNITY_SpecialistFrontmatter Happy Path|SpecialistFrontmatter Happy Path]]
- [[_COMMUNITY_SpecialistFrontmatter Constraints|SpecialistFrontmatter Constraints]]
- [[_COMMUNITY_WorkflowSpec Happy Path|WorkflowSpec Happy Path]]
- [[_COMMUNITY_ID Builder Happy Path|ID Builder Happy Path]]

## God Nodes (most connected - your core abstractions)
1. `JournalEntry` - 42 edges
2. `WorkflowSpec` - 35 edges
3. `ResumeToken` - 34 edges
4. `SpecialistFrontmatter` - 34 edges
5. `HookPayload` - 33 edges
6. `TestProjectConfig` - 24 edges
7. `read_env()` - 22 edges
8. `SdlcError` - 22 edges
9. `load_project_config()` - 21 edges
10. `TestSanitizeMapping` - 18 edges

## Surprising Connections (you probably didn't know these)
- `test_dispatch_many_caps_concurrency()` --calls--> `BoundedDispatcher`  [INFERRED]
  tests/unit/concurrency/test_subprocess_pool.py → src/sdlc/concurrency/subprocess_pool.py
- `test_dispatch_many_returns_in_input_order()` --calls--> `BoundedDispatcher`  [INFERRED]
  tests/unit/concurrency/test_subprocess_pool.py → src/sdlc/concurrency/subprocess_pool.py
- `test_dispatch_many_empty_iterable_returns_empty_list()` --calls--> `BoundedDispatcher`  [INFERRED]
  tests/unit/concurrency/test_subprocess_pool.py → src/sdlc/concurrency/subprocess_pool.py
- `test_current_in_flight_zero_at_rest()` --calls--> `BoundedDispatcher`  [INFERRED]
  tests/unit/concurrency/test_subprocess_pool.py → src/sdlc/concurrency/subprocess_pool.py
- `test_construction_rejects_zero_or_negative_size()` --calls--> `BoundedDispatcher`  [INFERRED]
  tests/unit/concurrency/test_subprocess_pool.py → src/sdlc/concurrency/subprocess_pool.py

## Hyperedges (group relationships)
- **Five Wire-Format Pydantic Contracts (Story 1.7)** — contracts_JournalEntry, contracts_ResumeToken, contracts_HookPayload, contracts_SpecialistFrontmatter, contracts_WorkflowSpec [EXTRACTED 1.00]
- **Module Boundary + LOC Cap Enforcement (ADR-010, Story 1.4)** — check_module_boundaries_MODULE_DEPS, check_module_boundaries_check_imports, check_module_boundaries_check_loc_cap, check_module_boundaries_layered_dag [EXTRACTED 1.00]
- **Hierarchical ID Builder-Parser Pair (EpicId/StoryId/TaskId)** — ids_EpicId, ids_StoryId, ids_TaskId [EXTRACTED 1.00]
- **Module Boundary Enforcement: script + unit tests + integration tests** — check_module_boundaries_script, test_check_module_boundaries, test_module_boundaries_main [EXTRACTED 1.00]
- **Secret Redaction Chain: sanitize_mapping + SdlcError.to_envelope + integration test** — sdlc_config_sanitize, sdlc_errors_sdlcerror, test_secret_hygiene [EXTRACTED 1.00]
- **IDs Roundtrip: builders + parsers + property tests** — ids_builders, ids_parsers, test_ids_roundtrip [EXTRACTED 1.00]
- **Five-Wire Format Contracts Test Suite** — test_hook_payload_TestHookPayloadHappyPath, test_journal_entry_TestJournalEntryHappyPath, test_resume_token_TestResumeTokenHappyPath, test_specialist_frontmatter_TestSpecialistFrontmatterHappyPath, test_workflow_spec_TestWorkflowSpecHappyPath [INFERRED 0.95]
- **Canonical Byte Stability and JSON Roundtrip Invariant** — canonical_byte_stability_pattern, test_hook_payload_TestHookPayloadCanonical, test_journal_entry_TestJournalEntryCanonical, test_resume_token_TestResumeTokenHappyPath [INFERRED 0.85]
- **BMad TOML Merge Scripts - Config and Customization Resolution** — resolve_config_main, resolve_customization_main, resolve_config_deep_merge, resolve_customization_deep_merge [INFERRED 0.85]
- **CI Quality Gate Pipeline: ruff + mypy + pytest enforced across all ADRs** — adr002_ruff_config, adr003_mypy_strict, adr004_pytest_config, adr006_ci_yml [EXTRACTED 1.00]
- **Pre-commit Hook Chain: ruff + mypy + boundary-validator + specialist-validator** — adr010_pre_commit_config, adr002_ruff_config, adr012_module_layout [EXTRACTED 1.00]
- **Graceful Skip / Honest Signal Pattern Applied Across E2E and Docs Workflows** — rationale_honest_signal_principle, adr007_e2e_yml, adr009_docs_yml [INFERRED 0.95]
- **Foundation Layer Leaf-First Build Order: errors -> ids -> contracts -> config -> concurrency** — module_errors, module_ids, module_contracts, module_config, module_concurrency [EXTRACTED 0.95]
- **Quality Gate Enforcement Chain: pyproject.toml gates + pre-commit hooks + CI matrix** — story_1_2_quality_gates, story_1_3_cicd, story_1_4_precommit [EXTRACTED 1.00]
- **Wire-Format Immutability: frozen=True + Literal[1] schema_version + extra=forbid across all 5 contracts** — contract_journal_entry, contract_resume_token, contract_hook_payload, contract_specialist_frontmatter, contract_workflow_spec [EXTRACTED 1.00]

## Communities (67 total, 15 thin omitted)

### Community 0 - "ID Type System"
Cohesion: 0.06
Nodes (64): build_epic_id(), build_story_id(), build_task_id(), _check_int(), EpicId, parse_epic_id(), parse_story_id(), parse_task_id() (+56 more)

### Community 1 - "Architecture Decision Records"
Cohesion: 0.05
Nodes (62): ADR-001 â€” pyproject Metadata, ADR-002 â€” Ruff Configuration, ADR-003 â€” mypy --strict Mode, ADR-004 â€” pytest/coverage Configuration, ADR-006 â€” ci.yml Design, ADR-010 â€” Pre-commit Configuration, ADR-011 â€” MkDocs Setup, ADR-012 â€” Module Layout (+54 more)

### Community 2 - "Journal Wire Format"
Cohesion: 0.08
Nodes (13): JournalEntry, Wire-format contract: append-only journal record (Architecture §595-§606, Decisi, _canonicalize(), test_missing_required_field_raises(), TestJournalEntryCanonical, TestJournalEntryEqualityAndHash, TestJournalEntryExtraField, TestJournalEntryFieldConstraints (+5 more)

### Community 3 - "Concurrency and File Locking"
Cohesion: 0.07
Nodes (24): _FileLock Sync+Async Context Manager, file_lock(), lock_registry(), POSIX-Only flock Design Decision, Per-file flock context manager — POSIX-only (see Architecture §573).  Async path, Return a per-file exclusive lock context manager for *path*., Return a read-only snapshot of currently-held (path → fd) pairs., BoundedDispatcher Semaphore-Backed Dispatcher (+16 more)

### Community 4 - "Boundary Validator Tests"
Cohesion: 0.05
Nodes (14): Unit tests for the boundary-validator core logic in scripts/check_module_boundar, src/sdlc/version.py -> 'version' (P5: don't silently skip flat-file submodules)., `from sdlc import engine, dispatcher` — each name is a submodule target (P2)., `if TYPE_CHECKING:` imports are type-only, not runtime (P14 / PEP 484)., Also handles `if typing.TYPE_CHECKING:` attribute-form (P14)., # NOTE: with SPECIFIC_RULE_MAP, dispatcher→runtime DOES fire because, The historic bypass: `from sdlc import engine` inside state/ must be flagged., Re-run the import-time invariant for visibility (and fail loudly if violated). (+6 more)

### Community 5 - "WorkflowSpec Contract Tests"
Cohesion: 0.09
Nodes (13): _canonicalize(), test_missing_required_field_raises(), TestWorkflowSpecCanonical, TestWorkflowSpecEqualityAndHash, TestWorkflowSpecExtraField, TestWorkflowSpecFieldConstraints, TestWorkflowSpecFrozenAndContainers, TestWorkflowSpecHappyPath (+5 more)

### Community 6 - "Resume Token Contract"
Cohesion: 0.09
Nodes (13): Wire-format contract: resume-from-checkpoint token (Architecture §608-§613)., ResumeToken, _canonicalize(), test_missing_required_field_raises(), TestResumeTokenCanonical, TestResumeTokenEqualityAndHash, TestResumeTokenExtraField, TestResumeTokenFieldConstraints (+5 more)

### Community 7 - "Error Type Hierarchy"
Cohesion: 0.08
Nodes (19): AdoptError, ConfigError, HookError, IdsError, JournalError, Root exception for the SDLC framework (Architecture §529)., SchemaError, SdlcError (+11 more)

### Community 8 - "Specialist Frontmatter Contract"
Cohesion: 0.1
Nodes (13): Wire-format contract: specialist YAML frontmatter (Architecture §623-§632)., SpecialistFrontmatter, _canonicalize(), test_missing_required_field_raises(), TestSpecialistFrontmatterCanonical, TestSpecialistFrontmatterEqualityAndHash, TestSpecialistFrontmatterExtraField, TestSpecialistFrontmatterFieldConstraints (+5 more)

### Community 9 - "Hook Payload Contract"
Cohesion: 0.1
Nodes (13): HookPayload, Wire-format contract: pre-write hook payload (Architecture §615-§621, Decision D, _canonicalize(), test_missing_required_field_raises(), TestHookPayloadCanonical, TestHookPayloadEqualityAndHash, TestHookPayloadExtraField, TestHookPayloadFieldConstraints (+5 more)

### Community 10 - "Project Config Module"
Cohesion: 0.11
Nodes (9): BaseModel, ProjectConfig Pydantic Model, load_project_config(), ProjectConfig, Typed wrapper for project.yaml (FR51).      Schema sources: epics.md:610-613, pr, Load ``project.yaml`` from ``path`` (default: <cwd>/project.yaml).      Behaviou, _wrap_validation_error(), TestProjectConfig (+1 more)

### Community 12 - "Module Boundary Enforcement"
Cohesion: 0.1
Nodes (29): check_imports(), check_loc_cap(), _extract_sdlc_imports(), file_to_module(), _format_forbidden_set(), Import, _import_target_module(), _is_loc_exempt() (+21 more)

### Community 13 - "Boundary Integration Tests"
Cohesion: 0.07
Nodes (17): Integration tests for scripts/check_module_boundaries.py.  Covers check_loc_cap, Absolute path under .../tests/fixtures/ is also exempt (P4)., End-to-end: relative import inside a src/sdlc/<module>/ file fires §1075., End-to-end check that `from sdlc import engine` no longer bypasses (P2)., The validator must pass when run over its own source (AC3 self-discipline)., Hard guard: validator stays under the cap it enforces., `scripts/validate_specialists.py` is the v0.2 no-op (AC5)., 400 content lines with no trailing newline -> exactly 400 lines (passes). (+9 more)

### Community 14 - "FileLock Implementation"
Cohesion: 0.11
Nodes (13): _FileLock, Unified sync + async per-file exclusive lock (one class, two protocols)., BoundedDispatcher, Asyncio-Semaphore-backed dispatcher capping parallel coroutine execution.      E, Return the number of coroutines currently executing under the semaphore., Run *coros* with at most `semaphore_size` executing concurrently.          Retur, test_construction_rejects_zero_or_negative_size(), test_current_in_flight_zero_at_rest() (+5 more)

### Community 15 - "ADR Cross-References"
Cohesion: 0.11
Nodes (28): ADR-001: pyproject Metadata, ADR-002: Ruff Linting + Formatting Configuration, ADR-003: Mypy Strict Type Checking Configuration, ADR-004: Pytest and Coverage Configuration, ADR-005: package_data Layout, ADR-006: CI Workflow (ci.yml) â€” Python x OS Matrix Quality Gates, ADR-007: E2E Workflow (e2e.yml) â€” Nightly Real-Claude Suite, ADR-008: Release Workflow (release.yml) â€” Wheel-Only PyPI Trusted Publishing (+20 more)

### Community 16 - "Secret Detection Script"
Cohesion: 0.11
Nodes (8): noqa:secret Escape Hatch Pattern, _scan_file Function, ENV_PREFIX_ALLOWLIST / ENV_EXACT_ALLOWLIST, Env Var Allow-List Security Design, _is_allowed(), Return the env-var value if ``name`` matches the allow-list, else raise ConfigEr, read_env(), TestReadEnv

### Community 17 - "Boundary Validator Internals"
Cohesion: 0.08
Nodes (4): TestExpandTargets, TestIsExempt, TestMain, TestScanFile

### Community 18 - "Exit Code Mapping"
Cohesion: 0.12
Nodes (20): AdoptError (ERR_ADOPT), EXIT_CODE_MAP Error-to-ExitCode Table, HookError (ERR_HOOK), IdsError (ERR_IDS), JournalError (ERR_JOURNAL), SchemaError (ERR_SCHEMA), SdlcError Root Exception, SignoffError (ERR_SIGNOFF) (+12 more)

### Community 19 - "TOML Customization Resolver"
Cohesion: 0.27
Nodes (11): deep_merge(), _detect_keyed_merge_field(), extract_key(), find_project_root(), load_toml(), main(), _merge_arrays(), _merge_by_key() (+3 more)

### Community 20 - "TOML Config Resolver"
Cohesion: 0.2
Nodes (11): deep_merge - Recursive Config Merger, _detect_keyed_merge_field - Key Detection, Four-Layer TOML Config Merge Strategy, load_toml - TOML File Loader, resolve_config.py - Four-Layer TOML Config Resolver, _merge_by_key - Keyed Array Merger, deep_merge - Skill Customization Merger, find_project_root - Project Root Discovery (+3 more)

### Community 21 - "Contracts Package Tests"
Cohesion: 0.2
Nodes (4): TestContractsPackageNamespace, Decision F3: schema_version independence per contract, sdlc.contracts (JournalEntry, ResumeToken, HookPayload, SpecialistFrontmatter, WorkflowSpec), Unit Tests: contract schema_version independence (Decision F3)

### Community 22 - "Module Dependency Spec"
Cohesion: 0.25
Nodes (9): MODULE_DEPS Dependency Table, ModuleSpec Dataclass, SPECIFIC_RULE_MAP Â§1103 Rules, check_imports Function, check_loc_cap Function, _extract_sdlc_imports AST Walker, file_to_module Helper, Layered DAG Architecture Constraint (+1 more)

### Community 23 - "Config Integration Cluster"
Cohesion: 0.31
Nodes (9): sdlc.config.ProjectConfig + load_project_config, sdlc.config.read_env (ENV_PREFIX_ALLOWLIST, ENV_EXACT_ALLOWLIST), sdlc.config.sanitize_mapping (secret redaction utility), ConfigError (config validation error subtype), SdlcError (base error with to_envelope() and details), Unit Tests: read_env allowlist enforcement (ConfigError), Unit Tests: ProjectConfig / load_project_config (YAML loading, Pydantic), Integration Test: secret redaction via SdlcError + sanitize_mapping (+1 more)

### Community 24 - "Canonical Byte Patterns"
Cohesion: 0.22
Nodes (9): Canonical Byte Stability Pattern, MappingProxy Immutability Pattern, Schema Version Strict Integer Validation Pattern, TestHookPayloadCanonical - Canonical Byte Stability, TestHookPayloadSchemaVersionRejection, TestJournalEntryCanonical, TestJournalEntryFrozenAndContainers, TestResumeTokenFrozenAndContainers (+1 more)

### Community 25 - "Config Resolver Functions"
Cohesion: 0.46
Nodes (7): deep_merge(), _detect_keyed_merge_field(), extract_key(), load_toml(), main(), _merge_arrays(), _merge_by_key()

### Community 26 - "Boundary Test Infrastructure"
Cohesion: 0.39
Nodes (8): check_module_boundaries.py script (MODULE_DEPS, check_imports, main), Tests conftest.py (sys.path injection for scripts/), LOC Cap Rule (400-line limit, Architecture Â§765), MODULE_DEPS DAG table (17-module dependency/forbidden spec), Architecture Â§1103 Boundary Rules (#1-#8), Unit Tests for check_module_boundaries core logic, Integration Tests for check_module_boundaries main() / LOC cap, validate_specialists.py placeholder script (v0.2 no-op)

### Community 27 - "Five-Wire Contract Set"
Cohesion: 0.29
Nodes (7): HookPayload Wire Contract, JournalEntry Wire Contract, ResumeToken Wire Contract, SpecialistFrontmatter Wire Contract, WorkflowSpec Wire Contract, Five-Wire Format Pydantic Contracts, Specialist Cross-Ref Validation Pipeline

### Community 28 - "16-Module Architecture"
Cohesion: 0.43
Nodes (7): 16-Module Dependency DAG, Eight Specific Module Boundary Rules, TRIZ-Style Determinism Contradiction, Architecture Overview - 16-Module DAG, Documentation Index, MkDocs Documentation Site Config, SDLC-Framework README

### Community 29 - "Secret Scanner Core"
Cohesion: 0.7
Nodes (4): _expand_targets(), _is_exempt(), main(), _scan_file()

### Community 30 - "BMAD Module Configurations"
Cohesion: 0.7
Nodes (5): BMAD BMB Module Configuration, BMAD BMM Module Configuration, BMAD CIS Module Configuration, BMAD Core Module Configuration, BMAD Version 6.6.0 Framework as Planning and Agent Generation System

### Community 31 - "BMAD Framework Manifest"
Cohesion: 0.4
Nodes (5): BMAD Module Manifest, BMAD Builder Module v1.7.0, BMAD Core Module v6.6.0, BMAD TEA Module v1.15.1, TEA Module Configuration

### Community 32 - "IDs Public API"
Cohesion: 0.83
Nodes (4): sdlc.ids.builders (build_epic_id, build_story_id, build_task_id), sdlc.ids Public API (__init__), sdlc.ids.parsers (EpicId, StoryId, TaskId + parse_* + regex constants), Property Tests: IDs build/parse roundtrip (Hypothesis)

### Community 33 - "Error Coverage Tests"
Cohesion: 0.5
Nodes (4): EXIT_CODE_MAP Coverage Tests, SdlcError Unit Tests, to_envelope Shape and JSON Serialization Tests, Builder Invalid Input Tests

### Community 34 - "Secret Suppression Logic"
Cohesion: 0.5
Nodes (4): noqa Secret Suppression Justification Pattern, TestIsExempt - Exemption Logic, TestMain - Secret Guard Entry Point, TestScanFile - Secret Detection

### Community 36 - "Hook Payload Happy Path"
Cohesion: 0.67
Nodes (3): sdlc.contracts Package Namespace, TestHookPayloadHappyPath, TestContractsPackageNamespace

### Community 37 - "Ops Dashboard Prototype"
Cohesion: 0.67
Nodes (3): Dashboard Prototype HTML (Editorial Ops Console), Dashboard Prototype README, Dark Editorial Register Design System for Ops Console Dashboard

## Knowledge Gaps
- **154 isolated node(s):** `ModuleSpec`, `Module boundary + LOC cap enforcement for src/sdlc/ (ADR-010, Story 1.4).  Encod`, `Module-level invariant: every value in any depends_on / forbidden_from is a`, `Return module name for paths under src/sdlc/<module>/...; None otherwise.`, `True if `node` is `if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:`.` (+149 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_project_config()` connect `Project Config Module` to `Secret Detection Script`, `Error Type Hierarchy`?**
  _High betweenness centrality (0.154) - this node is a cross-community bridge._
- **Why does `ConfigError` connect `Error Type Hierarchy` to `Secret Detection Script`, `Project Config Module`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `JournalEntry` (e.g. with `TestJournalEntryHappyPath` and `TestJournalEntrySchemaVersionRejection`) actually correct?**
  _`JournalEntry` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 32 inferred relationships involving `WorkflowSpec` (e.g. with `TestWorkflowSpecHappyPath` and `TestWorkflowSpecSchemaVersionRejection`) actually correct?**
  _`WorkflowSpec` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `ResumeToken` (e.g. with `TestResumeTokenHappyPath` and `TestResumeTokenSchemaVersionRejection`) actually correct?**
  _`ResumeToken` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `SpecialistFrontmatter` (e.g. with `TestSpecialistFrontmatterHappyPath` and `TestSpecialistFrontmatterSchemaVersionRejection`) actually correct?**
  _`SpecialistFrontmatter` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `HookPayload` (e.g. with `TestHookPayloadHappyPath` and `TestHookPayloadSchemaVersionRejection`) actually correct?**
  _`HookPayload` has 30 INFERRED edges - model-reasoned connections that need verification._