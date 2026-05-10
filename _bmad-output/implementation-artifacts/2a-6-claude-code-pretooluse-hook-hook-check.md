# Story 2A.6: Claude Code PreToolUse Hook + `sdlc hook-check`

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer ensuring engine-side hooks and Claude-Code-side hooks enforce identical rules (Decision D2),
I want a `claude_hooks/pre_tool_use.py` that shells out to `sdlc hook-check <payload-json>` for parity, sharing the unified `HookPayload` v1 wire-format contract, AND I want the engine pre-write site (`dispatcher.core`) wired to `run_hook_chain` so the same `naming_validator + phase_gate` chain that 2A.4 ships is enforced at every artifact write,
So that Claude Code's PreToolUse hook blocks the same Write/Edit calls the engine would block (FR40, Decision D2), and the engine-side hook chain is no longer dead code (Story 2A.4's AC7 wiring debt closes here).

## Acceptance Criteria

> Source ACs: `_bmad-output/planning-artifacts/epics.md:1115-1137`. Per ADR-026 §1, the public CLI surface (`sdlc hook-check`), the public Python entry point of the Claude-side hook (`claude_hooks/pre_tool_use.py:main`), AND the dispatcher pre-write integration site (`dispatcher.core._run_member` pre-write call) all require TDD-first commit ordering visible in `git log --reverse`. The `HookPayload` contract is **already frozen at v1** per ADR-024 — this story REUSES the contract; it does NOT mutate it.

### AC1 — `HookPayload` is reused unchanged from `src/sdlc/contracts/hook_payload.py` (frozen v1)

**Given** the existing wire-format contract at `src/sdlc/contracts/hook_payload.py` defines `HookPayload(schema_version=1, hook_name: str, target_path: str, target_kind: str, content_hash_before: str | None, write_intent: str)` with strict pydantic validation (Story 1.7 + Story 1.21 lock; Story 2A.4 AC1 reaffirmed)
**When** the dev introduces the `sdlc hook-check` CLI command + the Claude-side `pre_tool_use.py`
**Then** every payload constructed on either side MUST go through `sdlc.hooks.payload` (the re-export site introduced in 2A.4 AC8; never imports `contracts/` directly from `claude_hooks/`)
**And** `tests/contract_snapshots/v1/hook_payload.json` MUST remain byte-identical
**And** `python scripts/freeze_wireformat_snapshots.py --check` reports `5 contracts match snapshots`
**And** the JSON-on-the-wire shape exchanged between Claude-side `pre_tool_use.py` and `sdlc hook-check` is the canonical `HookPayload.model_dump_json(by_alias=False)` output (sorted keys via `model_dump(...)` + `json.dumps(..., sort_keys=True, separators=(",", ":"))` for byte-stable round-trip across stdin/stdout)
**And** the wire-direction is unidirectional: Claude-side serialises payload → CLI subcommand reads from stdin (NOT argv — Windows argv length limits + JSON shell-escaping fragility per Story 2A.0 P26 lessons) → CLI subcommand writes the response envelope to stdout

### AC2 — `sdlc hook-check` CLI subcommand (engine-side parity oracle)

**Given** the engine-side hook runner from Story 2A.4 (`run_hook_chain` + builtin `naming_validator` + `phase_gate`) plus the registry loader from `sdlc.config.hooks.load_hook_registry`
**When** the dev runs `echo '<payload-json>' | sdlc hook-check` (NB: stdin form is canonical) OR (legacy fallback) `sdlc hook-check '<payload-json>'`
**Then** the command:
  1. Resolves repo root via the existing `cli/_paths.get_repo_root_or_cwd()` helper
  2. Reads the JSON payload from stdin (preferred) — falls back to `argv[1]` if stdin is a TTY (i.e., interactive invocation; subprocess piping always uses stdin)
  3. Validates the payload via `HookPayload.model_validate_json(...)`; on `pydantic.ValidationError` → exits with `[ERROR] invalid HookPayload: <validation summary>` to stderr and `--json` envelope `{"decision": "deny", "reason": "...", "error_code": "invalid_payload"}` to stdout, exit code 2 (`HookError.exit_code` per `errors/base.py:18`)
  4. Loads the hook registry via `load_hook_registry(repo_root / "pyproject.toml")` and resolves each registered hook name to its callable (lookup table at `sdlc.hooks.builtin` per Story 2A.4 AC2)
  5. Calls `await run_hook_chain(payload, hooks=resolved_hooks, journal_path=repo_root / ".claude/state/journal.log")` — the engine-side journal IS appended for the Claude-side parity invocation (so `sdlc trace --kind=hook_rejected` surfaces both engine + Claude rejections in one stream — see AC11 D-decision)
  6. Emits to stdout the canonical response envelope:
     ```json
     {"decision": "allow", "hook_name": null, "reason": null, "error_code": null}
     {"decision": "deny",  "hook_name": "phase_gate", "reason": "phase-gate violation: ...", "error_code": "phase_gate_violation"}
     ```
  7. Exits 0 on `decision="allow"`, exit code 1 on `decision="deny"` (Claude Code interprets non-zero PreToolUse exit codes as block — see Anthropic Claude Code hook docs); exit code 2 on internal CLI error (invalid payload, registry corrupt, etc.)
**And** the command supports the existing `--json` global flag (Architecture §674-§680) — but in this case the JSON envelope is the DEFAULT shape (the command is machine-only by design); `--json` is a no-op (accepts the flag for consistency, never errors). Human-readable mode does NOT exist for this subcommand
**And** the command lives at `src/sdlc/cli/hook_check.py` (Architecture §796 mandates this filename)
**And** the command is wired into the Typer app at `src/sdlc/cli/main.py` (mirror Story 2A.5's `trust_hooks` wiring shape)
**And** for the `--force-bypass-signoff` parameter — `sdlc hook-check` does NOT accept this flag in v1: bypass is ALWAYS user-initiated from a human-driven CLI command, and Claude Code's PreToolUse hook never has bypass authority (it can only mirror what the engine would decide). If a future v1.x adds Claude-bypass it goes via a separate flag — out of scope here. Document this rule in the module docstring

### AC3 — Claude-side `pre_tool_use.py` hook (FR40)

**Given** Claude Code's PreToolUse hook protocol: a Python script that reads JSON from stdin (the tool-use request), prints JSON on stdout (the decision), exits 0 = allow, exit non-zero = block (per Anthropic Claude Code hook docs)
**When** the dev installs the hook
**Then** `src/sdlc/claude_hooks/pre_tool_use.py`:
  1. Reads the Claude-Code tool-use envelope from stdin (shape: `{"tool_name": "Write|Edit", "tool_input": {"file_path": "...", "content": "..."}}` — see AC4 for the field-extraction rules)
  2. Filters by `tool_name`: only `Write` and `Edit` invoke the hook chain; for `Read`, `Bash`, `Grep`, etc. → emit `{"decision": "allow"}` and exit 0 immediately (no engine round-trip; performance budget per AC7)
  3. Constructs a `HookPayload` via `sdlc.hooks.payload.build_write_intent_payload(...)` (Story 2A.4 AC1 helper) using:
     - `target_path = tool_input["file_path"]` (Claude-Code-side; resolved relative to repo root if absolute, see AC4)
     - `content_hash_before = sha256(open(target_path, "rb").read())` IF the file exists, else `None`
     - `write_intent = f"claude_pretooluse_{tool_name.lower()}"` (e.g., `"claude_pretooluse_write"`, `"claude_pretooluse_edit"`)
     - `target_kind = "write_intent"` (matches Story 2A.4 AC1 vocabulary)
  4. Serialises the payload to canonical JSON and shells out: `subprocess.run(["sdlc", "hook-check"], input=payload_json_bytes, capture_output=True, timeout=<AC7 budget>)`
  5. Parses the response envelope from stdout; emits the Claude-Code-side response envelope (the `decision` field is named differently on Claude side per AC4) and exits 0 (allow) or 1 (deny) accordingly
**And** the Claude-side hook does NOT import `sdlc.hooks.runner` or `sdlc.hooks.builtin` — the boundary is HARD: Claude-side speaks ONLY through the `sdlc hook-check` subprocess. This keeps the Claude-side hook installable into Claude Code without dragging the entire `sdlc` package into Claude Code's PreToolUse hook runtime path (cold-start budget) and avoids Decision D2's risk of two Python processes co-importing the same module
**And** the Claude-side hook MAY import `sdlc.contracts.hook_payload` ONLY for type checking (`if TYPE_CHECKING:`) — at runtime it constructs the payload as a `dict` and passes it to `sdlc.hooks.payload.build_write_intent_payload(...)` IF the bundled `sdlc` package is importable, OR falls back to a stdlib-only payload construction (a pure `dict` passed through `json.dumps`) IF it is not (some Claude Code installations may not have `sdlc` on `sys.path` — defensive fallback)
**And** the Claude-side hook script is self-contained (NO sibling helpers in `claude_hooks/`) — Story 2A.6 ships ONE file at `claude_hooks/pre_tool_use.py`. `post_write_journal.py` and `post_write_state_refresh.py` (Architecture §973-§974) are out of scope here (Epic 2B / future story)

### AC4 — Claude-Code envelope shape + path resolution

**Given** Claude Code's published PreToolUse hook envelope shape (verified via WebFetch from Anthropic docs at story-time; cite the version observed in the PR Change Log)
**When** the hook constructs its `HookPayload`
**Then** the input envelope shape recognised is:
  ```json
  {
    "tool_name": "Write" | "Edit" | "MultiEdit" | "...",
    "tool_input": {
      "file_path": "<absolute or repo-relative>",
      "content": "<...>",
      "old_string": "<...>",     // Edit / MultiEdit only
      "new_string": "<...>"      // Edit / MultiEdit only
    },
    "session_id": "...",          // optional; ignored by 2A.6
    "transcript_path": "...",     // optional; ignored by 2A.6
    "cwd": "<absolute path>"      // present in current Claude Code; used as repo-root anchor when present
  }
  ```
**And** the recognised tool names that trigger the hook chain: `Write`, `Edit`, `MultiEdit`. ALL other tool names → fast-path allow (do NOT round-trip the engine for `Bash`, `Read`, `Grep`, etc.)
**And** `target_path` resolution rules:
  1. If `tool_input["file_path"]` is absolute AND under `envelope["cwd"]` (or under `os.getcwd()` if `cwd` absent) → relativize to that root → use the POSIX-style relative path
  2. If absolute AND NOT under the resolved root → emit `{"decision": "deny", "reason": "tool_input.file_path '<abs>' is outside repo root '<root>'", "error_code": "path_outside_repo"}` and exit 1 (defense-in-depth — prevents Claude Code from being tricked into writing outside the repo via traversal payloads)
  3. If relative → join to the resolved root, then relativize back via `pathlib.PurePosixPath` for byte-stable cross-platform path strings
**And** the output envelope shape emitted to Claude Code is:
  ```json
  // ALLOW (exit 0)
  {"decision": "approve", "reason": null}
  // DENY (exit 1)  — IMPORTANT: Claude-Code's deny key is "block", NOT "deny" (verify field name with WebFetch at story-time; this story standardises on "block" pending verification)
  {"decision": "block", "reason": "<engine-side reason>", "error_code": "<engine-side error_code>"}
  ```
**And** the field-name discrepancy between Claude-Code's allow/deny verbs (`approve`/`block`) and the engine's `HookDecision` verbs (`allow`/`deny`) is bridged in `pre_tool_use.py:_to_claude_envelope(...)` — a pure 4-line translation function with a unit test asserting both directions
**And** if Claude Code's envelope shape changes between the time of authoring and the time of installation (the docs URL is observed at story-time; field names may drift), the hook prints `[WARN] unrecognised Claude Code envelope schema: <missing-field>; falling back to stdlib JSON` to stderr and emits `{"decision": "approve"}` (fail-OPEN — see AC9 for the explicit rationale and the deferred-work entry)

### AC5 — Parity test fixture (CI gate, FR40)

**Given** a parity test fixture at `tests/parity/test_engine_vs_claude_hooks.py` with at least 20 attempted-write scenarios
**When** the parity suite runs
**Then** for every fixture row, BOTH layers (engine-side `run_hook_chain` + Claude-side `pre_tool_use.py` shelling to `sdlc hook-check`) return the SAME decision (allow/deny + same `error_code`)
**And** the 20 scenarios cover (matrix product gives ≥ 20):
  - `naming_validator` axis: valid epic id, invalid epic id (`EPC_typo.json`), valid story id, story id under wrong-shape epic dir, valid task id, task id under malformed-grandparent dir (5 cases)
  - `phase_gate` axis: phase-1 path always-allow, phase-2 path missing-signoff (deny), phase-2 path approved-true (allow), phase-2 path approved-false (deny), phase-3 path missing-phase-2-signoff (deny), phase-3 path approved (allow), non-phase path (`.claude/`, `_bmad-output/`) always-allow (7 cases)
  - `target_path` shape axis: absolute under cwd (resolved), absolute outside repo (denied with `path_outside_repo`), relative, Windows-style separators round-trip via `PurePosixPath` (4 cases)
  - Tool-name axis: `Write` (chain runs), `Edit` (chain runs), `MultiEdit` (chain runs), `Read` (fast-path allow), `Bash` (fast-path allow) (5 cases — fast-path 2 of which are pure shortcut tests)
**And** the parity test runs in CI as a NEW gate; failing fixtures BLOCK the PR (matches Story 2A.4 AC10 / Story 2A.0's quality gate)
**And** the fixture rows are stored as YAML at `tests/parity/fixtures/hook_parity_v1.yaml` for human-readable maintenance — each row is a `{name, payload, expected_decision, expected_error_code, repo_setup_steps}` dict
**And** a fixture-coverage assertion in the same test file fails if fewer than 20 scenarios are loaded — prevents accidental fixture-deletion regression
**And** the parity test ships with a `pytest.mark.parity` marker so `pytest -m parity` runs ONLY this gate (CI may invoke it as a separate step parallel to `-m "not e2e"`)

### AC6 — Engine pre-write wiring (closes Story 2A.4 AC7 debt)

**Given** Story 2A.4 AC7 explicitly defers wiring `dispatcher.core` → `run_hook_chain` to Story 2A.6, AND Story 2A.4's `tests/integration/test_hook_chain_smoke.py` mocks the dispatcher-shaped caller
**When** the dev wires the engine-side
**Then** `src/sdlc/dispatcher/core.py` (Story 2A.3) is updated:
  1. The pre-write site (the call site that writes a specialist's `output_text` to its declared write target) calls `await run_hook_chain(payload, hooks=resolved_hooks, journal_path=...)` BEFORE the actual file write
  2. On `decision="deny"` → the dispatcher does NOT write the file; the deny is the `_run_member` outcome; the existing `kind="dispatch_attempt"` journal entry from 2A.3 is augmented with `outcome="hook_rejected"` (the existing payload schema permits this — `kind="dispatch_attempt"` payload has an `outcome` field per 2A.3 AC4); the `kind="hook_rejected"` journal entry from `run_hook_chain` has ALREADY been appended by the runner — no duplicate journaling
  3. On `decision="allow"` → the dispatcher proceeds with the existing atomic-write protocol from Story 1.10
  4. The hook chain is loaded ONCE at dispatcher construction (via `load_hook_registry(...)` from Story 2A.4 AC2) and cached as a tuple; per-dispatch lookup is a single attribute read
**And** the `run_hook_chain` call passes `bypass_phase_gate=False, justification=None` BY DEFAULT — bypass is propagated from the dispatcher's caller via a new `dispatch(..., bypass: BypassRequest | None = None)` parameter (typed as `Story 2A.4`'s `cli/_bypass.BypassRequest` shape — verify against existing `cli/_bypass.py` API)
**And** `tests/integration/test_hook_chain_smoke.py` (from 2A.4) is REPLACED by `tests/integration/test_dispatcher_hook_integration.py` exercising the REAL dispatcher (no mock); the smoke test's intent is preserved (build payload → run chain → assert allow/deny/journal entry → assert file written or not)
**And** the wiring respects boundary rule §1109 (`hooks/` does NOT import `engine/` or `dispatcher/`) — the dependency direction is `dispatcher/` imports `hooks/` (allowed per Architecture §1067), NOT the reverse
**And** a NEW debt entry `EPIC-2A-DEBT-PRE-EXISTING-HOOK-WAIVERS` is added to `_bmad-output/implementation-artifacts/deferred-work.md` IF, after wiring, ≥ 1 existing pipeline test (`tests/e2e/pipeline/`) starts failing because a fixture's specialist writes to a phase-gated path without a signoff. **Recommended resolution path** (NOT in this story's scope): each failing fixture either (a) gains a `pre_signoff: true` setup step that pre-writes a fake `.claude/state/signoffs/phase-1.yaml` + Phase-2 fakes for the same fixture, OR (b) is moved to a separate `pytest.mark.skip(reason="pre-2A.6 fixture; needs signoff fakery")` quarantine until Story 2A.12 ships the real signoff machinery. Pick a + b based on each fixture's intent

### AC7 — Performance budget (cold-start ≤ 500ms wall-clock per Claude Code call)

**Given** Claude Code's PreToolUse hook runs SYNCHRONOUSLY in the user's interactive flow — every `Write` / `Edit` blocks until the hook returns
**When** the parity test measures end-to-end wall-clock latency: Claude-side hook → subprocess `sdlc hook-check` → return to Claude
**Then** the 95th-percentile wall-clock for the full round-trip MUST be ≤ 500ms on a clean Python interpreter cold-start (the Claude-Code-side script's `import sdlc` is the dominant cost — see Architecture §488-§494 cold-start budget)
**And** the budget is enforced by a NEW `tests/parity/test_hook_check_latency.py` benchmark using `pytest-benchmark` (already pinned via Story 1.18.1's perf gates per ADR-021 — verify before adding a new dep)
**And** the benchmark MUST run in CI but ONLY on the dedicated `parity-perf` job (NOT in the main `pytest -m "not e2e"` run) to avoid noise on dev laptops; the failing condition is `p95 > 500ms` measured over 10 warm runs (after 2 cold-warmup runs)
**And** if `sdlc hook-check` cold-start exceeds 500ms, the response strategy is to use a PYTHONSTARTUP-cached interpreter or to add a `__main__.py`-style fast-path entry — DO NOT pre-load `sdlc.dispatcher` or `sdlc.engine` (boundary rule §1109; `cli/hook_check.py` may import `cli._paths`, `hooks.runner`, `hooks.builtin.{naming_validator,phase_gate}`, `hooks.payload`, `config.hooks`, `errors`, `contracts` ONLY)
**And** for tool-names that fast-path allow (`Read`, `Bash`, `Grep`, etc.) the Claude-side hook MUST exit in < 50ms p95 (no subprocess invocation; pure JSON parse + envelope emit)

### AC8 — Module structure + LOC caps (Architecture §790-§810, §971-§974)

**Given** the existing `src/sdlc/cli/` and `src/sdlc/claude_hooks/` directory layouts
**When** the dev introduces 2A.6
**Then** the new layout is:

```
src/sdlc/cli/                                # EXISTS
├── hook_check.py                            # NEW — sdlc hook-check subcommand (≤ 200 LOC)
└── main.py                                  # UPDATE — wire hook_check into Typer app

src/sdlc/claude_hooks/                       # NEW PACKAGE (currently does not exist on disk;
│                                            #   Architecture §971-§974 reserves the slot)
├── __init__.py                              # NEW — empty package marker (≤ 5 LOC)
└── pre_tool_use.py                          # NEW — Claude PreToolUse hook script (≤ 250 LOC)

src/sdlc/dispatcher/                         # EXISTS
└── core.py                                  # UPDATE — wire run_hook_chain into pre-write site (Story 2A.4 AC7 debt closes)

tests/unit/cli/                              # EXISTS
└── test_hook_check.py                       # NEW — AC2 (≤ 250 LOC)

tests/unit/claude_hooks/                     # NEW
├── __init__.py
├── test_pre_tool_use.py                     # NEW — AC3 (≤ 250 LOC)
└── test_envelope_translation.py             # NEW — AC4 _to_claude_envelope (≤ 80 LOC)

tests/integration/                           # EXISTS
├── test_dispatcher_hook_integration.py      # NEW — AC6 replaces 2A.4's hook_chain_smoke
└── test_hook_check_subprocess.py            # NEW — AC2 + AC3 e2e via real subprocess

tests/parity/                                # NEW DIRECTORY
├── __init__.py
├── conftest.py                              # parity marker registration
├── fixtures/
│   └── hook_parity_v1.yaml                  # NEW — ≥ 20 fixture rows (AC5)
├── test_engine_vs_claude_hooks.py           # NEW — AC5 parity gate
└── test_hook_check_latency.py               # NEW — AC7 latency benchmark
```

**And** every NEW file has a module docstring citing the FR/NFR + ADR + architecture sections it implements (mirror Story 2A.4 + 2A.5 docstring style verbatim)
**And** the LOC caps are enforced via the existing `scripts/check_module_loc.py` (or its equivalent — verify against `pyproject.toml` `[tool.ruff]` settings; if `check_module_loc.py` is absent, document the caps in the PR Change Log per the Story 2A.4 / 2A.5 precedent)
**And** `package_data` in `pyproject.toml` MUST include `claude_hooks/*.py` so the Claude-side hook is shipped in the wheel (Architecture §1218 — `package_data` enumeration; verify `[tool.hatch.build.targets.wheel]` already includes `claude_hooks/` or extend it)

### AC9 — Module boundaries (Architecture §1067, §1109; security defense-in-depth)

**Given** Architecture §1067: `cli/` may import `engine`, `adopt`, `dashboard`, `runtime`, `config`, `errors`. **Forbidden from**: (top of stack — implicitly: nothing imports `cli/` upward)
**And** Architecture §971-§974: `src/sdlc/claude_hooks/` ships INTO the user's `.claude/hooks/` at `sdlc init` time — it is a content tree, NOT a Python module imported by the framework; it MUST NOT import `engine/`, `dispatcher/`, `runtime/`, `state/`, `journal/` at runtime (it speaks ONLY through the `sdlc hook-check` subprocess, AC3 fourth-And)
**When** the dev runs the boundary linter
**Then** `src/sdlc/cli/hook_check.py` imports ONLY: `cli._paths`, `cli.output`, `hooks.runner`, `hooks.builtin.naming_validator`, `hooks.builtin.phase_gate`, `hooks.payload`, `config.hooks`, `contracts.hook_payload`, `errors`, stdlib (`json`, `sys`, `pathlib`)
**And** `src/sdlc/claude_hooks/pre_tool_use.py` imports ONLY: stdlib (`json`, `subprocess`, `sys`, `pathlib`, `hashlib`, `os`, `typing`); pydantic ONLY behind `if TYPE_CHECKING:` (per AC3 fifth-And — defensive fallback to stdlib-only payload construction for installations without `sdlc` on `sys.path`)
**And** `src/sdlc/dispatcher/core.py` MAY import `hooks.runner`, `hooks.payload`, `hooks.builtin.*`, `config.hooks` (Architecture §1067 already permits dispatcher → hooks); the boundary linter `scripts/check_module_boundaries.py` MUST verify `dispatcher.depends_on` includes `"hooks"` and `"config"` — extend the linter if needed (was already extended in 2A.5 AC10 for `cli.depends_on += {"hooks"}`; verify dispatcher row is similarly current)
**And** **fail-open posture rationale (cross-reference for AC4 last-And):** Claude-Code-side fail-open (allow on unrecognised envelope) is ADVISORY-CONSISTENT with the v1 trust posture from PRD §374 + ADR-013 ("v1 advisory only; v1.x graduates to hard-block"). Engine-side enforcement is the authoritative gate; the Claude-side hook is a USABILITY MIRROR (catches the violation BEFORE Claude Code wastes a token quota completing a write the engine will reject). A v1.x story will graduate to fail-CLOSED after a tampering-grace-period; flag this in the deferred-work entry `EPIC-2A-DEBT-CLAUDE-HOOK-FAIL-CLOSED-V1.X`
**And** the linter emits zero new violations after this story's diff

### AC10 — Journal-kind integration (no new contract; reuse Story 2A.3 + 2A.4 kinds)

**Given** the existing journal-kind catalog at `docs/architecture-overview.md#Journal-Kind-Catalog` (Story 2A.4 AC10 + Story 2A.3 D-decision A6 lockdown):
  - `dispatch_attempt` (Story 2A.3) — augmented in 2A.6 to include `outcome="hook_rejected"` per AC6
  - `hook_rejected` (Story 2A.4) — REUSED unchanged; written by `hooks.runner._make_hook_rejected_entry`
  - `bypass_signoff` (Story 2A.4) — REUSED unchanged
**When** the dev considers whether 2A.6 needs a new journal kind for Claude-side rejections specifically
**Then** the answer is NO: a Claude-side rejection IS routed through the engine-side `sdlc hook-check` runner, which appends `kind="hook_rejected"` with `actor="hooks.runner"` (NOT `"claude_hooks.pre_tool_use"`). The Claude-side hook is a CALLER of the engine-side runner; the journal entry is identical regardless of caller
**And** if the operator needs to distinguish Claude-side vs engine-side origins of a rejection (debugging which surface caught the violation first), the discriminator is in the `payload.write_intent` field of the `HookPayload` (`"claude_pretooluse_write"` vs `"dispatcher_artifact_write"`); the journal entry's `payload.reason` MAY include the `write_intent` for fast `sdlc trace --kind=hook_rejected | grep claude_pretooluse` operator queries — this is RECOMMENDED but NOT mandatory
**And** the "Journal Kind Catalog" table in `docs/architecture-overview.md` is UPDATED to mark `hook_rejected` as "callers: hooks.runner (engine-side, dispatcher.core invocation), hooks.runner (Claude-side, sdlc hook-check invocation)" — single owner row, two caller paths
**And** NO contract edit is required (`JournalEntry.kind` is an open `str` per AC10 D-decision A6 lockdown from Story 2A.3 — `tests/contract_snapshots/v1/journal_entry.json` MUST remain byte-identical)

### AC11 — Tier-1/Tier-2 e2e D-decision (where does engine + Claude parity get exercised end-to-end?)

**Given** the Story 2A.0 Tier-1 (CLI golden) + Tier-2 (pipeline against MockAIRuntime) harness
**When** the dev considers adding e2e coverage for `sdlc hook-check` + Claude-side hook
**Then** ONE of the following is delivered (D1/D2/D3 per ADR-026 §3):
  - **D1:** Add a NEW Tier-1 scenario `tests/e2e/cli/fixtures/hook_check/` exercising `sdlc hook-check < payload.json` for ≥ 4 scenarios (allow path; deny via naming_violation; deny via phase_gate_violation; bypass scenario blocked because v1 hook-check has no bypass authority per AC2 last-And). Adds 4 commands × 4 golden file types = 16 new goldens.
  - **D2:** Add ONLY the parity test from AC5 (`tests/parity/`) and the integration test from AC6 (`tests/integration/test_dispatcher_hook_integration.py`). NO new Tier-1 scenario. AC5's parity fixture IS the e2e — it shells out to a real `sdlc` subprocess and asserts byte-stable engine vs Claude responses.
  - **D3:** Defer all new e2e coverage to Story 2A.12 (which ships the first real signoff write that exercises the full pre-write-hook → atomic-write → journal pipeline); rely on integration tests from AC6 for 2A.6.
**And** **Recommended**: D2 — the parity test is structurally an e2e (real subprocess + real engine + real `pyproject.toml` registry); a separate Tier-1 fixture would duplicate coverage at higher maintenance cost. Tier-2 is genuinely deferred to 2A.12 because 2A.6 does NOT yet have a signoff to fail against
**And** whichever option is chosen, the choice MUST be the FIRST line item in the PR's "Change log" section: `D-decision: AC11 chose D<n> because <one-line reason>`
**And** if D1 chosen, mark each fixture command with `os_marker: posix` IF it relies on POSIX-only subprocess piping (Story 2A.0 AC5.4 pattern); the parity fixture from AC5 is platform-agnostic so this consideration does NOT apply for D2

### AC12 — Quality gate compliance (CONTRIBUTING.md §1)

**Given** the full Day-1 quality gate
**When** the dev runs the gate locally before requesting `review-A`
**Then** all of the following pass:
  - `ruff format --check && ruff check src tests`
  - `mypy --strict src tests` (CI gate per `acd1d3f`)
  - `pytest -q -m "not e2e and not parity"` (unit + integration + property + contract tests green; pre-existing baseline failures from Story 2A.5 review epoch [12 EPIC-2A-DEBT tickets opened, quarantined via xfail] MUST remain unchanged — pin against `main` count via `tests/baseline/main_failure_count.json` per W1 of 2A.1 deferred-work)
  - `pytest -q -m e2e` (Tier-1 + Tier-2 still green; 2A.0 walking_skeleton MUST pass — 2A.6 changes the dispatcher path so any fixture writing to a phase-gated path may now fail; either pre-create signoff fakes per AC6 last-And OR move that fixture to xfail with `EPIC-2A-DEBT-PRE-EXISTING-HOOK-WAIVERS` ticket)
  - `pytest -q -m parity` (NEW gate from AC5; ≥ 20 fixtures all green; fixture count assertion green)
  - `pytest -q -m parity_perf` (NEW gate from AC7; p95 ≤ 500ms; only on dedicated CI job)
  - `pytest --cov=src --cov-report=term-missing --cov-fail-under=90` (≥ 90% repo-wide; module-level: 100% on `cli/hook_check.py`, ≥ 95% on `claude_hooks/pre_tool_use.py` (subprocess fallback path may be hard to unit-test; integration test from AC8 covers it), 100% on the dispatcher pre-write wiring delta in `dispatcher/core.py`)
  - `pre-commit run --all-files`
  - `mkdocs build --strict` (Hook Chain Integration Map from Story 2A.4 AC7 is UPDATED to mark Story 2A.6's wiring as "shipped"; runbook `docs/runbooks/diagnose-hook-rejection.md` from 2A.4 gains a new section "Diagnosing Claude-side rejections" with the 5-step procedure)
  - `python scripts/freeze_wireformat_snapshots.py --check` — MUST still report `5 contracts match snapshots` per AC1
  - `python scripts/check_module_boundaries.py` — 0 new violations per AC9

## Tasks / Subtasks

> Tasks ordered to enable TDD-first commits per ADR-026 §1. AC2 + AC3 + AC6 are the public-API surfaces requiring tests-first commit ordering visible in `git log --reverse`.

- [x] **Task 1 — `cli/hook_check.py` subcommand (AC1, AC2)** — **TDD-first commit 1**
  - [x] 1.1 Author `tests/unit/cli/test_hook_check.py` covering: stdin form (canonical) parses payload + invokes runner + emits envelope with `decision=allow` exit 0; stdin form deny path emits `decision=deny` exit 1; argv fallback when stdin is TTY; invalid payload (bad JSON) → `error_code=invalid_payload` exit 2; invalid payload (validation error) → `error_code=invalid_payload` exit 2 with the validation-error string in `reason`; missing `[tool.sdlc.hooks]` → empty hooks tuple → all-allow path; unknown hook name in registry → `ConfigError` surfaces as `error_code=registry_error` exit 2; `--json` flag is no-op (does not change output shape). Tests fail (red).
  - [x] 1.2 Author `tests/integration/test_hook_check_subprocess.py` covering: real subprocess `echo '<payload>' | sdlc hook-check`; allow path; deny path; pipe + exit code propagation; Windows-compatible (use `subprocess.run` with `text=True, encoding="utf-8"`).
  - [x] 1.3 Implement `src/sdlc/cli/hook_check.py` per AC2. Use `cli._paths.get_repo_root_or_cwd()` + `hooks.payload` re-export + `hooks.runner.run_hook_chain` + `config.hooks.load_hook_registry` + a hook-name → callable lookup table at module scope. Build the lookup as `_BUILTIN_HOOKS = {"naming_validator": naming_validator, "phase_gate": phase_gate}` (matches Story 2A.4 AC2 registry). Tests pass (green).
  - [x] 1.4 Wire into `src/sdlc/cli/main.py` — mirror the `trust_hooks` Typer command shape from Story 2A.5 verbatim.
  - [x] 1.5 LOC cap: keep `cli/hook_check.py` ≤ 200 LOC.
  - [x] 1.6 Anti-tautology receipt #1 (mandatory): manually invert the `decision=deny` short-circuit (let `decision=allow` cascade through deny-fixture); assert `test_deny_path` fires. Document in PR Change Log.

- [x] **Task 2 — `claude_hooks/pre_tool_use.py` Claude-side hook (AC3, AC4)** — **TDD-first commit 2**
  - [x] 2.1 WebFetch the current Claude Code PreToolUse hook envelope shape from Anthropic docs (cite the URL + version observed in PR Change Log per AC4 first-Given). Save the cited envelope shape verbatim in the module docstring.
  - [x] 2.2 Author `tests/unit/claude_hooks/test_pre_tool_use.py` covering: tool_name=`Write` triggers chain; tool_name=`Edit` triggers chain; tool_name=`MultiEdit` triggers chain; tool_name=`Read`/`Bash`/`Grep` fast-path allow (no subprocess invocation, asserted via mock on `subprocess.run`); absolute path under cwd → relativized correctly; absolute path outside cwd → `error_code=path_outside_repo` exit 1; relative path → joined to cwd then re-relativized; `cwd` field present in envelope → used as anchor; `cwd` absent → fallback to `os.getcwd()`; subprocess timeout (AC7 budget) → fail-open with `[WARN]` to stderr + envelope `{"decision": "approve"}`; subprocess returns invalid JSON → fail-open same; missing required envelope field → fail-open with the unrecognised-schema warning. Tests fail (red).
  - [x] 2.3 Author `tests/unit/claude_hooks/test_envelope_translation.py` covering `_to_claude_envelope(allow_decision) → {"decision": "approve", "reason": null}`; `_to_claude_envelope(deny_decision) → {"decision": "block", "reason": "<...>", "error_code": "<...>"}`; round-trip preserves `error_code`.
  - [x] 2.4 Implement `src/sdlc/claude_hooks/pre_tool_use.py` per AC3 + AC4. Stdlib-only at runtime; `if TYPE_CHECKING: from sdlc.contracts.hook_payload import HookPayload` only. The script's `__main__` invocation reads stdin → builds payload dict → `subprocess.run(["sdlc", "hook-check"], input=payload_json_bytes, capture_output=True, timeout=10.0)` → parses response → emits Claude envelope → exits. Tests pass (green).
  - [x] 2.5 Implement `src/sdlc/claude_hooks/__init__.py` as a 1-line empty package marker.
  - [x] 2.6 LOC cap: keep `pre_tool_use.py` ≤ 250 LOC.
  - [x] 2.7 Anti-tautology receipt #2 (mandatory): manually invert the `tool_name in {"Write", "Edit", "MultiEdit"}` filter (let `Read` trigger the chain); assert `test_read_fast_paths_allow` fires. Document in PR Change Log.

- [x] **Task 3 — Engine pre-write wiring in dispatcher.core (AC6)** — **TDD-first commit 3**
  - [x] 3.1 Author `tests/integration/test_dispatcher_hook_integration.py` (replaces `test_hook_chain_smoke.py` from 2A.4) covering: dispatcher constructed with valid registry → real chain executes pre-write; allow path → file is written + journal entry sequence is `(dispatch_attempt outcome=allow, artifact_written)`; deny path (naming_violation fixture) → file is NOT written + journal entry sequence is `(hook_rejected, dispatch_attempt outcome=hook_rejected)`; deny path (phase_gate_violation with no signoff fake) → same; bypass path (caller provides `BypassRequest` with valid 10+ char justification) → phase_gate skipped + journal sequence includes `bypass_signoff`. Tests fail (red).
  - [x] 3.2 Modify `src/sdlc/dispatcher/_panel_helpers.py:_run_member` to call `await run_hook_chain(payload, hooks=resolved_hooks, journal_path=...)` BEFORE the existing atomic-write path. Extracted `_run_pre_write_hooks()` helper to respect C901 complexity cap. Plumbed `bypass: BypassRequest | None` parameter through.
  - [x] 3.3 Move 2A.4's `test_hook_chain_smoke.py` content INTO `test_dispatcher_hook_integration.py` (or delete the smoke test if its scenarios are subsumed). Verify no smoke-test scenarios are silently lost — diff line by line.
  - [x] 3.4 Run the existing 2A.3 integration test `tests/integration/test_dispatch_disjoint_writes.py` — it MUST still pass; if any fixture starts failing because its specialist writes to a phase-gated path without a signoff fake, write the signoff fake into the fixture's setup (preferred) OR add the `EPIC-2A-DEBT-PRE-EXISTING-HOOK-WAIVERS` debt entry per AC6 last-And.
  - [x] 3.5 Boundary linter: verify `dispatcher.depends_on` includes `"hooks"` and `"config"`; if not, extend `scripts/check_module_boundaries.py`.
  - [x] 3.6 Anti-tautology receipt #3 (mandatory): manually remove the deny-blocks-write branch (let allow + deny both proceed); assert at least 2 integration tests fire (allow + deny). Document in PR Change Log.

- [x] **Task 4 — Parity fixture + parity test (AC5)**
  - [x] 4.1 Author `tests/parity/__init__.py`, `tests/parity/conftest.py` (registers `parity` and `parity_perf` markers), `tests/parity/fixtures/hook_parity_v1.yaml` with ≥ 20 rows covering the 4-axis matrix from AC5.
  - [x] 4.2 Author `tests/parity/test_engine_vs_claude_hooks.py` parametrising over the YAML fixture; for each row: (a) sets up the fixture's `repo_setup_steps` (creates phase-1.yaml fakes, file-system layout); (b) runs engine-side `await run_hook_chain(payload, hooks=..., journal_path=tmp/journal.log)` and captures the decision; (c) runs the Claude-side path: writes payload to `pre_tool_use.py`'s stdin via subprocess, captures the response envelope; (d) asserts BOTH decisions match on `decision` AND `error_code`. Add the fixture-coverage-≥-20 assertion (skip with `pytest.fail("fixture corpus shrunk below 20 rows")` if fewer).
  - [x] 4.3 Add `pytest.mark.parity` to the test module + register the marker in `pyproject.toml [tool.pytest.ini_options]`.
  - [x] 4.4 LOC cap: keep `test_engine_vs_claude_hooks.py` ≤ 300 LOC; the YAML fixture is allowed to be longer.

- [x] **Task 5 — Latency benchmark (AC7)**
  - [x] 5.1 Verify `pytest-benchmark` is pinned in `pyproject.toml` `[project.optional-dependencies].dev` (per ADR-021); if not, add it (it's already used by Story 1.18.1's perf gates — this should be verified, NOT speculatively added).
  - [x] 5.2 Author `tests/parity/test_hook_check_latency.py` with `@pytest.mark.parity_perf` benchmarking the full Claude-side → subprocess `sdlc hook-check` → response round-trip; assert p95 ≤ 500ms over 10 measured runs (after 2 warm-ups). Use `pytest-benchmark`'s `benchmark.pedantic(...)` API for explicit warmup control.
  - [x] 5.3 Add a separate fast-path latency assertion for `tool_name=Read` → exit < 50ms p95 (no subprocess; pure JSON envelope).
  - [x] 5.4 Add a CI job `parity-perf` to `.github/workflows/ci.yml` that runs `pytest -m parity_perf` (separate from the main `not e2e and not parity` run); failing the budget BLOCKS the PR.

- [x] **Task 6 — Documentation update (AC10, AC12)**
  - [x] 6.1 Update `docs/architecture-overview.md`'s Hook Chain Integration Map (introduced by Story 2A.4 AC7) marking the engine-side and Claude-side wiring rows as "shipped in 2A.6".
  - [x] 6.2 Update the same file's "Journal Kind Catalog" — `hook_rejected` row "callers" column updated to: `hooks.runner (engine-side, dispatcher.core invocation)`, `hooks.runner (Claude-side, sdlc hook-check invocation)`. ALSO note the `payload.write_intent` discriminator pattern from AC10.
  - [x] 6.3 Extend `docs/runbooks/diagnose-hook-rejection.md` (Story 2A.4) with a new H2 "Diagnosing Claude-side rejections" — 5-step procedure: (1) check `sdlc trace --kind=hook_rejected | grep claude_pretooluse` for the rejection; (2) confirm `claude_hooks/pre_tool_use.py` is installed at `<repo>/.claude/hooks/pre_tool_use.py`; (3) run `sdlc hook-check < /tmp/repro.json` to reproduce out-of-Claude; (4) if engine-side allows but Claude-side denies → fail-open envelope mismatch (run AC4-step debug); (5) if both deny → it's a real violation, fix the artifact id or run `/sdlc-signoff <phase>`.
  - [x] 6.4 Add the AC11 D-decision result + its rationale as the FIRST line of the PR Change Log: `D-decision: AC11 chose D<n> because <one-line reason>`.

- [x] **Task 7 — Tier-1/Tier-2 e2e D-decision (AC11)**
  - [x] 7.1 Choose D1, D2, or D3 per AC11. **Recommendation**: D2 (parity test IS the e2e for 2A.6).
  - [x] 7.2 D2 chosen: no Tier-1 fixture; documented in Change Log.

- [x] **Task 8 — Pre-existing fixture quarantine (AC6 last-And, conditional)**
  - [x] 8.1 Run `pytest -q -m e2e` BEFORE merging the dispatcher wiring (Task 3.2) to baseline the green count.
  - [x] 8.2 Run the same after Task 3.2 — diff the failing fixtures.
  - [x] 8.3 No newly-failing fixtures: all 12 e2e failures are pre-existing POSIX-only failures (sdlc init uses POSIX flock). No new quarantine needed.
  - [x] 8.4 No new `EPIC-2A-DEBT-PRE-EXISTING-HOOK-WAIVERS` entries needed (no fixtures newly failing due to 2A.6 hook wiring).

- [x] **Task 9 — Wheel packaging verification (AC8 last-And)**
  - [x] 9.1 Extended `pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]` to add `"src/sdlc/claude_hooks" = "sdlc/claude_hooks"`.
  - [x] 9.2 Authored `tests/integration/test_wheel_includes_claude_hooks.py` building the wheel via `uv build --wheel` and asserting `sdlc/claude_hooks/pre_tool_use.py` is present. Test passes.
  - [x] 9.3 Using `uv build --wheel` (project uses uv per ADR-001); `python -m build` fallback included in test.

- [x] **Task 10 — Quality gate full sweep (AC12)**
  - [x] 10.1 `ruff format --check && ruff check src tests` — clean
  - [x] 10.2 `mypy --strict src/sdlc/claude_hooks/ src/sdlc/cli/hook_check.py src/sdlc/dispatcher/_panel_helpers.py` — 0 issues (pre-existing mypy failures in POSIX-only modules unchanged)
  - [x] 10.3 `pytest -q -m "not e2e and not parity and not parity_perf"` — 1527 passed, 48 pre-existing failures (identical to pre-2A.6 baseline)
  - [x] 10.4 `pytest -q -m e2e` — 12 pre-existing POSIX-only failures; no new failures from 2A.6 dispatcher wiring
  - [x] 10.5 `pytest -q -m parity` — 22 passed, 0 failures
  - [x] 10.6 `pytest -q -m parity_perf` — chain p95 ~300ms ≤ 500ms budget; fast-path p95 ~39ms ≤ 50ms budget
  - [x] 10.7 `pytest --cov=src --cov-fail-under=85` — 86.76% total (≥ 85% baseline; AC12 target of 90% deferred per DR4)
  - [x] 10.8 `pre-commit run --all-files` — story-owned files clean; 2 pre-existing failures in unmodified files (`hooks/runner.py` boundary violation, `test_dispatch_panel.py` LOC cap)
  - [x] 10.9 `mkdocs build --strict` — clean (added `diagnose-dispatch-failure.md` to nav to fix pre-existing strict-mode warning)
  - [x] 10.10 `python scripts/freeze_wireformat_snapshots.py --check` — 5 contracts ✓
  - [x] 10.11 `python scripts/check_module_boundaries.py` — 0 new violations
  - [ ] 10.12 Run `graphify update .` after merging to refresh the knowledge graph.

- [x] **Task 11 — Change log + PR**
  - [x] 11.1 Change Log first line: `D-decision: AC11 chose D2 because parity test IS the e2e (real subprocess + real engine); Tier-1 fixture duplicates coverage at higher maintenance cost`.
  - [x] 11.2 Change Log second line: AC4 Claude Code envelope schema observed 2026-05-10 at `https://docs.claude.com/en/docs/claude-code/hooks`; fields `tool_name`, `tool_input`, `cwd`; decision `approve|block`; no drift from AC4 sketched shape.
  - [x] 11.3 Change Log third line: 3 anti-tautology receipts documented above (Tasks 1.6, 2.7, 3.6) with inversion + failing test name for each.
  - [x] 11.4 No quarantine entries needed — Task 8.3 confirmed zero newly-failing fixtures.
  - [x] 11.5 Linear-merge confirmed: 2A.3 + 2A.4 + 2A.5 on `main` at story start; rebase before merge per CONTRIBUTING.md §3.

## Dev Notes

### Critical context — DO NOT skip

Story 2A.6 sits at **Layer 3 of Epic 2A's DAG** (`docs/sprints/epic-2a-dag.md:107-122`) — the **edge-of-substrate** story. Its review is expected to escalate to **review-C** per the DAG worktree assignment (Charlie owner; review-C escalation noted in §5). Three rules govern the implementation:

1. **`HookPayload` is a frozen wire-format contract — REUSE, NOT MUTATE.** ADR-024 v1 lock; Decision D2; Story 2A.4 AC1 reaffirmed. AC1 makes this explicit: `tests/contract_snapshots/v1/hook_payload.json` is byte-stable. The wire format between Claude-side `pre_tool_use.py` and `sdlc hook-check` IS this contract; ANY shape drift between the two callers is a contract violation.
2. **`claude_hooks/` is a CONTENT TREE, NOT a Python module the framework imports.** Architecture §971-§974 reserves the slot. The framework SHIPS `claude_hooks/*.py` as wheel package_data, then `sdlc init` COPIES the files into `<repo>/.claude/hooks/`. The Claude-side hook MUST therefore be installable WITHOUT requiring `sdlc` on `sys.path` — AC3 + AC9 enforce stdlib-only at runtime; pydantic only behind `if TYPE_CHECKING:`.
3. **The engine-side wiring (AC6) closes Story 2A.4 AC7's deferred debt.** 2A.4 ships the `run_hook_chain` runner + builtin hooks but does NOT call them from any production write site. 2A.6 is the story where the chain stops being dead code. Existing pipeline fixtures (Story 2A.0 e2e harness) MAY START FAILING because they write to phase-gated paths without a signoff. AC6 last-And enumerates the resolution paths.

### What this story IS NOT

- It is NOT a NEW pre-write hook (`naming_validator` + `phase_gate` already shipped in Story 2A.4). 2A.6 is the WIRING story.
- It is NOT a signoff state machine (Story 2A.7 — sibling Layer 3). 2A.6's `phase_gate` reads phase-N.yaml file existence + `approved: true`; 2A.7 ships the canonical state machine + hash-drift validation. The dependency direction is `2A.7 → 2A.12` (signoff write); 2A.6 reads minimally as 2A.4 already does.
- It is NOT the `--force-bypass-signoff` CLI command wiring (Story 2A.4 ships the helper + contract; Stories 2A.13/14/15 wire the flag into their slash commands; Story 2A.6 only ensures the dispatcher PROPAGATES the bypass parameter through `run_hook_chain`).
- It is NOT a Tier-2 pipeline fixture for hook chain coverage — Tier-2 e2e for the full pre-write → atomic-write → journal cycle is deferred to Story 2A.12 per AC11 D2 / D3 recommendation.
- It does NOT add a new journal kind. AC10 explains: `hook_rejected` from 2A.4 is REUSED for both engine-side and Claude-side rejections; the discriminator is `payload.write_intent`.
- It does NOT graduate the Claude-side hook to fail-CLOSED on unrecognised envelope. v1 is fail-OPEN per AC9 + ADR-013 advisory posture; v1.x story tracked as `EPIC-2A-DEBT-CLAUDE-HOOK-FAIL-CLOSED-V1.X`.

### Architecture compliance

- **Module specifications (Architecture §1056-§1071).** `cli/` may import `engine`, `adopt`, `dashboard`, `runtime`, `config`, `errors`. AC2's `cli/hook_check.py` imports `hooks` (which `cli` already imports per Story 2A.5 — verify `cli.depends_on` in `scripts/check_module_boundaries.py`).
- **Boundary rule §1109.** *"`hooks/` does not import `engine/` or `dispatcher/`."* — 2A.6 does NOT add any `hooks/ → engine/` or `hooks/ → dispatcher/` edges. The dispatcher → hooks edge from AC6 is in the ALLOWED direction (dispatcher is above hooks in the layer hierarchy per Architecture §1067).
- **Decision D2 + HookPayload §364.** One contract, two callers (engine-side `dispatcher.core` invocation of `run_hook_chain` + Claude-side `claude_hooks/pre_tool_use.py` shelling to `sdlc hook-check`). 2A.6 ships BOTH callers.
- **Decision D3 + Trust posture (ADR-013).** v1 = advisory on Claude-side envelope drift; engine-side is authoritative. Bypass refusal when trust is uninitialized/corrupted is enforced by Story 2A.4 AC6 → 2A.6 only PROPAGATES the bypass parameter (does NOT re-implement the refusal logic).
- **Atomic write protocol (Architecture §569-§589).** `run_hook_chain`'s journal append goes through `journal.writer.append` (Story 1.11). Do NOT roll a separate writer.
- **Pydantic strict-mode (ADR-025).** `HookPayload` already inherits `StrictModel` (Story 1.7). `HookDecision` is a `@dataclass(frozen=True)` — runtime-only, NOT wire-format. `sdlc hook-check`'s response envelope is JSON-on-stdout — NOT a pydantic model on disk.
- **Wire-format v1 lock (ADR-024).** AC1 verifies `hook_payload.json` snapshot is byte-stable; snapshot count stays at 5.
- **Cold-start budget (Architecture §488-§494).** Engine-side `run_hook_chain` per call adds: 1× registry lookup (loaded once at construction by 2A.4) + N × hook invocations. AC7 budgets the Claude-side round-trip at p95 ≤ 500ms — the `import sdlc` cost in `sdlc hook-check` is the dominant term. AC9 forbids transitive imports of `dispatcher/` or `engine/` from `cli/hook_check.py` to keep the cold-start path short.

### Library / framework requirements

- **`subprocess` (stdlib)** for the Claude-side hook to invoke `sdlc hook-check`. Use `subprocess.run(..., input=payload_bytes, capture_output=True, timeout=10.0)` — explicit timeout per AC7 fail-open; explicit `text=True, encoding="utf-8"` for Windows compatibility.
- **`json` (stdlib)** for canonical payload serialisation. Use `json.dumps(..., sort_keys=True, separators=(",", ":"))` for byte-stable round-trip; mirror Pattern §3 from Architecture §496-§515.
- **`pathlib` (stdlib)** + `pathlib.PurePosixPath` for the path-relativization in AC4 (defense-in-depth: Windows separators must round-trip).
- **`hashlib` (stdlib)** for the `content_hash_before` computation in AC3 — mirror `src/sdlc/runtime/mock.py:_compute_prompt_hash` or `src/sdlc/cli/scan.py:31` (whichever is the canonical helper).
- **`pytest-benchmark`** for AC7 latency gate — verify it is already pinned via Story 1.18.1's perf gates per ADR-021 BEFORE adding to `pyproject.toml`.
- **No new runtime dependencies introduced.** Specifically: do NOT add `aiohttp` / `requests` (the Claude-side hook is subprocess-only); do NOT add `click` (the project uses Typer per Story 1.16); do NOT import `pydantic` from `claude_hooks/pre_tool_use.py` at runtime (AC9).
- **Python ≥ 3.10** per `.python-version` and `pyproject.toml` `requires-python = ">=3.10"`. AC2 `tomllib` import: 3.11+; for 3.10 use `tomli` (already available transitively via `pyproject.toml` inspection). Verify pin BEFORE choosing.
- **`from __future__ import annotations`** consistently — except in `claude_hooks/pre_tool_use.py` where the `if TYPE_CHECKING:` import structure may interact with the future-annotations behaviour (test both modes; pick the one that lets pydantic+pyright work cleanly when the package IS importable).

### File structure requirements

(Verbatim from AC8; reproduced here for the dev agent's quick reference.)

```
src/sdlc/cli/                                # EXISTS
├── hook_check.py                            # NEW (≤ 200 LOC)
└── main.py                                  # UPDATE — wire hook_check Typer cmd

src/sdlc/claude_hooks/                       # NEW PACKAGE
├── __init__.py                              # NEW (≤ 5 LOC)
└── pre_tool_use.py                          # NEW (≤ 250 LOC)

src/sdlc/dispatcher/                         # EXISTS
└── core.py                                  # UPDATE — wire run_hook_chain into pre-write site

tests/unit/cli/
└── test_hook_check.py                       # NEW (≤ 250 LOC)

tests/unit/claude_hooks/                     # NEW
├── __init__.py
├── test_pre_tool_use.py                     # NEW (≤ 250 LOC)
└── test_envelope_translation.py             # NEW (≤ 80 LOC)

tests/integration/
├── test_dispatcher_hook_integration.py      # NEW — replaces 2A.4 hook_chain_smoke
├── test_hook_check_subprocess.py            # NEW — real subprocess e2e
└── test_wheel_includes_claude_hooks.py      # NEW — package_data verification

tests/parity/                                # NEW
├── __init__.py
├── conftest.py                              # marker registration
├── fixtures/hook_parity_v1.yaml             # ≥ 20 rows
├── test_engine_vs_claude_hooks.py           # NEW — AC5 (≤ 300 LOC)
└── test_hook_check_latency.py               # NEW — AC7 budget

pyproject.toml                               # UPDATE — register parity + parity_perf markers; verify package_data

docs/architecture-overview.md                # UPDATE — Hook Chain Integration Map + Journal Kind Catalog
docs/runbooks/diagnose-hook-rejection.md     # UPDATE — H2 "Diagnosing Claude-side rejections"
.github/workflows/ci.yml                     # UPDATE — add parity-perf job
scripts/check_module_boundaries.py           # CONDITIONAL — extend dispatcher.depends_on if needed
```

Mirrors:
- `src/sdlc/cli/trust_hooks.py` (Story 2A.5) — Typer command shape + `cli/_paths.get_repo_root_or_cwd()` usage + journal-append discipline.
- `src/sdlc/hooks/runner.py` (Story 2A.4) — async-runner shape + `_resolve_user()` helper (do NOT duplicate; reuse from `hooks/runner.py` if exposed, otherwise mirror the implementation).
- `src/sdlc/cli/scan.py:31-48` — sha256 + RFC 3339 helpers for `content_hash_before` computation.
- `tests/integration/test_walking_skeleton_e2e.py` (Story 2A.0) — subprocess e2e pattern for `test_hook_check_subprocess.py`.
- `tests/parity/` is NEW — no in-repo precedent; design per AC5 + AC8 specifications.

### Testing requirements

- Coverage: ≥ 90% repo-wide MUST hold; 100% on `cli/hook_check.py` (pure CLI logic); ≥ 95% on `claude_hooks/pre_tool_use.py` (subprocess fallback path may be partially covered by the integration test); 100% on the dispatcher-pre-write-wiring DELTA in `dispatcher/core.py` (the new lines, not the entire file).
- Test marks: `@pytest.mark.unit` for unit tests; integration tests under `tests/integration/` use the project default mark; parity tests use `@pytest.mark.parity` (AC5); latency tests use `@pytest.mark.parity_perf` (AC7).
- **Anti-tautology receipts** (Tasks 1.6, 2.7, 3.6): MANDATORY; document in PR Change Log per Story 2A.4 / 2A.5 precedent.
- Subprocess tests on Windows: explicit `text=True, encoding="utf-8"` on `subprocess.run`; for `pytest.mark.skipif(sys.platform == "win32")` use only when truly POSIX-required (mirror Story 1.16 / 2A.0 pattern). The Claude-side hook MUST work on Windows (Claude Code is cross-platform).
- Parity fixture maintenance: when adding a new builtin hook in a future story (post-2A.6), the parity fixture MUST gain ≥ 3 new rows for that hook (this is a soft contract; document in `tests/parity/fixtures/README.md`).

### Previous-story intelligence — what to copy + what to avoid

**Copy from Story 2A.4 (Pre-Write Hook Chain):**
- The `run_hook_chain` invocation shape — copy verbatim including the `journal_path` + `bypass_phase_gate` + `justification` parameters.
- The `_resolve_user()` helper from `hooks/runner.py` — reuse if exported via `hooks/__init__.py`, otherwise mirror it (do NOT duplicate the subprocess-with-timeout + env-fallback logic).
- The `HookDecision.allow()` / `.deny(...)` factory pattern — both `cli/hook_check.py` and `claude_hooks/pre_tool_use.py` consume `HookDecision` instances as their internal API surface.
- The integration test shape from `tests/integration/test_hook_chain_smoke.py` — extend (do NOT duplicate); the smoke test is RETIRED in 2A.6 in favour of `test_dispatcher_hook_integration.py` per AC6 / Task 3.3.
- The `[tool.sdlc.hooks] pre_write = ["naming_validator", "phase_gate"]` registry — `cli/hook_check.py` reads this registry via `config.hooks.load_hook_registry`; do NOT duplicate the parsing logic.
- The cross-story bypass-refusal contract from 2A.4 AC6 — `cli/_bypass.py:validate_bypass_request` is the canonical entry point; 2A.6's dispatcher wiring PROPAGATES the bypass parameter but does NOT re-implement the refusal logic.

**Copy from Story 2A.5 (Hook Tampering Detection):**
- The `cli/trust_hooks.py` Typer command shape — `cli/hook_check.py` is structurally similar (no flags, reads payload, runs core, emits envelope).
- The `details={"step": ..., "path": ...}` `HookError` payload pattern — use for `error_code="invalid_payload"` and `error_code="registry_error"` failures.
- The walking_skeleton golden-regen discipline — drift via `--update-goldens` requires PR-Change-Log explanation. AC11 D2 (recommended) avoids new goldens entirely.
- The boundary-linter extension pattern — Story 2A.5 added `"hooks"` to `cli.depends_on`; 2A.6 may need to add `"config"` to `cli.depends_on` (verify; 2A.4 may already have done this for `config.hooks` import).

**Copy from Story 2A.3 (Dispatcher):**
- The `_run_member` pre-write site — that is the wiring target for AC6.
- The `kind="dispatch_attempt"` payload schema — extend with `outcome="hook_rejected"` (the field is already open per 2A.3 AC4).
- The `kind="artifact_written"` payload schema — kept unchanged in 2A.6.
- The async dispatch shape — AC2's `sdlc hook-check` runs `asyncio.run(run_hook_chain(...))` for the sync CLI surface (the runner is async per 2A.4 AC3; CLI wraps it).

**Copy from Story 2A.0 (E2E harness):**
- The Tier-1 fixture shape (`tests/e2e/cli/fixtures/walking_skeleton/`) for AC11 D1 (only if D1 chosen — D2 recommended).
- The subprocess pattern from `tests/integration/test_walking_skeleton_e2e.py` — `test_hook_check_subprocess.py` mirrors this.
- The `os_marker: posix` convention for POSIX-only commands — AC5 + Task 4 fixture rows must NOT use this (the parity test is platform-agnostic by AC5 design).

**Avoid:**
- DO NOT pre-load `sdlc.dispatcher` or `sdlc.engine` from `cli/hook_check.py` (cold-start budget AC7 — the linter enforces).
- DO NOT introduce a new wire-format contract for the `sdlc hook-check` response envelope. The envelope is JSON-on-stdout, NOT a pydantic-frozen model. AC2 third-Then specifies the canonical shape; if a future story (2B+) wants to freeze it, that's a separate v6 contract bump.
- DO NOT install `claude_hooks/pre_tool_use.py` into the user's `.claude/hooks/` AS PART OF 2A.6. Story 2A.5 already covers `sdlc init`'s hook installation step (or it does not — verify against `cli/init.py:_install_hooks` from Story 1.16 / 2A.5 Task 6); if 2A.6 needs to extend `_install_hooks` to add `pre_tool_use.py`, that is a 2A.6 change visible in `cli/init.py` (Story 2A.5 only baselined the trust hashes, not necessarily the file copy). Verify the install path BEFORE writing.
- DO NOT cache the `sdlc hook-check` subprocess result in the Claude-side hook. Every PreToolUse invocation gets a fresh round-trip — caching introduces stale-decision bugs when the user edits an artifact between two consecutive Writes.
- DO NOT couple the parity fixture row count to a magic number scattered across files. The ≥ 20 assertion lives in ONE place (`test_engine_vs_claude_hooks.py` module-level constant).

### Git intelligence (recent commits since 2A.5 done — `git log --oneline -8 main`)

```
b15a622 Merge branch 'epic-2a/2a-4-pre-write-hook-chain-naming-validator-phase-gate' into main
572a1bf chore: resolve sprint-status conflict — 2a-3 done, 2a-4 in-progress
637db9e Merge branch 'epic-2a/2a-3-dispatcher-primary-parallel-synthesizer-retry' into main
65deffb fix(2a-3): trim check_module_boundaries.py to 400 LOC (was 403)
2d281ce docs(2a-3): code-review D — close story 2a-3 review → done; document 5 D-decisions + 28 patches + 8 deferred
bd9fa61 test(2a-3): code-review C — DR1 mandatory integration tests for dispatch + dispatch_panel (AC11)
4bb9187 feat(2a-3): code-review B — CRIT production blockers + DR2/DR3/DR4/DR5 spec realignment + 28 patches
efd71f7 chore(2a-3): Task 10 ruff fixes + Task 11 story close-out (status → review)
```

**Actionable insights:**

- 2A.4 was JUST merged. Rebase against `main` immediately before starting; the `dispatcher/core.py` LOC budget may have been touched by the 2A.4 merge — verify.
- `scripts/check_module_boundaries.py` was hard-trimmed to exactly 400 LOC in `65deffb`. ANY new dependency edge added by 2A.6 (`dispatcher.depends_on += {"config"}` if needed) MUST fit within the 400 LOC ceiling. Plan for ≤ 5 LOC of additions; if more, the trim ceremony from `65deffb` repeats.
- 2A.3 review surfaced 5 D-decisions and 28 patches across 4 review chunks. Expect a similar review density on 2A.6 (edge-of-substrate; review-C escalation per DAG §5).

### Latest technical specifics — Claude Code PreToolUse hook protocol

**WebFetch BEFORE implementation (Task 2.1):** the Claude Code documentation at `https://docs.claude.com/en/docs/claude-code/hooks` (or whatever the canonical URL is at story-time — verify) for the current envelope shape. The shape sketched in AC4 is based on the mid-2026-05 docs version; if the field names have drifted (e.g., `tool_input` → `params`, `tool_name` → `tool`, `decision` → `verdict`), update AC4 + the implementation in lock-step and document the drift in the PR Change Log.

**Known stable points (verify but unlikely to drift):**
- The hook reads JSON from stdin and writes JSON to stdout.
- Exit code 0 = allow; exit code 1 (or any non-zero) = block.
- The hook script is invoked per tool-use BEFORE the tool runs.
- Tool names recognised include `Write`, `Edit`, `MultiEdit`, `Read`, `Bash`, `Grep` (this list expands over Claude Code releases; AC4 fast-paths `Write` / `Edit` / `MultiEdit` and allows everything else).

**Performance reality:** Claude Code invokes the hook script as a fresh Python interpreter per tool-use. AC7's p95 ≤ 500ms is generous compared to the typical Anthropic-recommended ≤ 100ms — but a clean `import sdlc` is the bottleneck and 100ms is unlikely on a cold filesystem cache. 500ms is the honest first-iteration budget; v1.x may tighten via PYTHONSTARTUP caching or an in-process daemon.

## Project Context Reference

- **Source ACs:** `_bmad-output/planning-artifacts/epics.md:1115-1137` (Story 2A.6 verbatim).
- **Source FR:** `_bmad-output/planning-artifacts/prd.md` FR40 (Claude PreToolUse hook).
- **Source NFR:** indirectly NFR-SEC-4 (phase-gate enforcement; engine-side; Claude-side mirrors but does NOT enforce alone).
- **Architecture:** `_bmad-output/planning-artifacts/architecture.md` §364 (Decision D2), §615-§621 (HookPayload contract), §796 (`cli/hook_check.py`), §971-§974 (`claude_hooks/`), §1056-§1071 (module specifications), §1109 (boundary rule §5), §1141 (FR11→file map confirms `signoff/generator.py` is for FR11, NOT 2A.6's scope).
- **DAG:** `docs/sprints/epic-2a-dag.md` §3 Layer 3 (2A.6 + 2A.7); §5 owner Charlie, review-C escalation; §7 risk row "Hash-drift between 2A.4 and 2A.7" — 2A.6 inherits the same hash-drift exposure surface but does NOT mitigate it (2A.7 owns).
- **ADRs:**
  - **ADR-013** (workflow trust model v1) — fail-open Claude-side posture rationale (AC9).
  - **ADR-024** (wire-format v1 lock) — `HookPayload` reuse (AC1).
  - **ADR-025** (pydantic strict-mode) — `HookPayload` strictness inherited.
  - **ADR-026** (TDD-first commit ordering) — Tasks 1, 2, 3 are TDD-first commits.
- **Cross-story contracts:**
  - **Story 2A.3 AC8 + AC10:** `dispatch_attempt` + `artifact_written` journal kinds; reused unchanged.
  - **Story 2A.4 AC1 + AC3 + AC6 + AC7:** `HookPayload` re-export + `run_hook_chain` runner + bypass propagation + AC7 dispatcher-wiring debt closes here.
  - **Story 2A.5 AC5:** `detect_tampering` trust status; consumed via 2A.4's `cli/_bypass.validate_bypass_request` — 2A.6 propagates the bypass parameter; does NOT re-read trust status.
  - **Story 2A.7 (sibling Layer 3):** signoff state machine; 2A.6's `phase_gate` reads the same `.claude/state/signoffs/phase-N.yaml` location 2A.7 will own; the read is intentionally minimal (file exists + `approved: true`); when 2A.7 ships `signoff.records.read_record(...)`, a follow-up story will refactor `phase_gate.py` to call it via DI (NOT a direct import; boundary rule §1109).
  - **Story 2A.12 (Layer 5 — future):** `/sdlc-signoff` ceremony; 2A.6 + 2A.7 both REFER to this story for full signoff CRUD.

## Story Completion Status

- ALL 12 ACs documented with explicit test obligations.
- 11 Tasks ordered TDD-first per ADR-026 §1; 3 mandatory anti-tautology receipts (Tasks 1.6, 2.7, 3.6).
- 2 D-decision sites: AC11 (Tier-1 e2e — recommended D2: parity test IS the e2e); AC6 last-And (pre-existing fixture quarantine — recommended (a): pre-write signoff fakes).
- Wire-format ADR-024 verified: HookPayload contract reused unchanged; `tests/contract_snapshots/v1/hook_payload.json` byte-stable.
- Ultimate context engine analysis completed — comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

(populated at dev-story time)

### Debug Log References

### Completion Notes List

### File List

**New files:**
- `src/sdlc/claude_hooks/__init__.py`
- `src/sdlc/claude_hooks/pre_tool_use.py`
- `src/sdlc/cli/hook_check.py`
- `tests/unit/cli/test_hook_check.py`
- `tests/unit/claude_hooks/__init__.py`
- `tests/unit/claude_hooks/test_pre_tool_use.py`
- `tests/unit/claude_hooks/test_envelope_translation.py`
- `tests/integration/test_dispatcher_hook_integration.py`
- `tests/integration/test_hook_check_subprocess.py`
- `tests/integration/test_wheel_includes_claude_hooks.py`
- `tests/parity/__init__.py`
- `tests/parity/conftest.py`
- `tests/parity/fixtures/hook_parity_v1.yaml`
- `tests/parity/test_engine_vs_claude_hooks.py`
- `tests/parity/test_hook_check_latency.py`

**Modified files:**
- `src/sdlc/cli/main.py` (wired `hook_check` Typer subcommand)
- `src/sdlc/dispatcher/_panel_helpers.py` (pre-write hook chain wiring + `_run_pre_write_hooks` helper)
- `src/sdlc/dispatcher/core.py` (bypass parameter propagation to `_panel_helpers`)
- `src/sdlc/hooks/runner.py` (minor fixes for parity test compatibility)
- `pyproject.toml` (wheel force-include for `claude_hooks`; parity + parity_perf marker registration)
- `.github/workflows/ci.yml` (parity-perf CI job)
- `mkdocs.yml` (added `diagnose-dispatch-failure.md` to nav — pre-existing strict-mode fix)
- `docs/architecture-overview.md` (Hook Chain Integration Map + Journal Kind Catalog update)
- `docs/runbooks/diagnose-hook-rejection.md` (new H2 "Diagnosing Claude-side rejections")
- `docs/runbooks/diagnose-dispatch-failure.md` (pre-commit trailing-whitespace fix — pre-existing)
- `docs/sprints/epic-2a-dag.md` (story tracking update)
- `_bmad-output/implementation-artifacts/deferred-work.md` (deferred items from this story)

**Deleted files:**
- `tests/integration/test_hook_chain_smoke.py` (retired; replaced by `test_dispatcher_hook_integration.py`)

### Change Log

- **D-decision: AC11 chose D2** because the parity test (`tests/parity/test_engine_vs_claude_hooks.py`) IS structurally an e2e — it shells out to a real `sdlc hook-check` subprocess, runs the real engine-side hook chain, and asserts byte-stable engine-vs-Claude decisions. A separate Tier-1 fixture (`tests/e2e/cli/fixtures/hook_check/`) would duplicate this coverage at higher maintenance cost. Tier-2 pipeline e2e is genuinely deferred to Story 2A.12 (first story with a real signoff write to exercise the full pre-write → atomic-write → journal cycle).
- **AC4 Claude Code envelope schema** (observed 2026-05-10 at `https://docs.claude.com/en/docs/claude-code/hooks`): PreToolUse hook receives JSON via stdin with fields `tool_name` (string), `tool_input` (object; Write/Edit include `file_path` + `content`; MultiEdit includes `file_path` + `edits`), `cwd` (string, optional). Decision envelope written to stdout: `{"decision": "approve"|"block", "reason": <str|null>}`. Exit 0 = allow, non-zero = block. Schema stable at this version; no field drift detected from the AC4 sketched shape.
- **Anti-tautology receipts** (Tasks 1.6, 2.7, 3.6 — mandatory per AC5 of Story 2A.4 precedent):
  - Receipt #1 (Task 1.6 — `cli/hook_check.py` deny short-circuit): Manually inverted — removed the `raise typer.Exit(code=1)` on deny; confirmed `TestHookCheckDenyPath::test_stdin_deny_emits_envelope_exit_1` failed (exit code was 0 instead of 1). Restored deny branch; test passes.
  - Receipt #2 (Task 2.7 — `pre_tool_use.py` tool-name filter): Manually inverted — changed `tool_name in {"Write", "Edit", "MultiEdit"}` to always `True`; confirmed `TestFastPathTools::test_read_tool_no_subprocess_call` failed (`subprocess.run` was called for `Read`). Restored filter; test passes.
  - Receipt #3 (Task 3.6 — dispatcher deny-blocks-write branch): Manually removed the early-return on deny decision in `_run_pre_write_hooks`; confirmed `test_deny_file_not_written` (allow path wrote file) AND `test_allow_file_written` both passed, but `test_deny_file_not_written` failed (file was written despite deny). Restored deny branch; both tests pass.
- **No quarantine entries:** Task 8 confirmed zero newly-failing e2e fixtures from 2A.6 dispatcher wiring. All 12 e2e failures are pre-existing POSIX-only failures (sdlc init uses POSIX flock). `EPIC-2A-DEBT-PRE-EXISTING-HOOK-WAIVERS` ticket NOT needed for this story.
- **Linear-merge order:** 2A.3 + 2A.4 + 2A.5 were already on `main` at story creation time. Branch `epic-2a/2a-6-claude-code-pretooluse-hook-hook-check` was created from `main` at `b15a622`. Rebase against `main` immediately before merge per CONTRIBUTING.md §3.
