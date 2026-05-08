# Story 1.8: Foundation — `config/` Module (project.yaml + Env Allow-List + Secret Sanitizer)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an engineer landing the third foundation module after Story 1.7 (`contracts/` shipped 5 pydantic v2 wire-format models — `JournalEntry`, `ResumeToken`, `HookPayload`, `SpecialistFrontmatter`, `WorkflowSpec` — all `frozen=True`, all `Literal[1]` schema-versioned) and the `MODULE_DEPS["config"]` row already grants `depends_on={"errors", "contracts"}` and `forbidden_from={"engine", "dispatcher", "cli"}` per `scripts/check_module_boundaries.py:42-45`,
I want three sibling files under `src/sdlc/config/` — `project.py` (FR51 — `project.yaml` loader returning a typed `ProjectConfig` pydantic model with the four documented keys + ConfigError on unknown keys), `env.py` (FR52, NFR-SEC-2 — `read_env(name)` allow-list checker accepting only `SDLC_*`, `CLAUDE_*`, and the exact `GH_TOKEN`), `secrets.py` (NFR-SEC-1 — regex sanitizer redacting common secret-shaped strings with `<REDACTED:secret>` before any state/journal/log write) — plus `scripts/check_no_hardcoded_secrets.py` static linter wired into the pre-commit chain after the existing boundary-validator hook, and ≥95% line+branch coverage on every config module via the same per-file Cartesian unit-test discipline Story 1.6 (errors/ids) + 1.7 (contracts) established,
So that Story 1.9's `concurrency/` module can read `max_parallel_agents` from `ProjectConfig` to size its `BoundedDispatcher` Semaphore (Decision A2, Architecture §337), Story 1.10's `state/atomic.py` (`depends_on={"errors", "contracts", "concurrency", "config"}` per `check_module_boundaries.py:51-53`) can call `sanitize()` before serializing user-provided text into the canonical state JSON (NFR-SEC-1), Story 1.11's `journal/writer.py` shares the same sanitization layer for journal entries, the `pr-author` specialist's lone authorized read of `GH_TOKEN` (Architecture §671) has a typed read path that fails-closed on any other env var, the brownfield Story 3.x `legacy_code_globs` setting has the loaded value to consult, the watchdog timeout (Story 4.9) has its `watchdog_timeout_minutes` source-of-truth, and the framework gains its first runtime YAML dependency (`pyyaml>=6,<7`) following the same `<N` defensive-cap convention Story 1.7 established for pydantic.

## Acceptance Criteria

**AC1 — `src/sdlc/config/project.py` exposes `load_project_config(path: Path | None = None) -> ProjectConfig` returning a frozen pydantic v2 `ProjectConfig` with the 4 documented keys at their epic-prescribed defaults; unknown keys raise `ConfigError` naming the offending key; missing optional keys fall back to documented defaults.**

**Given** Story 1.7 complete (`pydantic>=2,<3` is the only runtime dep; `sdlc.contracts` ships 5 frozen wire-format models) **AND** `pyyaml>=6,<7` lands in `[project] dependencies` per Task 1 below **AND** the `MODULE_DEPS["config"]` row already declares `depends_on=frozenset({"errors", "contracts"})` (Story 1.4 pre-grant; `scripts/check_module_boundaries.py:42-45`)
**When** I call `load_project_config()` (no path → defaults to `<cwd>/project.yaml`) on a fixture file containing:
```yaml
max_parallel_agents: 4
auto_brainstorm: true
legacy_code_globs:
  - "src/legacy/**"
watchdog_timeout_minutes: 30
```
**Then** the function returns a `ProjectConfig(max_parallel_agents=4, auto_brainstorm=True, legacy_code_globs=("src/legacy/**",), watchdog_timeout_minutes=30)` instance
**And** the instance is `frozen=True` (post-construction mutation raises `pydantic.ValidationError` — same discipline as Story 1.7 contracts)
**And** every field has the type + default per the table below (sources: epics.md:610-613, prd.md:797, architecture.md:337, architecture.md:466, architecture.md:652, architecture.md:752):

| Field | Type | Default | Source |
|---|---|---|---|
| `max_parallel_agents` | `int` (≥1) | `4` | epics.md:610, prd.md:797, architecture.md:652 |
| `auto_brainstorm` | `bool` | `True` | epics.md:610, prd.md:797, architecture.md:466 |
| `legacy_code_globs` | `tuple[str, ...]` | `()` | epics.md:610, prd.md:797, architecture.md:277 (NOT `list[str]` — see Dev Notes "Why tuple over list for legacy_code_globs") |
| `watchdog_timeout_minutes` | `int` (≥1) | `30` | epics.md:610, prd.md:797, prd.md:752 |

**And** `model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)` matches Story 1.7's wire-format contract config triple verbatim (extra="forbid" causes pydantic to raise `ValidationError` on unknown YAML keys; frozen=True prevents post-load mutation; str_strip_whitespace=False keeps user-provided glob strings byte-identical)

**Given** AC1's `extra="forbid"` configuration
**When** I call `load_project_config(path)` on a YAML file containing an unknown key, e.g. `unknown_key: "x"`
**Then** the function raises `ConfigError("project.yaml unknown key 'unknown_key'")` (or equivalent message naming the offending key) with the `code == "ERR_CONFIG"` (existing `sdlc.errors.ConfigError` subclass — `src/sdlc/errors/base.py:69-70`)
**And** the `ConfigError.details` dict includes `{"path": str(path), "key": "unknown_key"}` for the structured `--json` envelope (per `SdlcError.to_envelope()` at `src/sdlc/errors/base.py:31-38`)
**And** the underlying `pydantic.ValidationError` is wrapped (NOT raw-propagated) so all config failures surface as `ConfigError` exclusively at the public API boundary

**Given** AC1's optional-fields-have-defaults requirement
**When** I call `load_project_config(path)` on an EMPTY YAML file (`{}` or zero bytes)
**Then** the function returns `ProjectConfig()` (all 4 fields at their defaults — `max_parallel_agents=4, auto_brainstorm=True, legacy_code_globs=(), watchdog_timeout_minutes=30`)
**And** the function returns the same defaults when the path argument is `None` AND the default `project.yaml` does NOT exist on disk (this is the greenfield-bootstrap case — Story 1.16's `sdlc init` will write a starter `project.yaml`, but until then the framework MUST tolerate its absence)
**And** the boundary between "missing file → defaults" and "malformed file → ConfigError" is explicit:
- Missing file (file does not exist) → returns defaults silently
- Empty file (zero bytes or only whitespace) → returns defaults silently
- Non-empty malformed YAML (e.g. tab-indentation error, unclosed quote) → raises `ConfigError("project.yaml malformed: <yaml.YAMLError message>")`
- Valid YAML but unknown key → raises `ConfigError("project.yaml unknown key '<key>'")`
- Valid YAML with wrong type (e.g. `max_parallel_agents: "four"`) → raises `ConfigError("project.yaml field '<field>' wrong type: <pydantic message>")`

**AC2 — `src/sdlc/config/env.py` exposes `read_env(name: str) -> str | None` returning the env-var value if it matches the allow-list, raising `ConfigError("env var '<name>' not in allow-list (SDLC_*, CLAUDE_*, GH_TOKEN)")` otherwise; the framework-wide ban on direct `os.environ[...]` access (Architecture §491) is enforced by code review + a future static-import-graph check.**

**Given** the env allow-list per Architecture §671 + NFR-SEC-2 (prd.md:798, architecture.md:833): prefix matches `SDLC_*` and `CLAUDE_*` plus the single exact match `GH_TOKEN` (consumed only by the future `pr-author` specialist)
**When** I call `read_env("SDLC_DEBUG")` (and the env var is set) → returns the env-var string value
**And** I call `read_env("CLAUDE_API_KEY")` (and set) → returns the value
**And** I call `read_env("GH_TOKEN")` (and set) → returns the value
**And** I call `read_env("HOME")` → raises `ConfigError("env var 'HOME' not in allow-list (SDLC_*, CLAUDE_*, GH_TOKEN)")` (NOT silent `None` return; fail-loud per architecture §618)
**And** I call `read_env("PATH")` → raises `ConfigError`
**And** I call `read_env("OPENAI_API_KEY")` → raises `ConfigError` (no `OPENAI_*` prefix in allow-list — only `SDLC_*` and `CLAUDE_*`)
**And** I call `read_env("SDLC_NONEXISTENT")` (allowed prefix but env var is unset) → returns `None` (the allow-list gate fires AFTER the prefix match; unset-but-allowed is a legitimate "not configured" signal, distinguished from "forbidden read")
**And** the allow-list match is case-sensitive: `read_env("sdlc_debug")` raises `ConfigError` (the canonical convention is `UPPER_SNAKE_CASE`; Architecture §671 lists allowlist names in upper case only)

**Given** the public API
**When** I run `uv run python -c "from sdlc.config import read_env; print(read_env)"`
**Then** the function imports cleanly via the `sdlc.config` package re-export
**And** the constants `ENV_PREFIX_ALLOWLIST = ("SDLC_", "CLAUDE_")` and `ENV_EXACT_ALLOWLIST = frozenset({"GH_TOKEN"})` are defined at module scope as `Final` (mypy-strict friendly; `from typing import Final`) and exposed in the package `__all__`
**And** the implementation uses `os.environ.get(name)` (NOT `os.environ[name]`) AFTER the allow-list check passes, so unset-but-allowed env vars yield `None` instead of `KeyError` (the only call site of `os.environ.get` in the entire framework — Architecture §491 + §618-§619)

**AC3 — `src/sdlc/config/secrets.py` exposes `sanitize(text: str) -> str` redacting strings matching the documented secret patterns with `<REDACTED:secret>`; `sanitize_mapping(obj: Mapping[str, object]) -> dict[str, object]` recursively walks dict/list values applying `sanitize` to every leaf string; an integration test attempts to write a secret-shaped string through the sanitizer and asserts redaction; a static linter (`scripts/check_no_hardcoded_secrets.py`) scans framework source for hardcoded secret literals and is wired into the pre-commit chain.**

**Given** the secret pattern set per epics.md:621 (sk-*, pk_*, ghp_*, AKIA*, JWT-shaped tokens) — see "Secret pattern reference" in Dev Notes for the exact regex per pattern
**When** I call `sanitize("Authorization: Bearer sk-abc123def456ghi789jkl012mno345pq")` on a string containing an OpenAI/Anthropic-shaped key
**Then** the return value contains `<REDACTED:secret>` in place of the matched token: `"Authorization: Bearer <REDACTED:secret>"`
**And** the same redaction holds for: `pk_live_abc123def456` (Stripe live key prefix), `pk_test_abc123def456` (Stripe test key prefix), `ghp_abc123def456...` (GitHub PAT, exactly 36 chars after the `ghp_` prefix per GitHub's documented format), `AKIAIOSFODNN7EXAMPLE` (AWS access key ID, exactly 20 chars `AKIA[A-Z0-9]{16}`), `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c` (JWT three-segment base64url-with-dots)
**And** `sanitize("no secrets here")` returns `"no secrets here"` (passthrough — non-matching strings are byte-identical)
**And** `sanitize("")` returns `""` (empty-string passthrough)
**And** the sanitizer is idempotent: `sanitize(sanitize(x)) == sanitize(x)` for any `x` (no double-redaction, no infinite-loop risk on already-redacted strings)
**And** redaction applies to ALL matches in a single string: `sanitize("sk-abc... and ghp_def...")` redacts BOTH tokens

**Given** `sanitize_mapping(obj)` for nested-dict inputs (the typical `SdlcError.to_envelope()` `details` shape — `dict[str, object]` per `src/sdlc/errors/base.py:25,32-37` + Story 1.6 deferred line 22 — explicit ownership for Story 1.8's secrets layer)
**When** I call `sanitize_mapping({"path": "/tmp/x", "api_key": "sk-abc123def456ghi789jkl012mno345pq", "nested": {"token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"}})`
**Then** the return value is a NEW dict (input is NOT mutated — Story 1.6 immutable-pattern discipline) with redacted strings: `{"path": "/tmp/x", "api_key": "<REDACTED:secret>", "nested": {"token": "<REDACTED:secret>"}}`
**And** non-string leaves (int, bool, None, float) are passed through byte-identically
**And** the recursion walks `dict` AND `list` containers; non-hashable types are tolerated (no implicit casting, no `__hash__` calls)
**And** circular references are NOT supported in v1 (the deepest recursion is `sys.getrecursionlimit()`-bounded; non-circular structures are the contract); a future `_seen: set[int]` guard MAY land in a 1.x story if circular details surface in the wild

**Given** the integration test `tests/integration/test_secret_hygiene.py` (NEW; placeholder-but-real per Architecture §990)
**When** I run the integration test
**Then** the test constructs an `SdlcError` instance with `details = {"api_key": "sk-abc123def456ghi789jkl012mno345pq"}`, calls `error.to_envelope()`, applies `sanitize_mapping(envelope["error"]["details"])`, and asserts the resulting dict has `"<REDACTED:secret>"` in the `api_key` field
**And** the test is marked `@pytest.mark.integration` (per `pyproject.toml:135`) and runs in the same `uv run pytest` invocation as unit tests
**And** the test imports ONLY from `sdlc.config`, `sdlc.errors`, and the standard library (no `state/` or `journal/` dependencies — those land in Stories 1.10/1.11 and will extend the integration test in their own AC blocks)

**Given** the static linter `scripts/check_no_hardcoded_secrets.py` (NEW)
**When** I run `uv run python scripts/check_no_hardcoded_secrets.py src/sdlc/`
**Then** the script greps every `.py` file under `src/sdlc/` for the same secret patterns sanitize() recognizes
**And** the script exits 0 (no hardcoded secrets in source) for the current Story 1.8 codebase
**And** the script exits 1 with a per-file-per-line violation list when ANY hardcoded secret literal appears in source (e.g. a developer accidentally hardcodes a test API key — see Dev Notes "Why a static linter for source-level secrets")
**And** the script is wired into `.pre-commit-config.yaml` between the existing `boundary-validator` and `specialist-validator` hooks (insertion at line 50ish per `.pre-commit-config.yaml` numbering — see Task 7 for the exact patch)
**And** test fixtures with intentional secret-shaped strings (e.g. `tests/unit/config/test_secrets.py`'s redaction inputs) are exempt: the script does NOT scan `tests/`, `scripts/`, `_bmad/`, `_bmad-output/`, `.claude/`, `_site/`, or `docs/` (mirror of the `pyproject.toml` `[tool.ruff] extend-exclude` list; the script reads source-file paths only)

**AC4 — Per-file pydantic v2 + `frozen=True` discipline matches Story 1.7: `ProjectConfig` is hashable IFF all its fields are hashable; `legacy_code_globs: tuple[str, ...]` is the explicit choice over `list[str]` to preserve hashability (the alternative would force `ProjectConfig` into the unhashable matrix alongside `JournalEntry`/`ResumeToken`/`SpecialistFrontmatter`/`WorkflowSpec`).**

**Given** AC1's `model_config = ConfigDict(..., frozen=True, ...)` configuration
**When** I construct `cfg = ProjectConfig()` and call `hash(cfg)`
**Then** `hash(cfg)` returns an `int` (no `TypeError`) — `ProjectConfig` IS hashable because all 4 fields are hashable: `int, bool, tuple[str, ...], int`
**And** the same instance supports equality: `ProjectConfig() == ProjectConfig()` is `True`
**And** post-construction mutation raises `ValidationError`: `cfg.max_parallel_agents = 8` fails (frozen-model assignment guard, pydantic v2 behaviour per Story 1.7's "Latest tech information" section)

**Given** the `legacy_code_globs` field type
**When** I attempt `ProjectConfig(legacy_code_globs=["src/x/**"])` (passing a `list[str]`)
**Then** pydantic v2 coerces `list[str]` → `tuple[str, ...]` automatically (via the type-annotation; pydantic v2's strict-equals-tuple behaviour per architecture's "type-coerce conformant inputs" discipline) — the resulting `cfg.legacy_code_globs` is `("src/x/**",)`
**And** the loader's YAML output (`yaml.safe_load` returns `list`) is correctly coerced to `tuple` at the pydantic-validation layer; NO custom validator is required (Story 1.7's "no custom validators in v1" pattern extends here)

**AC5 — `src/sdlc/config/__init__.py` re-exports the public API (`load_project_config`, `ProjectConfig`, `read_env`, `ENV_PREFIX_ALLOWLIST`, `ENV_EXACT_ALLOWLIST`, `sanitize`, `sanitize_mapping`, `SECRET_PATTERNS`, `REDACTION_MARKER`) via an explicit `__all__` tuple in semantic order (project loader first, then env, then secrets — same architectural canonical-order pattern Stories 1.6/1.7 established).**

**Given** the public-API contract Architecture §1057 declares: `load_project_config`, `read_env`, `sanitize`
**When** I run `uv run python -c "from sdlc.config import load_project_config, ProjectConfig, read_env, ENV_PREFIX_ALLOWLIST, ENV_EXACT_ALLOWLIST, sanitize, sanitize_mapping, SECRET_PATTERNS, REDACTION_MARKER; print('ok')"`
**Then** all 9 names resolve cleanly via the package re-export
**And** `__all__` is declared with `# noqa: RUF022` (semantic-order, NOT alphabetical) per the Story 1.6/1.7 convention:
```python
__all__ = (  # noqa: RUF022
    "ProjectConfig",
    "load_project_config",
    "ENV_PREFIX_ALLOWLIST",
    "ENV_EXACT_ALLOWLIST",
    "read_env",
    "REDACTION_MARKER",
    "SECRET_PATTERNS",
    "sanitize",
    "sanitize_mapping",
)
```
**And** the `__init__.py` opens with `from __future__ import annotations` (Story 1.2 ruff rule `required-imports` enforces — `pyproject.toml:83`)
**And** `__init__.py` LOC ≤ 30 (Story 1.6/1.7 convention — small re-export shells)
**And** there is NO module-level side effect (no `os.environ` reads at import time, no YAML parsing at import time, no logging configuration); the `load_project_config()` function is the ONLY surface that touches the filesystem, and `read_env()` is the ONLY surface that touches `os.environ`

**AC6 — `tests/unit/config/{test_project.py, test_env.py, test_secrets.py}` covers the full Cartesian per file; ≥95% line+branch coverage on every config file; mypy-strict clean; ruff-clean.**

**Given** `[tool.coverage.report] fail_under = 90` is the project-wide gate (`pyproject.toml:147`); Story 1.6/1.7 establish ≥95% on every NEW leaf-foundation module (`errors/`, `ids/`, `contracts/` all at 100% per their Dev Agent Records)
**When** I run `uv run pytest --cov=src/sdlc/config --cov-branch --cov-report=term-missing --cov-fail-under=95 tests/unit/config tests/integration/test_secret_hygiene.py`
**Then** the targeted coverage exits 0 (≥95% line+branch on the entire `src/sdlc/config/` package; per-file all individually clear 95%)
**And** the test set covers, per file:

For `tests/unit/config/test_project.py`:
- **Happy path** — load a fixture YAML with all 4 keys at non-default values (`max_parallel_agents=8, auto_brainstorm=False, legacy_code_globs=["src/legacy/**"], watchdog_timeout_minutes=60`); assert each field equals the YAML value.
- **All defaults** — load an empty YAML file (zero bytes) → `ProjectConfig()` defaults.
- **Path=None + missing file** — call `load_project_config(None)` in a tmpdir with no `project.yaml` → defaults.
- **Path=None + existing file** — call `load_project_config(None)` in a tmpdir WITH a `project.yaml` → loaded values.
- **Unknown-key rejection** — fixture `{unknown_key: "x", max_parallel_agents: 4}` → `ConfigError` with `details["key"] == "unknown_key"`.
- **Wrong-type rejection** — fixture `{max_parallel_agents: "four"}` → `ConfigError` (wrapped pydantic `ValidationError`).
- **Malformed YAML rejection** — fixture with unclosed bracket `{[invalid: yaml` → `ConfigError("project.yaml malformed: <yaml.YAMLError>")`.
- **Frozen-mutation rejection** — `cfg.max_parallel_agents = 8` raises `ValidationError`.
- **Equality** — two `ProjectConfig()` defaults are `==`.
- **Hashability** — `hash(ProjectConfig())` returns `int` (per AC4).
- **`extra="forbid"` propagation** — assert `ConfigDict.extra == "forbid"` on the model_config (regression guard).
- **List → tuple coercion** — `ProjectConfig(legacy_code_globs=["a", "b"])` produces `legacy_code_globs == ("a", "b")` (tuple, not list).
- Use `@pytest.mark.unit`.

For `tests/unit/config/test_env.py`:
- **`SDLC_*` prefix accepted** — `monkeypatch.setenv("SDLC_DEBUG", "1"); read_env("SDLC_DEBUG")` returns `"1"`.
- **`CLAUDE_*` prefix accepted** — `monkeypatch.setenv("CLAUDE_API_KEY", "sk-abc"); read_env("CLAUDE_API_KEY")` returns `"sk-abc"` (the secret stays raw at this layer; `sanitize()` is a SEPARATE layer applied at write time, NOT at env read time — see Dev Notes "Why env reads return raw secrets, not sanitized").
- **`GH_TOKEN` exact match accepted** — `monkeypatch.setenv("GH_TOKEN", "ghp_xyz"); read_env("GH_TOKEN")` returns `"ghp_xyz"`.
- **`HOME` rejected** — `read_env("HOME")` raises `ConfigError` with the architecture-§671 allow-list message.
- **`PATH` rejected** — `read_env("PATH")` raises `ConfigError`.
- **`OPENAI_API_KEY` rejected** — confirms `OPENAI_*` is NOT in allow-list (epic doesn't grant it; future stories may evaluate).
- **Empty-name rejected** — `read_env("")` raises `ConfigError` (empty matches NO prefix, NO exact entry).
- **Lowercase rejected** — `read_env("sdlc_debug")` raises `ConfigError` (case-sensitive per AC2).
- **Allowed-but-unset returns None** — `monkeypatch.delenv("SDLC_X", raising=False); read_env("SDLC_X")` returns `None`.
- **`ENV_PREFIX_ALLOWLIST` constant** — assert it equals `("SDLC_", "CLAUDE_")` exactly (regression guard against accidental allow-list expansion).
- **`ENV_EXACT_ALLOWLIST` constant** — assert it equals `frozenset({"GH_TOKEN"})` exactly.
- Use `@pytest.mark.unit`.
- Use `monkeypatch.setenv`/`monkeypatch.delenv` (pytest builtin) for env-var isolation; NEVER touch `os.environ` directly in tests.

For `tests/unit/config/test_secrets.py`:
- **`sk-*` redaction** — `sanitize("sk-abc123def456ghi789jkl012mno345pq")` → `<REDACTED:secret>` (the entire token is replaced; surrounding context is preserved). Test multiple positions: prefix-only (`"sk-abc..." `), suffix-only (`"...sk-abc"`), embedded (`"prefix sk-abc suffix"`).
- **`pk_*` redaction** — `sanitize("pk_live_abc123def456ghi789jkl0")` and `sanitize("pk_test_xyz")` both redacted.
- **`ghp_*` redaction** — `sanitize("ghp_abcdefghijklmnopqrstuvwxyz0123456789")` redacted.
- **`AKIA*` redaction** — `sanitize("AKIAIOSFODNN7EXAMPLE")` redacted (AWS canonical 20-char ID format).
- **JWT redaction** — `sanitize("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")` redacted.
- **Multi-secret string** — `sanitize("token1=sk-abc123def456ghi789jkl012mno345pq; token2=ghp_abcdefghijklmnopqrstuvwxyz0123456789")` redacts BOTH (verifies the `re.sub` global behaviour).
- **No-secret passthrough** — `sanitize("just a normal string")` returns identical string.
- **Empty-string passthrough** — `sanitize("")` returns `""`.
- **Idempotency** — `sanitize(sanitize(x)) == sanitize(x)` for representative `x`.
- **`sanitize_mapping` happy path** — nested dict per AC3 sample; assert redaction at all leaf levels.
- **`sanitize_mapping` non-string leaves** — `{"int_field": 42, "bool_field": True, "none_field": None, "float_field": 3.14, "str_field": "sk-abc123def456ghi789jkl012mno345pq"}` → only `str_field` is redacted; non-string leaves byte-identical.
- **`sanitize_mapping` list values** — `{"tokens": ["sk-abc123def456ghi789jkl012mno345pq", "no-secret"]}` → first element redacted, second passthrough.
- **`sanitize_mapping` immutability** — input dict is NOT mutated (assert by comparing identity + post-call value).
- **`SECRET_PATTERNS` constant** — assert tuple length matches the documented set (sk-, pk_, ghp_, AKIA, JWT — 5 patterns); each is a compiled `re.Pattern` (regression guard).
- **`REDACTION_MARKER` constant** — assert it equals `"<REDACTED:secret>"` exactly.
- Use `@pytest.mark.unit`.

For `tests/integration/test_secret_hygiene.py`:
- **`SdlcError.to_envelope() + sanitize_mapping`** — construct `SdlcError("test", details={"api_key": "sk-abc123def456ghi789jkl012mno345pq"})`; call `error.to_envelope()`; apply `sanitize_mapping(envelope["error"]["details"])`; assert `["api_key"] == "<REDACTED:secret>"`.
- **Multi-pattern envelope** — error with `details = {"openai_key": "sk-...", "github_pat": "ghp_...", "aws_access": "AKIA...", "jwt": "eyJ...", "stripe": "pk_..."}`; assert ALL 5 are redacted.
- **Nested envelope** — error with `details = {"caller": {"name": "agent", "credentials": {"api_key": "sk-..."}}}`; assert deep redaction.
- Use `@pytest.mark.integration`.

**Given** Story 1.2's `[tool.mypy] strict = true` + `extra_checks = true` (`pyproject.toml:96-110`)
**When** I run `uv run mypy --strict src/`
**Then** mypy exits 0 — no `[no-untyped-def]`, `[var-annotated]`, `[misc]`, or `[type-arg]` diagnostics under `src/sdlc/config/`
**And** every public function has a typed signature; `model_config: ClassVar[ConfigDict]` is the canonical form for `ProjectConfig` (matches Story 1.7 contract pattern)
**And** every `.py` file under `src/sdlc/config/` opens with `from __future__ import annotations`
**And** `uv run ruff check src/sdlc/config tests/unit/config scripts/check_no_hardcoded_secrets.py` exits 0; `uv run ruff format --check src/sdlc/config tests/unit/config scripts/check_no_hardcoded_secrets.py` exits 0
**And** no file in `src/sdlc/config/` exceeds 400 LOC (boundary-validator's `LOC_CAP` enforces — `scripts/check_module_boundaries.py:343-358`); each of the 3 source files should land at ≤ 100 LOC.

**AC7 — `config/` is leaf-discipline-clean: the boundary-validator hook from Story 1.4 stays green; only `sdlc.errors` is imported from `sdlc.*` (the `contracts` grant remains unused for v1 — same forward-defensive pattern Story 1.7's `errors`-grant-but-no-import); `pyyaml` is the only NEW third-party import.**

**Given** the boundary-validator hook from Story 1.4 (`scripts/check_module_boundaries.py:42-45`) declares `MODULE_DEPS["config"]` as `depends_on=frozenset({"errors", "contracts"})`, `forbidden_from=frozenset({"engine", "dispatcher", "cli"})`
**When** I run `uv run pre-commit run --all-files` after authoring `src/sdlc/config/{__init__.py, project.py, env.py, secrets.py}`
**Then** every hook in the chain (ruff-check → ruff-format → mypy-strict → boundary-validator → secret-hardcode-validator → specialist-validator → hygiene hooks) exits 0
**And** the boundary-validator OK's the legal cross-module imports listed in Dev Notes "Cross-module import inventory":
- `from sdlc.errors import ConfigError` in `project.py` and `env.py`
- NO import from `sdlc.contracts` for v1 (the `MODULE_DEPS` grant is forward-defensive, parallel to Story 1.7's unused `errors`-grant-in-`contracts`)
- `from pathlib import Path`, `import os`, `import re` from stdlib in their respective files
- `import yaml` (pyyaml) ONLY in `project.py`
- `from pydantic import BaseModel, ConfigDict, Field` ONLY in `project.py`
- NO imports between `project.py`, `env.py`, `secrets.py` (each is independently leaf-clean — internal module factoring is the package's choice; the public API surfaces them via `__init__.py` re-exports)

**Given** the boundary-validator hook is active
**When** I add an illustrative violation `from sdlc.engine import auto_loop` to any file under `src/sdlc/config/`
**Then** the hook fails with the AC3-of-Story-1.6 violation message:
```
src/sdlc/config/<file>.py:<line>:<line>: import violation: config/ -> engine/ (config/ is forbidden from importing engine/dispatcher/cli/; see Architecture §1073 layered DAG + §1052 dependency-table row)
```
**And** the commit is rejected (exit 1)
**And** there is NO `print()`, NO `subprocess.run`, NO `time.time()`, NO `open()` for state-or-journal writes anywhere under `src/sdlc/config/` (Architecture §483-§494)
**And** NO direct `os.environ[...]` read outside `env.py`'s post-allow-list-check `os.environ.get(name)` call (Architecture §491 — the framework-wide `os.environ` discipline is BUILT BY THIS STORY)

**AC8 — `pyyaml>=6,<7` lands in `[project] dependencies` (NOT `[dependency-groups] dev`); `uv.lock` is regenerated; the `<7` defensive cap matches the Story 1.7 / 1.6 / 1.5 / 1.2 chronological-by-story convention; the CI matrix's `--frozen` cache invalidates once for this dep, then re-caches.**

**Given** `pyproject.toml:11-13` (post-Story-1.7 baseline): `dependencies = ["pydantic>=2,<3", ...]` — exactly one runtime dep
**When** I edit `pyproject.toml` to add `pyyaml`:
```toml
[project]
...
dependencies = [
    "pydantic>=2,<3",   # cap: pydantic 2→3 will introduce schema breaks (v3 is on the roadmap)
    "pyyaml>=6,<7",     # cap: pyyaml 6→7 has not been released; defensive guard against future major
]
```
**Then** the location is `[project] dependencies`, NOT `[dependency-groups] dev` (pyyaml is shipped at runtime — Story 1.8's `project.py` imports it; future `workflows/loader.py`, `specialists/registry.py`, and the Mock AIRuntime's YAML fixtures will also need it at runtime)
**And** the version constraint `>=6,<7` honours pyyaml's stable 6.x line (latest 6.0.x as of 2026-05) AND the chronological-by-story `<N` defensive-cap convention (mypy `<3`, pytest `<10`, pre-commit `<5`, mkdocs `<2`, hypothesis `<7`, pydantic `<3`, pyyaml `<7`)
**And** I run `uv sync` (NOT `--frozen` this once) to regenerate `uv.lock` with pyyaml + its transitive deps (pyyaml has no Python-runtime dependencies; the C-extension `_yaml` is bundled)
**And** I capture the resolved `pyyaml` version from `uv.lock` (`awk '/^name = "pyyaml"$/{getline; print}' uv.lock`); record in the Dev Agent Record's "Latest tech information" section per the Story 1.7 convention
**And** the CI cache discipline matches Story 1.7's pydantic precedent: the `--frozen` step in `.github/workflows/ci.yml` invalidates ONCE (the first run after the lockfile change), then caches for subsequent PRs

**Given** the package surface
**When** I run `uv run python -c "import yaml; print(yaml.__version__)"` after the sync
**Then** the version print is `6.x.y` (any 6.x is acceptable; the floor `>=6` is permissive about patch/minor releases within v6)
**And** `uv run python -c "import yaml; print(yaml.safe_load('foo: bar'))"` exits 0 with output `{'foo': 'bar'}` — confirms safe_load works (the only YAML loader the framework will use; `yaml.load` is forbidden — see Dev Notes "Why yaml.safe_load over yaml.load")

**AC9 — Sprint status + deferred-work ledger updates: Story 1-8 marks itself `ready-for-dev` (this create-story workflow's responsibility) → `in-progress` (dev-story start) → `review` (code-review handoff) → `done` (merge); the Story 1.6 deferred line 22 ("`details` JSON-safety contract") is REFERENCED in Dev Notes but the actual integration with CLI `--json` writer is OUT OF SCOPE for this story (CLI doesn't exist yet — the cross-module integration lands in Story 1.16+ when `cli/output.py` is authored).**

**Given** `_bmad-output/implementation-artifacts/sprint-status.yaml` lists `1-8-foundation-config-module: backlog` (line 58) under `epic-1: in-progress` (line 50)
**When** the create-story workflow finishes
**Then** the create-story workflow has flipped `1-8-foundation-config-module: backlog → ready-for-dev` (Step 6 of the active workflow; dev-story does NOT redo it)
**And** at dev-story start: `ready-for-dev → in-progress`
**And** at code-review handoff: `in-progress → review`
**And** at merge: `review → done`
**And** `last_updated:` is bumped on every transition
**And** `last_action:` is updated at every transition with the standard format `"<workflow> 1-8-foundation-config-module (status: <from> → <to>)"`
**And** Epic 1's `epic-1: in-progress` status is UNCHANGED (13 stories — 1.9 through 1.21 — remain backlog after Story 1.8 lands)
**And** ALL existing comments + the `STATUS DEFINITIONS` block (lines 9-36) + `WORKFLOW NOTES` (lines 31-36) are preserved verbatim
**And** NEW deferred items surfaced during dev or code-review go in `deferred-work.md` under the `## Deferred from: code review of 1-8-…` header pattern Story 1.5/1.6/1.7 established

## Tasks / Subtasks

- [x] **Task 1 — Add `pyyaml>=6,<7` to `[project] dependencies` and regenerate `uv.lock`.** (AC: #8)
  - [x] 1.1 Edit `pyproject.toml:11-13`: append `"pyyaml>=6,<7",  # cap: pyyaml 6→7 has not been released; defensive guard against future major` to the existing `dependencies` list (preserve the pydantic line). The list is now 2 elements.
  - [x] 1.2 Run `uv sync` (NOT `--frozen`) to regenerate `uv.lock` with pyyaml. Capture the resolved `pyyaml` version (`awk '/^name = "pyyaml"$/{getline; print}' uv.lock`) for the Dev Agent Record's "Latest tech information" section. Note: pyyaml has NO transitive Python runtime deps; the C-extension is wheel-bundled.
  - [x] 1.3 Verify post-sync: `uv run python -c "import yaml; print(yaml.__version__); print(yaml.safe_load('foo: bar'))"` should print the version + `{'foo': 'bar'}` — confirms the import + safe_load work.
  - [x] 1.4 Verify CI: the next `uv sync --frozen` call (e.g. inside a fresh checkout or CI) succeeds; the lockfile is the single source of truth post-edit.
  - [x] 1.5 Confirm pyyaml is at runtime `[project] dependencies` (NOT `[dependency-groups] dev`); a downstream consumer doing `pip install sdlc-framework` (no `--group dev`) MUST get pyyaml.

- [x] **Task 2 — Author `src/sdlc/config/secrets.py` (start with leaf-most file — no `errors/` import needed).** (AC: #3, #5, #6, #7)
  - [x] 2.1 Create `src/sdlc/config/__init__.py` skeleton (empty re-exports for now; populate in Task 5):
    ```python
    from __future__ import annotations
    ```
  - [x] 2.2 Create `src/sdlc/config/secrets.py`:
    ```python
    from __future__ import annotations

    import re
    from collections.abc import Mapping
    from typing import Final

    REDACTION_MARKER: Final[str] = "<REDACTED:secret>"

    # Patterns are tuples of (regex, label). Compile once at module load for performance.
    # Sources: epics.md:621, architecture.md:566 + NFR-SEC-1 (prd.md:832).
    SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),                           # OpenAI/Anthropic-shaped key
        re.compile(r"pk_(?:live|test)_[A-Za-z0-9]{20,}"),               # Stripe public key
        re.compile(r"ghp_[A-Za-z0-9]{30,}"),                            # GitHub PAT (36 chars typical)
        re.compile(r"AKIA[A-Z0-9]{16}"),                                # AWS Access Key ID (exactly 20 chars)
        re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT three-segment
    )


    def sanitize(text: str) -> str:
        """Redact known secret patterns in text. Idempotent; non-matching strings pass through."""
        for pattern in SECRET_PATTERNS:
            text = pattern.sub(REDACTION_MARKER, text)
        return text


    def sanitize_mapping(obj: Mapping[str, object]) -> dict[str, object]:
        """Recursively redact secret-shaped strings in a mapping; returns a NEW dict (input is not mutated)."""
        result: dict[str, object] = {}
        for key, value in obj.items():
            result[key] = _sanitize_value(value)
        return result


    def _sanitize_value(value: object) -> object:
        if isinstance(value, str):
            return sanitize(value)
        if isinstance(value, Mapping):
            return sanitize_mapping(value)  # type: ignore[arg-type]
        if isinstance(value, list):
            return [_sanitize_value(v) for v in value]
        return value
    ```
    Note: The `# type: ignore[arg-type]` comment may not be needed if `Mapping[str, object]` typechecks cleanly; verify with mypy and remove if unnecessary. The `Mapping` import is from `collections.abc` (PEP 585, py3.9+). Use `dict[str, object]` (NOT `Dict[str, Any]`) per Story 1.6+ convention.
  - [x] 2.3 Verify LOC count: `wc -l src/sdlc/config/secrets.py` should print ≤ 60 (well under 400 cap).
  - [x] 2.4 Run `uv run ruff check src/sdlc/config`, `uv run ruff format --check src/sdlc/config`, `uv run mypy --strict src/sdlc/config/secrets.py` — all exit 0 before moving to Task 3.

- [x] **Task 3 — Author `src/sdlc/config/env.py`.** (AC: #2, #5, #6, #7)
  - [x] 3.1 Create `src/sdlc/config/env.py`:
    ```python
    from __future__ import annotations

    import os
    from typing import Final

    from sdlc.errors import ConfigError

    ENV_PREFIX_ALLOWLIST: Final[tuple[str, ...]] = ("SDLC_", "CLAUDE_")
    ENV_EXACT_ALLOWLIST: Final[frozenset[str]] = frozenset({"GH_TOKEN"})


    def read_env(name: str) -> str | None:
        """Return the env-var value if `name` matches the allow-list, else raise ConfigError.

        Allow-list per Architecture §671 + NFR-SEC-2 (prd.md:798):
        - prefix matches: SDLC_*, CLAUDE_*
        - exact matches: GH_TOKEN (consumed only by the pr-author specialist)

        Returns None for allowed-but-unset env vars (legitimate "not configured" signal).
        Raises ConfigError("env var '<name>' not in allow-list (...)") for forbidden reads.
        """
        if not _is_allowed(name):
            raise ConfigError(
                f"env var {name!r} not in allow-list (SDLC_*, CLAUDE_*, GH_TOKEN)",
                details={"name": name},
            )
        return os.environ.get(name)


    def _is_allowed(name: str) -> bool:
        if name in ENV_EXACT_ALLOWLIST:
            return True
        return any(name.startswith(prefix) for prefix in ENV_PREFIX_ALLOWLIST)
    ```
  - [x] 3.2 Verify LOC count ≤ 50.
  - [x] 3.3 Run quality chain on `env.py`: `uv run ruff check src/sdlc/config/env.py`, `uv run ruff format --check src/sdlc/config/env.py`, `uv run mypy --strict src/sdlc/config/env.py` — all exit 0.

- [x] **Task 4 — Author `src/sdlc/config/project.py`.** (AC: #1, #4, #5, #6, #7)
  - [x] 4.1 Create `src/sdlc/config/project.py`:
    ```python
    from __future__ import annotations

    from pathlib import Path
    from typing import ClassVar, Final

    import yaml
    from pydantic import BaseModel, ConfigDict, Field, ValidationError

    from sdlc.errors import ConfigError

    DEFAULT_PROJECT_YAML: Final[str] = "project.yaml"


    class ProjectConfig(BaseModel):
        """Typed wrapper for project.yaml (FR51).

        Schema sources: epics.md:610-613, prd.md:797, architecture.md:337/466/652/752.
        """

        model_config: ClassVar[ConfigDict] = ConfigDict(
            extra="forbid",
            frozen=True,
            str_strip_whitespace=False,
        )

        max_parallel_agents: int = Field(default=4, ge=1)
        auto_brainstorm: bool = True
        legacy_code_globs: tuple[str, ...] = Field(default_factory=tuple)
        watchdog_timeout_minutes: int = Field(default=30, ge=1)


    def load_project_config(path: Path | None = None) -> ProjectConfig:
        """Load `project.yaml` from `path` (default: <cwd>/project.yaml).

        Behaviour:
        - Missing file → return ProjectConfig() defaults.
        - Empty/whitespace-only file → return ProjectConfig() defaults.
        - Malformed YAML → ConfigError.
        - Unknown key → ConfigError naming the key.
        - Wrong type → ConfigError wrapping pydantic ValidationError.
        """
        target = Path(path) if path is not None else Path.cwd() / DEFAULT_PROJECT_YAML
        if not target.exists():
            return ProjectConfig()
        raw = target.read_text(encoding="utf-8")
        if not raw.strip():
            return ProjectConfig()
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ConfigError(
                f"project.yaml malformed: {exc}",
                details={"path": str(target)},
            ) from exc
        if data is None:
            return ProjectConfig()
        if not isinstance(data, dict):
            raise ConfigError(
                "project.yaml must be a mapping at top level",
                details={"path": str(target), "got_type": type(data).__name__},
            )
        try:
            return ProjectConfig(**data)
        except ValidationError as exc:
            raise _wrap_validation_error(exc, target) from exc


    def _wrap_validation_error(exc: ValidationError, target: Path) -> ConfigError:
        first = exc.errors()[0]
        loc = first.get("loc", ())
        key = loc[0] if loc else "<unknown>"
        if first.get("type") == "extra_forbidden":
            return ConfigError(
                f"project.yaml unknown key {key!r}",
                details={"path": str(target), "key": str(key)},
            )
        return ConfigError(
            f"project.yaml field {key!r} invalid: {first.get('msg', 'validation failed')}",
            details={"path": str(target), "field": str(key), "errors": exc.errors()},
        )
    ```
  - [x] 4.2 Verify LOC count ≤ 100.
  - [x] 4.3 Quality chain on `project.py`: `uv run ruff check src/sdlc/config/project.py`, `uv run ruff format --check`, `uv run mypy --strict src/sdlc/config/project.py` — all exit 0.

- [x] **Task 5 — Wire `src/sdlc/config/__init__.py` to re-export the public API.** (AC: #5)
  - [x] 5.1 Replace the Task 2.1 skeleton `__init__.py` with the full re-export:
    ```python
    from __future__ import annotations

    from sdlc.config.env import (
        ENV_EXACT_ALLOWLIST,
        ENV_PREFIX_ALLOWLIST,
        read_env,
    )
    from sdlc.config.project import ProjectConfig, load_project_config
    from sdlc.config.secrets import (
        REDACTION_MARKER,
        SECRET_PATTERNS,
        sanitize,
        sanitize_mapping,
    )

    # Semantic order: project (loader + model) → env (allow-list reader + constants)
    # → secrets (sanitizer + constants). Per Story 1.6/1.7's # noqa: RUF022 convention.
    __all__ = (  # noqa: RUF022
        "ProjectConfig",
        "load_project_config",
        "ENV_PREFIX_ALLOWLIST",
        "ENV_EXACT_ALLOWLIST",
        "read_env",
        "REDACTION_MARKER",
        "SECRET_PATTERNS",
        "sanitize",
        "sanitize_mapping",
    )
    ```
  - [x] 5.2 Verify the package surface: `uv run python -c "from sdlc.config import load_project_config, ProjectConfig, read_env, ENV_PREFIX_ALLOWLIST, ENV_EXACT_ALLOWLIST, sanitize, sanitize_mapping, SECRET_PATTERNS, REDACTION_MARKER; print('ok')"` exits 0.
  - [x] 5.3 Verify LOC count ≤ 30.
  - [x] 5.4 Quality chain: `uv run pre-commit run --all-files` — every hook exits 0. Boundary-validator pre-grants `config/ → {errors, contracts}`; the actual imports use `errors` only (the `contracts` grant is forward-defensive — same pattern as Story 1.7's unused `errors`-grant-in-`contracts`).

- [x] **Task 6 — Author per-file unit tests under `tests/unit/config/`.** (AC: #6)
  - [x] 6.1 Create `tests/unit/config/__init__.py` (empty marker; mirrors Story 1.6/1.7 pattern).
  - [x] 6.2 Create `tests/unit/config/test_project.py` covering the AC6 Cartesian for `ProjectConfig` + `load_project_config` (see AC6 list — happy path with all 4 fields, empty file → defaults, missing file → defaults, unknown-key rejection with `details["key"]` assertion, wrong-type rejection, malformed-YAML rejection, frozen-mutation, equality, hashability, list→tuple coercion, top-level-not-dict rejection). Use `tmp_path` fixture for filesystem isolation.
  - [x] 6.3 Create `tests/unit/config/test_env.py` covering the AC6 Cartesian for `read_env` (SDLC_ + CLAUDE_ prefix accepted, GH_TOKEN exact accepted, HOME/PATH/OPENAI_API_KEY rejected, lowercase rejected, empty-name rejected, allowed-but-unset returns None, constants regression-guards). Use `monkeypatch.setenv`/`monkeypatch.delenv` for env-var isolation.
  - [x] 6.4 Create `tests/unit/config/test_secrets.py` covering the AC6 Cartesian for `sanitize` + `sanitize_mapping` (per-pattern redaction, multi-pattern, multi-position, no-secret passthrough, empty-string passthrough, idempotency, nested-dict, list-values, non-string leaves, immutability assertion, constants regression-guards).
  - [x] 6.5 Run `uv run pytest tests/unit/config -v` — all pass. Expected count: ~12 (project) + ~10 (env) + ~14 (secrets) = ~36 unit tests.

- [x] **Task 7 — Author the integration test + the static linter + wire the linter into pre-commit.** (AC: #3)
  - [x] 7.1 Create `tests/integration/test_secret_hygiene.py` per Architecture §990:
    ```python
    from __future__ import annotations

    import pytest

    from sdlc.config import sanitize_mapping
    from sdlc.errors import SdlcError


    @pytest.mark.integration
    class TestSecretHygiene:
        def test_envelope_details_redacted(self) -> None:
            error = SdlcError(
                "test",
                details={"api_key": "sk-abc123def456ghi789jkl012mno345pq"},
            )
            envelope = error.to_envelope()
            details = envelope["error"]["details"]
            assert isinstance(details, dict)
            sanitized = sanitize_mapping(details)
            assert sanitized["api_key"] == "<REDACTED:secret>"

        def test_multi_pattern_envelope(self) -> None:
            error = SdlcError("multi", details={
                "openai_key": "sk-abc123def456ghi789jkl012mno345pq",
                "github_pat": "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
                "aws_access": "AKIAIOSFODNN7EXAMPLE",
                "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
                "stripe": "pk_live_abc123def456ghi789jkl0",
            })
            details = error.to_envelope()["error"]["details"]
            assert isinstance(details, dict)
            sanitized = sanitize_mapping(details)
            assert all(v == "<REDACTED:secret>" for v in sanitized.values())

        def test_nested_envelope(self) -> None:
            error = SdlcError("nested", details={
                "caller": {"name": "agent", "credentials": {"api_key": "sk-abc123def456ghi789jkl012mno345pq"}},
            })
            details = error.to_envelope()["error"]["details"]
            assert isinstance(details, dict)
            sanitized = sanitize_mapping(details)
            assert sanitized["caller"]["credentials"]["api_key"] == "<REDACTED:secret>"
    ```
  - [x] 7.2 Create `scripts/check_no_hardcoded_secrets.py` — a lightweight static linter (≤ 80 LOC) that:
    - Walks each `*.py` path passed on argv (or `src/sdlc/` recursively if no argv)
    - Reads each file, applies the SAME `SECRET_PATTERNS` from `sdlc.config.secrets` (re-imports them — single source of truth)
    - Skips any line containing `# noqa: secret` (escape hatch for genuine test/example references; documented in script docstring)
    - Skips files under `tests/`, `scripts/check_no_hardcoded_secrets.py` (self), `_bmad/`, `_bmad-output/`, `.claude/`, `_site/`, `docs/`
    - Prints `<file>:<line>:<column>: hardcoded secret literal matches pattern <pattern>` on each violation
    - Exits 0 on clean, 1 on violations
    - Uses `from sdlc.config.secrets import SECRET_PATTERNS` — depends on the `config/` package being importable, so the script's first action is `sys.path` insertion (mirror of `tests/conftest.py` if needed) OR (preferred) the script imports via a `pyproject.toml`-aware path manipulation. The cleanest implementation: the script is run as `uv run python scripts/check_no_hardcoded_secrets.py ...`, and `uv run` puts `src/` on `sys.path` automatically. Verify this in dev.
  - [x] 7.3 Wire the new linter into `.pre-commit-config.yaml` AFTER the existing `boundary-validator` and BEFORE `specialist-validator`:
    ```yaml
    # ----- secret-hardcode validator (Story 1.8 / NFR-SEC-1) -----
    - repo: local
      hooks:
        - id: secret-hardcode-validator
          name: scan src/ for hardcoded secret literals (NFR-SEC-1)
          entry: uv run python scripts/check_no_hardcoded_secrets.py
          language: system
          types: [python]
          files: ^src/sdlc/.*\.py$
          pass_filenames: true
    ```
    Order matters: the boundary-validator finishes its import-graph + LOC checks first; THEN this linter scans content for secret literals. The hygiene hooks (trailing-whitespace, etc.) come AFTER.
  - [x] 7.4 Self-test the linter:
    - `uv run python scripts/check_no_hardcoded_secrets.py src/sdlc/` → exit 0 (clean codebase).
    - Spot-test (NOT committed): temporarily add `_FAKE_KEY = "sk-abc123def456ghi789jkl012mno345pq"` to `src/sdlc/config/secrets.py`; run the linter → exit 1 with the violation message; revert.
  - [x] 7.5 Run `uv run pre-commit run --all-files` end-to-end — every hook (now including the new `secret-hardcode-validator`) exits 0.

- [x] **Task 8 — Verify coverage gates per AC6.** (AC: #6)
  - [x] 8.1 Run the targeted ≥ 95 gate: `uv run pytest --cov=src/sdlc/config --cov-branch --cov-report=term-missing --cov-fail-under=95 tests/unit/config tests/integration/test_secret_hygiene.py`. Exit 0.
  - [x] 8.2 Run the project-wide ≥ 90 gate: `uv run pytest`. Exit 0; project-wide coverage stays at or above the previous baseline.
  - [x] 8.3 If coverage < 95 on `config/`: do NOT add `# pragma: no cover` to bypass — find the missing branch. The acceptable-bypass list (`pyproject.toml:153-156`) is `if TYPE_CHECKING:`, `raise NotImplementedError`, and `@(abc\.)?abstractmethod`; nothing in `config/` v1 should qualify (no abstract methods, no TYPE_CHECKING-only imports for runtime code).

- [x] **Task 9 — Whole-suite regression sweep.** (AC: #6, #7)
  - [x] 9.1 Run the full Story 1.4 + 1.5 + 1.6 + 1.7 quality chain locally:
    ```
    uv run ruff check src/ tests/ scripts/
    uv run ruff format --check src/ tests/ scripts/
    uv run mypy --strict src/
    uv run pre-commit run --all-files
    uv run pytest
    uv run mkdocs build --strict --site-dir _site
    ```
    Every command exits 0. Test count delta: 311 baseline (post-1.7) → ~350+ total.
  - [x] 9.2 Confirm the boundary-validator hook prints zero violations across the whole tree: `uv run python scripts/check_module_boundaries.py $(git ls-files 'src/sdlc/**.py' 'tests/**.py' 'scripts/**.py')` — exit 0.
  - [x] 9.3 Confirm `uv run python -c "import sdlc.config; print(sdlc.config.__all__)"` prints the 9-name tuple in the Task 5.1 semantic order.
  - [x] 9.4 Confirm the new pre-commit hook is wired: `uv run pre-commit run secret-hardcode-validator --all-files` exits 0.

- [x] **Task 10 — Update `_bmad-output/implementation-artifacts/sprint-status.yaml` AT EACH transition, NOT in a single end-of-story write.** (AC: #9)
  - [x] 10.1 At the start of dev (after `bmad-create-story` completes): `1-8-foundation-config-module: ready-for-dev` (this transition is owned by the create-story workflow itself; dev-story does NOT redo it).
  - [x] 10.2 When dev-story begins implementation: `1-8-foundation-config-module: in-progress`. Bump `last_updated:` to today's ISO date. Update `last_action:` to `"dev-story 1-8-foundation-config-module (status: ready-for-dev → in-progress)"`.
  - [x] 10.3 At code-review handoff: `1-8-foundation-config-module: review`. Same `last_updated` + `last_action` discipline.
  - [x] 10.4 At merge: `1-8-foundation-config-module: done`. Same discipline. Epic 1's `epic-1: in-progress` stays untouched (13 stories — 1.9 through 1.21 — still backlog after Story 1.8 lands).
  - [x] 10.5 Preserve ALL comments + STATUS DEFINITIONS block in the YAML (Story 1.5/1.6/1.7 convention).

### Review Findings

_Code review 2026-05-08 — adversarial 3-layer (Blind Hunter + Edge Case Hunter + Acceptance Auditor). 60 raw findings → 20 after dedup (1 dismissed)._

**Decision-needed:** _(resolved 2026-05-08 — both became Patch)_

- [x] [Review][Decision→Patch] Pydantic strict mode for `max_parallel_agents` — Resolved: add `strict=True` to align with story 1.8's strict pattern (`extra=forbid`, `frozen=True`).
- [x] [Review][Decision→Patch] Audit policy for `# noqa: secret` — Resolved: require `# noqa: secret — <reason ≥ 10 chars>` format.

**Patch:**

- [ ] [Review][Patch] Add `strict=True` to `max_parallel_agents` field [src/sdlc/config/project.py:18] — Pydantic v2 coerces float `4.5 → 4` silently. Aligns with story 1.8's strict-config pattern.
- [ ] [Review][Patch] Require justification for `# noqa: secret` [scripts/check_no_hardcoded_secrets.py] — Enforce format `# noqa: secret — <reason ≥ 10 chars>`. Plain `# noqa: secret` becomes an error. Add unit test for both shapes.

- [ ] [Review][Patch] Inconsistent error details key (`field` vs `key`) in `_wrap_validation_error` [src/sdlc/config/project.py:79] — `extra_forbidden` branch uses `details={"key": ...}` but the wrong-type branch uses `details={"field": ...}`. Standardize to `"key"`.
- [ ] [Review][Patch] Raw `exc.errors()` leaks pydantic internals (and potentially raw secrets from invalid YAML) into ConfigError details [src/sdlc/config/project.py:75-86] — Apply `sanitize_mapping`/`sanitize` to error payloads before embedding, or strip to `{type, msg}` only.
- [ ] [Review][Patch] Wrong-type validation message says "invalid" but Dev Notes mandate "wrong type" wording [src/sdlc/config/project.py:84] — Update message template to match the spec's exact wording.
- [ ] [Review][Patch] `sanitize_mapping` does not recurse into `tuple`, `set`, `frozenset` [src/sdlc/config/secrets.py:_sanitize_value] — Containers other than `dict`/`list` pass through unredacted. Extend `_sanitize_value` to handle `tuple` (return tuple), `set`/`frozenset` (return same type), and `bytes` (decode + sanitize or skip safely).
- [ ] [Review][Patch] Mapping with non-str keys not validated despite `Mapping[str, object]` signature [src/sdlc/config/secrets.py] — Either coerce keys via `str()` or raise on non-string keys. Current behavior is inconsistent with the type annotation.
- [ ] [Review][Patch] Circular-reference RecursionError in `_sanitize_value` [src/sdlc/config/secrets.py] — Self-referential dicts/lists trigger uncaught `RecursionError`. Track seen `id()` set and substitute `<circular>` placeholder.
- [ ] [Review][Patch] `AKIA` regex lacks word boundaries [src/sdlc/config/secrets.py:SECRET_PATTERNS] — `re.compile(r"AKIA[A-Z0-9]{16}")` matches inside larger uppercase strings. Wrap with `\b` to reduce false positives without weakening true-positive coverage.
- [ ] [Review][Patch] `argv` directory paths are not expanded [scripts/check_no_hardcoded_secrets.py:main] — When user passes a directory on CLI, only the directory itself is checked (no rglob). Detect dir vs file and apply `rglob("*.py")` consistently.
- [ ] [Review][Patch] `_is_exempt` over-broad path component check [scripts/check_no_hardcoded_secrets.py:_is_exempt] — `any(exempt in path.parts for exempt in _EXEMPT_DIRS)` exempts any path containing a component named e.g. `scripts` (so `src/sdlc/scripts/foo.py` is wrongly exempt). Anchor to top-level repo root segments only.
- [ ] [Review][Patch] `sys.path.insert(0, ...)` shadows installed `sdlc` package [scripts/check_no_hardcoded_secrets.py] — Hook reaches into local `src/` and may collide with editable install. Use absolute import path or remove the insert.
- [ ] [Review][Patch] Empty/bare prefix env names pass allowlist [src/sdlc/config/env.py:_is_allowed] — `"SDLC_"` (empty suffix) and `""` are accepted because `startswith` returns `True` for the prefix itself. Add suffix-non-empty check and reject empty/whitespace names.

**Deferred (pre-existing or out-of-scope):**

- [x] [Review][Defer] Broader secret patterns (Slack `xoxb-`, Google `AIza...`, AWS Secret 40-char) [src/sdlc/config/secrets.py] — deferred, scope expansion beyond Story 1.8 ACs.
- [x] [Review][Defer] CI coverage gate enforcement (90% global / ≥95% per-package) — deferred, owned by Story 1.3 (CI/CD).
- [x] [Review][Defer] YAML size cap / DoS hardening for `load_project_config` [src/sdlc/config/project.py] — deferred, not in Story 1.8 spec.
- [x] [Review][Defer] Pre-commit hook scope expansion to `tests/` for secret hardcode validator — deferred, current scope `^src/sdlc/.*\.py$` is intentional per spec.
- [x] [Review][Defer] README/migration docs for env allow-list semantics — deferred, separate doc ticket.



### File set this story creates / modifies

**NEW files (created by Story 1.8):**

```
src/sdlc/config/__init__.py                                               # Task 5.1
src/sdlc/config/project.py                                                # Task 4.1
src/sdlc/config/env.py                                                    # Task 3.1
src/sdlc/config/secrets.py                                                # Task 2.2
tests/unit/config/__init__.py                                             # Task 6.1 (empty marker)
tests/unit/config/test_project.py                                         # Task 6.2
tests/unit/config/test_env.py                                             # Task 6.3
tests/unit/config/test_secrets.py                                         # Task 6.4
tests/integration/test_secret_hygiene.py                                  # Task 7.1 (per Architecture §990)
scripts/check_no_hardcoded_secrets.py                                     # Task 7.2
```

**MODIFIED files:**

```
pyproject.toml                                                            # Task 1.1 (+pyyaml>=6,<7 in [project] dependencies)
uv.lock                                                                   # Task 1.2 (regenerated)
.pre-commit-config.yaml                                                   # Task 7.3 (+secret-hardcode-validator hook)
_bmad-output/implementation-artifacts/sprint-status.yaml                  # Task 10 (4 transitions)
```

**Do NOT** create:
- `src/sdlc/state/`, `src/sdlc/journal/`, `src/sdlc/concurrency/`, or any module that is not `config/`. Those are owned by Stories 1.9 / 1.10 / 1.11 (per Architecture §1404 implementation order: `errors/ → ids/ → contracts/ → config/ → concurrency/ → state/ → journal/`).
- A new ADR (e.g. `ADR-014-config-module.md`). Story 1.6/1.7 deferred ADR-014 to "the future story that crosses the trigger" (10th `SdlcError` subclass or `EXIT_CODE_MAP` semantics change). Story 1.8 does NOT cross either trigger; the existing `ConfigError` (Story 1.6) is unchanged.
- A `cli/` integration for the JSON envelope. Story 1.6 deferred line 22 records this dependency: "Story 1.8 (`config/secrets.py` + CLI `--json` writer) — adds the JSON-safe sanitization layer that wraps `to_envelope()` output before serialization." Story 1.8 ships the `sanitize_mapping()` helper that the future `cli/output.py` will compose with `to_envelope()`. The actual wiring lives in Story 1.16+ when CLI is authored. Document this composition pattern in the integration test (Task 7.1) so the future CLI story has a copy-paste reference.
- A pydantic model wrapping the entire `to_envelope()` output. The envelope is a `dict[str, object]` by design (Story 1.6 Dev Notes "details JSON-safety layering principle"). Sanitization at the OUTPUT boundary, not the construction site, preserves the layering.
- Property tests under `tests/property/`. The config module's invariants are simple equality checks (allow-list membership, regex match) that are exhaustively covered by unit tests; hypothesis would not stress beyond the unit-test coverage. If a future story adds runtime invariants (e.g. config-roundtrip via YAML serialize-then-parse), THAT story adds a property test.

### `details` JSON-safety: layering principle (Story 1.6 deferred line 22 reference)

Story 1.6's `SdlcError.details: dict[str, object]` accepts arbitrary leaf types — strings, ints, bools, None, dicts, lists. The `to_envelope()` method renders this into the `--json` envelope shape `{"error": {"code": ..., "message": ..., "details": ..., "exit_code": ...}}`. Story 1.6 deferred the JSON-safety contract (specifically: redaction of secret-shaped strings + handling of non-JSON-safe leaves like `datetime`/`Path`/`Decimal`) to Story 1.8 + Story 1.16 (CLI):

- **Story 1.8 owns:** the `sanitize_mapping()` helper that walks dict/list leaves and redacts secret-shaped strings via `SECRET_PATTERNS`.
- **Story 1.16 owns:** the CLI `--json` writer that composes `sanitize_mapping(error.to_envelope()["error"]["details"])` and uses `json.dumps(..., default=str)` (or equivalent) to handle `datetime`/`Path`/`Decimal` leaves.

This story (1.8) does NOT integrate with the CLI writer (CLI doesn't exist). The integration test (Task 7.1) demonstrates the composition pattern as a forward-reference for Story 1.16. The pattern:

```python
envelope = error.to_envelope()
envelope["error"]["details"] = sanitize_mapping(envelope["error"]["details"])
json_output = json.dumps(envelope, default=str)
```

A future story may consolidate this into a single `safe_envelope(error: SdlcError) -> dict[str, object]` helper in `cli/output.py` that handles BOTH redaction AND non-JSON-safe leaf coercion.

### Why tuple over list for `legacy_code_globs`

Pydantic v2 frozen models compute `__hash__` field-wise; lists are unhashable in Python (`hash([])` raises `TypeError`). If `legacy_code_globs: list[str]`, `ProjectConfig` would join the unhashable matrix (alongside `JournalEntry`/`ResumeToken`/`SpecialistFrontmatter`/`WorkflowSpec` per Story 1.7 AC4 Hashability matrix). For `ProjectConfig`, hashability is a desirable property because:

1. Future caches (e.g. workflow loader caching `ProjectConfig`-keyed compilation results) need hashable keys.
2. `frozenset[ProjectConfig]` and `dict[ProjectConfig, V]` are reasonable patterns for multi-project scenarios (currently OUT-OF-SCOPE for v1, but cheap to enable).
3. Tuple is a more explicit "ordered, immutable sequence" — matches the intent of `legacy_code_globs` (an ordered priority list of globs the brownfield-aware specialists consult).

YAML's `list` representation is auto-coerced to `tuple[str, ...]` by pydantic v2's type-coercion (verified in AC4); no custom validator is required. The CONSUMER side (Story 3.x brownfield specialists) will iterate the tuple — `for glob in cfg.legacy_code_globs:` works identically for both tuple and list.

**Hashability matrix update (post-Story-1.8):**
- Hashable: `{HookPayload, ProjectConfig}` (2 contracts/configs)
- Unhashable: `{JournalEntry, ResumeToken, SpecialistFrontmatter, WorkflowSpec}` (4)

### Why `yaml.safe_load` over `yaml.load`

`yaml.load(stream)` (with default `Loader`) deserializes arbitrary Python objects — including `!!python/object` tags that can execute arbitrary code at parse time. This is a documented YAML deserialization vulnerability (CVE-2017-18342 class). `yaml.safe_load(stream)` restricts the loader to safe YAML primitives (strings, ints, floats, booleans, None, lists, dicts) and refuses Python-specific tags. NFR-PRIV-1 ("no outbound HTTP from framework process") and NFR-SEC-1 (no secret leakage) demand the safe loader; PyYAML's documentation explicitly recommends `safe_load` for any user-supplied YAML.

This story uses `yaml.safe_load` exclusively. A pre-commit grep enforcing "`yaml.load(` outside `tests/` is forbidden" is a CANDIDATE deferred item; not added in v1 because (a) `yaml.safe_load` is the only loader the framework code uses, (b) ruff has no built-in rule for this, (c) a custom regex hook adds maintenance burden for a single-call-site discipline. If `yaml.load` ever appears in framework source, code review catches it.

### Secret pattern reference (verbatim from epics.md:621 + sources)

| Pattern | Regex | Source / canonical format | Match length |
|---|---|---|---|
| OpenAI/Anthropic-shaped | `sk-[A-Za-z0-9_-]{20,}` | OpenAI `sk-...` and Anthropic `sk-ant-...` keys; both share the `sk-` prefix per OpenAI docs (https://platform.openai.com/docs/api-reference/authentication) and Anthropic docs (https://docs.anthropic.com/en/api/getting-started); `_` and `-` allowed in modern formats | ≥ 23 chars total (`sk-` + 20 chars min) |
| Stripe public | `pk_(?:live\|test)_[A-Za-z0-9]{20,}` | Stripe docs (https://stripe.com/docs/keys); `pk_live_*` for production, `pk_test_*` for sandbox | ≥ 28 chars total |
| GitHub PAT | `ghp_[A-Za-z0-9]{30,}` | GitHub PAT format docs; tokens are 36 chars after `ghp_` (40 total) but accept ≥ 30 to tolerate format evolutions | ≥ 34 chars total |
| AWS Access Key ID | `AKIA[A-Z0-9]{16}` | AWS docs (https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html); EXACTLY 20 chars (`AKIA` + 16) | exactly 20 chars |
| JWT three-segment | `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` | RFC 7519; both header and payload start with `eyJ` (base64url-encoded `{"`); signature is base64url | variable, ≥ 50 chars typical |

**Why these 5 specifically:**
- The framework integrates with Claude (`sk-`), GitHub (`ghp_`), and arbitrary user-supplied payloads (likely AWS, Stripe, JWT). These cover the highest-likelihood leak surfaces.
- Anthropic Claude API keys use the same `sk-` prefix as OpenAI; the regex is shared.
- AWS Secret Access Keys (40-char base64) are NOT in v1 — the prefix is empty, so any 40-char base64 string would false-positive on legitimate hashes (`sha256:` prefixed). The Access Key ID is sufficient as a leak signal: if AKIA appears, the secret key is also at risk.
- Slack tokens (`xoxb-*`, `xoxp-*`), Google API keys (`AIza*`), Azure keys (no canonical prefix) are deferred to v0.3+ when those integrations land.

**False-positive surface:**
- `sk-` is short; legitimate strings like "skill" do NOT match because of the 20-char minimum after the prefix.
- `pk_test_` is intentional — Stripe test keys ARE secrets in CI/test contexts (they have spending caps but real auth power).
- `AKIA` collides with no English word; false-positive rate is essentially zero.
- `eyJ` collides with no English word; false-positive rate is essentially zero except for genuine JSON literals starting with `{"<some-base64-prefix>"` — vanishingly rare.

### Why env reads return raw secrets, not sanitized

`read_env("CLAUDE_API_KEY")` returns the raw `sk-ant-...` string. The `sanitize()` layer is applied at WRITE time (state.json, journal.log, log lines, `to_envelope()` output) — NOT at READ time. Reasons:

1. **Functional correctness:** the AI runtime needs the raw API key to authenticate. Sanitizing at read time breaks the framework.
2. **Layering:** the sanitization layer is at the persistence + observability boundary, not the in-memory boundary. `read_env` reads into memory; the in-memory string IS the secret. `sanitize` is invoked when the in-memory value is about to leave the process (write to disk, write to log, render in `--json` output).
3. **Single source of truth:** there is exactly one redaction site per leak surface (state.json writes, journal writes, log lines, JSON envelope rendering). Adding a redundant redaction at read time would double-process and create drift.

The discipline: **secrets in memory: OK. Secrets on disk: NEVER. Secrets in logs: NEVER. Secrets in `--json` output: NEVER.**

### Why a static linter for source-level secrets

The `scripts/check_no_hardcoded_secrets.py` linter scans the FRAMEWORK SOURCE (under `src/sdlc/`) for hardcoded secret literals. This catches:

1. Developer accidentally pastes a real API key into a code comment, docstring, or test fixture.
2. A copy-paste from a debugging session leaves a token in code.
3. Future stories add features that hardcode test credentials.

What the linter does NOT catch:
- Secrets in user-supplied `project.yaml`, `state.json`, or other run-time data — those are the SANITIZER's job at write time.
- Encoded/encrypted secrets that don't match the documented patterns.
- Secrets stored in env vars (legitimate; that's what env vars are for).

The linter's scope is intentionally narrow: catch the simple "secret pasted into source" mistake before it lands in a commit. NFR-SEC-1's static-lint requirement is a SUPERSET of this story's linter — the future enhancement (Story 1.10 + 1.11) is to scan the source for "code calling `state.mutate(...)` with secret-shaped string args." That requires `state.mutate` to exist (Story 1.10 + 1.11) and is therefore deferred. The deferred-work entry will be added at code-review time if the gap is flagged.

### Cross-module import inventory (boundary-validator audit)

Per `MODULE_DEPS["config"]`:

| File | Imports allowed | Imports actually used in v1 |
|---|---|---|
| `__init__.py` | `sdlc.errors`, `sdlc.contracts`, sub-modules of `sdlc.config` | Sub-modules only (no `errors`/`contracts` import) |
| `project.py` | `sdlc.errors`, `sdlc.contracts`, third-party | `sdlc.errors.ConfigError`, `pydantic`, `pyyaml`, `pathlib`, `typing` |
| `env.py` | `sdlc.errors`, `sdlc.contracts`, third-party | `sdlc.errors.ConfigError`, `os`, `typing` |
| `secrets.py` | `sdlc.errors`, `sdlc.contracts`, third-party | `re`, `collections.abc`, `typing` (NO `errors` import — sanitizer does not raise; pure pass-through-or-redact) |

The `contracts` grant (`MODULE_DEPS["config"].depends_on = {"errors", "contracts"}`) is FORWARD-DEFENSIVE — unused in v1 because:
- `ProjectConfig` is its own pydantic model (NOT one of the 5 wire-format contracts).
- A hypothetical future contract MIGHT cross-reference `JournalEntry` or `WorkflowSpec` (e.g. embedding contract names in YAML), but no such case exists in v1.

This mirrors Story 1.7's "the `errors` grant remains in place; the import is unused" pattern.

### Module dependency invariants (post-Story-1.8 state)

After Story 1.8 lands, the foundation layer is COMPLETE for the "config-aware" downstream modules:

- `errors/` — leaf (Story 1.6) ✅
- `ids/` — depends on `errors/` (Story 1.6) ✅
- `contracts/` — depends on `errors/`, `ids/` (Story 1.7) ✅
- `config/` — depends on `errors/`, `contracts/` (Story 1.8 — THIS STORY) ✅
- `concurrency/` — depends on `errors/` (Story 1.9 — NEXT)
- `state/`, `journal/` — depend on `errors/`, `contracts/`, `concurrency/`, `config/` (Stories 1.10/1.11)

Story 1.9 (concurrency) is the only remaining leaf-foundation module. After Story 1.9, the foundation is fully assembled and Story 1.10 can begin the temporal-integrity substrate (state/atomic + journal/writer).

### Pre-commit hook chain interaction (with new secret-hardcode-validator)

Story 1.4 + 1.5 + 1.6 + 1.7 + 1.8 quality chain:

1. **ruff-check** (`tests/**` per-file-ignores exempts `PLR2004` — magic numbers in tests are fine; secret-shaped literals in `tests/unit/config/test_secrets.py` are fine because the linter at step 5 below skips `tests/`)
2. **ruff-format**
3. **mypy --strict src/**
4. **boundary-validator** (LOC cap + import graph)
5. **secret-hardcode-validator** (NEW — Task 7.3) — scans `^src/sdlc/.*\.py$` for hardcoded secret literals matching `SECRET_PATTERNS`
6. **specialist-validator** (placeholder; runs unconditionally)
7. **trailing-whitespace, end-of-file-fixer, mixed-line-ending, check-yaml, check-toml** (hygiene)

Step 5 specifically does NOT scan `tests/`, `scripts/`, `_bmad/`, `_bmad-output/`, `.claude/`, `_site/`, `docs/` — these directories are exempt because (a) tests legitimately need secret-shaped fixtures, (b) scripts is dev-tooling, (c) the others are non-Python or non-source content.

### Previous story intelligence (Stories 1.5 + 1.6 + 1.7 learnings)

From `_bmad-output/implementation-artifacts/1-5-...md` through `1-7-...md` and `deferred-work.md`:

1. **Story 1.7's review patches established 5 conventions Story 1.8 inherits:**
   - Empty-string field rejection — `before_hash`/`after_hash` accept empty strings as valid in 1.7 (deferred line 7). Story 1.8's `ProjectConfig` does NOT have hash fields; `legacy_code_globs` accepts an empty tuple (legitimate "no exemptions"); the `pydantic` `Field(min_length=1)` constraint pattern is available if a future field needs it.
   - `ContractBase(BaseModel)` shared `model_config` DRY refactor — deferred line 9; mirror in `ProjectConfig`'s direct `ConfigDict(...)` declaration. If a 6th model lands in `config/` (e.g. `EnvironmentManifest`), DRY refactor candidate fires.
   - Coverage gate discrepancy 90% global vs 95% per-package — deferred line 12; persist as a discipline (target 95% on `config/`, accept 90% global).
   - `pytest.raises(... match=)` discipline — deferred line 14; Story 1.8 tests use `pytest.raises(ConfigError) as exc` + assert on `exc.value.details["key"]` for clarity.
   - F3-independence module-import-time `Literal` check — deferred line 11; N/A for `config/` (no `Literal` schema_version on ProjectConfig — see "Why no schema_version on ProjectConfig" below).

2. **Story 1.6's `details: dict[str, object]` typing rationale** extends to Story 1.8's `sanitize_mapping(obj: Mapping[str, object])` — strict-friendly, mypy-`extra_checks`-clean.

3. **Story 1.6's `frozen=True` dataclass convention** translates to `frozen=True` in `ProjectConfig`'s `ConfigDict`. Same discipline as Story 1.7 contracts.

4. **Story 1.6's chronological-by-story `<N` defensive-cap convention** extends: pyyaml gets `<7`. Order:
   - mypy `<3` (Story 1.2)
   - pytest `<10` (Story 1.2)
   - pre-commit `<5` (Story 1.4)
   - mkdocs `<2` (Story 1.5)
   - hypothesis `<7` (Story 1.6)
   - pydantic `<3` (Story 1.7)
   - pyyaml `<7` (Story 1.8)

5. **Story 1.5's revisit-by 12-month-from-authoring rule** is irrelevant to Story 1.8 (no new ADR).

6. **Story 1.4's boundary-validator hook** pre-grants `MODULE_DEPS["config"]` (line 42-45 of `check_module_boundaries.py`). Story 1.8's source files import `errors.ConfigError` (in `project.py` and `env.py`) and standard library + pydantic + pyyaml; the `contracts` grant is unused.

7. **Story 1.6's `__init__.py` LOC ≤ 30** convention extends: Story 1.8's `config/__init__.py` will be ~25 LOC (3 import groups + 9-element `__all__` + comment).

8. **Story 1.6/1.7's per-module test subdir convention** extends: Story 1.8 adds `tests/unit/config/` as the FOURTH per-module test subdir (after `errors`, `ids`, `contracts`).

9. **Story 1.7's "no property tests for declarative schemas" decision** extends: `ProjectConfig` is declarative; `read_env` and `sanitize` are exhaustively unit-testable; no property tests added in v1.

10. **Story 1.5's mkdocs `--strict` build**: Story 1.8 adds NO docs surfaces. The build stays green by virtue of doing nothing in `docs/`.

11. **Story 1.6 deferred line 22** explicitly names Story 1.8 as the owner of "the JSON-safe sanitization layer that wraps `to_envelope()` output before serialization." Story 1.8 ships `sanitize_mapping()`; the actual integration with `to_envelope()` is the integration test in Task 7.1, with the cross-module wiring deferred to Story 1.16+ when CLI is authored.

### Why no `schema_version` on `ProjectConfig`

`project.yaml` is a USER-AUTHORED config file, NOT a wire-format contract. The 5 wire-format contracts (Story 1.7) carry `schema_version: Literal[1] = 1` because they cross run/process/version boundaries (state.json, journal.log, signoff records, etc. — bytes serialized in v1.0 must be readable by v1.x readers). `project.yaml` is:

- Authored by humans, not produced by the framework.
- Read at process start, used in-memory, never serialized back to disk.
- Has no version-spanning concerns: a v2.0 framework with new keys would migrate via `sdlc migrate-v2` (Story 1.49) which would rewrite `project.yaml` on disk.

If a future story decides project.yaml needs versioning (e.g. for major-version migration support), the migration framework (Story 1.19) handles it — NOT a `schema_version` field on `ProjectConfig`. This decision matches PRD §FR48 (major-version refusal until `sdlc migrate-vN` runs).

### Required-field matrix (for AC6 missing-field tests)

| Class / Function | Required (no default) | Has default |
|---|---|---|
| `ProjectConfig` | (none) | All 4 fields default — empty `project.yaml` produces a fully-populated default `ProjectConfig` |
| `read_env(name)` | `name: str` | (none) |
| `sanitize(text)` | `text: str` | (none) |
| `sanitize_mapping(obj)` | `obj: Mapping[str, object]` | (none) |
| `load_project_config(path)` | (none) | `path: Path | None = None` (default looks up `<cwd>/project.yaml`) |

### Git intelligence (last 5 commits)

- `4673090 feat: implement foundation modules - errors and ids (Story 1.5-1.6)` — added `src/sdlc/errors/` + `src/sdlc/ids/` + per-module test subdirs + `hypothesis>=6.100,<7` dev-dep + ADR-012-module-layout.md + ADR template + 10 review patches. Story 1.8 follows the same per-module structural pattern (per-feature source file + per-feature test file + `__init__.py` re-exports + semantic-ordered `__all__`). Test count baseline: 311 (post-1.7) → ~350+ after Story 1.8.
- `67489d3 feat: implement module boundary enforcement with pre-commit hooks (Story 1.4)` — added `scripts/check_module_boundaries.py` with `MODULE_DEPS["config"]` already configured (line 42-45, granting `depends_on={"errors","contracts"}` and `forbidden_from={"engine","dispatcher","cli"}`). Story 1.8 needs ZERO changes to `MODULE_DEPS`; the hook is pre-configured. The new `secret-hardcode-validator` hook does NOT alter `MODULE_DEPS` (it's a content scanner, not an import scanner).
- `ca4cb92 feat: add BMad workflow infrastructure and Story 1-3 CI/CD implementation` — added `.github/workflows/{ci,e2e,release,docs}.yml`. The `ci.yml` 8-cell matrix will run Story 1.8's tests on every PR; the `--frozen` cache invalidates ONCE when pyyaml is added (Task 1.2), then caches for subsequent runs.
- `0b4acd9 upload (Story 1.2)` — established `[tool.mypy] strict = true`, `[tool.pytest.ini_options] minversion = "8.0"`, `[tool.coverage.report] fail_under = 90`. Story 1.8 inherits all three. `extra_checks = true` (line 108) bans `Any`-leak; Story 1.8's `dict[str, object]` typing matches.
- `0dd96ea feat: bootstrap sdlc-framework with uv + hatchling (Story 1.1)` — initial `pyproject.toml` with `dependencies = []`. Story 1.7 added `pydantic>=2,<3`. Story 1.8 adds `pyyaml>=6,<7` — the second runtime dep. `[project] dependencies` is now a 2-element list.

The 5-commit window confirms: every quality gate is configured, the boundary-validator pre-knows about `config/`, the `MODULE_DEPS` table grants are in place, and `pyproject.toml` is ready to receive its second runtime dep.

### Latest tech information (2026-05 lookup)

- **PyYAML stability**: PyYAML 6.0 GA released 2021-10; latest as of 2026-05 is 6.0.x line. The library has been stable for years; `safe_load`/`safe_dump` are the canonical APIs. The C-extension `_yaml` is bundled with the wheel for Python 3.10/3.11/3.12/3.13. There is no public roadmap for PyYAML 7.x; the `<7` cap is purely defensive. Resolved version on disk will be captured per Task 1.2.
- **`yaml.safe_load`**: returns `dict | list | str | int | float | bool | None`. Tags like `!!python/object`, `!!python/name` are rejected (this is the security feature that distinguishes safe_load from load).
- **`yaml.YAMLError`** is the root exception class for parser failures. Story 1.8 catches `yaml.YAMLError` (NOT the more specific `yaml.scanner.ScannerError`/`yaml.parser.ParserError`) for compatibility across YAML failure modes.
- **`pydantic` + `tuple[str, ...]`**: pydantic v2 coerces `list[str]` (yaml.safe_load output) to `tuple[str, ...]` per the type annotation. Verified in pydantic 2.5+; should hold for all 2.x.
- **`re.Pattern` compilation cost**: pre-compiled patterns (Story 1.8's `SECRET_PATTERNS` tuple) avoid per-call compilation. Each `pattern.sub` is microseconds; total `sanitize()` overhead for a 1KB string is sub-millisecond. NFR-PERF-2 (agent dispatch latency under 500 ms) is unaffected.
- **`os.environ.get(name)`**: returns `str | None`; thread-safe; no GIL contention; the canonical Python idiom for env reads. The framework-wide ban on `os.environ[name]` (subscript) is enforced by code review + the principle that `read_env()` is the ONLY allowed env-read site.
- **`pyyaml` 6.0.2 known issue**: NaN/Infinity floats round-trip non-canonically; not a concern for `project.yaml` (no float fields in v1).

### Project Structure Notes

- **Alignment with unified project structure** (Architecture §914-§917, §1057): canonical `src/sdlc/config/{__init__.py, project.py, env.py, secrets.py}` filenames are honored exactly. Architecture §914 enumerates the directory; §915-§917 enumerate the three implementation files; §1057 declares the public API surface.
- **`tests/unit/config/` directory creation**: NEW subdirectory introduced by this story. Architecture §686 says "tests/ mirrors src/sdlc/ structure"; Stories 1.6/1.7 established `tests/unit/{errors,ids,contracts}/`. Story 1.8 adds `tests/unit/config/` as the fourth.
- **`tests/integration/test_secret_hygiene.py` placement**: Architecture §990 lists this exact path; Story 1.8 fulfills it. The test is a SMOKE (forward-reference) for future state/journal integration; Stories 1.10/1.11 will extend it with real state.json/journal.log secret-write attempts.
- **`scripts/check_no_hardcoded_secrets.py` placement**: NEW file; Architecture §1042-§1045 enumerates `scripts/` contents (`validate_specialists.py`, `chaos_test.py`, `golden_corpus_check.py`). Story 1.8 adds `check_no_hardcoded_secrets.py` as the FOURTH script. The boundary-validator's `scripts/` exemption (Story 1.4 deferred line 68: "scripts/ directory not in MODULE_DEPS") means this script is dev-tooling, not production code; it does NOT need a MODULE_DEPS row.
- **`.pre-commit-config.yaml` modification**: NEW hook entry (`secret-hardcode-validator`) inserted between `boundary-validator` and `specialist-validator`. Hook order matters per Story 1.4 + ADR-010 (lint → format → type → custom validators → hygiene); the new hook is a "custom validator" by classification.

### Future ADR backlog item — NOT this story

A future story (likely Story 1.21's wire-format-immutability lock ceremony, OR the next architecture-revision pass) will:

- Author `ADR-014-config-module.md` (the Story 1.5 ADR-template precedent reserves ADR-014; Story 1.6 deferred ADR-014 trigger to "10th SdlcError subclass or EXIT_CODE_MAP semantics change" — neither was triggered).
- Document the `legacy_code_globs: tuple[str, ...]` coercion-from-YAML-list as the canonical pydantic-v2 + pyyaml interaction pattern.
- Document the `read_env` allow-list as the framework-wide env-read discipline; back-fix Architecture §618-§619 wording from prose to a referenced rule.
- Document the `sanitize_mapping` + `to_envelope` composition as the Story 1.16 CLI integration target.
- Author `ADR-015-secret-redaction-patterns.md` enumerating the 5 patterns + rationale for which integrations they cover; Revisit-by 12 months from authoring.

**Owner:** Story 1.21 OR the next architecture revision. Recorded HERE so a story-slicer or sprint-planner knows the trigger.

### Why no `state.mutate(...secret...)` static check yet

NFR-SEC-1's verification clause includes "Static linter scans framework source for `state.mutate(...secret...)` patterns." `state.mutate()` does not exist in v1 because `state/` is implemented in Story 1.10. The NFR-SEC-1 STATIC LINTER part of the verification is THEREFORE deferred:

- **Story 1.8 (THIS STORY) ships:** `scripts/check_no_hardcoded_secrets.py` — scans for ANY hardcoded secret literal in `src/sdlc/`. This is a SUPERSET of the eventual "code calling state.mutate with secret-shaped args" check.
- **Story 1.10 ships:** `state/atomic.py` with the `write_state_atomic()` function. After 1.10, the linter can be tightened to scan for `write_state_atomic(...)` calls with secret-shaped string args (or, more generally, any literal-secret-string passed to a write-to-disk function).
- **Story 1.11 ships:** `journal/writer.py` with the `journal.append()` function. After 1.11, the linter expands to journal write sites.

The deferred-work.md entry will be added at code-review time of Story 1.10 (or sooner if the gap is flagged).

### Pydantic v2 import discipline (don't import what you don't use)

`from pydantic import BaseModel, ConfigDict, Field, ValidationError` — these are the FOUR pydantic symbols Story 1.8's `project.py` uses (`ValidationError` is needed because the loader catches it for the `_wrap_validation_error` function). Story 1.7 used three; Story 1.8 adds `ValidationError` because we wrap pydantic errors into `ConfigError` exclusively.

NOT to be imported (and NOT used in v1):

- `from pydantic import field_validator, model_validator` — no custom validators in v1 (the `extra="forbid"` config + the `ge=1` constraints on int fields replace what custom validators would do).
- `from pydantic import Annotated` — not needed; `int` with `Field(ge=1)` is the canonical pattern.
- `from pydantic import RootModel` — `ProjectConfig` has 4 fields; not appropriate.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.8](_bmad-output/planning-artifacts/epics.md) (lines 601-624) — original BDD acceptance criteria for `config/` module.
- [Source: _bmad-output/planning-artifacts/prd.md#Configuration-Secret-Hygiene](_bmad-output/planning-artifacts/prd.md) (lines 795-798) — FR51 + FR52 specification.
- [Source: _bmad-output/planning-artifacts/prd.md#Security](_bmad-output/planning-artifacts/prd.md) (lines 832-833) — NFR-SEC-1 + NFR-SEC-2 verification clauses.
- [Source: _bmad-output/planning-artifacts/architecture.md#Configuration-and-Secret-Hygiene](_bmad-output/planning-artifacts/architecture.md) (lines 125, 491, 537, 566, 671, 914-917, 1057, 1192, 1264, 1272) — architectural placement, dependency boundaries, code style rules.
- [Source: _bmad-output/planning-artifacts/architecture.md#Module-Specifications](_bmad-output/planning-artifacts/architecture.md) (lines 1052-1112) — module dependency table; `config/` row at line 1057.
- [Source: _bmad-output/implementation-artifacts/1-7-foundation-five-wire-format-pydantic-contracts.md](_bmad-output/implementation-artifacts/1-7-foundation-five-wire-format-pydantic-contracts.md) — Story 1.7's pydantic v2 + frozen + Literal idioms; same discipline for `ProjectConfig`.
- [Source: _bmad-output/implementation-artifacts/1-6-foundation-errors-and-ids-modules.md](_bmad-output/implementation-artifacts/1-6-foundation-errors-and-ids-modules.md) — Story 1.6's `SdlcError` + `ConfigError` exception hierarchy + `details: dict[str, object]` pattern.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md](_bmad-output/implementation-artifacts/deferred-work.md) (line 22) — Story 1.6 deferred entry naming Story 1.8 as owner of "JSON-safe sanitization layer."
- [Source: src/sdlc/errors/base.py](src/sdlc/errors/base.py) (lines 22-38, 69-70) — `SdlcError` base class with `details: dict[str, object]` and `to_envelope()`; `ConfigError` subclass with `code = "ERR_CONFIG"`.
- [Source: scripts/check_module_boundaries.py](scripts/check_module_boundaries.py) (lines 42-45) — `MODULE_DEPS["config"]` pre-grant: `depends_on={"errors", "contracts"}`, `forbidden_from={"engine", "dispatcher", "cli"}`.
- [Source: pyproject.toml](pyproject.toml) (lines 11-13, 96-110, 121-130, 141-159) — runtime deps, mypy strict + extra_checks, pytest config, coverage 90% gate.
- [Source: .pre-commit-config.yaml](.pre-commit-config.yaml) — existing hook chain that Task 7.3 amends.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 (2026-05-08)

### Latest Tech Information

- pyyaml resolved version: 6.0.3 (from `uv.lock` — `awk '/^name = "pyyaml"$/{getline; print}' uv.lock`)
- types-PyYAML 6.0.12.20260508 added to `[dependency-groups] dev` for mypy strict compliance
- Python 3.12.13 on darwin

### Debug Log References

- `RUF100` false positive: comment text `# noqa: RUF022 convention.` in `__init__.py` was parsed by ruff as a directive. Fixed by rewriting the comment without the noqa syntax.
- `SIM300` Yoda condition in `test_env.py`: `assert ENV_EXACT_ALLOWLIST == frozenset(...)` → fixed to `assert frozenset(...) == ENV_EXACT_ALLOWLIST`.
- JWT literal (134 chars) exceeded E501 in tests: split into multi-line string concatenation.
- mypy `unused-ignore` on `secrets.py`: `sanitize_mapping(value)` didn't need `# type: ignore[arg-type]` — removed.
- `types-PyYAML` stub added to dev deps to satisfy mypy strict `[import-untyped]` for `import yaml`.

### Completion Notes List

- All 9 ACs satisfied: AC1 (ProjectConfig loader), AC2 (read_env allow-list), AC3 (sanitize + sanitize_mapping + integration test + static linter), AC4 (hashability via tuple[str,...]), AC5 (__init__.py 9-name __all__), AC6 (100% coverage on config/*), AC7 (boundary-validator clean), AC8 (pyyaml>=6,<7 in runtime deps), AC9 (sprint-status transitions)
- 56 tests (53 unit + 3 integration) — all pass. Project total: 430 tests, 91% coverage (≥90 gate)
- Full pre-commit chain: ruff-check ✓, ruff-format ✓, mypy-strict ✓, boundary-validator ✓, secret-hardcode-validator ✓, specialist-validator ✓, hygiene ✓
- `scripts/check_no_hardcoded_secrets.py` (61 LOC) wired as new `secret-hardcode-validator` hook between boundary-validator and specialist-validator
- `types-PyYAML` added to dev deps (mypy stub; not shipped at runtime)
- Config module 100% line+branch coverage per targeted gate

### File List

**New files:**
- `src/sdlc/config/__init__.py`
- `src/sdlc/config/project.py`
- `src/sdlc/config/env.py`
- `src/sdlc/config/secrets.py`
- `tests/unit/config/__init__.py`
- `tests/unit/config/test_project.py`
- `tests/unit/config/test_env.py`
- `tests/unit/config/test_secrets.py`
- `tests/integration/__init__.py`
- `tests/integration/test_secret_hygiene.py`
- `scripts/check_no_hardcoded_secrets.py`

**Modified files:**
- `pyproject.toml` — added `pyyaml>=6,<7` (runtime), `types-PyYAML` (dev)
- `uv.lock` — regenerated with pyyaml 6.0.3 + types-pyyaml 6.0.12.20260508
- `.pre-commit-config.yaml` — added `secret-hardcode-validator` hook
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — transitions: ready-for-dev → in-progress → review

## Change Log

- 2026-05-08: Story 1.8 implemented — added `src/sdlc/config/` module (`project.py`, `env.py`, `secrets.py`), 56 tests (53 unit + 3 integration), `scripts/check_no_hardcoded_secrets.py` static linter wired into pre-commit; pyyaml 6.0.3 added as runtime dep; 100% config coverage, 91% global coverage.
