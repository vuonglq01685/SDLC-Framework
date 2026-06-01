---
schema_version: 1
name: icon-too-long
title: "Icon Too Long Specialist"
icon: "ABCDE"
model: sonnet
tools: []
read_globs: []
write_globs: []
description: "Fixture for AC6 negative receipt — icon exceeds max_length=4."
---

# icon-too-long

Deliberately malformed fixture: the icon field has 5 characters, which exceeds
the SpecialistFrontmatter max_length=4 constraint.

This file exists ONLY to prove the 2A.2 frontmatter validator can reject a
malformed specialist (anti-tautology negative receipt, Story 2B.8 AC6).
