# Codemap: sdlc.journal

**Story:** 1.11 — Append-Only Journal + Property Test
**ADR:** [ADR-014](../decisions/ADR-014-append-only-journal-protocol.md)

## Files

| File | Purpose |
|------|---------|
| `src/sdlc/journal/__init__.py` | Package init; semantic-order `__all__`; Windows stub raises `JournalError(step="windows_unsupported")` |
| `src/sdlc/journal/writer.py` | POSIX append protocol (`append`, `append_sync`); ~240 LOC after split |
| `src/sdlc/journal/_canonical.py` | `_normalize_strings` + `_canonicalize_entry` (lockstep with `state/atomic`) |
| `src/sdlc/journal/_seq.py` | `_read_highest_seq` (re-raises OSError as `JournalError(step="read_highest_seq")`) |
| `src/sdlc/journal/reader.py` | Cross-platform reader (`iter_entries`, `iter_after`); ~100 LOC |
| `scripts/check_no_journal_mutation.py` | AST linter rejecting mutation patterns; runtime drift check on `_CANONICAL_WRITE_API` |
| `tests/unit/journal/test_journal_append_protocol.py` | Per-step isolation tests for writer |
| `tests/unit/journal/test_journal_reader.py` | Unit tests for reader |
| `tests/unit/journal/test_canonical_lockstep.py` | Asserts `_normalize_strings` parity with `state.atomic` |
| `tests/unit/test_journal_mutation_validator.py` | Unit tests for static linter |
| `tests/property/test_journal_append_only.py` | Hypothesis property tests (3 properties × 1000 examples) |

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
