---
schema_version: 1
name: phase1-signoff-summarizer
title: "Phase 1 Signoff Summarizer"
icon: "✅"
model: sonnet
tools: []
read_globs:
  - "01-Requirement/**/*.md"
  - "01-Requirement/**/*.json"
write_globs:
  - "01-Requirement/SIGNOFF.md"
description: "Phase 1 signoff narrative summarizer. Produces a human-readable preamble for the SIGNOFF.md draft. NOT dispatched in v1 (AC1/D1 — mechanical generation used instead). Registered for Story 2B.8 activation."
---

# phase1-signoff-summarizer (Phase 1 placeholder)

**v1 stub — NOT dispatched in v1 (AC1/D1 decision).**

This specialist is registered for future use in Story 2B.8 when real specialist
content becomes available. In v1, `sdlc signoff 1` generates SIGNOFF.md
mechanically (deterministic hash listing) without AI dispatch.

When activated in 2B.8, this specialist will:
- Receive the artifact list and hashes as context
- Produce a narrative preamble summarizing the Phase 1 deliverables
- Output a structured summary in `AgentResult.output_text`

The hash computation itself is always deterministic and not AI-appropriate;
this specialist adds narrative value only.

Placeholder until the full prompt is replaced by Story 2B.8.
