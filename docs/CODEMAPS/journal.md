# Codemap: sdlc.journal

**Story:** 1.11 — Append-Only Journal + Property Test
**ADR:** [ADR-014](../decisions/ADR-014-append-only-journal-protocol.md)

## Files

| File | Purpose |
|------|---------|
| `src/sdlc/journal/__init__.py` | Package init; semantic-order `__all__`; Windows stub for writer |
| `src/sdlc/journal/writer.py` | POSIX append protocol (`append`, `append_sync`); ~200 LOC |
| `src/sdlc/journal/reader.py` | Cross-platform reader (`iter_entries`, `iter_after`); ~90 LOC |
| `scripts/check_no_journal_mutation.py` | AST linter rejecting mutation patterns |
| `tests/unit/journal/test_journal_append_protocol.py` | Per-step isolation tests for writer |
| `tests/unit/journal/test_journal_reader.py` | Unit tests for reader |
| `tests/unit/test_journal_mutation_validator.py` | Unit tests for static linter |
| `tests/property/test_journal_append_only.py` | Hypothesis property tests (1000 examples × 2 properties) |

## Public API

```python
from sdlc.journal import append, append_sync, iter_entries, iter_after
```

- `append(entry: JournalEntry, journal_path: Path) -> None` — async, POSIX-only
- `append_sync(entry: JournalEntry, journal_path: Path) -> None` — sync, test-only
- `iter_entries(journal_path: Path) -> Iterator[JournalEntry]` — cross-platform
- `iter_after(journal_path: Path, threshold: int) -> Iterator[JournalEntry]` — cross-platform

## Module Dependencies

`MODULE_DEPS["journal"].depends_on = {"errors", "contracts", "concurrency", "config"}`
