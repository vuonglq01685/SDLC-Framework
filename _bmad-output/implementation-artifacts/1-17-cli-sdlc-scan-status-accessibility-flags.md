# Story 1.17: CLI `sdlc scan` + `sdlc status` + Accessibility Flags

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user checking project state without orchestration,
I want `sdlc scan` to refresh `state.json` from the filesystem and `sdlc status` to print a "you are here" resume card with the suggested-next-action command, both supporting `--no-color` and `--json` modes,
so that the v0.2 walking-skeleton end state (`sdlc init && sdlc status` says "Phase 1, no progress yet") is demonstrable end-to-end and the CLI is accessibility-friendly for assistive tooling and color-blind / no-color terminals (FR3, FR44, NFR-A11Y-4, NFR-PERF-1, Architecture §117, §349, §388, §549, §674-§680, §799, §801, §815, §1133, §1170, §1408).

## Acceptance Criteria

**AC1 — `sdlc scan` invokes the engine scanner, writes `state.json` atomically, appends a `scan_completed` journal entry, exits 0 (epic AC block 1)**

**Given** the framework was initialized via `sdlc init` (Story 1.16) — `<repo_root>/.claude/state/state.json` and `<repo_root>/.claude/state/journal.log` both exist,

**When** the user invokes `sdlc scan` from any cwd inside `<repo_root>`,

**Then**:

1. The command resolves the repo root via the same `_get_repo_root_or_cwd()` helper Story 1.16's `cli/init.py` uses (factor out into `cli/_paths.py` if `cli/init.py` exceeded 200 LOC and helpers were extracted in 1.16; otherwise duplicate the 5-line helper inline in `cli/scan.py` — single-use is acceptable, mirror the same exception narrowing).
2. The command refuses with exit 1 + clear stderr message if `<repo_root>/.claude/state/state.json` does NOT exist (state never initialized). Message:
   ```
   sdlc: project not initialized at <repo_root>; run `sdlc init` first
   ```
   Exit code 1 (`EXIT_USER_ERROR`). Mirrors Story 1.16's "already initialized" refusal pattern (clear, refuses cleanly, no partial work).
3. The command calls `sdlc.engine.scanner.scan(project_root=<repo_root>)` (Story 1.15) to compute the fresh `State` projection from the artifact tree (`01-Requirement/04-Epics/`, `01-Requirement/05-Stories/`, `03-Implementation/tasks/`). The scanner is pure read-only per Story 1.15 AC1 — no writes happen inside `scan()`.
4. **Atomic state write**: the resulting `State` is persisted to `<repo_root>/.claude/state/state.json` via `sdlc.state.write_state_atomic_sync` on POSIX. On Windows, fall back to `Path.write_bytes(canonical_bytes)` with the same `_logger.warning(...)` advisory Story 1.16's `cli/init.py` emits (POSIX-only atomic protocol unavailable; recommend WSL2). The canonical-bytes contract is identical to Story 1.16's `_canonical_initial_state_bytes()` — `json.dumps(state.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"` — but built from the SCANNED state, not `State()` defaults. Implementation tip: factor the canonical-bytes serializer into `state/__init__.py` as a public `state_to_canonical_bytes(state: State) -> bytes` helper so both `cli/init.py` and `cli/scan.py` share one source of truth (this avoids the canonical-bytes contract drifting between the two writers — a chaos vector if dev forgets to update one).
5. **Journal append**: a single `JournalEntry` is appended to `<repo_root>/.claude/state/journal.log` via `sdlc.journal.append_sync` (Story 1.11). Entry shape:
   ```python
   JournalEntry(
       schema_version=1,
       monotonic_seq=<state.next_monotonic_seq AFTER scan>,
       ts=<UTC now in RFC 3339 with Z and ms precision>,
       actor="cli",
       kind="scan_completed",
       target_id="state",
       before_hash=<sha256 of pre-scan state.json bytes, or None if state.json was missing>,
       after_hash=<sha256 of post-scan canonical state bytes>,
       payload={"epic_count": len(state.epics), "story_count": len(state.stories), "task_count": len(state.tasks)},
   )
   ```
   `monotonic_seq` MUST be exactly `pre_scan_state.next_monotonic_seq` (the seq slot the scan claims) and the new state written to disk MUST have `next_monotonic_seq = pre_scan_state.next_monotonic_seq + 1` so the next mutation finds an unclaimed slot. Story 1.12's projection reducer at `state/projection.py:70` does `next_seq = max(next_seq, entry.monotonic_seq + 1)` — this story's seq math must be consistent with that reducer. The `before_hash` is computed via `hashlib.sha256(pre_scan_bytes).hexdigest()` formatted as `f"sha256:{digest}"`; the `after_hash` is computed the same way over the canonical bytes about to be written. If pre-scan `state.json` was missing (recovery edge case after `sdlc init` partial failure), `before_hash=None` per the JournalEntry contract.
6. The timestamp is built via `datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"` — RFC 3339 UTC with millisecond precision, matching the JournalEntry `_RFC3339_UTC` regex at `contracts/journal_entry.py:16`. Use `datetime.datetime.now(datetime.timezone.utc)` ONLY (Architecture §490 forbids `time.time()` for ordering; here it's a human-readable timestamp, NOT an ordering primitive — Lamport `monotonic_seq` carries ordering — so the wall-clock use is permitted but must be UTC).
7. **Write order**: state.json FIRST, then journal append. This matches the Atomic Write Protocol Architecture §573-§583 step 8 ("append journal entry referencing the mutation"). If the journal append fails (`JournalError`), the state.json write has already landed — the framework refuses to start on next invocation only if the state itself is malformed (Story 1.20 owns this), but a journal-without-state mismatch is acceptable here because `before_hash` was computed FROM the previous state-on-disk before scan, and `state.rebuild` (Story 1.20) treats journal as source of truth. Document this ordering in dev notes; do NOT swap.
8. **Output (default human-readable mode)**: stdout prints a single confirmation line:
   ```
   sdlc scan: <repo_root> — phase 1, 0 epics, 0 stories, 0 tasks (state.json refreshed)
   ```
   Exact format is NOT load-bearing for tests; tests assert presence of the path + counts. The line MUST go through `cli/output.py:echo` (NOT `print`, NOT direct `typer.echo`) so the `--no-color` / `--json` flags route through one place.
9. **Output (`--json` mode)** — see AC4 below. A single canonical JSON document on stdout shaped:
   ```json
   {"command": "scan", "project_root": "<absolute-path>", "phase": 1, "epic_count": 0, "story_count": 0, "task_count": 0, "next_monotonic_seq": <int>, "journal_entry_seq": <int>}
   ```
   The schema for this output is a v1 wire-format-ADJACENT contract (NOT one of the 5 frozen contracts; CLI output schemas live alongside the wire-format contracts but are versioned separately per Architecture §678). Document the schema in `cli/output.py` as a `_SCAN_OUTPUT_SCHEMA: Final[str] = "v1"` constant + a docstring naming the keys.
10. **Exit code 0** on success.
11. The command is implemented in `src/sdlc/cli/scan.py` per Architecture §799 + §1133; the function is `run_scan() -> None` (mirrors `cli/init.py:run_init()` from Story 1.16). The Typer command function `scan_command()` lives in `cli/main.py` and defers `from sdlc.cli.scan import run_scan` to body level per Architecture §488 (cold-start budget — no `engine` / `state` / `journal` import for `sdlc --version`).

**And** the scan operation is **idempotent in projection but NOT idempotent in journal**: running `sdlc scan` twice on the same artifact tree produces byte-identical `state.json` (per Story 1.15 AC1 — scanner is pure) BUT appends two journal entries (one per scan call). This is correct: each scan is a *recorded observation* of the artifact tree, not a mutation of it. Second-run journal entry has `before_hash == after_hash` because state didn't change — that's permitted by the JournalEntry contract (no constraint that before != after). Tests verify this property.

**And** `sdlc scan` does NOT touch the artifact tree (`01-Requirement/`, `02-Architecture/`, `03-Implementation/`) — only `<repo_root>/.claude/state/state.json` and `<repo_root>/.claude/state/journal.log`. NFR-REL-6 spirit holds: scan is read-only with respect to user artifacts.

**AC2 — `sdlc status` prints the "you are here" resume card with suggested-next-action (epic AC block 2)**

**Given** the framework was initialized AND optionally scanned at least once,

**When** the user runs `sdlc status` from any cwd inside `<repo_root>`,

**Then** stdout prints a card with the following components (default human-readable mode):

1. **Header**: `sdlc status — <project_name>` where `<project_name>` is sourced from `pyproject.toml`'s `[project] name` if a `pyproject.toml` exists at `<repo_root>`, else from `<repo_root>` directory basename. The lookup is best-effort: if `pyproject.toml` is missing or unreadable, fall back to basename silently. Use `tomllib` (stdlib in Python 3.11+) with a `try: import tomllib except ImportError: import tomli as tomllib` fallback only if `tomli` is in the dep set — for v1.17, target Python 3.10+ (per `pyproject.toml:10`) so use `tomllib` with a guarded import: in 3.10, `tomllib` is missing — fall back to a regex/yaml-free name extraction (read first 50 lines, find `^name\s*=\s*["']([^"']+)["']`). Keep the helper ≤ 20 LOC.
2. **Phase line**: `Phase: <N>` where `<N>` is `state.phase` (Story 1.15 schema extension). Default `1` for fresh projects. The phase number is followed by a parenthetical phase name: `Phase: 1 (Requirement)`, `Phase: 2 (Architecture)`, `Phase: 3 (Implementation)`. The name lookup is a `_PHASE_NAMES: Final[Mapping[int, str]] = MappingProxyType({1: "Requirement", 2: "Architecture", 3: "Implementation"})` constant in `cli/status.py`. Unknown phase numbers print `Phase: <N> (unknown)` and emit a `_logger.warning` (forward-compat for v2.x extensions).
3. **Last-updated timestamp**: sourced from the most recent JournalEntry's `ts` field via `sdlc.journal.iter_entries(journal_path)` reading the LAST entry. If the journal is empty (`sdlc init` ran but no `sdlc scan` yet), print `Last updated: <never — run \`sdlc scan\`>`. The timestamp is rendered in the user's local timezone for human-readable mode and as the literal RFC 3339 UTC string for `--json` mode. The local-time conversion uses `datetime.datetime.fromisoformat(...)` (Python 3.10 compatible after the `T...Z` → `T...+00:00` substitution since 3.10's fromisoformat doesn't accept `Z`; 3.11+ does — handle both via `ts.replace("Z", "+00:00")` before parsing).
4. **Suggested next-action line**: `Suggested next: <command>` where the command is computed by a `_compute_suggested_next(state: State) -> str` helper:
   - **Fresh project** (`state.phase == 1` AND `state.epics == {}`): `/sdlc-start "<idea>"` (literal — the user replaces `<idea>` with their actual project description). Per epic AC block 2 explicitly: "on a fresh project, the suggested-next is `/sdlc-start \"<idea>\"`".
   - **Phase 1 in progress** (`state.phase == 1` AND `state.epics != {}` AND no SIGNOFF): `/sdlc-epics` or `/sdlc-stories <EPIC-id>` — for v1.17, fresh-project case is the only ACTIVELY tested branch; other branches are NAMED in the helper but the tests only assert the fresh-project case. Story 4.x's `engine/auto_loop.py` will own the rich next-action computation; v1.17's `_compute_suggested_next` is a STUB that handles fresh-project + falls through to `"sdlc scan"` for any other case (a non-blocking sensible default).
   - The helper has the comment `# v1.17: minimal stub — Story 4.x's auto_loop owns the rich engine. Fresh-project is the only AC-tested branch.` so future readers know the design intent.
5. **Bottom border / footer**: a single horizontal rule (`---` in plain mode, dim-styled `─` Unicode in rich mode). Optional decoration; keep `≤ 80` characters width to fit narrow terminals.
6. **Exit code 0** on success regardless of state shape (status is informational, never an error path even if state.json is malformed — that's a STOP trigger Story 4.x owns; v1.17 just prints what it can find).

**And** if `<repo_root>/.claude/state/state.json` does NOT exist (project not initialized), `sdlc status` exits 1 with stderr message:
```
sdlc: project not initialized at <repo_root>; run `sdlc init` first
```
Same refusal as `sdlc scan` AC1.2 — share the helper `_require_initialized_state(state_path: Path, repo_root: Path) -> None` between the two commands; place in `cli/_paths.py` (preferred) or duplicate inline.

**And** in `--json` mode (see AC4), the output is a canonical JSON document:
```json
{
  "command": "status",
  "project_name": "<name>",
  "project_root": "<absolute-path>",
  "phase": 1,
  "phase_name": "Requirement",
  "last_updated_ts": "2026-05-08T15:30:42.123Z",
  "epic_count": 0,
  "story_count": 0,
  "task_count": 0,
  "suggested_next": "/sdlc-start \"<idea>\"",
  "next_monotonic_seq": 1
}
```
When `last_updated_ts` is the "never" sentinel (empty journal), the JSON value is `null` (NOT the string `"never"`) per the JSON-Schema discipline of using `null` for absent values. Document this in `cli/output.py`.

**And** `sdlc status` is fully read-only: NO writes to state.json, NO writes to journal.log, NO subprocess calls (other than the optional `git rev-parse --show-toplevel` shared with Story 1.16's helper). Pure projection of `read_state` + last-journal-entry. Tests verify zero writes via mtime-snapshot.

**AC3 — `--no-color` flag + `NO_COLOR` env var disable ANSI escapes on every `sdlc *` subcommand (epic AC block 3, NFR-A11Y-4)**

**Given** any `sdlc *` subcommand (`init`, `scan`, `status`, `--version`, `--help`),

**When** the user appends `--no-color` to the invocation OR has `NO_COLOR=1` (or any non-empty value) in the environment,

**Then**:

1. The output contains ZERO ANSI escape sequences. Tests assert this via the regex `re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")` — the search MUST yield zero matches across the entire stdout AND stderr captures of every command.
2. The CLI flag `--no-color` is registered as a global Typer option on `cli/main.py:_root` (the root callback) — NOT as a per-subcommand option. Typer's idiomatic pattern for global flags is the root callback; subcommands inherit via the Typer context. Implementation:
   ```python
   @app.callback()
   def _root(
       ctx: typer.Context,
       version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
       no_color: bool = typer.Option(False, "--no-color", help="Disable ANSI color in CLI output (NO_COLOR env var also honored).", is_eager=True),
       json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON instead of human-readable output.", is_eager=True),
   ) -> None:
       ctx.ensure_object(dict)
       ctx.obj["no_color"] = no_color or _is_no_color_env_set()
       ctx.obj["json"] = json_output
   ```
   The `is_eager=True` ensures the flag is parsed before any subcommand dispatch (so subcommands can read it from `ctx.obj`).
3. `NO_COLOR` env var honoring: a helper `_is_no_color_env_set() -> bool` returns `True` if `os.environ.get("NO_COLOR", "")` is non-empty (per the no-color.org informal standard — any non-empty value disables color). Per Architecture §491 + Story 1.8's allow-list, env-var reads MUST go through `sdlc.config.read_env`. BUT `NO_COLOR` is NOT in the `SDLC_*` / `CLAUDE_*` / `GH_TOKEN` allow-list. **Resolution**: extend the allow-list. Edit `src/sdlc/config/env.py`:
   ```python
   ENV_EXACT_ALLOWLIST: Final[frozenset[str]] = frozenset({"GH_TOKEN", "NO_COLOR"})
   ```
   And add a one-line comment: `# NO_COLOR added in Story 1.17 per no-color.org informal standard for accessibility-friendly CLI output (NFR-A11Y-4).`
   This widening is intentional and AC-tested. The boundary linter does NOT need to change because `cli/` already depends on `config/` (Story 1.16 widening).
4. **Precedence rule** (per the no-color.org spec — "user-level configuration files and per-instance command-line arguments should override the NO_COLOR environment variable"): `--no-color` is OR'd with `_is_no_color_env_set()` — if EITHER is true, color is disabled. There is no `--color` opposite flag in v1.17 (the user can clear color preference by passing neither flag and unsetting `NO_COLOR`). Document the precedence in `cli/output.py` docstring + ADR-020.
5. The `cli/output.py:echo` helper updated from Story 1.16's stub to consult the no-color signal. Two implementation paths:
   - **Path A (preferred)**: Use `rich.console.Console(no_color=<flag>)` for human-readable output. Rich auto-handles non-TTY detection AND honors the `no_color` parameter. The console instance is created lazily per command (NOT at module import) to keep cold-start cost off the `--version` path.
   - **Path B (fallback)**: A custom ANSI-stripping pass `def _strip_ansi(s: str) -> str: return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", s)` for cases where the message is built without rich (legacy compatibility / `init.py` already uses plain strings).
   v1.17 implements PATH A (rich console) for `scan` + `status` outputs, and Path B's regex for any plain-string outputs (legacy from Story 1.16's `init.py` confirmation block — `init.py` does NOT need rewriting; the strip-ansi pass applied uniformly via `cli/output.py:echo` keeps init's output ANSI-free even before `init.py` ever uses rich).
6. **Test surface**: every command (`init`, `scan`, `status`, `--version`, `--help`) gets a parametrized test:
   ```python
   @pytest.mark.parametrize("argv", [
       ["--version"],
       ["init"],
       ["scan"],
       ["status"],
       ["--help"],
   ])
   def test_no_color_flag_strips_ansi_on_every_command(argv: list[str], tmp_path: Path) -> None:
       runner = CliRunner()
       result = runner.invoke(app, ["--no-color"] + argv, ...)
       assert _ANSI_RE.search(result.stdout) is None, f"ANSI in stdout for {argv}"
       assert _ANSI_RE.search(result.stderr) is None, f"ANSI in stderr for {argv}"
   ```
   Plus an env-var variant via `monkeypatch.setenv("NO_COLOR", "1")` without the flag.
7. The `--help` output's color suppression depends on Typer's internal `rich`-based help renderer. Typer 0.12+ exposes `rich_markup_mode="rich"` (default) vs `"markdown"` vs `None`. With `--no-color` set, the test asserts ANSI absence on `--help` output specifically — if Typer's rich-renderer ignores `NO_COLOR`, the workaround is to set `rich_markup_mode=None` on the `app = typer.Typer(...)` constructor when `_is_no_color_env_set()` returns True. In v1.17, take the simplest path: if Typer's default help output contains ANSI even with `--no-color` (which we verify in Task 7's smoke test), strip ANSI at the `cli/output.py` boundary via `_strip_ansi`. If Typer's `rich_markup_mode` already respects `NO_COLOR` (Typer ≥ 0.12 should), the strip pass is a no-op. Either way the assertion passes.

**AC4 — `--json` flag emits canonical JSON on stdout for every `sdlc *` subcommand; error envelope on stderr (epic AC block 4, Architecture §549, §678-§679)**

**Given** any `sdlc *` subcommand,

**When** the user appends `--json`,

**Then**:

1. The stdout output is EXACTLY ONE JSON document — no leading/trailing newlines beyond the trailing `\n` that `json.dumps(...) + "\n"` produces, no log lines, no banners, no prompts. Tests assert `json.loads(result.stdout)` succeeds and yields the expected dict shape.
2. The JSON document format is canonical: `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` — same canonical-bytes contract used by `state/atomic.py` (Story 1.10) and `journal/_canonical.py` (Story 1.11). This makes the JSON output byte-equal across runs given byte-equal state, which is testable in CI.
3. Per-command schemas (canonical key sets):
   - `sdlc --version --json`: `{"command": "version", "version": "0.0.0"}`. Trivial; the version string equals `sdlc.__version__`.
   - `sdlc init --json`: `{"command": "init", "project_root": "<path>", "created": ["<list>", "<of>", "<paths>"]}` — list of created paths relative to repo root, sorted. Story 1.16's `init.py` does NOT currently emit this shape; v1.17 ADDS the `--json` formatter at `cli/output.py:emit_json(command, payload)` and `cli/init.py` wires it via the context's `json` flag check at the top of `run_init`. The `init.py` body change is minimal (one branch on context flag → emit_json instead of echo).
   - `sdlc scan --json`: per AC1.9 above.
   - `sdlc status --json`: per AC2 trailing block above.
   - `sdlc --help --json` is NOT supported in v1.17 — Typer's help renderer does not have a JSON mode and we are NOT shimming one. The flag is silently passed through to Typer's default help renderer; the test asserts `--help` output is identical with and without `--json` (i.e. Typer ignores it for help). Document this exception in dev notes.
4. **Error envelope** (per Architecture §549-§559): all errors in `--json` mode emit on stderr (NOT stdout) as a single JSON document:
   ```json
   {"error": {"code": "<ERR_CODE>", "message": "<human-readable>", "details": {<kind-specific>}, "exit_code": <int>}}
   ```
   The `<ERR_CODE>` is one of:
   - `ERR_NOT_INITIALIZED`: `<repo_root>/.claude/state/state.json` missing (exit 1).
   - `ERR_ALREADY_INITIALIZED`: `sdlc init` re-run (exit 1) — wraps Story 1.16 AC3 into the JSON shape.
   - `ERR_SCAN_FAILED`: `engine.scanner.scan(...)` raised `StateError` (exit 2 — framework failure per Architecture §546).
   - `ERR_JOURNAL_APPEND_FAILED`: `journal.append_sync` raised (exit 2).
   - `ERR_STATE_WRITE_FAILED`: `state.write_state_atomic_sync` raised (exit 2).
   - `ERR_INFRASTRUCTURE`: `OSError` family or missing external binary (exit 3 per Architecture §547).
   - `ERR_USER_INPUT`: bad CLI args, missing required arg (exit 1) — Typer's own `BadParameter` is mapped here when `--json` is set.
   The `details` block carries the `details=` dict from the underlying `SdlcError` subclass, sanitized via `sdlc.config.sanitize_mapping` (Story 1.8) so secret-pattern matches are redacted before emission.
5. The error code → exit code mapping is centralized in `cli/output.py:_ERR_CODE_TO_EXIT_CODE: Final[Mapping[str, int]] = MappingProxyType({"ERR_NOT_INITIALIZED": 1, "ERR_ALREADY_INITIALIZED": 1, "ERR_SCAN_FAILED": 2, ...})` so the table is one source of truth. Story 1.18+'s `cli/trace.py`, `cli/replay.py`, `cli/logs.py` extend this table when they ship.
6. The error envelope is built by `cli/output.py:emit_error(code: str, message: str, details: dict[str, object] | None = None) -> NoReturn` — calls `typer.echo(json.dumps(envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":")), err=True)` then `raise typer.Exit(code=<mapped exit>)`. `NoReturn` is the type hint because the function always raises.
7. **Default mode (no `--json`)**: errors print as human-readable lines on stderr (current Story 1.16 behavior). The JSON envelope is conditional on `ctx.obj["json"]`. The error formatter at `cli/output.py:emit_error` reads the same context and branches.
8. **Test surface**: a parametrized test ensures `--json` produces exactly one JSON doc on stdout (or stderr for errors). Plus a per-command schema test asserting required keys are present:
   ```python
   def test_status_json_schema_keys(tmp_path: Path) -> None:
       _initialize_test_project(tmp_path)
       result = runner.invoke(app, ["--json", "status"], ...)
       payload = json.loads(result.stdout)
       expected_keys = {"command", "project_name", "project_root", "phase", "phase_name", "last_updated_ts", "epic_count", "story_count", "task_count", "suggested_next", "next_monotonic_seq"}
       assert set(payload.keys()) == expected_keys
   ```

**AC5 — `cli/output.py` module expansion: rich console, color/json modes, error envelope (Architecture §674-§680, §792)**

**Given** Story 1.16 shipped a minimal `cli/output.py` stub with a single `echo()` helper,

**When** Story 1.17 lands,

**Then** `src/sdlc/cli/output.py` is expanded to provide the full v1 surface:

1. Public API (re-exported via `cli/output.py:__all__`):
   - `echo(message: str, *, err: bool = False, ctx: typer.Context | None = None) -> None` — extends Story 1.16's stub. New: when `ctx` is supplied and `ctx.obj["no_color"]` is True, ANSI is stripped before emission. When `ctx.obj["json"]` is True, `echo` is a NO-OP (JSON mode silences plain-text channels — only `emit_json` / `emit_error` produce output in JSON mode). Backward-compat: when `ctx is None` (legacy callers), behavior matches Story 1.16's stub.
   - `emit_json(command: str, payload: dict[str, object], *, ctx: typer.Context) -> None` — emits the canonical-bytes JSON document on stdout. The `command` field is auto-injected into the payload as `payload["command"] = command` if not already set. Sorted keys, no ASCII escaping, compact separators, trailing `\n`.
   - `emit_error(code: str, message: str, *, ctx: typer.Context, details: Mapping[str, object] | None = None) -> NoReturn` — emits the error envelope per AC4.4 + maps to the exit code via `_ERR_CODE_TO_EXIT_CODE` + raises `typer.Exit(code=<mapped>)`. In `--json` mode the envelope goes to stderr as JSON; in default mode the message goes to stderr as plain text.
   - `make_console(ctx: typer.Context) -> rich.console.Console` — lazy factory returning a `rich.console.Console` configured with `no_color=ctx.obj["no_color"]` and `force_terminal=False` so the output respects the user's TTY context. Cached per-context via `ctx.obj.setdefault("_console", ...)` to avoid repeated construction.
2. Module structure (≤ 200 LOC; if exceeded, factor into `cli/_output_helpers.py` per the `journal/_canonical.py` precedent):
   - Module docstring naming Story 1.17 + the four public functions + the error code table.
   - `from __future__ import annotations`.
   - Stdlib imports: `import json`, `import os`, `import re`, `from collections.abc import Mapping`, `from types import MappingProxyType`, `from typing import Final, NoReturn`.
   - Third-party imports: `import typer`, `from rich.console import Console`.
   - SDLC imports: `from sdlc.config import sanitize_mapping`.
3. Constants:
   - `_ANSI_RE: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")`.
   - `_ERR_CODE_TO_EXIT_CODE: Final[Mapping[str, int]]` — table per AC4.5.
   - `_NO_COLOR_ENV: Final[str] = "NO_COLOR"`.
4. Public callable: `is_no_color_active(ctx: typer.Context | None) -> bool` — returns True if either `--no-color` was passed (read from `ctx.obj["no_color"]`) OR `NO_COLOR` env is non-empty. Reads env via `sdlc.config.read_env("NO_COLOR")` (after Task 2 widens the allow-list). Returns False if `ctx is None` (legacy compat).
5. Adds `__all__ = ("echo", "emit_json", "emit_error", "make_console", "is_no_color_active")` (semantic order: legacy stub → new emitters → factory → introspection — do NOT alphabetize per Story 1.7/1.11 convention).
6. The `rich` direct-dependency declaration: per Story 1.16 dev notes ("`rich` is a transitive dep of Typer; do NOT add it as a direct dep in 1.16 — Story 1.17's `cli/output.py` rich-styling work declares `rich` as a direct dep at that point"), Story 1.17 ADDS `"rich>=13,<15"` to `[project] dependencies` in `pyproject.toml`. Cap rationale: rich 13.x is stable; rich 14.x landed mid-2025 with minor breaking changes around `Console.print`'s `markup` default. The `<15` cap is defensive against the next major.

**AC6 — `cli/main.py` registers `scan` and `status` subcommands + global `--no-color` / `--json` flags (Architecture §791)**

**Given** Story 1.16 shipped `cli/main.py` with the Typer app, `--version` callback, and `init` subcommand,

**When** Story 1.17 lands,

**Then**:

1. `cli/main.py` is extended (NOT rewritten) to register two new subcommands:
   ```python
   @app.command(name="scan")
   def scan_command(ctx: typer.Context) -> None:
       """Refresh state.json from the artifact tree (FR3)."""
       from sdlc.cli.scan import run_scan  # deferred per Architecture §488
       run_scan(ctx=ctx)


   @app.command(name="status")
   def status_command(ctx: typer.Context) -> None:
       """Print the resume card with suggested next-action (FR44)."""
       from sdlc.cli.status import run_status  # deferred
       run_status(ctx=ctx)
   ```
2. The root callback `_root` is extended to add `--no-color` and `--json` global options per AC3.2. The signature change from Story 1.16's:
   ```python
   def _root(version: bool = typer.Option(...)) -> None:
   ```
   becomes:
   ```python
   def _root(
       ctx: typer.Context,
       version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
       no_color: bool = typer.Option(False, "--no-color", is_eager=True, help="..."),
       json_output: bool = typer.Option(False, "--json", is_eager=True, help="..."),
   ) -> None:
       ctx.ensure_object(dict)
       ctx.obj["no_color"] = no_color or os.environ.get("NO_COLOR", "") != ""
       ctx.obj["json"] = json_output
   ```
   The `os.environ.get` direct read is justified here because `cli/` is permitted env access and the `read_env` allow-list path requires the name to be allow-listed (which Task 2 does); using either is fine but the direct read is simpler in the root callback. Document the decision in ADR-020.
3. `init_command` (existing from Story 1.16) is updated to accept `ctx: typer.Context` and pass it to `run_init(ctx=ctx)`. `cli/init.py:run_init`'s signature gains `ctx: typer.Context | None = None` (default None for backward compat with existing tests calling `run_init()` without context — those tests still pass; new tests pass ctx). Inside `run_init`, the existing `echo(...)` calls are upgraded to `echo(..., ctx=ctx)` so `--no-color` / `--json` apply to init too.
4. The `--version` callback function `_version_callback` is updated to honor `--json`: when the eager flag fires, check `os.environ.get(...)` for the JSON sentinel set by `_root`. Because `--version` is `is_eager=True` (fires BEFORE `_root` body runs in some Typer versions), the cleanest approach is to read `--json` directly from `sys.argv` in `_version_callback`:
   ```python
   def _version_callback(value: bool) -> None:
       if value:
           if "--json" in sys.argv:
               typer.echo(json.dumps({"command": "version", "version": get_version()}, sort_keys=True, separators=(",", ":")))
           else:
               typer.echo(f"sdlc {get_version()}")
           raise typer.Exit(code=0)
   ```
   This is a minor sys.argv peek; document in ADR-020 as the "eager-callback bootstrap problem" workaround. The Typer eager-callback ordering is documented at typer.tiangolo.com/tutorial/options/version/.
5. `cli/main.py` LOC stays ≤ 130 (Story 1.16 caps at 100; new flags + two new subcommand registrations bring it to ~120-130). If exceeded, factor `_root` body into `cli/_main_helpers.py:initialize_context(ctx, no_color, json_output)`.
6. Module-level imports stay minimal per Architecture §488: `typer`, `sdlc.cli.version.get_version`, `os`, `sys`, `json` are the only allowed module-level imports. NO `from sdlc.engine import ...`, NO `from sdlc.state import ...`, NO `from sdlc.journal import ...` at module level — all deferred to subcommand body.

**AC7 — Tests prove `scan`, `status`, `--no-color`, `--json` all work end-to-end (epic AC block 1+2+3+4)**

**Given** the test pyramid established by Stories 1.10-1.16,

**When** Story 1.17 lands,

**Then** the test suite contains:

1. **Unit tests** at `tests/unit/cli/test_scan.py` (with `pytestmark = pytest.mark.unit`):
   - `test_scan_refuses_when_state_not_initialized(tmp_path)`: invoke `run_scan` against a tmp_path with no `.claude/state/state.json`; assert `typer.Exit` with `exit_code == 1`; capsys stderr contains "not initialized".
   - `test_scan_writes_fresh_state_json(tmp_path)`: bootstrap project (call `run_init`), then call `run_scan`; assert `state.json` exists with canonical empty State bytes (post-scan == State() canonical bytes for empty artifact tree). Assert `state.next_monotonic_seq == 1` (incremented from 0 because the scan_completed entry claimed seq 0).
   - `test_scan_appends_journal_scan_completed_entry(tmp_path)`: bootstrap + scan; read journal via `iter_entries`; assert exactly one entry, kind=`scan_completed`, monotonic_seq=0, target_id=`state`, payload has `epic_count=0`, `story_count=0`, `task_count=0`.
   - `test_scan_idempotent_state_byte_equal(tmp_path)`: bootstrap + scan + capture state.json bytes + scan again + capture bytes; assert byte-equality (state didn't change because artifact tree didn't change).
   - `test_scan_appends_one_journal_entry_per_call(tmp_path)`: bootstrap + scan + scan; assert journal has TWO entries, both kind=`scan_completed`, with `monotonic_seq=0` and `monotonic_seq=1` respectively (per AC1's "idempotent in projection but NOT idempotent in journal" property).
   - `test_scan_scans_artifacts_when_present(tmp_path)`: bootstrap + create `01-Requirement/04-Epics/EPIC-test.json` with `{"id": "EPIC-test", "title": "test"}` content + scan; assert state.epics has key `EPIC-test`, `payload.epic_count == 1`. NOTE: this test depends on Story 1.15 having landed (`engine.scanner.scan` exists). If Story 1.15 has NOT landed at story-implement time, this test is `pytest.skip("requires Story 1.15 engine.scanner.scan")` and gets unskipped when 1.15 lands.
   - `test_scan_canonical_bytes_match_state_canonical_bytes(tmp_path)`: assert state.json bytes are produced by the same canonical-bytes serializer as `cli/init.py` (same byte format — sort_keys, no ascii escaping, compact separators, trailing newline). Use the new `state.state_to_canonical_bytes` helper if Task 4 factored it out; otherwise inline the canonical-bytes recipe.
   - `test_scan_json_mode_emits_canonical_envelope(tmp_path)`: bootstrap + invoke via CliRunner with `["--json", "scan"]`; assert `json.loads(result.stdout)` keys exactly match `{"command", "project_root", "phase", "epic_count", "story_count", "task_count", "next_monotonic_seq", "journal_entry_seq"}`.

2. **Unit tests** at `tests/unit/cli/test_status.py` (with `pytestmark = pytest.mark.unit`):
   - `test_status_refuses_when_state_not_initialized(tmp_path)`: same pattern as scan — exit 1 + stderr "not initialized".
   - `test_status_fresh_project_suggests_sdlc_start(tmp_path)`: bootstrap (via `run_init`); invoke status; capture stdout; assert it contains `Suggested next: /sdlc-start "<idea>"` (verbatim per epic AC).
   - `test_status_phase_line_renders_phase_1_requirement(tmp_path)`: bootstrap; invoke status; assert `"Phase: 1 (Requirement)"` in stdout.
   - `test_status_last_updated_never_when_journal_empty(tmp_path)`: bootstrap (init writes state.json + empty journal); invoke status WITHOUT scanning; assert "never" sentinel in stdout (or `null` in `--json` mode).
   - `test_status_last_updated_uses_latest_journal_ts(tmp_path)`: bootstrap + scan (which appends an entry); invoke status; assert the rendered timestamp matches the scan's RFC 3339 timestamp (parsed back to naive then compared via tolerance window).
   - `test_status_json_mode_emits_canonical_envelope(tmp_path)`: invoke `["--json", "status"]`; assert keys per AC2 trailing block.
   - `test_status_does_not_write_state_or_journal(tmp_path)`: bootstrap + scan + capture state.json + journal.log mtimes + invoke status + re-capture mtimes; assert mtimes unchanged (status is read-only).
   - `test_status_zero_args_invokes_help_or_status_per_typer_default(tmp_path)`: separate test confirming `sdlc status` standalone (no extra args) behaves correctly, NOT confused with `sdlc` (no args) which shows help per Story 1.16.
   - `test_status_unknown_phase_logs_warning(tmp_path)`: synthesize a state.json with `phase: 99` (manually write canonical bytes); invoke status; assert stdout contains `Phase: 99 (unknown)` AND `caplog` (with `caplog.set_level(logging.WARNING)`) has a record naming `phase=99`.

3. **Unit tests** at `tests/unit/cli/test_output.py` (with `pytestmark = pytest.mark.unit`):
   - `test_echo_strips_ansi_when_no_color_active(monkeypatch)`: build a fake ctx with `ctx.obj["no_color"] = True`; call `echo("\x1b[31merror\x1b[0m", ctx=ctx)`; assert the captured output has no escape codes.
   - `test_emit_json_canonical_bytes(capsys)`: call `emit_json("test", {"foo": 1, "bar": 2}, ctx=<json_ctx>)`; capture stdout; assert it equals `'{"bar":2,"command":"test","foo":1}\n'` (sorted keys, compact separators).
   - `test_emit_error_json_envelope(capsys)`: call `emit_error("ERR_TEST", "test message", ctx=<json_ctx>)`; assert raises `typer.Exit` with `exit_code == 1` (or whatever the table maps); capture stderr; assert JSON shape per AC4.4.
   - `test_emit_error_human_readable(capsys)`: same but in default mode; assert stderr contains "test message" plain-text.
   - `test_is_no_color_active_respects_flag_and_env(monkeypatch)`:
     ```python
     # Flag set, env unset → True
     # Flag unset, env set to "1" → True
     # Flag unset, env set to "" → False
     # Flag unset, env unset → False
     # Flag set, env unset → True (precedence: either disables)
     ```
     Use `monkeypatch.setenv` / `monkeypatch.delenv`.
   - `test_emit_error_sanitizes_secret_patterns_in_details(capsys)`: pass a `details` dict with a known secret pattern (e.g. `details={"api_key": "sk-test-..."}` matching one of `config/secrets.py:SECRET_PATTERNS`); assert the emitted JSON has the redaction marker substituted via `sdlc.config.sanitize_mapping`.

4. **Unit tests** at `tests/unit/cli/test_main.py` (extends Story 1.16's file):
   - `test_main_app_has_scan_subcommand`: invoke `["--help"]`; assert "scan" appears.
   - `test_main_app_has_status_subcommand`: invoke `["--help"]`; assert "status" appears.
   - `test_main_app_no_color_flag_recognized`: invoke `["--no-color", "--version"]`; assert exit_code == 0; assert no ANSI in output.
   - `test_main_app_json_flag_emits_json_for_version`: invoke `["--json", "--version"]`; parse stdout as JSON; assert `payload["command"] == "version"` and `payload["version"] == sdlc.__version__`.
   - `test_no_color_env_var_disables_color(monkeypatch)`: set `NO_COLOR=1` via monkeypatch; invoke `["status"]` (after bootstrap); assert no ANSI in output.

5. **Parametrized integration test** at `tests/integration/test_no_color_every_command.py` (with `pytestmark = pytest.mark.integration`):
   - The test from AC3.6 — every command × every no-color signal (flag, env, both) → zero ANSI on stdout AND stderr.

6. **Integration test** at `tests/integration/test_walking_skeleton_e2e.py` (with `pytestmark = pytest.mark.integration` and `pytestmark = pytest.mark.e2e` if dual-marked):
   - `test_walking_skeleton_init_status_phase_1_no_progress`: in tmp_path, `subprocess.run(["uv", "run", "sdlc", "init"], cwd=tmp_path)`; assert exit 0. Then `subprocess.run(["uv", "run", "sdlc", "status"], cwd=tmp_path)`; assert exit 0 + stdout contains `"Phase: 1"` AND `"Suggested next: /sdlc-start"` — closing Architecture §1408's "First demonstrable behaviour" gate. SKIP on Windows when `shutil.which("uv") is None`.
   - `test_walking_skeleton_init_scan_status_shows_zero_counts`: same but with `scan` between init and status; assert stdout still says "0 epics" or equivalent zero-state framing.

7. **Integration test** at `tests/integration/test_scan_journal_seq_continuity.py` (with `pytestmark = pytest.mark.integration`):
   - `test_seq_continuity_across_init_scan_scan`: bootstrap; scan; assert journal has 1 entry with monotonic_seq=0; scan again; assert journal has 2 entries with seqs 0, 1 (no gaps, monotonic). State.next_monotonic_seq after second scan == 2.
   - `test_journal_entry_referential_integrity`: read journal entries; assert each entry's `before_hash` equals the `after_hash` of the entry whose seq is one less (chain-of-hashes property — except entry seq=0 whose before_hash matches the pre-scan state.json hash, which for `sdlc init`-only state is `sha256(canonical_init_bytes)`).

8. **Coverage gate**: new modules `cli/scan.py`, `cli/status.py`, `cli/output.py` (post-expansion) MUST reach ≥ 90% line coverage from unit + integration suites combined. Existing global `--cov-fail-under=90` (`pyproject.toml:177`) enforces this.

**And** all new test files include `from __future__ import annotations` as the first non-comment line + the module-level `pytestmark` declaration. Test classes are NOT used (project convention; bare functions only).

**And** the existing `tests/unit/cli/test_init.py` (Story 1.16) is updated to pass `ctx=None` explicitly OR a fake-ctx fixture in the new tests — backward-compat with Story 1.16 tests is preserved.

**AC8 — ADR-020 records the CLI scan/status design + accessibility flag contract**

**Given** NFR-MAINT-5 ("every load-bearing decision recorded as an ADR"),

**When** Story 1.17 lands,

**Then** `docs/decisions/ADR-020-cli-scan-status-accessibility-flags.md` is authored using `docs/decisions/adr-template.md` covering:

1. **Status:** Accepted, dated to story-implement day.
2. **Context:** FR3, FR44, NFR-A11Y-4 mapping; Story 1.15 (engine scanner) provides the read path; Story 1.16 (cli skeleton + init) provides the entry shell; Story 1.17 closes the v0.2 walking-skeleton end state per Architecture §1408.
3. **Decision:**
   - `cli/scan.py` is a thin wrapper over `engine.scanner.scan` that wires state-write + journal-append (per Story 1.15 dev notes' "thin wrapper" plan at line 558-564).
   - `cli/status.py` is read-only — projects state + last journal entry into a resume card.
   - The "Suggested next" computation is a v1.17 stub that handles fresh-project explicitly + falls through to `"sdlc scan"` for all other states; Story 4.x's `engine/auto_loop.py` owns the rich computation.
   - `cli/output.py` is expanded to provide `echo`, `emit_json`, `emit_error`, `make_console`, `is_no_color_active`. The error envelope per Architecture §549 is centralized here.
   - `--no-color` is a global Typer flag; `NO_COLOR` env var is honored per the no-color.org informal standard. The two are OR'd (either disables color).
   - `--json` is a global Typer flag; per-command output schemas are documented in the ADR + in `cli/output.py` docstring.
   - `rich>=13,<15` is added as a direct dep at v1.17 (deferred from Story 1.16 per the "first-direct-consumer-owns-the-direct-dep" pattern).
   - `NO_COLOR` is added to `config/env.py:ENV_EXACT_ALLOWLIST`.
   - The `state_to_canonical_bytes` helper is added to `state/__init__.py` so init + scan share one canonical-bytes contract.
4. **Alternatives considered:**
   - `--color=always|auto|never` tri-state flag: rejected — additional complexity; the no-color.org standard converged on a binary signal; v2.x can extend if needed.
   - Per-command `--json` flags (instead of global): rejected — duplicates the flag definition across N subcommands; global flag with eager parsing is the Typer idiom (typer.tiangolo.com/tutorial/options).
   - Keep `cli/output.py` as a stub and inline the rich console inside each subcommand: rejected — drift surface; centralizing in `cli/output.py` per Architecture §792 is the locked design.
   - Compute `last_updated_ts` from state.json's mtime: rejected — mtime is filesystem-dependent and unstable; journal `ts` is the canonical "last action" timestamp. Architecture §574's atomic write protocol updates state.json mtime even when content is byte-identical (rename happens regardless), which would falsely advance the "last updated" indicator on no-op scans.
   - Have `sdlc scan` skip the journal append when state is byte-identical (no-op scan): rejected — the journal is an audit log of OBSERVATIONS, not just MUTATIONS; recording every scan call (even no-op ones) is correct per ADR-014's "first entry corresponds to the first state mutation" interpretation extended to "every CLI-driven state observation appends an entry". This is a subtle decision; ADR-020 explicitly reframes ADR-014's invariant.
   - Use `time.time()` for the `ts` field: rejected per Architecture §490; `datetime.datetime.now(datetime.timezone.utc)` is the canonical wall-clock reader.
   - Add a `force_color` opposite flag: rejected for v1.17; if a user explicitly wants color in a piped context, they un-set `NO_COLOR` and don't pass `--no-color`. v1.x can add `--color` if user feedback warrants.
5. **Consequences:**
   - The v0.2 walking-skeleton ship signal (Architecture §1408) is now end-to-end demonstrable: `pip install sdlc-framework && sdlc init && sdlc status` shows "Phase 1, no progress yet".
   - The CLI is a11y-friendly per NFR-A11Y-4: `--no-color` and `--json` work on every command. Future commands (`trace`, `replay`, `logs`, `dashboard`, `migrate-vN`) inherit this for free via the global flag plumbing.
   - The error envelope is now stable per major version. Story 1.21's "Wire-Format v1.0 Lock" gate includes the CLI output schemas (per AC4.5's `_ERR_CODE_TO_EXIT_CODE` + per-command JSON schemas) — additions after v1.0 require ADR amendment.
   - The `rich` direct dep adds ~150 KB to the wheel install size. Cold-start regression: rich's first import is ~20 ms; lazy-loading via `make_console`'s deferred `from rich.console import Console` keeps the `--version` path cold-start unchanged.
   - The `NO_COLOR` allow-list addition is the SECOND env var in `ENV_EXACT_ALLOWLIST` after `GH_TOKEN` (Story 1.8). Future story-driven additions follow the same pattern: name the var, document the use case, add the allow-list line + comment with story attribution.
6. **Revisit-by:** Story 1.21 (wire-format v1 lock — CLI output schemas freeze; per-command JSON shape changes after that point require RFC + ADR amendment).
7. **References:** Architecture §117 (FR1-FR5), §349 (Decision B5), §388 (v0.2 sequence), §549-§559 (error envelope), §674-§680 (CLI output conventions), §791-§794 (cli/main + output + exit_codes), §799 (cli/scan.py), §801 (cli/status.py), §815 (engine/scanner.py), §1133 (FR3 mapping), §1170 (FR44 mapping), §1408 (v0.2 first-demo gate). PRD §FR3 (line 725), §FR44 (line 784), §NFR-A11Y-4 (line 892), §NFR-PERF-1 (line 810). ADR-013 (atomic state write), ADR-014 (journal append-only), ADR-015 (state projection — Story 1.12, if landed), ADR-018 (engine scanner — Story 1.15), ADR-019 (cli skeleton + Typer — Story 1.16). The no-color.org informal standard (https://no-color.org/) for `NO_COLOR` env var semantics.

**And** `docs/decisions/index.md` gains the row `| [020](ADR-020-cli-scan-status-accessibility-flags.md) | CLI scan + status + --no-color + --json + rich dep | 1.17 | Accepted |` after ADR-019's row. If 015-019 haven't all shipped at story-implement time, take the next free number.

## Tasks / Subtasks

- [ ] **Task 1: Pre-flight verification of dependencies, environment, and prior-story state (AC: all)**
  - [ ] Verify Story 1.10 deliverables on disk: `src/sdlc/state/atomic.py` exists and exports `write_state_atomic_sync` (sprint-status `1-10: done`). Smoke: `uv run python -c "from sdlc.state import State, write_state_atomic_sync, read_state; print('ok')"`. POSIX-only on Linux/macOS; on Windows expect the `NotImplementedError` shim per `state/__init__.py:13-20` — that's the supported posture.
  - [ ] Verify Story 1.11 deliverables on disk: `src/sdlc/journal/__init__.py` exports `append_sync` and `iter_entries`. Smoke: `uv run python -c "from sdlc.journal import append_sync, iter_entries; print('ok')"`. Story 1.11 shows `review` per sprint-status snapshot 2026-05-08; Story 1.17 hard-depends on `append_sync` so this is a blocking dep — if 1.11 is still in `review` at story-implement time, gate 1.17 implementation behind 1.11 reaching `done`.
  - [ ] Verify Story 1.12 deliverables on disk: `src/sdlc/state/projection.py:project_from_journal` exists. Smoke: `uv run python -c "from sdlc.state import project_from_journal; print('ok')"`. Story 1.17's `cli/status.py` does NOT call `project_from_journal` directly (it uses `read_state` for the cached projection + `iter_entries` for the last-entry timestamp), but the existence is a sanity check that the substrate is consistent.
  - [ ] Verify Story 1.15 deliverables on disk: `src/sdlc/engine/__init__.py` exports `scan` and `engine/scanner.py:scan(project_root: Path) -> State` exists with the AC1 contract. Smoke: `uv run python -c "from sdlc.engine import scan; print(scan)"`. Story 1.17 hard-depends on this. If Story 1.15 has NOT landed at story-implement time (sprint-status 2026-05-08 says `1-15: ready-for-dev`), gate 1.17 dev behind 1.15 reaching `done` — there is no "scan-stub" fallback for 1.17 because the entire AC1 contract requires the real scanner.
  - [ ] Verify Story 1.16 deliverables on disk: `src/sdlc/cli/main.py` (with `app` Typer instance), `src/sdlc/cli/init.py` (with `run_init`), `src/sdlc/cli/output.py` (stub with `echo`), `src/sdlc/cli/exit_codes.py` (with constants), `src/sdlc/cli/version.py` (with `get_version`). Smoke: `uv run sdlc --version` prints `sdlc 0.0.0` exit 0. If 1.16 has NOT landed (sprint-status `1-16: ready-for-dev`), gate 1.17 behind 1.16 reaching `done` — the entire CLI architecture this story extends is owned by 1.16.
  - [ ] Verify boundary-linter location: `scripts/check_module_boundaries.py` has `MODULE_DEPS["cli"]` widened by Story 1.16 to include `state`, `journal`, `contracts`, `ids`. Confirm via `grep -A5 '"cli": ModuleSpec' scripts/check_module_boundaries.py`. Story 1.17 does NOT widen further — the existing widening covers `cli/scan.py` (uses `state`, `journal`) and `cli/status.py` (uses `state`, `journal`, `contracts`).
  - [ ] Verify ADR numbering: ADRs 013, 014 are landed (Stories 1.10, 1.11); ADRs 015 (Story 1.12), 016 (1.13), 017 (1.14), 018 (1.15), 019 (1.16) are in flight per their stories' AC7-AC8. Story 1.17 (this story) authors **ADR-020**. Take next free number after the most recent ADR on disk.
  - [ ] Verify `pyproject.toml [project] dependencies` includes `typer>=0.12,<1` (Story 1.16). Confirm via `grep typer pyproject.toml`. Story 1.17 ADDS `rich>=13,<15` per AC5.6. Confirm `rich` is NOT already directly listed (it's a transitive dep of typer in 1.16).
  - [ ] Verify `src/sdlc/cli/scan.py` and `src/sdlc/cli/status.py` do NOT exist on disk: `test -f src/sdlc/cli/scan.py && echo "ABORT" || echo "ok, fresh"`. If they exist (half-merged earlier story), HALT and reconcile manually before proceeding.
  - [ ] Verify `tests/unit/cli/test_scan.py`, `test_status.py`, `test_output.py` do NOT exist: `test -f tests/unit/cli/test_scan.py && echo "ABORT" || echo "ok"`.
  - [ ] Verify the existing pre-commit hooks pass on `main`: `uv run pre-commit run --all-files`. Establish a green baseline before mutating.
  - [ ] Confirm the Story 1.16 walking-skeleton smoke works: in a tmp dir, `git init && uv run sdlc init && uv run sdlc --version`. Both succeed. Story 1.17 extends this with `sdlc scan` + `sdlc status` working too.

- [ ] **Task 2: Add `rich` direct dep + widen `NO_COLOR` allow-list (AC: #5.6, #3.3)**
  - [ ] Open `pyproject.toml`. In `[project] dependencies`, add `"rich>=13,<15"` after `"typer>=0.12,<1"`. Final block:
    ```toml
    dependencies = [
        "pydantic>=2,<3",
        "pyyaml>=6,<7",
        "typer>=0.12,<1",
        "rich>=13,<15",     # cap: rich 14→15 has not landed; defensive guard. Direct dep added in Story 1.17 per cli/output.py rich console (AC5.6).
    ]
    ```
  - [ ] Run `uv lock` to refresh `uv.lock`. Commit the lock change in the same commit as the dep addition.
  - [ ] Smoke-test the lock: `uv sync --frozen --group dev`; assert success. `uv run python -c "import rich; print(rich.__version__)"` confirms direct import resolves.
  - [ ] Open `src/sdlc/config/env.py`. Update line 9 (`ENV_EXACT_ALLOWLIST`) to include `NO_COLOR`:
    ```python
    ENV_EXACT_ALLOWLIST: Final[frozenset[str]] = frozenset({"GH_TOKEN", "NO_COLOR"})
    # NO_COLOR added in Story 1.17 per no-color.org informal standard for accessibility-friendly CLI output (NFR-A11Y-4).
    ```
  - [ ] Update `src/sdlc/config/env.py` docstring on `read_env` to mention `NO_COLOR`:
    ```python
    """...
    Allow-list per Architecture §671 + NFR-SEC-2 (prd.md:798):
    - prefix matches: SDLC_*, CLAUDE_*
    - exact matches: GH_TOKEN (consumed only by the pr-author specialist),
      NO_COLOR (consumed by cli/output.py for accessibility — Story 1.17)
    ...
    """
    ```
  - [ ] Add a unit test at `tests/unit/config/test_env.py` (extend if present from Story 1.8):
    ```python
    def test_read_env_allows_no_color() -> None:
        # Smoke: no_color in allow-list should not raise
        from sdlc.config import read_env
        # may return None if NO_COLOR is unset in test env; that's the success path
        result = read_env("NO_COLOR")
        assert result is None or isinstance(result, str)
    ```
  - [ ] Run `uv run pytest tests/unit/config/test_env.py -v` → green. Verify Story 1.8's existing tests still pass (no_color extension is purely additive; previous tests pinned `frozenset({"GH_TOKEN"})` and would fail — extend those assertions or use `>=` containment instead of `==` equality on the allow-list).

- [ ] **Task 3: Add `state_to_canonical_bytes` helper to `state/__init__.py` (AC: #1.4)**
  - [ ] Open `src/sdlc/state/__init__.py`. Add a new public helper that takes a `State` and returns the canonical bytes:
    ```python
    import json as _json  # alias to avoid shadowing user-facing 'json' module imports

    def state_to_canonical_bytes(state: State) -> bytes:
        """Serialize a State to canonical bytes (sort_keys, no ascii escaping, compact, trailing \\n).

        One source of truth shared by cli/init.py (Story 1.16) and cli/scan.py (Story 1.17)
        so the canonical-bytes contract cannot drift between the two writers. Mirrors the
        contract used by state/atomic.py's write protocol.
        """
        payload = state.model_dump(mode="json")
        return (
            _json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    ```
  - [ ] Update `__all__` to include the new helper. Final declaration (post-Story-1.17):
    ```python
    # Semantic order: model → write (async) → write (sync) → read → projection → canonicalizer; do NOT alphabetize.
    __all__ = (  # noqa: RUF022
        "State",
        "write_state_atomic",
        "write_state_atomic_sync",
        "read_state",
        "project_from_journal",
        "state_to_canonical_bytes",
    )
    ```
  - [ ] Add a unit test at `tests/unit/state/test_canonical_bytes.py`:
    - `test_canonical_bytes_round_trip`: `s = State()`; `b = state_to_canonical_bytes(s)`; `parsed = json.loads(b.decode("utf-8"))`; `s2 = State.model_validate(parsed)`; assert `s == s2`.
    - `test_canonical_bytes_byte_equal_across_calls`: `b1 = state_to_canonical_bytes(State())`; `b2 = state_to_canonical_bytes(State())`; assert `b1 == b2` (deterministic).
    - `test_canonical_bytes_sorted_keys`: assert key order in bytes is alphabetical (`epics` before `next_monotonic_seq` before `phase` before `schema_version` before `stories` before `tasks` — assuming Story 1.15's State extension landed; otherwise just `epics, next_monotonic_seq, schema_version`).
    - `test_canonical_bytes_trailing_newline`: assert `state_to_canonical_bytes(State()).endswith(b"\n")`.
    - `test_canonical_bytes_no_ascii_escaping`: build a State whose epics dict contains a Unicode key (e.g. via `State(epics={"é": {}})` if that's allowed by the schema; else skip); assert the bytes contain the literal Unicode codepoint, NOT `é`.
  - [ ] Run `uv run pytest tests/unit/state/ -v` → green.

- [ ] **Task 4: Expand `cli/output.py` with rich console + JSON envelope + error envelope (AC: #3, #4, #5)**
  - [ ] Open `src/sdlc/cli/output.py`. Replace the Story-1.16 stub with the expanded module per AC5. Top-of-file order:
    1. Module docstring naming Story 1.17 + the public functions + the error code table.
    2. `from __future__ import annotations`.
    3. Stdlib imports (alphabetized): `import json`, `import os`, `import re`, `import sys`, `from collections.abc import Mapping`, `from types import MappingProxyType`, `from typing import Final, NoReturn`.
    4. Third-party imports: `import typer`. (Defer `from rich.console import Console` to inside `make_console` to avoid module-level rich import for cold-start budget.)
    5. SDLC imports: `from sdlc.config import sanitize_mapping`.
  - [ ] Add module-level constants:
    ```python
    _ANSI_RE: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    _NO_COLOR_ENV: Final[str] = "NO_COLOR"
    _ERR_CODE_TO_EXIT_CODE: Final[Mapping[str, int]] = MappingProxyType(
        {
            "ERR_NOT_INITIALIZED": 1,
            "ERR_ALREADY_INITIALIZED": 1,
            "ERR_USER_INPUT": 1,
            "ERR_SCAN_FAILED": 2,
            "ERR_JOURNAL_APPEND_FAILED": 2,
            "ERR_STATE_WRITE_FAILED": 2,
            "ERR_INFRASTRUCTURE": 3,
        }
    )
    _DEFAULT_EXIT_CODE: Final[int] = 1  # fallback for unknown ERR_CODE values
    _SCAN_OUTPUT_SCHEMA: Final[str] = "v1"
    _STATUS_OUTPUT_SCHEMA: Final[str] = "v1"
    ```
  - [ ] Implement `is_no_color_active(ctx: typer.Context | None) -> bool`:
    ```python
    def is_no_color_active(ctx: typer.Context | None) -> bool:
        """True if --no-color flag is set OR NO_COLOR env is non-empty."""
        flag = bool(ctx is not None and ctx.obj is not None and ctx.obj.get("no_color", False))
        env = os.environ.get(_NO_COLOR_ENV, "") != ""
        return flag or env
    ```
    Note: `os.environ.get` direct read here (not `sdlc.config.read_env`) is acceptable in `cli/` per Architecture §492's `cli/` carve-out; the allow-list in `config/env.py` is widened (Task 2) so a future caller using `read_env("NO_COLOR")` also resolves cleanly.
  - [ ] Implement `_strip_ansi(s: str) -> str`:
    ```python
    def _strip_ansi(s: str) -> str:
        return _ANSI_RE.sub("", s)
    ```
  - [ ] Implement the expanded `echo`:
    ```python
    def echo(message: str, *, err: bool = False, ctx: typer.Context | None = None) -> None:
        """Emit ``message`` on stdout (or stderr if err=True).

        - If ctx.obj["json"] is True: NO-OP (JSON mode silences plain channels).
        - If is_no_color_active(ctx): strip ANSI before emission.
        - Otherwise: forward to typer.echo verbatim.
        """
        if ctx is not None and ctx.obj is not None and ctx.obj.get("json", False):
            return  # JSON mode: emit_json / emit_error own all output
        if is_no_color_active(ctx):
            message = _strip_ansi(message)
        typer.echo(message, err=err)
    ```
  - [ ] Implement `emit_json`:
    ```python
    def emit_json(command: str, payload: Mapping[str, object], *, ctx: typer.Context) -> None:
        """Emit canonical-bytes JSON document on stdout.

        Schema: payload is augmented with command field; sorted keys, no ascii escaping,
        compact separators, trailing newline (matches state.atomic canonical-bytes contract).
        """
        merged: dict[str, object] = dict(payload)
        merged.setdefault("command", command)
        canonical = json.dumps(merged, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        typer.echo(canonical)  # typer.echo adds the trailing newline
    ```
  - [ ] Implement `emit_error`:
    ```python
    def emit_error(
        code: str,
        message: str,
        *,
        ctx: typer.Context,
        details: Mapping[str, object] | None = None,
    ) -> NoReturn:
        """Emit error envelope per Architecture §549; raise typer.Exit with mapped code.

        - JSON mode: stderr gets {"error": {code, message, details, exit_code}} canonical bytes.
        - Default mode: stderr gets a plain-text "sdlc: <message>" line.
        """
        exit_code = _ERR_CODE_TO_EXIT_CODE.get(code, _DEFAULT_EXIT_CODE)
        json_mode = bool(ctx.obj is not None and ctx.obj.get("json", False))
        if json_mode:
            safe_details = sanitize_mapping(dict(details)) if details else {}
            envelope = {
                "error": {
                    "code": code,
                    "message": message,
                    "details": safe_details,
                    "exit_code": exit_code,
                }
            }
            canonical = json.dumps(envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            typer.echo(canonical, err=True)
        else:
            text = f"sdlc: {message}"
            if is_no_color_active(ctx):
                text = _strip_ansi(text)
            typer.echo(text, err=True)
        raise typer.Exit(code=exit_code)
    ```
  - [ ] Implement `make_console`:
    ```python
    def make_console(ctx: typer.Context) -> "Console":
        """Lazy rich Console factory; caches per ctx.obj.

        Deferred rich import keeps the --version cold-start budget under 200 ms
        (Architecture §488); rich is imported only when a command actually styles output.
        """
        if ctx.obj is None:
            ctx.ensure_object(dict)
        cached = ctx.obj.setdefault("_console", None)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        from rich.console import Console  # deferred per Architecture §488
        no_color = is_no_color_active(ctx)
        console = Console(no_color=no_color, force_terminal=False)
        ctx.obj["_console"] = console
        return console
    ```
    NOTE: the `# type: ignore[no-any-return]` annotation is on the cache-hit return because mypy strict can't introspect the rich Console's type from the cached `Optional[Any]` slot. If mypy errors, narrow with `assert isinstance(cached, Console)` after the deferred import.
  - [ ] Set the public surface:
    ```python
    __all__ = (  # noqa: RUF022
        "echo",
        "emit_json",
        "emit_error",
        "make_console",
        "is_no_color_active",
    )
    ```
  - [ ] Verify LOC ≤ 200. If exceeded, factor `_strip_ansi` + `is_no_color_active` into `cli/_output_helpers.py`.
  - [ ] Run `uv run mypy --strict src/sdlc/cli/output.py` → must pass.
  - [ ] Run `uv run ruff check src/sdlc/cli/output.py` → must pass.
  - [ ] Run `uv run ruff format --check src/sdlc/cli/output.py` → must pass.

- [ ] **Task 5: Implement `cli/scan.py` (AC: #1)**
  - [ ] Create `src/sdlc/cli/scan.py`. Top-of-file order:
    1. Module docstring: "`sdlc scan` implementation (FR3, Architecture §799, §1133, Decision A4 + B5). Wraps `engine.scanner.scan` with state.json atomic write + journal scan_completed append."
    2. `from __future__ import annotations`.
    3. Stdlib imports (alphabetized): `import datetime`, `import hashlib`, `import logging`, `import subprocess`, `import sys`, `from pathlib import Path`, `from typing import Final`.
    4. Third-party imports: `import typer`.
    5. SDLC imports: `from sdlc.cli.exit_codes import EXIT_USER_ERROR`, `from sdlc.cli.output import echo, emit_error, emit_json`, `from sdlc.contracts.journal_entry import JournalEntry`. Engine + state + journal imports DEFERRED to function bodies per Architecture §488.
    6. `_logger = logging.getLogger(__name__)`.
    7. Constants:
       ```python
       _STATE_PATH_REL: Final[str] = ".claude/state/state.json"
       _JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
       _SCAN_KIND: Final[str] = "scan_completed"
       _ACTOR: Final[str] = "cli"
       _STATE_TARGET_ID: Final[str] = "state"
       ```
  - [ ] Implement `_get_repo_root_or_cwd() -> Path`:
    - Same pattern as Story 1.16's `cli/init.py` helper. Try `subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False, timeout=5)`; on success return `Path(result.stdout.strip()).resolve()`; on any failure return `Path.cwd().resolve()`. Catch `OSError`, `subprocess.SubprocessError`, `FileNotFoundError`.
    - If Story 1.16 factored this into `cli/_paths.py:_get_repo_root_or_cwd`, IMPORT it instead — DO NOT duplicate. Verify the helper exists; if it doesn't, define inline (single-use is acceptable, Story 1.16's dev notes accept inline duplication for v1.17).
  - [ ] Implement `_compute_sha256_of_file(path: Path) -> str | None`:
    ```python
    def _compute_sha256_of_file(path: Path) -> str | None:
        """Return 'sha256:<hex>' or None if the file does not exist."""
        if not path.exists():
            return None
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return f"sha256:{digest}"
    ```
  - [ ] Implement `_now_rfc3339_utc() -> str`:
    ```python
    def _now_rfc3339_utc() -> str:
        """RFC 3339 UTC with millisecond precision matching JournalEntry _RFC3339_UTC regex."""
        now = datetime.datetime.now(datetime.timezone.utc)
        # %f gives microseconds; trim to milliseconds.
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    ```
    Verify the format matches `contracts/journal_entry.py:16` regex `r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"`.
  - [ ] Implement `_write_state_to_disk(state: State, state_path: Path) -> None`:
    ```python
    def _write_state_to_disk(state: "State", state_path: Path) -> None:
        from sdlc.state import state_to_canonical_bytes  # deferred
        canonical = state_to_canonical_bytes(state)
        if sys.platform == "win32":
            _logger.warning(
                "sdlc scan on Windows uses non-atomic write fallback for state.json "
                "(POSIX-only atomic protocol unavailable). Recommended: WSL2."
            )
            state_path.write_bytes(canonical)
            return
        from sdlc.state import write_state_atomic_sync  # deferred POSIX-only
        write_state_atomic_sync(state, target=state_path)
    ```
    NOTE: `write_state_atomic_sync` signature: verify against `state/atomic.py` and adjust if it takes `(state, target)` vs `(state, path)` vs other — Story 1.10 owns the canonical signature.
  - [ ] Implement `_append_scan_journal_entry(...)`:
    ```python
    def _append_scan_journal_entry(
        *,
        journal_path: Path,
        seq: int,
        ts: str,
        before_hash: str | None,
        after_hash: str,
        epic_count: int,
        story_count: int,
        task_count: int,
    ) -> None:
        from sdlc.journal import append_sync  # deferred
        entry = JournalEntry(
            schema_version=1,
            monotonic_seq=seq,
            ts=ts,
            actor=_ACTOR,
            kind=_SCAN_KIND,
            target_id=_STATE_TARGET_ID,
            before_hash=before_hash,
            after_hash=after_hash,
            payload={
                "epic_count": epic_count,
                "story_count": story_count,
                "task_count": task_count,
            },
        )
        append_sync(entry, journal_path=journal_path)
    ```
    On Windows, `append_sync` raises `JournalError` per `journal/__init__.py:31`; the caller catches it and emits via `emit_error("ERR_JOURNAL_APPEND_FAILED", ...)`.
  - [ ] Implement the public `run_scan(*, ctx: typer.Context) -> None`:
    ```python
    def run_scan(*, ctx: typer.Context) -> None:
        from sdlc.engine import scan as engine_scan  # deferred
        from sdlc.errors import JournalError, StateError
        from sdlc.state import read_state

        root = _get_repo_root_or_cwd()
        state_path = root / _STATE_PATH_REL
        journal_path = root / _JOURNAL_PATH_REL
        if not state_path.exists():
            emit_error(
                "ERR_NOT_INITIALIZED",
                f"project not initialized at {root}; run `sdlc init` first",
                ctx=ctx,
                details={"project_root": str(root)},
            )

        # Pre-scan: hash the existing state.json to populate journal before_hash.
        before_hash = _compute_sha256_of_file(state_path)

        # Pre-scan: read the existing state to learn the seq counter (= the seq this scan claims).
        try:
            pre_state = read_state(state_path)  # State pydantic model
        except (OSError, StateError) as exc:
            emit_error(
                "ERR_STATE_WRITE_FAILED",  # treat read as "state file unrecoverable" → framework failure
                f"failed to read existing state.json: {exc}",
                ctx=ctx,
                details={"path": str(state_path)},
            )
        seq = pre_state.next_monotonic_seq

        # Run the pure scanner.
        try:
            scanned = engine_scan(project_root=root)
        except StateError as exc:
            emit_error(
                "ERR_SCAN_FAILED",
                f"scan failed: {exc}",
                ctx=ctx,
                details=dict(exc.details) if hasattr(exc, "details") else {},
            )

        # Bump the seq counter on the new state to claim slot `seq` for the journal entry.
        new_state = scanned.model_copy(update={"next_monotonic_seq": seq + 1})

        # Compute after_hash from the canonical bytes that will be written.
        from sdlc.state import state_to_canonical_bytes
        canonical_bytes = state_to_canonical_bytes(new_state)
        after_hash = f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"

        # Write state.json atomically.
        try:
            _write_state_to_disk(new_state, state_path)
        except (OSError, StateError) as exc:
            emit_error(
                "ERR_STATE_WRITE_FAILED",
                f"state write failed: {exc}",
                ctx=ctx,
                details={"path": str(state_path)},
            )

        # Append journal entry.
        ts = _now_rfc3339_utc()
        try:
            _append_scan_journal_entry(
                journal_path=journal_path,
                seq=seq,
                ts=ts,
                before_hash=before_hash,
                after_hash=after_hash,
                epic_count=len(new_state.epics),
                story_count=len(new_state.stories),
                task_count=len(new_state.tasks),
            )
        except JournalError as exc:
            emit_error(
                "ERR_JOURNAL_APPEND_FAILED",
                f"journal append failed: {exc}",
                ctx=ctx,
                details={"path": str(journal_path), "seq": seq},
            )

        # Emit output.
        if ctx.obj.get("json", False):
            emit_json(
                "scan",
                {
                    "project_root": str(root),
                    "phase": new_state.phase if hasattr(new_state, "phase") else 1,
                    "epic_count": len(new_state.epics),
                    "story_count": len(new_state.stories),
                    "task_count": len(new_state.tasks),
                    "next_monotonic_seq": new_state.next_monotonic_seq,
                    "journal_entry_seq": seq,
                },
                ctx=ctx,
            )
        else:
            phase = new_state.phase if hasattr(new_state, "phase") else 1
            echo(
                f"sdlc scan: {root} — phase {phase}, "
                f"{len(new_state.epics)} epics, {len(new_state.stories)} stories, "
                f"{len(new_state.tasks)} tasks (state.json refreshed)",
                ctx=ctx,
            )
    ```
    NOTE on `state.phase`: if Story 1.15's State extension has NOT yet landed at story-implement time (`phase` attribute may not exist on the `State` model), the `hasattr(new_state, "phase")` guard returns the v1.10-minimal-shape compatible value. Once 1.15 lands, the `if hasattr` branches collapse to direct `new_state.phase` access — refactor in a follow-up.
  - [ ] Verify LOC ≤ 250 for `cli/scan.py`. If exceeded, factor `_compute_sha256_of_file`, `_now_rfc3339_utc`, `_get_repo_root_or_cwd` into `cli/_scan_helpers.py`.
  - [ ] **Forbidden patterns at code-review time**:
    - `print()` — use `cli/output.py:echo` / `emit_json` / `emit_error`.
    - `time.time()` for ordering — use `monotonic_seq` from state; wall-clock UTC for `ts` only via `datetime.datetime.now(datetime.timezone.utc)`.
    - `os.environ[...]` direct access (the env reads happen in `cli/output.py` only).
    - Bare `except:` / `except Exception:` — narrow catches only.
    - Mutating function arguments — `model_copy(update=...)` is the canonical immutable-update pattern.
  - [ ] Run `uv run mypy --strict src/sdlc/cli/scan.py` → must pass.

- [ ] **Task 6: Implement `cli/status.py` (AC: #2)**
  - [ ] Create `src/sdlc/cli/status.py`. Top-of-file order:
    1. Module docstring: "`sdlc status` implementation (FR44, Architecture §801, §1170). Read-only resume card; projects state + last journal entry."
    2. `from __future__ import annotations`.
    3. Stdlib imports: `import datetime`, `import logging`, `import re`, `from collections.abc import Mapping`, `from pathlib import Path`, `from types import MappingProxyType`, `from typing import Final, Optional`.
    4. Third-party imports: `import typer`.
    5. SDLC imports: `from sdlc.cli.output import echo, emit_error, emit_json, make_console`. State + journal imports DEFERRED.
    6. `_logger = logging.getLogger(__name__)`.
    7. Constants:
       ```python
       _STATE_PATH_REL: Final[str] = ".claude/state/state.json"
       _JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
       _PHASE_NAMES: Final[Mapping[int, str]] = MappingProxyType(
           {1: "Requirement", 2: "Architecture", 3: "Implementation"}
       )
       _NEVER_SENTINEL: Final[str] = "<never — run `sdlc scan`>"
       _PYPROJECT_NAME_RE: Final[re.Pattern[str]] = re.compile(r'^name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
       ```
  - [ ] Implement `_get_repo_root_or_cwd()`: same as Story 1.16 / Story 1.17 Task 5. Share via `cli/_paths.py` if present; else inline.
  - [ ] Implement `_resolve_project_name(root: Path) -> str`:
    ```python
    def _resolve_project_name(root: Path) -> str:
        """Best-effort project name from pyproject.toml [project] name; fallback to dir basename."""
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            try:
                text = pyproject.read_text(encoding="utf-8")
            except OSError:
                return root.name
            m = _PYPROJECT_NAME_RE.search(text)
            if m:
                return m.group(1)
        return root.name
    ```
  - [ ] Implement `_get_last_journal_ts(journal_path: Path) -> str | None`:
    ```python
    def _get_last_journal_ts(journal_path: Path) -> str | None:
        """Return the latest entry's ts (RFC 3339 UTC string) or None for empty/missing journal."""
        from sdlc.journal import iter_entries  # deferred

        if not journal_path.exists():
            return None
        last_ts: str | None = None
        for entry in iter_entries(journal_path):
            last_ts = entry.ts  # entries are sorted by monotonic_seq per Story 1.11 reader contract
        return last_ts
    ```
  - [ ] Implement `_format_ts_local(ts: str) -> str`:
    ```python
    def _format_ts_local(ts: str) -> str:
        """RFC 3339 UTC string → local-timezone human string. 3.10-compatible."""
        # Python 3.10's fromisoformat doesn't accept trailing Z; substitute.
        normalized = ts.replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(normalized)
        except ValueError:
            return ts  # fallback: emit raw
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d %H:%M:%S %Z")
    ```
  - [ ] Implement `_compute_suggested_next(state: "State") -> str`:
    ```python
    def _compute_suggested_next(state: "State") -> str:
        """Minimal v1.17 stub. Story 4.x's auto_loop owns the rich engine.
        Fresh-project case is the only AC-tested branch.
        """
        phase = getattr(state, "phase", 1)
        if phase == 1 and not state.epics:
            return '/sdlc-start "<idea>"'
        # Fall through: sensible default.
        return "sdlc scan"
    ```
  - [ ] Implement `run_status(*, ctx: typer.Context) -> None`:
    ```python
    def run_status(*, ctx: typer.Context) -> None:
        from sdlc.errors import StateError
        from sdlc.state import read_state

        root = _get_repo_root_or_cwd()
        state_path = root / _STATE_PATH_REL
        journal_path = root / _JOURNAL_PATH_REL
        if not state_path.exists():
            emit_error(
                "ERR_NOT_INITIALIZED",
                f"project not initialized at {root}; run `sdlc init` first",
                ctx=ctx,
                details={"project_root": str(root)},
            )

        try:
            state = read_state(state_path)
        except (OSError, StateError) as exc:
            emit_error(
                "ERR_STATE_WRITE_FAILED",
                f"failed to read state.json: {exc}",
                ctx=ctx,
                details={"path": str(state_path)},
            )

        project_name = _resolve_project_name(root)
        phase = getattr(state, "phase", 1)
        phase_name = _PHASE_NAMES.get(phase)
        if phase_name is None:
            _logger.warning("status: unknown phase %d (no name in _PHASE_NAMES)", phase)
            phase_name = "unknown"
        last_ts_raw = _get_last_journal_ts(journal_path)
        suggested_next = _compute_suggested_next(state)

        if ctx.obj.get("json", False):
            emit_json(
                "status",
                {
                    "project_name": project_name,
                    "project_root": str(root),
                    "phase": phase,
                    "phase_name": phase_name,
                    "last_updated_ts": last_ts_raw,  # null when journal empty
                    "epic_count": len(state.epics),
                    "story_count": len(state.stories) if hasattr(state, "stories") else 0,
                    "task_count": len(state.tasks) if hasattr(state, "tasks") else 0,
                    "suggested_next": suggested_next,
                    "next_monotonic_seq": state.next_monotonic_seq,
                },
                ctx=ctx,
            )
            return

        # Human-readable card.
        last_ts_display = _format_ts_local(last_ts_raw) if last_ts_raw else _NEVER_SENTINEL
        echo(f"sdlc status — {project_name}", ctx=ctx)
        echo(f"Phase: {phase} ({phase_name})", ctx=ctx)
        echo(f"Last updated: {last_ts_display}", ctx=ctx)
        echo(f"Suggested next: {suggested_next}", ctx=ctx)
    ```
  - [ ] Verify LOC ≤ 200. Optional rich-console styling can be added later (v1.x); v1.17 keeps the human-readable mode plain text routed through `echo` which is already a11y-friendly.
  - [ ] Run `uv run mypy --strict src/sdlc/cli/status.py` → must pass.

- [ ] **Task 7: Wire `scan` + `status` subcommands + global flags into `cli/main.py` (AC: #6)**
  - [ ] Open `src/sdlc/cli/main.py`. Update the imports at the top to add `import json`, `import os`, `import sys`. The `from sdlc.cli.version import get_version` stays.
  - [ ] Replace the existing `_version_callback` with the JSON-aware version per AC6.4:
    ```python
    def _version_callback(value: bool) -> None:
        if value:
            if "--json" in sys.argv:
                payload = json.dumps(
                    {"command": "version", "version": get_version()},
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                typer.echo(payload)
            else:
                typer.echo(f"sdlc {get_version()}")
            raise typer.Exit(code=0)
    ```
  - [ ] Replace the existing `_root` with the context-aware version per AC6.2:
    ```python
    @app.callback()
    def _root(
        ctx: typer.Context,
        version: bool = typer.Option(
            False, "--version", callback=_version_callback, is_eager=True,
            help="Print the installed version and exit.",
        ),
        no_color: bool = typer.Option(
            False, "--no-color", is_eager=True,
            help="Disable ANSI color in CLI output (NO_COLOR env var also honored).",
        ),
        json_output: bool = typer.Option(
            False, "--json", is_eager=True,
            help="Emit machine-readable JSON instead of human-readable output.",
        ),
    ) -> None:
        """SDLC framework CLI."""
        ctx.ensure_object(dict)
        ctx.obj["no_color"] = no_color or os.environ.get("NO_COLOR", "") != ""
        ctx.obj["json"] = json_output
    ```
  - [ ] Update the existing `init_command` to accept and pass `ctx`:
    ```python
    @app.command(name="init")
    def init_command(
        ctx: typer.Context,
        adopt: bool = typer.Option(False, "--adopt", help="...", hidden=True),
    ) -> None:
        """Initialize the SDLC framework in the current git repository."""
        if adopt:
            from sdlc.cli.output import emit_error
            emit_error(
                "ERR_USER_INPUT",
                "sdlc init --adopt is not implemented in v1.16 (Story 3.1+).",
                ctx=ctx,
            )
        from sdlc.cli.init import run_init  # deferred per Architecture §488
        run_init(ctx=ctx)
    ```
  - [ ] Add the `scan_command` and `status_command` per AC6.1:
    ```python
    @app.command(name="scan")
    def scan_command(ctx: typer.Context) -> None:
        """Refresh state.json from the artifact tree (FR3)."""
        from sdlc.cli.scan import run_scan  # deferred per Architecture §488
        run_scan(ctx=ctx)


    @app.command(name="status")
    def status_command(ctx: typer.Context) -> None:
        """Print the resume card with suggested next-action (FR44)."""
        from sdlc.cli.status import run_status  # deferred
        run_status(ctx=ctx)
    ```
  - [ ] Verify `cli/main.py` LOC ≤ 130. If exceeded, factor `_root` body into `cli/_main_helpers.py:initialize_context`.
  - [ ] Update `src/sdlc/cli/init.py:run_init` signature to accept `ctx: typer.Context | None = None` (default keeps Story 1.16's tests passing). Inside, branch on `ctx`:
    ```python
    def run_init(*, ctx: typer.Context | None = None) -> None:
        # ... existing scaffold logic ...
        # AT THE END, before the success echo block:
        if ctx is not None and ctx.obj is not None and ctx.obj.get("json", False):
            from sdlc.cli.output import emit_json
            emit_json(
                "init",
                {
                    "project_root": str(root),
                    "created": [<sorted list of relative paths>],
                },
                ctx=ctx,
            )
        else:
            # existing echo block; pass ctx for --no-color routing
            echo(f"Initialized SDLC framework in {root}", ctx=ctx)
            # ... etc ...
    ```
    The existing Story 1.16 echo lines change from `echo(...)` to `echo(..., ctx=ctx)`. The `ALREADY_INITIALIZED` refusal also routes through `emit_error` instead of direct stderr echo:
    ```python
    if _state_already_exists(root):
        from sdlc.cli.output import emit_error
        emit_error(
            "ERR_ALREADY_INITIALIZED",
            f"already initialized at {root}; use `sdlc scan` to refresh state.json",
            ctx=ctx,
            details={"project_root": str(root)},
        )
    ```
    NOTE: the message wording shifts from `"sdlc: already initialized at <root>; use \`sdlc scan\` to refresh state.json"` (Story 1.16's exact text) to `"already initialized at <root>; use \`sdlc scan\` to refresh state.json"` because `emit_error` prefixes `"sdlc: "`. The on-disk byte form is preserved.
  - [ ] Run `uv run mypy --strict src/sdlc/cli/main.py` and `uv run mypy --strict src/sdlc/cli/init.py` → both pass.
  - [ ] Smoke-test the wiring:
    ```bash
    cd $(mktemp -d)
    git init
    uv run sdlc --version
    uv run sdlc --json --version
    uv run sdlc init
    uv run sdlc scan
    uv run sdlc status
    uv run sdlc --no-color status
    uv run sdlc --json status
    NO_COLOR=1 uv run sdlc status
    ```
    Each command should exit 0 (after init) with shaped output.

- [ ] **Task 8: Tests — unit + integration + e2e (AC: #7)**
  - [ ] Create `tests/unit/cli/test_output.py` with `pytestmark = pytest.mark.unit`. Add the 6 tests from AC7.3. Use `pytest.MonkeyPatch` for env-var manipulation; build fake Typer contexts via `typer.Context(command=typer.core.TyperCommand("test"), parent=None)` or a lightweight fake-context fixture (consult Typer 0.12+ docs at typer.tiangolo.com/tutorial/commands/context/ for the canonical pattern).
  - [ ] Create `tests/unit/cli/test_scan.py` with `pytestmark = pytest.mark.unit`. Add the 8 tests from AC7.1. Use a `_initialize_test_project(tmp_path)` helper that calls `run_init(ctx=fake_ctx)` so each test starts from a known bootstrapped state. Helper:
    ```python
    def _initialize_test_project(tmp_path: Path, ctx: typer.Context | None = None) -> None:
        import os
        os.chdir(tmp_path)  # cli helpers resolve cwd; pytest's tmp_path is the safe scope
        from sdlc.cli.init import run_init
        run_init(ctx=ctx)
    ```
  - [ ] Create `tests/unit/cli/test_status.py` with `pytestmark = pytest.mark.unit`. Add the 9 tests from AC7.2. Use the same `_initialize_test_project` helper. The `unknown_phase` test synthesizes a state.json by writing canonical bytes manually: `(tmp_path / ".claude/state/state.json").write_text(json.dumps({"schema_version": 1, "next_monotonic_seq": 0, "phase": 99, "epics": {}, "stories": {}, "tasks": {}}, sort_keys=True))`.
  - [ ] Extend `tests/unit/cli/test_main.py` (Story 1.16) with the 5 tests from AC7.4. Reuse the existing `runner` / `app` fixtures.
  - [ ] Create `tests/integration/test_no_color_every_command.py` with `pytestmark = pytest.mark.integration`. Add the parametrized test from AC3.6. Use Typer's `CliRunner` (in-process) for speed; assert no ANSI in `result.stdout` AND `result.stderr` for every (cmd, no-color-signal) combination.
  - [ ] Create `tests/integration/test_walking_skeleton_e2e.py` with both `pytest.mark.integration` and `pytest.mark.e2e` markers (use `pytestmark = [pytest.mark.integration, pytest.mark.e2e]`). Add the two tests from AC7.6 using `subprocess.run(["uv", "run", "sdlc", ...], cwd=tmp_path)`. Skip on Windows when `shutil.which("uv") is None`.
  - [ ] Create `tests/integration/test_scan_journal_seq_continuity.py` with `pytestmark = pytest.mark.integration`. Add the two tests from AC7.7.
  - [ ] Run all new tests:
    ```bash
    uv run pytest tests/unit/cli/ -m unit -v
    uv run pytest tests/integration/test_no_color_every_command.py -v
    uv run pytest tests/integration/test_walking_skeleton_e2e.py -v
    uv run pytest tests/integration/test_scan_journal_seq_continuity.py -v
    ```
    All green.
  - [ ] Verify coverage: `uv run pytest tests/unit/cli/ tests/integration/test_no_color_every_command.py --cov=src/sdlc/cli --cov-report=term-missing`. The new `cli/scan.py`, `cli/status.py`, `cli/output.py` (post-expansion) MUST reach ≥ 90% line coverage. Uncovered lines acceptable: Windows-fallback branches (covered on Linux CI matrix cells), unreachable defensive paths.
  - [ ] Add a regression test for the `run_init` ctx-aware signature: `tests/unit/cli/test_init.py` (Story 1.16 file) gets a new test `test_init_with_ctx_emits_json_envelope_when_json_mode` that invokes `run_init` with a fake-ctx whose `json=True` and asserts canonical JSON on stdout.

- [ ] **Task 9: Author ADR-020 + update documentation (AC: #8)**
  - [ ] Determine the next free ADR number. Read `docs/decisions/index.md`. Story 1.17 takes the next number after the most recent ADR (typically 020 if 1.16's ADR-019 has landed; otherwise next-free).
  - [ ] Create `docs/decisions/ADR-020-cli-scan-status-accessibility-flags.md` using `docs/decisions/adr-template.md`. Populate per AC8 sections 1-7.
  - [ ] Update `docs/decisions/index.md`: add the row for ADR-020 after the most-recent ADR row.
  - [ ] Update `docs/CODEMAPS/cli-module.md` (Story 1.16 created this): add rows for `scan.py` and `status.py` with one-line responsibilities. Update the `output.py` row from "v1.16 stub: echo()" to "v1.17 expanded: echo, emit_json, emit_error, make_console, is_no_color_active".
  - [ ] Update `README.md` (if a "Quick Start" section exists from Story 1.16) to extend the demo:
    ```bash
    pip install sdlc-framework
    sdlc init
    sdlc status         # Phase 1, no progress yet
    sdlc scan           # refresh state from filesystem
    sdlc --no-color status   # accessibility-friendly mode
    sdlc --json status       # machine-readable for tooling
    ```

- [ ] **Task 10: Run the full quality gate stack and verify CI green (AC: all)**
  - [ ] `uv run ruff check src/ tests/ scripts/` → 0 errors. New `cli/scan.py`, `cli/status.py`, expanded `cli/output.py` MUST have `from __future__ import annotations`.
  - [ ] `uv run ruff format --check src/ tests/ scripts/` → all formatted.
  - [ ] `uv run mypy --strict src/` → 0 errors. All new code fully annotated; no `Any` leak through public surface.
  - [ ] `uv run pre-commit run --all-files` → all hooks pass:
    - `ruff-check`, `ruff-format`, `mypy-strict` (existing).
    - `boundary-validator` — verify the cli's existing widening (state, journal, contracts, ids per Story 1.16) covers `cli/scan.py` + `cli/status.py` + `cli/output.py`. No further widening needed.
    - `state-write-protocol-validator` (Story 1.10) — `cli/scan.py` calls `write_state_atomic_sync`; the validator's allowlist must include `cli/scan.py` (Story 1.16 added `cli/init.py`; this story adds `cli/scan.py`). If the allowlist is in `scripts/check_no_state_mutation.py`, add the entry per Story 1.16's pattern.
    - `journal-append-only-validator` (Story 1.11) — `cli/scan.py` calls `append_sync` which is the canonical writer; should not fire on canonical use.
    - `secret-hardcode-validator` (Story 1.8) — scoped to `^src/sdlc/.*\.py$`; no secrets in new files.
  - [ ] `uv run pytest tests/unit/cli/ -m unit -v` → all green.
  - [ ] `uv run pytest tests/integration/ -m integration -v` → all green (skipped where appropriate on Windows for subprocess tests).
  - [ ] Global `uv run pytest --cov=src --cov-fail-under=90` → coverage gate passes.
  - [ ] Confirm new files are tracked: `git status` → `src/sdlc/cli/scan.py`, `src/sdlc/cli/status.py` (new); `src/sdlc/cli/output.py`, `src/sdlc/cli/main.py`, `src/sdlc/cli/init.py`, `src/sdlc/state/__init__.py`, `src/sdlc/config/env.py`, `pyproject.toml`, `uv.lock` (modified). New tests: `tests/unit/cli/test_scan.py`, `test_status.py`, `test_output.py`, `tests/unit/state/test_canonical_bytes.py`, `tests/integration/test_no_color_every_command.py`, `test_walking_skeleton_e2e.py`, `test_scan_journal_seq_continuity.py`. Docs: `docs/decisions/ADR-020-cli-scan-status-accessibility-flags.md`, `docs/decisions/index.md` (modified), `docs/CODEMAPS/cli-module.md` (modified).
  - [ ] Run from a clean clone-equivalent: `git clean -fdx; uv sync --frozen --group dev; uv run pytest`. Everything must pass.
  - [ ] Smoke-test the actual user flow (Architecture §1408 walking-skeleton end state):
    ```bash
    cd $(mktemp -d)
    git init
    uv run sdlc init                     # creates canonical layout, exits 0
    uv run sdlc --version                # prints "sdlc 0.0.0", exits 0
    uv run sdlc status                   # "Phase: 1 (Requirement)", "Last updated: <never>", "Suggested next: /sdlc-start \"<idea>\""
    uv run sdlc scan                     # refreshes state, appends scan_completed entry
    uv run sdlc status                   # same card but Last updated now shows scan timestamp
    uv run sdlc scan                     # idempotent state, second journal entry
    uv run sdlc --no-color status        # zero ANSI escapes
    NO_COLOR=1 uv run sdlc status        # zero ANSI escapes (env path)
    uv run sdlc --json status            # canonical JSON envelope
    uv run sdlc --json scan              # canonical JSON envelope
    ```
    Document the smoke in the Story 1.17 dev notes / completion log so the reviewer can replay it.

## Dev Notes

### Why this story exists (FR + NFR + Decision mapping)

- **FR3 — `sdlc scan` (PRD §FR3, Architecture §1133)**: The user-facing rescan command. Story 1.15 owns the engine read path; Story 1.17 owns the CLI wrapper that wires state-write + journal-append.
- **FR44 — `sdlc status` resume card (PRD §FR44, Architecture §1170)**: The "you are here" surface from Journey 4 (UX spec §283-§295). Without 1.17, the dashboard is the only surface that surfaces this — but the dashboard is Story 5.x and walks much later in the timeline. The CLI status card unblocks Diep's resume-onboarding journey end-to-end at v0.2.
- **NFR-A11Y-4 — `--no-color` + `--json` (PRD §892, Architecture §138, §677-§679)**: Accessibility commitment. Without 1.17, the CLI is unusable for assistive tooling (screen readers stumble on ANSI escapes; build pipelines can't parse rich text). The flags MUST work on every command — `--no-color` and `--json` are global, not per-command.
- **NFR-PERF-1 — `sdlc scan` < 2 s on 200 stories / 1000 tasks (PRD §810, Architecture §131, §1407)**: Story 1.15 owns the CI regression gate via pytest-benchmark on `engine.scanner.scan`. Story 1.17's `cli/scan.py` adds ~milliseconds for state-write + journal-append; these costs are uncovered by the 1.15 benchmark and should NOT push the wall-clock past 2 s. v1.17 does NOT extend the benchmark surface (Story 1.15 already covers the dominant cost); a follow-up story can add a `cli_scan_perf` benchmark if profiling reveals the wrapper costs are nontrivial.
- **Architecture §349 — Decision B5 ("State as projection of journal")**: Story 1.17's scan operation appends a journal entry per scan, even when state is byte-identical. This is consistent with B5: the journal is the source of truth, state.json is a cached projection; recording each scan as an OBSERVATION is correct. ADR-020 reframes ADR-014's "first entry is the first state mutation" invariant to include "every CLI-driven state read is also recorded."
- **Architecture §1408 — v0.2 first-demo gate**: "First demonstrable behaviour: `sdlc init && sdlc status` shows 'Phase 1, no progress yet'". Story 1.16 ships HALF this milestone (`sdlc init`); Story 1.17 ships the OTHER HALF (`sdlc status` + `sdlc scan`). Together they close the v0.2 walking-skeleton ship signal.

### File set this story creates / modifies

**New files (created):**

- `src/sdlc/cli/scan.py` — `run_scan()` + helpers (~200-250 LOC)
- `src/sdlc/cli/status.py` — `run_status()` + helpers (~150-200 LOC)
- `tests/unit/cli/test_scan.py` — scan handler tests (~8 cases)
- `tests/unit/cli/test_status.py` — status handler tests (~9 cases)
- `tests/unit/cli/test_output.py` — output module tests (~6 cases)
- `tests/unit/state/test_canonical_bytes.py` — canonical-bytes helper tests (~5 cases)
- `tests/integration/test_no_color_every_command.py` — parametrized a11y test
- `tests/integration/test_walking_skeleton_e2e.py` — Architecture §1408 end-to-end gate
- `tests/integration/test_scan_journal_seq_continuity.py` — seq invariant property
- `docs/decisions/ADR-020-cli-scan-status-accessibility-flags.md` — new ADR

**Optional new file** (factor out if line caps exceeded):

- `src/sdlc/cli/_paths.py` — shared `_get_repo_root_or_cwd()` if Story 1.16 didn't already factor it out
- `src/sdlc/cli/_output_helpers.py` — `_strip_ansi`, `is_no_color_active` if `output.py` exceeds 200 LOC
- `src/sdlc/cli/_scan_helpers.py` — `_compute_sha256_of_file`, `_now_rfc3339_utc` if `scan.py` exceeds 250 LOC
- `src/sdlc/cli/_main_helpers.py` — `initialize_context` if `main.py` exceeds 130 LOC

**Modified files:**

- `src/sdlc/cli/output.py` — expanded from Story 1.16 stub (echo) to v1.17 surface (echo, emit_json, emit_error, make_console, is_no_color_active) (~50 → 200 LOC)
- `src/sdlc/cli/main.py` — adds `scan` + `status` subcommand registrations + global `--no-color` / `--json` flags + JSON-aware version callback (~100 → 130 LOC)
- `src/sdlc/cli/init.py` — `run_init` signature gains `ctx: typer.Context | None = None`; existing echo lines route through ctx; `ALREADY_INITIALIZED` refusal routes through `emit_error` instead of direct echo
- `src/sdlc/state/__init__.py` — adds `state_to_canonical_bytes` public helper + extends `__all__`
- `src/sdlc/config/env.py` — adds `NO_COLOR` to `ENV_EXACT_ALLOWLIST`
- `pyproject.toml` — adds `rich>=13,<15` to `[project] dependencies`
- `uv.lock` — refreshed by `uv lock`
- `tests/unit/cli/test_main.py` — extends Story 1.16's tests with 5 new cases
- `tests/unit/cli/test_init.py` — adds 1 regression test for ctx-aware signature
- `tests/unit/config/test_env.py` — adds 1 test for NO_COLOR allow-list (or extends an existing allow-list assertion)
- `docs/decisions/index.md` — adds ADR-020 row
- `docs/CODEMAPS/cli-module.md` — extends Story 1.16's codemap with `scan.py`, `status.py`, expanded `output.py`
- `README.md` — extends quick-start with status/scan/--no-color/--json examples (optional but recommended)

**Conditionally modified files** (only if Story 1.16's allowlist needs extending):

- `scripts/check_no_state_mutation.py` (or wherever the validator lives) — add `cli/scan.py` to the allowlist of modules permitted to call `write_state_atomic_sync` directly

**Files NOT modified (invariant — break-glass if any of these change):**

- `src/sdlc/__init__.py` — Story 1.1 owns; `__version__` stays at "0.0.0".
- `src/sdlc/state/atomic.py`, `src/sdlc/state/model.py`, `src/sdlc/state/projection.py` — Stories 1.10/1.12/1.15 own; consumers only.
- `src/sdlc/journal/writer.py`, `src/sdlc/journal/reader.py`, `src/sdlc/journal/__init__.py` — Story 1.11 owns; consumers only.
- `src/sdlc/engine/scanner.py`, `src/sdlc/engine/__init__.py` — Story 1.15 owns; consumers only.
- `src/sdlc/contracts/journal_entry.py`, `src/sdlc/contracts/resume_token.py` — Story 1.7 owns; consumers only.
- `src/sdlc/ids/`, `src/sdlc/errors/`, `src/sdlc/concurrency/` — Stories 1.6/1.9 own; not touched.
- `src/sdlc/cli/version.py`, `src/sdlc/cli/exit_codes.py`, `src/sdlc/cli/__init__.py` — Story 1.16 owns; not modified.
- `scripts/check_module_boundaries.py` — Story 1.16's widening (`cli` → `state`, `journal`, `contracts`, `ids`) covers Story 1.17. NO further widening.
- `.pre-commit-config.yaml` — no new hook.

### Why `cli/scan.py` is a thin wrapper, not the engine itself

Story 1.15 explicitly designs `engine/scanner.py:scan` as a pure-function read with NO side effects (no state.json write, no journal append). Story 1.15 dev notes (line 558-564) preview Story 1.17's wrapper:

```python
state = scan(project_root)
write_state_atomic_sync(state, target=...)
journal.append_sync(JournalEntry(kind="scan_completed", ...), journal_path=...)
```

The separation of concerns is load-bearing:

1. **Story 1.20's `sdlc rebuild-state`** will call `engine.scanner.scan` to compare artifact-tree state against journal-projected state during reconciliation. If `scan()` wrote state.json on every call, rebuild-state would have to either suppress the write (kludgy) or call a half-private internal function. Pure shape avoids both.
2. **Story 1.14's abstraction-adequacy CI test** stub-replaces `scan()` with mock-runtime data. If `scan()` had side effects, the stub story would be more invasive.
3. **POSIX/Windows portability**: `engine.scanner.scan` runs on Windows (pure read). The wrapper `cli/scan.py` is POSIX-only for the atomic-write path (with a Windows fallback warning, mirroring Story 1.16's `cli/init.py`).

### Why `sdlc scan` appends a journal entry even when state is byte-identical

Decision B5 (Architecture §349) says "the journal is the source of truth; state.json is a cached projection". Two readings:

1. **Strict**: only state-changing operations append journal entries. A no-op scan is just a read.
2. **Lenient**: every CLI-driven state observation is recorded. Journal becomes "audit log of CLI-mediated reads + writes" instead of "audit log of writes only".

Story 1.17 chooses the LENIENT reading. Rationale:

- **Audit completeness**: knowing WHEN the user observed state (not just when state changed) is valuable for debugging — "the user ran scan but didn't see the new epic? check the timestamp of the scan entry vs. the file mtime."
- **Idempotency property**: "scan twice → state byte-equal" is preserved (state.json bytes are identical). The journal is allowed to grow because it's append-only; growth is not a correctness violation.
- **Minimal surprise for ADR-014**: ADR-014 says "the first entry corresponds to the first state mutation." Story 1.17's interpretation extends this to "the first entry is the first scan_completed event, which is the first state OBSERVATION (which may or may not be a mutation)." The ADR-020 amendment makes this explicit.

Alternative: emit a `scan_noop` kind separately and only emit `scan_completed` on actual changes. Rejected: complicates the journal kind taxonomy without adding signal — both `scan_completed` and `scan_noop` would advance `next_monotonic_seq`, so the seq counter behavior is identical; only the kind label differs, and consumers can derive "was this a noop?" from `before_hash == after_hash` directly.

### Why the suggested-next computation is a stub in v1.17

Story 4.x's `engine/auto_loop.py` owns the rich next-action engine — it reads state, journal, signoffs, dirty/replan flags, current STOP triggers, and computes the optimal next command. Pulling that forward into v1.17 would inflate the story scope by 5x.

The v1.17 stub handles ONE case explicitly (fresh project → `/sdlc-start "<idea>"`) and falls through to a sensible default (`sdlc scan`) for all others. The fresh-project case is the ONLY case the epic AC tests verify; downstream cases will be tested when Story 4.x replaces the stub.

The `_compute_suggested_next` function lives in `cli/status.py` for v1.17. When Story 4.x lands, the function is REPLACED with a deferred call into `engine.auto_loop.suggest_next(state, journal, ...)`. The CLI surface (the `Suggested next: <command>` line) is invariant; the computation engine swaps cleanly underneath.

### Why `--no-color` and `--json` are global, not per-command

Two design alternatives:

1. **Per-command flags**: `sdlc scan --no-color --json`, `sdlc status --no-color --json`. Each subcommand declares the flags. Pro: Typer-idiomatic for command-specific options. Con: every new command must remember to declare them; drift surface; users must position the flag AFTER the subcommand which is non-obvious.
2. **Global flags via root callback**: `sdlc --no-color status`, `sdlc --json scan`. Declared ONCE on `cli/main.py:_root`; subcommands inherit via `typer.Context`. Pro: one source of truth; users can position the flag anywhere; new subcommands inherit for free. Con: requires `is_eager=True` semantics so the flag is parsed before subcommand dispatch.

v1.17 takes option 2. The Typer idiom for global eager flags is established (see typer.tiangolo.com/tutorial/options/version/ for `--version` precedent).

### NO_COLOR env var honoring

Per the no-color.org informal standard (https://no-color.org/):

- Any non-empty value of `NO_COLOR` disables color (the value content is irrelevant).
- User-level config files and per-instance command-line arguments should override `NO_COLOR`.

v1.17's interpretation: `--no-color` is a stricter signal (user explicitly asked); `NO_COLOR` is a softer signal (env-level preference). The two are OR'd — either disables color. There is NO `--color` opposite flag that would un-set `NO_COLOR`; if a user explicitly wants color in a piped context, they un-set the env var.

The allow-list extension in `config/env.py` is the only NEW code-path widening this requires. The architectural impact is minimal — `NO_COLOR` joins `GH_TOKEN` as the second exact-allow-list entry, with the same per-story attribution comment pattern.

### Cold-start budget for `sdlc --version`

Architecture §488 sets the cold-start budget at < 200 ms. Story 1.16's measurement showed `sdlc --version` at ~80-120 ms. Story 1.17's additions:

- **`rich` direct dep**: `rich` is already a transitive dep via Typer; the import is lazy (`make_console` defers `from rich.console import Console`). The `--version` path does NOT touch `make_console`, so no cold-start regression.
- **`scan` and `status` subcommand registrations**: Typer registers these as decorators at module import time on `cli/main.py`. The registration cost is ~5 ms total (Typer parses the function signatures). The subcommand BODIES are not imported until `sdlc scan` or `sdlc status` is invoked.
- **Global `--no-color` / `--json` flags**: parsed eagerly during `--version`. Eager parsing is ~1 ms.

Diagnosis path if a regression pushes past 200 ms:
```bash
python -X importtime -m sdlc.cli.main --version 2>&1 | sort -k 2 -n | tail -20
```
Heaviest suspected imports if regression: pydantic (~30 ms — only loaded if state/contracts get pulled into main accidentally), rich (~20 ms — only loaded via `make_console` on scan/status). Keep `cli/main.py`'s module-level imports minimal.

### Windows posture

- `state/atomic.py` is POSIX-only (Story 1.10). `cli/scan.py` falls back to `Path.write_bytes(canonical_bytes)` with a one-line warning, mirroring Story 1.16's `cli/init.py` pattern.
- `journal/writer.py` is POSIX-only (Story 1.11). `cli/scan.py`'s `_append_scan_journal_entry` will raise `JournalError` on Windows; the caller catches and emits via `emit_error("ERR_JOURNAL_APPEND_FAILED", ...)`.
- The Windows refusal posture is honest: `sdlc scan` on Windows works for state-write but fails for journal-append. The error message names the architectural reason and points to WSL2.
- All e2e tests `subprocess.run(["uv", "run", "sdlc", ...])` skip on Windows when `shutil.which("uv") is None`.

### Test pyramid placement

| Test type | New tests in Story 1.17 |
|---|---|
| Unit (`tests/unit/`) | 8 (test_scan) + 9 (test_status) + 6 (test_output) + 5 (test_canonical_bytes) + 5 (test_main extension) + 1 (test_init regression) + 1 (test_env extension) = 35 |
| Integration (`tests/integration/`) | 5+ parametrized (test_no_color_every_command) + 2 (test_walking_skeleton_e2e) + 2 (test_scan_journal_seq_continuity) = ~9 distinct |
| Property | none (Story 1.11/1.12 own the journal/projection property tests; Story 1.17 doesn't introduce new invariants) |
| Chaos | none (no new POSIX-only kill points; existing chaos tests cover state/atomic + journal/writer) |
| Benchmark | none (Story 1.15 covers the dominant scan cost; v1.17 wrapper costs are negligible per the cold-start analysis) |

### Forbidden patterns in this story

Per Architecture §483-§494, these patterns MUST NOT appear in any new file:

- `print()` — use `cli/output.py:echo` / `emit_json` / `emit_error`. (`cli/` is the only module where ANY direct user-facing output is permitted, and it MUST route through `output.py`.)
- `time.time()` for ordering — use `monotonic_seq` from State. Wall-clock UTC for human-readable `ts` only via `datetime.datetime.now(datetime.timezone.utc)`.
- `os.environ[...]` direct access OUTSIDE `cli/output.py` — use `sdlc.config.read_env`. Inside `cli/output.py` the direct read is justified per Architecture's `cli/` carve-out + matches the eager-parse pattern; document inline.
- `subprocess.run` — only the optional `git rev-parse --show-toplevel` is permitted (mirroring Story 1.16's pattern).
- Bare `except:` / `except Exception:` — narrow catches only (`OSError`, `subprocess.SubprocessError`, `FileNotFoundError`, `JournalError`, `StateError`, etc.).
- Mutating function arguments — use `model_copy(update=...)` for State updates; build new dicts/lists rather than mutate in place.
- Float arithmetic for state values — N/A; no float math here.

## Project Structure Notes

### Alignment with unified project structure

Story 1.17 ALIGNS with Architecture §790-§811 (Module Specification) by populating the next two cli modules:

```
src/sdlc/cli/
├── __init__.py        # Story 1.16
├── main.py            # Story 1.16 (extended in 1.17)
├── output.py          # Story 1.16 stub (expanded in 1.17)
├── exit_codes.py      # Story 1.16
├── version.py         # Story 1.16
├── init.py            # Story 1.16 (minimally extended in 1.17 for ctx)
├── scan.py            # THIS STORY (Architecture §799, FR3)
├── status.py          # THIS STORY (Architecture §801, FR44)
└── ...                # Stories 1.18-1.20 add trace, replay, logs, rebuild_state, trust_hooks
```

The boundary table widening from Story 1.16 (`cli` → `state`, `journal`, `contracts`, `ids`) covers Story 1.17 fully — no further widening.

### Detected variances

None. All paths and module responsibilities align with Architecture §790-§811.

## References

- [Source: _bmad-output/planning-artifacts/architecture.md#Project Lifecycle Management (FR1-FR5)] — line 117 (FR3 framing)
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision B5 — State as projection of journal] — line 349
- [Source: _bmad-output/planning-artifacts/architecture.md#v0.2 foundation sequence] — line 388
- [Source: _bmad-output/planning-artifacts/architecture.md#CLI exit code mapping + Error envelope] — lines 540-560
- [Source: _bmad-output/planning-artifacts/architecture.md#Code Style Beyond Ruff] — lines 483-494 (forbidden patterns)
- [Source: _bmad-output/planning-artifacts/architecture.md#Atomic Write Protocol] — lines 569-583 (canonical sequence step 8 — append journal)
- [Source: _bmad-output/planning-artifacts/architecture.md#The Five Wire-Format Contract Schemas — JournalEntry] — lines 595-606
- [Source: _bmad-output/planning-artifacts/architecture.md#CLI Output Conventions] — lines 674-680 (--no-color / --json contract)
- [Source: _bmad-output/planning-artifacts/architecture.md#Module Specification — cli/] — lines 790-811
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-level Boundary Rules] — lines 1052-1112
- [Source: _bmad-output/planning-artifacts/architecture.md#Functional Requirements → File Mapping] — lines 1131-1170 (FR3, FR44 mapping)
- [Source: _bmad-output/planning-artifacts/architecture.md#v0.2 Implementation Sequence] — line 1408 (walking-skeleton first-demo gate)
- [Source: _bmad-output/planning-artifacts/prd.md#FR3] — line 725
- [Source: _bmad-output/planning-artifacts/prd.md#FR44] — line 784
- [Source: _bmad-output/planning-artifacts/prd.md#NFR-A11Y-4] — line 892
- [Source: _bmad-output/planning-artifacts/prd.md#NFR-PERF-1] — line 810
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.17] — lines 827-855
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Resume card] — lines 410, 446 (resume card UX from Journey 4)
- [Source: docs/decisions/ADR-001-pyproject-metadata.md] — pyproject metadata (consumed by Task 2)
- [Source: docs/decisions/ADR-013-atomic-state-write-protocol.md] — atomic write protocol (consumed by cli/scan.py)
- [Source: docs/decisions/ADR-014-append-only-journal-protocol.md] — journal append-only invariant (consumed by cli/scan.py)
- [Source: docs/decisions/ADR-015-state-projection-from-journal.md] — Story 1.12; projection contract
- [Source: docs/decisions/ADR-018-engine-scanner-skeleton.md] — Story 1.15; engine.scanner.scan contract (consumed)
- [Source: docs/decisions/ADR-019-cli-skeleton-typer-adoption.md] — Story 1.16; cli skeleton + Typer adoption + boundary widening (extended)
- [Source: scripts/check_module_boundaries.py:133-135] — `MODULE_DEPS["cli"]` widening from Story 1.16 (covers this story)
- [Source: src/sdlc/cli/output.py] — Story 1.16 stub (expanded by Task 4)
- [Source: src/sdlc/cli/main.py] — Story 1.16 entry shell (extended by Task 7)
- [Source: src/sdlc/cli/init.py] — Story 1.16 init scaffolder (minimally extended by Task 7 for ctx)
- [Source: src/sdlc/state/__init__.py:11] — `write_state_atomic_sync` re-export (consumed by cli/scan.py)
- [Source: src/sdlc/journal/__init__.py:10] — `append_sync` re-export (consumed by cli/scan.py)
- [Source: src/sdlc/contracts/journal_entry.py:16] — `_RFC3339_UTC` regex (timestamp format must match)
- [Source: src/sdlc/state/projection.py:70] — seq math (`max(next_seq, entry.monotonic_seq + 1)`); cli/scan.py's seq logic must be consistent
- [Source: src/sdlc/config/env.py:9] — `ENV_EXACT_ALLOWLIST` (extended by Task 2)
- [Source: src/sdlc/config/secrets.py] — `sanitize_mapping` (consumed by `emit_error` for details redaction)
- [Source: _bmad-output/implementation-artifacts/1-15-engine-scanner-skeleton.md:558-564] — Story 1.15 dev notes preview Story 1.17's wrapper pseudocode
- [Source: _bmad-output/implementation-artifacts/1-16-cli-sdlc-init-greenfield.md] — Story 1.16 cli skeleton (entire file is precedent for structure, naming, ADR pattern, test patterns)
- [Source: https://no-color.org/] — informal NO_COLOR standard
- [Source: https://typer.tiangolo.com/tutorial/options/version/] — Typer is_eager flag idiom for `--version`-class options
- [Source: https://typer.tiangolo.com/tutorial/commands/context/] — Typer Context idiom for global flags

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m]

### Debug Log References

### Completion Notes List

### File List
