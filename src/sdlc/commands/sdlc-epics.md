# `/sdlc-epics`

Phase 1 epic generation (Story 2A.11). Dispatches the `epic-generator` specialist (primary-only) through the dispatcher, pre-write hooks, and PreToolUse bridge, then writes one JSON file per epic under `01-Requirement/04-Epics/`. The workflow spec lives at `src/sdlc/workflows_yaml/sdlc-epics.yaml`.

## CLI

```
sdlc epics "<idea>"
sdlc --json epics "<idea>"
```

(Exact flags and error codes ship with the `sdlc epics` subcommand implementation; until then, treat this document as the operator contract.)

## Behavior (target)

- **Inputs:** product idea text (same boundary semantics as other phase-1 commands).
- **Outputs:** canonical epic JSON (`schema_version`, `id`, `label`, `priority`, `dependencies`, `ordering`, `acceptance_criteria`, `drafted_at`, `drafted_by_specialist: epic-generator`).
- **Postconditions:** non-empty epics directory, every `*.json` valid against the epic contract, boundary line present in prompts.
- **Journal:** `agent_dispatched` + `artifact_written` events consistent with other phase-1 flows.

## Refusals (contract)

- Phase mismatch, uninitialized workspace, dispatch failure, and postcondition failures follow the same envelope patterns as `sdlc research` / `sdlc start`.

## See also

- Story 2A.11: `_bmad-output/implementation-artifacts/2a-11-sdlc-epics-and-sdlc-stories.md`
- Specialist: `src/sdlc/agents/phase1/epic-generator.md`
