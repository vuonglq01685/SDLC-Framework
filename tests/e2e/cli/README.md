# tests/e2e/cli — Tier-1 CLI Golden Harness

See [tests/e2e/README.md](../README.md) for the overall strategy.
Reference: [ADR-027](../../../docs/decisions/ADR-027-e2e-test-framework-strategy.md).

## commands.yaml schema

```yaml
schema_version: 1
scenario: <name>
commands:
  - id: "<NN>_<cmd>"   # e.g. "01_init" — the NN prefix drives golden file names
    args: ["<cmd>"]    # positional args passed to sdlc (after --no-color)
    flags: []          # required (PR30); reserved for per-command flags (e.g. ["--json"])
```

Duplicate keys raise a `ConstructorError` at load time (`_NoDuplicateKeysLoader`).
PR30: `flags` is now a required field — the prior dead-schema status meant typos
like `flgs:` silently passed.

## Golden file naming

Each command produces five golden files under `fixtures/<scenario>/goldens/`:

| File | Content |
|------|---------|
| `<NN>_<cmd>.stdout` | stdout (path-normalized + project-name normalized + ANSI-stripped) |
| `<NN>_<cmd>.stderr` | stderr (uv preamble stripped, path-normalized) |
| `<NN>_<cmd>.exit` | decimal exit code + newline |
| `<NN>_<cmd>.journal_sha256` | ts-excluded journal content hash of `.claude/state/journal.log` + newline |
| `<NN>_<cmd>.state_sha256` | raw-bytes sha256 of `.claude/state/state.json` + newline |

Sentinels (PR12 — distinct values for absent vs empty journals):
  - `<no-journal>`  — journal.log file is absent or zero-byte.
  - `<empty-journal>` — file present but contains no non-blank JSON entries.
  - `<no-state>` — state.json file is absent.

PR1: stdout contains `<TMP>` (absolute paths) and `<PROJECT>` (basename of
the working directory) sentinels so goldens are stable across pytest's per-test
tmp_path naming. Don't bake test-function-derived basenames into goldens.

## --update-goldens workflow

```
pytest tests/e2e/cli/ --update-goldens   # regenerate all golden files
```

Then: inspect each diff in git, explain the change in your PR Change Log, and get it
through review-A. CI never passes `--update-goldens` (asserted by `test_harness_anti_tautology.py`).

## POSIX-only commands

Commands that use `journal.append_sync` (POSIX flock) must be decorated at the test level:

```python
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only flock")
```

See `test_walking_skeleton_goldens.py` for the pattern.

## Don't lie to yourself

`tests/e2e/test_harness_anti_tautology.py` verifies that `assert_goldens` correctly
FAILS on corrupted goldens. After modifying this module, re-run the anti-tautology tests.
