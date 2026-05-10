---
schema_version: 1
name: dangling-in-html-comment
title: Dangling Inside HTML Comment
icon: "💬"
model: claude-sonnet-4-6
tools: []
read_globs: []
write_globs: []
description: Body has a dangling ref inside an HTML comment — must not trigger orphan error (P-R4).
---

Live content here.

<!--
TODO: implement [[nonexistent-in-comment]] reference and link
to [Example](agents/nonexistent-in-comment.md) once it exists.
-->

End of body.
