from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

REDACTION_MARKER: Final[str] = "<REDACTED:secret>"
_CIRCULAR_PLACEHOLDER: Final[str] = "<circular>"

# Patterns compiled once at module load for performance.
# Sources: epics.md:621, architecture.md:566 + NFR-SEC-1 (prd.md:832).
SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),  # OpenAI/Anthropic-shaped key
    re.compile(r"pk_(?:live|test)_[A-Za-z0-9]{20,}"),  # Stripe public key
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),  # GitHub PAT (36 chars typical)
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),  # AWS Access Key ID (20 chars), bounded
    re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT
)


def sanitize(text: str) -> str:
    """Redact known secret patterns in text. Idempotent; non-matching strings pass through."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTION_MARKER, text)
    return text


def sanitize_mapping(obj: Mapping[str, object]) -> dict[str, object]:
    """Recursively redact secret-shaped strings in a mapping.

    Returns a NEW dict (input is not mutated). Recurses into nested dicts,
    lists, tuples, sets, and frozensets. Self-referential cycles in mutable
    containers are replaced with ``<circular>``. Non-string keys raise
    ``TypeError`` per the signature contract.
    """
    seen: set[int] = {id(obj)}
    result: dict[str, object] = {}
    for key, value in obj.items():
        if not isinstance(key, str):
            raise TypeError(
                f"sanitize_mapping requires str keys; got {type(key).__name__}"
            )
        result[key] = _sanitize_value(value, seen)
    return result


def _sanitize_value(value: object, seen: set[int]) -> object:
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, Mapping):
        oid = id(value)
        if oid in seen:
            return _CIRCULAR_PLACEHOLDER
        new_seen = seen | {oid}
        nested: dict[str, object] = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"sanitize_mapping requires str keys; got {type(key).__name__}"
                )
            nested[key] = _sanitize_value(val, new_seen)
        return nested
    if isinstance(value, list):
        oid = id(value)
        if oid in seen:
            return _CIRCULAR_PLACEHOLDER
        new_seen = seen | {oid}
        return [_sanitize_value(v, new_seen) for v in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(v, seen) for v in value)
    if isinstance(value, frozenset):
        return frozenset(_sanitize_value(v, seen) for v in value)
    if isinstance(value, set):
        return {_sanitize_value(v, seen) for v in value}
    return value
