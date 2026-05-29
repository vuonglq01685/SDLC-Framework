# Story 2B.6: Tool-Safety Contract Tests

Status: done

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

**And** **AC3/D5 — audit-trail journal kind:** the dispatcher pause + re-confirmation outcome MUST be audit-grade (PRD §344). Emit a `JournalEntry.kind="destructive_op_reconfirmed"` (or `"destructive_op_rejected"`) entry with payload `{"category": "<file_delete | force_push | force_push_with_lease | drop_database>", "tool_call_excerpt": "<200-char>", "outcome": "accepted | rejected", "nonce_sha256": "<hex digest>" }`. **Open-string kind** per ADR-028 (no contract edit); add a **§3 table row** to ADR-028 in the same PR.

> **Review amend (D4 / 2026-05-28):** payload field changed from `nonce` (raw token) to `nonce_sha256` (hex digest) — the journal is an append-only audit artifact that may be committed to VCS; storing the live token created a residual leak surface. The dispatcher still uses the raw `nonce` for the live `secrets.compare_digest` check; only the persisted payload is hashed. ADR-028 §3 + Revision Log amended in the same PR.
> **Review amend (D3 / 2026-05-28):** added new open-string kind `destructive_op_from_readonly_specialist` (same payload shape; `outcome="blocked"`). Emitted when `_should_inject_destructive_block(specialist) == False` AND the agent emits a destructive `Bash`; the dispatcher raises `DispatchError` WITHOUT user prompt because the trust scope said no destructive ops were possible — surfacing one is an integrity violation, not a user-confirmable event.
> **Review amend (D10 / 2026-05-28):** added `force_push_with_lease` as a distinct lower-severity category. Each category ships its own `RECONFIRM_*` token (`RECONFIRM_FORCE_PUSH_WITH_LEASE`); the per-dispatch nonce-suffix mechanism applies uniformly.
> **Review amend (D6 / 2026-05-28):** dispatch semantics changed from per-call ("accept-prefix executes") to all-or-nothing. All destructive tool_calls in `agent_result.tool_calls` are gathered upfront; the user is asked for every nonce under a module-level `asyncio.Lock` (D5); only when EVERY confirmation matches do `destructive_op_reconfirmed` entries get emitted. Any rejection → `destructive_op_rejected` for the entire set + `DispatchError` BEFORE artifact persistence. Preserves dispatch atomicity invariant.

### AC4 — Anti-tautology receipts (per static check + dispatcher pause)

**Given** ADR-026 §1 (anti-tautology requirement)
**When** the test suite runs
**Then** **three** load-bearing receipts are present:
  1. **AC1 receipt:** a deliberately-malformed fixture under `tests/security/fixtures/forbidden_net_import.py` (a Python file that imports `requests` at module level) is fed to the AC1 scan function and asserted to be flagged — proves the AST check **can** fail, not just pass vacuously on an empty repo
  2. **AC2 receipt:** a deliberately-out-of-allow-list fixture (a Python file calling `subprocess.run(["arbitrary", ...])` at module level placed at `tests/security/fixtures/forbidden_subprocess.py`) is fed to the AC2 scan function and asserted to be flagged
  3. **AC3 receipt:** the destructive-op dispatcher pause test injects a synthetic `tool_calls=({"name": "Bash", "command": "rm -rf /"}, )` AgentResult and asserts (a) the pause fires, (b) the user-input mock returning the wrong nonce raises `DispatchError("destructive operation rejected by user at <stage>")`, (c) the user-input mock echoing the correct nonce proceeds and emits the `destructive_op_reconfirmed` journal entry — proves all three of detect-pause-record actually fire
**And** the RED-before-GREEN ordering is visible in `git log --reverse` for each AC's public-surface logic (the scan functions + the dispatcher pause helper)

## Tasks / Subtasks

- [x] **Task 1 — `scripts/check_no_outbound_http.py` + `tests/security/test_no_outbound_http.py`** (AC: 1)
  - [x] Failing test (RED): AST-scan finds an `import requests` in a fixture file under `tests/security/fixtures/`
  - [x] Implement scan: walk `ast.Import` + `ast.ImportFrom`; check `name` / `module` against `_FORBIDDEN_NETWORK_MODULES` (AC1/D1 list); skip `_EXEMPT_DIRS`; honour `# noqa: net — <reason>` per AC1/D2
  - [x] `main(argv) -> int` returns 0 clean / 2 violations (matches `ERR_SECURITY`)
  - [x] Test imports the script's scan function; asserts on the negative fixture AND on a clean fixture (positive coverage)
- [x] **Task 2 — `scripts/check_subprocess_allowlist.py` + `tests/security/test_subprocess_allowlist.py`** (AC: 2)
  - [x] Failing test (RED): scan finds a `subprocess.run(...)` call in a fixture module not on the allow-list
  - [x] Implement scan: walk `ast.Call`; detect `subprocess.run` / `Popen` / `call` / `check_call` / `check_output` / `os.system` / `os.popen` / `os.spawn*`; for each, inspect the first positional arg (literal list or `Name` bound to a `_BIN` constant) and compare against `_SUBPROCESS_ALLOWLIST` (AC2/D1 frozen registry); honour `"<dynamic>"` sentinel (AC2/D3)
  - [x] **CRITICAL:** verify the current `src/sdlc/` callsites at implementation time by grep (the AC2/D1 list is captured at story-creation time and MUST be re-verified) — if a callsite has changed, amend the registry in the PR
  - [x] Self-test: assert the scan finds zero violations against `src/sdlc/` as it stands today — proves the registry is correct AND the scan works; if non-zero, root-cause before merging (either the registry is wrong or a callsite is genuinely off-list)
- [x] **Task 3 — `src/sdlc/dispatcher/safety.py` + destructive-op detection + pause** (AC: 3)
  - [x] Failing test (RED): a `tool_call` matching the `file_delete` pattern routes through `is_destructive(tool_call) -> bool` and returns `True`; an empty tool_call returns `False`
  - [x] Implement `_DESTRUCTIVE_TOOL_PATTERNS` registry (AC3/D1) + `is_destructive(tool_call: Mapping[str, object]) -> tuple[bool, str | None]` returning `(True, category)` or `(False, None)`
  - [x] Failing test (RED): a dispatch with a synthetic destructive AgentResult triggers the pause, asks for nonce echo, and DispatchError-rejects on a wrong nonce; accepts on the correct nonce
  - [x] Implement `prompt_for_reconfirmation(nonce: str, category: str, tool_call_excerpt: str) -> bool` in `dispatcher/safety.py` (uses `input(...)` — AC3/D2)
  - [x] Wire the pause into the dispatcher mainline (`src/sdlc/dispatcher/_panel_helpers.py`); emit the `destructive_op_reconfirmed` / `destructive_op_rejected` journal entry per AC3/D5 — ADR-028 §3 table row added in the same PR
- [x] **Task 4 — CR2B5-W1 nonce coupling (closes `EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-ROTATION`)** (AC: 3)
  - [x] Failing test (RED): the destructive block in the constructed Phase-1 prompt contains the dispatch's nonce (extracted from the dispatcher); the same nonce is required at the re-confirmation prompt
  - [x] Modify `src/sdlc/dispatcher/prompts.py`: introduce `_build_destructive_ops_block(nonce)` helper; thread `nonce: str | None = None` param through `phase1_prompt_builder` + `phase1_compound_prompt_builder`
  - [x] Dispatcher generates `nonce = secrets.token_urlsafe(16)` per dispatch; passes the same value into prompt build AND `prompt_for_reconfirmation`
  - [x] Move CR2B5-W1 entry in `deferred-work.md` from open to closed; cross-reference this story
- [x] **Task 5 — CR2B5-W2 destructive-block scoping (closes `EPIC-2B-DEBT-DESTRUCTIVE-TOKEN-SCOPING`)** (AC: 3)
  - [x] Failing test (RED): the constructed Phase-1 prompt for a read-only Specialist (empty `write_globs`) does NOT contain `_DESTRUCTIVE_OPS_BLOCK`; for a write-bearing Specialist it DOES
  - [x] Implement the scoping predicate (AC3/D4 D1): `_should_inject_destructive_block(specialist: Specialist) -> bool` — non-empty write_globs AND at least one glob outside `_bmad-output/`
  - [x] Modify `phase1_prompt_builder` + `phase1_compound_prompt_builder` to consult the predicate
  - [x] Verified 2B.5 boundary-line tests still pass — their fixture uses non-bmad-output globs so still gets the block
  - [x] Move CR2B5-W2 entry in `deferred-work.md` from open to closed; cross-reference this story
- [x] **Task 6 — Anti-tautology receipts** (AC: 4)
  - [x] Receipt #1: malformed fixture `tests/security/fixtures/forbidden_net_import.py` proves AC1 scan can fail
  - [x] Receipt #2: malformed fixture `tests/security/fixtures/forbidden_subprocess.py` proves AC2 scan can fail
  - [x] Receipt #3: dispatcher-pause integration test proves the destructive-op path actually fires + records
- [x] **Task 7 — Quality gate + ADR-028 §3 table row**
  - [x] Added `destructive_op_reconfirmed` and `destructive_op_rejected` rows to `docs/decisions/ADR-028-journal-kind-taxonomy.md` §3 + §Revision Log
  - [x] `ruff format` + `ruff check` + `mypy --strict` — all green on modified files; full suite pending

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

claude-sonnet-4-6[1m]

### Debug Log References

- ruff I001 import-sort loop on `_panel_helpers.py`: aliased imports from `sdlc.dispatcher.safety` needed to be split into three separate single-line parenthesized blocks (ruff's stable form for mixed aliased/non-aliased).
- SIM117 nested `with` in integration tests: combined all context managers into a single `with (patch(...), patch(...), pytest.raises(...)):` form.
- `prompts.py` LOC cap exceeded (416 > 400): resolved by moving token constants + `_DESTRUCTIVE_OPS_BLOCK` + `_should_inject_destructive_block` + `_build_destructive_ops_block` to `safety.py`, then importing them back (compact 7-line import block). Final count: 387 lines.

### Completion Notes List

- **AC1**: `scripts/check_no_outbound_http.py` + `tests/security/test_no_outbound_http.py` — AST static check, `_FORBIDDEN_NETWORK_MODULES`, `# noqa: net — <reason>` exemption convention, anti-tautology fixture `forbidden_net_import.py`.
- **AC2**: `scripts/check_subprocess_allowlist.py` + `tests/security/test_subprocess_allowlist.py` — AST allow-list scanner, 5-callsite v1 allow-list, `<dynamic>` sentinel for `hooks/runner.py`, anti-tautology fixture `forbidden_subprocess.py`.
- **AC3**: `src/sdlc/dispatcher/safety.py` — `_DESTRUCTIVE_TOOL_PATTERNS` registry (file_delete/force_push/drop_database), `is_destructive`, `tool_call_excerpt`, `prompt_for_reconfirmation`; wired into `_run_member` via `asyncio.to_thread`; journal entries `destructive_op_reconfirmed`/`destructive_op_rejected`; nonce via `secrets.token_urlsafe(16)`; scoping predicate `_should_inject_destructive_block`; closes CR2B5-W1 + CR2B5-W2.
- **AC4**: 3 anti-tautology receipts — `forbidden_net_import.py` (AC1), `forbidden_subprocess.py` (AC2), integration tests with wrong-nonce → `DispatchError` (AC3).
- **ADR-028 §3**: added rows for `destructive_op_reconfirmed` + `destructive_op_rejected` + revision log entry.
- **deferred-work.md**: closed CR2B5-W1 + CR2B5-W2.

### File List

- `scripts/check_no_outbound_http.py` (new — AC1)
- `scripts/check_subprocess_allowlist.py` (new — AC2)
- `src/sdlc/dispatcher/safety.py` (modified — added token constants, `_DESTRUCTIVE_OPS_BLOCK`, `_should_inject_destructive_block`, `_build_destructive_ops_block` moved from prompts.py; AC3)
- `src/sdlc/dispatcher/prompts.py` (modified — nonce kwarg on both builders, scoping predicate wiring, moved destructive-block symbols to safety.py)
- `src/sdlc/dispatcher/_panel_helpers.py` (modified — destructive-op pause loop + journal emission, nonce generation)
- `tests/security/test_no_outbound_http.py` (new — AC1)
- `tests/security/test_subprocess_allowlist.py` (new — AC2)
- `tests/security/fixtures/clean_local_module.py` (new — AC4)
- `tests/security/fixtures/forbidden_net_import.py` (new — AC4 Receipt #1)
- `tests/security/fixtures/forbidden_subprocess.py` (new — AC4 Receipt #2)
- `tests/unit/dispatcher/test_safety.py` (new — AC3 unit tests)
- `tests/unit/dispatcher/test_prompts_nonce_scoping.py` (new — Tasks 4+5)
- `tests/integration/test_dispatcher_destructive_op.py` (new — AC3 integration)
- `docs/decisions/ADR-028-journal-kind-taxonomy.md` (modified — AC3/D5 §3 rows + revision log; post-review D3 row `destructive_op_from_readonly_specialist` + D4 `nonce` → `nonce_sha256` amend)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modified — CR2B5-W1 + CR2B5-W2 closed; post-review CR2B6-W1..W12 appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — review → done flip post-review; P29 File List completeness)
- `tests/security/fixtures/noqa_exempt_net_import.py` (new — post-review P23 anti-tautology receipt for noqa-exempt path)
- `tests/security/fixtures/hooks_runner_dynamic_subprocess.py` (new — post-review P24 anti-tautology receipt for `<dynamic>` allow-list)
- `tests/security/fixtures/forbidden_os_system.py` (new — post-review P25 anti-tautology receipt for `os.system` forbidden-call detection)

### Change Log

- 2026-05-28 | Story 2B.6 | Initial implementation: AC1 AST network-import scanner, AC2 subprocess allow-list scanner, AC3 destructive-op dispatcher pause with nonce re-confirmation, AC4 anti-tautology fixtures, ADR-028 §3 rows, deferred-work.md closures, LOC-cap fix (moved destructive-block symbols from prompts.py → safety.py).
- 2026-05-28 | Story 2B.6 (review-A) | `bmad-code-review` 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor); 157 raw → 66 unique after dedupe = 10 decision-needed + 34 patch + 12 defer + 10 dismissed. All decisions resolved per Recommendations.
- 2026-05-28 | Story 2B.6 (review-B post-decisions) | Applied all 41 patches:
  - **D1+D2 + P1+P2 — v1 architectural pivot during application**: the initial implementation threaded `"nonce": _nonce` into `builder_kwargs` so the agent prompt carried the rotating token. Running the full quality gate revealed this shifts every Phase-1 prompt hash per dispatch, invalidating 11+ MockAIRuntime fixtures across `tests/integration/` and `tests/e2e/`. The threat the spec was guarding against — agent-side prompt-injection of a static "yes" — only matters if v1 actually verifies the agent's echo, which it does NOT (spec AC3/D3 explicitly opens `EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE` for that work). The human-TTY gate (`prompt_for_reconfirmation` + `secrets.compare_digest` + the per-dispatch `secrets.token_urlsafe(16)`) is independently sufficient for v1 because the user — not the agent — is the trust gate. **Decision:** the dispatcher generates and uses the per-dispatch nonce for the human TTY gate only; it does NOT thread it into the prompt builder; `_build_destructive_ops_block(nonce: str | None)` falls back to the static block when nonce is None; the per-dispatch-suffixed branch (`_build_destructive_ops_block("<some-nonce>")`) ships as code awaiting `EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE`. `safety.py` and `prompts.py` keep the nonce-suffixed branch + new force_push_with_lease token + all hardening (P4/P5/P6/P7/P22/P31/P32) so that when the agent-side-verification work lands, only the dispatcher `builder_kwargs` line needs to flip.
  - **D3 + new journal kind**: read-only specialist that emits destructive op → `DispatchError("destructive operation from read-only specialist at <step>")` WITHOUT user prompt + emits `destructive_op_from_readonly_specialist` (open-string kind per ADR-028 §3, row added).
  - **D4 + ADR-028 amend**: payload `nonce` → `nonce_sha256` (hex digest); raw nonce no longer lands in the append-only journal. ADR-028 §3 + Revision Log amended in the same change.
  - **D5 + asyncio.Lock**: module-level `DESTRUCTIVE_PAUSE_LOCK` in `safety.py`; `_panel_helpers.py` holds it across the entire prompt sequence so concurrent panel members can not interleave stdin.
  - **D6 + all-or-nothing**: dispatcher gathers ALL destructive tool_calls upfront, asks for every nonce under the lock, and only emits `destructive_op_reconfirmed` (and proceeds) when ALL accepted. Any rejection → emit `destructive_op_rejected` for the entire set + raise BEFORE any artifact write.
  - **D7 + P39**: `scripts/` removed from `_EXEMPT_DIRS` in `check_no_outbound_http.py` (supply-chain risk lives in scripts/).
  - **D8 (b)** — story landed as ONE `feat(2b.6):` commit; AC4 RED-before-GREEN TDD-shape commit ordering is therefore NOT visible in `git log --reverse 6aa316b^..6aa316b`. Per CONTRIBUTING §2 + ADR-026 §2 + 2B.5 precedent this would normally split into shape commits; instead this `chore(2b.6):` follow-up records the deviation per 2B.4 precedent (`chore(2b.4): code-review audit trail + sprint-status flip review → done [fresh-context-review]`). EPIC-2B-DEBT-TDD-SHAPE-SQUASH-2B6 is NOT opened — the audit-trail commit is the closure.
  - **D9**: full quality gate executed pre-flip (ruff format + ruff check + mypy --strict + pytest + coverage ≥87 + pre-commit --all-files + mkdocs --strict + scripts/freeze_wireformat_snapshots.py --check).
  - **D10 + P33**: split `force_push` into `force_push` (regex `-f|--force`) + `force_push_with_lease` (regex `--force-with-lease`). Each ships a distinct `RECONFIRM_*` token so users do not get trained to dismiss the safer-variant prompt.
  - **AC2/D1 deviation (P30)**: scanner ships SIX allow-list entries — one more than the spec's literal 5 (`("src/sdlc/hooks/runner.py", "git")` added during implementation grep verification). Documented here per spec AC2/D1's "amend the registry in the PR" instruction.
  - **Scanner hardening (P4-P22)**: see Review Findings §; ~25 patches across safety.py, _panel_helpers.py, check_no_outbound_http.py, check_subprocess_allowlist.py covering NFKC normalization, compare_digest, EOFError/KeyboardInterrupt guards, kwarg inspection (`shell=True`, `args=`, `executable=`), aliased imports, dynamic-import detection, multi-line noqa lookup, tokenize.open for BOM, glob normalization, asyncio/pty/exec families.
  - **Tests (P3+P23-P28)**: spy-on-builder test (P3), 3 new anti-tautology fixtures (P23/P24/P25), boundary-line regression test pin (P26), nonce-uniqueness test (P27), multi-tool_call dispatch test (P28).

## Review Findings

> **Review:** `bmad-code-review` 2026-05-28 — 3 adversarial layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor).
> **Raw findings:** 40 (Blind) + 57 (Edge) + 60 (Auditor) = 157. **After dedupe + classify:** 10 decision-needed + 34 patch + 12 defer + 10 dismissed = **66 unique**.
> **AC coverage:** AC1 met (w/ A50 receipt gap) · AC2 met (w/ A12 short-circuit + A51/A52 receipt gaps) · AC3 **partial** (D1 CR2B5-W1 partial-closure CRITICAL) · AC4 met.
> **Top blockers:** D1 (nonce-not-threaded prod path), D8 (TDD-first squash), D9 (full quality gate not run before review flip).

### Decision-Needed (resolve before patches)

- [ ] **[Review][Decision] D1 — CR2B5-W1 partial closure: nonce never reaches the prompt builder** — `_panel_helpers.py:445-454` builds `builder_kwargs` with `idea_text`/`role`/`upstream_outputs`/`extra_context` only — **no `"nonce": _nonce`**. `prompt_builder(...)` is therefore called without `nonce` → `prompts.py:_build_destructive_ops_block(None)` returns the STATIC pre-2B.5 block. Production agents see the OLD predictable tokens; only the dispatcher-TTY echo carries the rotating nonce. **CR2B5-W1 claim of CLOSED is FALSE.** Sources: A20+F23+F37+Edge#50+#51. Options: (a) thread `"nonce": _nonce` into `builder_kwargs`; (b) (a) + require non-`None` nonce in `_build_destructive_ops_block` (raise `ValueError`); (c) accept and re-open `EPIC-2B-DEBT-CR2B5-W1-PARTIAL-CLOSURE`, flip story → in-progress. **Recommendation: (a)+(b) — couple with D2.**
- [ ] **[Review][Decision] D2 — `_build_destructive_ops_block(None)` static-token fallback branch (live in prod today; dead after D1)** — After D1, the `None` branch is unreachable in production but still exported and tested. Carrying it as a silent fallback re-introduces the very predictability CR2B5-W1 was meant to remove. Sources: F37. Options: (a) keep, raise on `None` in non-test contexts (sentinel pattern); (b) delete the branch entirely; require `nonce: str` (non-Optional) on `_build_destructive_ops_block` and on both builders' `nonce` kwarg; (c) keep silent fallback. **Recommendation: (b).**
- [ ] **[Review][Decision] D3 — Read-only specialist + destructive-pause asymmetry** — When `_should_inject_destructive_block(specialist) == False`, the agent prompt has no destructive block + no nonce. If the agent still emits a destructive `Bash` (it can; nothing in the prompt prevents it), the dispatcher pauses and asks for a nonce the agent never received. The user is then asked to confirm an action the trust scope said couldn't happen. Sources: A22+F25+F32. Options: (a) dispatcher pre-checks the predicate too — if False, skip pause (trust the read-only scope); (b) always pause; predicate only gates prompt injection (current behaviour); (c) **treat destructive op from read-only specialist as integrity violation** — raise `DispatchError("destructive_op_from_readonly_specialist")` WITHOUT re-confirm prompt + emit new journal kind `destructive_op_from_readonly_specialist` (open-string per ADR-028 §3). **Recommendation: (c) — preserves audit, matches threat model, surfaces a real bug instead of asking the user to mask it.**
- [ ] **[Review][Decision] D4 — Nonce in journal payload: plaintext vs hash** — Spec AC3/D5 mandates `"nonce": "<token>"` plaintext in `destructive_op_reconfirmed`/`destructive_op_rejected` payload. Journal is append-only and may be committed to VCS; storing the live token is a residual artifact. Sources: F4+F29+Edge#41. Options: (a) honour spec — keep plaintext; (b) override spec — store `"nonce_sha256": hashlib.sha256(nonce.encode()).hexdigest()` instead, amend ADR-028 §3 + spec AC3/D5; (c) store both — `"nonce_sha256"` + omit `"nonce"`. **Recommendation: (b) — the only legitimate journal reader does not need the raw nonce.**
- [ ] **[Review][Decision] D5 — Parallel panel members race on stdin** — `_run_member` runs under `asyncio` and may be invoked concurrently for panel members; concurrent `input()` calls interleave prompts and may bind the wrong nonce to the wrong op. Sources: F5+Edge#45. Options: (a) module-level `asyncio.Lock` around the destructive-pause section (minimum-disruption, correctness-preserving); (b) serialize the entire panel when ANY tool_call is destructive (synchronous fallback); (c) accept race as test-environment-only, document in docstring. **Recommendation: (a).**
- [ ] **[Review][Decision] D6 — Multi-tool_call dispatch: accept-then-reject mixed entries** — If `agent_result.tool_calls` has N destructive calls and the user accepts call 1, rejects call 2: the dispatcher already wrote `destructive_op_reconfirmed` for call 1 then writes `destructive_op_rejected` for call 2 and raises. Call 1's downstream side effects WILL run. Sources: F31+A18+Edge#43. Options: (a) all-or-nothing — validate ALL tool_calls first; any rejection raises BEFORE any accepted call executes; (b) current behaviour (accept-prefix executes); (c) one-ceremony — collect all prompts, ask N times, proceed only if all accepted. **Recommendation: (a) — preserves dispatch atomicity invariant.**
- [ ] **[Review][Decision] D7 — `scripts/` in `_EXEMPT_DIRS` for the AC1 network scanner** — `_EXEMPT_DIRS = {"tests","scripts","_bmad","_bmad-output",".claude","_site","docs"}` exempts `scripts/`. But supply-chain risk (build, install, CI helpers) lives in `scripts/`. Source: F15. Options: (a) drop `scripts/` from `_EXEMPT_DIRS`; scan `scripts/` too — likely zero violations today; (b) keep current exemption + document the exclusion in `docs/threat-model.md` (Story 2B.7). **Recommendation: (a).**
- [ ] **[Review][Decision] D8 — TDD-first commit ordering: single squash vs split** — Story landed as ONE commit `feat(2b.6):`; AC4 + CONTRIBUTING §2 + ADR-026 §2 mandate "RED-before-GREEN visible in `git log --reverse`" for each AC's public-surface logic. 2B.5 precedent split into shape commits. Sources: A5. Options: (a) interactive rebase + force-push to rewrite `main` history (RISKY on shared branch); (b) accept squash + record audit-trail in `chore(2b.6):` commit + Change Log deviation note per 2B.4 precedent (`chore(2b.4): code-review audit trail`); (c) open `EPIC-2B-DEBT-TDD-SHAPE-SQUASH-2B6` and address in retrospective. **Recommendation: (b).**
- [ ] **[Review][Decision] D9 — Full quality gate not run before `review` flip** — Story Task 7 says "ruff format + ruff check + mypy --strict — all green on modified files; **full suite pending**". CONTRIBUTING §1 requires the FULL gate (pytest, coverage ≥87, pre-commit --all-files, mkdocs --strict, wireformat snapshots) BEFORE the status flip to `review`. Sources: F27+F28+A41. Options: (a) run the full gate now; if green, story remains in review; if red, flip back to in-progress; (b) accept dev-side ruff+mypy as sufficient + defer full gate to PR-CI; (c) one-time exception in CONTRIBUTING.md. **Recommendation: (a) — non-negotiable per CONTRIBUTING §1.**
- [ ] **[Review][Decision] D10 — `--force-with-lease` lumped with `--force` in `force_push` pattern** — `--force-with-lease` is the safer alternative; lumping trains users to dismiss the prompt. Source: F8. Options: (a) remove `--force-with-lease` from `force_push` regex; (b) add new lower-severity category `force_push_with_lease` with distinct prompt text; (c) keep current (conservative). **Recommendation: (b).**

### Patches (apply after decisions resolved)

- [ ] [Review][Patch] P1 — Thread `"nonce": _nonce` into `builder_kwargs` so prompt builder receives session nonce (depends on D1) [`src/sdlc/dispatcher/_panel_helpers.py:445-454`]
- [ ] [Review][Patch] P2 — Make `_build_destructive_ops_block(nonce: str)` non-Optional; raise `ValueError("nonce required")` on empty/None (depends on D2) [`src/sdlc/dispatcher/safety.py:32-45`]
- [ ] [Review][Patch] P3 — Add `test_dispatcher_threads_nonce_into_phase1_builder` — spy on `prompt_builder` to assert `"nonce"` kwarg passed [`tests/integration/test_dispatcher_destructive_op.py`]
- [ ] [Review][Patch] P4 — Replace `response == nonce` with `secrets.compare_digest(response, nonce)` for constant-time comparison [`src/sdlc/dispatcher/safety.py:80`]
- [ ] [Review][Patch] P5 — Wrap `input(...)` in `try: ... except (EOFError, KeyboardInterrupt): return False` for non-interactive contexts [`src/sdlc/dispatcher/safety.py:76-80`]
- [ ] [Review][Patch] P6 — Validate non-empty `nonce` and non-empty `response` in `prompt_for_reconfirmation`; raise `ValueError` on empty `nonce` [`src/sdlc/dispatcher/safety.py:75-80`]
- [ ] [Review][Patch] P7 — UTF-8-safe + control-char-sanitized `tool_call_excerpt`: NFKC normalize, collapse control chars, truncate by character (not byte), explicit dict-key whitelist when `command` non-str (avoid `str(tool_call)` leaking all keys) [`src/sdlc/dispatcher/safety.py:56-59`]
- [ ] [Review][Patch] P8 — Guard `for _tc in (agent_result.tool_calls or ()):`; non-Mapping `_tc` → `DispatchError("malformed tool_call")` not `AttributeError` [`src/sdlc/dispatcher/_panel_helpers.py:563-565`]
- [ ] [Review][Patch] P9 — Subprocess scanner: track aliased imports (`import subprocess as sp`, `from subprocess import run as r`); resolve calls back to canonical [`scripts/check_subprocess_allowlist.py:131-141`]
- [ ] [Review][Patch] P10 — Subprocess scanner: flag any `shell=True` kwarg regardless of binary [`scripts/check_subprocess_allowlist.py:483-517`]
- [ ] [Review][Patch] P11 — Subprocess scanner: inspect ALL keywords (`args=`, `executable=`) — not just first positional [`scripts/check_subprocess_allowlist.py:118-130`]
- [ ] [Review][Patch] P12 — Remove `len(allowed) == 1` silent permit at scanner line 144; replace with explicit `_DYNAMIC_BIN in allowed` check [`scripts/check_subprocess_allowlist.py:144`]
- [ ] [Review][Patch] P13 — Subprocess scanner: handle path-stripped binary names via `Path(value).name` (`/usr/bin/git` → `git`) [`scripts/check_subprocess_allowlist.py:101`]
- [ ] [Review][Patch] P14 — Subprocess scanner: add `asyncio.create_subprocess_exec`/`create_subprocess_shell` to detected-call set [`scripts/check_subprocess_allowlist.py:520-546`]
- [ ] [Review][Patch] P15 — Subprocess scanner: add `pty.spawn`/`posix_spawn`/`os.exec*` family to detected calls [`scripts/check_subprocess_allowlist.py:520-546`]
- [ ] [Review][Patch] P16 — Subprocess scanner: f-string binary names (`ast.JoinedStr`) → return `<dynamic>` sentinel (not `None` which fails-open under D7's removed shortcut) [`scripts/check_subprocess_allowlist.py:101-130`]
- [ ] [Review][Patch] P17 — Network scanner: handle `importlib.import_module("requests")` and `__import__("requests")` dynamic imports [`scripts/check_no_outbound_http.py:80-100`]
- [ ] [Review][Patch] P18 — Network scanner: handle relative imports `from . import socket` (`node.level > 0`) — skip resolution to avoid false-positive on local `socket.py` [`scripts/check_no_outbound_http.py:80-100`]
- [ ] [Review][Patch] P19 — Network scanner: walk physical line range (`node.lineno..node.end_lineno`) for `noqa` lookup; handle continuation lines and decorated module-level statements [`scripts/check_no_outbound_http.py:114-119`]
- [ ] [Review][Patch] P20 — Network + subprocess scanners: open files via `tokenize.open(path)` to honour PEP-263 encoding cookie and BOM (UTF-16 fallback) [`scripts/check_no_outbound_http.py:104-115`, `scripts/check_subprocess_allowlist.py:206-211`]
- [ ] [Review][Patch] P21 — Mock `secrets.token_urlsafe` at `sdlc.dispatcher._panel_helpers.secrets.token_urlsafe` (not global `secrets.token_urlsafe`) [`tests/integration/test_dispatcher_destructive_op.py:97,108`]
- [ ] [Review][Patch] P22 — Rename `prompt_for_reconfirmation(nonce, category, tool_call_excerpt)` parameter to `excerpt` to avoid shadowing module-level helper [`src/sdlc/dispatcher/safety.py:75`]
- [ ] [Review][Patch] P23 — Add anti-tautology fixture + test for AC1 `# noqa: net -- <reason>` exemption path (positive case currently untested) [`tests/security/test_no_outbound_http.py`, `tests/security/fixtures/noqa_exempt_net_import.py` (new)]
- [ ] [Review][Patch] P24 — Add anti-tautology fixture + test for AC2 `<dynamic>` sentinel allowance (hooks/runner.py-shaped fixture) [`tests/security/test_subprocess_allowlist.py`]
- [ ] [Review][Patch] P25 — Add anti-tautology fixture + test for AC2 `os.system` forbidden-call detection (registry handles it; no load-bearing receipt today) [`tests/security/test_subprocess_allowlist.py`, `tests/security/fixtures/forbidden_os_system.py` (new)]
- [ ] [Review][Patch] P26 — Add regression test pinning 2B.5 boundary-line scanner against the new scoping predicate (Task 5 claim is asserted by hand, not by test) [`tests/security/test_boundary_line_presence.py` or new]
- [ ] [Review][Patch] P27 — Add test asserting nonce uniqueness across two consecutive `_run_member` dispatches (regression guard against future module-level caching) [`tests/unit/dispatcher/test_safety.py`]
- [ ] [Review][Patch] P28 — Add multi-tool_call dispatch test (mixed safe+destructive; assert ordering invariants per D6 resolution) [`tests/integration/test_dispatcher_destructive_op.py`]
- [ ] [Review][Patch] P29 — Update spec File List §276-290 to include `_bmad-output/implementation-artifacts/sprint-status.yaml` [`_bmad-output/implementation-artifacts/2b-6-tool-safety-contract-tests.md:274-290`]
- [ ] [Review][Patch] P30 — Document additional `("src/sdlc/hooks/runner.py", "git")` allow-list entry as Change Log §294 deviation from AC2/D1 5-entry literal [`_bmad-output/implementation-artifacts/2b-6-tool-safety-contract-tests.md:294`]
- [ ] [Review][Patch] P31 — `_should_inject_destructive_block` glob normalization: strip leading `./`, normalize `\\`→`/`, strip leading `!`, ignore empty strings [`src/sdlc/dispatcher/safety.py:26-29`]
- [ ] [Review][Patch] P32 — `is_destructive`: `unicodedata.normalize("NFKC", command).strip()` before regex (defeats unicode-look-alike `rm` and whitespace prefix bypass) [`src/sdlc/dispatcher/safety.py:62-72`]
- [ ] [Review][Patch] P33 — Implement D10(b): add `force_push_with_lease` lower-severity category if D10 chooses (b) [`src/sdlc/dispatcher/safety.py:49-53`]
- [ ] [Review][Patch] P34 — Wrap `journal_append` in try/except in `_run_member` rejection path; raise `DispatchError("journal_failure")` on disk-full/permission-denied so audit trail is never silently lost [`src/sdlc/dispatcher/_panel_helpers.py:580-590`]

### Deferred (pre-existing scope or v1-accepted)

- [x] [Review][Defer] CR2B6-W1 EPIC-2B-DEBT-DESTRUCTIVE-CATALOGUE-EXPANSION — extend `_DESTRUCTIVE_TOOL_PATTERNS` with `find -delete`/`shred`/`dd of=`/`truncate`/`TRUNCATE`/`DELETE FROM`/`ALTER ... DROP COLUMN`/`git push --delete`/`git push +ref`/`git push --mirror`/`sudo` wrappers/heredoc/multi-call sessions/`rm -r -f`/`rm -Rf`/`rm --recursive --force`/bare `rm`/`> overwrite`. Sources: F7+F9+Edge#26+#28+#29+#37+others. Pre-existing scope per spec AC3/D1; debt opened by spec [`src/sdlc/dispatcher/safety.py:49-53`] — deferred, pre-existing
- [x] [Review][Defer] CR2B6-W2 EPIC-2B-DEBT-NETWORK-MODULE-CATALOGUE — extend `_FORBIDDEN_NETWORK_MODULES` with `ssl`/`paramiko`/`pycurl`/`websockets`/`grpc`/`python-socketio`/`tornado`/`twisted`/`asyncio.streams`. Source: Edge#4 [`scripts/check_no_outbound_http.py:24-40`] — deferred, pre-existing
- [x] [Review][Defer] CR2B6-W3 EPIC-2B-DEBT-NETWORK-ISOLATED-CI — runtime network-sandbox/firewall layer per `architecture.md:1273`. Source: spec AC1/D3; already opened by spec — deferred, pre-existing
- [x] [Review][Defer] CR2B6-W4 EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE — verify agent echoes the nonce in its acknowledgement before the destructive tool_call. Source: spec AC3/D3; already opened by spec — deferred, pre-existing
- [x] [Review][Defer] CR2B6-W5 EPIC-2B-DEBT-SUBPROCESS-WRAPPER-CONSOLIDATION — refactor to single internal `subprocess_pool.py` wrapper per `architecture.md:879` Decision A2. Source: spec AC2/D1; already opened by spec — deferred, pre-existing
- [x] [Review][Defer] CR2B6-W6 — symlink/permission/UTF-16/BOM edge cases in scanners. Sources: Edge#8+#9+#10. Low-risk on current dev surface [`scripts/check_no_outbound_http.py:267-302`] — deferred, low-risk
- [x] [Review][Defer] CR2B6-W7 — `noqa` reason-quality control (10-char filler accepted). Source: F16. Inherited from 2B.5 scanner pattern; addressing requires repo-wide convention change [`scripts/check_no_outbound_http.py:34`] — deferred, cross-cutting
- [x] [Review][Defer] CR2B6-W8 — `asyncio.to_thread` cancellation hazard on blocked `input()`. Source: Edge#46. Rare; cancellation hangs on blocked stdin thread [`src/sdlc/dispatcher/_panel_helpers.py:565-595`] — deferred, low-frequency
- [x] [Review][Defer] CR2B6-W9 — `tool_call_excerpt` does not redact secrets/tokens/JWTs before journaling. Source: A46. Privacy debt; couples with journal-PII review [`src/sdlc/dispatcher/safety.py:56-59`] — deferred, cross-cutting
- [x] [Review][Defer] CR2B6-W10 — nonce generated unconditionally per `_run_member`; could be lazy on first destructive detection. Sources: F21+A19+Edge#40. Cosmetic; no security impact [`src/sdlc/dispatcher/_panel_helpers.py:442`] — deferred, cosmetic
- [x] [Review][Defer] CR2B6-W11 — `main()` prints to stdout from inside scanner. Source: F20. Script convention; consistent with `check_no_hardcoded_secrets.py` [`scripts/check_no_outbound_http.py:140-150`] — deferred, convention
- [x] [Review][Defer] CR2B6-W12 — `prompts.py` re-exports private `_build_destructive_ops_block` and `_should_inject_destructive_block` via `# noqa: F401`. Source: F33. Style; the test access pattern is intentional [`src/sdlc/dispatcher/prompts.py:17-22`] — deferred, style

### Dismissed (10)

- R1 (F1+F2+A44) — Nonce visible to user is BY DESIGN (interactive trust gate; user is trusted party + must type the value). Agent-side visibility is intentional per AC3/D3 with `EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE` already open.
- R2 (F18) — `Path(__file__).resolve()` brittleness on symlinks; overkill given v1 invocation surface.
- R3 (F19) — Claim `tests/security/conftest.py` `sys.path` mutation is "fragile" — verified as the 2B.5 P8 canonical pattern.
- R4 (F25) — Scoping by `write_globs` "conceptually questionable" — spec AC3/D4 D1 mandates this scoping.
- R5 (F30) — ADR-028 row consistency — verified via A26; rows + Revision Log entry present.
- R6 (F36) — Ugly triple-import block satisfying ruff I001 — repo-wide style standard.
- R7 (F39) — `_FIXED_NONCE` test constant low-entropy — intentional for determinism.
- R8 (A6+A7+A8+A10+A13+A14+A15+A23+A25) — Covered by 2B.5 precedent or verified false-positive (urllib.request prefix-matched via `urllib`; `noqa` bare-marker behaviour intentional fail-closed; magic exit code 2 consistent with `check_boundary_line_presence.py`).
- R9 (A24) — Module-boundary `dispatcher → specialists` — verified ALLOWED at `scripts/module_boundary_table.py:83`. Spec Dev Notes §195 was out-of-date; `prompts.py:25` already imported `Specialist` pre-story.
- R10 (A35+A36+A37) — Force-push regex narrowness covered by W1 catalogue-expansion debt; `--force-with-lease=ref` form matches via `\b` boundary (verified).
