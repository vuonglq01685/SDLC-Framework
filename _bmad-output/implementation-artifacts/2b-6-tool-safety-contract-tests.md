# Story 2B.6: Tool-Safety Contract Tests

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user trusting the framework not to invoke arbitrary system commands,
I want contract tests asserting subprocess invocation is restricted to the documented allow-list (`claude`, `git`, `gh`) and tool calls returning destructive operations require re-confirmation,
so that the supply-chain risk surface is bounded and tested (Concern #13, NFR-SEC-3, NFR-PRIV-1).

## Acceptance Criteria

> **Source ACs:** `_bmad-output/planning-artifacts/epics.md:1582-1604` (3 AC groups → AC1–AC3 below).
> **DAG position:** **Layer 2**, Epic 2B. Depends on **2B.1** for the `runtime/claude.py` callsite that AC2's allow-list whitelists (DAG §3 dependency note). **Layer-3 Story 2B.7** (`docs/threat-model.md`) depends on this story — it documents tool-safety surfaces and links to the test paths added here.
> **One new wire-format-adjacent surface (`SecurityError` reuse).** This story reuses `SecurityError(SdlcError, code="ERR_SECURITY", exit=2)` introduced by Story 2B.5 — **do NOT re-add it**. The destructive-op dispatcher pause is a CLI prompt, not a new contract.
> **No new `JournalEntry.kind` values** unless AC3's dispatcher-pause emits an audit-trail entry — see AC3/D3 for a `destructive_op_reconfirmed` proposal (open-string kind per ADR-028; add a §3 table row if emitted).
>
> **Scope boundary — do NOT reinvent:**
> - **`SecurityError` already exists** (Story 2B.5 / `src/sdlc/errors/base.py`, code `ERR_SECURITY`, exit 2). Reuse it for AC1/AC2 static-check failures.
> - **The static-check script pattern is canonical** — `scripts/check_no_hardcoded_secrets.py` (100 LOC): `_REPO_ROOT`, `_EXEMPT_DIRS`, `_SELF`, `_NOQA_PATTERN`, `_scan_file(path) -> list[(lineno, col, msg)]`, `main(argv) -> int`. Model new scripts on it. **Re-use `_EXEMPT_DIRS = {"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"}`** — the same set the secret-check uses (verify via grep before redefining).
> - **CR2B5-W1 (`EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-ROTATION`) + CR2B5-W2 (`EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-SCOPING`) flow into AC3.** These are explicitly deferred from 2B.5 to this story per `deferred-work.md:575-576`. The 2B.5 destructive-op tokens in `src/sdlc/dispatcher/prompts.py:25-36` (static English literals `RECONFIRM_FILE_DELETE` / `RECONFIRM_FORCE_PUSH` / `RECONFIRM_DROP_DATABASE`, applied unconditionally to every Phase-1 prompt) are the **prompt-text half** of destructive-op safety. AC3 here is the **dispatcher-side half**: detect, pause, re-confirm.

### AC1 — No outbound HTTP from `src/sdlc/` (AST static check)

**Given** the framework process
**When** I run the network-isolated CI test (`tests/security/test_no_outbound_http.py`)
**Then** the framework runs the full pipeline offline except for documented subprocess calls
**And** any attempted import of `http.client`, `urllib3`, `requests`, `httpx` (and the obvious aliases — `aiohttp`, `urllib.request`, see AC1/D1) in non-test code under `src/sdlc/` fails the static check
**And** the assertion is enforced by **AST parsing** of `src/sdlc/`, not by a `grep` heuristic (a `grep` for `import requests` misses `from requests import …`, `__import__("requests")`, and conditional imports)
**And** the failure raises `SecurityError("module <path> imports forbidden network module <name>")` with the exact `file:line` of the offending `Import` / `ImportFrom` node
**And** test exit code is 2 (matches `ERR_SECURITY` from Story 2B.5)

**And** **AC1/D1 — forbidden-module list:** the epic lists 4 modules (`http.client`, `urllib3`, `requests`, `httpx`). Pick the **canonical exhaustive list** (record in code as `_FORBIDDEN_NETWORK_MODULES: frozenset[str]`):
  - **D1 (Recommended):** `frozenset({"http.client", "http.server", "urllib", "urllib.request", "urllib3", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "socket"})`. **Rationale:** the epic's 4-module list is illustrative; `socket` is the universal escape hatch (`requests` itself is just a wrapper); `urllib` ships with stdlib and is the most likely accidental dependency. **Pros:** comprehensive AST coverage; aligns with NFR-PRIV-1 "no outbound HTTP from framework process". **Cons:** `http.server` is the documented dashboard server runtime (Decision E1, `architecture.md:1267`) — must be exempted (see AC1/D2).
  - **D2:** stick to the epic's 4. **Cons:** an `import socket` in `src/sdlc/runtime/claude.py` to read a socket-like child pipe is undetected; future regressions silent.
  - **Recommended: D1** with exemptions per AC1/D2.

**And** **AC1/D2 — per-module exemption mechanism:** the dashboard server (Story 5.1, deferred-to-Epic-5) will need `http.server`. **Two-strategy choice:**
  - **D1 (Recommended for v1):** the static check operates only on the MODULES SHIPPING IN v1 — i.e. it does not yet need to exempt `http.server` because `dashboard/server.py` does not exist. When Epic 5 lands, the exemption is added via a per-file `# noqa: net — <reason>` marker (model on `_NOQA_PATTERN` in `check_no_hardcoded_secrets.py:35` — 10-char minimum reason). **Pros:** narrow scope; the noqa marker carries a free-text justification. **Cons:** Epic 5's first commit also touches this check.
  - **D2:** a frozen exempt-paths set `_EXEMPT_PATHS = frozenset({"src/sdlc/dashboard/server.py"})`. **Cons:** silent — the exemption is invisible at the violation site; future contributors see a clean import and assume `http.server` is unrestricted.
  - **Recommended: D1.** Document the `# noqa: net — <reason>` convention in the script's docstring even if no v1 module uses it.

**And** **AC1/D3 — AC1 is a pytest test, not a runtime "isolated CI" gate:** the epic wording says "network-isolated CI test (`tests/security/test_no_outbound_http.py`)". The AST static check **does NOT need network isolation to be valid** — the AST never opens sockets. **Two scopes:**
  - **D1 (Recommended for v1):** AC1's only deliverable is the AST static check at `tests/security/test_no_outbound_http.py` (and optionally a parallel `scripts/check_no_outbound_http.py`). **A literal CI sandbox-network-block (firewall rule) is not in scope for v1** — `architecture.md:1273` documents it as the long-term verification, but v1's static-check satisfies the auditable layer. Open `EPIC-2B-DEBT-NETWORK-ISOLATED-CI` for the future sandbox layer. **Pros:** v1 ships a real coverage gate with no flaky firewall-mocking; the AST check is deterministic. **Cons:** a runtime escape via `os.system("curl ...")` or `subprocess.Popen(["curl", ...])` is not caught by AC1 — but **IS caught by AC2** (the subprocess allow-list).
  - **D2:** also ship a `pytest-socket`-style network-blocker plugin in the test. **Cons:** flaky on macOS sandbox; mocking-not-prevention.
  - **Recommended: D1.** AC1 + AC2 together close the "no outbound HTTP" surface for v1 — the AST check catches Python-level network imports, the subprocess allow-list catches shell-out escapes.

### AC2 — Subprocess allow-list (AST static check)

**Given** the subprocess allow-list test (`tests/security/test_subprocess_allowlist.py`)
**When** static analysis runs
**Then** `subprocess.run(...)`, `subprocess.Popen(...)`, `subprocess.call(...)`, `subprocess.check_call(...)`, `subprocess.check_output(...)`, and `os.system(...)` invocations are limited to a **declared allow-list of `(module_path, binary_name)` tuples**
**And** the canonical v1 allow-list is: `runtime/claude.py` → `claude`; `cli/git.py` → `git`; `cli/gh.py` → `gh` (per `architecture.md:492, 794-795, 1105-1106, 1120-1125`)
**And** any module in `src/sdlc/` invoking subprocess functions but not on the allow-list, OR a listed module invoking a binary not declared for it, fails the static check with `SecurityError("module <path> invokes subprocess at <line> — not in allow-list, or binary differs from declared")`
**And** the failure cites the exact `file:line` of the offending call site
**And** the binary-name check inspects the first positional argument of the call: either a string literal (`["claude", ...]`'s `[0]`) or a `Name` node bound to a module-level constant (`_CLAUDE_BIN = "claude"`). A dynamic binary name (a parameter, an `os.environ.get(...)`) **fails** the check unless the module is on the allow-list AND the dynamic-name pattern is explicitly approved (see AC2/D3)

**And** **AC2/D1 — the v1 allow-list is broader than the epic literal — resolve before coding:** the epic lists 3 modules. **Current `src/sdlc/` subprocess callsites (verified by grep at story-creation time):**
  - `src/sdlc/runtime/claude.py` — `claude` ✓ (epic-listed)
  - `src/sdlc/cli/_compat_check.py` — `claude --version` (added by Story 2B.2 for the min-version gate)
  - `src/sdlc/cli/_paths.py` — `git` for repo-root discovery (or similar; verify)
  - `src/sdlc/hooks/runner.py` — `subprocess.run` for hook-script invocation (Story 2A.4)
  - `src/sdlc/claude_hooks/pre_tool_use.py` — `subprocess.run` for `sdlc hook-check` self-invocation (Story 2A.6)
  - `src/sdlc/cli/git.py` + `src/sdlc/cli/gh.py` — **do NOT currently exist** (planned per `architecture.md:794-795`; appear in v1 only when `pr-author` is wired — likely Epic 4 or post-Epic-2B)
  Pick ONE strategy:
  - **D1 (Recommended):** the allow-list is a **frozen registry** in `scripts/check_subprocess_allowlist.py` (and re-exported for the test). v1 entries:
    ```python
    _SUBPROCESS_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({
        ("src/sdlc/runtime/claude.py",         "claude"),
        ("src/sdlc/cli/_compat_check.py",      "claude"),   # 2B.2 min-version gate
        ("src/sdlc/cli/_paths.py",             "git"),       # repo-root discovery
        ("src/sdlc/hooks/runner.py",           "<dynamic>"), # hook-script binary is per-hook, see AC2/D3
        ("src/sdlc/claude_hooks/pre_tool_use.py", "sdlc"),   # self-invocation
    })
    ```
    **Pros:** matches reality; every binary on the list maps to a documented use-case in `architecture.md:1116-1125` or `2A.4 / 2A.6 / 2B.2`. **Cons:** the epic's 3-module list is amended — record this in the PR Change Log as an explicit deviation citing the verified callsites.
  - **D2:** keep the epic's 3-module allow-list literally and **migrate** all 5 current callsites either into the 3 listed modules or behind a single internal `subprocess_pool.py` wrapper (per `architecture.md:879` Decision A2). **Cons:** large refactor; out of scope for a v1 contract-test story; the binaries are still `claude` / `git` / `sdlc` regardless of which file holds the call. The 3-module wording is the architectural target post-refactor — the test should match v1 reality, not the target.
  - **Recommended: D1.** Open `EPIC-2B-DEBT-SUBPROCESS-WRAPPER-CONSOLIDATION` for the future D2 refactor; v1 ships D1.

**And** **AC2/D2 — `os.system` is also forbidden:** the epic lists `subprocess.run` + `subprocess.Popen`. **`os.system` is a strict superset of the risk** (shell-injectable, no argv array). Add `os.system` + `os.popen` + `os.spawn*` to the forbidden-function set with NO allow-listed callers. The current src/ tree has no `os.system` calls (verified by grep at story-creation); this is a guard against future regressions, not a remediation.

**And** **AC2/D3 — dynamic-binary callsites (e.g. `hooks/runner.py`) — explicit approval:** `src/sdlc/hooks/runner.py` invokes a per-hook binary (the binary path comes from `pyproject.toml [tool.sdlc.hooks] pre_write` registry — Story 2A.4). The binary name is NOT a literal. **Two strategies:**
  - **D1 (Recommended):** the allow-list registry has a sentinel `"<dynamic>"` marker (per AC2/D1) for `hooks/runner.py`; the static check treats `"<dynamic>"` as "this module's binary is intentionally dynamic — do not assert the literal, but flag if the call site adds new subprocess functions". This is the "approved exemption" path. **Pros:** explicit; future readers see the marker and understand. **Cons:** weaker than a literal — but the actual risk surface is `pyproject.toml`'s hook registry, which is the user's project, not the framework.
  - **D2:** refactor `hooks/runner.py` to call a single `_invoke_hook_binary(binary: str, ...)` wrapper and migrate the literal binary-name check to runtime against a `pyproject.toml`-loaded allow-list. **Cons:** out of scope; the hook binary is the user's choice, not the framework's.
  - **Recommended: D1.** Document the `"<dynamic>"` semantics in the script's docstring.

### AC3 — Dispatcher pauses + surfaces re-confirmation for destructive tool calls

**Given** a specialist's tool call returning a destructive operation (file delete, force-push, drop database)
**When** the dispatcher processes the tool call
**Then** the dispatcher pauses and surfaces a re-confirmation prompt to the user (CLI prompt)
**And** the re-confirmation logic is tested with fixtures for each destructive operation type
**And** if the user declines (any answer other than the literal canonical confirmation), the dispatcher aborts the dispatch with `DispatchError("destructive operation rejected by user at <stage>")` and emits an audit-trail journal entry (see AC3/D3)
**And** if the user accepts, the destructive tool call proceeds; the audit-trail journal entry records the acceptance

**And** **AC3/D1 — destructive-operation detection:** the source of truth for "this tool call is destructive" is the **specialist tool-call shape** (`AgentResult.tool_calls: tuple[Mapping[str, object], ...]` per `src/sdlc/runtime/abc.py:29`). Each tool call is a Mapping. **Choose the detection key:**
  - **D1 (Recommended):** introduce a frozen registry `_DESTRUCTIVE_TOOL_PATTERNS` mapping a `tool_calls` Mapping shape to a destructive category. v1 categories: `"file_delete"` (e.g. `tool_call["name"] == "Bash"` and the `command` field matches `/\brm\s+(-rf|-fr)\b/`), `"force_push"` (`"name" == "Bash"` + `command` matches `/git\s+push\s+(-f|--force|--force-with-lease)/`), `"drop_database"` (`"name" == "Bash"` + `command` matches `/\bDROP\s+(DATABASE|TABLE|SCHEMA)\b/i`). Registry lives in `src/sdlc/dispatcher/safety.py` (new module). **Pros:** explicit catalogue; testable as a unit; extensible per AC3/D2.
  - **D2:** rely on the specialist's frontmatter declaring `destructive: true` and have the dispatcher pause on every tool call from such a specialist. **Cons:** every Phase-3 specialist (`code-author`, `task-breaker`) emits some destructive calls and many safe ones; binary specialist-level flag is too coarse.
  - **Recommended: D1.** Open `EPIC-2B-DEBT-DESTRUCTIVE-CATALOGUE-EXPANSION` for adding more categories post-v1 (e.g. `kubectl delete`, `terraform destroy`, `aws s3 rb`).

**And** **AC3/D2 — re-confirmation prompt mechanism:** the dispatcher MUST pause synchronously and read a single line from the user's TTY. Use Python stdlib `input("...")` from `cli/_runtime_selection.py`-style helper; **do NOT** introduce `click.confirm` or other third-party prompt dependency (Story 1.x established no-deps-beyond-stdlib for CLI prompts; verify against `pyproject.toml [project] dependencies`). The canonical acceptance string is the literal word documented in the prompt — match exactly, case-sensitive, NOT a partial-match.

**And** **AC3/D3 — CR2B5-W1 destructive-token nonce + AC3 confirmation coupling:** CR2B5-W1 (`EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-ROTATION`) deferred a per-invocation nonce from Story 2B.5. **Couple it here:** the dispatcher generates a per-dispatch cryptographic nonce (`secrets.token_urlsafe(16)`) at the start of each `dispatch()`, INJECTS it into the prompt via the 2B.5 destructive-op block (`src/sdlc/dispatcher/prompts.py:_DESTRUCTIVE_OPS_BLOCK`) so it appears in the prompt text the agent sees, and the AC3 re-confirmation prompt requires the user to **echo the nonce** (not just answer "yes"). **Pros:** an attacker cannot smuggle a static "yes" into a prompt-injection payload because the nonce is fresh per dispatch. **Pick one:**
  - **D1 (Recommended):** implement the nonce coupling in this PR. Modify `src/sdlc/dispatcher/prompts.py` to accept an `_inject_destructive_nonce(prompt: str, nonce: str) -> str` helper; modify `phase1_prompt_builder` + `phase1_compound_prompt_builder` to thread it; the dispatcher passes the nonce into both the prompt build AND the re-confirmation prompt. Close `EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-ROTATION` (CR2B5-W1).
  - **D2:** keep CR2B5-W1 deferred; AC3's re-confirmation asks for "yes" only. **Cons:** the prompt-injection adversary path noted in `deferred-work.md:575` stays open in v1.
  - **Recommended: D1.** Closes a v1 security gap. Open `EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE` if the verification of "agent echoes the nonce in its acknowledgement before issuing the destructive tool call" is not feasible in v1 (likely deferred — agents do not currently structure their outputs to echo nonces).

**And** **AC3/D4 — CR2B5-W2 destructive-block scoping by specialist write-glob:** CR2B5-W2 (`EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-SCOPING`) deferred conditional injection from Story 2B.5. **Implement here:** the 2B.5 `_DESTRUCTIVE_OPS_BLOCK` is currently appended to **every** Phase-1 prompt regardless of the dispatched specialist's `write_globs` (`src/sdlc/dispatcher/prompts.py:273-279, 360-367`). For a read-only specialist (e.g. `product-strategist` with no `write_globs`), the block is noise that trains the model to ignore safety directives. Gate the block insertion on:
  - **D1 (Recommended):** the dispatched specialist's `write_globs` is non-empty AND any glob matches a destructive-target path predicate (e.g. any glob NOT starting with `_bmad-output/` is potentially destructive). Read the predicate via `Specialist.write_globs` (`src/sdlc/contracts/specialist_frontmatter.py`). Inject the destructive block only when the predicate is true. **Pros:** explicit; testable; closes CR2B5-W2.
  - **D2:** always inject (status quo per 2B.5). **Cons:** the deferred-work concerns remain unaddressed.
  - **Recommended: D1.** A unit test asserts: a product-strategist-shaped Specialist (read-only) does NOT receive the destructive block; a code-author-shaped Specialist (writes to `src/`) DOES receive it.

**And** **AC3/D5 — audit-trail journal kind:** the dispatcher pause + re-confirmation outcome MUST be audit-grade (PRD §344). Emit a `JournalEntry.kind="destructive_op_reconfirmed"` (or `"destructive_op_rejected"`) entry with payload `{"category": "<file_delete | force_push | drop_database>", "tool_call_excerpt": "<200-char>", "outcome": "accepted | rejected", "nonce": "<token>" }`. **Open-string kind** per ADR-028 (no contract edit); add a **§3 table row** to ADR-028 in the same PR.

### AC4 — Anti-tautology receipts (per static check + dispatcher pause)

**Given** ADR-026 §1 (anti-tautology requirement)
**When** the test suite runs
**Then** **three** load-bearing receipts are present:
  1. **AC1 receipt:** a deliberately-malformed fixture under `tests/security/fixtures/forbidden_net_import.py` (a Python file that imports `requests` at module level) is fed to the AC1 scan function and asserted to be flagged — proves the AST check **can** fail, not just pass vacuously on an empty repo
  2. **AC2 receipt:** a deliberately-out-of-allow-list fixture (a Python file calling `subprocess.run(["arbitrary", ...])` at module level placed at `tests/security/fixtures/forbidden_subprocess.py`) is fed to the AC2 scan function and asserted to be flagged
  3. **AC3 receipt:** the destructive-op dispatcher pause test injects a synthetic `tool_calls=({"name": "Bash", "command": "rm -rf /"}, )` AgentResult and asserts (a) the pause fires, (b) the user-input mock returning the wrong nonce raises `DispatchError("destructive operation rejected by user at <stage>")`, (c) the user-input mock echoing the correct nonce proceeds and emits the `destructive_op_reconfirmed` journal entry — proves all three of detect-pause-record actually fire
**And** the RED-before-GREEN ordering is visible in `git log --reverse` for each AC's public-surface logic (the scan functions + the dispatcher pause helper)

## Tasks / Subtasks

- [ ] **Task 1 — `scripts/check_no_outbound_http.py` + `tests/security/test_no_outbound_http.py`** (AC: 1)
  - [ ] Failing test (RED): AST-scan finds an `import requests` in a fixture file under `tests/security/fixtures/`
  - [ ] Implement scan: walk `ast.Import` + `ast.ImportFrom`; check `name` / `module` against `_FORBIDDEN_NETWORK_MODULES` (AC1/D1 list); skip `_EXEMPT_DIRS`; honour `# noqa: net — <reason>` per AC1/D2
  - [ ] `main(argv) -> int` returns 0 clean / 2 violations (matches `ERR_SECURITY`)
  - [ ] Test imports the script's scan function; asserts on the negative fixture AND on a clean fixture (positive coverage)
- [ ] **Task 2 — `scripts/check_subprocess_allowlist.py` + `tests/security/test_subprocess_allowlist.py`** (AC: 2)
  - [ ] Failing test (RED): scan finds a `subprocess.run(...)` call in a fixture module not on the allow-list
  - [ ] Implement scan: walk `ast.Call`; detect `subprocess.run` / `Popen` / `call` / `check_call` / `check_output` / `os.system` / `os.popen` / `os.spawn*`; for each, inspect the first positional arg (literal list or `Name` bound to a `_BIN` constant) and compare against `_SUBPROCESS_ALLOWLIST` (AC2/D1 frozen registry); honour `"<dynamic>"` sentinel (AC2/D3)
  - [ ] **CRITICAL:** verify the current `src/sdlc/` callsites at implementation time by grep (the AC2/D1 list is captured at story-creation time and MUST be re-verified) — if a callsite has changed, amend the registry in the PR
  - [ ] Self-test: assert the scan finds zero violations against `src/sdlc/` as it stands today — proves the registry is correct AND the scan works; if non-zero, root-cause before merging (either the registry is wrong or a callsite is genuinely off-list)
- [ ] **Task 3 — `src/sdlc/dispatcher/safety.py` + destructive-op detection + pause** (AC: 3)
  - [ ] Failing test (RED): a `tool_call` matching the `file_delete` pattern routes through `is_destructive(tool_call) -> bool` and returns `True`; an empty tool_call returns `False`
  - [ ] Implement `_DESTRUCTIVE_TOOL_PATTERNS` registry (AC3/D1) + `is_destructive(tool_call: Mapping[str, object]) -> tuple[bool, str | None]` returning `(True, category)` or `(False, None)`
  - [ ] Failing test (RED): a dispatch with a synthetic destructive AgentResult triggers the pause, asks for nonce echo, and DispatchError-rejects on a wrong nonce; accepts on the correct nonce
  - [ ] Implement `prompt_for_reconfirmation(nonce: str, category: str, tool_call_excerpt: str) -> bool` in `dispatcher/safety.py` (uses `input(...)` — AC3/D2)
  - [ ] Wire the pause into the dispatcher mainline (`src/sdlc/dispatcher/_panel_helpers.py` or `dispatcher/core.py`); emit the `destructive_op_reconfirmed` / `destructive_op_rejected` journal entry per AC3/D5 — ADR-028 §3 table row added in the same PR
- [ ] **Task 4 — CR2B5-W1 nonce coupling (closes `EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-ROTATION`)** (AC: 3)
  - [ ] Failing test (RED): the destructive block in the constructed Phase-1 prompt contains the dispatch's nonce (extracted from the dispatcher); the same nonce is required at the re-confirmation prompt
  - [ ] Modify `src/sdlc/dispatcher/prompts.py`: introduce `_inject_destructive_nonce(prompt: str, nonce: str) -> str`; thread the nonce parameter through `phase1_prompt_builder` + `phase1_compound_prompt_builder` (additive optional param, default `None` for backward compat, REQUIRED when destructive block is injected)
  - [ ] Dispatcher generates `nonce = secrets.token_urlsafe(16)` per dispatch; passes the same value into prompt build AND `prompt_for_reconfirmation`
  - [ ] Move CR2B5-W1 entry in `deferred-work.md` from open to closed; cross-reference this story
- [ ] **Task 5 — CR2B5-W2 destructive-block scoping (closes `EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-SCOPING`)** (AC: 3)
  - [ ] Failing test (RED): the constructed Phase-1 prompt for a read-only Specialist (empty `write_globs`) does NOT contain `_DESTRUCTIVE_OPS_BLOCK`; for a write-bearing Specialist it DOES
  - [ ] Implement the scoping predicate (AC3/D4 D1): `_should_inject_destructive_block(specialist: Specialist) -> bool` — non-empty write_globs AND at least one glob outside `_bmad-output/`
  - [ ] Modify `phase1_prompt_builder` + `phase1_compound_prompt_builder` to consult the predicate
  - [ ] Update the **2B.5 boundary-line scanner** (`scripts/check_boundary_line_presence.py`) and the **2B.5 destructive-token tests** if either depends on unconditional injection — verify before changing
  - [ ] Move CR2B5-W2 entry in `deferred-work.md` from open to closed; cross-reference this story
- [ ] **Task 6 — Anti-tautology receipts** (AC: 4)
  - [ ] Receipt #1: malformed fixture `tests/security/fixtures/forbidden_net_import.py` proves AC1 scan can fail
  - [ ] Receipt #2: malformed fixture `tests/security/fixtures/forbidden_subprocess.py` proves AC2 scan can fail
  - [ ] Receipt #3: dispatcher-pause test (Task 3) proves the destructive-op path actually fires + records
- [ ] **Task 7 — Quality gate + ADR-028 §3 table row**
  - [ ] If AC3/D5 emits `destructive_op_reconfirmed` / `destructive_op_rejected` open-string kinds: add the §3 table row in `docs/decisions/ADR-028-journal-kind-taxonomy.md` (kind name, before_hash/after_hash semantics, payload notes); cite this story in §Revision Log
  - [ ] `ruff format` + `ruff check` + `mypy --strict` + `pytest` + coverage ≥87 + `pre-commit run --all-files` + `mkdocs --strict` + wire-format snapshots (`scripts/freeze_wireformat_snapshots.py --check`)

## Dev Notes

### Relevant architecture patterns and constraints

- **`SecurityError` from Story 2B.5** — `src/sdlc/errors/base.py` (added by 2B.5). Code `ERR_SECURITY`, exit 2. **REUSE — do not redefine.** Both AC1 and AC2 raise this on static-check violations. The 2B.5 audit trail already registered it in `EXIT_CODE_MAP` (`errors/base.py`) and `_ERR_CODE_TO_EXIT_CODE` (`cli/output.py`).
- **Architecture `subprocess` allow-list** — `architecture.md:492` ("No `subprocess.run` outside `runtime/`, `cli/git.py`, `cli/gh.py` — these three are the only modules that may invoke external binaries.") + `architecture.md:1105-1106` ("`cli/` is the only module that may invoke external binaries other than `runtime/`. `cli/git.py` and `cli/gh.py` wrap subprocess calls; `runtime/claude.py` is the third permitted subprocess invoker."). **AC2/D1 documents the v1 deviation:** 5 actual callsites today vs the 3-module aspirational target. The story ships the v1-reality allow-list and tracks the consolidation refactor as debt (see AC2/D1).
- **Architecture `no outbound HTTP`** — `architecture.md:134` (Privacy table: "No outbound HTTP from framework process itself; all data local; zero telemetry in v1") + `architecture.md:717` (Pattern Enforcement: "No outbound HTTP from framework | network-isolated CI test (NFR-PRIV-1)") + `architecture.md:1125` ("**Network (outbound HTTP)** | **none** | **never originates from framework process** | verified by network-isolated CI test (NFR-PRIV-1)"). AC1 ships the **static-check half** for v1; the sandbox-firewall half is deferred per AC1/D3.
- **Static-check script pattern** — `scripts/check_no_hardcoded_secrets.py` (100 LOC) is the canonical model. Key features:
  - `_REPO_ROOT = Path(__file__).parent.parent` (file lives at `scripts/`)
  - `_EXEMPT_DIRS = frozenset({"tests", "scripts", "_bmad", "_bmad-output", ".claude", "_site", "docs"})` — re-use this set verbatim in the new scripts
  - `_SELF = Path(__file__).resolve()` — exempt the scanner from itself
  - `_NOQA_PATTERN = re.compile(r"#\s*noqa:\s*secret(?:\s*(?:—|--)\s*(.{10,}))?")` — model AC1/D2 `# noqa: net — <reason>` and AC2 `# noqa: subprocess — <reason>` on this
  - `_scan_file(path) -> list[(lineno, col, msg)]` + `main(argv) -> int` returning `0 if clean else <exit_code>`
- **2B.5 scanner pattern for ast-walk discipline** — `scripts/check_boundary_line_presence.py` (post-review state, all P1-P21 patches landed). Specifically:
  - Use `ast.walk(tree)` (NOT `tree.body`) — catches ClassDef nesting, closures, AsyncFunctionDef (2B.5 P1)
  - Handle both `ast.Assign` AND `ast.AnnAssign` for typed assignments (2B.5 P7)
  - Fail-closed on `OSError` / `UnicodeDecodeError` / `SyntaxError` — raise `SecurityError`, do not return clean (2B.5 P9)
  - Module-top `sys.path.insert` taints importers — own `sys.path` mutation in `tests/security/conftest.py`, NOT in the script (2B.5 P8). Re-use 2B.5's `tests/security/conftest.py` pattern.
- **Current `src/sdlc/` subprocess callsites (verified by grep at story-creation 2026-05-28):**
  - `src/sdlc/runtime/claude.py:39, 50, 52, 183-187, 201` — `Popen`, `TimeoutExpired`; binary = `claude`
  - `src/sdlc/cli/_compat_check.py:155, 167, 173` — `subprocess.run`; binary = `claude --version`
  - `src/sdlc/cli/_paths.py:26, 34` — `subprocess.run`; binary likely `git` (verify before coding)
  - `src/sdlc/hooks/runner.py:103, 112` — `subprocess.run`; binary = `<dynamic>` (hook-registry-driven)
  - `src/sdlc/claude_hooks/pre_tool_use.py:134, 141` — `subprocess.run`; binary = `sdlc` (self-invocation for `hook-check`)
- **`AgentResult.tool_calls` shape** — `src/sdlc/runtime/abc.py:29`: `tool_calls: tuple[Mapping[str, object], ...] = Field(default_factory=tuple)`. Each call is a Mapping; the v1 shape from `ClaudeAIRuntime` follows the Claude CLI JSON envelope. AC3/D1 detection uses the `name` + `command` / `path` / `query` fields (Anthropic-tool-spec adjacent — verify against `runtime/claude.py:_parse_claude_stdout` output at implementation time).
- **2B.5 destructive-op block** — `src/sdlc/dispatcher/prompts.py:25-36`: `_DESTRUCTIVE_OPS_BLOCK` with three static literals (`RECONFIRM_FILE_DELETE`, `RECONFIRM_FORCE_PUSH`, `RECONFIRM_DROP_DATABASE`). Appended unconditionally to every Phase-1 prompt at `prompts.py:273-279, 360-367`. **Task 4 modifies these.**
- **ADR-028 journal-kind taxonomy** — `docs/decisions/ADR-028-journal-kind-taxonomy.md` (prep-sprint DOC1). Open-string `JournalEntry.kind` posture; new kinds require a §3 table row + §Revision Log entry in the same PR. AC3/D5 emits 2 new open-string kinds (`destructive_op_reconfirmed`, `destructive_op_rejected`) — no contract edit; just the §3 table row.

### Module boundary guardrail (READ — primary cause of RED-checkpoint failures)

`scripts/module_boundary_table.py`: relevant rows for this story:
- **`dispatcher/`** may import `errors`, `contracts`, `ids`, `concurrency`, `journal`, `state`, `hooks`, `runtime`, `telemetry`, `signoff`, `engine`. **Adding `dispatcher/safety.py` is on-side.**
- **`hooks/`** may import `errors`, `contracts`, `state`, `journal`, `ids` (per `architecture.md:1065`). Hooks do NOT import dispatcher — if Task 3's pause helper needs hooks integration, the dispatcher orchestrates, hooks don't call back into dispatcher.
- **`runtime/`** is leaf-most (per 2B.1) — `runtime/` may not import dispatcher. The destructive-op detection lives in `dispatcher/`, not `runtime/`.
- **`scripts/`** is unrestricted (lives outside the src/ module-boundary table); the static-check scripts can import what they need.

### Project Structure Notes

- **New (the bulk of the work):**
  - `scripts/check_no_outbound_http.py` (AC1) — model on `check_no_hardcoded_secrets.py`
  - `scripts/check_subprocess_allowlist.py` (AC2) — model on `check_no_hardcoded_secrets.py`
  - `tests/security/test_no_outbound_http.py` (AC1) — pytest CI gate; imports the script's scan function
  - `tests/security/test_subprocess_allowlist.py` (AC2) — pytest CI gate; imports the script's scan function
  - `tests/security/fixtures/forbidden_net_import.py` (AC4 Receipt #1)
  - `tests/security/fixtures/forbidden_subprocess.py` (AC4 Receipt #2)
  - `src/sdlc/dispatcher/safety.py` (AC3) — `_DESTRUCTIVE_TOOL_PATTERNS` registry, `is_destructive`, `prompt_for_reconfirmation`
  - `tests/unit/dispatcher/test_safety.py` (AC3 unit tests)
  - `tests/integration/test_dispatcher_destructive_op.py` (AC3 integration — synthetic AgentResult, mocked TTY, asserts journal entry)
- **Modified:**
  - `src/sdlc/dispatcher/prompts.py` (Task 4 nonce coupling, Task 5 scoping predicate)
  - `src/sdlc/dispatcher/_panel_helpers.py` or `dispatcher/core.py` (Task 3 pause-wiring + nonce generation)
  - `_bmad-output/implementation-artifacts/deferred-work.md` (close CR2B5-W1 + CR2B5-W2 entries)
  - `docs/decisions/ADR-028-journal-kind-taxonomy.md` (AC3/D5 §3 table row + §Revision Log)
  - **Re-verify and possibly update** `scripts/check_boundary_line_presence.py` + `tests/security/test_boundary_line_presence.py` if Task 5 scoping breaks any 2B.5 unconditional-injection assumption
- **Layer 2 sibling coordination:** **2B.3 (`tests/integration/test_abstraction_adequacy.py`)** is the other Layer 2 story; it does NOT add `subprocess.*` callsites in `src/` — no conflict with this story's AC2 allow-list. Both merge independently; if 2B.6 merges first, 2B.3 rebases (no expected change).
- **Worktree:** `epic-2b/2b-6-tool-safety` (owner: Winston, DAG §5). Per CONTRIBUTING §3 — one branch, linear FF-merge to `main`; rebase if 2B.3 merges first.
- **Snapshot count:** no wire-format contract touched. `scripts/freeze_wireformat_snapshots.py --check` MUST stay green; ADR-024 snapshot count unchanged. `AgentResult.tool_calls` shape is consumed (not modified) by `dispatcher/safety.py`.

### Testing standards summary

- TDD-first (CONTRIBUTING §2): tests-first commit ordering visible in `git log --reverse` for each AC's scan function and for `dispatcher/safety.py:is_destructive` + `prompt_for_reconfirmation` (all four are public-surface).
- Anti-tautology (ADR-026 §1): AC4 mandates 3 receipts — one per AC. A static check that scans only the existing src/ tree (which currently has zero forbidden imports) would pass tautologically; the negative fixtures under `tests/security/fixtures/` are mandatory.
- Test org (`architecture.md:682-701`): `tests/security/` is the established home (2B.4 corpus + 2B.5 boundary-line scanner already there); `tests/unit/dispatcher/test_safety.py` mirrors src; `tests/integration/test_dispatcher_destructive_op.py` for the dispatcher+TTY end-to-end pause.
- Quality gate (CONTRIBUTING §1): `ruff format` + `ruff check` + `mypy --strict` + `pytest` + coverage ≥87 + `pre-commit run --all-files` + `mkdocs --strict` + wire-format snapshots.
- `mypy --strict` on AST-walking code: `ast.Import` / `ast.ImportFrom` / `ast.Call` / `ast.Attribute` / `ast.Name` need careful annotations; no bare `type: ignore`.
- TTY-mocking pattern for AC3 integration test: use `monkeypatch.setattr("builtins.input", lambda prompt: <canned>)` or `capsys` + `monkeypatch.setattr("sys.stdin", io.StringIO(...))`. Verify which is idiomatic in this repo (`grep -r "monkeypatch.setattr.*input" tests/`).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-2B.6] — AC source (lines 1582-1604)
- [Source: _bmad-output/planning-artifacts/architecture.md] — §134 (Privacy: no outbound HTTP), §492 (subprocess allow-list), §717 (pattern enforcement), §1105-1106 (`cli/` is the only external-binary invoker except `runtime/`), §1116-1125 (External Integration Points table)
- [Source: docs/sprints/epic-2b-dag.md] — §3 Layer 2 (2B.3 + 2B.6), §5 worktree (owner: Winston), §7 — 2B.7 (threat-model docs) depends on 2B.6
- [Source: scripts/check_no_hardcoded_secrets.py] — canonical static-check script pattern (100 LOC)
- [Source: scripts/check_boundary_line_presence.py] — 2B.5 post-review state; AST-walk + ast.AnnAssign + fail-closed disciplines
- [Source: tests/security/conftest.py] — 2B.5 pattern for owning `sys.path` mutation outside the script
- [Source: src/sdlc/errors/base.py] — `SecurityError` reused from 2B.5 (code `ERR_SECURITY`, exit 2)
- [Source: src/sdlc/runtime/abc.py] — `AgentResult.tool_calls` shape (line 29)
- [Source: src/sdlc/runtime/claude.py] — `_parse_claude_stdout` envelope shape (lines 49-50 post-2B.1-review)
- [Source: src/sdlc/dispatcher/prompts.py] — `_DESTRUCTIVE_OPS_BLOCK` (lines 25-36), Phase-1 builder injection sites (lines 273-279, 360-367)
- [Source: src/sdlc/hooks/runner.py] — `subprocess.run` callsite (line 103) — AC2 `<dynamic>` allow-list entry
- [Source: src/sdlc/cli/_compat_check.py] — `claude --version` subprocess.run (line 155) — Story 2B.2
- [Source: src/sdlc/claude_hooks/pre_tool_use.py] — `sdlc hook-check` self-invocation (line 134) — Story 2A.6
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — CR2B5-W1 (line 575 — destructive-token rotation) + CR2B5-W2 (line 576 — destructive-token scoping); both close in this story
- [Source: _bmad-output/implementation-artifacts/2b-5-automated-boundary-line-presence-test.md] — `done`; 2B.5 destructive-op block + the deferred items this story absorbs
- [Source: _bmad-output/implementation-artifacts/2b-1-claudeairuntime-implementation-subprocess-management.md] — `done`; `runtime/claude.py` is the canonical `claude` subprocess invoker
- [Source: docs/decisions/ADR-028-journal-kind-taxonomy.md] — §3 open-string kind taxonomy; AC3/D5 adds 2 rows
- [Source: docs/decisions/ADR-026.md §1] — anti-tautology receipt requirement (AC4)
- [Source: CONTRIBUTING.md] — §1 quality gate, §2 TDD-first, §3 worktree workflow

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

### Change Log

## Review Findings

(Populated after `bmad-code-review` runs against the post-implementation branch.)
