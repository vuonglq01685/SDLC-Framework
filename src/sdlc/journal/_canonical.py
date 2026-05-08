"""Canonical JSON serialization helpers for journal entries (Architecture §501-§508, §513).

Extracted from ``sdlc.journal.writer`` to keep writer.py within the ≤200 LOC target
(ADR-014 Decision D1). The functions here mirror ``sdlc.state.atomic._normalize_strings``
byte-for-byte; ``MODULE_DEPS["journal"].depends_on`` excludes ``state`` so the duplication
is required (factoring up the dependency graph is out of v1 scope).

Lockstep enforcement: tests/unit/journal/test_canonical_lockstep.py imports both copies
and asserts byte-identical canonicalization for a fixed corpus.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from sdlc.contracts.journal_entry import JournalEntry


def _normalize_strings(obj: Any) -> Any:
    """Recursively NFC-normalize all string values (Architecture §513).

    Duplicated from ``sdlc.state.atomic._normalize_strings`` to respect
    ``MODULE_DEPS["journal"].depends_on`` which excludes ``state``. Both copies must stay
    in lockstep — DO NOT factor up the dependency graph (out of v1 scope).
    """
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _normalize_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_strings(item) for item in obj]
    return obj


def _canonicalize_entry(entry: JournalEntry) -> bytes:
    r"""Return canonical JSONL bytes for a journal entry (Architecture §501-§508, §513).

    Terminating ``\n`` is REQUIRED for JSONL — distinct from hash-canonicalization which
    omits it.
    """
    payload = _normalize_strings(entry.model_dump(mode="json"))
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )
