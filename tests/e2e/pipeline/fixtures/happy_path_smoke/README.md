# happy_path_smoke — Tier-2 Seed Scenario

Minimal pipeline replay: single `MockAIRuntime.dispatch` call via the 2A.0
`engine_dispatch_smoke` shim. Story 2A.3 replaces the shim with the real dispatcher.

## Inputs

`pipeline.yaml` — one step: `engine_dispatch_smoke` with `workflow_step="_smoke"`.
`mock_responses/_smoke.yaml` — fixture keyed by sha256("smoke test prompt"); shape mirrors
`tests/fixtures/mock_responses/_smoke.yaml` (canonical example per AC3).

## Expected goldens (2A.0 seed)

| File | Expected value |
|------|----------------|
| `final_journal_sha256` | `<no-journal>` (shim doesn't write state) |
| `signoff_hashes.json` | `[]` (no signoffs; arrives 2A.12) |
| `hook_chain_order.json` | `[]` (no hooks; arrives 2A.4) |
| `specialist_invocations.json` | single `_smoke` primary dispatch |
