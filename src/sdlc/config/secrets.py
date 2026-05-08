from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

REDACTION_MARKER: Final[str] = "<REDACTED:secret>"

# Patterns compiled once at module load for performance.
# Sources: epics.md:621, architecture.md:566 + NFR-SEC-1 (prd.md:832).
SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),  # OpenAI/Anthropic-shaped key
    re.compile(r"pk_(?:live|test)_[A-Za-z0-9]{20,}"),  # Stripe public key
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),  # GitHub PAT (36 chars typical)
    re.compile(r"AKIA[A-Z0-9]{16}"),  # AWS Access Key ID (20 chars)
    re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT three-segment
)


def sanitize(text: str) -> str:
    """Redact known secret patterns in text. Idempotent; non-matching strings pass through."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTION_MARKER, text)
    return text


def sanitize_mapping(obj: Mapping[str, object]) -> dict[str, object]:
    """Recursively redact secret-shaped strings in a mapping.

    Returns a NEW dict (input is not mutated).
    """
    result: dict[str, object] = {}
    for key, value in obj.items():
        result[key] = _sanitize_value(value)
    return result


def _sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    return value
