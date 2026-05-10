---
schema_version: 1
name: unsupported-forms
title: Unsupported Link Forms
icon: "🚫"
model: claude-sonnet-4-6
tools: []
read_globs: []
write_globs: []
description: Body contains link forms intentionally outside AC6 scope — must not trigger orphan error (P-R23).
---

Out-of-scope forms (per validator module docstring):

1. Relative-prefixed: [Doc](./agents/nonexistent-relative.md)
2. Parent-prefixed:   [Doc](../agents/nonexistent-parent.md)
3. With title:        [Doc](agents/nonexistent-titled.md "tooltip")
4. Padded wikilink:   [[ nonexistent-padded ]]

None of these reference real specialists, but all are intentionally not
validated by AC6 — broader scope deferred to Story 2B.8.
