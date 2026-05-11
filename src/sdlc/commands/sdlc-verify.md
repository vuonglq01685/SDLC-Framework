---
description: Phase 1 artifact verification — dispatch artifact-verifier and append to frontmatter (FR8)
---

# /sdlc-verify

Run `sdlc verify <artifact-id>` to verify a single Phase 1 artifact (e.g.
`01-Requirement/01-PRODUCT.md`). The artifact-verifier specialist is
dispatched, its verdict is appended to the artifact's `verifications:`
frontmatter list (non-destructive), and a `kind=artifact_verified`
journal entry is emitted.

Example:

```
sdlc verify 01-Requirement/01-PRODUCT.md
```

Verifications stack: a single artifact may be verified multiple times.
Each invocation appends a new entry — no entries are ever overwritten.
The artifact body bytes (after the second `---` delimiter) are hashed
into `content_hash_at_verify` so subsequent frontmatter-only edits
remain hash-invariant.
