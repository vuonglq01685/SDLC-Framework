# `/sdlc-stories`

Phase 1 story generation (Story 2A.11). Dispatches the `story-writer` specialist (primary-only) through the dispatcher, pre-write hooks, and PreToolUse bridge, then writes story JSON files under `01-Requirement/05-Stories/<epic-id>/`. The workflow spec lives at `src/sdlc/workflows_yaml/sdlc-stories.yaml`.

## CLI

```
sdlc stories "<idea>"
sdlc --json stories "<idea>"
```

(Exact flags and error codes ship with the `sdlc stories` subcommand implementation; until then, treat this document as the operator contract.)

## Behavior (target)

- **Inputs:** product idea text (same boundary semantics as other phase-1 commands).
- **Outputs:** canonical story JSON per story (`schema_version`, `id`, `epic_id`, `seq`, user-story fields, `given_when_then`, `dependencies`, `drafted_at`, `drafted_by_specialist: story-writer`).
- **Postconditions:** non-empty stories tree, every story `*.json` valid, boundary line present in prompts.
- **Journal:** `agent_dispatched` + `artifact_written` events consistent with other phase-1 flows.

## Refusals (contract)

- Phase mismatch, uninitialized workspace, dispatch failure, and postcondition failures follow the same envelope patterns as `sdlc research` / `sdlc start`.

## See also

- Story 2A.11: `_bmad-output/implementation-artifacts/2a-11-sdlc-epics-and-sdlc-stories.md`
- Specialist: `src/sdlc/agents/phase1/story-writer.md`
