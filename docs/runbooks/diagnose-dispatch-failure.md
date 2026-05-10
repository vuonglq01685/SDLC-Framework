# Runbook: Diagnose a Dispatch Failure

**Applies to:** any `DispatchResult` or `PanelResult` with `outcome="failed"`, or a hung `/sdlc-*` command that exhausted retries.

## Background

`dispatcher.core.dispatch()` and `dispatch_panel()` wrap each specialist call in `with_retries(max_attempts=3, backoff=1s/4s)`. On terminal failure the dispatcher:

1. Returns a result with `outcome="failed"` (does NOT raise — the engine/CLI decides whether to halt).
2. Appends a `JournalEntry(kind="stop_trigger_raised")` placeholder (Epic 4 wires the STOP banner).
3. Does NOT write the artifact (`target_path` contains the last successful write, or the fallback path).

Two root causes are possible:

| Class | Examples | Retried? | Signal |
|---|---|---|---|
| **Transient** | `DispatchError` / `MockMissError` | Yes (3×) | `dispatch_attempt` journal rows with `outcome=retry` |
| **Config / operator** | `SpecialistError`, `WorkflowError`, `ConfigError` | No | Single `dispatch_attempt` row, propagated immediately |

---

## Step 1 — Locate the failure window in `agent_runs.jsonl`

```bash
# Show last 20 dispatch records, most-recent first
tail -20 .claude/agent_runs.jsonl | python3 -c "
import sys, json
for line in reversed(sys.stdin.read().splitlines()):
    if line.strip():
        r = json.loads(line)
        print(f\"{r['ts']}  {r['outcome']:8s}  attempts={r['attempts']}  {r['specialist_name']}  ({r['target_kind']})\")
"
```

A transient failure that exhausted retries looks like:

```
2026-05-10T12:34:56.789Z  failed    attempts=3  product-strategist  (primary)
```

A config failure that propagated immediately looks like:

```
2026-05-10T12:34:57.001Z  failed    attempts=1  product-strategist  (primary)
```

---

## Step 2 — Read the per-attempt journal trace

```bash
sdlc trace --kind=dispatch_attempt | tail -20
```

This filters `journal.log` for `dispatch_attempt` entries and shows the `outcome` field for each attempt:

```
seq=0  ts=...  dispatch_attempt  outcome=retry   attempt=1  specialist=product-strategist
seq=1  ts=...  dispatch_attempt  outcome=retry   attempt=2  specialist=product-strategist
seq=2  ts=...  dispatch_attempt  outcome=failed  attempt=3  specialist=product-strategist
```

Three rows for the same specialist means all retries were exhausted (transient path).
One row with `outcome=failed` means the error was non-retryable (config/operator path).

---

## Step 3 — Check for the STOP-trigger placeholder

```bash
sdlc trace --kind=stop_trigger_raised | tail -5
```

A `stop_trigger_raised` entry confirms the panel short-circuited and no synthesizer ran.
The `payload.specialist` field names which member failed first:

```json
{
  "kind": "stop_trigger_raised",
  "payload": {
    "trigger": "agent_failure_after_retries",
    "specialist": "product-strategist",
    "step": "requirements",
    "epic_4_placeholder": true
  }
}
```

> **Note:** `epic_4_placeholder: true` means the STOP banner itself is not yet wired (Epic 4 Story 4.6). The entry is diagnostic only in Epic 2A.

---

## Step 4 — Identify retry-vs-config failures

### Transient (retried): 3 `dispatch_attempt` rows

Cause: the runtime returned an error on every attempt. With `MockAIRuntime`, this means the fixture file for this prompt hash is missing (`MockMissError`) or the YAML is malformed.

```bash
# Find the prompt hash that caused the miss
grep "MockMissError\|fixture" .claude/debug_events.jsonl 2>/dev/null | tail -10
```

Fix: add or correct the fixture file under `tests/e2e/pipeline/fixtures/<workflow>/mock_responses/`.

### Config / operator (not retried): 1 `dispatch_attempt` row with `outcome=failed`

| Error class | Meaning | Fix |
|---|---|---|
| `SpecialistError` | Specialist name not found in registry | Check `specialists/` manifest; verify frontmatter `name:` matches the workflow YAML |
| `WorkflowError` | Workflow YAML failed static checks | Re-run `sdlc-start` after fixing the YAML |
| `DispatchError("write_globs")` | Workflow step has no `write_globs` entry for this specialist | Add the entry to the step's `write_globs` map |
| `ConfigError` | Missing or invalid project config | Check `project.yaml` for `max_parallel_agents` and other required fields |

---

## Step 5 — Replay a single dispatch for debugging

There is no `sdlc replay-dispatch` command in v1. To replay manually:

```python
import asyncio
from sdlc.dispatcher.core import dispatch
from sdlc.runtime.mock import MockAIRuntime
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.workflows.registry import WorkflowRegistry
from pathlib import Path

registry = WorkflowRegistry.from_yaml(Path("workflows/"))
step = registry.get("requirements")
specialist_registry = SpecialistRegistry.from_manifest(Path("specialists/"))
runtime = MockAIRuntime(fixtures_dir=Path("tests/e2e/pipeline/fixtures/dispatch_panel/mock_responses/"))

result = asyncio.run(dispatch(
    step,
    runtime=runtime,
    registry=specialist_registry,
    repo_root=Path("."),
    journal_path=Path(".claude/journal.log"),
    agent_runs_path=Path(".claude/agent_runs.jsonl"),
    _max_attempts=1,  # single attempt for debugging
))
print(result)
```

---

## Quick-reference: dispatch failure checklist

- [ ] `agent_runs.jsonl` shows `outcome=failed` — note `attempts` count
- [ ] `sdlc trace --kind=dispatch_attempt` shows retry vs. immediate failure
- [ ] `sdlc trace --kind=stop_trigger_raised` identifies which panel member failed
- [ ] If `attempts=3`: check fixture files / runtime connectivity
- [ ] If `attempts=1`: check specialist names, workflow YAML, and project config
- [ ] Artifact at `target_path` is stale (last successful write) — do not rely on it
