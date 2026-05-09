# MockAIRuntime YAML Fixtures (Decision C2, Architecture §356, §692, §1012)

One YAML file per `workflow_step` value. Filename = `<workflow_step>.yaml` (e.g.
`sdlc-epics.yaml` for `workflow_step="sdlc-epics"`).

Top-level: mapping of `prompt_hash` (sha256:<hex>) → fixture record.

Fixture record schema (validated by `_Fixture` pydantic model in `runtime/mock.py`):

- `output_text: str` — the response text.
- `tool_calls: list` of mappings (default `[]`) — author as a YAML list of mappings; pydantic
  coerces it to `tuple[Mapping[str, object], ...]` on the loaded `AgentResult` (tuple is real-frozen,
  whereas `list` would not be — see `runtime/abc.py` docstring + Story 1.13 dev notes).
- `tokens_in: int` (≥ 0, strict — `true`/`false` rejected) — input token count.
- `tokens_out: int` (≥ 0, strict — `true`/`false` rejected) — output token count.

YAML notes:

- Filenames must use the lowercase `.yaml` suffix. Sibling `.yml` / `.YAML` / `.YML` files are
  rejected at fixtures-dir load time so authors don't silently lose a fixture to a typo.
- Duplicate `prompt_hash` keys within a single file fail-loud (PyYAML's default last-wins
  behavior is overridden by `_NoDuplicateKeysLoader`).
- Empty / comment-only files fail-loud at construction. Delete the file or add at least one entry.

Generate a prompt_hash:

```
python -c 'import hashlib; print("sha256:"+hashlib.sha256("YOUR PROMPT".encode("utf-8")).hexdigest())'
```

Per-workflow fixtures (`sdlc-epics.yaml`, `sdlc-task.yaml`, etc.) are owned by their
respective workflow stories (Stories 2A-9 onwards). Story 1.13 ships the SHAPE + a smoke
fixture only. Do NOT add per-workflow fixtures here until the relevant workflow story lands.
