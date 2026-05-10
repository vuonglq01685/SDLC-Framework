---
schema_version: 1
name: dangling-in-code-block
title: Dangling Inside Code Block
icon: "📦"
model: claude-sonnet-4-6
tools: []
read_globs: []
write_globs: []
description: Body has a dangling ref inside a fenced code block — must not trigger orphan error (P-R4).
---

Documentation example:

```python
# Example only — these names do NOT exist in the registry.
load("agents/nonexistent-in-code.md")
ref("[[nonexistent-wiki-in-code]]")
```

End of body.
