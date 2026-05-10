# Runbook: Diagnose Signoff Hash Drift

**Applies to:** Story 2A.7 — `sdlc signoff validate` raising `SignoffError` with `kind="drifted"` or `kind="missing"`

When a signoff draft references artifact hashes that no longer match the artifacts on disk,
`validate_signoff` raises a `SignoffError` before writing the canonical record. This runbook
explains how to identify what changed and recover.

---

## 1. Recognise the symptom

```
sdlc.errors.SignoffError: hash drift on artifact "01-Requirement/PRODUCT.md":
  expected sha256=abc123... got sha256=def456...
```

Or for a deleted artifact:

```
sdlc.errors.SignoffError: artifact missing: "01-Requirement/ASSUMPTIONS.md"
```

In both cases `validate_signoff` aborts without writing a canonical record. The signoff
draft file (`<phase-dir>/SIGNOFF.md`) is left unchanged.

---

## 2. Identify which artifact(s) drifted

The exception carries a `details` dict:

```python
except SignoffError as exc:
    print(exc.details["kind"])          # "drifted" | "missing"
    print(exc.details["artifact_path"]) # relative path from repo root
    print(exc.details.get("expected"))  # expected sha256 hex (drifted only)
    print(exc.details.get("actual"])    # actual sha256 hex   (drifted only)
```

Or run `sdlc signoff validate --phase <N>` and read the error output directly.

---

## 3. Determine what changed

### `kind="drifted"` — file was modified after the draft was written

```bash
git log --oneline -- <artifact_path>
git diff HEAD -- <artifact_path>
```

If the file appears unmodified in git but the hash differs, check for editor
artifacts (trailing newlines, BOM, line-ending normalization) or a filesystem
race during the draft step.

### `kind="missing"` — file was deleted after the draft was written

```bash
git log --oneline -- <artifact_path>   # confirm it existed
git status <artifact_path>             # deleted tracked? untracked?
```

---

## 4. Recovery paths

### Path A — the change is intentional (artifact was legitimately updated)

1. Recompute the artifact hash:
   ```bash
   python -c "
   from sdlc.signoff.hasher import compute_artifact_hash
   from pathlib import Path
   h = compute_artifact_hash(Path('<artifact_path>'), repo_root=Path('.'))
   print(h)
   "
   ```
2. Open `<phase-dir>/SIGNOFF.md` and update the `hash:` line for the drifted artifact.
3. Re-run validation:
   ```bash
   sdlc signoff validate --phase <N>
   ```
4. If validation passes, write the canonical record:
   ```bash
   sdlc signoff write --phase <N>
   ```

### Path B — the change was accidental (artifact was unintentionally modified)

1. Restore the artifact to its pre-modification state from version control:
   ```bash
   git checkout HEAD -- <artifact_path>
   ```
2. Re-run validation:
   ```bash
   sdlc signoff validate --phase <N>
   ```
3. If validation passes, write the canonical record.

### Path C — the artifact was intentionally deleted

1. Remove the deleted artifact's entry from `<phase-dir>/SIGNOFF.md`.
2. If this is a substantive scope change, ensure the relevant approver reviews and
   re-signs the draft before writing the canonical record.
3. Re-run validation and write the canonical record.

---

## 5. Prevention

- Draft the signoff **only after** all phase artifacts are finalized and in their committed state.
- Avoid editing phase artifacts between `sdlc signoff draft` and `sdlc signoff validate` — if a
  late fix is needed, redraft after the fix is committed.
- The hash algorithm is SHA-256 over the raw file bytes relative to the repo root
  (see `sdlc.signoff.hasher.compute_artifact_hash`). Line-ending normalization is
  **not** applied — use `.gitattributes` to enforce consistent line endings across platforms.

---

## Related

- `docs/runbooks/handle-hash-drift.md` — hook-hash trust store drift (different concern)
- `docs/runbooks/diagnose-hook-rejection.md` — `phase_gate_violation` causes and bypass policy
- `sdlc.errors.SignoffError` — all signoff error shapes carry a `details` dict
