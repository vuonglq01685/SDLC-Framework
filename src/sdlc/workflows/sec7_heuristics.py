"""NFR-SEC-7 instruction-shape heuristics for workflow YAML fields (Story 2A.1, AC3).

This module is a literal-only sentinel against the most common
instruction-injection shapes — NOT a security control on its own. The full
prompt-injection corpus and adversarial regression land in Story 2B.4; this
story wires the catalog so 2B.4 has an attachment point.

The catalog is a frozen tuple of (name, predicate) pairs. Callers may iterate
the tuple to find ALL matches (for diagnostics) or stop at the first match
(for fail-loud rejection). Adding new heuristics for 2B.4 is a one-line
append here — no loader changes needed.

Alternatives considered: third-party prompt-injection libraries — rejected to
avoid new runtime dependencies (ADR-027 §"Alternatives Considered" pattern).
The four heuristics below cover the Attack Surface Model v1 patterns.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# Maximum permitted size for a single string field. Enforced as the stricter of
# (codepoint count) OR (UTF-8 byte length / 4) so that unicode-heavy payloads
# cannot evade the limit by packing many bytes into few codepoints.
# Spec line 40 mandates exposure at ``workflows.loader.MAX_FIELD_LEN`` — see
# ``loader.py`` for the re-export (Debug Log #2: circular-import workaround).
MAX_FIELD_LEN: int = 512

# Slash-command allowlist applied BEFORE generic heuristics to avoid
# false-positives on legitimate slash names that happen to contain
# heuristic-shaped substrings.
_SLASH_COMMAND_ALLOWLIST_RE = re.compile(r"^/[a-z][a-z0-9-]{0,63}$")


def _is_allowlisted_slash_command(value: str) -> bool:
    """Return True if value is a well-formed slash command exempt from heuristics."""
    return bool(_SLASH_COMMAND_ALLOWLIST_RE.match(value))


# --- Predicate implementations ---

# Tolerates hyphen / dot / underscore separators in addition to whitespace, plus
# common synonyms (disregard, forget, override, replace) for "ignore previous".
_INSTRUCTION_PREFIX_RE = re.compile(
    r"(?i)\b(ignore|disregard|forget|override|replace)"
    r"[\s\-_.]+(all[\s\-_.]+|the[\s\-_.]+)?"
    r"(previous|prior|above|earlier|preceding)"
    r"[\s\-_.]+(instructions?|directives?|orders?|prompts?|rules?)"
)
# Drops the trailing ``\n`` requirement so single-line / CRLF-terminated /
# end-of-string fenced blocks still match.
_FENCED_CODE_BLOCK_RE = re.compile(r"```[a-zA-Z]*(?:\r\n|\r|\n|\s|$)")
# Broadened tag set: includes assistant/user roles and accepts attributes,
# closing tags, and surrounding whitespace.
_XML_INSTRUCTION_TAG_RE = re.compile(
    r"<\s*/?\s*(system|prompt|instruction|context|assistant|user)\b[^>]*>",
    re.IGNORECASE,
)


def _length_overflow(value: str) -> bool:
    """Trigger when codepoint count exceeds MAX_FIELD_LEN OR UTF-8 byte length
    exceeds ``MAX_FIELD_LEN * 4`` (so emoji-packed payloads cannot evade)."""
    return len(value) > MAX_FIELD_LEN or len(value.encode("utf-8")) > MAX_FIELD_LEN * 4


_HEURISTICS: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("instruction_prefix", lambda s: bool(_INSTRUCTION_PREFIX_RE.search(s))),
    ("fenced_code_block", lambda s: bool(_FENCED_CODE_BLOCK_RE.search(s))),
    ("xml_instruction_tag", lambda s: bool(_XML_INSTRUCTION_TAG_RE.search(s))),
    ("length_overflow", _length_overflow),
)


def check_instruction_shape(value: str) -> tuple[str, Callable[[str], bool]] | None:
    """Return the FIRST matching ``(name, predicate)`` pair, or None.

    Preserves AC3's first-match-raise semantics for the loader's hot path.
    For multi-match diagnostics use :func:`check_all_instruction_shapes`.
    """
    for name, predicate in _HEURISTICS:
        if predicate(value):
            return (name, predicate)
    return None


def check_all_instruction_shapes(value: str) -> tuple[str, ...]:
    """Return the names of ALL matching heuristics in catalog order.

    Useful for error-message diagnostics so a user fixing one heuristic does
    not have to rediscover the others on the next round-trip.
    """
    return tuple(name for name, predicate in _HEURISTICS if predicate(value))


def check_instruction_shape_for_field(
    field_name: str, value: str
) -> tuple[str, Callable[[str], bool]] | None:
    """First-match check that exempts allowlisted ``slash_command`` values.

    Other field names fall through to the standard catalog.
    """
    if field_name == "slash_command" and _is_allowlisted_slash_command(value):
        return None
    return check_instruction_shape(value)
