# tests/e2e/pipeline — Tier-2 Pipeline Harness (MockAIRuntime)

See [tests/e2e/README.md](../README.md) for the overall strategy.
Reference: [ADR-027](../../../docs/decisions/ADR-027-e2e-test-framework-strategy.md).

## pipeline.yaml schema

```yaml
schema_version: 1
scenario: <name>
mock_responses_dir: "./mock_responses"   # relative to this pipeline.yaml
steps:
  - id: "<NN>_<label>"
    kind: "engine_dispatch_smoke"         # 2A.0 placeholder; Story 2A.3 adds "cli_invoke"
    workflow_step: "<step-key>"           # key into mock_responses/<step-key>.yaml
    prompt: "<prompt text>"
```

## MockAIRuntime fixture authoring

Each `mock_responses/<workflow_step>.yaml` file maps `sha256:<hex>` keys to fixture records.
See `src/sdlc/runtime/mock.py` docstring for the full YAML record shape — do NOT duplicate it here.

To compute the key for a given prompt:
```python
import hashlib
"sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
```

## Four Tier-2 golden files

All under `fixtures/<scenario>/goldens/`:

| File | Content |
|------|---------|
| `final_journal_sha256` | ts-excluded sha256 of `.claude/state/journal.log` or sentinel (PR3, PR14) |
| `signoff_hashes.json` | canonical JSON array of `{"phase": N, "hash": "sha256:<hex>"}` |
| `hook_chain_order.json` | canonical JSON array of `{"hook": ..., "command": ..., "arg_summary": ...}` |
| `specialist_invocations.json` | canonical JSON array of `{"specialist_id": ..., "kind": ..., "write_glob_set": [...]}` |

Sentinels for `final_journal_sha256` (PR12 — distinct values for absent vs empty):
  - `<no-journal>`  — journal.log file is absent or zero-byte.
  - `<empty-journal>` — file present but contains no non-blank JSON entries.

JSON canonicalization: `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), indent=2)` + `\n`.
PR-DR6 sanctions the `indent=2` deviation from `src/sdlc/journal/_canonical.py`'s
no-indent form for human-reviewable goldens (see ADR-027 amendment).

For 2A.0 seed: `signoff_hashes.json` = `[]`, `hook_chain_order.json` = `[]`
(hooks arrive in 2A.4; signoffs arrive in 2A.12).

## --update-goldens workflow

```
pytest tests/e2e/pipeline/ --update-goldens
```

Then inspect each diff in git and cite the change in your PR Change Log.

## Import boundary

Tier-2 code MAY import from: `sdlc.runtime`, `sdlc.errors`, `sdlc.contracts`.
MUST NOT import from: `sdlc.cli`, `sdlc.engine`, `sdlc.dispatcher` (not yet stable).
When Story 2A.3 lands, the pipeline runner imports the dispatcher through its public seam.

## Don't lie to yourself

`test_happy_path_smoke.py` includes a determinism test that runs the same scenario twice
and asserts byte-identical observations — proving MockAIRuntime has no state leakage.
The anti-tautology test in `tests/e2e/test_harness_anti_tautology.py` additionally verifies
that a missing mock fixture raises `MockMissError` with a clear error message.
