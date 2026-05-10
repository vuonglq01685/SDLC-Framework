# Runbook: Diagnose Hook Rejection

**Applies to:** Story 2A.4 — Pre-Write Hook Chain (`naming_validator` + `phase_gate`)

When a write attempt is blocked by the hook chain, `run_hook_chain` returns a `HookDecision.deny(...)` and the caller appends a `hook_rejected` journal entry. This runbook explains how to identify the cause and resolve it.

---

## 1. Find the rejection in the journal

```bash
sdlc logs --filter-kind hook_rejected
```

Each `hook_rejected` entry contains:

| Field | Meaning |
|---|---|
| `payload.hook` | Which hook blocked the write (`naming_validator` or `phase_gate`) |
| `payload.target` | The file path that was blocked |
| `payload.reason` | Human-readable explanation |
| `payload.error_code` | Machine-readable code (see §3) |

---

## 2. Error codes and resolution

### `naming_violation` (hook: `naming_validator`)

The file stem does not match the canonical artifact-ID regex for its directory.

**Scoped directories:**

| Directory | Required ID shape |
|---|---|
| `01-Requirement/04-Epics/` | `EPIC-<slug>` |
| `01-Requirement/05-Stories/<epic>/` | `<epic>-S<N>-<slug>` |
| `01-Requirement/06-Tasks/<epic>/<story>/` | `<story>-T<N>-<slug>` |

All other paths are **always allowed** — `naming_validator` only applies to the three directories above.

**Resolution:**

1. Check the rejection reason: the regex that the stem must match is quoted in `payload.reason`.
2. Rename the file so its stem matches the canonical regex.
3. Retry the write.

> `naming_validator` is **never bypassable** (NFR-SEC-4, AC6). Bypassing it would corrupt the artifact-ID audit trail that `sdlc trace` and `sdlc rebuild-state` rely on.

---

### `phase_gate_violation` (hook: `phase_gate`)

A write to a Phase 2 or Phase 3 path was attempted without the required prior-phase signoff.

| Target path prefix | Required signoff |
|---|---|
| `02-Architecture/` | `.claude/state/signoffs/phase-1.yaml` with `approved: true` |
| `03-Implementation/` | `.claude/state/signoffs/phase-2.yaml` with `approved: true` |

**Phase 1 paths (`01-Requirement/`) and all other paths (`.claude/`, `tests/`, etc.) are always allowed.**

**Resolution — normal path:**

1. Ensure the previous phase's work is reviewed and approved.
2. Create the signoff file:

   ```yaml
   # .claude/state/signoffs/phase-1.yaml
   approved: true
   phase: 1
   approved_by: "your.email@example.com"
   approved_at: "2026-05-10T12:00:00.000Z"
   ```

3. Retry the write.

**Resolution — emergency bypass:**

If the gate must be bypassed (e.g., critical hotfix during an incident), use `--force-bypass-signoff` (Story 2A.4, AC6):

```bash
sdlc write <file> --force-bypass-signoff --justification "P0 incident: fixing auth crash before retro"
```

Bypass requirements:
- Justification must be **≥ 10 characters**.
- The hook trust store must be **initialized and not uninitialized**. Run `sdlc trust-hooks` first if needed.
- Bypass journals a `bypass_signoff` entry (actor: `hooks.runner`) with your identity, the justification, and the phase that was bypassed.
- Bypass is **per-dispatch** — it does not persist across writes.

> `naming_validator` is **still enforced** even with `--force-bypass-signoff`.

---

### `phase_gate_violation` (sub-case: corrupted signoff)

The signoff file exists but contains invalid YAML.

**Symptom:** `payload.reason` contains `"is corrupted (YAML parse error)"`.

**Resolution:**

1. Open `.claude/state/signoffs/phase-N.yaml` and fix the YAML syntax.
2. Validate with `python -c "import yaml; yaml.safe_load(open('.claude/state/signoffs/phase-N.yaml').read())"`.
3. Retry the write.

---

### `hook_internal_error`

A hook raised an unhandled exception during execution. `run_hook_chain` converts it to a deny with `error_code: hook_internal_error`.

**Resolution:**

1. Check `payload.reason` for the exception message.
2. Report the error to the SDLC Framework maintainers with the full journal entry.

---

## 3. Summary of error codes

| `error_code` | Hook | Bypassable? | Fix |
|---|---|---|---|
| `naming_violation` | `naming_validator` | **No** | Rename the file |
| `phase_gate_violation` | `phase_gate` | Yes (with justification + trust) | Create prior-phase signoff or bypass |
| `hook_internal_error` | any | — | Report bug |

---

## 4. Diagnosing Claude-side rejections

Claude Code's PreToolUse hook (`claude_hooks/pre_tool_use.py`) shells out to `sdlc hook-check`
for every `Write`, `Edit`, or `MultiEdit` call. If Claude Code shows a block that you did not
expect, follow these five steps:

**Step 1 — Locate the rejection in the journal.**

```bash
sdlc trace --kind hook_rejected | grep claude_pretooluse
```

Claude-side rejections carry `write_intent` values like `"claude_pretooluse_write"`, `"claude_pretooluse_edit"`, or `"claude_pretooluse_multiedit"` (AC10 discriminator).
Engine-side rejections carry `write_intent="dispatcher_artifact_write"`.

**Step 2 — Confirm the hook is installed.**

```bash
ls <repo>/.claude/hooks/pre_tool_use.py
```

If absent, run `sdlc init` (or copy `src/sdlc/claude_hooks/pre_tool_use.py` manually).

**Step 3 — Reproduce out of Claude using `sdlc hook-check`.**

```bash
echo '{"schema_version":1,"hook_name":"pre_write","target_path":"02-Architecture/01-UX/tokens.md","target_kind":"write_intent","content_hash_before":null,"write_intent":"claude_pretooluse_write"}' \
  | sdlc hook-check
```

This exercises the identical engine path as the Claude-side hook, without requiring a
Claude Code session.

**Step 4 — Mismatch: Claude-side allows but engine-side denies (fail-open divergence).**

`pre_tool_use.py` is fail-open: if `sdlc hook-check` exits with no stdout (e.g., crash or
timeout) it emits `{"decision": "approve"}` and lets Claude proceed. Engine-side will then
block the write on the next dispatch. Check `stderr` of the subprocess:

```bash
python src/sdlc/claude_hooks/pre_tool_use.py <<'EOF'
{"tool_name":"Write","tool_input":{"file_path":"02-Architecture/01-UX/tokens.md"},"cwd":"/path/to/repo"}
EOF
```

Look for `[pre_tool_use WARN]` lines on stderr. If present, `sdlc hook-check` is failing
internally — run Step 3 to diagnose.

**Step 5 — Both sides deny (real violation).**

Fix the artifact ID or create the required signoff:

- `naming_violation` → rename the file per §2.
- `phase_gate_violation` → create `.claude/state/signoffs/phase-N.yaml` per §2 or bypass per §2.

---

## 5. Related

- `docs/runbooks/handle-hash-drift.md` — when `trust_uninitialized` or `trust_corrupted` blocks bypass
- `sdlc trust-hooks` — initialize / refresh hook-hash trust store
- Architecture §363–§365 (hook chain decisions D1/D2)
- NFR-SEC-4, AC6 — bypass policy
