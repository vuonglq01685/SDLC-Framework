# Prompt-injection corpus (Story 2B.4)

Regression corpus for NFR-SEC-3 (user-text boundary) and NFR-SEC-7 / static
workflow checks. Discovered automatically by
`tests/security/test_prompt_injection_corpus.py` — **no test-code edits** when
adding a pattern.

## Layout

| Path                  | Purpose                                        |
|-----------------------|------------------------------------------------|
| `user_text/*.txt`     | Adversarial `/sdlc-start` idea strings         |
| `workflow_yaml/*.yaml`| Adversarial workflow fixtures                  |

Complements (does not duplicate) `tests/fixtures/workflows/adversarial/sec7/`
— enforced at test time by `test_workflow_corpus_complements_existing_sec7_fixtures`.

**Template census (Story 2B.5):** `tests/security/test_boundary_line_presence.py`
statically asserts every `*_prompt_builder` in `src/sdlc/dispatcher/prompts.py`
that interpolates CLI user text references `BOUNDARY_LINE` with
`<BOUNDARY>` ordered before `<USER_IDEA>`. This corpus exercises runtime
disposition; 2B.5 is the authoritative template gate per AC3/D2.

## User-text format

Each `user_text/*.txt` file consists of:

1. Metadata lines (`# key: value`, lowercase ASCII keys, one per line).
2. A `---` separator (required when a payload follows).
3. The raw attack payload — verbatim user idea, included after `---` byte-for-byte.

### Metadata fields

| Key                    | Required? | Allowed values                                                       |
|------------------------|-----------|----------------------------------------------------------------------|
| `category`             | yes       | One of the 10 epic categories + `benign` + `boundary_smuggling` (see below) |
| `expected_disposition` | yes       | `boundary-wrapped` or `rejected-at-validation`                       |
| `expected_reason`      | iff rejected | `boundary_marker`, `envelope_fragment`, `control_char`, `non_empty`, `too_long` |

`expected_disposition` semantics:

- **`boundary-wrapped`** — `phase1_prompt_builder` succeeds; the rendered prompt
  contains `BOUNDARY_LINE` exactly once **before** a single `<USER_IDEA>` envelope
  (import from `sdlc.dispatcher.prompts`; never hard-code the constant string).
- **`rejected-at-validation`** — `_validate_idea_text` raises `WorkflowError`
  before any prompt is built. The fixture MUST also declare an `expected_reason`
  matching one of the rejection sites in `src/sdlc/dispatcher/prompts.py`
  (lines ~104-125: boundary marker, envelope fragment, control chars, non-empty,
  byte-cap overflow).

### Categories (AC1)

The corpus covers the 10 attack-model categories named in the epic AC
(`_bmad-output/planning-artifacts/epics.md:1531-1557`) plus one `benign`
negative-control:

```
instruction_override, role_flip, system_prompt_leak, tool_invocation,
json_smuggling, base64_directive, rot13_obfuscation, multilingual,
url_exfiltration, command_substitution, benign
```

Plus one meta-category `boundary_smuggling` for fixtures that exercise the
`_validate_idea_text` rejection paths directly (NFKC-bypass, envelope-fragment
smuggling, etc.). `boundary_smuggling` is **not** in the AC1 attack list — it
is an additional defence-in-depth surface.

### Gotchas — payloads that auto-reject

`_validate_idea_text` (`src/sdlc/dispatcher/prompts.py:~104-125`) refuses to
build a prompt when the payload trips any of:

- empty / whitespace-only;
- > 8 KiB (UTF-8 bytes);
- any C0/C1 control character (excluding `\t`, `\n`, `\r`);
- the BOUNDARY_LINE substring (after NFKC + dash-fold + whitespace-collapse
  + lowercase normalisation — `_DASH_VARIANTS` covers en/em/figure/wave dashes);
- an envelope-breaking tag fragment (e.g. `</BOUNDARY>`, `</user_idea>`,
  `<system>` — see `_ENVELOPE_FRAGMENTS`).

A payload that trips any of these MUST declare `expected_disposition:
rejected-at-validation` with the matching `expected_reason`. A payload that
trips one of these by accident — when the author intended a `boundary-wrapped`
outcome — is a test failure with a declared-vs-actual diff (AC3/D1).

## Workflow-YAML format

Each `workflow_yaml/*.yaml` file MUST begin with two metadata comment lines
**before** any YAML content:

```yaml
# expected_rejector: loader|static_check
# expected_vector: instruction_shape|phantom_agent|glob_overlap|specialist_redirection
schema_version: 1
name: ...
```

The harness dispatches to the declared rejection layer:

- **`loader`** — `load_workflow(path)` itself raises `WorkflowError`.
  Covers SEC-7 heuristics (instruction prefix, fenced code block, XML tag,
  length overflow) and pydantic field validation. Filename convention: `sec7_*.yaml`.
- **`static_check`** — `load_workflow(path)` returns a valid `WorkflowSpec`
  and `validate_workflow(spec)` raises. Covers `_check_phantom_agents`,
  intra-agent glob overlap, inter-agent disjoint-writes overlap, and
  specialist-redirection patterns. Filename convention: `static_*.yaml`.

`expected_vector` enumerates the four PRD §354-355 vector classes:

| Vector key                 | Description                                             |
|----------------------------|---------------------------------------------------------|
| `instruction_shape`        | SEC-7 instruction-prefix / fenced-code / xml-tag / length |
| `phantom_agent`            | `write_globs` references an undeclared agent             |
| `glob_overlap`             | Two globs overlap (intra-agent OR cross-agent)           |
| `specialist_redirection`   | An agent's globs reach into another agent's territory    |

## Template census (Story 2B.5)

This corpus is **deliberately scoped to `phase1_prompt_builder`** for
`/sdlc-start` only (single primary user input). `phase1_compound_prompt_builder`
(multi-input variants such as `/sdlc-prd`) belongs to the
`tests/security/test_boundary_line_presence.py` template-census surface owned
by **Story 2B.5**.

Keep both stories cross-referenced when adding builders or templates:

- 2B.4 (this corpus) — **adversarial corpus** for builders we know.
- 2B.5 — **static enumeration** that asserts every template interpolating user
  text carries a `BOUNDARY_LINE` before the interpolation point — closes the
  "unknown new template" hole (AC3/D2 Recommended D1).

## Adding a pattern

1. Add a file under `user_text/` or `workflow_yaml/`.
2. Re-run the regression suite:
   ```bash
   uv run pytest tests/security/test_prompt_injection_corpus.py -q
   ```
   (Substitute `pytest` directly if your environment does not use `uv`.)
3. If `rejected-at-validation`, confirm the `expected_reason` matches actual
   behaviour — mismatches fail with a declared-vs-actual diff (AC3/D1).
4. If a new workflow vector class emerges, extend `_REQUIRED_VECTORS` in the
   harness AND the table above.

## Auto-discovery filters

The harness filters dotfiles, symbolic links, and non-files when discovering
corpus paths. macOS `.DS_Store`, Finder `._foo.txt` sidecars, and symlinks to
files outside the corpus directory are silently skipped. To deliberately
exclude a file from regression (e.g., during local triage), rename it to
start with a `.`.
