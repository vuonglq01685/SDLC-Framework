# `/sdlc-research`

Phase 1 topical research (FR7). Dispatches the `technical-researcher` specialist (primary-only — no panel) through the dispatcher (Story 2A.3), pre-write hook chain (Story 2A.4), and PreToolUse bridge (Story 2A.6), then writes a stand-alone research artifact under `01-Requirement/02-Research/<slug>.md`. Re-runs with the same topic produce a deduplicating `-N` suffix (gaps filled compact); prior research is never overwritten.

## CLI

```
sdlc research "<topic>"
sdlc --json research "<topic>"
```

## Example

```
sdlc research "PCI compliance scope"
# → 01-Requirement/02-Research/pci-compliance-scope.md
sdlc research "PCI compliance scope"   # again
# → 01-Requirement/02-Research/pci-compliance-scope-2.md
```

## Behavior

- **Slug** derived from the topic: lowercase, runs of non-alphanumeric → single `-`, stripped, truncated at 80 chars on a hyphen boundary where possible.
- **Artifact frontmatter** (deterministic, CLI-authored — AC6/D2): `schema_version`, `kind: research`, `topic` (verbatim), `slug`, `researched_at` (RFC 3339 UTC ms with `Z` suffix), `researched_by_specialist: technical-researcher`.
- **Journal:** every invocation produces one `agent_dispatched` (actor `agent:technical-researcher`) + one `artifact_written` (actor `cli`). Boundary-line-bearing prompts (NFR-SEC-3) are recorded in `03-Implementation/agent_runs.jsonl`.

## Refusals (exit code 1 with error envelope)

- `ERR_NOT_INITIALIZED` — `.claude/state/state.json` is missing. Run `sdlc init` first.
- `ERR_PHASE_MISMATCH` — current phase is not 1. Run `sdlc start` to transition into phase 1 first; phase 0 / 2 / 3 are all refused (stricter than `/sdlc-start` which accepts phase 0 → 1 transition because research is a supplementary artifact, not a phase-entry artifact).
- `ERR_USER_INPUT` — topic is empty, or slugifies to empty (e.g., unicode-only `你好世界`), or the dedup counter is exhausted (`<slug>-999.md` already exists).
- `ERR_RESEARCH_DISPATCH_FAILED` — dispatch crashed mid-flight (exit code 2).

## v1 mock caveat

`sdlc research` currently dispatches against `MockAIRuntime` and writes a placeholder body — a `[WARN]` line is emitted to stderr on every invocation. Real Claude dispatch ships with Story 2B.1 (`ClaudeAIRuntime`). Until then, treat the on-disk artifact as a structural placeholder, not a research deliverable.

## See also

- Story 2A.9 spec: `_bmad-output/implementation-artifacts/2a-9-sdlc-research.md`
- Story 2A.10 `/sdlc-verify` appends `verifications: [...]` to this frontmatter (audit-grade chain-of-custody).
- Architecture §937-944, §956-962, §1052-1072.
