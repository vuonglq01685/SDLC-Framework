# Cluster C–J Review Packet (26 proposals)

**Story:** 2A.10 — sdlc-verify
**Branch:** fix/2a-10-post-review-2026-05-12 (current HEAD: 2d8ffd1, post Cluster A+B)
**Scope:** Adversarial review of UNAPPLIED patch proposals before implementation.
**Cluster legend:** C/D = correctness + test-tightening; E/F = TOCTOU + concurrency; G/H = AC contract; I/J = boundary + audit

> All P-IDs below reference `_bmad-output/implementation-artifacts/2a-10-sdlc-verify.md` "Patches (P1–P36)" section, lines 482–522.

---

## P5 — CRLF + BOM in `_split_frontmatter_block`
Handle CRLF + BOM in `_split_frontmatter_block` (strip BOM, normalise CRLF→LF before split) OR strict-reject with `ERR_ARTIFACT_MALFORMED` — current behaviour silently treats malformed files as no-frontmatter.
**Site:** `src/sdlc/cli/_verify_frontmatter.py:78-103`

## P6 — `_read_state_phase` defensive defaults
Raise `ERR_STATE_CORRUPT` on JSON decode error / missing `phase` field / non-int phase (currently defaults to 1 → silent phase-bypass).
**Site:** `src/sdlc/cli/verify.py:75-84`

## P7 — Tighten symlink-escape + path-traversal assertions
Replace `OR "01-Requirement" in out` with exact `ERR_PATH_TRAVERSAL` match (trivially passes today).
**Site:** `tests/unit/cli/test_verify_preflight.py:144,178-187`

## P8 — Tighten `test_boundary_in_artifact_body_rejected`
Assert exact `ERR_ARTIFACT_CONTAINS_BOUNDARY` (current `OR "boundary" in out.lower()` is too loose).
**Site:** `tests/unit/cli/test_verify_boundary_guard.py:2033-2039`

## P9 — `_resolve_artifact_path` parent-symlink walk
Walk every parent component of the resolved path; reject if any is a symlink crossing target_root (current check only validates leaf containment; `01-Requirement/` itself being a symlink escapes).
**Site:** `src/sdlc/cli/verify.py:1205-1232`

## P10 — Close TOCTOU on artifact body
Pass pre-flight-read `artifact_content` into `append_and_persist_frontmatter` (or fail-loud on hash mismatch between pre-flight body hash and post-dispatch fresh-read body hash) to close TOCTOU.
**Sites:** `src/sdlc/cli/_verify_post.py:949-956`, `src/sdlc/cli/_verify_dispatch.py:287`

## P11 — Atomic write
Write to `<path>.tmp`, fsync, `os.replace` — current `Path.write_text` leaves truncated artifact on crash mid-write.
**Site:** `src/sdlc/cli/_verify_post.py:949-953`

## P12 — Two-phase commit order
Journal `artifact_verified` BEFORE frontmatter persistence so interrupt cannot leave artifact mutated without journal record.
**Site:** `src/sdlc/cli/_verify_dispatch.py:601-619`

## P13 — Surface `advance_state_seq` failures
Surface `advance_state_seq` failures explicitly via `ERR_STATE_SYNC_FAILED` (currently swallows StateError + OSError silently).
**Site:** `src/sdlc/cli/_verify_post.py:152-180`

## P14 — Reject oversized `verifier_note`
Reject (or fail-loud) when verifier returns >500 char note instead of silent truncation; preserves audit-trail integrity.
**Site:** `src/sdlc/cli/_verify_post.py:910-915`

## P16 — Grapheme-boundary truncation
Truncate `verifier_note` at grapheme boundary, not at character index 500 (current truncation may split surrogate pairs / mixed-script combiners).
**Site:** `src/sdlc/cli/_verify_post.py:910-915`

## P17 — Journal append file-lock
Add file lock (flock or `_journal_lock` abstraction) around journal append in `emit_artifact_verified` to prevent two concurrent `sdlc verify` processes racing on seq allocation.
**Site:** `src/sdlc/cli/_verify_post.py:emit_artifact_verified`

## P19 — Validate `verifications:` entry shape
Validate existing `verifications:` list entries are dict-shaped before appending (current code happily appends to a list of legacy strings, breaking `verification_index` semantics).
**Site:** `src/sdlc/cli/_verify_frontmatter.py:_append_verification`

## P20 — Ensure phase directory exists
Ensure `03-Implementation/` exists (or route Phase-1 agent_runs to a Phase-1 path) before journal append — test fixtures create it manually, real Phase-1 init may not.
**Site:** `src/sdlc/cli/_verify_dispatch.py:invoke_dispatch`

## P21 — Use `result.output` in tests
Use `result.output` (not `result.stderr + result.stdout`) consistently across e2e/integration tests — fragile across click versions.
**Site:** `tests/e2e/pipeline/test_sdlc_verify.py:1637`, others

## P23 — Tighten `test_partial_marker_substring_proceeds`
Assert mock `_invoke_dispatch.called == True` (current test trivially passes when guard short-circuits earlier).
**Site:** `tests/unit/cli/test_verify_boundary_guard.py:2025-2028`

## P24 — Hash-invariance regression
Add regression test pinning: no-frontmatter artifact → first verify → second verify hash invariance (currently untested; `_compute_body_hash` returns different bytes across the no-fm → with-fm transition).
**Site:** new test in `test_verify_frontmatter_edges.py`

## P25 — `_run_member` kwargs verification
Verify `_run_member` actually accepts `persist_artifact`/`target_path_override`/`observer` kwargs (panel-parity claim in docstring); add test or fix dispatcher signature if mismatched.
**Site:** `src/sdlc/dispatcher/core.py:_run_member`

## P26 — JSON-mode missing-arg test
Add JSON-mode missing-arg test for `sdlc verify` — Typer default error path may not emit a valid JSON envelope.
**Site:** new test in `tests/unit/cli/`

## P27 — Proper Typer ctx mock
Pass proper Typer ctx mock in e2e `_init_repo` helper (currently `ctx=None`) — silent contract drift risk if `run_init` reads `ctx.obj`.
**Site:** `tests/e2e/pipeline/test_sdlc_verify.py:1584-1589`

## P29 — AC7 hashes + payload keys (from DR1)
In `_panel_helpers._make_journal_entry` (or the `_run_member`/`emit_agent_dispatched` site) compute and set `before_hash = "sha256:<pre-verify on-disk bytes>"` for `agent_dispatched`. Add `attempt: int` to payload. Rename `idea_hash` → `artifact_hash_at_dispatch` for `/sdlc-verify`-routed dispatches (or branch on slash_command). For `artifact_verified` in `_verify_post.emit_artifact_verified`: set `before_hash = sha256(pre-verify on-disk file bytes incl. frontmatter)` and `after_hash = sha256(post-verify on-disk file bytes incl. frontmatter)`. Keep `content_hash_at_verify` in payload as the body-only hash (unchanged semantics — drives 2A.12 drift detection). Add regression tests pinning all four hashes.
**Sites:** `src/sdlc/dispatcher/_panel_helpers.py:113,422-452`, `src/sdlc/cli/_verify_post.py:144-145,978-991`

## P30 — Route verifier `status:"failed"` (from DR2 part 1)
In `_verify_dispatch.invoke_dispatch`, do NOT short-circuit on `result.outcome == "success"` only; also accept `result.outcome == "success"` with `verdict == "failed"` as a distinct path: run `parse_verdict_envelope` → `build_verification_entry(status="failed")` → run hook chain → `append_and_persist_frontmatter` → `emit_artifact_verified(payload.status="failed")` → exit non-zero. Dispatcher-decided `result.outcome != "success"` continues to fail loudly via `ERR_PANEL_DISPATCH_FAILED` (existing branch).
**Site:** `src/sdlc/cli/_verify_dispatch.py:275-282,573-619`

## P31 — Test verifier-failed branch (from DR2 part 2)
Add: (a) unit test in `test_verify_post.py` covering `build_verification_entry(status="failed")`; (b) integration test in `test_sdlc_verify.py` with MockAIRuntime canned response `{"verdict":"failed","note":"reason"}`, asserting frontmatter has the failed row + journal has `artifact_verified` with `payload.status="failed"` + exit code != 0; (c) e2e Tier-2 scenario #6 mirroring (b).
**Sites:** `tests/unit/cli/test_verify_post.py`, `tests/integration/test_sdlc_verify.py`, `tests/e2e/pipeline/test_sdlc_verify.py`

## P33 — CLI boundary guard normaliser parity (from DR4)
In `src/sdlc/cli/verify.py:_artifact_contains_boundary` import `_normalize_for_boundary_check` from `sdlc.dispatcher.prompts` (or promote it to a shared `prompts/boundary.py` helper) and compare normalised forms. Update the docstring (currently claims "case-sensitive byte match") to describe NFKC + dash-fold + whitespace-collapse + lowercase compare. Add regression tests: U+2013 EN DASH variant, NBSP-separated marker, lowercase-only marker — all must reject as `ERR_ARTIFACT_CONTAINS_BOUNDARY`.
**Sites:** `src/sdlc/cli/verify.py:204`, `src/sdlc/dispatcher/prompts.py:51-117`, new tests in `test_verify_boundary_guard.py`

## P34 — Wire `run_hook_chain` around frontmatter rewrite (from DR5)
In `_verify_post.append_and_persist_frontmatter`, BEFORE `artifact_path.write_text(...)`, construct a `HookPayload` for the frontmatter rewrite and call `run_hook_chain(build_pre_write_hook_chain(repo_root), payload, journal_path=journal_path)`. On `result.decision == "deny"`, abort the write, emit `ERR_HOOK_REJECTED`, and exit non-zero. Add test pinning that a `phase_gate` hook rejecting the rewrite produces a non-zero exit + no frontmatter mutation + appropriate journal entry.
**Site:** `src/sdlc/cli/_verify_post.py:949-956`

## P36 — Unknown verdict → "advisory" + audit flag (from DR7)
In `_verify_post.parse_verdict_envelope` and `build_verification_entry`, change the silent `"verified"` fallback to `"advisory"`. Add an extra flag to the `artifact_verified` journal payload: `verifier_payload_malformed: True` when the verdict was coerced (verdict missing, non-string, or not in ALLOWED_STATUSES). Add a stderr warning surfaced even in JSON mode (structured `warnings` array). Tests: unknown `verdict`, missing `verdict`, non-string `verdict`, `{"verdict":["verified"]}` (the unhashable case from P28).
**Sites:** `src/sdlc/cli/_verify_post.py:910-935,978-991`, new tests in `test_verify_post.py`

---

## Spec context — AC summary (from 2a-10-sdlc-verify.md AC1–AC10)

- **AC1:** `/sdlc-verify <artifact_id>` command exists; pre-flight body hash + path validation; emits structured envelope.
- **AC2:** Routes to panel/dispatcher via `_run_member` or equivalent; never bypasses dispatcher.
- **AC3:** Mock verifier deterministic; e2e covers happy/path-traversal/symlink/boundary/missing-state.
- **AC4:** Frontmatter appends a `verifications:` row (dict-shaped); deduped on `(date, agent_id)`.
- **AC5:** Dispatcher kwargs `persist_artifact=False` / `target_path_override` / `observer` (originally spec'd `suppress_artifact_write=True` — DR6 resolution: inverted-polarity rename).
- **AC6:** Journal emits `agent_dispatched` AND `artifact_verified` events with required keys.
- **AC7:** Hashes — `idea_hash` / `content_hash_at_verify` / `before_hash` / `after_hash` — pin the verify ceremony (DR1; promoted to P29).
- **AC8:** Module size — single file `cli/verify.py` ≤ Arch §1052-§1112 LOC cap (DR3 retroactive D4 → split with re-export façade).
- **AC9:** Quality gate green — ruff, mypy --strict, pytest, ≥90 % coverage, wire-format snapshots stable.
- **AC10:** Self-attestation — gate evidence bound to commit range (deferred W6).

## Common code references (cite these locations when reviewing)

```
src/sdlc/cli/
  verify.py                  (CLI surface; pre-flight; path resolution)        — 280 LOC
  _verify_dispatch.py        (panel dispatch; outcome routing)                 — 358 LOC
  _verify_post.py            (post-dispatch: parse verdict / append / journal) — 202 LOC
  _verify_frontmatter.py     (frontmatter split/parse/append)                  — 192 LOC
src/sdlc/dispatcher/
  core.py                    (_run_member; dispatch signature)                 — 498 LOC
  _panel_helpers.py          (_make_journal_entry; agent_dispatched payload)   — 611 LOC
  prompts.py                 (_normalize_for_boundary_check)                   — 283 LOC
tests/unit/cli/, tests/integration/, tests/e2e/pipeline/
```

## Appendix — Line-number rectifications post HEAD `2d8ffd1` (PC1 / Edge Case Hunter E1)

The original P5–P36 citations in `2a-10-sdlc-verify.md` lines 488–522 reference pre-split line numbers (when `cli/verify.py` was a single 835-LOC file). After AC8/D4 split and Cluster A+B patches, sites have moved. Use this table to map cited locations to HEAD-correct file:line ranges. Implementer MUST `git grep -n <symbol>` at apply-time and not trust the citations in the original P-list.

| P-ID | Cited location (stale) | HEAD-correct location | Symbol |
|------|------------------------|------------------------|--------|
| P5 | `_verify_frontmatter.py:78-103` | `_verify_frontmatter.py:76-118` | `_split_frontmatter_block` |
| P6 | `verify.py:75-84` | `verify.py:79-88` | `_read_state_phase` |
| P7 | `tests/unit/cli/test_verify_preflight.py:144,178-187` | unchanged (test file) | path-traversal assertions |
| P8 | `test_verify_boundary_guard.py:2033-2039` | `git grep -n test_boundary_in_artifact_body_rejected` (line may have drifted post Cluster A+B) | boundary test |
| P9 | `verify.py:1205-1232` | `verify.py:91-174` | `_resolve_artifact_path` |
| P10 | `_verify_post.py:949-956`, `_verify_dispatch.py:287` | `_verify_post.py:101-119`, `_verify_dispatch.py:302` | `append_and_persist_frontmatter` / `parse_verdict_envelope` callsite |
| P11 | `_verify_post.py:949-953` | `_verify_post.py:101-119` (write at `:116`) | `append_and_persist_frontmatter` |
| P12 | `_verify_dispatch.py:601-619` | `_verify_dispatch.py:302-338` | `parse_verdict → append → emit` block |
| P13 | `_verify_post.py:152-180` | `_verify_post.py:161-189` | `advance_state_seq` |
| P14 | `_verify_post.py:910-915` | `_verify_post.py:75-78` | `raw_note[:VERIFIER_NOTE_MAX_LEN]` |
| P15 | (applied Cluster A+B) | `_verify_post.py:133-144` | `verifier_note` payload key |
| P16 | `_verify_post.py:910-915` | DROPPED per DC1 resolution | — |
| P17 | `_verify_post.py:emit_artifact_verified` | `_verify_post.py:122-158` | `emit_artifact_verified` |
| P19 | `_verify_frontmatter.py:_append_verification` | `_verify_frontmatter.py:120-189` (approx; verify with grep) | `_append_verification` |
| P20 | `_verify_dispatch.py:invoke_dispatch` | `_verify_dispatch.py:invoke_dispatch` (line varies — find by name) | journal-append site |
| P21 | `tests/e2e/pipeline/test_sdlc_verify.py:1637`, others | grep `result.stderr` + `result.stdout` patterns | e2e fragility |
| P23 | `test_verify_boundary_guard.py:2025-2028` | grep `test_partial_marker_substring_proceeds` | weak assertion |
| P24 | new test in `test_verify_frontmatter_edges.py` | new file | hash invariance |
| P25 | `src/sdlc/dispatcher/core.py:_run_member` | DEFERRED per DC-W1 (W2-gated) | — |
| P26 | new test in `tests/unit/cli/` | new file | JSON envelope missing-arg |
| P27 | `tests/e2e/pipeline/test_sdlc_verify.py:1584-1589` | grep `_init_repo` helper | non-None ctx mock |
| P29 | `_panel_helpers.py:113,422-452`, `_verify_post.py:144-145,978-991` | `_panel_helpers.py:113,422-452` (verify with grep `_make_journal_entry`), `_verify_post.py:122-158` | journal payload keys |
| P30 | `_verify_dispatch.py:275-282,573-619` | `_verify_dispatch.py:291-338` | verifier-failed routing — but see E4: code partially works today; scope down per DC10 |
| P31 | tests in `test_verify_post.py`, `test_sdlc_verify.py`, `test_sdlc_verify.py` | unchanged (test files) | new tests |
| P33 | `verify.py:204`, `prompts.py:51-117` | `verify.py:232-242` (`_artifact_contains_boundary`), `prompts.py:51-117` | boundary normaliser |
| P34 | `_verify_post.py:949-956` | DC11-contingent: drop if dispatcher hooks cover; else `_verify_post.py:101-119` | `append_and_persist_frontmatter` |
| P36 | `_verify_post.py:910-935,978-991` | `_verify_post.py:48-79` (`parse_verdict_envelope`), `:82-98` (`build_verification_entry`), `:122-158` (`emit_artifact_verified`) | verdict envelope + journal |

The original packet text above remains the canonical proposal source; this appendix is the line-number-resolution table. When implementer applies a P-patch, first `git grep` the named symbol on HEAD, then locate the actual edit range.

---

## Review prompts (one per layer)

### Blind Hunter
You receive ONLY this packet. No project access, no spec. Treat each P-proposal as a standalone change proposal. For each one, hunt for:
- Internal inconsistencies (e.g. "raise ERR_X" but no error type defined; "add test" but no acceptance criterion to assert against)
- Vague / unfalsifiable wording ("fail-loud", "preserve audit-trail" without concrete signal)
- Ambiguity over WHO consumes the new field / event
- Hidden coupling implied by phrasing (e.g. P12 reorder might break P34 hook ordering)
- Cross-patch contradictions (e.g. P14 says "reject >500", P16 says "truncate at grapheme" — pick ONE)
- Missing rollback / migration story for shipped artifacts

Output as a Markdown list. Each finding: title, P-IDs involved, severity (CRITICAL/HIGH/MEDIUM/LOW), one-line evidence.

### Edge Case Hunter
You receive this packet AND read access to the project. Walk every branching path and boundary condition implied by each P-proposal. For each one, look for:
- Unhandled edge case that the proposal does NOT address (e.g. P11 atomic write: what if `os.replace` itself fails mid-test on Windows; P17 flock: what about Windows where flock is no-op; P9 parent-symlink walk: what about case-insensitive FS)
- Pre-existing code state that the proposal misreads (read the cited line ranges in the actual source — does the proposal description match what's there now?)
- Test fixtures the proposal assumes exist but don't
- Interaction with already-applied Cluster A+B patches (P1-P4, P15, P18, P28 + others already in HEAD 2d8ffd1)
- Race conditions the proposal claims to fix but only partially closes
- New code paths introduced that the proposal forgets to test (esp P29/P30/P33/P34/P36)

Output as a Markdown list. Each finding: title, P-IDs involved, severity, evidence pointing at concrete file:line.

### Acceptance Auditor
You receive this packet, the spec at `_bmad-output/implementation-artifacts/2a-10-sdlc-verify.md`, and read access. Check each P-proposal against the spec's AC1–AC10 and existing change-log entries. For each one, look for:
- AC violations introduced by the proposal (e.g. P36 advisory verdict — does AC1 envelope contract permit `status:"advisory"`?)
- Spec amendments piggy-backed in code patches without explicit AC-edit proposal (P29/P32/P35 are spec-text edits — verify only spec-text changes there, no silent code side-effects)
- Existing AC items the proposal silently breaks (e.g. P30 verifier-failed path — does AC2 dispatcher-bypass clause cover this branch?)
- Contract / wire-format snapshot regen required (any change to journal payload shape under ADR-024 mutation taxonomy)
- DR↔P mapping integrity (DR1→P29, DR2→P30+P31, DR3→P32, DR4→P33, DR5→P34, DR6→P35, DR7→P36 — verify each promotion captures the full DR resolution)
- Missing AC clauses needed for new behaviour (e.g. P34 hook deny on frontmatter rewrite — does any AC describe hook-rejection envelope?)

Output as a Markdown list. Each finding: title, P-IDs involved, AC/contract violated, severity, evidence.
