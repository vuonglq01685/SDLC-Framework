---
schema_version: 1
name: dangling-in-inline-code
title: Dangling Inside Inline Code
icon: "💡"
model: claude-sonnet-4-6
tools: []
read_globs: []
write_globs: []
description: Body has dangling refs inside inline code spans — must not trigger orphan error (P-R4).
---

Use the syntax `[[name-of-specialist]]` for wikilinks and `[Label](agents/some-name.md)` for markdown links.
The names `nonexistent-inline` shown above do not exist; this is intentional documentation.
